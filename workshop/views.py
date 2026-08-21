from django.shortcuts import get_object_or_404, render, redirect
from django.http import HttpResponse
from django.contrib import messages
from django.views.decorators.csrf import csrf_exempt
from django.core.mail import send_mail
from django.utils import timezone
from functools import wraps
from .models import User, Vehicle, ServiceBooking, Payment, Inventory, EmailOTP, ContactMessage, ServiceReview
from .invoice_generator import generate_pdf_invoice
import random
import time
import razorpay
from django.conf import settings

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
    reviews = ServiceReview.objects.filter(rating__gte=4).select_related('user', 'booking__vehicle')[:6]
    return render(request, 'home.html', {'reviews': reviews})


def contact(request):
    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        email = request.POST.get("email", "").strip()
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

        messages.success(request, f"Thank you, {name}! Your message has been received. Our workshop team will get back to you shortly.")
        return redirect("contact")

    initial_data = {}
    if request.session.get("user_id"):
        try:
            current_user = User.objects.get(id=request.session["user_id"])
            initial_data["name"] = current_user.name
            initial_data["email"] = current_user.email
            initial_data["phone"] = current_user.phone
        except User.DoesNotExist:
            pass

    return render(request, "contact.html", initial_data)


def send_otp_email(email, purpose, request=None):
    EmailOTP.objects.filter(email=email, purpose=purpose, is_used=False).update(is_used=True)
    otp = f"{random.randint(100000, 999999)}"

    EmailOTP.objects.create(
        email=email,
        otp=otp,
        purpose=purpose
    )

    if request:
        request.session[f'otp_email_{purpose}'] = email
        request.session[f'otp_last_sent_{purpose}'] = time.time()

    purpose_titles = {
        'register': 'Account Email Verification',
        'forgot_password': 'Password Reset Code',
        'login_otp': 'Instant Login Code'
    }
    title = purpose_titles.get(purpose, 'Verification Code')

    subject = f"AutoFixPro - {title}: {otp}"
    message = f"""
Hello,

Your 6-digit AutoFixPro verification code is:

    ===========================
             {otp}
    ===========================

This OTP is valid for {getattr(settings, 'EMAIL_OTP_EXPIRY_MINUTES', 5)} minutes.
Please do not share this code with anyone.

Best regards,
AutoFixPro Workshop Team
support@autofixpro.com
"""

    html_message = f"""
    <div style="font-family: 'Segoe UI', Arial, sans-serif; max-width: 500px; margin: 0 auto; background: #ffffff; border: 1px solid #e2e8f0; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 16px rgba(0,0,0,0.06);">
        <div style="background: #0f172a; padding: 24px; text-align: center;">
            <h1 style="color: #ffffff; margin: 0; font-size: 24px; letter-spacing: -0.5px;">AutoFix<span style="color: #ff4d30;">Pro</span></h1>
            <p style="color: #94a3b8; margin: 4px 0 0; font-size: 13px;">Premium Vehicle Workshop &amp; Auto Care</p>
        </div>
        <div style="padding: 30px 25px; text-align: center;">
            <h2 style="color: #0f172a; font-size: 20px; margin-top: 0;">{title}</h2>
            <p style="color: #64748b; font-size: 14.5px; line-height: 1.5;">Use the one-time verification code below to complete your action:</p>
            <div style="background: #f8fafc; border: 2px dashed #ff4d30; border-radius: 10px; padding: 18px; margin: 25px 0; font-size: 32px; font-weight: 800; letter-spacing: 8px; color: #ff4d30;">
                {otp}
            </div>
            <p style="color: #94a3b8; font-size: 13px;">This code will expire in {getattr(settings, 'EMAIL_OTP_EXPIRY_MINUTES', 5)} minutes. If you did not request this, please ignore this email.</p>
        </div>
        <div style="background: #f1f5f9; padding: 14px; text-align: center; font-size: 12px; color: #64748b; border-top: 1px solid #e2e8f0;">
            &copy; 2026 AutoFixPro Technologies Inc.
        </div>
    </div>
    """

    try:
        send_mail(
            subject=subject,
            message=message,
            from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'AutoFixPro <support@autofixpro.com>'),
            recipient_list=[email],
            html_message=html_message,
            fail_silently=False
        )
    except Exception as e:
        print(f"[AutoFixPro Email Dispatch Error]: {e}")
    
    print(f"\n==========================================")
    print(f" [AutoFixPro OTP SENT] -> {email} ({purpose}) : {otp}")
    print(f"==========================================\n")

    return otp


