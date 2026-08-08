# CC中转 New-API 原生能力盘点与补齐路线

> 最后更新: 2026-07-05
> 目标: 先吃透并补齐 QuantumNous/new-api 已有能力，再把 CC Switch、闲鱼履约、86Game 渠道导入等自研功能作为轻集成叠加，避免重复造轮子。

---

## 一、当前结论

CC中转当前公网主入口已经切到 New-API 成熟面板。New-API 自带的能力已经覆盖“模型网关 + 用户体系 + API Key 管理 + 兑换码 + 渠道管理 + 模型定价 + 日志 + 钱包 + 订阅 + 系统设置”的大部分商业面板基础能力。

后续原则:

1. **New-API 已有的功能优先用原生**，例如兑换码、API Key、渠道管理、模型定价、日志、用户、订阅、支付、限流、安全设置。
2. **自研功能只做补强层**，不要替换 New-API 主业务表和主流程。
3. **不新增产品营销文案**，需要配置时优先使用 New-API 默认页面和现有表单；内部文档可以记录运营说明。
4. **正式售卖前先补生产安全项**，尤其 Turnstile、邮箱验证/找回、管理员强安全和渠道自动巡检。

---

## 二、New-API 已有能力清单

### 2.1 用户与认证

New-API 原生支持:

- 用户注册、登录、退出、改资料、删号
- 邮箱验证码、找回密码
- Turnstile 人机验证
- 用户 2FA/TOTP、备份码
- Passkey/WebAuthn
- OAuth: GitHub、Discord、OIDC、LinuxDO、Telegram、WeChat、自定义 OAuth
- 管理员创建/禁用/删除用户、调整用户额度、清理 OAuth/Passkey/2FA 绑定

当前生产状态:

- 注册/登录 API 已通过受控生产 E2E：临时关闭 Turnstile/邮箱验证后在 Oracle 本机直连完成成功路径，随后恢复生产安全门。
- 2026-07-05 已复用旧 JIYU AI 生产配置写入 New-API 原生设置: `turnstile_check=true`、`email_verification=true`；公网无 Turnstile 注册/登录返回 `Turnstile token 为空`。
- 旧 JIYU Turnstile 允许域名已包含 `jiyu.245334.xyz`，可继续复用。
- New-API 管理员/root 账户已复用旧 JIYU 管理员 TOTP secret，当前 `two_fas=2`。
- `passkey_login=false`
- OAuth 均未启用。
- 用户数 20。

补齐优先级:

- P0: Turnstile、SMTP、邮箱验证/找回密码已复用 JIYU 配置并启用；继续做真人浏览器验收。
- P0: 管理员账号 2FA 已复用 JIYU TOTP 配置启用。
- P1: Passkey 可作为可选增强，不作为售卖首发硬门槛。
- P2: OAuth 暂不启用，除非明确需要社交登录。

### 2.2 API Key 与用户控制台

New-API 原生支持:

- API Key 创建、列表、详情、取完整 Key、改名、改额度、禁用、恢复、删除
- Key 级模型限制、IP 白名单、分组、跨组重试
- 批量删除、批量取 Key
- Token 用量查询
- Dashboard、钱包、日志、个人资料、语言偏好
- 客户端导入入口: Cherry Studio、AionUI、流畅阅读、CC Switch、Lobe Chat、AI as Workspace、AMA、OpenCat 等

当前生产状态:

- 生产 E2E 已验证 Key 创建/更新/禁用/恢复/删除。
- `/v1/models` 返回 15 个模型。
- CC Switch 已在 `chats` 入口中出现；JIYU 轻集成已验证 `ccswitch:` provider 导入链接，endpoint 为 `https://jiyu.245334.xyz/v1`，同 Key 调模型 200，删除后 401。
- 活跃 Token 数 1，E2E 临时 Token 清理后为 0 残留。

补齐优先级:

- P0: 继续使用 New-API 原生 API Key 管理作为主流程；JIYU 运营台只做自动发货/CC Switch 轻集成，不替换 New-API Token 表。
- P1: CC Switch 只作为客户端导入增强，不另建 API Key 管理系统。
- P1: 如需“一键导出多客户端配置”，优先扩展 New-API 的 chat/client link 配置，不改 Token 主逻辑。

### 2.3 兑换码、钱包、充值、订阅

New-API 原生支持:

- 管理员生成兑换码、查看状态、搜索、更新、删除无效码
- 用户钱包兑换码充值
- TopUp 充值记录
- 邀请奖励、余额转移
- 订阅计划、用户订阅绑定、订阅订单
- 支付接口: Epay、Stripe、Creem、Waffo、Waffo Pancake
- 每日签到奖励

当前生产状态:

- 生产 E2E 已验证管理员创建兑换码、用户兑换到账；JIYU 运营台生成的卡密可同步到 New-API，并在闲鱼履约分配后随买家兑换回写状态。
- 兑换码表当前 2 条，`available_redemptions=0`。
- TopUp 记录 4 条。
- 订阅相关表存在，但还未作为主售卖路径使用。
- 支付网关未作为当前上线必备项。
- `checkin_enabled=false`。

补齐优先级:

- P0: 兑换码使用 New-API 原生 `redemptions` + `/api/user/topup`，不要再新建自研兑换码状态机作为主流程。
- P0: 正式开卖前建立 New-API 原生兑换码库存批次和导出规则。
- P1: 如果售卖“月包/套餐”，优先使用 New-API 原生订阅计划，不自研套餐表。
- P2: 自动支付等拿到商户后再启用；现阶段继续人工售卖兑换码。
- P2: 签到奖励默认不启用，避免内测期被薅羊毛。

### 2.4 渠道、模型、路由与价格

New-API 原生支持:

- 多渠道供应商: OpenAI、Claude、Gemini、OpenRouter、DeepSeek、Moonshot、通义、豆包、xAI、Mistral、Cohere、Cloudflare、Ollama、Replicate、Codex OAuth 等
- 渠道新增、编辑、复制、删除、批量管理、标签管理、多 Key 管理
- 渠道测试、全渠道测试、余额刷新、响应时间记录
- 拉取上游模型、上游模型变动检测/应用
- 模型映射、模型元数据、供应商元数据、价格页
- 模型倍率、分组倍率、缓存/图片/音频/工具价格、阶梯计费
- Channel affinity 粘性路由
- Codex OAuth 渠道开始/完成/刷新/用量

当前生产状态:

- 启用渠道 3 个。
- 模型元数据 15 条。
- 能力映射 22 条。
- 供应商元数据 2 条。
- 外网 E2E 已验证渠道刷新和 OpenAI/Claude 真实调用。

补齐优先级:

- P0: 渠道管理、模型映射、模型价格全部使用 New-API 原生。
- P0: 打开/校准 New-API 原生自动渠道测试、自动禁用/恢复规则。
- P1: 86Game Key 批量导入做成“导入器/适配器”，落到 New-API channels，不另建渠道系统。
- P1: 渠道倍率同步优先落到 New-API 模型倍率/分组倍率/上游同步，而不是自研价格表。
- P2: 多上游切换继续使用 New-API 渠道和分组能力。

### 2.5 网关协议与模型能力

New-API 原生支持:

- `/v1/models`
- `/v1/chat/completions`
- `/v1/responses`
- `/v1/responses/compact`
- `/v1/messages`
- `/v1/completions`
- `/v1/embeddings`
- `/v1/images/generations`
- `/v1/images/edits`
- `/v1/audio/speech`
- `/v1/audio/transcriptions`
- `/v1/audio/translations`
- `/v1/rerank`
- `/v1/moderations`
- `/v1/realtime`
- Gemini `/v1beta` 兼容接口
- Midjourney、Suno/视频任务接口
- Playground 测试台

