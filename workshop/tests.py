from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.hashers import make_password, check_password
from workshop.models import User, Vehicle, ServiceBooking, Payment, Inventory, ContactMessage, ServiceReview

class AutoFixProTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create(
            fullname="Test User",
            email="testuser@example.com",
            phone="9876543210",
            password=make_password("testpassword")
        )
        self.admin_user = User.objects.create(
            fullname="Admin User",
            email="admin@autofixpro.com",
            phone="9998887776",
            password=make_password("adminpassword"),
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

    def test_admin_authorization_denied_for_regular_user(self):
        # Regular customer session
        session = self.client.session
        session['user_id'] = self.user.id
        session['name'] = self.user.fullname
        session['email'] = self.user.email
        session.save()

        response = self.client.get(reverse('admin_dashboard'))
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('login'))

    def test_post_only_destructive_actions(self):
        session = self.client.session
        session['user_id'] = self.user.id
        session['name'] = self.user.fullname
        session['email'] = self.user.email
        session['phone'] = self.user.phone
        session.save()

        # 1. delete_vehicle GET should return 405 Method Not Allowed
        get_del_veh = self.client.get(reverse('delete_vehicle', args=[self.vehicle.id]))
        self.assertEqual(get_del_veh.status_code, 405)

        # 2. cancel_booking GET should return 405 Method Not Allowed
        get_cancel = self.client.get(reverse('cancel_booking', args=[self.booking.id]))
        self.assertEqual(get_cancel.status_code, 405)

        # 3. cancel_booking POST should succeed
        post_cancel = self.client.post(reverse('cancel_booking', args=[self.booking.id]))
        self.assertEqual(post_cancel.status_code, 302)
        self.assertFalse(ServiceBooking.objects.filter(id=self.booking.id).exists())

        # 4. delete_vehicle POST should succeed
        post_del_veh = self.client.post(reverse('delete_vehicle', args=[self.vehicle.id]))
        self.assertEqual(post_del_veh.status_code, 302)
        self.assertFalse(Vehicle.objects.filter(id=self.vehicle.id).exists())

    def test_payment_cash_success_flow(self):
        session = self.client.session
        session['user_id'] = self.user.id
        session['name'] = self.user.fullname
        session['email'] = self.user.email
        session['phone'] = self.user.phone
        session.save()

        # Perform cash payment post
        response = self.client.post(
            reverse('cash_payment', args=[self.booking.id]),
            {
                'payment_method': 'CASH',
            }
        )
        self.assertEqual(response.status_code, 302)

        # Check Payment object created in DB with Pending status (pay at workshop)
        payment = Payment.objects.get(booking=self.booking)
        self.assertEqual(payment.payment_status, 'Pending')
        self.assertEqual(payment.payment_method, 'CASH')
        self.assertEqual(payment.amount, 1499.00)

    def test_payment_online_success_flow(self):
        from unittest.mock import patch

        session = self.client.session
        session['user_id'] = self.user.id
        session['name'] = self.user.fullname
        session['email'] = self.user.email
        session['phone'] = self.user.phone
        session.save()

        # Pre-create payment record matching razorpay order
        Payment.objects.create(
            booking=self.booking,
            amount=1499.00,
            payment_method='RAZORPAY',
            razorpay_order_id='order_test_789',
            payment_status='Pending'
        )

        with patch('razorpay.Client') as mock_razorpay:
            mock_client_instance = mock_razorpay.return_value
            mock_client_instance.utility.verify_payment_signature.return_value = True

            response = self.client.post(
                reverse('payment_success', args=[self.booking.id]),
                {
                    'razorpay_order_id': 'order_test_789',
                    'razorpay_payment_id': 'pay_test_789',
                    'razorpay_signature': 'valid_signature_123',
                }
            )

            self.assertEqual(response.status_code, 302)
            payment = Payment.objects.get(booking=self.booking)
            self.assertEqual(payment.payment_status, 'Paid')
            self.assertEqual(payment.payment_method, 'RAZORPAY')
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
        self.assertTrue(check_password('brandnewpassword123', self.user.password))

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
        import time
        from workshop.models import EmailOTP

        # 1. Generate OTP
        self.client.post(reverse('login_otp'), {'email': self.user.email})

        # 2. Submit wrong OTP
        wrong_response = self.client.post(reverse('verify_otp', kwargs={'purpose': 'login_otp'}), {
            'otp': '000000'
        })
        self.assertEqual(wrong_response.status_code, 200)
        self.assertContains(wrong_response, 'Invalid verification code')

        # 3. Resend OTP with cooldown simulated
        session = self.client.session
        session['otp_last_sent_login_otp'] = time.time() - 35
        session.save()

        resend_response = self.client.get(reverse('resend_otp', kwargs={'purpose': 'login_otp'}))
        self.assertEqual(resend_response.status_code, 302)

        # 4. Ensure new active OTP exists
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
        self.assertRedirects(response, reverse('login'))

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

    def test_registration_phone_length_validation(self):
        # 1. More than 10 digits -> Rejected
        response_too_long = self.client.post(reverse('register'), {
            'fullname': 'Test Long Phone',
            'email': 'longphone@example.com',
            'phone': '9876543210999',
            'password': 'password123',
            'confirm_password': 'password123',
        })
        self.assertEqual(response_too_long.status_code, 200)
        self.assertContains(response_too_long, 'Contact number must be exactly 10 digits.')

        # 2. Less than 10 digits -> Rejected
        response_too_short = self.client.post(reverse('register'), {
            'fullname': 'Test Short Phone',
            'email': 'shortphone@example.com',
            'phone': '98765',
            'password': 'password123',
            'confirm_password': 'password123',
        })
        self.assertEqual(response_too_short.status_code, 200)
        self.assertContains(response_too_short, 'Contact number must be exactly 10 digits.')

        # 3. Valid exactly 10 digits -> Success & redirect to verify_otp
        response_valid = self.client.post(reverse('register'), {
            'fullname': 'Test Valid Phone',
            'email': 'validphone@example.com',
            'phone': '9876543210',
            'password': 'password123',
            'confirm_password': 'password123',
        })
        self.assertEqual(response_valid.status_code, 302)
        self.assertRedirects(response_valid, reverse('verify_otp', kwargs={'purpose': 'register'}))

    def test_login_security_credentials(self):
        # 1. Correct email + correct password -> Login OK
        res_ok = self.client.post(reverse('login'), {
            'email': 'testuser@example.com',
            'password': 'testpassword'
        })
        self.assertEqual(res_ok.status_code, 302)
        self.assertRedirects(res_ok, reverse('dashboard'))

        # 2. Correct email + wrong password -> Rejected
        res_bad_pass = self.client.post(reverse('login'), {
            'email': 'testuser@example.com',
            'password': 'wrongpassword'
        })
        self.assertEqual(res_bad_pass.status_code, 200)
        self.assertContains(res_bad_pass, 'Invalid email or password')

        # 3. Wrong email -> Rejected
        res_bad_email = self.client.post(reverse('login'), {
            'email': 'nonexistent@example.com',
            'password': 'somepassword'
        })
        self.assertEqual(res_bad_email.status_code, 200)
        self.assertContains(res_bad_email, 'Invalid email or password')

    def test_cross_user_booking_authorization_isolation(self):
        # Create User B and User B's booking
        user_b = User.objects.create(
            fullname="User B",
            email="userb@example.com",
            phone="9112233445",
            password=make_password("passwordb")
        )
        veh_b = Vehicle.objects.create(
            user=user_b,
            vehicle_number="GJ01XY9999",
            brand="Tata",
            model="Harrier",
            year=2024,
            fuel_type="Diesel",
            color="Black"
        )
        booking_b = ServiceBooking.objects.create(
            user=user_b,
            vehicle=veh_b,
            service_type="Oil Change",
            service_date="2026-09-05",
            service_time="11:00:00",
            status="Pending"
        )

        # Log in as User A
        session = self.client.session
        session['user_id'] = self.user.id
        session['name'] = self.user.fullname
        session['email'] = self.user.email
        session.save()

        # User A attempts to access User B's booking URL -> must be 404 (isolated)
        response = self.client.get(reverse('view_booking', args=[booking_b.id]))
        self.assertEqual(response.status_code, 404)

    def test_otp_bruteforce_lockout_after_max_attempts(self):
        from workshop.models import EmailOTP

        # Generate OTP
        self.client.post(reverse('login_otp'), {'email': self.user.email})

        # Submit 4 wrong OTP attempts -> status 200 with remaining attempts warning
        for attempt in range(1, 5):
            res = self.client.post(reverse('verify_otp', kwargs={'purpose': 'login_otp'}), {
                'otp': f'99999{attempt}'
            })
            self.assertEqual(res.status_code, 200)
            self.assertContains(res, 'Invalid verification code')

        # 5th attempt -> status 302 (blocked / lockout)
        res_5 = self.client.post(reverse('verify_otp', kwargs={'purpose': 'login_otp'}), {
            'otp': '999995'
        })
        self.assertEqual(res_5.status_code, 302)

        # Verify OTP is marked as used / locked in DB
        active_otp = EmailOTP.objects.filter(email=self.user.email, purpose='login_otp', is_used=False).first()
        self.assertIsNone(active_otp)

    def test_payment_tampered_signature_rejection(self):
        from unittest.mock import patch
        import razorpay

        session = self.client.session
        session['user_id'] = self.user.id
        session.save()

        Payment.objects.create(
            booking=self.booking,
            amount=1499.00,
            payment_method='RAZORPAY',
            razorpay_order_id='order_tampered_123',
            payment_status='Pending'
        )

        with patch('razorpay.Client') as mock_razorpay:
            mock_client_instance = mock_razorpay.return_value
            mock_client_instance.order.create.return_value = {"id": "order_mock_123"}
            # Simulate Razorpay signature verification failure
            mock_client_instance.utility.verify_payment_signature.side_effect = razorpay.errors.SignatureVerificationError('Invalid signature')

            response = self.client.post(
                reverse('payment_success', args=[self.booking.id]),
                {
                    'razorpay_order_id': 'order_tampered_123',
                    'razorpay_payment_id': 'pay_fake_123',
                    'razorpay_signature': 'invalid_forged_signature',
                }
            )

            # Payment must fail and redirect back to payment page
            self.assertEqual(response.status_code, 302)
            self.assertEqual(response.url, reverse('payment', args=[self.booking.id]))

            # The tampered payment order must be marked as Failed, not Paid
            tampered_payment = Payment.objects.filter(booking=self.booking, razorpay_order_id='order_tampered_123').first()
            self.assertEqual(tampered_payment.payment_status, 'Failed')

    def test_inventory_list_view_admin(self):
        session = self.client.session
        session['user_id'] = self.admin_user.id
        session['name'] = self.admin_user.fullname
        session['email'] = self.admin_user.email
        session.save()

        response = self.client.get(reverse('inventory'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Parts &amp; Fluids Inventory")
        self.assertTrue('total_valuation' in response.context)
        self.assertTrue('total_items' in response.context)
        self.assertGreaterEqual(response.context['total_items'], 1)

    def test_add_inventory_item(self):
        session = self.client.session
        session['user_id'] = self.admin_user.id
        session.save()

        response = self.client.post(reverse('add_inventory'), {
            'name': 'Brembo Ceramic Disc Rotors',
            'category': 'Brakes',
            'quantity': '14',
            'price': '3400.00',
        })
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('inventory'))

        created = Inventory.objects.filter(name='Brembo Ceramic Disc Rotors').first()
        self.assertIsNotNone(created)
        self.assertEqual(created.category, 'Brakes')
        self.assertEqual(created.quantity, 14)
        self.assertEqual(float(created.price), 3400.00)
        self.assertEqual(created.stock_status, 'In Stock')
        self.assertEqual(created.category_icon, 'fa-compact-disc')

    def test_edit_inventory_item(self):
        session = self.client.session
        session['user_id'] = self.admin_user.id
        session.save()

        item = Inventory.objects.create(
            name='Test Wiper Blades',
            category='Accessories',
            quantity=5,
            price=450.00
        )

        response = self.client.post(reverse('edit_inventory', args=[item.id]), {
            'name': 'Test Wiper Blades Updated',
            'category': 'Accessories',
            'quantity': '20',
            'price': '520.00',
        })
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('inventory'))

        item.refresh_from_db()
        self.assertEqual(item.name, 'Test Wiper Blades Updated')
        self.assertEqual(item.quantity, 20)
        self.assertEqual(float(item.price), 520.00)

    def test_delete_inventory_item(self):
        session = self.client.session
        session['user_id'] = self.admin_user.id
        session.save()

        item = Inventory.objects.create(
            name='Temporary Scrap Part',
            category='Engine',
            quantity=1,
            price=100.00
        )

        response = self.client.post(reverse('delete_inventory', args=[item.id]))
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('inventory'))

        self.assertFalse(Inventory.objects.filter(id=item.id).exists())

    def test_inventory_access_denied_for_regular_user(self):
        # Regular customer session
        session = self.client.session
        session['user_id'] = self.user.id
        session.save()

        for url_name in ['inventory', 'add_inventory']:
            response = self.client.get(reverse(url_name))
            self.assertEqual(response.status_code, 302)
            self.assertRedirects(response, reverse('login'))

    def test_manage_messages_view_admin(self):
        session = self.client.session
        session['user_id'] = self.admin_user.id
        session['is_admin'] = True
        session.save()

        msg1 = ContactMessage.objects.create(
            name="Rahul Sharma",
            email="rahul@example.com",
            phone="9876543211",
            subject="Brake squeaking inquiry",
            message="My car brakes are making squeaking noise after rain."
        )

        response = self.client.get(reverse('manage_messages'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Brake squeaking inquiry")
        self.assertContains(response, "Rahul Sharma")

    def test_toggle_message_status(self):
        session = self.client.session
        session['user_id'] = self.admin_user.id
        session['is_admin'] = True
        session.save()

        msg = ContactMessage.objects.create(
            name="Priya Patel",
            email="priya@example.com",
            subject="Engine oil type query",
            message="Which oil is recommended for 2023 Creta Petrol?"
        )
        self.assertFalse(msg.is_resolved)

        response = self.client.post(reverse('toggle_message_status', args=[msg.id]))
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('manage_messages'))

        msg.refresh_from_db()
        self.assertTrue(msg.is_resolved)

    def test_delete_message(self):
        session = self.client.session
        session['user_id'] = self.admin_user.id
        session['is_admin'] = True
        session.save()

        msg = ContactMessage.objects.create(
            name="Spam Bot",
            email="spam@example.com",
            subject="Spam Promotion",
            message="Buy cheap followers"
        )

        response = self.client.post(reverse('delete_message', args=[msg.id]))
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('manage_messages'))
        self.assertFalse(ContactMessage.objects.filter(id=msg.id).exists())

    def test_manage_messages_access_denied_for_regular_user(self):
        session = self.client.session
        session['user_id'] = self.user.id
        session.save()

        response = self.client.get(reverse('manage_messages'))
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('login'))

    def test_manage_reviews_view_admin(self):
        session = self.client.session
        session['user_id'] = self.admin_user.id
        session['is_admin'] = True
        session.save()

        # Create booking and review
        from datetime import date, time
        b = ServiceBooking.objects.create(
            user=self.user,
            vehicle=self.vehicle,
            service_type="Brake Service",
            service_date=date.today(),
            service_time=time(10, 0),
            description="Brake pad change",
            status="Completed"
        )
        rev = ServiceReview.objects.create(
            booking=b,
            user=self.user,
            rating=5,
            comment="Awesome brake service, super responsive!"
        )

        response = self.client.get(reverse('manage_reviews'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Awesome brake service")
        self.assertContains(response, "Test User")
        self.assertContains(response, "Hyundai Creta")

    def test_manage_reviews_filtering(self):
        session = self.client.session
        session['user_id'] = self.admin_user.id
        session['is_admin'] = True
        session.save()

        from datetime import date, time
        b1 = ServiceBooking.objects.create(
            user=self.user,
            vehicle=self.vehicle,
            service_type="Oil Change",
            service_date=date.today(),
            service_time=time(11, 0),
            description="Oil service",
            status="Completed"
        )
        ServiceReview.objects.create(
            booking=b1,
            user=self.user,
            rating=5,
            comment="Terrific synthetic oil!"
        )

        v2 = Vehicle.objects.create(
            user=self.user,
            vehicle_number="GJ01XY9999",
            brand="Tata",
            model="Harrier",
            year=2022,
            fuel_type="Diesel",
            color="Black"
        )
        b2 = ServiceBooking.objects.create(
            user=self.user,
            vehicle=v2,
            service_type="General Service",
            service_date=date.today(),
            service_time=time(12, 0),
            description="General checkup",
            status="Completed"
        )
        ServiceReview.objects.create(
            booking=b2,
            user=self.user,
            rating=1,
            comment="Unsatisfactory detailing."
        )

        # Filter 5 stars
        res5 = self.client.get(reverse('manage_reviews') + '?rating=5')
        self.assertEqual(res5.status_code, 200)
        self.assertContains(res5, "Terrific synthetic oil!")
        self.assertNotContains(res5, "Unsatisfactory detailing.")

        # Filter low rating
        res_low = self.client.get(reverse('manage_reviews') + '?rating=low')
        self.assertEqual(res_low.status_code, 200)
        self.assertContains(res_low, "Unsatisfactory detailing.")
        self.assertNotContains(res_low, "Terrific synthetic oil!")

    def test_delete_review(self):
        session = self.client.session
        session['user_id'] = self.admin_user.id
        session['is_admin'] = True
        session.save()

        from datetime import date, time
        b = ServiceBooking.objects.create(
            user=self.user,
            vehicle=self.vehicle,
            service_type="Tire Change",
            service_date=date.today(),
            service_time=time(14, 0),
            description="New tires",
            status="Completed"
        )
        rev = ServiceReview.objects.create(
            booking=b,
            user=self.user,
            rating=2,
            comment="Spam test comment"
        )

        response = self.client.post(reverse('delete_review', args=[rev.id]))
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('manage_reviews'))
        self.assertFalse(ServiceReview.objects.filter(id=rev.id).exists())

    def test_manage_reviews_access_denied_for_regular_user(self):
        session = self.client.session
        session['user_id'] = self.user.id
        session.save()

        response = self.client.get(reverse('manage_reviews'))
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('login'))

    def test_export_bookings_csv_admin(self):
        session = self.client.session
        session['user_id'] = self.admin_user.id
        session['is_admin'] = True
        session.save()

        from datetime import date, time
        ServiceBooking.objects.create(
            user=self.user,
            vehicle=self.vehicle,
            service_type="Full Vehicle Service",
            service_date=date.today(),
            service_time=time(9, 30),
            description="Complete maintenance",
            status="In Progress"
        )

        response = self.client.get(reverse('export_bookings_csv'))
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/csv", response["Content-Type"])
        self.assertIn("attachment; filename=\"autofixpro_bookings_", response["Content-Disposition"])
        content = response.content.decode("utf-8")
        self.assertIn("Full Vehicle Service", content)
        self.assertIn("GJ01AB1234", content)
        self.assertIn("Hyundai", content)

    def test_export_payments_csv_admin(self):
        session = self.client.session
        session['user_id'] = self.admin_user.id
        session['is_admin'] = True
        session.save()

        from datetime import date, time
        b = ServiceBooking.objects.create(
            user=self.user,
            vehicle=self.vehicle,
            service_type="General Service",
            service_date=date.today(),
            service_time=time(10, 0),
            description="Periodic service",
            status="Completed"
        )
        Payment.objects.create(
            booking=b,
            amount=1499.00,
            payment_method="UPI",
            razorpay_payment_id="pay_test123456",
            payment_status="Paid"
        )

        response = self.client.get(reverse('export_payments_csv'))
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/csv", response["Content-Type"])
        self.assertIn("attachment; filename=\"autofixpro_payments_", response["Content-Disposition"])
        content = response.content.decode("utf-8")
        self.assertIn("1499.00", content)
        self.assertIn("pay_test123456", content)
        self.assertIn("UPI", content)

    def test_export_csv_access_denied_for_regular_user(self):
        session = self.client.session
        session['user_id'] = self.user.id
        session.save()

        res1 = self.client.get(reverse('export_bookings_csv'))
        self.assertEqual(res1.status_code, 302)
        self.assertRedirects(res1, reverse('login'))

        res2 = self.client.get(reverse('export_payments_csv'))
        self.assertEqual(res2.status_code, 302)
        self.assertRedirects(res2, reverse('login'))

    def test_registration_rejects_dummy_disposable_emails(self):
        # Test disposable domains like mailinator, tempmail, dummy.com
        for dummy_email in ['cheater@mailinator.com', 'user@tempmail.com', 'test@dummy.com', 'fake@gmail.com']:
            response = self.client.post(reverse('register'), {
                'fullname': 'Fake User',
                'email': dummy_email,
                'phone': '9876543210',
                'password': 'password123',
                'confirm_password': 'password123',
            })
            self.assertEqual(response.status_code, 200)
            self.assertFalse(User.objects.filter(email=dummy_email).exists())

    def test_registration_rejects_nonexistent_email_domain(self):
        response = self.client.post(reverse('register'), {
            'fullname': 'Nonexistent Domain User',
            'email': 'user@thisdomaindoesnotexistatall99881122.com',
            'phone': '9876543210',
            'password': 'password123',
            'confirm_password': 'password123',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "does not exist on the internet")

    def test_registration_sends_real_otp_email(self):
        from django.core import mail
        mail.outbox = []

        response = self.client.post(reverse('register'), {
            'fullname': 'Real User',
            'email': 'genuineuser@example.com',
            'phone': '9876543210',
            'password': 'password123',
            'confirm_password': 'password123',
        })
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('verify_otp', kwargs={'purpose': 'register'}))

        # Verify that an email was actually generated and sent
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Account Email Verification", mail.outbox[0].subject)
        self.assertEqual(mail.outbox[0].to, ['genuineuser@example.com'])

    def test_service_reminder_active_service(self):
        from workshop.services import get_vehicle_service_reminder
        # self.booking is Pending (active)
        reminder = get_vehicle_service_reminder(self.vehicle)
        self.assertTrue(reminder["has_active_booking"])
        self.assertEqual(reminder["status"], "active_service")
        self.assertEqual(reminder["recommended_service"], "General Service")

    def test_service_reminder_overdue_and_due_soon(self):
        from datetime import date, timedelta
        from workshop.services import get_vehicle_service_reminder

        # Vehicle 2: last completed 120 days ago (90 days interval => overdue by 30 days)
        v_overdue = Vehicle.objects.create(
            user=self.user,
            vehicle_number="GJ01OV9999",
            brand="Honda",
            model="City",
            year=2022,
            fuel_type="Petrol",
            color="Silver"
        )
        past_date = date.today() - timedelta(days=120)
        ServiceBooking.objects.create(
            user=self.user,
            vehicle=v_overdue,
            service_type="Oil Change",
            service_date=past_date,
            service_time="11:00:00",
            description="Completed past oil change",
            status="Completed"
        )
        reminder = get_vehicle_service_reminder(v_overdue)
        self.assertTrue(reminder["is_overdue"])
        self.assertEqual(reminder["status"], "overdue")
        self.assertEqual(reminder["recommended_service"], "Brake Service")
        self.assertIn("Overdue by 30 days", reminder["status_label"])

        # Vehicle 3: last completed 85 days ago (due in 5 days => due_soon)
        v_due_soon = Vehicle.objects.create(
            user=self.user,
            vehicle_number="GJ01DS8888",
            brand="Tata",
            model="Harrier",
            year=2021,
            fuel_type="Diesel",
            color="Black"
        )
        recent_past = date.today() - timedelta(days=85)
        ServiceBooking.objects.create(
            user=self.user,
            vehicle=v_due_soon,
            service_type="General Service",
            service_date=recent_past,
            service_time="14:00:00",
            description="Completed general service",
            status="Completed"
        )
        reminder_ds = get_vehicle_service_reminder(v_due_soon)
        self.assertTrue(reminder_ds["is_due_soon"])
        self.assertEqual(reminder_ds["status"], "due_soon")
        self.assertIn("Due in 5 days", reminder_ds["status_label"])

    def test_service_reminder_healthy_and_new_vehicle(self):
        from datetime import date, timedelta
        from workshop.services import get_vehicle_service_reminder

        # Vehicle with fresh service 10 days ago (healthy)
        v_fresh = Vehicle.objects.create(
            user=self.user,
            vehicle_number="GJ01FR7777",
            brand="Maruti",
            model="Swift",
            year=2024,
            fuel_type="Petrol",
            color="Red"
        )
        fresh_date = date.today() - timedelta(days=10)
        ServiceBooking.objects.create(
            user=self.user,
            vehicle=v_fresh,
            service_type="Full Vehicle Service",
            service_date=fresh_date,
            service_time="09:00:00",
            description="Full service",
            status="Completed"
        )
        rem_fresh = get_vehicle_service_reminder(v_fresh)
        self.assertTrue(rem_fresh["is_healthy"])
        self.assertEqual(rem_fresh["status"], "healthy")

        # Brand new vehicle with no previous service
        v_new = Vehicle.objects.create(
            user=self.user,
            vehicle_number="GJ01NW6666",
            brand="Toyota",
            model="Fortuner",
            year=2024,
            fuel_type="Diesel",
            color="White"
        )
        rem_new = get_vehicle_service_reminder(v_new)
        self.assertEqual(rem_new["recommended_service"], "General Service")
        self.assertIn("Due Today", rem_new["status_label"])

    def test_dashboard_displays_smart_service_reminders(self):
        session = self.client.session
        session['user_id'] = self.user.id
        session['name'] = self.user.fullname
        session['email'] = self.user.email
        session.save()

        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'AI Maintenance Predictor')
        self.assertContains(response, 'Creta')
        self.assertContains(response, 'GJ01AB1234')

    def test_book_service_preselection(self):
        session = self.client.session
        session['user_id'] = self.user.id
        session['name'] = self.user.fullname
        session['email'] = self.user.email
        session.save()

        response = self.client.get(reverse('book_service') + f"?vehicle={self.vehicle.id}&service_type=Brake+Service")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f'value="{self.vehicle.id}" selected')
        self.assertContains(response, 'value="Brake Service" selected')









