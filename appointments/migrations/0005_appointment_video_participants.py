from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("appointments", "0004_video_consultation_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="appointment",
            name="video_participants",
            field=models.JSONField(blank=True, default=list),
        ),
    ]
