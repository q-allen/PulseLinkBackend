import re
from datetime import date

from django.contrib.auth import authenticate
from django.core.cache import cache
from rest_framework import serializers

from .models import FamilyMember, User

PHONE_REGEX = re.compile(r"^\+639\d{9}$")

BLOOD_TYPES = ["A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"]
GENDER_CHOICES = ["male", "female", "other"]


class PatientDetailSerializer(serializers.ModelSerializer):
    """
    Read serializer for patient details as seen by a doctor.
    Returns the fields needed for the doctor's Patients page.
    """
    class Meta:
        model = User
        fields = [
            "id", "email",
            "first_name", "middle_name", "last_name",
            "phone", "birthdate", "gender",
            "blood_type", "allergies",
        ]


class FamilyMemberSerializer(serializers.ModelSerializer):
    """
    Read/write serializer for FamilyMember.
    Used nested inside UserSerializer (read-only) and standalone for CRUD.
    """
    class Meta:
        model = FamilyMember
        fields = ["id", "name", "age", "gender", "relationship", "birthdate"]
        read_only_fields = ["id"]


class UserSerializer(serializers.ModelSerializer):
    """
    Full read serializer for GET /api/auth/me/.
    Returns all patient-facing fields including nested family members.
    NowServing pattern: one call hydrates the entire patient store.
    """
    family_members = FamilyMemberSerializer(many=True, read_only=True)
    avatar = serializers.SerializerMethodField()

    def get_avatar(self, obj):
        if not obj.avatar:
            return None
        url = obj.avatar.name if hasattr(obj.avatar, 'name') else str(obj.avatar)
        # Already a full Cloudinary URL stored in DB
        if url.startswith('http'):
            return url
        # Fallback: let the field generate the URL
        try:
            return obj.avatar.url
        except Exception:
            return None

    class Meta:
        model = User
        fields = [
            "id", "email",
            "first_name", "middle_name", "last_name",
            "phone", "birthdate", "gender",
            "blood_type", "allergies",
            "role", "is_profile_complete",
            "avatar",
            "family_members",
        ]


def validate_password_strength(value: str) -> str:
    """
    Validate password strength with user-friendly error messages.
    NowServing pattern: clear, helpful feedback for password requirements.
    """
    errors = []
    
    if len(value) < 8:
        errors.append("at least 8 characters")
    if not re.search(r"[A-Z]", value):
        errors.append("one uppercase letter")
    if not re.search(r"[a-z]", value):
        errors.append("one lowercase letter")
    if not re.search(r"\d", value):
        errors.append("one number")
    
    if errors:
        raise serializers.ValidationError(
            f"Password must contain {', '.join(errors)}."
        )
    return value


class SendOtpSerializer(serializers.Serializer):
    email = serializers.EmailField(
        error_messages={
            'required': 'Please enter your email address.',
            'invalid': 'Please enter a valid email address.'
        }
    )


