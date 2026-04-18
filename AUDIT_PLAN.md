# OpenClaw Bot 全方位审计方案

> **版本**: v2.0 | **创建**: 2026-04-18 | **状态**: 执行中
> **继续任务指令**: `继续审计任务 — RX [轮次名称]`
> **上下文限制**: 每轮约 150-200K Token，修复即提交，不跨产品线改动

---

## 审计总览

### 项目规模快照

| 维度 | 数值 |
|------|------|
| Python 后端文件 | 821 个 .py |
| 前端 TS/TSX 文件 | 87 个（不含 node_modules） |
| FastAPI 端点 | 94 个 (93 HTTP + 1 WebSocket) |
| Tauri IPC 命令 | 112 个 |
| Telegram Bot 命令 | 98 个 |
| 回调处理器 | 14 个 |
| 中文 NLP 触发词 | 200+ 个 |
| 已知活跃问题 | 5 个 (HI-388/462/522/523/524) |
| Mock 数据问题 | 6 处 |
| Workflow Stub | 8 个方法 |
| CI/CD 工作流 | 4 套 |
| Docker Compose | 5 个 |
| 注册表文档 | 4 个 |

### 架构决策记录

- **macOS 桌面端底座**: 从现有 Tauri+React 更换为 `itq5/OpenClaw-Admin` (Vue3+Vite+NaiveUI+Tauri2)
  - 原因: 25+页面功能最全、双网关支持、Vue3+Vite 是 Tauri 2 官方推荐、中文原生
  - GitHub: https://github.com/itq5/OpenClaw-Admin (526 Stars, 最后更新 2026-04-18)

---

## 11 轮审计总表

| 轮次 | 名称 | 范围 | 条目数 | 详细文档 | 状态 |
|------|------|------|--------|---------|------|
| R1 | 基础设施与文件治理 | Git/CI-CD/Docker/依赖/文档 | ~45 | [R1](docs/audit/R01_INFRA.md) | 待执行 |
| R2 | 后端核心引擎 | Brain/EventBus/Router/LiteLLM/API/DB/安全 | ~55 | [R2](docs/audit/R02_BACKEND_CORE.md) | 待执行 |
| R3 | Telegram Bot 命令层 | 98命令+14回调+200+NLP | ~50 | [R3](docs/audit/R03_BOT_COMMANDS.md) | 待执行 |
| R4 | Telegram Bot 业务场景 | 投资/社媒/闲鱼/执行/Gateway | ~45 | [R4](docs/audit/R04_BOT_BUSINESS.md) | 待执行 |
| R5 | macOS 底座更换 | OpenClaw-Admin集成+Tauri包装 | ~40 | [R5](docs/audit/R05_MACOS_REBASE.md) | 待执行 |
| R6 | macOS 核心页面 | 仪表盘/对话/频道/模型/技能/监控 | ~50 | [R6](docs/audit/R06_MACOS_CORE.md) | 待执行 |
| R7 | macOS 业务页面 | 交易/社媒/闲鱼/记忆/日志/设置 | ~45 | [R7](docs/audit/R07_MACOS_BUSINESS.md) | 待执行 |
| R8 | 投资交易系统 | IBKR/风控/回测/AI投票/仓位/策略 | ~45 | [R8](docs/audit/R08_TRADING.md) | 待执行 |
| R9 | 闲鱼+社媒+工具链 | 闲鱼客服/比价/社媒/微信/TTS/OCR | ~40 | [R9](docs/audit/R09_XIANYU_SOCIAL.md) | 待执行 |
| R10 | 生产部署与运维 | VPS/Docker/心跳/监控/备份 | ~35 | [R10](docs/audit/R10_DEPLOY.md) | 待执行 |
| R11 | 端到端集成+审计报告 | 全链路冒烟/文档终态/报告归档 | ~30 | [R11](docs/audit/R11_E2E_FINAL.md) | 待执行 |
| **合计** | | | **~480** | | |

---

## 每轮标准 SOP

```
1. 声明: "继续审计任务 — 第 RX 轮 [名称]"
2. 读取: AUDIT_PLAN.md 定位当前轮次 → 读取对应 docs/audit/RXX_*.md
3. 基线: cd packages/clawbot && pytest tests/ --tb=no -q 2>&1 | tail -5
4. 执行: 按条目逐一审计 → 读源码 → 对照官方文档 → 发现问题 → 修复 → 验证
5. 提交: 每修一个问题立即 git add -A && git commit -m "[修复] RX.NN: 描述"
6. 更新: 审计文档标记 [x] 完成 + 置信度 + 实际修复记录
7. 回归: pytest tests/ --tb=no -q 确认无新增失败
8. 文档: 更新 HEALTH.md + CHANGELOG.md
9. 交接: 写入 HANDOFF.md（如果是会话最后一步）
```

