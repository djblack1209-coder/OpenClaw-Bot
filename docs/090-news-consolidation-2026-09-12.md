# 科技早报归并到 Global Intelligence

## 结果与归属

用户反馈的 2026-09-11「科技早报」来自 `packages/clawbot/src/news_fetcher.py` 的旧格式生成器，由 `ExecutionScheduler` 的 `morning_news` 任务经通用 ClawBot 投递。它与独立 Intel 新闻产品重复，而且发送 Bot 归属错误。本次移除旧生成器、自动任务与调度器专用抓取注入；通用新闻查询、监控和社媒采集所需的 `NewsFetcher` 保留。

Telegram `/news`、历史中文触发、旧按钮和微信 `104` 统一返回 Global Intelligence Bot 入口。微信 `104` 不再错误调用运营日报 API。专用 Bot 已有 `/today`、`/ai`、`/market`；本次只读 `getMe` 确认其显示名为 Global Intelligence，实际 username 写入本地配置，不把 token 或用户目标纳入仓库。

`ReportPreferences` 对 `morning_news` 永久禁用，旧环境变量、控制面启用记录和已缓存待发报告均不能恢复旧投递。控制面移除旧任务，旧 toggle 返回 410；数据库保留历史记录。普通运营日报和周报继续走各自的投递合同。

## 运行修复与调度

- 本次操作前，本机 ClawBot 运行中的控制面显示旧早报 2026-09-11 已发送。已原子写入任务禁用，并通过认证 API 回读禁用生效；仅修改该任务及专用 Bot username 配置。
- 独立 Intel listener 已加载运行。旧 scheduler 最近证据为 `blocked / skipped_late_trigger / network_calls=0`：Mac 使用 America/New_York，LaunchAgent 按宿主 08:30 唤醒，Intel 却按 Asia/Singapore 的 08:30–10:00 窗口判定。
- 用户明确确认沿用 **08:30 Asia/Singapore**。修复后的宿主每小时 `:30` 唤醒，生产 CLI 使用 `--scheduled`，由真实业务时区窗口与持久每日执行权共同决定是否运行；纽约夏冬令时均不会把业务时间改成当地 08:30。
- 每日执行权先持久化再调用生产周期，同一日并发、重启、失败或未知结果不会自动再次投递；窗口外跳过不覆盖上一份真实周期证据。失败后人工核对原回执和状态，不能删除执行记录强制重发。

ClawBot 已完成一次重载：认证 API 确认调度器运行、旧任务已从列表移除；实际本地微信 `104` 路由返回专用 Bot 链接与菜单；Telegram `getMyCommands` 回读 `/news` 的新入口说明。测试没有通过外部聊天发送新闻。独立 Intel 调度已原子安装并回读加载状态，原凭据、输出和日志路径保持一致；按真实当前时间运行其入口，确认窗口外 `skipped_late_trigger`、`network_calls=0`，上一份真实 cycle 内容未变。新自然投递仍未验收。

微信扩展源码也覆盖 `104` 和历史早报词；本地 bridge 不可用时返回固定引导，发送结果不明时不重发、不进入普通 AI。该扩展当前未配置为活动 Gateway 插件，未启用或重载它，真实微信入站未验证。

## 本次验证

- 新闻入口、旧调度、投递保护和恢复 review 最终隔离组合 105 项通过；此前独立鉴权组合 68 项通过。运行使用临时源码、隔离用户路径和禁止外网的 runner。
- 当前前端 58 项既有测试、lint、精确锁干净安装和 build 通过。已有安装缺少 3 个 lucide-react 文件，从同锁副本核实后仅补齐缺失项，已有文件未覆盖。
- Rust 配置测试 26 项及 `cargo check --locked` 通过；Cargo.lock 未变。九组依赖审计完成，未发现漏洞；Rust 仍有 7 条既有 warning（6 条 unmaintained、1 条 unsound）。
- 修复安装检查从 Shell 迁到 Python 后留下的旧断言，运维脚本回归 27 项通过。供应链、Python 平台锁、ShellCheck、Gitleaks 通过；容器静态合同 3 项通过，依赖独立 BuildKit 的 1 项未执行。
- 后端成本、鉴权、观测与手动交易组合 **670 项通过、零警告**。现有 Python 环境缺失的 14 个文件经匹配锁定 wheel 及其他 2980 个文件完整核对后排他补齐，未覆盖文件或改变版本。观测测试修复 SDK 后台日志入队与清理之间的竞态，严格协程警告回归通过。
- 微信 bridge 离线行为测试 20 项通过；已将其及费用、引导、卖出状态回归接入 CI，最终 Node CI 组合 **98 项通过**。微信 helper 的 TypeScript 检查通过，但扩展整包缺 `tsconfig.json`，整包语义构建未通过验收。
- 跨时区调度、生产周期、LaunchAgent 生成和 readiness 等 **91 项隔离回归通过**，测试复制边界另 3 项通过；独立复核通过。慢采集超过 10:00 或跨新加坡业务日时，最终发送闸门重新检查真实时间并阻断投递。
- 文档检查通过（23 个文档），差异空白与密钥扫描通过。旧审计 C07/C08 的 Linux 整合、GUI 真实流程及商业验收等未完成项仍按 089 保留，不因本次合并而标为完成。

## 备份与回滚

新备份仅保存在本机专用目录，既有每日与异地备份任务不变。改动前后分别保存归档并执行 checksum、路径、manifest 和 SQLite 只读恢复演练；25 项 inventory warning 为既有可选路径缺失或跳过，不等同于完整灾备恢复。另保存 Git bundle、运行配置、原 LaunchAgent 前态和缺失依赖文件的恢复清单；含私有数据的归档及证据不纳入 Git。

回滚仅恢复本次修改的配置和 LaunchAgent，并仅重载对应服务；不得整库覆盖费用、订阅或投递记录。即使源码回滚，旧 `morning_news` 的运行控制仍应保持关闭，避免重新出现双份新闻。独立 Intel 的每日执行权和回执必须保留以防重复发送。

## 提交范围

用户要求提交所有改动，因此保留的前轮审计实现、相关测试和文档与本次修复一并纳入。检查点文档中的旧失败、未验收和外部依赖继续保留。实际提交、main 合并和远端回读结果以本次最终 Git 验证为准。
