"""
appointments/serializers.py - UPDATED FOR SIMPLIFIED BOOKED-FOR
"""

from datetime import datetime, timedelta

from django.utils import timezone
from rest_framework import serializers

from doctors.models import DoctorProfile
from users.models import User
from .models import Appointment, AppointmentShare, FollowUpInvitation, PatientProfile, Review


def _get_doctor_profile(doctor_user):
    return getattr(doctor_user, "doctor_profile", None)


# ── List ──────────────────────────────────────────────────────────────────────

class PatientProfileSerializer(serializers.ModelSerializer):
    """Serializer for PatientProfile model."""
    full_name = serializers.ReadOnlyField()
    age = serializers.ReadOnlyField()

    class Meta:
        model = PatientProfile
        fields = [
            "id", "account_owner", "first_name", "middle_name", "last_name",
            "full_name", "date_of_birth", "age", "email", "sex", "home_address",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "account_owner", "created_at", "updated_at"]


class AppointmentListSerializer(serializers.ModelSerializer):
    patient_name           = serializers.SerializerMethodField()
    doctor_name            = serializers.SerializerMethodField()
    doctor_profile_id      = serializers.SerializerMethodField()
    queue_position         = serializers.SerializerMethodField()
    estimated_wait_minutes = serializers.SerializerMethodField()
    effective_fee          = serializers.SerializerMethodField()
    clinic_info            = serializers.SerializerMethodField()
    patient_profile_data   = serializers.SerializerMethodField()

    class Meta:
        model  = Appointment
        fields = [
            "id", "patient", "doctor", "patient_name", "doctor_name", "doctor_profile_id",
            "date", "time", "type", "status", "payment_status",
            "queue_number", "queue_position", "estimated_wait_minutes",
            "is_on_demand", "fee", "effective_fee",
            "doctor_earnings", "platform_commission",
            "hmo_provider", "hmo_coverage_percent",
            "clinic_info",
            "booked_for_name", "patient_profile", "patient_profile_data",
            "symptoms",
            "created_at",
        ]

    def get_patient_name(self, obj):
        # If booked_for_name is provided, use it; otherwise use logged-in user's name
        if obj.booked_for_name and obj.booked_for_name.strip():
            return obj.booked_for_name.strip()
        return f"{obj.patient.first_name} {obj.patient.last_name}".strip()
    
    def get_patient_profile_data(self, obj):
        """Return full patient profile data if available."""
        if obj.patient_profile:
            return PatientProfileSerializer(obj.patient_profile).data
        return None

    def get_doctor_name(self, obj):
        return f"Dr. {obj.doctor.first_name} {obj.doctor.last_name}".strip()

    def get_doctor_profile_id(self, obj):
        try:
            return obj.doctor.doctor_profile.id
        except Exception:
            return None

    def get_queue_position(self, obj):
        return obj.queue_position

    def get_estimated_wait_minutes(self, obj):
        return obj.estimated_wait_minutes

    def get_effective_fee(self, obj):
        return obj.effective_fee

    def get_clinic_info(self, obj):
        if obj.type != "in_clinic" or not obj.clinic_info_snapshot:
            return None
        s = obj.clinic_info_snapshot
        parts = filter(None, [s.get("clinic_name"), s.get("clinic_address"), s.get("city")])
        full = ", ".join(parts)
        return {
            "clinic_name":    s.get("clinic_name", ""),
            "clinic_address": s.get("clinic_address", ""),
            "city":           s.get("city", ""),
            "maps_url":       f"https://maps.google.com/?q={full.replace(' ', '+')}" if full else None,
        }


# ── Create ────────────────────────────────────────────────────────────────────

