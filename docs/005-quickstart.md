# 快速启动与部署指南

> 合并自原 020-quickstart.md + 021-deployment-guide.md + 022-developer-guide.md + 023-disaster-recovery.md + 027-key-rotation.md + 028-api-registration-guide.md

---

## 一、OMEGA v2.0 快速启动

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

---

## 二、闲鱼商业部署


> 最后更新: 2026-03-27

## 系统概览

已完成的商业化部署系统，包含：
- **6个免费AI Bot** (Telegram) - 基于 g4f 免费模型
- **闲鱼AI客服** - 自动回复、议价、订单处理
- **自动交付系统** - 付款检测 → License生成 → 百度网盘发货
- **防退款保护** - 检测退款自动吊销License
- **部署授权服务** - License验证 + 设备绑定

## 快速启动

### 一键启动所有服务
```bash
cd /Users/blackdj/Desktop/OpenClaw\ Bot/packages/clawbot
bash scripts/start_all.sh
```

启动内容：
- g4f API (端口 18891) - 免费AI模型
- 部署授权服务 (端口 18800) - License验证
- 闲鱼AI客服 - WebSocket实时监控
- 6个Telegram Bot - 全能助手

### 停止所有服务
```bash
bash scripts/stop_all.sh
```

## 核心配置

### 1. 百度网盘交付链接
编辑 `config/.env`，设置：
```bash
BAIDU_PAN_LINK=https://pan.baidu.com/s/你的分享链接
BAIDU_PAN_CODE=提取码
```

### 2. 打包部署客户端
```bash
bash scripts/pack_deploy_bundle.sh
```
生成 `OpenClaw_Deploy_v2026.3.zip`，上传到百度网盘

### 3. 闲鱼Cookie更新
当Cookie失效时：
1. Chrome打开闲鱼，F12复制Cookie
2. 更新 `.env` 中的 `XIANYU_COOKIES`
3. 热更新：`kill -USR1 $(cat /tmp/xianyu.pid)`

## 商业流程

### 买家购买流程
1. 买家在闲鱼咨询 → AI自动回复
2. 买家议价 → AI根据底价策略应对
3. 买家付款 → 系统检测到"等待卖家发货"
4. 自动创建License (用户名/密码/Key)
5. 通过闲鱼消息发送：百度网盘链接 + License
6. 同时Telegram通知你接手远程部署

### 买家部署流程
1. 下载百度网盘的部署包
2. 双击运行"一键部署"
3. 输入License Key
4. 选择AI模型方案（付费API/免费/本地）
5. 配置Telegram Bot Token
6. 自动安装OpenClaw + Skills
7. 生成健康报告

### 退款保护
- 检测到"退款成功" → 自动吊销License
- 买家无法继续使用
- Telegram通知你

## 定价策略

当前AI客服底价设置（`src/xianyu/xianyu_agent.py`）：
- 部署服务：¥89（可议价到¥79）
- API Token包：¥15

建议闲鱼标价：
- 产品A：OpenClaw一键部署包 - ¥19.9
- 产品B：云托管版 - ¥49.9/月（未实现）

## 服务监控

### 查看日志
```bash
tail -f logs/xianyu.log        # 闲鱼客服
tail -f logs/multi_bot.log     # Telegram Bot
tail -f logs/g4f.log           # g4f API
tail -f logs/deploy_server.log # 部署服务
```

### 检查服务状态
```bash
lsof -ti:18891  # g4f
lsof -ti:18800  # 部署服务
ps aux | grep xianyu
ps aux | grep multi_main
```

### License管理
```bash
# 查看所有License
curl -H "X-Admin-Token: $(grep DEPLOY_ADMIN_TOKEN config/.env | cut -d= -f2)" \
  http://localhost:18800/api/admin/licenses

# 手动吊销License
curl -X POST -H "X-Admin-Token: $(grep DEPLOY_ADMIN_TOKEN config/.env | cut -d= -f2)" \
  http://localhost:18800/api/admin/licenses/OC-XXXX-XXXX/revoke
```

## 成本控制