class RegisterSerializer(serializers.Serializer):
    email      = serializers.EmailField(
        error_messages={
            'required': 'Email address is required.',
            'invalid': 'Please enter a valid email address.'
        }
    )
    password   = serializers.CharField(
        min_length=8,
        write_only=True,
        error_messages={
            'required': 'Password is required.',
            'min_length': 'Password must be at least 8 characters long.'
        }
    )
    firstName  = serializers.CharField(
        source="first_name",
        error_messages={
            'required': 'First name is required.',
            'blank': 'First name cannot be empty.'
        }
    )
    middleName = serializers.CharField(
        source="middle_name",
        required=False,
        allow_blank=True,
        default=""
    )
    lastName   = serializers.CharField(
        source="last_name",
        error_messages={
            'required': 'Last name is required.',
            'blank': 'Last name cannot be empty.'
        }
    )
    birthdate  = serializers.DateField(
        error_messages={
            'required': 'Date of birth is required.',
            'invalid': 'Please enter a valid date (YYYY-MM-DD).'
        }
    )
    phone      = serializers.CharField(
        error_messages={
            'required': 'Mobile number is required.',
            'blank': 'Mobile number cannot be empty.'
        }
    )
    role       = serializers.ChoiceField(choices=["patient"])
    otp        = serializers.CharField(
        write_only=True,
        error_messages={
            'required': 'Please enter the verification code.',
            'blank': 'Verification code cannot be empty.'
        }
    )

    def validate_email(self, value):
        """Check if email is already registered with helpful message."""
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError(
                "This email is already registered. Please sign in or use a different email."
            )
        return value

    def validate_password(self, value):
        return validate_password_strength(value)

    def validate_phone(self, value):
        """
        Validate Philippine mobile number with flexible format support.
        Accepts: +639XXXXXXXXX or 09XXXXXXXXX
        """
        # Clean the input
        cleaned = value.strip().replace(' ', '').replace('-', '')
        
        # Convert 09XX format to +639XX
        if cleaned.startswith('09') and len(cleaned) == 11:
            cleaned = '+63' + cleaned[1:]
        
        # Validate E.164 format
        if not PHONE_REGEX.match(cleaned):
            raise serializers.ValidationError(
                "Please enter a valid Philippine mobile number (e.g., +639171234567 or 09171234567)."
            )
        
        # Return normalized format
        return cleaned

    def validate_birthdate(self, value):
        """Validate age requirement with clear, friendly message."""
        today = date.today()
        age = today.year - value.year - ((today.month, today.day) < (value.month, value.day))
        
        if age < 18:
            raise serializers.ValidationError(
                "You must be at least 18 years old to register. If you're under 18, please ask a parent or guardian to create an account."
            )
        
        if age > 120:
            raise serializers.ValidationError(
                "Please enter a valid date of birth."
            )
        
        return value

    def validate(self, attrs):
        """Validate OTP with clear error messages."""
        email = attrs.get("email")
        otp   = attrs.pop("otp")
        cached_otp = cache.get(f"otp:{email}")
        
        if not cached_otp:
            raise serializers.ValidationError({
                "otp": "Your verification code has expired. Please request a new one."
            })
        
        if otp != cached_otp:
            raise serializers.ValidationError({
                "otp": "The verification code you entered is incorrect. Please check and try again."
            })
        
        cache.delete(f"otp:{email}")
        return attrs

    def create(self, validated_data):
        password = validated_data.pop("password")
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        return user


class ForgotPasswordSerializer(serializers.Serializer):
    email = serializers.EmailField(
        error_messages={
            'required': 'Please enter your email address.',
            'invalid': 'Please enter a valid email address.'
        }
    )

    def validate_email(self, value):
        """Check if account exists with helpful message."""
        if not User.objects.filter(email=value).exists():
            raise serializers.ValidationError(
                "We couldn't find an account with this email. Please check your email or sign up for a new account."
            )
        return value


class ResetPasswordSerializer(serializers.Serializer):
    email        = serializers.EmailField(
        error_messages={
            'required': 'Email address is required.',
            'invalid': 'Please enter a valid email address.'
        }
    )
    otp          = serializers.CharField(
        write_only=True,
        error_messages={
            'required': 'Please enter the verification code.',
            'blank': 'Verification code cannot be empty.'
        }
    )
    new_password = serializers.CharField(
        min_length=8,
        write_only=True,
        error_messages={
            'required': 'New password is required.',
            'min_length': 'Password must be at least 8 characters long.'
        }
    )

    def validate_new_password(self, value):
        return validate_password_strength(value)

    def validate(self, attrs):
        """Validate OTP for password reset with clear messages."""
        email = attrs["email"]
        otp   = attrs.pop("otp")
        cached_otp = cache.get(f"otp:{email}")
        
        if not cached_otp:
            raise serializers.ValidationError({
                "otp": "Your verification code has expired. Please request a new one."
            })
        
        if otp != cached_otp:
            raise serializers.ValidationError({
                "otp": "The verification code you entered is incorrect. Please check and try again."
            })
        
        cache.delete(f"otp:{email}")
        return attrs

    def save(self):
        user = User.objects.get(email=self.validated_data["email"])
        user.set_password(self.validated_data["new_password"])
        user.save(update_fields=["password"])
        return user