当前生产状态:

- `/v1/models`、OpenAI Chat、Claude Chat 已通过。
- 绘图、音频、嵌入、rerank、MJ/Suno 未作为当前售卖主路径验证。

补齐优先级:

- P0: 首发只承诺已验证的 Chat/Claude/OpenAI 兼容模型。
- P1: 按上游真实支持情况逐步开放图片、音频、embedding、rerank。
- P2: MJ/Suno/视频任务暂不作为首发卖点。

### 2.6 日志、统计、监控、性能

New-API 原生支持:

- 管理员全站日志、用户日志、Token 日志
- 日志统计、用量统计、quota_data
- 性能指标、磁盘缓存、性能监控、GC、日志清理
- Uptime Kuma 面板
- 渠道自动测试、自动禁用/恢复、额度提醒
- Rankings、Pricing、Dashboard

当前生产状态:

- 日志 192 条。
- `enable_data_export=true`
- `api_info_enabled=true`
- `uptime_kuma_enabled=true`
- `announcements_enabled=true`
- `faq_enabled=true`
- 自动渠道测试具体策略仍需下一步校准。

补齐优先级:

- P0: 用 New-API 原生日志/用量作为客服排障和对账依据。
- P0: 校准渠道自动测试和自动禁用规则。
- P1: 接入 Uptime Kuma 或保留 JIYU 现有 readiness/备份监控作为补强。
- P1: 公共 FAQ/公告如果没有必要，不主动新增产品文案。

### 2.7 安全与风控

New-API 原生支持:

- 全局 API rate limit
- 模型请求 rate limit
- 搜索限流、关键操作限流、邮箱验证码限流
- 敏感词过滤
- SSRF 防护
- Secure Verification
- 2FA、Passkey、Turnstile

当前生产状态:

- 2026-07-05 已复用 JIYU AI 旧配置启用 New-API 原生 Turnstile、SMTP/邮箱验证和管理员 2FA。
- 公网注册/登录不带 Turnstile token 会返回 `Turnstile token 为空`。
- JIYU 旧入口曾有 Turnstile/2FA/readiness，但公网主入口切到 New-API 后，应优先补 New-API 原生安全配置。

补齐优先级:

- P0: New-API Turnstile、邮箱验证/找回密码、管理员 2FA 已启用；正式售卖前由老板做一次真人浏览器注册/登录/兑换验收。
- P0: 模型请求 rate limit，防止 Key 被撞库或无限刷。
- P1: SSRF 与敏感词按默认安全开启，不做激进拦截，避免误伤正常模型调用。

---

## 三、自研功能应该怎么接入

### 3.1 CC Switch

定位: 自研客户端/导入能力。

接入方式:

- 保持 New-API Token 为唯一 Key 来源。
- 使用 New-API 原生 `Chats` 配置展示 CC Switch 入口。
- 如需增强，仅扩展导入链接参数、客户端配置模板和可视化说明，不新建 Key 表。

### 3.2 86Game / 上游 Key 导入

定位: 渠道导入器。

接入方式:

- 读取老板提供的上游 baseURL/key。
- 探测模型与真实调用。
- 转换成 New-API channel / ability / model meta。
- 导入后交给 New-API 原生渠道测试、自动禁用、模型映射和日志处理。

不要做:

- 不再维护独立渠道库存表作为主路由。
- 不绕过 New-API relay 自己写转发。

### 3.3 闲鱼履约

定位: 安全发货辅助层，当前生产内测先走“人工确认已付款后一键发货”。

接入方式:

