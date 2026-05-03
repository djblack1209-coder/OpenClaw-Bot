# Frist-API 快速启动

> 日期: 2026-05-03
> 范围: 可小范围开放测试的网站、轻量中转后端、隐藏管理端、Docker 部署入口

## 当前定位

Frist-API 是独立公开网站，放在 `apps/frist-api/`，不改 OpenClaw APP 现有 New API 页面。它只做注册、登录、改密、充值/入账、发 Key、计费、用量统计、CC Switch 导入和上游号源中转，不使用服务器本地硬件做模型推理。

当前公网验收入口:

- HTTPS 用户端: `https://pending-tractor-floating-fashion.trycloudflare.com/`
- HTTPS API 网关: `https://pending-tractor-floating-fashion.trycloudflare.com/v1`
- HTTP 兼容入口: `http://101.43.41.96:5566/`

当前 HTTPS 入口使用服务器已安装的 Cloudflare Quick Tunnel，浏览器证书可信，适合今晚外部实测。它不是长期品牌域名，进生产时仍建议绑定自有域名到现有 Cloudflare Tunnel 或 DNS，再把 `FRIST_API_PUBLIC_GATEWAY_BASE_URL` 切到固定域名。

管理端不公开展示。普通 `/admin.html` 在公网会返回 404。日常用法是先注册/登录自己的用户账号，在右上角账户区域输入一次性管理员身份码，当前账号会升级为管理员，身份码随即作废；升级后账户区域会出现运营入口，管理 API 也会直接识别当前登录态。隐藏入口码和管理员令牌仍保留为服务器后备方案，不给普通用户展示。

人工收款、固定域名、SMTP、Turnstile 和正式支付接口的操作清单见 `docs/024-frist-api-operator-runbook.md`。

无域名阶段这是临时 HTTP 验收地址。正式开放陌生付费用户前，必须绑定域名、HTTPS、SMTP/找回密码、Turnstile、真实支付回调、管理员 2FA 和数据库备份。

## 用户端能看到什么

用户端是低密度商业网站，不再是高密度管理后台。

- 首页只保留余额、模型消耗、Claude/OpenAI 连通性和三个直接入口: API Key、充值、CC Switch。
- 广场页面提供模型下拉选择、对话窗口和“实测连通”按钮，文字模型走聊天网关，`gpt-image-2` 等图片模型走图片生成网关，并在页面显示成功/失败、耗时和返回摘要。
- 数据看板展示模型消耗分布、消耗列表和服务可用性，不展示上游渠道或库存细节。
- 模型广场展示可用模型、模型家族、用途、上下文和计价，价格口径用客户能理解的销售展示文案。
- 使用教程展示 Codex、Claude、OpenClaw 的 JSON/TOML 配置，并提供 macOS/Windows 一键配置命令。
- 未登录游客页只显示 0 余额、0 消耗和 0 调用，不再用演示账单填空。
- 注册、登录和改密只在右上角账户菜单里，不放进 API 页面正文；公开模式下注册/登录会先做轻量验证码挑战和 IP 频率限制。
- API 页面只处理创建 Key、开关 Key、复制 Key 和请求地址。
- 创建 Key 时可选择模型分组: Claude、OpenAI、Other 或 All；分组不匹配的模型会在网关层拦截。
- 充值页面只展示日卡、月卡、余额和兑换码，充值卡片只保留类型与金额。
- CC Switch 页面让用户选择 Claude、Codex、OpenCode、OpenClaw、Hermes，并生成一键导入链接。
- 手动配置里提供 `auth.json` 和 `config.toml`，适配 Codex、OpenCode 等兼容 OpenAI Responses 格式的客户端。
- 导入配置统一写入 Frist-API 供应商标识、官网入口、公开网关地址、用户 `fk-live-*` Key、Responses 接口格式、`xhigh` 推理强度、上下文窗口、自动压缩、`setCacheKey` 和工具搜索配置，不暴露上游号商信息。
- 用户端不展示补号助手、上游号商、价格解析、渠道、倍率、模型映射和库存。运营入口只会在当前账号完成一次性管理员身份码激活后出现。

## 管理端能做什么

管理端独立在隐藏入口后。推荐方式是用一次性管理员身份码把你的账号升级为管理员，然后通过账户区域的运营入口进入；管理员令牌只作为后备方式保留在服务器环境变量里，不写入仓库和公开文档。

