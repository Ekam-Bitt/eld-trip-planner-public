from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, timedelta
import json
import math
import re
from typing import Any, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import quote_plus
from urllib.request import Request, urlopen


MILES_PER_METER = 0.000621371
SECONDS_PER_HOUR = 3600.0
MINUTES_PER_HOUR = 60
MINUTES_PER_DAY = 24 * MINUTES_PER_HOUR

FUEL_INTERVAL_MILES = 1000.0
FUEL_STOP_HOURS = 0.5
PICKUP_DROP_HOURS = 1.0
PRETRIP_HOURS = 0.5
MAX_DRIVING_HOURS_PER_DAY = 11.0
MAX_ON_DUTY_HOURS_PER_DAY = 14.0
DEFAULT_AVG_SPEED_MPH = 50.0

COORDINATE_INPUT = re.compile(
    r"^\s*(?P<lat>[-+]?\d{1,2}(?:\.\d+)?)\s*,\s*(?P<lon>[-+]?\d{1,3}(?:\.\d+)?)\s*$"
)


class TripPlannerError(RuntimeError):
    """Raised when planning cannot continue due to invalid input or API failures."""


@dataclass(frozen=True)
class LocationPoint:
    label: str
    lat: float
    lon: float


@dataclass(frozen=True)
class RouteLeg:
    index: int
    from_location: str
    to_location: str
    distance_miles: float
    duration_hours: float
    instructions: list[str]


@dataclass(frozen=True)
class PlannedDay:
    index: int
    log_date: str
    miles_driven: float
    off_duty_hours: float
    sleeper_berth_hours: float
    driving_hours: float
    on_duty_hours: float
    total_hours: float
    timeline_events: list[dict[str, Any]]
    notes: list[str]


@dataclass(frozen=True)
class TripPlanResult:
    cycle: str
    cycle_cap_hours: float
    current_cycle_used_hours: float
    assumptions: dict[str, Any]
    locations: dict[str, dict[str, Any]]
    route: dict[str, Any]
    stops: list[dict[str, Any]]
    daily_logs: list[PlannedDay]

    def to_dict(self) -> dict[str, Any]:
        return {
            "cycle": self.cycle,
            "cycle_cap_hours": self.cycle_cap_hours,
            "current_cycle_used_hours": self.current_cycle_used_hours,
            "assumptions": self.assumptions,
            "locations": self.locations,
            "route": self.route,
            "stops": self.stops,
            "daily_logs": [asdict(day) for day in self.daily_logs],
            "days_count": len(self.daily_logs),
        }


@dataclass
class _Task:
    kind: str  # "drive" | "on"
    remaining_minutes: int
    remaining_miles: float
    note: str
    location: str


def _round_hours(minutes: int) -> float:
    return round(minutes / MINUTES_PER_HOUR, 2)


def _to_clock(total_minutes: int) -> dict[str, int]:
    normalized = max(0, min(MINUTES_PER_DAY, total_minutes))
    if normalized == MINUTES_PER_DAY:
        normalized = MINUTES_PER_DAY - 1
    return {
        "h": normalized // MINUTES_PER_HOUR,
        "m": normalized % MINUTES_PER_HOUR,
    }


def _haversine_miles(a_lat: float, a_lon: float, b_lat: float, b_lon: float) -> float:
    radius_miles = 3958.7613
    lat1 = math.radians(a_lat)
    lat2 = math.radians(b_lat)
    d_lat = math.radians(b_lat - a_lat)
    d_lon = math.radians(b_lon - a_lon)

    sin_d_lat = math.sin(d_lat / 2.0)
    sin_d_lon = math.sin(d_lon / 2.0)
    chord = sin_d_lat * sin_d_lat + math.cos(lat1) * math.cos(lat2) * sin_d_lon * sin_d_lon
    arc = 2.0 * math.atan2(math.sqrt(chord), math.sqrt(max(0.0, 1.0 - chord)))
    return radius_miles * arc


