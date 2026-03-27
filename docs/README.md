# OpenClaw Bot 文档中心 (AI-SOP 资料库)

> 最后更新: 2026-03-22
> **目的**: 让 AI 开发助手在新对话中快速了解项目，无需每次全量扫描。
> **底层规则**: 见项目根目录 `AGENTS.md` — 所有 AI 工具的硬入口。

---

## 三层文档防线

```
第一层: 根目录入口 (AI 自动读取)
├── CLAUDE.md          ← Claude Code / OpenCode 自动读取 (30秒速览+铁律+完工协议)
├── AGENTS.md          ← OpenCode / Codex 自动读取 (完整规则手册)
├── .cursorrules       ← Cursor 自动读取 (symlink → CLAUDE.md)
└── .clinerules        ← Cline 自动读取 (symlink → CLAUDE.md)

第二层: 系统感知 (上帝视角)
├── docs/PROJECT_MAP.md       ← 项目全景导航 (672行, 必读)
└── docs/status/HEALTH.md     ← 系统健康 + Bug + 技术债

第三层: 开发规范 (深入工作)
├── docs/sop/UPDATE_PROTOCOL.md   ← 文档更新触发规则
├── docs/CHANGELOG.md             ← 变更历史 (领域标签)
└── docs/registries/              ← 注册表 (模块/命令/依赖/API)
```

---

## 快速入口

### 必读 (每次新对话)

| 文件 | 内容 |
|------|------|
| [PROJECT_MAP.md](PROJECT_MAP.md) | **项目全景地图** — 架构、技术栈、文件结构、模块清单 |
| [status/HEALTH.md](status/HEALTH.md) | **系统健康仪表盘** — Bug追踪 + 技术债 + 部署状态 |

### 注册表 (docs/registries/)

| 文件 | 内容 | 何时读 |
|------|------|--------|
| [registries/MODULE_REGISTRY.md](registries/MODULE_REGISTRY.md) | 190 个 Python 模块速查 | 修改/新增模块时 |
| [registries/COMMAND_REGISTRY.md](registries/COMMAND_REGISTRY.md) | 74 个命令 + 回调按钮 + 中文触发器 | 修改命令/按钮时 |
| [registries/DEPENDENCY_MAP.md](registries/DEPENDENCY_MAP.md) | 50 个依赖包 + 用途 + 版本约束 | 新增依赖时 |
| [registries/API_POOL_REGISTRY.md](registries/API_POOL_REGISTRY.md) | 26 个 API 提供商 + Key状态 + 限制 | 修改API/LLM时 |

### 开发规范 (docs/sop/)

| 文件 | 内容 |
|------|------|
| [sop/UPDATE_PROTOCOL.md](sop/UPDATE_PROTOCOL.md) | 文档更新触发规则 + CHANGELOG格式 + 自检清单 |

### 分类文档 (按需阅读)

| 目录 | 内容 | 文件 |
|------|------|------|
| [architecture/](architecture/) | 架构设计 | `OMEGA_V2_ARCHITECTURE.md`, `OPTIMIZATION_PLAN.md` |
| [guides/](guides/) | 操作指南 | `QUICKSTART.md`, `DEVELOPER_GUIDE.md`, `DEPLOYMENT_GUIDE.md` |
| [reports/](reports/) | 审计报告 | `HEALTH_CHECK_2026_03_16.md` |
| [business/](business/) | 商业文档 | `XIANYU_BUSINESS_PLAN.md` |
| [specs/](specs/) | 功能规格 | (按需创建) |

### 不在本目录的文档 (不要移动!)

| 位置 | 内容 | 原因 |
|------|------|------|
| `apps/openclaw/` | Agent 工作空间 (AGENTS.md, SOUL.md, 记忆系统, 35 Skills) | **被代码硬引用**，移动会导致系统崩溃 |
| `packages/clawbot/docs/` | ClawBot 子项目专有文档 (agents.md, 部署清单) | `web_installer.py` 代码引用 |

---

## 底层规则速查 (完整版见根 `AGENTS.md`)

### 强制更新规则

| 变更类型 | 必须更新的文档 |
|----------|---------------|
| 新增/删除 Python 模块 | `registries/MODULE_REGISTRY.md` |
| 新增/修改 Telegram 命令或按钮 | `registries/COMMAND_REGISTRY.md` |
| 新增 pip 依赖 | `registries/DEPENDENCY_MAP.md` |
| 新增/修改 API Key 或 LLM 提供商 | `registries/API_POOL_REGISTRY.md` |
| 发现 Bug 或技术债 | `status/HEALTH.md` (登记到「活跃问题」) |
| 修复 Bug | `status/HEALTH.md` (移至「已解决」) + `CHANGELOG.md` |
| 识别技术债 | `status/HEALTH.md` (记入「技术债务」) |
| 架构级改动 | `PROJECT_MAP.md` |
| **任何代码变更** | `CHANGELOG.md` (追加条目) |

### 文档命名规范

- 文件名: **全大写 + 下划线分隔** (如 `MODULE_REGISTRY.md`)
- 日期后缀: `_YYYY_MM_DD` (如 `HEALTH_CHECK_2026_03_16.md`)
- 规格文件: `YYYY-MM-DD-topic-design.md`
- 每个文档开头有 `> 最后更新: YYYY-MM-DD`
- **禁止**: 小写命名、中文文件名、空格、kebab-case
- **禁止**: 在 `docs/` 以外创建 `.md` 文档
- **禁止**: 创建重复文档 — 新建前必须搜索是否已有
