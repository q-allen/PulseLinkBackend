from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("pharmacy", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="order",
            name="paymongo_session_id",
            field=models.CharField(blank=True, default="", max_length=100),
        ),
        migrations.AddField(
            model_name="order",
            name="payment_status",
            field=models.CharField(
                choices=[("pending", "Pending"), ("paid", "Paid"), ("failed", "Failed")],
                default="pending",
                max_length=10,
            ),
        ),
        migrations.AddField(
            model_name="order",
            name="payment_method_type",
            field=models.CharField(blank=True, default="", max_length=30),
        ),
    ]
