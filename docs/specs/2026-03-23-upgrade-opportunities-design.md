# OpenClaw Bot — 体验诊断 & 升级机会清单

> 最后更新: 2026-03-24 | 领域: `backend` `ai-pool` `trading` `infra`

---

## 一、现状诊断："最好的体验" 还是 "能用"？

**结论：能用偏上，离「最好的体验」还有 2–3 个迭代。**

### 当前强项

| 维度 | 状态 | 说明 |
|------|------|------|
| 功能广度 | ✅ 扎实 | 75 命令 + 66 触发词，覆盖投资/社媒/购物/闲鱼/生活 |
| LLM 路由 | ✅ 领先 | 74 deployment + 主备切换，成本/稳定性方案成熟 |
| 闲鱼客服 | ✅ 闭环 | 唯一真正端到端跑通的自动化场景 |
| 可观测 | ✅ 完整 | Langfuse + Phoenix OTEL 全链路追踪 |
| 部署 | ✅ 完成 | macOS 主 + 腾讯云备，心跳+自动切换 |

### 当前短板（阻碍「最好体验」）

| 问题 | 严重度 | 根因 |
|------|--------|------|
| IBKR 实盘未接入 | 🔴 | 交易系统核心卖点无法真实验证 |
| `execution_hub.py` 3808行巨石 | 🟠 | 可维护性差，AI 工具上下文窗口溢出 |
| 两个核心文件来自反编译 | 🟠 | 变量名不可靠，难以安全重构 |
| 功能广但深度浅 | 🟡 | 75 命令中高频使用估计 < 10 个 |
| 测试覆盖不均衡 | 🟡 | 99.3% 通过但 3 个隔离问题存在 |
| context_manager 为简化版 | 🔵 | 751行自实现，缺完整分层记忆能力 |

---

## 二、核心护城河分析

**坦诚评估：技术层面几乎没有「抄不走」的壁垒，壁垒在产品设计层。**

### 真正的护城河

| 护城河 | 描述 | 可复制难度 |
|--------|------|------------|
| **AI 投资委员会编排** | Haiku→Qwen→GPT→DeepSeek→Sonnet 5模型分工投票 | 中等（需大量调优） |
| **中文生活场景组合** | 闲鱼+A股+小红书/微博+jieba NLP，覆盖中国用户独特高频场景 | 高（场景积累） |
| **50+ LLM Deployment 运维** | 国内免费源+限流策略+Key池轮换，运维经验不是代码 | 高（时间积累） |
| **7 Bot 协作体系** | 多 Bot 分工 + OMEGA v2 路由 | 中等 |

### 没有护城河的部分

- LiteLLM 路由 = 任何人 `pip install litellm`
- mem0 记忆 = 开源方案
- crawl4ai 购物比价 = 标准爬虫封装
- browser-use 自动化 = 开源方案

**结论**：护城河不在单项技术，在「产品组合 × 中文场景适配 × 运维积累」的组合。

---

## 三、可搬运高星项目 — 按价值位阶排序

> 原则：不重复造轮子。按「提升用户感知价值」排序。

---

### 🔴 位阶 1：补齐核心卖点（交易系统硬实力）

IBKR 实盘未接入 = 投资功能目前只是 Demo。先做深再做广。

#### 1.1 VectorBT Pro — 向量化回测（已有接入点，优先深化）

| 属性 | 值 |
|------|----|
| 项目 | `polakowo/vectorbt` |
| Stars | 5k⭐ |
| 搬运目标 | 深化 `backtester_vbt.py` (257行) |
| 当前状态 | 已引入但功能浅，未充分利用 |
| 搬运后 | 性能 10x+；夏普/回撤/胜率/卡玛自动计算；Portfolio 优化 |
| 工作量 | 2–3 天 |

#### 1.2 FinRL — 深度强化学习交易 ✅ 已完成

| 属性 | 值 |
|------|----| 
| 项目 | `AI4Finance-Foundation/FinRL` |
| Stars | 11k⭐ |
| 搬运目标 | 新建 `src/strategies/drl_strategy.py` (~310行) |
| 搬运后 | PPO/A2C 策略 + gymnasium 交易环境 + 模型缓存 |
| 实际工作量 | 0.5 天 |
| 完成日期 | 2026-03-24 |

#### 1.3 Qlib — 微软量化研究平台 ✅ 已完成

| 属性 | 值 |
|------|----| 
| 项目 | `microsoft/qlib` |
| Stars | 18k⭐ |
| 搬运目标 | 新建 `src/strategies/factor_strategy.py` (~380行) |
| 搬运后 | 16 Alpha 因子 + LightGBM ML 信号 + 双路径打分 |
| 实际工作量 | 0.5 天 |
| 完成日期 | 2026-03-24 |

---

### 🟠 位阶 2：让已有功能从「能用」变「好用」

