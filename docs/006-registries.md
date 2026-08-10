# 项目注册表总集

> 合并自原 030-api-pool-registry.md + 031-command-registry.md + 032-dependency-map.md + 033-module-registry.md

## 2026-08-08 JIYU AI / Sub2API 部署注册

> 本节是当前生产唯一事实源。下方旧 New-API 注册项仅保留给本地开发历史和代码兼容查阅，不能据此恢复生产数据或服务。

| 类型 | 唯一事实源 / 入口 | 当前合同 |
|---|---|---|
| 对外品牌 | `JIYU AI` / `Unified AI API Gateway` | 通过 Sub2API OEM `site_name`、`site_subtitle` 保存到 PostgreSQL；登录页、首页、侧边栏和浏览器标题统一读取该设置 |
| 生产底座 | Oracle `jiyu.245334.xyz` / `sub2api.service` | 基于官方 Sub2API `v0.1.173` 固定提交构建的 `v0.1.173-jiyu.31344140382` ARM64 二进制；JIYU 补丁可从官方提交重复应用，主进程只绑定 `127.0.0.1:18080` |
| 数据库 | PostgreSQL 16 `sub2api` | 独立角色、独立数据库；首次安装不导入 New-API 用户、Key、渠道、兑换码、日志或上游凭据；当前只保留 1 个管理员 |
| 缓存 | `sub2api-redis.service` | 专用 Redis 7 实例，绑定 `127.0.0.1:16379`，密码只保存在 Oracle `/etc/sub2api/sub2api.env` |
| 管理脚本 | `scripts/sub2api_oracle_manage.sh` / Oracle `/usr/local/sbin/openclaw-sub2api-manager` | `install-jiyu-build <path>` 用于完整发布；`stage-jiyu-build <path>` 原子暂存已校验二进制，并调度独立 systemd 任务在 WebUI 重启后核对运行哈希和健康状态；`pricing-fallback` 校验并原子安装官方模型价格回退资源；`region-headers` 收口 Cloudflare 地域头信任边界；`recharge-center` 原子维护最小回退页和精确 `frame-src`；`enable-web-update <broker> <manifest-url>` 安装固定 root 更新代理 |
| 自动更新 | `.github/workflows/sub2api-jiyu-compat.yml` + `scripts/sub2api_jiyu_update_broker.sh` + `sub2api-update.timer` | CI 从官方稳定标签构建带 JIYU 补丁的 ARM64 兼容包并生成 SHA-256 清单；当前兼容基线只允许 `v0.1.172`/`v0.1.173`，未知上游标签失败关闭。当前生产 `v0.1.173-jiyu.31344140382` 已启用受管更新 |
| 自动备份 | `sub2api-backup.timer` / `sub2api-backup.service` | 每日 03:40（Asia/Singapore，随机延迟 15 分钟）备份 PostgreSQL、二进制、版本和 root-only 环境文件；本地 `/var/backups/sub2api` 保留 30 天 |
| 管理员账号 | 受控身份，不记录标识 | 当前唯一管理员；密码不写仓库，已存入 macOS 钥匙串服务“CC中转 Sub2API 管理员” |
| 凭据保管 | Oracle `/etc/sub2api/sub2api.env` + 本机钥匙串 | Oracle env `0600 root-only`；修改管理员密码后同步更新这两处并做真实登录验证 |
| 旧底座清理 | Oracle、腾讯云、R2 | Oracle/Tencent 旧 New-API 数据目录、SQLite/容器/镜像、systemd 服务和同名本地备份已删除；旧 R2 加密对象已删除并重建为只含 JIYU runtime/application.env 的新备份 |
| 图形 Logo | `scripts/assets/jiyu-ai-logo-email.png` / `/api/v1/pages/docs/images/jiyu-ai-logo.png` | 512×512 PNG，源自选定的 2K JY 标志；站内继续使用 2K 等比图形，验证码、通知邮箱和运维告警模板通过同域公开 PNG 加载 |
| 文档入口 | `/custom/docs` / `md:docs` | 左侧“文档”提供 CC Switch v3.19.2 三平台下载和全部官方版本入口；四个入口使用桌面四列、窄屏两列的同宽网格。创建密钥时按 Claude/OpenAI 展示根端点或 `/v1`，并默认在创建后立即导入 CC Switch |
| 定制补丁 | `scripts/sub2api-jiyu-v0.1.173.patch` | 当前生产补丁；`v0.1.172` 对应补丁仍保留用于可恢复发布。覆盖品牌隐私、账号列表供货域名隐藏、标题/版本徽标、创建密钥端点引导、CC Switch、充值中心固定公开嵌入和公告空状态 |
| 历史渠道迁移 | `scripts/sub2api_configure_jiyu_channels.mjs` | 只保留为可从 Git 恢复的数据库迁移材料；其前置基线固定为 6 个聚合渠道、目标为 10 个一对一渠道，当前 16 渠道生产态不得再次执行 |

### JIYU AI 上游、分组与渠道注册

永久测试用户为受控身份，不记录标识；不记录密码、Key、Token 或 Cookie，并保留独立、可轮换的真实调用验证能力。

| 项目 | 当前约束 |
|---|---|
| 渠道家族 | 两个匿名渠道家族 |
| 业务渠道 | 16 条 active 业务渠道，其中 4 条只服务 `region=cn` 国内分组 |
| 监控 | 按用户要求恢复 Sub2API 原生 Channel Monitor V1 主动探测；V2 配置、watermark、聚合表和历史保留，可维护窗口恢复；该选择不是稳定性阻塞项 |
| 自营 Plus/Pro 池 | 两个自营号池当前均无库存 |
| 定价与供应 | 内部定价由所有者控制；公式、数值及渠道供应商数据不得进入文档或用户 UI |
| 原生账号费率回写 | 保持禁用，因其无法保留已批准的业务合同 |

### JIYU AI 邮箱与条款注册

| 项目 | 当前合同 |
|---|---|
| SMTP | Gmail `smtp.gmail.com:587` + TLS；用户名、发件邮箱均为管理员邮箱，应用密码只保存在服务器加密设置，不写仓库 |
| 邮箱绑定 | 个人资料提供“管理邮箱 → 发送验证码 → 更换主邮箱”；开放注册仍关闭，注册邮箱验证已开启，新用户默认余额 `0`、并发 `5`、RPM `60` |
| 邮件模板 | `auth.verify_code`、`notification_email.verify_code`、`ops.alert` 中文模板均使用 JY 图形 Logo；验证码模板明确绑定用途、验证码和有效期 |
| 登录条款 | 2026-08-07 生效；弹窗强制确认；目标为中国大陆 IP 指向中国站点、其他 IP 指向海外站点；中国站点前置条件未满足前，线上仍由海外唯一事实源提供服务并执行模型地域限制；其他制裁、出口管制或上游服务限制仍适用 |

---

## 2026-08-05 审计闭环注册增量

| 类型 | 唯一事实源 / 入口 | 当前合同 |
|---|---|---|
| 目标驱动审计 | `docs/009-health.md` 顶部 Destination / Notes / Decisions / Frontier | 复用 mattpocock `wayfinder` + `to-tickets` 结构；不创建被仓库规则禁止的 `CONTEXT.md` 或 docs 子目录。 |
| JIYU 数据层 | Sub2API PostgreSQL + 专用 Redis | 用户、渠道、倍率、监控、订阅、用量和更新状态以生产数据库与服务 API 为唯一事实源；仓库不再复制旧 Node runtime。 |
| 闲鱼运营投影 | `packages/clawbot/src/xianyu/operations_projection.py` | 唯一公开接口 `project_operations(snapshot)`；只接受普通快照，一次生成 sale readiness、loop watch、buyer progress，运行对象固定拒绝。 |
| Intel Brief schema | `packages/clawbot/src/intel/db/store.py` / schema v4 | 旧 `content_delivery_attempts` 原子重建为稳定 `event_key` 去重结构；旧记录按 content item event key 迁移，真实库迁移前必须 SQLite `.backup`。 |
| 本机每日备份 | `make backup-run` / `backup-schedule-install` / `backup-schedule-status` / `backup-schedule-uninstall` / `backup-restore-drill` | `ai.openclaw.daily-backup` 默认 03:30 运行；备份成功后必须 restore drill，失败返回非 0。已有备份不随卸载删除。 |
| 备份配置 | `OPENCLAW_BACKUP_DIR` / `OPENCLAW_BACKUP_OFFSITE_DIR` / `OPENCLAW_BACKUP_GPG_RECIPIENT` / `OPENCLAW_BACKUP_RETENTION_DAYS` / `OPENCLAW_BACKUP_RETENTION_COUNT` | 本机默认 `~/.local/share/openclaw/backups`、30 天/最多 14 份；配置离机目录时必须同时提供本机 GPG 公钥，只发布 `.tgz.gpg` + checksum + ready。 |
| 安全门 | `make security-check` | ShellCheck、Gitleaks、四套 npm、Linux/macOS pip-audit、RustSec 和供应链合同统一入口；GitHub PR 对所有目标分支执行同构门。 |
| 主容器安装 | `packages/clawbot/Dockerfile` / `docker-compose.yml` | Python 依赖使用 Linux x86_64 完整哈希锁与精确源码包白名单；Compose 固定 `linux/amd64` 和基础镜像 digest，运行用户非 root。 |

## 2026-08-04 运行与质量门注册增量

| 类型 | 唯一事实源 / 入口 | 当前合同 |
|---|---|---|
| 桌面 npm 运行时 | `apps/openclaw-manager-src/src-tauri/npm-runtime-lock/package.json` + `package-lock.json` | OpenClaw 固定 `2026.7.2-beta.7`；9 个直接运行包、354 个含传递依赖的 SHA-512 图；只允许 `npm ci --omit=dev --ignore-scripts`。MCP 与供应链检查均从该 manifest 读取精确版本，不保留第二份版本字符串。 |
| Tauri 运行时管理 | `src-tauri/src/commands/npm_runtime.rs` | 清单内嵌进签名 App，安装目录为 `~/.openclaw/manager-npm-runtime`；锁漂移或入口缺失会清理不完整目录并失败关闭。 |
| MCP Store 目录 | `src-tauri/src/commands/mcp.rs` + `src-tauri/src/commands/npm_runtime.rs` | 从唯一类型化 `MANAGED_MCP_PACKAGES` 展示 8 个受管运行包及锁定版本；只读 DTO 不含 command/args/env，桌面端不伪装 stdio 启停。真实 MCP 会话由 CC Switch/OpenClaw 官方配置链建立。 |
| JIYU 支付超时 | Sub2API 原生支付设置 / `SUB2API_PAYMENT_REQUEST_TIMEOUT_MS` | 外部支付请求必须有有限超时；未配置真实商户凭据时保持关闭，不把失败提示伪装成余额到账。 |
| Python 平台锁 | `packages/clawbot/requirements-lock.txt` / `requirements-lock-macos.txt` | Linux x86_64 与 macOS arm64 Python 3.12 全量哈希锁；`aiohttp>=3.14.3`、`cryptography>=50.0.0`。 |
| 异步所有权 | `packages/clawbot/src/core/loop_owner.py` | Brain/EventBus、券商、闲鱼、WebSocket、CLI 和可复用 async primitive 通过所有者循环调用；未绑定不得跨线程偷建。 |
| 主动任务域 | `packages/clawbot/src/core/proactive_periodic.py` | 主动检查的周期任务从核心引擎拆出，由主循环创建与取消。 |
| JIYU 安全域 | Sub2API 原生认证、Cloudflare WAF、站内内容预拦截 | 注册/登录限流、人机验证、DDoS 缓解和敏感字段脱敏由生产边界统一负责。 |
| 质量命令 | `make python-lock-check` / `make security-check` / `make supply-chain-check` / `make test-cov` / `make docs-check` | 分别验证双平台锁、密钥/依赖/Rust/Shell 安全门、Action+npm 完整性、总体/关键覆盖率、文档结构与事实。 |
| 桌面回滚 | `make tauri-rollback-check` / `make tauri-rollback` | 前者只读核验上一版签名/CDHash；后者必须显式确认并执行事务交换。 |

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
| 19 | inroi 授权上游 | 付费授权余额站 | 1 | 请求地址为 `https://www.inroi.shop/v1`；已验证 `/v1/models` 21 个模型和 `gpt-5.4-mini` Chat Completions；真实 Key 仅在服务器 runtime 加密号池保存 | JIYU AI 管理端号池 |
| 20 | 86GameStore 授权上游 | 付费授权余额站 | 1 | 请求地址为 `https://api.86gamestore.com`；本地 JIYU AI runtime 已按 Claude/OpenAI 两个模型组分开保存并探测 healthy，Claude 组覆盖 `claude-sonnet-4-5-c`、`claude-opus-4-6-c`，OpenAI 组覆盖 `gpt-5.4-mini`、`gpt-5.3-codex`、`gpt-5.4`、`gpt-5.5`；真实 Key 仅在 ignored runtime 中以 `enc:v1:` 保存 | JIYU AI 管理端号池 |

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

运行时能力必须显式启用，关闭时不得进入模型路由、fallback 或交易调度：

| 开关 | 默认值 | 启用后要求 |
|---|---|---|
| `G4F_ENABLED` | `false` | G4F 可复现虚拟环境存在，LaunchAgent 运行且 18891 可达 |
| `KIRO_GATEWAY_ENABLED` | `false` | Kiro Gateway 虚拟环境和 Key 存在，LaunchAgent 运行且 18793 可达 |
| `OLLAMA_ENABLED` | `false` | 本机 11434 可达；`OLLAMA_API_KEY` 可选，`LOCAL_HF_MODEL_ENDPOINT` 可覆盖地址 |
| `IBKR_ENABLED` | `false` | IB Gateway/TWS 端口可达；才注册连接、资金、成交、撤单和健康任务 |
| `AUTO_RESUBMIT_PENDING_NEXT_SESSION` | `false` | 仅在 `IBKR_ENABLED` 已启用且 `AutoTrader.auto_mode=true` 时允许隔夜 BUY 重挂；人工确认模式始终拒绝自动提交 |
| `HEARTBEAT_SENDER_ENABLED` | `false` | 目标主机/端口已配置并完成主备实机验收 |

---

## 二、命令注册表


> 最后更新: 2026-08-04 (支付验签 + 实盘卖出复核 + 闲鱼放行 + 认证与调度安全门) | Bot 命令总数 105

---

## JIYU AI 运维与本机 MCP 入口

| 入口 | 命令 | 说明 |
|---|---|---|
| 生图 MCP 安装 | `scripts/install_jiyu_image_mcp.sh install` | 安装锁定依赖的 stdio MCP，清理两个失效旧条目，并同步到 CC Switch 的 Claude、Codex、OpenCode |
| 生图 Key | `scripts/install_jiyu_image_mcp.sh set-key` | 隐藏输入后写入 macOS 钥匙串服务“JIYU AI 生图 API Key”，脚本和 CC Switch 数据库均不保存明文 |
| 生图 MCP 状态 | `scripts/install_jiyu_image_mcp.sh status` | 只返回安装文件、CC Switch 条目和钥匙串三项布尔状态，不回显 Key |
| 兼容包暂存 | `scripts/sub2api_oracle_manage.sh stage-jiyu-build <path>` | root 发布内部入口；备份后原子替换磁盘二进制与 VERSION，不直接杀死正在服务的进程，并创建独立验证任务 |
| 兼容包验证 | `scripts/sub2api_oracle_manage.sh verify-jiyu-stage` | 仅供 systemd 内部调用；重启后校验运行中 `/proc/<pid>/exe` 哈希与 `/health`，失败或超时自动恢复发布前二进制、VERSION 和数据库 |
| WebUI 更新启用 | `scripts/sub2api_oracle_manage.sh enable-web-update <broker> <manifest-url>` | 安装固定 root 代理、root-only 清单 URL、最小 sudoers 和 systemd 环境；完成健康检查后才放开受管更新接口 |
| Codex WS 桥接启用 | `scripts/sub2api_oracle_manage.sh openai-ws-http-bridge` | 启用官方 OpenAI WS 模式路由；账号仍需在 WebUI 选择 `http_bridge`，不直接写数据库或改上游地址 |
| Codex WS 旧模式回滚 | `scripts/sub2api_oracle_manage.sh openai-ws-legacy` | 关闭官方模式路由并恢复旧版传输判定；用于桥接异常时快速回滚 |
| 本地补号助手 | OpenClaw Manager 的“系统设置 -> 补号助手”，或 `http://127.0.0.1:18796` | 桌面入口自动启动只绑定 `127.0.0.1:18796` 的可视化 Web App；兼容分隔行、标签块和 JSON，串行走 Sub2 原生 OpenAI OAuth，识别 Plus/Pro 后只匹配同名自营号池，绝不回退渠道A/B；密码/TOTP/Token 只在进程内存，挑战页面暂停人工。`make jiyu-sub2-replenish` 仅保留为排障入口 |
| 本地补号演练 | `make jiyu-sub2-replenish-dry-run` | 只验证三类严格解析、自营号池语义、掩码和页面，不读取钥匙串、不打开登录窗口、不调用生产接口 |
| Telegram 补号安全提示 | `/jiyu_replenish`、`/jiyu_replenish cancel` | 仅授权管理员私聊提示远程材料提交和本地批次控制均已禁用，唯一入口是本机桌面设置或本机网页；提示后同一私聊的下一条普通文本会被一次性保护消费而不读取，`cancel` 仅取消该等待状态。`status`、`stop` 与遗留键盘操作均明确回复 Telegram 无法查看或控制本地批次；群聊失败关闭。 |

---

## 0. JIYU AI Web 操作入口

