# 项目注册表总集

> 合并自原 030-api-pool-registry.md + 031-command-registry.md + 032-dependency-map.md + 033-module-registry.md

---

## 一、API Key 池注册表

# API_POOL_REGISTRY — LLM API 号池注册表

> 最后更新: 2026-04-10
> 本文件记录所有 API 提供商、Key 状态、官方限制、模型可用性。修改 API Key 或新增提供商时必须同步更新。

---

## 号池总览

| # | 提供商 | 类型 | Key 数量 | 限制 | 环境变量 |
|---|--------|------|----------|------|----------|
| 1 | SiliconFlow | 免费无限 | 4 | 无 (免费模型) | `SILICONFLOW_KEYS` |
| 2 | SiliconFlow 付费 | 付费 (14元/条) | 10 | 未实名,禁Pro | `SILICONFLOW_PAID_KEYS` |
| 3 | iflow | 免费无限 | 1 | 无 (14个顶级模型) | `SILICONFLOW_UNLIMITED_KEY` |
| 4 | Groq | 免费 | 1 | 按模型不同 30-60RPM, 1000-14400RPD | `GROQ_API_KEY` |
| 5 | Cerebras | 免费 | 1 | 30RPM, 当前接入 `gpt-oss-120b` / `llama3.1-8b` | `CEREBRAS_API_KEY` |
| 6 | Gemini (Google AI Studio) | 免费 | 1 | 2.5/3.x 系动态 RPM/RPD, 1M上下文 | `GEMINI_API_KEY` |
| 7 | OpenRouter | 免费 | 1 | :free模型 20RPM, 50-1000RPD | `OPENROUTER_API_KEY` |
| 8 | Mistral | 免费 | 1 | 低RPM, 数据用于训练 | `MISTRAL_API_KEY` |
| 9 | Cohere | 免费 | 1 | 1000次/月, 20RPM | `COHERE_API_KEY` |
| 10 | NVIDIA NIM | 信用额度 | 1 | ~60RPM, 额度用完停用 | `NVIDIA_NIM_API_KEY` |
| 11 | GPT_API_Free | 免费 | 1 | 5-200次/天 (按模型) | `GPT_API_FREE_KEY` |
| 12 | Claude 代理 | 付费 | 1 | 仅 `/claude` 显式调用，不再走 XAPI | `CLAUDE_API_KEY` |
| 13 | g4f 本地 | 免费 | 1 | 无 (本地代理) | `G4F_API_KEY` |
| 14 | Kiro Gateway | 免费 | 1 | ~5RPM (本地代理) | `KIRO_API_KEY` |
| 15 | Volcengine 火山 | 付费 | 1 | ~10RPM | `VOLCENGINE_API_KEY` |
| 16 | Zhipu 智谱 | 付费 | 1 | OCR专用 | `ZHIPU_API_KEY` |
| 17 | Sambanova | 免费 | 1 | ~10RPM (DeepSeek-R1) | `SAMBANOVA_API_KEY` |
| 18 | GitHub Models | 免费 | 1 | ~15RPM | `GITHUB_MODELS_TOKEN` |
| 19 | inroi 授权上游 | 付费授权余额站 | 1 | 请求地址为 `https://www.inroi.shop/v1`；已验证 `/v1/models` 21 个模型和 `gpt-5.4-mini` Chat Completions；真实 Key 仅在服务器 runtime 加密号池保存 | Frist-API 管理端号池 |
| 20 | 86GameStore 授权上游 | 付费授权余额站 | 1 | 请求地址为 `https://api.86gamestore.com`；本地 Frist-API runtime 已按 Claude/OpenAI 两个模型组分开保存并探测 healthy，Claude 组覆盖 `claude-sonnet-4-5-c`、`claude-opus-4-6-c`，OpenAI 组覆盖 `gpt-5.4-mini`、`gpt-5.3-codex`、`gpt-5.4`、`gpt-5.5`；真实 Key 仅在 ignored runtime 中以 `enc:v1:` 保存 | Frist-API 管理端号池 |

## 非 LLM API

| # | 提供商 | 用途 | 限制 | 环境变量 |
|---|--------|------|------|----------|
| 21 | fal.ai | 图像/视频生成 | 按额度 | `FAL_KEY` |
| 22 | Deepgram | 语音转文字 | 按额度 | `DEEPGRAM_API_KEY` |
| 23 | Mem0 Cloud | 云端记忆 | 按额度 | `MEM0_API_KEY` |
| 24 | Kling AI | 视频生成 | 按额度 | `KLING_ACCESS_KEY` + `KLING_SECRET_KEY` |
| 25 | Manus AI | 联网搜索+编程 | 按额度 | `MANUS_API_KEY` |
| 26 | Vercel AI Gateway | AI网关 | 按额度 | `VERCEL_AI_KEY` |
| 27 | HuggingFace | 模型部署 | 免费额度 | `HUGGINGFACE_TOKEN` |
| 28 | SerpApi | 搜索引擎 | 250次/月, 50次/小时 | `SERPAPI_KEY` |
| 29 | Brave Search | 网页搜索 | 50QPS | `BRAVE_SEARCH_API_KEY` |
| 30 | CloudConvert | 文件格式转换 | 按额度 | `CLOUDCONVERT_API_KEY`（当前仅登记，主代码尚未接入） |
| 31 | Tavily | AI搜索 | 免费1000次/月 | `TAVILY_API_KEY` |
| 32 | 闲鱼 AI 客服 | 闲鱼专用LLM | 按额度 | `XIANYU_LLM_API_KEY` + `XIANYU_LLM_BASE_URL` + `XIANYU_LLM_MODEL` |
| 33 | Langfuse | LLM观测/追踪 | 免费额度 | `LANGFUSE_SECRET_KEY` + `LANGFUSE_PUBLIC_KEY` + `LANGFUSE_HOST` |
| 34 | 微信通知 | 微信消息推送 | 无 | `WECHAT_NOTIFY_ENABLED` |
| 35 | 微信笔笔省小程序 | 微信领券入口 App ID | 公开仓库不硬编码真实值 | `WECHAT_COUPON_APP_ID` |

---

## 详细限制 (基于官方文档)

### Groq — 极速推理

| 模型 | RPM | RPD | TPM | TPD | 上下文 |
|------|-----|-----|-----|-----|--------|
| `llama-3.3-70b-versatile` | 30 | 1,000 | 12,000 | 100,000 | 131K |
| `moonshotai/kimi-k2-instruct` | 60 | 1,000 | 10,000 | 300,000 | 262K |
| `openai/gpt-oss-120b` | 30 | 1,000 | 8,000 | 200,000 | 131K |
| `qwen/qwen3-32b` | 60 | 1,000 | 6,000 | 500,000 | 131K |
| `llama-3.1-8b-instant` | 30 | 14,400 | 6,000 | 500,000 | 131K |

### Gemini — Google AI Studio

| 模型 | 状态 | 上下文 | 输出 | 备注 |
|------|------|--------|------|------|
| `gemini-2.5-pro` | 稳定 | 1M | 65K | 最强, RPM低 |
| `gemini-2.5-flash` | 稳定 | 1M | 65K | 主力 |
| `gemini-2.5-flash-lite` | 稳定 | 1M | 65K | 轻量 |
| `gemini-3-flash-preview` | 预览 | 1M | 65K | 最新, 速率更严 |
| `gemini-2.0-flash` | **已从项目主链移除** | 1M | 8K | 官方已废弃 |

### Cerebras — 免费高速推理

- 当前项目重新启用 `gpt-oss-120b` 与 `llama3.1-8b`
- 官方免费层按模型 30RPM，适合作为高速开放模型补位
- 不参与 Claude 专用兜底链

### OpenRouter — 免费模型

- 无充值: 20RPM, **50RPD**
- 有充值 (≥$1): 20RPM, **1000RPD**
- 免费模型以 `:free` 后缀标识
- 项目中定位为后位免费兜底，不承担主链流量

### SiliconFlow 付费Key — 特别注意

- **10条Key, 每条14元余额, 全部未实名**
- **禁止调用含 "Pro" 的模型** → HTTP 403, 可能导致key报废
- 免费模型 (Qwen3-235B, GLM-4-32B) 不扣余额
- DeepSeek-R1 (非Pro) ~175次/key, DeepSeek-V3 ~1000次/key

### GPT_API_Free — 模型分级限制

| 模型组 | 日限制 |
|--------|--------|
| gpt-5/4o/4.1 系 | 5次/天 |
| deepseek-r1/v3 系 | 30次/天|
| gpt-4o-mini/3.5/nano 系 | 200次/天 |

### 当前项目主链与降级口径

- 主链优先: `SiliconFlow` → `iflow` → `Groq` → `Gemini 2.5/3.x`
- 中位补位: `Cerebras` → `OpenRouter free` → `NVIDIA NIM` → `Volcengine`
- 后位兜底: `Mistral` → `Cohere` → `GPT_API_Free` → `g4f`
- `Claude API` 仅保留给 `/claude` 显式调用，不再允许走 `XAPI/9w7` 空余额线路

---

## LiteLLM Router 模型强度排名 (节选)

| 分数 | 模型 | 提供商 |
|------|------|--------|
| 98 | gemini-2.5-pro | Google |
| 97 | gemini-2.5-flash | Google |
| 95 | claude-sonnet-4 / gemini-3-flash-preview | Kiro / Google |
| 94 | kimi-k2-instruct | Groq / iflow |
| 93 | DeepSeek-R1 | 多源 |
| 92 | o4-mini / Qwen3-235B | GitHub / SiliconFlow |
| 90 | Hermes-3-405B / DeepSeek-V3 | OpenRouter / SiliconFlow |

完整排名见 `src/litellm_router.py:MODEL_RANKING`。

---

## 配置文件位置

| 文件 | 用途 |
|------|------|
| `packages/clawbot/config/.env` | 所有 API Key 主配置 |
| `packages/clawbot/src/litellm_router.py` | LiteLLM Router 注册 + 模型排名 |
| `packages/clawbot/src/bot/globals.py` | Key 加载 + 余额管理 |
| `packages/clawbot/config/omega.yaml` | OMEGA 成本控制 + 模型路由映射 |
| `packages/clawbot/src/core/cost_control.py` | 日预算 + 成本跟踪 |

---

## 二、命令注册表


> 最后更新: 2026-05-09 (同步 Frist-API 319px 移动端批注修复) | Bot 命令总数 104

---

## 0. Frist-API Web 操作入口

| 入口 | 选择器 / 路径 | 说明 |
|------|---------------|------|
| 账户菜单 | `data-auth-toggle` / `data-auth-panel` | Frist-API 用户端右上角注册和登录入口 |
| 中英文切换 | `data-language-toggle` / `data-language-status` | 用户端顶栏语言偏好入口；当前只切换 `html.lang` 和偏好提示，完整英文界面未接入时会明确提示“仅切换语言偏好” |
| 用户注册 | `data-register-account` / `/api/frist/challenge` | Frist-API 用户端注册入口，注册专用验证码挑战，公开页不回显答案 |
| 用户登录 | `data-login-account` | Frist-API 用户端邮箱密码登录入口，不再要求每次登录填写验证码 |
| 忘记密码 | `data-password-reset-request` / `/api/frist/password-reset/request` | 登录前按邮箱发送重置验证码，SMTP 未配置时返回明确反馈 |
| 重置密码 | `data-password-reset-confirm` / `/api/frist/password-reset/confirm` | 用户输入重置验证码和新密码后完成 PBKDF2 密码更新 |
| 管理员身份码 | `data-owner-claim-code` / `data-owner-claim` | 登录后用一次性身份码把当前账号升级为管理员 |
| 运营入口 | `data-owner-entry` | 仅管理员账号可见，进入独立管理页 |
| 返回首页 | `data-back-home` / `data-route="dashboard"` | 子页面用“首页”短按钮返回用户首页，避免导入、测试、配置等页面迷路 |
| 创建 Key | `data-create-key` | 创建用户 `fk-live-*` API Key，兼容旧 `sk-*` |
| Key 改名 | `data-key-name` / `data-rename-key` | 修改单个用户 API Key 的显示名称 |
| Key 删除 | `data-delete-key` | 删除单个用户 API Key |
| Key 开关 | `data-toggle-key` | 开启或关闭单个用户 API Key |
| 兑换码购买入口 | `data-xianyu-purchase-link` | 预留闲鱼等第三方平台商品链接，用户购买卡密后回站内兑换 |
| 微信支付回调 | `/api/frist/payments/wechat/notify` | 微信支付 APIv3 回调验签、解密和按订单号幂等入账 |
| 支付宝支付回调 | `/api/frist/payments/alipay/notify` | 支付宝当面付异步通知验签和按订单号幂等入账 |
| 兑换码 | `data-redeem-code` | 日卡/月卡/加油包兑换 |
| 余额预警设置 | `data-balance-alert-card` / `data-balance-alert-enabled` / `data-balance-alert-threshold` / `data-balance-alert-email` | 用户在账单页自定义低余额提醒阈值和收件邮箱 |
| 余额预警保存 | `data-balance-alert-save` | 保存当前用户的余额预警配置 |
| 余额预警测试邮件 | `data-balance-alert-test` / `data-balance-alert-feedback` | 发送一封品牌化余额预警测试邮件，验证 SMTP 配置 |
| Tabcode Console 风格系统 | `data-design-system="tabcode-console"` / `.brand-mark` | Frist-API 用户端和管理端吸收 Tabcode 控制台视觉；用户端 Logo 保留红白斜切抽象品牌标，不再退回单字母占位 |
| 工作台导航 | `data-workspace-layout` / `data-workspace-rail` / `data-workspace-content` / `data-console-board` / `aria-current="page"` | 用户端固定左侧工作台导航，所有 hash 页面在右侧内容区切换；当前项只用细线和文字提示；移动端折叠菜单箭头固定在按钮内部，319px 视口不溢出 |
| 首页核心指标 | `data-focus-metrics` / `data-today-calls` / `data-today-cost` / `data-average-latency` / `data-success-rate` | 首屏只展示余额、Key、今日请求/消费和成功率，减少解释性文字 |
| 加载与空态 | `aria-busy` / `skeleton-row` / `empty-row--stack` / `table-empty` / `panel-caption` | 用户端加载、无数据和表格空状态统一反馈；Dashboard 消耗、异常、通道卡在无真实数据时说明统计口径、异常含义和下一步动作 |
| 后端恢复提示 | `data-server-recovery` / `data-retry-dashboard` | 后端不可用时显示“离线”和一键重连入口，避免用户不知道如何恢复 |
| Token 趋势 | `data-token-trend` / `data-trend-tooltip` / `data-trend-point` | 用户首页展示 SVG 折线/面积趋势图；鼠标移入整块图表或键盘聚焦点位时显示日期和 Token 数据 |
| 最近日志 | `data-usage-records` | 首页不再展示最近日志板块；完整日志统一进入左侧“记录/使用记录”查看 |
| API 搜索 | `data-api-search` | 在 API 管理页按名称或 Key 搜索用户 API Key |
| API 端点展示 | `data-base-url` | 在 API 管理页展示用户侧 OpenAI 兼容端点 |
| 使用记录 | `data-route="records"` / `data-usage-records` | 展示 API 密钥、模型、客户端、推理强度、端点、类型、计费模式、费用、延迟和 Token |
| 我的订阅 | `data-route="subscription"` / `subscription-surface` | 为未来时限套餐展示周期、到期和续费状态预留页面 |
| 独立兑换码页 | `data-route="redeem"` / `data-exchange-code` / `data-redeem-code` | 兑换卡密，并预留微信/支付宝异常时的人工代收付说明 |
| 充值入口 | `data-route="billing"` | 充值页面和后端能力保留，左侧导航暂时隐藏，等微信/支付宝正式接口稳定后再恢复入口 |
| 邀请返利 | `data-route="invite"` / `invite-surface` | 页面保留但左侧导航暂时隐藏；后续有真实拉新运营需要时再展示 |
| 个人资料 | `data-route="profile"` / `profile-surface` / `data-profile-avatar-input` | 行业通用账户布局，支持修改头像 URL、昵称和邮箱，并展示套餐、API Key 数量和余额 |
| 导入目标选择 | `data-import-targets` / `data-target` | 用户端选择 Claude、Codex、Gemini、OpenCode、OpenClaw、Hermes；`Harmes` 仅保留底层兼容，不再展示为重复目标 |
| CC Switch 导入 | `data-open-import` / `data-copy-link` / `data-import-fallback` | 打开或复制 Claude、Codex、Gemini、OpenCode、OpenClaw、Hermes 供应商导入链接；顶部前置一键导入按钮；深链只携带 CC Switch 当前官方 provider parser 消费字段和 `usageScript` / `usageEnabled` / `usageApiKey` / `usageBaseUrl` / `usageAutoInterval`，不再塞旧 `config` 或 `availableModels` 大块字段；服务端确认用户选择模型时，返回字段、深链 `model` 和 Codex TOML 默认模型保持一致；协议无弹窗时显示已复制降级反馈；319px 视口目标按钮两列显示，导入说明不横向裁切 |
| CC Switch 用量查询 | `/api/frist/key-usage` / `.usage-import-guide` | 用户 Key Bearer 或 `x-api-key` 只读鉴权，返回余额、已用、总额、今日/本月消费、请求量、Token、延迟和成功率；用量说明下移为教程/说明，不再占据页面前置主操作；移动端单列显示并允许长链接/脚本自动换行 |
| CC Switch 导入后检测 | `data-import-verification` / `data-refresh-health` / `data-playground-model` | 用户导入后按供应商卡片、用量脚本、真实调用、`gpt-image-2` 流程图和记录页消费逐项验收 |
| 异常消耗检测 | `data-usage-anomalies` / `data-usage-anomaly-status` / `usageAnomalies` | Dashboard 返回今日消耗偏高、单次调用费用突增和高延迟提醒；前端说明监控余额突增、失败率、慢请求和异常模型消耗，只展示用户可读摘要，不展示上游 Key、供应商原始地址或 raw usage |
| 导出模型清单 | `data-export-default-model` / `data-export-model-count` / `data-export-models` | 在 CC Switch 页展示默认模型、可用模型数量和完整模型列表 |
| CC Switch MCP 增强 | `data-open-ccswitch-mcp` / `data-copy-ccswitch-mcp` / `data-ccswitch-mcp-link` | 生成单独的 `resource=mcp` deep link，默认 apps 为 `claude,codex,gemini,opencode,hermes`，载入 Playwright、Superpowers 和 open-computer-use；OpenClaw 供应商可导入，但当前 CC Switch 会忽略 OpenClaw MCP |
| 手动配置复制 | `copy-code-box` / `data-copy-auth-json` / `data-copy-config-toml` / `data-copy-usage-script` / `data-copy-test-command` | 复制 Claude/Codex/OpenCode 等客户端 JSON/TOML、CC Switch 用量脚本和不污染用户本机配置的临时 CLI 连通测试命令；复制按钮已改为代码框内图标按钮 |
| 连通性刷新 | `data-refresh-health` | 用户侧模型连通性刷新 |
| 广场模型选择 | `data-playground-model` / `data-playground-model-grid` / `data-playground-selected-model` | 参考 OpenAI Web 端布局，用户在左侧模型列表选择文本或图片模型，右侧对话区测试 |
| 广场连通实测 | `data-playground-test` / `data-playground-status` | 一键实测当前模型，展示成功/失败、耗时和返回摘要 |
| 广场发送 | `data-playground-send` | 调用聊天网关或图片生成网关进行模型实测 |
| 广场消息删除 | `data-delete-message` | 删除单条广场测试消息 |
| 广场清空 | `data-clear-playground` | 清空广场测试消息并恢复欢迎提示 |
| 图片输出 | `data-image-output` | 展示 `gpt-image-2` 等图片模型生成结果 |
| 消耗分布图 | `data-usage-donut` | 用户侧模型消耗分布图；无真实请求时显示分段空态环和“暂无真实请求”说明，不再只展示单调灰色圆环 |
| 服务可用性 | `data-service-health` / `data-channel-monitor-metrics` / `data-channel-monitor-history` | 登录用户侧展示 `卡商1`、`卡商2` 等号池渠道当前库存快照、可用率、真实最低/平均延迟、60 秒刷新口径和最近状态条；无真实延迟样本时显示“等待真实请求更新”，游客 Dashboard 返回空 `channelChecks`，避免误认为 mock 数据 |
| 顶栏管理员快捷入口 | `data-owner-shortcut` | 右上角常驻“登录/身份码/管理”快捷入口；游客可一键打开登录弹窗，登录后未激活管理员可直接输入身份码，已激活时直达管理页，解决移动端入口不易发现问题 |
| 首页通道监控 | `data-channel-monitor-summary` / `data-channel-monitor-history` | 首页通道摘要按公开卡商号池聚合 healthy/down/slow 状态，支持慢线/断线自动降级，不暴露上游地址、上游 Key 或具体号商信息 |
| 模型广场 | `data-model-catalog` | 展示可用模型、家族、上下文和计价 |
| 教程目标选择 | `data-guide-targets` / `data-guide-target` | 独立教程入口从左侧导航隐藏，缺失配置说明合并回 CC Switch 页面；教程目标不再展示重复 `Harmes` |
| 教程 macOS 命令 | `data-mac-command` / `data-copy-mac-command` | 生成并复制 macOS 一键配置命令 |
| 教程 Windows 命令 | `data-win-command` / `data-copy-win-command` | 生成并复制 Windows 一键配置命令 |
| 教程配置复制 | `data-copy-guide-json` / `data-copy-guide-toml` | 复制教程页 JSON/TOML 配置 |
| 管理端人工入账 | `/admin.html` + `data-admin-credit` | 管理员按用户邮箱确认人工充值入账 |
| 管理端卡密生成 | `/admin.html` + `data-admin-redemption-cards` / `data-admin-card-create` / `/api/admin/redemption-cards` | 按套餐批量生成一次性兑换码，导出给闲鱼自动发货或客服系统 |
| 管理端账号恢复 | `/admin.html` + `data-admin-password-reset` / `/api/admin/customers/password` | SMTP 不可用或用户无法收信时，由管理员重置客户密码；响应和审计不回显明文密码 |
| 管理端 Plus 账号台账 | `/admin.html` + `data-admin-plus-accounts` / `data-admin-plus-save` / `data-admin-plus-edit` / `/api/admin/plus-accounts` | 登记和更新自用 ChatGPT Plus 账号、Apple ID、到期、TRY 余额、设备/Profile 和合规状态；不进入用户 `/v1` 路由 |
| 管理端 RT JSON 导入 | `/admin.html` + `data-admin-rt-accounts` / `data-admin-rt-import` / `/api/admin/rt-accounts/import` | 支持 JSON 数组、单个对象和 TXT 行导入 `refresh_token`、邮箱和账号 ID；只做脱敏台账和刷新准备，不减少 New-API 原有管理能力且不进入用户 `/v1` 路由 |
| 管理员 2FA | `/api/admin/2fa/verify` + `data-admin-2fa-code` | 管理端 TOTP 二次验证；启用 `FRIST_API_REQUIRE_ADMIN_2FA=1` 后，管理 API 除 2FA 验证入口外都必须带有效二次验证会话 |
| 生产边界检查 | `/api/admin/production-readiness` + `data-admin-readiness` | 汇总固定品牌域名、New-API 数据库、备份监控、管理员 2FA、真实支付商户和长期渠道 SLA 状态 |
| 备份状态登记 | `/api/admin/backups/status` | 记录最近备份、恢复演练、备份目标、校验值和状态，供生产强制检查使用 |
| 管理端补号 | `/admin.html` + `data-admin-replenish` | 独立管理端写入号源库存，不出现在用户端 |
| 管理端代理地址 | `/admin.html` + `data-admin-proxy-url` | 可选填写代理请求地址，补号时自动与直连路径择优 |
| 管理端探测模式 | `/admin.html` + `data-admin-probe-mode` | 自动探测、严格探测和信任写入模式选择 |
| 管理端号池首次使用流程 | `/admin.html` + `admin-onboarding-flow` | 首次管理员按填端点、粘 Key、一键获取模型、写入可用库存、自动切换五步完成号池接入 |
| 管理端渠道诊断 | `/admin.html` + `data-admin-channel-diagnostics` | 按端点和模型组汇总健康/断开/降级、最快延迟、失败原因和模型清单，帮助判断哪个渠道断了 |
| 管理端备用渠道类型 | `/admin.html` + `data-admin-source-type` | 区分授权/自有、CPA JSON、chong 和其他备用渠道 |
| 管理端风险状态 | `/admin.html` + `data-admin-risk-status` / `data-admin-backup-risk-accepted` | 备用渠道默认隔离，人工核验并确认后才进入路由 |
| 管理端风险备注 | `/admin.html` + `data-admin-risk-note` | 记录备用渠道来源责任人、放行依据和复核说明 |
| 管理端库存刷新 | `/admin.html` + `data-admin-refresh` | 独立管理端查看脱敏库存状态 |
| 管理端审计 | `/admin.html` + `data-admin-audit` | 查看补号、切换、耗尽、路由等脱敏事件 |

