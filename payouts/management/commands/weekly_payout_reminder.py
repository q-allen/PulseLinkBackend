"""
Management command: weekly_payout_reminder

Notifies doctors who have available earnings but no pending payout request.
Run weekly via Celery Beat or a cron job.

Usage:
    python manage.py weekly_payout_reminder
    python manage.py weekly_payout_reminder --dry-run
"""

from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db.models import Sum

from appointments.models import Appointment
from payouts.models import Payout


class Command(BaseCommand):
    help = "Notify doctors with available earnings to submit a payout request."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Preview without sending notifications.")

    def handle(self, *args, **options):
        dry_run = options["dry_run"]

        # Find all doctors with completed paid online appointments
        from users.models import User
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

            # Skip if already has a pending request
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

            self.stdout.write(
                f"  Dr. {doctor.first_name} {doctor.last_name} — available: ₱{available:,.2f}"
            )

            if not dry_run:
                try:
                    from notifications.models import Notification
                    Notification.objects.create(
                        user=doctor,
                        type="payout",
                        title="You have earnings available for payout 💰",
                        message=(
                            f"You have ₱{available:,.2f} in available earnings. "
                            f"Submit a payout request from your dashboard."
                        ),
                        data={"available_earnings": str(available)},
                    )
                except Exception as exc:
                    self.stderr.write(f"    Notification failed for {doctor.email}: {exc}")

            notified += 1

        action = "Would notify" if dry_run else "Notified"
        self.stdout.write(self.style.SUCCESS(f"{action} {notified} doctor(s)."))