def register(request):
    if request.method == "POST":
        fullname = request.POST.get("fullname", "").strip()
        email = request.POST.get("email", "").strip()
        phone = request.POST.get("phone", "").strip()
        password = request.POST.get("password", "")
        confirm_password = request.POST.get("confirm_password", "")

        if not fullname or not email or not phone or not password:
            messages.error(request, "Please fill in all required fields.")
            return render(request, "register.html")

        if password != confirm_password:
            messages.error(request, "Passwords do not match.")
            return render(request, "register.html")

        if User.objects.filter(email=email).exists():
            messages.error(request, "Email is already registered. Please login or reset your password.")
            return render(request, "register.html")

        request.session["reg_data"] = {
            "fullname": fullname,
            "email": email,
            "phone": phone,
            "password": password
        }

        send_otp_email(email, "register", request)
        messages.info(request, f"A 6-digit verification code was sent to {email}. Please enter it below.")
        return redirect("verify_otp", purpose="register")

    return render(request, "register.html")


def verify_otp(request, purpose):
    email = request.session.get(f'otp_email_{purpose}')

    if not email:
        if purpose == 'register':
            reg_data = request.session.get('reg_data')
            if reg_data:
                email = reg_data.get('email')
                request.session[f'otp_email_{purpose}'] = email
            else:
                messages.error(request, "Session expired. Please fill in the registration form again.")
                return redirect("register")
        elif purpose == 'forgot_password':
            messages.error(request, "Please enter your email address to reset password.")
            return redirect("forgot_password")
        elif purpose == 'login_otp':
            messages.error(request, "Please enter your email address to receive a login code.")
            return redirect("login_otp")
        else:
            return redirect("login")

    purpose_meta = {
        'register': {
            'title': 'Verify Your Email Address',
            'desc': f'We sent a 6-digit confirmation code to {email}. Enter it below to activate your AutoFixPro account.',
            'back_url': 'register',
            'back_label': 'Back to Registration',
        },
        'forgot_password': {
            'title': 'Password Reset Verification',
            'desc': f'We sent a 6-digit recovery code to {email}. Enter it below to proceed with resetting your password.',
            'back_url': 'forgot_password',
            'back_label': 'Back to Forgot Password',
        },
        'login_otp': {
            'title': 'Instant Login Verification',
            'desc': f'We sent a 6-digit one-time code to {email}. Enter it below to log into your account.',
            'back_url': 'login_otp',
            'back_label': 'Back to OTP Login',
        }
    }
    meta = purpose_meta.get(purpose, purpose_meta['register'])

    if request.method == "POST":
        otp_input = request.POST.get("otp", "").strip()
        if not otp_input:
            digits = [request.POST.get(f"digit_{i}", "") for i in range(1, 7)]
            otp_input = "".join(digits).strip()

        if not otp_input or len(otp_input) != 6:
            messages.error(request, "Please enter the complete 6-digit verification code.")
            return render(request, "verify_otp.html", {"email": email, "purpose": purpose, "meta": meta})

        otp_record = EmailOTP.objects.filter(
            email=email,
            purpose=purpose,
            is_used=False
        ).order_by("-created_at").first()

        expiry_minutes = getattr(settings, 'EMAIL_OTP_EXPIRY_MINUTES', 5)

        if not otp_record or not otp_record.is_valid(expiry_minutes):
            messages.error(request, "This OTP has expired. Please click 'Resend OTP' to receive a fresh code.")
            return render(request, "verify_otp.html", {"email": email, "purpose": purpose, "meta": meta})

        if otp_record.otp != otp_input:
            messages.error(request, "Invalid verification code. Please check the code and try again.")
            return render(request, "verify_otp.html", {"email": email, "purpose": purpose, "meta": meta})

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
            if "reg_data" in request.session:
                del request.session["reg_data"]

            request.session["user_id"] = user.id
            request.session["name"] = user.fullname
            request.session["email"] = user.email
            request.session["phone"] = user.phone

            messages.success(request, f"Welcome to AutoFixPro, {user.fullname}! Your email was verified and your account is active. 🎉")
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

            request.session["user_id"] = user.id
            request.session["name"] = user.fullname
            request.session["email"] = user.email
            request.session["phone"] = user.phone
            request.session["is_admin"] = user.is_admin

            if user.is_admin:
                messages.success(request, f"Welcome back Administrator {user.fullname}! 🛡️")
                return redirect("admin_dashboard")

            messages.success(request, f"Welcome back, {user.fullname}! Logged in successfully.")
            return redirect("dashboard")

    return render(request, "verify_otp.html", {
        "email": email,
        "purpose": purpose,
        "meta": meta,
        "expiry_minutes": getattr(settings, 'EMAIL_OTP_EXPIRY_MINUTES', 5)
    })