class AppointmentCreateSerializer(serializers.Serializer):
    """Serializer for creating appointments with patient profile fields from frontend."""
    doctor_id       = serializers.IntegerField(error_messages={
        'required': 'Please select a doctor.',
        'invalid': 'Invalid doctor selection.'
    })
    date            = serializers.DateField(error_messages={
        'required': 'Please select an appointment date.',
        'invalid': 'Invalid date format. Please select a valid date.'
    })
    time            = serializers.TimeField(error_messages={
        'required': 'Please select an appointment time.',
        'invalid': 'Invalid time format. Please select a valid time slot.'
    })
    type            = serializers.ChoiceField(
        choices=["online", "in_clinic", "on_demand"],
        error_messages={
            'required': 'Please select a consultation type (Online or In-Clinic).',
            'invalid_choice': 'Invalid consultation type. Please choose Online or In-Clinic.'
        }
    )
    symptoms        = serializers.CharField(required=False, allow_blank=True, default="")
    notes           = serializers.CharField(required=False, allow_blank=True, default="")
    hmo_card_id     = serializers.IntegerField(required=False, allow_null=True)
    paymongo_payment_id = serializers.CharField(required=False, allow_blank=True, default="")
    pre_consult_files = serializers.ListField(
        child=serializers.URLField(), required=False, default=list
    )
    
    # ── Patient Profile fields from frontend Step 2 ──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
    # These fields are manually filled by the user in the Patient Details step.
    # We combine firstName + middleName + lastName into booked_for_name.
    # If all name fields are empty, we default to the logged-in user's name.
    firstName       = serializers.CharField(required=False, allow_blank=True, default="")
    middleName      = serializers.CharField(required=False, allow_blank=True, default="")
    lastName        = serializers.CharField(required=False, allow_blank=True, default="")
    dateOfBirth     = serializers.DateField(required=False, allow_null=True, input_formats=["%Y-%m-%d", "iso-8601"])
    email           = serializers.EmailField(required=False, allow_blank=True, default="")
    sex             = serializers.CharField(required=False, allow_blank=True, default="")
    homeAddress     = serializers.CharField(required=False, allow_blank=True, default="")
    reasonForConsultation = serializers.CharField(required=False, allow_blank=True, default="")

    def validate_doctor_id(self, value):
        try:
            doctor = User.objects.select_related("doctor_profile").get(
                pk=value, role="doctor", is_active=True
            )
        except User.DoesNotExist:
            raise serializers.ValidationError(
                "This doctor is not available. Please select another doctor."
            )
        profile = _get_doctor_profile(doctor)
        if not profile:
            raise serializers.ValidationError(
                "This doctor's profile is incomplete. Please select another doctor."
            )
        if not profile.is_verified:
            raise serializers.ValidationError(
                "This doctor is not yet verified. Please select a verified doctor."
            )
        return value

    def validate_date(self, value):
        today = timezone.localdate()
        if value < today:
            raise serializers.ValidationError(
                "Cannot book appointments in the past. Please select today or a future date."
            )
        max_advance_days = 90
        if value > today + timedelta(days=max_advance_days):
            raise serializers.ValidationError(
                f"Cannot book more than {max_advance_days} days in advance. Please select a closer date."
            )
        return value

    def validate(self, attrs):
        consult_type = attrs.get("type")
        if not consult_type:
            raise serializers.ValidationError({
                "type": "Please select a consultation type (Online or In-Clinic)."
            })

        # On-demand: auto-set date/time
        if consult_type == "on_demand":
            attrs["date"] = timezone.localdate()
            attrs["time"] = timezone.localtime().time()
            return attrs

        # Validate date and time for scheduled appointments
        if not attrs.get("date"):
            raise serializers.ValidationError({
                "date": "Please select an appointment date."
            })
        if not attrs.get("time"):
            raise serializers.ValidationError({
                "time": "Please select an appointment time."
            })

        # Block booking a past time slot on today's date
        if attrs["date"] == timezone.localdate() and attrs["time"] <= timezone.localtime().time():
            raise serializers.ValidationError({
                "time": "This time slot has already passed. Please select a future time slot."
            })

        # In-clinic: validate clinic info exists
        if consult_type == "in_clinic":
            try:
                doctor = User.objects.select_related("doctor_profile").get(
                    pk=attrs["doctor_id"], role="doctor"
                )
                profile = _get_doctor_profile(doctor)
                if profile and not profile.clinic_name:
                    raise serializers.ValidationError({
                        "type": "This doctor does not have clinic information set up for in-clinic consultations. Please choose Online consultation."
                    })
            except User.DoesNotExist:
                pass

        # Check for time slot conflicts
        try:
            doctor_user_id = User.objects.get(
                doctor_profile__id=attrs["doctor_id"], role="doctor"
            ).pk
        except User.DoesNotExist:
            doctor_user_id = attrs["doctor_id"]

        overlap = Appointment.objects.filter(
            doctor_id=doctor_user_id,
            date=attrs["date"],
            time=attrs["time"],
        ).exclude(status__in=["cancelled", "no_show"]).exists()
        if overlap:
            raise serializers.ValidationError({
                "time": "This time slot is no longer available. Please select another time."
            })
        
        return attrs


