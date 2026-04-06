from django.conf import settings
from django.db import models


class Prescription(models.Model):
    appointment  = models.ForeignKey("appointments.Appointment", on_delete=models.SET_NULL, null=True, blank=True, related_name="prescriptions")
    patient      = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="prescriptions")
    doctor       = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="issued_prescriptions")
    date         = models.DateField(auto_now_add=True)
    diagnosis    = models.TextField()
    medications  = models.JSONField(default=list)
    instructions = models.TextField(blank=True)
    valid_until  = models.DateField()
    pdf_file     = models.FileField(upload_to="prescriptions/", null=True, blank=True, max_length=500)
    is_digital   = models.BooleanField(default=True)
    created_at   = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Rx #{self.pk} \u2014 {self.patient}"


class LabResult(models.Model):
    STATUS_CHOICES = [
        ("pending",    "Pending"),
        ("processing", "Processing"),
        ("completed",  "Completed"),
    ]

    patient     = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="lab_results")
    doctor      = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="requested_labs")
    appointment = models.ForeignKey("appointments.Appointment", on_delete=models.SET_NULL, null=True, blank=True, related_name="lab_results")
    test_name   = models.CharField(max_length=200)
    test_type   = models.CharField(max_length=100)
    date        = models.DateField(auto_now_add=True)
    status      = models.CharField(max_length=12, choices=STATUS_CHOICES, default="pending")
    results     = models.JSONField(default=list, blank=True)
    notes       = models.TextField(blank=True)
    file        = models.FileField(upload_to="lab_results/", null=True, blank=True, max_length=500)
    laboratory  = models.CharField(max_length=200, blank=True)
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Lab #{self.pk} \u2014 {self.test_name} for {self.patient}"


class MedicalCertificate(models.Model):
    appointment = models.ForeignKey("appointments.Appointment", on_delete=models.SET_NULL, null=True, blank=True, related_name="certificates")
    patient     = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="certificates")
    doctor      = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="issued_certificates")
    date        = models.DateField(auto_now_add=True)
    purpose     = models.CharField(max_length=300)
    diagnosis   = models.TextField()
    rest_days   = models.PositiveIntegerField(default=0)
    valid_from  = models.DateField()
    valid_until = models.DateField()
    pdf_file    = models.FileField(upload_to="certificates/", null=True, blank=True, max_length=500)
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Cert #{self.pk} \u2014 {self.patient}"


class ConsultTranscript(models.Model):
    """Post-consult transcript/summary saved by doctor."""

    appointment = models.OneToOneField(
        "appointments.Appointment", on_delete=models.CASCADE, related_name="consult_transcript_record"
    )
    patient     = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="consult_transcripts")
    doctor      = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="consult_transcripts_issued")
    notes       = models.TextField(blank=True)
    summary     = models.TextField(blank=True)
    duration_seconds = models.PositiveIntegerField(default=0)
    created_at  = models.DateTimeField(auto_now_add=True)
    updated_at  = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Transcript #{self.pk} — Apt #{self.appointment_id}"


class CertificateRequest(models.Model):
    """Patient requests a medical certificate; doctor approves and issues it."""

    STATUS_CHOICES = [
        ("pending",  "Pending"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
    ]

    patient     = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="cert_requests")
    doctor      = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="cert_requests_received")
    appointment = models.ForeignKey("appointments.Appointment", on_delete=models.SET_NULL, null=True, blank=True, related_name="cert_requests")
    purpose     = models.CharField(max_length=300)
    notes       = models.TextField(blank=True)
    status      = models.CharField(max_length=10, choices=STATUS_CHOICES, default="pending")
    certificate = models.ForeignKey(MedicalCertificate, on_delete=models.SET_NULL, null=True, blank=True, related_name="request")
    created_at  = models.DateTimeField(auto_now_add=True)
    updated_at  = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"CertReq #{self.pk} \u2014 {self.patient} \u2192 {self.doctor}"
