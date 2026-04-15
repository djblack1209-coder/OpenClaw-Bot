# OpenClaw OMEGA v2.0 — 完整架构设计

> 最后更新: 2026-03-27

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 OpenClaw 从功能孤岛式 AI 助手升级为"数字生命体"——以 Telegram 为唯一交互界面，具备感知、行动、社交、投资、电商、自进化、异常自愈能力的全自主智能体系统。

**Architecture:** 洋葱分层架构（Layer 0 基础设施 → Layer 1 能力层 → Layer 2 执行层 → Layer 3 编排层 → Layer 4 交互层），所有模块通过事件总线松耦合。现有 `multi_main.py` 入口 + `globals.py` DI容器模式保持不变，新模块以插件方式注册。

**Tech Stack:** Python 3.12 / FastAPI / python-telegram-bot / CrewAI / LangGraph / LiteLLM / mem0 / APScheduler / Redis(可选) / Playwright / Retell AI / PaddleOCR / vectorbt

---

## 一、系统全景图

```
┌─────────────────────────────────────────────────────────────┐
│  Layer 4: 交互层 (Gateway)                                  │
│  ┌─────────────┐  ┌──────────────┐  ┌───────────────────┐  │
│  │ Telegram Bot │  │ Tauri Manager │  │ FastAPI REST/WS  │  │
│  │ (主控台)     │  │ (桌面管理器)  │  │ (内部API :18790) │  │
│  └──────┬──────┘  └──────┬───────┘  └────────┬──────────┘  │
├─────────┼────────────────┼───────────────────┼──────────────┤
│  Layer 3: 编排层 (Brain)                                     │
│  ┌──────┴────────────────┴───────────────────┴──────────┐   │
│  │  IntentParser → TaskGraph(DAG) → Brain(调度) → 进度推送 │   │
│  │  MultiModelRouter / CostControl / Security            │   │
│  └──────┬──────────────┬──────────────┬─────────────────┘   │
├─────────┼──────────────┼──────────────┼─────────────────────┤
│  Layer 2: 执行层 (Executor)                                  │
│  ┌──────┴──────┐ ┌─────┴─────┐ ┌─────┴──────┐ ┌─────────┐ │
│  │ API直连     │ │ 浏览器自动化│ │ AI语音拨号 │ │ 异常自愈 │ │
│  │ (httpx)     │ │ (Playwright)│ │ (Retell)  │ │(SelfHeal)│ │
│  └─────────────┘ └───────────┘ └───────────┘ └─────────┘  │
├─────────────────────────────────────────────────────────────┤
│  Layer 1: 能力层 (Modules)                                   │
│  ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐ ┌──────────┐ │
│  │ 投资团队│ │ 社媒运营│ │ 电商博弈│ │ 生活服务│ │ 自进化   │ │
│  │(CrewAI) │ │(已有)  │ │(已有)  │ │ (新增) │ │ (已有)   │ │
│  └────────┘ └────────┘ └────────┘ └────────┘ └──────────┘ │
├─────────────────────────────────────────────────────────────┤
│  Layer 0: 基础设施                                           │
│  ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐ ┌──────────┐ │
│  │ 记忆系统│ │ 任务队列│ │ 监控告警│ │ 成本控制│ │ 审计日志 │ │
│  │(mem0)  │ │(APSched)│ │(Prom.) │ │(新增)  │ │ (新增)   │ │
│  └────────┘ └────────┘ └────────┘ └────────┘ └──────────┘ │
└─────────────────────────────────────────────────────────────┘
```

---

## 二、目录结构（增量设计，兼容现有代码）

