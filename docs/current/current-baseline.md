# JIYU AI 当前生产基线

> 更新时间：2026-08-15（Asia/Singapore）。生产运行时是唯一事实；仓库仅用于必要维护、恢复和异地备份。`docs/current/` 只保留本文件。

## 范围与结论

- 范围仅限本机 Mac OpenClaw/ClawBot 与 Oracle Singapore JIYU/Sub2API。中国 origin、腾讯旧备机和其他项目未修改。
- 闲鱼商品已全部下架且无待处理订单；闲鱼客服、卖家桥、自动交付、Frist-API、CC 中转与中央生图 MCP 均已退役，不是恢复目标。
- 本次生产复查只读完成，没有写入生产、升级版本、制造订单/支付/模型负载或新增控制面。
- 本机严格健康已恢复 `release_ready=true`；scheduler 与 daily-backup 的 LaunchAgent 计数器仍为陈旧的 `runs=0/(never exited)`，但各自的真实成功产物已通过只读审计，不代表核心服务故障。

## 1. 已通过的真实生产检查

### 本机 Mac

- `scripts/auto_health_check.sh --json --strict` 返回 `ok=true`、`release_ready=true`、`bad=0`、`warn=0`；核心服务、备份新鲜度、ClawBot API、Gateway API、公网站点和上游监控均通过。scheduler 的生产周期产物、标准输出与投递结果已由既有只读审计验证；daily-backup 的归档、就绪标记与只读恢复演练已验证。两者的 launchctl 计数器仍陈旧，但不再被误判为失败。
- `openclaw health --json` 返回 `ok=true`、约 17 ms；`openclaw status --deep --json` 网关可达；`openclaw doctor --lint --json` 返回 `ok=true` 且无 findings。
- 当前 OpenClaw 为官方 `2026.7.1-2`；`/Applications/OpenClaw.app` 严格签名校验通过，内部应用版本为 `0.1.1`。
- 没有输入 Token、密码、Cookie 或 MFA；匿名本地浏览器连接因缺少认证不作为通过依据。

### Oracle Singapore、Cloudflare 与备份

- JIYU/Sub2API 运行受管构建 `v0.1.173-jiyu.31551931801`。Sub2API、PostgreSQL、专用 Redis、Apache、更新 timer 和备份 timer 均为 active；systemd 失败单元为 0，Apache 返回 `Syntax OK`。
- 内网和公网 `/health` 返回 200；未授权 `/v1/models` 返回 401；未授权 Responses/WebSocket 边界返回 401；Sub2API 管理器的 PostgreSQL 预检、内网健康和 WebSocket 代理检查通过。
- 当前 `payment_orders=0`、近 24 小时/7 天 `usage_logs=0`、active channels=9、active accounts=16；9 个启用监控的最新年龄约 0–5 分钟。
- 受管费率按当前账号倍率加既有 `+0.05` 合同回读为 7 个符合条件 group，7 个正确、0 个漂移。生产事实优先于旧基线中曾出现的 11/11 数字。
- 备份目录有 1608 个文件、38 个 checksum 文件；38/38 checksum 校验通过。备份 timer active；现有本地备份新鲜，离机加密介质仍未配置。

### 真实 Chrome 登录态

- 已接管现有登录态只读打开仪表盘和渠道状态页，页面可达并已恢复到原仪表盘位置。
- 渠道状态页总体为 `DEGRADED`，可见 2 个正常、1 个降级、3 个错误结果；页面自身提示探针仅供参考。该现象与服务端真实上游错误结果一致，不能用总健康接口掩盖。
- 未读取 Cookie、Local Storage、密码或会话存储，没有提交表单、创建 Key、刷新配置或发送业务请求。

## 2. 发现并已修复的问题

