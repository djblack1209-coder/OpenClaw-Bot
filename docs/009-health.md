# 系统健康状态

> 合并自原 060-health.md + 063-learnings.md + 064-feature-requests.md

---

## 全维度审计与软件闭环目标（2026-08-05）

### Destination

目标：对 OpenEverything/OpenClaw 完成功能、架构、并发、安全、供应链、测试、发布、灾备、运维和用户可感知体验审计；持续修复并验证所有可在软件侧闭环的问题。最终只保留必须由资产所有者完成的硬件/账号续费、平台凭据、真实付费或不可逆生产操作。

完成标准：本地 CI、聚焦回归、安全门、容器冒烟、桌面构建、真实本机备份与恢复演练均有新证据；`HEALTH`、注册表、运维手册、CHANGELOG 和发布证据互相一致；健康检查不把关闭能力或历史失败伪装成当前故障/成功。

### Notes

- 用户授权按产品经理视角补全模糊需求并主动执行；资金、真实外部消息、商户支付、第三方凭据轮换和公开发行签名仍遵守不可逆操作边界。
- 本轮使用 mattpocock/skills 的 `wayfinder` 管理目标与前沿，使用 `to-tickets` 把审计发现登记为下表 HI 项，使用 `improve-codebase-architecture` 与 `codebase-design` 形成源码证据和渐进式架构方案。
- 上游技能默认建议创建 `CONTEXT.md` 和分层文档，但本仓库硬规则只允许 `docs/` 根目录编号文档，因此目标地图合并到本文件，架构可视化保留为本机验收产物，不制造第二套事实源。

### Decisions so far

- 优先级固定为：资金/身份/履约安全 > 数据可恢复 > 并发与事件循环正确性 > 供应链可复现 > 架构深度 > 视觉与文档。
- 采用渐进迁移而非大重写：Frist 把持久化事务深模块化；闲鱼把运行对象收口为不可变快照和纯投影；`api/rpc.py` 冻结为兼容门面，新行为继续进入领域 router。
- 关闭功能不是故障：G4F、Kiro、Ollama、IBKR 和 VPS heartbeat 只有显式启用后才进入健康红灯。
- 本机备份默认落在 `~/.local/share/openclaw/backups`；离机目录只允许 GPG 加密包，绝不向同步盘发布明文密钥或 Cookie。

### Frontier

| 前沿 | 状态 | 证据 / 下一步 |
|---|---|---|
| 软件审计发现 | 已闭环 | HI-965 至 HI-978 均有代码、聚焦测试或实机证据；最终全量数字以 `docs/086-release-evidence.md` 为准。 |
| 每日备份 | 已实装 | `ai.openclaw.daily-backup` 已加载；每天 03:30 执行一致性备份后强制 restore drill，首次实机运行退出 0。 |
| Intel Brief 旧库迁移 | 已修复，待自然确认 | 真实数据库已先备份再升级到 schema v4；旧 `event_key` 缺列回归已关闭。为避免提前发送真实 Telegram 消息，08:30 定时任务只重新加载，首次自然运行前健康状态保持黄色。 |
| 长期 SLI | 自然观察 | HI-933 的 7 日可用率/投递率必须由时间积累，系统自动记录，不需要老板手工操作。 |
| 外部资产 | 仅剩老板边界 | 离机 GPG 公钥/同步目标、第三方历史凭据轮换回执、Developer ID/公证、真实商户或闲鱼小额单均不能由代码伪造。 |

### 2026-08-07 OpenEverything 单主实例收口

| 编号 | 分类 | 严重度 | 状态 | 当前结论 |
|---|---|---|---|---|
| HI-982 | `BUG/INFRA` | 🟠 重要 | 线上已关闭 | 腾讯云旧 ClawBot 备用实例依赖约 109 天未更新的主心跳，每 30 秒重复尝试提升，但备用进程因缺失 Python 模块持续失败，既不能接管又消耗共享小机器资源。已先备份 service/timer/脚本/状态，再停用 `clawbot.service` 和 `clawbot-failover.timer`。Mac LaunchAgent 仍是唯一活跃主实例且未重启；腾讯云微信接收、云控和 SillyTavern 保持 active，三个公网业务探针均为 200。VPS 自动接管只有在实时心跳、单主隔离、回滚和真实 Telegram 验收同时具备后才可重新启用。 |

### 2026-08-07 CC中转切换为干净 Sub2API 底座

| 编号 | 分类 | 严重度 | 状态 | 当前结论 |
|---|---|---|---|---|
| HI-983 | `DEPLOY/SECURITY` | 🟠 重要 | 线上已关闭 | 旧主站 New-API 运行库、上游 Key、用户/Token/渠道/日志和回滚副本已按老板要求清理；Oracle 主站当前为基于官方 Sub2API `v0.1.172` 固定提交构建的 `v0.1.172-jiyu.5`，只绑定 loopback `18080`，PostgreSQL/专用 Redis 均为独立实例。自动更新只检查不覆盖 JIYU 补丁，显式构建发布带完整备份、健康检查和失败回滚。 |
| HI-984 | `INFRA` | 🟡 一般 | 线上已关闭 | 旧 R2 备份脚本原先强制备份 `one-api.db`，会在清理后失败或重新制造旧底座副本；已移除该来源，删除 19 个旧 R2 对象，重新生成只含 `runtime.json` 与 `application.env` 的加密回程备份。Sub2API 自己由 `sub2api-backup.timer` 每日做 PostgreSQL 一致性备份。 |
| HI-985 | `DEPLOY/AI_POOL` | 🟡 一般 | 内测可运营，持续观测 | 渠道A与渠道B各 5 个文本专用 Key，加上 2 个生图专用账号；12 个分组、12 个一对一渠道和 12 条监控已建立。文本用户倍率相对当前上游倍率绝对增加 `0.05x`；生图按上游每张价格绝对增加 `0.05`。监控统一为 300 秒和 ±30 秒，页面如实并列显示正常、降级和错误，不用静态绿灯覆盖故障。 |
| HI-986 | `FRONTEND/SECURITY` | 🟡 一般 | 线上已关闭 | 登录条款、邮箱验证码和邮件模板已品牌化；创建密钥按 Claude/OpenAI 分组显示正确端点并默认导入 CC Switch。首页、标题、版本徽标和管理员菜单已清理可见上游品牌/仓库残留，生产真实重载确认生效。 |
| HI-987 | `BUSINESS/COMPLIANCE` | 🟠 重要 | 外部平台阻塞 | 链动小铺明确禁止代理类服务。店铺资料和 7 档 JIYU 商品草稿已完成，但全部保持下架、零库存，未绕词上架、未执行 ¥1 真实购买，充值中心也未写入不可购买链接。需平台书面确认允许的商品类型后才能继续发布和支付闭环。 |
| HI-988 | `OPS` | 🟠 重要 | 持续观测 | 10 条真实监控当前存在上游错误与降级样本，这是线路真实状态而非前端故障。正式售卖前需逐条恢复或制定对用户透明的降级策略；禁止直接改状态为绿色。 |
| HI-989 | `SECURITY/ARCH_LIMIT` | 🟡 一般 | 方案待实施 | 当前 CC Switch 官方导入协议仍把新建 Key 作为本机深链参数传递；虽然只发往本机应用，仍可能进入浏览器历史或系统日志。建议后续改为同域一次性导入票据，并在 JIYU Switch 中默认开启用量查询和本地路由转发。 |
| HI-990 | `BUSINESS` | 🟠 重要 | 库存阻塞 | 闲鱼/CC readiness v2 已如实返回 10×10 合同，但自动发货仍暂停且可用兑换码库存为 0，正式售卖门保持关闭。补库存、恢复 owner-loop 并完成真实小额同单验收前不得公开售卖。 |
| HI-991 | `PERF/QA` | 🔵 低优先 | 待补证据 | 当前 Chrome 接管接口不能设置精确视口，已完成真实窗口和历史 390×844 证据复核，但本轮无法从同一登录态重新生成 1440×1000/390×844 双主题全页面截图。另有 Vite 原有大分包警告，暂未观察到明显交互卡顿。 |
| HI-992 | `SECURITY` | 🟠 重要 | 方案待实施 | 生产 CSP 已启用 nonce、`frame-ancestors 'none'` 和 `form-action 'self'`，但 `connect-src https:` 与 `img-src https:` 仍允许任意 HTTPS 目标；同时未返回 HSTS 和 Permissions-Policy。收紧前需先盘点支付、验证码、对象存储和 OAuth 真实域名，采用 report-only 观察后再切强制策略，避免直接中断登录或支付。 |
| HI-993 | `OPS` | 🟠 重要 | 业务确认待办 | 8 条运维告警规则已启用，SMTP 与到期提醒已配置，但余额不足和账号限额通知当前关闭，通知邮箱列表为空。建议以管理员邮箱作为首个收件人并设置去重/静默窗口后再启用，避免直接打开造成邮件轰炸。 |
| HI-994 | `DEPLOY/ARCH_LIMIT` | 🟠 重要 | 本地已实现，生产待发布 | 官方 WebUI 自更新会覆盖 JIYU 定制，且旧 Apache 拦截把错误截成 `status c`。现已实现 CI 兼容包、SHA-256/大小清单、固定域名 root-only 下载代理、最小 sudoers、原子暂存与独立 systemd 运行哈希/健康验证；失败或 10 分钟未重启会恢复二进制、VERSION 和 PostgreSQL。当前生产 `v0.1.172-jiyu.5` 仍安全失败关闭，需先发布首个兼容包并部署带新后端的构建，再启用真实按钮闭环。 |
| HI-995 | `AI_POOL/BUSINESS` | 🟠 重要 | 渠道已建，上游阻塞 | 两个匿名生图分组、账号、渠道和 300±30 秒监控均已建立，仅开放 `gpt-image-2`。渠道A按上游 `0.05/张` 定价 `0.10/张`，真实调用返回 `502 Upstream access forbidden`；渠道B高质量组按 `0.07/张` 定价 `0.12/张`，专用 Key 返回 `401 invalid token`。不得在上游修复前伪造绿色或公开售卖。 |
| HI-996 | `BUG/SECURITY` | 🟠 重要 | 本机运行时已重建，专用站内 Key 待创建 | 已删除 CC Switch 中两个指向缺失脚本的旧条目，安装基于官方 MCP SDK `1.30.0` 的 `jiyu-ai-image` stdio MCP，并同步 Claude、Codex、OpenCode；该版本修复 `1.29.0` 传递依赖的中危路径穿越公告，生产依赖审计为 0。MCP 只允许 JIYU 固定域名、单图、20 MiB 上限且付费 POST 不自动重试；当前钥匙串未配置站内生图专用 Key，因此失败关闭，待上游 502/401 修复后做一次真实单图验收。 |
| HI-997 | `SECURITY` | 🟠 重要 | 已降至 9 项，继续分组审计 | 本次 main 推送的 GitHub 回执从 31 项降为 9 项（2 high、7 moderate）；随后合并 `h2 4.4.1` 与 `pypdf 6.15.0` 两条双平台哈希锁安全更新。剩余项仍需按生产运行时/开发时分组确认，禁止为了清零数字直接升级生产底座。 |
| HI-998 | `FRONTEND/BUG` | 🟡 一般 | 本地已关闭，生产待发布 | 管理端监控表已按渠道A后渠道B排序，但真实用户“渠道状态”卡片仍沿用 API 顺序而混排。现已抽取共享比较器供管理端和用户端复用，顺序固定为渠道A全部产品（生图最后）后接渠道B；聚焦用例锁住该合同，待新 JIYU 构建上线后截图复验。 |
| HI-999 | `CI/BUG` | 🟡 一般 | 本地已关闭，待远端复验 | 首次兼容包 CI 因补丁生成未纳入两个未跟踪的共享排序器新文件而类型检查失败；主 CI 同时发现生图安装器 `SC2155` 和闲鱼预检未使用变量 `F841`。补丁已包含新文件，Shell 声明已拆分，未使用读取已删除；只重跑对应类型、ShellCheck 和 Ruff 门。 |

| 编号 | 分类 | 严重度 | 状态 | 当前结论 |
|---|---|---|---|---|
| HI-965 | `SECURITY` | 🔴 阻塞 | 本地已关闭 | 通用 HTTP 客户端和浏览器链路曾可被 DNS 重绑定、重定向或子资源绕过 SSRF 限制；现逐跳解析并固定已验证地址，浏览器主文档、子资源和 WebSocket 均按精确主机拦截，相关组合回归通过。 |
| HI-966 | `SECURITY` | 🟠 重要 | 本地已关闭 | Frist 邮箱验证、重置、2FA、会话和限流存在可枚举、容量或持久令牌风险；现会话只存 SHA-256 指纹，重置/2FA 叠加账号与 IP 桶，限流表满时失败关闭，公共占位配置不再伪装可用。 |
| HI-967 | `SECURITY` | 🟠 重要 | 本地已关闭 | 闲鱼管理页曾把根 Token 暴露给浏览器持久存储并允许宽松脚本渲染；现根 Token 只换取 15 分钟、最多 128 个随机 HttpOnly 会话，写请求同源校验，逐响应 nonce CSP，动态内容只走 DOM `textContent`。 |
| HI-968 | `ARCH_LIMIT` | 🟠 重要 | 本地已关闭 | 闲鱼管理线程曾直接读取 owner-loop 内实时对象，三套运营摘要重复组合同一事实；现 owner 只导出普通不可变快照，`operations_projection.py` 一次生成售卖、循环观察和买家进度投影，运行对象输入固定拒绝。 |
| HI-969 | `BUG` | 🟠 重要 | 本地已关闭 | Bot 运行状态与自动健康脚本曾把进程存在或 LaunchAgent 已加载误报为服务健康；现必需服务同时验证 `running + PID + 真实端点`，可选能力按显式开关区分 disabled 与 bad。 |
| HI-970 | `SECURITY` | 🟠 重要 | 本地已关闭 | 日志脱敏曾只处理参数而遗漏最终渲染文本、异常源码行和文件权限；现最终 record、异常链和落盘路径统一清洗，目录 0700、日志 0600。 |
| HI-971 | `SECURITY` | 🟠 重要 | 本地已关闭 | API 限流曾无条件信任代理头且状态表可无界增长；现只信显式可信代理链，所有桶有硬容量上限，容量耗尽拒绝新桶。 |
| HI-972 | `SECURITY` | 🟠 重要 | 本地已关闭 | CLIAnything 管理 API 曾可从远端请求触发动态 pip 安装；现远程安装入口永久 403，桥接器不再启动 pip 子进程，只允许预装且注册的适配器。 |
| HI-973 | `SECURITY` | 🟠 重要 | 本地已关闭 | npm/Python/Rust/Docker 工件存在旧漏洞或不可复算安装面；现直接依赖与 override 升级到零已知高危组合，Linux/macOS Python 哈希锁、354 包 npm 锁、固定镜像 digest 和 RustSec 审计全部进入门禁。 |
| HI-974 | `TECH_DEBT` | 🟠 重要 | 本地已关闭 | PR CI 曾只覆盖主分支且缺 ShellCheck、Gitleaks、完整依赖/供应链和 cargo audit；现所有 PR 目标分支执行只读权限、固定 Action SHA 和本地同构安全门。 |
| HI-975 | `SECURITY` | 🟠 重要 | 本地已关闭 | 主容器曾允许平台/源码根定位漂移，依赖安装也不能证明来自哈希锁；现固定 amd64 构建平台、哈希锁安装和非 root 用户，容器内 API store 根定位有回归，完整镜像构建与导入冒烟通过。 |
| HI-976 | `BUG` | 🔴 阻塞 | 本机已关闭 | 旧备份只是文件复制，活动 SQLite、半成品、路径穿越、明文同步盘和不可恢复包均可能被误当成功；现在线 `.backup`、双层 SHA-256、原子 `.ready`、安全 tar、SQLite quick_check、GPG 离机加密、恢复 drill 和每日 LaunchAgent 全部闭环。 |
| HI-977 | `BUG` | 🟠 重要 | 本机已关闭 | Intel Brief 生产库停在 schema v3，`content_delivery_attempts` 缺 `event_key`，导致 2026-08-04 定时投递崩溃；现 schema v4 原子重建并保留旧投递记录，真实库备份/quick_check/迁移成功，旧库红绿测试与 37 项链路回归通过。 |
| HI-978 | `ARCH_LIMIT` | 🟡 一般 | 本地已关闭 | Frist 原子文件写、串行 mutation 和敏感字段加密曾继续占据 HTTP 巨型入口；现集中到 `server/runtime-store.js`，入口只注入数据规范化边界，直接合同 `3/3`、Frist 全量 `234/234`。 |
| HI-979 | `SECURITY` | 🟡 一般 | 外部凭据待办 | 离机备份已经强制 GPG，但本机尚未配置用户选择的公钥指纹和真正独立的同步/远端目录；缺任一项时 `--require-offsite` 固定失败，当前只保留本机加密权限边界内的备份。 |
| HI-980 | `TECH_DEBT` | 🔵 低优先 | 上游隔离 | New-API 子模块未部署的 Electron dev 依赖仍有上游审计告警，三个参考 MCP server 已 deprecated；生产 Go 容器和受管 npm runtime 审计为 0，旧包只读展示、不执行。替换需跟随上游方案，不在本轮伪造重写。 |
| HI-981 | `BUG` | 🟠 重要 | 已关闭 | 首次推送后的 Linux CI 暴露三处本机未触发的兼容问题：健康脚本 heredoc 组合写法在 Linux Bash 解析失败并触发 ShellCheck SC2015，Node 24 在后台巡检最后一次原子写期间清理测试目录会偶发 `ENOTEMPTY`，文档门禁假设 CI 预装 `rg`。现健康巡检使用明确子 shell 并始终产出可解析失败 JSON，测试夹具对已停止服务的在途文件写执行有限重试，文档门禁在无 `rg` 时回退到 `grep`；Linux 容器聚焦回归和远程 CI 用于锁定跨平台合同。 |

## 全维度 8 分目标整改（2026-08-04，历史基线）

当前结论：审计确认的 P0 已全部关闭，影响当前 macOS 单机 + Oracle 内测拓扑的 P1 已修复、失败关闭或以可核验证据降级为 P2。实盘卖出、闲鱼并发履约、生产管理面鉴权、旧事件循环关闭、Frist 外部 I/O 写队列和桌面异版本回滚已追加红绿回归；最终全量数字和五维二元评分以 `docs/086-release-evidence.md` 为唯一事实源。

| 编号 | 分类 | 严重度 | 状态 | 当前结论 |
|---|---|---|---|---|
| HI-934 | `SECURITY` | 🔴 阻塞 | 本地已关闭 | 支付宝缺少平台公钥时曾仍显示就绪且异步通知跳过验签；现要求完整公私钥配置，通知无公钥固定失败关闭。旧代码安全用例 `0/2`，修复后支付宝聚焦链路 `4/4`。 |
| HI-935 | `BUG` | 🔴 阻塞 | 本地已关闭 | Portfolio 曾单击即提交整仓 MKT 卖出，并把 HTTP 200 的 `success=false` 误报为成功；现增加危险操作复核、同步防重复锁和严格业务结果校验，危险框默认聚焦取消。桌面合同红绿通过，桌面/移动截图无溢出。 |
| HI-936 | `SECURITY` | 🟠 重要 | 本地已关闭 | 闲鱼单次放行票曾以无锁 JSON 读改写，并在状态缺失/损坏时默认恢复发货；现使用跨进程事务锁、原子替换和失败关闭。旧代码并发实测一张票可成功消费 5 次，修复后只允许 1 次。 |
| HI-937 | `SECURITY` | 🟠 重要 | 本地已关闭 | Frist 曾无条件信任最左侧 `X-Forwarded-For`，密码重置确认只有 IP 限流且限流表无容量边界；现默认只信 socket 对端，仅对显式可信代理从右侧解析链路，重置确认叠加账号 HMAC 桶，限流表满时拒绝新桶。旧代码三项安全用例 `0/3`，修复后 `3/3`。 |
| HI-938 | `SECURITY` | 🟠 重要 | 本地已关闭 | WebSocket 在未配置 Token 时曾无条件放行，和 HTTP 的生产/外网失败关闭策略不一致；现 HTTP/WS 共用同一判定，`production`、`prod` 或非本机绑定均拒绝，仅本机开发模式可无 Token。 |
| HI-939 | `SECURITY` | 🟠 重要 | 本地已关闭 | Frist 管理员根令牌曾长期写入 `localStorage`；现只保存在页面内存，刷新或关闭页面即失效，所有管理操作统一从当前密码框捕获，不再写浏览器持久存储。 |
| HI-940 | `BUG` | 🟠 重要 | 本地已关闭 | 隔夜取消的 BUY 单曾默认加入队列并在次日自动提交，绕过自动交易默认关闭与人工确认；现默认关闭重挂，且显式开关和 `AutoTrader.auto_mode=true` 缺一不可。 |
| HI-941 | `BUG` | 🟠 重要 | 本地已关闭 | Intel Brief runner 返回 `failed/partial_failed` 时曾仍写入当天已运行，导致全天漏发；现只有明确 `status=success` 才封存日期，失败结果保留后续调度重试机会。 |
| HI-942 | `SECURITY` | 🔴 阻塞 | 本地已关闭 | 支付回调曾只验签和金额，不绑定本机 `appid/mchid`、订单原渠道与平台交易号唯一性；现商户身份、渠道、订单状态、交易号和金额缺一即拒绝。错误微信 App ID/商户号、错误支付宝 App ID、手工订单渠道错配和跨订单复用交易号均保持未入账。 |
| HI-943 | `SECURITY` | 🟠 重要 | 本地已关闭 | 微信渠道曾可生成付款二维码但缺平台公钥时无法验签履约；现平台公钥进入统一就绪条件，配置不完整固定返回 503，不允许客户先付款。 |
| HI-944 | `SECURITY` | 🟠 重要 | 本地已关闭 | 桌面安装器和 MCP 曾只固定 npm 版本号，传递依赖与下载内容未锁；现内嵌 lockfileVersion 3 的 354 包 SHA-512 图，统一执行 `npm ci --ignore-scripts`，MCP Store 只从类型化注册表展示锁内目录，不伪装 stdio 启停。版本只从内嵌 manifest 读取，Rust 不复制版本字符串。OpenClaw 稳定版因高危传递漏洞被拒绝，当前精确锁到审计为 0 的 `2026.7.2-beta.7`，并保留桌面回滚副本。 |
| HI-945 | `SECURITY` | 🟠 重要 | 本地已关闭 | 两个 GitHub 工作流的 16 个 Action 曾使用可移动主版本/分支标签；现全部固定 40 位 commit SHA，写权限只留在 New-API 同步 job，checkout 不持久化写凭据；静态门会拒绝任何新可移动引用。 |
| HI-946 | `BUG` | 🟠 重要 | 本地已关闭 | Scheduler 切换曾漏传目标状态，Store 同时维护第二份插件事实，Assistant 停止按钮不能中止流；现后端确认目标状态、Store 读取 Tauri MCP 配置、Assistant 使用 AbortController 保留已接收内容。调度异常字段不再击穿整页。 |
| HI-947 | `ARCH_LIMIT` | 🟠 重要 | 本地已关闭 | Brain、EventBus、SocialAutopilot、IBKR、闲鱼、WebSocket 推送、CLI bridge、LiteLLM Router 和 resilience primitive 曾可跨事件循环复用；现显式绑定所有者循环，停止/提交竞态失败关闭，loop.close 前取消并排空已启动任务，未就绪返回 503/504，API 在交易/调度状态服务就绪后才监听。 |
| HI-948 | `TECH_DEBT` | 🟠 重要 | 本地已关闭 | Python 曾无可复算平台锁，CI 缺前端 lint/build、关键覆盖率、文档真实性和供应链门；现 Linux/macOS 双哈希锁可复算，总覆盖率门 40%，高风险聚合门 80%，逐文件下限、Action SHA、npm/Python 审计和文档事实检查均进入本地/远端 CI。 |
| HI-949 | `TECH_DEBT` | 🟡 一般 | 持续收窄 | Frist 的支付、会话/CSRF、限流、共享规则和 runtime store 已下沉，`server.js` 当前 7,943 行；闲鱼运营纯投影下沉后 `xianyu_admin.py` 为 5,557 行。`api/rpc.py` 冻结为兼容门面，其余热点继续按域渐进拆分，不以一次大重写冒险。 |
| HI-950 | `TECH_DEBT` | 🔵 低优先 | 已降级 | 三个旧 MCP server 包已被上游标记 deprecated；桌面 Store 已明确降级为受管目录只读展示，不声称建立 stdio 会话。真实 MCP 仍需用户通过 CC Switch/OpenClaw 官方配置链显式启用，版本与传递工件保持锁定且 npm audit 为 0。 |
| HI-951 | `ARCH_LIMIT` | 🔵 低优先 | 已降级 | OpenClaw 当前安全工件是精确 beta 版本，不作为公开发行承诺；其 CLI 版本、gateway token/password、配置校验和插件枚举已在干净 HOME 冒烟通过。新稳定版只有在完整性锁、0 高危审计和同组回归全绿后才可替换。 |
| HI-952 | `SECURITY` | 🟠 重要 | 本地已关闭 | 微信/支付宝下单曾接受未验平台签名的 HTTP 200 响应，可能把伪造二维码交给客户；现外部请求硬超时、订单总额字段优先于折扣展示字段，微信校验时间戳、nonce、平台序列号和原始响应 RSA-SHA256，支付宝校验响应 `sign`，缺失、过期、序列号不符或验签失败均返回 502。重复成功回调不重复追加事件。 |
| HI-953 | `SECURITY` | 🟠 重要 | 本地已关闭 | Frist 辅助模块曾保留可接受 `enc:v1:` 占位 API Key、绕过 2FA 的管理员接口以及弱化的代理头、流式断连和 SLA 实现；现加密占位值固定拒绝，旧接口和零调用重复事实源已删除，并由 8 项安全合同防止回归。 |
| HI-954 | `SECURITY` | 🟠 重要 | 本地已关闭 | MCP Store 曾读取用户旧配置并把凭据带入 WebView 日志，且空配置可能伪装成可用 stdio；现目录 DTO 不包含 command/args/env，桌面只展示受管注册表，不读旧配置、不启动子进程，Rust/TypeScript 静态合同锁住该边界。 |
| HI-955 | `SECURITY` | 🟠 重要 | 本地已关闭 | 充值路由曾在全局写队列内等待外部支付渠道，渠道挂起会阻塞所有订单；现采用准备事务 → 外部请求（硬超时）→ 成功/失败落库的两阶段流程，并保留支付入账竞态合同。 |
| HI-956 | `TECH_DEBT` | 🟡 一般 | 本地已关闭 | 供应链门曾允许 Compose 只写可移动 tag、临时安装复用本机缓存，且桌面构建可能在备份失败时先删旧 App；现镜像固定 tag+digest、干净临时目录安装门和备份就绪闸门均有自动化回归。 |
| HI-957 | `ARCH_LIMIT` | 🟡 一般 | 本地已关闭 | Bulkhead 动态重配曾替换 semaphore，旧持有者与新对象可叠加突破并发上限；现原位调整容量并以持有期间重配测试锁定上限。 |
| HI-958 | `ARCH_LIMIT` | 🟡 一般 | 本地已关闭 | SocialAutopilot 关闭路径曾遗漏 APScheduler 和 owner 引用；现主循环关机阶段调用 owner-only `close()`，释放调度器和循环引用但保留持久化意图。 |
| HI-959 | `BUG` | 🟠 重要 | 本地已关闭 | 实盘 SELL 的 LMT 缺价格曾静默退化为市价单，且接口把 Cancelled/Inactive/零成交 Filled 误报成功，也未核对真实可卖持仓。现未知订单类型和无价格限价单失败关闭，SELL 在所有者循环内串行核对真实持仓、未完成卖单和本地保留量；只有券商明确接收或正成交量才返回成功。 |
| HI-960 | `SECURITY` | 🟠 重要 | 本地已关闭 | 闲鱼消息缺真实订单标识时曾用包含时间戳等易变字段生成履约键；同一付款事件并发到达时主 webhook 仍可能双发，暂停分支还能覆盖已发送状态。现只接受真实订单/交易 ID，无法证明唯一性即不发；webhook 分配、轮询复用、人工发送均先原子领取，发送异常进入不可自动重试的不确定态，终态禁止被暂停覆盖。 |
| HI-961 | `SECURITY` | 🟠 重要 | 本地已关闭 | 闲鱼管理面曾只识别 `ENV=production`，并用配置主机而非实际监听地址判断外网，`ENV=prod` 或实际外网绑定存在无 Token 放行风险。现 `prod/production` 与实际 bind host 统一进入失败关闭，HTTP/WS 共用边界。 |
| HI-962 | `ARCH_LIMIT` | 🟠 重要 | 本地已关闭 | 旧 owner loop 的 close guard 曾在对象已重绑新循环后仍设置全局关闭标记并清空新 owner。现只回收属于正在关闭循环的任务，且仅当该循环仍是当前 owner 时更新关闭状态；重绑竞态有专门回归。 |
| HI-963 | `ARCH_LIMIT` | 🟠 重要 | 本地已关闭 | Frist 注册/重置邮件、补货探测、渠道巡检、上游余额和 Token 外部调用曾可占用全局 runtime 写队列。现普通 `mutate` 拒绝 Promise，外部 I/O 均在队列外执行并以短事务准备/落库；生产禁止本地旧网关兼容链，重置邮件另有账号级 3 次/15 分钟限流。 |
| HI-964 | `BUG` | 🟠 重要 | 本地已关闭 | 桌面重复构建会把同一 CDHash 同时保存为当前版和“上一版”，`rollback_ready=true` 不能证明可回退。现清单要求当前/上一版指纹不同，记录源码补丁与 DMG SHA-256；0.1.1/0.1.0 已真实双向交换，同指纹自动化用例固定拒绝。 |

### 五维最终评分

| 维度 | 分数 | 复核证据 | 保留边界 |
|---|---:|---|---|
| 功能完整度 | 9.0 | 10 项二元门通过 9 项；支付、实盘交易、闲鱼履约、认证、Scheduler、MCP 目录、Assistant、桌面安装和恢复均有成功/失败合同 | 缺真实商户小额支付验收，F10 计 0 |
| 测试与发布 | 9.0 | 10 项二元门通过 9 项；本地 CI、覆盖率、前端/Rust、干净安装、供应链、签名、DMG、异版本回滚和截图可复核 | 本工作树未在远端 Linux runner 新跑，T10 计 0 |
| 系统架构 | 8.0 | 10 项二元门通过 8 项；所有者循环、事务外 I/O、原子履约、单一注册表和生命周期边界有回归 | Frist/RPC 巨型入口与 JSON runtime 兼容层各计 0 |
| 安全边界 | 8.0 | 10 项二元门通过 8 项；资金、支付、履约、身份、本机执行、限流、供应链和密钥扫描失败关闭 | 历史第三方凭据轮换无平台侧证明、无 Developer ID/公证，各计 0 |
| 可维护性 | 8.0 | 10 项二元门通过 8 项；锁、lint/build、覆盖率、文档门、注册表、热点命令、版本源和回滚清单可复现 | 巨型热点未清零、未取得当前工作树远端 CI 产物，各计 0 |
| **综合** | **8.4** | `(9+9+8+8+8)/5`；逐项定义和命令证据集中在 `docs/086-release-evidence.md` | 评分只覆盖当前 macOS 单机 + Oracle 内测拓扑 |

当前保留边界：Assistant 的“快速/深度/创意”仍只影响界面选中态，后端语义等待产品规格确认；macOS 仍是 ad-hoc 内测签名而非 Developer ID/公证；当前未提交工作树没有远端 Linux runner 新产物；HI-817/818 的第三方平台凭据轮换缺平台侧证明；巨型热点继续按登记的聚焦门拆分。这些均为 P2/明确降级，不开放资金、履约、身份或本机执行旁路。

## 每日资讯 V2 健康基线（2026-08-04）

当前结论：工程发布门为绿色，七个维度均达到 8 分；7 日周期可用率和投递成功率需要从 V2 部署后自然积累，当前标记为 `warmup`，不能写成已达到 95%/99%。下表中的关闭状态均有 345 项 Intel 回归、八阶段本地 CI、同视口视觉证据或真实 Telegram `sendPhoto` 证据；生产实装结果记录在 `docs/007-operations.md`。

| 编号 | 分类 | 严重度 | 状态 | 当前结论 |
|---|---|---|---|---|
| HI-928 | `BUG` | 🟠 重要 | 已关闭 | 旧 2020 BYND、缺失日期、Senate limit-before-sort 和旧 AI 内容可进入简报；现由统一日期契约、全量排序后限额和过期 fail-closed 关闭。 |
| HI-929 | `BUG` | 🟠 重要 | 已关闭 | 跨日重复、同仓库刷屏和首次 GitHub/13F 基线漏拦截；现由 event key、逐订阅者投递状态、GitHub 7 日 entity cooldown、baseline event/entity 水位关闭。 |
| HI-930 | `BUG` | 🟠 重要 | 已关闭 | 并发 production run 可对同一订阅者双发；SQLite V3 使用订阅者+业务日期唯一 claim、15 分钟 lease、过期接管和 token fencing。 |
| HI-931 | `PERF` | 🟠 重要 | 已部署关闭 | 旧 listener 每次空轮询落盘，实机累积约 202,726 个文件、810,904 KiB；新进程只写有意义事件，30 天、最多 2000 文件、5 分钟 idle log，并由 100MB 健康门约束。旧目录已在备份、重载和真实图片验收后删除。 |
| HI-932 | `SECURITY` | 🟠 重要 | 已关闭 | 翻译 Key 仅从 CC Switch 只读加载，最多三个 HTTPS 端点，Key 不写日志/证据/缓存且不进入 endpoint `repr`；用户追踪名回显执行 HTML 转义。 |
| HI-933 | `ARCH_LIMIT` | 🔵 低优先 | 观察中 | V2 的 7 日周期可用率目标 95%、投递成功率目标 99% 尚无完整自然窗口；`runtime_health.py` 会如实返回 warmup，不以单次测试代替长期 SLI。 |

模块评分：内容正确性 9.1、Telegram 体验 8.8、国际化 8.7、可靠性/幂等 8.8、安全 8.9、运维/可观测 8.5、测试/文档 8.8，综合 8.8。评分边界只覆盖当前 macOS 单机、Telegram 内测用户、现有六源和 CC Switch 三端池；不扩大到微信 709、飞书/钉钉实连或长期 SLI。

### V2 仍需自然观察的信号

- 首次真实 08:30 应确认六源 `fresh/cached/failed` 覆盖、Top 3 分类多样性和中文/English 真实投递。
- 真实图片上线验收后 `telegram_media_assets` 已有 1 个 active `file_id`；次日同 Bot/同封面仍需确认不新增资产或重新上传本地文件。
- listener 新目录当前心跳小于 120 秒、文件少于 2000、体积小于 100MB；旧 810,904 KiB 轮询证据已删除，数据库、环境和 plist 回滚副本仍保留。

## P0 安全与正确性整改（2026-08-03）

本轮对 Telegram 控制面、Agent 工具、交易订单、OMEGA 编排、社媒发布、Frist/New-API 多租户、桌面 Gateway、运行时真值和 CI 做了端到端整改。下表状态已按 2026-08-03 本机 Bot/Gateway、macOS App 和 Oracle Frist 实装结果回写；评分边界仍只覆盖当前 macOS + Oracle 内测拓扑。

