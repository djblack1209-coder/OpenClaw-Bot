# OpenClaw 全量审计方案 v3

> **用法**: 新建会话，把本文件内容粘贴给 AI，说"按这个方案执行审计"。
> **最后更新**: 2026-04-21
> **前置条件**: 所有服务已启动，IBKR Gateway 已连接，闲鱼 Cookie 有效

---

## 0. 核心原则（上几轮审计踩的坑）

### 绝对禁止的行为
1. **不准声称"已修复"却不验证** — 每个修复必须有 curl 输出、截图、或编译结果证明
2. **不准一次改太多文件** — 每改 1-2 个文件就跑一次验证（TypeScript: `npx tsc --noEmit`，Rust: `cargo check`）
3. **不准猜测文件内容** — 修改前必须先 Read 文件，看到原文再改
4. **不准批量替换不检查上下文** — 上一轮批量替换品牌名导致 Rust struct 字段重复
5. **不准跳过已知问题** — 下面列出的 HEALTH.md 活跃问题必须逐个验证

### 验证铁律
- 改了前端 → `npx tsc --noEmit` 必须零错误
- 改了 Rust → `cargo check` 必须零错误
- 改了后端 Python → `python -m py_compile <file>` 必须通过
- 改了 API → 用 `curl` 调一下确认返回正常
- 改了 UI 文本 → 用浏览器打开确认肉眼可见

---

## 1. 环境准备

### 1.1 项目路径
```
项目根目录: /Users/blackdj/Desktop/OpenEverything
Python: /Users/blackdj/Desktop/OpenEverything/packages/clawbot/.venv312/bin/python
前端: /Users/blackdj/Desktop/OpenEverything/apps/openclaw-manager-src
Tauri: /Users/blackdj/Desktop/OpenEverything/apps/openclaw-manager-src/src-tauri
配置: /Users/blackdj/Desktop/OpenEverything/packages/clawbot/config/.env
```

### 1.2 端口清单
| 端口 | 服务 | 验证命令 |
|------|------|----------|
| `18789` | OpenClaw Gateway (Node.js) | `curl http://127.0.0.1:18789` |
| `18790` | ClawBot API (FastAPI) | `curl http://127.0.0.1:18790/api/v1/status` |
| `18793` | Kiro Gateway | `curl http://127.0.0.1:18793/health` |
| `18891` | g4f 免费模型代理 | `curl http://127.0.0.1:18891/v1/models` |
| `9090` | Prometheus 指标 | `curl http://127.0.0.1:9090/metrics` |
| `4002` | IBKR Gateway | `lsof -i :4002` |
| `1420` | Vite 开发服务器 | `curl http://127.0.0.1:1420` |

### 1.3 启动顺序
```bash
# 0. 清理残留端口
kill $(lsof -ti :9090) 2>/dev/null

# 1. Redis（如果需要）
brew services start redis

# 2. 前端开发服务器
cd /Users/blackdj/Desktop/OpenEverything/apps/openclaw-manager-src
npm run dev &

# 3. 用桌面端一键启动所有后端服务（推荐）
open /Applications/OpenClaw.app
# → 设置页 → "启动所有服务" 按钮

# 或者命令行方式：
cd /Users/blackdj/Desktop/OpenEverything/packages/clawbot
bash scripts/start_all.sh

# 4. 验证所有端口
for port in 18789 18790 18793 18891 9090 4002 1420; do
  lsof -i :$port > /dev/null 2>&1 && echo "$port ✅" || echo "$port ❌"
done
```

### 1.4 启动后基线快照
```bash
# 记录当前状态作为基线
curl -s http://127.0.0.1:18790/api/v1/status | python3 -m json.tool | head -20
curl -s http://127.0.0.1:18790/api/v1/trading/portfolio-summary | python3 -m json.tool
```

---

## 2. 审计检查清单

### 规则
- 每个检查项标记: ✅通过 / ❌失败(记录具体错误) / ⏭️跳过(说明原因)
- 失败项必须记录: 文件路径+行号+错误内容+截图（如果是 UI 问题）
- 不要一口气审计完再回来修——发现一个修一个，修完验证再继续

---

### 2.1 首页 (Home) — 路径 `/`

