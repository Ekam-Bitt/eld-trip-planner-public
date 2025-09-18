from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from core.crypto import encrypt_value

from .models import Driver, DriverProfile


class DriverProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = DriverProfile
        fields = (
            "license_state",
            "driver_initials",
            "driver_signature",
            "home_center_city",
            "home_center_state",
            "carrier",
            "time_zone",
            "units",
            "main_office_address",
            "home_terminal_address",
        )


class DriverSerializer(serializers.ModelSerializer):
    profile = DriverProfileSerializer(read_only=True)

    class Meta:
        model = Driver
        fields = (
            "id",
            "name",
            "email",
            "license_no",
            "license_state",
            "truck_type",
            "truck_number",
            "avg_mpg",
            "carrier_name",
            "terminal_name",
            "time_zone",
            "units",
            "dark_mode",
            "date_joined",
            "has_mapbox_key",
            "profile",
        )
        read_only_fields = ("id", "email", "date_joined", "has_mapbox_key")

    has_mapbox_key = serializers.SerializerMethodField()

    def get_has_mapbox_key(self, obj: Driver) -> bool:  # type: ignore[override]
        return bool(obj.mapbox_api_key_encrypted)


class DriverCreateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)

    class Meta:
        model = Driver
        fields = ("name", "email", "password", "license_no", "truck_type", "avg_mpg")

    def create(self, validated_data):
        password = validated_data.pop("password")
        user = Driver.objects.create_user(password=password, **validated_data)
        DriverProfile.objects.create(driver=user)
        return user


class DriverProfileUpdateSerializer(serializers.Serializer):
    # Optional fields for updates
    mapbox_api_key = serializers.CharField(write_only=True, required=False, allow_blank=False)
    name = serializers.CharField(required=False)
    license_no = serializers.CharField(required=False)
    license_state = serializers.CharField(required=False, allow_blank=True)
    truck_type = serializers.CharField(required=False, allow_blank=True)
    truck_number = serializers.CharField(required=False, allow_blank=True)
    avg_mpg = serializers.DecimalField(max_digits=5, decimal_places=2, required=False)
    carrier_name = serializers.CharField(required=False, allow_blank=True)
    terminal_name = serializers.CharField(required=False, allow_blank=True)
    time_zone = serializers.CharField(required=False)
    units = serializers.ChoiceField(choices=("miles", "km"), required=False)
    dark_mode = serializers.BooleanField(required=False)

    def update(self, instance: Driver, validated_data):  # type: ignore[override]
        update_fields: list[str] = []
        key = validated_data.get("mapbox_api_key")
        if key:
            instance.mapbox_api_key_encrypted = encrypt_value(key.strip())
            update_fields.append("mapbox_api_key_encrypted")

        for field in [
            "name",
            "license_no",
            "license_state",
            "truck_type",
            "truck_number",
            "avg_mpg",
            "carrier_name",
            "terminal_name",
            "time_zone",
            "units",
            "dark_mode",
        ]:
            if field in validated_data:
                setattr(instance, field, validated_data[field])
                update_fields.append(field)

        if update_fields:
            instance.save(update_fields=update_fields)
        return instance


class EmailTokenObtainPairSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token["email"] = user.email
        token["name"] = user.name
        return token
