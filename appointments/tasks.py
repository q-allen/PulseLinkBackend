"""
appointments/tasks.py

Celery tasks for appointment reminders.
Schedule via django-celery-beat periodic tasks or call directly.
"""

import logging

from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_appointment_reminders(self):
    """
    Run every 30 minutes via celery-beat.
    Sends 24h email reminders for upcoming confirmed appointments.
    SMS via Semaphore/Globe M360: uncomment the _send_sms calls below.
    """
    from appointments.models import Appointment

    now = timezone.now()

    # 24h window: appointments between 23h50m and 24h10m from now
    window_24h_start = now + timezone.timedelta(hours=23, minutes=50)
    window_24h_end   = now + timezone.timedelta(hours=24, minutes=10)

    # 24h reminders
    apts_24h = Appointment.objects.filter(
        status__in=["confirmed", "pending"],
        reminder_24h_sent=False,
    ).select_related("patient", "doctor")

    for apt in apts_24h:
        apt_dt = timezone.datetime.combine(apt.date, apt.time)
        apt_dt = timezone.make_aware(apt_dt) if timezone.is_naive(apt_dt) else apt_dt
        if window_24h_start <= apt_dt <= window_24h_end:
            _send_reminder_email(apt, hours=24)
            # _send_sms(apt.patient.phone, f"Reminder: appointment with Dr. {apt.doctor.last_name} tomorrow at {apt.time}.")
            apt.reminder_24h_sent = True
            apt.save(update_fields=["reminder_24h_sent"])
            logger.info("24h reminder sent for appointment #%s", apt.pk)

def _send_reminder_email(apt, hours: int):
    subject = f"PulseLink Reminder: Appointment in {hours} hour{'s' if hours > 1 else ''}"
    plain = (
        f"Hi {apt.patient.first_name},\n\n"
        f"This is a reminder that you have an appointment with "
        f"Dr. {apt.doctor.first_name} {apt.doctor.last_name} "
        f"on {apt.date} at {apt.time}.\n\n"
        f"Type: {apt.get_type_display()}\n"
    )
    if apt.video_link:
        plain += f"Join video: {apt.video_link}\n"
    plain += "\nPulseLink — Your health, our priority."

    html = f"""
    <div style="font-family:Poppins,sans-serif;max-width:520px;margin:auto;padding:32px;
                border:1px solid #e5e7eb;border-radius:12px;">
      <h2 style="color:#0d9488;margin-bottom:4px;">PulseLink</h2>
      <p style="color:#6b7280;font-size:14px;margin-top:0;">Your health, our priority.</p>
      <hr style="border:none;border-top:1px solid #e5e7eb;margin:20px 0;">
      <p style="font-size:15px;color:#111827;">Hi <strong>{apt.patient.first_name}</strong>,</p>
      <p style="font-size:14px;color:#374151;">This is a friendly reminder that you have an appointment coming up in <strong>{hours} hour{'s' if hours > 1 else ''}</strong>:</p>
      <ul style="font-size:14px;color:#374151;line-height:1.8;">
        <li><strong>Doctor:</strong> Dr. {apt.doctor.first_name} {apt.doctor.last_name}</li>
        <li><strong>Date:</strong> {apt.date}</li>
        <li><strong>Time:</strong> {apt.time}</li>
        <li><strong>Type:</strong> {apt.get_type_display()}</li>
      </ul>
      {"<div style='text-align:center;margin:24px 0;'><a href='" + apt.video_link + "' style='background:#0d9488;color:#fff;padding:12px 28px;border-radius:8px;text-decoration:none;font-weight:600;'>Join Video Consult</a></div>" if apt.video_link else ""}
      <p style="font-size:12px;color:#9ca3af;text-align:center;margin-top:24px;">PulseLink &mdash; Your health, our priority.</p>
    </div>
    """
    try:
        send_mail(
            subject=subject,
            message=plain,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[apt.patient.email],
            html_message=html,
            fail_silently=False,
        )
    except Exception as exc:
        logger.error("Failed to send reminder email for apt #%s: %s", apt.pk, exc)


# Uncomment and configure for SMS via Semaphore (https://semaphore.co)
# def _send_sms(phone: str, message: str):
#     import requests
#     requests.post("https://api.semaphore.co/api/v4/messages", data={
#         "apikey": settings.SEMAPHORE_API_KEY,
#         "number": phone,
#         "message": message,
#         "sendername": "PulseLink",
#     }, timeout=10)

