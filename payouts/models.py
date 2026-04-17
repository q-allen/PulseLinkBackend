"""
payouts/models.py

Payout request and history for the PulseLink commission system.

Flow:
  1. Doctor completes an online appointment → doctor_earnings is saved on Appointment.
  2. Doctor requests payout via POST /payouts/request/.
  3. Admin reviews and approves/rejects via PATCH /payouts/<id>/approve/ or /reject/.
  4. On approval, payout_reference is recorded and status → "paid".

Commission recap:
  - Platform takes 15% of every completed online/on_demand consultation fee.
  - Doctor receives 85% (doctor_earnings on the Appointment row).
  - In-clinic appointments: 0% commission, no payout needed (paid at clinic).
"""

from decimal import Decimal

from django.conf import settings
from django.db import models


class Payout(models.Model):
    """
    A payout request submitted by a doctor for their accumulated earnings.

    Lifecycle:
      pending  → admin reviews
      approved → admin marks paid, records reference number
      rejected → admin rejects with reason
      paid     → funds transferred (manual bank transfer / GCash)
    """

    STATUS_CHOICES = [
        ("pending",  "Pending"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
        ("paid",     "Paid"),
    ]

    METHOD_CHOICES = [
        ("gcash",         "GCash"),
        ("bank_transfer", "Bank Transfer"),
        ("maya",          "Maya"),
        ("other",         "Other"),
    ]

    # ── Relations ─────────────────────────────────────────────────────────────
    doctor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="payout_requests",
        limit_choices_to={"role": "doctor"},
        help_text="The doctor requesting the payout.",
    )

    # ── Amount ────────────────────────────────────────────────────────────────
    # Always use Decimal — never float for money.
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        help_text="Total payout amount requested (sum of doctor_earnings for included appointments).",
    )

    # ── Payout method ─────────────────────────────────────────────────────────
    method = models.CharField(
        max_length=20,
        choices=METHOD_CHOICES,
        default="gcash",
        help_text="Preferred payout channel.",
    )
    account_name = models.CharField(
        max_length=200,
        blank=True,
        help_text="Account holder name for the payout channel.",
    )
    account_number = models.CharField(
        max_length=100,
        blank=True,
        help_text="GCash number / bank account number / Maya number.",
    )
    bank_name = models.CharField(
        max_length=100,
        blank=True,
        help_text="Bank name (only for bank_transfer method).",
    )

    # ── Status ────────────────────────────────────────────────────────────────
    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default="pending",
        db_index=True,
    )

    # ── Admin fields ──────────────────────────────────────────────────────────
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="payout_reviews",
        help_text="Admin who approved or rejected this payout.",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(
        blank=True,
        help_text="Reason provided by admin when rejecting a payout request.",
    )
    # Reference number from the actual bank/GCash transfer
    payout_reference = models.CharField(
        max_length=200,
        blank=True,
        help_text="Bank/GCash transaction reference number recorded by admin on approval.",
    )
    admin_notes = models.TextField(
        blank=True,
        help_text="Internal admin notes (not visible to doctor).",
    )

    # ── Period covered ────────────────────────────────────────────────────────
    # Optional: doctor can specify the date range their payout covers.
    period_start = models.DateField(
        null=True,
        blank=True,
        help_text="Start of the earnings period covered by this payout.",
    )
    period_end = models.DateField(
        null=True,
        blank=True,
        help_text="End of the earnings period covered by this payout.",
    )

    # ── Timestamps ────────────────────────────────────────────────────────────
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Payout"
        verbose_name_plural = "Payouts"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["doctor", "status", "-created_at"], name="payout_doctor_status_idx"),
            models.Index(fields=["status", "-created_at"],           name="payout_status_created_idx"),
        ]

    def __str__(self):
        return f"Payout #{self.pk} — {self.doctor} | ₱{self.amount} | {self.status}"

    @property
    def is_pending(self) -> bool:
        return self.status == "pending"

    @property
    def is_paid(self) -> bool:
        return self.status == "paid"

