from __future__ import annotations

from datetime import date
import os
from pathlib import Path
import re
import shutil
from typing import Any
from uuid import uuid4

from driver_log_renderer import generate_driver_log, list_dynamic_fields
from hos_compliance import HOSCycle, HOSRecapInput, apply_hos_compliance
from persistence import (
    DriverProfileRecord,
    UserRecord,
    create_daily_log,
    create_trip_run,
)
from timeline_renderer import (
    DutyStatus,
    TimelineEvent,
    TimelinePoint,
    detect_template_scale,
    render_timeline,
)
from trip_planner import TripPlannerError, plan_trip


ROOT_DIR = Path(__file__).resolve().parents[2]
ARTIFACTS_DIR = ROOT_DIR / "artifacts"
REPORTS_DIR = ARTIFACTS_DIR / "reports"
LATEST_DIR = ARTIFACTS_DIR / "latest"
PDF_PATH = LATEST_DIR / "driver-log.pdf"
TEMPLATE_CANDIDATES = (
    "assets/templates/driver-log-template.svg",
    "assets/templates/driver-logbook.svg",
    "driver-log-template.svg",
    "driver-logbook.svg",
)
DB_PATH = Path(
    os.getenv(
        "DRIVER_LOG_DB_PATH",
        str(ROOT_DIR / "apps" / "api" / "data" / "driver_log.db"),
    )
).expanduser().resolve()

ONBOARDING_TEMPLATE_FIELD_MAP = {
    "carrier_name": "name-of-carrier",
    "main_office_address": "main-office-address",
    "home_terminal_address": "home-terminal-address",
    "truck_trailer_numbers": "truck-trailer-numbers",
}

US_STATE_ABBREVIATIONS = {
    "alabama": "AL",
    "alaska": "AK",
    "arizona": "AZ",
    "arkansas": "AR",
    "california": "CA",
    "colorado": "CO",
    "connecticut": "CT",
    "delaware": "DE",
    "district of columbia": "DC",
    "florida": "FL",
    "georgia": "GA",
    "hawaii": "HI",
    "idaho": "ID",
    "illinois": "IL",
    "indiana": "IN",
    "iowa": "IA",
    "kansas": "KS",
    "kentucky": "KY",
    "louisiana": "LA",
    "maine": "ME",
    "maryland": "MD",
    "massachusetts": "MA",
    "michigan": "MI",
    "minnesota": "MN",
    "mississippi": "MS",
    "missouri": "MO",
    "montana": "MT",
    "nebraska": "NE",
    "nevada": "NV",
    "new hampshire": "NH",
    "new jersey": "NJ",
    "new mexico": "NM",
    "new york": "NY",
    "north carolina": "NC",
    "north dakota": "ND",
    "ohio": "OH",
    "oklahoma": "OK",
    "oregon": "OR",
    "pennsylvania": "PA",
    "rhode island": "RI",
    "south carolina": "SC",
    "south dakota": "SD",
    "tennessee": "TN",
    "texas": "TX",
    "utah": "UT",
    "vermont": "VT",
    "virginia": "VA",
    "washington": "WA",
    "west virginia": "WV",
    "wisconsin": "WI",
    "wyoming": "WY",
}

ADDRESS_ABBREVIATIONS = (
    (r"\bstreet\b", "St"),
    (r"\broad\b", "Rd"),
    (r"\bavenue\b", "Ave"),
    (r"\bboulevard\b", "Blvd"),
    (r"\bdrive\b", "Dr"),
    (r"\blane\b", "Ln"),
    (r"\bhighway\b", "Hwy"),
    (r"\bparkway\b", "Pkwy"),
    (r"\bplace\b", "Pl"),
    (r"\bterrace\b", "Ter"),
    (r"\bsuite\b", "Ste"),
    (r"\bapartment\b", "Apt"),
    (r"\bnorth\b", "N"),
    (r"\bsouth\b", "S"),
    (r"\beast\b", "E"),
    (r"\bwest\b", "W"),
)


class ServiceValidationError(ValueError):
    """Raised when request payload validation fails."""


