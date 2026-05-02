# ClawBot 开发者指南

> 项目位置: `/Users/blackdj/Desktop/OpenClaw Bot/packages/clawbot`
> 版本: v5.0 (Mixin 架构版)
> 最后更新: 2026-03-27 (R9 更新: 修正项目路径 + 测试计数 + 依赖安装命令)

---

## 一、项目概述

ClawBot 是一个 **Telegram 多模型 AI 自动交易系统**，核心能力：
- 7 Bot 多智能体系统 (Mixin 架构，OMEGA v2.0 引擎)
- LiteLLM Router: 110 deployments, 17 LLM 提供商
- IBKR 盈透证券实盘/模拟交易
- 技术分析信号引擎（RSI/MACD/EMA/布林带/ATR）
- AI 团队投票 → 风控校验 → 自动下单完整流水线
- 仓位管理、止损止盈、每日亏损限额、熔断保护
- 群聊协作（多 Bot 在同一群组，智能路由消息）
- 闲鱼自动客服 + 自动发货 + 收入报表
- 社媒自动驾驶 (X/小红书)
- VPS 备用节点 + 心跳 failover

---

## 二、快速开始

### 安装依赖

```bash
cd "/Users/blackdj/Desktop/OpenClaw Bot/packages/clawbot"
python3.12 -m venv .venv312
.venv312/bin/pip install -r requirements.txt
```

### 启动服务

```bash
# 启动
python3 multi_main.py

# 后台运行
nohup python3 multi_main.py &

# 使用运维脚本
./scripts/clawctl.sh start
./scripts/clawctl.sh status
./scripts/clawctl.sh stop

# 查看日志
tail -f logs/multi_bot.log
```

### 运行测试

```bash
python3 -m pytest          # 全部 408 个测试
python3 -m pytest -v       # 详细输出
python3 -m pytest tests/test_ta_engine.py  # 单个文件
```

---

## 三、架构总览

### Mixin 架构

v5.0 采用 Mixin 模式将 MultiBot 拆分为多个职责单一的混入类：

```
MultiBot (src/bot/multi_bot.py)
  ├── APIMixin            # API 调用（SiliconFlow/g4f/Kiro/Claude 代理）
  ├── BasicCommandsMixin  # /start /clear /status /help
  ├── InvestCommandsMixin # /invest /quote /market /portfolio /buy /sell
  ├── AnalysisCommandsMixin # /analyze /scan 技术分析
  ├── IBKRCommandsMixin   # IBKR 实盘交易命令
  ├── TradingCommandsMixin # 自动交易系统命令
  ├── CollabCommandsMixin # 群聊协作、AI 会议、投票
  └── MessageHandlerMixin # 普通消息处理、上下文管理
```

所有 Mixin 通过 `src/bot/globals.py` 访问共享组件（避免循环依赖）。

### 交易流水线

```
用户指令 / AI 信号
    ↓
技术分析引擎 (ta_engine.py) → 信号评分
    ↓
AI 团队投票 (ai_team_voter.py) → 多模型共识
    ↓
决策校验 (decision_validator.py)
    ↓
风险管理 (risk_manager.py) → 仓位计算、风控检查
    ↓
交易执行 (pipeline_helper.py → broker_bridge.py → IBKR)
    ↓
持仓监控 (position_monitor.py) → 止损止盈
    ↓
交易日志 (trading_journal.py) → 绩效追踪
```

### 目录结构