# ── Detail ────────────────────────────────────────────────────────────────────

class AppointmentDetailSerializer(serializers.ModelSerializer):
    patient_name           = serializers.SerializerMethodField()
    doctor_name            = serializers.SerializerMethodField()
    doctor_specialty       = serializers.SerializerMethodField()
    doctor_profile_id      = serializers.SerializerMethodField()
    doctor_avatar          = serializers.SerializerMethodField()
    queue_position         = serializers.SerializerMethodField()
    estimated_wait_minutes = serializers.SerializerMethodField()
    can_cancel_free        = serializers.SerializerMethodField()
    effective_fee          = serializers.SerializerMethodField()
    video_room_url         = serializers.SerializerMethodField()
    video_duration_seconds = serializers.SerializerMethodField()
    shared_documents       = serializers.SerializerMethodField()
    clinic_info            = serializers.SerializerMethodField()
    cancelled_by           = serializers.SerializerMethodField()
    review                 = serializers.SerializerMethodField()
    payment_display_note   = serializers.SerializerMethodField()
    patient_profile_data   = serializers.SerializerMethodField()

    class Meta:
        model  = Appointment
        fields = [
            "id", "patient", "doctor", "patient_name", "doctor_name", "doctor_specialty",
            "doctor_profile_id", "doctor_avatar",
            "date", "time", "type", "status", "payment_status",
            "payment_display_note",
            "queue_number", "queue_position", "estimated_wait_minutes",
            "is_on_demand", "fee", "effective_fee",
            "doctor_earnings", "platform_commission",
            "hmo_provider", "hmo_coverage_percent",
            "symptoms", "notes", "pre_consult_files",
            "video_link", "video_room_id", "video_password", "video_room_url",
            "video_started_at", "video_ended_at", "video_duration_seconds", "video_participants",
            "chat_room_id",
            "consult_transcript", "consult_notes", "consult_summary",
            "shared_documents",
            "clinic_info",
            "booked_for_name", "patient_profile", "patient_profile_data",
            "rejection_reason", "can_cancel_free",
            "cancel_reason", "cancelled_by", "refunded_at",
            "paymongo_payment_id",
            "reminder_24h_sent", "reminder_1h_sent", "reminder_15m_sent",
            "review",
            "created_at", "updated_at",
        ]
        read_only_fields = fields

    def get_patient_name(self, obj):
        # If booked_for_name is provided, use it; otherwise use logged-in user's name
        if obj.booked_for_name and obj.booked_for_name.strip():
            return obj.booked_for_name.strip()
        return f"{obj.patient.first_name} {obj.patient.last_name}".strip()
    
    def get_patient_profile_data(self, obj):
        """Return full patient profile data if available."""
        if obj.patient_profile:
            return PatientProfileSerializer(obj.patient_profile).data
        return None

    def get_doctor_name(self, obj):
        return f"Dr. {obj.doctor.first_name} {obj.doctor.last_name}".strip()

    def get_doctor_specialty(self, obj):
        p = _get_doctor_profile(obj.doctor)
        return p.specialty if p else None

    def get_doctor_profile_id(self, obj):
        try:
            return obj.doctor.doctor_profile.id
        except Exception:
            return None

    def get_doctor_avatar(self, obj):
        try:
            p = obj.doctor.doctor_profile
            if p and p.profile_photo:
                request = self.context.get("request")
                if request:
                    return request.build_absolute_uri(p.profile_photo.url)
                return p.profile_photo.url
        except Exception:
            pass
        return None

    def get_payment_display_note(self, obj):
        doctor_name  = f"Dr. {obj.doctor.first_name} {obj.doctor.last_name}".strip()
        patient_name = f"{obj.patient.first_name} {obj.patient.last_name}".strip()
        fee_display  = (
            f"₱{obj.effective_fee:,.2f}" if obj.effective_fee else
            (f"₱{obj.fee:,.2f}" if obj.fee else None)
        )

        if obj.type not in ("online", "on_demand"):
            return None

        status = obj.payment_status
        if status == "paid" and fee_display:
            return {
                "patient": f"You paid {fee_display} for an online consultation with {doctor_name} via PulseLink.",
                "doctor":  f"Payment of {fee_display} received from {patient_name} for their online consultation.",
                "badge":   "paid",
                "color":   "success",
            }
        if status == "refunded" and fee_display:
            return {
                "patient": f"{fee_display} has been refunded to your original payment method.",
                "doctor":  f"{fee_display} was refunded to {patient_name}.",
                "badge":   "refunded",
                "color":   "warning",
            }
        if status == "awaiting":
            return {
                "patient": f"Payment of {fee_display or 'consultation fee'} is pending for your consultation with {doctor_name}.",
                "doctor":  f"Awaiting payment from {patient_name}.",
                "badge":   "awaiting",
                "color":   "warning",
            }
        return {
            "patient": f"Payment for your consultation with {doctor_name} is not yet confirmed.",
            "doctor":  f"Payment from {patient_name} is not yet confirmed.",
            "badge":   "pending",
            "color":   "muted",
        }

    def get_queue_position(self, obj):
        return obj.queue_position

    def get_estimated_wait_minutes(self, obj):
        return obj.estimated_wait_minutes

    def get_can_cancel_free(self, obj):
        return obj.can_cancel_free

    def get_effective_fee(self, obj):
        return obj.effective_fee

    def get_video_room_url(self, obj):
        if not obj.video_room_id:
            return None
        from django.conf import settings
        domain = getattr(settings, "JITSI_DOMAIN", "meet.jit.si")
        return f"https://{domain}/{obj.video_room_id}"

    def get_video_duration_seconds(self, obj):
        return obj.video_duration_seconds

    def get_shared_documents(self, obj):
        shares = obj.shared_documents.select_related("created_by").all()
        return AppointmentShareSerializer(shares, many=True).data

    def get_clinic_info(self, obj):
        if obj.type != "in_clinic":
            return None
        snapshot = obj.clinic_info_snapshot or {}
        if not snapshot:
            return None
        address_parts = filter(None, [
            snapshot.get("clinic_name"),
            snapshot.get("clinic_address"),
            snapshot.get("city"),
        ])
        full_address = ", ".join(address_parts)
        maps_url = f"https://maps.google.com/?q={full_address.replace(' ', '+')}" if full_address else None
        return {
            "clinic_name":    snapshot.get("clinic_name", ""),
            "clinic_address": snapshot.get("clinic_address", ""),
            "city":           snapshot.get("city", ""),
            "maps_url":       maps_url,
        }

    def get_cancelled_by(self, obj):
        if not obj.cancelled_by:
            return None
        return {
            "id":   obj.cancelled_by.pk,
            "name": f"{obj.cancelled_by.first_name} {obj.cancelled_by.last_name}".strip(),
            "role": obj.cancelled_by.role,
        }

    def get_review(self, obj):
        try:
            r = obj.review
            return {
                "id":           r.pk,
                "appointment":  r.appointment_id,
                "patient":      r.patient_id,
                "doctor":       r.doctor_id,
                "patient_name": f"{r.patient.first_name} {r.patient.last_name}".strip(),
                "rating":       r.rating,
                "comment":      r.comment,
                "created_at":   r.created_at.isoformat(),
                "doctor_reply": r.doctor_reply or None,
                "reply_at":     r.reply_at.isoformat() if r.reply_at else None,
            }
        except Exception:
            return None


