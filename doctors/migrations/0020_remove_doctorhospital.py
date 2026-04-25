from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("doctors", "0019_alter_doctorprofile_face_front"),
    ]

    operations = [
        migrations.DeleteModel(
            name="DoctorHospital",
        ),
    ]