- 使用 New-API 原生兑换码作为卡密库存。
- 自研只做“已付款订单信息 → 分配未使用兑换码 → 复制发货话术 → 标记已发货/已分配”的辅助表或视图。
- 用户仍在 New-API 钱包/充值页兑换到账，兑换后状态回写，避免同一张卡重复发货。
- 当前优先接入 OpenClaw `XianyuLive`：由 WebSocket 订单事件识别“等待卖家发货/已付款”，调用 CC中转低权限 webhook 发卡并发送话术。浏览器插件只作为备用入口，只允许读取已付款订单并回填/发送同一条话术，不保存闲鱼 Cookie，不做主动营销动作。

不要做:

- 不自动砍价。
- 不批量私信。
- 不刷单。
- 不绕闲鱼风控。
- 不在没有明确“已付款”证据时自动发卡。
- 不另建主兑换码系统。

### 3.4 生产 readiness / 备份 / 运维

定位: 生产护栏。

接入方式:

- New-API 原生负责业务。
- 自研只做外围检查: 域名、HTTPS、服务状态、数据库备份、可用渠道数、真实模型调用、E2E 临时数据清理。
- 不改 New-API 主流程。

---

## 四、下一步执行优先级

### P0 — 先把 New-API 原生生产能力补齐

1. 配置 New-API Turnstile。
2. 配置 New-API SMTP、邮箱验证、找回密码。
3. 确认 root/admin 账号 2FA。
4. 校准模型请求 rate limit。
5. 校准渠道自动测试、自动禁用/恢复。
6. 建立 New-API 原生兑换码库存批次与导出 SOP。
7. 继续外网 E2E 覆盖注册、登录、兑换、创建 Key、模型调用、禁用 Key、渠道刷新。

### P1 — 原生商业化能力补齐

1. 补齐模型价格页、供应商元数据、分组倍率。
2. 如卖套餐，优先配置 New-API 订阅计划。
3. 用 New-API 钱包/TopUp/兑换码记录做售后对账。
4. 接入 Uptime Kuma 或保留现有 readiness 护栏。
5. 形成“管理员发码 → 用户兑换 → API Key → 调用模型”的标准操作视频/截图，不写进产品页面。

### P2 — 接入自研能力

1. CC Switch 导入增强。
2. 86Game 批量导入器。
3. 闲鱼履约辅助台。
4. 渠道倍率同步自动化。
5. 多上游质量评分和补货提醒。

---

## 五、2026-07-05 生产只读审计结果

本节是对 `https://jiyu.245334.xyz` 当前生产内测环境的只读审计，不改配置、不打印密钥。

### 5.1 已经可以继续沿用的 New-API 原生能力

| 能力 | 当前状态 | 判断 |
|------|----------|------|
| 公网入口 | `https://jiyu.245334.xyz` → New-API | 已作为主入口 |
| 品牌名 | `system_name=CC中转` | 已收口 |
| CC Switch 客户端入口 | `/api/status` 的 `chats` 已包含 `CC Switch` | 继续轻集成 |
| API Key 管理 | `tokens=6`，状态表正常 | 用 New-API 原生 |
| 渠道库存 | `channels=3`，均 `status=1` | 可继续内测 |
| 渠道测试记录 | 3 个渠道均有 `test_time/response_time` | 已有基础巡检数据 |
| 模型元数据 | `models=15`，均 `status=1` | 用 New-API 原生 |
| 能力映射 | `abilities=22`，均 `enabled=1` | 用 New-API 原生路由 |
| 兑换/充值记录 | `redemptions=2`、`top_ups=4` | 流程已跑通 |
| 日志/统计 | `logs=192`、`quota_data=17`、`perf_metrics=7` | 可做客服排障和对账依据 |
| Uptime Kuma 开关 | `uptime_kuma_enabled=true` | 可继续接外部看板 |

### 5.2 原生 P0/P1 能力当前状态