---

### 0.1 Frist-API 生产环境变量登记

| 环境变量 | 用途 | 备注 |
|----------|------|------|
| `FRIST_API_SMTP_HOST` | 余额预警 SMTP 主机 | Gmail 可用 `smtp.gmail.com` |
| `FRIST_API_SMTP_PORT` | 余额预警 SMTP 端口 | TLS 通常用 `465` |
| `FRIST_API_SMTP_SECURE` | 是否使用 TLS | `1` 表示 TLS，`0` 表示明文连接 |
| `FRIST_API_SMTP_FAMILY` | SMTP 地址族选择 | 默认 `auto`，可用 `6` 强制 IPv6、`4` 强制 IPv4 |
| `FRIST_API_SMTP_USER` | SMTP 登录用户名 | 只放服务器环境变量 |
| `FRIST_API_SMTP_PASSWORD` | SMTP 应用专用密码 | 禁止提交到 Git 或写进文档正文 |
| `FRIST_API_SMTP_FROM` | 余额预警发件邮箱 | 默认可与用户名一致 |
| `FRIST_API_BALANCE_ALERT_FROM_NAME` | 余额预警发件人名称 | 默认 `Frist-API Billing` |
| `FRIST_API_PASSWORD_HASH_SECRET` | Frist-API 用户密码哈希密钥 | 生产必须为强随机值；和会话密钥分离，便于轮换登录会话而不锁死旧账号 |
| `FRIST_API_LEGACY_PASSWORD_HASH_SECRETS` | 历史密码哈希密钥兼容列表 | 逗号分隔；更换密码哈希密钥后临时保留旧值，用户下次登录成功后自动迁移 |
| `FRIST_API_REQUIRE_CAPTCHA` | 是否启用注册验证码挑战 | `1` 启用；登录不再要求验证码 |
| `FRIST_API_CAPTCHA_MAX_ATTEMPTS` | 单个验证码最大错误次数 | 默认 `3`，超过后需刷新挑战 |
| `FRIST_API_PASSWORD_RESET_TTL_MS` | 忘记密码验证码有效期 | 默认 `900000`，即 15 分钟 |
| `FRIST_API_DATA_ENCRYPTION_KEY` | runtime 敏感字段加密密钥 | 公开模式必填；用于加密用户 Key 和上游 rawKey |
| `FRIST_API_PUBLIC_GATEWAY_BASE_URL` | 用户导出和邮件使用的公网 `/v1` 网关地址 | 生产必须使用 HTTPS 品牌域名；`https://www.inroi.shop/v1` 是授权上游请求地址，不是用户导出入口 |
| `FRIST_API_REQUIRE_CSRF` | Cookie 登录态非幂等接口 CSRF 校验开关 | 生产建议 `1`；公开模式和 `NODE_ENV=production` 会自动启用 |
| `FRIST_API_REQUIRE_ADMIN_2FA` | 是否强制管理端 TOTP 二次验证 | 生产强制模式必须为 `1` |
| `FRIST_API_ADMIN_TOTP_SECRETS` | 管理员 TOTP Base32 Secret 列表 | 逗号分隔；只放服务器环境变量或安全注入，不写文档正文 |
| `FRIST_API_ADMIN_2FA_SESSION_TTL_MS` | 管理员 2FA 会话有效期 | 默认 `3600000`，即 1 小时 |
| `FRIST_API_ALLOW_PRIVATE_UPSTREAM_URLS` | 是否允许管理端补号 URL 指向私网/本机地址 | 生产必须保持 `0`，只用于本地私网测试 |
| `FRIST_API_CANONICAL_HOST` | Frist-API 唯一内容入口域名 | 当前为 `frist-api.101-43-41-96.nip.io`；Docker Compose 已透传 |
| `FRIST_API_REDIRECT_HOSTS` | 需要跳转到唯一入口的旧/裸域名 | 当前为 `101-43-41-96.nip.io`，只做 301，不直接服务页面；Docker Compose 已透传 |
| `FRIST_API_ENFORCE_PRODUCTION_READINESS` | 是否强制生产边界检查 | `1` 时缺固定 HTTPS 品牌域名、New-API 数据库、2FA 或真实支付商户会启动失败 |
| `FRIST_API_ALLOW_INSECURE_PUBLIC_HTTP` | 是否允许临时公网 HTTP 网关 | 免费 HTTP 过渡期才设 `1`；正式 HTTPS 域名应为 `0` |
| `FRIST_API_BACKUP_STATUS_MAX_AGE_HOURS` | 备份新鲜度上限 | 默认 `26` 小时，超过视为备份监控未闭环 |
| `FRIST_API_SLA_RETENTION_DAYS` | 渠道 SLA 探测事件保留天数 | 默认 `30` 天 |
| `FRIST_API_CHANNEL_MONITOR_ENABLED` | 是否启用后台 60 秒通道巡检 | `1` 启用；无人调用时也会巡检健康库存 |
| `FRIST_API_CHANNEL_MONITOR_INTERVAL_MS` | 后台通道巡检间隔毫秒 | 默认 `60000` |
| `FRIST_API_CHANNEL_MONITOR_BATCH_SIZE` | 每轮巡检最多探测的 Key 数量 | 默认 `4`，防止一次性压测所有库存 |
| `FRIST_API_CHANNEL_MONITOR_COOLDOWN_MS` | 同一 Key 自动巡检最小间隔毫秒 | 默认 `55000`，避免短时间重复探测 |
| `FRIST_API_KEY_ALERT_WEBHOOK` | Key 认证/额度异常告警 Webhook | 可选；未配置 Telegram 时可走通用告警 Webhook |
| `FRIST_API_TELEGRAM_BOT_TOKEN` | Telegram Bot Token | 可选；配置后自动发送一次性补号提醒 |
| `FRIST_API_TELEGRAM_CHAT_ID` | Telegram 接收群/用户 ID | 与 Bot Token 搭配，用于接收 Key 异常提醒 |
| `FRIST_API_PAYMENT_ENABLED` | 是否启用真实支付接口 | 总开关；未启用时仍可人工确认 |
| `FRIST_API_WECHAT_PAY_ENABLED` | 是否启用微信 Native 支付 | 需要商户平台、AppID、商户号和 APIv3 配置 |
| `FRIST_API_WECHAT_PAY_APPID` | 微信支付 AppID | 由微信支付商户平台绑定的应用提供 |
| `FRIST_API_WECHAT_PAY_MCH_ID` | 微信支付商户号 | 微信支付商户平台提供 |
| `FRIST_API_WECHAT_PAY_SERIAL_NO` | 微信商户 API 证书序列号 | 用于 APIv3 请求签名 |
| `FRIST_API_WECHAT_PAY_PRIVATE_KEY` | 微信商户私钥 PEM | 只放服务器环境变量或安全文件注入 |
| `FRIST_API_WECHAT_PAY_PUBLIC_KEY` | 微信支付平台公钥 PEM | 用于回调验签 |
| `FRIST_API_WECHAT_PAY_API_V3_KEY` | 微信支付 APIv3 密钥 | 32 字节，用于回调资源解密 |
| `FRIST_API_WECHAT_PAY_NOTIFY_URL` | 微信支付回调 URL | 默认可由公开入口推导为 `/api/frist/payments/wechat/notify` |
| `FRIST_API_ALIPAY_ENABLED` | 是否启用支付宝当面付 | 需要支付宝开放平台应用和当面付产品 |
| `FRIST_API_ALIPAY_APP_ID` | 支付宝应用 AppID | 支付宝开放平台提供 |
| `FRIST_API_ALIPAY_PRIVATE_KEY` | 支付宝应用私钥 PEM | 只放服务器环境变量或安全文件注入 |
| `FRIST_API_ALIPAY_PUBLIC_KEY` | 支付宝平台公钥 PEM | 用于异步通知验签 |
| `FRIST_API_ALIPAY_NOTIFY_URL` | 支付宝回调 URL | 默认可由公开入口推导为 `/api/frist/payments/alipay/notify` |
| `FRIST_API_NEWAPI_ENABLED` | 是否启用 Frist-API 服务端 New-API 业务桥接 | `1` 启用；未启用时继续走本地 JSON 自研逻辑 |
| `FRIST_API_REQUIRE_NEWAPI_DATABASE` | 是否把 New-API 数据库作为生产必备持久化层 | 生产强制模式必须为 `1`，用于防止继续把 JSON runtime 当生产数据库 |
| `FRIST_API_NEWAPI_BASE_URL` | New-API 内网 API 地址 | 例如 `http://openclaw-newapi:3000`，不要暴露公网管理口 |
| `FRIST_API_NEWAPI_ACCESS_TOKEN` | New-API 用户 access token | 只放服务器环境变量，禁止写入仓库 |
| `FRIST_API_NEWAPI_USER_ID` | access token 所属 New-API 用户 ID | v1 会校验 `New-Api-User` 头 |
| `FRIST_API_NEWAPI_DEFAULT_GROUP` | New-API 新建 Token 默认分组 | 默认 `default` |
| `FRIST_API_NEWAPI_DEFAULT_TOKEN_QUOTA` | New-API 新建 Token 默认额度 | `0` 配合 `unlimited_quota=true` |
| `FRIST_API_NEWAPI_GATEWAY_ENABLED` | 是否让 Frist-API `/v1` 直接代理 New-API 网关 | `1` 启用；默认关闭以保留自研路由兜底 |
| `FRIST_API_NEWAPI_GATEWAY_BASE_URL` | New-API 网关地址 | 通常为 `http://openclaw-newapi:3000/v1` |

---

### 0.2 New-API 同步与代理入口登记

| 类型 | 名称 | 路径 / 命令 | 说明 |
|------|------|-------------|------|
| 上游源码 | `QuantumNous/new-api` | `packages/new-api-upstream` | Git submodule，当前固定 `v1.0.0-rc.4` |
| Compose 镜像 | `calciumion/new-api` | `docker-compose.newapi.yml` | 当前镜像 `calciumion/new-api:v1.0.0-rc.4`，不使用 `latest` |
| 同步检查 | `new-api-check` | `make new-api-check` | 检查 GitHub 最新非草稿 release、submodule 指针和 compose 镜像 tag 是否一致 |
| 同步升级 | `new-api-sync` | `make new-api-sync` | 更新 submodule 到最新 release，并同步 compose 镜像 tag |
| 同步脚本 | `sync_new_api_upstream.sh` | `scripts/sync_new_api_upstream.sh` | 支持 `check` / `update`；`check` 发现落后返回非 0，适合 CI/定时任务 |
| 定时同步 | `New-API Scheduled Sync` | `.github/workflows/new-api-sync.yml` | 每天检查最新 release，落后时自动开 `codex/new-api-scheduled-sync` PR；不会直接升级生产数据库 |
| Frist-API 桥接 | `newApiBridge.js` | `apps/frist-api/server/newApiBridge.js` | 通过 New-API HTTP 接口承接用户看板、Token、日志、兑换、订阅、邀请和可选网关代理 |
| 迁移演练 | `frist_api_newapi_migration_dry_run.mjs` | `scripts/frist_api_newapi_migration_dry_run.mjs` | 默认只读 Frist-API runtime，输出用户、Token、订单、日志迁移清单和风险提示，不写生产 New-API |

| 环境变量 | 用途 | 备注 |
|----------|------|------|
| `NEWAPI_BASE_URL` | New-API 内网服务地址 | 默认 `http://localhost:3000` |
| `NEWAPI_HOST_PORT` | New-API 宿主机回环监听端口 | 默认 `3000`；共享服务器如端口冲突可改为 `13000`，容器内部仍为 `3000` |
| `NEWAPI_ADMIN_TOKEN` | New-API 用户 access token | 通过 New-API 用户资料页或 `/api/user/token` 生成，禁止写入仓库 |
| `NEWAPI_ADMIN_USER_ID` | New-API 当前用户 ID | New-API v1 后台/用户 API 会校验 `New-Api-User` 头，需与 access token 所属用户一致 |
| `NEWAPI_INITIAL_TOKEN` | New-API 容器初始 root token | 只放本机或服务器环境文件，用于首次初始化 |

---

## 1. 注册命令一览（101 个）

命令在 `multi_bot.py:289-387` 统一注册。

### 1.1 基础命令 — `BasicCommandsMixin` (cmd_basic_mixin.py, 1038 行) + `ToolsMixin` (cmd_basic/tools_mixin.py)

| # | 命令 | Handler | 说明 | BotFather 菜单 |
|---|------|---------|------|:-:|
| 1 | `/start` | `onboard_entry` | ConversationHandler 引导向导：新用户3步向导，老用户智能欢迎 | Y |
| 2 | `/help` | `cmd_help` | 帮助菜单（始终展示9分类菜单，不触发向导） | Y |
| 3 | `/clear` | `cmd_clear` | 清空当前对话历史 | Y |
| 4 | `/status` | `cmd_status` | Bot 运行状态 + 网关 + 浏览器 | Y |
| 4.1 | `/perf` | `cmd_perf` | 性能指标报告 (响应时间/LLM耗时/交易周期) | Y |
| 5 | `/draw` | `cmd_draw` | AI 生图 (flux/sd3/sdxl) | Y |
| 6 | `/news` | `cmd_news` | 科技早报 | Y |
| 7 | `/metrics` | `cmd_metrics` | 运行指标 (消息/API/延迟/模型) | N |
| 8 | `/lanes` | `cmd_lanes` | 群聊显式分流标签说明 | N |
| 9 | `/lane` | `cmd_lane` | `/lanes` 别名 | N |
| 10 | `/context` | `cmd_context` | 上下文 token 用量 + 进度条 | N |
| 11 | `/compact` | `cmd_compact` | 手动压缩上下文 | N |
| 12 | `/model` | `cmd_model` | 当前模型 + 路由方式 | N |
| 13 | `/pool` | `cmd_pool` | 免费 API 池 + AdaptiveRouter 状态 | N |
| 14 | `/memory` | `cmd_memory` | 查看/管理 Bot 记忆 (分页) | N |
| 15 | `/settings` | `cmd_settings` | 个人偏好设置 (InlineKeyboard 切换) | N |
| 16 | `/voice` | `cmd_voice` | 切换语音回复模式 | N |
| 17 | `/qr` | `cmd_qr` | 生成二维码 | N |
| 18 | `/keyhealth` | `cmd_keyhealth` | API Key 健康验证报告 (Admin) | N |
| 19 | `/tts` | `cmd_tts` | 文字转语音 (edge-tts, 支持6种中文音色) | N |
| 20 | `/claude` | `cmd_claude` | Claude Code CLI 桥接，启动/停止 Claude Code 开发环境 | N |

### 1.2 投资命令 — `InvestCommandsMixin` (cmd_invest_mixin.py, 498 行)

| # | 命令 | Handler | 说明 | BotFather |
|---|------|---------|------|:-:|
| 20 | `/quote` | `cmd_quote` | 行情查询 (富卡片 + 操作按钮) | Y |
| 21 | `/market` | `cmd_market` | 市场概览 | Y |
| 22 | `/portfolio` | `cmd_portfolio` | 投资组合 (卡片 + 风险敞口 + SPY对标 + 饼图 + 行业分布 + IBKR) | Y |
| 23 | `/buy` | `cmd_buy` | 模拟买入 (风控→IBKR→模拟降级) | Y |
| 24 | `/sell` | `cmd_sell` | 模拟卖出 | Y |
| 25 | `/watchlist` | `cmd_watchlist` | 自选股管理 | N |
| 26 | `/trades` | `cmd_trades` | 交易记录 + PnL 图表 | N |
| 27 | `/reset_portfolio` | `cmd_reset_portfolio` | 重置投资组合 | N |
| 28 | `/export` | `cmd_export` | 导出 trades/watchlist/portfolio/expenses/xianyu (xlsx/csv) | N |

### 1.3 技术分析 — `AnalysisCommandsMixin` (cmd_analysis_mixin.py, 362 行)

