# COMMAND_REGISTRY — OpenClaw Bot 命令全表

> 最后更新: 2026-03-28 | 新增 /review_history 复盘历史查询命令 + cmd_chart K线图实装，总数 92

---

## 1. 注册命令一览（91 个）

命令在 `multi_bot.py:171-340` 统一注册。

### 1.1 基础命令 — `BasicCommandsMixin` (cmd_basic_mixin.py, 1038 行)

| # | 命令 | Handler | 说明 | BotFather 菜单 |
|---|------|---------|------|:-:|
| 1 | `/start` | `cmd_start` | 首次 onboarding + 老用户分类菜单 | Y |
| 2 | `/help` | `cmd_start` | 同 /start（别名） | Y |
| 3 | `/clear` | `cmd_clear` | 清空当前对话历史 | Y |
| 4 | `/status` | `cmd_status` | Bot 运行状态 + 网关 + 浏览器 | Y |
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

### 1.2 投资命令 — `InvestCommandsMixin` (cmd_invest_mixin.py, 498 行)

| # | 命令 | Handler | 说明 | BotFather |
|---|------|---------|------|:-:|
| 19 | `/quote` | `cmd_quote` | 行情查询 (富卡片 + 操作按钮) | Y |
| 20 | `/market` | `cmd_market` | 市场概览 | Y |
| 21 | `/portfolio` | `cmd_portfolio` | 投资组合 (卡片 + 风险敞口 + SPY对标 + 饼图 + 行业分布 + IBKR) | Y |
| 22 | `/buy` | `cmd_buy` | 模拟买入 (风控→IBKR→模拟降级) | Y |
| 23 | `/sell` | `cmd_sell` | 模拟卖出 | Y |
| 24 | `/watchlist` | `cmd_watchlist` | 自选股管理 | N |
| 25 | `/trades` | `cmd_trades` | 交易记录 + PnL 图表 | N |
| 26 | `/reset_portfolio` | `cmd_reset_portfolio` | 重置投资组合 | N |
| 27 | `/export` | `cmd_export` | 导出 trades/watchlist/portfolio/expenses/xianyu (xlsx/csv) | N |

### 1.3 技术分析 — `AnalysisCommandsMixin` (cmd_analysis_mixin.py, 362 行)

| # | 命令 | Handler | 说明 | BotFather |
|---|------|---------|------|:-:|
| 28 | `/ta` | `cmd_ta` | 全套超短线技术指标 | Y |
| 29 | `/scan` | `cmd_scan` | 市场多标的扫描 | N |
| 30 | `/signal` | `cmd_signal` | 快速买卖信号 (多标的并行) | N |
| 31 | `/performance` | `cmd_performance` | 绩效仪表盘 | N |
| 32 | `/review` | `cmd_review` | AI 团队复盘今日交易 | N |
| 33 | `/journal` | `cmd_journal` | 交易日志 (持仓 + 已平仓) | N |
| 34 | `/chart` | `cmd_chart` | K线图 (MA+成交量, Plotly candlestick) | N |
| 35 | `/drl` | `cmd_drl` | DRL 强化学习策略分析 (PPO, FinRL) | N |
| 36 | `/factors` | `cmd_factors` | 16 Alpha 因子分析 (Qlib, LightGBM) | N |
| 37 | `/calc` | `cmd_calc` | 仓位计算器: 固定比例法+凯利公式 (搬运 TradingView Position Size Calculator) | N |
| 38 | `/weekly` | `cmd_weekly` | 综合周报 (投资+社媒+闲鱼+成本 7 天聚合) | N |
| 39 | `/accuracy` | `cmd_accuracy` | AI预测准确率面板 (按AI分组显示历史预测表现) | N |
| 40 | `/equity` | `cmd_equity` | 权益曲线图表 (按日聚合累计收益变化) | N |
| 41 | `/targets` | `cmd_targets` | 盈利目标进度 (日/周/月目标达成百分比) | N |
| 42 | `/review_history` | `cmd_review_history` | 复盘历史查询 (近N次复盘记录+教训+星级评分) | N |

### 1.4 IBKR 实盘 — `IBKRCommandsMixin` (cmd_ibkr_mixin.py, 165 行)

