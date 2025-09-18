import logging
from datetime import datetime, timedelta, timezone

from django.conf import settings
from django.http import HttpResponse
from django.template.loader import render_to_string  # type: ignore
from django.utils.timezone import make_aware, now
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from drivers.models import DriverProfile
from logs.models import DailyLog, Inspection, LogEvent
from logs.serializers import (
    DailyLogSerializer,
    InspectionCreateSerializer,
    InspectionSerializer,
    LogEventCreateSerializer,
    LogEventSerializer,
)
from trips.models import Trip

from .hos import LogEntry, calculate_daily_totals, detect_violations

logger = logging.getLogger(__name__)


# Temporary runtime shim for pydyf < 0.12 used by WeasyPrint >= 60
def _ensure_pydyf_compat() -> None:
    try:
        import inspect

        import pydyf  # type: ignore

        sig = inspect.signature(pydyf.PDF.__init__)
        # Older pydyf exposes PDF.__init__(self)
        # but WeasyPrint calls PDF(version, identifier)
        if len(sig.parameters) == 1:  # only 'self'
            _orig_init = pydyf.PDF.__init__  # type: ignore[attr-defined]

            # mypy: ignore[no-redef]
            def _patched_init(self, version=None, identifier=None, *args, **kwargs):
                _orig_init(self)
                # Add missing attributes for WeasyPrint compatibility
                # Ensure version is always bytes for comparison compatibility
                if version is None:
                    self.version = b"1.4"  # Default PDF version
                elif isinstance(version, str):
                    self.version = version.encode("utf-8")
                else:
                    self.version = version
                if identifier:
                    self.identifier = identifier

            pydyf.PDF.__init__ = _patched_init  # type: ignore[assignment]
    except Exception:
        # If anything goes wrong, let WeasyPrint raise normally
        pass


def _parse_utc_offset(offset_str: str | None) -> timedelta:
    if not offset_str or not offset_str.startswith("UTC"):
        return timedelta(0)
    try:
        sign = 1 if "+" in offset_str else -1
        hhmm = offset_str.split("UTC")[1].strip("+").strip("-")
        hours, minutes = hhmm.split(":")
        return sign * timedelta(hours=int(hours), minutes=int(minutes))
    except Exception:
        return timedelta(0)


