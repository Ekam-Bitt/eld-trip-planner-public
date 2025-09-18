from rest_framework import serializers

from logs.models import DailyLog, Inspection, LogEvent


class LogEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = LogEvent
        fields = (
            "id",
            "trip",
            "driver",
            "day",
            "timestamp",
            "status",
            "city",
            "state",
            "activity",
            "created_at",
        )
        read_only_fields = ("id", "driver", "created_at")


class LogEventCreateSerializer(serializers.Serializer):
    trip_id = serializers.IntegerField()
    timestamp = serializers.DateTimeField(required=False)
    status = serializers.ChoiceField(choices=LogEvent.Status.choices)
    city = serializers.CharField(max_length=128, required=False, allow_blank=True)
    state = serializers.CharField(max_length=64, required=False, allow_blank=True)
    activity = serializers.CharField(max_length=255, required=False, allow_blank=True)


class DailyLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = DailyLog
        fields = (
            "id",
            "trip",
            "driver",
            "day",
            "total_off",
            "total_sleeper",
            "total_driving",
            "total_on_duty",
            "submitted",
            "submitted_at",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "driver", "created_at", "updated_at", "submitted_at")


class InspectionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Inspection
        fields = (
            "id",
            "trip",
            "driver",
            "kind",
            "performed_at",
            "defects",
            "signature_driver",
            "signature_mechanic",
            "notes",
            "created_at",
        )
        read_only_fields = ("id", "driver", "created_at")


class InspectionCreateSerializer(serializers.Serializer):
    trip_id = serializers.IntegerField()
    kind = serializers.ChoiceField(choices=Inspection.Type.choices)
    performed_at = serializers.DateTimeField(required=False)
    defects = serializers.ListField(child=serializers.DictField(), required=False)
    signature_driver = serializers.CharField(max_length=255)
    signature_mechanic = serializers.CharField(max_length=255, required=False, allow_blank=True)
    notes = serializers.CharField(required=False, allow_blank=True)
