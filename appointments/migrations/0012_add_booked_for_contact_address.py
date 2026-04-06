# Generated migration for adding booked_for_contact and booked_for_address fields

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('appointments', '0011_merge_20260403_1411'),
    ]

    operations = [
        migrations.AddField(
            model_name='appointment',
            name='booked_for_contact',
            field=models.CharField(
                blank=True,
                max_length=20,
                help_text='Contact number of the person being seen.',
            ),
        ),
        migrations.AddField(
            model_name='appointment',
            name='booked_for_address',
            field=models.TextField(
                blank=True,
                help_text='Address of the person being seen.',
            ),
        ),
    ]
