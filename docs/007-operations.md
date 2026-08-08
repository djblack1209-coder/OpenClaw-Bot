
# 运维操作手册

> 合并自原 024-frist-api-operator-runbook.md + 025-frist-api-quickstart.md + 026-xianyu-cookie-guide.md + 029-deployment-checklist.md

## 2026-08-08 当前主站：JIYU AI（Sub2API 底座）

当前用户主站 `https://jiyu.245334.xyz` 的对外品牌为 `JIYU AI`，运行基于官方 Sub2API `v0.1.172` 固定提交构建的 `v0.1.172-jiyu.31250692935`。JIYU 改动以仓库补丁固化，WebUI 只安装通过聚焦门和完整性清单的 JIYU 兼容包，不会用官方原版覆盖定制。

| 项目 | 当前值 |
|---|---|
| 对外品牌 | `JIYU AI` / `Unified AI API Gateway` |
| Sub2API | `sub2api.service`，`127.0.0.1:18080` |
| PostgreSQL | `sub2api` 独立数据库，PostgreSQL 16；备份与更新前强制预检 |
| Redis | `sub2api-redis.service`，`127.0.0.1:16379` |
| 自动更新 | `sub2api-update.timer` 每日检查官方 release；管理员从 WebUI 显式安装 JIYU 兼容包 |
| 自动备份 | `sub2api-backup.timer`，每日 PostgreSQL 一致性备份，`/var/backups/sub2api` 保留 30 天 |
| 管理员邮箱 | `djblack1209@gmail.com` |
| 管理员密码 | macOS 钥匙串服务“CC中转 Sub2API 管理员”；Oracle env 仅 root 可读 |

### 当前运营配置（2026-08-08）

- 两个上游分别使用 5 个新建 JIYU 专用 Key，不复用历史 Key。日常补号继续进入“账号管理”，日常轮换上游 Key 时保持同名专用用途并在站内执行真实测试。
- 10 个用户分组统一采用“上游账号倍率 + `0.05x`”绝对加价。修改任一上游倍率后，必须同步修改对应分组并核对差值仍为 `0.0500`；渠道A OpenAI Pro 为 `0.095 → 0.145`，OpenAI Plus 为 `0.06 → 0.11`。
- 10 个文本渠道加 2 个生图渠道已启用并分别绑定一个分组；10 条文本监控每 300 秒执行、随机抖动 ±30 秒。2 条生图监控配置也固定为 300±30 秒并保存加密凭据，但因上游 502/401 保持禁用，避免持续错误探测或付费请求。页面固定先显示渠道A再显示渠道B；红色/降级表示真实波动，不得手工改成绿色。
- `Anthropic`、`OpenAI`、`Grok` 是帮助用户识别模型/API 生态的产品标签，必须保留；匿名化对象仅限真实供货上游及其域名，用户可见渠道统一为渠道A/渠道B。
- 上游安全白名单只新增 `api.aigo0.com`、`www.huyunapi.com`，私网和不安全 HTTP 仍拒绝。

### 永久测试账号与真实客户端基线（2026-08-08）

- 永久测试账号为 `jiyu-e2e-20260808@245334.xyz`（用户 ID 2），必须保留；密码和两个活动 Key 分别存入 macOS 钥匙串，不得输出、截图或写入仓库。旧 OpenAI Key 已轮换并停用，历史用量保留用于对账。
- Claude Code 使用 `ANTHROPIC_BASE_URL=https://jiyu.245334.xyz` 和独立 Claude Key。渠道B连续两次成功；服务端成功样本为输入 327、输出 101、首 Token 3155 ms、总时长 7430 ms、站内计费 `$0.002496`。短单轮提示没有可复用缓存块，缓存为 0 属预期；渠道A对应分组当前 0 个可调度账号，真实返回 503，禁止继续对外显示为可用。
- OpenAI Responses 使用 `https://jiyu.245334.xyz/v1` 和独立 OpenAI Key。最近成功样本为非缓存输入 550、缓存读取 3840、输出 6，缓存占总输入 `87.47%`，HTTP 客户端首包 5889 ms、总时长 6150 ms，服务端处理 4609 ms，站内计费 `$0.004850`、上游实际成本 `$0.0011155`。
- Codex `0.147.0` 默认 Responses WebSocket。Apache upgrade 代理和 Sub2API 官方模式路由均已启用，四个 OpenAI 文本 API Key 账号在 WebUI 使用 `HTTP 桥接（http_bridge）`，两个生图账号保持关闭。最小 WS 样本客户端首输出 4287 ms、总时长 4524 ms，缓存 3840/4395；真实 Codex 服务端首 Token 2482 ms、总时长 2964 ms，记录为 `openai_ws_mode=true`。
- 本轮账号共有 10 条真实计费记录；内容拦截 403 后记录数不增加，证明预拦截请求没有进入上游或扣费。每次体验回归只跑一组最小真实请求，不循环消耗余额。

Apache 规则必须位于通用根代理之前；未来重装或配置漂移后执行：

```bash
ssh oracle-arm1 '/usr/local/sbin/openclaw-sub2api-manager responses-websocket'
ssh oracle-arm1 '/usr/local/sbin/openclaw-sub2api-manager openai-ws-http-bridge'
ssh oracle-arm1 '/usr/local/sbin/openclaw-sub2api-manager status'
```

账号级模式在“账号管理”中保存，不直接改数据库。只筛选四个 OpenAI Pro/Plus 文本账号，批量把 `WS mode` 设为 `HTTP 桥接（http_bridge）`；生图账号保持 `off`。如需回滚，先在 WebUI 把四个账号恢复为 `off`，再执行 `ssh oracle-arm1 '/usr/local/sbin/openclaw-sub2api-manager openai-ws-legacy'`。

### 风控、反注册机与 Cloudflare（2026-08-08）

- Sub2API 风控和会话级阻断已启用；内容审核使用 `pre_block + keyword_only`，7 条中英文高置信系统提示词窃取短语命中时返回 403，10 次命中进入自动封禁统计。没有外接内容审核 API，因此不会额外外传提示词或增加模型前置网络耗时。
- 真实验证：正常提示返回 200；精确恶意短语在约 840 ms 内返回 `content_policy_violation`，无上游调用和计费。关键词规则只覆盖确定性短语，不等价于语义级防提示注入，新增规则前必须复核误伤。
- 开放注册保持关闭、邮箱验证保持开启。源站 Redis 限流为注册 5 次/分钟、登录 20 次/分钟、验证码 5 次/分钟；Cloudflare 对同一主机再叠加注册/验证码 5 次/60 秒并封禁 600 秒、登录/2FA 20 次/60 秒并封禁 300 秒。
- Cloudflare 代理、严格 SSL、最低 TLS 1.3、Managed WAF、OWASP、L7 DDoS 和高安全级别均启用。Super Bot Fight Mode 没有做全区域一刀切，避免误伤 `/v1` 的 Codex/Claude 等合法非浏览器客户端和同区域其他站点。
- Turnstile 当前关闭。正式开放注册前必须先创建 JIYU 专用 widget，再以桌面/手机真实注册、验证码、失败和无障碍流程验收；不得直接复用历史 New-API 口径声称已开启。
- Oracle 443 第一阶段已收口：`jiyu-cloudflare-origin.service` 从 Cloudflare 官方地址页下载并校验 CIDR，只允许 Cloudflare、loopback 和 Tailscale 访问 443。应用命令先安排 5 分钟自动回滚；必须从独立外部主机确认直连源站超时后，才能执行确认命令取消回滚。
- 2026-08-08 验收：三个 HTTPS vhost 经 Cloudflare 分别返回 200/301/预期未授权 404；三个独立外部 VPS 直连源站 443 均超时。80 TCP、SSH、Tailscale 未改，`naive-cert-renew.timer` active 且最近结果 success。
- 第二阶段先把 `naive-iad` 的证书签发迁到 DNS-01、独立入口或其他不依赖公网 80 的方案，再单独评估 80 收口。80 收口涉及共享主机网络，未获确认前只保留方案和只读证据，不应用对应规则。

### 邮箱绑定、验证码与告警

1. 用户从“个人资料 → 管理邮箱”输入邮箱并点击“发送验证码”，收到带 JY 图形 Logo 的 `JIYU AI 邮箱绑定验证码`；输入验证码和当前密码后才会更换主邮箱。
2. “系统设置 → 安全与认证”保持邮箱验证开启、开放注册关闭；需要开放内测注册时必须先确认地区条款、邀请码和风控策略。
3. Gmail SMTP 使用 `smtp.gmail.com:587` + TLS。应用密码只保存在服务器设置中；不得写入本文件、仓库或截图。
4. `auth.verify_code`、`notification_email.verify_code` 和 `ops.alert` 模板已品牌化。图形 Logo 公网地址为 `https://jiyu.245334.xyz/api/v1/pages/docs/images/jiyu-ai-logo.png`。
5. SMTP“测试邮件”只有连接成功标识，不含验证码；验收验证码必须从个人资料的真实邮箱绑定入口触发。2026-08-07 实际发送接口返回 HTTP 200。
6. 忘记密码和 Passkey 已启用。Passkey 部署配置固定为 `JIYU AI`、RP ID `jiyu.245334.xyz`、来源 `https://jiyu.245334.xyz`；修改前备份 `/opt/sub2api/data/config.yaml`，重启后必须复核本地/公网健康和 WebUI 的 RP 状态。
7. 余额不足邮件提醒已开启，默认阈值 `$1`，充值链接为 `https://jiyu.245334.xyz/custom/recharge-center`。账号限额通知未启用，先确认通知邮箱、静默窗口和去重策略。
8. Turnstile、LinuxDo、GitHub/Google 邮箱快捷登录没有真实专用凭据，保持关闭；开放注册继续关闭、邮箱验证继续开启。不得填入测试占位值冒充已配置。

### 文档和 CC Switch

- 左侧“文档”进入 `https://jiyu.245334.xyz/custom/docs`，提供 CC Switch v3.19.2 三平台下载。“API 密钥”页和创建弹窗固定同时显示 Claude 根端点与 ChatGPT `/v1` 端点，并默认勾选创建后导入 CC Switch。
- OpenAI 兼容地址为 `https://jiyu.245334.xyz/v1`，Claude 兼容地址为 `https://jiyu.245334.xyz`。Key 只在站内创建并导入本机 CC Switch，不发送给未配置外站。
- 文档页手机端隐藏内置目录侧栏，避免正文被覆盖；桌面端保留目录。

### 小白首次使用与补号

1. 打开 `https://jiyu.245334.xyz/login`，使用管理员邮箱登录。首次进入后台必须由实例负责人本人阅读并完成“部署与运营合规确认”，不要交给自动化脚本代为同意。
2. 左侧进入“分组管理”并创建分组。分组相当于一个可用模型套餐，先选择平台并确认倍率；只自用也建议先建一个清晰命名的测试分组。
3. 左侧进入“账号管理”并点击“添加账号”。这就是日常所说的“补号”：选择 Anthropic、OpenAI、Gemini 或 Grok，再按页面选择 OAuth、Setup Token、API Key 等添加方式。只使用本人有权使用且符合上游条款的账号或 Key。
4. 把新增账号绑定到对应分组，保持“可调度”开启；添加后先在账号列表执行测试并确认状态正常。账号失效或额度不足时，也回到“账号管理”处理重新授权、停用或添加替代账号。
5. 左侧“API 密钥”点击“创建 API 密钥”，选择刚才的分组。生成的 Key 只展示给需要调用的客户端，不要发到聊天或提交到仓库。

首次登录会显示官方 21 步引导，顺序就是“分组管理 → 账号管理 → API 密钥”。“用户管理”是管理下游用户，“渠道管理”是平台定价/状态，不是补号入口。

小白日常只需要看这三个命令（不打印密码）：

```bash
ssh oracle-arm1 '/usr/local/sbin/openclaw-sub2api-manager status'
ssh oracle-arm1 '/usr/local/sbin/openclaw-sub2api-manager check'
ssh oracle-arm1 'systemctl list-timers sub2api-update.timer sub2api-backup.timer --no-pager'
```

数据库或源站权限异常时只使用管理器入口：

```bash
ssh oracle-arm1 'sudo /usr/local/sbin/openclaw-sub2api-manager postgres-preflight'
ssh oracle-arm1 'sudo /usr/local/sbin/openclaw-sub2api-manager cloudflare-origin-443'
# 仅在独立外部主机确认直连 443 已阻断且公网域名正常后执行：
ssh oracle-arm1 'sudo /usr/local/sbin/openclaw-sub2api-manager confirm-cloudflare-origin-443'
ssh oracle-arm1 'sudo /usr/local/sbin/openclaw-sub2api-manager rollback-cloudflare-origin-443'
```

`update` 当前默认只检查。发布新的 JIYU 构建必须先从固定官方提交应用 `scripts/sub2api-jiyu-v0.1.172.patch`、完成聚焦验证和 ARM64 构建，再执行 `SUB2API_JIYU_VERSION=<version> openclaw-sub2api-manager install-jiyu-build <path>`。该命令会先备份并在健康失败时回滚；不要直接替换二进制或修改 Apache。

WebUI 更新方案 A 已在仓库和生产启用：`.github/workflows/sub2api-jiyu-compat.yml` 只发布通过补丁、类型检查、嵌入式前端根页和聚焦测试的 ARM64 兼容包及 SHA-256 清单；首个基础版使用不可变 `jiyu-vX.Y.Z` 标签，同一上游版本的手动修订使用不可变 `jiyu-vX.Y.Z-r<run_id>`，旧发布和旧工件不覆盖；定时任务看到已适配基础版仍直接跳过。`jiyu-latest` 只移动清单且清单始终引用不可变工件。`scripts/sub2api_jiyu_update_broker.sh` 不接受任何浏览器参数，只读取 root 管理的清单并调用 `stage-jiyu-build`。版本面板对 JIYU 构建始终显示“检查并安装”，代理按完整 `vX.Y.Z-jiyu.<run_id>` 比较；相同构建固定返回“已是最新”，不会下载或重启。应用进程保留 `NoNewPrivileges`，只允许通过 `/run/sub2api-jiyu-update.sock` 连接 systemd 按需启动的固定 root 代理；套接字仅 `root:sub2api` 可读写，服务端状态协议只接受 `noop`、`staged`、`error`，旧 sudoers 会在启用时删除。暂存时会另起独立 systemd 验证任务；管理员点击重启后，该任务核对正在运行的二进制哈希和 `/health`，失败自动恢复二进制、VERSION 与 PostgreSQL，10 分钟未重启也会撤销暂存。禁止恢复官方裸二进制更新路径。

所有会修改 Apache 配置的 JIYU 运维命令必须经 `reload_apache_with_recovery`：先运行 `apache2ctl configtest`，再 graceful reload 并最多 5 次复核 `https://jiyu.245334.xyz/health`；公网 TLS/健康失败时自动执行 full restart 并再次复核。`rollback-cutover` 使用旧服务的 `/api/status`，不能误用 Sub2API `/health`。不要直接运行 `systemctl reload apache2` 代替该入口。

### 生图与 MCP

- Sub2API 已原生提供 `POST /v1/images/generations` 和图片权限/计价能力，不需要另建一套公网生图网关。
- 两个上游生图入口已在用户侧匿名为 `JIYU 生图 · 渠道A`、`JIYU 生图 · 渠道B`，分别使用独立账号、分组、渠道和监控；两个分组开启生图权限和独立 1x 图片倍率。
- 本机已用 `scripts/install_jiyu_image_mcp.sh` 将两个失效 MCP 条目替换为 `JIYU AI 生图`，同步到 Claude、Codex 和 OpenCode；Key 只从 macOS 钥匙串服务“JIYU AI 生图 API Key”读取。新手步骤见 `docs/087-jiyu-image-mcp-guide.md`。
- 生图价格使用上游每张价格绝对增加 `$0.05`。渠道B高画质上游价为 `$0.07/次`，站内为 `$0.12/张`；渠道A请求返回 502、渠道B令牌返回 401，恢复前监控和健康记录必须保持真实异常，不执行连续付费重试。

### 链动小铺运营边界

- 店铺昵称、公告、头像和自定义链接已统一为 JIYU AI；¥1/10/50/100/300/500/1000 七档商品已建立并使用同一 JY Logo，标题、详情和兑换步骤已保存。
- 保证金账户已真实显示 ¥100；七档商品各导入 1 张既有兑换码并上架，七个公开页均显示“立即购买”。站内充值中心已回填七档链接；受管重建命令为 `ssh oracle-arm1 'sudo /usr/local/sbin/openclaw-sub2api-manager recharge-center'`。
- 仍未执行真实购买。首笔 ¥1 实单必须在操作当时再次确认，再按“付款 → 自动发货 → 兑换到账 → 创建密钥 → CC Switch 导入 → 用量查询”完成闭环；任一步失败立即下架并保留交易证据。
- Sub2API 支付与异步生图对象存储继续关闭：当前没有支付服务商回调/签名配置，也没有 JIYU 专用 S3 端点、存储桶和访问凭据。异步生图与备份共用 S3 客户端，但不得复用现有备份资源或为此擅自开通付费资源。

