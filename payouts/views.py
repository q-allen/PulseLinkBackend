"""
payouts/views.py

Payout request system for CareConnect.

Endpoints:
  GET    /payouts/                    → doctor: own payout history | admin: all payouts
  POST   /payouts/request/            → doctor: submit payout request
  GET    /payouts/<id>/               → retrieve single payout
  PATCH  /payouts/<id>/approve/       → admin: approve + record transfer reference
  PATCH  /payouts/<id>/reject/        → admin: reject with reason
  GET    /payouts/earnings/           → doctor: earnings summary dashboard
  GET    /payouts/admin/revenue/      → admin: platform revenue dashboard (daily/weekly/monthly)

Commission recap:
  - 15% platform commission on every completed online/on_demand appointment.
  - Doctor receives 85% (stored as doctor_earnings on the Appointment row).
  - In-clinic: 0% commission, no payout needed.
"""

import logging
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum, Count
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from appointments.models import Appointment
from .models import Payout
from .serializers import (
    DoctorEarningsSummarySerializer,
    PayoutApproveSerializer,
    PayoutRejectSerializer,
    PayoutRequestSerializer,
    PayoutSerializer,
    _get_available_earnings,
)

logger = logging.getLogger(__name__)


# ── Permission helpers ────────────────────────────────────────────────────────

def _is_doctor(user): return getattr(user, "role", None) == "doctor"
def _is_admin(user):  return getattr(user, "role", None) == "admin" or user.is_staff


# ── Payout list + request ─────────────────────────────────────────────────────

