import base64
import json
import os
import tempfile
import time

from checkphone import (
    GOPAY_PROXY,
    GOTO_AUTH,
    GopayClient,
    _auth_body,
    _country_code,
    _is_rate_limited,
    _normalize_phone,
    _response_error,
    generate_device_fingerprint,
    login_methods_invalid_user,
)


GOPAY_CUSTOMER = "https://customer.gopayapi.com"
GOPAY_PIN_CLIENT_ID = os.environ.get("GOPAY_PIN_CLIENT_ID", "6d11d261d7ae462dbd4be0dc5f36a697-MFAGOJEK")
GOPAY_LOGIN_FP_RETRIES = int(os.environ.get("GOPAY_LOGIN_FP_RETRIES", "8"))
GOPAY_LOGIN_OTP_TIMEOUT_SECONDS = int(os.environ.get("GOPAY_LOGIN_OTP_TIMEOUT_SECONDS", "180"))
GOPAY_REQUIRED_BALANCE_RP = int(os.environ.get("GOPAY_REQUIRED_BALANCE_RP", "1"))
GOPAY_TGBOT_STATE_FILE = os.environ.get("GOPAY_TGBOT_STATE_FILE", "/data/gopay_login_state.json")

LOGIN_STATE_KEYS = (
    "_login_phone",
    "_login_country_code",
    "_login_verification_id",
    "_login_verification_method",
    "_login_otp_token",
    "_login_2fa_token",
    "_login_started_at",
    "_login_otp_sent_at",
    "_login_otp_expires_at",
)


def load_state() -> dict:
    if not os.path.exists(GOPAY_TGBOT_STATE_FILE):
        return {}
    with open(GOPAY_TGBOT_STATE_FILE, encoding="utf-8") as f:
        return json.load(f)