def _http_json(url: str, timeout_seconds: int = 12) -> Any:
    request = Request(
        url=url,
        headers={
            "User-Agent": "eld-adv-trip-planner/1.0",
            "Accept": "application/json",
        },
    )
    with urlopen(request, timeout=timeout_seconds) as response:  # nosec B310 - controlled URLs.
        payload = response.read().decode("utf-8")
    return json.loads(payload)


def _parse_coordinate_input(raw_location: str) -> LocationPoint | None:
    match = COORDINATE_INPUT.match(raw_location)
    if match is None:
        return None

    lat = float(match.group("lat"))
    lon = float(match.group("lon"))
    if lat < -90 or lat > 90 or lon < -180 or lon > 180:
        raise TripPlannerError(f"Invalid coordinate input '{raw_location}'.")

    return LocationPoint(label=raw_location.strip(), lat=lat, lon=lon)


def _geocode_location(raw_location: str) -> LocationPoint:
    parsed = _parse_coordinate_input(raw_location)
    if parsed is not None:
        return parsed

    query = quote_plus(raw_location.strip())
    url = f"https://nominatim.openstreetmap.org/search?format=jsonv2&limit=1&q={query}"

    try:
        data = _http_json(url)
    except HTTPError as exc:
        raise TripPlannerError(
            f"Geocoding failed for '{raw_location}' with HTTP {exc.code}. "
            "If this persists, provide coordinates as 'lat,lon'."
        ) from exc
    except URLError as exc:
        raise TripPlannerError(
            f"Geocoding service was unreachable for '{raw_location}'. "
            "Use coordinates as 'lat,lon' or retry."
        ) from exc
    except Exception as exc:
        raise TripPlannerError(f"Failed to geocode '{raw_location}'.") from exc

    if not isinstance(data, list) or len(data) == 0:
        raise TripPlannerError(f"No map match found for '{raw_location}'.")

    match = data[0]
    try:
        lat = float(match["lat"])
        lon = float(match["lon"])
    except (KeyError, TypeError, ValueError) as exc:
        raise TripPlannerError(f"Unexpected geocoder response for '{raw_location}'.") from exc

    label = str(match.get("display_name") or raw_location).strip()
    return LocationPoint(label=label, lat=lat, lon=lon)


def _format_osrm_instruction(step: dict[str, Any]) -> str:
    maneuver = step.get("maneuver", {}) if isinstance(step, dict) else {}
    maneuver_type = str(maneuver.get("type") or "continue")
    modifier = str(maneuver.get("modifier") or "").strip()
    road_name = str(step.get("name") or "").strip()
    distance_miles = round(float(step.get("distance", 0.0)) * MILES_PER_METER, 1)

    title = maneuver_type.replace("_", " ").title()
    if modifier:
        title = f"{title} {modifier}"

    if road_name:
        return f"{title} onto {road_name} for {distance_miles} mi"
    return f"{title} for {distance_miles} mi"


def _fallback_route(points: Sequence[LocationPoint]) -> tuple[list[RouteLeg], list[list[float]], float, float]:
    legs: list[RouteLeg] = []
    geometry: list[list[float]] = [[point.lat, point.lon] for point in points]
    total_distance_miles = 0.0
    total_duration_hours = 0.0

    for index in range(len(points) - 1):
        start = points[index]
        end = points[index + 1]
        distance_miles = _haversine_miles(start.lat, start.lon, end.lat, end.lon)
        duration_hours = distance_miles / DEFAULT_AVG_SPEED_MPH
        legs.append(
            RouteLeg(
                index=index + 1,
                from_location=start.label,
                to_location=end.label,
                distance_miles=round(distance_miles, 2),
                duration_hours=round(duration_hours, 2),
                instructions=[f"Drive from {start.label} to {end.label}."],
            )
        )
        total_distance_miles += distance_miles
        total_duration_hours += duration_hours

    return legs, geometry, total_distance_miles, total_duration_hours


