from django.contrib.admin import AdminSite
from django.utils import timezone


class CareConnectAdminSite(AdminSite):
    def index(self, request, extra_context=None):
        from appointments.models import Appointment
        from doctors.models import DoctorProfile, PatientHMO
        from pharmacy.models import Order
        from users.models import User

        today = timezone.localdate()

        stats = {
            "total_users":           User.objects.count(),
            "new_users_today":       User.objects.filter(date_joined__date=today).count(),
            "total_doctors":         DoctorProfile.objects.count(),
            "verified_doctors":      DoctorProfile.objects.filter(is_verified=True).count(),
            "appointments_today":    Appointment.objects.filter(date=today).count(),
            "pending_appointments":  Appointment.objects.filter(status="pending").count(),
            "pending_verifications": DoctorProfile.objects.filter(is_verified=False).count(),
            "pharmacy_orders":       Order.objects.count(),
            "pending_orders":        Order.objects.filter(status="pending").count(),
            "pending_hmo":           PatientHMO.objects.filter(verification_status="pending").count(),
        }

        recent_appointments = (
            Appointment.objects
            .select_related("patient", "doctor")
            .order_by("-created_at")[:8]
        )

        pending_doctors = (
            DoctorProfile.objects
            .filter(is_verified=False)
            .select_related("user")
            .order_by("-created_at")[:8]
        )

        extra_context = extra_context or {}
        extra_context.update({
            "stats":               stats,
            "recent_appointments": recent_appointments,
            "pending_doctors":     pending_doctors,
        })
        return super().index(request, extra_context)
