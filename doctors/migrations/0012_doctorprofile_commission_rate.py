"""
Migration: add commission_rate to DoctorProfile.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("doctors", "0011_alter_doctorprofile_profile_photo_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="doctorprofile",
            name="commission_rate",
            field=models.DecimalField(
                decimal_places=2,
                default=15.0,
                help_text="Platform commission % deducted from online consultation fees. Default: 15%.",
                max_digits=5,
            ),
        ),
    ]