| # | 命令 | Handler | 说明 | BotFather |
|---|------|---------|------|:-:|
| 29 | `/ta` | `cmd_ta` | 全套超短线技术指标 | Y |
| 30 | `/scan` | `cmd_scan` | 市场多标的扫描 | N |
| 31 | `/signal` | `cmd_signal` | 快速买卖信号 (多标的并行) | N |
| 32 | `/performance` | `cmd_performance` | 绩效仪表盘 | N |
| 33 | `/review` | `cmd_review` | AI 团队复盘今日交易 | N |
| 34 | `/journal` | `cmd_journal` | 交易日志 (持仓 + 已平仓) | N |
| 35 | `/chart` | `cmd_chart` | K线图 (MA+成交量, Plotly candlestick) | N |
| 36 | `/drl` | `cmd_drl` | DRL 强化学习策略分析 (PPO, FinRL) | N |
| 37 | `/factors` | `cmd_factors` | 16 Alpha 因子分析 (Qlib, LightGBM) | N |
| 38 | `/calc` | `cmd_calc` | 仓位计算器: 固定比例法+凯利公式 (搬运 TradingView Position Size Calculator) | N |
| 39 | `/weekly` | `cmd_weekly` | 综合周报 (投资+社媒+闲鱼+成本 7 天聚合) | N |
| 40 | `/accuracy` | `cmd_accuracy` | AI预测准确率面板 (按AI分组显示历史预测表现) | N |
| 41 | `/equity` | `cmd_equity` | 权益曲线图表 (按日聚合累计收益变化) | N |
| 42 | `/targets` | `cmd_targets` | 盈利目标进度 (日/周/月目标达成百分比) | N |
| 43 | `/review_history` | `cmd_review_history` | 复盘历史查询 (近N次复盘记录+教训+星级评分) | N |

### 1.4 IBKR 实盘 — `IBKRCommandsMixin` (cmd_ibkr_mixin.py, 165 行)

| # | 命令 | Handler | 说明 | BotFather |
|---|------|---------|------|:-:|
| 44 | `/ibuy` | `cmd_ibuy` | IBKR 买入 (市价/限价) | N |
| 45 | `/isell` | `cmd_isell` | IBKR 卖出 | N |
| 46 | `/ipositions` | `cmd_ipositions` | IBKR 持仓查询 | N |
| 47 | `/iorders` | `cmd_iorders` | IBKR 挂单查询 | N |
| 48 | `/iaccount` | `cmd_iaccount` | IBKR 账户信息 + 预算 | N |
| 49 | `/icancel` | `cmd_icancel` | 取消 IBKR 订单 | N |

### 1.5 自动交易 — `TradingCommandsMixin` (cmd_trading_mixin.py, 399 行)

| # | 命令 | Handler | 说明 | BotFather |
|---|------|---------|------|:-:|
| 50 | `/autotrader` | `cmd_autotrader` | AutoTrader 控制 (start/stop/auto/manual/cycle/confirm/cancel) | N |
| 51 | `/risk` | `cmd_risk` | 风控状态 + IBKR 实时数据 | Y |
| 52 | `/monitor` | `cmd_monitor` | 持仓监控 (卡片 + 饼图) | N |
| 53 | `/tradingsystem` | `cmd_tradingsystem` | 交易系统全状态 | N |
| 54 | `/backtest` | `cmd_backtest` | 回测 (自研引擎 / Freqtrade + Bokeh + 高级分析) | Y |
| 55 | `/rebalance` | `cmd_rebalance` | 再平衡 (preset 配置 + 漂移分析) | N |

### 1.6 协作命令 — `CollabCommandsMixin` (cmd_collab_mixin.py, 824 行)

| # | 命令 | Handler | 说明 | BotFather |
|---|------|---------|------|:-:|
| 56 | `/invest` | `cmd_invest` | 6 位 AI 投资分析会议 | Y |
| 57 | `/discuss` | `cmd_discuss` | 多 Bot 多轮讨论 (1-10 轮) | N |
| 58 | `/stop_discuss` | `cmd_stop_discuss` | 中断讨论/投资会议 | N |
| 59 | `/collab` | `cmd_collab` | 多模型协作 (规划→执行→审查→汇总) | N |

### 1.7 执行场景 — `ExecutionCommandsMixin` (cmd_execution_mixin.py, 1737 行)

| # | 命令 | Handler | 说明 | BotFather |
|---|------|---------|------|:-:|
| 60 | `/ops` | `cmd_ops` | 自动化工作台 (交互菜单) | Y |
| 61 | `/dev` | `cmd_dev` | 开发流程 (→ops dev) | N |
| 62 | `/brief` | `cmd_brief` | 执行简报 | N |
| 63 | `/hot` | `cmd_hot` | 热点发文 (→cmd_hotpost) | Y |
| 64 | `/hotpost` | `cmd_hotpost` | 抓热点 + 一键发文 (支持 --preview) | N |
| 65 | `/cost` | `cmd_cost` | 成本/配额/节流状态 | N |
| 66 | `/config` | `cmd_config` | 运行配置概览 | N |
| 67 | `/topic` | `cmd_topic` | 题材深度研究 | N |
| 68 | `/xhs` | `cmd_xhs` | 小红书发文 | N |
| 69 | `/post` | `cmd_post` | 双平台发文 (无题材→热点) | Y |
| 70 | `/social_plan` | `cmd_social_plan` | 发文计划 | N |
| 71 | `/social_repost` | `cmd_social_repost` | 双平台改写草稿 | N |
| 72 | `/social_launch` | `cmd_social_launch` | 数字生命首发包 | N |
| 73 | `/social_persona` | `cmd_social_persona` | 当前社媒人设 | N |
| 74 | `/post_social` | `cmd_post_social` | 双平台发文 (→cmd_post) | N |
| 75 | `/post_x` | `cmd_post_x` | 发 X (→cmd_xpost) | N |
| 76 | `/post_xhs` | `cmd_post_xhs` | 发小红书 (→cmd_xhspost) | N |
| 77 | `/xwatch` | `cmd_xwatch` | X 博主监控导入 | N |
| 78 | `/xbrief` | `cmd_xbrief` | X 博主更新摘要 | N |
| 79 | `/xdraft` | `cmd_xdraft` | 生成 X 草稿 | N |
| 80 | `/xpost` | `cmd_xpost` | 自动发 X | N |
| 81 | `/xhsdraft` | `cmd_xhsdraft` | 生成小红书草稿 | N |
| 82 | `/xhspost` | `cmd_xhspost` | 自动发小红书 | N |
| 83 | `/dualpost` | `cmd_post` | 一键双平台发文 (`/post` 的别名) | N |
| 84 | `/publish` | `cmd_publish` | 社媒多平台发布 — sau_bridge (抖音/B站/小红书/快手) | N |
| 85 | `/xianyu` | `cmd_xianyu` | 闲鱼 AI 客服控制 (start/stop/status/reload/floor) | N |
| 86 | `/social_calendar` | `cmd_social_calendar` | 内容日历(DB优先+AI生成)，支持 `done N` 标记完成 | N |
| 87 | `/social_report` | `cmd_social_report` | 社媒效果报告 + A/B 测试 | N |
| 88 | `/agent` | `cmd_agent` | 智能 Agent — 自然语言驱动多工具链 (smolagents) | N |
| 89 | `/novel` | `cmd_novel` | AI 小说工坊 — 网文大纲/续写/导出/TTS (inkos+MuMuAINovel) | N |
| 90 | `/ship` | `cmd_ship` | 闲鱼卡券管理 — add/stock/rule/stats/test (auto_shipper) | N |
| 91 | `/xianyu_report` | `cmd_xianyu_report` | 闲鱼收入报表 — 日报/周报/月报 + 爆款排行 + BI三板块(热销排行/高峰时段/转化漏斗) | N |
| 92 | `/xianyu_style` | `cmd_xianyu_style` | 闲鱼 AI 客服回复配置 — 自定义回复风格/FAQ模板/商品规则 (set/faq/rule/show) | N |
| 93 | `/bill` | `cmd_bill` | 生活账单追踪 — 话费/水电费余额检测 + 低余额告警 + 定期提醒 (add/update/list/remove + 中文NLP) | N |
| 94 | `/pricewatch` | `cmd_pricewatch` | 降价监控 — 商品降价提醒 + 每6小时自动检查 + 目标价触发通知 (add/list/remove + 中文NLP) | Y |
| 95 | `/deals` | `cmd_deals` | 折扣搜索/比价查询 (cmd_life_mixin.py) | N |
| 96 | `/intel` | `cmd_intel` | 全球情报速递 — 7大行业+5大地区交互式菜单 + 关键词搜索 (Worldmonitor API) | Y |
| 97 | `/coupon` | `cmd_coupon` | 微信笔笔省领券 — mitmproxy抓包+API直调自动领取提现免费券 | N |
| 98 | `/test_token` | `cmd_test_token` | 测试已保存的领券token有效性 — 纯API调用,不走mitmproxy,返回token年龄和有效状态 | N |
| 99 | `/set_coupon_token` | `cmd_set_coupon_token` | 手动设置领券token — 通过手机抓包获取token后直接设置,免mitmproxy流程 | N |
| 100 | `/evolution` | `cmd_evolution` | 进化引擎状态 — 查看自动进化提案/能力缺口/审批统计 (cmd_ops_mixin.py) | N |

---

## 2. Callback Button 模式一览

在 `multi_bot.py:388-406` 注册。

| # | Pattern | Handler | Source | 说明 |
|---|---------|---------|--------|------|
| 1 | `^itrade` | `handle_trade_callback` | callback_mixin | 投资分析后一键下单 |
| 2 | `^help:` | `handle_help_callback` | help_mixin | /start 分类菜单导航 |
| 3 | `^ob_i:` | `onboard_interests` | onboarding_mixin | 引导向导 Step 1: 兴趣领域选择 (ConversationHandler 内部) |
| 4 | `^ob_s:` | `onboard_style` | onboarding_mixin | 引导向导 Step 2: 沟通风格选择 (ConversationHandler 内部) |
| 5 | `^fb\|` | `handle_feedback_callback` | memory_mixin | 👍/👎/🔄 反馈按钮 |
| 6 | `^mem_` | `handle_memory_callback` | memory_mixin | 记忆分页/清除 |
| 7 | `^settings\|` | `handle_settings_callback` | settings_mixin | 设置切换按钮 |
| 8 | `^cmd:` | `handle_notify_action_callback` | callback_mixin | 交易通知 actionable 按钮 + 模糊引导快捷操作 (bill/xianyu 已加入 cmd_map) |
| 9 | `^social_confirm:` | `handle_social_confirm_callback` | cmd_social_mixin | 社交发文预览确认/取消/重生成 |
| 10 | `^ops_` | `handle_ops_menu_callback` | cmd_ops_mixin | /ops 交互菜单按钮 |
| 11 | `^intel_` | `handle_intel_callback` | cmd_intel_mixin | 情报分类/地区/简报按钮 (intel_cat:/intel_reg:/intel_brief) |
| 12 | `^(ta_\|buy_\|watch_)` | `handle_quote_action_callback` | cmd_invest_mixin | 行情卡片操作 (技术分析/买入/加自选) |
| 13 | `^(trade:\|bt:\|ta:\|analyze:\|news:\|evo:\|retry:\|shop:\|post:)` | `handle_card_action_callback` | callback_mixin | OMEGA 响应卡片操作按钮 |
| 14 | `^\d+:.+:.+$` | `handle_clarification_callback` | callback_mixin | ClarificationCard 追问按钮 ({tid}:{param}:{value}) |
| 15 | `^suggest:` | `handle_suggest_callback` | callback_mixin | 模糊输入建议按钮 |
| 16 | `^noop$` | lambda (answer) | multi_bot | 空操作（已收到反馈占位） |

### 非 Command 消息处理器 (multi_bot.py:408-434)

| Handler | Filter | 说明 |
|---------|--------|------|
| `handle_message` | TEXT & ~COMMAND | 文本对话（流式输出 + 中文 NLP 拦截） |
| `handle_photo` | PHOTO | OCR → 场景路由 → 业务决策链 |
| `handle_voice` | VOICE \| AUDIO | Whisper 转文字 → handle_message |
| `handle_document_ocr` | Document.PDF \| Document.IMAGE \| .docx \| .pptx \| .xlsx \| .doc \| .xls \| .ppt | 文档 OCR (PDF/图片/Office文档) |
| `handle_inline_query` | InlineQuery | @bot 搜股票/记忆/命令提示 |

---

## 3. 中文自然语言触发词

定义在 `message_mixin.py:19-181` 的 `_match_chinese_command()` 函数。

### 3.1 基础触发词 (fullmatch 精确匹配)

| 触发文本 | Action Type | Maps To |
|----------|-------------|---------|
| 开始/帮助/菜单/命令/指令/使用说明 | `start` | `/start` |
| 清空/清空对话/重置对话/重置会话 | `clear` | `/clear` |
| 状态/查看状态/机器人状态 | `status` | `/status` |
| 配置/配置状态/当前配置/运行配置 | `config` | `/config` |
| 成本/配额/用量/成本状态/配额状态 | `cost` | `/cost` |
| 上下文/上下文状态 | `context` | `/context` |
| 压缩/压缩上下文/整理上下文 | `compact` | `/compact` |
| 新闻/科技早报/早报 | `news` | `/news` |
| 指标/运行指标/监控指标 | `metrics` | `/metrics` |
| 分流/分流规则/路由规则/... | `lanes` | `/lanes` |

### 3.2 执行场景触发词 (search 模糊匹配)

| 触发文本 | Action Type | Maps To |
|----------|-------------|---------|
| 执行场景/自动化菜单/ops帮助 | `ops_help` | `/ops help` |
| 整理邮箱/邮件整理/邮箱分类 | `ops_email` | `/ops email` |
| 执行简报/行业简报/今日简报 | `ops_brief` | `/brief` |
| 最重要3件事/任务优先级/今日任务 | `ops_task_top` | `/ops task top` |
| 赏金猎人/自动接单/接单机器人/bounty | `ops_bounty_run` | `/ops bounty run` |
| 扫赏金/扫描赏金/找赏金/赏金扫描 + 关键词 | `ops_bounty_scan` | `/ops bounty scan` |
| 赏金列表/赏金机会/赏金看板 | `ops_bounty_list` | `/ops bounty list` |
| 赏金top/赏金排行/高收益赏金 | `ops_bounty_top` | `/ops bounty top` |
| 开工赚钱/打开赏金机会/开赏金链接 | `ops_bounty_open` | `/ops bounty open` |
| 推文计划/分析推文/推文执行计划 + url | `ops_tweet_plan` | `/ops tweet plan` |
| 执行推文/推文执行/推文赚钱 + url | `ops_tweet_run` | `/ops tweet run` |
| 文档检索/文档搜索/搜文档 + query | `ops_docs_search` | `/ops docs search` |
| 建立文档索引/索引文档 + path | `ops_docs_index` | `/ops docs index` |
| 会议纪要/总结会议 + text | `ops_meeting` | `/ops meeting` |
| 社媒选题/内容选题/写作选题 + keyword | `ops_content` | `/ops content` |
| N分钟后提醒我 + message | `ops_life_remind` | `/ops life remind` |
| 提醒我 + message | `ops_life_remind` | `/ops life remind 30` |
| 我的提醒 / 提醒列表 / 查看提醒 | `ops_life_remind` | 直接调用 `list_reminders()` |
| 取消提醒 #N / 删除提醒N | `ops_life_remind` | 直接调用 `cancel_reminder()` |
| 每天/每周X/每小时/每月N号/工作日 提醒我 + message | `ops_life_remind` | 直接调用 `create_reminder(recurrence_rule=)` |
| 明天下午3点/下周一 提醒我 + message | `ops_life_remind` | 直接调用 `create_reminder(time_text=)` |
| 项目周报/生成项目周报 + path | `ops_project` | `/ops project` |
| 开发流程/执行开发流程/跑开发流程 + path | `ops_dev` | `/ops dev` |

### 3.3 社媒触发词

| 触发文本 | Action Type | Maps To |
|----------|-------------|---------|
| 社媒计划/发文计划/今日发什么 | `social_plan` | `/social_plan` |
| 双平台改写/改写双平台/双平台草稿 | `social_repost` | `/social_repost` |
| 双平台发文/一键双发/双平台一键发文 | `dualpost` | `/dualpost` |
| 数字生命首发/首发包/社媒首发包 | `social_launch` | `/social_launch` |
| 当前社媒人设/社媒人设/数字生命人设 | `social_persona` | `/social_persona` |
| 研究/分析/看看/学习 + X + 题材/方向/内容 | `social_topic` | `/topic` |
| 发X到小红书 | `social_xhs` | `/xhs` |
| 发X到x/推特/推文 | `social_x` | `/xpost` |
| 发X双平台/同时发/发到两个平台 | `social_post` | `/post` |
| 一键发文/热点发文/蹭热点发文/自动发文 | `social_hotpost` | `/hotpost` |
| 添加资讯监控/新增资讯监控/监控关键词 + kw | `ops_monitor_add` | `/ops monitor add` |
| 资讯监控列表/新闻监控列表 | `ops_monitor_list` | `/ops monitor list` |
| 运行资讯监控/扫描资讯监控 | `ops_monitor_run` | `/ops monitor run` |

### 3.3b 闲鱼 BI 触发词

| 触发文本 | Action Type | Maps To |
|----------|-------------|---------|
| 闲鱼报告/闲鱼数据/闲鱼报表/闲鱼分析 | `xianyu_report` | `/xianyu_report` |
| 商品排行/哪个商品卖得好/热销排行 | `xianyu_report` | `/xianyu_report` |
| 咨询高峰/什么时候咨询最多 | `xianyu_report` | `/xianyu_report` |
| 转化率/转化漏斗/闲鱼转化 | `xianyu_report` | `/xianyu_report` |
| 闲鱼风格/闲鱼回复风格/客服风格/AI客服风格 | `xianyu_style_show` | `/xianyu_style show` |
| 闲鱼常见问题/闲鱼FAQ | `xianyu_style_faq_list` | `/xianyu_style faq list` |

### 3.4 投资/交易触发词

| 触发文本 | Action Type | Maps To |
|----------|-------------|---------|
| 开始投资/自动投资/帮我投资/一键投资/找机会/自动交易/今天买什么/有什么机会 | `auto_invest` | `_auto_invest` |
| 扫描/扫一下/看看市场/市场扫描/全市场 | `scan` | `/scan` |
| 分析/技术分析/看看/研究 + SYMBOL | `ta` | `/ta` |
| SYMBOL + 信号/买卖/怎么样/能买吗 | `signal` | `/signal` |
| SYMBOL + 多少钱/股价/价格/行情 | `quote` | `/quote` |
| 查/看 + 行情/价格 + SYMBOL | `quote` | `/quote` |
| 市场概览/大盘/今天行情/行情怎么样 | `market` | `/market` |
| 我的持仓/仓位/组合/资产/投资组合 | `portfolio` | `/portfolio` |
| IBKR/盈透/真实/实盘 + 持仓/仓位 | `positions` | `/ipositions` |
| 绩效/战绩/成绩/表现/胜率/盈亏/收益率 | `performance` | `/performance` |
| 复盘/总结今天交易/回顾/检讨/反思 | `review` | `/review` |
| 交易日志/交易记录/交易历史 | `journal` | `/journal` |
| 风控/风险/熔断 | `risk` | `/risk` |
| 持仓监控/监控状态/止损状态/止盈 | `monitor` | `/monitor` |
| 交易系统/系统状态/全部状态 | `tradingsystem` | `/tradingsystem` |
| 启动自动/开启自动/自动交易启动 | `autotrader_start` | `/autotrader start` |
| 停止自动/关闭自动/自动交易停止 | `autotrader_stop` | `/autotrader stop` |
| 回测/测试策略/backtest + SYMBOL | `backtest` | `/backtest` |
| 蒙特卡洛(模拟) + SYMBOL | `backtest` | `/backtest monte SYMBOL` |
| 参数优化/优化参数 + SYMBOL | `backtest` | `/backtest optimize SYMBOL` |
| 前进分析/walk forward + SYMBOL | `backtest` | `/backtest walkforward SYMBOL` |
| 再平衡/调仓/rebalance/配置组合 | `rebalance` | `/rebalance` |
| 投资/讨论/分析 + 一下 + 话题 | `invest` | `/invest` |

### 3.5 购物 & 降价监控触发词

| 触发文本 | Action Type | Maps To |
|----------|-------------|---------|
| 帮我找便宜的X / 比较一下X的价格 / X哪里买最便宜 | `smart_shop` | 比价搜索 |
| 帮我盯着X，降到N告诉我 | `pricewatch_add` | `/pricewatch add X N` |
| X降价提醒 N / X降到N提醒我 | `pricewatch_add` | `/pricewatch add X N` |
| 降价监控 / 我的监控 / 价格提醒列表 | `pricewatch_list` | `/pricewatch list` |

### 3.6 导出触发词

| 触发文本 | Action Type | Maps To |
|----------|-------------|---------|
| 导出记账 / 导出账单 / 导出支出 / 导出开支 [N天] | `export_expenses` | `/export expenses [N]` |
| 导出闲鱼 / 闲鱼报表导出 / 闲鱼订单导出 [N天] | `export_xianyu` | `/export xianyu [N]` |

### 3.7 情报命令 — `IntelCommandMixin` (cmd_intel_mixin.py, ~300 行)

| # | 命令 | Handler | 说明 | BotFather |
|---|------|---------|------|:-:|
| 96 | `/intel` | `cmd_intel` | 全球情报速递（交互式菜单 + 分类查询 + 搜索） | N |