### 完全免费的部分
- 6个Telegram Bot：使用g4f免费模型
- 闲鱼AI客服：使用g4f的qwen-3-235b
- 部署授权服务：自建Flask API
- 所有基础设施：本地运行

### 可选付费部分
- Claude代理API：0.01元/次（仅作备用，已配置但未启用）
- 服务器托管：如需7x24运行可用VPS（约¥30/月）

## 故障排查

### g4f无响应
```bash
kill $(lsof -ti:18891)
python3 -m g4f.api --port 18891 --g4f-api-key dummy
```

### 闲鱼客服掉线
检查Cookie是否过期，查看 `logs/xianyu.log`

### Telegram Bot无响应
检查Token是否正确，查看 `logs/multi_bot.log`

## 下一步优化

1. **百度网盘自动上传** - 目前需手动上传部署包
2. **自动定价策略** - 根据市场竞争动态调价
3. **客户CRM** - 记录客户购买历史和满意度
4. **A/B测试** - 测试不同话术的转化率

## 技术架构

```
闲鱼买家
  ↓ WebSocket
闲鱼AI客服 (xianyu_live.py)
  ↓ 检测付款
License Manager (license_manager.py)
  ↓ 生成凭证
闲鱼消息 (百度网盘链接 + License)
  ↓
买家下载部署包
  ↓
部署客户端 (deploy_client.py)
  ↓ License验证
部署授权服务 (deploy_server.py)
  ↓ 设备绑定
OpenClaw安装完成
```

---

**所有核心功能已实现并测试通过。**

---

## 三、开发者指南


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
make test                  # 推荐：自动使用 packages/clawbot/.venv312/bin/python
cd packages/clawbot && .venv312/bin/python -m pytest -v
cd packages/clawbot && .venv312/bin/python -m pytest tests/test_ta_engine.py  # 单个文件
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
make test                                # 推荐：自动使用项目 Python 3.12 虚拟环境
cd packages/clawbot && .venv312/bin/python -m pytest -v
cd packages/clawbot && .venv312/bin/python -m pytest --tb=short
cd packages/clawbot && .venv312/bin/python -m pytest tests/test_xxx.py
cd packages/clawbot && .venv312/bin/python -m pytest -k "test_name"
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

---

## 四、灾难恢复


> 最后更新: 2026-04-18

---

## 数据资产清单

### SQLite 数据库（11 个）

| 数据库 | 用途 | 重要性 | 数据量级 |
|--------|------|--------|----------|
| trading.db | 交易日志/持仓/盈亏 | 🔴 关键 | 中 |
| portfolio.db | 投资组合/现金管理 | 🔴 关键 | 小 |
| shared_memory.db | AI 记忆/用户偏好 | 🟠 重要 | 中 |
| history.db | 对话历史 | 🟡 一般 | 大 |
| execution_hub.db | 任务执行记录/提醒/记账 | 🟠 重要 | 中 |
| xianyu_chat.db | 闲鱼客服对话 | 🟠 重要 | 大 |
| feedback.db | 用户反馈 | 🟡 一般 | 小 |
| cost_analytics.db | LLM 成本分析 | 🟡 一般 | 中 |
| deploy_licenses.db | License 发放记录 | 🟠 重要 | 小 |
| novels.db | AI 小说创作 | 🟡 一般 | 小 |
| auto_shipper.db | 闲鱼自动发货规则 | 🟠 重要 | 小 |

### 其他关键数据

| 数据 | 位置 | 重要性 |
|------|------|--------|
| Redis | localhost:6379 | 🟡 会话缓存（可重建） |
| LLM 缓存 | data/llm_cache/ | 🔵 可再生 |
| 配置文件 | config/.env | 🔴 关键（含 API 密钥） |
| 草稿 | ~/.openclaw/drafts.json | 🟡 一般 |
| Cookie | config/.env 中 XIANYU_COOKIES | 🟠 重要 |

---

## 自动备份机制

### 定时任务
- **每日 03:00**: 数据清理（trading 365天/feedback 90天/cost 30天/降价监控 30+90天）
- **每日 04:00**: 全量数据库备份（11 个 SQLite 文件）

