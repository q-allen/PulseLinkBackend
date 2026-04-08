"""
Management command: backfill_commissions

Recalculates doctor_earnings and platform_commission for all historical
completed + paid online/on_demand appointments that are missing these values.

Usage:
    python manage.py backfill_commissions
    python manage.py backfill_commissions --dry-run
"""
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from appointments.models import Appointment


class Command(BaseCommand):
    help = "Backfill doctor_earnings and platform_commission for old completed appointments."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Preview changes without saving to the database.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]

        qs = (
            Appointment.objects
            .select_related("doctor__doctor_profile")
            .filter(
                status="completed",
                payment_status="paid",
                type__in=("online", "on_demand"),
                doctor_earnings=None,   # only unprocessed rows
            )
            .exclude(fee=None)
        )

        total = qs.count()
        self.stdout.write(f"Found {total} appointment(s) to backfill.")

        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN — no changes will be saved."))

        updated = 0
        for apt in qs.iterator():
            try:
                commission_rate = apt.doctor.doctor_profile.commission_rate
            except Exception:
                commission_rate = Decimal("15.00")

            platform_commission = round(apt.fee * (commission_rate / Decimal("100")), 2)
            doctor_earnings     = round(apt.fee - platform_commission, 2)

            self.stdout.write(
                f"  Apt #{apt.pk} | fee=₱{apt.fee} | "
                f"commission={commission_rate}% → "
                f"platform=₱{platform_commission} | doctor=₱{doctor_earnings}"
            )

            if not dry_run:
                with transaction.atomic():
                    apt.platform_commission = platform_commission
                    apt.doctor_earnings     = doctor_earnings
                    apt.save(update_fields=["platform_commission", "doctor_earnings", "updated_at"])
            updated += 1

        action = "Would update" if dry_run else "Updated"
        self.stdout.write(self.style.SUCCESS(f"{action} {updated}/{total} appointment(s)."))