def resend_otp(request, purpose):
    email = request.session.get(f'otp_email_{purpose}')
    if not email and purpose == 'register':
        reg_data = request.session.get('reg_data')
        if reg_data:
            email = reg_data.get('email')

    if not email:
        messages.error(request, "Session expired. Please restart the request.")
        return redirect("login")

    last_sent = request.session.get(f'otp_last_sent_{purpose}', 0)
    if time.time() - last_sent < 15:
        messages.warning(request, "Please wait a few seconds before requesting another OTP.")
        return redirect("verify_otp", purpose=purpose)

    send_otp_email(email, purpose, request)
    messages.success(request, f"A fresh OTP verification code was sent to {email}.")
    return redirect("verify_otp", purpose=purpose)


def forgot_password(request):
    if request.method == "POST":
        email = request.POST.get("email", "").strip()

        if not email:
            messages.error(request, "Please enter your registered email address.")
            return render(request, "forgot_password.html")

        user = User.objects.filter(email=email).first()
        if not user:
            messages.error(request, "No account is registered with this email address.")
            return render(request, "forgot_password.html")

        send_otp_email(email, "forgot_password", request)
        messages.info(request, f"Password reset OTP sent to {email}.")
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

        if not new_password or len(new_password) < 4:
            messages.error(request, "New password must be at least 4 characters long.")
            return render(request, "reset_password.html", {"email": email})

        if new_password != confirm_password:
            messages.error(request, "Passwords do not match.")
            return render(request, "reset_password.html", {"email": email})

        user = User.objects.filter(email=email).first()
        if not user:
            messages.error(request, "User account not found.")
            return redirect("forgot_password")

        user.password = new_password
        user.save()

        if "reset_password_allowed" in request.session:
            del request.session["reset_password_allowed"]

        messages.success(request, "Your password was reset successfully! Please login with your new password.")
        return redirect("login")

    return render(request, "reset_password.html", {"email": email})


def login_otp(request):
    if request.method == "POST":
        email = request.POST.get("email", "").strip()

        if not email:
            messages.error(request, "Please enter your email address.")
            return render(request, "login_otp.html")

        user = User.objects.filter(email=email).first()
        if not user:
            messages.error(request, "No account registered with this email address. Please register first.")
            return render(request, "login_otp.html")

        send_otp_email(email, "login_otp", request)
        messages.info(request, f"One-time login code sent to {email}.")
        return redirect("verify_otp", purpose="login_otp")

    return render(request, "login_otp.html")


