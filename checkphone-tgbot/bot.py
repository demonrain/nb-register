import os
import re
import signal
import sys
import time
from dataclasses import dataclass
from typing import Callable, Optional

import requests

import gopay_login
from checkphone import _country_code, _normalize_phone, check_phone_by_login_methods


PHONE_RE = re.compile(r"\+?\d[\d\s().-]{4,}\d")
CHECK_COMMAND = "/check-gopay-registered"
LOGIN_GOPAY_COMMAND = "/login-gopay"
GOPAY_STATUS_COMMAND = "/gopay-status"
CLEAR_GOPAY_LOGIN_COMMAND = "/clear-gopay-login"
COMMANDS = {"/start", "/help", CHECK_COMMAND}
CHECK_COMMANDS = {CHECK_COMMAND}
PRIVATE_COMMANDS = {LOGIN_GOPAY_COMMAND, GOPAY_STATUS_COMMAND, CLEAR_GOPAY_LOGIN_COMMAND}
PENDING_TTL_SECONDS = int(os.environ.get("TELEGRAM_PENDING_SECONDS", "300"))


@dataclass
class CheckRequest:
    phone: str
    country_code: str


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name, "")
    if value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _proxy_map(proxy: str) -> Optional[dict]:
    value = str(proxy or "").strip()
    if not value:
        return None
    if value.startswith("socks5://"):
        value = "socks5h://" + value[len("socks5://"):]
    return {"http": value, "https": value}


def parse_allowed_chat_ids(value: str) -> set[str]:
    return {part.strip() for part in re.split(r"[,\s]+", value or "") if part.strip()}


def _strip_bot_mention(command: str) -> str:
    return command.split("@", 1)[0].lower()


def _redact_token(text: object) -> str:
    value = str(text)
    return re.sub(r"/bot[^/\s]+/", "/bot<redacted>/", value)


def parse_check_text(text: str, default_country_code: str) -> Optional[CheckRequest]:
    raw = str(text or "").strip()
    if not raw:
        return None

    parts = raw.split(maxsplit=1)
    if parts:
        command = _strip_bot_mention(parts[0])
        if command.startswith("/"):
            return None

    tokens = raw.split()
    country_code = _country_code(default_country_code)
    if len(tokens) >= 2 and re.fullmatch(r"\+?\d{1,4}", tokens[0]):
        country_code = _country_code(tokens[0])
        raw = " ".join(tokens[1:])

    match = PHONE_RE.search(raw)
    if not match:
        return None
    phone = re.sub(r"\D", "", match.group())
    if not phone:
        return None
    return CheckRequest(phone=phone, country_code=country_code)


def usage_text(default_country_code: str) -> str:
    cc = _country_code(default_country_code)
    return (
        "检测 GoPay 手机号是否已注册：\n"
        f"1. 发送 {CHECK_COMMAND}\n"
        "2. 按提示发送手机号\n\n"
        "支持格式：628xxxxxxxxxx、8xxxxxxxxxx、+62 8xxxxxxxxxx\n"
        f"当前默认区号：{cc}"
    )


def owner_usage_text(default_country_code: str) -> str:
    return (
        usage_text(default_country_code)
        + "\n\n私有 GoPay 登录：\n"
        f"{LOGIN_GOPAY_COMMAND} - 登录并检查余额是否 > {gopay_login.GOPAY_REQUIRED_BALANCE_RP} Rp\n"
        f"{GOPAY_STATUS_COMMAND} - 重新检查已保存账号余额\n"
        f"{CLEAR_GOPAY_LOGIN_COMMAND} - 清空本地登录状态"
    )


def phone_prompt_text(default_country_code: str) -> str:
    cc = _country_code(default_country_code)
    return (
        "请发送要检测的手机号。\n"
        "支持格式：628xxxxxxxxxx、8xxxxxxxxxx、+62 8xxxxxxxxxx\n"
        f"当前默认区号：{cc}"
    )


