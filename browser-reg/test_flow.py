import unittest

from browser_reg.cookies import extract_session_token
from browser_reg.flow import _select_checkout_amount


class PlusTrialProbeTests(unittest.TestCase):
    def test_extracts_chunked_session_cookie(self):
        token = extract_session_token([
            {"name": "__Secure-next-auth.session-token.1", "value": "tail", "domain": ".chatgpt.com"},
            {"name": "__Secure-next-auth.session-token.0", "value": "head", "domain": ".chatgpt.com"},
        ])

        self.assertEqual(token, "headtail")

    def test_extracts_authjs_session_cookie(self):
        token = extract_session_token([
            {"name": "__Secure-authjs.session-token", "value": "session", "domain": ".chatgpt.com"},
        ])

        self.assertEqual(token, "session")

    def test_prefers_stripe_total_summary_due(self):
        amount, source = _select_checkout_amount({
            "invoice": {"amount_due": 34900000},
            "total_summary": {"due": 0},
        })

        self.assertEqual(amount, 0)
        self.assertEqual(source, "total_summary.due")

    def test_reads_invoice_amount_due(self):
        amount, source = _select_checkout_amount({
            "currency": "idr",
            "invoice": {"amount_due": 34900000},
        })

        self.assertEqual(amount, 34900000)
        self.assertEqual(source, "invoice.amount_due")


if __name__ == "__main__":
    unittest.main()
