from django.db import models


class User(models.Model):
    fullname = models.CharField(max_length=100)
    email = models.EmailField()
    phone = models.CharField(max_length=15)
    password = models.CharField(max_length=100)
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

    def __str__(self):
        return self.name


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

