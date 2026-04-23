"""
doctors/views.py

ViewSet + APIViews for the doctors app.

Endpoints:
  GET    /doctors/                    → public list (verified + active)
  GET    /doctors/<pk>/               → public detail
  PATCH  /doctors/<pk>/               → doctor self-update (own profile)
  GET    /doctors/available_now/      → on-demand doctors active within 10 min
  POST   /doctors/invite/             → admin invite new doctor
  PATCH  /doctors/<pk>/verify/        → admin verify doctor (set is_verified=True)
  POST   /doctors/ping/               → doctor heartbeat (updates last_active_at)
  ── NEW ──
  PATCH  /doctors/availability/       → doctor toggles on-demand + sets weekly_schedule
  POST   /doctors/slots/              → doctor creates single or recurring slots
  PATCH  /doctors/slots/<pk>/         → doctor updates a slot
  DELETE /doctors/slots/<pk>/         → doctor deletes a slot (only if not booked)
  GET    /doctors/my-schedule/        → doctor dashboard: schedule + upcoming appointments
"""

import threading
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from rest_framework import filters, status
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet
from rest_framework_simplejwt.tokens import RefreshToken

from users.models import User
from users.views import _set_auth_cookies
from .filters import DoctorFilter
from .models import DoctorAvailableSlot, DoctorProfile, PatientHMO
from .serializers import (
    ActivateDoctorSerializer,
    AvailabilityUpdateSerializer,
    DoctorDetailSerializer,
    DoctorListSerializer,
    DoctorProfileCompletionSerializer,
    DoctorSelfUpdateSerializer,
    InviteDoctorSerializer,
    MyScheduleSerializer,
    PatientHMOSerializer,
    SlotCreateSerializer,
    SlotSerializer,
    SlotUpdateSerializer,
)
from .aws_liveness import (
    LivenessConfigError,
    compare_face_to_prc,
    create_liveness_session,
    extract_audit_image_bytes,
    extract_reference_image_bytes,
    get_liveness_results,
    get_temporary_liveness_credentials,
    parse_liveness_confidence,
    parse_liveness_status,
)
from .utils import check_slot_overlap, dates_for_weekday_in_range, get_available_weekdays

try:
    from django_filters.rest_framework import DjangoFilterBackend
    _FILTER_BACKEND_AVAILABLE = True
except ImportError:
    _FILTER_BACKEND_AVAILABLE = False


# ── Permission helpers ────────────────────────────────────────────────────────

def _is_owner_or_admin(request, profile: DoctorProfile) -> bool:
    return request.user.is_staff or request.user.pk == profile.user_id


def _get_doctor_profile(request) -> "DoctorProfile | None":
    """Return the DoctorProfile for the authenticated doctor, or None."""
    try:
        return request.user.doctor_profile
    except DoctorProfile.DoesNotExist:
        return None


def _profile_file_url(field) -> str | None:
    """Safely resolve a Cloudinary or local media URL."""
    if not field:
        return None
    try:
        name = field.name if hasattr(field, "name") else str(field)
        return name if name.startswith("http") else field.url
    except Exception:
        return None


def _doctor_profile_completion_payload(profile: DoctorProfile) -> dict:
    return {
        "is_profile_complete": profile.is_profile_complete,
        "specialty": profile.specialty,
        "clinic_name": profile.clinic_name,
        "city": profile.city,
        "consultation_fee_online": str(profile.consultation_fee_online or ""),
        "consultation_fee_in_person": str(profile.consultation_fee_in_person or ""),
        "is_on_demand": profile.is_on_demand,
        "signature": _profile_file_url(profile.signature),
        "prc_card_image": _profile_file_url(profile.prc_card_image),
        "face_front": _profile_file_url(profile.face_front),
        "is_face_verified": profile.is_face_verified,
        "face_verification_status": profile.face_verification_status,
        "face_verification_error": profile.face_verification_error,
    }


# ── Main ViewSet ──────────────────────────────────────────────────────────────

