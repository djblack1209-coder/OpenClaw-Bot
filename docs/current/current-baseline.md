# JIYU AI 当前生产基线

> 更新时间：2026-08-16（Asia/Singapore；本轮最终复查完成于 2026-08-16T03:42Z，跨项目备份状态于 2026-08-16T05:47Z 收口）。生产运行时是唯一事实；仓库仅用于必要维护、恢复和异地备份。`docs/current/` 只保留本文件。

## 范围与结论

- 范围仅限本机 Mac OpenClaw/ClawBot 与 Oracle Singapore JIYU/Sub2API。中国 origin、腾讯旧备机和其他项目未修改。
- 闲鱼商品已全部下架且无待处理订单；闲鱼客服、卖家桥、自动交付、Frist-API、CC 中转与中央生图 MCP 均已退役，不是恢复目标。
- 本次生产复查没有制造订单/支付/模型负载或新增控制面；Oracle 只执行了有备份、可回滚的同版本前端工件发布和充值菜单最小写入。
- 云猫商家资料已按链动小铺可见资料补齐，七档商品已销售中并导入 707/707 张库存（每档 101 张），公开页七档均显示“库存充足”；默认手续费承担方已保存为买家承担。
- 左侧充值入口已统一命名为“链动小铺”和“云猫寄售”；云猫自配支付功能已开通但易支付支付宝/微信均保持关闭，当前没有收款账号。新增账号需要易支付网关、PID、密钥，实际结算主体由易支付服务商绑定的支付宝/微信商户决定；本轮未提交支付资料、未开启通道、未产生费用或订单。
- 2026-08-16 最终回读发现 Oracle 管理脚本没有随仓库最后一次标签变更同步，导致旧标签仍在数据库中。仅同步已复核的 5 处标签参数化差异，使用远端脚本 prestate、原子替换、失败恢复旧脚本，再复用 `recharge-center` 的数据库/页面备份和失败回滚；两项新标签各 1 条、旧标签 0 条，服务和公网探针继续通过。
- 本机严格健康已恢复 `release_ready=true`；scheduler 与 daily-backup 的 LaunchAgent 计数器仍为陈旧的 `runs=0/(never exited)`，但各自的真实成功产物已通过只读审计，不代表核心服务故障。

## 1. 已通过的真实生产检查

### 本机 Mac

- `scripts/auto_health_check.sh --json --strict` 返回 `ok=true`、`release_ready=true`、`bad=0`、`warn=0`；核心服务、备份新鲜度、ClawBot API、Gateway API、公网站点和上游监控均通过。scheduler 的生产周期产物、标准输出与投递结果已由既有只读审计验证；daily-backup 的归档、就绪标记与只读恢复演练已验证。两者的 launchctl 计数器仍陈旧，但不再被误判为失败。
- `openclaw health --json` 返回 `ok=true`、约 17 ms；`openclaw status --deep --json` 网关可达；`openclaw doctor --lint --json` 返回 `ok=true` 且无 findings。
- 当前 OpenClaw 为官方 `2026.7.1-2`；`/Applications/OpenClaw.app` 严格签名校验通过，内部应用版本为 `0.1.1`。本机真实应用窗口可达、核心引擎显示在线，未见致命 UI 错误。
- 没有输入 Token、密码、Cookie 或 MFA；匿名本地浏览器连接因缺少认证不作为通过依据。

### Oracle Singapore、Cloudflare 与备份

- JIYU/Sub2API 运行受管构建 `v0.1.173-jiyu.31894209937`。Sub2API、PostgreSQL、专用 Redis、Apache、更新 timer 和备份 timer 均为 active；systemd 失败单元为 0，Apache 返回 `Syntax OK`。
- 内网和公网 `/health` 返回 200；未授权 `/v1/models` 返回 401；未授权 Responses/WebSocket 边界返回 401；Sub2API 管理器的 PostgreSQL 预检、内网健康和 WebSocket 代理检查通过。
- `2026-08-16T03:27Z` 的既有 VPS-Config 只读状态曾记录 Oracle Ashburn 根分区可用空间为 23.4%；重复副本再平衡先将其恢复到 28.4%，资产所有者随后精确批准 `7 daily + 4 weekly + 3 monthly` GFS。VPS-Config 于 `2026-08-16T05:44:20Z` 完成三镜像/恢复保护下的事务，保留 19 个、删除 39 个唯一备份族并回收 `12,861,810,280` bytes；`05:44:36Z` 定点回读确认 Oracle Ashburn 36.1%、HostDare 45.7%，两节点 0 问题、0 failed unit。
- 当前 `payment_orders=0`、近 24 小时/7 天 `usage_logs=0`、active channels=9、active accounts=16；9 个启用监控的最新年龄约 0–5 分钟。
- 受管费率按当前账号倍率加既有 `+0.05` 合同回读为 7 个符合条件 group，7 个正确、0 个漂移。生产事实优先于旧基线中曾出现的 11/11 数字。
- 备份目录有 1608 个文件、38 个 checksum 文件；38/38 checksum 校验通过。备份 timer active；本轮新增本地归档 `openeverything-20260816-114058.tgz`，checksum、路径、manifest、SQLite 恢复演练全部通过；清单 49 项中 4 个当前不存在的运行目录被如实标记，离机加密介质仍未配置。