**Inline 回调按钮:**

| callback_data | Handler | 说明 |
|---------------|---------|------|
| `intel_cat:<key>` | `handle_intel_callback` | 行业分类情报查询 |
| `intel_reg:<key>` | `handle_intel_callback` | 地区情报查询 |
| `intel_brief` | `handle_intel_callback` | 生成每日综合情报简报 |

### 3.8 微信领券 — `IntelCommandMixin` (cmd_intel_mixin.py, 共用)

| # | 命令 | Handler | 说明 | BotFather |
|---|------|---------|------|:-:|
| 97 | `/coupon` | `cmd_coupon` | 微信全平台自动领券 | N |
| 98 | `/test_token` | `cmd_test_token` | 测试领券 Token 有效性 | N |
| 99 | `/set_coupon_token` | `cmd_set_coupon_token` | 设置微信领券 Token | N |

---

## 微信端编号命令映射

定义在 `wechat.py`。微信端不支持 `/` 斜杠命令，用户发送数字编号触发对应功能。

### 100-109: AI & 基础

| 编号 | 映射命令 | 说明 |
|------|----------|------|
| 100 | `/help` | 帮助菜单 |
| 101 | `/clear` | 清空对话 |
| 102 | `/status` | Bot 状态 |
| 103 | `/draw` | AI 生图 |
| 104 | `/news` | 科技早报 |
| 105 | `/tts` | 文字转语音 |
| 106 | `/qr` | 生成二维码 |

### 200-221: 投资分析

| 编号 | 映射命令 | 说明 |
|------|----------|------|
| 200 | `/quote` | 行情查询 |
| 201 | `/market` | 市场概览 |
| 202 | `/portfolio` | 投资组合 |
| 203 | `/ta` | 技术分析 |
| 204 | `/signal` | 买卖信号 |
| 205 | `/scan` | 市场扫描 |
| 206 | `/chart` | K线图 |
| 207 | `/calc` | 仓位计算器 |
| 208 | `/trades` | 交易记录 |
| 209 | `/performance` | 绩效仪表盘 |
| 210 | `/review` | AI 复盘 |
| 211 | `/journal` | 交易日志 |
| 212 | `/watchlist` | 自选股 |
| 213 | `/risk` | 风控状态 |
| 214 | `/monitor` | 持仓监控 |
| 215 | `/tradingsystem` | 交易系统状态 |
| 216 | `/backtest` | 回测 |
| 217 | `/invest` | AI 投资会议 |
| 218 | `/equity` | 权益曲线 |
| 219 | `/targets` | 盈利目标进度 |
| 220 | `/accuracy` | AI 预测准确率 |
| 221 | `/weekly` | 综合周报 |

### 230-235: IBKR 实盘

| 编号 | 映射命令 | 说明 |
|------|----------|------|
| 230 | `/ibuy` | IBKR 买入 |
| 231 | `/isell` | IBKR 卖出 |
| 232 | `/ipositions` | IBKR 持仓 |
| 233 | `/iorders` | IBKR 挂单 |
| 234 | `/iaccount` | IBKR 账户 |
| 235 | `/icancel` | 取消订单 |

### 300-308: 社媒

| 编号 | 映射命令 | 说明 |
|------|----------|------|
| 300 | `/hot` | 热点发文 |
| 301 | `/post` | 双平台发文 |
| 302 | `/xpost` | 发 X |
| 303 | `/xhspost` | 发小红书 |
| 304 | `/social_plan` | 发文计划 |
| 305 | `/social_persona` | 社媒人设 |
| 306 | `/topic` | 题材研究 |
| 307 | `/social_report` | 社媒报告 |
| 308 | `/social_calendar` | 内容日历 |

### 400-407: 闲鱼

| 编号 | 映射命令 | 说明 |
|------|----------|------|
| 400 | `/xianyu` | 闲鱼客服控制 |
| 401 | `/xianyu_report` | 闲鱼报表 |
| 402 | `/xianyu_style` | 客服风格配置 |
| 403 | `/ship` | 卡券管理 |
| 404 | `/pricewatch` | 降价监控 |
| 405 | `/deals` | 折扣搜索/比价 |
| 406 | `/coupon` | 微信领券 |
| 407 | `/intel` | 全球情报 |

### 500-503: 生活

| 编号 | 映射命令 | 说明 |
|------|----------|------|
| 500 | `/brief` | 执行简报 |
| 501 | `/bill` | 生活账单 |
| 502 | `/export` | 数据导出 |
| 503 | `/ops` | 自动化工作台 |

### 600-606: 系统

| 编号 | 映射命令 | 说明 |
|------|----------|------|
| 600 | `/memory` | Bot 记忆管理 |
| 601 | `/settings` | 个人设置 |
| 602 | `/model` | 当前模型 |
| 603 | `/pool` | API 池状态 |
| 604 | `/perf` | 性能指标 |
| 605 | `/cost` | 成本/配额 |
| 606 | `/config` | 运行配置 |

---

## 三、依赖清单


> 最后更新: 2026-05-01 | 补齐开发依赖 ruff，修复 Makefile lint 工具链缺口

## 搬运的高星项目 (38 个, 累计 ~473k Stars)

| 包 | Stars | 用途 | 文件 | 版本 |
|----|-------|------|------|------|
| crawl4ai | 62.4k | 购物比价引擎 | shopping/crawl4ai_engine.py | >=0.6.0 |
| RestrictedPython | 1.2k | 代码沙箱安全执行 | tools/code_tool.py | >=8.0 |
| jieba | 34.8k | 中文分词+意图识别 | core/intent_parser.py | >=0.42.1 |
| loguru | 23.7k | 全局结构化日志 | log_config.py | >=0.7.0 |
| plotly | 18.4k | K线图/饼图/瀑布图 | charts.py | >=6.0.0 |
| Apprise | 16.1k | 100+渠道通知 | notifications.py | >=1.9.0 |
| openpyxl | 12k | Excel 导出 | tools/export_service.py | >=3.1.0 |
| instructor | 10k | 结构化 LLM 输出 | structured_llm.py | >=1.7.0 |
| edge-tts | 10.3k | 零成本语音合成 | tts_engine.py | >=6.0.0 |
| Phoenix OTEL | 9k | LLM 可观测性 | observability.py | >=0.1.0 |
| vectorbt | 6.9k | 向量化策略回测 | modules/investment/backtester_vbt.py | >=0.26.0 |
| tenacity | 6k | 指数退避真重试 | core/self_heal.py | >=9.0.0 |
| pandas-ta | 5k | 标准技术指标 | strategy_engine.py | >=0.3.14b1 |
| quantstats | 4.8k | 回测报告+VaR/CVaR风控 | backtester_vbt.py, risk_var.py | >=0.0.62 |
| qrcode | 4.9k | 二维码生成 | tools/qr_service.py | >=7.0 |
| **PyBroker** | **3.3k** | **Numba加速回测+Bootstrap验证** | **modules/investment/backtester_pybroker.py** | **>=1.2.12** |
| ~~diskcache~~ | 2.8k | ~~LLM 响应缓存~~ | ~~llm_cache.py~~ | ~~>=5.6.0~~ | ❌ 已移除 (CVE-2025-69872)，替换为自研 `src/utils_cache.py` (sqlite3 标准库) |
| fpdf2 | 1.5k | PDF 报告 | tools/pdf_report.py | ==2.7.9 | ⚠️ 已注释 (HI-366) |
| stamina | 1.4k | 声明式重试 | resilience.py | >=24.1.0,<26 |
| kaleido | 1.2k | Plotly 静态导出 | charts.py | >=0.2.0 |
| mistletoe | 1k | Telegram MD 渲染 | telegram_markdown.py | >=1.4.0 |
| PyrateLimiter | 485 | API 令牌桶限流 | resilience.py | >=3.0.0 |
| feedparser | 9.8k | RSS/Atom 解析 | news_fetcher.py | >=6.0.0 |
| snownlp | 6k | 中文情感分析 | social_tools.py | >=0.12.3 |
| textblob | 9k | 英文情感分析 | social_tools.py | >=0.18.0 |
| PyPortfolioOpt | 4.6k | 投资组合有效前沿优化 | rebalancer.py | >=1.5.0 |
| exchange-calendars | 4.1k | 全球交易所日历 (50+) | auto_trader.py | >=4.5.0 |
| alpaca-py | 1k | Alpaca 券商 SDK | alpaca_bridge.py | >=0.30.0 |
| composio-core | 20k | 250+ 外部服务 SDK (可选) | integrations/composio_bridge.py | >=0.7.0 |
| tvscreener | — | TradingView 股票筛选 API | universe.py | >=0.5.0 |
| price-parser | 4.2k | 智能价格提取 (全球货币) | shopping/price_engine.py | >=0.3.0 |
| tweepy | 10.6k | Twitter/X 官方 SDK | execution/social/x_platform.py | >=4.14.0 |
| twikit | 2k | X/Twitter Cookie 持久化登录 | execution/social/x_platform.py | >=2.0.0 |
| xhs | 3k | 小红书 API 客户端 (Cookie 登录) | execution/social/xhs_platform.py | >=0.2.0 |
| dateparser | 2.5k | 自然语言时间解析 (13种语言) | execution/life_automation.py | >=1.2.0 |
| humanize | 2.9k | 自然语言时间/大小/数字格式化 | notify_style.py | >=4.9.0 |


## 原有核心依赖

| 包 | 用途 | 版本 |
|----|------|------|
| python-telegram-bot | Telegram Bot API | ~=22.5 |
| litellm | 统一 LLM 路由 | >=1.70.0 |
| mem0ai | AI 记忆层 | >=0.1.30 |
| browser-use | AI 浏览器代理 | >=0.2.0 |
| langfuse | LLM 观测平台 | >=2.0.0 |
| crewai | 多 Agent 协作 | >=0.80.0 |
| fastapi | 内控 API | >=0.115.0 |
| httpx | HTTP 客户端 | ~=0.28.1 |
| yfinance | 美股数据 | ~=1.1.0 |
| akshare | A股数据 | >=1.15.0 |
| ccxt | 加密货币 108+ 交易所 | >=4.4.0 |
| DrissionPage | 反检测浏览器 | >=4.1.0 |
| apscheduler | 定时任务 | >=3.10.0 |
| pandas / numpy / ta | 数据分析+技术指标 | ~=2.3.3 / ~=2.0.2 / ~=0.11.0 |
| optuna | 超参数优化 | >=4.0.0 |
| python-dotenv | 环境变量加载 (.env) | ~=1.2.1 |
| beautifulsoup4 | HTML 解析 | ~=4.14.3 |
| requests | HTTP 客户端 (同步) | ~=2.32.0 |
| flask | 部署服务器 (deployer/) | >=3.0.0 |
| aiohttp | 异步 HTTP (evolution/) | >=3.9.0 |
| json-repair | JSON 容错解析 (LLM 输出修复) | ~=0.30.0 |
| pydantic-settings | 配置管理 (类型校验+env) | ~=2.7.0 |
| websockets | 闲鱼 WebSocket 实时聊天 | ~=13.0 |
| openai | OpenAI SDK (闲鱼/Agent) | >=1.68.2 |
| ib_async | IBKR 券商对接 (ib_insync 社区接力 fork) | >=2.1.0 |
| tavily-python | AI 搜索引擎 SDK | >=0.5.0 |
| smolagents | 轻量 Agent 框架 (HuggingFace) | >=1.0.0 |
| docling | 文档理解引擎 (PDF/DOCX→MD) | >=2.0.0 |
| pybreaker | 工业级熔断器 (self_heal.py) | >=1.4.0 |

## Python 版本约束
- 当前: **Python 3.12** (venv: `.venv312`)
- 注意: `fpdf2` 锁定 `==2.7.9`
- 注意: `pandas-ta` 在 PyPI 上无法安装 (需 pip install from git)

## R8 新增/修正 (2026-03-27)

| 包 | 版本 | 用途 | 来源 |
|---|---|---|---|
| `playwright` | `>=1.40.0` | 浏览器自动化 (browser-use 底层依赖) | R1 审计新增 |
| `uvicorn[standard]` | `~=0.32.0` | ASGI 服务器 | requirements.txt 已有但注册表漏登 |
| `pyautogui` | `>=0.9.54` | macOS 桌面控制 | requirements.txt 已有但注册表漏登 |
| `pyobjc-core` | `>=10.0` | macOS Quartz 底层 | requirements.txt 已有但注册表漏登 |
| `arize-phoenix-otel` | `>=0.1.0` | Phoenix OTEL 客户端 | requirements.txt 已有但注册表漏登 |
| `openinference-instrumentation-litellm` | `>=0.1.0` | LiteLLM OTEL 插桩 | requirements.txt 已有但注册表漏登 |
| `pytest` / `pytest-asyncio` / `pytest-cov` | 多版本 | 测试框架 | requirements-dev.txt |
| `ruff` | `>=0.8.0,<1.0.0` | Python 代码检查与格式化 | requirements-dev.txt |

**已移除**: `tiktoken` — 注册表曾列出但 requirements.txt 未包含，代码中也未使用 (P5审计已从搬运表中替换为 RestrictedPython)
- 最低支持: Python 3.10 (`docling>=2.0.0` 要求)

---

## 四、Python 模块索引


> 最后更新: 2026-04-19 | 新增 3 个模块 (285→288): ai-hedge-fund 估值 + Hurst + 大师 Agent

---

## 新增模块 (2026-04-19) — ai-hedge-fund 集成

### valuation_models.py — 4 种投资估值模型

| 属性 | 值 |
|------|-----|
| 路径 | `packages/clawbot/src/trading/valuation_models.py` |
| 行数 | 212 |
| 导入方 | `test_valuation_models` |
| 依赖 | 无（纯数学计算） |

**Public API:**
- `calculate_intrinsic_value_dcf()` — DCF 三场景概率加权估值
- `calculate_owner_earnings()` — 巴菲特持有人收益法
- `calculate_ev_ebitda_value()` — 企业价值倍数隐含估值
- `calculate_residual_income_value()` — 残余收入模型
- `calculate_wacc()` — 加权平均资本成本
- `get_valuation_summary()` — 整合 4 大模型的综合信号

### hurst_analysis.py — Hurst 指数 + 统计套利

| 属性 | 值 |
|------|-----|
| 路径 | `packages/clawbot/src/trading/hurst_analysis.py` |
| 行数 | 150 |
| 导入方 | `test_hurst_analysis` |
| 依赖 | 标准库 (`math`, `statistics`) |

**Public API:**
- `calculate_hurst_exponent(prices)` — R/S 分析法计算 Hurst 指数
- `classify_regime(hurst)` — 市场机制分类 (trending/mean_reverting/random)
- `calculate_stat_arb_signals(prices, lookback)` — z-score 统计套利信号

### master_analysts.py — 5 位投资大师人格 Agent

| 属性 | 值 |
|------|-----|
| 路径 | `packages/clawbot/src/trading/master_analysts.py` |
| 行数 | 233 |
| 导入方 | `test_master_analysts` |
| 依赖 | 标准库 (`asyncio`, `json`, `re`) |

**Public API:**
- `MASTER_PROMPTS` — 5 位大师的系统提示词字典
- `analyze_as_master(master_name, ticker, data, llm_fn)` — 单个大师分析
- `run_master_panel(ticker, data, llm_fn, masters)` — 圆桌并行分析 + 信号聚合

---

## 新增模块 (2026-04-19) — 体验升级三阶段

### input_processor.py — 输入清洗 + 智能键盘

| 属性 | 值 |
|------|-----|
| 路径 | `packages/clawbot/src/bot/input_processor.py` |
| 行数 | 172 |
| 导入方 | `message_mixin`, `callback_mixin`, `test_ai_assistant_features` |
| 依赖 | 标准库 (`re`, `logging`) |

**Public API:**
- `_detect_correction(text)` — 检测用户纠正意图
- `_build_smart_reply_keyboard(text, ...)` — 构建上下文感知的智能回复键盘

### voice_handler.py — 语音消息处理

| 属性 | 值 |
|------|-----|
| 路径 | `packages/clawbot/src/bot/voice_handler.py` |
| 行数 | 140 |
| 导入方 | `message_mixin` (mixin 继承) |
| 依赖 | `litellm_router` (STT 调用) |

**Public API:**
- `VoiceHandlerMixin` — 语音消息处理 mixin（Groq/OpenAI/Deepgram 三级降级）

### session_tracker.py — 会话恢复追踪

| 属性 | 值 |
|------|-----|
| 路径 | `packages/clawbot/src/bot/session_tracker.py` |
| 行数 | 134 |
| 导入方 | `message_mixin` (mixin 继承) |
| 依赖 | `smart_memory`, `litellm_router` |

**Public API:**
- `SessionTrackerMixin` — 会话恢复检测 + 异步建议更新

### stream_manager.py — 流式输出管理

| 属性 | 值 |
|------|-----|
| 路径 | `packages/clawbot/src/bot/stream_manager.py` |
| 行数 | 52 |
| 导入方 | `message_mixin` (mixin 继承) |
| 依赖 | 标准库 (`asyncio`) |

**Public API:**
- `StreamManagerMixin` — 流式编辑频率控制 + typing 动画

### perf_metrics.py — 性能度量

| 属性 | 值 |
|------|-----|
| 路径 | `packages/clawbot/src/perf_metrics.py` |
| 行数 | 205 |
| 导入方 | `brain`, `message_mixin`, `auto_trader`, `litellm_router`, `api/routers/system`, `cmd_ops_mixin` |
| 依赖 | 标准库 (`time`, `threading`, `statistics`, `functools`) |

**Public API:**
- `PerfTracker` — 线程安全性能指标追踪器（环形缓冲区，最多 1000 条/指标）
- `get_tracker()` — 获取全局单例
- `perf_timer(name)` — 装饰器，自动记录函数耗时（支持 sync/async）

---

## 新增模块 (2026-04-19) — 社媒适配器模式

### platform_adapter.py — 社媒平台适配器基类 + 注册表

| 属性 | 值 |
|------|-----|
| 路径 | `packages/clawbot/src/execution/social/platform_adapter.py` |
| 行数 | 101 |
| 导入方 | `brain_exec_social`, `rpc`, `drafts`, `social_scheduler`, `content_pipeline`, `x_adapter`, `xhs_adapter` |
| 依赖 | 标准库 (`abc`, `logging`, `typing`) |

**Public API:**
- `SocialPlatformAdapter` — 抽象基类（platform_id / display_name / aliases / publish / normalize_content / build_worker_payload / worker_action）
- `register_adapter(adapter)` — 注册适配器到全局注册表
- `get_adapter(platform)` — 按名称/别名查找适配器
- `get_all_adapters()` — 获取所有已注册适配器（去重）
- `list_supported_platforms()` — 返回支持的平台 ID 列表

### x_adapter.py — X/Twitter 平台适配器

| 属性 | 值 |
|------|-----|
| 路径 | `packages/clawbot/src/execution/social/x_adapter.py` |
| 行数 | 58 |
| 导入方 | `platform_adapter._auto_register()` |
| 依赖 | `platform_adapter.SocialPlatformAdapter`, `x_platform.publish_x_post` |

**Public API:**
- `XPlatformAdapter` — platform_id="x", aliases=["twitter","tw"]

### xhs_adapter.py — 小红书平台适配器

| 属性 | 值 |
|------|-----|
| 路径 | `packages/clawbot/src/execution/social/xhs_adapter.py` |
| 行数 | 71 |
| 导入方 | `platform_adapter._auto_register()` |
| 依赖 | `platform_adapter.SocialPlatformAdapter`, `xhs_platform.publish_xhs_article` |

**Public API:**
- `XhsPlatformAdapter` — platform_id="xiaohongshu", aliases=["xhs","小红书"]

---

## 新增模块 (2026-04-16 R4)

### db_utils.py — 全局 SQLite 连接工厂

| 属性 | 值 |
|------|-----|
| 路径 | `packages/clawbot/src/db_utils.py` |
| 行数 | 64 |
| 导入方 | `execution/_db`, `license_manager`, `novel_writer`, `xianyu_context`, `invest_tools`, `auto_shipper`, `trading_journal`, `cost_analyzer` |
| 依赖 | 标准库 (`sqlite3`, `os`, `logging`, `contextlib`) |

**Public API:**
- `get_conn(db_path, *, row_factory=None)` — contextmanager，统一 WAL + busy_timeout=5000 + 文件权限保护 + 异常自动回滚

---

## 新增模块 (2026-04-16 R1)

### risk_var.py — VaR/CVaR 风险度量 Mixin

| 属性 | 值 |
|------|-----|
| 路径 | `packages/clawbot/src/risk_var.py` |
| 行数 | 271 |
| 导入方 | `risk_manager.py` (Mixin 继承) |
| 依赖 | `numpy`, `quantstats` (可选，缺失时用内置计算) |

