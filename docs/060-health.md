# HEALTH — 系统健康状态

> 最后更新: 2026-05-03

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
| Frist-API | ✅ HTTPS Quick Tunnel 和裸 IP 测试端口均已恢复；本地链路测试和公网冒烟通过，用户端已补齐弹窗登录注册、失败/成功反馈、API Key 创建反馈、连通性刷新不跳教程、渠道连通性聚合展示、价格管理、官方模型命名清洗、Claude Code/Codex 跨模型家族一键导入、Claude 第三方推理真实菜单流程图、Codex 导入 Claude 模型流程图、Codex 默认 Playwright/Superpowers/open-computer-use MCP、无网页 mock 数据兜底、默认最强模型导出、数据看板、模型广场、一次性管理员身份码、图片生成网关、OpenCode `/openai/chat/completions` 兼容路由、Chat Completions 到 Responses 降级、上游信息清洗、五客户端导入、日卡/小时卡轮转、会话粘滞、流式透传和公开模式硬门槛；本轮 Frist-API `npm test` 为 103/103 通过，已补齐广场 `5.5`/`image2` 别名、图片模型 `/images/generations` 补号探测、广场一键实测状态、CPA JSON/chong 备用渠道人工风险入口，以及上游禁用后的库存落盘下线；腾讯云 `/opt/frist-api` 部署状态为 `frist-api-server` healthy，公网冒烟通过；公网真实上游当前返回 `API key is disabled`，需补入新可用上游后才能恢复 `gpt-5.5` / `gpt-image-2` 真生成；商业化自动运营仍需支付回调、固定域名、数据库、备份和监控 |
| 微信命令 | ✅ 27/27 可用 (25✅ 2⚠️数据空) |
| Ollama 内存 | ✅ 151MB (原9.3GB) |
| 日志目录 | ✅ 784KB (已清理本地日志) |
| 文档治理 | ✅ 主项目 docs 压缩到 19 个 Markdown，历史截图/旧审计/散落设计报告已清理 |
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

---

## 技术债

| ID | 分类 | 描述 | 优先级 |
|----|------|------|--------|
| TD-001 | TECH_DEBT | CookieCloud 服务器 127.0.0.1:8088 离线 | 🟡 |
| TD-002 | ARCH_LIMIT | 部分微信编号命令(~25个)无真实API,走LLM通用回复 | 🟡 |
| TD-003 | TECH_DEBT | CLICommandsMixin (/cli) 预备代码未注册 | 🔵 |
| TD-004 | TECH_DEBT | 源码仍有 63 个历史 `pass` 语句，多数位于可选依赖降级、异常兜底和测试辅助路径，需按模块分批审查后清理 | 🔵 |
| TD-005 | TECH_DEBT | `ruff` 工具链已补齐，但 `make lint` 暴露 547 个历史 lint 问题，主要为 UP031(192)、B904(88)、RUF013(62)、E402(49)；已完成 monitor 路由 3 项和 API 边界异常链路 5 项机械清理 | 🟡 |
| TD-006 | ARCH_LIMIT | Frist-API 当前仍使用 JSON 运行数据；已加公开模式配置硬门槛和轻量验证码，公开扩大前仍需迁移数据库、SMTP/找回密码、Turnstile、管理员 2FA、真实支付回调和探测预算队列 | 🟠 |
| TD-007 | INFRA | Frist-API 当前 HTTPS 入口使用 Cloudflare Quick Tunnel，适合外部实测但不是长期品牌域名；需绑定自有域名到 Cloudflare Tunnel 或修复 DNS/ACME 直签后切换为固定入口 | 🟡 |
| TD-008 | ARCH_LIMIT | Frist-API 模型目录和默认最强模型仍有内置排序兜底；生产应改为上游 `/v1/models`、官方模型目录校验、后台可审计排序共同决定，避免硬编码模型名误导客户 | 🟠 |
