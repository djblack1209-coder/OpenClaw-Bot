# 参与 OpenEverything

感谢你愿意改进这个项目。建议从一个可复现问题、一个失败场景测试或一处文档改进开始。项目的主要评审入口是[首页](../README.md)与[工程导览](017-engineering-tour.md)。

## 可以从哪里开始

| 方向 | 小而完整的贡献示例 | 入口 |
|---|---|---|
| AI 应用后端 | 为模型重试或未知用量增加回归案例 | [费用测试](../packages/clawbot/tests/test_cost_ledger.py) |
| 全栈体验 | 改善首次配置失败后的提示与恢复 | [Onboarding](../apps/openclaw-manager-src/src/components/Onboarding) |
| 情报调度 | 补充窗口边界或失败恢复案例 | [调度测试](../packages/clawbot/tests/test_intel_scheduled_cycle.py) |
| 文档与展示 | 翻译工程导览、改进移动端讲解页 | [展示页](../apps/project-showcase) |

这些是贡献方向，不代表已有分配给你的 Issue。开始较大的改动前，请在 [Issues](https://github.com/djblack1209-coder/OpenClaw-Bot/issues) 描述具体问题与范围。

## 准备环境

```bash
git clone https://github.com/djblack1209-coder/OpenClaw-Bot.git
cd OpenClaw-Bot
git switch -c codex/your-topic
```

仅修改文档或离线展示页，不需要配置 Bot、模型账号或运行服务。展示页运行方式见[首页](../README.md#快速体验)。

后端与桌面开发环境统一遵循[快速开始](005-quickstart.md#开发环境先验证再配置运行)的版本矩阵与锁文件。macOS 全新环境可从仓库根目录执行隔离安装检查：

```bash
bash scripts/check_clean_install.sh --component all --python "$(command -v python3.12)" --keep
```

它使用临时副本与锁定依赖；具体前置条件、结果目录和平台边界见快速开始。已有开发环境不需要每次重装。不要用未锁定的 `pip install -r requirements.txt` 或 `npm install` 替代锁文件安装，也不要覆盖现有配置。

## 修改与验证

保留他人未提交改动，一个 PR 解决一个明确问题。按影响范围选择已有测试：

| 改动范围 | 必要检查 |
|---|---|
| 文档、GitHub 入口 | `git diff --check`、`make docs-check` |
| 离线展示页 | JavaScript 语法、桌面/窄屏实际显示、全部受影响交互 |
| Python 逻辑 | 在 `packages/clawbot/` 用 `.venv312/bin/python -m pytest <相关测试路径>` |
| 桌面前端 | 相关现有测试、`npm run lint`、`npm run build` |
| Rust 原生逻辑 | `cargo test --locked <过滤器>`、`cargo check --locked` |

缺少真实设备或外部依赖时，说明测试方法、实际结果和未验证项。构建通过不能替代真实消息投递、安装后运行或计费对账。

`docker compose up`、`npm run tauri:dev`、`make tauri-build` 与 LaunchAgent 安装会影响运行环境，不属于纯构建检查。真实交易、账号操作、消息发送和收费调用保留原有授权边界。

## 提交 PR

描述用户会看到什么变化、为什么要改、如何验证，以及已知限制。遵循[PR 模板](../.github/pull_request_template.md)，无需为不相关模块填写通过结论。

- 不提交密钥、Cookie、token、二维码、浏览器资料、数据库或私人运行数据。
- 截图使用可复现的合成数据，并注明是演示还是实际运行结果。
- 新增文档留在既有 `docs/` 布局，按三位编号命名；当前生产事实只放在唯一[当前基线](current/current-baseline.md)。
- 依赖升级保留锁文件与许可证检查；不要以 `latest` 替换受管运行时。

漏洞请按[安全政策](014-security.md)私下报告。讨论遵循[行为准则](015-code-of-conduct.md)。