| 编号 | 分类 | 严重度 | 状态 | 当前结论 |
|---|---|---|---|---|
| HI-913 | `SECURITY` | 🔴 阻塞 | 已部署关闭 | Telegram 白名单空值不再等于公开访问，启动配置 fail-closed；媒体/Inline 入口先鉴权。自动循环不再获得本地文件、Shell、代码执行或记忆写入权限；`/agent` 改为只读 ToolCallingAgent，Bash 禁用 Git，`/claude` 禁止远程提示词进入终端。 |
| HI-914 | `BUG` | 🔴 阻塞 | 已部署关闭 | 自动交易默认关闭；预算同步不突破配置上限也不清零已花金额；零成交、取消、未决和模拟订单不会再伪造真实持仓，退出订单按累计成交量对账。Bot 重启日志确认 IBKR 未启用且没有新重连循环。 |
| HI-915 | `SECURITY` | 🔴 阻塞 | 已部署关闭 | 社媒正文直发和夜间自动发布旁路关闭；只有内容未变化的已审核草稿可签发短时一次性确认。发布中/已发布草稿不可变，外部成功与本地状态冲突会追加对账审计并提示禁止重发。 |
| HI-916 | `SECURITY` | 🟠 重要 | 已部署关闭 | 桌面端移除固定 Gateway Token、WebView 文件权限和 IBKR Shell 配置；管理器新建 Token 使用强随机字符串，OpenClaw 2026.7.1 支持的 Token/密码/远程 SecretRef 原样保留并交由官方校验；WebView 配置/导出递归脱敏且数组内凭据可安全回写，Provider 更新保留 SecretRef 和官方扩展字段；跨实例锁、PID 所有权和日志边界统一。实装 App 已通过严格 ad-hoc sealed 签名与真实首屏验收。 |
| HI-917 | `SECURITY` | 🔴 阻塞 | 生产已关闭 | Frist 对共享 New-API Token 建立客户归属并保护读写/导入/网关代理；人民币分和 New-API units 已分离，创建 Key 使用“本地预留 → 上游零额度暂存 → 归属落盘 → 激活”及失败补偿。Oracle 已配置默认有限额度 7200；历史 Token 1–9 仍全部无限且 owner 为空，dry-run 确认拒绝映射。 |
| HI-918 | `TECH_DEBT` | 🟠 重要 | 本地已关闭 | CI 不再容忍预存失败；Frist、Tauri Rust、桌面安全边界和文档治理均进入必过门禁。 |
| HI-919 | `ARCH_LIMIT` | 🔵 低优先 | 已隔离 | `CodeTool` 使用 RestrictedPython + 受限子进程，不等同容器/内核级沙箱；当前自动 Agent 和 Telegram 不可达。重新开放前应迁移到容器或专用沙箱。 |
| HI-920 | `SECURITY` | 🔵 低优先 | 已隔离 | `FileTool` 的路径预检与实际打开之间存在理论上的本机并发换链竞态；当前自动 Agent 和未授权入口不可达。重新开放写入前应改用 `openat/dirfd` 与 no-follow 原子打开。 |
| HI-921 | `TECH_DEBT` | 🔵 低优先 | 已关闭 | 已对 Tauri Rust 工作区执行统一格式化；`cargo fmt --all -- --check`、34 项 Rust 测试和 `cargo check` 全部通过。 |
| HI-922 | `ARCH_LIMIT` | 🔵 低优先 | 已降级 | 桌面渠道 JSON/env 联合读写在管理器进程内和多个管理器实例间使用同一把锁，普通写入错误会恢复 env 快照；两个独立文件仍不具备断电或强制终止级原子提交，极窄窗口内可能留下跨文件版本差异。当前 env 只承载测试目标 ID，可通过重新保存渠道配置恢复；若未来把凭据迁入该联合事务，必须先改成单一持久化源或增加可恢复事务日志。 |
| HI-923 | `TECH_DEBT` | 🔵 低优先 | 已关闭 | 历史 Bot 日志有 19 条 `Unclosed client session`；2026-08-03 重启后持续到桌面实装完成的日志窗口新增 0 条，同时 IBKR 重连新增 0 条。若未来再次出现，按 client 持有者重新登记，不沿用本次已关闭结论。 |
| HI-924 | `PERF` | 🔵 低优先 | 已关闭 | Frist Node 18 测试夹具过去逐例等待 5 秒 HTTP keep-alive，200 项矩阵显著慢于 Node 24；fixture close 已主动清理空闲与现存连接，不改变生产优雅关闭路径。 |
| HI-925 | `TECH_DEBT` | 🔵 低优先 | 已关闭 | 闲鱼操作台暂停/恢复测试曾读取本机历史库存缓存，导致干净 CI 的首个阻断从“真实小额单严格门”漂移为“库存为 0”；测试已显式注入冷缓存与刷新后状态，生产预检逻辑不变。 |
| HI-926 | `PERF` | 🔵 低优先 | 已降级 | 本机重启时 OpenClaw Weixin 上游通道首次连接约 230 秒后超时降级，期间 Gateway 已监听 18789 但 HTTP 未就绪；进程无 CPU/内存异常，日志随后出现 `gateway ready`，`/health` 恢复约 2ms。部署验收必须等待 ready/HTTP 200，后续升级 Weixin 插件时复测启动耗时。 |
| HI-927 | `BUG` | 🟠 重要 | 已关闭 | 真实 `make tauri-build` 先发现 Rust Tauri `2.11.5` 与 JavaScript API/CLI `2.10.1` 主次版本不一致，修复后又发现无 Apple 身份时 App 资源未 sealed、严格 `codesign` 失败。API/CLI 已对齐到 `2.11.x`，Tauri 官方 ad-hoc `signingIdentity="-"`、构建产物和覆盖前临时安装副本签名门均已生效；旧树合同红灯 2 项、当前 7/7 绿，最终 App 严格签名、唯一安装和真实首屏均通过。 |

上线硬门槛已执行：Oracle 回滚包 `/opt/frist-api/backups/release-gate2-20260803T064021Z` 含 runtime、New-API SQLite 在线备份、源码、环境、Apache/systemd 和哈希；目标机 Node 18 staging 为 `200/200`；systemd 环境已设置 `FRIST_API_NEWAPI_DEFAULT_TOKEN_QUOTA=7200`；`newApiTokenOwners` 对历史 Token 1–9 仍为空且 ownership dry-run 拒绝无限 Token。Apache 主域 `jiyu.245334.xyz → New-API:13000` 未改变，Frist 3180、New-API 13000、两个公网入口和未授权 401 门均已复验。

保留的安全降级边界：券商下单成功与本地订单 ID 落盘之间若进程被强制终止，会留下未绑定预算预留并阻止后续买入；必须先用券商订单记录人工对账或显式重置，系统不会猜测释放额度。社媒外发成功后若磁盘无法落盘，草稿保持 `publishing` 并阻止重发，调用方会收到平台结果和人工对账提示。桌面渠道 JSON/env 已对管理器读写统一加锁并在普通错误时补偿恢复，但强制终止发生在两个文件替换之间时仍需重新保存渠道配置，不能宣称具备跨文件崩溃原子性。

发布验证证据：本地 `make ci-local`、GitHub PR #11 干净环境 5 个 job、Oracle Node 18 staging 和实际部署冒烟均全绿；覆盖 Python `2182` 项收集/0 失败/2 项预期跳过、Frist `200/200`、桌面静态合同 `20/20`、Rust `34/34`、TypeScript/编译和 22 份文档治理。桌面/Frist npm 与项目 Python 3.12 审计均为 0 已知漏洞，gitleaks 无泄漏。Release Gate 2.0 六维评分为架构 8.3、代码质量 8.2、测试工程 8.8、安全 8.6、可靠性 8.3、运维发布 8.4，综合 8.4；六维均达到 8 分，只覆盖当前 macOS/Oracle 内测拓扑。


### 每日简报 / CC中转文档治理 — 已收口

2026-07-10 最终审计发现两处会让后续 AI 继续“越整理越乱”的治理漂移：根目录 `intel-brief-implementation-report.md` 不在唯一文档目录中，`docs/superpowers/` 又违反 `docs/` 禁止子目录规则。现已把历史验收报告归档为 `docs/084-intel-brief-implementation-report.md`，在顶部明确它只代表旧阶段证据；已删除完成任务后不再需要的补充执行计划目录，并把有效内容继续由 `docs/052-intel-brief-master-plan.md`、`docs/084-intel-brief-implementation-report.md` 和当前健康记录承接。新增 `scripts/check_docs_layout.sh` 与 `make docs-check`，自动检查根目录散落文档、`docs/` 子目录、编号命名、索引漏登记和陈旧索引引用，并纳入 `make ci-local`。完整 CI 首轮还发现微信桥证据读取器使用 `datetime.UTC`，会破坏 Intel worker 的 Python 3.10 兼容门；现已改回 `timezone.utc` 并保留 Ruff 兼容说明。验证：`bash -n scripts/check_docs_layout.sh` 通过；`make docs-check` 返回 22 个文档全部合规；Frist-API `npm test` 为 `187 passed / 0 failed`；每日简报/微信相关回归为 `96 passed`；第二轮 `make ci-local` 的 Ruff、Python 全量测试、Python 语法、前端 TypeScript 和 docs-check 全部通过。为建立可维护 Git 基线，New-API submodule 的 5 处品牌改动已保存为 `scripts/patches/new-api-cc-brand.patch`，submodule 恢复到干净的上游 `v1.0.0-rc.4`；后续升级使用 `make new-api-check` 检查补丁兼容，使用 `make new-api-brand-patch` 应用，不再依赖无法从上游拉取的本地 detached commit。`output/` 与 `packages/clawbot/relative-launch/` 已明确列为可再生成本地产物，不纳入源码基线。

### Intel Brief 每日简报入口 — Telegram 已真人闭环，微信编号已接入，飞书/钉钉未真实闭环

2026-07-10 追加每日简报降级体验修复：此前生产推送会把 `partial_fallback / qwen / tokens=0` 等工程状态直接展示给用户，订阅筛选后还会把真实摘要覆盖成“查看下方输入条目”的空提示，并固定只展示前 5 条，造成“筛选 8 条但只看到 5 条”的体验断层。现已改为用户视角的“今日重点 + 精选情报”结构：生产消息隐藏模型/Token/内部状态，降级时只提示“AI 精炼暂时不可用，已切换稳定整理模式”；每位订阅者按过滤后的真实条目生成专属总览，最多完整展示 8 条并对更多条目给出明确说明；标题和摘要执行 Telegram HTML 转义，避免 `<`、`&` 导致发送失败；点击“今日简报”时不再叠加双层标题；没有符合条件的订阅者时返回空成功结果，不再引用未定义消息。验证：`py_compile` 通过；`test_intel_delivery_sandbox.py + test_intel_subscription_filtered_delivery.py + test_intel_telegram_menu_handlers.py` 共 `29 passed`。

2026-07-08 追加微信控制权限深度诊断：`scripts/wechat_control_doctor.sh` 已升级为深度医生，支持 `--deep` 同时检查全屏截图、微信单窗口截图、AX 辅助功能内部控件和输入框数量，并支持 `--open-permissions` 打开 macOS 屏幕录制/辅助功能/自动化权限页。医生现在同时读取 Codex 主程序和 OpenAI Computer Use 辅助进程的屏幕录制授权记录，避免系统设置里漏勾辅助进程。实机结果更精确：`fullscreen_capture_ok=1`，说明系统截图能力可用；但 `window_capture_ok=0` 且错误为 `could not create image from window`，微信主窗口仍为 `kCGWindowSharingState=0`；AX 侧 `ax_content_visible=0`、`ax_editable_count=0`，只能看到标题栏按钮，看不到聊天输入框。结论：当前不是单纯 Codex 没权限，而是微信窗口主动保护/隐藏聊天内容；可以让老板手动补齐 Codex/OpenAI 辅助进程/WeChat/Terminal 屏幕录制权限后重启复测，但在状态转绿前继续禁止坐标盲发，真实微信闭环优先走 OpenClaw Weixin 插件桥证据。

2026-07-08 追加微信入站桥接推进：老板完成 Weixin ClawBot 重连后，本轮把本项目处理器和 OpenClaw 插件桥补到可闭环状态。根因确认：旧转发器习惯打 `/wechat/incoming`，但本机 FastAPI 之前只挂了 `/api/v1/wechat/incoming`，所以旧路径 404；同时 18790 没重启时仍跑旧代码，会把 `700` 当普通聊天丢给 LLM。已修复：`/wechat/incoming` 与 `/api/v1/wechat/incoming` 均可用且仍走 API Token；微信处理器按当前 UTC 时间判断订阅有效期；OpenClaw Weixin 插件实际加载产物已加“每日简报编号菜单直通桥”，授权会话发送 `700-708/菜单/今日简报/我的订阅` 会先调用本项目处理器并直接回微信。复验：本地微信用户旅程脚本 `verified=true`、`passed_steps=12`、`real_wechat_network_calls=0`；live HTTP 两个入口均 HTTP 200 且返回“🧭 今日简报 / 700 今日简报”；OpenClaw Weixin 通道 `enabled, configured, running`。边界：Codex 尝试接管桌面微信发送 `700` 时，系统坐标/焦点不稳定，未成功稳定发到「Global Intelligence AI」，因此不能把“真实微信里已由 Codex 发出 700 并看到回复”写成完成；下一条真实微信消息可作为最终实机入站证据。

2026-07-08 追加微信桌面控制权限诊断：新增 `scripts/wechat_control_doctor.sh` 后复测发现，Codex 并非完全没有控制权限：`System Events` 辅助功能可用，Codex Apple Events 授权存在，WeChat 可被 bundle id 稳定拉到前台，系统也能检测到微信窗口在屏幕上。但微信窗口的 `kCGWindowSharingState=0`，截图和 Computer Use 只能看到白屏/菜单栏，读不到聊天列表和输入框。当前策略改为不做坐标盲点发送，防止误发或重复发；真实微信闭环优先用 OpenClaw Weixin 插件桥和日志证据推进。若必须视觉接管，需要老板先手动关闭微信防截图/隐私保护，或在系统设置中给 Codex 补齐屏幕录制授权后重跑 `scripts/wechat_control_doctor.sh --json`。

2026-07-08 追加微信中文快捷词体验修复：在无法视觉接管微信窗口后，继续从插件桥和本机入口排查真实用户路径，发现 OpenClaw Weixin 插件会把“今日简报/我的订阅”转发到本机，但 `/wechat/incoming` 之前只识别 700/701，中文快捷词会掉入普通 LLM 闲聊；同时用户在 `705` 设置时间过程中回复“菜单”，会被误当作推送时间参数。已修复：微信入口支持“今日简报/每日简报/我的订阅/订阅状态/市场资金/AI科技/天气预警/推送时间/添加追踪/暂停简报”和带参数人话格式；显式菜单/中文快捷词会打断两步式 pending，避免误吃参数；OpenClaw Weixin 插件源码和当前 dist 产物已同步扩展快捷词并重启 Gateway。复验：新增回归 `11 passed`；微信本地用户旅程验收 `verified=true`、`passed_steps=18`；live HTTP 覆盖 `菜单 → 今日简报 → 我的订阅 → 705 → 菜单 → 705 → 2 → 706 → 今日简报 → 706 → 英伟达 → 708 → 701 → 702 → 701` 全部 HTTP 200 且不落 LLM。live 验证临时微信测试用户已从真实库清理。边界不变：这仍证明本机处理器和插件桥就绪，不等于 Codex 已在真实微信窗口里亲自发出消息。

2026-07-08 追加真实微信桥接证据闭环准备：为绕开微信窗口 `kCGWindowSharingState=0` 导致 Codex 无法视觉读取的问题，已把“真实微信入站是否走了每日简报桥”改成插件桥自证据。OpenClaw Weixin 插件桥现在在命中每日简报数字/中文快捷词并成功回发后，会写入 `packages/clawbot/data/intel_evidence/phasefix/wechat-bridge/runtime.json`，只保存快捷词类型、文本长度、sender hash、`/wechat/incoming` HTTP 状态、回复特征和是否已回发微信，不保存聊天原文、原始用户 ID 或 Token。新增 `packages/clawbot/scripts/intel_wechat_bridge_runtime_acceptance.py` 会读取该证据并要求最近一次事件为 `status=handled`、`reason=sent_reply`、HTTP 200、`sent_reply_success=true`、未落 LLM；旧证据、失败证据、未回发证据都会失败。当前 OpenClaw Gateway 已重启，`openclaw-weixin` 仍 `enabled, configured, running`；因本轮没有新的真实微信消息触发，默认验收报告按预期为 `verified=false`，blocker 为“未找到微信桥接证据文件”。下一次真实微信发送 `今日简报` 或 `700` 后，运行该脚本即可形成最终实机入站证据。

2026-07-08 追加等待式真实微信验收：`packages/clawbot/scripts/intel_wechat_bridge_runtime_acceptance.py` 已支持 `--wait-seconds` 和 `--poll-seconds`。后续 Codex 可以先运行 `--wait-seconds 120 --poll-seconds 2`，再让老板在微信里发 `今日简报` 或 `700`，脚本会自动轮询插件桥证据直到 `verified=true`；若超时，会明确输出“等待 N 秒后仍未看到新的真实微信桥接成功证据”。复验：单测扩展为 `5 passed`；本机无真实入站时 `--wait-seconds 1 --poll-seconds 0.2` 返回 `timed_out=true`，边界清晰。

2026-07-08 追加每日简报入口收口：已修复“清理 Telegram 聊天后 `/start` 不回菜单”的根因，新增并加载常驻监听器 `ai.openclaw.intel-brief.telegram-listener`；当前 `launchctl` 显示 running，心跳 `last_status=no_new_updates`，表示机器人正在等新消息而不是只等每天 08:30 定时推送。Telegram `/start` 菜单已改为产品化入口：`700 今日简报 / 701 我的订阅 / 702 市场资金 / 703 AI科技 / 704 天气预警 / 705 推送时间 / 706 添加追踪 / 707 帮助 / 708 暂停简报`，同时保留按钮点击和旧按钮兼容。

2026-07-08 追加真人验收器：常驻监听器心跳现在会保留最近一次 `/start` 菜单发送成功证据，避免成功后又被下一轮“无新消息”覆盖；新增 `packages/clawbot/scripts/intel_telegram_start_menu_acceptance.py`，老板发完 `/start` 后可自动判断 `verified=true/false`。Bot API `getMe` 已确认每日简报机器人是 `@carven_Jianbao_bot`，直达链接 `https://t.me/carven_Jianbao_bot?start=start`；BotCommand 同步证据记录 `command_count=10` 且包含 `/start`。老板本人已在 Telegram 对 `@carven_Jianbao_bot` 发送 `/start`，验收器输出 `verified=true`、`listener_fresh=true`、`blockers=[]`，菜单发送时间为 `2026-07-08T17:44:43.993878+00:00`，inline 按钮菜单和常驻键盘均已发送，共 2 条回复。该验收器不保存聊天内容、chat id、用户 id 或 token。

2026-07-08 追加用户旅程闭环：站在普通用户角度继续验收后，发现“能用”还不是“最好状态”：旧底部快捷键不够直接、旧文字快捷键 `🧭 今日简报` 会重新打开菜单、`708 暂停简报` 路由未接全、`/schedule 09:00` 会被误解析。本轮已修复：底部常驻键盘改为 `🧭 今日简报 / 📌 我的订阅`；`🧭 今日简报` 和 callback `today` 都会返回最近一次成功简报；`708` 可暂停且 `/start`/`701` 不会偷偷恢复；只有重新选择内容或添加追踪才恢复；`/schedule 09:00` 可正确设置每天 09:00。新增 `packages/clawbot/scripts/intel_telegram_user_journey_acceptance.py`，本地临时库验收 `/start → 今日简报 → 我的订阅 → 改时间 → 添加追踪 → 暂停 → 暂停后查询/打开菜单 → 选择内容恢复`，当前输出 `verified=true`、`passed_steps=9/9`、`real_telegram_network_calls=0`。

本机真实库当前有 1 个 Telegram active 订阅者，偏好为 `ai_model_updates`、`akshare`、`senate_trading`，`delivery_log` 最近一次真实 Telegram success 为 2026-07-08；测试过程中误写入的微信测试用户、临时市场/GitHub偏好和“英伟达”追踪已清理。微信端代码已接入 700-708 数字回复，`700` 打开每日简报，`706 英伟达` 添加追踪，且测试覆盖不落 LLM 兜底；但未做真实微信转发器/公众号端实机验收，不能写成“微信真实闭环”。飞书/钉钉当前只有统一菜单合同和数字命令协议，没有真实 webhook/token/回调入口，不能写成“已完成”。

本轮使用过程审计发现的问题与处理：1）旧菜单像配置表，不像用户菜单，已改成 8 个高频入口；2）只有定时推送没有常驻监听，清聊天后 `/start` 无人处理，已补常驻监听；3）不能点击菜单的平台需要数字编号，已补统一 700-708 协议并接入微信代码；4）`700 今日简报` 只弹菜单不够像“今日简报”，已改为优先返回最近成功投递内容；5）真实平台测试必须和生产库隔离，后续验证优先用临时库，动到真实库必须记录并恢复。

2026-07-08 追加真人两步式追踪验收：Codex 已接管本机 Telegram 从用户视角继续实测，真实发送 `700/701/705/706/708/702/707` 均有回复；其中发现 `706` 空关键词对小白仍不够顺手，已改为“先发 706，下一条直接回复名字”的两步式流程。真实复测 `706 → Codex20260708` 已成功添加追踪，随后已清理测试追踪对象 `NVIDIA/Codex20260708`，并把生产库恢复为 1 个 Telegram active 订阅者、偏好 `ai_model_updates/akshare/senate_trading`、推送时间每天 08:30、pending action 为 0。自动验收脚本已扩展到 10 步，包含两步式添加追踪，当前 `verified=true`、`passed_steps=10/10`。Computer Use 对 Telegram 底部按钮点击偶发 `noWindowsAvailable`，但等价文本路径和后端按钮 callback 已覆盖，记为本机控制工具限制，不判定为 Bot 功能失败。

2026-07-08 追加点击优先菜单收口：Telegram 端不能再退化成纯数字菜单，已把 Bot 左侧命令菜单真实同步为 `/start`、`/today`、`/status`、`/market`、`/ai`、`/weather`、`/schedule`、`/track`、`/pause`、`/help`，证据文件记录 `command_count=10` 且 `setMyCommands.success=true`。普通用户可直接点 Telegram 命令或点消息内按钮；数字 `700-708` 只作为兼容备用。推送时间补齐两步式：用户只发 `/schedule` 或 `705` 时，机器人会给 5 个常用选项，下一条回复 `1/2/3/4/5` 或 `每周 09:00` 即可完成设置。自动用户旅程验收已从 10 步扩展为 14 步，覆盖 `/start`、点击/斜杠今日简报、订阅状态、`/schedule → 2`、`705 → 每周 09:00`、`/market`、`/ai`、`/weather`、`706 英伟达`、`706 → 周杰伦`、`/track → OpenEverything`、`/pause`、暂停后状态和 `702` 恢复，当前 `verified=true`、`passed_steps=14/14`、`failed_steps=0`。

2026-07-08 追加多渠道边界：微信端与 Telegram 菜单策略不同。Telegram 支持点击菜单，因此优先按钮/斜杠菜单；微信不支持原生斜杠命令菜单，才使用数字编号菜单。微信代码已接入 `705` 推送时间和 `706` 添加追踪的两步式 pending action，例如 `705 → 2`、`706 → 英伟达`；但本机 Weixin ClawBot 旧 iLink 凭证只读探测为 `token_present=true`、`userId_present=true`、`context_token_obtained=false`、`ret=-4`，说明旧凭证文件还在但不能直接收发，需要重新扫码/授权后才能真实接管微信测试。飞书/钉钉仍不做连通和配置测试。

### CC中转 VPS 部署与故障转移 — 主站在 Oracle ARM-1，Oracle ARM-2 可做温备候选

2026-07-08 只读调研 `/Users/blackdj/Documents/VPS-Config` 与本项目运维文档：当前 CC中转生产主入口为 `https://jiyu.245334.xyz`，Cloudflare proxied A 指向 Oracle ARM-1 `150.136.73.15`，Oracle Apache/Origin CA 反代 New-API `127.0.0.1:13000`，Frist-API 兼容与运营能力运行在 `127.0.0.1:3180`；关键服务为 `frist-api.service`、`openclaw-newapi.service`、`apache2`、`frist-api-r2-backup.timer`。`/Users/blackdj/Documents/VPS-Config` 中已登记 Oracle ARM-2 / Oracle 3055 `129.213.33.101`，并已有 `openeverything_health` / `openeverything_home` 这类 loopback-only 状态探针、server-status fallback、ccgame standby、Sonic active/passive 等可借鉴的主备思路。

故障转移建议：先做“温备主从”，不要直接做双活写入。主站继续放在 Oracle ARM-1；Oracle ARM-2 预装同版本 New-API/Frist-API/Apache/证书/健康探针，运行数据通过 R2 备份和定时只读同步预热。故障时由 18800 操作台或一键脚本完成三件事：冻结主站写入、在 ARM-2 恢复最近备份并跑健康检查、把 Cloudflare DNS/Load Balancer 切到 ARM-2。对 Telegram/微信每日简报推荐“双入口单数据库”：两个客户端都读写同一个订阅数据库，不做两边聊天内容流式同步，避免用户在 Telegram 点了暂停、微信又自动恢复这类错乱。

### CC中转真实小额订单预检问题 — 已恢复自动发货，首单观察中

2026-07-08 追加自动发货恢复：老板明确说“恢复自动发货”后，已先跑恢复前安全检查，live 返回 `safe_to_resume=true`、`blockers=[]`；随后恢复常驻自动发货。当前 `auto_ship_paused=false`、`can_auto_ship_paid_orders=true`、`auto_resume_canary_active=true`、首单观察剩余 1 次，表示下一笔真实发卡成功后会自动暂停一次，防止重复刷屏。公开售卖锁 live 返回 `can_public_sale=true`、`state=public_sale_unlocked`、`blockers=[]`；18800 首页截图为 `output/playwright/cc-ops-console-auto-ship-restored-20260708.png`，可见“正式售卖已放行 / 自动发货开着 / 补救 0 / 库存 36 张”。本轮只恢复开关，不主动点击闲鱼发货按钮，不额外发送卡密。

2026-07-08 追加当前页订单号识别增强：真实闲鱼聊天页当前只暴露“¥1.00 / 等待卖家发货”订单卡，没有可见订单号，导致严格单次发卡仍不能落成 `xy_oid_*`。已增强页面执行器，只读从白名单订单参数、订单相关 `data-*` 属性和“去发货/待发货”链接里提取真实订单号，并显式拒绝把商品链接 `id=...` 当订单号；扫描结果新增 `orderCardPresent/shipActionPresent`，18800 会提示老板点订单卡或“去发货”旁边进入订单详情。实机复验当前页仍未下发真实订单号，且刷新监听未抓到可用订单接口；当前安全状态仍是不发卡、不点发货、等待进入含订单号/交易号的详情页后再单次放行。

2026-07-08 追加真实待发货只读扫单：为避免重复发卡事故后直接恢复自动发货，18800 操作台新增“真实待发货扫单”和 `/api/cc-paid-order-probe`。该入口只读读取闲鱼卖家待发货列表，返回脱敏订单/买家/商品候选，不发卡、不调 webhook、不点“去发货”、不解除暂停。实机复验当前闲鱼卖家订单 API 返回 `PERMISSION_EXCEPTION::无权限访问`，页面会提示改走浏览器当前页兜底；确认只命中目标订单后，再单轮放行发货/接管严格门。

2026-07-08 追加浏览器真实订单号接管：Chrome 页面执行器和本机桥接器已支持从真实已付款页 URL/可见“订单号/交易号”提取订单号，并以 `xianyu-real:*` 交给本机后端转换为 `xy_oid_*`。没有真实订单号时仍生成 `xy_browser_*`，不能解锁正式售卖；该改动只改变订单证据归属，不绕过付款可见校验、不自动解除暂停。

2026-07-08 追加后端确认发货实验入口：18800 操作台新增 `/api/cc-shipments/{id}/confirm-xianyu-backend` 和“后端确认发货”按钮，复用闲鱼 H5 虚拟商品发货接口推进真实数字订单状态。该能力默认关闭，只有显式开启 `CC_XIANYU_AUTO_CONFIRM_SHIPMENT_ENABLED=1` 且订单已经 `message_sent`、订单号为 10 位以上纯数字时才执行；`xy_manual_*` / `xy_browser_*` 内测补救单只会标记跳过，不会调用闲鱼接口。当前仍不恢复桥接器，避免重复发卡事故复发。

2026-07-08 追加操作台 UI 收口：针对“是否可以基于 layui/layui 重构 18800”的判断，已采用本地静态资源方式引入 `layui@2.13.8`，不使用 CDN，不改变发货安全锁和业务 API。`http://127.0.0.1:18800/` 已接入 layui layer/element，补救队列升级为 layui 表格，危险确认改为更醒目的确认弹层；`/static/layui/...` 已加入免 Token 静态白名单，页面可正常加载本机样式和脚本，但业务 API 仍需要 Token；自动发货仍保持暂停，桥接器未恢复，避免重复刷屏事故复发。
2026-07-08 继续追加 18800 老板入口告警置顶：layui 操作台首屏新增 `top-alerts`，会把补救队列、待确认发货、自动发货暂停、闲鱼连接异常、库存不足等红/黄灯置顶，并在旁边给“怎么办/只读检查/只放行一次”按钮。已重启 `ai.openclaw.xianyu` 并用 Playwright 截图 `output/playwright/cc-ops-console-layui-alerts-20260708.png` 复验；运行态仍为 `auto_ship_paused=true`、`one_shot_active=false`，没有恢复常驻自动发货。
2026-07-08 再追加 18800 layui 暂停态收口：修复主渲染函数漏定义 `strictPaused` 导致浏览器运行态可能报错的问题，并把首屏状态从“故障/先别卖”收口为“待你恢复自动发货 / 严格门已通过，自动发货暂停保护”。live 只读复验显示 `state=paused_after_strict_gate`、`resume-preflight.safe_to_resume=true`，但 `auto_ship_paused=true`、`one_shot_active=false`、`auto_resume_canary_active=false` 仍保持；截图证据为 `output/playwright/cc-ops-console-paused-ready-to-resume-20260708.png`。
2026-07-08 追加恢复前安全检查自动刷新证据：过去老板要先点“刷新上架锁”，再点“恢复前安全检查”，不够傻瓜。本轮已让 `/api/cc-operator-mode/resume-preflight` 在库存/渠道证据冷启动为空时自动跑一次只读刷新；live 复验返回 `safe_to_resume=true`、`refreshed_inventory=true`、`blockers=[]`。该动作只读，不分配卡密、不发送闲鱼消息、不点击发货、不恢复自动发货；当前自动发货仍保持 `auto_ship_paused=true`、`one_shot_active=false`、`auto_resume_canary_active=false`，等待老板明确恢复。
2026-07-08 追加 18800 冷启动暂停保护口径修正：服务重启后如果库存/渠道证据缓存还没刷新，过去 `/api/cc-ops-snapshot` 会把“严格门已通过但自动发货暂停保护”短暂误报成 `auto_ship_not_ready/danger`。本轮已把严格门已过、补救队列清零、买家入口和 CC Switch 基础项正常、仅库存缓存冷启动的状态合并为 `paused_after_strict_gate` 展示态；总快照 now `ok=true`、下一步 `severity=warning`，老板看到的是“待恢复自动发货”而不是“系统故障”。恢复自动发货预检仍要求先刷新库存/渠道证据，不会绕过安全门；当前 live 仍为 `auto_ship_paused=true`、`one_shot_active=false`、`auto_resume_canary_active=false`。
2026-07-08 追加 skipped 发货确认假告警修正：旧手工/浏览器内测单被标记为 `xianyu_confirm_status=skipped` 后，过去仍会被 `xianyu_confirm_page_pending` 和 18800 补救队列表格当作“待点发货”，导致老板看到无需处理的假 1。本轮已把 skipped 从待点发货统计和补救队列表格中排除；显式当前页补救入口仍可按需人工触发，但老板首页不再制造红黄假告警。重启本机服务后 live 只读复验为 `pending_rescue=0`、`xianyu_confirm_page_pending=0`、`xianyu_confirm_pending=0`、`xianyu_confirm_failed=0`，截图为 `output/playwright/cc-ops-console-skipped-confirm-false-alert-fixed-20260708.png`。该改动只修正展示与统计，不发卡、不点击闲鱼发货、不恢复自动发货。
2026-07-08 追加 18800 layui 人工预检口径合并：已确认 `layui/layui` 可作为本机老板操作台的渐进式 UI 底座，继续使用本地静态资源、不走 CDN、不改变发货业务接口。本轮新增 `mergeLockWithPrecheck`，当 `/api/cc-manual-precheck-evidence` 显示 6/6 且状态为 `paused_after_strict_gate` 时，首屏会显示“严格门已通过，自动发货暂停保护/待你恢复自动发货”，避免旧售卖锁快照把老板误导为链路故障或“先别卖”。该改动只修正看板展示，不发卡、不点击闲鱼发货、不恢复自动发货。
2026-07-08 再追加人工预检证据入口：新增 `GET /api/cc-manual-precheck-evidence`，把人工预检 6 项拆成只读证据：CF 位置、品牌邮箱模板、重复发卡保护、可控自动发货策略、1 元额度 1:1、真实小额单严格门。live 复验返回 `passed=6/6`、`precheck_ready=true`、`missing=[]`、`state=paused_after_strict_gate`；接口安全边界为不发卡、不点击闲鱼发货、不恢复自动发货。当前 `auto_ship_paused=true`、`one_shot_active=false`、`auto_resume_canary_active=false` 仍保持，下一步仍是老板明确确认是否恢复自动发货。

2026-07-08：针对人工预检反馈，已完成四个可直接推进的修复。第一，公网注册/登录弹窗内已放入 Turnstile 验证槽，验证码会跟着登录/注册组件显示，不再沉到页面底部。第二，注册验证码和重置密码邮件已换成卡片化事务邮件模板，包含大号验证码、安全提醒、深色模式和移动端适配。第三，闲鱼卡密重复发送风险已加三层保险：后端已发订单不会再次派发话术，卖家桥接器遇到已处理订单直接跳过，浏览器执行器如果看到输入框里残留同一张卡密/同一段发货话术，会先清空草稿而不是再次发送。第四，闲鱼 `xianyu-*` 套餐额度已改为按人民币售价 1:1 入账，1 元测试商品不会再变成 7.5 美元/折算额度。
2026-07-08 追加回归守护：注册/登录页现在不仅要求存在 Turnstile，还用测试锁定“主登录卡片的登录/注册表单内、提交按钮上方”这一位置，避免验证码再次漂到页面底部。邮件模板和 1 元额度也已复验：验证码邮件 HTML 仍包含 `mail-shell/brand-card/security-badge` 和大号验证码；`xianyu-test-1` 生成卡密继续保持 `priceCny=1`、`creditCents=100`，同步 New-API quota 为 1 元对应值，不按 `DEFAULT_USD_TO_CNY` 放大。

2026-07-08 追加实机复验：本机旧服务未重启时曾把已 `message_sent` 的浏览器内测单再次当作待发送话术，导致桥接器又执行了一次 Enter 发送。现已补回归并上线运行态：浏览器待发送队列只返回 `manual_delivery_ready/message_send_failed`，已发订单再次巡检返回 `shipment_already_handled`；页面执行器新增“残留卡密草稿清理”，即使输入框里还留着卡密，也只清空不发送。已重启 `ai.openclaw.xianyu` 和 `ai.openclaw.cc-seller-bridge`，复验 `/api/cc-browser-delivery/next` 为 `hasPending=false`，桥接器单轮对已发订单返回 `stage=pending` / `alreadyHandled=true`，未再出现 `stage=sent`。当前补救队列仍为 0。

