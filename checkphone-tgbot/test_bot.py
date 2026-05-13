import unittest
from unittest.mock import patch

from bot import TelegramCheckPhoneBot, format_check_response, format_gopay_balance_response, parse_allowed_chat_ids, parse_check_text


class FakeTelegramBot(TelegramCheckPhoneBot):
    def __init__(self, *args, **kwargs):
        super().__init__("token", *args, **kwargs)
        self.calls = []

    def _telegram(self, method: str, payload: dict, timeout: int = 30, attempts: int = 3) -> dict:
        self.calls.append((method, payload))
        return {"ok": True, "result": True}


class TelegramBotParsingTests(unittest.TestCase):
    def test_parse_plain_phone_uses_default_country_code(self):
        parsed = parse_check_text("6289600000000", "62")

        self.assertEqual(parsed.phone, "6289600000000")
        self.assertEqual(parsed.country_code, "+62")

    def test_parse_gopay_registered_command_with_phone_is_not_accepted(self):
        parsed = parse_check_text("/check-gopay-registered 6281234567890", "62")

        self.assertIsNone(parsed)

    def test_parse_check_command_with_explicit_country_code_is_not_accepted(self):
        parsed = parse_check_text("/check-gopay-registered +62 89600000000", "+1")

        self.assertIsNone(parsed)

    def test_parse_menu_command_with_underscore_is_not_accepted(self):
        parsed = parse_check_text("/check_gopay_registered 6281234567890", "62")

        self.assertIsNone(parsed)

    def test_parse_help_returns_none(self):
        self.assertIsNone(parse_check_text("/help", "+62"))

    def test_parse_allowed_chat_ids_accepts_commas_and_spaces(self):
        self.assertEqual(parse_allowed_chat_ids("1, 2\n3"), {"1", "2", "3"})

    def test_format_registered_response(self):
        text = format_check_response("6289600000000", "+62", {
            "success": True,
            "available": False,
            "status": "registered",
        })

        self.assertIn("+6289600000000", text)
        self.assertIn("已注册", text)

    def test_check_command_prompts_then_next_message_checks_phone(self):
        checked = []

        def fake_checker(phone, country_code):
            checked.append((phone, country_code))
            return {"success": True, "available": False, "status": "registered"}

        bot = FakeTelegramBot(default_country_code="62", checker=fake_checker)
        bot.handle_update({
            "message": {
                "message_id": 1,
                "chat": {"id": 100},
                "from": {"id": 200},
                "text": "/check-gopay-registered",
            },
        })
        bot.handle_update({
            "message": {
                "message_id": 2,
                "chat": {"id": 100},
                "from": {"id": 200},
                "text": "6281234567890",
            },
        })

        self.assertEqual(checked, [("6281234567890", "+62")])
        messages = [payload["text"] for method, payload in bot.calls if method == "sendMessage"]
        self.assertIn("请发送要检测的手机号", messages[0])
        self.assertIn("已注册", messages[-1])

    def test_check_command_with_phone_only_prompts_and_does_not_check(self):
        checked = []
        bot = FakeTelegramBot(
            default_country_code="62",
            checker=lambda phone, country_code: checked.append((phone, country_code)),
        )

        bot.handle_update({
            "message": {
                "message_id": 1,
                "chat": {"id": 100},
                "from": {"id": 200},
                "text": "/check-gopay-registered 6281234567890",
            },
        })

        self.assertEqual(checked, [])
        messages = [payload["text"] for method, payload in bot.calls if method == "sendMessage"]
        self.assertEqual(len(messages), 1)
        self.assertIn("请发送要检测的手机号", messages[0])

    def test_private_login_denied_without_owner(self):
        bot = FakeTelegramBot(default_country_code="62")

        bot.handle_update({
            "message": {
                "message_id": 1,
                "chat": {"id": 100},
                "from": {"id": 200},
                "text": "/login-gopay",
            },
        })

        messages = [payload["text"] for method, payload in bot.calls if method == "sendMessage"]
        self.assertEqual(messages, ["这个功能未授权。"])

    def test_private_login_prompts_and_checks_balance_for_owner(self):
        bot = FakeTelegramBot(default_country_code="62", owner_chat_ids={"100"})

        with patch("bot.gopay_login.start_login", return_value={
            "success": True,
            "ready": True,
            "balance_amount": 2,
            "balance_currency": "IDR",
            "required_balance_rp": 1,
            "has_required_balance": True,
        }) as start_login:
            bot.handle_update({
                "message": {
                    "message_id": 1,
                    "chat": {"id": 100},
                    "from": {"id": 200},
                    "text": "/login-gopay",
                },
            })
            bot.handle_update({
                "message": {
                    "message_id": 2,
                    "chat": {"id": 100},
                    "from": {"id": 200},
                    "text": "6281234567890",
                },
            })
            bot.handle_update({
                "message": {
                    "message_id": 3,
                    "chat": {"id": 100},
                    "from": {"id": 200},
                    "text": "123456",
                },
            })

        start_login.assert_called_once_with("6281234567890", "123456", "+62")
        messages = [payload["text"] for method, payload in bot.calls if method == "sendMessage"]
        self.assertIn("请发送要登录的 GoPay 手机号", messages[0])
        self.assertIn("请发送这个 GoPay 账号的 PIN", messages[1])
        self.assertIn("状态：可用", messages[-1])

    def test_format_gopay_balance_requires_greater_than_threshold(self):
        text = format_gopay_balance_response({
            "success": True,
            "balance_amount": 1,
            "balance_currency": "IDR",
            "required_balance_rp": 1,
            "has_required_balance": False,
        })

        self.assertIn("余额不足", text)
        self.assertIn("> 1 Rp", text)


if __name__ == "__main__":
    unittest.main()
