"""
appointments/models.py - SIMPLIFIED BOOKED-FOR FIELDS
"""

import uuid

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone


class PatientProfile(models.Model):
    """
    Stores patient profile information for appointments.
    Can be reused across multiple appointments.
    Linked to the account owner (patient FK) who created the profile.
    """
    SEX_CHOICES = [
        ("male", "Male"),
        ("female", "Female"),
        ("other", "Other"),
    ]

    # Account owner who created this profile
    account_owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="patient_profiles",
        help_text="The logged-in user who created this profile"
    )

    # Patient Profile fields from frontend
    first_name = models.CharField(max_length=100)
    middle_name = models.CharField(max_length=100, blank=True)
    last_name = models.CharField(max_length=100)
    date_of_birth = models.DateField(null=True, blank=True)
    email = models.EmailField()
    sex = models.CharField(max_length=10, choices=SEX_CHOICES)
    home_address = models.TextField()

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["account_owner", "-created_at"], name="profile_owner_created_idx"),
        ]

    def __str__(self):
        return f"{self.first_name} {self.last_name} (Profile #{self.pk})"

    @property
    def full_name(self):
        """Returns the full name combining first, middle, and last name."""
        parts = [self.first_name, self.middle_name, self.last_name]
        return " ".join(part for part in parts if part).strip()

    @property
    def age(self):
        """Calculate age from date of birth."""
        if not self.date_of_birth:
            return None
        today = timezone.now().date()
        return today.year - self.date_of_birth.year - (
            (today.month, today.day) < (self.date_of_birth.month, self.date_of_birth.day)
        )


class Appointment(models.Model):
    STATUS_CHOICES = [
        ("pending",     "Pending"),
        ("confirmed",   "Confirmed"),
        ("in_progress", "In Progress"),
        ("completed",   "Completed"),
        ("cancelled",   "Cancelled"),
        ("no_show",     "No Show"),
    ]
    PAYMENT_STATUS_CHOICES = [
        ("pending",  "Pending"),
        ("awaiting", "Awaiting"),
        ("paid",     "Paid"),
        ("refunded", "Refunded"),
    ]
    TYPE_CHOICES = [
        ("online",    "Online"),
        ("in_clinic", "In Clinic"),
        ("on_demand", "On Demand"),
    ]

    patient        = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="patient_appointments")
    doctor         = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="doctor_appointments")
    
    # Link to patient profile (stores complete patient information)
    patient_profile = models.ForeignKey(
        "PatientProfile",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="appointments",
        help_text="Patient profile used for this appointment"
    )
    
    date           = models.DateField(db_index=True)
    time           = models.TimeField()
    type           = models.CharField(max_length=10, choices=TYPE_CHOICES, default="in_clinic")
    status         = models.CharField(max_length=12, choices=STATUS_CHOICES, default="pending")
    payment_status = models.CharField(max_length=10, choices=PAYMENT_STATUS_CHOICES, default="pending")
    queue_number   = models.PositiveIntegerField(null=True, blank=True)
    symptoms       = models.TextField(blank=True)
    notes          = models.TextField(blank=True)
    fee            = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    # ── Commission / Earnings (calculated on completion) ───────────────────────────
    # Populated atomically when status -> "completed" AND payment_status == "paid".
    # Formula (online/on_demand only):
    #   platform_commission = fee * (doctor.commission_rate / 100)   [default 15%]
    #   doctor_earnings     = fee - platform_commission
    # In-clinic appointments: both fields remain None (0% commission).
    doctor_earnings = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        help_text="Net amount the doctor receives after platform commission.",
    )
    platform_commission = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        help_text="15% platform fee deducted from online consultation fee.",
    )

    # On-demand / NowServing fields
    is_on_demand   = models.BooleanField(default=False)
    video_link     = models.URLField(max_length=500, blank=True)
    video_room_id  = models.CharField(max_length=200, blank=True)
    video_password = models.CharField(max_length=20, blank=True)
    video_started_at  = models.DateTimeField(null=True, blank=True)
    video_ended_at    = models.DateTimeField(null=True, blank=True)
    video_participants = models.JSONField(default=list, blank=True)
    chat_room_id   = models.UUIDField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True)

    # Clinic snapshot
    clinic_info_snapshot = models.JSONField(
        default=dict,
        blank=True,
        help_text="Snapshot of clinic_name/clinic_address/city at booking time (in_clinic only).",
    )

    # Pre-consult attachments
    pre_consult_files = models.JSONField(default=list, blank=True)

    # HMO coverage
    hmo_coverage_percent = models.PositiveSmallIntegerField(default=0)
    hmo_provider         = models.CharField(max_length=100, blank=True)

    # Post-consult
    consult_transcript = models.TextField(blank=True)
    consult_notes      = models.TextField(blank=True)
    consult_summary    = models.TextField(blank=True)

    # ── Denormalized patient name for quick display ──────────────────────────────
    # Stores the full name derived from patient_profile for display purposes.
    # If empty, the appointment is for the logged-in user (self).
    booked_for_name = models.CharField(
        max_length=200,
        blank=True,
        help_text="Cached full name from patient_profile. Empty = booking for self.",
    )

    # Cancellation / Refund fields
    cancelled_by       = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="cancellations_made",
    )
    cancel_reason      = models.TextField(blank=True)
    refunded_at        = models.DateTimeField(null=True, blank=True)
    paymongo_payment_id = models.CharField(max_length=100, blank=True)

    # Reminder flags
    reminder_24h_sent = models.BooleanField(default=False)
    reminder_1h_sent  = models.BooleanField(default=False)
    reminder_15m_sent = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["doctor", "date"],         name="apt_doctor_date_idx"),
            models.Index(fields=["doctor", "date", "status"], name="apt_doctor_date_status_idx"),
            models.Index(fields=["patient", "date"],        name="apt_patient_date_idx"),
        ]

    def __str__(self):
        return f"Apt #{self.pk} — {self.patient} with {self.doctor} on {self.date}"

    @property
    def net_earnings(self):
        """Alias for doctor_earnings. Returns None if commission not yet calculated."""
        return self.doctor_earnings

    @property
    def video_duration_seconds(self):
        if self.video_started_at and self.video_ended_at:
            return int((self.video_ended_at - self.video_started_at).total_seconds())
        return None

    @property
    def queue_position(self):
        if self.queue_number is None or self.status not in ("confirmed", "in_progress", "pending"):
            return None
        ahead = Appointment.objects.filter(
            doctor=self.doctor, date=self.date,
            status__in=("confirmed", "in_progress"),
            queue_number__lt=self.queue_number,
        ).count()
        return ahead + 1

    @property
    def estimated_wait_minutes(self):
        pos = self.queue_position
        return None if pos is None else max(0, (pos - 1) * 15)

    @property
    def can_cancel_free(self):
        appt_dt = timezone.datetime.combine(self.date, self.time)
        appt_dt = timezone.make_aware(appt_dt) if timezone.is_naive(appt_dt) else appt_dt
        return (appt_dt - timezone.now()).total_seconds() > 86400

    @property
    def effective_fee(self):
        if not self.fee:
            return self.fee
        from decimal import Decimal
        discount = self.fee * Decimal(self.hmo_coverage_percent) / Decimal(100)
        return round(self.fee - discount, 2)