class AppointmentShareSerializer(serializers.ModelSerializer):
    created_by_name = serializers.SerializerMethodField()

    class Meta:
        model  = AppointmentShare
        fields = [
            "id", "doc_type", "document_id", "title", "summary",
            "created_by", "created_by_name", "created_at",
        ]
        read_only_fields = fields

    def get_created_by_name(self, obj):
        if not obj.created_by:
            return None
        return f"{obj.created_by.first_name} {obj.created_by.last_name}".strip()


# ── Cancel ────────────────────────────────────────────────────────────────────

class CancelAppointmentSerializer(serializers.Serializer):
    reason = serializers.CharField(required=False, allow_blank=True, default="")


# ── Update ────────────────────────────────────────────────────────────────────

class AppointmentUpdateSerializer(serializers.Serializer):
    status           = serializers.ChoiceField(
        choices=["confirmed", "in_progress", "completed", "cancelled", "no_show"],
        required=False,
    )
    payment_status   = serializers.ChoiceField(choices=["pending", "paid", "awaiting"], required=False)
    notes            = serializers.CharField(required=False, allow_blank=True)
    rejection_reason = serializers.CharField(required=False, allow_blank=True)


# ── Review ────────────────────────────────────────────────────────────────────

class ReviewSerializer(serializers.ModelSerializer):
    patient_name = serializers.SerializerMethodField()

    class Meta:
        model  = Review
        fields = [
            "id", "appointment", "patient", "doctor", "patient_name",
            "rating", "comment", "created_at",
            "doctor_reply", "reply_at",
        ]
        read_only_fields = [
            "id", "patient", "doctor", "created_at", "reply_at"
        ]

    def get_patient_name(self, obj):
        return f"{obj.patient.first_name} {obj.patient.last_name}".strip()


