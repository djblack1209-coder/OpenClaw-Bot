# MODULE_REGISTRY — OpenClaw Bot 模块注册表

> 最后更新: 2026-04-19 | 新增 3 个社媒适配器模块 (277→280)

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

## 更新模块 (2026-04-08)

### newapi.py — New-API 管理代理路由

| 属性 | 值 |
|------|-----|
| 路径 | `packages/clawbot/src/api/routers/newapi.py` |
| 行数 | ~219 |
| 导入方 | `api/routers/__init__.py` → `api/server.py` |
| 依赖 | `httpx`, `fastapi`, `pydantic` |

**Public API (HTTP 端点):**
- `GET /api/v1/newapi/status` — 检查 New-API 服务状态
- `GET /api/v1/newapi/channels` — 获取通道列表
- `GET /api/v1/newapi/tokens` — 获取令牌列表
- `POST /api/v1/newapi/channels` — 创建新通道
- `PUT /api/v1/newapi/channels/{id}` — 更新通道
- `DELETE /api/v1/newapi/channels/{id}` — 删除通道
- `POST /api/v1/newapi/channels/{id}/status` — 切换通道启用/禁用
- `DELETE /api/v1/newapi/tokens/{id}` — 删除令牌

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
| quote_cache.py | `src/quote_cache.py` | 220 | diskcache 行情缓存 |
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

> 详细设计文档: `docs/specs/2026-03-23-upgrade-opportunities-design.md`

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