| 入口 | 选择器 / 路径 | 说明 |
|------|---------------|------|
| 账户菜单 | `data-auth-toggle` / `data-auth-panel` | JIYU AI 用户端右上角注册和登录入口 |
| 中英文切换 | `data-language-toggle` / `data-language-status` | 用户端顶栏语言偏好入口；当前只切换 `html.lang` 和偏好提示，完整英文界面未接入时会明确提示“仅切换语言偏好” |
| 用户注册 | `data-register-account` / `/api/frist/challenge` | JIYU AI 用户端注册入口，注册专用验证码挑战，公开页不回显答案 |
| 用户登录 | `data-login-account` | JIYU AI 用户端邮箱密码登录入口，不再要求每次登录填写验证码 |
| 忘记密码 | `data-password-reset-request` / `/api/frist/password-reset/request` | 登录前按邮箱发送重置验证码，SMTP 未配置时返回明确反馈 |
| 重置密码 | `data-password-reset-confirm` / `/api/frist/password-reset/confirm` | 用户输入重置验证码和新密码后完成 PBKDF2 密码更新 |
| 管理员身份码 | `data-owner-claim-code` / `data-owner-claim` | 登录后用一次性身份码把当前账号升级为管理员 |
| 运营入口 | `data-owner-entry` | 仅管理员账号可见，进入独立管理页 |
| 返回首页 | `data-back-home` / `data-route="dashboard"` | 子页面用“首页”短按钮返回用户首页，避免导入、测试、配置等页面迷路 |
| 创建 Key | `data-create-key` | 创建用户 `fk-live-*` API Key，兼容旧 `sk-*` |
| Key 改名 | `data-key-name` / `data-rename-key` | 修改单个用户 API Key 的显示名称 |
| Key 删除 | `data-delete-key` | 删除单个用户 API Key |
| Key 开关 | `data-toggle-key` | 开启或关闭单个用户 API Key |
| 兑换码购买入口 | `data-xianyu-purchase-link` | 当前暂未正式售卖；预留未来外部交易平台商品链接，内测/购买卡密后回站内兑换 |
| 微信支付回调 | `/api/frist/payments/wechat/notify` | 微信支付 APIv3 回调验签、解密和按订单号幂等入账 |
| 支付宝支付回调 | `/api/frist/payments/alipay/notify` | 支付宝当面付异步通知验签和按订单号幂等入账；渠道必须同时配置 App ID、商户私钥和平台公钥，缺平台公钥时不进入就绪状态且通知固定 503 失败关闭 |
| 兑换码 | `data-redeem-code` | 日卡/月卡/加油包兑换 |
| 余额预警设置 | `data-balance-alert-card` / `data-balance-alert-enabled` / `data-balance-alert-threshold` / `data-balance-alert-email` | 用户在账单页自定义低余额提醒阈值和收件邮箱 |
| 余额预警保存 | `data-balance-alert-save` | 保存当前用户的余额预警配置 |
| 余额预警测试邮件 | `data-balance-alert-test` / `data-balance-alert-feedback` | 发送一封品牌化余额预警测试邮件，验证 SMTP 配置 |
| Tabcode Console 风格系统 | `data-design-system="tabcode-console"` / `.brand-mark` | JIYU AI 用户端和管理端吸收 Tabcode 控制台视觉；用户端 Logo 保留红白斜切抽象品牌标，不再退回单字母占位 |
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
| 闲鱼全自动发货 webhook | `/api/ops/xianyu/paid-order` | 由 OpenClaw `XianyuLive` 或后续浏览器助手在检测到“等待卖家发货/已付款”后调用；低权限 token 鉴权，未付款订单阻断，成功后分配兑换码并返回发货话术；本机传入稳定 `orderId`，服务端按 `orderId` 幂等，重复订单不会重复分配卡密 |
| 闲鱼发货补救队列 | `127.0.0.1:18800/api/cc-shipments` / `/api/cc-shipments/{id}/resolve` / `/api/cc-shipments/{id}/mark-sent` / `/api/cc-shipments/{id}/mark-send-failed` | 本机受 `X-API-Token` 保护的闲鱼 GUI 接口；记录 CC中转 webhook 已发、消息发送失败、话术缺失、异常、人工已处理、`manual_delivery_ready` 漏单兜底和 `browser_delivery_claimed` 浏览器领取中状态；卡已分配但未确认发给买家时会进入补救队列，老板粘贴发送后必须点 mark-sent 才算真实已发货，浏览器发送失败会 mark-send-failed 退回重试队列 |
| 闲鱼商品套餐映射 | `127.0.0.1:18800/api/cc-item-mappings` + `127.0.0.1:18800/api/items` | 本机 GUI 配置 `item_id → planId`；GUI 会展示最近捕获到的闲鱼商品并一键填入映射表单；CC中转自动发货优先按商品映射发对应套餐，无映射时才回退默认套餐或任意未售卡密 |
| 闲鱼已付款漏单兜底 | `127.0.0.1:18800/api/cc-manual-paid-order/dispatch` | 本机受 `X-API-Token` 保护；仅在老板已从闲鱼界面确认“买家已付款/等待发货”但 WebSocket 未触发时使用。接口调用低权限 webhook 分配兑换码并返回可复制话术，状态先记为 `manual_delivery_ready`，不自动标记已发货、不自动点击闲鱼、不绕风控。浏览器/桥接器在暂停状态下若带 `one_shot=true`，必须先消费 `/api/cc-operator-mode/one-shot-delivery` 的单次放行票，否则不会生成并发送卡密 |
| 闲鱼真实待发货只读扫单 | `127.0.0.1:18800/api/cc-paid-order-probe` + `XianyuLive.scan_cc_paid_orders_readonly()` | 本机受 `X-API-Token` 保护；只读读取闲鱼卖家“待发货”列表，用于老板重新下单后确认系统是否看得到真实候选单。返回订单哈希、买家/商品是否存在、本机履约状态等脱敏摘要；不分配卡密、不调用 webhook、不发送闲鱼消息、不点击“去发货”、不解除 `auto_ship_paused` |
| 闲鱼浏览器付款页兜底发卡 | `127.0.0.1:18800/api/cc-manual-paid-order/dispatch` + Chrome 插件 `paid_page_dispatch` | 当卖家订单列表 API 无权限且本机没有待发送话术时，Chrome 插件可在当前闲鱼页先确认可见“已付款/待发货”信号，再调用本机受保护接口生成卡密话术并发送；页面能从 URL、可见“订单号/交易号”、白名单订单参数或订单相关 `data-*` / “去发货”链接提取真实订单号时，会以 `xianyu-real:*` 转为 `xy_oid_*`，否则仍生成 `xy_browser_*`，仅用于生产内测补救，不计入正式售卖真实自动订单严格门。暂停状态下插件/桥接器必须带 `one_shot=true` 并消耗单次放行票，避免重复发送 |
| 闲鱼浏览器发货助手 | `127.0.0.1:18800/api/cc-browser-delivery/next` + Chrome 插件 `xianyuDeliveryScan/xianyuDeliverySend/xianyuDeliveryWatchSet` | 本机受 `X-API-Token` 保护；Chrome 插件在闲鱼聊天页检测“已付款/待发货”等可见信号后，原子领取已分配待发送话术并把状态改为 `browser_delivery_claimed`，防止多个浏览器/桥接器/标签页重复拿同一张卡密；自动发货暂停时默认返回 `operator_paused` 且不返回话术。`one_shot=1` 的票检查与消费位于同一跨线程/跨进程事务，多个助手并发时只有一个能成功；状态缺失或损坏时默认暂停。填入并点击发送成功后调用 `/api/cc-shipments/{id}/mark-sent`，失败调用 `/api/cc-shipments/{id}/mark-send-failed` 退回失败队列。看守模式支持锁定当前聊天页，也支持“看守所有闲鱼页”；全局看守只有本机刚好 1 条待发货时才启用，避免多单场景发错买家。成功发送一次后自动关闭。发送成功后会继续尝试当前页安全点击闲鱼“去发货/无需物流/确认发货”，失败只回写原因，不重复分配卡密、不自动砍价、不批量私信、不绕风控 |
| 闲鱼浏览器确认发货 | `127.0.0.1:18800/api/cc-xianyu-confirm/next` + `/api/cc-xianyu-confirm/current-page-candidate` + `/api/cc-shipments/{id}/mark-xianyu-confirmed` / `/mark-xianyu-confirm-failed` + Chrome/桥接器 `xianyuShipmentConfirm` | 本机受 `X-API-Token` 保护；正式队列只把 `message_sent`、未确认发货且订单号为 10 位以上数字的真实闲鱼订单交给浏览器助手，`xy_manual_*` / `xy_browser_*` 不进入正式 `xy_oid_*` 严格门。生产内测补救时，`current-page-candidate` 可返回已发卡密的手工/浏览器补救单候选，但浏览器页面执行器仍必须先看到当前页“已付款/待发货”可见信号，才会点击“去发货/无需物流/确认发货”；页面没有付款信号则安全跳过。结果写入 `cc_shipments.xianyu_confirm_status/xianyu_confirm_at/xianyu_confirm_error` |
| 闲鱼恢复可售兜底 | `127.0.0.1:18800/api/cc-xianyu-relist/next` + `/api/cc-shipments/{id}/mark-relisted` / `/mark-relist-failed` + Chrome 插件 `xianyuItemRelist` / `relist_queue_watch` | 买家确认收货后，如闲鱼商品页明确显示“已下架/已售罄/重新上架”，浏览器助手可点击“重新上架/恢复上架”并回写 `cc_shipments.xianyu_relist_status/xianyu_relist_at/xianyu_relist_error`；页面显示仍在售时不会点击，不改标题、不改价格、不新建商品 |
| 闲鱼可选后端确认发货 | `127.0.0.1:18800/api/cc-shipments/{id}/confirm-xianyu-backend` + `XianyuApis.confirm_dummy_shipment()` + `CC_XIANYU_AUTO_CONFIRM_SHIPMENT_ENABLED` | 借鉴开源闲鱼管理系统的虚拟商品确认发货做法；默认关闭。只有已成功发送兑换码、订单号是闲鱼真实数字订单号且显式开启时，才调用 `mtop.taobao.idle.logistic.consign.dummy` 尝试把闲鱼订单推进为已发货。18800 补救队列会对真实数字 `message_sent` 订单显示“后端确认发货”按钮；结果只写入 `cc_shipments.xianyu_confirm_status`，失败不回滚卡密发货，不对 `xy_manual_*` / `xy_browser_*` 内测兜底单执行 |
| 闲鱼自动化运营水位 | `127.0.0.1:18800/api/cc-sale-readiness` / `/api/status.cc_chrome_extension` | 本机 GUI 汇总自动发货可用性、正式售卖门槛、webhook/ws/cookie/补救队列/商品映射状态、自动发货套餐路由预判、买家自助入口健康和仍需人工介入事项；`cc_chrome_extension` 只读保留 X/小红书 Social Pilot 能力上报，闲鱼卖家桥接器通过 `manifest_version=bridge` 表示 CDP 接管；不输出 token、卡密或用户 Key |
| 闲鱼正式售卖上架锁 | `127.0.0.1:18800/api/cc-public-sale-lock` | 本机 GUI 只读上架门禁；默认读取缓存，`refresh=true` 时运行只读巡检刷新库存/兑换码/渠道/买家入口证据；只有自动发货、补救队列、库存、兑换码、渠道、买家主站/API 网关、webhook 未授权拦截、CC Switch 导入入口和真实小额单严格门全部满足才显示 `public_sale_unlocked`。若严格门已通过但老板手动暂停自动发货，会返回 `state=paused_after_strict_gate`、`state_label=严格门已通过，自动发货暂停保护`、`can_public_sale=false`，明确这是防重复发卡保护而非链路故障 |
| 闲鱼实单闭环观察 | `127.0.0.1:18800/api/cc-loop-watch` | 本机 GUI/后台守护线程轻量观察真实订单闭环阶段：自动发货配置、WebSocket、Cookie、补救队列、真实订单数、商品映射、后台严格门节流状态和严格买家闭环是否通过；展示最近严格门脱敏摘要和后台严格门观察最近运行结果，摘要会落盘到本机 SQLite；不输出卡密 |
| 闲鱼买家链路进度 | `127.0.0.1:18800/api/cc-buyer-chain-progress` | 只读聚合真实订单买家侧五步：已发货、已兑换、API Key、调模型、同单闭环；供 `/ops-links` 和本机 GUI 判断买家卡在哪一步，不触发审计、不发货、不分配卡密、不改库存 |
| 闲鱼下一步行动建议 | `127.0.0.1:18800/api/cc-operator-next-action` | 只读聚合上架锁、自动发货、补救队列、真实订单和买家链路，返回 `state/severity/title/primary_action/checklist`，并带 `buyer_site_smoke_plan`；供 Chrome 入口、GUI 和后续通知复用，不触发审计、不发货、不分配卡密、不改库存 |
| CC中转本机人工控制 | `127.0.0.1:18800/api/cc-operator-mode` + `/api/cc-operator-mode/resume-preflight` | 本机受 `X-API-Token` 保护的操作台开关；`GET` 返回自动发货是否暂停、webhook 是否配置、是否可自动发已付款订单、补救队列和四步操作状态；`POST` 可暂停/恢复自动发货。暂停只写 `.openclaw/cc-zhongzhuan-operator-state.json`，不改卡密、不改订单、不改闲鱼商品；暂停后浏览器待发接口也不会返回卡密话术，防止插件/桥接器绕过暂停继续发送。恢复自动发货前必须通过只读安全预检：补救队列清空、库存/兑换码/渠道、买家入口、webhook 未授权拦截、CC Switch、闲鱼连接/Cookie 和真实小额单严格门均正常，否则返回 409 并保持暂停；`resume-preflight` 只读返回同一份检查结果，不改变开关。恢复成功后会自动武装 `auto_resume_canary` 首单观察票，第 1 条卡密进入 `message_sent` 后自动重新暂停，防止连续发卡 |
| CC中转单次发卡放行 | `127.0.0.1:18800/api/cc-operator-mode/one-shot-delivery` | 本机受 `X-API-Token` 保护；在保持 `auto_ship_paused=true` 的前提下写入 1 张 3 分钟有效的单次放行票。授权、读取、消费和写回使用同一跨进程可重入锁，状态文件以 `fsync + os.replace` 原子提交；浏览器助手或 `cc_zhongzhuan_seller_bridge.mjs --one-shot-override` 并发时也只能消费 1 次，成功领取/生成一条卡密话术后自动失效；不恢复常驻自动发货、不改库存、不改闲鱼商品 |
| CC中转一键跑当前页 | `127.0.0.1:18800/api/cc-seller-bridge/one-shot-delivery` | 本机受 `X-API-Token` 保护；18800 操作台按钮调用卖家桥接器 `--delivery-only --one-shot-override --require-single-xianyu-page --require-real-order-id --json`，要求只打开 1 个闲鱼页；只检查当前已打开闲鱼页是否有“已付款/待发货 + 输入框 + 真实订单号/交易号”，最多发送 1 条卡密。不会点击闲鱼发货按钮、不会确认发货、不会恢复上架；当前页不是付款页或识别不到真实订单号时安全跳过且不留下单次放行票；多开闲鱼页会返回 `one_shot_requires_exactly_one_xianyu_page` |
| CC中转只读检查当前页 | `127.0.0.1:18800/api/cc-seller-bridge/page-scan` | 本机受 `X-API-Token` 保护；18800 操作台按钮调用卖家桥接器 `--scan-only --require-real-order-id --json`，只读返回卖家 Chromium 当前闲鱼页数量、付款信号、聊天输入框、发送按钮、待发货订单卡、去发货入口和订单号提示是否存在。不分配卡密、不调用 webhook、不申请单次放行票、不点击闲鱼、不改本机履约记录；识别不到真实订单号/交易号时只提示老板切到订单详情页，不发卡。只读扫描能跑完但当前页不满足发卡条件时返回 `scanCompleted=true/notReady=true`，不再把正常未命中包装成系统故障；当前页是闲鱼首页时会明确提示从消息或订单列表打开已付款订单，并在 18800 页面提供“打开闲鱼消息 / 打开卖家工作台”快捷入口 |
| CC中转卖家页面导航 | `127.0.0.1:18800/api/cc-seller-bridge/open-page` | 本机受 `X-API-Token` 保护；18800 按钮调用卖家桥接器 `--open-page=im|seller --json`，通过 DevTools 让卖家专用 Chromium 打开闲鱼消息或卖家工作台。只接受白名单目标，不支持任意 URL；不发卡、不申请单次放行票、不读取/修改订单、不点击闲鱼页面 |
| CC中转站内烟测计划 | `127.0.0.1:18800/api/cc-buyer-site-smoke-plan` | 只读说明站内买家烟测是否可准备、会写入哪些生产数据、清理要求和安全边界；当前 `executes_now=false`，未获明确确认前不创建用户、不兑换、不创建 API Key、不调模型 |
| CC中转实单验收包 | `127.0.0.1:18800/api/cc-real-order-test-pack` | 只读聚合真实小额单验收步骤、当前上架锁、自动观察状态、入口地址、商品模板、安全边界和 `buyer_site_smoke_plan`；证据缺失时只跑一次只读巡检刷新，不发货、不分配卡密、不发送闲鱼消息、不修改库存 |
| CC中转闭环覆盖清单 | `127.0.0.1:18800/api/cc-automation-coverage` | 只读把全自动售卖目标拆成 11 项证据：Chrome 入口、已付款检测、卡密分配、话术发送、履约回写、买家注册兑换、API Key、CC Switch、模型调用、安全边界和真实小额单严格门；同时返回 `auto_strict_audit_status`、`buyer_site_smoke` 与 `buyer_site_smoke_plan`；当前历史真实闲鱼订单严格门已 PASS，不能把它当作链动首笔 ¥1 实单证据 |
| CC中转人工预检闭环证据 | `127.0.0.1:18800/api/cc-manual-precheck-evidence` | 本机受 `X-API-Token` 保护的只读证据接口；一次性检查人工预检 6 项：注册/登录 CF 验证是否在组件容器内、邮箱模板是否为品牌卡片、闲鱼重复发卡保护、可控自动发货策略、1 元套餐 1:1 入账、真实小额单严格门。该接口只读源码和当前运行态，不发卡、不点击闲鱼发货、不恢复自动发货；当前自动发货未暂停、补救队列为 0，历史真实闲鱼订单严格门已 PASS |
| CC中转运营统一快照 | `127.0.0.1:18800/api/cc-ops-snapshot` | 只读一次性返回 `next_action/status/sale_lock/loop_watch/buyer_progress/auto_strict_audit_status/buyer_site_smoke/buyer_site_smoke_plan`，供 Chrome 入口、GUI、后续通知或看板复用；不触发审计、不发货、不分配卡密、不改库存 |
| CC中转本机运营提醒 | `127.0.0.1:18800/api/cc-ops-notify/check` | 受 `X-API-Token` 保护的本机提醒检查接口；后台线程默认值守状态变化，WebSocket/Cookie 异常、补救队列、低库存、真实单买家链路阶段变化时弹 macOS 通知；真实订单发货后会用 `buyer_attention_stage` 标记卡点（等待严格门/未兑换/未创建 API Key/未调模型/同单待确认/已闭环）；`force=true` 可从 `/ops-links` 手动发送当前状态提醒；不触发审计、不发货、不分配卡密、不改库存，也不自动催买家 |
| 闲鱼商品模板生成 | `127.0.0.1:18800/api/cc-product-template` | 生成只含履约说明的极简商品模板，包含付款后自动发卡、注册/登录、兑换到账、创建 API Key、CC Switch 导入和模型测试步骤；不写额外营销话术、不暴露 `/v1` 网关 |
| GUI 一键闭环审计 | `127.0.0.1:18800/api/cc-readiness-audit?mode=read_only|strict` | 本机受 `X-API-Token` 保护的只读审计接口；GUI 按钮可运行生产内测巡检或正式售卖严格门，不开放 `--webhook-smoke` 写入冒烟按钮；strict 结果会保存脱敏摘要到 `cc_strict_audits` |
| CC中转状态中心 | `127.0.0.1:18800/ops-links` | 本机免 token 打开的老板日常入口；Apple 风格暗色状态中心只展示一个结论、闭环圆环、自动发货、库存与渠道、买家链路和下一步。输入本机 `OPENCLAW_API_TOKEN` 后只读读取 `/api/cc-ops-snapshot` 与 `/api/cc-operator-mode`，不提供发货/分配卡密/冒烟写入按钮；工程详情默认折叠，`/v1`、`/v1/models` 和旧 `/admin.html` 不再作为人类入口收藏 |
| CC中转操作台 | `127.0.0.1:18800/` | 本机免 token 打开页面、API 受 `X-API-Token` 保护；Apple 风格深色状态面板 + 本机 `layui@2.13.8` 组件层（`/static/layui/...`，不走 CDN），首屏 6 张老板状态卡只回答：当前能不能卖、自动发货是否开着、库存是否够、上游余额是否够、是否有待处理订单、是否需要介入/是否有正式售卖资格。红/黄告警会通过 `top-alerts` 置顶，并给“怎么办/只读检查/只放行一次”按钮；恢复常驻自动发货前可点“恢复前安全检查”，恢复按钮也会二次确认并由后端预检兜底；恢复成功提示会说明“第 1 单发卡成功后会自动暂停”；商品绑定、漏单兜底、补救队列、只读巡检和高级排障默认折叠；补救队列使用 `layui-table`，确认/提示使用 layui layer；旧 `message_sent` 补救单待点击闲鱼发货时提示打开对应已付款页面，不要求重新下单 |
| New-API 兑换状态回写 | `/api/admin/redemption-cards/sync-newapi-status` / `SUB2API_NEWAPI_REDEMPTION_STATUS_SYNC_ENABLED` | JIYU AI 默认每 60 秒读取 New-API SQLite 兑换表，按卡密哈希把已发出的闲鱼卡密和履约状态回写为 `redeemed`；后台接口可手动触发，过程不输出完整卡密 |
| 闲鱼兑换码库存自动补 | `/api/admin/redemption-cards/autoreplenish` / `SUB2API_CARD_AUTOREPLENISH_ENABLED` | JIYU AI 生产可按安全库存自动生成 `1/5/15/50/100/500` 元套餐兑换码，默认日上限 50 张；服务启动后会按 `SUB2API_CARD_AUTOREPLENISH_INTERVAL_MS` 定时执行，仍受每日上限和套餐安全库存约束 |
| New-API 上游余额同步 | `/api/admin/upstream-balance` / `/api/admin/upstream-balance/sync` / `SUB2API_UPSTREAM_BALANCE_SYNC_ENABLED` | JIYU AI 可每日同步 New-API 上游余额，低于 50 元 warning、低于 20 元 critical；结果只给管理端展示或告警，不向用户暴露上游 token |
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
| 管理端卡密生成 | `/admin.html` + `data-admin-redemption-cards` / `data-admin-card-create` / `/api/admin/redemption-cards` | 按套餐批量生成一次性兑换码；新卡密落库为 `codeHash + codeCipher + codePreview`，明文只在创建响应和导出文本中出现 |
| 闲鱼自动发货助手 | `/admin.html` + `data-xianyu-*` / `/api/admin/xianyu/fulfillments` / `/api/ops/xianyu/remap-order` | 运营入口 `https://jiyu.245334.xyz/admin.html`；粘贴已付款订单后一键分配未售卡密、生成发货话术并标记 `sold/delivered`，买家兑换后回写 `redeemed`；低权限 `remap-order` 仅用于把已发卡浏览器临时单接管为真实闲鱼订单号，不分配新卡 |
| 管理端账号恢复 | `/admin.html` + `data-admin-password-reset` / `/api/admin/customers/password` | SMTP 不可用或用户无法收信时，由管理员重置客户密码；响应和审计不回显明文密码 |
| JIYU AI 品牌资产 | `scripts/assets/jiyu-ai-logo-email.png` / `/api/v1/pages/docs/images/jiyu-ai-logo.png` | JY 图形 Logo、站点 favicon、邮件和链动小铺商品统一使用；用户侧不展示其他品牌。 |
| CC中转合规页面 | `/index.html#about` / `#terms` / `#refund` / `#privacy` | 服务说明、服务条款、售后规则、隐私说明；从首页、兑换页和页脚可达 |
| 管理端 Plus 账号台账 | `/admin.html` + `data-admin-plus-accounts` / `data-admin-plus-save` / `data-admin-plus-edit` / `/api/admin/plus-accounts` | 登记和更新自用 ChatGPT Plus 账号、Apple ID、到期、TRY 余额、设备/Profile 和合规状态；不进入用户 `/v1` 路由 |
| 管理端 RT JSON 导入 | `/admin.html` + `data-admin-rt-accounts` / `data-admin-rt-import` / `/api/admin/rt-accounts/import` | 支持 JSON 数组、单个对象和 TXT 行导入 `refresh_token`、邮箱和账号 ID；只做脱敏台账和刷新准备，不减少 New-API 原有管理能力且不进入用户 `/v1` 路由 |
| 管理员 2FA | `/api/admin/2fa/verify` + `data-admin-2fa-code` | 管理端 TOTP 二次验证；启用 `SUB2API_REQUIRE_ADMIN_2FA=1` 后，管理 API 除 2FA 验证入口外都必须带有效二次验证会话 |
| 生产边界检查 | `/api/admin/production-readiness` + `data-admin-readiness` | 汇总固定品牌域名 `jiyu.245334.xyz`、New-API 数据库、健康上游库存、备份监控、管理员 2FA、Turnstile、兑换码收款闭环和长期渠道 SLA 状态；自动支付商户仅作备用；健康上游库存为 0 时必须 `ready=false` |
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
| 管理端根令牌 | `/admin.html` + `data-admin-token` / `data-admin-save-token` | 仅在当前页面内存中使用；刷新或关闭页面后清空，禁止写入 `localStorage` 等浏览器持久存储 |

---

### 0.1 JIYU AI 生产环境变量登记