def gopay_login_phone_prompt(default_country_code: str) -> str:
    cc = _country_code(default_country_code)
    return (
        "请发送要登录的 GoPay 手机号。\n"
        "支持格式：628xxxxxxxxxx、8xxxxxxxxxx、+62 8xxxxxxxxxx\n"
        f"当前默认区号：{cc}"
    )


def gopay_pin_prompt() -> str:
    return "请发送这个 GoPay 账号的 PIN。"


def gopay_otp_prompt(method: str = "") -> str:
    suffix = f"（{method}）" if method else ""
    return f"已通过 PIN，等待登录 OTP{suffix}。请发送 OTP。"


def format_check_response(phone: str, country_code: str, result: dict) -> str:
    cc = _country_code(country_code)
    normalized = _normalize_phone(phone, cc)
    display_phone = f"{cc}{normalized}"
    status = str(result.get("status") or "error")
    if result.get("success") and result.get("available"):
        return f"{display_phone}\n状态：可用（未注册）"
    if result.get("success") and status == "registered":
        return f"{display_phone}\n状态：已注册"
    if status == "rate_limited":
        return f"{display_phone}\n状态：限流\n错误：{result.get('error') or 'RATE_LIMITED'}"
    return f"{display_phone}\n状态：检测失败\n错误：{result.get('error') or result.get('error_message') or 'unknown error'}"


def format_gopay_balance_response(result: dict) -> str:
    if not result.get("success"):
        return f"GoPay 登录/检查失败：{result.get('error') or 'unknown error'}"
    amount = int(result.get("balance_amount") or 0)
    currency = result.get("balance_currency") or "IDR"
    required = int(result.get("required_balance_rp") or gopay_login.GOPAY_REQUIRED_BALANCE_RP)
    phone = str(result.get("phone") or "").strip()
    prefix = f"手机号：{phone}\n" if phone else ""
    if result.get("has_required_balance"):
        return f"{prefix}余额：{amount} {currency}\n状态：可用，余额 > {required} Rp"
    return f"{prefix}余额：{amount} {currency}\n状态：余额不足，需要 > {required} Rp"


