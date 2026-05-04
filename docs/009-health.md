# 系统健康状态

> 合并自原 060-health.md + 063-learnings.md + 064-feature-requests.md

---

## 一、当前状态与已知问题

# HEALTH — 系统健康状态

> 最后更新: 2026-05-04

---

## 当前系统状态: 🟡 质量优化和冗余清理完成, 待外部密钥轮换

| 指标 | 值 |
|------|------|
| 后端进程 | ✅ 运行中 (PID 自动重启) |
| 7 Bot 在线 | ✅ 7/7 |
| IBKR | ✅ 已连接 (DUP113460) |
| API 池 | ✅ 139/142 活跃源 |
| 闲鱼客服 | ✅ 自动回复活跃 |
| 社媒自动驾驶 | ✅ 运行中 |
| 测试 | ✅ 1488 passed, 2 skipped, 0 failed |
| Frist-API | ✅ HTTPS Quick Tunnel 和裸 IP 测试端口均已恢复；本地链路测试和公网冒烟通过，用户端已补齐弹窗登录注册、失败/成功反馈、API Key 创建反馈、连通性刷新不跳教程、渠道连通性聚合展示、价格管理、官方模型命名清洗、Claude Code/Codex 跨模型家族一键导入、Claude 第三方推理真实菜单流程图、Codex 导入 Claude 模型流程图、Codex 默认 Playwright/Superpowers/open-computer-use MCP、无网页 mock 数据兜底、默认最强模型导出、数据看板、模型广场、一次性管理员身份码、图片生成网关、OpenCode `/openai/chat/completions` 兼容路由、Chat Completions 到 Responses 降级、上游信息清洗、五客户端导入、日卡/小时卡轮转、会话粘滞、流式透传、公开模式硬门槛和自定义余额邮件预警；本轮已补齐授权余额站根地址自动切 `/v1`、2xx 非 JSON 响应拦截、无域名 HTTP 验收开关透传、工作台式首页、广场轻量 PNG 生图参数、余额预警 SMTP 配置、完整 Workbench 外壳、使用记录/订阅/兑换/邀请/资料页面、美元计价展示和 Codex + DeepSeek 官方端点配置；用户端和管理端已接入 Refero Hyperstudio 风格深色工作台 UI，补齐骨架加载、生产空态、当前页无障碍标记和图表可访问标签；模型广场/测试台已参考 New-API 控制台逻辑重构为模型浏览器、搜索/分组、端点/计费/状态诊断和快捷测试，后端空数据时保留未检测模型模板，避免误以为模型缺失；安全审计已将密码哈希迁移到 PBKDF2-SHA256 并兼容旧 SHA-256 登录升级，公网 HTTPS Session Cookie 自动加 `Secure`，动态 HTML 渲染补齐转义；本轮继续补齐注册验证码邮件、忘记密码、微信 Native/支付宝当面付真实回调验签和幂等入账、runtime 用户 Key/上游 Key AES-GCM 加密、New-API 迁移 dry-run；DeepSeek 官方 live 文档已重新核对，新导入默认模型改为 `deepseek-v4-flash`，并保留 `deepseek-v4-pro`、`deepseek-chat`、`deepseek-reasoner` 兼容；CPA JSON/chong 仍只作为人工风险审核备用入口；腾讯云 `/opt/frist-api` 已部署 DeepSeek v4 默认模型改动，远端备份为 `backups/frist-api-app-20260504-104527-before-deepseek-v4.tgz`，`frist-api-server` 为 healthy，公网首页 200、看板 200、模型目录包含 `deepseek-v4-flash`、未授权 `/v1/models` 为 401；腾讯云到 Gmail SMTP IPv6 发信链路已实测可用，Node 连接已补 DNS 地址轮询兜底，Compose 已透传 SMTP 环境变量；本地 `npm test` 为 123/123 通过；旧公网真实上游已禁用，新授权余额站 `/v1` 已接入；New-API 已作为 submodule 固定到 GitHub latest release `v1.0.0-rc.2`，`docker-compose.newapi.yml` 已同步 `calciumion/new-api:v1.0.0-rc.2`，`make new-api-check` / `make new-api-sync` 已落地，GitHub Actions 已新增每日定时同步 PR；Frist-API 已新增服务端 New-API 桥接层，可由 New-API 接管看板、API Key、日志、兑换、订阅/充值/邀请读取和可选 `/v1` 网关代理，同时保留 Workbench UI、CC Switch/Codex/DeepSeek 配置、余额预警、补号助手和本地 JSON 兜底；商业化自动运营仍需固定品牌域名、商户平台开户注册、数据库备份监控和历史数据迁移 |
| 微信命令 | ✅ 27/27 可用 (25✅ 2⚠️数据空) |
| Ollama 内存 | ✅ 151MB (原9.3GB) |
| 日志目录 | ✅ 784KB (已清理本地日志) |
| 文档治理 | ✅ 主项目 docs 从散落状态统一归集到 43 个编号 Markdown，扁平化无子目录，历史截图/旧审计/散落设计报告/冗余打包文档已清理 |
| 公开仓库安全 | 🟡 Git 历史已重写并通过本地扫描, 仍需轮换曾暴露过的外部密钥 |

