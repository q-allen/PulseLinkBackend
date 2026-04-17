"""
notifications/tasks.py

Celery tasks for no-show auto-handling and pre-consult reminders.
Run every 5 minutes via celery-beat.
"""

import logging

from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone

logger = logging.getLogger(__name__)


def _apt_datetime(apt):
    apt_dt = timezone.datetime.combine(apt.date, apt.time)
    return timezone.make_aware(apt_dt) if timezone.is_naive(apt_dt) else apt_dt


def _notify(user, title, message, notif_type="appointment", data=None):
    try:
        from notifications.models import Notification
        notif = Notification.objects.create(
            user=user, type=notif_type, title=title, message=message, data=data or {}
        )
        # Push to the user's WebSocket channel (fire-and-forget)
        try:
            from channels.layers import get_channel_layer
            from asgiref.sync import async_to_sync
            async_to_sync(get_channel_layer().group_send)(
                f"notifications_{user.pk}",
                {
                    "type":       "notify",
                    "id":         notif.pk,
                    "notif_type": notif_type,
                    "title":      title,
                    "message":    message,
                    "data":       data or {},
                    "created_at": notif.created_at.isoformat(),
                },
            )
        except Exception as ws_exc:
            logger.warning("Notification WS push failed: %s", ws_exc)
    except Exception as exc:
        logger.warning("Notification create failed: %s", exc)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_follow_up_invitation_notification(self, invitation_id: int):
    """
    Notify patient (in-app + email) when a doctor suggests a follow-up date.
    """
    from appointments.models import FollowUpInvitation

    try:
        invitation = FollowUpInvitation.objects.select_related(
            "appointment",
            "patient",
            "appointment__doctor",
            "appointment__doctor__doctor_profile",
            "appointment__patient_profile",
        ).get(pk=invitation_id)
    except FollowUpInvitation.DoesNotExist:
        logger.warning("send_follow_up_invitation_notification: invite #%s not found", invitation_id)
        return

    patient = invitation.patient
    apt = invitation.appointment
    doctor = apt.doctor
    doctor_name = f"Dr. {doctor.first_name} {doctor.last_name}".strip()
    suggested = invitation.follow_up_date.strftime("%B %d, %Y")
    frontend_url = getattr(settings, "FRONTEND_URL", "http://localhost:3000")
    invitation_url = f"{frontend_url}/patient/invitations/{invitation.pk}"

    patient_name = (
        (apt.booked_for_name or "").strip()
        or (apt.patient_profile.full_name if apt.patient_profile else "")
        or f"{patient.first_name} {patient.last_name}".strip()
    )

    apt_type_label = "In-Clinic Consultation" if apt.type == "in_clinic" else "Online Consultation"

    doctor_profile = getattr(doctor, "doctor_profile", None)
    doctor_specialty = getattr(doctor_profile, "specialty", "") or ""
    doctor_profile_id = getattr(doctor_profile, "pk", None)

    # ── In-app notification ───────────────────────────────────────────────────
    _notify(
        patient,
        title=f"{doctor_name} invited you for a follow-up consultation.",
        message=(
            f"Suggested date: {suggested}. Tap to view and confirm your booking."
        ),
        notif_type="appointment",
        data={
            "invitation_id": invitation.pk,
            "appointment_id": apt.pk,
            "prescription_id": invitation.prescription_id,
            "doctor_id": doctor.pk,
            "doctor_profile_id": doctor_profile_id,
            "follow_up_date": str(invitation.follow_up_date),
        },
    )

    # ── Email notification ────────────────────────────────────────────────────
    plain = (
        f"Hi {patient.first_name},\n\n"
        f"{doctor_name} has invited you for a follow-up consultation.\n\n"
        f"Patient: {patient_name}\n"
        f"Doctor: {doctor_name}" + (f" ({doctor_specialty})" if doctor_specialty else "") + "\n"
        f"Suggested Date: {suggested}\n"
        f"Type: {apt_type_label}\n\n"
        f"Tap the link below to view the invitation and proceed to booking:\n"
        f"{invitation_url}\n\n"
        f"This is a suggested date — you can choose a different time slot when booking.\n\n"
        f"— The PulseLink Team"
    )

    html = f"""
    <div style="font-family:Poppins,sans-serif;max-width:540px;margin:auto;padding:32px;border:1px solid #e5e7eb;border-radius:12px;background:#ffffff;">
      <h2 style="color:#0d9488;margin-bottom:2px;">PulseLink</h2>
      <p style="color:#6b7280;font-size:13px;margin-top:0;">Healthcare, made simple.</p>
      <hr style="border:none;border-top:1px solid #e5e7eb;margin:18px 0;">
      <div style="background:#eff6ff;border:1px solid #bfdbfe;border-radius:10px;padding:16px 18px;margin-bottom:20px;">
        <p style="margin:0;font-size:15px;font-weight:700;color:#1d4ed8;">&#128197; Follow-Up Consultation Invitation</p>
        <p style="margin:6px 0 0;font-size:13px;color:#1e40af;">
          <strong>{doctor_name}</strong> has suggested a follow-up date for you.
        </p>
      </div>
      <p style="font-size:15px;color:#111827;margin-bottom:4px;">Hi <strong>{patient.first_name}</strong>,</p>
      <p style="font-size:14px;color:#374151;margin-top:4px;">
        Your doctor has recommended a follow-up consultation. Please review the details below and confirm your booking.
      </p>
      <div style="background:#f9fafb;border:1px solid #e5e7eb;border-radius:10px;padding:18px 20px;margin:20px 0;">
        <table style="width:100%;border-collapse:collapse;">
          <tr>
            <td style="padding:5px 0;color:#6b7280;font-size:13px;width:140px;">Patient</td>
            <td style="padding:5px 0;font-size:13px;font-weight:600;color:#111827;">{patient_name}</td>
          </tr>
          <tr>
            <td style="padding:5px 0;color:#6b7280;font-size:13px;">Doctor</td>
            <td style="padding:5px 0;font-size:13px;font-weight:600;color:#111827;">{doctor_name}{f' <span style="color:#6b7280;font-weight:400;">({doctor_specialty})</span>' if doctor_specialty else ''}</td>
          </tr>
          <tr>
            <td style="padding:5px 0;color:#6b7280;font-size:13px;">Suggested Date</td>
            <td style="padding:5px 0;font-size:14px;font-weight:700;color:#0d9488;">{suggested}</td>
          </tr>
          <tr>
            <td style="padding:5px 0;color:#6b7280;font-size:13px;">Type</td>
            <td style="padding:5px 0;font-size:13px;color:#111827;">{apt_type_label}</td>
          </tr>
        </table>
      </div>
      <div style="background:#fefce8;border:1px solid #fde68a;border-radius:8px;padding:12px 16px;margin-bottom:20px;">
        <p style="margin:0;font-size:12px;color:#92400e;">
          &#9432; This is a suggested date. You can choose a different available time slot when you proceed to booking.
        </p>
      </div>
      <div style="text-align:center;margin:24px 0;">
        <a href="{invitation_url}" style="background:#0d9488;color:#fff;padding:13px 32px;border-radius:8px;text-decoration:none;font-weight:700;font-size:15px;">View Invitation &amp; Book</a>
      </div>
      <p style="font-size:12px;color:#9ca3af;text-align:center;margin-top:24px;">PulseLink &mdash; Healthcare, made simple.</p>
    </div>
    """

    try:
        from django.core.mail import send_mail as _send
        _send(
            subject=f"{doctor_name} invited you for a follow-up consultation — {suggested}",
            message=plain,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[patient.email],
            html_message=html,
            fail_silently=False,
        )
        logger.info("Follow-up invitation email sent to %s for invitation #%s", patient.email, invitation.pk)
    except Exception as exc:
        logger.warning("Follow-up invitation email failed for invitation #%s: %s", invitation.pk, exc)
        raise self.retry(exc=exc)