class DoctorViewSet(ModelViewSet):
    """
    Patient-facing doctor discovery + doctor self-management.

    Public list/detail: only verified + invite_accepted + active doctors.
    Staff can see all profiles regardless of verification status.
    """

    http_method_names = ["get", "patch", "head", "options"]
    parser_classes = [MultiPartParser, FormParser]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = [
        "user__first_name",
        "user__last_name",
        "specialty",
        "clinic_name",
        "city",
    ]
    ordering_fields = [
        "consultation_fee_online",
        "consultation_fee_in_person",
        "years_of_experience",
        "created_at",
    ]
    ordering = ["-created_at"]

    def get_filter_backends(self):
        backends = list(self.filter_backends)
        if _FILTER_BACKEND_AVAILABLE:
            backends.insert(0, DjangoFilterBackend)
        return backends

    @property
    def filterset_class(self):
        if _FILTER_BACKEND_AVAILABLE:
            return DoctorFilter
        return None

    def get_queryset(self):
        base = (
            DoctorProfile.objects
            .select_related("user")
            .prefetch_related("hospitals", "services", "hmos")
            .filter(invite_accepted=True, user__is_active=True)
        )
        if not (self.request.user.is_authenticated and self.request.user.is_staff):
            base = base.filter(is_verified=True)
        return base

    def get_permissions(self):
        if self.action in ("list", "retrieve", "available_now"):
            return [AllowAny()]
        return [IsAuthenticated()]

    def get_serializer_class(self):
        if self.action == "retrieve":
            return DoctorDetailSerializer
        if self.action == "partial_update":
            return DoctorSelfUpdateSerializer
        return DoctorListSerializer

    def partial_update(self, request, *args, **kwargs):
        profile = self.get_object()
        if not _is_owner_or_admin(request, profile):
            return Response({"detail": "Forbidden."}, status=status.HTTP_403_FORBIDDEN)
        serializer = DoctorSelfUpdateSerializer(
            profile, data=request.data, partial=True
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(DoctorDetailSerializer(profile, context={"request": request}).data)

    # ── GET /doctors/my-patients/ ────────────────────────────────────────────
    @action(detail=False, methods=["get"], url_path="my-patients", permission_classes=[IsAuthenticated])
    def my_patients(self, request):
        """
        Returns the unique patients who have had appointments with the
        authenticated doctor, with full profile details.
        """
        from appointments.models import Appointment as Apt
        from users.serializers import PatientDetailSerializer

        apt_qs = (
            Apt.objects
            .filter(doctor=request.user)
            .select_related("patient")
            .order_by("-date")
        )
        seen = set()
        patients = []
        for apt in apt_qs:
            if apt.patient_id not in seen:
                seen.add(apt.patient_id)
                patients.append(apt.patient)

        serializer = PatientDetailSerializer(patients, many=True, context={"request": request})
        return Response(serializer.data)

    # ── GET /doctors/available_now/ ───────────────────────────────────────────
    @action(detail=False, methods=["get"], url_path="available_now", permission_classes=[AllowAny])
    def available_now(self, request):
        """
        Returns on-demand doctors who pinged within the last 10 minutes.
        Powers the "Available Now" section on the patient home screen.
        """
        cutoff = timezone.now() - timezone.timedelta(minutes=10)
        qs = self.get_queryset().filter(
            is_on_demand=True,
            last_active_at__gte=cutoff,
        )
        serializer = DoctorListSerializer(qs, many=True, context={"request": request})
        return Response(serializer.data)

    # ── POST /doctors/ping/ ───────────────────────────────────────────────────
    @action(detail=False, methods=["post"], url_path="ping", permission_classes=[IsAuthenticated])
    def ping(self, request):
        """
        Doctor heartbeat endpoint.  Updates last_active_at to now.
        Called every ~5 min from the doctor app to maintain "Available Now" status.
        """
        profile = _get_doctor_profile(request)
        if not profile:
            return Response({"detail": "No doctor profile found."}, status=status.HTTP_404_NOT_FOUND)

        profile.last_active_at = timezone.now()
        profile.save(update_fields=["last_active_at"])
        return Response({"last_active_at": profile.last_active_at})


# ── Admin: Invite doctor ──────────────────────────────────────────────────────

class InviteDoctorView(APIView):
    """POST /doctors/invite/ — admin creates inactive user + profile, sends email."""

    permission_classes = [IsAdminUser]

    def post(self, request):
        serializer = InviteDoctorSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        user = User(
            email=data["email"],
            first_name=data["first_name"],
            middle_name=data.get("middle_name", ""),
            last_name=data["last_name"],
            phone=data["phone"],
            role="doctor",
            is_active=False,
        )
        user.set_unusable_password()
        user.save()

        DoctorProfile.objects.create(
            user=user,
            specialty=data["specialty"],
            clinic_name=data["clinic_name"],
            prc_license=data["prc_license"],
            city=data.get("city", ""),
        )

        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)
        invite_url = f"{settings.FRONTEND_URL}/set-doctor-password?uid={uid}&token={token}"

        # Send synchronously so SMTP errors surface in logs/response.
        _send_invite_email(user.email, user.first_name, invite_url)

        return Response(
            {"detail": "Doctor invited. Activation email sent."},
            status=status.HTTP_201_CREATED,
        )


