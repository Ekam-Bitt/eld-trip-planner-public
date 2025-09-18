from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Iterable, List, Literal, Optional, Tuple

LogStatus = Literal["OFF", "SLEEPER", "DRIVING", "ON_DUTY"]


@dataclass
class LogEntry:
    timestamp: datetime
    status: LogStatus


@dataclass
class DailyTotals:
    off_hours: float
    sleeper_hours: float
    driving_hours: float
    on_duty_hours: float


@dataclass
class Violation:
    code: str
    message: str
    day: str  # YYYY-MM-DD


def _round_hours(minutes: int) -> float:
    return round(minutes / 60.0, 2)


def calculate_daily_totals(entries: Iterable[LogEntry], day: str) -> DailyTotals:
    """
    Compute OFF/SB/DR/ON totals for a given day.
    Assumes entries may span the day; we clamp to [00:00, 24:00).
    Entries must be sorted by timestamp ascending and include a terminal entry
    for the end-of-day status.
    """
    start = datetime.fromisoformat(f"{day}T00:00:00+00:00")
    end = datetime.fromisoformat(f"{day}T23:59:59.999999+00:00")

    clamped: List[Tuple[datetime, LogStatus]] = []
    for e in entries:
        t = e.timestamp
        if t < start:
            continue
        if t > end:
            break
        clamped.append((t, e.status))

    # Seed at day start if first entry is after midnight
    if not clamped:
        # Default entire day OFF if no entries
        return DailyTotals(_round_hours(24 * 60), 0.0, 0.0, 0.0)

    if clamped[0][0] > start:
        clamped.insert(0, (start, clamped[0][1]))

    # Ensure a closing timestamp at end-of-day
    if clamped[-1][0] <= end:
        clamped.append((end, clamped[-1][1]))

    totals_min: Dict[LogStatus, int] = {"OFF": 0, "SLEEPER": 0, "DRIVING": 0, "ON_DUTY": 0}

    for idx in range(len(clamped) - 1):
        t0, s0 = clamped[idx]
        t1, _ = clamped[idx + 1]
        minutes = max(0, int((t1 - t0).total_seconds() // 60))
        totals_min[s0] += minutes

    return DailyTotals(
        off_hours=_round_hours(totals_min["OFF"]),
        sleeper_hours=_round_hours(totals_min["SLEEPER"]),
        driving_hours=_round_hours(totals_min["DRIVING"]),
        on_duty_hours=_round_hours(totals_min["ON_DUTY"]),
    )


def detect_violations(
    entries_by_day: Dict[str, List[LogEntry]],
    cycle: Literal["70/8"] = "70/8",
) -> List[Violation]:
    """
    Detect HOS violations across days:
    - 11-hour driving limit (since last 10-hour OFF/SLEEPER reset)
    - 14-hour on-duty window (resets after 10-hour OFF/SLEEPER)
    - 30-minute break required within 8 hours of driving
    - 70-hour/8-day limit
    """
    violations: List[Violation] = []

    # Precompute daily totals and on-duty window bounds
    daily_totals_map: Dict[str, DailyTotals] = {}

    for day, entries in entries_by_day.items():
        sorted_entries = sorted(entries, key=lambda e: e.timestamp)
        daily_totals_map[day] = calculate_daily_totals(sorted_entries, day)

        # Build segments within the day (clamped)
        start_dt = datetime.fromisoformat(f"{day}T00:00:00+00:00")
        end_dt = datetime.fromisoformat(f"{day}T23:59:59.999999+00:00")
        seq: List[Tuple[datetime, LogStatus]] = []
        for e in sorted_entries:
            if e.timestamp < start_dt:
                continue
            if e.timestamp > end_dt:
                break
            seq.append((e.timestamp, e.status))
        if not seq:
            continue
        if seq[0][0] > start_dt:
            seq.insert(0, (start_dt, seq[0][1]))
        if seq[-1][0] <= end_dt:
            seq.append((end_dt, seq[-1][1]))

        # Rolling calculations with 10-hour OFF/SLEEPER reset
        window_start: Optional[datetime] = None
        max_window_span_min = 0
        driving_since_reset_min = 0
        max_driving_since_reset_min = 0
        minutes_driving_since_break = 0
        had_violation_30 = False

        for idx in range(len(seq) - 1):
            t0, s0 = seq[idx]
            t1, _ = seq[idx + 1]
            minutes = max(0, int((t1 - t0).total_seconds() // 60))

            # 10-hour reset
            if s0 in ("OFF", "SLEEPER") and minutes >= 10 * 60:
                window_start = None
                driving_since_reset_min = 0
                minutes_driving_since_break = 0

            # Start window at first on-duty/driving segment after reset
            if s0 in ("DRIVING", "ON_DUTY") and window_start is None:
                window_start = t0

            # Accrue on-duty window span
            if window_start is not None:
                span_min = int((t1 - window_start).total_seconds() // 60)
                if span_min > max_window_span_min:
                    max_window_span_min = span_min

            # Accrue driving since reset
            if s0 == "DRIVING":
                driving_since_reset_min += minutes
                if driving_since_reset_min > max_driving_since_reset_min:
                    max_driving_since_reset_min = driving_since_reset_min
                minutes_driving_since_break += minutes
            elif s0 in ("OFF", "SLEEPER"):
                # Break accrual
                if minutes >= 30:
                    minutes_driving_since_break = 0
            # else: ON_DUTY does not reset break

            # 30-minute break rule check mid-day
            if minutes_driving_since_break > 8 * 60 and not had_violation_30:
                had_violation_30 = True

        # End-of-day check for 30-min break
        if minutes_driving_since_break >= 8 * 60 and not had_violation_30:
            had_violation_30 = True

        # Apply violations for the day
        if max_driving_since_reset_min > 11 * 60:
            hours11 = _round_hours(max_driving_since_reset_min)
            msg11 = f"Driving exceeds 11 hours ({hours11}h)"
            violations.append(Violation(code="11H", message=msg11, day=day))

        if max_window_span_min > 14 * 60:
            hours14 = _round_hours(max_window_span_min)
            msg = f"On-duty window exceeds 14 hours ({hours14}h)"
            violations.append(Violation(code="14H", message=msg, day=day))

        if had_violation_30:
            violations.append(
                Violation(
                    code="30M",
                    message="30-min break required within 8 hours of driving",
                    day=day,
                )
            )

    # Weekly 70/8 limit: rolling 8 days
    if cycle == "70/8" and entries_by_day:
        all_days_sorted = sorted(entries_by_day.keys())
        # Build a map of day -> on-duty minutes (driving + on-duty)
        day_to_on_duty_min: Dict[str, int] = {}
        for day in all_days_sorted:
            totals = daily_totals_map.get(day)
            if not totals:
                continue
            day_to_on_duty_min[day] = int((totals.driving_hours + totals.on_duty_hours) * 60)

        for idx, day in enumerate(all_days_sorted):
            window_days = all_days_sorted[max(0, idx - 7) : idx + 1]
            total_min = sum(day_to_on_duty_min.get(d, 0) for d in window_days)
            if total_min > 70 * 60:
                msg = f"70-hour/8-day limit exceeded ({_round_hours(total_min)}h)"
                violations.append(Violation(code="70/8", message=msg, day=day))

    return violations