- 删除 5 个已确认无当前调用者、可由 Git 恢复且会制造误操作风险的遗留入口：packages/clawbot/scripts/setup_unattended_mode.sh、scripts/sub2api_configure_jiyu_channels.mjs、packages/clawbot/scripts/heartbeat_sender.sh、apps/openclaw/tools/memory-dispatch.mjs、packages/clawbot/scripts/deploy_vps.sh。
- 心跳脚本由当前 `tools/launchagents/ai.openclaw.heartbeat-sender.plist` 内联逻辑取代；无人值守脚本引用的旧 `com.openclaw.*` plist 已不存在；JIYU 一次性迁移脚本只剩历史文档引用。
- 保留了 `start_clawbot.sh`、`start.sh`、`start_omega.sh`、IBKR 运维脚本、支付/订单/授权、数据库迁移、备份恢复、安全和关键浏览器测试；未删除 Tauri 生成 Schema 或 `jiyu_xianyu_redeem_reservations.sql`。
- 修正现有 Intel LaunchAgent 只读审计：投递状态成功且 `eligible/sent/failed` 均为 0 时，明确记录为“无收件人但投递成功”，不伪造 Telegram 发送成功；严格健康检查现在复用该审计，并对每日备份复用已有归档与恢复演练产物。

## 3. 未修复问题及原因

- 两条生图上游仍受权限拒绝或目标模型缺失阻断；未制造付费探针，也未恢复中央 MCP。
- 真实渠道页仍有错误/降级模型结果，需供应商恢复、限流解除或运营决定停用对应报价；本项目没有可安全替代的生产修复。
- 本地公网观测曾出现间歇性 `000`，远端 canonical 探针健康；未形成双观测点故障证据，不修改 DNS、路由或 Cloudflare。
- LaunchAgent 的 `runs=0/(never exited)` 计数器仍未被 macOS 回写；当前不 kickstart、不重载、不修改生产调度，继续以真实产物和只读审计为事实依据。
- 实体手机未连接；App 仍为内部 ad-hoc 签名。对外分发需要 Apple Developer ID、公证材料和单独验收。
- VPS-Config 现有主机探针不检查 JIYU 公网业务；该控制面在本项目边界外，本轮未新增 watcher。

## 4. 官方版本核对

- OpenClaw 最新发布为 `v2026.7.1-2`，与生产一致，不升级。
- Sub2API 最新发布为 `v0.1.176`，生产为带 JIYU 补丁的 `v0.1.173`；没有当前相关安全/稳定收益和完整回滚窗口，不升级。
- new-api 最新发布为 `v1.0.0-rc.24`，本地子模块没有生产调用者，不升级。
- cloudflared 最新发布为 `2026.8.2`，当前路径使用 Apache + Cloudflare origin service，不做替换。
- 参考的官方能力包括 OpenClaw `health`/`doctor`/`backup`、Sub2API 原生更新/备份、Cloudflare Health Checks 与 failover steering；未增加重复控制面。

## 5. P0/P1/P2 优化

### P0

- 当前无生产阻断，不执行生产写入或回滚。

### P1

- 在既有 VPS-Config 能力内加入 JIYU `/health` 外部失败通知，目标发现时间 1–5 分钟；不在本仓新增 watcher。
- 对持续失败的上游报价做供应商侧修复、停售或重新定价，避免把不可用模型提供给用户。
- 供应商确认恢复后只做一次最低成本真实图片探针，验证异步终态、MIME、对象期限和清理。
- 连接实体手机复用现有关键浏览器流程，补齐移动端唯一设备盲区。

### P2

- 只有官方 `v0.1.176` 含当前相关安全或稳定修复时，才评估重放 JIYU 补丁；预计 2–4 小时并需要完整 prestate/备份/回滚。
- 对 OpenClaw 原生 backup/doctor 与本地包装脚本做等价性审计，只有能删除维护面时才迁移。
- 本轮在确认无 Cargo/Tauri/npm/Playwright 构建进程后，已回收 `target`、桌面 `node_modules`、npm runtime 构建依赖、`output` 和 `.playwright-cli`，释放约 `4,515,044 KiB`（约 4.3 GiB）；不会自动删除运行中的 `.venv312`、浏览器 profile 或 `.openclaw`。
- 对外分发、公证、new-api 子模块和 Cloudflare 代理替换暂不处理。