class FollowUpInvitation(models.Model):
    """
    Follow-up booking invitation created when a doctor sets a follow-up date
    while sending a prescription during a consultation (NowServing pattern).
    """
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("ignored", "Ignored"),
        ("booked",  "Booked"),
    ]

    appointment = models.ForeignKey(
        Appointment,
        on_delete=models.CASCADE,
        related_name="follow_up_invitations",
    )
    prescription = models.ForeignKey(
        "records.Prescription",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="follow_up_invitations",
    )
    patient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="follow_up_invitations",
    )
    follow_up_date = models.DateField()
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="pending")
    ignored_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["patient", "status", "-created_at"], name="followup_patient_status_idx"),
            models.Index(fields=["appointment", "-created_at"], name="followup_appointment_idx"),
        ]

    def __str__(self):
        return f"FollowUpInvite #{self.pk} — Apt #{self.appointment_id} on {self.follow_up_date}"


class Review(models.Model):
    appointment = models.OneToOneField(
        Appointment, on_delete=models.CASCADE, related_name="review"
    )
    patient     = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="reviews_given")
    doctor      = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="reviews_received")
    rating       = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    comment      = models.TextField(blank=True)
    doctor_reply = models.TextField(blank=True)
    reply_at     = models.DateTimeField(null=True, blank=True)
    created_at   = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Review #{self.pk} — {self.rating}★ for {self.doctor}"


class AppointmentShare(models.Model):
    DOC_TYPE_CHOICES = [
        ("prescription", "Prescription"),
        ("certificate",  "Certificate"),
        ("lab",          "Lab Request"),
    ]

    appointment = models.ForeignKey(
        Appointment, on_delete=models.CASCADE, related_name="shared_documents"
    )
    doc_type    = models.CharField(max_length=20, choices=DOC_TYPE_CHOICES)
    document_id = models.PositiveIntegerField()
    title       = models.CharField(max_length=200, blank=True)
    summary     = models.TextField(blank=True)
    created_by  = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="shared_documents"
    )
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Share #{self.pk} — {self.doc_type} for Apt #{self.appointment_id}"
