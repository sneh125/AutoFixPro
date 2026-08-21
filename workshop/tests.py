from django.test import TestCase, Client
from django.urls import reverse
from workshop.models import User, Vehicle, ServiceBooking, Payment

class AutoFixProTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create(
            fullname="Test User",
            email="testuser@example.com",
            phone="9876543210",
            password="testpassword"
        )
        self.admin_user = User.objects.create(
            fullname="Admin User",
            email="admin@autofixpro.com",
            phone="9998887776",
            password="adminpassword",
            is_admin=True
        )
        self.vehicle = Vehicle.objects.create(
            user=self.user,
            vehicle_number="GJ01AB1234",
            brand="Hyundai",
            model="Creta",
            year=2023,
            fuel_type="Petrol",
            color="Polar White"
        )
        self.booking = ServiceBooking.objects.create(
            user=self.user,
            vehicle=self.vehicle,
            service_type="General Service",
            service_date="2026-09-01",
            service_time="10:00:00",
            description="Routine maintenance",
            status="Pending"
        )

    def test_home_page(self):
        response = self.client.get(reverse('home'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'AutoFix')

    def test_login_page(self):
        response = self.client.get(reverse('login'))
        self.assertEqual(response.status_code, 200)

    def test_register_page(self):
        response = self.client.get(reverse('register'))
        self.assertEqual(response.status_code, 200)

    def test_authenticated_customer_portal(self):
        session = self.client.session
        session['user_id'] = self.user.id
        session['name'] = self.user.fullname
        session['email'] = self.user.email
        session['phone'] = self.user.phone
        session.save()

        # Dashboard
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Test User')

        # Vehicles
        response = self.client.get(reverse('my_vehicle'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'GJ01AB1234')

        # Bookings
        response = self.client.get(reverse('my_bookings'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'General Service')

        # View Booking
        response = self.client.get(reverse('view_booking', args=[self.booking.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '₹1499')

        # Payment View
        response = self.client.get(reverse('payment', args=[self.booking.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '1499')

        # Service History
        self.booking.status = "Completed"
        self.booking.save()
        response = self.client.get(reverse('service_history'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Completed')

        # Profile
        response = self.client.get(reverse('profile'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'testuser@example.com')

    def test_admin_portal(self):
        session = self.client.session
        session['user_id'] = self.admin_user.id
        session['name'] = self.admin_user.fullname
        session['email'] = self.admin_user.email
        session.save()

        for url_name in ['admin_dashboard', 'manage_users', 'add_user', 'manage_vehicles', 'manage_bookings', 'manage_payments', 'inventory']:
            response = self.client.get(reverse(url_name))
            self.assertEqual(response.status_code, 200, f"Failed on URL: {url_name}")

        response = self.client.get(reverse('edit_user', args=[self.user.id]))
        self.assertEqual(response.status_code, 200)

    def test_payment_cash_success_flow(self):
        session = self.client.session
        session['user_id'] = self.user.id
        session['name'] = self.user.fullname
        session['email'] = self.user.email
        session['phone'] = self.user.phone
        session.save()

        # Perform cash payment post
        response = self.client.post(
            reverse('payment_success', args=[self.booking.id]),
            {
                'payment_method': 'CASH',
                'razorpay_signature': 'CASH_BYPASS',
                'razorpay_order_id': 'order_dummy_123',
                'razorpay_payment_id': 'CASH_123456',
            }
        )
        self.assertEqual(response.status_code, 302)

        # Check Payment object created in DB
        payment = Payment.objects.get(booking=self.booking)
        self.assertEqual(payment.payment_status, 'Paid')
        self.assertEqual(payment.payment_method, 'CASH')
        self.assertEqual(payment.amount, 1499.00)

        # View booking should now show Paid
        view_resp = self.client.get(reverse('view_booking', args=[self.booking.id]))
        self.assertContains(view_resp, 'Paid Successfully')

    def test_payment_online_success_flow(self):
        from unittest.mock import patch

        # Client without session simulates cross-site bank redirect
        unauthenticated_client = Client()

        with patch('razorpay.Client') as mock_razorpay:
            mock_client_instance = mock_razorpay.return_value
            mock_client_instance.utility.verify_payment_signature.return_value = True

            response = unauthenticated_client.post(
                reverse('payment_success', args=[self.booking.id]),
                {
                    'payment_method': 'NET_BANKING',
                    'razorpay_order_id': 'order_test_789',
                    'razorpay_payment_id': 'pay_test_789',
                    'razorpay_signature': 'valid_signature_123',
                }
            )

            self.assertEqual(response.status_code, 302)
            payment = Payment.objects.get(booking=self.booking)
            self.assertEqual(payment.payment_status, 'Paid')
            self.assertEqual(payment.payment_method, 'NET_BANKING')
            self.assertEqual(payment.razorpay_payment_id, 'pay_test_789')

    def test_registration_otp_flow(self):
        from workshop.models import EmailOTP

        # 1. Post Registration Form
        response = self.client.post(reverse('register'), {
            'fullname': 'New Customer',
            'email': 'newcustomer@example.com',
            'phone': '9123456789',
            'password': 'customerpass123',
            'confirm_password': 'customerpass123',
        })
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('verify_otp', kwargs={'purpose': 'register'}))

        # Check OTP generated in database
        otp_entry = EmailOTP.objects.filter(email='newcustomer@example.com', purpose='register', is_used=False).first()
        self.assertIsNotNone(otp_entry)
        self.assertEqual(len(otp_entry.otp), 6)

        # 2. Enter Valid OTP
        verify_response = self.client.post(reverse('verify_otp', kwargs={'purpose': 'register'}), {
            'otp': otp_entry.otp
        })
        self.assertEqual(verify_response.status_code, 302)
        self.assertRedirects(verify_response, reverse('dashboard'))

        # Check User created and logged into session
        new_user = User.objects.filter(email='newcustomer@example.com').first()
        self.assertIsNotNone(new_user)
        self.assertEqual(new_user.fullname, 'New Customer')
        self.assertEqual(self.client.session['user_id'], new_user.id)

    def test_forgot_password_otp_flow(self):
        from workshop.models import EmailOTP

        # 1. Request Password Reset OTP
        response = self.client.post(reverse('forgot_password'), {
            'email': self.user.email
        })
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('verify_otp', kwargs={'purpose': 'forgot_password'}))

        otp_entry = EmailOTP.objects.filter(email=self.user.email, purpose='forgot_password', is_used=False).first()
        self.assertIsNotNone(otp_entry)

        # 2. Verify OTP
        verify_response = self.client.post(reverse('verify_otp', kwargs={'purpose': 'forgot_password'}), {
            'otp': otp_entry.otp
        })
        self.assertEqual(verify_response.status_code, 302)
        self.assertRedirects(verify_response, reverse('reset_password'))

        # 3. Set New Password
        reset_response = self.client.post(reverse('reset_password'), {
            'new_password': 'brandnewpassword123',
            'confirm_password': 'brandnewpassword123'
        })
        self.assertEqual(reset_response.status_code, 302)
        self.assertRedirects(reset_response, reverse('login'))

        # Check updated password
        self.user.refresh_from_db()
        self.assertEqual(self.user.password, 'brandnewpassword123')

    def test_login_otp_flow(self):
        from workshop.models import EmailOTP

        # 1. Request Login OTP
        response = self.client.post(reverse('login_otp'), {
            'email': self.user.email
        })
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('verify_otp', kwargs={'purpose': 'login_otp'}))

        otp_entry = EmailOTP.objects.filter(email=self.user.email, purpose='login_otp', is_used=False).first()
        self.assertIsNotNone(otp_entry)

        # 2. Verify Login OTP
        verify_response = self.client.post(reverse('verify_otp', kwargs={'purpose': 'login_otp'}), {
            'otp': otp_entry.otp
        })
        self.assertEqual(verify_response.status_code, 302)
        self.assertRedirects(verify_response, reverse('dashboard'))
        self.assertEqual(self.client.session['user_id'], self.user.id)

    def test_invalid_otp_and_resend(self):
        from workshop.models import EmailOTP

        # Generate OTP
        self.client.post(reverse('login_otp'), {'email': self.user.email})

        # Submit wrong OTP
        wrong_response = self.client.post(reverse('verify_otp', kwargs={'purpose': 'login_otp'}), {
            'otp': '000000'
        })
        self.assertEqual(wrong_response.status_code, 200)
        self.assertContains(wrong_response, 'Invalid verification code')

        # Resend OTP
        resend_response = self.client.get(reverse('resend_otp', kwargs={'purpose': 'login_otp'}))
        self.assertEqual(resend_response.status_code, 302)

        # Ensure new active OTP exists
        new_otp = EmailOTP.objects.filter(email=self.user.email, purpose='login_otp', is_used=False).first()
        self.assertIsNotNone(new_otp)

    def test_contact_page_get(self):
        response = self.client.get(reverse('contact'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Get in Touch with AutoFixPro Experts')
        self.assertContains(response, 'Send Us a Message')

    def test_contact_page_post_success(self):
        from workshop.models import ContactMessage
        response = self.client.post(reverse('contact'), {
            'name': 'Test Sender',
            'email': 'sender@example.com',
            'phone': '9876543210',
            'subject': 'General Service Inquiry',
            'message': 'Hello, I want to inquire about periodic car service package.'
        })
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('contact'))

        # Verify saved in DB
        msg = ContactMessage.objects.filter(email='sender@example.com').first()
        self.assertIsNotNone(msg)
        self.assertEqual(msg.name, 'Test Sender')
        self.assertEqual(msg.subject, 'General Service Inquiry')
        self.assertEqual(msg.phone, '9876543210')

    def test_download_invoice_pdf(self):
        # Create paid payment record
        Payment.objects.create(
            booking=self.booking,
            amount=1499.00,
            payment_status='Paid',
            payment_method='Razorpay Online'
        )

        # Authenticate user session
        session = self.client.session
        session['user_id'] = self.user.id
        session.save()

        # Download invoice
        response = self.client.get(reverse('download_invoice', kwargs={'booking_id': self.booking.id}))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertTrue(response['Content-Disposition'].startswith('attachment;'))
        self.assertTrue(len(response.content) > 1000)

    def test_preview_invoice_pdf(self):
        # Create paid payment record
        Payment.objects.create(
            booking=self.booking,
            amount=1499.00,
            payment_status='Paid',
            payment_method='Razorpay Online'
        )

        session = self.client.session
        session['user_id'] = self.user.id
        session.save()

        response = self.client.get(reverse('preview_invoice', kwargs={'booking_id': self.booking.id}))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertTrue(response['Content-Disposition'].startswith('inline;'))
        self.assertTrue(len(response.content) > 1000)

    def test_download_invoice_unpaid_fails(self):
        # Authenticate session
        session = self.client.session
        session['user_id'] = self.user.id
        session.save()

        # Try to download invoice without paying
        response = self.client.get(reverse('download_invoice', kwargs={'booking_id': self.booking.id}))
        # Must redirect back to view_booking with error
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('view_booking', kwargs={'booking_id': self.booking.id}))



    def test_submit_review(self):
        from workshop.models import ServiceReview

        # Mark booking completed
        self.booking.status = 'Completed'
        self.booking.save()

        session = self.client.session
        session['user_id'] = self.user.id
        session.save()

        # Submit review
        response = self.client.post(reverse('submit_review', kwargs={'booking_id': self.booking.id}), {
            'rating': '5',
            'comment': 'Exceptional mechanical expertise! Fixed my car AC perfectly.'
        })
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('view_booking', kwargs={'booking_id': self.booking.id}))

        # Verify review in DB
        rev = ServiceReview.objects.filter(booking=self.booking).first()
        self.assertIsNotNone(rev)
        self.assertEqual(rev.rating, 5)
        self.assertEqual(rev.comment, 'Exceptional mechanical expertise! Fixed my car AC perfectly.')

    def test_admin_access_denied_for_regular_customer(self):
        # Regular customer login (is_admin=False)
        self.user.is_admin = False
        self.user.save()

        session = self.client.session
        session['user_id'] = self.user.id
        session['is_admin'] = False
        session.save()

        # Try to access admin dashboard
        response = self.client.get(reverse('admin_dashboard'))
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('dashboard'))

    def test_admin_access_granted_for_admin_user(self):
        # Create admin user
        admin_user = User.objects.create(
            fullname='Workshop Admin',
            email='admin@autofixpro.com',
            phone='9998887776',
            password='adminsecretpassword',
            is_admin=True
        )

        session = self.client.session
        session['user_id'] = admin_user.id
        session['is_admin'] = True
        session.save()

        # Access admin dashboard
        response = self.client.get(reverse('admin_dashboard'))
        self.assertEqual(response.status_code, 200)

        # Access admin bookings
        response = self.client.get(reverse('manage_bookings'))
        self.assertEqual(response.status_code, 200)






