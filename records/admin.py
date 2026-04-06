from django.contrib import admin, messages

from .models import CertificateRequest, LabResult, MedicalCertificate, Prescription


@admin.register(Prescription)
class PrescriptionAdmin(admin.ModelAdmin):
    list_display  = ("id", "patient", "doctor", "diagnosis", "date", "valid_until")
    search_fields = ("patient__email", "doctor__email", "diagnosis")
    ordering      = ("-created_at",)


@admin.register(LabResult)
class LabResultAdmin(admin.ModelAdmin):
    list_display  = ("id", "patient", "doctor", "test_name", "status", "date")
    list_filter   = ("status",)
    search_fields = ("patient__email", "test_name")
    ordering      = ("-created_at",)
    actions       = ["mark_completed"]

    @admin.action(description="✅ Mark selected lab results as Completed")
    def mark_completed(self, request, queryset):
        updated = queryset.exclude(status="completed").update(status="completed")
        self.message_user(request, f"{updated} lab result(s) marked as completed.", messages.SUCCESS)


@admin.register(MedicalCertificate)
class MedicalCertificateAdmin(admin.ModelAdmin):
    list_display  = ("id", "patient", "doctor", "purpose", "date", "valid_until")
    search_fields = ("patient__email", "doctor__email")
    ordering      = ("-created_at",)
    readonly_fields = ("created_at",)


@admin.register(CertificateRequest)
class CertificateRequestAdmin(admin.ModelAdmin):
    list_display  = ("id", "patient", "doctor", "purpose", "status", "created_at")
    list_filter   = ("status",)
    search_fields = ("patient__email", "doctor__email", "purpose")
    ordering      = ("-created_at",)
    readonly_fields = ("created_at", "updated_at")
