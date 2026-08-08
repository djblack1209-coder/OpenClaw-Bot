# HANDOFF — 会话交接摘要

> 最后更新: 2026-08-09

---

## [2026-08-09 06:00] JIYU 模型广场真实上游对齐与旧兼容入口清理（已验收）

### 本次完成了什么
- 通过 Sub2 原生账号模型同步逐条读取 12 个渠道的上游模型清单；11 条返回成功，1 条生图渠道未返回清单。
- 对 12 条渠道保存“上游清单与已有定价的交集”映射并启用模型限制；价格、账号凭据、分组倍率和上游线路均未改动。
- 兼容补丁新增受限渠道模型广场语义和 `TestSupportedModels` 聚焦门；仓库已移除停用的旧兼容应用、编排与脚本，文档和 CI 统一使用 JIYU AI。CI `31278104138` 已由生产 WebUI 安装并重启生效。

### 未完成的工作
- 软件侧已闭环：生产 VERSION 为 `v0.1.172-jiyu.31278104138`，服务 PID 已更新，模型广场页面与 `/api/v1/model-plaza` 已回读。后续新增或轮换账号仍需重新执行原生上游同步。
- 上游未返回清单的生图渠道保持失败关闭；这不是本轮要处理的上游可用性问题。

### 需要注意的坑
- 新账号或轮换账号后必须先在账号管理点击“同步上游模型”，不要复制另一条渠道的模型列表；同步失败时不要手工填静态模型名。
- 任何生产证据仍禁止密码、API Key、Token、Cookie、TOTP secret、卡密或原始号源。

### 当前系统状态
- 本地补丁已在官方 v0.1.172 干净源码通过 `git apply --check` 和受限模型聚焦测试；生产数据库限制映射已保存。真实页面截图为 `scripts/assets/audit-20260809-model-plaza-after-align.jpg`，页面 Console 警告/错误为 0。
- Telegram 已完成“中文菜单 → 模拟发货格式 → 解析 → dry-run 补号 → 删除临时材料”闭环，输出未回显敏感字段。
- 浏览器后续只保留必要的 JIYU 标签，完成截图后关闭；分支为 `main`，本轮文件待提交。

## [2026-08-09 04:20] JIYU 自营池模板倍率与 Telegram 远程补号

### 本次完成了什么
- 生产管理端创建并刷新回读两个专属空自营池：`JIYU OpenAI Plus 自营号池` 模板 `2.0x`、`JIYU OpenAI Pro 自营号池` 模板 `3.0x`；两池均无账号、无用户绑定、无默认分组和无渠道绑定。
- 本地补号助手读取空池的明确分组模板倍率创建首个账号；已有账号倍率不一致或模板缺失仍暂停人工确认，不回退到 `1x`。
- Telegram Bot 新增 `/jiyu_replenish`、`status`、`stop`、`cancel` 私聊入口；严格解析 JSON/分隔号源，Bot 只返回脱敏任务状态，OAuth 浏览器仍在本机执行。
- 闲鱼既有 `/xianyu start|stop|status` 菜单开关保持可用，继续控制本机 `ai.openclaw.xianyu.plist` 对应的 GUI/客服进程。

### 未完成的工作
- 真实卖家号源导入仍需资产所有者购买后操作；CAPTCHA、短信、实体手机号和风控不会自动绕过。
- Telegram Bot 与本地 Web App 入口共享安全合同；不要同时启动两个补号批次。链动小铺首笔真实购买、自动发货与站内兑换、生图上游异常仍按健康记录处理。

### 需要注意的坑
- Telegram 远程补号只接受 `ALLOWED_USER_IDS` 授权管理员私聊；不要把 JSON 号源发到群聊、普通对话或第三方机器人。
- 所有凭据、Token、Cookie、TOTP secret 和卡密继续禁止输出、截图或写入仓库；关闭 Bot 或批次后进程内敏感引用会清除。

