# OpenClaw Bot — 项目全景地图

> 最后更新: 2026-04-17 (Sprint 4 全量端到端审计) | AI 开发助手请先读完本文再开始工作 | 含用户痛点地图

## 一句话概述

**OpenClaw** 是一个 7-Bot Telegram 多智能体系统，集成投资交易、社媒运营、购物比价、闲鱼自动客服、
生活自动化等能力。后端 Python + FastAPI，桌面管理端 Tauri + React，搬运整合 30+ 高星开源项目。
目标用户：个人效率极客 / 超短线投资者。

---

## 技术栈

### 后端 (Python 3.12, venv: `.venv312`)
| 层 | 技术 | 用途 |
|---|---|---|
| Bot 框架 | python-telegram-bot 22.5 | 7 个 Bot 多轮对话 |
| LLM 路由 | LiteLLM (39k⭐) + instructor (10k⭐) | 100+ 模型统一调用 + 结构化输出 |
| 内控 API | FastAPI (80k⭐) + Uvicorn | REST API 供 Tauri Manager 调用 |
| 记忆层 | mem0 (50k⭐) + SQLite | 向量嵌入 + 语义搜索 + 冲突消解 |
| 浏览器 | browser-use (81k⭐) + DrissionPage (11.6k⭐) + Skyvern (11k⭐) | AI 浏览器自动化 + 反检测 CDP + 视觉 RPA |
| 可观测 | Langfuse (23.4k⭐) + Phoenix OTEL (9k⭐) | 全链路追踪 + 成本分析 |
| 多Agent | CrewAI (46.6k⭐) | 动态角色 + 结构化任务编排 |
| 交易数据 | yfinance + AKShare (14k⭐) + CCXT (35k⭐) | 美股/A股/加密货币 |
| 技术分析 | pandas-ta (5k⭐) + ta | 200+ 标准指标 |
| 网页抓取 | crawl4ai (62.4k⭐) + Jina Reader | 结构化抽取 + LLM 降级 |
| 通知 | Apprise (16.1k⭐) | 100+ 渠道 (Discord/Slack/微信等) |
| 日志 | loguru (23.7k⭐) | 彩色控制台 + JSON 文件 + 自动轮转 |
| 重试 | tenacity (6k⭐) + stamina (1.4k⭐) | 指数退避 + 声明式重试 |
| 限流 | PyrateLimiter (485⭐) | 令牌桶统一 API 限流 |
| 图表 | Plotly (18.4k⭐) + Kaleido | 交互式图表 → PNG 导出 |
| TTS | edge-tts (10.3k⭐) | 零成本文本转语音 |
| 中文NLP | jieba (34.8k⭐) | TF-IDF 关键词提取 |
| 缓存 | utils_cache (自研, sqlite3) | LLM 响应 SQLite 持久化缓存 (替代有 CVE 的 diskcache) |
| 定时任务 | APScheduler (6.3k⭐) | 社交自动驾驶日程 |
| PDF | fpdf2 (1.1k⭐) | CJK 报告导出 |
| 二维码 | qrcode (4.5k⭐) | 邀请链接/URL 二维码 |
| Excel | openpyxl (3.7k⭐) | 交易记录/组合导出 |
| Markdown | mistletoe (1k⭐) | AST 级 Markdown → Telegram HTML |

### 桌面端 (Tauri + React)
| 技术 | 版本 | 用途 |
|---|---|---|
| Tauri 2 | 2.10 | Rust 桌面壳 |
| React | 18.3 | UI 框架 |
| TypeScript | 5.7 | 类型安全 |
| Tailwind CSS | 3.4 | 原子化样式 |
| shadcn/ui | 4.1 | 组件库 |
| Zustand | 5.0 | 状态管理 |
| @xyflow/react | 12.10 | 节点流程图 (Execution Flow 可视化) |
| Recharts | 3.8 | 数据图表 |
| framer-motion | 11.18 | 动画 |

### 基础设施
| 组件 | 说明 |
|---|---|
| Docker Compose | Redis + OpenClaw 主服务 |
| Redis 7 | 任务队列持久化 (可选) |
| API 端口 | 18790 (内控 REST) / 9090 (Prometheus) |
| macOS LaunchAgent | 开机自启服务管理 |

---

## 项目结构

