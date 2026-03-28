# MODULE_REGISTRY — OpenClaw Bot 模块注册表

> 最后更新: 2026-03-29 | R22 新增: risk_config/trading_memory_bridge/broker_selector + cmd_basic子包拆分

---

## 0. R22 架构重构新增模块

以下模块在 R22 代码架构重构中从超长文件提取而来。

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
| 文件数 | 8 (含 __init__.py) |
| 总行数 | ~1358 (原 cmd_basic_mixin.py 拆分) |
| 导入方 | multi_bot (通过 cmd_basic_mixin.py 转发) |

**子模块:**
- `help_mixin.py` — 帮助菜单和新用户引导 (cmd_start, handle_help_callback)
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
| globals.py | `src/bot/globals.py` | 300 | 全局共享对象 + DATA_DIR + SiliconFlow SSOT |
| api_mixin.py | `src/bot/api_mixin.py` | 371 | LLM API 调用 (流式/非流式) |
| rate_limiter.py | `src/bot/rate_limiter.py` | 243 | 消息频率限制 + Token 预算 |
| sau_bridge.py | `src/sau_bridge.py` | 175 | 社媒发布桥接层 — CLI 调用 social-auto-upload (抖音/B站/小红书/快手) |
| message_mixin.py | `src/bot/message_mixin.py` | 1128 | 消息处理 + 流式输出 + 链式工作流 (从1914行拆分) |
| chinese_nlp_mixin.py | `src/bot/chinese_nlp_mixin.py` | 565 | 中文NLP命令匹配(模糊容错) + ticker映射 + 噪音清洗 + "你是不是想说"建议 |
| ocr_mixin.py | `src/bot/ocr_mixin.py` | 325 | 图片/文档OCR处理 (从message_mixin提取) |
| chat_router.py | `src/chat_router.py` | ~1200 | 群聊路由 + 讨论管理 + 优先级队列 |
| litellm_router.py | `src/litellm_router.py` | ~830 | LiteLLM 统一路由: 15+ provider, 50+ deployment, 模型强度排名, 10条付费硅基Key池, validate_keys() 健康验证 |
| smart_memory.py | `src/smart_memory.py` | ~800 | mem0 集成 + 用户画像 |
| shared_memory.py | `src/shared_memory.py` | 1111 | ✅ 共享记忆层 v4.0: Mem0 Cloud → qdrant → SQLite 三级降级, user_id 隔离 + Cloud API 签名兼容, 冲突检测 + 重要性衰减 + 自动压缩 |
| invest_tools.py | `src/invest_tools.py` | ~600 | 行情获取 + 报价格式化 |
| ta_engine.py | `src/ta_engine.py` | ~500 | pandas-ta 技术指标计算 |
| history_store.py | `src/history_store.py` | ~400 | SQLite 对话历史存储 |
| risk_manager.py | `src/risk_manager.py` | ~1320 | 风控引擎 (仓位/止损/集中度/行业查询/风险敞口摘要) |
| social_tools.py | `src/social_tools.py` | ~700 | 社媒内容生成 + 发布 |
| monitoring.py | `src/monitoring.py` | 1243 | Prometheus 监控 + 健康检查 |
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
| ai_team_integration.py | `src/trading/ai_team_integration.py` | 50 | AI 团队集成 (投票注入点/包装器) |
| env_helpers.py | `src/trading/env_helpers.py` | 30 | 交易环境变量工具 (bool/int 安全读取) |
| market_hours.py | `src/trading/market_hours.py` | 33 | 市场时间判断 (美股交易时段/休市日检测) |
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

## 5. R9 补充的核心模块条目

以下模块在 R1~R8 审计中发现缺失注册，现统一补充。

| 模块 | 路径 | 行数 | 说明 | 搬运来源 |
|------|------|------|------|---------|
| `browser_use_bridge.py` | `src/browser_use_bridge.py` | ~220 | AI 浏览器代理桥接 — DOM 解析/LLM 决策/反检测 | browser-use (81k⭐) |
| `crewai_bridge.py` | `src/crewai_bridge.py` | ~180 | CrewAI 多 Agent 协作桥接 | crewai (27k⭐) |
| `trading_journal.py` | `src/trading_journal.py` | ~350 | 交易日志 — 开仓/平仓/盈亏记录 | 自研 |
| `novel_writer.py` | `src/novel_writer.py` | ~450 | AI 小说工坊 — 大纲/续写/TTS | inkos + MuMuAINovel |
| `position_monitor.py` | `src/position_monitor.py` | ~700 | 持仓实时监控 — 止损/止盈/异动告警 | 自研 |
| `social_scheduler.py` | `src/social_scheduler.py` | ~580 | 社媒自动驾驶 — 5 个定时任务 (APScheduler) | 自研 |
| `auto_trader.py` | `src/auto_trader.py` | ~680 | 自动交易引擎 — 信号扫描/执行/管理 | 自研 |
| `data_providers.py` | `src/data_providers.py` | ~400 | 多市场数据源聚合 (yfinance/Alpha Vantage) | yfinance (16k⭐) |
| `backtester.py` | `src/backtester.py` | ~350 | 回测引擎主模块 | vectorbt (5.4k⭐) |
| `skyvern_bridge.py` | `src/integrations/skyvern_bridge.py` | ~150 | Skyvern 浏览器 RPA 桥接 | skyvern (14k⭐) |
| `strategies/drl_strategy.py` | `src/strategies/drl_strategy.py` | ~200 | 深度强化学习交易策略 (PPO) | FinRL (10k⭐) |
| `strategies/factor_strategy.py` | `src/strategies/factor_strategy.py` | ~300 | 16 Alpha 因子量化策略 | Qlib (16k⭐) |
| `image_tool.py` | `src/tools/image_tool.py` | ~100 | 图片生成工具 (硅基流动 FLUX/SD3/SDXL) | 自研 |
| `bash_tool.py` | `src/tools/bash_tool.py` | ~80 | Bash 命令执行工具 (沙箱) | smolagents |
| `code_tool.py` | `src/tools/code_tool.py` | ~120 | Python 代码执行工具 (沙箱) | smolagents |
