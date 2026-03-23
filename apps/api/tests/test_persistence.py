from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from persistence import (  # type: ignore
    create_bootstrap_admin,
    create_daily_log,
    create_user_with_organization,
    create_trip_run,
    create_session,
    create_user,
    get_driver_profile,
    get_daily_log,
    get_trip_run,
    get_user_by_email,
    get_user_by_session_token,
    hash_password,
    init_db,
    list_daily_logs,
    list_trip_runs,
    list_users,
    summarize_trip_run_logs,
    upsert_driver_profile,
    verify_password,
)


class PersistenceTests(unittest.TestCase):
    def with_db(self) -> tuple[Path, tempfile.TemporaryDirectory[str]]:
        tmp = tempfile.TemporaryDirectory()
        db_path = Path(tmp.name) / "app.db"
        init_db(db_path)
        return db_path, tmp

    def test_bootstrap_hash_and_session(self) -> None:
        db_path, temp_dir = self.with_db()
        self.addCleanup(temp_dir.cleanup)

        admin = create_bootstrap_admin(
            db_path=db_path,
            organization_name="Acme Logistics",
            full_name="Admin User",
            email="admin@example.com",
            password_hash_value=hash_password("Password123!"),
        )

        loaded_admin, password_hash_value = get_user_by_email(db_path, "admin@example.com")
        self.assertIsNotNone(loaded_admin)
        self.assertIsNotNone(password_hash_value)
        self.assertEqual(admin.id, loaded_admin.id)
        self.assertTrue(verify_password("Password123!", str(password_hash_value)))
        self.assertFalse(verify_password("wrong-password", str(password_hash_value)))

        session = create_session(db_path, admin.id)
        session_user = get_user_by_session_token(db_path, session.token)
        self.assertIsNotNone(session_user)
        self.assertEqual(session_user.id, admin.id)

    def test_create_user_and_filter_by_role(self) -> None:
        db_path, temp_dir = self.with_db()
        self.addCleanup(temp_dir.cleanup)

        admin = create_bootstrap_admin(
            db_path=db_path,
            organization_name="Acme Logistics",
            full_name="Admin User",
            email="admin@example.com",
            password_hash_value=hash_password("Password123!"),
        )
        driver = create_user(
            db_path=db_path,
            organization_id=admin.organization_id,
            full_name="Driver One",
            email="driver1@example.com",
            role="driver",
            password_hash_value=hash_password("Password123!"),
        )

        drivers = list_users(db_path, admin.organization_id, role="driver")
        self.assertEqual(1, len(drivers))
        self.assertEqual(driver.id, drivers[0].id)
        self.assertEqual("driver", drivers[0].role)

    def test_create_standalone_driver_and_upsert_profile(self) -> None:
        db_path, temp_dir = self.with_db()
        self.addCleanup(temp_dir.cleanup)

        driver = create_user_with_organization(
            db_path=db_path,
            organization_name="Northwind Transport",
            full_name="Driver One",
            email="driver1@example.com",
            role="driver",
            password_hash_value=hash_password("Password123!"),
        )

        profile = upsert_driver_profile(
            db_path=db_path,
            organization_id=driver.organization_id,
            user_id=driver.id,
            carrier_name="Northwind Transport",
            main_office_address="123 Main St, Dallas, TX",
            home_terminal_address="456 Yard Rd, Dallas, TX",
            truck_trailer_numbers="TRK-17 / TRL-9",
            cycle_rule="70",
            is_onboarding_complete=True,
        )

        loaded = get_driver_profile(db_path, driver.id)
        self.assertIsNotNone(loaded)
        self.assertEqual(profile.user_id, loaded.user_id)
        self.assertEqual("Northwind Transport", loaded.carrier_name)
        self.assertTrue(loaded.is_onboarding_complete)

    def test_create_and_retrieve_daily_log(self) -> None:
        db_path, temp_dir = self.with_db()
        self.addCleanup(temp_dir.cleanup)

        admin = create_bootstrap_admin(
            db_path=db_path,
            organization_name="Acme Logistics",
            full_name="Admin User",
            email="admin@example.com",
            password_hash_value=hash_password("Password123!"),
        )
        driver = create_user(
            db_path=db_path,
            organization_id=admin.organization_id,
            full_name="Driver One",
            email="driver1@example.com",
            role="driver",
            password_hash_value=hash_password("Password123!"),
        )

        created = create_daily_log(
            db_path=db_path,
            organization_id=admin.organization_id,
            driver_user_id=driver.id,
            created_by_user_id=admin.id,
            trip_run_id=None,
            log_date="2026-02-10",
            cycle="70",
            values={"from": "PHOENIX, AZ"},
            recap={"cycle": "70"},
            compliance={"is_legal_today": True, "available_hours_tomorrow": 9.5},
            timeline_events=[{"start": {"h": 6, "m": 0}, "duty": "driving"}],
            svg_path="/tmp/a.svg",
            pdf_path="/tmp/a.pdf",
        )

        listed = list_daily_logs(db_path=db_path, organization_id=admin.organization_id)
        self.assertEqual(1, len(listed))
        self.assertEqual(created["id"], listed[0]["id"])
        self.assertEqual(driver.id, listed[0]["driver_user_id"])

        fetched = get_daily_log(db_path, created["id"])
        self.assertIsNotNone(fetched)
        self.assertEqual("2026-02-10", fetched["log_date"])
        self.assertEqual("PHOENIX, AZ", fetched["values"]["from"])

    def test_trip_run_links_daily_logs(self) -> None:
        db_path, temp_dir = self.with_db()
        self.addCleanup(temp_dir.cleanup)

        admin = create_bootstrap_admin(
            db_path=db_path,
            organization_name="Acme Logistics",
            full_name="Admin User",
            email="admin@example.com",
            password_hash_value=hash_password("Password123!"),
        )
        driver = create_user(
            db_path=db_path,
            organization_id=admin.organization_id,
            full_name="Driver One",
            email="driver1@example.com",
            role="driver",
            password_hash_value=hash_password("Password123!"),
        )

        plan = {
            "cycle": "70",
            "locations": {"current": {"label": "Phoenix"}, "pickup": {"label": "Dallas"}, "dropoff": {"label": "Austin"}},
            "route": {"total_distance_miles": 1200.0, "total_driving_hours": 24.0},
            "stops": [{"label": "Fuel Stop"}],
            "daily_logs": [{"log_date": "2026-02-10"}, {"log_date": "2026-02-11"}],
            "days_count": 2,
        }
        trip = create_trip_run(
            db_path=db_path,
            organization_id=admin.organization_id,
            driver_user_id=driver.id,
            created_by_user_id=admin.id,
            cycle="70",
            current_location="Phoenix, AZ",
            pickup_location="Dallas, TX",
            dropoff_location="Austin, TX",
            current_cycle_used_hours=38.5,
            start_date="2026-02-10",
            end_date="2026-02-11",
            plan=plan,
        )

        create_daily_log(
            db_path=db_path,
            organization_id=admin.organization_id,
            driver_user_id=driver.id,
            created_by_user_id=admin.id,
            trip_run_id=trip["id"],
            log_date="2026-02-10",
            cycle="70",
            values={"from": "PHOENIX, AZ"},
            recap={"cycle": "70"},
            compliance={"is_legal_today": True, "is_legal_tomorrow": True},
            timeline_events=[{"start": {"h": 6, "m": 0}, "duty": "driving"}],
            svg_path="/tmp/a.svg",
            pdf_path="/tmp/a.pdf",
        )
        create_daily_log(
            db_path=db_path,
            organization_id=admin.organization_id,
            driver_user_id=driver.id,
            created_by_user_id=admin.id,
            trip_run_id=trip["id"],
            log_date="2026-02-11",
            cycle="70",
            values={"from": "DALLAS, TX"},
            recap={"cycle": "70"},
            compliance={"is_legal_today": True, "is_legal_tomorrow": True},
            timeline_events=[{"start": {"h": 7, "m": 0}, "duty": "driving"}],
            svg_path="/tmp/b.svg",
            pdf_path="/tmp/b.pdf",
        )

        runs = list_trip_runs(db_path, admin.organization_id)
        self.assertEqual(1, len(runs))
        self.assertEqual(trip["id"], runs[0]["id"])
        self.assertEqual(2, runs[0]["days_count"])

        linked_logs = list_daily_logs(
            db_path=db_path,
            organization_id=admin.organization_id,
            trip_run_id=trip["id"],
            limit=10,
        )
        self.assertEqual(2, len(linked_logs))
        self.assertTrue(all(item["trip_run_id"] == trip["id"] for item in linked_logs))

        fetched_trip = get_trip_run(db_path, trip["id"])
        self.assertIsNotNone(fetched_trip)
        self.assertEqual("Phoenix, AZ", fetched_trip["current_location"])

    def test_summarize_trip_run_logs(self) -> None:
        db_path, temp_dir = self.with_db()
        self.addCleanup(temp_dir.cleanup)

        admin = create_bootstrap_admin(
            db_path=db_path,
            organization_name="Acme Logistics",
            full_name="Admin User",
            email="admin@example.com",
            password_hash_value=hash_password("Password123!"),
        )
        driver = create_user(
            db_path=db_path,
            organization_id=admin.organization_id,
            full_name="Driver One",
            email="driver1@example.com",
            role="driver",
            password_hash_value=hash_password("Password123!"),
        )

        trip = create_trip_run(
            db_path=db_path,
            organization_id=admin.organization_id,
            driver_user_id=driver.id,
            created_by_user_id=admin.id,
            cycle="70",
            current_location="Phoenix, AZ",
            pickup_location="Dallas, TX",
            dropoff_location="Austin, TX",
            current_cycle_used_hours=25.0,
            start_date="2026-02-10",
            end_date="2026-02-11",
            plan={"days_count": 2},
        )

        create_daily_log(
            db_path=db_path,
            organization_id=admin.organization_id,
            driver_user_id=driver.id,
            created_by_user_id=admin.id,
            trip_run_id=trip["id"],
            log_date="2026-02-10",
            cycle="70",
            values={},
            recap={},
            compliance={"is_legal_today": True, "is_legal_tomorrow": True},
            timeline_events=[],
            svg_path="/tmp/a.svg",
            pdf_path="/tmp/a.pdf",
        )
        create_daily_log(
            db_path=db_path,
            organization_id=admin.organization_id,
            driver_user_id=driver.id,
            created_by_user_id=admin.id,
            trip_run_id=trip["id"],
            log_date="2026-02-11",
            cycle="70",
            values={},
            recap={},
            compliance={"is_legal_today": False, "is_legal_tomorrow": True},
            timeline_events=[],
            svg_path="/tmp/b.svg",
            pdf_path="/tmp/b.pdf",
        )

        summary = summarize_trip_run_logs(db_path, admin.organization_id, [trip["id"]])
        self.assertIn(trip["id"], summary)
        self.assertEqual(2, summary[trip["id"]]["generated_sheet_count"])
        self.assertFalse(summary[trip["id"]]["all_logs_legal"])
        self.assertEqual(1, summary[trip["id"]]["non_compliant_count"])


if __name__ == "__main__":
    unittest.main()
