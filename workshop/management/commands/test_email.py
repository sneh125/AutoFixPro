import os
import requests
from django.core.management.base import BaseCommand
from django.conf import settings
from workshop.views import send_otp_email, send_robust_autofix_email


class Command(BaseCommand):
    help = "Safely tests Brevo API and registration email/OTP dispatch without exposing secrets."

    def add_arguments(self, parser):
        parser.add_argument("recipient", nargs="?", default="snehprajapati36@gmail.com", help="Recipient email address")

    def handle(self, *args, **options):
        recipient = (options["recipient"] or "snehprajapati36@gmail.com").strip().lower()

        brevo_key = (
            getattr(settings, "BREVO_API_KEY", "")
            or os.getenv("BREVO_API_KEY", "")
        ).strip("'\" \t\r\n")

        sender_email = (
            os.getenv("BREVO_SENDER_EMAIL", "")
            or getattr(settings, "BREVO_SENDER_EMAIL", "")
            or "snehprajapati36@gmail.com"
        ).strip("'\" \t\r\n")

        sender_name = (
            os.getenv("BREVO_SENDER_NAME", "")
            or getattr(settings, "BREVO_SENDER_NAME", "")
            or "AutoFixPro"
        ).strip("'\" \t\r\n")

        self.stdout.write(self.style.NOTICE("=== AutoFixPro Email Diagnostic Test ==="))
        self.stdout.write(f"Target Recipient: {recipient}")
        self.stdout.write(f"BREVO_API_KEY: {'SET' if brevo_key else 'MISSING'}")
        self.stdout.write(f"BREVO_SENDER_EMAIL: {sender_email if sender_email else 'MISSING'}")
        self.stdout.write(f"BREVO_SENDER_NAME: {sender_name}")

        # Step 1: Direct Brevo API Endpoint Probe
        self.stdout.write("\n[Step 1] Probing Brevo HTTPS REST API (https://api.brevo.com/v3/smtp/email)...")
        if not brevo_key:
            self.stdout.write(self.style.ERROR("FAILED"))
            self.stdout.write("HTTP STATUS: N/A")
            self.stdout.write("BREVO RESPONSE: BREVO_API_KEY is not configured in .env or settings.")
        else:
            try:
                headers = {
                    "accept": "application/json",
                    "api-key": brevo_key,
                    "content-type": "application/json",
                }
                payload = {
                    "sender": {"name": sender_name, "email": sender_email},
                    "to": [{"email": recipient}],
                    "subject": "AutoFixPro Brevo API Diagnostic Test",
                    "textContent": "This is a direct diagnostic test from AutoFixPro via Brevo HTTPS REST API.",
                    "htmlContent": "<p>AutoFixPro Brevo HTTPS REST API diagnostic test successful.</p>",
                }
                resp = requests.post(
                    "https://api.brevo.com/v3/smtp/email",
                    headers=headers,
                    json=payload,
                    timeout=15,
                )
                if 200 <= resp.status_code < 300:
                    self.stdout.write(self.style.SUCCESS("SUCCESS"))
                    self.stdout.write(f"HTTP STATUS: {resp.status_code}")
                    resp_json = resp.json() if resp.text else {}
                    self.stdout.write(f"BREVO RESPONSE: messageId={resp_json.get('messageId', 'OK')}")
                else:
                    self.stdout.write(self.style.ERROR("FAILED"))
                    self.stdout.write(f"HTTP STATUS: {resp.status_code}")
                    self.stdout.write(f"BREVO RESPONSE: {resp.text[:400]}")
            except requests.exceptions.Timeout:
                self.stdout.write(self.style.ERROR("FAILED"))
                self.stdout.write("HTTP STATUS: Timeout")
                self.stdout.write("BREVO RESPONSE: Connection timed out after 15s connecting to api.brevo.com.")
            except Exception as e:
                self.stdout.write(self.style.ERROR("FAILED"))
                self.stdout.write("HTTP STATUS: Network/Exception")
                self.stdout.write(f"BREVO RESPONSE: {type(e).__name__}: {str(e)}")

        # Step 2: Testing Registration OTP Helper Function
        self.stdout.write("\n[Step 2] Testing existing send_otp_email(recipient, 'register') flow...")
        raw_otp, email_sent = send_otp_email(recipient, "register")
        if email_sent:
            self.stdout.write(self.style.SUCCESS("[SUCCESS] Registration OTP email dispatched successfully!"))
            self.stdout.write(f"Verification code delivered to: {recipient}")
        else:
            self.stdout.write(self.style.ERROR("[FAILED] Registration OTP email could not be dispatched."))
            self.stdout.write("Check the backend log above for exact HTTP status and provider response.")