2026-07-08 再追加重复刷屏事故止血：老板反馈闲鱼仍不断向买家重复发送卡密后，已立即保持 `auto_ship_paused=true`，并停用 `ai.openclaw.cc-seller-bridge` LaunchAgent。根因定位为浏览器待发接口过去只是“读取下一条”，没有服务端领取锁；多个发送入口或多个闲鱼标签页可能同时/循环拿到同一条卡密。现已把 `/api/cc-browser-delivery/next` 改为原子领取，领取后进入 `browser_delivery_claimed`，第二个发送器拿不到完整话术；暂停状态会直接返回 `operator_paused`，不会再走付款页兜底派发；新增 `mark-send-failed`，页面失败会退回 `message_send_failed`。`browser_delivery_claimed` 已纳入补救/严格门未收尾统计。当前实机状态：`ai.openclaw.xianyu` 已重启加载新版，`/api/cc-browser-delivery/next` 在暂停时返回 `hasPending=false/reason=operator_paused`，桥接器服务未恢复，自动发货仍处于暂停，不能继续刷屏。恢复自动发货前必须先由老板确认买家侧没有新增重复消息，再手动单轮桥接器验证。

开源社区调研结论已同步到当前路线：PC 页面“去发货”经常只提示扫码去 App，不适合作为稳定自动发货主链路；更可行的下一步是对真实数字订单号实验 H5/mtop 虚拟发货接口，成功或“已发货”都视为确认，登录失效/订单状态错误要明确提示老板处理，页面点击仅做兜底。多价格商品短期不建议强行网页自动多规格发布，先用“一个套餐一个商品链接”保证稳定；长期再评估闲鱼开放平台/服务商 SKU 能力。正式售卖严格门不放宽：`xy_browser_*` / `xy_manual_*` 仍只算内测证据，公开售卖仍必须等 `xy_oid_*` 真实小额订单完成发卡、兑换、创建 API Key、导入 CC Switch 和终端调模型。

2026-07-08 追加 GitHub 轮子调研：已按用户提供的 21 个仓库完成调研并登记 `docs/082-open-source-wheel-research.md`。当前产品判断：`mootdx/mootdx`、`d60/twikit`、`Evil0ctal/Douyin_TikTok_Download_API` 最适合直接作为依赖或隔离服务接入；闲鱼三件套和 MediaCrawler 更适合借鉴架构/协议思路，不直接复制到生产；已归档、过旧、抢拍/强聊/OSINT 类项目暂不接入。

### CC中转老板统一入口、替换模式与自动恢复脚本 — 已完成第一批闭环

2026-07-07：本机新增 `http://127.0.0.1:18800/dashboard` 作为老板唯一收藏入口，首页明确展示首页总览、闲鱼售卖、每日简报、系统维护、帮助中心和技术支持报告。新增 `/api/export-status` / `/export-status` 脱敏状态报告，技术支持可直接读取队列、库存、运行态和下一步，但不包含卡密、Token、买家昵称或 API Key。新增 `/api/cc-replacement-mode-test-pack`，用于当前买家号不可用时演练“模拟下单 → 发卡 → 发货 → 公网注册 → 兑换 → 创建 API → 导入 CC Switch → 终端调用”，但明确不解锁正式售卖；`xy_oid_*` 真实小额订单严格门仍保持。新增 `scripts/auto_health_check.sh`、`scripts/auto_recovery.sh`、`scripts/local_backup.sh`、`scripts/disaster_recovery.sh`，健康检查实测 6.4 秒返回 JSON，恢复脚本 dry-run 不误重启已存活 18800，临时本地备份成功且未包含 `.env`。

2026-07-07 追加：替换模式已升级为严格模拟门 v2，新增 `GET /api/cc-simulation-gate`。该门按正式严格门口径追踪：真实给买家号发送卡密、商品模板/重新上架回写、买家公网注册兑换、API Key 创建、CC Switch 导入入口、终端模型调用日志、渠道/服务器状态；只有“买家真实下单付款”和“最终点击闲鱼发货按钮”被明确列为排除项。即使模拟门全绿，也固定 `can_unlock_public_sale=false`，正式售卖仍必须等新的 `xy_oid_*` 真实小额单。

2026-07-08 追加收口：严格模拟门最后缺口“重新上架/恢复上架已回写”已闭环。当前卖家 Chromium 打开的是闲鱼商品详情页，页面未出现“已下架/已售罄/商品已失效”等失效文案；页面执行器已把可访问商品详情页视为在线核验通过，桥接器 `--relist-only --simulation-relist` 回写 `relist_status=online_verified`。`/api/cc-simulation-gate` 当前 `simulation_gate_ok=true`、`missing_steps=[]`、`can_unlock_public_sale=false`；正式售卖仍锁定在没有新的 `xy_oid_*` 真实订单，`--require-real-order` 返回 `ok=false` 属于预期安全门。全量后端回归第二次通过；首轮 Intel Worker CLI 曾出现一次外部源 `raw_count=0` 抖动，单测复跑和第二次全量均通过，暂不影响 CC中转闭环。

### CC中转方案 B 当前真实状态 — 生产内测可继续，正式售卖仍锁定

2026-07-07 操作台/UI 与后半段补救复核：本机 `http://127.0.0.1:18800/` 已重做为 Apple 风格深色状态面板，首屏只显示老板日常 6 件事，工程排障默认折叠。已新增 `GET /api/cc-xianyu-confirm/current-page-candidate`：旧 `xy_manual_*` / `xy_browser_*` 测试单即使已经是 `message_sent`、已发卡密，也可以在卖家 Chromium 当前页明确可见“已付款/待发货/等待发货”信号时继续点击闲鱼发货；页面没有付款信号时桥接器返回 `no_paid_order_signal` 并跳过。该路径只用于生产内测补救，不保存真实订单号，不计入正式 `xy_oid_*` 严格门。当前截图证据为 `output/playwright/cc-ops-console-redesign-20260707-final.png`，生产内测可继续；正式售卖仍需新 `xy_oid_*` 真实订单严格门通过。

2026-07-07 追加复核：已修正商品绑定稳健性，完整闲鱼分享文本、短链接本体、`短链接 CZ007` 都能命中同一套餐映射；本机 `ai.openclaw.xianyu` 已重启加载新规则，卖家专用 Chromium 已重新拉起，本机桥接器 `--once` 返回 `ok=true` 且无已付款信号时安全跳过。最新验证：Python 闲鱼/接口回归 `[100%]`、Chrome 扩展测试 `47 passed`、Frist-API 全量 `185 passed`、生产内测只读巡检 `ok=true`。Oracle runtime 只读复核显示上游余额同步 `level=ok`、低余额阈值 `50/20` 元，今日自动补库存曾创建 `32` 张后再次巡检创建 `0` 张，说明六档安全库存已补齐。正式售卖严格门仍保持 `ok=false`，原因仍是尚无新的 `xy_oid_*` 真实闲鱼自动订单；这不是故障，等待老板再跑 1 单小额真实付款。

2026-07-07 最新收口：系统已补齐三条发货路径：1）WebSocket 结构化付款卡片自动发卡；2）卖家订单列表 `NOT_SHIP` 轮询兜底（当前登录态可能返回 `PERMISSION_EXCEPTION::无权限访问`，只能作为加分能力）；3）Chrome 付款页 `paid_page_dispatch` 兜底，在当前闲鱼页可见“已付款/待发货”时自动生成话术并发送。确认发货已支持后端真实数字订单号内存确认和浏览器页面点击两种路径；恢复可售已补 `/api/cc-xianyu-relist/next` 队列，只对已确认发货记录候选，且页面必须显示已下架/已售罄和重新上架按钮才点击。严格门口径已收紧：只有 `xy_oid_*` 真实自动订单才算正式售卖证明，`xy_manual_*` 与 `xy_browser_*` 只算内测/补救，不再冒充真实自动订单；看板历史摘要也已按该口径规整，旧手工单不会再显示为真实自动订单。当前只读生产内测巡检 `ok=true`，但 `--require-real-order` 严格门 `ok=false`，原因是尚未产生新的 `xy_oid_*` 真实闲鱼付款自动发货订单。实机复核发现当前 Chrome 仍只有旧社媒插件心跳，未检测到 `OpenEverything Social Pilot` 已加载；操作台已改为明确提示运行 `make cc-seller-chrome` 并加载运行版插件目录 `~/.openclaw/cc-social-pilot-runtime-extension`，避免把“没装插件”误报为“刷新一下即可”。

### CC中转闲鱼自动发货 — 实单闭环已通过（生产内测）

2026-07-07 复核 6 个闲鱼/卡密自动发货开源项目后，当前判断保持不整套替换：成熟项目可借鉴“卡券池、防重复、待发货队列、补发、确认发货”，但许可证/接口权限/业务链路都不适合直接替换 New-API + CC Switch。代码侧已新增可选“发码后确认闲鱼发货”能力，默认关闭；只有 `CC_XIANYU_AUTO_CONFIRM_SHIPMENT_ENABLED=1` 且订单号是闲鱼真实数字订单号时才会调用，`xy_manual_*` 手工兜底单会跳过。Chrome 书签入口已从 3 个继续收敛为 2 个（本机操作台、用户主站），减少老板日常标签页。

此前人工确认发送的内测单已证明“卡密分配 → 闲鱼聊天发送 → 买家兑换 → 创建 API Key → CC Switch 导入 → 调模型”这条业务链路能跑通，但该单属于 `xy_manual_*`/浏览器补救口径，不能作为正式售卖严格门证据。当前补救队列为 0，仍可继续生产内测；正式放量必须再跑一笔新的 1 元真实闲鱼付款单，并由 WebSocket/卖家订单路径产生 `xy_oid_*` 自动订单证据。

2026-07-07 追加：方案 B 自动运营增强已落地到代码侧。Chrome 发货助手已补后台心跳和后端能力保留，发送卡密话术成功后会继续在当前闲鱼页面安全点击“去发货/无需物流/确认发货”，并把成功或失败原因写回 `cc_shipments.xianyu_confirm_*`；页面没有“已付款/待发货”信号时不会点击。恢复可售只做兜底：商品页明确显示“已下架/已售罄/重新上架”时才点击恢复上架，并写回 `cc_shipments.xianyu_relist_*`，不会自动改标题、价格或新建商品。Frist-API 侧已把 `1/5/15/50/100/500` 档位库存自动补卡接入后台定时，New-API 上游余额同步和 50 元低余额预警配置已补齐。

2026-07-07 追加生产收口：方案 B 已部署到 Oracle 生产内测 Frist-API，远端 `frist-api.service` 与 `openclaw-newapi.service` 均 active。生产套餐已从旧 `codex-30-*` 收口为 `1元测试/5/15/50/100/500` 六档，并执行自动补库存，当前安全库存为 `3/10/10/5/3/1`；本机闲鱼默认套餐与测试商品映射已改为 `xianyu-test-1`。上游余额同步可用，最近同步 `level=ok`。安全修正：`xy_manual_*` 手工兜底单不再进入自动点击闲鱼发货队列，只保留发码与买家链路证据；真实数字闲鱼订单才会进入浏览器确认发货队列。当前唯一需要人工保持的是卖家专用 Chromium 窗口打开并登录闲鱼；本机卖家桥接器已常驻接管浏览器兜底巡检。2026-07-07 老板已确认方案 B 的六档套餐、库存自动补、每日余额同步和低余额预警口径；代码侧已把公共 `shared.js` 默认套餐同步为六档，避免默认配置漂移。

2026-07-07 继续收口：本地与 Oracle 的 `apps/frist-api/server/shared.js` 已同步为六档套餐，远端备份为 `/opt/frist-api/backups/shared.js-before-cc-plan-default-20260707T132748Z.bak`；`frist-api.service` 重启后 active，公网主站 HTTP 200，未授权 `/v1/models` HTTP 401。Oracle 上一次 `unified-monitoring-agent_restarter.service` 失败只是 OCI 监控重启触发器历史标记，真实 `unified-monitoring-agent.service` 正在 running；已执行 `systemctl reset-failed`，当前 `systemctl --failed` 为 0。

2026-07-07 继续收口：老板确认方案 B 后，已把浏览器兜底从“插件直接 fetch localhost”升级为“本机卖家桥接器”。原因是新版 Chromium 的 Local Network Access 会让扩展 Service Worker 访问 127.0.0.1 不稳定；现由 `ai.openclaw.cc-seller-bridge` LaunchAgent 常驻，每 15 秒读取本机 18800 队列，再通过 DevTools 注入同一套闲鱼页面执行器，执行自动发卡发送、确认发货和恢复可售巡检。本机运行态已验证：桥接器 `running`，`/api/status.cc_chrome_extension` 显示 `manifest_version=bridge`、`supports_paid_page_dispatch=true`、`supports_relist_queue=true`、`needs_refresh_for_global_watch=false`；当前闲鱼页无已付款信号时安全跳过，不发送消息。正式售卖严格门仍不放宽，仍需新的 `xy_oid_*` 真实小额单。

## 一、当前状态与已知问题

### CC中转闲鱼重复发卡风险 — 已加单次放行闸门（仍待真实小额单严格门）

2026-07-08 最终严格门收口：已从闲鱼 `message.headinfo` 网络响应只读提取真实订单号和商品 ID，当前真实订单已从 `xy_browser_*` 浏览器临时单安全接管为 `xy_oid_87f...`，没有再次发送卡密。Frist-API 已上线低权限 `/api/ops/xianyu/remap-order`，只改已发卡履约的订单号，不分配新卡；Oracle `frist-api.service` 重启后 active。随后用同一真实订单对应买家 API Key 做一次极小真实模型调用，`model_logs_after_redeem` 从 0 变为 1；`node scripts/cc_zhongzhuan_readiness_audit.mjs --require-real-order` 已 PASS，18800 严格门摘要显示 `real_orders=1`、`same_order_ready=1`。当前公开售卖锁只剩 `auto_ship_paused=true` 人为安全开关，重复发卡事故后不自动恢复常驻发货；老板确认后可在 18800 操作台手动恢复。
2026-07-08 追加售卖锁人话修正：`/api/cc-public-sale-lock?refresh=true` 现在能把“严格门已通过但自动发货被老板手动暂停保护”和“自动发货链路故障”区分开。当前 live 返回 `state=paused_after_strict_gate`、`state_label=严格门已通过，自动发货暂停保护`、`can_public_sale=false`，唯一 blocker 是 `自动发货被手动暂停保护（防重复发卡）`；这只是文案和诊断字段收口，没有恢复常驻自动发货。
2026-07-08 继续追加恢复前安全预检：`POST /api/cc-operator-mode` 现在恢复自动发货前会先做只读预检，缺库存/渠道证据、补救队列未清、买家入口/CC Switch/闲鱼登录异常或真实小额单严格门未通过时返回 409，保持 `auto_ship_paused=true`。新增 `GET /api/cc-operator-mode/resume-preflight` 和 18800 “恢复前安全检查”按钮；live 复验只读刷新后 `safe_to_resume=true`，但没有自动恢复，仍等待老板明确确认。
2026-07-08 继续追加恢复后首单观察保险：老板明确恢复常驻自动发货时，系统会自动写入 `auto_resume_canary`，第 1 条卡密真正进入 `message_sent` 后立刻自动暂停，防止恢复后一口气连续处理多单。该保险覆盖 18800 `mark-sent` 和 `XianyuLive` WebSocket 自动发货记录路径；当前 live 没有恢复，所以 `auto_resume_canary_active=false`。

2026-07-08 追加安全收口：在已保持 `auto_ship_paused=true` 和浏览器领取锁的基础上，新增“只放行一次发卡”闸门。18800 操作台现在可点“只放行一次发卡”，系统会写入 1 张 3 分钟有效的单次放行票；浏览器助手或 `scripts/cc_zhongzhuan_seller_bridge.mjs --once --one-shot-override --json` 只能消费 1 次，成功领取/生成一条卡密话术后自动失效。无放行票时，`/api/cc-browser-delivery/next` 在暂停状态继续返回 `operator_paused` 且不返回卡密；付款页兜底派发带 `one_shot=true` 时也必须消费放行票，否则 HTTP 409，不会调用 webhook 分配新卡。

当前这项修复只解决“暂停状态下安全推进一单”和“避免重复发两条卡密”的问题；正式售卖严格门仍未完成，仍需要新的 `xy_oid_*` 真实闲鱼小额订单完成：发卡 → 买家兑换 → 创建 API Key → CC Switch/终端调模型。

2026-07-08 继续追加“一键跑当前页”：18800 操作台可直接调用 `/api/cc-seller-bridge/one-shot-delivery`，内部使用 `--delivery-only --one-shot-override --require-single-xianyu-page --require-real-order-id`，不再要求老板记终端命令。当前实测浏览器只打开 1 个闲鱼首页时，`/api/cc-seller-bridge/page-scan` 只读返回 `scanCompleted=true`、`notReady=true`、`readyPages=0`、`reason=no_paid_order_signal`，没有发送卡密，也没有留下单次放行票；该情况现在会显示为“现在打开的是闲鱼首页，请从消息或订单列表打开这笔已付款订单”，不再误报系统扫描失败。为避免多聊天页发错买家，单次发卡还会要求只打开 1 个闲鱼页，且页面必须能识别真实订单号/交易号。因此下一步仍是把卖家 Chromium 切到唯一的真实已付款聊天/订单详情页，先点“只读检查当前页”，确认付款信号、输入框和订单号都命中后，再点“一键跑当前页”。
2026-07-08 再追加前端提示修正：后端已给出人话 `nextAction` 后，18800 页面现在会优先展示该建议，不再把 `no_paid_order_signal` 等机器原因显示给老板；这只改变提示文案，不改变发卡安全门。
2026-07-08 再追加入口引导：18800 单次发卡区域新增“打开卖家 Chromium 的闲鱼消息”和“打开卖家 Chromium 的工作台”快捷按钮；只读检查未通过时也会附带这两个按钮，帮助老板从闲鱼首页切到已付款买家的聊天/订单页。该入口走 `/api/cc-seller-bridge/open-page` 和 `--open-page=im|seller`，只导航卖家专用 Chromium，并通过 `Page.bringToFront` 尽量把目标标签页带到前台；不发卡、不申请单次放行、不修改订单，普通浏览器链接只作为兜底。
2026-07-08 运行态复验：已通过 `/api/cc-seller-bridge/open-page` 把卖家 Chromium 当前页从闲鱼首页导航到闲鱼消息页，返回 `openPageOnly=true/deliveryOnly=false/oneShot=false`。随后只读扫描仍显示未选中具体已付款买家（`paidSignal=false/inputReady=false`），所以没有发卡；下一步是在消息页里点进目标已付款买家的聊天/订单详情。
2026-07-08 继续补提示：只读检查现在能区分“闲鱼消息列表页”和“卖家工作台页”。当前停在 `goofish.com/im` 且没点进买家时，会明确提示“在左侧会话列表点进已付款买家”；停在 `seller.goofish.com` 时，会提示从订单/待发货打开该订单或联系买家。该改动只改提示，不发卡。

### CC中转闲鱼真实付款漏单 — 已补浏览器发货助手（待真实聊天页发送）

2026-07-06 真实小额内测出现关键问题：买家手机端截图已显示“我已付款，等待你发货”，但本机 `ai.openclaw.xianyu` 虽然 WebSocket/Cookie 正常，SQLite 中 `messages=0 / orders=0 / cc_shipments=0`，说明这次不是“收到后未发货”，而是闲鱼付款系统卡片没有进入本机 WebSocket，或在服务重启窗口被错过。该问题证明当前生产内测不能只依赖 WebSocket 推送作为唯一自动发货触发源，后续需要继续补订单轮询/浏览器助手读待发货列表。

本轮已先补安全兜底：操作台新增“已付款漏单兜底”，受本机 `X-API-Token` 保护。老板只有在闲鱼界面已确认买家付款后才可点击，接口会调用 CC中转低权限 webhook 分配真实兑换码并返回可复制发货话术，记录状态为 `manual_delivery_ready`；该状态被纳入补救队列和只读巡检 pending rescue，防止“卡密已分配但还没发给买家”被误判为闭环完成。2026-07-06 继续补 Chrome 插件“CC中转发货助手”：插件在当前闲鱼聊天页可见“已付款/待发货”信号后，读取本机已分配话术、填入聊天输入框并点击发送，随后自动调用 `mark-sent`；如果页面没有付款信号会阻止发送。2026-07-07 已对当前这笔测试单完成真实聊天发送并标记 `message_sent`，补救队列已清零；未完成买家兑换/API/CC Switch/调模型前，生产内测仍不能改口为正式可售。

2026-07-06 追加复核开源轮子与订单 API：`zhinianboke/xianyu-auto-reply`、`GuDong2003/xianyu-auto-reply-fix` 和 `23Star/xianyu-super-butler` 功能更全，但主线/二开要么 AGPL-3.0、要么许可证不清，且公开 Issue 已出现与本机一致的 `PERMISSION_EXCEPTION::无权限访问` 待发货订单接口问题。本机真实 Cookie 只读调用闲鱼卖家 `NOT_SHIP` 订单页同样返回无权限，因此不能把“全自动”建立在卖家订单列表 API 上。本轮已把 Chrome 插件升级为“看守当前聊天页”：老板打开对应买家聊天页后开启看守，插件锁定该标签页定时检查付款信号，命中后只发送已分配待发送话术，成功一次自动关闭。2026-07-07 当前真实测试单已人工确认并通过浏览器发送，pending rescue 已清零。
插件已进一步适配手机闲鱼页面：识别 `m.tb.cn/tb.cn` 分享短链，付款提示新增“提醒发货/记得及时发货”，输入框新增“想跟TA说点什么”占位符。由于 manifest 权限发生变化，真实 Chrome 里的扩展需要在 `chrome://extensions` 手动刷新一次后才能使用新短链/看守能力。
2026-07-06 继续收口：Chrome 插件新增“看守所有闲鱼页”，并修复后台看守预检目标标签页的隐患。此前 `sendXianyuCcDeliveryFromTab(tab)` 的预检会误用当前激活标签页；现在会预检传入的目标闲鱼标签页。全局看守只在本机刚好 1 条待发货时启用，扫描已打开的闲鱼页，页面必须可见已付款/待发货信号并找到聊天输入框才发送，成功一次自动关闭，避免多单场景误发。已通过插件 43 项测试、后端相关 42 项测试和 `make test` 全量；2026-07-07 当前实单已发送，严格门现在阻断在买家自助链路未完成。
本机状态中心和操作台也已修正下一步口径：当补救队列是 `manual_delivery_ready` 时，会直接提示“刷新 Chrome 插件，打开买家聊天页，用当前页看守或单待发货全局看守发送”，避免误以为后台订单 API 能自动补发；当前补救队列已清零，下一步改为等待买家兑换、创建 API Key、CC Switch 导入和调模型。

### CC中转闲鱼测试商品绑定预备检查 — 已通过（等待真实付款）

2026-07-06 针对用户已发布的闲鱼测试商品 `https://m.tb.cn/h.RC4QcXM?tk=DxWwgNjrfdQ CZ007` 做真实下单前预备检查：已扩展本机操作台商品绑定接口，支持直接粘贴 `【闲鱼】[短链接](短链接) CZ007 「标题」点击链接直接打开` 这类完整分享文本，后台会规整为 `短链接 + 分享码` 后再保存，避免老板每次手动删除前后说明。新增回归测试先确认旧行为会把整段文本原样保存，再修复为自动规整。

预备检查同时发现当前测试商品曾绑定到套餐 `1`，该值不是 CC中转发货接口认可的套餐 ID；如果直接真实付款，可能导致已付款但找不到可发卡密。现已把该测试商品映射修正为当前有库存的 `codex-30-day`，本机 `/api/cc-operator-mode` 返回 `auto_ship_paused=false`、`webhook_configured=true`、`can_auto_ship_paid_orders=true`、`pending_rescue=0`、`enabled_item_mappings=1`。只读生产巡检 `node scripts/cc_zhongzhuan_readiness_audit.mjs --mode=read_only --json` 返回 `ok=true`：闲鱼 WebSocket/Cookie 正常，自动发货 webhook 已配置，补救队列 0，Oracle `frist-api.service` / `openclaw-newapi.service` / `apache2` 均 active，未售卡密 5，New-API 启用兑换码 5、启用渠道 3，公网主站 200。当前仍是生产环境内测；正式售卖前唯一剩余门槛仍是用另一个账号跑 1 单真实小额付款，并完成买家兑换、创建 API Key、CC Switch 导入和调模型严格门。

### CC中转老板入口收敛与公网自用模式移除 — 已复验（内测）

2026-07-06 追加复验：按用户反馈继续把本机页面从“暗色工程控制台”重构为 Apple 风格“状态中心 + 操作台”。`http://127.0.0.1:18800/ops-links` 现在默认只显示状态结论、闭环圆环、自动发货、库存与渠道、买家链路和下一步，高级排障折叠；`http://127.0.0.1:18800/` 现在是老板操作台，只保留确认闲鱼在线、绑定商品、暂停/恢复自动发货、处理补救队列四步，商品模板和只读巡检在次级区域。新增 `/api/cc-operator-mode` 和 `cc_operator_state.py`，可一键暂停/恢复自动发货；暂停时 `XianyuLive` 不调用 CC中转 webhook，失败补发循环也跳过。已重启 `ai.openclaw.xianyu`，live `/api/cc-operator-mode` 返回 `auto_ship_paused=false`、`webhook_configured=true`、`can_auto_ship_paid_orders=true`、`pending_rescue=0`；Playwright 截图保存为 `output/playwright/cc-status-center-apple.png` 和 `output/playwright/cc-operator-console-apple.png`，截图检查 `hasDenseOldText=false`。`make test` 重新跑到 `[100%]` 且退出码 0。当前仍是生产环境内测，不是正式售卖；正式售卖唯一外部门槛仍是 1 单真实闲鱼小额付款同单严格门。

2026-07-06 按用户反馈把 Chrome/本机 GUI 从“工程排障入口堆叠”收敛为给人看的暗色状态中心：`http://127.0.0.1:18800/ops-links` 只展示售卖状态、自动发货、库存与渠道、买家链路、下一步和 3 个常用入口；完整 GUI `http://127.0.0.1:18800/` 改名为“CC中转高级控制台”并暗色化，仅用于补救发货、商品映射和严格门排障。Chrome `CC中转运营` 书签文件夹已重建为 3 个入口（状态中心、用户主站、高级控制台），当前 Chrome 相关标签也只剩这 3 个；`node scripts/cc_zhongzhuan_chrome_bookmarks.mjs --json` 返回 4 个 Profile 均 `urlCount=3`，只读审计 `chromeBookmarks.ok=true`。生产 New-API 已把 `SelfUseModeEnabled=false`，公网渲染 `https://jiyu.245334.xyz/` 标题为 `CC中转` 且页面文本不含“自用模式”；`https://jiyu.245334.xyz/admin.html` 已由 Apache 302 到 `/console`。`/v1` 404 和未授权 `/v1/models` 401 仍是正常程序接口行为，不再作为人类标签页。

2026-07-06 全量测试同时暴露并修复一个社媒插件测试隔离问题：`test_social_extension_status.py` 过去只替换 `x_auto_ops._STATE_FILE`，但草稿列表会合并 `social_scheduler._STATE_FILE`，导致读取本机真实草稿时计数从 1 漂到 3。现已为该测试文件增加自动隔离 fixture，`test_social_extension_status.py` 和 `make test` 均已通过。


### CC中转生产内测售卖闭环与运营台入口 — 已复验（内测）

2026-07-05 最新复验：本机 `ai.openclaw.xianyu` 已重启，`/api/cc-public-sale-lock?refresh=true` 返回 `state=internal_test_ready`、`can_internal_test=true`、`can_public_sale=false`，WebSocket/Cookie 正常，CC自动发货已配置，默认发货套餐已固定到当前唯一可售日卡库存，自动发货套餐路由预判显示 `mode=default_plan`、`risk=low`，买家自助入口健康已纳入上架锁且 live 为主站 200 / models 401 / webhook 401，CC Switch 导入入口也已纳入只读巡检和上架锁，live 为 Frist 首页 200 且 `ccswitch` / `data-import-link` 标记齐全；新增 `/api/cc-real-order-test-pack` 和 GUI“实单验收包”，服务刚重启时可自动只读刷新证据并返回 `run_real_small_order`；后台严格门观察状态已暴露到 `/api/status` 和 `/api/cc-loop-watch`，严格门通过后的买家进度恢复已修复并过滤敏感字段，新增闭环覆盖清单且支持冷启动只读刷新和真实单后自动严格门只读观察，统一运营快照 `/api/cc-ops-snapshot` 也已返回同一份 `auto_strict_audit_status`，并新增 `buyer_site_smoke` 站内买家烟测证据；本轮新增 `/api/cc-buyer-site-smoke-plan` 只读计划，live 为 `state=ready_requires_confirmation`、`can_prepare=true`、`executes_now=false`，不会擅自创建用户、兑换、创建 API Key 或调模型；`/api/cc-automation-coverage` live 为 10/11、内部自动化 ready、正式售卖仍锁定，`auto_strict_audit_status.state=waiting_paid_order`，即严格门自动观察已开启但正在等待真实已付款订单；`buyer_site_smoke.state=partial`，当前兑换增量 0、API Key 增量 0、模型调用日志为正；`/api/cc-real-order-test-pack` 和 `/api/cc-operator-next-action` 已把 `buyer_site_smoke` 与 `buyer_site_smoke_plan` 纳入检查项；补救队列 0，未售卡密 5，New-API 启用兑换码 5，启用渠道 3。Chrome 书签脚本已重新修复 `Default`、`Profile 1`、`Profile 2`、`Profile 3` 的 `CC中转运营` 文件夹，只读审计 `chromeBookmarks.ok=true`；若 Chrome 运行中未即时显示书签栏，可直接访问/收藏 `http://127.0.0.1:18800/ops-links`，必要时重启 Chrome 刷新本地书签文件。`XianyuLive` 的稳定订单号识别已补强到闲鱼 URL 参数，已付款状态识别覆盖待发货/买家已付款/已支付等变体和订单结构化字段位置；已付款订单自带商品 ID 时会优先用于商品套餐映射，找不到再回退最近聊天商品/默认套餐，同时保护待付款/未付款/退款/关闭与普通聊天文本不误发卡或发错套餐；`make test` 全量跑到 `[100%]` 且退出码 0。当前唯一正式售卖 blocker 仍是：尚未通过真实闲鱼小额单的兑换、创建 API Key、CC Switch 导入和调模型严格门。




### CC中转运营统一快照接口 — 已补齐（内测）

2026-07-05 继续为后续通知/看板收口：新增 `GET /api/cc-ops-snapshot`，只读一次性返回 `next_action/status/sale_lock/loop_watch/buyer_progress`。`/ops-links` 和本机 GUI 已读取该快照，后续如果接通知可复用同一份状态，避免多接口拼装漂移；该接口不触发审计、不发货、不分配卡密、不修改库存。live 快照当前 `ok=true`，下一步仍是发布 1 个小额闲鱼测试商品并完成真实付款。

### CC中转统一下一步行动建议 — 已补齐（内测）

2026-07-05 继续减少老板判断成本：新增 `GET /api/cc-operator-next-action`，统一聚合上架锁、自动发货、补救队列、真实订单和买家链路，返回 `state/severity/title/primary_action/checklist`。`/ops-links` 和本机 GUI 已接入同一套建议；服务刚重启、库存证据未刷新时会优先提示“刷新上架锁”，只读刷新后才提示“发布 1 个小额闲鱼测试商品”。该接口不触发审计、不发货、不分配卡密、不修改库存。

### CC中转买家自助链路进度 — 已补齐（内测）

2026-07-05 继续补齐真实订单后的可视化排障：新增 `GET /api/cc-buyer-chain-progress`，只读聚合“已发货、已兑换、API Key、调模型、同单闭环”五步，并在 `/ops-links` 显示“买家进度”、在本机 GUI 显示“买家自助链路进度”。该接口不触发严格门、不发货、不分配卡密、不修改库存；live 当前返回 `stage=waiting_paid_order`，说明还没有真实闲鱼小额付款订单。

### CC中转实单买家闭环回写 — 已补齐（内测）

2026-07-05 继续补齐“已发货”和“买家完整跑通”的区别：本机 `cc_shipments` 新增 `buyer_chain_status / buyer_chain_verified_at / buyer_chain_note`。正式售卖严格门通过后，`record_cc_strict_audit()` 会按订单哈希把同一真实闲鱼订单标记为 `verified`，GUI/运营入口会显示已闭环订单数；老 SQLite 表会在启动时自动补列。回写只使用订单哈希匹配，不把完整订单号、卡密、Token 或 API Key 写入严格门摘要。

### CC中转运营入口总控看板 — 已补齐（内测）

2026-07-05 继续降低老板误操作风险：`http://127.0.0.1:18800/ops-links` 已从纯链接页升级为本机运营总控入口，输入本机 `OPENCLAW_API_TOKEN` 后会只读展示“上架前安全锁 / 自动发货 / 实单闭环 / 当前你要做什么”。页面只读取 `/api/status`、`/api/cc-loop-watch` 和 `/api/cc-public-sale-lock`，不提供发货、分配卡密或 webhook 冒烟按钮；重启 `ai.openclaw.xianyu` 后 live 页面包含上述标记，只读刷新上架锁返回 `internal_test_ready`、库存 5、兑换码 5、渠道 3，正式售卖仍因真实小额单严格门未过而锁定。

### CC中转后台内测巡检自动刷新 — 已补齐（内测）

2026-07-05 继续减少“上架锁证据要靠人工点击刷新”的漂移风险：本机闲鱼助手启动时会同时启动后台只读巡检线程，默认每 15 分钟运行一次 `read_only` 审计，自动刷新未售卡密库存、New-API 启用兑换码和启用渠道数量。该线程只更新上架锁和状态接口缓存，不调用 `--webhook-smoke`，不发送闲鱼消息，不分配卡密，不修改库存；当前 live 状态为 `internal_test_ready`、未售库存 5、启用兑换码 5、启用渠道 3，正式售卖仍因尚无真实闲鱼小额单严格门而锁定。

### CC中转上架前安全锁 — 已补齐（内测）

2026-07-05 继续避免“生产内测可发货”被误认为“正式可售”：本机闲鱼 GUI 新增“上架前安全锁”和 `GET /api/cc-public-sale-lock`。默认只读缓存，点击刷新时运行一次只读巡检刷新库存、New-API 启用兑换码和渠道证据；正式售卖只有在自动发货就绪、补救队列为 0、未售卡密库存 > 0、New-API 启用兑换码 > 0、New-API 启用渠道 > 0、真实闲鱼小额单兑换/API/调模型严格门通过后才会显示 `public_sale_unlocked`。复验：相关 pytest 为 `46 passed / 0 failed`；live 刷新返回 `state=internal_test_ready`、`can_internal_test=true`、`can_public_sale=false`、库存 5、兑换码 5、渠道 3，唯一锁定原因是尚未通过真实小额单严格门。

### CC中转 Chrome 运营窗口一键打开 — 已补齐（内测）

2026-07-05 继续修复“老板看不到书签组”的实际体验问题：`scripts/cc_zhongzhuan_chrome_bookmarks.mjs` 新增 `--open-window` / `--open` 参数。默认仍修复 4 个 Chrome Profile 的 `CC中转运营` 书签文件夹；加参数后会直接新开一个 Chrome 窗口并打开 7 个运营入口，绕过 Chrome 正在运行时书签 UI 不即时刷新的问题。复验：脚本语法检查通过；临时 Profile `--dry-run --open-window --json` 返回 `ok=true`；真实 Chrome 运行 `--open-window --json` 返回 `openedWindow.tabCount=7`，4 个 Profile 均 `urlCount=7`、`bookmarkBarVisible=true`。

