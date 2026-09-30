# 🚗 AutoFixPro

## Project Description
**AutoFixPro** is a modern, professional automotive service booking and workshop management web application built with **Django**. It allows vehicle owners to manage their digital garage, book certified repair services in seconds, track stage-by-stage repairs live, make secure online payments via Razorpay or Cash on Delivery, receive automated GST-compliant PDF Tax Invoices via multi-channel email dispatch, and submit verified 5-star customer ratings.

The platform includes full role-based access control (RBAC) with dedicated portals for **Customers** and a centralized **Workshop Admin Control Center** — providing complete control over service packages, appointments, customer vehicles, inventory spare parts stock, billing reconciliation, and analytical reporting.

---

## Live Demo
🔗 [https://sneh125.pythonanywhere.com/](https://sneh125.pythonanywhere.com/)

---

## Features
- **User Registration & Login** — Session-based authentication, user profile management, password recovery flow, and passwordless instant Email OTP login with PBKDF2 cryptographic hashing.
- **Digital Garage (My Vehicles)** — Vehicle fleet management with automated body-type classification (SUV, Sedan, EV, Motorcycle, Hatchback, Luxury), 3D plate badges, and color-coded fuel pills.
- **Service Search & Availability** — Search and browse certified workshop service packages with real-time conflict-free slot booking, duplicate slot prevention, and past-date rejection.
- **Live Mechanical Stage Tracking** — Visual progress tracker reflecting workshop workflow: `Pending` ➔ `Confirmed` ➔ `In Progress` ➔ `Quality Check` ➔ `Completed`.
- **Enforced State Machine Transitions** — Strict administrative status transition rules preventing invalid status progressions and arbitrary reopening of finalized/cancelled bookings.
- **Interactive Job Card & Inventory Spares** — Administrative job card drawer allowing mechanics to allocate spare parts to active bookings with real-time stock deduction, concurrency-safe row-locking (`select_for_update`), and auto-restocking on cancellation.
- **Razorpay Payments & COD Checkout** — Integrated sandbox and production Razorpay payment checkout with HMAC SHA-256 signature verification, cancelled booking payment protection, and Cash payment marking.
- **Payment & Refund Status Synchronization** — Automatic reconciliation when bookings are cancelled (`Paid` ➔ `Refund Pending`, `Pending` ➔ `Cancelled`) and billing lock to protect invoice accuracy.
- **Automated PDF Tax Invoice & Email** — In-memory dynamic vector PDF Tax Invoices generated via ReportLab with itemized spare parts breakdown, GST calculation, and multi-channel email dispatch (Brevo API, Resend API, Gmail SMTP).
- **Customer Reviews & Ratings** — Verified 1-to-5 star customer ratings and reviews with featured display on homepage and admin moderation.
- **Customer "My Bookings" Dashboard** — Grouped booking cards, categorized into Active Bookings, Completed Services, and Cancelled Bookings, with pagination and CSV export.
- **Admin Management & Analytics** — Comprehensive administrative control panel for customers, service packages, bookings, spare parts inventory, reviews, contact inquiries, and visual financial analytics with monthly revenue charts.

---

## Credentials

### Admin / Superuser Account:
- **Email:** `admin@autofixpro.com`
- **Password:** *(Set via `ADMIN_PASSWORD` in your `.env` file, or auto-generated on first bootstrap via `python manage.py setup_server`)*
- **Admin Dashboard URL:** `http://127.0.0.1:8000/admin-dashboard/`

### Customer Demo Account:
- **Email:** `customer@example.com`
- **Password:** `AutoFixPass#2026`
- **Customer Login URL:** `http://127.0.0.1:8000/login/`

---

## Installation & Setup

### Windows

```bash
# 1. Clone the repository
git clone https://github.com/sneh125/AutoFixPro.git
cd AutoFixPro

# 2. Create and activate virtual environment
python -m venv myenv
myenv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Set up environment variables
copy .env.example .env
# Configure your SECRET_KEY, RAZORPAY, and EMAIL settings in .env

# 5. Run database migrations
python manage.py makemigrations
python manage.py migrate

# 6. Seed initial inventory spare parts (Optional)
python manage.py seed_inventory

# 7. Bootstrap server and create admin account
python manage.py setup_server

# 8. Start the development server
python manage.py runserver
```
Open [http://127.0.0.1:8000](http://127.0.0.1:8000/) in your browser.

---

### macOS / Linux

```bash
# 1. Clone the repository
git clone https://github.com/sneh125/AutoFixPro.git
cd AutoFixPro

# 2. Create and activate virtual environment
python3 -m venv myenv
source myenv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Set up environment variables
cp .env.example .env
# Configure your SECRET_KEY, RAZORPAY, and EMAIL settings in .env

# 5. Run database migrations
python3 manage.py makemigrations
python3 manage.py migrate

# 6. Seed initial inventory spare parts (Optional)
python3 manage.py seed_inventory

# 7. Bootstrap server and create admin account
python3 manage.py setup_server

# 8. Start the development server
python3 manage.py runserver
```
Open [http://127.0.0.1:8000](http://127.0.0.1:8000/) in your browser.

---

## 🛠️ Technology Stack

| Component | Technology / Library | Description |
| :--- | :--- | :--- |
| **Core Framework** | Python 3.10+ / Django 5.x / 6.x | Robust MVT Web Architecture with custom RBAC security |
| **Database** | SQLite3 (PostgreSQL Ready) | Local relational SQL database with transactional integrity |
| **Payment Gateway** | Razorpay Python SDK | Sandbox & Production payment processing with HMAC SHA-256 signature verification |
| **PDF Generation** | ReportLab 4.x / 5.x | Dynamic in-memory GST-compliant PDF Tax Invoices |
| **Email Service** | Multi-Channel Dispatch (Brevo / Resend / Gmail SMTP) | Automated invoice receipt dispatch and secure OTP delivery |
| **Security & Auth** | Python `secrets` / PBKDF2 SHA-256 | Cryptographic OTP hashing, rate limiting, and password strength enforcement |
| **Images & Assets** | Pillow (PIL) | Image upload processing for spare parts and vehicle assets |
| **Frontend Styling** | Custom CSS3, Glassmorphism & Font Awesome 6 | Responsive UI with micro-animations optimized for mobile and desktop |

---

## 🧪 Running Automated Unit Tests
Automated tests are set up inside `workshop/tests.py`. Validate view responses, booking state machine transitions, cancelled payment guards, spare parts locking, OTP security, invoice generation, and test database isolation by running:

```bash
python manage.py test
```

*All **73 automated unit tests** run with 100% success.*

---

## Screenshots
1. **Home-page** — Hero banner, certified service packages, workshop highlights, and verified customer testimonials.
2. **Login-page** — Dual authentication modal with password login, password recovery, and instant email OTP login.
3. **Profile-page** — Customer vehicle fleet management with 3D number plates, body-type badges, and specs.
4. **Booking-page** — Interactive 60-second appointment booking with calendar date picker and conflict-free slot selection.
5. **Tracker-page** — Live stage-by-stage mechanical workflow progress indicator (Pending ➔ In Progress ➔ Completed).
6. **Invoice-page** — Complete job card breakdown with fitted spare parts and in-memory GST Tax Invoice preview.
7. **History-page** — Grouped booking cards categorized into Active, Completed, and Cancelled services with CSV export.
8. **Admin-Dashboard** — Visual financial analytics, monthly revenue charts grounded in cleared payment dates, and KPIs.
9. **Manage-Bookings-page** — Real-time booking status management with enforced state machine transitions and spare parts allocation drawer.
10. **Inventory-page** — Live stock level monitoring, re-stocking controls, parts catalog, and pricing management.

---

## 📄 License
This project is licensed under the MIT License - see the LICENSE file for details.
