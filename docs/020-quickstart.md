# OpenClaw OMEGA v2.0 — 快速启动指南

> 最后更新: 2026-03-27

> 从零到运行，30分钟内完成。

## 前提条件

- Python 3.12+
- pip / venv
- Telegram Bot Token（至少1个，推荐2个：现有Bot + OMEGA Gateway Bot）

## Step 1: 安装依赖（5分钟）

```bash
cd packages/clawbot

# 创建虚拟环境（如果还没有）
python3.12 -m venv .venv312
source .venv312/bin/activate

# 安装核心依赖
pip install -r requirements.txt

# 安装 OMEGA 新增依赖（可选，按需安装）
pip install pyyaml          # omega.yaml 配置解析
pip install retell           # AI电话（可选）
pip install twilio           # VoIP备选（可选）
pip install paddleocr        # 中文OCR（可选）
pip install openai-whisper   # 语音识别（可选）
```

## Step 2: 配置环境变量（5分钟）

编辑 `config/.env`，追加以下变量：

```bash
# === OMEGA v2.0 新增 ===

# Gateway Bot Token（从 @BotFather 创建新Bot获取）
OMEGA_GATEWAY_BOT_TOKEN=your_gateway_bot_token_here

# 管理员 Telegram user_id（逗号分隔）
OMEGA_ADMIN_USER_IDS=123456789

# 每日 LLM 预算（美元）
OMEGA_DAILY_BUDGET=50.0

# Tavily API Key（用于自愈引擎的Web搜索，可选）
TAVILY_API_KEY=your_tavily_key

# Retell AI（电话功能，可选）
RETELL_API_KEY=your_retell_key

# Twilio（电话备选，可选）
TWILIO_ACCOUNT_SID=
TWILIO_AUTH_TOKEN=
TWILIO_FROM_NUMBER=
```

## Step 3: 配置 omega.yaml（3分钟）

```bash
# omega.yaml 已预置默认配置，通常不需要修改
# 如需自定义，编辑 config/omega.yaml
```

关键配置项：
- `investment.auto_trade: false` — 默认需要人工确认交易
- `cost.daily_budget_usd: 50.0` — 每日LLM预算
- `security.require_pin_for_trades: true` — 交易需PIN确认

## Step 4: 启动（2分钟）

```bash
# 方式1: 直接启动（开发模式）
cd packages/clawbot
python multi_main.py

# 方式2: Docker启动（生产模式）
cd /path/to/OpenClaw\ Bot
docker-compose up -d
```

启动后会看到：
```
INFO - Prometheus metrics server started on :9090
INFO - LiteLLM routing: balanced
INFO - Bot qwen235b started: @your_bot_username
INFO - ...（其他Bots）
INFO - Internal API server started on :18790
INFO - OpenClawBrain 已初始化
INFO - OpenClaw Gateway Bot 已启动
INFO - Evolution Engine started (24h interval)
```

## Step 5: 验证（5分钟）

### 5.1 API 健康检查
```bash
curl http://localhost:18790/api/v1/ping
# 应返回: {"status": "pong", "version": "5.0"}
```

### 5.2 Telegram 测试
在 Telegram 中找到你的 Gateway Bot，发送：
```
/start
```
应收到欢迎消息。然后试试：
```
帮我分析茅台今天能买吗
```

### 5.3 投资团队测试
```
分析AAPL
```
应看到6个角色的分析过程和最终决策。

## 架构概览

```
用户 (Telegram)
    ↓
GatewayBot (第8个Bot)
    ↓
OpenClawBrain (意图解析→任务图→调度)
    ↓
    ├── 投资团队 (CrewAI 6角色)
    ├── 社媒运营 (APScheduler 5个cron)
    ├── 执行引擎 (API→浏览器→电话)
    ├── 自愈引擎 (6步自愈)
    └── 进化引擎 (GitHub Trending扫描)
```

## 新增文件清单

| 文件 | 行数 | 职责 |
|------|------|------|
| `src/core/brain.py` | 757 | 核心编排器 |
| `src/core/intent_parser.py` | 349 | 意图解析 |
| `src/core/task_graph.py` | 351 | 任务DAG引擎 |
| `src/core/executor.py` | 390 | 多路径执行 |
| `src/core/self_heal.py` | 397 | 异常自愈 |
| `src/core/event_bus.py` | 329 | 事件总线 |
| `src/core/cost_control.py` | 227 | 成本控制 |
| `src/core/security.py` | 245 | 安全分级 |
| `src/gateway/telegram_gateway.py` | 476 | Telegram主控台 |
| `src/modules/investment/team.py` | 750 | 投资团队 |
| `config/omega.yaml` | 120 | 全局配置 |
| **合计** | **~4,400** | |

## 进化口令

一键启动全自动进化扫描：
```
claw evolve --scope all --depth deep --auto-integrate --notify
```

或在 Telegram 中发送：
```
/evolve
```

## 常见问题

**Q: Gateway Bot 和现有7个Bot冲突吗？**
A: 不冲突。Gateway Bot 是独立的第8个Bot，现有Bot继续处理各自的群聊/频道。

**Q: 不安装 Redis 能运行吗？**
A: 可以。Redis 是可选的，用于任务队列持久化。不安装则使用内存队列。

**Q: 如何设置交易PIN码？**
A: 在 Telegram 中对 Gateway Bot 发送 `/setpin 1234`（首次使用时设置）。

**Q: 投资团队的建议可靠吗？**
A: 投资建议仅供参考，不保证盈利。默认 `auto_trade: false`，所有交易需要人工确认。