### 真实 Chrome 登录态与窄屏回读

- 已接管现有登录态只读打开仪表盘和渠道状态页，页面可达并已恢复到原仪表盘位置。
- 渠道状态页总体为 `DEGRADED`，可见 2 个正常、1 个降级、3 个错误结果；页面自身提示探针仅供参考。该现象与服务端真实上游错误结果一致，不能用总健康接口掩盖。
- 浏览器已有的非 JIYU 当前主域名标签页未作为本项目发布依据，也未修改；JIYU 当前主域名在既有会话内回读到“链动小铺”和“云猫寄售”两项菜单，旧标签未出现。两个嵌入页均可见，iframe 不携带 query/hash 会话参数。
- 在真实 Chrome 会话临时设为 `390x844` 后，两页均无横向溢出、iframe 可见且落在视口内；已恢复默认窗口尺寸。这是窄屏覆盖，不替代实体手机验收。
- 未读取 Cookie、Local Storage、密码或会话存储，没有提交表单、创建 Key、刷新配置或发送业务请求。
- 云猫寄售真实登录态复查：商家后台可达；店铺昵称、公告、官网按钮和已有联系方式已同步，默认手续费承担方为“买家承担”；`¥1/10/50/100/300/500/1000` 七档 `JIYU AI 余额兑换码` 均为“销售中”，每档后台回读 101 张库存。
- 云猫“支付方式 → 自配支付渠道”真实只读回读：自配能力显示“已开通”；“易支付支付宝”和“易支付微信”均显示“已关闭”，两者均无收款账号；新增账号表单只要求账号别名、易支付网关、易支付 PID、易支付密钥，微信/支付宝通道分别配置。
- 云猫原生跨站搬家任务真实回读为“成功/迁移完成”，`分类 1/1 商品 7/7 库存 707/707`；未读取、打印或提交密码、Cookie、Token 或卡密正文。

## 2. 发现并已修复的问题

- 删除 5 个已确认无当前调用者、可由 Git 恢复且会制造误操作风险的遗留入口：packages/clawbot/scripts/setup_unattended_mode.sh、scripts/sub2api_configure_jiyu_channels.mjs、packages/clawbot/scripts/heartbeat_sender.sh、apps/openclaw/tools/memory-dispatch.mjs、packages/clawbot/scripts/deploy_vps.sh。
- 心跳脚本由当前 `tools/launchagents/ai.openclaw.heartbeat-sender.plist` 内联逻辑取代；无人值守脚本引用的旧 `com.openclaw.*` plist 已不存在；JIYU 一次性迁移脚本只剩历史文档引用。
- 保留了 `start_clawbot.sh`、`start.sh`、`start_omega.sh`、IBKR 运维脚本、支付/订单/授权、数据库迁移、备份恢复、安全和关键浏览器测试；未删除 Tauri 生成 Schema 或 `jiyu_xianyu_redeem_reservations.sql`。
- 修正现有 Intel LaunchAgent 只读审计：投递状态成功且 `eligible/sent/failed` 均为 0 时，明确记录为“无收件人但投递成功”，不伪造 Telegram 发送成功；严格健康检查现在复用该审计，并对每日备份复用已有归档与恢复演练产物。
- 充值中心部署入口已补齐写入保护：每次执行先生成 `recharge-<UTC timestamp>` prestate/一致性备份，记录当前菜单和页面存在性，失败时恢复数据库、CSP、页面并重启复核健康。
- 首次用旧生产二进制启用 `充值中心2` 时，真实 iframe 暴露了站内用户查询参数；已立即保存 `recharge2-menu-disable-20260815T155317Z` prestate 并移除菜单。随后以同版本 JIYU 前端补丁工件发布，重新启用菜单后浏览器确认 iframe 只使用云猫公开 URL、无查询或哈希参数，未留下用户可见的旧入口。
- 2026-08-16 修复远端管理脚本滞后：远端与仓库 HEAD 的 diff 仅为 5 处充值菜单标签参数化。新脚本经语法和校验和检查后原子替换，保留带时间戳的旧脚本备份；`recharge-center` 再次生成自己的 prestate/一致性备份并完成 post-check。数据库回读确认两个新标签各 1 条、两个旧标签均不存在，两个自定义页继续返回 200。
- GitHub Actions 运行 `31894209937`（分支 `codex/production-final-audit-20260815`）构建门禁全部通过并发布可校验的 Linux ARM64 工件；定时任务对未审阅的官方版本已安全跳过，手动指定仍明确失败。