```
clawbot/
├── multi_main.py              # ★ 主入口（Bot 配置 + 启动逻辑）
├── config/
│   ├── .env                   # API Keys、Bot Tokens（不入 git）
│   └── bot_profiles.py        # Bot 人设、emoji、专长配置
├── src/
│   ├── bot/                   # ★ Bot 核心（Mixin 架构）
│   │   ├── multi_bot.py       # MultiBot 组合类
│   │   ├── globals.py         # 全局共享状态
│   │   ├── api_mixin.py       # API 调用层
│   │   ├── message_mixin.py   # 消息处理
│   │   ├── cmd_basic_mixin.py # 基础命令
│   │   ├── cmd_invest_mixin.py    # 投资命令
│   │   ├── cmd_analysis_mixin.py  # 技术分析命令
│   │   ├── cmd_ibkr_mixin.py     # IBKR 交易命令
│   │   ├── cmd_trading_mixin.py  # 自动交易命令
│   │   ├── cmd_collab_mixin.py   # 群聊协作命令
│   │   └── rate_limiter.py    # 速率限制
│   ├── trading_system.py      # 交易系统编排（init/start/stop）
│   ├── auto_trader.py         # 自动交易引擎
│   ├── ta_engine.py           # 技术分析引擎（信号评分）
│   ├── risk_manager.py        # 风险管理器
│   ├── position_monitor.py    # 持仓监控（止损止盈）
│   ├── broker_bridge.py       # IBKR 券商桥接
│   ├── ai_team_voter.py       # AI 团队投票决策
│   ├── decision_validator.py  # 决策校验器
│   ├── pipeline_helper.py     # 交易流水线辅助
│   ├── invest_tools.py        # 行情查询、组合管理
│   ├── quote_cache.py         # 行情缓存
│   ├── rebalancer.py          # 组合再平衡
│   ├── http_client.py         # 弹性 HTTP（指数退避+熔断器）
│   ├── trading_journal.py     # 交易日志（SQLite）
│   ├── chat_router.py         # 智能消息路由
│   ├── context_manager.py     # 上下文压缩
│   ├── history_store.py       # 对话历史（SQLite）
│   ├── message_sender.py      # 长消息分片发送
│   ├── shared_memory.py       # Bot 间共享记忆
│   ├── monitoring.py          # 健康检查、自动恢复
│   ├── scheduler.py           # 定时任务
│   ├── news_fetcher.py        # 新闻抓取
│   ├── universe.py            # 全市场扫描
│   ├── backtester.py          # 回测引擎
│   ├── models.py              # 数据模型
│   ├── utils.py               # 工具函数
│   └── tools/                 # 工具集（bash/file/screen/image 等）
├── tests/                     # 408 个单元测试
├── scripts/                   # 运维脚本（clawctl.sh 等）
├── data/             # 数据存储（history/）
├── logs/                      # 运行日志
└── images/                    # 生成的图片
```

---

## 四、配置说明

所有配置集中在 `config/.env`，参考 `.env.example`：

```env
# ========== API 配置 ==========
SILICONFLOW_KEYS=sk-xxx,sk-yyy       # 多个用逗号分隔
SILICONFLOW_BASE_URL=https://api.siliconflow.cn/v1
G4F_BASE_URL=http://localhost:1337/v1 # g4f 本地网关
KIRO_BASE_URL=http://localhost:8889/v1 # Kiro 网关
CLAUDE_API_KEY=sk-xxx
CLAUDE_BASE_URL=https://...

# ========== Bot Tokens ==========
QWEN235B_TOKEN=xxx
GPTOSS_TOKEN=xxx
CLAUDE_SONNET_TOKEN=xxx
CLAUDE_HAIKU_TOKEN=xxx
DEEPSEEK_V3_TOKEN=xxx
CLAUDE_OPUS_TOKEN=xxx

# ========== 安全配置 ==========
ALLOWED_USER_IDS=7043182738           # 多个用逗号分隔

# ========== IBKR 配置 ==========
IBKR_HOST=127.0.0.1
IBKR_PORT=7497                        # 7497=模拟, 7496=实盘
```

---

## 五、AI 团队

| Bot | 模型 | API 类型 | 专长 |
|-----|------|----------|------|
| Qwen-3-235B | qwen-3-235b | g4f | 全能分析 |
| GPT-OSS-120B | gpt-oss-120b | g4f | 快速问答、翻译 |
| Claude Sonnet | claude-sonnet-4.5 | kiro | 深度分析、架构设计 |
| Claude Haiku | claude-haiku-4.5 | kiro | 轻量对话 |
| DeepSeek V3 | DeepSeek-V3.2 | siliconflow | 中文写作、文化 |
| Claude Opus | claude-opus-4-6 | claude_proxy | 终极决策 |

Bot 人设配置在 `config/bot_profiles.py`。

---

## 六、Telegram 命令

| 命令 | 说明 |
|------|------|
| `/start` | 开始使用 |
| `/clear` | 清空对话历史 |
| `/status` | 查看系统状态 |
| `/invest <代码>` | 发起 AI 投资分析会议 |
| `/quote <代码>` | 查询实时行情 |
| `/market` | 市场概览 |
| `/portfolio` | 查看投资组合 |
| `/buy <代码> <数量>` | 买入股票 |
| `/sell <代码> <数量>` | 卖出股票 |
| `/watchlist` | 自选股管理 |