```
OpenClaw Bot/
├── packages/
│   └── clawbot/                    # 🧠 核心 Python 后端 (189 文件, 67,079 行)
│       ├── multi_main.py           # 入口: 多Bot启动 + 信号处理 (875行)
│       ├── config/
│       │   ├── bot_profiles.py     # 7个Bot人设/能力/投资角色 (323行)
│       │   └── .env                # 环境变量 (API keys)
│       ├── src/
│       │   ├── core/               # OMEGA 核心引擎 (5,082行)
│       │   │   ├── brain.py        #   编排器: 意图→任务图→执行→推送 (1,475行)
│       │   │   ├── intent_parser.py#   自然语言→结构化意图 (571行)
│       │   │   ├── task_graph.py   #   DAG 任务引擎 (372行)
│       │   │   ├── executor.py     #   多路径执行: API→浏览器→电话→Composio→Skyvern→人工 (476行)

│       │   │   ├── event_bus.py    #   异步发布-订阅总线 (329行)
│       │   │   ├── self_heal.py    #   6步异常自愈 + 熔断器 (627行)
│       │   │   ├── response_cards.py#  Telegram 响应卡片生成 (809行)
│       │   │   ├── synergy_pipelines.py# 跨模块协同管道 (356行)
│       │   │   ├── cost_control.py #   每日预算/成本控制 (227行)
│       │   │   └── security.py     #   输入消毒/权限控制 (245行)
│       │   ├── bot/                # Telegram Bot 层 (7,198行)
│       │   │   ├── multi_bot.py    #   MultiBot 启动/Handler注册 (307行)
│       │   │   ├── message_mixin.py#   消息处理+中文NL触发 (1,284行)
│       │   │   ├── cmd_basic_mixin.py#  基础命令 (1,199行)
│       │   │   ├── cmd_execution_mixin.py# 执行场景命令 (1,524行)
│       │   │   ├── cmd_collab_mixin.py#  协作命令 (824行)
│       │   │   ├── cmd_invest_mixin.py#  投资命令 (576行)
│       │   │   ├── cmd_trading_mixin.py# 交易命令 (399行)
│       │   │   ├── cmd_analysis_mixin.py# 分析命令 (242行)
│       │   │   ├── cmd_ibkr_mixin.py#   IBKR实盘命令 (165行)
│       │   │   ├── api_mixin.py    #   内控API mixin (371行)
│       │   │   ├── globals.py      #   全局DI容器 (300行)
│       │   │   └── rate_limiter.py #   请求限流 (243行)
│       │   ├── tools/              # 工具服务层 (3,442行, 18文件)
│       │   │   ├── export_service.py#  Excel/CSV导出 (540行)
│       │   │   ├── comfyui_client.py#  ComfyUI 图片生成 (486行)
│       │   │   ├── code_tool.py    #   代码执行沙箱 (307行)
│       │   │   ├── free_apis.py    #   免费API聚合 (225行)
│       │   │   ├── docling_service.py# 文档理解 (215行)
│       │   │   ├── tavily_search.py#   AI搜索 (206行)
│       │   │   ├── fal_client.py   #   fal.ai 图片API (190行)
│       │   │   ├── file_tool.py    #   文件读写 (189行)
│       │   │   ├── bash_tool.py    #   安全Shell执行 (174行)
│       │   │   ├── qr_service.py   #   二维码生成 (121行)
│       │   │   ├── image_tool.py   #   图片处理 (117行)
│       │   │   ├── jina_reader.py  #   网页摘要 (112行)
│       │   │   ├── tts_tool.py     #   文字转语音 (112行)
│       │   │   ├── web_tool.py     #   网页抓取 (113行)
│       │   │   ├── deepgram_stt.py #   语音转文字 (101行)
│       │   │   ├── memory_tool.py  #   记忆工具 (98行)
│       │   │   ├── vision.py       #   视觉处理 (65行)
│       │   │   └── __init__.py     #   工具注册 (71行)
│       │   ├── xianyu/             # 闲鱼自动客服 (2,379行)
│       │   │   ├── xianyu_live.py  #   WebSocket实时聊天 (597行)
│       │   │   ├── xianyu_agent.py #   AI客服Agent (436行)
│       │   │   ├── goofish_monitor.py# 闲鱼监控 (332行)
│       │   │   ├── xianyu_admin.py #   管理面板 (317行)
│       │   │   └── ...             #   APIs/Context/Cookie/Utils
│       │   ├── execution/          # 10类执行场景 (1,693行)
│       │   │   ├── bounty.py       #   赏金猎人 (226行)
│       │   │   ├── scheduler.py    #   定时调度 (162行)
│       │   │   ├── monitoring.py   #   信息监控 (161行)
│       │   │   ├── task_mgmt.py    #   任务管理 (110行)
│       │   │   ├── social/         #   社媒执行子模块 (1,070行)
│       │   │   │   ├── media_crawler_bridge.py# MediaCrawler桥接 (297行)
│       │   │   │   ├── real_trending.py#  真实热搜数据 (229行)
│       │   │   │   ├── x_platform.py#    X/Twitter平台 (161行)
│       │   │   │   ├── content_strategy.py# 内容策略 (157行)
│       │   │   │   └── xhs_platform.py#  小红书平台 (76行)
│       │   │   └── ...             #   email/brief/docs/meeting/life/dev/project
│       │   ├── trading/            # 高级交易子系统 (1,026行)
│       │   │   ├── protections.py  #   交易保护/熔断 (276行)
│       │   │   ├── weight_optimizer.py# Optuna权重优化 (239行)
│       │   │   ├── strategy_pipeline.py# 策略管道 (225行)
│       │   │   └── ...             #   reentry/position_sync/market_hours
│       │   ├── modules/            # 领域模块 (1,483行)
│       │   │   ├── investment/
│       │   │   │   ├── team.py     #   AI投资团队编排 (777行)
│       │   │   │   ├── pydantic_agents.py# Pydantic智能体 (445行)
│       │   │   │   └── backtester_vbt.py# VBT回测 (257行)
│       │   │   ├── commerce/       #   (已废弃, 电商功能在 src/xianyu/ + src/shopping/)
│       │   │   └── life/           #   (已废弃, 生活功能在 src/execution/life_automation.py)
│       │   ├── shopping/           # 购物比价引擎 (1,119行)
│       │   │   ├── crawl4ai_engine.py# 三级降级爬虫 (650行)
│       │   │   └── price_engine.py #   价格对比引擎 (469行)
│       │   ├── api/                # FastAPI 内控API (2,124行)
│       │   │   ├── rpc.py          #   RPC 远程调用 (925行)
│       │   │   ├── server.py       #   FastAPI 启动 (118行)
│       │   │   └── routers/        #   路由: omega/trading/social/evolution/ws

│       │   ├── gateway/            # 网关层 (520行)
│       │   │   └── telegram_gateway.py# Telegram 统一网关 (519行)
│       │   ├── integrations/       # 外部服务集成 (可选依赖)
│       │   │   └── composio_bridge.py# Composio 250+服务桥接 (~220行)
│       │   ├── evolution/          # 自进化引擎 (1,064行)
│       │   │   ├── engine.py       #   进化核心: GitHub扫描→提案→集成 (762行)
│       │   │   └── github_trending.py# GitHub Trending 抓取 (302行)
│       │   ├── deployer/           # 部署系统 (1,365行)
│       │   │   ├── web_installer.py#   Web安装器 (484行)
│       │   │   ├── deploy_client.py#   部署客户端 (435行)
│       │   │   ├── license_manager.py# 许可证管理 (232行)
│       │   │   └── deploy_server.py#   部署服务端 (157行)
│       │   ├── routing/             # 群聊智能路由包 (1,563行, 8文件)
│       │   │   ├── orchestrator.py #   路由编排器 (核心)
│       │   │   ├── router.py       #   路由引擎
│       │   │   ├── priority_queue.py#  优先级队列
│       │   │   ├── sessions.py     #   会话管理
│       │   │   ├── streaming.py    #   流式输出
│       │   │   ├── models.py       #   数据模型
│       │   │   └── constants.py    #   常量定义
│       │   ├── ~~execution_hub.py~~  # ⚠️ DEPRECATED — 已迁移到 src/execution/ 模块化包
│       │   ├── chat_router.py      # 群聊路由入口 — 实际逻辑已重构到 src/routing/ 包 (1,415行)
│       │   ├── auto_trader.py      # 自动交易引擎 (1,530行)
│       │   ├── trading_system.py   # 交易系统统一入口 (1,431行)
│       │   ├── shared_memory.py    # 共享记忆层 (1,070行)
│       │   ├── monitoring/          # 系统监控包 (1,393行, 7文件)
│       │   │   ├── logger.py       #   结构化日志 (433行)
│       │   │   ├── cost_analyzer.py#   成本分析 (225行)
│       │   │   ├── health.py       #   健康检查 (224行)
│       │   │   ├── anomaly_detector.py# 异常检测 (200行)
│       │   │   ├── metrics.py      #   指标采集 (182行)
│       │   │   └── alerts.py       #   告警通知 (60行)
│       │   ├── risk_manager.py     # 风控引擎 (1,183行)
│       │   ├── trading_journal.py  # 交易日志 (1,170行)
│       │   ├── backtester.py       # 回测引擎 (1,124行)
│       │   ├── broker_bridge.py    # 券商桥接(IBKR) (1,061行)
│       │   ├── ai_team_voter.py    # AI团队投票 (922行)
│       │   ├── context_manager.py  # 上下文管理 (751行)
│       │   ├── decision_validator.py# 决策验证 (734行)
│       │   ├── tool_executor.py    # 工具执行器 (720行)
│       │   ├── ta_engine.py        # 技术分析引擎 (716行)
│       │   ├── backtest_reporter.py# 回测报告 (688行)

│       │   ├── freqtrade_bridge.py # Freqtrade桥接 (672行)
│       │   ├── telegram_ux.py      # Telegram UX 组件 (668行)
│       │   ├── telegram_markdown.py# Markdown→TG格式 (662行)
│       │   ├── litellm_router.py   # LiteLLM统一路由 (653行)
│       │   ├── strategy_engine.py  # 策略引擎 (623行)
│       │   ├── resilience.py       # 韧性层(限流/重试) (615行)
│       │   ├── charts.py           # Plotly图表引擎 (625行)
│       │   ├── invest_tools.py     # 投资工具函数 (625行)
│       │   ├── notifications.py    # Apprise多渠道通知 (588行)
│       │   ├── position_monitor.py # 持仓监控 (570行)
│       │   ├── social_scheduler.py # 社媒定时发布 (542行)
│       │   ├── message_format.py   # 消息格式化 (528行)
│       │   ├── data_providers.py   # 多市场数据源 (509行)
│       │   ├── social_tools.py     # 社媒工具 (418行)
│       │   ├── smart_memory.py     # 智能记忆 (423行)
│       │   ├── notify_style.py     # 通知样式 (398行)
│       │   ├── models.py           # 数据模型 (Pydantic)
│       │   ├── http_client.py      # HTTP客户端
│       │   ├── ocr_service.py      # OCR服务
│       │   ├── ocr_router.py       # OCR路由
│       │   ├── tts_engine.py       # TTS引擎
│       │   ├── structured_llm.py   # 结构化LLM调用
│       │   └── ...                 # 更多模块
│       ├── tests/                  # 测试套件 (31文件, 6,410行)
│       ├── data/                   # 运行时数据 (SQLite/JSON)
│       └── logs/                   # 日志输出
├── apps/
│   ├── openclaw-manager-src/       # 🖥️ Tauri 2 桌面管理端 (React+TS)
│   │   ├── src/                    #   React UI 源码
│   │   └── src-tauri/              #   Rust 后端
│   ├── openclaw/                   # 📋 Bot 配置/Skills/Memory 定义
│   │   ├── AGENTS.md               #   Bot 行为指令
│   │   ├── SOUL.md                 #   Bot 灵魂/人格
│   │   ├── IDENTITY.md             #   Bot 身份
│   │   ├── MEMORY.md               #   记忆策略
│   │   ├── TOOLS.md                #   可用工具
│   │   ├── skills/                 #   技能包
│   │   └── tools/                  #   工具脚本 (GLM-OCR CLI)
│   ├── OpenClaw.app/               # macOS .app 打包
│   ├── openclaw-cli                # CLI 入口
│   └── openclaw-ui                 # Web UI 入口 (占位)
├── tools/
│   ├── installers/                 # 安装脚本
│   └── launchagents/               # macOS 服务管理
├── docker-compose.yml              # Docker 编排
└── docs/
    ├── PROJECT_MAP.md              # ← 你在这里
    ├── README.md
    ├── QUICKSTART.md
    └── business-plan.md
```

