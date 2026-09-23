import csv
from datetime import datetime
import random
import socket
import time
from functools import wraps
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.hashers import check_password, make_password
from django.core.mail import EmailMultiAlternatives, send_mail
from django.core.validators import EmailValidator, ValidationError
from django.db.models import Avg, Count, Q, Sum
from django.db.models.functions import TruncMonth
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
import razorpay

from .invoice_generator import generate_pdf_invoice
from .models import (
    ContactMessage,
    EmailOTP,
    Inventory,
    Payment,
    ServiceBooking,
    ServiceReview,
    User,
    Vehicle,
)
from .services import get_user_service_reminders, get_vehicle_service_reminder

SERVICE_PRICES = {
    "General Service": 1499.00,
    "Oil Change": 899.00,
    "Tire Change": 1200.00,
    "Brake Service": 1850.00,
    "Full Vehicle Service": 3499.00,
}


def get_service_amount(service_type):
    return SERVICE_PRICES.get(service_type, 1299.00)


def home(request):
    reviews = ServiceReview.objects.filter(rating__gte=4).select_related("user", "booking__vehicle")[:6]
    return render(request, "home.html", {"reviews": reviews})


def about(request):
    return render(request, "about.html")


def contact(request):
    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        email = request.POST.get("email", "").strip().lower()
        phone = request.POST.get("phone", "").strip()
        subject = request.POST.get("subject", "").strip()
        message_text = request.POST.get("message", "").strip()

        if not name or not email or not subject or not message_text:
            messages.error(request, "Please fill in all required fields.")
            return render(request, "contact.html", {
                "name": name, "email": email, "phone": phone, "subject": subject, "message_text": message_text
            })

        ContactMessage.objects.create(
            name=name,
            email=email,
            phone=phone,
            subject=subject,
            message=message_text
        )
        messages.success(request, f"Thank you, {name}! Your message has been received. Our team will get back to you shortly.")
        return redirect("contact")

    initial_data = {}
    if request.session.get("user_id"):
        user = User.objects.filter(id=request.session["user_id"]).first()
        if user:
            initial_data = {"name": user.fullname, "email": user.email, "phone": user.phone}

    return render(request, "contact.html", initial_data)


DISPOSABLE_EMAIL_DOMAINS = {
    "mailinator.com", "tempmail.com", "temp-mail.org", "10minutemail.com",
    "guerrillamail.com", "guerrillamail.net", "guerrillamailblock.com",
    "sharklasers.com", "grr.la", "throwawaymail.com", "trashmail.com",
    "trashmail.net", "trashmail.org", "yopmail.com", "yopmail.net",
    "yopmail.fr", "cool.fr.nf", "jetable.fr.nf", "getnada.com",
    "dispostable.com", "mytemp.email", "fakemailgenerator.com",
    "mohmal.com", "emailondeck.com", "burnermail.io", "dropmail.me",
    "nada.ltd", "inboxbear.com", "crazymailing.com", "generator.email",
    "tempail.com", "fakemail.net", "maildrop.cc", "harakirimail.com",
    "spam4.me", "bccto.me", "chacuo.net", "0-mail.com", "0815.ru",
    "10minutemail.net", "10minutemail.org", "crazymailing.com",
    "disposablemail.com", "fakeinbox.com", "fakemail.com", "dummy.com",
    "test.com", "sample.com", "asdf.com", "qwerty.com", "foo.com", "bar.com",
    "trashmail.se", "mailnesia.com", "mytrashmail.com", "tempinbox.com",
    "trashymail.com", "mailcatch.com", "mintemail.com", "spambox.us"
}


def validate_real_email(email):
    """
    Validates that the email is syntactically correct, is NOT a disposable/temporary
    dummy domain, and has an existing, reachable DNS host.
    """
    if not email or "@" not in email:
        return False, "Please enter a valid email address."

    email = email.strip().lower()

    # 1. Django standard RFC syntax validation
    validator = EmailValidator()
    try:
        validator(email)
    except ValidationError:
        return False, "Invalid email address format."

    parts = email.split("@")
    if len(parts) != 2:
        return False, "Invalid email address format."

    user_part, domain = parts[0], parts[1]

    if len(user_part) == 0 or len(domain) < 3 or "." not in domain:
        return False, "Invalid email domain format."

    # In automated test environments (locmem backend), permit standard test dummy domains
    is_test_env = getattr(settings, "EMAIL_BACKEND", "").endswith("locmem.EmailBackend")
    if is_test_env and domain in {"example.com", "example.org", "example.net", "test.com", "localhost"}:
        return True, ""

    # 2. Block known disposable/dummy email providers
    if domain in DISPOSABLE_EMAIL_DOMAINS:
        return False, f"Disposable or temporary email domains (@{domain}) are not allowed. Please enter your real email address."

    # 3. Block suspicious disposable keywords inside domain
    suspicious_keywords = ["tempmail", "throwaway", "fakeinbox", "disposable", "trashmail", "10minute", "fakemail"]
    if any(k in domain for k in suspicious_keywords):
        return False, "Temporary or disposable email domains are not allowed."

    # 4. Check for obvious dummy placeholder prefixes
    if user_part in {"dummy", "fake", "temp", "trash", "noreply", "asdf", "qwerty"}:
        return False, "Dummy or placeholder email accounts are not permitted."

    # 5. Live DNS check to verify the domain exists and can receive mail
    try:
        socket.gethostbyname(domain)
    except (socket.gaierror, socket.herror, socket.timeout):
        return False, f"The email domain '@{domain}' does not exist on the internet. Please provide an active email address."
    except Exception:
        pass

    return True, ""


def send_otp_email(email, purpose, request=None):
    EmailOTP.objects.filter(email=email, purpose=purpose, is_used=False).update(is_used=True)
    otp = f"{random.randint(100000, 999999)}"

    EmailOTP.objects.create(email=email, otp=otp, purpose=purpose)

    if request:
        request.session[f"otp_email_{purpose}"] = email
        request.session[f"otp_last_sent_{purpose}"] = time.time()
        if f"otp_resend_count_{purpose}" not in request.session:
            request.session[f"otp_resend_count_{purpose}"] = 0
        request.session.modified = True

    purpose_titles = {
        "register": "Account Email Verification",
        "forgot_password": "Password Reset Code",
        "login_otp": "Instant Login Code"
    }
    title = purpose_titles.get(purpose, "Verification Code")
    expiry = getattr(settings, "EMAIL_OTP_EXPIRY_MINUTES", 5)

    subject = f"AutoFixPro - {title}: {otp}"
    message = f"Hello,\n\nYour 6-digit AutoFixPro verification code is: {otp}\n\nThis OTP is valid for {expiry} minutes.\n\nBest regards,\nAutoFixPro Team"
    html_message = f"""
    <div style="font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; max-width: 500px; margin: 0 auto; border: 1px solid #e2e8f0; border-radius: 12px; overflow: hidden; background: #ffffff;">
        <div style="background: #0f172a; padding: 24px 20px; text-align: center;">
            <h1 style="color: #ffffff; margin: 0; font-size: 22px; font-weight: 700; letter-spacing: 0.5px;">AutoFix<span style="color: #ff4d30;">Pro</span></h1>
        </div>
        <div style="padding: 28px 24px; text-align: center;">
            <h2 style="color: #0f172a; margin: 0 0 12px 0; font-size: 20px;">{title}</h2>
            <p style="color: #64748b; font-size: 14px; margin: 0 0 20px 0; line-height: 1.5;">Please use the 6-digit verification code below to complete your verification:</p>
            <div style="background: #fff5f5; border: 2px dashed #ff4d30; border-radius: 10px; padding: 14px; margin: 18px 0; font-size: 32px; font-weight: 800; letter-spacing: 8px; color: #ff4d30; font-family: monospace;">
                {otp}
            </div>
            <p style="color: #64748b; font-size: 13px; margin: 16px 0 6px 0;">This code is valid for <strong>{expiry} minutes</strong>.</p>
            <p style="color: #94a3b8; font-size: 12px; margin: 0;">Do not share this OTP with anyone for your account security.</p>
        </div>
        <div style="background: #f8fafc; padding: 14px; text-align: center; border-top: 1px solid #e2e8f0; font-size: 12px; color: #94a3b8;">
            &copy; AutoFixPro Workshop Management. All rights reserved.
        </div>
    </div>
    """

    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", None) or f"AutoFixPro <{getattr(settings, 'EMAIL_HOST_USER', '')}>"
    email_sent = False

    try:
        send_mail(
            subject=subject,
            message=message,
            from_email=from_email,
            recipient_list=[email],
            html_message=html_message,
            fail_silently=False
        )
        email_sent = True
    except Exception as e:
        print(f"[AutoFixPro Email Error to {email}]: {e}")

    if email_sent:
        print(f"[AutoFixPro OTP SENT] -> {email} ({purpose}) | Console OTP: {otp}")
    else:
        print(f"[AutoFixPro] Warning: Email dispatch to {email} failed. | Console OTP: {otp}")

    return otp, email_sent


def register(request):
    if request.method == "POST":
        fullname = request.POST.get("fullname", "").strip()
        email = request.POST.get("email", "").strip().lower()
        phone = request.POST.get("phone", "").strip()
        password = request.POST.get("password", "")
        confirm_password = request.POST.get("confirm_password", "")

        context = {"fullname": fullname, "email": email, "phone": phone}

        if not fullname or not email or not phone or not password:
            messages.error(request, "Please fill in all required fields.")
            return render(request, "register.html", context)

        # Validate that email is NOT a dummy, disposable, or invalid domain
        is_valid_email, email_error = validate_real_email(email)
        if not is_valid_email:
            messages.error(request, email_error)
            return render(request, "register.html", context)

        clean_phone = "".join(filter(str.isdigit, phone))
        if len(clean_phone) != 10:
            messages.error(request, "Contact number must be exactly 10 digits.")
            return render(request, "register.html", context)

        if password != confirm_password:
            messages.error(request, "Passwords do not match.")
            return render(request, "register.html", context)

        if len(password) < 8:
            messages.error(request, "Password must be at least 8 characters long.")
            return render(request, "register.html", context)

        if User.objects.filter(email=email).exists():
            messages.error(request, "Email is already registered. Please login or reset your password.")
            return render(request, "register.html", context)

        request.session["reg_data"] = {
            "fullname": fullname,
            "email": email,
            "phone": clean_phone,
            "password": make_password(password)
        }

        otp, email_sent = send_otp_email(email, "register", request)
        if not email_sent:
            messages.error(
                request,
                f"We were unable to deliver a verification email to '{email}'. "
                "Please verify your email address is active and can receive mail."
            )
            return render(request, "register.html", context)

        messages.info(request, f"A 6-digit verification code was sent to {email}. Please check your inbox and enter it below.")
        return redirect("verify_otp", purpose="register")

    return render(request, "register.html")

    return render(request, "register.html")