#### API 数据验证
```bash
curl -s http://127.0.0.1:18790/api/v1/status | python3 -m json.tool
curl -s http://127.0.0.1:18790/api/v1/trading/portfolio-summary | python3 -m json.tool
curl -s http://127.0.0.1:18790/api/v1/system/notifications?limit=20 | python3 -m json.tool
curl -s http://127.0.0.1:18790/api/v1/system/daily-brief | python3 -m json.tool
```

#### 逐区域检查
| # | 检查项 | 预期结果 | 实际 |
|---|--------|---------|------|
| 1 | TradingEngineCard 显示 7-Bot 投票 | 各 Bot 有 approve/reject/pending 状态，不全是 pending |  |
| 2 | TradingEngineCard 日盈亏 | IBKR 连接时显示真实金额，非 $0.00 |  |
| 3 | TelemetryCard LLM 费用 | 显示当日 API 费用数值 |  |
| 4 | TelemetryCard 模型池 | 显示"X/Y 活跃"，不是"0/0" |  |
| 5 | 闲鱼/AI 卡片 Cookie 状态 | 显示"有效"/"已过期"，不是"未知" |  |
| 6 | 快捷操作6个按钮 | 分别跳转到 portfolio/social/xianyu/assistant/finradar/settings |  |
| 7 | TerminalLogsCard | 浏览器模式显示"请使用桌面客户端"，桌面模式显示实时日志 |  |
| 8 | 系统状态摘要5项 | 各项显示"在线"/"离线"，不是英文 |  |
| 9 | WebSocket 连接 | Header 显示"已连接"绿色圆点 |  |
| 10 | 所有文字 | 无英文残留（LiteLLM 模型池 不是 LiteLLM Pool） |  |
| 11 | 后端不可达时 | 显示黄色警告条 |  |

---

### 2.2 AI 助手 (Assistant) — 侧边栏"AI 助手"

#### API 数据验证
```bash
curl -s http://127.0.0.1:18790/api/v1/conversation/sessions?limit=50 | python3 -m json.tool
# 创建一个测试会话
curl -s -X POST "http://127.0.0.1:18790/api/v1/conversation/sessions?title=test" | python3 -m json.tool
```

#### 逐功能检查
| # | 检查项 | 预期结果 | 实际 |
|---|--------|---------|------|
| 1 | 4个模式标签 | 显示中文：对话/投资/执行/创作，不是 Chat/Invest/Execute/Create |  |
| 2 | 每个模式6个快捷指令 | 全部中文（简报/天气/翻译/周报/问答/日程等） |  |
| 3 | **发送消息** | 输入文字 → 点发送 → 收到 AI 流式回复 |  |
| 4 | 发送消息失败时 | 显示中文错误提示，不是英文 |  |
| 5 | 会话历史列表 | 显示标题/时间/消息数 |  |
| 6 | 新建会话按钮(+) | 点击后创建新会话 |  |
| 7 | 删除会话按钮(🗑) | 点击后删除会话 |  |
| 8 | 附件上传(📎) | 选择文件后上传成功 |  |
| 9 | 麦克风按钮(🎤) | 点击录音，松开后语音识别 |  |
| 10 | 系统信息区 | 显示当前模式/会话数/消息数 |  |

**重点**: #3 是上一轮报告的 Bug——消息发不出去。必须验证：
- 后端 `/api/v1/conversation/sessions/{id}/send` 是否正常
- SSE 流式是否正确返回
- 前端是否正确处理响应

---

### 2.3 全球监控 (WorldMonitor) — 侧边栏"全球监控"

#### API 数据验证
```bash
curl -s http://127.0.0.1:18790/api/v1/monitor/risk | python3 -m json.tool | head -30
curl -s http://127.0.0.1:18790/api/v1/monitor/risk/global | python3 -m json.tool
curl -s http://127.0.0.1:18790/api/v1/monitor/extended | python3 -m json.tool | head -40
```

