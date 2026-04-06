from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("doctors", "0009_invite_proxy"),
    ]

    operations = [
        migrations.AddField(
            model_name="doctorprofile",
            name="clinic_lat",
            field=models.DecimalField(
                max_digits=9, decimal_places=6,
                null=True, blank=True,
                help_text="Latitude of clinic pin set via Google Maps.",
            ),
        ),
        migrations.AddField(
            model_name="doctorprofile",
            name="clinic_lng",
            field=models.DecimalField(
                max_digits=9, decimal_places=6,
                null=True, blank=True,
                help_text="Longitude of clinic pin set via Google Maps.",
            ),
        ),
    ]
