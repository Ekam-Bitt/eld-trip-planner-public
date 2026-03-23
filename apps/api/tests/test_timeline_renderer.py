from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from driver_log_renderer import write_filled_svg
from timeline_renderer import DutyStatus, TimelineEvent, TimelinePoint, render_timeline


class TimelineRendererTests(unittest.TestCase):
    def test_render_timeline_contains_step_lines(self) -> None:
        events = [
            TimelineEvent(
                start=TimelinePoint(6, 0),
                end=TimelinePoint(8, 30),
                duty=DutyStatus.DRIVING,
            ),
            TimelineEvent(
                start=TimelinePoint(8, 30),
                duty=DutyStatus.ON,
            ),
        ]

        timeline_svg = render_timeline(events)

        self.assertIn("<line", timeline_svg)
        self.assertIn('y1="331.227"', timeline_svg)
        self.assertIn('y2="351.227"', timeline_svg)

    def test_write_filled_svg_injects_into_dynamic_timeline_group_only(self) -> None:
        template = """<?xml version=\"1.0\"?>
<svg xmlns=\"http://www.w3.org/2000/svg\">
  <g id=\"other\"><g id=\"timeline-events\" /></g>
  <g id=\"dynamic\">
    <text id=\"from\"><tspan>OLD</tspan></text>
    <g id=\"timeline-events\" />
  </g>
</svg>
"""

        timeline_svg = render_timeline(
            [
                TimelineEvent(
                    start=TimelinePoint(6, 0),
                    end=TimelinePoint(7, 0),
                    duty=DutyStatus.DRIVING,
                )
            ]
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            template_path = Path(tmp_dir) / "template.svg"
            output_path = Path(tmp_dir) / "filled.svg"
            template_path.write_text(template, encoding="utf-8")

            write_filled_svg(
                template_path,
                output_path,
                values={"from": "NEW"},
                timeline_svg=timeline_svg,
            )

            output = output_path.read_text(encoding="utf-8")

        self.assertIn("<text id=\"from\"><tspan>NEW</tspan></text>", output)

        dynamic_start = output.find('<g id="dynamic">')
        dynamic_end = output.find("</g>", dynamic_start)
        dynamic_chunk = output[dynamic_start:dynamic_end]

        other_start = output.find('<g id="other">')
        other_end = output.find("</g>", other_start)
        other_chunk = output[other_start:other_end]

        self.assertIn("<line", dynamic_chunk)
        self.assertNotIn("<line", other_chunk)


if __name__ == "__main__":
    unittest.main()