def login(request):
    if request.method == "POST":
        email = request.POST.get("email", "").strip()
        password = request.POST.get("password", "")

        try:
            user = User.objects.get(email=email, password=password)
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

        except User.DoesNotExist:
            messages.error(request, "Invalid email or password. Please try again or use 'Login with OTP'.")

    return render(request, "login.html")


def logout(request):
    request.session.flush()
    messages.info(request, "You have been logged out successfully.")
    return redirect("login")


def dashboard(request):
    if "user_id" not in request.session:
        return redirect("login")

    user_id = request.session.get("user_id")
    name = request.session.get("name", "User")

    user_vehicles = Vehicle.objects.filter(user_id=user_id)
    vehicle_count = user_vehicles.count()

    user_bookings = ServiceBooking.objects.filter(user_id=user_id).select_related("vehicle").order_by("-service_date")
    total_bookings = user_bookings.count()
    pending_bookings = user_bookings.filter(status__iexact="Pending").count()
    completed_bookings = user_bookings.filter(status__iexact="Completed").count()
    recent_bookings = user_bookings[:5]

    context = {
        "name": name,
        "vehicles": user_vehicles[:3],
        "vehicle_count": vehicle_count,
        "total_bookings": total_bookings,
        "pending_bookings": pending_bookings,
        "completed_bookings": completed_bookings,
        "recent_bookings": recent_bookings,
    }
    return render(request, "dashboard.html", context)


def my_vehicle(request):
    if "user_id" not in request.session:
        return redirect("login")

    user_id = request.session.get("user_id")
    search = request.GET.get("search", "").strip()

    vehicles = Vehicle.objects.filter(user_id=user_id)
    if search:
        vehicles = vehicles.filter(vehicle_number__icontains=search) | vehicles.filter(brand__icontains=search) | vehicles.filter(model__icontains=search)

    return render(request, "my_vehicle.html", {"vehicles": vehicles, "search": search})


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

    bookings = ServiceBooking.objects.filter(
        user_id=user_id
    ).select_related("vehicle").order_by("-service_date")

    for booking in bookings:
        booking.payment = Payment.objects.filter(
            booking=booking,
            payment_status="Paid"
        ).first()

    return render(request, "my_bookings.html", {"bookings": bookings})


def view_booking(request, booking_id):
    user_id = request.session.get("user_id")
    if not user_id:
        return redirect("login")

    booking = get_object_or_404(ServiceBooking, id=booking_id, user_id=user_id)
    amount = get_service_amount(booking.service_type)
    payment = Payment.objects.filter(booking=booking, payment_status="Paid").first()
    review = ServiceReview.objects.filter(booking=booking).first()

    return render(
        request,
        "view_booking.html",
        {
            "booking": booking,
            "amount": amount,
            "payment": payment,
            "review": review,
        }
    )


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

    return redirect("view_booking", booking_id=booking.id)


def download_invoice(request, booking_id):
    user_id = request.session.get("user_id")
    if not user_id:
        return redirect("login")

    booking = get_object_or_404(ServiceBooking, id=booking_id, user_id=user_id)
    payment = Payment.objects.filter(booking=booking, payment_status="Paid").first()

    if not payment:
        messages.error(request, "Invoice can only be downloaded after payment is completed.")
        return redirect("view_booking", booking_id=booking.id)

    pdf_content = generate_pdf_invoice(booking, payment)

    response = HttpResponse(pdf_content, content_type="application/pdf")
    filename = f"AutoFixPro_Invoice_BK{booking.id}.pdf"
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


