"""
payouts/serializers.py

Serializers for the payout request system.
"""

from decimal import Decimal

from rest_framework import serializers

from .models import Payout


class PayoutSerializer(serializers.ModelSerializer):
    """Full payout detail — used for list and retrieve."""

    doctor_name   = serializers.SerializerMethodField()
    reviewed_by_name = serializers.SerializerMethodField()

    class Meta:
        model  = Payout
        fields = [
            "id", "doctor", "doctor_name",
            "amount", "method", "account_name", "account_number", "bank_name",
            "status",
            "reviewed_by", "reviewed_by_name", "reviewed_at",
            "rejection_reason", "payout_reference", "admin_notes",
            "period_start", "period_end",
            "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "doctor", "status",
            "reviewed_by", "reviewed_at",
            "rejection_reason", "payout_reference", "admin_notes",
            "created_at", "updated_at",
        ]

    def get_doctor_name(self, obj):
        return f"Dr. {obj.doctor.first_name} {obj.doctor.last_name}".strip()

    def get_reviewed_by_name(self, obj):
        if not obj.reviewed_by:
            return None
        return f"{obj.reviewed_by.first_name} {obj.reviewed_by.last_name}".strip()


class PayoutRequestSerializer(serializers.Serializer):
    """
    Doctor submits a payout request.

    The amount is validated against the doctor's available (unpaid) earnings:
      available = sum(doctor_earnings) for completed+paid online appointments
                  that are NOT already covered by a pending/approved/paid payout.
    """

    amount         = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("1.00"))
    method         = serializers.ChoiceField(choices=Payout.METHOD_CHOICES, default="gcash")
    account_name   = serializers.CharField(max_length=200)
    account_number = serializers.CharField(max_length=100)
    bank_name      = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")
    period_start   = serializers.DateField(required=False, allow_null=True)
    period_end     = serializers.DateField(required=False, allow_null=True)

    def validate_amount(self, value):
        request = self.context["request"]
        available = _get_available_earnings(request.user)
        if value > available:
            raise serializers.ValidationError(
                f"Requested amount ₱{value:,.2f} exceeds available earnings ₱{available:,.2f}."
            )
        return value


class PayoutApproveSerializer(serializers.Serializer):
    """Admin approves a payout and records the transfer reference."""

    payout_reference = serializers.CharField(max_length=200)
    admin_notes      = serializers.CharField(required=False, allow_blank=True, default="")


class PayoutRejectSerializer(serializers.Serializer):
    """Admin rejects a payout with a reason."""

    rejection_reason = serializers.CharField(min_length=5, max_length=500)


class DoctorEarningsSummarySerializer(serializers.Serializer):
    """
    Doctor dashboard earnings summary.
    Returned by GET /payouts/earnings/
    """
    total_gross        = serializers.DecimalField(max_digits=12, decimal_places=2)
    total_commission   = serializers.DecimalField(max_digits=12, decimal_places=2)
    total_earnings     = serializers.DecimalField(max_digits=12, decimal_places=2)
    available_earnings = serializers.DecimalField(max_digits=12, decimal_places=2)
    paid_out           = serializers.DecimalField(max_digits=12, decimal_places=2)
    pending_payout     = serializers.DecimalField(max_digits=12, decimal_places=2)
    completed_count    = serializers.IntegerField()
    commission_rate    = serializers.CharField()
    today_earnings     = serializers.DecimalField(max_digits=12, decimal_places=2)
    today_commission   = serializers.DecimalField(max_digits=12, decimal_places=2)
    today_consults     = serializers.IntegerField()
    week_earnings      = serializers.DecimalField(max_digits=12, decimal_places=2)
    week_commission    = serializers.DecimalField(max_digits=12, decimal_places=2)
    week_consults      = serializers.IntegerField()
    breakdown          = serializers.ListField(child=serializers.DictField())


class AdminRevenueSummarySerializer(serializers.Serializer):
    """
    Admin dashboard revenue summary.
    Returned by GET /payouts/admin/revenue/
    """
    period             = serializers.CharField()
    total_revenue      = serializers.DecimalField(max_digits=12, decimal_places=2)
    total_gross        = serializers.DecimalField(max_digits=12, decimal_places=2)
    total_appointments = serializers.IntegerField()
    breakdown          = serializers.ListField(child=serializers.DictField())


# ── Internal helper ───────────────────────────────────────────────────────────

def _get_available_earnings(doctor_user) -> Decimal:
    """
    Returns the doctor's available (not-yet-requested) earnings.

    available = total doctor_earnings (completed + paid online appointments)
              - amount already in pending/approved/paid payout requests
    """
    from decimal import Decimal
    from django.db.models import Sum
    from appointments.models import Appointment

    total_earned = (
        Appointment.objects
        .filter(
            doctor=doctor_user,
            status="completed",
            payment_status="paid",
            type__in=("online", "on_demand"),
        )
        .exclude(doctor_earnings=None)
        .aggregate(total=Sum("doctor_earnings"))["total"]
    ) or Decimal("0.00")

    already_requested = (
        Payout.objects
        .filter(doctor=doctor_user, status__in=("pending", "approved", "paid"))
        .aggregate(total=Sum("amount"))["total"]
    ) or Decimal("0.00")

    return max(Decimal("0.00"), total_earned - already_requested)