品牌名称异常时执行 `ssh oracle-arm1 '/usr/local/sbin/openclaw-sub2api-manager brand'`；邮件或文档图形 Logo 异常时执行 `ssh oracle-arm1 '/usr/local/sbin/openclaw-sub2api-manager brand-asset'`。选定的 2K JY 标志已上线，512×512 邮件资源由 `scripts/assets/jiyu-ai-logo-email.png` 固化，两个命令都带健康检查。

---

## 0.1 老板统一入口与一键排障

- 日常只收藏 `http://127.0.0.1:18800/dashboard`。该入口聚合首页总览、闲鱼售卖、每日简报、系统维护和帮助中心；红色/黄色状态旁边直接显示下一步。
- 技术支持报告：访问 `http://127.0.0.1:18800/export-status`，返回脱敏 JSON，不包含卡密、Token、买家昵称或 API Key。
- 当前买家号不可用时，访问 `/api/cc-simulation-gate`、`/api/cc-replacement-mode-test-pack` 或在 Dashboard 展开“替换模式模拟验收”；严格模拟门会逐步显示真实发卡、商品模板/重新上架、注册兑换、创建 API、导入 CC Switch、终端调用、渠道/服务器状态。它只用于闭环演练，`can_unlock_public_sale` 固定为 `false`，不替代 `xy_oid_*` 真实小额订单严格门。
- 本机健康检查：`scripts/auto_health_check.sh --json`，默认只读，最多等待 20 秒生产内测审计，避免健康检查卡死。
- 本机恢复预演：`scripts/auto_recovery.sh --dry-run`；确认后再去掉 `--dry-run`。恢复脚本会检查 LaunchAgent、卖家 Chrome/桥接器、旧日志和健康检查。
- 本机备份：`make backup-run`，默认写入 `~/.local/share/openclaw/backups`，包含恢复所需私有配置和 SQLite 在线快照，目录/文件固定 0700/0600；构建缓存、虚拟环境、node_modules、日志和旧备份不重复打包。
- 灾备恢复：`make backup-restore-drill` 会完整校验但不覆盖文件；真正恢复必须对 `scripts/disaster_recovery.sh` 显式加 `--confirm`。

### 每日自动备份与离机加密

```bash
make backup-schedule-status
make backup-run
make backup-restore-drill
```

- `ai.openclaw.daily-backup` 已安装并加载，默认每天 03:30 执行；每次只有在本机备份完成后才运行完整 restore drill，任一步失败都会让 LaunchAgent 退出非 0。
- `scripts/auto_health_check.sh --json` 同时检查任务最近退出码和 36 小时备份新鲜度。本轮实机生成 `openeverything-20260805-034824.tgz` 并通过 checksum、路径、内部 manifest 与 SQLite drill；文件名用于本次证据，日常以健康检查返回的最新文件为准。
- 本机备份防止误删、升级失败和软件损坏，但不能抵御整台硬盘损坏。离机目录必须和本机目录不同，并且只允许 GPG 密文：

```bash
export OPENCLAW_BACKUP_OFFSITE_DIR="/绝对路径/到独立同步盘/OpenClaw-encrypted"
export OPENCLAW_BACKUP_GPG_RECIPIENT="你的-GPG-公钥指纹"
make backup-schedule-install
make backup-run
```

- 只配置目录或只配置公钥都会失败关闭；离机目录只出现 `.tgz.gpg`、`.sha256`、`.ready`，不会出现明文 `.tgz`。恢复设备必须另行持有对应私钥，这是资产所有者凭据，不能写入仓库或由程序自动伪造。
- 卸载任务使用 `make backup-schedule-uninstall`，不会删除已有备份。修改时间、目录或公钥后重新运行 `make backup-schedule-install`，安装器会原子替换 plist 并验证加载状态。

### Intel Brief schema v4 实装记录（2026-08-05）

- 2026-08-04 08:30 的生产调度在投递阶段报 `sqlite3.OperationalError: no such column: event_key`；来源采集正常，根因是旧生产库已标记 schema v3，但旧 `content_delivery_attempts` 表没有随新建表定义增量迁移。
- 修复会在初始化时检查真实列结构，不相信版本号；旧表原子重建，按 `content_items.event_key` 保留历史投递身份，并把 `content_item_id` 改为可空以支持只有稳定事件键的记录。
- 真实库迁移前备份到 `~/.local/share/openclaw/migrations/intel_brief-before-v4-20260805-034441.db`，SHA-256 为 `db845bc5ce4e380086090eeef38bd5e27f54dbf89af3cb2d59e88cc496f036cf`；备份与迁移后数据库均 `PRAGMA quick_check=ok`，`user_version=4`、`event_key` 列存在。
- 正式 LaunchAgent 已重新加载，未手工 kickstart，避免在非计划时间提前发送真实 Telegram 简报。首次 08:30 自然运行前健康检查显示黄色“等待首次自然调度验证”；运行成功后会自动转绿。

### Release Gate 2.0 本机发布步骤

1. 在 `packages/clawbot/config/.env` 显式设置 `G4F_ENABLED`、`KIRO_GATEWAY_ENABLED`、`OLLAMA_ENABLED`、`IBKR_ENABLED`、`HEARTBEAT_SENDER_ENABLED`。未验收的能力保持 `false`；禁止用 LaunchAgent 已加载冒充服务可用。
2. 执行 `make ci-local`；必须同时通过 Python 双哈希锁、固定 Action SHA、ShellCheck、Gitleaks、npm/pip/RustSec、npm 完整性锁、Ruff、全量测试、总体覆盖率 `--cov-fail-under=40`、高风险模块聚合覆盖率 `--fail-under=80`、Frist、桌面合同、TypeScript、前端 lint/生产构建、Rust 和文档真实性治理。Linux CI 使用 `packages/clawbot/requirements-lock.txt`，macOS 本机使用 `packages/clawbot/requirements-lock-macos.txt`，两者都由 `make python-lock-check` 复算。
3. 执行 `scripts/auto_health_check.sh --json`；只有 `ok=true` 且 `release_ready=true` 才能继续。本机已安装但关闭的旧可选 LaunchAgent 应 `launchctl bootout` 后删除用户目录中的旧 plist，仓库模板保留供未来显式启用。
4. 桌面端只能执行 `make tauri-build`。该入口会先备份并清理 `/Applications/OpenEverything.app`、`OpenClaw.app`、`OpenClaw-Gateway.app`，失败恢复旧版；macOS 内测包按 Tauri 官方方式使用 `signingIdentity="-"`，构建产物与覆盖前临时安装副本都必须通过严格 `codesign`，成功后只保留 `/Applications/OpenClaw.app`。构建后执行 `make tauri-rollback-check`，确认上一版的 manifest、CDHash 和严格签名可用。这不是 Developer ID 签名或 Apple 公证，不能作为公开分发口径。
5. 重启 Bot/Gateway 后，以新日志窗口确认没有新增 G4F/Kiro 重启风暴、IBKR 拒绝连接或未关闭 HTTP session；再复跑健康检查。

### Frist-API Release Gate 2.0 部署边界

- 先备份 `/opt/frist-api/apps/frist-api`、`/etc/frist-api/frist-api.env`、Frist runtime、New-API SQLite 和 Apache 配置；备份校验成功后才替换源码。
- systemd 实际环境必须设置有限正整数 `FRIST_API_NEWAPI_DEFAULT_TOKEN_QUOTA`，单位为本地人民币分；例如 `7200` 表示单次最多划转 72 元，再换算为 New-API quota units。
- 生产 Token 1–9 当前都是 unlimited Token，继续由主域 New-API 原生用户额度体系承接；不得映射、禁用或迁移到 Frist owner 表。Frist 客户只创建新的有限 Key。
- 只重启 `frist-api.service`，不替换 New-API 二进制、不改变 Apache `jiyu.245334.xyz -> 127.0.0.1:13000` 主域拓扑。失败时恢复源码、环境和 runtime 备份并重启 Frist。
- 部署后同时验证 3180 Dashboard、13000 `/api/status`、公网站点、未授权 `/v1/models=401`、Frist 运营域和 `systemctl --failed`；任一失败立即回滚。

### Release Gate 2.0 实装记录（2026-08-03）

- 本机 Bot 与 Gateway 已从当前工作树重启；五个可选能力显式为 `false`，G4F/Kiro/heartbeat 三个历史失败 LaunchAgent 已从用户目录卸载，核心 18789/18790/18800 和 `scripts/auto_health_check.sh --json` 均为健康。重启后的 Bot 日志没有新增未关闭 session 或 IBKR 重连；Gateway 因 Weixin 上游首次连接约 230 秒后才 ready，部署门在此期间保持红色，恢复后 `/health` 为毫秒级 200。
- `/Applications` 只保留 `OpenClaw.app`；Bundle ID 为 `com.openclaw.manager`，arm64 App 的 ad-hoc sealed resources 通过 `codesign --verify --deep --strict`。真实 App 首屏已用 Computer Use 验收，窗口非空、连接状态正常、无控件重叠或凭据展示；本机临时证据截图为 `output/playwright/openclaw-app-deployed.png`，不纳入 Git 基线。
- Oracle Frist 发布前在 Node 18 的完整仓库 staging 跑过 `200/200`；生产备份为 `/opt/frist-api/backups/release-gate2-20260803T064021Z`，包含源码、root-only 环境、Frist runtime、SQLite 在线备份、Apache/systemd 配置和前后哈希。只重启 `frist-api.service` 后，3180/13000/两个公网入口均为 200，未授权 `/v1/models` 为 401，SQLite `quick_check=ok`，源码漂移/新增错误/新增 failed unit 均为 0。
- 生产 `FRIST_API_NEWAPI_DEFAULT_TOKEN_QUOTA=7200` 已生效；`newApiTokenOwners=0`，New-API Token 仍为 `9/9` 无限额度。ownership dry-run 已确认会拒绝无限 Token，本轮没有执行 `--apply`、禁用或迁移。

## 一、CC中转 / Frist-API 运营操作清单

# CC中转 / Frist-API 运营操作清单

> 日期: 2026-07-04
> 范围: 管理员首登、人工入账、支付接口、固定域名、邮箱、验证码、New-API 迁移和 R2 备份

## 当前可运营边界

CC中转当前沿用 Frist-API 内部服务名，处于生产环境内测，暂未正式售卖；已经能跑小范围真实验收: 用户注册登录、闲鱼已付款自动发货、用户兑换自动到账、管理员批量生成卡密、创建用户 Key、导出 Codex/OpenCode/Claude/OpenClaw/Hermes 配置，并通过 `/v1` 网关转发请求。

当前处于生产环境内测，暂未正式售卖；正式售卖前先按“内测卡密库存 + 闲鱼已付款自动发货 + CC中转站内核销”验收，商业化仍走闲鱼等外部交易平台 C2C 卡密销售。自动支付只作为未来备用能力，不是当前上线必需项。现阶段生产内测用户入口先使用现有 `245334.xyz` 的品牌子域名 `jiyu.245334.xyz`；运营入口使用 `frist-api-oracle.245334.xyz` 访问 Frist 自研兑换码/闲鱼自动发货助手；旧 `frist-api.245334.xyz` 只保留跳转和冷回滚排障。Cloudflare、R2/备份目标优先复用 `/Users/blackdj/Documents/VPS-Config` 中已治理的公共资产与配置模块，避免两套文档各说各话。

2026-07-07 最新内测口径：老板日常只收藏 2 个入口：`http://127.0.0.1:18800/` 本机操作台、`https://jiyu.245334.xyz/` 用户主站；`/ops-links` 只作为兼容状态页保留，不再默认加入 Chrome 书签。操作台负责确认闲鱼在线、绑定商品、暂停/恢复自动发货、处理补救队列和只读巡检。`GET/POST /api/cc-operator-mode` 可一键暂停/恢复自动发货；暂停只影响本机发货动作，不改卡密、不改订单、不改闲鱼商品。当前仍处于生产环境内测，正式售卖仍只差真实闲鱼小额付款同单严格门。

2026-07-07 追加：仓库内 Chrome 插件与本机卖家桥接器共同组成“CC中转发货助手”。如果闲鱼 WebSocket/订单接口漏掉真实已付款单，但本机已经生成 `manual_delivery_ready` 话术，桥接器会在卖家专用 Chromium 的已打开闲鱼页中检测“已付款/待发货”信号；命中后自动填入并发送已分配话术，然后本机自动标记 `message_sent`。桥接器同样负责确认发货和恢复可售队列：只有页面真的出现“去发货/无需物流/确认发货”或“已下架/已售罄 + 重新上架”按钮才点击。它不会重新分配卡密，不会自动砍价、批量私信、刷单或绕过平台风控。

2026-07-07 追加：新版 Chromium 对扩展访问 `127.0.0.1` 有 Local Network Access 限制，所以生产内测默认不再依赖“插件直接 fetch 本机接口”，而是由 `ai.openclaw.cc-seller-bridge` 本机 LaunchAgent 常驻接管。老板日常先运行 `make cc-seller-chrome` 打开卖家专用 Chromium，然后在该窗口登录闲鱼并保持打开；桥接器每 15 秒自动巡检已打开闲鱼页。操作台显示 `manifest_version=bridge`、`needs_refresh_for_global_watch=false` 就代表桥接器已接管。

| 模块 | 当前状态 | 生产要求 |
|------|------|------|
| 访问入口 | 生产内测入口 `https://jiyu.245334.xyz` 已接入 Cloudflare proxied A → Oracle ARM `150.136.73.15` → Apache/Origin CA → New-API `127.0.0.1:13000`，外网首页、登录页、注册页和 `/v1` 网关冒烟通过；旧 `frist-api.245334.xyz` 已 301 跳转到 CC中转主站；`frist-api-oracle.245334.xyz` 反代 Frist-API `127.0.0.1:3180`，作为兑换码与闲鱼自动发货助手运营台 | 后续若购买 `jiyu.gg` / `jiyu.cc`，按同一流程替换主域名；旧入口只做跳转/排障，冷回滚入口只有回滚时才启用 |
| 充值 | 当前不正式售卖；主路径为管理端生成内测兑换码、闲鱼已付款订单自动发货、用户端核销自动到账；站内烟测只读计划已上线但不会自动写生产数据；商户支付代码保留但当前不要求开通 | 平台售卖链接、自动发货规则、兑换码对账、库存告警和真实小额单严格门 |
| 价格 | 管理端可直接编辑套餐和模型价格 JSON | 正式售卖前人工确认价格；若未来恢复自动支付，再增加价格版本审计和生效审批 |
| 邮箱 | Frist-API 旧 SMTP 已复用到 New-API，`email_verification=true`；余额预警、注册验证码和找回密码 SMTP 邮件可共用同一套服务器环境配置 | 企业邮箱或稳定邮件服务商 + 发信监控 |
| 防刷 | New-API 原生 Turnstile 已复用 Frist 旧配置启用，公网注册/登录无 token 会被拦截；模型请求限流已开启，正式售卖前只需确认阈值适合当前套餐 | 若水平扩展再接 Redis/SQLite 限流 |
| 数据 | 生产 New-API 迁移已按授权执行：用户/余额/订单/兑换码/日志已迁入 Oracle 本机 New-API，历史 `enc:v1:` 用户 Key 因旧加密密钥缺失未伪造迁移；R2 定时备份已在 Oracle 启用，腾讯旧 timer 已禁用 | New-API 数据库 + VPS-Config 既有 R2/备份体系 |
| 管理员 | 一次性身份码 + 管理登录态 | 管理员 2FA + 审计 |
| 模型列表 | 客户可见模型只来自健康上游 `/v1/models` / 真实探测；内置目录仅做后台审计排序参考 | 定期审计上游真实模型和价格 |
| 上游来源 | 授权供应商余额站/自有额度为主；CPA JSON、chong 只作为人工审核备用渠道登记 | 禁止把批量 OAuth Session、来路不明 JSON 号源或规避风控的账号池默认当作生产库存 |

## Oracle 主生产部署摘要（旧 New-API 历史，禁止执行）

> 下面的旧 New-API/腾讯冷回滚段落是历史记录，不代表当前运行态。当前生产操作以本页顶部“干净 Sub2API 底座”段落和 `scripts/sub2api_oracle_manage.sh` 为准；旧数据、服务和回滚副本已按要求清理。

Frist-API 生产流量已从国内腾讯云迁到 Oracle ARM Always Free，目的是把公开客户网关放到资源更充沛、长期免费的海外实例上，同时降低国内共享服务器端口和资源耦合。腾讯云只保留冷回滚数据，不再承接正式流量。

