import os
from unittest.mock import MagicMock, patch

from cryptography.fernet import Fernet
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from core.crypto import encrypt_value
from drivers.models import Driver


class TripsApiTests(APITestCase):
    def setUp(self):
        # Ensure encryption key is present for tests
        if not os.environ.get("MAPBOX_ENC_KEY"):
            os.environ["MAPBOX_ENC_KEY"] = Fernet.generate_key().decode()

        # Patch get_fernet for the duration of the test
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

        self.driver = Driver.objects.create_user(
            email="bob@example.com",
            password="Password123!",
            name="Bob",
            license_no="LIC999",
            avg_mpg=6.5,
        )
        self.driver.mapbox_api_key_encrypted = encrypt_value("test-mapbox-key")
        self.driver.save()

        # login
        login_url = reverse("drivers:login")
        resp = self.client.post(
            login_url,
            {"email": "bob@example.com", "password": "Password123!"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.access = resp.data["access"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.access}")

    def tearDown(self):
        self.mock_get_fernet_patcher.stop()

    @patch("requests.Session")
    def test_create_and_list_trip(self, mock_session):
        mock_session_instance = MagicMock()
        mock_session.return_value = mock_session_instance
        mock_session_instance.get.return_value.status_code = 200
        mock_session_instance.get.return_value.json.return_value = {
            "routes": [
                {
                    "distance": 160934.4,  # 100 miles in meters
                    "geometry": {
                        "type": "LineString",
                        "coordinates": [[-122.4, 37.8], [-121.9, 37.3]],
                    },
                }
            ]
        }

        create_url = reverse("trips:list-create")
        payload = {
            "current_location": "-122.4,37.8",
            "pickup_location": "-122.4,37.8",
            "dropoff_location": "-121.9,37.3",
        }
        resp = self.client.post(create_url, payload, format="json")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        trip_id = resp.data["id"]
        self.assertAlmostEqual(float(resp.data["distance_miles"]), 100.0, delta=0.1)
        self.assertIn("route_geometry", resp.data)

        # list
        resp = self.client.get(create_url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertTrue(len(resp.data) >= 1)

        # detail
        detail_url = reverse("trips:detail", args=[trip_id])
        resp = self.client.get(detail_url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["id"], trip_id)

        # no resume endpoint in scope
