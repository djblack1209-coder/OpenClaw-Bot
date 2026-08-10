# OpenClaw Bot — 项目全景地图

> 最后更新: 2026-08-10 (JIYU AI v0.1.173-jiyu.31344140382、真实生产复验与中国/海外站点分流前置审计) | AI 开发助手请先读完本文再开始工作 | 当前健康状态以 `docs/current/current-baseline.md` 为准

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
| Tauri 2 | 2.11 | Rust 桌面壳（Cargo.lock 固定） |
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

本节只记录稳定职责和入口，不记录文件数、代码行数或测试数量；这些易漂移数字必须由验证命令实时生成，不能作为架构事实写入地图。

```
OpenEverything/
├── AGENTS.md                       # AI 开发入口、质量门与热点边界
├── Makefile                        # 本地 CI、锁检查、构建和回滚统一入口
├── docs/                           # 扁平编号文档；项目地图、注册表、运维、健康和变更记录
├── packages/
│   ├── clawbot/                    # Python 3.12 后端
│   │   ├── multi_main.py           # 主事件循环、Bot 和有状态服务生命周期入口
│   │   ├── requirements-lock.txt   # Linux x86_64 哈希锁
│   │   ├── requirements-lock-macos.txt # macOS arm64 哈希锁
│   │   ├── src/
│   │   │   ├── core/               # Brain、EventBus、所有者循环、主动引擎和成本/安全控制
│   │   │   ├── api/                # FastAPI 服务器、认证、RPC 兼容门面和领域路由
│   │   │   ├── bot/                # Telegram Bot 与命令 mixin
│   │   │   ├── trading/            # 交易生命周期、状态机、保护和调度任务
│   │   │   ├── xianyu/             # 闲鱼实时客服、履约状态、管理 API 与 Cookie 生命周期
│   │   │   ├── execution/          # 定时任务及社媒、生活、文档等执行域
│   │   │   ├── routing/            # 群聊路由、会话、优先队列和流式输出
│   │   │   ├── integrations/       # CLIAnything、Composio、Skyvern 等可选集成
│   │   │   └── modules/            # 投资等领域模块
│   │   └── tests/                  # Python 回归、跨线程/事件循环和安全合同
│   ├── openclaw-npm/               # 上游 OpenClaw 源码快照；不是桌面安装版本事实源
│   └── new-api-upstream/            # New-API 上游子模块；遵循其子树专属约束
├── apps/
│   ├── openclaw-manager-src/       # React/TypeScript UI + Tauri 2 Rust 本机控制面
│   │   └── src-tauri/npm-runtime-lock/ # OpenClaw/MCP 直接与传递依赖完整性锁
│   ├── sub2api/                    # JIYU AI 生产底座（Oracle 受管二进制，不在仓库内复制）
│   └── openclaw/                   # Bot 人设、Skills 和 Memory 运行资产，路径不可移动
├── scripts/                        # 健康检查、发布、回滚、迁移与运营脚本
├── tools/launchagents/             # macOS 服务定义
└── .github/workflows/              # Linux、Node 和桌面静态发布门
```

`packages/clawbot/src/core/loop_owner.py` 是跨线程调用 Brain、EventBus、IBKR、闲鱼实时客户端和社媒调度器时复用的事件循环所有权边界；调用线程不得直接操作这些对象持有的异步资源。

`packages/clawbot/src/xianyu/operations_projection.py` 只接受普通不可变快照，一次生成售卖就绪、循环观察和买家进度；HTTP/background adapter 不得把 WebSocket、owner-loop 或文件句柄传入投影层。JIYU AI 生产数据由 Sub2API PostgreSQL、专用 Redis 和受管更新代理统一负责，仓库不再保留旧 Node 网关副本。

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

### P0 安全边界（2026-08-03）