---

## 核心模块架构

### 消息处理流水线

```
用户消息 (Telegram)
    │
    ▼
┌─────────────────────────────┐
│ multi_bot.py                │  Handler 注册, 92个命令
│ ├─ CommandHandler (/xxx)    │  ← 92个斜杠命令
│ ├─ MessageHandler (文本)    │  ← 自然语言路由
│ └─ CallbackQueryHandler     │  ← 13个回调模式
└─────────────┬───────────────┘
              │
    ┌─────────┼──────────────┐
    ▼         ▼              ▼
 命令分发    NL匹配        LLM路由
 (mixin)   (66个中文触发)  (chat_router)
    │         │              │
    └─────────┼──────────────┘
              ▼
┌─────────────────────────────┐
│ brain.py (OMEGA 编排器)     │  核心入口
│ 1. intent_parser.py         │  ← NL → 结构化意图 (10种TaskType)
│ 2. task_graph.py            │  ← 意图 → DAG (支持并行依赖)
│ 3. executor.py              │  ← API → 浏览器 → 电话 → 人工
│ 4. response_cards.py        │  ← 结果 → Telegram卡片
└─────────────┬───────────────┘
              │
    ┌─────────┼──────────────┐
    ▼         ▼              ▼
 event_bus   self_heal    cost_control
 (发布订阅)  (6步自愈)    (预算控制)
```

