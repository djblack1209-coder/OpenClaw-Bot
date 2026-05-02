# Frist-API 腾讯云部署准备

> 日期: 2026-05-02
> 范围: 2 核 2GB Ubuntu Server 22.04 小服务器公开试用部署

## 安全边界

- 不把服务器 IP、root 密码、管理员令牌、上游 Key 写入仓库。
- 生产只使用强随机 `FRIST_API_ADMIN_TOKEN` 和 `FRIST_API_SESSION_SECRET`。
- 生产必须设置 `FRIST_API_ADMIN_PAGE_CODE`；公网普通 `/admin.html` 应返回 404，只能通过隐藏入口码加载静态管理页。
- 生产建议同时设置 `FRIST_API_ADMIN_CLAIM_CODES`，用于把你自己的登录账号升级成管理员；一次性码成功使用后会自动失效。
- 生产必须设置 `NODE_ENV=production` 和 `FRIST_API_PUBLIC_MODE=1`；如果仍使用默认令牌、验证码回显、演示充值或本地 HTTP 网关地址，服务会拒绝启动。
- 没有域名和 HTTPS 时，可以临时设置 `FRIST_API_ALLOW_INSECURE_PUBLIC_HTTP=1` 做公网 IP 验收；这只适合测试，不适合正式付费用户。
- 当前公网 HTTPS 实测使用 Cloudflare Quick Tunnel: `https://pending-tractor-floating-fashion.trycloudflare.com/`，证书可信但入口不是长期品牌域名。
- 生产保持 `FRIST_API_ALLOW_DEMO_RECHARGE=0` 和 `FRIST_API_EXPOSE_VERIFICATION_CODE=0`，不要开放演示充值或验证码回显。
- 生产保持 `FRIST_API_REQUIRE_CAPTCHA=1` 和认证频率限制，避免注册登录被批量撞库。
- 容器默认绑定 `127.0.0.1:3180`，公网正式使用时只开放 HTTPS 反向代理；无域名临时验收可额外映射一个测试端口。
- `data/frist-api/runtime/runtime.json` 会包含用户 Key 和上游 Key，必须保持未跟踪并定期备份。
- 多项目服务器不要直接抢占 80/443 的默认站点。Frist-API 在无正式域名阶段只使用独立测试端口或 Cloudflare Tunnel；绑定正式域名后再把该域名反代到 `http://127.0.0.1:3180`。

## 服务器策略

这台服务器配置较小，Frist-API 只能做中转、鉴权、计费、日志和轻量探测，不做本地模型推理。

建议运行方式:

1. Docker Compose 跑 Frist-API Node 服务，内存限制 256MB。
2. Nginx 或 Caddy 负责 HTTPS、域名、gzip 和静态缓存。
3. 管理端只允许 HTTPS 访问，并尽快加正式登录和 2FA。日常建议先用一次性管理员身份码升级自己的账号，再把运营入口藏到右上角账户菜单里。
4. 补号探测保留超时和并发控制，不做高成本批量模型评测。
5. 上游优先从号源直接调用；如果直连慢或失败率高，管理端可填写代理请求地址，系统会在补号时自动择优。
6. 用户请求成功后按上游 `usage` 和管理端价格草稿扣费；上游不返回 `usage` 时才用保守估算价。
7. 客户端应带 `x-frist-session-id` 或请求体 `metadata.frist_session_id`；同一会话会固定到同一枚健康上游 Key，坏号切换时完整保留原始上下文请求体。
8. `stream: true` 会透传上游 SSE 流；流式请求按预估值先扣费，非流式请求优先按上游 `usage` 精确扣费。
9. 库存按小时卡、日卡、月卡、不限时、默认池顺序消耗，优先减少限时卡浪费。
10. 低库存通知通过 `FRIST_API_LOW_INVENTORY_WEBHOOK` 输出，可桥接 OpenClaw 的 Telegram/微信通知服务。

## 部署步骤

1. 安装 Docker 和 Compose 插件。
2. 拉取或同步当前仓库到服务器。
3. 在服务器本机创建环境文件，参考 `apps/frist-api/deploy/production.env.example`。
4. 设置强随机值:

```bash
openssl rand -base64 48
```

5. 启动服务:

```bash
docker compose -f docker-compose.frist-api.yml --env-file apps/frist-api/deploy/production.env up -d
```

6. 运行冒烟检查:

```bash
apps/frist-api/deploy/smoke-test.sh http://127.0.0.1:3180
```

如果设置了隐藏管理入口码，冒烟脚本应传入第二个参数:

```bash
apps/frist-api/deploy/smoke-test.sh http://127.0.0.1:3180 "$FRIST_API_ADMIN_PAGE_CODE"
```

7. 配置 Nginx/Caddy，把公网域名反代到 `http://127.0.0.1:3180`。

