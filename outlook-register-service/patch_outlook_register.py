import os
from pathlib import Path


repo = Path(os.environ.get("OUTLOOK_REGISTER_DIR", "/opt/OutlookRegister")).resolve()
base_py = repo / "controllers" / "base_controller.py"
base = base_py.read_text(encoding="utf-8")

base_init_target = "        self.email_suffix = data['email_suffix']\n"
base_init_replacement = """        self.email_suffix = data['email_suffix']
        self.manual_captcha = bool(data.get("manual_captcha", False))
        self.manual_captcha_timeout = int(data.get("manual_captcha_timeout", 300))
        self.captcha_api_url = data.get("captcha_api_url", "")
        self.captcha_api_key = data.get("captcha_api_key", "")
        self.captcha_api_max_retries = int(data.get("captcha_max_retries", 3))
        self.captcha_api_quota_used = 0
        self.captcha_proxy = data.get("proxy", "")
"""
if base_init_replacement.strip() not in base:
    if base_init_target not in base:
        raise SystemExit("OutlookRegister base_controller.py changed; missing init target")
    base = base.replace(base_init_target, base_init_replacement, 1)

helper_anchor = "        os.makedirs(self.results_dir, exist_ok=True)\n"
helper_methods = """

    def first_visible_locator(self, page, selectors, timeout=10000):
        deadline = time.time() + timeout / 1000
        last_error = None
        while time.time() < deadline:
            for selector in selectors:
                try:
                    matches = page.locator(selector)
                    if matches.count() <= 0:
                        continue
                    locator = matches.nth(0)
                    if locator.is_visible(timeout=300):
                        return locator
                except Exception as exc:
                    last_error = exc
            page.wait_for_timeout(250)
        raise TimeoutError(f"no visible locator found: {selectors}; last_error={last_error}")

    def first_visible_text(self, page, texts, timeout=10000):
        deadline = time.time() + timeout / 1000
        last_error = None
        while time.time() < deadline:
            for text in texts:
                try:
                    matches = page.get_by_text(text)
                    if matches.count() <= 0:
                        continue
                    locator = matches.nth(0)
                    if locator.is_visible(timeout=300):
                        return locator
                except Exception as exc:
                    last_error = exc
            page.wait_for_timeout(250)
        raise TimeoutError(f"no visible text found: {texts}; last_error={last_error}")

    def optional_visible_text(self, page, texts, timeout=3000):
        try:
            return self.first_visible_text(page, texts, timeout=timeout)
        except Exception:
            return None

    def email_input(self, page, timeout=10000):
        return self.first_visible_locator(page, [
            '[aria-label="新建电子邮件"]',
            '[aria-label="New email"]',
            'input[type="email"]',
            'input[name="MemberName"]',
            '#usernameInput',
            'input'
        ], timeout=timeout)

    def primary_button(self, page, timeout=10000):
        return self.first_visible_locator(page, [
            '[data-testid="primaryButton"]',
            'button:has-text("Next")',
            'button:has-text("下一步")',
            'button:has-text("继续")'
        ], timeout=timeout)
"""

if helper_methods.strip() not in base:
    if helper_anchor not in base:
        raise SystemExit("OutlookRegister base_controller.py changed; missing helper anchor")
    base = base.replace(helper_anchor, helper_anchor + helper_methods, 1)

start_block = """        try:
            page.goto("https://outlook.live.com/mail/0/?prompt=create_account", timeout=20000, wait_until="domcontentloaded")
            page.get_by_text('同意并继续').wait_for(timeout=30000)
            start_time = time.time()
            page.wait_for_timeout(0.1 * self.wait_time)
            page.get_by_text('同意并继续').click(timeout=30000)
        except:
            print("[Error: IP] - IP质量不佳，无法进入注册界面。")
            return False
"""
start_replacement = """        try:
            print("[OutlookRegister] opening Outlook signup page", flush=True)
            page.goto("https://outlook.live.com/mail/0/?prompt=create_account", timeout=30000, wait_until="domcontentloaded")
            start_time = time.time()

            consent = self.optional_visible_text(page, ["同意并继续", "Agree and continue"], timeout=15000)
            if consent:
                print("[OutlookRegister] consent button visible", flush=True)
                page.wait_for_timeout(0.1 * self.wait_time)
                consent.click(timeout=30000)
                print("[OutlookRegister] consent accepted", flush=True)

            self.email_input(page, timeout=30000).wait_for(state="visible", timeout=30000)
            print("[OutlookRegister] signup form ready", flush=True)
        except Exception as e:
            print(f"[Error: IP] - IP质量不佳，无法进入注册界面: {e}", flush=True)
            return False
"""
if start_block not in base:
    raise SystemExit("OutlookRegister base_controller.py changed; missing start block")