### 关键文件路径和行数

| 模块 | 文件路径 | 行数 | 说明 |
|---|---|---|---|
| 编排器 | `src/core/brain.py` | 1,475 | 所有输入的统一入口 |
| 意图解析 | `src/core/intent_parser.py` | 571 | NL→TaskType+params |
| 任务DAG | `src/core/task_graph.py` | 372 | asyncio DAG 调度 |
| 执行器 | `src/core/executor.py` | 476 | 4路径降级执行 |
| 事件总线 | `src/core/event_bus.py` | 329 | 异步 pub/sub |
| 自愈引擎 | `src/core/self_heal.py` | 627 | tenacity重试+熔断 |
| 协同管道 | `src/core/synergy_pipelines.py` | 356 | 6条跨模块管道 |
| 响应卡片 | `src/core/response_cards.py` | 809 | Telegram UI 生成 |
| 安全层 | `src/core/security.py` | 245 | 输入消毒+权限 |
| 成本控制 | `src/core/cost_control.py` | 227 | 日预算 $50 |

### 10种任务类型 (TaskType)

```python
INVESTMENT    # 投资分析/交易
SOCIAL        # 社媒运营
SHOPPING      # 购物比价
BOOKING       # 预订 (餐厅/酒店/机票)
LIFE          # 生活服务 (快递/日历/账单)
CODE          # 代码/开发任务
INFO          # 信息查询
COMMUNICATION # 通信代理 (邮件/企微通知)
SYSTEM        # 系统管理
EVOLUTION     # 自进化指令
```

### 6种执行器类型 (ExecutorType)

```python
LLM           # LLM 推理
API           # HTTP API 直连
BROWSER       # 浏览器自动化
VOICE_CALL    # AI 电话
LOCAL         # 本地函数调用
HUMAN         # 需要人工介入
CREW          # CrewAI 多智能体
```

---

## 模块分类速查

### AI 核心 (Core)
| 路径 | 行数 | 说明 |
|---|---|---|
| `src/core/brain.py` | 1,475 | OMEGA 编排器 (含上下文注入+响应合成) |
| `src/core/response_synthesizer.py` | 362 | 响应合成层 + Brain上下文收集 (搬运omi) |
| `src/core/proactive_engine.py` | 602 | 主动智能引擎 Gate→Generate→Critic (搬运omi) |
| `src/core/intent_parser.py` | 571 | 意图解析 (jieba + LLM) |
| `src/core/task_graph.py` | 372 | DAG 任务引擎 |
| `src/core/executor.py` | 476 | 多路径执行引擎 |
| `src/core/event_bus.py` | 329 | 异步事件总线 |
| `src/core/self_heal.py` | 627 | 异常自愈 + 熔断 |
| `src/core/synergy_pipelines.py` | 356 | 跨模块协同管道 |
| `src/core/response_cards.py` | 809 | Telegram UI 卡片 (含合成回复优先) |
| `src/core/cost_control.py` | 227 | LLM 成本控制 |
| `src/core/security.py` | 245 | 安全防护层 |
| `src/litellm_router.py` | 653 | LiteLLM 统一路由 |
| `src/structured_llm.py` | — | instructor 结构化输出 |
| `src/chat_router.py` | 1,415 | 群聊意图路由 + 协作编排 |
| `src/context_manager.py` | 751 | 上下文窗口管理 |
| `src/llm_cache.py` | — | diskcache LLM 缓存 |

### 投资/交易系统
| 路径 | 行数 | 说明 |
|---|---|---|
| `src/auto_trader.py` | 1,530 | 自动交易引擎 |
| `src/trading_system.py` | 1,431 | 交易系统统一入口 |
| `src/risk_manager.py` | 1,183 | 风控引擎 (2%规则/日亏限制) |
| `src/trading_journal.py` | 1,170 | 交易日志 + 绩效分析 |
| `src/backtester.py` | 1,124 | 回测引擎 |
| `src/broker_bridge.py` | 1,061 | 券商桥接 (IBKR) |
| `src/ai_team_voter.py` | 922 | AI 投资团队投票 |
| `src/ta_engine.py` | 716 | 技术分析引擎 |
| `src/backtest_reporter.py` | 688 | 回测报告 (Plotly) |
| `src/freqtrade_bridge.py` | 672 | Freqtrade 桥接 |
| `src/strategy_engine.py` | 623 | 策略引擎 |
| `src/decision_validator.py` | 734 | 交易决策验证 |
| `src/position_monitor.py` | 570 | 持仓实时监控 |
| `src/data_providers.py` | 509 | 多市场数据源 |
| `src/invest_tools.py` | 625 | 投资工具函数 |
| `src/quote_cache.py` | — | 行情缓存 |
| `src/rebalancer.py` | — | 组合再平衡 |
| `src/trading/protections.py` | 276 | 交易保护/熔断 |
| `src/trading/weight_optimizer.py` | 239 | Optuna 权重优化 |
| `src/trading/strategy_pipeline.py` | 225 | 策略管道 |
| `src/modules/investment/team.py` | 777 | AI 投资团队编排 |
| `src/modules/investment/pydantic_agents.py` | 445 | Pydantic Agent |