| 项目 | 当前约定 |
|------|------|
| 主生产服务器 | Oracle ARM `150.136.73.15`（SSH alias: `oracle-arm1`） |
| 运行目录 | Oracle `/opt/frist-api` |
| Frist-API | `frist-api.service`，监听 `http://127.0.0.1:3180` |
| New-API | `openclaw-newapi.service`，监听 `http://127.0.0.1:13000`；使用 New-API v1.0.0-rc.4 ARM64 release 二进制，不在 Oracle 上安装 Docker |
| 公网入口 | 用户主站 `https://jiyu.245334.xyz` → Cloudflare proxied A → Oracle Apache 443/Origin CA → New-API `127.0.0.1:13000`；运营台 `https://frist-api-oracle.245334.xyz/admin.html` → Frist-API `127.0.0.1:3180`；旧 `https://frist-api.245334.xyz` 301 到 CC中转主站 |
| 备份 | `frist-api-r2-backup.timer` 在 Oracle active；Release Gate 2.0 回滚包为 `/opt/frist-api/backups/release-gate2-20260803T064021Z`，SQLite/源码/环境/runtime/Apache/systemd 和校验清单完整 |
| 冷回滚 | 腾讯云 `101.43.41.96:/opt/frist-api` 保留旧数据和备份，旧 `frist-api-server` / `openclaw-newapi` 容器已停止，旧 R2 timer 已禁用 |
| 运行数据 | Oracle 生产真实路径为 `/opt/frist-api/data/frist-api/runtime/runtime.json`，New-API 数据库为 `/opt/frist-api/data/newapi/one-api.db`；两者均只在服务器环境中保存，含用户 Key、上游 Key 和卡密密文，禁止提交 Git |
| 环境变量 | 只放服务器本机环境文件，禁止写入仓库；SMTP 密码必须无回显输入，不能放进命令历史；`FRIST_API_NEWAPI_DEFAULT_TOKEN_QUOTA=7200` 已用于新建有限 Key，`FRIST_API_NEWAPI_REDEMPTION_STATUS_SYNC_ENABLED=1` 用于把 New-API 原生兑换状态回写到 Frist 闲鱼履约 |

上线或重启后按下面顺序验收:

1. `ssh oracle-arm1 'systemctl is-active frist-api.service openclaw-newapi.service apache2 frist-api-r2-backup.timer'` 必须全部为 `active`。
2. `ssh oracle-arm1 'curl -sS -o /dev/null -w "%{http_code}" http://127.0.0.1:3180/api/frist/dashboard'` 应返回 `200`。
3. `ssh oracle-arm1 'curl -sS -o /dev/null -w "%{http_code}" http://127.0.0.1:13000/api/status'` 应返回 `200`。
4. 本机访问 `https://jiyu.245334.xyz/api/status` 应返回 `system_name=CC中转` 且 `hasCcSwitch=true`；未授权访问 `https://jiyu.245334.xyz/v1/models` 应返回 `401`；访问 `https://frist-api.245334.xyz/` 应 301 到 CC中转主站。
5. `ssh oracle-arm1 'systemctl --failed --no-pager'` 当前基线为 3 个与 Frist 无依赖的被动站单元：`oracle-resource-maintainer-standby`、`sonic-extract-failover-db-publish`、`sonic-oracle-db-backup`。发布门检查“没有新增 failed unit”，禁止用 `reset-failed` 抹掉基线；这 3 个单元归 SONIC EXTRACT/资源维护项目单独处理。
6. 旧腾讯云只做冷回滚；除非执行回滚，不要同时启动旧 Frist-API 和旧 R2 timer，避免双源探测、重复备份或上游渠道状态漂移。

### 多 VPS 故障转移方案（给老板的大白话版）

当前不是“没有备份服务器”，而是“主业务还没正式做一键切换”。现在用户真正访问的 CC中转在 Oracle ARM-1 `150.136.73.15`；`/Users/blackdj/Documents/VPS-Config` 里已经有 Oracle ARM-2 / Oracle 3055 `129.213.33.101`，并且它已经跑过多种 loopback-only 状态探针和温备脚本，适合做下一台备用机。

推荐先做 **主备温备**，不要一开始就做双活：

1. **主站**：Oracle ARM-1 `150.136.73.15`，继续承接 `https://jiyu.245334.xyz` 的真实用户流量。
2. **备站**：Oracle ARM-2 `129.213.33.101`，预装同版本 New-API、Frist-API、Apache、健康检查和备份恢复脚本，默认不接真实用户写入。
3. **数据**：`runtime.json`、New-API `one-api.db`、卡密密文、兑换/订单状态按 R2 备份 + 定时只读同步预热；故障切换前先冻结主站写入，避免两边同时卖同一张卡密。
4. **切入口**：优先使用 Cloudflare Load Balancer；如果暂时不买 LB，就用低 TTL DNS + 一键脚本把 `jiyu.245334.xyz` 从 ARM-1 切到 ARM-2。
5. **切换按钮**：18800 后续增加“故障切换到备用服务器”按钮，按钮内部做三步：健康检查 → 恢复最近备份 → Cloudflare 切流；老板不需要记 SSH 命令。
6. **回切**：ARM-1 修好后先把 ARM-2 的新数据备份回 R2，再恢复到 ARM-1，最后切回域名；禁止直接两边同时写。

为什么不做“双活同时卖”？CC中转有卡密、余额、订单、API Key 这类“只能扣一次”的数据，双活容易出现一张卡密发给两个人、余额不同步、订单状态打架。等温备切换稳定后，再考虑数据库层主从复制或托管数据库。

Telegram/微信每日简报的多端方案也按同一原则：**双入口单数据库**。用户可以同时用 Telegram 和微信，但订阅状态、推送时间、暂停状态、追踪名单只存一份；不做 Telegram 聊天和微信聊天的流式互传，避免两边菜单互相覆盖。

### 每日简报微信入口怎么验收

微信不像 Telegram 那样有可点击命令菜单，所以微信端使用数字编号。老板只要记住一句话：**看到菜单后回复数字即可**。

当前本机有三层：

1. **本项目处理器**：`POST http://127.0.0.1:18790/wechat/incoming`，输入 `700` 会返回每日简报菜单；兼容新路径 `/api/v1/wechat/incoming`。
2. **OpenClaw Weixin 插件桥**：授权微信会话发 `700-708`、`菜单`、`今日简报`、`我的订阅`、`推送时间`、`添加追踪` 等快捷词时，插件先调用本项目处理器并直接回微信，避免被普通 AI 聊天误答。
3. **真实微信通道**：`openclaw channels status --channel openclaw-weixin --probe` 应显示 `enabled, configured, running`。

本地只读验收命令：

```bash
cd packages/clawbot
.venv312/bin/python scripts/intel_wechat_user_journey_acceptance.py
```

看到 `verified=true` 表示微信编号菜单的“普通用户路径”已通过：打开菜单、今日简报、我的订阅、设置时间、添加追踪、暂停、恢复都能走通。这个脚本不调用真实微信网络，不会给任何联系人发消息。

真实微信验收方式：在微信里打开「Global Intelligence AI」或当前绑定的 ClawBot 会话，发送 `今日简报` 或 `700`。正常应回复“🧭 今日简报”以及 `700-708` 菜单。发送后运行：

```bash
cd packages/clawbot
.venv312/bin/python scripts/intel_wechat_bridge_runtime_acceptance.py
```

看到 `verified=true` 表示真实微信消息已经命中 OpenClaw Weixin 插件桥、本机 `/wechat/incoming` 返回 200、插件已把回复发回微信，并且没有落入普通 LLM 闲聊。该证据只保存脱敏 sender hash、快捷词类型、HTTP 状态和回复特征，不保存微信聊天原文、用户 ID 或 Token。如果脚本提示“未找到微信桥接证据文件”，说明还没有新的真实微信入站消息触发桥接。

如果希望 Codex/技术支持开着等你发微信，可以用等待模式：

```bash
cd packages/clawbot
.venv312/bin/python scripts/intel_wechat_bridge_runtime_acceptance.py --wait-seconds 120 --poll-seconds 2
```

你在 2 分钟内发 `今日简报` 或 `700` 即可；脚本会自动轮询，看到 `verified=true` 就算这一步过关。如果超时，会明确显示“等待 120 秒后仍未看到新的真实微信桥接成功证据”。

如果回复变成闲聊解释“700 是什么数字”，说明 OpenClaw 插件桥没生效，先执行：

```bash
openclaw gateway restart
openclaw channels status --channel openclaw-weixin --probe
```

如果仍失败，再看 OpenClaw 日志里是否有 `Intel Brief bridge failed`。

### Codex 能不能直接接管微信窗口

先跑这个只读诊断，不会发微信消息：

```bash
scripts/wechat_control_doctor.sh --json --deep
```

老板只看这 3 个字段：

| 字段 | 绿色含义 | 当前实机结果 |
|------|----------|--------------|
| `fullscreen_capture_ok` | 系统允许截图 | `1`，说明系统截图能力可用 |
| `window_capture_ok` | 微信窗口可以被单独截图 | `0`，微信拒绝被单窗口读取 |
| `ax_editable_count` | 辅助功能能找到微信输入框 | `0`，微信没有把聊天输入框暴露给 Codex |

如果看到 `status=blocked_by_wechat_capture_protection`，意思是：**Codex 不是完全没权限，而是微信窗口本身不让自动化工具看见聊天内容。** 这时不要让 Codex 坐标盲点发消息，避免误发到别的联系人或重复发卡。

可以先打开系统权限页补齐授权：

```bash
scripts/wechat_control_doctor.sh --open-permissions
```

手动确认：

1. **屏幕录制**：勾选 Codex、OpenAI/CUAService（如果列表里出现）、WeChat（微信）、Terminal/iTerm。
2. **辅助功能**：勾选 Codex。
3. **自动化**：允许 Codex 控制 System Events / WeChat。
4. 退出并重新打开 Codex 和微信，再重跑 `scripts/wechat_control_doctor.sh --json --deep`。

如果重跑后仍是 `blocked_by_wechat_capture_protection`，就不要继续折腾视觉接管；每日简报微信闭环改走 OpenClaw Weixin 插件桥证据：在微信里发 `今日简报` 或 `700`，再跑 `packages/clawbot/scripts/intel_wechat_bridge_runtime_acceptance.py` 验收。

### 运营入口怎么用（给老板收藏）

- 本机操作台：`http://127.0.0.1:18800/`。老板日常唯一控制面板：确认闲鱼在线、绑定商品、暂停/恢复自动发货、处理补救队列、运行只读巡检。
- 用户主站：`https://jiyu.245334.xyz/`。买家注册、登录、兑换、创建 API Key、导入 CC Switch 都从这里走。
- 兼容状态页：`http://127.0.0.1:18800/ops-links`。只读状态看板，保留给排障，不再默认收藏。
- 用户注册、登录、兑换、创建 API Key、查看用量：`https://jiyu.245334.xyz`。
- New-API 管理从用户主站登录后进 `/console`；旧 `https://jiyu.245334.xyz/admin.html` 已 302 到 `/console`，不要再收藏。
- `https://frist-api-oracle.245334.xyz/admin.html` 是 Frist 隐藏运营入口，普通打开返回 404 属于门禁伪装；不要当老板日常入口，也不要把入口码写进聊天、文档或命令历史。
- 卖家自动发货助手：先运行 `make cc-seller-chrome` 打开卖家专用 Chromium，再在这个窗口登录闲鱼并保持打开；本机 `ai.openclaw.cc-seller-bridge` 服务会每 15 秒巡检一次。需要手动确认运行态时执行 `node scripts/cc_zhongzhuan_seller_bridge.mjs --once --json`，看到 `ok=true` 且 `xianyuTabs>=1` 即可。
- 闲鱼当前主路径已切到合规全自动发货：OpenClaw `XianyuLive` 检测到订单状态“等待卖家发货/待发货/买家已付款/已支付”等已付款变体后（支持 `redReminder`、`statusText`、`tradeStatusText`、`payStatusText` 等订单结构化字段），调用 CC中转低权限 webhook 自动分配兑换码，并通过闲鱼消息发送返回的话术；`待付款/未付款/退款/交易关闭` 会被保护性排除，普通聊天文本不会作为付款状态扫描，避免误发卡；手工粘贴已付款订单只作为兜底。`XianyuLive` 会优先从订单结构字段或闲鱼 URL/query 参数提取商品 ID 用于 `item_id → planId` 套餐路由，找不到再回退最近聊天商品/默认套餐；同时会从字段或闲鱼 URL/query 参数提取真实订单/交易 ID 并生成稳定 `orderId`，同一订单重复推送或消息里时间戳变化时不会重复分配卡密；商品 ID 识别不扫描普通聊天文本，避免买家聊天复制链接时发错套餐；如果已经分配但闲鱼消息失败，只补发旧话术。砍价、批量私信、刷单、绕风控相关能力暂停并隐藏到高级区，不作为当前运营主线。


- 2026-07-07 追加方案 B 收口：卖家订单列表 API 当前仍可能返回 `PERMISSION_EXCEPTION::无权限访问`，所以不能把“自动运营”押在该接口上。新版本机卖家桥接器增加 `paid_page_dispatch`：当卖家专用 Chromium 中的真实买家聊天/订单页可见“已付款/待发货”且本机没有待发送话术时，桥接器会先调用本机 `/api/cc-manual-paid-order/dispatch` 生成话术，再注入页面填入并发送；该路径订单号为 `xy_browser_*`，适合生产内测自动补救，但正式售卖严格门仍只认卖家订单接口/WebSocket 真实订单脱敏后的 `xy_oid_*`。恢复上架也改为队列式：`/api/cc-xianyu-relist/next` 只返回已确认发货的记录，桥接器只有在商品页明确显示“已下架/已售罄 + 重新上架按钮”时才点击。
- 2026-07-07 追加：闲鱼卖家工作台/订单列表 API 当前会返回无权限，不能作为自动发货主通道。系统已补齐 WebSocket 明文付款系统卡片识别：如果闲鱼推送的系统标题是“我已付款，等待你发货/待发货/提醒发货”一类，会进入自动发货；普通买家聊天内容即使照抄这句话也不会触发。若已发生真实付款但系统没有自动发出，说明当前单可能进入 `manual_delivery_ready` 补救队列；此时打开卖家专用 Chromium 的买家聊天页并保持页面可见，桥接器会自动检测并发送。若桥接器仍识别不到已付款信号，才人工复制后点“已手动发送”。
- 漏单兜底：如果买家手机端已经显示“我已付款，等待你发货”，但本机 `messages/orders/cc_shipments` 没有新增，说明闲鱼 WebSocket 推送漏掉或助手重启期间错过事件。此时先在 `http://127.0.0.1:18800/` 操作台使用“已付款漏单兜底”生成话术，状态会变成 `manual_delivery_ready` 并进入补救队列；随后优先刷新 Chrome 插件并打开对应买家的闲鱼聊天页，用 Chrome 插件“CC中转发货助手”检测并发送待发货卡密，或在只有 1 条待发货时开启“看守所有闲鱼页”。插件会自动调用 `mark-sent`。如果插件没有识别到已付款/待发货信号，才手动复制到闲鱼聊天发送，再点“已手动发送”。未发送并标记前不算真实订单已发货。
- 自动发货话术已覆盖买家自助完整路径：注册/登录、兑换码到账、创建 API Key、进入 CC Switch 导入、选择模型测试；话术不包含上游信息，也不直接暴露 `/v1` 网关地址。

- 2026-07-07 开源轮子复核：`xianyu-auto-reply` 系列、`xianyu-super-butler`、`xianyu-auto-ship`、`autofishing` 等项目均确认有自动回复/卡券池、防重复、补发、确认发货能力；本项目不整套替换，只搬能力模式。后端真实订单号确认发货仍默认关闭，只有已成功发送兑换码、订单号是闲鱼真实数字订单号且显式开启时才调用；`xy_manual_*` / `xy_browser_*` 不计入正式售卖严格门。若旧内测单已经发了卡密但还没点闲鱼发货，走“当前页面补救确认发货”：老板打开对应闲鱼已付款/待发货页面并保持卖家 Chromium 可见，桥接器只有在页面可见“已付款/待发货/等待发货”信号时才点击“去发货/无需物流/确认发货”，没有付款信号就安全跳过。
- Frist-API 已启用 New-API 原生兑换状态回写：买家如果直接在 New-API 主站兑换卡密，后台会按卡密哈希把 Frist 卡密和闲鱼履约状态自动更新为 `redeemed`；也可在运营台通过 `/api/admin/redemption-cards/sync-newapi-status` 手动触发。
- 2026-07-05 生产已准备 5 张 `day|quotaUsd=30|source=xianyu` 内测可售卡密，并同步为 5 条 New-API 启用兑换码；无套餐/无 SKU 的已付款订单也已修复为“从任意未售卡密发货”，避免买家不聊天直接付款时漏单。
- 本机 Chrome 书签栏已写入并复验 `CC中转运营` 文件夹（`Default`、`Profile 1`、`Profile 2`、`Profile 3` 均有 2 个入口：本机操作台、用户主站；`scripts/cc_zhongzhuan_readiness_audit.mjs --json` 已显示 `chromeBookmarks.ok=true`）。如果 Chrome 没即时刷新书签栏，直接访问 `http://127.0.0.1:18800/` 即可操作。`/v1` 和 `/v1/models` 是程序接口，旧 `/admin.html` 是错误入口，不再放入老板标签页。
- 本机操作台：`http://127.0.0.1:18800/`。首页可直接打开，会提示输入 `packages/clawbot/config/.env` 里的 `OPENCLAW_API_TOKEN`；API 仍受 `X-API-Token` 保护。操作台已改为 Apple 风格深色状态面板，老板首屏只看 6 张状态卡：当前能不能卖、自动发货是否开着、库存是否够、上游余额是否够、是否有待处理订单、是否需要介入/是否有正式售卖资格。商品绑定、漏单兜底、补救队列、巡检和高级排障默认折叠；旧 `message_sent` 补救单如果待点闲鱼发货，会提示“打开已付款测试单页面”，不要求重新下单。

上架前安全锁只读刷新：

