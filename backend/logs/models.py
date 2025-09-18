from django.conf import settings
from django.db import models


class LogEvent(models.Model):
    class Status(models.TextChoices):
        OFF = "OFF", "OFF"
        SLEEPER = "SLEEPER", "SLEEPER"
        DRIVING = "DRIVING", "DRIVING"
        ON_DUTY = "ON_DUTY", "ON_DUTY"

    trip = models.ForeignKey("trips.Trip", on_delete=models.CASCADE, related_name="log_events")
    driver = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="log_events"
    )
    day = models.DateField()
    timestamp = models.DateTimeField()
    status = models.CharField(max_length=16, choices=Status.choices)
    # Optional remarks aligned with duty change moments
    city = models.CharField(max_length=128, blank=True)
    state = models.CharField(max_length=64, blank=True)
    activity = models.CharField(max_length=255, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["trip", "day"]),
            models.Index(fields=["driver", "day"]),
            models.Index(fields=["timestamp"]),
        ]
        ordering = ["timestamp"]

    def __str__(self) -> str:  # type: ignore[override]
        ts = self.timestamp.isoformat()
        return f"LogEvent({self.trip_id}, {self.driver_id}, {self.status}, {ts})"


class DailyLog(models.Model):
    """Aggregated daily log per trip/driver/day. Allows review and submission."""

    trip = models.ForeignKey("trips.Trip", on_delete=models.CASCADE, related_name="daily_logs")
    driver = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="daily_logs"
    )
    day = models.DateField()

    total_off = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    total_sleeper = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    total_driving = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    total_on_duty = models.DecimalField(max_digits=5, decimal_places=2, default=0)

    submitted = models.BooleanField(default=False)
    submitted_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("trip", "driver", "day")
        indexes = [models.Index(fields=["trip", "day"]), models.Index(fields=["driver", "day"])]
        ordering = ["day"]

    def __str__(self) -> str:  # type: ignore[override]
        return f"DailyLog({self.trip_id}, {self.driver_id}, {self.day})"


class Inspection(models.Model):
    class Type(models.TextChoices):
        PRE_TRIP = "PRE_TRIP", "PRE_TRIP"
        POST_TRIP = "POST_TRIP", "POST_TRIP"

    trip = models.ForeignKey("trips.Trip", on_delete=models.CASCADE, related_name="inspections")
    driver = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="inspections"
    )
    kind = models.CharField(max_length=16, choices=Type.choices)
    performed_at = models.DateTimeField()
    defects = models.JSONField(default=list)  # list of {item, severity, note}
    signature_driver = models.CharField(max_length=255)
    signature_mechanic = models.CharField(max_length=255, blank=True)
    notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["trip", "kind"]), models.Index(fields=["driver"])]
        ordering = ["-performed_at"]

    def __str__(self) -> str:  # type: ignore[override]
        return f"Inspection({self.trip_id}, {self.kind}, {self.performed_at.isoformat()})"