### 社交媒体运营
| 路径 | 行数 | 说明 |
|---|---|---|
| `src/social_scheduler.py` | 542 | 社媒定时发布 (APScheduler) |
| `src/social_tools.py` | 418 | 社媒工具集 |
| `src/execution/social/media_crawler_bridge.py` | 297 | MediaCrawler 桥接 |
| `src/execution/social/real_trending.py` | 229 | 真实热搜数据 |
| `src/execution/social/x_platform.py` | 161 | X/Twitter 平台 |
| `src/execution/social/content_strategy.py` | 157 | 内容策略生成 |
| `src/execution/social/xhs_platform.py` | 76 | 小红书平台 |

### 闲鱼/电商
| 路径 | 行数 | 说明 |
|---|---|---|
| `src/xianyu/xianyu_live.py` | 597 | WebSocket 实时聊天 |
| `src/xianyu/xianyu_agent.py` | 436 | AI 客服 Agent |
| `src/xianyu/goofish_monitor.py` | 332 | 闲鱼商品监控 |
| `src/xianyu/xianyu_admin.py` | 317 | 后台管理 |
| `src/shopping/crawl4ai_engine.py` | 650 | crawl4ai 三级降级爬虫 |
| `src/shopping/price_engine.py` | 469 | 多平台价格对比 |

### 执行场景 (10类)
| 路径 | 行数 | 场景 |
|---|---|---|
| ~~`src/execution_hub.py`~~ | ~~3,808~~ | ~~已废弃~~ ✅ 迁移到 `src/execution/` 模块化包 |
| `src/execution/bounty.py` | 226 | 赏金猎人自动接单 |
| `src/execution/scheduler.py` | 162 | 定时任务调度 |
| `src/execution/monitoring.py` | 161 | 信息监控提醒 |
| `src/execution/task_mgmt.py` | 110 | 智能任务管理 |
| `src/execution/daily_brief.py` | 47 | 每日简报 |
| `src/execution/doc_search.py` | 99 | 文档检索 |
| `src/execution/email_triage.py` | 68 | 邮件分类 |

### 工具层
| 路径 | 行数 | 说明 |
|---|---|---|
| `src/tools/export_service.py` | 540 | Excel/CSV 导出 |
| `src/tools/comfyui_client.py` | 486 | ComfyUI 图片生成 |
| `src/tools/code_tool.py` | 307 | 代码执行沙箱 (RestrictedPython) |
| `src/tools/free_apis.py` | 225 | 免费 API 聚合 |
| `src/tools/docling_service.py` | 215 | 文档理解引擎 (PDF/DOCX→MD) |
| `src/tools/tavily_search.py` | 206 | AI 搜索 (Tavily) |
| `src/tools/fal_client.py` | 190 | fal.ai 图片 API |

### 基础设施
| 路径 | 行数 | 说明 |
|---|---|---|
| `src/monitoring/` | 1,393 | 系统监控包 (logger/metrics/health/alerts/anomaly/cost) |
| `src/shared_memory.py` | 1,070 | 共享记忆层 (mem0) |
| `src/resilience.py` | 615 | 韧性层 (限流/重试/熔断) |
| `src/notifications.py` | 588 | Apprise 多渠道通知 |
| `src/telegram_markdown.py` | 662 | Markdown 转换 (mistletoe) |
| `src/log_config.py` | — | loguru 日志配置 |
| `src/api/rpc.py` | 925 | RPC 远程调用 |
| `src/api/server.py` | 118 | FastAPI 服务器 |
| `src/gateway/telegram_gateway.py` | 519 | Telegram 统一网关 |
| `src/evolution/engine.py` | 762 | 自进化核心 |
| `src/evolution/github_trending.py` | 302 | GitHub Trending 抓取 |

---

## 依赖清单: 30+ 高星开源项目集成

| # | 项目 | GitHub Stars | 用途 | 替换了什么 |
|---|---|---|---|---|
| 1 | browser-use | 81k⭐ | AI 浏览器代理 | 自研 ai_browser.py |
| 2 | crawl4ai | 62.4k⭐ | 结构化网页抽取 | httpx+bs4 爬虫 |
| 3 | mem0 | 50k⭐ | AI 记忆层 | shared_memory RAG |
| 4 | Freqtrade | 47.8k⭐ | 量化交易框架 | 自研 backtester |
| 5 | CrewAI | 46.6k⭐ | 多Agent协作 | ai_team_voter |
| 6 | LiteLLM | 39k⭐ | 统一LLM路由 | free_api_pool.py |
| 7 | CCXT | 35k⭐ | 加密货币交易所 | — |
| 8 | jieba | 34.8k⭐ | 中文分词 | regex 关键词匹配 |
| 9 | loguru | 23.7k⭐ | 结构化日志 | stdlib logging |
| 10 | Langfuse | 23.4k⭐ | LLM 可观测 | 自研 CostAnalyzer |
| 11 | FastAPI | 80k⭐ | 内控API | — |
| 12 | Plotly | 18.4k⭐ | 交互式图表 | matplotlib |
| 13 | Apprise | 16.1k⭐ | 多渠道通知 | 仅 Telegram |
| 14 | AKShare | 14k⭐ | A股数据 | — |
| 15 | PyAutoGUI | 12k⭐ | 桌面控制 | — |
| 16 | DrissionPage | 11.6k⭐ | 反检测浏览器 | — |
| 17 | Optuna | 11k⭐ | 超参优化 | — |
| 18 | instructor | 10k⭐ | 结构化LLM输出 | json_repair+regex |
| 19 | edge-tts | 10.3k⭐ | 文本转语音 | — |
| 20 | Phoenix OTEL | 9k⭐ | LLM可观测 | — |
| 21 | Uvicorn | 9k⭐ | ASGI服务器 | — |
| 22 | APScheduler | 6.3k⭐ | 定时任务 | — |
| 23 | tenacity | 6k⭐ | 重试库 | 假重试 |
| 24 | pandas-ta | 5k⭐ | 技术分析指标 | 手写 RSI/MA |
| 25 | json-repair | 4.6k⭐ | JSON容错解析 | json.loads |
| 26 | qrcode | 4.5k⭐ | 二维码生成 | — |
| 27 | openpyxl | 3.7k⭐ | Excel读写 | — |
| 28 | diskcache | 2.8k⭐ | SQLite缓存 | — |
| 29 | stamina | 1.4k⭐ | 声明式重试 | — |
| 30 | fpdf2 | 1.1k⭐ | PDF生成 | — |
| 31 | mistletoe | 1k⭐ | Markdown AST | regex 清理 |
| 32 | PyrateLimiter | 485⭐ | 令牌桶限流 | 手写滑动窗口 |