```
packages/clawbot/
├── multi_main.py                    # 现有入口，追加新模块注册
├── requirements.txt                 # 追加新依赖
├── config/
│   ├── .env                         # 现有
│   └── omega.yaml                   # 新增：OMEGA全局配置
├── src/
│   ├── bot/                         # 现有 Mixin Bot 架构（保持）
│   ├── api/                         # 现有 FastAPI（追加 router）
│   │   └── routers/
│   │       ├── gateway.py           # 新增：Telegram主控台API
│   │       └── cost.py              # 新增：成本查询API
│   │
│   ├── core/                        # ★ 新增：OMEGA 核心编排层
│   │   ├── __init__.py
│   │   ├── brain.py                 # 核心编排器（意图→任务图→调度→推送）
│   │   ├── intent_parser.py         # 意图解析器（NL→结构化意图）
│   │   ├── task_graph.py            # 任务DAG引擎（基于LangGraph）
│   │   ├── executor.py              # 多路径执行引擎（API→浏览器→电话降级链）
│   │   ├── self_heal.py             # 异常自愈引擎（6步自愈流程）
│   │   ├── cost_control.py          # 成本控制（预算/追踪/感知路由）
│   │   ├── security.py              # 安全分级（PIN/白名单/审计日志）
│   │   └── event_bus.py             # 事件总线（替代直接import联动）
│   │
│   ├── gateway/                     # ★ 新增：Telegram 主控台
│   │   ├── __init__.py
│   │   ├── telegram_gateway.py      # Telegram Bot 主控台（进度推送/Inline KB）
│   │   ├── progress_streamer.py     # 实时进度推送器
│   │   ├── keyboard_builder.py      # 交互式按钮生成器
│   │   └── notification.py          # 分级通知管理
│   │
│   ├── modules/                     # ★ 新增：功能模块目录
│   │   ├── __init__.py
│   │   ├── investment/
│   │   │   ├── __init__.py
│   │   │   ├── team.py              # 多智能体投资团队（CrewAI 6角色）
│   │   │   ├── monitor.py           # 盘中自动监控
│   │   │   ├── strategy_learner.py  # 从X学习交易策略
│   │   │   └── risk_rules.py        # 风控规则引擎
│   │   ├── commerce/
│   │   │   ├── __init__.py
│   │   │   ├── price_aggregator.py  # 全平台价格聚合
│   │   │   ├── bargainer.py         # 智能砍价机器人
│   │   │   └── coupon_hunter.py     # 优惠券猎手
│   │   └── life/
│   │       ├── __init__.py
│   │       ├── calendar_agent.py    # 日历与时间管理
│   │       ├── delivery_tracker.py  # 快递追踪
│   │       └── travel_planner.py    # 旅行规划
│   │
│   ├── senses/                      # ★ 新增：感知层
│   │   ├── __init__.py
│   │   ├── screen_agent.py          # 全局屏幕感知（Computer Use）
│   │   ├── voice_input.py           # 语音输入（Whisper STT）
│   │   └── web_perceiver.py         # 网络信息感知
│   │
│   ├── actions/                     # ★ 新增：行动层
│   │   ├── __init__.py
│   │   ├── voice_call.py            # AI语音拨号（Retell + Twilio）
│   │   ├── voice_clone.py           # 声音克隆（OpenVoice）
│   │   └── app_controller.py        # 应用控制器
│   │
│   ├── evolution/                   # 现有（增强）
│   ├── execution/                   # 现有
│   ├── trading/                     # 现有
│   ├── shopping/                    # 现有
│   ├── xianyu/                      # 现有
│   ├── tools/                       # 现有
│   ├── synergy.py                   # 现有（升级为EventBus消费者）
│   ├── monitoring.py                # 现有
│   └── ...                          # 其他现有模块保持不变
│
├── data/
│   ├── memory/                      # 现有
│   ├── evolution/                   # 现有
│   ├── cost/                        # 新增：成本追踪数据
│   │   └── daily_costs.jsonl
│   ├── audit/                       # 新增：审计日志
│   │   └── operations.jsonl
│   ├── personas/                    # 现有
│   ├── strategies/                  # 新增：投资策略库
│   └── task_templates/              # 新增：任务模板库
│       ├── restaurant_booking.yaml
│       ├── shopping_compare.yaml
│       └── travel_planning.yaml
│
└── tests/
    ├── test_brain.py                # 新增
    ├── test_intent_parser.py        # 新增
    ├── test_executor.py             # 新增
    ├── test_investment_team.py      # 新增
    ├── test_cost_control.py         # 新增
    └── test_security.py             # 新增
```

---

## 三、GitHub 乐高清单（按层分类，含集成优先级）