class TelegramCheckPhoneBot:
    def __init__(
        self,
        token: str,
        *,
        api_base: str = "https://api.telegram.org",
        telegram_proxy: str = "",
        default_country_code: str = "+62",
        allowed_chat_ids: Optional[set[str]] = None,
        owner_chat_ids: Optional[set[str]] = None,
        poll_timeout: int = 30,
        poll_limit: int = 20,
        checker: Callable[[str, str], dict] = check_phone_by_login_methods,
    ):
        self.token = token.strip()
        self.api_base = api_base.rstrip("/")
        self.telegram_proxy = telegram_proxy
        self.default_country_code = _country_code(default_country_code)
        self.allowed_chat_ids = allowed_chat_ids or set()
        self.owner_chat_ids = owner_chat_ids or set()
        self.poll_timeout = max(1, poll_timeout)
        self.poll_limit = max(1, min(100, poll_limit))
        self.checker = checker
        self._stopping = False
        self._pending_checks: dict[tuple[int, str], float] = {}
        self._pending_gopay_logins: dict[tuple[int, str], dict] = {}

    def stop(self, *_args) -> None:
        self._stopping = True

    def _api_url(self, method: str) -> str:
        return f"{self.api_base}/bot{self.token}/{method}"

    def _telegram(self, method: str, payload: dict, timeout: int = 30, attempts: int = 3) -> dict:
        last_error = None
        for attempt in range(1, max(1, attempts) + 1):
            try:
                response = requests.post(
                    self._api_url(method),
                    json=payload,
                    proxies=_proxy_map(self.telegram_proxy),
                    timeout=timeout,
                )
                response.raise_for_status()
                data = response.json()
                if not data.get("ok"):
                    raise RuntimeError(f"telegram {method} failed: {data.get('description') or data}")
                return data
            except Exception as e:
                last_error = e
                if attempt >= max(1, attempts):
                    break
                time.sleep(min(2 * attempt, 5))
        raise RuntimeError(f"telegram {method} failed after retries: {_redact_token(last_error)}")

    def delete_webhook(self, drop_pending_updates: bool) -> None:
        self._telegram("deleteWebhook", {"drop_pending_updates": drop_pending_updates}, timeout=15)

    def configure_menu(self) -> None:
        commands = [
            {"command": "help", "description": "查看使用说明"},
        ]
        self._telegram("setMyCommands", {"commands": commands}, timeout=15)
        description = f"发送 {CHECK_COMMAND}，再按提示发送手机号，检测 GoPay 是否已注册。"
        self._telegram("setMyDescription", {"description": description}, timeout=15)
        self._telegram("setMyShortDescription", {"short_description": "GoPay 手机号注册检测"}, timeout=15)

    def get_updates(self, offset: Optional[int]) -> list[dict]:
        payload = {
            "timeout": self.poll_timeout,
            "limit": self.poll_limit,
            "allowed_updates": ["message", "edited_message"],
        }
        if offset is not None:
            payload["offset"] = offset
        data = self._telegram("getUpdates", payload, timeout=self.poll_timeout + 10, attempts=2)
        return data.get("result") or []

    def send_message(self, chat_id: int, text: str, reply_to_message_id: Optional[int] = None) -> None:
        payload = {"chat_id": chat_id, "text": text}
        if reply_to_message_id:
            payload["reply_parameters"] = {"message_id": reply_to_message_id}
        self._telegram("sendMessage", payload, timeout=15)

    def send_chat_action(self, chat_id: int, action: str = "typing") -> None:
        try:
            self._telegram("sendChatAction", {"chat_id": chat_id, "action": action}, timeout=10, attempts=2)
        except Exception as e:
            print(f"[checkphone-tgbot] sendChatAction ignored: {_redact_token(e)}", flush=True)

    def _pending_key(self, message: dict, chat_id: int) -> tuple[int, str]:
        user = message.get("from") or {}
        user_id = str(user.get("id") or chat_id)
        return int(chat_id), user_id

    def _is_owner(self, chat_id: int) -> bool:
        return bool(self.owner_chat_ids) and str(chat_id) in self.owner_chat_ids

    def _set_pending_check(self, message: dict, chat_id: int) -> None:
        self._pending_checks[self._pending_key(message, chat_id)] = time.time() + PENDING_TTL_SECONDS

    def _pop_pending_check(self, message: dict, chat_id: int) -> bool:
        key = self._pending_key(message, chat_id)
        expires_at = self._pending_checks.get(key)
        if not expires_at:
            return False
        if expires_at < time.time():
            self._pending_checks.pop(key, None)
            return False
        self._pending_checks.pop(key, None)
        return True

    def _set_pending_gopay_login(self, message: dict, chat_id: int, session: dict) -> None:
        session = dict(session)
        session["expires_at"] = time.time() + PENDING_TTL_SECONDS
        self._pending_gopay_logins[self._pending_key(message, chat_id)] = session

    def _get_pending_gopay_login(self, message: dict, chat_id: int) -> Optional[dict]:
        key = self._pending_key(message, chat_id)
        session = self._pending_gopay_logins.get(key)
        if not session:
            return None
        if float(session.get("expires_at") or 0) < time.time():
            self._pending_gopay_logins.pop(key, None)
            return None
        return session

    def _clear_pending_gopay_login(self, message: dict, chat_id: int) -> None:
        self._pending_gopay_logins.pop(self._pending_key(message, chat_id), None)

    def _send_private_denied(self, chat_id: int, message_id: Optional[int]) -> None:
        self.send_message(chat_id, "这个功能未授权。", message_id)

    def _handle_private_command(self, first: str, text: str, message: dict, chat_id: int) -> bool:
        if first not in PRIVATE_COMMANDS:
            return False
        if not self._is_owner(chat_id):
            self._send_private_denied(chat_id, message.get("message_id"))
            return True

        if first == LOGIN_GOPAY_COMMAND:
            self._set_pending_gopay_login(message, chat_id, {"step": "phone"})
            self.send_message(chat_id, gopay_login_phone_prompt(self.default_country_code), message.get("message_id"))
            return True
        if first == GOPAY_STATUS_COMMAND:
            self.send_chat_action(chat_id)
            result = gopay_login.check_ready_account()
            self.send_message(chat_id, format_gopay_balance_response(result), message.get("message_id"))
            return True
        if first == CLEAR_GOPAY_LOGIN_COMMAND:
            self._clear_pending_gopay_login(message, chat_id)
            gopay_login.clear_state()
            self.send_message(chat_id, "已清空本地 GoPay 登录状态。", message.get("message_id"))
            return True
        return False

    def _handle_pending_gopay_login(self, text: str, message: dict, chat_id: int) -> bool:
        session = self._get_pending_gopay_login(message, chat_id)
        if not session:
            return False
        if not self._is_owner(chat_id):
            self._clear_pending_gopay_login(message, chat_id)
            self._send_private_denied(chat_id, message.get("message_id"))
            return True

        step = session.get("step")
        if step == "phone":
            request = parse_check_text(text, self.default_country_code)
            if request is None:
                self._set_pending_gopay_login(message, chat_id, {"step": "phone"})
                self.send_message(chat_id, gopay_login_phone_prompt(self.default_country_code), message.get("message_id"))
                return True
            self._set_pending_gopay_login(
                message,
                chat_id,
                {"step": "pin", "phone": request.phone, "country_code": request.country_code},
            )
            self.send_message(chat_id, gopay_pin_prompt(), message.get("message_id"))
            return True

        if step == "pin":
            pin = re.sub(r"\D", "", text)
            if not pin:
                self._set_pending_gopay_login(message, chat_id, session)
                self.send_message(chat_id, gopay_pin_prompt(), message.get("message_id"))
                return True
            self.send_chat_action(chat_id)
            result = gopay_login.start_login(
                str(session.get("phone") or ""),
                pin,
                str(session.get("country_code") or self.default_country_code),
            )
            if not result.get("success"):
                self._clear_pending_gopay_login(message, chat_id)
                self.send_message(chat_id, format_gopay_balance_response(result), message.get("message_id"))
                return True
            if result.get("ready"):
                self._clear_pending_gopay_login(message, chat_id)
                self.send_message(chat_id, format_gopay_balance_response(result), message.get("message_id"))
                return True
            if result.get("otp_sent"):
                self._set_pending_gopay_login(message, chat_id, {"step": "otp"})
                self.send_message(chat_id, gopay_otp_prompt(result.get("verification_method", "")), message.get("message_id"))
                return True
            self._clear_pending_gopay_login(message, chat_id)
            self.send_message(chat_id, "GoPay 登录状态未知。", message.get("message_id"))
            return True

        if step == "otp":
            otp = re.sub(r"\D", "", text)
            if not otp:
                self._set_pending_gopay_login(message, chat_id, {"step": "otp"})
                self.send_message(chat_id, gopay_otp_prompt(), message.get("message_id"))
                return True
            self.send_chat_action(chat_id)
            result = gopay_login.complete_login(otp)
            self._clear_pending_gopay_login(message, chat_id)
            self.send_message(chat_id, format_gopay_balance_response(result), message.get("message_id"))
            return True

        self._clear_pending_gopay_login(message, chat_id)
        return False

    def handle_update(self, update: dict) -> None:
        message = update.get("message") or update.get("edited_message") or {}
        chat = message.get("chat") or {}
        chat_id = chat.get("id")
        if chat_id is None:
            return

        if self.allowed_chat_ids and str(chat_id) not in self.allowed_chat_ids:
            print(f"[checkphone-tgbot] ignoring unauthorized chat_id={chat_id}", flush=True)
            return

        text = str(message.get("text") or "").strip()
        if not text:
            return

        first = _strip_bot_mention(text.split(maxsplit=1)[0])
        if first in {"/start", "/help"}:
            print(f"[checkphone-tgbot] help chat_id={chat_id}", flush=True)
            help_text = owner_usage_text(self.default_country_code) if self._is_owner(chat_id) else usage_text(self.default_country_code)
            self.send_message(chat_id, help_text, message.get("message_id"))
            return

        if self._handle_private_command(first, text, message, chat_id):
            return

        if self._handle_pending_gopay_login(text, message, chat_id):
            return

        if first in CHECK_COMMANDS:
            parts = text.split(maxsplit=1)
            if len(parts) > 1:
                self.send_message(chat_id, phone_prompt_text(self.default_country_code), message.get("message_id"))
                return
            self._set_pending_check(message, chat_id)
            self.send_message(chat_id, phone_prompt_text(self.default_country_code), message.get("message_id"))
            return
        elif self._pop_pending_check(message, chat_id):
            request = parse_check_text(text, self.default_country_code)
            if request is None:
                self._set_pending_check(message, chat_id)
                self.send_message(chat_id, phone_prompt_text(self.default_country_code), message.get("message_id"))
                return
        else:
            request = parse_check_text(text, self.default_country_code)

        if request is None:
            if first.startswith("/"):
                self.send_message(chat_id, usage_text(self.default_country_code), message.get("message_id"))
            return

        self.send_chat_action(chat_id)
        print(f"[checkphone-tgbot] check chat_id={chat_id} country_code={request.country_code}", flush=True)
        result = self.checker(request.phone, request.country_code)
        self.send_message(
            chat_id,
            format_check_response(request.phone, request.country_code, result),
            message.get("message_id"),
        )

    def run(self, drop_pending_updates: bool = True) -> None:
        self.delete_webhook(drop_pending_updates)
        try:
            self.configure_menu()
        except Exception as e:
            print(f"[checkphone-tgbot] configure menu ignored: {_redact_token(e)}", flush=True)
        offset = None
        print("[checkphone-tgbot] long polling started", flush=True)
        while not self._stopping:
            try:
                updates = self.get_updates(offset)
                for update in updates:
                    update_id = update.get("update_id")
                    try:
                        self.handle_update(update)
                        if isinstance(update_id, int):
                            offset = max(offset or 0, update_id + 1)
                    except Exception as e:
                        print(f"[checkphone-tgbot] update handling failed: {_redact_token(e)}", flush=True)
            except Exception as e:
                print(f"[checkphone-tgbot] polling failed: {_redact_token(e)}", flush=True)
                time.sleep(5)