### CC中转严格门证据持久化 — 已补齐（内测）

2026-07-05 继续推进“全自动闭环”可审计性：本机闲鱼 SQLite 新增 `cc_strict_audits` 表，`mode=strict` 正式售卖严格门会把脱敏摘要落盘，`XianyuAdmin` 可在进程重启后恢复最近严格门状态。落盘字段只包含通过状态、真实订单数、同单匹配数、同单完成数、兑换/API Key/模型调用增量和最多 5 条同单分阶段摘要；不保存 stdout、stderr、完整卡密、Token 或 API Key。复验：`py_compile xianyu_admin.py xianyu_context.py` 通过，`test_xianyu_cc_auto_ship.py + test_api_routes_regression.py` 为 `45 passed / 0 failed`；重启 `ai.openclaw.xianyu` 后 live `cc_strict_audit={}`，符合尚无真实小额订单现状；默认生产只读审计 `ok=true`，严格门仍按预期因 `realOrders=0` 失败。

### CC中转后台严格门自动观察 — 已补齐（内测）

2026-07-05 继续推进“全自动闭环”：本机闲鱼助手 `ai.openclaw.xianyu` 启动时会同时启动后台严格门观察线程，不再依赖老板打开 GUI 页面。该线程默认每 60 秒观察一次 `/api/cc-loop-watch` 同等状态；只有真实闲鱼订单已自动发货、无补救队列、自动发货链路可用且阶段为 `waiting_buyer_chain` 时，才按 10 分钟节流运行 `mode=strict` 的只读正式售卖严格门。它不调用 `--webhook-smoke`、不发送闲鱼消息、不分配卡密、不改库存；当前 live 阶段仍是 `waiting_paid_order`，所以会等待真实小额付款订单后再触发。复验：`py_compile xianyu_admin.py` 通过，`test_xianyu_cc_auto_ship.py + test_api_routes_regression.py` 为 `44 passed / 0 failed`；重启 `ai.openclaw.xianyu` 后 `/api/cc-loop-watch` 显示 `background_strict_audit_enabled=true`、`background_strict_audit_scan_seconds=60`、`stage=waiting_paid_order`、`pending_rescue=0`；默认生产只读审计 `ok=true`，严格门仍按预期因真实闲鱼实单数为 0 失败。

2026-07-05 已把兑换码与闲鱼自动发货助手收口到公网运营入口 `https://frist-api-oracle.245334.xyz/admin.html`，该入口经 Cloudflare proxied A → Oracle Apache → Frist-API `127.0.0.1:3180`，并继续受后台入口码/Cookie 保护；用户主入口仍是 `https://jiyu.245334.xyz`，旧 `frist-api.245334.xyz` 继续 301 到用户主站。已修复 Frist-API 在 Cloudflare/Apache 链式代理 `X-Forwarded-*` 逗号列表下 URL 解析崩溃的问题，并新增回归测试。生产内测 E2E 结果：New-API 受控成功路径完成注册、登录、兑换、API Key 创建/更新/禁用/恢复/删除、`/v1/models`、OpenAI/Claude 真实调用和渠道刷新；测试结束后已恢复 `turnstile_check=true`、`email_verification=true`，公网无 Turnstile 注册/登录继续返回 `Turnstile token 为空`，临时用户/Token/兑换码残留为 0。Frist 运营闭环完成卡密生成、同步 New-API、闲鱼履约 `delivered`、readiness `ready=true`；CC Switch E2E 已确认 `ccswitch:` provider 导入链接包含 `https://jiyu.245334.xyz/v1`、`gpt-5.4-mini` 和匹配 Key，调模型 200，删除 Key 后 401。New-API 原生渠道检测每 10 分钟开启，自动禁用/恢复、模型请求限流开启；当前 3 个渠道启用、15 个模型倍率已写入；Oracle 已显式固定 `FRIST_API_RATE_MARKUP=0.1`，最终复验显示渠道同步 `rateMarkup=0.1`、3 个渠道健康。已追加低权限全自动发货 webhook 和 OpenClaw `XianyuLive` 接入：已付款订单可自动发卡并发送话术，未付款订单阻断；2026-07-05 已补齐 `XianyuLive` 到 CC中转 webhook 的独立回归测试，`test_auto_shipper.py + test_xianyu_cc_auto_ship.py` 为 `20 passed / 0 failed`，并修复买家不聊天直接付款时 recent item 为空导致跳过发货的风险；同日进一步修复 Frist-API 无套餐/无 SKU 订单误判“没有可发货兑换码”的生产 Bug，生产无套餐 webhook 冒烟返回 `delivered` 且清理后仍保留 5 张未售日卡库存，New-API 启用兑换码为 5 条；本机 `ai.openclaw.xianyu` 已重启加载最新配置，日志显示 WebSocket 注册成功，且已把第三方 HTTP 客户端日志降噪并脱敏旧 Telegram 通知 URL；仍保持“生产环境内测，暂未正式售卖”；正式发闲鱼商品前建议老板用真人浏览器完成一次 Turnstile 注册/邮箱验证码/兑换的人工验收，并小批量实单观察闲鱼发送稳定性。

2026-07-05 追加复验：本机 Chrome `Default`、`Profile 1`、`Profile 2`、`Profile 3` 均已写入并去重 `CC中转运营` 书签文件夹，书签栏已开启；普通 Chrome 窗口已打开用户主站、New-API 后台、Frist 运营台、`/v1` 和 `/v1/models` 五个入口。新增一键审计 `scripts/cc_zhongzhuan_readiness_audit.mjs` 后，默认只读模式返回 `PASS`，带 `--webhook-smoke` 的生产低权限 webhook 冒烟也返回 `PASS`，测试履约已清理且库存恢复为 `unused=5`。项目级回归 `make test` 已跑到 `[100%]` 且 exit 0；Frist-API 全量回归为 `181 passed / 0 failed`。

2026-07-05 再追加自动化运营补救：本机闲鱼管理面板 `http://127.0.0.1:18800/` 已新增“CC中转发货补救队列”，并由 `cc_shipments` SQLite 表持久化。若 CC中转 webhook 已分配兑换码但闲鱼 WebSocket 消息发送失败，会记录 `message_send_failed`、保留完整待补发话术、触发健康告警，并允许在受 `X-API-Token` 保护的 GUI 中标记 `manually_resolved`；webhook HTTP 失败、话术缺失和异常也会进入同一队列。已重启 `ai.openclaw.xianyu`，首页无 token 可打开并提示输入本机 `OPENCLAW_API_TOKEN`，API 无 token 仍为 401，带正确 `X-API-Token` 的 `/api/status` 和 `/api/cc-shipments?limit=5` 均为 200。

2026-07-05 继续补齐 GUI 可视化：本机闲鱼助手 `/api/status` 现在返回 `cc_auto_ship` 与 `cc_shipments` 摘要，首页“系统状态”直接展示 CC 自动发货是否配置、补救待处理数量、已自动发送数、已人工处理数和 webhook 地址。复验显示 `ws_connected=true`、`cookie_ok=true`、`cc_auto_ship.configured=true`、`cc_shipments.pending_rescue=0`，说明当前自动发货助手在线且没有待补发黑洞。

2026-07-05 继续把该 GUI 状态纳入一键生产审计：`scripts/cc_zhongzhuan_readiness_audit.mjs` 新增 `localXianyuGui` 检查，要求本机 GUI 首页 HTTP 200、API 无 token HTTP 401、带 token HTTP 200、WebSocket/Cookie 正常、CC自动发货已配置且 `pendingRescue=0`。当前 `node scripts/cc_zhongzhuan_readiness_audit.mjs` 返回 `PASS`，并输出 `localXianyuGui: PASS`。

2026-07-05 继续补齐失败自动补发：`XianyuLive` 新增 `CC_XIANYU_RESCUE_LOOP_ENABLED` 后台循环，默认每 60 秒扫描 `message_send_failed` 记录，在闲鱼 WebSocket 在线且记录里已有完整发货话术时自动重发同一条消息；本机 GUI 也新增 `POST /api/cc-shipments/{id}/resend` 和“重试发送”按钮。该能力只处理“卡密已分配但首次消息发送失败”的补救，不会重新分配卡密，不会处理未付款订单。当前代码回归 `test_xianyu_cc_auto_ship.py + test_api_routes_regression.py` 为 `37 passed / 0 failed`，一键审计只读模式 `PASS`；正式售卖前剩余外部门槛仍是老板发布闲鱼商品后跑 1 单小额真实付款，观察平台真实消息投递稳定性。

2026-07-05 追加正式售卖前实单门：`scripts/cc_zhongzhuan_readiness_audit.mjs --require-real-order` 会强制要求本机 `cc_shipments` 出现真实闲鱼助手产生的 `xy_* / message_sent` 记录，避免把生产 webhook 冒烟误判成真实平台订单。随后继续把该严格门扩展到买家站内闭环：Oracle 生产 New-API 的已兑换兑换码数、活跃 API Key 数和模型调用日志数必须同时超过 2026-07-05 验收基线，才能证明买家完成“收到话术 → 注册/登录 → 兑换到账 → 创建 Key → 调模型”。当前默认审计 `PASS`，严格实单门按预期 `FAIL`，因为尚未发布闲鱼商品并完成小额真实付款/买家站内操作；这不是系统故障，而是正式售卖前最后一个外部平台验收门槛仍未发生。

2026-07-05 继续把正式售卖验收门做成 GUI 可见：本机闲鱼助手 `http://127.0.0.1:18800/` 首页新增“正式售卖验收门”卡片，直接展示真实闲鱼发货是否已发生、`xy_* / message_sent` 真实订单数、补救待处理数，以及严格验收命令。`/api/status` 新增 `cc_final_sale_gate`，来源为本机 SQLite `cc_shipments` 汇总，不泄露完整卡密或买家信息。当前 GUI 已重启加载新版，页面包含该卡片；默认审计和 webhook 冒烟均 `PASS`，严格实单门仍按预期 `FAIL`。

2026-07-05 继续补齐买家自助路径：Frist-API 闲鱼发货话术已从“兑换入口 + 卡密”升级为完整操作步骤：注册/登录、进入“兑换码”到账、进入“API Key”创建 Key、进入“CC Switch”复制导入链接并选择模型测试；未加入营销文案，不暴露上游信息，也不直接写 `/v1` 网关地址。该变更已单文件部署到 Oracle 并重启 `frist-api.service`，生产 webhook 冒烟和内网话术检查均通过，库存清理后仍为 `unused_after=5`。

2026-07-05 继续补齐 New-API 原生兑换回写：Frist-API 已新增默认 60 秒一次的 New-API 兑换状态同步器，并部署到 Oracle。同步器读取 New-API SQLite `redemptions`，按卡密哈希匹配 Frist 卡密，不打印完整卡密；买家若直接在 New-API 主站兑换，Frist 兑换卡和对应闲鱼履约会自动回写为 `redeemed`。一键审计 `--require-real-order` 也从“只看数量增长”升级为“同一 `xy_*` 真实闲鱼订单哈希关联”：要求同一订单已自动发货、对应卡密已兑换、履约已回写、兑换用户有启用 API Key 且兑换后有模型调用日志。当前默认生产内测审计和 webhook 冒烟均 `PASS`；严格正式售卖门仍按预期 `FAIL`，唯一原因是尚未发布闲鱼商品并完成 1 单小额真实付款/买家兑换/API/调模型。

2026-07-05 继续补齐老板可视化验收：本机闲鱼助手 GUI 已新增“一键闭环审计”卡片和 `GET /api/cc-readiness-audit?mode=read_only|strict`，可直接点击运行生产内测巡检或正式售卖严格门。该 GUI 接口只读，不开放 `--webhook-smoke` 写入冒烟，避免误点改变生产库存。复验显示页面包含“一键闭环审计 / 运行内测巡检 / 运行正式售卖严格门”，API `read_only` 返回 `ok=true, exit=0`，`strict` 返回 `ok=false, exit=1`，严格失败原因仍是尚无真实小额闲鱼订单。

2026-07-05 继续补齐多商品自动发货防错发：本机闲鱼助手 GUI 新增“闲鱼商品套餐映射”，可配置 `item_id → planId`，`XianyuLive` 检测到已付款订单后会优先按已启用映射调用 CC中转低权限 webhook；没有映射时继续回退默认套餐或任意未售卡密。CC中转自动发货接管时，旧 OpenClaw 部署包 License 话术不再同时发送，避免买家收到两套无关内容。复验：`test_xianyu_cc_auto_ship.py + test_api_routes_regression.py` 为 `41 passed / 0 failed`，`py_compile` 通过，默认闭环审计 `PASS`；本机 GUI 首页 200、无 token API 401、带 token `/api/status` 200，`ws_connected=true`、`cookie_ok=true`、`cc_auto_ship.configured=true`、`pending_rescue=0`，映射 API 冒烟“新增 → 查询 → 删除”通过且测试数据已清理；`make test` 全量 pytest exit 0，Frist-API 全量 Node 测试 `182 passed / 0 failed`。

2026-07-05 继续把运营状态做成老板可读 GUI：本机闲鱼助手新增“自动化运营水位”和“闲鱼商品模板”。`/api/cc-sale-readiness` 会汇总自动发货可用性、正式售卖是否仍缺真实小额单验收、webhook/ws/cookie/补救队列/商品映射状态和仍需人工介入事项；`/api/cc-product-template` 生成只含履约说明的极简闲鱼商品模板，包含付款后自动发卡、注册/登录、兑换、创建 API Key、CC Switch 导入和模型测试步骤，不写额外营销话术，不暴露 `/v1` 网关。复验：相关 pytest `42 passed / 0 failed`，GUI 首页包含“自动化运营水位 / 闲鱼商品模板”，带 token API 冒烟返回 `can_auto_ship_paid_orders=true`、`ready_for_public_sale=false`、`pending_rescue=0`；默认闭环审计继续 `PASS`。

2026-07-05 继续补齐 Chrome 运营入口可维护性：新增 `scripts/cc_zhongzhuan_chrome_bookmarks.mjs`，可重复修复/重建本机 Chrome 各 Profile 的 `CC中转运营` 书签文件夹，写入本机运营入口总页、用户主站、New-API 后台、Frist 运营台、`/v1`、`/v1/models` 和本机闲鱼助手 GUI 共 7 个入口，并开启书签栏显示；写入前会在 Chrome Profile 原目录生成 `.codex-backup-*` 备份。已用临时 Chrome Profile 冒烟验证去重/保留旧入口/备份逻辑，并对真实 `Default`、`Profile 1`、`Profile 2`、`Profile 3` 运行修复，均返回 `ok=true`、`urlCount=7`、`bookmarkBarVisible=true`；随后默认闭环审计继续 `PASS` 且 `chromeBookmarks: PASS`。

2026-07-05 继续把老板可见入口和多商品映射收口：本机闲鱼 GUI 新增免 token 运营入口总页 `http://127.0.0.1:18800/ops-links`，集中跳转用户主站、New-API 后台、Frist 运营台、本机闲鱼 GUI、模型接口检查和 API Base URL；Chrome `CC中转运营` 书签文件夹升级为 7 个入口，并清理废弃 `file://cc_zhongzhuan_ops_links.html` 链接，真实 `Default`、`Profile 1`、`Profile 2`、`Profile 3` 复写后均为 `urlCount=7`。GUI 的“闲鱼商品套餐映射”新增“最近捕获到的闲鱼商品”列表，点“填入映射”即可把 `item_id`、标题和价格带入表单/商品模板。复验：`test_xianyu_cc_auto_ship.py + test_api_routes_regression.py` 为 `42 passed / 0 failed`，`/ops-links` 和 GUI 首页 HTTP 200，默认闭环审计 `PASS`；严格实单门仍按预期 `FAIL`，因为尚未发生真实闲鱼小额付款订单。

2026-07-05 继续补齐买家站内闭环可视化：本机闲鱼助手“一键闭环审计”卡片现在会显示同一真实订单的分阶段明细，包括订单前缀、履约状态、卡密状态、New-API 兑换、API Key 数量、兑换后模型调用数和最终结论。当前没有真实小额订单，所以 `/api/cc-readiness-audit?mode=read_only` 返回 `same_order_latest=[]`、`same_order_ready=0`，属于预期；真实订单发生后这里会用于定位买家卡在“已发货 / 已兑换 / API Key / 调模型”的哪一步。复验：相关 pytest `42 passed / 0 failed`，默认闭环审计 `PASS`，GUI 首页包含分阶段状态渲染逻辑。

2026-07-05 继续收紧正式售卖状态和实单观察：本机闲鱼助手 GUI 新增“实单闭环观察”卡片和 `/api/cc-loop-watch`，轻量显示自动发货配置、闲鱼 WebSocket/Cookie、补救队列、真实订单数、商品映射数和严格买家闭环是否通过。同步修复 GUI 前端漏接 `/api/items` 响应的问题，“最近捕获到的闲鱼商品”现在能真正填入映射表单。`ready_for_public_sale` 不再仅凭本机 `xy_* / message_sent` 变绿，只有最近一次正式售卖严格门通过且同一真实订单完成兑换/API Key/模型调用后才会放行。复验：相关 pytest `42 passed / 0 failed`，live `/api/cc-loop-watch` 返回 `stage=waiting_paid_order`、`can_auto_ship_paid_orders=true`、`ready_for_public_sale=false`、`pending_rescue=0`；默认闭环审计 `PASS`，严格门仍按预期因无真实小额付款订单失败。

2026-07-05 继续减少老板人工记忆负担：本机闲鱼 GUI 在“实单闭环观察”进入 `waiting_buyer_chain` 后，会按 `CC_XIANYU_AUTO_STRICT_AUDIT_INTERVAL_MS`（默认 10 分钟，最小 1 分钟）节流自动调用只读严格门 `GET /api/cc-readiness-audit?mode=strict`。该自动观察不开放 `--webhook-smoke`，不会发闲鱼消息、分配卡密或修改库存；仅用于刷新“同一真实订单是否已完成买家兑换/API Key/模型调用”的证据。当前 live 状态仍是 `waiting_paid_order`，所以自动严格门尚不会触发；GUI 已重启加载新版，页面包含 `maybeAutoRunStrictAudit` 和 `ccLastAutoStrictAuditAt`，相关 pytest 仍为 `42 passed / 0 failed`。

### CC中转 New-API 公网主入口 — 已闭环（生产内测）

2026-07-05 已把 `https://jiyu.245334.xyz/` 公网主入口从旧 Frist 自研页面切到成熟开源 New-API 面板：Cloudflare → Oracle Apache → `127.0.0.1:13000`；旧 `frist-api.245334.xyz` 继续 301 到主站，Frist-API 仍在 `127.0.0.1:3180` 运行用于 CC Switch/旧桥接能力和内部兼容。公网全链路 E2E 已通过：原生注册、登录、兑换码创建/兑换到账、API Key 创建/列表/详情/取 Key/更新/禁用/恢复/删除、`/v1/models`、OpenAI `gpt-5.4-mini`、Claude `claude-haiku-4-5-20251001`、渠道刷新均正常；清理后 New-API SQLite `e2e_users=0`、`e2e_tokens=0`、`e2e_redemptions=0`。当前 New-API 库存为 3 个启用渠道、15 个模型；未授权 `/v1/models` 返回 401；Playwright 验证首页、登录页、注册页可打开，标题最终为「CC中转」，无前端 error/warning。当前仍是生产环境内测，未正式售卖；2026-07-05 已复用旧 Frist-API 生产配置写入 New-API 原生设置，`turnstile_check=true`、`email_verification=true`，New-API 管理员/root 账户 `two_fas=2`。

2026-07-05 追加 New-API 原生能力只读审计：CC Switch 入口、API Key、渠道、模型、能力映射、兑换/充值、日志统计均可继续沿用 New-API 原生能力；已复用 Frist 旧配置补齐 New-API Turnstile、SMTP/邮箱验证和管理员 2FA。正式售卖前剩余 P0 技术债为模型请求限流、可售兑换码库存和老板真人浏览器 Turnstile 注册/登录/兑换验收；`subscription_plans=0` 表示套餐订阅尚未配置。


### CC中转生产内测品牌收口与售卖前验收 — 已闭环（内测）

2026-07-05 已按用户最新口径将对外产品名收口为「CC中转」；当前仍使用 `https://jiyu.245334.xyz/` 作为生产内测入口，暂未正式售卖。站内已加入“生产环境内测，暂未正式售卖”提示，新生成卡密默认前缀改为 `CC`，历史 `JIYU-*` 仅保留为兼容别名，避免旧测试卡密失效。售卖前验收中发现并修复四个 New-API 生产桥接断点：CC 卡密经 New-API 兑换到账后不回写本地卡密/闲鱼履约状态、New-API 创建的 API Key 访问 `GET /v1/models` 仍走旧本地 Key 表导致 401、API Key“禁用”未调用 New-API `status_only=true` 导致数据库 `tokens.status` 仍为启用、New-API 删除 Token 后 SQLite `tokens` 表仍可能保留 E2E 临时残留。当前本地全量回归为 `177 passed / 0 failed / 0 skipped`；公网首页、品牌、内测提示、旧域名跳转、Turnstile 安全门、管理员 2FA/readiness、卡密生成同步 New-API、闲鱼履约分配、渠道状态刷新均已复验。用户提供的 3 条 86Game 上游 Key 已脱敏探测并接入生产内测库存：New-API 当前有 3 个可用渠道、15 个模型，OpenAI/Codex 与 Claude 真实调用均为 200；`/api/admin/production-readiness` 按新增的 `healthy_upstream_inventory` 门槛返回 `ready=true`。生产 E2E 已验证临时用户 Dashboard、API Key 创建、`/v1/models`、OpenAI `gpt-5.4-mini`、Claude `claude-haiku-4-5-20251001`、Key 禁用后 401、兑换码同步 New-API、闲鱼履约 `delivered`、readiness `failedChecks=[]`，并确认清理后 `e2e_tokens=0`、`active_e2e_tokens=0`、`e2e_redemptions=0`。公网自动化不会绕过 Turnstile，因此真实“注册→登录→兑换”的最后一跳仍建议老板在浏览器手动点一次人机验证做人工验收；在此之前建议保持“生产内测，暂未正式售卖”口径。


### CC中转 Cloudflare/Oracle 生产内测入口 — 已闭环

2026-07-04 已按“优先用 xyz 子域名”的生产路径上线：`jiyu.245334.xyz` 已在 Cloudflare `245334.xyz` 区域创建 proxied A 记录并指向 Oracle ARM `150.136.73.15`；Oracle Apache 使用 Cloudflare Origin CA 证书，证书覆盖 `jiyu.245334.xyz`、`frist-api.245334.xyz` 和 `frist-api-oracle.245334.xyz`；旧 `frist-api.245334.xyz` 已 301 跳转到 CC中转主站。2026-07-05 公网主入口已改为反代 New-API `127.0.0.1:13000`，Frist-API `127.0.0.1:3180` 仅保留为内部兼容/旧桥接服务。公网验证：CC中转首页 HTTP 200，登录页/注册页可打开，未授权 `/v1/models` HTTP 401，旧 Frist 域名最终跳转到 CC中转主站；Oracle `frist-api.service`、`openclaw-newapi.service`、`apache2`、`frist-api-r2-backup.timer` 均 active。 2026-07-04 追加生产强制模式验收：`FRIST_API_PUBLIC_MODE=1`、`FRIST_API_ENFORCE_PRODUCTION_READINESS=1`、`FRIST_API_ALLOW_INSECURE_PUBLIC_HTTP=0` 已启用；Frist-API 管理员 TOTP 2FA 已开启；R2 备份 `frist-api-20260705T000508Z.tar.gz` 已完成恢复演练并登记；2026-07-05 New-API 主入口已复用同一套 Turnstile/SMTP/TOTP 生产配置。

### CC中转品牌重塑与兑换码生产内测基线 — 本地回归通过

2026-07-04 已把 Frist-API 对外品牌收口为「CC中转」：用户端、管理端、CC Switch 导入名、邮件模板、默认卡密前缀、生产配置示例和静态品牌资产已统一为 CC中转；新增服务说明、服务条款、售后/退款规则和隐私说明四个用户可达页面，用户可见文案不再使用“官方合作/官方授权/平台直营/第三方”等高风险表达，模型价格展示也改为“参考标价”口径。兑换码安全已升级：新生成卡密只在创建响应和导出文本中出现明文，运行数据落库为 `codeHash + codeCipher + codePreview`；闲鱼履约话术按需解密生成，不长期保存完整卡密话术；兑换接口新增 IP + 登录账号双维度限流，降低暴力猜码风险。快速开源复用检查未发现 86GameStore 本身公开仓库；MIT 卡密商城 `34892002/edgeKey` 技术栈与当前链路不一致，本轮不迁移。验证结果：`cd apps/frist-api && node --check server/server.js src/app.js src/admin.js src/core.js src/businessFlow.js server/shared.js server/catalog.js server/email.js` exit 0；`cd apps/frist-api && node --test tests/*.test.mjs` 为 `166 passed / 0 failed / 0 skipped`；`git diff --check` exit 0。生产内测入口为 `https://jiyu.245334.xyz/`。

### Frist-API + QuantumNous/new-api 本机直连栈 — 已跑通

2026-07-04 已把本机运行方式改成“直接跑 QuantumNous/new-api，本机 Frist-API 全面桥接”的路径：New-API 固定 `calciumion/new-api:v1.0.0-rc.4`，容器 `openclaw-newapi` 监听 `127.0.0.1:3000`；Frist-API 容器 `frist-api-server` 监听 `127.0.0.1:3180`。新增 `make new-api-up`、`make frist-api-newapi-setup`、`make frist-api-up/down`；桥接脚本从 `data/newapi/one-api.db` 读取已生成 access token 用户并写入本机 `.env`，不在终端打印密钥。Frist-API New-API adapter 已接管看板、Token、日志/用量、兑换、订阅/充值/邀请读取和可选 `/v1` 网关代理，同时保留 Frist 自研工作台、CC Switch/Codex/OpenCode/Claude/Hermes 导入、兑换码售卖、闲鱼发货和补号助手。验证结果：`node --check scripts/setup_local_newapi_bridge.mjs apps/frist-api/server/server.js apps/frist-api/server/newApiBridge.js` exit 0；`cd apps/frist-api && node --test tests/*.test.mjs` 为 `165 passed / 0 failed / 0 skipped`；New-API `/api/status` 返回 `success=true`、`version=v1.0.0-rc.4`、`setup=true`；Frist Dashboard 返回 HTTP 200；Playwright 打开 `http://127.0.0.1:3180/` 控制台 `0 error / 0 warning`，截图为 `output/playwright/frist-api-newapi-login-20260704.png`。

### Frist-API 86GameStore 风格后台与兑换/闲鱼履约闭环 — 本地审计通过

2026-07-04 已按“克隆上游后台骨架 + 保留 Frist 功能 + 重点打通兑换”的方向完成 Frist-API 本地版本：用户端切为 86GameStore Downstream 浅色工作台，保留 CC Switch / API Key / 测试 / 使用记录 / 可用渠道 / 兑换码 / 套餐订阅；管理端新增 86GameStore 渠道同步、倍率 `+0.1` 下游加价、兑换码批量生成、卡密 `sold` 状态和闲鱼自动发货履约区。追加按 GitHub 高星方案复核后的高保真克隆层：参考 `abi/screenshot-to-code` 的截图转代码方法，未登录页已还原上游公开登录页的蓝紫渐变、居中白色卡片、邮箱/密码/忘记密码/注册/条款提示；管理端补 AdminLTE 式左侧导航和分组锚点。Plus 等上游倍率会以脱敏快照方式保存，示例 `0.18 → 0.28`，已修复刷新后售卖倍率回退为上游倍率的问题。闲鱼链路当前已可“订单号 + 套餐 → 分配未售出卡密 → 生成发货话术 → 买家兑换后自动标记已兑换”；真实“检测闲鱼下单并自动发送”仍需要后续用户授权登录态/浏览器环境后接入，当前不要求用户交出密码。验证结果：Frist-API 语法检查通过；`cd apps/frist-api && node --test tests/*.test.mjs` 为 `165 passed / 0 failed / 0 skipped`；本地 Playwright 审计用户页和管理页通过，用户页与管理页控制台均 `0 error / 0 warning`；截图为 `output/playwright/frist-api-clone-login-20260704.png` 和 `output/playwright/frist-api-admin-clone-shell-20260704.png`。

### 社媒运营插件排程与增长复盘 — 提交前验证通过

2026-07-02 提交前收口验证完成：桌面端 Social 中控、Chrome Social Pilot、Telegram 社媒命令、后端 Social API、排程/最终确认、增长复盘和当前页上下文扫描均保持“只生成待审草稿/只读复盘/人工最终确认”的安全边界；仍不自动发布、不自动评论、不关注/私信、不推广。已清理失效生活自动化/微信优惠券与旧 MITM token 相关冗余路径。验证结果：`git diff --check` exit 0；后端 Python 编译通过；后端全量 pytest exit 0（进度日志统计 `1601 passed / 2 skipped / 0 failed`）；桌面端 `npm run build`、Tauri `cargo check`、Social 静态测试、Chrome 插件 Popup/social-core/page-runner 测试和真实浏览器 smoke 均通过。当前需要注意的边界仍是：真实外发/评论动作必须由用户在已登录页面最终人工确认，不能恢复自动外发。

### Bot 心跳丢失误报 — gptoss 已恢复

2026-07-02 05:49 MDT 已处理 `gptoss` 心跳丢失告警。根因是 `gptoss` 在 03:01:44 启动超时后，`MultiBot.__init__` 已提前把它写入健康检查和群聊路由，但启动失败后没有进入运行注册表，也没有注册自动恢复函数，导致健康检查持续报“Bot 心跳丢失 / 未注册重启函数”。现已把 Bot 健康/路由注册移动到 Telegram polling 启动成功之后，并新增回归测试防止缺 Token 或启动失败的 Bot 残留假心跳。重启 `ai.openclaw.clawbot-agent` 后，`GET /api/v1/status` 显示 qwen235b、gptoss、claude_sonnet、claude_haiku、deepseek_v3、claude_opus、free_llm 均 `alive=true`；新日志中 `gptoss 未注册重启函数=0`、`Bot 心跳丢失=0`。


### 公开仓库敏感告警清理 — 已处理当前可达内容

2026-06-22 已开启 GitHub secret scanning / push protection 后，继续清理审核视角下的敏感告警：本地未推送历史、stash、旧本地实验分支和 Codex turn-diff / snapshot refs 中残留的 Google OAuth Client ID/Secret 已删除并 GC；当前 `main` 与 `origin/main` 同步，工作区干净；当前追踪树、可达 Git refs 和工作区均不包含被 GitHub Push Protection 拦截的 OAuth 值。已清理历史生活自动化敏感配置痕迹，公开仓库只保留必要占位符。GitHub 历史 secret alerts 已核对来源，涉及早期误提交的 `.openclaw` 运行配置、`node_modules`、`.venv312`、Telegram/OpenRouter/Slack/Discord/Google/微信等历史值；当前 open secret alerts 为 0，历史 alerts 已按 revoked 处理。后续仍建议在对应平台轮换/废弃这些旧凭证。

### 开源项目审核准备 — 已补齐基础治理材料

2026-06-22 为提高 OpenAI Codex for OSS 等开源项目审核通过率，根目录新增 Apache-2.0 `LICENSE`，`README.md` 已移除旧的私有/专有许可证表述并补充项目定位、可复用开源价值、安全/合规边界和贡献入口；新增 `docs/013-contributing.md`、`docs/014-security.md`、`docs/015-code-of-conduct.md`、GitHub issue/PR 模板，明确贡献流程、验证清单、漏洞报告、社区行为准则、密钥保护和 API credits 只用于 PR review、测试、文档、安全分析、重构维护，不用于真实交易、刷量、绕过平台风控、未授权抓取、商业客户工作负载或转售。已通过 GitHub CLI 更新仓库公开描述、topics、Discussions、secret scanning、push protection、Dependabot security updates 和 private vulnerability reporting。



### Dependabot 依赖安全收口 — 大部分可修项已处理

2026-06-22 打开 Dependabot security updates 后，GitHub 首次暴露 78 个历史依赖告警。本轮已升级 `.openclaw/extensions/openclaw-weixin`、`apps/openclaw-manager-src`、`packages/clawbot/requirements-dev.txt`、`packages/openclaw-npm` 及其扩展包中的可修安全版本；桌面端 `WorldMonitor` 已移除 `react-simple-maps`，改用 `d3-geo` + `topojson-client` 直接渲染本地地图，从根上去掉旧 d3 漏洞链。`@mariozechner/pi-coding-agent` 上游暂无 patched version，且当前源码未直接 import，本轮已从 `packages/openclaw-npm` 直接依赖移除。最终远端 Dependabot 告警数以推送后 GitHub 重新分析为准；本地 `.openclaw/extensions/openclaw-weixin` 和 `apps/openclaw-manager-src` 的 `npm audit --audit-level=moderate` 均为 0。全量测试中发现 `test_api_routes_regression.py` 会被本机 `OPENCLAW_API_TOKEN` 污染成 401，已在测试层固定无 Token 开发模式并用带 token 环境复验 12/12 通过。


# HEALTH — 系统健康状态

> 最后更新: 2026-07-02

---

### X 全自动运营任务 — 已切换为中英文热点追踪涨粉号

2026-06-22 已按用户新方向把 X 自动运营从 AI/视频蒸馏垂直号切换为“中文/英文热点追踪 + 抽象好玩短推”：默认排程设计为 08:30 / 10:30 / 12:30 / 15:00 / 17:30 / 20:30（America/Denver）各尝试发布 1 条。链路现在优先抓微博/百度/知乎真实热榜、B站热榜、Google News 中文/英文 RSS、Hacker News Algolia front page，并用热度、排名、可吐槽性/抽象程度、中英文覆盖和安全风险评分；YouTube RSS/字幕蒸馏保留为低优先级补位，不再作为默认账号方向。此前 2026-06-22 11:35 MDT 已通过同一 LaunchAgent 真实自动发出 1 条推文，取证链接 `https://x.com/BonoDJblack/status/2069112204343779412`。剩余边界：微博/百度/知乎接口偶发超时会自动降级到 B站/HN/Google News；B站仍以标题/热榜级语义为主，若要更准地追评论梗/小红书/微博实时梗，后续建议接入 MediaCrawler 或平台登录态评论采集；为降低 X 风控，当前不做批量关注/评论/点赞。

2026-06-23 已按用户要求切到“先确认人设/内容，再发布”模式：LaunchAgent 当前未加载，`x_auto_morning_post.py --publish-next` 未审核时只返回 `requires_review=true`，不会外发；桌面端 Social 页已能统一看到 X 自动运营草稿并执行“确认内容 / 打回 / 最终发布确认”。热点过滤已追加官方政治口号、硬新闻、核电/战争/枪击和 AI 垂直模型新闻降权/过滤，最新候选草稿保持 `review_status=pending`，等待用户确认人设与内容后再恢复外发。

2026-06-23 追加统一“浏览器运营插件”工作台：后端新增只读聚合接口 `GET /api/v1/social/ops-workspace`，一次返回 X / 小红书 / 闲鱼三平台 SaaS 卡片、审核计数、人设确认、skills 审计和闲鱼客服状态；桌面端 Social 页优先使用该接口，失败再降级旧接口。当前判断：现有 `social-autopilot` Skill 与 `social-persona.md` 仍偏 AI/程序员/效率工具号，和用户想要的“追热点、抽象好玩、最快涨粉”不完全一致，因此继续保持人工确认闸口，不能恢复自动外发。

