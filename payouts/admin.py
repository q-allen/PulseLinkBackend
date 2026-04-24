"""
payouts/admin.py

Rich Django admin for the PulseLink payout system.

Features:
  - Color-coded status badges (pending=yellow, paid=green, rejected=red)
  - Bulk approve / reject actions
  - Per-doctor earnings summary inline
  - Platform revenue summary at the top of the changelist
  - Date-range filters (today / this week / this month)
"""

from decimal import Decimal

from django.contrib import admin, messages
from django.db.models import Sum, Count, Q
from django.utils import timezone
from django.utils.html import format_html

from .models import Payout


# ── Inline: per-doctor earnings summary ──────────────────────────────────────

class PayoutInline(admin.TabularInline):
    """Show a doctor's payout history inline on the User admin page."""
    model = Payout
    extra = 0
    fields = ["amount", "method", "status", "payout_reference", "created_at"]
    readonly_fields = ["amount", "method", "status", "payout_reference", "created_at"]
    can_delete = False
    show_change_link = True
    verbose_name = "Payout Request"
    verbose_name_plural = "Payout History"


# ── Main Payout admin ─────────────────────────────────────────────────────────

@admin.register(Payout)
class PayoutAdmin(admin.ModelAdmin):
    """
    Full payout management for PulseLink admins.

    Workflow:
      1. Doctor submits payout request → status=pending
      2. Admin reviews here → bulk approve or reject
      3. On approval: enter payout_reference (GCash/bank ref number)
      4. Status → paid, doctor is notified automatically
    """

    list_display = [
        "id",
        "colored_status",
        "doctor_name_link",
        "amount_display",
        "method_display",
        "account_info",
        "payout_reference",
        "reviewed_by",
        "created_at",
    ]
    list_display_links = ["id", "colored_status"]
    list_filter  = ["status", "method", "created_at", "doctor"]
    search_fields = [
        "doctor__first_name", "doctor__last_name", "doctor__email",
        "payout_reference", "account_number",
    ]
    readonly_fields = [
        "created_at", "updated_at", "reviewed_at",
    ]
    ordering = ["-created_at"]
    date_hierarchy = "created_at"
    list_per_page = 25
    change_form_template = "admin/payouts/payout/change_form.html"

    fieldsets = [
        ("Payout Request", {
            "fields": [
                "doctor",
                "amount", "method",
                "account_name", "account_number", "bank_name",
                "period_start", "period_end",
            ],
        }),
        ("Status & Review", {
            "fields": [
                "status",
                "payout_reference",
                "rejection_reason",
                "reviewed_by",
                "reviewed_at",
                "admin_notes",
            ],
        }),
        ("Timestamps", {
            "fields": ["created_at", "updated_at"],
            "classes": ["collapse"],
        }),
    ]

    actions = ["action_approve", "action_reject"]

    # ── Change view: inject earnings + payout history + breakdown ─────────────

    def change_view(self, request, object_id, form_url="", extra_context=None):
        extra_context = extra_context or {}
        from appointments.models import Appointment

        try:
            payout = Payout.objects.select_related("doctor").get(pk=object_id)
        except Payout.DoesNotExist:
            return super().change_view(request, object_id, form_url, extra_context)

        doctor = payout.doctor

        # ── Summary stats ─────────────────────────────────────────────────────
        agg = (
            Appointment.objects
            .filter(
                doctor=doctor,
                status="completed",
                payment_status="paid",
                type__in=("online", "on_demand"),
            )
            .exclude(doctor_earnings=None)
            .aggregate(
                total_gross=Sum("fee"),
                total_commission=Sum("platform_commission"),
                total_earnings=Sum("doctor_earnings"),
                count=Count("id"),
            )
        )
        total_earnings = agg["total_earnings"] or Decimal("0.00")
        paid_out = (
            Payout.objects
            .filter(doctor=doctor, status__in=("approved", "paid"))
            .aggregate(t=Sum("amount"))["t"]
        ) or Decimal("0.00")
        pending_amt = (
            Payout.objects
            .filter(doctor=doctor, status="pending")
            .aggregate(t=Sum("amount"))["t"]
        ) or Decimal("0.00")
        available = max(Decimal("0.00"), total_earnings - paid_out - pending_amt)

        extra_context["earnings_stats"] = {
            "doctor_name":      f"Dr. {doctor.first_name} {doctor.last_name}".strip(),
            "consult_count":    agg["count"] or 0,
            "total_gross":      agg["total_gross"]      or Decimal("0.00"),
            "total_commission": agg["total_commission"] or Decimal("0.00"),
            "total_earnings":   total_earnings,
            "paid_out":         paid_out,
            "pending":          pending_amt,
            "available":        available,
        }

        # ── Payout history ────────────────────────────────────────────────────
        extra_context["payout_history"] = (
            Payout.objects
            .filter(doctor=doctor)
            .order_by("-created_at")
            .values(
                "id", "amount", "method", "status",
                "payout_reference", "rejection_reason", "created_at",
            )
        )

        # ── Appointment earnings breakdown ────────────────────────────────────
        extra_context["earnings_breakdown"] = (
            Appointment.objects
            .filter(
                doctor=doctor,
                status="completed",
                payment_status="paid",
                type__in=("online", "on_demand"),
            )
            .exclude(doctor_earnings=None)
            .order_by("-date")
            .values(
                "id", "date", "type", "fee",
                "platform_commission", "doctor_earnings",
            )
        )

        return super().change_view(request, object_id, form_url, extra_context)

    # ── List display helpers ──────────────────────────────────────────────────

    @admin.display(description="Status", ordering="status")
    def colored_status(self, obj):
        colors = {
            "pending":  ("#f59e0b", "#fffbeb", "⏳ Pending"),
            "approved": ("#10b981", "#ecfdf5", "✓ Approved"),
            "paid":     ("#0d9488", "#f0fdfa", "✅ Paid"),
            "rejected": ("#ef4444", "#fef2f2", "✗ Rejected"),
        }
        color, bg, label = colors.get(obj.status, ("#6b7280", "#f9fafb", obj.status))
        return format_html(
            '<span style="color:{};background:{};padding:3px 10px;border-radius:12px;'
            'font-size:12px;font-weight:600;white-space:nowrap;">{}</span>',
            color, bg, label,
        )

    @admin.display(description="Doctor", ordering="doctor__last_name")
    def doctor_name_link(self, obj):
        return format_html(
            '<strong>Dr. {} {}</strong><br><small style="color:#6b7280">{}</small>',
            obj.doctor.first_name,
            obj.doctor.last_name,
            obj.doctor.email,
        )

    @admin.display(description="Amount (PHP)", ordering="amount")
    def amount_display(self, obj):
        return format_html(
            '<span style="font-weight:700;color:#0d9488;font-size:15px;">₱{}</span>',
            f"{obj.amount:,.2f}",
        )

    @admin.display(description="Method")
    def method_display(self, obj):
        icons = {"gcash": "📱", "bank_transfer": "🏦", "maya": "💳", "other": "💰"}
        return f"{icons.get(obj.method, '💰')} {obj.get_method_display()}"

    @admin.display(description="Account")
    def account_info(self, obj):
        if obj.account_number:
            return format_html(
                '{}<br><small style="color:#6b7280">{}</small>',
                obj.account_name or "—",
                obj.account_number,
            )
        return obj.account_name or "—"

    # ── Bulk actions ──────────────────────────────────────────────────────────

    @admin.action(description="✅ Approve selected pending payouts")
    def action_approve(self, request, queryset):
        pending = queryset.filter(status="pending")
        count = pending.update(
            status="paid",
            reviewed_by=request.user,
            reviewed_at=timezone.now(),
        )
        # Send notifications (best-effort)
        for payout in pending:
            try:
                from notifications.models import Notification
                Notification.objects.create(
                    user=payout.doctor,
                    type="payout",
                    title="Payout Approved ✅",
                    message=(
                        f"Your payout of ₱{payout.amount:,.2f} has been approved. "
                        f"Funds will be transferred via {payout.get_method_display()}."
                    ),
                    data={"payout_id": payout.pk},
                )
            except Exception:
                pass
        self.message_user(request, f"{count} payout(s) approved.", messages.SUCCESS)

    @admin.action(description="✗ Reject selected pending payouts")
    def action_reject(self, request, queryset):
        pending = queryset.filter(status="pending")
        count = pending.update(
            status="rejected",
            reviewed_by=request.user,
            reviewed_at=timezone.now(),
            rejection_reason="Rejected via bulk admin action. Please contact admin for details.",
        )
        for payout in pending:
            try:
                from notifications.models import Notification
                Notification.objects.create(
                    user=payout.doctor,
                    type="payout",
                    title="Payout Request Rejected",
                    message=(
                        f"Your payout request of ₱{payout.amount:,.2f} was rejected. "
                        f"Your earnings remain available. Please contact admin for details."
                    ),
                    data={"payout_id": payout.pk},
                )
            except Exception:
                pass
        self.message_user(request, f"{count} payout(s) rejected.", messages.WARNING)

    # ── Changelist: inject platform revenue summary at top ────────────────────

    def changelist_view(self, request, extra_context=None):
        """Inject platform revenue summary or per-doctor summary depending on filter."""
        from appointments.models import Appointment
        from django.urls import reverse as _reverse

        extra_context = extra_context or {}

        # Detect if filtered to a specific doctor
        doctor_id = request.GET.get("doctor__id__exact")

        if doctor_id:
            # ── Per-doctor view ───────────────────────────────────────────────
            try:
                from users.models import User
                doctor = User.objects.get(pk=doctor_id)
            except User.DoesNotExist:
                doctor = None

            if doctor:
                agg = (
                    Appointment.objects
                    .filter(
                        doctor=doctor,
                        status="completed",
                        payment_status="paid",
                        type__in=("online", "on_demand"),
                    )
                    .exclude(doctor_earnings=None)
                    .aggregate(
                        total_gross=Sum("fee"),
                        total_commission=Sum("platform_commission"),
                        total_earnings=Sum("doctor_earnings"),
                        count=Count("id"),
                    )
                )
                total_earnings = agg["total_earnings"] or Decimal("0.00")

                paid_out = (
                    Payout.objects
                    .filter(doctor=doctor, status__in=("approved", "paid"))
                    .aggregate(t=Sum("amount"))["t"]
                ) or Decimal("0.00")
                pending = (
                    Payout.objects
                    .filter(doctor=doctor, status="pending")
                    .aggregate(t=Sum("amount"))["t"]
                ) or Decimal("0.00")
                available = max(Decimal("0.00"), total_earnings - paid_out - pending)

                extra_context["doctor_detail"] = {
                    "name":             f"Dr. {doctor.first_name} {doctor.last_name}".strip(),
                    "email":            doctor.email,
                    "consult_count":    agg["count"] or 0,
                    "total_gross":      agg["total_gross"]      or Decimal("0.00"),
                    "total_commission": agg["total_commission"] or Decimal("0.00"),
                    "total_earnings":   total_earnings,
                    "paid_out":         paid_out,
                    "pending":          pending,
                    "available":        available,
                    "back_url":         _reverse("admin:payouts_payout_changelist"),
                }
                extra_context["earnings_stats"] = extra_context["doctor_detail"]
                extra_context["payout_history"] = list(
                    Payout.objects.filter(doctor=doctor).order_by("-created_at")
                    .values("id", "amount", "method", "status", "payout_reference", "rejection_reason", "created_at")
                )
                extra_context["earnings_breakdown"] = list(
                    Appointment.objects
                    .filter(doctor=doctor, status="completed", payment_status="paid", type__in=("online", "on_demand"))
                    .exclude(doctor_earnings=None).order_by("-date")
                    .values("id", "date", "type", "fee", "platform_commission", "doctor_earnings")
                )
                extra_context["doctor_rows"] = []
                extra_context["revenue_summary"] = None

        else:
            # ── Platform-wide view ────────────────────────────────────────────
            agg = (
                Appointment.objects
                .filter(
                    status="completed",
                    payment_status="paid",
                    type__in=("online", "on_demand"),
                )
                .exclude(platform_commission=None)
                .aggregate(
                    total_revenue=Sum("platform_commission"),
                    total_gross=Sum("fee"),
                    total_count=Count("id"),
                )
            )

            today = timezone.localdate()
            month_start = today.replace(day=1)
            month_agg = (
                Appointment.objects
                .filter(
                    status="completed",
                    payment_status="paid",
                    type__in=("online", "on_demand"),
                    date__gte=month_start,
                )
                .exclude(platform_commission=None)
                .aggregate(
                    revenue=Sum("platform_commission"),
                    count=Count("id"),
                )
            )

            payout_agg = Payout.objects.aggregate(
                total_paid=Sum("amount", filter=Q(status__in=("approved", "paid"))),
                total_pending=Sum("amount", filter=Q(status="pending")),
                count_pending=Count("id", filter=Q(status="pending")),
            )

            extra_context["revenue_summary"] = {
                "total_revenue": agg["total_revenue"]        or Decimal("0.00"),
                "total_gross":   agg["total_gross"]          or Decimal("0.00"),
                "total_count":   agg["total_count"]          or 0,
                "month_revenue": month_agg["revenue"]        or Decimal("0.00"),
                "month_count":   month_agg["count"]          or 0,
                "total_paid_out":payout_agg["total_paid"]    or Decimal("0.00"),
                "total_pending": payout_agg["total_pending"] or Decimal("0.00"),
                "count_pending": payout_agg["count_pending"] or 0,
            }

            doctors_qs = (
                Appointment.objects
                .filter(
                    status="completed",
                    payment_status="paid",
                    type__in=("online", "on_demand"),
                )
                .exclude(doctor_earnings=None)
                .values("doctor", "doctor__first_name", "doctor__last_name", "doctor__email")
                .annotate(
                    total_gross=Sum("fee"),
                    total_commission=Sum("platform_commission"),
                    total_earnings=Sum("doctor_earnings"),
                    consult_count=Count("id"),
                )
                .order_by("-total_earnings")
            )

            doctor_rows = []
            for row in doctors_qs:
                did = row["doctor"]
                paid_out = (
                    Payout.objects
                    .filter(doctor_id=did, status__in=("approved", "paid"))
                    .aggregate(t=Sum("amount"))["t"]
                ) or Decimal("0.00")
                pending = (
                    Payout.objects
                    .filter(doctor_id=did, status="pending")
                    .aggregate(t=Sum("amount"))["t"]
                ) or Decimal("0.00")
                total_earnings = row["total_earnings"] or Decimal("0.00")
                available = max(Decimal("0.00"), total_earnings - paid_out - pending)
                doctor_rows.append({
                    "id":               did,
                    "name":             f"Dr. {row['doctor__first_name']} {row['doctor__last_name']}".strip(),
                    "email":            row["doctor__email"],
                    "consult_count":    row["consult_count"],
                    "total_gross":      row["total_gross"]      or Decimal("0.00"),
                    "total_commission": row["total_commission"] or Decimal("0.00"),
                    "total_earnings":   total_earnings,
                    "paid_out":         paid_out,
                    "pending":          pending,
                    "available":        available,
                    "payout_url":       _reverse("admin:payouts_payout_changelist") + f"?doctor__id__exact={did}",
                })
            extra_context["doctor_rows"] = doctor_rows
            extra_context["earnings_stats"] = None
            extra_context["payout_history"] = None
            extra_context["earnings_breakdown"] = None

        return super().changelist_view(request, extra_context=extra_context)

