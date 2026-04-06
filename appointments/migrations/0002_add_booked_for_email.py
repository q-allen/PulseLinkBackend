# Generated migration for adding booked_for_email field

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('appointments', '0001_initial'),  # Update this to your latest migration
    ]

    operations = [
        migrations.AddField(
            model_name='appointment',
            name='booked_for_email',
            field=models.EmailField(blank=True, help_text='Email of the person being seen (optional, for sending appointment notifications).', max_length=254),
        ),
    ]
