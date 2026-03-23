from __future__ import annotations

import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from hos_compliance import HOSCycle, HOSRecapInput, apply_hos_compliance, resolve_hos_field_ids


class HOSComplianceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.available_ids = {
            "off-duty-hours",
            "sleeper-berth-hours",
            "driving-hours",
            "on-duty-hours",
            "total-hours",
            "total-on-duty-hours-today",
            "on-duty-last-5-days",
            "available-hours-tomorrow-60hr",
            "on-duty-last-7-days-alt",
            "on-duty-last-7-days",
            "available-hours-tomorrow-70hr",
            "on-duty-last-8-days",
        }

    def test_resolve_hos_field_ids(self) -> None:
        mapping = resolve_hos_field_ids(self.available_ids)

        self.assertEqual(mapping["off_duty_hours"], "off-duty-hours")
        self.assertEqual(mapping["side60_a"], "on-duty-last-5-days")
        self.assertEqual(mapping["side70_c"], "on-duty-last-8-days")

    def test_cycle_70_computation_without_restart(self) -> None:
        values = {
            "off-duty-hours": "2",
            "sleeper-berth-hours": "2",
            "driving-hours": "8",
            "on-duty-hours": "2",
        }

        recap_input = HOSRecapInput(
            cycle=HOSCycle.CYCLE_70,
            previous_on_duty_hours=(8, 9, 7, 10, 8, 9, 6),
            longest_off_duty_streak_hours=12,
        )

        result = apply_hos_compliance(values, recap_input, self.available_ids)

        self.assertEqual(result.computed_values["total-hours"], "14")
        self.assertEqual(result.computed_values["total-on-duty-hours-today"], "10")
        self.assertEqual(result.computed_values["on-duty-last-7-days"], "61")
        self.assertEqual(result.computed_values["available-hours-tomorrow-70hr"], "9")
        self.assertEqual(result.computed_values["on-duty-last-8-days"], "44")
        self.assertTrue(result.is_legal_today)
        self.assertTrue(result.is_legal_tomorrow)

    def test_cycle_60_computation_with_restart(self) -> None:
        values = {
            "driving-hours": "11",
            "on-duty-hours": "2",
        }

        recap_input = HOSRecapInput(
            cycle=HOSCycle.CYCLE_60,
            previous_on_duty_hours=(12, 12, 12, 12, 12, 12, 12),
            longest_off_duty_streak_hours=34,
        )

        result = apply_hos_compliance(values, recap_input, self.available_ids)

        self.assertTrue(result.restart_applied)
        self.assertEqual(result.computed_values["on-duty-last-5-days"], "0")
        self.assertEqual(result.computed_values["available-hours-tomorrow-60hr"], "60")
        self.assertEqual(result.computed_values["on-duty-last-7-days-alt"], "0")

    def test_violation_when_over_cap(self) -> None:
        values = {
            "driving-hours": "14",
            "on-duty-hours": "4",
        }

        recap_input = HOSRecapInput(
            cycle=HOSCycle.CYCLE_60,
            previous_on_duty_hours=(10, 11, 12, 9, 8, 0, 0),
            longest_off_duty_streak_hours=0,
        )

        result = apply_hos_compliance(values, recap_input, self.available_ids)

        self.assertFalse(result.is_legal_today)
        self.assertFalse(result.is_legal_tomorrow)
        self.assertGreater(len(result.violations), 0)


if __name__ == "__main__":
    unittest.main()
