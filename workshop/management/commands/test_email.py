from django.core.management.base import BaseCommand
from workshop.views import send_robust_autofix_email
from django.conf import settings


class Command(BaseCommand):
    help = "Tests email dispatch via Brevo HTTPS API, Resend, or SMTP."

    def add_arguments(self, parser):
        parser.add_argument("recipient", nargs="?", default="snehprajapati36@gmail.com", help="Recipient email address")

    def handle(self, *args, **options):
        recipient = options["recipient"]
        self.stdout.write(self.style.NOTICE(f"Testing email delivery to: {recipient}"))
        self.stdout.write(f"BREVO_API_KEY set: {'YES' if getattr(settings, 'BREVO_API_KEY', '') else 'NO'}")
        self.stdout.write(f"RESEND_API_KEY set: {'YES' if getattr(settings, 'RESEND_API_KEY', '') else 'NO'}")
        self.stdout.write(f"EMAIL_HOST: {getattr(settings, 'EMAIL_HOST', '')}")
        self.stdout.write(f"EMAIL_HOST_USER: {getattr(settings, 'EMAIL_HOST_USER', '')}")

        subject = "AutoFixPro Test Email"
        message = "This is a test email from AutoFixPro to verify your production email dispatch configuration."
        html_message = """
        <div style="font-family: Arial, sans-serif; padding: 20px; border: 1px solid #e2e8f0; border-radius: 8px;">
            <h2 style="color: #ff4d30;">AutoFixPro Email Test</h2>
            <p>Congratulations! Your email system is working properly.</p>
            <p>You can now receive OTPs and booking confirmations in your inbox.</p>
        </div>
        """

        success, status = send_robust_autofix_email(
            subject=subject,
            plain_message=message,
            recipient_list=[recipient],
            html_message=html_message
        )

        if success:
            self.stdout.write(self.style.SUCCESS(f"\n[SUCCESS] Email sent successfully! ({status})"))
            self.stdout.write(self.style.SUCCESS(f"Please check inbox & spam folder of {recipient}."))
        else:
            self.stdout.write(self.style.ERROR(f"\n[FAILED] Email delivery failed: {status}"))
            self.stdout.write(self.style.WARNING("Reminder: On PythonAnywhere Free Tier, direct SMTP ports (587, 465) are blocked."))
            self.stdout.write(self.style.WARNING("Add your BREVO_API_KEY to .env or environment variables to send via HTTPS."))
