# OpenClaw Bot — 全系统智能化跃迁设计 (Wave 1)

> 最后更新: 2026-03-30
> 领域: `backend`, `xianyu`, `trading`, `social`, `infra`
> 状态: 设计中

---

## 一、核心问题

系统当前是"工具集合"——每个模块独立运行，被动等待用户命令。数据收集了但不反哺，模块之间不联动。

**目标**: 从"被动工具"升级为"智能助手"——自己会思考、会学习、会主动帮忙。

**根因**: 数据收集机制完善（SQLite 表、EventBus 事件），但缺少"反馈循环"——做完事不回头看效果。

---

## 二、Wave 1 设计 — "把已有数据用起来"

### 2.1 日报智能化 — 从"数据报表"到"决策参谋"

**现状**: `daily_brief.py` 聚合 13 个数据段，每段独立获取数据，无叙事、无交叉分析、无建议。

**改造**:

1. **新增开头: 一句话总结**
   - 在所有数据段之前，用 LLM 生成 2 句话的"当日概况":
   - 输入: 持仓盈亏、闲鱼订单数、社媒互动变化、预算状态
   - 输出: "整体不错——投资组合涨了 2%，闲鱼成交 3 单，社媒粉丝增长 15"
   - 实现: 新增 `_generate_executive_summary(sections_data: dict) -> str`

2. **新增结尾: 3 条今日建议**
   - 基于当日数据生成可操作建议:
   - 实现: 新增 `_generate_daily_recommendations(sections_data: dict) -> str`
   - LLM prompt 要求: 每条建议必须引用具体数据，不要泛泛而谈
   - 示例输出:
     ```
     💡 今日建议:
     1. 闲鱼商品"MacBook Pro"已挂 14 天无人问，建议降价 5%
     2. NVDA 持仓浮盈 15%，可考虑分批止盈
     3. 你的投资类帖子互动率是其他类型的 3 倍，今天适合写一篇交易复盘
     ```

3. **新增趋势对比**
   - 关键数字旁加"vs 昨天"或"vs 上周":
   - 持仓总值: $12,500 (↑2.1% vs 昨天)
   - 闲鱼咨询: 8 条 (↓30% vs 上周同期)
   - 实现: 在 `daily_stats`, `get_today_trades` 等调用旁增加历史对比查询

**改动文件**: `packages/clawbot/src/execution/daily_brief.py`
**新增函数**: `_generate_executive_summary()`, `_generate_daily_recommendations()`, `_get_yesterday_stats()`
**验证标准**: 日报开头有概况总结，结尾有 3 条数据驱动的建议

---

### 2.2 闲鱼买家画像 — 从"每次当陌生人"到"记住每个人"

**现状**: `XianyuReplyBot.agenerate_reply()` 接收 `user_msg + item_desc + context`，不注入任何买家历史。`consultations` 表已记录买家数据（msg_count, converted）但从未反哺到 AI 提示词。

**改造**:

1. **新增买家画像注入**
   - 在 `agenerate_reply` 流程中，调用 `ctx.get_buyer_profile(user_id)` 获取画像
   - 画像数据来源: `consultations` + `orders` + `messages` 表
   - 画像内容:
     ```
     【买家画像】
     - 历史咨询: 5 次 (跨 3 个商品)
     - 历史成交: 1 次 (2 天前，金额 ¥299)
     - 砍价倾向: 高 (3/5 次咨询涉及砍价)
     - 上次联系: 昨天问过另一个商品
     ```
   - 注入位置: `PriceAgent.agenerate()` 和 `BaseAgent.agenerate()` 的 system prompt 中

2. **新增方法 `XianyuContextManager.get_buyer_profile(user_id: str) -> dict`**
   ```python
   def get_buyer_profile(self, user_id: str) -> dict:
       """构建买家画像:
       - total_consultations: 总咨询次数
       - total_orders: 总成交次数
       - items_consulted: 咨询过的商品列表
       - bargain_tendency: 砍价倾向 (低/中/高)
       - last_contact_ts: 上次联系时间
       - avg_msg_count: 平均每次对话消息数
       - is_repeat_buyer: 是否回头客
       """
   ```

3. **PriceAgent 策略适配**
   - 回头客: 温度降低 0.1，语气更亲近 ("欢迎回来")
   - 高砍价倾向: 初始温度提高 0.1，策略更坚定
   - 新买家 (0 次历史): 标准策略

