# HANDOFF — 会话交接摘要

> 最后更新: 2026-08-08

---

## [2026-08-08 19:10] JIYU 443、PostgreSQL 与链动保证金交接

### 本次完成了什么
- Oracle 443 已仅允许 Cloudflare 官方 CIDR、loopback 和 Tailscale；应用时保留 5 分钟自动回滚，三个独立外部 VPS 直连源站均超时后才取消。公网 80、SSH、Tailscale 未改，ACME timer active 且最近成功。
- 修复 PostgreSQL 重启风险：Headscale 故障转移脚本不再每两分钟把 `/var/log` 改成 0700；管理器把文件权限、服务和 SQL 预检接到备份、发布与 WebUI 更新路径。手动运行污染源任务后预检仍通过。
- 生产合同复核为 12 个分组、12 个 active 渠道；10 个文本倍率差均为 `0.0500`，10 条文本监控为 300±30 秒且启用，2 条图片监控保持禁用，图片价格为 0.10/0.12 每张。
- 链动小铺七档标题、统一 Logo、详情和兑换步骤已保存；一枚未售临时兑换码已删除并重建，全程未输出或截图明文。

### 未完成的工作
- 链动保证金账户最低要求 ¥100，当前余额 0；库存导入、商品上架、充值中心回填和 ¥1 实单均被平台硬门阻塞。老板需在已保留的钱包页面完成真实充值，最终付款前仍需确认。
- 渠道A Claude Messages、生图 502/401、Turnstile 开放注册前验收继续保持原边界；未改上游线路、未付费探测。

### 需要注意的坑
- 不要直接对 `/var/log` 使用 `install -d -m 700`；会把 postgres 的 named ACL mask 清零。所有 Sub2API 发布前先跑 `postgres-preflight`。
- Cloudflare CIDR 更新必须走 `cloudflare-origin-443`，先保留自动回滚；没有外部直连阻断证据不得执行确认命令。
- 链动商品库存未导入前不能把公开链接放进充值中心；已生成但未售的兑换码不得输出、截图或写入文件。

### 当前系统状态
- `v0.1.172-jiyu.31250692935`、Sub2API、Redis、PostgreSQL、Apache、Cloudflare 443 策略、更新/备份 timer 均 active；内网健康和 Responses WebSocket 代理通过。
- 公网主站首页/健康为 200，旧入口为 301，运营入口未授权为预期 404。源站直连 443 已关闭，80 仍为 ACME 保留。
- 链动浏览器停在保证金钱包页；七档商品仍下架、零库存，充值中心继续只显示预留页。

## [2026-08-08 17:10] JIYU 同版更新入口与 Apache 525 收口

### 本次完成了什么
- JIYU 版本面板改为始终提供“检查并安装”，root 代理按完整构建号判断；同版新修订可安装，已最新安全 no-op。
- 所有 JIYU Apache 配置命令统一为 `configtest → reload → 公网 HTTPS 复核 → 失败 full restart → 再复核`；旧 New-API 回滚保留自己的状态地址。
- 红绿回归已证明旧代码 2 项失败、当前 4/4 通过；生产变更前服务均 active，Apache `Syntax OK`，公网健康连续 5/5 为 200。
- 第一版新修订已发布并更新生产；账号页供货域名链接已清零。真实点击发现 `NoNewPrivileges` 与旧 sudo 调用冲突，现改为 systemd Unix 激活套接字，生产非特权预演已安全返回 `noop`。

### 未完成的工作
- 渠道A Claude、源站 443 收口、生图上游与链动小铺合规仍按既有边界处理，本次未修改。

### 需要注意的坑
- 不要恢复 JIYU 面板对官方 `hasUpdate` 的依赖；同一官方基础版也会有安全/品牌修订。
- 不要直接重复执行 Apache graceful reload；任何配置操作必须走带 full restart 降级和公网 TLS 复核的管理器。

### 当前系统状态
- 生产为 `v0.1.172-jiyu.31250692935`；Sub2API、Redis、Apache 和 `sub2api-jiyu-update.socket` active，独立哈希验证通过，公网健康 5/5 为 200。
- 真实 WebUI 最新版检查为 HTTP 200，PID 不变且无暂存；账号页供货域名链接为 0，Anthropic/OpenAI/Grok 标签保留，最终前后截图已生成。

## [2026-08-08 15:00] JIYU Codex WS 闭环与源站收口取证

### 本次完成了什么
- 启用官方 OpenAI WS 模式路由，四个 OpenAI 文本 API Key 账号经真实管理 WebUI 保存为 `http_bridge`，两个生图账号保持 `off`；部署脚本增加启用与回滚命令。
- 原始 Responses WebSocket 和 Codex `0.147.0` 均真实成功；站内新增第 9、10 条用量，Codex 记录为 `openai_ws_mode=true`，首 Token 2482 ms、服务端总时长 2964 ms。
- 渠道A Claude 账号 #2 根因确认为上游分组拒绝 `/v1/messages`，继续保持 error 和停调度。08-08 的 25 次 503 已全部归因，05:04 后无新增。
- 发现管理端账号名称仍链接真实供货域名；JIYU 补丁已改为普通文本，保持账号编辑和 Anthropic/OpenAI/Grok 协议生态标签不变，等待受管兼容包发布验收。

### 未完成的工作
- 渠道A Claude 需上游恢复 Messages 协议，或经业务确认后临时隐藏公开分组；未擅自改线路或用户可见行为。
- 源站第一阶段只应把 443 收口到 Cloudflare CIDR；80 被同机直连 ACME HTTP-01 使用，需迁移 DNS-01 后再评估。防火墙仍待老板确认。
- 生图 502/401、链动小铺合规、Turnstile 开放注册前验收继续保持原阻塞条件。

