"""
payouts/tasks.py

Celery tasks for the payout system.
"""

import logging
from decimal import Decimal

logger = logging.getLogger(__name__)


def send_weekly_payout_reminders():
    """
    Notify doctors with available earnings to submit a payout request.
    Registered in CELERY_BEAT_SCHEDULE — runs weekly.
    Can also be triggered manually:
        python manage.py weekly_payout_reminder
    """
    try:
        from django.db.models import Sum
        from appointments.models import Appointment
        from payouts.models import Payout
        from users.models import User
        from notifications.models import Notification

        doctor_ids = (
            Appointment.objects
            .filter(status="completed", payment_status="paid", type__in=("online", "on_demand"))
            .exclude(doctor_earnings=None)
            .values_list("doctor_id", flat=True)
            .distinct()
        )

        notified = 0
        for doctor_id in doctor_ids:
            try:
                doctor = User.objects.get(pk=doctor_id, role="doctor", is_active=True)
            except User.DoesNotExist:
                continue

            if Payout.objects.filter(doctor=doctor, status="pending").exists():
                continue

            total_earned = (
                Appointment.objects
                .filter(doctor=doctor, status="completed", payment_status="paid", type__in=("online", "on_demand"))
                .exclude(doctor_earnings=None)
                .aggregate(total=Sum("doctor_earnings"))["total"]
            ) or Decimal("0.00")

            already_requested = (
                Payout.objects
                .filter(doctor=doctor, status__in=("pending", "approved", "paid"))
                .aggregate(total=Sum("amount"))["total"]
            ) or Decimal("0.00")

            available = max(Decimal("0.00"), total_earned - already_requested)
            if available < Decimal("1.00"):
                continue

            Notification.objects.create(
                user=doctor,
                type="payout",
                title="Weekly Earnings Summary 💰",
                message=(
                    f"You have ₱{available:,.2f} in available earnings this week. "
                    f"Submit a payout request from your dashboard."
                ),
                data={"available_earnings": str(available)},
            )
            notified += 1

        logger.info("Weekly payout reminders sent to %d doctor(s).", notified)

    except Exception as exc:
        logger.exception("weekly_payout_reminders task failed: %s", exc)


# Wrap in Celery task if Celery is available
try:
    from backend.celery import app

    @app.task(name="payouts.tasks.send_weekly_payout_reminders", bind=True, max_retries=2)
    def send_weekly_payout_reminders_task(self):
        send_weekly_payout_reminders()

    # Re-export under the name the Beat schedule references
    send_weekly_payout_reminders = send_weekly_payout_reminders_task

except Exception:
    pass  # Celery not configured — task runs as plain function via management command