def _route_via_osrm(points: Sequence[LocationPoint]) -> tuple[list[RouteLeg], list[list[float]], float, float]:
    if len(points) < 2:
        raise TripPlannerError("At least two locations are required for routing.")

    coordinates = ";".join([f"{point.lon:.6f},{point.lat:.6f}" for point in points])
    url = (
        "https://router.project-osrm.org/route/v1/driving/"
        f"{coordinates}?overview=full&geometries=geojson&steps=true"
    )

    try:
        data = _http_json(url)
        routes = data.get("routes") if isinstance(data, dict) else None
        if not isinstance(routes, list) or len(routes) == 0:
            raise TripPlannerError("No route returned by OSRM.")

        route = routes[0]
        route_geometry = route.get("geometry", {}).get("coordinates", [])
        geometry = []
        for raw in route_geometry:
            if not isinstance(raw, list) or len(raw) < 2:
                continue
            geometry.append([float(raw[1]), float(raw[0])])  # lat, lon

        legs_raw = route.get("legs", [])
        legs: list[RouteLeg] = []
        for index, leg_raw in enumerate(legs_raw):
            start = points[index]
            end = points[index + 1]
            steps_raw = leg_raw.get("steps", []) if isinstance(leg_raw, dict) else []
            instructions = []
            for step in steps_raw[:45]:
                if isinstance(step, dict):
                    instructions.append(_format_osrm_instruction(step))

            legs.append(
                RouteLeg(
                    index=index + 1,
                    from_location=start.label,
                    to_location=end.label,
                    distance_miles=round(float(leg_raw.get("distance", 0.0)) * MILES_PER_METER, 2),
                    duration_hours=round(float(leg_raw.get("duration", 0.0)) / SECONDS_PER_HOUR, 2),
                    instructions=instructions,
                )
            )

        total_distance_miles = float(route.get("distance", 0.0)) * MILES_PER_METER
        total_duration_hours = float(route.get("duration", 0.0)) / SECONDS_PER_HOUR
        return legs, geometry, total_distance_miles, total_duration_hours
    except Exception:
        return _fallback_route(points)


def _build_route_urls(points: Sequence[LocationPoint]) -> dict[str, str]:
    joined_route = ";".join([f"{point.lat:.6f},{point.lon:.6f}" for point in points])
    route_url = (
        "https://www.openstreetmap.org/directions?engine=fossgis_osrm_car&route="
        f"{quote_plus(joined_route)}"
    )
    return {"openstreetmap_directions_url": route_url}


def _expand_with_fuel_stops(initial_tasks: Sequence[_Task]) -> list[_Task]:
    expanded: list[_Task] = []
    miles_until_fuel = FUEL_INTERVAL_MILES

    def remaining_drive_miles(index: int) -> float:
        miles = 0.0
        for future in initial_tasks[index + 1 :]:
            if future.kind == "drive":
                miles += future.remaining_miles
        return miles

    for index, task in enumerate(initial_tasks):
        if task.kind != "drive":
            expanded.append(task)
            continue

        remaining_minutes = task.remaining_minutes
        remaining_miles = task.remaining_miles
        future_miles = remaining_drive_miles(index)

        while remaining_minutes > 0 and remaining_miles > 0:
            miles_chunk = min(remaining_miles, miles_until_fuel)
            chunk_ratio = miles_chunk / remaining_miles if remaining_miles > 0 else 1.0
            minutes_chunk = max(1, int(round(remaining_minutes * chunk_ratio)))
            minutes_chunk = min(minutes_chunk, remaining_minutes)

            expanded.append(
                _Task(
                    kind="drive",
                    remaining_minutes=minutes_chunk,
                    remaining_miles=round(miles_chunk, 3),
                    note=task.note,
                    location=task.location,
                )
            )

            remaining_minutes -= minutes_chunk
            remaining_miles = max(0.0, remaining_miles - miles_chunk)
            miles_until_fuel -= miles_chunk

            has_more_drive = remaining_miles > 0.05 or future_miles > 0.05
            if miles_until_fuel <= 0.01 and has_more_drive:
                expanded.append(
                    _Task(
                        kind="on",
                        remaining_minutes=int(round(FUEL_STOP_HOURS * MINUTES_PER_HOUR)),
                        remaining_miles=0.0,
                        note="Fuel stop",
                        location=task.location,
                    )
                )
                miles_until_fuel = FUEL_INTERVAL_MILES

    return expanded