```bash
curl -H "X-API-Token: $OPENCLAW_API_TOKEN" "http://127.0.0.1:18800/api/cc-public-sale-lock?refresh=true"
```

该接口只读刷新库存、兑换码、渠道、买家入口、CC Switch 导入入口和本机自动发货状态，不分配卡密、不发闲鱼消息。 刷新后可看 `/ops-links` 或 GUI 的“当前行动建议”：它来自 `GET /api/cc-operator-next-action`，会先检查自动发货、补救队列和库存证据，再决定是否提示跑真实小额单；不会因为服务刚重启、库存证据为空就误提示上架。 如果后续要接通知或外部看板，优先读取 `GET /api/cc-ops-snapshot`，它一次性返回行动建议、上架锁、自动发货、实单闭环、买家进度、`auto_strict_audit_status` 和 `buyer_site_smoke`，仍然是只读。`auto_strict_audit_status.state=waiting_paid_order` 表示严格门自动观察已开启但正在等待真实付款；`armed` 表示真实订单已发货，后台会自动观察兑换/API Key/调模型严格门。`buyer_site_smoke` 是最近一次只读巡检里的站内买家烟测计数：`redeemed_delta / active_token_delta / model_log_delta`，只证明站内链路活动，不替代真实闲鱼同单严格门。真实小额单验收时可读取 `GET /api/cc-real-order-test-pack`，它会在证据缺失时只读刷新一次库存/渠道/入口状态，并返回可复制测试商品模板和逐步验收状态。 本机后台提醒读取同一份快照，状态变化时通过 macOS 通知提醒，不单独产生新的业务状态源。

一键闭环审计（默认只读，不打印 token、卡密或用户 Key）：

```bash
node scripts/cc_zhongzhuan_readiness_audit.mjs
```

该命令会检查 Chrome 书签、本机闲鱼 LaunchAgent、本机 `.env`、本机闲鱼 GUI、Oracle 服务/库存和公网安全门。本机闲鱼 GUI 必须满足：首页可打开、API 无 token 为 401、带 token 为 200、WebSocket 已连接、Cookie 正常、CC自动发货已配置、补救待处理为 0；如果出现 `message_send_failed`，本机后台会优先自动补发同一条已分配话术，不会重新分配卡密；如果出现 `manual_delivery_ready`，优先打开卖家专用 Chromium 的对应买家聊天页，让本机桥接器发送并标记。2026-07-06 当前只读巡检因真实测试单 `pending_rescue=1` 仍为 `ok=false`，这是正确阻断，不代表 Oracle/New-API 坏；正式售卖仍等待真实小额单严格门。

Chrome 运营入口修复（看不到书签文件夹时使用）：

```bash
node scripts/cc_zhongzhuan_chrome_bookmarks.mjs
```

修复后再跑 `node scripts/cc_zhongzhuan_readiness_audit.mjs`，确认 `chromeBookmarks: PASS`。

带生产 webhook 冒烟（会临时分配 1 张卡密，随后清理履约并恢复库存）：

```bash
node scripts/cc_zhongzhuan_readiness_audit.mjs --webhook-smoke
```

2026-07-05 复验结果：只读模式和 webhook 冒烟模式均 `PASS`；冒烟返回 `fulfillment=delivered`、`cleanup=true`、`unused_after=5`；默认审计显示同一真实订单闭环为 `localOrderHashes=0, matchedOrders=0, readyOrders=0（默认不强制）`。

正式开卖前真实闲鱼实单 + 买家站内闭环验收（只有发布商品并跑过 1 单小额真实付款，且买家完成兑换、创建 API Key、调模型后才应通过）：

```bash
node scripts/cc_zhongzhuan_readiness_audit.mjs --require-real-order
```

这个严格模式会读取两类证据：

1. 本机闲鱼助手 `cc_shipments`：正式售卖严格门只接受由 `XianyuLive`/卖家订单接口真实检测到已付款订单后产生的 `xy_oid_* / message_sent` 自动发货记录；`xy_manual_*`、`xy_browser_*` 和生产 webhook 冒烟不再算作真实自动订单证明。
2. Oracle 生产 New-API 数据库 + Frist runtime：用本机 `xy_oid_*` 订单哈希匹配同一笔闲鱼履约，要求该订单对应卡密已兑换、履约已回写 `redeemed`、兑换用户有启用 API Key，且兑换后有模型调用日志。

当前未发布商品时该命令预期失败，失败不代表系统坏，而是提醒“还没做外部平台实单 + 买家站内闭环验证”。

如果不想敲命令，也可以打开 `http://127.0.0.1:18800/`，在“一键闭环审计”里点击“运行内测巡检”或“运行正式售卖严格门”。这两个按钮只运行只读审计；生产 webhook 冒烟仍必须由开发/运维在终端显式执行，避免误点。真实小额订单发生后，审计卡片会显示同一订单的分阶段状态：已发货、卡密已兑换、New-API 已兑换、API Key 数量、兑换后模型调用数和“闭环完成/继续观察”。注意：GUI 的“正式售卖”状态只有在最近一次严格门通过且同一真实订单完成买家兑换、创建 API Key、调模型后才会转绿；仅出现已发货记录不会放行正式售卖。

本机闲鱼助手后台还会默认每 15 分钟运行一次只读“内测巡检”，自动刷新上架锁里的未售卡密库存、New-API 启用兑换码和启用渠道数量；这个线程随 `ai.openclaw.xianyu` 启动，不要求浏览器一直打开。它只运行 `read_only` 审计，不调用 `--webhook-smoke`，不会发送闲鱼消息、分配卡密或修改库存。对应开关是 `CC_XIANYU_AUTO_READINESS_AUDIT_ENABLED`，间隔为 `CC_XIANYU_AUTO_READINESS_AUDIT_INTERVAL_MS`，扫描频率为 `CC_XIANYU_AUTO_READINESS_AUDIT_SCAN_SECONDS`。

GUI 和后台现在都会做安全的自动观察：当“实单闭环观察”显示“已自动发货，等待买家完成兑换/API/调模型”时，页面和后台守护线程都会按 10 分钟节流自动运行一次“正式售卖严格门”只读审计。后台线程随 `ai.openclaw.xianyu` 启动，不要求浏览器一直打开；它不会调用 `--webhook-smoke`，不会重新发货，不会分配新卡密，不会改库存；只是把“买家是否已经完成兑换、创建 API Key、调模型”的证据刷新到缓存和 GUI。没有真实订单、存在补救队列或自动发货未就绪时不会自动跑严格门。 严格门结果会以脱敏摘要写入本机 SQLite 的 `cc_strict_audits` 表，保留订单前缀/哈希、履约状态、兑换状态、API Key 数量、模型调用数和 ready 标记，不保存卡密、Token 或 API Key；所以真实订单闭环通过后，即使闲鱼助手重启，GUI 也能恢复最近一次严格门结果和买家进度。 严格门通过后，还会按订单哈希把本机 `cc_shipments` 对应记录标记为 `buyer_chain_status=verified`，因此发货/补救列表能区分“已发送兑换码”和“买家已经完成兑换、API Key、调模型闭环”；该回写不保存完整订单号到审计摘要。

本机闲鱼助手后台还会默认启动“运营提醒”线程，不要求浏览器一直打开。它每 30 秒检查一次运营快照，状态真正变化且超过 120 秒节流时，会通过 macOS 通知提醒 WebSocket/Cookie 异常、补救队列、低库存、等待真实小额单、买家链路卡点或正式售卖严格门通过。真实订单发货后，提醒会优先告诉你买家卡在哪一步：等待严格门、未兑换、未创建 API Key、未调模型、同单待确认或已闭环；该提醒优先级高于低库存，避免真单发生后只看到库存提醒。提醒只读，不自动催买家、不批量私信、不触发审计、不发货、不分配卡密、不改库存；手动发送当前状态提醒可在 `/ops-links` 的“本机提醒”卡片点击，也可调用：

```bash
curl -X POST -H "X-API-Token: $OPENCLAW_API_TOKEN" "http://127.0.0.1:18800/api/cc-ops-notify/check?force=true"
```

相关开关：`CC_XIANYU_OPS_NOTIFY_ENABLED`、`CC_XIANYU_OPS_NOTIFY_INTERVAL_MS`、`CC_XIANYU_OPS_NOTIFY_SCAN_SECONDS`、`CC_XIANYU_LOW_INVENTORY_THRESHOLD`。

闲鱼商品发布前建议顺序：
1. 打开状态中心确认补救队列为 0、库存和渠道正常，再打开操作台确认“自动发货”不是暂停。
2. 在“闲鱼商品模板”生成极简模板，复制到闲鱼商品详情；模板只写付款后自动发卡和买家自助使用步骤，不加额外营销话术。
3. 商品发布后，把闲鱼商品链接或商品 ID 填进操作台“商品绑定”，补上对应 `planId` 并保存；多商品正式上架前必须绑定，避免错发套餐。当前只有一个商品时，本机助手仍有默认套餐兜底，但操作台会明确提示“商品绑定 0”。 支持直接粘贴完整闲鱼分享文本、短链接本体或 `短链接 CZ007` 格式，后台会统一匹配同一商品绑定。
4. 如果临时不想卖，先在操作台点“暂停自动发货”，再去闲鱼下架商品；恢复时先确认库存，再上架闲鱼，再点“恢复自动发货”。
5. 用真实小额订单跑一次“付款 → 自动发卡 → 买家兑换 → 创建 API Key → CC Switch 导入 → 调模型”，再点“运行正式售卖严格门”或等待后台严格门自动观察。

如果真实订单已经在手机闲鱼里显示“我已付款，等待你发货”，但本机状态中心出现补救队列，则走浏览器兜底：先在 Chrome 里打开对应买家的闲鱼聊天页，确认页面能看到“已付款/待发货/等待你发货/记得及时发货”等提示；刷新已安装的 OpenEverything Social Pilot 插件后，打开插件的“CC中转发货助手”，可选择“检测当前聊天”做只读预检，也可点“看守当前聊天页”。看守模式会锁定当前聊天标签页，每 30 秒检查一次；只有页面可见付款信号、找到输入框且本机有 `manual_delivery_ready` 话术时才自动发送，成功一次后自动关闭。本机状态中心/操作台在这种状态下也会把下一步写成“打开聊天页 + 插件检测/看守发送”，不要再等待闲鱼订单 API 自动补发。手机分享短链 `m.tb.cn` 已纳入插件权限，但因为 Chrome manifest 改过，首次使用前需要在 `chrome://extensions` 点一次插件刷新。不要同时开启多个聊天页看守；多笔订单并发时，先清空补救队列再继续上架。


SMTP 密码已通过隐藏输入方式写入 Oracle 环境变量，并已用 Gmail 465/TLS 跑通生产测试邮件；2026-07-05 已把同一套 SMTP 配置复用到 New-API 原生邮箱验证。New-API 数据库、R2 备份和 Cloudflare DNS 代码侧已落地。生产内测当前走人工发放内测兑换码，不把微信/支付宝/Stripe 商户自动支付作为上线必备。

## 你需要人工开通的服务

| 优先级 | 服务 | 你要准备的字段 | 我接入后的接口 |
|------|------|------|------|
| P0 | 域名和 Cloudflare / 免费 DNS | 已用现有 `245334.xyz` 区域开通 `jiyu.245334.xyz` 并指向 Oracle `150.136.73.15`；`frist-api.245334.xyz` 仅保留跳转排障 | `https://jiyu.245334.xyz/` 和 `https://jiyu.245334.xyz/v1` 作为当前用户入口；nip.io 只作为历史/冷回滚排障，不再对用户宣称兜底 |
| P0 | 兑换码内测/未来售卖平台 | 内测卡密批次、未来闲鱼商品/SKU、自动发货规则、兑换码库存和对账表 | CC中转 `#redeem` 核销；内测期不需要自动支付商户资质 |
| P0 | 备份目标 | 已复用 VPS-Config 既有 R2/对象存储备份资产；密钥只在服务器环境文件和私有凭据仓，未写入仓库 | 每日 R2 timer 已启用，最近一次手动上传返回 HTTP 200 |
| P1 | SMTP 邮箱 | 主机、端口、用户名、应用密码、发件邮箱；Gmail 只作为短期测试，密码只能写服务器环境变量 | Frist-API 与 New-API 已共用，New-API `email_verification=true` |
| P1 | Turnstile | 复用 VPS-Config / Cloudflare 账号申请的 Site Key、Secret Key、允许域名；Secret 只进服务器环境变量 | New-API `turnstile_check=true`，注册/登录无 token 已被拦截 |
| P1 | 告警 Webhook | Telegram、企业微信、飞书或 OpenClaw 通知地址 | 低库存、5xx、支付失败、异常扣费告警 |
| P2 | 合规文档 | 服务条款、退款规则、隐私政策、AGPL 源码入口 | 页面页脚和订单确认页展示 |

不要把 API Key、Webhook Secret、商户密钥、SMTP 密码或服务器密码发到聊天里。SMTP 密码即使用户在聊天里给过，也不能由 Codex 写进命令历史或最终报告；本轮已通过本机隐藏输入框写入 Oracle `/etc/frist-api/frist-api.env`，文档只记录状态不记录值。`/opt/frist-api/.env` 是历史兼容文件，不是当前 `frist-api.service` 的 `EnvironmentFile`，以后不要只更新该兼容文件。

## 备用渠道人工风控

CPA JSON、chong 和其他备用来源只能作为应急库存入口，不作为默认生产库存。管理端已经把这些来源和授权/自有来源分开，目的是让你人工记录风险判断，而不是自动接管账号或批量刷新 OAuth。

操作规则:

1. 优先选择 `授权供应商 / 自有额度`。只有主库存不足或需要应急验证时，才选择 `CPA JSON 备用渠道`、`chong 备用渠道` 或 `其他人工备用渠道`。
2. 备用渠道首次写入时，`风险状态` 保持 `待人工核验，先隔离`。隔离库存会保存到管理端，但不会出现在 `/v1/models`，也不会被用户广场或 API 网关调用。
3. 人工核验至少确认四项: 来源责任人、是否有可转售/转接授权、可用范围、异常时谁负责下架和赔付。
4. 四项都确认后，才能把 `风险状态` 改为 `已人工核验，可路由`，并勾选 `备用渠道已完成合规与风险判断，允许进入路由`。
5. 发现异常、投诉、上游封禁、价格不明或来源说不清时，立刻把风险状态改为 `禁止路由`，再刷新库存确认状态不是 `可用`。
6. `Key 列表` 可以粘贴普通逐行 Key，也可以粘贴 JSON 数组；JSON 只用于人工导入已合规确认的 API 兼容凭证，不用于提取 OAuth Session、刷新 Refresh Token 或绕过平台风控。
7. 用户端永远不展示 `CPA JSON`、`chong`、风险备注、上游地址或号商细节；这些字段只留在管理端审计。

判断能不能放行只看一句话: 你能明确说明来源合法、责任人明确、额度可转售、异常能下架。任何一项说不清，就保持隔离。

## 授权余额站上游接入

余额站模式和旧的零散 API + 端点模式不同: 管理员只需要录入供应商的 OpenAI 兼容根地址、授权 Key、模型清单和额度，真实消耗由供应商站内余额扣减。

操作规则:

1. 渠道类型选择 `授权供应商 / 自有额度`，不要把已购买的余额站 Key 标成 CPA JSON 或 chong 备用渠道。
2. 请求地址可以填供应商根地址，也可以直接填 `/v1` 地址。若根地址返回网站 Dashboard 的 HTML 壳，Frist-API 会先拒绝这个 2xx 非 JSON 响应，再自动尝试同域 `/v1`。
3. 严格探测会校验 Chat Completions、Responses、Images 返回体是否是对应 OpenAI 兼容 JSON；网页、余额页、登录页或错误页都不会写成健康库存。
4. `模型` 建议只填实际购买分组明确支持的模型，例如 `gpt-5.5`、`gpt-image-2`，不要把供应商未列出的模型手工扩进去。
5. `额度` 按人民币分写入运行库存。若按美元额度购买，先用当前运营汇率折算成人民币，再乘以 100 写入 cents。
6. 补号后先用管理端库存状态确认 `lastProbeStatus` 是 `chat_probe_ok`、`responses_probe_ok` 或 `image_probe_ok`，再到用户广场做 `gpt-5.5` 和 `gpt-image-2` 真请求。
7. 如果供应商返回 `API key is disabled`、余额不足、登录页或非 JSON 响应，保持库存 failed/exhausted，不要手工改回 healthy。

判断能不能上线只看两条证据: `/v1/models` 能看到目标模型，广场真实请求能返回文本或图片。只看到供应商 Dashboard 余额页不算 API 连通。

## ChatGPT Plus 自用账号台账

Frist-API 管理端现在可以登记自用 ChatGPT Plus 账号资产，但它和 API 库存是两套系统。Plus 台账只用于提醒到期、记录 Apple 余额、设备/Profile 隔离和风险状态；不会被用户 `/v1` 网关调用，也不会自动登录或导出密码。

操作规则:

1. 只登记本人自用账号。账号状态要如实选择 `养号中`、`Plus 可用`、`待续费`、`暂停`、`风险冻结` 或 `退役`。
2. 合规状态默认 `待核验`；只有确认“仅自用，禁止共享/转售”后，才能把账号设为 `Plus 可用`。
3. `续费日期`、`Apple 余额 TRY`、`月费 TRY` 用来做运营提醒，不代表系统会代充或自动扣费。
4. `设备 / 浏览器隔离` 只记录你人工使用哪个 iPhone、Mac 或浏览器 Profile，避免混淆登录环境。
5. `密码备注` 会写入 runtime 敏感字段并在启用 `FRIST_API_DATA_ENCRYPTION_KEY` 时加密；接口和管理列表只返回“已保存”状态，不返回明文。
6. 不要把 Plus 账号当作 Frist-API 可售库存，不要把账号借给用户，不要做自动轮换规避平台限额。要对外提供 API 服务时，仍使用授权余额站、自有 API 额度或已经人工核验可路由的上游 Key。

一句话判断: Plus 台账是“自用订阅资产管家”，不是“用户网关库存”。

## RT JSON 导入台账

管理端新增 RT JSON/TXT 导入，只用于把已经合规取得的 Refresh Token 做后台台账和后续刷新准备；它是在 New-API 原有通道、Key、日志、钱包、用户管理、补号、价格、卡密和审计入口之外的新增能力，不替换也不减少原管理侧。

支持三种输入:

1. JSON 数组: `[{"refresh_token":"rt_xxx","email":"user@example.com","account_id":"acct_xxx"}]`
2. 单个 JSON 对象: `{"refresh_token":"rt_xxx","email":"user@example.com"}`
3. TXT 每行: `rt_xxx,user@example.com,acct_xxx`

安全边界:

1. `refresh_token` 原文只写入 runtime 敏感字段；启用 `FRIST_API_DATA_ENCRYPTION_KEY` 时会加密落盘。
2. 管理接口只返回脱敏邮箱、账号 ID 尾号、RT 预览和指纹，不返回原始 RT。
3. RT 台账不会进入 `credentials` 可售库存，不参与用户 `/v1` 路由，不自动绕过平台风控。
4. 来源、平台、账号类型和备注必须写清楚，后续人工复核时按来源批次追踪。

一句话判断: RT 导入是“登录凭证保险柜和刷新准备表”，不是“马上可售的 API 号源”。

## 管理员首登

推荐走一次性管理员身份码，不要把账号密码发给开发者。

1. 打开 CC中转用户端，按普通用户流程注册和登录。
2. 先完成一次用户链路测试: 创建 Key、选择模型分组、生成 CC Switch 导入链接。
3. 回到右上角账户菜单，在身份码输入框粘贴一次性管理员身份码。
4. 点击激活。成功后当前账号变成管理员，身份码立即作废。
5. 账户菜单会显示运营入口。点击后进入独立管理页，同一浏览器登录态可直接加载库存和充值单。
6. 管理页里的管理员令牌输入框是后备方式，正常可以留空。

如果身份码输错，页面会提示身份码无效；如果已经使用过，会提示身份码已失效。需要新码时，只在服务器环境变量 `FRIST_API_ADMIN_CLAIM_CODES` 追加新的一次性码，然后重启 Frist-API 容器。

## 生产内测验收方式

当前最稳的验收方式是生产环境内测，暂未正式售卖；先由管理员人工生成内测兑换码，再由用户端自动核销。

1. 管理员进入运营入口，在“卡密生成与闲鱼发货”里选择套餐和数量，生成一次性兑换码。
2. 复制本批卡密清单，保存到内测发放清单，未来可导入闲鱼自动发货或客服系统。
3. 内测用户拿到人工发放的卡密；正式售卖后再由外部交易平台完成收款、售后和自动发货。
4. 用户回到 CC中转的兑换码页面输入卡密。
5. 系统校验卡密未使用后立即到账，并把卡密标记为已兑换。

这种方式不需要商户支付资质，也不需要用户上传付款截图，适合正式售卖前先验证全链路。

人工入账只作为异常兜底。正常订单以兑换码核销记录为准，至少保留: 卡密批次、闲鱼订单号、卡密、套餐、售出平台、核销用户和核销时间。

### 闲鱼兑换码内测/未来售卖

内测期先把每个套餐作为后台卡密批次；正式售卖后，再把每个套餐作为一个闲鱼商品或 SKU，自动发货内容只放一条兑换码。

1. 在管理端生成本批卡密，复制 `卡密 + 套餐 + 额度 + 时限` 文本。
2. 将卡密导入闲鱼自动发货库或 OpenClaw 闲鱼客服系统。
3. 内测用户收到人工发放卡密后，回 CC中转 `#redeem` 页面兑换。
4. 兑换成功后，卡密状态变成 `redeemed`，不能再次使用。
5. 售后退款时，先查卡密是否已核销；已核销则按平台规则处理，未核销可在后续后台停用。

用户端的闲鱼购买链接当前是占位，等商品发布后把链接配置进去即可。

## 价格管理系统

管理端已经有价格管理区，位置在 `运营入口 -> 套餐与模型计价`。这里不是写死在代码里的价格表，适合上游价格变化时快速调整。

1. 打开管理端，输入管理员令牌或使用已激活管理员账号进入。
2. 找到 `套餐与模型计价`。
3. `充值套餐 JSON` 维护用户看到的套餐: `id`、`label`、`quotaUsd`、`priceCny`、`durationDays`、`plan`。
4. `模型官方价格 JSON` 维护扣费价格: `model`、`inputCostCnyPerMillion`、`outputCostCnyPerMillion`、`inputSaleCnyPerMillion`、`outputSaleCnyPerMillion`。
5. 当前策略是模型计价按官方成本价走，充值套餐做折扣；所以默认 `inputSaleCnyPerMillion` 等于 `inputCostCnyPerMillion`，`outputSaleCnyPerMillion` 等于 `outputCostCnyPerMillion`。
6. 修改后点 `保存价格`，用户端刷新后会看到新套餐；网关扣费会按新的模型价格执行。
7. 每次改价前先复制一份旧 JSON 到本地对账表，记录改价时间、改价原因和操作人，避免后续退款或争议查不到依据。

当前默认套餐:

| 套餐 | 用户售价 | 入账额度 | 时效 |
|------|------:|------:|------|
| Codex API 30刀额度/日卡 | 5.88 元 | 30 美元额度 | 1 天 |
| Codex API 30刀额度/不限时 | 8.88 元 | 30 美元额度 | 不限时 |
| Codex API 100刀额度/不限时 | 28.88 元 | 100 美元额度 | 不限时 |
| Codex API 500刀额度/不限时 | 68.88 元 | 500 美元额度 | 不限时 |
| Codex API 1000刀额度/不限时 | 118.88 元 | 1000 美元额度 | 不限时 |

## 测试账号加 60 刀日卡额度

当前系统内部余额字段是人民币额度，美元额度按 `1 USD = 7.2 CNY` 折算。因此 60 刀额度对应 `432 元` 账户额度。

管理员后台入账时这样填:

1. `用户邮箱`: 测试账号邮箱。
2. `金额`: `432`。
3. `套餐`: `日卡`。
4. `备注/方式`: `manual_test_60_usd_day_card`。
5. 入账成功后，用户侧应显示 `日卡`、`套餐额度 ¥432.00`，到期日为入账后 1 天。

这个动作只用于测试额度，不代表真实收款已经发生。真实运营时必须先看到支付到账，再做人工入账。

如果历史测试账号已经有一部分日卡额度，只补差额即可。例如已有 `¥48.00`，本次补到 60 刀只需要再入账 `¥384.00`，补完后总额度是 `¥432.00`。

## 自动支付备用说明（当前不推进）

当前处于生产环境内测，暂未正式售卖；正式收款主路径未来才会切到外部交易平台 C2C 卡密销售，再由 CC中转 `#redeem` 页面自动核销。微信支付、支付宝、Stripe 或聚合支付只作为未来备用能力；本阶段不要求开户注册、不要求支付回调上线，也不要为了“看起来完整”伪造支付成功。

如果以后决定恢复自动支付，仍必须先由账号所有者在对应平台完成主体实名、商户号、应用 AppID、签名密钥、公钥、回调域名、订单号规则和退款规则配置。不要把密钥发到聊天里，写入服务器环境文件后再接代码。

### 支付宝当面付

支付宝当面付适合“用户扫码付款后自动入账”的国内小额充值场景。你需要在支付宝开放平台完成商户入驻和产品开通。

你要人工完成:

1. 打开支付宝开放平台，用企业或个体工商户主体注册账号，并完成实名资料。
2. 进入控制台，创建一个网页/扫码支付应用。
3. 在产品能力里申请 `当面付`。如果后台要求经营类目、客服电话、营业执照，按实际主体资料填写。
4. 应用创建成功后，记录 `AppID`、支付宝网关地址和应用名称。
5. 在开发设置里生成密钥。推荐用支付宝密钥工具生成应用私钥和应用公钥。
6. 把应用公钥上传到支付宝开放平台，下载或复制支付宝平台公钥。
7. 在应用里配置异步通知地址，建议预留为 `https://你的域名/api/frist/payments/alipay/notify`。
8. 确认签名算法是 `RSA2`，字符集是 `utf-8`，金额单位是元，订单号不要超过支付宝限制。
9. 在服务器 `/opt/frist-api/.env.production` 写入 AppID、商户号、应用私钥、支付宝平台公钥和回调地址。
10. 重启 Frist-API 后，用支付宝沙箱或 0.01 元订单测试: 下单生成二维码、扫码付款、收到回调、用户自动入账、重复回调不会重复加钱。

我接入时会做三件事: 创建支付订单并返回二维码，校验支付宝异步通知签名，按订单号幂等入账，避免重复通知重复加钱。

当前代码已接入: `alipay.trade.precreate` 下单、下单响应 `sign` 验签、`RSA2` 异步通知验签、`TRADE_SUCCESS` / `TRADE_FINISHED` 幂等入账。下单响应缺签名或验签失败固定返回 502；商户未开户注册前，页面会提示接口未配置，不会伪造自动支付成功。

官方入口:

- 支付宝开放平台: https://open.alipay.com/
- 支付宝当面付 / `alipay.trade.precreate`: https://opendocs.alipay.com/open/f540afd8_alipay.trade.precreate

### 微信支付 Native

微信支付 Native 适合桌面网页扫码支付。它需要微信商户平台审核，通常比个人收款码多一步主体资质。

你要人工完成:

1. 打开微信支付商户平台，注册商户号，完成主体实名、经营类目和结算账户审核。
2. 准备一个公众号、小程序或 AppID，并在商户平台完成绑定。没有 AppID 时先不要写代码，先确认后台允许哪种产品形态。
3. 在产品中心开通 `Native 支付`。
4. 进入账户中心，记录 `商户号`、`AppID`、`商户 API 证书序列号`。
5. 设置 `APIv3 密钥`，下载商户证书、商户私钥和微信支付平台公钥，并记录平台证书序列号或支付公钥 ID。
6. 配置异步通知地址，建议预留为 `https://你的域名/api/frist/payments/wechat/notify`。
7. 确认微信回调是加密资源，需要用 APIv3 密钥解密；订单金额单位是分，不是元。
8. 把证书、私钥和 APIv3 密钥放到服务器安全路径，例如 `/opt/frist-api/secrets/wechat/`，权限设为只有 root 可读。
9. 在 `/opt/frist-api/.env.production` 写入商户号、AppID、商户证书序列号、平台序列号、平台公钥、商户私钥、APIv3 密钥和回调地址。
10. 重启 Frist-API 后，用 0.01 元订单测试: 下单生成 Native 二维码、微信扫码付款、收到回调、用户自动入账、重复回调不会重复加钱。

当前代码已接入: 微信支付 Native 下单、下单原始响应的时间戳/nonce/平台序列号/RSA-SHA256 验签、APIv3 回调验签、AES-256-GCM 资源解密、`SUCCESS` 幂等入账。下单响应缺签名、超过 5 分钟、序列号不符或验签失败固定返回 502；商户未开户注册前，页面会提示接口未配置，不会伪造自动支付成功。

官方入口:

- 微信支付商户平台: https://pay.weixin.qq.com/
- 微信支付 Native 下单: https://pay.wechatpay.cn/doc/v3/merchant/4012791877

### Stripe

Stripe 的 API Secret Key、Webhook Signing Secret 和账号实名审核只能由你在 Stripe 后台完成。官方文档说明 API Key 在 Dashboard 管理，测试 key 以 `sk_test_` 开头，正式 key 以 `sk_live_` 开头；Webhook 正式模式需要 HTTPS 和有效证书，且只支持 TLS 1.2/1.3。

操作步骤:

1. 登录 Stripe Dashboard，完成账号激活和收款主体资料。
2. 进入 Developers / API keys，先复制测试模式 `sk_test_...`，正式上线前再切换 `sk_live_...`。
3. 进入 Developers / Webhooks，新增 Endpoint。
4. 正式域名准备好后，Webhook URL 建议预留为 `https://你的域名/api/frist/payments/stripe/webhook`。
5. 勾选支付成功、支付失败、退款相关事件。第一版至少需要支付成功事件。
6. 复制 Webhook Signing Secret，形如 `whsec_...`。
7. 不要把这些密钥发在聊天里；建议写进服务器本机 `.env.production`，再让我接自动回调代码。

第一版自动支付只接一个成功事件和一个失败事件就够了，先保证付款后能自动入账、重复回调不会重复加钱、订单金额和用户选择套餐一致。退款、促销码和订阅续费放到第二阶段。

参考官方文档:

- Stripe API keys: https://docs.stripe.com/keys
- Stripe Webhooks: https://docs.stripe.com/webhooks

### 易支付或其他国内聚合支付

国内聚合支付平台差异很大，但通常都需要你在商户后台拿到这些字段:

- 网关地址
- 商户 ID / PID
- 商户密钥 / MD5 Key
- 异步通知地址
- 同步跳转地址
- 签名算法
- 支持的支付方式

建议先选一家稳定平台，不要同时接多家。拿到字段后不要发到公开聊天，可以直接写进服务器环境文件；我再按它的签名规则接回调。

建议预留地址:

- 异步通知: `https://你的域名/api/frist/payments/yipay/notify`
- 同步跳转: `https://你的域名/#billing`

国内聚合支付必须先确认签名算法、金额单位、订单号长度、回调重试规则和回调来源 IP。没有这些信息不能写安全的自动入账逻辑，否则会出现伪造回调或重复入账。

## 固定域名和证书

品牌上线方案已按“先用现有 xyz 子域名闭环”的路线落地：当前正式入口为 `jiyu.245334.xyz`，复用 `/Users/blackdj/Documents/VPS-Config` 已有 Cloudflare DNS、R2/备份资产和服务器配置方式；OpenClaw 只记录变量名和验证步骤，不复制该项目的私有凭据。2026-07-03 生产已从腾讯云切到 Oracle ARM；2026-07-04 新增 `jiyu.245334.xyz` Cloudflare proxied A 指向 `150.136.73.15`，Oracle Apache 使用覆盖 JiYu/Frist 别名的 Cloudflare Origin CA 证书反代 Frist-API。专用 Tunnel 曾短暂验证但因 systemd 日志会暴露 token 已停用并删除。`frist-api.245334.xyz` 只做跳转/排障/冷回滚别名，不再作为用户宣传入口。

历史免费方案曾使用 `nip.io` wildcard DNS，例如 `frist-api.101-43-41-96.nip.io` 会解析到腾讯云 `101.43.41.96`。现在正式入口是 `https://jiyu.245334.xyz`；旧 `frist-api.245334.xyz` 会跳转到 CC中转主站，旧 nip.io 只保留冷回滚排障语境，如果腾讯云旧容器保持停止，旧 nip.io 返回 502 属于预期，不应再发给用户。

旧 nip.io 冷回滚排障步骤（非当前生产入口）:

1. 在服务器检查 80/443 是否已被其他项目占用，避免影响共享项目。
2. 新增 Nginx server block: `server_name frist-api.101-43-41-96.nip.io` 反代到 `http://127.0.0.1:3180`；`server_name 101-43-41-96.nip.io` 只返回 301 到品牌域名。
3. 使用 certbot 给 `frist-api.101-43-41-96.nip.io` 申请证书；本轮证书机构访问 80 端口 ACME challenge 返回 connection reset，免费域名 HTTPS 未签发成功。
4. 只有执行腾讯云冷回滚时才临时配置旧 HTTP 入口；正常 Oracle 生产必须保持 `FRIST_API_PUBLIC_GATEWAY_BASE_URL=https://jiyu.245334.xyz/v1`、`FRIST_API_CANONICAL_HOST=jiyu.245334.xyz`，并保持 `FRIST_API_ALLOW_INSECURE_PUBLIC_HTTP` 关闭。
5. 重启容器后跑首页、看板、`/v1/models` 未授权 401、管理员入口隐藏和支付回调 URL 冒烟。

免费域名只适合历史排障。正式投放使用 CC中转品牌入口，并沿用 VPS-Config 的 Cloudflare/R2 配置治理方式。

2026-07-04 当前入口状态：

