"""
chat/admin.py

Conversation admin with inline messages and unread_count column.
Message admin with file preview link.
"""

from django.contrib import admin
from django.utils.html import format_html

from .models import Conversation, Message


class MessageInline(admin.TabularInline):
    model          = Message
    extra          = 0
    readonly_fields = ("sender", "type", "content", "file_preview", "file_size", "is_read", "timestamp")
    fields          = ("sender", "type", "content", "file_preview", "file_size", "is_read", "timestamp")
    ordering        = ("timestamp",)
    can_delete      = False

    def file_preview(self, obj):
        if obj.file:
            return format_html('<a href="{}" target="_blank">{}</a>', obj.file.url, obj.file_name or "Download")
        return "—"
    file_preview.short_description = "File"


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display   = ("id", "patient", "doctor", "message_count", "unread_for_doctor", "updated_at")
    search_fields  = ("patient__email", "patient__first_name", "doctor__email", "doctor__first_name")
    ordering       = ("-updated_at",)
    readonly_fields = ("created_at", "updated_at")
    inlines        = [MessageInline]

    def message_count(self, obj):
        return obj.messages.count()
    message_count.short_description = "Messages"

    def unread_for_doctor(self, obj):
        """Unread messages from patient that doctor hasn't read yet."""
        return obj.messages.filter(is_read=False).exclude(sender=obj.doctor).count()
    unread_for_doctor.short_description = "Unread (doctor)"


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display   = ("id", "conversation", "sender", "type", "short_content", "is_read", "timestamp")
    list_filter    = ("type", "is_read")
    search_fields  = ("sender__email", "content")
    ordering       = ("-timestamp",)
    readonly_fields = ("conversation", "sender", "timestamp", "file_size")

    def short_content(self, obj):
        return (obj.content[:60] + "…") if len(obj.content) > 60 else obj.content or f"[{obj.type}]"
    short_content.short_description = "Content"