- 人工入账: 按用户邮箱确认日卡、月卡或余额充值。
- 补号助手: 可直接粘贴订单详情，也可手动输入请求地址、可选代理地址、池子、模型、价格文本和一批上游 Key。
- 备用渠道: CPA JSON、chong 和其他人工备用渠道只能在管理端登记；默认进入隔离态，必须人工核验并勾选确认后才会进入路由。
- 订单清洗: 自动识别请求地址、卡密、日卡/月卡/不限时、额度、数量、创建时间、到期时间、模型、认证字段、认证前缀和额外请求头。
- 自动探测: 同一请求地址优先探测一次模型列表；每枚 Key 做最低成本健康检查，图片模型会走 `/images/generations` 探测，不再误用聊天接口。
- fallback 探测: 上游不支持 `/models` 时，按内置模型清单逐个低成本探测，只写入可用模型。
- 直连/代理择优: 对直连和代理路径做低成本检测，选择成功率更高且延迟更低的 `routeBaseUrl`。
- 价格草稿: 粘贴美元或人民币价格文本后，自动换算销售价并参与网关扣费。
- 库存审计: 展示脱敏库存、补号、切换、耗尽、失败、浪费估算和路由事件。
- 低库存告警: 库存低于阈值时触发 `FRIST_API_LOW_INVENTORY_WEBHOOK`，后续可桥接 OpenClaw 的 Telegram/微信通知。

管理端不会把原始上游 Key、管理员令牌或号商细节带到用户端。

## 业务链路

用户链路:

1. 用户打开 Frist-API，右上角注册或登录，并完成轻量验证码挑战。
2. 用户选择日卡、月卡或余额，提交充值申请；公开环境默认不会自动给用户加钱。
3. 管理员通过隐藏入口进入管理端，按邮箱人工确认入账，或用户使用一次性兑换码。
4. 用户进入 API 页面选择模型分组并创建 `fk-live-*` Key。
5. 用户可以开启/关闭 Key，复制请求地址。
6. 用户进入 CC Switch 页面选择 Claude、Codex、OpenCode、OpenClaw 或 Hermes。
7. 页面生成 `ccswitch://v1/import` 一键导入链接，也提供 `auth.json` 和 `config.toml`。
8. 客户端使用 `https://pending-tractor-floating-fashion.trycloudflare.com/v1` 和用户 Key 调用模型。

管理员首登链路:

1. 先按普通用户流程注册、登录、创建 Key 和导入 CC Switch，确认用户链路没问题。
2. 回到右上角账户菜单，在身份码输入框粘贴一次性管理员身份码。
3. 点击激活后，当前账号会获得管理员权限，身份码立即失效。
4. 账户菜单显示运营入口后，点击进入管理页；同一浏览器登录态可直接加载库存、人工入账和补号功能。

网关链路:

1. `/v1/models` 只返回健康库存中的客户安全模型；广场常用别名会先清洗为官方库存名，例如 `5.5` -> `gpt-5.5`、`image2` -> `gpt-image-2`。
2. `/v1/chat/completions`、`/v1/responses` 和 `/v1/images/generations` 使用用户 `fk-live-*` 鉴权。
3. 网关先检查用户余额和套餐额度，余额不足时不访问上游。
4. 请求成功后优先按上游 `usage` 精确扣费；流式请求按预估消耗先扣费。
5. 客户端传 `x-frist-session-id`、`x-conversation-id` 或 `metadata.frist_session_id` 时，同一会话优先固定到同一枚健康上游 Key。
6. 库存消耗顺序是小时卡、日卡、月卡、不限时、默认池；同池内优先用更早到期、延迟更低的 Key。
7. 日卡 Key 额度不足、上游余额不足、上游 5xx 或网络失败时，网关摘除当前 Key，清掉会话粘滞记录，并带着完整请求体切到下一枚健康 Key。
8. 日卡到期后，网关路由前清空套餐额度并切回默认套餐。

## 本地运行

```bash
make frist-api-dev
```

打开:

```text
http://127.0.0.1:3180
http://127.0.0.1:3180/admin.html
```

本地如果设置了 `FRIST_API_ADMIN_PAGE_CODE`，管理页也会走隐藏入口；公网环境必须设置。

本地测试:

```bash
make frist-api-test
```

当前回归覆盖 103 条，包括:

- 用户注册、登录、改密、验证码挑战、认证限流、充值申请、管理员入账、兑换码、创建 Key、开启/关闭 Key 和 CC Switch 导入。
- 广场模型对话、`5.5` / `image2` 别名清洗、广场连通实测、图片生成模型路由、图片模型补号探测、模型消耗分布、服务可用性、模型广场和使用教程页面接线。
- 五个导入目标: Claude、Codex、OpenCode、OpenClaw、Hermes。
- Codex/OpenCode 的 `auth.json`、`config.toml`、Responses 接口格式、上下文压缩、`setCacheKey` 和工具搜索配置生成。
- Codex 的 `config.toml` 默认写入 Playwright、Superpowers、open-computer-use MCP；Computer Use 第一次实际使用时仍需要用户按系统提示完成本机权限授权。
- Codex、Claude、OpenClaw 的 macOS/Windows 一键配置命令生成，并验证不携带上游号商字段。
- 用户端禁止出现管理端、补号、价格、号源、渠道写入等内容。
- 用户端无左侧导航、无 sticky、无旧版高密度分组文字。
- 公开 HTML 初始值和游客 Dashboard 不闪现演示套餐、演示金额或演示用户。
- 管理员一次性身份码升级、管理端隐藏入口、订单文本清洗、认证字段清洗、代理择优、fallback 模型探测、价格文本扣费。
- CPA JSON/chong 备用渠道人工风控: 隔离态不出现在 `/v1/models`，不触发上游调用；人工放行后才可作为备用库存路由。
- 日卡自动切换、会话粘滞、故障切换上下文保留、流式 SSE 透传。
- 图片生成请求使用同一套用户 Key、日卡库存、上游故障切换和扣费链路。
- OpenCode `/openai/chat/completions` 前缀路由、Chat Completions 到 Responses 降级、OpenCode `models` 对象映射、可复制 provider 片段，以及 Codex/OpenCode 完整模型清单导出。
- CC Switch 3.14.1 深链导入 OpenCode 时可能只写默认模型；遇到这种情况，使用页面上的“OpenCode 完整配置”复制 provider 片段，并合并到 `~/.config/opencode/opencode.json` 的 `provider`。
- 小时卡、日卡、月卡、不限时库存优先级和低库存通知钩子。
- 公开模式拒绝默认管理员令牌、默认会话密钥、验证码回显、演示充值和本地 HTTP 网关地址。

## Docker 原型

```bash
docker compose -f docker-compose.frist-api.yml up -d
```

当前 Docker 原型使用 `node:22-alpine` 跑轻量 Frist-API 后端，内存限制 256MB，适配 2 核 2GB 的小服务器。运行数据默认写入 `data/frist-api/runtime/runtime.json`，该文件可能包含用户 Key 和上游 Key，不能提交到 Git。

生产环境必须设置:

- `FRIST_API_ADMIN_TOKEN`: 强随机管理员令牌
- `FRIST_API_ADMIN_PAGE_CODE`: 隐藏管理入口码
- `FRIST_API_ADMIN_CLAIM_CODES`: 一次性管理员身份码，逗号分隔；每个码成功使用后自动失效
- `FRIST_API_SESSION_SECRET`: 强随机会话密钥
- `FRIST_API_PUBLIC_MODE=1`
- `NODE_ENV=production`
- `FRIST_API_ALLOW_DEMO_RECHARGE=0`
- `FRIST_API_EXPOSE_VERIFICATION_CODE=0`
- `FRIST_API_REQUIRE_CAPTCHA=1`
- `FRIST_API_AUTH_RATE_LIMIT_MAX=20`
- `FRIST_API_LOW_INVENTORY_WEBHOOK`: 可选，低库存通知 Webhook

无域名公网 IP 验收时可临时设置 `FRIST_API_ALLOW_INSECURE_PUBLIC_HTTP=1`。当前 Cloudflare HTTPS 入口已关闭这个临时开关。

冒烟检查:

```bash
apps/frist-api/deploy/smoke-test.sh http://127.0.0.1:3180 "$FRIST_API_ADMIN_PAGE_CODE"
```

## 当前限制

- 仍使用 JSON 运行数据，适合小范围验收；扩大公开前要迁移 SQLite/PostgreSQL 或 New-API fork 数据库。
- 已有轻量验证码、认证限流和一次性管理员身份码，但未接 SMTP、找回密码、Turnstile、真实支付回调、管理员 2FA。
- 补号探测已做低成本可用性判断、Responses fallback、直连/代理择优和认证字段清洗，但未做完整上下文上限、工具调用、流式能力和模型质量评分。
- CPA JSON/chong 入口只做人工登记和放行，不包含 OAuth Session 提取、Refresh Token 刷新、账号池规避风控或自动化批量获取逻辑。
- `QuantumNous/new-api` 是 AGPL-3.0，公开二开运营时必须准备源码公开入口或公开 fork。

## 下一步

1. 绑定域名和 HTTPS，关闭临时公网 HTTP 开关。
2. 接 SMTP/找回密码/Turnstile、管理员 2FA、真实支付回调和订单审计。
3. 把 JSON 运行数据迁移到 SQLite/PostgreSQL 或 New-API fork 数据库。
4. 给补号探测加并发上限、预算上限和后台队列。
5. 做价格草稿确认、版本回滚和亏损预警。
6. 准备 AGPL-3.0 合规源码公开入口。
