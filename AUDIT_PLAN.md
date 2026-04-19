# OpenClaw Bot 全方位审计方案 v3.0

> **版本**: v3.0 | **创建**: 2026-04-18 | **状态**: 执行中
> **继续任务指令**: `继续审计任务`（AI 自动读取本文件定位断点）
> **上下文限制**: 每轮约 200K Token，每轮仅处理一个子单元，修复即提交
> **升级说明**: 基于 v2.0 重构，按价值位阶排序，子单元粒度细化至单次会话可完成

---

## 审计总览

### 项目规模快照（2026-04-18 实测）

| 维度 | 数值 |
|------|------|
| Python 后端文件 | 408 个 .py（排除 venv） |
| 前端 TS/TSX 文件 | 87 个（排除 node_modules） |
| FastAPI 端点 | 94 个 (93 HTTP + 1 WebSocket) |
| Tauri IPC 命令 | 112 个 |
| Telegram Bot 命令 | 92+ 个 |
| 回调处理器 | 14 个 |
| 中文 NLP 触发词 | 200+ 个 |
| C端入口 | 3 个（Telegram Bot / 微信 ClawBot / macOS App） |
| 已知活跃问题 | 5 个 (HI-388/462/522/523/524) |
| Mock 数据问题 | 6 处 |
| Workflow Stub | 8 个方法 |
| CI/CD 工作流 | 4 套 |
| Docker Compose | 5 个 |
| 注册表文档 | 4 个 |

### 审计角色矩阵（按顶级软件公司职位架构）

| 角色 | 职责 | 覆盖轮次 |
|------|------|---------|
| **CPO（首席产品官）** | 用户旅程完整性、功能闭环、UX 一致性 | R03/R04/R06/R07/R09/R11 |
| **CTO（首席技术官）** | 架构合理性、技术债务、可扩展性 | R01/R02/R05/R08/R10 |
| **VP Engineering** | 代码质量、测试覆盖、CI/CD、依赖安全 | R01/R02/R03 |
| **VP Security（CSO）** | OWASP/STRIDE、密钥管理、输入验证、日志脱敏 | R02/R08/R10 |
| **Staff Engineer** | 模块级代码审查、API 设计、性能优化 | 所有轮次 |
| **QA Lead** | E2E 测试、回归防护、Mock 数据清理 | R03/R06/R07/R11 |
| **DevOps Lead** | Docker/CI/部署/监控/灾备 | R01/R10 |
| **Design Lead** | UI/UX 一致性、无障碍、响应式 | R06/R07 |

---

## 11 轮审计总表（按价值位阶排序）

| 轮次 | 名称 | 范围 | 预估条目 | 详细文档 | 状态 |
|------|------|------|---------|---------|------|
| R1 | 基础设施与文件治理 | Git/CI-CD/Docker/依赖/文档对齐 | ~40 | [R01](docs/audit/R01_INFRA.md) | ✅ 已完成(6项修复) |
| R2 | 后端核心引擎 | Brain/EventBus/Router/LiteLLM/API/安全 | 46 | [R02](docs/audit/R02_BACKEND_CORE.md) | ✅ 已完成(14项修复/5技术债) |
| R3 | Telegram Bot 命令层 | 92+命令+14回调+NLP触发 | ~45 | [R03](docs/audit/R03_BOT_COMMANDS.md) | ✅ 已完成(3项修复/9文档修正/3技术债) |
| R4 | Telegram Bot 业务场景 | 投资/社媒/闲鱼/执行 | ~40 | [R04](docs/audit/R04_BOT_BUSINESS.md) | ✅ 已完成(32通过/8技术债) |
| R5 | macOS 桌面端架构 | Tauri2+React 集成/IPC/构建 | ~35 | [R05](docs/audit/R05_MACOS_ARCH.md) | ✅ 已完成(2项修复/5技术债) |
| R6 | macOS 核心页面 | Dashboard/Assistant/Bots/Settings | ~45 | [R06](docs/audit/R06_MACOS_CORE.md) | ✅ 已完成(8项修复/15技术债) |
| R7 | macOS 业务页面 | Trading/Social/Xianyu/Memory/Logs | ~40 | [R07](docs/audit/R07_MACOS_BUSINESS.md) | ✅ 已完成(6项修复/20技术债) |
| R8 | 投资交易系统 | IBKR/风控/回测/AI投票/仓位 | ~40 | [R08](docs/audit/R08_TRADING.md) | ✅ 已完成(4项修复/10技术债) |
| R9 | 闲鱼+社媒+微信+工具链 | 闲鱼客服/社媒/微信Bridge/TTS/OCR | ~35 | [R09](docs/audit/R09_XIANYU_SOCIAL.md) | ✅ 已完成(4项修复/14技术债) |
| R10 | 生产部署与运维 | VPS/Docker/心跳/监控/备份 | ~30 | [R10](docs/audit/R10_DEPLOY.md) | ✅ 已完成(0项修复/5技术债/VPS需人工验证) |
| R11 | 端到端集成验证 | 全链路冒烟/文档终态/报告归档 | ~25 | [R11](docs/audit/R11_E2E_FINAL.md) | ✅ 已完成(0项修复/3技术债) |
| R12 | CI/CD 管道与 DevOps | Workflow/测试策略/缓存/Billing/本地验证 | ~30 | [R12](docs/audit/R12_CI_DEVOPS.md) | ✅ 已完成(CI重写+Billing修复) |
| **合计** | | | **~455** | | |

