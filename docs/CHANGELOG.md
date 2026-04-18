# CHANGELOG

> 格式规范: 每条变更必须包含 `领域` + `影响模块` + `关联问题`。详见 `docs/sop/UPDATE_PROTOCOL.md`。
> 领域标签: `backend` | `frontend` | `ai-pool` | `deploy` | `docs` | `infra` | `trading` | `social` | `xianyu`

## 按月查看

- [2026-04 月变更记录](CHANGELOG/2026-04.md) — 最新
- [2026-03 月变更记录](CHANGELOG/2026-03.md)

---

## 最近更新（2026-04）

## 2026-04-18 — T2+T3: 意图识别准确率提升 + 风控系统 BUG 修复
> 领域: `backend`, `trading`
> 影响模块: `chinese_nlp_mixin`, `intent_parser`, `freqtrade_bridge`, `brain_exec_invest`, `risk_manager`
> 关联问题: 四阶段方法论 T2/T3, HI-520, HI-521, HI-522~524

### 变更内容

**T2: 意图识别准确率提升**
1. **正则层扩充**: 新增"走势"→chart、"帮我查/查一下/看下"→ta、autotrader_status 模式
2. **购物消歧修复**: 排除词 `手` 改为 `\d+手` — 修复"入手"中"手"被误杀导致"入手苹果"无法触发购物
3. **dispatch_map 补充**: autotrader_start/stop/status 三个命令补入分发映射
4. **LLM prompt 优化**: 补全 11 类型 + 5 条 few-shot 示例，改善 LLM 降级分类准确率
5. **购物排除模式扩展**: 新增 AMZN/META/BTC/比特币/茅台/特斯拉/英伟达等金融标的排除
6. **测试覆盖提升**: 新增 12 个测试用例覆盖走势/查询/autotrader/购物消歧场景

**T3: 风控系统 BUG 修复**
7. **freqtrade_bridge 修复 (HI-520)**: `confirm_trade_entry()` 传 dict 改为关键字参数 + `.get("approved")` 改为 `.approved` 属性 + 补传默认 3% 止损
8. **brain_exec_invest 修复 (HI-521)**: `_exec_risk_check()` 两处 `check_trade()` 调用补传 `stop_loss=entry_price*0.97`，修复 StopLossValidator 拒绝所有 BUY 交易的问题
9. **架构问题登记 (HI-522~524)**: check_trade() 共享状态竞态、SELL 方向风控缺失、新账户 VaR 空白 — 登记为技术债

### 文件变更
- `packages/clawbot/src/bot/chinese_nlp_mixin.py` — 正则扩充 + 购物消歧修复 + dispatch_map 补充
- `packages/clawbot/src/core/intent_parser.py` — LLM prompt 优化（11类型+few-shot）+ 购物排除模式扩展
- `packages/clawbot/tests/test_message_mixin.py` — 新增 12 个测试用例
- `packages/clawbot/src/freqtrade_bridge.py` — 修复 confirm_trade_entry() API 不匹配
- `packages/clawbot/src/core/brain_exec_invest.py` — 补传 stop_loss 参数修复 StopLossValidator 误拒
- `docs/status/HEALTH.md` — 新增 HI-520~524

---

## 2026-04-18 — T4+T5: QuantStats 报告活化 + LiteLLM 配置外化
> 领域: `backend`, `ai-pool`
> 影响模块: `backtester_vbt`, `cmd_trading_mixin`, `risk_var`, `litellm_router`, `llm_routing_config`, `llm_routing.json`
> 关联问题: 四阶段方法论 T4/T5

### 变更内容

**T4: QuantStats HTML 报告活化**
1. **generate_quantstats_report() 重构**: 从孤儿方法升级为实际可用功能 — 支持全8策略信号生成 + SPY 基准对比 + 接受任意 returns Series
2. **自研引擎接入**: 在 `/backtest` 单股回测路径中新增 `_send_quantstats_report()` — 从 PerformanceReport.daily_returns 生成 HTML tearsheet 并通过 Telegram send_document() 发送
3. **死代码清理**: `risk_var.py` 中 calc_var()/calc_cvar() 的 QuantStats 调用被 numpy 覆盖的死代码已移除

**T5: LiteLLM 配置外化（JSON 为单一真相源）**
4. **Router 参数从 JSON 读取**: `initialize()` 从 JSON `router_config` 字段读取 num_retries/timeout/cooldown 等参数，替代硬编码常量
5. **BOT_MODEL_FAMILY 从 JSON 加载**: 新增 `_load_bot_model_family()` 从 JSON `bot_model_family` 加载 Bot→模型族映射
6. **MODEL_RANKING 移入 JSON**: 50+ 模型评分集中到 JSON `model_ranking` 字段，Python 端动态加载
7. **smart_route 映射移入 JSON**: `_smart_route()` 的 model→family 映射移入 JSON `smart_route_model_to_family` 字段
8. **配置加载器扩展**: `llm_routing_config.py` 新增 `get_model_ranking()` / `get_smart_route_mapping()`

### 文件变更
- `packages/clawbot/src/modules/investment/backtester_vbt.py` — 重构 generate_quantstats_report() + 新增 _get_strategy_signals()
- `packages/clawbot/src/bot/cmd_trading_mixin.py` — 新增 _send_quantstats_report() + 自研引擎接入
- `packages/clawbot/src/risk_var.py` — 清理 calc_var()/calc_cvar() 死代码
- `packages/clawbot/src/litellm_router.py` — Router 参数/BOT_MODEL_FAMILY/MODEL_RANKING/smart_route 从 JSON 加载
- `packages/clawbot/src/llm_routing_config.py` — 新增 get_model_ranking()/get_smart_route_mapping()
- `packages/clawbot/config/llm_routing.json` — 新增 model_ranking/smart_route_model_to_family + 修正 bot_model_family

---

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
