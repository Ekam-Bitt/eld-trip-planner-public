from datetime import datetime, timedelta, timezone

from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView

from logs.models import LogEvent
from drivers.models import DriverProfile

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

        # Resolve driver's home terminal time zone offset (e.g., "UTC-08:00")
        profile, _ = DriverProfile.objects.get_or_create(driver=user)

        def _parse_utc_offset(offset_str: str | None) -> timedelta:
            if not offset_str or not offset_str.startswith("UTC"):
                return timedelta(0)
            try:
                sign = 1 if "+" in offset_str else -1
                hhmm = offset_str.split("UTC")[1].strip("+").strip("-")
                hours, minutes = hhmm.split(":")
                return sign * timedelta(hours=int(hours), minutes=int(minutes))
            except Exception:
                return timedelta(0)

        offset = _parse_utc_offset(profile.time_zone)

        # Compute "today" and 8-day window in driver's local time, then convert to UTC for queries
        local_now = now + offset
        local_start_today = datetime(local_now.year, local_now.month, local_now.day, tzinfo=timezone.utc)
        # local_start_today is a naive midnight in local frame represented as UTC tz-aware at local midnight; convert to UTC boundary by subtracting offset
        start_today = (local_start_today - offset).astimezone(timezone.utc)
        start_8_days = start_today - timedelta(days=7)

        # Fetch last 8 days of log events
        events = (
            LogEvent.objects.filter(driver=user, timestamp__gte=start_8_days, timestamp__lt=now)
            .order_by("timestamp")
            .values("day", "timestamp", "status")
        )

        # Compute hours per status (driver-local day boundaries) and roll-up
        def compute_hours(ev_list):
            totals = {"OFF": 0.0, "SLEEPER": 0.0, "DRIVING": 0.0, "ON_DUTY": 0.0}
            if not ev_list:
                return totals
            # Group by driver-local day using timestamp + offset
            from collections import defaultdict

            by_day: dict[str, list[dict]] = defaultdict(list)
            for e in ev_list:
                local_day_key = (e["timestamp"] + offset).date().isoformat()
                by_day[local_day_key].append(e)

            # For each driver-local day, accumulate durations within [local 00:00, local 24:00)
            for day_key, arr in by_day.items():
                arr_sorted = sorted(arr, key=lambda x: x["timestamp"])  # type: ignore[index]

                # Compute local day window and corresponding UTC instants
                day_local_start = datetime.fromisoformat(f"{day_key}T00:00:00+00:00")
                day_local_end = datetime.fromisoformat(f"{day_key}T23:59:59.999999+00:00")
                day_utc_start = (day_local_start - offset).astimezone(timezone.utc)
                day_utc_end = (day_local_end - offset).astimezone(timezone.utc)

                # Build entries in local frame by shifting timestamps by offset (durations preserved)
                entries_local: list[tuple[datetime, str]] = []

                # Seed with previous status at local midnight if first event is after start
                if not arr_sorted or arr_sorted[0]["timestamp"] > day_utc_start:
                    prev = (
                        LogEvent.objects.filter(driver=user, timestamp__lt=day_utc_start)
                        .order_by("-timestamp")
                        .values("status", "timestamp")
                        .first()
                    )
                    seed_status = prev["status"] if prev else "OFF"
                    entries_local.append((day_local_start, seed_status))

                for e in arr_sorted:
                    entries_local.append((e["timestamp"] + offset, e["status"]))

                # Extend to end of local day or local now if today
                local_now_eff = now + offset
                terminal = day_local_end if day_local_end <= local_now_eff else local_now_eff
                if entries_local:
                    entries_local.append((terminal, entries_local[-1][1]))

                # Sum per status
                for i in range(len(entries_local) - 1):
                    t0, s0 = entries_local[i]
                    t1, _ = entries_local[i + 1]
                    # Clamp within [day_local_start, day_local_end]
                    if t1 <= day_local_start or t0 >= day_local_end:
                        continue
                    t0c = max(t0, day_local_start)
                    t1c = min(t1, day_local_end)
                    dur_h = max(0.0, (t1c - t0c).total_seconds() / 3600.0)
                    totals[s0] += dur_h
            return totals

        totals_8d = compute_hours(list(events))
        # Today's subset (driver-local): events with timestamp >= start_today (UTC boundary for local midnight)
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
