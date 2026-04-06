"""
Management command to verify PayMongo live mode configuration.

Usage:
    python manage.py check_paymongo_config

This command verifies:
  - PayMongo keys are configured
  - Live keys are used in production (not test keys)
  - Webhook secret is configured
  - Keys are valid and can connect to PayMongo API
"""

import sys
from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Verify PayMongo live mode configuration"

    def handle(self, *args, **options):
        self.stdout.write("\n" + "="*70)
        self.stdout.write(self.style.HTTP_INFO("  PayMongo Configuration Check"))
        self.stdout.write("="*70 + "\n")

        errors = []
        warnings = []
        success = []

        # Check 1: Keys are configured
        secret_key = getattr(settings, "PAYMONGO_SECRET_KEY", "")
        public_key = getattr(settings, "PAYMONGO_PUBLIC_KEY", "")
        webhook_secret = getattr(settings, "PAYMONGO_WEBHOOK_SECRET", "")

        if not secret_key:
            errors.append("PAYMONGO_SECRET_KEY is not configured in .env")
        else:
            success.append(f"✓ PAYMONGO_SECRET_KEY is configured ({secret_key[:10]}...)")

        if not public_key:
            errors.append("PAYMONGO_PUBLIC_KEY is not configured in .env")
        else:
            success.append(f"✓ PAYMONGO_PUBLIC_KEY is configured ({public_key[:10]}...)")

        if not webhook_secret:
            warnings.append("⚠ PAYMONGO_WEBHOOK_SECRET is not configured (webhooks will fail)")
        else:
            success.append(f"✓ PAYMONGO_WEBHOOK_SECRET is configured ({webhook_secret[:10]}...)")

        # Check 2: Live vs Test mode
        is_debug = getattr(settings, "DEBUG", True)
        is_test_secret = secret_key.startswith("sk_test_") if secret_key else False
        is_test_public = public_key.startswith("pk_test_") if public_key else False
        is_live_secret = secret_key.startswith("sk_live_") if secret_key else False
        is_live_public = public_key.startswith("pk_live_") if public_key else False

        if is_debug:
            self.stdout.write(self.style.WARNING("\n🔧 DEBUG MODE: Test keys are acceptable\n"))
            if is_test_secret and is_test_public:
                success.append("✓ Using test keys (sk_test_... / pk_test_...)")
            elif is_live_secret and is_live_public:
                warnings.append("⚠ Using LIVE keys in DEBUG mode — real money will be charged!")
            else:
                errors.append("Keys have mismatched prefixes (one test, one live)")
        else:
            self.stdout.write(self.style.ERROR("\n🚀 PRODUCTION MODE: Live keys required\n"))
            if is_test_secret or is_test_public:
                errors.append(
                    "❌ CRITICAL: Test keys detected in production! "
                    "Replace with live keys (sk_live_... / pk_live_...)"
                )
            elif is_live_secret and is_live_public:
                success.append("✓ Using LIVE keys (sk_live_... / pk_live_...) — REAL MONEY MODE")
            else:
                errors.append("Keys have invalid prefixes or are missing")

        # Check 3: Test API connectivity
        if secret_key and len(secret_key) > 20:
            self.stdout.write("\n🔌 Testing PayMongo API connectivity...\n")
            try:
                import requests
                import base64
                token = base64.b64encode(f"{secret_key}:".encode()).decode()
                resp = requests.get(
                    "https://api.paymongo.com/v1/payment_methods",
                    headers={"Authorization": f"Basic {token}"},
                    timeout=10,
                )
                if resp.status_code == 200:
                    success.append("✓ PayMongo API connection successful")
                elif resp.status_code == 401:
                    errors.append("❌ PayMongo API authentication failed (invalid secret key)")
                else:
                    warnings.append(f"⚠ PayMongo API returned status {resp.status_code}")
            except requests.Timeout:
                warnings.append("⚠ PayMongo API connection timeout (check internet)")
            except requests.RequestException as exc:
                warnings.append(f"⚠ PayMongo API connection error: {exc}")
            except Exception as exc:
                warnings.append(f"⚠ Unexpected error testing API: {exc}")

        # Print results
        self.stdout.write("\n" + "-"*70)
        self.stdout.write(self.style.SUCCESS("  PASSED CHECKS"))
        self.stdout.write("-"*70)
        for msg in success:
            self.stdout.write(self.style.SUCCESS(msg))

        if warnings:
            self.stdout.write("\n" + "-"*70)
            self.stdout.write(self.style.WARNING("  WARNINGS"))
            self.stdout.write("-"*70)
            for msg in warnings:
                self.stdout.write(self.style.WARNING(msg))

        if errors:
            self.stdout.write("\n" + "-"*70)
            self.stdout.write(self.style.ERROR("  ERRORS"))
            self.stdout.write("-"*70)
            for msg in errors:
                self.stdout.write(self.style.ERROR(msg))

        self.stdout.write("\n" + "="*70 + "\n")

        if errors:
            self.stdout.write(
                self.style.ERROR(
                    "❌ Configuration check FAILED. Fix the errors above before deploying.\n"
                )
            )
            sys.exit(1)
        elif warnings:
            self.stdout.write(
                self.style.WARNING(
                    "⚠ Configuration check passed with warnings. Review before deploying.\n"
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    "✅ Configuration check PASSED. PayMongo is ready for live mode!\n"
                )
            )