2026-06-23 继续补齐“先确认人设内容”的产品闭环：新增 `social/persona-review` 人设确认流和 `persona_review.py` 状态文件，工作台会展示“热点抽象观察员”提案、样稿预览、确认/打回按钮。确认人设只保存方向，不会恢复自动外发；内容草稿仍必须逐条确认后才允许进入最终发布确认。

2026-06-23 人设确认卡进一步接入真实待审草稿样稿：`social/ops-workspace` 会把当前 X/小红书待审核草稿整理为 `persona_check.review_samples`，前端优先展示这些真实样稿，避免用户只看静态模板无法判断内容风格。

2026-06-23 继续收紧旧社媒自动驾驶安全边界：`SocialAutopilot` 现在固定处于审核模式，晚间生产出的 X / 小红书草稿默认是 `needs_review/pending`；午间自动回复/蹭评直接跳过；晚间发布任务即使遇到已确认草稿也不会自动外发，只提示到桌面端执行最终发布确认。统一工作台已暴露 `review_mode=true` 与 `external_actions_locked=true`，并把真实待审样稿上限扩到 6 条，平台卡片新增“下一步/样稿预览”。

2026-06-23 补齐浏览器控制插件的安全操作入口：新增 `social/browser-control` 后端 API、Tauri IPC 和桌面端卡片按钮，允许在统一工作台里执行“打开 X / 打开小红书 / 登录 / 刷新状态”等安全动作；同一入口显式拒绝 publish/reply/delete 等外部变更动作，仍必须走草稿审核和最终发布确认。

2026-06-23 追加只读审核包与开源轮子复查：新增 `GET /api/v1/social/review-pack`，一次返回“热点抽象观察员”人设提案、X/小红书真实待审样稿、guardrails、skill 审计和轮子复用判断；当前样稿 `sample_count=8`、`auto_publish_enabled=false`、`requires_owner_review=true`。已复查 `social-autopilot` Skill 和 `social-persona.md`：旧配置仍偏 AI 工具号与全自动互动，不直接启用；继续复用项目内 `sau_bridge`、`media_crawler_bridge`、`social_browser_worker.py`，并确认 GitHub 上 `NanmiCoder/MediaCrawler`（51,767⭐，覆盖小红书/B站/微博等采集）和 `dreammis/social-auto-upload`（12,811⭐，覆盖小红书/YouTube/Bilibili 等上传）可作为后续深度采集/搬运轮子。

2026-06-23 Chrome 插件第一阶段已从 Browser Relay 壳升级为 `OpenEverything Social Pilot`：`manifest.json` 默认打开 `popup.html`，Popup 能识别 X / 小红书 / 闲鱼、启动/暂停本标签页运营状态、同步到后端 `GET/POST /api/v1/social/extension/status`；`options.html` 已变成 no-code SaaS 高级设置页，支持人设标签、主内容模型、网页登录额度优先、生图模型、热点来源、自动化强度、互动强度、本地 API Base URL 和 Relay 兼容配置。当前健康判断：插件已完成“平台识别 + 设置保存 + 状态同步 + 安全闸口”的骨架闭环，但仍未实现页面自动填入、网页登录免费额度自动调用、热点深采集、生图、排程发布和互动；这些能力继续受人工审核闸口保护。

2026-06-23 Chrome 插件继续向“当前页/热点 → 待审草稿”推进：Popup 新增“根据当前页生成待审草稿”，后台只读采集当前标签页标题、选中文本、可见标题/短文本和少量正文摘要，通过 `POST /api/v1/social/extension/drafts` 写入统一社媒草稿审核队列；生成的草稿固定为 `needs_review/pending`，并继续强制 `auto_publish_enabled=false`、`external_actions_locked=true`。后续又补齐插件内审核、热点池、填入点检测、安全填入、待发布排程、插件人设与样稿确认面板、插件排程提醒面板、到点提醒和最终确认：`social-page-runner.js` 可单测验证小红书标题/正文拆分、X compose 合并填入和不点击发布按钮；`POST /api/v1/social/extension/drafts/{draft_id}/schedule` 只把已确认草稿写入 `extension_schedule`，`ops-workspace` 可见排程摘要；排程到点后转为 `awaiting_final_confirmation`，`GET /api/v1/social/extension/schedule` 会把队列和草稿预览同步到插件“看排程”面板，`final-confirm` 仅标记 `ready_for_manual_publish`，仍不调用发布器。当前仍未启用网页登录免费额度、生图、排程外发和自动互动；人设确认只代表方向确认，不等于发布授权，下一步应在真实已登录页面继续校准选择器。

2026-06-23 继续补齐真实页面校准闭环：插件 `socialPageProbe` 完成当前页只读检测后，会把平台、URL、ready、可用字段名和失败原因通过 `POST /api/v1/social/extension/page-probe` 同步到中控 `page_calibration`，并丢弃 selector 等页面细节；Popup 会明确提示“校准结果已同步”或“本地检测成功但未同步中控”。该能力只用于判断 X / 小红书 / 闲鱼页面是否已打开可填输入框，仍不点击发布、发送、评论或关注按钮。

2026-06-23 继续补强真实页面校准稳定性与冷启动闭环：`buildAutofillSelectors()` 已覆盖 X 嵌套 contenteditable / DraftEditor、小红书 Quill `.ql-editor` / aria-placeholder、闲鱼 placeholder / aria-label 聊天编辑器等常见真实页面变体；新增回归确保探测模式只读、不改写内容。App Social 的 `growth_draft_action` 在暂无增长样本时也保持可用，走 `fallback_mode=cold_start_hotspot_pool` 从热点池生成待审草稿；有高信号样本时继续复用增长反馈画像。Playwright 已用当前源码临时 API `127.0.0.1:18791` 截图验证按钮可点击且文案明确“不自动发布、不自动评论”。

2026-06-23 继续补齐产品线 1 的 Telegram 中控审核闭环：新增 `/social_review_drafts`、`/social_review_approve`、`/social_review_reject`、`/social_review_schedule`、`/social_review_schedule_queue`、`/social_review_final_confirm` 和“查看待审草稿/确认草稿/打回草稿/排程草稿明天8点/查看社媒排程/最终确认草稿”等自然语言路由。Telegram 现在可以远程查看统一草稿队列、确认、打回、加入待发布排程、查看到点排程并做最终确认；序号与插件草稿 ID 均可用，中文口语时间会规整为带时区排程时间。安全边界不变：确认只改审核状态，排程只进入 `queued_for_owner_publish`，最终确认只标记 `ready_for_manual_publish`，不自动发布、不自动评论、不关注/私信、不推广。

2026-06-23 热点池进一步升级为 MCN 选题卡：`GET /api/v1/social/extension/trends` 现在除标题/来源外，还按 X / 小红书 / 闲鱼返回目标人群、内容角度、平台打法、涨粉理由、风险等级、风险提示、执行步骤和 hook 模板；插件“抓热点”卡片会展示这些运营信号，并在生成热点草稿时把内容角度/打法/风险写入上下文。当前状态：更接近“追热点 + 平台打法 + 可执行内容”的运营产品，但仍需要真实账号数据反馈来做排序权重闭环。

2026-06-23 草稿生成继续补齐平台化内容计划与素材计划：`POST /api/v1/social/extension/drafts` 现在为 X / 小红书 / 闲鱼草稿返回 `content_plan`、`image_plan`、`platform_style`、`format_checklist`、`safety_checklist`、`cost_route`；Popup 草稿编辑器新增“素材计划”卡片，可展示内容结构、封面提示词、图片素材提示词、安全清单和模型路由提示。图片计划默认 `auto_generate=false`，只给人工确认后的生图提示词，不自动消耗 GPT Image / Gemini / Grok 等网页或 API 额度；排程提醒回填草稿时也会保留素材计划，避免到点最终确认时丢失封面和安全边界。

2026-06-23 继续补齐网页登录免费额度的安全用法：Chrome 插件新增“网页登录额度”卡片，可基于当前待审草稿生成 Gemini / Grok / ChatGPT 网页提示词，并只做“复制提示词 + 打开模型网页”。Background 白名单限制为 Gemini、Grok、ChatGPT 三个网页，且明确不自动粘贴、不自动提交、不自动生图、不自动发布；用户需要在网页手动提交后，把结果复制回插件继续审核。

2026-06-23 继续补齐运营复盘/增长反馈闭环：Chrome 插件新增“采表现”入口，可在已发布内容页只读采集点赞、评论、转发、曝光、收藏等可见指标，并通过 `POST /api/v1/social/extension/performance` 写入 `extension_performance`、草稿 `performance_snapshots` 和 `growth_feedback`。该数据只用于后续热点排序、人设复盘和 MCN 选题权重，不提供推广/boost/刷量路径，也不会触发自动发布、评论或再发布。热点池已开始读取这些增长反馈画像：历史 `high_signal` 或高赞/高评/高曝光内容会给相似标题/标签候选增加 `growth_feedback_boost`，并在插件卡片展示“历史高信号”原因。新增 `GET /api/v1/social/extension/growth-feedback` 和插件“看复盘”面板，可直接查看历史高信号内容、关键指标、标签和下一步选题建议。



2026-06-24 继续补齐产品线 1 的 Telegram 中控策略入口：新增 `/social_strategy [打法] [平台]`，并支持“切到X抽象热点打法 / 把社媒运营打法改成小红书生活攻略”等中文自然语言路由。Telegram 现在可以和 App/Chrome 共用同一个 `strategyPreset` / `strategy_summary`，远程切换财富前沿、抽象热点、小红书生活攻略、闲鱼成交客服等打法；该动作仍只改策略，不发布、不评论、不关注/私信、不推广。

2026-06-24 继续补齐 no-code 运营打法闭环：Chrome 插件高级设置新增的 `strategyPreset` 已贯通到后端 `strategy_summary` 与 App Social 中控，当前支持自动匹配、X 财富前沿、X 抽象热点、小红书生活攻略、闲鱼成交客服五种打法；App 会展示当前运营打法、目标人群、内容重点和增长闭环，平台卡也能看到对应 `strategy_preset`；App 还可通过 no-code 下拉保存打法到 `POST /api/v1/social/extension/strategy`。这解决了“插件里选了打法，但 App/Telegram 中控看不到/改不了策略”的断点；安全边界不变，打法只影响待审草稿、内容计划、素材计划和热点排序，不授权自动发布或自动评论。

2026-06-24 继续补齐三端状态一致性：Chrome Popup / Options 打开时会通过 Background 的 `socialStatusFetch` 读取 `GET /api/v1/social/extension/status`，把 App/Telegram 中控保存的合法 `strategyPreset` 自动回写到 Chrome 本地设置；同步过程继续保留本地 `automationLevel` / `interactionLevel` 安全默认值，避免任何远程状态打开自动发布或自动互动。Telegram `/social_strategy` 无参数时现在可只读查询当前打法、平台增长闭环、待审草稿、可发布未最终确认和排程数；带参数时才切换打法。

2026-06-24 真实浏览器 QA 发现并修复 Chrome 插件 Options 高级设置页的表单语义细节：Gateway token 密码框此前不在真实 form 内，Chrome 会提示 `Password field is not contained in a form`。现已用 `<form id="social-settings-form">` 包住 no-code 设置区与底部操作区，保存按钮改为 `type="submit"`，`options.js` 监听 submit 并阻止默认跳转后保存；真实 Google Chrome 复验 `hasForm=true`、`tokenInsideForm=true`、`saveType=submit`、控制台无 warning/error，截图已保存到 `output/playwright/social-pilot-options-form-fixed-20260624.png`。该修复只改善设置页浏览器 UX，不改变发布/评论安全闸口。

2026-06-24 继续把当前页热点/上下文采集收敛进共享页面执行器：`social-page-runner.js` 新增 `runSocialPageContextScanInPage()`，可只读采集 X 趋势/推文、小红书笔记标题/正文/评论、闲鱼商品/聊天/描述等信号，并返回 `selection`、`headings`、`trends`、`bodyText`。`background.js` 的当前页生成待审草稿链路已改为通过 `chrome.scripting.executeScript` 调用同一个 runner，真实 Chrome 烟测已覆盖三平台 `contextReady=true`、`contextSignals>0`、`buttonClicks=0`。这让“我打开平台页面 → 插件读当前热点/上下文 → 生成待审草稿”的入口更稳定，但仍只读采集，不点击发布/发送/评论按钮。

2026-06-24 继续把“当前页热点/上下文采集”从后台能力做成插件内可见 no-code 面板：Popup 新增“当前页热点/上下文”区域和“扫当前页”按钮，扫描结果会以卡片展示趋势、标题、正文摘要和选中文本，点击卡片才会生成待审草稿。Background 新增 `socialPageContextScan` 桥接，仍复用共享 runner 且强制 `publishIntent=false` / `auto_publish_enabled=false`。真实 Chrome 烟测已额外打开 Popup 预览页，确认 `page-context-panel` 展开、草稿编辑器出现，并保存截图 `output/playwright/social-pilot-browser-smoke-20260624/social-pilot-popup-context-20260624.png`。

2026-06-24 继续把 Chrome 插件主执行链路从单测推进到真实浏览器可重复验收：新增 `test/social-browser-smoke.mjs`，用本机 Google Chrome 模拟 X / 小红书 / 闲鱼页面，加载真实 `social-core.js` 和 `social-page-runner.js`，验证三平台都能识别 URL、探测输入框并把待审/已确认草稿安全填入页面。页面内已监听 Post / 发布 / 发送按钮点击，任何按钮点击都会让烟测失败；当前三平台结果均为 `ready=true`、`filled=true`、`buttonClicks=0`，截图位于 `output/playwright/social-pilot-browser-smoke-20260624/`。这证明 L1“自动填入页面但用户手动发布”已具备可重复 QA 证据，但仍不代表真实平台最终发布已放开。

2026-06-23 继续补齐安全互动闭环：Chrome 插件新增“扫互动”入口，能在当前 X / 小红书 / 闲鱼页面只读扫描评论、聊天或可回复信号，并点击候选卡片生成 `chrome_extension_interaction_scan` 来源的待审回复草稿。该链路只读页面文本，不点击回复/发送/评论/发布按钮；Background 只提供 `socialInteractionScan`，不提供自动评论提交路径；后端仍把草稿固定为 `needs_review/pending`，确认前不会评论或外发。

## 当前系统状态: 🟡 可运行且生产已切到 Oracle, 剩余为旧 Key 补录和外部账号判断

| 指标 | 值 |
|------|------|
| 后端进程 | ✅ 运行中 (PID 自动重启) |
| 7 Bot 在线 | ✅ 7/7 |
| IBKR | ✅ 已连接 (DUP113460) |
| API 池 | ✅ 139/142 活跃源 |
| 闲鱼客服 | ✅ 自动回复活跃 |
| 社媒自动驾驶 | 🟡 草稿生成、素材计划、网页登录额度接力、只读互动扫描、增长复盘和 Telegram 审核/排程中控可运行；旧自动互动/自动发布已锁住，外部发布/评论必须走人工最终确认 |
| 测试 | ✅ 2026-07-05 CC中转闲鱼自动发货/API/WorldMonitor focused 回归 `85 passed / 0 failed`，`xianyu_live.py` / `xianyu_context.py` / `xianyu_admin.py` / `world_monitor.py` / 相关测试 `py_compile` 通过；同日 `make test` 全量跑到 `[100%]` 且退出码 `0`；2026-07-04 Frist-API Node 全量 `166 passed / 0 failed / 0 skipped`，语法检查通过，用户页/管理页本地 Playwright 审计通过；2026-07-03 收口验证：后端 pytest `1606 passed / 2 skipped / 0 failed`，`make lint` 0 遗留，桌面端 typecheck/lint/build 通过，桌面端与 Frist-API `npm audit --audit-level=high --omit=dev` 均 0 高危，Python 3.12 环境 `pip check` 无破损依赖，`.venv312/bin/python -m pip_audit` 无已知漏洞，可提交文件 gitleaks 0 泄露，可达 Git 历史 gitleaks 0 泄露，`git diff --check` 0 问题。历史基线：后端 pytest 1601 passed / 2 skipped / 0 failed，Frist-API 157/157，桌面端 typecheck/build 通过；本地必须走 `make test` 或 `.venv312/bin/python -m pytest`，不能直接用系统 `pytest`。 |
| Frist-API 入口 | ✅ 生产内测入口 `https://jiyu.245334.xyz` 已切到 Oracle ARM `150.136.73.15`，通过 Cloudflare proxied A + Apache/Origin CA 闭环，外网首页/Dashboard 200；旧 `frist-api.245334.xyz` 已跳转到 CC中转主站，旧腾讯云/nip.io 入口只保留为冷回滚，不再对用户宣称为可用兜底 |
| Frist-API | ✅ AI_POOL 自动熔断、真实调用失败降级、客户可见模型真实上游优先和 AGPL 源码入口已处理。2026-07-04 本地已新增 86GameStore Downstream 后台骨架、渠道脱敏同步、倍率 `+0.1`、兑换码生成/管理/核销和闲鱼自动发货履约雏形。New-API 生产迁移已按授权执行：用户 19、token 1、充值/订单 4、兑换码 2、日志 162 已迁入，回滚目录为 `/opt/frist-api/backups/newapi-migration-20260703T005433Z`；Oracle 当前以 `frist-api.service` + `openclaw-newapi.service` 承接生产，R2 定时备份在 Oracle 启用。16 个历史 `enc:v1:` 用户 Key 因旧加密密钥缺失未迁移，必须重新生成/补录。SMTP 密码已通过隐藏输入方式写入 Oracle root-only 环境文件，并用 Gmail 465/TLS 发出生产测试邮件。 |
| Frist-API 批注修复 | ✅ 2026-05-09 已处理 Logo、状态灯、工作台折叠菜单、通道展示批注、管理员快捷入口、固定工作台导航、趋势图 hover 数据和首页当前项背景；423×718 浏览器复验无横向溢出，Logo 105px，状态灯 18px，导航默认折叠且切页后自动收起，顶栏“登录/身份码/管理”可操作，`.provider-models` 为 0，控制台 0 error/0 warning；同日追加 319×718 极窄屏修复，Dashboard 与 CC Switch 本地浏览器复验 `scrollWidth=319`，顶栏账户按钮 173px，CC Switch 用量说明宽 235px 且无横向裁切 |
| Frist-API Oracle 生产 / 腾讯冷回滚 | ✅ 2026-07-03 已从国内腾讯云切到 Oracle ARM `150.136.73.15`；2026-07-04 CC中转子域名上线：Oracle `/opt/frist-api` 运行 `frist-api.service`、`openclaw-newapi.service`、`apache2` 和 `frist-api-r2-backup.timer`；Cloudflare `jiyu.245334.xyz` 代理到 Oracle，旧 `frist-api.245334.xyz` 跳转到 CC中转。公网 Dashboard HTTP 200，未授权 `/v1/models` HTTP 401；最新外网压测 Dashboard 100/100 HTTP 200（p95 0.792s），models 50/50 HTTP 401（p95 0.758s）。腾讯云 `/opt/frist-api` 仅保留冷回滚数据和备份，旧 `frist-api-server` / `openclaw-newapi` 容器已停止，旧 R2 timer 已禁用，避免双源探测和备份漂移。 |
| ClawBot 腾讯云部署 | ✅ 2026-05-08 已单文件部署闲鱼管理页转义修复到 `/home/clawbot/clawbot/src/xianyu/xianyu_admin.py`；远端备份 `/home/clawbot/clawbot/backups/xianyu_admin_20260508155652_before_escape.py`；远端 `py_compile` 通过，`clawbot.service` 重启后 active |
| 微信命令 | ✅ 27/27 可用 (25✅ 2⚠️数据空) |
| Ollama 内存 | ✅ 151MB (原9.3GB) |
| 日志目录 | ✅ 2026-05-09 已清理本地 `packages/clawbot/logs/` 旧运行日志；生产日志和远端备份未清理 |
| 本地冗余 | ✅ 2026-05-09 已清理 `.DS_Store`、源码/测试 `__pycache__`、`.pytest_cache`、`.ruff_cache`、`.playwright-mcp`、Playwright/Expect 调试产物、Frist-API 历史审计截图和根目录临时截图；`.env`、`.openclaw/`、runtime 数据、`node_modules`、`.venv312` 保留 |
| 文档治理 | ✅ 主项目 docs 从散落状态统一归集到 43 个编号 Markdown，扁平化无子目录，历史截图/旧审计/散落设计报告/冗余打包文档已清理；2026-05-09 已补本轮清理日志 |
| 公开仓库安全 | 🟡 Git 历史已重写并通过本地扫描；本轮新增 CI secret/audit 门禁并准备推送触发 GitHub 重算；历史泄露凭据是否轮换由 Carven 自行判断 |

---

## 已知问题

### 🔴 阻塞 / 🟠 重要

| ID | 分类 | 描述 | 发现日期 | 状态 |
|----|------|------|----------|------|
| HI-907 | AI_POOL/INFRA | CC中转生产内测曾因 New-API 与 Frist 本地库存均无健康上游而阻塞正式售卖；2026-07-05 用户补充的 3 条 86Game 上游 Key 已脱敏探测并接入生产内测，New-API 当前 3 个可用渠道/15 个模型，OpenAI 与 Claude 真实调用 200，readiness 返回 `ready=true`；本机闲鱼助手已具备已付款自动发货、稳定 `orderId` 幂等防重复发卡（含 URL 参数真实订单号识别）和已付款状态变体/字段位置识别、补救队列、浏览器发货助手、后台只读巡检、CC Switch 导入入口上架锁、后台严格门观察、实单验收包、运营统一快照和 macOS 状态提醒；2026-07-06 真实测试单因闲鱼推送漏单仍处于 `manual_delivery_ready/pending_rescue=1`，需要打开对应闲鱼聊天页由插件/人工发出后再继续买家兑换、创建 API Key、CC Switch 导入和模型调用严格门 | 2026-07-05 | 🟡 生产内测可发货但当前有待补发真单，正式售卖锁等待真实小额订单闭环 |
| HI-872 | UX | Frist-API `#switch` 页面曾因导出模型展开逻辑被部分上游库存裁掉 `gpt-5.4`、`gpt-5.4-mini`、`gpt-image-2`、`gpt-5.3-codex`，且品牌标被 Tabcode 皮肤覆盖；已补完整 OpenAI 模型族可见逻辑、恢复原品牌标并加回归 | 2026-05-05 | ✅ 已处理 |
| HI-873 | INFRA | Frist-API 免费 nip.io 裸域名 `101-43-41-96.nip.io` 曾和品牌域名并列直接服务同一页面，用户误以为有两个网站；历史阶段已收口裸域名跳转。2026-07-04 后正式入口改为 `https://jiyu.245334.xyz`，旧 `https://frist-api.245334.xyz` 跳转，旧 nip.io 只保留腾讯冷回滚排障，不再作为用户内容入口 | 2026-05-05 | ✅ 已处理 |
| HI-817 | SECURITY | 公开 Git 历史曾提交 `.openclaw/openclaw.json*`、`.openclaw/devices/paired.json` 和数据库文件；当前工作树、可达历史和发布工件扫描未发现新增明文，CI 已阻断复发。第三方平台是否完成历史凭据轮换没有平台侧回执，不能宣称关闭；因当前生产凭据只从 root-only/ignored 配置加载且无代码旁路，降级为 P2 人工残余。 | 2026-04-28 | 🟡 P2 人工残余，平台轮换待证明 |
| HI-818 | SECURITY | 本机 ignored `.env` 与浏览器 profile 日志曾含真实 API token；当前跟踪文件和发布工件无新增明文，生产读取边界不把值写日志或 WebView。第三方平台轮换仍缺平台侧证明，按 P2 人工残余登记，不计入“已关闭”安全项。 | 2026-04-28 | 🟡 P2 人工残余，平台轮换待证明 |
| HI-885 | BUG | 后端全量测试发现 `src.api.routers.store` 被删除但 `api/server.py` 仍挂载，导致 APIServer 初始化失败；已恢复 `/api/v1/store/catalog` 和 `/api/v1/store/categories` 最小兼容路由，并用 1491 passed 回归确认 | 2026-05-08 | ✅ 已处理 |
| HI-886 | INFRA | `make new-api-check` 显示 New-API 本地源码和 Compose 镜像曾为 `v1.0.0-rc.2`，GitHub 最新为 `v1.0.0-rc.4`；已通过自动同步 PR #1 更新 submodule 和 Compose 镜像到 `v1.0.0-rc.4`，并复验 compose 配置通过。2026-07-03 生产 New-API 已迁到 Oracle ARM release 二进制 `openclaw-newapi.service`，腾讯 Compose 只保留冷回滚 | 2026-05-08 | ✅ 已处理 |
| HI-887 | AI_POOL/PERF | 86GameStore/余额站类渠道已补日消费限额、当日消费高于剩余额度且慢线时自动熔断、慢线降级到备用健康渠道和一次性告警；补号入库可保存 `dailySpendLimitCents` / `slowLatencyThresholdMs` / `costSensitive`。充值本身仍由用户付款处理。 | 2026-05-08 | ✅ 已处理（充值为人工事项） |
| HI-890 | SECURITY | 服务器 root 密码曾在对话中明文出现。2026-08-04 只读复核确认 Oracle root 密码修改日期晚于暴露日期且 fail2ban 活跃；腾讯冷回滚机禁止密码认证并限制 root 为密钥登录，fail2ban 活跃。仓库和历史扫描无该值，因此从 P1 降为 P2 运维观察；Oracle 仍允许 root 密码登录，后续应迁移为密钥专用，但当前暴露密码已失效。 | 2026-05-08 | 🟡 P2 运维观察，已验证暴露口令不可用 |
| HI-891 | INFRA | `New-API Scheduled Sync` 最近失败 run `25576027773` 卡在 `docker compose -f docker-compose.newapi.yml config`：CI 缺少 `NEWAPI_INITIAL_TOKEN`，导致已完成的 New-API 同步无法进入创建 PR；已给 compose 校验注入 CI 占位 token，并让检查脚本用退出码 `2` 明确表示“需要同步”、其他非零表示真实错误；复验 run `25588894721` 已成功并创建 PR #1 | 2026-05-08 | ✅ 已处理 |
| HI-892 | UX | 内置浏览器审计发现 Frist-API 隐藏视图的多个返回按钮文本箭头会在可访问性快照中聚合为 `← ← ←`，对屏幕阅读器和自动化审计产生噪音；已将 `.back-home::before` 改为纯 CSS 图形箭头，本地浏览器复验不再出现箭头文本且控制台无 error/warn | 2026-05-08 | ✅ 已处理 |
| HI-893 | UX | 内置浏览器复审发现账户弹窗密码字段不在真实 `form` 内，浏览器密码管理器会给出结构提示；已将登录/注册、改密码、重置密码和身份码激活拆成独立 `data-auth-form`，补齐 `autocomplete`，并让回车提交复用原处理逻辑 | 2026-05-08 | ✅ 已处理 |
| HI-894 | INFRA | 审计入口复核发现直接运行系统 `pytest` 会命中本机 Python 3.9 用户级脚本，导致 Python 3.12 项目代码被旧解释器误判；已将 AGENTS 和快速导航命令收口为 `make test` / `.venv312/bin/python -m pytest`，并用 `make test` 复验 | 2026-05-08 | ✅ 已处理 |
| HI-895 | INFRA | 腾讯云 New-API 远端 compose 曾仍为 `v1.0.0-rc.2`；2026-05-09 已重新备份运行数据，成功拉取 `calciumion/new-api:v1.0.0-rc.4`，并处理共享服务器 `127.0.0.1:3000` 端口冲突和 `data/newapi` UID 501 权限问题。2026-07-03 后 Oracle `openclaw-newapi.service` 为生产，腾讯旧 `openclaw-newapi` 容器已停止并保留冷回滚 | 2026-05-08 | ✅ 已处理 |
| HI-896 | AI_POOL/BUG | 已补“探测健康但真实调用失败”的降级：真实聊天返回 503/401 时自动标记上游 failed/exhausted、清理会话粘滞、一次性告警，并避免面板继续把该渠道展示成可用。补充/轮换真实上游 Key 仍是平台账号人工事项。 | 2026-05-09 | ✅ 代码侧已处理，补 Key 为人工事项 |
| HI-897 | INFRA/DOCS | 本地工作区遗留可重建缓存、调试日志和审计截图容易干扰后续审计基线；已清理 `.DS_Store`、`.playwright-mcp`、`.pytest_cache`、`__pycache__`、`.ruff_cache`、Playwright/Expect 临时产物、历史审计截图和本地旧日志，并保留运行配置、runtime 数据、依赖环境与生产备份 | 2026-05-09 | ✅ 已处理 |
| HI-898 | UX/AI_POOL | 移动端批注发现 Frist-API 顶栏状态灯和 Logo 挤压、工作台导航占屏、连通性卡按 Claude/OpenAI 模型分类且存在默认延迟疑似 mock；已改为小状态点、紧凑 Logo、默认折叠导航、卡商号池渠道展示、60 秒刷新口径和无真实延迟空态，并用 423×718 浏览器复验 | 2026-05-09 | ✅ 已处理 |
| HI-899 | UX/AI_POOL | 移动端管理员入口仅在账户弹窗底部，且无人请求时缺后台 Key 巡检，导致“看起来已连通但真实 Key 失效”不易被及时发现；已新增顶栏 `身份码/管理` 快捷入口、后台 60 秒巡检、Key 认证/额度异常自动降级和一次性补号提醒（Telegram/Webhook） | 2026-05-09 | ✅ 已处理 |
| HI-900 | UX | 浏览器批注发现 Frist-API 用户端 Logo 被退回单字母 F、趋势图鼠标移入不显示数据、首页导航当前项有大块背景且页面像脱离左侧导航；已恢复红白斜切抽象 Logo、给趋势图补整块 hover/键盘聚焦数据浮层、把工作台导航固定在左侧并让所有内容在右侧 `workspace-content` 内切换，当前项只保留细线提示 | 2026-05-09 | ✅ 已处理 |
| HI-901 | UX | 319px 移动端批注发现 Frist-API 顶栏语言/状态/登录余额遮挡、工作台折叠菜单箭头溢出、模型消耗空饼图过于单调、异常/通道空态缺说明、语言按钮像完整中英文切换、CC Switch 和用量教程比例裁切；已改为双行顶栏、固定箭头、解释型空状态、语言偏好提示和 CC Switch 两列/单列移动布局，并用 319×718 浏览器回测无横向溢出 | 2026-05-09 | ✅ 已处理 |

### 🟡 一般

| ID | 分类 | 描述 | 发现日期 | 状态 |
|----|------|------|----------|------|
| HI-802 | BUG | /monitor/news 首次调用可能超时 (RSS 20源+AI摘要) — 缓存热后正常 | 2026-04-26 | 🟡 已知 |
| HI-804 | BUG | G4F 服务 uptime 显示 0m — 进程检测关键词可能不匹配 | 2026-04-26 | 🟡 低优先 |
| HI-812 | BUG | 微信 iLink bot token 在平台侧失效(errcode=-14) 时，代码已给出清晰“需要重新扫码”提示、一次性告警并避免伪造 token；真实重新扫码授权仍需用户在 iLink/终端完成。 | 2026-04-26 | ✅ 代码侧已处理，扫码为人工事项 |
| HI-888 | SECURITY | `gitleaks` 扫描当前 HEAD 仍命中 `docs/007-operations.md` 中环境变量示例的 `generic-api-key` 误报；已改写为“变量名 + 取值”格式并复扫 | 2026-05-08 | ✅ 已处理 |
| HI-889 | SECURITY | 桌面端新闻/世界监控曾使用 `textarea.innerHTML` 解码外部文本，闲鱼管理页把接口返回字段拼入 `innerHTML` 前缺少统一转义；已改为安全实体解码和 `escapeHtml()` 转义，并部署远端闲鱼管理页修复 | 2026-05-08 | ✅ 已处理 |

### 已修复 (本轮)