1. `https://jiyu.245334.xyz/`：当前正式用户入口，Cloudflare DNS proxied A 指向 Oracle ARM `150.136.73.15`，Oracle Apache 使用 Cloudflare Origin CA 证书反代；外网首页和 Dashboard 冒烟返回 HTTP 200。
2. `https://frist-api.245334.xyz/`：旧入口，保留为 301 跳转和冷回滚排障别名，正常对外投放不再使用。
3. Oracle 生产服务已启用 New-API adapter；`FRIST_API_NEWAPI_ENABLED=1` 与 `FRIST_API_REQUIRE_NEWAPI_DATABASE=1` 已生效。
4. R2 定时备份已在 Oracle 启用；最近一次手动上传 HTTP 200。
5. 腾讯云旧入口和 `http://frist-api.101-43-41-96.nip.io/` 只保留冷回滚，不再作为用户入口；旧容器停止时该地址不可用是预期。
6. SMTP 密码已通过隐藏输入方式落地；生产测试邮件已返回 `smtp_test=sent`。

当前采用 Cloudflare DNS 代理，不依赖长期 `cloudflared` 服务。2026-07-04 Oracle 源站已安装 Cloudflare Origin CA 证书并让 Apache 监听 `jiyu.245334.xyz:443`，证书同时覆盖旧 Frist 别名，解决 Cloudflare 526 风险。若未来重新启用 Tunnel，必须把 Tunnel token 放在 root-only 环境文件，且禁止通过 `systemctl status` / 服务日志输出 token。

参考官方文档：

- Cloudflare DNS: https://developers.cloudflare.com/dns/manage-dns-records/how-to/create-dns-records/
- Cloudflare Proxy status: https://developers.cloudflare.com/dns/proxy-status/

域名切换后需要同步修改服务器环境变量，例如 `FRIST_API_PUBLIC_GATEWAY_BASE_URL=https://jiyu.245334.xyz/v1`、`FRIST_API_CANONICAL_HOST=jiyu.245334.xyz`。否则用户导出的 Codex/OpenCode 配置仍可能指向旧测试入口。

## 邮箱和防刷

当前已有轻量验证码、登录频率限制和 New-API 原生 Turnstile；余额预警、注册验证和找回密码邮件都可以走 SMTP。正式开放陌生用户前需要维持可售兑换码库存、确认模型请求限流阈值，并跑一单真人小额实单。

你需要人工准备:

- SMTP 主机、端口、用户名、应用专用密码、发件邮箱。余额预警、注册验证码和找回密码共用 `FRIST_API_SMTP_HOST`、`FRIST_API_SMTP_PORT`、`FRIST_API_SMTP_SECURE`、`FRIST_API_SMTP_FAMILY`、`FRIST_API_SMTP_USER`、`FRIST_API_SMTP_PASSWORD`、`FRIST_API_SMTP_FROM` 和 `FRIST_API_BALANCE_ALERT_FROM_NAME`。
- Cloudflare Turnstile Site Key 和 Secret Key。
- 一个客服邮箱，用于账单、找回密码和异常申诉。

建议先用企业邮箱或域名邮箱，不建议用个人邮箱长期发验证码。Gmail 这类个人邮箱只能作为短期测试，应用专用密码只允许写入服务器环境变量，不能写入仓库、文档、命令历史或运行数据。当前生产已配置 Gmail SMTP：使用 `smtp.gmail.com`、465 端口、TLS、`FRIST_API_SMTP_FAMILY=auto`；测试邮件已成功发出。

余额预警测试方式:

1. 用户登录 Frist-API，进入 `账单`。
2. 在 `余额预警` 卡片里打开开关，填写阈值和收件邮箱。
3. 点击 `发送测试邮件`。成功说明 SMTP 可以发信；失败时页面会显示 SMTP 未配置或连接异常。
4. 真实扣费后，系统只在余额从阈值上方跌到阈值以下时发送一次，避免每次调用都刷邮件。

如果本机或云厂商出口限制 SMTP，可能出现 465/587 端口 TCP 可连但 TLS 或 SMTP greeting 阶段无响应。遇到这种情况，不要反复换代码，先在正式服务器网络上跑测试邮件，再决定是否改用企业邮箱、邮件服务商或放行 SMTP 出口。Oracle 实测 Gmail 465/TLS 可用；默认 `FRIST_API_SMTP_FAMILY=auto` 会按 DNS 地址逐个尝试。如某台服务器 IPv4 长期超时，可临时设为 `6`。

Turnstile 已复用 Frist 旧配置接入 New-API：前端只保存 Site Key，Secret Key 只能放在服务器。服务端必须校验 Cloudflare 返回结果，不能只检查前端传了一个 token。

## 模型列表和默认最强模型规则

商业化页面不能靠硬编码宣传模型能力。正确规则是:

1. 补号时优先请求上游 `/v1/models`。
2. 上游不支持 `/models` 时，按内置候选清单做低成本探测，只把真实通过的模型写入库存。
3. 图片模型必须走 `/images/generations` 探测；`image2` 会先清洗为 `gpt-image-2`，不能用 `/chat/completions` 或 `/responses` 判断图片库存是否健康。
4. 用户创建 Key 后，`/v1/models` 只返回这个用户有权限且库存健康的模型。
5. CC Switch 导出时，页面展示完整可用模型列表，默认模型从这个列表里按强度排序选择。
6. 如果官方模型目录没有某个名字，只能标为上游兼容模型，不能在页面上写成官方模型。

因此，导出 Codex/OpenCode 时应该显示“完整可用列表 + 默认最强模型”。页面和手动配置可以保留完整模型列表；`ccswitch://` 深链必须保持短字段，只写 CC Switch 当前官方 provider parser 消费的 `resource/app/name/homepage/endpoint/apiKey/model/*Model/notes/usage*` 字段，避免旧 `config` / `availableModels` 大块参数导致链接过长或解析偏差。

## Codex MCP 默认增强

Codex 的 CC Switch 导出会在 `config.toml` 里直接写入推荐 MCP:

- `playwright`: 通过固定版本 `@playwright/mcp@0.0.78` 给 Codex 增加浏览器自动化能力。
- `superpowers`: 通过固定版本 `superpowers-mcp@6.2.0` 增加 TDD、调试、协作类工作流提示。
- `open_computer_use`: 通过固定版本 `open-computer-use@0.3.1` 启动 `open-codex-computer-use-mcp`，给支持的 Codex 环境准备电脑操作入口。

这三项属于 Codex 配置增强，不影响 Claude/OpenCode/Hermes 的供应商导入。需要注意: Computer Use 涉及本机系统权限，CC Switch 可以写入配置，但第一次真实使用时仍需要用户按 Codex 或系统弹窗完成辅助功能、屏幕录制等权限授权。

## 生产验收顺序

1. 固定域名生效，`/` 可打开，`/v1/models` 未授权返回 401。
2. 注册验证码邮件、登录、忘记密码、创建 Key、改名、删除 Key 均可用。
3. 用户提交充值申请后，订单进入待支付或待人工确认状态，不直接加余额。
4. 微信/支付宝 0.01 元测试能生成二维码、收到真实回调并自动入账，重复回调不会重复加钱。
5. 管理员人工入账后，用户余额或套餐立即变化，事件能在管理端看到。
6. 上游库存补入后，`/v1/models` 返回完整健康模型列表，不泄露上游 Key。
7. Codex/OpenCode 导入配置里的默认模型和完整模型列表一致。
8. Codex 导入配置包含 Playwright、Superpowers、open-computer-use MCP 段；Computer Use 首次运行能引导用户完成系统权限授权。
9. `/v1/chat/completions`、`/v1/responses`、`/v1/images/generations` 能按用户 Key 鉴权、转发和扣费。
10. 上游 5xx、余额不足或网络失败时会切换备用 Key，并保留原请求体。
11. runtime 文件中用户 Key 和上游 Key 以 `enc:v1:` 形式保存，重启后仍能正常鉴权和路由。
12. 备份恢复演练后，用户余额、Key、订单和库存仍存在。

## 你不用手动处理的事

这些已经由 Frist-API 处理:

- 用户 Key 生成、开关和请求地址展示。
- CC Switch、Codex、Claude、OpenCode、OpenClaw、Hermes 导入配置清洗。
- 上游订单文本解析、Key 提取、请求地址清洗、模型探测和认证字段清洗。
- `5.5`、`gpt5.5`、`image2` 等广场常用别名清洗。
- 小时卡、日卡、月卡、不限时库存优先级。
- 额度用尽、上游 5xx、网络失败后的自动切换。
- 同一会话的上游粘滞和失败后完整请求体转移。
- 用户侧隐藏上游号商、上游 Key、管理令牌和库存细节。

---

## 二、Frist-API 快速启动


> 日期: 2026-05-03
> 范围: 可小范围开放测试的网站、轻量中转后端、隐藏管理端、Docker 部署入口

## 当前定位

Frist-API 是独立公开网站，放在 `apps/frist-api/`，不改 OpenClaw APP 现有 New API 页面。它只做注册、登录、改密、充值/入账、发 Key、计费、用量统计、CC Switch 导入和上游号源中转，不使用服务器本地硬件做模型推理。

当前公网验收入口:

- 正式用户端: `https://jiyu.245334.xyz/`
- 正式 API 网关: `https://jiyu.245334.xyz/v1`
- 旧 Frist 入口: `https://frist-api.245334.xyz/`，只做 301 跳转和冷回滚排障。
- 旧 `http://frist-api.101-43-41-96.nip.io/` 和裸 `http://101-43-41-96.nip.io/` 只保留腾讯云冷回滚排障，不再作为生产入口。

当前 CC中转子域名和 HTTPS 证书已闭环；生产 `FRIST_API_PUBLIC_GATEWAY_BASE_URL` 为 `https://jiyu.245334.xyz/v1`。后续若老板购买独立品牌域名，再按同一流程替换主域名。

管理端不公开展示。普通 `/admin.html` 在公网会返回 404。日常用法是先注册/登录自己的用户账号，在右上角账户区域输入一次性管理员身份码，当前账号会升级为管理员，身份码随即作废；升级后账户区域会出现运营入口，管理 API 也会直接识别当前登录态。隐藏入口码和管理员令牌仍保留为服务器后备方案，不给普通用户展示。

人工收款、固定域名、SMTP、Turnstile 和正式支付接口的操作清单见本文件上方的 Frist-API 运营操作清单。

无域名阶段这是临时 HTTP 验收地址。当前固定 HTTPS 入口、SMTP 注册验证/找回密码、Turnstile、管理员 2FA、New-API 数据库、备份恢复和 5 张内测可售兑换码库存均已接入；正式开放陌生付费用户前需要确认模型请求限流阈值，并完成一次真人浏览器注册/登录/兑换 + 小额闲鱼实单验收。收款主路径继续走闲鱼兑换码，不把真实支付回调作为本阶段上线门槛。

## 用户端能看到什么

用户端是工作台式控制台，不再是大面积营销 Hero 或高密度管理后台。

- 首页左侧是紧凑工作台导航，右侧只保留余额、API Key、累计消耗、模型连通四个核心状态卡，以及模型消耗和 Claude/OpenAI 连通性。
- 广场页面提供模型下拉选择、对话窗口和“实测连通”按钮，文字模型走聊天网关，`gpt-image-2` 等图片模型走图片生成网关；图片广场默认使用 `quality: low`、`output_format: png` 和 `n: 1` 做轻量公网实测，并在页面显示成功/失败、耗时和返回摘要。
- 数据看板展示模型消耗分布、消耗列表和服务可用性，不展示上游渠道或库存细节。
- 模型广场展示可用模型、模型家族、用途、上下文和计价，价格口径用客户能理解的销售展示文案。
- 使用教程展示 Codex、Claude、OpenClaw 的 JSON/TOML 配置，并提供 macOS/Windows 一键配置命令。
- 未登录游客页只显示 0 余额、0 消耗和 0 调用，不再用演示账单填空。
- 注册、登录和改密只在右上角账户菜单里，不放进 API 页面正文；公开模式下注册/登录会先做轻量验证码挑战和 IP 频率限制。
- API 页面只处理创建 Key、开关 Key、复制 Key 和请求地址。
- 创建 Key 时可选择模型分组: Claude、OpenAI、Other 或 All；分组不匹配的模型会在网关层拦截。
- 充值页面主路径是购买兑换码，充值卡片只保留套餐和金额；闲鱼商品链接位置已预留。
- CC Switch 页面让用户选择 Claude、Codex、OpenCode、OpenClaw、Hermes，并生成一键导入链接。
- 手动配置里提供 `auth.json` 和 `config.toml`，适配 Codex、OpenCode 等兼容 OpenAI Responses 格式的客户端。
- 导入配置统一写入 Frist-API 供应商标识、官网入口、公开网关地址、用户 `fk-live-*` Key、Responses/Anthropic 兼容入口、`xhigh` 推理强度、上下文窗口、自动压缩、`setCacheKey` 和工具搜索配置，不暴露上游号商信息；历史 `sk-*` Key 仅作为兼容读取。
- 用户端不展示补号助手、上游号商、价格解析、渠道、倍率、模型映射和库存。右上角常驻“登录/身份码/管理”快捷入口：游客点击先登录，登录后可直接输身份码激活管理员，激活后同位置直达管理页，移动端可直接操作。

## 管理端能做什么

管理端独立在隐藏入口后。推荐方式是用一次性管理员身份码把你的账号升级为管理员，然后通过右上角“管理”快捷入口进入；管理员令牌只作为后备方式保留在服务器环境变量里，不写入仓库和公开文档。

- 人工入账: 按用户邮箱确认日卡、月卡或余额充值。
- 闲鱼自动发货助手: 支持 OpenClaw `XianyuLive` 全自动 webhook，也支持手工粘贴已付款订单兜底；只要订单确认已付款，就会分配未使用兑换码、生成发货话术、发送给买家并把履约状态标记为已发货；多商品/多套餐时先在本机 GUI 配置 `item_id → planId`，自动发货会优先按映射选择套餐；无映射、无套餐或无 SKU 订单才会回退默认套餐/任意未售兑换码；如果卡已分配但闲鱼消息发送失败，本机 GUI 的“CC中转发货补救队列”会保留待补发话术，后台默认自动重试发送，页面也可一键“重试发送”；当闲鱼订单 API 返回无权限或 WebSocket 漏掉付款卡片时，可在 Chrome 插件里对当前买家聊天页开启“看守当前聊天页”，也可在只有 1 条待发货时开启“看守所有闲鱼页”；插件只复用已分配待发送话术并成功一次后自动关闭；当前不做自动砍价、批量私信或刷单。
- 补号助手: 可直接粘贴订单详情，也可手动输入请求地址、可选代理地址、池子、模型、价格文本和一批上游 Key。
- 备用渠道: CPA JSON、chong 和其他人工备用渠道只能在管理端登记；默认进入隔离态，必须人工核验并勾选确认后才会进入路由。
- 订单清洗: 自动识别请求地址、卡密、日卡/月卡/不限时、额度、数量、创建时间、到期时间、模型、认证字段、认证前缀和额外请求头。
- 自动探测: 同一请求地址优先探测一次模型列表；每枚 Key 做最低成本健康检查，图片模型会走 `/images/generations` 探测，不再误用聊天接口。
- 余额站探测: 授权余额站可以填供应商根地址；如果根地址返回网站 HTML 壳，补号会自动尝试同域 `/v1`，并要求返回 OpenAI 兼容 JSON 才写成健康库存。
- fallback 探测: 上游不支持 `/models` 时，按内置模型清单逐个低成本探测，只写入可用模型。
- 直连/代理择优: 对直连和代理路径做低成本检测，选择成功率更高且延迟更低的 `routeBaseUrl`。
- 价格草稿: 粘贴美元或人民币价格文本后，自动换算销售价并参与网关扣费。
- 库存审计: 展示脱敏库存、补号、切换、耗尽、失败、浪费估算和路由事件。
- 低库存告警: 库存低于阈值时触发 `FRIST_API_LOW_INVENTORY_WEBHOOK`，后续可桥接 OpenClaw 的 Telegram/微信通知。
- Key 异常巡检: 后台每 60 秒巡检健康库存；若通道可达但 Key 认证失败或额度耗尽，会自动降级该 Key，并通过 Telegram/Webhook 只提醒一次补号，避免重复刷屏。用户端首页也会每 60 秒静默刷新，看板状态无需手动点“检测”。

管理端不会把原始上游 Key、管理员令牌或号商细节带到用户端。

## 业务链路

用户链路:

1. 用户打开 CC中转，右上角注册或登录，并完成轻量验证码挑战。
2. 用户选择日卡、月卡或余额，提交充值申请；公开环境默认不会自动给用户加钱。
3. 管理员通过隐藏入口进入管理端，按邮箱人工确认入账，或用户使用一次性兑换码。
4. 用户进入 API 页面选择模型分组并创建 `fk-live-*` Key。
5. 用户可以开启/关闭 Key，复制请求地址。
6. 用户进入 CC Switch 页面选择 Claude、Codex、OpenCode、OpenClaw 或 Hermes。
7. 页面生成 `ccswitch://v1/import` 一键导入链接，也提供 `auth.json` 和 `config.toml`。
8. 客户端使用页面展示的当前公开网关 `/v1` 地址和用户 Key 调用模型。

管理员首登链路:

1. 先按普通用户流程注册、登录、创建 Key 和导入 CC Switch，确认用户链路没问题。
2. 回到右上角账户菜单，在身份码输入框粘贴一次性管理员身份码。
3. 点击激活后，当前账号会获得管理员权限，身份码立即失效。
4. 账户菜单显示运营入口后，点击进入管理页；同一浏览器登录态可直接加载库存、人工入账和补号功能。