## 3. 未修复问题及原因

- 两条生图上游仍受权限拒绝或目标模型缺失阻断；未制造付费探针，也未恢复中央 MCP。
- 上游渠道页仍有错误/降级模型结果，需供应商恢复、限流解除或运营决定停用对应报价；本项目没有可安全替代的生产修复。
- 当前没有发现云猫商品或充值中心2的生产阻断：商品、库存、买家手续费、菜单、CSP、页面和公开店铺均已回读通过；后续只需观察真实订单，不制造合成订单。
- 云猫自配支付尚未开通：缺少易支付服务商商户账号及其绑定的支付宝/微信结算主体；需要用户完成服务商开户、资质审核、商户密钥配置并确认云猫客服的接入要求。本项目不代填或提交支付凭据。
- 本地公网观测曾出现间歇性 `000`，远端 canonical 探针健康；未形成双观测点故障证据，不修改 DNS、路由或 Cloudflare。
- LaunchAgent 的 `runs=0/(never exited)` 计数器仍未被 macOS 回写；当前不 kickstart、不重载、不修改生产调度，继续以真实产物和只读审计为事实依据。
- 实体手机未连接；App 仍为内部 ad-hoc 签名。对外分发需要 Apple Developer ID、公证材料和单独验收。
- VPS-Config 现有主机探针不检查 JIYU 公网业务；该控制面在本项目边界外，本轮未新增 watcher。

## 4. 官方版本核对

- OpenClaw 最新发布为 `v2026.7.1-2`，与生产一致，不升级。
- Sub2API 最新发布为 `v0.1.177`（2026-08-15）。官方改动包含分组用量日汇总、Codex remote compaction v2 适配、Grok 计费/媒体模型修复和账号刷新偏好修复，同时改变未显式配置的 Codex OAuth 指纹收敛默认行为。生产仍为带 JIYU 补丁的 `v0.1.173`；未完成补丁重放和行为审阅前不升级。
- new-api 最新发布为 `v1.0.0-rc.24`，本地子模块没有生产调用者，不升级。
- cloudflared 最新发布为 `2026.8.2`，当前路径使用 Apache + Cloudflare origin service，不做替换。
- 参考的官方能力包括 OpenClaw `health`/`doctor`/`backup`、Sub2API 原生更新/备份、Cloudflare Health Checks 与 failover steering；未增加重复控制面。

### 优化空间审计排序

按“稳定性 → 速度 → 安全性 → 用户体验 → 维护成本 → 资源利用率”排序；收益是相对当前生产状态的估算，不把本地测试数量当作生产收益。

- 稳定性：P1 保持现有 VPS-Config 能力，补 JIYU `/health` 外部失败通知（目标发现时间 1–5 分钟），并处理持续失败的上游报价；预计减少故障暴露窗口 1–5 分钟，维护成本为一次接线和后续供应商处置，不新增本仓常驻 watcher。
- 速度：当前 OpenClaw Gateway 真实连接约 37 ms、公网根页约 0.47 秒，未发现可由本仓修复的瓶颈；Cloudflare 官方健康检查/steering 已覆盖现有能力，继续调路由预计收益低于 10%，暂不改动。
- 安全性：P2 仅在确需 Sub2API `v0.1.177` 的 remote compaction v2、计费或刷新修复时重放 JIYU 补丁；预计获得对应上游修复，成本 2–4 小时并承担补丁/回滚风险，当前不自动升级。
- 用户体验：菜单漂移已修复；P1 接入实体手机复用关键浏览器流程，预计补齐唯一设备盲区，耗时约 10 分钟、0 新费用；Chrome 窄屏回读已证明布局风险而非实体兼容性。
- 维护成本：P2 只做 OpenClaw 原生 backup/doctor 与现有包装脚本等价性审计，只有能删除维护入口时才迁移；预期减少重复脚本，否则收益为 0。
- 资源利用率：VPS-Config 重复副本去重与所有者批准的 GFS 已完成，累计回收约 19.18 GB；Oracle Ashburn 为 36.1%、HostDare 为 45.7%，当前没有阈值告警。策略由 VPS-Config 既有 `backup-retention` 维护，默认只读且未来执行仍需最新摘要精确批准；本仓不增加清理器。

