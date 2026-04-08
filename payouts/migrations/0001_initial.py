import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Payout",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("amount", models.DecimalField(decimal_places=2, max_digits=12, help_text="Total payout amount requested.")),
                ("method", models.CharField(choices=[("gcash", "GCash"), ("bank_transfer", "Bank Transfer"), ("maya", "Maya"), ("other", "Other")], default="gcash", max_length=20)),
                ("account_name",  models.CharField(blank=True, max_length=200)),
                ("account_number", models.CharField(blank=True, max_length=100)),
                ("bank_name",     models.CharField(blank=True, max_length=100)),
                ("status", models.CharField(choices=[("pending", "Pending"), ("approved", "Approved"), ("rejected", "Rejected"), ("paid", "Paid")], db_index=True, default="pending", max_length=10)),
                ("reviewed_at",       models.DateTimeField(blank=True, null=True)),
                ("rejection_reason",  models.TextField(blank=True)),
                ("payout_reference",  models.CharField(blank=True, max_length=200)),
                ("admin_notes",       models.TextField(blank=True)),
                ("period_start",      models.DateField(blank=True, null=True)),
                ("period_end",        models.DateField(blank=True, null=True)),
                ("created_at",        models.DateTimeField(auto_now_add=True)),
                ("updated_at",        models.DateTimeField(auto_now=True)),
                (
                    "doctor",
                    models.ForeignKey(
                        limit_choices_to={"role": "doctor"},
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="payout_requests",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "reviewed_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="payout_reviews",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={"verbose_name": "Payout", "verbose_name_plural": "Payouts", "ordering": ["-created_at"]},
        ),
        migrations.AddIndex(
            model_name="payout",
            index=models.Index(fields=["doctor", "status", "-created_at"], name="payout_doctor_status_idx"),
        ),
        migrations.AddIndex(
            model_name="payout",
            index=models.Index(fields=["status", "-created_at"], name="payout_status_created_idx"),
        ),
    ]
