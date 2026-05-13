import unittest
from unittest.mock import patch

import sms_pb2
import sms_server


class GetNumberTests(unittest.TestCase):
    def setUp(self):
        sms_server._activations.clear()
        sms_server._get_number_inflight = False

    def tearDown(self):
        sms_server._activations.clear()
        sms_server._get_number_inflight = False

    def test_get_number_rejects_when_active_activation_exists(self):
        sms_server._activations["old-id"] = {
            "phone": "81230000000",
            "raw_phone": "6281230000000",
            "country": 6,
            "created_at": sms_server.time.time(),
        }

        resp = sms_server.SMSServicer().GetNumber(sms_pb2.GetNumberRequest(), None)

        self.assertFalse(resp.success)
        self.assertEqual(resp.error_message, "ACTIVE_ACTIVATION_EXISTS")
        self.assertEqual(resp.activation_id, "old-id")

    def test_force_new_number_keeps_existing_activation_and_gets_new_one(self):
        sms_server._activations["old-id"] = {
            "phone": "81230000000",
            "raw_phone": "6281230000000",
            "country": 6,
            "created_at": sms_server.time.time(),
        }

        with patch.object(sms_server, "_call", return_value="ACCESS_NUMBER:new-id:6281299999999"):
            resp = sms_server.SMSServicer().GetNumber(
                sms_pb2.GetNumberRequest(force_new_number=True),
                None,
            )

        self.assertTrue(resp.success)
        self.assertEqual(resp.activation_id, "new-id")
        self.assertEqual(resp.phone, "81299999999")
        self.assertIn("old-id", sms_server._activations)
        self.assertIn("new-id", sms_server._activations)


if __name__ == "__main__":
    unittest.main()