def _send_email(subject: str, message: str, to_email: str):
    try:
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[to_email],
            fail_silently=True,
        )
    except Exception as exc:
        logger.warning("Email send failed: %s", exc)


def _broadcast_queue_update(doctor_id: int, target_date):
    """Lightweight queue update broadcast for background tasks."""
    try:
        from channels.layers import get_channel_layer
        from asgiref.sync import async_to_sync
        from appointments.models import Appointment

        qs = (
            Appointment.objects
            .select_related("patient")
            .filter(
                doctor_id=doctor_id,
                date=target_date,
                status__in=["confirmed", "in_progress"],
            )
            .order_by("queue_number", "time")
        )
        now_serving = qs.filter(status="in_progress").first()
        waiting = [apt for apt in qs if apt.status == "confirmed"]

        payload = {
            "type": "queue.update",
            "doctor_id": doctor_id,
            "date": str(target_date),
            "now_serving": {
                "appointment_id": now_serving.pk if now_serving else None,
                "patient_name": f"{now_serving.patient.first_name} {now_serving.patient.last_name}".strip()
                if now_serving else None,
                "queue_number": now_serving.queue_number if now_serving else None,
                "status": now_serving.status if now_serving else None,
            },
            "waiting": [
                {
                    "appointment_id": apt.pk,
                    "patient_name": f"{apt.patient.first_name} {apt.patient.last_name}".strip(),
                    "queue_number": apt.queue_number,
                    "queue_position": apt.queue_position,
                    "estimated_wait_minutes": apt.estimated_wait_minutes,
                }
                for apt in waiting
            ],
        }

        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            f"queue_doctor_{doctor_id}",
            payload,
        )

        for apt in qs:
            async_to_sync(channel_layer.group_send)(
                f"appointment_{apt.pk}",
                {
                    "type": "queue.update",
                    "appointment_id": apt.pk,
                    "queue_position": apt.queue_position,
                    "estimated_wait_minutes": apt.estimated_wait_minutes,
                    "now_serving_id": now_serving.pk if now_serving else None,
                },
            )
    except Exception as exc:
        logger.warning("Queue broadcast failed: %s", exc)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_verification_complete_email(self, doctor_profile_id: int):
    """
    Notify a doctor by email (and in-app) when an admin sets is_verified=True.
    Triggered by VerifyDoctorView after saving the profile.
    """
    try:
        from doctors.models import DoctorProfile
        profile = DoctorProfile.objects.select_related("user").get(pk=doctor_profile_id)
    except Exception as exc:
        logger.warning("send_verification_complete_email: profile #%s not found: %s", doctor_profile_id, exc)
        return

    user = profile.user
    doctor_name = f"Dr. {user.first_name} {user.last_name}".strip()
    dashboard_url = f"{getattr(settings, 'FRONTEND_URL', 'http://localhost:3000')}/doctor/dashboard"

    plain = (
        f"Hi {doctor_name},\n\n"
        f"Great news! Your PulseLink profile has been verified by our admin team.\n\n"
        f"You can now:\n"
        f"  • Appear in patient search results\n"
        f"  • Accept appointment bookings\n"
        f"  • Enable on-demand consultations\n\n"
        f"Log in to your dashboard to get started:\n"
        f"{dashboard_url}\n\n"
        f"Welcome to PulseLink!\n"
        f"— The PulseLink Team"
    )
    html = f"""
    <div style="font-family:Poppins,sans-serif;max-width:520px;margin:auto;padding:32px;
                border:1px solid #e5e7eb;border-radius:12px;">
      <h2 style="color:#0d9488;margin-bottom:4px;">PulseLink</h2>
      <p style="color:#6b7280;font-size:14px;margin-top:0;">Healthcare, made simple.</p>
      <hr style="border:none;border-top:1px solid #e5e7eb;margin:20px 0;">
      <div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:8px;padding:16px;margin-bottom:20px;">
        <p style="margin:0;font-size:16px;font-weight:600;color:#15803d;">&#10003; Profile Verified!</p>
      </div>
      <p style="font-size:15px;color:#111827;">Hi <strong>{doctor_name}</strong>,</p>
      <p style="font-size:14px;color:#374151;">
        Your PulseLink profile has been <strong>verified</strong> by our admin team.
        You are now visible to patients and can start accepting appointments.
      </p>
      <ul style="font-size:14px;color:#374151;line-height:1.8;">
        <li>Appear in patient search results</li>
        <li>Accept appointment bookings</li>
        <li>Enable on-demand consultations</li>
      </ul>
      <div style="text-align:center;margin:28px 0;">
        <a href="{dashboard_url}"
           style="background:#0d9488;color:#fff;padding:12px 28px;border-radius:8px;
                  text-decoration:none;font-weight:600;font-size:15px;">
          Go to My Dashboard
        </a>
      </div>
      <p style="font-size:12px;color:#9ca3af;text-align:center;">PulseLink &mdash; Healthcare, made simple.</p>
    </div>
    """

    # In-app notification
    _notify(
        user,
        title="Profile Verified!",
        message="Your profile is now verified. You can accept appointments and appear in search.",
        notif_type="system",
        data={"doctor_profile_id": doctor_profile_id},
    )

    # Email
    try:
        from django.core.mail import send_mail as _send
        _send(
            subject="Your PulseLink Profile is Now Verified!",
            message=plain,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            html_message=html,
            fail_silently=False,
        )
        logger.info("Verification email sent to %s", user.email)
    except Exception as exc:
        logger.warning("Verification email failed for %s: %s", user.email, exc)
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def send_new_message_notification(self, message_id: int, recipient_id: int):
    """
    Push notification for a new chat message.
    Triggered by ChatConsumer._handle_message and MessageListView.post.

    Creates an in-app Notification and sends an email if the recipient
    has not read the message within 30 seconds (fire-and-forget pattern).
    """
    from chat.models import Message

    try:
        msg = Message.objects.select_related(
            "sender", "conversation__patient", "conversation__doctor"
        ).get(pk=message_id)
    except Message.DoesNotExist:
        logger.warning("send_new_message_notification: msg #%s not found", message_id)
        return

    # Skip if already read (recipient opened chat before task ran)
    if msg.is_read:
        return

    from django.contrib.auth import get_user_model
    User = get_user_model()
    try:
        recipient = User.objects.get(pk=recipient_id)
    except User.DoesNotExist:
        return

    sender_name = f"{msg.sender.first_name} {msg.sender.last_name}".strip() or msg.sender.email
    preview     = (msg.content[:60] + "…") if len(msg.content) > 60 else msg.content
    if msg.type in ("image", "file"):
        preview = f"📎 {msg.file_name or 'Attachment'}"

    # In-app notification
    _notify(
        recipient,
        title=f"New message from {sender_name}",
        message=preview,
        notif_type="message",
        data={"conversation_id": msg.conversation_id, "message_id": msg.pk},
    )

    # Email notification
    _send_email(
        subject=f"PulseLink: New message from {sender_name}",
        message=(
            f"Hi {recipient.first_name},\n\n"
            f"{sender_name} sent you a message:\n"
            f"  {preview}\n\n"
            f"Open PulseLink to reply.\n\n"
            f"— The PulseLink Team"
        ),
        to_email=recipient.email,
    )


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_patient_payment_receipt(self, appointment_id: int):
    """
    Send receipt email to PulseLink account holder with "Under Review" message.
    Includes patient details (booked_for info if applicable).
    """
    from appointments.models import Appointment

    try:
        apt = Appointment.objects.select_related(
            "patient", "doctor", "doctor__doctor_profile"
        ).get(pk=appointment_id)
    except Appointment.DoesNotExist:
        logger.warning("send_patient_payment_receipt: apt #%s not found", appointment_id)
        return

    patient = apt.patient
    doctor = apt.doctor
    doctor_name = f"Dr. {doctor.first_name} {doctor.last_name}".strip()
    date_str = apt.date.strftime("%B %d, %Y")
    time_str = apt.time.strftime("%I:%M %p").lstrip("0")
    ref_number = f"APT-{str(apt.pk).zfill(8).upper()}"
    fee_display = f"\u20b1{apt.effective_fee:,.2f}" if apt.effective_fee else (
        f"\u20b1{apt.fee:,.2f}" if apt.fee else "\u2014"
    )
    frontend_url = getattr(settings, "FRONTEND_URL", "http://localhost:3000")
    apt_url = f"{frontend_url}/patient/appointments/{apt.pk}"

    patient_name = apt.booked_for_name or f"{patient.first_name} {patient.last_name}".strip()
    profile = apt.patient_profile
    patient_age = profile.age if profile else ""
    patient_gender = profile.sex if profile else ""

    patient_info = f"{patient_name}"
    if patient_age:
        patient_info += f", {patient_age} years old"
    if patient_gender:
        patient_info += f", {patient_gender.capitalize()}"

    payment_method = "PayMongo"
    if apt.paymongo_payment_id:
        if "gcash" in apt.paymongo_payment_id.lower():
            payment_method = "GCash via PayMongo"
        elif "grab" in apt.paymongo_payment_id.lower():
            payment_method = "GrabPay via PayMongo"
        else:
            payment_method = "Card via PayMongo"

    hmo_block = ""
    if apt.hmo_coverage_percent and apt.hmo_coverage_percent > 0:
        hmo_block = (
            "<tr>"
            f"<td style='padding:5px 0;color:#6b7280;font-size:13px;'>HMO ({apt.hmo_provider})</td>"
            f"<td style='padding:5px 0;font-size:13px;color:#16a34a;font-weight:600;'>-{apt.hmo_coverage_percent}% covered</td>"
            "</tr>"
        )

    plain = (
        f"Hi {patient.first_name},\n\n"
        f"Your payment has been received.\n\n"
        f"YOUR BOOKING IS UNDER REVIEW\n"
        f"Please wait for your doctor's response to confirm the booking.\n\n"
        f"Patient: {patient_info}\n"
        f"Doctor: {doctor_name}\n"
        f"Date: {date_str}\nTime: {time_str}\n"
        f"Amount Paid: {fee_display}\n"
        f"Reference: {ref_number}\n\n"
        f"View: {apt_url}\n\n"
        f"— PulseLink Team"
    )

    html = f"""
    <div style="font-family:Poppins,sans-serif;max-width:540px;margin:auto;padding:32px;border:1px solid #e5e7eb;border-radius:12px;">
      <h2 style="color:#0d9488;">PulseLink</h2>
      <div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:10px;padding:14px;margin:16px 0;">
        <p style="margin:0;font-weight:700;color:#15803d;">✓ Payment Received</p>
        <p style="margin:4px 0 0;font-size:13px;color:#166534;">Your payment of <strong>{fee_display}</strong> has been processed.</p>
      </div>
      <div style="background:#fef3c7;border:1px solid #fbbf24;border-radius:10px;padding:14px;margin:16px 0;">
        <p style="margin:0;font-weight:700;color:#92400e;">⏳ Booking Under Review</p>
        <p style="margin:4px 0 0;font-size:13px;color:#78350f;">Please wait for your doctor's response.</p>
      </div>
      <p>Hi <strong>{patient.first_name}</strong>,</p>
      <div style="background:#f9fafb;border:1px solid #e5e7eb;border-radius:10px;padding:18px;margin:16px 0;">
        <table style="width:100%;">
          <tr><td style="color:#6b7280;padding:4px 0;width:130px;">Reference</td><td style="font-weight:700;color:#0d9488;font-family:monospace;padding:4px 0;">{ref_number}</td></tr>
          <tr><td style="color:#6b7280;padding:4px 0;">Patient</td><td style="font-weight:600;padding:4px 0;">{patient_info}</td></tr>
          <tr><td style="color:#6b7280;padding:4px 0;">Doctor</td><td style="font-weight:600;padding:4px 0;">{doctor_name}</td></tr>
          <tr><td style="color:#6b7280;padding:4px 0;">Date</td><td style="padding:4px 0;">{date_str}</td></tr>
          <tr><td style="color:#6b7280;padding:4px 0;">Time</td><td style="padding:4px 0;">{time_str}</td></tr>
          {hmo_block}
          <tr><td colspan="2" style="border-top:1px solid #e5e7eb;padding-top:8px;"></td></tr>
          <tr><td style="font-weight:700;padding:4px 0;">Amount Paid</td><td style="font-size:18px;font-weight:800;color:#0d9488;padding:4px 0;">{fee_display}</td></tr>
          <tr><td style="color:#6b7280;font-size:12px;padding:4px 0;">Payment Method</td><td style="font-size:12px;color:#6b7280;padding:4px 0;">{payment_method}</td></tr>
          <tr><td style="color:#6b7280;font-size:12px;padding:4px 0;">Status</td><td style="font-size:12px;font-weight:600;color:#f59e0b;padding:4px 0;">Under Review</td></tr>
        </table>
      </div>
      <div style="text-align:center;margin:20px 0;">
        <a href="{apt_url}" style="background:#0d9488;color:#fff;padding:11px 28px;border-radius:8px;text-decoration:none;font-weight:600;">View Appointment</a>
      </div>
    </div>
    """

    _notify(
        patient,
        title="Payment Received — Booking Under Review",
        message=f"Payment of {fee_display} received. Booking with {doctor_name} is under review. Patient: {patient_info}",
        notif_type="appointment",
        data={"appointment_id": apt.pk, "reference": ref_number},
    )

    recipients = [patient.email]
    profile_email = profile.email if profile else ""
    if profile_email and profile_email.strip().lower() != patient.email.lower():
        recipients.append(profile_email.strip())

    try:
        from django.core.mail import send_mail as _send
        _send(
            subject=f"Payment Received — Booking Under Review with {doctor_name}",
            message=plain,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=recipients,
            html_message=html,
            fail_silently=False,
        )
        logger.info("Payment receipt (under review) sent to %s for apt #%s", recipients, apt.pk)
    except Exception as exc:
        logger.warning("Payment receipt email failed for apt #%s: %s", apt.pk, exc)
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_doctor_payment_notification(self, appointment_id: int):
    """
    NowServing alignment: notify the doctor (in-app + email) when a patient's
    PayMongo payment is confirmed for their online consultation.
    """
    from appointments.models import Appointment

    try:
        apt = Appointment.objects.select_related(
            "patient", "doctor", "doctor__doctor_profile"
        ).get(pk=appointment_id)
    except Appointment.DoesNotExist:
        logger.warning("send_doctor_payment_notification: apt #%s not found", appointment_id)
        return

    patient      = apt.patient
    doctor       = apt.doctor
    patient_name = f"{patient.first_name} {patient.last_name}".strip()
    date_str     = apt.date.strftime("%B %d, %Y")
    time_str     = apt.time.strftime("%I:%M %p").lstrip("0")
    ref_number   = f"APT-{str(apt.pk).zfill(8).upper()}"
    fee_display  = f"\u20b1{apt.effective_fee:,.2f}" if apt.effective_fee else (
        f"\u20b1{apt.fee:,.2f}" if apt.fee else "\u2014"
    )
    frontend_url = getattr(settings, "FRONTEND_URL", "http://localhost:3000")
    apt_url      = f"{frontend_url}/doctor/appointments/{apt.pk}"

    # In-app notification shown in doctor's notification bell immediately
    _notify(
        doctor,
        title=f"Payment Received \u2014 {patient_name} \u2705",
        message=(
            f"Payment of {fee_display} received from {patient_name} for their "
            f"online consultation on {date_str} at {time_str}. Reference: {ref_number}"
        ),
        notif_type="appointment",
        data={
            "appointment_id": apt.pk,
            "reference": ref_number,
            "amount": str(apt.effective_fee or apt.fee or 0),
        },
    )

    plain = (
        f"Hi Dr. {doctor.last_name},\n\n"
        f"A payment has been received for your upcoming online consultation.\n\n"
        f"Patient   : {patient_name}\n"
        f"Date      : {date_str}\n"
        f"Time      : {time_str}\n"
        f"Amount    : {fee_display}\n"
        f"Reference : {ref_number}\n\n"
        f"View appointment: {apt_url}\n\n"
        f"--- The PulseLink Team"
    )

    html = f"""
    <div style="font-family:Poppins,sans-serif;max-width:540px;margin:auto;padding:32px;
                border:1px solid #e5e7eb;border-radius:12px;background:#ffffff;">
      <h2 style="color:#0d9488;margin-bottom:2px;">PulseLink</h2>
      <p style="color:#6b7280;font-size:13px;margin-top:0;">Healthcare, made simple.</p>
      <hr style="border:none;border-top:1px solid #e5e7eb;margin:18px 0;">
      <div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:10px;padding:14px 18px;margin-bottom:20px;">
        <p style="margin:0;font-size:15px;font-weight:700;color:#15803d;">&#10003; Payment Received</p>
        <p style="margin:4px 0 0;font-size:13px;color:#166534;">
          {patient_name} has paid for their online consultation with you.
        </p>
      </div>
      <p style="font-size:15px;color:#111827;margin-bottom:4px;">Hi <strong>Dr. {doctor.last_name}</strong>,</p>
      <p style="font-size:14px;color:#374151;margin-top:4px;">A patient has completed payment for their upcoming consultation:</p>
      <div style="background:#f9fafb;border:1px solid #e5e7eb;border-radius:10px;padding:18px 20px;margin:20px 0;">
        <table style="width:100%;border-collapse:collapse;">
          <tr>
            <td style="padding:5px 0;color:#6b7280;font-size:13px;width:130px;">Patient</td>
            <td style="padding:5px 0;font-size:13px;font-weight:600;color:#111827;">{patient_name}</td>
          </tr>
          <tr>
            <td style="padding:5px 0;color:#6b7280;font-size:13px;">Date</td>
            <td style="padding:5px 0;font-size:13px;color:#111827;">{date_str}</td>
          </tr>
          <tr>
            <td style="padding:5px 0;color:#6b7280;font-size:13px;">Time</td>
            <td style="padding:5px 0;font-size:13px;color:#111827;">{time_str}</td>
          </tr>
          <tr><td colspan="2" style="border-top:1px solid #e5e7eb;padding-top:10px;"></td></tr>
          <tr>
            <td style="padding:5px 0;color:#111827;font-size:14px;font-weight:700;">Amount Paid</td>
            <td style="padding:5px 0;font-size:18px;font-weight:800;color:#0d9488;">{fee_display}</td>
          </tr>
          <tr>
            <td style="padding:5px 0;color:#6b7280;font-size:12px;">Reference</td>
            <td style="padding:5px 0;font-size:12px;font-family:monospace;color:#0d9488;">{ref_number}</td>
          </tr>
        </table>
      </div>
      <div style="text-align:center;margin:24px 0;">
        <a href="{apt_url}" style="background:#0d9488;color:#fff;padding:11px 28px;border-radius:8px;
           text-decoration:none;font-weight:600;font-size:14px;">View Appointment</a>
      </div>
      <p style="font-size:12px;color:#9ca3af;text-align:center;margin-top:24px;">
        PulseLink &mdash; Healthcare, made simple.
      </p>
    </div>
    """

    try:
        from django.core.mail import send_mail as _send
        _send(
            subject=f"Payment Received \u2014 {patient_name} on {date_str}",
            message=plain,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[doctor.email],
            html_message=html,
            fail_silently=False,
        )
        logger.info("Doctor payment notification sent to %s for apt #%s", doctor.email, apt.pk)
    except Exception as exc:
        logger.warning("Doctor payment notification failed for apt #%s: %s", apt.pk, exc)
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_appointment_cancelled_email(self, appointment_id: int, refund_issued: bool, reason: str = "", cancelled_by_doctor: bool = False):
    """
    Send cancellation/refund email to patient with clear, friendly messaging.
    Triggered by both cancel (patient) and refund (doctor) actions.
    NowServing alignment: always show refund timeline clearly.
    
    PRODUCTION-READY: Detailed logging, error handling, HTML email support.
    """
    logger.info("[TASK START] send_appointment_cancelled_email: apt_id=%s, refund=%s", appointment_id, refund_issued)
    
    from appointments.models import Appointment
    from django.core.mail import EmailMultiAlternatives

    try:
        apt = Appointment.objects.select_related("patient", "doctor").get(pk=appointment_id)
        logger.info("[TASK] Appointment loaded: #%s, patient=%s, doctor=%s", apt.pk, apt.patient.email, apt.doctor.email)
    except Appointment.DoesNotExist:
        logger.error("[TASK ERROR] send_appointment_cancelled_email: apt #%s not found", appointment_id)
        return
    except Exception as exc:
        logger.exception("[TASK ERROR] Failed to load appointment #%s: %s", appointment_id, exc)
        raise self.retry(exc=exc)

    patient     = apt.patient
    doctor      = apt.doctor
    doctor_name = f"Dr. {doctor.first_name} {doctor.last_name}".strip()
    date_str    = apt.date.strftime("%B %d, %Y")
    time_str    = apt.time.strftime("%I:%M %p").lstrip("0")
    ref_number  = f"APT-{str(apt.pk).zfill(8).upper()}"
    frontend_url = getattr(settings, "FRONTEND_URL", "http://localhost:3000")

    # Patient details from patient_profile (same as booking form)
    profile = apt.patient_profile
    patient_name = apt.booked_for_name or f"{patient.first_name} {patient.last_name}".strip()
    if profile:
        profile_name = f"{profile.first_name} {profile.last_name}".strip()
        if profile_name:
            patient_name = profile_name
    patient_age = profile.age if profile else ""
    patient_gender = profile.sex if profile else ""
    patient_info = patient_name
    if patient_age:
        patient_info += f", {patient_age} years old"
    if patient_gender:
        patient_info += f", {patient_gender.capitalize()}"

    # Build refund message with clear timeline
    refund_block_plain = ""
    refund_block_html = ""
    if refund_issued:
        refund_block_plain = (
            "\n\nREFUND PROCESSED:\n"
            "A full refund has been issued to your original payment method.\n\n"
            "Expected refund timeline:\n"
            "  • GCash / Maya: Typically instant\n"
            "  • Credit / Debit card: 3–7 business days\n\n"
            "You will receive a confirmation from your payment provider once the refund is complete."
        )
        refund_block_html = (
            "<div style='background:#f0fdf4;border:1px solid #bbf7d0;border-radius:10px;padding:16px;margin:16px 0;'>\n"
            "  <p style='margin:0;font-weight:700;color:#15803d;font-size:14px;'>✓ Refund Processed</p>\n"
            "  <p style='margin:8px 0 0;font-size:13px;color:#166534;'>\n"
            "    A full refund has been issued to your original payment method.\n"
            "  </p>\n"
            "  <div style='margin-top:12px;font-size:13px;color:#166534;'>\n"
            "    <p style='margin:0 0 4px;font-weight:600;'>Expected refund timeline:</p>\n"
            "    <ul style='margin:4px 0;padding-left:20px;'>\n"
            "      <li>GCash / Maya: <strong>Typically instant</strong></li>\n"
            "      <li>Credit / Debit card: <strong>3–7 business days</strong></li>\n"
            "    </ul>\n"
            "    <p style='margin:8px 0 0;font-size:12px;'>\n"
            "      You will receive a confirmation from your payment provider once the refund is complete.\n"
            "    </p>\n"
            "  </div>\n"
            "</div>"
        )

    reason_line = f"\n\nReason: {reason}" if reason else ""

    if cancelled_by_doctor:
        cancel_intro_plain = f"{doctor_name} has cancelled your appointment."
        cancel_intro_html = f"{doctor_name} has cancelled your appointment."
        cancel_banner_html = f"<p style='margin:4px 0 0;font-size:13px;color:#7f1d1d;'>{doctor_name} has cancelled your appointment.</p>"
    else:
        cancel_intro_plain = f"Your appointment with {doctor_name} has been cancelled."
        cancel_intro_html = f"Your appointment with <strong>{doctor_name}</strong> has been cancelled."
        cancel_banner_html = f"<p style='margin:4px 0 0;font-size:13px;color:#7f1d1d;'>Your appointment with {doctor_name} has been cancelled.</p>"

    plain = (
        f"Hi {patient.first_name},\n\n"
        f"{cancel_intro_plain}\n\n"
        f"Appointment Details:\n"
        f"  Patient: {patient_info}\n"
        f"  Doctor: {doctor_name}\n"
        f"  Date: {date_str}\n"
        f"  Time: {time_str}\n"
        f"  Reference: {ref_number}{reason_line}{refund_block_plain}\n\n"
        f"You can book a new appointment at any time through your PulseLink account.\n\n"
        f"— The PulseLink Team"
    )

    html = f"""
    <div style="font-family:Poppins,sans-serif;max-width:540px;margin:auto;padding:32px;border:1px solid #e5e7eb;border-radius:12px;">
      <h2 style="color:#0d9488;margin-bottom:4px;">PulseLink</h2>
      <p style="color:#6b7280;font-size:13px;margin-top:0;">Healthcare, made simple.</p>
      <hr style="border:none;border-top:1px solid #e5e7eb;margin:20px 0;">
      <div style="background:#fef2f2;border:1px solid #fecaca;border-radius:10px;padding:14px;margin-bottom:20px;">
        <p style="margin:0;font-weight:700;color:#991b1b;font-size:14px;">Appointment Cancelled</p>
        {cancel_banner_html}
      </div>
      <p style="font-size:15px;color:#111827;">Hi <strong>{patient.first_name}</strong>,</p>
      <p style="font-size:14px;color:#374151;margin-top:8px;">
        {cancel_intro_html}
      </p>
      <div style="background:#f9fafb;border:1px solid #e5e7eb;border-radius:10px;padding:18px;margin:16px 0;">
        <table style="width:100%;">
          <tr><td style="color:#6b7280;padding:4px 0;width:100px;">Reference</td><td style="font-weight:700;color:#0d9488;font-family:monospace;padding:4px 0;">{ref_number}</td></tr>
          <tr><td style="color:#6b7280;padding:4px 0;">Patient</td><td style="font-weight:600;padding:4px 0;">{patient_info}</td></tr>
          <tr><td style="color:#6b7280;padding:4px 0;">Doctor</td><td style="font-weight:600;padding:4px 0;">{doctor_name}</td></tr>
          <tr><td style="color:#6b7280;padding:4px 0;">Date</td><td style="padding:4px 0;">{date_str}</td></tr>
          <tr><td style="color:#6b7280;padding:4px 0;">Time</td><td style="padding:4px 0;">{time_str}</td></tr>
          {f'<tr><td style="color:#6b7280;padding:4px 0;">Reason</td><td style="padding:4px 0;">{reason}</td></tr>' if reason else ''}
        </table>
      </div>
      {refund_block_html}
      <p style="font-size:13px;color:#6b7280;margin-top:20px;">
        You can book a new appointment at any time through your PulseLink account.
      </p>
      <div style="text-align:center;margin:24px 0;">
        <a href="{frontend_url}/patient/appointments" style="background:#0d9488;color:#fff;padding:11px 28px;border-radius:8px;text-decoration:none;font-weight:600;font-size:14px;">View My Appointments</a>
      </div>
      <p style="font-size:12px;color:#9ca3af;text-align:center;margin-top:24px;">PulseLink — Healthcare, made simple.</p>
    </div>
    """

    recipients = [patient.email]
    cancel_profile_email = getattr(apt.patient_profile, "email", "") if apt.patient_profile else ""
    if cancel_profile_email and cancel_profile_email.strip().lower() != patient.email.lower():
        recipients.append(cancel_profile_email.strip())

    logger.info("[TASK] Sending cancellation email to: %s", recipients)

    try:
        # Use EmailMultiAlternatives for HTML + plain text fallback
        email = EmailMultiAlternatives(
            subject=f"Appointment Cancelled{' & Refunded' if refund_issued else ''} — {date_str}",
            body=plain,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=recipients,
        )
        email.attach_alternative(html, "text/html")
        email.send(fail_silently=False)
        logger.info("[TASK SUCCESS] Cancellation email sent to %s for apt #%s", recipients, apt.pk)
    except Exception as exc:
        logger.exception("[TASK ERROR] Cancellation email failed for apt #%s: %s", apt.pk, exc)
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_doctor_cancellation_notification(self, appointment_id: int, reason: str = ""):
    """
    Notify doctor when a patient cancels or when doctor processes a refund.
    NowServing alignment: clear, professional notification.
    
    PRODUCTION-READY: Detailed logging, error handling, HTML email support.
    """
    logger.info("[TASK START] send_doctor_cancellation_notification: apt_id=%s", appointment_id)
    
    from appointments.models import Appointment
    from django.core.mail import EmailMultiAlternatives

    try:
        apt = Appointment.objects.select_related("patient", "doctor").get(pk=appointment_id)
        logger.info("[TASK] Appointment loaded: #%s, doctor=%s", apt.pk, apt.doctor.email)
    except Appointment.DoesNotExist:
        logger.error("[TASK ERROR] send_doctor_cancellation_notification: apt #%s not found", appointment_id)
        return
    except Exception as exc:
        logger.exception("[TASK ERROR] Failed to load appointment #%s: %s", appointment_id, exc)
        raise self.retry(exc=exc)

    patient      = apt.patient
    doctor       = apt.doctor
    date_str     = apt.date.strftime("%B %d, %Y")
    time_str     = apt.time.strftime("%I:%M %p").lstrip("0")
    ref_number   = f"APT-{str(apt.pk).zfill(8).upper()}"
    frontend_url = getattr(settings, "FRONTEND_URL", "http://localhost:3000")
    apt_url      = f"{frontend_url}/doctor/appointments/{apt.pk}"

    profile      = apt.patient_profile
    patient_name = (
        (f"{profile.first_name} {profile.last_name}".strip() if profile else "") or
        apt.booked_for_name or
        f"{patient.first_name} {patient.last_name}".strip()
    )
    patient_age    = profile.age if profile else ""
    patient_gender = profile.sex if profile else ""
    patient_info   = patient_name
    if patient_age:
        patient_info += f", {patient_age} years old"
    if patient_gender:
        patient_info += f", {patient_gender.capitalize()}"

    refund_line = ""
    if apt.payment_status == "refunded":
        refund_line = "\n\nA full refund has been issued to the patient's original payment method."

    reason_line = f"\n\nReason: {reason}" if reason else ""

    plain = (
        f"Hi Dr. {doctor.last_name},\n\n"
        f"The appointment with {patient_info} has been cancelled.\n\n"
        f"Appointment Details:\n"
        f"  Patient: {patient_info}\n"
        f"  Date: {date_str}\n"
        f"  Time: {time_str}\n"
        f"  Reference: {ref_number}{reason_line}{refund_line}\n\n"
        f"View appointment: {apt_url}\n\n"
        f"— The PulseLink Team"
    )

    html = f"""
    <div style="font-family:Poppins,sans-serif;max-width:540px;margin:auto;padding:32px;border:1px solid #e5e7eb;border-radius:12px;">
      <h2 style="color:#0d9488;margin-bottom:4px;">PulseLink</h2>
      <p style="color:#6b7280;font-size:13px;margin-top:0;">Healthcare, made simple.</p>
      <hr style="border:none;border-top:1px solid #e5e7eb;margin:20px 0;">
      <div style="background:#fef2f2;border:1px solid #fecaca;border-radius:10px;padding:14px;margin-bottom:20px;">
        <p style="margin:0;font-weight:700;color:#991b1b;font-size:14px;">Appointment Cancelled</p>
        <p style="margin:4px 0 0;font-size:13px;color:#7f1d1d;">{patient_info}'s appointment has been cancelled.</p>
      </div>
      <p style="font-size:15px;color:#111827;">Hi <strong>Dr. {doctor.last_name}</strong>,</p>
      <p style="font-size:14px;color:#374151;margin-top:8px;">
        The appointment with <strong>{patient_info}</strong> has been cancelled.
      </p>
      <div style="background:#f9fafb;border:1px solid #e5e7eb;border-radius:10px;padding:18px;margin:16px 0;">
        <table style="width:100%;">
          <tr><td style="color:#6b7280;padding:4px 0;width:100px;">Reference</td><td style="font-weight:700;color:#0d9488;font-family:monospace;padding:4px 0;">{ref_number}</td></tr>
          <tr><td style="color:#6b7280;padding:4px 0;">Patient</td><td style="font-weight:600;padding:4px 0;">{patient_info}</td></tr>
          <tr><td style="color:#6b7280;padding:4px 0;">Date</td><td style="padding:4px 0;">{date_str}</td></tr>
          <tr><td style="color:#6b7280;padding:4px 0;">Time</td><td style="padding:4px 0;">{time_str}</td></tr>
          {f'<tr><td style="color:#6b7280;padding:4px 0;">Reason</td><td style="padding:4px 0;">{reason}</td></tr>' if reason else ''}
        </table>
      </div>
      {f'<div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:10px;padding:14px;margin:16px 0;"><p style="margin:0;font-size:13px;color:#166534;">✓ A full refund has been issued to the patient.</p></div>' if apt.payment_status == 'refunded' else ''}
      <div style="text-align:center;margin:24px 0;">
        <a href="{apt_url}" style="background:#0d9488;color:#fff;padding:11px 28px;border-radius:8px;text-decoration:none;font-weight:600;font-size:14px;">View Appointment</a>
      </div>
      <p style="font-size:12px;color:#9ca3af;text-align:center;margin-top:24px;">PulseLink — Healthcare, made simple.</p>
    </div>
    """

    logger.info("[TASK] Sending doctor notification to: %s", doctor.email)

    try:
        email = EmailMultiAlternatives(
            subject=f"Appointment Cancelled — {patient_info} on {date_str}",
            body=plain,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[doctor.email],
        )
        email.attach_alternative(html, "text/html")
        email.send(fail_silently=False)
        logger.info("[TASK SUCCESS] Doctor cancellation notification sent to %s for apt #%s", doctor.email, apt.pk)
    except Exception as exc:
        logger.exception("[TASK ERROR] Doctor cancellation notification failed for apt #%s: %s", apt.pk, exc)
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def process_preconsult_reminders(self):
    """
    Sends 1h and 15m reminders (email + in-app).
    Runs every 5 minutes.
    """
    from appointments.models import Appointment

    now = timezone.now()
    window_1h_start = now + timezone.timedelta(minutes=55)
    window_1h_end   = now + timezone.timedelta(minutes=65)
    window_15m_start = now + timezone.timedelta(minutes=12)
    window_15m_end   = now + timezone.timedelta(minutes=18)

    # 1h reminders
    apts_1h = (
        Appointment.objects
        .filter(status__in=["confirmed", "pending"], reminder_1h_sent=False)
        .select_related("patient", "doctor")
    )
    for apt in apts_1h:
        apt_dt = _apt_datetime(apt)
        if window_1h_start <= apt_dt <= window_1h_end:
            _notify(
                apt.patient,
                title="Appointment Reminder (1 hour)",
                message=f"Your appointment with Dr. {apt.doctor.last_name} is in 1 hour.",
                data={"appointment_id": apt.pk},
            )
            _notify(
                apt.doctor,
                title="Upcoming Appointment (1 hour)",
                message=f"You have an appointment with {apt.patient.first_name} {apt.patient.last_name} in 1 hour.",
                data={"appointment_id": apt.pk},
            )
            _send_email(
                subject="PulseLink Reminder: Appointment in 1 hour",
                message=(
                    f"Hi {apt.patient.first_name},\n\n"
                    f"Your appointment with Dr. {apt.doctor.first_name} {apt.doctor.last_name} "
                    f"is in 1 hour on {apt.date} at {apt.time}.\n\n"
                    f"PulseLink"
                ),
                to_email=apt.patient.email,
            )
            apt.reminder_1h_sent = True
            apt.save(update_fields=["reminder_1h_sent"])

    # 15m reminders
    apts_15m = (
        Appointment.objects
        .filter(status__in=["confirmed", "pending"], reminder_15m_sent=False)
        .select_related("patient", "doctor")
    )
    for apt in apts_15m:
        apt_dt = _apt_datetime(apt)
        if window_15m_start <= apt_dt <= window_15m_end:
            _notify(
                apt.patient,
                title="Appointment Reminder (15 minutes)",
                message=f"Your appointment with Dr. {apt.doctor.last_name} starts in 15 minutes.",
                data={"appointment_id": apt.pk},
            )
            _notify(
                apt.doctor,
                title="Upcoming Appointment (15 minutes)",
                message=f"Your appointment with {apt.patient.first_name} {apt.patient.last_name} starts in 15 minutes.",
                data={"appointment_id": apt.pk},
            )
            _send_email(
                subject="PulseLink Reminder: Appointment in 15 minutes",
                message=(
                    f"Hi {apt.patient.first_name},\n\n"
                    f"Your appointment with Dr. {apt.doctor.first_name} {apt.doctor.last_name} "
                    f"starts in 15 minutes on {apt.date} at {apt.time}.\n\n"
                    f"PulseLink"
                ),
                to_email=apt.patient.email,
            )
            apt.reminder_15m_sent = True
            apt.save(update_fields=["reminder_15m_sent"])


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def auto_mark_no_shows(self):
    """
    Auto-mark no-show if appointment is confirmed and 15 minutes past schedule.
    Runs every 5 minutes.
    """
    from appointments.models import Appointment

    now = timezone.now()
    cutoff = now - timezone.timedelta(minutes=15)

    apts = (
        Appointment.objects
        .filter(status="confirmed")
        .select_related("patient", "doctor")
    )
    for apt in apts:
        if _apt_datetime(apt) <= cutoff:
            apt.status = "no_show"
            apt.save(update_fields=["status", "updated_at"])

            _notify(
                apt.patient,
                title="Marked as No-Show",
                message="We didn't detect a consult start within 15 minutes. Please rebook if needed.",
                data={"appointment_id": apt.pk},
            )
            _notify(
                apt.doctor,
                title="Patient No-Show",
                message=f"{apt.patient.first_name} {apt.patient.last_name} did not join the scheduled consult.",
                data={"appointment_id": apt.pk},
            )

            # Broadcast status change and queue update
            try:
                from channels.layers import get_channel_layer
                from asgiref.sync import async_to_sync
                channel_layer = get_channel_layer()
                async_to_sync(channel_layer.group_send)(
                    f"appointment_{apt.pk}",
                    {
                        "type": "status.changed",
                        "appointment_id": apt.pk,
                        "status": "no_show",
                    },
                )
            except Exception as exc:
                logger.warning("No-show broadcast failed: %s", exc)

            _broadcast_queue_update(apt.doctor_id, apt.date)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_appointment_confirmed_email(self, appointment_id: int):
    """
    Sent to patient when doctor accepts the booking.
    Includes patient details (booked_for info).
    """
    from appointments.models import Appointment

    try:
        apt = Appointment.objects.select_related(
            "patient", "doctor", "doctor__doctor_profile"
        ).get(pk=appointment_id)
    except Appointment.DoesNotExist:
        logger.warning("send_appointment_confirmed_email: apt #%s not found", appointment_id)
        return

    patient = apt.patient
    doctor = apt.doctor
    doctor_name = f"Dr. {doctor.first_name} {doctor.last_name}".strip()
    date_str = apt.date.strftime("%B %d, %Y")
    time_str = apt.time.strftime("%I:%M %p").lstrip("0")
    ref_number = f"APT-{str(apt.pk).zfill(8).upper()}"
    frontend_url = getattr(settings, "FRONTEND_URL", "http://localhost:3000")
    apt_url = f"{frontend_url}/patient/appointments/{apt.pk}"

    patient_name = apt.booked_for_name or f"{patient.first_name} {patient.last_name}".strip()
    profile = apt.patient_profile
    patient_age = profile.age if profile else ""
    patient_gender = profile.sex if profile else ""

    patient_info = f"{patient_name}"
    if patient_age:
        patient_info += f", {patient_age} years old"
    if patient_gender:
        patient_info += f", {patient_gender.capitalize()}"

    apt_type_label = {
        "online": "Online / Video",
        "in_clinic": "In-Clinic",
        "on_demand": "On-Demand",
    }.get(apt.type, apt.type.replace("_", " ").title())

    if apt.type == "in_clinic":
        snap = apt.clinic_info_snapshot or {}
        clinic_name = snap.get("clinic_name", "") or getattr(getattr(doctor, "doctor_profile", None), "clinic_name", "")
        clinic_address = snap.get("clinic_address", "") or getattr(getattr(doctor, "doctor_profile", None), "clinic_address", "")
        city = snap.get("city", "") or getattr(getattr(doctor, "doctor_profile", None), "city", "")
        location_line = ", ".join(filter(None, [clinic_name, clinic_address, city]))
        detail_html = (
            "<tr>"
            f"<td style='padding:5px 0;color:#6b7280;font-size:13px;width:130px;'>Clinic</td>"
            f"<td style='padding:5px 0;font-size:13px;font-weight:600;color:#111827;'>{location_line}</td>"
            "</tr>"
            "<tr>"
            "<td style='padding:5px 0;color:#6b7280;font-size:13px;'>Payment</td>"
            "<td style='padding:5px 0;font-size:13px;color:#111827;'>Pay at clinic upon arrival</td>"
            "</tr>"
        )
    else:
        fee_display = f"\u20b1{apt.effective_fee:,.2f}" if apt.effective_fee else (
            f"\u20b1{apt.fee:,.2f}" if apt.fee else "\u2014"
        )
        detail_html = (
            "<tr>"
            "<td style='padding:5px 0;color:#6b7280;font-size:13px;width:130px;'>Fee Paid</td>"
            f"<td style='padding:5px 0;font-size:13px;font-weight:600;color:#0d9488;'>{fee_display}</td>"
            "</tr>"
        )

    plain = (
        f"Hi {patient.first_name},\n\n"
        f"Your booking with {doctor_name} has been confirmed!\n\n"
        f"Patient: {patient_info}\n"
        f"Doctor: {doctor_name}\n"
        f"Date: {date_str}\nTime: {time_str}\n"
        f"Type: {apt_type_label}\n"
        f"Reference: {ref_number}\n\n"
        f"View: {apt_url}\n\n"
        f"— PulseLink Team"
    )

    html = f"""
    <div style="font-family:Poppins,sans-serif;max-width:540px;margin:auto;padding:32px;border:1px solid #e5e7eb;border-radius:12px;">
      <h2 style="color:#0d9488;">PulseLink</h2>
      <div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:10px;padding:14px;margin:16px 0;">
        <p style="margin:0;font-weight:700;color:#15803d;">✓ Booking Confirmed!</p>
        <p style="margin:4px 0 0;font-size:13px;color:#166534;">Your booking with <strong>{doctor_name}</strong> has been confirmed.</p>
      </div>
      <p>Hi <strong>{patient.first_name}</strong>,</p>
      <div style="background:#f9fafb;border:1px solid #e5e7eb;border-radius:10px;padding:18px;margin:16px 0;">
        <table style="width:100%;">
          <tr><td style="color:#6b7280;padding:4px 0;width:130px;">Reference</td><td style="font-weight:700;color:#0d9488;font-family:monospace;padding:4px 0;">{ref_number}</td></tr>
          <tr><td style="color:#6b7280;padding:4px 0;">Patient</td><td style="font-weight:600;padding:4px 0;">{patient_info}</td></tr>
          <tr><td style="color:#6b7280;padding:4px 0;">Doctor</td><td style="font-weight:600;padding:4px 0;">{doctor_name}</td></tr>
          <tr><td style="color:#6b7280;padding:4px 0;">Date</td><td style="padding:4px 0;">{date_str}</td></tr>
          <tr><td style="color:#6b7280;padding:4px 0;">Time</td><td style="padding:4px 0;">{time_str}</td></tr>
          <tr><td style="color:#6b7280;padding:4px 0;">Type</td><td style="padding:4px 0;">{apt_type_label}</td></tr>
          {detail_html}
        </table>
      </div>
      <div style="text-align:center;margin:20px 0;">
        <a href="{apt_url}" style="background:#0d9488;color:#fff;padding:11px 28px;border-radius:8px;text-decoration:none;font-weight:600;">View Appointment</a>
      </div>
    </div>
    """

    _notify(
        patient,
        title=f"Booking Confirmed — {doctor_name}",
        message=f"Your booking with {doctor_name} on {date_str} at {time_str} has been confirmed. Patient: {patient_info}",
        notif_type="appointment",
        data={"appointment_id": apt.pk, "reference": ref_number},
    )

    recipients = [patient.email]
    profile_email = profile.email if profile else ""
    if profile_email and profile_email.strip().lower() != patient.email.lower():
        recipients.append(profile_email.strip())

    try:
        from django.core.mail import send_mail as _send
        _send(
            subject=f"Your booking with {doctor_name} has been confirmed",
            message=plain,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=recipients,
            html_message=html,
            fail_silently=False,
        )
        logger.info("Confirmation email sent to %s for apt #%s", recipients, apt.pk)
    except Exception as exc:
        logger.warning("Confirmation email failed for apt #%s: %s", apt.pk, exc)
        raise self.retry(exc=exc)

