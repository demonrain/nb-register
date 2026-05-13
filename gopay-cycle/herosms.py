"""
HeroSMS 接码平台客户端
API 基于 SMS-Activate 格式
"""

import time
import os
import json
import urllib.error
import urllib.request
import urllib.parse

API_BASE = os.environ.get("HEROSMS_API_BASE", "https://hero-sms.com/stubs/handler_api.php").strip() or "https://hero-sms.com/stubs/handler_api.php"


def _result_error(result: str) -> str:
    try:
        data = json.loads(result)
    except (TypeError, ValueError):
        return result
    if isinstance(data, dict):
        title = data.get("title") or data.get("error") or data.get("status") or data.get("message")
        detail = data.get("details") or data.get("message") or data.get("error")
        if title and detail and title != detail:
            return f"{title}: {detail}"
        if title:
            return str(title)
    return result


class HeroSMS:
    def __init__(self, api_key: str):
        self.api_key = api_key

    def _call(self, action: str, **params) -> str:
        if not self.api_key:
            raise RuntimeError("HEROSMS_API_KEY required")
        params["api_key"] = self.api_key
        params["action"] = action
        url = f"{API_BASE}?{urllib.parse.urlencode(params)}"
        try:
            resp = urllib.request.urlopen(url, timeout=15)
            return resp.read().decode().strip()
        except urllib.error.HTTPError as e:
            body = e.read().decode().strip()
            if body:
                return body
            raise

    def get_balance(self) -> str:
        result = self._call("getBalance")
        if result.startswith("ACCESS_BALANCE:"):
            return result.split(":", 1)[1]
        return _result_error(result)

    def get_number(self, service: str = None, country: int = 6, max_price: float = None) -> tuple:
        """
        获取号码。
        service: HeroSMS 服务码，默认 HEROSMS_SERVICE=ni (Gojek)
        country: 6 = Indonesia
        max_price: 最大价格过滤
        Returns: (activation_id, phone_number)
        """
        service = (service or os.environ.get("HEROSMS_SERVICE", "ni")).strip() or "ni"
        params = {"service": service, "country": country}
        if max_price is not None:
            params["maxPrice"] = max_price
        result = self._call("getNumber", **params)
        # Response: ACCESS_NUMBER:id:number
        if result.startswith("ACCESS_NUMBER"):
            parts = result.split(":", 2)
            if len(parts) != 3:
                raise Exception(f"bad ACCESS_NUMBER response: {result}")
            return parts[1], parts[2]
        raise Exception(f"getNumber failed: {_result_error(result)}")

    def get_status(self, activation_id: str) -> tuple:
        """
        查询激活状态。
        Returns: (status, code_or_none)
        Status: STATUS_WAIT_CODE, STATUS_OK:code, STATUS_CANCEL
        """
        result = self._call("getStatus", id=activation_id)
        if result.startswith("STATUS_OK"):
            parts = result.split(":", 1)
            code = parts[1].strip() if len(parts) == 2 else ""
            return "OK", code
        elif result == "STATUS_WAIT_CODE":
            return "WAITING", None
        elif result.startswith("STATUS_WAIT_RETRY"):
            return "WAITING", None
        elif result == "STATUS_CANCEL":
            return "CANCELLED", None
        return _result_error(result), None

    def set_status(self, activation_id: str, status: int) -> str:
        """
        设置激活状态。
        status: 1=通知SMS已发送, 3=重新请求SMS, 6=完成激活, 8=取消激活
        """
        return self._call("setStatus", id=activation_id, status=status)

    def request_additional_sms(self, activation_id: str) -> str:
        return self.set_status(activation_id, 3)

    def finish_activation(self, activation_id: str) -> str:
        return self.set_status(activation_id, 6)

    def cancel_activation(self, activation_id: str) -> str:
        return self.set_status(activation_id, 8)

    def wait_for_code(self, activation_id: str, timeout: int = 120, interval: int = 5) -> str:
        """等待接收验证码"""
        deadline = time.time() + timeout
        while time.time() < deadline:
            status, code = self.get_status(activation_id)
            if status == "OK":
                return code
            elif status == "CANCELLED":
                raise Exception("Activation cancelled")
            time.sleep(interval)
        raise TimeoutError(f"No code received within {timeout}s")


if __name__ == "__main__":
    import os
    key = os.environ.get("HEROSMS_API_KEY", "")
    if not key:
        print("Set HEROSMS_API_KEY env var")
        exit(1)
    
    sms = HeroSMS(key)
    print(f"Balance: {sms.get_balance()}")
