import os
import secrets
from django.core.management.base import BaseCommand
from django.core.management import call_command
from django.contrib.auth.hashers import make_password
from workshop.models import User, Inventory


class Command(BaseCommand):
    help = "Initializes database, admin user, initial inventory, and collects static files for PythonAnywhere & production."

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE("1. Running database migrations..."))
        call_command("migrate", interactive=False)
        self.stdout.write(self.style.SUCCESS("[OK] Migrations applied successfully."))

        self.stdout.write(self.style.NOTICE("2. Checking Admin user..."))
        admin_email = os.getenv("ADMIN_EMAIL", "admin@autofixpro.com").strip()
        admin_password = os.getenv("ADMIN_PASSWORD", "").strip()
        generated_password = False
        if not admin_password:
            admin_password = secrets.token_urlsafe(12)
            generated_password = True

        admin_user = User.objects.filter(email=admin_email).first()
        if not admin_user:
            User.objects.create(
                fullname="Admin Panel",
                email=admin_email,
                phone="9876543210",
                password=make_password(admin_password),
                is_admin=True
            )
            self.stdout.write(self.style.SUCCESS(f"[OK] Admin created: {admin_email}"))
        else:
            if not admin_user.is_admin:
                admin_user.is_admin = True
                admin_user.save()
            self.stdout.write(self.style.SUCCESS(f"[OK] Admin account exists ({admin_email})."))

        self.stdout.write(self.style.NOTICE("3. Checking Inventory parts..."))
        if Inventory.objects.count() == 0:
            sample_items = [
                ("Premium Synthetic Engine Oil (5W-30)", "Fluids", 45, 1200.0),
                ("Front Ceramic Brake Pads", "Brakes", 18, 2500.0),
                ("High-Flow Oil Filter", "Filters", 60, 350.0),
                ("Iridium Spark Plug Set (x4)", "Ignition", 8, 1800.0),
                ("Engine Coolant Anti-Freeze (Red, 5L)", "Fluids", 25, 850.0),
                ("Activated Carbon Cabin Air Filter", "Filters", 6, 600.0),
                ("Heavy Duty Maintenance-Free Car Battery 12V", "Electrical", 12, 5500.0),
                ("Ventilated Front Brake Disc Rotors (Pair)", "Brakes", 14, 4200.0),
                ("All-Weather Silicone Wiper Blades (24+18 inch)", "Accessories", 30, 950.0),
                ("Heavy Duty Timing Belt", "Engine", 10, 3200.0),
            ]
            for name, cat, qty, pr in sample_items:
                Inventory.objects.create(name=name, category=cat, quantity=qty, price=pr)
            self.stdout.write(self.style.SUCCESS(f"[OK] Seeded {len(sample_items)} inventory workshop parts."))
        else:
            self.stdout.write(self.style.SUCCESS(f"[OK] Inventory items already present ({Inventory.objects.count()} items)."))

        self.stdout.write(self.style.NOTICE("4. Collecting static files with WhiteNoise..."))
        try:
            call_command("collectstatic", interactive=False)
            self.stdout.write(self.style.SUCCESS("[OK] Static files collected successfully into staticfiles/"))
        except Exception as e:
            self.stdout.write(self.style.WARNING(f"! collectstatic notice: {e}"))

        self.stdout.write(self.style.SUCCESS("\n========================================================"))
        self.stdout.write(self.style.SUCCESS("  AutoFixPro Server Bootstrap Completed!"))
        self.stdout.write(self.style.SUCCESS("  - Login URL: /login/"))
        self.stdout.write(self.style.SUCCESS(f"  - Admin Email: {admin_email}"))
        if not admin_user:
            if generated_password:
                self.stdout.write(self.style.WARNING(f"  - Generated Admin Password: {admin_password}"))
                self.stdout.write(self.style.NOTICE("    (Store this securely or configure ADMIN_PASSWORD in your .env file)"))
            else:
                self.stdout.write(self.style.SUCCESS("  - Admin Password: [Configured via ADMIN_PASSWORD environment variable]"))
        self.stdout.write(self.style.SUCCESS("========================================================\n"))