base = base.replace(start_block, start_replacement, 1)

replacements = {
    'page.locator(\'[aria-label="新建电子邮件"]\').type(email, delay=0.006 * self.wait_time, timeout=10000)':
        'print("[OutlookRegister] filling email and password", flush=True)\n            self.email_input(page, timeout=10000).type(email, delay=0.006 * self.wait_time, timeout=10000)',
    'page.locator(\'[data-testid="primaryButton"]\').click(timeout=5000)':
        'self.primary_button(page, timeout=5000).click(timeout=5000)',
    'page.locator(\'[name="BirthYear"]\').fill(year, timeout=10000)':
        'print("[OutlookRegister] filling profile fields", flush=True)\n            page.locator(\'[name="BirthYear"]\').fill(year, timeout=10000)',
    "captcha_result = self.handle_captcha(page)":
        'print("[OutlookRegister] handling captcha", flush=True)\n            captcha_result = self.handle_captcha(page)',
    'page.locator(\'[aria-label="新邮件"]\').wait_for(timeout=32000)':
        'print("[OutlookRegister] waiting for mailbox initialization", flush=True)\n            self.first_visible_locator(page, [\'[aria-label="新邮件"]\', \'[aria-label="New mail"]\'], timeout=32000)',
}

birthdate_block = """            try:
                page.wait_for_timeout(0.02 * self.wait_time)
                page.locator('[name="BirthMonth"]').select_option(value=month, timeout=1000)
                page.wait_for_timeout(0.05 * self.wait_time)
                page.locator('[name="BirthDay"]').select_option(value=day)
            except:
                page.locator('[name="BirthMonth"]').click()
                page.wait_for_timeout(0.02 * self.wait_time)
                page.locator(f'[role="option"]:text-is("{month}月")').click()
                page.wait_for_timeout(0.04 * self.wait_time)
                page.locator('[name="BirthDay"]').click()
                page.wait_for_timeout(0.03 * self.wait_time)
                page.locator(f'[role="option"]:text-is("{day}日")').click()
                page.locator('[data-testid="primaryButton"]').click(timeout=5000)
"""
birthdate_replacement = """            try:
                page.wait_for_timeout(0.02 * self.wait_time)
                page.locator('[name="BirthMonth"]').select_option(value=month, timeout=1000)
                page.wait_for_timeout(0.05 * self.wait_time)
                page.locator('[name="BirthDay"]').select_option(value=day)
            except:
                month_names = [
                    "January", "February", "March", "April", "May", "June",
                    "July", "August", "September", "October", "November", "December",
                ]
                month_name = month_names[int(month) - 1]
                page.locator('[name="BirthMonth"]').first.click(timeout=5000, force=True)
                page.wait_for_timeout(0.02 * self.wait_time)
                self.first_visible_locator(page, [
                    f'[role="option"]:text-is("{month}月")',
                    f'[role="option"]:text-is("{month_name}")',
                    f'[role="option"]:text-is("{int(month)}")',
                ], timeout=10000).click(timeout=5000, force=True)
                page.wait_for_timeout(0.04 * self.wait_time)
                page.locator('[name="BirthDay"]').first.click(timeout=5000, force=True)
                page.wait_for_timeout(0.03 * self.wait_time)
                self.first_visible_locator(page, [
                    f'[role="option"]:text-is("{day}日")',
                    f'[role="option"]:text-is("{int(day)}")',
                ], timeout=10000).click(timeout=5000, force=True)
                self.primary_button(page, timeout=5000).click(timeout=5000)
"""
if birthdate_block not in base:
    raise SystemExit("OutlookRegister base_controller.py changed; missing birthdate block")
base = base.replace(birthdate_block, birthdate_replacement, 1)

for source, replacement in replacements.items():
    if source not in base:
        raise SystemExit(f"OutlookRegister base_controller.py changed; missing patch target: {source}")
    base = base.replace(source, replacement)

base = base.replace(
    '        except Exception:\n            print("[Error: IP] - 加载超时或因触发机器人检测导致按压次数达到最大仍未通过。")',
    '        except Exception as e:\n            print(f"[Error: IP] - 加载超时或因触发机器人检测导致按压次数达到最大仍未通过: {e}", flush=True)',
)
base_py.write_text(base, encoding="utf-8")