#### 逐区域检查
| # | 检查项 | 预期结果 | 实际 |
|---|--------|---------|------|
| 1 | 全球风险指数 | 显示 0-100 分值+脉冲动画 |  |
| 2 | 世界地图热力图 | 国家按风险着色，悬停显示国名+分数 |  |
| 3 | 活跃冲突区 | 列出分数≥70的国家 |  |
| 4 | **基础设施状态** | 4 项数据，"正常"字样大小统一 |  |
| 5 | 气候与灾害 | 4 项数据，链接可点击 |  |
| 6 | 网络安全态势 | 4 项数据 |  |
| 7 | 情报终端流 | 时间戳+分类+消息，可滚动 |  |
| 8 | 所有文字 | 无英文残留 |  |

**重点**: #4 是上一轮报告的 Bug——两个"正常"字样大小不一致。需要检查 CSS。

---

### 2.4 金融雷达 (FinRadar) — 侧边栏"金融雷达"

#### API 数据验证
```bash
curl -s http://127.0.0.1:18790/api/v1/monitor/finance/indices | python3 -m json.tool | head -20
curl -s http://127.0.0.1:18790/api/v1/monitor/finance/crypto | python3 -m json.tool | head -20
curl -s http://127.0.0.1:18790/api/v1/monitor/finance/commodities | python3 -m json.tool | head -20
curl -s http://127.0.0.1:18790/api/v1/monitor/finance/forex | python3 -m json.tool | head -20
```

#### 逐区域检查
| # | 检查项 | 预期结果 | 实际 |
|---|--------|---------|------|
| 1 | 股指 Tab | 价格>0（不是全 0），有涨跌幅 |  |
| 2 | 加密货币 Tab | BTC/ETH 等有实时价格 |  |
| 3 | 大宗商品 Tab | 黄金/原油价格>0 |  |
| 4 | 外汇 Tab | 汇率>0 |  |
| 5 | 恐贪指数 | 显示 0-100 数值 |  |
| 6 | 涨跌榜 | Top3 涨/跌 有数据 |  |
| 7 | 加密货币占比 | BTC/ETH/其他（不是 Others） |  |
| 8 | 所有文字 | 无英文残留 |  |

**重点**: HI-701 报告股指/商品/外汇价格全 0。需要先验证后端数据源是否恢复。

---

### 2.5 投资组合 (Portfolio) — 侧边栏"投资组合"

#### API 数据验证
```bash
curl -s http://127.0.0.1:18790/api/v1/trading/portfolio-summary | python3 -m json.tool
curl -s http://127.0.0.1:18790/api/v1/trading/journal | python3 -m json.tool | head -20
curl -s http://127.0.0.1:18790/api/v1/controls/trading | python3 -m json.tool
```

#### 6个标签页逐个检查
| # | Tab | 检查项 | 预期结果 | 实际 |
|---|-----|--------|---------|------|
| 1 | 持仓概览 | 总资产/日盈亏 | IBKR 连接时显示真实数据 |  |
| 2 | 持仓概览 | 持仓列表 | 有真实持仓（如果有的话） |  |
| 3 | 持仓概览 | 模式标签 | DEMO MODE / LIVE / PAPER |  |
| 4 | 持仓概览 | 卖出按钮 | DEMO 模式下禁用 |  |
| 5 | 交易决策 | 输入股票代码 | 输入 AAPL → 点分析 → 显示投票结果 |  |
| 6 | 交易决策 | 周期选择 | 4个按钮可点击切换 |  |
| 7 | 自动交易 | 5个开关 | 可切换，状态实时更新 |  |
| 8 | 回测分析 | 输入代码+选策略+选周期 | 点"运行"后显示回测结果 |  |
| 9 | 估值分析 | 输入代码 | 点"分析"后显示 DCF 估值 |  |
| 10 | 交易日志 | 筛选+分页 | 有交易记录（如果有的话） |  |

**重点**: 交易引擎全是"待定和0"的问题。如果 IBKR 已连接，应该显示真实持仓和盈亏。

---

### 2.6 新闻中心 (NewsFeed) — 侧边栏"新闻中心"

#### API 数据验证
```bash
curl -s "http://127.0.0.1:18790/api/v1/monitor/news?limit=50" | python3 -m json.tool | head -30
```

