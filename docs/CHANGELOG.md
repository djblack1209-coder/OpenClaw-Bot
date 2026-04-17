# CHANGELOG

> 格式规范: 每条变更必须包含 `领域` + `影响模块` + `关联问题`。详见 `docs/sop/UPDATE_PROTOCOL.md`。
> 领域标签: `backend` | `frontend` | `ai-pool` | `deploy` | `docs` | `infra` | `trading` | `social` | `xianyu`

## 按月查看

- [2026-04 月变更记录](CHANGELOG/2026-04.md) — 最新
- [2026-03 月变更记录](CHANGELOG/2026-03.md)

---

## 最近更新（2026-04）

## 2026-04-17 — CSO 全量安全审计修复 (10项)
> 领域: `backend`, `infra`, `frontend`, `deploy`
> 影响模块: `weekly_report`, `xianyu.py`, `docker-compose.yml`, `Makefile`, `deploy_server.py`, `docker-compose.newapi.yml`, `openclaw-manager-src`, `App.tsx`, `Store/index.tsx`, `.env`
> 关联问题: CSO 安全审计 2026-04-17

### 变更内容

**🔴 CRITICAL 修复 (4项)**
1. **周报导入路径修复**: `weekly_report.py` 中 `from src.content_pipeline import ...` 导入路径错误（模块位于 `src.execution.social.content_pipeline`），导致周报生成必然崩溃。修正为正确路径
2. **闲鱼路由 XianyuBot 幻影导入修复**: `api/routers/xianyu.py` 导入不存在的 `XianyuBot` 类，替换为 `XianyuContextManager` 直接查询 SQLite，消除启动时 ImportError
3. **Docker 资源超配修复**: `docker-compose.yml` Redis 内存限制 512M→128M、OpenClaw 主服务 2G→1G，防止 OOM killer 干掉容器；移除 `internal: true` 网络标记恢复容器互联网访问；新增双网络架构（公网+内网隔离）
4. **Makefile Python 路径修复**: 硬编码 `/usr/bin/python3` 在 macOS/brew 环境下不存在，改为 `which python3 || which python` 自动检测

**🟠 HIGH 修复 (3项)**
5. **部署服务器时序攻击修复**: `deploy_server.py` Webhook 签名验证使用 `==` 字符串比较存在时序攻击漏洞，改为 `hmac.compare_digest()` 常量时间比较
6. **NewAPI Docker 安全加固**: `docker-compose.newapi.yml` 添加 `cap_drop: ALL` + `security_opt: no-new-privileges:true`，最小权限原则
7. **移除未使用依赖**: `openclaw-manager-src` 前端项目移除未使用的 `sucrase` 依赖，减少供应链攻击面

**🟡 MEDIUM 修复 (3项)**
8. **误导注释修复**: `App.tsx` 中注释与实际代码行为不符，修正为准确描述
9. **forwardRef 警告修复**: `Store/index.tsx` 中 `PluginCard` 组件触发 React forwardRef 废弃警告，修复组件定义
10. **.env 文件权限加固**: 所有 `.env` 文件权限设置为 `600`（仅 owner 可读写），防止同机其他用户读取密钥

### 文件变更
- `packages/clawbot/src/execution/weekly_report.py` — 修正 content_pipeline 导入路径
- `packages/clawbot/src/api/routers/xianyu.py` — 替换 XianyuBot 为 XianyuContextManager 直接查询
- `docker-compose.yml` — 资源限制调整 + 网络架构重构 + 移除 internal 标记
- `Makefile` — Python 路径自动检测
- `packages/clawbot/src/deployer/deploy_server.py` — hmac.compare_digest 替换 ==
- `docker-compose.newapi.yml` — 安全加固 cap_drop/no-new-privileges
- `apps/openclaw-manager-src/package.json` — 移除 sucrase 依赖
- `apps/openclaw-manager-src/src/App.tsx` — 修正误导注释
- `apps/openclaw-manager-src/src/components/Store/index.tsx` — 修复 forwardRef 警告
- `config/.env*` — 权限收紧为 600

---

## 2026-04-17 — 全量端到端审计 (Sprint 4 审计)