**Public API (通过 RiskManager 暴露):**
- `calc_var(confidence)` — 历史模拟法 VaR
- `calc_cvar(confidence)` — 条件风险价值 / Expected Shortfall
- `calc_sortino()` — Sortino Ratio (下行风险调整收益)
- `calc_tail_ratio()` — 尾部比率 (右尾/左尾)
- `calc_calmar()` — Calmar Ratio (收益/最大回撤)
- `get_var_metrics()` — 完整风险指标集
- `check_var_limit(proposed_loss)` — check_trade() 第18项检查

---

### backtester_pybroker.py — PyBroker 回测引擎桥接

| 属性 | 值 |
|------|-----|
| 路径 | `packages/clawbot/src/modules/investment/backtester_pybroker.py` |
| 行数 | 350 |
| 导入方 | `bot/cmd_trading_mixin.py` (/backtest --pb) |
| 依赖 | `lib-pybroker>=1.2.12` (可选，缺失时降级) |

**Public API:**
- `PyBrokerBacktester.run_backtest(symbol, strategy_name, period)` — 单策略回测
- `PyBrokerBacktester.run_compare(symbol, period)` — 多策略对比
- `get_pybroker_backtester()` — 全局单例
- 策略: `pb_ma_cross` / `pb_rsi` / `pb_momentum`

---

### brain_exec_invest.py — 投资执行器 Mixin

| 属性 | 值 |
|------|-----|
| 路径 | `packages/clawbot/src/core/brain_exec_invest.py` |
| 行数 | ~160 |
| 导入方 | `brain_executors.py` (Mixin 继承) |

### brain_exec_social.py — 社媒执行器 Mixin

| 属性 | 值 |
|------|-----|
| 路径 | `packages/clawbot/src/core/brain_exec_social.py` |
| 行数 | ~120 |
| 导入方 | `brain_executors.py` (Mixin 继承) |

### brain_exec_life.py — 生活服务执行器 Mixin

| 属性 | 值 |
|------|-----|
| 路径 | `packages/clawbot/src/core/brain_exec_life.py` |
| 行数 | ~250 |
| 导入方 | `brain_executors.py` (Mixin 继承) |

### brain_exec_tools.py — 工具+系统执行器 Mixin

| 属性 | 值 |
|------|-----|
| 路径 | `packages/clawbot/src/core/brain_exec_tools.py` |
| 行数 | ~110 |
| 导入方 | `brain_executors.py` (Mixin 继承) |

---

## 新增模块 (2026-04-15)

### local_llm.py — 本地 LLM 适配器

| 属性 | 值 |
|------|-----|
| 路径 | `packages/clawbot/src/tools/local_llm.py` |
| 行数 | 253 |
| 导入方 | `core/intent_parser.py` (本地预筛查) |
| 依赖 | `httpx` (已安装), 无新增第三方依赖 |

**Public API:**
- `LocalLLMAdapter(backend, base_url)` — 初始化本地 LLM 适配器
  - `classify_intent(text)` — 意图分类（返回意图标签）
  - `summarize_context(messages)` — 上下文摘要
  - `extract_sentiment(text)` — 情感提取
  - `xianyu_quick_reply(buyer_msg, item_info)` — 闲鱼快速回复
  - `extract_keywords(text)` — 关键词提取
- `detect_local_llm()` — 自动探测 Ollama/LM Studio/HF Inference Server
- 支持后端: `ollama` (默认 11434), `lmstudio` (默认 1234), `huggingface` (默认 8080)

---

### controls.py — 控制面板 API 端点

| 属性 | 值 |
|------|-----|
| 路径 | `packages/clawbot/src/api/routers/controls.py` |
| 行数 | 225 |
| 导入方 | `api/routers/__init__.py` → `api/server.py` |
| 依赖 | `fastapi`, `pydantic` |

**Public API (HTTP 端点):**
- `GET /api/v1/controls/trading` — 获取交易控件状态
- `PUT /api/v1/controls/trading` — 更新交易控件
- `GET /api/v1/controls/social` — 获取社媒控件状态
- `PUT /api/v1/controls/social` — 更新社媒控件
- `GET /api/v1/controls/scheduler` — 获取调度器状态
- `PUT /api/v1/controls/scheduler` — 更新调度器设置
- `GET /api/v1/controls/settings` — 获取全局设置
- `PUT /api/v1/controls/settings` — 更新全局设置
- `GET /api/v1/controls/all` — 获取所有控件状态（聚合）

**状态持久化:** `data/controls_state.json`

---

## 新增模块 (2026-04-11)

### risk_extreme_market.py — 极端行情检测 Mixin

| 属性 | 值 |
|------|-----|
| 路径 | `packages/clawbot/src/risk_extreme_market.py` |
| 行数 | 132 |
| 导入方 | `risk_manager.py` (Mixin 继承) |
| 依赖 | `src.utils.now_et` |

**Public API (通过 RiskManager 暴露):**
- `check_extreme_market(symbol, current_atr, avg_atr, price_change_pct, vix, spread_pct)` — ATR飙升/闪崩/VIX恐慌/价差检测
- `record_extreme_event(event_type, details)` — 记录极端行情事件并启动冷却
- `is_in_extreme_cooldown()` — 检查是否在极端行情冷却期

---

### risk_kelly.py — 凯利公式仓位计算 Mixin

| 属性 | 值 |
|------|-----|
| 路径 | `packages/clawbot/src/risk_kelly.py` |
| 行数 | 132 |
| 导入方 | `risk_manager.py` (Mixin 继承) |
| 依赖 | 无外部依赖 |

**Public API (通过 RiskManager 暴露):**
- `calc_kelly_quantity(entry_price, stop_loss, take_profit, capital)` — 基于凯利公式计算最优仓位
- `_get_trade_stats()` — 从交易历史计算胜率和盈亏比

---

### risk_sector.py — 板块集中度与风险敞口 Mixin

| 属性 | 值 |
|------|-----|
| 路径 | `packages/clawbot/src/risk_sector.py` |
| 行数 | 156 |
| 导入方 | `risk_manager.py` (Mixin 继承) |
| 依赖 | `yfinance` (可选，缺失时降级为"未知") |

**Public API (通过 RiskManager 暴露):**
- `_check_sector_concentration(symbol, new_value, current_positions)` — 板块集中度检查
- `lookup_sectors(symbols)` — 查询标的所属行业（带缓存）
- `get_risk_exposure_summary(positions, cash)` — 风险敞口摘要（供 /portfolio 展示）

---

### auto_trader_filters.py — 候选筛选与提案生成 Mixin

| 属性 | 值 |
|------|-----|
| 路径 | `packages/clawbot/src/auto_trader_filters.py` |
| 行数 | 157 |
| 导入方 | `auto_trader.py` (Mixin 继承) |
| 依赖 | `src.models.TradeProposal`, `src.utils.env_bool`, `src.utils.env_int` |

**Public API (通过 AutoTrader 暴露):**
- `_filter_candidates(signals)` — 自适应阈值多层候选筛选
- `_generate_proposal(candidate)` — 机械策略提案生成（含 ATR 止损）
- `_enrich_candidates_with_broker_quotes(candidates)` — IBKR 实时快照刷新候选报价

---

### auto_trader_review.py — 收盘复盘 Mixin

| 属性 | 值 |
|------|-----|
| 路径 | `packages/clawbot/src/auto_trader_review.py` |
| 行数 | 86 |
| 导入方 | `auto_trader.py` (Mixin 继承) |
| 依赖 | `src.trading_pipeline.TraderState`, `src.trading_journal`, `src.utils.today_et_str` |

**Public API (通过 AutoTrader 暴露):**
- `_run_review()` — 收盘自动复盘（交易总结 + 教训持久化 + Telegram 通知）

---

### daily_brief_llm.py — 日报 LLM 辅助分析

| 属性 | 值 |
|------|-----|
| 路径 | `packages/clawbot/src/execution/daily_brief_llm.py` |
| 行数 | 263 |
| 导入方 | `daily_brief.py` (re-export) |
| 依赖 | `src.constants.FAMILY_QWEN`, `src.litellm_router.free_pool` |

**Public API:**
- `_analyze_news_with_llm(headlines, holdings)` — LLM 新闻分析 + 持仓关联
- `_generate_executive_summary(sections_data)` — 2句话执行摘要 (LLM/模板降级)
- `_generate_daily_recommendations(sections_data)` — 3条可操作建议 (LLM)

---

### daily_brief_data.py — 日报数据采集

| 属性 | 值 |
|------|-----|
| 路径 | `packages/clawbot/src/execution/daily_brief_data.py` |
| 行数 | 257 |
| 导入方 | `daily_brief.py`, `weekly_report.py` |
| 依赖 | `src.execution._db.get_conn` |

**Public API:**
- `_section(title, items)` — 构建 format_digest section tuple
- `_get_timestamp_tag()` — 时间戳标签
- `_get_yesterday_comparison(db_path)` — 昨日指标对比数据
- `_calc_deltas(today_data, yesterday_data)` — 今日 vs 昨日 delta
- `_format_delta(value, unit)` — delta 格式化 (↑/↓)
- `_build_today_agenda(db_path)` — 今日日程聚合 (5个数据源)
- `_fetch_trending_projects()` — GitHub Trending 项目发现

---

### weekly_report.py — 综合周报

| 属性 | 值 |
|------|-----|
| 路径 | `packages/clawbot/src/execution/weekly_report.py` |
| 行数 | 211 |
| 导入方 | `daily_brief.py` (re-export), `scheduler.py`, `cmd_analysis_mixin.py` |
| 依赖 | `src.notify_style`, `src.execution.daily_brief_data` |

**Public API:**
- `weekly_report()` — 生成综合周报 (社媒+闲鱼+成本+目标，4个section)

---

## 新增模块 (2026-04-08)

### slider_solver.py — 闲鱼滑块验证码自动求解器

| 属性 | 值 |
|------|-----|
| 路径 | `packages/clawbot/src/xianyu/slider_solver.py` |
| 行数 | ~480 |
| 导入方 | `scripts/xianyu_login.py` |
| 依赖 | `playwright` (已安装), 无新增第三方依赖 |

**Public API:**
- `SliderSolver` — 异步版滑块求解器 (用于 asyncio 上下文)
  - `.inject_stealth(page)` — 注入反检测 JS
  - `.detect_slider(page)` — 检测页面是否有滑块
  - `.solve(page, max_retries)` — 自动求解滑块
- `SliderSolverSync` — 同步版滑块求解器 (用于 Playwright sync_api)
  - `.detect_slider(page)` / `.solve(page, max_retries)`
- `STEALTH_JS` — 反检测 JavaScript 脚本常量
- `perlin_noise_1d(x, seed_offset)` — 1D Perlin 噪声函数

---

### login_helper.py — 通用登录弹窗工具

| 属性 | 值 |
|------|-----|
| 路径 | `packages/clawbot/src/tools/login_helper.py` |
| 行数 | ~220 |
| 导入方 | `xianyu/xianyu_live.py`, `scripts/social_browser_worker.py` |
| 依赖 | `subprocess`, `asyncio` (无第三方依赖) |

**Public API:**
- `LoginHelper(service_name)` — 初始化登录助手
- `.mac_notify(title, message, sound)` — macOS 通知中心通知
- `.mac_alert(title, message)` — macOS 模态对话框
- `.play_sound(sound_name, repeat)` — 播放系统提示音
- `.open_url(url, bring_to_front)` — 打开浏览器并置前
- `.alert_and_open(url, reason)` — 完整弹窗流程（通知+声音+浏览器+对话框）
- `.wait_for_condition(check_fn, timeout)` — 异步轮询等待登录完成
- `.open_browser_profile(profile_dir, urls)` — 打开 Chrome Profile 登录

---

## 更新模块 (2026-05-03)

### newapi.py — New-API 管理代理路由

| 属性 | 值 |
|------|-----|
| 路径 | `packages/clawbot/src/api/routers/newapi.py` |
| 行数 | ~450 |
| 导入方 | `api/routers/__init__.py` → `api/server.py` |
| 依赖 | `httpx`, `fastapi`, `pydantic` |

**Public API (HTTP 端点):**
- `GET /api/v1/newapi/status` — 检查 New-API 服务状态
- `GET /api/v1/newapi/channels` — 获取通道列表
- `GET /api/v1/newapi/tokens` — 获取令牌列表
- `GET /api/v1/newapi/tokens/search` — 搜索用户令牌，支持名称或 Key 片段
- `POST /api/v1/newapi/tokens` — 创建用户令牌
- `PUT /api/v1/newapi/tokens/{id}` — 编辑用户令牌
- `POST /api/v1/newapi/tokens/{id}/status` — 启用或禁用用户令牌
- `DELETE /api/v1/newapi/tokens/{id}` — 删除令牌
- `POST /api/v1/newapi/channels` — 创建新通道
- `PUT /api/v1/newapi/channels/{id}` — 更新通道
- `DELETE /api/v1/newapi/channels/{id}` — 删除通道
- `POST /api/v1/newapi/channels/{id}/status` — 切换通道启用/禁用
- `GET /api/v1/newapi/logs/self` — 获取当前用户使用记录
- `GET /api/v1/newapi/logs/self/stat` — 获取当前用户用量统计
- `GET /api/v1/newapi/data/self` — 获取当前用户 Token 趋势数据
- `GET /api/v1/newapi/subscriptions/plans` — 获取可售订阅套餐
- `GET /api/v1/newapi/subscriptions/self` — 获取当前用户订阅状态
- `GET /api/v1/newapi/redemptions` — 获取兑换码列表
- `POST /api/v1/newapi/redemptions` — 创建兑换码
- `GET /api/v1/newapi/pricing` — 获取模型价格和可用分组
- `GET /api/v1/newapi/topup/info` — 获取充值配置
- `GET /api/v1/newapi/aff` — 获取邀请返利码
- `POST /api/v1/newapi/aff/transfer` — 把邀请返利转入余额

**认证备注:**
- New-API v1 的 `UserAuth` / `AdminAuth` 会同时校验 access token 和 `New-Api-User` 头。
- ClawBot 代理读取 `NEWAPI_ADMIN_TOKEN` 和 `NEWAPI_ADMIN_USER_ID`，只做请求转发，不复制 New-API 业务规则。

---

## 新增模块 (2026-04-06)

### wechat_coupon.py — 微信笔笔省自动领券

| 属性 | 值 |
|------|-----|
| 路径 | `packages/clawbot/src/execution/wechat_coupon.py` |
| 行数 | ~300 |
| 导入方 | `cmd_intel_mixin.py`, `scheduler.py` |
| 依赖 | `httpx`, `subprocess`, `asyncio` |

**Public API:**
- `auto_claim_coupon()` — 自动领券完整流程（设代理→抓token→POST领券→恢复代理）

### mitm_token_addon.py — mitmproxy token 截取 addon

| 属性 | 值 |
|------|-----|
| 路径 | `packages/clawbot/scripts/mitm_token_addon.py` |
| 行数 | ~80 |
| 导入方 | 由 mitmdump -s 加载 |
| 依赖 | `mitmproxy` |

### worldmonitor_client.py — Worldmonitor 全球情报 API 客户端

| 属性 | 值 |
|------|-----|
| 路径 | `packages/clawbot/src/tools/worldmonitor_client.py` |
| 行数 | ~400 |
| 导入方 | `cmd_intel_mixin.py` |
| 依赖 | `httpx`, `src.utils`, `src.notify_style` (可选) |

**Public API:**
- `fetch_category_news(category, max_items)` — 按行业分类获取情报
- `fetch_region_news(region, max_items)` — 按地区获取情报
- `fetch_news_by_query(query, max_items)` — 关键词搜索情报
- `generate_intel_brief()` — 生成综合每日情报简报
- `format_intel_items(items, max_items)` — 格式化条目为 Telegram HTML
- `get_category_list()` — 返回可用分类列表
- `INDUSTRY_CATEGORIES` / `REGION_CATEGORIES` — 分类常量字典

### cmd_intel_mixin.py — 情报速递命令 Mixin

| 属性 | 值 |
|------|-----|
| 路径 | `packages/clawbot/src/bot/cmd_intel_mixin.py` |
| 行数 | ~300 |
| 导入方 | (已注册到 multi_bot.py) |
| 依赖 | `telegram`, `src.bot.auth`, `src.telegram_ux`, `worldmonitor_client` |

**Public API:**
- `cmd_intel(update, context)` — `/intel` 命令处理器
- `handle_intel_callback(update, context)` — Inline 回调按钮处理


以下模块在 R22-R24 代码架构重构中提取/新增而来。

### 0.0a error_utils.py — API 错误处理工具

| 属性 | 值 |
|------|-----|
| 路径 | `packages/clawbot/src/api/error_utils.py` |
| 行数 | ~17 |
| 导入方 | `api/routers/omega.py`, `trading.py`, `social.py`, `memory.py`, `pool.py`, `system.py`, `shopping.py`, `evolution.py` (8个router) |
| 依赖 | 无 (纯标准库) |

**Public API:**
- `safe_error(e: Exception) -> str` — 将异常转为安全的错误消息，过滤内部路径和技术细节

### 0.0b constants.py — 全局常量

| 属性 | 值 |
|------|-----|
| 路径 | `packages/clawbot/src/constants.py` |
| 行数 | ~22 |
| 导入方 | `real_trending.py`, `github_trending.py`, `price_engine.py`, `xianyu_apis.py`, `xianyu_live.py` (5个文件) |
| 依赖 | 无 |

**Public API:**
- `DEFAULT_USER_AGENT` — 通用 Web 抓取 User-Agent (macOS Chrome)
- `XIANYU_USER_AGENT` — 闲鱼专用 User-Agent (Windows Chrome)

### 0.1 risk_config.py — 风控配置数据类

| 属性 | 值 |
|------|-----|
| 路径 | `packages/clawbot/src/risk_config.py` |
| 行数 | ~110 |
| 导入方 | risk_manager, backtester, trading/_init_system, 多个测试文件 |
| 依赖 | dataclasses, typing |

**Public API:**
- `RiskConfig` — 风控配置数据类 (total_capital, max_position_pct, daily_loss_limit 等 20+ 参数)
- `RiskCheckResult` — 风控检查结果数据类 (allowed, reasons, risk_score, position_size)

### 0.2 trading_memory_bridge.py — 交易记忆桥接

| 属性 | 值 |
|------|-----|
| 路径 | `packages/clawbot/src/trading_memory_bridge.py` |
| 行数 | ~140 |
| 导入方 | multi_main |
| 依赖 | logging, trading_journal |

**Public API:**
- `TradingMemoryBridge` — 将交易事件 (开仓/平仓/复盘) 通过 monkey-patch 写入 SharedMemory
- `trading_memory_bridge` — 全局实例 (绑定到 journal)

### 0.3 broker_selector.py — 券商选择器

| 属性 | 值 |
|------|-----|
| 路径 | `packages/clawbot/src/broker_selector.py` |
| 行数 | ~65 |
| 导入方 | brain_executors, trading/_scheduler_daily, trading/_lifecycle, invest_tools |
| 依赖 | logging, os, broker_bridge |

**Public API:**
- `get_ibkr()` — 懒加载 IBKRBridge 单例
- `ibkr` — 懒代理对象 (向后兼容)
- `get_broker()` — 统一券商选择器 (IBKR > Alpaca > 模拟盘)

### 0.4 cmd_basic/ — 基础命令子包

| 属性 | 值 |
|------|-----|
| 路径 | `packages/clawbot/src/bot/cmd_basic/` |
| 文件数 | 9 (含 __init__.py) |
| 总行数 | ~1616 (原 cmd_basic_mixin.py 拆分 + onboarding_mixin 新增) |
| 导入方 | multi_bot (通过 cmd_basic_mixin.py 转发) |

**子模块:**
- `onboarding_mixin.py` — 新用户引导向导 (ConversationHandler 3步交互式引导)
- `help_mixin.py` — 帮助菜单和老用户欢迎 (cmd_help, _show_returning_user_start, handle_help_callback)
- `status_mixin.py` — 系统状态查询 (cmd_status/metrics/model/pool/keyhealth)
- `settings_mixin.py` — 用户设置 (cmd_settings, handle_settings_callback)
- `memory_mixin.py` — 记忆管理 (cmd_memory, handle_memory/feedback_callback)
- `callback_mixin.py` — 按钮回调 (handle_notify/card/clarification_callback)
- `tools_mixin.py` — 工具命令 (cmd_draw/news/qr/tts/agent, handle_inline_query)
- `context_mixin.py` — 上下文管理 (cmd_context/compact/clear/voice/lanes)

---

## 1. 优化期间新建的模块

以下模块在 Tier 1-5 优化期间创建，从高星开源项目搬运核心逻辑并适配。

### 1.0 auth.py — 权限装饰器

| 属性 | 值 |
|------|-----|
| 路径 | `packages/clawbot/src/bot/auth.py` |
| 行数 | 26 |
| 导入方 | cmd_basic_mixin, cmd_execution_mixin, cmd_analysis_mixin, cmd_invest_mixin, cmd_trading_mixin, cmd_ibkr_mixin, cmd_collab_mixin |
| 依赖 | functools, telegram |

