# OpenClaw Bot — AI 开发入口

> **本文件由 Claude Code / OpenCode / Codex 自动读取。** Cursor 读 `.cursorrules`，Cline 读 `.clinerules`。
> 最后更新: 2026-03-22

---

## 30 秒速览

| 属性 | 值 |
|------|-----|
| **项目** | OpenClaw Bot — 7-Bot Telegram 多智能体系统 |
| **后端** | Python 3.12 + FastAPI + LiteLLM (15+ LLM provider) |
| **桌面** | Tauri 2 + React + TypeScript |
| **依赖** | 30+ 高星开源项目 (browser-use 81K★, crawl4ai 62K★, CrewAI 47K★...) |
| **规模** | 189 Python 文件, 67K 行, 75 命令, 7 Bot |
| **入口** | `packages/clawbot/multi_main.py` |
| **虚拟环境** | `packages/clawbot/.venv312` |
| **状态** | 生产运行中 (macOS 桌面 + 腾讯云备用) |

---

## 必读文档 (按优先级)

| 优先级 | 文档 | 何时读 |
|--------|------|--------|
| 🔴 必读 | `docs/PROJECT_MAP.md` | **每次新对话** — 672行项目全景 |
| 🔴 必读 | `docs/status/HEALTH.md` | **每次新对话** — 系统健康 + Bug + 技术债 |
| 🟡 按需 | `docs/registries/MODULE_REGISTRY.md` | 修改模块时 |
| 🟡 按需 | `docs/registries/COMMAND_REGISTRY.md` | 修改命令时 |
| 🟡 按需 | `docs/registries/API_POOL_REGISTRY.md` | 修改 API/LLM 时 |
| 🟡 按需 | `docs/registries/DEPENDENCY_MAP.md` | 新增依赖时 |
| ⚪ 深入 | `docs/architecture/OMEGA_V2_ARCHITECTURE.md` | 架构级改动 |
| ⚪ 深入 | `docs/guides/DEVELOPER_GUIDE.md` | 开发规范 |

---

## 关键命令

```bash
# 本地开发
cd packages/clawbot
source .venv312/bin/activate
python multi_main.py                    # 启动 7 Bot + FastAPI :18790

# 测试
pytest                                  # 运行测试 (456/459 通过)
python -c "import ast; ast.parse(open('src/FILE.py').read())"  # 语法检查

# 其他服务
python -m g4f api --port 18891          # g4f 免费 LLM 代理
python kiro-gateway/main.py             # Kiro Gateway :18793
python scripts/xianyu_main.py           # 闲鱼 AI 客服
```

---

## 架构概览

```
用户消息 (Telegram)
    │
    ▼
┌─ multi_bot.py ──────────────────┐
│  7 Bot (polling) + 75 命令       │
│  ├─ CommandHandler (/xxx)        │
│  ├─ MessageHandler (中文NL)      │
│  └─ CallbackQueryHandler         │
└──────────┬──────────────────────┘
           ▼
┌─ brain.py (OMEGA 编排器) ────────┐
│  intent_parser → task_graph       │
│  → executor → response_cards     │
└──────────┬──────────────────────┘
           ▼
┌─ litellm_router.py ─────────────┐
│  15+ provider, 50+ deployment    │
│  SiliconFlow / Groq / Gemini /   │
│  OpenRouter / iflow / Cerebras   │
└──────────────────────────────────┘
```

---

## 铁律 (NEVER 违反)

### 目录红线
- **NEVER** 移动 `apps/openclaw/` 下的文件 — 被代码硬引用，移动即崩溃
- **NEVER** 在 `docs/` 以外创建 `.md` 文档
- **NEVER** 提交 `.env`、`credentials.json` 等密钥文件

### 架构约束
- **NEVER** 跨层调用 — Bot层不直接调数据层，必须走 core/ 编排
- **NEVER** 同一 Telegram Bot Token 并发 polling — 会导致消息丢失

### 安全红线
- **NEVER** 在日志中输出完整 API Key — 最多显示前20字符
- **NEVER** 调用硅基付费Key的Pro模型 — HTTP 403，key可能报废

---

## ★ 完工强制协议 (4步，缺一不可)

完成任何代码变更后，**必须**执行以下 4 步，否则任务视为未完成:

### Step 1: 更新变更日志

追加到 `docs/CHANGELOG.md` 顶部:

```markdown
## [YYYY-MM-DD] 标题

> 领域: `backend` | `frontend` | `ai-pool` | `deploy` | `docs` | `infra` | `trading` | `social` | `xianyu`
> 影响模块: `模块A`, `模块B`
> 关联问题: HI-xxx (来自 HEALTH.md)

### 变更内容
- 描述

### 文件变更
- `path/to/file.py` — 说明
```

### Step 2: 更新受影响文档

| 变更类型 | 必须更新 |
|----------|---------|
| 新增/删除模块 | `docs/registries/MODULE_REGISTRY.md` |
| 新增/修改命令 | `docs/registries/COMMAND_REGISTRY.md` |
| 新增依赖 | `docs/registries/DEPENDENCY_MAP.md` |
| API Key/LLM 变更 | `docs/registries/API_POOL_REGISTRY.md` |
| 架构级改动 | `docs/PROJECT_MAP.md` |

### Step 3: 更新系统状态

- 发现 Bug → 登记到 `docs/status/HEALTH.md`「活跃问题」
- 修复 Bug → 移至 `docs/status/HEALTH.md`「已解决」
- 识别技术债 → 记入 `docs/status/HEALTH.md`「技术债务」

### Step 4: 自检清单

- [ ] 代码通过语法检查 (`python -c "import ast; ..."`)
- [ ] CHANGELOG 已追加且格式正确
- [ ] 受影响的注册表文档已更新
- [ ] 发现的 Bug/技术债已登记到 HEALTH.md

---

## 已知陷阱 (高频踩坑)

| # | 陷阱 | 正确做法 |
|---|------|----------|
| 1 | `execution_hub.py` 是 3808 行巨石反编译文件 | 优先使用 `src/execution/` 拆分模块 |
| 2 | `message_mixin.py` 也是反编译来源 | 变量名可能不准确，改前先理解上下文 |
| 3 | Telegram Markdown 渲染经常崩 | 用 `telegram_markdown.md_to_html()` 而非手写 |
| 4 | 流式输出群聊触发 flood 限制 | 群聊阈值 50-180 字符，私聊 15-90 |
| 5 | 硅基付费Key调Pro模型会403 | 只用非Pro模型: DeepSeek-R1/V3, Qwen3-235B |
| 6 | Gemini 2.0 系已废弃 | 用 2.5-flash/2.5-pro/3-flash-preview |

---

## 配置文件位置

| 文件 | 用途 |
|------|------|
| `packages/clawbot/config/.env` | 所有 API Key + Bot Token + 功能开关 |
| `packages/clawbot/config/omega.yaml` | OMEGA 系统配置 (成本/安全/路由) |
| `packages/clawbot/src/litellm_router.py` | LLM 路由注册 + 模型排名 |
| `packages/clawbot/config/bot_profiles.py` | 7 Bot 人设 + 投资角色 |
| `apps/openclaw/AGENTS.md` | Bot 运行时行为指令 |

---

## 完整规则手册

详细的开发规范、命名规则、文档归属等完整规则见 `AGENTS.md` (项目根目录)。
