"""Migration: upgrade Appointment + add Review."""
import django.core.validators
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("appointments", "0002_upgrade_nowserving_fields"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # ── Appointment new fields ────────────────────────────────────────────
        migrations.AddField(
            model_name="appointment",
            name="video_room_id",
            field=models.CharField(blank=True, max_length=200),
        ),
        migrations.AddField(
            model_name="appointment",
            name="pre_consult_files",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name="appointment",
            name="hmo_coverage_percent",
            field=models.PositiveSmallIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="appointment",
            name="hmo_provider",
            field=models.CharField(blank=True, max_length=100),
        ),
        migrations.AddField(
            model_name="appointment",
            name="consult_transcript",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="appointment",
            name="reminder_24h_sent",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="appointment",
            name="reminder_1h_sent",
            field=models.BooleanField(default=False),
        ),
        migrations.AlterField(
            model_name="appointment",
            name="type",
            field=models.CharField(
                choices=[("online", "Online"), ("in_clinic", "In Clinic"), ("on_demand", "On Demand")],
                default="in_clinic", max_length=10,
            ),
        ),
        # ── Review ────────────────────────────────────────────────────────────
        migrations.CreateModel(
            name="Review",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("rating", models.PositiveSmallIntegerField(
                    validators=[
                        django.core.validators.MinValueValidator(1),
                        django.core.validators.MaxValueValidator(5),
                    ]
                )),
                ("comment", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("appointment", models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="review",
                    to="appointments.appointment",
                )),
                ("doctor", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="reviews_received",
                    to=settings.AUTH_USER_MODEL,
                )),
                ("patient", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="reviews_given",
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={"ordering": ["-created_at"]},
        ),
    ]