### Layer 0 基础设施

| 项目 | Stars | 用途 | 集成方式 | 优先级 |
|------|-------|------|---------|--------|
| `mem0ai/mem0` | 50k+ | 长期记忆层 | **已集成** | - |
| `apscheduler/apscheduler` | 6.3k | 定时任务 | **已集成** | - |
| `redis/redis-py` | 12k | 任务队列持久化 | pip install, 可选 | P2 |
| `AgentOps-AI/agentops` | 3k | 智能体运行监控 | pip install + decorator | P2 |

### Layer 1 能力层

| 项目 | Stars | 用途 | 集成方式 | 优先级 |
|------|-------|------|---------|--------|
| `crewAIInc/crewAI` | 46k+ | 多智能体投资团队 | **已安装**，需定义6角色 | P0 |
| `microsoft/qlib` | 15k | 量化投资平台 | pip install, 数据层对接 | P1 |
| `polakowo/vectorbt` | 4k | 向量化快速回测 | pip install, 替换现有backtester | P1 |
| `AI4Finance-Foundation/FinRL` | 11k | 强化学习交易策略 | pip install, 策略插件 | P2 |
| `comfyanonymous/ComfyUI` | 80k | AI图像工作流 | **已集成** | - |
| `hacksider/Deep-Live-Cam` | 41k | 直播换脸 | 独立服务, API调用 | P3 |

### Layer 2 执行层

| 项目 | Stars | 用途 | 集成方式 | 优先级 |
|------|-------|------|---------|--------|
| `microsoft/playwright` | 70k | 浏览器自动化 | **已安装** | - |
| `retellai/retell-python-sdk` | 800 | AI电话拨号 | pip install + API key | P1 |
| `twilio/twilio-python` | 1.8k | VoIP拨号（备选） | pip install + API key | P2 |
| `myshell-ai/OpenVoice` | 31k | 声音克隆 | pip install, 本地推理 | P2 |
| `PaddlePaddle/PaddleOCR` | 45k | 中文OCR | pip install paddleocr | P1 |
| `openai/whisper` | 70k | 语音转文字 | pip install openai-whisper | P2 |
| `ultrafunkamsterdam/undetected-chromedriver` | 9k | 反检测浏览器 | pip install | P2 |
| `2captcha/2captcha-python` | 400 | 验证码破解 | pip install + API key | P2 |

### Layer 3 编排层

| 项目 | Stars | 用途 | 集成方式 | 优先级 |
|------|-------|------|---------|--------|
| `langchain-ai/langgraph` | 9k | 任务DAG引擎 | pip install langgraph | P0 |
| `microsoft/autogen` | 36k | 多智能体编排（备选） | 参考架构，不直接用 | - |

### Layer 4 交互层

| 项目 | Stars | 用途 | 集成方式 | 优先级 |
|------|-------|------|---------|--------|
| `python-telegram-bot` | 26k | Telegram主控台 | **已集成**，升级交互模式 | P0 |
| `elevenlabs/elevenlabs-python` | 2k | 云端TTS | pip install + API key | P2 |
| `deepgram/deepgram-sdk` | 500 | 实时STT | pip install + API key | P2 |

---

## 四、各模块详细设计

### Module 0: 核心编排器 (core/brain.py)

**职责**: 接收所有输入源（Telegram/API/定时任务），解析意图，生成任务DAG，调度执行，推送进度。

**与现有系统的关系**: 
- 复用 `litellm_router.py` 的多模型路由
- 复用 `globals.py` 的 DI 容器模式
- 复用 `rpc.py` 的 lazy-import + fault-isolation 模式
- 新增 `EventBus` 替代 `synergy.py` 的直接函数调用

**核心类**: `OpenClawBrain`
- `async process_message(source, message, context) -> TaskResult`
- `async execute_task_graph(graph: TaskGraph) -> list[StepResult]`
- 内含 IntentParser / TaskGraphBuilder / CostController / SecurityGate

