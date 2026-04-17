from rest_framework import serializers
from .models import Medicine, Order, PharmacyPrescriptionUpload

# Payment methods that route through PayMongo Checkout
ONLINE_PAYMENT_METHODS = frozenset({
    "gcash", "card", "paymaya", "grab_pay",
    "qrph", "billease", "dob", "bank_transfer",
})


class MedicineWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Medicine
        fields = [
            "name", "generic_name", "category", "price", "description",
            "dosage_form", "manufacturer", "requires_prescription", "prescription_note",
            "in_stock", "quantity", "image", "pharmacy_partner",
        ]


class MedicineSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()

    class Meta:
        model  = Medicine
        fields = [
            "id", "name", "generic_name", "category", "price", "description",
            "dosage_form", "manufacturer", "requires_prescription", "prescription_note",
            "in_stock", "quantity", "image_url", "pharmacy_partner",
        ]

    def get_image_url(self, obj):
        request = self.context.get("request")
        if obj.image and request:
            return request.build_absolute_uri(obj.image.url)
        return None


class PrescriptionUploadSerializer(serializers.ModelSerializer):
    file_url = serializers.SerializerMethodField()

    class Meta:
        model  = PharmacyPrescriptionUpload
        fields = ["id", "file", "file_url", "status", "notes", "order", "created_at"]
        read_only_fields = ["id", "status", "notes", "created_at"]

    def get_file_url(self, obj):
        request = self.context.get("request")
        if obj.file and obj.pk:
            proxy_path = f"/api/pharmacy/prescriptions/upload/{obj.pk}/file"
            return request.build_absolute_uri(proxy_path) if request else proxy_path
        return None


class OrderSerializer(serializers.ModelSerializer):
    """
    Read serializer returned on list / detail / after create.
    checkout_url is injected by the view after a PayMongo session is created;
    it is not stored on the model so it only appears on the create response.
    """
    checkout_url        = serializers.SerializerMethodField()
    prescription_upload = serializers.SerializerMethodField()

    class Meta:
        model  = Order
        fields = [
            "id", "patient", "items", "total_amount", "status",
            "delivery_address", "payment_method", "prescription",
            "order_ref", "tracking_number", "from_prescription",
            # PayMongo
            "paymongo_checkout_id", "payment_status", "payment_method_type",
            "checkout_url", "prescription_upload",
            "created_at", "updated_at",
        ]
        read_only_fields = fields

    def get_checkout_url(self, obj):
        return self.context.get("checkout_url")

    def get_prescription_upload(self, obj):
        try:
            upload = obj.prescription_upload
            file_url = None
            if upload.file:
                request = self.context.get("request")
                proxy_path = f"/api/pharmacy/prescriptions/upload/{upload.pk}/file/"
                file_url = request.build_absolute_uri(proxy_path) if request else proxy_path
            return {"id": upload.pk, "status": upload.status, "file_url": file_url}
        except PharmacyPrescriptionUpload.DoesNotExist:
            return None


class OrderFromPrescriptionSerializer(serializers.Serializer):
    """Write serializer for POST /pharmacy/orders/from-prescription/."""
    prescription_id  = serializers.IntegerField()
    delivery_address = serializers.CharField()
    payment_method   = serializers.CharField(default="cod")

    def validate_payment_method(self, value):
        allowed = {"cod"} | ONLINE_PAYMENT_METHODS
        if value not in allowed:
            raise serializers.ValidationError(
                f"payment_method must be one of: {', '.join(sorted(allowed))}"
            )
        return value


class AdminOrderStatusSerializer(serializers.Serializer):
    """Write serializer for PATCH /pharmacy/orders/<id>/status/ (admin only)."""
    tracking_number = serializers.CharField(required=False, allow_blank=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from .models import Order
        self.fields["status"] = serializers.ChoiceField(
            choices=[c[0] for c in Order.STATUS_CHOICES], required=False
        )


class PlaceOrderSerializer(serializers.Serializer):
    """Write serializer for POST /pharmacy/orders."""

    items                  = serializers.ListField(child=serializers.DictField(), min_length=1)
    delivery_address       = serializers.CharField()
    payment_method         = serializers.CharField()
    prescription_id        = serializers.IntegerField(required=False, allow_null=True)
    prescription_upload_id = serializers.IntegerField(required=False, allow_null=True)
    total_amount           = serializers.DecimalField(max_digits=10, decimal_places=2)

    def validate_payment_method(self, value):
        allowed = {"cod"} | ONLINE_PAYMENT_METHODS
        if value not in allowed:
            raise serializers.ValidationError(
                f"payment_method must be one of: {', '.join(sorted(allowed))}"
            )
        return value

    def validate_items(self, items):
        required_keys = ("medicine_id", "name", "quantity", "price")
        for item in items:
            for key in required_keys:
                if key not in item:
                    raise serializers.ValidationError(
                        f"Each item must include '{key}'."
                    )
            try:
                if int(item["quantity"]) < 1:
                    raise serializers.ValidationError("Item quantity must be ≥ 1.")
                if float(item["price"]) <= 0:
                    raise serializers.ValidationError("Item price must be > 0.")
            except (TypeError, ValueError):
                raise serializers.ValidationError("Item quantity and price must be numeric.")
        return items

    def validate(self, data):
        """Block checkout if any item requires a prescription but none is provided."""
        items = data.get("items", [])
        rx_medicine_ids = [
            item["medicine_id"] for item in items
            if item.get("medicine_id") is not None
        ]
        if rx_medicine_ids:
            from .models import Medicine as Med
            rx_required = Med.objects.filter(
                pk__in=rx_medicine_ids, requires_prescription=True
            ).exists()
            if rx_required and not data.get("prescription_id") and not data.get("prescription_upload_id"):
                raise serializers.ValidationError(
                    {"prescription_id": "One or more items require a prescription. "
                     "Please upload a prescription or link an existing one."}
                )
        return data


class PrescriptionUploadWriteSerializer(serializers.Serializer):
    """Write serializer for POST /pharmacy/prescriptions/upload/."""
    file     = serializers.FileField()
    order_id = serializers.IntegerField(required=False, allow_null=True)

    def validate_file(self, value):
        allowed_types = {"image/jpeg", "image/png", "image/webp", "application/pdf"}
        if value.content_type not in allowed_types:
            raise serializers.ValidationError("Only JPG, PNG, WebP, or PDF files are allowed.")
        if value.size > 10 * 1024 * 1024:
            raise serializers.ValidationError("File size must not exceed 10MB.")
        return value
