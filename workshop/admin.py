from django.contrib import admin
from .models import User, Vehicle, ServiceBooking, Payment, Inventory, EmailOTP, ContactMessage, ServiceReview


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


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "booking",
        "amount",
        "payment_date",
    )


@admin.register(Inventory)
class InventoryAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "name",
        "category",
        "quantity",
        "price",
    )


@admin.register(EmailOTP)
class EmailOTPAdmin(admin.ModelAdmin):
    list_display = ("id", "email", "otp", "purpose", "created_at", "is_used")
    list_filter = ("purpose", "is_used")
    search_fields = ("email", "otp")


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