| # | 命令 | Handler | 说明 | BotFather |
|---|------|---------|------|:-:|
| 37 | `/ibuy` | `cmd_ibuy` | IBKR 买入 (市价/限价) | N |
| 38 | `/isell` | `cmd_isell` | IBKR 卖出 | N |
| 39 | `/ipositions` | `cmd_ipositions` | IBKR 持仓查询 | N |
| 40 | `/iorders` | `cmd_iorders` | IBKR 挂单查询 | N |
| 41 | `/iaccount` | `cmd_iaccount` | IBKR 账户信息 + 预算 | N |
| 42 | `/icancel` | `cmd_icancel` | 取消 IBKR 订单 | N |

### 1.5 自动交易 — `TradingCommandsMixin` (cmd_trading_mixin.py, 399 行)

| # | 命令 | Handler | 说明 | BotFather |
|---|------|---------|------|:-:|
| 43 | `/autotrader` | `cmd_autotrader` | AutoTrader 控制 (start/stop/auto/manual/cycle/confirm/cancel) | N |
| 44 | `/risk` | `cmd_risk` | 风控状态 + IBKR 实时数据 | Y |
| 45 | `/monitor` | `cmd_monitor` | 持仓监控 (卡片 + 饼图) | N |
| 46 | `/tradingsystem` | `cmd_tradingsystem` | 交易系统全状态 | N |
| 47 | `/backtest` | `cmd_backtest` | 回测 (自研引擎 / Freqtrade + Bokeh) | Y |
| 48 | `/rebalance` | `cmd_rebalance` | 再平衡 (preset 配置 + 漂移分析) | N |

### 1.6 协作命令 — `CollabCommandsMixin` (cmd_collab_mixin.py, 824 行)

| # | 命令 | Handler | 说明 | BotFather |
|---|------|---------|------|:-:|
| 49 | `/invest` | `cmd_invest` | 6 位 AI 投资分析会议 | Y |
| 50 | `/discuss` | `cmd_discuss` | 多 Bot 多轮讨论 (1-10 轮) | N |
| 51 | `/stop_discuss` | `cmd_stop_discuss` | 中断讨论/投资会议 | N |
| 52 | `/collab` | `cmd_collab` | 多模型协作 (规划→执行→审查→汇总) | N |

### 1.7 执行场景 — `ExecutionCommandsMixin` (cmd_execution_mixin.py, 1737 行)

| # | 命令 | Handler | 说明 | BotFather |
|---|------|---------|------|:-:|
| 53 | `/ops` | `cmd_ops` | 自动化工作台 (交互菜单) | Y |
| 54 | `/dev` | `cmd_dev` | 开发流程 (→ops dev) | N |
| 55 | `/brief` | `cmd_brief` | 执行简报 | N |
| 56 | `/hot` | `cmd_hot` | 热点发文 (→cmd_hotpost) | Y |
| 57 | `/hotpost` | `cmd_hotpost` | 抓热点 + 一键发文 (支持 --preview) | N |
| 58 | `/cost` | `cmd_cost` | 成本/配额/节流状态 | N |
| 59 | `/config` | `cmd_config` | 运行配置概览 | N |
| 60 | `/topic` | `cmd_topic` | 题材深度研究 | N |
| 61 | `/xhs` | `cmd_xhs` | 小红书发文 | N |
| 62 | `/post` | `cmd_post` | 双平台发文 (无题材→热点) | Y |
| 63 | `/social_plan` | `cmd_social_plan` | 发文计划 | N |
| 64 | `/social_repost` | `cmd_social_repost` | 双平台改写草稿 | N |
| 65 | `/social_launch` | `cmd_social_launch` | 数字生命首发包 | N |
| 66 | `/social_persona` | `cmd_social_persona` | 当前社媒人设 | N |
| 67 | `/post_social` | `cmd_post_social` | 双平台发文 (→cmd_post) | N |
| 68 | `/post_x` | `cmd_post_x` | 发 X (→cmd_xpost) | N |
| 69 | `/post_xhs` | `cmd_post_xhs` | 发小红书 (→cmd_xhspost) | N |
| 70 | `/xwatch` | `cmd_xwatch` | X 博主监控导入 | N |
| 71 | `/xbrief` | `cmd_xbrief` | X 博主更新摘要 | N |
| 72 | `/xdraft` | `cmd_xdraft` | 生成 X 草稿 | N |
| 73 | `/xpost` | `cmd_xpost` | 自动发 X | N |
| 74 | `/xhsdraft` | `cmd_xhsdraft` | 生成小红书草稿 | N |
| 75 | `/xhspost` | `cmd_xhspost` | 自动发小红书 | N |
| 76 | `/dualpost` | `cmd_dual_post` | 一键双平台发文 (AI生成→预览→确认) | N |
| 77 | `/publish` | `cmd_publish` | 社媒多平台发布 — sau_bridge (抖音/B站/小红书/快手) | N |
| 78 | `/xianyu` | `cmd_xianyu` | 闲鱼 AI 客服控制 (start/stop/status/reload/floor) | N |
| 79 | `/social_calendar` | `cmd_social_calendar` | 内容日历(DB优先+AI生成)，支持 `done N` 标记完成 | N |
| 80 | `/social_report` | `cmd_social_report` | 社媒效果报告 + A/B 测试 | N |
| 81 | `/agent` | `cmd_agent` | 智能 Agent — 自然语言驱动多工具链 (smolagents) | N |
| 82 | `/novel` | `cmd_novel` | AI 小说工坊 — 网文大纲/续写/导出/TTS (inkos+MuMuAINovel) | N |
| 83 | `/ship` | `cmd_ship` | 闲鱼卡券管理 — add/stock/rule/stats/test (auto_shipper) | N |
| 84 | `/xianyu_report` | `cmd_xianyu_report` | 闲鱼收入报表 — 日报/周报/月报 + 爆款排行 + BI三板块(热销排行/高峰时段/转化漏斗) | N |
| 85 | `/xianyu_style` | `cmd_xianyu_style` | 闲鱼 AI 客服回复配置 — 自定义回复风格/FAQ模板/商品规则 (set/faq/rule/show) | N |
| 86 | `/bill` | `cmd_bill` | 生活账单追踪 — 话费/水电费余额检测 + 低余额告警 + 定期提醒 (add/update/list/remove + 中文NLP) | N |
| 86 | `/pricewatch` | `cmd_pricewatch` | 降价监控 — 商品降价提醒 + 每6小时自动检查 + 目标价触发通知 (add/list/remove + 中文NLP) | Y |

