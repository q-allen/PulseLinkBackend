from django.core.management.base import BaseCommand
from records.models import MedicalCertificate
from records.utils import generate_certificate_pdf


class Command(BaseCommand):
    help = "Backfill missing PDFs for all MedicalCertificate records"

    def handle(self, *args, **options):
        certs = MedicalCertificate.objects.select_related("doctor", "patient").all()
        total = certs.count()
        generated = 0
        skipped = 0

        for cert in certs:
            if cert.pdf_file:
                skipped += 1
                continue
            ok = generate_certificate_pdf(cert)
            if ok:
                generated += 1
                self.stdout.write(self.style.SUCCESS(f"  OK cert #{cert.pk} - {cert.purpose}"))
            else:
                self.stdout.write(self.style.ERROR(f"  FAIL cert #{cert.pk} - PDF generation failed"))

        self.stdout.write(self.style.SUCCESS(
            f"\nDone. {generated} generated, {skipped} already had PDF, {total} total."
        ))