---

## 审计条目格式说明

每个条目包含以下字段，确保实习生可独立执行：

| 字段 | 说明 |
|------|------|
| 编号 | `RX.NN` 格式，X=轮次，NN=序号 |
| 分类 | Bug / 安全 / 风控 / 设计 / Mock / Stub / 文档 / 冗余 / 配置 / 依赖 |
| 位置 | `文件路径:行号` 精确定位 |
| 问题 | 大白话描述，不懂代码的人也能理解 |
| 修复 | 具体操作步骤，可直接执行 |
| 置信度 | 确认(有代码证据) / 疑似(需验证) / 需验证(需运行时测试) |
| 验证 | 修复后的验证命令或检查方式 |
| 状态 | `[ ]` 待做 / `[x]` 已完成 / `[-]` 跳过(附原因) |

---

## 已知关键问题汇总（跨轮次引用）

### 确认级 Bug (必修)

| ID | 轮次 | 位置 | 问题 |
|----|------|------|------|
| HI-NEW-01 | R2 | `src/api/rpc.py:108` | `_rpc_system_status()` 引用 os 未导入，运行时 NameError |
| HI-NEW-02 | R2 | `src/api/routers/ws.py:95-97` | WS 事件 popleft 多客户端丢失 |
| HI-NEW-03 | R2 | `src/api/routers/ws.py:84` | WS 初始状态无异常保护 |
| HI-522 | R8 | `src/risk_manager.py` | check_trade() 竞态条件 |
| HI-523 | R8 | `src/risk_manager.py` | SELL 方向风控缺失 |
| HI-524 | R8 | `src/risk_manager.py` | 新账户 VaR 保护无效 |

### Mock 数据 (必修)

| ID | 轮次 | 位置 | 问题 |
|----|------|------|------|
| MOCK-01 | R6/R7 | `Dashboard/AssetDistribution.tsx:29-67` | 硬编码假资产分布 |
| MOCK-02 | R6/R7 | `Dashboard/RecentActivity.tsx:36-64` | 全假活动列表 |
| MOCK-03 | R6/R7 | `Money/OrderBook.tsx:47-67` | Mock 订单簿降级 |
| MOCK-04 | R6/R7 | `Money/DepthChart.tsx:46-66` | Mock 深度图降级 |
| MOCK-05 | R6/R7 | `DevPanel/index.tsx:41` | TODO: 未接入后端 API |
| MOCK-06 | R6/R7 | `Store/index.tsx:506` | 静默降级无提示 |

### 安全风险 (重要)

| ID | 轮次 | 位置 | 问题 |
|----|------|------|------|
| HI-388 | R1 | `requirements.txt` | diskcache CVE-2025-69872 |
| HI-462 | R2 | `src/` 全目录 ~360处 | logger 泄露 API Key 风险 |

### Stub/未完成 (需决策)

| ID | 轮次 | 位置 | 问题 |
|----|------|------|------|
| STUB-01~08 | R3 | `src/bot/workflow_mixin.py` | 8个方法是空壳 |

---

## 服务器信息 (R10 使用)

- **IP**: 101.43.41.96
- **OS**: Ubuntu 22.04 LTS
- **配置**: 2C2G + 40GB SSD + 200GB/月流量(3Mbps)
- **用户**: root
- **SSH**: `ssh root@101.43.41.96`

---

## 文件结构

```
AUDIT_PLAN.md              ← 你在这里（审计总索引）
docs/audit/
├── R01_INFRA.md            ← R1 基础设施审计条目
├── R02_BACKEND_CORE.md     ← R2 后端核心审计条目
├── R03_BOT_COMMANDS.md     ← R3 Bot命令层审计条目
├── R04_BOT_BUSINESS.md     ← R4 Bot业务场景审计条目
├── R05_MACOS_REBASE.md     ← R5 macOS底座更换审计条目
├── R06_MACOS_CORE.md       ← R6 macOS核心页面审计条目
├── R07_MACOS_BUSINESS.md   ← R7 macOS业务页面审计条目
├── R08_TRADING.md          ← R8 投资交易系统审计条目
├── R09_XIANYU_SOCIAL.md    ← R9 闲鱼社媒工具链审计条目
├── R10_DEPLOY.md           ← R10 生产部署运维审计条目
└── R11_E2E_FINAL.md        ← R11 端到端集成验证审计条目
```
