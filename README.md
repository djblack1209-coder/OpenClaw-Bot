# OpenClaw Bot

> 7-Bot Telegram 多智能体系统参考实现：把 LLM 路由、Telegram 移动控制台、FastAPI 内控接口、Tauri 桌面管理端、运维观测和安全闸门组合成一个可学习、可二次开发的个人 AI 自动化项目。

[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.12-3776AB.svg)](packages/clawbot)
[![Desktop](https://img.shields.io/badge/desktop-Tauri%202%20%2B%20React-24C8DB.svg)](apps/openclaw-manager-src)

## 项目定位

OpenClaw Bot 是一个公开开源的 AI operations / personal automation 实验仓库，重点沉淀这些可复用模式：

- **多 Bot 协作**：7 个 Telegram Bot 分工处理系统状态、AI 号池、交易复盘、社媒、微信入口和运维提醒。
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

## 当前运行边界

本项目不是“双活服务器集群”，而是按职责拆分：

- **本机 Mac**：OpenClaw Gateway、Telegram Bot、Intel listener、桌面管理端与本地计划任务的主要运行位置。
- **Oracle ARM1**：承载独立的 JIYU / Sub2API 商业服务；它不是 OpenClaw Bot 的主运行节点。
- **Cloudflare**：提供 JIYU 公网入口与源站保护。其他服务器资产和跨项目链路由 `VPS-Config` 统一管理，不在本 README 重复维护。

备份计划已安装并按每日 03:30 运行。2026-09-04 的只读复查确认当次任务退出码为 0，本地归档与异地加密归档的校验摘要一致；当时未执行解密还原。2026-09-12 新闻归并另建本地备份并通过只读恢复演练，既有计划不变；这些证据不等同于完整异地灾难恢复闭环。

运行状态必须分别验证：本机 OpenClaw 使用项目健康脚本，JIYU 使用其独立生产健康与真实业务探针；单个 `/health` 不能代表整套项目正常。

新闻简报统一由 **Global Intelligence Bot** 的 Intel 管线提供，专用菜单为 `/today`、`/ai`、`/market`，每日业务时间为 **08:30 Asia/Singapore**。通用 ClawBot 的 `/news`、中文“科技早报”和微信 `104` 只显示专用 Bot 入口；旧科技早报生成器和自动推送已退役。运营日报、周报及按需新闻查询继续独立使用。迁移与验证见 [新闻归并记录](docs/090-news-consolidation-2026-09-12.md)。

## Quick Start

本地构建验证不会启动 Gateway、ClawBot、交易或消息发送。完整步骤与部署边界见 [快速开始](docs/005-quickstart.md)。

### 环境与锁文件

- Python **3.12.x**；macOS arm64 使用 `requirements-lock-macos.txt`，Linux amd64 使用 `requirements-lock.txt`。其他平台尚未验证。
- Node.js **22.19+（22.x）或 24.x**、npm **10.x 或 11.x**、uv；桌面 Rust 检查还需要 Rust/Cargo 与平台编译工具。本机实测 Node 22.22.3、npm 10.9.8、Rust 1.93.1；CI 配置使用 Node 24。
- Python、npm、Cargo 均使用仓库锁文件；验证不需要运行密钥。

### macOS：全新临时目录验证

从仓库根目录执行。脚本仅复制公开源文件，以哈希锁安装到新建临时目录；禁用 npm 安装脚本，构建和测试阶段隔离真实用户目录与外网。

```bash
python3.12 --version
node --version
npm --version
uv --version
bash scripts/check_clean_install.sh --component all --python "$(command -v python3.12)" --keep
```

以退出码及输出的 `WORK_DIR/results.json` 为准。保存成功、构建成功和服务运行通过是不同状态；Weixin 语义编译与完整 Linux 桌面验证的剩余项见 [审计闭环记录](docs/089-audit-closure-2026-09-10.md)。不要用 `pip install -r requirements.txt` 或 `npm install` 替代锁文件验收。

### Linux 容器与桌面部署

Linux 后端镜像固定 Python 基础镜像摘要，并使用 Linux 哈希锁。首次部署需要单独准备配置和数据目录，详见 [部署步骤](docs/005-quickstart.md#容器部署)。`docker compose up`、`npm run tauri:dev` 和 `make tauri-build` 会启动或安装实际服务，不属于上述本地验证。

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

- `docs/current/chatgpt-collaboration.md`：ChatGPT 规划、Codex 执行的使用与恢复说明（接入验收状态见文档）
- `docs/current/current-baseline.md`：本项目当前运行边界与接管入口
- `docs/001-project-map.md`：项目全景与模块说明
- `docs/004-architecture.md`：系统架构与 Bot 指令
- `docs/005-quickstart.md`：启动、部署、灾备、密钥轮换
- Git 历史：已完成变更、旧审计和迁移背景
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
- `docs/015-code-of-conduct.md`

## License

OpenClaw Bot 根项目采用 [Apache License 2.0](LICENSE)。

第三方子模块、上游源码包和运行资产可能使用各自许可证；请以对应目录内的 `LICENSE` / README / 上游仓库说明为准。
