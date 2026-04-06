"""
chat/models.py

NowServing-style 1:1 private messaging between patient and doctor.

Conversation  — unique patient↔doctor pair (enforced via unique_together).
Message       — individual message with read receipt fields:
                  is_read   → False until receiver opens the chat
                  read_at   → timestamp when marked read (for "read at 3:45 PM" display)

Design notes:
- unread_count(viewer) is a method so it works symmetrically for both roles.
- DB indexes on (conversation, timestamp) keep message fetch fast.
- file_size stored at write time so clients skip a HEAD request.
- Message.Meta.ordering = ["timestamp"] ensures chronological display.
"""

from django.conf import settings
from django.db import models


class Conversation(models.Model):
    patient    = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="patient_conversations"
    )
    doctor     = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="doctor_conversations"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        # Enforce 1:1 private channel — mirrors NowServing's patient↔doctor thread model
        unique_together = ("patient", "doctor")
        ordering        = ["-updated_at"]
        indexes         = [
            models.Index(fields=["patient", "updated_at"], name="chat_conv_patient_idx"),
            models.Index(fields=["doctor",  "updated_at"], name="chat_conv_doctor_idx"),
        ]

    def __str__(self):
        return f"Conv #{self.pk}: {self.patient} ↔ {self.doctor}"

    def unread_count(self, viewer) -> int:
        """
        Messages sent by the OTHER party that this viewer hasn't read yet.
        Symmetric: works correctly for both patient and doctor viewers.

        Uses a simple filter — no select_for_update needed here since this is
        a read-only count query used for badge display only.
        """
        return self.messages.filter(is_read=False).exclude(sender=viewer).count()

    @property
    def last_message(self):
        """Most recent message — used for conversation list preview."""
        return self.messages.order_by("-timestamp").first()


class Message(models.Model):
    TYPE_CHOICES = [
        ("text",         "Text"),
        ("image",        "Image"),
        ("file",         "File"),
        ("prescription", "Prescription"),
        ("system",       "System"),
    ]

    conversation = models.ForeignKey(
        Conversation, on_delete=models.CASCADE, related_name="messages"
    )
    sender       = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="sent_messages"
    )
    content      = models.TextField(blank=True)
    type         = models.CharField(max_length=14, choices=TYPE_CHOICES, default="text")
    file         = models.FileField(upload_to="chat_files/", null=True, blank=True, max_length=500)
    file_name    = models.CharField(max_length=255, blank=True)
    file_size    = models.PositiveIntegerField(
        null=True, blank=True, help_text="File size in bytes, stored at upload time."
    )

    # Read receipt fields — NowServing shows ✓ (sent) / ✓✓ (read)
    is_read  = models.BooleanField(default=False, db_index=True)
    read_at  = models.DateTimeField(null=True, blank=True)

    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        # Ascending timestamp = chronological chat order (oldest at top, newest at bottom)
        ordering = ["timestamp"]
        indexes  = [
            # Primary fetch: all messages in a conversation ordered by time
            models.Index(fields=["conversation", "timestamp"], name="chat_msg_conv_ts_idx"),
            # Unread count query: filter by is_read + exclude sender
            models.Index(fields=["is_read", "sender"], name="chat_msg_unread_idx"),
        ]

    def __str__(self):
        return f"Msg #{self.pk} [{self.type}] in Conv #{self.conversation_id}"