---

## 命令系统概览

### 92个斜杠命令 (按功能分组)

**基础 (6个)**
`/start` `/help` `/clear` `/status` `/config` `/settings`

**信息 (4个)**
`/news` `/metrics` `/lanes` `/context`

**会话 (3个)**
`/compact` `/discuss` `/stop_discuss`

**模型管理 (3个)**
`/model` `/pool` `/cost`

**投资分析 (9个)**
`/quote` `/market` `/portfolio` `/invest` `/ta` `/scan`
`/accuracy` `/equity` `/targets`

**交易操作 (10个)**
`/buy` `/sell` `/watchlist` `/trades` `/signal` `/performance`
`/review` `/journal` `/reset_portfolio` `/autotrader`

**风控/监控 (4个)**
`/risk` `/monitor` `/tradingsystem` `/rebalance`

**回测 (1个)**
`/backtest`

**IBKR 实盘 (6个)**
`/ibuy` `/isell` `/ipositions` `/iorders` `/iaccount` `/icancel`

**社媒运营 (16个)**
`/topic` `/xhs` `/post` `/social_plan` `/social_repost` `/social_launch`
`/social_persona` `/post_social` `/post_x` `/post_xhs` `/xwatch` `/xbrief`
`/xdraft` `/xpost` `/xhsdraft` `/xhspost`

**闲鱼 (1个)**
`/xianyu`

**社媒日历/报告 (2个)**
`/social_calendar` `/social_report`

**执行场景 (5个)**
`/ops` `/dev` `/brief` `/hot` `/hotpost`

**协作 (3个)**
`/collab` `/lane` `/draw`

**工具 (5个)**
`/memory` `/voice` `/export` `/qr` ~~`/view`~~ (已移除)

**周报 (1个)**
`/weekly`

### 66+ 中文自然语言触发器

所有在 `src/bot/message_mixin.py` 的 `_match_chinese_command()` 中定义:

| 类别 | 示例触发词 |
|---|---|
| 系统 | "开始" "帮助" "清空对话" "状态" "配置" "成本" "上下文" "压缩" |
| 信息 | "新闻" "科技早报" "指标" "分流规则" |
| 执行场景 | "整理邮箱" "行业简报" "任务优先级" "赏金猎人" "扫赏金" |
| 社媒 | "社媒计划" "一键发文" "热点发文" "双平台改写" "数字生命首发" |
| X/小红书 | "发...到小红书" "发...到推特" "研究...题材" |
| 监控 | "添加资讯监控" "运行资讯监控" "提醒我..." |
| 投资 | "帮我投资" "自动交易" "今天买什么" "扫描市场" |
| 行情 | "分析 AAPL" "TSLA 多少钱" "查行情" "市场概览" |
| 持仓 | "我的持仓" "绩效" "复盘" "交易日志" |
| 风控 | "风控" "熔断" "持仓监控" "交易系统" |
| 交易 | "启动自动交易" "停止自动" "回测" "再平衡" |
| 讨论 | "投资讨论..." "分析一下..." |

### 13个回调按钮模式 (CallbackQueryHandler)

```
^itrade          # 交易确认
^help:           # 帮助导航
^onboard:        # 新手引导
^fb\|            # 反馈评分
^mem_            # 记忆管理 (翻页/清除)
^settings\|      # 设置切换
^cmd:            # 通知操作按钮
^social_confirm: # 社媒发布确认
^ops_            # 执行场景菜单
^(ta_|buy_|watch_) # 行情操作 (技术分析/买入/加自选)
^(trade:|bt:|ta:|analyze:|news:|evo:|retry:|shop:|post:) # OMEGA响应卡片
^noop$           # 空操作 (已处理标记)
+ InlineQueryHandler # @bot 搜股票/记忆
```

---

## 7 Bot 团队架构

| Bot ID | 模型 | 投资角色 | 口头禅 |
|---|---|---|---|
| `qwen235b` | Qwen-3-235B | 宏观猎手 | "先说结论" |
| `gptoss` | GPT-OSS-120B | 图表狙击手 | "一句话：" |
| `claude_sonnet` | Claude Sonnet 4.5 | 交易指挥官(拍板) | "等一下，这里有个问题" |
| `claude_haiku` | Claude Haiku 4.5 | 市场雷达(先发) | "收到，马上" |
| `deepseek_v3` | DeepSeek V3.2 | 风控铁闸 | "容我细说" |
| `claude_opus` | Claude Opus 4.5 | 首席策略师 | "我只说一次" |
| `free_llm` | free-pool-best | 免费万能助手 | "今天用的是" |