def main() -> int:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        print("TELEGRAM_BOT_TOKEN is required", file=sys.stderr)
        return 2

    bot = TelegramCheckPhoneBot(
        token,
        api_base=os.environ.get("TELEGRAM_API_BASE", "https://api.telegram.org"),
        telegram_proxy=os.environ.get("TELEGRAM_PROXY", ""),
        default_country_code=os.environ.get("GOPAY_COUNTRY_CODE", "62"),
        allowed_chat_ids=parse_allowed_chat_ids(os.environ.get("TELEGRAM_ALLOWED_CHAT_IDS", "")),
        owner_chat_ids=parse_allowed_chat_ids(
            os.environ.get("TELEGRAM_OWNER_CHAT_IDS", "") or os.environ.get("TELEGRAM_ALLOWED_CHAT_IDS", "")
        ),
        poll_timeout=int(os.environ.get("TELEGRAM_POLL_TIMEOUT_SECONDS", "30")),
        poll_limit=int(os.environ.get("TELEGRAM_POLL_LIMIT", "20")),
    )
    signal.signal(signal.SIGTERM, bot.stop)
    signal.signal(signal.SIGINT, bot.stop)
    bot.run(drop_pending_updates=_env_bool("TELEGRAM_DROP_PENDING_UPDATES", True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