| 环境变量 | 用途 | 备注 |
|----------|------|------|
| `SUB2API_SMTP_HOST` | 余额预警 SMTP 主机 | Gmail 可用 `smtp.gmail.com` |
| `SUB2API_SMTP_PORT` | 余额预警 SMTP 端口 | TLS 通常用 `465` |
| `SUB2API_SMTP_SECURE` | 是否使用 TLS | `1` 表示 TLS，`0` 表示明文连接 |
| `SUB2API_SMTP_FAMILY` | SMTP 地址族选择 | 默认 `auto`，可用 `6` 强制 IPv6、`4` 强制 IPv4 |
| `SUB2API_SMTP_USER` | SMTP 登录用户名 | 只放服务器环境变量 |
| `SUB2API_SMTP_PASSWORD` | SMTP 应用专用密码 | 禁止提交到 Git 或写进文档正文 |
| `SUB2API_SMTP_FROM` | 余额预警发件邮箱 | 默认可与用户名一致 |
| `SUB2API_BALANCE_ALERT_FROM_NAME` | 余额预警发件人名称 | Oracle 生产当前为 `CC-Billing`，避免 shell source 类脚本误把空格拆成命令 |
| `SUB2API_PASSWORD_HASH_SECRET` | CC中转用户密码哈希密钥 | 生产必须为强随机值；和会话密钥分离，便于轮换登录会话而不锁死旧账号 |
| `SUB2API_LEGACY_PASSWORD_HASH_SECRETS` | 历史密码哈希密钥兼容列表 | 逗号分隔；更换密码哈希密钥后临时保留旧值，用户下次登录成功后自动迁移 |
| `SUB2API_REQUIRE_CAPTCHA` | 是否启用注册验证码挑战 | `1` 启用；登录不再要求验证码 |
| `SUB2API_CAPTCHA_MAX_ATTEMPTS` | 单个验证码最大错误次数 | 默认 `3`，超过后需刷新挑战 |
| `SUB2API_PASSWORD_RESET_TTL_MS` | 忘记密码验证码有效期 | 默认 `900000`，即 15 分钟 |
| `SUB2API_PASSWORD_RESET_REQUEST_RATE_LIMIT_MAX` | 同一账号在窗口内允许的重置邮件请求数 | 默认 `3`；账号键使用服务端密钥 HMAC，达到上限后不再投递邮件 |
| `SUB2API_PASSWORD_RESET_REQUEST_RATE_LIMIT_WINDOW_MS` | 账号级重置邮件请求窗口 | 默认 `900000`，即 15 分钟 |
| `SUB2API_PASSWORD_RESET_CONFIRM_RATE_LIMIT_MAX` | 同一账号在窗口内允许的重置确认尝试数 | 默认 `5`；账号键使用服务端密钥 HMAC，不在内存键中保存明文邮箱 |
| `SUB2API_PASSWORD_RESET_CONFIRM_RATE_LIMIT_WINDOW_MS` | 账号级重置确认限流窗口 | 默认 `900000`，即 15 分钟 |
| `SUB2API_RATE_LIMIT_MAX_ENTRIES` | 进程内限流桶容量上限 | 默认 `10000`；先清理过期桶，仍满则拒绝新桶，不淘汰现有封禁 |
| `SUB2API_TRUSTED_PROXY_IPS` | Node 直连可信反向代理 IP 白名单 | 默认空并忽略全部转发头；Oracle 的本机 Nginx 反代应显式填实际对端 IP（通常 `127.0.0.1`），不得填公网客户端或不受控代理 |
| `SUB2API_REDEEM_RATE_LIMIT_MAX` | 兑换接口限流次数 | 默认 `12`；按 IP 和登录账号分别计数，防暴力猜卡密 |
| `SUB2API_REDEEM_RATE_LIMIT_WINDOW_MS` | 兑换接口限流窗口 | 默认 `60000`，即 1 分钟 |
| `SUB2API_DATA_ENCRYPTION_KEY` | runtime 敏感字段加密密钥 | 公开模式必填；用于加密用户 Key 和上游 rawKey；旧 key 不可恢复的历史 `enc:v1:` 字段会被隔离并提示重新生成 |
| `SUB2API_PUBLIC_GATEWAY_BASE_URL` | 用户导出和邮件使用的公网 `/v1` 网关地址 | 当前 CC中转生产内测值为 `https://jiyu.245334.xyz/v1`；旧数字域名和 nip.io 只保留跳转/冷回滚排障，不是当前用户导出入口；`https://www.inroi.shop/v1` 是上游请求地址，不是用户导出入口 |
| `SUB2API_REQUIRE_CSRF` | Cookie 登录态非幂等接口 CSRF 校验开关 | 生产建议 `1`；公开模式和 `NODE_ENV=production` 会自动启用 |
| `SUB2API_SESSION_TTL_MS` | 客户服务端会话有效期 | 默认 `604800000`（7 天），最短 5 分钟、最长 30 天；过期会话和旧版无 TTL 会话均要求重新登录 |
| `SUB2API_REQUIRE_ADMIN_2FA` | 是否强制管理端 TOTP 二次验证 | 生产强制模式必须为 `1`；Oracle 生产已开启 |
| `SUB2API_ADMIN_TOTP_SECRETS` | 管理员 TOTP Base32 Secret 列表 | 逗号分隔；只放服务器环境变量或 root-only 安全文件，不写文档正文 |
| `SUB2API_ADMIN_2FA_SESSION_TTL_MS` | 管理员 2FA 会话有效期 | 默认 `3600000`，即 1 小时 |
| `SUB2API_ALLOW_PRIVATE_UPSTREAM_URLS` | 是否允许管理端补号 URL 指向私网/本机地址 | 生产必须保持 `0`，只用于本地私网测试 |
| `SUB2API_CANONICAL_HOST` | CC中转唯一内容入口域名 | 当前生产内测为 `jiyu.245334.xyz`；旧 `245334.xyz`、`jiyu.245334.xyz` 和 nip.io 只保留跳转/冷回滚排障语境，不作为生产兜底入口 |
| `SUB2API_REDIRECT_HOSTS` | 需要跳转到唯一入口的旧/裸域名 | Oracle 用户入口以 `jiyu.245334.xyz` 为主；`jiyu.245334.xyz`、裸域和 nip.io 跳转到主站；`jiyu.245334.xyz` 不在跳转名单内，专用于 JIYU 运营台/自动发货助手 |
| `SUB2API_ENFORCE_PRODUCTION_READINESS` | 是否强制生产边界检查 | Oracle 生产已为 `1`；缺固定 HTTPS 品牌域名、New-API 数据库、2FA、兑换码/备份等运营闭环会启动失败；自动支付商户不是当前硬门槛 |
| `SUB2API_ALLOW_INSECURE_PUBLIC_HTTP` | 是否允许临时公网 HTTP 网关 | Oracle 生产已为 `0`；只有冷回滚排障才临时打开 |
| `SUB2API_BACKUP_STATUS_MAX_AGE_HOURS` | 备份新鲜度上限 | 默认 `26` 小时，超过视为备份监控未闭环 |
| `SUB2API_SLA_RETENTION_DAYS` | 渠道 SLA 探测事件保留天数 | 默认 `30` 天 |
| `SUB2API_CHANNEL_MONITOR_ENABLED` | 是否启用后台 60 秒通道巡检 | `1` 启用；无人调用时也会巡检健康库存 |
| `SUB2API_CHANNEL_MONITOR_INTERVAL_MS` | 后台通道巡检间隔毫秒 | 默认 `60000` |
| `SUB2API_CHANNEL_MONITOR_BATCH_SIZE` | 每轮巡检最多探测的 Key 数量 | 默认 `4`，防止一次性压测所有库存 |
| `SUB2API_CHANNEL_MONITOR_COOLDOWN_MS` | 同一 Key 自动巡检最小间隔毫秒 | 默认 `55000`，避免短时间重复探测 |
| `SUB2API_RATE_MARKUP` | 上游倍率同步后的固定加价 | 生产内测显式固定为 `0.1`；同步到 New-API 模型倍率时只在上游倍率基础上加 `0.1`，其余保持上游一致 |
| `SUB2API_XIANYU_WEBHOOK_TOKEN` | 闲鱼全自动发货低权限 webhook token | 只允许调用 `/api/ops/xianyu/paid-order` 发起已付款订单发卡，以及 `/api/ops/xianyu/remap-order` 接管已发卡订单号；不具备管理员权限；禁止写入文档正文或聊天 |
| `SUB2API_CARD_AUTOREPLENISH_ENABLED` | JIYU AI 是否启用兑换码库存自动补 | 生产内测建议 `1`；只补到安全库存，受每日上限限制 |
| `SUB2API_CARD_AUTOREPLENISH_INTERVAL_MS` | 兑换码库存自动补扫描间隔 | 默认 `86400000`，即每天一次；启动服务时会先跑一次 |
| `SUB2API_CARD_AUTOREPLENISH_DAILY_CAP` | 自动补兑换码每日上限 | 默认 `50`，防止异常循环大量发码 |
| `SUB2API_CARD_AUTOREPLENISH_SAFETY_STOCK` | 自动补兑换码安全库存 JSON/配置 | 留空使用默认档位：1元测试3张、5/15元各10张、50元5张、100元3张、500元1张 |
| `SUB2API_UPSTREAM_BALANCE_SYNC_ENABLED` | 是否启用上游余额定时同步 | 生产内测建议 `1`；只读同步 New-API 余额用于运营预警 |
| `SUB2API_UPSTREAM_BALANCE_SYNC_INTERVAL_MS` | 上游余额同步间隔 | 默认 `86400000`，即每天一次；启动服务时会先跑一次 |
| `SUB2API_UPSTREAM_BALANCE_WARNING_CNY` | 上游余额 warning 阈值 | 默认 `50` 元 |
| `SUB2API_UPSTREAM_BALANCE_CRITICAL_CNY` | 上游余额 critical 阈值 | 默认 `20` 元 |
| `SUB2API_UPSTREAM_BALANCE_STALE_HOURS` | 上游余额数据过期小时数 | 默认 `26` 小时，超过视为状态过期 |
| `SUB2API_UPSTREAM_BALANCE_WEBHOOK` | 上游余额预警 webhook | 可选；用于余额低于阈值时提醒老板充值 |
| `CC_XIANYU_AUTO_SHIP_ENABLED` | OpenClaw 闲鱼助手是否启用 CC中转自动发货 | `1` 启用；`0/false/no/off` 禁用并回退旧本地 AutoShipper |
| `CC_XIANYU_WEBHOOK_URL` | OpenClaw 调用 CC中转自动发货 webhook 的地址 | 当前生产内测指向 `https://jiyu.245334.xyz/api/ops/xianyu/paid-order`；本机会自动推导同域 `/api/ops/xianyu/remap-order` 用于真实订单号接管 |
| `CC_XIANYU_WEBHOOK_TOKEN` | OpenClaw 调用 CC中转 webhook 的低权限 token | 只用于已付款订单发卡；禁止打印完整值，生产变更后需重启 `ai.openclaw.xianyu` |
| `CC_XIANYU_AUTO_SHIP_PAUSED` | 自动发货运行时暂停的环境兜底 | 可选；`1/true/yes/on` 时启动后默认暂停。日常暂停/恢复优先使用本机操作台 `/api/cc-operator-mode`，不会要求老板改环境变量 |
| `CC_OPERATOR_STATE_FILE` | 本机操作台状态文件路径 | 可选；默认 `.openclaw/cc-zhongzhuan-operator-state.json`，测试用例用该变量隔离暂停状态 |
| `CC_XIANYU_AUTO_SHIP_DELAY_SECONDS` | OpenClaw 检测到已付款后的发货延迟 | 默认 `10` 秒，降低平台风控误判概率 |
| `CC_XIANYU_DEFAULT_PLAN_ID` | 闲鱼订单无 SKU 或无商品映射时的默认套餐 ID | 当前本机生产内测已固定为唯一可售日卡库存对应 planId；`/api/status.cc_auto_plan_routing` 与 `/api/cc-sale-readiness.plan_routing` 会显示实际路由模式和风险等级；多商品正式上架时仍优先在本机 GUI 配置 `item_id → planId` |
| `CC_XIANYU_DEFAULT_ITEM_ID` | 闲鱼订单无聊天商品上下文时的默认商品映射 | 可留空；用于买家不聊天直接付款时仍进入 CC中转自动发货链路 |
| `CC_XIANYU_RESCUE_LOOP_ENABLED` | 闲鱼消息发送失败后的自动补发循环 | 默认 `1`；只补发已分配且本机有完整发货话术的 `message_send_failed` 记录，不会重新分配卡密 |
| `CC_XIANYU_RESCUE_INTERVAL_SECONDS` | 自动补发队列扫描间隔 | 默认 `60` 秒；下限 `15` 秒 |
| `CC_XIANYU_RESCUE_BATCH_SIZE` | 每轮最多补发记录数 | 默认 `5`，最大 `20` |
| `CC_XIANYU_PAID_ORDER_POLL_ENABLED` | 是否启用闲鱼卖家待发货订单列表轮询兜底 | 默认 `1`；当前真实登录态可能返回 `PERMISSION_EXCEPTION::无权限访问`，因此只能作为加分兜底，不能替代 WebSocket/Chrome 付款页看守 |
| `CC_XIANYU_PAID_ORDER_POLL_INTERVAL_SECONDS` | 卖家订单列表轮询间隔 | 默认 `60` 秒；接口无权限时只记录安全告警，不分配卡密 |
| `CC_XIANYU_PAID_ORDER_POLL_BATCH_SIZE` | 每轮最多处理待发货订单数 | 默认 `5`，最大 `20`；同订单幂等，不重复发卡 |
| `CC_XIANYU_AUTO_READINESS_AUDIT_ENABLED` | 后台是否自动刷新内测巡检证据 | 默认 `1`；随闲鱼助手启动，只运行 `read_only` 审计刷新库存、New-API 启用兑换码和渠道数量，不发送消息、不分配卡密、不改库存 |
| `CC_XIANYU_AUTO_READINESS_AUDIT_INTERVAL_MS` | 后台内测巡检最小间隔 | 默认 `900000`；最小强制 300000ms，避免频繁读取生产接口 |
| `CC_XIANYU_AUTO_READINESS_AUDIT_SCAN_SECONDS` | 后台内测巡检扫描间隔 | 默认 `60` 秒，最小 `30` 秒；只判断是否到期刷新只读证据 |
| `CC_XIANYU_AUTO_STRICT_AUDIT_ENABLED` | 真实发货后 GUI/后台是否自动轮询正式售卖严格门 | 默认 `1`；仅在观察到已自动发货、无补救、等待买家兑换/API/调模型时触发只读严格审计，不发送消息、不分配卡密、不改库存 |
| `CC_XIANYU_AUTO_STRICT_AUDIT_INTERVAL_MS` | GUI/后台自动严格门轮询最小间隔 | 默认 `600000`；最小强制 60000ms，避免频繁远程审计 |
| `CC_XIANYU_AUTO_STRICT_AUDIT_SCAN_SECONDS` | 后台严格门观察扫描间隔 | 默认 `60` 秒，最小 `30` 秒；只扫描是否需要运行只读严格门，不触发发货或库存写入 |
| `CC_XIANYU_AUTO_CONFIRM_SHIPMENT_ENABLED` | 是否启用 OpenClaw 后端 API 确认闲鱼发货 | 默认 `0`；浏览器助手确认发货已可用，后端私有 API 方式仅作为显式开启的补充路径 |
| `CC_XIANYU_OPS_NOTIFY_ENABLED` | 是否启用本机运营状态提醒 | 默认 `1`；随本机闲鱼助手启动，状态变化时弹 macOS 通知；只读，不发货、不分配卡密、不改库存 |
| `CC_XIANYU_OPS_NOTIFY_INTERVAL_MS` | 本机运营提醒最小间隔 | 默认 `120000`；最小强制 30000ms，避免状态短时间抖动时刷屏 |
| `CC_XIANYU_OPS_NOTIFY_SCAN_SECONDS` | 本机运营提醒扫描间隔 | 默认 `30` 秒，最小 `10` 秒；只判断是否需要提醒 |
| `CC_XIANYU_LOW_INVENTORY_THRESHOLD` | 兑换码低库存提醒阈值 | 默认 `2`；未售卡密数量小于等于阈值时提醒补货 |
| `cc_strict_audits` | 本机 SQLite 严格门审计摘要表 | 保存 `ok/exit_code/real_orders/same_order_ready/same_order_matched` 等脱敏证据，供 GUI/后台在重启后恢复最近严格门状态；不保存卡密、Token、API Key 或原始 stdout/stderr；严格门通过后会用订单哈希把 `cc_shipments.buyer_chain_status` 回写为 `verified` |
| `SUB2API_KEY_ALERT_WEBHOOK` | Key 认证/额度异常告警 Webhook | 可选；未配置 Telegram 时可走通用告警 Webhook |
| `SUB2API_GATEWAY_DAILY_SPEND_LIMIT_CENTS` | 上游 Key 默认日消费限额 | 可选；余额站库存可单 Key 覆盖，超过后自动熔断并切备用健康渠道 |
| `SUB2API_GATEWAY_SLOW_LATENCY_MS` | 慢线上游降级阈值 | 默认 `5000`；当余额站当日消费已超过剩余额度且响应慢，会自动下线该 Key |
| `SUB2API_TELEGRAM_BOT_TOKEN` | Telegram Bot Token | 可选；配置后自动发送一次性补号提醒 |
| `SUB2API_TELEGRAM_CHAT_ID` | Telegram 接收群/用户 ID | 与 Bot Token 搭配，用于接收 Key 异常提醒 |
| `SUB2API_PAYMENT_ENABLED` | 是否启用真实支付接口 | 总开关；未启用时仍可人工确认 |
| `SUB2API_WECHAT_PAY_ENABLED` | 是否启用微信 Native 支付 | 需要商户平台、AppID、商户号和 APIv3 配置 |
| `SUB2API_WECHAT_PAY_APPID` | 微信支付 AppID | 由微信支付商户平台绑定的应用提供 |
| `SUB2API_WECHAT_PAY_MCH_ID` | 微信支付商户号 | 微信支付商户平台提供 |
| `SUB2API_WECHAT_PAY_SERIAL_NO` | 微信商户 API 证书序列号 | 用于 APIv3 请求签名 |
| `SUB2API_WECHAT_PAY_PRIVATE_KEY` | 微信商户私钥 PEM | 只放服务器环境变量或安全文件注入 |
| `SUB2API_WECHAT_PAY_PUBLIC_KEY` | 微信支付平台公钥 PEM | 用于下单原始应答和回调验签 |
| `SUB2API_WECHAT_PAY_PLATFORM_SERIAL_NO` | 微信平台证书序列号或支付公钥 ID | 必须与应答头 `Wechatpay-Serial` 精确匹配 |
| `SUB2API_WECHAT_PAY_API_V3_KEY` | 微信支付 APIv3 密钥 | 32 字节，用于回调资源解密 |
| `SUB2API_WECHAT_PAY_NOTIFY_URL` | 微信支付回调 URL | 默认可由公开入口推导为 `/api/frist/payments/wechat/notify` |
| `SUB2API_ALIPAY_ENABLED` | 是否启用支付宝当面付 | 需要支付宝开放平台应用和当面付产品 |
| `SUB2API_ALIPAY_APP_ID` | 支付宝应用 AppID | 支付宝开放平台提供 |
| `SUB2API_ALIPAY_PRIVATE_KEY` | 支付宝应用私钥 PEM | 只放服务器环境变量或安全文件注入 |
| `SUB2API_ALIPAY_PUBLIC_KEY` | 支付宝平台公钥 PEM | 用于下单响应与异步通知验签 |
| `SUB2API_ALIPAY_NOTIFY_URL` | 支付宝回调 URL | 默认可由公开入口推导为 `/api/frist/payments/alipay/notify` |
| `SUB2API_NEWAPI_ENABLED` | 是否启用 JIYU AI 服务端 New-API 业务桥接 | `1` 启用；未启用时继续走本地 JSON 自研逻辑 |
| `SUB2API_REQUIRE_NEWAPI_DATABASE` | 是否把 New-API 数据库作为生产必备持久化层 | 生产强制模式必须为 `1`，用于防止继续把 JSON runtime 当生产数据库 |
| `SUB2API_NEWAPI_BASE_URL` | New-API 内网 API 地址 | Oracle 生产为 `http://127.0.0.1:13000`；Docker/本地开发可用 `http://sub2api.service:3000`，不要暴露公网管理口 |
| `SUB2API_NEWAPI_ACCESS_TOKEN` | New-API 用户 access token | 只放服务器环境变量，禁止写入仓库 |
| `SUB2API_NEWAPI_USER_ID` | access token 所属 New-API 用户 ID | v1 会校验 `New-Api-User` 头 |
| `SUB2API_NEWAPI_DEFAULT_GROUP` | New-API 新建 Token 默认分组 | 默认 `default` |
| `SUB2API_NEWAPI_DEFAULT_TOKEN_QUOTA` | 旧兼容层配置（已停用） | 当前生产不读取该变量；新密钥额度由 Sub2API 管理端和用户余额合同控制。 |
| `SUB2API_NEWAPI_REQUEST_TIMEOUT_MS` | JIYU 调用 New-API 管理接口的响应头超时 | 默认 `15000` 毫秒，下限 1000；超时返回 504，流式网关在收到响应头后继续按流传输 |
| `SUB2API_NEWAPI_GATEWAY_ENABLED` | 是否让 JIYU AI `/v1` 代理 New-API 网关 | `1` 启用；仅作用于 JIYU 3180 桥接面。代理前精确查 bearer，仅允许唯一有效本地用户的完整 active owner，以及 enabled、`unlimited_quota=false`、剩余额度为正的上游 Token；不改变 Apache 主域直连 New-API 的产品拓扑 |
| `SUB2API_NEWAPI_GATEWAY_BASE_URL` | New-API 网关地址 | Oracle 生产为 `http://127.0.0.1:13000/v1`；Docker/本地开发通常为 `http://sub2api.service:3000/v1` |
| `SUB2API_NEWAPI_REDEMPTION_STATUS_SYNC_ENABLED` | 是否自动回写 New-API 原生兑换状态 | 生产为 `1`；服务端按卡密哈希把 New-API 已兑换记录同步回 JIYU 闲鱼履约 |
| `SUB2API_NEWAPI_REDEMPTION_STATUS_SYNC_INTERVAL_MS` | New-API 兑换状态回写间隔 | 默认 `60000` 毫秒；正式售卖期保持开启 |
| `SUB2API_DOCKER_NEWAPI_BASE_URL` | 旧兼容层配置（已停用） | 当前生产不读取该变量。 |
| `SUB2API_DOCKER_NEWAPI_GATEWAY_BASE_URL` | 旧兼容层配置（已停用） | 当前生产不读取该变量。 |
| `MITMDUMP_BIN` | mitmdump 可执行文件 | 可指向 `~/.openclaw/tools/mitmproxy-local-venv/bin/mitmdump` 这类独立工具 venv，避免污染项目虚拟环境 |

---

### 0.2 New-API 同步与代理入口登记