### 备份位置
```
packages/clawbot/data/backups/
├── trading_2026-04-18.db
├── portfolio_2026-04-18.db
├── shared_memory_2026-04-18.db
└── ...
```

### 保留策略
- 每日备份：保留 **7 天**
- 每周备份（周日）：保留 **4 周**

### 手动备份
```bash
cd packages/clawbot
.venv312/bin/python scripts/backup_databases.py
```

---

## 恢复步骤

### 场景 1：单个数据库损坏

```bash
# 1. 停止 ClawBot
kill $(pgrep -f multi_main.py)

# 2. 找到最近的备份
ls -la data/backups/ | grep trading

# 3. 替换损坏的数据库
cp data/backups/trading_2026-04-18.db data/trading.db

# 4. 验证完整性
sqlite3 data/trading.db "PRAGMA integrity_check;"

# 5. 重启 ClawBot
.venv312/bin/python multi_main.py &
```

### 场景 2：全部数据库恢复

```bash
# 1. 停止 ClawBot
kill $(pgrep -f multi_main.py)

# 2. 备份当前损坏的数据库（以防万一）
mkdir data/corrupted_$(date +%Y%m%d)
mv data/*.db data/corrupted_$(date +%Y%m%d)/

# 3. 找到最近日期的备份
LATEST=$(ls data/backups/trading_*.db | sort | tail -1 | grep -o '[0-9]\{4\}-[0-9]\{2\}-[0-9]\{2\}')

# 4. 恢复所有数据库
for db in trading portfolio history shared_memory execution_hub xianyu_chat feedback cost_analytics deploy_licenses novels auto_shipper; do
  if [ -f "data/backups/${db}_${LATEST}.db" ]; then
    cp "data/backups/${db}_${LATEST}.db" "data/${db}.db"
    echo "✅ 已恢复 ${db}.db"
  fi
done

# 5. 重启
.venv312/bin/python multi_main.py &
```

### 场景 3：Mac 主机硬盘损坏 → VPS 接管

1. 确认 VPS failover 已自动接管（heartbeat 超时 120s × 3 次 = 6 分钟后）
2. SSH 登录 VPS 检查 `systemctl status clawbot`
3. VPS 上的数据可能不是最新的 — 最后一次 rsync 的数据
4. 修复 Mac 后，从 VPS 拉回数据：
```bash
rsync -avz user@vps:/path/to/clawbot/data/ packages/clawbot/data/
```
5. 在 Mac 重启 ClawBot，VPS 会自动退让

### 场景 4：config/.env 丢失

1. 从密码管理器/笔记中恢复 API 密钥
2. 必须恢复的密钥清单：
   - `TELEGRAM_BOT_TOKEN` — Telegram @BotFather
   - `MEM0_API_KEY` — mem0 Cloud 控制台
   - `SILICONFLOW_API_KEY` — SiliconFlow 控制台
   - `IBKR_*` — IBKR 交易网关配置
   - `XIANYU_COOKIES` — 需要重新扫码登录
3. 其余密钥参见 `docs/006-registries.md`

---

## 预防措施

1. **Git 推送**：所有代码变更及时 push 到 GitHub
2. **密钥管理**：config/.env 不进 Git，建议同步到加密密码管理器
3. **VPS 同步**：rsync 排除 data/ 目录（数据库太大），仅同步代码
4. **监控**：heartbeat 每 60s 一次，3 次失败自动切换到 VPS
5. **定期验证**：每月检查 `data/backups/` 目录确认备份正在运行

---

## 联系方式

遇到无法恢复的问题，检查：
- `docs/009-health.md` — 已知问题
- `docs/012-handoff.md` — 最近的工作状态
- GitHub Issues — 记录和追踪

---

## 五、密钥轮换


> 最后更新: 2026-03-28

## 1. 概述

项目使用 `config/.env` 文件管理约 55 个 API 密钥。本指南规定了密钥分类、轮换频率和操作步骤。