### 当前系统状态
- 聚焦回归 `15 passed`（补号助手 + Telegram 中文菜单入口 + MultiBot 注册），Python 编译、Ruff、docs-check 和 `git diff --check` 通过。
- 工作树待提交本次 Telegram/模板倍率代码及文档，分支保持 `main`；生产管理员浏览器已关闭，不保留浏览器会话。

---

## [2026-08-09 03:15] JIYU 渠道A Claude 与 Responses WebSocket 只读复核交接

### 本次完成了什么
- Oracle 生产只读回读确认渠道A Claude 官 Key 账号 #2 为 `anthropic/apikey`、`active=true`、可调度且恰好绑定 1 个分组；对应渠道 active 且恰好绑定 1 个分组，最近监控状态 `operational`。12 个账号和 12 个 active 渠道均通过单分组合同，排除“空分组”软件故障。
- 复核 Apache `/v1/responses` upgrade 规则在通用根代理之前，公网近期 Codex 请求出现 `101`；Sub2API 全局模式路由开启，四个 OpenAI 文本账号为 `http_bridge=true`，两个生图账号为 `off=false`。
- 复核生产 Responses 用量 6 条、其中 WS 2 条；最新 WS 样本记录缓存读取 1408、首 Token 2482 ms、总时长 2964 ms、站内计费 `$0.087439`。未循环或新增付费请求。
- 复核 Cloudflare 443 收口服务 active，nftables 仅放行 Cloudflare 官方 CIDR、loopback 和 Tailscale；未执行任何防火墙写操作。

### 未完成的工作
- 本轮没有发现需要软件侧修复的空分组或 WS 调度兼容 bug，因此没有执行 WebUI/API 账号分组业务操作，也没有修改定价、注册、支付、数据库或上游线路。
- 链动小铺首笔 ¥1 真实购买、自动发货与站内兑换仍需操作时由老板确认；生图渠道真实 502/401 异常继续保持失败关闭。

### 需要注意的坑
- 生产版本当前为 `v0.1.172-jiyu.31271410817`；后续更新沿用“检查并安装 → 立即重启 → VERSION/stage/health/PID 回读”验收门。
- 账号/分组和 WS mode 的业务配置继续通过 WebUI 管理，不能直接改数据库；任何付费复测只跑单组最小样本，不做循环。

### 当前系统状态
- 本地 `node scripts/cc_zhongzhuan_readiness_audit.mjs --mode=read_only --json` PASS；Oracle manager `status` PASS，Sub2API/Redis/JIYU/Apache active，Responses WebSocket 代理通过；本次 `NRestarts=1` 为 systemd 历史累计重启计数，服务当前 `active/running` 且 `ExecMainStatus=0`，不代表当前故障。
- 工作树仅含本次文档更新，分支保持 `main`；未读取、输出或写入密码、API Key、Token、Cookie、TOTP secret 或卡密。

---

## [2026-08-09 02:18] JIYU WebUI 更新重启根因修复交接

### 本次完成了什么
- 修复 `scripts/sub2api_oracle_manage.sh` systemd 模板注释中的中文弯引号；该字符被 Linux ShellCheck 误判为未闭合引号并报 `SC1111`。仅改为 ASCII 引号，未改变生成的 unit、生产配置或业务逻辑。
- 通过真实 WebUI 点击兼容包更新：CI 构建 `31270629630` 下载和校验成功，接口返回 200；随后点击“立即重启”触发保护性暂存验证。
- 生产实际回读 `/var/lib/sub2api-ops/jiyu-stage-last-result.json` 为 `rolled_back`，原因是 `sub2api.service` 的 `Restart=on-failure` 不会在重启接口正常退出（码 0）后拉起新进程。旧版本和数据库已自动恢复，公网 `/health` 重新 200。
- 已将 `scripts/sub2api_oracle_manage.sh` 和 Oracle 生产 unit 改为 `Restart=always`；受控重启确认 PID `1288563→1291998`，`127.0.0.1:18080/health` 通过。
- 重新触发 CI `31271410817` 后，真实 WebUI“检查并安装→立即重启”成功应用，生产 VERSION 回读 `v0.1.172-jiyu.31271410817`，stage 结果 `applied`，健康 200。
- 更新后移动端创建密钥页 `390×844` 回读 `body/documentElement.scrollWidth=390`，证据为 `scripts/assets/audit-20260809-create-key-mobile-after-update.jpg`。

