from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("pharmacy", "0006_prescription_upload_and_medicine_note"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="order",
            name="delivery_status",
        ),
    ]