**核心原则：**
- 所有密钥通过 `os.getenv()` 加载，源码中零硬编码
- `.env` 文件已被 `.gitignore` 排除，不会提交到 Git
- 密钥缺失时功能静默降级（不崩溃）

---

## 2. 密钥分类与轮换周期

| 优先级 | 分类 | 轮换周期 | 密钥清单 |
|--------|------|----------|----------|
| **高** | 付费 LLM API | 90天 | `CLAUDE_API_KEY`, `VOLCENGINE_API_KEY`, `FAL_KEY`, `KLING_*`, `DEEPGRAM_API_KEY` |
| **高** | 内部认证 | 90天 | `OPENCLAW_API_TOKEN`, `DEPLOY_ADMIN_TOKEN`, `KIRO_API_KEY` |
| **中** | 邮箱密码 | 180天 | `OPS_EMAIL_PASSWORD`, `SMTP_PASS` (同一密码，需同时更新) |
| **中** | 免费 LLM API | 180天或额度耗尽 | `OPENROUTER_API_KEY`, `GROQ_API_KEY`, `CEREBRAS_API_KEY`, `GEMINI_API_KEY` 等 |
| **低** | Telegram Bot | 仅泄露时 | `QWEN235B_TOKEN` 等 7 个 Bot Token |
| **低** | Session Cookie | 自动过期 | `XIANYU_COOKIES` |

---

## 3. 轮换操作步骤

### 3.1 通用流程

```bash
# 1. 在提供商官网生成新密钥

# 2. 测试新密钥可用
curl -H "Authorization: Bearer <新密钥>" https://api.xxx.com/v1/models

# 3. 更新 config/.env
nano packages/clawbot/config/.env
# 修改对应行: SOME_API_KEY=<新密钥>

# 4. 重启服务
cd packages/clawbot && python multi_main.py

# 5. 检查日志确认初始化成功
grep "已启用\|initialized\|API Token 认证已启用" /tmp/clawbot.log

# 6. 在提供商官网撤销旧密钥
```

### 3.2 OPENCLAW_API_TOKEN 轮换

这是内部 API 认证 Token，需同时更新后端和前端：

```bash
# 1. 生成新 Token
python3 -c "import secrets; print(secrets.token_urlsafe(32))"

# 2. 更新后端
# 编辑 packages/clawbot/config/.env:
# OPENCLAW_API_TOKEN=<新Token>

# 3. 更新前端 (Tauri 桌面端)
# 编辑 apps/openclaw-manager-src/.env.local:
# VITE_CLAWBOT_API_TOKEN=<新Token>

# 4. 重启后端 + 重新构建前端
```

### 3.3 Telegram Bot Token 轮换

```bash
# 1. 通过 @BotFather 使用 /revoke 命令获取新 Token
# 2. 更新 config/.env 中对应的 *_TOKEN 变量
# 3. 重启服务
```

### 3.4 邮箱应用密码轮换

```bash
# 1. 在 Google 账户 → 安全性 → 应用专用密码 → 生成新密码
# 2. 同时更新两处 (使用相同密码):
#    OPS_EMAIL_PASSWORD=<新密码>
#    SMTP_PASS=<新密码>
# 3. 重启服务
```

---

## 4. SiliconFlow 密钥池管理

SiliconFlow 支持多密钥轮转，系统自动管理：

```bash
# config/.env 中逗号分隔多个密钥
SILICONFLOW_KEYS=key1,key2,key3,key4
SILICONFLOW_PAID_KEYS=pkey1,pkey2,...,pkey10
```

- 系统自动 Round-Robin 轮转
- 额度耗尽的密钥自动标记为 exhausted
- 新增密钥只需追加到逗号列表末尾并重启

---

## 5. 紧急泄露处理

如果发现密钥泄露：

```bash
# 1. 立即在提供商官网撤销泄露的密钥
# 2. 生成新密钥并更新 config/.env
# 3. 重启服务
# 4. 检查是否有异常 API 调用 (查看提供商的用量仪表盘)
# 5. 如果是 Git 泄露，使用 git filter-repo 清除历史
```

