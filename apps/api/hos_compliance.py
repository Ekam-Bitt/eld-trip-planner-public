from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Iterable, Mapping, Sequence


class HOSCycle(str, Enum):
    CYCLE_60 = "60"
    CYCLE_70 = "70"


@dataclass(frozen=True)
class HOSRecapInput:
    cycle: HOSCycle = HOSCycle.CYCLE_70
    previous_on_duty_hours: tuple[float, ...] = ()
    longest_off_duty_streak_hours: float = 0.0


@dataclass(frozen=True)
class HOSComputationResult:
    computed_values: dict[str, str]
    field_ids: dict[str, str | None]
    cycle: str
    cycle_cap_hours: float
    recap_a_hours: float
    recap_c_hours: float
    available_hours_tomorrow: float
    today_on_duty_hours: float
    restart_applied: bool
    is_legal_today: bool
    is_legal_tomorrow: bool
    violations: list[str]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _pick_field_id(
    available_ids: set[str],
    candidates: Sequence[str],
    used_ids: set[str] | None = None,
) -> str | None:
    for candidate in candidates:
        if candidate in available_ids and (used_ids is None or candidate not in used_ids):
            if used_ids is not None:
                used_ids.add(candidate)
            return candidate
    return None


def _parse_number(raw_value: str | int | float | None) -> float:
    try:
        return float(str(raw_value).strip())
    except (TypeError, ValueError):
        return 0.0


def _format_hours(value: float) -> str:
    rounded = round(value, 2)
    if rounded.is_integer():
        return str(int(rounded))
    return str(rounded)


def _window_sum(values: Sequence[float], size: int) -> float:
    return sum(values[:size])


def _normalize_previous_on_duty(values: Sequence[float], max_days: int = 7) -> list[float]:
    normalized: list[float] = []

    for raw in values[:max_days]:
        normalized.append(float(raw))

    while len(normalized) < max_days:
        normalized.append(0.0)

    return normalized


def resolve_hos_field_ids(available_ids: Iterable[str]) -> dict[str, str | None]:
    available_set = set(available_ids)
    used_recap_ids: set[str] = set()

    field_ids = {
        "off_duty_hours": _pick_field_id(available_set, ["off-duty-hours", "total-off-duty-hours"]),
        "sleeper_berth_hours": _pick_field_id(
            available_set,
            ["sleeper-berth-hours", "total-sleeper-berth-hours"],
        ),
        "driving_hours": _pick_field_id(available_set, ["driving-hours", "total-driving-hours"]),
        "on_duty_hours": _pick_field_id(available_set, ["on-duty-hours", "text482"]),
        "total_hours": _pick_field_id(available_set, ["total-hours"]),
        "total_on_duty_hours_today": _pick_field_id(
            available_set,
            ["total-on-duty-hours-today", "total-on-duty-hours"],
        ),
        "side60_a": _pick_field_id(
            available_set,
            ["on-duty-last-6-days", "on-duty-last-5-days"],
            used_recap_ids,
        ),
        "side60_b": _pick_field_id(
            available_set,
            ["available-hours-tomorrow-60hr"],
            used_recap_ids,
        ),
        "side60_c": _pick_field_id(
            available_set,
            ["on-duty-last-7-days-alt"],
            used_recap_ids,
        ),
        "side70_a": _pick_field_id(
            available_set,
            ["on-duty-last-7-days"],
            used_recap_ids,
        ),
        "side70_b": _pick_field_id(
            available_set,
            ["available-hours-tomorrow-70hr"],
            used_recap_ids,
        ),
        "side70_c": _pick_field_id(
            available_set,
            ["on-duty-last-8-days", "on-duty-last-5-days"],
            used_recap_ids,
        ),
    }

    return field_ids


def list_computed_field_ids(field_ids: Mapping[str, str | None]) -> list[str]:
    ordered_keys = (
        "total_hours",
        "total_on_duty_hours_today",
        "side60_a",
        "side60_b",
        "side60_c",
        "side70_a",
        "side70_b",
        "side70_c",
    )

    seen: set[str] = set()
    output: list[str] = []

    for key in ordered_keys:
        value = field_ids.get(key)
        if value and value not in seen:
            seen.add(value)
            output.append(value)

    return output