- **入口身份**：Telegram 主 Bot、Gateway、Inline Query、语音、图片和文档都先检查正整数 `ALLOWED_USER_IDS`；白名单为空或全非法时启动失败，运行时也默认拒绝。
- **Agent 工具**：自动 LLM 循环不提供文件、Shell、代码执行和记忆写入工具；外部网页内容进入上下文后，当前请求后续工具权限全部撤销。`/agent` 使用只读 `ToolCallingAgent`，不再使用本地 `CodeAgent`；Bash 禁用 Git，`/claude` 不接受远程提示词。Python 代码仅在受限子进程执行 RestrictedPython 字节码，Node/Shell 代码执行关闭。
- **交易状态**：真实持仓只接受券商确认的正数成交量；未决订单等待券商对账，失败/取消/零成交不删持仓，模拟回退不写真实日志。自动交易与空闲强制交易默认关闭。
- **社媒发布**：自动化只生成草稿；发布必须依次通过内容审核快照、短时一次性最终确认和原子消费。发布中/已发布草稿不可变；外部成功但本地状态冲突时追加对账审计并明确禁止重发。
- **客户隔离**：JIYU 在共享 New-API 管理账号之上维护客户 Token 归属；看板、日志、更新、删除和导入均按归属过滤。额度从客户已购余额划转，禁止无限 Key。
- **桌面控制面**：管理器新建本地 `gateway.auth.token` 时只生成强随机字符串；当前受管运行时精确锁定 `OpenClaw 2026.7.2-beta.7`，Token/密码/远程 SecretRef 原样保留并交给官方校验。354 个直接/传递 npm 包由内嵌 SHA-512 锁安装。MCP Store 只展示受管运行包目录，不返回 command/args/env，也不伪装成已建立的 stdio 会话；真实 MCP 配置仍由 CC Switch/OpenClaw 官方配置链负责。配置跨实例原子写入，WebView 只接收脱敏配置，服务停止只针对管理器登记且核验通过的 PID，WebView 不直接拥有文件系统权限。
- **运行时真值**：G4F、Kiro、Ollama、IBKR 和 VPS 心跳全部改为显式开关；未启用能力不进入 LiteLLM 路由、fallback 或交易定时器。健康检查同时验证必需 LaunchAgent 的 `running + PID` 和真实 HTTP/TCP 端点，不再用“服务已加载”代替“服务可用”。
- **ClawBot Telegram 补号边界（2026-08-09）**：本地 LaunchAgent `ai.openclaw.clawbot-agent` 已在安全补丁后重载，现以新 PID 运行且无需回滚；浏览器无认证 Telegram Web 会话，未发送真实 `/jiyu_replenish status`，外部命令响应仍未验证。
- **部署拓扑**：macOS LaunchAgent 是当前唯一 OpenEverything/ClawBot 活跃主实例。腾讯云旧备用实例因主心跳长期失效且进程持续启动失败，已于 2026-08-07 备份后停用其服务和 30 秒故障转移定时器；腾讯云上的微信接收、OpenClaw 云控和 SillyTavern 仍独立运行。恢复 VPS 自动接管前必须重新建立实时心跳、单主写入隔离和真实 Telegram 用户链路验收。
- **JIYU AI / CC中转底座（2026-08-10）**：Oracle ARM 主站 `jiyu.245334.xyz` 对外品牌为 `JIYU AI`，当前运行基于官方 Sub2API `v0.1.173` 固定提交构建的 `v0.1.173-jiyu.31344140382`。Sub2API 只监听 `127.0.0.1:18080`，专用 Redis 只监听 `127.0.0.1:16379`，PostgreSQL 使用独立 `sub2api` 数据库。DeepSeek、Kimi、SiliconFlow、智谱各有 1 个国内账号、分组和渠道，国内白名单数量为 2/4/8/61，文本分组倍率固定为账号倍率 +0.05。当前按用户要求使用原生 Channel Monitor V1 主动探测；V2 配置和数据保留，不是阻塞项。内容预拦截和 Cloudflare WAF/DDoS、注册/登录限流正常。中国大陆到中国站点、其他地区到 Oracle 的站点级分流仍等待独立中国 origin、域名/ICP 与 Cloudflare 方案确认，Oracle 继续是账户、余额、订单、API 密钥和账本唯一事实源。

### 2026-08-05 全维度审计收口

- **安全**：SSRF 逐跳固定、可信代理限流、最终日志脱敏、闲鱼短时 HttpOnly 管理会话、CLI 远程安装关闭和依赖/容器供应链门均失败关闭。
- **可靠性**：Intel Brief 真实旧库已从 schema v3 备份并迁移到 v4；每日备份以 SQLite 在线快照、双层校验、恢复演练和 macOS LaunchAgent 自动执行。
- **架构**：JIYU runtime store 与闲鱼运营投影成为独立 deep module；RPC 兼容门面冻结，新功能继续进入领域 router。
- **发布**：PR 覆盖所有目标分支，ShellCheck、Gitleaks、npm/pip/RustSec、固定 Action SHA、Docker 哈希锁和非 root 冒烟进入本地/远端门禁。
- **边界**：离机 GPG 公钥、第三方凭据回执、Developer ID/公证和真实平台付费仍由资产所有者掌握；代码不伪造这些证据。

### 五维 8 分目标历史评分（2026-08-04）

以下评分是 2026-08-04 的历史快照，只说明当时的 macOS 单机与 Oracle 内测拓扑，不是当前生产完成结论。当前状态以 `docs/current/current-baseline.md` 为准。

