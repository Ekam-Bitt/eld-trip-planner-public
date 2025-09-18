import os
from unittest.mock import MagicMock, patch

from cryptography.fernet import Fernet
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from .models import Driver


class AuthFlowTests(APITestCase):
    def test_signup_login_logout_me(self):
        signup_url = reverse("drivers:signup")
        login_url = reverse("drivers:login")
        logout_url = reverse("drivers:logout")
        me_url = reverse("drivers:me")

        payload = {
            "name": "Alice",
            "email": "alice@example.com",
            "password": "Password123!@#",
            "license_no": "LIC123",
            "truck_type": "Semi",
            "avg_mpg": "6.50",
        }
        resp = self.client.post(signup_url, payload, format="json")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertTrue(Driver.objects.filter(email=payload["email"]).exists())

        resp = self.client.post(
            login_url,
            {"email": payload["email"], "password": payload["password"]},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        access = resp.data["access"]
        refresh = resp.data["refresh"]

        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
        resp = self.client.get(me_url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["email"], payload["email"])

        resp = self.client.post(logout_url, {"refresh": refresh}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_205_RESET_CONTENT)


class ProfileCrudAndDashboardTests(APITestCase):
    def setUp(self):
        # Ensure encryption key exists and patch get_fernet like other tests
        if not os.environ.get("MAPBOX_ENC_KEY"):
            os.environ["MAPBOX_ENC_KEY"] = Fernet.generate_key().decode()
        self.mock_get_fernet_patcher = patch("core.crypto.get_fernet")
        mock_get_fernet = self.mock_get_fernet_patcher.start()
        mock_fernet_instance = MagicMock()
        mock_fernet_instance.encrypt.side_effect = lambda x: Fernet(
            os.environ["MAPBOX_ENC_KEY"].encode()
        ).encrypt(x)
        mock_fernet_instance.decrypt.side_effect = lambda x: Fernet(
            os.environ["MAPBOX_ENC_KEY"].encode()
        ).decrypt(x)
        mock_get_fernet.return_value = mock_fernet_instance

        self.user = Driver.objects.create_user(
            email="carol@example.com",
            password="Password123!",
            name="Carol",
            license_no="LIC777",
        )
        # login
        login_url = reverse("drivers:login")
        resp = self.client.post(
            login_url, {"email": "carol@example.com", "password": "Password123!"}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {resp.data['access']}")

    def tearDown(self):
        self.mock_get_fernet_patcher.stop()

    def test_profile_update_fields_and_mapbox_key(self):
        url = reverse("drivers:profile-update")
        payload = {
            "name": "Carol D",
            "license_state": "CA",
            "truck_type": "Tractor",
            "truck_number": "T-100",
            "avg_mpg": "6.75",
            "carrier_name": "ACME Logistics",
            "terminal_name": "SF",
            "time_zone": "US/Pacific",
            "units": "km",
            "dark_mode": True,
            "mapbox_api_key": "pk.test",
        }
        resp = self.client.put(url, payload, format="json")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertEqual(self.user.name, "Carol D")
        self.assertEqual(self.user.license_state, "CA")
        self.assertEqual(self.user.truck_number, "T-100")
        self.assertEqual(self.user.units, "km")
        self.assertTrue(bool(self.user.mapbox_api_key_encrypted))

    def test_dashboard_structure(self):
        url = reverse("drivers:dashboard")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn("cycle", resp.data)
        self.assertIn("today", resp.data)
        self.assertIn("warnings", resp.data)
        self.assertIn("recent_trips", resp.data)