网关链路:

1. `/v1/models` 只返回健康库存中的客户安全模型；广场常用别名会先清洗为官方库存名，例如 `5.5` -> `gpt-5.5`、`image2` -> `gpt-image-2`。
2. `/v1/chat/completions`、`/v1/responses` 和 `/v1/images/generations` 使用用户 `fk-live-*` 鉴权，历史 `sk-*` Key 只保留兼容。
3. 网关先检查用户余额和套餐额度，余额不足时不访问上游。
4. 请求成功后优先按上游 `usage` 精确扣费；流式请求按预估消耗先扣费。
5. 客户端传 `x-frist-session-id`、`x-conversation-id` 或 `metadata.frist_session_id` 时，同一会话优先固定到同一枚健康上游 Key。
6. 库存消耗顺序是小时卡、日卡、月卡、不限时、默认池；同池内优先用更早到期、延迟更低的 Key。
7. 日卡 Key 额度不足、上游余额不足、上游 5xx 或网络失败时，网关摘除当前 Key，清掉会话粘滞记录，并带着完整请求体切到下一枚健康 Key。
8. 日卡到期后，网关路由前清空套餐额度并切回默认套餐。

## 本地运行

```bash
make frist-api-dev
```

打开:

```text
http://127.0.0.1:3180
http://127.0.0.1:3180/admin.html
```

本地如果设置了 `FRIST_API_ADMIN_PAGE_CODE`，管理页也会走隐藏入口；公网环境必须设置。

本地测试:

```bash
make frist-api-test
```

### 本机 QuantumNous/new-api 直连运行

如果老板要“直接跑 New-API 本体，再让 Frist-API 接上去”，走这条路径：

```bash
# 1. 启动 QuantumNous/new-api；启动前会自动备份 data/newapi
make new-api-up

# 2. 首次使用时打开 New-API，完成初始化并在个人资料页生成 access token
open http://127.0.0.1:3000

# 3. 把 New-API access token / user id 写入本机 .env；脚本不会打印密钥
make frist-api-newapi-setup

# 4. 启动 Frist-API + New-API 全链路
make frist-api-up
```

打开：

```text
New-API 管理页: http://127.0.0.1:3000
CC中转用户页: http://127.0.0.1:3180
Frist-API 网关:   http://127.0.0.1:3180/v1
```

快速验收：

```bash
docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}'
curl -sS http://127.0.0.1:3000/api/status
curl -sS http://127.0.0.1:3180/api/frist/dashboard
```

当前本机已验证：`openclaw-newapi` 使用 `calciumion/new-api:v1.0.0-rc.4` 监听 `127.0.0.1:3000`；`frist-api-server` 监听 `127.0.0.1:3180`；New-API `/api/status` 返回 `success=true`、`setup=true`；Frist-API Dashboard 返回 HTTP 200。停止全链路：

```bash
make frist-api-down
```

注意事项：

- `.env`、`data/newapi/`、`data/frist-api/runtime/` 都可能包含 token、用户 Key 或上游 Key，禁止提交 Git。
- `scripts/setup_local_newapi_bridge.mjs` 只读取本机 `data/newapi/one-api.db`，找不到 access token 时会要求先去 New-API 个人资料页生成。
- Docker 内部访问 New-API 用 `http://new-api:3000`；宿主机浏览器和 curl 用 `http://127.0.0.1:3000`。

当前回归覆盖 165 条，包括:

- 用户注册、登录、改密、验证码挑战、认证限流、充值申请、管理员入账、兑换码、创建 Key、开启/关闭 Key 和 CC Switch 导入。
- 广场模型对话、`5.5` / `image2` 别名清洗、广场连通实测、图片生成模型路由、图片模型补号探测、模型消耗分布、服务可用性、模型广场和使用教程页面接线。
- 五个导入目标: Claude、Codex、OpenCode、OpenClaw、Hermes。
- Codex/OpenCode 的 `auth.json`、`config.toml`、Responses 接口格式、上下文压缩、`setCacheKey` 和工具搜索配置生成。
- Codex 的 `config.toml` 默认写入 Playwright、Superpowers、open-computer-use MCP；Computer Use 第一次实际使用时仍需要用户按系统提示完成本机权限授权。
- Codex、Claude、OpenClaw 的 macOS/Windows 一键配置命令生成，并验证不携带上游号商字段。
- 用户端禁止出现管理端、补号、价格、号源、渠道写入等内容。
- 用户端使用紧凑工作台 rail，无 sticky、无旧版高密度分组文字。
- 公开 HTML 初始值和游客 Dashboard 不闪现演示套餐、演示金额或演示用户。
- 管理员一次性身份码升级、管理端隐藏入口、订单文本清洗、认证字段清洗、代理择优、fallback 模型探测、价格文本扣费。
- CPA JSON/chong 备用渠道人工风控: 隔离态不出现在 `/v1/models`，不触发上游调用；人工放行后才可作为备用库存路由。
- 日卡自动切换、会话粘滞、故障切换上下文保留、流式 SSE 透传。
- 图片生成请求使用同一套用户 Key、日卡库存、上游故障切换和扣费链路。
- OpenCode `/openai/chat/completions` 前缀路由、Chat Completions 到 Responses 降级、OpenCode `models` 对象映射、可复制 provider 片段，以及 Codex/OpenCode 完整模型清单导出。
- 授权余额站根地址返回 HTML 壳时，补号探测会自动切到 `/v1`，后续网关请求也固定走通过探测的 OpenAI 兼容路径。
- CC Switch 3.14.1 深链导入 OpenCode 时可能只写默认模型；遇到这种情况，使用页面上的“OpenCode 完整配置”复制 provider 片段，并合并到 `~/.config/opencode/opencode.json` 的 `provider`。
- 小时卡、日卡、月卡、不限时库存优先级和低库存通知钩子。
- 公开模式拒绝默认管理员令牌、默认会话密钥、验证码回显、演示充值和本地 HTTP 网关地址。

## Docker 原型

```bash
make frist-api-up
```

当前 Docker 原型使用 `node:22-alpine` 跑轻量 Frist-API 后端，同时复用 `calciumion/new-api:v1.0.0-rc.4` 作为底层业务网关。Frist-API 内存限制 256MB，New-API 内存限制 512MB，适配 2 核 2GB 的小服务器。运行数据默认写入 `data/frist-api/runtime/runtime.json` 与 `data/newapi/`，这些文件可能包含用户 Key、access token 和上游 Key，不能提交到 Git。

生产环境必须设置:

- `FRIST_API_ADMIN_TOKEN`: 强随机管理员令牌
- `FRIST_API_ADMIN_PAGE_CODE`: 隐藏管理入口码
- `FRIST_API_ADMIN_CLAIM_CODES`: 一次性管理员身份码，逗号分隔；每个码成功使用后自动失效
- `FRIST_API_SESSION_SECRET`: 强随机会话密钥
- `FRIST_API_PASSWORD_HASH_SECRET`: 强随机密码哈希密钥；不要和会话密钥共用。轮换 `FRIST_API_SESSION_SECRET` 时旧账号密码仍可用。
- `FRIST_API_LEGACY_PASSWORD_HASH_SECRETS`: 历史密码哈希密钥列表。上线修复旧环境时先填旧 `FRIST_API_SESSION_SECRET`，用户登录成功后会迁移到新 `FRIST_API_PASSWORD_HASH_SECRET`。
- `FRIST_API_PUBLIC_MODE=1`
- `NODE_ENV=production`
- `FRIST_API_ENFORCE_PRODUCTION_READINESS=1`: 正式开放陌生付费用户时打开；缺固定 HTTPS 品牌域名、New-API 数据库、管理员 2FA 或兑换码/备份等运营闭环会直接启动失败；自动支付商户不再作为当前上线必备项
- `FRIST_API_ALLOW_DEMO_RECHARGE=0`
- `FRIST_API_EXPOSE_VERIFICATION_CODE=0`
- `FRIST_API_REQUIRE_CSRF=1`
- `FRIST_API_REQUIRE_ADMIN_2FA=1`
- `FRIST_API_ADMIN_TOTP_SECRETS`: 管理员 TOTP Base32 Secret，多个用逗号分隔，只放服务器环境变量或 root-only 安全文件，不能写进仓库或聊天
- `FRIST_API_REQUIRE_CAPTCHA=1`，仅用于注册挑战；登录不再要求验证码
- `FRIST_API_CAPTCHA_MAX_ATTEMPTS=3`
- `FRIST_API_AUTH_RATE_LIMIT_MAX=20`
- `FRIST_API_PASSWORD_RESET_REQUEST_RATE_LIMIT_MAX=3` 与 `FRIST_API_PASSWORD_RESET_REQUEST_RATE_LIMIT_WINDOW_MS=900000`：同一账号 15 分钟最多请求 3 封重置邮件，邮件投递在全局 runtime 写队列外执行
- `FRIST_API_PASSWORD_RESET_CONFIRM_RATE_LIMIT_MAX=5` 与 `FRIST_API_PASSWORD_RESET_CONFIRM_RATE_LIMIT_WINDOW_MS=900000`：重置确认除 IP 外按账号再限制 5 次/15 分钟
- `FRIST_API_RATE_LIMIT_MAX_ENTRIES=10000`：限流桶满后拒绝新桶，不淘汰现有封禁
- `FRIST_API_TRUSTED_PROXY_IPS=127.0.0.1`：仅当 Node 直连对端确为本机 Nginx 时使用；未配置时忽略全部 `X-Forwarded-For`，配置错误会让反代用户共享一个限流桶
- `FRIST_API_BACKUP_STATUS_MAX_AGE_HOURS=26`: 备份超过 26 小时未登记则生产检查不通过
- `FRIST_API_SLA_RETENTION_DAYS=30`: 渠道 SLA 探测事件保留 30 天
- `FRIST_API_LOW_INVENTORY_WEBHOOK`: 可选，低库存通知 Webhook
- `FRIST_API_CHANNEL_MONITOR_ENABLED=1`: 启用后台通道巡检
- `FRIST_API_CHANNEL_MONITOR_INTERVAL_MS=60000`: 60 秒巡检一次
- `FRIST_API_CHANNEL_MONITOR_BATCH_SIZE=4`: 每轮最多巡检 4 个 Key
- `FRIST_API_CHANNEL_MONITOR_COOLDOWN_MS=55000`: 单 Key 最短巡检间隔
- `FRIST_API_KEY_ALERT_WEBHOOK`: 可选，Key 异常告警 Webhook
- `FRIST_API_TELEGRAM_BOT_TOKEN` / `FRIST_API_TELEGRAM_CHAT_ID`: 可选，Key 异常一次性补号提醒 Telegram 通知
- `FRIST_API_SMTP_HOST` / `FRIST_API_SMTP_PORT` / `FRIST_API_SMTP_SECURE` / `FRIST_API_SMTP_FAMILY`: 可选，余额预警邮件 SMTP 连接配置
- `FRIST_API_SMTP_USER` / `FRIST_API_SMTP_PASSWORD` / `FRIST_API_SMTP_FROM`: 可选，余额预警邮件登录和发件配置
- `FRIST_API_BALANCE_ALERT_FROM_NAME`: 可选，余额预警邮件发件人名称；Oracle 生产当前使用 `CC-Billing`，避免 shell source 类脚本被空格绊倒
- `FRIST_API_NEWAPI_ENABLED`: 生产设为 `1`，Frist-API 服务端通过 New-API 接管用户看板、API Key、日志、订阅、兑换和邀请数据
- `FRIST_API_REQUIRE_NEWAPI_DATABASE=1`: 生产硬门槛，防止继续把 JSON runtime 当数据库使用
- `FRIST_API_NEWAPI_BASE_URL` / `FRIST_API_NEWAPI_ACCESS_TOKEN` / `FRIST_API_NEWAPI_USER_ID`: 可选，New-API 内网地址、用户 access token 和对应用户 ID，只能放服务器环境变量
- `FRIST_API_NEWAPI_GATEWAY_ENABLED` / `FRIST_API_NEWAPI_GATEWAY_BASE_URL`: 可选，设为 `1` 后仅让 Frist 3180 的 `/v1` 桥接面代理 New-API；代理前必须同时通过本地唯一用户、完整 active owner 和上游 finite/enabled/正余额校验。该开关不控制 Apache 主域直连 New-API 的产品入口

无域名公网 IP 验收时可临时设置 `FRIST_API_ALLOW_INSECURE_PUBLIC_HTTP=1`。当前 Cloudflare HTTPS 入口已关闭这个临时开关。

生产边界验收（生产已开启管理员 2FA，管理接口需要先拿二次验证会话；不要在终端打印 token/secret）:

```bash
# 1) 先用 TOTP 验证，保存 Set-Cookie 里的 frist_admin_2fa，或把返回 cookie 写入临时 cookie jar。
curl -fsS -X POST \
  -H "x-admin-token: $FRIST_API_ADMIN_TOKEN" \
  -H "content-type: application/json" \
  --data '{"code":"<你的 6 位 TOTP>"}' \
  https://你的域名/api/admin/2fa/verify

# 2) 再带 x-admin-2fa-session 或 cookie 读取 readiness。
curl -fsS \
  -H "x-admin-token: $FRIST_API_ADMIN_TOKEN" \
  -H "x-admin-2fa-session: $FRIST_ADMIN_2FA_SESSION" \
  https://你的域名/api/admin/production-readiness
```

备份任务完成后登记一次状态，恢复演练建议至少每月跑一次。Oracle 当前 `frist-api.service` 的工作目录是 `/opt/frist-api/apps/frist-api`，唯一实际加载的 systemd 环境文件是 `/etc/frist-api/frist-api.env`；仓库 `apps/frist-api/deploy/production.env.example` 只是模板。服务器 env 文件按 key/value 解析，不要直接 `source /etc/frist-api/frist-api.env`，避免包含空格或特殊字符的值被 shell 误执行。

```bash
curl -fsS -X POST \
  -H "x-admin-token: $FRIST_API_ADMIN_TOKEN" \
  -H "x-admin-2fa-session: $FRIST_ADMIN_2FA_SESSION" \
  -H "content-type: application/json" \
  --data '{"provider":"rclone-r2","target":"r2://frist-api-prod/runtime","lastBackupAt":"2026-07-05T00:05:09.000Z","lastRestoreTestAt":"2026-07-05T00:05:09.000Z","status":"ok","artifact":"frist-api-20260705T000508Z.tar.gz","checksum":"sha256:..."}' \
  https://你的域名/api/admin/backups/status
```

2026-07-04 生产验收记录（UTC 时间为 2026-07-05T00:05:09Z）：

- `FRIST_API_PUBLIC_MODE=1`、`FRIST_API_ENFORCE_PRODUCTION_READINESS=1`、`FRIST_API_ALLOW_INSECURE_PUBLIC_HTTP=0` 已在 Oracle 生产启用。
- 管理员 TOTP 2FA 已启用，secret 保存在 Oracle root-only 环境文件/安全文件中。
- R2 备份 `frist-api-20260705T000508Z.tar.gz` 已解包恢复演练，`runtime.json` 可读，`one-api.db` 完整性检查为 `ok`。
- `/api/admin/production-readiness` 当时返回 `ready=true`，7 项检查全部通过；2026-07-05 起已追加第 8 项“健康上游库存”，若 New-API `channels/models` 和 Frist 健康库存均为 0，则必须返回 `ready=false`，禁止正式售卖。

冒烟检查:

```bash
apps/frist-api/deploy/smoke-test.sh http://127.0.0.1:3180 "$FRIST_API_ADMIN_PAGE_CODE"
```

## New-API 业务桥接模式

启用 `FRIST_API_NEWAPI_ENABLED=1` 后，Frist-API 不复制 New-API 的 Go 业务代码，而是通过 New-API 官方 HTTP 接口复用成熟业务逻辑。当前可直接接管:

- 用户看板: `/api/user/self`、`/api/log/self`、`/api/log/self/stat`、`/api/data/self`
- API Key: `/api/token/`、`/api/token/search`、`/api/token/:id/key`、`PUT /api/token/`、`DELETE /api/token/:id`
- 兑换码: `POST /api/user/topup`
- 订阅/充值/邀请读取: `/api/subscription/self`、`/api/user/topup/info`、`/api/user/aff`
- 可选模型网关: `FRIST_API_NEWAPI_GATEWAY_ENABLED=1` 后代理 `/v1/chat/completions`、`/v1/responses`、`/v1/images/generations`、`/v1/messages`；未归属、旧字符串归属、待激活、残缺、孤儿、无限、耗尽或禁用 Token 在实际网关请求前统一拒绝

仍然保留在 Frist-API 自研层的部分:

- Workbench 前端视觉、页面结构和客户动线。
- CC Switch、Codex、Claude、Gemini、OpenCode、OpenClaw、Hermes/Harmes 的导入配置生成。
- Codex + DeepSeek 官方端点 `https://api.deepseek.com/v1` 的配置生成；新导入默认 `deepseek-v4-flash`，同时保留 `deepseek-v4-pro`、`deepseek-chat`、`deepseek-reasoner` 兼容。
- 余额预警邮件、隐藏管理员身份码、补号助手、备用渠道人工风险隔离、供应商文本解析和本地 JSON 兜底。

