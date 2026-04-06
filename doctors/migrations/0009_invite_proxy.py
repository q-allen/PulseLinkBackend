from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('doctors', '0008_doctorprofile_is_profile_complete'),
    ]

    operations = [
        migrations.CreateModel(
            name='DoctorInvite',
            fields=[
            ],
            options={
                'verbose_name': 'Invite Doctor',
                'verbose_name_plural': 'Invite Doctor',
                'proxy': True,
                'indexes': [],
                'constraints': [],
            },
            bases=('doctors.doctorprofile',),
        ),
    ]
