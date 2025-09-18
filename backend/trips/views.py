import uuid
from decimal import Decimal
from math import asin, cos, radians, sin, sqrt
from typing import Any

import requests
from django.db import transaction
from requests.adapters import HTTPAdapter
from requests.exceptions import ConnectionError as ReqConnectionError, RequestException
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from urllib3.exceptions import NameResolutionError
from urllib3.util.retry import Retry

from core.crypto import decrypt_value
from drivers.models import DriverProfile

from .models import Trip
from .serializers import TripCreateSerializer, TripSerializer


def estimate_hours(distance_miles: float, avg_speed_mph: float = 55.0) -> float:
    return round(distance_miles / max(avg_speed_mph, 1.0), 2)


def plan_fueling_stops(distance_miles: float, avg_mpg: float | None) -> list:
    # If mpg unknown, fall back to coarse stops every ~1000 miles
    if not avg_mpg or avg_mpg <= 0:
        leg = 1000.0
    else:
        # Simple heuristic: assume 150 gal tank, stop every 80% of range
        tank_gallons = 150.0
        range_miles = tank_gallons * float(avg_mpg)
        leg = 0.8 * range_miles
    stops = []
    remaining = distance_miles
    while remaining > leg:
        stops.append({"mile": round(distance_miles - remaining + leg, 2)})
        remaining -= leg
    return stops


