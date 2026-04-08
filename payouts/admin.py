"""
payouts/admin.py
"""

from django.contrib import admin
from django.utils import timezone

from .models import Payout


@admin.register(Payout)
class PayoutAdmin(admin.ModelAdmin):
    list_display  = [
        "id", "doctor_name", "amount", "method",
        "status", "payout_reference", "reviewed_by", "created_at",
    ]
    list_filter   = ["status", "method", "created_at"]
    search_fields = ["doctor__first_name", "doctor__last_name", "doctor__email", "payout_reference"]
    readonly_fields = ["created_at", "updated_at", "reviewed_at"]
    ordering      = ["-created_at"]

    fieldsets = [
        ("Request", {
            "fields": ["doctor", "amount", "method", "account_name", "account_number", "bank_name", "period_start", "period_end"],
        }),
        ("Status", {
            "fields": ["status", "payout_reference", "rejection_reason"],
        }),
        ("Admin", {
            "fields": ["reviewed_by", "reviewed_at", "admin_notes"],
        }),
        ("Timestamps", {
            "fields": ["created_at", "updated_at"],
            "classes": ["collapse"],
        }),
    ]

    actions = ["approve_payouts", "reject_payouts"]

    @admin.display(description="Doctor")
    def doctor_name(self, obj):
        return f"Dr. {obj.doctor.first_name} {obj.doctor.last_name}".strip()

    @admin.action(description="Approve selected payouts")
    def approve_payouts(self, request, queryset):
        pending = queryset.filter(status="pending")
        count = pending.update(
            status="paid",
            reviewed_by=request.user,
            reviewed_at=timezone.now(),
        )
        self.message_user(request, f"{count} payout(s) approved.")

    @admin.action(description="Reject selected payouts")
    def reject_payouts(self, request, queryset):
        pending = queryset.filter(status="pending")
        count = pending.update(
            status="rejected",
            reviewed_by=request.user,
            reviewed_at=timezone.now(),
            rejection_reason="Rejected via bulk admin action.",
        )
        self.message_user(request, f"{count} payout(s) rejected.")