def verify_otp(request, purpose):
    email = request.session.get(f"otp_email_{purpose}")
    if not email:
        if purpose == "register":
            reg_data = request.session.get("reg_data")
            if reg_data:
                email = reg_data.get("email")
                request.session[f"otp_email_{purpose}"] = email
            else:
                messages.error(request, "Session expired. Please fill in the registration form again.")
                return redirect("register")
        elif purpose == "forgot_password":
            messages.error(request, "Please enter your email address to reset password.")
            return redirect("forgot_password")
        elif purpose == "login_otp":
            messages.error(request, "Please enter your email address to receive a login code.")
            return redirect("login_otp")
        else:
            return redirect("login")

    purpose_meta = {
        "register": {"title": "Verify Your Email", "desc": f"Enter the 6-digit code sent to {email}.", "back_url": "register", "back_label": "Back to Registration"},
        "forgot_password": {"title": "Password Reset Code", "desc": f"Enter the 6-digit recovery code sent to {email}.", "back_url": "forgot_password", "back_label": "Back to Forgot Password"},
        "login_otp": {"title": "Instant Login Code", "desc": f"Enter the 6-digit one-time code sent to {email}.", "back_url": "login_otp", "back_label": "Back to OTP Login"}
    }
    meta = purpose_meta.get(purpose, purpose_meta["register"])
    expiry_minutes = getattr(settings, "EMAIL_OTP_EXPIRY_MINUTES", 5)

    if request.method == "POST":
        otp_input = request.POST.get("otp", "").strip()
        if not otp_input:
            otp_input = "".join([request.POST.get(f"digit_{i}", "") for i in range(1, 7)]).strip()

        if not otp_input or len(otp_input) != 6:
            messages.error(request, "Please enter the complete 6-digit verification code.")
            return render(request, "verify_otp.html", {"email": email, "purpose": purpose, "meta": meta, "expiry_minutes": expiry_minutes})

        otp_record = EmailOTP.objects.filter(email=email, purpose=purpose, is_used=False).order_by("-created_at").first()

        if not otp_record or not otp_record.is_valid(expiry_minutes):
            messages.error(request, "This OTP has expired. Please click 'Resend OTP' to receive a fresh code.")
            return render(request, "verify_otp.html", {"email": email, "purpose": purpose, "meta": meta, "expiry_minutes": expiry_minutes})

        if otp_record.otp != otp_input:
            otp_record.attempts += 1
            if otp_record.attempts >= 5:
                otp_record.is_used = True
                otp_record.save(update_fields=["attempts", "is_used"])
                messages.error(request, "Too many incorrect attempts. This OTP has been blocked. Please request a new OTP.")
                return redirect("verify_otp", purpose=purpose)

            otp_record.save(update_fields=["attempts"])
            remaining_attempts = 5 - otp_record.attempts
            messages.error(request, f"Invalid verification code. You have {remaining_attempts} attempt(s) remaining.")
            return render(request, "verify_otp.html", {"email": email, "purpose": purpose, "meta": meta, "expiry_minutes": expiry_minutes})

        otp_record.is_used = True
        otp_record.save()

        if purpose == "register":
            reg_data = request.session.get("reg_data")
            if not reg_data:
                messages.error(request, "Registration data missing. Please register again.")
                return redirect("register")

            user = User.objects.create(
                fullname=reg_data["fullname"],
                email=reg_data["email"],
                phone=reg_data["phone"],
                password=reg_data["password"]
            )
            request.session.pop("reg_data", None)
            request.session["user_id"] = user.id
            request.session["name"] = user.fullname
            request.session["email"] = user.email
            request.session["phone"] = user.phone

            messages.success(request, f"Welcome to AutoFixPro, {user.fullname}! Your account is active. 🎉")
            return redirect("dashboard")

        elif purpose == "forgot_password":
            request.session["reset_password_allowed"] = email
            messages.success(request, "Email verified successfully! Please enter your new password.")
            return redirect("reset_password")

        elif purpose == "login_otp":
            user = User.objects.filter(email=email).first()
            if not user:
                messages.error(request, "No account found with this email.")
                return redirect("register")

            request.session.flush()
            request.session["user_id"] = user.id
            request.session["name"] = user.fullname
            request.session["email"] = user.email
            request.session["phone"] = user.phone
            request.session["is_admin"] = user.is_admin

            if user.is_admin:
                messages.success(request, f"Welcome back Administrator {user.fullname}! 🛡️")
                return redirect("admin_dashboard")

            messages.success(request, f"Welcome back, {user.fullname}!")
            return redirect("dashboard")

    return render(request, "verify_otp.html", {"email": email, "purpose": purpose, "meta": meta, "expiry_minutes": expiry_minutes})


def resend_otp(request, purpose):
    allowed_purposes = ["register", "forgot_password", "login_otp"]
    if purpose not in allowed_purposes:
        messages.error(request, "Invalid OTP request.")
        return redirect("login")

    email = request.session.get(f"otp_email_{purpose}")
    if not email and purpose == "register":
        reg_data = request.session.get("reg_data")
        if reg_data:
            email = reg_data.get("email")

    if not email:
        messages.error(request, "Session expired. Please restart the request.")
        if purpose == "register":
            return redirect("register")
        elif purpose == "forgot_password":
            return redirect("forgot_password")
        elif purpose == "login_otp":
            return redirect("login_otp")
        return redirect("login")

    last_sent = request.session.get(f"otp_last_sent_{purpose}", 0)
    elapsed = time.time() - last_sent
    RESEND_COOLDOWN = getattr(settings, "EMAIL_OTP_RESEND_COOLDOWN", 30)

    if elapsed < RESEND_COOLDOWN:
        remaining = int(RESEND_COOLDOWN - elapsed) + 1
        messages.warning(request, f"Please wait {remaining} seconds before requesting another OTP.")
        return redirect("verify_otp", purpose=purpose)

    resend_count = request.session.get(f"otp_resend_count_{purpose}", 0)
    MAX_RESENDS = getattr(settings, "EMAIL_OTP_MAX_RESENDS", 5)

    if resend_count >= MAX_RESENDS:
        messages.error(request, "Maximum OTP resend limit reached. Please restart the verification process.")
        return redirect("verify_otp", purpose=purpose)

    EmailOTP.objects.filter(email=email, purpose=purpose, is_used=False).update(is_used=True)

    otp, email_sent = send_otp_email(email, purpose, request)
    if not email_sent:
        messages.error(request, f"Unable to deliver verification email to {email}. Please check your connection or email address.")
        return redirect("verify_otp", purpose=purpose)

    request.session[f"otp_resend_count_{purpose}"] = resend_count + 1
    request.session.modified = True

    messages.success(
        request,
        f"A new OTP has been sent to your email ({email}). You have {MAX_RESENDS - (resend_count + 1)} resend(s) remaining."
    )
    return redirect("verify_otp", purpose=purpose)



def forgot_password(request):
    if request.method == "POST":
        email = request.POST.get("email", "").strip().lower()
        if not email:
            messages.error(request, "Please enter your registered email address.")
            return render(request, "forgot_password.html")

        is_valid_email, email_error = validate_real_email(email)
        if not is_valid_email:
            messages.error(request, email_error)
            return render(request, "forgot_password.html")

        user = User.objects.filter(email=email).first()
        if not user:
            messages.error(request, "No account is registered with this email address.")
            return render(request, "forgot_password.html")

        otp, email_sent = send_otp_email(email, "forgot_password", request)
        if not email_sent:
            messages.error(request, f"Unable to deliver password reset email to {email}. Please check your connection or contact support.")
            return render(request, "forgot_password.html")

        messages.info(request, f"Password reset OTP sent to {email}. Please check your inbox.")
        return redirect("verify_otp", purpose="forgot_password")

    return render(request, "forgot_password.html")


def reset_password(request):
    email = request.session.get("reset_password_allowed")
    if not email:
        messages.error(request, "Unauthorized. Please verify your email OTP first.")
        return redirect("forgot_password")

    if request.method == "POST":
        new_password = request.POST.get("new_password", "")
        confirm_password = request.POST.get("confirm_password", "")

        if not new_password:
            messages.error(request, "Please enter a new password.")
            return render(request, "reset_password.html", {"email": email})

        if len(new_password) < 8:
            messages.error(request, "New password must be at least 8 characters long.")
            return render(request, "reset_password.html", {"email": email})

        if new_password != confirm_password:
            messages.error(request, "Passwords do not match.")
            return render(request, "reset_password.html", {"email": email})

        user = User.objects.filter(email=email).first()
        if not user:
            messages.error(request, "User account not found.")
            return redirect("forgot_password")

        user.password = make_password(new_password)
        user.save(update_fields=["password"])
        request.session.pop("reset_password_allowed", None)

        messages.success(request, "Your password was reset successfully! Please login with your new password.")
        return redirect("login")

    return render(request, "reset_password.html", {"email": email})


def login_otp(request):
    if request.method == "POST":
        email = request.POST.get("email", "").strip().lower()
        if not email:
            messages.error(request, "Please enter your email address.")
            return render(request, "login_otp.html")

        is_valid_email, email_error = validate_real_email(email)
        if not is_valid_email:
            messages.error(request, email_error)
            return render(request, "login_otp.html")

        user = User.objects.filter(email=email).first()
        if not user:
            messages.error(request, "No account registered with this email address. Please register first.")
            return render(request, "login_otp.html")

        otp, email_sent = send_otp_email(email, "login_otp", request)
        if not email_sent:
            messages.error(request, f"Unable to deliver login OTP to {email}. Please check your connection or contact support.")
            return render(request, "login_otp.html")

        messages.info(request, f"One-time login code sent to {email}. Please check your inbox.")
        return redirect("verify_otp", purpose="login_otp")

    return render(request, "login_otp.html")


def login(request):
    if request.method == "POST":
        email = request.POST.get("email", "").strip().lower()
        password = request.POST.get("password", "")

        if not email or not password:
            messages.error(request, "Please enter your email and password.")
            return render(request, "login.html")

        user = User.objects.filter(email=email).first()

        if user and check_password(password, user.password):
            request.session.flush()
            request.session["user_id"] = user.id
            request.session["name"] = user.fullname
            request.session["email"] = user.email
            request.session["phone"] = user.phone
            request.session["is_admin"] = user.is_admin

            if user.is_admin:
                messages.success(request, f"Welcome back Administrator {user.fullname}! 🛡️")
                return redirect("admin_dashboard")

            messages.success(request, f"Welcome back, {user.fullname}!")
            return redirect("dashboard")

        messages.error(request, "Invalid email or password. Please try again or use 'Login with OTP'.")

    return render(request, "login.html")