---

## 每轮标准 SOP

```
1. 声明: "继续审计任务"
2. 读取: AUDIT_PLAN.md → 找到第一个"待执行"轮次 → 读取对应 docs/audit/RXX_*.md
3. 基线: cd packages/clawbot && pytest tests/ --tb=no -q 2>&1 | tail -5
4. 执行: 按条目逐一审计 → 读源码 → 对照官方文档 → 发现问题 → 修复 → 验证
5. 提交: 每修一个问题立即 git add -A && git commit -m "[审计] RX.NN: 描述"
6. 更新: 审计文档标记 ✅ 完成 + 置信度 + 实际修复记录
7. 回归: pytest tests/ --tb=no -q 确认无新增失败
8. 文档: 更新 HEALTH.md + CHANGELOG.md
9. 收尾: 将轮次状态改为"已完成"或"部分完成"，写入 HANDOFF.md
```

---

## 审计条目格式

| 字段 | 说明 |
|------|------|
| 编号 | `RX.NN` 格式 |
| 分类 | Bug / 安全 / 设计 / Mock / Stub / 文档 / 冗余 / 配置 / 依赖 / UX |
| 位置 | `文件路径:行号` |
| 问题 | 大白话描述 |
| 修复 | 具体操作步骤 |
| 置信度 | ✅确认 / ⚠️疑似 / 🔍需验证 |
| 验证 | 修复后的验证命令 |
| 状态 | ⬜ 待做 / ✅ 已完成 / ⏭️ 跳过(附原因) |

---

## 已知关键问题（跨轮次引用）

### 确认级 Bug

| ID | 轮次 | 位置 | 问题 |
|----|------|------|------|
| HI-NEW-01 | R2 | `src/api/rpc.py:108` | `_rpc_system_status()` 引用 os 未导入 |
| HI-NEW-02 | R2 | `src/api/routers/ws.py:95-97` | WS 事件 popleft 多客户端丢失 |
| HI-NEW-03 | R2 | `src/api/routers/ws.py:84` | WS 初始状态无异常保护 |
| HI-522 | R8 | `src/risk_manager.py` | check_trade() 竞态条件 |
| HI-523 | R8 | `src/risk_manager.py` | SELL 方向风控缺失 |
| HI-524 | R8 | `src/risk_manager.py` | 新账户 VaR 保护无效 |

### Mock 数据

| ID | 轮次 | 位置 | 问题 |
|----|------|------|------|
| MOCK-01 | R6/R7 | `Dashboard/AssetDistribution.tsx` | 硬编码假资产分布 |
| MOCK-02 | R6/R7 | `Dashboard/RecentActivity.tsx` | 全假活动列表 |
| MOCK-03 | R6/R7 | `Money/OrderBook.tsx` | Mock 订单簿 |
| MOCK-04 | R6/R7 | `Money/DepthChart.tsx` | Mock 深度图 |
| MOCK-05 | R6/R7 | `DevPanel/index.tsx` | TODO: 未接入后端 |
| MOCK-06 | R6/R7 | `Store/index.tsx` | 静默降级无提示 |

### 安全风险

| ID | 轮次 | 位置 | 问题 |
|----|------|------|------|
| HI-388 | R1 | `requirements.txt` | diskcache CVE |
| HI-462 | R2 | 全目录 ~360处 | logger 泄露 API Key |

### Stub/未完成

| ID | 轮次 | 位置 | 问题 |
|----|------|------|------|
| STUB-01~08 | R3 | `src/bot/workflow_mixin.py` | 8个方法空壳 |

---

## 服务器信息（R10 使用）

- **IP**: 101.43.41.96
- **OS**: Ubuntu 22.04 LTS
- **配置**: 2C2G + 40GB SSD + 200GB/月(3Mbps)
- **SSH**: `ssh root@101.43.41.96`

---

## 文件结构

```
AUDIT_PLAN.md              ← 审计总索引（你在这里）
docs/audit/
├── R01_INFRA.md            ← R1 基础设施与文件治理
├── R02_BACKEND_CORE.md     ← R2 后端核心引擎
├── R03_BOT_COMMANDS.md     ← R3 Bot 命令层
├── R04_BOT_BUSINESS.md     ← R4 Bot 业务场景
├── R05_MACOS_ARCH.md       ← R5 macOS 桌面端架构
├── R06_MACOS_CORE.md       ← R6 macOS 核心页面
├── R07_MACOS_BUSINESS.md   ← R7 macOS 业务页面
├── R08_TRADING.md          ← R8 投资交易系统
├── R09_XIANYU_SOCIAL.md    ← R9 闲鱼+社媒+微信+工具链
├── R10_DEPLOY.md           ← R10 生产部署与运维
├── R11_E2E_FINAL.md        ← R11 端到端集成验证
└── R12_CI_DEVOPS.md        ← R12 CI/CD 管道与 DevOps
```