# ── Admin: Verify doctor ──────────────────────────────────────────────────────

class VerifyDoctorView(APIView):
    """
    PATCH /doctors/<pk>/verify/ — admin sets is_verified=True after manual
    PRC license check.  Only verified doctors appear in public patient listings.
    """

    permission_classes = [IsAdminUser]

    def patch(self, request, pk):
        try:
            profile = DoctorProfile.objects.select_related("user").get(pk=pk)
        except DoctorProfile.DoesNotExist:
            return Response({"detail": "Doctor not found."}, status=status.HTTP_404_NOT_FOUND)

        already_verified = profile.is_verified
        profile.is_verified = True
        profile.save(update_fields=["is_verified"])

        # Send verification email only on first verification
        if not already_verified:
            from notifications.tasks import send_verification_complete_email
            send_verification_complete_email.delay(profile.pk)

        return Response(
            {"detail": f"Dr. {profile.user.first_name} {profile.user.last_name} is now verified."}
        )


# ── Activate doctor (invite link) ─────────────────────────────────────────────

class ActivateDoctorView(APIView):
    """POST /doctors/activate/ — doctor sets password via invite link."""

    permission_classes = [AllowAny]

    def post(self, request):
        serializer = ActivateDoctorSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        refresh = RefreshToken.for_user(user)

        data = {
            "user": {
                "id": user.id,
                "email": user.email,
                "first_name": user.first_name,
                "middle_name": user.middle_name,
                "last_name": user.last_name,
                "role": user.role,
            }
        }
        response = Response(data, status=status.HTTP_200_OK)
        _set_auth_cookies(response, refresh)
        return response


# ── NEW: Availability (on-demand toggle + weekly schedule) ────────────────────

class AvailabilityView(APIView):
    """
    PATCH /doctors/availability/

    Doctor updates their on-demand flag and/or recurring weekly schedule.
    Only the authenticated doctor can update their own profile.

    NowServing.ph alignment: doctors set their weekly hours once here;
    the slot-generation logic in appointments/views.py reads weekly_schedule
    to auto-produce 30-min slots for any date that has no explicit slot rows.
    """
    permission_classes = [IsAuthenticated]

    def patch(self, request):
        profile = _get_doctor_profile(request)
        if not profile:
            return Response({"detail": "Doctor profile not found."}, status=status.HTTP_404_NOT_FOUND)

        serializer = AvailabilityUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        update_fields = ["updated_at"]

        if "is_on_demand" in data:
            profile.is_on_demand = data["is_on_demand"]
            update_fields.append("is_on_demand")

        if "weekly_schedule" in data:
            # Replace the entire weekly_schedule (partial day updates not supported
            # at this level — doctor sends the full desired schedule).
            profile.weekly_schedule = data["weekly_schedule"]
            update_fields.append("weekly_schedule")

        profile.save(update_fields=update_fields)

        return Response({
            "is_on_demand":    profile.is_on_demand,
            "is_available_now": profile.is_available_now,
            "weekly_schedule": profile.weekly_schedule,
        })

    def get(self, request):
        """GET /doctors/availability/ — return current availability settings."""
        profile = _get_doctor_profile(request)
        if not profile:
            return Response({"detail": "Doctor profile not found."}, status=status.HTTP_404_NOT_FOUND)

        return Response({
            "is_on_demand":    profile.is_on_demand,
            "is_available_now": profile.is_available_now,
            "weekly_schedule": profile.weekly_schedule,
        })


