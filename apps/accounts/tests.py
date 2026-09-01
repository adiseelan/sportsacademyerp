from django.test import TestCase, override_settings

from apps.academy.models import Academy
from apps.accounts import otp as otp_service
from apps.accounts.models import EmailOTP, Role, User


class OtpAuthTests(TestCase):
    def setUp(self):
        self.academy = Academy.objects.create(name="Test Academy", slug="test")
        self.user = User.objects.create_user(
            email="parent@example.com", full_name="Test Parent",
            role=Role.PARENT, academy=self.academy,
        )

    @override_settings(OTP_MAX_SENDS=5, OTP_COOLDOWN_SECONDS=900)
    def test_five_sends_then_cooldown(self):
        for i in range(5):
            res = otp_service.request_login_otp("parent@example.com", ip="1.1.1.1")
            self.assertEqual(res.sends_used, i + 1)
        # 6th request must be blocked with a cooldown.
        with self.assertRaises(otp_service.CooldownActive):
            otp_service.request_login_otp("parent@example.com", ip="1.1.1.1")

    def test_otp_is_hashed_not_plaintext(self):
        otp_service.request_login_otp("parent@example.com")
        row = EmailOTP.objects.latest("created_at")
        self.assertEqual(len(row.code_hash), 64)  # sha256 hex
        self.assertNotIn(row.code_hash, "0123456789")

    @override_settings(DEBUG=True)
    def test_correct_code_logs_in_and_clears_throttle(self):
        res = otp_service.request_login_otp("parent@example.com", ip="9.9.9.9")
        user = otp_service.verify_login_otp("parent@example.com", res.dev_code, ip="9.9.9.9")
        self.assertEqual(user.pk, self.user.pk)
        # A second, fresh request should now be allowed (throttle reset).
        res2 = otp_service.request_login_otp("parent@example.com")
        self.assertEqual(res2.sends_used, 1)

    @override_settings(DEBUG=True, OTP_MAX_VERIFY_ATTEMPTS=3)
    def test_wrong_code_burns_after_max_attempts(self):
        otp_service.request_login_otp("parent@example.com")
        for _ in range(3):
            with self.assertRaises(otp_service.InvalidCode):
                otp_service.verify_login_otp("parent@example.com", "000000")
        # Code is now burned -> even a later correct-looking attempt is expired.
        with self.assertRaises(otp_service.CodeExpired):
            otp_service.verify_login_otp("parent@example.com", "123456")

    def test_unknown_email_does_not_leak_but_still_counts(self):
        # No user for this email -> no OTP row created, but no error either.
        res = otp_service.request_login_otp("ghost@example.com")
        self.assertEqual(res.sends_used, 1)
        self.assertFalse(EmailOTP.objects.filter(email="ghost@example.com").exists())


class AuthViewTests(TestCase):
    def setUp(self):
        self.academy = Academy.objects.create(name="A", slug="a")
        self.user = User.objects.create_user(
            email="admin@example.com", full_name="Admin", role=Role.ADMIN, academy=self.academy
        )

    def test_login_page_renders(self):
        resp = self.client.get("/auth/login/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Send code")

    def test_security_headers_present(self):
        resp = self.client.get("/auth/login/")
        self.assertIn("Content-Security-Policy", resp)
        self.assertEqual(resp["X-Frame-Options"], "DENY")
        self.assertEqual(resp["X-Content-Type-Options"], "nosniff")

    def test_protected_page_redirects_anonymous(self):
        resp = self.client.get("/app/")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/auth/login/", resp["Location"])
