from django.contrib import admin
from django.urls import path
from django.http import HttpResponse
from workshop import views

def favicon(request):
    return HttpResponse(status=204)

urlpatterns = [
    # Customer Portal & Authentication
    path('', views.home, name='home'),
    path('contact/', views.contact, name='contact'),
    path('register/', views.register, name='register'),
    path('login/', views.login, name='login'),
    path('login-otp/', views.login_otp, name='login_otp'),
    path('forgot-password/', views.forgot_password, name='forgot_password'),
    path('reset-password/', views.reset_password, name='reset_password'),
    path('verify-otp/<str:purpose>/', views.verify_otp, name='verify_otp'),
    path('resend-otp/<str:purpose>/', views.resend_otp, name='resend_otp'),
    path('logout/', views.logout, name='logout'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('add_vehicle/', views.add_vehicle, name='add_vehicle'),
    path('my_vehicle/', views.my_vehicle, name='my_vehicle'),
    path('edit_vehicle/<int:vehicle_id>/', views.edit_vehicle, name='edit_vehicle'),
    path('delete_vehicle/<int:vehicle_id>/', views.delete_vehicle, name='delete_vehicle'),
    path('update_vehicle/<int:vehicle_id>/', views.update_vehicle, name='update_vehicle'),
    path('book_service/', views.book_service, name='book_service'),
    path('my_bookings/', views.my_bookings, name='my_bookings'),
    path('view_booking/<int:booking_id>/', views.view_booking, name='view_booking'),
    path('booking/<int:booking_id>/invoice/', views.download_invoice, name='download_invoice'),
    path('booking/<int:booking_id>/invoice/preview/', views.preview_invoice, name='preview_invoice'),
    path('booking/<int:booking_id>/review/', views.submit_review, name='submit_review'),
    path('cancel_booking/<int:booking_id>/', views.cancel_booking, name='cancel_booking'),
    path('payment/<int:booking_id>/', views.payment, name='payment'),
    path('payment/<int:booking_id>/success/', views.payment_success, name='payment_success'),
    path('service_history/', views.service_history, name='service_history'),
    path('profile/', views.profile, name='profile'),
    path('edit_profile/', views.edit_profile, name='edit_profile'),
    path('change_password/', views.change_password, name='change_password'),

    # Admin Management Portal
    path('admin-dashboard/', views.admin_dashboard, name='admin_dashboard'),
    path('admin-dashboard/users/', views.manage_users, name='manage_users'),
    path('admin-dashboard/users/add/', views.add_user, name='add_user'),
    path('admin-dashboard/users/edit/<int:user_id>/', views.edit_user, name='edit_user'),
    path('admin-dashboard/users/delete/<int:user_id>/', views.delete_user, name='delete_user'),
    path('admin-dashboard/vehicles/', views.manage_vehicles, name='manage_vehicles'),
    path('admin-dashboard/bookings/', views.manage_bookings, name='manage_bookings'),
    path('admin-dashboard/bookings/update-status/<int:booking_id>/', views.update_booking_status, name='update_booking_status'),
    path('admin-dashboard/payments/', views.manage_payments, name='manage_payments'),
    path('admin-dashboard/inventory/', views.inventory, name='inventory'),

    # Fallback shortcuts
    path('manage-users/', views.manage_users),
    path('add_user/', views.add_user),
    path('edit-user/<int:user_id>/', views.edit_user),
    path('delete_user/<int:user_id>/', views.delete_user),
    path('manage_vehicles/', views.manage_vehicles),

    # System & Django Admin
    path('favicon.ico', favicon, name='favicon'),
    path('admin/', admin.site.urls),
]