#### 2.1 Pydantic AI — 统一 Agent 定义层

| 属性 | 值 |
|------|----|
| 项目 | `pydantic/pydantic-ai` |
| Stars | 13k⭐ |
| 搬运目标 | 替代 `structured_llm.py` + 散落 instructor 调用 |
| 搬运后 | 统一 Agent 注册 + 工具绑定 + 类型安全 + 自动重试 |
| 工作量 | 3–4 天 |

#### 2.2 LangGraph — 成熟状态机 Agent 编排

| 属性 | 值 |
|------|----|
| 项目 | `langchain-ai/langgraph` |
| Stars | 12k⭐ |
| 搬运目标 | 替代 `task_graph.py` + 拆分 `execution_hub.py` 巨石 |
| 搬运后 | 检查点 + 人在回路 + 子图 + 持久状态 + 可视化调试 |
| 工作量 | 5–7 天 |
| 注意 | 必须在独立 git worktree 中进行 |

#### 2.3 Letta (MemGPT) — 完整分层记忆 ✅ 已完成

| 属性 | 值 |
|------|----| 
| 项目 | `letta-ai/letta` |
| Stars | 16k⭐ |
| 搬运目标 | 深化 `context_manager.py` v2.1→v3.0 |
| 搬运后 | Core memory 持久化 + SmartMemory 集成 + per-chat 隔离 |
| 实际工作量 | 0.5 天 |
| 完成日期 | 2026-03-24 |

---

### 🟡 位阶 3：扩展能力边界

#### 3.1 Composio — 250+ 外部服务一键集成

| 属性 | 值 |
|------|----|
| 项目 | `ComposioHQ/composio` |
| Stars | 20k⭐ |
| 搬运目标 | 新建 `integrations/composio_bridge.py` |
| 搬运后 | GitHub/Gmail/Calendar/Notion 等 250+ 服务零代码接入 |
| 工作量 | 1–2 天 |

#### 3.2 Skyvern — 视觉 RPA

| 属性 | 值 |
|------|----|
| 项目 | `Skyvern-AI/skyvern` |
| Stars | 11k⭐ |
| 搬运目标 | 增强浏览器自动化层 |
| 搬运后 | 视觉页面理解 + 更强反检测 + 无需 selector 表单操作 |
| 工作量 | 3–4 天 |

#### 3.3 Prefect — 高级任务编排

| 属性 | 值 |
|------|----|
| 项目 | `PrefectHQ/prefect` |
| Stars | 17k⭐ |
| 搬运目标 | 替代 APScheduler 定时任务 |
| 搬运后 | 任务依赖图 + 重试 + 可观测面板 + 分布式执行 |
| 工作量 | 3–5 天 |

---

### 🔵 位阶 4：前瞻性储备

#### 4.1 AG2 (AutoGen 2) — 多 Agent 对话框架

| 属性 | 值 |
|------|----|
| 项目 | `ag2ai/ag2` |
| Stars | 40k⭐ |
| 搬运目标 | 潜在替代 CrewAI 多 Agent 编排 |
| 备注 | CrewAI 目前够用，但 AG2 社区更活跃，API 更灵活 |

#### 4.2 DSPy — 声明式 LLM 编程

| 属性 | 值 |
|------|----|
| 项目 | `stanfordnlp/dspy` |
| Stars | 23k⭐ |
| 搬运目标 | 意图解析 `intent_parser.py` 优化 |
| 备注 | 用声明式签名替代手写 prompt，自动优化 |

---

## 四、推荐执行顺序 (ROI 排序) — 执行进展