| ID | 分类 | 描述 | 修复日期 |
|----|------|------|----------|
| HI-905 | SECURITY/BUG | CC中转生产强制模式开启后，历史 runtime 已带 `__encryption` 标记但旧数据加密 key 不可恢复时，管理接口曾因 `enc:v1:` 解密失败返回 500；已改为隔离旧密文字段并提示重新生成，生产 2FA/readiness/备份登记恢复正常 | 2026-07-04 |
| HI-805 | BUG | 金融指数全零 — yfinance Tickers 批量请求失败无错误提示 | 2026-04-26 |
| HI-806 | BUG | IBKR accountSummary "event loop already running" — 同步调异步 | 2026-04-26 |
| HI-807 | BUG | /monitor/extended 超时 54s+ — 外部API串行+重复RSS拉取 | 2026-04-26 |
| HI-808 | PERF | 日志文件每10秒生成一个,累积1800+文件168MB — loguru配置错误 | 2026-04-26 |
| HI-809 | UX | 微信欢迎消息不完整,只展示8个命令 | 2026-04-26 |
| HI-810 | BUG | 微信 cmd_iorders(233) 映射错误端点 | 2026-04-26 |
| HI-811 | BUG | 微信 cmd_dashboard 不可达(无编号映射) | 2026-04-26 |
| HI-813 | BUG | cmd_status(102) 映射路径错误(/system/status→/status) | 2026-04-26 |
| HI-814 | UX | 12个有API的微信命令未映射,走LLM兜底(300/407/500等) | 2026-04-26 |
| HI-815 | UX | 热点话题(300)只显示"[10项]",全球情报(407)嵌套dict未展开 | 2026-04-26 |
| HI-801 | PERF | Ollama 模型启动后常驻内存 9.1GB — 已配置 KEEP_ALIVE=5m 自动卸载 | 2026-04-26 |
| HI-803 | TECH_DEBT | 微信命令路由同步到腾讯云 wechat_receiver.py | 2026-04-26 |
| HI-816 | INFRA | 创建 Makefile + BUILD_GUIDE.md 构建规范化 | 2026-04-27 |
| HI-819 | INFRA | Git 密钥扫描 + 本地冗余清理：移除可重建缓存约4.4GB、删除含 token 痕迹的浏览器临时日志、补充忽略规则 | 2026-04-28 |
| HI-820 | SECURITY | Git 全历史重写完成：移除敏感历史路径、数据库/依赖/构建产物、扫描器样例噪音；清理后 gitleaks/trufflehog 历史扫描 0 命中 | 2026-04-28 |
| HI-821 | TECH_DEBT | Makefile 测试入口优先使用系统 Python 导致 pytest 缺失；API RPC 价格补齐和社媒 Cookie 检测存在重复实现 | 2026-05-01 |
| HI-822 | TECH_DEBT | AGENTS/SOP/索引仍指向历史大写文档路径；部分抽象类和聚合类保留空占位语句 | 2026-05-01 |
| HI-823 | INFRA | `make lint` 依赖 ruff 但开发依赖未声明；已补齐 requirements-dev 与依赖注册表 | 2026-05-01 |
| HI-824 | BUG | Frist-API 轻量后端静态首页因绝对路径归一化返回 403；已补回归测试并修复为同域 200 | 2026-05-01 |
| HI-825 | SECURITY | Frist-API 公开充值按钮会直接给用户加余额；已改为待处理充值单 + 管理端人工确认入账，生产默认关闭演示充值 | 2026-05-01 |
| HI-826 | TECH_DEBT | Frist-API 补号缺少直连/代理择优、上游不支持模型列表时的 fallback 探测和按真实 usage 扣费；已补齐轻量实现并纳入回归测试 | 2026-05-01 |
| HI-827 | ARCH_LIMIT | Frist-API 网关缺少公开可用级会话粘滞、真实流式透传和生产配置硬门槛；已补齐并纳入回归测试 | 2026-05-01 |
| HI-828 | UX | Frist-API 用户端信息密度过高、左侧导航/分组冗余、首屏存在演示数据闪现；已移除侧栏和 sticky，注册登录收进右上角，首屏只保留余额、模型消耗、连通性和导入入口，游客页不再显示演示消耗 | 2026-05-02 |
| HI-829 | SECURITY | Frist-API 公开管理页不应暴露给普通用户，注册登录需要基础防刷；已加入隐藏管理入口码、验证码挑战、认证限流和公网冒烟检查 | 2026-05-02 |
| HI-830 | UX | Frist-API 用户端缺少模型测试广场、数据看板、模型定价目录和配置教程；已补齐广场对话/生图、模型消耗分布、服务可用性、模型广场和 Codex/Claude/OpenClaw 一键配置教程 | 2026-05-02 |
| HI-831 | SECURITY | Frist-API 管理员升级不应依赖用户把账号密码交给开发者；已改为登录后输入一次性管理员身份码，成功后当前账号升级且身份码作废 | 2026-05-02 |
| HI-832 | UX | Frist-API 用户端注册登录、页面返回、广场消息管理、API Key 改名/删除、CC Switch 全模型导出、官方 Pro 模型优先级和 OpenCode/Hermes/Harmes 教程完整度不足；已补齐用户侧闭环并纳入回归测试 | 2026-05-02 |
| HI-833 | UX | Frist-API Codex/OpenCode 导出后用户无法在页面确认完整模型清单，外部 GUI 若只读单一字段可能只显示默认模型；已在 CC Switch 页可见化默认模型/全模型列表，并补齐多套模型列表兼容字段 | 2026-05-02 |
| HI-834 | INFRA | Frist-API 裸 IP 测试入口拒绝连接；根因是容器仅本地绑定且 Nginx 未监听测试端口，同时服务器代码落后于本地 open4；已同步代码、更新 Nginx 监听并通过公网冒烟 | 2026-05-02 |
| HI-835 | UX | Frist-API 首屏主卡过大、品牌标识弱化、快捷入口过于等分；已恢复黑白红品牌标识，并改为主控台、右侧说明、核心指标和不对称任务轨道 | 2026-05-02 |
| HI-836 | UX/ARCH_LIMIT | CC Switch 跨模型家族导入存在断点：ChatGPT 模型不能直接导入 Claude Code，Claude 模型导入 Codex 缺少 Responses 降级链路；已补齐 Claude Code Anthropic Messages 配置、Codex Responses fallback、开发者模式引导和支付最后一公里手册 | 2026-05-02 |
| HI-837 | UX | CC Switch 跨模型导入教程仍偏文字化，用户不知道 Claude 左上角菜单、第三方推理输入框和 Codex 配置字段在哪里；已补两张仿真实操流程图、编号步骤、字段对照和上下文切换验收提示 | 2026-05-02 |
| HI-838 | UX/BUG | Frist-API 登录、创建 Key、连通性刷新、模型命名、mock 数据和价格管理存在实测断点；已补明确反馈、刷新留在当前页、渠道聚合状态、官方模型名清洗、真实数据空态、后台价格 JSON 管理和 60 刀测试额度入账 | 2026-05-02 |
| HI-839 | UX/BUG | Frist-API 外网实测发现 CC Switch 一键导入入口藏在长教程后、广场 `gpt-5.5` Chat Completions 返回上游 `Route /openai/chat/completions not found`、OpenCode 前缀路由未接住、OpenCode 导入模型清单缺 `gpt-5.4` / `gpt-5.3-codex`，桌面端实际导入后 `config.models` 仍只写默认模型；已前置一键导入主操作、补 OpenCode `/openai/*` 兼容路由、Chat Completions 缺失时降级 Responses，并按 OpenCode/CC Switch 真实配置格式补完整模型映射 | 2026-05-02 |
| HI-840 | TECH_DEBT | 主项目文档、历史截图、旧审计报告、本地构建缓存和服务器临时产物过多；已压缩 docs 到 19 个 Markdown，本地仓库体积从约 2.4GB 降到约 196MB，并分层清理服务器日志、缓存、临时文件和 Docker 非运行对象 | 2026-05-03 |
| HI-841 | UX/BUG | Frist-API 广场和补号对 `5.5`、`image2` 这类商业别名不够稳，图片库存严格探测可能误走聊天接口；已补别名清洗、图片模型 `/images/generations` 探测、广场一键实测状态和回归测试 | 2026-05-03 |
| HI-842 | SECURITY/ARCH_LIMIT | Frist-API 需要把 CPA JSON 和 chong 作为备用渠道人工管理，但不能默认进入生产路由；已增加渠道类型、风险状态、人工确认和隔离态路由过滤 | 2026-05-03 |
| HI-843 | BUG | 腾讯云公网实测发现上游返回 `API key is disabled` 时，网关 503 路径会回滚库存状态，导致广场继续展示失效模型；已改为保留失败状态并让模型清单自动下线 | 2026-05-03 |
| HI-844 | BUG/UX | 授权余额站上游根地址会返回网站 HTML 壳，旧补号探测可能把 2xx HTML 当成健康或额度错误；已改为根地址失败后自动尝试 `/v1`、校验 OpenAI 兼容 JSON，并把首页改为控制台工作台布局 | 2026-05-03 |
| HI-845 | UX/AI_POOL | 新余额站 `gpt-image-2` 真请求耗时 40-110 秒，广场默认图片参数过重容易放大公网等待；已改为轻量 PNG 请求并完成裸 IP 公网图片真测 | 2026-05-03 |
| HI-858 | UX | Frist-API Workbench 壳不足：侧栏品牌与顶部 Logo 重复、仪表盘指标/图表/日志不足、API 管理缺搜索和端点展示、缺使用记录/订阅/兑换/邀请/资料页面、CC Switch 需覆盖 Gemini/OpenCode/OpenClaw/Hermes/Harmes 和 Codex DeepSeek；已完成 UI 外壳、美元展示和回归测试 | 2026-05-03 |
| HI-859 | ARCH_LIMIT | Frist-API 已接入服务端 New-API 业务桥接层和每日 GitHub Actions 同步 PR；New-API 可接管看板、Token、日志、兑换、订阅、充值配置、邀请返利和可选网关代理。仍保留 Frist-API 自研 UI、CC Switch/Codex/DeepSeek 配置、补号助手、余额预警和 JSON 兜底；完整切换还需要历史用户/余额/Key/订单迁移和生产 New-API 初始化 | 2026-05-03 |
| HI-848 | UX | Frist-API 用户无法按自己的心理安全线设置余额提醒；已新增账单页自定义阈值、收件邮箱、测试邮件和扣费跨阈值一次性提醒 | 2026-05-03 |
| HI-849 | INFRA | 本机到 Gmail SMTP 异常；腾讯云实测 IPv6 SMTP TLS 与真实发信可用，IPv4 465 超时；已补 Node SMTP DNS 地址轮询和 `FRIST_API_SMTP_FAMILY` 配置 | 2026-05-03 |
| HI-855 | SECURITY/UX | Frist-API 验证码原为简单算术题且登录也强制填写；已改为仅注册需要多题型挑战、单题错误次数限制，登录保留频率限制但不再要求验证码 | 2026-05-03 |
| HI-851 | SECURITY | Frist-API 密码哈希使用 SHA-256（GPU 友好）；已改为 PBKDF2-SHA256 新格式，旧 SHA-256 用户登录成功后自动升级 | 2026-05-04 |
| HI-852 | SECURITY | Frist-API Session Cookie 缺少 `Secure` 标记；已在 HTTPS 公网网关或 `x-forwarded-proto=https` 下自动加 `Secure` | 2026-05-04 |
| HI-860 | SECURITY | Frist-API 用户端和管理端部分动态 `innerHTML` 字段未统一转义；已补齐 API Key 属性、充值/导入按钮、管理端摘要/审计日志等转义并加回归 | 2026-05-04 |
| HI-861 | AI_POOL/UX | Frist-API Codex DeepSeek 导入仍默认旧 `deepseek-chat`，与 DeepSeek 官方当前 v4 模型文档不一致；已将新导入默认模型改为 `deepseek-v4-flash`，补 `deepseek-v4-pro` 并保留旧模型兼容 | 2026-05-04 |
| HI-862 | UX | Frist-API 后端不可用时用户只看到顶部错误提示，不知道如何恢复；已在工作台增加离线恢复条和一键重新连接入口 | 2026-05-04 |
| HI-850 | SECURITY | Frist-API runtime.json 明文存储用户 fk-live Key 和上游 rawKey；已新增 AES-256-GCM 字段加密，兼容旧明文读取并在保存时迁移 | 2026-05-04 |
| HI-853 | UX | Frist-API 无"忘记密码"功能，用户丢失密码后无法自助恢复；已新增 SMTP 重置验证码和确认改密接口 | 2026-05-04 |
| HI-854 | UX | Frist-API 前端服务不可用时静默降级无重试入口，用户看不到明确恢复指引 | 2026-05-03 |
| HI-856 | ARCH_LIMIT | Frist-API 当时抽取 shared/catalog/newApiBridge/email/auth/payments/store 等职责，并把 SMTP DNS 轮询、注册/重置/余额预警邮件模板和邮箱归一化迁入 `server/email.js`，阶段回归为 `161/161`。2026-08-04 复核发现旧 `store.js` 未被使用且会丢运行字段，现已删除；当前权威存储安全超集仍保留在 `server.js`，完整拆分继续按独立批次推进。 | 2026-05-03 |
| HI-857 | ARCH_LIMIT | 当前 Frist-API 单实例部署下，轻量 captcha/rateLimit 内存态可接受；生产水平扩展或多进程部署前必须迁移到 Redis/SQLite。已在运维文档写明判断依据和触发条件。 | 2026-05-03 |
| HI-863 | INFRA | Frist-API 长期入口已复用 VPS-Config 既有域名和 Cloudflare 资产闭环：`jiyu.245334.xyz` 当前通过 Cloudflare proxied A 指向 Oracle ARM `150.136.73.15`，旧 `frist-api.245334.xyz` 跳转到 CC中转主站，旧 `frist-api.101-43-41-96.nip.io` 只保留冷回滚排障语境，不再作为生产兜底入口 | 2026-05-04 |
| HI-864 | UX/COMMERCE | Frist-API 个人阶段不再推进个人收款码自动识别；已改为管理端批量生成一次性兑换码、用户端专属兑换页核销自动到账，并预留闲鱼商品链接位置 | 2026-05-04 |
| HI-865 | AI_POOL/UX | Frist-API 需要管理自用 ChatGPT Plus 账号资产但不能把 Plus 账号变成可售 API 路由库存；已新增管理端 Plus 台账、到期摘要、敏感备注加密和用户路由隔离回归 | 2026-05-04 |
| HI-866 | AI_POOL/UX | Frist-API 需要参考 New-API Codex OAuth 和 Grok RT JSON 格式支持 Refresh Token 批量管理，同时不能减少原 New-API 管理侧能力；已新增管理端 RT JSON/TXT 导入、脱敏台账、加密落盘和路由隔离回归 | 2026-05-04 |
| HI-867 | UX/PERF | Frist-API 用户端和管理端解释性文案偏多、深色 Hyperstudio 壳与 Apple 简洁方向不一致，搜索和测试台存在不必要局部重绘；已切换 Refero Apple 浅色控制台、压缩首屏指标和导航文案、保留管理侧原功能并补局部渲染优化 | 2026-05-05 |
| HI-868 | UX/PERF | Frist-API 参考 Tabcode 控制台克隆吸收优秀设计：替换旧视觉皮肤为 `tabcode-console`，后续按用户反馈收敛为深色顶栏、深色工作区、160px 侧栏、14px 卡片和短动效反馈，管理端原有 New-API/价格/入账/卡密/Plus/RT/接入/订单/库存/审计能力不减少 | 2026-05-05 |
| HI-869 | BUG | Frist-API Plus 台账金额字段审计发现异常数字输入可能把 `NaN` 带入运行数据；已改为有限数字归一化并补回归，异常 TRY 余额/月费统一落为 0 | 2026-05-05 |
| HI-870 | UX/SECURITY/ARCH_LIMIT | Frist-API CC Switch 导出曾按本机 Tabcode Claude/Codex 真实导入结构补齐大块 `settings_config`；后续 HI-877 已按 CC Switch 当前官方 parser 收敛为短 deep link，页面仍展示完整模型清单，协议无响应时自动复制降级；管理认证失败脱敏审计、runtime 写入失败 warning 和 SIGTERM/SIGINT 优雅关闭已保留 | 2026-05-05 |
| HI-871 | UX | Frist-API Tabcode 浅色皮肤存在旧深色规则残留，黑底按钮/代码栏复制按钮/返回按钮出现灰字低对比；已更新资源版本并增加对比度护栏，用户端 6 个主路由和管理端可见交互元素扫描低对比为 0 | 2026-05-05 |
| HI-874 | AI_POOL/INFRA | 用户提供的 `https://www.inroi.shop/v1` 是授权上游请求地址，后续字符串是上游 Key，不是 Frist-API 对外入口；已按 `x-admin-token` 复查远端管理号池，同 Key 旧根地址记录为 `exhausted/enabled=false` 不可路由，正确 `/v1` 记录为 `healthy/enabled=true` 且模型 21 个，runtime 中 rawKey 为 AES-GCM 加密字段 | 2026-05-05 |
| HI-875 | UX/AI_POOL | Frist-API 用户端日志过长、测试页文字爆炸、深色对比不足、模型价格说明不完整、记录页缺客户端/费用/延迟、API Key 前缀像 fake；已改为 5 条精简日志、短动效反馈、深色控制台逐页审计、官方输入/缓存/输出价、3 分钟自动检测、消费后余额刷新、邮箱遮罩、兑换码前置、消费返利 5% 上限和资料可编辑；2026-07-04 当前生产入口已迁到 Oracle `https://jiyu.245334.xyz`，旧 Frist 域名跳转，历史腾讯入口仅冷回滚；2026-05-06 上线前安全复审已将新 Key 前缀恢复为 `fk-live-*` | 2026-05-05 |
| HI-876 | SECURITY | Frist-API 上线前安全闭环复审发现 CSRF、SSRF、支付少付入账、runtime 写入原子性、用户 Key 明文回显、共享脱敏前缀和生产模板开关存在上线风险；已补 CSRF Token、补号 URL 私网阻断、支付金额校验、临时文件 fsync+rename、Dashboard 不再持久回显明文 Key、`fk-live-*` 脱敏一致性和生产 `FRIST_API_REQUIRE_CSRF`/`FRIST_API_ALLOW_PRIVATE_UPSTREAM_URLS` 登记 | 2026-05-06 |
| HI-877 | UX/BACKEND | CC Switch 用量查询曾只能靠用户按教程手填 Key 和 API 地址，且 DeepSeek 官方端点导入时用量脚本可能误用上游域名；已核对 CC Switch 3.14.1 官方 deep link 支持 `usageScript` 等字段，导入链接自动带 Base64URL 用量脚本并移除旧 `config` / `availableModels` 大块参数，新增 `/api/frist/key-usage` 只读脱敏接口，修复 New-API 用量接口 500 回归，并将模型请求地址与 Frist 用量查询地址解耦；2026-05-06 实机验证中 CC Switch 日志确认解析 `resource=provider/app=claude/name=Frist-API`，临时等价导入后 Claude CLI 返回 `Frist API CLI OK`，测试后已恢复用户原配置 | 2026-05-06 |
| HI-878 | UX/BACKEND | Frist-API 渠道状态监视器此前只有 healthy/total 简表，用户无法判断降级、慢线、最近状态和刷新口径；已参考 86GameStore `/monitor` 补齐当前库存快照、可用率、最低/平均延迟、慢线/失败状态条和 60 秒刷新展示，响应继续脱敏；2026-05-07 已通过 HI-882 补齐持久化探测事件和 7/15/30 天 SLA 摘要 | 2026-05-06 |
| HI-879 | BUG/AI_POOL | Frist-API “Claude 兼容入口 · 查询失败”根因是 CC Switch 用量脚本返回对象型 `extra`，同时 Claude 原生 Messages 上游未优先直连；已将 `extra` 改为字符串、补 Claude `/v1/messages` 原生路由/严格探测、同 Key 多模型组隔离和导出按模型组选 Key。86GameStore Claude/OpenAI 号源已加密写入 ignored runtime，用户流程、Claude CLI、Codex CLI 和浏览器刷新均已实测闭环 | 2026-05-06 |
| HI-880 | UX/BUG | CC Switch 小白导入 Workflow 存在边界不清：供应商 deep link 和 MCP deep link 是两个 resource，页面曾把 MCP 偏向 Codex 且用户显式选择模型时服务端返回默认模型、深链模型和 TOML 默认模型可能不一致；已按 CC Switch `origin/main` 源码收敛为两步 Workflow，MCP 增强包覆盖 `claude,codex,gemini,opencode,hermes`，明确 OpenClaw MCP 会被当前 CC Switch 忽略，并补齐用户选择模型一致性回归 | 2026-05-06 |
| HI-881 | UX/BACKEND | Frist-API 用户侧缺少导入后的闭环检测和异常消费提醒，管理侧号池对小白管理员仍难以判断哪个端点/渠道断了；已将 OpenAI 命名收敛、补导入后检测闭环、`gpt-image-2` 流程图验证入口、轻量异常消费检测、管理端号池首次使用流程和渠道诊断。受控实机验证中，文本 `pong`、图片返回、用量脚本、记录页消费、异常提醒和 `gpt-image-2` 降级 `1/2 可用` 均闭环 | 2026-05-07 |
| HI-882 | SECURITY/ARCH_LIMIT | Frist-API New-API 剩余生产边界缺少统一硬门槛；已新增生产强制开关、固定品牌域名检查、New-API 数据库必备开关、管理员 TOTP 2FA、真实支付商户状态、备份/恢复登记和 7/15/30 天渠道 SLA 事件摘要。外部仍需购买/绑定真实品牌域名、在商户平台开户、部署备份任务并完成历史 JSON 到 New-API 数据迁移 | 2026-05-07 |
| HI-883 | UX/BUG | Frist-API 用户端浏览器批注发现状态灯、导航间距、趋势图、CC Switch 教程、重复 Harmes、复制按钮、模型展示名、资料页、登录弹窗和游客库存展示存在视觉 QA 问题；已按批注修复，未登录 Dashboard 不再展示 `channelChecks`，真实内部模型 ID 继续保留以免影响路由 | 2026-05-08 |
| HI-884 | BUG/SECURITY | Frist-API 登录失败曾把真实 401 账号错误统一显示为“后端暂不可用”，且公网容器仍使用默认管理令牌，SMTP 未配置时用户无法自助恢复密码；已补真实错误反馈、管理员账号恢复接口、独立密码哈希密钥、默认管理令牌替换和 CSRF。历史 runtime 已有 `enc:v1` 字段但缺原始数据加密密钥，公网暂保留兼容模式，后续需一次性迁移后再启用公开模式数据加密 | 2026-05-08 |

---

## 技术债

| ID | 分类 | 描述 | 优先级 |
|----|------|------|--------|
| TD-001 | TECH_DEBT | CookieCloud 127.0.0.1:8088 仅剩可选增强路径；未配置时系统不阻塞，本机 ignored `.env` 中死配置已清理，注册表不再把它当必需依赖 | ✅ 已处理 |
| TD-002 | ARCH_LIMIT | 微信编号命令已逐条收口：可接内部只读 API 的全部映射到真实 GET 路由；交易/发文/发货/导出等高风险或无安全回传能力的入口改为明确说明原因并转人工确认 | ✅ 已处理 |
| TD-003 | TECH_DEBT | `/cli` 已正式注册到 `CLICommandsMixin` 和 `MultiBot`，并补启动注册回归；不再是预备死代码 | ✅ 已处理 |
| TD-004 | TECH_DEBT | 历史 `pass` 已从 63 降到 49；剩余均为可选依赖降级、任务取消、幂等辅助或异常兜底路径，并补中文注释说明保留原因，不再静默误导主流程 | ✅ 已处理 |
| TD-005 | TECH_DEBT | 历史 lint 问题已机械清理到 `make lint` 可通过；2026-07-02 fresh `make lint` 输出 `All checks passed!` | ✅ 已处理 |
| TD-006 | ARCH_LIMIT | Frist-API JSON runtime → New-API 生产迁移已按授权执行：用户 19、token 1、充值/订单 4、兑换码 2、日志 162 已迁入，New-API adapter 已启用，回滚目录为 `/opt/frist-api/backups/newapi-migration-20260703T005433Z`；16 个历史 `enc:v1:` 用户 Key 因旧加密密钥缺失未迁移，需重新生成/补录 | ✅ 代码/迁移已处理，旧 Key 为人工补录 |
| TD-007 | INFRA | 域名/Cloudflare/R2 不新购，已复用 `/Users/blackdj/Documents/VPS-Config` 既有资产并完成 Oracle 切流：`jiyu.245334.xyz` 为 Cloudflare proxied A → Oracle ARM `150.136.73.15` → Apache/Origin CA → New-API `127.0.0.1:13000`，旧 `frist-api.245334.xyz` 301 到 CC中转；Frist-API `127.0.0.1:3180` 仅保留内部兼容；R2 备份 timer 在 Oracle enabled/active，腾讯旧 timer disabled/inactive。SMTP 密码已通过隐藏输入方式写入 Oracle `/etc/frist-api/frist-api.env` 和兼容 `.env`，生产测试邮件返回 `smtp_test=sent`；密码未写入命令历史/Git/文档正文 | ✅ 域名/R2/Oracle/SMTP 已处理，旧 Key 为人工补录 |
| TD-008 | ARCH_LIMIT | 客户可见模型目录已改为健康上游 `/v1/models` / 真实探测优先；硬编码模型目录只用于后台审计排序，不再兜底展示不存在模型 | ✅ 已处理 |
| TD-009 | TECH_DEBT | Frist-API `ccswitch://` 导入链接依赖用户已安装 CC Switch，浏览器无协议处理器时降级体验为空；已改为点击导入自动复制链接并显示短降级反馈 | ✅ 已处理 |
| TD-010 | SECURITY | Frist-API 管理 API 失败认证不生成审计事件，暴力破解无法检测；已补脱敏审计事件且不记录提交的 token | ✅ 已处理 |
| TD-011 | ARCH_LIMIT | Frist-API 无优雅关闭（SIGTERM/SIGINT），连接直接断开对网关流式请求不友好；CLI 启动已补优雅关闭和超时兜底 | ✅ 已处理 |
| TD-012 | ARCH_LIMIT | Frist-API 文件写入失败被 `catch(() => {})` 静默吞掉，store 破损后无告警；已改为 `FRIST_API_RUNTIME_WRITE_FAILED` warning | ✅ 已处理 |
| TD-013 | ARCH_LIMIT | Frist-API 已将网关成功、慢线、失败和额度耗尽写入 `channelProbeEvents` 并返回 7/15/30 天 SLA 摘要；2026-05-09 已补独立 60 秒后台探测队列覆盖无人调用时段，并支持 Key 异常一次性补号提醒 | ✅ 已处理 |
| TD-014 | TECH_DEBT | requests/urllib3/aiohttp/FastAPI/Starlette/LiteLLM 等依赖安全下限已升级；高风险可选依赖默认移出并保留 graceful degradation；第三方 `js2py` / `Starlette TestClient` Python 3.12 兼容提示已通过 pytest 过滤隔离；2026-07-02 `pip check` 无破损依赖、`pip-audit` 无已知漏洞 | ✅ 已处理 |
| TD-015 | INFRA | 已查询上游并升级到 `actions/cache@v6`、`actions/setup-python@v6`、`astral-sh/setup-uv@v8.2.0`，CI 增加 secret/audit 门禁，Node 20 action 预警代码侧已收口 | ✅ 已处理 |
| TD-016 | ARCH_LIMIT | 社媒自动化只做工程质量收口，继续保持“待审草稿/只读采集/人工最终确认”边界；本轮没有恢复自动发布、评论、关注、私信、点赞或推广 | ✅ 工程侧已收口，外发仍人工 |
| TD-017 | TECH_DEBT | 内容蒸馏/多平台素材继续作为低优先级补位，只整理文档和安全边界；未擅自接入自动搬运或自动外发能力 | ✅ 工程侧已收口，深度蒸馏待业务确认 |

---


### Intel Brief Phase 0/基础切片 — 部分可用，仍有人工阻塞

2026-07-06 已按补充决策完成非部署基础切片：开放姓名追踪 schema/helper、`tracking_audit_log`、内容过滤基础模块和 Senate raw GitHub fallback。Oracle 真实验证显示 `house-stock-watcher-data` S3 裸文件仍 HTTP 403 `AccessDenied`，但 `timothycarambat/senate-stock-watcher-data/master/aggregate/all_transactions.json` 通过 raw GitHub HTTP 200 可用，MVP 可先用 Senate 数据。当前仍未确认 `oracle-arm1` 是否作为 Intel Brief 常驻运行环境，也未确认长期专用 venv、MediaCrawler 登录态、X/Reddit、Telegram 第 8 Bot Token、定价与套餐，因此不得宣称 Phase 1-4 完成。


### Intel Brief 多服务器与社媒登录策略 — 已有本地策略，生产仍需凭证/环境

2026-07-06 用户已允许按多服务器架构设计：纯国内源可放国内服务器（如炎火云），海外流量源走海外服务器。代码侧已新增 `src/intel/runtime_policy.py`，本地测试覆盖国内源、海外源、未知源 controller 兜底，以及微博/小红书 `cdp_cookie` / `cookie` 优先、二维码 fallback-only 策略。生产风险仍在：国内服务器尚未实际创建/连通，MediaCrawler 账号 Cookie/CDP 登录态尚未提供，平台风控仍可能要求扫码或手机号二次验证，因此不得宣称微博/小红书已实现 100% 无人值守。


### Intel Brief 规划基线 — 已冻结先规划后生产变更

2026-07-06 用户明确要求先完成整体方案、开源社区高星轮子调研和搬运规划，再推进生产变更。已新增 `docs/052-intel-brief-master-plan.md`，并在独立 VPS-Config 仓库写入 `/Users/blackdj/Documents/VPS-Config/docs/indexes/intel-brief-runtime-placement.public.md`。当前基线：国内源优先炎火云 worker，海外源优先低负载 Oracle 新加坡西 worker，OpenEverything 保持 controller。后续若直接改生产、部署 worker、写 Cookie/Token 或跳过目标节点真实验证，均视为偏离基线。


### Intel Brief Phase B 目标节点验证 — 已起步，SGW 管理路径阻塞

2026-07-06 Phase B 已开始。炎火云可 SSH，已从目标国内节点真实验证微博公开页、小红书公开页、东方财富 API 与 AKShare 龙虎榜接口；AKShare 使用 `/tmp` 临时 venv 和国内镜像安装，没有写入生产依赖。Oracle SGW 作为海外首选节点从当前 Mac 直连 SSH 在 banner 阶段超时，因此不能声称 SGW 数据源验证完成；已通过 Beszel 只读证明 SGW 系统可见/up。海外数据源暂用 `oracle-arm1` 标记为 `overseas-fallback` 验证通过 SEC 13F、OpenAI RSS、Anthropic News、Senate raw GitHub 和 GitHub API。后续生产闭环必须优先恢复/确认 SGW 管理路径，再把 fallback 验证迁移到 SGW。

## 二、自学习经验库


记录系统运行中积累的经验、最佳实践和优化心得。

## 格式

```
## [YYYY-MM-DD] 主题

**背景**: 场景描述
**发现**: 关键洞察
**应用**: 如何应用到实际工作中
```

---

## [2026-03-18] 系统全面优化完成

**背景**: 对 OpenClaw Bot 进行全面功能完善

**完成项目**:
1. 集成优化报告到 multi_main.py（Prometheus 指标、分层上下文、策略引擎、告警系统）
2. 交易记忆自动写入机制（TradingMemoryBridge 挂载到 journal）
3. 修复类型标注问题（execution_hub 4个bug、broker_bridge TYPE_CHECKING）
4. 社交媒体浏览器发布适配器（Playwright 自动发布 X/小红书）
5. 任务可观测性增强（TaskObserver 跟踪质量/成本/检索命中率）
6. 自学习系统启用（.learnings 文件初始化）

**关键洞察**:
- 交易系统虽然在跑，但记忆为空导致"失忆"决策 → 自动桥接解决
- 社交发布链条在最后一步断了 → Playwright 补上自动化
- 可观测性不足 → TaskObserver 按任务类型跟踪成本和质量
- 类型错误大多是 decompiled 文件的副作用，修复实际 bug 即可

**应用**:
- 所有关键业务流程都应有记忆沉淀机制
- 自动化链条要端到端完整，不能在最后一步依赖人工
- 可观测性要细化到任务级别，才能优化成本和质量

---

## 三、功能需求跟踪


记录用户提出的功能需求、改进建议和待实现特性。

## 格式

```
## [YYYY-MM-DD] 功能名称

**需求**: 用户需求描述
**优先级**: High/Medium/Low
**实现思路**: 技术方案概要
**状态**: Pending/In Progress/Done
```

---

## [2026-03-18] 初始化

功能需求跟踪已启用。后续需求将记录到此文件。

### Intel Brief Phase C/D 生产闭环支架 — 本地可验证，仍未生产执行

2026-07-06 用户确认 Phase B 不能作为终点，需要持续推进到生产闭环。本轮已在不部署、不重启、不写入凭证的前提下补齐两层支架：`src/intel/sources/base.py` 统一 Source Adapter 返回契约，`src/execution/intel_brief.py` 生成 plan-only 多服务器派发计划。验证结果：Intel Brief 相关测试 `20 passed`。证据文件：`packages/clawbot/data/intel_evidence/phasec/20260706T230209Z-controller-source-adapter-plan.json`、`packages/clawbot/data/intel_evidence/phased/20260706T230209Z-controller-dispatch-plan.json`。生产边界仍明确：当前没有远程执行、没有 scheduler 注册、没有 Telegram 推送，SGW 管理路径和 MediaCrawler 登录态仍是进入真实生产闭环前的硬门槛。

### Intel Brief Worker Contract / Source Health — 生产前支架已补，SGW 仍未闭合

2026-07-06 追加完成 controller↔worker JSON-safe 契约与 `source_health` helper。`dispatch_source_job` 现在仍是 `plan_only`，但会生成可审计的 `worker_request`；该 JSON 不包含 token/cookie/password/private key 等密钥材料。`record_source_health` 已能在临时 SQLite DB 中记录失败、连续失败计数和恢复清零。证据：`packages/clawbot/data/intel_evidence/phased/20260706T230933Z-controller-worker-contract-plan.json`、`packages/clawbot/data/intel_evidence/phasee/20260706T230933Z-source-health-seed.json`。只读 SGW 排查显示 VPS-Config 已有 SOP 把 Mac 直连 banner timeout 归为 management-path mismatch，当前不得把 SGW 视为已验证可执行生产 worker。

### Intel Brief 本轮验证基线 — 2026-07-06T23:11Z

本轮 worker contract 与 source_health 支架验证完成：`ruff` 输出 `All checks passed!`，Intel Brief 相关 pytest 输出 `26 passed`，OpenEverything 与 VPS-Config 的 `git diff --check` 均通过。证据路径：`packages/clawbot/data/intel_evidence/phasee/20260706T231131Z-worker-contract-source-health-verification.json`。该基线仍为本地 controller/DB helper 级别，不能替代 SGW/炎火云目标节点生产验证。

### Intel Brief Worker Runner / SGW Read-only Preflight — 2026-07-06T23:21Z

Worker 侧本地执行器已补齐：`execute_worker_request_json` 可把 controller 生成的 JSON-safe request 转为 adapter 调用，并返回 JSON-safe response，同时可写 source_health。默认 adapter registry 当前只开放 `senate_trading`，避免未验证数据源被误入生产。SGW 只读 preflight 已运行，报告状态 `blocked-launch-prerequisites` / `completed-with-launch-blockers` / `PRODUCTION_ACTION none`；这证明 OCI 只读配置可用，但 SGW SSH 管理路径仍未闭合，不能作为生产 worker 已可执行的证据。

### Intel Brief 本轮验证基线 — 2026-07-06T23:30Z

Worker runner、adapter registry、worker contract、source_health helper 与 SGW read-only preflight 证据已汇总。验证结果：`ruff` 为 `All checks passed!`，Intel Brief 相关 pytest 为 `31 passed`，OpenEverything/VPS-Config diff check 均通过。证据路径：`packages/clawbot/data/intel_evidence/phasee/20260706T233012Z-worker-runner-sgw-preflight-verification.json`。SGW preflight 结果仍是 `blocked-launch-prerequisites`，不能替代 SGW SSH/worker 执行验证。

### Intel Brief Worker CLI 基线 — 2026-07-06T23:35Z

Worker CLI 已新增并完成本地验证：stdin/file 输入、可选 DB、未知 source 返回 2、坏 JSON 返回 1。CLI 本地真实调用 `senate_trading` 成功返回 BYND / Ron L Wyden 样本，并写入临时 source_health；证据路径：`packages/clawbot/data/intel_evidence/phasee/20260706T233517Z-worker-cli-local-execution.json`。`oracle-arm1` 只读 readiness 检查显示 SSH/Python 可用但常见路径无 OpenEverything 项目；证据路径：`packages/clawbot/data/intel_evidence/phasee/20260706T233541Z-oracle-arm1-worker-cli-readiness-readonly.json`。目标 worker 执行仍未完成。

### Intel Brief 本轮验证基线 — 2026-07-06T23:37Z

Worker CLI 入口验证完成：`ruff` 输出 `All checks passed!`，Intel Brief 相关 pytest 输出 `35 passed`，OpenEverything/VPS-Config diff check 均通过。证据路径：`packages/clawbot/data/intel_evidence/phasee/20260706T233730Z-worker-cli-verification.json`。该基线证明 CLI 可作为目标 worker 执行入口，但尚未在 SGW/炎火云/Oracle Ashburn 上远程运行。

### Intel Brief oracle-arm1 fallback 远程执行证据 — 2026-07-06T23:43Z

Intel worker bundle 已在 Oracle Ashburn fallback `oracle-arm1` 以临时 `/tmp` staging 方式真实执行：`senate_trading` 返回 BYND / Ron L Wyden 样本，remote source_health `failure_count=0`，随后执行 cleanup 并二次验证 `remote_stage_absent`。证据路径：`packages/clawbot/data/intel_evidence/phasee/20260706T234325Z-oracle-arm1-worker-cli-remote-execution.json`。该证据只证明 Ashburn fallback 可跑 worker CLI，不代表 SGW preferred worker 已闭合，也未创建 systemd/cron/生产配置/密钥。

### Intel Brief 本轮验证基线 — 2026-07-06T23:45Z

Worker bundle 与 oracle-arm1 fallback 真实远程执行验证完成：`ruff` 输出 `All checks passed!`，Intel Brief 相关 pytest 输出 `37 passed`，oracle-arm1 临时 `/tmp` staging 执行 `senate_trading` 成功并已清理，OpenEverything/VPS-Config diff check 均通过。证据路径：`packages/clawbot/data/intel_evidence/phasee/20260706T234653Z-worker-bundle-remote-verification.json`。该基线证明 Ashburn fallback 可跑最小 worker CLI，但 SGW preferred worker 仍未验证。

### Intel Brief 炎火云 AKShare worker CLI 证据 — 2026-07-06/UTC 2026-07-07

