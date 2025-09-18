import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("drivers", "0001_initial"),
        ("trips", "0002_trip_route_metadata"),
    ]

    operations = [
        migrations.CreateModel(
            name="LogEvent",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("day", models.DateField()),
                ("timestamp", models.DateTimeField()),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("OFF", "OFF"),
                            ("SLEEPER", "SLEEPER"),
                            ("DRIVING", "DRIVING"),
                            ("ON_DUTY", "ON_DUTY"),
                        ],
                        max_length=16,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "driver",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="log_events",
                        to="drivers.driver",
                    ),
                ),
                (
                    "trip",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="log_events",
                        to="trips.trip",
                    ),
                ),
            ],
            options={"ordering": ["timestamp"]},
        ),
        migrations.AddIndex(
            model_name="logevent",
            index=models.Index(fields=["trip", "day"], name="logs_logev_trip_id_6f4b6f_idx"),
        ),
        migrations.AddIndex(
            model_name="logevent",
            index=models.Index(fields=["driver", "day"], name="logs_logev_driver__e8d28a_idx"),
        ),
        migrations.AddIndex(
            model_name="logevent",
            index=models.Index(fields=["timestamp"], name="logs_logev_timesta_7d9d7b_idx"),
        ),
    ]
