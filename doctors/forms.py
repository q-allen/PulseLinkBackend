import re

from django import forms
from users.models import User
from .models import DoctorProfile

PHONE_REGEX = re.compile(r"^\+639\d{9}$")


class InviteDoctorForm(forms.Form):
    first_name  = forms.CharField(max_length=150, label="First Name")
    middle_name = forms.CharField(max_length=150, label="Middle Name", required=False)
    last_name   = forms.CharField(max_length=150, label="Last Name")
    email       = forms.EmailField(label="Email Address")
    phone       = forms.CharField(max_length=20, label="Phone (+639XXXXXXXXX)")
    specialty   = forms.CharField(max_length=100, label="Specialty")
    clinic_name = forms.CharField(max_length=200, label="Clinic Name")
    prc_license = forms.CharField(max_length=20, label="PRC License Number")

    def clean_email(self):
        value = self.cleaned_data["email"]
        if User.objects.filter(email=value).exists():
            raise forms.ValidationError("A user with this email already exists.")
        return value

    def clean_phone(self):
        value = self.cleaned_data["phone"]
        if not PHONE_REGEX.match(value):
            raise forms.ValidationError("Phone must be in format: +639XXXXXXXXX")
        return value

    def clean_prc_license(self):
        value = self.cleaned_data["prc_license"]
        if DoctorProfile.objects.filter(prc_license=value).exists():
            raise forms.ValidationError("A doctor with this PRC license already exists.")
        return value