def apply_hos_compliance(
    values: Mapping[str, str | int | float | None],
    recap_input: HOSRecapInput | None,
    available_field_ids: Iterable[str],
) -> HOSComputationResult:
    field_ids = resolve_hos_field_ids(available_field_ids)

    off_duty_hours = _parse_number(values.get(field_ids["off_duty_hours"]))
    sleeper_berth_hours = _parse_number(values.get(field_ids["sleeper_berth_hours"]))
    driving_hours = _parse_number(values.get(field_ids["driving_hours"]))
    on_duty_hours = _parse_number(values.get(field_ids["on_duty_hours"]))

    computed_values: dict[str, str] = {}

    if field_ids["total_hours"]:
        computed_values[field_ids["total_hours"]] = _format_hours(
            off_duty_hours + sleeper_berth_hours + driving_hours + on_duty_hours
        )

    today_on_duty_hours = driving_hours + on_duty_hours

    if field_ids["total_on_duty_hours_today"]:
        computed_values[field_ids["total_on_duty_hours_today"]] = _format_hours(today_on_duty_hours)

    for recap_key in ("side60_a", "side60_b", "side60_c", "side70_a", "side70_b", "side70_c"):
        recap_id = field_ids.get(recap_key)
        if recap_id:
            computed_values[recap_id] = ""

    normalized_recap = recap_input or HOSRecapInput()
    previous_on_duty = _normalize_previous_on_duty(normalized_recap.previous_on_duty_hours)
    history = [today_on_duty_hours, *previous_on_duty]

    restart_applied = normalized_recap.longest_off_duty_streak_hours >= 34.0

    if normalized_recap.cycle == HOSCycle.CYCLE_70:
        cycle_cap_hours = 70.0
        recap_a_hours = 0.0 if restart_applied else _window_sum(history, 7)
        recap_c_hours = 0.0 if restart_applied else _window_sum(history, 5)
        available_hours_tomorrow = cycle_cap_hours if restart_applied else cycle_cap_hours - recap_a_hours

        if field_ids["side70_a"]:
            computed_values[field_ids["side70_a"]] = _format_hours(recap_a_hours)
        if field_ids["side70_b"]:
            computed_values[field_ids["side70_b"]] = _format_hours(available_hours_tomorrow)
        if field_ids["side70_c"]:
            computed_values[field_ids["side70_c"]] = _format_hours(recap_c_hours)
    else:
        cycle_cap_hours = 60.0
        recap_a_hours = 0.0 if restart_applied else _window_sum(history, 6)
        recap_c_hours = 0.0 if restart_applied else _window_sum(history, 7)
        available_hours_tomorrow = cycle_cap_hours if restart_applied else cycle_cap_hours - recap_a_hours

        if field_ids["side60_a"]:
            computed_values[field_ids["side60_a"]] = _format_hours(recap_a_hours)
        if field_ids["side60_b"]:
            computed_values[field_ids["side60_b"]] = _format_hours(available_hours_tomorrow)
        if field_ids["side60_c"]:
            computed_values[field_ids["side60_c"]] = _format_hours(recap_c_hours)

    is_legal_today = recap_a_hours <= cycle_cap_hours
    is_legal_tomorrow = available_hours_tomorrow >= 0.0

    violations: list[str] = []
    if not is_legal_today:
        violations.append(
            f"Cycle overrun: recap A is {round(recap_a_hours, 2)}h which exceeds {int(cycle_cap_hours)}h."
        )
    if not is_legal_tomorrow:
        violations.append(
            f"No available hours tomorrow: {round(available_hours_tomorrow, 2)}h remaining."
        )

    return HOSComputationResult(
        computed_values=computed_values,
        field_ids=field_ids,
        cycle=normalized_recap.cycle.value,
        cycle_cap_hours=cycle_cap_hours,
        recap_a_hours=round(recap_a_hours, 2),
        recap_c_hours=round(recap_c_hours, 2),
        available_hours_tomorrow=round(available_hours_tomorrow, 2),
        today_on_duty_hours=round(today_on_duty_hours, 2),
        restart_applied=restart_applied,
        is_legal_today=is_legal_today,
        is_legal_tomorrow=is_legal_tomorrow,
        violations=violations,
    )
