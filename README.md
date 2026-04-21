# OpenClaw Bot

> 7-Bot Telegram 多智能体系统 — 投资交易 / 社媒运营 / 闲鱼客服 / 生活自动化，集成 30+ 高星开源项目。

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.12, FastAPI, python-telegram-bot, LiteLLM, CrewAI, mem0 |
| Desktop | Tauri 2, React 18, TypeScript, Tailwind CSS, shadcn/ui, Zustand |
| Trading | yfinance, AKShare, CCXT, pandas-ta, IBKR bridge |
| Browser | browser-use, DrissionPage, crawl4ai |
| Infra | Docker Compose, Redis, Langfuse, loguru |

## Quick Start

### Prerequisites

- Python 3.12+
- Node.js 18+
- Rust (for Tauri)

### Backend

```bash
cd packages/clawbot
python -m venv .venv312
source .venv312/bin/activate
pip install -r requirements.txt
cp config/.env.example config/.env   # fill in your API keys
python multi_main.py
```

### Desktop Manager (Tauri)

```bash
cd apps/openclaw-manager-src
npm install
npm run tauri:dev
```

### Docker (optional)

```bash
docker-compose up -d
```

## Project Structure

```
OpenClaw Bot/
├── packages/clawbot/          # Python backend (core engine, bots, trading, tools)
├── apps/openclaw-manager-src/ # Tauri 2 desktop manager (React + TypeScript)
├── apps/openclaw/             # Bot configuration / skills / memory definitions
├── tools/                     # Installers & macOS LaunchAgents
├── docker-compose.yml
└── docs/                      # Project documentation
```

## Documentation

- `docs/README.md`：文档总入口，先看这个
- `docs/PROJECT_MAP.md`：项目全景与模块说明
- `docs/status/HEALTH.md`：已知问题与技术债
- `docs/CHANGELOG.md`：完整变更历史
- `docs/sop/FULL_AUDIT_PLAN.md`：全量审计总方案
- `docs/guides/OPENCLAW_APP_VISUAL_AUDIT_PROMPT.md`：OpenClaw APP 全量视觉级审计提示词

## License

Private / Proprietary
