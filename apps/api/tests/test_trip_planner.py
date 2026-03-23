from __future__ import annotations

from datetime import date
import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from trip_planner import TripPlannerError, plan_trip


class TripPlannerTests(unittest.TestCase):
    def test_plan_trip_builds_multi_day_plan_and_route_summary(self) -> None:
        result = plan_trip(
            current_location="33.4484,-112.0740",  # Phoenix
            pickup_location="35.1983,-111.6513",  # Flagstaff
            dropoff_location="32.7767,-96.7970",  # Dallas
            current_cycle_used_hours=8.0,
            cycle="70",
            start_date=date(2026, 2, 10),
        )

        self.assertGreater(result.route["total_distance_miles"], 100.0)
        self.assertGreaterEqual(len(result.daily_logs), 2)
        self.assertEqual("2026-02-10", result.daily_logs[0].log_date)
        self.assertIn("openstreetmap.org/directions", result.route["openstreetmap_directions_url"])
        self.assertGreater(len(result.stops), 0)

        for day in result.daily_logs:
            total_hours = day.off_duty_hours + day.sleeper_berth_hours + day.driving_hours + day.on_duty_hours
            self.assertAlmostEqual(24.0, total_hours, places=2)
            self.assertLessEqual(day.driving_hours, 11.0 + 0.01)
            self.assertLessEqual(day.driving_hours + day.on_duty_hours, 14.0 + 0.01)
            self.assertGreater(len(day.timeline_events), 0)

    def test_plan_trip_rejects_invalid_cycle_usage(self) -> None:
        with self.assertRaises(TripPlannerError):
            plan_trip(
                current_location="33.4484,-112.0740",
                pickup_location="35.1983,-111.6513",
                dropoff_location="32.7767,-96.7970",
                current_cycle_used_hours=75.0,
                cycle="70",
                start_date=date(2026, 2, 10),
            )


if __name__ == "__main__":
    unittest.main()

