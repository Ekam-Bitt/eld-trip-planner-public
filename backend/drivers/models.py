from django.contrib.auth.models import (
    AbstractBaseUser,
    BaseUserManager,
    PermissionsMixin,
)
from django.db import models


class DriverManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("Email must be provided")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        if password:
            user.set_password(password)
        else:
            raise ValueError("Password must be provided")
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")
        return self.create_user(email, password, **extra_fields)


class Driver(AbstractBaseUser, PermissionsMixin):
    name = models.CharField(max_length=255)
    email = models.EmailField(unique=True)
    # License and vehicle
    license_no = models.CharField(max_length=64)
    license_state = models.CharField(max_length=16, blank=True, null=True)
    truck_type = models.CharField(max_length=128, blank=True)
    truck_number = models.CharField(max_length=64, blank=True, null=True)
    avg_mpg = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    # Employment/org
    carrier_name = models.CharField(max_length=255, blank=True, null=True)
    terminal_name = models.CharField(max_length=255, blank=True, null=True)
    # Encrypted Mapbox API key (Fernet). Store ciphertext; decrypt on use.
    mapbox_api_key_encrypted = models.TextField(null=True, blank=True)
    # Preferences
    time_zone = models.CharField(max_length=64, default="UTC")
    units = models.CharField(
        max_length=8,
        choices=(
            ("miles", "Miles"),
            ("km", "Kilometers"),
        ),
        default="miles",
    )
    dark_mode = models.BooleanField(default=False)

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(auto_now_add=True)

    objects = DriverManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["name"]

    def __str__(self) -> str:  # type: ignore[override]
        return f"{self.name} <{self.email}>"


class DriverProfile(models.Model):
    UNITS_CHOICES = (("MILES", "Miles"), ("KM", "Kilometers"))

    driver = models.OneToOneField(Driver, on_delete=models.CASCADE, related_name="profile")
    license_state = models.CharField(max_length=2, blank=True)
    driver_initials = models.CharField(max_length=8, blank=True)
    driver_signature = models.TextField(
        blank=True
    )  # digital signature (text/URL/base64 as app chooses)
    home_center_city = models.CharField(max_length=128, blank=True)
    home_center_state = models.CharField(max_length=2, blank=True)
    carrier = models.CharField(max_length=255, blank=True)
    time_zone = models.CharField(max_length=32, blank=True)  # e.g., 'UTC-05:00'
    units = models.CharField(max_length=8, choices=UNITS_CHOICES, default="MILES")
    # Addresses
    main_office_address = models.TextField(blank=True)
    home_terminal_address = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:  # type: ignore[override]
        return f"DriverProfile({self.driver_id})"


# Create your models here.