### 未完成的工作
- WebUI 更新链路本轮已闭环；后续同上游修订沿用“检查并安装→立即重启→版本回读”验收门即可。
- 链动小铺实际购买、卖家 2FA/CAPTCHA 人工挑战和第三方店铺移动布局仍按 HI-987/HI-1012/HI-1016 处理。

### 需要注意的坑
- 任何新构建都先观察 stage result、运行版本、PID 和 `/health`，避免把自动回滚误判成成功。
- 所有证据继续禁止密码、API Key、Token、Cookie、TOTP secret、卡密和个人邮箱；浏览器只保留充值中心主标签。

### 当前系统状态
- 分支只有 `main`，兼容补丁、文档与截图已推送；本地源码已更新为 `Restart=always`，生产 unit 已同步。ShellCheck `SC1111` 注释字符修复已由 OpenClaw CI `31272391317` 的 `security-gates` 确认回绿。
- CI `31271410817` 工件已落地；生产新版本健康，WebUI 更新链路已完成真实验收。

## [2026-08-09 01:54] JIYU 充值移动端与补号/闲鱼审计交接

### 本次完成了什么
- 真实 Chrome 审计确认充值中心继续固定嵌入公开整店，`1440×1000` 与 `390×844` 下外层均无白屏；移动 iframe 位于顶栏下 `x=0,y=64,w=390,h=780`。链动店铺的内部导航和商品卡仍不是响应式布局，已单列为第三方限制。
- 复核 API 密钥页存在 Claude 与 ChatGPT 两个正确端点，创建密钥弹窗默认勾选 CC Switch 导入，移动端弹窗本身无截断；文档下载卡尺寸一致，渠道状态按渠道A后渠道B顺序显示。
- 官方 Sub2API 只支持已生成 token/auth 凭据，不支持卖家 `邮箱----密码----totp_secret` 原文；本地 `make jiyu-sub2-replenish` 已承担严格解析、Plus/Pro 识别和本机 PyOTP 2FA。链动参考商品 `9khhu8` 当前显示未上架，无法读取其历史 2FA 说明。
- 闲鱼重型助手改为部分替换结论：优先比较 `GuDong2003/xianyu-auto-reply-fix`，但 OpenClaw 仍是库存、发货、补救和严格门真值；没有部署或复制第三方 AGPL 源码。
- 系统设置已把登录/注册副标题改为 `JIYU AI API 服务`，保存后重载回读一致。API 端点浮层窄屏横向溢出补丁已通过官方 `v0.1.172` 干净源码应用验证。

### 未完成的工作
- 当时兼容补丁尚未推送、构建和通过 WebUI 受管安装；随后已发布 `v0.1.172-jiyu.31271410817`，并在 `390×844` 重新核验 API 密钥页无横向滚动。
- 链动小铺目前未提供可验证的移动专用入口；不能跨域改写其内部 CSS。首笔真实 ¥1 付款、自动发货与兑换到账仍需操作时确认。

### 需要注意的坑
- 所有截图、日志、文档和提交均不得包含密码、API Key、Token、Cookie、TOTP secret、卡密或个人联系邮箱；系统设置总览截图因含个人邮箱不作为最终证据。
- 不得让第三方闲鱼助手在异常时覆盖 OpenClaw 的库存扣减或补救状态，也不得绕过 CAPTCHA、短信、实体手机号或风控。

### 当前系统状态
- 当前工作树含兼容补丁、文档与审计截图；已完成 `git apply --check`、实际应用补丁和 `node --test scripts/sub2api_ops_scripts.test.mjs`（4/4）。
- 当时生产运行版本为 `v0.1.172-jiyu.31265860057`；充值页本轮网络错误与运行时异常为 0。系统设置首次加载偏慢且浏览器保留 CSP report-only 噪声，未假定为已解决。