### 需要注意的坑
- 永久测试用户和 10 条真实用量不得删除；任何密码、Key、Token、Cookie 不得输出、截图或入仓库。
- Codex CLI 本次总墙钟时间包含本机技能/MCP 初始化，服务端真实处理只有 2964 ms；不要把本机启动噪声误判为 JIYU 转发延迟。
- 不能直接封共享主机 80/443；必须先安排自动回滚并验证三个 HTTPS vhost 和直连 ACME 依赖。

### 当前系统状态
- 生产 `v0.1.172-jiyu.31237926226`；Sub2API、Redis、Apache active，四个文本账号 WS HTTP bridge 生效。
- P0 为 0；Codex WS P1 已关闭，仍未关闭 P1 为 HI-1001、HI-1005。

## [2026-08-08 14:10] JIYU 永久测试用户、真实客户端与边缘防护

### 本次完成了什么
- 创建并保留测试用户 `jiyu-e2e-20260808@245334.xyz`（ID 2）；Claude/OpenAI Key 分离并保存在钥匙串，旧 OpenAI Key 已轮换停用，账号和 8 条真实用量不删除。
- Claude Code 渠道B真实成功；OpenAI Responses 真实成功且缓存输入占比 87.47%。内容预拦截真实 403 且用量不增加。
- Cloudflare Managed WAF/OWASP/L7 DDoS 复核正常；新增 JIYU 主机级注册、验证码、登录和 2FA 边缘限流。Apache Responses WebSocket 由 426 修为 101，并固化为 `responses-websocket` 运维命令。

### 未完成的工作
- 渠道A Claude 官 Key 分组没有可调度账号；需恢复上游账号或临时隐藏公开分组，属于上游线路/业务行为确认。
- Codex 0.147 WebSocket 已到达 Sub2API，但 API Key 账号未被 WS 调度器接受；需补兼容账号或实现安全 HTTP 回退方案后再做真实客户端验收。
- Oracle 80/443 可绕过 Cloudflare；需批准共享主机防火墙 allowlist、带外回滚和 CIDR 自动同步方案。开放注册前还需启用并实测专用 Turnstile。

### 需要注意的坑
- 不得删除 ID 2 测试用户或其历史用量；不得输出、截图、提交任何测试/管理员密码、Key、Token 或 Cookie。
- 直连 curl 成功不等于 Codex 客户端成功；渠道分组显示正常不等于有可调度账号。
- 关键词预拦截不是完整语义防投毒；新增泛化规则前先观察误伤和延迟。

### 当前系统状态
- 生产 `v0.1.172-jiyu.31237926226`；Sub2API、Redis、Apache active，Apache 配置 Syntax OK。
- 注册关闭、邮箱验证开启；站内风险控制和 Cloudflare 主机级限流 active。
- P0 为 0；未关闭 P1 为 HI-1001、HI-1002、HI-1005。

## [2026-08-08 12:07] JIYU 受管更新与渠道排序闭环

### 本次完成了什么
- 生产发布 `v0.1.172-jiyu.31237926226`，首页、渠道状态和健康接口均为 200；WebUI 受管更新使用 `jiyu-latest` 清单、固定 sudo 代理、原子暂存和独立 systemd 回滚验证。
- 首个候选因漏掉 `-tags embed` 导致首页 404，已立即从发布前备份回滚 `.5`；修复工作流并增加嵌入式根页门后才重新部署。
- 用户“渠道状态”真实顺序已复核为 `AAAAABBBBB`，截图保存为 `scripts/assets/audit-jiyu-monitor-after-managed-update-20260808.jpg`；Anthropic/OpenAI/Grok 产品标签保留，只匿名真实供货上游。
- 两套 `gpt-image-2` 分组、账号和渠道保持启用，定价为上游单张价加 `0.05`；两条 300±30 秒监控配置因上游 502/401 保持禁用。

### 未完成的工作
- 渠道A真实生图返回 502，渠道B专用 Key 返回 401；需上游修复凭据/权限后再启用监控、创建站内专用 Key并做一次真实单图验收。
- 当前官方基础版仍为 `v0.1.172`，因此只能验收 WebUI 的“已是最新”路径；下一个官方版本出现后需观察第一次真实点击安装和独立回滚验证结果。
- 链动小铺仍需平台书面合规确认；7 档草稿保持下架/零库存，充值中心不回填不可购买链接。

### 需要注意的坑
- 不得把上游 Key、站内 Key、Cookie 或管理员凭据写入脚本、文档、截图、提交或 CI；MCP 安装状态可以记录布尔值，不能记录 Key。
- 生图付费 POST 禁止自动重试；上游 502/401 未解决前不得伪造正常监控或公开售卖。
- 不要恢复官方裸二进制 update/rollback；WebUI 只允许调用无参数 root 代理并校验 JIYU 清单。Anthropic/OpenAI/Grok 不是供货上游匿名对象，不要移除。

### 当前系统状态
- 生产为 `v0.1.172-jiyu.31237926226`；10 条文本监控运行，2 条生图监控配置保留 300±30 秒但禁用。
- 本机生图 MCP 安装文件与 CC Switch 条目均存在，钥匙串尚无站内生图专用 Key，调用会明确失败关闭。
- OpenClaw CI `31237915263` 和 JIYU CI `31237926226` 均成功；两类 JIYU Release 已明确标记为预发布兼容包，最终文档/截图提交和远端只保留 `main` 仍需收尾。
