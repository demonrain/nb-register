import unittest

from browser_reg.flow import _select_checkout_amount


class PlusTrialProbeTests(unittest.TestCase):
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
