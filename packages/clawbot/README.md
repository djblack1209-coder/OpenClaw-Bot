# ClawBot - Telegram 多模型 AI 自动交易系统

通过 Telegram 群聊协调 6 个 AI 模型，实现股票技术分析、自动交易、风险管理的完整闭环。

## 核心功能

- **多模型 AI 团队**: Qwen-3-235B、GPT-OSS-120B、Claude Sonnet/Haiku/Opus、DeepSeek V3 协作决策
- **自动交易**: IBKR 盈透证券对接，AI 投票 → 风控校验 → 自动下单
- **技术分析**: RSI/MACD/EMA/布林带/ATR 多指标信号评分引擎
- **风险管理**: 仓位计算、止损止盈、每日亏损限额、熔断保护
- **投资组合**: 模拟/实盘组合管理、再平衡、绩效追踪
- **群聊协作**: 多 Bot 在同一 Telegram 群组各司其职，智能路由

## 快速开始

### 1. 安装依赖

```bash
pip3 install -r requirements.txt
```

### 2. 配置

复制 `.env.example` 并编辑 `config/.env`：

```bash
cp .env.example config/.env
# 编辑填入 API Keys 和 Bot Tokens
```

### 3. 运行

```bash
python3 multi_main.py

# 后台运行
nohup python3 multi_main.py &

# 使用运维脚本
./scripts/clawctl.sh start
./scripts/clawctl.sh status
./scripts/clawctl.sh stop
```

## Telegram 命令

| 命令 | 说明 |
|------|------|
| `/start` | 开始使用 |
| `/clear` | 清空对话历史 |
| `/status` | 查看系统状态 |
| `/invest` | 发起 AI 投资分析会议 |
| `/quote <代码>` | 查询实时行情 |
| `/market` | 市场概览 |
| `/portfolio` | 查看投资组合 |
| `/buy <代码> <数量>` | 买入股票 |
| `/sell <代码> <数量>` | 卖出股票 |
| `/watchlist` | 自选股管理 |

## 目录结构

```
clawbot/
├── multi_main.py           # 主入口（v5.0 Mixin 架构）
├── config/
│   ├── .env                # 配置文件（API Keys、Tokens）
│   └── bot_profiles.py     # Bot 人设配置
├── src/
│   ├── bot/                # Bot 核心（Mixin 架构）
│   │   ├── multi_bot.py    # MultiBot 组合类
│   │   ├── globals.py      # 全局共享状态
│   │   ├── api_mixin.py    # API 调用层
│   │   ├── message_mixin.py       # 消息处理
│   │   ├── cmd_basic_mixin.py    # 基础命令
│   │   ├── cmd_invest_mixin.py   # 投资命令
│   │   ├── cmd_analysis_mixin.py # 分析命令
│   │   ├── cmd_ibkr_mixin.py     # IBKR 交易命令
│   │   ├── cmd_trading_mixin.py  # 交易系统命令
│   │   └── cmd_collab_mixin.py   # 群聊协作命令
│   ├── trading_system.py   # 交易系统编排
│   ├── auto_trader.py      # 自动交易引擎
│   ├── ta_engine.py        # 技术分析引擎
│   ├── risk_manager.py     # 风险管理
│   ├── position_monitor.py # 持仓监控
│   ├── broker_bridge.py    # IBKR 券商桥接
│   ├── ai_team_voter.py    # AI 团队投票
│   ├── invest_tools.py     # 行情查询/组合管理
│   ├── http_client.py      # 弹性 HTTP 客户端（重试+熔断）
│   ├── trading_journal.py  # 交易日志
│   ├── quote_cache.py      # 行情缓存
│   ├── rebalancer.py       # 组合再平衡
│   ├── chat_router.py      # 智能消息路由
│   ├── decision_validator.py # 决策校验
│   ├── pipeline_helper.py  # 交易流水线
│   └── ...                 # 其他模块
├── tests/                  # 408 个单元测试
├── scripts/                # 运维脚本
├── logs/                   # 运行日志
└── data/                   # 数据存储
```

## AI 团队

| Bot | 模型 | API | 专长 |
|-----|------|-----|------|
| Qwen-3-235B | qwen-3-235b | g4f | 全能分析 |
| GPT-OSS-120B | gpt-oss-120b | g4f | 快速问答 |
| Claude Sonnet | claude-sonnet-4.5 | kiro | 深度分析、架构 |
| Claude Haiku | claude-haiku-4.5 | kiro | 轻量对话 |
| DeepSeek V3 | DeepSeek-V3.2 | siliconflow | 中文写作 |
| Claude Opus | claude-opus-4-6 | claude_proxy | 终极决策 |

## 技术栈

- Python 3.9+
- python-telegram-bot 20.x
- httpx（弹性 HTTP 客户端）
- yfinance（行情数据）
- ib_insync（IBKR 交易）
- SQLite（对话历史 + 交易日志）