炎火云 domestic worker 已完成临时 worker CLI 真实执行：`akshare` adapter 调用 `stock_lhb_detail_em()` 成功，返回 `000021` / `深科技`，source_health `failure_count=0`，stdout 已验证为单个 JSON response，远程 staging `/tmp/openclaw-intel-worker-20260707T000126Z` 已清理并验证 `remote_stage_absent`。证据路径：`packages/clawbot/data/intel_evidence/phasee/20260707T000126Z-yanhuoyun-akshare-worker-cli-clean-stdout.json`。过程中发现并修复 Python 3.10 `datetime.UTC` 兼容问题；失败证据保留在 `20260706T235130Z-yanhuoyun-akshare-worker-cli-remote-execution.json`。

### Intel Brief 本轮验证基线 — 2026-07-07T00:06Z

Yanhuoyun domestic AKShare worker CLI 验证完成：`ruff` 为 `All checks passed!`，Intel Brief 相关 pytest 为 `43 passed`，远程临时 CLI 返回 `000021` / `深科技`，stdout 为纯 JSON，source_health `failure_count=0`，staging 清理并验证 absent。证据路径：`packages/clawbot/data/intel_evidence/phasee/20260707T000629Z-yanhuoyun-akshare-domestic-verification.json`。该基线只覆盖 AKShare 非登录源，不覆盖社媒登录态或常驻服务。

### Intel Brief Remote Runner 双 worker 复核 — 2026-07-07T00:14Z

`intel_worker_remote_run.py` 已把临时 SSH/tar/worker CLI 流程固化为可重复的远程执行原语。复核结果：oracle-arm1 fallback 执行 `senate_trading` 成功，证据 `packages/clawbot/data/intel_evidence/phasee/20260707T001230Z-remote-runner-oracle-arm1-senate.json`；炎火云 domestic worker 执行 `akshare` 成功，证据 `packages/clawbot/data/intel_evidence/phasee/20260707T001324Z-remote-runner-yanhuoyun-akshare.json`。两者均 cleanup_ok 且 `remote_stage_absent`，未创建常驻服务/cron/systemd/生产配置/密钥。

### Intel Brief 本轮验证基线 — 2026-07-07T00:17Z

Remote runner 固化验证完成：`ruff` 为 `All checks passed!`，Intel Brief 相关 pytest 为 `46 passed`。同一脚本已成功复核 oracle-arm1 `senate_trading` 与炎火云 `akshare`，两者均 cleanup verified。证据路径：`packages/clawbot/data/intel_evidence/phasee/20260707T001745Z-remote-runner-verification.json`。该基线提供 scheduler 未来可调用的 one-shot remote execution 原语，但尚未启用生产调度。

### Intel Brief Collect-once 多源采集基线 — 2026-07-07T00:22Z

`intel_collect_once.py` 已完成真实多源远程采集：`senate_trading` 通过 oracle-arm1 fallback 成功，`akshare` 通过炎火云 domestic worker 成功，聚合报告 `packages/clawbot/data/intel_evidence/phasef/20260707T002040Z-collect-once-senate-akshare.json` 显示 `success=2 / failed=0`，child runs 均 cleanup_ok 且 `remote_stage_absent`。该基线是 scheduler 前的 one-shot controller 编排，不代表常驻调度或 Telegram 推送已启用。

### Intel Brief 本轮验证基线 — 2026-07-07T00:28Z

Collect-once 多源编排验证完成：`ruff` 为 `All checks passed!`，Intel Brief 相关 pytest 为 `49 passed`，真实 collect-once 聚合 `senate_trading` + `akshare` 成功，summary `success=2 / failed=0`，两个 child runs 均 cleanup verified。证据路径：`packages/clawbot/data/intel_evidence/phasef/20260707T002711Z-collect-once-verification.json`。该基线仍为 one-shot controller orchestration，不等于生产 scheduler/Telegram 闭环。

### Intel Brief Dry-run 简报草稿 — 已形成 one-shot 内容层闭环（未生产推送）

2026-07-07 追加完成 collect-once 之后的内容层 dry-run：`intel_brief_dry_run.py` 使用真实 `senate_trading + akshare` 聚合证据生成 Markdown/JSON 简报草稿，summary 为 `source_count=2 / rendered_count=2 / deduped_count=0 / moderated_count=0`。证据路径：`packages/clawbot/data/intel_evidence/phasef/20260707T003755Z-brief-dry-run.md` 与 `packages/clawbot/data/intel_evidence/phasef/20260707T003755Z-brief-dry-run.json`。

健康边界：该状态只证明“真实远程采集 → 聚合证据 → 规范化/去重/内容过滤 → Markdown 草稿”的 one-shot 内容层闭环。尚未证明 LLM 摘要、订阅者权限筛选、Telegram 推送、第8个 bot token、scheduler 注册、常驻 worker、自然日演练或 MediaCrawler 社媒登录态。

### Intel Brief LLM 摘要 dry-run — 本地 LLM routing 已闭合（未生产投递）

2026-07-07 追加完成 LLM 摘要层 dry-run。首次用 `gemma` 本地 8B 模型调用超时，并暴露现有 Router fallback 会继续尝试外部 provider 的噪音；该失败已保留为证据 `packages/clawbot/data/intel_evidence/phaseg/20260707T005033Z-llm-summary-dry-run.json`。随后新增 `intel_local` family 指向本地 Ollama `qwen2.5:1.5b` 且禁用 fallback，使用真实 Phase F dry-run evidence 成功完成 LLM routing 摘要，证据为 `packages/clawbot/data/intel_evidence/phaseg/20260707T005640Z-llm-summary-dry-run-intel-local.json`，token usage `prompt=353 / completion=159 / total=512`。

健康边界：该状态证明本地 dry-run 的 LLM routing 链路可跑通，不证明生产优先 provider 的质量/费用/额度稳定性；也不证明 Telegram 推送、第8个 bot token、scheduler、常驻 worker、自然日演练或社媒登录态已闭合。

### CC中转闲鱼自动发货真实内测单 — 仍阻断正式售卖

2026-07-07 最新状态：已修复闲鱼 WebSocket 明文付款系统卡片被跳过的问题，后续如果闲鱼推送“我已付款，等待你发货”这类系统卡片，会进入自动发货任务；普通聊天照抄付款文案不会触发。后端全量测试、Chrome 插件测试、CC中转主站测试均通过。当前真实测试单仍有 `pending_rescue=1`，状态为 `manual_delivery_ready`，说明卡密已分配但尚未实际发送到买家聊天；因此系统仍不能宣布“正式售卖闭环”。Chrome 当前没有打开对应卖家侧买家聊天页，且已安装插件仍未上报新版 `all_open_xianyu_tabs_watch/target_tab_preflight` 能力，需要手动刷新 Chrome 插件并打开一次弹窗。卖家订单列表 API 仍返回 `PERMISSION_EXCEPTION::无权限访问`，这一路不能作为主通道，只能继续走 WebSocket 系统卡片 + Chrome 聊天页兜底。

分类: `BUG`
严重度: 🟠 重要
下一步: 用户在卖家账号 Chrome 中刷新 `OpenEverything Social Pilot` 插件，打开对应买家聊天页；我再执行只读识别，发送前按浏览器安全规则向用户确认一次，确认后才让插件把已分配话术发出并标记 `message_sent`。随后必须完成买家注册/兑换/API Key/CC Switch/模型调用同单严格门。

### Intel Brief 投递沙盒 — fake Telegram 已闭合（未真实推送）

2026-07-07 追加完成订阅者与投递层沙盒：使用 Phase G LLM summary evidence 作为输入，创建 sandbox SQLite DB 和 1 个测试 Telegram subscriber，fake sender 写入 1 条 outbox，并在 `delivery_log` 记录成功投递。证据：`packages/clawbot/data/intel_evidence/phaseh/20260707T010624Z-delivery-sandbox.json`，结果 `eligible=1 / sent=1 / failed=0 / delivery_log_count=1 / network_calls=0`。

健康边界：这只证明订阅者筛选、投递消息渲染、delivery_log 和 fake outbox 路径可跑通；不证明真实第8个 Telegram bot token、真实 Bot API、真实 chat id、scheduler、常驻 worker 或自然日演练已闭合。

### Intel Brief Scheduled sandbox — 本地定时排练已闭合（未生产调度）

2026-07-07 追加完成 scheduled controller rehearsal。新增 `src/intel/scheduled_pipeline.py` 与 `packages/clawbot/scripts/intel_scheduled_sandbox.py`，在不注册 cron/systemd/ExecutionScheduler 生产任务的前提下，验证到点判断后可从既有 Phase F 真实 collect evidence 串联 brief dry-run、LLM fallback-only summary、delivery sandbox。证据：`packages/clawbot/data/intel_evidence/phasei/20260707T011556Z-scheduled-sandbox.json`，结果 schedule reason=`due`，brief rendered=2，LLM `llm_attempted=false`，delivery `eligible=1 / sent=1 / failed=0`，fake sender `network_calls=0`。

健康边界：这只证明本地 scheduled sandbox controller 链路可跑通；不证明真实 Telegram Bot API、第8个 bot token、生产 scheduler、常驻 worker、自然日演练、SGW preferred worker 或 MediaCrawler 社媒登录态已闭合。最终验证 evidence：`packages/clawbot/data/intel_evidence/phasei/20260707T011701Z-scheduled-sandbox-verification.json`。

### Intel Brief ExecutionScheduler 安全闸门 — 已接入但仍默认关闭

2026-07-07 追加完成 Intel Brief 调度安全闸门。`ExecutionScheduler._loop()` 已有 Intel Brief hook，但 `INTEL_BRIEF_ENABLED` 默认空/关闭；`INTEL_BRIEF_MODE=production` 会被 `build_intel_brief_scheduler_gate()` 阻断，除非 token/chat/worker placement/production ack 等门槛齐备，且当前仍显式包含 `production_runner_not_implemented` 防止误生产。生产阻断证据：`packages/clawbot/data/intel_evidence/phasej/20260707T012933Z-production-hard-gate-blocked.json`。

真实 scheduler sandbox invocation 已通过：`packages/clawbot/data/intel_evidence/phasej/20260707T013200Z-execution-scheduler-sandbox-invocation.json`，结果 brief rendered=2，LLM attempted=false，delivery eligible=1/sent=1/failed=0，network_calls=0。过程中发现 async scheduler context 不能直接调用含 `asyncio.run()` 的同步 pipeline，已用 `asyncio.to_thread()` 修复并补回归测试。

健康边界：这不是生产 scheduler 启用；没有 cron/systemd/常驻服务、真实 Telegram Bot API、生产 DB、远程新抓取或密钥写入。下一步要进入真实生产推送前，仍必须提供第8个 bot token/chat id、确认 worker placement，并移除/替换 `production_runner_not_implemented` 闸门。

### Intel Brief 本轮验证基线 — 2026-07-07T01:33Z

ExecutionScheduler 安全闸门验证完成。证据路径：`packages/clawbot/data/intel_evidence/phasej/20260707T013304Z-scheduler-gate-verification.json`。该验证覆盖 Phase J evidence JSON、`llm_routing.json`、ruff、Intel Brief/LLM routing/Execution facade 相关 pytest、fake secret 泄漏检查、OpenEverything/VPS-Config diff check。生产边界不变：未启用真实 scheduler/cron/systemd，未调用真实 Telegram Bot API，未创建常驻 worker，未写生产 DB。

### Intel Brief Telegram sender 合同层 — 已就绪但未真实发送

2026-07-07 追加完成 Telegram Bot API sender 合同层。证据 `packages/clawbot/data/intel_evidence/phasek/20260707T014112Z-telegram-sandbox-gate-blocked.json` 显示当前真实 token/chat/ack 缺失，gate blocked 且 `network_calls=0`；证据 `packages/clawbot/data/intel_evidence/phasek/20260707T014112Z-telegram-sandbox-contract-injected.json` 使用注入 transport 验证 sender 合同，`network=injected_transport`，没有真实 Telegram 网络调用。

健康边界：真实第8个 `intel_brief_bot` token 和 sandbox chat id 仍未提供；未调用 Telegram Bot API；未启用生产 scheduler；未创建常驻 worker。该层只降低后续真实沙盒发送时的代码风险。

### Intel Brief 本轮验证基线 — 2026-07-07T01:44Z

Telegram sender 合同层验证完成。证据路径：`packages/clawbot/data/intel_evidence/phasek/20260707T014408Z-telegram-contract-verification.json`。该验证覆盖 Phase K evidence JSON、Telegram 合同层 ruff、`.env.example` ack 变量、Phase K/Intel Brief/LLM routing 相关 pytest、token/chat/fake secret 泄漏检查、OpenEverything/VPS-Config diff check。生产边界不变：未调用真实 Telegram Bot API，未验证真实第8 bot token/chat id，未启用生产 scheduler/cron/systemd，未创建常驻 worker。

### Intel Brief Telegram summary delivery 预演 — 摘要内容已进入 sender 合同层

2026-07-07 追加完成 Phase L-pre：真实 Intel Brief LLM summary evidence 已可渲染为 Telegram 消息并进入 Telegram sender 合同层。证据 `packages/clawbot/data/intel_evidence/phasel/20260707T015241Z-telegram-summary-gate-blocked.json` 显示缺 token/chat/ack 时 gate blocked 且 `network_calls=0`；证据 `packages/clawbot/data/intel_evidence/phasel/20260707T015241Z-telegram-summary-contract-injected.json` 使用注入 transport 验证同一摘要消息的发送合同，`network=injected_transport`。

健康边界：这仍不是真实 Telegram 推送；没有真实第8 bot token/chat id，没有 Bot API 调用，没有生产 scheduler/cron/systemd，没有常驻 worker，没有新数据抓取。

### Intel Brief 本轮验证基线 — 2026-07-07T01:54Z

Telegram summary delivery 集成预演验证完成。证据路径：`packages/clawbot/data/intel_evidence/phasel/20260707T015419Z-telegram-summary-delivery-verification.json`。该验证覆盖 Phase L-pre evidence JSON、Telegram summary delivery ruff、Phase L-pre/Intel Brief/LLM routing 相关 pytest、token/chat/fake secret 泄漏检查、OpenEverything/VPS-Config diff check。生产边界不变：未调用真实 Telegram Bot API，未验证真实第8 bot token/chat id，未启用生产 scheduler/cron/systemd，未创建常驻 worker。


### Intel Brief Production Readiness — 只读审计已闭合，生产仍被硬闸门阻断

2026-07-07 追加完成 Phase M readiness 审计。证据 `packages/clawbot/data/intel_evidence/phasem/20260707T020329Z-production-readiness-audit.json` 显示：真实 collect evidence ready、summary evidence ready，但 Telegram sandbox gate、scheduler production gate、worker placement gate 未 ready，整体 `status=blocked`、`ready=2/5`、`network_calls=0`。

健康边界：这是生产门槛可见性，不是生产放行。当前仍缺 sandbox ack、chat id、worker placement confirmation、production ack，并且 production runner 仍显式未实现；没有真实 Telegram Bot API 调用，没有生产 scheduler/cron/systemd，没有常驻 worker。

### Intel Brief Telegram local bootstrap — 自举代码已就绪，真实发送待安全注入

新增 `telegram_bootstrap.py` 与 `intel_telegram_local_bootstrap.py`，用于本机 Telegram 沙盒自举：用户向 `@carven_Jianbao_bot` 发送 `/start intel_brief_sandbox` 后，脚本可用 Bot API `getUpdates` 自动发现 chat id 并发送真实 summary sandbox 消息。当前 gate-blocked evidence：`packages/clawbot/data/intel_evidence/phasel/20260707T021607Z-telegram-local-bootstrap-gate-blocked.json`，原因是 token 未通过安全运行时注入、sandbox ack 未设置、未允许真实网络，因此 `network_calls=0`。

健康边界：bot token 不应写入 repo/docs/evidence；真实发送前必须使用隐藏 prompt 或本地 env，并设置 `INTEL_BRIEF_TELEGRAM_SANDBOX_SEND_ACK=I_UNDERSTAND_TELEGRAM_SANDBOX_SEND`。这一步仍只是 sandbox，不启用 production scheduler。


### Intel Brief 本轮验证基线 — 20260707T022621Z

Phase M + Telegram local bootstrap 验证完成。证据路径：`packages/clawbot/data/intel_evidence/phasem/20260707T022907Z-production-readiness-bootstrap-verification.json`。该验证覆盖 readiness/bootstrap evidence JSON、ruff、相关 pytest、diff check 和真实 token 片段泄漏检查。生产边界不变：尚未真实调用 Telegram Bot API，尚未验证 chat id，尚未启用 production scheduler/cron/systemd，尚未创建常驻 worker。


### Intel Brief Production runner 合同 — 技术阻断已移除，真实门槛仍阻断

2026-07-07 追加完成 Phase N：`production_runner_not_implemented` 不再作为永久硬阻断。Production gate 现在要求 token/chat id、Telegram sandbox ack、worker placement confirmation、production ack、summary evidence 全部齐备才会进入 production branch。新 readiness evidence：`packages/clawbot/data/intel_evidence/phasem/20260707T024108Z-production-readiness-runner-contract-audit.json`，结果 `status=blocked`、`ready=2/5`、`network_calls=0`，缺口为 token/chat/ack/worker placement/production ack。

健康边界：这只证明 production runner 技术合同可达；真实 Telegram、真实 chat id、production scheduler 启用、常驻 worker、自然日演练仍未闭合。


### Intel Brief 本轮验证基线 — 2026-07-07T02:42Z

Phase N production runner 合同验证完成。证据路径：`packages/clawbot/data/intel_evidence/phasem/20260707T024229Z-production-runner-contract-verification.json`。该验证覆盖新 readiness evidence、runner-not-implemented 移除检查、ruff、Intel Brief/LLM routing 相关 pytest、diff check 和真实 token 片段泄漏检查。生产边界不变：真实 Telegram、chat id、production scheduler、常驻 worker、自然日演练仍未闭合。


### Intel Brief Phase O — Telegram sandbox 与 SGW preferred worker 已真实闭合

2026-07-07 追加完成真实 Telegram sandbox delivery 与 SGW preferred overseas worker 验证。Telegram 证据 `packages/clawbot/data/intel_evidence/phasel/20260707T024537Z-telegram-local-bootstrap-real-sandbox.json` 显示 Bot API `network_calls=3` 且发送成功；证据只记录 chat candidate 存在性，不含 token/chat id。

SGW 证据链：`20260707T024457Z-sgw-ssh-python-smoke.json` 证明 SGW SSH/Python 可用；`20260707T024555Z-sgw-senate-worker-remote-run.json` 记录首次 venv/ensurepip 失败且清理成功；修复 remote runner 后 `20260707T024852Z-sgw-senate-worker-remote-run-system-python.json` 在 SGW 成功抓取 Senate 数据并 cleanup verified。随后 `20260707T025103Z-collect-once-sgw-senate-yanhuoyun-akshare.json` 完成 SGW+Yanhuoyun collect-once，`success=2/failed=0`；`20260707T025315Z-scheduled-sgw-sandbox.json` 使用该输入完成 scheduled sandbox；`20260707T025328Z-production-readiness-sgw-placement-confirmed.json` 将 readiness 提升到 `ready=3/5`。

健康边界：这仍不是 production scheduler 启用。剩余缺口是把 Telegram token/chat/ack/production ack 安全配置到目标运行环境，并完成 production scheduler 与自然日观察。


### Intel Brief 本轮验证基线 — 2026-07-07T02:55Z

Phase O 最终验证完成。证据路径：`packages/clawbot/data/intel_evidence/phasen/20260707T025535Z-phase-o-telegram-sgw-verification.json`。验证覆盖真实 Telegram sandbox success、SGW preferred worker success、SGW+Yanhuoyun collect-once、scheduled sandbox、readiness 3/5、ruff、Intel Brief/LLM routing 相关 pytest、diff check 和真实 token 片段泄漏检查。生产边界不变：production scheduler/cron/systemd、生产 env 持久配置、常驻 worker、自然日生产演练仍未执行。


### Intel Brief Phase P — 私有 env 与 launch package dry-run 已就绪

2026-07-07 追加完成私有 env 机制和 launchd dry-run package。`intel_private_env.py` 会写 `.openclaw/intel-brief.production.env`（0600、gitignored）并输出脱敏 evidence；`intel_launch_package.py` 只生成 review-only launchd package，不执行 launchctl。当前 evidence：`packages/clawbot/data/intel_evidence/phasep/20260707T030509Z-private-env-audit-redacted.json`（blocked，未写真实 token）、`20260707T030509Z-launchd-dry-run-package.json`（generated，production_action=none）、`20260707T030727Z-readiness-private-env-path-blocked.json`（readiness 3/5）。

健康边界：私有 env 尚未真实写入，production scheduler 未启用，production ack 仍保留为单独人工门。


### Intel Brief 本轮验证基线 — 2026-07-07T03:08Z

Phase P private env / launch package 验证完成。证据路径：`packages/clawbot/data/intel_evidence/phasep/20260707T030858Z-phase-p-private-env-launch-verification.json`。该验证覆盖 private env audit、launchd dry-run package、private-env-path readiness、ruff、Intel Brief/LLM routing 相关 pytest、diff check 和真实 token 片段泄漏检查。生产边界不变：真实私有 env 写入、production ack、scheduler 安装/加载、自然日演练仍未执行。


### Intel Brief Phase Q — production-once 入口已就绪但被 gate 阻断

2026-07-07 新增一次性 production runner：`intel_production_once.py`。它在发送前复用 production gate，缺 token/chat/ack/worker placement/production ack 时 `network_calls=0`。证据：`packages/clawbot/data/intel_evidence/phaseq/20260707T031446Z-production-once-private-env-blocked.json`。launchd dry-run package 已升级为指向 production_once，证据 `packages/clawbot/data/intel_evidence/phaseq/20260707T031446Z-launchd-production-once-dry-run-package.json`，仍未安装/加载。

### Intel Brief Phase R — Telegram Bot API production-once 已闭合（未启用调度）

2026-07-07 最新状态：私有 env 已 ready，readiness 在无 production ack 时正确保持 blocked（`ready=4/5`，只缺 `production_ack_missing`）；production-once runner 已修复 private env 传递问题。使用临时 production ack 运行一次性 production runner 后，真实 Telegram Bot API `sendMessage` 成功，证据 `packages/clawbot/data/intel_evidence/phaser/20260707T032645Z-production-once-real-delivery.json` 显示 `status=success`、`network_calls=1`、`send_result.success=true`、message_id 存在且脱敏。

健康边界：这证明 Telegram Bot API 与一次性 production runner 路径已可用，但不是生产 scheduler 闭环。当前未安装/加载 launchd，未注册 cron/systemd，未创建常驻 worker，未完成自然日到点观察，production ack 未持久化，MediaCrawler 社媒登录态仍未闭合。

验证基线：`packages/clawbot/data/intel_evidence/phaser/20260707T033355Z-phase-r-production-once-final-verification.json`。该基线确认 evidence JSON、gitignore、ruff、pytest、diff check 和变更文件密钥片段扫描均通过。

### Intel Brief Phase S — fresh production cycle 已真实闭合（未启用定时）

2026-07-07 最新状态：production cycle 已能从当前 controller 一次性完成 fresh run：SGW `senate_trading` 与炎火云 `akshare` 重新远程采集，两个 child run 均 cleanup verified；随后生成 brief/summary，并经 production-once 调用 Telegram Bot API `sendMessage` 成功。证据：`packages/clawbot/data/intel_evidence/phases/20260707T034621Z-production-cycle-real-delivery.json`。

健康边界：这证明“新采集→新摘要→真实 Telegram 投递”的 one-shot 生产链路可用，不是固定旧 summary 重放；但仍不是自然日 scheduler 闭环。当前未安装/加载 launchd，未注册 cron/systemd，未创建常驻 worker，production ack 未持久化，MediaCrawler 社媒登录态仍未闭合。

验证基线：`packages/clawbot/data/intel_evidence/phases/20260707T035130Z-phase-s-production-cycle-final-verification.json`。该基线确认 fresh cycle evidence、ruff、pytest、diff check、gitignore 和变更文件密钥片段扫描均通过。

### Intel Brief Phase T — LaunchAgent 已加载（自动运行待观察）

2026-07-07 最新状态：本机 macOS LaunchAgent `ai.openclaw.intel-brief.scheduler` 已安装并加载，指向 fresh `intel_production_cycle.py`，日历触发 08:30。最新证据 `packages/clawbot/data/intel_evidence/phaset/20260707T040135Z-launchd-production-cycle-reinstall-load-absolute.json` 显示 `status=loaded`、`network_calls=0`、`uses_absolute_run_paths=true`。

健康边界：没有执行 kickstart，因此没有立即重复发 Telegram；下一次真正自动调度还需要等日历触发后检查 runs/latest-production-cycle.json 与日志。回滚命令已记录在 evidence。

验证基线：`packages/clawbot/data/intel_evidence/phaset/20260707T041245Z-phase-t-launchagent-final-verification.json`。该基线确认 LaunchAgent loaded、目标 production cycle、绝对 evidence/log 路径、ruff/pytest/diff/gitignore 与密钥片段扫描均通过；自然日自动运行仍未完成。

### Intel Brief Phase U — 自动运行审计入口已就绪，当前未触发

2026-07-07 最新状态：新增 LaunchAgent post-run audit 工具，当前真实审计 `packages/clawbot/data/intel_evidence/phaseu/20260707T041950Z-launchagent-post-run-audit-pending.json` 显示 `pending_calendar_trigger`，`launchctl.runs=0`，`last_exit_code=(never exited)`，run evidence 尚不存在。这与当前尚未到下一次 08:30 触发时间一致。

下一次 08:30 后必须用同一审计工具确认 `verified_success`，才能声明自然日自动运行闭环完成。

验证基线：`packages/clawbot/data/intel_evidence/phaseu/20260707T042640Z-phase-u-launchagent-audit-final-verification.json`。该基线确认审计工具和当前 pending 状态本身已验证；自然日自动运行仍待下一次 calendar trigger 后复核。

### Intel Brief Telegram Bot API — 2026-07-07T12:34Z 复核通过

Telegram Bot API 当前不是卡点。复核证据：私有 env audit `packages/clawbot/data/intel_evidence/phasetelegram/20260707T123333Z-telegram-private-env-audit.json` 显示 token/chat/ack/worker placement 均已配置且 env 文件为 `0600`；真实 `sendMessage` 证据 `packages/clawbot/data/intel_evidence/phasetelegram/20260707T123350Z-telegram-bot-api-real-send-probe.json` 显示发送成功；真实 `getMe` 证据 `packages/clawbot/data/intel_evidence/phasetelegram/20260707T123424Z-telegram-bot-api-getme-probe.json` 返回 username `carven_Jianbao_bot`。证据均不包含 token/chat id 明文。

健康边界：Bot API 已可用，但自然日 08:30 LaunchAgent 生产调度仍待观察；SGW 间歇 SSH timeout 需要后续加 fallback/容错。

### Intel Brief Phase W — SGW fallback 容错与 calendar canary 通过

2026-07-07 最新状态：`senate_trading` 已具备 SGW preferred → oracle-arm1 fallback 的受控容错路径；remote runner 对初始 SSH staging failure 会 fail-fast，避免一次 SGW 管理路径 timeout 放大成多次 SSH timeout。受控 fallback 证据 `packages/clawbot/data/intel_evidence/phasew/20260707T124408Z-forced-senate-fallback/collect-once.json` 显示 primary SSH 失败后 fallback 到 `oracle-arm1-overseas-fallback` 并真实抓取成功，cleanup verified。

真实 production cycle 证据 `packages/clawbot/data/intel_evidence/phasew/20260707T124152Z-production-cycle-with-sgw-fallback/latest-production-cycle.json` 显示当前 SGW primary 已恢复可用，SGW+Yanhuoyun collect `success=2/failed=0`，Telegram delivery 成功。真实 LaunchAgent calendar canary 证据 `packages/clawbot/data/intel_evidence/phasew/20260707T125003Z-launchd-calendar-canary-verified/post-run-audit.json` 显示 `verified_success`、`launchctl.runs=1`、`last_exit_code=0`、Telegram message_id present；rollback 证据显示临时 canary 已删除。

健康边界：正式 daily label `ai.openclaw.intel-brief.scheduler` 仍未经历自然日 08:30 触发，当前 `runs=0`；因此还不能把完整自然日生产闭环标为完成。远端 worker 仍为临时 `/tmp` staging，不是 VPS 常驻服务。

Phase W 最终验证基线：`packages/clawbot/data/intel_evidence/phasew/20260707T125656Z-phase-w-final-verification.json`。该基线确认 JSON、ruff、pytest、diff check、Token 片段扫描、canary removal 与 daily LaunchAgent loaded 状态均通过；自然日 08:30 正式触发仍待观察。

### Intel Brief Phase X — 正式 daily LaunchAgent 等待自然触发

2026-07-07 本地 06:58 MDT 审计正式 daily LaunchAgent：`ai.openclaw.intel-brief.scheduler` 已加载，目标为 `intel_production_cycle.py`，但 `runs=0`、`last_exit_code=(never exited)`，run evidence 尚不存在。这是 08:30 前的预期状态。证据：`packages/clawbot/data/intel_evidence/phasex/20260707T125904Z-daily-launchagent-pre-trigger-pending-audit.json`。

已创建一次性线程 heartbeat，在本地 08:40 左右继续审计正式 daily 自然触发结果。当前不能把目标标记 complete。

Phase X 预触发等待阶段最终验证：`packages/clawbot/data/intel_evidence/phasex/20260707T130040Z-phase-x-pretrigger-final-verification.json`。该基线确认 pending audit/heartbeat evidence JSON、diff check、Token 片段扫描和 daily LaunchAgent loaded 状态均通过；正式自然触发仍需 08:40 后继续审计。

Phase X 重复预触发审计：`packages/clawbot/data/intel_evidence/phasex/20260707T130243Z-daily-launchagent-repeat-pre-trigger-audit.json`。本地 07:02 MDT 仍早于正式 08:30 触发，daily LaunchAgent `runs=0`；一次性 heartbeat 配置存在且 active，将在本地 08:40 继续审计。

### Intel Brief Phase X — 正式 daily LaunchAgent 自然触发已闭合

2026-07-07 本地 08:30，正式 daily LaunchAgent `ai.openclaw.intel-brief.scheduler` 自然触发成功。launchctl 显示 `runs=1`、`last_exit_code=0`；run evidence `packages/clawbot/data/intel_evidence/phaset/20260707T040135Z-launchd-production-cycle-install-package-absolute/runs/latest-production-cycle.json` 显示 fresh production cycle `status=success`，SGW Senate + Yanhuoyun AKShare collect `success=2/failed=0`，Telegram delivery 成功且 message_id present。正式 post-run audit `packages/clawbot/data/intel_evidence/phasex/20260707T144102Z-daily-launchagent-post-run-audit.json` 为 `verified_success`。

一次性 heartbeat 已清理，证据 `packages/clawbot/data/intel_evidence/phasex/20260707T145534Z-heartbeat-cleanup-after-daily-success.json`。当前生产闭环的剩余健康边界：VPS 侧仍未创建常驻 worker，远端仍为 controller 驱动的临时 `/tmp` staging；这与当前架构设计一致。

Phase X 最终验证基线：`packages/clawbot/data/intel_evidence/phasex/20260707T145702Z-daily-launchagent-closure-final-verification.json`。该基线确认正式 daily natural trigger、run evidence success、Telegram delivery success、post-run audit verified、ruff/pytest/diff/token scan 全部通过。当前 Intel Brief 最小生产闭环已完成；后续风险主要是数据源扩容、社媒登录态无人值守和是否把临时 remote staging 升级为 VPS 常驻 worker。

### Intel Brief Phase Y — 商业订阅 MVP 数据层就绪

2026-07-07 新增商业订阅 MVP 数据层：`src/intel/subscriptions.py` 与 schema 的 `delivery_preferences` / `subscription_audit_log`。sandbox 证据 `packages/clawbot/data/intel_evidence/phasey/20260707T152655Z-commercial-mvp-subscription-contract/evidence.json` 显示 active 用户可按分类进入 eligible recipients，到期用户被排除，Telegram menu contract 可生成。当前边界：这还没有接入真实 Telegram bot handler，也没有接入闲鱼/支付自动授权；只是商业 MVP 所需的数据与菜单合同层。

Phase Y 最终验证基线：`packages/clawbot/data/intel_evidence/phasey/20260707T153329Z-commercial-mvp-subscription-final-verification.json`。该基线确认商业订阅数据层和 Telegram 菜单合同的 sandbox evidence、ruff、pytest、diff check、Token 扫描均通过。下一健康门槛：真实 Telegram handler 与 production delivery 按订阅偏好筛选。

### Intel Brief Phase Z — Telegram 用户菜单 handler contract 就绪

2026-07-07 最新状态：新增 Intel Brief Telegram 菜单 handler contract，能够在 sandbox DB 中完成 `/start` 创建用户、人工授权后 `/sources` 设置分类、`/schedule` 设置推送时间、`/custom 周杰伦` 写入开放人物追踪与审计日志、`/status` 返回 active profile。证据：`packages/clawbot/data/intel_evidence/phasez/20260707T155448Z-telegram-menu-handler-contract/evidence.json`。

健康边界：本阶段没有调用 Telegram Bot API，也没有启动真实 long-polling/webhook；没有触发社媒抓取；没有调用支付/闲鱼；没有修改正式 LaunchAgent 或生产 DB。商业化订阅 MVP 下一门槛是把 handler contract 接入真实 `intel_brief_bot` runtime，并让 daily production delivery 按订阅/偏好筛选真实收件人。

Phase Z 最终验证基线：`packages/clawbot/data/intel_evidence/phasez/20260707T155805Z-telegram-menu-handler-final-verification.json`。该基线确认 sandbox evidence、ruff、pytest、diff check 和 Telegram token 形态扫描均通过；真实 Bot runtime 与按订阅筛选投递仍是下一健康门槛。

### Intel Brief Phase AA — Telegram runtime adapter sandbox 就绪

2026-07-07 最新状态：新增 Telegram runtime adapter，可处理 Telegram-shaped updates 并通过注入式 sender 回复。sandbox evidence `packages/clawbot/data/intel_evidence/phaseaa/20260707T160334Z-telegram-runtime-adapter-sandbox/evidence.json` 显示 5 条 update 全部处理并成功 reply，final profile active，分类/时间/人物追踪偏好已保存，`network_calls=0`。

健康边界：仍未接入真实 Telegram Bot API `getUpdates`/webhook，未设置真实 bot commands，未写生产 DB，未按订阅筛选 daily production delivery。下一健康门槛是用真实 Bot API 完成 setMyCommands/getUpdates/sendMessage 的受控证据，且不泄漏 token/chat id。

Phase AA 最终验证基线：`packages/clawbot/data/intel_evidence/phaseaa/20260707T160655Z-telegram-runtime-adapter-final-verification.json`。该基线确认 runtime sandbox evidence、ruff、pytest、diff check 和 Telegram token 形态扫描均通过；真实 Bot API runtime 与按订阅筛选投递仍是下一健康门槛。

### Intel Brief Phase AB — Telegram Bot API runtime gate 已真实通过

2026-07-07 最新状态：新增 Bot API runtime probe，并用私有 env 真实调用 Telegram Bot API。真实证据 `packages/clawbot/data/intel_evidence/phaseab/20260707T161129Z-telegram-bot-runtime-real-probe.json` 显示 gate ready、`setMyCommands` success、`getUpdates` success、`network_calls=2`；Bot commands 已注册为 Intel Brief 菜单命令。证据只记录 update/chat 计数，不持久化 raw updates、chat id、user id 或消息文本。

