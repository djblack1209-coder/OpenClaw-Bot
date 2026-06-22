# OpenClaw Bot

> 7-Bot Telegram 多智能体系统参考实现：把 LLM 路由、Telegram 移动控制台、FastAPI 内控接口、Tauri 桌面管理端、运维观测和安全闸门组合成一个可学习、可二次开发的个人 AI 自动化项目。

[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.12+-3776AB.svg)](packages/clawbot)
[![Desktop](https://img.shields.io/badge/desktop-Tauri%202%20%2B%20React-24C8DB.svg)](apps/openclaw-manager-src)

## 项目定位

OpenClaw Bot 是一个公开开源的 AI operations / personal automation 实验仓库，重点沉淀这些可复用模式：

- **多 Bot 协作**：7 个 Telegram Bot 分工处理系统状态、AI 号池、交易复盘、闲鱼客服、微信入口和运维提醒。
- **LLM 路由与成本控制**：用 LiteLLM 风格的统一路由、免费优先策略、收费模型闸门和低敏健康统计管理多 Provider。
- **手机 + 桌面双控制面**：Telegram 命令卡片适合手机操作，Tauri + React 管理端适合本地配置、可视化和调试。
- **开源集成编排**：集成 FastAPI、python-telegram-bot、CrewAI、browser-use、crawl4ai、Redis、APScheduler、Plotly 等生态工具。
- **安全维护流程**：默认不提交密钥，不回显 token，不自动执行高风险动作；文档中记录验证、回归和已知边界。

> 说明：仓库包含交易、社媒、浏览器自动化等模块，但它们在本项目中的定位是**受控研究和个人助理场景**。任何真实交易、平台账号操作、抓取、通知或发布都必须遵守当地法律、平台条款和人工确认流程。

## Tech Stack

| Layer | Technology |
|-------|------------|
| Backend | Python 3.12, FastAPI, python-telegram-bot, LiteLLM-style routing, CrewAI, mem0 |
| Desktop | Tauri 2, React 18, TypeScript, Tailwind CSS, shadcn/ui, Zustand |
| Trading / Analysis | yfinance, AKShare, CCXT, pandas-ta, IBKR bridge |
| Browser / Web | browser-use, DrissionPage, crawl4ai |
| Infra / Ops | Docker Compose, Redis, Langfuse, loguru, APScheduler |

## Quick Start

### Prerequisites

- Python 3.12+
- Node.js 18+
- Rust toolchain（Tauri 桌面端需要）
- Telegram Bot token、LLM Provider Key 等运行密钥（只放在本机 `.env`，不要提交）

### Backend

```bash
cd packages/clawbot
python -m venv .venv312
source .venv312/bin/activate
pip install -r requirements.txt
cp config/.env.example config/.env
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

```text
OpenClaw Bot/
├── packages/clawbot/          # Python 后端：Bot、路由、API、交易/客服/运维模块
├── apps/openclaw-manager-src/ # Tauri 2 桌面管理端
├── apps/openclaw/             # Bot 人设、技能和运行资产
├── tools/                     # 安装器与 macOS LaunchAgent
├── docker-compose.yml
└── docs/                      # 项目文档治理中心
```

## Documentation

- `docs/003-docs-index.md`：文档总入口
- `docs/001-project-map.md`：项目全景与模块说明
- `docs/004-architecture.md`：系统架构与 Bot 指令
- `docs/005-quickstart.md`：启动、部署、灾备、密钥轮换
- `docs/006-registries.md`：API 池、命令、依赖、模块注册表
- `docs/009-health.md`：已知问题、技术债和健康状态
- `docs/002-changelog.md`：变更历史
- `docs/013-contributing.md`：贡献指南
- `docs/014-security.md`：安全政策与漏洞报告

## Safety and acceptable-use boundaries

为了让项目更适合作为公开开源样例，仓库默认坚持以下边界：

- 不提交 `.env`、API Key、Cookie、token、证书、浏览器 Profile 或交易凭证。
- 不把 LLM 输出直接作为真实投资建议或自动下单依据；真实交易必须人工确认并独立承担风险。
- 不用自动化绕过验证码、登录保护、付费墙、平台风控或平台服务条款。
- 不做刷量、垃圾信息、欺骗性社媒发布或未授权数据抓取。
- 对外部输入、Webhook、文件读写和命令执行保留鉴权、脱敏、白名单和确认码。

## Contributing

欢迎 issue、文档补充、测试用例、Bug 修复和小型 PR。开始前请先阅读：

- `docs/013-contributing.md`
- `docs/014-security.md`
- `AGENTS.md`

## License

OpenClaw Bot 根项目采用 [Apache License 2.0](LICENSE)。

第三方子模块、上游源码包和运行资产可能使用各自许可证；请以对应目录内的 `LICENSE` / README / 上游仓库说明为准。
