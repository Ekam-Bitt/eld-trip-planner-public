import os
from datetime import datetime, timedelta, timezone

from cryptography.fernet import Fernet
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from core.crypto import encrypt_value
from drivers.models import Driver, DriverProfile
from logs.models import LogEvent
from trips.models import Trip


class LogEventApiTests(APITestCase):
    def setUp(self):
        if not os.environ.get("MAPBOX_ENC_KEY"):
            os.environ["MAPBOX_ENC_KEY"] = Fernet.generate_key().decode()
        self.driver = Driver.objects.create_user(
            email="sam@example.com",
            password="Password123!",
            name="Sam",
            license_no="LIC111",
            avg_mpg=6.0,
        )
        self.driver.mapbox_api_key_encrypted = encrypt_value("test-mapbox-key")
        self.driver.save()
        DriverProfile.objects.create(
            driver=self.driver, license_state="CA", time_zone="UTC-08:00", units="MILES"
        )

        # login
        login_url = reverse("drivers:login")
        resp = self.client.post(
            login_url,
            {"email": "sam@example.com", "password": "Password123!"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        access = resp.data["access"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")

        # create a minimal trip owned by driver to attach logs
        self.trip = Trip.objects.create(
            owner=self.driver,
            current_location="-118.2,34.0",
            pickup_location="-118.2,34.0",
            dropoff_location="-118.1,34.1",
            distance_miles=1,
            estimated_hours=1,
            fueling_stops=[],
            route_geometry={
                "type": "LineString",
                "coordinates": [[-118.2, 34.0], [-118.1, 34.1]],
            },
        )

    def test_create_and_list_logs(self):
        create_url = reverse("logs:create")
        now = datetime.now(timezone.utc)
        payload = {
            "trip_id": self.trip.id,
            "timestamp": now.isoformat(),
            "status": "DRIVING",
        }
        resp = self.client.post(create_url, payload, format="json")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.data["status"], "DRIVING")

        list_url = reverse("logs:list", args=[self.trip.id])
        resp = self.client.get(list_url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.data), 1)
        self.assertEqual(resp.data[0]["status"], "DRIVING")

    def test_hos_summary_11h_violation(self):
        # Build a day with > 11 hours driving
        day = datetime.now(timezone.utc).date().isoformat()
        t0 = datetime.fromisoformat(f"{day}T00:00:00+00:00")
        # Create segments: 12 hours continuous driving
        for hour in range(0, 12):
            LogEvent.objects.create(
                trip=self.trip,
                driver=self.driver,
                day=t0.date(),
                timestamp=t0 + timedelta(hours=hour),
                status="DRIVING",
            )
        url = reverse("logs:hos", args=[self.trip.id])
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        violations = resp.data["violations"]
        assert any(v["code"] == "11H" and v["day"] == day for v in violations)

    def test_hos_summary_30min_break_required(self):
        day = datetime.now(timezone.utc).date().isoformat()
        t0 = datetime.fromisoformat(f"{day}T00:00:00+00:00")
        # 9 hours driving without 30m OFF/SLEEPER break
        for hour in range(0, 9):
            LogEvent.objects.create(
                trip=self.trip,
                driver=self.driver,
                day=t0.date(),
                timestamp=t0 + timedelta(hours=hour),
                status="DRIVING",
            )
        url = reverse("logs:hos", args=[self.trip.id])
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        violations = resp.data["violations"]
        assert any(v["code"] == "30M" and v["day"] == day for v in violations)

    def test_inspection_create_and_list(self):
        create_url = reverse("logs:inspection-create")
        payload = {
            "trip_id": self.trip.id,
            "kind": "PRE_TRIP",
            "signature_driver": "Sam",
            "defects": [{"item": "Brakes", "severity": "LOW", "note": "ok"}],
            "notes": "Pre-trip check",
        }
        resp = self.client.post(create_url, payload, format="json")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        insp_id = resp.data["id"]
        self.assertEqual(resp.data["kind"], "PRE_TRIP")
        self.assertEqual(resp.data["trip"], self.trip.id)

        list_url = reverse("logs:inspection-list", args=[self.trip.id])
        resp = self.client.get(list_url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertTrue(any(i["id"] == insp_id for i in resp.data))

    def test_reports_pdf_and_csv(self):
        # Seed a simple log and inspection
        now = datetime.now(timezone.utc)
        self.client.post(
            reverse("logs:create"),
            {"trip_id": self.trip.id, "timestamp": now.isoformat(), "status": "ON_DUTY"},
            format="json",
        )
        self.client.post(
            reverse("logs:inspection-create"),
            {"trip_id": self.trip.id, "kind": "POST_TRIP", "signature_driver": "Sam"},
            format="json",
        )
        # PDF
        pdf_url = reverse("reports:trip-pdf", args=[self.trip.id])
        resp = self.client.get(pdf_url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp["Content-Type"], "application/pdf")
        self.assertTrue(len(resp.content) > 0)
        # CSV
        csv_url = reverse("reports:trip-csv", args=[self.trip.id])
        resp = self.client.get(csv_url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp["Content-Type"], "text/csv")
        body = resp.content.decode()
        self.assertIn("type,day,timestamp,status,city,state,activity", body)
        self.assertIn(
            "type,kind,performed_at,defects_count,signature_driver,signature_mechanic", body
        )

    def test_trip_creation_blocked_without_profile(self):
        # Clear required profile fields
        prof = self.driver.profile
        prof.license_state = ""
        prof.time_zone = ""
        prof.save()
        url = reverse("trips:list-create")
        resp = self.client.post(
            url,
            {
                "current_location": "-118.2,34.0",
                "pickup_location": "-118.2,34.0",
                "dropoff_location": "-118.1,34.1",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Complete your profile", resp.data.get("detail", ""))

    def test_csv_header_includes_profile_and_trip(self):
        # Ensure CSV header rows exist
        csv_url = reverse("reports:trip-csv", args=[self.trip.id])
        resp = self.client.get(csv_url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        body = resp.content.decode()
        self.assertIn("header,driver_name,Sam", body)
        self.assertIn("header,driver_license_no,LIC111", body)