def preview_invoice(request, booking_id):
    user_id = request.session.get("user_id")
    if not user_id:
        return redirect("login")

    booking = get_object_or_404(ServiceBooking, id=booking_id, user_id=user_id)
    payment = Payment.objects.filter(booking=booking, payment_status="Paid").first()

    if not payment:
        messages.error(request, "Invoice preview is only available after payment is completed.")
        return redirect("view_booking", booking_id=booking.id)

    pdf_content = generate_pdf_invoice(booking, payment)

    response = HttpResponse(pdf_content, content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="AutoFixPro_Invoice_BK{booking.id}.pdf"'
    return response


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

    booking = get_object_or_404(ServiceBooking, id=booking_id, user_id=user_id)
    amount = get_service_amount(booking.service_type)

    existing_payment = Payment.objects.filter(booking=booking).first()
    if existing_payment and existing_payment.payment_status == "Paid":
        messages.info(request, f"Booking #{booking.id} has already been paid.")
        return redirect("view_booking", booking_id=booking.id)

    client = razorpay.Client(
        auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET)
    )

    razorpay_amount = int(amount * 100)
    razorpay_order = client.order.create({
        "amount": razorpay_amount,
        "currency": "INR",
        "payment_capture": 1
    })

    context = {
        "booking": booking,
        "amount": amount,
        "razorpay_order_id": razorpay_order["id"],
        "razorpay_key_id": settings.RAZORPAY_KEY_ID,
    }
    return render(request, "payment.html", context)


@csrf_exempt
def payment_success(request, booking_id):
    if request.method != "POST":
        return redirect("view_booking", booking_id=booking_id)

    booking = get_object_or_404(ServiceBooking, id=booking_id)

    existing = Payment.objects.filter(booking=booking, payment_status="Paid").first()
    if existing:
        messages.info(request, f"Booking #{booking.id} is already paid.")
        return redirect("view_booking", booking_id=booking.id)

    razorpay_order_id = request.POST.get("razorpay_order_id", "")
    razorpay_payment_id = request.POST.get("razorpay_payment_id", "")
    razorpay_signature = request.POST.get("razorpay_signature", "")
    payment_method = request.POST.get("payment_method", "NET_BANKING")

    amount = get_service_amount(booking.service_type)

    if payment_method == "CASH" or razorpay_signature == "CASH_BYPASS":
        user_id = request.session.get("user_id")
        if not user_id or user_id != booking.user.id:
            return redirect("login")

        Payment.objects.update_or_create(
            booking=booking,
            defaults={
                "amount": amount,
                "payment_method": "CASH",
                "razorpay_order_id": razorpay_order_id,
                "razorpay_payment_id": razorpay_payment_id,
                "razorpay_signature": "",
                "payment_status": "Paid",
            }
        )
        messages.success(
            request,
            f"Booking #{booking.id} confirmed! Please pay ₹{amount} in cash at the workshop. 💵"
        )
        return redirect("view_booking", booking_id=booking.id)

    client = razorpay.Client(
        auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET)
    )

    params = {
        "razorpay_order_id": razorpay_order_id,
        "razorpay_payment_id": razorpay_payment_id,
        "razorpay_signature": razorpay_signature,
    }

    try:
        client.utility.verify_payment_signature(params)
        signature_valid = True
    except razorpay.errors.SignatureVerificationError:
        signature_valid = False
    except Exception:
        signature_valid = False

    if signature_valid:
        request.session["user_id"] = booking.user.id
        request.session["name"] = booking.user.fullname
        request.session["email"] = booking.user.email
        request.session["phone"] = booking.user.phone

        Payment.objects.update_or_create(
            booking=booking,
            defaults={
                "amount": amount,
                "payment_method": payment_method,
                "razorpay_order_id": razorpay_order_id,
                "razorpay_payment_id": razorpay_payment_id,
                "razorpay_signature": razorpay_signature,
                "payment_status": "Paid",
            }
        )
        messages.success(
            request,
            f"Payment of ₹{amount} successful! Booking #{booking.id} confirmed. 🎉"
        )
        return redirect("view_booking", booking_id=booking.id)
    else:
        messages.error(
            request,
            "Payment verification failed. Please try again or contact support if amount was deducted."
        )
        return redirect("payment", booking_id=booking.id)


