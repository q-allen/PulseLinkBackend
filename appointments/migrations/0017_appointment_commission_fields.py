"""
Migration: add doctor_earnings and platform_commission to Appointment.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("appointments", "0016_follow_up_invitation"),
    ]

    operations = [
        migrations.AddField(
            model_name="appointment",
            name="doctor_earnings",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="Net amount the doctor receives after platform commission.",
                max_digits=10,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="appointment",
            name="platform_commission",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="15% platform fee deducted from online consultation fee.",
                max_digits=10,
                null=True,
            ),
        ),
    ]
