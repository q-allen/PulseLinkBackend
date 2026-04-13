from django.conf import settings
from django.db import models
from cloudinary_storage.storage import RawMediaCloudinaryStorage


class Medicine(models.Model):
    name                  = models.CharField(max_length=200)
    generic_name          = models.CharField(max_length=200)
    category              = models.CharField(max_length=100)
    price                 = models.DecimalField(max_digits=10, decimal_places=2)
    description           = models.TextField(blank=True)
    dosage_form           = models.CharField(max_length=100, blank=True)
    manufacturer          = models.CharField(max_length=200, blank=True)
    requires_prescription = models.BooleanField(default=False)
    in_stock              = models.BooleanField(default=True)
    quantity              = models.PositiveIntegerField(default=0)
    image                 = models.ImageField(upload_to="medicines/", null=True, blank=True, max_length=500)
    pharmacy_partner      = models.CharField(max_length=200, blank=True)
    prescription_note     = models.TextField(blank=True, help_text="Instructions shown to patient when prescription is required.")

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Order(models.Model):
    STATUS_CHOICES = [
        ("pending",    "Pending"),
        ("confirmed",  "Confirmed"),
        ("processing", "Processing"),
        ("shipped",    "Shipped"),
        ("out_for_delivery", "Out for Delivery"),
        ("delivered",  "Delivered"),
        ("cancelled",  "Cancelled"),
    ]

    PAYMENT_STATUS_CHOICES = [
        ("pending",   "Pending"),
        ("paid",      "Paid"),
        ("failed",    "Failed"),
        ("cancelled", "Cancelled"),
        ("refunded",  "Refunded"),
    ]

    patient               = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="pharmacy_orders",
    )
    items                 = models.JSONField(default=list)
    # [{medicine_id, name, generic_name?, dosage_form?, quantity, price}]
    total_amount          = models.DecimalField(max_digits=10, decimal_places=2)
    status                = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    delivery_address      = models.TextField()
    payment_method        = models.CharField(max_length=20, default="cod")
    # cod | gcash | card | paymaya | grab_pay | qrph | billease | bank_transfer
    prescription          = models.ForeignKey(
        "records.Prescription",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="pharmacy_orders",
    )
    order_ref             = models.CharField(max_length=50, unique=True)
    # Delivery tracking
    tracking_number       = models.CharField(max_length=100, blank=True)
    # Flag set when order was created directly from a prescription (one-tap flow)
    from_prescription     = models.BooleanField(default=False)

    # ── PayMongo fields ───────────────────────────────────────────────────────
    paymongo_checkout_id  = models.CharField(max_length=100, blank=True, null=True)
    payment_status        = models.CharField(
        max_length=20,
        choices=PAYMENT_STATUS_CHOICES,
        default="pending",
    )
    payment_method_type   = models.CharField(max_length=50, blank=True, null=True)
    # Actual method used at checkout: gcash, card, paymaya, grab_pay, etc.

    created_at            = models.DateTimeField(auto_now_add=True)
    updated_at            = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes  = [
            models.Index(fields=["patient", "status"]),
            models.Index(fields=["paymongo_checkout_id"]),
        ]

    def __str__(self):
        return f"Order {self.order_ref} — {self.patient}"

    @property
    def is_cod(self):
        return self.payment_method == "cod"


def _rx_upload_path(instance, filename):
    return f"pharmacy/prescriptions/{instance.patient_id}/{filename}"


class PharmacyPrescriptionUpload(models.Model):
    """Patient-uploaded prescription image/PDF for a pharmacy order."""

    STATUS_CHOICES = [
        ("pending",  "Pending Review"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
    ]

    patient    = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="pharmacy_prescription_uploads",
    )
    order      = models.OneToOneField(
        Order,
        on_delete=models.CASCADE,
        null=True, blank=True,
        related_name="prescription_upload",
    )
    file       = models.FileField(upload_to=_rx_upload_path, max_length=500, storage=RawMediaCloudinaryStorage())
    status     = models.CharField(max_length=10, choices=STATUS_CHOICES, default="pending")
    notes      = models.TextField(blank=True, help_text="Admin review notes.")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"RxUpload #{self.pk} — {self.patient} [{self.status}]"