class ReviewCreateSerializer(serializers.Serializer):
    appointment_id = serializers.IntegerField()
    rating         = serializers.IntegerField(min_value=1, max_value=5)
    comment        = serializers.CharField(required=False, allow_blank=True, default="")

    def validate_appointment_id(self, value):
        request = self.context["request"]
        try:
            apt = Appointment.objects.get(pk=value, patient=request.user, status="completed")
        except Appointment.DoesNotExist:
            raise serializers.ValidationError("Completed appointment not found.")
        if hasattr(apt, "review"):
            raise serializers.ValidationError("You have already reviewed this appointment.")
        return value


class ReviewReplySerializer(serializers.Serializer):
    reply = serializers.CharField(min_length=1, max_length=1000)


# ── Follow-Up Invitation ─────────────────────────────────────────────────────

class FollowUpInvitationSerializer(serializers.ModelSerializer):
    doctor_id         = serializers.SerializerMethodField()
    doctor_profile_id = serializers.SerializerMethodField()
    doctor_name       = serializers.SerializerMethodField()
    doctor_avatar     = serializers.SerializerMethodField()
    doctor_specialty  = serializers.SerializerMethodField()
    patient_name      = serializers.SerializerMethodField()
    appointment_type  = serializers.SerializerMethodField()

    class Meta:
        model  = FollowUpInvitation
        fields = [
            "id",
            "appointment",
            "prescription",
            "patient",
            "follow_up_date",
            "status",
            "ignored_at",
            "created_at",
            "doctor_id",
            "doctor_profile_id",
            "doctor_name",
            "doctor_specialty",
            "doctor_avatar",
            "patient_name",
            "appointment_type",
        ]
        read_only_fields = fields

    def _get_doctor(self, obj):
        if obj.appointment_id and obj.appointment:
            return obj.appointment.doctor
        if obj.prescription_id and obj.prescription:
            return obj.prescription.doctor
        return None

    def get_doctor_id(self, obj):
        doctor = self._get_doctor(obj)
        return doctor.pk if doctor else None

    def get_doctor_profile_id(self, obj):
        doctor = self._get_doctor(obj)
        try:
            return doctor.doctor_profile.id if doctor else None
        except Exception:
            return None

    def get_doctor_name(self, obj):
        doctor = self._get_doctor(obj)
        if not doctor:
            return None
        return f"Dr. {doctor.first_name} {doctor.last_name}".strip()

    def get_doctor_specialty(self, obj):
        doctor = self._get_doctor(obj)
        if not doctor:
            return None
        p = getattr(doctor, "doctor_profile", None)
        return getattr(p, "specialty", None) if p else None

    def get_doctor_avatar(self, obj):
        doctor = self._get_doctor(obj)
        if not doctor:
            return None
        try:
            p = doctor.doctor_profile
            if p and p.profile_photo:
                request = self.context.get("request")
                if request:
                    return request.build_absolute_uri(p.profile_photo.url)
                return p.profile_photo.url
        except Exception:
            pass
        return None

    def get_patient_name(self, obj):
        apt = obj.appointment
        if apt:
            if apt.booked_for_name and apt.booked_for_name.strip():
                return apt.booked_for_name.strip()
            profile = getattr(apt, "patient_profile", None)
            if profile and profile.full_name:
                return profile.full_name
        if obj.patient:
            return f"{obj.patient.first_name} {obj.patient.last_name}".strip()
        return None

    def get_appointment_type(self, obj):
        return obj.appointment.type if obj.appointment else None


# ── Doctor Earnings Dashboard ─────────────────────────────────────────────────

class DoctorEarningsSummarySerializer(serializers.Serializer):
    """
    Aggregated earnings summary for the doctor dashboard.
    Returned by GET /appointments/earnings/summary/
    """
    total_earnings        = serializers.DecimalField(max_digits=12, decimal_places=2)
    total_commission      = serializers.DecimalField(max_digits=12, decimal_places=2)
    total_gross           = serializers.DecimalField(max_digits=12, decimal_places=2)
    completed_count       = serializers.IntegerField()
    breakdown             = serializers.ListField(child=serializers.DictField())