class PayoutListView(APIView):
    """
    GET  /payouts/  — doctor sees own history; admin sees all.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if _is_admin(request.user):
            qs = (
                Payout.objects
                .select_related("doctor", "reviewed_by")
                .all()
                .order_by("-created_at")
            )
            # Optional filter by status
            status_filter = request.query_params.get("status")
            if status_filter:
                qs = qs.filter(status=status_filter)
        elif _is_doctor(request.user):
            qs = (
                Payout.objects
                .select_related("doctor", "reviewed_by")
                .filter(doctor=request.user)
                .order_by("-created_at")
            )
        else:
            return Response({"detail": "Forbidden."}, status=status.HTTP_403_FORBIDDEN)

        return Response(PayoutSerializer(qs, many=True).data)


class PayoutRequestView(APIView):
    """
    POST /payouts/request/
    Doctor submits a payout request for their available earnings.

    The system validates that the requested amount does not exceed
    available earnings (total doctor_earnings minus already-requested amounts).
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if not _is_doctor(request.user):
            return Response({"detail": "Only doctors can request payouts."}, status=status.HTTP_403_FORBIDDEN)

        # Block if there is already a pending payout request
        if Payout.objects.filter(doctor=request.user, status="pending").exists():
            return Response(
                {"detail": "You already have a pending payout request. Please wait for admin review."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = PayoutRequestSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        payout = Payout.objects.create(
            doctor=request.user,
            amount=data["amount"],
            method=data["method"],
            account_name=data["account_name"],
            account_number=data["account_number"],
            bank_name=data.get("bank_name", ""),
            period_start=data.get("period_start"),
            period_end=data.get("period_end"),
            status="pending",
        )

        # Notify admin (best-effort)
        try:
            from notifications.models import Notification
            from users.models import User
            admins = User.objects.filter(is_staff=True, is_active=True)
            for admin in admins:
                Notification.objects.create(
                    user=admin,
                    type="payout",
                    title="New Payout Request",
                    message=(
                        f"Dr. {request.user.first_name} {request.user.last_name} "
                        f"requested a payout of ₱{payout.amount:,.2f} via {payout.get_method_display()}."
                    ),
                    data={"payout_id": payout.pk},
                )
        except Exception as exc:
            logger.warning("Payout admin notification failed: %s", exc)

        return Response(PayoutSerializer(payout).data, status=status.HTTP_201_CREATED)


# ── Payout detail ─────────────────────────────────────────────────────────────

class PayoutDetailView(APIView):
    """
    GET /payouts/<id>/  — retrieve a single payout.
    Doctor can only see their own; admin can see all.
    """
    permission_classes = [IsAuthenticated]

    def _get_payout(self, pk, user):
        try:
            qs = Payout.objects.select_related("doctor", "reviewed_by")
            if _is_admin(user):
                return qs.get(pk=pk)
            return qs.get(pk=pk, doctor=user)
        except Payout.DoesNotExist:
            return None

    def get(self, request, pk):
        payout = self._get_payout(pk, request.user)
        if not payout:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(PayoutSerializer(payout).data)


# ── Admin: Approve ────────────────────────────────────────────────────────────

class PayoutApproveView(APIView):
    """
    PATCH /payouts/<id>/approve/
    Admin approves a pending payout and records the transfer reference number.

    Sets status → "paid" (funds are considered transferred at this point).
    """
    permission_classes = [IsAuthenticated]

    def patch(self, request, pk):
        if not _is_admin(request.user):
            return Response({"detail": "Admins only."}, status=status.HTTP_403_FORBIDDEN)

        try:
            payout = Payout.objects.select_related("doctor").get(pk=pk)
        except Payout.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        if payout.status != "pending":
            return Response(
                {"detail": f"Cannot approve a payout with status '{payout.status}'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = PayoutApproveSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        with transaction.atomic():
            payout.status           = "paid"
            payout.reviewed_by      = request.user
            payout.reviewed_at      = timezone.now()
            payout.payout_reference = data["payout_reference"]
            payout.admin_notes      = data.get("admin_notes", "")
            payout.save(update_fields=[
                "status", "reviewed_by", "reviewed_at",
                "payout_reference", "admin_notes", "updated_at",
            ])

        # Notify doctor
        try:
            from notifications.models import Notification
            Notification.objects.create(
                user=payout.doctor,
                type="payout",
                title="Payout Approved ✅",
                message=(
                    f"Your payout of ₱{payout.amount:,.2f} has been approved and transferred "
                    f"via {payout.get_method_display()}. "
                    f"Reference: {payout.payout_reference}"
                ),
                data={"payout_id": payout.pk, "reference": payout.payout_reference},
            )
        except Exception as exc:
            logger.warning("Payout approval notification failed: %s", exc)

        return Response(PayoutSerializer(payout).data)


# ── Admin: Reject ─────────────────────────────────────────────────────────────

class PayoutRejectView(APIView):
    """
    PATCH /payouts/<id>/reject/
    Admin rejects a pending payout with a reason.
    The doctor's earnings remain available for a future payout request.
    """
    permission_classes = [IsAuthenticated]

    def patch(self, request, pk):
        if not _is_admin(request.user):
            return Response({"detail": "Admins only."}, status=status.HTTP_403_FORBIDDEN)

        try:
            payout = Payout.objects.select_related("doctor").get(pk=pk)
        except Payout.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        if payout.status != "pending":
            return Response(
                {"detail": f"Cannot reject a payout with status '{payout.status}'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = PayoutRejectSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        with transaction.atomic():
            payout.status           = "rejected"
            payout.reviewed_by      = request.user
            payout.reviewed_at      = timezone.now()
            payout.rejection_reason = data["rejection_reason"]
            payout.save(update_fields=[
                "status", "reviewed_by", "reviewed_at",
                "rejection_reason", "updated_at",
            ])

        # Notify doctor
        try:
            from notifications.models import Notification
            Notification.objects.create(
                user=payout.doctor,
                type="payout",
                title="Payout Request Rejected",
                message=(
                    f"Your payout request of ₱{payout.amount:,.2f} was not approved. "
                    f"Reason: {payout.rejection_reason}. "
                    f"Your earnings remain available — you may submit a new request."
                ),
                data={"payout_id": payout.pk},
            )
        except Exception as exc:
            logger.warning("Payout rejection notification failed: %s", exc)

        return Response(PayoutSerializer(payout).data)


# ── Doctor: Earnings Dashboard ────────────────────────────────────────────────

class DoctorEarningsDashboardView(APIView):
    """
    GET /payouts/earnings/
    Doctor dashboard: full earnings breakdown.

    Returns:
      - total_gross:        sum of all fees charged to patients (online only)
      - total_commission:   sum of platform_commission (15%)
      - total_earnings:     sum of doctor_earnings (85%)
      - available_earnings: earnings not yet requested for payout
      - paid_out:           sum of approved/paid payout amounts
      - pending_payout:     sum of pending payout requests
      - completed_count:    number of completed paid online appointments
      - breakdown:          per-appointment detail list
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        # Admin can query any doctor via ?doctor_id=X
        if _is_admin(request.user):
            doctor_id = request.query_params.get("doctor_id")
            if not doctor_id:
                return Response(
                    {"detail": "Pass ?doctor_id=<id> to view a doctor's earnings."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            from users.models import User
            try:
                doctor = User.objects.get(pk=doctor_id, role="doctor")
            except User.DoesNotExist:
                return Response({"detail": "Doctor not found."}, status=status.HTTP_404_NOT_FOUND)
        elif _is_doctor(request.user):
            doctor = request.user
        else:
            return Response({"detail": "Forbidden."}, status=status.HTTP_403_FORBIDDEN)

        qs = (
            Appointment.objects
            .filter(
                doctor=doctor,
                status="completed",
                payment_status="paid",
                type__in=("online", "on_demand"),
            )
            .exclude(doctor_earnings=None)
            .order_by("-date")
        )

        agg = qs.aggregate(
            total_gross=Sum("fee"),
            total_commission=Sum("platform_commission"),
            total_earnings=Sum("doctor_earnings"),
        )

        total_earnings   = agg["total_earnings"]   or Decimal("0.00")
        total_commission = agg["total_commission"] or Decimal("0.00")
        total_gross      = agg["total_gross"]      or Decimal("0.00")

        # Paid out = sum of approved + paid payout requests
        paid_out = (
            Payout.objects
            .filter(doctor=doctor, status__in=("approved", "paid"))
            .aggregate(total=Sum("amount"))["total"]
        ) or Decimal("0.00")

        # Pending payout = sum of pending requests
        pending_payout = (
            Payout.objects
            .filter(doctor=doctor, status="pending")
            .aggregate(total=Sum("amount"))["total"]
        ) or Decimal("0.00")

        available_earnings = max(Decimal("0.00"), total_earnings - paid_out - pending_payout)

        breakdown = list(
            qs.values(
                "id", "date", "type", "fee",
                "platform_commission", "doctor_earnings",
                "payment_status",
            )
        )

        return Response({
            "total_gross":        total_gross,
            "total_commission":   total_commission,
            "total_earnings":     total_earnings,
            "available_earnings": available_earnings,
            "paid_out":           paid_out,
            "pending_payout":     pending_payout,
            "completed_count":    qs.count(),
            "breakdown":          breakdown,
        })


# ── Admin: Platform Revenue Dashboard ────────────────────────────────────────

class AdminRevenueDashboardView(APIView):
    """
    GET /payouts/admin/revenue/
    Admin dashboard: platform commission revenue grouped by period.

    Query params:
      period = daily | weekly | monthly  (default: monthly)

    Returns:
      - total_revenue:       all-time platform commission collected
      - total_gross:         all-time gross fees charged to patients
      - total_appointments:  count of completed paid online appointments
      - breakdown:           grouped by period with revenue + count
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not _is_admin(request.user):
            return Response({"detail": "Admins only."}, status=status.HTTP_403_FORBIDDEN)

        from django.db.models.functions import TruncDay, TruncWeek, TruncMonth

        period   = request.query_params.get("period", "monthly")
        trunc_fn = {"daily": TruncDay, "weekly": TruncWeek, "monthly": TruncMonth}.get(period, TruncMonth)

        qs = (
            Appointment.objects
            .filter(
                status="completed",
                payment_status="paid",
                type__in=("online", "on_demand"),
            )
            .exclude(platform_commission=None)
        )

        totals = qs.aggregate(
            total_revenue=Sum("platform_commission"),
            total_gross=Sum("fee"),
            total_appointments=Count("id"),
        )

        grouped = list(
            qs.annotate(period=trunc_fn("date"))
            .values("period")
            .annotate(
                revenue=Sum("platform_commission"),
                gross=Sum("fee"),
                count=Count("id"),
            )
            .order_by("-period")
        )

        # Payout summary for admin
        payout_summary = Payout.objects.aggregate(
            total_paid_out=Sum("amount", filter=models_q(status__in=("approved", "paid"))),
            total_pending=Sum("amount",  filter=models_q(status="pending")),
        )

        return Response({
            "period":             period,
            "total_revenue":      totals["total_revenue"]      or Decimal("0.00"),
            "total_gross":        totals["total_gross"]        or Decimal("0.00"),
            "total_appointments": totals["total_appointments"] or 0,
            "breakdown":          grouped,
            "payout_summary": {
                "total_paid_out":  payout_summary["total_paid_out"] or Decimal("0.00"),
                "total_pending":   payout_summary["total_pending"]  or Decimal("0.00"),
            },
        })


# ── Q import helper (avoids top-level circular import) ───────────────────────

def models_q(**kwargs):
    from django.db.models import Q
    return Q(**kwargs)
