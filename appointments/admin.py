from django.contrib import admin, messages
from django.utils.html import format_html

from .models import Appointment, Review


@admin.register(Appointment)
class AppointmentAdmin(admin.ModelAdmin):
    list_display    = (
        "id", "patient", "doctor", "date", "time",
        "type_badge", "status_badge", "payment_badge",
        "queue_number", "is_on_demand",
    )
    list_filter     = ("status", "type", "payment_status", "is_on_demand", "date")
    search_fields   = ("patient__email", "patient__first_name", "doctor__email", "doctor__first_name")
    ordering        = ("-date", "queue_number")
    list_per_page   = 25
    show_full_result_count = True
    readonly_fields = (
        "created_at", "updated_at", "queue_number", "is_on_demand",
        "video_link", "video_room_id", "chat_room_id", "effective_fee",
    )
    actions = ["confirm_selected", "mark_no_show", "mark_completed"]

    fieldsets = (
        ("Appointment",  {"fields": ("patient", "doctor", "date", "time", "type", "queue_number", "is_on_demand")}),
        ("Status",       {"fields": ("status", "payment_status", "rejection_reason")}),
        ("Content",      {"fields": ("symptoms", "notes", "fee", "effective_fee", "pre_consult_files")}),
        ("HMO",          {"fields": ("hmo_provider", "hmo_coverage_percent")}),
        ("Online",       {"fields": ("video_link", "video_room_id", "chat_room_id")}),
        ("Reminders",    {"fields": ("reminder_24h_sent", "reminder_1h_sent")}),
        ("Transcript",   {"fields": ("consult_transcript",)}),
        ("Timestamps",   {"fields": ("created_at", "updated_at")}),
    )

    @admin.display(description="Type", ordering="type")
    def type_badge(self, obj):
        if obj.type == "online":
            return format_html('<span class="badge-status badge-online">{}</span>', "💻 Online")
        return format_html('<span class="badge-status badge-in_person">{}</span>', "🏥 In-Person")

    @admin.display(description="Status", ordering="status")
    def status_badge(self, obj):
        mapping = {
            "pending":     ("badge-pending",     "⏳ Pending"),
            "confirmed":   ("badge-confirmed",   "✓ Confirmed"),
            "in_progress": ("badge-in_progress", "▶ In Progress"),
            "completed":   ("badge-completed",   "✔ Completed"),
            "cancelled":   ("badge-cancelled",   "✗ Cancelled"),
            "no_show":     ("badge-no_show",     "⚠ No Show"),
        }
        css, label = mapping.get(obj.status, ("badge-inactive", obj.status))
        return format_html('<span class="badge-status {}">{}</span>', css, label)

    @admin.display(description="Payment", ordering="payment_status")
    def payment_badge(self, obj):
        if obj.payment_status == "paid":
            return format_html('<span class="badge-status badge-paid">{}</span>', "✓ Paid")
        return format_html('<span class="badge-status badge-unpaid">{}</span>', "✗ Unpaid")

    @admin.action(description="✅ Confirm selected appointments")
    def confirm_selected(self, request, queryset):
        updated = queryset.filter(status="pending").update(status="confirmed")
        self.message_user(request, f"{updated} appointment(s) confirmed.", messages.SUCCESS)

    @admin.action(description="🚫 Mark selected as No Show")
    def mark_no_show(self, request, queryset):
        updated = queryset.filter(status__in=["confirmed", "in_progress"]).update(status="no_show")
        self.message_user(request, f"{updated} appointment(s) marked as no-show.", messages.WARNING)

    @admin.action(description="✔️ Mark selected as Completed")
    def mark_completed(self, request, queryset):
        updated = queryset.filter(status="in_progress").update(status="completed")
        self.message_user(request, f"{updated} appointment(s) marked as completed.", messages.SUCCESS)


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display    = ("id", "patient", "doctor", "stars", "created_at")
    list_filter     = ("rating",)
    search_fields   = ("patient__email", "doctor__email")
    ordering        = ("-created_at",)
    readonly_fields = ("created_at",)

    @admin.display(description="Rating", ordering="rating")
    def stars(self, obj):
        stars = "★" * obj.rating + "☆" * (5 - obj.rating)
        return format_html('<span style="color:#f59e0b;font-size:1rem">{}</span>', stars)