patchright_py = repo / "controllers" / "patchright_controller.py"
patchright = patchright_py.read_text(encoding="utf-8")
if "import time" not in patchright:
    patchright = patchright.replace("import random\n", "import random\nimport time\nimport requests\n", 1)
else:
    if "import requests" not in patchright:
        patchright = patchright.replace("import time\n", "import time\nimport requests\n", 1)

captcha_start = patchright.index("    def handle_captcha(self, page):")
captcha_end = patchright.index("    def get_thread_page(self):", captcha_start)
captcha_replacement = '''    def handle_captcha(self, page):

        def find_visible_locator(selectors, timeout=10000):
            deadline = time.time() + timeout / 1000
            last_error = None
            while time.time() < deadline:
                for frame in page.frames:
                    for selector in selectors:
                        try:
                            matches = frame.locator(selector)
                            if matches.count() <= 0:
                                continue
                            locator = matches.nth(0)
                            if locator.is_visible(timeout=250):
                                return locator
                        except Exception as exc:
                            last_error = exc
                page.wait_for_timeout(250)
            raise TimeoutError(f"captcha locator not found: {selectors}; last_error={last_error}")

        def has_visible_locator(selectors, timeout=1000):
            try:
                find_visible_locator(selectors, timeout=timeout)
                return True
            except Exception:
                return False

        def _bezier_move(x1, y1, x2, y2):
            """Move mouse along a cubic bezier curve for natural movement."""
            import math
            dist = math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)
            steps = max(12, min(45, int(dist / 8)))
            cx1 = x1 + (x2 - x1) * random.uniform(0.15, 0.4) + random.randint(-25, 25)
            cy1 = y1 + (y2 - y1) * random.uniform(0.0, 0.3) + random.randint(-25, 25)
            cx2 = x1 + (x2 - x1) * random.uniform(0.6, 0.85) + random.randint(-12, 12)
            cy2 = y1 + (y2 - y1) * random.uniform(0.7, 1.0) + random.randint(-12, 12)
            for i in range(steps + 1):
                t = i / steps
                u = 1 - t
                px = u**3 * x1 + 3 * u**2 * t * cx1 + 3 * u * t**2 * cx2 + t**3 * x2
                py = u**3 * y1 + 3 * u**2 * t * cy1 + 3 * u * t**2 * cy2 + t**3 * y2
                page.mouse.move(px, py)
                page.wait_for_timeout(random.randint(4, 18))

        def click_center(locator, hold_ms=0):
            box = locator.bounding_box(timeout=5000)
            if not box:
                raise TimeoutError("captcha locator has no bounding box")
            tx = box['x'] + box['width'] / 2 + random.randint(-6, 6)
            ty = box['y'] + box['height'] / 2 + random.randint(-6, 6)
            # Start from a random nearby position for natural approach
            sx = tx + random.randint(-120, 120)
            sy = ty + random.randint(-80, 80)
            page.mouse.move(sx, sy)
            page.wait_for_timeout(random.randint(80, 250))
            _bezier_move(sx, sy, tx, ty)
            page.wait_for_timeout(random.randint(30, 120))
            if hold_ms > 0:
                page.mouse.down()
                page.wait_for_timeout(hold_ms + random.randint(-300, 500))
                page.mouse.up()
            else:
                page.mouse.click(tx, ty)

        accessible_selectors = ['[aria-label="可访问性挑战"]', '[aria-label="Accessible challenge"]']
        press_selectors = ['[aria-label*="按住"]', '[aria-label*="Press and hold"]', '[aria-label*="Press"]', 'button:has-text("按住")', 'button:has-text("Press and hold")']
        retry_selectors = ['[aria-label*="再次"]', '[aria-label*="again"]', 'button:has-text("再次")', 'button:has-text("Press again")']
        all_captcha_selectors = accessible_selectors + press_selectors + retry_selectors

        if getattr(self, "captcha_api_url", None) and getattr(self, "captcha_api_key", None):
            max_quota = getattr(self, "captcha_api_max_retries", 3)
            if getattr(self, "captcha_api_quota_used", 0) >= max_quota:
                print(f"[Error: FunCaptcha] API quota protection triggered (max {max_quota} calls). Failing fast.", flush=True)
                return False

            self.captcha_api_quota_used = getattr(self, "captcha_api_quota_used", 0) + 1
            print(f"[FunCaptcha] API configured, preparing to intercept Blob and inject Token... (Call {self.captcha_api_quota_used}/{max_quota})", flush=True)

            public_key = "B7D8911C-5CC8-A9A3-35B0-554ACEE604DA"
            app_id = "PXzC5j78di"
            captcha_type = "FunCaptcha"
            blob_data = None

            page.wait_for_timeout(3000)
            for fr in page.frames:
                if 'hsprotect.net' in fr.url:
                    captcha_type = "PerimeterX"
                    print(f"[{captcha_type}] Detected HUMAN Security Frame: {fr.url}", flush=True)
                    try:
                        import urllib.parse
                        parsed = urllib.parse.urlparse(fr.url)
                        qs = urllib.parse.parse_qs(parsed.query)
                        if 'app_id' in qs:
                            app_id = qs['app_id'][0]
                    except:
                        pass
                    break
                elif 'arkoselabs.com' in fr.url or 'funcaptcha' in fr.url:
                    captcha_type = "FunCaptcha"
                    print(f"[{captcha_type}] Detected Arkose Labs Frame: {fr.url}", flush=True)
                    try:
                        import urllib.parse
                        parsed = urllib.parse.urlparse(fr.url)
                        qs = urllib.parse.parse_qs(parsed.query)
                        if 'public_key' in qs:
                            public_key = qs['public_key'][0]
                        if 'data' in qs:
                            blob_data = qs['data'][0]
                        elif 'blob' in qs:
                            blob_data = qs['blob'][0]
                    except:
                        pass
                    break

            api_base = self.captcha_api_url.rstrip('/')
            create_payload = {"clientKey": self.captcha_api_key}

            # Parse proxy for CAPTCHA API (IP binding improves token acceptance)
            proxy_params = {}
            _captcha_proxy = getattr(self, "captcha_proxy", "")
            if _captcha_proxy:
                try:
                    import urllib.parse as _up
                    _pp = _up.urlparse(_captcha_proxy)
                    proxy_params = {
                        "proxyType": _pp.scheme.split("://")[0] if "://" in _pp.scheme else _pp.scheme,
                        "proxyAddress": _pp.hostname or "",
                        "proxyPort": _pp.port or 0,
                    }
                    if _pp.username:
                        proxy_params["proxyLogin"] = _up.unquote(_pp.username)
                    if _pp.password:
                        proxy_params["proxyPassword"] = _up.unquote(_pp.password)
                    print(f"[Captcha] Using proxy for solving: {_pp.scheme}://{_pp.hostname}:{_pp.port}", flush=True)
                except Exception as proxy_err:
                    print(f"[Captcha] Failed to parse proxy for API, falling back to Proxyless: {proxy_err}", flush=True)
                    proxy_params = {}

            if captcha_type == "PerimeterX":
                print(f"[PerimeterX] Using App ID: {app_id}", flush=True)
                task_data = {
                    "type": "PerimeterxTask" if proxy_params else "PerimeterxTaskProxyless",
                    "websiteURL": "https://signup.live.com/signup?lic=1",
                    "appId": app_id,
                    "pageAction": "b"
                }
                task_data.update(proxy_params)
                create_payload["task"] = task_data
            else:
                print(f"[FunCaptcha] Using Public Key: {public_key}", flush=True)
                task_data = {
                    "type": "FunCaptchaTask" if proxy_params else "FunCaptchaTaskProxyless",
                    "websiteURL": "https://signup.live.com/signup?lic=1",
                    "websitePublicKey": public_key
                }
                if blob_data:
                    task_data["data"] = '{"blob":"' + blob_data + '"}'
                task_data.update(proxy_params)
                create_payload["task"] = task_data

            try:
                print(f"[{captcha_type}] Submitting task to {api_base}/createTask", flush=True)
                create_resp = requests.post(f"{api_base}/createTask", json=create_payload, timeout=15).json()
                if create_resp.get("errorId", 1) != 0:
                    print(f"[Error: {captcha_type}] Create Task Failed: {create_resp}", flush=True)
                    return False

                task_id = create_resp["taskId"]
                print(f"[{captcha_type}] Task ID: {task_id}, waiting for solution...", flush=True)

                solution_data = None
                for _ in range(60):
                    time.sleep(2)
                    res = requests.post(f"{api_base}/getTaskResult", json={"clientKey": self.captcha_api_key, "taskId": task_id}, timeout=10).json()
                    if res.get("status") == "ready":
                        solution_data = res.get("solution", {})
                        break
                    elif res.get("status") == "processing":
                        continue
                    else:
                        print(f"[Error: {captcha_type}] Solving failed: {res}", flush=True)
                        break

                if not solution_data:
                    print(f"[Error: {captcha_type}] Failed to get token or timed out", flush=True)
                    return False

                print(f"[{captcha_type}] Token received! Injecting into page...", flush=True)

                if captcha_type == "PerimeterX":
                    px_captcha = solution_data.get("_pxCaptcha")
                    px_cookie = solution_data.get("_px3") or solution_data.get("_px")
                    if px_captcha:
                        # Try PX callback first, then postMessage fallback
                        _px_js = f"""(function() {{
                            if (window._pxOnCaptchaSuccess) {{
                                window._pxOnCaptchaSuccess('{px_captcha}');
                                return 'callback';
                            }}
                            window.postMessage({{ type: 'px_captcha_solved', captchaData: '{px_captcha}' }}, '*');
                            return 'postMessage';
                        }})()"""
                        _px_method = page.evaluate(_px_js)
                        print(f"[PerimeterX] Injected via {_px_method}", flush=True)
                    if px_cookie:
                        for _cn in ["_px3", "_px", "_pxhd"]:
                            _cv = solution_data.get(_cn)
                            if _cv:
                                page.context.add_cookies([{"name": _cn, "value": _cv, "domain": ".live.com", "path": "/"}])
                        if not px_captcha:
                            page.reload()
                else:
                    token = solution_data.get("token")
                    # Multi-method injection: callback → input → enforcement → postMessage
                    _fc_js = f"""(function() {{
                        var tk = '{token}';
                        if (window.__funcaptcha_callback) {{
                            window.__funcaptcha_callback(tk);
                            return 'callback';
                        }}
                        var inputs = document.querySelectorAll('input[name="fc-token"], input[id*="fc-token"]');
                        if (inputs.length > 0) {{
                            inputs[0].value = tk;
                            inputs[0].dispatchEvent(new Event('change', {{ bubbles: true }}));
                            return 'input';
                        }}
                        if (window.ArkoseEnforcement) {{
                            window.ArkoseEnforcement.setConfig({{ data: {{ token: tk }} }});
                            return 'enforcement';
                        }}
                        var msg = JSON.stringify({{ eventId: 'challenge-complete', payload: {{ sessionToken: tk }} }});
                        window.postMessage(msg, '*');
                        for (var i = 0; i < window.frames.length; i++) {{
                            try {{ window.frames[i].postMessage(msg, '*'); }} catch(e) {{}}
                        }}
                        return 'postMessage';
                    }})()"""
                    _fc_method = page.evaluate(_fc_js)
                    print(f"[FunCaptcha] Injected via {_fc_method}", flush=True)

                page.wait_for_timeout(8000)

                if (
                    page.get_by_text('一些异常活动').count()
                    or page.get_by_text('unusual activity').count()
                    or page.get_by_text('此站点正在维护，暂时无法使用，请稍后重试。').count()
                    or page.get_by_text('temporarily unavailable').count()
                ):
                    print(f"[Error: Rate limit] - 正常通过验证码，但当前IP注册频率过快或被拦截。")
                    return False

                if page.get_by_text('取消').count() > 0 or page.get_by_text('Cancel').count() > 0:
                    print(f"[{captcha_type}] Passed via API injection!", flush=True)
                    return True

                print(f"[{captcha_type}] Injection completed but success indicator not verified immediately. Continuing.", flush=True)
                return True

            except Exception as e:
                print(f"[Error: {captcha_type}] API Exception: {e}", flush=True)
                return False

        if self.manual_captcha:
            print("[ManualCaptcha] 请在弹出的浏览器里手动完成验证", flush=True)
            deadline = time.time() + self.manual_captcha_timeout
            seen_challenge = False
            clear_since = None
            while time.time() < deadline:
                if (
                    page.get_by_text('一些异常活动').count()
                    or page.get_by_text('unusual activity').count()
                    or page.get_by_text('此站点正在维护，暂时无法使用，请稍后重试。').count()
                    or page.get_by_text('temporarily unavailable').count()
                ):
                    print("[Error: Rate limit] - 当前IP注册频率过快或被拦截。")
                    return False

                if has_visible_locator(all_captcha_selectors, timeout=1500):
                    seen_challenge = True
                    clear_since = None
                    page.wait_for_timeout(1000)
                    continue

                if seen_challenge:
                    if clear_since is None:
                        clear_since = time.time()
                    if time.time() - clear_since >= 5:
                        print("[ManualCaptcha] 验证码已通过，继续流程。", flush=True)
                        return True

                if not seen_challenge and time.time() < deadline - self.manual_captcha_timeout + 45:
                    page.wait_for_timeout(1000)
                    continue

                if not seen_challenge:
                    print("[ManualCaptcha] 验证码已通过，继续流程。", flush=True)
                    return True

                page.wait_for_timeout(1000)

            print("[Error: ManualCaptcha] - 等待人工验证码超时。", flush=True)
            return False

        # Pre-captcha: simulate natural page interaction
        try:
            vw = page.evaluate("window.innerWidth")
            vh = page.evaluate("window.innerHeight")
            sx, sy = random.randint(100, max(101, vw - 100)), random.randint(100, max(101, vh - 100))
            page.mouse.move(sx, sy)
            page.wait_for_timeout(random.randint(200, 600))
            ex, ey = random.randint(100, max(101, vw - 100)), random.randint(100, max(101, vh - 100))
            _bezier_move(sx, sy, ex, ey)
            page.wait_for_timeout(random.randint(300, 800))
        except Exception:
            pass

        max_attempts = 3
        for attempt in range(max_attempts):
            page.wait_for_timeout(random.randint(300, 700))

            try:
                press_button = find_visible_locator(press_selectors, timeout=10000)
                print(f"[FunCaptcha/PerimeterX] attempt {attempt+1}/{max_attempts}: press and hold", flush=True)
                click_center(press_button, hold_ms=4500)
            except Exception as exc:
                print(f"[Error: Captcha] - 未找到按压验证码按钮: {exc}")
                return False

            page.wait_for_timeout(8000)

            if (
                page.get_by_text('一些异常活动').count()
                or page.get_by_text('unusual activity').count()
                or page.get_by_text('此站点正在维护，暂时无法使用，请稍后重试。').count()
                or page.get_by_text('temporarily unavailable').count()
            ):
                print("[Error: Rate limit] - 正常通过验证码，但当前IP注册频率过快。")
                return False

            if page.get_by_text('取消').count() > 0 or page.get_by_text('Cancel').count() > 0:
                print(f"[Captcha] passed after press-and-hold on attempt {attempt+1}", flush=True)
                break

            if not has_visible_locator(all_captcha_selectors, timeout=5000):
                print(f"[Captcha] captcha disappeared, likely passed on attempt {attempt+1}", flush=True)
                break

            print(f"[Captcha] attempt {attempt+1}/{max_attempts}: press-and-hold failed, trying accessible + retry", flush=True)
            try:
                accessible = find_visible_locator(accessible_selectors, timeout=5000)
                print(f"[Captcha] clicking accessible (小人) button", flush=True)
                accessible.click(force=True, timeout=5000)
                page.wait_for_timeout(2000)
            except Exception:
                print(f"[Captcha] accessible button not found, skipping", flush=True)

            try:
                retry_button = find_visible_locator(retry_selectors, timeout=25000)
                print(f"[Captcha] attempt {attempt+1}/{max_attempts}: found retry button (再次), clicking", flush=True)
                retry_button.click(force=True, timeout=5000)
            except Exception:
                try:
                    retry_button = find_visible_locator(press_selectors, timeout=10000)
                    print(f"[Captcha] attempt {attempt+1}/{max_attempts}: retry not found, clicking press button instead", flush=True)
                    retry_button.click(force=True, timeout=5000)
                except Exception as exc:
                    print(f"[Captcha] no retry/press button found: {exc}", flush=True)

            page.wait_for_timeout(8000)

            if (
                page.get_by_text('一些异常活动').count()
                or page.get_by_text('unusual activity').count()
                or page.get_by_text('此站点正在维护，暂时无法使用，请稍后重试。').count()
                or page.get_by_text('temporarily unavailable').count()
            ):
                print("[Error: Rate limit] - 正常通过验证码，但当前IP注册频率过快。")
                return False

            if page.get_by_text('取消').count() > 0 or page.get_by_text('Cancel').count() > 0:
                print(f"[Captcha] passed after press-and-hold on attempt {attempt+1}", flush=True)
                break
        else:
            raise Exception("加载超时或因触发机器人检测导致按压次数达到最大仍未通过")
        return True

'''
patchright = patchright[:captcha_start] + captcha_replacement + patchright[captcha_end:]
patchright_py.write_text(patchright, encoding="utf-8")