**Public API:**
- `requires_auth(func)` — 装饰器: 检查 `self._is_authorized(update.effective_user.id)`，未授权时静默返回

### 1.0.1 error_messages.py — 统一错误消息模板

| 属性 | 值 |
|------|-----|
| 路径 | `packages/clawbot/src/bot/error_messages.py` |
| 行数 | 72 |
| 导入方 | api_mixin, cmd_basic_mixin, cmd_trading_mixin, message_mixin, telegram_ux, xianyu_agent |
| 依赖 | (无外部依赖) |

**Public API:**
- `error_generic(detail)` — 通用错误 (⚠️ 处理请求时出错...)
- `error_rate_limit()` — 请求频率超限
- `error_ai_busy()` — AI 服务繁忙/超时
- `error_not_found(item)` — 资源未找到
- `error_permission()` — 无权限
- `error_invalid_input(hint)` — 输入格式错误
- `error_ai_empty()` — AI 返回空内容
- `error_tool_abuse()` — 工具调用过多
- `error_network()` — 网络连接问题
- `error_auth()` — API 认证失败
- `error_circuit_open()` — 熔断器打开

### 1.1 telegram_ux.py — Telegram UX 增强层

| 属性 | 值 |
|------|-----|
| 路径 | `packages/clawbot/src/telegram_ux.py` |
| 行数 | 728 |
| 搬运自 | python-telegram-bot 最佳实践 + grammY (15k⭐) + freqtrade + n3d1117/chatgpt-telegram-bot (3.5k⭐) |
| 导入方 | cmd_basic_mixin, cmd_invest_mixin, cmd_trading_mixin, cmd_analysis_mixin, cmd_execution_mixin, message_mixin |
| 依赖 | telegram, matplotlib, plotly (可选) |

**Public API:**
- `class TypingIndicator(chat_id, context, interval)` — 持续 typing 上下文管理器
- `class ProgressTracker(chat_id, context, title)` — 长操作进度反馈
- `class StreamingEditor(chat_id, context)` — LLM 流式消息编辑器
- `class TelegramProgressBar(total, label, message, context)` — tqdm 风格进度条
- `class NotificationBatcher(send_func, flush_interval)` — 通知合并器
- `with_typing(func)` — typing 装饰器
- `send_error_with_retry(update, context, error, retry_command)` — 错误恢复 + 重试按钮
- `format_trade_card(trade) -> str` — 交易通知卡片 (HTML)
- `format_portfolio_card(positions, cash) -> str` — 持仓概览卡片 (HTML)
- `format_quote_card(data) -> str` — 行情卡片 (HTML)
- `generate_equity_chart(equity_curve, title) -> BytesIO` — 权益曲线图
- `generate_pnl_chart(trades, title) -> BytesIO` — PnL 柱状图
- `generate_portfolio_pie(positions, title) -> BytesIO` — 持仓饼图
- `generate_sector_pie(sector_values, title) -> BytesIO` — 行业分布饼图
- `send_chart(update, context, chart_buf, caption)` — 发送图表 + 降级

### 1.2 notify_style.py — 统一排版引擎

| 属性 | 值 |
|------|-----|
| 路径 | `packages/clawbot/src/notify_style.py` |
| 行数 | 398 |
| 搬运自 | 内部设计规范 |
| 导入方 | cmd_execution_mixin, message_mixin |

### 1.3 wechat_bridge.py — 微信通知桥接

| 属性 | 值 |
|------|-----|
| 路径 | `packages/clawbot/src/wechat_bridge.py` |
| 行数 | 120 |
| 搬运自 | 原创 — 连接 Python 后端通知 → OpenClaw 微信插件 (contextToken TTL 30min + 3次重试) |
| 导入方 | `notifications.py` |

**Public API:**
- `is_wechat_notify_enabled() -> bool` — 检查微信通知是否启用
- `send_to_wechat(text, user_id) -> bool` — 异步推送通知到微信
- `send_to_wechat_sync(text, user_id) -> bool` — 同步版本

**环境变量:**
- `WECHAT_NOTIFY_ENABLED=true` — 启用微信通知
- `WECHAT_NOTIFY_USER=xxx@im.wechat` — 微信管理员用户 ID

### 1.4 notifications.py — 多渠道通知管理器

| 属性 | 值 |
|------|-----|
| 路径 | `packages/clawbot/src/notifications.py` |
| 行数 | 595 |
| 搬运自 | caronc/apprise (16.1k⭐) 封装 |
| 导入方 | `multi_main.py`, EventBus 自动订阅 |

**特性:**
- 支持 100+ 通知渠道 (Telegram/微信/Discord/Slack/Bark/ntfy/邮件/Webhook)
- 4 级通知 (CRITICAL → HIGH → NORMAL → LOW)
- 标签路由 (按事件类型路由到特定渠道)
- 微信同步推送 (通过 wechat_bridge.py)

**Public API:**
- `clean_text(value) -> str` — 清洗空白
- `shorten(value, max_len) -> str` — 截断
- `bullet(text, icon) -> str` — 列表项
- `kv(label, value) -> str` — 键值对
- `divider(style) -> str` — 分隔线
- `timestamp_tag() -> str` — 时间戳
- `format_notice(title, lines) -> str` — 通用通知
- `format_status_card(...)` — Bot 状态卡片
- `format_social_published(...)` — 社媒发布成功通知
- `format_social_dual_result(...)` — 双平台发布结果
- `format_hotpost_result(...)` — 热点发文结果
- `format_cost_card(...)` — 成本配额卡片
- `format_bounty_result(...)` — 赏金结果
- `format_digest(title, intro, sections, footer)` — 结构化摘要

### 1.3 feedback.py — 用户反馈系统

| 属性 | 值 |
|------|-----|
| 路径 | `packages/clawbot/src/feedback.py` |
| 行数 | 116 |
| 搬运自 | karfly/chatgpt_telegram_bot (5.6k⭐) + n3d1117 callback_data 编码 |
| 导入方 | message_mixin, cmd_basic_mixin |
| 依赖 | telegram, sqlite3 |

**Public API:**
- `build_feedback_keyboard(bot_id, model_used, chat_id) -> InlineKeyboardMarkup`
- `parse_feedback_data(callback_data) -> dict | None`
- `get_feedback_store() -> FeedbackStore`
- `class FeedbackStore` — SQLite 持久化反馈记录 (threading.Lock 线程安全)

### 1.4 telegram_markdown.py — Markdown → Telegram HTML 安全渲染

| 属性 | 值 |
|------|-----|
| 路径 | `packages/clawbot/src/telegram_markdown.py` |
| 行数 | 662 |
| 搬运自 | mistletoe (1k⭐) AST 级转换 |
| 导入方 | message_mixin |

**Public API:**
- `md_to_html(text) -> str` — Markdown 转 Telegram-safe HTML

### 1.5 error_handler.py — 全局错误处理

| 属性 | 值 |
|------|-----|
| 路径 | `packages/clawbot/src/error_handler.py` |
| 行数 | 224 |
| 搬运自 | python-telegram-bot 官方 error_handler 模式 |
| 导入方 | multi_bot |

**Public API:**
- `get_error_handler() -> ErrorHandler`
- `class ErrorHandler` — 分类错误 + 通知管理员 + telegram_error_handler

### 1.6 http_client.py — 弹性 HTTP 客户端

| 属性 | 值 |
|------|-----|
| 路径 | `packages/clawbot/src/http_client.py` |
| 行数 | 275 |
| 搬运自 | httpx + tenacity + 熔断模式 |
| 导入方 | multi_bot, api_mixin |

**Public API:**
- `class ResilientHTTPClient(timeout, retry_config, circuit_breaker, name)`
- `class RetryConfig(max_retries, base_delay)`
- `class CircuitBreaker(failure_threshold, recovery_timeout)`

### 1.7 charts.py — Plotly 图表引擎

| 属性 | 值 |
|------|-----|
| 路径 | `packages/clawbot/src/charts.py` |
| 行数 | 625 |
| 搬运自 | plotly (18.4k⭐) + kaleido |
| 导入方 | telegram_ux (plotly 优先降级) |
| 依赖 | plotly, kaleido (可选) |

**Public API:**
- `generate_equity_curve(equity_curve, title) -> bytes | None` — 权益曲线 (回撤阴影)
- `generate_pnl_waterfall(trades, title) -> bytes | None` — PnL 瀑布图
- `generate_portfolio_pie(positions, title) -> bytes | None` — 资产饼图
- `generate_candlestick(ohlcv_data, indicators, title) -> bytes | None` — K线图
- `generate_sentiment_gauge(value, title) -> bytes | None` — 情绪仪表盘

### 1.8 resilience.py — 弹性工具集

| 属性 | 值 |
|------|-----|
| 路径 | `packages/clawbot/src/resilience.py` |
| 行数 | 615 |
| 搬运自 | stamina (1.4k⭐) + PyrateLimiter (485⭐) + tenacity (6k⭐) |
| 导入方 | 全局 |

**Public API:**
- `@retry_api` — 3 次重试，指数退避，httpx/timeout
- `@retry_network` — 5 次重试，网络错误
- `@retry_llm` — 3 次重试，排除 ValueError
- `api_limiter(name)` — 令牌桶限流上下文管理器

### 1.9 ocr_service.py / ocr_router.py / ocr_processors.py — OCR 三件套

| 属性 | 值 |
|------|-----|
| 路径 | `packages/clawbot/src/ocr_service.py` (236 行) |
| | `packages/clawbot/src/ocr_router.py` (172 行) |
| | `packages/clawbot/src/ocr_processors.py` (328 行) |
| 总行数 | 736 |
| 搬运自 | GLM-OCR (智谱) + 场景路由设计 |
| 导入方 | message_mixin |

**Public API:**
- `ocr_image(image_bytes, mime_type, user_id, file_unique_id) -> OcrResult`
- `class OcrResult` — OCR 结果数据类
- `classify_ocr_scene(text) -> SceneMatch` — 场景分类 (financial/ecommerce/general)
- `class OcrScene(Enum)` — 场景枚举
- `process_financial_scene(ocr_result) -> dict` — 财报/K线处理
- `process_ecommerce_scene(ocr_result) -> dict` — 竞品/商品处理

### 1.10 context_manager.py — 上下文管理 (对标 MemGPT)

| 属性 | 值 |
|------|-----|
| 路径 | `packages/clawbot/src/context_manager.py` |
| 行数 | ~923 |
| 搬运自 | letta-ai/letta (16k⭐) 三层架构 |
| 导入方 | cmd_basic_mixin, globals, api_mixin |

**Public API:**
- `class ContextManager` — 渐进式压缩 + 关键信息保留
  - `get_context_status(messages) -> dict`
  - `estimate_tokens(messages) -> int`
  - `compress_local(messages) -> (compressed, summary)`
  - `update_history_store(store, bot_id, chat_id, compressed)`
- `class TieredContextManager` — Letta 三层架构 v3.0
  - `build_context(messages, system_prompt, query_hint, chat_id) -> (assembled, metadata)` — 智能组装 core+archival+recall
  - `core_set(key, value, chat_id)` / `core_get(key, chat_id)` — 读写 core memory
  - `_sync_smart_memory_facts(chat_id)` — 从 SmartMemory 同步 key_facts + user_profile 到 core memory
  - `archival_search(query, limit) -> str` — SharedMemory 向量语义检索

### 1.11 tts_engine.py — 文本转语音

| 属性 | 值 |
|------|-----|
| 路径 | `packages/clawbot/src/tts_engine.py` |
| 行数 | 103 |
| 搬运自 | edge-tts (10.3k⭐) |
| 导入方 | message_mixin |

**Public API:**
- `text_to_voice(text) -> bytes | None`

### 1.12 tools/export_service.py — 数据导出

| 属性 | 值 |
|------|-----|
| 路径 | `packages/clawbot/src/tools/export_service.py` |
| 行数 | 291 |
| 搬运自 | openpyxl (3.7k⭐) |
| 导入方 | cmd_invest_mixin |

**Public API:**
- `export_trades(trades, format) -> BytesIO`
- `export_watchlist(items, format) -> BytesIO`
- `export_portfolio(positions, summary, format) -> BytesIO`
- `HAS_OPENPYXL: bool` — openpyxl 可用性

### 1.13 tools/qr_service.py — 二维码生成

| 属性 | 值 |
|------|-----|
| 路径 | `packages/clawbot/src/tools/qr_service.py` |
| 行数 | 120 |
| 搬运自 | qrcode (4.5k⭐) |
| 导入方 | cmd_basic_mixin |

**Public API:**
- `generate_qr(text) -> BytesIO`
- `HAS_QRCODE: bool`

### 1.13.1 tools/tts_tool.py — 文字转语音

| 属性 | 值 |
|------|-----|
| 路径 | `packages/clawbot/src/tools/tts_tool.py` |
| 行数 | 100 |
| 搬运自 | edge-tts (10.3k⭐) |
| 导入方 | cmd_basic_mixin |

**Public API:**
- `text_to_speech(text, voice, rate, volume, output_path) -> Optional[str]` — 生成语音文件
- `get_voices(language) -> List[Dict]` — 获取可用音色
- `format_voice_list() -> str` — 格式化音色列表
- `CHINESE_VOICES: dict` — 6 种中文音色别名映射

### 1.14 backtest_reporter.py — 回测报告增强

| 属性 | 值 |
|------|-----|
| 路径 | `packages/clawbot/src/backtest_reporter.py` |
| 行数 | 688 |
| 搬运自 | backtesting.py (4.3k⭐) + Bokeh |
| 导入方 | cmd_trading_mixin |

**Public API:**
- `class BacktestReporter` — 生成 HTML 报告 (权益曲线/回撤/策略对比)
- `class BokehVisualizer` — Bokeh 可视化
- `_bokeh_available: bool`

### 1.15 rebalancer.py — 投资组合再平衡

| 属性 | 值 |
|------|-----|
| 路径 | `packages/clawbot/src/rebalancer.py` |
| 行数 | 332 |
| 搬运自 | 投资组合理论 + Markowitz |
| 导入方 | cmd_trading_mixin |

**Public API:**
- `rebalancer` — 全局单例
- `PRESET_ALLOCATIONS` — 预设配置 (tech/balanced/conservative)
- `class Rebalancer`
  - `set_targets(targets)`
  - `get_targets() -> list`
  - `analyze(positions, quotes, cash) -> RebalancePlan`
  - `format_targets() -> str`

---

### 1.16 integrations/composio_bridge.py — Composio 250+ 外部服务桥接

| 属性 | 值 |
|------|-----|
| 路径 | `packages/clawbot/src/integrations/composio_bridge.py` |
| 行数 | ~220 |
| 搬运自 | ComposioHQ/composio (20k⭐, Apache 2.0) |
| 导入方 | core/executor.py (composio 执行路径) |
| 依赖 | composio-core (可选) |

**Public API:**
- `get_composio_bridge() -> ComposioBridge` — 全局单例
- `class ComposioBridge(api_key, entity_id)`
  - `is_available() -> bool` — SDK + API Key 检查
  - `list_apps() -> List[str]` — 可用应用列表
  - `list_actions(app_name) -> List[Dict]` — 应用动作列表
  - `find_actions(*apps, use_case) -> List[str]` — 语义搜索动作
  - `execute_action(action_name, params, entity_id, connected_account_id) -> Dict` — 执行动作
  - `get_status() -> Dict` — 健康检查

---

### 1.17 integrations/skyvern_bridge.py — Skyvern 视觉 RPA 桥接

| 属性 | 值 |
|------|-----|
| 路径 | `packages/clawbot/src/integrations/skyvern_bridge.py` |
| 行数 | ~230 |
| 搬运自 | Skyvern-AI/skyvern (11k⭐, AGPL-3.0) |
| 导入方 | core/executor.py (skyvern 执行路径) |
| 依赖 | skyvern (可选) |

**Public API:**
- `get_skyvern_bridge() -> SkyvernBridge` — 全局单例
- `class SkyvernBridge(api_key, base_url)`
  - `is_available() -> bool` — SDK + API Key 检查
  - `run_task(url, goal, max_steps, data_extraction_schema, wait_for_completion, timeout) -> Dict` — 核心: 视觉理解执行任务
  - `extract_data(url, schema, prompt, max_steps) -> Dict` — 结构化数据提取
  - `fill_form(url, fields, submit, max_steps) -> Dict` — 表单填写
  - `get_status() -> Dict` — 健康检查
  - `close()` — 释放资源

---

## 2. 关键已有模块速查

### 1.18 core/response_synthesizer.py — 响应合成层 (对标 omi)

| 属性 | 值 |
|------|-----|
| 路径 | `packages/clawbot/src/core/response_synthesizer.py` |
| 行数 | ~280 |
| 导入方 | brain.py |
| 依赖 | config/prompts.py (SOUL_CORE, RESPONSE_SYNTH_PROMPT), litellm_router, resilience |
| 参考项目 | BasedHardware/omi (17k⭐) |

**解决问题:** Brain 路径输出数据堆砌 → 合成为对话式回复

**Public API:**
- `ResponseSynthesizer.synthesize(raw_data, task_type, user_profile, conversation_summary) → Optional[str]` — 将结构化数据转化为自然语言
- `BrainContextCollector.collect(user_id, chat_id, bot_id) → Dict` — 从 SharedMemory/TieredContextManager/HistoryStore 收集上下文
- `get_response_synthesizer() → ResponseSynthesizer` — 单例
- `get_context_collector() → BrainContextCollector` — 单例

### 1.19 core/proactive_engine.py — 主动智能引擎 (搬运 omi 三步管道)

| 属性 | 值 |
|------|-----|
| 路径 | `packages/clawbot/src/core/proactive_engine.py` |
| 行数 | ~495 |
| 导入方 | multi_main.py (已集成: EventBus监听 + 30分钟定时检查) |
| 依赖 | config/prompts.py (PROACTIVE_*), structured_llm, litellm_router, event_bus, bot.globals |
| 参考项目 | BasedHardware/omi (17k⭐) proactive_notification.py |

**解决问题:** Bot 纯被动等待用户开口 → 主动推送有价值信息

**三步管道:**
1. Gate — 最便宜模型快速判断是否值得打扰 (relevance_score ≥ 0.70)
2. Generate — 生成通知文本 (100字以内，像朋友发微信)
3. Critic — 人类视角审查 (想象收到后的反应)

**触发方式:** EventBus 事件 (TRADE_EXECUTED/RISK_ALERT) + 30分钟定时系统状态检查

**频率控制:** 每用户每小时最多 3 条

**Public API:**
- `ProactiveEngine.evaluate(context_type, current_context, user_id, user_profile) → Optional[str]` — 三步评估
- `setup_proactive_listeners(engine)` — 注册 EventBus 监听器
- `periodic_proactive_check(engine)` — 定时收集系统上下文(持仓/闲鱼/交易)并评估是否推送
- `get_proactive_engine() → ProactiveEngine` — 单例

---

