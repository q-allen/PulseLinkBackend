from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("doctors", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="doctorprofile",
            name="is_on_demand",
            field=models.BooleanField(default=False),
        ),
    ]