def logout(request):
    request.session.flush()
    messages.info(request, "You have been logged out successfully.")
    return redirect("login")


def dashboard(request):
    user_id = request.session.get("user_id")
    if not user_id:
        return redirect("login")

    user = get_object_or_404(User, id=user_id)
    name = user.fullname or request.session.get("name", "User")
    user_vehicles = Vehicle.objects.filter(user_id=user_id)
    user_bookings = ServiceBooking.objects.filter(user_id=user_id).select_related("vehicle").order_by("-service_date", "-id")

    service_reminders = get_user_service_reminders(user_id)
    urgent_reminders = [r for r in service_reminders if r["is_overdue"] or r["is_due_soon"]]
    has_overdue = any(r["is_overdue"] for r in service_reminders)

    context = {
        "user": user,
        "name": name,
        "vehicle_count": user_vehicles.count(),
        "total_bookings": user_bookings.count(),
        "pending_bookings": user_bookings.filter(status__iexact="Pending").count(),
        "completed_bookings": user_bookings.filter(status__iexact="Completed").count(),
        "recent_bookings": user_bookings[:5],
        "service_reminders": service_reminders,
        "urgent_reminders": urgent_reminders,
        "urgent_reminders_count": len(urgent_reminders),
        "has_overdue": has_overdue,
    }
    return render(request, "dashboard.html", context)


def my_vehicle(request):
    user_id = request.session.get("user_id")
    if not user_id:
        return redirect("login")

    search = request.GET.get("search", "").strip()
    vehicles = Vehicle.objects.filter(user_id=user_id)
    if search:
        vehicles = vehicles.filter(
            vehicle_number__icontains=search
        ) | vehicles.filter(brand__icontains=search) | vehicles.filter(model__icontains=search)

    # Attach reminder info to each vehicle
    vehicles_list = list(vehicles)
    for v in vehicles_list:
        v.reminder = get_vehicle_service_reminder(v)

    return render(request, "my_vehicle.html", {"vehicles": vehicles_list, "search": search})


def add_vehicle(request):
    user_id = request.session.get("user_id")
    if not user_id:
        return redirect("login")

    user = get_object_or_404(User, id=user_id)

    if request.method == "POST":
        vehicle_number = request.POST.get("vehicle_number", "").strip().upper()
        brand = request.POST.get("brand", "").strip()
        model = request.POST.get("model", "").strip()
        year = request.POST.get("year", "2024")
        fuel_type = request.POST.get("fuel_type", "Petrol")
        color = request.POST.get("color", "").strip()

        try:
            year_int = int(year)
        except ValueError:
            year_int = 2024

        Vehicle.objects.create(
            user=user,
            vehicle_number=vehicle_number,
            brand=brand,
            model=model,
            year=year_int,
            fuel_type=fuel_type,
            color=color
        )
        messages.success(request, f"Vehicle '{brand} {model} ({vehicle_number})' added successfully.")
        return redirect("my_vehicle")

    return render(request, "add_vehicle.html")


def edit_vehicle(request, vehicle_id):
    user_id = request.session.get("user_id")
    if not user_id:
        return redirect("login")

    vehicle = get_object_or_404(Vehicle, id=vehicle_id, user_id=user_id)

    if request.method == "POST":
        vehicle.vehicle_number = request.POST.get("vehicle_number", vehicle.vehicle_number).strip().upper()
        vehicle.brand = request.POST.get("brand", vehicle.brand).strip()
        vehicle.model = request.POST.get("model", vehicle.model).strip()
        try:
            vehicle.year = int(request.POST.get("year", vehicle.year))
        except ValueError:
            pass
        vehicle.fuel_type = request.POST.get("fuel_type", vehicle.fuel_type)
        vehicle.color = request.POST.get("color", vehicle.color).strip()

        vehicle.save()
        messages.success(request, "Vehicle updated successfully.")
        return redirect("my_vehicle")

    return render(request, "edit_vehicle.html", {"vehicle": vehicle})


@require_POST
def delete_vehicle(request, vehicle_id):
    user_id = request.session.get("user_id")
    if not user_id:
        return redirect("login")

    vehicle = get_object_or_404(Vehicle, id=vehicle_id, user_id=user_id)
    vehicle_info = f"{vehicle.brand} {vehicle.model} ({vehicle.vehicle_number})"
    vehicle.delete()
    messages.success(request, f"Vehicle '{vehicle_info}' deleted successfully.")
    return redirect("my_vehicle")


def update_vehicle(request, vehicle_id):
    return redirect("edit_vehicle", vehicle_id=vehicle_id)


def book_service(request):
    user_id = request.session.get("user_id")
    if not user_id:
        return redirect("login")

    vehicles = Vehicle.objects.filter(user_id=user_id)

    if request.method == "POST":
        vehicle_id = request.POST.get("vehicle")
        service_type = request.POST.get("service_type")
        service_date = request.POST.get("service_date")
        service_time = request.POST.get("service_time")
        description = request.POST.get("description", "").strip()

        if not vehicle_id or not service_type or not service_date or not service_time:
            messages.error(request, "Please fill in all appointment details.")
            return render(request, "book_service.html", {"vehicles": vehicles})

        vehicle = get_object_or_404(Vehicle, id=vehicle_id, user_id=user_id)

        booking = ServiceBooking.objects.create(
            user_id=user_id,
            vehicle=vehicle,
            service_type=service_type,
            service_date=service_date,
            service_time=service_time,
            description=description,
            status="Pending"
        )
        messages.success(request, f"Service booked successfully for {vehicle.brand} {vehicle.model}! Booking ID: #{booking.id}")
        return redirect("my_bookings")

    return render(request, "book_service.html", {"vehicles": vehicles})


def my_bookings(request):
    user_id = request.session.get("user_id")
    if not user_id:
        return redirect("login")

    all_bookings = ServiceBooking.objects.filter(user_id=user_id).select_related("vehicle").order_by("-service_date", "-id")
    
    total_count = all_bookings.count()
    active_count = sum(1 for b in all_bookings if str(b.status).lower() in ["in progress", "progress", "confirmed"])
    pending_count = sum(1 for b in all_bookings if str(b.status).lower() == "pending")
    completed_count = sum(1 for b in all_bookings if str(b.status).lower() == "completed")

    status_filter = request.GET.get("status", "").strip()
    search_query = request.GET.get("q", "").strip()

    bookings = list(all_bookings)
    if status_filter:
        sf = status_filter.lower()
        if sf == "active":
            bookings = [b for b in bookings if str(b.status).lower() in ["in progress", "progress", "confirmed"]]
        elif sf == "pending":
            bookings = [b for b in bookings if str(b.status).lower() == "pending"]
        elif sf == "completed":
            bookings = [b for b in bookings if str(b.status).lower() == "completed"]
        elif sf == "cancelled":
            bookings = [b for b in bookings if str(b.status).lower() == "cancelled"]

    if search_query:
        q = search_query.lower()
        bookings = [
            b for b in bookings
            if q in str(b.vehicle.brand).lower()
            or q in str(b.vehicle.model).lower()
            or q in str(b.vehicle.vehicle_number).lower()
            or q in str(b.service_type).lower()
            or q in str(b.id)
        ]

    for booking in bookings:
        booking.payment = Payment.objects.filter(booking=booking, payment_status="Paid").first()

    return render(request, "my_bookings.html", {
        "bookings": bookings,
        "total_count": total_count,
        "active_count": active_count,
        "pending_count": pending_count,
        "completed_count": completed_count,
        "status_filter": status_filter,
        "search_query": search_query,
    })


def view_booking(request, booking_id):
    user_id = request.session.get("user_id")
    if not user_id:
        return redirect("login")

    booking = get_object_or_404(ServiceBooking, id=booking_id, user_id=user_id)
    amount = get_service_amount(booking.service_type)
    payment = Payment.objects.filter(booking=booking, payment_status="Paid").first()
    review = ServiceReview.objects.filter(booking=booking).first()

    return render(request, "view_booking.html", {
        "booking": booking,
        "amount": amount,
        "payment": payment,
        "review": review,
    })


def submit_review(request, booking_id):
    user_id = request.session.get("user_id")
    if not user_id:
        return redirect("login")

    booking = get_object_or_404(ServiceBooking, id=booking_id, user_id=user_id)

    if booking.status != "Completed":
        messages.warning(request, "You can submit a review once your service appointment is marked Completed.")
        return redirect("view_booking", booking_id=booking.id)

    if request.method == "POST":
        try:
            rating = int(request.POST.get("rating", 5))
            if rating < 1 or rating > 5:
                rating = 5
        except ValueError:
            rating = 5

        comment = request.POST.get("comment", "").strip()

        ServiceReview.objects.update_or_create(
            booking=booking,
            defaults={
                "user_id": user_id,
                "rating": rating,
                "comment": comment
            }
        )
        messages.success(request, f"Thank you for your valuable feedback! Rating saved: {'★' * rating}")

    return redirect("view_booking", booking_id=booking.id)


