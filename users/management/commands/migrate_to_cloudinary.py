"""
Management command to migrate existing local media files to Cloudinary.

Usage:
    python manage.py migrate_to_cloudinary
    python manage.py migrate_to_cloudinary --dry-run
"""

import os
import cloudinary
import cloudinary.uploader
from django.core.management.base import BaseCommand

from users.models import User
from doctors.models import DoctorProfile, PatientHMO
from records.models import Prescription, LabResult, MedicalCertificate
from pharmacy.models import Medicine, PharmacyPrescriptionUpload
from chat.models import Message

FIELDS = [
    (User,                       "avatar"),
    (DoctorProfile,              "profile_photo"),
    (PatientHMO,                 "card_image"),
    (Prescription,               "pdf_file"),
    (LabResult,                  "file"),
    (MedicalCertificate,         "pdf_file"),
    (Medicine,                   "image"),
    (PharmacyPrescriptionUpload, "file"),
    (Message,                    "file"),
]

# Map file extensions to Cloudinary resource_type
def _resource_type(path):
    ext = os.path.splitext(path)[1].lower()
    return "raw" if ext in (".pdf", ".doc", ".docx") else "image"


class Command(BaseCommand):
    help = "Migrate local media files to Cloudinary"

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true",
                            help="Preview only, no upload.")

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        total = skipped = migrated = failed = 0

        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN - no files will be uploaded.\n"))

        for Model, field_name in FIELDS:
            qs = Model.objects.exclude(**{f"{field_name}__isnull": True}).exclude(
                **{f"{field_name}__exact": ""}
            )
            for obj in qs:
                total += 1
                current_name = getattr(obj, field_name).name or ""

                # Already on Cloudinary
                if current_name.startswith("http") or "res.cloudinary.com" in current_name:
                    self.stdout.write(f"  SKIP  {Model.__name__} #{obj.pk} - already on Cloudinary")
                    skipped += 1
                    continue

                local_path = os.path.join("media", current_name.lstrip("/"))
                if not os.path.exists(local_path):
                    self.stdout.write(
                        self.style.WARNING(f"  MISS  {Model.__name__} #{obj.pk} - not found: {local_path}")
                    )
                    skipped += 1
                    continue

                if dry_run:
                    self.stdout.write(f"  WOULD UPLOAD  {Model.__name__} #{obj.pk} -> {local_path}")
                    migrated += 1
                    continue

                try:
                    # Upload directly to Cloudinary
                    folder = os.path.dirname(current_name)
                    result = cloudinary.uploader.upload(
                        local_path,
                        folder=folder,
                        resource_type=_resource_type(local_path),
                        use_filename=True,
                        unique_filename=False,
                        overwrite=True,
                    )
                    cloudinary_url = result["secure_url"]

                    # Save the Cloudinary URL back to the DB field
                    Model.objects.filter(pk=obj.pk).update(**{field_name: cloudinary_url})

                    self.stdout.write(self.style.SUCCESS(
                        f"  OK    {Model.__name__} #{obj.pk} -> {cloudinary_url}"
                    ))
                    migrated += 1
                except Exception as e:
                    self.stdout.write(self.style.ERROR(
                        f"  FAIL  {Model.__name__} #{obj.pk} - {e}"
                    ))
                    failed += 1

        self.stdout.write("\n" + "=" * 50)
        self.stdout.write(f"Total:    {total}")
        self.stdout.write(self.style.SUCCESS(f"Migrated: {migrated}"))
        self.stdout.write(self.style.WARNING(f"Skipped:  {skipped}"))
        if failed:
            self.stdout.write(self.style.ERROR(f"Failed:   {failed}"))
        else:
            self.stdout.write(f"Failed:   {failed}")
