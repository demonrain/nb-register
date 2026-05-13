"""
SMS Service - HeroSMS 接码平台 gRPC 封装
"""

import os
import time
import json
import threading
import urllib.error
import urllib.request
import urllib.parse
from concurrent import futures

import grpc
import sms_pb2
import sms_pb2_grpc

API_BASE = os.environ.get("HEROSMS_API_BASE", "https://hero-sms.com/stubs/handler_api.php").strip() or "https://hero-sms.com/stubs/handler_api.php"
API_KEY = os.environ.get("HEROSMS_API_KEY", "")
PROXY = os.environ.get("SMS_PROXY", "")
PORT = int(os.environ.get("SMS_PORT", "50051"))
DEFAULT_MAX_PRICE = float(os.environ.get("HEROSMS_MAX_PRICE", "0.05"))
SERVICE = os.environ.get("HEROSMS_SERVICE", "ni").strip() or "ni"
COUNTRY = int(os.environ.get("HEROSMS_COUNTRY", "6"))
COUNTRY_CALLING_CODE = os.environ.get("HEROSMS_COUNTRY_CALLING_CODE", "62").strip().lstrip("+")
NUMBER_TTL = 20 * 60  # 号码有效期 20 分钟
CANCEL_MIN_AGE_SECONDS = int(os.environ.get("SMS_CANCEL_MIN_AGE_SECONDS", "120"))

# 记录每个 activation 的获取时间
_activations = {}  # activation_id -> {"phone": str, "created_at": float}
_activation_lock = threading.Lock()
_get_number_inflight = False
_STATUS_OK = {
    1: "ACCESS_READY",
    3: "ACCESS_RETRY_GET",
    6: "ACCESS_ACTIVATION",
    8: "ACCESS_CANCEL",
}
_COUNTRY_CALLING_CODES = {
    0: "7",
    1: "380",
    2: "7",
    3: "86",
    4: "63",
    5: "95",
    6: "62",
    7: "60",
    8: "254",
    10: "84",
    16: "44",
    22: "91",
    36: "1",
    43: "49",
    52: "66",
    73: "55",
    78: "33",
    117: "351",
    187: "1",
    196: "65",
}


def _json_result(result: str):
    try:
        return json.loads(result)
    except (TypeError, ValueError):
        return None


def _result_error(result: str) -> str:
    data = _json_result(result)
    if isinstance(data, dict):
        title = data.get("title") or data.get("error") or data.get("status") or data.get("message")
        detail = data.get("details") or data.get("message") or data.get("error")
        if title and detail and title != detail:
            return f"{title}: {detail}"
        if title:
            return str(title)
    return result


def _calling_code(country: int) -> str:
    if country == COUNTRY and COUNTRY_CALLING_CODE:
        return COUNTRY_CALLING_CODE
    return _COUNTRY_CALLING_CODES.get(country, "")


def _normalize_phone(phone: str, country: int) -> str:
    value = str(phone or "").strip().lstrip("+")
    prefix = _calling_code(country)
    if prefix and value.startswith(prefix):
        return value[len(prefix):]
    return value


def _call(action: str, **params) -> str:
    if not API_KEY:
        raise RuntimeError("HEROSMS_API_KEY required")
    params["api_key"] = API_KEY
    params["action"] = action
    url = f"{API_BASE}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    if PROXY:
        handler = urllib.request.ProxyHandler({"https": PROXY, "http": PROXY})
        opener = urllib.request.build_opener(handler)
    else:
        opener = urllib.request.build_opener()
    try:
        resp = opener.open(req, timeout=15)
        return resp.read().decode().strip()
    except urllib.error.HTTPError as e:
        body = e.read().decode().strip()
        if body:
            return body
        raise


def _set_status(activation_id: str, status: int) -> tuple[bool, str]:
    if not activation_id:
        return False, "activation_id required"
    if status not in _STATUS_OK:
        return False, "unsupported status"
    result = _call("setStatus", id=activation_id, status=status)
    expected = _STATUS_OK.get(status)
    return (not expected or result == expected), result