| 类型 | 名称 | 路径 / 命令 | 说明 |
|------|------|-------------|------|
| 上游源码 | `QuantumNous/new-api` | `packages/new-api-upstream` | Git submodule，当前固定 `v1.0.0-rc.4` |
| Compose 镜像 | `calciumion/new-api` | `docker-compose.newapi.yml` | 本地/冷回滚 Compose 固定 `calciumion/new-api:v1.0.0-rc.4`，不使用 `latest`；Oracle 生产为 release ARM64 二进制 systemd，不安装 Docker |
| 同步检查 | `new-api-check` | `make new-api-check` | 检查 GitHub 最新非草稿 release、submodule 指针和 compose 镜像 tag 是否一致 |
| 同步升级 | `new-api-sync` | `make new-api-sync` | 更新 submodule 到最新 release，并同步 compose 镜像 tag |
| 同步脚本 | `sync_new_api_upstream.sh` | `scripts/sync_new_api_upstream.sh` | 支持 `check` / `update`；`check` 发现落后返回非 0，适合 CI/定时任务 |
| 品牌补丁 | `new-api-brand-patch` / `apply_new_api_brand_patch.sh` | `make new-api-brand-patch` | `scripts/patches/new-api-cc-brand.patch` 是 CC中转品牌修改的可维护基线；submodule 保持上游干净状态，升级后先检查兼容，再按需应用补丁 |
| 本机运维 | `sub2api-check` / `jiyu-sub2-replenish` / `jiyu-sub2-replenish-dry-run` | `Makefile` | 分别检查生产脚本、启动本地补号助手和执行不登录上游的解析演练。 |
| New-API 冷回滚同步 | `make new-api-check` / `make new-api-sync` | 人工显式执行 | 自动创建分支的定时 workflow 已随生产切换到 Sub2API 删除；旧底座研究不得自动恢复服务或生产数据库 |
| JIYU AI 网关 | `https://jiyu.245334.xyz/v1` | Sub2API 原生 OpenAI/Claude 兼容网关；用户密钥、端点、计费和用量均由 Sub2API 管理，生产不再运行旧桥接进程。 |
| Chrome 运营书签修复 | `cc_zhongzhuan_chrome_bookmarks.mjs` | `scripts/cc_zhongzhuan_chrome_bookmarks.mjs` | 修复/重建本机 Chrome 各 Profile 的 `CC中转运营` 书签文件夹，只写入 2 个老板可点入口：本机操作台、用户主站；`/ops-links` 保留兼容但不再默认收藏。写入前在 Chrome Profile 目录生成 `.codex-backup-*` 备份；加 `--open-window` 可直接打开 2 个运营入口窗口；2026-07-07 复验 `Default/Profile 1/Profile 2/Profile 3` 均为 2 个入口且 `chromeBookmarks.ok=true` |
| CC中转卖家 Chromium 启动器 | `cc-seller-chrome` / `cc_zhongzhuan_launch_seller_chrome.mjs` | OpenClaw 桌面端“启动并打开运营台”（维护入口：`scripts/cc_zhongzhuan_launch_seller_chrome.mjs`） | 由桌面端点击启动，准备独立卖家 Profile、回环 CDP 和本机操作台/用户主站/闲鱼首页；闲鱼由本机桥接器直接接管，不复制扩展、不读取 `.env`、不写 runtime-config、不复制 Token；遗留 `--copy-token` 参数失败关闭。优先使用可用的隔离 Chromium，否则降级到普通 Google Chrome，不提示下载或手动加载扩展 |
| CC中转卖家本机桥接器 | `cc-seller-bridge` / `cc_zhongzhuan_seller_bridge.mjs` | `make cc-seller-bridge` / `scripts/cc_zhongzhuan_seller_bridge.mjs` | 本机 DevTools 桥接器，读取 18800 队列并注入闲鱼页面执行器，负责付款页发卡、点击发送、确认发货和恢复可售巡检；`--scan-only --require-real-order-id` 会只读捕获闲鱼 `message.headinfo` 真实订单号/商品 ID；`--one-shot-override` 会强制 delivery-only/只跑一次/只允许 1 个闲鱼页，并且优先把已发 `xy_browser_*` 临时单接管为 `xy_oid_*`，不重复发卡；不建议在重复发卡事故未完全验收前恢复 `ai.openclaw.cc-seller-bridge` 常驻 LaunchAgent |
| 生产闭环审计 | `cc_zhongzhuan_readiness_audit.mjs` | `scripts/cc_zhongzhuan_readiness_audit.mjs` | 默认只读检查 Chrome 运营入口、本机闲鱼助手、本机 GUI 状态、本机配置、Oracle 服务/库存/公网安全门；Oracle 合同失败关闭校验 12 个分组/账号/启用渠道、10 条启用文本监控、2 条禁用生图监控、12 条 300±30 秒调度、文本 `+0.05x` 倍率差、生图 `1.0x`/按次 `0.10/0.12` 与渠道A Claude 账号 #2 状态；当前默认与 `--require-real-order` 两种只读巡检均 PASS，可用兑换码 707、自动发货未暂停、历史真实闲鱼订单 1 单、补救队列 0；链动七档商品均为 101 张且销售中，首笔 ¥1 真实购买仍须单独实单确认；不输出 token、卡密或用户 Key |
| 老板统一运营入口 | `/dashboard` / `/api/export-status` / `/api/cc-paid-order-probe` / `/api/cc-operator-mode/one-shot-delivery` / `/api/cc-seller-bridge/page-scan` / `/api/cc-seller-bridge/one-shot-delivery` / `/api/cc-simulation-gate` / `/api/cc-replacement-mode-test-pack` | `http://127.0.0.1:18800/dashboard` | 单一入口展示首页总览、闲鱼售卖、每日简报、系统维护、帮助中心；状态报告导出会脱敏订单、卡密、Token、买家昵称和 API Key；“真实待发货扫单”只读确认闲鱼待发货候选，不发卡、不点击发货；“只放行一次发卡”在暂停状态下只允许当前已付款页发送 1 条卡密；严格模拟门 v2 追踪真实发卡、商品模板/上架、兑换、API Key、CC Switch、模型调用、渠道/服务器状态，但不解锁 `xy_oid_*` 真实订单严格门 |
| 桌面持仓整仓卖出 | `Portfolio → 持仓概览 → 卖出` / `/api/v1/trading/sell` | `apps/openclaw-manager-src/src/components/Portfolio/index.tsx` | 首次点击只打开危险操作复核框，明确展示股票、整仓数量和 MKT 类型；确认后才提交。请求中禁用全部卖出按钮并用同步锁防重复，只有后端明确返回 `success=true` 才提示成功 |
| 本机自动健康与灾备脚本 | `auto_health_check.sh` / `auto_recovery.sh` / `local_backup.sh` / `disaster_recovery.sh` / `manage_backup_launchagent.sh` | `scripts/` | 健康检查验证五个常驻核心服务、Intel/备份定时任务、真实端点和 36 小时备份新鲜度；可选能力按 ENABLED 区分禁用与故障。备份包含恢复所需私有配置但以 0700/0600 留在本机，排除构建缓存/日志；离机只发布 GPG 密文。恢复默认预演，只有显式 `--confirm` 才覆盖文件。 |
| 桌面事务构建安装 | `tauri-build` / `tauri_build_install.sh` | `make tauri-build` / `scripts/tauri_build_install.sh` | 唯一允许的 macOS 打包入口；构建前备份并清理三个历史 App 名称，失败自动恢复，成功只安装 `/Applications/OpenClaw.app`。默认生成全部 bundle；本机内测若 DMG 生成受 macOS 环境阻塞，可显式使用 `OPENCLAW_TAURI_BUNDLES=app make tauri-build` 只构建已签名 App。禁止直接执行 `tauri build` |
| 文档治理检查 | `docs-check` / `check_docs_layout.sh` | `make docs-check` | 检查项目根目录散落文档、`docs/` 子目录、非 `XXX-kebab-case.md` 命名、索引漏登记和索引陈旧引用；已纳入 `make ci-local` |
| 本地完整门禁 | `ci-local` | `make ci-local` | 依次执行依赖锁与安全门、干净安装、Ruff、Python 全量/覆盖率/语法、JIYU AI 全量、桌面安全边界、TypeScript/ESLint/Vite、Tauri Rust 和文档治理；任一失败立即返回非 0。 |
| Oracle 生产运行 | `sub2api.service.service` / `sub2api.service` | Oracle ARM `/opt/sub2api` | New-API v1.0.0-rc.4 ARM64 release 二进制监听 `127.0.0.1:13000`，Apache/Cloudflare 公开 `jiyu.245334.xyz`；JIYU AI 监听 `127.0.0.1:3180`，通过 `jiyu.245334.xyz` 提供兑换码/闲鱼运营台；旧 `jiyu.245334.xyz` 仅跳转到主站 |
| 腾讯冷回滚 | `sub2api.service` | 腾讯云旧实例 | 旧容器和定时器均已停用；恢复前必须重新完成单主写入和真实健康验收。 |

| 环境变量 | 用途 | 备注 |
|----------|------|------|
| `NEWAPI_BASE_URL` | New-API 内网服务地址 | 必须显式配置；未配置时本机兼容代理以 503 失败关闭，不会默认连接 `localhost:3000`。Oracle 生产为 `http://127.0.0.1:13000`。 |
| `NEWAPI_HOST_PORT` | New-API 宿主机回环监听端口 | 本地/冷回滚 Docker 默认 `3000`，共享服务器可改 `13000`；Oracle 生产二进制直接监听 `127.0.0.1:13000` |
| `NEWAPI_ADMIN_TOKEN` | New-API 用户 access token | 通过 New-API 用户资料页或 `/api/user/token` 生成，禁止写入仓库 |
| `NEWAPI_ADMIN_USER_ID` | New-API 当前用户 ID | New-API v1 后台/用户 API 会校验 `New-Api-User` 头，需与 access token 所属用户一致 |
| `NEWAPI_INITIAL_TOKEN` | New-API 容器初始 root token | 只放本机或服务器环境文件，用于首次初始化 |

---

## 1. 注册命令一览（107 个）

命令在 `multi_bot.py` 统一注册；`/cli` 已正式挂到 `CLICommandsMixin`，不再作为预备死代码。

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
| 20 | `/claude code` | `cmd_claude_code` | 仅在固定项目目录打开本机 Claude Code 交互终端；任何 Telegram 提示词参数都会被拒绝 | N |
| 21 | `/cli` | `cmd_cli` | CLI-Anything 工具入口，支持 list/run/install/help/status；已补启动注册回归 | N |

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
| 74 | `/post_social` | `cmd_post_social` | 生成双平台草稿并进入审核队列，不直接外发 | N |
| 75 | `/post_x` | `cmd_post_x` | 进入 X 草稿/审核流程；无一次性最终确认时拒绝发布 | N |
| 76 | `/post_xhs` | `cmd_post_xhs` | 进入小红书草稿/审核流程；无一次性最终确认时拒绝发布 | N |
| 77 | `/xwatch` | `cmd_xwatch` | X 博主监控导入 | N |
| 78 | `/xbrief` | `cmd_xbrief` | X 博主更新摘要 | N |
| 79 | `/xdraft` | `cmd_xdraft` | 生成 X 草稿 | N |
| 80 | `/xpost` | `cmd_xpost` | 仅发布已审核 X 草稿；必须携带短时一次性最终确认 | Y |
| 81 | `/xhsdraft` | `cmd_xhsdraft` | 生成小红书草稿 | N |
| 82 | `/xhspost` | `cmd_xhspost` | 仅发布已审核小红书草稿；必须携带短时一次性最终确认 | Y |
| 83 | `/dualpost` | `cmd_post` | 生成双平台待审草稿（`/post` 的别名），不直接外发 | N |
| 84 | `/publish` | `cmd_publish` | 多媒体直发关闭；现有素材没有可持久化审核快照和一次性令牌，因此不会调用 Sau 发布器 | Y |
| 85 | `/xianyu` | `cmd_xianyu` | 闲鱼 AI 客服控制 (start/stop/status/reload/floor) | N |
| 86 | `/social_calendar` | `cmd_social_calendar` | 内容日历(DB优先+AI生成)，支持 `done N` 标记完成 | N |
| 87 | `/social_report` | `cmd_social_report` | 社媒效果报告 + A/B 测试 | N |
| 87a | `/social_growth_feedback [x|xhs]` | `cmd_social_growth_feedback` | 社媒增长复盘，只读展示插件高信号内容、标签、指标和下一步建议；不触发发布/评论/推广 | N |
| 87b | `/social_growth_drafts [x|xhs]` | `cmd_social_growth_drafts` | 基于增长复盘生成下一批待审热点草稿；只入审核队列，不触发发布/评论/推广 | N |
| 87c | `/social_review_drafts` | `cmd_social_review_drafts` | Telegram 中控查看统一待审草稿队列；只读展示序号/ID/预览 | Y |
| 87d | `/social_review_approve <序号或ID>` | `cmd_social_review_approve` | Telegram 中控确认待审草稿；只改审核状态，不触发发布 | Y |
| 87e | `/social_review_reject <序号或ID>` | `cmd_social_review_reject` | Telegram 中控打回待审草稿；只改审核状态，不删除、不发布 | Y |
| 87f | `/social_review_schedule <序号或ID> [时间]` | `cmd_social_review_schedule` | Telegram 中控把已确认插件草稿加入待发布排程；到点仍需最终确认，不自动外发 | Y |
| 87g | `/social_review_schedule_queue` | `cmd_social_review_schedule_queue` | Telegram 中控查看待发布排程队列；到点只提示最终确认 | Y |
| 87h | `/social_review_final_confirm <序号或ID>` | `cmd_social_review_final_confirm` | Telegram 中控对到点排程做最终确认；只标记可手动发布，不点击平台发布按钮 | Y |
| 88 | `/agent` | `cmd_agent` | 智能 Agent — smolagents ToolCallingAgent 串联行情/搜索/风控等显式只读工具，不执行模型生成的本地代码 | N |
| 89 | `/novel` | `cmd_novel` | AI 小说工坊 — 网文大纲/续写/导出/TTS (inkos+MuMuAINovel) | N |
| 90 | `/ship` | `cmd_ship` | 闲鱼卡券管理 — add/stock/rule/stats/test (auto_shipper) | N |
| 91 | `/xianyu_report` | `cmd_xianyu_report` | 闲鱼收入报表 — 日报/周报/月报 + 爆款排行 + BI三板块(热销排行/高峰时段/转化漏斗) | N |
| 92 | `/xianyu_style` | `cmd_xianyu_style` | 闲鱼 AI 客服回复配置 — 自定义回复风格/FAQ模板/商品规则 (set/faq/rule/show) | N |
| 93 | `/bill` | `cmd_bill` | 生活账单追踪 — 话费/水电费余额检测 + 低余额告警 + 定期提醒 (add/update/list/remove + 中文NLP) | N |
| 94 | `/pricewatch` | `cmd_pricewatch` | 降价监控 — 商品降价提醒 + 每6小时自动检查 + 目标价触发通知 (add/list/remove + 中文NLP) | Y |
| 95 | `/deals` | `cmd_deals` | 折扣搜索/比价查询 (cmd_life_mixin.py) | N |
| 96 | `/intel` | `cmd_intel` | 全球情报速递 — 7大行业+5大地区交互式菜单 + 关键词搜索 (Worldmonitor API) | Y |
| 100 | `/evolution` | `cmd_evolution` | 进化引擎状态 — 查看自动进化提案/能力缺口/审批统计 (cmd_ops_mixin.py) | N |

---

## 2. Callback Button 模式一览

在 `multi_bot.py:398-416` 注册。

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

### 非 Command 消息处理器 (multi_bot.py:418-436)

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
| 社媒增长复盘/运营复盘/看看X运营复盘/小红书运营复盘 | `social_growth_feedback` | `/social_growth_feedback` |
| 根据增长复盘生成下一批草稿/生成X下一批待审热点草稿/反哺草稿 | `social_growth_drafts` | `/social_growth_drafts` |
| 查看待审草稿/待审草稿列表/社媒草稿队列/审核草稿列表 | `social_review_drafts` | `/social_review_drafts` |
| 确认草稿 xxx/通过草稿 xxx/审核通过草稿 xxx | `social_review_approve` | `/social_review_approve` |
| 打回草稿 xxx/拒绝草稿 xxx/驳回草稿 xxx | `social_review_reject` | `/social_review_reject` |
| 排程草稿 xxx 明天8点/定时草稿 xxx 今天20:30 | `social_review_schedule` | `/social_review_schedule` |
| 查看社媒排程/待发布排程/排程队列/社媒排程列表 | `social_review_schedule_queue` | `/social_review_schedule_queue` |
| 最终确认草稿 xxx/最后确认草稿 xxx/确认外发草稿 xxx | `social_review_final_confirm` | `/social_review_final_confirm` |
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
| 230 | `/ibuy` | IBKR 买入（微信端不直接下单，需交易面板人工确认） |
| 231 | `/isell` | IBKR 卖出（微信端不直接下单，需交易面板人工确认） |
| 232 | `/ipositions` | IBKR 持仓 |
| 233 | `/iorders` | IBKR 挂单 |
| 234 | `/iaccount` | IBKR 账户 |
| 235 | `/icancel` | 取消订单（微信端不直接执行，需交易面板人工确认） |

### 300-308: 社媒

| 编号 | 映射命令 | 说明 |
|------|----------|------|
| 300 | `/hot` | 热点发文 |
| 301 | `/post` | 双平台发文（仅生成待审草稿，不自动发布） |
| 302 | `/xpost` | 发 X（仅生成待审草稿，不自动发布） |
| 303 | `/xhspost` | 发小红书（仅生成待审草稿，不自动发布） |
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

### 700-709: 每日简报

平台策略：Telegram 支持点击和斜杠菜单，因此优先使用 BotCommand/Inline 按钮/常驻键盘；数字编号只作为兼容备用。微信不支持 Telegram 式点击命令菜单，因此降级为数字编号，并在每个入口提示“回复数字即可跳转”。

| 编号 | 映射命令 | 说明 |
|------|----------|------|
| 700 | `/start` / `/today` / 每日简报菜单/今日简报/每日简报 | 优先返回最近一次成功简报；没有记录时显示菜单；Telegram 底部快捷键 `🧭 今日简报` 等同 700；微信可直接发“今日简报” |
| 701 | `/status` / 我的订阅/订阅状态/简报状态 | 查看套餐、到期时间、已选内容和推送时间 |
| 702 | `/market` / 市场资金 | 开启 A股资金、国会持仓、机构13F 等市场资金源 |
| 703 | `/ai` / AI科技 | 开启 AI 模型动态和 GitHub Trending |
| 704 | `/weather` / 天气预警 | 开启天气、空气、降雨、温度、湿度、灾害预警 |
| 705 | `/schedule` / 推送时间/设置时间 | 当前生产只支持 Asia/Singapore 08:30；回复 `1` 为每天，回复 `2` 为每周一。不在唯一 LaunchAgent 调度范围内的时间会明确拒绝，不再展示无法履约的选项 |
| 706 | `/track` / 添加追踪/追踪 | 支持 `706 英伟达`、`添加追踪 英伟达`、`追踪 英伟达`、`/track 英伟达`；也支持先发 `706`、`添加追踪` 或 `/track`，下一条直接回复名字完成追踪 |
| 707 | `/help` / 简报帮助 | 返回每日简报菜单和数字命令说明 |
| 708 | `/pause` / 暂停简报 | 将当前订阅者状态标为 paused；查看状态/打开菜单不会自动恢复，重新选择内容才恢复 |
| 709 | `/language zh\|en` / 中文 / English | Telegram 资讯语言切换；只更新 `content_language`，不改变分类、频率、时区、订阅到期或暂停状态 |

当前 Telegram Bot 左侧命令菜单已同步为 11 个点击命令：`/start`、`/today`、`/status`、`/market`、`/ai`、`/weather`、`/schedule`、`/track`、`/pause`、`/language`、`/help`，并注册 default、`zh`、`en` 三个 scope。微信端仍保持 700-708 数字回复与中文快捷词；709 是本轮明确的 Telegram 入口，不伪装成已接通微信。显式“菜单/今日简报”等快捷词会打断 pending 状态，不会被误当作时间或追踪参数。本机处理器同时支持 `/api/v1/wechat/incoming` 和旧路径 `/wechat/incoming`。

---

## 三、依赖清单


> 最后更新: 2026-08-03 | P0 闭环依赖审计：桌面生产与开发依赖、Python JSON 修复库安全下限收口

| 包/区域 | 版本/动作 | 用途 | 说明 |
|---|---|---|---|
| `@modelcontextprotocol/sdk` | `1.30.0`，npm lockfile 固定 | JIYU 生图 stdio MCP | 安装时执行 `npm ci --omit=dev --ignore-scripts`；只暴露单图工具，Key 从环境变量或 macOS 钥匙串读取，不把凭据写入 CC Switch；升级后生产依赖审计为 0 |
| `h2` / `hpack` / `pypdf` | `4.4.1` / `4.2.0` / `6.15.0`，Linux 与 macOS 哈希锁同步 | ClawBot HTTP/2 与 PDF 解析 | 合并 Dependabot 安全更新并补齐 `h2` 必需的 `hpack>=4.2`；`pypdf` 直接依赖下限同步为 `>=6.15.0,<7.0.0`，不改变业务接口 |
| `js-yaml` / `nanoid` | `4.3.1` / `3.3.17` override | OpenClaw Manager 前端构建 | 修复 GitHub 主 CI 新识别的两个高危公告；只提升传递依赖，不升级 Tauri、React 或业务组件 |


## OSS 安全依赖收口 (2026-06-22)

| `layui` | `2.13.8`（vendored 静态资源） | 18800 本机操作台组件层 | 文件存放在 `packages/clawbot/src/xianyu/static/layui/`，由 FastAPI `/static/layui/...` 本地提供；不从 CDN 加载，避免本机 Token 页面依赖外网脚本 |
| 包/区域 | 版本/动作 | 用途 | 说明 |
|---|---|---|---|
| `pytest` | `>=9.0.3,<10.0` | Python 测试框架 | 修复 Dependabot 报告的 tmpdir 处理漏洞 |
| `pytest-asyncio` | `>=1.4.0,<2.0` | Python 异步测试插件 | 配套支持 pytest 9，避免依赖解析冲突 |
| `requests` / `urllib3` | `>=2.33.0,<3` / `>=2.7.0,<3` | Python HTTP 兼容栈 | 修复历史版本组合告警，`pip check` 当前无冲突 |
| `aiohttp` / `fastapi` / `starlette` / `litellm` | 安全下限版本 | 后端 API、网关与 LLM 路由 | 按 2026-07-02 官方/PyPI 安全下限收口，避免解析回退到已知漏洞版本 |
| `crawl4ai` / `browser-use` / `crewai` / `docling` / `textblob` | 默认不安装，隔离可选 | 爬虫、浏览器 Agent、多 Agent、文档理解、英文情感分析 | 默认依赖树存在无修复漏洞或安全版本冲突；项目代码保持 graceful degradation，需要时单独隔离安装并审计 |
| `react-simple-maps` | 已移除 | 桌面端世界地图 | 替换为 `d3-geo` + `topojson-client`，清理旧 d3 漏洞链 |
| `d3-geo` | `^3.1.1` | 地理投影和 SVG path 生成 | `WorldMonitor` 直接渲染本地 TopoJSON |
| `topojson-client` | `^3.1.0` | TopoJSON → GeoJSON | `WorldMonitor` 读取 `countries-110m.json` |
| `postcss` / `nanoid` | `8.5.25` / `3.3.16` | 桌面前端构建 | 修复 source map 路径穿越公告并同步安全的传递依赖 |
| `brace-expansion` / `fast-uri` / `hono` / `ip-address` / `js-yaml` / `minimatch` | `5.0.9` / `4.1.2` / `4.13.0` / `10.4.0` / `4.3.0` / `10.2.6` | 桌面开发与构建工具链 | 固定到当前公告修复版本；全量 `npm audit` 为 0 |
| Tauri 桌面依赖 | Rust Tauri `2.11.5`、`@tauri-apps/api 2.11.1`、`@tauri-apps/cli 2.11.4` / `apps/openclaw-manager-src/src-tauri/Cargo.lock` + `package-lock.json` | 桌面原生层可重复构建 | Rust/JavaScript 必须保持相同主次版本；本地/GitHub CI 使用 `cargo test --locked` 和 `cargo check --locked`，运维合同检查版本与 macOS ad-hoc signing；本机正式打包只走 `make tauri-build` |
| `hono` / `undici` / `markdown-it` / `tar` / `@opentelemetry/sdk-node` | 安全补丁版本 | `packages/openclaw-npm` 上游包 | 修复 Hono、Undici、Markdown、tar、OTel 相关 Dependabot 告警 |
| `@mariozechner/pi-coding-agent` | 已从 `packages/openclaw-npm` 直接依赖移除 | 历史上游 Agent 包 | 源码未直接 import；上游暂无 patched version，移除可降低公开告警面 |

## Chrome 插件资产 (2026-06-24)