---

## 已知问题

### 🔴 阻塞 / 🟠 重要

| ID | 分类 | 描述 | 发现日期 | 状态 |
|----|------|------|----------|------|
| HI-817 | SECURITY | 公开 Git 历史曾提交 `.openclaw/openclaw.json*`、`.openclaw/devices/paired.json` 和数据库文件；已重写历史并通过本地 gitleaks/trufflehog 扫描 | 2026-04-28 | 🟠 待轮换密钥 + force-push 后复扫 |
| HI-818 | SECURITY | 本机 ignored `.env` 与浏览器 profile 日志含真实 API token；已确认未进入当前跟踪文件, 但涉及 token 应按泄露预案轮换 | 2026-04-28 | 🟠 待轮换 |

### 🟡 一般

| ID | 分类 | 描述 | 发现日期 | 状态 |
|----|------|------|----------|------|
| HI-802 | BUG | /monitor/news 首次调用可能超时 (RSS 20源+AI摘要) — 缓存热后正常 | 2026-04-26 | 🟡 已知 |
| HI-804 | BUG | G4F 服务 uptime 显示 0m — 进程检测关键词可能不匹配 | 2026-04-26 | 🟡 低优先 |
| HI-812 | BUG | 微信 iLink bot token 在平台侧失效(errcode=-14)，需在 iLink 后台重新扫码获取新 token | 2026-04-26 | 🟠 待操作 |

### 已修复 (本轮)

