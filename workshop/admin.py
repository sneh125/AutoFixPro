from django.contrib import admin
from .models import User, Vehicle, ServiceBooking, Payment, Inventory, BookingPart, EmailOTP, ContactMessage, ServiceReview


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ("id", "fullname", "email", "phone", "is_admin")
    list_filter = ("is_admin",)
    search_fields = ("fullname", "email", "phone")


@admin.register(Vehicle)
class VehicleAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "vehicle_number",
        "brand",
        "model",
        "year",
        "fuel_type",
        "color",
    )
    search_fields = ("vehicle_number", "brand", "model", "user__fullname", "user__email")


@admin.register(ServiceBooking)
class ServiceBookingAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "vehicle",
        "service_type",
        "service_date",
        "service_time",
        "status",
    )
    list_filter = ("status", "service_type")
    search_fields = ("user__fullname", "user__email", "vehicle__vehicle_number")


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "booking",
        "amount",
        "payment_method",
        "payment_status",
        "payment_date",
        "paid_at",
    )
    list_filter = ("payment_status", "payment_method")
    search_fields = ("razorpay_order_id", "razorpay_payment_id", "booking__id")


@admin.register(Inventory)
class InventoryAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "name",
        "category",
        "quantity",
        "price",
    )
    list_filter = ("category",)
    search_fields = ("name", "category")


@admin.register(BookingPart)
class BookingPartAdmin(admin.ModelAdmin):
    list_display = ("id", "booking", "inventory_item", "quantity", "unit_price", "added_at")
    list_filter = ("added_at",)
    search_fields = ("booking__id", "inventory_item__name")


@admin.register(EmailOTP)
class EmailOTPAdmin(admin.ModelAdmin):
    # Security: OTP plain value and OTP search are removed to protect user credentials
    list_display = ("id", "email", "purpose", "created_at", "is_used", "attempts")
    list_filter = ("purpose", "is_used")
    search_fields = ("email",)


@admin.register(ContactMessage)
class ContactMessageAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "email", "phone", "subject", "created_at", "is_resolved")
    list_filter = ("is_resolved", "created_at")
    search_fields = ("name", "email", "subject", "message")


@admin.register(ServiceReview)
class ServiceReviewAdmin(admin.ModelAdmin):
    list_display = ("id", "booking", "user", "rating", "created_at")
    list_filter = ("rating", "created_at")
    search_fields = ("user__fullname", "user__email", "comment")