## 5. P0/P1/P2 优化

### P0

- 当前无 P0 生产阻断；已完成的同版本发布不需要继续升级或回滚。

### P1

- 在既有 VPS-Config 能力内加入 JIYU `/health` 外部失败通知，目标发现时间 1–5 分钟；不在本仓新增 watcher。
- 对持续失败的上游报价做供应商侧修复、停售或重新定价，避免把不可用模型提供给用户。
- 供应商确认恢复后只做一次最低成本真实图片探针，验证异步终态、MIME、对象期限和清理。
- 连接实体手机复用现有关键浏览器流程，补齐移动端唯一设备盲区；预期 10 分钟、0 新成本，当前 Chrome 窄屏回读仅降低布局风险。

### P2

- 仅在需要 `v0.1.177` 的 Codex remote compaction v2、计费或账号刷新修复时，才评估重放 JIYU 补丁；预计 2–4 小时，需要完整 prestate/备份/回滚，收益取决于真实 Codex 会话和 Grok 使用量，当前不做投机升级。
- 云猫充值中心2已完成部署；继续投入只保留真实订单/退款探针和供应商故障处理，不再增加第二套库存或支付控制面。
- 对 OpenClaw 原生 backup/doctor 与本地包装脚本做等价性审计，只有能删除维护面时才迁移。
- 本轮在确认无 Cargo/Tauri/npm/Playwright 构建进程后，已回收 `target`、桌面 `node_modules`、npm runtime 构建依赖、`output` 和 `.playwright-cli`，释放约 `4,515,044 KiB`（约 4.3 GiB）；不会自动删除运行中的 `.venv312`、浏览器 profile 或 `.openclaw`。
- 本轮额外将已退役图像 MCP 的可再生 `node_modules`（24 MB）和 pytest 缓存（244 KB）移入系统废纸篓；没有删除受跟踪源码、凭证、浏览器 profile 或运行虚拟环境。
- 对外分发、公证、new-api 子模块和 Cloudflare 代理替换暂不处理。

## 6. 已无继续优化价值

- 不恢复闲鱼、Frist-API、CC 中转、自动发货、中央生图 MCP 或第二订单事实源。
- 不新增 Gate、证据编译器、计划 Schema、一次性测试包、常驻 AI 管理面、第二启停控制面、第三套备份或合成负载。
- 不按供应商监控页逐项镜像本站监控，不为清零探针错误而改 DNS、路由或健康语义。
- 不做没有明确安全、稳定或用户收益的版本升级、迁移、私有 glib 分叉或硬编码重构。

## 7. 新会话交接提示词

- 用户只需在需要时处理 MFA、账户恢复、续费/付款、所有权转移、Apple Developer ID、公证、离机加密备份介质、供应商图片权限和实体手机；本轮没有触发这些人工接管项。
- 本机没有硬件瓶颈；构建/测试缓存已回收，`.venv312`、浏览器 profile、`.openclaw` 和凭证相关运行态目录继续保留。VPS-Config 已完成批准的 GFS，Oracle Ashburn 为 36.1%、HostDare 为 45.7%，再次 dry-run 为 0 删除候选；不在本仓添加清理器。
- 云猫迁移、七档上架、707/707 库存导入、买家承担手续费和 Oracle `充值中心2` 已完成；后续只需在真实业务发生时人工处理平台 MFA、验证码、退款争议或账户恢复。

## 8. 本轮收口验证

