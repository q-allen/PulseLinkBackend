from django.db import migrations, models


def set_initial_face_status(apps, schema_editor):
    DoctorProfile = apps.get_model("doctors", "DoctorProfile")
    DoctorProfile.objects.filter(is_face_verified=True).update(
        face_verification_status="verified"
    )


class Migration(migrations.Migration):

    dependencies = [
        ("doctors", "0015_doctorprofile_face_front_doctorprofile_face_left_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="doctorprofile",
            name="face_verification_status",
            field=models.CharField(
                choices=[
                    ("pending", "Pending"),
                    ("verified", "Verified"),
                    ("manual_review", "Manual Review"),
                    ("admin_override", "Admin Override"),
                ],
                default="pending",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="doctorprofile",
            name="face_verification_error",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.RunPython(set_initial_face_status, migrations.RunPython.noop),
    ]
