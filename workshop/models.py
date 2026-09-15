from django.db import models


class User(models.Model):
    fullname = models.CharField(max_length=100)
    email = models.EmailField()
    phone = models.CharField(max_length=15)
    password = models.CharField(max_length=255)
    is_admin = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.fullname} ({'Admin' if self.is_admin else 'Customer'})"


class Vehicle(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    vehicle_number = models.CharField(max_length=20)
    brand = models.CharField(max_length=100)
    model = models.CharField(max_length=100)
    year = models.IntegerField()
    fuel_type = models.CharField(max_length=20)
    color = models.CharField(max_length=50)

    def __str__(self):
        return f"{self.brand} {self.model} ({self.vehicle_number})"

    @property
    def category(self):
        name = f"{self.brand} {self.model}".lower()
        if any(k in name for k in ['bullet', 'bike', 'pulsar', 'activa', 'royalenfield', 'ktm', 'ninja', 'splendor', 'jupiter', 'scooter', 'himalayan', 'r15', 'apache', 'duke']):
            return 'Motorcycle'
        elif any(k in name for k in ['creta', 'harrier', 'scorpio', 'thar', 'fortuner', 'safari', 'brezza', 'nexon', 'seltos', 'xuv', 'suv', 'hector', 'compass', 'innova']):
            return 'SUV / Crossover'
        elif any(k in name for k in ['swift', 'i20', 'baleno', 'wagonr', 'altroz', 'polo', 'tiago', 'hatchback', 'kwid', 'grand i10', 'glanza']):
            return 'Hatchback'
        elif any(k in name for k in ['bmw', 'mercedes', 'audi', 'porsche', 'jaguar', 'mustang']):
            return 'Luxury / Performance'
        elif str(self.fuel_type).lower() == 'electric':
            return 'Electric EV'
        else:
            return 'Premium Sedan'

    @property
    def icon_class(self):
        cat = self.category
        if cat == 'Motorcycle':
            return 'fa-motorcycle'
        elif cat == 'SUV / Crossover':
            return 'fa-truck-pickup'
        elif cat == 'Electric EV':
            return 'fa-bolt'
        elif cat == 'Luxury / Performance':
            return 'fa-tachometer-alt'
        else:
            return 'fa-car-side'

    @property
    def fuel_badge_color(self):
        f = str(self.fuel_type).lower()
        if 'petrol' in f:
            return 'badge-petrol'
        elif 'diesel' in f:
            return 'badge-diesel'
        elif 'electric' in f:
            return 'badge-ev'
        elif 'cng' in f:
            return 'badge-cng'
        return 'badge-petrol'


class ServiceBooking(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    vehicle = models.ForeignKey(Vehicle, on_delete=models.CASCADE)
    service_type = models.CharField(max_length=100)
    service_date = models.DateField()
    service_time = models.TimeField()
    description = models.TextField()
    status = models.CharField(max_length=50, default="Pending")

    def __str__(self):
        return f"{self.vehicle} - {self.service_type}"

    @property
    def is_cancelled(self):
        return self.status.strip().lower() == "cancelled"

    @property
    def stage_number(self):
        s = self.status.strip().lower()
        if s == "cancelled":
            return -1
        elif s == "pending":
            return 1
        elif s in ["confirmed", "vehicle received"]:
            return 2
        elif s in ["in progress", "progress"]:
            return 3
        elif s in ["quality check", "testing"]:
            return 4
        elif s == "completed":
            return 5
        return 1

    @property
    def stage_percent(self):
        st = self.stage_number
        if st == -1:
            return 0
        elif st == 1:
            return 10
        elif st == 2:
            return 32
        elif st == 3:
            return 58
        elif st == 4:
            return 82
        elif st == 5:
            return 100
        return 10

    @property
    def stage_title(self):
        st = self.stage_number
        if st == -1:
            return "Booking Cancelled"
        elif st == 1:
            return "Booking Confirmed"
        elif st == 2:
            return "Vehicle Received & Inspection"
        elif st == 3:
            return "Servicing & Mechanical Work"
        elif st == 4:
            return "Quality Check & Detailing"
        elif st == 5:
            return "Service Completed & Ready"
        return "Booking Confirmed"

    @property
    def stage_description(self):
        st = self.stage_number
        if st == -1:
            return "This service appointment has been cancelled."
        elif st == 1:
            return "Your appointment has been registered. Please bring your vehicle to the workshop at the scheduled time."
        elif st == 2:
            return "Your vehicle has arrived at AutoFixPro. Our certified mechanics are performing preliminary diagnostics."
        elif st == 3:
            return f"Mechanical servicing ({self.service_type}) and genuine parts replacement are currently underway."
        elif st == 4:
            return "Technical repairs are done. Vehicle is undergoing final safety check, system scan, and complementary wash."
        elif st == 5:
            return "All mechanical work and quality checks are complete! Your vehicle is ready for pickup."
        return ""


class Payment(models.Model):
    booking = models.OneToOneField(ServiceBooking, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_method = models.CharField(max_length=20, default="UPI")
    razorpay_order_id = models.CharField(max_length=100, blank=True, null=True)
    razorpay_payment_id = models.CharField(max_length=100, blank=True, null=True)
    razorpay_signature = models.CharField(max_length=255, blank=True, null=True)
    payment_status = models.CharField(max_length=30, default="Created")
    payment_date = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Payment - Booking #{self.booking.id}"


class Inventory(models.Model):
    name = models.CharField(max_length=100)
    category = models.CharField(max_length=100)
    quantity = models.IntegerField()
    price = models.DecimalField(max_digits=10, decimal_places=2)
    image = models.ImageField(upload_to='inventory/', blank=True, null=True)
    image_url = models.CharField(max_length=500, blank=True, null=True)

    def __str__(self):
        return f"{self.name} ({self.category})"

    @property
    def display_image(self):
        if self.image:
            try:
                return self.image.url
            except Exception:
                pass
        if self.image_url and self.image_url.strip():
            return self.image_url.strip()

        name_lower = str(self.name).lower()
        cat_lower = str(self.category).lower()
        combined = f"{name_lower} {cat_lower}"

        if "battery" in combined:
            return "/static/images/parts/battery.jpg"
        elif any(k in combined for k in ["spark", "plug", "ignition"]):
            return "/static/images/parts/spark_plugs.jpg"
        elif any(k in combined for k in ["brake pad", "pad"]):
            return "/static/images/parts/brake_pads.jpg"
        elif any(k in combined for k in ["rotor", "disc"]):
            return "/static/images/parts/disc_rotor.jpg"
        elif "air filter" in combined or "oil filter" in combined:
            return "/static/images/parts/air_filter.jpg"
        elif "cabin" in combined:
            return "/static/images/parts/cabin_filter.jpg"
        elif any(k in combined for k in ["engine oil", "synthetic"]):
            return "/static/images/parts/engine_oil.jpg"
        elif "coolant" in combined:
            return "/static/images/parts/coolant.jpg"
        elif any(k in combined for k in ["wiper", "blade"]):
            return "/static/images/parts/wiper_blades.jpg"
        elif any(k in combined for k in ["timing belt", "belt"]):
            return "/static/images/parts/timing_belt.jpg"
        elif any(k in combined for k in ["tire", "wheel"]):
            return "/static/images/parts/tire.jpg"
        elif any(k in combined for k in ["fluid", "oil"]):
            return "/static/images/parts/brake_fluid.jpg"

        return "/static/images/service_periodic.jpg"

    @property
    def stock_status(self):
        if self.quantity <= 0:
            return "Out of Stock"
        elif self.quantity <= 10:
            return "Low Stock"
        return "In Stock"

    @property
    def status_badge_class(self):
        if self.quantity <= 0:
            return "status-cancelled"
        elif self.quantity <= 10:
            return "status-pending"
        return "status-completed"

    @property
    def category_icon(self):
        cat = str(self.category).lower()
        if any(k in cat for k in ["fluid", "oil", "coolant", "brake fluid"]):
            return "fa-oil-can"
        elif any(k in cat for k in ["brake", "pad", "rotor"]):
            return "fa-compact-disc"
        elif any(k in cat for k in ["filter", "air", "cabin"]):
            return "fa-filter"
        elif any(k in cat for k in ["electrical", "battery", "wire"]):
            return "fa-car-battery"
        elif any(k in cat for k in ["ignition", "plug", "spark"]):
            return "fa-bolt"
        elif any(k in cat for k in ["engine", "belt", "motor"]):
            return "fa-cogs"
        elif any(k in cat for k in ["tire", "wheel"]):
            return "fa-circle-notch"
        elif any(k in cat for k in ["accessories", "wiper", "blade"]):
            return "fa-wrench"
        return "fa-box-open"

    @property
    def total_value(self):
        return self.quantity * self.price


class EmailOTP(models.Model):
    PURPOSE_CHOICES = (
        ('register', 'Registration'),
        ('forgot_password', 'Forgot Password'),
        ('login_otp', 'Login with OTP'),
    )

    email = models.EmailField()
    otp = models.CharField(max_length=6)
    purpose = models.CharField(max_length=30, choices=PURPOSE_CHOICES, default='register')
    created_at = models.DateTimeField(auto_now_add=True)
    is_used = models.BooleanField(default=False)
    attempts = models.PositiveSmallIntegerField(default=0)

    def is_valid(self, expiry_minutes=5):
        from django.utils import timezone
        if self.is_used:
            return False
        now = timezone.now()
        age = (now - self.created_at).total_seconds()
        return age <= (expiry_minutes * 60)

    def __str__(self):
        return f"OTP for {self.email} ({self.purpose}) - {self.otp}"


class ContactMessage(models.Model):
    name = models.CharField(max_length=150)
    email = models.EmailField()
    phone = models.CharField(max_length=20, blank=True, null=True)
    subject = models.CharField(max_length=200)
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    is_resolved = models.BooleanField(default=False)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Message from {self.name} - {self.subject[:30]}"


class ServiceReview(models.Model):
    booking = models.OneToOneField(ServiceBooking, on_delete=models.CASCADE, related_name="review")
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    rating = models.IntegerField(default=5)
    comment = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.rating}★ Review by {self.user.fullname} (Booking #{self.booking.id})"

