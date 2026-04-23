from django.core.mail import send_mail
from django.conf import settings


def send_otp_email(email: str, otp: str, purpose: str = "verify your email") -> None:
    subject = "Your PulseLink verification code"
    plain = f"Your OTP to {purpose} is: {otp}\n\nThis code expires in 10 minutes. Do not share it with anyone."
    html = f"""
    <div style="font-family:Poppins,sans-serif;max-width:480px;margin:auto;padding:32px;border:1px solid #e5e7eb;border-radius:12px;">
      <h2 style="color:#0d9488;margin-bottom:4px;">PulseLink</h2>
      <p style="color:#6b7280;font-size:14px;margin-top:0;">Your health, our priority.</p>
      <hr style="border:none;border-top:1px solid #e5e7eb;margin:24px 0;">
      <p style="font-size:15px;color:#111827;">We're happy to help! Use the code below to {purpose}:</p>
      <div style="letter-spacing:8px;font-size:36px;font-weight:700;color:#0d9488;text-align:center;padding:16px 0;">
        {otp}
      </div>
      <p style="font-size:13px;color:#6b7280;text-align:center;">This code expires in <strong>10 minutes</strong>. Please do not share it with anyone.</p>
      <hr style="border:none;border-top:1px solid #e5e7eb;margin:24px 0;">
      <p style="font-size:12px;color:#9ca3af;text-align:center;">If you didn't request this, you can safely ignore this email.</p>
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