class TripListCreateView(generics.ListCreateAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Trip.objects.filter(owner=self.request.user).order_by("-created_at")

    def get_serializer_class(self):
        return TripSerializer if self.request.method == "GET" else TripCreateSerializer

    @transaction.atomic
    def perform_create(self, serializer):  # type: ignore[override]
        user = self.request.user
        user.refresh_from_db()
        assert hasattr(user, "mapbox_api_key_encrypted"), "Invalid user model"
        # Enforce minimal completeness using Driver fields (profile optional)
        # Older tests/users may not have completed nested DriverProfile yet.
        minimal_required = [
            user.name,
            user.license_no,
            getattr(user, "time_zone", None),
            getattr(user, "units", None),
        ]
        if not all(bool(f) for f in minimal_required):
            raise ValueError("Complete your profile: name, license #, time zone, and units")
        # If DriverProfile exists, ensure critical fields present (backward-compatible with tests)
        profile = DriverProfile.objects.filter(driver=user).first()
        if profile is not None:
            if not (profile.license_state and profile.time_zone):
                raise ValueError("Complete your profile: home terminal state and time zone")

        if not user.mapbox_api_key_encrypted:
            raise ValueError("Mapbox API key not set in profile")
        api_key = decrypt_value(user.mapbox_api_key_encrypted)

        data = serializer.validated_data

        def _normalize_coordinates(s: str) -> str | None:
            parts = [p.strip() for p in s.split(",")]
            if len(parts) != 2:
                return None
            try:
                a = float(parts[0])
                b = float(parts[1])
            except Exception:
                return None
            # a=lon, b=lat
            if -180.0 <= a <= 180.0 and -90.0 <= b <= 90.0:
                return f"{a},{b}"
            # a=lat, b=lon (flip)
            if -90.0 <= a <= 90.0 and -180.0 <= b <= 180.0:
                return f"{b},{a}"
            return None

        # Generate a session_token to group Search Box requests
        session_token = str(uuid.uuid4())

        def _geocode_to_lonlat(query: str) -> tuple[str, str | None]:
            # If coordinates provided (lon,lat or lat,lon), normalize and pass through
            norm = _normalize_coordinates(query)
            if norm is not None:
                return norm, None
            # Use Mapbox Search Box API (forward geocoding)
            # Minimal safety: URL encode handled via params
            sb_url = "https://api.mapbox.com/search/searchbox/v1/suggest"
            sb_params = {
                "q": query,
                "access_token": api_key,
                "limit": 1,
                "session_token": session_token,
            }
            try:
                r = requests.get(sb_url, params=sb_params, timeout=10)
                if r.status_code == 200:
                    js = r.json()
                    if js.get("suggestions"):
                        sid = js["suggestions"][0].get("mapbox_id")
                        if sid:
                            det_url = "https://api.mapbox.com/search/searchbox/v1/retrieve"
                            det = requests.get(
                                det_url,
                                params={
                                    "id": sid,
                                    "access_token": api_key,
                                    "session_token": session_token,
                                },
                                timeout=10,
                            )
                            if det.status_code == 200:
                                dj = det.json()
                                feats = dj.get("features") or []
                                if feats:
                                    f0 = feats[0]
                                    props = f0.get("properties", {}) if isinstance(f0, dict) else {}
                                    # 1) geometry center
                                    center = (
                                        (f0.get("geometry", {}) or {}).get("coordinates")
                                        if isinstance(f0.get("geometry", {}), dict)
                                        else None
                                    )
                                    coords = None
                                    if (
                                        isinstance(center, list)
                                        and len(center) == 2
                                        and all(isinstance(x, (int, float)) for x in center)
                                    ):
                                        coords = center
                                    else:
                                        # 2) bbox midpoint
                                        bbox = f0.get("bbox") or props.get("bbox")
                                        if (
                                            isinstance(bbox, list)
                                            and len(bbox) == 4
                                            and all(isinstance(x, (int, float)) for x in bbox)
                                        ):
                                            lon = (float(bbox[0]) + float(bbox[2])) / 2.0
                                            lat = (float(bbox[1]) + float(bbox[3])) / 2.0
                                            coords = [lon, lat]
                                        else:
                                            # 3) properties center/coordinates
                                            alt = props.get("center") or props.get("coordinates")
                                            if (
                                                isinstance(alt, list)
                                                and len(alt) == 2
                                                and all(isinstance(x, (int, float)) for x in alt)
                                            ):
                                                coords = alt

                                    if coords is not None:
                                        label = (
                                            props.get("name")
                                            or props.get("place_name")
                                            or f0.get("name")
                                            or None
                                        )
                                        return f"{coords[0]},{coords[1]}", label
            except Exception:
                pass
            # 4) Final fallback: Mapbox Geocoding API (permissive)
            try:
                from requests.utils import quote  # local import to avoid top-level costs

                url_gc = f"https://api.mapbox.com/geocoding/v5/mapbox.places/{quote(query)}.json"
                gc = requests.get(url_gc, params={"access_token": api_key, "limit": 1}, timeout=10)
                if gc.status_code == 200:
                    jg = gc.json()
                    feats = jg.get("features") or []
                    if feats:
                        f0 = feats[0]
                        center = f0.get("center")
                        if (
                            isinstance(center, list)
                            and len(center) == 2
                            and all(isinstance(x, (int, float)) for x in center)
                        ):
                            label = f0.get("place_name") or f0.get("text")
                            return f"{center[0]},{center[1]}", label
            except Exception:
                pass
            # If still unresolved, raise error
            raise ValueError(
                f"Unable to geocode '{query}'. Enter coordinates 'lon,lat' or a more specific name."
            )

        current_location, current_label = _geocode_to_lonlat(data["current_location"])  # lon,lat
        pickup_location, pickup_label = _geocode_to_lonlat(data["pickup_location"])  # lon,lat
        dropoff_location, dropoff_label = _geocode_to_lonlat(data["dropoff_location"])  # lon,lat
        pickup_time = data.get("pickup_time")
        dropoff_time = data.get("dropoff_time")

        # Build Mapbox Directions API request similar to playground sample
        # Simplify: inputs are "lon,lat" strings
        url = "https://api.mapbox.com/directions/v5/mapbox/driving"
        params = {
            "alternatives": "true",
            "annotations": "distance,duration,maxspeed",
            "geometries": "polyline",
            "language": "en",
            "overview": "full",
            "steps": "true",
            # simple default vehicle constraints (metric units)
            "max_height": "4.1",
            "max_width": "2.6",
            "max_weight": "36.29",
            "access_token": api_key,
        }
        coords = f"{current_location};{pickup_location};{dropoff_location}"
        # Use a session with retries to better handle transient DNS/network hiccups
        session = requests.Session()
        retries = Retry(
            total=3,
            connect=3,
            read=3,
            backoff_factor=0.5,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods={"GET"},
        )
        adapter = HTTPAdapter(max_retries=retries)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        try:
            resp = session.get(f"{url}/{coords}", params=params, timeout=20)
        except (NameResolutionError, ReqConnectionError) as e:
            raise ValueError(
                "Network error reaching Mapbox. Please check your internet/VPN and try again."
            ) from e
        except RequestException as e:
            raise ValueError("Failed to call Mapbox Directions API") from e
        if resp.status_code != 200:
            try:
                detail = resp.json().get("message")
            except Exception:
                detail = None
            raise ValueError(f"Mapbox error: {resp.status_code}{' - ' + detail if detail else ''}")
        js = resp.json()
        if not js.get("routes"):
            raise ValueError("No route found")
        route = js["routes"][0]
        distance_m = float(route.get("distance", 0.0))
        distance_miles = distance_m / 1609.344
        geometry_resp: Any = route.get("geometry")
        # If Mapbox returned polyline, decode to GeoJSON LineString
        geometry: Any
        if isinstance(geometry_resp, str):
            try:
                import polyline  # type: ignore

                # Try polyline precision 5 first (Mapbox "polyline")
                coords_latlng = polyline.decode(geometry_resp)
                if not coords_latlng:
                    # Fallback to precision 6 (Mapbox "polyline6")
                    coords_latlng = polyline.decode(geometry_resp, 6)
                coords_lnglat = [[lon, lat] for lat, lon in coords_latlng]
                geometry = {"type": "LineString", "coordinates": coords_lnglat}
            except Exception:
                # Final fallback: empty geometry if decode fails
                geometry = {"type": "LineString", "coordinates": []}
        else:
            # Already GeoJSON
            geometry = geometry_resp

        est_hours = estimate_hours(distance_miles)
        stops = plan_fueling_stops(distance_miles, float(user.avg_mpg) if user.avg_mpg else None)

        # If we have route coordinates and planned stop mileposts, place stop markers along the line
        try:
            coords: list[list[float]] = (
                geometry.get("coordinates", []) if isinstance(geometry, dict) else []
            )
            if coords and len(coords) > 1 and stops:
                # Pre-compute cumulative distances along the polyline in miles
                def haversine_miles(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
                    R = 3958.7613  # Earth radius in miles
                    lon1r, lat1r, lon2r, lat2r = map(radians, [lon1, lat1, lon2, lat2])
                    dlon = lon2r - lon1r
                    dlat = lat2r - lat1r
                    a = sin(dlat / 2) ** 2 + cos(lat1r) * cos(lat2r) * sin(dlon / 2) ** 2
                    c = 2 * asin(min(1.0, sqrt(a)))
                    return R * c

                segment_miles: list[float] = []
                for i in range(1, len(coords)):
                    lon1, lat1 = coords[i - 1]
                    lon2, lat2 = coords[i]
                    segment_miles.append(haversine_miles(lon1, lat1, lon2, lat2))
                cumulative: list[float] = [0.0]
                for d in segment_miles:
                    cumulative.append(cumulative[-1] + d)

                total_length = cumulative[-1]

                # If Mapbox distance differs slightly, rely on polyline length
                def interpolate(
                    lon1: float, lat1: float, lon2: float, lat2: float, t: float
                ) -> list[float]:
                    return [lon1 + (lon2 - lon1) * t, lat1 + (lat2 - lat1) * t]

                updated_stops: list[dict] = []
                for s in stops:
                    mile = float(s.get("mile", 0.0))
                    # Clamp to route length
                    target = max(0.0, min(mile, total_length))
                    # Find segment where this mile falls
                    # cumulative[i] is distance up to vertex i
                    seg_index = 0
                    for i in range(1, len(cumulative)):
                        if cumulative[i] >= target:
                            seg_index = i - 1
                            break
                    # Handle edge cases
                    if seg_index >= len(coords) - 1:
                        coord = coords[-1]
                    else:
                        seg_start_m = cumulative[seg_index]
                        seg_len = max(1e-9, cumulative[seg_index + 1] - seg_start_m)
                        t = (target - seg_start_m) / seg_len
                        lon1, lat1 = coords[seg_index]
                        lon2, lat2 = coords[seg_index + 1]
                        coord = interpolate(lon1, lat1, lon2, lat2, t)
                    updated_stops.append({"mile": round(mile, 2), "coord": coord})

                stops = updated_stops
        except Exception:
            # If anything goes wrong, keep stops without coordinates
            pass

        # Minimal metadata to help frontend (legs and steps optional)
        route_metadata = {
            "distance": route.get("distance"),
            "duration": route.get("duration"),
            "legs": route.get("legs"),
            # human-friendly labels where available
            "origin_label": current_label,
            "pickup_label": pickup_label,
            "dropoff_label": dropoff_label,
        }

        trip = Trip.objects.create(
            owner=user,
            current_location=current_location,
            pickup_location=pickup_location,
            dropoff_location=dropoff_location,
            distance_miles=Decimal(str(round(distance_miles, 2))),
            estimated_hours=Decimal(str(est_hours)),
            fueling_stops=stops,
            pickup_time=pickup_time,
            dropoff_time=dropoff_time,
            route_geometry=geometry,
            route_metadata=route_metadata,
            # new trip fields
            log_date=data.get("log_date"),
            co_driver_name=data.get("co_driver_name") or "N/A",
            tractor_number=data.get("tractor_number") or "",
            trailer_numbers=data.get("trailer_numbers") or "",
            other_trailers=data.get("other_trailers") or "",
            shipper_name=data.get("shipper_name") or "",
            commodity_description=data.get("commodity_description") or "",
            load_id=data.get("load_id") or "",
        )
        self.instance = trip

    def create(self, request, *args, **kwargs):  # type: ignore[override]
        ser = TripCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            self.perform_create(ser)
        except Exception as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(TripSerializer(self.instance).data, status=status.HTTP_201_CREATED)


class TripDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = TripSerializer

    def get_queryset(self):
        return Trip.objects.filter(owner=self.request.user)

    def delete(self, request, *args, **kwargs):  # type: ignore[override]
        response = super().delete(request, *args, **kwargs)
        response.data = None
        return response


class SearchBoxSuggestView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, *args, **kwargs):  # type: ignore[override]
        user = request.user
        assert hasattr(user, "mapbox_api_key_encrypted"), "Invalid user model"
        if not user.mapbox_api_key_encrypted:
            return Response({"detail": "Mapbox API key not set in profile"}, status=400)
        api_key = decrypt_value(user.mapbox_api_key_encrypted)

        q = request.query_params.get("q")
        session_token = request.query_params.get("session_token")
        if not q or not session_token:
            return Response({"detail": "q and session_token are required"}, status=400)
        try:
            r = requests.get(
                "https://api.mapbox.com/search/searchbox/v1/suggest",
                params={
                    "q": q,
                    "access_token": api_key,
                    "session_token": session_token,
                    "limit": request.query_params.get("limit", 5),
                },
                timeout=10,
            )
        except RequestException:
            return Response({"detail": "Failed to call Mapbox suggest"}, status=502)
        return Response(r.json(), status=r.status_code)


class SearchBoxRetrieveView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, *args, **kwargs):  # type: ignore[override]
        user = request.user
        assert hasattr(user, "mapbox_api_key_encrypted"), "Invalid user model"
        if not user.mapbox_api_key_encrypted:
            return Response({"detail": "Mapbox API key not set in profile"}, status=400)
        api_key = decrypt_value(user.mapbox_api_key_encrypted)

        mapbox_id = request.query_params.get("id")
        session_token = request.query_params.get("session_token")
        if not mapbox_id or not session_token:
            return Response({"detail": "id and session_token are required"}, status=400)
        try:
            r = requests.get(
                "https://api.mapbox.com/search/searchbox/v1/retrieve",
                params={
                    "id": mapbox_id,
                    "access_token": api_key,
                    "session_token": session_token,
                },
                timeout=10,
            )
        except RequestException:
            return Response({"detail": "Failed to call Mapbox retrieve"}, status=502)
        return Response(r.json(), status=r.status_code)
