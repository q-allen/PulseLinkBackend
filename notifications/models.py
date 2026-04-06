from django.conf import settings
from django.db import models


class Notification(models.Model):
    TYPE_CHOICES = [
        ("appointment", "Appointment"),
        ("queue",       "Queue"),
        ("message",     "Message"),
        ("prescription","Prescription"),
        ("lab_result",  "Lab Result"),
        ("system",      "System"),
        ("pharmacy",    "Pharmacy"),
    ]

    user       = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications")
    type       = models.CharField(max_length=14, choices=TYPE_CHOICES, default="system")
    title      = models.CharField(max_length=255)
    message    = models.TextField()
    is_read    = models.BooleanField(default=False)
    data       = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Notif #{self.pk} → {self.user} [{self.type}]"
