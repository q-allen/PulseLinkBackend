from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.conf import settings


class UserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("Email is required.")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("role", "admin")
        return self.create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    ROLE_CHOICES = [
        ("patient", "Patient"),
        ("doctor", "Doctor"),
        ("admin", "Admin"),
    ]

    email = models.EmailField(unique=True)
    first_name = models.CharField(max_length=150)
    middle_name = models.CharField(max_length=150, blank=True)
    last_name = models.CharField(max_length=150)
    birthdate = models.DateField(null=True, blank=True)
    phone = models.CharField(max_length=20, blank=True, default="")
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default="patient")

    # ── Health info (stored on User for patients) ─────────────────────────────
    blood_type = models.CharField(max_length=5, blank=True, default="")
    allergies  = models.JSONField(default=list, blank=True)
    gender     = models.CharField(max_length=10, blank=True, default="")

    avatar = models.ImageField(upload_to='avatars/', null=True, blank=True, max_length=500)

    # ── Profile completion (NowServing pattern: optional) ─────────────────────
    # False until the patient finishes onboarding; still optional to skip.
    # Keep blank=True so partial updates can omit this field safely.
    is_profile_complete = models.BooleanField(
        default=False,
        blank=True,
        help_text="Set True when the user finishes or skips onboarding.",
    )

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(auto_now_add=True)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["first_name", "last_name"]

    def __str__(self):
        return self.email


class FamilyMember(models.Model):
    """
    A saved family member profile belonging to a patient account.

    NowServing.ph pattern: one patient account can book for multiple
    family members (children, spouse, parents, etc.) without creating
    separate accounts. The booker (patient) remains responsible for
    payment and receives all notifications.

    Relationship choices mirror NowServing's booking-for-others flow.
    """

    GENDER_CHOICES = [
        ("male",   "Male"),
        ("female", "Female"),
        ("other",  "Other"),
    ]

    RELATIONSHIP_CHOICES = [
        ("spouse",  "Spouse"),
        ("child",   "Child"),
        ("parent",  "Parent"),
        ("sibling", "Sibling"),
        ("other",   "Other"),
    ]

    # The logged-in patient who owns this family member record
    patient      = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="family_members",
    )
    name         = models.CharField(max_length=200)
    age          = models.PositiveSmallIntegerField()
    gender       = models.CharField(max_length=10, choices=GENDER_CHOICES)
    relationship = models.CharField(max_length=10, choices=RELATIONSHIP_CHOICES, default="other")
    # Optional — useful for age-sensitive consultations (pediatrics, OB-GYN)
    birthdate    = models.DateField(null=True, blank=True)
    created_at   = models.DateTimeField(auto_now_add=True)
    updated_at   = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.relationship}) — {self.patient.email}"
