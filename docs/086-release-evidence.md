# 全维度审计与软件闭环发布证据

> 日期: 2026-08-08
> 范围: 当前工作树、macOS arm64 桌面版 0.1.1、本机 OpenClaw 运行服务、Oracle Frist/JIYU 生产内测拓扑
> 规则: 只把可重复命令、自动化合同或真实运行结果计为完成；账号、凭据、真实资金和不可逆生产操作不以模拟结果冒充。

## JIYU 永久测试用户与安全回归

| 链路 | 真实结果 | 可复核数据 |
|---|---|---|
| Claude Code / 渠道B | 成功 | `claude-sonnet-4-6`；输入 327、输出 101、首 Token 3155 ms、总时长 7430 ms、计费 `$0.002496`；短单轮无缓存块 |
| OpenAI Responses / 渠道B | 成功 | `gpt-5.5`；非缓存输入 550、缓存读取 3840、输出 6；缓存输入占比 87.47%，首包 5889 ms、总时长 6150 ms、计费 `$0.004850` |
| Codex `0.147.0` | 成功 | 四个 OpenAI 文本账号使用官方 `http_bridge`；真实 Codex 记录 `openai_ws_mode=true`，输入 17287、输出 10、缓存读取 1408、首 Token 2482 ms、总时长 2964 ms、计费 `$0.087439` |
| 内容预拦截 | 成功 | 正常提示 200；高置信恶意短语约 840 ms 返回 403；用量记录仍为 8，无上游调用或计费 |
| Cloudflare | 成功 | Managed WAF、OWASP、L7 DDoS；注册/验证码 5 次/60 秒封禁 600 秒，登录/2FA 20 次/60 秒封禁 300 秒 |
| WebUI 深链刷新 | 观察 | 移动端 `/usage` 曾有 1 次瞬时 503；08-08 源站 25 次 503 均归因于明确失败测试或发布重启，05:04 后无新增，Console 0 error/0 warning |
| 账号列表品牌隐私 | 成功 | 生产 `v0.1.172-jiyu.31250692935` 重载后 12 个账号名称均为普通文本，供货域名链接为 0；Anthropic/OpenAI/Grok 生态标签保留，前后截图已入仓库。 |
| JIYU 同版兼容更新 | 成功 | systemd Unix 激活套接字保留应用 `NoNewPrivileges`；兼容包 CI `31250692935` 成功。生产真实 WebUI 最新版检查返回 HTTP 200/“已是最新版本”，耗时 302 ms，PID `1125212` 不变、无暂存文件。 |
| Apache 525 恢复 | 部署完成 | 全部 JIYU Apache 修改入口已统一执行配置校验、graceful reload、公网 HTTPS 复核，失败自动 full restart 并再次复核；生产管理器已安装，真实 happy path 与公网健康 5/5 为 200。为避免主动制造 525，full restart 分支以静态合同覆盖。 |
| Cloudflare 源站 443 | 成功 | 官方 CIDR 独立 nftables 表 active；三个独立外部 VPS 直连源站均超时，Cloudflare 公网首页/健康为 200，80 与 ACME timer 保持可用。 |
| PostgreSQL 预检 | 成功 | 修复 Headscale 日志初始化每两分钟清空 postgres ACL mask 的根因；故障转移任务手动运行后 ACL、SQL、Sub2API 健康和 WebSocket 代理均通过。 |
| 链动小铺 | 外部资金阻塞 | 七档资料与统一 Logo 已保存，未售临时码已轮换；平台保证金最低 ¥100、当前余额 0，未导入库存、未上架、未回填充值链接、未付款。 |

永久测试账号为用户 ID 2，必须保留；密码、API Key、Token 和 Cookie 只在钥匙串或服务器私有配置中，不出现在本报告。Codex WS 调度与源站 443 绕过已关闭；渠道A Claude 上游协议仍是未关闭 P1，链动保证金属于真实资金阻塞，见 `docs/009-health.md` HI-1001、HI-987。

## 结论

本轮从功能正确性、架构与并发、安全、供应链、测试、桌面发布、灾备恢复、运行健康和用户体验九个方向完成复审。审计发现的可在软件侧关闭的问题已登记为 HI-965 至 HI-978，并完成代码、聚焦回归或实机闭环；当前没有未处理的 P0/P1 软件缺陷。

最终 `make ci-local` 11/11 退出 0；本机每日备份已实际运行并通过恢复演练；Intel Brief 真实旧数据库已备份并迁移到 schema v4；桌面 App/DMG 已重新构建并原子安装。当前健康检查唯一黄色项是 Intel Brief 等待首次 08:30 自然投递验证，为避免向真实 Telegram 提前发消息，没有用人工强启伪造成功。

## 自动化验证

| 验证面 | 末次结果 | 关键边界 |
|---|---|---|
| 全量 CI | `make ci-local` 11/11 退出 0 | 同一入口覆盖依赖、安全、Ruff、Python、前端、Frist、桌面合同、Rust、文档和供应链 |
| Python | 2,407 项收集；2,405 通过、2 项预期跳过、0 失败 | 总覆盖率 45%；高风险关键聚合覆盖率 88% |
| 高风险聚焦 | 闲鱼/owner/API `208/208`；Intel `37/37`；自动运维 `21/21` | 事件循环所有权、幂等履约、旧库迁移和灾备均有直接回归 |
| Frist | `234/234` | 认证、限流、支付、runtime store、并发写入和失败关闭 |
| 桌面合同 | `39/39` | 本机进程白名单、临时文件、备份/恢复、构建与回滚合同 |
| 前端 | TypeScript、ESLint、Vite build 全部退出 0 | Vite 转换 2,526 modules |
| Rust | `47/47`，`cargo check --locked` 通过 | Tauri 显式命令白名单和本机参数边界 |
| 文档 | `make docs-check` 为 `24/24` | 扁平目录、编号、索引和事实一致性 |