### backend
- **[修复]** yfinance 价格回退：IBKR 离线时自动通过 yfinance 获取实时报价 `rpc.py`
- **[修复]** portfolio-summary 字段映射：qty→quantity, avg_cost→avg_price `trading.py`
- **[修复]** 速率限制提高至 300 req/min `server.py`
- **[新增]** 闲鱼路由: conversations/qr 端点 `routers/xianyu.py`
- **[新增]** WebSocket 事件类型: NOTIFICATION/SERVICE_CHANGE `schemas.py`
- **[修复]** CI 测试断言修复 (Sortino/TailRatio 兼容 quantstats) `test_risk_var.py`

### frontend
- **[修复]** Portfolio 崩溃：avg_cost/avg_price 字段映射 + .toFixed() 安全兜底
- **[修复]** 总市值自动计算 (后端无 total_market_value 字段时从 positions 聚合)
- **[修复]** Store 安装持久化至 localStorage，移除 window.confirm()
- **[修复]** 闲鱼开关接入 serviceStart/serviceStop 真实 API
- **[修复]** 社媒平台数据映射 (数组→对象, xhs/x 名称)
- **[修复]** 死按钮修复 (设置/AI助手使用/发布反馈)
- **[优化]** MOCK_PLUGINS → CURATED_PLUGINS，Evolution 数据优先
- **[优化]** console.error → createLogger 结构化日志
- **[新增]** Onboarding 向导、ErrorState 组件、useClawbotWS hook
- **[新增]** Markdown h1/h2/h3 标题渲染
- **[优化]** AI 模型标签 "Claude 助手" → "AI 助手"

### infra
- **[构建]** Tauri 重新构建并安装至 /Applications/OpenClaw.app
- **[CI]** GitHub Actions CI 通过 (1339 passed)

---

## [2026-04-17] 后端 API 新增 + 前端真实数据对接 — 从演示数据到可用系统
> 领域: `backend`, `frontend`
> 影响模块: `api/routers/system`, `api/routers/trading`, `api/server`, `api/routers/conversation`, `tauri.ts`, `Home`, `conversationService`
> 关联问题: 桌面 APP 5 个页面需要从模拟数据切换到后端真实数据
### 变更内容
- **后端新增 4 组 API 端点** — `GET /api/v1/system/daily-brief`（今日简报聚合 metrics + 模块状态）、`GET/POST /api/v1/system/notifications`（通知列表+标记已读+全部已读）、`GET /api/v1/trading/portfolio-summary`（持仓聚合摘要）、`GET /api/v1/system/services`（服务运行状态检测）
- **挂载 Conversation 路由** — `router_conversation` 之前已实现（SSE 流式对话 333 行），但未在 server.py 注册，导致 /api/v1/conversation/* 端点全部 404
- **前端 tauri.ts 新增全部 API 封装** — dailyBrief/notifications/markNotificationRead/markAllNotificationsRead/portfolioSummary/services/serviceStatus + conversation 完整封装（sessions/create/get/delete/send）
- **Home 首页对接真实数据** — 模拟通知替换为 `api.notifications()` + 首页摘要并行请求加入 `api.dailyBrief()`
- **conversationService SSE 修复** — 流式请求从裸 fetch 改为 clawbotFetch（携带 API Token），修复未授权错误
- **回归测试**: 1339 passed, 2 skipped, 0 failures ✓
### 文件变更
- `packages/clawbot/src/api/server.py` — 新增 router_conversation 导入和挂载（2处）
- `packages/clawbot/src/api/routers/system.py` — 31行→~280行，新增 daily-brief/notifications/services 三组端点
- `packages/clawbot/src/api/routers/trading.py` — 151行→~240行，新增 portfolio-summary 端点
- `apps/openclaw-manager-src/src/lib/tauri.ts` — 719行→~820行，新增所有 API 封装函数
- `apps/openclaw-manager-src/src/components/Home/index.tsx` — 模拟通知→真实 API + dailyBrief 数据对接
- `apps/openclaw-manager-src/src/services/conversationService.ts` — SSE fetch→clawbotFetch + 移除废弃 API_BASE

---


...

查看完整记录请访问 [2026-04.md](CHANGELOG/2026-04.md)