**改动文件**: `xianyu_context.py` (新增 `get_buyer_profile`), `xianyu_agent.py` (注入画像到 prompt)
**验证标准**: 回头买家收到的回复中包含"回头客"相关语气调整

---

### 2.3 社媒发帖时间优化 — 从"固定时间"到"数据驱动"

**现状**: `social_scheduler.py` 使用 5 个固定 cron 时间 (09:00/12:30/19:00/20:30/22:00)。`PostTimeOptimizer.best_hours()` 已实现且有数据，但发布任务 `job_night_publish` 固定在 20:30 执行，从未使用优化器输出。

**改造**:

1. **发布时间动态化**
   - `_setup_cron_jobs()` 中，`night_publish` 改为从 `PostTimeOptimizer` 获取最佳发布时间
   - 如果优化器无数据（冷启动），保持默认 20:30
   - 如果有数据，取 `best_hours("twitter", top_n=1)[0]` 作为发布 hour
   - 每天 `job_late_review` (22:00) 结束后重新计算次日最佳时间并调整 cron

2. **实现方式**
   ```python
   # 在 _setup_cron_jobs 中:
   optimizer = get_post_time_optimizer()
   best = optimizer.best_hours("twitter", top_n=1)
   publish_hour = best[0] if best else 20  # 默认 20 点
   publish_minute = 30

   scheduler.add_job(
       self.job_night_publish,
       CronTrigger(hour=publish_hour, minute=publish_minute, timezone="Asia/Shanghai"),
       id="night_publish", ...
   )
   ```

3. **次日时间更新**
   - 在 `job_late_review` 末尾新增:
   ```python
   # 根据今日数据更新明日发布时间
   new_best = optimizer.best_hours("twitter", top_n=1)
   if new_best and new_best[0] != current_publish_hour:
       self.scheduler.reschedule_job("night_publish",
           trigger=CronTrigger(hour=new_best[0], minute=30, timezone="Asia/Shanghai"))
       logger.info(f"[社媒] 明日发布时间调整为 {new_best[0]}:30")
   ```

**改动文件**: `social_scheduler.py` (`_setup_cron_jobs`, `job_late_review`)
**验证标准**: 发布时间跟随 `PostTimeOptimizer` 输出变化

---

### 2.4 主动引擎扩展 — 从"只管 3 件事"到"全局感知"

**现状**: `ProactiveEngine` 只订阅 5 个事件 (`TRADE_EXECUTED`, `RISK_ALERT`, `WATCHLIST_ANOMALY`, `TASK_COMPLETED`, `brain.progress`)。大量有价值的事件被忽略。

**改造**:

1. **新增 4 个事件订阅**

   | 新事件 | 触发场景 | 通知示例 |
   |--------|---------|---------|
   | `XIANYU_ORDER_PAID` | 闲鱼买家付款 | "有人刚买了你的 MacBook 充电器，¥89，要现在发货吗？" |
   | `BUDGET_EXCEEDED` | 月度预算超支 | "这个月餐饮花了 ¥2000，超出预算 30%" |
   | `SOCIAL_PUBLISHED` | 社媒内容发布 | "帖子已发布到小红书，1 小时后我帮你看看初始互动" |
   | `FOLLOWER_MILESTONE` | 粉丝里程碑 | "恭喜！X 平台粉丝突破 1000 了" |

2. **事件发射端补充**
   - `xianyu_live.py`: 付款成功时 `bus.publish(EventType.XIANYU_ORDER_PAID, {...})`
   - `life_automation.py`: `check_budget_alert()` 触发时 `bus.publish(EventType.BUDGET_EXCEEDED, {...})`
   - `social_scheduler.py`: `job_night_publish()` 成功后 `bus.publish(EventType.SOCIAL_PUBLISHED, {...})`
   - `social_scheduler.py`: `job_late_review()` 检测到粉丝增长里程碑时发射

3. **EventType 枚举扩展**
   - 在 `event_bus.py` 中新增 4 个事件类型

**改动文件**: `proactive_engine.py`, `event_bus.py`, `xianyu_live.py`, `life_automation.py`, `social_scheduler.py`
**验证标准**: 闲鱼付款后收到 Telegram 通知

