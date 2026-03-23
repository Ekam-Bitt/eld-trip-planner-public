from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import re
from typing import Sequence
import xml.etree.ElementTree as ET
from pathlib import Path
from xml.sax.saxutils import escape


class DutyStatus(str, Enum):
    OFF = "off"
    SLEEPER = "sleeper"
    DRIVING = "driving"
    ON = "on"


@dataclass(frozen=True)
class TimelinePoint:
    h: int
    m: int


@dataclass(frozen=True)
class TimelineEvent:
    start: TimelinePoint
    duty: DutyStatus
    end: TimelinePoint | None = None
    location: str | None = None
    activity: str | None = None


@dataclass(frozen=True)
class TimelineConstants:
    start_x: float = 70.0
    px_per_hour: float = 19.924
    px_per_minute: float = 0.332


TIMELINE = TimelineConstants()
DUTY_Y = {
    DutyStatus.OFF: 291.227,
    DutyStatus.SLEEPER: 311.227,
    DutyStatus.DRIVING: 331.227,
    DutyStatus.ON: 351.227,
}
CURVE_HEIGHT = 18.0
LABEL_OFFSET = 26.0

_TIMELINE_GROUP_OPEN_CLOSE = re.compile(
    r"(<g\b[^>]*\bid=\"timeline-events\"[^>]*>)(?P<body>.*?)(</g>)",
    re.DOTALL,
)
_TIMELINE_GROUP_SELFCLOSE = re.compile(
    r"<g\b(?P<attrs>[^>]*\bid=\"timeline-events\"[^>]*)\s*/>",
    re.DOTALL,
)


class TimelineRenderError(RuntimeError):
    """Raised when timeline events are invalid or injection fails."""


def _minutes(point: TimelinePoint) -> int:
    return point.h * 60 + point.m


def detect_template_scale(template_path: Path) -> float:
    """Scale canonical constants to template user units using width/viewBox ratio."""
    try:
        root = ET.parse(template_path).getroot()
    except Exception:
        return 1.0

    width_attr = (root.get("width") or "").strip()
    viewbox_attr = (root.get("viewBox") or "").strip()
    if not width_attr or not viewbox_attr:
        return 1.0

    width_match = re.match(r"^([0-9]+(?:\\.[0-9]+)?)", width_attr)
    if width_match is None:
        return 1.0

    width = float(width_match.group(1))
    if width <= 0:
        return 1.0

    parts = viewbox_attr.replace(",", " ").split()
    if len(parts) != 4:
        return 1.0

    try:
        viewbox_width = float(parts[2])
    except ValueError:
        return 1.0

    if viewbox_width <= 0:
        return 1.0

    return viewbox_width / width


def time_to_x(h: int, m: int, scale: float = 1.0) -> float:
    return (
        TIMELINE.start_x * scale
        + h * TIMELINE.px_per_hour * scale
        + m * TIMELINE.px_per_minute * scale
    )


def _line(x: float, y1: float, y2: float) -> str:
    return (
        f'<line x1="{x}" y1="{y1}" x2="{x}" y2="{y2}" '
        'stroke="black" stroke-width="1" />'
    )


def _horizontal_line(x1: float, x2: float, y: float) -> str:
    return (
        f'<line x1="{x1}" y1="{y}" x2="{x2}" y2="{y}" '
        'stroke="black" stroke-width="1" />'
    )


def _text(x: float, y: float, content: str) -> str:
    return (
        f'<text x="{x}" y="{y}" text-anchor="middle" '
        'style="font-size:2.38125px;font-family:Helvetica;fill:#5b6ab1;fill-opacity:0.933333;stroke:none;">'
        f"{escape(content)}</text>"
    )


def _validate_point(point: TimelinePoint, point_name: str) -> None:
    if point.h < 0 or point.h > 23:
        raise TimelineRenderError(f"{point_name}.h must be between 0 and 23")
    if point.m < 0 or point.m > 59:
        raise TimelineRenderError(f"{point_name}.m must be between 0 and 59")


def normalize_events(events: Sequence[TimelineEvent]) -> list[TimelineEvent]:
    normalized: list[TimelineEvent] = []

    for index, event in enumerate(events):
        _validate_point(event.start, f"events[{index}].start")

        if event.end is not None:
            _validate_point(event.end, f"events[{index}].end")
            if _minutes(event.end) <= _minutes(event.start):
                raise TimelineRenderError(
                    f"events[{index}] has invalid duration: end must be after start"
                )

        normalized.append(event)

    # Stable sort by start time only. Keep caller order for same-time transitions.
    normalized.sort(key=lambda e: _minutes(e.start))
    return normalized


def _interval_end_minutes(
    event: TimelineEvent,
    next_event: TimelineEvent | None,
) -> int | None:
    if event.end is not None:
        return _minutes(event.end)
    if next_event is not None:
        next_start_minutes = _minutes(next_event.start)
        start_minutes = _minutes(event.start)
        if next_start_minutes > start_minutes:
            return next_start_minutes
    return None


def render_timeline(events: Sequence[TimelineEvent], scale: float = 1.0) -> str:
    normalized = normalize_events(events)

    output: list[str] = []
    prev_duty: DutyStatus | None = None
    prev_end_minutes: int | None = None

    for index, event in enumerate(normalized):
        next_event = normalized[index + 1] if index + 1 < len(normalized) else None
        start_minutes = _minutes(event.start)
        end_minutes = _interval_end_minutes(event, next_event)

        # Instant status change marker.
        if end_minutes is None or end_minutes <= start_minutes:
            if prev_duty is not None and prev_duty != event.duty and prev_end_minutes == start_minutes:
                output.append(
                    _line(
                        time_to_x(event.start.h, event.start.m, scale=scale),
                        DUTY_Y[prev_duty] * scale,
                        DUTY_Y[event.duty] * scale,
                    )
                )
            prev_duty = event.duty
            prev_end_minutes = start_minutes
            continue

        y = DUTY_Y[event.duty] * scale
        x_start = time_to_x(event.start.h, event.start.m, scale=scale)
        end_h = end_minutes // 60
        end_m = end_minutes % 60
        x_end = time_to_x(end_h, end_m, scale=scale)

        # Duty change connector at event start.
        if prev_duty is not None and prev_duty != event.duty and prev_end_minutes == start_minutes:
            output.append(_line(x_start, DUTY_Y[prev_duty] * scale, y))

        output.append(_horizontal_line(x_start, x_end, y))

        # Labels intentionally disabled for now; render only step lines.

        prev_duty = event.duty
        prev_end_minutes = end_minutes

    return "\n".join(output)


def inject_timeline_into_dynamic_body(dynamic_body: str, timeline_svg: str) -> str:
    if _TIMELINE_GROUP_OPEN_CLOSE.search(dynamic_body):
        return _TIMELINE_GROUP_OPEN_CLOSE.sub(
            lambda match: f"{match.group(1)}{timeline_svg}{match.group(3)}",
            dynamic_body,
            count=1,
        )

    if _TIMELINE_GROUP_SELFCLOSE.search(dynamic_body):
        return _TIMELINE_GROUP_SELFCLOSE.sub(
            lambda match: f"<g{match.group('attrs')}>{timeline_svg}</g>",
            dynamic_body,
            count=1,
        )

    raise TimelineRenderError(
        "Could not find <g id=\"timeline-events\"> inside <g id=\"dynamic\"> in template"
    )