def save_state(state: dict) -> None:
    directory = os.path.dirname(GOPAY_TGBOT_STATE_FILE)
    if directory:
        os.makedirs(directory, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(prefix=".gopay-login.", suffix=".json", dir=directory or None)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
            f.write("\n")
        os.chmod(tmp_path, 0o600)
        os.replace(tmp_path, GOPAY_TGBOT_STATE_FILE)
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


def clear_state() -> None:
    if os.path.exists(GOPAY_TGBOT_STATE_FILE):
        os.unlink(GOPAY_TGBOT_STATE_FILE)


def new_logon_device_profile() -> dict:
    device = generate_device_fingerprint(randomize_model=True)
    device["profile_id"] = os.urandom(8).hex()
    device["profile_created_at"] = int(time.time())
    return device


def _choose_otp_method(methods) -> str:
    preferred = (os.environ.get("GOPAY_LOGIN_OTP_METHOD", "otp_wa") or "otp_wa").strip()
    for method in (preferred, "otp_wa", "otp_sms"):
        if method and method in methods:
            return method
    return preferred or "otp_wa"


def _decode_jwt_payload(token: str) -> dict:
    token = str(token or "").strip().removeprefix("Bearer ").strip()
    parts = token.split(".")
    if len(parts) < 2:
        return {}
    payload = parts[1]
    payload += "=" * (-len(payload) % 4)
    try:
        return json.loads(base64.urlsafe_b64decode(payload.encode()).decode("utf-8"))
    except Exception:
        return {}


def access_token_expires_at(token: str) -> int:
    try:
        return int(_decode_jwt_payload(token).get("exp") or 0)
    except (TypeError, ValueError):
        return 0


def _store_token_response(state: dict, data: dict) -> None:
    token = str(data.get("access_token") or "").strip()
    if not token:
        raise RuntimeError("access_token missing")
    state["token"] = token
    if data.get("refresh_token"):
        state["refresh_token"] = str(data.get("refresh_token") or "").strip()
    expires_at = access_token_expires_at(token)
    if not expires_at:
        try:
            expires_in = int(data.get("expires_in") or 0)
        except (TypeError, ValueError):
            expires_in = 0
        if expires_in > 0:
            expires_at = int(time.time()) + expires_in
    if expires_at:
        state["token_expires_at"] = expires_at
    state.pop("last_error", None)


def _parse_balance_amount(value):
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    text = str(value).strip()
    if not text:
        return None
    digits = "".join(ch for ch in text if ch.isdigit() or ch == "-")
    if not digits or digits == "-":
        return None
    try:
        return int(digits)
    except ValueError:
        return None


def _gopay_wallet_balance(data) -> tuple:
    items = data.get("data") if isinstance(data, dict) and isinstance(data.get("data"), list) else data
    if isinstance(items, dict):
        items = [items]
    if not isinstance(items, list):
        return None, ""

    for item in items:
        if not isinstance(item, dict) or item.get("type") != "GOPAY_WALLET":
            continue
        balance = item.get("balance") if isinstance(item.get("balance"), dict) else {}
        amount = _parse_balance_amount(balance.get("value"))
        if amount is None:
            amount = _parse_balance_amount(balance.get("display_value"))
        currency = str(balance.get("currency") or item.get("currency") or "").strip()
        return amount, currency
    return None, ""


def check_balance(state: dict) -> dict:
    token = str(state.get("token") or "").strip()
    if not token:
        return {"success": False, "error": "access_token missing"}

    device = state.get("device") or generate_device_fingerprint()
    state["device"] = device
    c = GopayClient(token, proxy=GOPAY_PROXY, device=device)
    r = c.get(f"{GOPAY_CUSTOMER}/v1/payment-options/balances")
    state["last_balance_check_at"] = int(time.time())
    if r.get("status") != 200:
        state["last_error"] = _response_error("balance check failed", r)
        save_state(state)
        return {"success": False, "error": state["last_error"]}

    raw = r.get("raw") if isinstance(r.get("raw"), dict) else {}
    if raw.get("success") is False:
        state["last_error"] = _response_error("balance check failed", r)
        save_state(state)
        return {"success": False, "error": state["last_error"]}

    amount, currency = _gopay_wallet_balance(r.get("data"))
    if amount is None:
        state["last_error"] = "gopay wallet balance missing"
        save_state(state)
        return {"success": False, "error": state["last_error"]}

    has_required_balance = amount > GOPAY_REQUIRED_BALANCE_RP
    state["balance_amount"] = amount
    state["balance_currency"] = currency or "IDR"
    state["has_required_balance"] = has_required_balance
    state["required_balance_rp"] = GOPAY_REQUIRED_BALANCE_RP
    state.pop("last_error", None)
    save_state(state)
    return {
        "success": True,
        "balance_amount": amount,
        "balance_currency": state["balance_currency"],
        "required_balance_rp": GOPAY_REQUIRED_BALANCE_RP,
        "has_required_balance": has_required_balance,
    }


def verify_profile(state: dict) -> dict:
    token = str(state.get("token") or "").strip()
    if not token:
        return {"success": False, "error": "access_token missing"}
    device = state.get("device") or generate_device_fingerprint()
    state["device"] = device
    c = GopayClient(token, proxy=GOPAY_PROXY, device=device)
    r = c.get(f"{GOPAY_CUSTOMER}/v1/users/profile")
    if r.get("status") != 200:
        return {"success": False, "error": _response_error("profile failed", r)}
    data = r.get("data") if isinstance(r.get("data"), dict) else {}
    phone = data.get("phone") or data.get("number") or ""
    if phone:
        state["phone"] = _normalize_phone(phone)
    state["stage"] = "ready"
    state["ready_at"] = int(time.time())
    save_state(state)
    return {"success": True, "phone": state.get("phone", "")}


def check_ready_account() -> dict:
    state = load_state()
    profile = verify_profile(state)
    if not profile.get("success"):
        return profile
    balance = check_balance(state)
    if not balance.get("success"):
        return balance
    balance["phone"] = state.get("phone", "")
    return balance


def start_login(phone: str, pin: str, country_code: str = "") -> dict:
    state = {}
    cc = _country_code(country_code)
    normalized_phone = _normalize_phone(phone, cc)
    if not normalized_phone:
        return {"success": False, "error": "phone missing"}
    if not pin:
        return {"success": False, "error": "gopay pin missing"}

    attempts = max(1, GOPAY_LOGIN_FP_RETRIES)
    last_response = None
    for attempt in range(1, attempts + 1):
        device = new_logon_device_profile()
        state["device"] = device
        state["_login_phone"] = normalized_phone
        state["_login_country_code"] = cc
        state["_login_started_at"] = int(time.time())
        state["stage"] = "login"
        save_state(state)

        c = GopayClient("", proxy=GOPAY_PROXY, device=device)
        r = c.post(
            f"{GOTO_AUTH}/goto-auth/login/methods",
            body=_auth_body(
                country_code=cc,
                device_verification_token_id="",
                email="",
                phone_number=normalized_phone,
            ),
        )
        last_response = r
        if r["status"] in (200, 201):
            break
        if _is_rate_limited(r) and attempt < attempts:
            time.sleep(1)
            continue
        if login_methods_invalid_user(r):
            return {"success": False, "not_registered": True, "error": _response_error("login methods failed", r)}
        return {"success": False, "error": _response_error("login methods failed", r)}
    else:
        return {"success": False, "error": _response_error("login methods failed", last_response or {})}

    methods = r["data"].get("methods", [])
    verification_id = r["data"].get("verification_id", "")
    if not verification_id:
        return {"success": False, "error": "verification_id missing"}
    if "goto_pin" not in methods:
        return {"success": False, "error": f"goto_pin unavailable: {methods}"}

    r = c.post(
        f"{GOTO_AUTH}/cvs/v1/initiate",
        body=_auth_body(
            country_code=cc,
            device_verification_token_id=None,
            email_address=None,
            flow="login_1fa",
            is_multiple_method=True,
            phone_number=normalized_phone,
            verification_id=verification_id,
            verification_method="goto_pin",
        ),
        extra_headers={"Authorization": ""},
    )
    if r["status"] != 200:
        return {"success": False, "error": _response_error("login pin initiate failed", r)}

    challenge_id = r["data"].get("challenge_id", "")
    if not challenge_id:
        return {"success": False, "error": "pin challenge_id missing"}

    r = c.get(f"{GOPAY_CUSTOMER}/api/v2/challenges/{challenge_id}/pin-page/nb")
    if r["status"] != 200:
        return {"success": False, "error": _response_error("pin page failed", r)}

    r = c.post(
        f"{GOPAY_CUSTOMER}/api/v1/users/pin/tokens/nb",
        body={"challenge_id": challenge_id, "client_id": GOPAY_PIN_CLIENT_ID, "pin": pin},
    )
    if r["status"] != 200:
        return {"success": False, "error": _response_error("pin token failed", r)}

    validation_jwt = r["data"].get("token", "")
    if not validation_jwt:
        return {"success": False, "error": "pin validation token missing"}

    r = c.post(
        f"{GOTO_AUTH}/cvs/v1/verify",
        body=_auth_body(
            data={"challenge_id": challenge_id, "validation_jwt": validation_jwt},
            flow="login_1fa",
            verification_id=verification_id,
            verification_method="goto_pin",
        ),
    )
    if r["status"] != 200:
        return {"success": False, "error": _response_error("login pin verify failed", r)}

    verification_token = r["data"].get("verification_token", "")
    if not verification_token:
        return {"success": False, "error": "1fa verification_token missing"}

    r = c.post(
        f"{GOTO_AUTH}/goto-auth/accountlist",
        body=_auth_body(),
        extra_headers={"Verification-Token": f"Bearer {verification_token}"},
    )
    if r["status"] != 200:
        return {"success": False, "error": _response_error("accountlist failed", r)}

    accounts = r["data"].get("account_list", [])
    account_id = accounts[0].get("account_id", "") if accounts else ""
    one_fa_token = r["data"].get("1fa_token", "")
    if not account_id or not one_fa_token:
        return {"success": False, "error": "account_id or 1fa_token missing"}

    r = c.post(
        f"{GOTO_AUTH}/goto-auth/token",
        body=_auth_body(account_id=account_id, ext_user_token=None, grant_type="cvs", token=one_fa_token),
    )
    if r["status"] == 201:
        _store_token_response(state, r["data"])
        state["phone"] = normalized_phone
        state["stage"] = "ready"
        state["ready_at"] = int(time.time())
        save_state(state)
        balance = check_balance(state)
        return {"success": True, "ready": True, "otp_sent": False, **balance}

    data = r.get("data") if isinstance(r.get("data"), dict) else {}
    two_fa_token = data.get("2fa_token", "")
    verification_id = data.get("verification_id", "")
    if r["status"] != 403 or not two_fa_token or not verification_id:
        return {"success": False, "error": _response_error("token exchange failed", r)}

    method = _choose_otp_method(data.get("methods", []))
    r = c.post(
        f"{GOTO_AUTH}/cvs/v1/initiate",
        body=_auth_body(
            country_code=cc,
            device_verification_token_id=None,
            email_address=None,
            flow="login_2fa",
            is_multiple_method=None,
            phone_number=normalized_phone,
            verification_id=verification_id,
            verification_method=method,
        ),
        extra_headers={"Authorization": ""},
    )
    if r["status"] != 200:
        return {"success": False, "error": _response_error("2fa otp initiate failed", r)}

    otp_token = r["data"].get("otp_token", "")
    if not otp_token:
        return {"success": False, "error": "2fa otp_token missing"}

    state["_login_phone"] = normalized_phone
    state["_login_country_code"] = cc
    state["_login_verification_id"] = verification_id
    state["_login_verification_method"] = method
    state["_login_otp_token"] = otp_token
    state["_login_2fa_token"] = two_fa_token
    now = int(time.time())
    state["_login_otp_sent_at"] = now
    state["_login_otp_expires_at"] = now + GOPAY_LOGIN_OTP_TIMEOUT_SECONDS
    state["stage"] = "login_otp_pending"
    save_state(state)
    return {"success": True, "ready": False, "otp_sent": True, "verification_method": method}


def complete_login(otp: str) -> dict:
    state = load_state()
    device = state.get("device")
    c = GopayClient("", proxy=GOPAY_PROXY, device=device)
    verification_id = state.get("_login_verification_id", "")
    otp_token = state.get("_login_otp_token", "")
    method = state.get("_login_verification_method", "otp_wa")
    two_fa_token = state.get("_login_2fa_token", "")
    if not verification_id or not otp_token or not two_fa_token:
        return {"success": False, "error": "login 2fa state missing"}

    r = c.post(
        f"{GOTO_AUTH}/cvs/v1/verify",
        body=_auth_body(
            data={"otp": otp, "otp_token": otp_token},
            flow="login_2fa",
            verification_id=verification_id,
            verification_method=method,
        ),
    )
    if r["status"] != 200:
        return {"success": False, "error": _response_error("2fa verify failed", r)}
    verification_token = r["data"].get("verification_token", "")
    if not verification_token:
        return {"success": False, "error": "2fa verification_token missing"}

    r = c.post(
        f"{GOTO_AUTH}/goto-auth/token",
        body=_auth_body(ext_user_token=None, grant_type="challenge", token=two_fa_token),
        extra_headers={"Verification-Token": f"Bearer {verification_token}"},
    )
    if r["status"] != 201:
        return {"success": False, "error": _response_error("challenge token failed", r)}

    _store_token_response(state, r["data"])
    state["phone"] = state.get("_login_phone", "")
    state["stage"] = "ready"
    state["ready_at"] = int(time.time())
    for key in LOGIN_STATE_KEYS:
        state.pop(key, None)
    save_state(state)
    balance = check_balance(state)
    return {"success": True, "ready": True, **balance}