| 维度 | 分数 | 达标证据 | 保留边界 |
|---|---:|---|---|
| 功能完整度 | 9.0 | 10 门通过 9 门；支付、实盘 SELL、闲鱼履约、认证、Scheduler、MCP、Assistant、桌面安装与恢复均有合同 | 未完成真实商户小额支付，F10=0 |
| 测试与发布 | 9.0 | 10 门通过 9 门；本地 CI、覆盖率、前端/Rust、干净安装、供应链、签名、DMG、异版本回滚和截图可复核 | 当前工作树无远端 Linux runner 新产物，T10=0 |
| 系统架构 | 8.0 | 10 门通过 8 门；所有者循环、事务外 I/O、原子履约、单一注册表、Bulkhead 与生命周期边界有回归 | 巨型入口和 JSON runtime 兼容层各计 0 |
| 安全边界 | 8.0 | 10 门通过 8 门；资金、支付、履约、身份、本机执行、限流、供应链和密钥扫描失败关闭 | 平台凭据轮换证明与 Developer ID/公证各计 0 |
| 可维护性 | 8.0 | 10 门通过 8 门；依赖锁、lint/build、覆盖率、文档门、注册表、热点命令、版本源和回滚清单可复现 | 巨型热点未清零、当前工作树远端 CI 产物缺失，各计 0 |
| **综合** | **8.4** | `(9+9+8+8+8)/5`；历史评分，不作为当前生产事实 | 不扩大到尚未验收的公开发行边界 |

### 每日资讯 V2 子系统（2026-08-04）

```text
六源采集
  -> 统一 ContentItem 契约
  -> 日期 fail-closed / URL 规范化 / 事件与实体去重
  -> 确定性评分 / 来源与类别配额 / 多样化 Top 3
  -> CC Switch 三端只读翻译池 + SQLite 翻译缓存
  -> Telegram sendPhoto + inline callback + 完整 brief 回放
  -> delivery claim / update offset / LaunchAgent / runtime health
```

- 中央视图由独立 SQLite V3 承载：内容事实、观察、候选决定、结构化 brief、本地化、投递 artifact、媒体 `file_id`、逐事件尝试、来源 LKG、基线水位和投递 claim 均可审计。
- tgNetDisc 采用“搬核心、不搬服务”的方案 C：复用 Telegram `file_id` 存储思想，不引入 Go 服务、公开文件代理或第二个 update poller；缓存按脱敏 Bot 身份、渲染版本和内容哈希隔离。
- 翻译池只读本机 CC Switch 数据库，最多选择三个 HTTPS OpenAI 兼容端点；Key 仅在内存使用，不进入日志、证据、持久化缓存或对象 `repr`。
- 生产调度合同收口为 Asia/Singapore 08:30；可选每周一 08:30。系统不再展示唯一 LaunchAgent 无法兑现的 09:00/12:00/20:00 选项。

| 维度 | 分数 | 证据 | 保留边界 |
|---|---:|---|---|
| 内容正确性与新鲜度 | 9.1 | 日期缺失/过旧 fail-closed、Senate 排序后限额、13F 聚合、事件去重、GitHub 7 日冷却、空成功不覆盖 LKG | 上游源真实性仍依赖公开来源本身 |
| Telegram 体验 | 8.8 | 候选 3 深色封面、管道 rank 保序的 Top 3、完整回放、分类/语言按钮、无重叠同视口 QA | Telegram 客户端字体渲染存在平台差异 |
| 国际化 | 8.7 | 中文/English 菜单与内容、实体遮罩、字段缓存、三端 failover、45 秒总 deadline、降级后恢复重试 | 翻译质量仍需抽样人工复核 |
| 可靠性与幂等 | 8.8 | 投递 claim lease、逐事件去重、callback 先确认、partial/unknown offset 终态、媒体失效重传 | 7 日真实 SLI 尚在新版本部署后自然积累 |
| 安全 | 8.9 | CC Switch 只读、HTTPS-only、Key 不落盘/不进 repr、HTML 回显转义、证据脱敏 | 本机用户账户仍是私有环境的信任边界 |
| 运维与可观测 | 8.5 | 六源 health/LKG、只读 runtime health、心跳、30 天/2000 文件/100MB 门、SQLite quick check | 首次部署后的周期/投递 SLI 为 warmup，不冒充已达 95%/99% |
| 测试与文档 | 8.8 | Intel 全量 345 项、Ruff/format/py_compile/diff 门、V0/V2->V3 迁移、视觉 QA 和回滚手册 | 真实次日跨日运行仍需自然观测 |
| **综合** | **8.8** | 七维工程门均超过 8 分 | 分数表示当前单机 Telegram 内测发布能力，不等于长期 SLI 已完成采样 |

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
| `src/chat_router.py` | — | ✅ 已删除 (Sprint 5)，全部引用迁移到 `src/routing/` 包 |
| `src/context_manager.py` | 751 | 上下文窗口管理 |
| `src/llm_cache.py` | — | SQLite3 LLM 缓存 (utils_cache) |

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
| 28 | ~~diskcache~~ | 2.8k⭐ | ~~SQLite缓存~~ | ❌ 已移除(CVE)，替换为自研 utils_cache |
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
- ~~`src/chat_router.py`~~ — ✅ 已删除（2026-04-22），全部引用迁移到 `src/routing/` 包
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
- LLM 缓存: sqlite3 自研持久化 (utils_cache)
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
| 运行测试 | `make test` |
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
| 社媒 — 发文 | 想发小红书/X | 统一草稿队列 + 双平台适配 + 人工最终确认 | 支持一处编辑和分平台发布，但每次外发必须审核并使用一次性确认，定时器不能替用户直发 | 🔒 安全闭环 |
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
