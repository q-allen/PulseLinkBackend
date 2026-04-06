from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("appointments", "0003_review_homeservice_appointment_upgrades"),
    ]

    operations = [
        migrations.AddField(
            model_name="appointment",
            name="video_password",
            field=models.CharField(blank=True, max_length=20),
        ),
        migrations.AddField(
            model_name="appointment",
            name="video_started_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="appointment",
            name="video_ended_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
