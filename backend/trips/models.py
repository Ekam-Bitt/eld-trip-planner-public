from django.conf import settings
from django.db import models


class Trip(models.Model):
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="trips"
    )
    current_location = models.CharField(max_length=255)
    pickup_location = models.CharField(max_length=255)
    dropoff_location = models.CharField(max_length=255)
    distance_miles = models.DecimalField(max_digits=8, decimal_places=2)
    estimated_hours = models.DecimalField(max_digits=6, decimal_places=2)
    fueling_stops = models.JSONField(default=list)
    pickup_time = models.DateTimeField(null=True, blank=True)
    dropoff_time = models.DateTimeField(null=True, blank=True)
    route_geometry = models.JSONField()  # GeoJSON LineString
    route_metadata = models.JSONField(null=True, blank=True)

    # Trip-specific header fields
    log_date = models.DateField(null=True, blank=True)
    co_driver_name = models.CharField(max_length=255, default="N/A")
    tractor_number = models.CharField(max_length=64, blank=True)
    trailer_numbers = models.CharField(max_length=255, blank=True)  # comma-separated
    other_trailers = models.CharField(max_length=255, blank=True)
    shipper_name = models.CharField(max_length=255, blank=True)
    commodity_description = models.CharField(max_length=255, blank=True)
    load_id = models.CharField(max_length=128, blank=True)
    # Totals
    total_miles_driving_today = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True
    )
    total_mileage_today = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:  # type: ignore[override]
        return f"Trip {self.id} by {self.owner_id}"