| 资产 | 路径 | 用途 | 说明 |
|---|---|---|---|
| Social Pilot Manifest | `packages/openclaw-npm/assets/chrome-extension/manifest.json` | Chrome MV3 插件入口 | 工具栏默认打开 `popup.html`，保留 Browser Relay 权限，新增 X / 小红书 / 闲鱼 host permissions（含 `m.tb.cn/tb.cn` 手机分享短链），并加入 `scripting` 用于当前标签页只读上下文采集 |
| Social Core | `packages/openclaw-npm/assets/chrome-extension/social-core.js` | 插件社媒运营核心配置 | 平台识别（含闲鱼 `m.tb.cn/tb.cn` 短链）、安全默认设置、人设/模型/热点选项、no-code 打法选项、从后端 `strategy_summary` 安全同步合法 `strategyPreset`、自动化/互动等级、API URL 拼接、当前页上下文归一化、MCN 热点选题卡规整、草稿创建 payload、热点草稿 payload、互动信号规整、互动回复草稿 payload、表现快照规整、增长反馈 payload、增长反馈热点加权字段、草稿内容/素材计划规整、网页登录额度 copy-only 提示词任务、填入选择器计划（覆盖 X 嵌套 contenteditable/DraftEditor、小红书 Quill/aria-placeholder、闲鱼 placeholder 聊天编辑器）、页面探测 payload、页面校准上报 payload、安全填入 payload、待发布排程 payload、排程提醒卡片规整、人设审核包规整和任务预览 |
| Popup 驾驶舱 | `packages/openclaw-npm/assets/chrome-extension/popup.html` / `popup.js` | 浏览器主执行入口 | 自动识别当前标签页平台，打开时回拉 OpenEverything 中控 `strategyPreset` 并回写本地安全设置，支持启动/暂停、同步中控、紧急停止、看人设/样稿确认、抓热点并展示 MCN 选题卡、扫当前页并把趋势/标题/正文摘要变成可点击上下文卡片、扫互动并把评论/聊天信号转成待审回复草稿、采表现并把已发布内容指标写入增长反馈池、展示历史高信号选题加权原因、看增长复盘摘要、基于增长复盘生成下一批待审热点草稿、根据当前页或热点生成待审草稿、展示内容结构/封面提示词/图片素材提示词/安全清单的“素材计划”、网页登录额度卡片（复制提示词/打开 Gemini、Grok、ChatGPT 网页）、插件内编辑/确认/打回、加入排程、看排程/到点提醒、最终确认、检测填入点并提示校准是否同步中控、安全填入页面；在闲鱼页额外提供“CC中转发货助手”，可检测当前聊天已付款信号并发送本机待发货卡密；高级设置和 Relay 兼容连接 |
| Options 高级设置 | `packages/openclaw-npm/assets/chrome-extension/options.html` / `options.js` | no-code 运营设置 | 人设标签、主内容模型、生图模型、热点来源、自动化强度、互动强度、本地 API Base URL 和 Relay 兼容配置；打开时读取后端当前打法并提示“已从 OpenEverything 中控同步当前运营打法”；设置区已纳入真实 `<form id="social-settings-form">`，Gateway token 密码框位于 form 内，保存按钮走 `submit` + `preventDefault()`，真实 Chrome 复验无密码字段表单警告，兼容浏览器密码管理器和回车提交体验 |
| Background 桥接 | `packages/openclaw-npm/assets/chrome-extension/background.js` | 后台消息桥 | 保留原 Browser Relay attach/detach，同时处理 `toggleRelayForActiveTab`、`socialStatusFetch`、`socialStatusUpdate`、`socialTrendsFetch`、`socialDraftCreate`、`socialPageContextScan`、`socialTrendDraftCreate`、`socialDraftUpdate`、`socialDraftReview`、`socialReviewPackFetch`、`socialPersonaReview`、`socialDraftSchedule`、`socialScheduleFetch`、`socialDraftFinalConfirm`、`socialDraftAutofill`、`socialPageProbe`、`socialWebModelOpen`、`socialInteractionScan`、`socialPerformanceScan`、`socialPerformanceRecord`、`socialGrowthFeedbackFetch`、`socialGrowthDraftsCreate`、`xianyuDeliveryScan`、`xianyuDeliverySend`，读取/同步插件状态、回写中控 no-code 打法到 Chrome 本地设置、读取热点池、写入待审草稿、加入待发布排程、执行到点最终确认桥接、只打开白名单模型网页，并调用可测试页面执行器完成当前页上下文/热点采集、只读检测、互动扫描、表现采集和只填入不发布；生成当前页待审草稿时通过 `runSocialPageContextScanInPage()` 读取 X 趋势/推文、小红书笔记/评论、闲鱼商品/聊天上下文；闲鱼发货桥接会读取本机 `cc-browser-delivery/next` 并在页面付款信号通过后填入/发送/标记；`xianyuDeliveryWatchSet` 可锁定当前闲鱼聊天标签页做一次性看守，命中付款信号和待发货话术后自动发送并关闭看守；卖家专用运行版可读取 `runtime-config.json` 作为本机 gateway token fallback，避免首次使用反复粘贴；页面探测后会把校准摘要上报 `social/extension/page-probe`；不提供 `socialInteractionSubmit` 自动评论路径，也不提供 `socialPerformanceBoost` 推广/刷量路径 |
| Social Page Runner | `packages/openclaw-npm/assets/chrome-extension/social-page-runner.js` | 页面上下文采集、输入框检测、安全填入、只读互动扫描与表现采集执行器 | 从 `background.js` 抽出的可复用注入函数；`runSocialPageContextScanInPage()` 采集当前页 `selection`、`headings`、`trends`、`bodyText`，覆盖 X trend/tweet、小红书 note/title/content/comment、闲鱼 item/message/chat/desc 等热点与上下文信号；支持 X contenteditable/DraftEditor、小红书标题/正文/Quill 编辑器、闲鱼回复/描述/placeholder/“想跟TA说点什么”聊天编辑器，检测模式和上下文采集均只读，普通草稿填入模式不点击任何发布/发送/评论按钮；互动扫描只读取可见评论/聊天文本并返回候选信号；表现采集只读取已发布内容可见指标，不点击页面控件；`runXianyuDeliveryScanInPage()` / `runXianyuDeliveryFillAndSendInPage()` 是 CC中转已付款发货专用动作，要求页面可见付款信号才会点击“发送” |
| 真实浏览器烟测 | `packages/openclaw-npm/assets/chrome-extension/test/social-browser-smoke.mjs` | Chrome 插件端到端 QA | 使用本机 Google Chrome 模拟 X / 小红书 / 闲鱼三类页面，加载 `social-core.js` 与 `social-page-runner.js` 的真实模块，验证平台识别、当前页上下文采集、输入框探测、安全填入和截图取证；页面内监听 Post / 发布 / 发送按钮点击，任一按钮点击会失败，当前三平台验收均 `ready=true`、`contextReady=true`、`contextSignals>0`、`filled=true`、`buttonClicks=0`，并额外验证 Popup 预览页点击“扫当前页”后 `page-context-panel` 展开、待审草稿编辑器出现，截图 `social-pilot-popup-context-20260624.png` |
| Social App 静态测试 | `apps/openclaw-manager-src/src/components/Social/social-growth-feedback.static.test.mjs` | 桌面中控回归 | 覆盖 Social 页增长复盘卡片、复盘反哺待审草稿按钮、Tauri IPC/API/Rust 命令代理，防止 App 中控与 Chrome 插件复盘断链 |
| 插件单测 | `packages/openclaw-npm/assets/chrome-extension/test/social-core.test.mjs` / `test/social-page-runner.test.mjs` | 行为回归 | 覆盖平台识别、安全默认值、后端 `strategy_summary` 同步到本地合法 no-code 打法且不打开自动化权限、外部动作闸口、平台任务预览、API URL 拼接、当前页上下文规整、MCN 热点选题卡字段、热点草稿 payload、互动信号规整、互动回复草稿 payload、表现快照规整、增长反馈 payload、增长反馈热点加权字段、草稿内容/素材计划规整、网页登录额度 copy-only 提示词、填入选择器计划、真实页面编辑器变体、页面探测 payload、页面校准上报 payload、安全填入 payload、待发布排程 payload、排程提醒卡片规整并保留素材计划、人设审核包规整，以及页面执行器的当前页热点/上下文采集、只读检测、小红书拆分填入/Quill 检测、X compose/DraftEditor 检测且不发布、闲鱼 placeholder 聊天编辑器检测、互动扫描不点击按钮、表现采集不点击按钮；`popup-static.test.mjs` 静态防止按钮绑定函数、消息桥、共享页面上下文采集器、Popup 当前页上下文扫描面板、MCN 热点展示、互动扫描、表现复盘、增长复盘反哺待审草稿、素材计划/网页登录额度展示、中控打法同步缺失、Options 设置页真实表单/密码字段 form 归属/submit 保存逻辑回退，以及三平台真实浏览器烟测脚本缺失 |

## 搬运的高星项目 (38 个, 累计 ~473k Stars)

| 包 | Stars | 用途 | 文件 | 版本 |
|----|-------|------|------|------|
| crawl4ai | 62.4k | 购物比价引擎 | shopping/crawl4ai_engine.py | 默认不安装，隔离可选 |
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
| textblob | 9k | 英文情感分析 | social_tools.py | 默认不安装，词袋降级 |
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
| litellm | 统一 LLM 路由 | >=1.84.0,<2.0.0 |
| mem0ai | AI 记忆层 | >=0.1.30 |
| browser-use | AI 浏览器代理 | 默认不安装，隔离可选 |
| langfuse | LLM 观测平台 | >=2.0.0 |
| crewai | 多 Agent 协作 | 默认不安装，原生投票降级 |
| fastapi | 内控 API | >=0.120.4,<0.140.0 |
| httpx | HTTP 客户端 | ~=0.28.1 |
| yfinance | 美股数据 | >=1.3.0,<2.0.0 |
| akshare | A股数据 | >=1.15.0 |
| ccxt | 加密货币 108+ 交易所 | >=4.4.0 |
| DrissionPage | 反检测浏览器 | >=4.1.0 |
| apscheduler | 定时任务 | >=3.10.0 |
| pandas / numpy / ta | 数据分析+技术指标 | >=2.2,<3 / >=2.0.2,<3 / ~=0.11.0 |
| optuna | 超参数优化 | >=4.0.0 |
| python-dotenv | 环境变量加载 (.env) | ~=1.2.1 |
| beautifulsoup4 | HTML 解析 | ~=4.14.3 |
| requests | HTTP 客户端 (同步) | ~=2.32.0 |
| flask | 部署服务器 (deployer/) | >=3.0.0 |
| aiohttp | 异步 HTTP (evolution/) | >=3.9.0 |
| json-repair | JSON 容错解析（LLM 输出修复；0.60.1 起修复已知资源消耗漏洞） | ~=0.60.1 |
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

### JIYU Sub2 本地补号助手（2026-08-08）

| 路径 | 用途 | 安全合同 |
|---|---|---|
| `packages/clawbot/src/sub2_replenish/core.py` | 分隔行/标签块/JSON 严格解析、邮箱掩码、TOTP 生成和内存任务模型 | `repr=False`、不持久化、不回显密码/TOTP；模糊字段失败关闭 |
| `packages/clawbot/src/sub2_replenish/sub2_client.py` | 读取 macOS 钥匙串并调用 Sub2 原生 OAuth、账号、分组接口 | 固定 `https://jiyu.245334.xyz`，错误不带响应正文，倍率不使用默认值 |
| `packages/clawbot/src/sub2_replenish/runner.py` | 批次渠道、计划自动分组、独立 BrowserContext、`localhost:1455` 回调、串行/暂停/重试/停止 | OTP 只匹配明确 one-time-code/OTP/TOTP/MFA/verification code 语义；CAPTCHA、短信、实体手机号和风控交人工 |
| `packages/clawbot/src/sub2_replenish/app.py` | localhost UI、同源校验、随机 HttpOnly 会话和 CSP | 无 CORS；仅 `127.0.0.1:18796` |
| `packages/clawbot/src/bot/cmd_jiyu_replenish_mixin.py` | Telegram 本机 UI 安全提示、取消等待和一次性保护消费 | 仅 `ALLOWED_USER_IDS` 私聊；不接受来源材料，不回显或解析文本；绝不构造、查看或停止本地 UI 的 `ReplenishRunner` |


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
| 导入方 | `packages/clawbot/scripts/xianyu_login.py` |
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
| 导入方 | `xianyu/xianyu_live.py`, `packages/clawbot/scripts/social_browser_worker.py` |
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
| multi_bot.py | `src/bot/multi_bot.py` | 468 | MultiBot 核心类，组合 11 个 Mixin；已注册社媒增长复盘、待审草稿审核、排程查看与最终确认命令 |
| globals.py | `src/bot/globals.py` | 200 | 全局共享对象实例 + 辅助函数 + UserPreferences (纯配置已提取到 config.py) |
| config.py | `src/bot/config.py` | 107 | 纯配置层: 环境变量 + API Key管理 + SF Key轮转 (HI-359: 打破循环依赖) |
| api_mixin.py | `src/bot/api_mixin.py` | 371 | LLM API 调用 (流式/非流式) |
| rate_limiter.py | `src/bot/rate_limiter.py` | 243 | 消息频率限制 + Token 预算 |
| sau_bridge.py | `src/sau_bridge.py` | 175 | 社媒发布桥接层 — CLI 调用 social-auto-upload (抖音/B站/小红书/快手) |
| x_auto_morning_post.py | `packages/clawbot/scripts/x_auto_morning_post.py` | 121 | X 自动运营草稿入口 — 构建/列出待审核内容；`--publish`、`--publish-next` 和 LaunchAgent 均拒绝外发，真实发布只能走 App/Telegram 最终确认 |
| message_mixin.py | `src/bot/message_mixin.py` | 1128 | 消息处理 + 流式输出 + 链式工作流 (从1914行拆分) |
| chinese_nlp_mixin.py | `src/bot/chinese_nlp_mixin.py` | 790 | 中文NLP命令匹配(模糊容错) + ticker映射 + 噪音清洗 + "你是不是想说"建议；含社媒待审草稿查看/确认/打回/排程/排程队列/最终确认自然语言路由 |
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
| social_scheduler.py | `src/social_scheduler.py` | 542+ | APScheduler 社交自动驾驶；只生成/排程待审草稿，夜间直发分支已移除，最终发布必须走一次性确认门 |
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
| task_graph.py | `src/core/task_graph.py` | 374+ | ✅ DAG任务图: 深拷贝输入/上游快照，顶层及 `data/result/details` 业务失败识别，缺失依赖/备选在执行前拒绝，上游失败阻断，fallback 仅主路径失败后激活并正确收口 |
| executor.py | `src/core/executor.py` | 542 | ✅ 统一执行器: API→浏览器→语音→Composio→Skyvern→人工 6条路径 + 平台熔断器 |
| event_bus.py | `src/core/event_bus.py` | 346 | ✅ 事件总线: 发布/订阅 + 通配符匹配 + 优先级排序 + 异常隔离 + JSONL审计日志 + 线程安全单例 |
| cost_control.py | `src/core/cost_control.py` | 247 | ✅ 成本控制: 模型定价表(8模型) + 日预算检查 + 80%阈值告警 + 成本感知模型路由 + 周报 |
| self_heal.py | `src/core/self_heal.py` | 656 | ✅ 自愈引擎6步: 错误分类→已知方案(含tenacity重试)→记忆检索→Web搜索(Jina/Tavily)→替代方案→通知用户 + 熔断器(同一错误3次5分钟冷却) |
| synergy_pipelines.py | `src/core/synergy_pipelines.py` | 550 | 跨模块协同管道: 交易→社媒/社交→投资/进化广播/风控过滤/新闻情感→风控(4h定时)/盈利庆祝帖 |
| security.py | `src/core/security.py` | 349 | ✅ 安全防护层: 输入消毒(sanitize_input) + PIN(PBKDF2+盐+频率限制) + 审计日志(JSONL) + 权限三级分控(auto/confirm/always_human) + XSS/SQL注入/路径遍历/命令注入防护 |
| **核心工具 (src/ 根级)** | | | |
| utils.py | `src/utils.py` | 101 | 共享工具函数 (时间/环境变量/样板代码消除) |
| cross_process_lock.py | `src/cross_process_lock.py` | 125 | 跨进程文件锁与原子状态更新基础设施，供交易预算、订单 claim、成交对账和社媒发布门复用；锁超时 fail-closed |
| scheduler.py | `src/scheduler.py` | 186 | 定时任务调度器 (早报推送/提醒, 美东时间) |
| pipeline_helper.py | `src/pipeline_helper.py` | 130 | 交易管道桥接 (dict→TradeProposal + ATR 止损止盈) |
| agent_tools.py | `src/agent_tools.py` | 400 | 自主 Agent 工具集（smolagents `ToolCallingAgent`，仅串联显式只读工具，不启用本地代码执行器） |
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
| drafts.py | `src/execution/social/drafts.py` | 293+ | 社媒草稿持久化、去重和审核状态；发布只消费 `publish_gate` 签发的一次性确认，worker 失败向调用方传播 |
| publish_gate.py | `src/execution/social/publish_gate.py` | 285 | 社媒发布授权门：审核内容哈希、10 分钟一次性 Token、编辑失效、原子消费和跨线程/进程文件锁；`publishing/published` 禁止修改，状态冲突追加 `publish_outcomes` 对账审计 |
| worker_bridge.py | `src/execution/social/worker_bridge.py` | 187 | 社媒浏览器 Worker 桥接 (独立于 ExecutionHub 调用) |
| persona_review.py | `src/execution/social/persona_review.py` | 124 | 社媒人设确认 — 热点抽象号提案、样稿、确认/打回状态持久化；确认人设不触发发布 |
| x_auto_ops.py | `src/execution/social/x_auto_ops.py` | 1891 | X / 小红书热点运营闭环 — 中英文热点聚合（微博/百度/知乎/B站/Google News/HN）、热点评分、抽象短推、小红书笔记草稿、语言配额、旧队列替换、安全过滤、审核闸口、失败重试和 6 时段排程配置 |
| **工具 (src/tools/)** | | | |
| docling_service.py | `src/tools/docling_service.py` | 217 | 文档理解 (PDF/DOCX/PPTX→Markdown, Docling 56.3k⭐ 搬运) |
| tavily_search.py | `src/tools/tavily_search.py` | 206 | 智能搜索 (Tavily SDK — QnA/RAG 上下文/深度研究) |
| vision.py | `src/tools/vision.py` | 65 | 图片理解 (LiteLLM Vision 多模型, 零新依赖) |
| code_tool.py | `src/tools/code_tool.py` | 300+ | ✅ Python 仅执行 RestrictedPython 受限字节码并使用子进程资源限制/环境清洗；禁用 import/open，Node.js 与 Shell 代码执行 fail-closed |
| bash_tool.py | `src/tools/bash_tool.py` | 277 | ✅ 只读命令白名单 + `shell=False` + 项目内路径限制 + 固定系统 PATH；Git 整体禁用，危险或难安全解析的命令/参数拒绝 |
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
| xianyu_context.py | `src/xianyu/xianyu_context.py` | 825 | 闲鱼对话上下文管理 (SQLite 持久化/历史记录/CC中转发货补救队列/商品套餐映射, @contextmanager, 利润核算含佣金, 时区统一) |
| cc_operator_state.py | `src/xianyu/cc_operator_state.py` | 82 | CC中转本机操作台状态文件；保存暂停/恢复自动发货开关，不保存卡密、Token、Cookie 或买家信息 |
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
| rpc.py | `src/api/rpc.py` | 3798 | ✅ RPC 远程调用接口: _safe_error 脱敏(隐藏路径+截断) + Tauri 桌面端通信 + freqtrade RPC 模式(System/Trading/Social/Memory/Pool/Shopping)；含 `social/ops-workspace` 聚合 X / 小红书 / 闲鱼统一浏览器运营工作台并同步增长复盘摘要，并接入 `social/persona-review` 人设确认流、`social/review-pack` 人设与内容审核包、`social/browser-control` 安全浏览器控制、`social/extension/status` Chrome 插件状态同步、`social/extension/page-probe` 页面校准摘要、`social/extension/trends` MCN 热点选题卡、`social/extension/drafts` 当前页生成待审草稿与平台化内容/图片素材计划、插件草稿排程队列、`POST /social/extension/performance` 表现复盘记录、增长反馈反哺 `GET /social/extension/trends` 热点排序、`GET /social/extension/growth-feedback` 增长复盘摘要、`POST /social/extension/growth-drafts` 批量生成待审热点草稿；`growth_draft_action` 支持有高信号时复用增长反馈、无样本时冷启动热点池，`GET /social/extension/schedule` 排程提醒读取并保留素材计划、真实样稿、平台下一步、增长复盘、复盘反哺待审草稿动作和审核锁状态 |

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
| cmd_social_mixin.py | `src/bot/cmd_social_mixin.py` | 1651 | 社媒命令 (发帖/日历/草稿)；含 `/social_strategy` no-code 运营打法查询/切换、增长复盘、增长反哺待审草稿、Telegram 待审草稿查看/确认/打回/排程/排程队列/最终确认中控，默认不自动外发 |
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
| position_monitor.py | `src/position_monitor.py` | ~850 | 持仓实时监控；失败/取消/零成交不删除持仓，未决退出防重复下单并按订单 ID、累计成交量和加权价格对账 | 自研 |
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
| x_auto_ops.py | `src/execution/social/x_auto_ops.py` | 1891 | X / 小红书自动运营 — 中文/英文热点种子、热点评分、抽象好玩推文、小红书笔记草稿、语言配额、YouTube/B站低优先级补位、旧污染草稿过滤、去重状态、审核状态和 6 时段 launchd 排程 |

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
| xianyu_live.py | `src/xianyu/xianyu_live.py` | 1853 | 闲鱼实时客服 — WebSocket 长连接/自动回复/CC中转已付款自动发货、已付款/待发货状态变体与订单结构化字段位置识别、未付款/退款/普通聊天误发保护、商品套餐映射、订单自带商品 ID 优先路由、URL 参数真实订单号识别、稳定 `orderId` 幂等、发送失败补救记录和本机暂停开关 |
| xianyu_agent.py | `src/xianyu/xianyu_agent.py` | 497 | 闲鱼 AI Agent — 多轮对话/砍价/推荐 |
| xianyu_admin.py | `src/xianyu/xianyu_admin.py` | 3002 | 闲鱼管理后台 — Apple 风格 CC中转状态中心与操作台、商品/订单/统计/CC中转发货补救队列/已付款漏单兜底发货/商品套餐映射/完整闲鱼分享文本规整/暂停恢复自动发货/自动化运营水位/商品模板/一键闭环审计/CC Switch 导入入口上架锁/后台严格门观察/严格门摘要恢复与买家闭环进度恢复；桌面端通过 `/api/session/desktop-launch` 换取一次性本机启动 URL，消费后进入 `/dashboard`，不回显 API Token |
| cc_operator_state.py | `src/xianyu/cc_operator_state.py` | 82 | CC中转本机操作台状态文件 — 保存暂停/恢复自动发货开关，不保存卡密、Token、Cookie 或买家信息 |
| goofish_monitor.py | `src/xianyu/goofish_monitor.py` | 336 | 闲鱼监控 — 竞品价格/销量追踪 |

#### API 层 (src/api/)

| 模块 | 路径 | 行数 | 说明 |
|------|------|------|------|
| server.py | `src/api/server.py` | 122 | FastAPI 服务器 — 应用工厂/中间件/生命周期 |
| routers/evolution.py | `src/api/routers/evolution.py` | 189 | 进化端点 — 自我进化/指标/报告 |
| routers/social.py | `src/api/routers/social.py` | 588+ | 社媒端点 — 研究、草稿、审核、排程和分析；正文直发关闭。发布必须先审核草稿，再调用 final-confirm 取得短时一次性 Token，最后用同一 `draft_id + confirmation_token` 发布；内容变化或重复消费均拒绝 |
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
| telegram_gateway.py | `src/gateway/telegram_gateway.py` | 528 | OMEGA 网关 Bot — 统一入口/路由分发到 7 Bot；管理员白名单为空时 fail-closed |
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
| proactive_periodic.py | `src/core/proactive_periodic.py` | 241 | 主动引擎定时检查 — 每 30 分钟收集系统上下文 (持仓/闲鱼/交易/提醒/风控) 评估是否推送 |