---

## 2. Callback Button 模式一览

在 `multi_bot.py:245-268` 注册。

| # | Pattern | Handler | Source | 说明 |
|---|---------|---------|--------|------|
| 1 | `^itrade` | `handle_trade_callback` | message_mixin | 投资分析后一键下单 |
| 2 | `^help:` | `handle_help_callback` | cmd_basic_mixin | /start 分类菜单导航 |
| 3 | `^onboard:` | `handle_help_callback` | cmd_basic_mixin | 首次用户 onboarding 按钮 |
| 4 | `^fb\|` | `handle_feedback_callback` | cmd_basic_mixin | 👍/👎/🔄 反馈按钮 |
| 5 | `^mem_` | `handle_memory_callback` | cmd_basic_mixin | 记忆分页/清除 |
| 6 | `^settings\|` | `handle_settings_callback` | cmd_basic_mixin | 设置切换按钮 |
| 7 | `^cmd:` | `handle_notify_action_callback` | cmd_basic_mixin | 交易通知 actionable 按钮 + 模糊引导快捷操作 (bill/xianyu 已加入 cmd_map) |
| 8 | `^social_confirm:` | `handle_social_confirm_callback` | cmd_execution_mixin | 社交发文预览确认/取消/重生成 |
| 9 | `^ops_` | `handle_ops_menu_callback` | cmd_execution_mixin | /ops 交互菜单按钮 |
| 10 | `^(ta_\|buy_\|watch_)` | `handle_quote_action_callback` | cmd_invest_mixin | 行情卡片操作 (技术分析/买入/加自选) |
| 11 | `^(trade:\|bt:\|ta:\|...)` | `handle_card_action_callback` | cmd_basic_mixin | OMEGA 响应卡片操作按钮 |
| 12 | `^noop$` | lambda (answer) | multi_bot | 空操作（已收到反馈占位） |

### 非 Command 消息处理器 (multi_bot.py:270-281)

| Handler | Filter | 说明 |
|---------|--------|------|
| `handle_message` | TEXT & ~COMMAND | 文本对话（流式输出 + 中文 NLP 拦截） |
| `handle_photo` | PHOTO | OCR → 场景路由 → 业务决策链 |
| `handle_voice` | VOICE \| AUDIO | Whisper 转文字 → handle_message |
| `handle_document_ocr` | Document.PDF \| Document.IMAGE | 文档 OCR |
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