def service_history(request):
    user_id = request.session.get("user_id")
    if not user_id:
        return redirect("login")

    completed_services = ServiceBooking.objects.filter(
        user_id=user_id,
        status__iexact="Completed"
    ).select_related("vehicle").order_by("-service_date")

    for booking in completed_services:
        booking.payment = Payment.objects.filter(
            booking=booking,
            payment_status="Paid"
        ).first()

    context = {
        "completed_services": completed_services,
    }
    return render(request, "service_history.html", context)


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

    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        email = request.POST.get("email", "").strip()
        phone = request.POST.get("phone", "").strip()

        if not name or not email or not phone:
            messages.error(request, "All fields are required.")
            return render(request, "edit_profile.html", {
                "user": user, "name": name, "email": email, "phone": phone
            })

        if User.objects.filter(email=email).exclude(id=user.id).exists():
            messages.error(request, "This email address is already in use by another account.")
            return render(request, "edit_profile.html", {
                "user": user, "name": name, "email": email, "phone": phone
            })

        user.fullname = name
        user.email = email
        user.phone = phone
        user.save()

        request.session["name"] = name
        request.session["email"] = email
        request.session["phone"] = phone

        messages.success(request, "Profile updated successfully! 🎉")
        return redirect("profile")

    return render(request, "edit_profile.html", {
        "user": user,
        "name": user.fullname,
        "email": user.email,
        "phone": user.phone,
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

        if current_password != user.password:
            messages.error(request, "Current password is incorrect.")
        elif not new_password or len(new_password) < 4:
            messages.error(request, "New password must be at least 4 characters long.")
        elif new_password != confirm_password:
            messages.error(request, "New passwords do not match.")
        else:
            user.password = new_password
            user.save()
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

        user = User.objects.filter(id=user_id).first()
        if not user or not user.is_admin:
            messages.error(request, "Access denied. Administrator privileges required.")
            return redirect("dashboard")

        return view_func(request, *args, **kwargs)
    return _wrapped_view


@admin_required
def admin_dashboard(request):
    total_users = User.objects.count()
    total_vehicles = Vehicle.objects.count()
    total_bookings = ServiceBooking.objects.count()
    total_payments = Payment.objects.filter(payment_status="Paid").count()

    recent_bookings = ServiceBooking.objects.select_related("vehicle", "vehicle__user").order_by("-id")[:5]
    recent_users = User.objects.order_by("-id")[:5]

    context = {
        "total_users": total_users,
        "total_vehicles": total_vehicles,
        "total_bookings": total_bookings,
        "total_payments": total_payments,
        "recent_bookings": recent_bookings,
        "recent_users": recent_users,
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
        email = request.POST.get("email", "").strip()
        phone = request.POST.get("phone", "").strip()
        password = request.POST.get("password", "")

        if not fullname or not email or not phone or not password:
            messages.error(request, "All fields are required.")
            return render(request, "add_user.html")

        if User.objects.filter(email=email).exists():
            messages.error(request, "A user with this email already exists.")
            return render(request, "add_user.html")

        User.objects.create(
            fullname=fullname,
            email=email,
            phone=phone,
            password=password
        )
        messages.success(request, f"User '{fullname}' created successfully.")
        return redirect("manage_users")

    return render(request, "add_user.html")


@admin_required
def edit_user(request, user_id):
    user = get_object_or_404(User, id=user_id)

    if request.method == "POST":
        fullname = request.POST.get("fullname", "").strip()
        email = request.POST.get("email", "").strip()
        phone = request.POST.get("phone", "").strip()
        password = request.POST.get("password", "").strip()

        if fullname and email and phone:
            user.fullname = fullname
            user.email = email
            user.phone = phone
            if password:
                user.password = password
            user.save()
            messages.success(request, f"User '{fullname}' updated successfully.")
            return redirect("manage_users")
        else:
            messages.error(request, "Please fill in all required fields.")

    return render(request, "edit_user.html", {"user": user})


@admin_required
def delete_user(request, user_id):
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
        vehicles = vehicles.filter(vehicle_number__icontains=search) | vehicles.filter(brand__icontains=search) | vehicles.filter(model__icontains=search) | vehicles.filter(user__fullname__icontains=search)

    return render(request, "manage_vehicles.html", {"vehicles": vehicles, "search": search})


@admin_required
def manage_bookings(request):
    search = request.GET.get("search", "").strip()
    status_filter = request.GET.get("status", "").strip()

    bookings = ServiceBooking.objects.select_related("vehicle", "vehicle__user").all().order_by("-service_date", "-id")
    if status_filter:
        bookings = bookings.filter(status__iexact=status_filter)
    if search:
        bookings = bookings.filter(vehicle__vehicle_number__icontains=search) | bookings.filter(vehicle__brand__icontains=search) | bookings.filter(vehicle__user__fullname__icontains=search)

    return render(request, "manage_bookings.html", {
        "bookings": bookings,
        "search": search,
        "status_filter": status_filter
    })


@admin_required
def update_booking_status(request, booking_id):
    if request.method == "POST":
        status = request.POST.get("status")
        booking = get_object_or_404(ServiceBooking, id=booking_id)
        booking.status = status
        booking.save()
        messages.success(request, f"Booking #{booking_id} status updated to '{status}'.")
    return redirect("manage_bookings")


@admin_required
def manage_payments(request):
    payments = Payment.objects.select_related("booking", "booking__vehicle", "booking__vehicle__user").all().order_by("-payment_date")
    total_revenue = sum(p.amount for p in payments if p.payment_status == "Paid")
    return render(request, "manage_payments.html", {"payments": payments, "total_revenue": total_revenue})


@admin_required
def inventory(request):
    inventory_items = [
        {"id": 1, "name": "Premium Synthetic Engine Oil (5W-30)", "category": "Fluids", "quantity": 45, "unit_price": 1200.00, "status": "In Stock"},
        {"id": 2, "name": "Front Ceramic Brake Pads", "category": "Brakes", "quantity": 18, "unit_price": 2500.00, "status": "In Stock"},
        {"id": 3, "name": "High-Flow Oil Filter", "category": "Filters", "quantity": 60, "unit_price": 350.00, "status": "In Stock"},
        {"id": 4, "name": "Iridium Spark Plug Set (x4)", "category": "Ignition", "quantity": 8, "unit_price": 1800.00, "status": "Low Stock"},
        {"id": 5, "name": "Engine Coolant Anti-Freeze (Red, 5L)", "category": "Fluids", "quantity": 25, "unit_price": 850.00, "status": "In Stock"},
        {"id": 6, "name": "Activated Carbon Cabin Air Filter", "category": "Filters", "quantity": 0, "unit_price": 600.00, "status": "Out of Stock"},
        {"id": 7, "name": "Heavy Duty Maintenance-Free Car Battery 12V", "category": "Electrical", "quantity": 12, "unit_price": 5500.00, "status": "In Stock"},
        {"id": 8, "name": "Aerodynamic Wiper Blade Pair", "category": "Accessories", "quantity": 30, "unit_price": 900.00, "status": "In Stock"},
        {"id": 9, "name": "DOT 4 High Performance Brake Fluid (1L)", "category": "Fluids", "quantity": 40, "unit_price": 450.00, "status": "In Stock"},
        {"id": 10, "name": "Engine Timing Belt Kit", "category": "Engine", "quantity": 6, "unit_price": 4200.00, "status": "Low Stock"},
    ]
    return render(request, "inventory.html", {"inventory": inventory_items})