---

### 2.5 交易后自动跟进 — 从"买完就忘"到"持续关注"

**现状**: `auto_trader.py` 执行交易后只发一条通知卡片，无后续跟进。`TRADE_EXECUTED` 事件由 `multi_main.py` 通过字符串匹配文本发射（而非结构化数据）。

**改造**:

1. **结构化交易事件**
   - 在 `auto_trader.py` 的 `execute_proposal()` 成功后，直接发射结构化事件:
   ```python
   await bus.publish(EventType.TRADE_EXECUTED, {
       "symbol": symbol,
       "direction": direction,  # BUY/SELL
       "quantity": filled_qty,
       "entry_price": entry_price,
       "stop_loss": stop_loss,
       "take_profit": take_profit,
       "timestamp": now_et().isoformat(),
   })
   ```

2. **延迟跟进处理**
   - `ProactiveEngine.on_trade_executed()` 增加延迟跟进逻辑:
   ```python
   async def on_trade_executed(self, data):
       # 立即: 评估是否需要跨域通知
       await self._evaluate_and_maybe_notify(...)

       # 2小时后: 跟进交易状态
       asyncio.get_running_loop().call_later(
           7200,  # 2小时
           lambda: asyncio.create_task(self._trade_followup(data))
       )

   async def _trade_followup(self, trade_data):
       """查询当前价格，与买入价对比，发送跟进通知"""
       current_price = await get_quick_quote(trade_data["symbol"])
       pnl_pct = (current_price - trade_data["entry_price"]) / trade_data["entry_price"] * 100
       # 通过 Gate/Generate/Critic 管道决定是否通知
   ```

**改动文件**: `auto_trader.py` (结构化事件发射), `proactive_engine.py` (跟进逻辑)
**验证标准**: 交易执行 2 小时后收到跟进消息

---

## 三、Wave 2 预览 — "让系统会学习"（本次不实施）

| 模块 | 升级 | 核心机制 |
|------|------|---------|
| 闲鱼 | 谈判策略学习 | 记录每次对话结果(成交/流失)，LLM 提取成功话术，构建 playbook |
| 社媒 | 内容效果反馈环 | 追踪每种内容类型的互动率，自动停止低效内容、增产高效内容 |
| 投资 | 交易复盘学习 | 结构化提取每笔交易教训，验证改进建议是否有效 |
| 生活 | 消费模式识别 | 分析消费时间/类目分布，识别异常消费并提醒 |

---

## 四、Wave 3 预览 — "融会贯通"（本次不实施）

| 联动 | 数据流 | 效果 |
|------|--------|------|
| 闲鱼→投资 | 月销售额 → 可投资金额建议 | "闲鱼这月赚了 ¥3000，可以追加 2 个持仓" |
| 社媒→投资 | 帖子提及个股的互动率 → 情绪验证 | "你的 NVDA 帖子互动率 3x，市场情绪也看好" |
| 全部→生活 | 所有收支 → 统一财务视图 | "闲鱼赚 500，投资亏 300，生活花 150，净赚 50" |
| 全部→日报 | 跨模块数据 → 全局健康诊断 | 日报变成"管家汇报"而非"数据报表" |

---

## 五、技术约束

1. **LLM 调用成本**: 日报新增 2 次 LLM 调用 (概况+建议)，使用 g4f (免费) 或最便宜模型
2. **延迟跟进**: 使用 `call_later` 而非 APScheduler，重启会丢失——可接受，因为是辅助功能
3. **买家画像**: 纯 SQLite 查询，无新依赖，无性能风险
4. **事件扩展**: 只增加 EventType 枚举值和 handler，不改变 EventBus 核心机制
5. **向后兼容**: 所有改动都是增量式的，不删除任何现有功能

---

## 六、实施顺序

| 序号 | 子系统 | 预计改动文件数 | 优先级 |
|------|--------|-------------|--------|
| 1 | 日报智能化 | 1 | 最高 (用户每天看) |
| 2 | 闲鱼买家画像 | 2 | 高 (直接影响收入) |
| 3 | 社媒发帖时间 | 1 | 中 (数据已有) |
| 4 | 主动引擎扩展 | 5 | 中 (基础设施) |
| 5 | 交易后跟进 | 2 | 中 (体验提升) |
