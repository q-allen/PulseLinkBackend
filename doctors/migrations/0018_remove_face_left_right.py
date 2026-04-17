from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("doctors", "0017_alter_doctorprofile_face_verification_error_and_more"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="doctorprofile",
            name="face_left",
        ),
        migrations.RemoveField(
            model_name="doctorprofile",
            name="face_right",
        ),
    ]