| 模块 | 路径 | 行数 | 核心用途 |
|------|------|------|----------|
| auth.py | `src/api/auth.py` | 75 | API 共享密钥认证 (X-API-Token header + WS query param) |
| multi_bot.py | `src/bot/multi_bot.py` | 420 | MultiBot 核心类，组合 11 个 Mixin |
| globals.py | `src/bot/globals.py` | 200 | 全局共享对象实例 + 辅助函数 + UserPreferences (纯配置已提取到 config.py) |
| config.py | `src/bot/config.py` | 107 | 纯配置层: 环境变量 + API Key管理 + SF Key轮转 (HI-359: 打破循环依赖) |
| api_mixin.py | `src/bot/api_mixin.py` | 371 | LLM API 调用 (流式/非流式) |
| rate_limiter.py | `src/bot/rate_limiter.py` | 243 | 消息频率限制 + Token 预算 |
| sau_bridge.py | `src/sau_bridge.py` | 175 | 社媒发布桥接层 — CLI 调用 social-auto-upload (抖音/B站/小红书/快手) |
| message_mixin.py | `src/bot/message_mixin.py` | 1128 | 消息处理 + 流式输出 + 链式工作流 (从1914行拆分) |
| chinese_nlp_mixin.py | `src/bot/chinese_nlp_mixin.py` | 565 | 中文NLP命令匹配(模糊容错) + ticker映射 + 噪音清洗 + "你是不是想说"建议 |
| ocr_mixin.py | `src/bot/ocr_mixin.py` | 325 | 图片/文档OCR处理 (从message_mixin提取) |
| **路由包 (src/routing/)** | | **~1563 (8文件)** | **从 chat_router.py 拆分的群聊智能路由包** |
| \_\_init\_\_.py | `src/routing/__init__.py` | 72 | routing 包入口 — 群聊智能路由 + 协作编排 |
| constants.py | `src/routing/constants.py` | 105 | 路由常量 — 意图关键词、分流规则、触发词 |
| models.py | `src/routing/models.py` | 101 | 路由数据模型 — dataclass 和 Enum 定义 |
| orchestrator.py | `src/routing/orchestrator.py` | 364 | CollabOrchestrator — 多 Bot 协作编排器 |
| priority_queue.py | `src/routing/priority_queue.py` | 73 | PriorityMessageQueue — 优先级消息队列 |
| router.py | `src/routing/router.py` | 475 | ChatRouter — 群聊消息智能路由器 |
| sessions.py | `src/routing/sessions.py` | 251 | SessionMixin — 讨论会话 + 服务工作流管理 |
| streaming.py | `src/routing/streaming.py` | 122 | StreamingResponse — 流式传输支持 |
| litellm_router.py | `src/litellm_router.py` | ~830 | LiteLLM 统一路由: 15+ provider, 50+ deployment, 模型强度排名, 10条付费硅基Key池, validate_keys() 健康验证 |
| smart_memory.py | `src/smart_memory.py` | ~800 | mem0 集成 + 用户画像 |
| shared_memory.py | `src/shared_memory.py` | 1111 | ✅ 共享记忆层 v4.0: Mem0 Cloud → qdrant → SQLite 三级降级, user_id 隔离 + Cloud API 签名兼容, 冲突检测 + 重要性衰减 + 自动压缩 |
| invest_tools.py | `src/invest_tools.py` | ~600 | 行情获取 + 报价格式化 |
| ta_engine.py | `src/ta_engine.py` | ~500 | pandas-ta 技术指标计算 |
| history_store.py | `src/history_store.py` | ~400 | SQLite 对话历史存储 |
| risk_manager.py | `src/risk_manager.py` | ~1320 | 风控引擎 (仓位/止损/集中度/行业查询/风险敞口摘要) |
| social_tools.py | `src/social_tools.py` | ~700 | 社媒内容生成 + 发布 |
| monitoring/ | `src/monitoring/` | 1394 (7文件) | Prometheus 监控包 — metrics.py(采集) + health.py(健康检查) + alerts.py(告警) + anomaly_detector.py(异常检测) + cost_analyzer.py(成本分析) + logger.py(日志) |
| message_format.py | `src/message_format.py` | 528 | OMEGA 结构化响应 + 格式化 |
| message_sender.py | `src/message_sender.py` | 135 | Telegram 消息清洗 + 分割 |
| social_scheduler.py | `src/social_scheduler.py` | 542 | APScheduler 社交自动驾驶 |
| quote_cache.py | `src/quote_cache.py` | 220 | 行情缓存 |
| llm_cache.py | `src/llm_cache.py` | 273 | LLM 响应缓存 |
| structured_llm.py | `src/structured_llm.py` | 273 | instructor 结构化 LLM 输出 |
| observability.py | `src/observability.py` | 243 | OTEL + Phoenix 可观测 |
| log_config.py | `src/log_config.py` | 234 | loguru 日志配置 |
| strategy_engine.py | `src/strategy_engine.py` | 710 | 交易策略引擎 v3.0 (7策略加权投票) |
| synergy.py | `src/synergy.py` | 180 | 多 Bot 协同策略 |
| **核心引擎 (src/core/)** | | | |
| brain.py | `src/core/brain.py` | 848 | ✅ OMEGA 核心大脑: 对话入口(process_message) + 复合意图拆解 + DAG编排 + 响应合成 + 追问建议 + asyncio.Lock竞态保护 |
| intent_parser.py | `src/core/intent_parser.py` | 611 | ✅ 三级意图解析: 快速正则(60%命中) → LLM+instructor结构化 → legacy JSON解析 |
| task_graph.py | `src/core/task_graph.py` | 374 | ✅ DAG任务图: TaskGraphBuilder流式API + 并行调度 + 死锁检测 + 指数退避重试 + 超时 + fallback |
| executor.py | `src/core/executor.py` | 542 | ✅ 统一执行器: API→浏览器→语音→Composio→Skyvern→人工 6条路径 + 平台熔断器 |
| event_bus.py | `src/core/event_bus.py` | 346 | ✅ 事件总线: 发布/订阅 + 通配符匹配 + 优先级排序 + 异常隔离 + JSONL审计日志 + 线程安全单例 |
| cost_control.py | `src/core/cost_control.py` | 247 | ✅ 成本控制: 模型定价表(8模型) + 日预算检查 + 80%阈值告警 + 成本感知模型路由 + 周报 |
| self_heal.py | `src/core/self_heal.py` | 656 | ✅ 自愈引擎6步: 错误分类→已知方案(含tenacity重试)→记忆检索→Web搜索(Jina/Tavily)→替代方案→通知用户 + 熔断器(同一错误3次5分钟冷却) |
| synergy_pipelines.py | `src/core/synergy_pipelines.py` | 550 | 跨模块协同管道: 交易→社媒/社交→投资/进化广播/风控过滤/新闻情感→风控(4h定时)/盈利庆祝帖 |
| security.py | `src/core/security.py` | 349 | ✅ 安全防护层: 输入消毒(sanitize_input) + PIN(PBKDF2+盐+频率限制) + 审计日志(JSONL) + 权限三级分控(auto/confirm/always_human) + XSS/SQL注入/路径遍历/命令注入防护 |
| **核心工具 (src/ 根级)** | | | |
| utils.py | `src/utils.py` | 101 | 共享工具函数 (时间/环境变量/样板代码消除) |
| scheduler.py | `src/scheduler.py` | 186 | 定时任务调度器 (早报推送/提醒, 美东时间) |
| pipeline_helper.py | `src/pipeline_helper.py` | 130 | 交易管道桥接 (dict→TradeProposal + ATR 止损止盈) |
| agent_tools.py | `src/agent_tools.py` | 397 | 自主 Agent 工具集 (smolagents 搬运, CodeAgent 降级链) |
| langfuse_obs.py | `src/langfuse_obs.py` | 285 | Langfuse 观测层 (LLM 调用追踪/成本/延迟上报) |
| monitoring_extras.py | `src/monitoring_extras.py` | 166 | 监控增强 (g4f 健康检查/AlertManager/系统资源) |
| **执行层 (src/execution/)** | | | |
| _ai.py | `src/execution/_ai.py` | 110 | 执行层 AI 调用 (LiteLLM 统一路由封装) |
| _db.py | `src/execution/_db.py` | 125 | 执行层数据库 (SQLite 连接管理/表结构定义) |
| _utils.py | `src/execution/_utils.py` | 146 | 执行层工具函数 (从 execution_hub.py 提取的通用方法) |
| dev_workflow.py | `src/execution/dev_workflow.py` | 44 | 开发流程自动化 (自定义工作流命令执行) |
| meeting_notes.py | `src/execution/meeting_notes.py` | 45 | 会议纪要提炼 (摘要/行动事项/关键决策提取) |
| project_report.py | `src/execution/project_report.py` | 51 | 项目周报生成 (基于 git log 自动汇总) |
| **社媒 (src/execution/social/)** | | | |
| content_pipeline.py | `src/execution/social/content_pipeline.py` | 638 | 社媒内容管道 (自动发布/话题研究/创意生成/人设组合/日历持久化+查询+标记完成) |
| drafts.py | `src/execution/social/drafts.py` | 293 | 社媒草稿管理 (保存/去重检测/状态更新/发布) |
| worker_bridge.py | `src/execution/social/worker_bridge.py` | 187 | 社媒浏览器 Worker 桥接 (独立于 ExecutionHub 调用) |
| **工具 (src/tools/)** | | | |
| docling_service.py | `src/tools/docling_service.py` | 217 | 文档理解 (PDF/DOCX/PPTX→Markdown, Docling 56.3k⭐ 搬运) |
| tavily_search.py | `src/tools/tavily_search.py` | 206 | 智能搜索 (Tavily SDK — QnA/RAG 上下文/深度研究) |
| vision.py | `src/tools/vision.py` | 65 | 图片理解 (LiteLLM Vision 多模型, 零新依赖) |
| code_tool.py | `src/tools/code_tool.py` | 155 | ✅ Python/Node.js 代码沙箱: import hook 禁用14个危险模块 + open()禁用 + subclasses阻断 + Node.js 12模块黑名单 + 代码长度限制(10KB) |
| bash_tool.py | `src/tools/bash_tool.py` | 161 | ✅ 安全 Shell 执行: 白名单命令模式(35个安全命令) + shell=False + shlex.split 解析 + 进程组超时终止 + execute_dangerous 已禁用 |
| **交易 (src/trading/)** | | | |
| _helpers.py | `src/trading/_helpers.py` | 142 | 交易工具函数 (纯工具，无全局状态依赖) |
| _init_system.py | `src/trading/_init_system.py` | 358 | 交易系统初始化 + AI 团队配置 |
| _lifecycle.py | `src/trading/_lifecycle.py` | 230 | 启停/状态恢复/便捷访问器 |
| _scheduler_daily.py | `src/trading/_scheduler_daily.py` | 387 | 每日定时任务 (风控重置/收盘复盘/行情刷新) |
| _scheduler_tasks.py | `src/trading/_scheduler_tasks.py` | 440 | 调度重型任务 (IBKR 成交回写/撤单/重入队列) |
| market_calendar.py | `src/trading/market_calendar.py` | 119 | 美股市场日历 (假日计算+开盘日判断) |
| reentry_queue.py | `src/trading/reentry_queue.py` | 61 | 重入队列管理 (盘后取消→下一交易日重新提交) |
| **闲鱼 (src/xianyu/)** | | | |
| cookie_refresher.py | `src/xianyu/cookie_refresher.py` | 87 | Cookie 自动刷新 (_m_h5_tk 过期监控/主动续期) |
| order_notifier.py | `src/xianyu/order_notifier.py` | 134 | 订单通知 (邮件+Telegram 推送/日报/健康告警) |
| xianyu_apis.py | `src/xianyu/xianyu_apis.py` | 143 | 闲鱼 API 封装 (Token 获取/商品信息/登录状态) |
| xianyu_context.py | `src/xianyu/xianyu_context.py` | 275 | 闲鱼对话上下文管理 (SQLite 持久化/历史记录, @contextmanager, 利润核算含佣金, 时区统一) |
| xianyu/utils.py | `src/xianyu/utils.py` | 151 | 闲鱼工具函数 (签名生成/MessagePack 解密/ID 生成) |
| auto_shipper.py | `src/xianyu/auto_shipper.py` | 210 | **搬运** xianyu-super-butler 自动发货引擎 (卡券库存管理/发货规则/订单自动匹配/WebSocket 集成) |
| **自选股监控 (src/)** | | | |
| watchlist.py | `src/watchlist.py` | 86 | 自选股统一访问层 — 桥接 Portfolio.watchlist (get_symbols/with_targets/add/remove) |
| watchlist_monitor.py | `src/watchlist_monitor.py` | 257 | **搬运** position_monitor 循环+冷却模式 — 自选股异动监控引擎 (价格>3%/放量/RSI极值/目标价止损触达, PanWatch 冷却节流) |
| **API (src/api/)** | | | |
| schemas.py | `src/api/schemas.py` | 272 | API 请求/响应模型 (Pydantic 集中定义, freqtrade 模式) |
| pool.py | `src/api/routers/pool.py` | 11 | API Pool 端点 (统计数据查询) |
| shopping.py | `src/api/routers/shopping.py` | 25 | 比价购物端点 (多平台价格对比+AI 总结) |
| store.py | `src/api/routers/store.py` | 358 | 统一插件商店端点，扫描本地 NPM Skills、NPM Extensions 和 Bot Skills |
| system.py | `src/api/routers/system.py` | 16 | 系统状态端点 (ping/version/status) |
| memory.py | `src/api/routers/memory.py` | 23 | 记忆搜索端点 (keyword/semantic/hybrid 模式) |
| rpc.py | `src/api/rpc.py` | 923 | ✅ RPC 远程调用接口: _safe_error 脱敏(隐藏路径+截断) + Tauri 桌面端通信 + freqtrade RPC 模式(System/Trading/Social/Memory/Pool/Shopping) |

### 2.1 本次迭代增强的模块 (2026-03-23)

**2026-03-24 新增:**

| 模块 | 路径 | 行数 | 功能 | 导入方 |
|------|------|------|------|--------|
| prompts.py | `config/prompts.py` | 220 | 系统提示词注册表 (SSOT) — 消除 7 文件 42+ 内联提示词重复 | brain.py, intent_parser.py, team.py, pydantic_agents.py, cmd_collab_mixin.py |

| 模块 | 路径 | 行数 | 增强内容 | 搬运来源 |
|------|------|------|----------|----------|
| backtester_vbt.py | `src/modules/investment/backtester_vbt.py` | 750 | 7策略+DRL/因子回测+Optuna优化+QuantStats报告 | vectorbt (6.9k⭐) + FinRL (11k⭐) + Qlib (18k⭐) |
| strategy_engine.py | `src/strategy_engine.py` | 710 | v3.0: `backtest_all()` + DRL/因子策略注册 | FinRL + Qlib + finlab_crypto |
| message_format.py | `src/message_format.py` | 700 | 新增 `markdown_to_telegram_html()` + `strip_markdown()` | CoPaw (agentscope-ai, Apache-2.0) |
| omega.py (API) | `src/api/routers/omega.py` | 268 | `/investment/backtest` 支持 6 策略 + Optuna 优化 | — |
| context_manager.py | `src/context_manager.py` | 870 | v3.0: core memory 持久化 + SmartMemory 集成 + per-chat 隔离 | letta-ai/letta (16k⭐) |
| social_tools.py | `src/social_tools.py` | 460 | 情感分析 v2.0: snownlp(中文) + textblob(英文) + 词袋降级 | snownlp (6k⭐) + textblob (9k⭐) |
| news_fetcher.py | `src/news_fetcher.py` | 330 | feedparser RSS 解析 + 8 源内置 + 按分类聚合 | feedparser (9.8k⭐) |
| rebalancer.py | `src/rebalancer.py` | 470 | PyPortfolioOpt 有效前沿优化 (max_sharpe/min_vol) + 离散分配 | PyPortfolioOpt (4.6k⭐) |
| daily_brief.py | `src/execution/daily_brief.py` | 90 | 接入 RSS 新闻 + 行情摘要，简报从3段→5段 | — |
| auto_trader.py | `src/auto_trader.py` | 1545 | exchange-calendars (4.1k⭐) 替代手写 70 行休市日计算 | exchange-calendars (4.1k⭐) |
| alpaca_bridge.py | `src/alpaca_bridge.py` | 250 | **新建** Alpaca 券商桥接，与 IBKRBridge 接口兼容 | alpaca-py (1k⭐) |
| broker_bridge.py | `src/broker_bridge.py` | 1100 | 新增 `get_broker()` 统一券商选择器 (IBKR→Alpaca→模拟) | — |
| invest_tools.py | `src/invest_tools.py` | 720 | 新增 Fear & Greed Index + `get_quick_quotes()` + `get_earnings_calendar()` | alternative.me + yfinance |
| daily_brief.py | `src/execution/daily_brief.py` | 100 | 接入 Fear & Greed Index (简报第6段) | — |
| daily_brief.py | `src/execution/daily_brief.py` | 930 | 新增 _build_today_agenda() 日程板块，合并5源(持仓风险/提醒/账单/待办/降价监控)按紧急度排序 | — |
| universe.py | `src/universe.py` | 400 | tvscreener (Apache-2.0) 动态股票筛选 `get_dynamic_candidates()` | tvscreener |
| alpaca_bridge.py | `src/alpaca_bridge.py` | 380 | v1.1: +6 IBKRBridge 兼容方法，可完全替换 IBKR | alpaca-py (1k⭐) |
| trading_system.py | `src/trading_system.py` | 1431 | 健康检查统一为 `_broker_health_check` (IBKR/Alpaca 双支持) | — |
| price_engine.py | `src/shopping/price_engine.py` | 480 | price-parser (4.2k⭐) 智能价格提取，替代 regex | price-parser (MIT) |
| x_platform.py | `src/execution/social/x_platform.py` | 270 | tweepy (10.6k⭐) 三级降级: API→Jina→browser | tweepy (MIT) |
| life_automation.py | `src/execution/life_automation.py` | 455 | dateparser (2.5k⭐) 自然语言时间解析 + 简易记账 (add/summary/undo, 金额验证+并发防护+撤销隔离) | dateparser |
| notify_style.py | `src/notify_style.py` | 440 | humanize (2.9k⭐) natural_time/size/number | humanize |
| config_validator.py | `src/core/config_validator.py` | 130 | 启动配置验证: 7 Bot Token + 12 LLM Key + 文件检查 | — |


### 2.2 R27 全量补录 — 缺失模块注册

> 以下模块在 R1~R26 审计中均未注册，R27 统一补录。含原 Section 5 (R9补充) 去重后的独有条目。

#### Bot 命令层 (src/bot/)

| 模块 | 路径 | 行数 | 说明 |
|------|------|------|------|
| cmd_basic_mixin.py | `src/bot/cmd_basic_mixin.py` | 14 | 基础命令入口 (转发到 cmd_basic/ 子包) |
| cmd_analysis_mixin.py | `src/bot/cmd_analysis_mixin.py` | 718 | 分析命令 (研报/对比/评审) |
| cmd_invest_mixin.py | `src/bot/cmd_invest_mixin.py` | 877 | 投资命令 (行情/持仓/回测/再平衡) |
| cmd_trading_mixin.py | `src/bot/cmd_trading_mixin.py` | 516 | 交易命令 (买卖/止损/账单) |
| cmd_ibkr_mixin.py | `src/bot/cmd_ibkr_mixin.py` | 171 | IBKR 专项命令 (连接/状态/订单) |
| cmd_social_mixin.py | `src/bot/cmd_social_mixin.py` | 802 | 社媒命令 (发帖/日历/草稿) |
| cmd_collab_mixin.py | `src/bot/cmd_collab_mixin.py` | 812 | 协作命令 (研究/深度分析/辩论) |
| cmd_xianyu_mixin.py | `src/bot/cmd_xianyu_mixin.py` | 545 | 闲鱼命令 (上架/客服/订单) |
| cmd_novel_mixin.py | `src/bot/cmd_novel_mixin.py` | 198 | 小说命令 (创建/续写/导出) |
| cmd_life_mixin.py | `src/bot/cmd_life_mixin.py` | 643 | 生活命令 (记账/提醒/待办/日程) |
| cmd_ops_mixin.py | `src/bot/cmd_ops_mixin.py` | 514 | 运维命令 (部署/日志/健康/Key管理) |
| cmd_execution_mixin.py | `src/bot/cmd_execution_mixin.py` | 27 | 执行命令入口 (转发到 execution/) |
| workflow_mixin.py | `src/bot/workflow_mixin.py` | 478 | 工作流编排 (多步骤任务串联) |
| callback_mixin.py | `src/bot/callback_mixin.py` | 293 | 按钮回调路由 (InlineKeyboard 事件分发) |

#### Core 引擎 (src/core/)

| 模块 | 路径 | 行数 | 说明 |
|------|------|------|------|
| brain_executors.py | `src/core/brain_executors.py` | 646 | Brain 执行器 — 各路径 (投资/社媒/闲鱼/工具) 的具体执行逻辑 |
| response_cards.py | `src/core/response_cards.py` | 809 | 响应卡片模板 — 结构化 HTML 卡片 (交易/持仓/分析/社媒) |
| brain_graph_builders.py | `src/core/brain_graph_builders.py` | 183 | Brain 图构建器 — LangGraph 状态图节点定义 |

#### 交易/投资系统 (src/ 根级)

