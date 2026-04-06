from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("pharmacy", "0002_order_paymongo"),
    ]

    operations = [
        # 1. Rename paymongo_session_id → paymongo_checkout_id
        migrations.RenameField(
            model_name="order",
            old_name="paymongo_session_id",
            new_name="paymongo_checkout_id",
        ),
        # 2. Make paymongo_checkout_id nullable + blank (was blank=True, default="")
        migrations.AlterField(
            model_name="order",
            name="paymongo_checkout_id",
            field=models.CharField(blank=True, max_length=100, null=True),
        ),
        # 3. Expand payment_status choices + widen to max_length=20
        migrations.AlterField(
            model_name="order",
            name="payment_status",
            field=models.CharField(
                choices=[
                    ("pending",   "Pending"),
                    ("paid",      "Paid"),
                    ("failed",    "Failed"),
                    ("cancelled", "Cancelled"),
                    ("refunded",  "Refunded"),
                ],
                default="pending",
                max_length=20,
            ),
        ),
        # 4. Widen payment_method_type to 50 chars + make nullable
        migrations.AlterField(
            model_name="order",
            name="payment_method_type",
            field=models.CharField(blank=True, max_length=50, null=True),
        ),
        # 5. Add composite index on (patient, status) for order list queries
        migrations.AddIndex(
            model_name="order",
            index=models.Index(fields=["patient", "status"], name="pharmacy_order_patient_status_idx"),
        ),
        # 6. Add index on paymongo_checkout_id for webhook lookups
        migrations.AddIndex(
            model_name="order",
            index=models.Index(fields=["paymongo_checkout_id"], name="pharmacy_order_checkout_id_idx"),
        ),
    ]