def _prune_expired_activations_locked():
    now = time.time()
    expired = [
        activation_id
        for activation_id, activation in _activations.items()
        if now - activation.get("created_at", 0) >= NUMBER_TTL
    ]
    for activation_id in expired:
        _activations.pop(activation_id, None)


def _active_activation_locked():
    _prune_expired_activations_locked()
    for activation_id, activation in _activations.items():
        return activation_id, activation
    return "", None


def _activation_action_response(response_type, activation_id: str, status: int):
    if not activation_id:
        return response_type(success=False, error_message="activation_id required")
    success, result = _set_status(activation_id, status)
    if status in (6, 8) and success:
        with _activation_lock:
            _activations.pop(activation_id, None)
    return response_type(
        success=success,
        error_message="" if success else _result_error(result),
        raw_response=result,
    )


def _wait_until_cancel_allowed(activation_id: str, context) -> str:
    if CANCEL_MIN_AGE_SECONDS <= 0:
        return ""
    with _activation_lock:
        activation = _activations.get(activation_id)
    if not activation:
        return ""

    age = time.time() - activation.get("created_at", 0)
    remaining = CANCEL_MIN_AGE_SECONDS - age
    if remaining <= 0:
        return ""

    deadline = time.time() + remaining
    while time.time() < deadline:
        if context is not None and not context.is_active():
            return "CANCEL_WAIT_CANCELLED"
        time.sleep(min(1.0, max(0.0, deadline - time.time())))
    return ""


def _cancel_activation_response(activation_id: str, context):
    if not activation_id:
        return sms_pb2.CancelActivationResponse(success=False, error_message="activation_id required")
    wait_error = _wait_until_cancel_allowed(activation_id, context)
    if wait_error:
        return sms_pb2.CancelActivationResponse(success=False, error_message=wait_error)
    return _activation_action_response(sms_pb2.CancelActivationResponse, activation_id, 8)