#### 逐区域检查
| # | 检查项 | 预期结果 | 实际 |
|---|--------|---------|------|
| 1 | 新闻列表 | 50 条新闻，标题可点击 |  |
| 2 | 分类筛选 | 7 个按钮可切换过滤 |  |
| 3 | 威胁雷达严重性 | 显示中文：严重/高/中/低（不是 CRITICAL/HIGH/MEDIUM/LOW） |  |
| 4 | 来源排行 | 显示 Top 来源 |  |
| 5 | AI 摘要 | 有摘要文本 |  |

---

### 2.7 我的机器人 (Bots) — 侧边栏"我的机器人"

#### API 数据验证
```bash
curl -s http://127.0.0.1:18790/api/v1/system/services | python3 -m json.tool
curl -s http://127.0.0.1:18790/api/v1/xianyu/cookiecloud/status | python3 -m json.tool
curl -s http://127.0.0.1:18790/api/v1/controls/scheduler | python3 -m json.tool | head -30
```

#### 逐区域检查
| # | 检查项 | 预期结果 | 实际 |
|---|--------|---------|------|
| 1 | 服务舰队列表 | 每个服务显示状态+名称+端口 |  |
| 2 | 启停按钮 | 点击后服务状态变化 |  |
| 3 | Cookie 状态 | VALID/INVALID 显示正确 |  |
| 4 | 闲鱼 AI 客服 | 在线/离线状态正确 |  |
| 5 | 社媒自动驾驶 | 启停按钮可用 |  |
| 6 | 定时任务列表 | 16 个任务+开关 |  |

---

### 2.8 闲鱼管理 (Xianyu) — 侧边栏"闲鱼管理"

#### API 数据验证
```bash
curl -s http://127.0.0.1:18790/api/v1/xianyu/conversations?limit=20 | python3 -m json.tool
curl -s http://127.0.0.1:18790/api/v1/xianyu/profit | python3 -m json.tool
curl -s http://127.0.0.1:18790/api/v1/xianyu/cookie-status | python3 -m json.tool
```

#### 逐区域检查
| # | 检查项 | 预期结果 | 实际 |
|---|--------|---------|------|
| 1 | 对话列表 | 最近 20 条买家对话 |  |
| 2 | 利润统计 | 显示销售额/利润数据 |  |
| 3 | Cookie 状态 | 有效/已过期/剩余时间 |  |
| 4 | 所有文字 | 无英文残留 |  |

---

### 2.9 社媒运营 (Social) — 侧边栏"社媒运营"

#### API 数据验证
```bash
curl -s http://127.0.0.1:18790/api/v1/social/status | python3 -m json.tool
curl -s http://127.0.0.1:18790/api/v1/social/topics | python3 -m json.tool
```

#### 逐区域检查
| # | 检查项 | 预期结果 | 实际 |
|---|--------|---------|------|
| 1 | 发帖功能 | 输入内容 → 发布 |  |
| 2 | 话题推荐 | 显示推荐话题列表 |  |
| 3 | 自动驾驶状态 | 显示下次发布时间 |  |

---

### 2.10 Bot 商店 (Store) — 侧边栏"Bot 商店"

#### 逐区域检查
| # | 检查项 | 预期结果 | 实际 |
|---|--------|---------|------|
| 1 | 提案列表 | 有卡片显示 |  |
| 2 | 搜索框 | 输入后过滤 |  |
| 3 | 审批/拒绝按钮 | 可点击，状态更新 |  |
| 4 | API 失败态 | 显示中文错误提示 |  |

---

### 2.11 设置 (Settings) — 侧边栏"设置"

#### 逐区域检查
| # | 检查项 | 预期结果 | 实际 |
|---|--------|---------|------|
| 1 | 系统信息 | OS/Node/Python 版本正确 |  |
| 2 | CPU/内存/磁盘 | 显示真实使用率（不是 0%） |  |
| 3 | API 密钥状态 | 已配置的显示✓，未配置的显示✗ |  |
| 4 | 通知开关 | 4 个开关可切换 |  |
| 5 | 语言切换 | 中/英切换后全页面生效 |  |
| 6 | 启动/停止所有服务 | 桌面模式可用，浏览器模式禁用 |  |
| 7 | 保存设置 | 点击后有成功提示 |  |
| 8 | 浏览器模式 | 显示"当前为浏览器模式"提示 |  |