**投资协作流程** (`/invest` 触发):
1. Haiku 先扫 → 2. Qwen 宏观 → 3. GPT-OSS 技术面 → 4. DeepSeek 风控 → 5. Sonnet 拍板

**交易铁律**: 超短线 1-5天 | 单笔风险 ≤ 2%($40) | 日亏限 $100 | R:R ≥ 1:2

---

## 已知限制

### 架构限制
- ~~**execution_hub.py 是巨石文件** (3,808行)~~ — ✅ v3.0 全部迁移到 `src/execution/` 模块化包
- **message_mixin.py 反编译来源** — 文件头有 `Decompyle++` 标记，非原始源码
- ~~**execution_hub.py 同样是反编译**~~ — ✅ 已标记 FULLY DEPRECATED，不再被运行时加载

- 微信端 — Apprise 支持企业微信 webhook 通知推送，但无微信个人号聊天机器人功能

### 可选依赖 (注释/未安装)
- `freqtrade` — 量化框架，需手动 `pip install freqtrade` (GPL-3.0)
- `ib_insync` — IBKR 实盘券商，不安装则自动降级模拟盘
- MongoDB — 支持但默认不启用

### 模块状态
- ~~`src/modules/commerce/`~~ — ✅ 已清理（2026-04-18），电商功能已迁移至 `src/xianyu/` + `src/shopping/`
- ~~`src/modules/life/`~~ — ✅ 已清理（2026-04-18），生活功能已迁移至 `src/execution/life_automation.py`
- ~~`src/senses/`~~ — ✅ 已清理（2026-04-18），感知功能已迁移至 `src/tools/` (OCR/STT/图片处理)
- ~~`src/actions/`~~ — ✅ 已清理（2026-04-18），动作功能已迁移至 `src/core/executor.py`
- ~~`src/execution_hub.py`~~ — ✅ 已清理（2026-04-18），功能已迁移至 `src/execution/` 模块化包
- `src/chat_router.py` — ⚠️ 保留作为向后兼容层，实际逻辑在 `src/routing/` 包（被 3 个文件引用）
- 部分 executor 路径 (VOICE_CALL, HUMAN) 为框架定义，待实际集成

### 运行环境
- Python 3.12 (macOS, venv: `.venv312`)
- 所有可选模块均有 `try/except ImportError` 降级处理
- 需要大量 API Key (OpenAI/Claude/SiliconFlow/Deepgram/fal/Jina 等)

---

## 最近变更摘要

### 架构重构 (Tier 1-5)

**Tier 1 — 核心引擎重建**
- 搭建 OMEGA 核心: `brain.py` / `intent_parser.py` / `task_graph.py` / `executor.py`
- 异步事件总线 `event_bus.py` 替代直接函数调用
- 协同管道 `synergy_pipelines.py`: 6条跨模块数据链路

**Tier 2 — 高星项目搬运**
- LiteLLM 替代 free_api_pool.py (935行→653行)
- mem0 升级共享记忆层
- browser-use + DrissionPage 双引擎浏览器自动化
- CrewAI 升级多Agent协作

**Tier 3 — 交易系统完善**
- 多市场数据源: yfinance + AKShare + CCXT
- 风控引擎: 2%规则 / 日亏限额 / R:R 审查
- 回测报告: Plotly 可视化 + PDF 导出
- 交易保护: 熔断器 / 再入场队列 / 仓位同步

**Tier 4 — 工具层增强**
- 购物比价: crawl4ai 三级降级链
- 多渠道通知: Apprise 100+ 渠道
- Markdown 转换: mistletoe AST 级别
- 图表引擎: Plotly K线/瀑布/仪表盘

**Tier 5 — 韧性与可观测**
- 自愈引擎: tenacity 真实重试 + 熔断器
- 限流: PyrateLimiter 令牌桶
- LLM 缓存: diskcache 持久化
- 可观测: Langfuse + Phoenix OTEL 双栈

### Manager 桌面端

#### C-端页面 (面向终端用户)
| 页面 | 组件 | 说明 |
|---|---|---|
| Home | `Home/index.tsx` | 首页 Dashboard — 今日简报 + 模块状态 + 通知 + AI 建议 |
| Assistant | `Assistant/index.tsx` | AI 助手 — 4 模式 (闲聊/投资/执行/创作) + Markdown 渲染 |
| Portfolio | `Portfolio/index.tsx` | 我的资产 — 5 tabs (持仓概览/交易决策/自动交易/回测分析/交易日志) |
| Bots | `Bots/index.tsx` | 我的机器人 — 4 sections (闲鱼客服/社媒驾驶/自动化脚本/通知中心) |
| Store | `Store/index.tsx` | 插件商店 — App Store 风格 + Evolution 数据优先 |
| Onboarding | `Onboarding/index.tsx` | 新用户向导 — 分步引导配置 |

#### B-端页面 (开发者/高级用户)
| 页面 | 组件 | 说明 |
|---|---|---|
| Dashboard | `Dashboard/` | 系统总览大屏 |
| ExecutionFlow | `ExecutionFlow/` | xyflow 节点可视化 |
| Logs | `Logs/` | 实时日志流 WebSocket |
| Evolution | `Evolution/` | 自进化引擎面板 |
| Social | `Social/` | 社媒运营面板 |
| Settings | `Settings/` | 系统设置 |

- Tauri 2 + React + shadcn 完整重构
- 实时日志流 WebSocket 桥接

### 近期修复
- Gateway 启动路径对齐
- Manager 面板错误全面修复
- 模型配置升级 + 免费渠道扩充
- 部署结构整理与路径修复

---

## 快速导航

