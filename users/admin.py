from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.forms import UserChangeForm, UserCreationForm
from django.utils.html import format_html

from .models import User


class CustomUserCreationForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model  = User
        fields = ("email", "first_name", "middle_name", "last_name", "birthdate", "phone", "role")


class CustomUserChangeForm(UserChangeForm):
    class Meta(UserChangeForm.Meta):
        model  = User
        fields = "__all__"


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    form     = CustomUserChangeForm
    add_form = CustomUserCreationForm

    list_display       = ("email", "full_name", "role_badge", "active_badge", "is_staff", "date_joined")
    list_filter        = ("role", "is_active", "is_staff")
    search_fields      = ("email", "first_name", "last_name")
    ordering           = ("-date_joined",)
    list_display_links = ("email",)
    list_per_page      = 25
    show_full_result_count = True

    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Personal Info", {
            "fields": ("first_name", "middle_name", "last_name", "birthdate", "phone", "role"),
        }),
        ("Profile", {
            "fields": ("avatar_preview", "avatar", "blood_type", "allergies", "gender", "is_profile_complete"),
        }),
        ("Permissions", {
            "fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions"),
        }),
        ("Important Dates", {"fields": ("last_login", "date_joined")}),
    )
    readonly_fields = ("date_joined", "last_login", "avatar_preview")

    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": (
                "email", "first_name", "middle_name", "last_name",
                "birthdate", "phone", "role",
                "password1", "password2",
            ),
        }),
    )

    @admin.display(description="Current Avatar")
    def avatar_preview(self, obj):
        if not obj.avatar:
            return "No avatar uploaded"
        url = obj.avatar.name
        if not url.startswith(("http://", "https://")):
            url = obj.avatar.url
        return format_html('<img src="{}" style="max-height:120px;border-radius:50%;" />', url)

    @admin.display(description="Name", ordering="last_name")
    def full_name(self, obj):
        name = f"{obj.first_name} {obj.last_name}".strip()
        return format_html('<strong style="color:#0f172a">{}</strong>', name or "—")

    @admin.display(description="Role", ordering="role")
    def role_badge(self, obj):
        mapping = {
            "doctor":  ("badge-doctor",  "🩺 Doctor"),
            "patient": ("badge-patient", "👤 Patient"),
            "admin":   ("badge-admin",   "🔑 Admin"),
        }
        css, label = mapping.get(obj.role, ("badge-inactive", obj.role.title()))
        return format_html('<span class="badge-status {}">{}</span>', css, label)

    @admin.display(description="Active", ordering="is_active")
    def active_badge(self, obj):
        if obj.is_active:
            return format_html('<span class="badge-status badge-active">{}</span>', "✓ Active")
        return format_html('<span class="badge-status badge-inactive">{}</span>', "✗ Inactive")
