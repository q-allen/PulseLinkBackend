"""
Management command to test cancellation email delivery.

Usage:
    python manage.py test_cancel_email <appointment_id>
    python manage.py test_cancel_email <appointment_id> --refund
    python manage.py test_cancel_email <appointment_id> --reason "Schedule conflict"
"""

from django.core.management.base import BaseCommand
from notifications.tasks import send_appointment_cancelled_email, send_doctor_cancellation_notification


class Command(BaseCommand):
    help = 'Test cancellation email delivery (synchronous, bypasses Celery)'

    def add_arguments(self, parser):
        parser.add_argument('appointment_id', type=int, help='Appointment ID to test')
        parser.add_argument('--refund', action='store_true', help='Simulate refund issued')
        parser.add_argument('--reason', type=str, default='', help='Cancellation reason')

    def handle(self, *args, **options):
        appointment_id = options['appointment_id']
        refund_issued = options['refund']
        reason = options['reason']

        self.stdout.write(self.style.WARNING(f'Testing cancellation email for appointment #{appointment_id}...'))
        self.stdout.write(f'  Refund: {refund_issued}')
        self.stdout.write(f'  Reason: {reason or "(none)"}')
        self.stdout.write('')

        try:
            # Call synchronously (no .delay())
            self.stdout.write('Sending patient email...')
            send_appointment_cancelled_email(appointment_id, refund_issued, reason)
            self.stdout.write(self.style.SUCCESS('✓ Patient email sent'))

            self.stdout.write('Sending doctor email...')
            send_doctor_cancellation_notification(appointment_id, reason)
            self.stdout.write(self.style.SUCCESS('✓ Doctor email sent'))

            self.stdout.write('')
            self.stdout.write(self.style.SUCCESS('All emails sent successfully!'))
            self.stdout.write('Check your inbox and spam folder.')

        except Exception as exc:
            self.stdout.write(self.style.ERROR(f'✗ Email failed: {exc}'))
            raise