class SMSServicer(sms_pb2_grpc.SMSServiceServicer):

    def GetNumber(self, request, context):
        global _get_number_inflight
        reserved_number = False
        try:
            with _activation_lock:
                force_new_number = bool(getattr(request, "force_new_number", False))
                active_id, _ = _active_activation_locked()
                if active_id and not force_new_number:
                    return sms_pb2.GetNumberResponse(
                        success=False,
                        error_message="ACTIVE_ACTIVATION_EXISTS",
                        activation_id=active_id,
                    )
                if _get_number_inflight:
                    return sms_pb2.GetNumberResponse(
                        success=False,
                        error_message="GET_NUMBER_IN_PROGRESS",
                    )
                _get_number_inflight = True
                reserved_number = True

            service = (request.service or SERVICE).strip() or SERVICE
            country = request.country or COUNTRY
            params = {"service": service, "country": country}
            max_price = request.max_price or DEFAULT_MAX_PRICE
            if max_price > 0:
                params["maxPrice"] = max_price

            result = _call("getNumber", **params)
            if result.startswith("ACCESS_NUMBER"):
                parts = result.split(":", 2)
                if len(parts) != 3:
                    return sms_pb2.GetNumberResponse(success=False, error_message=f"bad ACCESS_NUMBER response: {result}")
                activation_id = parts[1]
                raw_phone = parts[2]
                phone = _normalize_phone(raw_phone, country)
                with _activation_lock:
                    _activations[activation_id] = {
                        "phone": phone,
                        "raw_phone": raw_phone,
                        "country": country,
                        "created_at": time.time(),
                    }
                prefix = _calling_code(country)
                display_phone = f"+{prefix}{phone}" if prefix else raw_phone
                print(f"[sms] GetNumber service={service} country={country}: {display_phone} id={activation_id}")
                return sms_pb2.GetNumberResponse(
                    success=True, activation_id=activation_id, phone=phone)
            error = _result_error(result)
            print(f"[sms] GetNumber failed service={service}: {error}")
            return sms_pb2.GetNumberResponse(success=False, error_message=error)
        except Exception as e:
            return sms_pb2.GetNumberResponse(success=False, error_message=str(e))
        finally:
            if reserved_number:
                with _activation_lock:
                    _get_number_inflight = False

    def WaitOTP(self, request, context):
        try:
            if not request.activation_id:
                return sms_pb2.WaitOTPResponse(success=False, error_message="activation_id required")
            # 检查号码是否还在有效期内
            with _activation_lock:
                act = _activations.get(request.activation_id)
            if act:
                elapsed = time.time() - act["created_at"]
                remaining_ttl = NUMBER_TTL - elapsed
                if remaining_ttl <= 0:
                    return sms_pb2.WaitOTPResponse(success=False, error_message="NUMBER_EXPIRED")
            else:
                remaining_ttl = NUMBER_TTL

            timeout = min(request.timeout_seconds or 120, int(remaining_ttl))
            deadline = time.time() + timeout
            while time.time() < deadline:
                if not context.is_active():
                    return sms_pb2.WaitOTPResponse(success=False, error_message="cancelled")
                # 再次检查 TTL
                if act and (time.time() - act["created_at"]) >= NUMBER_TTL:
                    return sms_pb2.WaitOTPResponse(success=False, error_message="NUMBER_EXPIRED")
                result = _call("getStatus", id=request.activation_id)
                if result.startswith("STATUS_OK"):
                    parts = result.split(":", 1)
                    code = parts[1].strip() if len(parts) == 2 else ""
                    if not code:
                        return sms_pb2.WaitOTPResponse(success=False, error_message=f"bad STATUS_OK response: {result}")
                    print(f"[sms] WaitOTP: got code {code} for {request.activation_id}")
                    return sms_pb2.WaitOTPResponse(success=True, code=code)
                if result == "STATUS_CANCEL":
                    print(f"[sms] WaitOTP: cancelled {request.activation_id}")
                    return sms_pb2.WaitOTPResponse(success=False, error_message="cancelled")
                if result == "STATUS_WAIT_CODE" or result.startswith("STATUS_WAIT_RETRY"):
                    time.sleep(5)
                    continue
                return sms_pb2.WaitOTPResponse(success=False, error_message=_result_error(result))
            return sms_pb2.WaitOTPResponse(success=False, error_message="timeout")
        except Exception as e:
            return sms_pb2.WaitOTPResponse(success=False, error_message=str(e))

    def MarkSMSSent(self, request, context):
        try:
            return _activation_action_response(sms_pb2.MarkSMSSentResponse, request.activation_id, 1)
        except Exception as e:
            return sms_pb2.MarkSMSSentResponse(success=False, error_message=str(e))

    def RequestAdditionalSMS(self, request, context):
        try:
            return _activation_action_response(sms_pb2.RequestAdditionalSMSResponse, request.activation_id, 3)
        except Exception as e:
            return sms_pb2.RequestAdditionalSMSResponse(success=False, error_message=str(e))

    def FinishActivation(self, request, context):
        try:
            return _activation_action_response(sms_pb2.FinishActivationResponse, request.activation_id, 6)
        except Exception as e:
            return sms_pb2.FinishActivationResponse(success=False, error_message=str(e))

    def CancelActivation(self, request, context):
        try:
            return _cancel_activation_response(request.activation_id, context)
        except Exception as e:
            return sms_pb2.CancelActivationResponse(success=False, error_message=str(e))

    def GetBalance(self, request, context):
        try:
            result = _call("getBalance")
            if result.startswith("ACCESS_BALANCE:"):
                result = result.split(":", 1)[1]
            return sms_pb2.BalanceResponse(balance=_result_error(result))
        except Exception as e:
            return sms_pb2.BalanceResponse(balance=str(e))


def serve():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=4))
    sms_pb2_grpc.add_SMSServiceServicer_to_server(SMSServicer(), server)
    server.add_insecure_port(f"0.0.0.0:{PORT}")
    server.start()
    print(f"[sms-service] gRPC listening on :{PORT}")
    server.wait_for_termination()


if __name__ == "__main__":
    serve()