## 6. 已无继续优化价值

- 不恢复闲鱼、Frist-API、CC 中转、自动发货、中央生图 MCP 或第二订单事实源。
- 不新增 Gate、证据编译器、计划 Schema、一次性测试包、常驻 AI 管理面、第二启停控制面、第三套备份或合成负载。
- 不按供应商监控页逐项镜像本站监控，不为清零探针错误而改 DNS、路由或健康语义。
- 不做没有明确安全、稳定或用户收益的版本升级、迁移、私有 glib 分叉或硬编码重构。

## 7. 新会话交接提示词

- 用户只需在需要时处理 MFA、账户恢复、续费/付款、所有权转移、Apple Developer ID、公证、离机加密备份介质、供应商图片权限和实体手机。
- 当前没有硬件瓶颈；构建/测试缓存已回收，`.venv312`、浏览器 profile、`.openclaw` 和凭证相关运行态目录继续保留。

## 8. 本轮收口验证

- Intel LaunchAgent 审计回归测试通过，包含“计数器陈旧”和“无符合条件订阅者但投递成功”两条路径；备份与自动运维脚本测试 19/19 通过。
- `bash -n scripts/auto_health_check.sh scripts/manage_backup_launchagent.sh`、`git diff --check` 通过；本轮仍未执行生产写入、kickstart、备份安装或账户操作。
- 生产完成结论来自真实 LaunchAgent 产物、备份归档/恢复演练、健康端点和真实登录态页面；本地测试仅作为代码回归证据。
- 本地减负后再次运行严格健康、`openclaw health` 和 `openclaw doctor --lint` 均通过；清理仅涉及可再生、被 Git 忽略的构建/测试产物。

```text
接手 OpenEverything 生产维护。生产运行时是唯一事实，仓库只用于必要维护、恢复和异地备份。范围仅限本机 Mac OpenClaw/ClawBot 与 Oracle Singapore JIYU/Sub2API；其他项目只做只读边界确认。

当前 JIYU 生产版本为 v0.1.173-jiyu.31551931801。账号是 V1 渠道监控和费率同步的唯一运行时来源：受管文本 group 按账号倍率加既有 +0.05 合同以当前 group 值 CAS 更新；不得恢复旧的“旧倍率恰好匹配才更新”条件。若已绑定的 channel/group/account 任一停用，监控应自动禁用并取消调度；只有完全独立的监控可以回退自己的快照。

生产回读：7 个符合条件的受管文本 group 正确、漂移为 0；9 个启用监控新鲜；渠道页仍有真实上游错误/降级结果；两条生图上游仍受权限/模型阻断。供应商确认恢复后只做一次最低成本真图验收，不恢复中央 MCP。

本机严格健康当前返回 `ok=true/release_ready=true`；scheduler/daily-backup 的 `runs=0/(never exited)` 是陈旧计数器，但真实调度产物、备份归档与恢复演练已通过只读审计，不要 kickstart 或重载任务来追求计数器变化。

不得输出密码、Token、Cookie、私钥、订阅地址或账户标识。不得制造订单、支付、Telegram 外发、模型负载或压力测试。每个生产写入必须有最新 prestate、可恢复备份、最小变更、失败回滚和真实业务回读。

闲鱼、卖家桥、自动交付、Frist-API、CC 中转和中央生图 MCP 已退役，不要恢复。支付、订单、授权、数据库迁移、备份恢复、安全和关键浏览器测试必须保留。当前没有 P0；优先在现有 VPS-Config 能力内补 JIYU /health 外部监控，再处理持续失败的上游报价。
```
