from rest_framework import serializers

from .models import Trip


class TripSerializer(serializers.ModelSerializer):
    route_metadata = serializers.JSONField(required=False)

    class Meta:
        model = Trip
        fields = (
            "id",
            "current_location",
            "pickup_location",
            "dropoff_location",
            "distance_miles",
            "estimated_hours",
            "fueling_stops",
            "pickup_time",
            "dropoff_time",
            "route_geometry",
            "route_metadata",
            # new fields
            "log_date",
            "co_driver_name",
            "tractor_number",
            "trailer_numbers",
            "other_trailers",
            "shipper_name",
            "commodity_description",
            "load_id",
            "total_miles_driving_today",
            "total_mileage_today",
            "created_at",
        )
        read_only_fields = (
            "id",
            "distance_miles",
            "estimated_hours",
            "fueling_stops",
            "route_geometry",
            "route_metadata",
            "created_at",
        )


class TripCreateSerializer(serializers.Serializer):
    current_location = serializers.CharField()
    pickup_location = serializers.CharField()
    dropoff_location = serializers.CharField()
    current_cycle_used_hrs = serializers.FloatField(required=False)
    pickup_time = serializers.DateTimeField(required=False, allow_null=True)
    dropoff_time = serializers.DateTimeField(required=False, allow_null=True)
    # new trip fields (optional at create)
    log_date = serializers.DateField(required=False)
    co_driver_name = serializers.CharField(required=False, allow_blank=True)
    tractor_number = serializers.CharField(required=False, allow_blank=True)
    trailer_numbers = serializers.CharField(required=False, allow_blank=True)
    other_trailers = serializers.CharField(required=False, allow_blank=True)
    shipper_name = serializers.CharField(required=False, allow_blank=True)
    commodity_description = serializers.CharField(required=False, allow_blank=True)
    load_id = serializers.CharField(required=False, allow_blank=True)
    total_miles_driving_today = serializers.DecimalField(
        max_digits=8, decimal_places=2, required=False
    )
    total_mileage_today = serializers.DecimalField(max_digits=8, decimal_places=2, required=False)