- Intel LaunchAgent 审计回归测试通过，包含“计数器陈旧”和“无符合条件订阅者但投递成功”两条路径；备份与自动运维脚本测试 19/19 通过。
- `bash -n scripts/sub2api_oracle_manage.sh scripts/auto_health_check.sh scripts/manage_backup_launchagent.sh`、ShellCheck、运维合同测试和 `git diff --check` 通过；本轮没有 kickstart、账户密码提交或合成业务负载。
- 生产完成结论来自真实 LaunchAgent 产物、备份归档/恢复演练、健康端点和真实登录态页面；本地测试仅作为代码回归证据。
- 本地减负后再次运行严格健康、`openclaw health` 和 `openclaw doctor --lint` 均通过；清理仅涉及可再生、被 Git 忽略的构建/测试产物。
- 本轮新增真实验证为 GitHub 工件 SHA/大小/架构匹配、Oracle 发布后服务健康、菜单2存在、两个自定义页面 HTTP 200、CSP 中链动/云猫各出现一次且无其他云猫指令、公开页 7 档库存充足、浏览器 iframe 无查询参数且与链动页整屏尺寸一致。
- 充值中心写入生成了带时间戳的数据库/配置/页面 prestate 和日备份；发布前二进制备份位于 `/var/backups/sub2api/jiyu-v0.1.173-jiyu.31894209937-20260815T161855Z`，菜单安全回滚 prestate 仍可恢复。
- 最终回读：远端管理脚本与仓库 HEAD 一致；菜单新标签均存在且旧标签均不存在；两个充值页 HTTP 200，浏览器确认两个 iframe 无用户参数且窄屏无横向溢出；Mac 实机 App 窗口、签名和核心引擎均正常。VPS-Config 后续 GFS、恢复探针和两节点定点回读确认备份磁盘阈值告警已闭环。
- 本轮重新执行 `make docs-check`、`make sub2api-check`、`make shellcheck`、`make gitleaks-check` 与 `git diff --check` 均通过；重新回读 Sub2API 生产状态和公网探针，结果与上方基线一致。生产结论仍以真实运行时和备份恢复演练为准。

```text
接手 OpenEverything 生产维护。生产运行时是唯一事实，仓库只用于必要维护、恢复和异地备份。范围仅限本机 Mac OpenClaw/ClawBot 与 Oracle Singapore JIYU/Sub2API；其他项目只做只读边界确认。

当前 JIYU 生产版本为 v0.1.173-jiyu.31894209937。账号是 V1 渠道监控和费率同步的唯一运行时来源：受管文本 group 按账号倍率加既有 +0.05 合同以当前 group 值 CAS 更新；不得恢复旧的“旧倍率恰好匹配才更新”条件。若已绑定的 channel/group/account 任一停用，监控应自动禁用并取消调度；只有完全独立的监控可以回退自己的快照。

生产回读：7 个符合条件的受管文本 group 正确、漂移为 0；9 个启用监控新鲜；渠道页仍有真实上游错误/降级结果；两条生图上游仍受权限/模型阻断。供应商确认恢复后只做一次最低成本真图验收，不恢复中央 MCP。

本机严格健康当前返回 `ok=true/release_ready=true`；scheduler/daily-backup 的 `runs=0/(never exited)` 是陈旧计数器，但真实调度产物、备份归档与恢复演练已通过只读审计，不要 kickstart 或重载任务来追求计数器变化。

不得输出密码、Token、Cookie、私钥、订阅地址或账户标识。不得制造订单、支付、Telegram 外发、模型负载或压力测试。每个生产写入必须有最新 prestate、可恢复备份、最小变更、失败回滚和真实业务回读。

云猫充值中心2：七档商品均为“销售中”，每档 101 张库存，迁移日志为 7/7 商品、707/707 库存，默认手续费由买家承担。Oracle 菜单和 CSP 已用 `sub2api_oracle_manage.sh recharge-center` 部署并回读；iframe 必须保持公开 URL 且不得拼接用户 ID、Token、Cookie 或其他会话参数，失败立即回滚。

2026-08-16 最终复查已发现并修复一次远端管理脚本滞后：远端脚本现在与仓库 HEAD 一致，菜单为“链动小铺”和“云猫寄售”，旧标签不存在；原子脚本替换和菜单写入都留有独立、可恢复的时间戳 prestate。不要手工 SQL 修改菜单或复制脚本片段，继续只用 `recharge-center`。

最新 Sub2API 为 v0.1.177，尚未重放 JIYU 补丁；其 Codex remote compaction v2/计费/刷新修复只有在真实使用触发时再评估。VPS-Config 已完成资产所有者批准的 `7 daily + 4 weekly + 3 monthly` GFS，保留 19 个唯一备份族并回收约 12.86 GB；删除后 Oracle Ashburn 为 36.1%、HostDare 为 45.7%，恢复探针和零候选 dry-run 通过。禁止在本仓新增清理器或直接删除远端备份。

闲鱼、卖家桥、自动交付、Frist-API、CC 中转和中央生图 MCP 已退役，不要恢复。支付、订单、授权、数据库迁移、备份恢复、安全和关键浏览器测试必须保留。当前没有 P0；优先在现有 VPS-Config 能力内补 JIYU /health 外部监控，再处理持续失败的上游报价。
```
