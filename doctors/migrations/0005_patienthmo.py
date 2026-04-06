"""Migration: add PatientHMO model to doctors app."""
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("doctors", "0004_alter_doctorprofile_options_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="PatientHMO",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("provider", models.CharField(max_length=100)),
                ("member_id", models.CharField(max_length=100)),
                ("card_image", models.ImageField(blank=True, null=True, upload_to="hmo_cards/")),
                ("verification_status", models.CharField(
                    choices=[("pending", "Pending"), ("verified", "Verified"), ("rejected", "Rejected")],
                    default="pending", max_length=10,
                )),
                ("coverage_percent", models.PositiveSmallIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("patient", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="hmo_cards",
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={"ordering": ["-created_at"]},
        ),
    ]
