"""
chat/serializers.py

MessageSerializer       — full message detail including read_at for ✓✓ receipts.
ConversationSerializer  — conversation list card with last_message preview
                          and per-viewer unread_count (passed via context).
"""

from rest_framework import serializers
from .models import Conversation, Message


class MessageSerializer(serializers.ModelSerializer):
    sender_name = serializers.SerializerMethodField()
    sender_role = serializers.SerializerMethodField()
    file_url    = serializers.SerializerMethodField()

    class Meta:
        model  = Message
        fields = [
            "id", "conversation",
            "sender", "sender_name", "sender_role",
            "content", "type",
            "file_url", "file_name", "file_size",
            # Read receipt fields — is_read drives ✓/✓✓ in frontend
            "is_read", "read_at",
            "timestamp",
        ]
        read_only_fields = [
            "id", "sender", "sender_name", "sender_role",
            "file_url", "timestamp", "read_at",
        ]

    def get_sender_name(self, obj):
        u = obj.sender
        return f"{u.first_name} {u.last_name}".strip() or u.email

    def get_sender_role(self, obj):
        return obj.sender.role

    def get_file_url(self, obj):
        request = self.context.get("request")
        if obj.file and request:
            return request.build_absolute_uri(obj.file.url)
        return None


class ConversationSerializer(serializers.ModelSerializer):
    patient_name   = serializers.SerializerMethodField()
    doctor_name    = serializers.SerializerMethodField()
    patient_avatar = serializers.SerializerMethodField()
    doctor_avatar  = serializers.SerializerMethodField()
    doctor_specialty = serializers.SerializerMethodField()
    # Expose IDs so frontend mapper can build participant arrays
    patient_id   = serializers.IntegerField(read_only=True)
    doctor_id    = serializers.IntegerField(read_only=True)
    last_message = serializers.SerializerMethodField()
    unread_count = serializers.SerializerMethodField()

    class Meta:
        model  = Conversation
        fields = [
            "id", "patient", "doctor",
            "patient_id", "doctor_id",
            "patient_name", "doctor_name",
            "patient_avatar", "doctor_avatar",
            "doctor_specialty",
            "last_message", "unread_count",
            "created_at", "updated_at",
        ]

    def get_patient_name(self, obj):
        return f"{obj.patient.first_name} {obj.patient.last_name}".strip()

    def get_doctor_name(self, obj):
        return f"Dr. {obj.doctor.first_name} {obj.doctor.last_name}".strip()

    def get_patient_avatar(self, obj):
        return None  # patients have no avatar field yet

    def get_doctor_avatar(self, obj):
        request = self.context.get("request")
        try:
            photo = obj.doctor.doctor_profile.profile_photo
            if photo and request:
                return request.build_absolute_uri(photo.url)
        except Exception:
            pass
        return None

    def get_doctor_specialty(self, obj):
        try:
            return obj.doctor.doctor_profile.specialty
        except Exception:
            return None

    def get_last_message(self, obj):
        msg = obj.last_message
        if not msg:
            return None
        request  = self.context.get("request")
        file_url = None
        if msg.file and request:
            file_url = request.build_absolute_uri(msg.file.url)
        return {
            "id":        msg.pk,
            "content":   msg.content,
            "type":      msg.type,
            "file_url":  file_url,
            "sender_id": msg.sender_id,
            "is_read":   msg.is_read,
            "timestamp": msg.timestamp,
        }

    def get_unread_count(self, obj):
        """
        Per-viewer unread count — symmetric for patient and doctor.
        Viewer is passed via serializer context.
        """
        viewer = self.context.get("request") and self.context["request"].user
        if viewer and viewer.is_authenticated:
            return obj.unread_count(viewer)
        # Admin / no-context fallback
        return obj.messages.filter(is_read=False).exclude(sender=obj.patient).count()