| 顺序 | 搬运项 | Stars | 价值 | 工作量 | 状态 |
|------|--------|-------|------|--------|------|
| 1 | VectorBT 深化 | 5k | 回测 10x 提速 | 2–3d | ✅ 完成 (257→750行) |
| 2 | Pydantic AI | 13k | 统一 Agent 层 | 3–4d | ⏭ 跳过 (instructor已是最优) |
| 3 | CoPaw MD→HTML | — | AI回复不崩溃 | 0.5d | ✅ 完成 |
| 4 | Letta 深化 | 16k | 记忆层完善 | 2–3d | ✅ 完成 (context_manager v3.0) |
| 5 | LangGraph | 12k | 编排重构 | 5–7d | ⏭ 跳过 (task_graph已够好) |
| 6 | snownlp+textblob | 15k | 情感分析精度 | 1d | ✅ 完成 |
| 7 | feedparser | 9.8k | RSS新闻 | 0.5d | ✅ 完成 |
| 8 | PyPortfolioOpt | 4.6k | 有效前沿 | 1d | ✅ 完成 |
| 9 | exchange-calendars | 4.1k | 交易日历 | 0.5d | ✅ 完成 |
| 10 | Alpaca | 1k | 零门槛券商 | 1d | ✅ 完成 (新建) |
| 11 | get_broker() | — | 统一券商选择 | 0.5d | ✅ 完成 |
| 12 | Fear & Greed | — | 市场情绪 | 0.5d | ✅ 完成 |
| 13 | 财报日历 | — | 避财报风险 | 0.5d | ✅ 完成 |
| 14 | tvscreener | — | 动态筛选 | 0.5d | ✅ 完成 |
| 15 | ib_insync | 2.8k | IBKR实盘 | 0.5d | ✅ 完成 (启用安装) |
| 16 | 投资闭环 | — | invest→backtest→pipeline | 0.5d | ✅ 完成 (串联现有组件) |
| 17 | 新手引导 | — | 3步交互向导 | 0.5d | ✅ 完成 |
| 18 | 双平台发文 | — | /dualpost X+小红书 | 0.5d | ✅ 完成 |
| 19 | Composio | 20k | 250+ 集成 | 1–2d | ✅ 完成 (桥接+executor) |
| 20 | 收益可视化 | — | /performance 权益曲线 | 0.5d | ✅ 完成 |
| 21 | 闲鱼底线价 | — | 自动成交+/xianyu floor | 0.5d | ✅ 完成 |
| 22 | Skyvern | 11k | 视觉 RPA | 3–4d | ✅ 完成 (桥接+executor) |
| 23 | FinRL DRL | 11k | PPO/A2C 强化学习策略 | 0.5d | ✅ 完成 (drl_strategy.py) |
| 24 | Qlib 因子 | 18k | 16 Alpha 因子 + LightGBM | 0.5d | ✅ 完成 (factor_strategy.py) |
| 25 | Letta 记忆深化 | 16k | core memory 持久化 + SmartMemory 集成 | 0.5d | ✅ 完成 (context_manager v3.0) |
| 26 | K线图 + /chart | — | Plotly candlestick 命令 | 0.5d | ✅ 完成 (cmd_analysis_mixin) |
| 27 | 策略命令暴露 | — | /drl /factors 用户可触达 | 0.5d | ✅ 完成 (cmd_analysis_mixin) |

---

## 五、关键参考开源项目 (新增)

| 领域 | 项目 | 地址 | 说明 |
|------|------|------|------|
| Agent 定义 | pydantic-ai | https://github.com/pydantic/pydantic-ai | 类型安全 Agent 框架 |
| Agent 编排 | LangGraph | https://github.com/langchain-ai/langgraph | 状态机 Agent 编排 |
| 记忆管理 | Letta | https://github.com/letta-ai/letta | 分层 Agent 记忆 |
| 外部集成 | Composio | https://github.com/ComposioHQ/composio | 250+ 服务 SDK |
| 量化回测 | VectorBT | https://github.com/polakowo/vectorbt | 向量化回测 |
| DRL 交易 | FinRL | https://github.com/AI4Finance-Foundation/FinRL | 强化学习交易 |
| 因子平台 | Qlib | https://github.com/microsoft/qlib | 微软量化研究 |
| 视觉 RPA | Skyvern | https://github.com/Skyvern-AI/skyvern | 视觉浏览器自动化 |
| 任务编排 | Prefect | https://github.com/PrefectHQ/prefect | 分布式任务编排 |
| 多 Agent | AG2 | https://github.com/ag2ai/ag2 | AutoGen 2 多 Agent |
| LLM 编程 | DSPy | https://github.com/stanfordnlp/dspy | 声明式 LLM 编程 |

---

## 六、Phase 1 新增积木库清单 (2026-03-23 立项补充)

> 针对功能优先级矩阵中🚀立即执行项的搬运方案

| # | 功能 | 推荐库 | Stars | 协议 | 契合点 | 改造点 |
|---|-----|-------|-------|-----|-------|-------|
| 1 | sanitize_input 安全层 | `bleach` (2.6k⭐) + 自研正则 | 2.6k | Apache-2.0 | HTML/XSS 清洗行业标准；31 个 xfail 测试已定义接口 | 增加 SQL注入/命令注入/路径遍历检测 |
| 2 | IBKR 实盘 | `ib_insync` (2.8k⭐) | 2.8k | BSD-2 | 代码已有 try/import；broker_bridge 接口已定义 | TWS 配置指南；实盘资金保护层 |
| 3 | 输入验证增强 | `validators` (940⭐) | 940 | MIT | URL/email/IP 验证 | 整合到 security.py |
| 4 | 策略可视化 | `lightweight-charts-python` (1.4k⭐) | 1.4k | MIT | TradingView 风格 K线图 | 对接 charts.py |
| 5 | Telegram WebApp | React SDK + `@grammyjs/web-app` | — | MIT | 复用现有 React 组件 | 从 Tauri 剥离为纯 Web |