main_py = repo / "main.py"
main = main_py.read_text(encoding="utf-8")
main = main.replace(
    "token_result = get_access_token(page, email)",
    'print("[OutlookRegister] opening OAuth2 authorization", flush=True)\n        token_result = get_access_token(page, email, password)',
)
main_py.write_text(main, encoding="utf-8")

get_token_py = repo / "get_token.py"
get_token = get_token_py.read_text(encoding="utf-8")
if "import time\n" not in get_token:
    get_token = get_token.replace("import requests\n", "import requests\nimport time\n", 1)

old_handle_oauth = """def handle_oauth2_form(page, email):
    try:
        page.locator('[name="loginfmt"]').fill(email, timeout=20000)
        page.locator('#idSIButton9').click(timeout=7000)

        consent_btn = page.locator('[data-testid="appConsentPrimaryButton"]')
        consent_btn.wait_for(state='visible', timeout=20000)
        consent_btn.click(timeout=10000)
    except:
        pass
"""
new_handle_oauth = """def _first_visible(page, selectors, timeout=1000):
    deadline = time.time() + timeout / 1000
    last_error = None
    while time.time() < deadline:
        for selector in selectors:
            try:
                matches = page.locator(selector)
                if matches.count() <= 0:
                    continue
                locator = matches.nth(0)
                if locator.is_visible(timeout=200):
                    return locator
            except Exception as exc:
                last_error = exc
        page.wait_for_timeout(200)
    raise TimeoutError(f"no visible OAuth locator found: {selectors}; last_error={last_error}")

def _click_first(page, selectors, timeout=1000):
    try:
        _first_visible(page, selectors, timeout=timeout).click(timeout=3000, force=True)
        return True
    except Exception:
        return False

def handle_oauth2_form(page, email, password=None):
    deadline = time.time() + 45
    while time.time() < deadline:
        progressed = False

        if _click_first(page, [
            f'[data-test-id="{email}"]',
            f'[aria-label*="{email}"]',
            f'div:has-text("{email}")',
        ], timeout=700):
            progressed = True

        try:
            login = _first_visible(page, ['[name="loginfmt"]', 'input[type="email"]'], timeout=700)
            login.fill(email, timeout=3000)
            _click_first(page, ['#idSIButton9', 'button[type="submit"]', 'button:has-text("Next")', 'button:has-text("下一步")'], timeout=3000)
            progressed = True
        except Exception:
            pass

        if password:
            try:
                password_input = _first_visible(page, ['[name="passwd"]', 'input[type="password"]'], timeout=700)
                password_input.fill(password, timeout=3000)
                _click_first(page, ['#idSIButton9', 'button[type="submit"]', 'button:has-text("Sign in")', 'button:has-text("登录")'], timeout=3000)
                progressed = True
            except Exception:
                pass

        if _click_first(page, [
            '[data-testid="appConsentPrimaryButton"]',
            'button:has-text("Accept")',
            'button:has-text("Yes")',
            'button:has-text("Continue")',
            'button:has-text("接受")',
            'button:has-text("是")',
            'button:has-text("继续")',
            '#idSIButton9',
        ], timeout=700):
            progressed = True

        if not progressed:
            page.wait_for_timeout(500)
        else:
            page.wait_for_timeout(900)
"""
if old_handle_oauth in get_token:
    get_token = get_token.replace(old_handle_oauth, new_handle_oauth, 1)