**依赖关系:** `proactive_engine.py` → `proactive_models.py` + `proactive_notify.py` + `proactive_listeners.py` + `proactive_periodic.py`

#### 异步所有权边界 (2026-08-04)

| 模块 | 路径 | 行数 | 说明 |
|------|------|------|------|
| loop_owner.py | `src/core/loop_owner.py` | 348 | 单事件循环所有者 — 绑定主循环、跨线程提交协程、阻断停止/旧循环关闭竞态并在 loop.close 前回收本循环已启动任务 |

**依赖关系:** `multi_main.py` 绑定所有者循环；Brain、EventBus、券商、闲鱼、WebSocket、CLI 与社媒自动化通过 `loop_owner.py` 跨线程调用。

#### 进化引擎 (src/evolution/)

| 模块 | 路径 | 行数 | 说明 |
|------|------|------|------|
| engine.py | `src/evolution/engine.py` | 761 | 自主进化核心 — GitHub Trending 扫描 + LLM 价值评估 + 集成提案生成 + 低风险自动/高风险审批 + 历史记录 |
| github_trending.py | `src/evolution/github_trending.py` | 322 | GitHub Trending 采集器 — 爬取 trending 页面 (无 Token) + Search API 快速增长仓库查询 + README 获取 |

**依赖关系:** `evolution/engine.py` → `evolution/github_trending.py` + `litellm_router.py` + `utils.py`

#### 闲鱼登录入口

旧 QR API 路由、桌面封装、`qr_login.py` 与 Telegram QR 通知链已移除。当前唯一登录入口是 OpenClaw 桌面端的“启动并打开运营台”按钮；它会打开隔离卖家 Chromium，资产所有者本人在其中扫码，随后由本机桥接器通过回环 CDP 接管。`xianyu_live` 的正常浏览器登录、CookieCloud 与运行态 Cookie 读取保持不变。

#### cmd_basic 子模块展开 (从 cmd_basic_mixin.py 拆分)

> 原有包级条目 (Section 0.4) 仅列名称，以下为各子模块的独立路径注册。

| 模块 | 路径 | 行数 | 说明 |
|------|------|------|------|
| help_mixin.py | `src/bot/cmd_basic/help_mixin.py` | 350 | 帮助菜单 — /help 命令 + help 回调 + 老用户 /start 欢迎（向导逻辑已移至 onboarding_mixin）；社媒分组已补待审草稿审核/排程/最终确认命令 |
| onboarding_mixin.py | `src/bot/cmd_basic/onboarding_mixin.py` | 258 | 新用户引导向导 — ConversationHandler 3步交互式引导（选兴趣→选风格→个性化推荐） |
| status_mixin.py | `src/bot/cmd_basic/status_mixin.py` | 237 | 状态查询 — /status, /metrics, /model, /pool, /keyhealth 系统信息 |
| tools_mixin.py | `src/bot/cmd_basic/tools_mixin.py` | 409 | 工具命令 — /draw、/news、/qr、/tts、只读 /agent、固定无参 /claude code 与鉴权后的 inline query |
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

### Intel Brief 新增模块（2026-07-06）

| 模块 | 路径 | 说明 |
|------|------|------|
| Intel Brief schema | `packages/clawbot/src/intel/db/intel_brief_schema.sql` | 独立 SQLite schema；开放姓名追踪使用 `tracking_targets` / `tracking_subscriptions` / `tracking_audit_log`；含 `content_moderation_log` 与 `source_health`。 |
| Intel DB store | `packages/clawbot/src/intel/db/store.py` | 初始化 Intel Brief DB；同名追踪目标复用；记录用户追踪请求审计日志。 |
| Content moderation | `packages/clawbot/src/intel/quality/content_moderation.py` | 推送前内容过滤入口；关键词预过滤、可注入 LLM/规则二次判断、占位过滤、SQLite 日志。 |
| Congress trading | `packages/clawbot/src/intel/sources/congress_trading.py` | Senate raw GitHub fallback 解析与拉取；MVP 先用 Senate 数据，House 数据源继续迭代。 |
| Runtime policy | `packages/clawbot/src/intel/runtime_policy.py` | 多服务器运行节点偏好；国内源优先国内 worker，海外源走海外 worker；微博/小红书无人值守优先登录策略。 |
| Intel worker probe | `packages/clawbot/scripts/intel_worker_probe.py` | Phase B worker/source 验证证据 JSON 脚手架；不连接服务器、不读取密钥，只统一证据字段。 |

### Intel Brief 测试注册（2026-07-06）

| 测试文件 | 被测模块 | 覆盖类型 |
|----------|----------|----------|
| `test_intel_schema_and_tracking.py` | `src/intel/db/*` | Schema 表结构、开放姓名追踪复用、审计日志 |
| `test_intel_content_moderation.py` | `src/intel/quality/content_moderation.py` | 关键词预过滤、分类器过滤、占位替换、过滤日志 |
| `test_intel_congress_trading.py` | `src/intel/sources/congress_trading.py` | Senate JSON 解析、raw GitHub fetch 注入 |
| `test_intel_runtime_policy.py` | `src/intel/runtime_policy.py` | 国内/海外/controller 路由策略、微博/小红书无人值守优先登录策略 |
| `test_intel_worker_probe.py` | `packages/clawbot/scripts/intel_worker_probe.py` | Phase B 证据结构、国内/海外路由和 JSON 落盘 |

### Intel Brief Phase C/D 支架注册（2026-07-06）

| 模块 | 路径 | 说明 |
|------|------|------|
| Intel source adapter base | `packages/clawbot/src/intel/sources/base.py` | 统一 `IntelSourceResult` / `IntelSourceAdapter` 契约，后续所有真实数据源必须返回该结构并携带 evidence_path。 |
| Intel execution scene | `packages/clawbot/src/execution/intel_brief.py` | 独立 Intel Brief 执行场景入口；当前仅 `plan_only` 派发，不远程执行、不注册生产调度。 |

| 测试文件 | 被测模块 | 覆盖类型 |
|----------|----------|----------|
| `test_intel_source_adapter_base.py` | `src/intel/sources/base.py`, `src/intel/sources/congress_trading.py` | Source Adapter 契约、Senate adapter 结果封装 |
| `test_intel_scheduler_dispatch.py` | `src/execution/intel_brief.py` | 国内/海外/controller 派发计划、worker_counts 汇总 |

### Intel Brief Worker Contract 与 Source Health 注册（2026-07-06）

| 模块 | 路径 | 说明 |
|------|------|------|
| Intel worker contract | `packages/clawbot/src/intel/worker_contract.py` | Controller/worker JSON-safe 契约；只传路由与执行意图，不传 token/cookie/password/private key。 |
| Intel source health helpers | `packages/clawbot/src/intel/db/store.py` | 新增 `record_source_health` / `get_source_health`；success 清零连续失败，failure 累加并保留最近失败原因。 |

| 测试文件 | 被测模块 | 覆盖类型 |
|----------|----------|----------|
| `test_intel_worker_contract.py` | `src/intel/worker_contract.py` | Worker request/response 序列化、metadata 敏感键拒绝、source result 包装 |
| `test_intel_schema_and_tracking.py` | `src/intel/db/store.py` | 追加 source_health success/failure 写入与持久化读取 |

### Intel Brief Worker Runner / Adapter Registry 注册（2026-07-06）

| 模块 | 路径 | 说明 |
|------|------|------|
| Intel worker runner | `packages/clawbot/src/intel/worker_runner.py` | Worker 本地执行器；接收 JSON-safe request，调用 adapter，返回 JSON-safe response，并可写 source_health。 |
| Intel adapter registry | `packages/clawbot/src/intel/sources/registry.py` | 默认 adapter 注册表；当前只注册已有 Phase B 真实证据的 `senate_trading`。 |

| 测试文件 | 被测模块 | 覆盖类型 |
|----------|----------|----------|
| `test_intel_worker_runner.py` | `src/intel/worker_runner.py` | 成功执行、adapter 异常、未知 source、JSON round-trip、source_health 写入 |
| `test_intel_source_adapter_base.py` | `src/intel/sources/registry.py` | 默认 registry 只注册已验证 Senate adapter |

### Intel Brief Worker CLI 注册（2026-07-06）

| 脚本 | 路径 | 说明 |
|------|------|------|
| Intel worker CLI | `packages/clawbot/scripts/intel_worker_cli.py` | 目标 worker 执行入口；stdin/文件读取 request JSON，调用默认 adapter registry，stdout 输出 response JSON，可选写 source_health DB。 |

| 测试文件 | 被测模块 | 覆盖类型 |
|----------|----------|----------|
| `test_intel_worker_cli.py` | `packages/clawbot/scripts/intel_worker_cli.py` | stdin/file 输入、DB 写入、未知源非零返回、坏 JSON parse error |

### Intel Brief Worker Bundle 注册（2026-07-06）

| 脚本 | 路径 | 说明 |
|------|------|------|
| Intel worker bundle builder | `packages/clawbot/scripts/intel_worker_bundle.py` | 构建最小 worker CLI bundle；只包含 Intel runtime/schema，不包含密钥、服务文件或生产配置；manifest 记录 cleanup 回滚命令。 |

| 测试文件 | 被测模块 | 覆盖类型 |
|----------|----------|----------|
| `test_intel_worker_bundle.py` | `packages/clawbot/scripts/intel_worker_bundle.py` | Bundle 文件清单、manifest、独立目录 CLI smoke |

### Intel Brief AKShare Adapter 注册（2026-07-06/UTC 2026-07-07）

| 模块 | 路径 | 说明 |
|------|------|------|
| AKShare 龙虎榜 adapter | `packages/clawbot/src/intel/sources/astock_flow.py` | 调用 `akshare.stock_lhb_detail_em()` 并归一化为 IntelSourceResult；目标 domestic worker 需提供 akshare 运行环境。 |

| 测试文件 | 被测模块 | 覆盖类型 |
|----------|----------|----------|
| `test_intel_astock_flow.py` | `src/intel/sources/astock_flow.py` | 中文/英文列名归一化、adapter 返回 domestic result |
| `test_intel_python310_compat.py` | `src/intel/*`, `scripts/intel_worker_*.py` | 防止 worker bundle runtime 使用 Python 3.11+ `datetime.UTC` |

### Intel Brief Remote Runner 注册（2026-07-07）

| 脚本 | 路径 | 说明 |
|------|------|------|
| Intel remote worker runner | `packages/clawbot/scripts/intel_worker_remote_run.py` | 构建最小 bundle，通过 SSH 临时 staging 到目标 worker，执行 one-shot worker CLI，查询 source_health，cleanup 并写 evidence。 |

| 测试文件 | 被测模块 | 覆盖类型 |
|----------|----------|----------|
| `test_intel_worker_remote_runner.py` | `packages/clawbot/scripts/intel_worker_remote_run.py` | 命令编排、成功/失败 evidence、cleanup 语义、直接脚本 help |

### Intel Brief Collect-once 注册（2026-07-07）

| 脚本 | 路径 | 说明 |
|------|------|------|
| Intel collect once | `packages/clawbot/scripts/intel_collect_once.py` | Controller 一次性多源采集编排；按 source 调用 remote runner，聚合 child evidence；不注册 scheduler。 |

| 测试文件 | 被测模块 | 覆盖类型 |
|----------|----------|----------|
| `test_intel_collect_once.py` | `packages/clawbot/scripts/intel_collect_once.py` | 默认 worker profiles、聚合成功、未知源失败不远程执行 |

### Intel Brief Dry-run Brief Builder 注册（2026-07-07）

| 模块/脚本 | 路径 | 说明 |
|---|---|---|
| Intel brief builder | `packages/clawbot/src/intel/brief_builder.py` | 从 collect-once evidence 生成规范化、去重、内容过滤后的 dry-run Markdown/JSON；不访问外部源、不调用 LLM、不推送 Telegram。 |
| Intel brief dry-run CLI | `packages/clawbot/scripts/intel_brief_dry_run.py` | Controller 本地 dry-run 入口；参数为 collect evidence、Markdown 输出、JSON 输出和 stamp。 |

| 测试文件 | 被测模块 | 覆盖类型 |
|---|---|---|
| `test_intel_brief_dry_run.py` | `src/intel/brief_builder.py`, `packages/clawbot/scripts/intel_brief_dry_run.py` | 数据源展示归一化、stable-key 去重、内容过滤防泄漏、Markdown/JSON evidence、CLI 输出 |

### Intel Brief LLM Summary 注册（2026-07-07）

| 模块/脚本/配置 | 路径 | 说明 |
|---|---|---|
| Intel Brief LLM profile | `packages/clawbot/config/llm_routing.json` | `routing_profiles.intel_brief`；生产 family 偏好链与 dry-run family 分离。 |
| Intel local dry-run family | `packages/clawbot/config/llm_routing.json` | `intel_local` → Ollama `qwen2.5:1.5b`；`fallback_chains.intel_local=[]`，避免本地取证误触发外部 provider。 |
| Routing profile helper | `packages/clawbot/src/llm_routing_config.py` | `get_routing_profile()` 读取业务专属 LLM profile。 |
| Intel LLM summary builder | `packages/clawbot/src/intel/llm_summary.py` | 从 dry-run evidence 构造 prompt，调用 LiteLLM routing，写出 LLM summary evidence；失败时保留 fallback evidence。 |
| Intel LLM summary CLI | `packages/clawbot/scripts/intel_llm_summary_dry_run.py` | 支持 `--dry-run-json`、`--family`、`--max-tokens`，用于受控摘要 dry-run。 |

| 测试文件 | 被测模块 | 覆盖类型 |
|---|---|---|
| `test_intel_llm_summary.py` | `src/intel/llm_summary.py`, `src/llm_routing_config.py`, `packages/clawbot/scripts/intel_llm_summary_dry_run.py` | profile、family选择、prompt、LLM调用注入、fallback、CLI与输出 evidence |

## CC中转闲鱼自动发货补充登记

- `XianyuLive._decode_sync_message_payload(raw)`：兼容闲鱼 WebSocket 加密 payload 与明文 JSON 系统卡片。
- `XianyuLive._extract_order_buyer_id(message)`：从结构化订单消息或聊天系统卡片 meta 中提取买家 ID；缺失时阻止自动发货。
- `XianyuLive._looks_like_xianyu_paid_system_title(value)`：仅识别“我已付款，等待你发货/待发货/提醒发货”这类闲鱼系统卡片标题，普通聊天内容不触发。
- `GET /api/cc-browser-delivery/next`：Chrome 发货助手读取已分配待发送话术；返回值属于本机受 token 保护接口，禁止对外公开。
- `POST /api/cc-shipments/{shipment_id}/mark-sent`：浏览器助手或老板确认话术已发后标记本机履约记录为 `message_sent`。
- `POST /api/cc-shipments/{shipment_id}/browser-send`：保留给能提供真实 buyer_id/chat_id 的浏览器兜底发送；不得用昵称猜测 buyer_id。

### Intel Brief Delivery Sandbox 注册（2026-07-07）

| 模块/脚本 | 路径 | 说明 |
|---|---|---|
| Intel delivery sandbox | `packages/clawbot/src/intel/delivery.py` | Sandbox subscriber/plan/subscription/source_preferences、fake Telegram sender、delivery_log 写入与 delivery evidence。 |
| Intel delivery sandbox CLI | `packages/clawbot/scripts/intel_delivery_sandbox.py` | 从 LLM summary evidence 运行 fake Telegram 投递沙盒；输出 DB/outbox/evidence。 |

| 测试文件 | 被测模块 | 覆盖类型 |
|---|---|---|
| `test_intel_delivery_sandbox.py` | `src/intel/delivery.py`, `packages/clawbot/scripts/intel_delivery_sandbox.py` | sandbox 订阅者、消息渲染、fake sender JSONL、delivery_log、evidence rollback、CLI |

### Intel Brief Scheduled Sandbox 注册（2026-07-07）

| 模块/脚本 | 路径 | 说明 |
|---|---|---|
| Intel scheduled pipeline | `packages/clawbot/src/intel/scheduled_pipeline.py` | Controller 本地 scheduled rehearsal；判断计划时间并串联 brief dry-run、LLM summary dry-run、delivery sandbox。 |
| Intel scheduled sandbox CLI | `packages/clawbot/scripts/intel_scheduled_sandbox.py` | 从既有 collect evidence 运行 scheduled sandbox；输出统一 scheduled evidence；不注册 cron/systemd。 |

| 测试文件 | 被测模块 | 覆盖类型 |
|---|---|---|
| `test_intel_scheduled_pipeline.py` | `src/intel/scheduled_pipeline.py`, `packages/clawbot/scripts/intel_scheduled_sandbox.py` | 到点判断、同日去重、skip evidence、artifact 串联、fallback-only LLM、fake Telegram network_calls=0、CLI |

### Intel Brief Scheduler Gate 注册（2026-07-07）

| 模块/脚本/配置 | 路径 | 说明 |
|---|---|---|
| Intel scheduler gate | `packages/clawbot/src/execution/intel_brief.py` | `build_intel_brief_scheduler_gate()`；读取 Intel Brief 调度环境变量并输出脱敏 gate decision。 |
| ExecutionScheduler Intel hook | `packages/clawbot/src/execution/scheduler.py` | `_run_intel_brief()`；默认 sandbox-only，生产硬闸门未满足时不执行。 |
| Intel scheduler gate probe CLI | `packages/clawbot/scripts/intel_scheduler_gate_probe.py` | 只读输出 gate evidence；不注册 scheduler、不调用 Telegram、不抓外部源。 |
| Intel Brief env example | `packages/clawbot/config/.env.example` | `INTEL_BRIEF_ENABLED` / `INTEL_BRIEF_TIME` / `INTEL_BRIEF_MODE` 等独立调度变量；默认关闭。 |
| Control panel task row | `packages/clawbot/src/api/routers/controls.py` | 静态任务表新增 `intel_brief`，默认 disabled，仅展示。 |

| 测试文件 | 被测模块 | 覆盖类型 |
|---|---|---|
| `test_intel_scheduler_gate.py` | `src/execution/intel_brief.py`, `src/execution/scheduler.py`, `packages/clawbot/scripts/intel_scheduler_gate_probe.py` | 默认关闭、生产硬闸门、sandbox ready、同日去重、CLI 脱敏、async scheduler 默认 runner |

### Intel Brief Telegram Sandbox Sender 注册（2026-07-07）

| 模块/脚本/配置 | 路径 | 说明 |
|---|---|---|
| Telegram delivery contract | `packages/clawbot/src/intel/telegram_delivery.py` | Telegram sandbox gate、Bot API sender 合同、注入 transport、evidence probe。 |
| Telegram sandbox probe CLI | `packages/clawbot/scripts/intel_telegram_sandbox_probe.py` | 默认 gate-only；真实网络需要 `--allow-real-network` 和完整 gate。 |
| Telegram sandbox env ack | `packages/clawbot/config/.env.example` | `INTEL_BRIEF_TELEGRAM_SANDBOX_SEND_ACK`；默认空，防误发。 |

| 测试文件 | 被测模块 | 覆盖类型 |
|---|---|---|
| `test_intel_telegram_delivery.py` | `src/intel/telegram_delivery.py`, `packages/clawbot/scripts/intel_telegram_sandbox_probe.py` | token/chat 脱敏、缺凭证阻断、注入 transport 合同、probe evidence、CLI blocked evidence |

### Intel Brief Telegram Summary Probe 注册（2026-07-07）

| 模块/脚本 | 路径 | 说明 |
|---|---|---|
| Telegram summary delivery probe | `packages/clawbot/src/intel/telegram_delivery.py` | `build_telegram_summary_delivery_probe()`；从真实 summary evidence 渲染 Telegram message 并走 sandbox gate/transport。 |
| Telegram summary probe CLI | `packages/clawbot/scripts/intel_telegram_summary_probe.py` | 输入 summary evidence，输出 Telegram delivery probe evidence；默认不真实联网。 |

| 测试文件 | 被测模块 | 覆盖类型 |
|---|---|---|
| `test_intel_telegram_delivery.py` | `src/intel/telegram_delivery.py`, `packages/clawbot/scripts/intel_telegram_summary_probe.py` | summary evidence 渲染、gate blocked、注入 transport、CLI evidence |


### Intel Brief Production Readiness 注册（2026-07-07）

| 模块/脚本 | 路径 | 说明 |
|---|---|---|
| Intel production readiness | `packages/clawbot/src/intel/production_readiness.py` | 只读聚合 production readiness：collect evidence、summary evidence、Telegram sandbox gate、scheduler production gate、worker placement。 |
| Intel production readiness CLI | `packages/clawbot/scripts/intel_production_readiness_audit.py` | 写 readiness evidence；blocked 退出码为 2；不联网、不部署、不写生产 DB。 |

| 测试文件 | 被测模块 | 覆盖类型 |
|---|---|---|
| `test_intel_production_readiness.py` | `src/intel/production_readiness.py`, `packages/clawbot/scripts/intel_production_readiness_audit.py` | 缺门槛阻断、密钥脱敏、production runner 未实现阻断、缺 evidence、CLI 相对路径解析 |

### Intel Brief Telegram Local Bootstrap 注册（2026-07-07）

| 模块/脚本 | 路径 | 说明 |
|---|---|---|
| Telegram local bootstrap | `packages/clawbot/src/intel/telegram_bootstrap.py` | 本机 Telegram 沙盒自举：getMe、getUpdates、chat id 自动发现、summary sandbox send；证据脱敏。 |
| Telegram local bootstrap CLI | `packages/clawbot/scripts/intel_telegram_local_bootstrap.py` | 支持 `--prompt-token` 隐藏输入、`--open-telegram`、`--wait-seconds`；真实网络必须显式 `--allow-real-network` 和 sandbox ack。 |

| 测试文件 | 被测模块 | 覆盖类型 |
|---|---|---|
| `test_intel_telegram_bootstrap.py` | `src/intel/telegram_bootstrap.py`, `packages/clawbot/scripts/intel_telegram_local_bootstrap.py` | chat candidate 选择、缺 ack 阻断、注入 transport 成功发送、轮询 `/start`、CLI blocked evidence |


### Intel Brief Production Runner Contract 注册（2026-07-07）

| 模块/脚本 | 路径 | 说明 |
|---|---|---|
| Intel production scheduler gate | `packages/clawbot/src/execution/intel_brief.py` | Production mode 校验 token/chat id、sandbox ack、worker placement、production ack、summary evidence；全部齐备才 `production_ready`。 |
| ExecutionScheduler production branch | `packages/clawbot/src/execution/scheduler.py` | Gate ready 后调用注入 `intel_brief_production_runner` 或默认 Telegram summary delivery probe；不会绕过 gate。 |

