# 🚗 AutoFixPro — Next-Gen Vehicle Care & Certified Garage Platform

![AutoFixPro Banner](static/images/car.jpg)

**AutoFixPro** is a full-featured, modern automotive service booking and workshop management web application built with **Django 6.0**, **Python**, **Vanilla CSS**, and **ReportLab**. It enables vehicle owners to manage their digital garage, book certified repair services in seconds, track stage-by-stage repairs live, pay online via Razorpay, generate GST-compliant PDF Tax Invoices, and submit 5-star customer ratings.

---

## ✨ Key Features

### 👤 1. Customer Experience
- **Smart Authentication & OTP:** Register with 6-digit Email OTP verification, standard password login, and passwordless One-Click Email OTP login.
- **Password Recovery:** Forgot Password flow with instant 6-digit security OTP.
- **Digital Garage (My Vehicles):** Automated vehicle category classification (SUV, Sedan, EV, Motorcycle, Hatchback, Luxury) with 3D badges and color-coded fuel pills.
- **Service Booking in 60s:** Quick booking with date picker, time slot selector, and 5 distinct service packages.
- **Live Mechanical Stage Tracking:** Real-time stage progress tracker (`Booking Received` ➔ `Inspection` ➔ `In Progress` ➔ `Quality Check` ➔ `Completed`).
- **Payments:** Razorpay UPI/Card/NetBanking online payments + Cash on Delivery (COD) mode.
- **Branded Tax Invoice Generator:** Automated, GSTIN-compliant PDF Tax Invoices generated via ReportLab (protected strictly for paid bookings).
- **5-Star Rating & Reviews:** Customer feedback submission for completed services with dynamic testimonials displayed on the home page.
- **Contact & Support:** Public inquiry message system with customer notifications.

### 🛡️ 2. Admin Control Center
- **Role-Based Security:** Custom `@admin_required` security decorator ensuring strict RBAC access control.
- **Analytics Dashboard:** Live revenue tracking, booking statuses, user stats, and inventory health metrics.
- **Management Portals:** Manage Users, Manage Vehicles, Manage Bookings (with live status transitions), Payment Transaction Logs, and Spare Parts Inventory.

---

## 🛠️ Technology Stack

- **Backend:** Python 3.12, Django 6.0
- **Database:** SQLite (development / default)
- **Styling:** Vanilla Modern CSS with Glassmorphism, CSS Grid, Flexbox, and Micro-animations
- **PDF Engine:** ReportLab (Vector Graphics & Typography)
- **Payment Gateway:** Razorpay API (HMAC SHA-256 signature verification)
- **Email Dispatch:** Real Gmail SMTP with HTML email templates & OTP expiration handling
- **Configuration:** Python-Dotenv (`.env` file management)

---

## 🚀 Quick Setup & Installation

### 1. Clone the repository
```bash
git clone https://github.com/YOUR_USERNAME/AutoFixPro.git
cd AutoFixPro
```

### 2. Create and activate a Virtual Environment
```bash
# Windows
python -m venv venv
venv\Scripts\activate

# macOS / Linux
python3 -m venv venv
source venv/bin/activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Configure Environment Variables (`.env`)
Create a `.env` file in the root directory (you can copy `.env.example`):
```bash
cp .env.example .env
```

Fill in your configuration details in `.env`:
```env
SECRET_KEY=your-secure-django-secret-key
DEBUG=True
ALLOWED_HOSTS=*

# Razorpay Credentials
RAZORPAY_KEY_ID=your_razorpay_key_id
RAZORPAY_KEY_SECRET=your_razorpay_key_secret

# Email SMTP Settings (Gmail)
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=your_email@gmail.com
EMAIL_HOST_PASSWORD=your_16_digit_app_password
DEFAULT_FROM_EMAIL=AutoFixPro <your_email@gmail.com>
EMAIL_OTP_EXPIRY_MINUTES=5
```

### 5. Apply Database Migrations
```bash
python manage.py migrate
```

### 6. Run Automated Test Suite
```bash
python manage.py test
```

### 7. Launch Development Server
```bash
# Default port 8000:
python manage.py runserver

# Or custom port 8080 (to run alongside other projects):
python manage.py runserver 8080
```
Visit `http://127.0.0.1:8080` in your web browser.

---

## 🔒 Security & Privacy Notice
- Never commit your `.env` file or SQLite database to GitHub.
- Keep `DEBUG=False` in production deployments.
- AutoFixPro uses role-based access control to protect administrative endpoints.

---

## 📄 License
This project is licensed under the MIT License - see the LICENSE file for details.
