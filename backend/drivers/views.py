from datetime import datetime, timedelta, timezone

from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView

from logs.models import LogEvent

from .models import Driver
from .serializers import (
    DriverCreateSerializer,
    DriverProfileUpdateSerializer,
    DriverSerializer,
    EmailTokenObtainPairSerializer,
)


class SignupView(generics.CreateAPIView):
    queryset = Driver.objects.all()
    serializer_class = DriverCreateSerializer
    permission_classes = [permissions.AllowAny]


class LoginView(TokenObtainPairView):
    permission_classes = [permissions.AllowAny]
    serializer_class = EmailTokenObtainPairSerializer


class LogoutView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, *args, **kwargs):
        refresh_token = request.data.get("refresh")
        if not refresh_token:
            return Response(
                {"detail": "Refresh token required"}, status=status.HTTP_400_BAD_REQUEST
            )
        try:
            token = RefreshToken(refresh_token)
            token.blacklist()
        except Exception:
            return Response({"detail": "Invalid refresh token"}, status=status.HTTP_400_BAD_REQUEST)
        return Response(status=status.HTTP_205_RESET_CONTENT)


class MeView(generics.RetrieveAPIView):
    serializer_class = DriverSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return self.request.user


class ProfileUpdateView(generics.UpdateAPIView):
    serializer_class = DriverProfileUpdateSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return self.request.user


class DashboardView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):  # type: ignore[override]
        user: Driver = request.user  # type: ignore[assignment]
        now = datetime.now(timezone.utc)
        start_today = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)
        start_8_days = start_today - timedelta(days=7)

        # Fetch last 8 days of log events
        events = (
            LogEvent.objects.filter(driver=user, timestamp__gte=start_8_days, timestamp__lt=now)
            .order_by("timestamp")
            .values("day", "timestamp", "status")
        )

        # Compute hours per status today and rolling 8 days
        def compute_hours(ev_list):
            totals = {"OFF": 0.0, "SLEEPER": 0.0, "DRIVING": 0.0, "ON_DUTY": 0.0}
            if not ev_list:
                return totals
            # Group by day
            from collections import defaultdict

            by_day: dict[str, list[dict]] = defaultdict(list)
            for e in ev_list:
                by_day[e["day"].isoformat()].append(e)  # type: ignore[attr-defined]
            # For each day, accumulate durations between events within [00:00,24:00]
            for day_key, arr in by_day.items():
                arr_sorted = sorted(arr, key=lambda x: x["timestamp"])  # type: ignore[index]
                day_dt = datetime.fromisoformat(day_key)
                day_start = datetime(day_dt.year, day_dt.month, day_dt.day, tzinfo=timezone.utc)
                day_end = day_start + timedelta(days=1)
                # Seed OFF at day start if first event after start
                entries: list[tuple[datetime, str]] = []
                if not arr_sorted or arr_sorted[0]["timestamp"] > day_start:
                    entries.append((day_start, "OFF"))
                for e in arr_sorted:
                    entries.append((e["timestamp"], e["status"]))
                # Ensure last entry extends to day_end
                if entries:
                    entries.append(
                        (min(day_end, now if day_end > now else day_end), entries[-1][1])
                    )
                # Sum per status
                for i in range(len(entries) - 1):
                    t0, s0 = entries[i]
                    t1, _ = entries[i + 1]
                    dur_h = max(0.0, (t1 - t0).total_seconds() / 3600.0)
                    totals[s0] += dur_h
            return totals

        totals_8d = compute_hours(list(events))
        # Today's subset
        events_today = [e for e in events if e["timestamp"] >= start_today]
        totals_today = compute_hours(events_today)

        # HOS caps: 11h driving per day; 14h on-duty window; 70h in 8 days
        driving_left_today = max(0.0, 11.0 - float(totals_today.get("DRIVING", 0.0)))
        onduty_left_today = max(
            0.0,
            14.0
            - float(totals_today.get("ON_DUTY", 0.0))
            - float(totals_today.get("DRIVING", 0.0)),
        )
        cycle_left_8d = max(
            0.0,
            70.0 - (float(totals_8d.get("ON_DUTY", 0.0)) + float(totals_8d.get("DRIVING", 0.0))),
        )

        warnings: list[str] = []
        if driving_left_today <= 3.0:
            warnings.append("Only %.1f driving hours left today" % driving_left_today)
        if onduty_left_today <= 2.0:
            warnings.append("On-duty window nearly exhausted")
        if cycle_left_8d <= 8.0:
            warnings.append("Cycle hours low: %.1f h remaining")

        recent_trips = list(
            user.trips.all()
            .order_by("-created_at")
            .values(
                "id",
                "pickup_location",
                "dropoff_location",
                "distance_miles",
                "estimated_hours",
                "created_at",
            )[:5]
        )

        return Response(
            {
                "cycle": {
                    "used_8d": round(70.0 - cycle_left_8d, 2),
                    "remaining_8d": round(cycle_left_8d, 2),
                },
                "today": {
                    "driving": round(float(totals_today.get("DRIVING", 0.0)), 2),
                    "on_duty": round(float(totals_today.get("ON_DUTY", 0.0)), 2),
                    "off": round(float(totals_today.get("OFF", 0.0)), 2),
                    "sleeper": round(float(totals_today.get("SLEEPER", 0.0)), 2),
                    "driving_left": round(driving_left_today, 2),
                    "onduty_left": round(onduty_left_today, 2),
                },
                "warnings": warnings,
                "recent_trips": recent_trips,
            }
        )