---

## 6. 未配置密钥的功能列表

以下功能因对应密钥未配置而处于禁用状态：

| 功能 | 需要的密钥 | 状态 |
|------|-----------|------|
| X/Twitter 发帖 | `X_BEARER_TOKEN` + OAuth 4个 | 未配置 |
| Alpaca 交易 | `ALPACA_API_KEY/SECRET` | 未配置 |
| Langfuse 监控 | `LANGFUSE_SECRET_KEY/PUBLIC_KEY` | 未配置 |
| Tavily 搜索 | `TAVILY_API_KEY` | 未配置 |
| Retell 语音 | `RETELL_API_KEY` | 未配置 |
| Composio 集成 | `COMPOSIO_API_KEY` | 未配置 |
| Skyvern RPA | `SKYVERN_API_KEY` | 未配置 |

---

## 六、API 注册教程（小白版）


> 这份教程写给完全没有技术基础的朋友，每一步都会写得很详细，照着做就行。

---

## 第1部分：获取AI模型的"钥匙"

> 你可以把AI模型想象成一个很聪明的助手，而"API Key"就是联系这个助手的**专属电话号码**。下面教你3种方式获取它。

### 方式一：DeepSeek（推荐，国内直接用）

1. 打开浏览器（就是你平时上网用的那个软件），在地址栏输入 `platform.deepseek.com`，然后按键盘上的**回车键**
2. 页面打开后，找到右上角的**"注册"**按钮，点一下
3. 输入你的**手机号**，然后点**"获取验证码"**，手机会收到一条短信，把短信里的数字填进去
4. 设置一个**密码**（字母加数字，至少8位），然后点**"注册"**
5. 注册成功后会自动登录。这时候新用户会送你**10块钱的免费额度**，够用很久了
6. 在左边的菜单栏里，找到**"API Keys"**这一项，点进去
7. 然后点页面上的**"创建 API Key"**按钮
8. 会弹出一个小窗口，名称随便填（比如写"我的机器人"），然后点**"确定"**
9. 这时候屏幕上会显示一串以 `sk-` 开头的字符，这就是你的**钥匙**。**立刻复制下来，保存到一个记事本里**，因为它只显示这一次，关掉就看不到了

> 复制方法：用鼠标左键按住从头拖到尾，选中后按键盘 `Ctrl + C`（苹果电脑是 `Command + C`），然后打开记事本按 `Ctrl + V`（苹果电脑是 `Command + V`）粘贴保存。

### 方式二：硅基流动 SiliconFlow（国内平台，有免费模型）

1. 打开浏览器，在地址栏输入 `cloud.siliconflow.cn`，按**回车键**
2. 点右上角的**"注册"**，用手机号注册一个账号（步骤和上面类似）
3. 登录之后，在左边菜单找到**"API密钥"**，点进去
4. 点**"新建API密钥"**按钮
5. 同样会出现一串字符，**马上复制保存到记事本**
6. 这个平台有一些**完全免费的模型**可以用，不花钱也能体验

### 方式三：Ollama（离线免费，不用联网，但需要电脑配置好一些）

> 这个方式是把AI直接装到你自己的电脑上。好处是完全免费、不用网络；缺点是需要电脑比较好（建议内存16GB以上）。

1. 打开浏览器，输入 `ollama.com`，按**回车键**
2. 找到页面上大大的**"Download"（下载）**按钮，点一下
3. 选择你的电脑系统：苹果电脑选**macOS**，普通电脑选**Windows**
4. 下载完成后，找到下载的文件，**双击打开**，然后一路点**"下一步"**或**"Install"（安装）**直到装完
5. 安装好之后，打开**终端**（一个黑色的窗口）：
   - Windows电脑：按键盘上的 `Win键 + R`，输入 `cmd`，按回车
   - 苹果电脑：在启动台搜索"终端"，点开
6. 在黑色窗口里，输入下面这行字，然后按**回车键**：
   ```
   ollama pull qwen2.5
   ```
7. 等它下载完就行了（可能需要几分钟，取决于网速）
8. 用Ollama的话，后面填写地址时填 `http://localhost:11434`，不需要API Key

