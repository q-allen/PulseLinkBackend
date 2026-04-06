from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import pharmacy.models


class Migration(migrations.Migration):

    dependencies = [
        ("pharmacy", "0005_delivery_tracking_fields"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # Add prescription_note to Medicine
        migrations.AddField(
            model_name="medicine",
            name="prescription_note",
            field=models.TextField(
                blank=True,
                help_text="Instructions shown to patient when prescription is required.",
            ),
        ),
        # Create PharmacyPrescriptionUpload
        migrations.CreateModel(
            name="PharmacyPrescriptionUpload",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("file", models.FileField(upload_to=pharmacy.models._rx_upload_path)),
                ("status", models.CharField(
                    choices=[("pending", "Pending Review"), ("approved", "Approved"), ("rejected", "Rejected")],
                    default="pending",
                    max_length=10,
                )),
                ("notes", models.TextField(blank=True, help_text="Admin review notes.")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("patient", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="pharmacy_prescription_uploads",
                    to=settings.AUTH_USER_MODEL,
                )),
                ("order", models.OneToOneField(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="prescription_upload",
                    to="pharmacy.order",
                )),
            ],
            options={"ordering": ["-created_at"]},
        ),
    ]