**多模型路由规则**（复用现有 `litellm_router.py`）:
```
复杂推理/决策      → Claude Opus 4 (free_first)
快速执行/格式化    → Claude Sonnet / Haiku (free_pool)
中文社媒理解      → Qwen3-235B / DeepSeek V3 (free_pool)
投资团队多角色    → CrewAI (内部调度)
图像理解/OCR      → Claude Vision / PaddleOCR (本地)
代码任务          → Claude Code CLI (subprocess)
本地私密任务      → Ollama (本地)
```

### Module 1: 意图解析器 (core/intent_parser.py)

**职责**: 将自然语言转为结构化 `ParsedIntent`。

**ParsedIntent 数据结构**:
```python
@dataclass
class ParsedIntent:
    goal: str                    # 核心目标
    task_type: TaskType          # BOOKING/SHOPPING/INVESTMENT/SOCIAL/LIFE/INFO/CODE
    known_params: dict           # 已知参数
    missing_critical: list       # 缺失的关键参数（必须问）
    missing_optional: list       # 缺失的可选参数（可自行决策）
    constraints: list            # 约束条件
    urgency: str                 # urgent/normal/background
    reversible: bool             # 操作是否可逆
    estimated_cost: float        # 预估费用（美元）
    requires_confirmation: bool  # 是否需要用户确认
```

**信息充足性规则**:
- `missing_critical` 不为空 → 先并行执行可执行的部分，再一次性问所有缺失信息
- 永远不分多轮问问题，合并成一个 Inline Keyboard 问题
- 推荐用按钮让用户快速回答

### Module 2: 任务DAG引擎 (core/task_graph.py)

**职责**: 将 ParsedIntent 转为有依赖关系的有向无环图。

**基于 LangGraph**: 
- 每个节点是一个 `TaskNode`（搜索/对比/选择/执行/确认）
- 节点间有边表示依赖
- 独立节点并行执行
- 任何节点失败触发 `SelfHealEngine`

**TaskNode 数据结构**:
```python
@dataclass 
class TaskNode:
    id: str
    name: str                     # "搜索餐厅" / "对比价格"
    executor_type: ExecutorType   # API / BROWSER / VOICE_CALL / LLM
    params: dict
    dependencies: list[str]       # 依赖的节点ID
    retry_count: int = 3
    fallback_chain: list[str] = field(default_factory=list)
    timeout_seconds: int = 120
    status: str = "pending"       # pending/running/success/failed/skipped
    result: Any = None
```

### Module 3: 多路径执行引擎 (core/executor.py)

**职责**: 每个 TaskNode 按以下优先级尝试执行:

```
路径1: 官方API直连（httpx）
  ↓ 失败/不存在
路径2: 非官方API（第三方封装）
  ↓ 失败/不存在
路径3: 浏览器自动化（Playwright + DrissionPage）
  ↓ 失败/验证码/反爬
路径4: AI语音电话（Retell + Twilio）
  ↓ 无法接通
路径5: 通知用户人工处理
```

**熔断机制**（参考意见补充）:
- 连续3次失败同一平台 → 自动切换备用路径
- 单日API费用 > $50 → 暂停非紧急任务
- 验证码连续失败2次 → 截图给用户

### Module 4: 异常自愈引擎 (core/self_heal.py)

**6步自愈流程**:
1. 分析错误原因（调用 LLM 分析 stderr / error message）
2. 本地知识库检索解决方案（mem0 similarity_search）
3. Web搜索 GitHub Issues / Stack Overflow（Tavily API）
4. 尝试替代方案（换库/API/工具路径）
5. 将解决方案记录到长期记忆（避免重复失败）
6. **只有当1-5全部失败时**，才通知用户请求介入

**与现有系统整合**: 
- 复用 `monitoring.py` 的 `AutoRecovery` 类
- 复用 `http_client.py` 的 `CircuitBreaker`
- 新增知识库查询和Web搜索能力

### Module 5: 多智能体投资团队 (modules/investment/team.py)

**基于 CrewAI 的6个角色**:

