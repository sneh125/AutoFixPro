from datetime import date, timedelta
from .models import Vehicle, ServiceBooking

RECOMMENDED_PACKAGES_BY_PREVIOUS = {
    "General Service": "Oil Change",
    "Oil Change": "Brake Service",
    "Brake Service": "General Service",
    "Tire Change": "General Service",
    "Full Vehicle Service": "General Service",
}


def get_vehicle_service_reminder(vehicle):
    """
    Analyzes a vehicle's booking history and determines:
    - active_booking: Any ongoing appointment (Pending, Confirmed, In Progress, etc.)
    - last_completed: Last finished service
    - next_due_date: Target date for next maintenance (default 90 days after last service or today if none)
    - days_remaining: integer days until due (negative if overdue)
    - status: 'active_service' | 'overdue' | 'due_soon' | 'upcoming' | 'healthy'
    - status_label: Human-friendly badge text
    - badge_class: CSS class for badge
    - recommended_service: Suggested package name
    - recommended_service_reason: Short explanation
    """
    today = date.today()

    # 1. Check for active/ongoing booking
    active_booking = vehicle.servicebooking_set.exclude(status__in=["Completed", "Cancelled"]).order_by("-service_date", "-id").first()
    if active_booking:
        return {
            "vehicle": vehicle,
            "has_active_booking": True,
            "active_booking": active_booking,
            "last_completed": vehicle.servicebooking_set.filter(status__iexact="Completed").order_by("-service_date", "-id").first(),
            "status": "active_service",
            "status_label": f"Service in progress ({active_booking.status})",
            "badge_class": "badge-progress",
            "urgency_rank": 4,
            "next_due_date": active_booking.service_date,
            "days_remaining": (active_booking.service_date - today).days,
            "recommended_service": active_booking.service_type,
            "recommended_service_reason": "Current ongoing appointment",
            "is_overdue": False,
            "is_due_soon": False,
            "is_healthy": False,
        }

    # 2. Check for last completed booking
    last_completed = vehicle.servicebooking_set.filter(status__iexact="Completed").order_by("-service_date", "-id").first()

    if last_completed:
        # Standard maintenance interval: 90 days (approx. 3 months or ~5,000 km)
        next_due_date = last_completed.service_date + timedelta(days=90)
        days_remaining = (next_due_date - today).days
        last_service_name = last_completed.service_type
        recommended_service = RECOMMENDED_PACKAGES_BY_PREVIOUS.get(last_service_name, "General Service")
        recommended_reason = f"Based on last {last_service_name} on {last_completed.service_date.strftime('%d %b %Y')}"
    else:
        # Vehicle has no completed service history yet: recommend initial health check
        next_due_date = today
        days_remaining = 0
        last_completed = None
        recommended_service = "General Service"
        recommended_reason = "First comprehensive health check & 40-point safety inspection"

    # 3. Categorize status
    if days_remaining < 0:
        status = "overdue"
        overdue_days = abs(days_remaining)
        status_label = f"Overdue by {overdue_days} day{'s' if overdue_days != 1 else ''}"
        badge_class = "badge-danger"
        urgency_rank = 1
        is_overdue = True
        is_due_soon = False
        is_healthy = False
    elif days_remaining <= 14:
        status = "due_soon"
        status_label = f"Due in {days_remaining} day{'s' if days_remaining != 1 else ''}" if days_remaining > 0 else "Due Today"
        badge_class = "badge-warning"
        urgency_rank = 2
        is_overdue = False
        is_due_soon = True
        is_healthy = False
    elif days_remaining <= 45:
        status = "upcoming"
        status_label = f"Due in {days_remaining} days"
        badge_class = "badge-info"
        urgency_rank = 3
        is_overdue = False
        is_due_soon = False
        is_healthy = False
    else:
        status = "healthy"
        status_label = f"Road Ready (Due in {days_remaining} days)"
        badge_class = "badge-success"
        urgency_rank = 5
        is_overdue = False
        is_due_soon = False
        is_healthy = True

    return {
        "vehicle": vehicle,
        "has_active_booking": False,
        "active_booking": None,
        "last_completed": last_completed,
        "next_due_date": next_due_date,
        "days_remaining": days_remaining,
        "status": status,
        "status_label": status_label,
        "badge_class": badge_class,
        "urgency_rank": urgency_rank,
        "recommended_service": recommended_service,
        "recommended_service_reason": recommended_reason,
        "is_overdue": is_overdue,
        "is_due_soon": is_due_soon,
        "is_healthy": is_healthy,
    }


def get_user_service_reminders(user_id):
    """
    Retrieves all service reminders for vehicles of a given user.
    Sorted by urgency: Overdue (1) -> Due Soon (2) -> Upcoming (3) -> Active Service (4) -> Healthy (5).
    """
    vehicles = Vehicle.objects.filter(user_id=user_id)
    reminders = [get_vehicle_service_reminder(v) for v in vehicles]
    reminders.sort(key=lambda r: (r["urgency_rank"], r["days_remaining"]))
    return reminders