class LogEventCreateView(generics.CreateAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def create(self, request, *args, **kwargs):  # type: ignore[override]
        ser = LogEventCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        trip_id = ser.validated_data["trip_id"]
        status_val = ser.validated_data["status"]
        timestamp = ser.validated_data.get("timestamp")
        if timestamp is None:
            timestamp = datetime.now(timezone.utc)
        if timestamp.tzinfo is None:
            timestamp = make_aware(timestamp)

        try:
            trip = Trip.objects.get(id=trip_id, owner=request.user)
        except Trip.DoesNotExist:
            return Response({"detail": "Trip not found"}, status=status.HTTP_404_NOT_FOUND)

        ev = LogEvent.objects.create(
            trip=trip,
            driver=request.user,
            day=timestamp.date(),
            timestamp=timestamp,
            status=status_val,
            city=ser.validated_data.get("city", ""),
            state=ser.validated_data.get("state", ""),
            activity=ser.validated_data.get("activity", ""),
        )
        return Response(LogEventSerializer(ev).data, status=status.HTTP_201_CREATED)


class LogEventListView(generics.ListAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = LogEventSerializer

    def get_queryset(self):  # type: ignore[override]
        trip_id = self.kwargs["trip_id"]
        return LogEvent.objects.filter(trip_id=trip_id, driver=self.request.user).order_by(
            "timestamp"
        )


class HOSSummaryView(generics.GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, *args, **kwargs):  # type: ignore[override]
        trip_id = kwargs.get("trip_id")
        try:
            Trip.objects.get(id=trip_id, owner=request.user)
        except Trip.DoesNotExist:
            return Response({"detail": "Trip not found"}, status=status.HTTP_404_NOT_FOUND)

        profile, _ = DriverProfile.objects.get_or_create(driver=request.user)
        offset = _parse_utc_offset(profile.time_zone)

        logs = LogEvent.objects.filter(trip_id=trip_id, driver=request.user).order_by("timestamp")
        # Group by local day (driver time zone)
        entries_by_day: dict[str, list[LogEntry]] = {}
        for ev in logs:
            t = ev.timestamp + offset
            day_local = t.date().isoformat()
            entries_by_day.setdefault(day_local, []).append(
                LogEntry(timestamp=ev.timestamp, status=ev.status)
            )

        # Build daily totals using the local day key
        daily = []
        for day, entries in sorted(entries_by_day.items()):
            totals = calculate_daily_totals(entries, day)
            daily.append(
                {
                    "day": day,
                    "totals": {
                        "OFF": totals.off_hours,
                        "SLEEPER": totals.sleeper_hours,
                        "DRIVING": totals.driving_hours,
                        "ON_DUTY": totals.on_duty_hours,
                    },
                }
            )

        violations = [vars(v) for v in detect_violations(entries_by_day)]

        return Response({"daily": daily, "violations": violations})


class DailyLogListView(generics.ListAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = DailyLogSerializer

    def get_queryset(self):  # type: ignore[override]
        trip_id = self.kwargs["trip_id"]
        return DailyLog.objects.filter(trip_id=trip_id, driver=self.request.user).order_by("day")


class DailyLogSubmitView(generics.GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, *args, **kwargs):  # type: ignore[override]
        trip_id = kwargs.get("trip_id")
        day = request.data.get("day")
        if not day:
            return Response({"detail": "day is required"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            Trip.objects.get(id=trip_id, owner=request.user)
        except Trip.DoesNotExist:
            return Response({"detail": "Trip not found"}, status=status.HTTP_404_NOT_FOUND)

        # Aggregate totals from log events for the specified day
        logs = LogEvent.objects.filter(trip_id=trip_id, driver=self.request.user, day=day).order_by(
            "timestamp"
        )
        entries = [LogEntry(timestamp=ev.timestamp, status=ev.status) for ev in logs]
        totals = calculate_daily_totals(entries, day) if entries else None

        daily_log, _created = DailyLog.objects.get_or_create(
            trip_id=trip_id, driver=request.user, day=day
        )
        if totals:
            daily_log.total_off = totals.off_hours
            daily_log.total_sleeper = totals.sleeper_hours
            daily_log.total_driving = totals.driving_hours
            daily_log.total_on_duty = totals.on_duty_hours
        daily_log.submitted = True
        daily_log.submitted_at = now()
        daily_log.save()

        return Response(DailyLogSerializer(daily_log).data)


class InspectionCreateView(generics.CreateAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def create(self, request, *args, **kwargs):  # type: ignore[override]
        ser = InspectionCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        trip_id = ser.validated_data["trip_id"]
        performed_at = ser.validated_data.get("performed_at") or now()
        if performed_at.tzinfo is None:
            performed_at = make_aware(performed_at)  # type: ignore[arg-type]
        try:
            trip = Trip.objects.get(id=trip_id, owner=request.user)
        except Trip.DoesNotExist:
            return Response({"detail": "Trip not found"}, status=status.HTTP_404_NOT_FOUND)

        insp = Inspection.objects.create(
            trip=trip,
            driver=request.user,
            kind=ser.validated_data["kind"],
            performed_at=performed_at,
            defects=ser.validated_data.get("defects", []),
            signature_driver=ser.validated_data["signature_driver"],
            signature_mechanic=ser.validated_data.get("signature_mechanic", ""),
            notes=ser.validated_data.get("notes", ""),
        )
        return Response(InspectionSerializer(insp).data, status=status.HTTP_201_CREATED)


class InspectionListView(generics.ListAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = InspectionSerializer

    def get_queryset(self):  # type: ignore[override]
        trip_id = self.kwargs["trip_id"]
        return Inspection.objects.filter(trip_id=trip_id, driver=self.request.user).order_by(
            "-performed_at"
        )


class TripReportPDFView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def _render_html_pdf(self, request, trip: Trip, graphs_by_day: dict[str, bytes] | None = None):
        _ensure_pydyf_compat()
        profile, _ = DriverProfile.objects.get_or_create(driver=request.user)
        # Resolve prior-rendered log grid image (prefer SVG, match by day if available)
        graph_data_url = None
        # Accept from GET query (allows direct link download)
        graph_data_url = request.GET.get("graph_svg") or request.GET.get("graph_png") or None
        # Accept from POST body
        data = request.data or {}
        if settings.DEBUG:
            logger.debug("POST data received keys: %s", list(data.keys()))

        if not graph_data_url:
            if "graphs" in data and isinstance(data["graphs"], list) and data["graphs"]:
                if settings.DEBUG:
                    logger.debug("Found %d graph(s) in request data", len(data["graphs"]))
                desired_day = trip.log_date.isoformat() if trip.log_date else None
                if settings.DEBUG:
                    logger.debug("Looking for trip log_date: %s", desired_day)

                chosen = None
                # Try exact date match first
                if desired_day:
                    for i, item in enumerate(data["graphs"]):
                        if isinstance(item, dict):
                            item_day = str(item.get("day", ""))
                            if settings.DEBUG:
                                logger.debug(
                                    "Graph %d: day='%s', has_png=%s",
                                    i,
                                    item_day,
                                    bool(item.get("png")),
                                )
                            if item_day == desired_day:
                                chosen = item
                                if settings.DEBUG:
                                    logger.debug("Found exact match for %s", desired_day)
                                break

                # If no exact match, try the first available graph
                if not chosen and data["graphs"]:
                    first = data["graphs"][0]
                    if isinstance(first, dict):
                        chosen = first
                        if settings.DEBUG:
                            logger.debug("Using first available graph as fallback")

                if chosen:
                    graph_data_url = chosen.get("svg") or chosen.get("png")
                    if settings.DEBUG:
                        sel_len = len(graph_data_url) if graph_data_url else 0
                        logger.debug("Selected graph data URL length: %d", sel_len)
                else:
                    if settings.DEBUG:
                        logger.debug("No suitable graph found in data")
            else:
                # Try direct graph data in request body
                graph_data_url = data.get("graph_svg") or data.get("graph_png")
                if graph_data_url and settings.DEBUG:
                    direct_len = len(graph_data_url)
                    logger.debug("Found direct graph data in request body, length: %d", direct_len)

        # Simplified single-day approach
        if settings.DEBUG:
            size = len(graph_data_url) if graph_data_url else 0
            logger.debug("Using single-day approach with graph_data_url: %d chars", size)

        # Format locations using labels from route metadata when available, fallback to coordinates
        meta = trip.route_metadata or {}

        def _format_named(loc_str: str | None, label: str | None) -> str:
            if label:
                if loc_str and ("," in loc_str):
                    return f"{label} ({loc_str})"
                return label
            return self._format_location(loc_str)

        from_location_formatted = _format_named(
            trip.pickup_location, meta.get("pickup_label") or meta.get("origin_label")
        )
        to_location_formatted = _format_named(trip.dropoff_location, meta.get("dropoff_label"))

        # Format home terminal time (FMCSA compliant)
        home_terminal_time = self._format_home_terminal_time(profile.time_zone)

        ctx = {
            "log_date": (trip.log_date.isoformat() if trip.log_date else ""),
            "driver_name": request.user.name,
            "co_driver": trip.co_driver_name or "N/A",
            "from_location_formatted": from_location_formatted,
            "to_location_formatted": to_location_formatted,
            "home_terminal_time": home_terminal_time,
            "carrier_name": profile.carrier or "N/A",
            "main_office_address": profile.main_office_address or "N/A",
            "home_terminal_address": profile.home_terminal_address or "N/A",
            "tractor_no": trip.tractor_number or "N/A",
            "trailer_nos": trip.trailer_numbers or trip.other_trailers or "N/A",
            "total_miles_driven_today": trip.total_miles_driving_today or "0",
            "log_grid_image_url": graph_data_url or "",
            "shipper": trip.shipper_name or "N/A",
            "commodity": trip.commodity_description or "N/A",
            "load_id": trip.load_id or "N/A",
            "driver_signature": profile.driver_signature or "________________",
        }
        if settings.DEBUG:
            logger.debug("Final context - log grid len: %d", len(ctx["log_grid_image_url"]))
        html = render_to_string("driver_logs/driver_daily_log.html", ctx)
        _ensure_pydyf_compat()
        # Lazy import WeasyPrint to avoid import at module load during tests without system deps
        from weasyprint import HTML  # type: ignore

        pdf = HTML(string=html, base_url=request.build_absolute_uri("/")).write_pdf()
        resp = HttpResponse(pdf, content_type="application/pdf")
        resp["Content-Disposition"] = f"attachment; filename=trip_{trip.id}_styled_log.pdf"
        return resp

    def _get_graph_for_date(self, request, data: dict, target_date) -> str | None:
        """Get graph image URL for a specific date from request data."""
        if not target_date:
            return None

        target_date_str = target_date.isoformat()

        # Try GET parameters first
        if "graph_svg" in request.GET:
            return request.GET["graph_svg"]
        elif "graph_png" in request.GET:
            return request.GET["graph_png"]

        # Try POST data with date matching
        if "graphs" in data and isinstance(data["graphs"], list):
            # Debug: print what we're looking for vs what we have
            if settings.DEBUG:
                logger.debug("Looking for date: %s", target_date_str)
            for i, graph_entry in enumerate(data["graphs"]):
                if isinstance(graph_entry, dict):
                    entry_day = str(graph_entry.get("day", ""))
                    if settings.DEBUG:
                        logger.debug(
                            "Graph %d: day='%s', has_png=%s",
                            i,
                            entry_day,
                            bool(graph_entry.get("png")),
                        )
                    if entry_day == target_date_str:
                        result = graph_entry.get("svg") or graph_entry.get("png")
                        if settings.DEBUG:
                            logger.debug(
                                "Found matching graph for %s: %s", target_date_str, bool(result)
                            )
                        return result

            # Fallback to first graph if no date match
            if data["graphs"]:
                first_graph = data["graphs"][0]
                if isinstance(first_graph, dict):
                    result = first_graph.get("svg") or first_graph.get("png")
                    if settings.DEBUG:
                        logger.debug("Using first graph as fallback: %s", bool(result))
                    return result

        return None

    def _format_location(self, location_str: str | None) -> str:
        """Convert GPS coordinates to City, State format for FMCSA compliance."""
        if not location_str:
            return "N/A"

        # If it looks like coordinates (contains comma and numbers), convert to city/state
        if "," in location_str and any(c.isdigit() or c == "." or c == "-" for c in location_str):
            try:
                # This is a simplified conversion - in production you'd use a geocoding service
                # For now, return a placeholder that indicates coordinates were provided
                coords = location_str.strip()
                return f"Location ({coords})"  # Placeholder - should be geocoded to "City, ST"
            except Exception:
                return location_str

        # If it's already in city/state format, return as-is
        return location_str

    def _format_home_terminal_time(self, time_zone: str | None) -> str:
        """Format time zone for FMCSA compliance."""
        if not time_zone:
            return "N/A"

        # Convert UTC offset to readable time zone name
        time_zone_map = {
            "UTC-05:00": "Eastern (UTC−05:00)",
            "UTC-06:00": "Central (UTC−06:00)",
            "UTC-07:00": "Mountain (UTC−07:00)",
            "UTC-08:00": "Pacific (UTC−08:00)",
            "UTC-09:00": "Alaska (UTC−09:00)",
            "UTC-10:00": "Hawaii (UTC−10:00)",
        }

        return f"Home terminal time: {time_zone_map.get(time_zone, time_zone)}"

    def get(self, request, *args, **kwargs):  # type: ignore[override]
        trip_id = kwargs.get("trip_id")
        try:
            trip = Trip.objects.get(id=trip_id, owner=request.user)
        except Trip.DoesNotExist:
            return Response({"detail": "Trip not found"}, status=status.HTTP_404_NOT_FOUND)
        # Always use HTML template-based PDF
        return self._render_html_pdf(request, trip)

    def post(self, request, *args, **kwargs):  # type: ignore[override]
        trip_id = kwargs.get("trip_id")
        try:
            trip = Trip.objects.get(id=trip_id, owner=request.user)
        except Trip.DoesNotExist:
            return Response({"detail": "Trip not found"}, status=status.HTTP_404_NOT_FOUND)
        # Always use HTML template-based PDF; image data will be picked up inside _render_html_pdf
        return self._render_html_pdf(request, trip)


class TripReportCSVView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, *args, **kwargs):  # type: ignore[override]
        trip_id = kwargs.get("trip_id")
        try:
            trip = Trip.objects.get(id=trip_id, owner=request.user)
        except Trip.DoesNotExist:
            return Response({"detail": "Trip not found"}, status=status.HTTP_404_NOT_FOUND)

        profile, _ = DriverProfile.objects.get_or_create(driver=request.user)

        lines: list[str] = []
        # Header row for combined fields
        lines.append("section,field,value")
        header_map = {
            "driver_name": request.user.name,
            "driver_initials": profile.driver_initials,
            "driver_license_no": request.user.license_no,
            "driver_license_state": profile.license_state,
            "carrier": profile.carrier,
            "time_zone": profile.time_zone,
            "units": profile.units,
            "home_center_city": profile.home_center_city,
            "home_center_state": profile.home_center_state,
            "co_driver_name": trip.co_driver_name,
            "tractor_number": trip.tractor_number,
            "trailer_numbers": trip.trailer_numbers or trip.other_trailers,
            "shipper_name": trip.shipper_name,
            "commodity_description": trip.commodity_description,
            "load_id": trip.load_id,
            "log_date": trip.log_date.isoformat() if trip.log_date else "",
        }
        for k, v in header_map.items():
            lines.append(",".join(["header", k, str(v or "")]))

        # ELD daily totals
        lines.append("eld,day,off_h,sb_h,dr_h,on_h")
        logs = LogEvent.objects.filter(trip=trip, driver=request.user).order_by("timestamp")
        entries_by_day: dict[str, list[LogEntry]] = {}
        for ev in logs:
            d = ev.day.isoformat()
            entries_by_day.setdefault(d, []).append(
                LogEntry(timestamp=ev.timestamp, status=ev.status)
            )
        for day in sorted(entries_by_day.keys()):
            totals = calculate_daily_totals(entries_by_day[day], day)
            lines.append(
                ",".join(
                    [
                        "eld",
                        day,
                        f"{totals.off_hours}",
                        f"{totals.sleeper_hours}",
                        f"{totals.driving_hours}",
                        f"{totals.on_duty_hours}",
                    ]
                )
            )

        # Logs
        lines.append("type,day,timestamp,status,city,state,activity")
        for ev in LogEvent.objects.filter(trip=trip, driver=request.user).order_by("timestamp"):
            lines.append(
                ",".join(
                    [
                        "log",
                        ev.day.isoformat(),
                        ev.timestamp.isoformat(),
                        ev.status,
                        (ev.city or "").replace(",", " "),
                        (ev.state or "").replace(",", " "),
                        (ev.activity or "").replace(",", " "),
                    ]
                )
            )
        lines.append(
            "type,kind,performed_at,defects_count,signature_driver,signature_mechanic,notes,defects"
        )
        for insp in Inspection.objects.filter(trip=trip, driver=request.user).order_by(
            "-performed_at"
        ):
            defects = insp.defects or []
            defects_text = "; ".join(
                [
                    f"{d.get('item', '')}: {d.get('severity', '')} {d.get('note', '')}".strip()
                    for d in defects
                ]
            )
            lines.append(
                ",".join(
                    [
                        "inspection",
                        insp.kind,
                        insp.performed_at.isoformat(),
                        str(len(defects)),
                        insp.signature_driver.replace(",", " "),
                        (insp.signature_mechanic or "").replace(",", " "),
                        (insp.notes or "").replace(",", " "),
                        defects_text.replace(",", " "),
                    ]
                )
            )
        data = "\n".join(lines)
        resp = HttpResponse(data, content_type="text/csv")
        resp["Content-Disposition"] = f"attachment; filename=trip_{trip_id}_report.csv"
        return resp