| 角色 | Agent ID | 职责 | LLM |
|------|----------|------|-----|
| 投资总监 | `director` | 接收指令/分配任务/最终决策/汇报 | Claude Opus |
| 研究员 | `researcher` | 基本面/行业分析/舆情 | Claude Sonnet |
| 技术分析师 | `ta_analyst` | K线/指标/形态/趋势 | Qwen3-235B |
| 量化工程师 | `quant` | 因子计算/策略回测 | DeepSeek V3 |
| 风控官 | `risk_officer` | 仓位管理/止损/一票否决 | Claude Sonnet |
| 复盘官 | `reviewer` | 交易后分析/策略迭代 | Claude Haiku |

**与现有系统整合**:
- 复用 `trading_system.py` 的 IBKR 下单通道
- 复用 `ta_engine.py` 的技术指标计算
- 复用 `risk_manager.py` 的风控规则
- 复用 `strategy_engine.py` 的策略框架
- 复用 `trading/ai_team_integration.py` 的投票机制（升级为6角色）
- 复用 `data_providers.py` 的 akshare/ccxt/yfinance 数据源

**风控硬性规则**:
```python
RISK_RULES = {
    "max_position_single": 0.20,      # 单标的最大仓位20%
    "max_sector_position": 0.35,      # 同行业最大仓位35%
    "max_total_position": 0.80,       # 总仓位上限80%
    "max_drawdown_stop": 0.08,        # 单标的回撤>8%自动止损
    "daily_loss_limit": 0.03,         # 单日亏损>3%暂停交易
    "require_human_approval": 100000,  # 单笔>10万RMB需人工确认
    "correlation_check": True,         # 持仓相关性检查
    "liquidity_check": True,           # 流动性检查
}
```

**策略失效检测**（参考意见补充）:
```python
class StrategyHealthMonitor:
    """实盘与回测表现偏离>20%时自动暂停策略"""
    FAILURE_MODES = {
        "regime_change": "市场环境突变",
        "alpha_decay": "策略被过多使用导致失效",
        "overfitting": "历史数据过度优化",
    }
```

### Module 6: Telegram 主控台 (gateway/telegram_gateway.py)

**升级现有 Telegram Bot 为主控台**:
- 保留现有 `MultiBot` Mixin 架构（7个Bot继续运行）
- 新增一个 `GatewayBot`（第8个Bot），作为统一入口
- 支持：文字指令/语音消息/图片/文件/转发消息
- 进度实时推送（流式）
- Inline Keyboard 交互式按钮
- 分级通知（silent/normal/important/urgent）

**与现有系统整合**:
- 复用 `telegram_ux.py` 的通知批量/智能分块
- 复用 `bot/globals.py` 的 DI 容器
- 通过 `EventBus` 接收所有模块事件

### Module 7: 成本控制 (core/cost_control.py)

**参考意见中的关键补充**:
```python
COST_TIERS = {
    "free":     "本地Ollama / 免费API池",         # $0
    "cheap":    "Claude Haiku / Qwen / DeepSeek",  # <$0.001/1K tokens
    "standard": "Claude Sonnet / GPT-4o-mini",     # ~$0.003/1K tokens
    "premium":  "Claude Opus / GPT-4o",            # ~$0.015/1K tokens
}

DAILY_BUDGET = float(os.getenv("OMEGA_DAILY_BUDGET", "50.0"))  # 美元
```

- 每条指令执行前预估成本
- 每条Telegram消息末尾可选显示本次成本
- 每周自动推送费用报告
- 超预算自动降级到免费模型

### Module 8: 安全分级 (core/security.py)

**权限分级体系**:
```python
PERMISSION_LEVELS = {
    "auto": [
        "读取屏幕内容", "浏览网页", "发布社媒内容（已预审核）",
        "执行比价搜索", "监控投资仓位", "回复日常消息",
    ],
    "confirm_required": [
        "实际购买（金额>500）", "拨打电话", "发送重要工作邮件",
        "执行投资买卖", "删除文件", "修改系统设置",
    ],
    "always_human": [
        "大额转账（>5000）", "法律文件签署",
        "隐私数据分享", "账号注销操作",
    ]
}
```

**安全措施**:
- Telegram user_id 白名单（复用现有 `ALLOWED_USER_IDS`）
- 敏感操作PIN码确认
- 不可篡改的操作审计日志
- 敏感数据（银行卡号/密码/身份证号）仅内存存储，永不持久化