# ── NEW: Slot management ──────────────────────────────────────────────────────

class SlotListCreateView(APIView):
    """
    POST /doctors/slots/  — create one or many slots (single date or recurring weekly).
    GET  /doctors/slots/  — list the authenticated doctor's upcoming slots.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        profile = _get_doctor_profile(request)
        if not profile:
            return Response({"detail": "Doctor profile not found."}, status=status.HTTP_404_NOT_FOUND)

        today = timezone.localdate()
        days  = int(request.query_params.get("days", 30))
        days  = min(max(days, 1), 90)  # clamp 1–90

        slots = (
            DoctorAvailableSlot.objects
            .filter(doctor=profile, date__gte=today, date__lte=today + timedelta(days=days))
            .order_by("date", "start_time")
        )
        return Response(SlotSerializer(slots, many=True).data)

    def post(self, request):
        profile = _get_doctor_profile(request)
        if not profile:
            return Response({"detail": "Doctor profile not found."}, status=status.HTTP_404_NOT_FOUND)

        serializer = SlotCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        start_time   = data["start_time"]
        end_time     = data["end_time"]
        is_available = data.get("is_available", True)
        is_recurring = data.get("is_recurring", False)

        created_slots = []
        skipped       = 0

        with transaction.atomic():
            if is_recurring:
                # Generate slots for every matching weekday in the next N weeks.
                # Default is 12 weeks (NowServing.ph pattern: pre-generate ~3 months).
                weekday     = data["weekday"]
                weeks_ahead = data.get("weeks_ahead", 12)
                today       = timezone.localdate()
                target_dates = dates_for_weekday_in_range(weekday, today, weeks_ahead)

                for target_date in target_dates:
                    # Skip if a slot already exists at this time on this date
                    if DoctorAvailableSlot.objects.filter(
                        doctor=profile, date=target_date, start_time=start_time
                    ).exists():
                        skipped += 1
                        continue

                    slot = DoctorAvailableSlot.objects.create(
                        doctor=profile,
                        date=target_date,
                        start_time=start_time,
                        end_time=end_time,
                        is_available=is_available,
                        is_recurring=True,
                    )
                    created_slots.append(slot)

            else:
                # Single date slot
                target_date = data["date"]

                # Reject if an active appointment already occupies this window
                if check_slot_overlap(profile.user, target_date, start_time, end_time):
                    return Response(
                        {"detail": "A booked appointment already exists in this time window."},
                        status=status.HTTP_409_CONFLICT,
                    )

                slot, created = DoctorAvailableSlot.objects.get_or_create(
                    doctor=profile,
                    date=target_date,
                    start_time=start_time,
                    defaults={
                        "end_time":     end_time,
                        "is_available": is_available,
                        "is_recurring": False,
                    },
                )
                if not created:
                    return Response(
                        {"detail": "A slot already exists at this date and start time."},
                        status=status.HTTP_409_CONFLICT,
                    )
                created_slots.append(slot)

        # Build booked_set for N+1-safe is_booked computation
        from appointments.models import Appointment
        if created_slots:
            dates_in_batch = {s.date for s in created_slots}
            booked_set = {
                f"{apt.date}|{str(apt.time)[:5]}"
                for apt in Appointment.objects.filter(
                    doctor=profile.user,
                    date__in=dates_in_batch,
                ).exclude(status__in=["cancelled", "no_show"])
            }
        else:
            booked_set = set()

        response_data = SlotSerializer(
            created_slots, many=True, context={"booked_set": booked_set}
        ).data
        return Response(
            {
                "created": len(created_slots),
                "skipped": skipped,
                "slots":   response_data,
            },
            status=status.HTTP_201_CREATED,
        )


class SlotDetailView(APIView):
    """
    PATCH  /doctors/slots/<pk>/  — update a slot's time or availability flag.
    DELETE /doctors/slots/<pk>/  — delete a slot (blocked if a booking exists).
    """
    permission_classes = [IsAuthenticated]

    def _get_slot(self, pk, request) -> "DoctorAvailableSlot | None":
        """Return slot only if it belongs to the authenticated doctor."""
        try:
            return DoctorAvailableSlot.objects.select_related("doctor__user").get(
                pk=pk, doctor__user=request.user
            )
        except DoctorAvailableSlot.DoesNotExist:
            return None

    def patch(self, request, pk):
        slot = self._get_slot(pk, request)
        if not slot:
            return Response({"detail": "Slot not found."}, status=status.HTTP_404_NOT_FOUND)

        serializer = SlotUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        new_start = data.get("start_time", slot.start_time)
        new_end   = data.get("end_time",   slot.end_time)

        # If time is changing, verify no appointment conflicts
        if (new_start != slot.start_time or new_end != slot.end_time):
            if check_slot_overlap(
                slot.doctor.user, slot.date, new_start, new_end,
                exclude_slot_pk=slot.pk,
            ):
                return Response(
                    {"detail": "A booked appointment conflicts with the new time window."},
                    status=status.HTTP_409_CONFLICT,
                )

        if "start_time"   in data: slot.start_time   = data["start_time"]
        if "end_time"     in data: slot.end_time      = data["end_time"]
        if "is_available" in data: slot.is_available  = data["is_available"]

        slot.save(update_fields=["start_time", "end_time", "is_available", "updated_at"])
        return Response(SlotSerializer(slot).data)

    def delete(self, request, pk):
        slot = self._get_slot(pk, request)
        if not slot:
            return Response({"detail": "Slot not found."}, status=status.HTTP_404_NOT_FOUND)

        # Block deletion if an active appointment occupies this slot
        if check_slot_overlap(slot.doctor.user, slot.date, slot.start_time, slot.end_time):
            return Response(
                {"detail": "Cannot delete a slot that has an active booking."},
                status=status.HTTP_409_CONFLICT,
            )

        slot.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


# ── NEW: My Schedule dashboard ────────────────────────────────────────────────

class MyScheduleView(APIView):
    """
    GET /doctors/my-schedule/

    Returns the doctor's full schedule dashboard:
      - on-demand status
      - weekly recurring hours
      - explicit upcoming slots (next N days, default 14)
      - upcoming booked appointments (same window)

    NowServing.ph alignment: this is the "My Schedule" tab in the doctor app,
    showing both the recurring template and concrete upcoming bookings.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        profile = _get_doctor_profile(request)
        if not profile:
            return Response({"detail": "Doctor profile not found."}, status=status.HTTP_404_NOT_FOUND)

        today = timezone.localdate()
        days  = int(request.query_params.get("days", 30))
        days  = min(max(days, 1), 60)  # clamp 1–60
        end_date = today + timedelta(days=days)

        # Upcoming explicit slots
        upcoming_slots = list(
            DoctorAvailableSlot.objects
            .filter(doctor=profile, date__gte=today, date__lte=end_date)
            .order_by("date", "start_time")
        )

        # Upcoming booked appointments
        from appointments.models import Appointment
        upcoming_apts = (
            Appointment.objects
            .select_related("patient")
            .filter(
                doctor=profile.user,
                date__gte=today,
                date__lte=end_date,
            )
            .exclude(status__in=["cancelled", "no_show", "completed"])
            .order_by("date", "time")
        )

        # Pre-build booked_set so ScheduleDashboardSlotSerializer avoids N+1
        booked_set = {
            f"{apt.date}|{str(apt.time)[:5]}"
            for apt in upcoming_apts
        }

        apt_data = [
            {
                "id":           apt.pk,
                "patient_name": f"{apt.patient.first_name} {apt.patient.last_name}".strip(),
                "date":         apt.date,
                "time":         apt.time,
                "type":         apt.type,
                "status":       apt.status,
            }
            for apt in upcoming_apts
        ]

        payload = {
            "is_on_demand":          profile.is_on_demand,
            "is_available_now":      profile.is_available_now,
            "weekly_schedule":       profile.weekly_schedule,
            "upcoming_slots":        upcoming_slots,
            "upcoming_appointments": apt_data,
        }

        serializer = MyScheduleSerializer(payload, context={"booked_set": booked_set})
        return Response(serializer.data)