临时公网验收可以叠加一个独立 Compose 覆盖文件，把服务器测试端口映射到容器 `3180`。验收结束或绑定域名后应关闭该端口，只保留 HTTPS 入口。

当前服务器直签动态 IP 域名时遇到两个外部限制: `sslip.io` / `nip.io` / `traefik.me` 在 Let’s Encrypt 校验侧出现 DNSPod 拦截、80 端口超时或旧 certbot webroot 空挑战问题。已改用服务器现有 `cloudflared` 创建 HTTPS Quick Tunnel，生产域名建议在 Cloudflare 后台把固定域名映射到 `http://127.0.0.1:3180`。

如果浏览器访问测试入口出现 `ERR_CONNECTION_REFUSED`，先按下面顺序查:

1. `docker ps` 确认 `frist-api-server` 为 `healthy`。
2. `ss -ltnp` 确认容器只监听 `127.0.0.1:3180`，这是安全设计，不是故障。
3. `nginx -T` 或查看 `/etc/nginx/conf.d/frist-api.conf`，确认 Nginx 是否监听当前测试端口并反代到 `http://127.0.0.1:3180`。
4. `curl -sS -D - http://127.0.0.1:3180/ -o /tmp/frist-local.html` 验证容器本地入口。
5. `curl -sS -D - http://127.0.0.1:<测试端口>/ -o /tmp/frist-nginx.html` 验证 Nginx 入口。
6. 从本机外网跑 `apps/frist-api/deploy/smoke-test.sh http://<公网测试入口>`。

本次裸 IP 访问失败的根因就是 Nginx 没有监听 Frist-API 测试端口，而容器按安全策略只暴露本地端口。修复方式是保留容器本地绑定，在 Nginx 增加独立测试端口监听并反代到 `127.0.0.1:3180`。

## 上线前检查

- 用户端能打开 `/`。
- 普通 `/admin.html` 返回 404；登录账号输入一次性管理员身份码后能看到运营入口，并能用同一浏览器登录态加载库存。隐藏入口码和管理员令牌只作为后备方式验证。
- 用户能完成验证码、注册、登录、改密、兑换、提交充值申请、创建 Key、生成 CC Switch 导入链接。
- 管理端能按邮箱人工确认充值入账。
- 管理端能粘贴订单详情补日卡/月卡/不限时库存，坏 Key 被过滤或标记失败。
- 订单详情里的上游请求地址、认证字段、额外请求头、模型、额度和到期时间能被清洗成脱敏库存。
- CC Switch 导入只出现 Frist-API 供应商标识、官网入口、用户 Key 和公开网关，不出现上游号商地址或上游 Key。
- 管理端填写代理请求地址后，库存记录会展示直连或代理标签，网关会按择优后的路径转发。
- 上游不支持 `/models` 时，系统会按内置模型清单做低成本探测，只写入探测通过的模型。
- 管理端粘贴价格文本后，用户真实请求会按上游返回的 `usage` 扣减套餐额度、加油包额度和上游库存额度。
- 用户用 `fk-live-*` 调 `/v1/chat/completions` 后，额度会扣减。
- 带同一个 `x-frist-session-id` 连续调用时，补入更快 Key 后当前对话仍走原健康 Key。
- 上游 5xx 或余额不足触发切换时，备用 Key 收到的请求体仍包含完整 `messages`、`tools` 和 `metadata`。
- `stream: true` 请求能在上游首包返回后立即向客户端输出。
- 小时卡/日卡 Key 耗尽、上游 5xx 或网络失败时，会切到下一枚健康 Key，并在对应库存低于阈值时触发通知钩子。
- 日卡套餐到期后，套餐额度会清零并切回默认套餐，旧日卡不能继续走日卡池。
- 容器重启后数据仍存在。
- Docker 健康检查必须访问 `http://127.0.0.1:3180/`，不要用 `localhost`，避免 Alpine 先走 IPv6 `::1` 导致误报 `unhealthy`。
- 使用公网 IP 临时验收时，确认 `FRIST_API_ALLOW_INSECURE_PUBLIC_HTTP=1` 只出现在测试环境；绑定域名和 HTTPS 后要删掉。当前 Quick Tunnel HTTPS 部署已设置为 `0`。

## 仍需补齐

- SMTP 邮箱验证码和找回密码。
- Turnstile 防注册刷号；当前只有轻量算术验证码和认证限流。
- 管理员正式登录和 2FA。
- SQLite/PostgreSQL 持久化。
- 真实支付回调和订单审计。
- 自动备份、恢复演练和支付对账。
- 生产监控告警、错误率阈值和低库存升级通知。
- New-API AGPL 合规公开源码入口。
- 固定品牌域名和正式 Cloudflare Tunnel/DNS 规则；Quick Tunnel 只用于今晚外部可测入口。