启用前必须先在 New-API 里生成用户 access token，并确认 `FRIST_API_NEWAPI_USER_ID` 与该 token 所属用户一致。New-API v1 会同时校验 `Authorization` 和 `New-Api-User`，二者不一致会认证失败。

## 当前限制

- JSON runtime 仍作为兜底和本地小范围验收可用；生产已启用 `FRIST_API_NEWAPI_ENABLED=1` 和 `FRIST_API_REQUIRE_NEWAPI_DATABASE=1`。2026-07-03 已按授权执行 New-API 迁移：用户、余额、订单、兑换码和日志已迁入 New-API；16 个历史 `enc:v1:` 用户 Key 因旧加密密钥缺失未迁移，避免把密文伪造成可用 Key。
- 已有轻量验证码、认证限流、一次性管理员身份码、管理员 TOTP 2FA、余额预警 SMTP 邮件、兑换码核销和备用真实支付回调代码；当前收款走闲鱼兑换码，商户自动支付不是必需项。正式域名/Cloudflare/R2 已复用 VPS-Config 既有资产落地，SMTP 密码已隐藏输入并通过生产测试邮件验证；2026-07-05 已复用 Frist 旧配置启用 New-API 原生 Turnstile、邮箱验证和管理员 2FA。
- 补号探测已做低成本可用性判断、Responses fallback、直连/代理择优和认证字段清洗，但未做完整上下文上限、工具调用、流式能力和模型质量评分。
- CPA JSON/chong 入口只做人工登记和放行，不包含 OAuth Session 提取、Refresh Token 刷新、账号池规避风控或自动化批量获取逻辑。
- `QuantumNous/new-api` 是 AGPL-3.0；Frist-API 页面页脚已提供现有 OpenClaw-Bot 源码入口。若后续二开 New-API 本体并公开运营，仍需确保复用的 GitHub 仓库/fork 可公开访问。

## New-API JSON runtime 迁移演练

本仓库提供只读迁移演练脚本，先生成可审计材料，不直接写生产库：

```bash
node scripts/frist_api_newapi_migration_dry_run.mjs \
  --file apps/frist-api/data/runtime.json \
  --package \
  --output-dir apps/frist-api/data/migration-plans
```

输出内容包括：

- 当前 runtime 用户、用户 Key、订单、兑换码、网关日志和上游库存统计。
- 带时间戳的 runtime 备份。
- 幂等迁移计划 JSON（只含脱敏 Key 预览，不写原始 Key）。
- 回滚脚本，用于把 runtime 恢复到迁移前备份。

2026-07-03 已在生产执行 `--apply`：迁移用户 19 个、New-API token 1 个、充值/订单 4 条、兑换码 2 条、日志 162 条；回滚目录为服务器 `/opt/frist-api/backups/newapi-migration-20260703T005433Z`。因旧 `FRIST_API_DATA_ENCRYPTION_KEY` 未能在本地、VPS-Config 或服务器常规备份中找到，16 个历史 `enc:v1:` 用户 Key 未迁移到 New-API token；用户需要重新生成/补录可用 Key。

## New-API 上游同步 SOP

New-API 不再从旧本地目录复制代码。项目用 `packages/new-api-upstream` submodule 固定上游 release，用 `docker-compose.newapi.yml` 固定同版本 Docker 镜像，Frist-API 和 ClawBot 通过接口代理复用业务逻辑。

当前生产内测的渠道倍率策略已显式固定为 `FRIST_API_RATE_MARKUP=0.1`：同步上游渠道倍率时，只在上游倍率基础上加 `0.1`，不额外改写其余价格口径。

日常检查:

```bash
make new-api-check
```

升级到 GitHub 最新非草稿 release:

```bash
make new-api-sync
git submodule status packages/new-api-upstream
docker compose -f docker-compose.newapi.yml config
```

运行或升级服务前必须先备份本地 New-API 数据:

```bash
mkdir -p data/backups
tar -czf "data/backups/newapi-$(date +%Y%m%d-%H%M%S).tgz" data/newapi
```

注意事项:

- 当前固定版本为 `v1.0.0-rc.4`，镜像为 `calciumion/new-api:v1.0.0-rc.4`。
- `make new-api-check` 发现版本落后会返回非 0；自动创建同步 PR 的旧 workflow 已随生产切换到 Sub2API 删除，冷回滚研究只允许人工执行 `make new-api-sync`。
- Docker Desktop 或服务器 Docker daemon 必须运行，才能执行镜像 pull、容器启动和健康检查。
- 本地已有 `data/newapi/new-api.db` 和 `data/newapi/one-api.db`，不要在未备份时直接启动新版容器，避免自动迁移后无法回退。
- New-API v1 后台/用户接口需要 `Authorization` 和 `New-Api-User` 一致；ClawBot 代理环境变量为 `NEWAPI_ADMIN_TOKEN` / `NEWAPI_ADMIN_USER_ID`，Frist-API 桥接环境变量为 `FRIST_API_NEWAPI_ACCESS_TOKEN` / `FRIST_API_NEWAPI_USER_ID`。
- `docker-compose.newapi.yml` 默认把容器 `3000` 端口绑定到宿主机 `127.0.0.1:${NEWAPI_HOST_PORT:-3000}`；共享服务器已有其他项目占用 3000 时，只设置 `NEWAPI_HOST_PORT=13000`，不要停止无关服务。
- 公开商业化时，AGPL-3.0 合规要求必须准备源码公开入口或公开 fork。

当前生产状态:

- Oracle ARM `/opt/frist-api` 已承接 Frist-API 和 New-API：`frist-api.service` 监听 `127.0.0.1:3180`，`openclaw-newapi.service` 监听 `127.0.0.1:13000`。
- 腾讯云 `/opt/frist-api` 仅保留冷回滚数据；旧 `frist-api-server` / `openclaw-newapi` 容器已停止，旧 `frist-api-r2-backup.timer` 已禁用。

## 下一步

1. 维护闲鱼兑换码商品、自动发货规则和卡密库存告警；自动支付商户平台开户当前不推进。
2. 持续审计上游真实 `/v1/models`、余额站日限额、慢线降级和价格版本。
3. 保持页面源码入口可见，确保 AGPL-3.0 上游合规。

---

## 三、闲鱼 Cookie 刷新


### 方法1：Chrome浏览器（推荐）

1. 打开 Chrome，访问 https://2.taobao.com/
2. 登录你的闲鱼账号
3. 按 F12 打开开发者工具
4. 点击 "Application" 标签
5. 左侧展开 "Cookies" → 点击 "https://2.taobao.com"
6. 复制所有 Cookie，格式：name1=value1; name2=value2; ...

### 方法2：使用插件（最简单）

1. 安装 Chrome 插件：EditThisCookie
2. 访问 https://2.taobao.com/ 并登录
3. 点击插件图标 → Export → 复制

### 需要的关键 Cookie

必须包含这些字段：
- `_m_h5_tk`
- `_m_h5_tk_enc`
- `cna`
- `t`
- `unb`
- `_tb_token_`

### 更新到配置

复制完整 Cookie 字符串，替换 `config/.env` 中的：
```
XIANYU_COOKIES=你的新Cookie
```

### 注意事项

- Cookie 有效期约 24 小时，需定期更新
- 不要在多个设备同时登录（会导致 Cookie 失效）
- 确保网络能直连闲鱼（不要用代理）

---

## 四、部署验证清单

### 当前支持的桌面发布路径

- 历史 `OpenClaw-Installer-v4.0.zip`、Web 安装器、百度网盘下载和“退款自动销毁”方案均未进入当前仓库发布链，不得再对外宣称已提供。
- 桌面端只允许执行 `make tauri-build`。安装器的唯一运行真值为 `src-tauri/npm-runtime-lock/`：当前 OpenClaw 精确固定到 `2026.7.2-beta.7`，全部传递依赖带 SHA-512；MCP 与供应链门都从该 manifest 读取版本，不保留第二份版本字符串。稳定版重新进入前必须同时满足相同配置合同、`npm audit` 高危为 0 和回滚门。
- MCP Store 当前只展示桌面代码内登记的 8 个受管运行包目录；返回值不含 command/args/env，桌面端不声称已经建立 stdio 会话，也不提供伪启动/停止按钮。真实 MCP 配置和会话仍由 CC Switch/OpenClaw 官方配置链负责；受管运行时仍通过锁文件 `npm ci --ignore-scripts` 安装，任何在线 `npx -y`、自定义解释器、额外参数和未登记环境变量均失败关闭。
- Frist 充值先在本地短事务中锁定订单，再在事务外请求支付渠道，成功/失败各自以第二个短事务落库；渠道请求受 `FRIST_API_PAYMENT_REQUEST_TIMEOUT_MS` 硬超时保护，默认 15 秒。微信回调还必须匹配配置商户身份、原渠道、平台序列号、时间戳窗口和平台交易号唯一性，重复成功回调不增长事件记录。
- Docker Compose 的外部镜像必须使用 `tag@sha256:<digest>`；`make clean-install-check` 在临时目录用 npm 与 Python 哈希锁重装，验证开发机没有依赖缓存假绿。
- 当前发行边界仍是 macOS 本机内测。没有 Developer ID、公证和 Windows/Linux 实机构建证据时，不得宣称跨平台公开安装包已经就绪。

### 发布前证据

1. `make python-lock-check` 复算 Linux/macOS 两份哈希锁，`make supply-chain-check` 核验 Action SHA、354 包 npm 完整性和高危漏洞，随后运行 `make ci-local`。
2. `scripts/auto_health_check.sh --json` 必须同时返回 `ok=true` 与 `release_ready=true`。
3. `make tauri-build` 成功后，`/Applications` 只能保留一个 `OpenClaw.app`，并通过严格签名校验、`make tauri-rollback-check` 和真实首屏截图验收。
4. CC中转继续按本手册“一、CC中转 / Frist-API 运营操作清单”执行真实小额单、库存、履约和回滚门；不复用已经废止的桌面安装包售卖文案。

### 2026-08-04 最终实测证据

- `make ci-local` 的最终数字必须以命令末次输出和 `docs/086-release-evidence.md` 为准；该门现在包含 Python 双锁复算、受管 npm 审计、临时目录干净安装、Python/Frist/桌面/Rust 全量测试、TypeScript、ESLint、Vite、覆盖率和文档真实性检查。
- npm 三组审计与 `pip-audit` 均为 0；Gitleaks 扫描 859 个提交、约 55 MB 历史无泄漏；354 包完整性与 Linux/macOS Python 哈希锁复算通过。
- `make tauri-build` 成功生成并安装 `OpenClaw.app` 和 DMG；构建脚本在删除旧 App 前先完成所有本地备份，任何备份不完整都保持旧安装不动；随后由 `codesign --verify --deep --strict`、`hdiutil verify`、`make tauri-rollback-check` 和唯一安装检查生成证据。
- `/Applications` 只存在 `OpenClaw.app`，版本 `0.1.1`、Bundle ID `com.openclaw.manager`；0.1.1 与 0.1.0 的 CDHash 不同，已实测 `0.1.1 → 0.1.0 → 0.1.1` 双向交换并在每一步通过严格签名和回滚检查。清单同时记录源码补丁 SHA-256 与 DMG SHA-256；同指纹副本会被拒绝，不再计为有效回滚。真实安装包首屏截图见 `output/playwright/openclaw-installed-app-final.png`。当前签名为 ad-hoc 内测签名，未持有 Developer ID/公证凭据，因此不扩张为公开发行证据。

## 每日资讯 V2 本机部署与回滚

### 生产合同

- listener: `ai.openclaw.intel-brief.telegram-listener`
- scheduler: `ai.openclaw.intel-brief.scheduler`，本机 Asia/Singapore 08:30
- 数据库: `packages/clawbot/data/intel_brief.db`，SQLite V3
- 私有环境: `.openclaw/intel-brief.production.env`，权限必须为 0600 且保持 Git 忽略
- 生产开关: `INTEL_BRIEF_TRANSLATION_ENABLED=true`、`INTEL_BRIEF_SCHEDULER_TIMEZONE=Asia/Singapore`、`INTEL_BRIEF_SCHEDULER_WINDOW_END=10:00`、`INTEL_BRIEF_TELEGRAM_RICH_MESSAGE_ENABLED=false`
- `INTEL_BRIEF_TELEGRAM_MEDIA_CHAT_ID` 可选；不应把真实用户私聊当素材群。未配置时，首位收件人的 `sendPhoto` 回包会种入缓存。

### 部署顺序

1. 记录时间戳，复制私有环境文件，使用 SQLite `.backup` 生成数据库回滚副本并对副本执行 `PRAGMA quick_check`。
2. `launchctl bootout` 停止 listener，确认旧 PID 已退出。scheduler 保持待机，不在非 08:30 时间直接触发外发。
3. 将旧 `telegram-listener` 证据目录在同一文件系统重命名为带时间戳的隔离目录，再创建权限 0700 的空目录；禁止在验证前直接删除旧证据。
4. 使用 `src.intel.private_env.load_private_env_file/write_private_env_file` 修改非密钥开关，避免 shell 重写时回显或丢失已有 Token。
5. 调用 `initialize_intel_db()` 执行 V0/V2 -> V3 幂等迁移；随后把活跃 Telegram 订阅统一校正为 `08:30 / Asia/Singapore`，保留 daily/weekly 频率。
6. `plutil -lint` 验证 plist 后重新 `launchctl bootstrap` listener；观察心跳、stderr、PID 和证据文件增长。
7. 运行 `packages/clawbot/scripts/intel_runtime_health.py`。`database_quick_check`、listener 文件/体积门必须为真；六源和 7 日 SLI 初次部署可为 warmup。

### 验收查询

```bash
cd /Users/blackdj/Desktop/OpenEverything/packages/clawbot

.venv312/bin/python scripts/intel_runtime_health.py \
  --db data/intel_brief.db \
  --listener-evidence-dir data/intel_evidence/phasefix/telegram-listener

sqlite3 -readonly data/intel_brief.db '
PRAGMA quick_check;
PRAGMA user_version;
SELECT max(version) FROM schema_migrations;
SELECT count(*) FROM telegram_media_assets WHERE invalidated_at IS NULL;
'
```

预期：`quick_check=ok`、`user_version=3`、最大迁移版本 3、listener heartbeat 小于 120 秒、新目录不超过 2000 文件/100MB。首次真实图片投递前媒体资产可以为 0；首次投递后应出现 active `file_id`，次日同 Bot/同封面不新增 key。

### 回滚

1. 停止 listener，将当前数据库和证据目录重命名为 `.failed-<timestamp>`。
2. 从部署前 SQLite `.backup` 恢复数据库，恢复部署前私有环境副本和旧证据目录。
3. 重新 bootstrap listener，验证 heartbeat 和 `PRAGMA quick_check`。
4. 旧 791MB 级证据隔离目录只在 V2 首次真实投递、次日媒体复用和运行健康均通过后删除；这是运行冗余，不进入 Git。

安全边界：整个过程不打印 Bot Token、API Key 或完整 chat id；健康证据只记录布尔值、计数、哈希和稳定错误类型。

### 2026-08-04 本机实装记录

- 部署时间：2026-08-04 04:36-04:48 Asia/Singapore；回滚目录为 `.openclaw/backups/intel-brief-v2-20260803T203601Z`，数据库、私有环境和旧 listener plist 均已备份，文件权限统一为 0600，SQLite 回滚副本 `quick_check=ok`。
- 数据：生产库 `user_version=3`、迁移版本 3、`quick_check=ok`；1 个 active Telegram 订阅的偏好已规范为 `08:30 / Asia/Singapore`，原订阅状态和语言偏好保留。
- listener：LaunchAgent 已重装并显式携带 `--lock-file ~/.openclaw/locks/intel-brief-telegram-listener.lock`；锁文件 0600、单进程运行、heartbeat 小于 120 秒，新证据目录通过 2000 文件/100MB 硬门。
- 翻译：生产开关已启用，CC Switch 只读探针确认 3 个 HTTPS 端点可用；未配置私有素材会话，符合“首位收件人种缓存”的方案 C 合同。
- Telegram：真实 `sendPhoto` 上线验收成功，返回 message id 和 photo `file_id`，并把候选 3 封面种入 `telegram_media_assets`；验收过程未建立每日投递 claim，不会吞掉 08:30 的正式简报。
- 健康：`runtime_health.py` 返回 `ok=true`、`hard_failures=[]`；数据库、listener 心跳、文件数和体积均通过。六源 coverage 与 7 日周期/投递 SLI 尚未完成自然采样，继续显示 `warmup`。
- 清理：旧 listener 证据目录约 202,726 个文件、810,904 KiB，在新 listener、数据库备份和真实图片验收通过后已删除；回滚所需的数据库、环境和 plist 小型副本继续保留。
- 本机提示：用户所见“CC中转”通知来自 `ai.openclaw.xianyu` 进程中 `xianyu_admin.py` 的 macOS `osascript` 运营提醒，不是 CC Switch。已在 Git 忽略的 `packages/clawbot/config/.env` 设置 `CC_XIANYU_OPS_NOTIFY_ENABLED=0` 并通过 SIGUSR1 热加载；闲鱼进程继续运行，后续观察无新通知进程。CC Switch 数据库已恢复原配置，未关闭 Provider、密钥、路由或用量记录。