---

## 第2部分：创建 Telegram 机器人

> Telegram 是一个国外的聊天软件，我们要在上面创建一个属于你自己的AI机器人。

### 第一步：下载安装 Telegram

1. 打开浏览器，输入 `telegram.org`，按**回车键**
2. 选择你的设备类型，点击下载（手机去应用商店搜"Telegram"也行）
3. 安装完打开，用**手机号注册**

> **重要提示**：在国内使用Telegram需要借助网络工具才能正常访问，请自行准备。注册时如果收不到短信验证码，可以选择"通过电话接听验证码"。

### 第二步：找到"机器人之父"

4. 打开Telegram之后，点上方的**搜索栏**（放大镜图标）
5. 输入 `@BotFather`，然后在搜索结果里找到带**蓝色认证标志**的那个，点进去

### 第三步：创建你的机器人

6. 进入对话后，点击底部输入框，输入 `/newbot`，然后**发送**
7. BotFather会回复你，问你给机器人起个**名字**（这是显示名，随便起，比如"小助手"），输入后**发送**
8. 接着它会让你设置一个**用户名**，这个必须以 `bot` 结尾（比如 `my_ai_helper_bot`），输入后**发送**
9. 如果用户名没被别人用过，BotFather就会回复你一条消息，里面有一串类似这样的字符：
   ```
   7123456789:AAF1234567890abcdefghijklmnop
   ```
10. 这串字符就是你的**机器人Token**（可以理解为机器人的身份证号）。**复制下来，保存到记事本里**

> 到这里你的Telegram机器人就创建好了！后面只要把这个Token填到程序里，机器人就能工作了。

---

## 第3部分：接入飞书 / 钉钉

### 飞书机器人

1. 打开浏览器，输入 `open.feishu.cn`，按**回车键**
2. 用你的**飞书账号**登录（没有的话先去 `feishu.cn` 注册一个）
3. 登录后，在页面上方找到**"开发者后台"**，点进去
4. 然后点**"创建企业自建应用"**按钮
5. 填写应用名称（随便起，比如"AI助手"），上传一个图标（随便传一张图就行），然后点**"确定创建"**
6. 创建好之后会进入应用设置页面。在左边菜单找到**"凭证与基础信息"**，点进去
7. 你会看到两个重要信息：**App ID** 和 **App Secret**，把它们都**复制保存到记事本里**
8. 接着在左边菜单点**"权限管理"**，搜索并开通 `im:message`（收发消息的权限）
9. 然后在左边菜单点**"机器人"**，把机器人功能开启
10. 最后在左边菜单点**"版本管理与发布"**，点**"创建版本"**，然后**"申请发布"**

### 钉钉机器人

1. 打开浏览器，输入 `open-dev.dingtalk.com`，按**回车键**
2. 用你的**钉钉账号**登录
3. 登录后，点页面上的**"应用开发"**，然后选**"企业内部开发"**
4. 点**"创建应用"**，选择**"H5微应用"**
5. 填上应用名称和简介（随便写），然后点**"确定创建"**
6. 创建完成后，在应用信息页面，你能看到 **AppKey** 和 **AppSecret**，**复制保存到记事本**
7. 接着在左边菜单找到**"机器人与消息推送"**，点进去，把机器人功能**打开**（开关点成蓝色）
8. 最后点**"版本管理与发布"**，点**"发布"**按钮

---

## 你现在应该有了这些东西

| 你做了什么 | 你拿到了什么 | 保存好了吗？ |
|---|---|---|
| 注册DeepSeek/硅基流动 | API Key（sk-开头的一串字符） | 请确认 |
| 创建Telegram机器人 | Bot Token（一串数字和字母） | 请确认 |
| 创建飞书应用 | App ID + App Secret | 请确认 |
| 创建钉钉应用 | AppKey + AppSecret | 请确认 |

> **安全提醒**：上面这些"钥匙"都非常重要，就像你的银行卡密码一样，**不要发给任何人，也不要发到群里**。