| 测试文件 | 被测模块 | 覆盖类型 |
|---|---|---|
| `test_intel_scheduler_gate.py` | `src/execution/intel_brief.py`, `src/execution/scheduler.py` | production gate ready/blocked、缺 summary、缺 ack、注入 production runner |
| `test_intel_production_readiness.py` | `src/intel/production_readiness.py` | readiness all-gates-ready 与真实缺口聚合 |


### Intel Brief SGW Preferred Worker 注册（2026-07-07）

| 模块/脚本 | 路径 | 说明 |
|---|---|---|
| Intel remote runner | `packages/clawbot/scripts/intel_worker_remote_run.py` | 无 pip 依赖时使用系统 Python 执行临时 worker bundle；有 pip 依赖时才建 venv。 |
| Intel collect once | `packages/clawbot/scripts/intel_collect_once.py` | `senate_trading` 默认路由到 `oracle-sg-west` / `oracle-sg-west-preferred-overseas`；`akshare` 仍路由 Yanhuoyun。 |

| 测试文件 | 被测模块 | 覆盖类型 |
|---|---|---|
| `test_intel_worker_remote_runner.py` | `packages/clawbot/scripts/intel_worker_remote_run.py` | system-python no-pip path、失败仍 cleanup、help CLI |
| `test_intel_collect_once.py` | `packages/clawbot/scripts/intel_collect_once.py` | SGW preferred profile、collect aggregation、unknown source failure |


### Intel Brief Private Env / Launch Package 注册（2026-07-07）

| 模块/脚本 | 路径 | 说明 |
|---|---|---|
| Private env helpers | `packages/clawbot/src/intel/private_env.py` | 写入/读取/审计 `.openclaw/intel-brief.production.env`，证据脱敏，权限 0600。 |
| Private env CLI | `packages/clawbot/scripts/intel_private_env.py` | 写入或 audit 私有 env；不写 production ack。 |
| Launch package | `packages/clawbot/src/intel/launch_package.py` | 生成 launchd review package，不安装。 |
| Launch package CLI | `packages/clawbot/scripts/intel_launch_package.py` | 写 launchd dry-run package evidence，`production_action=none`。 |

| 测试文件 | 被测模块 | 覆盖类型 |
|---|---|---|
| `test_intel_private_env.py` | private env helpers/CLI | 权限 0600、脱敏、audit、gitignore 覆盖 |
| `test_intel_launch_package.py` | launch package helpers/CLI | dry-run plist/rollback/evidence |
| `test_intel_scheduler_gate.py` | scheduler gate | `INTEL_BRIEF_PRIVATE_ENV` 合并与脱敏 |


### Intel Brief Production-once 注册（2026-07-07）

| 模块/脚本 | 路径 | 说明 |
|---|---|---|
| Production-once runner | `packages/clawbot/src/intel/production_once.py` | 一次性 production delivery 入口；先评估 gate，ready 后才调用 Telegram summary delivery。 |
| Production-once CLI | `packages/clawbot/scripts/intel_production_once.py` | future scheduler target；当前缺门禁时 blocked 且 `network_calls=0`。 |

| 测试文件 | 被测模块 | 覆盖类型 |
|---|---|---|
| `test_intel_production_once.py` | production-once runner/CLI | 缺 gate 不联网、注入 runner 成功、CLI blocked evidence |

### Intel Brief Production-once Private Env 修复注册（2026-07-07）

| 模块/脚本 | 路径 | 说明 |
|---|---|---|
| Production-once runner | `packages/clawbot/src/intel/production_once.py` | 调用 delivery runner 前合并 `INTEL_BRIEF_PRIVATE_ENV`，保证 gate 与真实 Telegram sender 使用同一脱敏运行环境。 |
| Production-once CLI | `packages/clawbot/scripts/intel_production_once.py` | 已完成一次真实 Telegram production-once 投递；仍不安装 scheduler。 |

| 测试文件 | 被测模块 | 覆盖类型 |
|---|---|---|
| `test_intel_production_once.py` | `src/intel/production_once.py` | 缺 gate 不联网、注入 runner 成功、CLI blocked、private env 传递给 delivery runner |

真实投递 evidence：`packages/clawbot/data/intel_evidence/phaser/20260707T032645Z-production-once-real-delivery.json`。该 evidence 只记录 endpoint 脱敏、chat_id_present、message_id presence、network_calls，不记录 token/chat id。

### Intel Brief Production Cycle 注册（2026-07-07）

| 模块/脚本 | 路径 | 说明 |
|---|---|---|
| Production cycle runner | `packages/clawbot/src/intel/production_cycle.py` | Fresh one-shot production path：preflight → collect-once → brief → summary → production-once Telegram delivery。 |
| Production cycle CLI | `packages/clawbot/scripts/intel_production_cycle.py` | 未来 scheduler target；当前已完成一次真实 one-shot run。 |
| Launch package | `packages/clawbot/src/intel/launch_package.py` | dry-run plist 指向 `intel_production_cycle.py`，不再重放固定 summary evidence。 |

| 测试文件 | 被测模块 | 覆盖类型 |
|---|---|---|
| `test_intel_production_cycle.py` | production cycle runner/CLI | 无 ack 不采集不联网、fresh cycle 编排、CLI blocked evidence |
| `test_intel_launch_package.py` | launch package | plist 指向 production cycle；CLI 不再要求 fixed summary |

真实 fresh cycle evidence：`packages/clawbot/data/intel_evidence/phases/20260707T034621Z-production-cycle-real-delivery.json`。

### Intel Brief LaunchAgent 注册（2026-07-07）

| 项目 | 路径/Label | 说明 |
|---|---|---|
| LaunchAgent label | `ai.openclaw.intel-brief.scheduler` | macOS 用户 LaunchAgent，日历触发 08:30。 |
| Installed plist | `~/Library/LaunchAgents/ai.openclaw.intel-brief.scheduler.plist` | 已加载；目标脚本为 `packages/clawbot/scripts/intel_production_cycle.py`。 |
| Evidence dir | `packages/clawbot/data/intel_evidence/phaset/20260707T040135Z-launchd-production-cycle-install-package-absolute/runs` | launchd 自动运行输出位置。 |
| Logs | `.../logs/stdout.log` / `stderr.log` | launchd stdout/stderr。 |
| Rollback | `launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/ai.openclaw.intel-brief.scheduler.plist && rm -f ...` | 已记录在 install/load evidence。 |

安装证据：`packages/clawbot/data/intel_evidence/phaset/20260707T040135Z-launchd-production-cycle-reinstall-load-absolute.json`。

### Intel Brief LaunchAgent Post-run Audit 注册（2026-07-07）

| 模块/脚本 | 路径 | 说明 |
|---|---|---|
| LaunchAgent audit | `packages/clawbot/src/intel/launchagent_audit.py` | 只读审计 launchctl 状态、run evidence、stdout/stderr，判断自然触发是否完成；当 macOS `launchctl runs` 计数滞后但 artifact/stdout 均成功时，记录 `counter_mismatch=true` 并以 artifact/stdout 作为验证依据。 |
| LaunchAgent audit CLI | `packages/clawbot/scripts/intel_launchagent_audit.py` | 输出 Phase U evidence；`verified_success` 退出 0，否则退出 2。 |
| LaunchAgent next-run readiness | `packages/clawbot/src/intel/launchagent_readiness.py` | 只读解析 installed plist 与 controlled six-source evidence，证明下一次自然触发是否会使用当前六源默认链路。 |
| LaunchAgent readiness CLI | `packages/clawbot/scripts/intel_launchagent_next_run_readiness.py` | 输出 Phase BD readiness evidence；`ready` 退出 0，否则退出 2。 |

| 测试文件 | 被测模块 | 覆盖类型 |
|---|---|---|
| `test_intel_launchagent_audit.py` | launchagent audit | 未触发 pending、成功触发 verified、launchctl counter stale fallback、CLI evidence |
| `test_intel_launchagent_readiness.py` | launchagent readiness | 默认六源 ready、显式旧 source mismatch、CLI evidence |

当前 verified evidence：`packages/clawbot/data/intel_evidence/phaset/20260707T211424Z-launchagent-natural-0830-verified-with-artifact/evidence.json`；`verification.basis=artifact_and_standard_output`，`launchctl.counter_mismatch=true`。
Next-run six-source readiness evidence：`packages/clawbot/data/intel_evidence/phasebd/20260707T213012Z-launchagent-next-run-six-source-readiness/evidence.json`；`status=ready`，`missing=[]`。

### Intel Brief SGW Fallback / Remote Runner Resilience 注册（2026-07-07）

| 模块/脚本 | 路径 | 说明 |
|---|---|---|
| Collect once | `packages/clawbot/scripts/intel_collect_once.py` | `senate_trading` 默认优先 SGW，失败后 fallback 到 `oracle-arm1-overseas-fallback`；evidence 记录 `attempts[]` / `fallback`。 |
| Remote worker runner | `packages/clawbot/scripts/intel_worker_remote_run.py` | 初始 SSH staging/mkdir 失败时 fail-fast，避免重复 SSH timeout；仍只做 `/tmp` 临时 staging。 |

| 测试文件 | 被测模块 | 覆盖类型 |
|---|---|---|
| `test_intel_collect_once.py` | collect once | SGW failed → oracle-arm1 fallback success；summary success；fallback evidence 字段 |
| `test_intel_worker_remote_runner.py` | remote runner | staging SSH failure fail-fast，不继续 worker/health/cleanup/verify |

真实证据：

- Fallback 路径：`packages/clawbot/data/intel_evidence/phasew/20260707T124408Z-forced-senate-fallback/collect-once.json`
- Production cycle：`packages/clawbot/data/intel_evidence/phasew/20260707T124152Z-production-cycle-with-sgw-fallback/latest-production-cycle.json`
- LaunchAgent canary：`packages/clawbot/data/intel_evidence/phasew/20260707T125003Z-launchd-calendar-canary-verified/post-run-audit.json`
- Canary rollback：`packages/clawbot/data/intel_evidence/phasew/20260707T125003Z-launchd-calendar-canary-verified/rollback-evidence.json`

### Intel Brief Commercial MVP Subscription 注册（2026-07-07）

| 模块/脚本 | 路径 | 说明 |
|---|---|---|
| Subscription service | `packages/clawbot/src/intel/subscriptions.py` | 商业 MVP 订阅与偏好服务：plan/subscriber/subscription/preferences/delivery cadence/menu contract。 |
| DB schema | `packages/clawbot/src/intel/db/intel_brief_schema.sql` | 新增 `delivery_preferences` 与 `subscription_audit_log`。 |

| 测试文件 | 被测模块 | 覆盖类型 |
|---|---|---|
| `test_intel_commercial_mvp.py` | `src/intel/subscriptions.py` / schema | 订阅授权、到期排除、分类偏好、推送偏好、Telegram menu contract |

真实证据：`packages/clawbot/data/intel_evidence/phasey/20260707T152655Z-commercial-mvp-subscription-contract/evidence.json`。

### Intel Brief Telegram Menu Handler Contract 注册（2026-07-07）

| 模块/脚本 | 路径 | 说明 |
|---|---|---|
| Telegram menu contract handler | `packages/clawbot/src/intel/telegram_menu.py` | 不联网处理 Intel Brief Telegram 命令合同：start/status/sources/schedule/custom/help。 |
| Telegram menu sandbox | `packages/clawbot/scripts/intel_telegram_menu_sandbox.py` | 用 sandbox SQLite 演练用户菜单、订阅授权、偏好、开放人物追踪 audit。 |

| 测试文件 | 被测模块 | 覆盖类型 |
|---|---|---|
| `test_intel_telegram_menu_handlers.py` | `src/intel/telegram_menu.py` / sandbox script | subscriber 创建、active subscription 状态、分类偏好、推送计划、人物追踪审计、evidence 生成 |

真实证据：`packages/clawbot/data/intel_evidence/phasez/20260707T155448Z-telegram-menu-handler-contract/evidence.json`。该证据 `network_calls=0`，不包含真实 Telegram token/chat id。

### Intel Brief Telegram Runtime Adapter 注册（2026-07-07）

| 模块/脚本 | 路径 | 说明 |
|---|---|---|
| Telegram runtime adapter | `packages/clawbot/src/intel/telegram_runtime.py` | 解析 Telegram update，调用 Intel Brief menu handler，并通过注入式 sender 回复。 |
| Runtime sandbox | `packages/clawbot/scripts/intel_telegram_runtime_sandbox.py` | fake sender + sandbox SQLite 演练完整用户配置流。 |

| 测试文件 | 被测模块 | 覆盖类型 |
|---|---|---|
| `test_intel_telegram_runtime.py` | `src/intel/telegram_runtime.py` / runtime sandbox | update 解析、reply sender 注入、chat id 脱敏、active 用户配置、evidence 生成 |

真实证据：`packages/clawbot/data/intel_evidence/phaseaa/20260707T160334Z-telegram-runtime-adapter-sandbox/evidence.json`。该证据 `network_calls=0`，不包含真实 Telegram token/chat id。

### Intel Brief Telegram Bot API Runtime Probe 注册（2026-07-07）

| 模块/脚本 | 路径 | 说明 |
|---|---|---|
| Bot API runtime probe | `packages/clawbot/src/intel/telegram_bot_runtime.py` | Bot API gate、`setMyCommands`、`getUpdates` 与脱敏 evidence。 |
| Bot API runtime CLI | `packages/clawbot/scripts/intel_telegram_bot_runtime_probe.py` | 从私有 env 执行受控真实 Bot API probe；不发送消息。 |

| 测试文件 | 被测模块 | 覆盖类型 |
|---|---|---|
| `test_intel_telegram_bot_runtime.py` | `src/intel/telegram_bot_runtime.py` / CLI | gate blocked、命令 payload、getUpdates 脱敏、evidence 生成、CLI blocked |

真实证据：

- 注入式合同：`packages/clawbot/data/intel_evidence/phaseab/20260707T161200Z-telegram-bot-runtime-injected-contract/evidence.json`
- 真实 Bot API：`packages/clawbot/data/intel_evidence/phaseab/20260707T161129Z-telegram-bot-runtime-real-probe.json`

### Intel Brief Telegram Update Processor 注册（2026-07-07）

| 模块/脚本 | 路径 | 说明 |
|---|---|---|
| Telegram update processor | `packages/clawbot/src/intel/telegram_update_processor.py` | 持久化 update offset，过滤重复 update，调用 runtime adapter，成功后推进 offset。 |
| Update processor sandbox | `packages/clawbot/scripts/intel_telegram_update_processor_sandbox.py` | fake client/sender + sandbox DB 演练 offset 防重复与用户配置流。 |
| Runtime state schema | `packages/clawbot/src/intel/db/intel_brief_schema.sql` | 新增 `telegram_runtime_state(bot_profile,last_update_id,updated_at)`。 |

| 测试文件 | 被测模块 | 覆盖类型 |
|---|---|---|
| `test_intel_telegram_update_processor.py` | schema / `src/intel/telegram_update_processor.py` / sandbox | offset 持久化、重复跳过、用户配置、evidence 生成 |

真实证据：`packages/clawbot/data/intel_evidence/phaseac/20260707T161820Z-telegram-update-processor-offset-sandbox/evidence.json`。

### Intel Brief Telegram Baseline Offset 注册（2026-07-07）

| 模块/脚本 | 路径 | 说明 |
|---|---|---|
| Telegram baseline offset | `packages/clawbot/src/intel/telegram_baseline_offset.py` | 自动回复前读取最新 update_id 并设置 baseline offset，不回复历史命令。 |
| Baseline offset CLI | `packages/clawbot/scripts/intel_telegram_baseline_offset.py` | 使用私有 env 真实执行 baseline getUpdates；只写 offset。 |

| 测试文件 | 被测模块 | 覆盖类型 |
|---|---|---|
| `test_intel_telegram_baseline_offset.py` | baseline helper / CLI | offset 推进、不降低已有 offset、evidence 脱敏、blocked gate |

真实证据：

- sandbox：`packages/clawbot/data/intel_evidence/phasead/20260707T162500Z-telegram-baseline-offset-sandbox/evidence.json`
- real：`packages/clawbot/data/intel_evidence/phasead/20260707T162505Z-telegram-baseline-offset-real.json`

### Intel Brief Telegram Real Update Runner 注册（2026-07-07）

| 模块/脚本 | 路径 | 说明 |
|---|---|---|
| Real update runner | `packages/clawbot/src/intel/telegram_real_update_runner.py` | 真实 Bot API getUpdates + sendMessage sender 接入 offset-safe processor，带显式 send gate。 |
| Real update runner CLI | `packages/clawbot/scripts/intel_telegram_real_update_runner.py` | 一次性运行真实 update 处理；默认 blocked，需显式允许网络和发送。 |

| 测试文件 | 被测模块 | 覆盖类型 |
|---|---|---|
| `test_intel_telegram_real_update_runner.py` | real runner / CLI | gate、注入式 send、无新 update 不发送、evidence blocked、CLI blocked |

真实证据：`packages/clawbot/data/intel_evidence/phaseae/20260707T163143Z-telegram-real-update-runner-one-shot.json`。


### Intel Brief Subscription-filtered Delivery 注册（2026-07-07）

| 模块/脚本 | 路径 | 说明 |
|---|---|---|
| Subscription delivery helper | `packages/clawbot/src/intel/subscription_delivery.py` | 从 summary evidence 提取来源分类，筛选 active/non-expired/matching source preference Telegram 订阅者，调用注入式 sender，并写 `delivery_log`。 |
| Subscription delivery sandbox CLI | `packages/clawbot/scripts/intel_subscription_delivery_sandbox.py` | 使用 sandbox SQLite 与 fake sender 生成脱敏 evidence；不联网。 |

| 测试文件 | 被测模块 | 覆盖类型 |
|---|---|---|
| `packages/clawbot/tests/test_intel_subscription_filtered_delivery.py` | `src/intel/subscription_delivery.py` | 订阅到期/偏好过滤、delivery_log、evidence 脱敏、sandbox builder。 |

证据：`packages/clawbot/data/intel_evidence/phaseaf/20260707T164449Z-subscription-filtered-delivery-sandbox/evidence.json`；最终验证：`packages/clawbot/data/intel_evidence/phaseaf/20260707T165346Z-subscription-filtered-delivery-final-verification.json`。

边界：该注册项目前未成为正式 production cycle 的 recipient selector；真实 Telegram delivery 仍走既有生产路径，直到后续显式接线并验证。


### Intel Brief Production-once Subscription Switch 注册（2026-07-07）

| 模块/开关 | 路径/变量 | 说明 |
|---|---|---|
| Production delivery switch | `packages/clawbot/src/intel/production_once.py` | `INTEL_BRIEF_SUBSCRIPTION_DELIVERY_ENABLED=true` 时从 fixed-chat 改走 subscription-filtered delivery。默认关闭。 |
| Intel Brief DB path gate | `INTEL_BRIEF_DB_PATH` | subscription delivery 开启时必填；缺失则 blocked 且不调用 Telegram。 |
| Tests | `packages/clawbot/tests/test_intel_production_once.py` | 覆盖默认 fixed-chat、订阅接线、缺 DB 阻断。 |

证据：`packages/clawbot/data/intel_evidence/phaseag/20260707T165951Z-production-once-subscription-delivery-switch-sandbox/evidence.json`；最终验证：`packages/clawbot/data/intel_evidence/phaseag/20260707T170034Z-production-once-subscription-switch-final-verification.json`。

运维边界：正式 LaunchAgent 环境尚未加入该开关；当前 daily production loop 仍按 fixed-chat 路径运行，直到后续显式切换并产出真实证据。


### Intel Brief Telegram Inline Keyboard 菜单注册（2026-07-07）

| 模块/能力 | 路径 | 说明 |
|---|---|---|
| Inline menu contract | `packages/clawbot/src/intel/subscriptions.py` | `build_telegram_menu_contract()` 输出 `reply_markup.inline_keyboard`，5 行 22 个按钮，`menu_style=inline_keyboard_card`。 |
| Callback handling | `packages/clawbot/src/intel/telegram_runtime.py` | 支持 `callback_query`，将按钮文本映射到现有 sources/status/custom/schedule handler。 |
| Bot API polling | `packages/clawbot/src/intel/telegram_bot_runtime.py` | `allowed_updates` 包含 `message` 与 `callback_query`。 |
| Callback ACK | `packages/clawbot/src/intel/telegram_delivery.py` | `TelegramBotApiSender.answer_callback_query()`，防止 inline 按钮点击后客户端 loading。 |

测试覆盖：`packages/clawbot/tests/test_intel_telegram_menu_handlers.py`、`test_intel_telegram_runtime.py`、`test_intel_telegram_delivery.py`、`test_intel_telegram_bot_runtime.py`、`test_intel_telegram_real_update_runner.py`。

证据：`packages/clawbot/data/intel_evidence/phaseai/20260707T172324Z-real-telegram-inline-keyboard-menu-send/evidence.json`；最终验证：`packages/clawbot/data/intel_evidence/phaseai/20260707T172410Z-inline-keyboard-menu-final-verification.json`。

### Intel Brief Telegram reference-style menu contract（2026-07-07）

| Registry item | Location | Current baseline |
|---|---|---|
| Reference-style inline menu | `packages/clawbot/src/intel/subscriptions.py` | `/start` 菜单正文为短标题/短说明；按钮在 `reply_markup.inline_keyboard` 中渲染。 |
| Button grid | `TELEGRAM_INLINE_MENU_KEYBOARD` | 7 行、25 个按钮、最大 4 列；第 6 行为 `设置/自定义/定时`，最后一行为 `🔍 情报搜索/👥 功能导航` 两个宽入口；不得回退为正文 ASCII 菜单。 |
| Evidence | `packages/clawbot/data/intel_evidence/phaseba/20260707T210719Z-screenshot-style-menu-v3-real-send/evidence.json` | 真实 Telegram `sendMessage` 成功，脱敏 evidence 记录新版 7 行 25 按钮截图式菜单；未写 token/chat id 明文。 |

### Intel Brief real subscription-filtered delivery baseline（2026-07-07）

| Registry item | Location | Current baseline |
|---|---|---|
| Production subscriber DB | `packages/clawbot/data/intel_brief.db` | 1 个 Telegram subscriber，active 内部测试订阅，偏好 `akshare/senate_trading`，推送 daily 08:30 America/Denver。 |
| Delivery log | `delivery_log` table | 已有 1 条真实 Telegram delivery success 记录；不记录 raw chat id。 |
| Real delivery evidence | `packages/clawbot/data/intel_evidence/phaseaj/20260707T174622Z-real-subscription-filtered-delivery/evidence.json` | `eligible=1/sent=1/failed=0`；`delivery_log_delta=1`；source categories `akshare/senate_trading`。 |
| Redaction contract | `packages/clawbot/src/intel/subscription_delivery.py` | Returned delivery evidence records `user_id_present` / `channel_user_id_present` only; raw Telegram user id and chat id are in-memory only. |
| User-facing delivery copy | `packages/clawbot/src/intel/delivery.py` | 默认 production 文案为 `🧭 情报简报` + 公开来源/非投资建议提示；sandbox fake 文案只在显式 `delivery_context="sandbox"` 时使用。 |
| Commercial E2E audit | `packages/clawbot/src/intel/e2e_status_audit.py` / `packages/clawbot/scripts/intel_e2e_status_audit.py` | 只读汇总真实 subscriber、订阅/偏好、最新 delivery_log、next-run readiness 和最近 production delivery evidence；不写 raw chat id/user id/token/message。 |
| E2E evidence | `packages/clawbot/data/intel_evidence/phasebe/20260707T213933Z-commercial-mvp-e2e-status-audit/evidence.json` | `status=verified`；active eligible subscriber=1；latest delivery success；无 sandbox/fake 文案；按偏好过滤；next-run readiness=ready。 |

