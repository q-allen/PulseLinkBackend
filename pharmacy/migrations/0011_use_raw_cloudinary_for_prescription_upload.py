import cloudinary_storage.storage
import pharmacy.models
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pharmacy', '0010_alter_pharmacyprescriptionupload_file'),
    ]

    operations = [
        migrations.AlterField(
            model_name='pharmacyprescriptionupload',
            name='file',
            field=models.FileField(
                max_length=500,
                storage=cloudinary_storage.storage.RawMediaCloudinaryStorage(),
                upload_to=pharmacy.models._rx_upload_path,
            ),
        ),
    ]