| ID | 分类 | 描述 | 修复日期 |
|----|------|------|----------|
| HI-805 | BUG | 金融指数全零 — yfinance Tickers 批量请求失败无错误提示 | 2026-04-26 |
| HI-806 | BUG | IBKR accountSummary "event loop already running" — 同步调异步 | 2026-04-26 |
| HI-807 | BUG | /monitor/extended 超时 54s+ — 外部API串行+重复RSS拉取 | 2026-04-26 |
| HI-808 | PERF | 日志文件每10秒生成一个,累积1800+文件168MB — loguru配置错误 | 2026-04-26 |
| HI-809 | UX | 微信欢迎消息不完整,只展示8个命令 | 2026-04-26 |
| HI-810 | BUG | 微信 cmd_iorders(233) 映射错误端点 | 2026-04-26 |
| HI-811 | BUG | 微信 cmd_dashboard 不可达(无编号映射) | 2026-04-26 |
| HI-813 | BUG | cmd_status(102) 映射路径错误(/system/status→/status) | 2026-04-26 |
| HI-814 | UX | 12个有API的微信命令未映射,走LLM兜底(300/407/500等) | 2026-04-26 |
| HI-815 | UX | 热点话题(300)只显示"[10项]",全球情报(407)嵌套dict未展开 | 2026-04-26 |
| HI-801 | PERF | Ollama 模型启动后常驻内存 9.1GB — 已配置 KEEP_ALIVE=5m 自动卸载 | 2026-04-26 |
| HI-803 | TECH_DEBT | 微信命令路由同步到腾讯云 wechat_receiver.py | 2026-04-26 |
| HI-816 | INFRA | 创建 Makefile + BUILD_GUIDE.md 构建规范化 | 2026-04-27 |
| HI-819 | INFRA | Git 密钥扫描 + 本地冗余清理：移除可重建缓存约4.4GB、删除含 token 痕迹的浏览器临时日志、补充忽略规则 | 2026-04-28 |
| HI-820 | SECURITY | Git 全历史重写完成：移除敏感历史路径、数据库/依赖/构建产物、扫描器样例噪音；清理后 gitleaks/trufflehog 历史扫描 0 命中 | 2026-04-28 |
| HI-821 | TECH_DEBT | Makefile 测试入口优先使用系统 Python 导致 pytest 缺失；API RPC 价格补齐和社媒 Cookie 检测存在重复实现 | 2026-05-01 |
| HI-822 | TECH_DEBT | AGENTS/SOP/索引仍指向历史大写文档路径；部分抽象类和聚合类保留空占位语句 | 2026-05-01 |
| HI-823 | INFRA | `make lint` 依赖 ruff 但开发依赖未声明；已补齐 requirements-dev 与依赖注册表 | 2026-05-01 |
| HI-824 | BUG | Frist-API 轻量后端静态首页因绝对路径归一化返回 403；已补回归测试并修复为同域 200 | 2026-05-01 |
| HI-825 | SECURITY | Frist-API 公开充值按钮会直接给用户加余额；已改为待处理充值单 + 管理端人工确认入账，生产默认关闭演示充值 | 2026-05-01 |
| HI-826 | TECH_DEBT | Frist-API 补号缺少直连/代理择优、上游不支持模型列表时的 fallback 探测和按真实 usage 扣费；已补齐轻量实现并纳入回归测试 | 2026-05-01 |
| HI-827 | ARCH_LIMIT | Frist-API 网关缺少公开可用级会话粘滞、真实流式透传和生产配置硬门槛；已补齐并纳入回归测试 | 2026-05-01 |
| HI-828 | UX | Frist-API 用户端信息密度过高、左侧导航/分组冗余、首屏存在演示数据闪现；已移除侧栏和 sticky，注册登录收进右上角，首屏只保留余额、模型消耗、连通性和导入入口，游客页不再显示演示消耗 | 2026-05-02 |
| HI-829 | SECURITY | Frist-API 公开管理页不应暴露给普通用户，注册登录需要基础防刷；已加入隐藏管理入口码、验证码挑战、认证限流和公网冒烟检查 | 2026-05-02 |
| HI-830 | UX | Frist-API 用户端缺少模型测试广场、数据看板、模型定价目录和配置教程；已补齐广场对话/生图、模型消耗分布、服务可用性、模型广场和 Codex/Claude/OpenClaw 一键配置教程 | 2026-05-02 |
| HI-831 | SECURITY | Frist-API 管理员升级不应依赖用户把账号密码交给开发者；已改为登录后输入一次性管理员身份码，成功后当前账号升级且身份码作废 | 2026-05-02 |
| HI-832 | UX | Frist-API 用户端注册登录、页面返回、广场消息管理、API Key 改名/删除、CC Switch 全模型导出、官方 Pro 模型优先级和 OpenCode/Hermes/Harmes 教程完整度不足；已补齐用户侧闭环并纳入回归测试 | 2026-05-02 |
| HI-833 | UX | Frist-API Codex/OpenCode 导出后用户无法在页面确认完整模型清单，外部 GUI 若只读单一字段可能只显示默认模型；已在 CC Switch 页可见化默认模型/全模型列表，并补齐多套模型列表兼容字段 | 2026-05-02 |
| HI-834 | INFRA | Frist-API 裸 IP 测试入口拒绝连接；根因是容器仅本地绑定且 Nginx 未监听测试端口，同时服务器代码落后于本地 open4；已同步代码、更新 Nginx 监听并通过公网冒烟 | 2026-05-02 |
| HI-835 | UX | Frist-API 首屏主卡过大、品牌标识弱化、快捷入口过于等分；已恢复黑白红品牌标识，并改为主控台、右侧说明、核心指标和不对称任务轨道 | 2026-05-02 |
| HI-836 | UX/ARCH_LIMIT | CC Switch 跨模型家族导入存在断点：ChatGPT 模型不能直接导入 Claude Code，Claude 模型导入 Codex 缺少 Responses 降级链路；已补齐 Claude Code Anthropic Messages 配置、Codex Responses fallback、开发者模式引导和支付最后一公里手册 | 2026-05-02 |
| HI-837 | UX | CC Switch 跨模型导入教程仍偏文字化，用户不知道 Claude 左上角菜单、第三方推理输入框和 Codex 配置字段在哪里；已补两张仿真实操流程图、编号步骤、字段对照和上下文切换验收提示 | 2026-05-02 |
| HI-838 | UX/BUG | Frist-API 登录、创建 Key、连通性刷新、模型命名、mock 数据和价格管理存在实测断点；已补明确反馈、刷新留在当前页、渠道聚合状态、官方模型名清洗、真实数据空态、后台价格 JSON 管理和 60 刀测试额度入账 | 2026-05-02 |
| HI-839 | UX/BUG | Frist-API 外网实测发现 CC Switch 一键导入入口藏在长教程后、广场 `gpt-5.5` Chat Completions 返回上游 `Route /openai/chat/completions not found`、OpenCode 前缀路由未接住、OpenCode 导入模型清单缺 `gpt-5.4` / `gpt-5.3-codex`，桌面端实际导入后 `config.models` 仍只写默认模型；已前置一键导入主操作、补 OpenCode `/openai/*` 兼容路由、Chat Completions 缺失时降级 Responses，并按 OpenCode/CC Switch 真实配置格式补完整模型映射 | 2026-05-02 |
| HI-840 | TECH_DEBT | 主项目文档、历史截图、旧审计报告、本地构建缓存和服务器临时产物过多；已压缩 docs 到 19 个 Markdown，本地仓库体积从约 2.4GB 降到约 196MB，并分层清理服务器日志、缓存、临时文件和 Docker 非运行对象 | 2026-05-03 |
| HI-841 | UX/BUG | Frist-API 广场和补号对 `5.5`、`image2` 这类商业别名不够稳，图片库存严格探测可能误走聊天接口；已补别名清洗、图片模型 `/images/generations` 探测、广场一键实测状态和回归测试 | 2026-05-03 |
| HI-842 | SECURITY/ARCH_LIMIT | Frist-API 需要把 CPA JSON 和 chong 作为备用渠道人工管理，但不能默认进入生产路由；已增加渠道类型、风险状态、人工确认和隔离态路由过滤 | 2026-05-03 |
| HI-843 | BUG | 腾讯云公网实测发现上游返回 `API key is disabled` 时，网关 503 路径会回滚库存状态，导致广场继续展示失效模型；已改为保留失败状态并让模型清单自动下线 | 2026-05-03 |
| HI-844 | BUG/UX | 授权余额站上游根地址会返回网站 HTML 壳，旧补号探测可能把 2xx HTML 当成健康或额度错误；已改为根地址失败后自动尝试 `/v1`、校验 OpenAI 兼容 JSON，并把首页改为控制台工作台布局 | 2026-05-03 |
| HI-845 | UX/AI_POOL | 新余额站 `gpt-image-2` 真请求耗时 40-110 秒，广场默认图片参数过重容易放大公网等待；已改为轻量 PNG 请求并完成裸 IP 公网图片真测 | 2026-05-03 |
| HI-858 | UX | Frist-API Workbench 壳不足：侧栏品牌与顶部 Logo 重复、仪表盘指标/图表/日志不足、API 管理缺搜索和端点展示、缺使用记录/订阅/兑换/邀请/资料页面、CC Switch 需覆盖 Gemini/OpenCode/OpenClaw/Hermes/Harmes 和 Codex DeepSeek；已完成 UI 外壳、美元展示和回归测试 | 2026-05-03 |
| HI-859 | ARCH_LIMIT | Frist-API 已接入服务端 New-API 业务桥接层和每日 GitHub Actions 同步 PR；New-API 可接管看板、Token、日志、兑换、订阅、充值配置、邀请返利和可选网关代理。仍保留 Frist-API 自研 UI、CC Switch/Codex/DeepSeek 配置、补号助手、余额预警和 JSON 兜底；完整切换还需要历史用户/余额/Key/订单迁移和生产 New-API 初始化 | 2026-05-03 |
| HI-848 | UX | Frist-API 用户无法按自己的心理安全线设置余额提醒；已新增账单页自定义阈值、收件邮箱、测试邮件和扣费跨阈值一次性提醒 | 2026-05-03 |
| HI-849 | INFRA | 本机到 Gmail SMTP 异常；腾讯云实测 IPv6 SMTP TLS 与真实发信可用，IPv4 465 超时；已补 Node SMTP DNS 地址轮询和 `FRIST_API_SMTP_FAMILY` 配置 | 2026-05-03 |
| HI-855 | SECURITY/UX | Frist-API 验证码原为简单算术题且登录也强制填写；已改为仅注册需要多题型挑战、单题错误次数限制，登录保留频率限制但不再要求验证码 | 2026-05-03 |
| HI-851 | SECURITY | Frist-API 密码哈希使用 SHA-256（GPU 友好）；已改为 PBKDF2-SHA256 新格式，旧 SHA-256 用户登录成功后自动升级 | 2026-05-04 |
| HI-852 | SECURITY | Frist-API Session Cookie 缺少 `Secure` 标记；已在 HTTPS 公网网关或 `x-forwarded-proto=https` 下自动加 `Secure` | 2026-05-04 |
| HI-860 | SECURITY | Frist-API 用户端和管理端部分动态 `innerHTML` 字段未统一转义；已补齐 API Key 属性、充值/导入按钮、管理端摘要/审计日志等转义并加回归 | 2026-05-04 |
| HI-861 | AI_POOL/UX | Frist-API Codex DeepSeek 导入仍默认旧 `deepseek-chat`，与 DeepSeek 官方当前 v4 模型文档不一致；已将新导入默认模型改为 `deepseek-v4-flash`，补 `deepseek-v4-pro` 并保留旧模型兼容 | 2026-05-04 |
| HI-862 | UX | Frist-API 后端不可用时用户只看到顶部错误提示，不知道如何恢复；已在工作台增加离线恢复条和一键重新连接入口 | 2026-05-04 |
| HI-850 | SECURITY | Frist-API runtime.json 明文存储用户 fk-live Key 和上游 rawKey；已新增 AES-256-GCM 字段加密，兼容旧明文读取并在保存时迁移 | 2026-05-04 |
| HI-853 | UX | Frist-API 无"忘记密码"功能，用户丢失密码后无法自助恢复；已新增 SMTP 重置验证码和确认改密接口 | 2026-05-04 |
| HI-854 | UX | Frist-API 前端服务不可用时静默降级无重试入口，用户看不到明确恢复指引 | 2026-05-03 |
| HI-856 | ARCH_LIMIT | Frist-API server.js 单文件 4432 行，账号/网关/邮件/管理全耦合在一个模块 | 2026-05-03 |
| HI-857 | ARCH_LIMIT | Frist-API 内存态 captcha/rateLimit 在进程重启或水平扩展时丢失 | 2026-05-03 |
| HI-863 | INFRA | Frist-API 长期入口仍缺固定品牌域名；免费域名已实测，`sslip.io` 在腾讯 DNSPod 侧被拦截，当前过渡入口切到 `frist-api.101-43-41-96.nip.io`；Let’s Encrypt 访问 ACME challenge 被重置，HTTPS 仍需自有域名或 Cloudflare Tunnel 闭环 | 2026-05-04 |