### Intel Brief daily subscription delivery runtime switch（2026-07-07）

| Registry item | Location | Current baseline |
|---|---|---|
| Daily delivery mode | `.openclaw/intel-brief.production.env` | `INTEL_BRIEF_SUBSCRIPTION_DELIVERY_ENABLED=true`（私有 env，不提交、不打印明文）。 |
| Production DB path | `.openclaw/intel-brief.production.env` | `INTEL_BRIEF_DB_PATH` 指向正式 `packages/clawbot/data/intel_brief.db`，存在性已验证。 |
| LaunchAgent | `~/Library/LaunchAgents/ai.openclaw.intel-brief.scheduler.plist` | plist 未重装；通过 `INTEL_BRIEF_PRIVATE_ENV` 读取私有 env。 |
| Gate hardening | `packages/clawbot/src/intel/production_once.py` | subscription mode requires token present + DB path present + DB file exists before any send. |
| Controlled evidence | `packages/clawbot/data/intel_evidence/phaseal/20260707T175654Z-daily-subscription-mode-production-once/evidence.json` | `delivery_mode=subscription_filtered`，真实 Telegram delivery success，`delivery_log_delta=1`。 |

### Intel Brief controlled production_cycle subscription-mode baseline（2026-07-07）

| Registry item | Location | Current baseline |
|---|---|---|
| Production cycle script path | `packages/clawbot/scripts/intel_production_cycle.py` | 已在 private env subscription mode 下受控跑通。 |
| Full-chain evidence | `packages/clawbot/data/intel_evidence/phaseam/20260707T180242Z-controlled-production-cycle-subscription-mode/latest-production-cycle.json` | status=success，collect success=2/failed=0，network_calls=1。 |
| Delivery mode evidence | `.../runs/20260707T180242Z-production-once-delivery.json` | `delivery_mode=subscription_filtered`，subscription gate ready，`eligible=1/sent=1/failed=0`。 |
| Delivery log baseline | `packages/clawbot/data/intel_brief.db` / `delivery_log` | 至少 3 条真实 Telegram success 记录。 |

### Intel Brief subscription lifecycle registry（2026-07-07）

| Registry item | Location | Current baseline |
|---|---|---|
| Lifecycle module | `packages/clawbot/src/intel/subscription_lifecycle.py` | `audit_subscription_lifecycle()` supports read-only audit, optional expired marking, optional reminder sending, same-day reminder de-dup. |
| Lifecycle sandbox | `packages/clawbot/scripts/intel_subscription_lifecycle_sandbox.py` | Generates sandbox evidence with fake sender; no Telegram network. |
| Lifecycle maintenance CLI | `packages/clawbot/scripts/intel_subscription_lifecycle.py` | Production-safe entrypoint; default read-only, `--apply-expiry` requires lifecycle apply ack, `--send-reminders` requires Telegram token + runtime ack + `--allow-real-network`. |
| Lifecycle tests | `packages/clawbot/tests/test_intel_subscription_lifecycle.py` | Covers read-only audit, expiry marking, reminder send, dedup, gated maintenance wrapper, CLI evidence, and redaction. |
| Sandbox evidence | `packages/clawbot/data/intel_evidence/phasean/20260707T181146Z-subscription-lifecycle-sandbox/evidence.json` | expired=1, reminder=1, audit=2, replay reminder=0. |
| Production read-only audit | `packages/clawbot/data/intel_evidence/phasean/20260707T181219Z-production-db-subscription-lifecycle-readonly-audit/evidence.json` | Current production DB has no expired active subscription and no 7-day expiring subscription; counts unchanged. |
| Maintenance evidence | `packages/clawbot/data/intel_evidence/phasebc/20260707T212320Z-subscription-lifecycle-maintenance-sandbox/evidence.json` / `phasebc/20260707T212337Z-subscription-lifecycle-production-readonly/evidence.json` | Sandbox proves blocked/apply/reminder gates; production read-only audit succeeded with no expired/expiring candidates and `network_calls=0`. |

### Intel Brief production_cycle lifecycle audit integration（2026-07-07）

| Registry item | Location | Current baseline |
|---|---|---|
| Lifecycle integration | `packages/clawbot/src/intel/production_cycle.py` | Top-level `subscription_lifecycle` is written into production-cycle evidence. |
| Read-only policy | `audit_subscription_lifecycle(... apply_expiry=False, send_reminders=False)` | Daily cycle observes expiry state but does not mutate subscriptions or send reminders. |
| DB path source | private env `INTEL_BRIEF_DB_PATH` | If missing/not found, lifecycle audit is `skipped` and main cycle continues. |
| Integration evidence | `packages/clawbot/data/intel_evidence/phaseao/20260707T182041Z-production-cycle-lifecycle-readonly-integration/wrapper.json` | Production DB counts unchanged, lifecycle summary all 0, network_calls=0. |

### Intel Brief manual entitlement registry（2026-07-07）

| Registry item | Location | Current baseline |
|---|---|---|
| Manual entitlement module | `packages/clawbot/src/intel/manual_entitlement.py` | Converts verified external order info into subscription grant; dry-run by default. |
| Operator CLI | `packages/clawbot/scripts/intel_manual_entitlement.py` | Requires `--apply` for mutation; otherwise preview only. |
| Sandbox CLI | `packages/clawbot/scripts/intel_manual_entitlement_sandbox.py` | Verifies dry-run, apply, renewal, redaction without production DB. |
| Tests | `packages/clawbot/tests/test_intel_manual_entitlement.py` | Covers dry-run no business writes, renewal extension, CLI evidence, sandbox redaction. |
| Production dry-run evidence | `packages/clawbot/data/intel_evidence/phaseap/20260707T183007Z-production-db-manual-entitlement-dry-run/evidence.json` | counts unchanged, planned renewal expiry calculated, network_calls=0. |

### Intel Brief Telegram reference screenshot menu baseline（2026-07-07 Phase AR）

| Registry item | Location | Current baseline |
|---|---|---|
| Reference screenshot menu | `packages/clawbot/src/intel/subscriptions.py` | `/start` 正文为 `🔥 热搜排行` + 高价值情报入口 + 关键词搜索提示；首屏不展示订阅状态或命令说明。 |
| Button definitions | `TELEGRAM_INLINE_MENU_BUTTONS` | 6 行、23 个按钮、最大 4 列；按钮展示文本与 `callback_data` 分离。 |
| Callback mapping | `packages/clawbot/src/intel/telegram_menu.py` | `github/openai/claude/deepseek/settings/custom/schedule/status` 等稳定 callback 值映射到现有 handler。 |
| Evidence | `packages/clawbot/data/intel_evidence/phasear/20260707T185237Z-reference-screenshot-style-menu-real-send/evidence.json` | 真实 Telegram `sendMessage` 成功，evidence 只记录 token/chat id 存在性与脱敏发送结果。 |

### Intel Brief GitHub Trending source registry（2026-07-07 Phase AQ）

| Registry item | Location | Current baseline |
|---|---|---|
| Source adapter | `packages/clawbot/src/intel/sources/github_trending.py` | `GitHubTrendingAdapter` 抓取 `https://github.com/trending?since=daily`，输出 `repo/url/description/language/stars_today`。 |
| Parser invariant | `parse_github_trending_html()` | 仓库名只从 article 内 repo heading 的 `<h2><a>` 提取，避免 `/sponsors/...` 链接误识别为 repo。 |
| Default registry | `packages/clawbot/src/intel/sources/registry.py` | `build_default_source_adapters()` 注册 `github_trending`，evidence 指向已验证的 Oracle SG West 真实调用。 |
| Worker profile | `packages/clawbot/scripts/intel_collect_once.py` | primary=`oracle-sg-west`，fallback=`oracle-arm1`，fallback source 保持 `github_trending`。 |
| Worker bundle | `packages/clawbot/scripts/intel_worker_bundle.py` | bundle 包含 `src/intel/sources/github_trending.py`。 |
| Real worker evidence | `packages/clawbot/data/intel_evidence/phaseaq/20260707T190500Z-github-trending-oracle-sg-worker-parser-fixed.json` | Oracle SG West real call success，`raw_count=3`，cleanup=`cleanup_ok`，cleanup_verify=`remote_stage_absent`。 |
| Production-cycle evidence | `packages/clawbot/data/intel_evidence/phaseaq/20260707T190718Z-controlled-production-cycle-three-sources/latest-production-cycle.json` | 三源 collect success=3/failed=0，并完成 subscription-filtered Telegram delivery。 |
| Final verification | `packages/clawbot/data/intel_evidence/phaseaq/20260707T191656Z-github-trending-final-verification/evidence.json` | ruff/pytest/JSON parse/token scan/docs sync 通过。 |

### Intel Brief AI model updates source registry（2026-07-07 Phase AU）

| Registry item | Location | Current baseline |
|---|---|---|
| Source adapter | `packages/clawbot/src/intel/sources/ai_model_updates.py` | `AIModelUpdatesAdapter` 聚合 OpenAI official RSS、Anthropic official news HTML、DeepSeek official homepage announcement HTML。 |
| Providers | `DEFAULT_AI_MODEL_UPDATE_FEEDS` | `openai=https://openai.com/news/rss.xml`；`anthropic=https://www.anthropic.com/news`；`deepseek=https://www.deepseek.com/`。DeepSeek 使用根页是因为 Oracle SG West 访问 `/news` 返回 404。 |
| Merge invariant | `fetch_ai_model_updates()` | 按 feed 轮询合并，避免 OpenAI RSS 多条记录挤掉 Anthropic/DeepSeek。 |
| Default registry | `packages/clawbot/src/intel/sources/registry.py` | 注册 `ai_model_updates`，evidence 指向已验证 Oracle SG West real worker。 |
| Worker profile | `packages/clawbot/scripts/intel_collect_once.py` | primary=`oracle-sg-west`，fallback=`oracle-arm1`，source-specific `limit=6`。 |
| GitHub source limit | `packages/clawbot/scripts/intel_collect_once.py` | `github_trending` source-specific `limit=3`，对应 Star 增长榜前三 MVP 口径。 |
| Telegram AI buttons | `packages/clawbot/src/intel/telegram_menu.py` | `OpenAI/Claude/Deepseek` 按钮均映射到 `ai_model_updates` 订阅分类。 |
| Real worker evidence | `packages/clawbot/data/intel_evidence/phaseau/20260707T193548Z-ai-model-updates-oracle-sg-worker-final.json` | Oracle SG West real call success，providers=`openai/anthropic/deepseek`，cleanup verified。 |
| Four-source cycle evidence | `packages/clawbot/data/intel_evidence/phaseau/20260707T194551Z-controlled-production-cycle-four-sources-source-limits/latest-production-cycle.json` | `senate_trading/akshare/github_trending/ai_model_updates` collect success=4/failed=0；subscription-filtered delivery success。 |
| Final verification | `packages/clawbot/data/intel_evidence/phaseau/20260707T195140Z-ai-model-and-recipient-filter-final-verification/evidence.json` | ruff/pytest/diff/JSON/token scan/docs sync 通过。 |

### Intel Brief per-recipient delivery filter registry（2026-07-07 Phase AV）

| Registry item | Location | Current baseline |
|---|---|---|
| Recipient payload filter | `packages/clawbot/src/intel/subscription_delivery.py` | `_filter_summary_payload_for_categories()` 在发送前按 subscriber `matched_categories` 裁剪 items，并重写 summary_text，避免未订阅分类泄漏到正文。 |
| Delivery evidence | `deliver_summary_to_eligible_subscribers()` | 每个 delivery 记录 `matched_categories` 与 `filtered_item_count`，不记录 raw chat id/user id。 |
| Sandbox evidence | `packages/clawbot/data/intel_evidence/phaseav/20260707T194902Z-subscription-delivery-per-recipient-filter-sandbox/evidence.json` | 三个 sandbox 用户分别只收到自己分类的 1 条 item。 |

## Intel Brief source registry update — institutional_13f aggregated evidence (2026-07-07)

- Source: `institutional_13f`
- Adapter: `packages/clawbot/src/intel/sources/institutional_13f.py`
- Registry evidence: `packages/clawbot/data/intel_evidence/phaseaw/20260707T201214Z-institutional-13f-oracle-sg-worker-aggregated.json`
- Target worker: Oracle Singapore West (`oracle-sg-west-preferred-overseas`)
- Verified result: `status=success`, `raw_count=10`, cleanup `remote_stage_absent`; sample holdings include Apple, American Express, Coca Cola, Bank of America, Chevron.
- Quality note: duplicate SEC 13F rows are aggregated by `(issuer, class, cusip)` before limiting, so top-N is not consumed by split rows for the same issuer.

## Intel Brief source registry update — weather source (2026-07-07)

- Source: `weather`
- Adapter: `packages/clawbot/src/intel/sources/weather_monitor.py`
- Registry evidence: `packages/clawbot/data/intel_evidence/phaseaz/20260707T204803Z-weather-oracle-sg-worker.json`
- Target worker: Oracle Singapore West (`oracle-sg-west-preferred-overseas`), fallback Oracle ARM1.
- External endpoints:
  - NWS: `https://api.weather.gov/points/{lat},{lon}`, `forecastHourly`, `https://api.weather.gov/alerts/active?point={lat},{lon}`. Requires custom User-Agent.
  - Open-Meteo Air Quality: `https://air-quality-api.open-meteo.com/v1/air-quality?...` no key for MVP probe; commercial-use boundary must be reviewed before public paid sale.
- Verified result: `status=success`, `raw_count=6`, cleanup `remote_stage_absent`; categories `weather/temperature/rainfall/humidity/disaster_alerts/air_quality`.
- Delivery behavior: item `category_aliases` lets broad `weather` subscribers receive all weather subitems while subcategory subscribers receive only their selected category.
### Intel Brief 常驻菜单与多渠道数字命令注册（2026-07-08）

| 模块/脚本 | 路径 | 说明 |
|---|---|---|
| Cross-channel numbered menu | `packages/clawbot/src/intel/channel_menu.py` | 每日简报 700-708 数字命令、Telegram/微信/飞书/钉钉菜单合同；本模块不直接调用任何平台网络接口。 |
| Telegram menu handler | `packages/clawbot/src/intel/telegram_menu.py` | `/start`、按钮 callback、旧按钮兼容、700-708 数字回复处理；`706` 支持两步式添加追踪。 |
| Telegram menu contract | `packages/clawbot/src/intel/subscriptions.py` | `build_telegram_menu_contract()` 输出当前产品化菜单文案和 inline keyboard。 |
| WeChat numbered router | `packages/clawbot/src/api/routers/wechat.py` | 微信 700-708 编号入口和中文快捷词接入 `handle_numbered_intel_command()`，不落 LLM 兜底；运行时用当前 UTC 时间判断订阅有效期；菜单/快捷词可打断两步式 pending。 |
| WeChat inbound API | `packages/clawbot/src/api/server.py` | 同时挂载 `/api/v1/wechat/incoming` 和兼容旧转发器的 `/wechat/incoming`；两条路径仍走全局 API Token。 |
| WeChat OpenClaw bridge | `.openclaw/extensions/openclaw-weixin/src/messaging/process-message.ts` + 当前加载的 `~/.openclaw/.../process-message.js` | 授权微信会话命中每日简报数字或中文快捷词时，插件调用本机 `/wechat/incoming` 并直接回发，不进入普通 AI pipeline。 |
| Telegram update daemon | `packages/clawbot/scripts/intel_telegram_update_daemon.py` | 常驻轮询 Telegram update，处理 `/start` / 数字回复 / 按钮点击；心跳保留最近一次 `/start` 菜单成功证据；不保存 raw update/chat id/token。 |
| Telegram /start acceptance CLI | `packages/clawbot/scripts/intel_telegram_start_menu_acceptance.py` | 老板发完 `/start` 后读取脱敏心跳，输出 `verified=true/false`、缺口和下一步；不读取或保存原始聊天内容。 |
| Telegram user journey acceptance CLI | `packages/clawbot/scripts/intel_telegram_user_journey_acceptance.py` | 本地临时库验收普通用户完整路径：打开菜单、看今日简报、看订阅、改时间、完整命令加追踪、两步式加追踪、暂停、暂停后查询、恢复；不调用真实 Telegram。 |
| WeChat bridge runtime acceptance CLI | `packages/clawbot/scripts/intel_wechat_bridge_runtime_acceptance.py` | 读取 OpenClaw Weixin 插件桥脱敏证据文件，验收最近一次真实微信入站是否命中每日简报桥、调用 `/wechat/incoming` 200、已回发微信且未落普通 LLM；支持 `--wait-seconds` 等待老板发微信；不保存聊天原文、用户 ID 或 Token。 |
| macOS LaunchAgent | `~/Library/LaunchAgents/ai.openclaw.intel-brief.telegram-listener.plist` | 本机每日简报菜单监听器；当前 label 为 `ai.openclaw.intel-brief.telegram-listener`。 |

| 测试文件 | 覆盖内容 |
|---|---|
| `packages/clawbot/tests/test_intel_multichannel_numbered_menu.py` | Telegram/微信/飞书/钉钉菜单能力差异、700-708 数字命令、微信入口不落 LLM。 |
| `packages/clawbot/tests/test_intel_telegram_menu_handlers.py` | Telegram `/start`、按钮、数字回复、状态、分类、完整命令追踪和两步式追踪。 |
| `packages/clawbot/tests/test_intel_telegram_runtime.py` | Telegram update 到回复合同的运行时适配。 |
| `packages/clawbot/tests/test_intel_telegram_update_daemon.py` | 常驻监听器安全闸、心跳脱敏、LaunchAgent plist、`/start` 成功证据不被空轮询覆盖。 |
| `packages/clawbot/tests/test_intel_telegram_start_menu_acceptance.py` | 真人 `/start` 菜单验收器：等待态、成功态、since 过滤和脱敏输出。 |
| `packages/clawbot/tests/test_intel_telegram_user_journey_acceptance.py` | 普通用户旅程验收：菜单、今日简报、订阅状态、推送时间、完整命令追踪、两步式追踪、暂停、恢复。 |
| `packages/clawbot/tests/test_wechat_numbered_commands.py` | 微信编号映射完整性，覆盖 700-708、本地中文快捷词、pending 打断和 `/wechat/incoming` 兼容路径。 |
| `packages/clawbot/tests/test_intel_wechat_bridge_runtime_acceptance.py` | 微信真实桥接证据验收器：近期 handled 证据可通过，旧证据、LLM 闲聊证据、未回发证据必须失败；等待模式有证据立即通过、无证据明确报告。 |
| `packages/clawbot/scripts/intel_wechat_user_journey_acceptance.py` | 微信菜单用户旅程验收器；覆盖数字、中文快捷词、两步式中途跳转、暂停恢复；只用临时 SQLite，不调用真实微信网络，输出脱敏证据。 |

真实运行边界：Telegram 监听器已真实运行；Bot API `getMe` 确认机器人为 `@carven_Jianbao_bot`，`getMyCommands` 确认 `/start` 存在；微信处理器和 OpenClaw Weixin 插件桥已就绪，并新增真实桥接证据验收器；但受微信窗口防截图限制，Codex 未完成真实桌面微信发消息验收，当前默认验收报告会在没有新微信入站时显示“未找到微信桥接证据文件”；飞书/钉钉没有真实平台入口，仍为协议层。

### Intel Brief V2 内容、双语、富媒体与运行治理注册（2026-08-04）

| 类型 | 路径/变量 | 说明 |
|---|---|---|
| 内容契约 | `packages/clawbot/src/intel/content_contract.py` | 六源统一 `ContentItem`、日期解析、URL 规范化、坏行隔离和 13F accession 聚合。 |
| 选择管道 | `packages/clawbot/src/intel/content_pipeline.py` | 时效 fail-closed、事件/实体去重、GitHub 7 日冷却、确定性评分、来源/类别配额和多样化 Top 3。 |
| 本地化 | `packages/clawbot/src/intel/localization.py`、`translation_service.py` | 实体遮罩、字段缓存、最多三个 CC Switch HTTPS 第三方端点、45 秒总 deadline；Key 只驻留内存且不进入 repr。 |
| Telegram 渲染 | `packages/clawbot/src/intel/telegram_brief_renderer.py` | 候选 3 深色首屏、管道 rank 保序、Top 3 caption、完整回放和语言/分类 callback。 |
| Telegram 媒体 | `packages/clawbot/src/intel/telegram_media_store.py` | 搬运 tgNetDisc 的核心思想：私有 Telegram `file_id` 存储与复用；不引入 Go 服务、公开文件代理或第二轮询器。 |
| 生产封面 | `packages/clawbot/assets/intel/openclaw-intel-brief-dark.jpg` | JPEG 1280 x 720，156 KB，SHA-256 `eee7a545...d5315`。 |
| 运行健康 | `packages/clawbot/src/intel/runtime_health.py`、`packages/clawbot/scripts/intel_runtime_health.py` | 只读汇总 SQLite quick check、六源覆盖、7 日周期/投递 SLI、listener 心跳和证据留存。 |
| Schema V3 | `packages/clawbot/src/intel/db/intel_brief_schema.sql` | 结构化 brief/localization、翻译缓存、Telegram media、内容事实/观察/候选、逐事件尝试、来源 LKG、管道水位和投递 claim lease。 |
| 调度 | `INTEL_BRIEF_SCHEDULER_TIMEZONE`、`INTEL_BRIEF_SCHEDULER_WINDOW_END` | 默认 Asia/Singapore，生产窗口 08:30-10:00；非法时区/窗口 fail-closed。 |
| 翻译 | `INTEL_BRIEF_TRANSLATION_ENABLED`、`CC_SWITCH_DB_PATH` | 生产需显式开启翻译；CC Switch 数据库只读。 |
| 媒体 | `INTEL_BRIEF_TELEGRAM_MEDIA_CHAT_ID` | 可选私有素材会话；未设置时由首个真实收件人的 `sendPhoto` 回包种入缓存。 |
| 富消息兼容 | `INTEL_BRIEF_TELEGRAM_RICH_MESSAGE_ENABLED` | 生产保持 false；Telegram 无官方 `sendRichMessage`，误开时本地零网络拒绝并降级 `sendPhoto`。 |

新增回归文件：`test_intel_content_contract.py`、`test_intel_content_pipeline.py`、`test_intel_db_migrations_v2.py`、`test_intel_localization.py`、`test_intel_translation_service.py`、`test_intel_brief_replay.py`、`test_intel_telegram_rich_delivery.py`、`test_intel_telegram_media_store.py`、`test_intel_runtime_health.py`。V2 未新增 pip 依赖，继续使用 Python 标准库、现有 SQLite 和 Telegram Bot API。
