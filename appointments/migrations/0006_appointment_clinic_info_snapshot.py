from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("appointments", "0006_appointment_consult_notes_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="appointment",
            name="clinic_info_snapshot",
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text="Snapshot of clinic_name/clinic_address/city at booking time (in_clinic only).",
            ),
        ),
    ]