---

### 2.12 开发者页面（三击版本号开启）

需要单独审计的开发者页面：
- **control** — 总控中心
- **dashboard** — 系统仪表盘  
- **gateway** — API 网关
- **scheduler** — 调度器
- **channels** — 通知渠道
- **ai** — AI 模型管理
- **plugins** — MCP 插件管理
- **memory** — 记忆系统
- **evolution** — 进化引擎
- **dev** / **devpanel** — 开发面板
- **testing** — 测试工具
- **logs** — 日志查看器

每个开发者页面也按上面格式检查：API 返回 → 数据展示 → 按钮功能 → 文字语言。

---

## 3. 已知活跃问题（必须验证）

以下是 HEALTH.md 中的活跃问题，审计时必须确认状态：

| HI | 问题 | 验证方式 |
|----|------|---------|
| HI-701 | 金融数据 23 项全 0 | `curl /api/v1/monitor/finance/indices` 看价格 |
| HI-702 | newapi channels/tokens 500 | `curl /api/v1/newapi/channels` 看状态码 |
| HI-703 | 30 处 N/A 占位符 | 全局搜索 `'N/A'` |

---

## 4. 桌面端专项审计

### 4.1 构建
```bash
cd /Users/blackdj/Desktop/OpenEverything
make tauri-build
# 验证: /Applications/ 下只有 OpenClaw.app，没有 OpenEverything.app
ls /Applications/ | grep -i "open"
```

### 4.2 桌面端独有功能
| # | 检查项 | 预期结果 |
|---|--------|---------|
| 1 | 窗口标题 | "OpenClaw"（不是 OpenEverything） |
| 2 | 启动日志 | 控制台输出 "🦞 OpenClaw 启动" |
| 3 | 服务控制 | 设置页启停按钮可用 |
| 4 | 本地日志 | 日志页显示实时日志流 |
| 5 | 系统诊断 | 设置→系统诊断 正常运行 |
| 6 | 环境检查 | 首次启动检查 Node/Python/配置 |
| 7 | Tauri IPC | 3 秒轮询 `get_service_status` 正常 |

### 4.3 与浏览器模式对比
| 功能 | 浏览器模式 | 桌面模式 |
|------|-----------|---------|
| 服务启停 | 按钮禁用+提示 | 按钮可用 |
| 本地日志 | "请使用桌面客户端" | 实时日志流 |
| 系统资源 | CPU/内存可能为 0 | 真实数据 |
| 文件操作 | 不可用 | 可用 |

---

## 5. 输出格式

审计完成后，输出结构化报告：

```markdown
# 审计报告 YYYY-MM-DD

## 环境
- 后端: ✅/❌ (端口 18790)
- IBKR: ✅/❌ (端口 4002)
- 闲鱼: ✅/❌
- WebSocket: ✅/❌

## 按页面汇总
| 页面 | 通过 | 失败 | 跳过 | 严重问题 |
|------|------|------|------|---------|

## 失败项详情
| # | 页面 | 检查项 | 预期 | 实际 | 文件:行号 | 严重度 |
|---|------|--------|------|------|-----------|--------|

## 修复记录
| # | 问题 | 修复文件 | 验证方式 | 验证结果 |
|---|------|---------|---------|---------|
```

---

## 6. WebSocket 验证

```bash
# 安装 websocat (如果没有)
# brew install websocat

# 或者用 Python 验证
python3 -c "
import websocket
ws = websocket.create_connection('ws://127.0.0.1:18790/api/v1/events')
print('连接成功')
data = ws.recv()
print(f'收到数据: {data[:200]}')
ws.close()
"
```

---

## 7. 前端编译验证

```bash
# TypeScript 检查
cd /Users/blackdj/Desktop/OpenEverything/apps/openclaw-manager-src
npx tsc --noEmit

# Rust 检查
cd /Users/blackdj/Desktop/OpenEverything/apps/openclaw-manager-src/src-tauri
cargo check

# Python 检查（后端）
cd /Users/blackdj/Desktop/OpenEverything/packages/clawbot
.venv312/bin/python -m py_compile src/api/server.py
```
