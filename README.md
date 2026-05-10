# NB Register

本项目用于本地编排账号注册、Outlook 邮件 OTP、GoPay 支付和工作流看板。

> 使用本项目即表示接受 [NOTICE.md](NOTICE.md)。本项目仅限授权研究、内部实验、协议分析、CTF/安全研究和教学验证，严禁商业化运营、账号批量生产或转售、代注册、代充值、规避支付、欺诈、未授权自动化，或任何违反第三方服务条款及适用法律法规的活动。

支付和浏览器自动化相关实现参考并感谢 [DanOps-1/Gpt-Agreement-Payment](https://github.com/DanOps-1/Gpt-Agreement-Payment)。

根仓统一管理 compose、共享 proto 和各服务目录：`account-db`、`browser-reg`、`dashboard`、`gopay-payment`、`orchestrator`、`outlook-imap-service`。

## 快速启动

```bash
cp compose.example.env compose.env
```

编辑 `compose.env` 顶部的用户配置项。通常只需要改这些：

```env
REGISTER_PROXY_URL=socks5://host.docker.internal:10813

GOPAY_COUNTRY_CODE=62
GOPAY_PHONE_NUMBER=
GOPAY_PIN=
GOPAY_PROXY_URL=socks5://host.docker.internal:10813
```

启动：

```bash
docker compose --env-file compose.env build camoufox-base
docker compose --env-file compose.env up -d --build
```

打开看板：

```text
http://127.0.0.1:8080
```

健康检查：

```bash
curl -fsS http://127.0.0.1:8080/api/health
```

## 配置说明

`compose.example.env` 已按使用频率分层：

- `User settings`：首次运行必须确认，包含注册代理、可选 OutlookRegister 邮箱池、GoPay 手机号/PIN/代理。
- `Optional host ports`：默认即可，只有本机端口冲突时再改。
- `Stable defaults`：内部服务地址、数据库、Temporal、OTP 等待时间等，正常不要改。

真实值只写入 `compose.env`。`compose.env`、token、日志、抓包、浏览器状态和数据库数据都不会入库。

## Outlook 邮件服务

`outlook-imap-service` 是单个 Python gRPC 服务，同时负责邮箱分配、OAuth token 刷新和收信。邮箱元数据写入 PostgreSQL 的 `mailboxes` 表，字段包含邮箱、密码、状态、主邮箱标记、所属主邮箱和错误信息；邮箱服务不保存 OpenAI 账号绑定关系。

分配规则：

- 优先返回 `AVAILABLE` 的主邮箱。
- 主邮箱注册成功后状态变为 `REGISTERED`，后续可从该主邮箱生成 plus alias。
- 邮箱被标记为 `USER_ALREADY_EXISTS` 时，对应主邮箱会变为 `BLOCKED`，后续不再从这个主邮箱分裂。

每个主邮箱需要一条可用的 Microsoft OAuth refresh token。可以通过 OutlookRegister 自动产出账号信息后由 orchestrator 导入，也可以在看板「邮箱管理」里手动添加邮箱和密码后点击「补 OAuth」自动补齐。底层也保留 `EmailService.UpsertMailbox` gRPC 接口用于脚本写入。

如需使用自己在 Azure 注册的应用，可在 `compose.env` 覆盖：

```env
OUTLOOK_OAUTH_CLIENT_ID=
OUTLOOK_OAUTH_SCOPE=https://graph.microsoft.com/Mail.Read
```

服务会按 PG 中状态为 `AVAILABLE`、`ASSIGNED`、`REGISTERED` 且带 refresh token 的主邮箱轮询 Outlook 全邮箱消息；refresh token 刷新后会回写 `mailboxes` 表。认证失败会标记为 `AUTH_FAILED`。

### OutlookRegister 邮箱池

`outlook-register-service` 内置 [LainsNL/OutlookRegister](https://github.com/LainsNL/OutlookRegister) 执行器，只负责注册/OAuth 并通过 gRPC 返回成功账号信息。它不连接 PostgreSQL，也不调用 `outlook-imap-service`；邮箱池导入由 orchestrator 调用 `EmailService.UpsertMailbox` 完成。`outlook-imap-service` 只负责邮箱池、Graph token 存储和取信/取码。

先在 `compose.env` 填写 OutlookRegister 参数，至少需要：

```env
OUTLOOK_REGISTER_PROXY=socks5://host.docker.internal:10810
OUTLOOK_REGISTER_ENABLED=false
OUTLOOK_REGISTER_BROWSER=patchright
OUTLOOK_REGISTER_EMAIL_SUFFIX=@outlook.com
OUTLOOK_REGISTER_ENABLE_OAUTH2=true
OUTLOOK_REGISTER_OAUTH_SCOPES=offline_access https://graph.microsoft.com/Mail.Read
OUTLOOK_REGISTER_MAX_TASKS=1
OUTLOOK_REGISTER_CONCURRENT_FLOWS=1
OUTLOOK_REGISTER_MANUAL_CAPTCHA=false
OUTLOOK_REGISTER_MANUAL_CAPTCHA_TIMEOUT_SECONDS=300
OUTLOOK_REGISTER_LOCK_WAIT_SECONDS=0
```

`OUTLOOK_REGISTER_OAUTH_CLIENT_ID` 和 `OUTLOOK_REGISTER_OAUTH_REDIRECT_URL` 默认复用邮件服务内置 public client 配置；正常不用填。只有你要换自己的 Azure 应用时才覆盖。

运行一次邮箱池补充：

```bash
docker compose --env-file compose.env exec -T -e OUTLOOK_REGISTER_ENABLED=true -e OUTLOOK_REGISTER_INTERVAL_SECONDS=0 outlook-register-service python /app/register_provider.py run
```

注册服务返回从结果文件收集到的账号信息；如果没有新账号，`RunMailboxRegistration` 会返回失败，不再把空结果当成功。orchestrator 收到账号后负责导入邮箱池：带 refresh token 的邮箱标记为 `AVAILABLE`，只有账号密码但没有 refresh token 的邮箱会导入为 `AUTH_FAILED` 并保留错误说明，避免被注册流程误取为可用邮箱。注册器强制 `OUTLOOK_REGISTER_MAX_TASKS=1` 和 `OUTLOOK_REGISTER_CONCURRENT_FLOWS=1`，并用文件锁保证同一时间只有一个注册进程；重复触发默认直接失败并返回锁错误。

邮箱前缀会用 Python `Faker("en_US")` 生成英文名/姓并追加数字后缀，例如 `adamdiaz4168@outlook.com`，避免纯随机字母串。

验证码默认走源仓自动流程；`OUTLOOK_REGISTER_MANUAL_CAPTCHA=true` 仅作为本地调试 fallback。

看板「邮箱管理」里的「手动注册邮箱」按钮会调用 orchestrator 的 `RegisterMailbox` RPC，由 Temporal workflow 编排 `outlook-register-service` 注册账号，再由 orchestrator 导入邮箱池，不再需要 dashboard 挂 Docker socket 或执行宿主机命令；邮箱列表、状态、取码仍由 `outlook-imap-service` 提供。

注册过程日志：

```bash
docker compose --env-file compose.env logs -f dashboard
docker compose --env-file compose.env logs -f orchestrator
tail -f outlook-register-service/register-results/register.log
```

## GoPay OTP

GoPay payment 内置 OTP webhook。手机端通知转发工具把收到的 GoPay OTP POST 到：

```text
http://<本机局域网 IP>:8081/webhook/otp
```

本机测试：

```bash
curl -X POST http://127.0.0.1:8081/webhook/otp \
  -H 'Content-Type: application/json' \
  -d '{"otp":"123456","source":"phone"}'
```

也支持纯文本 payload。

GoPay 支付参数来自容器环境变量，不从 gRPC 请求传入：

```env
GOPAY_COUNTRY_CODE=62
GOPAY_PHONE_NUMBER=
GOPAY_PIN=
GOPAY_PROXY_URL=socks5://host.docker.internal:10813
```

## 看板操作

在 `http://127.0.0.1:8080` 可以执行：

- 创建账号：可不填邮箱/密码；邮箱会从邮箱池领取，密码会随机生成。
- 邮箱池：先把你持有且可收 OTP 的主邮箱和密码加入邮箱池，点击「补 OAuth」获取 refresh token；创建账号不填邮箱时会向邮箱服务领取。
- 注册账号：触发 `browser-reg`，默认最多等待 180 秒获取 Outlook 邮件 OTP；如果邮箱服务没取到码，可以在「工作流详情」对运行中的注册 job 手动提交 OTP。
- 激活账号：使用账号 session token / access token 触发 GoPay 支付，等待 GoPay OTP webhook 回传。
- 注册并激活：按顺序执行注册和支付。
- 账号详情：查看/隐藏账号密码，修改 session token。
- 工作流详情：查看 job 状态、步骤、错误和结果摘要。

账号有运行中的 job 时，行内操作会显示“进行中”并禁止重复触发。

## 常用命令

查看服务：

```bash
docker compose --env-file compose.env ps
```

查看日志：

```bash
docker compose --env-file compose.env logs -f orchestrator
docker compose --env-file compose.env logs -f browser-reg
docker compose --env-file compose.env logs -f gopay-payment
docker compose --env-file compose.env logs -f outlook-imap-service
```

重启单个服务：

```bash
docker compose --env-file compose.env restart dashboard
```

重建单个服务：

```bash
docker compose --env-file compose.env up -d --build dashboard
```

停止：

```bash
docker compose --env-file compose.env down
```

## 开发检查

```bash
./scripts/generate-proto.sh
(cd account-db && go test ./...)
(cd orchestrator && go test ./...)
(cd dashboard && go test ./...)
(cd outlook-imap-service && python3 -m py_compile email_service.py)
(cd outlook-register-service && python3 -m py_compile register_service.py register_provider.py camoufox_register.py)
(cd dashboard/web && npm run build)
docker compose --env-file compose.example.env config --quiet
```

## 赞赏

<img src="assets/zan.jpg" alt="赞赏码" width="240">