| 我要... | 去看... |
|---|---|
| 理解消息如何被处理 | `src/core/brain.py` → `intent_parser.py` → `task_graph.py` |
| 添加新的斜杠命令 | `src/bot/multi_bot.py` (注册) + 对应 `cmd_*_mixin.py` (实现) |
| 添加中文触发词 | `src/bot/message_mixin.py` → `_match_chinese_command()` |
| 理解群聊路由 | `src/chat_router.py` |
| 修改 Bot 人设 | `config/bot_profiles.py` |
| 添加新交易策略 | `src/trading/strategy_pipeline.py` + `src/strategy_engine.py` |
| 添加新的工具 | `src/tools/` 目录 + `src/core/executor.py` 注册 |
| 修改社媒发布 | `src/execution/social/` + `src/social_scheduler.py` |
| 修改闲鱼客服 | `src/xianyu/xianyu_agent.py` + `xianyu_live.py` |
| 添加新的API端点 | `src/api/routers/` + `src/api/server.py` 注册 |
| 理解自愈流程 | `src/core/self_heal.py` |
| 修改 LLM 路由 | `src/litellm_router.py` |
| 调整风控规则 | `src/risk_manager.py` + `src/trading/protections.py` |
| 修改通知格式 | `src/notify_style.py` + `src/notifications.py` |
| 运行测试 | `cd packages/clawbot && pytest` |
| 启动 Bot | `cd packages/clawbot && python multi_main.py` |
| 启动 Manager | `cd apps/openclaw-manager-src && npm run tauri:dev` |
| Docker 部署 | `docker-compose up -d` |

---

## 用户痛点地图 (2026-03-23 立项)

> CPO 视角：基于项目全景 + 已知问题 + 竞品分析的深度痛点挖掘

### 用户画像

| 画像 | 描述 | 占比估算 |
|------|------|----------|
| **超短线投资者** | 1-5 天持仓，多市场(美股/A股/加密)，需要快速决策+风控 | 40% |
| **效率极客/独立开发者** | 用 Telegram 做个人控制中心，自动化日常 | 25% |
| **闲鱼卖家** | 需要 7×24 AI 客服，自动砍价应对 | 20% |
| **社媒运营者** | 小红书+X 双平台内容分发 | 15% |

### 痛点地图

| 用户旅程阶段 | 用户行为 | 当前体验 | 真实痛点 | 痛点烈度 |
|------------|--------|---------|---------|---------|
| 投资 — 决策 | 问 bot "AAPL 今天能买吗" | ~~5 模型串行投票，结果详尽~~ v3.0 团队分析+信号验证 | ~~AI 说买但不知道历史胜率，缺回测验证~~ ✅ quick_signal_validation 自动附带胜率 | ~~🔥🔥🔥🔥🔥~~ ✅ |
| 投资 — 执行 | 发 /buy AAPL | ~~Alpaca 纸盘可用，IBKR 实盘未接入~~ ✅ IBKR 实盘已接入 | ~~模拟盘的"执行成功"毫无意义~~ ✅ 实盘下单+成交确认 | ~~🔥🔥🔥🔥🔥~~ ✅ |
| 投资 — 风控 | 持仓被套 | ~~有风控引擎但无主动推送~~ v2.0 三级预警 | ~~缺实时推送当价格接近止损位~~ ✅ 已实现 | ~~🔥🔥🔥🔥~~ ✅ |
| 投资 — 复盘 | 想看本周战绩 | ~~纯文字~~ ✅ Plotly 图表+收益曲线 | ~~纯文字看不出趋势，缺可视化收益曲线~~ ✅ 已实现 | ~~🔥🔥🔥~~ ✅ |
| 闲鱼 — 客服 | 买家砍价 | ~~每次还要人工确认~~ ✅ 底价注入自动成交 | ~~缺底线价自动成交~~ ✅ 已实现 | ~~🔥🔥🔥~~ ✅ |
| 社媒 — 发文 | 想发小红书/X | ~~手动切平台~~ ✅ 一键双平台同发 | ~~手动切平台复制粘贴，缺一键双平台同发~~ ✅ 已实现 | ~~🔥🔥🔥🔥~~ ✅ |
| 社媒 — 分析 | 想看哪篇效果好 | ~~`/social_report` 有但数据浅~~ ✅ 真实互动数据+平台聚合+Top帖子 | ~~当前"分析"基本靠猜，缺真实互动数据~~ ✅ 浏览器采集→存储→展示全通 | ~~🔥🔥🔥~~ ✅ |
| 上手 — 学习 | 第一次用 bot | ~~有 onboarding 引导~~ v2.0 自然语言直达 | ~~75 个命令太多不知道从哪开始~~ 说中文即可操作 | ~~🔥🔥🔥🔥~~ ✅ |
| 日常 — 提醒 | "明天下午3点提醒我" | ~~dateparser 已接入~~ v2.0 重复提醒+自然语言时间 | ~~不支持重复提醒+日历集成~~ ✅ 每天/每周/每月/工作日重复 | ~~🔥🔥~~ ✅ |

### 竞品对标

| 竞品 | 核心功能 | 我们的差异化优势 |
|------|--------|----------------|
| chatgpt-on-wechat (19k⭐) | 微信/企微接入 ChatGPT | 75 功能命令 vs 纯聊天；多模型路由 vs 单模型 |
| Freqtrade (47.8k⭐) | 加密货币自动交易 | 覆盖三市场；自然语言交互 vs YAML配置 |
| AutoGPT/AG2 (40k⭐) | 通用自主 Agent | 成本控制 $50/天；垂直场景深耕 vs 通用泛化 |

### 核心护城河

**主护城河：工作流锁定** — 投资+闲鱼+社媒+生活全绑定，替换成本极高
**辅助护城河：技术复杂度** — 50+ LLM deployment 运维 + 中文场景适配 + 7 Bot 编排