### Module 9: 事件总线 (core/event_bus.py)

**替代 `synergy.py` 的直接函数调用**:
```python
class EventBus:
    """轻量级进程内事件总线，异步发布-订阅"""
    
    async def publish(self, event_type: str, data: dict)
    def subscribe(self, event_type: str, handler: Callable)
    def unsubscribe(self, event_type: str, handler: Callable)
```

**标准事件类型**:
```python
class EventType:
    # 交易事件
    TRADE_SIGNAL = "trade.signal"
    TRADE_EXECUTED = "trade.executed"
    RISK_ALERT = "trade.risk_alert"
    STRATEGY_SUSPENDED = "trade.strategy_suspended"
    
    # 社媒事件
    SOCIAL_PUBLISHED = "social.published"
    SOCIAL_TRENDING = "social.trending"
    
    # 进化事件
    EVOLUTION_PROPOSAL = "evolution.proposal"
    EVOLUTION_INTEGRATED = "evolution.integrated"
    
    # 系统事件
    COST_WARNING = "system.cost_warning"
    SECURITY_ALERT = "system.security_alert"
    SELF_HEAL_SUCCESS = "system.self_heal"
    SELF_HEAL_FAILED = "system.self_heal_failed"
    
    # 生活事件
    DELIVERY_UPDATE = "life.delivery"
    CALENDAR_REMINDER = "life.reminder"
```

---

## 五、数据流图（核心场景）

### 场景1: 用户说"帮我分析茅台今天能买吗"

```
Telegram消息
    ↓
GatewayBot.on_message()
    ↓
IntentParser.parse("帮我分析茅台今天能买吗")
    → ParsedIntent(goal="投资分析", task_type=INVESTMENT,
                   known_params={"symbol": "600519.SS"},
                   missing_critical=[], urgency="normal")
    ↓
TaskGraphBuilder.build(intent)
    → DAG: [研究员分析] ─┐
           [TA分析]    ─┤→ [风控审核] → [总监决策] → [推送结果]
           [量化回测]  ─┘
    ↓
Brain.execute_task_graph(dag)
    → 并行: Researcher + TA + Quant (各自用不同LLM)
    → 汇聚: RiskOfficer 审核
    → 最终: Director 决策
    ↓
ProgressStreamer.push_to_telegram(结构化结果)
    → Inline Keyboard: [确认买入] [修改仓位] [取消]
    ↓
用户点击 [确认买入]
    ↓
SecurityGate.check("投资买卖") → confirm_required → 发送PIN确认
    ↓
Trader.execute_order() (通过现有 broker_bridge.py)
    ↓
EventBus.publish("trade.executed", {...})
    → CostControl 记录费用
    → AuditLog 记录操作
    → SynergyEngine 生成社媒草稿
```

### 场景2: 用户说"帮我周末订个好餐厅"

```
Telegram消息
    ↓
IntentParser.parse("帮我周末订个好餐厅")
    → ParsedIntent(goal="餐厅预订", task_type=BOOKING,
                   known_params={"time": "周末"},
                   missing_critical=["date", "time", "guest_count", "location"],
                   urgency="normal", reversible=True)
    ↓
Brain: missing_critical不为空 → 先执行可执行的部分（搜索）
    ↓
并行执行:
    ├─ Executor.search_dianping(location=None) → 附近餐厅
    ├─ Executor.search_meituan(location=None) → 附近餐厅
    └─ KeyboardBuilder.build_clarification(missing_critical)
    ↓
Telegram推送:
    "我已经找到附近几家好餐厅，确认前需要几个信息：
     📅 用餐时间：[周六晚] [周日晚] [周六午] [周日午]
     🕕 几点：[6:00] [6:30] [7:00] [7:30]
     👥 几位：[2人] [3-4人] [5人以上]
     💬 预订人姓名和电话（请直接回复）"
    ↓
用户回复后 → 补全参数 → 继续DAG执行
    ↓
检测预订方式:
    路径1: 美团/大众点评API → 成功 → 完成
    路径2: 网页自动化 → 成功 → 完成
    路径3: AI电话拨号 → Retell拨打 → 实时转录推送到Telegram
    ↓
确认推送 + 写入日历 + 设置提醒
```

