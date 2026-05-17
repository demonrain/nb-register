import os


DEFAULT_ORCHESTRATOR_ADDR = "orchestrator:50051"


class OrchestratorGopayClient:
    def __init__(self, addr: str = "", *, timeout: int = 120):
        self.addr = str(addr or os.environ.get("ORCHESTRATOR_ADDR") or DEFAULT_ORCHESTRATOR_ADDR).strip()
        self.timeout = max(1, int(timeout or 120))
        self._pb2 = None
        self._stub = None

    def _ensure_stub(self):
        if self._stub is not None:
            return self._pb2, self._stub
        import grpc
        import orchestrator_gopay_app_pb2
        import orchestrator_gopay_app_pb2_grpc

        channel = grpc.insecure_channel(self.addr)
        self._pb2 = orchestrator_gopay_app_pb2
        self._stub = orchestrator_gopay_app_pb2_grpc.GoPayAppWorkflowServiceStub(channel)
        return self._pb2, self._stub

    def status(self, user_id: str):
        pb2, stub = self._ensure_stub()
        return stub.GoPayUserStatus(pb2.GoPayUserStatusRequest(user_id=user_id), timeout=self.timeout)

    def clear_state(self, user_id: str):
        pb2, stub = self._ensure_stub()
        return stub.GoPayUserClearState(pb2.GoPayUserClearStateRequest(user_id=user_id), timeout=self.timeout)

    def set_wa_phone(self, user_id: str, *, wa_phone: str):
        pb2, stub = self._ensure_stub()
        return stub.GoPayUserSetWAPhone(
            pb2.GoPayUserSetWAPhoneRequest(user_id=user_id, wa_phone=wa_phone),
            timeout=self.timeout,
        )

    def get_wa_phone(self, user_id: str):
        pb2, stub = self._ensure_stub()
        return stub.GoPayUserGetWAPhone(pb2.GoPayUserGetWAPhoneRequest(user_id=user_id), timeout=self.timeout)

    def auth_start(self, user_id: str, *, phone: str, country_code: str, pin: str):
        pb2, stub = self._ensure_stub()
        return stub.GoPayUserAuthStart(
            pb2.GoPayUserAuthStartRequest(
                user_id=user_id,
                phone=phone,
                country_code=country_code,
                pin=pin,
            ),
            timeout=self.timeout,
        )

    def auth_complete(self, user_id: str, *, otp: str, pin: str):
        pb2, stub = self._ensure_stub()
        return stub.GoPayUserAuthComplete(
            pb2.GoPayUserAuthCompleteRequest(user_id=user_id, otp=otp, pin=pin),
            timeout=self.timeout,
        )

    def change_phone_start(self, user_id: str, *, new_phone: str, pin: str):
        pb2, stub = self._ensure_stub()
        return stub.GoPayUserChangePhoneStart(
            pb2.GoPayUserChangePhoneStartRequest(user_id=user_id, new_phone=new_phone, pin=pin),
            timeout=self.timeout,
        )

    def change_phone_complete(self, user_id: str, *, otp: str):
        pb2, stub = self._ensure_stub()
        return stub.GoPayUserChangePhoneComplete(
            pb2.GoPayUserChangePhoneCompleteRequest(user_id=user_id, otp=otp),
            timeout=self.timeout,
        )

    def change_phone_retry(self, user_id: str):
        pb2, stub = self._ensure_stub()
        return stub.GoPayUserChangePhoneRetry(
            pb2.GoPayUserChangePhoneRetryRequest(user_id=user_id),
            timeout=self.timeout,
        )

    def signup_start(self, user_id: str, *, phone: str, name: str, email: str, country_code: str):
        pb2, stub = self._ensure_stub()
        return stub.GoPayUserSignupStart(
            pb2.GoPayUserSignupStartRequest(
                user_id=user_id,
                phone=phone,
                name=name,
                email=email,
                country_code=country_code,
            ),
            timeout=self.timeout,
        )

    def signup_complete(self, user_id: str, *, otp: str):
        pb2, stub = self._ensure_stub()
        return stub.GoPayUserSignupComplete(
            pb2.GoPayUserSignupCompleteRequest(user_id=user_id, otp=otp),
            timeout=self.timeout,
        )

    def create_pin_start(self, user_id: str, *, pin: str):
        pb2, stub = self._ensure_stub()
        return stub.GoPayUserCreatePinStart(
            pb2.GoPayUserCreatePinStartRequest(user_id=user_id, pin=pin),
            timeout=self.timeout,
        )

    def create_pin_complete(self, user_id: str, *, otp: str, pin: str):
        pb2, stub = self._ensure_stub()
        return stub.GoPayUserCreatePinComplete(
            pb2.GoPayUserCreatePinCompleteRequest(user_id=user_id, otp=otp, pin=pin),
            timeout=self.timeout,
        )