class DoctorEarningsView(APIView):
    """
    GET /doctors/earnings/

    Doctor dashboard: net earnings, commission deducted, payout status.
    Delegates to the payouts app for the full breakdown.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        profile = _get_doctor_profile(request)
        if not profile:
            return Response({"detail": "Doctor profile not found."}, status=status.HTTP_404_NOT_FOUND)

        from decimal import Decimal
        from django.db.models import Sum
        from appointments.models import Appointment
        from payouts.models import Payout

        today      = timezone.localdate()
        week_start = today - timedelta(days=6)

        # ── All-time completed + paid online appointments ──────────────────────
        qs_all = (
            Appointment.objects
            .filter(
                doctor=request.user,
                status="completed",
                payment_status="paid",
                type__in=("online", "on_demand"),
            )
            .exclude(doctor_earnings=None)
        )

        agg = qs_all.aggregate(
            total_gross=Sum("fee"),
            total_commission=Sum("platform_commission"),
            total_earnings=Sum("doctor_earnings"),
        )
        total_earnings   = agg["total_earnings"]   or Decimal("0.00")
        total_commission = agg["total_commission"] or Decimal("0.00")
        total_gross      = agg["total_gross"]      or Decimal("0.00")

        # ── Payout status ─────────────────────────────────────────────────────
        paid_out = (
            Payout.objects
            .filter(doctor=request.user, status__in=("approved", "paid"))
            .aggregate(total=Sum("amount"))["total"]
        ) or Decimal("0.00")

        pending_payout = (
            Payout.objects
            .filter(doctor=request.user, status="pending")
            .aggregate(total=Sum("amount"))["total"]
        ) or Decimal("0.00")

        available_earnings = max(Decimal("0.00"), total_earnings - paid_out - pending_payout)

        # ── This week ─────────────────────────────────────────────────────────
        qs_week = qs_all.filter(date__gte=week_start, date__lte=today)
        agg_week = qs_week.aggregate(
            earnings=Sum("doctor_earnings"),
            commission=Sum("platform_commission"),
        )

        # ── Today ─────────────────────────────────────────────────────────────
        qs_today = qs_all.filter(date=today)
        agg_today = qs_today.aggregate(
            earnings=Sum("doctor_earnings"),
            commission=Sum("platform_commission"),
        )

        return Response({
            # All-time
            "total_gross":        total_gross,
            "total_commission":   total_commission,
            "total_earnings":     total_earnings,
            "available_earnings": available_earnings,
            "paid_out":           paid_out,
            "pending_payout":     pending_payout,
            "commission_rate":    profile.commission_rate,
            # This week
            "week_earnings":      agg_week["earnings"]   or Decimal("0.00"),
            "week_commission":    agg_week["commission"] or Decimal("0.00"),
            "week_consults":      qs_week.count(),
            # Today
            "today_earnings":     agg_today["earnings"]   or Decimal("0.00"),
            "today_commission":   agg_today["commission"] or Decimal("0.00"),
            "today_consults":     qs_today.count(),
        })


# ── NEW: Available weekdays for a doctor (patient-facing) ────────────────────

class AvailableWeekdaysView(APIView):
    """
    GET /doctors/<pk>/available-weekdays/

    Returns the weekday names on which the doctor has availability, so the
    patient-facing calendar can disable days with no slots without fetching
    every date individually.

    Response:
      { "weekdays": ["monday", "wednesday", "friday"] }

    NowServing.ph alignment: the patient calendar grays out days the doctor
    has not configured — this endpoint provides that data efficiently.
    """
    permission_classes = [AllowAny]

    def get(self, request, pk):
        # Accept either user ID or profile ID
        profile = None
        try:
            from users.models import User as _User
            user = _User.objects.select_related("doctor_profile").get(
                pk=pk, role="doctor", is_active=True
            )
            profile = getattr(user, "doctor_profile", None)
        except Exception:
            pass

        if not profile:
            try:
                profile = DoctorProfile.objects.get(pk=pk, user__is_active=True)
            except DoctorProfile.DoesNotExist:
                return Response({"detail": "Doctor not found."}, status=status.HTTP_404_NOT_FOUND)

        return Response({"weekdays": get_available_weekdays(profile)})


# ── Doctor profile completion (onboarding wizard) ────────────────────────────

class CompleteDoctorProfileView(APIView):
    """
    PATCH /api/doctors/me/complete/

    Doctor onboarding wizard endpoint.
    NowServing.ph / SeriousMD pattern: after activation doctors are forced
    through a 6-step wizard before the full dashboard is unlocked.

    Each step PATCHes this endpoint with partial data (multipart for photo).
    The final step sends is_profile_complete=True.

    Example payloads:
      Step 1: {"bio": "...", "languages_spoken": ["Filipino", "English"]}
      Step 2: {"clinic_name": "...", "clinic_address": "...", "city": "Makati",
               "consultation_fee_online": 500, "consultation_fee_in_person": 400}
      Step 3: {"weekly_schedule": {"monday": {"start": "09:00", "end": "17:00"}},
               "is_on_demand": false}
      Step 4: {"specialty": "General Medicine"}
      Step 5: {"signature": <png>, "prc_card_image": <jpg/png>}
      Step 6: complete AWS liveness first, then PATCH {"is_profile_complete": true}
    """
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get(self, request):
        """GET /api/doctors/me/complete/ — return the doctor's own full profile."""
        profile = _get_doctor_profile(request)
        if not profile:
            return Response(
                {"detail": "Doctor profile not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        data = DoctorDetailSerializer(profile, context={"request": request}).data
        completion_data = _doctor_profile_completion_payload(profile)
        if data.get("signature"):
            completion_data["signature"] = data["signature"]
        data.update(completion_data)
        return Response(data, status=status.HTTP_200_OK)

    def patch(self, request):
        profile = _get_doctor_profile(request)
        if not profile:
            return Response(
                {"detail": "Doctor profile not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        serializer = DoctorProfileCompletionSerializer(
            profile, data=request.data, partial=True
        )
        serializer.is_valid(raise_exception=True)
        profile = serializer.save()
        return Response(_doctor_profile_completion_payload(profile), status=status.HTTP_200_OK)


class DoctorLivenessSessionView(APIView):
    """Create a Rekognition face liveness session and short-lived browser creds."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        profile = _get_doctor_profile(request)
        if not profile:
            return Response({"detail": "Doctor profile not found."}, status=404)

        try:
            session_id = create_liveness_session()
            credentials = get_temporary_liveness_credentials()

            return Response({
                "session_id": session_id,
                "region": settings.AWS_REGION,
                "credentials": credentials,
            }, status=200)

        except LivenessConfigError as exc:
            import traceback
            traceback.print_exc()
            return Response({"detail": str(exc)}, status=500)
        except Exception as exc:
            import traceback
            traceback.print_exc()
            return Response({"detail": f"Unable to start liveness session: {str(exc)}"}, status=502)


class DoctorLivenessCompleteView(APIView):
    """Fetch Rekognition results, store evidence images, and update profile flags."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        profile = _get_doctor_profile(request)
        if not profile:
            return Response(
                {"detail": "Doctor profile not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        session_id = request.data.get("session_id")
        if not session_id:
            return Response(
                {"detail": "session_id is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            results = get_liveness_results(str(session_id))
        except LivenessConfigError as exc:
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        except Exception as exc:
            return Response(
                {"detail": f"Unable to fetch liveness results: {exc}"},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        status_value = parse_liveness_status(results)
        confidence = parse_liveness_confidence(results)
        threshold = float(getattr(settings, "AWS_LIVENESS_SCORE_THRESHOLD", 75))

        if status_value != "SUCCEEDED":
            profile.is_face_verified = False
            profile.face_verification_status = "manual_review"
            profile.face_verification_error = (
                "Face liveness did not finish successfully. Please try again."
            )
            profile.save(
                update_fields=[
                    "is_face_verified",
                    "face_verification_status",
                    "face_verification_error",
                    "updated_at",
                ]
            )
            payload = _doctor_profile_completion_payload(profile)
            payload["session_id"] = session_id
            return Response(payload, status=status.HTTP_200_OK)

        reference_bytes = extract_reference_image_bytes(results)
        audit_images = extract_audit_image_bytes(results)

        if reference_bytes:
            profile.face_front.save(
                f"liveness-front-{profile.pk}-{session_id}.jpg",
                ContentFile(reference_bytes),
                save=False,
            )

        is_verified = confidence >= threshold

        if is_verified and profile.prc_card_image and reference_bytes:
            try:
                prc_ok, prc_msg = compare_face_to_prc(reference_bytes, profile.prc_card_image)
            except LivenessConfigError as exc:
                return Response({"detail": str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            if not prc_ok:
                is_verified = False
                profile.face_verification_error = prc_msg
            else:
                profile.face_verification_error = ""
        elif is_verified:
            profile.face_verification_error = ""
        else:
            profile.face_verification_error = (
                "We could not confirm liveness with enough confidence. Please retry in better lighting."
            )

        profile.is_face_verified = is_verified
        profile.face_verification_status = "verified" if is_verified else "manual_review"
        profile.save()

        payload = _doctor_profile_completion_payload(profile)
        payload["session_id"] = session_id
        return Response(payload, status=status.HTTP_200_OK)


# ── Email helper ──────────────────────────────────────────────────────────────

def _send_invite_email(email: str, first_name: str, invite_url: str) -> None:
    subject = "Welcome to PulseLink – Activate My Account"
    plain = (
        f"Hi Dr. {first_name},\n\n"
        f"An administrator has created a PulseLink doctor account for you.\n\n"
        f"Click the link below to set your password and activate your account:\n"
        f"{invite_url}\n\n"
        f"This link expires in 3 days. If you did not expect this email, ignore it."
    )
    html = f"""
    <div style="font-family:Poppins,sans-serif;max-width:520px;margin:auto;padding:32px;
                border:1px solid #e5e7eb;border-radius:12px;">
      <h2 style="color:#0d9488;margin-bottom:4px;">PulseLink</h2>
      <p style="color:#6b7280;font-size:14px;margin-top:0;">Healthcare, made simple.</p>
      <hr style="border:none;border-top:1px solid #e5e7eb;margin:20px 0;">
      <p style="font-size:15px;color:#111827;">Hi <strong>Dr. {first_name}</strong>,</p>
      <p style="font-size:14px;color:#374151;">
        An administrator has created a PulseLink doctor account for you.
        Click the button below to set your password and activate your account.
      </p>
      <div style="text-align:center;margin:28px 0;">
        <a href="{invite_url}"
           style="background:#0d9488;color:#fff;padding:12px 28px;border-radius:8px;
                  text-decoration:none;font-weight:600;font-size:15px;">
          Activate My Account
        </a>
      </div>
      <p style="font-size:12px;color:#9ca3af;text-align:center;">
        This link expires in <strong>3 days</strong>.
        If you did not expect this email, you can safely ignore it.
      </p>
    </div>
    """
    send_mail(
        subject=subject,
        message=plain,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[email],
        html_message=html,
        fail_silently=False,
    )


# ── PatientHMO ────────────────────────────────────────────────────────────────

class PatientHMOView(APIView):
    """
    GET  /doctors/hmo/  — list patient's HMO cards
    POST /doctors/hmo/  — upload new HMO card
    """
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def get(self, request):
        qs = PatientHMO.objects.filter(patient=request.user)
        return Response(PatientHMOSerializer(qs, many=True).data)

    def post(self, request):
        serializer = PatientHMOSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(patient=request.user)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class PatientHMODetailView(APIView):
    """DELETE /doctors/hmo/<pk>/"""
    permission_classes = [IsAuthenticated]

    def delete(self, request, pk):
        try:
            card = PatientHMO.objects.get(pk=pk, patient=request.user)
        except PatientHMO.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        card.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