| 优先级 | New-API 原生能力 | 当前审计结果 | 补齐方式 |
|--------|------------------|--------------|----------|
| P0 | Turnstile 人机验证 | 已复用 JIYU 配置，`turnstile_check=true`，公网无 token 注册/登录会被拦截 | 剩余真人浏览器验收 |
| P0 | SMTP / 邮箱验证 / 找回密码 | 已复用 JIYU SMTP 配置，`email_verification=true`，Oracle SMTP TLS 握手通过 | 剩余真实收信验收 |
| P0 | 管理员 2FA | 已复用 JIYU TOTP 配置，`two_fas=2` | 管理员登录时使用旧 JIYU 管理 TOTP |
| P0 | 模型请求限流 | 状态接口未显示已启用的模型限流配置 | 使用 New-API 原生 rate limit 配置，先保守限流 |
| P0 | 可售兑换码库存 | `redemptions=2` 且 `status=2`，当前可售库存为 0 | 用 New-API 原生兑换码批量生成库存 |
| P1 | 订阅套餐 | `subscription_plans=0`、`user_subscriptions=0` | 如果卖月包/套餐，优先配置 New-API 原生订阅计划 |
| P1 | 价格页/供应商元数据 | `vendors=2`，模型 `vendor_id` 多为默认值 | 补齐供应商和价格展示，避免用户看不懂模型区别 |
| P2 | OAuth / Passkey / 签到 | OAuth/Passkey/签到均未启用 | 暂不作为首发售卖门槛 |

### 5.3 施工顺序结论

先补 New-API 原生 P0，不先写自研功能：

1. **安全入口**：Turnstile、SMTP/邮箱验证、管理员 2FA 已复用 JIYU 配置并启用。
2. **防刷成本控制**：下一步配置模型请求 rate limit → 渠道自动禁用/恢复阈值。
3. **可售库存**：用 New-API 原生兑换码生成一批内测库存并导出发货话术。
4. **再测闭环**：外网注册、登录、兑换、创建 Key、模型调用、禁用 Key、渠道刷新。
5. **最后再接自研**：CC Switch 增强、86Game 批量导入、闲鱼履约辅助台。

### 5.4 New-API 原生配置键

这些配置都属于 New-API 原生设置，后续应通过管理端“系统设置”或 Root 权限 `/api/option` 写入，不改源码、不新建配置表。

| 目标 | New-API 配置键 |
|------|----------------|
| Turnstile 站点 Key | `TurnstileSiteKey` |
| Turnstile Secret | `TurnstileSecretKey` |
| 开启 Turnstile | `TurnstileCheckEnabled=true` |
| SMTP 服务器 | `SMTPServer` |
| SMTP 端口 | `SMTPPort` |
| SMTP 发件账号 | `SMTPAccount` |
| SMTP 发件地址 | `SMTPFrom` |
| SMTP 密码/授权码 | `SMTPToken` |
| SMTP SSL | `SMTPSSLEnabled` |
| 开启邮箱验证 | `EmailVerificationEnabled=true` |
| 开启模型请求限流 | `ModelRequestRateLimitEnabled=true` |
| 限流窗口分钟数 | `ModelRequestRateLimitDurationMinutes` |
| 每窗口总请求上限 | `ModelRequestRateLimitCount` |
| 每窗口成功请求上限 | `ModelRequestRateLimitSuccessCount` |
| 分组限流 | `ModelRequestRateLimitGroup` |
| 渠道自动测试开关 | `monitor_setting.auto_test_channel_enabled=true` |
| 渠道自动测试间隔 | `monitor_setting.auto_test_channel_minutes` |

---

## 六、本次盘点依据

- New-API 后端路由: `packages/new-api-upstream/router/api-router.go`、`relay-router.go`
- New-API 前端模块: `packages/new-api-upstream/web/default/src/features/*`、`routes/*`
- 生产状态接口: `http://127.0.0.1:13000/api/status`
- 生产数据库摘要: `/opt/sub2api/data/newapi/one-api.db`
- 生产验证结论: 2026-07-05 外网 E2E 已验证注册、登录、兑换、API Key、模型调用、渠道刷新和清理闭环。