---

## 六、接口定义（核心类的完整API）

### Brain API
```python
class OpenClawBrain:
    async def process_message(self, source: str, message: Message, 
                              context: dict) -> TaskResult
    async def execute_task_graph(self, graph: TaskGraph) -> list[StepResult]
    async def handle_callback(self, callback_id: str, data: str) -> TaskResult
    def get_active_tasks(self) -> list[TaskStatus]
    def cancel_task(self, task_id: str) -> bool
```

### Executor API
```python
class MultiPathExecutor:
    async def execute(self, node: TaskNode) -> ExecutionResult
    async def execute_via_api(self, endpoint: str, params: dict) -> Any
    async def execute_via_browser(self, url: str, actions: list) -> Any
    async def execute_via_voice_call(self, phone: str, script: str) -> CallResult
    async def fallback_to_human(self, task: TaskNode) -> None
```

### Investment Team API
```python
class InvestmentTeam:
    async def analyze(self, symbol: str, context: dict = None) -> TeamAnalysis
    async def daily_meeting(self) -> DailyBrief
    async def execute_trade(self, decision: TradeDecision) -> TradeResult
    async def review_trade(self, trade_id: str) -> ReviewReport
    def get_portfolio_status(self) -> PortfolioStatus
```

### SelfHeal API
```python
class SelfHealEngine:
    async def heal(self, error: Exception, context: dict) -> HealResult
    async def search_local_solutions(self, error_msg: str) -> list[Solution]
    async def search_web_solutions(self, error_msg: str) -> list[Solution]
    async def try_alternatives(self, failed_approach: str, context: dict) -> Any
    def record_solution(self, error_pattern: str, solution: str)
```

---

## 七、配置文件设计 (config/omega.yaml)

```yaml
# OpenClaw OMEGA v2.0 配置
omega:
  version: "2.0"
  
  # Telegram 主控台
  gateway:
    telegram:
      gateway_bot_token: "${OMEGA_GATEWAY_BOT_TOKEN}"
      admin_user_ids: [123456789]  # Telegram user_id 白名单
      notification_levels:
        silent: ["social.published", "evolution.scan_complete"]
        normal: ["trade.executed", "task.completed"]
        important: ["trade.risk_alert", "cost.warning"]
        urgent: ["trade.stop_loss", "system.critical"]
      progress_style: "streaming"  # streaming / batch
      
  # 成本控制
  cost:
    daily_budget_usd: 50.0
    show_cost_per_message: false
    weekly_report: true
    cost_aware_routing: true
    
  # 安全
  security:
    require_pin_for_trades: true
    pin_hash: ""  # SHA256 hash of PIN, set on first use
    audit_log_enabled: true
    sensitive_data_in_memory_only: true
    
  # 投资团队
  investment:
    team_enabled: true
    auto_trade: false  # 需要人工确认
    risk_rules:
      max_position_single: 0.20
      max_sector_position: 0.35
      max_total_position: 0.80
      max_drawdown_stop: 0.08
      daily_loss_limit: 0.03
      require_human_approval_rmb: 100000
    monitor:
      enabled: true
      check_interval_seconds: 300
      
  # 执行引擎
  executor:
    fallback_chain: ["api", "browser", "voice_call", "human"]
    circuit_breaker:
      failure_threshold: 3
      recovery_timeout_seconds: 300
    browser:
      headless: true
      anti_detect: true
    voice_call:
      provider: "retell"  # retell / twilio
      
  # 自进化
  evolution:
    scan_interval_hours: 24
    auto_approve_threshold: 8.0
    auto_integrate: false  # 需要人工确认
    
  # 模型路由
  routing:
    default_strategy: "balanced"
    task_routing:
      complex_reasoning: "claude-opus-4"
      fast_execution: "claude-sonnet-4"
      chinese_understanding: "qwen3-235b-a22b"
      code_tasks: "claude-code-cli"
      local_private: "ollama/qwen2.5"
```

---

## 八、执行路线图