def _append_block(blocks: list[dict[str, Any]], duty: str, minutes: int, miles: float = 0.0) -> None:
    if minutes <= 0:
        return
    if blocks and blocks[-1]["duty"] == duty:
        blocks[-1]["minutes"] += minutes
        blocks[-1]["miles"] += miles
        return
    blocks.append({"duty": duty, "minutes": minutes, "miles": miles})


def _timeline_from_blocks(blocks: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    cursor = 0

    for block in blocks:
        minutes = int(block["minutes"])
        if minutes <= 0:
            continue
        start_minutes = cursor
        end_minutes = min(MINUTES_PER_DAY, cursor + minutes)
        if end_minutes <= start_minutes:
            continue
        if end_minutes == MINUTES_PER_DAY:
            if start_minutes >= MINUTES_PER_DAY - 1:
                cursor = end_minutes
                continue
            end_minutes = MINUTES_PER_DAY - 1

        output.append(
            {
                "start": _to_clock(start_minutes),
                "end": _to_clock(end_minutes),
                "duty": str(block["duty"]),
            }
        )
        cursor = end_minutes

    if cursor < MINUTES_PER_DAY:
        end_minutes = MINUTES_PER_DAY - 1
        if cursor >= end_minutes:
            return output
        output.append(
            {
                "start": _to_clock(cursor),
                "end": _to_clock(end_minutes),
                "duty": "off",
            }
        )

    return output


def _stop_type_from_note(note: str) -> str:
    lowered = note.lower()
    if "pickup" in lowered:
        return "pickup"
    if "dropoff" in lowered:
        return "dropoff"
    if "fuel" in lowered:
        return "fuel"
    if "restart" in lowered:
        return "restart"
    return "stop"


def _build_daily_logs(
    tasks: list[_Task],
    start_date: date,
    cycle_cap_hours: float,
    current_cycle_used_hours: float,
) -> tuple[list[PlannedDay], list[dict[str, Any]]]:
    queue = [task for task in tasks if task.remaining_minutes > 0]
    days: list[PlannedDay] = []
    stops: list[dict[str, Any]] = []

    day_index = 0
    remaining_cycle_minutes = max(0, int(round((cycle_cap_hours - current_cycle_used_hours) * MINUTES_PER_HOUR)))
    restart_minutes = 0

    while queue:
        day_date = start_date + timedelta(days=day_index)

        if remaining_cycle_minutes <= 0:
            restart_minutes += MINUTES_PER_DAY
            days.append(
                PlannedDay(
                    index=day_index + 1,
                    log_date=day_date.isoformat(),
                    miles_driven=0.0,
                    off_duty_hours=24.0,
                    sleeper_berth_hours=0.0,
                    driving_hours=0.0,
                    on_duty_hours=0.0,
                    total_hours=24.0,
                    timeline_events=[
                        {
                            "start": {"h": 0, "m": 0},
                            "end": {"h": 23, "m": 59},
                            "duty": "off",
                        }
                    ],
                    notes=["34-hour restart in progress"],
                )
            )

            if restart_minutes >= int(round(34.0 * MINUTES_PER_HOUR)):
                remaining_cycle_minutes = int(round(cycle_cap_hours * MINUTES_PER_HOUR))
                restart_minutes = 0

            day_index += 1
            continue

        day_on_duty_budget = min(
            int(round(MAX_ON_DUTY_HOURS_PER_DAY * MINUTES_PER_HOUR)),
            remaining_cycle_minutes,
        )
        day_driving_budget = int(round(MAX_DRIVING_HOURS_PER_DAY * MINUTES_PER_HOUR))
        day_blocks: list[dict[str, Any]] = []
        day_notes: list[str] = []
        day_miles = 0.0
        day_cursor = 0

        _append_block(day_blocks, "off", 6 * MINUTES_PER_HOUR)
        day_cursor = 6 * MINUTES_PER_HOUR

        if queue:
            pretrip_minutes = min(int(round(PRETRIP_HOURS * MINUTES_PER_HOUR)), day_on_duty_budget)
            _append_block(day_blocks, "on", pretrip_minutes)
            day_on_duty_budget -= pretrip_minutes
            day_cursor += pretrip_minutes

        progress_made = False
        while queue and day_on_duty_budget > 0:
            task = queue[0]
            if task.kind == "drive":
                if day_driving_budget <= 0:
                    break
                alloc = min(task.remaining_minutes, day_on_duty_budget, day_driving_budget)
                if alloc <= 0:
                    break

                before_minutes = max(1, task.remaining_minutes)
                miles_chunk = task.remaining_miles * (alloc / before_minutes)
                if alloc >= task.remaining_minutes:
                    miles_chunk = task.remaining_miles

                _append_block(day_blocks, "driving", alloc, miles_chunk)
                day_miles += miles_chunk
                task.remaining_minutes -= alloc
                task.remaining_miles = max(0.0, task.remaining_miles - miles_chunk)
                day_on_duty_budget -= alloc
                day_driving_budget -= alloc
                day_cursor += alloc
                progress_made = True
            else:
                alloc = min(task.remaining_minutes, day_on_duty_budget)
                if alloc <= 0:
                    break

                _append_block(day_blocks, "on", alloc)
                task.remaining_minutes -= alloc
                day_on_duty_budget -= alloc
                day_cursor += alloc
                progress_made = True

            if task.remaining_minutes <= 0:
                if task.note:
                    day_notes.append(task.note)
                    stops.append(
                        {
                            "type": _stop_type_from_note(task.note),
                            "label": task.note,
                            "location": task.location,
                            "date": day_date.isoformat(),
                            "time": f"{day_cursor // MINUTES_PER_HOUR:02d}:{day_cursor % MINUTES_PER_HOUR:02d}",
                        }
                    )
                queue.pop(0)

        if not progress_made and queue:
            # Safety valve to prevent infinite loops from malformed tasks.
            raise TripPlannerError("Planner could not allocate remaining tasks within HOS limits.")

        used_minutes = sum(int(block["minutes"]) for block in day_blocks)
        if used_minutes < MINUTES_PER_DAY:
            _append_block(day_blocks, "off", MINUTES_PER_DAY - used_minutes)

        duty_minutes = {"off": 0, "sleeper": 0, "driving": 0, "on": 0}
        for block in day_blocks:
            duty = str(block["duty"])
            if duty in duty_minutes:
                duty_minutes[duty] += int(block["minutes"])

        on_duty_minutes = duty_minutes["driving"] + duty_minutes["on"]
        remaining_cycle_minutes = max(0, remaining_cycle_minutes - on_duty_minutes)

        days.append(
            PlannedDay(
                index=day_index + 1,
                log_date=day_date.isoformat(),
                miles_driven=round(day_miles, 2),
                off_duty_hours=_round_hours(duty_minutes["off"]),
                sleeper_berth_hours=_round_hours(duty_minutes["sleeper"]),
                driving_hours=_round_hours(duty_minutes["driving"]),
                on_duty_hours=_round_hours(duty_minutes["on"]),
                total_hours=24.0,
                timeline_events=_timeline_from_blocks(day_blocks),
                notes=day_notes,
            )
        )

        day_index += 1

    return days, stops


def _build_trip_tasks(legs: Sequence[RouteLeg]) -> list[_Task]:
    if len(legs) < 2:
        raise TripPlannerError("Trip planning requires current, pickup, and dropoff locations.")

    to_pickup = legs[0]
    to_dropoff = legs[1]

    tasks = [
        _Task(
            kind="drive",
            remaining_minutes=max(1, int(round(to_pickup.duration_hours * MINUTES_PER_HOUR))),
            remaining_miles=max(0.01, to_pickup.distance_miles),
            note=f"Drive to pickup: {to_pickup.to_location}",
            location=to_pickup.to_location,
        ),
        _Task(
            kind="on",
            remaining_minutes=int(round(PICKUP_DROP_HOURS * MINUTES_PER_HOUR)),
            remaining_miles=0.0,
            note="Pickup completed",
            location=to_pickup.to_location,
        ),
        _Task(
            kind="drive",
            remaining_minutes=max(1, int(round(to_dropoff.duration_hours * MINUTES_PER_HOUR))),
            remaining_miles=max(0.01, to_dropoff.distance_miles),
            note=f"Drive to dropoff: {to_dropoff.to_location}",
            location=to_dropoff.to_location,
        ),
        _Task(
            kind="on",
            remaining_minutes=int(round(PICKUP_DROP_HOURS * MINUTES_PER_HOUR)),
            remaining_miles=0.0,
            note="Dropoff completed",
            location=to_dropoff.to_location,
        ),
    ]
    return _expand_with_fuel_stops(tasks)


def plan_trip(
    *,
    current_location: str,
    pickup_location: str,
    dropoff_location: str,
    current_cycle_used_hours: float,
    cycle: str = "70",
    start_date: date | None = None,
) -> TripPlanResult:
    if cycle not in {"60", "70"}:
        raise TripPlannerError("cycle must be either '60' or '70'.")

    if current_cycle_used_hours < 0:
        raise TripPlannerError("current_cycle_used_hours cannot be negative.")

    cycle_cap_hours = 60.0 if cycle == "60" else 70.0
    if current_cycle_used_hours > cycle_cap_hours:
        raise TripPlannerError(
            f"current_cycle_used_hours cannot exceed cycle cap ({int(cycle_cap_hours)})."
        )

    planning_date = start_date or date.today()

    current = _geocode_location(current_location)
    pickup = _geocode_location(pickup_location)
    dropoff = _geocode_location(dropoff_location)
    waypoints = [current, pickup, dropoff]

    legs, geometry, total_distance_miles, total_duration_hours = _route_via_osrm(waypoints)
    if len(legs) < 2:
        raise TripPlannerError("Routing provider did not return the expected trip legs.")

    trip_tasks = _build_trip_tasks(legs)
    daily_logs, stops = _build_daily_logs(
        tasks=trip_tasks,
        start_date=planning_date,
        cycle_cap_hours=cycle_cap_hours,
        current_cycle_used_hours=current_cycle_used_hours,
    )

    route_urls = _build_route_urls(waypoints)
    assumptions = {
        "cycle_policy": f"{int(cycle_cap_hours)} hours / {'8' if cycle == '70' else '7'} days",
        "average_speed_mph": DEFAULT_AVG_SPEED_MPH,
        "fuel_every_miles": FUEL_INTERVAL_MILES,
        "pickup_duration_hours": PICKUP_DROP_HOURS,
        "dropoff_duration_hours": PICKUP_DROP_HOURS,
        "max_driving_hours_per_day": MAX_DRIVING_HOURS_PER_DAY,
        "max_on_duty_hours_per_day": MAX_ON_DUTY_HOURS_PER_DAY,
    }

    route_payload = {
        "total_distance_miles": round(total_distance_miles, 2),
        "total_driving_hours": round(total_duration_hours, 2),
        "geometry": geometry,
        "legs": [asdict(leg) for leg in legs],
        **route_urls,
    }

    locations_payload = {
        "current": asdict(current),
        "pickup": asdict(pickup),
        "dropoff": asdict(dropoff),
    }

    return TripPlanResult(
        cycle=cycle,
        cycle_cap_hours=cycle_cap_hours,
        current_cycle_used_hours=round(current_cycle_used_hours, 2),
        assumptions=assumptions,
        locations=locations_payload,
        route=route_payload,
        stops=stops,
        daily_logs=daily_logs,
    )