def _slugify_filename_part(value: str, *, fallback: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", value.strip().lower())
    normalized = normalized.strip("-")
    return normalized[:28] or fallback


def _build_log_export_basename(
    *,
    log_date: str,
    day_index: int,
    total_days: int,
    from_value: str,
    to_value: str,
    suffix: str,
) -> str:
    from_slug = _slugify_filename_part(from_value, fallback="origin")
    to_slug = _slugify_filename_part(to_value, fallback="destination")
    return f"driver-log_{log_date}_day-{day_index:02d}-of-{total_days:02d}_{from_slug}_to_{to_slug}_{suffix}"


def _normalize_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", str(value).strip())


def _truncate_text(value: str, max_length: int) -> str:
    clean_value = _normalize_whitespace(value)
    if len(clean_value) <= max_length:
        return clean_value
    if max_length <= 3:
        return clean_value[:max_length]
    return clean_value[: max_length - 3].rstrip(" ,;-") + "..."


def _maybe_state_abbreviation(value: str) -> str | None:
    normalized = _normalize_whitespace(value).lower()
    normalized = re.sub(r"\b\d{5}(?:-\d{4})?\b", "", normalized).strip(" ,")
    if normalized in US_STATE_ABBREVIATIONS:
        return US_STATE_ABBREVIATIONS[normalized]
    if normalized.upper() in set(US_STATE_ABBREVIATIONS.values()):
        return normalized.upper()
    return None


def _compact_location_for_log(value: str, *, max_length: int) -> str:
    clean_value = _normalize_whitespace(value)
    if not clean_value or clean_value.upper() == "EN ROUTE":
        return clean_value

    parts = [part.strip() for part in clean_value.split(",") if part.strip()]
    if not parts:
        return _truncate_text(clean_value, max_length)

    filtered_parts: list[str] = []
    state_code: str | None = None

    for part in parts:
        lower_part = part.lower()
        if lower_part in {"united states", "united states of america", "usa"}:
            continue
        if any(token in lower_part for token in (" county", " parish", " borough", " municipality", " census area")):
            continue
        maybe_state = _maybe_state_abbreviation(part)
        if maybe_state:
            state_code = maybe_state
            continue
        filtered_parts.append(part)

    city_or_origin = filtered_parts[0] if filtered_parts else parts[0]
    if state_code:
        return _truncate_text(f"{city_or_origin}, {state_code}", max_length)
    if len(filtered_parts) >= 2:
        return _truncate_text(f"{filtered_parts[0]}, {filtered_parts[1]}", max_length)
    return _truncate_text(city_or_origin, max_length)


def _compact_address_for_log(value: str, *, max_length: int) -> str:
    compacted = _normalize_whitespace(value)
    compacted = re.sub(
        r",?\s*(United States|United States of America|USA)\s*$",
        "",
        compacted,
        flags=re.IGNORECASE,
    )
    for pattern, replacement in ADDRESS_ABBREVIATIONS:
        compacted = re.sub(pattern, replacement, compacted, flags=re.IGNORECASE)
    return _truncate_text(compacted, max_length)


def _render_field_value_for_template(field_id: str, value: str) -> str:
    if field_id in {"from", "to"}:
        return _compact_location_for_log(value, max_length=34)
    if field_id in {"main-office-address", "home-terminal-address"}:
        return _compact_address_for_log(value, max_length=44)
    if field_id == "shipper-commodity":
        return _truncate_text(value, 42)
    if field_id == "dvl-or-manifest-number":
        return _truncate_text(value, 24)
    if field_id == "name-of-carrier":
        return _truncate_text(value, 34)
    if field_id == "truck-trailer-numbers":
        return _truncate_text(value, 28)
    return _normalize_whitespace(value)


def _render_template_values(values: dict[str, str]) -> dict[str, str]:
    rendered: dict[str, str] = {}
    for key, value in values.items():
        rendered[key] = _render_field_value_for_template(key, str(value))
    return rendered


def ensure_storage() -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    LATEST_DIR.mkdir(parents=True, exist_ok=True)


def resolve_template_path() -> Path:
    explicit_template = os.getenv("DRIVER_LOG_TEMPLATE")
    if explicit_template:
        return Path(explicit_template).expanduser().resolve()

    for relative_path in TEMPLATE_CANDIDATES:
        candidate = ROOT_DIR / relative_path
        if candidate.exists():
            return candidate

    return ROOT_DIR / "assets" / "templates" / "driver-log-template.svg"


def serialize_user(user: UserRecord) -> dict[str, object]:
    return {
        "id": user.id,
        "organization_id": user.organization_id,
        "email": user.email,
        "full_name": user.full_name,
        "role": user.role,
        "is_active": user.is_active,
        "created_at": user.created_at,
    }


def serialize_driver_profile(profile: DriverProfileRecord | None) -> dict[str, object]:
    if profile is None:
        return {
            "carrier_name": "",
            "main_office_address": "",
            "home_terminal_address": "",
            "truck_trailer_numbers": "",
            "cycle_rule": "70",
            "is_onboarding_complete": False,
            "locked_fields": list(ONBOARDING_TEMPLATE_FIELD_MAP.keys()),
        }

    return {
        "carrier_name": profile.carrier_name,
        "main_office_address": profile.main_office_address,
        "home_terminal_address": profile.home_terminal_address,
        "truck_trailer_numbers": profile.truck_trailer_numbers,
        "cycle_rule": profile.cycle_rule,
        "is_onboarding_complete": profile.is_onboarding_complete,
        "locked_fields": list(ONBOARDING_TEMPLATE_FIELD_MAP.keys()),
        "created_at": profile.created_at,
        "updated_at": profile.updated_at,
    }


def profile_template_values(profile: DriverProfileRecord) -> dict[str, str]:
    return {
        "name-of-carrier": _render_field_value_for_template("name-of-carrier", profile.carrier_name),
        "main-office-address": _render_field_value_for_template("main-office-address", profile.main_office_address),
        "home-terminal-address": _render_field_value_for_template(
            "home-terminal-address",
            profile.home_terminal_address,
        ),
        "truck-trailer-numbers": _render_field_value_for_template(
            "truck-trailer-numbers",
            profile.truck_trailer_numbers,
        ),
    }


def require_text(
    payload: dict[str, Any],
    key: str,
    *,
    label: str,
    min_length: int = 1,
    max_length: int = 240,
) -> str:
    value = str(payload.get(key, "")).strip()
    if len(value) < min_length:
        raise ServiceValidationError(f"{label} is required.")
    if len(value) > max_length:
        raise ServiceValidationError(f"{label} must be at most {max_length} characters.")
    return value


def require_email(payload: dict[str, Any], key: str = "email") -> str:
    value = str(payload.get(key, "")).strip().lower()
    if "@" not in value or "." not in value:
        raise ServiceValidationError("A valid email is required.")
    return value


def require_password(payload: dict[str, Any], key: str = "password") -> str:
    value = str(payload.get(key, ""))
    if len(value) < 8:
        raise ServiceValidationError("Password must be at least 8 characters.")
    if len(value) > 128:
        raise ServiceValidationError("Password must be at most 128 characters.")
    return value


def parse_trip_payload(payload: dict[str, Any], cycle_rule: str) -> dict[str, object]:
    current_location = require_text(
        payload,
        "current_location",
        label="Current location",
        min_length=2,
    )
    pickup_location = require_text(
        payload,
        "pickup_location",
        label="Pickup location",
        min_length=2,
    )
    dropoff_location = require_text(
        payload,
        "dropoff_location",
        label="Dropoff location",
        min_length=2,
    )

    try:
        current_cycle_used_hours = float(str(payload.get("current_cycle_used_hours", "0")).strip())
    except ValueError as exc:
        raise ServiceValidationError("Current cycle used hours must be a number.") from exc

    cycle_cap_hours = 60.0 if cycle_rule == "60" else 70.0
    if current_cycle_used_hours < 0 or current_cycle_used_hours > cycle_cap_hours:
        raise ServiceValidationError(
            f"Current cycle used hours must be between 0 and {int(cycle_cap_hours)}."
        )

    start_date_raw = str(payload.get("start_date", "")).strip()
    if not start_date_raw:
        trip_start_date = date.today()
    else:
        try:
            trip_start_date = date.fromisoformat(start_date_raw)
        except ValueError as exc:
            raise ServiceValidationError("Trip start date must use YYYY-MM-DD.") from exc

    return {
        "current_location": current_location,
        "pickup_location": pickup_location,
        "dropoff_location": dropoff_location,
        "current_cycle_used_hours": round(current_cycle_used_hours, 2),
        "cycle": cycle_rule,
        "start_date": trip_start_date,
    }


def format_hours_value(value: float) -> str:
    rounded = round(float(value), 2)
    if float(rounded).is_integer():
        return str(int(rounded))
    return str(rounded)


def timeline_events_from_dicts(events: list[dict[str, object]]) -> list[TimelineEvent]:
    converted: list[TimelineEvent] = []
    for event in events:
        start_data = event["start"]
        end_data = event.get("end")

        start = TimelinePoint(
            h=int(start_data["h"]),  # type: ignore[index]
            m=int(start_data["m"]),  # type: ignore[index]
        )
        end = None
        if end_data is not None:
            end = TimelinePoint(
                h=int(end_data["h"]),  # type: ignore[index]
                m=int(end_data["m"]),  # type: ignore[index]
            )

        converted.append(
            TimelineEvent(
                start=start,
                end=end,
                duty=DutyStatus(str(event["duty"])),
            )
        )
    return converted


def plan_trip_from_payload(
    payload: dict[str, Any],
    *,
    cycle_rule: str,
) -> dict[str, Any]:
    trip_input = parse_trip_payload(payload, cycle_rule)
    plan = plan_trip(
        current_location=str(trip_input["current_location"]),
        pickup_location=str(trip_input["pickup_location"]),
        dropoff_location=str(trip_input["dropoff_location"]),
        current_cycle_used_hours=float(trip_input["current_cycle_used_hours"]),
        cycle=str(trip_input["cycle"]),
        start_date=trip_input["start_date"],  # type: ignore[arg-type]
    )
    return plan.to_dict()


def generate_trip_from_payload(
    payload: dict[str, Any],
    *,
    current_user: UserRecord,
    profile: DriverProfileRecord,
    save_record: bool = True,
) -> dict[str, object]:
    if not profile.is_onboarding_complete:
        raise ServiceValidationError("Complete onboarding before generating trip logs.")

    ensure_storage()
    template_path = resolve_template_path()
    template_fields = list_dynamic_fields(template_path)
    field_ids = [field["id"] for field in template_fields]
    scale = detect_template_scale(template_path)

    trip_input = parse_trip_payload(payload, profile.cycle_rule)
    plan = plan_trip(
        current_location=str(trip_input["current_location"]),
        pickup_location=str(trip_input["pickup_location"]),
        dropoff_location=str(trip_input["dropoff_location"]),
        current_cycle_used_hours=float(trip_input["current_cycle_used_hours"]),
        cycle=str(trip_input["cycle"]),
        start_date=trip_input["start_date"],  # type: ignore[arg-type]
    )
    plan_dict = plan.to_dict()

    trip_run_id: str | None = None
    if save_record:
        trip_start = plan.daily_logs[0].log_date if plan.daily_logs else trip_input["start_date"].isoformat()
        trip_end = plan.daily_logs[-1].log_date if plan.daily_logs else trip_start
        trip_run = create_trip_run(
            db_path=DB_PATH,
            organization_id=current_user.organization_id,
            driver_user_id=current_user.id,
            created_by_user_id=current_user.id,
            cycle=profile.cycle_rule,
            current_location=str(trip_input["current_location"]),
            pickup_location=str(trip_input["pickup_location"]),
            dropoff_location=str(trip_input["dropoff_location"]),
            current_cycle_used_hours=float(trip_input["current_cycle_used_hours"]),
            start_date=trip_start,
            end_date=trip_end,
            plan=plan_dict,
        )
        trip_run_id = str(trip_run["id"])

    base_values = {field["id"]: field["value"] for field in template_fields}
    for key, value in profile_template_values(profile).items():
        if key in base_values:
            base_values[key] = str(value)

    previous_on_duty_history = [float(trip_input["current_cycle_used_hours"]), 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
    generated_logs: list[dict[str, object]] = []
    latest_pdf_path: Path | None = None
    restart_streak_hours = 0.0
    total_days = len(plan.daily_logs)
    cumulative_miles = 0.0

    for index, day in enumerate(plan.daily_logs):
        day_values = dict(base_values)
        cumulative_miles += day.miles_driven

        day_date = date.fromisoformat(day.log_date)
        from_value = plan.locations["current"]["label"] if index == 0 else "EN ROUTE"
        if index == total_days - 1:
            to_value = plan.locations["dropoff"]["label"]
        elif index == 0:
            to_value = plan.locations["pickup"]["label"]
        else:
            to_value = "EN ROUTE"

        if "from" in day_values:
            day_values["from"] = _render_field_value_for_template("from", str(from_value))
        if "to" in day_values:
            day_values["to"] = _render_field_value_for_template("to", str(to_value))
        if "off-duty-hours" in day_values:
            day_values["off-duty-hours"] = format_hours_value(day.off_duty_hours)
        if "sleeper-berth-hours" in day_values:
            day_values["sleeper-berth-hours"] = format_hours_value(day.sleeper_berth_hours)
        if "driving-hours" in day_values:
            day_values["driving-hours"] = format_hours_value(day.driving_hours)
        if "on-duty-hours" in day_values:
            day_values["on-duty-hours"] = format_hours_value(day.on_duty_hours)
        if "total-miles-driving-today" in day_values:
            day_values["total-miles-driving-today"] = str(int(round(day.miles_driven)))
        if "total-mileage-today" in day_values:
            day_values["total-mileage-today"] = str(int(round(cumulative_miles)))
        if "log-date-year" in day_values:
            day_values["log-date-year"] = f"{day_date.year % 100:02d}"
        if "log-date-month" in day_values:
            day_values["log-date-month"] = f"{day_date.month:02d}"
        if "log-date-day" in day_values:
            day_values["log-date-day"] = f"{day_date.day:02d}"
        if "shipper-commodity" in day_values and not str(day_values["shipper-commodity"]).strip():
            commodity_value = (
                f"{_compact_location_for_log(plan.locations['pickup']['label'], max_length=18)} -> "
                f"{_compact_location_for_log(plan.locations['dropoff']['label'], max_length=18)}"
            )
            day_values["shipper-commodity"] = _render_field_value_for_template(
                "shipper-commodity",
                commodity_value,
            )
        if "dvl-or-manifest-number" in day_values and not str(day_values["dvl-or-manifest-number"]).strip():
            manifest_value = f"DL-{day_date.strftime('%Y%m%d')}-D{index + 1:02d}"
            day_values["dvl-or-manifest-number"] = _render_field_value_for_template(
                "dvl-or-manifest-number",
                manifest_value,
            )

        if day.off_duty_hours >= 24.0 and day.on_duty_hours <= 0.0:
            restart_streak_hours += 24.0
        else:
            restart_streak_hours = 0.0

        compliance = apply_hos_compliance(
            values=day_values,
            recap_input=HOSRecapInput(
                cycle=HOSCycle(profile.cycle_rule),
                previous_on_duty_hours=tuple(previous_on_duty_history[:7]),
                longest_off_duty_streak_hours=restart_streak_hours,
            ),
            available_field_ids=field_ids,
        )
        compliance_dict = compliance.to_dict()
        day_values.update(compliance.computed_values)
        day_values = _render_template_values(day_values)

        timeline_svg = render_timeline(
            timeline_events_from_dicts(day.timeline_events),
            scale=scale,
        )

        artifact_suffix = uuid4().hex[:8]
        artifact_basename = _build_log_export_basename(
            log_date=day.log_date,
            day_index=index + 1,
            total_days=total_days,
            from_value=str(from_value),
            to_value=str(to_value),
            suffix=artifact_suffix,
        )
        output_svg_path = REPORTS_DIR / f"{artifact_basename}.svg"
        output_pdf_path = REPORTS_DIR / f"{artifact_basename}.pdf"
        generate_driver_log(
            template_path=template_path,
            output_svg_path=output_svg_path,
            output_pdf_path=output_pdf_path,
            values=day_values,
            timeline_svg=timeline_svg,
        )

        latest_pdf_path = output_pdf_path

        record = None
        if save_record:
            record = create_daily_log(
                db_path=DB_PATH,
                organization_id=current_user.organization_id,
                driver_user_id=current_user.id,
                created_by_user_id=current_user.id,
                trip_run_id=trip_run_id,
                log_date=day.log_date,
                cycle=profile.cycle_rule,
                values=day_values,
                recap={
                    "cycle": profile.cycle_rule,
                    "current_cycle_used_hours": trip_input["current_cycle_used_hours"],
                    "previous_on_duty_hours": previous_on_duty_history[:7],
                },
                compliance=compliance_dict,
                timeline_events=day.timeline_events,
                svg_path=str(output_svg_path),
                pdf_path=str(output_pdf_path),
            )

        pdf_url = f"/api/logs/{record['id']}/pdf/{output_pdf_path.name}" if record else str(output_pdf_path)
        generated_logs.append(
            {
                "index": index + 1,
                "log_date": day.log_date,
                "miles_driven": day.miles_driven,
                "driving_hours": day.driving_hours,
                "on_duty_hours": day.on_duty_hours,
                "off_duty_hours": day.off_duty_hours,
                "is_legal_today": compliance_dict["is_legal_today"],
                "is_legal_tomorrow": compliance_dict["is_legal_tomorrow"],
                "available_hours_tomorrow": compliance_dict["available_hours_tomorrow"],
                "violations": compliance_dict["violations"],
                "record_id": record["id"] if record else None,
                "trip_run_id": trip_run_id,
                "pdf_url": pdf_url,
                "pdf_filename": output_pdf_path.name,
            }
        )

        try:
            output_svg_path.unlink(missing_ok=True)
        except OSError:
            pass

        previous_on_duty_history = [float(compliance_dict["today_on_duty_hours"]), *previous_on_duty_history[:6]]

    if latest_pdf_path:
        shutil.copyfile(latest_pdf_path, PDF_PATH)

    return {
        "plan": plan_dict,
        "generated_logs": generated_logs,
        "count": len(generated_logs),
        "trip_run_id": trip_run_id,
        "latest_pdf": generated_logs[-1]["pdf_url"] if generated_logs else None,
    }