---

## 技术债

| ID | 分类 | 描述 | 优先级 |
|----|------|------|--------|
| TD-001 | TECH_DEBT | CookieCloud 服务器 127.0.0.1:8088 离线 | 🟡 |
| TD-002 | ARCH_LIMIT | 部分微信编号命令(~25个)无真实API,走LLM通用回复 | 🟡 |
| TD-003 | TECH_DEBT | CLICommandsMixin (/cli) 预备代码未注册 | 🔵 |
| TD-004 | TECH_DEBT | 源码仍有 63 个历史 `pass` 语句，多数位于可选依赖降级、异常兜底和测试辅助路径，需按模块分批审查后清理 | 🔵 |
| TD-005 | TECH_DEBT | `ruff` 工具链已补齐，但 `make lint` 暴露 547 个历史 lint 问题，主要为 UP031(192)、B904(88)、RUF013(62)、E402(49)；已完成 monitor 路由 3 项和 API 边界异常链路 5 项机械清理 | 🟡 |
| TD-006 | ARCH_LIMIT | Frist-API 当前仍使用 JSON 运行数据；已加公开模式配置硬门槛、轻量验证码和余额预警 SMTP 邮件，公开扩大前仍需迁移数据库、注册验证/找回密码 SMTP、Turnstile、管理员 2FA、真实支付回调和探测预算队列 | 🟠 |
| TD-007 | INFRA | Frist-API 当前 HTTPS 入口使用 Cloudflare Quick Tunnel，适合外部实测但不是长期品牌域名；需绑定自有域名到 Cloudflare Tunnel 或修复 DNS/ACME 直签后切换为固定入口 | 🟡 |
| TD-008 | ARCH_LIMIT | Frist-API 模型目录和默认最强模型仍有内置排序兜底；生产应改为上游 `/v1/models`、官方模型目录校验、后台可审计排序共同决定，避免硬编码模型名误导客户 | 🟠 |
| TD-009 | TECH_DEBT | Frist-API `ccswitch://` 导入链接依赖用户已安装 CC Switch，浏览器无协议处理器时降级体验为空 | 🟡 |
| TD-010 | SECURITY | Frist-API 管理 API 失败认证不生成审计事件，暴力破解无法检测 | 🟡 |
| TD-011 | ARCH_LIMIT | Frist-API 无优雅关闭（SIGTERM/SIGINT），连接直接断开对网关流式请求不友好 | 🟡 |
| TD-012 | ARCH_LIMIT | Frist-API 文件写入失败被 `catch(() => {})` 静默吞掉，store 破损后无告警 | 🔵 |

