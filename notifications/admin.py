from django.contrib import admin
from django.utils.html import format_html

from .models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display  = ("id", "user", "type", "title", "read_badge", "created_at")
    list_filter   = ("type", "is_read")
    search_fields = ("user__email", "title")
    ordering      = ("-created_at",)
    list_per_page = 25

    @admin.display(description="Read", ordering="is_read")
    def read_badge(self, obj):
        if obj.is_read:
            return format_html('<span class="badge-status badge-active">{}</span>', "✓ Read")
        return format_html('<span class="badge-status badge-pending">{}</span>', "● Unread")