def download_invoice(request, booking_id):
    user_id = request.session.get("user_id")
    if not user_id:
        return redirect("login")

    is_admin = request.session.get("is_admin", False)
    if is_admin or User.objects.filter(id=user_id, is_admin=True).exists():
        booking = get_object_or_404(ServiceBooking, id=booking_id)
    else:
        booking = get_object_or_404(ServiceBooking, id=booking_id, user_id=user_id)

    payment = Payment.objects.filter(booking=booking, payment_status="Paid").first()

    if not payment:
        messages.error(request, "Invoice can only be downloaded after payment is completed.")
        return redirect("view_booking", booking_id=booking.id)

    pdf_content = generate_pdf_invoice(booking, payment)
    response = HttpResponse(pdf_content, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="AutoFixPro_Invoice_BK{booking.id}.pdf"'
    return response


def preview_invoice(request, booking_id):
    user_id = request.session.get("user_id")
    if not user_id:
        return redirect("login")

    is_admin = request.session.get("is_admin", False)
    if is_admin or User.objects.filter(id=user_id, is_admin=True).exists():
        booking = get_object_or_404(ServiceBooking, id=booking_id)
    else:
        booking = get_object_or_404(ServiceBooking, id=booking_id, user_id=user_id)

    payment = Payment.objects.filter(booking=booking, payment_status="Paid").first()

    if not payment:
        messages.error(request, "Invoice preview is only available after payment is completed.")
        return redirect("view_booking", booking_id=booking.id)

    pdf_content = generate_pdf_invoice(booking, payment)
    response = HttpResponse(pdf_content, content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="AutoFixPro_Invoice_BK{booking.id}.pdf"'
    return response


@require_POST
def cancel_booking(request, booking_id):
    user_id = request.session.get("user_id")
    if not user_id:
        return redirect("login")

    booking = get_object_or_404(ServiceBooking, id=booking_id, user_id=user_id)
    booking.delete()
    messages.success(request, f"Booking #{booking_id} cancelled successfully.")
    return redirect("my_bookings")


def payment(request, booking_id):
    user_id = request.session.get("user_id")
    if not user_id:
        return redirect("login")

    booking = get_object_or_404(
        ServiceBooking,
        id=booking_id,
        user_id=user_id
    )

    amount = get_service_amount(booking.service_type)

    existing_payment = Payment.objects.filter(
        booking=booking,
        payment_status="Paid"
    ).first()

    if existing_payment:
        messages.info(
            request,
            f"Booking #{booking.id} has already been paid."
        )
        return redirect(
            "view_booking",
            booking_id=booking.id
        )

    client = razorpay.Client(
        auth=(
            settings.RAZORPAY_KEY_ID,
            settings.RAZORPAY_KEY_SECRET
        )
    )

    razorpay_amount = int(round(amount * 100))

    try:
        razorpay_order = client.order.create({
            "amount": razorpay_amount,
            "currency": "INR",
            "receipt": f"booking_{booking.id}",
            "notes": {
                "booking_id": str(booking.id),
                "user_id": str(user_id),
            }
        })
    except Exception as e:
        print(f"Razorpay order creation error: {e}")
        messages.error(
            request,
            "Unable to start payment. Please try again."
        )
        return redirect(
            "view_booking",
            booking_id=booking.id
        )

    Payment.objects.update_or_create(
        booking=booking,
        defaults={
            "amount": amount,
            "payment_method": "RAZORPAY",
            "razorpay_order_id": razorpay_order["id"],
            "razorpay_payment_id": "",
            "razorpay_signature": "",
            "payment_status": "Pending",
        }
    )

    context = {
        "booking": booking,
        "amount": amount,
        "razorpay_order_id": razorpay_order["id"],
        "razorpay_key_id": settings.RAZORPAY_KEY_ID,
    }

    return render(
        request,
        "payment.html",
        context
    )


@require_POST
def payment_success(request, booking_id):
    user_id = request.session.get("user_id")
    if not user_id:
        return redirect("login")

    booking = get_object_or_404(
        ServiceBooking,
        id=booking_id,
        user_id=user_id
    )

    existing_payment = Payment.objects.filter(
        booking=booking,
        payment_status="Paid"
    ).first()

    if existing_payment:
        messages.info(
            request,
            f"Booking #{booking.id} is already paid."
        )
        return redirect(
            "view_booking",
            booking_id=booking.id
        )

    razorpay_order_id = request.POST.get("razorpay_order_id", "").strip()
    razorpay_payment_id = request.POST.get("razorpay_payment_id", "").strip()
    razorpay_signature = request.POST.get("razorpay_signature", "").strip()

    if not razorpay_order_id:
        messages.error(request, "Invalid payment order.")
        return redirect("payment", booking_id=booking.id)

    if not razorpay_payment_id:
        messages.error(request, "Payment ID is missing.")
        return redirect("payment", booking_id=booking.id)

    if not razorpay_signature:
        messages.error(request, "Payment signature is missing.")
        return redirect("payment", booking_id=booking.id)

    payment_record = Payment.objects.filter(
        booking=booking,
        razorpay_order_id=razorpay_order_id
    ).first()

    if not payment_record:
        messages.error(request, "Payment order does not match this booking.")
        return redirect("payment", booking_id=booking.id)

    expected_amount = get_service_amount(booking.service_type)

    if float(payment_record.amount) != float(expected_amount):
        messages.error(request, "Payment amount verification failed.")
        return redirect("payment", booking_id=booking.id)

    client = razorpay.Client(
        auth=(
            settings.RAZORPAY_KEY_ID,
            settings.RAZORPAY_KEY_SECRET
        )
    )

    params = {
        "razorpay_order_id": razorpay_order_id,
        "razorpay_payment_id": razorpay_payment_id,
        "razorpay_signature": razorpay_signature,
    }

    try:
        client.utility.verify_payment_signature(params)
    except razorpay.errors.SignatureVerificationError:
        payment_record.payment_status = "Failed"
        payment_record.save(update_fields=["payment_status"])
        messages.error(request, "Payment verification failed.")
        return redirect("payment", booking_id=booking.id)
    except Exception as e:
        print(f"Razorpay verification error: {e}")
        messages.error(request, "Unable to verify payment. Please try again.")
        return redirect("payment", booking_id=booking.id)

    payment_record.razorpay_payment_id = razorpay_payment_id
    payment_record.razorpay_signature = razorpay_signature
    payment_record.payment_status = "Paid"
    payment_record.payment_method = "RAZORPAY"
    payment_record.save()

    # Dispatch branded payment confirmation email with Tax Invoice PDF
    send_payment_invoice_email(booking, payment_record)

    messages.success(
        request,
        f"Payment of ₹{expected_amount} successful! Booking #{booking.id} confirmed. 🎉"
    )
    return redirect("view_booking", booking_id=booking.id)


@require_POST
def cash_payment(request, booking_id):
    user_id = request.session.get("user_id")
    if not user_id:
        return redirect("login")

    booking = get_object_or_404(
        ServiceBooking,
        id=booking_id,
        user_id=user_id
    )

    existing_payment = Payment.objects.filter(
        booking=booking,
        payment_status="Paid"
    ).first()

    if existing_payment:
        messages.info(
            request,
            f"Booking #{booking.id} is already paid."
        )
        return redirect(
            "view_booking",
            booking_id=booking.id
        )

    amount = get_service_amount(booking.service_type)

    Payment.objects.update_or_create(
        booking=booking,
        defaults={
            "amount": amount,
            "payment_method": "CASH",
            "razorpay_order_id": "",
            "razorpay_payment_id": "",
            "razorpay_signature": "",
            "payment_status": "Pending",
        }
    )

    messages.success(
        request,
        f"Booking #{booking.id} confirmed. Please pay ₹{amount} at the workshop."
    )
    return redirect("view_booking", booking_id=booking.id)



def service_history(request):
    user_id = request.session.get("user_id")
    if not user_id:
        return redirect("login")

    q = request.GET.get("q", "").strip()
    selected_vehicle_id = request.GET.get("vehicle_id", "").strip()

    vehicles = Vehicle.objects.filter(user_id=user_id).order_by("brand", "model")

    completed_services = ServiceBooking.objects.filter(
        user_id=user_id, status__iexact="Completed"
    ).select_related("vehicle").order_by("-service_date", "-id")

    if selected_vehicle_id:
        completed_services = completed_services.filter(vehicle_id=selected_vehicle_id)

    if q:
        completed_services = completed_services.filter(
            vehicle__brand__icontains=q
        ) | completed_services.filter(
            vehicle__model__icontains=q
        ) | completed_services.filter(
            vehicle__vehicle_number__icontains=q
        ) | completed_services.filter(
            service_type__icontains=q
        )

    all_completed = list(completed_services)
    total_completed = len(all_completed)
    total_spent = 0.0

    for booking in all_completed:
        booking.payment = Payment.objects.filter(booking=booking, payment_status="Paid").first()
        booking.review = ServiceReview.objects.filter(booking=booking).first()
        if booking.payment:
            total_spent += float(booking.payment.amount)

    return render(request, "service_history.html", {
        "completed_services": all_completed,
        "total_completed": total_completed,
        "total_spent": total_spent,
        "search_query": q,
        "vehicles": vehicles,
        "selected_vehicle_id": selected_vehicle_id,
    })


def export_service_history_csv(request):
    import csv
    from django.http import HttpResponse

    user_id = request.session.get("user_id")
    if not user_id:
        return redirect("login")

    completed_services = ServiceBooking.objects.filter(
        user_id=user_id, status__iexact="Completed"
    ).select_related("vehicle").order_by("-service_date", "-id")

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="autofixpro_maintenance_history.csv"'

    writer = csv.writer(response)
    writer.writerow(["Booking ID", "Vehicle", "License Plate", "Service Package", "Completion Date", "Amount Paid (INR)", "Payment Method", "Technician Work Notes"])

    for b in completed_services:
        payment = Payment.objects.filter(booking=b, payment_status="Paid").first()
        writer.writerow([
            f"#BK-{b.id}",
            f"{b.vehicle.brand} {b.vehicle.model}",
            b.vehicle.vehicle_number,
            b.service_type,
            b.service_date,
            payment.amount if payment else "N/A",
            payment.payment_method if payment else "N/A",
            b.description or "Routine workshop maintenance",
        ])

    return response


def profile(request):
    user_id = request.session.get("user_id")
    if not user_id:
        return redirect("login")

    user = get_object_or_404(User, id=user_id)
    user_vehicles = Vehicle.objects.filter(user=user)
    user_bookings = ServiceBooking.objects.filter(user=user).select_related("vehicle").order_by("-service_date")

    context = {
        "user": user,
        "name": user.fullname,
        "email": user.email,
        "phone": user.phone,
        "vehicles": user_vehicles,
        "vehicle_count": user_vehicles.count(),
        "bookings": user_bookings[:3],
        "booking_count": user_bookings.count(),
        "completed_count": user_bookings.filter(status__iexact="Completed").count(),
        "pending_count": user_bookings.filter(status__iexact="Pending").count(),
    }
    return render(request, "profile.html", context)


def edit_profile(request):
    user_id = request.session.get("user_id")
    if not user_id:
        return redirect("login")

    user = get_object_or_404(User, id=user_id)
    user_vehicles = Vehicle.objects.filter(user=user)
    user_bookings = ServiceBooking.objects.filter(user=user)

    sidebar_ctx = {
        "vehicle_count": user_vehicles.count(),
        "booking_count": user_bookings.count(),
        "completed_count": user_bookings.filter(status__iexact="Completed").count(),
    }

    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        email = request.POST.get("email", "").strip().lower()
        phone = request.POST.get("phone", "").strip()

        if not name or not email or not phone:
            messages.error(request, "All fields are required.")
            return render(request, "edit_profile.html", {"user": user, "name": name, "email": email, "phone": phone, **sidebar_ctx})

        clean_phone = "".join(filter(str.isdigit, phone))
        if len(clean_phone) != 10:
            messages.error(request, "Contact number must be exactly 10 digits.")
            return render(request, "edit_profile.html", {"user": user, "name": name, "email": email, "phone": phone, **sidebar_ctx})

        if User.objects.filter(email=email).exclude(id=user.id).exists():
            messages.error(request, "This email address is already in use by another account.")
            return render(request, "edit_profile.html", {"user": user, "name": name, "email": email, "phone": phone, **sidebar_ctx})

        user.fullname = name
        user.email = email
        user.phone = clean_phone
        user.save()

        request.session["name"] = name
        request.session["email"] = email
        request.session["phone"] = clean_phone

        messages.success(request, "Profile updated successfully! 🎉")
        return redirect("profile")

    return render(request, "edit_profile.html", {
        "user": user,
        "name": user.fullname,
        "email": user.email,
        "phone": user.phone,
        **sidebar_ctx
    })


def change_password(request):
    user_id = request.session.get("user_id")
    if not user_id:
        return redirect("login")

    user = get_object_or_404(User, id=user_id)

    if request.method == "POST":
        current_password = request.POST.get("current_password", "")
        new_password = request.POST.get("new_password", "")
        confirm_password = request.POST.get("confirm_password", "")

        if not check_password(current_password, user.password):
            messages.error(request, "Current password is incorrect.")
        elif not new_password or len(new_password) < 8:
            messages.error(request, "New password must be at least 8 characters long.")
        elif new_password != confirm_password:
            messages.error(request, "New passwords do not match.")
        elif check_password(new_password, user.password):
            messages.error(request, "New password must be different from your current password.")
        else:
            user.password = make_password(new_password)
            user.save(update_fields=["password"])
            messages.success(request, "Password changed successfully.")
            return redirect("profile")

    return render(request, "change_password.html")


def admin_required(view_func):
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        user_id = request.session.get("user_id")

        if not user_id:
            messages.error(request, "Admin login required. Please sign in.")
            return redirect("login")

        user = User.objects.filter(id=user_id, is_admin=True).first()

        if not user:
            request.session.flush()
            messages.error(
                request,
                "Access denied. Administrator privileges required."
            )
            return redirect("login")

        return view_func(request, *args, **kwargs)

    return _wrapped_view


@admin_required
def admin_dashboard(request):
    total_users = User.objects.count()
    total_vehicles = Vehicle.objects.count()
    total_bookings = ServiceBooking.objects.count()
    total_payments = Payment.objects.filter(payment_status="Paid").count()

    recent_bookings = ServiceBooking.objects.select_related(
        "vehicle", "vehicle__user"
    ).order_by("-id")[:5]

    recent_users = User.objects.order_by("-id")[:5]

    # Graph 1: Bookings by Service Type
    service_booking_data = (
        ServiceBooking.objects
        .values("service_type")
        .annotate(total=Count("id"))
        .order_by("-total")
    )

    service_labels = [
        item["service_type"] for item in service_booking_data
    ]

    service_counts = [
        item["total"] for item in service_booking_data
    ]

    # Graph 2: Monthly Bookings Trend
    monthly_booking_data = (
        ServiceBooking.objects
        .annotate(month=TruncMonth("service_date"))
        .values("month")
        .annotate(total=Count("id"))
        .order_by("month")
    )

    monthly_labels = [
        item["month"].strftime("%b %Y") if item["month"] else "N/A"
        for item in monthly_booking_data
    ]

    monthly_counts = [
        item["total"]
        for item in monthly_booking_data
    ]

    # Graph 3: Booking Status Distribution
    status_booking_data = (
        ServiceBooking.objects
        .values("status")
        .annotate(total=Count("id"))
        .order_by("status")
    )

    status_labels = [
        item["status"] for item in status_booking_data
    ]

    status_counts = [
        item["total"] for item in status_booking_data
    ]

    # Graph 4: Monthly Revenue
    monthly_revenue_data = (
        Payment.objects
        .filter(payment_status="Paid")
        .annotate(month=TruncMonth("payment_date"))
        .values("month")
        .annotate(total=Sum("amount"))
        .order_by("month")
    )

    revenue_labels = [
        item["month"].strftime("%b %Y") if item["month"] else "N/A"
        for item in monthly_revenue_data
    ]

    revenue_counts = [
        float(item["total"]) if item["total"] is not None else 0.0
        for item in monthly_revenue_data
    ]

    context = {
        "total_users": total_users,
        "total_vehicles": total_vehicles,
        "total_bookings": total_bookings,
        "total_payments": total_payments,
        "recent_bookings": recent_bookings,
        "recent_users": recent_users,
        # Graph 1 data
        "service_labels": service_labels,
        "service_counts": service_counts,
        # Graph 2 data
        "monthly_labels": monthly_labels,
        "monthly_counts": monthly_counts,
        # Graph 3 data
        "status_labels": status_labels,
        "status_counts": status_counts,
        # Graph 4 data
        "revenue_labels": revenue_labels,
        "revenue_counts": revenue_counts,
    }

    return render(request, "admin_dashboard.html", context)


@admin_required
def manage_users(request):
    search = request.GET.get("search", "").strip()
    users = User.objects.all().order_by("-id")
    if search:
        users = users.filter(fullname__icontains=search) | users.filter(email__icontains=search) | users.filter(phone__icontains=search)

    return render(request, "manage_users.html", {"users": users, "search": search})


@admin_required
def add_user(request):
    if request.method == "POST":
        fullname = request.POST.get("fullname", "").strip()
        email = request.POST.get("email", "").strip().lower()
        phone = request.POST.get("phone", "").strip()
        password = request.POST.get("password", "")

        if not fullname or not email or not phone or not password:
            messages.error(request, "All fields are required.")
            return render(request, "add_user.html")

        clean_phone = "".join(filter(str.isdigit, phone))
        if len(clean_phone) != 10:
            messages.error(request, "Contact number must be exactly 10 digits.")
            return render(request, "add_user.html")

        if len(password) < 8:
            messages.error(request, "Password must be at least 8 characters long.")
            return render(request, "add_user.html")

        if User.objects.filter(email=email).exists():
            messages.error(request, "A user with this email already exists.")
            return render(request, "add_user.html")

        User.objects.create(
            fullname=fullname,
            email=email,
            phone=clean_phone,
            password=make_password(password)
        )
        messages.success(request, f"User '{fullname}' created successfully.")
        return redirect("manage_users")

    return render(request, "add_user.html")


@admin_required
def edit_user(request, user_id):
    user = get_object_or_404(User, id=user_id)

    if request.method == "POST":
        fullname = request.POST.get("fullname", "").strip()
        email = request.POST.get("email", "").strip().lower()
        phone = request.POST.get("phone", "").strip()
        password = request.POST.get("password", "").strip()

        if fullname and email and phone:
            clean_phone = "".join(filter(str.isdigit, phone))
            if len(clean_phone) != 10:
                messages.error(request, "Contact number must be exactly 10 digits.")
                return render(request, "edit_user.html", {"user": user})

            user.fullname = fullname
            user.email = email
            user.phone = clean_phone
            if password:
                if len(password) < 8:
                    messages.error(request, "Password must be at least 8 characters long.")
                    return render(request, "edit_user.html", {"user": user})
                user.password = make_password(password)
            user.save()
            messages.success(request, f"User '{fullname}' updated successfully.")
            return redirect("manage_users")
        messages.error(request, "Please fill in all required fields.")

    return render(request, "edit_user.html", {"user": user})


@admin_required
@require_POST
def delete_user(request, user_id):
    if user_id == request.session.get("user_id"):
        messages.error(request, "You cannot delete your currently logged in admin account.")
        return redirect("manage_users")

    user = get_object_or_404(User, id=user_id)
    username = user.fullname
    user.delete()
    messages.success(request, f"User '{username}' deleted successfully.")
    return redirect("manage_users")


@admin_required
def manage_vehicles(request):
    search = request.GET.get("search", "").strip()
    vehicles = Vehicle.objects.select_related("user").all().order_by("-id")
    if search:
        vehicles = vehicles.filter(
            vehicle_number__icontains=search
        ) | vehicles.filter(brand__icontains=search) | vehicles.filter(model__icontains=search) | vehicles.filter(user__fullname__icontains=search) | vehicles.filter(user__phone__icontains=search)

    return render(request, "manage_vehicles.html", {"vehicles": vehicles, "search": search})


@admin_required
def manage_bookings(request):
    search = request.GET.get("search", "").strip()
    status_filter = request.GET.get("status", "").strip()

    bookings = ServiceBooking.objects.select_related("vehicle", "vehicle__user").all().order_by("-service_date", "-id")
    if status_filter:
        bookings = bookings.filter(status__iexact=status_filter)
    if search:
        bookings = bookings.filter(
            vehicle__vehicle_number__icontains=search
        ) | bookings.filter(vehicle__brand__icontains=search) | bookings.filter(vehicle__user__fullname__icontains=search)

    return render(request, "manage_bookings.html", {
        "bookings": bookings,
        "search": search,
        "status_filter": status_filter
    })


@admin_required
def export_bookings_csv(request):
    search = request.GET.get("search", "").strip()
    status_filter = request.GET.get("status", "").strip()

    bookings = ServiceBooking.objects.select_related("vehicle", "vehicle__user", "user").all().order_by("-service_date", "-id")

    if status_filter:
        bookings = bookings.filter(status__iexact=status_filter)
    if search:
        bookings = bookings.filter(
            Q(vehicle__vehicle_number__icontains=search)
            | Q(vehicle__brand__icontains=search)
            | Q(vehicle__model__icontains=search)
            | Q(vehicle__user__fullname__icontains=search)
            | Q(user__fullname__icontains=search)
        )

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="autofixpro_bookings_{timestamp}.csv"'

    # Write UTF-8 BOM for Microsoft Excel compatibility
    response.write("\ufeff")

    writer = csv.writer(response)
    writer.writerow([
        "Booking ID",
        "Customer Name",
        "Customer Email",
        "Customer Phone",
        "Vehicle Brand",
        "Vehicle Model",
        "Registration No",
        "Fuel Type",
        "Service Package",
        "Appointment Date",
        "Appointment Time",
        "Current Status",
        "Estimated Amount (INR)",
        "Payment Status"
    ])

    for b in bookings:
        customer = b.user or (b.vehicle.user if b.vehicle else None)
        c_name = customer.fullname if customer else "N/A"
        c_email = customer.email if customer else "N/A"
        c_phone = customer.phone if customer else "N/A"

        v_brand = b.vehicle.brand if b.vehicle else "N/A"
        v_model = b.vehicle.model if b.vehicle else "N/A"
        v_plate = b.vehicle.vehicle_number if b.vehicle else "N/A"
        v_fuel = b.vehicle.fuel_type if b.vehicle else "N/A"

        amt = get_service_amount(b.service_type)
        pay = Payment.objects.filter(booking=b).first()
        pay_status = pay.payment_status if pay else "Unpaid"

        writer.writerow([
            f"#{b.id}",
            c_name,
            c_email,
            c_phone,
            v_brand,
            v_model,
            v_plate,
            v_fuel,
            b.service_type,
            b.service_date.strftime("%d-%m-%Y") if b.service_date else "",
            b.service_time.strftime("%I:%M %p") if b.service_time else "",
            b.status,
            f"{amt:.2f}",
            pay_status
        ])

    return response



def send_booking_status_email(booking, old_status, new_status):
    """
    Sends an automated, branded AutoFixPro notification email to customer
    whenever their service appointment status is updated by the workshop admin.
    """
    if not booking or not booking.user or not booking.user.email:
        return False

    recipient_email = booking.user.email.strip()
    recipient_name = booking.user.fullname or "Valued Customer"
    vehicle_name = f"{booking.vehicle.brand} {booking.vehicle.model} ({booking.vehicle.vehicle_number})"

    # Status-specific subject line & message details
    s_lower = new_status.lower()
    if s_lower == "completed":
        subject = f"🚗 Your Vehicle is Ready for Pickup! — AutoFixPro Booking #{booking.id}"
        badge_bg = "#10b981"
        badge_text = "READY FOR PICKUP"
        headline = "Great news! Your vehicle service is completed."
        status_note = "Our certified technicians have completed all required servicing, repairs, and our multi-point safety inspection. Your vehicle is ready for pickup at our workshop."
    elif s_lower in ["in progress", "progress"]:
        subject = f"🔧 Service Started on Your {booking.vehicle.brand} — AutoFixPro Booking #{booking.id}"
        badge_bg = "#f59e0b"
        badge_text = "SERVICE IN PROGRESS"
        headline = "Your vehicle service is now underway."
        status_note = "Our workshop mechanic has checked in your vehicle and started servicing. You can track live stage progress directly in your customer portal."
    elif s_lower in ["quality check", "testing"]:
        subject = f"🔍 Quality Check in Progress — AutoFixPro Booking #{booking.id}"
        badge_bg = "#8b5cf6"
        badge_text = "FINAL QUALITY AUDIT"
        headline = "Final inspection in progress."
        status_note = "Mechanical servicing is finished. Our senior diagnostic engineer is currently conducting a road test and electronic scan before final handover."
    elif s_lower == "confirmed":
        subject = f"📅 Service Booking Confirmed — AutoFixPro Booking #{booking.id}"
        badge_bg = "#3b82f6"
        badge_text = "BOOKING CONFIRMED"
        headline = "Your service slot is confirmed."
        status_note = f"Your appointment for {booking.service_type} on {booking.service_date} at {booking.service_time} is locked in. We look forward to servicing your vehicle!"
    elif s_lower == "cancelled":
        subject = f"⚠️ Booking #{booking.id} Cancelled — AutoFixPro"
        badge_bg = "#ef4444"
        badge_text = "CANCELLED"
        headline = "Your service appointment was cancelled."
        status_note = "This service booking has been cancelled. If this was a mistake or you need to reschedule, you can book again anytime."
    else:
        subject = f"AutoFixPro Service Update: Booking #{booking.id} is {new_status}"
        badge_bg = "#64748b"
        badge_text = new_status.upper()
        headline = f"Status updated to {new_status}."
        status_note = f"Your service booking status has been updated to {new_status}."

    html_message = f"""
    <div style="font-family: 'Plus Jakarta Sans', Arial, sans-serif; max-width: 600px; margin: 0 auto; background: #ffffff; border: 1px solid #e2e8f0; border-radius: 16px; overflow: hidden; box-shadow: 0 4px 20px rgba(0,0,0,0.06);">
        <div style="background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%); padding: 32px 28px; text-align: center; border-bottom: 3px solid #ff4d30;">
            <h1 style="color: #ffffff; margin: 0; font-size: 24px; font-weight: 800; letter-spacing: -0.5px;">AutoFix<span style="color: #ff4d30;">Pro</span></h1>
            <p style="color: #94a3b8; margin: 6px 0 0; font-size: 13px;">Official Workshop Service Notification</p>
        </div>
        <div style="padding: 32px 28px; color: #1e293b;">
            <p style="font-size: 16px; margin: 0 0 16px;">Hello <strong>{recipient_name}</strong>,</p>
            <p style="font-size: 15px; line-height: 1.6; color: #334155; margin: 0 0 24px;">{headline}</p>

            <div style="background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 12px; padding: 20px; margin-bottom: 24px;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 14px; border-bottom: 1px solid #e2e8f0; padding-bottom: 12px;">
                    <span style="font-size: 12px; color: #64748b; text-transform: uppercase; font-weight: 700;">Status Update</span>
                    <span style="display: inline-block; background: {badge_bg}; color: #ffffff; padding: 5px 12px; border-radius: 20px; font-size: 11px; font-weight: 800; letter-spacing: 0.5px;">{badge_text}</span>
                </div>
                <div style="font-size: 13.5px; line-height: 1.8; color: #334155;">
                    <div><strong>Booking ID:</strong> #{booking.id}</div>
                    <div><strong>Vehicle:</strong> {vehicle_name}</div>
                    <div><strong>Service Package:</strong> {booking.service_type}</div>
                    <div><strong>Scheduled Date:</strong> {booking.service_date} ({booking.service_time})</div>
                </div>
            </div>

            <div style="background: rgba(255, 77, 48, 0.06); border-left: 4px solid #ff4d30; padding: 14px 18px; border-radius: 0 8px 8px 0; margin-bottom: 26px;">
                <p style="margin: 0; font-size: 13.5px; line-height: 1.6; color: #0f172a;">{status_note}</p>
            </div>

            <div style="text-align: center; margin: 28px 0 10px;">
                <a href="http://127.0.0.1:8080/view_booking/{booking.id}/" style="background: #ff4d30; color: #ffffff; padding: 12px 28px; text-decoration: none; border-radius: 8px; font-size: 14px; font-weight: 700; display: inline-block; box-shadow: 0 4px 14px rgba(255, 77, 48, 0.35);">
                    View Live Service Tracker &rarr;
                </a>
            </div>
        </div>
        <div style="background: #f1f5f9; padding: 18px 24px; text-align: center; font-size: 12px; color: #64748b; border-top: 1px solid #e2e8f0;">
            Questions? Call our workshop desk at <strong>+91 98765 43210</strong> or reply to this email.<br>
            &copy; 2026 AutoFixPro Workshop Technologies Inc.
        </div>
    </div>
    """

    plain_message = f"AutoFixPro Service Update: Booking #{booking.id} status is now {new_status}. Vehicle: {vehicle_name}. {status_note}"
    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", None) or f"AutoFixPro <{getattr(settings, 'EMAIL_HOST_USER', '')}>"

    try:
        send_mail(
            subject=subject,
            message=plain_message,
            from_email=from_email,
            recipient_list=[recipient_email],
            html_message=html_message,
            fail_silently=False
        )
        print(f"[AutoFixPro Status Email] -> Sent to {recipient_email} | Booking #{booking.id} -> '{new_status}'")
        return True
    except Exception as e:
        print(f"[AutoFixPro Status Email Error to {recipient_email}]: {e}")
        return False


def send_payment_invoice_email(booking, payment):
    """
    Sends an automated, branded AutoFixPro payment receipt and attaches
    the official GST Tax Invoice PDF to the customer's registered email.
    """
    if not booking or not booking.user or not booking.user.email:
        return False

    recipient_email = booking.user.email.strip()
    recipient_name = booking.user.fullname or "Valued Customer"
    vehicle_name = f"{booking.vehicle.brand} {booking.vehicle.model} ({booking.vehicle.vehicle_number})"
    invoice_num = f"INV-{booking.id:05d}"
    amount = f"{float(payment.amount):.2f}"
    pay_method = (payment.payment_method or "ONLINE").upper()
    txn_id = payment.razorpay_payment_id or f"TXN-CSH{payment.id:05d}"
    pay_date = payment.payment_date.strftime("%d %b %Y, %I:%M %p") if payment.payment_date else datetime.now().strftime("%d %b %Y, %I:%M %p")

    subject = f"🧾 Payment Confirmed & Tax Invoice #{invoice_num} — AutoFixPro Booking #{booking.id}"

    plain_message = (
        f"Hello {recipient_name},\n\n"
        f"Thank you for your payment! We have received ₹{amount} for Booking #{booking.id}.\n"
        f"Vehicle: {vehicle_name}\n"
        f"Service: {booking.service_type}\n"
        f"Payment Method: {pay_method}\n"
        f"Transaction ID: {txn_id}\n\n"
        f"Your official GST Tax Invoice PDF is attached to this email.\n\n"
        f"Best regards,\nAutoFixPro Workshop Technologies"
    )

    html_message = f"""
    <div style="font-family: 'Plus Jakarta Sans', Arial, sans-serif; max-width: 600px; margin: 0 auto; background: #ffffff; border: 1px solid #e2e8f0; border-radius: 16px; overflow: hidden; box-shadow: 0 4px 20px rgba(0,0,0,0.06);">
        <div style="background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%); padding: 32px 28px; text-align: center; border-bottom: 3px solid #10b981;">
            <h1 style="color: #ffffff; margin: 0; font-size: 24px; font-weight: 800; letter-spacing: -0.5px;">AutoFix<span style="color: #ff4d30;">Pro</span></h1>
            <p style="color: #94a3b8; margin: 6px 0 0; font-size: 13px;">Official Payment Receipt &amp; Tax Invoice</p>
        </div>
        <div style="padding: 32px 28px; color: #1e293b;">
            <p style="font-size: 16px; margin: 0 0 16px;">Hello <strong>{recipient_name}</strong>,</p>
            <p style="font-size: 15px; line-height: 1.6; color: #334155; margin: 0 0 24px;">
                We have successfully received your payment. Your official GST-compliant Tax Invoice has been generated and is attached to this email as a PDF.
            </p>

            <div style="background: #f0fdf4; border: 1px solid #bbf7d0; border-radius: 12px; padding: 22px; margin-bottom: 24px; text-align: center;">
                <span style="display: inline-block; background: #10b981; color: #ffffff; padding: 4px 14px; border-radius: 20px; font-size: 11px; font-weight: 800; letter-spacing: 0.5px; margin-bottom: 10px;">PAYMENT SUCCESSFUL</span>
                <div style="font-size: 32px; font-weight: 800; color: #047857; margin-bottom: 6px;">₹{amount}</div>
                <div style="font-size: 12.5px; color: #065f46;">Settled via {pay_method} &bull; TXN: {txn_id}</div>
            </div>

            <div style="background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 12px; padding: 20px; margin-bottom: 24px;">
                <div style="font-size: 12px; color: #64748b; text-transform: uppercase; font-weight: 700; margin-bottom: 12px; border-bottom: 1px solid #e2e8f0; padding-bottom: 8px;">Transaction Breakdown</div>
                <table style="width: 100%; font-size: 13.5px; line-height: 1.9; color: #334155; border-collapse: collapse;">
                    <tr>
                        <td style="color: #64748b;">Invoice Number:</td>
                        <td style="text-align: right; font-weight: 700; color: #0f172a;">{invoice_num}</td>
                    </tr>
                    <tr>
                        <td style="color: #64748b;">Booking Reference:</td>
                        <td style="text-align: right; font-weight: 600;">#{booking.id}</td>
                    </tr>
                    <tr>
                        <td style="color: #64748b;">Vehicle:</td>
                        <td style="text-align: right; font-weight: 600;">{vehicle_name}</td>
                    </tr>
                    <tr>
                        <td style="color: #64748b;">Service Package:</td>
                        <td style="text-align: right; font-weight: 600;">{booking.service_type}</td>
                    </tr>
                    <tr>
                        <td style="color: #64748b;">Payment Date:</td>
                        <td style="text-align: right; font-weight: 600;">{pay_date}</td>
                    </tr>
                </table>
            </div>

            <div style="background: rgba(16, 185, 129, 0.08); border-left: 4px solid #10b981; padding: 14px 18px; border-radius: 0 8px 8px 0; margin-bottom: 26px;">
                <p style="margin: 0; font-size: 13.5px; line-height: 1.6; color: #065f46;">
                    📎 <strong>PDF Invoice Attached:</strong> Your tax invoice <code>AutoFixPro_Invoice_{invoice_num}.pdf</code> is attached to this email. You can also preview or download it anytime from your customer dashboard.
                </p>
            </div>

            <div style="text-align: center; margin: 28px 0 10px;">
                <a href="http://127.0.0.1:8080/view_booking/{booking.id}/" style="background: #0f172a; color: #ffffff; padding: 12px 28px; text-decoration: none; border-radius: 8px; font-size: 14px; font-weight: 700; display: inline-block;">
                    View Booking &amp; Service History &rarr;
                </a>
            </div>
        </div>
        <div style="background: #f1f5f9; padding: 18px 24px; text-align: center; font-size: 12px; color: #64748b; border-top: 1px solid #e2e8f0;">
            Thank you for choosing AutoFixPro Workshop! | Phone: <strong>+91 98765 43210</strong><br>
            &copy; 2026 AutoFixPro Workshop Technologies Inc. All rights reserved.
        </div>
    </div>
    """

    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", None) or f"AutoFixPro <{getattr(settings, 'EMAIL_HOST_USER', '')}>"

    try:
        msg = EmailMultiAlternatives(
            subject=subject,
            body=plain_message,
            from_email=from_email,
            to=[recipient_email]
        )
        msg.attach_alternative(html_message, "text/html")

        # Generate and attach the official PDF Invoice
        try:
            pdf_bytes = generate_pdf_invoice(booking, payment)
            if pdf_bytes:
                msg.attach(
                    filename=f"AutoFixPro_Invoice_{invoice_num}.pdf",
                    content=pdf_bytes,
                    mimetype="application/pdf"
                )
        except Exception as pdf_err:
            print(f"[AutoFixPro Invoice Attachment Warning]: {pdf_err}")

        msg.send(fail_silently=False)
        print(f"[AutoFixPro Invoice Email] -> Successfully sent invoice to {recipient_email} for Booking #{booking.id}")
        return True
    except Exception as e:
        print(f"[AutoFixPro Invoice Email Error to {recipient_email}]: {e}")
        return False



@admin_required
@require_POST
def update_booking_status(request, booking_id):
    status = request.POST.get("status", "").strip()

    allowed_statuses = {
        "Pending",
        "Confirmed",
        "In Progress",
        "Quality Check",
        "Completed",
        "Cancelled",
    }

    if status not in allowed_statuses:
        messages.error(request, "Invalid booking status.")
        return redirect("manage_bookings")

    booking = get_object_or_404(ServiceBooking.objects.select_related("user", "vehicle"), id=booking_id)
    old_status = booking.status

    if old_status != status:
        booking.status = status
        booking.save(update_fields=["status"])
        send_booking_status_email(booking, old_status, status)
        messages.success(
            request,
            f"Booking #{booking_id} status updated to '{status}' and customer notified via email."
        )
    else:
        messages.info(request, f"Booking #{booking_id} is already in '{status}' status.")

    return redirect("manage_bookings")


@admin_required
def manage_payments(request):
    search = request.GET.get("search", "").strip()
    status_filter = request.GET.get("status", "").strip()

    all_payments_qs = Payment.objects.select_related(
        "booking", "booking__user", "booking__vehicle", "booking__vehicle__user"
    ).all()

    total_revenue = sum(p.amount for p in all_payments_qs if p.payment_status == "Paid")
    total_count = all_payments_qs.count()
    paid_count = all_payments_qs.filter(payment_status="Paid").count()
    pending_count = all_payments_qs.filter(payment_status__in=["Pending", "Created"]).count()
    failed_count = all_payments_qs.filter(payment_status__in=["Failed", "Cancelled"]).count()

    payments = all_payments_qs.order_by("-payment_date")

    if status_filter:
        if status_filter.lower() == "paid":
            payments = payments.filter(payment_status="Paid")
        elif status_filter.lower() == "pending":
            payments = payments.filter(payment_status__in=["Pending", "Created"])
        elif status_filter.lower() == "failed":
            payments = payments.filter(payment_status__in=["Failed", "Cancelled"])

    if search:
        clean_num = search.replace("#", "").replace("TXN-", "").replace("txn-", "").replace("BKG-", "").replace("bkg-", "").strip()
        q = (
            Q(booking__vehicle__user__fullname__icontains=search)
            | Q(booking__user__fullname__icontains=search)
            | Q(booking__vehicle__user__phone__icontains=search)
            | Q(booking__user__phone__icontains=search)
            | Q(booking__vehicle__vehicle_number__icontains=search)
            | Q(booking__vehicle__brand__icontains=search)
            | Q(booking__vehicle__model__icontains=search)
            | Q(razorpay_payment_id__icontains=search)
            | Q(razorpay_order_id__icontains=search)
            | Q(payment_method__icontains=search)
        )
        if clean_num.isdigit():
            q |= Q(id=int(clean_num)) | Q(booking__id=int(clean_num))

        payments = payments.filter(q)

    context = {
        "payments": payments,
        "total_revenue": total_revenue,
        "total_count": total_count,
        "paid_count": paid_count,
        "pending_count": pending_count,
        "failed_count": failed_count,
        "search": search,
        "status_filter": status_filter,
    }
    return render(request, "manage_payments.html", context)


@admin_required
@require_POST
def mark_payment_paid(request, payment_id):
    payment = get_object_or_404(Payment, id=payment_id)
    if payment.payment_status != "Paid":
        payment.payment_status = "Paid"
        if not payment.razorpay_payment_id:
            payment.razorpay_payment_id = f"CASH-{payment.id:05d}"
        payment.save(update_fields=["payment_status", "razorpay_payment_id"])

        # Send confirmation & tax invoice PDF to customer email
        send_payment_invoice_email(payment.booking, payment)
        messages.success(request, f"Payment #{payment.id} marked as Paid. Tax invoice emailed to {payment.booking.user.email}!")
    else:
        messages.info(request, f"Payment #{payment.id} is already marked as Paid.")
    return redirect("manage_payments")


@admin_required
def export_payments_csv(request):
    search = request.GET.get("search", "").strip()
    status_filter = request.GET.get("status", "").strip()

    payments_qs = Payment.objects.select_related(
        "booking", "booking__user", "booking__vehicle", "booking__vehicle__user"
    ).all().order_by("-payment_date")

    if status_filter:
        if status_filter.lower() == "paid":
            payments_qs = payments_qs.filter(payment_status="Paid")
        elif status_filter.lower() == "pending":
            payments_qs = payments_qs.filter(payment_status__in=["Pending", "Created"])
        elif status_filter.lower() == "failed":
            payments_qs = payments_qs.filter(payment_status__in=["Failed", "Cancelled"])

    if search:
        clean_num = search.replace("#", "").replace("TXN-", "").replace("txn-", "").replace("BKG-", "").replace("bkg-", "").strip()
        q = (
            Q(booking__vehicle__user__fullname__icontains=search)
            | Q(booking__user__fullname__icontains=search)
            | Q(booking__vehicle__user__phone__icontains=search)
            | Q(booking__user__phone__icontains=search)
            | Q(booking__vehicle__vehicle_number__icontains=search)
            | Q(booking__vehicle__brand__icontains=search)
            | Q(booking__vehicle__model__icontains=search)
            | Q(payment_method__icontains=search)
            | Q(payment_status__icontains=search)
        )
        if clean_num.isdigit():
            q |= Q(id=int(clean_num)) | Q(booking__id=int(clean_num))
        payments_qs = payments_qs.filter(q)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="autofixpro_payments_{timestamp}.csv"'

    # Write UTF-8 BOM for Excel
    response.write("\ufeff")

    writer = csv.writer(response)
    writer.writerow([
        "Transaction ID",
        "Booking ID",
        "Customer Name",
        "Customer Email",
        "Customer Phone",
        "Vehicle",
        "Registration No",
        "Service Package",
        "Amount (INR)",
        "Payment Method",
        "Razorpay Payment ID",
        "Payment Status",
        "Payment Date & Time"
    ])

    for p in payments_qs:
        b = p.booking
        customer = b.user if (b and b.user) else (b.vehicle.user if (b and b.vehicle) else None)
        c_name = customer.fullname if customer else "N/A"
        c_email = customer.email if customer else "N/A"
        c_phone = customer.phone if customer else "N/A"

        v_name = f"{b.vehicle.brand} {b.vehicle.model}" if (b and b.vehicle) else "N/A"
        v_plate = b.vehicle.vehicle_number if (b and b.vehicle) else "N/A"
        svc_type = b.service_type if b else "N/A"

        writer.writerow([
            f"#TXN-{p.id}",
            f"#BKG-{b.id}" if b else "N/A",
            c_name,
            c_email,
            c_phone,
            v_name,
            v_plate,
            svc_type,
            f"{p.amount:.2f}",
            p.payment_method,
            p.razorpay_payment_id or "N/A",
            p.payment_status,
            p.payment_date.strftime("%d-%m-%Y %I:%M %p") if p.payment_date else "N/A"
        ])

    return response



DEFAULT_INVENTORY_SEEDS = [
    {"name": "Premium Synthetic Engine Oil (5W-30)", "category": "Fluids", "quantity": 45, "price": 1200.00, "image_url": "/static/images/parts/engine_oil.jpg"},
    {"name": "Front Ceramic Brake Pads", "category": "Brakes", "quantity": 18, "price": 2500.00, "image_url": "/static/images/parts/brake_pads.jpg"},
    {"name": "High-Flow Oil Filter", "category": "Filters", "quantity": 60, "price": 350.00, "image_url": "/static/images/parts/air_filter.jpg"},
    {"name": "Iridium Spark Plug Set (x4)", "category": "Ignition", "quantity": 8, "price": 1800.00, "image_url": "/static/images/parts/spark_plugs.jpg"},
    {"name": "Engine Coolant Anti-Freeze (Red, 5L)", "category": "Fluids", "quantity": 25, "price": 850.00, "image_url": "/static/images/parts/coolant.jpg"},
    {"name": "Activated Carbon Cabin Air Filter", "category": "Filters", "quantity": 0, "price": 600.00, "image_url": "/static/images/parts/cabin_filter.jpg"},
    {"name": "Heavy Duty Maintenance-Free Car Battery 12V", "category": "Electrical", "quantity": 12, "price": 5500.00, "image_url": "/static/images/parts/battery.jpg"},
    {"name": "Aerodynamic Wiper Blade Pair", "category": "Accessories", "quantity": 30, "price": 900.00, "image_url": "/static/images/parts/wiper_blades.jpg"},
    {"name": "DOT 4 High Performance Brake Fluid (1L)", "category": "Fluids", "quantity": 40, "price": 450.00, "image_url": "/static/images/parts/brake_fluid.jpg"},
    {"name": "Engine Timing Belt Kit", "category": "Engine", "quantity": 6, "price": 4200.00, "image_url": "/static/images/parts/timing_belt.jpg"},
]


@admin_required
def inventory(request):
    # Auto-seed initial rich catalog if table has fewer than 5 items
    if Inventory.objects.count() < 5:
        for seed in DEFAULT_INVENTORY_SEEDS:
            if not Inventory.objects.filter(name=seed["name"]).exists():
                Inventory.objects.create(
                    name=seed["name"],
                    category=seed["category"],
                    quantity=seed["quantity"],
                    price=seed["price"],
                    image_url=seed.get("image_url", ""),
                )

    search = request.GET.get("search", "").strip()
    category_filter = request.GET.get("category", "").strip()
    status_filter = request.GET.get("status", "").strip()

    all_items = Inventory.objects.all()

    # Calculate overall catalog metrics
    total_items = all_items.count()
    total_valuation = sum(item.quantity * item.price for item in all_items)
    in_stock_count = all_items.filter(quantity__gt=10).count()
    low_stock_count = all_items.filter(quantity__gt=0, quantity__lte=10).count()
    out_of_stock_count = all_items.filter(quantity__lte=0).count()

    # Extract distinct categories
    categories = sorted(list(set(all_items.values_list("category", flat=True))))

    inventory_qs = all_items.order_by("-id")

    # Apply search filter
    if search:
        clean_search = search.replace("#", "").replace("PRT-", "").replace("prt-", "").strip()
        q = Q(name__icontains=search) | Q(category__icontains=search)
        if clean_search.isdigit():
            q |= Q(id=int(clean_search))
        inventory_qs = inventory_qs.filter(q)

    # Apply category filter
    if category_filter:
        inventory_qs = inventory_qs.filter(category=category_filter)

    # Apply status filter
    if status_filter:
        if status_filter == "In Stock":
            inventory_qs = inventory_qs.filter(quantity__gt=10)
        elif status_filter == "Low Stock":
            inventory_qs = inventory_qs.filter(quantity__gt=0, quantity__lte=10)
        elif status_filter == "Out of Stock":
            inventory_qs = inventory_qs.filter(quantity__lte=0)

    context = {
        "inventory": inventory_qs,
        "total_items": total_items,
        "total_valuation": total_valuation,
        "in_stock_count": in_stock_count,
        "low_stock_count": low_stock_count,
        "out_of_stock_count": out_of_stock_count,
        "categories": categories,
        "search": search,
        "category_filter": category_filter,
        "status_filter": status_filter,
    }
    return render(request, "inventory.html", context)


@admin_required
def add_inventory(request):
    categories = ["Fluids", "Brakes", "Filters", "Electrical", "Ignition", "Engine", "Accessories", "Tires & Wheels"]

    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        category = request.POST.get("category", "").strip()
        quantity_str = request.POST.get("quantity", "").strip()
        price_str = request.POST.get("price", "").strip()

        if not name or not category or quantity_str == "" or price_str == "":
            messages.error(request, "All fields are required.")
            return render(request, "add_inventory.html", {"categories": categories})

        try:
            quantity = int(quantity_str)
            if quantity < 0:
                raise ValueError
        except ValueError:
            messages.error(request, "Stock quantity must be a non-negative whole number.")
            return render(request, "add_inventory.html", {"categories": categories})

        try:
            price = float(price_str)
            if price <= 0:
                raise ValueError
        except ValueError:
            messages.error(request, "Unit price must be a valid positive amount.")
            return render(request, "add_inventory.html", {"categories": categories})

        image_file = request.FILES.get("image")
        image_url = request.POST.get("image_url", "").strip()

        Inventory.objects.create(
            name=name,
            category=category,
            quantity=quantity,
            price=price,
            image=image_file if image_file else None,
            image_url=image_url if image_url else None,
        )
        messages.success(request, f"Spare part '{name}' added successfully to inventory.")
        return redirect("inventory")

    return render(request, "add_inventory.html", {"categories": categories})


@admin_required
def edit_inventory(request, item_id):
    item = get_object_or_404(Inventory, id=item_id)
    categories = ["Fluids", "Brakes", "Filters", "Electrical", "Ignition", "Engine", "Accessories", "Tires & Wheels"]

    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        category = request.POST.get("category", "").strip()
        quantity_str = request.POST.get("quantity", "").strip()
        price_str = request.POST.get("price", "").strip()
        image_file = request.FILES.get("image")
        image_url = request.POST.get("image_url", "").strip()

        if not name or not category or quantity_str == "" or price_str == "":
            messages.error(request, "All fields are required.")
            return render(request, "edit_inventory.html", {"item": item, "categories": categories})

        try:
            quantity = int(quantity_str)
            if quantity < 0:
                raise ValueError
        except ValueError:
            messages.error(request, "Stock quantity must be a non-negative whole number.")
            return render(request, "edit_inventory.html", {"item": item, "categories": categories})

        try:
            price = float(price_str)
            if price <= 0:
                raise ValueError
        except ValueError:
            messages.error(request, "Unit price must be a valid positive amount.")
            return render(request, "edit_inventory.html", {"item": item, "categories": categories})

        item.name = name
        item.category = category
        item.quantity = quantity
        item.price = price
        if image_file:
            item.image = image_file
        if image_url is not None:
            item.image_url = image_url
        item.save()

        messages.success(request, f"Inventory item '{name}' updated successfully.")
        return redirect("inventory")

    return render(request, "edit_inventory.html", {"item": item, "categories": categories})


@admin_required
@require_POST
def delete_inventory(request, item_id):
    item = get_object_or_404(Inventory, id=item_id)
    item_name = item.name
    item.delete()
    messages.success(request, f"Spare part '{item_name}' removed from inventory.")
    return redirect("inventory")


@admin_required
def manage_messages(request):
    search = request.GET.get("search", "").strip()
    status_filter = request.GET.get("status", "").strip()

    all_messages = ContactMessage.objects.all()

    total_count = all_messages.count()
    pending_count = all_messages.filter(is_resolved=False).count()
    resolved_count = all_messages.filter(is_resolved=True).count()

    messages_qs = all_messages.order_by("-created_at")

    if search:
        messages_qs = messages_qs.filter(
            Q(name__icontains=search)
            | Q(email__icontains=search)
            | Q(phone__icontains=search)
            | Q(subject__icontains=search)
            | Q(message__icontains=search)
        )

    if status_filter == "pending":
        messages_qs = messages_qs.filter(is_resolved=False)
    elif status_filter == "resolved":
        messages_qs = messages_qs.filter(is_resolved=True)

    context = {
        "contact_messages": messages_qs,
        "total_count": total_count,
        "pending_count": pending_count,
        "resolved_count": resolved_count,
        "search": search,
        "status_filter": status_filter,
    }
    return render(request, "manage_messages.html", context)


@admin_required
@require_POST
def toggle_message_status(request, message_id):
    msg = get_object_or_404(ContactMessage, id=message_id)
    msg.is_resolved = not msg.is_resolved
    msg.save(update_fields=["is_resolved"])
    new_state = "Resolved" if msg.is_resolved else "Pending / Open"
    messages.success(request, f"Inquiry #{msg.id} marked as {new_state}.")
    return redirect("manage_messages")


@admin_required
@require_POST
def delete_message(request, message_id):
    msg = get_object_or_404(ContactMessage, id=message_id)
    sender = msg.name
    msg.delete()
    messages.success(request, f"Inquiry from '{sender}' was deleted.")
    return redirect("manage_messages")


@admin_required
def manage_reviews(request):
    search = request.GET.get("search", "").strip()
    rating_filter = request.GET.get("rating", "").strip()

    all_reviews = ServiceReview.objects.select_related("user", "booking", "booking__vehicle")

    total_count = all_reviews.count()
    avg_data = all_reviews.aggregate(Avg("rating"))
    avg_rating = round(avg_data["rating__avg"], 1) if avg_data["rating__avg"] is not None else 0.0
    five_star_count = all_reviews.filter(rating=5).count()
    low_rating_count = all_reviews.filter(rating__lte=2).count()

    reviews_qs = all_reviews.order_by("-created_at")

    if search:
        reviews_qs = reviews_qs.filter(
            Q(user__fullname__icontains=search)
            | Q(user__email__icontains=search)
            | Q(booking__vehicle__brand__icontains=search)
            | Q(booking__vehicle__model__icontains=search)
            | Q(booking__vehicle__vehicle_number__icontains=search)
            | Q(booking__service_type__icontains=search)
            | Q(comment__icontains=search)
        )

    if rating_filter == "5":
        reviews_qs = reviews_qs.filter(rating=5)
    elif rating_filter == "4":
        reviews_qs = reviews_qs.filter(rating=4)
    elif rating_filter == "3":
        reviews_qs = reviews_qs.filter(rating=3)
    elif rating_filter == "low":
        reviews_qs = reviews_qs.filter(rating__lte=2)

    context = {
        "reviews": reviews_qs,
        "total_count": total_count,
        "avg_rating": avg_rating,
        "five_star_count": five_star_count,
        "low_rating_count": low_rating_count,
        "search": search,
        "rating_filter": rating_filter,
    }
    return render(request, "manage_reviews.html", context)


@admin_required
@require_POST
def delete_review(request, review_id):
    review = get_object_or_404(ServiceReview, id=review_id)
    customer_name = review.user.fullname
    booking_id = review.booking.id
    review.delete()
    messages.success(request, f"Review by '{customer_name}' for Booking #{booking_id} was deleted.")
    return redirect("manage_reviews")