## 安全与供应链

| 安全门 | 结果 |
|---|---|
| ShellCheck | 仓库 35 个 Shell 脚本零告警 |
| Gitleaks | 859 个提交历史、当前 diff 和未跟踪文件均未发现泄漏 |
| npm audit | 桌面完整/生产、Frist、受管 runtime 四套 production 审计均为 0 |
| pip-audit | Linux/macOS 两份哈希锁均无已知漏洞 |
| RustSec | 0 vulnerability；17 条仅为已登记的目标平台/上游 informational warning |
| 供应链 | 2 个工作流、16 个固定 Action SHA、354 个 npm 锁包、Compose 镜像 digest 全部通过静态门 |
| 干净安装 | 260 个 Python 锁定分发包及前端锁文件在临时目录复算成功 |
| 容器 | amd64 完整镜像从哈希锁构建；以 `uid=999 gid=999` 非 root 运行并完成 `imports=ok` 冒烟 |

## 架构闭环

| 热点 | 审计前 | 当前事实 | 决策 |
|---|---:|---:|---|
| `apps/frist-api/server/server.js` | 8,123 行 | 7,943 行；新增 214 行 `runtime-store.js` 深模块 | 原子写、串行 mutation、敏感字段加密已下沉；入口继续只做组合 |
| `xianyu_admin.py` | 5,780 行 | 5,557 行；新增 300 行 `operations_projection.py` | owner-loop 只导出不可变快照，运营视图统一纯投影 |
| `api/rpc.py` | 4,440 行 | 4,440 行 | 冻结为兼容门面；新行为只能进入领域 router/module，避免高风险大重写 |

这不是以“拆文件数量”冒充架构优化：下沉模块分别锁住持久化事务和跨线程状态投影，原入口不能再直接承担这些职责。完整图解见本机架构报告。

## 真实运行证据

### 每日备份与恢复

- `ai.openclaw.daily-backup` 已安装为每天 03:30 自动执行，并在真实 LaunchAgent 运行中退出 0。
- 最近实机包：`~/.local/share/openclaw/backups/openeverything-20260805-034824.tgz`。
- 备份使用 SQLite 在线备份、包内逐文件 manifest、包外 SHA-256 和原子 `.ready`；同一轮恢复 drill 已通过路径、哈希和 SQLite `quick_check`。
- 离机目标只接受 GPG 密文；未配置公钥或独立目标时 `--require-offsite` 固定失败，不会把明文密钥/Cookie 同步出去。

### Intel Brief 真实旧库

- 真实库曾为 schema v3，`content_delivery_attempts` 缺少 `event_key`，2026-08-04 定时任务因此退出 1。
- 迁移前 root-only 备份：`~/.local/share/openclaw/migrations/intel_brief-before-v4-20260805-034441.db`。
- 备份 SHA-256：`db845bc5ce4e380086090eeef38bd5e27f54dbf89af3cb2d59e88cc496f036cf`。
- 备份和迁移后数据库 `quick_check=ok`，当前 `user_version=4`；LaunchAgent 已重新加载并等待自然调度。

### 桌面发布

- `make tauri-build` 生成并安装 `OpenClaw 0.1.1`，`/Applications` 只有 `OpenClaw.app`，没有旧 `OpenEverything.app`。
- 当前 App 严格 ad-hoc 签名有效，Identifier 为 `com.openclaw.manager`，CDHash 为 `143d02e6466da2a3e43c3c545d0de2d7f5837a7b`。
- DMG：`apps/openclaw-manager-src/src-tauri/target/release/bundle/dmg/OpenClaw_0.1.1_aarch64.dmg`，SHA-256 为 `f1cb24afa1ab8562b6b8fdd4e8dfc744da357e8a46fd7be316ca81e6ebbe2b11`。
- `make tauri-rollback-check` 返回 `rollback_ready=true`；上一版 CDHash 为 `42799197e82ee94bea79ccfdbb0a906909c910b0`，与当前版本不同。
- Apple 公证因未提供 Developer ID 凭据而按设计跳过，不冒充公开分发签名。

## 用户可感知证据

- 最新安装版首屏：`output/playwright/openclaw-installed-app-audit-20260805.png`。
- 架构闭环桌面/移动：`output/playwright/architecture-review-desktop.png`、`output/playwright/architecture-review-mobile.png`。
- Scheduler：`output/playwright/scheduler-contract-desktop-fixed.png`、`output/playwright/scheduler-contract-mobile-fixed.png`。
- 实盘卖出确认：`output/playwright/portfolio-sell-confirm-desktop.png`、`output/playwright/portfolio-sell-confirm-mobile.png`。

## 软件外剩余边界

以下项目不能由代码安全代办，也不属于未修软件缺陷：

- Apple Developer ID 购买/续费与公证凭据。
- 用户选择的 GPG 公钥、独立硬盘或远端备份账号。
- 第三方平台历史凭据轮换及平台回执。
- 真实商户支付、真实闲鱼小额单等会产生资金或外部消息的最终验收。
- 7 日可用率和投递率由系统自然累计；无需手工维护，未满观察窗前不伪造 SLI。