elif "def handle_oauth2_form(page, email, password=None):" not in get_token:
    raise SystemExit("OutlookRegister get_token.py changed; missing OAuth form handler")

get_token = get_token.replace(
    "def get_access_token(page, email, max_retries=3):",
    "def get_access_token(page, email, password=None, max_retries=3):",
)
get_token = get_token.replace(
    "        result = _try_get_access_token(page, email)",
    "        result = _try_get_access_token(page, email, password)",
)
get_token = get_token.replace(
    "def _try_get_access_token(page, email):",
    "def _try_get_access_token(page, email, password=None):",
)
get_token = get_token.replace(
    """    code_verifier = generate_code_verifier()
    code_challenge = generate_code_challenge(code_verifier)
    params = {
        'client_id': client_id,
        'response_type': 'code',
        'redirect_uri': redirect_url,
        'scope': ' '.join(SCOPES),
        'response_mode': 'query',
        'prompt': 'select_account',
        'code_challenge': code_challenge,
        'code_challenge_method': 'S256'
    }
""",
    """    full_email = f"{email}{_email_suffix}"
    code_verifier = generate_code_verifier()
    code_challenge = generate_code_challenge(code_verifier)
    params = {
        'client_id': client_id,
        'response_type': 'code',
        'redirect_uri': redirect_url,
        'scope': ' '.join(SCOPES),
        'response_mode': 'query',
        'prompt': 'consent',
        'login_hint': full_email,
        'code_challenge': code_challenge,
        'code_challenge_method': 'S256'
    }
""",
)
get_token = get_token.replace(
    """            page.wait_for_timeout(250)
            page.goto(authorize_url, timeout=30000)
        except:
            return False, False, False

        handle_oauth2_form(page, f"{email}{_email_suffix}")
""",
    """            page.wait_for_timeout(250)
            print("[OutlookRegister] opening OAuth2 authorize page", flush=True)
            page.goto(authorize_url, timeout=30000, wait_until="domcontentloaded")
        except Exception as exc:
            print(f"[Error: OAuth2] - 无法打开授权页: {exc}", flush=True)
            return False, False, False

        print("[OutlookRegister] completing OAuth2 authorization", flush=True)
        handle_oauth2_form(page, full_email, password)
""",
)
get_token = get_token.replace(
    """        for i in range(400):
            page.wait_for_timeout(100)
            if captured_url:
                break

            if i > 0 and i % refresh_interval == 0:
                if refresh_count >= max_refreshes:
                    return False, False, False
                refresh_count += 1
                try:
                    page.reload(timeout=10000)
                except:
                    pass
        else:
            return False, False, False
""",
    """        for i in range(800):
            page.wait_for_timeout(100)
            if not captured_url and redirect_url in page.url and 'code=' in page.url:
                captured_url = page.url
            if captured_url:
                break

            if i > 0 and i % 30 == 0:
                handle_oauth2_form(page, full_email, password)

            if i > 0 and i % refresh_interval == 0:
                if refresh_count >= max_refreshes:
                    print("[Error: OAuth2] - 授权页等待超时，未捕获 code。", flush=True)
                    return False, False, False
                refresh_count += 1
                try:
                    page.reload(timeout=10000)
                except:
                    pass
        else:
            print("[Error: OAuth2] - 授权页等待超时，未捕获 code。", flush=True)
            return False, False, False
""",
)
get_token = get_token.replace(
    """        if 'refresh_token' in response.json():
            tokens = response.json()
""",
    """        tokens = response.json()
        if 'refresh_token' in tokens:
""",
)
get_token_py.write_text(get_token, encoding="utf-8")