健康边界：当前仍未自动回复真实用户，未写生产 DB，未保存 update offset，未接入 long-polling/webhook。下一健康门槛是受控处理真实 updates：持久化 offset、防重复回复、写入正式订阅 DB，并使用真实 `sendMessage` 回复。

Phase AB 最终验证基线：`packages/clawbot/data/intel_evidence/phaseab/20260707T161357Z-telegram-bot-runtime-final-verification.json`。该基线确认真实 Bot API `setMyCommands`/`getUpdates`、ruff、pytest、diff check、token/raw-update scan 均通过；下一健康门槛是 offset 持久化与真实 update 自动回复。

### Intel Brief Phase AC — Telegram update offset 防重复沙盒通过

2026-07-07 最新状态：新增 `telegram_runtime_state` 与 update processor。sandbox evidence `packages/clawbot/data/intel_evidence/phaseac/20260707T161820Z-telegram-update-processor-offset-sandbox/evidence.json` 显示 offset 从 `0` 推进到 `100`，再从 `100` 推进到 `103`；重复 replay 时 request offset 为 `104` 且 `handled_count=0`，避免重复回复历史 commands。

健康边界：本阶段仍没有调用真实 Telegram Bot API 或 `sendMessage`，没有写 production DB。下一健康门槛是为真实处理设置明确 ack/baseline offset，避免历史 update 被批量回复，然后连接真实 Bot API client/sender。

Phase AC 最终验证基线：`packages/clawbot/data/intel_evidence/phaseac/20260707T162038Z-telegram-update-processor-final-verification.json`。该基线确认 offset sandbox、ruff、pytest、diff check、token/raw-chat scan 均通过；真实自动回复仍需显式 baseline offset/ack。

### Intel Brief Phase AD — Telegram baseline offset 已真实写入

2026-07-07 最新状态：真实 Bot API `getUpdates` baseline 已执行，正式 `packages/clawbot/data/intel_brief.db` 的 `telegram_runtime_state` 中 `intel_brief_bot.last_update_id=684746897`。证据：`packages/clawbot/data/intel_evidence/phasead/20260707T162505Z-telegram-baseline-offset-real.json`。这意味着后续真实自动回复应从 `684746898` 之后的新 update 开始，避免批量回复历史命令。

健康边界：本阶段没有调用 `sendMessage`，没有写用户订阅/偏好，未启动 long-polling/webhook。下一健康门槛是处理一条真实新命令并回复，同时写正式 DB。

Phase AD 最终验证基线：`packages/clawbot/data/intel_evidence/phasead/20260707T162726Z-telegram-baseline-offset-final-verification.json`。该基线确认真实 baseline offset、正式 DB offset、ruff、pytest、diff check、token/raw-update scan 均通过；真实新命令自动回复仍是下一健康门槛。

### Intel Brief Phase AE — 真实 update runner 已就绪，本次无新 update

2026-07-07 最新状态：真实 Telegram update runner 已执行一次。证据 `packages/clawbot/data/intel_evidence/phaseae/20260707T163143Z-telegram-real-update-runner-one-shot.json` 显示 gate ready，request offset `684746898`，真实 `getUpdates` 返回 0 条新 update，`send_message_attempted=false`，正式 DB offset 保持 `684746897`。

健康边界：runner 能安全处理新 update，但本次没有新用户命令，因此还没有真实 `sendMessage` 回复和正式 DB 用户偏好写入证据。下一健康门槛：让真实 Telegram 用户发送一个新命令后重跑 runner。

Phase AE 最终验证基线：`packages/clawbot/data/intel_evidence/phaseae/20260707T163352Z-telegram-real-update-runner-final-verification.json`。该基线确认真实 runner 空跑路径、正式 DB offset、ruff、pytest、diff check、token/raw-update scan 均通过；真实新命令自动回复仍是下一健康门槛。


## 43. Phase AF 订阅过滤投递健康基线（2026-07-07）

| 项目 | 当前结果 | 证据 | 边界 |
|---|---|---|---|
| Recipient filtering | 只选择 active、未过期、Telegram 渠道且 source preferences 命中 `akshare/senate_trading` 的订阅者。 | `packages/clawbot/data/intel_evidence/phaseaf/20260707T164449Z-subscription-filtered-delivery-sandbox/evidence.json` | sandbox DB；正式 DB 未变更。 |
| Delivery | fake sender 投递 2 人，`eligible=2/sent=2/failed=0`。 | 同上 | `network_calls=0`，没有 Telegram API 调用。 |
| Redaction | evidence 未写 raw chat id；只记录 presence 与摘要。 | `packages/clawbot/data/intel_evidence/phaseaf/20260707T165346Z-subscription-filtered-delivery-final-verification.json` | 测试文件内 fake chat id 仅用于脱敏断言。 |

最终验证 evidence：`packages/clawbot/data/intel_evidence/phaseaf/20260707T165346Z-subscription-filtered-delivery-final-verification.json`。验证通过项：ruff、pytest 16 项、OpenEverything/VPS-Config diff check、JSON/token/raw-chat evidence scan。当前健康边界：production daily delivery 尚未接入订阅过滤；真实 Telegram 新命令自动回复/正式 DB 写入仍待新 update 验证。


## 44. Phase AG Production-once 订阅投递开关健康基线（2026-07-07）

| 项目 | 当前结果 | 证据 | 边界 |
|---|---|---|---|
| 默认兼容 | `INTEL_BRIEF_SUBSCRIPTION_DELIVERY_ENABLED` 未开启时仍为 `delivery_mode=fixed_chat`。 | `packages/clawbot/data/intel_evidence/phaseag/20260707T165951Z-production-once-subscription-delivery-switch-sandbox/evidence.json` | 保护已闭环 daily LaunchAgent。 |
| 订阅投递接线 | 开关开启且 `INTEL_BRIEF_DB_PATH` 存在时进入 `delivery_mode=subscription_filtered`。 | 同上 | sandbox 注入式 runner；未调用 Telegram。 |
| 缺 DB 阻断 | 开关开启但 DB path 缺失时 blocked，`network_calls=0`。 | 同上 | 防止误切后静默投递到错误目标。 |

最终验证 evidence：`packages/clawbot/data/intel_evidence/phaseag/20260707T170034Z-production-once-subscription-switch-final-verification.json`。验证通过项：ruff、pytest 22 项、OpenEverything/VPS-Config diff check、JSON/token/evidence scan。当前健康边界：正式 daily LaunchAgent 尚未切换到订阅投递；真实 Telegram 用户 DB 写入仍待新 update。


## 45. Phase AI Telegram inline keyboard 菜单健康基线（2026-07-07）

| 项目 | 当前结果 | 证据 | 边界 |
|---|---|---|---|
| 菜单形态 | `/start` 发送消息内 `inline_keyboard`，不是底部 `keyboard`。 | `packages/clawbot/data/intel_evidence/phaseai/20260707T172324Z-real-telegram-inline-keyboard-menu-send/evidence.json` | UI/交互层修正。 |
| 菜单规模 | 5 行、22 个按钮，按钮均带 `callback_data`。 | 同上 | 不记录具体 chat/user/token。 |
| 回调能力 | runtime 支持 `callback_query`；sender 支持 `answerCallbackQuery`。 | `packages/clawbot/data/intel_evidence/phaseai/20260707T172410Z-inline-keyboard-menu-final-verification.json` | 真实用户点击回调待下一次实际点击记录。 |
| 验证 | ruff、pytest 36 项、diff check、脱敏扫描通过。 | `packages/clawbot/data/intel_evidence/phaseai/20260707T172410Z-inline-keyboard-menu-final-verification.json` | 未改变 daily LaunchAgent 或订阅授权。 |

## 46. Phase AK Telegram 菜单截图式网格健康基线（2026-07-07）

| 项目 | 当前结果 | 证据 | 边界 |
|---|---|---|---|
| 菜单正文 | 已移除旧的 `命令：/sources...` 说明，改为短标题/短说明。 | `packages/clawbot/data/intel_evidence/phaseak/20260707T174008Z-reference-style-telegram-menu-send/evidence.json` | UI 层修正。 |
| 按钮矩阵 | `inline_keyboard` 6 行 22 个按钮，行宽 `[4,4,4,4,4,2]`，最大 4 列。 | 同上 | 不是底部 reply keyboard。 |
| 真实发送 | Telegram `sendMessage` 成功，`message_id_present=true`，证据不含 token/chat id/user id。 | 同上 | 没有改变订阅、调度或 VPS。 |

当前健康边界：真实用户点击 callback 的生产 evidence 仍待用户实际点击后由 runner 记录；daily production delivery 尚未切换到订阅过滤投递。

## 47. Phase AJ 真实订阅过滤投递健康基线（2026-07-07）

| 项目 | 当前结果 | 证据 | 边界 |
|---|---|---|---|
| Entitlement | 正式 DB 中 1 个 Telegram subscriber 具备 active 内部测试订阅。 | `packages/clawbot/data/intel_evidence/phaseaj/20260707T172805Z-production-subscriber-internal-test-entitlement/evidence.json` | 内部测试授权，不是支付/闲鱼订单自动化。 |
| Preference filtering | summary categories `akshare/senate_trading` 命中 subscriber 偏好。 | `packages/clawbot/data/intel_evidence/phaseaj/20260707T174622Z-real-subscription-filtered-delivery/evidence.json` | 当前只有 1 个真实 subscriber。 |
| Real delivery | Telegram `sendMessage` 成功，`eligible=1/sent=1/failed=0`，`network_calls=1`。 | 同上 | 这是受控单次投递，不是自然 daily cycle。 |
| DB delivery log | `delivery_log` 增加 1 条 success 记录。 | 同上与正式 DB 复核 | 不持久化 raw chat id。 |
| Redaction | evidence 不包含 token/chat id/user id；delivery result 只保留 presence flags。 | 后续 Phase AJ final verification | 测试内 fake ids 仅用于脱敏断言。 |

当前健康边界：daily production LaunchAgent 尚需切换到 subscription-filtered delivery 并等待自然 08:30 触发验证；支付/闲鱼订单授权自动化仍未完成。

## 48. Phase AL daily 订阅投递切换健康基线（2026-07-07）

| 项目 | 当前结果 | 证据 | 边界 |
|---|---|---|---|
| 私有 env | 已启用 `INTEL_BRIEF_SUBSCRIPTION_DELIVERY_ENABLED` 并配置正式 DB path；只记录 presence。 | `packages/clawbot/data/intel_evidence/phaseal/20260707T175654Z-daily-subscription-mode-production-once/private-env-subscription-switch.json` | 私有 env 不提交；不输出 token/chat id。 |
| Gate hardening | 订阅投递模式要求 token present、DB path present、DB exists。 | Phase AL final verification | 仍依赖 private env 正确维护。 |
| Controlled production_once | 受控运行进入 `delivery_mode=subscription_filtered`，真实发送 1 条。 | `packages/clawbot/data/intel_evidence/phaseal/20260707T175654Z-daily-subscription-mode-production-once/evidence.json` | 不是自然 LaunchAgent 触发。 |
| DB delivery log | 受控验证使 `delivery_log` 再增加 1 条 success。 | 同上 | 当前真实 subscriber 只有 1 个。 |
| 回滚 | 关闭/删除 `INTEL_BRIEF_SUBSCRIPTION_DELIVERY_ENABLED` 即回到 fixed-chat；无需重装 LaunchAgent。 | 文档基线 | 回滚会影响下一次 daily 投递模式。 |

当前健康边界：下一门槛是等待正式 `ai.openclaw.intel-brief.scheduler` 自然 08:30 触发后，审计 `latest-production-cycle.json` 确认 `delivery_mode=subscription_filtered` 且 `delivery_log_delta>=1`。支付/闲鱼订单授权自动化仍未完成。

## 49. Phase AM 受控 production_cycle 全链路健康基线（2026-07-07）

| 项目 | 当前结果 | 证据 | 边界 |
|---|---|---|---|
| Script path | 使用 LaunchAgent 同一脚本 `intel_production_cycle.py` 受控运行。 | `packages/clawbot/data/intel_evidence/phaseam/20260707T180242Z-controlled-production-cycle-subscription-mode/latest-production-cycle.json` | 不是自然 08:30 触发。 |
| Collect | `senate_trading` + `akshare` 采集 success=2/failed=0。 | 同上及 collect evidence | 当前数据源仍只有两个生产可用源。 |
| Delivery mode | production_once 进入 `subscription_filtered`。 | `.../runs/20260707T180242Z-production-once-delivery.json` | 依赖 private env 开关保持开启。 |
| Real delivery | Telegram 投递 `eligible=1/sent=1/failed=0`，network_calls=1。 | 同上 | 当前真实 subscriber 只有 1 个。 |
| DB log | `delivery_log` 至少 3 条 success。 | Phase AM final verification | 不持久化 raw chat id。 |

当前健康边界：自然 `ai.openclaw.intel-brief.scheduler` 08:30 subscription-filtered run 尚待下一次定时触发审计；支付/闲鱼订单授权自动化仍未实现。

## 50. Phase AN 订阅生命周期健康基线（2026-07-07）

| 项目 | 当前结果 | 证据 | 边界 |
|---|---|---|---|
| 到期审计 | 能识别 active 订阅中的已过期与 7 天内到期。 | `packages/clawbot/data/intel_evidence/phasean/20260707T181146Z-subscription-lifecycle-sandbox/evidence.json` | sandbox DB。 |
| 过期标记 | `apply_expiry=True` 时标记 expired 并写 audit。 | 同上 | 正式 DB 未启用该 mutation。 |
| 到期提醒 | `send_reminders=True` 且 sender 存在时发送提醒。 | 同上 | fake sender，真实 Telegram 未发送。 |
| 提醒去重 | 同日 replay `reminders_sent=0`。 | 同上 | 去重粒度 subscriber/plan/day。 |
| 正式 DB 审计 | 当前无已过期 active 订阅、无 7 天内到期订阅，counts unchanged。 | `packages/clawbot/data/intel_evidence/phasean/20260707T181219Z-production-db-subscription-lifecycle-readonly-audit/evidence.json` | 只读；未改订阅状态，未发提醒。 |

当前健康边界：订阅生命周期能力已可用，但还未接入 daily automation；下一步可把只读审计纳入 daily evidence，把提醒/过期标记作为独立显式开关上线。

## 51. Phase AO production_cycle 生命周期只读审计健康基线（2026-07-07）

| 项目 | 当前结果 | 证据 | 边界 |
|---|---|---|---|
| Daily evidence integration | `production_cycle` 顶层写入 `subscription_lifecycle`。 | `packages/clawbot/data/intel_evidence/phaseao/20260707T182041Z-production-cycle-lifecycle-readonly-integration/evidence.json` | injected delivery，非真实 Telegram 发送。 |
| Read-only lifecycle | `apply_expiry=false`、`send_reminders=false`。 | 同上 | 不改正式订阅状态，不发提醒。 |
| DB safety | 正式 DB counts unchanged。 | `.../wrapper.json` | 审计读取正式 DB。 |
| Missing DB behavior | DB path 缺失时 lifecycle skipped，不阻断主 cycle。 | `tests/test_intel_production_cycle.py` | 仍需保持 private env DB path 正确。 |

当前健康边界：下一次自然 08:30 LaunchAgent 审计需确认 `latest-production-cycle.json.subscription_lifecycle.status=success`，且自然投递仍为 `subscription_filtered`。

## 52. Phase AP 人工订单授权健康基线（2026-07-07）

| 项目 | 当前结果 | 证据 | 边界 |
|---|---|---|---|
| Dry-run | 可预览人工订单授权计划，不写业务行。 | `packages/clawbot/data/intel_evidence/phaseap/20260707T182938Z-manual-entitlement-sandbox/evidence.json` | sandbox DB。 |
| Apply | `--apply` 才 upsert subscriber/plan、grant subscription、设置偏好。 | 同上 | 未在正式 DB apply。 |
| Renewal | 从现有 active 到期日顺延。 | 同上 | 续费逻辑已测。 |
| Production dry-run | 当前真实 subscriber 30 天续费预演，正式 DB counts unchanged。 | `packages/clawbot/data/intel_evidence/phaseap/20260707T183007Z-production-db-manual-entitlement-dry-run/evidence.json` | 未修改正式 DB，未调用 Telegram/支付/闲鱼。 |
| Redaction | evidence 不含 raw Telegram user id、chat id、order ref；audit source 只存短哈希。 | Phase AP final verification | 操作员仍需妥善保管输入参数。 |

当前健康边界：这是人工核单桥，不是闲鱼/支付自动化；真正订单回调自动授权仍未实现。

## 52. Phase AR Telegram 菜单参考图一致性健康基线（2026-07-07）

| 项目 | 当前结果 | 证据 | 边界 |
|---|---|---|---|
| 首屏正文 | `/start` 首屏只显示 `🔥 热搜排行`、高价值情报入口、关键词搜索提示；不再输出 `inactive_or_expired` 或命令说明。 | `packages/clawbot/data/intel_evidence/phasear/20260707T185209Z-reference-screenshot-style-menu-contract-v2/evidence.json` | UI 文案修正。 |
| 按钮矩阵 | `inline_keyboard` 6 行 23 个按钮，行宽 `[4,4,4,4,4,3]`，最大 4 列。 | 同上 | 仍使用消息内 inline keyboard，不触碰调度/订阅授权。 |
| 真实发送 | Telegram `sendMessage` 成功，`reply_markup_kind=inline_keyboard`，证据不含 token/chat id/user id。 | `packages/clawbot/data/intel_evidence/phasear/20260707T185237Z-reference-screenshot-style-menu-real-send/evidence.json` | 发送 1 条菜单消息用于视觉验收；未修改 DB、LaunchAgent、VPS。 |
| 验证 | ruff 与 Telegram 菜单/运行时相关 pytest 通过。 | `packages/clawbot/data/intel_evidence/phasear/20260707T185522Z-reference-screenshot-menu-final-verification/evidence.json`。 | 不代表真实用户点击 callback 已验收。 |

## 53. Phase AQ GitHub Trending 高价值源健康基线（2026-07-07）

| 项目 | 当前结果 | 证据 | 边界 |
|---|---|---|---|
| 解析正确性 | 已覆盖普通 trending row 与 sponsor-link-before-repo 的回归测试，避免把 `/sponsors/...` 误当 repo。 | `packages/clawbot/tests/test_intel_github_trending.py`；ruff/pytest 通过。 | HTML 结构若大改仍需重新验证。 |
| 目标 worker 真实调用 | Oracle SG West 调用 GitHub Trending 成功，返回 3 条真实 repo，`raw_count=3`。 | `packages/clawbot/data/intel_evidence/phaseaq/20260707T190500Z-github-trending-oracle-sg-worker-parser-fixed.json` | 临时 `/tmp` worker，不是常驻服务。 |
| 三源生产链路 | 受控 production_cycle 采集 `senate_trading/akshare/github_trending`，collect `success=3/failed=0`。 | `packages/clawbot/data/intel_evidence/phaseaq/20260707T190718Z-controlled-production-cycle-three-sources/latest-production-cycle.json` | 受控运行，不等同自然 LaunchAgent 08:30 审计。 |
| 订阅过滤投递 | 三源 summary 生成后进入 `delivery_mode=subscription_filtered`，eligible=1/sent=1/failed=0。 | 同上：`steps.production_once.delivery.summary`。 | 当前真实用户偏好命中 `akshare/senate_trading`；GitHub 分类已可采集但是否启用由用户偏好决定。 |

## 54. Phase AU AI 模型动态源健康基线（2026-07-07）

| 项目 | 当前结果 | 证据 | 边界 |
|---|---|---|---|
| 官方源覆盖 | OpenAI RSS、Anthropic News、DeepSeek 官方首页公告均可在 Oracle SG West 获取并解析。 | `packages/clawbot/data/intel_evidence/phaseau/20260707T193548Z-ai-model-updates-oracle-sg-worker-final.json` | DeepSeek `/news` 在 Oracle SG West 返回 404，当前基线使用 `/`。 |
| 真实返回 | `raw_count=6`，providers 包含 `openai/anthropic/deepseek`。 | 同上 | 无 API token；HTML 结构变更需回归测试。 |
| source limit | GitHub daily 取 3 条，AI 动态取 6 条。 | `packages/clawbot/data/intel_evidence/phaseau/20260707T194551Z-controlled-production-cycle-four-sources-source-limits/latest-production-cycle.json` | Senate/A股仍各取 1 条 MVP 样本。 |
| 四源链路 | 四源 collect `success=4/failed=0`，真实 Telegram delivery 成功。 | 同上 | 受控运行；自然 LaunchAgent 下一次 08:30 仍需审计。 |

## 55. Phase AV 订阅正文按用户偏好过滤健康基线（2026-07-07）

| 项目 | 当前结果 | 证据 | 边界 |
|---|---|---|---|
| 收件人筛选 | 仍按 active subscription、未过期、Telegram channel、source preferences 匹配。 | `packages/clawbot/tests/test_intel_subscription_filtered_delivery.py` | 不改变订阅授权逻辑。 |
| 正文过滤 | 发送前按 recipient `matched_categories` 裁剪 summary items，并重写 summary_text，避免未订阅分类出现在消息正文和 delivery_log。 | `packages/clawbot/data/intel_evidence/phaseav/20260707T194902Z-subscription-delivery-per-recipient-filter-sandbox/evidence.json` | LLM 全局摘要不再原样发给用户，后续可升级为按用户偏好重算摘要。 |
| 真实投递验证 | 四源 production cycle 中当前真实 subscriber matched `akshare/senate_trading`，filtered_item_count=2，send_success=true。 | `packages/clawbot/data/intel_evidence/phaseau/20260707T194551Z-controlled-production-cycle-four-sources-source-limits/latest-production-cycle.json` | 当前真实 subscriber 未启用 GitHub/AI 偏好，因此真实消息只含已启用分类。 |

## Intel Brief health note — five-source controlled cycle after 13F aggregation (2026-07-07)

- Controlled production cycle evidence: `packages/clawbot/data/intel_evidence/phaseaw/20260707T201455Z-controlled-production-cycle-five-sources-13f-aggregated/latest-production-cycle.json`.
- Status: success. Collect summary `success=5/failed=0` across `senate_trading`, `akshare`, `github_trending`, `ai_model_updates`, `institutional_13f`.
- Delivery: subscription-filtered Telegram delivery success, `eligible=1/sent=1/failed=0`, `network_calls=1`; evidence stores only boolean token/chat presence.
- 13F source: Oracle SG West worker returned `raw_count=10` and cleanup `remote_stage_absent` after aggregation fix.
- Remaining production health boundary: this was a controlled one-shot cycle, not a natural LaunchAgent 08:30 trigger audit.

## Intel Brief LaunchAgent natural 08:30 audit note (2026-07-07)

- Superseded audit evidence: `packages/clawbot/data/intel_evidence/phaset/20260707T202022Z-launchagent-natural-0830-post-run-audit/evidence.json` originally stayed `pending_calendar_trigger` because it trusted only `launchctl runs`.
- Verified audit evidence: `packages/clawbot/data/intel_evidence/phaset/20260707T211424Z-launchagent-natural-0830-verified-with-artifact/evidence.json`.
- Run artifact inspected: `packages/clawbot/data/intel_evidence/phaset/20260707T040135Z-launchd-production-cycle-install-package-absolute/runs/latest-production-cycle.json`.
- Artifact status: success at `2026-07-07T14:30:05Z`, collect `success=2/failed=0`, production_once success, Telegram send success.
- Audit status is now `verified_success` with `verification.basis=artifact_and_standard_output`; current `launchctl print` still reports `runs=0` and `last exit code=(never exited)`, so the evidence explicitly records `launchctl.counter_mismatch=true`. No launchctl kickstart/bootstrap/bootout was executed.
- Boundary: this natural artifact predates the later six-source default cycle; it covered the installed two-source LaunchAgent package at that time.

## Intel Brief health note — six-source controlled cycle with weather (2026-07-07)

- Weather real worker evidence: `packages/clawbot/data/intel_evidence/phaseaz/20260707T204803Z-weather-oracle-sg-worker.json` (`status=success`, `raw_count=6`, cleanup `remote_stage_absent`).
- Controlled production cycle evidence: `packages/clawbot/data/intel_evidence/phaseaz/20260707T205021Z-controlled-production-cycle-six-sources-weather/latest-production-cycle.json`.
- Status: success. Collect summary `success=6/failed=0` across `senate_trading`, `akshare`, `github_trending`, `ai_model_updates`, `institutional_13f`, `weather`.
- Delivery: subscription-filtered Telegram delivery success, `eligible=1/sent=1/failed=0`, current subscriber still matched only `akshare/senate_trading`, so weather was collected and summarized but not sent to that subscriber.
- Boundary: this is a controlled one-shot cycle. Next natural 08:30 LaunchAgent audit is still required to prove the updated six-source default in calendar mode.
- Commercial-use note: Open-Meteo air-quality endpoint is acceptable for no-key MVP verification but requires commercial-use review before paid public rollout.

## Intel Brief LaunchAgent natural 08:30 verified_success after audit hardening (2026-07-07)

| 项目 | 当前结果 | 证据 | 边界 |
|---|---|---|---|
| Audit hardening | `intel_launchagent_audit.py` 现在可在 `launchctl runs` 计数滞后但 artifact/stdout 均成功时给出 `verified_success`，同时记录 `launchctl.counter_mismatch=true`。 | `packages/clawbot/tests/test_intel_launchagent_audit.py`；ruff/pytest 通过。 | 不隐藏 counter mismatch；审计报告保留 `verification.basis=artifact_and_standard_output`。 |
| Natural 08:30 run | 正式 `ai.openclaw.intel-brief.scheduler` 在 `2026-07-07T14:30:05Z` 产出 `latest-production-cycle.json`，collect `success=2/failed=0`，真实 Telegram send success。 | `packages/clawbot/data/intel_evidence/phaset/20260707T211424Z-launchagent-natural-0830-verified-with-artifact/evidence.json` | 只读审计；未 kickstart/重装/重载 LaunchAgent。 |
| Six-source boundary | 六源链路已有 controlled cycle `success=6/failed=0`，但尚未由自然 08:30 LaunchAgent 触发。 | `packages/clawbot/data/intel_evidence/phaseaz/20260707T205021Z-controlled-production-cycle-six-sources-weather/latest-production-cycle.json` | 下一次自然 08:30 后需要再次审计，以证明当前六源默认链路在 calendar mode 下运行。 |

## 57. Phase BC 订阅生命周期生产安全维护入口（2026-07-07）

| 项目 | 当前结果 | 证据 | 边界 |
|---|---|---|---|
| Maintenance CLI | 新增 `intel_subscription_lifecycle.py`；默认只读，显式 gate 才允许过期标记或 Telegram 到期提醒。 | `packages/clawbot/tests/test_intel_subscription_lifecycle.py` | CLI 不是自动支付/闲鱼续费入口，只处理已有订阅状态。 |
| Apply gate | `--apply-expiry` 缺 `INTEL_BRIEF_SUBSCRIPTION_LIFECYCLE_APPLY_ACK` 时 blocked，DB 不变。 | `packages/clawbot/data/intel_evidence/phasebc/20260707T212320Z-subscription-lifecycle-maintenance-sandbox/evidence.json` | 生产未执行 apply。 |
| Reminder gate | `--send-reminders` 需要 Telegram token、runtime ack、`--allow-real-network`；sandbox 使用 injected transport 验证，不走真实 Telegram。 | 同上 | 生产未发送 reminder。 |
| Production readonly | 正式 DB 当前 `expired_active_found=0`、`expiring_active_found=0`、`network_calls=0`。 | `packages/clawbot/data/intel_evidence/phasebc/20260707T212337Z-subscription-lifecycle-production-readonly/evidence.json` | 只读；未改订阅状态，未写提醒 audit，未发 Telegram。 |

当前健康边界：订阅到期管理已经从“只有库函数/沙盒”推进到“可运行的生产安全 CLI”。下一步可选择是否把该 CLI 纳入独立日常运维计划；在未确认前，daily `production_cycle` 仍只做 lifecycle readonly audit。

## 58. Phase BD LaunchAgent 下一次六源自然触发 readiness（2026-07-07）

| 项目 | 当前结果 | 证据 | 边界 |
|---|---|---|---|
| Plist source mode | 已安装 LaunchAgent 调用 `intel_production_cycle.py`，没有固定 `--source` 参数，因此下一次触发会读取当前代码的默认源。 | `packages/clawbot/data/intel_evidence/phasebd/20260707T213012Z-launchagent-next-run-six-source-readiness/evidence.json` | 只读审计；未重装/重载 LaunchAgent。 |
| Current defaults | 当前 `DEFAULT_PRODUCTION_CYCLE_SOURCES` 为六源：`senate_trading/akshare/github_trending/ai_model_updates/institutional_13f/weather`。 | 同上；`packages/clawbot/src/intel/production_cycle.py` | 代码默认值已更新。 |
| Controlled proof | 六源 controlled cycle collect `success=6/failed=0`，sources 与默认值一致。 | 同上关联 `phaseaz/20260707T205021Z-controlled-production-cycle-six-sources-weather/latest-production-cycle.json` | controlled cycle 不是自然触发。 |
| Previous natural proof | 上一条自然 08:30 已 verified success，但发生在六源接入前。 | 同上关联 `phaset/20260707T211424Z-launchagent-natural-0830-verified-with-artifact/evidence.json` | 下一次自然 08:30 后仍需复审六源真实触发。 |

当前健康边界：LaunchAgent 下一次六源自然触发 readiness 已成立；目标闭环仍需等待下一次 08:30 自然运行后用 post-run audit 证明真实 calendar mode 六源执行和定制化投递。

## 59. Phase BE 商业 MVP E2E 状态审计与投递文案修复（2026-07-07）

| 项目 | 当前结果 | 证据 | 边界 |
|---|---|---|---|
| 投递文案 | 真实 Telegram 投递不再显示 `sandbox fake Telegram sender` / `未调用真实 Bot API`；改为公开来源与非投资建议提示。 | `packages/clawbot/data/intel_evidence/phasebe/20260707T213634Z-production-once-user-facing-delivery-copy/evidence.json` | 真实发送 1 条修正文案验收消息。 |
| Subscription filtered delivery | 当前真实 subscriber matched `akshare/senate_trading`，filtered item count=2，eligible=1/sent=1/failed=0。 | 同上 | 未改变用户偏好或授权。 |
| E2E 状态审计 | 当前正式 DB 有 1 个 active eligible Telegram subscriber；有分类偏好；最新 delivery_log success；不含 sandbox/fake 文案；无未订阅源标记；next-run readiness=ready。 | `packages/clawbot/data/intel_evidence/phasebe/20260707T213933Z-commercial-mvp-e2e-status-audit/evidence.json` | 审计只读，不发消息、不改 DB。 |
| Redaction | E2E evidence 不写 raw chat id、user id、Telegram token、raw delivery content。 | `packages/clawbot/tests/test_intel_e2e_status_audit.py` | 仅记录 presence/booleans/计数。 |

当前健康边界：真实用户从 active 订阅、偏好、定制化投递到最新 delivery_log 的当前状态已 `verified`。最终目标仍需下一次自然 08:30 后证明六源默认链路真实在 calendar mode 下执行。

## 60. Phase BF Telegram 菜单 v4 截图式交互修复（2026-07-07）

| 项目 | 当前结果 | 证据 | 边界 |
|---|---|---|---|
| `/start` 菜单正文 | 已改为 `CARVEN 情报简报` + 热搜排行短文案；不显示订阅状态、分类状态或命令说明。 | `packages/clawbot/data/intel_evidence/phasebf/20260707T215214Z-screenshot-like-telegram-menu-v4/evidence.json` | 不改订阅授权/偏好。 |
| Inline 按钮矩阵 | 7 行矩阵，含 GitHub/AI/社媒/天气/财经/设置/搜索/功能导航入口。 | 同上 | 按钮仍复用现有 callback handler。 |
| 底部快捷键盘 | 新增 persistent keyboard：`👥 功能导航 / 🔥 热搜排行`；runtime 对菜单类回复支持先安装底部键盘再发 inline 菜单。 | `packages/clawbot/data/intel_evidence/phasebf/20260707T215317Z-screenshot-like-menu-v4-real-send/evidence.json` | 真实发送 2 条 Telegram 验证消息；证据脱敏。 |
| 功能导航行为 | `👥 功能导航` 不再进入 status/settings 状态页，改为返回菜单卡片。 | `packages/clawbot/tests/test_intel_telegram_menu_handlers.py` | `设置/订阅/状态` 仍可查看状态。 |
| Native commands | `setMyCommands` 真实调用成功。 | `packages/clawbot/data/intel_evidence/phasebf/20260707T215248Z-telegram-command-menu-registration-v4.json` | 不持久化 raw update/chat id。 |

当前健康边界：菜单 UX 已按用户截图方向修复，并已真实发送验证。生产闭环仍需下一次自然 08:30 后证明六源默认链路在 calendar mode 下真实执行。

## 61. Phase BG LaunchAgent 六源 post-run audit 强约束（2026-07-07）

| 项目 | 当前结果 | 证据 | 边界 |
|---|---|---|---|
| CLI 参数 | `intel_launchagent_audit.py` 支持重复 `--expected-source`。 | `packages/clawbot/tests/test_intel_launchagent_audit.py` | 只读审计参数；不触发 launchd。 |
| Evidence 字段 | 审计输出记录实际源、期望源、缺失源、意外源、失败源、source match 与 collect success match。 | `packages/clawbot/data/intel_evidence/phasebg/20260707T220027Z-launchagent-six-source-expected-regression/evidence.json` | 不写 token/chat id/user id。 |
| 回归结果 | 旧自然 08:30 两源 artifact 在六源 expected audit 下返回 `failed_or_incomplete`，缺失 4 个源。 | 同上 | 证明旧自然运行不能再被误当作六源闭环。 |
| 下一次验收口径 | 下一次自然 08:30 后必须 expected-source 六源均成功才能算 `verified_success`。 | `packages/clawbot/src/intel/launchagent_audit.py` | 当前仍未证明下一次自然六源已实际触发。 |

当前健康边界：post-run audit 已具备防误判能力；商业化 MVP 目标仍需下一次自然 08:30 后产出六源 `verified_success` 证据。

## 62. Phase BH 商业 MVP E2E 审计接入自然六源验收门（2026-07-07）

| 项目 | 当前结果 | 证据 | 边界 |
|---|---|---|---|
| E2E 新门禁 | `intel_e2e_status_audit.py` 支持 `--launchagent-audit-evidence`，并新增 `natural_six_source_launchagent_verified`。 | `packages/clawbot/tests/test_intel_e2e_status_audit.py` | 只读审计；不触发 launchd。 |
| 当前生产 E2E | subscriber/偏好/最新投递/next-run readiness 均通过。 | `packages/clawbot/data/intel_evidence/phasebh/20260707T220524Z-commercial-mvp-e2e-requires-natural-six-source/evidence.json` | 未发送 Telegram，未改 DB。 |
| 未完成原因 | 引用的自然 LaunchAgent 六源审计为 `failed_or_incomplete`，缺失 `github_trending/ai_model_updates/institutional_13f/weather`。 | 同上 | 这是旧两源自然 artifact 的预期结果。 |
| 完成条件 | 下一次自然 08:30 后，六源 expected-source post-run audit 必须 `verified_success`，再进入 E2E audit。 | Phase BG/Phase BH 脚本 | 当前不能标记目标 complete。 |

当前健康边界：商业 MVP E2E 总审计已具备最终完成门禁，且当前状态正确保持 `needs_attention`，避免提前宣布闭环。
