import unittest
from unittest.mock import patch

import payment_pb2
import payment_server
from payment_server import FlowStore, PaymentService


TEST_CYCLE_PHONE = "test-cycle-phone"
TEST_PIN = "000000"


class FakeCharger:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


class FlowStoreTests(unittest.TestCase):
    def test_flow_store_keeps_flow_until_pop(self):
        store = FlowStore()
        charger = FakeCharger()

        flow_id = store.put(charger, {"snap_token": "snap"})
        flow = store.pop(flow_id)

        self.assertIsNotNone(flow)
        self.assertIs(flow.charger, charger)
        self.assertEqual(flow.state["snap_token"], "snap")
        self.assertIsNone(store.pop(flow_id))

    def test_close_releases_unpopped_flows(self):
        store = FlowStore()
        charger = FakeCharger()

        store.put(charger, {"snap_token": "snap"})
        store.close()

        self.assertTrue(charger.closed)


class PaymentServiceTests(unittest.TestCase):
    def test_cycle_token_does_not_replace_chatgpt_access_token(self):
        captured = {}

        class FakeChatGPTSession:
            headers = {}

            def close(self):
                pass

        class FakeGoPayCharger:
            def __init__(self, chatgpt_session, gopay_cfg, **kwargs):
                captured["gopay_cfg"] = dict(gopay_cfg)
                captured["charger_kwargs"] = dict(kwargs)

            def start_until_otp(self, stripe_pk="", billing=None):
                return {"snap_token": "snap", "issued_after_unix": 123}

        def fake_build_chatgpt_session(auth_cfg, proxy=None):
            captured["auth_cfg"] = dict(auth_cfg)
            captured["build_proxy"] = proxy
            return FakeChatGPTSession()

        svc = PaymentService({"fresh_checkout": {"auth": {}}, "gopay": {"country_code": "62", "phone_number": "", "pin": TEST_PIN}})

        with patch.object(svc, "_ready_cycle_access_token", return_value=("cycle-gopay-token", TEST_CYCLE_PHONE)), \
                patch.object(payment_server, "_build_chatgpt_session", fake_build_chatgpt_session), \
                patch.object(payment_server, "resolve_checkout_proxy", return_value="socks5://checkout"), \
                patch.object(payment_server, "resolve_payment_proxy", return_value="socks5://payment"), \
                patch.object(payment_server, "GoPayCharger", FakeGoPayCharger):
            resp = svc.StartGoPay(
                payment_pb2.StartGoPayRequest(access_token="chatgpt-access-token", use_cycle_token=True),
                None,
            )

        self.assertTrue(resp.success)
        self.assertEqual(captured["auth_cfg"]["access_token"], "chatgpt-access-token")
        self.assertEqual(captured["gopay_cfg"]["phone_number"], TEST_CYCLE_PHONE)
        self.assertEqual(captured["build_proxy"], "socks5://checkout")
        self.assertEqual(captured["charger_kwargs"]["checkout_proxy"], "socks5://checkout")
        self.assertEqual(captured["charger_kwargs"]["payment_proxy"], "socks5://payment")


if __name__ == "__main__":
    unittest.main()