utils_py = repo / "utils.py"
utils = utils_py.read_text(encoding="utf-8")
utils = utils.replace(
    "import string\nimport secrets\n",
    "import string\nimport secrets\nimport re\nfrom faker import Faker\n",
    1,
)
old_random_email = """def random_email(length=random.randint(12,14)):

    first_char = random.choice(string.ascii_lowercase)

    other_chars = []
    for _ in range(length - 1):
        if random.random() < 0.07:
            other_chars.append(random.choice(string.digits))
        else:
            other_chars.append(random.choice(string.ascii_lowercase))

    return first_char + ''.join(other_chars)
"""
new_random_email = """_fake = Faker("en_US")

def _email_name_part(value):
    return re.sub(r"[^a-z0-9]", "", value.lower())

def random_email(length=None):
    # Generate a human-looking local part, e.g. emilywalker482.
    for _ in range(20):
        first = _email_name_part(_fake.first_name())
        last = _email_name_part(_fake.last_name())
        if first and last:
            suffix = str(random.randint(10, 9999))
            candidates = [
                f"{first}{last}{suffix}",
                f"{first[0]}{last}{suffix}",
                f"{first}{last[0]}{suffix}",
            ]
            candidate = random.choice(candidates)
            if length:
                candidate = candidate[:max(6, int(length))]
            return candidate[:30]

    fallback_length = int(length) if length else random.randint(12, 14)
    first_char = random.choice(string.ascii_lowercase)
    other_chars = [
        random.choice(string.digits if random.random() < 0.07 else string.ascii_lowercase)
        for _ in range(fallback_length - 1)
    ]
    return first_char + ''.join(other_chars)
"""
if old_random_email not in utils:
    raise SystemExit("OutlookRegister utils.py changed; missing random_email block")
utils = utils.replace(old_random_email, new_random_email, 1)
utils_py.write_text(utils, encoding="utf-8")
