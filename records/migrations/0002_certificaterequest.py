"""Migration: add CertificateRequest + pdf_file to MedicalCertificate."""
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("records", "0001_initial"),
        ("appointments", "0003_review_homeservice_appointment_upgrades"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="medicalcertificate",
            name="pdf_file",
            field=models.FileField(blank=True, null=True, upload_to="certificates/"),
        ),
        migrations.CreateModel(
            name="CertificateRequest",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("purpose", models.CharField(max_length=300)),
                ("notes", models.TextField(blank=True)),
                ("status", models.CharField(
                    choices=[("pending", "Pending"), ("approved", "Approved"), ("rejected", "Rejected")],
                    default="pending", max_length=10,
                )),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("appointment", models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="cert_requests",
                    to="appointments.appointment",
                )),
                ("certificate", models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="request",
                    to="records.medicalcertificate",
                )),
                ("doctor", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="cert_requests_received",
                    to=settings.AUTH_USER_MODEL,
                )),
                ("patient", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="cert_requests",
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={"ordering": ["-created_at"]},
        ),
    ]