### Phase 1: 核心编排层 + Telegram主控台（第1-2周）

- [ ] Task 1: `core/event_bus.py` — 事件总线
- [ ] Task 2: `core/intent_parser.py` — 意图解析器
- [ ] Task 3: `core/task_graph.py` — 任务DAG引擎（LangGraph）
- [ ] Task 4: `core/brain.py` — 核心编排器
- [ ] Task 5: `gateway/telegram_gateway.py` — Telegram主控台
- [ ] Task 6: `gateway/progress_streamer.py` — 进度推送
- [ ] Task 7: `gateway/keyboard_builder.py` — Inline Keyboard
- [ ] Task 8: 集成到 `multi_main.py`

**验收标准**: 用户在Telegram发送自然语言指令，系统能解析意图、展示进度、通过按钮交互。

### Phase 2: 多智能体投资团队 + 安全 + 成本（第2-4周）

- [ ] Task 9: `modules/investment/team.py` — 6角色定义
- [ ] Task 10: `modules/investment/monitor.py` — 盘中监控
- [ ] Task 11: `modules/investment/risk_rules.py` — 风控规则
- [ ] Task 12: `core/cost_control.py` — 成本控制
- [ ] Task 13: `core/security.py` — 安全分级
- [ ] Task 14: 投资团队与现有 trading_system.py 对接

**验收标准**: 用户说"分析茅台"，5个Bot完成分析并以结构化格式汇报，风控有一票否决权。

### Phase 3: 多路径执行 + 自愈（第4-6周）

- [ ] Task 15: `core/executor.py` — 多路径执行引擎
- [ ] Task 16: `core/self_heal.py` — 异常自愈
- [ ] Task 17: `actions/voice_call.py` — AI语音拨号
- [ ] Task 18: `senses/screen_agent.py` — 屏幕感知
- [ ] Task 19: 任务模板库 (data/task_templates/)

**验收标准**: 系统能完成"搜索→比价→下单"的端到端流程，遇到验证码/反爬时自动降级。

### Phase 4: 生活服务 + 进化增强（第6周+）

- [ ] Task 20: `modules/life/` — 日历/快递/旅行
- [ ] Task 21: `modules/commerce/` — 全平台比价+砍价
- [ ] Task 22: Evolution Engine 升级（X策略学习）
- [ ] Task 23: 声音克隆（OpenVoice集成）

**验收标准**: 一周不给指令，OpenClaw能自主维护社媒、监控投资、整理知识。

---

## 九、进化指令系统

```bash
# 全面扫描
claw evolve scan --scope github --filter ai-agent --days 7

# 针对特定能力
claw evolve scan --capability captcha-bypass
claw evolve scan --capability voice-call

# 评估特定项目
claw evolve evaluate --repo owner/repo-name

# 集成到指定模块
claw evolve integrate --repo owner/repo-name --module commerce

# 投资策略进化
claw evolve strategy --mode backtest --period 1y
claw evolve strategy --source x-kol --accounts @trader1,@trader2

# 全自动进化（定时运行）
claw evolve auto --schedule weekly --notify on-completion

# 系统自检
claw evolve benchmark --compare last-week
claw evolve health --full
```

**进化口令（一键启动）**:
```
claw evolve --scope all --depth deep --auto-integrate --notify
```

---

## 十、能力边界诚实声明

### 高置信度（✅）
- 任何有官方API的服务：完全自动化
- 浏览器自动化操作：成功率85%+
- AI电话拨号：成功率70%+
- 内容创作（图文）：几乎无法被识别为AI
- 信息搜索和分析：超越普通人
- 投资决策支持：多维度分析，但盈亏不保证

### 有局限（⚠️）
- 强反爬平台（抖音/微信内部）：需定期维护
- 验证码：第三方打码服务，有费用，偶有失败
- 实名认证操作：需用户预先配置
- 投资收益：依赖市场环境，不保证盈利
- 复杂IVR穿越：成功率约60%

### 做不到（❌）
- 生物识别（指纹/人脸）
- 物理世界操作（取快递/签合同）
- 保证投资盈利
- 端对端加密通信内容访问
- 未授权访问他人账户
