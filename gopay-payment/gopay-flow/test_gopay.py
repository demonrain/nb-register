import unittest

from gopay import (
    GoPayCharger,
    GoPayError,
    GoPayOTPRejected,
    _request_with_retries,
    _resolve_expected_amount,
    _stripe_confirm_error_detail,
)


class FakeResponse:
    def __init__(self, status_code, text="", payload=None):
        self.status_code = status_code
        self.text = text
        self._payload = payload or {}

    def json(self):
        return self._payload


class FakeExt:
    def __init__(self, response):
        self.response = response

    def post(self, *args, **kwargs):
        return self.response


class FlakySession:
    def __init__(self):
        self.calls = 0

    def post(self, *args, **kwargs):
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("TLS connect error: transient")
        return FakeResponse(200, payload={"ok": True})


class GoPayValidateOtpTests(unittest.TestCase):
    def charger_for(self, response):
        charger = GoPayCharger.__new__(GoPayCharger)
        charger.ext = FakeExt(response)
        charger.browser_locale = "zh-CN"
        return charger

    def test_validate_otp_400_is_retryable_otp_error(self):
        charger = self.charger_for(FakeResponse(400, '{"success":false,"error":"invalid otp"}'))

        with self.assertRaises(GoPayOTPRejected) as raised:
            charger._gopay_validate_otp("ref", "111111")

        self.assertIn("validate-otp 400", str(raised.exception))
        self.assertIn("invalid otp", str(raised.exception))

    def test_validate_otp_unsuccessful_200_is_retryable_otp_error(self):
        charger = self.charger_for(FakeResponse(200, payload={"success": False, "error": "bad otp"}))

        with self.assertRaises(GoPayOTPRejected):
            charger._gopay_validate_otp("ref", "111111")


class RetryTransportTests(unittest.TestCase):
    def test_retries_retryable_transport_error(self):
        session = FlakySession()

        resp = _request_with_retries(
            session,
            "post",
            "https://api.stripe.com/v1/payment_methods",
            log=lambda _msg: None,
            delay_seconds=0,
        )

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(session.calls, 2)


class StripeExpectedAmountTests(unittest.TestCase):
    def test_uses_zero_amount_from_checkout_session(self):
        amount, source = _resolve_expected_amount(
            {"currency": "idr", "checkout_session": {"amount_total": 0}},
            {},
        )

        self.assertEqual(amount, "0")
        self.assertEqual(source, "checkout_session.amount_total")

    def test_refuses_nonzero_amount_by_default(self):
        with self.assertRaises(GoPayError) as raised:
            _resolve_expected_amount(
                {"currency": "idr", "latest_invoice": {"amount_due": 319000}},
                {},
            )

        self.assertIn("not free-trial 0", str(raised.exception))

    def test_allows_nonzero_amount_when_explicitly_configured(self):
        amount, source = _resolve_expected_amount(
            {"currency": "idr", "latest_invoice": {"amount_due": 319000}},
            {"allow_nonzero_expected_amount": True},
        )

        self.assertEqual(amount, "319000")
        self.assertEqual(source, "latest_invoice.amount_due")

    def test_runtime_expected_amount_override(self):
        amount, source = _resolve_expected_amount(
            {"currency": "idr", "latest_invoice": {"amount_due": 319000}},
            {"expected_amount": "0"},
        )

        self.assertEqual(amount, "0")
        self.assertEqual(source, "runtime.expected_amount")

    def test_checkout_amount_mismatch_error_mentions_sent_amount(self):
        detail = _stripe_confirm_error_detail(
            '{"error":{"code":"checkout_amount_mismatch","message":"amount changed"}}',
            expected_amount="0",
            expected_amount_source="fallback_zero_unknown",
        )

        self.assertIn("sent expected_amount=0", detail)
        self.assertIn("another checkout", detail)


if __name__ == "__main__":
    unittest.main()