---

## 二、自学习经验库


记录系统运行中积累的经验、最佳实践和优化心得。

## 格式

```
## [YYYY-MM-DD] 主题

**背景**: 场景描述
**发现**: 关键洞察
**应用**: 如何应用到实际工作中
```

---

## [2026-03-18] 系统全面优化完成

**背景**: 对 OpenClaw Bot 进行全面功能完善

**完成项目**:
1. 集成优化报告到 multi_main.py（Prometheus 指标、分层上下文、策略引擎、告警系统）
2. 交易记忆自动写入机制（TradingMemoryBridge 挂载到 journal）
3. 修复类型标注问题（execution_hub 4个bug、broker_bridge TYPE_CHECKING）
4. 社交媒体浏览器发布适配器（Playwright 自动发布 X/小红书）
5. 任务可观测性增强（TaskObserver 跟踪质量/成本/检索命中率）
6. 自学习系统启用（.learnings 文件初始化）

**关键洞察**:
- 交易系统虽然在跑，但记忆为空导致"失忆"决策 → 自动桥接解决
- 社交发布链条在最后一步断了 → Playwright 补上自动化
- 可观测性不足 → TaskObserver 按任务类型跟踪成本和质量
- 类型错误大多是 decompiled 文件的副作用，修复实际 bug 即可

**应用**:
- 所有关键业务流程都应有记忆沉淀机制
- 自动化链条要端到端完整，不能在最后一步依赖人工
- 可观测性要细化到任务级别，才能优化成本和质量

---

## 三、功能需求跟踪


记录用户提出的功能需求、改进建议和待实现特性。

## 格式

```
## [YYYY-MM-DD] 功能名称

**需求**: 用户需求描述
**优先级**: High/Medium/Low
**实现思路**: 技术方案概要
**状态**: Pending/In Progress/Done
```

---

## [2026-03-18] 初始化

功能需求跟踪已启用。后续需求将记录到此文件。