---

## 七、开发指南

### 添加新 Bot

1. 在 BotFather 创建新 Bot，获取 Token
2. 在 `config/.env` 添加 Token 和 Username
3. 在 `multi_main.py` 的 `BOTS` 列表添加配置项
4. 在 `config/bot_profiles.py` 添加人设

### 添加新命令

1. 在对应的 Mixin 文件中添加 `cmd_xxx` 方法（或创建新 Mixin）
2. 在 Mixin 的 `register_handlers()` 中注册 CommandHandler
3. 如果是新 Mixin，在 `multi_bot.py` 的 MultiBot 继承列表中添加

```python
# 示例：在 cmd_basic_mixin.py 中
async def cmd_xxx(self, update, context):
    await update.message.reply_text("Hello!")

# 在 register_handlers() 中
self.app.add_handler(CommandHandler("xxx", self.cmd_xxx))
```

### 添加新交易策略

1. 在 `ta_engine.py` 的 `compute_signal_score()` 中添加新指标评分逻辑
2. 在 `auto_trader.py` 中调整信号阈值或交易规则
3. 在 `risk_manager.py` 中添加对应的风控规则

### 关键设计模式

- **Mixin 架构**: MultiBot 通过多继承组合功能，每个 Mixin 职责单一
- **globals.py 共享**: 所有共享组件通过 `src/bot/globals.py` 访问，避免循环依赖
- **弹性 HTTP**: `http_client.py` 提供指数退避重试 + 熔断器，每次请求新建连接
- **交易流水线**: 信号 → 投票 → 校验 → 风控 → 执行 → 监控，各环节解耦

---

## 八、运维

```bash
# 使用 clawctl.sh
./scripts/clawctl.sh start    # 启动
./scripts/clawctl.sh stop     # 停止
./scripts/clawctl.sh restart  # 重启
./scripts/clawctl.sh status   # 查看状态
./scripts/clawctl.sh logs     # 查看日志

# 手动操作
python3 multi_main.py                    # 前台启动
nohup python3 multi_main.py &            # 后台启动
pkill -f 'multi_main.py'                 # 停止
tail -f logs/multi_bot.log               # 日志
```

---

## 九、测试

```bash
python3 -m pytest                        # 全部 408 个测试
python3 -m pytest -v                     # 详细输出
python3 -m pytest --tb=short             # 简洁错误信息
python3 -m pytest tests/test_xxx.py      # 单个文件
python3 -m pytest -k "test_name"         # 按名称过滤
```

测试覆盖的核心模块：
- `test_ta_engine.py` — 信号评分、趋势判定、仓位计算
- `test_trading_journal.py` — 交易生命周期、绩效统计
- `test_http_client.py` — 熔断器状态机、重试逻辑、退避计算
- `test_broker_bridge.py` — IBKR 券商桥接
- `test_risk_manager.py` — 风控规则
- `test_position_monitor.py` — 持仓监控
- `test_ai_team_voter.py` — AI 投票决策
- `test_auto_trader.py` — 自动交易引擎
- 等共 19 个测试文件

---

## 十、Telegram 设置

在 BotFather 中对每个 Bot 执行：

```
/setprivacy -> Disable
```

这样 Bot 才能在群聊中读取所有消息。

---

## 十一、依赖

核心依赖（完整列表见 `requirements.txt`，版本已用 `~=` 锁定）：

- `python-telegram-bot` — Telegram Bot API
- `httpx` — 异步 HTTP 客户端
- `yfinance` — 股票行情数据
- `ib_insync` — IBKR 交易接口
- `python-dotenv` — 环境变量管理

---

## 十二、更新日志

### v5.0 (2026-02-24)
- Mixin 架构重构：MultiBot 拆分为 8 个职责单一的 Mixin
- 全局共享状态提取到 globals.py
- 新增 6 个 AI 模型支持
- 完整交易流水线（信号→投票→风控→执行→监控）
- 408 个单元测试
- 依赖版本锁定（~= 兼容约束）
- 消除 18 处静默异常

### v2.2 (2026-02-06)
- 对话持久化
- 余额监控预警
- 图片分析功能（Claude）

### v2.0 (2026-02-06)
- 多 Bot 群聊协作
- 支持 4 个 AI 模型
