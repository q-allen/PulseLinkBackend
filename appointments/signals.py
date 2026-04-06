"""
appointments/signals.py

Post-save signal: when an appointment moves to 'completed',
save the consult transcript to records if provided.
"""

from django.db.models.signals import post_save
from django.dispatch import receiver


@receiver(post_save, sender="appointments.Appointment")
def on_appointment_completed(sender, instance, created, **kwargs):
    if created or instance.status != "completed":
        return
    if not instance.consult_transcript:
        return
    # Persist transcript as a system chat message in the conversation if one exists
    try:
        from chat.models import Conversation, Message
        conv = Conversation.objects.filter(
            patient=instance.patient, doctor=instance.doctor
        ).first()
        if conv:
            Message.objects.get_or_create(
                conversation=conv,
                type="system",
                content=f"[Consult transcript — {instance.date}]\n{instance.consult_transcript}",
                defaults={"sender": instance.doctor},
            )
    except Exception:
        pass
