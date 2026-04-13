import requests
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand

from pharmacy.models import PharmacyPrescriptionUpload


class Command(BaseCommand):
    help = "Re-upload existing pharmacy prescription files to Cloudinary as raw resource type."

    def handle(self, *args, **options):
        uploads = PharmacyPrescriptionUpload.objects.exclude(file="")
        self.stdout.write(f"Found {uploads.count()} upload(s) to process.")

        for upload in uploads:
            old_url = upload.file.url
            if "/raw/upload/" in old_url:
                self.stdout.write(f"  #{upload.pk} already raw — skipping.")
                continue

            # Fetch the file from Cloudinary using the image URL (it exists there)
            fetch_url = old_url.replace("/image/upload/", "/raw/upload/")
            # Try raw first, fall back to image URL
            r = None
            for url in [fetch_url, old_url]:
                try:
                    r = requests.get(url, timeout=15)
                    if r.status_code == 200:
                        break
                except requests.RequestException:
                    continue

            if not r or r.status_code != 200:
                self.stdout.write(self.style.ERROR(f"  #{upload.pk} — could not fetch file, skipping."))
                continue

            filename = upload.file.name.split("/")[-1]
            # Save via RawMediaCloudinaryStorage (set on the field)
            upload.file.save(filename, ContentFile(r.content), save=True)
            self.stdout.write(self.style.SUCCESS(f"  #{upload.pk} — re-uploaded as raw: {upload.file.url}"))

        self.stdout.write(self.style.SUCCESS("Done."))