| 模块 | 路径 | 行数 | 说明 | 搬运来源 |
|------|------|------|------|----------|
| trading_pipeline.py | `src/trading_pipeline.py` | 496 | 交易管道 — 信号→筛选→风控→执行完整流程 | 自研 |
| ai_team_voter.py | `src/ai_team_voter.py` | 822 | AI 团队投票器 — 多 Agent 协商 + 加权投票决策 | 自研 |
| decision_validator.py | `src/decision_validator.py` | 734 | 决策验证器 — 交易决策多维度校验 (风控/仓位/市场) | 自研 |
| freqtrade_bridge.py | `src/freqtrade_bridge.py` | 651 | Freqtrade 桥接 — 兼容 freqtrade 策略接口 | freqtrade (35k⭐) |
| tool_executor.py | `src/tool_executor.py` | 726 | 工具执行器 — 统一工具调用框架 (参数验证/超时/日志) | 自研 |
| models.py | `src/models.py` | 23 | 数据模型 — 共享 Pydantic/dataclass 定义 | — |
| browser_use_bridge.py | `src/browser_use_bridge.py` | ~220 | AI 浏览器代理桥接 — DOM 解析/LLM 决策/反检测 | browser-use (81k⭐) |
| crewai_bridge.py | `src/crewai_bridge.py` | ~180 | CrewAI 多 Agent 协作桥接 | crewai (27k⭐) |
| trading_journal.py | `src/trading_journal.py` | 464 | 交易日志主类 — DB初始化/配置/交易CRUD/cleanup + Mixin组合 | 自研 |
| journal_performance.py | `src/journal_performance.py` | 202 | 交易日志 Mixin — 绩效统计/权益曲线/格式化报告 | 自研 |
| journal_predictions.py | `src/journal_predictions.py` | 145 | 交易日志 Mixin — 研判预期记录/收盘验证/准确率统计 | 自研 |
| journal_targets.py | `src/journal_targets.py` | 115 | 交易日志 Mixin — 盈利目标设定/进度更新/格式化展示 | 自研 |
| journal_review.py | `src/journal_review.py` | 221 | 交易日志 Mixin — 复盘会议/复盘数据/迭代改进报告 | 自研 |
| novel_writer.py | `src/novel_writer.py` | ~450 | AI 小说工坊 — 大纲/续写/TTS | inkos + MuMuAINovel |
| position_monitor.py | `src/position_monitor.py` | ~700 | 持仓实时监控 — 止损/止盈/异动告警 | 自研 |
| data_providers.py | `src/data_providers.py` | ~400 | 多市场数据源聚合 (yfinance/Alpha Vantage) | yfinance (16k⭐) |
| backtester.py | `src/backtester.py` | ~350 | 回测引擎主模块 | vectorbt (5.4k⭐) |

#### 策略层 (src/strategies/)

| 模块 | 路径 | 行数 | 说明 | 搬运来源 |
|------|------|------|------|----------|
| drl_strategy.py | `src/strategies/drl_strategy.py` | ~200 | 深度强化学习交易策略 (PPO) | FinRL (10k⭐) |
| factor_strategy.py | `src/strategies/factor_strategy.py` | ~300 | 16 Alpha 因子量化策略 | Qlib (16k⭐) |

#### 执行层 (src/execution/)

| 模块 | 路径 | 行数 | 说明 |
|------|------|------|------|
| scheduler.py | `src/execution/scheduler.py` | 547 | 执行调度器 — 定时任务注册/取消/状态查询 |
| bookkeeping.py | `src/execution/bookkeeping.py` | 681 | 记账系统 — 收支记录/分类统计/预算管理 |
| tracking.py | `src/execution/tracking.py` | 469 | 任务追踪 — 进度/状态/提醒/超期检测 |
| task_mgmt.py | `src/execution/task_mgmt.py` | 108 | 任务管理 — CRUD + 优先级排序 |
| monitoring.py | `src/execution/monitoring.py` | 160 | 执行监控 — 任务健康/超时/失败告警 |
| doc_search.py | `src/execution/doc_search.py` | 99 | 文档搜索 — 本地知识库检索 |
| bounty.py | `src/execution/bounty.py` | 225 | 赏金任务 — 悬赏/投稿/评选 |
| email_triage.py | `src/execution/email_triage.py` | 66 | 邮件分拣 — AI 分类/摘要/优先级 |

#### 社媒执行 (src/execution/social/)

| 模块 | 路径 | 行数 | 说明 |
|------|------|------|------|
| real_trending.py | `src/execution/social/real_trending.py` | 230 | 实时热搜 — 多平台热点抓取/排名 |
| xhs_platform.py | `src/execution/social/xhs_platform.py` | 81 | 小红书平台 — 笔记发布适配 |
| media_crawler_bridge.py | `src/execution/social/media_crawler_bridge.py` | 302 | MediaCrawler 桥接 — 社媒数据采集 |
| content_strategy.py | `src/execution/social/content_strategy.py` | 156 | 内容策略 — 发帖时机/频率/A/B测试 |

#### 工具集 (src/tools/)

| 模块 | 路径 | 行数 | 说明 |
|------|------|------|------|
| free_apis.py | `src/tools/free_apis.py` | 225 | 免费 API 集合 — 天气/汇率/新闻/名言 |
| file_tool.py | `src/tools/file_tool.py` | 189 | 文件操作 — 读写/格式转换/压缩 |
| memory_tool.py | `src/tools/memory_tool.py` | 98 | 记忆工具 — Agent 记忆读写接口 |
| web_tool.py | `src/tools/web_tool.py` | 69 | 网页工具 — URL 抓取/摘要 |
| jina_reader.py | `src/tools/jina_reader.py` | 112 | Jina Reader — 网页→Markdown 转换 |
| comfyui_client.py | `src/tools/comfyui_client.py` | 486 | ComfyUI 客户端 — 图片生成工作流 |
| fal_client.py | `src/tools/fal_client.py` | 190 | fal.ai 客户端 — 云端 AI 模型调用 |
| deepgram_stt.py | `src/tools/deepgram_stt.py` | 101 | Deepgram STT — 语音转文字 |
| image_tool.py | `src/tools/image_tool.py` | ~100 | 图片生成工具 (硅基流动 FLUX/SD3/SDXL) |

#### 闲鱼 (src/xianyu/)

| 模块 | 路径 | 行数 | 说明 |
|------|------|------|------|
| xianyu_live.py | `src/xianyu/xianyu_live.py` | 778 | 闲鱼实时客服 — WebSocket 长连接/自动回复 |
| xianyu_agent.py | `src/xianyu/xianyu_agent.py` | 497 | 闲鱼 AI Agent — 多轮对话/砍价/推荐 |
| xianyu_admin.py | `src/xianyu/xianyu_admin.py` | 328 | 闲鱼管理后台 — 商品/订单/统计 |
| goofish_monitor.py | `src/xianyu/goofish_monitor.py` | 336 | 闲鱼监控 — 竞品价格/销量追踪 |

#### API 层 (src/api/)

| 模块 | 路径 | 行数 | 说明 |
|------|------|------|------|
| server.py | `src/api/server.py` | 122 | FastAPI 服务器 — 应用工厂/中间件/生命周期 |
| routers/evolution.py | `src/api/routers/evolution.py` | 189 | 进化端点 — 自我进化/指标/报告 |
| routers/social.py | `src/api/routers/social.py` | 225 | 社媒端点 — 发布/日历/分析 |
| routers/store.py | `src/api/routers/store.py` | 358 | 统一插件商店端点 — `/store/catalog` 和 `/store/categories` |
| routers/trading.py | `src/api/routers/trading.py` | 86 | 交易端点 — 下单/持仓/历史 |
| routers/ws.py | `src/api/routers/ws.py` | 120 | WebSocket 端点 — 实时消息推送 |

#### 投资模块 (src/modules/investment/)

| 模块 | 路径 | 行数 | 说明 | 搬运来源 |
|------|------|------|------|----------|
| team.py | `src/modules/investment/team.py` | 776 | 投资 AI 团队 — CrewAI 多角色协作 (分析师/策略师/风控) | crewai (27k⭐) |
| pydantic_agents.py | `src/modules/investment/pydantic_agents.py` | 430 | Pydantic AI Agent — 结构化投资分析 | pydantic-ai (13k⭐) |

#### 购物/网关/部署

| 模块 | 路径 | 行数 | 说明 |
|------|------|------|------|
| crawl4ai_engine.py | `src/shopping/crawl4ai_engine.py` | 650 | Crawl4AI 比价引擎 — 多电商平台爬取/价格对比 |
| telegram_gateway.py | `src/gateway/telegram_gateway.py` | 528 | OMEGA 网关 Bot — 统一入口/路由分发到 7 Bot |
| license_manager.py | `src/deployer/license_manager.py` | 240 | 授权管理 — License 生成/验证/过期检查 |
| deploy_server.py | `src/deployer/deploy_server.py` | 157 | 部署服务器 — 远程部署/更新/回滚 |

---

### 2.3 HI-358 大文件拆分补录 (2026-04-12)

> 以下 26 个模块在 HI-358 大文件拆分中新建，此前未注册。按拆分来源分组。

#### 回测引擎拆分 (从 backtester.py 拆分)

| 模块 | 路径 | 行数 | 说明 |
|------|------|------|------|
| backtester_models.py | `src/backtester_models.py` | 181 | 回测数据模型 — Bar/BacktestTrade/BacktestConfig/PerformanceReport 数据类 + load_historical_data 数据加载 |
| backtester_advanced.py | `src/backtester_advanced.py` | 533 | 回测高级分析 — 蒙特卡洛模拟/网格参数优化/Walk-Forward 过拟合检测/增强绩效指标 (Sortino/Calmar/SQN) |

**依赖关系:** `backtester.py` → `backtester_models.py`; `backtester_advanced.py` → `backtester_models.py` + `risk_config.py`

#### 中文 NLP 拆分 (从 chinese_nlp_mixin.py 拆分)

| 模块 | 路径 | 行数 | 说明 |
|------|------|------|------|
| nlp_dispatch_handlers.py | `src/bot/nlp_dispatch_handlers.py` | 549 | NLP 分发处理器 — 独立 async handler 函数 (快递/记账/提醒/待办/查询/购物/翻译/天气等) |
| nlp_ticker_map.py | `src/bot/nlp_ticker_map.py` | 126 | Ticker 映射 + 对话噪音清洗 — 中文股票名→ticker 映射 + 对话粒子剥离 + 模糊命令建议 |

**依赖关系:** `chinese_nlp_mixin.py` → `nlp_dispatch_handlers.py` + `nlp_ticker_map.py`

#### 券商桥接拆分 (从 broker_bridge.py 拆分)

| 模块 | 路径 | 行数 | 说明 |
|------|------|------|------|
| broker_scanner.py | `src/broker_scanner.py` | 246 | IBKR 扫描器 Mixin — 合约构建/Scanner 扫描/合约搜索/实时快照 (依赖 ib_insync) |
| broker_slippage.py | `src/broker_slippage.py` | 109 | 滑点估算 Mixin — SlippageEstimate 数据类 + 基于 yfinance 的滑点/流动性评估 (不依赖 ib_insync) |

**依赖关系:** `broker_bridge.py` (Mixin 继承) → `broker_scanner.py` + `broker_slippage.py`

#### 主动引擎拆分 (从 proactive_engine.py 拆分)

| 模块 | 路径 | 行数 | 说明 |
|------|------|------|------|
| proactive_models.py | `src/core/proactive_models.py` | 52 | 主动引擎数据模型 — GateResult/NotificationDraft/CriticResult Pydantic 模型 (三步管道结构化输出) |
| proactive_notify.py | `src/core/proactive_notify.py` | 72 | 主动引擎通知发送 — _send_proactive (文本) + _send_proactive_photo (图片+降级) |
| proactive_listeners.py | `src/core/proactive_listeners.py` | 430 | 主动引擎事件监听 — 9 个 EventBus 处理器 (交易成交/风控预警/自选股异动/订单支付/预算超支等) |
| proactive_periodic.py | `src/core/proactive_periodic.py` | 208 | 主动引擎定时检查 — 每 30 分钟收集系统上下文 (持仓/闲鱼/交易/提醒/风控) 评估是否推送 |

**依赖关系:** `proactive_engine.py` → `proactive_models.py` + `proactive_notify.py` + `proactive_listeners.py` + `proactive_periodic.py`

#### 进化引擎 (src/evolution/)

| 模块 | 路径 | 行数 | 说明 |
|------|------|------|------|
| engine.py | `src/evolution/engine.py` | 761 | 自主进化核心 — GitHub Trending 扫描 + LLM 价值评估 + 集成提案生成 + 低风险自动/高风险审批 + 历史记录 |
| github_trending.py | `src/evolution/github_trending.py` | 322 | GitHub Trending 采集器 — 爬取 trending 页面 (无 Token) + Search API 快速增长仓库查询 + README 获取 |

**依赖关系:** `evolution/engine.py` → `evolution/github_trending.py` + `litellm_router.py` + `utils.py`

#### 闲鱼新增 (src/xianyu/)

| 模块 | 路径 | 行数 | 说明 |
|------|------|------|------|
| qr_login.py | `src/xianyu/qr_login.py` | 415 | 闲鱼扫码登录 — 纯 API 实现 (不弹浏览器)，Telegram 发送二维码 + 轮询扫码 + Cookie 写入 .env + 热更新 |

**依赖关系:** `cmd_xianyu_mixin.py` → `qr_login.py`; 搬运自 GuDong2003/xianyu-auto-reply-fix

#### cmd_basic 子模块展开 (从 cmd_basic_mixin.py 拆分)

> 原有包级条目 (Section 0.4) 仅列名称，以下为各子模块的独立路径注册。

| 模块 | 路径 | 行数 | 说明 |
|------|------|------|------|
| help_mixin.py | `src/bot/cmd_basic/help_mixin.py` | 248 | 帮助菜单 — /help 命令 + help 回调 + 老用户 /start 欢迎（向导逻辑已移至 onboarding_mixin） |
| onboarding_mixin.py | `src/bot/cmd_basic/onboarding_mixin.py` | 258 | 新用户引导向导 — ConversationHandler 3步交互式引导（选兴趣→选风格→个性化推荐） |
| status_mixin.py | `src/bot/cmd_basic/status_mixin.py` | 237 | 状态查询 — /status, /metrics, /model, /pool, /keyhealth 系统信息 |
| tools_mixin.py | `src/bot/cmd_basic/tools_mixin.py` | 306 | 工具命令 — /draw, /news, /qr, /tts, /agent + inline query 处理 |
| memory_mixin.py | `src/bot/cmd_basic/memory_mixin.py` | 178 | 记忆管理 — /memory 命令 + 记忆分页/清除回调 + 反馈回调 |
| callback_mixin.py | `src/bot/cmd_basic/callback_mixin.py` | 161 | 回调处理 — 通知操作按钮 + 卡片操作按钮 + 追问建议按钮 |
| settings_mixin.py | `src/bot/cmd_basic/settings_mixin.py` | 144 | 用户设置 — /settings 命令及其 Inline 回调 |
| context_mixin.py | `src/bot/cmd_basic/context_mixin.py` | 107 | 上下文管理 — /context, /compact, /clear, /voice, /lanes 命令 |

**依赖关系:** `cmd_basic_mixin.py` (转发入口) → 以上 8 个子模块; 各子模块依赖 `bot.globals` + `bot.auth` + `telegram_ux`; `onboarding_mixin` 额外依赖 `ConversationHandler`

#### monitoring 子模块展开 (src/monitoring/)

> 原有包级条目 (Section 2, 第806行) 仅列名称，以下为各子模块的独立路径注册。

| 模块 | 路径 | 行数 | 说明 |
|------|------|------|------|
| metrics.py | `src/monitoring/metrics.py` | 182 | Prometheus 指标收集器 — Counter/Gauge/Histogram 三种指标 + HTTP 导出服务器 (无外部依赖) |
| health.py | `src/monitoring/health.py` | 274 | 健康检查 + 自动恢复 — Bot 心跳 + 错误计数 + AutoRecovery 不健康自动重启 (带冷却+计数上限) |
| alerts.py | `src/monitoring/alerts.py` | 60 | 告警规则引擎 — 可编程告警规则 + 回调通知 (对标 LiteLLM) |
| anomaly_detector.py | `src/monitoring/anomaly_detector.py` | 200 | 异常检测器 — 延迟尖峰/错误率突增/成本异常/流量异常 (对标 Datadog APM) |
| cost_analyzer.py | `src/monitoring/cost_analyzer.py` | 246 | 成本归因分析 — 按 bot/用户/功能/模型 维度成本归因 + 月度预测 + 预算告警 (对标 LiteLLM Budget Manager) |
| logger.py | `src/monitoring/logger.py` | 433 | 结构化日志 — StructuredLogger JSON 日志 + TaskObserver 任务级质量/成本/检索评估 |

**依赖关系:** `monitoring/__init__.py` 统一导出; `multi_main.py` + `bot.globals` 导入使用

---

## 3. 待搬运高星项目清单 (2026-03-23 评估)

> 历史设计报告已在 2026-05-03 文档清理中移除；本节保留可执行的模块清单和当前状态。

### 3.1 价值位阶 1 — 交易系统硬实力

| 项目 | Stars | 搬运目标 | 替代/增强 | 状态 |
|------|-------|----------|-----------|------|
| VectorBT | 5k⭐ | 深化 `backtester_vbt.py` (257→750行) | 7策略+DRL/因子回测+Optuna+QuantStats | ✅ 已完成 (2026-03-24) |
| FinRL | 11k⭐ | 新建 `src/strategies/drl_strategy.py` | DRL 交易策略 (PPO/A2C via stable-baselines3) | ✅ 已完成 (2026-03-24) |
| Qlib | 18k⭐ | 新建 `src/strategies/factor_strategy.py` | 16 Alpha 因子 + LightGBM ML 信号 | ✅ 已完成 (2026-03-24) |

### 3.2 价值位阶 2 — 架构升级

| 项目 | Stars | 搬运目标 | 替代/增强 | 状态 |
|------|-------|----------|-----------|------|
| Pydantic AI | 13k⭐ | 替代 `structured_llm.py` + 散落 instructor 调用 | 统一 Agent 定义层 | 📋 待搬运 |
| LangGraph | 12k⭐ | 替代 `task_graph.py` + 统一 execution 子模块编排 | 状态机编排 + 可视化 | 📋 待搬运 |
| Letta | 16k⭐ | 深化 `context_manager.py` v2.1→v3.0 | Core memory 持久化 + SmartMemory 集成 | ✅ 已完成 (2026-03-24) |

### 3.3 价值位阶 3 — 能力扩展

| 项目 | Stars | 搬运目标 | 替代/增强 | 状态 |
|------|-------|----------|-----------|------|
| Composio | 20k⭐ | 新建 `integrations/composio_bridge.py` | 250+ 外部服务集成 | ✅ 已完成 (2026-03-23) |
| Skyvern | 11k⭐ | 新建 `integrations/skyvern_bridge.py` | 视觉 RPA | ✅ 已完成 (2026-03-24) |
| inkos + MuMuAINovel | 2.4k+1.9k⭐ | 新建 `novel_writer.py` | AI 网文写作引擎 | ✅ 已完成 (2026-03-26) |
| Prefect | 17k⭐ | 替代 APScheduler | 高级任务编排 | 📋 待搬运 |

### 3.4 价值位阶 4 — 前瞻储备

| 项目 | Stars | 搬运目标 | 替代/增强 | 状态 |
|------|-------|----------|-----------|------|
| AG2 (AutoGen 2) | 40k⭐ | 潜在替代 CrewAI | 多 Agent 对话框架 | 🔮 评估中 |
| DSPy | 23k⭐ | 优化 `intent_parser.py` | 声明式 LLM 编程 | 🔮 评估中 |

---

## 4. 测试模块注册表

> 最后更新: 2026-03-23 (QA 价值位阶审计)

### 4.1 测试覆盖矩阵

| 测试文件 | 被测模块 | 测试数 | 覆盖类型 | 新增日期 |
|----------|----------|--------|----------|----------|
| `test_omega_core.py` | brain, intent_parser, task_graph, executor | 15 | 端到端集成 | 2026-03-23 |
| `test_security.py` | core/security.py | 35+31x | 单元+安全渗透 | 2026-03-23 |
| `test_cost_control.py` | core/cost_control.py | ~20 | 单元+边界 | 2026-03-23 |
| `test_event_bus.py` | core/event_bus.py | ~28 | 单元+集成 | 2026-03-23 |
| `test_self_heal.py` | core/self_heal.py | 28 | 单元+熔断器 | 2026-03-23 |
| `test_bash_tool.py` | tools/bash_tool.py | 31 | 安全沙箱 | 2026-03-23 |
| `test_risk_manager.py` | risk_manager.py | ~45 | 单元+边界+集成 | 2026-03-22+ |
| `test_auto_trader.py` | auto_trader.py | ~25 | 单元+容错 | 2026-03-22+ |
| `test_position_monitor.py` | position_monitor.py | ~30 | 单元+退出条件 | 2026-03-22+ |
| `test_trading_system.py` | trading_system.py | 25 | 单元+生命周期 | 2026-03-22+ |
| `test_e2e_pipeline.py` | trading pipeline | ~35 | 端到端 | 2026-03-22 |
| `test_broker_bridge.py` | broker_bridge.py | 20 | 单元+mock | 2026-03-22 |
| 其余 20 文件 | 各模块 | ~280 | 混合 | 2026-03-22 |

**总计: 980 passed = 980 个测试用例 (R8 新增 34 个)**

### 4.2 未覆盖的 P0 模块

| 模块 | 行数 | 缺失原因 | 优先级 |
|------|------|----------|--------|
| `src/chat_router.py` | 1,415 | 群聊路由复杂度高，需 mock 7 Bot | P1 |
| `src/shared_memory.py` | 1,070 | **R8 已补测试 (6 cases)** | ✅ |
| `src/context_manager.py` | 751 | 依赖 LLM token 计数 | P2 |
| `src/litellm_router.py` | 653 | 依赖 50+ API key | P2 |

---