class LoginSerializer(serializers.Serializer):
    email    = serializers.EmailField(
        error_messages={
            'required': 'Please enter your email address.',
            'invalid': 'Please enter a valid email address.'
        }
    )
    password = serializers.CharField(
        write_only=True,
        error_messages={
            'required': 'Please enter your password.',
            'blank': 'Password cannot be empty.'
        }
    )

    def validate(self, attrs):
        """Authenticate user with clear error messages."""
        user = authenticate(username=attrs["email"], password=attrs["password"])
        
        if not user:
            raise serializers.ValidationError(
                "The email or password you entered is incorrect. Please try again."
            )
        
        if not user.is_active:
            raise serializers.ValidationError(
                "Your account has been deactivated. Please contact support for assistance."
            )
        
        attrs["user"] = user
        return attrs


class ProfileCompletionSerializer(serializers.ModelSerializer):
    """
    PATCH /api/auth/me/complete/

    Patient onboarding wizard — partial update for User fields.
    NowServing.ph pattern: patients fill in health info after registration
    before they can book their first appointment.

    Required fields (wizard Step 1):
      - first_name, last_name, phone, birthdate, gender

    Optional fields (wizard Steps 2-3):
      - blood_type, allergies (health info)
      - HMO cards and family members are handled by separate endpoints

    Setting is_profile_complete=True unlocks the full patient dashboard.
    """

    allergies = serializers.ListField(
        child=serializers.CharField(max_length=100),
        required=False,
        allow_empty=True,
        allow_null=True,
        default=list,
    )

    class Meta:
        model = User
        fields = [
            "first_name",
            "middle_name",
            "last_name",
            "phone",
            "birthdate",
            "gender",
            "blood_type",
            "allergies",
            "is_profile_complete",
        ]
        extra_kwargs = {
            "first_name":  {"required": False, "allow_blank": True},
            "middle_name": {"required": False, "allow_blank": True},
            "last_name":   {"required": False, "allow_blank": True},
            "phone":       {"required": False, "allow_blank": True},
            "birthdate":   {"required": False, "allow_null": True},
            "gender":      {"required": False, "allow_blank": True},
            "blood_type":  {"required": False, "allow_blank": True},
            "is_profile_complete": {"required": False},
        }

    def validate_phone(self, value):
        """Validate phone with flexible format support."""
        if value:
            # Clean the input
            cleaned = value.strip().replace(' ', '').replace('-', '')
            
            # Convert 09XX format to +639XX
            if cleaned.startswith('09') and len(cleaned) == 11:
                cleaned = '+63' + cleaned[1:]
            
            if not PHONE_REGEX.match(cleaned):
                raise serializers.ValidationError(
                    "Please enter a valid Philippine mobile number (e.g., +639171234567 or 09171234567)."
                )
        return value

    def validate_gender(self, value):
        if value and value not in GENDER_CHOICES:
            raise serializers.ValidationError(f"Gender must be one of: {GENDER_CHOICES}")
        return value

    def validate_blood_type(self, value):
        if value and value not in BLOOD_TYPES:
            raise serializers.ValidationError(f"Blood type must be one of: {BLOOD_TYPES}")
        return value

    def validate_birthdate(self, value):
        """Validate age requirement for profile completion."""
        if value:
            today = date.today()
            age = today.year - value.year - ((today.month, today.day) < (value.month, value.day))
            if age < 18:
                raise serializers.ValidationError(
                    "You must be at least 18 years old."
                )
            if age > 120:
                raise serializers.ValidationError(
                    "Please enter a valid date of birth."
                )
        return value

    def validate(self, attrs):
        """
        NowServing pattern: is_profile_complete=True can always be set,
        even if optional fields are missing. Patients can skip the wizard
        and book immediately — only name/phone/birthdate/gender are
        encouraged but never enforced at the API level.
        """
        return attrs

    def update(self, instance, validated_data):
        if not validated_data:
            return instance
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save(update_fields=list(validated_data.keys()))
        return instance
