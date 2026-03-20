# OpenClaw Bot Skills Pack

This pack curates local workspace skills for OpenClaw Bot and maps them to community references.

## 🆕 新增集成 (2026-03-19)

基于 GLM-OCR（智谱，2.9k stars）完善的 5 个 OCR skills:

- `glmocr` 📄 — 通用文字提取（图片/PDF/扫描件，OmniDocBench V1.5 第一名）
- `glmocr-table` 📊 — 表格识别与提取（复杂表格、合并单元格→Markdown）
- `glmocr-formula` 🔢 — 数学公式识别（→LaTeX 格式）
- `glmocr-handwriting` ✍️ — 手写体识别（多语言、多风格）
- `glmocr-sdk` 🔌 — SDK 程序化集成（pip install glmocr，批量处理/MCP 封装）

CLI 脚本: `apps/openclaw/tools/scripts/glm_ocr_cli.py`
前置条件: `ZHIPU_API_KEY`（https://open.bigmodel.cn）

## 🆕 新增集成 (2026-03-17)

基于 GitHub 热门 AI Agent 项目完善的 5 个新 skills:

- `openviking` 🗄️ — OpenViking 上下文数据库（字节跳动，替代 SQLite memory）
- `superpowers-workflow` ⚡ — 结构化开发方法论（obra/superpowers 90k stars）
- `cli-anything` 🔧 — 一键为任意 GUI 软件生成 CLI（HKUDS/CLI-Anything）
- `gstack-review` 🎯 — 多角色审查模式（YC 总裁 Garry Tan 的 gstack）
- `page-agent` 🌐 — 自然语言控制浏览器（Alibaba page-agent）

## Local skills enabled

- `usecase-playbook-router`
- `profit-war-room`
- `alpha-research-pipeline`
- `execution-risk-gate`
- `drawdown-kill-switch`
- `recovery-retrain-loop`
- `pnl-daily-brief`
- `clawbot-self-heal`
- `channel-command-center`
- `telegram-lane-router`
- `cost-quota-dashboard`
- `dev-todo-mode`

## Product & Design skills (from great-product-skills)

- `product-team` — 全流程产研 Team Agent（想法→Spec→Demo→走查）
- `pm-debate` — 高质量产品讨论，资深 PM 陪练
- `spec-generate` — 结构化 PRD 生成
- `frontend-design` — 生产级前端 UI 实现
- `web-artifacts-builder` — React + shadcn/ui 多组件原型
- `ux-walkthrough` — 系统性 UX 走查与问题报告
- `doc-coauthoring` — 协作文档撰写

## Telegram shortcut aliases

- `profit` -> `profit-war-room`
- `alpha` -> `alpha-research-pipeline`
- `risk` -> `execution-risk-gate`
- `recover` -> `recovery-retrain-loop`
- `brief` -> `pnl-daily-brief`
- `heal` -> `clawbot-self-heal`
- `channel` -> `channel-command-center`
- `playbook` -> `usecase-playbook-router`
- `lane` -> `telegram-lane-router`
- `cost` -> `cost-quota-dashboard`
- `dev` -> `dev-todo-mode`

## GLM-OCR skills (智谱 OCR)

- `glmocr` — 通用 OCR 文字提取
- `glmocr-table` — 表格识别
- `glmocr-formula` — 公式识别
- `glmocr-handwriting` — 手写体识别
- `glmocr-sdk` — SDK 程序化集成

## Reference mapping

| Local skill | Usecase inspirations | Skill-list inspirations |
|---|---|---|
| `profit-war-room` | `usecases/polymarket-autopilot.md` | `categories/search-and-research.md` (`reef-polymarket-research`) |
| `alpha-research-pipeline` | `usecases/earnings-tracker.md` | `categories/git-and-github.md` (`kiro-creator-monitor-daily-brief`) |
| `execution-risk-gate` | `usecases/polymarket-autopilot.md` | `categories/productivity-and-tasks.md` (`portfolio-risk-analyzer`) |
| `drawdown-kill-switch` | `usecases/polymarket-autopilot.md` | `categories/search-and-research.md` (`blacksnow`) |
| `recovery-retrain-loop` | `usecases/project-state-management.md` | `categories/productivity-and-tasks.md` (`ops-hygiene`) |
| `pnl-daily-brief` | `usecases/custom-morning-brief.md` | `categories/productivity-and-tasks.md` (`rho-telegram-alerts`) |
| `clawbot-self-heal` | `usecases/self-healing-home-server.md` | `categories/devops-and-cloud.md` (`agentic-devops`) |
| `channel-command-center` | `usecases/multi-channel-assistant.md` | `categories/web-and-frontend-development.md` (`create-agent-with-telegram-group`) |
| `telegram-lane-router` | `usecases/multi-channel-assistant.md` | `categories/communication.md` (`telegram-contact-sync`) |
| `cost-quota-dashboard` | `usecases/project-state-management.md` | `categories/data-and-analytics.md` (`lineary-api`) |
| `dev-todo-mode` | `usecases/autonomous-game-dev-pipeline.md` | `categories/coding-agents-and-ides.md` (`coding-agent`) |
| `usecase-playbook-router` | `usecases/README.md` | `categories/git-and-github.md` (`agent-team-orchestration`) |

## Activation path

1. Skills live under `apps/openclaw/skills/` (workspace scope).
2. Skill entries are enabled in `.openclaw/openclaw.json` under `skills.entries`.
3. OpenClaw loads workspace skills on the next session turn.

## Security note

- These local skills are instruction-only playbooks.
- Before adopting any third-party executable skill from public registries, review source code and permissions.
