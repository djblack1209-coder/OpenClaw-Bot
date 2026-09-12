# OpenEverything / OpenClaw Bot 项目约定

本仓库包括本机 Gateway、ClawBot、Intel 调度与 Tauri 管理端，以及独立服务的运维材料。交付必须对应用户要求的那条业务路径。

## 按任务选择入口

- 项目用途与环境：`README.md`；模块归属不明确时看 `docs/001-project-map.md`，跨模块设计看 `docs/004-architecture.md`。
- Python 后端：`packages/clawbot/multi_main.py`、`packages/clawbot/src/` 和相关 `tests/`；LLM 路由先定位 `src/llm_routing_config.py` 与实际调用方。
- 桌面端：`apps/openclaw-manager-src/`，React / TypeScript 在 `src/`，原生命令在 `src-tauri/`。涉及前后端接口时同步契约、鉴权与调用方。
- 运行诊断、启动或部署：`docs/current/current-baseline.md`、`docs/005-quickstart.md`；跨服务器操作再查 VPS-Config 当前资产归属和运行合同。
- 安全、账户、消息或交易边界：`docs/014-security.md` 与对应业务源码。
- ChatGPT 规划、只读连接或恢复：`docs/current/chatgpt-collaboration.md` 与已安装的 codex-with-chatgpt 技能。普通本地修改无需启动网页规划环节。

## 非显然的约束

- `apps/openclaw/` 中的人设、技能和运行材料用于 Bot；其局部指令不扩展为整个仓库的开发人设。第三方源码与子模块遵守各自局部说明及固定版本。
- 本地源码目录、vendor 包和实际 Gateway 安装版本分别核实。使用当前 npm runtime lock、Python 平台哈希锁及 Cargo.lock，不以 latest 覆盖正在运行的环境。
- 保留用户及并行任务的未提交工作。修改前核对当前文件与 Git 差异，编辑限于本次目标；不为“清理”回退其他任务的内容。
- 本地文档、隔离测试和静态构建可自主连续完成。`docker compose up`、`npm run tauri:dev`、`make tauri-build`、LaunchAgent 安装和调度器启动会影响实际运行状态，按任务授权及相应恢复约束执行。
- 通知、社媒发布、账户修改、真实交易和收费模型调用保留现有业务闸门。验证优先使用隔离数据与替代传输；没有相应授权时，不发送真实消息或触发账户/费用副作用。
- 配置优化和代码验证不授予生产发布权限。生产写入仍需新鲜前态、可恢复备份、原子幂等应用、失败回滚和真实业务验证。
- 不输出或提交 `.env`、token、会话、浏览器资料、交易凭据、私有连接地址及运行数据。

## 验证与完成

- 仅文档 / 指令：`git diff --check`；文档结构或入口变化时运行 `make docs-check`。文档留在现有 `docs/` 布局；新增根级说明仅使用 `AGENTS.md`。
- Python：使用 `packages/clawbot/.venv312/bin/python`（存在时），从 `packages/clawbot/` 对受影响测试运行 `python -m pytest <相关测试路径>`；缺环境时按 quickstart 的平台锁设置隔离环境。
- 桌面前端：在 `apps/openclaw-manager-src/` 运行相关现有测试、`npm run lint` 和 `npm run build`；Rust 改动在 `src-tauri/` 选择相关 `cargo test --locked <过滤器>` 与 `cargo check --locked`。界面交付检查实际受影响流程。
- 依赖、安装或发布范围使用 Makefile 的对应锁文件、供应链、clean-install 与 CI 检查；普通编辑不默认执行 `make ci-local`、重装或启动服务。
- 完成用户要求的实现、相关验证与必要修复后交付。运行结果分别报告本机 Gateway、ClawBot、自然调度产物和独立远端服务；health 成功不代表消息已投递、计费正确或整体运行验收通过。
