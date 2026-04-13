import cloudinary_storage.storage
import pharmacy.models
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pharmacy', '0008_alter_medicine_image_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='pharmacyprescriptionupload',
            name='file',
            field=models.FileField(
                max_length=500,
                upload_to=pharmacy.models._rx_upload_path,
                storage=cloudinary_storage.storage.RawMediaCloudinaryStorage(),
            ),
        ),
    ]
