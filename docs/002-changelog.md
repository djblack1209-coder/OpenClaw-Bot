# CHANGELOG

> 格式规范: 每条变更必须包含 `领域` + `影响模块` + `关联问题`。文档更新触发规则以 `AGENTS.md` 和 `docs/003-docs-index.md` 为准。
> 领域标签: `backend` | `frontend` | `ai-pool` | `deploy` | `docs` | `infra` | `trading` | `social` | `xianyu`

## 最近更新（2026-08 / 2026-07 / 2026-06 / 2026-05）

## [2026-08-08] JIYU Codex WebSocket 桥接与源站收口取证
> 领域: `backend` | `ai-pool` | `deploy` | `infra` | `docs`
> 影响模块: `Sub2API`, `Codex`, `Responses WebSocket`, `Cloudflare`, `Oracle firewall`
> 关联问题: HI-1000, HI-1001, HI-1002, HI-1005, HI-1006, HI-1007
### 变更内容
- 启用 Sub2API 官方 OpenAI WS 模式路由，通过管理 WebUI 把四个 OpenAI Pro/Plus 文本 API Key 账号设为 `http_bridge`；两个生图账号保持 `off`，未改上游地址、分组、定价或调度关系。
- 管理脚本新增桥接启用和旧模式回滚入口，新安装默认启用模式路由；全局配置、账号配置和生产重载均有独立复核。
- 原始 Responses WebSocket 完成模型输出，真实 Codex `0.147.0` 调用成功且站内记录为 WS 模式；永久测试账号累计 10 条用量，继续保留。
- 明确渠道A Claude 根因为上游分组拒绝 `/v1/messages`，继续保持错误与停调度，不用假绿掩盖。
- 复核源站共享业务后把防火墙方案修正为先收口 443；公网 80 因直连 ACME HTTP-01 暂时保留，待迁移 DNS-01 后再评估。未获确认前未应用防火墙。
- 修复管理端账号列表隐私残留：账号名称不再链接或悬浮显示真实供货 `base_url`；编辑表单和 Anthropic/OpenAI/Grok 协议生态标签继续保留。
- 修复兼容包同版本修订会被已有发布错误跳过：定时任务继续去重，手动修订改为独立不可变 `-r<run_id>` 标签，`jiyu-latest` 只移动清单，不覆盖旧二进制。
### 文件变更
- `.github/workflows/sub2api-jiyu-compat.yml`、`scripts/sub2api_oracle_manage.sh`、`scripts/sub2api-jiyu-v0.1.172.patch`、`scripts/sub2api_ops_scripts.test.mjs` — 不可变同版本修订、OpenAI WS 模式路由启用/回滚、账号列表供货域名隐藏和聚焦合同。
- `docs/002-changelog.md`、`docs/006-registries.md`、`docs/007-operations.md`、`docs/009-health.md`、`docs/012-handoff.md`、`docs/086-release-evidence.md` — 同步真实客户端指标、渠道根因、5xx 归因和源站方案。
### 验证
- 运维脚本合同 `4/4`、Bash 语法和 diff 检查通过；生产 Sub2API active、`/health` 通过，四个文本账号重载后为 `http_bridge=true`，两个生图账号仍为 `off=false`。
- 最小 WS 客户端首输出 4287 ms、总时长 4524 ms、缓存读取 3840/4395；真实 Codex 首 Token 2482 ms、服务端总时长 2964 ms、站内计费 `$0.087439`。
- 08-08 的 25 次源站 503 全部归因于渠道A失败验证或发布重启，05:04 后没有新增；最新 main CI `31243427810` 为 5/5 成功。

## [2026-08-08] JIYU 永久测试用户、真实客户端基线与边缘防护
> 领域: `backend` | `ai-pool` | `deploy` | `infra` | `docs`
> 影响模块: `Sub2API`, `Claude Code`, `Codex`, `Responses API`, `Apache`, `Cloudflare`, `risk control`
> 关联问题: HI-1000, HI-1001, HI-1002, HI-1003, HI-1004, HI-1005, HI-1006
### 变更内容
- 创建并保留永久测试用户，Claude/OpenAI Key 分离并只保存在 macOS 钥匙串；轮换停用可能暴露的旧 OpenAI Key，保留账号和历史用量。
- 使用 Claude Code 和 OpenAI Responses 做最小真实调用，对齐客户端与服务端的 Token、缓存、首 Token/首包、总时长、站内计费和上游实际成本；8 条计费记录留作长期体验基线。
- 修复 Codex 新版 Responses WebSocket 在 Apache 被普通 HTTP 代理截断的 426：专用 upgrade 路由位于根代理之前，握手恢复 101；将幂等修复、配置校验、公网健康和自动回滚固化为 `responses-websocket` 运维命令。
- 开启站内风险控制、会话级阻断和高置信系统提示词窃取预拦截；真实正常请求 200、恶意短语 403 且没有新增用量或计费。
- 复核 Cloudflare 严格 TLS、Managed WAF、OWASP 和 L7 DDoS；新增 JIYU 主机级注册/验证码与登录/2FA 限流，不对整个区域启用可能误伤模型 API 的 Bot Fight Mode。
- 如实登记渠道A空分组、Codex API Key WebSocket 调度和源站公网绕过三个 P1，不擅自调整上游线路、公开分组或共享主机防火墙。
- 真实移动端刷新曾出现一次 `/usage` HTML 503；随后连续 12 次均为 200、业务 API 全部 200，登记为 24 小时 5xx 观察项，不做无法证伪的猜测性修改。
### 文件变更
- `scripts/sub2api_oracle_manage.sh`、`scripts/sub2api_ops_scripts.test.mjs` — Responses WebSocket 代理幂等修复、校验和合同。
- `docs/001-project-map.md`、`docs/006-registries.md`、`docs/007-operations.md`、`docs/009-health.md`、`docs/012-handoff.md`、`docs/086-release-evidence.md` — 同步生产版本、永久账号、真实指标、防护和残余风险。
### 验证
- `make sub2api-check` 聚焦门；Oracle Sub2API/Redis/Apache active，Apache Syntax OK，公网健康接口 200。
- Claude Code 渠道B成功；OpenAI Responses 最近样本缓存读取 3840 / 总输入 4390（87.47%）、首包 5889 ms、总时长 6150 ms、计费 `$0.004850`。
- Cloudflare API 重载确认两条规则 active；恶意短语约 840 ms 返回 403，用量记录仍为 8。

## [2026-08-08] JIYU 生图渠道、受管 WebUI 更新与 CC Switch MCP
> 领域: `frontend` | `backend` | `ai-pool` | `deploy` | `infra` | `docs`
> 影响模块: `Sub2API`, `Images API`, `CC Switch`, `GitHub Actions`, `JIYU update`
> 关联问题: HI-985, HI-994, HI-995, HI-996, HI-998, HI-999
### 变更内容
- 生产建立渠道A/渠道B各一套 `gpt-image-2` 专用分组、账号、渠道和 300±30 秒监控；按老板确认的“上游每张价格绝对增加 `0.05`”执行，渠道A为 `0.05 → 0.10/张`，渠道B高质量组为 `0.07 → 0.12/张`。
- 修复用户“渠道状态”仍混排的问题：管理表和用户卡片改为复用同一比较器，固定渠道A全部产品后接渠道B，生图排在各渠道文本产品之后。
- 真实调用保留失败事实：渠道A返回上游 502，渠道B专用 Key 返回 401；未生成图片、未伪造绿色状态，也未把不可用能力公开为已闭环。
- 新增锁定官方 MCP SDK `1.30.0` 的本机生图服务和一键安装器，替换 CC Switch 两个失效旧条目；Key 只从环境变量或 macOS 钥匙串读取，付费 POST 不自动重试，生产依赖审计为 0。
- 将 WebUI 更新方案实现为 GitHub Actions 兼容包、SHA-256/大小清单、固定域名 root-only 代理和原子暂存；另起 systemd 任务在重启后验证运行哈希与健康状态，失败或 10 分钟未重启会恢复二进制、VERSION 与 PostgreSQL。保留旧版本安全失败关闭，待首个发布包与新后端部署后再启用。
- 合并 Dependabot 的 `h2 4.4.1` 与 `pypdf 6.15.0` 双平台哈希锁更新，并补齐 `hpack 4.2.0` 兼容约束；删除会持续创建旧 New-API 同步分支的定时工作流，冷回滚研究仍可显式运行 `make new-api-sync`，生产继续只使用 Sub2API。
- 修复首轮 CI 发现的三个确定性问题：补丁纳入共享排序器新文件，生图安装器消除 ShellCheck `SC2155`，闲鱼人工预检删除未使用文件读取以消除 Ruff `F841`。
- 将 OpenClaw Manager 的 `js-yaml` / `nanoid` override 提升到 `4.3.1` / `3.3.17`，关闭主 CI 新识别的两个高危公告，不升级桌面框架。
- 修复首个兼容包使用工作流序号造成的版本倒退：改用全仓库单调递增的 GitHub Run ID，拒绝把新构建以低于生产 `.5` 的编号发布。
- 首个生产候选暴露“健康接口正常但首页 404”与代理退出清理报错后，立即从发布前备份回滚 `.5`；兼容包改为 `-tags embed` 嵌入前端并增加嵌入式根页聚焦门，代理清理由全局受控路径负责，避免函数返回后的未绑定变量。
- 增加 `jiyu-latest` 受信任移动清单：未来官方版本变化时 WebUI 始终读取新清单，二进制仍留在按上游版本命名的不可变 Release 中并接受哈希、大小、平台和架构校验；两类 JIYU Release 均标记为预发布兼容包，不占用仓库正式版的 Latest 标记。
- 收紧兼容包聚焦门：更新服务测试显式启用上游 `unit` 构建标签；嵌入式前端只验证标志、`index.html` 和根路由，不再误用依赖上游默认 `logo.png` 的无关旧子用例。
- 生产发布 `v0.1.172-jiyu.31237926226` 并启用 `jiyu-latest` 受管更新；固定 sudo 路径真实返回“当前基础版已最新”，首页、渠道状态和健康接口均为 200。用户渠道卡顺序实测为 `AAAAABBBBB`，新截图保留真实正常/降级/错误状态。
- 明确品牌边界：Anthropic/OpenAI/Grok 作为模型与 API 生态标签保留；只匿名真实供货上游名称及域名，避免把用户需要理解的协议生态误删。
### 文件变更
- `.github/workflows/sub2api-jiyu-compat.yml` — 从官方标签应用 JIYU 补丁、跑聚焦门、构建 ARM64 包并发布校验清单。
- New-API Scheduled Sync workflow — 删除已与 Sub2API 生产架构冲突的自动分支生成任务。
- `scripts/sub2api_jiyu_update_broker.sh`、`scripts/sub2api_oracle_manage.sh`、`scripts/sub2api-jiyu-v0.1.172.patch` — 受管更新代理、暂存/启用命令和 WebUI 后端入口。
- `scripts/jiyu-image-mcp/`、`scripts/install_jiyu_image_mcp.sh` — 锁定依赖的生图 MCP 与 CC Switch/钥匙串安装入口。
- `packages/clawbot/requirements.txt`、`requirements-lock.txt`、`requirements-lock-macos.txt` — `h2`/`pypdf` 安全版本和双平台哈希同步。
- `packages/clawbot/src/xianyu/xianyu_admin.py` — 删除未使用的 Frist server 源码读取，不改变预检结果。
- `apps/openclaw-manager-src/package.json`、`package-lock.json` — 桌面构建传递依赖安全 override 与锁文件。
- `scripts/assets/audit-jiyu-monitor-after-managed-update-20260808.jpg` — 生产发布后渠道排序、产品生态标签和真实健康状态截图。
- `docs/006-registries.md`、`docs/007-operations.md`、`docs/009-health.md`、`docs/053-jiyu-growth-payment-image-update-plan.md`、`docs/087-jiyu-image-mcp-guide.md`、`docs/012-handoff.md` — 同步合同、操作步骤、风险和交接。
### 验证
- JIYU 补丁在官方 `v0.1.172` 干净提交上通过 `git apply --check`；上游更新服务 unit 用例 `1/1`、排序/端点/CC Switch 前端用例 `13/13`、Vue 类型检查、运维脚本合同 `4/4`、工作流 YAML 与文档门均通过。
- 生图 MCP `tools/list` 仅返回 `generate_image`，缺少钥匙串 Key 时明确失败关闭；SDK `1.30.0` 锁文件生产依赖审计为 `0 vulnerabilities`。
- 真实 Chrome 重新加载确认两个生图分组、账号、渠道与 300±30 秒监控已保存，渠道B价格为 `0.12/张`；上游 502/401 继续作为未解决风险，不用重复付费请求伪造成功。

## [2026-08-08] JIYU 双端点、监控排序和生图 MCP 方案
> 领域: `frontend` | `ai-pool` | `deploy` | `docs`
> 影响模块: `Sub2API`, `channel monitor`, `API keys`, `CC Switch`, `JIYU update`
> 关联问题: HI-985, HI-986, HI-994, HI-995, HI-996
### 变更内容
- 生产发布 `v0.1.172-jiyu.5`：渠道监控固定按渠道A五条、渠道B五条排列，第二列仅显示匿名渠道，不再混排或展示第三方供应商名称；真实正常、降级和错误状态保持不变。
- “API 密钥”页固定同时展示 Claude 根端点和 ChatGPT `/v1` 端点；创建密钥弹窗选择分组后仍保留双端点说明，并默认勾选导入 CC Switch。
- 修复 JIYU 定制版本与同一官方基础版比较时的虚假更新提示；官方二进制继续禁止直接覆盖定制补丁，WebUI 自助更新改为“CI 兼容包 + root-only 安装代理”推荐方案，等待架构确认后实施。
- 确认 Sub2API 已原生支持 `/v1/images/generations`、生图权限、图片倍率和尺寸计价；确认本机两个旧生图 MCP 都指向不存在脚本，且两个现有上游配置只登记了文本模型，未把未知生图模型伪装为已同步。
- 新增生图、充值和自助更新执行方案，以及面向小白的生图专用 Key + CC Switch stdio MCP 教程和可复制 AI 提示词。
### 文件变更
- `scripts/sub2api-jiyu-v0.1.172.patch` — 固化双端点、定制版更新提示、监控排序和匿名渠道列。
- `docs/053-jiyu-growth-payment-image-update-plan.md` — 生图渠道、链动充值与 WebUI 更新分阶段方案。
- `docs/087-jiyu-image-mcp-guide.md` — 生图专用 Key 和 MCP 小白教程。
- `docs/003-docs-index.md`、`docs/007-operations.md`、`docs/009-health.md`、`docs/012-handoff.md` — 同步索引、生产事实、风险和交接。
### 验证
- EndpointPopover 聚焦测试 `2/2`、Vue 类型检查和 Vite 生产构建通过；补丁在干净的官方 `v0.1.172` 固定提交上通过 `git apply --check`。
- ARM64 二进制构建和生产安装成功，管理脚本状态确认 Sub2API、专用 Redis、更新检查 timer、备份 timer 均 active，内网健康检查通过。
- 真实 Chrome 重载确认 `v0.1.172-jiyu.5` 和 10 条监控顺序；表头为“渠道”，行值只显示渠道A/渠道B。
- 推送后 GitHub 默认分支返回 31 个 Dependabot 漏洞的聚合提示，已登记为 HI-997；本轮不盲目升级依赖，等待按运行时/开发时边界分组审计。

## [2026-08-08] JIYU AI 生产审计、10 路渠道和新手密钥闭环
> 领域: `frontend` | `ai-pool` | `deploy` | `infra` | `xianyu` | `docs`
> 影响模块: `Sub2API`, `CC Switch`, `channel monitor`, `JIYU readiness`, `链动小铺`
> 关联问题: HI-985, HI-986, HI-987, HI-988, HI-989
### 变更内容
- 将 10 个业务分组落为 10 个一对一渠道和 10 条真实监控，均保持 300 秒周期、±30 秒抖动；用户倍率继续严格等于对应上游倍率绝对增加 `0.05x`，渠道A OpenAI Plus 为 `0.06x → 0.11x`。
- 基于官方 Sub2API `v0.1.172` 固定提交维护可重复应用的 JIYU 补丁，生产发布 `v0.1.172-jiyu.3`；自动更新改为只检查，定制版只允许显式构建发布并在健康失败时自动回滚。新建监控表单默认值与生产合同统一为 300±30 秒。
- 创建密钥页按分组显示 Claude 根端点或 OpenAI `/v1` 端点，默认勾选“创建后立即导入 CC Switch”；首页只展示 JIYU AI、JY Logo、渠道A和渠道B，移除上游仓库入口并修复重复版本前缀。
- 系统监控默认周期从遗留 60 秒同步为 300 秒，定制表单默认抖动为 ±30 秒；更新检查能识别“基于当前官方最新版的 JIYU 构建”，不再误报待升级。
- 闲鱼/CC 运营投影升级为只读 readiness v2，真实反映 10 个渠道、10 条监控、倍率合同、库存和自动发货门，不用静态绿色掩盖异常。
- 链动小铺资料已改为 JIYU AI 并建立 ¥1/10/50/100/300/500/1000 七档统一 Logo 商品草稿；平台规则禁止代理类服务，全部保持下架、零库存，未绕过审核、未执行真实付款，也未把无效链接写回充值中心。
### 文件变更
- `scripts/sub2api-jiyu-v0.1.172.patch` — 固化品牌、端点引导、CC Switch 导入和空状态修复。
- `scripts/sub2api_oracle_manage.sh`、`scripts/sub2api_configure_jiyu_channels.mjs`、`scripts/sub2api_ops_scripts.test.mjs` — 固化检查式更新、构建发布、备份回滚和 10×10 配置合同。
- `scripts/cc_zhongzhuan_readiness_audit.mjs`、`packages/clawbot/src/xianyu/operations_projection.py`、`packages/clawbot/src/xianyu/xianyu_admin.py` 及聚焦测试 — readiness v2 和真实运营门。
- `scripts/assets/` — JY Logo 与不含凭据的审计截图。
- `docs/001-project-map.md`、`docs/002-changelog.md`、`docs/006-registries.md`、`docs/007-operations.md`、`docs/009-health.md`、`docs/012-handoff.md` — 同步生产事实、风险和交接证据。
### 验证
- Sub2API 聚焦前端测试 `10/10`、Vue 类型检查、Vite 生产构建、补丁干净应用和 `make sub2api-check` 均通过；生产服务、Redis、更新检查和备份 timer 均 active，内网健康检查通过。
- 闲鱼自动发货与 owner-loop 热点聚焦用例全绿；真实浏览器逐页检查用户端、管理端和系统设置 9 个标签，10 条监控页面同时显示正常、降级和错误状态。

## [2026-08-07] JIYU AI 上游展示名称匿名化
> 领域: `ai-pool` | `deploy` | `docs`
> 影响模块: `Sub2API`, `accounts`, `groups`, `channels`, `channel monitors`, `audit logs`
> 关联问题: HI-985
### 变更内容
- 将两个第三方上游在全站账号、分组、渠道、监控、备注、描述和后台审计记录中的展示名称统一替换为“渠道A”和“渠道B”，不再暴露供应商名称。
- 仅调整展示文本；API Key、上游域名、倍率、分组关系、模型定价、可调度状态和监控周期均保持不变。
### 文件变更
- `docs/002-changelog.md`、`docs/006-registries.md`、`docs/007-operations.md`、`docs/009-health.md` — 统一匿名渠道口径和远端验证证据。
### 验证
- PostgreSQL 全部 public 表逐表扫描确认旧展示名称残留为 `0`；账号、分组、渠道和监控数量保持 `10 / 10 / 6 / 6`。
- `make sub2api-check`、`make docs-check` 和 `git diff --check` 通过；管理端 WebUI 使用真实浏览器复核渠道显示。

## [2026-08-07] JIYU AI 上游、定价、监控、邮箱与文档运营闭环
> 领域: `ai-pool` | `deploy` | `frontend` | `docs`
> 影响模块: `Sub2API`, `JIYU AI branding`, `channel pricing`, `channel monitor`, `SMTP`, `CC Switch docs`
> 关联问题: HI-985, HI-986
### 变更内容
- 渠道A与渠道B各新建 5 个 JIYU 专用 Key，接入 10 个账号和 10 个独立分组；用户倍率统一为当前上游倍率绝对增加 `0.05x`，不复用历史上游 Key。
- 建立 6 个 active 渠道并同步模型定价，建立 6 条 Claude/OpenAI/Grok 真实连通监控，统一为 300 秒周期和 ±30 秒抖动。
- 渠道B的 5 个账号全部通过站内真实请求；渠道A的 Claude Kiro、OpenAI Pro、OpenAI Plus 通过。渠道A的 Claude 满血因上游组不支持 Anthropic 路由保持不可调度，监控继续如实记录 Grok/OpenAI 上游波动。
- 完成通用设置、2026-08-07 登录条款、用户默认值和 Gmail SMTP；开放注册保持关闭、邮箱验证开启。测试邮件与真实邮箱绑定验证码接口均返回 200。
- 邮箱绑定验证码、通知邮箱验证码和运维告警模板加入同域 JY 图形 Logo、验证码和有效期说明；保留既有深蓝、青绿、橙色视觉体系。
- 左侧新增“文档”，提供 CC Switch v3.19.2 官方三平台下载、站内一键导入和手动地址；修复手机端目录侧栏遮挡正文。
- 管理脚本新增 `brand-asset`，发布 512×512 PNG 到同域公开地址并随全新安装固化；上游白名单只增加两个指定域名，SSRF 私网防护不放宽。
### 文件变更
- `scripts/sub2api_oracle_manage.sh` — 固化图形 Logo 资源、手机文档样式、CC Switch 文档和上游白名单运维入口。
- `scripts/assets/jiyu-ai-logo-email.png` — 邮件与文档使用的 512×512 JY 图形 Logo。
- `scripts/sub2api_ops_scripts.test.mjs` — 增加品牌资源、文档和安全白名单合同测试。
- `.gitignore` — 仅放行已确认的 JIYU AI 品牌 PNG，其他临时截图继续忽略。
- `docs/002-changelog.md`、`docs/006-registries.md`、`docs/007-operations.md`、`docs/009-health.md` — 同步运营配置、已知上游限制和验证证据。
### 验证
- 渠道B的 Claude Kiro、Claude 满血、OpenAI Pro、OpenAI Plus、Grok 真实请求均返回内容；渠道A的 Claude Kiro、OpenAI Pro、OpenAI Plus 返回内容。
- PostgreSQL 查询确认 10 个分组的 `user_rate - upstream_rate = 0.0500`，6 个渠道均 active、6 条监控均 enabled。
- `/api/v1/pages/docs/images/jiyu-ai-logo.png` 返回 HTTP 200 `image/png`；手机 390×844 截图无目录遮挡。
- `/api/v1/admin/settings/send-test-email` 与 `/api/v1/user/account-bindings/email/send-code` 均返回 HTTP 200。

## [2026-08-07] CC中转切换为干净 Sub2API 底座并清理旧 New-API
> 领域: `deploy` | `infra` | `docs`
> 影响模块: `Sub2API`, `Oracle ARM`, `Apache`, `PostgreSQL`, `Redis`, `R2 backup`, `Tencent cold rollback`
> 关联问题: HI-983, HI-984
### 变更内容
- 生产站 OEM 品牌改为 `JIYU AI`，副标题改为 `Unified AI API Gateway`；登录页、首页、后台侧边栏和浏览器标题统一从 PostgreSQL 公共设置读取，底层服务名、数据库名和官方升级来源继续使用 `sub2api` 技术标识。
- 管理脚本新增可重复执行的 `brand` 命令，并在全新安装收口时自动应用品牌，避免未来重装或更新后回到默认站名。
- 尝试调用本机 `86gamestore_image` MCP 的 `gpt-image-2`，MCP 启动正常但上游返回 `502 Upstream access forbidden`；保留失败证据后改用可编辑 SVG 生成 4 套 Logo 方案，并导出 PNG 到桌面 `JIYU AI Logos` 目录。
- Oracle 主站 `jiyu.245334.xyz` 从 New-API 切换到官方 `Wei-Shaw/sub2api` `v0.1.171` ARM64 release；Sub2API 仅监听 `127.0.0.1:18080`，专用 Redis 监听 `127.0.0.1:16379`，PostgreSQL 使用独立 `sub2api` 数据库。
- 全新安装没有迁移任何旧用户、API Key、渠道、兑换码、日志或上游凭据；数据库验收为 `users=1`（新管理员）、`accounts=0`、`api_keys=0`、`channels=0`、`usage_logs=0`。
- 新增官方 release SHA-256 校验、升级前 PostgreSQL 备份、`flock` 并发锁、启动健康检查和失败自动回滚；`sub2api-update.timer` 每日检查，`sub2api-backup.timer` 每日做一致性备份。
- 删除 Oracle 与腾讯云的旧 New-API SQLite、运行目录、环境密钥、二进制、systemd 服务、Docker 容器/镜像及同名本地备份；旧 R2 加密对象删除 19 个并重新生成不含 `one-api.db` 的加密备份。
- 删除 Apache 旧 New-API HTML 品牌替换/标题注入，恢复 Sub2API 原生 CSP 页面；Frist-API 兼容服务仍保留，但其 New-API 桥接开关已落为 `0`。
- 将唯一管理员邮箱更新为 `djblack1209@gmail.com`，密码使用 bcrypt 写入数据库并同步 root-only 环境文件与 macOS 钥匙串；更新前已创建 PostgreSQL 备份，旧本机钥匙串账号已删除。
- 补充小白首次使用说明，明确“补号”入口为“账号管理 → 添加账号”，首次配置顺序为“分组管理 → 账号管理 → API 密钥”。
### 文件变更
- `scripts/sub2api_oracle_manage.sh` — 新增全新安装、收口、状态、检查、升级、备份、品牌恢复、切换、清理和旧底座永久清除入口。
- `scripts/sub2api_ops_scripts.test.mjs` — 新增 Shell 管理脚本 7 项安全合同。
- `Makefile` — 新增 `make sub2api-check`。
- `docs/001-project-map.md`、`docs/006-registries.md`、`docs/007-operations.md`、`docs/009-health.md` — 同步当前底座与清理边界。
### 验证
- `make sub2api-check`：6 passed；ShellCheck、Bash 语法和 `git diff --check` 通过。
- Oracle：Sub2API、专用 Redis、PostgreSQL、Apache、两个 Sub2API timer 均 active；`/health` 返回 `{"status":"ok"}`，`jiyu.245334.xyz` 首页/登录页 200，未授权 `/v1/models` 401。
- 新管理员邮箱的公网登录接口实际返回 admin 角色和访问令牌；管理员密码未写入仓库，已存 macOS 钥匙串“CC中转 Sub2API 管理员”。
- Playwright 截图：`output/playwright/sub2api-public-home-20260807.png`、`sub2api-public-home-mobile-20260807.png`、`sub2api-login-20260807.png`；桌面/移动首页和登录页无控制台错误。
- PostgreSQL 备份恢复到临时数据库成功（`restore_check=ok users=1`）；手动触发 `sub2api-update.service` 返回“当前 v0.1.171 已是最新稳定版”。

## [2026-08-07] 腾讯云失效 ClawBot 备用实例退役
> 领域: `deploy` | `infra` | `docs`
> 影响模块: `ClawBot VPS backup`, `failover timer`, `macOS LaunchAgent`, `Tencent shared services`
> 关联问题: HI-982
### 变更内容
- 线上核验确认 macOS `ai.openclaw.clawbot-agent` 是唯一持续运行的主实例，腾讯云保存的主心跳已约 109 天未更新；旧 `clawbot-failover.timer` 每 30 秒尝试提升备用实例，而备用进程因缺失 Python 模块持续失败并累计大量重启。
- 在服务器标准备份目录保存 service、timer、故障转移脚本和状态文件后，停用腾讯云 `clawbot.service` 与 `clawbot-failover.timer`，清除失效的提升状态但保留应用数据和回滚材料。
- 腾讯云 `wechat-receiver`、`openclaw-cloud-control` 与 `sillytavern` 保持运行；本次不触碰 Oracle 上的 New-API/Frist，也不删除任何业务数据。
### 验证
- 腾讯云旧 ClawBot 与 failover timer 均为 `inactive/disabled`；Mac 主 LaunchAgent 为 `running`，PID 保持不变且 `last exit code = never exited`。
- 状态页、EduMath 和 CC 中转公网健康探针均返回 HTTP 200；腾讯云其余三项共享业务仍为 active。
- 腾讯云可用内存约 502 MiB（25.7%），比退役前释放部分压力但仍低于 30% 运维余量线，继续作为资源优化项，不伪装为已闭环。
### 文件变更
- `docs/001-project-map.md`、`docs/002-changelog.md`、`docs/009-health.md` — 收口单主实例与 VPS 备用边界。

## [2026-08-05] 全维度审计闭环：安全、供应链、架构与自动灾备
> 领域: `backend` | `frontend` | `deploy` | `infra` | `docs` | `xianyu`
> 影响模块: `HTTP/浏览器安全`, `Frist runtime`, `闲鱼管理面`, `Intel Brief`, `Docker`, `CI`, `本机灾备`, `AI 开发 SOP`
> 关联问题: HI-965, HI-966, HI-967, HI-968, HI-969, HI-970, HI-971, HI-972, HI-973, HI-974, HI-975, HI-976, HI-977, HI-978, HI-979, HI-980, HI-981
### 变更内容
- 使用 mattpocock/skills 的 Wayfinder 目标地图、审计 ticket 和架构深模块原则完成全维度审计；在仓库文档规则下把 Destination / Notes / Decisions / Frontier 合并到 HEALTH，修正 `AGENTS.md` 中不存在或已改名的 Skill 路由。
- HTTP 客户端逐跳验证 DNS、重定向和固定地址，浏览器主文档/子资源/WebSocket 共用精确主机边界；API 限流只信显式可信代理并限制状态容量，最终日志 record/异常链统一脱敏并以 0700/0600 落盘。
- Frist 邮箱、重置、2FA、会话指纹和限流失败关闭；闲鱼根 Token 只换取 15 分钟、最多 128 个 HttpOnly 会话，写请求同源校验，页面使用 nonce CSP 和安全 DOM；CLIAnything 远程动态安装固定 403。
- 闲鱼运行对象先转换为不可变 snapshot，`operations_projection.py` 一次生成售卖、循环观察和买家进度；Frist 原子文件写、串行 mutation 与 AES-256-GCM 字段加密迁入 `runtime-store.js`，两个热点入口分别减少 223 行和 180 行。
- 更新 npm 直接/传递依赖、双平台 Python 哈希锁、Docker 固定 digest/amd64/非 root 安装和 RustSec 门；PR CI 覆盖全部目标分支，固定 Action SHA，并执行 ShellCheck、Gitleaks、npm/pip/cargo 与供应链检查。
- 重建本机灾备：SQLite 在线 `.backup`、包内逐文件 manifest、包外 SHA-256、原子 `.ready`、安全 tar、恢复 dry-run/drill/confirm、GPG 离机密文和数量/天数保留。`ai.openclaw.daily-backup` 已实装为每天 03:30 自动备份后强制恢复演练。
- 修复 Intel Brief 旧 schema v3 缺 `content_delivery_attempts.event_key` 导致的真实定时任务崩溃；真实库先做 root-only SQLite 备份，再迁移到 v4 并通过 quick_check。为避免提前发送真实消息，LaunchAgent 只重新加载，等待 08:30 自然验证。
- 修复 Bot 假健康、Tauri 可预测 `/tmp` WhatsApp 脚本和容器内 store 项目根定位；桌面本机进程临时文件改为随机 0700、用后清理，容器完整构建后以非 root 导入冒烟。
- 修复首次远程 CI 暴露的 Linux 差异：健康脚本 heredoc 改为可移植子 shell，并在审计命令无输出时生成结构化失败 JSON；Node 24 测试夹具对已停止后台巡检的在途原子写执行有限目录清理重试；文档门禁在最小 CI 镜像未安装 `rg` 时自动回退到 `grep`。
### 验证
- 聚焦回归：闲鱼投影/履约/owner/API `208/208`，Intel schema/订阅投递/生产链 `37/37`，Frist `234/234`，自动运维 `21/21`，新增 runtime store `3/3`；Ruff、ShellCheck、Node/Bash 语法和 `git diff --check` 通过。
- 安全门：四套 npm production audit 为 0，Linux/macOS pip-audit 无已知漏洞，RustSec 为 0 vulnerability（17 条目标平台/上游 informational allow warning），35 个仓库 Shell 脚本零告警；Gitleaks 当前树和 859 提交历史均无泄漏。
- 容器：完整 amd64 镜像从哈希锁构建成功，最终以 `uid=999 gid=999` 运行并完成 `imports=ok` 冒烟；SSRF/浏览器组合回归与真实 `https://example.com` 请求均通过。
- 实机：`ai.openclaw.daily-backup` 已加载并退出 0；`openeverything-20260805-034824.tgz` 完整 restore drill 通过。Intel 真实数据库备份 SHA-256 为 `db845bc5ce4e380086090eeef38bd5e27f54dbf89af3cb2d59e88cc496f036cf`，迁移后 schema v4 与 quick_check 通过。
- 跨平台：Linux Node 24 健康脚本聚焦回归、Frist Node 24 后台巡检用例、无 `rg` 文档治理检查和 GitHub PR 五项检查作为推送后发布门，避免 macOS 本机绿灯掩盖 Bash/文件系统差异。
- 最终 `make ci-local`、桌面构建/唯一安装和截图数字集中记录在 `docs/086-release-evidence.md`，避免多处复制漂移。
### 文件变更
- `packages/clawbot/src/http_client.py`、`src/tools/web_tool.py`、`src/api/server.py`、`src/log_config.py`、`src/integrations/cli_anything_bridge.py` 与测试 — SSRF、限流、日志和动态安装边界。
- `packages/clawbot/src/xianyu/operations_projection.py`、`xianyu_admin.py`、`xianyu_live.py` 与测试 — owner 快照、纯投影和管理会话安全。
- `packages/clawbot/src/intel/db/store.py` 与测试 — schema v4 真实旧库迁移。
- `apps/frist-api/server/runtime-store.js`、认证/安全/支付模块与测试 — 深模块、会话、限流和资金链失败关闭。
- `scripts/local_backup.sh`、`disaster_recovery.sh`、`manage_backup_launchagent.sh`、`auto_health_check.sh`、`auto_ops_scripts.test.mjs`、`Makefile` — 自动备份、恢复演练和健康门。
- `.github/workflows/`、依赖锁、Docker/Compose、`scripts/check_supply_chain.mjs`、`scripts/check_clean_install.sh` — 可复现构建与安全门。
- `AGENTS.md`、`docs/001-project-map.md`、`docs/002-changelog.md`、`docs/006-registries.md`、`docs/007-operations.md`、`docs/009-health.md`、`docs/086-release-evidence.md` — 目标、事实源、运维和发布证据。

## [2026-08-04] 8 分目标复审收口：实盘、履约、写队列与真实回滚
> 领域: `backend` | `frontend` | `trading` | `xianyu` | `deploy` | `infra` | `docs`
> 影响模块: `IBKR SELL`, `闲鱼履约`, `owner-loop`, `Frist runtime`, `认证限流`, `Tauri 回滚`, `五维评分`
> 关联问题: HI-817, HI-818, HI-890, HI-959, HI-960, HI-961, HI-962, HI-963, HI-964
### 变更内容
- 实盘 SELL 严格区分 MKT/LMT，限价缺价格不再退化为市价单；下单前串行核对真实多头持仓、未完成卖单和本地保留量，取消、失效、零成交和结果不确定均不再返回成功。
- 闲鱼只从真实订单/交易 ID 生成履约键；主 webhook、订单轮询复用、浏览器和人工补发统一使用 SQLite 原子领取。发送异常停在 `message_send_uncertain` 并禁止自动重试，暂停分支不能覆盖已发送或不确定终态。
- `AsyncLoopOwner` 的旧循环关闭只回收本循环任务，不再清空已经重绑的新 owner；闲鱼管理 HTTP/WS 以实际 bind host 和 `prod/production` 统一失败关闭。
- Frist 普通 runtime `mutate` 强制同步，注册/重置邮件、补货探测、渠道巡检、上游余额和 New-API Token 外部请求移出全局写队列；生产禁止本地旧网关兼容链，密码重置请求增加账号级 3 次/15 分钟限流。
- 桌面版本升至 0.1.1；构建只把 CDHash 不同的签名 App 计为上一版，清单新增源码补丁与 DMG SHA-256。同指纹检查固定拒绝，0.1.1/0.1.0 已真实双向交换后恢复 0.1.1。
- 五维评分改为每维 10 个二元证据门；历史第三方凭据轮换、Developer ID/公证、当前工作树远端 Linux 产物和巨型热点不再主观加分，明确记为 P2/未通过项。
### 验证
- 交易/API/owner-loop 聚焦回归 `145/145`，闲鱼自动发货与 owner-loop `133/133`，均在 `PYTHONASYNCIODEBUG=1` 和 `RuntimeWarning` 失败门下通过；相关 Ruff、Node 语法和 `git diff --check` 通过。
- Frist 全量 `228/228`，账号级重置限流、SMTP 队列解耦、补货探测和渠道巡检均有回归。
- 运维脚本 `11/11`；两个不同 ad-hoc 签名测试 App 可双向交换，同指纹固定拒绝。真实 `make tauri-build` 生成 `OpenClaw_0.1.1_aarch64.dmg`，0.1.1 `42799197…` 与 0.1.0 `39fb9e44…` 不同，真实回滚后已恢复 0.1.1；最终源码补丁和 DMG SHA-256 由构建后的 root-only 回滚清单记录，避免文档复制值漂移。
### 文件变更
- `packages/clawbot/src/broker_bridge.py`、`src/api/routers/trading.py`、`src/core/loop_owner.py` 与对应测试 — SELL 持仓/状态和旧循环关闭边界。
- `packages/clawbot/src/xianyu/xianyu_live.py`、`xianyu_context.py`、`xianyu_admin.py` 与对应测试 — 稳定订单身份、原子分配/发送和生产鉴权。
- `apps/frist-api/server/server.js`、`security.js`、`email.js`、生产环境示例和测试 — 外部 I/O 队列拆分与重置请求限流。
- `scripts/tauri_build_install.sh`、`tauri_rollback.sh`、`auto_ops_scripts.test.mjs`、桌面版本文件 — 真实异版本回滚与发布指纹。
- `docs/001-project-map.md`、`docs/002-changelog.md`、`docs/006-registries.md`、`docs/007-operations.md`、`docs/009-health.md`、`docs/086-release-evidence.md` — 事实源、P2 残余和二元评分。

## [2026-08-04] 8 分目标最终收口：失败关闭、供应链与发布证据校准
> 领域: `backend` | `frontend` | `deploy` | `infra` | `docs`
> 影响模块: `owner-loop`, `SocialAutopilot`, `Bulkhead`, `闲鱼只读探测`, `Frist 支付`, `MCP Store`, `桌面构建`, `CI`
> 关联问题: HI-947, HI-952, HI-954, HI-955, HI-956, HI-957, HI-958
### 变更内容
- owner-loop 提交改为 Future 登记 + owner 线程惰性创建协程；停止/提交竞态失败关闭，`loop.close()` 前取消并排空已启动任务，避免 pending Task 被销毁。
- Bulkhead 动态重配原位调整同一隔离舱，闲鱼只读扫单明确映射 owner 未就绪/超时为 503/504；SocialAutopilot 关机阶段释放 APScheduler 和循环引用但不篡改持久化 `enabled` 意图。
- Frist 充值拆为准备事务、事务外渠道请求、成功/失败落库三段；渠道请求有硬超时，金额校验使用订单总额字段，微信回调增加时间戳/平台序列号，重复成功回调不重复追加事件。
- Tauri MCP Store 降级为受管目录只读展示：从唯一 `MANAGED_MCP_PACKAGES` 注册表派生版本和元数据，不读取旧配置、不返回 command/args/env、不提供伪 stdio 启停入口；真实 MCP 会话由 CC Switch/OpenClaw 官方配置链负责。
- Compose 镜像固定 `tag@sha256`，新增临时目录干净安装门；桌面构建在所有备份就绪前不删除现有 App。
- 桌面开发工具链安全 override 更新为 `brace-expansion@5.0.9`、`fast-uri@4.1.2`、`hono@4.13.0`、`ip-address@10.4.0`；完整桌面/生产依赖 `npm audit` 重新归零。
- 忽略闲鱼运营状态文件旁的进程锁临时文件，避免测试或异常退出把本机运行态带入工作树。
- 文档真实性检查区分仓库事实与明确受 Git 忽略的本机运行资产；干净检出不再因私有 `.env`、生产 SQLite 或历史情报 evidence 缺席而误报，源码、脚本和发布文档路径仍逐项校验。
### 验证
- owner-loop、Brain/EventBus、Social、IBKR、闲鱼和 WebSocket 聚焦回归在 `PYTHONASYNCIODEBUG=1` 下通过；Bulkhead、SocialAutopilot、闲鱼自动发货聚焦回归通过；最终 `make ci-local` 为 Python `2,364` 收集、`2,362` 通过、`2` 预期跳过、`0` 失败，总覆盖率 `44.34%`、关键聚合 `88%`；Frist `226/226`、桌面合同 `27/27`、Rust `44/44`，TypeScript、ESLint、Vite 和文档门全绿。
- 供应链检查验证 2 个工作流、16 个 Action SHA、354 个 npm 锁定包和 3 个 Compose 文件的 digest；临时目录 npm/Python 哈希锁安装通过；桌面完整/生产、Frist、runtime npm audit 和 Linux/macOS pip-audit 均为 0；Gitleaks 扫描 859 commits、约 55.11 MB 无泄漏。
- `make tauri-build` 生成 `OpenClaw.app` 与 `OpenClaw_0.1.0_aarch64.dmg`；严格 ad-hoc 签名、DMG checksum、`rollback_ready=true`、唯一安装和旧 App 删除前备份闸门均通过。原生首屏为 `output/playwright/openclaw-installed-app-final.png`，Vite 桌面/移动验收为 `openclaw-vite-desktop-final.png` / `openclaw-vite-mobile-final.png`。
### 文件变更
- `packages/clawbot/src/core/loop_owner.py`、`resilience.py`、`social_scheduler.py`、`xianyu/xianyu_admin.py` 与对应测试 — 关闭竞态、重配和生命周期边界。
- `apps/frist-api/server/server.js`、`payments.js`、`shared.js` 与支付测试 — 两阶段充值、超时、金额与回调时效/去重。
- `apps/openclaw-manager-src/src-tauri/src/commands/mcp.rs`、`npm_runtime.rs`、Store IPC/UI、供应链脚本和 Compose 文件 — 只读 MCP 目录、唯一注册表和 digest 门。
- `scripts/tauri_build_install.sh`、`check_clean_install.sh`、`check_docs_layout.sh`、`Makefile`、`docs/` — 构建备份闸门、干净安装、干净检出文档检查和证据口径。

## [2026-08-04] 8 分目标第三阶段：事件循环、供应链与发布证据收口
> 领域: `backend` | `frontend` | `deploy` | `infra` | `docs`
> 影响模块: `Brain/EventBus`, `交易与闲鱼所有者循环`, `Frist 支付与会话`, `Tauri npm/MCP 运行时`, `CI 与覆盖率`, `桌面发布回滚`
> 关联问题: HI-942, HI-943, HI-944, HI-945, HI-946, HI-947, HI-948, HI-949, HI-950, HI-951, HI-952, HI-953
### 变更内容
- 把 Brain、EventBus、SocialAutopilot、IBKR、闲鱼实时链、WebSocket 推送、CLI bridge、LiteLLM Router 和 resilience primitive 收口到显式所有者循环；跨线程入口转发，未就绪失败关闭，FastAPI 在交易和调度服务初始化后才监听。
- Frist 支付回调新增本机商户身份、订单原渠道、状态、金额和平台交易号唯一性五重校验；微信/支付宝下单响应也校验平台签名，缺失、过期、序列号不符或验签失败统一返回 502。微信平台公钥进入可下单就绪门。
- Frist 将可信代理/限流、会话/CSRF、支付、共享规则和目录规则分别收口到 `security.js`、`auth.js`、`payments.js`、`shared.js` 和 `catalog.js`；删除会丢运行字段的未使用 `store.js`、绕过完整管理员校验的旧接口及弱化的重复安全实现。`server.js` 从审计基线 9,263 行降至 7,795 行；加密占位 API Key 固定拒绝。
- 闲鱼补发与浏览器助手统一复用原子领取、发送、不确定态停机和完成落库状态机；发送异常不能自动重试，仍需人工核对。
- 桌面安装器改用内嵌 npm package-lock：354 个运行包及传递依赖具备 SHA-512，安装执行 `npm ci --ignore-scripts`；MCP 运行时注册表和 Store 目录现在由最终收口条目统一描述。已拒绝含高危项的 OpenClaw 稳定包，精确采用审计为 0 且配置合同冒烟通过的 `2026.7.2-beta.7`。
- 两个 GitHub 工作流的 16 个 Action 全部固定完整 commit SHA；New-API 同步 checkout 不持久化写凭据。新增 `make supply-chain-check`，同时验证 Action SHA、npm 直接/传递完整性和高危漏洞门。
- Python 增加 Linux/macOS 双哈希锁与复算门；`aiohttp` 升至 3.14.3、`cryptography` 升至 50.0.0，pip-audit 对完整锁使用无二次解析模式并回到 0 已知漏洞。覆盖率增加总体、高风险聚合及逐文件下限。
- Scheduler 修复切换请求和异常字段失败关闭，并补 390px 自动图标侧栏；Store 统一读取 Tauri MCP 配置；Assistant 支持真实取消。Tauri 构建保存签名回滚副本、CDHash 清单并提供只读/显式回滚入口。
### 验证
- 该阶段的历史基线为 Python 2,360 个节点、Frist `222/222`、桌面/Social/运维合同 `26/26`、Rust `45/45`；最终收口后的数字以本次 `make ci-local` 输出和 `docs/086-release-evidence.md` 为准，避免把阶段基线误报为当前结果。
- 支付提供商创建响应聚焦合同 `5/5`；Frist 新增 8 项静态安全合同，覆盖加密占位 Key、危险旧接口和弱安全重复事实源；闲鱼发货与所有者循环聚焦回归全绿。
- npm 三组审计均为 0；受管运行时 `354` 包完整性检查、Python 双锁复算与 `pip-audit` 均通过；Gitleaks 扫描 859 个提交、约 55 MB 历史无泄漏。干净 HOME 运行 `OpenClaw 2026.7.2-beta.7`，配置写入/校验、Gateway 帮助和插件枚举均退出 0。
- `make tauri-build` 生成并安装 `OpenClaw.app` 与 `OpenClaw_0.1.0_aarch64.dmg`；App 严格 ad-hoc 签名、DMG 校验、唯一安装和当前/上一版回滚签名均通过，`rollback_ready=true`。真实安装包首屏截图为 `output/playwright/openclaw-installed-app.png`；Scheduler 与实盘卖出桌面/移动截图同时保留。
### 文件变更
- `packages/clawbot/src/core/loop_owner.py`、`brain.py`、`event_bus.py`、`social_scheduler.py`、`broker_bridge.py`、`xianyu/`、`api/routers/` 与对应测试 — 所有者循环和失败关闭。
- `apps/frist-api/server/auth.js`、`security.js`、`payments.js`、`shared.js`、`catalog.js`、`server.js`、删除的 `store.js` 与 `tests/` — 安全域拆分、危险重复事实清理和支付全链路负向门。
- `apps/openclaw-manager-src/src-tauri/npm-runtime-lock/`、`src/commands/npm_runtime.rs`、`installer.rs`、`mcp.rs` — 受管 npm 完整性锁与本地 MCP 入口。
- `.github/workflows/`、`Makefile`、`scripts/check_supply_chain.mjs`、`scripts/check_docs_layout.sh`、`packages/clawbot/requirements*.txt` — CI、供应链、文档事实与依赖锁。
- `apps/openclaw-manager-src/src/components/`、`src/lib/` — 调度、Store、Assistant、交易确认和移动端布局合同。
- `scripts/tauri_build_install.sh`、`scripts/tauri_rollback.sh` — 签名构建、持久回滚副本与清单校验。

## [2026-08-04] 8 分目标第二阶段：认证与定时任务失败关闭
> 领域: `backend` | `trading` | `infra` | `docs`
> 影响模块: `Frist-API 认证限流`, `FastAPI WebSocket`, `管理员控制台`, `交易重挂`, `Intel Brief 调度`
> 关联问题: HI-937, HI-938, HI-939, HI-940, HI-941
### 变更内容
- Frist 默认忽略客户端自报的转发头；只有 socket 对端命中显式可信代理名单时才从右向左解析 `X-Forwarded-For`。密码重置确认叠加账号 HMAC 限流，限流表增加过期清理和 10000 桶容量上限，满容量时失败关闭。
- HTTP 与 WebSocket 共用无 Token 本机开发判定；`production`、`prod` 和非本机绑定都拒绝连接，避免实时事件流绕过 HTTP 安全边界。
- 管理员根令牌从浏览器长期存储改为仅在页面内存使用，管理端按钮和提示明确“本次会话”，刷新或关闭页面自动清空。
- 隔夜 BUY 重挂默认关闭；只有显式开关与自动交易模式同时启用才允许入队和提交，人工确认模式不继承旧订单授权。
- Intel Brief 只有 runner 明确返回 `status=success` 才记录当天完成；Telegram 或沙箱投递失败不会再封死当天重试。
### 验证
- Frist 可信代理、账号级重置限流和容量边界在旧代码为 `0/3`，修复后 `3/3`；管理员存储合同旧代码红灯、修复后 `1/1`。
- WebSocket/HTTP 无 Token 策略新增 `prod` 和一致性用例，旧代码 `2` 项失败，修复后聚焦用例 `6/6`，Ruff 与 Python 编译通过。
- 交易重挂新增两项失败关闭用例，旧代码 `2/2` 失败；Intel 失败重试旧代码第二次返回 `skipped`。修复后两份调度测试合计 `46/46`。
- 最终 `make ci-local` 八阶段退出码 0：Python 全仓跑到 100% 且仅 2 项预期跳过，Frist `206/206`，桌面合同 `22/22`，TypeScript、Rust `34/34` 与文档 `23/23` 全部通过；前端 ESLint 与 Vite 正式构建通过，Gitleaks 对当前差异扫描为 0 泄漏。
### 文件变更
- `apps/frist-api/server/server.js`、`src/admin.js`、`admin.html`、`deploy/production.env.example`、`tests/server.test.mjs`、`tests/business-flow.test.mjs` — 可信代理、限流容量、账号重置保护和管理员临时令牌。
- `packages/clawbot/src/api/auth.py`、`tests/test_api_routes_regression.py` — HTTP/WS 统一无 Token 策略。
- `packages/clawbot/src/trading/_scheduler_tasks.py`、`tests/test_trading_system.py` — 隔夜重挂双重授权门。
- `packages/clawbot/src/execution/scheduler.py`、`tests/test_intel_scheduler_gate.py` — 成功后才封存当天。
- `docs/002-changelog.md`、`docs/006-registries.md`、`docs/007-operations.md`、`docs/009-health.md` — 同步变更、配置、运维和健康状态。

## [2026-08-04] 8 分目标第一阶段：支付、实盘卖出与闲鱼放行安全门
> 领域: `backend` | `frontend` | `trading` | `xianyu` | `docs`
> 影响模块: `Frist-API 支付`, `Portfolio 实盘卖出`, `CC中转闲鱼运营状态`, `桌面安全回归`
> 关联问题: HI-934, HI-935, HI-936
### 变更内容
- 支付宝渠道必须同时配置 App ID、商户私钥和平台公钥才会进入就绪状态；异步通知缺少平台公钥时固定返回 503，不能再绕过签名验证进入入账链路。
- Portfolio 的整仓市价卖出改为“首次点击只打开危险操作确认框 → 展示股票、数量和 MKT 类型 → 确认后才提交”；同步提交锁阻止同一渲染帧重复下单，所有卖出按钮在请求中统一禁用。
- 桌面 API 不再把任意 HTTP 2xx 当作卖出成功；只有合法 JSON 且业务字段 `success=true` 才显示成功，`success=false`、缺少字段或非法响应均显示失败。
- 危险确认框补齐标准 `dialog` 语义，并把默认焦点从红色确认按钮移到取消按钮，降低键盘误触真实资金操作的风险。
- 闲鱼单次发卡票的授权、读取、消费和写回统一进入跨线程/跨进程可重入锁；状态使用同目录临时文件、`fsync` 和原子替换，缺失或损坏时默认暂停，只有显式环境配置或人工恢复才能解除。
### 验证
- 支付红绿回归：旧代码新增用例 `0/2`，修复后聚焦与现有支付宝链路合计 `4/4` 通过。
- 桌面安全合同：旧代码 `7/8`，修复后 `8/8`；`npx tsc --noEmit` 通过。
- 闲鱼并发红灯在旧代码中观测到一张票被成功消费 5 次；修复后缺失/损坏失败关闭、并发唯一消费及既有单次发卡链路 4 项通过，完整闲鱼自动发货测试文件跑到 100%。
- Playwright 在 1440×900 和 390×844 验证确认框无溢出/重叠且取消按钮默认聚焦；模拟 HTTP 200 + `success=false` 后页面显示“卖出失败”，未误报成功。截图：`output/playwright/portfolio-sell-confirm-desktop.png`、`portfolio-sell-confirm-mobile.png`。
- 最终 `make ci-local` 八阶段退出码 0：Python Ruff、全仓测试与语法通过，Frist `202/202`，桌面安全/Social/运维合同 `22/22`，TypeScript、Rust `34/34`、`cargo check --locked` 和 23 份文档治理全部通过；前端 lint 与 Vite 正式构建通过。Git diff 与两个新增文件的 Gitleaks 扫描均为 0 泄漏。
### 文件变更
- `apps/frist-api/server/payments.js`、`tests/payments.test.mjs` — 支付宝就绪与通知验签失败关闭。
- `apps/openclaw-manager-src/src/components/Portfolio/index.tsx`、`src/components/ui/confirm-dialog.tsx`、`src/lib/api.ts`、`src/lib/trading-sell.ts`、`src/lib/security-hardening.static.test.mjs` — 卖出复核、同步防重、危险焦点和业务成功校验。
- `packages/clawbot/src/xianyu/cc_operator_state.py`、`tests/test_xianyu_cc_auto_ship.py` — 运营状态原子持久化、跨进程事务和并发回归。
- `docs/002-changelog.md`、`docs/006-registries.md`、`docs/009-health.md` — 同步变更、操作入口与风险关闭证据。

## [2026-08-04] 每日资讯 V2 内容正确性、双语与富媒体闭环
> 领域: `backend` | `ai-pool` | `deploy` | `infra` | `docs`
> 影响模块: `Intel Brief 内容管道`, `Telegram 菜单与投递`, `CC Switch 翻译池`, `SQLite V3`, `LaunchAgent`, `运行健康`
> 关联问题: HI-928, HI-929, HI-930, HI-931, HI-932, HI-933
### 变更内容
- 新增六源统一内容契约和 V2 选择管道：缺失/未来/过期日期 fail-closed，Senate 先全量按披露日排序再限额，A股补交易日，GitHub 保留真实仓库字段，13F 按 accession 聚合；事件键、实体冷却、来源/类别配额和确定性评分共同生成多样化 Top 3。
- 修复 2020 BYND、缺失日期、跨日重复、同 GitHub 仓库刷屏、空成功覆盖 LKG 和首次基线提前完成；GitHub/13F 基线必须两源均有新鲜观察才完成，旧 repo/accession 在后续运行持续拦截，新 accession 可进入候选。
- Telegram 采用方案 C：搬运 tgNetDisc 的 `file_id` 存储核心，不引入 Go 服务、公开代理或第二轮询器。候选 3 深色封面通过官方 `sendPhoto` 投递，首屏保留管道 Top 3 顺序，按钮支持分类、查看全部和中英文回放。
- 媒体缓存按脱敏 Bot 身份、渲染版本和内容哈希隔离；无私有素材群时也会读取首位收件人种入的缓存。Telegram 明确拒绝旧 `file_id` 时，系统作废缓存、用本地封面重传一次并保存新引用。
- 新增 `709` / `/language zh|en`，注册 Telegram default/zh/en 三套原生命令；语言切换和 brief callback 不恢复 paused 用户。首次翻译降级为 `partial_source_fallback` 后，供应商恢复可再次生成完整译文。
- 接入本机 CC Switch 最多三个第三方 HTTPS 端点，批量翻译同语言字段并持久化非密钥缓存；Key 只驻留内存且不进入 `repr`，三端共用 45 秒总 deadline，错误只暴露稳定类型。
- SQLite 升级 V3：增加结构化 brief/localization、内容事实/观察/候选、来源尝试/LKG、媒体资产、投递 artifact、逐事件状态和投递 claim lease；V0/V2 幂等迁移保留历史行并把生产投递合同收口到 Asia/Singapore 08:30。
- listener 改为只保留有意义事件，30 天且最多 2000 文件；callback 先确认再翻译/回放，正文 `sent/partial/unknown` 均提交 offset，只有首段明确失败才重试，避免 callback 辅助失败或超时导致重复回复。
- 生产菜单只提供每天 08:30 与每周一 08:30；无法由唯一 LaunchAgent 履约的时间会明确拒绝。新增只读运行健康汇总，覆盖数据库、六源、7 日周期/投递、心跳和证据目录门。
### 验证
- Intel Brief 全量：345 项通过；变更文件 Ruff check、Ruff format、Python 编译和 `git diff --check` 全绿。
- `make ci-local` 八阶段全部通过：Python 全仓 100%、Frist-API 200/200、桌面安全边界 20/20、TypeScript、Rust 34/34、`cargo check --locked` 与 23 份文档治理均为绿色。
- 真实 CC Switch 最小翻译烟测：3 个端点可用，英文句子成功翻译为中文；过程未输出或持久化 API Key。
- 视觉 QA：390 x 844 同视口实现与参考合并比较，控制台 0 error / 0 warning；详情见 `docs/085-intel-brief-design-qa.md`。
- 本机生产已迁移到 SQLite V3 和 Asia/Singapore 08:30，listener 以 0600 独占锁单实例运行；真实 Telegram `sendPhoto` 验收成功并种入 1 个 active `file_id`。运行健康无 hard failure，六源和 7 日 SLI 按事实保持 warmup。
- 旧 listener 的 202,726 级文件目录完成隔离后清理，释放 810,904 KiB；数据库、私有环境和旧 plist 回滚副本继续以 0600 保留。与 CC Switch 本体无关的“CC中转”本机弹窗定位到闲鱼 `xianyu_admin.py` 的 `osascript` 运营提醒，已通过本机私有运行开关关闭；CC Switch 数据库、Provider、密钥和路由保持原配置。
### 文件变更
- `packages/clawbot/src/intel/content_contract.py`、`content_pipeline.py`、`brief_builder.py`、`production_cycle.py` — 内容事实、筛选、LKG 与基线水位。
- `packages/clawbot/src/intel/localization.py`、`translation_service.py` — 双语、缓存和 CC Switch 三端池。
- `packages/clawbot/src/intel/telegram_brief_renderer.py`、`telegram_media_store.py`、`telegram_delivery.py`、`subscription_delivery.py` — Top 3、图片、回放、媒体复用与投递 claim。
- `packages/clawbot/src/intel/db/intel_brief_schema.sql`、`db/store.py` — SQLite V3 增量迁移与中央审计状态。
- `packages/clawbot/scripts/intel_telegram_update_daemon.py`、`scripts/intel_runtime_health.py`、`scripts/auto_health_check.sh` — listener 留存和运行健康。
- `packages/clawbot/assets/intel/openclaw-intel-brief-dark.jpg` — 候选 3 生产封面。
- `docs/001-project-map.md`、`002-changelog.md`、`003-docs-index.md`、`006-registries.md`、`007-operations.md`、`009-health.md`、`010-feature-specs.md`、`052-intel-brief-master-plan.md`、`085-intel-brief-design-qa.md` — 架构、基线、运维、规格和设计证据。

## [2026-08-03] P0 安全与交易正确性整改闭环
> 领域: `backend` | `frontend` | `ai-pool` | `deploy` | `infra` | `trading` | `social` | `docs`
> 影响模块: `Telegram 鉴权`, `Agent 工具`, `OMEGA DAG`, `交易状态机`, `社媒发布门`, `Frist-API/New-API`, `Tauri Manager`, `运行时健康`, `CI`
> 关联问题: HI-913, HI-914, HI-915, HI-916, HI-917, HI-918, HI-921, HI-922, HI-923, HI-924, HI-925, HI-926, HI-927
### 变更内容
- Telegram 主 Bot、OMEGA Gateway、Inline Query、图片、文档和语音等入口统一改为白名单为空即拒绝；启动配置缺少有效正整数用户 ID 时直接阻止服务启动，环境变量注入部署不再强制依赖磁盘 `.env`。
- 自动 Agent 工具循环移除文件读写、Shell、代码执行和记忆写入；外部网页内容进入上下文后撤销后续工具权限。`/agent` 从本地 CodeAgent 改为只读 ToolCallingAgent，Bash 整体禁用 Git，`/claude` 禁止 Telegram 提示词进入终端。Python 仅执行 RestrictedPython 受限字节码，Node/Shell 代码执行关闭，FileTool 收紧软链接和敏感文件边界。
- 自动交易默认关闭，IBKR 预算以配置上限和账户可用资金的较小值为准且同步不清零已花金额；只有确认 `filled_qty > 0` 的真实成交才能建立或减少真实持仓，未决入场/退出进入对账状态，模拟回退不写真实交易记录。
- OMEGA DAG 深拷贝节点输入和上游结果，把顶层及 `data/result/details` 内的 `success=false`、`ok=false`、错误和未完成状态识别为业务失败；依赖/备选 ID 在执行前校验，fallback 仅在主节点失败后激活，成功后再放行下游。
- 社媒所有直发入口收口到“草稿审核快照 + 10 分钟一次性确认 + 原子消费”发布门，内容编辑立即撤销旧授权；`publishing/published` 草稿禁止编辑/删除/重审，状态冲突追加外部结果审计，落盘失败时保留不可重发状态并要求人工对账。夜间定时器、平台 helper、DAG 和旧自动发布路径只生成草稿或拒绝直发。
- Frist-API 为共享 New-API Token 建立本地客户归属，按归属过滤看板和日志并保护更新、删除、导入；修正人民币分与 New-API quota units 混用问题，归属同时记录 `allocatedCents` 和 `upstreamQuotaUnits`。创建 Key 改为“本地额度预留 → 上游零额度暂存 → 本地归属落盘 → 上游激活”，归属写入或激活失败会撤销暂存 Token 并回滚余额。Frist 自身的 `/v1` 桥接现在会在实际网关请求前精确校验 bearer：只有归属用户唯一存在、owner 完整且 active、上游 Token enabled、有限且有剩余额度才放行；未归属、旧字符串、待激活、残缺、孤儿、无限、耗尽或禁用 Token 全部 fail-closed。显式历史归属工具默认 dry-run；`--apply` 必须通过 `--newapi-db` 只读验证有限正额度，并全程持有同目录独占锁，写入前自动备份，拒绝并发、覆盖和自动猜测。Token 删除必须按精确 ID 复验，库存分页或上游失败会让看板显式失败，不再伪装成空账户。会话增加服务端过期、登出、密码变更/重置全会话撤销和 CSRF 恢复。
- Tauri Manager 移除 WebView 文件权限和 IBKR 自定义 Shell 字段；管理器生成的本地 `gateway.auth.token` 使用强随机字符串，实际 OpenClaw 2026.7.1 支持的 Token/密码/远程 SecretRef 原样保留并交由官方校验。配置和导出在 IPC 边界递归脱敏，保存时递归恢复对象/数组内磁盘原凭据；Provider 更新基于最新对象合并，保留 SecretRef、headers/request 等未建模字段。渠道 `enabled` 可真实持久化，JSON/env 联合读取与写入共用跨实例锁；环境键兼容 dotenv/export 两种格式并消除重复项。单文件使用原子替换，跨文件普通错误会补偿恢复，强制终止边界登记为 HI-922。服务停止仅作用于已登记且身份核验通过的进程，敏感 IPC 不再记录参数或返回值。
- CI 从“最多允许 15 个失败”改为任一测试失败即阻断，并新增 Frist-API、桌面安全边界、Rust 测试/编译和文档治理门禁；`make ci-local` 同步为 8 阶段本地闭环入口。
- Tauri 桌面应用的 `Cargo.lock` 从忽略项改为版本化资产，将兼容范围内的 Rust 栈固定到已通过隔离测试的 Tauri 2.11.x；本地与 GitHub Rust 门禁统一使用 `cargo test --locked` / `cargo check --locked`，干净工作树若出现依赖解析漂移会直接失败。Capability schema 随锁定版本重新生成并纳入同一基线。
- 首次真实 `make tauri-build` 红灯发现 Rust Tauri 已锁到 `2.11.5`，JavaScript API/CLI 仍为 `2.10.1`，静态编译不会触发 Tauri 的主次版本一致性门。JavaScript API/CLI 已对齐到官方注册表 `2.11.x`，运维合同新增跨语言版本断言。第二次构建进一步发现无 Apple 身份时只有可执行文件 linker 签名、App 资源没有 sealed manifest；按 Tauri 官方 ARM 内测方案配置 `signingIdentity="-"`，并对构建产物和覆盖前临时安装副本强制执行严格 `codesign`，不把 ad-hoc 包冒充 Developer ID/公证发行版。
- 修复 Frist 在 Node 18 下每个 HTTP 测试夹具等待 5 秒 keep-alive 才关闭的问题：测试回收现在先发起 server close，再主动清理空闲与现存连接；Node 18/24 仍跑同一套 200 项合同，生产服务的优雅关闭逻辑不变。
- 修复闲鱼操作台暂停/恢复测试读取本机历史库存缓存的问题：测试现在显式模拟冷缓存、只读刷新后库存就绪、真实小额单严格门未通过三个状态，干净 CI 与开发机得到相同阻断顺序；生产预检逻辑不变。
- 本机发布重启证实 OpenClaw Weixin 上游通道首次连接可让 Gateway 在 socket 已监听后约 230 秒才进入 `gateway ready`；健康检查在此期间保持失败，超时降级后 `/health` 恢复毫秒级 200。部署验收改以 ready/HTTP 真值等待，不以 PID 或固定短延迟判断成功。
- 依赖安全门发现并修复生产 PostCSS 路径穿越公告（`8.5.15 → 8.5.25`）及 `json-repair` 资源消耗公告（`0.30.3 → 0.60.1`）；同步更新桌面开发工具链同主版本安全 overrides，使全量 `npm audit` 回到 0；桌面 CI 同时纳入 Social 最终确认静态合同。
- LiteLLM 路由把 G4F、Kiro 和 Ollama 改为显式启用，缺必填 Key 的 provider 不再注入 `dummy` deployment；IBKR 未启用时不建立券商连接、不注册成交/撤单/资金/健康定时任务。自动健康检查改为核验核心 LaunchAgent 的 `running + PID`、18789/18790/18800 真实端点和公网只读巡检，并把禁用的可选服务标记为正常隔离状态。
- 桌面打包入口改为事务式安装：构建前先把 `/Applications` 中三个历史 App 名称备份并清理，构建或安装失败自动恢复旧版，成功后保证只保留 `OpenClaw.app`。删除已被内联 LaunchAgent 取代且全仓零引用的 `gateway-launcher.sh`；G4F/Kiro 启动器因仍被桌面服务管理调用而保留。
- Release Gate 2.0 六维评分为架构 8.3、代码质量 8.2、测试工程 8.8、安全 8.6、可靠性 8.3、运维发布 8.4，综合 8.4；六维均达到 8 分。评分只覆盖当前 macOS/Oracle 内测拓扑，不把 Developer ID/公证、Windows 实机或正式公开售卖算作完成。
### 文件变更
- `.github/workflows/ci.yml`, `Makefile` — 收紧远端与本地 CI 门禁。
- `apps/frist-api/server/`, `apps/frist-api/src/`, `apps/frist-api/tests/`, `apps/frist-api/deploy/production.env.example`, `scripts/frist_api_newapi_ownership_map.mjs`, `docker-compose.frist-api.yml` — 多租户、前后端双单位额度、创建补偿、显式历史归属、会话和回归测试。
- `apps/openclaw-manager-src/` — Gateway Token、配置原子写入、服务进程所有权、日志、Capability 安全边界、Rust/JavaScript Tauri 版本锁定和 macOS ad-hoc bundle 签名。
- `apps/openclaw-manager-src/package.json`, `apps/openclaw-manager-src/package-lock.json`, `packages/clawbot/requirements.txt` — 依赖安全下限与锁文件更新。
- `packages/clawbot/src/`, `packages/clawbot/multi_main.py`, `packages/clawbot/tests/` — Telegram、工具沙箱、交易、DAG、社媒发布门和针对性回归。
- `scripts/auto_health_check.sh`, `scripts/auto_ops_scripts.test.mjs`, `scripts/tauri_build_install.sh`, `tools/launchagents/` — 运行时真值、可选能力开关、桌面事务安装和冗余清理。
- `docs/001-project-map.md`, `docs/002-changelog.md`, `docs/004-architecture.md`, `docs/006-registries.md`, `docs/007-operations.md`, `docs/009-health.md` — 同步架构、评分、注册表、风险与上线边界。
### 验证
- 最终 `make ci-local` 退出码 0：Ruff 通过；Python 收集 `2182` 项并跑到 `[100%]`、0 失败、2 项预期跳过；Python 全源码语法通过；Frist-API `200 passed / 0 failed / 0 skipped`；桌面安全/Social/运维合同 `20 passed / 0 failed`；TypeScript 通过；锁定依赖下 Rust `34 passed / 0 failed` 且 `cargo check --locked`、`cargo fmt --check` 通过；`docs-check` 为 22 份文档全部合规。
- 桌面与 Frist 生产依赖 `npm audit --omit=dev`、项目 Python 3.12 的 `pip-audit` 均为 0 已知漏洞，`pip check` 无依赖冲突。
- 独立安全复核结论为当前审查范围无剩余 P0/P1。`gitleaks --pre-commit` 无泄漏，CI YAML 可解析，`git diff --check` 通过；Playwright 在标准 Vite 1420 端口验证首屏 0 console error，主界面在无 Token 时按预期 fail-closed，真实桌面实装在部署阶段复验。
### 部署与回滚证据
- 本机五个可选能力已显式关闭，G4F/Kiro/heartbeat 三个失败 LaunchAgent 已卸载；Bot/Gateway 重启后健康检查 `ok=true, release_ready=true`，新日志没有未关闭 session 或 IBKR 重连。Weixin 首连让 Gateway ready 延迟约 230 秒，已登记 HI-926，稳定后 `/health` 为毫秒级 200。
- `make tauri-build` 最终成功生成并安装唯一 `/Applications/OpenClaw.app`；Bundle ID `com.openclaw.manager`、arm64、ad-hoc sealed resources 和严格 `codesign` 均通过。Computer Use 实机首页非空、已连接、无重叠或凭据显示；本机临时验收截图为 `output/playwright/openclaw-app-deployed.png`，属于可再生成且不纳入 Git 的证据。
- Oracle 在 `/opt/frist-api/releases/8736484/repo` staging 的 Node 18 全量测试为 `200/200`；回滚包 `/opt/frist-api/backups/release-gate2-20260803T064021Z` 已校验。部署后 Frist/New-API/Apache active，3180/13000/公网均 200，未授权模型入口 401，SQLite 与源码漂移正常，新增 failed unit/错误均为 0；额度 7200、owner 0、历史无限 Token 9/9 保持不变。
### 上线边界
- 代码已部署到本机 Bot/桌面和 Oracle Frist，但发布口径仍是内部 macOS/Oracle 内测。生产 Token 1–9 仍为 `unlimited_quota=1` 并由主域 New-API 原生用户额度承接；它们没有映射进 Frist，也未禁用或迁移。只有未来先经单独批准把某个 Token 转为明确有限正额度后，才可重新 dry-run/申请 ownership apply。桌面 App 为 ad-hoc 内测签名，不是 Apple Developer ID/公证公开发行版。

## [2026-07-08] 微信控制权限医生深度诊断与权限页引导
> 领域: `infra` | `docs`
> 影响模块: `Weixin ClawBot`, `Computer Use`, `Intel Brief`
> 关联问题: HI-wechat-control-permission
### 变更内容
- 补强 `scripts/wechat_control_doctor.sh`：支持 `--deep` 深度探针，分别判断全屏截图、微信单窗口截图、macOS 辅助功能内部控件和输入框是否可见。
- 诊断同时读取 Codex 主程序和 OpenAI Computer Use 辅助进程的屏幕录制授权记录，避免系统设置里只勾 Codex、漏掉辅助进程。
- 微信存在多个浮窗时，医生会选择面积最大的微信窗口做判断，避免误抓小浮窗导致“没有主窗口”的假结论。
- 诊断口径从“可能没权限”收口为更准确的三层判断：系统全屏截图可用、微信单窗口截图被拒绝、微信辅助功能只暴露标题栏按钮而不暴露聊天输入框。
- 新增 `--open-permissions` 参数：一键打开 macOS 屏幕录制、辅助功能和自动化权限页，方便老板手动勾选 Codex / WeChat / Terminal；脚本不直接修改系统隐私开关。
- 当前实机结论：Codex 辅助功能和 Apple Events 自动化授权可用，WeChat 能被拉到前台；但微信主窗口 `kCGWindowSharingState=0` 且 AX 输入框数量为 0，不能安全用 Computer Use 视觉接管微信聊天，继续禁止坐标盲发。
### 文件变更
- `scripts/wechat_control_doctor.sh` — 增加参数解析、AX 深度探针、微信单窗口截图探针、全屏截图探针和更细的 JSON 字段。
- `docs/002-changelog.md` / `docs/007-operations.md` / `docs/009-health.md` — 同步权限诊断结论、老板操作步骤和边界。
### 验证
- 语法检查：`bash -n scripts/wechat_control_doctor.sh` 通过。
- 实机深度诊断：`scripts/wechat_control_doctor.sh --json --deep` 输出 `status=blocked_by_wechat_capture_protection`、`fullscreen_capture_ok=1`、`window_capture_ok=0`、`ax_content_visible=0`、`ax_editable_count=0`。
- 权限页引导：`scripts/wechat_control_doctor.sh --open-permissions` 已能打开 macOS 隐私权限页，并再次输出同一根因。

## [2026-07-08] Weixin 每日简报真实桥接脱敏证据验收器
> 领域: `backend` | `infra` | `docs`
> 影响模块: `Intel Brief`, `OpenClaw Weixin 插件`, `微信真实入站验收`
> 关联问题: HI-wechat-bridge-runtime-evidence
### 变更内容
- 给 OpenClaw Weixin 每日简报插件桥增加脱敏运行证据文件：真实微信入站快捷词命中后，插件会记录是否调用 `/wechat/incoming`、HTTP 状态、回复是否存在、是否已回发微信、是否疑似落入 LLM。
- 证据文件不保存微信聊天原文、不保存原始用户 ID、不保存 Token，只保存快捷词类型、文本长度、sender hash、回复特征和状态。
- 新增 `intel_wechat_bridge_runtime_acceptance.py`：老板或 Codex 在真实微信发送 `今日简报` / `700` 后运行该脚本，即可判断最近一次真实入站是否完成“微信 → 插件桥 → 本机处理器 → 回发微信”的闭环。
- 验收器新增等待模式：`--wait-seconds 120 --poll-seconds 2`，可以开着等老板发微信，自动轮询到 `verified=true` 或明确超时。
- 当前已重启 OpenClaw Gateway；`openclaw-weixin` 通道仍为 `enabled, configured, running`。由于本轮没有新的真实微信入站消息，默认验收报告按预期显示 `verified=false`、blocker 为“未找到微信桥接证据文件”。
### 文件变更
- `.openclaw/extensions/openclaw-weixin/src/messaging/process-message.ts` — 插件桥新增脱敏证据写入、sender hash、快捷词分类和回发状态记录。
- `~/.openclaw/npm/projects/tencent-weixin-openclaw-weixin-7783ac86ba/node_modules/@tencent-weixin/openclaw-weixin/dist/src/messaging/process-message.js` — 当前实际加载产物同步证据写入逻辑。
- `packages/clawbot/scripts/intel_wechat_bridge_runtime_acceptance.py` — 新增真实微信桥接证据验收器。
- `packages/clawbot/tests/test_intel_wechat_bridge_runtime_acceptance.py` — 新增验收器回归测试。
- `docs/002-changelog.md` / `docs/006-registries.md` / `docs/007-operations.md` / `docs/009-health.md` — 同步验收命令、边界和运行证据口径。
### 验证
- 语法检查：`py_compile scripts/intel_wechat_bridge_runtime_acceptance.py tests/test_intel_wechat_bridge_runtime_acceptance.py` 通过。
- 单测：`tests/test_intel_wechat_bridge_runtime_acceptance.py` 为 `5 passed`。
- 插件产物语法：`node --check ~/.openclaw/.../process-message.js` 通过。
- 运行态：`openclaw gateway restart` 后 `openclaw channels status --channel openclaw-weixin --probe` 显示 `enabled, configured, running`。
- 默认真实证据验收：`intel_wechat_bridge_runtime_acceptance.py` 输出 `verified=false`，唯一 blocker 是还没有新的真实微信桥接证据文件，符合当前未能视觉代发微信消息的边界。
- 等待模式验收：`--wait-seconds 1 --poll-seconds 0.2` 输出 `timed_out=true`，blocker 明确包含“等待 1 秒后仍未看到新的真实微信桥接成功证据”。

## [2026-07-08] 微信每日简报中文快捷词与两步式跳转修复
> 领域: `backend` | `infra` | `docs`
> 影响模块: `Intel Brief`, `微信编号菜单`, `OpenClaw Weixin 插件`
> 关联问题: HI-wechat-intel-shortcuts
### 变更内容
- 修复 Weixin 插件桥已拦截“今日简报/我的订阅”，但本机 `/wechat/incoming` 未识别中文快捷词、会落入普通 LLM 闲聊的问题。
- 微信每日简报入口现在同时支持数字和中文：`今日简报/每日简报/我的订阅/订阅状态/市场资金/AI科技/天气预警/推送时间/添加追踪/暂停简报`，并支持 `推送时间 09:00`、`添加追踪 英伟达` 这类人话格式。
- 修复两步式设置中的误吃参数：用户发 `705` 或 `706` 后，如果下一条回复“菜单/今日简报”，系统会跳转对应入口并清理 pending 状态，不再把“菜单”当推送时间或把“今日简报”当追踪词。
- OpenClaw Weixin 插件桥的快捷词白名单同步扩展到上述中文入口；已同步源码和当前实际加载的 dist 产物，并重启 Gateway 生效。
- 真实库 live 验证使用的临时微信测试用户已清理，未保留测试订阅、偏好或追踪污染。
### 文件变更
- `packages/clawbot/src/api/routers/wechat.py` — 新增微信每日简报中文快捷词解析，并让显式菜单/快捷词打断两步式 pending。
- `packages/clawbot/tests/test_wechat_numbered_commands.py` — 增加中文快捷词不落 LLM、pending 中回复菜单/今日简报不误吃参数的回归测试。
- `packages/clawbot/scripts/intel_wechat_user_journey_acceptance.py` — 微信用户旅程验收扩展到 18 步，覆盖中文快捷词和两步式中途跳转。
- `.openclaw/extensions/openclaw-weixin/src/messaging/process-message.ts` 与当前加载的 `~/.openclaw/.../process-message.js` — 扩展每日简报桥接快捷词。
- `docs/002-changelog.md` / `docs/006-registries.md` / `docs/009-health.md` — 同步命令注册、证据和真实边界。
### 验证
- 先写失败测试：`今日简报` 原本会调用 LLM，测试报错 `微信每日简报快捷入口不应该调用 LLM`。
- 语法检查：`py_compile` 通过；当前 OpenClaw Weixin dist `node --check` 通过。
- 回归：`cd packages/clawbot && .venv312/bin/python -m pytest tests/test_wechat_numbered_commands.py tests/test_intel_multichannel_numbered_menu.py --tb=short -q`：`11 passed`。
- 用户旅程验收：`intel_wechat_user_journey_acceptance.py` 输出 `verified=true`、`passed_steps=18`、`failed_steps=[]`、`real_wechat_network_calls=0`。
- Live HTTP 复验：POST `/wechat/incoming` 覆盖 `菜单 → 今日简报 → 我的订阅 → 705 → 菜单 → 705 → 2 → 706 → 今日简报 → 706 → 英伟达 → 708 → 701 → 702 → 701`，全部 HTTP 200，未落 LLM；测试用户随后已从生产库清理。
- OpenClaw Weixin：`openclaw channels status --channel openclaw-weixin --probe` 显示 `enabled, configured, running`。

## [2026-07-08] 微信桌面控制权限诊断与防误发收口
> 领域: `infra` | `docs`
> 影响模块: `Weixin ClawBot`, `Computer Use`, `Intel Brief`
> 关联问题: HI-wechat-control-permission
### 变更内容
- 新增微信控制诊断脚本，只做权限、前台窗口、窗口共享状态检查，不发送微信消息、不修改系统设置。
- 诊断确认本机 Codex 已具备 Apple Events 自动化授权，System Events 辅助功能可用，且能把 WeChat 拉到前台；但微信主窗口 `kCGWindowSharingState=0`，表示窗口禁止被截图/读取。
- 因微信窗口内容对截图/视觉控制不可见，当前不再用坐标盲点代替用户发送测试消息，避免误发到错误会话或重复发送。
- 后续真实微信验收优先走 OpenClaw Weixin 插件桥的入站处理与日志证据；若必须视觉接管，需要老板手动关闭微信防截图/隐私保护或给 Codex 补齐屏幕录制授权后重跑诊断。
### 文件变更
- `scripts/wechat_control_doctor.sh` — 新增微信控制医生，输出 `blocked_by_wechat_capture_protection`、权限状态、前台应用和窗口坐标。
- `docs/002-changelog.md` / `docs/009-health.md` — 登记根因、边界和下一步。
### 验证
- 语法检查：`bash -n scripts/wechat_control_doctor.sh` 通过。
- 实机诊断：`scripts/wechat_control_doctor.sh --json` 输出 `status=blocked_by_wechat_capture_protection`、`ui_enabled=true`、`front_app=WeChat`、`wechat_onscreen=1`、`wechat_sharing_state=0`。

## [2026-07-08] 每日简报微信入站桥接与编号菜单闭环推进
> 领域: `backend` | `infra` | `docs`
> 影响模块: `Intel Brief`, `微信编号菜单`, `OpenClaw Weixin 插件`
> 关联问题: HI-intel-wechat-inbound-bridge
### 变更内容
- 修复本机微信转发兼容入口：每日简报微信处理器同时支持 `/api/v1/wechat/incoming` 和旧转发器路径 `/wechat/incoming`；兼容路径仍走全局 API Token 认证，不放松安全门。
- 修复微信编号菜单运行时使用固定远未来时间导致有效订阅被误判“未开通或已到期”的问题；运行时改用当前 UTC 时间判断订阅状态。
- 新增微信用户旅程验收脚本，覆盖 `菜单 → 700 → 701 → 705 两步式 → 706 两步式 → 708 暂停 → 702 恢复 → 701`，证据写入 `packages/clawbot/data/intel_evidence/phasefix/wechat-user-journey/acceptance.json`。
- 给当前实际加载的 OpenClaw Weixin 插件增加“每日简报编号菜单直通桥”：授权微信会话发送 `700-708`、`菜单`、`今日简报`、`我的订阅` 时，插件先调用本机 `/wechat/incoming` 并把回复直接发回微信，避免继续落入普通大模型闲聊。
- 重启本机 `ai.openclaw.clawbot-agent` 和 OpenClaw Gateway 后复验：18790 两个入口均返回每日简报菜单，OpenClaw Weixin 通道为 `enabled, configured, running`。
- 真实桌面微信自动输入测试受本机坐标/焦点限制，未能稳定代替用户在「Global Intelligence AI」会话发送 `700`；因此本轮不夸大为“真实微信入站消息已人工发送验收”，只声明处理器、插件桥和通道状态已就绪。
### 文件变更
- `packages/clawbot/src/api/server.py` — 挂载 `/wechat/incoming` 兼容路由。
- `packages/clawbot/src/api/routers/wechat.py` — 微信每日简报命令按当前 UTC 时间判断订阅。
- `packages/clawbot/scripts/intel_wechat_user_journey_acceptance.py` — 新增微信编号菜单用户旅程验收脚本。
- `packages/clawbot/tests/test_wechat_numbered_commands.py` / `packages/clawbot/tests/test_intel_commercial_mvp.py` — 补齐路由兼容与新 Telegram 命令菜单合同回归。
- `.openclaw/extensions/openclaw-weixin/src/messaging/process-message.ts` — 本仓库内 OpenClaw Weixin 插件源码补直通桥。
- `~/.openclaw/npm/projects/tencent-weixin-openclaw-weixin-7783ac86ba/node_modules/@tencent-weixin/openclaw-weixin/dist/src/messaging/process-message.js` — 当前实际加载的插件产物同步补直通桥并重启 Gateway 生效。
- `docs/002-changelog.md` / `docs/006-registries.md` / `docs/007-operations.md` / `docs/009-health.md` — 同步完成项、证据与剩余边界。
### 验证
- 语法检查：`python -m py_compile src/api/server.py src/api/routers/wechat.py scripts/intel_wechat_user_journey_acceptance.py tests/test_wechat_numbered_commands.py tests/test_intel_commercial_mvp.py` 通过。
- 针对性回归：`31 passed`（微信编号、跨渠道菜单、商业 MVP 菜单、Telegram 菜单用户旅程相关测试）。
- 全量后端回归：`cd packages/clawbot && .venv312/bin/python -m pytest tests/ --tb=no -q` exit 0，进度输出到 `[100%]`。
- 微信本地用户旅程验收：`intel_wechat_user_journey_acceptance.py` exit 0，`verified=true`，`passed_steps=12`，`real_wechat_network_calls=0`。
- Live HTTP 复验：带本机 API Token POST `/wechat/incoming` 和 `/api/v1/wechat/incoming`，两者 HTTP 200，均返回“🧭 今日简报 / 700 今日简报 / 701 我的订阅 ...”，不再把 `700` 当普通聊天。
- OpenClaw Weixin：`openclaw channels status --channel openclaw-weixin --probe` 显示 `enabled, configured, running`；`node --check` 当前实际插件产物通过。

## [2026-07-08] 每日简报点击优先菜单与业务故障转移方案收口
> 领域: `backend` | `infra` | `docs`
> 影响模块: `Intel Brief`, `Telegram 菜单`, `微信编号菜单`, `VPS 故障转移`
> 关联问题: HI-intel-menu-click-first-and-vps-failover
### 变更内容
- 将每日简报 Telegram 左侧命令菜单同步为点击优先的 10 个斜杠命令：`/start`、`/today`、`/status`、`/market`、`/ai`、`/weather`、`/schedule`、`/track`、`/pause`、`/help`，避免清理聊天记录后只剩旧命令或无菜单。
- 明确多端菜单原则：Telegram 这类支持点击的平台优先按钮/斜杠菜单；微信这类不支持点击命令菜单的平台才使用 `700-708` 数字编号降级。
- 推送时间新增小白两步式：用户发 `/schedule` 或 `705` 后，可以下一条回复 `1-5` 快速选择，也可回复 `每周 09:00` / `705 07:30`。
- 微信端数字降级补齐两步式：`705 → 2` 可设置推送时间，`706 → 名字` 可添加追踪；但当前只完成代码层和本地回归，未宣称微信真实闭环。
- 调研 `/Users/blackdj/Documents/VPS-Config` 后登记当前 CC中转部署位置与故障转移建议：主生产在 Oracle ARM-1 `150.136.73.15`，Oracle ARM-2 `129.213.33.101` 可作为温备候选；推荐“Cloudflare 切入口 + 主备同步 + 双入口单数据库”，不建议 Telegram/微信消息流互相同步。
### 文件变更
- `packages/clawbot/src/intel/subscriptions.py` — Telegram BotCommand 更新为点击优先命令清单。
- `packages/clawbot/src/intel/channel_menu.py` / `packages/clawbot/src/intel/telegram_menu.py` — 补齐 `/today`、`/market`、`/ai`、`/weather`、`/track`、`/pause` 和两步式时间设置路径。
- `packages/clawbot/src/api/routers/wechat.py` — 微信编号命令增加 `705/706` pending action。
- `packages/clawbot/scripts/intel_telegram_user_journey_acceptance.py` — 用户旅程验收扩展到 14 步。
- `docs/002-changelog.md` / `docs/006-registries.md` / `docs/007-operations.md` / `docs/009-health.md` — 同步菜单边界、微信登录态结论和 VPS 故障转移方案。
### 验证
- Telegram Bot API 真实同步：`intel_telegram_bot_runtime_probe.py` 输出 `status=success`、`set_my_commands_success=true`、`network_calls=2`，证据文件记录 `command_count=10` 且 `setMyCommands.success=true`。
- 常驻监听器：`launchctl` 为 running，心跳 `last_status=no_new_updates`、`raw_updates_persisted=false`。
- 用户旅程验收：`intel_telegram_user_journey_acceptance.py` 输出 `verified=true`、`passed_steps=14/14`、`failed_steps=0`、`real_telegram_network_calls=0`。
- 针对性回归：`cd packages/clawbot && .venv312/bin/python -m pytest tests/test_intel_telegram_user_journey_acceptance.py tests/test_intel_telegram_menu_handlers.py tests/test_intel_telegram_runtime.py tests/test_intel_telegram_update_processor.py tests/test_intel_telegram_update_daemon.py tests/test_intel_telegram_bot_runtime.py tests/test_intel_multichannel_numbered_menu.py tests/test_wechat_numbered_commands.py tests/test_wechat_bridge.py --tb=short -q --maxfail=5`：`42 passed`。
- 微信旧登录态只读探测：本机凭证文件存在且 `token_present=true`、`userId_present=true`，但 iLink `getconfig` 返回 `ret=-4`，`context_token_obtained=false`，需要重新扫码后才能真实接管测试。

## [2026-07-08] 每日简报 Telegram 真人两步式追踪优化
> 领域: `backend` | `docs`
> 影响模块: `Intel Brief`, `Telegram 菜单`, `Telegram 用户旅程验收`
> 关联问题: HI-intel-telegram-real-user-journey
### 变更内容
- 接管本机 Telegram 站在普通用户视角真实发送 `700/701/705/706/708/702/707`，确认菜单、今日简报、订阅状态、改时间、暂停/恢复和帮助入口可用。
- 发现 `706` 空关键词虽然能提示格式，但对小白用户仍要求记完整命令；已优化为两步式：先发 `706` 或点“添加追踪”，下一条直接回复名字即可添加追踪。
- 新增 Telegram pending action 状态表，保存“下一条消息用于添加追踪”的短暂状态；成功、取消或菜单命令都会清理，避免误吃后续正常搜索。
- 真实 Telegram 复测 `706 → Codex20260708` 已成功添加追踪；测试产生的 `NVIDIA/Codex20260708` 追踪对象已从生产库清理，真实订阅偏好恢复为 `ai_model_updates/akshare/senate_trading`、每天 08:30。
- 自动验收脚本新增“两步式添加追踪 706→周杰伦”步骤，后续回归会防止小白路径退化。
### 文件变更
- `packages/clawbot/src/intel/telegram_menu.py` — 新增两步式添加追踪状态、取消逻辑和统一成功回复。
- `packages/clawbot/src/intel/db/intel_brief_schema.sql` — 新增 `telegram_pending_actions` 表，兼容已有生产库按需创建。
- `packages/clawbot/scripts/intel_telegram_user_journey_acceptance.py` — 用户旅程验收从 9 步扩展到 10 步，覆盖两步式追踪。
- `packages/clawbot/tests/test_intel_telegram_menu_handlers.py` / `packages/clawbot/tests/test_intel_telegram_user_journey_acceptance.py` — 增加回归保护。
- `docs/002-changelog.md` / `docs/006-registries.md` / `docs/009-health.md` — 同步真人实测结论、边界和验证证据。
### 验证
- 真实 Telegram：`700` 返回今日简报，`701` 显示订阅状态，`705 09:00` 改时间成功，`706 NVIDIA` 成功添加追踪，`708` 暂停成功，暂停后 `701` 不偷偷恢复，`702` 恢复成功，`707` 打开帮助菜单。
- 真实 Telegram 新路径：`706` 后机器人提示“下一条直接回复名字就行”，下一条 `Codex20260708` 被正确添加追踪；测试数据已清理。
- 监听器：`launchctl print gui/$(id -u)/ai.openclaw.intel-brief.telegram-listener` 显示 `state = running`，心跳 `raw_updates_persisted=false`。
- 针对性回归：`packages/clawbot/.venv312/bin/python -m pytest ...`（Telegram/Intel Brief 相关 9 个测试文件）通过。
- 用户旅程验收：`intel_telegram_user_journey_acceptance.py` 输出 `verified=true`、`passed_steps=10/10`、`real_telegram_network_calls=0`。

## [2026-07-08] 每日简报 Telegram 用户旅程闭环体验修正
> 领域: `backend` | `docs`
> 影响模块: `Intel Brief`, `Telegram 菜单`, `Telegram 用户旅程验收`
> 关联问题: HI-intel-brief-user-journey-closure
### 变更内容
- 从普通用户视角补齐菜单后续体验，不再只把 `/start` 能回菜单当成闭环。
- 底部常驻快捷键从“功能导航/热搜排行”改成更直接的“今日简报/我的订阅”，减少用户思考成本。
- 修复“点今日简报又回菜单”的体验断点：旧文字快捷键 `🧭 今日简报` 现在和按钮 callback `today` 一样，优先返回最近一次成功简报。
- 修复 `708 暂停简报` 写在菜单里但路由没接上的问题；暂停后，用户查看状态或打开菜单不会偷偷恢复，只有重新选择内容/添加追踪时才恢复推送。
- 优化推送时间输入：普通用户发 `/schedule 09:00` 会正确设置为每天 09:00，不再误把 `09:00` 当成推送频率。
- 新增普通用户完整旅程验收器，覆盖 `/start → 今日简报 → 我的订阅 → 改时间 → 添加追踪 → 暂停 → 暂停后查看/打开菜单 → 选择内容恢复`。
### 文件变更
- `packages/clawbot/src/intel/channel_menu.py` — 补齐 `708`/暂停路由、快捷键映射、暂停态不被被动查询恢复。
- `packages/clawbot/src/intel/subscriptions.py` — 底部常驻键盘改成“今日简报/我的订阅”，订阅状态显式保留 `paused`。
- `packages/clawbot/src/intel/telegram_menu.py` — 透传暂停/时间/最近简报等验收状态，兼容 `/schedule 09:00`。
- `packages/clawbot/scripts/intel_telegram_user_journey_acceptance.py` — 新增普通用户旅程验收器。
- `packages/clawbot/tests/test_intel_telegram_user_journey_acceptance.py` / `packages/clawbot/tests/test_intel_telegram_menu_handlers.py` / `packages/clawbot/tests/test_intel_telegram_runtime.py` — 增加并更新用户旅程回归测试。
- `docs/002-changelog.md` / `docs/006-registries.md` / `docs/009-health.md` — 同步本轮体验闭环和边界。
### 验证
- 新增保护测试先红后绿：`/schedule 09:00`、`🧭 今日简报`、`708 暂停后不被 /start/701 偷偷恢复`。
- 语法检查：`python3 -m py_compile packages/clawbot/src/intel/channel_menu.py packages/clawbot/src/intel/subscriptions.py packages/clawbot/src/intel/telegram_menu.py packages/clawbot/scripts/intel_telegram_user_journey_acceptance.py packages/clawbot/tests/test_intel_telegram_user_journey_acceptance.py`：exit 0。
- 针对性回归：`packages/clawbot/.venv312/bin/python -m pytest packages/clawbot/tests/test_intel_telegram_user_journey_acceptance.py packages/clawbot/tests/test_intel_telegram_menu_handlers.py packages/clawbot/tests/test_intel_multichannel_numbered_menu.py packages/clawbot/tests/test_intel_commercial_mvp.py packages/clawbot/tests/test_intel_telegram_runtime.py packages/clawbot/tests/test_intel_telegram_update_processor.py packages/clawbot/tests/test_intel_telegram_update_daemon.py packages/clawbot/tests/test_intel_telegram_start_menu_acceptance.py --tb=short -q --maxfail=5`：`39 passed`。
- 用户旅程验收：`packages/clawbot/.venv312/bin/python packages/clawbot/scripts/intel_telegram_user_journey_acceptance.py --output packages/clawbot/data/intel_evidence/phasefix/telegram-user-journey/acceptance.json --db packages/clawbot/data/intel_evidence/phasefix/telegram-user-journey/acceptance.sqlite3`：`verified=true`、`passed_steps=9/9`、`real_telegram_network_calls=0`。

## [2026-07-08] 每日简报 Telegram 常驻菜单与多渠道数字命令收口
> 领域: `backend` | `docs`
> 影响模块: `Intel Brief`, `Telegram 菜单`, `微信编号命令`, `多渠道菜单协议`
> 关联问题: HI-intel-brief-menu-closure
### 变更内容
- 修复“清理 Telegram 聊天后 `/start` 没人回菜单”的根因：每日简报新增常驻 Telegram 更新监听器，LaunchAgent `ai.openclaw.intel-brief.telegram-listener` 当前为 running，并持续轮询新消息。
- 监听器心跳现在会保留最近一次 `/start` 菜单发送成功证据，不会被后续“无新消息”轮询覆盖；证据只保留成功时间、按钮是否发送、回复条数和脱敏布尔值，不保存聊天内容、chat id、用户 id 或 token。
- 新增 `/start` 真人验收器 `packages/clawbot/scripts/intel_telegram_start_menu_acceptance.py`：老板发完 `/start` 后，脚本自动输出 `verified=true/false` 和下一步，不需要老板看日志。
- Telegram 菜单从旧的配置表式按钮收口为用户能直接理解的产品菜单：今日简报、我的订阅、市场资金、AI科技、天气预警、推送时间、添加追踪、帮助；同时支持直接回复 700-708 数字命令。
- 微信端已接入 700-708 数字回复入口，用户发 `700` 可打开每日简报，发 `706 英伟达` 可添加追踪；该入口走本地每日简报逻辑，不落到 LLM 兜底。
- 飞书/钉钉当前只完成统一菜单合同和数字命令协议；由于没有真实 webhook/token/回调入口，本轮不声明真实闭环。
- `700 今日简报` 不再只弹菜单，会优先读取该用户最近一次成功投递的简报；没有记录时才提示下一次推送和菜单。
- 本轮复核发现生产库曾被临时测试写入偏好/追踪，已清理回真实用户原始偏好，避免测试污染老板真实订阅。
### 文件变更
- `packages/clawbot/src/intel/channel_menu.py` — 新增跨渠道菜单文案、700-708 数字命令和平台能力边界。
- `packages/clawbot/src/intel/subscriptions.py` — Telegram `/start` 菜单合同改为新的产品化菜单。
- `packages/clawbot/src/intel/telegram_menu.py` — Telegram 按钮、旧按钮兼容和数字命令入口接入。
- `packages/clawbot/src/api/routers/wechat.py` — 微信 700-708 编号命令接入每日简报逻辑。
- `packages/clawbot/scripts/intel_telegram_update_daemon.py` — 每日简报 Telegram 常驻监听器，心跳保留最近一次 `/start` 菜单成功证据。
- `packages/clawbot/scripts/intel_telegram_start_menu_acceptance.py` — 新增真人 `/start` 菜单验收器。
- `packages/clawbot/tests/test_intel_telegram_start_menu_acceptance.py` / `packages/clawbot/tests/test_intel_telegram_update_daemon.py` — 覆盖验收器和心跳成功证据不被覆盖。
- `docs/002-changelog.md` / `docs/006-registries.md` / `docs/009-health.md` — 登记真实完成项与未完成边界。
### 验证
- `launchctl print gui/$(id -u)/ai.openclaw.intel-brief.telegram-listener`：`state = running`。
- 心跳文件 `packages/clawbot/data/intel_evidence/phasefix/telegram-listener/heartbeat.json`：`last_status=no_new_updates`、`raw_updates_persisted=false`，说明监听器在轮询且不保存原始聊天内容。
- Bot API `getMe` 已确认每日简报机器人为 `@carven_Jianbao_bot`，直达链接为 `https://t.me/carven_Jianbao_bot?start=start`；`getMyCommands` 已确认 `/start` 命令存在。
- 老板本人向 `@carven_Jianbao_bot` 发送 `/start` 后，真人验收器输出 `verified=true`、`listener_fresh=true`、`blockers=[]`；证据显示菜单发送时间为 `2026-07-08T17:44:43.993878+00:00`，已发送 inline 按钮菜单和常驻键盘，共 2 条回复。
- 生产库只保留真实 Telegram 用户偏好：`ai_model_updates`、`akshare`、`senate_trading`；最近 `delivery_log` 有真实 Telegram success 记录。
- 针对性回归：`packages/clawbot/.venv312/bin/python -m pytest packages/clawbot/tests/test_intel_telegram_update_daemon.py packages/clawbot/tests/test_intel_telegram_start_menu_acceptance.py packages/clawbot/tests/test_intel_telegram_real_update_runner.py packages/clawbot/tests/test_intel_telegram_update_processor.py packages/clawbot/tests/test_intel_telegram_runtime.py packages/clawbot/tests/test_intel_telegram_menu_handlers.py packages/clawbot/tests/test_intel_multichannel_numbered_menu.py packages/clawbot/tests/test_intel_commercial_mvp.py packages/clawbot/tests/test_wechat_numbered_commands.py --tb=short -q --maxfail=5`：`42 passed`。

## [2026-07-08] 自动发货恢复与首单观察开启
> 领域: `xianyu` | `docs`
> 影响模块: `CC中转操作台`, `CC中转自动发货`, `CC中转售卖锁`
> 关联问题: HI-cc-auto-ship-restored
### 变更内容
- 按老板明确指令“恢复自动发货”，先执行恢复前安全检查，确认 `safe_to_resume=true`、`blockers=[]` 后，恢复常驻自动发货开关。
- 恢复后系统自动开启首单观察保险：下一笔真实发卡进入 `message_sent` 后，会自动暂停一次，防止重复发卡事故复发。
- 当前正式售卖锁已放行：`can_public_sale=true`、`state=public_sale_unlocked`，补救队列为 0，首页显示“正式售卖已放行 / 自动发货开着”。
- 本轮只恢复运营开关，不主动点击闲鱼发货按钮，不额外发送卡密。
### 文件变更
- `docs/002-changelog.md` / `docs/009-health.md` — 登记本次恢复动作、live 复验状态和截图证据。
### 验证
- `GET /api/cc-operator-mode/resume-preflight`：`safe_to_resume=true`、`blockers=[]`。
- `POST /api/cc-operator-mode`：`auto_ship_paused=false`、`auto_resume_canary_active=true`、`can_auto_ship_paid_orders=true`。
- `GET /api/cc-public-sale-lock?refresh=true`：`can_public_sale=true`、`state=public_sale_unlocked`、`blockers=[]`。
- Playwright 截图：`output/playwright/cc-ops-console-auto-ship-restored-20260708.png`，页面可见“正式售卖已放行 / 自动发货开着 / 补救 0 / 库存 36 张”。

## [2026-07-08] 恢复前安全检查自动刷新证据
> 领域: `xianyu` | `backend` | `docs`
> 影响模块: `XianyuAdmin`, `CC中转恢复预检`, `CC中转操作台`
> 关联问题: HI-cc-resume-preflight-auto-refresh
### 变更内容
- 恢复前安全检查现在会在库存/渠道证据冷启动为空时，自动跑一次只读上架锁刷新，不再要求老板先记住“刷新上架锁”这个额外步骤。
- 该刷新只读，不分配卡密、不发闲鱼消息、不点击发货、不恢复自动发货。
- 安全门没有放松：预检仍会检查 webhook、闲鱼在线/Cookie、补救队列、库存/兑换码/渠道、买家公网入口、CC Switch 入口和真实小额单严格门。
### 文件变更
- `packages/clawbot/src/xianyu/xianyu_admin.py` — `_cc_auto_ship_resume_preflight()` 在库存证据缺失时自动 `refresh=True` 只读刷新。
- `packages/clawbot/tests/test_api_routes_regression.py` — 增加恢复前预检自动刷新和不绕过严格门的回归断言。
- `docs/002-changelog.md` / `docs/009-health.md` — 同步 live 复验结果。
### 验证
- 先写失败用例：`test_xianyu_resume_preflight_refreshes_inventory_when_cache_cold` 初次失败为 `assert [] == ['refresh']`，证明旧逻辑不会自动刷新。
- `python3 -m py_compile packages/clawbot/src/xianyu/xianyu_admin.py packages/clawbot/tests/test_api_routes_regression.py`：exit 0。
- `node --check /tmp/cc_ops_console_inline.js`：exit 0。
- `cd packages/clawbot && .venv312/bin/python -m pytest tests/test_api_routes_regression.py::test_xianyu_resume_preflight_refreshes_inventory_when_cache_cold tests/test_api_routes_regression.py::test_xianyu_operator_mode_can_pause_auto_ship tests/test_api_routes_regression.py::test_xianyu_ops_snapshot_uses_precheck_when_inventory_cache_cold tests/test_api_routes_regression.py::test_xianyu_ops_snapshot_treats_pause_after_strict_gate_as_healthy tests/test_api_routes_regression.py::test_xianyu_operator_next_action_treats_pause_after_strict_gate_as_resume_prompt tests/test_api_routes_regression.py::test_xianyu_admin_public_sale_lock_explains_manual_pause_after_strict_gate tests/test_api_routes_regression.py::test_xianyu_admin_page_escapes_dynamic_fields tests/test_xianyu_cc_auto_ship.py::test_cc_shipment_summary_excludes_skipped_manual_confirm_from_page_pending --tb=short -q`：`8 passed`。
- 重启本机 `ai.openclaw.xianyu` 后 live 只读复验：`/api/cc-operator-mode/resume-preflight` 返回 `safe_to_resume=true`、`refreshed_inventory=true`、`blockers=[]`；`/api/cc-operator-mode` 仍为 `auto_ship_paused=true`、`one_shot_active=false`、`auto_resume_canary_active=false`。

## [2026-07-08] 18800 冷启动暂停保护口径修正
> 领域: `xianyu` | `backend` | `docs`
> 影响模块: `XianyuAdmin`, `CC中转操作台`, `CC中转运营快照`
> 关联问题: HI-cc-paused-strict-gate-cold-start
### 变更内容
- 修复 18800 服务重启后库存/渠道证据缓存未刷新时，总快照短暂把“严格门已通过但自动发货暂停保护”误报成 `auto_ship_not_ready/danger` 的问题。
- 售卖锁现在在严格门已过、补救队列清零、买家入口和 CC Switch 基础项正常、仅库存证据缓存冷启动时，会展示为 `paused_after_strict_gate`，老板看到的是“待恢复自动发货”，不是“系统故障”。
- 总快照 `ok` 现在把 `paused_after_strict_gate` / `paused_internal_test_ready` 视为健康待恢复态；`/api/cc-operator-next-action` 同步返回 `severity=warning`。
- 恢复自动发货预检没有放松：冷启动时仍会提示“库存/渠道证据未刷新，先点刷新上架锁”，不会直接恢复常驻自动发货。
### 文件变更
- `packages/clawbot/src/xianyu/xianyu_admin.py` — 合并暂停保护展示态，修正总快照 ok 和下一步提示。
- `packages/clawbot/tests/test_api_routes_regression.py` — 增加冷启动暂停保护、总快照健康态和下一步提示回归测试。
- `docs/002-changelog.md` / `docs/009-health.md` — 同步 live 复验结果。
### 验证
- 先写失败用例：`test_xianyu_ops_snapshot_uses_precheck_when_inventory_cache_cold` 初次失败为 `assert False is True`，证明冷启动会误报。
- 先写失败用例：`test_xianyu_operator_next_action_treats_pause_after_strict_gate_as_resume_prompt` 初次失败为 `auto_ship_not_ready != paused_after_strict_gate`。
- `node --check /tmp/cc_ops_console_inline.js`：exit 0。
- `cd packages/clawbot && .venv312/bin/python -m pytest tests/test_api_routes_regression.py::test_xianyu_ops_snapshot_uses_precheck_when_inventory_cache_cold tests/test_api_routes_regression.py::test_xianyu_ops_snapshot_treats_pause_after_strict_gate_as_healthy tests/test_api_routes_regression.py::test_xianyu_operator_next_action_treats_pause_after_strict_gate_as_resume_prompt tests/test_api_routes_regression.py::test_xianyu_operator_next_action_waits_for_inventory_evidence tests/test_api_routes_regression.py::test_xianyu_admin_public_sale_lock_explains_manual_pause_after_strict_gate tests/test_api_routes_regression.py::test_xianyu_admin_public_sale_lock_blocks_bad_buyer_entry tests/test_api_routes_regression.py::test_xianyu_admin_public_sale_lock_blocks_bad_ccswitch_entry tests/test_api_routes_regression.py::test_xianyu_admin_page_escapes_dynamic_fields tests/test_xianyu_cc_auto_ship.py::test_cc_shipment_summary_excludes_skipped_manual_confirm_from_page_pending --tb=short -q`：`9 passed`。
- 重启本机 `ai.openclaw.xianyu` 后 live 只读复验：`/api/cc-ops-snapshot.ok=true`、`next_state=paused_after_strict_gate`、`next_severity=warning`、`can_internal_test=true`、`can_public_sale=false`；`/api/cc-operator-mode` 仍为 `auto_ship_paused=true`、`one_shot_active=false`、`auto_resume_canary_active=false`。

## [2026-07-08] 闲鱼 skipped 发货确认假告警修正
> 领域: `xianyu` | `frontend` | `docs`
> 影响模块: `XianyuContext`, `XianyuAdmin`, `CC中转操作台`
> 关联问题: HI-cc-skipped-confirm-false-alert
### 变更内容
- 修复旧手工/浏览器内测单 `xianyu_confirm_status=skipped` 仍被计入“待点发货”的假告警。
- 后端 `cc_shipment_summary()` 的 `xianyu_confirm_page_pending` 现在排除 `confirmed` 和 `skipped`，老板首页不会再显示无需处理的旧内测单。
- 18800 补救队列表格同步排除 `skipped`，避免把“已明确跳过确认发货”的记录展示成“已发卡密，待页面点击发货”。
- 该改动只修正看板和队列显示，不发卡、不点击闲鱼发货、不恢复自动发货。
### 文件变更
- `packages/clawbot/src/xianyu/xianyu_context.py` — 修正 skipped 确认发货统计口径。
- `packages/clawbot/src/xianyu/xianyu_admin.py` — 前端补救队列表格排除 skipped。
- `packages/clawbot/tests/test_xianyu_cc_auto_ship.py` / `packages/clawbot/tests/test_api_routes_regression.py` — 增加 skipped 不产生待发货假告警的回归测试。
- `docs/002-changelog.md` / `docs/009-health.md` — 同步本轮假告警修复。
### 验证
- 先写失败用例：`test_cc_shipment_summary_excludes_skipped_manual_confirm_from_page_pending` 初次失败为 `assert 1 == 0`，证明旧逻辑会把 skipped 计入待点发货。
- `python3 -m py_compile packages/clawbot/src/xianyu/xianyu_context.py packages/clawbot/src/xianyu/xianyu_admin.py packages/clawbot/tests/test_xianyu_cc_auto_ship.py packages/clawbot/tests/test_api_routes_regression.py`：exit 0。
- `node --check /tmp/cc_ops_console_inline.js`：exit 0。
- `cd packages/clawbot && .venv312/bin/python -m pytest tests/test_xianyu_cc_auto_ship.py tests/test_api_routes_regression.py::test_xianyu_admin_page_escapes_dynamic_fields --tb=short -q`：`121 passed`。
- 重启本机 `ai.openclaw.xianyu` 后 live 只读复验：`pending_rescue=0`、`xianyu_confirm_page_pending=0`、`xianyu_confirm_pending=0`、`xianyu_confirm_failed=0`；自动发货仍为 `auto_ship_paused=true`、`one_shot_active=false`。
- Playwright 截图：`output/playwright/cc-ops-console-skipped-confirm-false-alert-fixed-20260708.png`。

## [2026-07-08] 18800 layui 人工预检口径合并
> 领域: `xianyu` | `frontend` | `docs`
> 影响模块: `XianyuAdmin`, `CC中转操作台`
> 关联问题: HI-cc-owner-console-precheck-display
### 变更内容
- 确认 `layui/layui` 适合继续作为 18800 本机老板操作台的渐进式 UI 底座：使用本地静态资源，不走 CDN，不替换后端业务链路。
- 新增前端 `mergeLockWithPrecheck`：当人工预检 6/6 已通过且状态为“严格门已通过，自动发货暂停保护”时，首屏会按这个老板可理解口径显示，不再被旧售卖锁快照误导成“先别卖”。
- 该改动只修正看板展示，不发卡、不点击闲鱼发货、不恢复自动发货。
### 文件变更
- `packages/clawbot/src/xianyu/xianyu_admin.py` — 18800 页面合并人工预检证据与售卖锁展示口径。
- `packages/clawbot/tests/test_api_routes_regression.py` — 增加前端合并逻辑静态回归断言。
- `docs/002-changelog.md` / `docs/009-health.md` — 同步本轮 UI 收口和验证证据。
### 验证
- `python3 -m py_compile packages/clawbot/src/xianyu/xianyu_admin.py packages/clawbot/tests/test_api_routes_regression.py`：exit 0。
- `node --check /tmp/cc_ops_console_inline.js`：exit 0。
- `cd packages/clawbot && .venv312/bin/python -m pytest tests/test_api_routes_regression.py::test_xianyu_admin_page_escapes_dynamic_fields tests/test_api_routes_regression.py::test_xianyu_admin_public_sale_lock_refreshes_readonly_audit --tb=short -q`：`2 passed`。
- 重启本机 `ai.openclaw.xianyu` 后 live 只读复验：首页 HTTP 200，页面包含 `function mergeLockWithPrecheck`、`/static/layui/layui.js`、`人工预检证据`、`待你恢复自动发货`。
- live 安全态复验：`GET /api/cc-operator-mode` 仍为 `auto_ship_paused=true`、`one_shot_active=false`、`auto_resume_canary_active=false`；`GET /api/cc-manual-precheck-evidence` 为 `passed=6/6`、`state=paused_after_strict_gate`。
- Playwright 截图：`output/playwright/cc-ops-console-layui-precheck-merge-20260708.png`。

## [2026-07-08] 人工预检闭环证据接口
> 领域: `xianyu` | `backend` | `docs`
> 影响模块: `XianyuAdmin`, `CC中转操作台`, `Frist-API 用户页`
> 关联问题: HI-cc-manual-precheck-evidence
### 变更内容
- 新增只读接口 `GET /api/cc-manual-precheck-evidence`，把人工预检反馈拆成 6 项可验证证据：注册/登录 CF 位置、邮箱模板质感、闲鱼重复发卡保护、自动发货策略、1 元额度 1:1、真实小额单严格门。
- 接口只读取源码和当前运行态，不发卡、不点击闲鱼发货、不恢复自动发货，返回 `safety.read_only=true` 等安全边界。
- live 复验显示 `passed=6/6`、`precheck_ready=true`、`state=paused_after_strict_gate`、`state_label=严格门已通过，自动发货暂停保护`；`auto_ship_paused=true`、`one_shot_active=false`、`auto_resume_canary_active=false` 仍保持。
### 文件变更
- `packages/clawbot/src/xianyu/xianyu_admin.py` — 新增人工预检闭环证据汇总函数和只读 API。
- `packages/clawbot/tests/test_api_routes_regression.py` — 增加接口结构、6 项证据和安全边界回归断言。
- `docs/002-changelog.md` / `docs/006-registries.md` / `docs/009-health.md` — 同步新证据入口与 live 状态。
### 验证
- `python3 -m py_compile packages/clawbot/src/xianyu/xianyu_admin.py packages/clawbot/tests/test_api_routes_regression.py`：exit 0。
- `cd packages/clawbot && .venv312/bin/python -m pytest tests/test_api_routes_regression.py::test_xianyu_admin_public_sale_lock_refreshes_readonly_audit tests/test_api_routes_regression.py::test_xianyu_admin_page_escapes_dynamic_fields --tb=short -q`：`2 passed`。
- live 只读复验：`GET /api/cc-manual-precheck-evidence` 返回 `passed=6,total=6,precheck_ready=true,state=paused_after_strict_gate,missing=[]`；`GET /api/cc-operator-mode` 仍返回自动发货暂停、单次放行关闭、首单观察未激活。

## [2026-07-08] 注册登录 CF 位置与 1 元额度回归守护
> 领域: `frontend` | `backend` | `docs`
> 影响模块: `Frist-API 用户页`, `CC中转注册登录`, `CC中转卡密套餐`
> 关联问题: HI-cc-auth-turnstile-email-price-guard
### 变更内容
- 补强注册/登录页结构测试：Cloudflare Turnstile 不只要存在，还必须位于主登录卡片的登录/注册表单容器内，并在提交按钮上方，防止再次漂到页面底部。
- 补强本地样式守护：Turnstile 容器必须由本地 CSS 预留稳定高度，避免验证码加载后挤到页面底部或造成跳动。
- 复验邮件模板与 1 元额度链路：注册验证码/密码重置邮件继续使用卡片化品牌模板；`xianyu-test-1` 继续保持本地 `creditCents=100`，同步到 New-API 兑换额度为 1 元对应 quota，不再按美元汇率变成 7.x 元。
### 文件变更
- `apps/frist-api/tests/business-flow.test.mjs` — 新增主登录卡片内 Turnstile 位置与样式回归断言。
- `docs/002-changelog.md` / `docs/009-health.md` — 同步本轮验证证据。
### 验证
- `cd apps/frist-api && node --test tests/business-flow.test.mjs --test-name-pattern "user-facing HTML exposes production auth|Turnstile"`：`20 passed`。
- `cd apps/frist-api && node --test tests/server.test.mjs --test-name-pattern "sends registration email codes|keeps Xianyu 1 yuan"`：`114 passed`。

## [2026-07-08] 18800 layui 操作台暂停态收口
> 领域: `xianyu` | `frontend` | `docs`
> 影响模块: `XianyuAdmin`, `CC中转操作台`
> 关联问题: HI-cc-owner-console-layui-paused-ready
### 变更内容
- 确认 `layui/layui` 适合 18800 本机老板操作台：当前采用本地 vendored 静态资源，不走 CDN，不把后端迁到 React，也不改变发货业务接口。
- 修复 18800 主渲染函数漏定义 `strictPaused` 的问题，避免“严格门已通过但自动发货暂停保护”状态在浏览器运行时报错。
- 首屏文案收口为“待你恢复自动发货 / 严格门已通过，自动发货暂停保护”，明确这不是系统故障，而是重复发卡事故后的安全保护；恢复后第 1 单仍会自动暂停观察。
- 新增页面结构回归断言，锁住 layui 本地资源、暂停保护文案、恢复前安全检查和首单观察提示。
### 文件变更
- `packages/clawbot/src/xianyu/xianyu_admin.py` — 补齐 `strictPaused` 渲染变量，确保暂停保护态首屏正常显示。
- `packages/clawbot/tests/test_api_routes_regression.py` — 增加老板可见文案和运行时变量结构守护。
- `docs/002-changelog.md` / `docs/009-health.md` — 同步本轮 UI 收口和验证证据。
### 验证
- `python3 -m py_compile packages/clawbot/src/xianyu/xianyu_admin.py packages/clawbot/tests/test_api_routes_regression.py`：exit 0。
- `node --check /tmp/cc_ops_console_inline.js`：exit 0。
- `cd packages/clawbot && .venv312/bin/python -m pytest tests/test_api_routes_regression.py::test_xianyu_admin_page_escapes_dynamic_fields tests/test_api_routes_regression.py::test_xianyu_admin_serves_local_layui_assets tests/test_api_routes_regression.py::test_xianyu_admin_serves_local_layui_assets_without_api_token tests/test_api_routes_regression.py::test_xianyu_operator_mode_can_pause_auto_ship tests/test_api_routes_regression.py::test_xianyu_admin_public_sale_lock_explains_manual_pause_after_strict_gate tests/test_xianyu_cc_auto_ship.py::test_xianyu_admin_resume_auto_ship_canary_pauses_after_first_sent tests/test_xianyu_cc_auto_ship.py::test_xianyu_live_message_sent_consumes_auto_resume_canary --tb=short -q`：`7 passed`。
- live 只读复验：`/api/cc-public-sale-lock?refresh=true` 返回 `state=paused_after_strict_gate`；`/api/cc-operator-mode/resume-preflight` 返回 `safe_to_resume=true`；`/api/cc-operator-mode` 仍为 `auto_ship_paused=true`、`one_shot_active=false`、`auto_resume_canary_active=false`。
- Chrome 截图：`output/playwright/cc-ops-console-paused-ready-to-resume-20260708.png`，页面可见“待你恢复自动发货 / 严格门已通过，自动发货暂停保护 / 恢复前安全检查 / 恢复自动发货”。

## [2026-07-08] 恢复自动发货首单观察保险
> 领域: `xianyu` | `backend` | `frontend` | `docs`
> 影响模块: `cc_operator_state`, `XianyuAdmin`, `XianyuLive`, `CC中转操作台`
> 关联问题: HI-cc-auto-resume-canary
### 变更内容
- 恢复常驻自动发货时，系统会自动写入“首单观察票”：恢复后第 1 条卡密真正标记为 `message_sent` 时，会立刻把 `auto_ship_paused` 重新置为 `true`。
- `XianyuAdmin` 手动/浏览器 `mark-sent` 路径和 `XianyuLive` WebSocket 自动发货记录路径都会消耗首单观察票，避免恢复后连续处理多单。
- 18800 恢复成功提示会明确“系统已开启首单观察：第 1 单发卡成功后会自动暂停”。
- 当前 live 复验只读刷新后 `resume-preflight.safe_to_resume=true`，但 `auto_ship_paused=true`、`auto_resume_canary_active=false`，说明首单观察票只会在老板明确恢复时开启。
### 文件变更
- `packages/clawbot/src/xianyu/cc_operator_state.py` — 新增 `auto_resume_canary` 状态、恢复时武装、发卡后消费并自动暂停。
- `packages/clawbot/src/xianyu/xianyu_admin.py` — 恢复自动发货时启用首单观察票，`mark-sent` 后自动暂停，页面提示首单观察。
- `packages/clawbot/src/xianyu/xianyu_live.py` — 自动发货写入 `message_sent` 时同样消耗首单观察票。
- `packages/clawbot/tests/test_xianyu_cc_auto_ship.py` / `packages/clawbot/tests/test_api_routes_regression.py` — 增加恢复首单自动暂停和 WebSocket 路径回归。
- `docs/002-changelog.md` / `docs/006-registries.md` / `docs/009-health.md` — 同步恢复保险策略。
### 验证
- `python3 -m py_compile packages/clawbot/src/xianyu/cc_operator_state.py packages/clawbot/src/xianyu/xianyu_admin.py packages/clawbot/src/xianyu/xianyu_live.py packages/clawbot/tests/test_xianyu_cc_auto_ship.py packages/clawbot/tests/test_api_routes_regression.py`：exit 0。
- `node --check /tmp/cc_ops_console_inline.js`：exit 0。
- `cd packages/clawbot && .venv312/bin/python -m pytest tests/test_xianyu_cc_auto_ship.py::test_xianyu_live_message_sent_consumes_auto_resume_canary tests/test_xianyu_cc_auto_ship.py::test_xianyu_admin_resume_auto_ship_canary_pauses_after_first_sent tests/test_xianyu_cc_auto_ship.py::test_xianyu_admin_one_shot_delivery_allows_exactly_one_claim_when_paused tests/test_xianyu_cc_auto_ship.py::test_xianyu_admin_one_shot_dispatch_consumes_gate_for_paid_page_fallback tests/test_api_routes_regression.py::test_xianyu_operator_mode_can_pause_auto_ship tests/test_api_routes_regression.py::test_xianyu_admin_page_escapes_dynamic_fields --tb=short -q`：`6 passed`。
- live 复验：重启 `ai.openclaw.xianyu` 后页面包含“恢复前安全检查 / 系统已开启首单观察 / 第 1 单发卡成功后会自动暂停”；只读刷新后 `resume-preflight.ok=true`，但当前仍 `auto_ship_paused=true`、`auto_resume_canary_active=false`。
- Playwright 截图：`output/playwright/cc-ops-console-auto-resume-canary-20260708.png`。

## [2026-07-08] 恢复自动发货增加安全预检
> 领域: `xianyu` | `backend` | `frontend` | `docs`
> 影响模块: `XianyuAdmin`, `CC中转操作台`, `CC中转发货安全闸门`
> 关联问题: HI-cc-safe-auto-ship-resume
### 变更内容
- `POST /api/cc-operator-mode` 在恢复自动发货前新增只读安全预检：补救队列、库存/兑换码/渠道、买家公网入口、webhook 未授权拦截、CC Switch 导入入口、闲鱼连接/Cookie 和真实小额单严格门全部通过后才允许恢复。
- 新增 `GET /api/cc-operator-mode/resume-preflight`，老板可先点“恢复前安全检查”，只读查看是否可以恢复，不改变暂停开关、不发卡、不分配卡密。
- 18800 操作台新增“恢复前安全检查”按钮；点“恢复自动发货”时会二次确认，并在后端预检不通过时拒绝恢复、显示人话原因。
- 当前 live 复验：只读刷新后 `resume-preflight.ok=true`，但 `auto_ship_paused=true` 仍保持，说明系统已经具备恢复条件但不会擅自恢复。
### 文件变更
- `packages/clawbot/src/xianyu/xianyu_admin.py` — 新增 `_cc_auto_ship_resume_preflight()`、恢复前 409 阻断、只读预检接口和前端按钮/错误解释。
- `packages/clawbot/tests/test_api_routes_regression.py` — 更新暂停/恢复测试，确认不安全恢复会被 409 拒绝，安全预检通过后才允许恢复。
- `docs/002-changelog.md` / `docs/006-registries.md` / `docs/009-health.md` — 同步恢复前安全闸门。
### 验证
- `python3 -m py_compile packages/clawbot/src/xianyu/xianyu_admin.py packages/clawbot/tests/test_api_routes_regression.py`：exit 0。
- `node --check /tmp/cc_ops_console_inline.js`：exit 0。
- `cd packages/clawbot && .venv312/bin/python -m pytest tests/test_api_routes_regression.py::test_xianyu_operator_mode_can_pause_auto_ship tests/test_api_routes_regression.py::test_xianyu_admin_public_sale_lock_refreshes_readonly_audit tests/test_api_routes_regression.py::test_xianyu_admin_public_sale_lock_explains_manual_pause_after_strict_gate tests/test_api_routes_regression.py::test_xianyu_admin_public_sale_lock_blocks_bad_buyer_entry tests/test_api_routes_regression.py::test_xianyu_admin_public_sale_lock_blocks_bad_ccswitch_entry tests/test_api_routes_regression.py::test_xianyu_admin_page_escapes_dynamic_fields tests/test_api_routes_regression.py::test_xianyu_admin_page_opens_without_token_but_api_requires_token tests/test_xianyu_cc_auto_ship.py::test_xianyu_admin_dashboard_alias_points_to_owner_console --tb=short -q`：`8 passed`。
- live 复验：重启 `ai.openclaw.xianyu` 后，冷启动 `resume-preflight` 先提示库存/渠道证据未刷新；运行 `/api/cc-public-sale-lock?refresh=true` 后，`resume-preflight.ok=true/safe_to_resume=true`、`auto_ship_paused=true`、`one_shot_active=false`。
- Playwright 截图：`output/playwright/cc-ops-console-resume-preflight-20260708.png`，页面可见“恢复前安全检查”和“恢复自动发货”两个独立按钮。

## [2026-07-08] 售卖锁区分自动发货暂停保护
> 领域: `xianyu` | `backend` | `frontend` | `docs`
> 影响模块: `XianyuAdmin`, `CC中转操作台`, `CC中转上架锁`
> 关联问题: HI-cc-public-sale-lock-pause-copy
### 变更内容
- `GET /api/cc-public-sale-lock` 现在会区分“老板手动暂停自动发货保护”和“自动发货链路真的坏了”。
- 当真实小额单严格门已通过、库存/渠道/买家入口都正常，但 `auto_ship_paused=true` 时，接口返回 `state=paused_after_strict_gate`、`state_label=严格门已通过，自动发货暂停保护`。
- 售卖锁仍保持 `can_public_sale=false`，不会绕过防重复发卡安全开关；老板确认准备正式卖后，仍需在 18800 操作台手动点“恢复自动发货”。
### 文件变更
- `packages/clawbot/src/xianyu/xianyu_admin.py` — 上架锁新增 `auto_ship_paused/webhook_configured/ws_connected/cookie_ok` 诊断字段，并细分暂停保护文案。
- `packages/clawbot/tests/test_api_routes_regression.py` — 新增严格门已过但自动发货暂停时的回归测试。
- `docs/002-changelog.md` / `docs/006-registries.md` / `docs/009-health.md` — 同步老板可见语义。
### 验证
- 先补失败用例：`test_xianyu_admin_public_sale_lock_explains_manual_pause_after_strict_gate` 初次失败在 `gates.auto_ship_paused` 不存在，证明旧接口无法区分暂停保护。
- `python3 -m py_compile packages/clawbot/src/xianyu/xianyu_admin.py packages/clawbot/tests/test_api_routes_regression.py`：exit 0。
- `cd packages/clawbot && .venv312/bin/python -m pytest tests/test_api_routes_regression.py::test_xianyu_admin_public_sale_lock_refreshes_readonly_audit tests/test_api_routes_regression.py::test_xianyu_admin_public_sale_lock_explains_manual_pause_after_strict_gate tests/test_api_routes_regression.py::test_xianyu_admin_public_sale_lock_blocks_bad_buyer_entry tests/test_api_routes_regression.py::test_xianyu_admin_public_sale_lock_blocks_bad_ccswitch_entry tests/test_api_routes_regression.py::test_xianyu_admin_page_escapes_dynamic_fields --tb=short -q`：`5 passed`。
- 重启 `ai.openclaw.xianyu` 后 live 复验：`/api/cc-public-sale-lock?refresh=true` 返回 `state=paused_after_strict_gate`、`state_label=严格门已通过，自动发货暂停保护`、`can_public_sale=false`、`blockers=[自动发货被手动暂停保护（防重复发卡）]`。
- Playwright 截图：`output/playwright/cc-ops-console-paused-after-strict-gate-20260708.png`，页面可见“严格门已通过，自动发货暂停保护”。

## [2026-07-08] 18800 layui 运营台告警置顶
> 领域: `xianyu` | `frontend` | `docs`
> 影响模块: `XianyuAdmin`, `CC中转操作台`
> 关联问题: HI-cc-owner-console-layui-alerts
### 变更内容
- 在 `http://127.0.0.1:18800/` layui 操作台首屏新增红/黄告警置顶区：补救队列、待确认发货、自动发货暂停、闲鱼连接异常和库存不足会直接显示在状态卡片上方。
- 每条告警都配“怎么办/去处理/只读检查”按钮，老板不需要先展开高级排障；按钮只跳转或触发只读检查/单次放行确认，不会恢复常驻自动发货。
- 保持重复发卡事故后的安全边界：运行态复验 `auto_ship_paused=true`、`one_shot_active=false`，没有恢复桥接器常驻发卡。
### 文件变更
- `packages/clawbot/src/xianyu/xianyu_admin.py` — 18800 操作台新增 `top-alerts`、`renderTopAlerts` 和 `scrollToSection`。
- `packages/clawbot/tests/test_api_routes_regression.py` — 增加 layui 告警置顶与“怎么办”按钮结构守护。
- `docs/002-changelog.md` / `docs/009-health.md` — 同步本轮 UI 安全收口状态。
### 验证
- `python3 -m py_compile packages/clawbot/src/xianyu/xianyu_admin.py packages/clawbot/tests/test_api_routes_regression.py`：exit 0。
- `node --check /tmp/cc_ops_console_inline.js`：exit 0。
- `cd packages/clawbot && .venv312/bin/python -m pytest tests/test_api_routes_regression.py::test_xianyu_admin_page_escapes_dynamic_fields tests/test_api_routes_regression.py::test_xianyu_admin_serves_local_layui_assets tests/test_api_routes_regression.py::test_xianyu_admin_serves_local_layui_assets_without_api_token tests/test_api_routes_regression.py::test_xianyu_admin_page_opens_without_token_but_api_requires_token --tb=short -q`：`4 passed`。
- 已重启 `ai.openclaw.xianyu` 后复验 live 页面包含 `id="top-alerts"`、`function renderTopAlerts` 和“自动发货仍处于暂停保护”。
- Playwright 截图：`output/playwright/cc-ops-console-layui-alerts-20260708.png`，可见顶部黄色暂停保护告警和“只放行一次”按钮。
- `GET /api/cc-operator-mode`：`auto_ship_paused=true`、`one_shot_active=false`；`GET /api/cc-public-sale-lock`：`can_public_sale=false`，安全锁未被绕过。

## [2026-07-08] 闲鱼真实小额订单严格门通过与真实订单接管
> 领域: `xianyu` | `backend` | `deploy` | `docs`
> 影响模块: `CC中转卖家桥接器`, `XianyuAdmin`, `Frist-API`, `CC中转严格门`
> 关联问题: HI-cc-real-order-strict-gate
### 变更内容
- 卖家桥接器新增只读监听闲鱼 `message.headinfo` 网络响应能力：当前聊天页只显示“等待卖家发货”但 DOM 没有订单号时，会刷新并点击左侧已付款会话行，提取真实订单号和商品 ID；不发卡、不点击“去发货”。
- 新增 `scripts/cc_xianyu_headinfo_parser.mjs`，只在“已付款/待发货/去发货”上下文中提取 `orderId`，并把 `itemId` 单独返回，防止把商品 ID 当真实订单号。
- 为避免重复发卡，已发出的 `xy_browser_*` 浏览器临时单在后续识别到真实闲鱼订单号时，会接管为 `xy_oid_*`，不会再次分配或发送新卡密；单次放行票会被消费并记录“本次不再发送卡密”。
- Frist-API 新增低权限 `/api/ops/xianyu/remap-order`，复用闲鱼 webhook token，仅允许把已发卡履约记录从旧订单号改为真实订单号，并同步卡密 `soldOrderId`；不会创建新卡、不会开放管理员能力。
- 已将 `apps/frist-api/server/server.js` 同步到 Oracle `/opt/frist-api/apps/frist-api/server/server.js`，远端备份后重启 `frist-api.service`，服务为 `active`。
- 当前真实订单已从 `xy_browser_*` 安全接管为 `xy_oid_87f...`；同一订单已完成买家兑换、API Key 创建和真实模型调用，正式严格门 `--require-real-order` 返回 PASS。
- 出于重复发卡事故后的安全边界，`auto_ship_paused=true` 仍保持，公开售卖锁现在只剩“自动发货暂停”人为安全开关；老板确认后可在 18800 操作台一键恢复。
### 文件变更
- `scripts/cc_xianyu_headinfo_parser.mjs` / `scripts/cc_xianyu_headinfo_parser.test.mjs` — 新增闲鱼 headinfo 订单号与商品 ID 解析及防误判测试。
- `scripts/cc_zhongzhuan_seller_bridge.mjs` — 严格只读扫描通过 CDP Network 捕获 headinfo，回填真实订单号和商品 ID。
- `packages/clawbot/src/xianyu/xianyu_context.py` — 新增已发卡浏览器临时单接管真实订单号的方法。
- `packages/clawbot/src/xianyu/xianyu_admin.py` — 手动/浏览器已付款派发在识别真实订单时优先接管旧记录，不再重复发卡。
- `apps/frist-api/server/server.js` — 新增低权限闲鱼履约订单号接管接口。
- `apps/frist-api/tests/server.test.mjs` / `packages/clawbot/tests/test_xianyu_cc_auto_ship.py` — 增加“接管不发新卡”的回归测试。
### 验证
- `node scripts/cc_zhongzhuan_seller_bridge.mjs --scan-only --require-real-order-id --json`：`ok=true`、`strictReadyPages=1`、`orderIdHintPresent=true`、`itemIdHintPresent=true`。
- `node scripts/cc_zhongzhuan_seller_bridge.mjs --one-shot-override --delivery-only --require-real-order-id --json`：返回 `shipment_already_handled`，未发送新卡密，旧记录接管为 `xy_oid_*`。
- `GET http://127.0.0.1:18800/api/cc-shipments?limit=5`：最新真实记录为 `xy_oid_87fdf5e5cf60c82f`、`status=message_sent`、`pending_rescue=0`。
- Oracle 真实调用：同一真实订单对应买家 Key 的 `model_logs_after_redeem` 从 `0` 增加到 `1`，`chat_http=200`。
- `node scripts/cc_zhongzhuan_readiness_audit.mjs --require-real-order`：`PASS`，`realXianyuOrderProof=PASS`、`oracle=PASS`、`readyOrders=1`。
- `GET /api/cc-readiness-audit?mode=strict`：`ok=true`、`real_orders=1`、`same_order_ready=1`，严格门摘要已写入本机 18800。
- `cd apps/frist-api && node --test --test-name-pattern "accepts paid Xianyu orders|remaps a browser Xianyu fulfillment" tests/server.test.mjs`：2 项通过。
- `cd packages/clawbot && .venv312/bin/python -m pytest tests/test_xianyu_cc_auto_ship.py::test_xianyu_admin_manual_paid_order_dispatch_does_not_resend_sent_shipment tests/test_xianyu_cc_auto_ship.py::test_xianyu_admin_manual_paid_order_dispatch_adopts_browser_sent_shipment_to_real_order tests/test_xianyu_cc_auto_ship.py::test_xianyu_admin_browser_delivery_next_ignores_already_sent_messages -q`：3 项通过。

## [2026-07-08] 闲鱼当前页真实订单号识别增强
> 领域: `xianyu` | `frontend` | `docs`
> 影响模块: `Chrome Social Pilot`, `CC中转卖家桥接器`, `CC中转操作台`
> 关联问题: HI-cc-real-order-id-scan
### 变更内容
- 针对真实聊天页已显示“等待卖家发货”但没有可见订单号的问题，页面执行器新增只读识别：可从白名单订单参数 `orderId/tradeId/bizOrderId/biz_order_id`、订单相关 `data-*` 属性和“去发货/待发货”链接里提取真实订单号。
- 为避免误判，普通商品链接 `id=...` 不会被当成真实订单号；没有订单号时仍不会发卡，继续保持 `xy_browser_*` 不能解锁正式售卖。
- 只读扫描新增 `orderCardPresent` / `shipActionPresent`，18800 和桥接器会在看到待发货订单卡但缺订单号时提示老板点“¥1.00 / 等待卖家发货”订单卡或“去发货”旁边进入订单详情。
- 已同步运行版 Chrome 插件 `~/.openclaw/cc-social-pilot-runtime-extension/social-page-runner.js`；卖家桥接器本身读取仓库源码，立即使用新版只读扫描。
### 文件变更
- `packages/openclaw-npm/assets/chrome-extension/social-page-runner.js` — 增强真实订单号提取与待发货订单卡识别。
- `scripts/cc_zhongzhuan_seller_bridge.mjs` — 透传订单卡/去发货入口信号，并输出更明确下一步。
- `packages/clawbot/src/xianyu/xianyu_admin.py` — 18800 只读检查的人话提示优先展示“点订单卡/去发货旁边进入详情”。
- `packages/openclaw-npm/assets/chrome-extension/test/social-page-runner.test.mjs` / `packages/clawbot/tests/test_xianyu_cc_auto_ship.py` — 增加订单号链接提取、商品 ID 防误判和老板提示回归。
### 验证
- `node --check packages/openclaw-npm/assets/chrome-extension/social-page-runner.js && node --check scripts/cc_zhongzhuan_seller_bridge.mjs`：exit 0。
- `cd packages/openclaw-npm/assets/chrome-extension && node --test test/social-page-runner.test.mjs test/popup-static.test.mjs`：`54 passed / 0 failed`。
- `python3 -m py_compile packages/clawbot/src/xianyu/xianyu_admin.py packages/clawbot/tests/test_xianyu_cc_auto_ship.py`：exit 0。
- `cd packages/clawbot && .venv312/bin/python -m pytest tests/test_xianyu_cc_auto_ship.py::test_xianyu_admin_seller_bridge_page_scan_is_read_only tests/test_xianyu_cc_auto_ship.py::test_xianyu_admin_seller_bridge_page_scan_guides_im_list tests/test_xianyu_cc_auto_ship.py::test_xianyu_admin_seller_bridge_page_scan_guides_paid_order_card tests/test_xianyu_cc_auto_ship.py::test_xianyu_admin_seller_bridge_open_page_only_navigates tests/test_api_routes_regression.py::test_xianyu_admin_page_escapes_dynamic_fields -q`：`5 passed`。
- 实机只读扫描当前卖家 Chromium：`paidSignal=true`、`orderCardPresent=true`、`inputReady=false`、`orderIdHintPresent=false`，未发卡；下一步提示为点击订单卡/去发货旁边进入详情。

## [2026-07-08] 闲鱼单次发卡放行闸门
> 领域: `xianyu` | `backend` | `frontend` | `docs`
> 影响模块: `cc_operator_state`, `XianyuAdmin`, `Chrome Social Pilot`, `CC中转卖家桥接器`, `CC中转操作台`
> 关联问题: HI-cc-xianyu-one-shot-delivery
### 变更内容
- 在保持 `auto_ship_paused=true` 的前提下，新增“只放行一次发卡”能力：老板可在 18800 操作台点一次，3 分钟内仅允许浏览器助手发送 1 条卡密，发送/领取后自动失效。
- 新增 `/api/cc-operator-mode/one-shot-delivery`，单次放行状态写入 `.openclaw/cc-zhongzhuan-operator-state.json`，不改库存、不恢复常驻自动发货、不绕过本机 `X-API-Token`。
- `/api/cc-browser-delivery/next` 支持 `one_shot=1`：暂停状态下没有有效放行票仍返回 `operator_paused` 且不返回卡密；有票时只原子领取一条并消费放行票，第二次请求拿不到同一条话术。
- 浏览器付款页兜底 `/api/cc-manual-paid-order/dispatch` 增加 `one_shot` 参数：暂停状态下若要由插件/桥接器生成并发送卡密，必须先消费单次放行票，避免多个触发器连续发两条卡密。
- 本机卖家桥接器新增 `--one-shot-override` / `--one-shot` 参数；Chrome 插件读取待发话术时自动带 `one_shot=1`，没有放行票时仍然被暂停闸门拦住。
- 18800 layui 操作台新增“只放行一次发卡”按钮和状态提示，文案明确“发完 1 条自动失效，常驻自动发货仍暂停”。
- 18800 操作台继续新增“一键跑当前页”，后端调用卖家桥接器 `--delivery-only --one-shot-override --require-single-xianyu-page --require-real-order-id --json`：只扫描当前闲鱼已付款页并最多发送 1 条卡密，不执行确认发货、不恢复上架；为防止多聊天页发错买家，单次发卡要求只打开 1 个闲鱼页，并且页面必须能识别真实订单号/交易号，避免新的严格门证据落成 `xy_browser_*`。
- 继续新增“只读检查当前页”按钮和 `/api/cc-seller-bridge/page-scan`：调用 `--scan-only --require-real-order-id --json` 只注入页面扫描器读取付款信号、输入框和订单号提示，不调用发货 API、不申请单次放行票、不改本机履约状态，用于老板点发卡前确认自己是否打开了正确页面。
- 只读检查的返回语义改成“检查是否跑完”和“当前页是否可发卡”分离：当前页不是付款页、缺输入框或缺订单号时返回 `scanCompleted=true/notReady=true` 和下一步建议，不再误报 `seller_bridge_scan_failed`，避免老板把正常未命中当成系统故障。
- 只读检查增加“闲鱼首页”专门提示：如果当前唯一闲鱼页是 `https://www.goofish.com/` 首页，会直接提示“现在打开的是闲鱼首页，请从消息或订单列表打开这笔已付款订单，并看到订单号/交易号后再检查”，减少老板猜下一步。
- 18800 前端同步优先展示后端 `nextAction` 人话建议，不再把 `no_paid_order_signal` 这类机器原因直接展示给老板。
- 18800 单次发卡区域新增“打开卖家 Chromium 的闲鱼消息”和“打开卖家 Chromium 的工作台”快捷入口；只读检查未通过时会附带这两个按钮，方便老板从闲鱼首页切到已付款买家的聊天/订单页。该入口调用 `/api/cc-seller-bridge/open-page` 和桥接器 `--open-page=im|seller --json`，只导航卖家专用 Chromium，并通过 `Page.bringToFront` 尽量把目标标签页带到前台；不发卡、不申请放行票、不改订单，普通浏览器链接仅作为兜底。
- 只读检查继续细分“闲鱼消息列表页”和“卖家工作台页”：如果已经在 `goofish.com/im` 但还没点进买家，会提示从左侧会话列表点进已付款买家；如果在 `seller.goofish.com`，会提示从订单/待发货打开该订单或联系买家。
- 18800 后端新增 Node 选择器，优先使用支持 DevTools WebSocket 的 Node，避免 LaunchAgent PATH 命中旧 Node 导致桥接器报 `WebSocket is not defined`。
### 文件变更
- `packages/clawbot/src/xianyu/cc_operator_state.py` — 新增单次放行票的授权、查看、消费和过期判断。
- `packages/clawbot/src/xianyu/xianyu_admin.py` — 新增单次放行 API、浏览器领取/手动兜底 one-shot 闸门、卖家桥接器只读扫描/一键 API 和操作台按钮。
- `scripts/cc_zhongzhuan_seller_bridge.mjs` — 支持 `--scan-only` / `--one-shot-override` / `--delivery-only` / `--require-single-xianyu-page` / `--require-real-order-id` / `--open-page=im|seller`，只读扫描不发卡，只有扫到唯一已付款页且可识别真实订单号时才申请单次放行；`--scan-only` 扫描成功但未命中付款页时也以正常诊断退出，避免被 GUI 误判为脚本崩溃。
- `packages/openclaw-npm/assets/chrome-extension/background.js` — 插件领取发货话术与付款页兜底派发均带单次放行参数。
- `packages/clawbot/tests/test_xianyu_cc_auto_ship.py` / `packages/clawbot/tests/test_api_routes_regression.py` — 增加暂停、一票一次、页面入口回归。
### 验证
- `packages/clawbot/.venv312/bin/python -m py_compile packages/clawbot/src/xianyu/cc_operator_state.py packages/clawbot/src/xianyu/xianyu_admin.py packages/clawbot/tests/test_xianyu_cc_auto_ship.py packages/clawbot/tests/test_api_routes_regression.py`：exit 0。
- `cd packages/clawbot && .venv312/bin/python -m pytest tests/test_xianyu_cc_auto_ship.py tests/test_api_routes_regression.py --tb=short -q`：跑到 `[100%]`，exit 0。
- `node --check scripts/cc_zhongzhuan_seller_bridge.mjs`、`node --check packages/openclaw-npm/assets/chrome-extension/background.js`：exit 0。
- `cd packages/openclaw-npm/assets/chrome-extension && node --test test/social-page-runner.test.mjs test/popup-static.test.mjs`：`52 passed / 0 failed`。
- 已同步运行版插件 `~/.openclaw/cc-social-pilot-runtime-extension`，`background.js` 和 `social-page-runner.js` 源/运行目录 SHA256 一致。
- 重启 `ai.openclaw.xianyu` 后实测：首页包含“只放行一次发卡”和 `/api/cc-operator-mode/one-shot-delivery`；无 Token 调用新接口 HTTP 401。
- 当前闲鱼页停在 `https://www.goofish.com/` 首页时实测 `/api/cc-seller-bridge/one-shot-delivery` 返回 `mode=one_shot_delivery_only`、`deliveries[0].reason=no_paid_order_signal`，未发送卡密，`one_shot_delivery_active=false`、`pending_rescue=0`。
- 同一首页实测 `node scripts/cc_zhongzhuan_seller_bridge.mjs --scan-only --require-real-order-id --json` 退出码为 0；`/api/cc-seller-bridge/page-scan` 返回 `ok=true`、`scanCompleted=true`、`notReady=true`、`mode=scan_only`、`readOnly=true`、`readyPages=0`，`nextAction` 明确提示“现在打开的是闲鱼首页，请从闲鱼消息或订单列表打开这笔已付款订单”，未发送卡密，未把正常未命中误报为系统故障。
- 重启 `ai.openclaw.xianyu` 后实测：18800 首页 HTTP 200，`/static/layui/layui.js` HTTP 200，无 Token `/api/cc-operator-mode` HTTP 401；页面包含“打开闲鱼消息 / 打开卖家工作台”链接和 `xianyuPageShortcutHtml`，`/api/cc-seller-bridge/page-scan` 在闲鱼首页返回 `ok=true/scanCompleted=true/notReady=true`，仍不发卡。
- 继续实测 `/api/cc-seller-bridge/open-page`：POST `destination=im` 返回 HTTP 200、`mode=open_page_only`、`openedIn=existing_tab`、`broughtFront=true`、`openPageOnly=true`、`deliveryOnly=false`、`oneShot=false`，卖家 Chromium 已从闲鱼首页导航到 `https://www.goofish.com/im?...`；随后只读扫描显示 `title=聊天_闲鱼`、`paidSignal=false`、`inputReady=false`，确认只是打开消息页，没有发卡。
- 重启后再测当前 `goofish.com/im` 消息列表页：`/api/cc-seller-bridge/page-scan` 返回 `ok=true/scanCompleted=true/notReady=true`，`nextAction` 已明确提示“请在左侧会话列表点进已付款买家，看到聊天输入框和订单号/交易号后再点只读检查”；仍未发卡。
- 追加前台激活复验：`/api/cc-seller-bridge/open-page` 再次打开 `destination=im` 返回 `broughtFront=true`、`deliveryOnly=false`、`oneShot=false`；随后只读扫描仍提示在左侧会话列表点进已付款买家，未发卡。

## [2026-07-08] 闲鱼真实待发货只读扫单入口
> 领域: `xianyu` | `backend` | `frontend` | `docs`
> 影响模块: `XianyuLive`, `XianyuAdmin`, `CC中转操作台`, `CC中转严格门`
> 关联问题: HI-cc-real-order-readonly-probe
### 变更内容
- 新增 `/api/cc-paid-order-probe`，只读扫描闲鱼卖家“待发货”订单列表，用于老板重新下单后先确认系统是否看得到真实待发货单。
- 新入口只读取并脱敏返回候选订单，不调用 CC中转 webhook、不分配卡密、不发送闲鱼消息、不点击“去发货”，也不会解除 `auto_ship_paused`；当闲鱼卖家订单 API 返回“无权限访问”时，会明确提示改走浏览器当前页兜底。
- 18800 操作台新增“真实待发货扫单”折叠区，按钮文案明确为“只读扫真实待发货订单”，帮助在重复发卡事故后安全推进 `xy_oid_*` 严格门。
- Live 层新增 `scan_cc_paid_orders_readonly()`，复用卖家订单列表解析和状态分类逻辑，只返回订单哈希、买家/商品是否存在、本机履约状态等脱敏摘要。
- 浏览器当前已付款页兜底升级：页面执行器会从 URL 或“订单号/交易号”可见文案提取真实订单号；只有提取到真实订单号时才传 `xianyu-real:*` 给本机后端并转换为 `xy_oid_*`，否则仍保持 `xy_browser_*`，不放宽正式严格门。
### 文件变更
- `packages/clawbot/src/xianyu/xianyu_live.py` — 新增真实待发货只读扫描方法。
- `packages/clawbot/src/xianyu/xianyu_admin.py` — 新增只读扫单 API、脱敏输出和 18800 操作台入口。
- `packages/clawbot/tests/test_xianyu_cc_auto_ship.py` — 增加只读扫单不发卡、不写履约记录、不泄露原始订单/买家的回归测试。
- `packages/clawbot/tests/test_api_routes_regression.py` — 增加操作台只读扫单入口结构守护。
- `docs/002-changelog.md` / `docs/006-registries.md` / `docs/009-health.md` — 同步安全边界和当前严格门卡点。
### 验证
- 先补失败用例：`test_xianyu_admin_paid_order_probe_is_read_only_and_scrubbed` 初次失败在 `/api/cc-paid-order-probe` HTTP 404，证明接口未实现。
- `python3 -m py_compile packages/clawbot/src/xianyu/xianyu_admin.py packages/clawbot/src/xianyu/xianyu_live.py packages/clawbot/tests/test_xianyu_cc_auto_ship.py packages/clawbot/tests/test_api_routes_regression.py`：exit 0。
- `cd packages/clawbot && .venv312/bin/python -m pytest tests/test_xianyu_cc_auto_ship.py::test_xianyu_admin_paid_order_probe_is_read_only_and_scrubbed tests/test_xianyu_cc_auto_ship.py::test_xianyu_live_readonly_paid_order_probe_does_not_send_or_record tests/test_api_routes_regression.py::test_xianyu_admin_page_escapes_dynamic_fields --tb=short -q`：`3 passed`。

## [2026-07-08] 闲鱼后端 H5 确认发货实验入口
> 领域: `xianyu` | `backend` | `frontend` | `docs`
> 影响模块: `XianyuAdmin`, `XianyuApis`, `CC中转操作台`, `CC中转严格门`
> 关联问题: HI-cc-xianyu-backend-confirm-shipment
### 变更内容
- 在 18800 操作台新增后端 H5 虚拟发货实验入口 `/api/cc-shipments/{id}/confirm-xianyu-backend`，复用 `mtop.taobao.idle.logistic.consign.dummy`，用于“卡密已确认发给买家”后尝试把闲鱼真实订单推进到已发货。
- 继续保持安全边界：默认关闭，必须显式设置 `CC_XIANYU_AUTO_CONFIRM_SHIPMENT_ENABLED=1` 才执行；只接受 10 位以上纯数字闲鱼订单号；`xy_manual_*` / `xy_browser_*` / 未发卡记录只标记跳过，不会调用闲鱼接口。
- 操作台补救队列对真实数字 `message_sent` 订单展示“后端确认发货”按钮；按钮会再次弹窗确认，失败只回写 `xianyu_confirm_status=failed`，不会重新分配卡密或重复发消息。
### 文件变更
- `packages/clawbot/src/xianyu/xianyu_admin.py` — 新增后端确认发货 API、Cookie 选择逻辑和操作台按钮。
- `packages/clawbot/tests/test_xianyu_cc_auto_ship.py` — 增加默认关闭、真实数字订单确认、手工单跳过回归。
- `packages/clawbot/tests/test_api_routes_regression.py` — 操作台静态结构守护新增后端确认发货按钮和接口。
- `docs/002-changelog.md` / `docs/006-registries.md` / `docs/009-health.md` — 同步默认关闭和真实订单安全边界。
### 验证
- 先补失败用例：`test_xianyu_admin_backend_confirm_is_disabled_by_default` 初次失败在接口 HTTP 404，证明 18800 尚未暴露后端确认发货入口。
- `python3 -m py_compile packages/clawbot/src/xianyu/xianyu_admin.py`：exit 0。
- `cd packages/clawbot && .venv312/bin/python -m pytest tests/test_api_routes_regression.py::test_xianyu_admin_page_escapes_dynamic_fields tests/test_xianyu_cc_auto_ship.py::test_xianyu_admin_backend_confirm_is_disabled_by_default tests/test_xianyu_cc_auto_ship.py::test_xianyu_admin_backend_confirm_only_confirms_numeric_order -q`：`3 passed`。
- `cd packages/clawbot && .venv312/bin/python -m pytest tests/test_api_routes_regression.py tests/test_xianyu_cc_auto_ship.py --tb=short -q`：跑到 `[100%]`，exit 0。
- 重启 `ai.openclaw.xianyu` 后实测：`/` HTTP 200、`/static/layui/css/layui.css` HTTP 200、无 Token `/api/cc-operator-mode` HTTP 401；页面包含“后端确认发货”、`confirmShipmentBackend` 和 `/confirm-xianyu-backend`；`ai.openclaw.cc-seller-bridge` 未启动。

## [2026-07-08] 18800 本机操作台 layui 组件化重构
> 领域: `xianyu` | `frontend` | `docs`
> 影响模块: `XianyuAdmin`, `CC中转操作台`, `本机静态资源`
> 关联问题: HI-cc-owner-console-layui
### 变更内容
- 确认可以基于 `layui/layui` 重构 `http://127.0.0.1:18800/`，但采用“本机静态资源 + 渐进增强”方式：不走 CDN，不改业务接口，不恢复自动发货，避免本机 Token 页面加载外部脚本。
- 将 `layui@2.13.8` 的 `layui.js`、`layui.css` 和字体文件复制到 `packages/clawbot/src/xianyu/static/layui/`，并由 FastAPI 挂载 `/static/layui/...`。
- 操作台首页接入 `layui.use(['layer','element'])`，危险确认/提示改用 layui layer 组件；无 layui 时仍降级为浏览器原生提示。
- 补救队列从卡片列表升级为 `layui-table` 表格，保留“填入话术 / 已手动发送 / 重试发送 / 标记已处理”等原有安全操作。
### 文件变更
- `packages/clawbot/src/xianyu/xianyu_admin.py` — 挂载本机静态资源、首页引入 layui、补救队列表格化和 layer 交互。
- `packages/clawbot/src/xianyu/static/layui/` — 新增本机 layui 前端资源，避免外链 CDN。
- `packages/clawbot/tests/test_api_routes_regression.py` — 增加本机 layui 资源、页面结构和静态资源免 Token 加载回归。
- `docs/002-changelog.md` / `docs/006-registries.md` / `docs/009-health.md` — 同步操作台重构状态。
### 验证
- 先补失败用例：`test_xianyu_admin_page_escapes_dynamic_fields` 初次失败在首页缺少 `/static/layui/layui.js`，证明旧页面未完成 layui 接入。
- `python3 -m py_compile packages/clawbot/src/xianyu/xianyu_admin.py`：exit 0。
- `cd packages/clawbot && .venv312/bin/python -m pytest tests/test_api_routes_regression.py::test_xianyu_admin_page_escapes_dynamic_fields tests/test_api_routes_regression.py::test_xianyu_admin_serves_local_layui_assets tests/test_api_routes_regression.py::test_xianyu_admin_serves_local_layui_assets_without_api_token tests/test_xianyu_cc_auto_ship.py::test_xianyu_admin_dashboard_alias_points_to_owner_console -q`：通过。
- 重启 `ai.openclaw.xianyu` 后实测：`/`、`/static/layui/css/layui.css`、`/static/layui/layui.js` 均 HTTP 200；无 Token 访问 `/api/cc-operator-mode` 仍 HTTP 401。
- 系统 Chrome Playwright 验收：`window.layui=true`、本机 layui CSS 已加载、页面不含外部 CDN，console `0 error / 0 warning`；截图 `output/playwright/cc-ops-console-layui-20260708.png`。

## [2026-07-08] 闲鱼重复发卡事故止血与领取锁
> 领域: `xianyu` | `backend` | `frontend` | `docs`
> 影响模块: `XianyuContextManager`, `XianyuAdmin`, `Chrome Social Pilot`, `CC中转卖家桥接器`, `严格门审计`
> 关联问题: HI-cc-xianyu-duplicate-delivery
### 变更内容
- 紧急止血：本机自动发货已保持 `auto_ship_paused=true`，`ai.openclaw.cc-seller-bridge` LaunchAgent 未恢复；重启后仅保留 `ai.openclaw.xianyu` 管理服务，防止继续自动刷屏买家。
- 修复根因：`/api/cc-browser-delivery/next` 从“只读下一条话术”改为服务端原子领取，领取后状态变为 `browser_delivery_claimed`，第二个浏览器/桥接器/标签页无法再次拿到完整卡密话术。
- 暂停开关加固：浏览器发货入口在自动发货暂停时直接返回 `reason=operator_paused`，不再向插件/桥接器返回卡密，也阻断“当前付款页兜底生成话术并发送”的旁路。
- 失败回写闭环：新增 `/api/cc-shipments/{id}/mark-send-failed`，页面发送失败时退回 `message_send_failed` 队列；桥接器和 Chrome 插件均会调用该接口，避免记录永久卡在“发送中”。
- 严格门和看板同步：`browser_delivery_claimed` 纳入补救/严格门待处理统计，导出状态报告和操作台补救队列会显示该状态，避免发货中断时误判为绿灯。
### 文件变更
- `packages/clawbot/src/xianyu/xianyu_context.py` — 新增浏览器发货领取锁、领取超时退回和发送失败回写。
- `packages/clawbot/src/xianyu/xianyu_admin.py` — 浏览器待发接口接入暂停保护和原子领取，新增 `mark-send-failed` 接口，并把新状态加入导出/看板。
- `scripts/cc_zhongzhuan_seller_bridge.mjs` — 暂停时不再走付款页兜底派发；页面发送失败会回写失败队列。
- `packages/openclaw-npm/assets/chrome-extension/background.js` — Chrome 插件同样尊重暂停状态，并在发送失败时回写失败。
- `scripts/cc_zhongzhuan_readiness_audit.mjs` — 正式售卖审计把 `browser_delivery_claimed` 计入未收尾队列。
- `packages/clawbot/tests/test_xianyu_cc_auto_ship.py` — 增加领取一次、暂停保护、发送失败释放三条回归测试。
- `docs/002-changelog.md` / `docs/006-registries.md` / `docs/009-health.md` — 同步事故、接口和当前运行状态。
### 验证
- 先补失败用例：`test_xianyu_admin_browser_delivery_next_claims_pending_once` 初次失败在 `manual_delivery_ready != browser_delivery_claimed`，证明原接口没有领取锁。
- `cd packages/clawbot && .venv312/bin/python -m pytest tests/test_xianyu_cc_auto_ship.py -q`：跑到 `[100%]`，exit 0。
- `cd packages/clawbot && .venv312/bin/python -m pytest tests/test_api_routes_regression.py --tb=short -q`：`43 passed`。
- `cd packages/openclaw-npm/assets/chrome-extension && node --check background.js && node --check social-page-runner.js && node --test test/social-page-runner.test.mjs test/popup-static.test.mjs`：`51 passed / 0 failed`。
- `python3 -m py_compile packages/clawbot/src/xianyu/xianyu_context.py packages/clawbot/src/xianyu/xianyu_admin.py`、`node --check scripts/cc_zhongzhuan_seller_bridge.mjs`、`node --check scripts/cc_zhongzhuan_readiness_audit.mjs`：exit 0。
- `cd packages/clawbot && .venv312/bin/python -m pytest tests/ --tb=short -q`：跑到 `[100%]`，exit 0（仅第三方 `js2py` deprecation warning）。
- 重启 `ai.openclaw.xianyu` 后实测：`/api/cc-operator-mode` 返回 `auto_ship_paused=true`、`stage=operator_paused`；`/api/cc-browser-delivery/next` 返回 `hasPending=false`、`reason=operator_paused`，不返回卡密话术；`launchctl list` 中无 `ai.openclaw.cc-seller-bridge`。

## [2026-07-08] CC中转真实小额订单预检问题收口
> 领域: `xianyu` | `frontend` | `backend` | `docs`
> 影响模块: `Frist-API`, `Chrome Social Pilot`, `CC中转卖家桥接器`, `XianyuAdmin`
> 关联问题: HI-cc-real-order-preflight
### 变更内容
- 修复注册/登录弹窗里 Turnstile 验证位置不符合用户习惯的问题：弹窗表单现在自带 `auth-turnstile-slot`，验证码会出现在登录/注册组件容器内，不再掉到页面底部。
- 邮箱验证码和重置密码邮件改为“大厂感”事务邮件模板：卡片化布局、大号验证码、安全提示、深色模式和移动端响应式；未新增第三方依赖，只复用纯 HTML/CSS。
- 补齐闲鱼卡密防重复发送三层保护：后端对已 `message_sent` 订单幂等跳过，卖家桥接器收到 `alreadyHandled` 不再填话术，浏览器页面执行器发现输入框残留同一张卡密/同一段发货话术时会清空草稿而不是再次发送。
- 实机复验时发现本机旧服务未重启会继续把已发订单当作待发送；已补“已发订单不进浏览器待发送队列”回归、增加已处理订单残留草稿清理函数，并重启 `ai.openclaw.xianyu` / `ai.openclaw.cc-seller-bridge` 让运行环境加载新版逻辑。
- 修复“1 元商品到账 7.5 美元/人民币折算额度”的口径错误：`xianyu-*` 套餐现在按闲鱼售价人民币 1:1 入账，1 元测试档本地余额为 100 分，同步 New-API 兑换额度为 500000。
- 完成开源社区调研后的自动发货路线判断：PC 页面的“去发货”经常被闲鱼引导扫码去 App，不能作为稳定自动化主链路；下一步应实验 H5/mtop 虚拟发货接口，只允许真实数字订单号走接口确认发货，页面点击继续作为兜底。
- 多价格商品短期方案收口为“多个商品链接对应多个套餐”，避免普通卖家网页端多规格自动发布不稳定；长期再评估闲鱼开放平台/服务商 SKU 发布能力。
- 完成用户指定 21 个 GitHub 高 Star 项目调研，新增 `docs/082-open-source-wheel-research.md`，按“直接可用 / 借鉴思路 / 暂不建议”给出接入路线。
### 文件变更
- `apps/frist-api/index.html` — 登录/注册弹窗内新增验证码容器。
- `apps/frist-api/server/email.js` — 统一事务邮件模板，优化验证码/重置邮件观感。
- `apps/frist-api/server/server.js` — 闲鱼套餐按人民币售价 1:1 计算到账额度。
- `packages/openclaw-npm/assets/chrome-extension/social-page-runner.js` / `background.js` — 新增 Enter 发送兜底、重复卡密草稿清理和已处理订单残留草稿清理。
- `scripts/cc_zhongzhuan_seller_bridge.mjs` — 已处理订单安全跳过并触发残留草稿清理，避免重复填入/发送卡密。
- `packages/clawbot/src/xianyu/xianyu_admin.py` — 手工已付款订单派发接口增加已发订单幂等保护，浏览器待发送队列只返回待发送/发送失败状态。
- `apps/frist-api/tests/business-flow.test.mjs` / `apps/frist-api/tests/server.test.mjs` / `packages/openclaw-npm/assets/chrome-extension/test/social-page-runner.test.mjs` / `packages/clawbot/tests/test_xianyu_cc_auto_ship.py` — 增加对应回归测试。
- `docs/082-open-source-wheel-research.md` / `docs/003-docs-index.md` — 新增开源轮子调研报告并登记索引。
### 验证
- `cd apps/frist-api && node --test tests/server.test.mjs tests/business-flow.test.mjs`：`133 passed / 0 failed`。
- `cd packages/openclaw-npm/assets/chrome-extension && node --check social-page-runner.js && node --check background.js && node --test test/social-page-runner.test.mjs`：`22 passed / 0 failed`。
- `cd packages/clawbot && .venv312/bin/python -m pytest tests/test_xianyu_cc_auto_ship.py::test_xianyu_admin_manual_paid_order_dispatch_does_not_resend_sent_shipment tests/test_xianyu_cc_auto_ship.py::test_xianyu_admin_browser_delivery_next_ignores_already_sent_messages tests/test_xianyu_cc_auto_ship.py::test_xianyu_admin_browser_delivery_next_reuses_pending_message -q`：`3 passed`。
- `node --check scripts/cc_zhongzhuan_seller_bridge.mjs`、`python3 -m py_compile packages/clawbot/src/xianyu/xianyu_admin.py`：exit 0。
- `cd packages/clawbot && .venv312/bin/python -m pytest tests/test_xianyu_cc_auto_ship.py -q`：跑到 `[100%]`，exit 0。
- `cd packages/clawbot && .venv312/bin/python -m pytest tests/ --tb=short -q`：跑到 `[100%]`，exit 0。
- 重启本机 `ai.openclaw.xianyu` / `ai.openclaw.cc-seller-bridge` 后复验：`/api/cc-browser-delivery/next` 返回 `hasPending=false`；`node scripts/cc_zhongzhuan_seller_bridge.mjs --once --json` 对已发订单返回 `stage=pending`、`reason=shipment_already_handled`，未再出现 `stage=sent`。
- `git diff --check`：exit 0。

## [2026-07-08] CC中转严格模拟门闭环收口
> 领域: `xianyu` | `frontend` | `docs`
> 影响模块: `Chrome Social Pilot`, `CC中转卖家桥接器`, `严格模拟门`
> 关联问题: HI-cc-xianyu-auto-ops
### 变更内容
- 补齐替换模式最后一环：当前页是可访问的闲鱼商品详情页，且没有“已下架/已售罄/商品已失效”文案时，页面执行器会把它视为“商品在线核验通过”，不再强依赖页面必须出现“在售中/正常展示”等卖家后台文案。
- 卖家桥接器 `--relist-only --simulation-relist` 已在当前打开的商品详情页完成只读在线核验，并把本次模拟履约记录回写为 `relist_status=online_verified`。
- `/api/cc-simulation-gate` 复验为全绿：`simulation_gate_ok=true`、`missing_steps=[]`、`can_unlock_public_sale=false`；模拟门仍明确排除“买家真实下单付款”和“最终点击闲鱼发货按钮”，不会解锁正式售卖。
- 正式严格门继续保持安全锁：`node scripts/cc_zhongzhuan_readiness_audit.mjs --require-real-order --json` 仍因没有新的 `xy_oid_*` 真实闲鱼自动订单返回 `ok=false`，这是预期阻断，不是故障。
### 文件变更
- `packages/openclaw-npm/assets/chrome-extension/social-page-runner.js` — 恢复上架执行器新增商品详情 URL 在线核验分支。
- `packages/openclaw-npm/assets/chrome-extension/test/social-page-runner.test.mjs` — 新增可访问 goofish 商品详情页不点击“重新上架”但回写在线核验的回归测试。
- `docs/002-changelog.md` / `docs/009-health.md` — 同步模拟门闭环状态和正式售卖边界。
### 验证
- 先补失败用例：`node --test test/social-page-runner.test.mjs --test-name-pattern 'verifies accessible goofish item detail page as online'` 初次失败在 `onlineVerified=false`，修复后通过。
- `cd packages/openclaw-npm/assets/chrome-extension && node --check social-page-runner.js && node --test test/social-page-runner.test.mjs`：`19 passed / 0 failed`。
- `node --test scripts/auto_ops_scripts.test.mjs`：`2 passed / 0 failed`。
- `python3 -m py_compile packages/clawbot/src/xianyu/xianyu_admin.py`：exit 0。
- `cd packages/clawbot && .venv312/bin/python -m pytest tests/test_xianyu_cc_auto_ship.py --tb=short -q`：`[100%]`，exit 0。
- `cd packages/clawbot && .venv312/bin/python -m pytest tests/ --tb=short -q`：第二次全量跑到 `[100%]`，exit 0；首次全量在 Intel Worker CLI 外部源用例出现一次 `raw_count=0` 抖动，单测复跑和第二次全量均通过。
- `node scripts/cc_zhongzhuan_seller_bridge.mjs --relist-only --simulation-relist --json`：`ok=true`、`onlineVerified=true`、`reason=item_detail_online`。
- `/api/cc-simulation-gate` 摘要：`simulation_gate_ok=true`、`missing_steps=[]`、`can_unlock_public_sale=false`、`excluded_steps=[real_buyer_payment, final_xianyu_ship_click]`。
- `/api/export-status` 已同步模拟门摘要；Dashboard 截图保存为 `output/playwright/openeverything-simulation-gate-closed.png` 和 `output/playwright/openeverything-simulation-gate-closed-expanded.png`，浏览器 console 无 error/warning。

## [2026-07-07] 老板统一运营入口、替换模式与自动恢复脚本
> 领域: `xianyu` | `backend` | `infra` | `docs`
> 影响模块: `XianyuAdmin`, `CC中转操作台`, `自动健康检查`, `灾备脚本`
> 关联问题: HI-cc-xianyu-auto-ops
### 变更内容
- 新增 `http://127.0.0.1:18800/dashboard` 老板唯一收藏入口，首页聚合首页总览、闲鱼售卖、每日简报、系统维护、帮助中心和技术支持报告。
- 新增 `/api/export-status` / `/export-status` 脱敏状态报告，方便一键发给技术支持；不输出卡密、Token、买家昵称或 API Key。
- 新增 `/api/cc-replacement-mode-test-pack` 与 Dashboard“替换模式模拟验收”，在买家号不可用时可演练模拟下单、发卡、发货、公网注册、兑换、创建 API、导入 CC Switch 和终端调用；正式售卖严格门仍只认新的 `xy_oid_*` 真实小额订单。
- 新增 `auto_health_check.sh`、`auto_recovery.sh`、`local_backup.sh`、`disaster_recovery.sh` 四个自动化脚本：只读健康检查、dry-run 恢复、本地 30 天备份和显式确认灾备恢复。
- 修复 `/dashboard` 被外层 Token 鉴权挡住导致普通浏览器无法先打开登录框的问题；状态报告导出改为页面内携带本地 Token 调 `/api/export-status` 下载，API 仍保持受保护。
- 截图验收过程中按安全流程轮换本机 `OPENCLAW_API_TOKEN`，重启 `ai.openclaw.xianyu`、`ai.openclaw.cc-seller-bridge`、`ai.openclaw.clawbot-agent` 并复验本机接口；未记录任何 Token 值。
- 新增 `GET /api/cc-simulation-gate` 严格模拟门 v2：除“买家真实下单付款”和“最终点击闲鱼发货按钮”外，逐步追踪真实发卡、商品模板/重新上架、买家公网兑换、API Key、CC Switch、终端模型调用、渠道/服务器状态；即使全绿也固定 `can_unlock_public_sale=false`。
- Dashboard“替换模式模拟验收”改为显示严格模拟门逐步状态，脱敏状态报告也带上模拟门缺失项，方便技术支持判断还差哪一步。
- 修复 Intel Brief 菜单契约测试中的旧按钮文案，把旧 `🔍 情报搜索` 同步为当前菜单 `🔍 备用搜索`。
### 文件变更
- `packages/clawbot/src/xianyu/xianyu_admin.py` — Dashboard 别名、统一入口文案、严格模拟门 v2、替换模式清单、脱敏状态报告接口。
- `packages/clawbot/tests/test_xianyu_cc_auto_ship.py` / `test_intel_commercial_mvp.py` — 新增入口/报告/替换模式回归，并修复菜单契约旧文案。
- `scripts/auto_health_check.sh` / `auto_recovery.sh` / `local_backup.sh` / `disaster_recovery.sh` / `auto_ops_scripts.test.mjs` — 自动健康、恢复、备份、灾备脚本和契约测试。
- `docs/081-owner-ops-handbook.md` / `docs/003-docs-index.md` / `docs/006-registries.md` / `docs/007-operations.md` / `docs/009-health.md` — 老板手册、索引、注册表、运维和健康状态同步。
### 验证
- `cd packages/clawbot && .venv312/bin/python -m pytest tests/test_xianyu_cc_auto_ship.py::test_xianyu_admin_dashboard_alias_points_to_owner_console tests/test_xianyu_cc_auto_ship.py::test_xianyu_admin_export_status_returns_redacted_support_report tests/test_xianyu_cc_auto_ship.py::test_xianyu_admin_replacement_mode_pack_keeps_public_sale_locked tests/test_xianyu_cc_auto_ship.py::test_xianyu_admin_manual_paid_order_mark_sent_clears_rescue_but_not_real_order_gate tests/test_xianyu_cc_auto_ship.py::test_xianyu_status_reports_local_bridge_next_action -q`：`5 passed`。
- `cd packages/clawbot && .venv312/bin/python -m pytest tests/test_intel_commercial_mvp.py::test_telegram_menu_contract_reflects_subscription_state_and_supported_commands -q`：`1 passed`。
- `node --test scripts/auto_ops_scripts.test.mjs`：`1 passed`。
- `scripts/auto_health_check.sh --json`：JSON 可解析，健康检查实测返回 `ok=true`。
- `scripts/auto_recovery.sh --dry-run`：只输出拟执行动作，未重启服务。
- `OPENCLAW_BACKUP_DIR=/tmp/openclaw-test-backups scripts/local_backup.sh` + `scripts/disaster_recovery.sh --archive <临时备份> --dry-run`：备份/恢复预演通过，备份包未包含 `.env`。

## [2026-07-07] CC中转操作台重设计与已发卡密后半段补救
> 领域: `xianyu` | `frontend` | `backend` | `docs`
> 影响模块: `XianyuAdmin`, `XianyuContextManager`, `CC中转卖家桥接器`, `CC中转操作台`
> 关联问题: HI-cc-xianyu-auto-ops
### 变更内容
- 重新设计本机 `http://127.0.0.1:18800/` CC中转操作台：改为 Apple 风格深色状态面板，首屏只回答老板日常 6 件事：当前能不能卖、自动发货是否开着、库存是否够、上游余额是否同步、是否有待处理订单、是否需要介入；商品绑定、漏单兜底、巡检和高级排障默认折叠。
- 补齐“已发卡密 → 点击闲鱼发货”后半段独立运行路径：新增本机只读候选接口 `/api/cc-xianyu-confirm/current-page-candidate`，允许 `xy_manual_*` / `xy_browser_*` 这类已发卡密的生产内测补救单，在当前闲鱼页面明确可见“已付款/待发货”信号时继续点击“去发货/无需物流/确认发货”。
- 桥接器主循环新增独立 `confirms` 阶段：即使没有新的待发送话术，也会单独检查当前打开闲鱼页是否可执行确认发货；页面没有付款信号时返回 `no_paid_order_signal` 并安全跳过。
- 正式售卖严格门没有放宽：`xy_manual_*` / `xy_browser_*` 仍不进入正式 `xy_oid_*` 严格门，只能作为生产内测/补救证据。
- 发现 Playwright 验证脚本曾把本机 API Token 回显到工具输出，已立即轮换 `OPENCLAW_API_TOKEN`，重启 `ai.openclaw.xianyu`、`ai.openclaw.cc-seller-bridge` 和 `ai.openclaw.clawbot-agent`，并复验本机 18800/18790 链路正常；未在文档记录任何 Token 值。
### 文件变更
- `packages/clawbot/src/xianyu/xianyu_admin.py` — 新增当前页面确认发货补救候选接口，重做操作台 UI，补空 favicon 避免浏览器误报 401 噪音。
- `packages/clawbot/src/xianyu/xianyu_context.py` — 状态摘要新增 `xianyu_confirm_page_pending`，让操作台能提示“已发卡密但待页面点击发货”。
- `scripts/cc_zhongzhuan_seller_bridge.mjs` — 主循环新增独立确认发货巡检，正式队列为空时才走当前页面补救候选。
- `packages/clawbot/tests/test_xianyu_cc_auto_ship.py` / `packages/clawbot/tests/test_api_routes_regression.py` — 增加手工内测单后半段补救回归，更新操作台静态结构守护。
- `docs/002-changelog.md` / `docs/006-registries.md` / `docs/007-operations.md` / `docs/009-health.md` — 同步操作方式、接口登记和当前状态。
### 验证
- `cd packages/clawbot && .venv312/bin/python -m pytest tests/test_xianyu_cc_auto_ship.py tests/test_social_extension_status.py tests/test_api_routes_regression.py -q`：`[100%]`，exit 0。
- `cd packages/openclaw-npm/assets/chrome-extension && node --test test/popup-static.test.mjs test/social-page-runner.test.mjs`：`47 passed / 0 failed`。
- `cd apps/frist-api && node --test tests/*.test.mjs`：`185 passed / 0 failed`。
- `node scripts/cc_zhongzhuan_seller_bridge.mjs --once --json`：`ok=true`、`xianyuTabs=1`、`bridgeStatusPosted=true`；当前打开页无已付款信号，`deliveries/confirms` 均安全跳过。
- `node scripts/cc_zhongzhuan_readiness_audit.mjs --mode=read_only --json`：`ok=true`，库存 `36`、启用兑换码 `36`、启用渠道 `2`、补救队列 `0`。
- `node scripts/cc_zhongzhuan_readiness_audit.mjs --require-real-order --json`：`ok=false`，原因是尚无新的 `xy_oid_*` 真实闲鱼自动订单；这是正式售卖安全锁，不是系统故障。
- Playwright 视觉验证：`output/playwright/cc-ops-console-redesign-20260707-final.png`，控制台 `0 error / 0 warning`，首屏 6 张状态卡齐全，提示旧测试单“打开已付款测试单页面”。

## [2026-07-07] CC中转方案 B 商品绑定稳健性与生产内测复核
> 领域: `xianyu` | `backend` | `docs`
> 影响模块: `XianyuContextManager`, `XianyuAdmin`, `CC中转卖家桥接器`
> 关联问题: HI-cc-xianyu-auto-ops
### 变更内容
- 商品套餐绑定现在兼容三种输入：完整闲鱼分享文本、短链接本体、短链接加 `CZ007` 分享码；后续真实订单/浏览器桥接只回传短链接时，也能命中已绑定套餐。
- 已重启本机 `ai.openclaw.xianyu` 服务加载新规则，并重新拉起卖家专用 Chromium；本机桥接器可连接调试端口，当前无已付款信号时安全跳过。
- 保持正式售卖严格门不放宽：生产内测巡检通过，但 `--require-real-order` 仍因尚无新的 `xy_oid_*` 真实闲鱼自动订单而失败，这是预期阻断。
### 文件变更
- `packages/clawbot/src/xianyu/xianyu_context.py` — `get_cc_item_mapping()` 增加短链/分享文本兜底命中。
- `packages/clawbot/tests/test_xianyu_cc_auto_ship.py` — 增加完整分享文本、短链接和带分享码三种命中回归。
- `docs/002-changelog.md` / `docs/007-operations.md` / `docs/009-health.md` — 同步当前生产内测状态和老板商品绑定口径。
### 验证
- `cd packages/clawbot && .venv312/bin/python -m pytest tests/test_xianyu_cc_auto_ship.py tests/test_social_extension_status.py tests/test_api_routes_regression.py -q`：`[100%]`，exit 0。
- `cd packages/openclaw-npm/assets/chrome-extension && node --test test/popup-static.test.mjs test/social-page-runner.test.mjs`：`47 passed / 0 failed`。
- `cd apps/frist-api && node --test tests/*.test.mjs`：`185 passed / 0 failed`。
- `node scripts/cc_zhongzhuan_seller_bridge.mjs --once --json`：`ok=true`、`xianyuTabs=1`，当前无已付款信号，安全跳过。
- `node scripts/cc_zhongzhuan_readiness_audit.mjs --mode=read_only --json`：`ok=true`；`--require-real-order`：`ok=false`，唯一原因是尚无新的 `xy_oid_*` 真实闲鱼付款自动订单。
- Oracle runtime 只读核验：`upstreamBalance.level=ok`，warning/critical 阈值为 `50/20` 元；今日自动补库存事件曾创建 `32` 张，后续后台巡检创建 `0` 张，说明安全库存已补齐。

## [2026-07-07] CC中转正式售卖门历史摘要防误导
> 领域: `xianyu` | `backend` | `docs`
> 影响模块: `XianyuAdmin`, `CC中转严格门`, `API Routes Regression`
> 关联问题: HI-cc-xianyu-auto-ops
### 变更内容
- 修正本机看板严格门历史摘要：旧的 `xy_manual_*` / `xy_browser_*` 内测单即使完成买家链路，也不再在摘要里显示为“真实自动订单”。
- 严格门展示层现在只把 `xy_oid_*` 且 `ready=true` 的订单计入 `real_orders`；旧历史摘要会附加内部提示，避免老板误以为可以正式售卖。
- 更新旧回归用例，避免 `xy_buyer` 这类非真实订单前缀继续被测试当成正式闭环。
### 文件变更
- `packages/clawbot/src/xianyu/xianyu_admin.py` — 严格门摘要脱敏/规整时只统计 `xy_oid_*` 自动订单。
- `packages/clawbot/tests/test_xianyu_cc_auto_ship.py` / `packages/clawbot/tests/test_api_routes_regression.py` — 增加手工单不计真实订单摘要的回归，并修正旧前缀测试数据。
- `docs/002-changelog.md` / `docs/009-health.md` — 同步当前生产内测口径。
### 验证
- `cd packages/clawbot && .venv312/bin/python -m pytest tests/test_xianyu_cc_auto_ship.py tests/test_social_extension_status.py tests/test_api_routes_regression.py -q`：`[100%]`，exit 0。
- `cd apps/frist-api && node --test tests/*.test.mjs`：`185 passed / 0 failed`。
- `cd packages/openclaw-npm/assets/chrome-extension && node --test test/popup-static.test.mjs test/social-page-runner.test.mjs`：`47 passed / 0 failed`。
- `git diff --check`：exit 0。

## [2026-07-07] CC中转方案 B 决策确认与套餐默认源收口
> 领域: `xianyu` | `backend` | `docs`
> 影响模块: `Frist-API`, `CC中转操作台`, `Chrome Seller Launcher`
> 关联问题: HI-cc-xianyu-auto-ops
### 变更内容
- 老板已确认方案 B：套餐按 `1元测试 / 5 / 15 / 50 / 100 / 500` 六档执行，库存按安全水位自动补，上游余额每天同步一次，低于 50 元提醒、低于 20 元严重提醒。
- 修正 Frist-API 默认套餐源漂移：`server.js` 已是六档套餐，公共 `shared.js` 仍残留旧 `codex-30-*` 默认值，现已统一为六档，避免桥接/目录默认值和生产套餐不一致。
- 已把 `shared.js` 单文件同步到 Oracle `/opt/frist-api/apps/frist-api/server/shared.js`，同步前创建远端备份 `/opt/frist-api/backups/shared.js-before-cc-plan-default-20260707T132748Z.bak`，并重启 `frist-api.service`。
- 卖家专用 Chrome 启动器保持“准备运行版插件目录 + 打开入口”的定位：Google Chrome 不允许命令行自动加载 unpacked extension，仍需老板在 `chrome://extensions` 手动加载一次 `~/.openclaw/cc-social-pilot-runtime-extension`。
- 继续保持生产内测口径：普通巡检可绿，正式售卖严格门不放宽，必须等新的 `xy_oid_*` 真实闲鱼付款订单完成买家链路后才允许公开售卖。
### 文件变更
- `apps/frist-api/server/shared.js` — 默认充值套餐统一为 CC中转六档。
- `docs/002-changelog.md` / `docs/006-registries.md` / `docs/007-operations.md` / `docs/009-health.md` — 同步方案 B 已确认口径、插件加载路径和严格门状态。
### 验证
- `node --check scripts/cc_zhongzhuan_launch_seller_chrome.mjs`、`node --check scripts/cc_zhongzhuan_configure_seller_extension.mjs` 与 Frist-API 关键 server 文件语法检查：exit 0。
- `cd apps/frist-api && node --test tests/*.test.mjs`：`185 passed / 0 failed`。
- `cd packages/clawbot && .venv312/bin/python -m pytest tests/test_xianyu_cc_auto_ship.py tests/test_social_extension_status.py -q`：跑到 `[100%]`，exit 0。
- `cd packages/openclaw-npm/assets/chrome-extension && node --test test/popup-static.test.mjs test/social-page-runner.test.mjs`：`47 passed / 0 failed`。
- `node scripts/cc_zhongzhuan_launch_seller_chrome.mjs --dry-run --json`：`ok=true`，`manualExtensionLoadRequired=true`。
- Oracle 复验：`frist-api.service` / `openclaw-newapi.service` / `apache2` active，`systemctl --failed` 为 `0 loaded units listed`，公网主站 HTTP 200，未授权 `/v1/models` HTTP 401。
- `node scripts/cc_zhongzhuan_readiness_audit.mjs --json`：`ok=true`；`--require-real-order`：`ok=false`，正确原因是尚无新的 `xy_oid_*` 真实自动订单。

## [2026-07-07] CC中转方案 B 浏览器助手加载状态提示修正
> 领域: `xianyu` | `backend` | `docs`
> 影响模块: `XianyuAdmin`, `Chrome Social Pilot`, `CC中转操作台`
> 关联问题: HI-cc-xianyu-auto-ops
### 变更内容
- 本机实机复核发现 Chrome 仍只有旧社媒插件心跳，没有检测到 `OpenEverything Social Pilot` 扩展已加载；操作台之前只提示“刷新扩展”，容易误导老板。
- `cc_chrome_extension` 摘要新增 Social Pilot 加载检测字段；当未检测到本项目插件目录时，下一步明确提示在 `chrome://extensions` 加载运行版插件目录 `~/.openclaw/cc-social-pilot-runtime-extension`，而不是笼统刷新。
- 保持正式售卖严格门不放宽：代码/后台可继续生产内测，但浏览器兜底自动点发货/恢复上架必须等 Chrome 真正加载新版插件后才算启用。
### 文件变更
- `packages/clawbot/src/xianyu/xianyu_admin.py` — 新增 Social Pilot 浏览器配置只读检测，并修正 `cc_chrome_extension.next_action`。
- `packages/clawbot/tests/test_xianyu_cc_auto_ship.py` — 增加未加载插件与旧心跳场景回归。
- `docs/007-operations.md` / `docs/009-health.md` — 同步当前实机状态和老板操作步骤。
### 验证
- `python3 -m py_compile packages/clawbot/src/xianyu/xianyu_admin.py`：exit 0。
- `cd packages/clawbot && .venv312/bin/python -m pytest tests/test_xianyu_cc_auto_ship.py::test_xianyu_status_reports_chrome_extension_global_watch_capability tests/test_xianyu_cc_auto_ship.py::test_xianyu_status_marks_stale_chrome_extension_heartbeat_offline tests/test_social_extension_status.py::test_social_extension_status_preserves_known_cc_capabilities_when_old_payload_arrives -q`：`3 passed / 0 failed`。
- 重启 `ai.openclaw.xianyu` 后，`/api/status.cc_chrome_extension` 返回 `social_pilot_installed=false`、`supports_paid_page_dispatch=false`、`supports_relist_queue=false`，下一步提示运行 `make cc-seller-chrome` 并加载运行版插件目录 `~/.openclaw/cc-social-pilot-runtime-extension`。

## [2026-07-07] CC中转方案 B 浏览器付款页兜底与严格门口径收紧
> 领域: `xianyu` | `backend` | `frontend`
> 影响模块: `XianyuAdmin`, `Chrome Social Pilot`, `XianyuLive`, `CC中转严格门`
> 关联问题: HI-cc-xianyu-auto-ops
### 变更内容
- 闲鱼卖家订单列表 API 当前对本机登录态返回 `PERMISSION_EXCEPTION::无权限访问`，不能作为全自动发货唯一通道；新增 Chrome 付款页兜底：在可见闲鱼聊天/订单页检测到“已付款/待发货”信号且没有待发送话术时，插件会调用本机受保护的 `/api/cc-manual-paid-order/dispatch` 生成卡密话术，再填入发送。
- 浏览器兜底订单统一使用 `xy_browser_*` 前缀；手工/浏览器兜底单可以完成内测发货，但不再冒充 `xy_oid_*` 卖家订单接口真实自动订单，正式售卖严格门只认 `xy_oid_*`。
- 后端确认发货补强：订单轮询拿到真实数字订单号时只在内存里用于 `confirm_dummy_shipment()`，本机数据库仍保存脱敏 `xy_oid_*`，避免泄露真实闲鱼订单号。
- 恢复可售补齐队列入口 `/api/cc-xianyu-relist/next`；只有 `message_sent` 且闲鱼确认发货状态为 `confirmed` 的记录才进入恢复上架候选，页面仍需看到“已下架/已售罄 + 重新上架按钮”才会点击。
- Chrome 插件能力上报新增 `paid_page_dispatch`、`relist_queue_watch`、`xianyu_confirm_shipment`、`xianyu_relist_item`，操作台能区分旧插件和新版付款页/恢复上架能力。
### 文件变更
- `packages/clawbot/src/xianyu/xianyu_live.py` — 真实订单号只在内存中用于确认发货，落库仍使用脱敏订单号。
- `packages/clawbot/src/xianyu/xianyu_admin.py` / `packages/clawbot/src/xianyu/xianyu_context.py` — 恢复上架队列、严格门真实订单口径、浏览器兜底订单前缀。
- `packages/openclaw-npm/assets/chrome-extension/background.js` / `popup.js` — 付款页自动生成待发货话术、恢复上架队列定时巡检、新能力心跳。
- `packages/clawbot/src/api/rpc.py` — Chrome 插件状态白名单新增新版 CC中转能力字段。
- `packages/clawbot/tests/test_xianyu_cc_auto_ship.py` / `test_social_extension_status.py` / `packages/openclaw-npm/assets/chrome-extension/test/*` — 增加真实订单口径、浏览器兜底、恢复上架和插件能力回归测试。
### 验证
- `python3 -m py_compile packages/clawbot/src/api/rpc.py packages/clawbot/src/xianyu/xianyu_live.py packages/clawbot/src/xianyu/xianyu_admin.py packages/clawbot/src/xianyu/xianyu_context.py packages/clawbot/src/xianyu/xianyu_apis.py`：exit 0。
- `cd packages/clawbot && .venv312/bin/python -m pytest tests/test_xianyu_cc_auto_ship.py tests/test_social_extension_status.py -q`：`[100%]`，0 failed。
- `cd packages/openclaw-npm/assets/chrome-extension && node --check background.js && node --check popup.js && node --check social-page-runner.js && node --test test/popup-static.test.mjs test/social-page-runner.test.mjs`：`47 passed / 0 failed`。
- `cd apps/frist-api && node --test tests/server.test.mjs --test-name-pattern "auto replenishes Xianyu|starts Xianyu card auto replenishment|syncs New-API upstream balance"`：`112 passed / 0 failed`。
- 本机运行态：`ai.openclaw.xianyu` active，`/api/status` HTTP 200，WebSocket/Cookie 正常，自动发货未暂停，补救队列 0，确认发货/恢复上架队列均为空。
- 生产内测只读巡检：`node scripts/cc_zhongzhuan_readiness_audit.mjs --json` 返回 `ok=true`；正式售卖严格门 `--require-real-order` 返回 `ok=false`，正确原因是尚未产生新的 `xy_oid_*` 真实闲鱼自动发货订单。
### 当前边界
- 当前 Chrome 已上报旧能力，仍需老板手动刷新一次 unpacked Chrome 扩展，才能启用新版 `paid_page_dispatch/relist_queue_watch`。
- 旧手工兜底内测单不再算正式售卖真实自动订单；下一步要用另一个账号跑 1 元测试单，产生 `xy_oid_*` 后再复验严格门。



## [2026-07-07] CC中转方案 B 生产部署与 6 档库存收口
> 领域: `xianyu` | `backend` | `deploy`
> 影响模块: `CC中转`, `Frist-API`, `Oracle`, `XianyuAdmin`
> 关联问题: HI-cc-xianyu-auto-ops
### 变更内容
- 已将本地 Frist-API 方案 B 改动同步到 Oracle 生产内测服务，远端备份后重启 `frist-api.service`，`openclaw-newapi.service` 保持 active。
- 生产套餐从旧 `codex-30-*` 收口为老板确认的 6 档：`1元测试 / 5 / 15 / 50 / 100 / 500`，并执行一次自动补库存，当前 6 档安全库存已补齐。
- 远端开启 `FRIST_API_CARD_AUTOREPLENISH_ENABLED=1`、`FRIST_API_UPSTREAM_BALANCE_SYNC_ENABLED=1`、`FRIST_API_RATE_MARKUP=0.1` 和 New-API 兑换状态同步；上游余额同步结果为 `level=ok`。
- 本机闲鱼商品映射和默认套餐改为 `xianyu-test-1`，下一笔测试单默认发 1 元测试档。
- 安全修正：`xy_manual_*` 手工兜底单没有真实闲鱼数字订单号，不再进入浏览器“自动点击闲鱼发货按钮”队列，避免旧兜底单卡队列或误点页面。
- Docker Compose 补齐方案 B 环境变量透传，避免未来容器化启动时自动补库存/余额同步开关丢失。
### 文件变更
- `docker-compose.frist-api.yml` — 透传自动补库存、上游余额同步、倍率、New-API 兑换状态同步和闲鱼 webhook token。
- `packages/clawbot/src/xianyu/xianyu_admin.py` — 确认发货队列只接收真实数字闲鱼订单号，手工兜底单自动标记 skipped。
- `packages/clawbot/tests/test_xianyu_cc_auto_ship.py` — 增加手工兜底单跳过确认发货队列的回归测试。
- `docs/002-changelog.md` / `docs/006-registries.md` / `docs/009-health.md` — 同步生产内测状态。
### 验证
- `cd apps/frist-api && node --test tests/server.test.mjs --test-name-pattern "auto replenishes Xianyu|starts Xianyu card auto replenishment|syncs New-API upstream balance"`：`112 passed / 0 failed`。
- `cd packages/openclaw-npm/assets/chrome-extension && node --test test/popup-static.test.mjs test/social-page-runner.test.mjs`：`47 passed / 0 failed`。
- `cd packages/clawbot && .venv312/bin/python -m pytest tests/test_xianyu_cc_auto_ship.py::test_xianyu_admin_confirm_shipment_queue_returns_sent_unconfirmed_order tests/test_xianyu_cc_auto_ship.py::test_xianyu_admin_confirm_shipment_queue_skips_manual_orders tests/test_xianyu_cc_auto_ship.py::test_xianyu_admin_confirm_shipment_mark_routes_update_status -q`：`3 passed / 0 failed`。
- Oracle 生产内测 smoke：`https://jiyu.245334.xyz/` HTTP 200，`/v1/models` 无 token HTTP 401，`frist-api.service` / `openclaw-newapi.service` active，6 档库存 `3/10/10/5/3/1` 已补齐，上游余额同步 `level=ok`。
- 严格巡检：`node scripts/cc_zhongzhuan_readiness_audit.mjs --require-real-order --json` 应继续返回 `ok=false`，直到出现新的 `xy_oid_*` 真实闲鱼付款订单并完成买家兑换、创建 API Key、CC Switch 导入和调模型证据；公网主站、CC Switch 导入入口、兑换/创建 Key/调模型基础证据仍在。

## [2026-07-07] CC中转方案 B 自动运营闭环增强
> 领域: `xianyu` | `backend` | `frontend`
> 影响模块: `CC中转`, `Frist-API`, `Chrome Social Pilot`, `XianyuAdmin`
> 关联问题: HI-cc-xianyu-auto-ops
### 变更内容
- 按老板确认的方案 B，补齐套餐档位 `1/5/15/50/100/500` 的库存自动补卡，并将自动补卡从管理按钮接入服务后台定时启动。
- 新增 New-API 上游余额同步与低余额预警配置，默认 warning 50 元、critical 20 元。
- Chrome 闲鱼发货助手在发送卡密话术成功后，会继续在当前闲鱼页面安全点击“去发货/无需物流/确认发货”，并回写确认结果；页面缺少已付款信号时不点击。
- 新增恢复可售兜底：只有商品页明确显示“已下架/已售罄/重新上架”时才点击恢复上架；不改标题、不改价格、不新建商品。
- `cc_shipments` 增加闲鱼确认发货与恢复上架状态字段，便于补救队列和生产内测追踪。
### 文件变更
- `apps/frist-api/server/server.js` / `apps/frist-api/tests/server.test.mjs` — 自动补卡后台定时、余额同步测试、档位验证。
- `packages/clawbot/src/xianyu/xianyu_context.py` / `packages/clawbot/src/xianyu/xianyu_admin.py` — 确认发货、恢复上架队列和回写 API。
- `packages/openclaw-npm/assets/chrome-extension/background.js` / `social-page-runner.js` / `test/social-page-runner.test.mjs` — 浏览器确认发货与恢复上架页面执行器。
- `apps/frist-api/deploy/production.env.example` / `packages/clawbot/config/.env.example` / `docs/006-registries.md` — 生产配置和注册表同步。
### 验证
- `cd packages/openclaw-npm/assets/chrome-extension && node --check background.js && node --check popup.js && node --check social-page-runner.js && node --test test/popup-static.test.mjs test/social-page-runner.test.mjs`：`47 passed / 0 failed`。
- `cd packages/clawbot && .venv312/bin/python -m py_compile src/xianyu/xianyu_context.py src/xianyu/xianyu_admin.py && .venv312/bin/python -m pytest tests/test_xianyu_cc_auto_ship.py tests/test_social_extension_status.py -q`：相关 Python 测试通过到 `[100%]`。
- `cd apps/frist-api && node --test tests/server.test.mjs --test-name-pattern "auto replenishes Xianyu|starts Xianyu card auto replenishment|syncs New-API upstream balance"`：`112 passed / 0 failed`。


## [2026-07-07] Intel Brief production-once 入口与 launch package 升级
> 领域: `backend` | `infra` | `docs`
> 影响模块: `Intel Brief`, `Production Once`, `Launch Package`
> 关联问题: IntelBrief-PhaseQ
### 变更内容
- 新增 `intel_production_once.py`，作为未来 scheduler 的真实一次性入口；缺门禁时不联网。
- launchd dry-run package 改为调用 production-once，而不是占位 `--help`。
- 当前由于私有 env 未写入且缺 production ack，production-once 正确 blocked。
### 文件变更
- `packages/clawbot/src/intel/production_once.py` / `packages/clawbot/scripts/intel_production_once.py`。
- `packages/clawbot/src/intel/launch_package.py` / `packages/clawbot/scripts/intel_launch_package.py`。
- `packages/clawbot/tests/test_intel_production_once.py` / `packages/clawbot/tests/test_intel_launch_package.py`。
### 验证
- Production-once blocked evidence：`packages/clawbot/data/intel_evidence/phaseq/20260707T031446Z-production-once-private-env-blocked.json`。
- Launch package evidence：`packages/clawbot/data/intel_evidence/phaseq/20260707T031446Z-launchd-production-once-dry-run-package.json`。
- 最终验证 evidence 见 Phase Q verification。


## [2026-07-07] Intel Brief 私有 env 与 launchd dry-run package
> 领域: `backend` | `infra` | `docs`
> 影响模块: `Intel Brief`, `Private Env`, `Launch Package`, `Scheduler Gate`
> 关联问题: IntelBrief-PhaseP
### 变更内容
- 新增私有 env 写入/审计工具，默认 `.openclaw/intel-brief.production.env`，权限 0600，证据脱敏。
- Scheduler gate 支持 `INTEL_BRIEF_PRIVATE_ENV` 合并私有 env 后判定，但不输出明文。
- 新增 launchd dry-run package 生成器，只生成 plist/README/rollback，不安装、不加载。
- 当前剪贴板没有可识别 token，真实私有 env 未写入；readiness 保持 `ready=3/5`。
### 文件变更
- `packages/clawbot/src/intel/private_env.py` / `packages/clawbot/scripts/intel_private_env.py`。
- `packages/clawbot/src/intel/launch_package.py` / `packages/clawbot/scripts/intel_launch_package.py`。
- `packages/clawbot/src/execution/intel_brief.py`。
- `packages/clawbot/tests/test_intel_private_env.py` / `tests/test_intel_launch_package.py` / `tests/test_intel_scheduler_gate.py`。
### 验证
- Private env audit：`packages/clawbot/data/intel_evidence/phasep/20260707T030509Z-private-env-audit-redacted.json`。
- Launch package dry-run：`packages/clawbot/data/intel_evidence/phasep/20260707T030509Z-launchd-dry-run-package.json`。
- Readiness private-env path：`packages/clawbot/data/intel_evidence/phasep/20260707T030727Z-readiness-private-env-path-blocked.json`。
- 最终验证 evidence：`packages/clawbot/data/intel_evidence/phasep/20260707T030858Z-phase-p-private-env-launch-verification.json`。


## [2026-07-07] Intel Brief 真实 Telegram sandbox 与 SGW preferred worker 闭合
> 领域: `backend` | `infra` | `docs`
> 影响模块: `Intel Brief`, `Telegram Delivery`, `SGW Worker`, `Collect Once`
> 关联问题: IntelBrief-PhaseO
### 变更内容
- 使用本机剪贴板 token 作为一次性 env 完成真实 Telegram sandbox delivery；证据脱敏，不写 token/chat id。
- 真实验证 SGW SSH/Python，并发现 remote runner 无依赖场景不应强制 venv；修复后 SGW `senate_trading` 成功。
- `senate_trading` 默认 collect worker 从 oracle-arm1 fallback 升级为 `oracle-sg-west-preferred-overseas`。
- 使用 SGW + Yanhuoyun 完成 collect-once 与 scheduled sandbox，readiness 提升为 `ready=3/5`。
### 文件变更
- `packages/clawbot/scripts/intel_worker_remote_run.py` / `packages/clawbot/scripts/intel_collect_once.py`。
- `packages/clawbot/tests/test_intel_worker_remote_runner.py` / `packages/clawbot/tests/test_intel_collect_once.py`。
- `docs/052-intel-brief-master-plan.md` / `docs/084-intel-brief-implementation-report.md` / `docs/009-health.md` / VPS-Config Intel Brief placement docs。
### 验证
- Telegram success：`packages/clawbot/data/intel_evidence/phasel/20260707T024537Z-telegram-local-bootstrap-real-sandbox.json`。
- SGW worker success：`packages/clawbot/data/intel_evidence/phasen/20260707T024852Z-sgw-senate-worker-remote-run-system-python.json`。
- SGW+Yanhuoyun collect：`packages/clawbot/data/intel_evidence/phasen/20260707T025103Z-collect-once-sgw-senate-yanhuoyun-akshare.json`。
- Readiness 3/5：`packages/clawbot/data/intel_evidence/phasen/20260707T025328Z-production-readiness-sgw-placement-confirmed.json`。
- 最终验证 evidence：`packages/clawbot/data/intel_evidence/phasen/20260707T025535Z-phase-o-telegram-sgw-verification.json`。


## [2026-07-07] Intel Brief production runner 合同闭合
> 领域: `backend` | `infra` | `docs`
> 影响模块: `Intel Brief`, `ExecutionScheduler`, `Production Readiness`
> 关联问题: IntelBrief-PhaseN
### 变更内容
- Production gate 新增 summary evidence 与 Telegram sandbox ack 校验，不再用 `production_runner_not_implemented` 永久阻断。
- `ExecutionScheduler._run_intel_brief()` 新增 production branch，gate ready 后可调用注入 production runner 或默认 Telegram summary delivery probe。
- 当前 readiness 仍 blocked，但阻断原因已收敛为真实外部门槛：token/chat/ack/worker placement/production ack。
### 文件变更
- `packages/clawbot/src/execution/intel_brief.py` / `packages/clawbot/src/execution/scheduler.py`。
- `packages/clawbot/tests/test_intel_scheduler_gate.py` / `packages/clawbot/tests/test_intel_production_readiness.py`。
- `docs/052-intel-brief-master-plan.md` / `docs/084-intel-brief-implementation-report.md` / `docs/009-health.md` / VPS-Config Intel Brief placement docs。
### 验证
- 新 readiness evidence：`packages/clawbot/data/intel_evidence/phasem/20260707T024108Z-production-readiness-runner-contract-audit.json` → `status=blocked`、`ready=2/5`、`network_calls=0`，且不再包含 `production_runner_not_implemented`。
- 最终验证 evidence：`packages/clawbot/data/intel_evidence/phasem/20260707T024229Z-production-runner-contract-verification.json`。


## [2026-07-07] Intel Brief production readiness 与 Telegram 本机自举助手
> 领域: `backend` | `infra` | `docs`
> 影响模块: `Intel Brief`, `Production Readiness`, `Telegram Delivery`
> 关联问题: IntelBrief-PhaseM
### 变更内容
- 新增只读 production readiness 聚合器与 CLI，统一汇总 collect、summary、Telegram、scheduler 和 worker placement 门槛。
- 新增 Telegram 本机沙盒自举助手：支持隐藏 token 输入、本机 Telegram deep link、轮询 `/start intel_brief_sandbox` 自动发现 chat id，并在门槛齐备时发送真实 summary sandbox 消息。
- 当前真实网络仍未调用：运行环境没有安全注入 token/ack，chat id 尚未发现，production runner 仍显式未实现。
### 文件变更
- `packages/clawbot/src/intel/production_readiness.py` / `packages/clawbot/scripts/intel_production_readiness_audit.py` / `packages/clawbot/tests/test_intel_production_readiness.py`。
- `packages/clawbot/src/intel/telegram_bootstrap.py` / `packages/clawbot/scripts/intel_telegram_local_bootstrap.py` / `packages/clawbot/tests/test_intel_telegram_bootstrap.py`。
- `docs/052-intel-brief-master-plan.md` / `docs/084-intel-brief-implementation-report.md` / `docs/006-registries.md` / `docs/009-health.md` / VPS-Config Intel Brief placement docs。
### 验证
- readiness evidence：`packages/clawbot/data/intel_evidence/phasem/20260707T020329Z-production-readiness-audit.json` → `status=blocked`、`ready=2/5`、`network_calls=0`。
- Telegram local bootstrap gate evidence：`packages/clawbot/data/intel_evidence/phasel/20260707T021607Z-telegram-local-bootstrap-gate-blocked.json` → 缺 token runtime 注入/ack/real-network allow，`network_calls=0`。
- 单测：`tests/test_intel_telegram_bootstrap.py` 已覆盖 hidden-token 自举路径的关键合同；最终验证 evidence：`packages/clawbot/data/intel_evidence/phasem/20260707T022907Z-production-readiness-bootstrap-verification.json`。

## [2026-07-07] CC中转真实买家链路内测通过（旧严格门口径）
> 领域: `xianyu` | `deploy` | `docs`
> 影响模块: `Xianyu Delivery`, `New-API`, `CC Switch`, `Readiness Audit`
> 关联问题: HI-907
### 变更内容
- 以买家视角跑完当前真实内测单：已发卡密在生产 New-API 中完成兑换到账，生成买家专用 API Key，并通过公网 `https://jiyu.245334.xyz/v1` 完成模型调用。
- CC Switch 导入合同已验证：导入链接 scheme、Base URL、API Key 参数和默认模型字段齐全；`/v1/models` 对买家 Key 返回 200，模型列表可读。
- 清理了本轮调试中手工插入但无效的测试 Key，仅保留 New-API 官方接口创建的买家 Key，避免干扰后续运营。
- 当时的旧严格门曾把该内测单计为 `ok=true`；2026-07-07 后续已收紧口径，`xy_manual_*` / `xy_browser_*` 只算内测或补救，正式售卖严格门必须等待新的 `xy_oid_*` 真实自动订单证据。
### 文件变更
- `docs/002-changelog.md` / `docs/009-health.md` / `/Users/blackdj/Documents/VPS-Config/docs/05-unified-execution-plan.md` — 同步真实内测单闭环通过状态。
### 验证
- 买家 Key 公网 `/v1/models` → HTTP 200，模型数 15。
- 买家 Key 公网 `/v1/chat/completions`（`gpt-5.4-mini`）→ HTTP 200，并在 New-API logs 中出现同买家模型调用记录。
- CC Switch 导入合同 → `ccswitch://v1/import`、`baseURL=https://jiyu.245334.xyz/v1`、`apiKey` 存在、默认模型 `gpt-5.4-mini`。
- `/api/cc-buyer-chain-progress` → `stage=verified`，发货/兑换/API Key/模型调用/同单验证五步均为 true。
- `/api/cc-loop-watch` → 旧口径曾显示 `stage=closed_loop_verified`；当前口径以新的 `xy_oid_*` 严格门为准。
- `node scripts/cc_zhongzhuan_readiness_audit.mjs --require-real-order --json` → 旧口径曾返回 `ok=true`；当前正式售卖前必须重新跑真实小额自动订单严格门。



## [2026-07-07] CC中转真实闲鱼测试单已发送，等待买家自助链路
> 领域: `xianyu` | `docs`
> 影响模块: `Xianyu Delivery`, `Readiness Audit`, `Operations Docs`
> 关联问题: HI-907
### 变更内容
- 获老板明确确认后，接管当前 Chrome 闲鱼聊天页，只读复查页面仍为 1 元测试单、已付款待发货状态、输入框为空且发送按钮可用。
- 将本机已分配的发货话术发送到该买家聊天，并调用本机 `mark-sent` 标记履约记录；`cc_shipments.id=1` 已从 `manual_delivery_ready` 变为 `message_sent`。
- 补救队列已清零：`/api/cc-browser-delivery/next` 返回 `hasPending=false`，不再有待浏览器发货记录。
- 严格门仍按预期未放行正式售卖：真实闲鱼发货证据已通过，但买家尚未完成兑换到账、创建 API Key、CC Switch 导入和调模型。
### 文件变更
- `docs/002-changelog.md` / `docs/009-health.md` / `/Users/blackdj/Documents/VPS-Config/docs/05-unified-execution-plan.md` — 同步真实测试单当前状态。
### 验证
- Chrome 当前闲鱼页发送后只读校验：输入框已清空，聊天中出现兑换入口和 CC Switch 操作提示。
- `POST /api/cc-shipments/1/mark-sent` → `{"ok": true, "status": "message_sent"}`。
- `/api/cc-sale-readiness` → `pending_rescue=0`、`real_order_seen=true`、`ready_for_public_sale=false`。
- `node scripts/cc_zhongzhuan_readiness_audit.mjs --require-real-order --json` → `ok=false`，正确原因是同单买家链路尚未完成。

## [2026-07-07] CC中转 Chrome 发货助手后台心跳与状态防漂移
> 领域: `xianyu` | `frontend` | `backend` | `docs`
> 影响模块: `Chrome Extension`, `Social Extension Status`, `XianyuAdmin`
> 关联问题: HI-907
### 变更内容
- Chrome 发货助手新增后台心跳：后台 keepalive / 看守闹钟 / 启动事件会自动向本机上报新版发货能力，不再完全依赖老板手动打开插件弹窗。
- 本机操作台新增插件状态新鲜度判断：状态文件超过 15 分钟未更新时不再继续显示为在线，避免旧心跳误导生产检查。
- 后端保存社媒插件状态时会保留已知 CC 发货能力位，避免旧插件动作或普通社媒心跳把 `extension.capabilities` 覆盖成空。
- 当前真实内测单仍未外发：严格门继续正确阻断在 `pendingRescue=1`，等待老板明确确认发送真实买家消息。
### 文件变更
- `packages/openclaw-npm/assets/chrome-extension/background.js` — 新增后台发货能力心跳。
- `packages/openclaw-npm/assets/chrome-extension/test/popup-static.test.mjs` — 增加后台心跳防回归断言。
- `packages/clawbot/src/api/rpc.py` — 保留已知发货能力位，支持 `background_heartbeat`。
- `packages/clawbot/src/xianyu/xianyu_admin.py` — 插件心跳超过 15 分钟即判定需刷新。
- `packages/clawbot/tests/test_social_extension_status.py` / `packages/clawbot/tests/test_xianyu_cc_auto_ship.py` — 增加能力保留和过期心跳测试。
### 验证
- `cd packages/openclaw-npm/assets/chrome-extension && node --check background.js && node --test test/popup-static.test.mjs` → `29 passed / 0 failed`。
- `cd packages/clawbot && .venv312/bin/python -m pytest tests/test_social_extension_status.py tests/test_xianyu_cc_auto_ship.py -q` → 跑到 `[100%]`，退出码 `0`。
- 重启 `ai.openclaw.clawbot-agent` 和 `ai.openclaw.xianyu` 后，本机 `/api/status` 正常返回，严格门 `node scripts/cc_zhongzhuan_readiness_audit.mjs --require-real-order --json` 仍 `ok=false`，正确原因是当前真实单未发送到闲鱼聊天。

## [2026-07-07] CC中转闲鱼自动发货开源复核与确认发货能力补齐
> 领域: `xianyu` | `backend` | `infra` | `docs`
> 影响模块: `XianyuLive`, `XianyuApis`, `XianyuContext`, `Chrome Bookmarks`, `Open Source Intake`
> 关联问题: HI-907
### 变更内容
- 复核 6 个闲鱼/卡密自动发货开源项目：`zhinianboke/xianyu-auto-reply`、`GuDong2003/xianyu-auto-reply-fix`、`23Star/xianyu-super-butler`、`HJYHJYHJY/xianyu-auto-reply`、`Jasonmars12/xianyu-auto-ship`、`rrrrrede1/autofishing`；结论是继续搬运能力模式，不整套替换。
- 借鉴开源项目的“发码后确认发货”能力，新增闲鱼虚拟商品确认发货封装；默认关闭，只有 `CC_XIANYU_AUTO_CONFIRM_SHIPMENT_ENABLED=1` 且订单号为真实数字订单号时才会在发码成功后尝试确认发货。
- `cc_shipments` 新增闲鱼侧确认发货结果字段，只记录 `confirmed/failed/skipped`，不改变卡密已发状态，确认发货接口失败不会回滚已发送兑换码。
- Chrome `CC中转运营` 书签文件夹从 3 个入口继续收敛为 2 个：本机操作台、用户主站；`/ops-links` 保留兼容但不再默认收藏，减少老板日常标签页。
- 已只读接管当前闲鱼聊天页，确认页面可见 1 元测试商品、当前买家聊天、待发货提示、输入框和发送按钮；未获明确确认前没有发送真实消息。
### 文件变更
- `packages/clawbot/src/xianyu/xianyu_apis.py` — 新增 `confirm_dummy_shipment()`，对非数字订单号直接拒绝，避免误调用。
- `packages/clawbot/src/xianyu/xianyu_live.py` — 发码/补发成功后接入默认关闭的可选确认发货钩子。
- `packages/clawbot/src/xianyu/xianyu_context.py` — `cc_shipments` 追加闲鱼确认发货状态字段和记录方法。
- `packages/clawbot/tests/test_xianyu_cc_auto_ship.py` — 增加默认关闭、开启后确认、手工订单跳过和 API 自身校验测试。
- `scripts/cc_zhongzhuan_chrome_bookmarks.mjs` / `scripts/cc_zhongzhuan_readiness_audit.mjs` — 老板书签入口收敛为 2 个。
- `docs/002-changelog.md` / `docs/006-registries.md` / `docs/007-operations.md` / `docs/009-health.md` / `/Users/blackdj/Documents/VPS-Config/docs/05-unified-execution-plan.md` — 同步能力边界和当前真实单状态。
### 验证
- `cd packages/clawbot && .venv312/bin/python -m py_compile src/xianyu/xianyu_apis.py src/xianyu/xianyu_context.py src/xianyu/xianyu_live.py` → 通过。
- `cd packages/clawbot && .venv312/bin/python -m pytest tests/test_xianyu_cc_auto_ship.py -q` → `78 passed`。
- `node --check scripts/cc_zhongzhuan_chrome_bookmarks.mjs && node --check scripts/cc_zhongzhuan_readiness_audit.mjs && node scripts/cc_zhongzhuan_chrome_bookmarks.mjs --json` → 4 个 Chrome Profile 均 `urlCount=2`、`bookmarkBarVisible=true`。
- `node scripts/cc_zhongzhuan_readiness_audit.mjs --require-real-order --json` → `ok=false`，正确阻断原因仍是 `pendingRescue=1` / 当前真实单还没发到闲鱼聊天；书签、服务、Cookie、WebSocket、公网和库存检查正常。

## [2026-07-06] CC中转闲鱼全局看守与目标标签预检修复
> 领域: `xianyu` | `frontend` | `docs`
> 影响模块: `Chrome Extension`, `Xianyu Delivery Watch`, `XianyuAdmin`
> 关联问题: HI-907
### 变更内容
- 复核闲鱼自动发货开源轮子和 New-API/Sub2API 管理生态：成熟闲鱼项目仍以 `xianyu-auto-reply` 系列为主，但多为 AGPL 或许可证不清，且同样无法绕过当前卖家订单接口无权限问题；本轮继续搬运“卡密队列、幂等发货、看守补发”能力，不整套替换。
- 修复 Chrome 插件后台看守的目标标签预检问题：`sendXianyuCcDeliveryFromTab(tab)` 现在会预检传入的目标闲鱼标签页，不再误用当前激活标签页。
- 新增“看守所有闲鱼页”入口：插件会扫描已打开的闲鱼页；只有本机刚好 1 条待发货、页面可见已付款/待发货信号、且找到聊天输入框时才发送，成功一次后自动关闭。
- 本机操作台下一步提示改为更直接的老板操作口径：刷新 Chrome 插件，打开买家聊天页，可用“看守当前聊天页”或安全门通过时用“看守所有闲鱼页”。
- 当前真实内测单仍为 `manual_delivery_ready/pending_rescue=1`；Chrome 当前没有打开买家闲鱼聊天页，不能假装已发货或闭环完成。
### 文件变更
- `packages/openclaw-npm/assets/chrome-extension/background.js` — 修复目标标签预检，新增全局看守、安全门和多闲鱼页扫描。
- `packages/openclaw-npm/assets/chrome-extension/popup.html` / `popup.js` — 新增“看守所有闲鱼页”按钮和状态显示。
- `packages/openclaw-npm/assets/chrome-extension/test/popup-static.test.mjs` — 增加全局看守和目标标签预检防回归断言。
- `packages/clawbot/src/xianyu/xianyu_admin.py` — 更新老板下一步操作提示。
- `docs/002-changelog.md` / `docs/006-registries.md` / `docs/007-operations.md` / `docs/009-health.md` / `/Users/blackdj/Documents/VPS-Config/docs/05-unified-execution-plan.md` — 同步本次能力边界和当前阻断状态。
### 验证
- `cd packages/openclaw-npm/assets/chrome-extension && node --check background.js && node --check popup.js && node --test test/social-page-runner.test.mjs test/popup-static.test.mjs` → `43` 项通过。
- `cd packages/clawbot && .venv312/bin/python -m py_compile src/xianyu/xianyu_admin.py && .venv312/bin/python -m pytest tests/test_xianyu_cc_auto_ship.py::test_operator_next_action_points_manual_ready_to_chrome_watch tests/test_api_routes_regression.py -q` → `42` 项通过。
- `make test` → 跑到 `[100%]` 且退出码 `0`。
- `node scripts/cc_zhongzhuan_readiness_audit.mjs --mode=read_only --json` → `ok=false`，正确阻断仍是 `pendingRescue=1`；Oracle、公网、New-API、库存正常。

## [2026-07-06] CC中转闲鱼发货看守模式与开源调研复核
> 领域: `xianyu` | `frontend` | `docs`
> 影响模块: `Chrome Extension`, `Xianyu Delivery Watch`, `Open Source Intake`
> 关联问题: HI-907
### 变更内容
- 复核闲鱼自动发货开源轮子：`zhinianboke/xianyu-auto-reply` 当前约 5.5k⭐、AGPL-3.0，`GuDong2003/xianyu-auto-reply-fix` 当前约 1.6k⭐、AGPL-3.0，`23Star/xianyu-super-butler` 是二开 UI 版但许可证信息不清。结论是不整套替换现有 CC中转/New-API 链路，只搬运“订单看守、幂等、防重复、卡券队列”能力。
- 真实调用当前闲鱼卖家待发货订单接口返回 `PERMISSION_EXCEPTION::无权限访问`；同类开源项目也存在公开 Issue 报告该错误，因此全自动不能押宝卖家订单列表 API。
- Chrome 插件“CC中转发货助手”新增“看守当前聊天页”：老板在对应闲鱼买家聊天页开启后，插件锁定该标签页定时检查；只有页面可见“已付款/待发货”且本机存在已分配待发送话术时才自动发送，成功一次后自动关闭看守，避免重复发货。
- 针对用户手机截图继续补强插件识别：新增 `m.tb.cn/tb.cn` 闲鱼短链权限与平台识别，付款信号覆盖“提醒发货/记得及时发货”，聊天输入框覆盖“想跟TA说点什么”。
- 本机状态中心/操作台下一步提示已按 `manual_delivery_ready` 特化：补救队列里是“已分配待发送话术”时，明确提示打开对应买家聊天页并使用 Chrome 插件检测/看守发送，不再泛化成“等待后台自动补发”。
- 当前真实内测单仍为 `manual_delivery_ready/pending_rescue=1`，因为 Chrome 当前未打开对应闲鱼聊天页且未执行真实发送；正式售卖仍需实际发出该单并完成买家兑换、API Key、CC Switch 导入和调模型严格门。
### 文件变更
- `packages/clawbot/src/xianyu/xianyu_admin.py` — 补救队列为 `manual_delivery_ready` 时，把老板下一步动作指向 Chrome 插件聊天页看守。
- `packages/openclaw-npm/assets/chrome-extension/background.js` — 新增闲鱼当前聊天页看守状态、定时检查、锁定标签页、成功一次自动关闭。
- `packages/openclaw-npm/assets/chrome-extension/manifest.json` / `social-core.js` / `social-page-runner.js` — 补充闲鱼短链识别、手机端付款提示和聊天输入框选择器。
- `packages/openclaw-npm/assets/chrome-extension/popup.html` / `popup.js` — 新增“看守当前聊天页”按钮和状态渲染。
- `packages/openclaw-npm/assets/chrome-extension/test/popup-static.test.mjs` / `test/social-page-runner.test.mjs` — 增加插件看守入口、短链权限和手机端付款页断言。
- `docs/002-changelog.md` / `docs/006-registries.md` / `docs/007-operations.md` / `docs/009-health.md` / `/Users/blackdj/Documents/VPS-Config/docs/05-unified-execution-plan.md` — 同步本次开源调研、权限阻断和运营口径。
### 验证
- `gh repo view zhinianboke/xianyu-auto-reply GuDong2003/xianyu-auto-reply-fix 23Star/xianyu-super-butler` → 已记录星数、许可证、更新时间；`GuDong2003/xianyu-auto-reply-fix#64` 与当前 `PERMISSION_EXCEPTION::无权限访问` 问题一致。
- 当前 Cookie 只读调用闲鱼卖家 `NOT_SHIP` 待发货订单页 → `PERMISSION_EXCEPTION::无权限访问`。
- `cd packages/openclaw-npm/assets/chrome-extension && node --check background.js && node --check popup.js && node --check social-core.js && node --check social-page-runner.js && node --test test/social-page-runner.test.mjs test/popup-static.test.mjs` → `43` 项通过。
- `cd packages/clawbot && .venv312/bin/python -m pytest tests/test_xianyu_cc_auto_ship.py::test_operator_next_action_points_manual_ready_to_chrome_watch tests/test_xianyu_cc_auto_ship.py::test_xianyu_admin_browser_delivery_next_reuses_pending_message tests/test_api_routes_regression.py -q` → 跑到 `[100%]` 且退出码 `0`。
- 重启本机 `ai.openclaw.xianyu` 后，`/api/cc-operator-mode` 与 `/api/cc-operator-next-action` 均提示“打开对应闲鱼买家聊天页 + Chrome 插件检测/看守发送”。
- `node scripts/cc_zhongzhuan_readiness_audit.mjs --mode=read_only --json` → `ok=false`，正确阻断原因仍是 `pendingRescue=1`；Oracle 服务、公网入口、New-API 渠道和库存正常。

## [2026-07-06] CC中转闲鱼浏览器发货助手闭环切片
> 领域: `xianyu` | `frontend` | `backend` | `docs`
> 影响模块: `XianyuAdmin`, `Chrome Extension`, `CC Browser Delivery`
> 关联问题: HI-907
### 变更内容
- 横向检查闲鱼自动发货开源轮子：`zhinianboke/xianyu-auto-reply` 及二开版具备多账号、订单、卡券、自动发货等能力，但同样依赖 WebSocket/订单接口/页面自动化；当前不整套替换，优先搬运“待发货队列 + 幂等补发 + 浏览器兜底”思路。
- 新增 `GET /api/cc-browser-delivery/next`：Chrome 发货助手可读取下一条已分配但待发送的话术；接口受本机 Token 保护，只复用 `manual_delivery_ready/message_send_failed`，不会重新分配卡密。
- 扩展现有 Chrome 社媒插件为“CC中转发货助手”：在闲鱼页显示“检测当前聊天 / 发送待发货卡密”，只有当前页可见“已付款/待发货”等信号且找到输入框时，才会填入话术并点击发送，随后调用本机 `mark-sent`。
- 当前真实测试单仍保持 `manual_delivery_ready/pending_rescue=1`，未在没有闲鱼聊天页的情况下擅自标记已发；已完成无外发模拟，确认当前待发货记录可被插件填入并点击发送。
### 文件变更
- `packages/clawbot/src/xianyu/xianyu_admin.py` — 新增浏览器发货助手取件接口。
- `packages/openclaw-npm/assets/chrome-extension/background.js` / `popup.html` / `popup.js` / `social-page-runner.js` — 新增闲鱼当前聊天检测与发货按钮。
- `packages/clawbot/tests/test_xianyu_cc_auto_ship.py` / `packages/openclaw-npm/assets/chrome-extension/test/*.mjs` — 增加后端接口、插件桥接和页面填发测试。
- `docs/002-changelog.md` / `docs/006-registries.md` / `docs/007-operations.md` / `docs/009-health.md` / `/Users/blackdj/Documents/VPS-Config/docs/05-unified-execution-plan.md` — 同步生产内测闭环口径。
### 验证
- `python3 -m py_compile packages/clawbot/src/xianyu/xianyu_admin.py packages/clawbot/src/xianyu/xianyu_live.py packages/clawbot/src/xianyu/xianyu_context.py packages/clawbot/tests/test_xianyu_cc_auto_ship.py` → 通过。
- `node --check packages/openclaw-npm/assets/chrome-extension/background.js && node --check packages/openclaw-npm/assets/chrome-extension/popup.js && node --check packages/openclaw-npm/assets/chrome-extension/social-page-runner.js` → 通过。
- `cd packages/openclaw-npm/assets/chrome-extension && node --test test/social-page-runner.test.mjs test/popup-static.test.mjs` → `41` 项通过。
- `cd packages/clawbot && .venv312/bin/python -m pytest tests/test_xianyu_cc_auto_ship.py tests/test_api_routes_regression.py -q` → 跑到 `[100%]` 且退出码 `0`。
- 重启 `ai.openclaw.xianyu` 后，`/api/cc-browser-delivery/next` 返回当前待发送记录 `id=1`（输出已隐藏完整卡密）；无外发模拟返回 `ok=true / clickedSend=true / leakedSecret=false`。
- 只读生产巡检仍 `ok=false`，原因是当前真实内测单还在 `pending_rescue=1`；Oracle 服务、公网入口、New-API 渠道和库存正常。正式售卖仍需打开真实闲鱼聊天页发出本单，并让买家完成兑换、API Key、CC Switch 和模型调用严格门。

## [2026-07-06] Intel Brief Phase B 目标节点真实验证起步
> 领域: `backend` | `infra` | `docs` | `social`
> 影响模块: `Intel Brief`, `Phase B Evidence`, `Yanhuoyun`, `Oracle Fallback`, `Worker Probe`
> 关联问题: HI-912
### 变更内容
- 新增 `packages/clawbot/scripts/intel_worker_probe.py` 和回归测试，统一 Phase B 证据 JSON 字段，后续数据源验证不再散落在终端输出。
- 炎火云真实远端验证：微博公开页 HTTP 200、小红书公开页 HTTP 200、东方财富行情 API HTTP 200、AKShare `stock_lhb_detail_em` 在 `/tmp` 临时 venv + 国内镜像安装后真实返回 637 行。
- Oracle SGW 从当前 Mac 直连 SSH 超时，未把 Mac 本地或 fallback 结果冒充 SGW 验证；同时生成 SGW Beszel 只读状态证据。
- Oracle Ashburn `oracle-arm1` 作为海外 fallback 验证 SEC 13F、OpenAI RSS、Anthropic News、Senate raw GitHub、GitHub API 均可真实返回。
- 本轮无部署、无服务重启、无生产配置变更、无密钥/Cookie 明文输出。
### 文件变更
- `packages/clawbot/scripts/intel_worker_probe.py`
- `packages/clawbot/tests/test_intel_worker_probe.py`
- `packages/clawbot/data/intel_evidence/phaseb/*.jsonl`
- `packages/clawbot/data/intel_evidence/phaseb/20260706T225200Z-phaseb-summary.md`
- `docs/002-changelog.md` / `docs/006-registries.md` / `docs/009-health.md`
- `/Users/blackdj/Documents/VPS-Config/docs/indexes/intel-brief-runtime-placement.public.md`
- `/Users/blackdj/Documents/VPS-Config/docs/05-unified-execution-plan.md`
### 验证
- `cd packages/clawbot && .venv312/bin/python -m pytest tests/test_intel_worker_probe.py -q` → `3 passed`。
- 炎火云 SSH 真实命令返回 `node=yanhuoyun`、Python `3.10.12`，证据见 `packages/clawbot/data/intel_evidence/phaseb/20260706T224401Z-yanhuoyun-domestic-probes.jsonl` 和 `20260706T225123Z-yanhuoyun-akshare-call-retry.jsonl`。
- Oracle fallback 证据见 `packages/clawbot/data/intel_evidence/phaseb/20260706T224830Z-oracle-arm1-overseas-fallback-probes.jsonl` 和 `20260706T224857Z-oracle-arm1-overseas-fallback-retry.jsonl`。

## [2026-07-06] Intel Brief 总体方案与开源搬运规划
> 领域: `docs` | `infra` | `backend` | `social`
> 影响模块: `Intel Brief`, `Open Source Intake`, `Runtime Placement`, `VPS-Config Baseline`
> 关联问题: HI-911
### 变更内容
- 新增 `docs/052-intel-brief-master-plan.md`，冻结 Intel Brief 先规划、先调研、再生产变更的总体路线。
- 按 GitHub 实时调研整理高星轮子搬运清单：MediaCrawler、AKShare、edgartools、RSSHub、LiteLLM、APScheduler、OpenBB、Qlib、Senate watcher data 等。
- 明确多服务器基线：国内源优先炎火云 worker，海外源优先低负载 Oracle 新加坡西 worker，OpenEverything 作为 controller。
- 在 VPS-Config 新增公开 runtime placement 基线文档，仅记录节点角色和维护护栏，不写入任何凭证明文。
- 本轮只做方案和文档，无部署、无重启、无 Cookie/Token 写入。
### 文件变更
- `docs/052-intel-brief-master-plan.md`
- `docs/003-docs-index.md`
- `docs/002-changelog.md`
- `docs/009-health.md`
- `/Users/blackdj/Documents/VPS-Config/docs/indexes/intel-brief-runtime-placement.public.md`
- `/Users/blackdj/Documents/VPS-Config/docs/05-unified-execution-plan.md`
### 验证
- `agent-reach doctor --json` → GitHub active_backend 为 `gh CLI`，RSS/web/exa_search 可用。
- `gh search repos` / `gh repo view` 已返回候选仓库、星数、license 和更新时间快照。
- `python3 - <<'PY' ... pathlib read_text ...` 文档存在性检查通过。

## [2026-07-06] Intel Brief 多服务器路由与社媒无人值守优先策略
> 领域: `backend` | `infra` | `social` | `docs`
> 影响模块: `Intel Brief`, `Runtime Policy`, `Social Auth Strategy`
> 关联问题: HI-910
### 变更内容
- 新增 Intel Brief runtime policy，把“国内业务优先国内 worker、海外数据源走海外 worker、未知源留在 controller”的多服务器架构决策落为可测试策略。
- 新增微博/小红书社媒登录策略描述：优先 `cdp_cookie` / `cookie` 等持久登录态无人值守运行，二维码仅作为风控失效后的人工兜底。
- 明确不承诺“永不扫码”：平台风控可能强制二次验证，工程目标是减少人工介入并在登录态失效时告警。
- 本轮未部署、未购买/创建国内服务器、未保存 Cookie、未触发扫码登录。
### 文件变更
- `packages/clawbot/src/intel/runtime_policy.py`
- `packages/clawbot/tests/test_intel_runtime_policy.py`
- `docs/084-intel-brief-implementation-report.md`
### 验证
- 已先运行新增测试得到 RED：`ModuleNotFoundError: No module named 'src.intel.runtime_policy'`。
- `cd packages/clawbot && .venv312/bin/python -m pytest tests/test_intel_runtime_policy.py -q` → `4 passed`。


## [2026-07-06] Intel Brief 开放追踪与内容过滤基础切片
> 领域: `backend` | `docs`
> 影响模块: `Intel Brief`, `SQLite Schema`, `Content Moderation`, `Congress Trading`
> 关联问题: HI-909
### 变更内容
- 按补充决策取消 `celebrity_watchlist` 白名单模型，新增开放输入姓名追踪 schema：`tracking_targets`、`tracking_subscriptions`、`tracking_audit_log`。
- 新增 Intel Brief 内容过滤基础模块，支持关键词预过滤、可注入 LLM/规则二次判断、过滤占位和 SQLite 过滤日志。
- 新增 Senate 国会持仓 raw GitHub fallback 模块；Oracle Phase 0 真实验证显示 S3 House 裸文件仍 403，但 Senate raw GitHub `master/aggregate/all_transactions.json` HTTP 200 可用。
- 本轮未部署、未重启服务、未处理 Telegram 第 8 Bot Token、MediaCrawler 登录态、X/Reddit 或定价。
### 文件变更
- `packages/clawbot/src/intel/db/intel_brief_schema.sql`
- `packages/clawbot/src/intel/db/store.py`
- `packages/clawbot/src/intel/quality/content_moderation.py`
- `packages/clawbot/src/intel/sources/congress_trading.py`
- `packages/clawbot/tests/test_intel_schema_and_tracking.py`
- `packages/clawbot/tests/test_intel_content_moderation.py`
- `packages/clawbot/tests/test_intel_congress_trading.py`
- `docs/superpowers/plans/2026-07-06-intel-brief-supplement.md`
- `docs/084-intel-brief-implementation-report.md`
### 验证
- Oracle `2026-07-06T21:50:40Z`：House S3 裸文件 HTTP 403 + `AccessDenied`；Senate raw GitHub HTTP 200，样本含 `BYND` / `Ron L Wyden`。
- `cd packages/clawbot && .venv312/bin/python -m pytest tests/test_intel_schema_and_tracking.py tests/test_intel_content_moderation.py tests/test_intel_congress_trading.py -q` → `8 passed`。

## [2026-07-06] CC中转闲鱼已付款漏单兜底发货
> 领域: `xianyu` | `backend` | `frontend` | `docs`
> 影响模块: `XianyuAdmin`, `XianyuContext`, `CC Manual Dispatch`, `Readiness Audit`
> 关联问题: HI-910
### 变更内容
- 真实内测发现：买家手机端显示“我已付款，等待你发货”，但本机闲鱼 WebSocket 未收到任何消息事件，`messages/orders/cc_shipments` 均为空，说明不能只依赖推送作为唯一发货触发源。
- 新增受保护的漏单兜底接口 `POST /api/cc-manual-paid-order/dispatch`：仅在老板已经看到闲鱼“已付款/待发货”后使用，调用 CC中转低权限 webhook 分配真实兑换码，返回可复制的发货话术，并把本机记录标记为 `manual_delivery_ready`。
- 新增 `POST /api/cc-shipments/{id}/mark-sent`：老板把话术粘贴到闲鱼聊天并发送后，显式标记为 `message_sent`；只有这一步完成后，本机真实订单门才会把该订单算作“已发货”。
- 本机操作台新增“已付款漏单兜底”卡片，支持生成话术、复制话术、标记已手动发送；补救队列支持从 `manual_delivery_ready` 记录重新填入话术，避免刷新后丢失。
- `manual_delivery_ready` 已纳入补救队列和只读巡检 pending rescue 统计，避免“卡密已分配但还没发给买家”被误判为闭环完成。
### 文件变更
- `packages/clawbot/src/xianyu/xianyu_admin.py` — 新增漏单兜底发货 API、标记已发送 API 和操作台按钮。
- `packages/clawbot/src/xianyu/xianyu_context.py` — 将 `manual_delivery_ready` 纳入补救队列/正式门禁统计。
- `scripts/cc_zhongzhuan_readiness_audit.mjs` — 只读巡检 pending rescue 纳入 `manual_delivery_ready`。
- `packages/clawbot/tests/test_xianyu_cc_auto_ship.py` — 增加漏单兜底分配、幂等和手动标记已发送回归测试。
- `docs/002-changelog.md` / `docs/006-registries.md` / `docs/007-operations.md` / `docs/009-health.md` / `/Users/blackdj/Documents/VPS-Config/docs/05-unified-execution-plan.md` — 同步真实内测故障和操作口径。
### 验证
- 新增测试先红后绿：`/api/cc-manual-paid-order/dispatch` 原先 404，补实现后返回 `manual_delivery_ready`；重复点击同一证明不会重复分配卡密。
- `python3 -m py_compile packages/clawbot/src/xianyu/xianyu_admin.py packages/clawbot/src/xianyu/xianyu_context.py packages/clawbot/src/xianyu/xianyu_live.py` → 通过。
- `node --check scripts/cc_zhongzhuan_readiness_audit.mjs` → 通过。
- `cd packages/clawbot && .venv312/bin/python -m pytest tests/test_xianyu_cc_auto_ship.py tests/test_api_routes_regression.py -q` → 跑到 `[100%]` 且退出码 `0`。
- `make test` → 跑到 `[100%]` 且退出码 `0`。
- 真实内测漏单已生成 `manual_delivery_ready` 记录，当前补救队列为 1；等待老板把剪贴板发货话术粘贴到闲鱼聊天并确认发送后再标记 `message_sent`。

## [2026-07-06] CC中转闲鱼测试商品绑定预备检查
> 领域: `xianyu` | `backend` | `docs`
> 影响模块: `XianyuAdmin`, `CC Item Mapping`, `Xianyu Auto Ship`
> 关联问题: HI-909
### 变更内容
- 商品绑定接口新增闲鱼完整分享文本规整：老板可直接粘贴 `【闲鱼】[短链接](短链接) CZ007 「标题」点击链接直接打开`，后台会自动保存为 `短链接 + 分享码`，不再需要手动删除前后文案。
- 本机操作台商品链接输入框提示已更新为可直接粘贴完整闲鱼分享文本。
- 预备检查发现测试商品原绑定套餐为 `1`，发货接口会按无效套餐处理；已将当前测试商品绑定修正为有库存的 `codex-30-day`。
### 文件变更
- `packages/clawbot/src/xianyu/xianyu_admin.py` — 新增商品绑定输入规整函数，保存映射前统一清洗商品键。
- `packages/clawbot/tests/test_xianyu_cc_auto_ship.py` — 新增完整闲鱼分享文本绑定回归测试。
- `docs/002-changelog.md` / `docs/006-registries.md` / `docs/009-health.md` / `/Users/blackdj/Documents/VPS-Config/docs/05-unified-execution-plan.md` — 同步本次内测预备检查结果。
### 验证
- 新增测试先红后绿：完整分享文本从整段原文规整为 `https://m.tb.cn/h.RC4QcXM?tk=DxWwgNjrfdQ CZ007`。
- `python3 -m py_compile packages/clawbot/src/xianyu/xianyu_admin.py packages/clawbot/src/xianyu/xianyu_context.py packages/clawbot/src/xianyu/xianyu_live.py` → 通过。
- `cd packages/clawbot && .venv312/bin/python -m pytest tests/test_xianyu_cc_auto_ship.py tests/test_api_routes_regression.py -q` → 跑到 `[100%]` 且退出码 `0`。
- `make test` → 跑到 `[100%]` 且退出码 `0`。
- 重启 `ai.openclaw.xianyu` 后：`/api/cc-operator-mode` 返回 `auto_ship_paused=false`、`webhook_configured=true`、`can_auto_ship_paid_orders=true`、`pending_rescue=0`、`enabled_item_mappings=1`。
- `node scripts/cc_zhongzhuan_readiness_audit.mjs --mode=read_only --json` → `ok=true`，本机闲鱼 WebSocket/Cookie/自动发货、Oracle 服务、公网主站、兑换码库存、New-API 渠道均通过；仍等待真实小额付款订单作为正式售卖门槛。

## [2026-07-06] CC中转状态中心与操作台 Apple 风格重构
> 领域: `xianyu` | `frontend` | `backend` | `docs`
> 影响模块: `XianyuAdmin`, `XianyuLive`, `CC Operator State`, `Ops Links`
> 关联问题: HI-908
### 变更内容
- 按老板反馈把本机 `http://127.0.0.1:18800/ops-links` 重做为 Apple 风格“状态中心”：大卡片、圆环进度、少量状态灯和一句下一步；默认隐藏工程排障信息，不再展示密集闭环清单。
- 把本机 `http://127.0.0.1:18800/` 重做为“操作台”：只保留四个日常动作（确认闲鱼在线、绑定商品、暂停/恢复自动发货、处理补救队列），商品模板和巡检放在次级区域，高级排障默认折叠。
- 新增本机运行时运营状态模块 `cc_operator_state.py` 和 `GET/POST /api/cc-operator-mode`，支持在操作台一键暂停/恢复自动发货；暂停后 `XianyuLive` 不再自动发卡，补救循环也会跳过。
- 自动发货状态新增 `paused/operational/pause_reason` 字段；售卖锁、运营水位和统一快照会把“人工暂停”识别为独立状态，而不是误报成配置坏了。
- 回归测试新增暂停/恢复 API 和暂停后不触发 webhook 的覆盖；页面测试更新为检查“状态中心/四步使用/暂停自动发货/高级排障”新结构。
### 文件变更
- `packages/clawbot/src/xianyu/cc_operator_state.py` — 新增本机操作台暂停状态文件读写，不保存卡密、Token、Cookie 或买家信息。
- `packages/clawbot/src/xianyu/xianyu_admin.py` — 重构 `/ops-links` 和 `/` 两个页面，新增 `/api/cc-operator-mode`，接入人工暂停状态。
- `packages/clawbot/src/xianyu/xianyu_live.py` — 自动发货和失败补发循环尊重本机暂停状态，暂停时只记录 `operator_paused`，不调用 CC中转 webhook。
- `packages/clawbot/tests/test_api_routes_regression.py` / `packages/clawbot/tests/test_xianyu_cc_auto_ship.py` — 增加新页面结构与暂停链路回归。
- `.gitignore` — 忽略 `.openclaw/cc-zhongzhuan-operator-state.json` 本机运行状态文件。
- `docs/002-changelog.md` / `docs/006-registries.md` / `docs/007-operations.md` / `docs/009-health.md` / `/Users/blackdj/Documents/VPS-Config/docs/05-unified-execution-plan.md` — 同步日常运营口径。
### 验证
- `python3 -m py_compile packages/clawbot/src/xianyu/cc_operator_state.py packages/clawbot/src/xianyu/xianyu_admin.py packages/clawbot/src/xianyu/xianyu_live.py` → 通过。
- `cd packages/clawbot && .venv312/bin/python -m pytest tests/test_api_routes_regression.py tests/test_xianyu_cc_auto_ship.py -q` → 通过。
- `make test` → 跑到 `[100%]` 且退出码 `0`。
- 重启 `ai.openclaw.xianyu` 后：`/ops-links=200`、`/=200`、`/api/cc-operator-mode` 返回 `auto_ship_paused=false`、`webhook_configured=true`、`can_auto_ship_paid_orders=true`、`pending_rescue=0`。
- Playwright 截图验证：`output/playwright/cc-status-center-apple.png`、`output/playwright/cc-operator-console-apple.png`；页面 `hasDenseOldText=false`，操作台包含暂停按钮和四步使用。

## [2026-07-06] CC中转运营入口收敛为暗色状态中心
> 领域: `xianyu` | `frontend` | `infra` | `docs`
> 影响模块: `XianyuAdmin`, `Ops Links`, `Chrome Bookmarks`, `New-API Production`
> 关联问题: HI-907
### 变更内容
- 将本机 `/ops-links` 从工程链接堆叠页重做为暗色“CC中转状态中心”，首屏只保留售卖状态、自动发货、库存与渠道、买家链路、下一步和 3 个常用入口。
- 将本机完整 GUI `/` 改为暗色“CC中转高级控制台”，明确它是排障/补救用，不再作为老板日常入口。
- Chrome `CC中转运营` 书签文件夹从 7 个入口收敛为 3 个：状态中心、用户主站、高级控制台；不再收藏 `/admin.html`、`/v1`、`/v1/models` 这类错误或程序接口入口。
- 生产 New-API 将 `SelfUseModeEnabled` 从 `true` 调整为 `false`，公网主站不再显示“自用模式”；Oracle 已备份数据库并重启 `openclaw-newapi.service`。
- Oracle Apache 为 `https://jiyu.245334.xyz/admin.html` 增加 302 到 `/console`，旧后台误点不会再落到 SPA “页面未找到”。
- 修复全量测试暴露的社媒插件测试隔离问题：`test_social_extension_status.py` 现在自动隔离 `social_scheduler` 与 `x_auto_ops` 状态文件，避免读取本机真实草稿导致测试计数漂移。
### 文件变更
- `packages/clawbot/src/xianyu/xianyu_admin.py` — 重做 `/ops-links` 暗色状态中心，暗色化 `/` 高级控制台，更新老板可见地址清单。
- `scripts/cc_zhongzhuan_chrome_bookmarks.mjs` / `scripts/cc_zhongzhuan_readiness_audit.mjs` — Chrome 运营入口清单收敛为 3 项。
- `packages/new-api-upstream/web/classic/src/components/layout/headerbar/HeaderLogo.jsx` — 上游源码层隐藏“自用模式”顶部徽标展示。
- `packages/clawbot/tests/test_api_routes_regression.py` — 更新状态中心和暗色高级控制台断言。
- `packages/clawbot/tests/test_social_extension_status.py` — 增加社媒草稿状态自动隔离 fixture。
- `docs/002-changelog.md` / `docs/006-registries.md` / `docs/007-operations.md` / `docs/009-health.md` / `/Users/blackdj/Documents/VPS-Config/docs/05-unified-execution-plan.md` — 同步运营入口和生产状态口径。
### 验证
- `python3 -m py_compile packages/clawbot/src/xianyu/xianyu_admin.py && node --check scripts/cc_zhongzhuan_chrome_bookmarks.mjs && node --check scripts/cc_zhongzhuan_readiness_audit.mjs` → 通过。
- `cd packages/clawbot && .venv312/bin/python -m pytest tests/test_api_routes_regression.py tests/test_xianyu_cc_auto_ship.py -q` → 通过。
- `cd packages/clawbot && .venv312/bin/python -m pytest tests/test_social_extension_status.py -q` → 通过。
- `make test` → 跑到 `[100%]` 且退出码 `0`。
- `cd packages/new-api-upstream/web/classic && bun install --frozen-lockfile && bun run build` → 通过（仅有上游依赖/大 chunk warning）。
- `node scripts/cc_zhongzhuan_chrome_bookmarks.mjs --json` → 4 个 Chrome Profile 均 `urlCount=3`、`bookmarkBarVisible=true`。
- `node scripts/cc_zhongzhuan_readiness_audit.mjs --json` → `ok=true`、`chromeBookmarks.ok=true`。
- Playwright 截图：`output/cc-ops-status-center-dark-20260706.png`、`output/cc-advanced-console-dark-20260706.png`、`output/jiyu-public-no-selfuse-20260706.png`；公网渲染 `hasSelfUse=false`。
- 公网验证：`https://jiyu.245334.xyz/admin.html` → `302 https://jiyu.245334.xyz/console`；`/api/status` → `system_name=CC中转`、`self_use_mode_enabled=false`、`setup=true`。

## [2026-07-05] 站内烟测计划与全自动闭环看板收口
> 领域: `xianyu` | `backend` | `frontend` | `docs`
> 影响模块: `XianyuAdmin`, `Ops Links`, `Automation Coverage`, `Chrome Bookmarks`
> 关联问题: HI-907
### 变更内容
- 新增只读 `GET /api/cc-buyer-site-smoke-plan`，展示站内买家烟测是否可准备、会写入哪些生产数据、需要哪些清理动作；默认 `executes_now=false`，不会擅自创建用户、兑换、创建 API Key 或调模型。
- `GET /api/cc-operator-next-action`、`GET /api/cc-real-order-test-pack`、`GET /api/cc-automation-coverage`、`GET /api/cc-ops-snapshot` 都返回同一份 `buyer_site_smoke_plan`，避免运营台和文档口径漂移。
- `/ops-links` 与本机闲鱼 GUI 新增“站内烟测计划”卡片；Chrome 书签脚本已再次重建 4 个本机 Profile 的 `CC中转运营` 文件夹，若 Chrome 运行中不刷新，直接打开 `http://127.0.0.1:18800/ops-links` 兜底。
### 文件变更
- `packages/clawbot/src/xianyu/xianyu_admin.py` — 新增站内烟测计划 API、快照字段和两个 GUI 渲染。
- `packages/clawbot/tests/test_api_routes_regression.py` — 覆盖新 API、页面标记和 `executes_now=false` 安全边界。
- `scripts/cc_zhongzhuan_chrome_bookmarks.mjs` — 复用现有脚本重建 Chrome 运营书签文件夹。
- `docs/002-changelog.md` / `docs/006-registries.md` / `docs/007-operations.md` / `docs/009-health.md` / `/Users/blackdj/Documents/VPS-Config/docs/05-unified-execution-plan.md` — 同步当前全自动闭环口径。
### 验证
- `node scripts/cc_zhongzhuan_chrome_bookmarks.mjs --json` → 4 个 Chrome Profile 均 `ok=true`、`urlCount=7`、`bookmarkBarVisible=true`。
- `python3 -m py_compile packages/clawbot/src/xianyu/xianyu_admin.py packages/clawbot/src/xianyu/xianyu_live.py packages/clawbot/src/xianyu/xianyu_context.py` → 通过。
- `cd packages/clawbot && .venv312/bin/python -m pytest tests/test_api_routes_regression.py -q` → `40 passed / 0 failed`。
- `cd packages/clawbot && .venv312/bin/python -m pytest tests/test_xianyu_cc_auto_ship.py -q` → `54 passed / 0 failed`。
- `make test` → 跑到 `[100%]` 且退出码 `0`。
- 重启 `ai.openclaw.xianyu` 后 live `/api/cc-buyer-site-smoke-plan` → `state=ready_requires_confirmation`、`can_prepare=true`、`executes_now=false`；live `/api/cc-automation-coverage` → `completed=10/11`、`internal_automation_ready=true`、`public_sale_ready=false`、唯一缺口 `real_order_strict_gate`；只读审计 → `ok=true`、`chromeBookmarks_ok=true`、`gui_ok=true`、`oracle_ok=true`。

## [2026-07-05] 实单验收包补齐站内买家烟测检查项
> 领域: `xianyu` | `backend` | `frontend` | `docs`
> 影响模块: `XianyuAdmin`, `Real Order Test Pack`, `Operator Next Action`
> 关联问题: HI-907
### 变更内容
- `GET /api/cc-operator-next-action` 的 checklist 新增 `buyer_site_smoke`，让“当前要做什么”同时显示站内兑换/API Key/调模型烟测是否完整。
- `GET /api/cc-real-order-test-pack` 的 checkpoints 新增“站内买家烟测”，并返回同一份 `buyer_site_smoke` 摘要。
- `/ops-links` 和完整 GUI 的实单验收包会展示站内买家烟测状态；当前 live 是 partial，仍需真实小额单完成同单严格门。
### 文件变更
- `packages/clawbot/src/xianyu/xianyu_admin.py` — 当前行动建议、实单验收包和两个 GUI 渲染接入 `buyer_site_smoke`。
- `packages/clawbot/tests/test_api_routes_regression.py` — 覆盖页面标记、行动建议 checklist、实单验收包 checkpoints。
- `docs/002-changelog.md` / `docs/007-operations.md` / `docs/009-health.md` / `/Users/blackdj/Documents/VPS-Config/docs/05-unified-execution-plan.md` — 同步验收包口径。
### 验证
- `packages/clawbot/.venv312/bin/python -m py_compile packages/clawbot/src/xianyu/xianyu_admin.py` → 通过。
- `cd packages/clawbot && .venv312/bin/python -m pytest tests/test_api_routes_regression.py tests/test_xianyu_cc_auto_ship.py -q` → `94 passed / 0 failed`。
- 重启 `ai.openclaw.xianyu` 后 live `/api/cc-real-order-test-pack` → HTTP 200，checkpoints 包含 `buyer_site_smoke=false`，`state=run_real_small_order`。
- live `/api/cc-operator-next-action` → HTTP 200，checklist 包含 `buyer_site_smoke=false`，下一步仍是跑真实小额单。

## [2026-07-05] 买家站内烟测证据接入运营快照
> 领域: `xianyu` | `backend` | `frontend` | `docs`
> 影响模块: `XianyuAdmin`, `Ops Snapshot`, `Automation Coverage`
> 关联问题: HI-907
### 变更内容
- 新增 `buyer_site_smoke` 只读摘要，展示从最近一次生产只读巡检得到的买家站内链路证据：兑换增量、API Key 增量、模型调用日志增量。
- `GET /api/cc-ops-snapshot` 与 `GET /api/cc-automation-coverage` 都返回该摘要；`/ops-links` 和完整 GUI 的“闭环覆盖清单”会显示站内烟测状态。
- 当前 live 为 `state=partial`：模型调用日志增量为正，但兑换增量和 API Key 增量为 0；这不替代真实闲鱼同单严格门，只是避免把“页面可访问”误读成“最近完整站内烟测已跑过”。
### 文件变更
- `packages/clawbot/src/xianyu/xianyu_admin.py` — 缓存买家站内烟测增量，接入统一快照、覆盖清单和两个 GUI。
- `packages/clawbot/tests/test_api_routes_regression.py` — 覆盖只读巡检缓存、统一快照和覆盖清单里的 `buyer_site_smoke`。
- `docs/002-changelog.md` / `docs/006-registries.md` / `docs/007-operations.md` / `docs/009-health.md` / `/Users/blackdj/Documents/VPS-Config/docs/05-unified-execution-plan.md` — 同步字段和 live 结论。
### 验证
- `packages/clawbot/.venv312/bin/python -m py_compile packages/clawbot/src/xianyu/xianyu_admin.py` → 通过。
- `cd packages/clawbot && .venv312/bin/python -m pytest tests/test_api_routes_regression.py tests/test_xianyu_cc_auto_ship.py -q` → `94 passed / 0 failed`。
- 重启 `ai.openclaw.xianyu` 后 live `/api/cc-ops-snapshot` 与 `/api/cc-automation-coverage` → HTTP 200，`buyer_site_smoke.state=partial`、`redeemed_delta=0`、`active_token_delta=0`、`model_log_delta=99`。

## [2026-07-05] 统一运营快照接入严格门自动观察状态
> 领域: `xianyu` | `backend` | `docs`
> 影响模块: `XianyuAdmin`, `Ops Snapshot`, `Strict Audit`
> 关联问题: HI-907
### 变更内容
- 新增 `_cc_auto_strict_audit_status()` 只读摘要，统一描述严格门自动观察是否开启、是否等待真实付款、是否已检测到真实订单后 armed、是否刚运行或已通过。
- `GET /api/cc-ops-snapshot` 现在直接返回 `auto_strict_audit_status`，后续本机提醒/外部看板读取统一快照时不用再额外拼覆盖清单接口。
- `GET /api/cc-automation-coverage` 复用同一个摘要，避免覆盖清单和统一快照对“严格门是否开启/为什么未运行”的口径漂移。
### 文件变更
- `packages/clawbot/src/xianyu/xianyu_admin.py` — 抽出严格门自动观察摘要，并接入统一运营快照。
- `packages/clawbot/tests/test_api_routes_regression.py` — 覆盖统一快照返回 `auto_strict_audit_status.state=armed` 的真实订单后观察态。
- `docs/002-changelog.md` / `docs/007-operations.md` / `/Users/blackdj/Documents/VPS-Config/docs/05-unified-execution-plan.md` — 同步快照字段口径。
### 验证
- `packages/clawbot/.venv312/bin/python -m py_compile packages/clawbot/src/xianyu/xianyu_admin.py` → 通过。
- `cd packages/clawbot && .venv312/bin/python -m pytest tests/test_api_routes_regression.py tests/test_xianyu_cc_auto_ship.py -q` → `94 passed / 0 failed`。
- 重启 `ai.openclaw.xianyu` 后 live `/api/cc-ops-snapshot` → HTTP 200，刷新证据后返回 `sale_lock_state=internal_test_ready`、`loop_stage=waiting_paid_order`、`auto_strict_state=waiting_paid_order`。
- live `/api/cc-automation-coverage` → HTTP 200，`completed=10/11`、`internal_automation_ready=true`、唯一缺口 `real_order_strict_gate`。

## [2026-07-05] 运营总页补齐书签可见提示与严格门等待原因
> 领域: `xianyu` | `backend` | `frontend` | `docs`
> 影响模块: `XianyuAdmin`, `Ops Links`, `Automation Coverage`
> 关联问题: HI-907
### 变更内容
- `/ops-links` 顶部新增极简运维提示：如果 Chrome 书签栏暂时没显示 `CC中转运营`，先直接收藏/打开本机运营总页；Chrome 运行中可能需要重启后才刷新本地书签文件。
- `GET /api/cc-automation-coverage` 新增 `auto_strict_audit_status`，明确显示严格门自动观察是否开启、当前状态、等待原因和节流间隔。
- `/ops-links` 和本机闲鱼 GUI 的“闭环覆盖清单”会展示“严格门自动观察：已开启，正在等待真实已付款订单”，避免把 `auto_strict_audit={}` 误解成自动化没启动。
### 文件变更
- `packages/clawbot/src/xianyu/xianyu_admin.py` — 新增严格门自动观察状态摘要，并在两个 GUI 渲染。
- `packages/clawbot/tests/test_api_routes_regression.py` — 覆盖书签提示、严格门状态字段和真实订单后自动观察状态。
- `docs/002-changelog.md` / `docs/007-operations.md` / `docs/009-health.md` / `/Users/blackdj/Documents/VPS-Config/docs/05-unified-execution-plan.md` — 同步当前 live 口径。
### 验证
- `packages/clawbot/.venv312/bin/python -m py_compile packages/clawbot/src/xianyu/xianyu_admin.py` → 通过。
- `cd packages/clawbot && .venv312/bin/python -m pytest tests/test_api_routes_regression.py tests/test_xianyu_cc_auto_ship.py -q` → `94 passed / 0 failed`。
- `make test` → 跑到 `[100%]`，退出码 `0`。
- 重启 `ai.openclaw.xianyu` 后 live `/api/cc-automation-coverage` → HTTP 200，`completed=10/11`、`internal_automation_ready=true`、`auto_strict_audit_status.state=waiting_paid_order`、`label=严格门自动观察已开启，正在等待真实已付款订单`。
- `node scripts/cc_zhongzhuan_readiness_audit.mjs --mode=read_only --json` → `ok=true`，Chrome 书签、本机闲鱼 GUI、Oracle、库存、兑换码、渠道、公网入口和 CC Switch 入口均通过。

## [2026-07-05] 覆盖清单真实单后自动严格门观察
> 领域: `xianyu` | `backend` | `docs`
> 影响模块: `XianyuAdmin`, `Automation Coverage`, `Strict Audit`
> 关联问题: HI-907
### 变更内容
- 覆盖清单在检测到真实闲鱼订单已自动发货、自动发货链路可用、无补救队列且节流允许时，会调用现有后台严格门只读观察。
- 该观察只运行 `strict` 审计，不调用 webhook 冒烟、不分配卡密、不发送闲鱼消息、不修改库存；用于真实付款后自动刷新买家兑换/API Key/调模型证据。
- 当前 live 没有真实订单，`auto_strict_audit={}`，不会误触发严格门；真实订单出现后才会自动观察。
### 文件变更
- `packages/clawbot/src/xianyu/xianyu_admin.py` — 覆盖清单接入 `_should_run_background_strict_audit()` 与 `_run_background_strict_audit_once()`。
- `packages/clawbot/tests/test_api_routes_regression.py` — 覆盖真实订单后自动触发严格门只读观察，以及无真实订单不误触发。
- `docs/002-changelog.md` / `docs/007-operations.md` / `docs/009-health.md` / `/Users/blackdj/Documents/VPS-Config/docs/05-unified-execution-plan.md` — 同步自动观察口径。
### 验证
- `packages/clawbot/.venv312/bin/python -m py_compile packages/clawbot/src/xianyu/xianyu_admin.py packages/clawbot/tests/test_api_routes_regression.py` → 通过。
- `cd packages/clawbot && .venv312/bin/python -m pytest tests/test_api_routes_regression.py tests/test_xianyu_cc_auto_ship.py -q` → `94 passed / 0 failed`。
- `make test` → 跑到 `[100%]`，退出码 `0`。
- 重启 `ai.openclaw.xianyu` 后 live `/api/cc-automation-coverage` → HTTP 200，`completed=10/11`、`internal_automation_ready=true`、`auto_strict_audit={}`、唯一缺口仍是 `real_order_strict_gate`。
- `node scripts/cc_zhongzhuan_readiness_audit.mjs --mode=read_only --json` → `ok=true`。


## [2026-07-05] 闭环覆盖清单冷启动只读刷新
> 领域: `xianyu` | `backend` | `docs`
> 影响模块: `XianyuAdmin`, `Automation Coverage`, `Readiness Audit`
> 关联问题: HI-907
### 变更内容
- `GET /api/cc-automation-coverage` 在服务刚重启、库存/书签/公网入口证据尚未写入缓存时，会自动运行一次只读巡检刷新证据。
- 该刷新不发货、不分配卡密、不发送闲鱼消息、不修改库存，只用于避免覆盖清单冷启动误判为“内部自动化未 ready”。
- live 重启后直接请求覆盖清单，无需先点“刷新上架锁”，返回 `completed=10/11`、`internal_automation_ready=true`、唯一缺口 `real_order_strict_gate`。
### 文件变更
- `packages/clawbot/src/xianyu/xianyu_admin.py` — 覆盖清单缺证据时自动只读刷新，并返回 `audit_error`。
- `packages/clawbot/tests/test_api_routes_regression.py` — 覆盖冷启动自动刷新路径。
- `docs/002-changelog.md` / `docs/007-operations.md` / `docs/009-health.md` / `/Users/blackdj/Documents/VPS-Config/docs/05-unified-execution-plan.md` — 同步冷启动刷新口径。
### 验证
- `packages/clawbot/.venv312/bin/python -m py_compile packages/clawbot/src/xianyu/xianyu_admin.py packages/clawbot/tests/test_api_routes_regression.py` → 通过。
- `cd packages/clawbot && .venv312/bin/python -m pytest tests/test_api_routes_regression.py tests/test_xianyu_cc_auto_ship.py -q` → `93 passed / 0 failed`。
- `make test` → 跑到 `[100%]`，退出码 `0`。
- 重启 `ai.openclaw.xianyu` 后直接请求 live `/api/cc-automation-coverage` → HTTP 200，`completed=10`、`total=11`、`internal_automation_ready=true`、`public_sale_ready=false`、`missing_keys=[real_order_strict_gate]`。
- `node scripts/cc_zhongzhuan_readiness_audit.mjs --mode=read_only --json` → `ok=true`。


## [2026-07-05] CC中转全自动闭环覆盖清单
> 领域: `xianyu` | `backend` | `frontend` | `docs`
> 影响模块: `XianyuAdmin`, `Ops Links`, `Automation Coverage`
> 关联问题: HI-907
### 变更内容
- 新增只读 `GET /api/cc-automation-coverage`，把目标闭环拆成 11 项证据：Chrome 书签、已付款检测、卡密分配、发货话术发送、履约回写、买家注册兑换、API Key、CC Switch、模型调用、合规边界、真实小额单严格门。
- `/ops-links` 和本机闲鱼 GUI 新增“闭环覆盖清单”卡片，直接显示 `已满足/总项数`、内部自动化是否 ready、正式售卖是否放行，以及下一步。
- live 当前覆盖清单显示 `10/11`，`internal_automation_ready=true`、`public_sale_ready=false`、`external_blocker=true`；唯一未满足项是必须由真实闲鱼小额付款触发的严格门。
### 文件变更
- `packages/clawbot/src/xianyu/xianyu_admin.py` — 新增覆盖清单摘要、API 路由、运营入口和完整 GUI 渲染。
- `packages/clawbot/tests/test_api_routes_regression.py` — 覆盖 API 状态、外部门槛不误判、两个 GUI 页面入口。
- `docs/002-changelog.md` / `docs/006-registries.md` / `docs/007-operations.md` / `docs/009-health.md` / `/Users/blackdj/Documents/VPS-Config/docs/05-unified-execution-plan.md` — 同步闭环覆盖清单和当前 live 结论。
### 验证
- `packages/clawbot/.venv312/bin/python -m py_compile packages/clawbot/src/xianyu/xianyu_admin.py packages/clawbot/tests/test_api_routes_regression.py` → 通过。
- `cd packages/clawbot && .venv312/bin/python -m pytest tests/test_api_routes_regression.py tests/test_xianyu_cc_auto_ship.py -q` → `92 passed / 0 failed`。
- `make test` → 跑到 `[100%]`，退出码 `0`。
- 重启 `ai.openclaw.xianyu` 后 live `/api/cc-automation-coverage` 返回 HTTP 200，`completed=10`、`total=11`、`internal_automation_ready=true`、`public_sale_ready=false`、`external_blocker=true`。
- `node scripts/cc_zhongzhuan_readiness_audit.mjs --mode=read_only --json` → `ok=true`，Chrome 书签、本机闲鱼 GUI、Oracle 服务、库存、兑换码、渠道、公网安全门均通过。


## [2026-07-05] 买家闭环严格门进度恢复修复
> 领域: `xianyu` | `backend` | `docs`
> 影响模块: `XianyuAdmin`, `Buyer Chain Progress`, `Ops Notify`
> 关联问题: HI-907
### 变更内容
- 修复严格门通过后，内存态/SQLite 恢复的买家进度可能缺少 `same_order_latest` 明细，导致 GUI 误显示“买家尚未兑换/尚未创建 API Key/尚未调模型”的问题。
- 严格门摘要现在会保留脱敏后的同单分阶段信息：订单前缀/哈希、履约状态、卡密状态、New-API 兑换状态、API Key 数量、兑换后模型调用数和 ready 标记；不会保存卡密、Token 或 API Key。
- 即使读取到旧格式严格门缓存，只要 `same_order_ready>0`，买家进度也会按“已闭环”显示，避免正式售卖前误判。
### 文件变更
- `packages/clawbot/src/xianyu/xianyu_admin.py` — 新增严格门摘要脱敏保留逻辑，并修正买家进度 verified 状态。
- `packages/clawbot/tests/test_api_routes_regression.py` — 覆盖严格门摘要恢复、敏感字段过滤、完整闭环进度和旧缓存兼容。
- `docs/002-changelog.md` / `docs/006-registries.md` / `docs/007-operations.md` / `docs/009-health.md` / `/Users/blackdj/Documents/VPS-Config/docs/05-unified-execution-plan.md` — 同步闭环进度恢复口径。
### 验证
- `packages/clawbot/.venv312/bin/python -m py_compile packages/clawbot/src/xianyu/xianyu_admin.py packages/clawbot/tests/test_api_routes_regression.py` → 通过。
- `cd packages/clawbot && .venv312/bin/python -m pytest tests/test_api_routes_regression.py tests/test_xianyu_cc_auto_ship.py -q` → `92 passed / 0 failed`。
- `make test` → 跑到 `[100%]`，退出码 `0`。
- 重启 `ai.openclaw.xianyu` 后 live `/api/status`、`/api/cc-loop-watch`、`/api/cc-buyer-chain-progress`、`/api/cc-ops-snapshot`、`/api/cc-public-sale-lock?refresh=true` 均为 HTTP 200；当前仍为 `waiting_paid_order/internal_test_ready`。
- `node scripts/cc_zhongzhuan_readiness_audit.mjs --mode=read_only --json` → `ok=true`，Chrome 书签、本机闲鱼 GUI、Oracle 服务、库存、兑换码、渠道、公网安全门均通过。


## [2026-07-05] 闲鱼已付款订单商品 ID 优先识别
> 领域: `xianyu` | `backend` | `docs`
> 影响模块: `XianyuLive`, `CC Auto Ship`, `Chrome Ops`
> 关联问题: HI-907
### 变更内容
- 已付款订单自动发货现在会优先从订单结构字段或闲鱼 URL/query 参数里的 `itemId`、`item_id`、`itemIdStr`、`item_id_str` 提取商品 ID，再回退最近聊天商品，最后才走默认套餐。
- 该识别只读取订单字段和 URL 类字段，不扫描普通聊天文本，避免买家聊天里复制 `itemId=xxx` 时污染商品套餐映射。
- 重新执行 Chrome 运营入口修复：4 个 Chrome Profile 的 `CC中转运营` 书签文件夹均为 7 个入口，并打开本机运营入口总页；Chrome 内部书签管理页因安全策略不能由自动化打开。
### 文件变更
- `packages/clawbot/src/xianyu/xianyu_live.py` — 新增商品 ID 提取器，并在 paid 分支优先使用订单自带商品 ID。
- `packages/clawbot/tests/test_xianyu_cc_auto_ship.py` — 覆盖 URL 参数、结构化商品字段、普通聊天误污染保护和 paid 分支优先级。
- `docs/002-changelog.md` / `docs/006-registries.md` / `docs/007-operations.md` / `docs/009-health.md` / `/Users/blackdj/Documents/VPS-Config/docs/05-unified-execution-plan.md` — 同步全自动发货商品路由口径。
### 验证
- `packages/clawbot/.venv312/bin/python -m py_compile packages/clawbot/src/xianyu/xianyu_live.py packages/clawbot/tests/test_xianyu_cc_auto_ship.py` → 通过。
- `cd packages/clawbot && .venv312/bin/python -m pytest tests/test_xianyu_cc_auto_ship.py -q` → `54 passed / 0 failed`。
- `cd packages/clawbot && .venv312/bin/python -m pytest tests/test_api_routes_regression.py tests/test_xianyu_cc_auto_ship.py -q` → `90 passed / 0 failed`。
- `make test` → 跑到 `[100%]`，退出码 `0`。
- 重启 `ai.openclaw.xianyu` 后 live `/api/status` 返回 `ws_connected=true`、`cookie_ok=true`、CC自动发货已配置、补救队列 0；`/api/cc-real-order-test-pack` 返回 `state=run_real_small_order`、`can_start_real_order_test=true`，`/api/cc-public-sale-lock?refresh=true` 返回 `internal_test_ready`、正式售卖仍因真实小额单严格门未过而锁定。
- `node scripts/cc_zhongzhuan_readiness_audit.mjs --mode=read_only --json` → `ok=true`；Chrome 4 个 Profile 书签 OK，本机闲鱼 GUI/API OK，Oracle 服务 active，未售卡密 5、New-API 启用兑换码 5、启用渠道 3，公网主站 200、未授权模型/发货接口 401。


## [2026-07-05] 闲鱼订单状态字段位置识别补强
> 领域: `xianyu` | `backend` | `docs`
> 影响模块: `XianyuLive`, `CC Auto Ship`
> 关联问题: HI-907
### 变更内容
- 已付款订单识别不再只依赖 `message["3"].redReminder`，现在会从 `orderInfo/statusText`、`tradeInfo/tradeStatusText`、`bizOrderInfo/payStatusText`、`3/reminderContent` 等订单相关结构化字段提取状态。
- 为避免误发卡，识别范围刻意不扫描普通聊天文本，也不把商品 `title/subTitle` 当状态字段；聊天里出现“我已付款了吗”不会触发自动发货。
- 新逻辑已随本机 `ai.openclaw.xianyu` 重启加载，当前生产内测仍为 `run_real_small_order`，等待真实小额单。
### 文件变更
- `packages/clawbot/src/xianyu/xianyu_live.py` — 新增订单状态候选字段提取器和单条状态分类函数。
- `packages/clawbot/tests/test_xianyu_cc_auto_ship.py` — 覆盖字段位置变化和普通聊天误触发保护。
- `docs/002-changelog.md` / `docs/006-registries.md` / `docs/007-operations.md` / `docs/009-health.md` / `/Users/blackdj/Documents/VPS-Config/docs/05-unified-execution-plan.md` — 同步状态字段识别口径。
### 验证
- `cd packages/clawbot && .venv312/bin/python -m pytest tests/test_xianyu_cc_auto_ship.py -q` → `50 passed / 0 failed`。
- `packages/clawbot/.venv312/bin/python -m py_compile packages/clawbot/src/xianyu/xianyu_live.py packages/clawbot/tests/test_xianyu_cc_auto_ship.py packages/clawbot/src/xianyu/xianyu_admin.py packages/clawbot/tests/test_api_routes_regression.py && cd packages/clawbot && .venv312/bin/python -m pytest tests/test_api_routes_regression.py tests/test_xianyu_cc_auto_ship.py -q` → `86 passed / 0 failed`。
- 重启 `ai.openclaw.xianyu` 后 live `/api/status` 返回 `ws_connected=true`、`cookie_ok=true`、自动发货已配置、补救队列 0；`/api/cc-real-order-test-pack` 返回 `run_real_small_order`。


## [2026-07-05] 闲鱼已付款状态识别变体补强
> 领域: `xianyu` | `backend` | `docs`
> 影响模块: `XianyuLive`, `CC Auto Ship`
> 关联问题: HI-907
### 变更内容
- 闲鱼订单状态识别从单一“等待卖家发货”扩展为支持“待发货 / 等待发货 / 买家已付款 / 已支付 / 已付款等待卖家发货”等常见变体，降低真实小额单漏发风险。
- 增加安全优先判断：`待付款 / 未付款 / 等待买家付款 / 退款 / 交易关闭` 等状态绝不会进入自动发货，避免未付款误发卡。
- 新状态识别已随本机 `ai.openclaw.xianyu` 重启加载，当前生产内测仍保持自动发货可用、正式售卖锁定。
### 文件变更
- `packages/clawbot/src/xianyu/xianyu_live.py` — 增加订单状态规整和付款/未付款保护判断。
- `packages/clawbot/tests/test_xianyu_cc_auto_ship.py` — 覆盖已付款变体和未付款/退款/关闭误发保护。
- `docs/002-changelog.md` / `docs/006-registries.md` / `docs/007-operations.md` / `docs/009-health.md` / `/Users/blackdj/Documents/VPS-Config/docs/05-unified-execution-plan.md` — 同步状态识别口径。
### 验证
- `cd packages/clawbot && .venv312/bin/python -m pytest tests/test_xianyu_cc_auto_ship.py -q` → `48 passed / 0 failed`。
- `packages/clawbot/.venv312/bin/python -m py_compile packages/clawbot/src/xianyu/xianyu_live.py packages/clawbot/tests/test_xianyu_cc_auto_ship.py packages/clawbot/src/xianyu/xianyu_admin.py packages/clawbot/tests/test_api_routes_regression.py && cd packages/clawbot && .venv312/bin/python -m pytest tests/test_api_routes_regression.py tests/test_xianyu_cc_auto_ship.py -q` → `84 passed / 0 failed`。
- 重启 `ai.openclaw.xianyu` 后 live `/api/status` 返回 `ws_connected=true`、`cookie_ok=true`、`auto_ship_configured=true`、`pending_rescue=0`；`/api/cc-real-order-test-pack` 返回 `run_real_small_order`。


## [2026-07-05] CC中转真实小额单验收包
> 领域: `xianyu` | `backend` | `docs`
> 影响模块: `XianyuAdmin`, `Ops Links`, `Public Sale Lock`
> 关联问题: HI-907
### 变更内容
- 新增 `GET /api/cc-real-order-test-pack`，把真实小额单验收所需的状态、步骤、入口、商品模板和安全边界聚合成一份只读“实单验收包”。
- `/ops-links` 和本机闲鱼 GUI 新增“实单验收包”卡片，显示从发布小额测试商品、自动发货、买家兑换、创建 API Key、CC Switch 导入、调模型到严格门的逐步状态。
- 服务刚重启且库存/渠道证据为空时，验收包会自动触发一次只读巡检刷新证据；不发货、不分配卡密、不发送闲鱼消息、不修改库存。
### 文件变更
- `packages/clawbot/src/xianyu/xianyu_admin.py` — 新增实单验收包摘要、API 路由和两处 GUI 渲染。
- `packages/clawbot/tests/test_api_routes_regression.py` — 覆盖实单验收包页面入口、API 字段、步骤和安全边界。
- `docs/002-changelog.md` / `docs/006-registries.md` / `docs/007-operations.md` / `docs/009-health.md` / `/Users/blackdj/Documents/VPS-Config/docs/05-unified-execution-plan.md` — 同步运营口径。
### 验证
- `packages/clawbot/.venv312/bin/python -m py_compile packages/clawbot/src/xianyu/xianyu_admin.py packages/clawbot/tests/test_api_routes_regression.py && cd packages/clawbot && .venv312/bin/python -m pytest tests/test_api_routes_regression.py tests/test_xianyu_cc_auto_ship.py -q` → `62 passed / 0 failed`。
- 重启 `ai.openclaw.xianyu` 后 live `/api/cc-real-order-test-pack` 返回 `state=run_real_small_order`、`can_start_real_order_test=true`、`can_public_sale=false`，上架锁保持 `internal_test_ready`、未售卡密 5、`ccswitch_import_ready=true`。


## [2026-07-05] CC中转 CC Switch 导入入口纳入上架锁
> 领域: `xianyu` | `backend` | `infra` | `docs`
> 影响模块: `Readiness Audit`, `XianyuAdmin`, `Public Sale Lock`, `Ops GUI`
> 关联问题: HI-907
### 变更内容
- 生产闭环只读巡检新增 Frist 公开首页的 CC Switch 导入入口检查：页面必须 HTTP 200，并包含 CC Switch 文案、`ccswitch` 标记和 `data-import-link` 导入按钮标记。
- `/api/cc-sale-readiness`、`/api/cc-public-sale-lock` 和本机 GUI 新增 `ccswitch_import` / `ccswitch_import_ready` 门槛；导入入口异常时内测发货和正式售卖都会被上架锁拦住。
- Chrome 已重新打开可见 `📌 CC中转运营入口` 标签组，包含 7 个运营入口，解决用户看不到书签组的问题；书签文件夹仍保留为长期入口。
### 文件变更
- `scripts/cc_zhongzhuan_readiness_audit.mjs` — 新增 CC Switch 导入入口公网探测，并纳入 Oracle/public 只读巡检结果。
- `packages/clawbot/src/xianyu/xianyu_admin.py` — 上架锁、自动化水位和 GUI 展示新增 CC Switch 导入入口状态。
- `packages/clawbot/tests/test_api_routes_regression.py` — 覆盖导入入口通过、刷新缓存、导入入口异常阻断上架锁。
- `docs/002-changelog.md` / `docs/006-registries.md` / `docs/007-operations.md` / `docs/009-health.md` / `/Users/blackdj/Documents/VPS-Config/docs/05-unified-execution-plan.md` — 同步生产内测闭环口径。
### 验证
- `node --check scripts/cc_zhongzhuan_readiness_audit.mjs && packages/clawbot/.venv312/bin/python -m py_compile packages/clawbot/src/xianyu/xianyu_admin.py packages/clawbot/tests/test_api_routes_regression.py && cd packages/clawbot && .venv312/bin/python -m pytest tests/test_api_routes_regression.py tests/test_xianyu_cc_auto_ship.py -q` → `62 passed / 0 failed`。
- `node scripts/cc_zhongzhuan_readiness_audit.mjs --mode=read_only --json` → `ok=true`，`ccswitch_entry.http=200`，`ccswitch_entry.ok=true`，导入标记齐全。


## [2026-07-05] CC中转买家自助入口健康纳入上架锁
> 领域: `xianyu` | `backend` | `infra` | `docs`
> 影响模块: `XianyuAdmin`, `Readiness Audit`, `Public Sale Lock`
> 关联问题: HI-907
### 变更内容
- 闭环审计摘要现在保留买家自助入口健康：用户主站 HTTP、`/v1/models` 未授权 HTTP、闲鱼发货 webhook 未授权 HTTP。
- 上架锁新增 `buyer_self_service_ready` 和 `webhook_public_locked` 两个门槛；如果买家主站/API 网关异常，或 webhook 未授权访问没有被拦截，内测/正式售卖都会被锁住。
- `/api/cc-sale-readiness` 和 GUI 自动化水位新增 `buyer_self_service`，直接展示买家入口是否可用，避免真实订单后买家打不开页面才发现问题。
### 文件变更
- `packages/clawbot/src/xianyu/xianyu_admin.py` — 摘要、上架锁、自动化水位和 GUI 展示增加买家入口健康门槛。
- `packages/clawbot/tests/test_api_routes_regression.py` — 覆盖买家入口健康通过与异常阻断上架锁。
- `docs/002-changelog.md` / `docs/006-registries.md` / `docs/007-operations.md` / `docs/009-health.md` / `/Users/blackdj/Documents/VPS-Config/docs/05-unified-execution-plan.md` — 同步买家入口健康口径。
### 验证
- `packages/clawbot/.venv312/bin/python -m py_compile packages/clawbot/src/xianyu/xianyu_admin.py packages/clawbot/tests/test_api_routes_regression.py && cd packages/clawbot && .venv312/bin/python -m pytest tests/test_api_routes_regression.py tests/test_xianyu_cc_auto_ship.py -q` → `61 passed / 0 failed`。
- 重启 `ai.openclaw.xianyu` 并刷新上架锁后 live 返回：买家主站 `200`、`/v1/models` 未授权 `401`、webhook 未授权 `401`、`buyer_self_service_ready=true`、`webhook_public_locked=true`；当前唯一 blocker 仍是真实小额单严格门未过。
- `make test` → 跑到 `[100%]`，退出码 `0`。

## [2026-07-05] CC中转自动发货套餐路由预判
> 领域: `xianyu` | `backend` | `docs`
> 影响模块: `XianyuAdmin`, `CC Auto Ship`, `Ops GUI`
> 关联问题: HI-907
### 变更内容
- 新增 `cc_auto_plan_routing` / `plan_routing` 状态摘要，明确无商品映射订单会按商品映射、默认套餐还是库存兜底发货，并给出风险等级。
- 当前生产内测 live 已显示 `mode=default_plan`、`default_plan_id_present=true`、`risk=low`，表示单商品真实小额单会按当前默认日卡套餐发货，不再需要老板理解 planId。
- `/api/cc-sale-readiness` 的 `human_required` 不再把“单商品默认套餐”误提示成必须介入事项；当前只剩真实小额单严格门和上游续费/补货。
### 文件变更
- `packages/clawbot/src/xianyu/xianyu_admin.py` — 新增自动发货套餐路由摘要，并接入 `/api/status`、`/api/cc-sale-readiness` 和 GUI 展示。
- `packages/clawbot/tests/test_api_routes_regression.py` — 覆盖默认套餐路由和商品映射优先路由。
- `docs/002-changelog.md` / `docs/006-registries.md` / `docs/007-operations.md` / `docs/009-health.md` / `/Users/blackdj/Documents/VPS-Config/docs/05-unified-execution-plan.md` — 同步套餐路由预判口径。
### 验证
- `packages/clawbot/.venv312/bin/python -m py_compile packages/clawbot/src/xianyu/xianyu_admin.py packages/clawbot/tests/test_api_routes_regression.py && cd packages/clawbot && .venv312/bin/python -m pytest tests/test_api_routes_regression.py tests/test_xianyu_cc_auto_ship.py -q` → `60 passed / 0 failed`。
- 重启 `ai.openclaw.xianyu` 后 live `/api/status` 与 `/api/cc-sale-readiness` 均返回 `plan_routing.mode=default_plan`、`risk=low`、`can_ship_unmapped_order=true`；`human_required` 只剩真实小额单严格门和上游续费/补货。
- `make test` → 跑到 `[100%]`，退出码 `0`。

## [2026-07-05] CC中转后台严格门观察状态可视化
> 领域: `xianyu` | `backend` | `docs`
> 影响模块: `XianyuAdmin`, `Strict Audit`, `Ops GUI`
> 关联问题: HI-907
### 变更内容
- 本机闲鱼助手新增 `cc_background_strict_audit` 状态摘要，展示后台严格门观察是否启用、节流间隔、最近运行时间和最近运行结果。
- `/api/cc-loop-watch` 现在返回 `last_background_strict_audit`，GUI 的“实单闭环观察”卡片会展示后台严格门观察最近是否运行、结果和原因，避免真实订单后老板不知道后台是否在值守。
- 不改变发货、不分配卡密、不发送闲鱼消息；该状态只读，仅用于确认真实订单后的自动严格门观察是否工作。
### 文件变更
- `packages/clawbot/src/xianyu/xianyu_admin.py` — 记录并暴露后台严格门最近运行结果，GUI 显示后台观察状态。
- `packages/clawbot/tests/test_api_routes_regression.py` — 覆盖状态接口和 loop-watch 返回后台严格门最近结果。
- `docs/002-changelog.md` / `docs/006-registries.md` / `docs/007-operations.md` / `docs/009-health.md` / `/Users/blackdj/Documents/VPS-Config/docs/05-unified-execution-plan.md` — 同步后台严格门观察状态口径。
### 验证
- `packages/clawbot/.venv312/bin/python -m py_compile packages/clawbot/src/xianyu/xianyu_admin.py packages/clawbot/tests/test_api_routes_regression.py && cd packages/clawbot && .venv312/bin/python -m pytest tests/test_api_routes_regression.py tests/test_xianyu_cc_auto_ship.py -q` → `60 passed / 0 failed`。
- 重启 `ai.openclaw.xianyu` 后 live `/api/status` 返回 `cc_background_strict_audit.enabled=true`，`/api/cc-loop-watch` 返回 `background_strict_audit_enabled=true`；当前 `last_background_strict_audit={}` 属于正常状态，因为尚未出现真实已付款订单。
- `make test` → 跑到 `[100%]`，退出码 `0`。

## [2026-07-05] CC中转闲鱼默认发货套餐固定
> 领域: `xianyu` | `infra` | `docs`
> 影响模块: `XianyuLive`, `Xianyu Config`, `CC Auto Ship`
> 关联问题: HI-907
### 变更内容
- 本机闲鱼助手生产内测配置已固定 `CC_XIANYU_DEFAULT_PLAN_ID` 为当前唯一未售库存对应的日卡 planId，避免真实小额单无商品映射时靠服务端兜底随机分配。
- 重启 `ai.openclaw.xianyu` 后 live `/api/status` 显示 `default_plan_id_present=true`，自动发货仍配置正常、WebSocket/Cookie 正常、补救队列为 0。
- 文档同步“一个商品可用默认套餐，多商品正式上架前仍优先配置 item_id → planId 映射”的运营口径。
### 文件变更
- `packages/clawbot/config/.env.example` — 增加默认 planId 配置说明。
- `docs/002-changelog.md` / `docs/006-registries.md` / `docs/007-operations.md` / `docs/009-health.md` / `/Users/blackdj/Documents/VPS-Config/docs/05-unified-execution-plan.md` — 同步默认发货套餐已固定。
### 验证
- 只读审计确认当前唯一未售库存：`unused_by_plan={"day|quotaUsd=30|source=xianyu":5}`。
- 重启本机助手后 live `/api/status` → `cc_auto_ship.configured=true`、`default_plan_id_present=true`、`ws_connected=true`、`cookie_ok=true`；live `/api/cc-public-sale-lock?refresh=true` → `state=internal_test_ready`、`unused_cards=5`、`enabled_redemptions=5`、`enabled_channels=3`、`can_public_sale=false`，唯一 blocker 仍为真实小额单严格门未过。

## [2026-07-05] CC中转全自动闭环复验与订单 URL 幂等补强
> 领域: `xianyu` | `backend` | `infra` | `docs`
> 影响模块: `XianyuLive`, `Chrome Bookmarks`, `WorldMonitor`, `CC Auto Ship`
> 关联问题: HI-907
### 变更内容
- `XianyuLive` 的稳定订单号提取继续补强：除字段名包含 order/trade/bizOrder 外，现在也会从闲鱼 URL/query 参数里的 `orderId`、`tradeId`、`bizOrderId`、`biz_order_id` 提取真实订单号并哈希成 `xy_oid_*`，避免同一已付款订单因重复推送或消息里有时间戳变化而二次分配卡密。
- 重新修复并复验 Chrome `CC中转运营` 书签文件夹：`Default`、`Profile 1`、`Profile 2`、`Profile 3` 均为 7 个入口且书签栏开启；只读生产闭环审计里的 `chromeBookmarks` 已转绿。
- 重启本机 `ai.openclaw.xianyu` 后复验生产内测状态：WebSocket/Cookie 正常、CC自动发货已配置、补救队列为 0、未售卡密 5、启用兑换码 5、启用渠道 3；当前仍锁在“等待真实闲鱼小额单”阶段，未放开正式售卖。
- 修复 `WorldMonitor` 风险等级偶发测试红灯：风险等级现在按最终展示分数计算，并改用稳定哈希种子，避免 49.96 显示为 50.0 但等级仍为 `moderate` 的边界不一致。
### 文件变更
- `packages/clawbot/src/xianyu/xianyu_live.py` — URL/query 参数订单号提取、稳定 orderId 幂等保护补强。
- `packages/clawbot/tests/test_xianyu_cc_auto_ship.py` — 增加 URL 参数订单号在 volatile 字段变化时仍稳定的回归测试。
- `packages/clawbot/src/monitoring/world_monitor.py` — 修复风险等级与展示分数边界不一致。
- `docs/002-changelog.md` / `docs/006-registries.md` / `docs/007-operations.md` / `docs/009-health.md` / `/Users/blackdj/Documents/VPS-Config/docs/05-unified-execution-plan.md` — 同步生产内测闭环状态。
### 验证
- `cd packages/clawbot && .venv312/bin/python -m pytest tests/test_xianyu_cc_auto_ship.py tests/test_api_routes_regression.py tests/test_world_monitor.py -q` → `85 passed / 0 failed`。
- `make test` → 跑到 `[100%]`，退出码 `0`。
- `node scripts/cc_zhongzhuan_chrome_bookmarks.mjs --json && node scripts/cc_zhongzhuan_readiness_audit.mjs --mode=read_only --json` → `chromeBookmarks.ok=true`。
- live `/api/cc-public-sale-lock?refresh=true` → `state=internal_test_ready`、`can_internal_test=true`、`can_public_sale=false`、唯一 blocker 为尚未通过真实闲鱼小额单兑换/API/调模型严格门。






## [2026-07-05] CC中转闲鱼自动发货幂等保护
> 领域: `xianyu` | `backend` | `docs`
> 影响模块: `XianyuLive`, `XianyuContext`, `CC Auto Ship`
> 关联问题: HI-907
### 变更内容
- 闲鱼已付款订单不再使用随机 UUID 作为 `orderId`；优先从消息中抽取真实订单/交易 ID 并哈希成稳定 `xy_oid_*`，抽不到时用消息指纹生成稳定 `xy_msg_*`。
- 自动发货前会先按 `orderId` 查询本机 `cc_shipments`：已发货直接跳过，已分配但发送失败则只补发旧话术，异常/人工处理记录不再重新分配卡密。
- SQLite 增加 `get_cc_shipment_by_order_id()`，用于重复订单事件的幂等保护。
### 文件变更
- `packages/clawbot/src/xianyu/xianyu_live.py` — 新增稳定订单号生成、真实订单号提取、重复履约记录复用和失败话术补发分支。
- `packages/clawbot/src/xianyu/xianyu_context.py` — 新增按 `order_id` 读取 CC中转履约记录。
- `packages/clawbot/tests/test_xianyu_cc_auto_ship.py` — 覆盖稳定订单号、重复已发货跳过 webhook、重复发送失败只补发旧话术和 SQLite 按订单号读取。
- `docs/002-changelog.md` / `docs/006-registries.md` / `docs/007-operations.md` / `/Users/blackdj/Documents/VPS-Config/docs/05-unified-execution-plan.md` — 同步幂等发货口径。
### 验证
- `packages/clawbot/.venv312/bin/python -m py_compile packages/clawbot/src/xianyu/xianyu_live.py packages/clawbot/src/xianyu/xianyu_context.py packages/clawbot/tests/test_xianyu_cc_auto_ship.py && cd packages/clawbot && .venv312/bin/python -m pytest tests/test_xianyu_cc_auto_ship.py -q` → `25 passed / 0 failed`。

## [2026-07-05] CC中转真实订单买家卡点提醒
> 领域: `xianyu` | `backend` | `docs`
> 影响模块: `XianyuAdmin`, `Ops Notify`, `Buyer Chain`
> 关联问题: HI-907
### 变更内容
- 本机运营提醒现在能在真实订单已发货后识别买家侧卡点：等待严格门、未兑换、未创建 API Key、未调模型、同单匹配待确认、已闭环。
- 买家卡点提醒优先级高于低库存，避免真实订单发生后通知仍只提示“库存偏低”。
- 严格门转绿时会提醒“真实单买家闭环已通过”；提醒只发给本机运营者，不自动催买家、不批量私信、不触发发货或库存写入。
### 文件变更
- `packages/clawbot/src/xianyu/xianyu_admin.py` — 新增 `_buyer_chain_notification_override()`，并把 `buyer_attention_stage` 纳入提醒签名和返回 payload。
- `packages/clawbot/tests/test_xianyu_cc_auto_ship.py` — 覆盖买家未调模型优先于低库存、严格门通过提醒两条分支。
- `docs/002-changelog.md` / `docs/006-registries.md` / `docs/007-operations.md` / `/Users/blackdj/Documents/VPS-Config/docs/05-unified-execution-plan.md` — 同步买家卡点提醒口径。
### 验证
- `packages/clawbot/.venv312/bin/python -m py_compile packages/clawbot/src/xianyu/xianyu_admin.py packages/clawbot/tests/test_xianyu_cc_auto_ship.py && cd packages/clawbot && .venv312/bin/python -m pytest tests/test_xianyu_cc_auto_ship.py -q` → `21 passed / 0 failed`。

## [2026-07-05] CC中转本机运营提醒与 Chrome 可见标签组
> 领域: `xianyu` | `backend` | `infra` | `docs`
> 影响模块: `XianyuAdmin`, `Ops Links`, `Chrome Bookmarks`
> 关联问题: HI-907
### 变更内容
- Chrome 已创建可见标签组 `📌 CC中转运营入口`，包含本机运营入口、闲鱼 GUI、用户主站、New-API 后台、Frist 运营台和模型检查入口；同时继续保留 `CC中转运营` 书签文件夹。
- 本机闲鱼管理服务新增后台运营提醒线程：状态变化、WebSocket/Cookie 异常、发货补救队列、低库存、真实单闭环状态变化时弹 macOS 本机通知。
- 新增 `POST /api/cc-ops-notify/check`，供 `/ops-links` 的“本机提醒”卡片手动发送当前状态提醒；该接口只读，不发货、不分配卡密、不改库存。
- `/ops-links` 增加“本机提醒”卡片，展示后台值守状态、提醒间隔、低库存阈值和最近提醒摘要。
### 文件变更
- `packages/clawbot/src/xianyu/xianyu_admin.py` — 新增本机运营提醒配置、通知 payload、macOS 通知发送、后台线程、手动检查接口和 `/ops-links` 提醒卡片。
- `packages/clawbot/tests/test_xianyu_cc_auto_ship.py` / `packages/clawbot/tests/test_api_routes_regression.py` — 增加提醒 payload、dry-run 路由和全局状态隔离测试。
- `docs/002-changelog.md` / `docs/006-registries.md` / `docs/007-operations.md` / `docs/009-health.md` / `/Users/blackdj/Documents/VPS-Config/docs/05-unified-execution-plan.md` — 同步全自动运营提醒口径。
### 验证
- `packages/clawbot/.venv312/bin/python -m py_compile packages/clawbot/src/xianyu/xianyu_admin.py packages/clawbot/tests/test_xianyu_cc_auto_ship.py packages/clawbot/tests/test_api_routes_regression.py && cd packages/clawbot && .venv312/bin/python -m pytest tests/test_xianyu_cc_auto_ship.py tests/test_api_routes_regression.py -q` → `52 passed / 0 failed`。
- 本机助手已重启，live `POST /api/cc-ops-notify/check?force=true` 返回 `sent=true`、`state=run_real_small_order`、`unused_cards=5`；live `/api/cc-ops-snapshot` 返回 `ok=true`、`sale_lock.state=internal_test_ready`、`loop_stage=waiting_paid_order`。
- Chrome openTabs 验证 5 个入口位于 `📌 CC中转运营入口` 标签组；总控页截图保存到 `output/cc-ops-links-status.png`。

## [2026-07-05] 新增 CC中转运营统一快照接口
> 领域: `xianyu` | `backend` | `docs`
> 影响模块: `XianyuAdmin`, `Ops Links`, `Xianyu GUI`
> 关联问题: HI-907
### 变更内容
- 新增 `GET /api/cc-ops-snapshot`，一次性返回当前行动建议、上架锁、自动发货状态、实单闭环和买家进度。
- `/ops-links` 与本机 GUI 已读取该快照，为后续通知/看板复用同一份安全状态做准备。
- 该接口只读，不触发审计、不发货、不分配卡密、不修改库存。
### 文件变更
- `packages/clawbot/src/xianyu/xianyu_admin.py` — 新增 `_cc_ops_snapshot_summary()` 和 `/api/cc-ops-snapshot`。
- `packages/clawbot/tests/test_api_routes_regression.py` — 覆盖快照接口、页面标记和关键字段。
- `docs/002-changelog.md` / `docs/006-registries.md` / `docs/007-operations.md` / `docs/009-health.md` / `/Users/blackdj/Documents/VPS-Config/docs/05-unified-execution-plan.md` — 同步运营快照口径。
### 验证
- `cd packages/clawbot && .venv312/bin/python -m py_compile src/xianyu/xianyu_admin.py && .venv312/bin/python -m pytest tests/test_api_routes_regression.py tests/test_xianyu_cc_auto_ship.py -q` → `50 passed / 0 failed`。
- 重启 `ai.openclaw.xianyu` 并只读刷新上架锁后，live `/api/cc-ops-snapshot` 返回 `ok=true`、`next_action.state=run_real_small_order`、`sale_lock.state=internal_test_ready`、`loop_stage=waiting_paid_order`。

## [2026-07-05] 统一下一步行动建议接口
> 领域: `xianyu` | `backend` | `docs`
> 影响模块: `XianyuAdmin`, `Ops Links`, `Xianyu GUI`
> 关联问题: HI-907
### 变更内容
- 新增 `GET /api/cc-operator-next-action`，把上架锁、自动发货、补救队列、真实订单和买家链路汇总为统一“下一步行动”。
- `/ops-links` 和本机闲鱼 GUI 改用同一套建议，避免一个页面提示“可以测试”，另一个页面仍提示“库存证据未刷新”。
- 服务刚重启且库存/渠道证据未刷新时，接口会优先提示刷新上架锁；证据刷新后才提示发布 1 单小额闲鱼测试商品。
- 该接口只读，不触发审计、不发货、不分配卡密、不修改库存。
### 文件变更
- `packages/clawbot/src/xianyu/xianyu_admin.py` — 新增 `_cc_operator_next_action_summary()`、`/api/cc-operator-next-action`，并接入 `/ops-links` 与 GUI。
- `packages/clawbot/tests/test_api_routes_regression.py` — 覆盖统一建议接口、库存证据未刷新分支、页面标记和 checklist。
- `docs/002-changelog.md` / `docs/006-registries.md` / `docs/007-operations.md` / `docs/009-health.md` / `/Users/blackdj/Documents/VPS-Config/docs/05-unified-execution-plan.md` — 同步运营口径。
### 验证
- `cd packages/clawbot && .venv312/bin/python -m py_compile src/xianyu/xianyu_admin.py && .venv312/bin/python -m pytest tests/test_api_routes_regression.py tests/test_xianyu_cc_auto_ship.py -q` → `50 passed / 0 failed`。
- 重启 `ai.openclaw.xianyu` 后，刷新证据前 live 接口返回 `state=locked`、`primary_action=库存/渠道证据未刷新，请点“刷新上架锁”`；刷新后返回 `state=run_real_small_order`、`primary_action=发布 1 个小额闲鱼测试商品，完成真实付款；系统会自动发卡。`

## [2026-07-05] 买家自助链路进度增加只读接口
> 领域: `xianyu` | `backend` | `docs`
> 影响模块: `XianyuAdmin`, `Ops Links`, `Readiness Audit`
> 关联问题: HI-907
### 变更内容
- 新增 `GET /api/cc-buyer-chain-progress`，把真实订单买家侧进度聚合成“已发货、已兑换、API Key、调模型、同单闭环”五步。
- Chrome 书签第一入口 `/ops-links` 增加“买家进度”卡片；本机闲鱼 GUI 增加“买家自助链路进度”卡片。
- 该接口只读，不触发严格门、不发货、不分配卡密、不修改库存；用于真实订单后判断买家卡在兑换、创建 API Key 还是模型调用。
### 文件变更
- `packages/clawbot/src/xianyu/xianyu_admin.py` — 新增 `_cc_buyer_chain_progress_summary()`、`/api/cc-buyer-chain-progress` 和两处 GUI 渲染。
- `packages/clawbot/tests/test_api_routes_regression.py` — 覆盖新接口、运营入口和 GUI 标记。
- `docs/002-changelog.md` / `docs/006-registries.md` / `docs/007-operations.md` / `docs/009-health.md` / `/Users/blackdj/Documents/VPS-Config/docs/05-unified-execution-plan.md` — 同步买家自助链路进度口径。
### 验证
- `cd packages/clawbot && .venv312/bin/python -m py_compile src/xianyu/xianyu_admin.py && .venv312/bin/python -m pytest tests/test_api_routes_regression.py tests/test_xianyu_cc_auto_ship.py -q` → `49 passed / 0 failed`。
- 重启 `ai.openclaw.xianyu` 后，live `/api/cc-buyer-chain-progress` 返回 `stage=waiting_paid_order`、五步均未完成、下一步为发布闲鱼商品并跑 1 单小额真实付款；`/ops-links` 包含“买家进度”和新接口调用。

## [2026-07-05] 实单买家闭环结果回写到发货记录
> 领域: `xianyu` | `backend` | `docs`
> 影响模块: `XianyuContext`, `XianyuAdmin`, `Readiness Audit`
> 关联问题: HI-907
### 变更内容
- `cc_shipments` 增加 `buyer_chain_status`、`buyer_chain_verified_at`、`buyer_chain_note`，用于记录某条真实闲鱼发货是否已完成买家兑换、创建 API Key 和调模型闭环。
- 正式售卖严格门通过后，`record_cc_strict_audit()` 会按订单哈希把同一真实订单标记为 `buyer_chain_status=verified`；审计摘要不保存完整订单号。
- 本机 GUI/运营入口的实单闭环卡片会显示“已闭环订单数”，让老板能区分“已发货”和“买家已经完整跑通”。
- 老 SQLite 表会在启动时自动补列，避免当前生产内测本机库因缺列启动失败。
### 文件变更
- `packages/clawbot/src/xianyu/xianyu_context.py` — 新增买家闭环字段、老库补列、哈希匹配回写和统计字段。
- `packages/clawbot/src/xianyu/xianyu_admin.py` — 状态接口和 GUI 增加已闭环订单数。
- `scripts/cc_zhongzhuan_readiness_audit.mjs` — 同单严格门摘要增加订单哈希，供本机安全匹配回写。
- `packages/clawbot/tests/test_xianyu_cc_auto_ship.py` — 覆盖严格门回写和老 SQLite 表迁移。
### 验证
- `cd packages/clawbot && .venv312/bin/python -m pytest tests/test_xianyu_cc_auto_ship.py -q` → `17 passed / 0 failed`。
- `cd packages/clawbot && .venv312/bin/python -m py_compile src/xianyu/xianyu_context.py src/xianyu/xianyu_admin.py && .venv312/bin/python -m pytest tests/test_xianyu_cc_auto_ship.py tests/test_api_routes_regression.py -q && node --check scripts/cc_zhongzhuan_readiness_audit.mjs` → `48 passed / 0 failed`。

## [2026-07-05] 运营入口总页增加实时状态看板
> 领域: `xianyu` | `backend` | `infra` | `docs`
> 影响模块: `XianyuAdmin`, `Ops Links`, `Readiness Audit`
> 关联问题: HI-907
### 变更内容
- `/ops-links` 从纯链接页升级为本机运营总控入口，打开后可输入本机 `OPENCLAW_API_TOKEN` 并只读查看上架前安全锁、自动发货、实单闭环和当前下一步。
- 页面会读取 `/api/status`、`/api/cc-loop-watch` 和 `/api/cc-public-sale-lock`，明确区分“生产内测可发货”和“正式售卖已放行”。
- 新入口不提供发货、分配卡密或 webhook 冒烟按钮，只读刷新状态；正式售卖仍必须通过真实闲鱼小额单兑换/API/调模型严格门。
### 文件变更
- `packages/clawbot/src/xianyu/xianyu_admin.py` — `/ops-links` 增加三张状态卡、Token 输入、本机 GUI 跳转和只读状态刷新。
- `packages/clawbot/tests/test_api_routes_regression.py` — 覆盖运营入口状态看板、API 调用脚本和正式售卖门槛提示。
- `docs/002-changelog.md` / `docs/007-operations.md` / `docs/009-health.md` / `/Users/blackdj/Documents/VPS-Config/docs/05-unified-execution-plan.md` — 同步老板收藏入口的新口径。
### 验证
- `cd packages/clawbot && .venv312/bin/python -m py_compile src/xianyu/xianyu_admin.py && .venv312/bin/python -m pytest tests/test_api_routes_regression.py tests/test_xianyu_cc_auto_ship.py -q` → `48 passed / 0 failed`。
- 重启 `ai.openclaw.xianyu` 后，`http://127.0.0.1:18800/ops-links` 包含“上架前安全锁 / 自动发货 / 实单闭环 / 当前你要做什么 / OPENCLAW_API_TOKEN”。
- 只读刷新 `/api/cc-public-sale-lock?refresh=true` 后返回 `state=internal_test_ready`、未售卡密 5、New-API 兑换码 5、渠道 3，正式售卖仍因真实小额单严格门未过而锁定。

## [2026-07-05] 后台自动刷新上架锁只读证据
> 领域: `xianyu` | `backend` | `infra` | `docs`
> 影响模块: `XianyuAdmin`, `Chrome Bookmarks`, `Readiness Audit`
> 关联问题: HI-907
### 变更内容
- 本机闲鱼助手启动时新增后台只读巡检线程，默认每 15 分钟自动刷新未售卡密库存、New-API 启用兑换码和启用渠道数量。
- `/api/status` 和“上架前安全锁”现在能看到 `cc_readiness_audit` / `auto_readiness_audit` 的自动刷新状态，减少人工点“刷新上架锁”的依赖。
- Chrome 入口脚本新增 `--visible-bookmark-folder` / `--visible-bookmark-group`，用于老板看不到书签栏文件夹时，直接通过 Chrome 自带“收藏所有标签页”流程创建可见的 `CC中转运营` 文件夹。
- 安全边界不变：后台只读巡检不调用 `--webhook-smoke`，不发送闲鱼消息，不分配卡密，不修改库存；正式售卖仍必须通过真实闲鱼小额单的兑换/API/调模型严格门。
### 文件变更
- `packages/clawbot/src/xianyu/xianyu_admin.py` — 新增后台只读巡检配置、节流、守护线程和状态字段。
- `packages/clawbot/config/.env.example` — 增加 `CC_XIANYU_AUTO_READINESS_AUDIT_*` 与严格门自动观察配置样例。
- `scripts/cc_zhongzhuan_chrome_bookmarks.mjs` — 增加可见书签文件夹创建参数。
- `docs/002-changelog.md` / `docs/006-registries.md` / `docs/007-operations.md` / `docs/009-health.md` / `/Users/blackdj/Documents/VPS-Config/docs/05-unified-execution-plan.md` — 同步生产内测运营口径。
### 验证
- `cd packages/clawbot && .venv312/bin/python -m py_compile src/xianyu/xianyu_admin.py && .venv312/bin/python -m pytest tests/test_api_routes_regression.py tests/test_xianyu_cc_auto_ship.py -q` → `48 passed / 0 failed`。
- 真实 Chrome 已用可见收藏流程创建 `CC中转运营` 书签栏文件夹，Default 资料读取到 7 个运营入口；`node scripts/cc_zhongzhuan_chrome_bookmarks.mjs --open-window --json` 返回 `ok=true`、`openedWindow.tabCount=7`。
- 重启 `ai.openclaw.xianyu` 后，`/api/status` 显示 `cc_readiness_audit.auto_enabled=true`、`auto_interval_ms=900000`、`auto_scan_seconds=60`，后台自动刷新后上架锁保持 `internal_test_ready`，正式售卖仍因真实小额单严格门未过而锁定。






## [2026-07-05] 闲鱼 GUI 增加上架前安全锁
> 领域: `xianyu` | `backend` | `docs`
> 影响模块: `XianyuAdmin`, `Xianyu GUI`, `Readiness Audit`
> 关联问题: HI-907
### 变更内容
- 本机闲鱼 GUI 新增“上架前安全锁”卡片和 `GET /api/cc-public-sale-lock`。
- 默认接口只读取本机缓存状态；点击“刷新上架锁（只读）”时才运行一次只读巡检，刷新库存、New-API 启用兑换码和渠道证据。
- 安全锁把状态明确分为 `locked`、`internal_test_ready`、`public_sale_unlocked`，防止把“生产内测可发货”误解为“正式售卖已放行”。
- 放行正式售卖必须同时满足：自动发货就绪、补救队列清零、未售卡密库存 > 0、New-API 启用兑换码 > 0、New-API 启用渠道 > 0、真实闲鱼小额单兑换/API/调模型严格门通过。
### 文件变更
- `packages/clawbot/src/xianyu/xianyu_admin.py` — 新增 `_cc_public_sale_lock_summary()`、`/api/cc-public-sale-lock` 和 GUI 上架锁渲染/刷新按钮。
- `packages/clawbot/tests/test_api_routes_regression.py` — 覆盖页面入口、接口状态、只读刷新和正式售卖锁定/放行判断。
- `docs/002-changelog.md` / `docs/006-registries.md` / `docs/007-operations.md` / `docs/009-health.md` — 同步操作口径。
### 验证
- `cd packages/clawbot && .venv312/bin/python -m py_compile src/xianyu/xianyu_admin.py && .venv312/bin/python -m pytest tests/test_api_routes_regression.py tests/test_xianyu_cc_auto_ship.py -q` → `46 passed / 0 failed`。
- 重启 `ai.openclaw.xianyu` 后，`/api/cc-public-sale-lock?refresh=true` 返回 `state=internal_test_ready`、`can_internal_test=true`、`can_public_sale=false`、库存 `unused_cards=5`、兑换码 `5`、渠道 `3`；唯一锁定原因是尚未通过真实闲鱼小额单严格门。

## [2026-07-05] Chrome 运营入口支持一键打开窗口
> 领域: `infra` | `xianyu` | `docs`
> 影响模块: `Chrome Bookmarks`, `Ops Links`, `Readiness Audit`
> 关联问题: HI-907
### 变更内容
- `scripts/cc_zhongzhuan_chrome_bookmarks.mjs` 新增 `--open-window` / `--open` 参数。
- 脚本仍会修复 4 个 Chrome Profile 的 `CC中转运营` 书签文件夹；额外参数会在当前 macOS Chrome 中直接打开一个包含 7 个运营入口的新窗口。
- 解决 Chrome 正在运行时书签文件已写入但当前 UI 未即时刷新的问题；老板找不到书签时可以直接运行一条命令打开运营窗口。
### 文件变更
- `scripts/cc_zhongzhuan_chrome_bookmarks.mjs` — 增加 macOS AppleScript 打开运营窗口逻辑，支持 JSON 输出 `openedWindow` 摘要。
- `docs/002-changelog.md` / `docs/006-registries.md` / `docs/007-operations.md` / `docs/009-health.md` — 同步 Chrome 入口操作口径。
### 验证
- `node --check scripts/cc_zhongzhuan_chrome_bookmarks.mjs` → exit 0。
- 临时 Chrome Profile dry-run：`--dry-run --open-window --json` 返回 `ok=true` 且跳过真实打开。
- 真实 Chrome：`node scripts/cc_zhongzhuan_chrome_bookmarks.mjs --open-window --json` 返回 `ok=true`、`openedWindow.tabCount=7`，4 个 Profile 均 `urlCount=7`、`bookmarkBarVisible=true`。

## [2026-07-05] 严格门审计结果落盘保存
> 领域: `xianyu` | `backend` | `docs`
> 影响模块: `XianyuContext`, `XianyuAdmin`, `Readiness Audit`
> 关联问题: HI-907
### 变更内容
- 本机闲鱼 SQLite 新增 `cc_strict_audits` 表，保存最近正式售卖严格门的脱敏摘要。
- `XianyuAdmin` 的严格门缓存现在支持从 SQLite 恢复；真实订单闭环一旦通过，闲鱼助手进程重启后仍可在 GUI/API 看到最近严格门证据。
- 持久化内容只包含 `ok/exit_code/real_orders/same_order_ready/same_order_matched/redeemed_delta/active_token_delta/model_log_delta/same_order_latest` 等摘要，不保存 stdout、stderr、完整订单号、卡密、Token 或 API Key。
- `/api/status` 增加 `cc_strict_audit`，`/api/cc-loop-watch` 的“最近严格门”展示会标记已落盘。
### 文件变更
- `packages/clawbot/src/xianyu/xianyu_context.py` — 新增严格门审计表和 `record_cc_strict_audit()` / `latest_cc_strict_audit()`。
- `packages/clawbot/src/xianyu/xianyu_admin.py` — 严格门结果写入 SQLite、从 SQLite 恢复，并在状态接口/GUI 展示。
- `packages/clawbot/tests/test_xianyu_cc_auto_ship.py` / `packages/clawbot/tests/test_api_routes_regression.py` — 覆盖严格门摘要落盘、不保存原始输出、重启后恢复判断。
- `docs/002-changelog.md` / `docs/006-registries.md` / `docs/007-operations.md` / `docs/009-health.md` / `/Users/blackdj/Documents/VPS-Config/docs/05-unified-execution-plan.md` — 同步闭环证据持久化口径。
### 验证
- `cd packages/clawbot && .venv312/bin/python -m py_compile src/xianyu/xianyu_admin.py src/xianyu/xianyu_context.py && .venv312/bin/python -m pytest tests/test_xianyu_cc_auto_ship.py tests/test_api_routes_regression.py -q` → `45 passed / 0 failed`。
- 重启 `ai.openclaw.xianyu` 后，`/api/cc-loop-watch` 返回 `stage=waiting_paid_order`、`can_auto_ship_paid_orders=true`、`background_strict_audit_enabled=true`、`pending_rescue=0`，当前 `last_strict_audit={}` 符合尚无真实订单现状。
- `node scripts/cc_zhongzhuan_readiness_audit.mjs --json` → `ok=true`；`--require-real-order` → `ok=false`、`realOrders=0`、`sameOrderReady=0`，继续作为正式售卖前真实小额订单门禁。

## [2026-07-05] 后台自动严格门观察接管 GUI 轮询
> 领域: `xianyu` | `backend` | `docs`
> 影响模块: `XianyuAdmin`, `Readiness Audit`, `Xianyu GUI`
> 关联问题: HI-907
### 变更内容
- 本机闲鱼助手启动时新增后台守护线程：即使浏览器没有打开 GUI，也会定时观察实单闭环阶段。
- 只有在真实闲鱼订单已自动发货、无补救队列、WebSocket/Cookie/webhook 均可用且阶段为 `waiting_buyer_chain` 时，才按 `CC_XIANYU_AUTO_STRICT_AUDIT_INTERVAL_MS` 节流运行正式售卖严格门只读审计。
- 后台严格门不调用 `--webhook-smoke`，不会发送闲鱼消息、不会分配卡密、不会改库存；只是刷新“同一真实订单是否已完成兑换/API Key/调模型”的证据。
- `/api/cc-loop-watch` 增加后台观察状态字段，GUI 仍保留页面打开时的辅助自动观察。
### 文件变更
- `packages/clawbot/src/xianyu/xianyu_admin.py` — 新增 `_auto_strict_audit_config()`、后台严格门判断/单次执行/守护线程，并在 `start_admin_server()` 启动。
- `packages/clawbot/tests/test_api_routes_regression.py` — 覆盖后台严格门触发条件、节流和单次执行。
- `packages/clawbot/tests/test_xianyu_cc_auto_ship.py` — 清理新增环境变量，避免测试串扰。
- `docs/002-changelog.md` / `docs/006-registries.md` / `docs/007-operations.md` / `docs/009-health.md` / `/Users/blackdj/Documents/VPS-Config/docs/05-unified-execution-plan.md` — 同步全自动运营口径。
### 验证
- `cd packages/clawbot && .venv312/bin/python -m py_compile src/xianyu/xianyu_admin.py && .venv312/bin/python -m pytest tests/test_xianyu_cc_auto_ship.py tests/test_api_routes_regression.py -q` → `44 passed / 0 failed`。
- 重启 `ai.openclaw.xianyu` 后，带 token 查询 `/api/cc-loop-watch` 返回 `stage=waiting_paid_order`、`can_auto_ship_paid_orders=true`、`background_strict_audit_enabled=true`、`background_strict_audit_scan_seconds=60`、`pending_rescue=0`。
- `node scripts/cc_zhongzhuan_readiness_audit.mjs --json` → `ok=true`，Chrome / 本机闲鱼 / GUI / Oracle 均通过，库存 `unused=5`、New-API 启用兑换码 `5`、渠道 `3`；`--require-real-order` 仍按预期失败，因真实闲鱼实单数为 `0`。

## [2026-07-05] GUI 在真实发货后自动轮询正式售卖严格门
> 领域: `xianyu` | `backend` | `docs`
> 影响模块: `XianyuAdmin`, `Xianyu GUI`, `Readiness Audit`
> 关联问题: HI-907
### 变更内容
- 本机闲鱼助手 GUI 新增自动严格门观察：当“实单闭环观察”进入 `waiting_buyer_chain`（已自动发货，等待买家完成兑换/API/调模型）时，页面会按 10 分钟节流自动运行一次“正式售卖严格门”只读审计。
- 自动观察只调用现有 `GET /api/cc-readiness-audit?mode=strict`，不会触发 `--webhook-smoke`，不会发送闲鱼消息，不会分配卡密，不会修改库存。
- 无真实订单时不自动跑严格门；当前 live 状态仍为 `waiting_paid_order`。
### 文件变更
- `packages/clawbot/src/xianyu/xianyu_admin.py` — 新增前端 `maybeAutoRunStrictAudit()`、自动严格门节流和 `CC_XIANYU_AUTO_STRICT_AUDIT_*` 只读配置。
- `packages/clawbot/tests/test_api_routes_regression.py` — 覆盖自动观察静态逻辑和接口返回的开关/节流参数。
- `docs/002-changelog.md` / `docs/006-registries.md` / `docs/007-operations.md` / `docs/009-health.md` / `/Users/blackdj/Documents/VPS-Config/docs/05-unified-execution-plan.md` — 同步运营口径。
### 验证
- `cd packages/clawbot && .venv312/bin/python -m py_compile src/xianyu/xianyu_admin.py && .venv312/bin/python -m pytest tests/test_xianyu_cc_auto_ship.py tests/test_api_routes_regression.py -q` → `42 passed / 0 failed`。
- 本机 `ai.openclaw.xianyu` 重启后，GUI 首页包含 `maybeAutoRunStrictAudit`、`ccLastAutoStrictAuditAt` 和“自动运行正式售卖严格门”。
- `/api/cc-loop-watch` 返回 `stage=waiting_paid_order`、`auto_strict_audit_enabled=true`、`auto_strict_audit_interval_ms=600000`、`ready_for_public_sale=false`。

## [2026-07-05] 闲鱼 GUI 增加实单闭环观察并收紧正式可售判断
> 领域: `xianyu` | `backend` | `docs`
> 影响模块: `XianyuAdmin`, `Xianyu GUI`, `Readiness Audit`
> 关联问题: HI-907
### 变更内容
- 本机闲鱼助手 GUI 新增“实单闭环观察”卡片和 `GET /api/cc-loop-watch`，轻量展示自动发货当前卡在 webhook、WebSocket、Cookie、补救队列、等待真实付款、等待买家兑换/API/调模型或已闭环哪一步。
- 修复 GUI 前端 Promise 解包漏接 `/api/items` 的问题，“最近捕获到的闲鱼商品”现在会真正拿到缓存商品数据。
- 收紧 `ready_for_public_sale` 判断：不再因为本机出现 `xy_* / message_sent` 就显示正式可售；只有最近一次“正式售卖严格门”通过且同一真实订单完成买家兑换、API Key、模型调用后才会转绿。
### 文件变更
- `packages/clawbot/src/xianyu/xianyu_admin.py` — 新增严格审计结果缓存、`/api/cc-loop-watch`、GUI 实单闭环观察卡片，并修复 `/api/items` 前端解包。
- `packages/clawbot/tests/test_api_routes_regression.py` — 覆盖新卡片、新接口和“本机已发货但买家闭环未通过时仍不可正式售卖”的安全判断。
- `docs/002-changelog.md` / `docs/006-registries.md` / `docs/007-operations.md` / `docs/009-health.md` / `/Users/blackdj/Documents/VPS-Config/docs/05-unified-execution-plan.md` — 同步当前运营口径。
### 验证
- `cd packages/clawbot && .venv312/bin/python -m py_compile src/xianyu/xianyu_admin.py && .venv312/bin/python -m pytest tests/test_xianyu_cc_auto_ship.py tests/test_api_routes_regression.py -q` → `42 passed / 0 failed`。
- 本机 `ai.openclaw.xianyu` 重启后，GUI 首页包含“实单闭环观察 / renderLoopWatch / /api/cc-loop-watch / 最近捕获到的闲鱼商品”。
- 带 token 调用 `/api/cc-loop-watch` 返回 `stage=waiting_paid_order`、`can_auto_ship_paid_orders=true`、`ready_for_public_sale=false`、`pending_rescue=0`。
- `node scripts/cc_zhongzhuan_readiness_audit.mjs` → `PASS`；`--require-real-order` 仍按预期 `FAIL`，原因是尚未发生真实闲鱼小额付款订单。

## [2026-07-05] 闲鱼 GUI 补齐捕获商品映射与 Chrome 运营入口总页
> 领域: `xianyu` | `infra` | `docs`
> 影响模块: `XianyuAdmin`, `Chrome Bookmarks`, `Readiness Audit`
> 关联问题: HI-907
### 变更内容
- 本机闲鱼助手 GUI 的“闲鱼商品套餐映射”新增“最近捕获到的闲鱼商品”列表，读取 `/api/items` 缓存商品，点击“填入映射”即可把 `item_id`、标题和价格带入映射表单/商品模板，减少手动查商品 ID。
- 新增本机运营入口总页 `http://127.0.0.1:18800/ops-links`，集中放用户主站、New-API 后台、Frist 运营台、本机闲鱼 GUI、模型检查和 API 网关 Base URL。
- Chrome 书签修复脚本把 `CC中转运营` 文件夹升级为 7 个入口，并清理废弃 `file://cc_zhongzhuan_ops_links.html` 链接；真实 Chrome 标签组已打开 `CC中转运营入口` 总页。
### 文件变更
- `packages/clawbot/src/xianyu/xianyu_admin.py` — 新增 `/ops-links` 页面、最近捕获商品渲染和 `fillMappingFromItem()`。
- `packages/clawbot/tests/test_api_routes_regression.py` / `packages/clawbot/tests/test_xianyu_cc_auto_ship.py` — 覆盖 `/ops-links`、`/api/items` 和 GUI 映射入口。
- `scripts/cc_zhongzhuan_chrome_bookmarks.mjs` / `scripts/cc_zhongzhuan_readiness_audit.mjs` — Chrome 入口清单升级为 7 项。
- `docs/002-changelog.md` / `docs/006-registries.md` / `docs/007-operations.md` / `docs/009-health.md` / `/Users/blackdj/Documents/VPS-Config/docs/05-unified-execution-plan.md` — 同步运营口径。
### 验证
- `cd packages/clawbot && .venv312/bin/python -m py_compile src/xianyu/xianyu_admin.py && .venv312/bin/python -m pytest tests/test_xianyu_cc_auto_ship.py tests/test_api_routes_regression.py -q` → `42 passed / 0 failed`。
- `node --check scripts/cc_zhongzhuan_chrome_bookmarks.mjs && node --check scripts/cc_zhongzhuan_readiness_audit.mjs && node scripts/cc_zhongzhuan_chrome_bookmarks.mjs --json` → 4 个 Chrome Profile 均 `urlCount=7`、`bookmarkBarVisible=true`。
- 本机 `ai.openclaw.xianyu` 重启后，`/ops-links` 包含 6 个运营入口，GUI 首页包含“最近捕获到的闲鱼商品 / 填入映射 / /api/items”。
- `node scripts/cc_zhongzhuan_readiness_audit.mjs` → `PASS`；`--require-real-order` 仍按预期失败，原因是尚未发生真实闲鱼小额付款订单。

## [2026-07-05] GUI 审计卡片显示同单买家闭环明细
> 领域: `xianyu` | `backend` | `docs`
> 影响模块: `XianyuAdmin`, `Readiness Audit`
> 关联问题: HI-907
### 变更内容
- 本机闲鱼助手“一键闭环审计”卡片新增同一真实订单分阶段明细渲染：订单前缀、履约状态、卡密状态、New-API 兑换、API Key 数量、兑换后模型调用数和最终结论。
- `_summarize_cc_readiness_payload()` 保留 `real_order_chain_proof.latestMatches` 的前 5 条，GUI 可直接展示真实订单卡在“已发货 / 已兑换 / API Key / 调模型”哪一步。
- 当前无真实订单时，GUI 明确显示“暂无同一真实订单明细”，避免把严格门失败误解成系统故障。
### 文件变更
- `packages/clawbot/src/xianyu/xianyu_admin.py` — 新增 `same_order_latest` 摘要和 `renderOrderChainMatches()` 前端渲染。
- `packages/clawbot/tests/test_api_routes_regression.py` — 覆盖页面函数和同单明细摘要字段。
- `docs/002-changelog.md` / `docs/007-operations.md` / `docs/009-health.md` — 同步 GUI 验收说明。
### 验证
- `cd packages/clawbot && .venv312/bin/python -m pytest tests/test_api_routes_regression.py::test_xianyu_admin_page_escapes_dynamic_fields tests/test_api_routes_regression.py::test_xianyu_admin_runs_readonly_cc_readiness_audit -q` → `2 passed / 0 failed`。
- `cd packages/clawbot && .venv312/bin/python -m py_compile src/xianyu/xianyu_admin.py && .venv312/bin/python -m pytest tests/test_xianyu_cc_auto_ship.py tests/test_api_routes_regression.py -q` → `42 passed / 0 failed`。
- `node scripts/cc_zhongzhuan_readiness_audit.mjs` → `PASS`；当前 `latestMatches=[]`、`readyOrders=0`，符合“尚无真实小额订单”的现状。
- 本机 `ai.openclaw.xianyu` 重启后，GUI 首页 HTTP 200，页面包含 `renderOrderChainMatches` 和“分阶段状态”提示；`/api/cc-readiness-audit?mode=read_only` 返回 `ok=true`、`same_order_latest=[]`。

## [2026-07-05] CC中转 Chrome 书签文件夹可重复修复脚本
> 领域: `infra` | `xianyu` | `docs`
> 影响模块: `Chrome Bookmarks`, `Readiness Audit`
> 关联问题: HI-907
### 变更内容
- 新增 `scripts/cc_zhongzhuan_chrome_bookmarks.mjs`，可重复修复/重建 Chrome 里的「CC中转运营」书签文件夹。
- 脚本会遍历本机 Chrome Profile，把 6 个运营入口写入书签栏并开启书签栏显示；写入前在原 Chrome Profile 目录生成 `.codex-backup-*` 备份。
- 支持 `CHROME_USER_DATA_DIR` / `CC_CHROME_USER_DATA_DIR` 指向临时目录做测试，也支持 `--dry-run` 和 `--json`。
### 文件变更
- `scripts/cc_zhongzhuan_chrome_bookmarks.mjs` — 新增 Chrome 书签修复脚本。
- `docs/002-changelog.md` / `docs/006-registries.md` / `docs/007-operations.md` / `docs/009-health.md` / `/Users/blackdj/Documents/VPS-Config/docs/05-unified-execution-plan.md` — 同步操作说明。
### 验证
- 临时 Chrome Profile 冒烟：脚本成功重建 `CC中转运营` 文件夹、保留旧入口、打开书签栏并生成备份。
- 真实 Chrome Profile 修复：`Default`、`Profile 1`、`Profile 2`、`Profile 3` 均返回 `ok=true`、`urlCount=7`、`bookmarkBarVisible=true`。
- `node scripts/cc_zhongzhuan_chrome_bookmarks.mjs --json && node scripts/cc_zhongzhuan_readiness_audit.mjs` → 书签修复成功，闭环审计 `PASS`。
- `node --check scripts/cc_zhongzhuan_chrome_bookmarks.mjs && git diff --check` → exit 0。

## [2026-07-05] 闲鱼助手增加自动化运营水位和商品模板
> 领域: `xianyu` | `backend` | `docs`
> 影响模块: `XianyuAdmin`, `Xianyu GUI`
> 关联问题: HI-907
### 变更内容
- 本机闲鱼助手 GUI 新增“自动化运营水位”卡片，直接展示 CC中转自动发货是否可用、正式售卖是否仍缺真实小额单验收、webhook/ws/cookie/补救队列/商品映射状态，以及老板仍需介入的事项。
- 新增 `GET /api/cc-sale-readiness`，供 GUI 汇总自动化运营水位；不输出 token、卡密或 API Key。
- 新增“闲鱼商品模板”卡片和 `GET /api/cc-product-template`，生成只含履约说明的极简商品模板：付款后自动发送兑换入口和一次性兑换码、注册/登录、兑换到账、创建 API Key、CC Switch 导入和模型测试；不写额外营销话术，不暴露 `/v1` 网关。
### 文件变更
- `packages/clawbot/src/xianyu/xianyu_admin.py` — 新增自动化水位 API、商品模板 API 和 GUI 卡片。
- `packages/clawbot/tests/test_api_routes_regression.py` — 覆盖 GUI 文案、自动化水位 API 和商品模板内容边界。
- `docs/002-changelog.md` / `docs/006-registries.md` / `docs/007-operations.md` / `docs/009-health.md` / `/Users/blackdj/Documents/VPS-Config/docs/05-unified-execution-plan.md` — 同步操作入口。
### 验证
- `cd packages/clawbot && .venv312/bin/python -m pytest tests/test_api_routes_regression.py::test_xianyu_admin_page_escapes_dynamic_fields tests/test_api_routes_regression.py::test_xianyu_admin_sale_readiness_and_product_template tests/test_xianyu_cc_auto_ship.py -q` → `18 passed / 0 failed`。
- `cd packages/clawbot && .venv312/bin/python -m py_compile src/xianyu/xianyu_admin.py src/xianyu/xianyu_context.py src/xianyu/xianyu_live.py && .venv312/bin/python -m pytest tests/test_xianyu_cc_auto_ship.py tests/test_api_routes_regression.py -q` → `42 passed / 0 failed`。
- 本机 `ai.openclaw.xianyu` 重启后，GUI 首页 HTTP 200 且包含“自动化运营水位 / 闲鱼商品模板”；带 token 调用 `/api/cc-sale-readiness` 返回 `can_auto_ship_paid_orders=true`、`ready_for_public_sale=false`、`pending_rescue=0`；模板接口包含注册/登录和 CC Switch 步骤，且不包含 `/v1`。
- `node scripts/cc_zhongzhuan_readiness_audit.mjs && git diff --check` → `PASS` / exit 0。

## [2026-07-05] 闲鱼自动发货增加商品套餐映射
> 领域: `xianyu` | `backend` | `docs`
> 影响模块: `XianyuLive`, `XianyuAdmin`, `XianyuContext`
> 关联问题: HI-907
### 变更内容
- 本机闲鱼助手新增“闲鱼商品套餐映射”：可在 GUI 里配置 `item_id → planId`，多商品/多套餐上架后优先按商品映射发对应兑换码，避免只走默认套餐导致错发。
- `XianyuLive` 调用 CC中转低权限 webhook 时，会优先读取已启用映射；没有映射时继续回退 `CC_XIANYU_DEFAULT_PLAN_ID` 或无套餐任意未售卡密。
- CC中转自动发货接管时，不再同时发送旧 OpenClaw 部署包 License 话术，避免买家收到两套无关发货内容。
- 本机 GUI 新增映射表单、列表和删除按钮；`/api/status` 增加映射数量摘要。
### 文件变更
- `packages/clawbot/src/xianyu/xianyu_context.py` — 新增 `cc_item_mappings` 表和增删查改方法。
- `packages/clawbot/src/xianyu/xianyu_live.py` — 自动发货 payload 增加商品映射 planId 解析，并在 CC中转接管时关闭旧 License 话术。
- `packages/clawbot/src/xianyu/xianyu_admin.py` — 新增 `/api/cc-item-mappings` API、GUI 表单和状态摘要。
- `packages/clawbot/tests/test_xianyu_cc_auto_ship.py` — 覆盖映射优先级、SQLite CRUD 和 GUI API。
- `docs/002-changelog.md` / `docs/006-registries.md` / `docs/007-operations.md` / `docs/009-health.md` / `/Users/blackdj/Documents/VPS-Config/docs/05-unified-execution-plan.md` — 同步自动发货运营说明。
### 验证
- `cd packages/clawbot && .venv312/bin/python -m pytest tests/test_xianyu_cc_auto_ship.py tests/test_api_routes_regression.py -q` → `41 passed / 0 failed`。
- `cd packages/clawbot && .venv312/bin/python -m py_compile src/xianyu/xianyu_context.py src/xianyu/xianyu_live.py src/xianyu/xianyu_admin.py` → exit 0。
- `node scripts/cc_zhongzhuan_readiness_audit.mjs` → `PASS`，本机 GUI 显示 `ws=true`、`cookie=true`、`autoShip=true`、`pendingRescue=0`。
- 本机 `http://127.0.0.1:18800/` 重启后首页包含“闲鱼商品套餐映射”，真实 API 冒烟完成“新增映射 → 查询 → 删除”，测试映射已清理。
- `make test` → exit 0（全量 pytest 进度到 `[100%]`，仅保留既有 `js2py` deprecation warning）。
- `cd apps/frist-api && node --test tests/*.test.mjs` → `182 passed / 0 failed`。

## [2026-07-05] 闲鱼助手 GUI 增加一键闭环审计按钮
> 领域: `xianyu` | `infra` | `docs`
> 影响模块: `XianyuAdmin`, `Readiness Audit`
> 关联问题: HI-907
### 变更内容
- 本机闲鱼助手 GUI 新增“一键闭环审计”卡片，提供“运行内测巡检”和“运行正式售卖严格门”两个按钮，老板不需要手敲 CLI 命令也能看到生产闭环状态。
- 新增 `GET /api/cc-readiness-audit?mode=read_only|strict`，只允许只读巡检和严格验收，不提供 `--webhook-smoke` 写入冒烟按钮，避免误点造成生产写操作。
- GUI 摘要展示 Chrome 入口、本机闲鱼、GUI、Oracle、库存、New-API 兑换码/渠道、补救队列、真实订单、同单闭环和买家站内增量。
### 文件变更
- `packages/clawbot/src/xianyu/xianyu_admin.py` — 新增审计 API、页面按钮和审计摘要渲染。
- `packages/clawbot/tests/test_api_routes_regression.py` — 覆盖页面按钮、只读审计 API 和严格模式参数，断言不会调用 `--webhook-smoke`。
- `docs/002-changelog.md` / `docs/006-registries.md` / `docs/007-operations.md` / `docs/009-health.md` / `/Users/blackdj/Documents/VPS-Config/docs/05-unified-execution-plan.md` — 同步 GUI 操作入口。
### 验证
- `cd packages/clawbot && .venv312/bin/python -m pytest tests/test_api_routes_regression.py::test_xianyu_admin_page_escapes_dynamic_fields tests/test_api_routes_regression.py::test_xianyu_admin_runs_readonly_cc_readiness_audit -q` → `2 passed / 0 failed`。
- `cd packages/clawbot && .venv312/bin/python -m pytest tests/test_xianyu_cc_auto_ship.py tests/test_api_routes_regression.py -q` → `38 passed / 0 failed`。
- 本机 `ai.openclaw.xianyu` 重启后，`/api/status` 返回 `ws=true`、`cookie=true`、`cc=true`。
- `GET http://127.0.0.1:18800/api/cc-readiness-audit?mode=read_only` → `ok=true`、`exit=0`。
- `GET http://127.0.0.1:18800/api/cc-readiness-audit?mode=strict` → `ok=false`、`exit=1`，原因仍是尚无真实小额闲鱼订单，属于预期售卖前门禁。

## [2026-07-05] CC中转补齐 New-API 原生兑换回写与同单严格验收
> 领域: `backend` | `xianyu` | `infra` | `deploy` | `docs`
> 影响模块: `Frist-API`, `Readiness Audit`, `XianyuAdmin`
> 关联问题: HI-907
### 变更内容
- Frist-API 新增 New-API 原生兑换状态回写器：服务启动后默认每 60 秒读取 New-API SQLite `redemptions`，用卡密哈希匹配 Frist 兑换卡，自动把已发出的闲鱼卡密和履约记录从 `sold/delivered` 回写为 `redeemed`。
- 新增后台手动同步接口 `/api/admin/redemption-cards/sync-newapi-status`，便于运营台立即刷新兑换状态；同步过程不打印、不落库完整卡密，只保存哈希、预览和 New-API 用户 ID 摘要。
- 一键审计严格模式升级为“同一真实订单闭环证明”：本机闲鱼助手只提供 `xy_*` 真实订单哈希，Oracle 端用该哈希匹配同一笔履约，再要求对应卡密已兑换、买家有启用 API Key 且兑换后有模型调用日志。
- 本机闲鱼 GUI 的正式售卖验收门同步增加 `same_xy_order_redeemed` 要求，避免把 webhook 冒烟或无关模型日志误判成正式可售。
- 已部署到 Oracle `/opt/frist-api/apps/frist-api/server/server.js`，并在 `/etc/frist-api/frist-api.env` 打开 `FRIST_API_NEWAPI_REDEMPTION_STATUS_SYNC_ENABLED=1`。
### 文件变更
- `apps/frist-api/server/server.js` — 新增 New-API 兑换状态同步器、后台手动同步接口和定时任务。
- `apps/frist-api/tests/server.test.mjs` — 新增“New-API 原生兑换后回写 Frist 闲鱼履约”的回归测试。
- `apps/frist-api/deploy/production.env.example` — 增加兑换状态同步开关和间隔示例。
- `scripts/cc_zhongzhuan_readiness_audit.mjs` — 严格门增加同一 `xy_*` 订单哈希关联证明。
- `packages/clawbot/src/xianyu/xianyu_context.py` — GUI 正式售卖验收门增加同单兑换要求。
- `docs/002-changelog.md` / `docs/006-registries.md` / `docs/007-operations.md` / `docs/009-health.md` / `/Users/blackdj/Documents/VPS-Config/docs/05-unified-execution-plan.md` — 同步生产闭环和验收口径。
### 验证
- `node --test --test-name-pattern="New-API native redemption status|New-API topup succeeds|newly generated CC cards" apps/frist-api/tests/server.test.mjs` → `3 pass / 0 fail`。
- `cd apps/frist-api && node --test tests/*.test.mjs` → `182 passed / 0 failed`。
- `cd packages/clawbot && .venv312/bin/python -m pytest tests/test_xianyu_cc_auto_ship.py tests/test_api_routes_regression.py -q` → `37 passed / 0 failed`。
- Oracle 部署后 `systemctl restart frist-api.service && systemctl is-active frist-api.service` → `active`。
- `node scripts/cc_zhongzhuan_readiness_audit.mjs` → `PASS`；默认模式显示 `同一真实订单闭环证明: localOrderHashes=0, matchedOrders=0, readyOrders=0（默认不强制）`。
- `node scripts/cc_zhongzhuan_readiness_audit.mjs --webhook-smoke` → `PASS`，`fulfillment=delivered`、`cleanup=true`、`unused_after=5`。
- `node scripts/cc_zhongzhuan_readiness_audit.mjs --require-real-order` → 预期 `FAIL` 且退出码 `1`，因为当前尚未发布闲鱼商品并跑真实小额订单。

## [2026-07-05] 闲鱼发货话术补齐买家自助使用步骤
> 领域: `backend` | `xianyu` | `docs`
> 影响模块: `Frist-API`, `Xianyu Fulfillment`
> 关联问题: HI-907
### 变更内容
- 闲鱼自动发货话术从“兑换入口 + 卡密”补齐为完整买家自助路径：注册/登录、进入兑换码到账、进入 API Key 创建 Key、进入 CC Switch 导入并选择模型测试。
- 话术仍保持操作说明口径，不新增营销文案，不暴露上游信息，也不把 `/v1` 网关直接写进闲鱼消息。
- 已将单文件部署到 Oracle `/opt/frist-api/apps/frist-api/server/server.js`，重启 `frist-api.service` 生效。
### 文件变更
- `apps/frist-api/server/server.js` — `buildXianyuDeliveryMessage()` 增加买家自助步骤。
- `apps/frist-api/tests/server.test.mjs` — 覆盖发货话术包含注册/登录、兑换码、API Key、CC Switch 和模型测试，并继续断言不出现 `jiyu.245334.xyz/v1`。
- `docs/002-changelog.md` / `docs/007-operations.md` / `docs/009-health.md` — 同步话术变更和生产验证。
### 验证
- `node --check apps/frist-api/server/server.js` → exit 0。
- `cd apps/frist-api && node --test --test-name-pattern 'marks local CC card and Xianyu fulfillment redeemed|allocates a redemption card for a Xianyu order|low-scope auto-ship webhook' tests/server.test.mjs` → `3 pass / 0 fail`。
- Oracle 单文件部署后：`node --check /opt/frist-api/apps/frist-api/server/server.js && systemctl restart frist-api.service` → `active`。
- `node scripts/cc_zhongzhuan_readiness_audit.mjs --webhook-smoke` → `PASS`，`fulfillment=delivered`、`cleanup=true`、`unused_after=5`。
- 生产内网 webhook 话术检查 → `has_register=true`、`has_redeem=true`、`has_api_key=true`、`has_cc_switch=true`、`has_model_test=true`、`leaks_v1=false`、`cleanup=true`、`unused_after=5`。

## [2026-07-05] 闲鱼助手 GUI 增加正式售卖验收门
> 领域: `xianyu` | `backend` | `docs`
> 影响模块: `XianyuAdmin`, `XianyuContext`, `Readiness Audit`
> 关联问题: HI-907
### 变更内容
- 本机闲鱼助手首页新增“正式售卖验收门”卡片，直接展示真实闲鱼发货是否已发生、真实订单数、补救待处理数，以及正式开卖前要跑的严格命令。
- `XianyuContextManager` 新增 `cc_final_sale_gate_summary()`，从本机 SQLite 汇总 `xy_* / message_sent` 真实发货记录，不显示完整卡密或买家信息。
- `/api/status` 新增 `cc_final_sale_gate`，GUI 可直接看到“真实实单 + 买家兑换/API/调模型”验收仍未完成，不再需要老板记 CLI 命令。
### 文件变更
- `packages/clawbot/src/xianyu/xianyu_context.py` — 新增正式售卖本地实单门汇总。
- `packages/clawbot/src/xianyu/xianyu_admin.py` — `/api/status` 返回 `cc_final_sale_gate`，首页新增“正式售卖验收门”卡片。
- `packages/clawbot/tests/test_xianyu_cc_auto_ship.py` / `packages/clawbot/tests/test_api_routes_regression.py` — 覆盖 GUI 文案、API 字段和本地实单门状态。
- `docs/002-changelog.md` / `docs/007-operations.md` / `docs/009-health.md` — 同步 GUI 入口和验证结果。
### 验证
- `packages/clawbot/.venv312/bin/python -m py_compile packages/clawbot/src/xianyu/xianyu_admin.py packages/clawbot/src/xianyu/xianyu_context.py` → exit 0。
- `cd packages/clawbot && .venv312/bin/python -m pytest tests/test_xianyu_cc_auto_ship.py tests/test_api_routes_regression.py -q` → `37 passed / 0 failed`。
- 本机 `ai.openclaw.xianyu` 重启后，`http://127.0.0.1:18800/` 首页包含 `正式售卖验收门`、严格命令和买家站内闭环说明。
- `node scripts/cc_zhongzhuan_readiness_audit.mjs` 与 `--webhook-smoke` 均 `PASS`；`--require-real-order` 按预期 `FAIL`，因为尚未有真实闲鱼小额订单。

## [2026-07-05] CC中转正式售卖前真实闲鱼实单与买家闭环验收门
> 领域: `xianyu` | `infra` | `docs`
> 影响模块: `Readiness Audit`, `Xianyu Auto Fulfillment`
> 关联问题: HI-907
### 变更内容
- `scripts/cc_zhongzhuan_readiness_audit.mjs` 新增 `--require-real-order` 严格模式：默认只读审计仍用于生产内测日常巡检；正式开卖前可强制要求本机 `cc_shipments` 出现真实闲鱼助手产生的 `xy_* / message_sent` 自动发货记录。
- 严格模式同时要求生产 New-API 买家站内链路超过当前验收基线：已兑换兑换码数、活跃 API Key 数和模型调用日志数都必须增长，避免只证明“已发货”但没证明“买家能兑换、创建 Key 并调模型”。
- 严格模式不会把生产 webhook 冒烟当成真实实单证明；当前没有真实订单时会明确失败并提示“发布闲鱼商品后跑 1 单小额实单再复验”。
- CLI 输出新增“真实闲鱼实单证明”和“买家站内闭环证明”摘要，显示是否发现真实发货、`sentRealOrders`、`pendingRescue`、兑换增量、Key 增量和模型日志增量，避免把系统内自测误判成外部平台已验证。
### 文件变更
- `scripts/cc_zhongzhuan_readiness_audit.mjs` — 新增 `--require-real-order`、本机 SQLite `cc_shipments` 真实订单检查、生产 New-API 买家站内闭环基线增量检查和输出摘要。
- `docs/002-changelog.md` / `docs/007-operations.md` / `docs/009-health.md` / `/Users/blackdj/Documents/VPS-Config/docs/05-unified-execution-plan.md` — 同步正式售卖前实单验收命令。
### 验证
- `node --check scripts/cc_zhongzhuan_readiness_audit.mjs && node scripts/cc_zhongzhuan_readiness_audit.mjs` → `PASS`，默认模式显示 `真实闲鱼实单证明: 未发现（默认不强制）`，买家站内闭环增量为 `0/0/0`。
- `node scripts/cc_zhongzhuan_readiness_audit.mjs --webhook-smoke && git diff --check` → `PASS`，webhook 冒烟仍不满足严格实单门。
- `node scripts/cc_zhongzhuan_readiness_audit.mjs --require-real-order` → 预期 `FAIL` 且退出码 `1`，失败原因是当前尚未发布闲鱼商品并完成真实小额付款/买家站内兑换/API/调模型。

## [2026-07-05] CC中转闲鱼失败发货自动补发
> 领域: `xianyu` | `backend` | `docs`
> 影响模块: `XianyuLive`, `XianyuAdmin`, `XianyuContext`, `Readiness Audit`
> 关联问题: HI-907
### 变更内容
- 本机闲鱼助手新增失败发货自动补发循环：默认每 60 秒扫描 `message_send_failed` 队列，只有在卡密已分配且本机保存了完整发货话术时才重发同一条消息，不重新分配卡密、不处理未付款订单。
- 新增 `POST /api/cc-shipments/{id}/resend`，本机 GUI 的补救队列表格增加“重试发送”按钮；按钮会复用已分配发货话术，成功后把记录改回 `message_sent`。
- `XianyuContextManager` 新增 `get_cc_shipment()`，支持按 ID 安全读取单条发货记录；默认不返回完整话术，只有补发路径显式要求时才读取。
- 一键审计脚本的 Chrome 书签校验改为按 URL 校验，并把 `http://127.0.0.1:18800/` 本机闲鱼助手 GUI 加入 `CC中转运营` 入口清单。
### 文件变更
- `packages/clawbot/src/xianyu/xianyu_live.py` — 新增 `resend_cc_shipment()` 和 `_cc_shipment_rescue_loop()`，并接入主 WebSocket 生命周期。
- `packages/clawbot/src/xianyu/xianyu_admin.py` — 新增补发 API 和 GUI“重试发送”按钮。
- `packages/clawbot/src/xianyu/xianyu_context.py` — 新增单条发货记录读取方法。
- `packages/clawbot/config/.env.example` / `docs/006-registries.md` — 新增自动补发循环配置项。
- `packages/clawbot/tests/test_xianyu_cc_auto_ship.py` / `packages/clawbot/tests/test_api_routes_regression.py` — 覆盖补发成功、无话术拒绝补发和管理 API。
- `scripts/cc_zhongzhuan_readiness_audit.mjs` — 运营入口清单加入本机闲鱼 GUI，并按 URL 校验 Chrome 书签。
### 验证
- `packages/clawbot/.venv312/bin/python -m py_compile packages/clawbot/src/xianyu/xianyu_context.py packages/clawbot/src/xianyu/xianyu_live.py packages/clawbot/src/xianyu/xianyu_admin.py` → exit 0。
- `cd packages/clawbot && .venv312/bin/python -m pytest tests/test_xianyu_cc_auto_ship.py tests/test_api_routes_regression.py -q` → `37 passed / 0 failed`。
- `node --check scripts/cc_zhongzhuan_readiness_audit.mjs && node scripts/cc_zhongzhuan_readiness_audit.mjs` → `PASS`，Chrome 书签、本机闲鱼、本机 GUI、Oracle 均通过；当前补救待处理为 `0`。

## [2026-07-05] CC中转一键审计纳入闲鱼 GUI 状态
> 领域: `infra` | `xianyu` | `docs`
> 影响模块: `Readiness Audit`, `XianyuAdmin`, `Auto Fulfillment`
> 关联问题: HI-907
### 变更内容
- `scripts/cc_zhongzhuan_readiness_audit.mjs` 新增 `localXianyuGui` 检查：读取本机 `OPENCLAW_API_TOKEN` 后访问 `127.0.0.1:18800`，验证 GUI 首页可打开、API 无 token 返回 401、带 token 返回 200。
- 一键审计现在会同时判断本机闲鱼 WebSocket、Cookie、CC自动发货 webhook 配置和补救队列待处理数量；补救队列不为 0 时会让审计失败，避免正式售卖时存在“卡已分配但消息没发出”的黑洞。
- CLI 输出新增本机闲鱼 GUI 摘要：`ws=true, cookie=true, autoShip=true, pendingRescue=0`。
### 文件变更
- `scripts/cc_zhongzhuan_readiness_audit.mjs` — 新增本机 GUI HTTP 审计、`.env` 解析和脱敏状态输出。
- `docs/002-changelog.md` / `docs/006-registries.md` / `docs/007-operations.md` / `docs/009-health.md` / `/Users/blackdj/Documents/VPS-Config/docs/05-unified-execution-plan.md` — 同步一键审计覆盖范围。
### 验证
- `node --check scripts/cc_zhongzhuan_readiness_audit.mjs` → exit 0。
- `node scripts/cc_zhongzhuan_readiness_audit.mjs` → `PASS`，新增 `localXianyuGui: PASS`，输出 `ws=true, cookie=true, autoShip=true, pendingRescue=0`。
- `node scripts/cc_zhongzhuan_readiness_audit.mjs --webhook-smoke` → `PASS`，新增 `localXianyuGui: PASS`，webhook 冒烟 `fulfillment=delivered`、`cleanup=true`、`unused_after=5`。
- `node scripts/cc_zhongzhuan_readiness_audit.mjs --json` → `ok=true`，`localXianyuGui.rootHttp=200`、`apiNoTokenHttp=401`、`apiWithTokenHttp=200`、`ccAutoShip.configured=true`、`ccShipments.pendingRescue=0`。

## [2026-07-05] CC中转闲鱼助手运营状态看板
> 领域: `xianyu` | `backend` | `docs`
> 影响模块: `XianyuAdmin`, `XianyuContext`, `XianyuLive`
> 关联问题: HI-907
### 变更内容
- 本机闲鱼助手 `/api/status` 新增 `cc_auto_ship` 和 `cc_shipments` 摘要：展示 CC中转自动发货是否启用、webhook 是否配置、token 是否存在、延迟秒数、补救队列总数、已发送数、待人工补救数和已处理数。
- 闲鱼管理面板首页“系统状态”新增 CC 自动发货状态行：老板打开 `http://127.0.0.1:18800/` 输入本机 token 后，可直接看到“CC自动发货: 已配置 / 补救待处理: 0 / Webhook 地址”，不用查日志。
- `XianyuContextManager` 新增 `cc_shipment_summary()`，从本机 SQLite 汇总 `cc_shipments` 状态，补救队列不再只是表格明细。
### 文件变更
- `packages/clawbot/src/xianyu/xianyu_context.py` — 新增 `cc_shipment_summary()`。
- `packages/clawbot/src/xianyu/xianyu_admin.py` — `/api/status` 返回自动发货配置和补救队列摘要，首页展示状态。
- `packages/clawbot/tests/test_api_routes_regression.py` / `packages/clawbot/tests/test_xianyu_cc_auto_ship.py` — 覆盖状态摘要、页面文案和补救队列汇总。
- `docs/002-changelog.md` / `docs/007-operations.md` / `docs/009-health.md` / `/Users/blackdj/Documents/VPS-Config/docs/05-unified-execution-plan.md` — 同步 GUI 看板和验证结果。
### 验证
- `node scripts/cc_zhongzhuan_readiness_audit.mjs` → `PASS`。
- `node scripts/cc_zhongzhuan_readiness_audit.mjs --webhook-smoke` → `PASS`，webhook 冒烟 `fulfillment=delivered`、`cleanup=true`、`unused_after=5`。
- `python3 -m py_compile packages/clawbot/src/xianyu/xianyu_admin.py packages/clawbot/src/xianyu/xianyu_context.py packages/clawbot/tests/test_api_routes_regression.py packages/clawbot/tests/test_xianyu_cc_auto_ship.py && git diff --check` → exit 0。
- `cd packages/clawbot && .venv312/bin/python -m pytest tests/test_api_routes_regression.py tests/test_xianyu_cc_auto_ship.py -q` → `34 passed / 0 failed`。
- `make test` → exit 0，进度到 `[100%]`，仅保留第三方 `js2py` DeprecationWarning。
- 本机 `ai.openclaw.xianyu` 重启后，`/api/status` 显示 `ws_connected=true`、`cookie_ok=true`、`cc_auto_ship.configured=true`、`cc_shipments.pending_rescue=0`；首页包含 `CC自动发货` 和 `CC中转发货补救队列`。

## [2026-07-05] CC中转闲鱼自动发货补救队列
> 领域: `xianyu` | `backend` | `docs`
> 影响模块: `XianyuLive`, `XianyuAdmin`, `XianyuContext`
> 关联问题: HI-907
### 变更内容
- 新增本机闲鱼 SQLite 表 `cc_shipments`，记录 CC中转低权限 webhook 发货状态：`message_sent`、`message_send_failed`、`webhook_failed`、`missing_delivery_message`、`exception`、`manually_resolved`。
- 修复自动发货最危险的黑洞场景：当 CC中转 webhook 已经分配兑换码但闲鱼 WebSocket 消息发送失败时，不再只写日志；系统会把完整发货话术写入本机受鉴权管理面板的补救队列，并触发健康告警，方便人工复制补发。
- 本机闲鱼管理面板新增 `GET /api/cc-shipments` 和 `POST /api/cc-shipments/{id}/resolve`，首页增加“CC中转发货补救队列”卡片；失败记录可标记已处理。
- 管理面板首页改为浏览器可直接打开的 token 输入页，API 仍要求 `X-API-Token`；已重启本机 `ai.openclaw.xianyu`，确认首页无 token HTTP 200、API 无 token HTTP 401、正确 token 下 `/api/status` 和 `/api/cc-shipments` HTTP 200。
### 文件变更
- `packages/clawbot/src/xianyu/xianyu_context.py` — 新增 CC中转发货审计表和查询/处理方法。
- `packages/clawbot/src/xianyu/xianyu_live.py` — 自动发货成功、webhook 失败、话术缺失、发送失败和异常均记录到本机补救队列。
- `packages/clawbot/src/xianyu/xianyu_admin.py` — 新增发货补救队列 API 和首页 GUI 卡片。
- `packages/clawbot/tests/test_xianyu_cc_auto_ship.py` / `packages/clawbot/tests/test_api_routes_regression.py` — 覆盖发送失败落队列、上下文持久化和管理 API。
- `docs/002-changelog.md` / `docs/006-registries.md` / `docs/007-operations.md` / `docs/009-health.md` — 同步补救队列和验证结果。
### 验证
- `node scripts/cc_zhongzhuan_readiness_audit.mjs` → `PASS`。
- `node scripts/cc_zhongzhuan_readiness_audit.mjs --webhook-smoke` → `PASS`，webhook 冒烟 `fulfillment=delivered`、`cleanup=true`、`unused_after=5`。
- `python3 -m py_compile packages/clawbot/src/xianyu/xianyu_context.py packages/clawbot/src/xianyu/xianyu_live.py packages/clawbot/src/xianyu/xianyu_admin.py packages/clawbot/tests/test_xianyu_cc_auto_ship.py packages/clawbot/tests/test_api_routes_regression.py` → exit 0。
- `cd packages/clawbot && .venv312/bin/python -m pytest tests/test_xianyu_cc_auto_ship.py -q` → `11 passed / 0 failed`。
- `cd packages/clawbot && .venv312/bin/python -m pytest tests/test_api_routes_regression.py -q` → `21 passed / 0 failed`。
- `cd packages/clawbot && .venv312/bin/python -m pytest tests/test_xianyu_cc_auto_ship.py tests/test_api_routes_regression.py -q` → `33 passed / 0 failed`。
- `make test` → exit 0，进度到 `[100%]`，仅保留第三方 `js2py` DeprecationWarning。
- 本机管理面板：`/` 无 token HTTP 200；`/api/status` 无 token HTTP 401；`/api/status`、`/api/cc-shipments?limit=5` 在正确 `X-API-Token` 下均 HTTP 200。

## [2026-07-05] CC中转书签入口修复与全自动闭环审计脚本复验
> 领域: `infra` | `xianyu` | `deploy` | `docs`
> 影响模块: `Chrome Bookmarks`, `Readiness Audit`, `Xianyu Auto Fulfillment`, `Frist-API`
> 关联问题: HI-907
### 变更内容
- 修复本机 Chrome 入口不可见问题：在 `Default`、`Profile 1`、`Profile 2`、`Profile 3` 真实 Profile 的书签栏写入并去重 `CC中转运营` 文件夹，每个文件夹包含用户主站、New-API 后台、Frist 运营台、`/v1` 网关和 `/v1/models` 检查入口；同时开启书签栏显示，并打开一个普通 Chrome 窗口承载 5 个运营入口。
- 修复 `scripts/cc_zhongzhuan_readiness_audit.mjs` 两个审计问题：正确遍历 Chrome `Bookmarks.roots.bookmark_bar`，避免误判书签不存在；替换残留模板变量并给公网审计请求加 UA，避免 Cloudflare 把 Python urllib 默认请求误判为 403。
- 复跑生产闭环审计：只读模式和 `--webhook-smoke` 模式均通过；带写冒烟会临时分配 1 张卡密、调用低权限闲鱼已付款 webhook、生成发货履约，再清理测试履约并恢复库存。
### 文件变更
- `scripts/cc_zhongzhuan_readiness_audit.mjs` — 修正 Chrome 书签遍历、webhook smoke 模板变量和公网审计请求头。
- `docs/002-changelog.md` / `docs/006-registries.md` / `docs/007-operations.md` / `docs/009-health.md` / `/Users/blackdj/Documents/VPS-Config/docs/05-unified-execution-plan.md` — 同步一键审计命令、验证结果和当前自动化边界。
### 验证
- `node scripts/cc_zhongzhuan_readiness_audit.mjs` → `PASS`，Chrome 书签、本机闲鱼助手、本机配置、Oracle 服务/库存/公网安全门均通过；生产库存 `unused=5`、New-API enabled redemptions `5`、channels `3`。
- `node scripts/cc_zhongzhuan_readiness_audit.mjs --webhook-smoke` → `PASS`，webhook 冒烟 `fulfillment=delivered`、`cleanup=true`、`unused_after=5`。
- `node --check scripts/cc_zhongzhuan_readiness_audit.mjs && git diff --check` → exit 0。
- `cd apps/frist-api && node --test tests/*.test.mjs` → `181 passed / 0 failed`。
- `cd packages/clawbot && .venv312/bin/python -m pytest tests/test_auto_shipper.py tests/test_xianyu_cc_auto_ship.py -q` → `20 passed / 0 failed`。
- `make test` → exit 0，进度到 `[100%]`，仅保留第三方 `js2py` DeprecationWarning。

## [2026-07-05] CC中转闲鱼全自动发货低权限闭环
> 领域: `backend` | `xianyu` | `deploy` | `docs`
> 影响模块: `Frist-API`, `XianyuLive`, `Auto Fulfillment`, `Chrome Bookmarks/Tab Group`
> 关联问题: HI-907
### 变更内容
- 新增低权限自动发货 webhook：`POST /api/ops/xianyu/paid-order`，只接受 `x-cc-xianyu-token`，不复用管理员令牌；未配置 token 返回 503，无 token 返回 401。
- webhook 只接受“等待卖家发货/买家已付款/已付款/待发货/paid”等已付款状态；未付款订单返回 409，防止误发卡。
- OpenClaw `XianyuLive` 已接入 CC中转：检测到“等待卖家发货”后优先调用 CC中转 webhook，拿到发货话术后通过闲鱼消息发给买家；失败时只告警，不回退乱发旧卡券。
- 管理台“闲鱼自动发货”区域新增“全自动接单”状态卡，展示 endpoint、认证头、token 预览和可接受订单状态；不回显完整 token。
- Chrome 已打开可见标签组「📌 CC中转运营」，包含用户主站、New-API 后台、运营台和模型网关地址；此前写入的「CC中转运营」书签文件夹作为备用入口保留。
- 补齐 OpenClaw `XianyuLive` 到 CC中转 webhook 的单元测试，覆盖未配置回退、已付款 payload、发送返回话术、HTTP 失败不发卡、无话术不发卡、CC 失败不回退旧卡券。
- 闲鱼助手已重启加载最新 CC webhook 配置；同时将 `httpx/httpcore` 日志降到 WARNING，并脱敏本地旧日志中的 Telegram Bot URL，避免第三方通知 token 继续落盘。
- 修复“买家不聊天直接付款”可能漏发的问题：当闲鱼订单没有最近商品上下文但 CC webhook 已配置时，仍进入 CC中转自动发货，由运营台按默认/任意未售兑换码分配；可选 `CC_XIANYU_DEFAULT_ITEM_ID` 用于指定默认商品映射。
- 修复 Frist-API webhook 无套餐/无 SKU 订单误判“没有可发货兑换码”的生产 Bug：只有明确传入套餐或额度时才过滤库存，否则从任意未售卡密发货。
- 生产内测已准备 5 张 `day|quotaUsd=30|source=xianyu` 可售卡密，并同步为 5 条 New-API 启用兑换码；测试冒烟占用已回滚，库存仍为 5。
### 文件变更
- `apps/frist-api/server/server.js` — 新增 `/api/ops/xianyu/paid-order`、低权限 token 校验、已付款订单规范化和自动发卡响应；无套餐订单不再错误过滤到 `balance` 套餐。
- `apps/frist-api/admin.html` / `apps/frist-api/src/admin.js` / `apps/frist-api/src/styles.css` — 管理台展示全自动接单状态。
- `apps/frist-api/deploy/production.env.example` — 增加 `FRIST_API_XIANYU_WEBHOOK_TOKEN`。
- `packages/clawbot/src/xianyu/xianyu_live.py` — 已付款订单自动调用 CC中转 webhook 并发送返回话术。
- `packages/clawbot/scripts/xianyu_main.py` — 降低第三方 HTTP 客户端日志级别，避免敏感通知 URL 落盘。
- `packages/clawbot/config/.env.example` — 增加 `CC_XIANYU_*` 自动发货配置项和直接付款兜底商品映射。
- `packages/clawbot/tests/test_xianyu_cc_auto_ship.py` — 新增 CC中转闲鱼自动发货独立回归测试。
- `docs/002-changelog.md` / `docs/006-registries.md` / `docs/007-operations.md` / `docs/009-health.md` / `docs/080-new-api-capability-roadmap.md` / `/Users/blackdj/Documents/VPS-Config/docs/05-unified-execution-plan.md` — 同步全自动发货闭环和边界。
### 验证
- 本地新增回归：`node --test --test-name-pattern 'paid-order webhook has no plan id|low-scope auto-ship webhook' tests/server.test.mjs` → `2 pass / 0 fail`。
- OpenClaw 闲鱼发货回归：`cd packages/clawbot && .venv312/bin/python -m pytest tests/test_auto_shipper.py tests/test_xianyu_cc_auto_ship.py -q` → `20 passed / 0 failed`。
- Frist-API 全量回归：`cd apps/frist-api && node --test tests/*.test.mjs` → `181 passed / 0 failed`。
- Python 语法：`python3 -m py_compile packages/clawbot/src/xianyu/xianyu_live.py packages/clawbot/scripts/xianyu_main.py packages/clawbot/tests/test_xianyu_cc_auto_ship.py` → exit 0。
- 本机助手运行态：`ai.openclaw.xianyu` 重启后 PID 存在，日志显示“闲鱼管理面板启动 / Token 刷新成功 / WebSocket 连接注册完成”，本地日志 Telegram Bot URL 泄露计数为 `0`。
- 项目级回归：`make test` → exit 0，进度跑到 `[100%]`，仅保留第三方 `js2py` DeprecationWarning。
- 本机助手二次运行态：加载直接付款兜底逻辑后重启 `ai.openclaw.xianyu`，日志显示“Token 刷新成功 / WebSocket 连接注册完成”。
- Oracle 部署：`frist-api.service` 重启后 `active`，`FRIST_API_XIANYU_WEBHOOK_TOKEN` 已配置且只显示脱敏。
- 公网安全冒烟：无 token 调用 `https://frist-api-oracle.245334.xyz/api/ops/xianyu/paid-order` 返回 401；带 token 但未付款返回 409。
- 生产库存：Oracle 真实 runtime `/opt/frist-api/data/frist-api/runtime/runtime.json` 显示 `unused=5`，New-API `redemptions.status=1` 为 `5`，启用渠道为 `3`。
- 生产无套餐自动发货冒烟：调用内网 webhook 返回 HTTP 200、`ok=true`、`fulfillmentStatus=delivered`、`cardPlan=day`、`messageGenerated=true`；随后清理测试履约并恢复卡密为 `unused`，`unused_after_cleanup=5`。
- 生产自动发货 E2E：临时卡密 + 已付款 webhook 返回 HTTP 200、`ok=true`、`fulfillmentStatus=delivered`、`messageGenerated=true`，测试后 runtime 和 New-API redemptions 残留均为 0。



## [2026-07-05] CC中转生产内测闭环与运营台入口复验
> 领域: `deploy` | `backend` | `xianyu` | `docs`
> 影响模块: `New-API`, `Frist-API`, `CC Switch`, `Xianyu Fulfillment`, `Oracle Apache`
> 关联问题: HI-907
### 变更内容
- 将 `frist-api-oracle.245334.xyz` 从 Frist-API 跳转名单中移除，作为兑换码与闲鱼自动发货助手的公网运营入口；`frist-api.245334.xyz` 继续 301 到用户主站 `jiyu.245334.xyz`。
- 在 Cloudflare `245334.xyz` 区域新增/确认 `frist-api-oracle.245334.xyz` proxied A 到 Oracle `150.136.73.15`，复用已有覆盖该主机名的 Cloudflare Origin CA 证书；公网访问需要后台入口 Cookie 或入口码，未授权仍不暴露管理台。
- 修复 Frist-API 在 Cloudflare/Apache 链式代理下 `X-Forwarded-Proto/Host` 逗号列表导致 `new URL()` 崩溃的问题；新增原始 HTTP 回归测试覆盖 origin-form 请求和 chained forwarded headers。
- 管理台已同步“售卖闭环 / 闲鱼自动发货助手”GUI：生成可售卡密、粘贴已付款订单、分配卡密并复制话术、复制商品模板、刷新渠道与倍率；Plus/RT/补号等非当前售卖主线能力继续折叠在高级区域。
- 明确闲鱼边界：当前只做“人工确认已付款后一键发货”的安全闭环；自动砍价、批量私信、刷单暂停/隐藏；后续浏览器插件仅可作为已付款订单读取和话术回填助手。
- 生产 E2E 已覆盖 New-API 原生注册/登录/兑换/API Key/模型调用成功路径（受控临时关闭 Turnstile/邮箱验证后立即恢复）、公网 Turnstile/邮箱验证恢复、Frist 运营台兑换码与闲鱼履约、CC Switch `ccswitch:` 导入链接、Key 删除后网关阻断、渠道检测和倍率。
- 将 Oracle `/etc/frist-api/frist-api.env` 和生产配置模板显式固定 `FRIST_API_RATE_MARKUP=0.1`，不再只依赖代码默认值；渠道倍率同步确认只在上游倍率基础上加 `0.1`。
### 文件变更
- `apps/frist-api/server/server.js` — 规整 chained forwarded headers，避免代理请求触发 URL 解析崩溃。
- `apps/frist-api/tests/server.test.mjs` — 新增原始 HTTP/代理头回归测试。
- `apps/frist-api/deploy/production.env.example` — 补充 `FRIST_API_RATE_MARKUP=0.1` 生产模板。
- Oracle `/etc/frist-api/frist-api.env` — 移除 `frist-api-oracle.245334.xyz` 跳转项，变更前已备份到 `/root/codex-backups/`。
- Oracle `/opt/frist-api/apps/frist-api/*` — 同步管理台 GUI 和服务端修复。
- `docs/002-changelog.md` / `docs/006-registries.md` / `docs/007-operations.md` / `docs/009-health.md` / `docs/080-new-api-capability-roadmap.md` / `/Users/blackdj/Documents/VPS-Config/docs/05-unified-execution-plan.md` — 同步入口、验证和运营边界。
### 验证
- 运营入口：`https://frist-api-oracle.245334.xyz/admin.html` 经 Cloudflare 返回 HTTP 200（带后台 Cookie），页面包含 `CC中转`、`闲鱼自动发货助手`、`售卖闭环`、`生成可售卡密`、`复制商品模板`；无入口码/Cookie 时返回 404。 Playwright 截图：`output/playwright/cc-ops-admin-xianyu-20260705.png`。
- New-API 受控 E2E：`CC_NEWAPI_BASE=http://127.0.0.1:13000 node /tmp/cc-newapi-prod-e2e-v2.mjs` 在临时关闭 Turnstile/邮箱验证后通过，覆盖注册、登录、兑换码到账、API Key 创建/更新/禁用/恢复/删除、`/v1/models`、OpenAI/Claude 真实调用、渠道测试；跑完已恢复 `TurnstileCheckEnabled=true`、`EmailVerificationEnabled=true`，并确认临时用户/Token/兑换码残留为 `0`。
- 公网安全门：`https://jiyu.245334.xyz/api/status` 显示 `turnstile_check=true`、`email_verification=true`、`hasCcSwitch=true`；无 Turnstile 的注册/登录返回 `success=false` / `Turnstile token 为空`。
- Frist 生产 E2E：`node /tmp/cc-production-e2e.mjs` 返回 OpenAI/Claude 调用 `200`、卡密同步 New-API、闲鱼履约 `delivered`、readiness `ready=true` 且 `failedChecks=[]`。
- CC Switch E2E：`node /tmp/cc-ccswitch-e2e.mjs` 生成 `ccswitch:` provider 导入链接，确认 endpoint 为 `https://jiyu.245334.xyz/v1`、模型 `gpt-5.4-mini`、Key 匹配；同 Key 调模型 `200`，删除后网关 `401`。
- New-API 原生配置：渠道自动检测每 10 分钟开启，自动禁用/恢复开启，模型请求限流开启；当前 3 个渠道启用，15 个模型倍率写入 `ModelRatio`，典型值为 `gpt-5.4-mini=0.475`、`gpt-5.4=1.35`、`claude-haiku-4-5=0.6`、`claude-sonnet=1.6`。
- 最终复验（2026-07-05 17:08Z）：`FRIST_API_RATE_MARKUP=0.1` 写入 Oracle 后重启 Frist-API，`node --test tests/*.test.mjs` 为 `179 passed / 0 failed`，生产 E2E 返回 OpenAI/Claude 调用 `200`、闲鱼履约 `delivered`、`rateMarkup=0.1`、`healthy=3`、`readiness.ready=true`。

## [2026-07-05] CC中转复用 Frist 旧配置补齐 New-API 安全入口
> 领域: `deploy` | `infra` | `docs`
> 影响模块: `New-API`, `Frist-API`, `Turnstile`, `SMTP`, `Admin 2FA`
> 关联问题: HI-907
### 变更内容
- 在 Oracle 生产环境只读扫描旧 Frist-API 配置，确认 `/etc/frist-api/frist-api.env` 和兼容 `/opt/frist-api/.env` 已存在 Turnstile、SMTP 和管理员 TOTP 配置；输出只包含存在性、长度和 SHA 指纹，不回显密钥。
- 复用旧 Frist 配置写入 New-API 原生 `options`：`TurnstileSiteKey`、`TurnstileSecretKey`、`TurnstileCheckEnabled=true`、SMTP 相关配置、`EmailVerificationEnabled=true`。
- 复用旧 Frist 管理员 TOTP secret，给 New-API 管理员/root 账户启用原生 2FA；当前 `two_fas=2`。
- 写入前已备份 New-API SQLite: `one-api.db.bak-before-newapi-option-reuse-20260705T155235Z`；写入后重启 `openclaw-newapi.service`。
- 剩余正式售卖前 P0：模型请求限流、可售兑换码库存、老板真人浏览器 Turnstile 注册/登录/兑换验收。
### 文件变更
- Oracle `/opt/frist-api/data/newapi/one-api.db` — 写入 New-API 原生安全/邮箱/2FA配置，变更前已备份。
- `docs/080-new-api-capability-roadmap.md` — 将 Turnstile、SMTP/邮箱验证、管理员 2FA 状态从“待启用”更新为“已复用 Frist 配置并启用”。
- `docs/009-health.md` — 同步当前生产内测健康状态和剩余 P0 技术债。
- `docs/002-changelog.md` — 记录本次生产配置复用。
- `/Users/blackdj/Documents/VPS-Config/docs/05-unified-execution-plan.md` — 同步 VPS-Config 侧源头文档，避免域名/Oracle/安全配置状态漂移。
### 验证
- 旧配置扫描：Frist 生产环境 `turnstile_enabled=True`、`smtp_present=True`、`totp_present=True`，Turnstile 允许域名包含 `jiyu.245334.xyz`。
- New-API 状态：内网 `/api/status` 返回 `turnstile_check=true`、`email_verification=true`；公网 `/api/status` 同样返回 `turnstile_check=true`、`email_verification=true`。
- 安全门验证：公网无 Turnstile 的注册/登录请求返回 `success=false`，消息为 `Turnstile token 为空`。
- SMTP 网络验证：Oracle 到 SMTP 服务器 TLS 握手成功，`cipher_ok=True`；未发送测试邮件，未打印邮箱密码。
- 服务验证：`openclaw-newapi.service` 重启后为 `active`；公网首页 HTTP 200 且包含 `CC中转`。

## [2026-07-05] CC中转 New-API 原生能力盘点与补齐路线
> 领域: `docs` | `deploy`
> 影响模块: `New-API`, `CC中转`, `Production Beta`
> 关联问题: HI-907
### 变更内容
- 新增 New-API 原生能力盘点，明确用户认证、API Key、兑换码/钱包、渠道/模型、网关协议、日志监控、安全风控等能力优先使用 New-API 已有实现。
- 明确 CC Switch、86Game 上游导入、闲鱼履约和生产 readiness 的定位：作为 New-API 主业务流之上的轻集成/补强层，不替换 New-API 主流程和主数据表。
- 记录当前生产状态：3 个启用渠道、15 个模型、22 条能力映射，Turnstile/邮箱验证/Passkey/OAuth/签到等 New-API 原生配置尚未启用，后续按 P0 → P1 → P2 补齐。
- 追加生产只读审计：确认 CC Switch 入口、API Key、渠道、模型、能力映射、兑换/充值、日志统计等可继续沿用 New-API 原生能力；Turnstile、SMTP/邮箱验证、管理员 2FA、模型请求限流和可售兑换码库存列为正式售卖前 P0。
- 补齐 New-API 原生配置键清单：Turnstile、SMTP、邮箱验证、模型请求限流和渠道自动测试后续均走 `/api/option`/管理端系统设置，不改源码、不新建配置表。
### 文件变更
- `docs/080-new-api-capability-roadmap.md` — 新增 New-API 原生能力盘点、补齐路线和生产只读审计结果。
- `docs/009-health.md` — 登记 New-API 原生 P0 技术债和当前生产只读审计结论。
- `docs/003-docs-index.md` — 登记 080 报告。
- `docs/002-changelog.md` — 记录本次盘点文档。
### 验证
- 源码盘点：读取 `packages/new-api-upstream/router/api-router.go`、`relay-router.go`、`web/default/src/features/*`、`web/default/src/routes/*`。
- 生产状态盘点（当时状态，已被上方“复用 Frist 旧配置补齐 New-API 安全入口”覆盖）：`/api/status` 显示 `system_name=CC中转`、`hasCcSwitch=true`、`turnstile_check=false`、`email_verification=false`；SQLite 摘要显示 `enabled_channels=3`、`models_meta=15`、`abilities=22`。
- 追加只读审计（当时状态，已被上方“复用 Frist 旧配置补齐 New-API 安全入口”覆盖）：`openclaw-newapi.service`、`frist-api.service`、`apache2` 均为 `active`；New-API SQLite 显示 `channels=3`、`models=15`、`abilities=22`、`tokens=6`、`redemptions=2`、`top_ups=4`、`logs=192`、`two_fas=0`、`subscription_plans=0`。

## [2026-07-05] CC中转公网主入口切到 New-API 成熟面板
> 领域: `deploy` | `infra` | `docs`
> 影响模块: `New-API`, `CC中转`, `Oracle Apache`, `Production Beta`
> 关联问题: HI-907
### 变更内容
- 已把 `https://jiyu.245334.xyz/` 公网主入口从旧 Frist 自研页面切到 `openclaw-newapi.service`，也就是成熟开源 New-API 面板；Frist-API 继续在 `127.0.0.1:3180` 运行，作为 CC Switch/旧桥接能力来源和内部兼容服务。
- Apache 已备份旧配置后改为：主站 `jiyu.245334.xyz` 反代 `127.0.0.1:13000`；旧 `frist-api.245334.xyz` 继续 301 到主站；`frist-api-oracle.245334.xyz` 仅作为旧 Frist 内部排障别名预留。
- 为避免官方镜像静态 HTML 首屏残留默认品牌，Apache 仅对 `text/html` 做最小品牌替换和浏览器标题修正；未对 New-API JS 包做中文全局替换，避免影响请求头和业务逻辑。
- CC Switch 继续走 New-API 原生聊天/客户端入口配置，`/api/status` 的 `chats` 已包含 `CC Switch`，后续再做轻集成，不魔改 New-API 核心。
- 当前仍按“生产内测，暂未正式售卖”口径运行；当时 New-API 原生 `turnstile_check=false`、`email_verification=false`，后续已在同日复用 Frist 旧配置启用。
### 文件变更
- Oracle `/etc/apache2/sites-available/frist-api.conf` — 公网主站反代切到 New-API，保留旧 Frist 内部兼容入口；配置变更前已在服务器同目录生成时间戳备份。
- `docs/002-changelog.md` / `docs/006-registries.md` / `docs/007-operations.md` / `docs/009-health.md` — 同步 New-API 主入口、验证结果和内测边界。
### 验证
- 内网生产 E2E：`CC_NEWAPI_BASE=http://127.0.0.1:13000 node /tmp/cc-newapi-prod-e2e-v2.mjs` → 原生注册、登录、兑换码创建/兑换到账、API Key 创建/列表/详情/取 Key/更新/禁用/恢复/删除、`/v1/models`、OpenAI `gpt-5.4-mini`、Claude `claude-haiku-4-5-20251001`、渠道刷新均通过，清理后 `users=0/tokens=0/redemptions=0`。
- 外网生产 E2E：`CC_NEWAPI_BASE=https://jiyu.245334.xyz node /tmp/cc-newapi-prod-e2e-v2.mjs` → 同一套链路全部通过；模型数 `15`，启用渠道 `3`，OpenAI/Claude 真实调用均 `200`，禁用/删除 Key 后 `/v1/models` 均 `401`。
- 公网冒烟：`https://jiyu.245334.xyz/api/status` 返回 `system_name=CC中转`、`server_address=https://jiyu.245334.xyz`、`setup=true`、`hasCcSwitch=true`；未授权 `/v1/models` 返回 `401`；旧 `https://frist-api.245334.xyz/` 返回 `301` 到主站。
- 浏览器验证：Playwright 打开首页、登录页、注册页均无前端 error/warning，页面可见 `CC中转`，浏览器标题最终为 `CC中转`；截图 `output/playwright/cc-newapi-public-home-20260705.png`。
- 服务/数据检查：`frist-api.service`、`openclaw-newapi.service`、`apache2`、`frist-api-r2-backup.timer` 均 `active`；New-API SQLite 查询 `e2e_users=0`、`e2e_tokens=0`、`e2e_redemptions=0`、`enabled_channels=3`、`models=15`；`apache2ctl configtest` 为 `Syntax OK`。

## [2026-07-05] CC中转改为 New-API 成熟面板优先底座
> 领域: `deploy` | `backend` | `docs`
> 影响模块: `New-API`, `CC中转`, `Local Beta`
> 关联问题: HI-907
### 变更内容
- 按用户最新要求，停止继续把 Frist-API 自研页面作为主面板优先方向，改为以高星开源项目 `QuantumNous/new-api` 作为成熟面板底座。
- 本地 `openclaw-newapi` 已保持官方稳定镜像运行，配置项 `SystemName=CC中转`，未新增公告、页脚、免责声明、Logo 或营销文案。
- 从已验证的 Oracle New-API 数据库只同步渠道、模型和能力表到本地，形成可运行本地底座：3 个启用渠道、15 个启用模型、22 条能力映射。
- 本地 root 用户已重置为随机强密码，密码只保存到 `/tmp/cc-newapi-admin-password`，不写入仓库。
- 保留极小源码品牌补丁：仅把 New-API 默认系统名、HTML title 和 SVG title 改为 `CC中转`；当前品牌镜像构建因上游 Dockerfile `bun install` tarball 完整性校验失败暂未替换官方镜像，后续网络稳定后继续构建。
### 文件变更
- `packages/new-api-upstream/common/constants.go` — 默认系统名改为 `CC中转`。
- `packages/new-api-upstream/web/default/index.html` / `web/classic/index.html` / `web/default/src/assets/logo.tsx` — 静态 title 改为 `CC中转`。
- `docs/002-changelog.md` — 记录 New-API 底座优先方向和本地验证结果。
### 验证
- GitHub 调研：`QuantumNous/new-api` 当前约 41k Star，2026-07-05 仍活跃更新；`Wei-Shaw/sub2api` 约 30k Star，但“订阅拼车/共享”方向与既定边界冲突风险更高，因此不作为第一底座。
- 本地服务：`openclaw-newapi` 运行 `calciumion/new-api:v1.0.0-rc.4`，监听 `127.0.0.1:3000`，容器 healthy。
- 状态接口：`/api/status` 返回 `system_name=CC中转`、`setup=true`、`footer_html=""`。
- 管理登录：`POST /api/user/login` 使用本地 root 用户返回 200；带 `New-Api-User: 1` 查询 `/api/channel/` 返回 3 个渠道。
- API 验证：本地测试 Key 调用 `/v1/models` 返回 15 个模型；`gpt-5.4-mini` 和 `claude-haiku-4-5-20251001` 真实 Chat 调用均返回 200。
- 浏览器验证：Playwright 打开 `http://127.0.0.1:3000/`，页面可见品牌为 `CC中转`，截图 `output/playwright/cc-newapi-local-home-20260705.png`。

## [2026-07-05] CC中转生产内测上游补货与全链路 E2E 闭环
> 领域: `backend` | `deploy` | `ai-pool` | `docs`
> 影响模块: `Frist-API`, `New-API Bridge`, `API Key Management`, `Production Beta`
> 关联问题: HI-907
### 变更内容
- 对用户提供的 3 条 86Game 上游 Key 做脱敏探测：`/v1/models` 与真实 Chat 调用均通过，未在仓库、日志或文档中回显完整 Key。
- 已将可用库存接入生产内测：New-API 当前有 3 个可用渠道、15 个模型；OpenAI/Codex 与 Claude 真实模型调用均返回 200；`/api/admin/production-readiness` 返回 `ready=true`。
- 修复 New-API Token 删除后的测试垃圾残留：New-API 删除接口可能只做软删除或让详情接口查不到但 SQLite `tokens` 表仍残留；Frist-API 现在在配置 `FRIST_API_NEWAPI_SQLITE_DB` 时会对被删 Token 做一次幂等硬删除，避免生产 E2E 临时 Key 越积越多。
- 生产内测 E2E 已覆盖：公网首页、Turnstile 安全拦截、登录态 Dashboard、API Key 创建、模型列表、OpenAI/Claude 真实调用、Key 禁用、兑换码生成并同步 New-API、闲鱼发货话术、渠道状态刷新、readiness、测试数据清理。
- 当前口径保持“生产环境内测，暂未正式售卖”；公网自动化不会绕过 Turnstile，真实注册/登录/兑换的最后一跳仍建议由老板在浏览器点一次人机验证做人工验收。
### 文件变更
- `apps/frist-api/server/newApiBridge.js` — 删除 New-API Token 后按 SQLite 配置做幂等硬删除兜底。
- `apps/frist-api/tests/server.test.mjs` — 新增 New-API 软删除后 SQLite 残留必须清理的回归测试。
- `docs/002-changelog.md` / `docs/009-health.md` — 同步生产内测上游恢复、E2E 验证结果和售卖前边界。
### 验证
- 本地语法与全量测试：`cd apps/frist-api && node --check server/newApiBridge.js server/server.js && node --test tests/*.test.mjs` → `177 passed / 0 failed / 0 skipped`。
- Oracle 部署：`rsync` 同步 `apps/frist-api` 后重启；`frist-api.service`、`openclaw-newapi.service`、`apache2` 均为 `active`。
- 生产 E2E：`node /tmp/cc-production-e2e.mjs` → 首页 200；无 Turnstile 的注册/登录/兑换均被拦截；临时 API Key 创建成功；`/v1/models` 返回 10 个用户可见模型样本；OpenAI `gpt-5.4-mini` 与 Claude `claude-haiku-4-5-20251001` 真实调用均 200；禁用 Key 后网关 401；卡密同步 New-API 成功；闲鱼履约 `delivered`；readiness `ready=true` 且 `failedChecks=[]`。
- 清理验证：New-API SQLite 查询 `e2e_tokens=0`、`active_e2e_tokens=0`、`e2e_redemptions=0`。
- 公网冒烟：`https://jiyu.245334.xyz/` → HTTP 200；未授权 `/v1/models` → HTTP 401；旧 `https://frist-api.245334.xyz/` 最终跳转到 `https://jiyu.245334.xyz/`。

## [2026-07-05] CC中转健康上游库存纳入生产就绪门槛
> 领域: `backend` | `deploy` | `docs`
> 影响模块: `Frist-API`, `Production Readiness`, `New-API Inventory`
> 关联问题: HI-907
### 变更内容
- 修正生产内测 readiness 的误导风险：以前只要域名、New-API 数据库、备份、2FA、Turnstile、兑换码和 SLA 事件齐全，即使当前健康上游库存为 0，`/api/admin/production-readiness` 仍可能返回 `ready=true`。
- 新增 `healthy_upstream_inventory` 检查项：同时统计 Frist 本地健康可路由库存和 New-API SQLite 中可用渠道/模型；两边都为 0 时 readiness 必须返回 `ready=false`。
- 管理端 readiness 响应新增 `upstreamInventory` 摘要，明确展示本地健康库存数、New-API 可用渠道数、模型数和 SQLite 可读状态。
- 当前 Oracle 生产内测环境按新规则应保持 `ready=false`，直到补入真实健康上游并完成模型调用复验；这能防止“站点安全项全绿但没有货也开卖”的误判。
### 文件变更
- `apps/frist-api/server/server.js` — production readiness 增加健康上游库存门槛和 New-API SQLite 只读库存统计。
- `apps/frist-api/tests/server.test.mjs` — 新增无健康上游时 readiness 必须阻断的回归测试，以及兼容当前 New-API SQLite schema 的库存统计测试。
- `docs/002-changelog.md` / `docs/006-registries.md` / `docs/007-operations.md` / `docs/009-health.md` — 同步 8 项 readiness 检查与当前不可售判断。
### 验证
- TDD 失败复现：`cd apps/frist-api && node --test --test-name-pattern 'keeps production readiness blocked' tests/server.test.mjs` 修复前为 `true !== false`。
- 单点验证：同一命令修复后通过。
- 本地全量验证：`cd apps/frist-api && node --check server/server.js server/newApiBridge.js && node --test tests/*.test.mjs` → `176 passed / 0 failed / 0 skipped`。

## [2026-07-05] CC中转 New-API Key 禁用生产修复与售卖前复验
> 领域: `backend` | `deploy` | `docs`
> 影响模块: `Frist-API`, `New-API Bridge`, `API Key Management`, `Production Beta`
> 关联问题: HI-907
### 变更内容
- 生产内测复验发现 New-API 创建的 API Key 可创建、可删除，但“禁用”只返回 200，New-API SQLite `tokens.status` 仍保持 `1`，禁用后 Key 仍可访问网关。
- 根因定位为 QuantumNous/new-api 的普通 `PUT /api/token/` 不更新 `status` 字段，官方前端启停 Key 使用的是 `PUT /api/token/?status_only=true`。
- Frist-API New-API 桥接层已改为：名称/额度等元数据走普通 PUT，启用/禁用走 `status_only=true`，随后重新读取 Token 最新状态再返回给前端。
- 已同步到 Oracle 生产内测环境并重启 `frist-api.service`；生产复验显示 API Key 禁用后数据库 `status=2`，禁用 Key 访问 `/v1/models` 返回 401，删除后 `deleted_at` 正常写入。
- 继续确认当前不是正式售卖状态：New-API `channels=0/models=0`，Frist 本地库存仅有 `failed/exhausted`，可售健康上游仍为 0；`/Users/blackdj/Documents/VPS-Config` 未发现可导入的明文 AI 上游，Oracle 旧 healthy runtime 虽有 2 条历史记录但 `enc:v1` 字段无法用现存历史数据密钥解开，不能直接恢复售卖库存。
### 文件变更
- `apps/frist-api/server/newApiBridge.js` — API Key 启用/禁用改用 New-API `status_only=true` 状态接口。
- `apps/frist-api/tests/server.test.mjs` — New-API 业务端到端测试增加 `status_only=true` 断言，并用可变 Token 状态验证禁用返回。
- `docs/002-changelog.md` / `docs/009-health.md` — 登记生产复验结果和正式售卖阻塞项。
### 验证
- TDD 失败复现：`cd apps/frist-api && node --test --test-name-pattern 'uses New-API business endpoints' tests/server.test.mjs` 修复前为 `500 !== 200`，原因是请求未携带 `status_only=true`。
- 单点修复验证：同一命令修复后通过。
- 本地全量验证：`cd apps/frist-api && node --check server/newApiBridge.js server/server.js && node --test tests/*.test.mjs` → `174 passed / 0 failed / 0 skipped`；`git diff --check` → exit 0。
- 生产闭环复验：管理员 2FA/readiness 200 且 `7/7`；临时卡密生成同步 New-API `synced=1`，闲鱼履约 `delivered/sold`，测试卡/测试用户/测试兑换码均清理；临时 API Key 创建 200、禁用 200 且 New-API DB `status=2`、禁用后 `/v1/models` 401、删除 200。
- 公网复验：`https://jiyu.245334.xyz/` HTTP 200，标题 `CC中转`，页面包含“生产环境内测/暂未正式售卖”；无 Turnstile 的注册/登录/兑换均 HTTP 400；旧 `frist-api.245334.xyz` 最终跳转到主入口；Oracle 四个关键服务 active，failed units 为 0。
- 上游恢复排查：VPS-Config 仅找到路由/审计记录，未找到可导入明文上游；Oracle 旧 runtime 2 条 healthy 记录为旧 `enc:v1`，现存 `FRIST_API_DATA_ENCRYPTION_KEY` 历史值可解字段数均为 0。

## [2026-07-05] CC中转生产内测品牌收口与售卖前验收
> 领域: `frontend` | `backend` | `deploy` | `docs` | `xianyu`
> 影响模块: `Frist-API`, `CC中转`, `Redemption Cards`, `Production Beta`
> 关联问题: HI-906
### 变更内容
- 将生产内测可见品牌从「极域 JiYu」收口为「CC中转」，域名暂不变，继续使用 `https://jiyu.245334.xyz/` 作为生产内测入口。
- 页面、管理端、邮件配置示例、静态 SVG 资产和 smoke test 文案补齐 CC中转品牌，并在登录页、仪表盘、充值/兑换、管理端加入“生产环境内测，暂未正式售卖”提示。
- 新生成卡密默认前缀改为 `CC`，新增 `CC-DAY-001` / `CC-MONTH-001` / `CC-BOOST-100` 测试兼容码；历史 `JIYU-*` 仅保留为兼容别名，避免旧测试卡密失效。
- 生产 readiness 的兑换码闭环说明从“售卖兑换码”改为“生产内测人工发放 + 站内核销”，避免在正式开卖前误导。
- 修复 New-API 生产桥接下的两个售卖前断点：后台生成/闲鱼发货的 CC 卡密经 New-API 到账后会同步回写本地卡密和履约状态；New-API 创建的用户 API Key 访问 `GET /v1/models` 时改为代理到 New-API，避免客户端拉模型列表时 401。
- 生产 Oracle 环境修正 New-API access token、`FRIST_API_NEWAPI_GATEWAY_ENABLED=1` 和 `FRIST_API_NEWAPI_GATEWAY_BASE_URL=http://127.0.0.1:13000/v1`；同时确认 New-API `channels=0/models=0`、Frist 本地库存 `0` 个健康 Key，当前仍是生产内测，不能正式售卖。
### 文件变更
- `apps/frist-api/index.html` / `admin.html` / `src/styles.css` — CC中转品牌和生产内测提示。
- `apps/frist-api/server/server.js` / `server/shared.js` / `src/businessFlow.js` — 默认 CC 卡密前缀、CC 测试兑换码、内测 readiness、New-API 兑换回写和 `/v1/models` 代理。
- `apps/frist-api/server/newApiBridge.js` — GET/HEAD 代理请求不携带 body，兼容 `GET /v1/models`。
- `apps/frist-api/assets/*.svg` / `favicon.svg` / `deploy/*` — 静态资产、部署示例品牌和 Oracle New-API 网关地址同步。
- `docs/006-registries.md` / `docs/007-operations.md` / `docs/009-health.md` / `docs/051-jiyu-brand-production-plan.md` — 文档改为 CC中转生产内测口径。
### 验证
- TDD 失败复现：`node --test --test-name-pattern 'marks local CC card|uses New-API business endpoints' tests/server.test.mjs` 修复前分别暴露“本地履约未回写”和 `GET /v1/models` 401。
- 语法检查：`cd apps/frist-api && node --check server/server.js src/app.js src/admin.js src/core.js src/businessFlow.js server/shared.js server/catalog.js server/email.js server/newApiBridge.js server/payments.js src/serverClient.js` → exit 0。
- Frist-API 全量测试：`cd apps/frist-api && node --test tests/*.test.mjs` → `174 passed / 0 failed / 0 skipped`。
- 格式检查：`git diff --check` → exit 0。
- Oracle 生产烟测：管理员 2FA/readiness 返回 `ready=true`；卡密生成同步 New-API 成功并完成闲鱼履约分配，测试卡已禁用且 New-API 兑换行已删除；临时测试用户创建 API Key、禁用、删除均返回 200；`GET /v1/models` 经配置修复后返回 200 但模型数为 0，暴露“上游渠道为空”阻塞项。


## [2026-07-04] 极域 JiYu 生产强制模式与安全闭环验收
> 领域: `backend` | `deploy` | `infra` | `docs`
> 影响模块: `Frist-API`, `JiYu Production`, `Turnstile`, `Admin 2FA`, `R2 Backup`
> 关联问题: HI-905

### 变更内容
- 生产环境正式开启 `FRIST_API_PUBLIC_MODE=1` 与 `FRIST_API_ENFORCE_PRODUCTION_READINESS=1`，关闭临时公网 HTTP 例外和验证码答案回显。
- Cloudflare Turnstile 已保护注册、登录、兑换三个高风险入口；不带 token 的公网请求会返回“请先完成人机验证”。
- 管理端启用 TOTP 二次验证，TOTP secret 和数据加密 key 仅保存在 Oracle root-only 环境文件/安全文件中，未写入仓库或终端输出。
- 触发一次 R2 备份并完成恢复演练：备份包 `frist-api-20260705T000508Z.tar.gz` 解包后 `runtime.json` 可读、`one-api.db` `pragma integrity_check` 为 `ok`，并登记到 `/api/admin/backups/status`。
- 修复生产发现的历史 runtime 加密兼容问题：旧数据已带 `__encryption` 标记但旧加密 key 不可恢复时，无法解密的 `enc:v1:` 敏感字段会被隔离为“需重新生成”，不再让管理接口整体 500。
- `/api/admin/production-readiness` 已返回 `ready=true`，7 个检查项（固定品牌域名、New-API 数据库、备份监控、管理员 2FA、Turnstile、兑换码收款闭环、渠道 SLA）全部通过。

### 文件变更
- `apps/frist-api/server/server.js` — runtime 旧加密字段隔离兼容，避免生产新 key 启用后整站 500。
- `apps/frist-api/tests/server.test.mjs` — 新增带 `__encryption` 标记的旧加密 runtime 回归测试。
- `docs/002-changelog.md` / `docs/006-registries.md` / `docs/007-operations.md` / `docs/009-health.md` / `docs/051-jiyu-brand-production-plan.md` — 同步生产强制模式、2FA、备份恢复演练和 readiness 结果。

### 验证
- 新增失败复现：`cd apps/frist-api && node --test --test-name-pattern 'marked encrypted runtime fields' tests/server.test.mjs` 修复前为 `500 !== 200`，修复后通过。
- 语法检查：`cd apps/frist-api && node --check server/server.js src/app.js src/serverClient.js` → exit 0。
- Frist-API 全量测试：`cd apps/frist-api && node --test tests/*.test.mjs` → `172 passed / 0 failed / 0 skipped`。
- 格式检查：`git diff --check` → exit 0。
- Oracle 服务：`frist-api.service`、`openclaw-newapi.service`、`apache2.service`、`frist-api-r2-backup.timer` → 全部 `active`；`systemctl --failed` → `0`。
- 公网冒烟：`https://jiyu.245334.xyz/` → HTTP 200；`/api/frist/dashboard` → HTTP 200；未授权 `/v1/models` → HTTP 401；旧 `https://frist-api.245334.xyz/` 最终跳转 `https://jiyu.245334.xyz/`。
- Turnstile 防护：不带 Turnstile token 的 `register/login/redeem` → HTTP 400，错误文案为“请先完成人机验证”。
- 生产 readiness：`/api/admin/production-readiness` → `ready=true`；备份登记时间 `2026-07-05T00:05:09.000Z`，SLA 探测事件 `21` 条。
- 浏览器验收：Playwright 打开线上首页，标题 `极域 JiYu`，截图保存为 `output/playwright/jiyu-production-home-20260704.png`；控制台噪音来自 Cloudflare Turnstile PAT/预加载挑战，不是本站脚本错误。


## [2026-07-04] 极域 JiYu Cloudflare 子域名与 Oracle 生产闭环
> 领域: `deploy` | `infra` | `docs`
> 影响模块: `JiYu Domain`, `Cloudflare DNS`, `Oracle ARM`, `Frist-API`
> 关联问题: HI-904, TD-007

### 变更内容
- 按“优先用 xyz 或免费域名”的上线要求，确定当前正式入口为 `https://jiyu.245334.xyz/`，不等待新域名购买。
- 在 Cloudflare `245334.xyz` 区域新增 `jiyu.245334.xyz` proxied A 记录，指向 Oracle ARM `150.136.73.15`。
- 在 Oracle 安装覆盖 `jiyu.245334.xyz`、`frist-api.245334.xyz`、`frist-api-oracle.245334.xyz` 的 Cloudflare Origin CA 证书，并让 Apache 以 JiYu 主机名反代到 `127.0.0.1:3180`。
- 生产环境变量切到 `FRIST_API_PUBLIC_GATEWAY_BASE_URL=https://jiyu.245334.xyz/v1`、`FRIST_API_CANONICAL_HOST=jiyu.245334.xyz`；旧 `frist-api.245334.xyz` 保留为 301 跳转和冷回滚排障别名。
- 仓库默认生产模板、Nginx 示例、测试断言和运维文档从未购买的 `jiyu.gg` 收口到当前真实可用的 `jiyu.245334.xyz`；后续若购买独立品牌域名，再按同一流程替换。
- 同步 `/Users/blackdj/Documents/VPS-Config` 的公开路由、Cloudflare 资产和业务故障切换契约，登记 JiYu 子域名、证书、回滚路径和健康门槛。

### 文件变更
- `apps/frist-api/server/server.js` / `src/app.js` / `index.html` — 默认 JiYu 公网入口改为 `jiyu.245334.xyz`。
- `apps/frist-api/deploy/production.env.example` / `deploy/nginx.conf` — 生产环境变量和反代示例改为当前真实域名。
- `apps/frist-api/tests/*.test.mjs` — 更新品牌域名、跳转和生产边界断言。
- `docs/006-registries.md` / `docs/007-operations.md` / `docs/009-health.md` / `docs/051-jiyu-brand-production-plan.md` — 登记当前生产入口、验证步骤和后续独立域名替换边界。
- `/Users/blackdj/Documents/VPS-Config/config/domain-routing.public.json` / `config/cloudflare-assets.public.json` / `config/business-failover.public.json` — 登记 Cloudflare DNS、Oracle 入口和回滚说明。

### 验证
- 语法检查：`cd apps/frist-api && node --check server/server.js src/app.js src/admin.js src/core.js src/businessFlow.js server/shared.js server/catalog.js server/email.js` → exit 0。
- Frist-API 全量测试：`cd apps/frist-api && node --test tests/*.test.mjs` → `166 passed / 0 failed / 0 skipped`。
- 配置格式：`python3 -m json.tool` 校验 VPS-Config 三个公开 JSON（`domain-routing.public.json`、`cloudflare-assets.public.json`、`business-failover.public.json`）→ exit 0。
- 格式检查：`git diff --check` → exit 0。
- 公网冒烟：`https://jiyu.245334.xyz/` → HTTP 200 且页面包含 `极域 JiYu`；`/api/frist/dashboard` → HTTP 200；未授权 `/v1/models` → HTTP 401；`https://frist-api.245334.xyz/` 最终跳转到 `https://jiyu.245334.xyz/`。
- Oracle 同步：已用 `rsync` 增量同步 `apps/frist-api` 到 `/opt/frist-api/apps/frist-api/`，排除 `node_modules/`、`data/`、`.env`、`.playwright-cli/`；同步前远端备份到 `/root/codex-backups/*-jiyu-app-before-domain-template-sync/`。
- Oracle 服务：`frist-api.service`、`openclaw-newapi.service`、`apache2`、`frist-api-r2-backup.timer` → 全部 `active`；`systemctl --failed` → `0 loaded units listed`。
- 重启后复验：JiYu 首页 HTTP 200，页面不再包含 `jiyu.gg`；Dashboard HTTP 200；未授权 `/v1/models` HTTP 401；旧 Frist 域名最终跳转到 JiYu 主站。


## [2026-07-04] 极域 JiYu 品牌重塑与兑换码生产安全收口
> 领域: `frontend` | `backend` | `deploy` | `docs` | `xianyu`
> 影响模块: `Frist-API`, `JiYu Brand`, `Redemption Cards`, `Xianyu Fulfillment`, `Production Config`
> 关联问题: HI-904

### 变更内容
- 将 Frist-API 对外品牌升级为「极域 JiYu」：用户端、管理端、CC Switch 导入名、邮件模板、默认网关示例和生产配置模板统一使用 JiYu 品牌与 `jiyu.245334.xyz`。
- 新增原创 JiYu SVG 资产：favicon、Logo、闲鱼头像、闲鱼横幅；主色统一为 `#7F77DD` 紫色浅色商业后台。
- 用户可见文案新增服务说明、服务条款、售后/退款规则、隐私说明四个页面，并从首页、兑换页和页脚直达；禁用“官方合作/官方授权/平台直营/第三方”等高风险表述。
- 模型价格展示从“官方价格”改成“参考标价”，默认示例卡密从 `FRIST-*` 改为 `JIYU-*`，避免用户误解为厂商直营或旧品牌残留。
- 渠道同步默认来源 ID 从目标站名称改为中性 `reference-channel`，测试示例域名也改为 `metered-supplier.example.com`。
- 兑换码安全升级：新生成卡密只在创建响应/导出文本里出现明文，运行数据改存 `codeHash + codeCipher + codePreview`；闲鱼履约话术按需解密生成，不长期保存完整卡密话术。
- 兑换接口新增 IP + 登录账号双维度频率限制，降低暴力猜码风险；测试覆盖同 IP 和同账号换 IP 两种枚举场景。
- 生产模板改为 `jiyu.245334.xyz` 唯一品牌入口，旧数字域名和历史测试域名只作为跳转/排障来源。
- 快速开源复用检查未发现 86GameStore 本身公开仓库；MIT 卡密商城 `34892002/edgeKey` 为 Cloudflare Workers/Vike 技术栈，和当前已打通的 JiYu/Frist-API 链路不一致，本轮不迁移，避免推倒重来。

### 文件变更
- `apps/frist-api/index.html` / `admin.html` / `src/styles.css` / `src/app.js` / `src/core.js` — JiYu 品牌、紫色视觉、合规页面和导入文案。
- `apps/frist-api/server/server.js` / `server/email.js` / `server/payments.js` / `server/newApiBridge.js` — JiYu 默认品牌、卡密哈希/加密、兑换限流和邮件文案。
- `apps/frist-api/assets/*.svg` / `favicon.svg` — JiYu Logo、闲鱼头像、闲鱼横幅和 favicon。
- `apps/frist-api/deploy/production.env.example` / `deploy/nginx.conf` / `deploy/smoke-test.sh` — `jiyu.245334.xyz` 生产入口、旧域名跳转和 smoke 文案。
- `apps/frist-api/tests/*.test.mjs` — 更新品牌断言、卡密不明文落库、闲鱼履约不保存完整卡密话术和兑换限流回归。
- `docs/051-jiyu-brand-production-plan.md` / `docs/003-docs-index.md` / `docs/006-registries.md` / `docs/007-operations.md` / `docs/009-health.md` — 登记 JiYu 生产上线方案、配置项和健康状态。

### 验证
- 语法检查：`cd apps/frist-api && node --check server/server.js src/app.js src/admin.js src/core.js src/businessFlow.js server/shared.js server/catalog.js server/email.js` → exit 0。
- Frist-API 全量测试：`cd apps/frist-api && node --test tests/*.test.mjs` → `166 passed / 0 failed / 0 skipped`。
- 格式检查：`git diff --check` → exit 0。

## [2026-07-04] QuantumNous/new-api 本机直连栈与 Frist-API 全面桥接
> 领域: `backend` | `infra` | `docs`
> 影响模块: `QuantumNous/new-api`, `Frist-API`, `New-API Bridge`, `Docker Compose`, `Makefile`
> 关联问题: HI-903

### 变更内容
- 将本机 New-API 运行栈收敛为固定上游 `QuantumNous/new-api` release：submodule `packages/new-api-upstream` 和 Docker 镜像均固定在 `v1.0.0-rc.4`，避免 `latest` 自动升级影响数据。
- 新增一键本机启动路径：`make new-api-up` 先备份 `data/newapi` 再启动 New-API；`make frist-api-newapi-setup` 从本机 SQLite 读取已生成 access token 并写入 `.env`，不在终端打印密钥；`make frist-api-up` 同时启动 New-API 与 Frist-API。
- Frist-API Docker 内部默认通过 `http://new-api:3000` 和 `http://new-api:3000/v1` 访问 New-API，宿主机调试继续用 `http://127.0.0.1:3000`。
- Frist-API 服务端 New-API 适配器已覆盖原 Frist 用户侧核心业务：看板、API Key 创建/改名/删除、日志/用量、兑换码核销、订阅/充值/邀请读取，以及可选 `/v1` 网关代理。
- 保留 Frist-API 自研差异能力：86GameStore 风格工作台、CC Switch/Codex/OpenCode/Claude/Gemini/Hermes 导入、兑换码售卖、闲鱼发货履约、补号助手、余额预警和 JSON 兜底。

### 文件变更
- `Makefile` — 新增 `new-api-up`、`new-api-down`、`frist-api-newapi-setup`，并让 `frist-api-up/down` 管理 New-API + Frist-API 全链路。
- `docker-compose.frist-api.yml` / `docker-compose.newapi.yml` — 固定 New-API 镜像与 Docker 内部服务地址，Frist-API 默认桥接 `new-api` 服务名。
- `scripts/setup_local_newapi_bridge.mjs` — 从 `data/newapi/one-api.db` 读取可用用户 access token，写入本机 `.env` 且不回显密钥。
- `apps/frist-api/server/newApiBridge.js` / `apps/frist-api/server/server.js` — 接管 New-API 用户看板、Token、用量、兑换和可选网关代理。
- `apps/frist-api/tests/new-api-adapter.test.mjs` / `apps/frist-api/tests/server.test.mjs` — 覆盖 New-API 业务桥接、wildcard 模型限制、网关代理和生产边界。
- `docs/006-registries.md` / `docs/007-operations.md` / `docs/009-health.md` — 登记本机 New-API 直连启动、环境变量、验证结果和运维边界。

### 验证
- 语法检查：`node --check scripts/setup_local_newapi_bridge.mjs apps/frist-api/server/server.js apps/frist-api/server/newApiBridge.js` → exit 0。
- Frist-API 全量测试：`cd apps/frist-api && node --test tests/*.test.mjs` → `165 passed / 0 failed / 0 skipped`。
- 本机容器：`openclaw-newapi` 使用 `calciumion/new-api:v1.0.0-rc.4` 监听 `127.0.0.1:3000`，`frist-api-server` 监听 `127.0.0.1:3180`，两个容器均 healthy。
- 接口冒烟：`curl http://127.0.0.1:3000/api/status` 返回 `success=true`、`version=v1.0.0-rc.4`、`setup=true`；`curl http://127.0.0.1:3180/api/frist/dashboard` 返回 HTTP 200，游客态 `5` 个充值套餐且不暴露渠道细节。
- 浏览器审计：Playwright 打开 `http://127.0.0.1:3180/`，页面标题 `Frist-API`，控制台 `0 error / 0 warning`；截图为 `output/playwright/frist-api-newapi-login-20260704.png`。

## [2026-07-04] Frist-API 86GameStore 风格后台与兑换/闲鱼履约闭环
> 领域: `frontend` | `backend` | `xianyu` | `docs`
> 影响模块: `Frist-API`, `86GameStore Downstream`, `Redemption Cards`, `Upstream Channel Sync`, `Xianyu Fulfillment`, `CC Switch`
> 关联问题: HI-902

### 变更内容
- 追加按 GitHub 高星克隆方案复核后的高保真外壳：参考 `abi/screenshot-to-code` 的截图转代码工作流，并借鉴 `ColorlibHQ/AdminLTE` 的后台左侧导航骨架；未复制上游私有源码，只复刻公开登录页结构和管理后台信息架构。
- 将 Frist-API 未登录首屏改为更接近 86GameStore 公开登录页的蓝紫渐变、居中白色登录卡、Logo/副标题、邮箱/密码、忘记密码、注册入口和条款提示；登录后仍进入 Frist 工作台。
- 将 Frist-API 用户端和管理端切到 86GameStore 风格浅色后台骨架：左侧工作台导航、白底卡片、青绿色主色，并保留 CC Switch、API Key、测试、使用记录、可用渠道、兑换码和套餐订阅入口。
- 打通兑换码售卖链路：管理端可批量生成卡密，卡密支持 `unused/sold/redeemed/disabled` 状态，用户端兑换后自动到账并防重复兑换。
- 新增 86GameStore 上游渠道同步接口和管理区块：只保存脱敏渠道状态、模型、延迟和倍率；默认下游售卖倍率在上游倍率基础上 `+0.1`，例如 Plus `0.18 → 0.28`，并修复刷新后倍率回退的问题。
- 新增闲鱼自动发货雏形：后台输入闲鱼订单号和商品套餐后自动分配未售出卡密、标记已发货并生成发货话术；买家完成兑换后履约记录自动标记已兑换。
- 补充本轮产品规格文档，明确当前可实现的是“第三方平台卖兑换码 + Frist-API 核销到账 + 后台履约提醒”，真实闲鱼下单检测仍需后续用户授权登录态后接入。

### 文件变更
- `apps/frist-api/index.html` / `apps/frist-api/admin.html` / `apps/frist-api/src/styles.css` — 86GameStore 公开登录页风格复刻、AdminLTE 式管理端左侧导航、兑换/渠道/闲鱼管理区块和 CC Switch 新皮肤防溢出样式。
- `apps/frist-api/src/app.js` — 增加登录态数据属性和登录表单镜像同步，保证未登录登录页与原账户弹窗共用同一套登录/注册逻辑。
- `apps/frist-api/src/core.js` / `apps/frist-api/server/server.js` — 上游渠道倍率加价、脱敏同步、兑换码状态、闲鱼履约分配和兑换反写逻辑。
- `apps/frist-api/src/admin.js` — 管理端接入渠道同步、卡密生成、闲鱼履约和新状态展示。
- `apps/frist-api/tests/core.test.mjs` / `apps/frist-api/tests/server.test.mjs` / `apps/frist-api/tests/business-flow.test.mjs` — 补齐倍率、渠道同步、兑换/闲鱼闭环和新皮肤回归。
- `docs/050-frist-api-86game-clone-commerce-plan.md` / `docs/003-docs-index.md` — 新增并注册本轮产品规格。
- `docs/002-changelog.md` / `docs/009-health.md` — 同步本轮交付和验证状态。

### 验证
- 语法检查：`cd apps/frist-api && node --check src/admin.js && node --check src/app.js && node --check src/core.js && node --check server/server.js` → exit 0。
- Frist-API 全量测试：`cd apps/frist-api && node --test tests/*.test.mjs` → `165 passed / 0 failed / 0 skipped`。
- 本地浏览器审计：`FRIST_API_PORT=3186 ... npm start` 后，Playwright 打开 `http://127.0.0.1:3186/` 和 `http://127.0.0.1:3186/admin.html?code=local-audit`；用户页控制台 `Errors: 0, Warnings: 0`，管理页预置本地令牌后控制台 `Errors: 0, Warnings: 0`。
- 截图证据：`output/playwright/frist-api-clone-login-20260704.png`、`output/playwright/frist-api-admin-clone-shell-20260704.png`；上一轮工作台截图仍保留在 `output/playwright/frist-api-user-dashboard.png`、`output/playwright/frist-api-admin-clean-authenticated.png`。

## [2026-07-03] Frist-API Oracle 生产迁移与域名/R2 收口
> 领域: `backend` | `deploy` | `infra` | `docs`
> 影响模块: `Frist-API`, `New-API Bridge`, `Oracle ARM`, `Cloudflare DNS`, `R2 Backup`, `GitHub Actions`
> 关联问题: TD-006, TD-007, TD-014, TD-015, HI-856, HI-857

### 变更内容
- 按 Carven 授权执行生产 New-API 迁移：用户、余额/订单、兑换码和日志已写入生产 New-API 数据库，Frist-API 生产环境启用 New-API adapter，并保留带时间戳回滚目录。
- 对历史 `enc:v1:` 用户 Key 采取安全跳过策略：旧数据加密密钥未能在本地、VPS-Config 或服务器常规备份中找到，不能把密文伪造成可用 Key；前端/服务端会把这类 Key 标记为需重新生成。
- 复用 VPS-Config 的 Cloudflare/R2 资产并完成 Oracle ARM 切流：`frist-api.245334.xyz` 的 Cloudflare proxied A 已切到 Oracle ARM `150.136.73.15`，源站由 Apache + Cloudflare Origin CA 反代到 Frist-API `127.0.0.1:3180`；New-API 以 ARM64 二进制 systemd 运行在 `127.0.0.1:13000`；R2 备份脚本、root-only env、systemd timer 已在 Oracle 启用并完成手动上传验证。
- 修正生产 SMTP 边界并完成落地：代码和文档只登记变量名，不写入聊天里出现过的 SMTP 密码；密码通过本机隐藏输入框写入 Oracle root-only 环境文件，Gmail 465/TLS 生产测试邮件返回 `smtp_test=sent`。
- 补齐提交前门禁：根目录 `.venv312` 软链加入忽略规则，避免误把本机 Python 环境提交；Python 依赖审计改用项目 Python 3.12 环境，避免系统 Python 3.9 误判 `requests>=2.33.0` 不可解析；gitleaks 历史误报通过指纹 allowlist 收口。

### 文件变更
- `docs/002-changelog.md` — 记录生产迁移、R2、Cloudflare 和 SMTP 安全边界。
- `docs/006-registries.md` — 更新 Frist-API 网关地址、New-API 迁移入口和回滚目录状态。
- `docs/007-operations.md` — 更新生产入口、New-API 已迁移、R2 已启用、SMTP 隐藏输入落地和 Cloudflare proxied A 方案。
- `docs/009-health.md` — 更新 TD-006 / TD-007 和当前系统状态。
- `.gitignore` — 忽略根目录 `.venv312` 虚拟环境软链。
- `.gitleaksignore` — 只忽略两个历史误报指纹，保留默认 secret 扫描规则。

### 验证
- New-API 数据迁移：`/opt/frist-api` apply 结果为 `migrated_users=19`、`tokens=1`、`frist_topups=4`、`redemptions=2`、`logs=162`；New-API 迁移回滚目录 `/opt/frist-api/backups/newapi-migration-20260703T005433Z`。
- Oracle 生产健康：`ssh oracle-arm1 systemctl is-active frist-api.service openclaw-newapi.service apache2 frist-api-r2-backup.timer` → 4 个 `active`；`systemctl --failed` → `0 loaded units listed`；Oracle 本机 `127.0.0.1:3180/api/frist/dashboard` → HTTP 200，`127.0.0.1:13000/api/status` → HTTP 200。
- 公网入口：`curl https://frist-api.245334.xyz/api/frist/dashboard` 连续 3 次 → `200/200/200`，耗时约 `0.65s`；未授权 `curl https://frist-api.245334.xyz/v1/models` 连续 3 次 → `401/401/401`。最新外网压测 Dashboard `100/100` 为 HTTP 200（p50 `0.648s` / p95 `0.792s`），未授权 models `50/50` 为 HTTP 401（p50 `0.670s` / p95 `0.758s`）。
- R2 备份：Oracle `frist-api-r2-backup.timer` 为 active，最近手动备份日志包含 `backup_ok ... http=200`；旧腾讯云 `frist-api-r2-backup.timer` 已 disabled/inactive，避免双源备份漂移。
- 腾讯冷回滚：`root@101.43.41.96 docker ps -a` 显示旧 `frist-api-server` 与 `openclaw-newapi` 已停止，`/opt/frist-api` 与备份目录保留；旧 `http://frist-api.101-43-41-96.nip.io` 当前不作为生产入口。
- DNS/HTTPS：`frist-api.245334.xyz` 通过 Cloudflare proxied A 对外返回 Cloudflare Anycast IP，源站记录已在 VPS-Config 登记为 Oracle `150.136.73.15`；公网 HTTPS Dashboard 冒烟 HTTP 200。
- SMTP：Oracle `/etc/frist-api/frist-api.env` 与兼容 `/opt/frist-api/.env` 已设置 Gmail SMTP，Frist-API 重启后 active；生产测试邮件返回 `smtp_test=sent`。
- 依赖安全：`.venv312/bin/python -m pip_audit -r packages/clawbot/requirements.txt -r packages/clawbot/requirements-dev.txt --vulnerability-service pypi --progress-spinner off --cache-dir /tmp/openclaw-pip-audit-cache --timeout 10` → `No known vulnerabilities found`；`.venv312/bin/python -m pip check` → `No broken requirements found`；可提交文件 gitleaks 与 `gitleaks git . --redact --log-level error` 均返回 0。

## [2026-07-02] OpenClaw Bot / Frist-API 全面收口
> 领域: `backend` | `frontend` | `ai-pool` | `infra` | `docs` | `social` | `xianyu`
> 影响模块: `Frist-API`, `AI Pool`, `New-API Bridge`, `ClawBot`, `WeChat Bridge`, `Social Guardrails`, `GitHub Actions`, `Docs`
> 关联问题: HI-812, HI-817, HI-818, HI-856, HI-857, HI-887, HI-890, HI-896, TD-001, TD-002, TD-003, TD-004, TD-005, TD-006, TD-007, TD-008, TD-014, TD-015, TD-016, TD-017

### 变更内容
- AI_POOL 收口：余额站/86GameStore 类渠道新增日消费限额、慢线阈值、成本敏感标记、当日消费超剩余额且慢线自动熔断、真实调用 503/401 自动降级、清理会话粘滞和一次性告警，避免面板继续展示失效渠道。
- Frist-API 模型目录收口：客户可见模型只来自健康上游 `/v1/models` 或真实探测，硬编码目录只用于后台审计排序；New-API wildcard-only token 不再膨胀成客户可见模型。
- Frist-API 生产边界按最新运营决策改为“固定 HTTPS + New-API + 管理员 2FA + 兑换码收款闭环 + 备份/SLA”，微信/支付宝/Stripe 自动支付保留为未来备用，不再作为当前上线硬门槛。
- New-API 迁移脚本新增 dry-run/package/rollback：生成 runtime 备份、幂等迁移计划和回滚脚本；`--apply` 仍阻塞在人工确认执行窗口，不直接写生产库。
- ClawBot 后端收口：`/cli` 正式注册；微信编号命令可接内部只读 API 的全部映射到真实 GET 路由，交易/发文/发货/导出等高风险入口明确转人工确认；iLink token 失效时给出重新扫码提示和一次性告警。
- Frist-API 架构收口：已把邮件发送、SMTP DNS 轮询、注册/重置/余额预警邮件模板和邮箱归一化抽到 `server/email.js`，`server.js` 从 7881 行降到 7247 行；核心网关/账号路由仍保留在主入口，避免本轮为追求拆分引入生产行为风险。
- 依赖和安全门禁收口：升级 Python 依赖安全下限，默认移出高风险/冲突可选依赖并保持 graceful degradation；CI 新增 Gitleaks、npm audit high、pip-audit 门禁，并升级 `actions/cache@v6`、`actions/setup-python@v6`、`astral-sh/setup-uv@v8.2.0`。
- 社媒边界保持克制：只做工程质量和文档收口，继续保持待审草稿、只读采集、人工最终确认；没有恢复自动发布、评论、关注、私信、点赞或推广。
- 运维文档同步：域名/Cloudflare/R2 改为复用 `/Users/blackdj/Documents/VPS-Config` 既有资产；收款主路径改为闲鱼等第三方平台售卖兑换码 + Frist-API 核销；AGPL 源码入口已在 Frist-API 页脚暴露现有 GitHub 仓库链接。

### 文件变更
- `.github/workflows/ci.yml` — 增加 secret/audit 安全门禁并升级 GitHub Actions 运行时。
- `apps/frist-api/server/server.js` / `apps/frist-api/server/email.js` / `apps/frist-api/server/shared.js` / `apps/frist-api/server/catalog.js` / `apps/frist-api/server/newApiBridge.js` — AI_POOL 熔断、模型目录、New-API 桥接、邮件模块拆分和生产边界收口。
- `apps/frist-api/src/core.js` / `apps/frist-api/src/app.js` / `apps/frist-api/index.html` / `apps/frist-api/src/styles.css` — 客户可见模型、AGPL 源码入口和前端状态文案同步。
- `scripts/frist_api_newapi_migration_dry_run.mjs` / `apps/frist-api/tests/migration.test.mjs` — New-API 迁移演练、备份和回滚包。
- `packages/clawbot/src/bot/multi_bot.py` / `packages/clawbot/src/bot/cmd_cli_mixin.py` — `/cli` 正式注册。
- `packages/clawbot/src/api/routers/wechat.py` / `packages/clawbot/src/wechat_bridge.py` — 微信编号命令真实 API 映射、危险动作转人工、iLink 失效提示和告警。
- `packages/clawbot/requirements.txt` / `packages/clawbot/pytest.ini` — 依赖安全下限和第三方 warning 隔离。
- `docs/006-registries.md` / `docs/007-operations.md` / `docs/009-health.md` — 注册表、运维和健康状态同步。

### 验证
- Frist-API：`cd apps/frist-api && node --test tests/core.test.mjs tests/server.test.mjs tests/migration.test.mjs tests/new-api-adapter.test.mjs tests/business-flow.test.mjs` → `161 passed / 0 failed / 0 skipped`；拆分邮件模块后 `tests/server.test.mjs` 单跑 → `92 passed / 0 failed`。
- 后端：`cd packages/clawbot && .venv312/bin/python -m pytest tests/ -o addopts='' --tb=short` → `1606 passed / 2 skipped / 0 failed`。
- 质量门禁：`make lint` → `All checks passed!`；桌面端 `npx tsc --noEmit && npm run lint && npm run build` → exit 0；`npm audit --audit-level=high --omit=dev`（桌面端、Frist-API）均 `found 0 vulnerabilities`；`pip check` → `No broken requirements found`；`pip-audit` → `No known vulnerabilities found`；tracked-tree `gitleaks detect --redact --no-git` → `no leaks found`；社媒真实浏览器 smoke → X/小红书/闲鱼 `buttonClicks=0`、`auto_publish_enabled=false`、`external_actions_locked=true`；`git diff --check` → exit 0。


## [2026-07-02] 社媒运营插件排程与增长复盘收口
> 领域: `backend` | `frontend` | `social` | `docs` | `infra`
> 影响模块: `OpenClaw Manager`, `Chrome Social Pilot`, `Social API`, `Telegram Commands`, `Execution Scheduler`, `Docs`
> 关联问题: TD-016, TD-017, HI-885

### 变更内容
- 收口社媒运营三端闭环：桌面端 Social 中控、Chrome 插件 Popup/Options、Telegram 命令与后端 API 统一支持人设确认、no-code 运营打法、当前页上下文扫描、增长复盘、增长反馈反哺待审草稿、待发布排程和最终人工确认。
- 安全边界保持不变：所有新增链路只生成/编辑/审核/排程草稿，不自动发布、不自动评论、不关注/私信、不调用推广/boost；网页登录额度入口仅复制提示词并打开模型网页，不自动提交。
- 清理失效生活自动化/微信优惠券相关冗余入口和旧 MITM token 脚本，避免继续保留不可维护、依赖短有效期凭证的功能路径。
- 修复 `gptoss` 启动超时后的心跳误报，避免未真正启动的 Bot 残留在健康检查和群聊路由里。
- 文档同步更新架构、注册表、运维、健康页和功能规格，并补充本轮提交前验证结果。

### 文件变更
- `apps/openclaw-manager-src/` — Social 中控、Tauri IPC/API、i18n 与静态测试同步更新。
- `packages/openclaw-npm/assets/chrome-extension/` — 新增/更新 Popup、Background、Options、共享 social-core、页面 runner 与插件测试。
- `packages/clawbot/src/api/routers/social.py` / `packages/clawbot/src/api/rpc.py` — 社媒工作台、插件状态、草稿、排程、增长复盘和最终确认 API 收口。
- `packages/clawbot/src/bot/` / `packages/clawbot/multi_main.py` / `packages/clawbot/src/social_scheduler.py` — Telegram 命令、中文自然语言入口、Bot 启动健康注册和调度安全闸口同步。
- `packages/clawbot/src/execution/social/` — 新增社媒人设确认和 X 自动运营辅助模块。
- `packages/clawbot/scripts/mitm_token_addon.py` / `packages/clawbot/src/execution/wechat_coupon.py` — 删除失效冗余实现。
- `docs/004-architecture.md` / `docs/006-registries.md` / `docs/007-operations.md` / `docs/009-health.md` / `docs/010-feature-specs.md` — 同步本轮系统状态和操作边界。

### 验证
- CLEANUP: `git diff --check` → exit 0；`docs/` 无子目录且编号命名合法；未发现 pyc/log/tmp/DS_Store 等生成物进入未跟踪列表；敏感格式扫描 `secret_like_hits=[]`。
- BACKEND: `cd packages/clawbot && .venv312/bin/python -m py_compile <changed-python-files>` → exit 0；`cd packages/clawbot && .venv312/bin/python -m pytest tests/ --tb=short -q` → exit 0，进度日志统计 `1601 passed / 2 skipped / 0 failed`。
- FRONTEND: `cd apps/openclaw-manager-src && npm run build` → `tsc && vite build` 成功；`cd apps/openclaw-manager-src/src-tauri && cargo check` → exit 0。
- PLUGIN: `node apps/openclaw-manager-src/src/components/Social/social-growth-feedback.static.test.mjs` → `5 passed`；`node packages/openclaw-npm/assets/chrome-extension/test/*.mjs` → Popup 静态 `26 passed`、social-core `31 passed`、page-runner `10 passed`，真实浏览器 smoke 返回 `ok=true` 且 `auto_publish_enabled=false` / `external_actions_locked=true`。
- RUNTIME: 本机 `ai.openclaw.clawbot-agent` 重启后，`GET /api/v1/status` 显示 7 个 Bot 均 `alive=true`，新日志 `gptoss 未注册重启函数=0`、`Bot 心跳丢失=0`。

## [2026-07-02] 修复 gptoss 启动失败后的心跳误报
> 领域: `backend` | `infra` | `docs`
> 影响模块: `MultiBot`, `HealthChecker`, `ChatRouter`, `LaunchAgent`
> 关联问题: HI-885

### 变更内容
- 修复 Bot 启动流程里的注册时机：只有 Telegram polling 真正启动成功后，才把 Bot 写入健康检查和群聊路由。
- 避免 gptoss 这类 Bot 在启动超时或缺 Token 时残留成“健康检查里存在、运行注册表里不存在”的假实例，导致持续出现“Bot 心跳丢失 / 未注册重启函数”告警。
- 新增回归测试覆盖“缺 Token 启动失败不残留健康心跳或路由”的场景。
- 已重启本机 `ai.openclaw.clawbot-agent`，gptoss 重新上线，当前 7 个 Bot 均为 alive。

### 文件变更
- `packages/clawbot/src/bot/multi_bot.py` — 将健康/路由注册移动到启动成功后执行。
- `packages/clawbot/tests/test_multibot_startup_registration.py` — 新增启动失败残留注册回归测试。
- `docs/002-changelog.md` / `docs/009-health.md` — 记录本轮告警处置和验证结果。

### 验证
- RED: `cd packages/clawbot && .venv312/bin/python -m pytest tests/test_multibot_startup_registration.py -q` → 新测试先失败，复现构造时提前注册的问题。
- GREEN: `cd packages/clawbot && .venv312/bin/python -m py_compile src/bot/multi_bot.py src/monitoring/health.py multi_main.py && .venv312/bin/python -m pytest tests/test_multibot_startup_registration.py tests/test_chat_router.py tests/test_monitoring_module.py -q` → `31 passed`，仅历史依赖 warning。
- FULL: `cd packages/clawbot && .venv312/bin/python -m pytest tests/ --tb=short -q` → exit 0；进度日志统计 `1601 passed / 2 skipped / 0 failed`，仅历史依赖和调度测试 coroutine warning。
- RUNTIME: `launchctl kickstart -k gui/$(id -u)/ai.openclaw.clawbot-agent` 后，`GET /api/v1/status` 显示 `qwen235b/gptoss/claude_sonnet/claude_haiku/deepseek_v3/claude_opus/free_llm` 均 `alive=true`；新日志中 `gptoss 未注册重启函数=0`、`Bot 心跳丢失=0`。

## [2026-07-01] 下线失效生活自动化任务
> 领域: `backend` | `docs` | `infra`
> 影响模块: `Telegram Commands`, `Execution Scheduler`, `LaunchAgent`, `Docs`
> 关联问题: TD-018

### 变更内容
- 因该生活自动化任务依赖短有效期凭证且恢复成本过高，已从项目中下线。
- 移除对应 Telegram 手动命令、中文自然语言触发、Bot 进程内定时调度、独立本机定时脚本和本机 LaunchAgent，避免继续发送相关 Telegram 通知。
- 清理示例配置、注册表、运维手册和健康页中的历史方案细节，只保留本条泛化下线记录。

### 文件变更
- Bot 命令、帮助菜单、中文自然语言入口、执行调度器、控制面板任务项、已失效实现、专用脚本、专用测试、示例配置与项目文档均已同步清理。

### 验证
- GREEN: `cd packages/clawbot && ./.venv312/bin/python -m py_compile multi_main.py src/bot/cmd_intel_mixin.py src/bot/multi_bot.py src/bot/chinese_nlp_mixin.py src/bot/cmd_basic/help_mixin.py src/bot/workflow_mixin.py src/bot/callback_mixin.py src/execution/scheduler.py src/api/routers/controls.py src/api/routers/wechat.py src/api/rpc.py src/api/schemas.py src/http_client.py src/ocr_router.py src/shopping/blackfriday_scanner.py src/shopping/crawl4ai_engine.py config/prompts.py` → exit 0。
- GREEN: `cd packages/clawbot && ./.venv312/bin/python -m pytest tests/test_api_routes_regression.py tests/test_social_scheduler.py tests/test_newapi_router.py -q --tb=short` → `52 passed`，仅 requests/js2py 依赖 warning。
- INFRA: 本机 LaunchAgent 检查确认已失效任务不存在。
- CLEANUP: 已删除旧状态/日志文件和本机旧临时文件；未读取或输出任何凭证明文。



## [2026-06-22] 收口 Dependabot 依赖安全告警
> 领域: `frontend` | `backend` | `docs` | `infra`
> 影响模块: `OpenClaw Manager`, `WorldMonitor`, `Dependabot`, `openclaw-npm`, `Weixin Extension`, `ClawBot Dev Requirements`
> 关联问题: OSS review hardening

### 变更内容
- 处理打开 Dependabot 后暴露的依赖安全告警：升级 `.openclaw/extensions/openclaw-weixin` 的 Vitest 相关 lockfile，并用 overrides 固定 `glob`、`brace-expansion`、`esbuild` 安全版本。
- 桌面端 `apps/openclaw-manager-src` 移除 `react-simple-maps`，改用 `d3-geo` + `topojson-client` 直接渲染本地 `countries-110m.json`，清理旧 d3 漏洞链；同步升级 `vite`、`postcss` 和多项传递依赖 overrides。
- 升级 `packages/clawbot/requirements-dev.txt` 中 `pytest` 到 `>=9.0.3,<10.0`，并配套升级 `pytest-asyncio` 到 `>=1.4.0,<2.0`。
- 收口 `packages/openclaw-npm` 及扩展包中的 `hono`、`undici`、`markdown-it`、`tar`、`@opentelemetry/sdk-node` 等安全补丁版本，并移除源码未直接使用且上游暂无 patched version 的 `@mariozechner/pi-coding-agent` 直接依赖。
- 同步 `docs/006-registries.md` 和 `docs/009-health.md`，登记本轮依赖安全处理范围与验证结果。
- 修复 `test_api_routes_regression.py` 在全量测试中被本机 `OPENCLAW_API_TOKEN` / `.env` 污染后返回 401 的测试隔离问题，确保 API route 回归测试固定运行在无 Token 开发模式。

### 文件变更
- `.openclaw/extensions/openclaw-weixin/package.json` / `package-lock.json` — 升级测试相关依赖并收口传递漏洞。
- `apps/openclaw-manager-src/package.json` / `package-lock.json` — 替换地图依赖，升级构建依赖并添加安全 overrides。
- `apps/openclaw-manager-src/src/components/WorldMonitor/index.tsx` — 地图改为 `d3-geo` + `topojson-client` 渲染。
- `packages/clawbot/requirements-dev.txt` — 升级 `pytest` / `pytest-asyncio`。
- `packages/openclaw-npm/package.json`、`packages/openclaw-npm/extensions/*/package.json` — 收口 Node 安全依赖。
- `packages/clawbot/tests/test_api_routes_regression.py` — 增加 API 鉴权环境隔离 fixture，避免本机密钥污染回归测试。
- `docs/002-changelog.md` / `docs/006-registries.md` / `docs/009-health.md` — 记录依赖安全收口。

### 验证
- `cd .openclaw/extensions/openclaw-weixin && npm audit --audit-level=moderate` → `found 0 vulnerabilities`。
- `cd apps/openclaw-manager-src && npm audit --audit-level=moderate` → `found 0 vulnerabilities`。
- `cd apps/openclaw-manager-src && npx tsc --noEmit` → 退出码 0。
- `cd apps/openclaw-manager-src && npm run build` → 退出码 0，Vite build 成功。
- `cd packages/clawbot && .venv312/bin/python -m pip check` → `No broken requirements found`。
- `cd packages/clawbot && OPENCLAW_API_TOKEN=demo .venv312/bin/python -m pytest tests/test_api_routes_regression.py -q --tb=short` → `12 passed`。
- `git diff --check` → 退出码 0。

## [2026-06-22] 补齐开源社区行为准则
> 领域: `docs` | `infra`
> 影响模块: `OSS Governance`, `README`, `Docs Index`
> 关联问题: OSS review hardening

### 变更内容
- 新增 `docs/015-code-of-conduct.md`，明确 issue、PR、Discussions 和安全报告中的友善协作、脱敏、禁止绕过平台规则和执行方式。
- 在 `README.md` 贡献入口加入行为准则链接，让外部贡献者在提交 issue / PR 前能看到社区规则。
- 更新 `docs/003-docs-index.md`，登记新增编号文档并保持 `docs/` 根目录扁平编号治理。

### 文件变更
- `docs/015-code-of-conduct.md` — 新增社区行为准则。
- `README.md` — 贡献入口增加行为准则链接。
- `docs/003-docs-index.md` — 登记新增文档。
- `docs/002-changelog.md` / `docs/009-health.md` — 记录本轮 OSS 治理补齐。

### 验证
- `find docs -maxdepth 2 -type d -print` → `docs` 下无子目录。
- `find docs -maxdepth 1 -type f -name '*.md' -exec basename {} \; | sort` → 新增文档为编号英文名。
- `git diff --check -- README.md docs/003-docs-index.md docs/015-code-of-conduct.md docs/002-changelog.md docs/009-health.md` → 退出码 0。

## [2026-06-22] 收口 OSS 审核前安全设置
> 领域: `docs` | `infra`
> 影响模块: `GitHub Repository`, `Security Settings`, `Local Git Refs`
> 关联问题: OSS review hardening

### 变更内容
- 开启 GitHub Dependabot security updates，让公开依赖告警后续可以自动生成安全修复 PR。
- 开启 GitHub private vulnerability reporting，让外部研究者可以通过私密入口报告漏洞，避免把敏感复现细节发到公开 issue。
- 清理本地仅存在的旧分支和 Codex 快照 ref，避免后续误推历史实验分支造成重复审核噪音。
- 二次清理本地可重建缓存、根目录临时截图和 Playwright 临时目录；运行配置、依赖环境、runtime 数据和生产备份继续保留。

### 文件变更
- `docs/002-changelog.md` — 记录本轮 OSS 审核前安全设置收口。
- `docs/009-health.md` — 更新公开仓库安全状态。

### 验证
- `gh api repos/djblack1209-coder/OpenClaw-Bot --jq '.security_and_analysis'` → `dependabot_security_updates=enabled`、`secret_scanning=enabled`、`secret_scanning_push_protection=enabled`。
- `gh api repos/djblack1209-coder/OpenClaw-Bot/private-vulnerability-reporting --jq '.'` → `{"enabled":true}`。
- `gh api repos/djblack1209-coder/OpenClaw-Bot/secret-scanning/alerts --paginate --jq '[.[] | select(.state=="open")] | length'` → `0`。
- `gh api repos/djblack1209-coder/OpenClaw-Bot/dependabot/alerts --paginate --jq '[.[] | select(.state=="open")] | length'` → `0`。
- `git for-each-ref --format='%(refname)' refs/heads refs/remotes refs/tags refs/stash refs/codex` → 仅剩 `main` 和 `origin/main` 相关 refs。
- `git fsck --full --unreachable --no-reflogs` → 无残留不可达对象输出。

## [2026-06-22] 补齐开源项目审核材料
> 领域: `docs` | `infra`
> 影响模块: `OSS Governance`, `README`, `Security Policy`
> 关联问题: Codex for OSS application readiness

### 变更内容
- 根目录新增 Apache-2.0 `LICENSE`，把项目从 README 中的私有/专有表述改为公开开源项目，提升 OpenAI Codex for OSS 等开源项目审核的一致性。
- 重写根 `README.md`：补充项目定位、可复用开源价值、技术栈、启动方式、文档入口、贡献入口和安全/合规边界。
- 新增 `docs/013-contributing.md` 和 `docs/014-security.md`：提供贡献流程、PR 验证清单、漏洞报告方式、密钥保护规则，以及赞助 API credits 只能用于 PR review、测试、文档、安全分析和重构维护的边界。
- 新增 GitHub issue/PR 模板，并用 GitHub CLI 更新仓库公开描述、topics、Discussions、secret scanning 和 push protection，提升社区资料完整度和密钥误提交防护。
- 同步 `docs/003-docs-index.md`，登记新增文档编号，继续遵守 `docs/` 扁平编号规则。

### 文件变更
- `LICENSE` — 新增 Apache License 2.0 根许可证。
- `README.md` — 改为开源友好的项目说明和安全边界。
- `docs/013-contributing.md` — 新增贡献指南。
- `docs/014-security.md` — 新增安全政策。
- `.github/ISSUE_TEMPLATE/bug_report.yml` / `.github/ISSUE_TEMPLATE/feature_request.yml` / `.github/ISSUE_TEMPLATE/config.yml` — 新增 GitHub issue 模板和安全报告入口。
- `.github/pull_request_template.md` — 新增 PR 验证与安全检查模板。
- `docs/003-docs-index.md` — 登记新增文档。
- `docs/009-health.md` — 记录 OSS 审核准备状态。

### 验证
- `find docs -maxdepth 1 -type f -name '*.md' -exec basename {} \\; | sort` → 确认新增文档均在 `docs/` 根目录且编号命名。
- `grep -n "Private / Proprietary" README.md LICENSE docs/013-contributing.md docs/014-security.md docs/003-docs-index.md docs/009-health.md` → 无旧私有许可证表述残留。
- `git diff --check -- LICENSE README.md docs/013-contributing.md docs/014-security.md docs/003-docs-index.md docs/002-changelog.md docs/009-health.md .github/ISSUE_TEMPLATE/bug_report.yml .github/ISSUE_TEMPLATE/feature_request.yml .github/ISSUE_TEMPLATE/config.yml .github/pull_request_template.md` → 退出码 0。
- `gh repo view djblack1209-coder/OpenClaw-Bot --json nameWithOwner,description,isPrivate,repositoryTopics,hasIssuesEnabled,hasDiscussionsEnabled` → 仓库公开、Issues/Discussions 已开启，topics 已包含 `ai-agents`、`telegram-bot`、`fastapi`、`tauri`、`react`、`llm-routing`、`open-source`、`automation`。
- `gh api repos/djblack1209-coder/OpenClaw-Bot --jq '{security_and_analysis:.security_and_analysis}'` → `secret_scanning=enabled`、`secret_scanning_push_protection=enabled`。

## [2026-05-09] Frist-API 319px 移动端批注修复
> 领域: `frontend` | `deploy` | `docs`
> 影响模块: `Frist-API`, `User Console`, `CC Switch`, `Tencent Cloud`, `docs`
> 关联问题: HI-901

### 变更内容
- 修复 319px 极窄屏顶栏遮挡：顶栏拆成品牌行和操作行，语言、连接状态点、登录余额按钮在第二行网格内排布，去掉 `body min-width: 320px` 造成的 319px 横向溢出。
- 修复工作台折叠菜单箭头溢出：移动端 `.rail-toggle` 改为相对定位并把箭头固定在按钮右侧安全区内，展开/收起旋转不再跑出容器。
- 优化 Dashboard 空状态：模型消耗空饼图改为带分段提示的空态环，并明确“暂无真实请求”；异常卡说明检测余额突增、失败率、慢请求和异常模型消耗；通道卡说明 60 秒巡检和登录创建 Key 后展示号池状态。
- 收口语言切换行为：按钮继续切换 `html.lang` 和偏好状态，但明确提示“仅切换语言偏好”，不再让用户误以为已完成全站中英文翻译。
- 修复 CC Switch 319px 比例和裁切：目标按钮改为两列，导入说明、用量查询、模型导出和代码片段统一 `min-width: 0` / `overflow-wrap: anywhere`，避免教程和模型列表横向撑破屏幕。
- 已用 319×718 浏览器回测 Dashboard 与 CC Switch：本地 `scrollWidth=319`，顶栏账户按钮宽度 173px，CC Switch 主内容宽 281px、用量说明宽 235px，无横向溢出。
- 已同步部署到腾讯云 `/opt/frist-api`，部署前备份为 `/opt/frist-api/backups/frist-api-mobile-319-20260509-045253-before-f2d6eda.tgz`；远端 `node --check` 和批注聚焦测试 57/57 通过，`frist-api-server` 重启后 healthy，公网首页 200、Dashboard 200、未授权 `/v1/models` 401，公网 319×718 Dashboard/CC Switch 复验 `scrollWidth=319`。

### 文件变更
- `apps/frist-api/index.html` — 增加语言状态辅助文本、Dashboard 卡片说明文案，并更新资源版本。
- `apps/frist-api/src/app.js` — 丰富消耗、异常、通道空状态，语言切换改为诚实提示偏好状态。
- `apps/frist-api/src/styles.css` — 增加 319px 移动端护栏，修复顶栏、折叠菜单箭头、空饼图和 CC Switch 横向裁切。
- `apps/frist-api/tests/core.test.mjs` / `apps/frist-api/tests/business-flow.test.mjs` — 增加 319px 顶栏、箭头、空态、语言状态和 CC Switch 宽度回归断言。
- `docs/002-changelog.md` / `docs/006-registries.md` / `docs/009-health.md` — 同步本轮移动端批注修复和登记 HI-901。

## [2026-05-09] Frist-API 工作台批注修复
> 领域: `frontend` | `deploy` | `docs`
> 影响模块: `Frist-API`, `User Console`, `Tencent Cloud`, `docs`
> 关联问题: HI-900

### 变更内容
- 恢复用户端原抽象品牌 Logo：顶部不再显示单字母 `F` 占位，改回红白斜切品牌标，防止 Tabcode 皮肤覆盖 Frist-API 识别。
- 修复 Token 趋势图交互：折线图增加透明热区、键盘聚焦点位和 `data-trend-tooltip` 数据浮层，鼠标移入图表即可看到日期与 Token 数值。
- 收口工作台布局：左侧导航固定为同一个工作台栏，`API Key`、趋势、记录、模型、资料和 CC Switch 等页面都在右侧 `workspace-content` 内切换，不再像单独页面脱离导航。
- 降低当前导航项视觉噪音：首页选中态从蓝色大背景改为细线和文字提示，保留 `aria-current="page"` 给辅助技术识别。
- 补充回归护栏：测试锁定 Logo 不可退回 `F` 字母、工作台内容必须在右侧区域切换、趋势图必须具备 hover 数据钩子。
- 已同步部署到腾讯云 `/opt/frist-api`，部署前备份为 `/opt/frist-api/backups/frist-api-workbench-comments-20260509-035316-before-385bfce.tgz`；远端容器 `frist-api-server` 重启后 healthy，公网首页 200、Dashboard 200、未授权 `/v1/models` 401。

### 文件变更
- `apps/frist-api/index.html` — 恢复品牌标结构，新增 `workspace-content` 右侧内容容器，并更新资源版本。
- `apps/frist-api/src/app.js` — 新增趋势图 hover/键盘聚焦数据点和浮层渲染。
- `apps/frist-api/src/styles.css` — 固定工作台左侧导航、恢复红白斜切 Logo、移除当前项大块背景、补趋势图热区与浮层样式。
- `apps/frist-api/tests/core.test.mjs` / `apps/frist-api/tests/business-flow.test.mjs` — 增加批注回归断言。
- `docs/002-changelog.md` / `docs/006-registries.md` / `docs/009-health.md` — 同步本轮批注修复和登记 HI-900。

## [2026-05-09] Frist-API 移动端管理员入口补齐与上游 Key 自动巡检
> 领域: `frontend` | `backend` | `ai-pool` | `infra` | `docs`
> 影响模块: `Frist-API`, `User Console`, `Gateway Monitor`, `Alerting`, `docs`
> 关联问题: HI-896, HI-899, TD-013

### 变更内容
- 补齐移动端管理员操作入口：顶栏常驻 `登录/身份码/管理` 快捷按钮，游客可直接打开登录弹窗，登录未激活管理员时一键打开身份码输入框，已激活后直达管理页，避免入口仅藏在账户弹窗底部。
- 新增后台通道巡检队列：支持按 60 秒间隔自动探测健康库存，即使无人请求也会刷新通道状态并回写连通性数据。
- 用户端首页新增 60 秒静默刷新，看板连通性与后台巡检保持同频更新，无需手动点“检测”才看到降级结果。
- 新增上游 Key 自动降级与一次性补号提醒：巡检或网关请求发现认证失败/额度耗尽时自动禁用对应 Key，支持 Telegram Bot 或 Webhook 告警，单 Key 同类问题只提醒一次，避免重复通知。
- 巡检过程会保留可用通道并更新路由字段与延迟数据，用户侧继续按健康库存自动切换，不暴露上游密钥和号商细节。

### 文件变更
- `apps/frist-api/index.html` / `apps/frist-api/src/app.js` / `apps/frist-api/src/styles.css` — 新增移动端管理员快捷入口与交互样式。
- `apps/frist-api/server/server.js` — 新增后台 60 秒巡检、Key 异常一次性告警、运行时告警去重存储和 Telegram/Webhook 通知。
- `apps/frist-api/tests/server.test.mjs` / `apps/frist-api/tests/core.test.mjs` / `apps/frist-api/tests/business-flow.test.mjs` — 新增巡检降级回归与移动端快捷入口断言。
- `apps/frist-api/deploy/production.env.example` / `docker-compose.frist-api.yml` — 新增通道巡检与 Key 告警环境变量透传。
- `docs/002-changelog.md` / `docs/006-registries.md` / `docs/007-operations.md` / `docs/009-health.md` — 同步本轮功能、运维配置和风险状态。

## [2026-05-09] Frist-API 移动端导航和卡商通道展示修复
> 领域: `frontend` | `backend` | `ai-pool` | `docs`
> 影响模块: `Frist-API`, `User Console`, `Channel Monitor`, `docs`
> 关联问题: HI-898

### 变更内容
- 修复移动端顶栏批注：423px 窄屏下 Logo 收敛为紧凑品牌区，连接状态改为小状态点，不再挤占余额按钮或产生横向溢出。
- 将移动端工作台左侧导航改为默认折叠菜单：点击“工作台导航”展开，进入任一页面后自动收起，并同步当前页标题。
- 通道连通性从模型分类展示改为客户可理解的号池渠道展示：公开卡片显示 `卡商1`、`卡商2` 等渠道名和号池标签，不再展示 `.provider-models` 模型标签。
- 清理延迟 mock 口径：补号导入未显式填写或探测不到真实延迟时落为 `0`，前端展示“等待真实请求更新”，不再用 `999ms/1000ms` 伪造最低/平均延迟。
- 固定监控刷新口径为 60 秒，并在通道聚合里保留 healthy/down/slow 统计，支持同一卡商下快线、慢线、断线的自动降级状态。

### 文件变更
- `apps/frist-api/index.html` / `apps/frist-api/src/styles.css` / `apps/frist-api/src/app.js` — 移动端 Logo、状态灯、折叠菜单和通道卡 UI 修复。
- `apps/frist-api/server/server.js` / `apps/frist-api/server/catalog.js` / `apps/frist-api/src/serverClient.js` / `apps/frist-api/src/newApiClient.js` / `apps/frist-api/src/core.js` — 卡商号池聚合、60 秒刷新、无真实延迟空态和模型目录可用性保护。
- `apps/frist-api/src/admin.js` / `apps/frist-api/src/businessFlow.js` — 未提供真实延迟时不再写入默认假延迟。
- `apps/frist-api/tests/*.test.mjs` — 增加移动端折叠导航、卡商通道、无假延迟、模型目录和自动降级回归。
- `docs/002-changelog.md` / `docs/006-registries.md` / `docs/009-health.md` — 同步本轮批注修复、验证证据和剩余生产风险。

## [2026-05-09] 本地冗余清理与文档状态收口
> 领域: `infra` | `docs`
> 影响模块: `Workspace`, `Frist-API`, `ClawBot`, `docs`
> 关联问题: HI-897

### 变更内容
- 清理本地可重建冗余：移除源码树中的 `.DS_Store`、`.playwright-mcp`、`.pytest_cache`、`__pycache__`、`.ruff_cache`、Playwright/Expect 调试产物、Frist-API 历史审计截图、根目录临时截图和 ClawBot 本地旧日志。
- 明确保留边界：未删除 `.env`、`.openclaw/` 运行身份与会话、Frist-API runtime 数据、ClawBot `data/`、桌面端 `node_modules`、Python `.venv312`、腾讯云生产备份和共享服务器其他项目，避免清理动作造成运行状态丢失。
- 复核 `.gitignore` 已覆盖 `.DS_Store`、`__pycache__/`、`.pytest_cache`、`.playwright-mcp/`、`.playwright-cli/`、根目录截图、日志和密钥扫描报告；本轮不需要新增忽略规则。
- 同步文档状态：健康页新增 `HI-897`，登记本轮冗余清理范围、保留原因和验证口径；项目全景图更新时间，避免入口文档继续停留在 2026-04 的旧审计状态。
- 清理后复验：`git diff --check` 通过；`make new-api-check` 显示 GitHub 最新、本地源码和 Compose 镜像均为 `v1.0.0-rc.4`；公网首页 200、Dashboard 200、未授权 `/v1/models` 401、裸域名最终跳转到唯一 Frist-API 入口；浏览器只读复核页面标题 `Frist-API`，控制台 0 error/0 warning；复核产生的 `.playwright-mcp` 临时快照已二次清理。

### 文件变更
- `docs/002-changelog.md` — 新增本轮冗余清理和文档状态收口记录。
- `docs/009-health.md` — 更新本地日志/冗余清理状态，并登记 `HI-897`。
- `docs/001-project-map.md` — 更新时间提示，说明当前状态以健康页和变更日志为准。

## [2026-05-09] New-API 生产启动与 CC Switch 连通复核
> 领域: `infra` | `ai-pool` | `deploy` | `docs`
> 影响模块: `New-API`, `Frist-API`, `CC Switch`, `Tencent Cloud`, `docs`
> 关联问题: HI-895, HI-896

### 变更内容
- 继续处理腾讯云 New-API 升级遗留项：本轮重新备份 `/opt/frist-api/data/newapi`、`.env` 和 compose 后，成功拉取 `calciumion/new-api:v1.0.0-rc.4`，解除上一轮 Docker Hub 超时阻塞。
- 定位启动失败根因并修复部署方式：共享服务器已有 `/opt/ccgame/server/src/app.js` 长期监听 `127.0.0.1:3000`，因此将 `docker-compose.newapi.yml` 的宿主机端口改为 `NEWAPI_HOST_PORT` 可配置；腾讯云设置 `NEWAPI_HOST_PORT=13000`，容器内部仍为 `3000`，不停止无关项目。
- 定位第二个启动失败根因并修复远端数据权限：`data/newapi` 来自旧 UID 501，New-API 在安全加固 `cap_drop: ALL` 下无法创建 `/data/logs`；已把远端 `data/newapi` 调整为 `root:root`、目录 `750`、数据库文件 `640`，保留安全加固而非放宽容器权限。
- 复验 New-API 运行态：`openclaw-newapi` 运行 `v1.0.0-rc.4`，`127.0.0.1:13000->3000/tcp`，健康状态 `healthy`；`/api/status` 返回 `success=true`、`version=v1.0.0-rc.4`、`setup=true`。
- 使用浏览器复核公网 `#switch`：页面标题 `Frist-API`，控制台 0 error/0 warning，Dashboard 请求 200；未登录状态下页面不生成带 Key 的 provider 导入链接，保留 21 个模型展示和独立 MCP deep link，符合“登录并创建 Key 后生成用量脚本”的边界。
- 用运行数据生成脱敏 CC Switch provider 链接样本，确认 `resource=provider`、`app=codex`、`endpoint=http://frist-api.101-43-41-96.nip.io/v1`、默认模型 `gpt-5.5`、`usageScript` 指向 `/api/frist/key-usage` 且包含 Authorization；未出现旧的大块 `config/settings_config/availableModels` 参数。
- 受控临时 Key 连通性复核：`/v1/models` 返回 200 且 21 个模型，用量接口返回 200 且 `ok=true/valid=true`；真实 `chat/completions` 返回 503，追踪到唯一 healthy 上游在测试请求后返回 401 并触发 `credential_failed upstream_http_401`，说明当前上游库存 Key 无法形成完整聊天闭环。已从测试前备份恢复 runtime，临时测试用户/Key 清零，唯一 healthy 通道状态恢复。
- 公网冒烟最终结果：首页 200、Dashboard 200、未授权 `/v1/models` 401、裸域名 301；本地 Frist-API 3180 为 200，New-API 13000 为 200。

### 文件变更
- `docker-compose.newapi.yml` — New-API 宿主机端口改为 `NEWAPI_HOST_PORT` 可配置，默认仍为 `3000`。
- `docs/006-registries.md` / `docs/007-operations.md` — 更新 New-API 固定版本、端口变量和腾讯云实际运行状态。
- `docs/002-changelog.md` / `docs/009-health.md` — 登记本轮生产启动、CC Switch 复核证据和真实聊天连通遗留风险。

## [2026-05-08] 审计入口复核与测试命令收口
> 领域: `docs` | `infra`
> 影响模块: `AGENTS`, `docs`, `pytest`
> 关联问题: HI-894, HI-895

### 变更内容
- 本轮继续审计时发现直接运行 `pytest packages/clawbot/tests/ ...` 会命中本机 Python 3.9 的用户级 `pytest`，而项目代码和 CI 要求 Python 3.12；这会产生 `str | None` 类型语法错误，属于审计入口误用，不是业务代码回归。
- 已将 AGENTS/SOP 和快速导航里的后端测试命令收口为 `make test` 或 `.venv312/bin/python -m pytest`，确保本地审计与 GitHub Actions 的 Python 3.12 基线一致。
- 复验实际证据：`make test` 使用 `packages/clawbot/.venv312/bin/python` 执行并通过；GitHub `OpenClaw CI` run `25590993947` 两个 job 均成功；`New-API Scheduled Sync` run `25589650518` 成功；`make new-api-check` 显示本地源码和 Compose 镜像均为 `v1.0.0-rc.4`。
- 远端复核发现腾讯云 `/opt/frist-api/docker-compose.newapi.yml` 仍停留在 `calciumion/new-api:v1.0.0-rc.2`，已先备份 `data/newapi` 和旧 compose 到 `backups/newapi-runtime-20260508223247-before-rc4.tgz`，再同步 compose 到 `v1.0.0-rc.4` 并通过 `docker compose config` 校验；实际启动受 Docker Hub 访问超时阻塞，New-API 容器未启动，现有 `frist-api-server` 仍 healthy 且公网首页/看板 200。

### 文件变更
- `AGENTS.md` / `docs/001-project-map.md` / `docs/005-quickstart.md` — 统一后端测试入口，避免系统 Python 误用旧测试工具。
- `docs/002-changelog.md` / `docs/009-health.md` — 登记本轮审计入口修复和剩余环境风险。

## [2026-05-08] 浏览器审计收尾与 CI 运行时升级
> 领域: `frontend` | `infra` | `ai-pool` | `docs`
> 影响模块: `Frist-API`, `OpenClaw CI`, `New-API`, `docs`
> 关联问题: HI-886, HI-891, HI-892, TD-015

### 变更内容
- 使用内置浏览器审计公网 `http://frist-api.101-43-41-96.nip.io/`：首页 200、标题为 `Frist-API`、控制台无 error/warn；窄屏用户端可正常进入首页和 CC Switch，CC Switch 会切成带“首页”返回按钮的详情页。
- 发现无障碍噪音：隐藏视图中的多个 `.back-home::before` 文本箭头会在浏览器快照里聚合为 `← ← ←`；已改为纯 CSS 边框箭头，保留视觉箭头但不再暴露额外文本。
- 复审发现账户弹窗密码输入框缺少真实 `form` 语义，浏览器会给出密码管理器结构提示；已按登录/注册、改密码、重置密码、身份码激活拆成独立表单，补齐 `autocomplete`，并让回车提交走原处理逻辑。
- 清理 GitHub Actions Node 20 运行时预警：`OpenClaw CI` 升级 `actions/checkout@v6`、`actions/setup-node@v6`，前端 typecheck 改用 Node.js 24。
- 合并 New-API 自动同步 PR #1：submodule 和 Compose 镜像已同步到 `v1.0.0-rc.4`；本地复验 `docker compose -f docker-compose.newapi.yml config` 通过。正式生产部署仍需先备份 `data/newapi` 并保留回滚窗口。

### 文件变更
- `apps/frist-api/index.html` / `apps/frist-api/src/app.js` / `apps/frist-api/src/styles.css` — 返回首页按钮箭头改为非文本 CSS 图形；账户弹窗改为按动作拆分的真实表单并保留原视觉布局，消除隐藏视图可访问性噪音和密码管理器结构提示。
- `apps/frist-api/tests/business-flow.test.mjs` — 增加账户表单语义、自动填充和回车提交回归断言。
- `.github/workflows/ci.yml` — 升级 checkout/setup-node action 和 Node.js 版本，消除 Node 20 Actions 预警。
- `docker-compose.newapi.yml` / `packages/new-api-upstream` — 经 PR #1 合并同步 New-API 到 `v1.0.0-rc.4`。
- `docs/002-changelog.md` / `docs/009-health.md` — 记录浏览器审计、CI 清理和 New-API 合并状态。

## [2026-05-08] New-API 定时同步工作流修复
> 领域: `infra` | `ai-pool` | `docs`
> 影响模块: `GitHub Actions`, `New-API Sync`, `docker-compose.newapi.yml`, `docs`
> 关联问题: HI-886, HI-891

### 变更内容
- 定位 `New-API Scheduled Sync` 最近失败 run `25576027773`：检查和同步步骤均成功，失败点为 `docker compose -f docker-compose.newapi.yml config` 在 GitHub Actions 中缺少 `NEWAPI_INITIAL_TOKEN`，导致同步 PR 步骤被跳过。
- 在工作流的 compose 配置校验步骤注入 CI 专用占位 `NEWAPI_INITIAL_TOKEN`，只用于解析配置，不触碰生产 `.env` 或真实 root token。
- 调整 New-API 检查脚本语义：退出码 `0` 表示已同步，`2` 表示需要同步，其他非零才表示真实错误；工作流据此避免把网络、GitHub API、submodule 等真失败误判成“需要同步”。
- 同步处理 GitHub 不更新的本地侧原因：本地 `main` 比 `origin/main` 多 3 个提交，本轮提交后需一并推送到 GitHub 触发工作流复验。
- 推送后复验：仓库级 Actions 权限从只读改为 write 并允许创建 PR；`New-API Scheduled Sync` run `25588894721` 已通过全部步骤，并创建 `codex/new-api-scheduled-sync` 到 `main` 的 PR #1。

### 文件变更
- 当时的 New-API Scheduled Sync workflow — 为 compose 校验注入 CI 占位 token，并只把退出码 2 当作需要同步；该 workflow 后续随 Sub2API 切换删除。
- `scripts/sync_new_api_upstream.sh` — `check` 模式用退出码 2 表达版本漂移。
- `docs/002-changelog.md` / `docs/009-health.md` — 登记 GitHub Actions 根因、修复和剩余 New-API 生产升级风险。

## [2026-05-08] 严格审计复核与闲鱼管理页安全部署
> 领域: `backend` | `frontend` | `xianyu` | `deploy` | `docs`
> 影响模块: `OpenClaw Manager`, `WorldMonitor`, `NewsFeed`, `Xianyu Admin`, `APIServer`, `Tencent Cloud`
> 关联问题: HI-885, HI-886, HI-887, HI-889, HI-890

### 变更内容
- 明确复核上一轮审计边界：上一轮不是“全项目绝对完美生产级全量审计”，本轮用本地代码、live 命令、远端只读检查和公网冒烟补证据链。
- 为 `/api/v1/store/catalog` 增加专项回归，防止 Store 路由缺失再次只在全量 APIServer 初始化时暴露。
- 桌面端 `NewsFeed` 和 `WorldMonitor` 移除用 `textarea.innerHTML` 解码外部新闻文本的实现，改为共享 `decodeHtmlEntities()`，避免把外部文本交给 HTML 解析器。
- 闲鱼管理页内嵌前端补 `escapeHtml()`，对 dashboard、系统状态、最近对话、最近订单等接口返回字段写入 `innerHTML` 前统一转义，并增加页面安全回归。
- 已将闲鱼管理页同一安全修复单文件部署到腾讯云 `/home/clawbot/clawbot/src/xianyu/xianyu_admin.py`；部署前远端备份为 `/home/clawbot/clawbot/backups/xianyu_admin_20260508155652_before_escape.py`，远端 `py_compile` 通过，`clawbot.service` 重启后为 active。
- 验证证据：后端全量 pytest 退出码 0，当前 pytest nodeids 为 1495；`test_api_routes_regression.py` 12/12 通过；Frist-API `npm test` 153/153 通过且 `npm audit --audit-level=moderate` 0 漏洞；桌面端 `npx tsc --noEmit` 通过；`git diff --check` 和 Frist-API JS 语法检查通过；`gitleaks git --log-opts='HEAD~2..HEAD' --redact` 0 泄漏；公网 Frist-API 首页 200、Dashboard 200、未授权 `/v1/models` 401、裸域名 301。
- 保留真实遗留风险：New-API 本地/镜像仍为 `v1.0.0-rc.2`，GitHub live 最新为 `v1.0.0-rc.4`；用户在对话中暴露了服务器 root 密码，必须轮换；86GameStore 余额/消费/延迟风险仍需运营限额和慢线治理。

### 文件变更
- `apps/openclaw-manager-src/src/lib/html.ts` — 新增安全 HTML 实体解码工具。
- `apps/openclaw-manager-src/src/components/NewsFeed/index.tsx` / `apps/openclaw-manager-src/src/components/WorldMonitor/index.tsx` — 复用安全实体解码，不再用 `innerHTML` 解码外部文本。
- `packages/clawbot/src/xianyu/xianyu_admin.py` — 闲鱼管理页动态字段统一转义。
- `packages/clawbot/tests/test_api_routes_regression.py` — 增加 Store 路由和闲鱼管理页转义回归。
- `docs/002-changelog.md` / `docs/009-health.md` — 同步严格审计、部署和剩余风险。

## [2026-05-08] 全量测试审计和 Store 路由恢复
> 领域: `backend` | `frontend` | `ai-pool` | `infra` | `docs`
> 影响模块: `APIServer`, `Store Router`, `Frist-API`, `New-API`, `docs`
> 关联问题: HI-885, HI-886, HI-887, HI-888

### 变更内容
- 先按用户要求提交工作区 checkpoint：`60709ea chore: checkpoint frist api recovery state`，再进行全量测试和审计。
- 后端全量测试发现 `src.api.routers.store` 缺失导致 APIServer 初始化失败；恢复 `/api/v1/store/catalog` 和 `/api/v1/store/categories` 最小兼容路由后，`pytest packages/clawbot/tests/ --tb=short -x` 通过 `1491 passed, 2 skipped`。
- 为 Frist-API 生成 `package-lock.json`，补齐 `npm audit` 可审计基线；`npm test` 通过 `153/153`，`npm audit --audit-level=moderate` 为 0 漏洞，JS 语法检查通过。
- 桌面端 `npx tsc --noEmit` 通过；公网冒烟确认 Frist-API 首页 200、Dashboard 200、未授权 `/v1/models` 401。
- 生产审计登记：New-API 本地 `v1.0.0-rc.2` 落后于上游 `v1.0.0-rc.4`；86GameStore 面板显示余额 `$35.70`、今日实际消费 `$38.1537`、平均响应 `16.11s`，不属于完美生产态。
- 调整运维文档环境变量示例写法，消除 `gitleaks` 对当前 HEAD 的 `generic-api-key` 误报。

### 文件变更
- `packages/clawbot/src/api/routers/store.py` — 恢复统一插件商店 API 路由。
- `apps/frist-api/package-lock.json` — 固定 Frist-API npm 审计基线。
- `docs/002-changelog.md` / `docs/006-registries.md` / `docs/007-operations.md` / `docs/009-health.md` — 同步测试证据、问题清单、注册表和安全扫描记录。

## [2026-05-08] Frist-API 登录恢复和公网配置修复
> 领域: `backend` | `frontend` | `deploy` | `docs`
> 影响模块: `Frist-API`, `User Console`, `Admin`, `Tencent Cloud`, `docs`
> 关联问题: HI-884

### 变更内容
- 修复登录失败反馈：前端不再把服务端 401 “邮箱或密码不正确”统一翻译成“后端暂不可用”，找回密码和重置密码也展示真实反馈。
- 新增管理员账号恢复接口 `POST /api/admin/customers/password`，用于 SMTP 未配置或用户无法收邮件时由管理员重置客户密码；响应和审计不回显明文密码。
- 新增独立 `FRIST_API_PASSWORD_HASH_SECRET` 和 `FRIST_API_LEGACY_PASSWORD_HASH_SECRETS`，避免公网修复会话密钥时让旧用户密码全部失效；旧哈希登录成功后自动迁移。
- 生产排查确认公网 `/api/frist/dashboard`、注册、登录和 Cookie 看板链路可用；腾讯云已替换默认管理令牌、开启 CSRF 并保留旧密码兼容。历史 runtime 已有 `enc:v1` 字段但缺原始加密密钥，暂不启用新的随机数据加密密钥，避免看板 500；后续需做一次性 runtime 明文迁移或找回原密钥后再启用公开模式数据加密。

### 文件变更
- `apps/frist-api/src/app.js` — 登录和找回密码反馈改为显示服务端真实错误。
- `apps/frist-api/server/server.js` / `apps/frist-api/admin.html` / `apps/frist-api/src/admin.js` — 增加管理员密码恢复接口和管理端入口。
- `docker-compose.frist-api.yml` / `apps/frist-api/deploy/production.env.example` — 透传独立密码哈希密钥和历史兼容密钥。
- `apps/frist-api/tests/business-flow.test.mjs` / `apps/frist-api/tests/server.test.mjs` — 覆盖错误反馈和管理员恢复账号回归。
- `docs/002-changelog.md` / `docs/006-registries.md` / `docs/007-operations.md` / `docs/009-health.md` — 同步本轮登录恢复、接口注册、运维配置、生产兼容模式和健康记录。

## [2026-05-08] Frist-API 用户端视觉 QA 批注修复
> 领域: `frontend` | `backend` | `docs`
> 影响模块: `Frist-API`, `User Console`, `CC Switch`, `Gateway Dashboard`, `docs`
> 关联问题: HI-883

### 变更内容
- 按 26 条浏览器批注重做用户端视觉细节：顶部状态灯改为带语义状态，新增中/英文切换，Logo 改为 Apple 风格的简洁 `F` 标识。
- 重新调整工作台导航间距和选中态，隐藏暂不运营的充值、邀请、独立配置教程入口；首页移除最近日志板块，日志统一到使用记录页查看。
- Token 趋势从难读日期堆叠改为 SVG 折线/面积趋势图；未登录 Dashboard 不再返回 `channelChecks`，避免把真实库存快照误认为 mock 数据。
- CC Switch 页面去掉重复 `Harmes`，顶部增加导入按钮，用量查询说明下移为教程，代码框复制改为框内图标按钮。
- Claude Code 教程改为“OpenAI 模型以 Claude 名称导入 Claude Code”的当前约束说明；用户端模型展示使用官方友好名称，不改真实内部模型 ID，避免影响路由。
- 测试台参考 OpenAI Web 端重排为模型选择侧栏、对话区和底部输入框；资料页重做为头像/昵称/邮箱可编辑布局，登录注册弹窗也同步调整。

### 文件变更
- `apps/frist-api/index.html` / `apps/frist-api/src/app.js` / `apps/frist-api/src/styles.css` — 用户端导航、顶部、趋势图、CC Switch、测试台、资料页和登录弹窗视觉修复
- `apps/frist-api/src/core.js` / `apps/frist-api/server/server.js` / `apps/frist-api/src/serverClient.js` — 用户友好模型名、游客安静看板和导入配置展示边界
- `apps/frist-api/tests/business-flow.test.mjs` / `apps/frist-api/tests/core.test.mjs` / `apps/frist-api/tests/server.test.mjs` — 覆盖隐藏入口、去重目标、复制框、资料编辑、语言切换、游客 `channelChecks` 空态和登录态 SLA
- `docs/002-changelog.md` / `docs/006-registries.md` / `docs/009-health.md` — 同步本轮视觉 QA 和入口注册表

## [2026-05-07] Frist-API New-API 生产边界硬门槛
> 领域: `backend` | `frontend` | `deploy` | `docs`
> 影响模块: `Frist-API`, `Admin`, `Gateway`, `New-API`, `docs`
> 关联问题: HI-882

### 变更内容
- 新增生产强制边界开关 `FRIST_API_ENFORCE_PRODUCTION_READINESS`：正式模式会检查固定 HTTPS 品牌域名、New-API 数据库、管理员 2FA、真实支付商户、备份监控和渠道 SLA 状态，缺核心项时阻止启动。
- 管理端新增 TOTP 2FA 验证入口和 `/api/admin/2fa/verify`；启用 `FRIST_API_REQUIRE_ADMIN_2FA=1` 后，管理 API 必须先通过二次验证。
- 新增 `/api/admin/production-readiness` 和 `/api/admin/backups/status`，用于登记备份/恢复演练并在管理端展示生产边界状态。
- 渠道健康从“当前库存快照”升级为可持久化 SLA 事件：成功、慢线、失败和额度耗尽会写入 `channelProbeEvents`，Dashboard 返回 7/15/30 天窗口摘要。
- 生产环境模板和 Compose 透传 `FRIST_API_REQUIRE_NEWAPI_DATABASE`、管理员 2FA、备份新鲜度、SLA 保留天数等变量。

### 文件变更
- `apps/frist-api/server/server.js` — 生产硬门槛、TOTP 管理员 2FA、备份状态、SLA 事件和 readiness API
- `apps/frist-api/admin.html` / `apps/frist-api/src/admin.js` / `apps/frist-api/src/styles.css` — 管理端 2FA 输入和生产检查面板
- `apps/frist-api/tests/server.test.mjs` — 覆盖生产边界、管理员 2FA、备份状态和真实 SLA 事件
- `apps/frist-api/deploy/production.env.example` / `docker-compose.frist-api.yml` — 登记生产变量和强制边界开关
- `docs/006-registries.md` / `docs/007-operations.md` / `docs/009-health.md` — 同步生产边界、环境变量和剩余外部操作

## [2026-05-07] Frist-API 用户与管理闭环实机验收
> 领域: `backend` | `frontend` | `ai-pool` | `docs`
> 影响模块: `Frist-API`, `CC Switch`, `User Console`, `Admin`, `Gateway`, `docs`
> 关联问题: HI-881

### 变更内容
- 用户侧把 `ChatGPT / OpenAI` 展示统一收敛为 `OpenAI`，并在 CC Switch 页新增“导入后检测闭环”：供应商卡片、用量脚本、真实调用、`gpt-image-2` 流程图测试和记录页消费回写。
- 管理侧新增号池首次使用流程和渠道诊断：管理员只需要填端点、粘 Key、写入库存；页面按模型组汇总可用/断开/降级、最快延迟、失败原因和模型清单，方便判断哪个渠道断了。
- Dashboard 新增轻量异常消耗检测，覆盖今日消耗接近余额、单次调用费用突增和高延迟请求；响应只返回用户可读摘要，不泄露上游 Key、供应商原始地址或 raw usage。
- 受控实机验收使用临时 runtime 和本地 mock 上游完成：登录、创建 `fk-live-*` Key、CC Switch 导入链接含用量脚本、文本 `pong`、`gpt-image-2` 图片返回、记录页文本/图片消费、异常消耗提醒、`gpt-image-2` `1/2 可用` 降级状态。
- 修复异常消耗回归用例的阈值样本：模拟 usage 调整为真实会触发“今日消耗偏高”的大额调用，避免把业务规则放宽成假通过。

### 文件变更
- `apps/frist-api/index.html` / `apps/frist-api/src/app.js` / `apps/frist-api/src/serverClient.js` / `apps/frist-api/src/styles.css` — 用户侧 OpenAI 命名、导入后检测闭环和异常消耗卡片
- `apps/frist-api/admin.html` / `apps/frist-api/src/admin.js` / `apps/frist-api/src/styles.css` — 管理端号池小白流程、库存诊断和状态展示
- `apps/frist-api/server/server.js` / `apps/frist-api/server/newApiBridge.js` — Dashboard 和 New-API 桥接层输出轻量异常消耗摘要
- `apps/frist-api/tests/business-flow.test.mjs` / `apps/frist-api/tests/core.test.mjs` / `apps/frist-api/tests/new-api-adapter.test.mjs` / `apps/frist-api/tests/server.test.mjs` — 覆盖导入检测、管理诊断、异常消耗和阈值回归
- `docs/006-registries.md` / `docs/009-health.md` — 登记本轮闭环能力和剩余生产边界

## [2026-05-06] Frist-API CC Switch 小白满血导入收尾
> 领域: `backend` | `frontend` | `docs`
> 影响模块: `Frist-API`, `CC Switch`, `Claude`, `Codex`, `OpenCode`, `OpenClaw`, `Hermes`, `docs`
> 关联问题: HI-880

### 变更内容
- 按 CC Switch 当前 `origin/main` 源码重新核对 provider/MCP deep link：供应商导入和 MCP 导入是两个 `resource`，一键供应商导入不能假装同时写入 MCP；页面改成“小白两步”：先导入供应商，再导入 MCP 增强包。
- MCP 增强包默认覆盖 CC Switch 当前支持的 `claude,codex,gemini,opencode,hermes`；页面明确说明 OpenClaw 供应商可导入，但 CC Switch 当前会忽略 OpenClaw MCP。
- 补充 CC Switch `prompt` / `skill` 资源边界：它们是独立 deep link 资源，不会随 provider 一键导入同时写入；没有公开 Skill 仓库时不生成虚假链接。
- 修复 `/api/frist/import-url` 用户显式选择模型时的导出不一致：服务端返回的默认模型、CC Switch 链接的 `model`、Codex `config.toml` 的 `model/default_model` 现在保持一致；未显式选择时仍默认最强可用模型。
- 保留 Codex 本地 `config.toml` 内联 Playwright/Superpowers/open-computer-use MCP；Claude、Gemini、OpenCode、Hermes 不再误塞 Codex TOML 段，而是使用单独的 CC Switch MCP deep link。
- 页面新增更直白的完整 Workflow：登录创建 Key、一键导入供应商、确认默认模型、测试用量查询、导入 MCP 增强包、复制终端测试命令；手动用户仍可复制 JSON/TOML、OpenCode provider 片段、用量脚本和 CLI 测试命令。

### 文件变更
- `apps/frist-api/src/core.js` — 增加服务端显式默认模型选项、全客户端 MCP deep link、Codex-only TOML MCP 内联和 CC Switch MCP 支持范围
- `apps/frist-api/server/server.js` — `/api/frist/import-url` 对服务端确认模型启用显式默认，避免导入链接和返回字段不一致
- `apps/frist-api/index.html` / `apps/frist-api/src/app.js` / `apps/frist-api/src/styles.css` — CC Switch 小白 Workflow、MCP 增强包、Prompt/Skill 边界和手动配置展示
- `apps/frist-api/tests/core.test.mjs` / `apps/frist-api/tests/business-flow.test.mjs` / `apps/frist-api/tests/server.test.mjs` — 覆盖全客户端 MCP deep link、OpenClaw MCP 边界和用户选择模型一致性
- `docs/006-registries.md` / `docs/009-health.md` — 登记 CC Switch 满血导入边界和本轮收尾状态

## [2026-05-06] Frist-API 86GameStore 号源接入与查询失败修复
> 领域: `backend` | `frontend` | `ai-pool` | `docs`
> 影响模块: `Frist-API`, `Gateway`, `CC Switch`, `Claude CLI`, `Codex CLI`, `docs`
> 关联问题: HI-879

### 变更内容
- 修复 CC Switch 用量查询“查询失败”：导出的 `usageScript.extractor.extra` 从对象改为字符串摘要，匹配当前 CC Switch provider 用量脚本解析契约，并增加回归断言。
- Claude 兼容入口优先走原生 Anthropic Messages `/v1/messages` 上游；如果上游不支持，再回退到 OpenAI Chat Completions 适配，避免 Claude CLI 导入后真实请求卡在适配层。
- 严格补号探测新增原生 Claude Messages 探测；对象形式补号 Key 未填 `modelGroup` 时继承补号单模型组；同一个上游 Key 作为 Claude/OpenAI 两组库存时按 `baseUrl + modelGroup + rawKey` 分开保存，避免后写覆盖先写。
- 本地 runtime 已接入 86GameStore 授权上游：Claude 组 `claude-sonnet-4-5-c`、`claude-opus-4-6-c` 为 healthy；OpenAI 组 `gpt-5.4-mini`、`gpt-5.3-codex`、`gpt-5.4`、`gpt-5.5` 为 healthy。真实上游 Key 只在 ignored runtime 中以 `enc:v1:` AES-GCM 形式保存。
- 实测用户闭环：注册/登录、管理员入账、创建 Claude/OpenAI 用户 Key、`/v1/models`、导出 Claude/Codex CC Switch 链接、`/api/frist/key-usage`、Claude `/v1/messages`、Codex `/v1/responses` 均成功，真实请求返回 `pong` 并写入使用记录。
- 实测 CLI 闭环：Claude CLI 使用临时 settings 指向本地 Frist-API，`claude-sonnet-4-5-c` 返回 `pong`；Codex CLI 使用临时 `CODEX_HOME` provider，`gpt-5.4-mini` 返回 `pong`。测试未覆盖或改写用户原有 Claude/Codex 配置。
- 前端顶部连接状态修复为 Dashboard 成功后显示“已连接”，失败时显示“后端暂不可用”；浏览器刷新后确认不再长期停在“连接中”。

### 文件变更
- `apps/frist-api/src/core.js` — CC Switch 用量脚本字段类型修复、导出按模型组选择匹配用户 Key
- `apps/frist-api/server/server.js` — Claude 原生 Messages 路由和严格探测、同 Key 多模型组库存隔离、补号模型组继承、探测超时默认 8 秒
- `apps/frist-api/src/serverClient.js` / `apps/frist-api/src/app.js` — 用户端连接状态成功/失败反馈收敛
- `apps/frist-api/tests/core.test.mjs` / `apps/frist-api/tests/server.test.mjs` — 补 CC Switch 用量脚本、Claude 原生路由、原生探测、共享 Key 分组隔离、导出选 Key 和连接状态回归
- `apps/frist-api/deploy/production.env.example` / `docs/006-registries.md` / `docs/009-health.md` — 登记 8 秒探测超时、86GameStore 授权上游和本轮实测状态

## [2026-05-06] Frist-API 渠道状态监视器增强
> 领域: `backend` | `frontend` | `docs`
> 影响模块: `Frist-API`, `User Console`, `Channel Monitor`, `docs`
> 关联问题: HI-878

### 变更内容
- 参考 86GameStore `/monitor` 的用户侧监控形态，确认其公开页采用 `/channel-monitors`、7/15/30 天窗口、主模型延迟、endpoint ping、最近 60 点状态条和 30/60/120 秒自动刷新；本项目先按现有 runtime 库存能力落地“当前库存快照”，不伪造真实 7/15/30 天时间序列。
- Frist-API Dashboard 的 `channelChecks` 增加 `healthyCount`、`totalCount`、`downCount`、`slowCount`、`availability7d`、`availabilityWindow`、`successLabel`、`latencyLabel`、`averageLatencyMs`、`monitorIntervalSeconds`、`monitorStatus` 和 60 点 `history`，响应仍只暴露 `/v1`，不返回上游地址、上游 Key 或号商字段。
- 用户首页“通道”和趋势页“服务可用性”补齐状态标签、可用率、最低/平均延迟、最近检测、60 秒刷新口径和状态条；降级线路会用慢/失败状态点标记。
- 补充服务端、浏览器归一化和用户页面 wiring 回归，覆盖聚合监控字段、降级状态、当前快照口径和敏感字段不泄露。

### 文件变更
- `apps/frist-api/server/server.js` / `apps/frist-api/server/catalog.js` — 渠道监控聚合字段从单纯 healthy/total 扩展为可用率、降级、慢线、平均延迟和 60 点状态条
- `apps/frist-api/src/serverClient.js` / `apps/frist-api/src/core.js` — 浏览器归一化和安全摘要支持新监控字段
- `apps/frist-api/src/app.js` / `apps/frist-api/src/styles.css` — 用户侧通道摘要和服务卡增加状态标签、指标格和历史条
- `apps/frist-api/tests/server.test.mjs` / `apps/frist-api/tests/new-api-adapter.test.mjs` / `apps/frist-api/tests/core.test.mjs` / `apps/frist-api/tests/business-flow.test.mjs` — 覆盖监控字段、降级状态、脱敏边界和页面钩子
- `docs/006-registries.md` / `docs/009-health.md` — 登记渠道监控口径和剩余真实时间序列技术债

## [2026-05-06] Frist-API CC Switch 用量查询一键导入与 CLI 实测闭环
> 领域: `backend` | `frontend` | `docs`
> 影响模块: `Frist-API`, `CC Switch`, `New-API Bridge`, `User Console`, `docs`
> 关联问题: HI-877

### 变更内容
- 核对 CC Switch 官方 Deep Link 协议和本机 CC Switch 3.14.1 行为，确认当前 provider deep link 消费 `resource/app/name/homepage/endpoint/apiKey/model/*Model/notes/usage*` 字段；导入链接已收敛为官方短字段，不再塞旧 `config`、`availableModels` 等大块配置。
- `usageScript` 改为 Base64URL 编码，匹配 CC Switch 当前 `usage_script` 解码逻辑；语雀公开可读摘要中的“右侧用量查询、填入秘钥和 API”步骤已落到页面教程。
- CC Switch 导入链接现在同步写入自定义用量查询脚本，默认 15 分钟自动查询；脚本调用 Frist-API 自己的 `/api/frist/key-usage`，返回余额、已用额度、总额度、今日/本月消费、请求量、Token、延迟和成功率。
- 新增 `/api/frist/key-usage` 只读接口，用户 Key 通过 Bearer 或 `x-api-key` 鉴权；响应只返回脱敏统计，不返回用户完整 Key、上游 rawKey、供应商地址或号商信息。
- 修复 New-API 桥接层 `buildKeyUsage` 参数名遮蔽内部请求函数导致 500 的回归，并覆盖 New-API Token 查询、Dashboard、导入和网关代理闭环。
- DeepSeek 等模型组继续把模型请求地址导向官方兼容端点，但用量查询地址固定从 Frist-API 公开网关地址派生，避免余额脚本误打到 `api.deepseek.com`。
- 实机闭环：使用临时 Frist API 和本地受控上游生成真实 `fk-live-*` Key，CC Switch 日志确认收到并解析 `resource=provider/app=claude/name=Frist-API` deep link；因当前 CC Switch 窗口无可访问确认按钮，按官方导入结构等价写入临时 provider 后，`claude --bare --no-session-persistence --model claude-sonnet-4-5-c` 返回 `Frist API CLI OK`。测试后已恢复用户原 CC Switch/Claude 配置。

### 文件变更
- `apps/frist-api/src/core.js` — CC Switch 导入新增用量查询脚本、Base64URL 编码、短 deep link 字段和 Frist/API 上游地址解耦
- `apps/frist-api/server/server.js` / `apps/frist-api/server/newApiBridge.js` — 新增用户 Key 用量查询接口并修复 New-API 桥接回归
- `apps/frist-api/index.html` / `apps/frist-api/src/app.js` / `apps/frist-api/src/styles.css` — CC Switch 页面补“用量查询、启用、测试脚本、自动查询间隔”教程和状态文案
- `apps/frist-api/tests/core.test.mjs` / `apps/frist-api/tests/server.test.mjs` / `apps/frist-api/tests/business-flow.test.mjs` — 覆盖 deep link 用量字段、短链接契约、OpenCode 配置、New-API 用量接口和教程文案
- `docs/006-registries.md` / `docs/009-health.md` — 登记新接口、教程闭环和剩余真实客户端验收边界

## [2026-05-06] Frist-API 上线前安全闭环修复
> 领域: `backend` | `frontend` | `deploy` | `docs`
> 影响模块: `Frist-API`, `Gateway`, `Runtime Store`, `Payments`, `User Console`, `docs`
> 关联问题: HI-876

### 变更内容
- 用户 API Key 新建前缀恢复为 `fk-live-*`，生成使用 `crypto.randomBytes(32).toString('base64url')`，校验统一走恒定时间比较，Dashboard 刷新后不再返回明文 Key。
- Cookie 登录态的非幂等接口增加 CSRF Token 校验；注册/登录返回 CSRF Token 并设置 `frist_csrf` Cookie，浏览器客户端自动带 `x-csrf-token`。
- 微信/支付宝回调入账前校验实付金额和订单金额；少付通知拒绝入账，重复通知仍按订单号幂等处理。
- 管理端补号 URL 增加 SSRF 防护，默认拒绝 localhost、私网、link-local 和云 metadata 地址，测试环境可显式注入解析器。
- runtime 写入改为临时文件 fsync 后 rename，写入失败发出 `FRIST_API_RUNTIME_WRITE_FAILED` warning；共享脱敏和 CORS 头同步支持 `fk-live-*` 与 `x-csrf-token`。
- 生产模板补齐 `FRIST_API_REQUIRE_CSRF`、`FRIST_API_ALLOW_PRIVATE_UPSTREAM_URLS`，公网网关示例恢复为 HTTPS 占位域名，避免生产硬门槛被 HTTP 示例误导。

### 文件变更
- `apps/frist-api/server/server.js` / `apps/frist-api/server/shared.js` / `apps/frist-api/server/newApiBridge.js` — Key 生成和脱敏、CSRF、SSRF、金额校验、runtime 原子写和 CORS 头
- `apps/frist-api/src/serverClient.js` / `apps/frist-api/src/app.js` / `apps/frist-api/src/newApiClient.js` — 浏览器 CSRF 头、创建后一次性显示 Key、刷新后不依赖明文 Key
- `apps/frist-api/tests/server.test.mjs` / `apps/frist-api/tests/business-flow.test.mjs` — 覆盖 `fk-live-*`、CSRF、少付回调、SSRF 阻断和用户侧不泄露明文 Key
- `apps/frist-api/deploy/production.env.example` / `docker-compose.frist-api.yml` — 登记生产 CSRF 和 SSRF 开关，修正公网 HTTPS 示例
- `docs/006-registries.md` / `docs/009-health.md` — 同步生产变量和上线前剩余风险

## [2026-05-05] Frist-API 用户端深色体验和官方计价修复
> 领域: `frontend` | `backend` | `ai-pool` | `deploy` | `docs`
> 影响模块: `Frist-API`, `User Console`, `Gateway Billing`, `docs`
> 关联问题: HI-875

### 变更内容
- 用户首页最近日志改为 5 条内的精简事件，过滤管理认证失败等噪音；使用记录页补充客户端、费用、延迟和 Token，让广场、MacBook、PC 等来源能分开看。
- API Key 展示曾短暂改为通用 `sk-*`；2026-05-06 已按安全审计恢复为新建 `fk-live-*`、兼容旧 `sk-*`。
- 测试页减少解释文字、修复深色气泡对比度，模型连通改为 3 分钟自动检测一次；顶部和局部反馈改为短动效状态，不再显示塑料感长文案。
- 模型价目表按官方输入、缓存输入/缓存读写、输出口径统一展示；覆盖 OpenAI、Claude、DeepSeek、Gemini 和图片模型。
- 账单页前置展开兑换码，预警邮箱只遮罩展示；邀请改为“消费才返利”，返利上限为受邀方首次充值金额 5%；资料页支持修改昵称和邮箱。
- 深色控制台逐页补齐对比度护栏，修复 API 页面布局闭合标签，消费后自动刷新余额。
- 已部署到腾讯云 `/opt/frist-api`，远端应用备份为 `backups/frist-api-app-20260505-211636-before-ux-deploy.tgz`，运行数据备份为 `backups/frist-api-runtime-20260505-211636-before-ux-deploy.tgz`；`frist-api-server` 为 healthy，公网首页和看板均返回 200，裸域名返回 301 到品牌入口，未授权 `/v1/models` 保持 401。

### 文件变更
- `apps/frist-api/index.html` / `apps/frist-api/src/styles.css` — 深色控制台、兑换码前置、API 页面布局和对比度修复
- `apps/frist-api/src/app.js` / `apps/frist-api/src/serverClient.js` — 日志降噪、测试页降噪、余额刷新、反馈动效、资料/邀请/预警展示
- `apps/frist-api/server/server.js` / `apps/frist-api/server/shared.js` — Key 展示、记录字段、价目表、消费扣费和余额刷新数据
- `apps/frist-api/deploy/smoke-test.sh` — 冒烟脚本兼容中文管理工作台和可关闭验证码场景
- `apps/frist-api/tests/*.test.mjs` — 覆盖 Key 前缀、日志/记录、官方价格、深色 UI 入口和自动测试
- `docs/002-changelog.md` / `docs/006-registries.md` / `docs/007-operations.md` / `docs/009-health.md` — 同步本轮修复

## [2026-05-05] Frist-API inroi 授权上游号池检测
> 领域: `ai-pool` | `deploy` | `docs`
> 影响模块: `Frist-API`, `AI Pool`, `Admin`, `docs`
> 关联问题: HI-874

### 变更内容
- 核对 `https://www.inroi.shop/v1` 是上游请求地址，不是 Frist-API 对外入口；Frist-API 公网入口仍按 `frist-api.101-43-41-96.nip.io` 收口，裸域名只做 301。
- 远端管理接口检测到同一 Key 的旧根地址记录 `https://www.inroi.shop` 已是 `exhausted/enabled=false`，不可路由；正确请求地址 `https://www.inroi.shop/v1` 已加入号池并处于 `healthy/enabled=true`。
- 已实测 inroi 上游 `/v1/models` 返回 21 个模型，`gpt-5.4-mini` Chat Completions 返回 200；真实 Key 只通过服务器管理 API 写入远端加密 runtime，不进入 Git 或文档正文。

### 文件变更
- `docs/006-registries.md` / `docs/009-health.md` — 同步 inroi 授权上游检测状态

## [2026-05-05] Frist-API 公网入口收口
> 领域: `backend` | `deploy` | `docs`
> 影响模块: `Frist-API`, `Nginx`, `Public Gateway`, `docs`
> 关联问题: HI-873

### 变更内容
- 将 Frist-API 唯一内容入口统一为 `frist-api.101-43-41-96.nip.io`，避免 `101-43-41-96.nip.io` 被误认为第二个网站。
- Nginx 配置改为品牌域名反代到 Frist-API 服务，裸域名只返回 301 到品牌域名。
- Node 服务增加应用层兜底跳转，绕过 Nginx 或未来反代配置变更时也不会直接渲染裸域名页面。
- 生产环境模板新增 `FRIST_API_CANONICAL_HOST` 和 `FRIST_API_REDIRECT_HOSTS`，导出和邮件公网地址统一到品牌域名。
- Docker Compose 透传 canonical/redirect 环境变量，确保公网容器重启后仍按唯一入口策略运行。

### 文件变更
- `apps/frist-api/server/server.js` — 增加 canonical host 和裸域名 301 兜底
- `docker-compose.frist-api.yml` / `apps/frist-api/deploy/nginx.conf` / `apps/frist-api/deploy/production.env.example` — 收口公网入口和环境变量模板
- `apps/frist-api/tests/server.test.mjs` — 覆盖裸域名 301 和品牌域名正常服务
- `docs/006-registries.md` / `docs/007-operations.md` / `docs/009-health.md` — 同步唯一入口、运维步骤和健康状态

## [2026-05-05] Frist-API CC Switch 导出模型与品牌标复原
> 领域: `frontend` | `backend` | `docs`
> 影响模块: `Frist-API`, `CC Switch`, `New-API Bridge`, `docs`
> 关联问题: HI-872

### 变更内容
- 修复用户在 `#switch` 页面看不到 `gpt-5.4`、`gpt-5.4-mini`、`gpt-image-2`、`gpt-5.3-codex` 的问题：OpenAI 家族导出清单现在会补齐官方完整模型集，不再被部分上游库存或桥接层裁掉。
- CC Switch 导出预览和 New-API 桥接层都改用同一套可见模型展开逻辑，保证 `/api/frist/import-url`、`ccswitch://` 和手动配置看到的是同一份完整模型表。
- 恢复 Frist-API 品牌标识为原黑红白 logo，Tabcode 皮肤只保留布局和对比度，不再把品牌标改成灰白抽象块。
- 给导出模型 chip 和相关回归补上测试门槛，防止以后再把核心模型藏掉。

### 文件变更
- `apps/frist-api/src/core.js` — 增加 OpenAI 官方模型族展开和统一可见模型归一化
- `apps/frist-api/src/app.js` — CC Switch 导出清单改为强制显示完整模型集
- `apps/frist-api/server/newApiBridge.js` / `apps/frist-api/server/server.js` — 桥接层与服务端导出链路同步完整模型集
- `apps/frist-api/src/styles.css` — 恢复品牌标视觉并强化导出 chip 可读性
- `apps/frist-api/tests/core.test.mjs` / `apps/frist-api/tests/server.test.mjs` — 补回归
- `docs/002-changelog.md` / `docs/009-health.md` — 记录本轮修复

## [2026-05-05] Frist-API Tabcode 皮肤对比度修复
> 领域: `frontend` | `docs`
> 影响模块: `Frist-API`, `User Console`, `Admin`, `CC Switch`, `docs`
> 关联问题: HI-871

### 变更内容
- 修复 Tabcode 浅色控制台里旧深色皮肤残留导致的黑底灰字问题，重点覆盖 CC Switch 目标按钮、返回按钮、代码栏复制按钮、测试页删除按钮和分段选中态。
- 静态资源版本号切到 `20260505-contrast-fix`，避免浏览器继续命中旧 CSS 缓存。
- 增加 Tabcode 对比度护栏：主按钮/选中态统一黑底白字，普通按钮统一白底深字，深色代码栏内复制按钮使用白底深字。
- 浏览器实测用户端 6 个主路由和管理端可见交互元素低对比扫描均为 0；桌面和 390px 移动端截图已验证。

### 文件变更
- `apps/frist-api/index.html` / `apps/frist-api/admin.html` — 更新 CSS/JS 资源版本号
- `apps/frist-api/src/styles.css` — 增加 Tabcode 对比度护栏和可读性颜色修复
- `apps/frist-api/tests/core.test.mjs` — 补充对比度护栏和资源版本回归断言
- `docs/002-changelog.md` / `docs/009-health.md` — 记录本轮 UI 修复

## [2026-05-05] Frist-API CC Switch 导出和运行遗留项收尾
> 领域: `backend` | `frontend` | `ai-pool` | `docs`
> 影响模块: `Frist-API`, `CC Switch`, `Admin`, `Runtime Store`, `docs`
> 关联问题: HI-870

### 变更内容
- 参考本机 CC Switch 已导入的 Tabcode Claude/Codex 配置，把一键导入补齐为 New-API 基础深链字段 + Tabcode 真实 `settings_config` 落库结构。
- Claude 导出写入 `ANTHROPIC_AUTH_TOKEN` 和不带 `/v1` 的 `ANTHROPIC_BASE_URL`；Codex 导出写入 `OPENAI_API_KEY` 和 Responses `config.toml`，同时保留完整模型清单、MCP 和现有扩展字段。
- 用户点击 `ccswitch://` 导入时自动复制链接并显示短降级反馈，浏览器未弹出 CC Switch 时仍可粘贴导入。
- 管理 API 认证失败会写入脱敏审计事件；runtime 写入失败会发出 Node warning，不再静默吞掉；CLI 启动增加 SIGTERM/SIGINT 优雅关闭。

### 文件变更
- `apps/frist-api/src/core.js` — 增加 CC Switch `settingsConfig/settings_config` 和 New-API 基础字段兼容
- `apps/frist-api/index.html` / `apps/frist-api/src/app.js` / `apps/frist-api/src/styles.css` — 增加 CC Switch 协议降级反馈和自动复制
- `apps/frist-api/server/server.js` — 增加管理失败审计、runtime 写入告警和优雅关闭
- `apps/frist-api/tests/core.test.mjs` / `apps/frist-api/tests/server.test.mjs` — 补齐 CC Switch 导出契约、管理失败审计和运行遗留项回归
- `docs/006-registries.md` / `docs/009-health.md` — 同步入口和健康状态

## [2026-05-05] Frist-API Plus 金额审计修复
> 领域: `backend` | `ai-pool` | `docs`
> 影响模块: `Frist-API`, `Admin`, `Plus Ledger`, `docs`
> 关联问题: HI-869

### 变更内容
- 全量审计时发现 Plus 账号台账的 TRY 余额/月费如果收到异常数字输入，可能把 `NaN` 带入运行数据和摘要。
- 后端新增有限数字归一化，异常金额统一落为 0，避免管理响应出现 `null` 或污染 Plus 摘要。
- 回归测试补充异常金额输入断言，确保 Plus 敏感字段仍脱敏且金额字段稳定返回数字。

### 文件变更
- `apps/frist-api/server/server.js` — Plus 台账金额改用有限数字归一化
- `apps/frist-api/tests/server.test.mjs` — 补充异常 TRY 金额回归覆盖
- `docs/002-changelog.md` / `docs/009-health.md` — 记录本轮审计修复

## [2026-05-05] Frist-API Tabcode Console 设计吸收
> 领域: `frontend` | `docs`
> 影响模块: `Frist-API`, `User Console`, `Admin`, `docs`
> 关联问题: HI-868

### 变更内容
- 参考本地 Tabcode Dashboard 克隆，把 Frist-API 用户端和管理端切换为 `tabcode-console`：54px 白色顶栏、160px 灰色侧栏、灰色工作区、14px 白色卡片、轻阴影和黑色主按钮。
- 移除上一版设计皮肤入口和 CSS 残留，图表配色从蓝色体系改为中性黑灰加状态色，登录弹窗改为 Tabcode 两栏桌面布局并保留移动端可滚动关闭。
- 管理端仅替换视觉壳，不删管理功能；New-API/价格/入账/卡密/Plus/RT/接入/订单/库存/审计等原有入口继续保留。
- 性能优化继续保留 `content-visibility`、隐藏面板跳过渲染、搜索防抖、模型目录缓存和测试台局部渲染，避免控制台高频切换时反复重绘。

### 文件变更
- `apps/frist-api/index.html` / `apps/frist-api/admin.html` — 设计系统标记和静态资源版本切到 Tabcode Console
- `apps/frist-api/src/styles.css` — 删除旧设计皮肤，新增 Tabcode Console token、布局、卡片、表格、弹窗和移动端规则
- `apps/frist-api/src/app.js` — 图表颜色切到中性控制台色系
- `apps/frist-api/tests/core.test.mjs` — 回归断言切到 Tabcode Console 视觉 token 和旧皮肤移除
- `docs/006-registries.md` / `docs/009-health.md` — 同步设计系统登记和健康状态

## [2026-05-05] Frist-API Refero Apple UI 降噪
> 领域: `frontend` | `docs`
> 影响模块: `Frist-API`, `User Console`, `Admin`, `docs`
> 关联问题: HI-867

### 变更内容
- 参考 Refero Styles 的 Apple 高热样式，把 Frist-API 用户端和管理端从深色 Hyperstudio 壳切到浅色 Apple 控制台：`#f5f5f7` 画布、白色面板、`#0071e3` 主操作、弱边界和短状态动效。
- 用户端以“前端入口”为准做降噪：首屏指标压到余额、Key、今日和成功率四项；导航把“仪表盘/广场/教程”等长标签改为“首页/测试/配置”，状态空态改为“无记录/未检测/离线”等短标签。
- 管理端保留价格、入账、卡密、Plus、RT、接入、订单、库存和审计等原有管理项，只压缩提示文案；New-API 管理侧能力没有减少。
- 性能上减少不必要渲染：模型目录缓存、测试台日志/图片签名复用、搜索输入防抖、面板 `content-visibility` 和克制状态动效，避免全量 DOM 反复重绘。

### 文件变更
- `apps/frist-api/index.html` — 精简用户端导航、状态、导入流程和兑换/邀请文案
- `apps/frist-api/admin.html` — 精简管理端说明文案，保留原管理区块和 RT JSON/TXT 入口
- `apps/frist-api/src/app.js` — 缩短空态/反馈文案，保留测试台和模型目录渲染缓存
- `apps/frist-api/src/admin.js` — 缩短管理端反馈和空态文案
- `apps/frist-api/src/styles.css` — 增加 Refero Apple final layer、状态微动效和 `content-visibility` 渲染优化
- `apps/frist-api/tests/core.test.mjs` — 回归断言切到 Refero Apple 视觉 token 与四指标首屏
- `docs/006-registries.md` / `docs/009-health.md` — 同步入口命名和健康状态

## [2026-05-04] Open Design 本机配置接入
> 领域: `infra` | `docs`
> 影响模块: `Codex Skills`, `Open Design`, `MCP`
> 关联问题: 无

### 变更内容
- 将 Open Design 克隆到 `/Users/blackdj/Desktop/open-design`，按官方要求启用 Node 24 和 pnpm 10.33.2，并完成依赖安装、daemon 构建和 Web 服务启动。
- 固定 Open Design 本机端口：Web 为 `http://127.0.0.1:17573`，daemon 为 `http://127.0.0.1:17456`，便于后续稳定接入 Codex。
- 在 `~/.codex/config.toml` 新增只读 `open-design` MCP server，让 Codex 后续能读取当前 Open Design 项目/文件/Artifact。
- 新增 Codex skill `~/.codex/skills/open-design`，记录启动、诊断、MCP 使用和把 Open Design 产物落地到项目 UI 的工作流。

### 文件变更
- `~/.codex/config.toml` — 新增 `mcp_servers.open-design`
- `~/.codex/skills/open-design/SKILL.md` — 新增 Open Design 使用工作流
- `~/.codex/skills/open-design/references/local-setup.md` — 记录本机路径、端口、启动命令和验证命令

## [2026-05-04] Frist-API RT JSON 批量导入管理
> 领域: `backend` | `frontend` | `ai-pool` | `docs`
> 影响模块: `Frist-API`, `Admin`, `New-API`, `AI Pool`, `docs`
> 关联问题: HI-866

### 变更内容
- 参考 New-API Codex OAuth 与 Grok 给出的 RT JSON 格式，在 Frist-API 管理端新增 Refresh Token 账号池，支持 JSON 数组、单个 JSON 对象和 TXT 每行一个 RT 的导入方式。
- 管理侧是在原有 New-API/补号/价格/卡密/Plus/审计内容上增量增加，原有管理入口不减少；RT 默认只作为后台台账和刷新准备，不直接进入用户 `/v1` 路由库存。
- 后端新增 `/api/admin/rt-accounts` 和 `/api/admin/rt-accounts/import`，导入后只返回脱敏邮箱、账号 ID、RT 预览和指纹；`refreshToken` 纳入 runtime AES-GCM 加密字段。
- 回归覆盖 JSON/TXT 导入、重复 RT 更新、明文 RT/账号 ID 不出现在管理响应和落盘文件、RT 台账不污染可售上游 Key 库存。
- 验证结果: `node --check apps/frist-api/server/server.js apps/frist-api/src/admin.js` 通过；聚焦 `node --test tests/business-flow.test.mjs tests/server.test.mjs` 为 85/85 通过；Frist-API 全量 `npm test` 为 125/125 通过；`git diff --check` 通过。

### 文件变更
- `apps/frist-api/server/server.js` — 新增 RT 台账模型、导入解析、管理 API、脱敏展示、摘要和加密字段
- `apps/frist-api/admin.html` / `apps/frist-api/src/admin.js` / `apps/frist-api/src/styles.css` — 新增管理端 RT 导入区块、摘要和脱敏列表
- `apps/frist-api/tests/core.test.mjs` / `apps/frist-api/tests/server.test.mjs` — 覆盖用户端隔离和 RT 导入安全边界
- `docs/006-registries.md` / `docs/009-health.md` — 同步管理入口和健康状态

## [2026-05-04] Frist-API Plus 自用账号台账入口
> 领域: `backend` | `frontend` | `ai-pool` | `docs`
> 影响模块: `Frist-API`, `Admin`, `AI Pool`, `docs`
> 关联问题: HI-865

### 变更内容
- 参考 Grok 方案后收敛边界：新增“ChatGPT Plus 自用账号台账”，只管理自有 Plus 账号资产、续费日期、TRY 余额、设备/Profile 和合规状态，不做自动登录、不导出密码、不接入用户 `/v1` 路由。
- 管理端新增 Plus 账号登记/编辑表、摘要指标和账号列表，支持状态、合规、地区、到期和余额展示。
- 后端新增 `/api/admin/plus-accounts` 管理接口，返回数据统一脱敏；Plus 密码备注纳入 runtime 敏感字段加密，`/api/admin/replenishments` 可同时返回 Plus 台账摘要但不会污染上游 Key 库存。
- 回归覆盖 Plus 台账不会泄露邮箱明文/密码备注、不会生成可路由库存，避免把 Plus 账号误当作售卖 API 号源。

### 文件变更
- `apps/frist-api/server/server.js` — 新增 Plus 账号台账模型、管理 API、脱敏展示、到期摘要和加密字段
- `apps/frist-api/admin.html` / `apps/frist-api/src/admin.js` / `apps/frist-api/src/styles.css` — 新增管理端 Plus 台账入口、表单、摘要和列表样式
- `apps/frist-api/tests/business-flow.test.mjs` / `apps/frist-api/tests/server.test.mjs` — 覆盖管理端入口和 Plus 台账安全边界
- `docs/006-registries.md` / `docs/007-operations.md` / `docs/009-health.md` — 同步入口、运营规则和健康状态

## [2026-05-04] Frist-API 兑换码售卖主链路
> 领域: `backend` | `frontend` | `docs`
> 影响模块: `Frist-API`, `Billing`, `Redeem`, `Admin`, `docs`
> 关联问题: HI-864

### 变更内容
- 放弃个人微信/支付宝收款码自动识别路线，避免收款风险和用户上传截图的糟糕体验；用户端主路径改为“第三方平台购买兑换码，站内核销自动到账”。
- 管理端新增兑换卡批量生成、批次导出、卡密状态展示，生成内容可直接给闲鱼自动发货或客服系统使用。
- 后端新增运行数据里的 `redemptionCards` 库存，兑换码一次性核销，成功后绑定用户并标记已兑换；旧测试兑换码继续兼容。
- 用户端充值页改为购买兑换码引导，独立兑换码页突出自动到账，并预留闲鱼商品链接位置。
- 已部署到腾讯云 `/opt/frist-api`，远端应用备份为 `backups/frist-api-app-20260504-152551-before-redemption-codes.tgz`，运行数据备份为 `backups/runtime-20260504-152551-before-redemption-codes.json`；公网首页 200，游客看板返回 5 个套餐和 11 个模型，未授权 `/v1/models` 为 401，容器为 healthy，远端真实生成/兑换/重复兑换拒绝闭环通过。
- 验证结果: `node --check apps/frist-api/server/server.js apps/frist-api/src/admin.js apps/frist-api/src/app.js` 通过；Frist-API `npm test` 为 123/123 通过；聚焦 `node --test tests/core.test.mjs tests/business-flow.test.mjs tests/server.test.mjs` 为 114/114 通过；`git diff --check` 通过。

### 文件变更
- `apps/frist-api/server/server.js` — 新增兑换卡生成接口、卡密库存、一次性核销和管理端脱敏展示
- `apps/frist-api/admin.html` / `apps/frist-api/src/admin.js` — 新增卡密生成、复制导出和卡密状态列表
- `apps/frist-api/index.html` / `apps/frist-api/src/app.js` / `apps/frist-api/src/styles.css` — 充值页和兑换页改为闲鱼兑换码主路径并预留购买链接
- `apps/frist-api/tests/core.test.mjs` / `apps/frist-api/tests/business-flow.test.mjs` / `apps/frist-api/tests/server.test.mjs` — 覆盖用户端入口、管理端钩子和卡密一次性兑换
- `docs/006-registries.md` / `docs/007-operations.md` / `docs/009-health.md` — 同步兑换码售卖 SOP 和健康状态

## [2026-05-04] Frist-API 支付回调、邮箱找回和运行数据加密
> 领域: `backend` | `frontend` | `deploy` | `docs`
> 影响模块: `Frist-API`, `Payments`, `Auth`, `New-API Migration`, `docs`
> 关联问题: HI-850, HI-853, HI-859, HI-863

### 变更内容
- 注册流程接入 SMTP 验证码邮件，继续保留公开模式不回显验证码；新增忘记密码请求和确认接口，验证码过期后不可复用。
- 充值链路新增微信支付 Native 和支付宝当面付预创建下单；微信/支付宝异步通知完成验签、解密和按订单号幂等入账，重复回调不会重复加钱。
- 充值页补充人工确认、微信 Native、支付宝当面付三种支付方式选择；接口未配置时会明确提示，不会误导用户已经自动入账。
- Frist-API runtime JSON 增加 AES-256-GCM 字段加密，保护用户 `fk-live-*` Key 和上游 `rawKey`，兼容旧明文文件读取并在保存时迁移为密文。
- 新增 New-API 迁移 dry-run 脚本，先只输出用户、Token、订单、日志和风险提示，不默认写入生产 New-API。
- 免费域名公网实测后，将过渡入口从被腾讯 DNSPod 拦截的 `sslip.io` 切到当前可用的 `frist-api.101-43-41-96.nip.io`；Let’s Encrypt 验证被 connection reset 拦住，HTTPS 仍建议后续走自有域名或 Cloudflare Tunnel。
- Docker Compose 和生产环境模板新增邮箱找回、运行数据加密、微信支付、支付宝支付相关环境变量。
- 验证结果: `node --check apps/frist-api/server/server.js apps/frist-api/server/payments.js apps/frist-api/src/app.js apps/frist-api/src/serverClient.js scripts/frist_api_newapi_migration_dry_run.mjs` 通过；Frist-API `npm test` 为 123/123 通过；`git diff --check` 通过；New-API 迁移 dry-run 空数据验证通过。

### 文件变更
- `apps/frist-api/server/server.js` / `apps/frist-api/server/payments.js` — 接入支付下单、回调验签/解密、幂等入账、邮箱验证码/找回密码和 runtime 字段加密
- `apps/frist-api/index.html` / `apps/frist-api/src/app.js` / `apps/frist-api/src/serverClient.js` / `apps/frist-api/src/styles.css` — 补齐忘记密码入口、支付方式选择和支付反馈
- `apps/frist-api/tests/server.test.mjs` / `apps/frist-api/tests/core.test.mjs` — 覆盖邮箱、支付、幂等、加密、公开模式配置和前端入口
- `scripts/frist_api_newapi_migration_dry_run.mjs` — 新增 New-API 迁移演练报告脚本
- `docker-compose.frist-api.yml` / `apps/frist-api/deploy/production.env.example` — 登记新增生产环境变量
- `docs/006-registries.md` / `docs/007-operations.md` / `docs/009-health.md` — 同步新接口、支付回调、域名方案和剩余运维风险

## [2026-05-04] Frist-API 仓库清理与离线恢复体验
> 领域: `frontend` | `docs`
> 影响模块: `Frist-API`, `docs`
> 关联问题: HI-862

### 变更内容
- 补齐后端不可用时的用户恢复路径：工作台显示“后端暂不可用”恢复条，说明当前为空数据模式，并提供一键重新连接按钮。
- 重新连接按钮复用现有 Dashboard 加载链路，成功后自动隐藏恢复条，失败时保留明确错误提示。
- 同步 Frist-API Web 操作注册表、快速启动文档和 HEALTH，并修正系统健康摘要接口的新版文档路径，避免文档和接口仍指向已删除的旧编号文件。

### 文件变更
- `apps/frist-api/index.html` — 增加后端恢复提示和重新连接入口
- `apps/frist-api/src/app.js` — 增加离线恢复条渲染和重试逻辑
- `apps/frist-api/src/styles.css` — 增加恢复提示的桌面/移动样式
- `apps/frist-api/tests/core.test.mjs` / `apps/frist-api/tests/business-flow.test.mjs` — 增加离线恢复体验回归钩子
- `packages/clawbot/src/api/routers/system.py` — 健康摘要读取新版 `docs/009-health.md`
- `docs/005-quickstart.md` / `docs/006-registries.md` / `docs/009-health.md` — 同步操作入口、文档路径和健康状态

## [2026-05-04] Frist-API DeepSeek 官方模型对齐
> 领域: `frontend` | `backend` | `ai-pool` | `docs`
> 影响模块: `Frist-API`, `CC Switch`, `Codex`, `DeepSeek`, `docs`
> 关联问题: HI-858, HI-861

### 变更内容
- 用 DeepSeek 官方 live 文档重新核对 Codex DeepSeek 导入逻辑：官方 OpenAI 兼容入口继续可使用 `https://api.deepseek.com/v1`，但默认模型已不应继续锁定旧 `deepseek-chat`。
- 将 DeepSeek 新导入默认模型改为 `deepseek-v4-flash`，并把 `deepseek-v4-pro` 加入 DeepSeek 模型清单；`deepseek-chat` / `deepseek-reasoner` 继续保留为旧配置兼容，避免已有导入立刻失效。
- 同步 Workbench 模型目录、CC Switch 指引、New-API 桥接默认模型和服务端默认目录，避免前端、后端、桥接层显示不同模型。
- 已部署到腾讯云 `/opt/frist-api`，远端应用备份为 `backups/frist-api-app-20260504-104527-before-deepseek-v4.tgz`；公网首页 200，游客看板 200，模型目录包含 `deepseek-v4-flash`，未授权 `/v1/models` 仍为 401，容器为 healthy。
- 验证结果: `node --check src/core.js src/app.js src/admin.js server/server.js server/shared.js server/newApiBridge.js` 通过；聚焦 `node --test tests/core.test.mjs tests/server.test.mjs` 为 90/90 通过；Frist-API `npm test` 为 118/118 通过；`make new-api-check` 确认 New-API 仍同步到 GitHub latest `v1.0.0-rc.2`。

### 文件变更
- `apps/frist-api/src/core.js` — DeepSeek 默认模型和强度排序改为 v4 优先，保留旧模型兼容
- `apps/frist-api/src/app.js` / `apps/frist-api/index.html` — 同步前端模型目录和 Codex DeepSeek 指引
- `apps/frist-api/server/server.js` / `apps/frist-api/server/shared.js` / `apps/frist-api/server/newApiBridge.js` — 同步服务端目录、探测候选和 New-API 桥接默认模型
- `apps/frist-api/tests/core.test.mjs` / `apps/frist-api/tests/server.test.mjs` — 覆盖新默认模型和旧模型兼容
- `docs/009-health.md` / `docs/007-operations.md` — 同步审计结论和仍需真实 DeepSeek Key 实测的闭环项

## [2026-05-04] Frist-API 用户体验与安全审计修复
> 领域: `backend` | `frontend` | `docs`
> 影响模块: `Frist-API`, `Auth`, `Workbench UI`, `docs`
> 关联问题: HI-850, HI-851, HI-852, HI-860

### 变更内容
- 明确本轮审计范围为 `apps/frist-api` 模块、New-API 同步桥接、部署配置和用户实际路径；不将其描述为 OpenEverything 全仓所有模块审计。
- 将 Frist-API 新注册和改密密码从 SHA-256 迁移为 Node 内置 PBKDF2-SHA256 慢哈希；历史 SHA-256 用户登录成功后自动升级哈希，不新增依赖、不要求一次性数据库迁移。
- HTTPS 公网网关或反向代理 HTTPS 请求下，注册和登录 Session Cookie 自动增加 `Secure`，继续保留 `HttpOnly` 和 `SameSite=Lax`。
- 删除未使用的旧 SHA-256 密码哈希导出，减少后续维护时误用旧逻辑的风险。
- 补齐用户端和管理端动态 `innerHTML` 字段转义，覆盖管理端库存摘要/审计日志、用户端 API Key 属性、充值套餐、导入目标、进度条百分比等位置。
- 使用 GitHub live API 和 `make new-api-check` 确认 New-API 当前 latest release、本地 submodule 和 Compose 镜像均为 `v1.0.0-rc.2`。
- 验证结果: Frist-API `npm test` 116/116 通过；聚焦回归 `node --test tests/business-flow.test.mjs tests/server.test.mjs` 79/79 通过；语法检查和 `git diff --check` 通过；公网游客看板返回 11 个模型目录、9 个渠道检查并包含 DeepSeek。

### 文件变更
- `apps/frist-api/server/server.js` — 增加 PBKDF2 密码哈希、旧哈希登录迁移和 HTTPS `Secure` Cookie
- `apps/frist-api/server/shared.js` — 移除未使用的旧 SHA-256 密码哈希导出
- `apps/frist-api/src/app.js` — 补齐动态 HTML 转义和百分比钳制
- `apps/frist-api/src/admin.js` — 补齐管理端库存摘要与审计日志转义
- `apps/frist-api/tests/business-flow.test.mjs` / `apps/frist-api/tests/server.test.mjs` — 增加密码哈希迁移、Cookie Secure 和 HTML 转义回归
- `docs/009-health.md` — 同步已修复问题和仍需闭环的架构缺口

## [2026-05-04] Frist-API 模型测试台按 New-API 控制台逻辑重构
> 领域: `frontend` | `docs`
> 影响模块: `Frist-API`, `Playground`, `Model Catalog`, `docs`
> 关联问题: HI-858

### 变更内容
- 参考 New-API 的 Playground、模型目录和使用记录页面组织方式，把 Frist-API 广场从单一下拉聊天框改为“模型浏览器 + 当前模型详情 + 连通诊断 + 测试台”。
- 模型选择恢复搜索、分组筛选、可用状态、供应商、端点类型和计费信息展示，避免用户误以为只剩少量模型。
- 模型广场增加搜索框和一键跳转测试台，模型卡片可直接选择测试或复制模型名。
- 保留 Refero 深色工作台视觉和 Frist-API 的 CC Switch / Codex / DeepSeek 特色，不改网关计费、路由和 New-API 桥接业务逻辑。
- 已部署到腾讯云 `/opt/frist-api`，远端应用备份为 `backups/frist-api-app-20260504-090503.tgz`；公网模型测试台返回 12 行模型入口，游客看板返回 11 个模型目录和 9 个服务检查，未授权 `/v1/models` 仍为 401。
- 验证结果: `node --check apps/frist-api/src/app.js apps/frist-api/src/admin.js apps/frist-api/server/server.js` 通过；Frist-API `npm test` 114/114 通过；`git diff --check` 通过；Playwright 桌面/390px 移动端截图无横向溢出。

### 文件变更
- `apps/frist-api/index.html` — 重构广场布局，新增模型浏览器、诊断区、快捷提示和模型目录搜索
- `apps/frist-api/src/app.js` — 增加模型筛选、选择、状态摘要和测试台诊断渲染
- `apps/frist-api/src/styles.css` — 增加测试台、模型行、当前模型面板和响应式样式
- `apps/frist-api/tests/business-flow.test.mjs` / `apps/frist-api/tests/core.test.mjs` — 覆盖 New-API 风格模型选择和测试台 UI 钩子

## [2026-05-04] Frist-API Refero 风格控制台 UI 改造
> 领域: `frontend` | `docs`
> 影响模块: `Frist-API`, `Workbench UI`, `docs`
> 关联问题: HI-858

### 变更内容
- 借鉴 Refero Hyperstudio 风格，把 Frist-API 用户端和管理端统一为深色控制台视觉：黑色画布、琥珀重点、绿色可用状态、8px 圆角和更克制的层级阴影。
- 保留现有前端路由和业务逻辑，仅通过 `data-design-system="refero-hyperstudio"`、CSS token 和可复用组件类调整整体 UI 壳。
- 首页模型消耗、渠道连通、最近日志、模型目录、使用记录和 API Key 列表增加生产可用空态；数据加载阶段增加骨架行和 `aria-busy`。
- 使用记录页额外增加表格外独立空态，避免小屏首次访问时只看到横向滚动表格里的截断提示。
- 静态预览或后端返回非 JSON 时，不再把 `Unexpected token` 这类技术错误直接暴露给用户，统一提示后端暂不可用并保留空数据壳。
- 工作台导航增加 `aria-current="page"`，Token 趋势条增加 `role="img"` 与描述标签，继续保留跳转主内容和可见焦点态。
- 验证结果: `node --check apps/frist-api/src/app.js` 通过；Frist-API `npm test` 114/114 通过。

### 文件变更
- `apps/frist-api/index.html` / `apps/frist-api/admin.html` — 接入 Refero 风格设计系统标记、缓存版本和初始加载语义
- `apps/frist-api/src/styles.css` — 新增深色控制台设计 token、按钮/卡片/表格/图表/空态/骨架屏可复用样式
- `apps/frist-api/src/app.js` — 增加加载态、空态、当前页无障碍状态和图表可访问标签
- `apps/frist-api/tests/core.test.mjs` — 增加 Refero 风格、加载态和可访问性回归钩子
- `docs/006-registries.md` / `docs/009-health.md` — 同步 Frist-API UI 状态和入口说明

## [2026-05-03] Frist-API 登录验证码与 CC Switch 体验修正
> 领域: `frontend` | `backend` | `docs`
> 影响模块: `Frist-API`, `CC Switch`, `Playground`, `docs`
> 关联问题: HI-855, HI-858

### 变更内容
- 登录接口移除验证码校验，保留 IP 频率限制；注册继续要求验证码挑战。
- 注册验证码从简单加法改为多题型挑战，支持字符位置、倒序、数字抽取和混合算式，并限制单个挑战错误次数。
- 账户弹窗只在注册模式显示验证码，切回登录会清空验证码状态。
- 工作台左侧导航移除数字编号，只保留清晰页面名称。
- 广场输入框支持 Enter 直接发送，Shift+Enter 保留换行。
- CC Switch 页面压缩冗余文字，突出 Claude 不带 `/v1`、Codex 必须带 `/v1` 等关键点，并把流程图里的 Codex 终端配置改为可复制。
- 腾讯云 `/opt/frist-api` 已部署本轮改动，远端代码备份为 `backups/frist-api-app-20260504-073450.tgz`，运行数据备份为 `backups/runtime-20260504-073450.json`；目标测试账号总可用额度已校准为 `$1000.00`。
- 验证结果: 本地 Frist-API `npm test` 114/114 通过；语法检查和 `git diff --check` 通过；Playwright 桌面/移动检查登录验证码、注册挑战、CC Switch 页面和移动端横向溢出通过；远端本机/公网首页 200，验证码接口正常，未授权 `/v1/models` 401，容器 `healthy`。

### 文件变更
- `apps/frist-api/server/server.js` — 调整登录/注册验证码策略并增强验证码挑战
- `apps/frist-api/index.html` — 移除侧栏编号，重构 CC Switch 教程重点和可复制终端块
- `apps/frist-api/src/app.js` — 登录免验证码、注册专用验证码、广场 Enter 发送和流程图复制交互
- `apps/frist-api/src/styles.css` — 优化 CC Switch 布局密度、重点标红和导航样式
- `apps/frist-api/tests/*.mjs` — 覆盖注册验证码、登录免验证码、侧栏编号移除、广场 Enter 发送和 CC Switch 可复制终端
- `docker-compose.frist-api.yml` / `apps/frist-api/deploy/production.env.example` — 登记验证码错误次数配置
- `docs/006-registries.md` / `docs/007-operations.md` / `docs/009-health.md` — 同步入口、生产配置和健康状态

## [2026-05-03] Frist-API 接入 New-API 业务桥接与定时同步
> 领域: `backend` | `infra` | `docs`
> 影响模块: `Frist-API`, `New-API`, `CC Switch`, `Docker Compose`, `GitHub Actions`, `docs`
> 关联问题: HI-859

### 变更内容
- 新增 GitHub Actions 定时同步任务，每天检查 `QuantumNous/new-api` 最新非草稿 release；若 submodule 或 compose 镜像落后，自动执行 `make new-api-sync` 并创建同步 PR。
- 新增 Frist-API 服务端 New-API 桥接层，启用后由 New-API 承接用户看板、API Key 创建/禁用/删除、兑换码、使用日志、订阅/充值/邀请读取和可选 `/v1` 网关代理。
- 保留 Frist-API 自研账号壳、Workbench UI、CC Switch/Codex/OpenCode/OpenClaw/Hermes 导入、DeepSeek 官方 API 配置、余额预警、补号助手和本地 JSON 兜底；New-API 未启用或不可用时仍走原逻辑。
- Docker Compose 和生产环境模板新增 `FRIST_API_NEWAPI_*` 配置，真实 token、用户 ID 和服务器密钥只允许放服务器环境变量，不写入仓库。
- Codex + DeepSeek 闭环继续保持官方 OpenAI 兼容端点 `https://api.deepseek.com/v1`，测试覆盖 CC Switch 导入配置、`auth.json`、`config.toml` 和 `/v1/responses` 网关代理。
- 验证结果: Frist-API `npm test` 113/113 通过；聚焦 New-API/Codex 回归 5/5 通过；`make new-api-check` 确认当前仍为最新 `v1.0.0-rc.2`；`docker compose -f docker-compose.newapi.yml config` 通过。

### 文件变更
- 当时的 New-API Scheduled Sync workflow — 新增 New-API 定时同步 PR 自动化；该 workflow 后续随 Sub2API 切换删除
- `apps/frist-api/server/newApiBridge.js` — 新增 New-API 业务桥接层
- `apps/frist-api/server/server.js` — 接入桥接层，保留本地业务逻辑兜底
- `apps/frist-api/tests/server.test.mjs` — 覆盖 New-API dashboard/token/import/gateway 闭环
- `docker-compose.frist-api.yml` — 透传 `FRIST_API_NEWAPI_*` 环境变量
- `apps/frist-api/deploy/production.env.example` — 登记 New-API 生产配置模板
- `docs/006-registries.md` / `docs/007-operations.md` / `docs/009-health.md` — 同步注册表、运维 SOP 和系统状态

## [2026-05-03] New-API 最新版升级与 Git 同步机制
> 领域: `backend` | `infra` | `docs`
> 影响模块: `New-API`, `Frist-API`, `ClawBot API`, `Docker Compose`, `docs`
> 关联问题: HI-859

### 变更内容
- 将 `QuantumNous/new-api` 作为 Git submodule 引入 `packages/new-api-upstream`，当前固定到最新 release `v1.0.0-rc.2`。
- `docker-compose.newapi.yml` 从 `calciumion/new-api:v0.12.6` 升级到 `calciumion/new-api:v1.0.0-rc.2`，源码指针和镜像版本保持一致。
- 新增 `scripts/sync_new_api_upstream.sh`，支持 `check` 和 `update`；`check` 会检查 GitHub 最新非草稿 release、submodule 指针和 compose 镜像 tag，发现落后时返回非 0，便于接入 CI/定时巡检。
- 新增 `make new-api-check` / `make new-api-sync` 统一入口，避免手工改镜像版本或直接复制上游代码。
- 扩展 ClawBot `newapi.py` 代理端点，新增 API Key 搜索/创建/编辑/禁用、使用日志、Token 趋势、订阅、兑换码、价格、充值配置和邀请返利接口代理；业务逻辑仍由 New-API 上游服务执行。
- New-API v1 后台接口需要 `New-Api-User` 头，代理层新增 `NEWAPI_ADMIN_USER_ID` 环境变量并同步测试，避免只配 access token 后认证失败。
- 研究结论: Frist-API 业务替换应采用“Frist-API 保留品牌壳 + New-API 内网服务承接账号/Key/渠道/计费/日志/订阅/兑换/支付”的代理与数据迁移方案，不再从旧本地 New-API 代码直接迁移。

### 文件变更
- `.gitmodules` / `packages/new-api-upstream` — 新增 New-API 上游 submodule，固定到 `v1.0.0-rc.2`
- `docker-compose.newapi.yml` — 升级 New-API 镜像并登记同步入口
- `scripts/sync_new_api_upstream.sh` — 新增上游版本检查和同步脚本
- `Makefile` — 增加 `new-api-check` / `new-api-sync`
- `packages/clawbot/src/api/routers/newapi.py` — 扩展 New-API 业务代理端点并补 `New-Api-User` 头
- `packages/clawbot/tests/test_newapi_router.py` — 覆盖新增代理路径和认证头
- `packages/clawbot/config/.env.example` — 登记 `NEWAPI_ADMIN_USER_ID`
- `docs/006-registries.md` / `docs/007-operations.md` / `docs/009-health.md` — 同步注册表、升级 SOP 和当前状态

## [2026-05-03] Frist-API Workbench 腾讯云部署与 New-API 上游检查
> 领域: `frontend` | `infra` | `docs`
> 影响模块: `Frist-API`, `Docker Compose`, `New-API`, `docs`
> 关联问题: HI-858, HI-859

### 变更内容
- 已将 Frist-API Workbench UI 外壳、使用记录、美元展示、扩展 CC Switch 导入和 Codex DeepSeek 配置同步部署到腾讯云 `/opt/frist-api`。
- 部署前已备份远端应用代码，运行数据、远端 `.env` 和真实密钥未同步、未覆盖。
- `docker-compose.frist-api.yml` 补齐余额预警 SMTP 环境变量透传，避免生产容器读取不到服务器环境配置。
- 远端 `frist-api-server` 已重新创建并恢复 `healthy` 状态，公网首页、游客看板、验证码、隐藏管理页和未授权模型接口冒烟通过。
- 按用户要求暂停从旧本地 New-API 逻辑迁移，改为先检查 GitHub 上游；当前最新 New-API 为 `v1.0.0-rc.2`，本地 `docker-compose.newapi.yml` 仍固定在旧版 `calciumion/new-api:v0.12.6`，后续应先做数据备份和升级演练。

### 文件变更
- `docker-compose.frist-api.yml` — 透传 `FRIST_API_SMTP_*` 和 `FRIST_API_BALANCE_ALERT_FROM_NAME`
- `docs/002-changelog.md` — 记录部署、验证和 New-API 上游检查结果
- `docs/009-health.md` — 同步 Frist-API 服务器部署和 New-API 版本状态

## [2026-05-03] Frist-API Workbench UI 外壳与美元计价
> 领域: `frontend` | `backend` | `ai-pool` | `docs`
> 影响模块: `Frist-API`, `CC Switch`, `New-API Adapter`, `docs`
> 关联问题: HI-858, HI-859

### 变更内容
- 用户端改成工作台式控制台外壳，保留顶部唯一 Frist-API Logo，移除侧栏重复品牌块。
- 仪表盘补齐今日请求、今日消费、今日 Token、累计 Token、累计消费、平均响应、性能指标和模型连通指标卡。
- 首页新增模型消耗圆形占比、Token 使用趋势、最近使用日志和服务可用性区块。
- API 管理新增“搜索名称或 key”、API 端点展示，以及禁用、编辑、删除、复制等图标化操作。
- 新增使用记录、我的订阅、兑换码、邀请返利和个人资料页面；使用记录展示 API 密钥、模型、推理强度、端点、类型、计费模式和 TOKEN。
- CC Switch 导入范围扩展并校验 Claude、Codex、Gemini、OpenCode、OpenClaw、Hermes、Harmes；Codex + DeepSeek 输出官方 OpenAI 兼容端点 `https://api.deepseek.com/v1`，真实 DeepSeek Key 未写入仓库。
- 用户侧余额、消费、模型价格、New-API 归一化数据和余额预警展示统一改为美元；充值仍按人民币生成美元额度。
- 已接入 New-API dashboard/token/usage/channel 的用户侧适配与脱敏归一化；完整 New-API 业务逻辑替换仍登记为架构迁移待办。
- 验证结果: Frist-API 语法检查通过；聚焦回归 3/3 通过；全量 `npm test` 112/112 通过；Playwright 已补桌面和移动截图。

### 文件变更
- `apps/frist-api/index.html` — 重做用户工作台外壳、新增页面和仪表盘区块
- `apps/frist-api/src/app.js` — 接入新路由、指标渲染、API 搜索、使用记录、CC Switch DeepSeek 流程
- `apps/frist-api/src/styles.css` — 新增工作台、指标卡、图表、记录表和新增页面响应式样式
- `apps/frist-api/src/core.js` — 扩展 CC Switch 客户端、DeepSeek 官方端点和导入配置
- `apps/frist-api/src/serverClient.js` — 归一化仪表盘、记录、日志和美元展示数据
- `apps/frist-api/src/businessFlow.js` — 同步业务流中的美元额度和导入状态
- `apps/frist-api/src/newApiClient.js` — 将 New-API 用户、Token、Usage、Channel 数据归一化到用户端美元展示
- `apps/frist-api/server/server.js` / `apps/frist-api/server/shared.js` — 输出新仪表盘字段、使用记录、最近日志和 DeepSeek 模型目录
- `apps/frist-api/tests/*.test.mjs` — 覆盖新外壳、API 搜索、使用记录、美元计价、CC Switch 导入和 DeepSeek Key 不落库
- `docs/006-registries.md` — 登记新增 Frist-API Web 操作入口
- `docs/009-health.md` — 登记 UI 壳完成与 New-API 完整替换剩余架构迁移
- `docs/002-changelog.md` — 记录本次变更

## [2026-05-03] Frist-API 端到端全量审计
> 领域: `backend` | `frontend` | `docs`
> 影响模块: `Frist-API`
> 关联问题: HI-850 ~ HI-857, TD-009 ~ TD-012

### 变更内容
- 对 apps/frist-api 模块执行全量端到端审计：源码审查、测试验证、安全扫描、UX 断点分析
- 测试结果：108/108 全量通过，0 失败
- 发现并登记 8 个新问题（3 安全 + 2 UX + 3 架构）和 4 个技术债
- 安全发现：runtime.json 明文存 Key、SHA-256 密码哈希过弱、Session Cookie 缺 Secure 标记、算术验证码可绕过
- UX 断点：无忘记密码流程、服务不可用时静默降级无重试
- 架构关注：单文件 4432 行、内存态状态无法水平扩展、data store 写入失败静默吞掉

### 文件变更
- `docs/009-health.md` — 新增 HI-850~857 和 TD-009~012
> 领域: `backend` | `frontend` | `docs`
> 影响模块: `Frist-API`, `Billing`, `SMTP`, `docs`
> 关联问题: HI-848

### 变更内容
- 用户账单页新增余额预警卡片，可自定义启用状态、人民币阈值和通知邮箱，并可手动发送测试邮件。
- 网关扣费后检测余额是否从阈值上方跌到阈值以下，只发送一次品牌化低余额邮件，避免重复刷屏。
- 后端新增 SMTP 发送器和 HTML/Text 双格式邮件模板，支持 Gmail/企业邮箱应用专用密码通过服务器环境变量配置。
- 腾讯云实测发现 Gmail IPv6 SMTP 可用、IPv4 465 超时；已补 Node SMTP DNS 地址轮询和 `FRIST_API_SMTP_FAMILY`，避免默认地址选择卡死自动邮件。
- 余额预警邮件模板升级为现代事务邮件样式：首屏突出当前余额/预警阈值，补齐事件摘要、CTA、暗黑模式和移动端可读性。
- 运维与注册表同步登记余额预警按钮、接口和 SMTP 环境变量；真实邮箱密码不落盘。
- 验证结果: Frist-API 本地回归测试当前 108/108 通过；本机到 Gmail SMTP 的 TLS/SMTP greeting 阶段不稳定，腾讯云服务器已通过 Gmail 587 STARTTLS 发出新版模板测试邮件，IPv4 465 超时仍保留为已知网络限制。

### 文件变更
- `apps/frist-api/server/server.js` — 新增余额预警 API、扣费触发逻辑、SMTP 发送器和邮件模板
- `apps/frist-api/index.html` — 在账单页新增余额预警设置卡片
- `apps/frist-api/src/app.js` — 接入余额预警保存、测试邮件和页面渲染
- `apps/frist-api/src/serverClient.js` — 增加余额预警接口客户端和 Dashboard 归一化
- `apps/frist-api/src/styles.css` — 增加余额预警卡片和移动端样式
- `apps/frist-api/tests/server.test.mjs` — 覆盖配置保存、跨阈值发信和重复通知抑制
- `apps/frist-api/tests/business-flow.test.mjs` — 覆盖账单页预警控件接线
- `apps/frist-api/deploy/production.env.example` — 增加 SMTP 环境变量示例
- `docs/006-registries.md` — 登记余额预警 Web 操作入口和 SMTP 环境变量
- `docs/007-operations.md` — 补充余额预警邮件配置和测试流程
- `docs/009-health.md` — 登记 HI-848/HI-849 并调整剩余 SMTP 技术债
- `docs/002-changelog.md` — 记录本次变更

## [2026-05-03] 文档压缩：43合12，核心10个
> 领域: `docs`
> 影响模块: `docs`, `AGENTS.md`
> 关联问题: HI-847

### 变更内容
- 文档合并: 43 个编号文件按类型合并为 12 个（001-010 核心 + 011-012 附录）。
  - `004-architecture.md` ← 010 + 011（OMEGA v2 + Bot Agent 指令）
  - `005-quickstart.md` ← 020 + 021 + 022 + 023 + 027 + 028
  - `006-registries.md` ← 030 + 031 + 032 + 033（API池+命令+依赖+模块）
  - `007-operations.md` ← 024 + 025 + 026 + 029
  - `008-sop.md` ← 040 + 041（文档优先协议+错误翻译）
  - `009-health.md` ← 060 + 063 + 064（健康+经验库+需求跟踪）
  - `010-feature-specs.md` ← 050-059 + 062 + 065（16个功能规格合并）
  - `011-kiro-gateway.md` ← 034-039（6个Kiro Gateway文档合并）
  - `012-handoff.md` ← 061（重编号）
- AGENTS.md 全文更新引用路径：060→009, 061→012, 030-033→006, 040-041→008, 063→009

### 文件变更
- `docs/004-010.md` — 新建 7 个合并文档
- `docs/011-kira-gateway.md` — 新建 1 个附录
- `docs/012-handoff.md` — 重编号
- `docs/` — 删除 39 个被合并的原文件
- `AGENTS.md` — 更新所有文档路径引用

## [2026-05-03] 文档治理：全项目归集 + 编号统一 + 冗余清理
> 领域: `docs`
> 影响模块: `docs`, `AGENTS.md`, `apps/openclaw/.learnings`, `apps/openclaw/usecases`, `packages/clawbot/docs`
> 关联问题: HI-846

### 变更内容
- 归集散落文档: 将 `apps/openclaw/.learnings/`、`apps/openclaw/usecases/`、`packages/clawbot/docs/` 共 27 个文档移入 `docs/` 根目录，统一编号命名
- 删除冗余: 移除 `packages/clawbot/docs/archive/`（3 个旧部署包说明）、`product-copy.txt`（闲鱼营销文案）、`final-checklist.txt`（含过期密钥的旧清单）、`architecture-ru.md`（冗余俄文翻译）、`packages/clawbot/docs/readme.md`（已过时子目录索引）
- 强化规则: 在 `AGENTS.md` 中新增「硬性规则」：docs/ 内禁止子目录、禁止非编号文件名、`docs/` 为文档唯一合法存放位置、排除范围清单、新增文档四步流程
- 编号扩展: docs/ 从 19 个扩展到 43 个，新增 011/026/028/029/034-039/050-059/062-065
- 索引同步: `docs/003-docs-index.md` 全面重写，标注编号空缺供后续使用

### 文件变更
- `docs/` — 新增 24 个编号文档，从散落位置移入
- `AGENTS.md` — §9 重写为硬性规则 + §10 新增子目录/命名禁令 + §6 新增文档变更触发索引
- `docs/003-docs-index.md` — 全文重写，增补编号空缺表
- `docs/060-health.md` — 更新文档治理状态
- `apps/openclaw/.learnings/` — 清空（内容已迁移到 docs/063-064）
- `apps/openclaw/usecases/` — 清空（内容已迁移到 docs/050-059/062/065）
- `packages/clawbot/docs/` — 清空（仅保留空目录）

## [2026-05-03] Frist-API 新余额站公网真测与图片广场优化
> 领域: `frontend` | `ai-pool` | `deploy` | `docs`
> 影响模块: `Frist-API`, `Playground`, `Gateway`, `docs`
> 关联问题: HI-845

### 变更内容
- 上游切换: 接入新的授权余额站 `/v1` 上游，并保留 CPA JSON/chong 仅作为人工风控备用入口。
- 公网实测: 通过裸 IP 网关完成 `/v1/models`、`gpt-5.5` Chat Completions 和 `gpt-image-2` Images 真请求，图片响应返回有效 1024x1024 PNG。
- 广场优化: 用户端广场生图默认带 `quality: low`、`output_format: png` 和 `n: 1`，让低带宽服务器上的图片连通测试更稳定。
- 验证结果: Frist-API 本地回归保持 104 条通过，腾讯云容器 `frist-api-server` 处于 healthy 状态。

### 文件变更
- `apps/frist-api/src/app.js` — 广场图片请求默认使用轻量 PNG 参数
- `apps/frist-api/tests/business-flow.test.mjs` — 覆盖广场图片请求参数接线
- `docs/002-changelog.md` — 记录新余额站公网真测和广场优化
- `docs/025-frist-api-quickstart.md` — 同步图片广场实测口径
- `docs/060-health.md` — 登记 HI-845

## [2026-05-03] Frist-API 余额站上游与工作台首页适配
> 领域: `backend` | `frontend` | `ai-pool` | `deploy` | `docs`
> 影响模块: `Frist-API`, `Gateway`, `Replenishment`, `Workbench`, `docs`
> 关联问题: HI-844

### 变更内容
- 上游策略: 适配授权余额站模式，管理员补号可以直接录入供应商根地址；当根地址返回网站 HTML 壳时，补号探测会自动尝试同域 `/v1` OpenAI 兼容路径。
- 探测校验: Chat Completions、Responses 和 Images 的 2xx 响应都要符合对应 OpenAI 兼容 JSON 结构，避免把网页、余额页或错误页误判为健康接口。
- 额度判断: 2xx HTML 文本不再参与余额不足判断，避免供应商 Dashboard 文案里的 balance 字样误触发 `quota_failed`。
- 公开部署: Docker Compose 透传 `FRIST_API_ALLOW_INSECURE_PUBLIC_HTTP`，便于无域名裸 IP 阶段按显式开关完成公网验收。
- 用户界面: 首页从营销 Hero 改为控制台工作台布局，参考余额站后台的信息密度，新增紧凑左侧导航、顶部操作区和余额/API Key/消耗/模型连通四个核心状态卡。
- 验证准备: 新增根地址 HTML 自动切 `/v1` 的回归测试，保障 `gpt-5.5`、`gpt-image-2` 这类余额站模型进入广场实测前先通过真实 API 路径。

### 文件变更
- `apps/frist-api/server/server.js` — 增加根地址与 `/v1` 候选路由探测、响应结构校验和 2xx 额度判断保护
- `apps/frist-api/tests/server.test.mjs` — 覆盖供应商根地址返回 HTML 时自动路由到 `/v1`
- `apps/frist-api/index.html` — 首页改为工作台控制台布局
- `apps/frist-api/src/styles.css` — 新增工作台、左侧 rail、控制台指标卡和响应式样式
- `apps/frist-api/tests/core.test.mjs` — 更新首页布局边界测试
- `docker-compose.frist-api.yml` — 透传无域名 HTTP 验收开关
- `apps/frist-api/deploy/production.env.example` — 补充生产环境变量示例
- `docs/024-frist-api-operator-runbook.md` — 增加授权余额站接入和根地址 `/v1` 自动探测说明
- `docs/025-frist-api-quickstart.md` — 同步工作台首页、余额站探测和测试覆盖说明
- `docs/031-command-registry.md` — 登记工作台 rail 和控制台主区入口
- `docs/060-health.md` — 登记 HI-844

## [2026-05-03] Frist-API 上游失效库存落盘
> 领域: `backend` | `ai-pool` | `docs`
> 影响模块: `Frist-API`, `Gateway`, `Inventory`, `docs`
> 关联问题: HI-843

### 变更内容
- 真实公网实测发现: 线上两枚上游 Key 已被供应商禁用，但库存仍停留在 `healthy`，导致广场继续展示 `gpt-5.5` / `gpt-image-2` 可用。
- 网关修复: 当同一模型的所有候选上游都因认证失败、网络失败或 5xx 被摘除后，返回 503 响应但保留本次库存状态变更，避免异常路径回滚。
- 库存下线: 失效上游会被持久化为 failed/exhausted，后续 `/v1/models`、广场和导入模型清单不再展示这类不可用模型。
- 验证结果: 新增所有候选上游被拒绝时的回归测试，确认 503 后库存状态会落盘且模型清单下线。

### 文件变更
- `apps/frist-api/server/server.js` — 将全候选失败路径改为可落盘的 503 网关响应
- `apps/frist-api/tests/server.test.mjs` — 覆盖所有上游被禁用时的库存持久化和模型下线行为
- `docs/002-changelog.md` — 记录公网实测暴露的问题与修复
- `docs/025-frist-api-quickstart.md` — 同步回归测试数量
- `docs/060-health.md` — 登记 HI-843

## [2026-05-03] Frist-API 备用渠道人工风控入口
> 领域: `backend` | `frontend` | `ai-pool` | `docs`
> 影响模块: `Frist-API`, `Admin`, `Gateway`, `Replenishment`, `docs`
> 关联问题: HI-842

### 变更内容
- 备用渠道: 管理端补号新增 `CPA JSON 备用渠道`、`chong 备用渠道` 和其他人工备用渠道类型，只作为库存登记和应急入口。
- 风险放行: 备用渠道默认写入隔离态，必须管理员选择已人工核验并勾选路由确认后，才会变成健康可路由库存。
- 路由保护: `/v1/models`、用户导入模型清单、广场和实际网关调用只使用已放行库存；隔离或禁止状态不会访问上游。
- JSON 入口: 管理端 Key 列表支持粘贴 JSON 数组，便于人工导入已合规确认的 API 兼容凭证；不实现 OAuth Token 抓取、批量刷新或绕过风控逻辑。
- 隐私边界: 用户端 Dashboard 不暴露 `cpa_json_backup`、`chong_backup`、风险备注或上游来源字段。
- 验证结果: Frist-API `npm test` 扩展到 102 条，覆盖备用渠道隔离、人工放行、图片生成和广场连通入口。

### 文件变更
- `apps/frist-api/server/server.js` — 增加渠道类型、风险状态、人工确认字段和路由过滤
- `apps/frist-api/admin.html` — 管理端新增备用渠道类型、风险状态、人工确认和风险备注入口
- `apps/frist-api/src/admin.js` — 提交/展示备用渠道风险字段，并支持 JSON 数组粘贴
- `apps/frist-api/src/businessFlow.js` — 业务流补齐备用渠道隔离/放行规则
- `apps/frist-api/tests/server.test.mjs` — 覆盖 CPA JSON 隔离和 chong 人工放行后的路由行为
- `apps/frist-api/tests/business-flow.test.mjs` — 覆盖管理端入口接线和备用渠道状态机
- `docs/024-frist-api-operator-runbook.md` — 增加备用渠道人工风控操作边界
- `docs/025-frist-api-quickstart.md` — 同步管理端备用渠道和测试覆盖说明
- `docs/031-command-registry.md` — 登记备用渠道风险字段入口
- `docs/060-health.md` — 登记 HI-842

## [2026-05-03] Frist-API 广场 5.5/image2 连通修复
> 领域: `backend` | `frontend` | `ai-pool` | `docs`
> 影响模块: `Frist-API`, `Gateway`, `Playground`, `Replenishment`, `docs`
> 关联问题: HI-841

### 变更内容
- 方案收口: 保留 Frist-API 商业展示层 + New-API 内网路由层的解耦思路，但明确生产库存只接授权供应商、自有额度或明确可转售额度，不把批量 OAuth Session / 来路不明 JSON 号源当生产方案。
- 模型别名: 将广场和补号里常见的 `5.5`、`gpt5.5`、`gpt-55` 统一清洗为 `gpt-5.5`，将 `image2`、`gpt-image2`、`gpt_image_2` 统一清洗为 `gpt-image-2`。
- 图片探测: 补号严格探测遇到图片模型时直接请求 `/images/generations`，避免用 `/chat/completions` 或 `/responses` 误判 `image2` 库存不可用。
- 广场实测: 用户广场新增“实测连通”按钮和状态摘要，能直接展示当前模型的成功/失败、耗时和返回结果；图片模型会展示生成结果。
- 管理摘要: 管理端脱敏库存返回 `lastProbeStatus` / `lastProbeReason`，便于确认图片库存是 `image_probe_ok` 而不是信任写入。
- 验证结果: 新增回归覆盖 `5.5` / `image2` 别名、图片模型补号探测和广场实测入口；Frist-API 测试集扩展到 100 条。

### 文件变更
- `apps/frist-api/src/core.js` — 增加 `5.5` / `image2` 等广场常用别名归一化
- `apps/frist-api/server/server.js` — 新增图片模型探测路径、图片默认候选模型和脱敏探测状态返回
- `apps/frist-api/src/app.js` — 新增广场连通实测状态、按钮逻辑和耗时摘要
- `apps/frist-api/index.html` — 新增广场连通实测按钮和状态展示位置
- `apps/frist-api/src/styles.css` — 新增广场实测状态样式
- `apps/frist-api/tests/core.test.mjs` — 覆盖广场模型别名清洗
- `apps/frist-api/tests/server.test.mjs` — 覆盖 `image2` 网关归一化和图片模型补号探测
- `apps/frist-api/tests/business-flow.test.mjs` — 覆盖广场连通实测入口接线
- `docs/024-frist-api-operator-runbook.md` — 明确授权库存边界和图片模型探测规则
- `docs/025-frist-api-quickstart.md` — 同步广场实测、别名和图片探测说明
- `docs/031-command-registry.md` — 登记广场连通实测入口
- `docs/060-health.md` — 登记 HI-841 修复状态

## [2026-05-03] 项目文档和冗余产物清理
> 领域: `docs` | `infra`
> 影响模块: `docs`, `Frist-API`, `workspace-cleanup`
> 关联问题: HI-840

### 变更内容
- 文档压缩: 主项目 `docs/` Markdown 从 37 个压缩到 19 个，保留核心入口、操作指南、注册表、SOP 和状态文档。
- 过时报告清理: 删除 5 月前审计/设计/归档报告、散落的 Bot 模型旧审计，以及 Frist-API 历史截图和散落测试截图。
- Frist-API 文档收口: 腾讯云部署和公网验收要点合并进 `docs/024-frist-api-operator-runbook.md` / `docs/025-frist-api-quickstart.md`，不再单独维护临时部署报告。
- 本地冗余清理: 清理可重建构建产物、缓存、浏览器模型缓存、运行日志和本地开发虚拟环境；仓库体积从约 2.4GB 降到约 196MB，保留业务数据库、测试、Bot 人设、Skill 文件和第三方包文档。
- 服务器清理: 只清腾讯云上的日志、缓存、临时文件、构建缓存和 Docker 非运行对象；系统日志从 264MB 降到 176MB，不删除共享服务器的业务项目、数据库、测试代码、运行虚拟环境、浏览器登录态或 Docker 业务卷。
- 验证结果: `apps/frist-api` 执行 `npm test`，99 passed, 0 failed；`docs/` 根目录保持 19 个 Markdown。

### 文件变更
- `docs/003-docs-index.md` — 重写为 19 个核心文档索引
- `docs/024-frist-api-operator-runbook.md` — 合并腾讯云部署和公网验收操作要点
- `docs/025-frist-api-quickstart.md` — 保留当前入口和本地/容器运行说明
- `docs/060-health.md` — 登记本次冗余清理
- `README.md` — 移除旧审计入口，指向当前 Frist-API 文档
- `apps/openclaw/BOT_MODEL_AUDIT.md` — 删除 2026-03 旧 Bot 模型审计报告

## [2026-05-02] Frist-API OpenCode 外网阻塞修复
> 领域: `backend` | `frontend` | `ai-pool` | `deploy` | `docs`
> 影响模块: `Frist-API`, `CC Switch`, `OpenCode`, `Gateway`, `docs`
> 关联问题: HI-839, HI-833, HI-836

### 变更内容
- 外网复现: 用公网 Quick Tunnel 注册新用户、创建 Key、补日卡额度后复现并验证广场和 OpenCode 路由，不再只做本地冒烟。
- 一键导入入口: CC Switch 页面把“一键导入 / 复制链接 / 导出模型清单”提前到长教程流程图之前，用户不用先读完教程才能找到主操作。
- OpenCode 路由: 网关新增 `/openai/chat/completions`、`/v1/openai/chat/completions`、`/openai/responses`、`/v1/openai/responses` 和图片前缀别名，兼容 OpenCode/CC Switch 生成的 OpenAI 前缀路径。
- Chat Completions 降级: 上游 Chat Completions 返回 404 或不支持时，自动把请求转换到 Responses，再把 Responses 响应转回 Chat Completions，修复 `Route /openai/chat/completions not found`。
- 模型清单补齐: OpenCode/Codex 导入 URL、base64 配置和前端模型清单同步补 `gpt-5.4-mini`、`gpt-5.3-codex` 等兼容字段，避免外部 GUI 只显示默认 `gpt-5.5`。
- OpenCode 桌面导入: `ccswitch://` 的 OpenCode `config.models` 改为 OpenCode/CC Switch 实际读取的模型对象映射，修复桌面端导入后编辑框仍只有 `gpt-5.5` 的问题。
- 公网验证: 腾讯云 `/opt/frist-api` 已同步并重启，`frist-api-server` healthy；公网 `gpt-5.5` Chat/Responses、OpenCode 前缀 Chat、`gpt-5.4` Responses 和 OpenCode 导入模型清单均返回成功。

### 文件变更
- `apps/frist-api/server/server.js` — 新增 OpenCode 前缀路由、Chat Completions→Responses 降级、Responses→Chat Completions 响应转换和 Codex 模型排序
- `apps/frist-api/index.html` — 将一键导入主操作和导出模型清单前置到长教程之前
- `apps/frist-api/src/styles.css` — 增加一键导入主操作区域样式
- `apps/frist-api/src/app.js` — 补齐 `gpt-5.3-codex` 前端模型强度排序
- `apps/frist-api/src/core.js` — 补齐 `gpt-5.3-codex` 导入配置模型强度排序，并按 OpenCode 真实配置格式输出完整 `models` 映射
- `apps/frist-api/tests/core.test.mjs` — 覆盖 OpenCode 桌面导入配置的完整模型映射
- `apps/frist-api/tests/server.test.mjs` — 覆盖 Chat Completions 降级、OpenCode 前缀路由和完整模型清单导出
- `apps/frist-api/tests/business-flow.test.mjs` — 覆盖一键导入主操作必须位于长教程之前
- `docs/060-health.md` — 登记 HI-839 并更新 Frist-API 当前状态
- `docs/002-changelog.md` — 记录本次外网阻塞修复和验证结果

## [2026-05-02] Frist-API 用户闭环断点修复与价格管理
> 领域: `frontend` | `backend` | `ai-pool` | `deploy` | `docs`
> 影响模块: `Frist-API`, `Admin`, `CC Switch`, `Pricing`, `docs`
> 关联问题: HI-838, TD-006, TD-008

### 变更内容
- 登录注册反馈: 用户登录、注册、验证码和密码错误现在都会显示明确成功/失败状态，按钮进入处理中状态，避免用户不知道请求是否生效。
- API Key 创建反馈: 创建 Key 改为真实服务端链路，成功/失败均有明确提示，不再本地伪造或静默失败。
- 连通性刷新: 刷新按钮保持在首页看板，不再误跳使用教程；渠道连通性升级为供应商、模型数量、可用状态和延迟摘要。
- 模型命名清洗: 上游返回的历史 Claude Haiku 别名统一归一为官方展示名，用户页、导入链接和模型广场不再暴露 `claude-haiku-4-5-20251001` 这类非规范名称。
- Mock 数据移除: 删除用户端网页 mock 数据文件和 New-API demo fallback；服务不可用时展示真实空态，不再展示演示套餐、演示用户或伪造 Key。
- 价格管理: 新增管理端套餐与模型计价 JSON 编辑，默认套餐按用户确认的 5 档 Codex API 额度配置；模型计价按官方成本价走，优惠只体现在充值套餐。
- 实机预审: 本地浏览器完整跑通注册、登录、创建 Key、刷新连通性、模型广场、充值套餐和管理端价格保存；腾讯云容器重新部署并通过本地/公网冒烟。
- 测试额度: 测试账号已通过管理端人工入账补足 60 刀等值日卡额度，便于实测 API 聚合、模型切换、上下文粘滞和无缝降级。
- 文档治理: 主项目 `docs/` 目录统一迁移到根目录编号命名，清理子目录层级，并同步代码、测试和 SOP 中的文档路径。

### 文件变更
- `apps/frist-api/server/server.js` — 新增价格管理 API、模型名清洗、真实空态数据、登录/Key 错误反馈和渠道连通性聚合
- `apps/frist-api/src/app.js` — 接入登录/注册/Key/连通性显式反馈，移除 mock 兜底并刷新价格/模型/导入状态
- `apps/frist-api/src/core.js` — 新增官方模型名归一化和跨客户端导入模型清单清洗
- `apps/frist-api/src/serverClient.js` — 补齐价格、登录、Key 和 dashboard 请求归一化
- `apps/frist-api/src/businessFlow.js` — 业务流去除演示数据依赖并同步价格配置
- `apps/frist-api/src/admin.js` — 管理端新增套餐与模型价格读取/保存
- `apps/frist-api/src/newApiClient.js` — 移除本地 demo store fallback
- `apps/frist-api/src/data.js` — 删除网页 mock 数据源
- `apps/frist-api/index.html` — 用户端补齐反馈容器、渠道连通性区域和真实空态
- `apps/frist-api/admin.html` — 管理端新增价格管理区
- `apps/frist-api/src/styles.css` — 增加反馈状态、连通性摘要和价格管理样式
- `apps/frist-api/tests/*.mjs` — 覆盖登录反馈、Key 创建反馈、价格管理、模型清洗、mock 移除和网关计费
- `docs/024-frist-api-operator-runbook.md` — 补齐价格管理、测试额度和支付人工操作指南
- `docs/060-health.md` — 登记 HI-838 并更新 Frist-API 当前状态
- `docs/002-changelog.md` — 记录本次用户闭环和价格管理收口

## [2026-05-02] Frist-API 跨模型导入实操流程图
> 领域: `frontend` | `ai-pool` | `docs`
> 影响模块: `Frist-API`, `CC Switch`, `Claude Code`, `Codex`, `Payments`
> 关联问题: HI-837, HI-836

### 变更内容
- Claude Code 实操引导: CC Switch 页新增“ChatGPT / OpenAI 模型导入 Claude Code”流程图，按真实 Claude 菜单标出左上角 `Developer`、`Configure Third-Party Inference...`、`Gateway base URL`、`Gateway API key`、`Gateway auth scheme`、`Model list` 和 `Skip login-mode chooser`。
- Codex 实操引导: 新增“Claude 模型导入 Codex”流程图，标出本站 CC Switch 目标选择、模型家族选择、一键导入、Codex `API 请求地址`、`auth.json`、`wire_api = "responses"`、默认 Claude 模型和 MCP 段。
- 动态字段: 流程图中的 Frist-API 地址、Claude/Codex 地址、默认 OpenAI 模型、默认 Claude 模型会按当前站点和用户可用模型自动刷新。
- 运营手册: 补齐个人微信/支付宝收款码试运营步骤、60 刀日卡测试额度折算说明、支付宝当面付和微信支付 Native 的小白级开通步骤，并加入对应官方接口文档入口。
- 测试额度: 已通过后台人工入账路径给测试账号加入 60 刀等值日卡额度，用于实测 API 聚合、模型切换和上下文粘滞。

### 文件变更
- `apps/frist-api/index.html` — 新增两张跨模型导入实操流程图和逐步字段说明
- `apps/frist-api/src/app.js` — 接入流程图动态字段刷新和当前场景高亮
- `apps/frist-api/src/styles.css` — 新增仿真实操窗口、菜单、设置页、Codex 配置页和响应式样式
- `apps/frist-api/tests/business-flow.test.mjs` — 覆盖流程图关键文案、字段和 MCP/Responses 配置提示
- `docs/024-frist-api-operator-runbook.md` — 扩写个人码收款、测试额度、支付宝/微信支付操作指南
- `docs/060-health.md` — 登记 HI-837 并更新 Frist-API 当前状态
- `docs/002-changelog.md` — 记录本次导入引导和支付手册改动

## [2026-05-02] Frist-API Codex MCP 默认增强
> 领域: `frontend` | `ai-pool` | `docs`
> 影响模块: `Frist-API`, `CC Switch`, `Codex`, `MCP`
> 关联问题: HI-836

### 变更内容
- Codex 最强默认配置: Codex 目标导出的 `config.toml` 现在默认写入 Playwright、Superpowers 和 open-computer-use MCP，继续保留 Responses、1M 上下文、90 万压缩阈值、xhigh 推理和工具搜索。
- CC Switch 兼容: 导入链接的隐藏配置同步携带 `mcpServers` / `mcp_servers` 元数据；如果 CC Switch 支持 MCP 字段，可以直接消费，若只写入 `config.toml` 也能保留 MCP 段。
- 用户引导: Codex 导入说明新增 MCP 和 Computer Use 权限提示，明确 CC Switch 能写配置，但首次使用桌面电脑操作能力仍需本机系统授权。
- 部署验证: 已同步到腾讯云 `/opt/frist-api`，容器 `frist-api-server` 为 healthy；公网 `/` 和 `/api/frist/dashboard` 返回 200，未授权 `/v1/models` 返回 401，普通 `/admin.html` 返回 404，冒烟脚本通过。

### 文件变更
- `apps/frist-api/src/core.js` — 为 Codex 生成默认 MCP TOML 和导入元数据
- `apps/frist-api/src/app.js` — CC Switch 页新增 Codex 最强开发配置和 MCP 权限提示
- `apps/frist-api/tests/core.test.mjs` — 覆盖 Codex MCP TOML 和 CC Switch 元数据
- `apps/frist-api/tests/business-flow.test.mjs` — 覆盖用户页 MCP 引导文案
- `docs/024-frist-api-operator-runbook.md` — 增加 Codex MCP 默认增强和验收项
- `docs/025-frist-api-quickstart.md` — 增加 Codex MCP 配置说明
- `docs/002-changelog.md` — 记录本次 MCP 默认增强

## [2026-05-02] Frist-API CC Switch 跨模型家族一键导入
> 领域: `backend` | `frontend` | `ai-pool` | `docs`
> 影响模块: `Frist-API`, `CC Switch`, `Claude Code`, `Codex`, `Payments`
> 关联问题: HI-836

### 变更内容
- Claude Code 导入: CC Switch 的 Claude 目标现在导出 `anthropic-messages` 配置，自动写入 `ANTHROPIC_AUTH_TOKEN`、`ANTHROPIC_BASE_URL`、默认模型、Tool Search 和团队模式字段，支持把 ChatGPT/OpenAI 模型通过 Frist-API 路由给 Claude Code 使用。
- Codex 导入: Codex 目标继续导出 Responses provider 配置，并标记 Claude 模型跨家族导入；网关在上游不支持 Responses 时自动降级到 Chat Completions，保证 Claude 模型也能被 Codex 调用。
- 网关适配: 新增 `/v1/messages` 和根路径 `/messages` 的 Anthropic Messages 入口，接收 Claude Code 请求后转换为 OpenAI 兼容上游请求，再转回 Anthropic 响应。
- 用户引导: CC Switch 页面新增“目标客户端 + 模型家族”双选择、Claude 开发者模式/第三方 API 步骤说明、Codex + Claude 导入说明和对应样式。
- 支付最后一公里: 运营手册补齐个人收款二维码人工入账、支付宝当面付、微信支付 Native、商户号、签名密钥、异步通知、验签和密钥保管操作指南。
- 回归测试: `npm test` 当前为 90/90 通过，覆盖 Claude Code Anthropic Messages、Codex Responses fallback、跨模型家族导入 UI 和支付人工操作清单。

### 文件变更
- `apps/frist-api/src/core.js` — 调整五客户端导入配置，新增 Claude Code JSON、Anthropic 格式字段和跨家族导入标记
- `apps/frist-api/server/server.js` — 新增 Anthropic Messages 网关入口、Responses 到 Chat Completions 降级和认证头兼容
- `apps/frist-api/index.html` — CC Switch 页面新增模型家族选择和跨家族导入引导
- `apps/frist-api/src/app.js` — 接入模型家族切换、跨导入文案和手动配置同步刷新
- `apps/frist-api/src/styles.css` — 增加导入家族选择和跨导入引导样式
- `apps/frist-api/tests/core.test.mjs` — 覆盖 Claude Code 使用 ChatGPT 模型、Codex 使用 Claude 模型的导入配置
- `apps/frist-api/tests/server.test.mjs` — 覆盖 `/v1/messages` 和 Responses fallback 网关链路
- `apps/frist-api/tests/business-flow.test.mjs` — 覆盖用户页跨家族导入引导和支付最后一公里文档
- `docs/024-frist-api-operator-runbook.md` — 补齐收款二维码、支付宝当面付、微信支付 Native 和密钥操作指南
- `docs/060-health.md` — 登记 HI-836 并更新 Frist-API 测试状态
- `docs/002-changelog.md` — 记录本次 CC Switch 跨模型家族适配

## [2026-05-02] Frist-API 首屏焦点流与品牌标识重做
> 领域: `frontend` | `docs`
> 影响模块: `Frist-API`, `docs`
> 关联问题: HI-835, HI-828, HI-833

### 变更内容
- 品牌回归: 顶部品牌标识改回黑底、白色斜切和红色识别点的黑白红方案，与 favicon 保持同一识别语言。
- 视觉节奏: 首页从单块大英雄卡改成“主控台 + 右侧说明 + 核心指标”双栏结构，主行动入口只保留一个，避免用户第一眼被多个等宽模块分散。
- 任务轨道: 快捷入口改成不对称任务轨道，CC Switch 作为首个主路径，其余入口保留为轻量辅助动作。
- 指标聚焦: 余额、消耗、连通三项状态继续保留，但移入右侧说明区，减少首屏横向铺满的机械感。
- 回归测试: 更新前端结构测试，覆盖新的 hero-flow 与 hero-aside 钩子以及主路径优先级。

### 文件变更
- `apps/frist-api/index.html` — 调整首屏结构、品牌文案和快捷入口排序
- `apps/frist-api/src/styles.css` — 重做品牌标识、首屏双栏布局、任务轨道和响应式断点
- `apps/frist-api/tests/core.test.mjs` — 补充首屏焦点流与品牌回归断言
- `docs/060-health.md` — 登记 HI-835 用户体验优化记录
- `docs/002-changelog.md` — 记录本次首屏视觉优化

## [2026-05-02] Frist-API 生产入口恢复与商业化审计
> 领域: `deploy` | `infra` | `docs` | `ai-pool`
> 影响模块: `Frist-API`, `Tencent Cloud`, `Nginx`, `docs`
> 关联问题: HI-834, TD-006, TD-007, TD-008

### 变更内容
- 线上恢复: 复现裸 IP 入口 `ERR_CONNECTION_REFUSED`，确认 Frist-API 容器健康但只绑定本地端口，Nginx 未监听 Frist-API 测试端口；已同步服务器代码和 Compose 文件，并在 Nginx 增加独立测试端口反代。
- 多项目保护: 保留服务器 80/443 现有默认项目，不抢占裸 IP 根路由；Frist-API 在无固定域名阶段通过独立测试端口和 Tunnel 验收。
- 商业化审计: 新增生产就绪报告，按架构、组件结构、数据流、API 设计、数据库模式、缓存策略、性能瓶颈、清洁架构拆分和人工开通清单审计当前状态。
- 运营手册: 扩写人工收款、支付平台、固定域名、SMTP、Turnstile、备份、告警、合规和模型列表规则，明确哪些事项必须由业务方在后台开通。
- 模型风险登记: 明确生产模型列表不能靠硬编码宣传，必须由上游 `/v1/models`、真实探测和官方目录校验共同决定；默认最强模型只能从用户真实可用列表中选择。
- 验证结果: 公网测试入口 `/` 和 `/api/frist/dashboard` 返回 `200 OK`；未授权 `/v1/models` 返回 `401`；公网冒烟脚本通过。

### 文件变更
- `docs/080-frist-api-production-readiness-2026-05-02.md` — 新增生产就绪审计、架构和商业化缺口报告
- `docs/024-frist-api-operator-runbook.md` — 扩写人工开通、支付、域名、邮箱、防刷、模型列表和生产验收清单
- `docs/026-frist-api-tencent-deploy.md` — 补充裸 IP 拒绝连接排查流程和多项目服务器反代边界
- `docs/060-health.md` — 登记 HI-834 和 TD-008，并更新 Frist-API 当前生产化状态
- `docs/002-changelog.md` — 记录本次线上入口恢复和商业化审计

## [2026-05-02] Frist-API 导出模型清单可见化
> 领域: `frontend` | `backend` | `ai-pool` | `docs`
> 影响模块: `Frist-API`, `CC Switch`, `Codex`, `OpenCode`
> 关联问题: HI-833

### 变更内容
- 导出页新增模型清单: CC Switch 页直接展示默认模型、可用模型数量和完整模型列表，用户切换 Codex/OpenCode 时可以立即确认导出结果。
- 兼容字段补强: 导入 URL 和 base64 配置同时输出 `models`、`availableModels`、`available_models`、`modelList`、`model_list`、`supportedModels`、`defaultModel` 和 `default_model`，降低外部 GUI 只读取某个字段时只显示单模型的风险。
- 目标切换同步: 在 CC Switch 页切换 Codex/OpenCode/OpenClaw/Hermes 或模型分组后，同步刷新导入链接、手动配置和模型清单，避免链接已变但配置区域仍是旧目标。
- 官方命名排序: 补充 `gpt-5.4-nano` 的官方模型排序兜底；实际导出仍以用户库存和模型目录里的真实可用模型为准，不凭空展示未供给模型。
- 回归测试: Frist-API 当前 `make frist-api-test` 为 84/84 通过，新增覆盖 Codex/OpenCode 全模型导出、兼容字段和用户页模型清单。

### 文件变更
- `apps/frist-api/index.html` — CC Switch 页新增默认模型、可用模型数量和模型列表展示区域，并更新前端资源版本
- `apps/frist-api/src/app.js` — 增加导出模型清单渲染，目标/分组切换时同步刷新配置
- `apps/frist-api/src/styles.css` — 增加导出模型清单和默认模型标签样式
- `apps/frist-api/src/core.js` — 补齐导入 URL 与 provider 配置里的模型列表兼容字段
- `apps/frist-api/server/server.js` — 导入 URL 接口同步返回默认模型和完整可用模型列表
- `apps/frist-api/tests/core.test.mjs` — 覆盖 Codex/OpenCode 全模型导出和兼容字段
- `apps/frist-api/tests/business-flow.test.mjs` — 覆盖用户页模型清单和配置同步接线
- `apps/frist-api/tests/server.test.mjs` — 覆盖服务端 Codex/OpenCode 导出同一份完整模型列表
- `docs/060-health.md` — 登记 HI-833
- `docs/031-command-registry.md` — 登记导出模型清单入口

## [2026-05-02] Frist-API 用户端完整度补强
> 领域: `frontend` | `backend` | `ai-pool` | `docs`
> 影响模块: `Frist-API`, `CC Switch`, `docs`
> 关联问题: HI-832

### 变更内容
- 账户入口: 右上角注册/登录从简陋账户区改为模态弹窗，登录/注册按模式只显示当前动作，并补齐 `dialog`、`tab`、`aria-selected` 和 Escape 关闭语义。
- 页面返回: 广场、数据、模型、教程、API Key、充值、CC Switch 等子页面统一增加返回首页入口，避免用户进入导入或管理页后迷路。
- 广场测试: 每条测试消息支持单条删除，广场支持一键清空，图片模型和文本模型继续走同一用户 Key 与网关链路。
- API Key 管理: 用户侧支持 Key 改名、删除和单 Key 状态展示，服务端新增 `PATCH /api/frist/token/:id` 改名和 `DELETE /api/frist/token/:id` 删除。
- CC Switch 导入: 导出配置改为默认最强模型 `gpt-5.5`，同时列出用户可用模型；若库存包含 `gpt-5.5-pro` 等官方 Pro 档，会自动把 Pro 档排到默认模型；OpenCode/Codex/Hermes 走 Responses 兼容格式并默认开启流式、图片、工具搜索等能力。
- 使用教程: 教程页补齐 OpenCode、Hermes 和 Harmes 入口，手动配置同步输出默认模型、模型列表和功能开关。
- 回归测试: Frist-API 当前 `make frist-api-test` 为 83/83 通过，新增覆盖账户弹窗语义、返回按钮、广场删除/清空、API Key 改名/删除、OpenCode 模型导出和官方 Pro 模型优先级。

### 文件变更
- `apps/frist-api/index.html` — 重做账户弹窗结构，补齐返回首页、广场清空、教程目标和 API Key 操作入口
- `apps/frist-api/src/app.js` — 接入账户模式切换、消息删除/清空、Key 改名/删除、默认最强模型和教程配置刷新
- `apps/frist-api/src/styles.css` — 增加账户弹窗、返回按钮、消息删除、Key 名称输入和危险操作样式
- `apps/frist-api/src/core.js` — 导出默认模型、可用模型列表、Responses 配置、功能开关和 Hermes/Harmes 别名
- `apps/frist-api/src/businessFlow.js` — 本地 fallback 支持 Key 改名/删除并保留真实 Key 供导入配置使用
- `apps/frist-api/src/serverClient.js` — 增加用户 Key 改名和删除 HTTP 客户端
- `apps/frist-api/server/server.js` — 增加 Key 改名/删除接口，导入 URL 使用用户可用模型列表和最强默认模型
- `apps/frist-api/src/data.js` — 补齐默认模型目录
- `apps/frist-api/tests/business-flow.test.mjs` — 覆盖账户弹窗、返回入口、广场删除/清空、API Key 操作和教程目标
- `apps/frist-api/tests/core.test.mjs` — 覆盖 OpenCode 导出全模型列表并默认最强模型
- `apps/frist-api/tests/server.test.mjs` — 覆盖 API Key 改名和删除 HTTP 链路
- `docs/031-command-registry.md` — 登记本轮新增用户侧操作入口
- `docs/060-health.md` — 登记 HI-832

## [2026-05-02] Frist-API 一次性管理员身份码
> 领域: `backend` | `frontend` | `deploy` | `docs`
> 影响模块: `Frist-API`, `Admin`, `docs`
> 关联问题: HI-831

### 变更内容
- 管理员激活: 登录后的用户可在右上角账户区域输入一次性身份码，把当前账号升级为管理员；身份码成功使用后自动作废。
- 管理入口: 账号升级后显示运营入口，可直接进入独立管理页；普通用户仍不会看到库存、补号和管理工作台。
- 管理鉴权: 管理 API 现在支持管理员登录态，也保留强随机管理员令牌作为后备方式，避免用户把账号密码交给开发者手动升级。
- 部署配置: Docker 和生产环境模板新增 `FRIST_API_ADMIN_CLAIM_CODES`，支持逗号分隔的一批一次性身份码。
- 操作说明: 补充管理员首登、人工入账、支付接口、固定域名、SMTP 和 Turnstile 的人工操作清单。
- 验证结果: 身份码链路已通过红绿回归，当前 Frist-API 测试扩展到 79 条。

### 文件变更
- `apps/frist-api/server/server.js` — 增加一次性管理员身份码校验、管理员登录态鉴权和静态管理页登录态放行
- `apps/frist-api/index.html` — 在账户区域加入身份码输入和管理员可见运营入口
- `apps/frist-api/src/app.js` — 接入身份码激活、管理员入口显示和前端状态刷新
- `apps/frist-api/src/admin.js` — 管理页支持用管理员登录态访问管理 API，管理员令牌降级为后备方式
- `apps/frist-api/src/serverClient.js` — 增加身份码激活接口和管理员字段归一化
- `apps/frist-api/src/businessFlow.js` — 同步用户状态中的管理员标记
- `apps/frist-api/src/styles.css` — 增加身份码行和运营入口样式
- `apps/frist-api/tests/server.test.mjs` — 覆盖身份码只能使用一次、管理员登录态可访问管理 API
- `apps/frist-api/tests/business-flow.test.mjs` — 覆盖用户页身份码接线且不暴露管理令牌输入框
- `docker-compose.frist-api.yml` — 增加 `FRIST_API_ADMIN_CLAIM_CODES`
- `apps/frist-api/deploy/production.env.example` — 增加一次性管理员身份码配置
- `docs/025-frist-api-quickstart.md` — 同步管理员首登链路和测试范围
- `docs/026-frist-api-tencent-deploy.md` — 同步腾讯云部署安全边界和上线检查
- `docs/024-frist-api-operator-runbook.md` — 新增必须人工操作的支付、域名、邮箱和验证码清单
- `docs/031-command-registry.md` — 登记身份码和运营入口选择器
- `docs/060-health.md` — 登记 HI-831

## [2026-05-02] Frist-API 用户广场与数据教程页
> 领域: `frontend` | `backend` | `ai-pool` | `docs`
> 影响模块: `Frist-API`, `CC Switch`, `docs`
> 关联问题: HI-830

### 变更内容
- 用户广场: 新增低密度模型测试页，用户可直接选择模型对话；`gpt-image-2` 等图片模型走图片生成窗口。
- 数据看板: 新增模型消耗分布、消耗列表和服务可用性聚合视图，把原渠道连通性收敛成客户能看懂的可用状态。
- 模型广场: 新增客户安全模型目录，展示模型家族、用途、上下文和计价，不泄露上游号商、请求地址或原始 Key。
- 使用教程: 新增 Codex、Claude、OpenClaw 的配置页，输出 JSON/TOML 配置和 macOS/Windows 一键配置命令。
- 网关链路: `/v1/images/generations` 纳入同一套用户 Key、日卡库存、上游路由和故障切换链路，方便网页广场直接测试生图模型。
- 公网入口: 已同步部署到腾讯云 Frist-API 容器，并通过 Cloudflare Quick Tunnel 提供可信 HTTPS 外网入口，当前用户端和 `/v1` 网关都走同一公开域名。
- 证书验证: 当前 HTTPS 入口证书由 Google Trust Services 签发给 `trycloudflare.com`，可满足今晚外部实测；长期生产仍需绑定自有固定域名。
- 移动端修复: 小屏下页面标题和操作控件改为纵向排布，避免“广场”等标题被按钮或选择器挤压。
- 冒烟脚本: 公网检查改为落盘再 grep，避免 `curl | grep -q` 的断管噪音污染交付日志。
- 验证结果: `npm test` 当前 78/78 通过；`node --check` 覆盖用户端、核心配置、浏览器客户端和轻量后端；`git diff --check` 无空白错误；敏感词扫描无命中。

### 文件变更
- `apps/frist-api/index.html` — 增加广场、数据看板、模型广场和使用教程四个用户页面
- `apps/frist-api/src/app.js` — 接入模型选择、对话/生图测试、数据看板、模型目录和配置教程渲染
- `apps/frist-api/src/core.js` — 生成 macOS/Windows 一键配置命令并保持 Frist-API 品牌清洗
- `apps/frist-api/server/server.js` — 增加客户安全模型目录和图片生成网关路由
- `apps/frist-api/src/styles.css` — 补齐新页面视觉层次、移动端标题布局和轻量动效
- `apps/frist-api/deploy/smoke-test.sh` — 稳定公网冒烟检查输出，覆盖用户端、验证码、隐藏管理入口和模型目录
- `apps/frist-api/tests/core.test.mjs` — 覆盖一键配置命令不泄露上游字段
- `apps/frist-api/tests/business-flow.test.mjs` — 覆盖广场、数据看板、模型广场和教程页接线
- `apps/frist-api/tests/server.test.mjs` — 覆盖客户安全模型目录和图片生成路由
- `docs/025-frist-api-quickstart.md` — 同步用户组件、网关路由和测试覆盖
- `docs/026-frist-api-tencent-deploy.md` — 同步 Quick Tunnel HTTPS 入口、动态域名直签限制和长期域名方案
- `docs/031-command-registry.md` — 登记新增用户页面操作入口
- `docs/060-health.md` — 更新 Frist-API 测试数和 HI-830
- `docs/002-changelog.md` — 记录本次用户组件补齐

## [2026-05-02] Frist-API 公开可测链路与隐藏管理入口
> 领域: `backend` | `frontend` | `ai-pool` | `deploy` | `docs`
> 影响模块: `Frist-API`, `CC Switch`, `Tencent Cloud`, `docs`
> 关联问题: HI-829

### 变更内容
- 公开入口: Frist-API 已同步到腾讯云 `5566` 临时公网端口，用户端可直接进行注册、登录、创建 Key、充值申请和 CC Switch 导入实测。
- 防刷门槛: 用户注册和登录接入轻量验证码挑战与 IP 频率限制，公开模式继续关闭验证码回显和演示充值。
- 管理入口: `/admin.html` 默认返回 404，必须带独立隐藏入口码后才加载静态管理页；管理 API 仍要求管理员令牌。
- 上游清洗: 补号订单文本会归一化请求地址、卡类型、额度、到期时间、认证字段、额外请求头和模型分组；用户侧导入只暴露 Frist-API 供应商标识、官网入口、用户 Key 和公开网关地址。
- 兼容导入: CC Switch 导入继续覆盖 Claude、Codex、OpenCode、OpenClaw、Hermes，并输出 `auth.json`、`config.toml`、Responses 接口格式、上下文/压缩、`setCacheKey` 和工具搜索配置。
- 中转策略: 网关按小时卡、日卡、月卡、不限时、默认池顺序消耗库存；同一会话通过 `x-frist-session-id` 或 `metadata.frist_session_id` 粘滞到健康上游，异常时带完整请求体切换。
- 库存告警: 低库存阈值通知钩子已接入 `FRIST_API_LOW_INVENTORY_WEBHOOK`，后续可接 OpenClaw 的 Telegram/微信通知入口。
- 验证结果: `npm test` 当前 74/74 通过；公网 `challenge` 可用、游客 Dashboard 零消耗、普通 `/admin.html` 返回 404。

### 文件变更
- `apps/frist-api/server/server.js` — 增加验证码/限流、隐藏管理页入口、上游字段清洗、低库存通知、会话粘滞和库存优先级链路
- `apps/frist-api/src/core.js` — 统一生成 Frist-API 品牌 CC Switch 导入配置，避免上游供应商信息泄露到用户端
- `apps/frist-api/src/app.js` — 右上角账户菜单接入验证码挑战和用户链路低密度展示
- `apps/frist-api/src/serverClient.js` — 接入 `/api/frist/challenge` 并提交验证码字段
- `apps/frist-api/tests/business-flow.test.mjs` — 覆盖订单文本清洗、日卡/小时卡优先级、用户/管理端解耦和验证码接线
- `apps/frist-api/tests/server.test.mjs` — 覆盖注册验证码、限流、隐藏管理页、模型分组、认证字段、日卡轮转、会话粘滞、流式透传和低库存通知
- `docker-compose.frist-api.yml` — 暴露隐藏管理入口码、验证码、限流和低库存 Webhook 环境变量
- `apps/frist-api/deploy/production.env.example` — 同步公开部署安全环境变量
- `apps/frist-api/deploy/smoke-test.sh` — 冒烟检查新增验证码和隐藏管理入口验证
- `docs/025-frist-api-quickstart.md` — 更新当前用户/管理/网关完整链路
- `docs/026-frist-api-tencent-deploy.md` — 更新腾讯云公开验收与隐藏管理入口说明
- `docs/081-frist-api-public-snapshot-2026-05-02.md` — 归档公网用户端浏览器快照，避免根目录散落文档
- `docs/060-health.md` — 更新 Frist-API 当前测试数和 HI-829
- `docs/061-handoff.md` — 更新当前交接状态
- `docs/002-changelog.md` — 记录本次公开可测链路收口

## [2026-05-02] Frist-API 用户端降噪与五客户端导入配置
> 领域: `frontend` | `docs`
> 影响模块: `Frist-API`, `CC Switch`, `docs`
> 关联问题: HI-828

### 变更内容
- 用户端降噪: 移除客户页左侧导航、不可点击分组文字、旧版高密度说明和管理端暗示，首页只固定保留余额、模型消耗、Claude/OpenAI 连通性和导入入口。
- 首屏默认值: 公开 HTML 初始状态改为未登录、0 元和 `FA` 标识，避免后端数据加载前闪现演示套餐或演示消耗。
- 充值页: 三个充值选项改为三列排列，去掉桌面端第四列空位，让日卡、月卡、余额更像独立购买入口。
- 游客页: 未登录状态不再用演示模型消耗填空，余额、消耗和调用统计保持 0，避免客户误以为已有历史账单。
- 导入配置: CC Switch 导入参数扩展为 Claude、Codex、OpenCode、OpenClaw、Hermes 五个客户端，导入链接带 provider、请求地址、模型、auth.json 和 config.toml。
- 解耦边界: 注册/登录收进右上角账户菜单，API 页面只保留创建 Key、开关 Key 和请求地址；补号、价格解析、号源库存继续只在 `/admin.html`。
- 回归测试: Frist-API 测试扩展到 60 条，覆盖用户端禁用词、无 sticky/无 sidebar、游客零消耗、首屏低密度、五客户端导入、日卡切换、流式透传和公开模式硬门槛。

### 文件变更
- `apps/frist-api/index.html` — 简化用户端首页、账户入口、API/充值/导入页面和公开初始状态
- `apps/frist-api/src/app.js` — 接入低密度首页渲染、右上角账户菜单、充值计划和服务端导入链接刷新
- `apps/frist-api/src/serverClient.js` — 游客 Dashboard 归一化为零余额、零消耗和零调用
- `apps/frist-api/server/server.js` — 游客 Dashboard 补齐零消耗字段
- `apps/frist-api/src/core.js` — 扩展五客户端 CC Switch 导入配置和 Codex/OpenCode 手动配置生成
- `apps/frist-api/src/data.js` — 简化充值档位和默认导入目标
- `apps/frist-api/src/styles.css` — 移除 sticky/侧栏样式，调整低密度首屏和充值三列布局
- `apps/frist-api/tests/core.test.mjs` — 增加用户端降噪、首屏默认值和五客户端导入回归测试
- `apps/frist-api/tests/business-flow.test.mjs` — 同步用户/管理端解耦和导入配置测试
- `apps/frist-api/tests/new-api-adapter.test.mjs` — 增加游客零消耗归一化回归测试
- `apps/frist-api/tests/server.test.mjs` — 增加游客 Dashboard 零消耗回归测试
- `docs/025-frist-api-quickstart.md` — 同步当前公开用户链路和低密度页面结构
- `docs/031-command-registry.md` — 同步 Frist-API 当前真实 Web 操作入口
- `docs/054-2026-05-01-frist-api-mvp-design.md` — 更新 UI 方向和当前实现边界
- `docs/060-health.md` — 更新 Frist-API 测试数和 HI-828
- `docs/061-handoff.md` — 写入当前公网同步交接
- `docs/002-changelog.md` — 记录本次用户端降噪

## [2026-05-01] Frist-API 腾讯云公网验收部署
> 领域: `deploy` | `infra` | `docs`
> 影响模块: `Frist-API`, `Docker`, `Tencent Cloud`
> 关联问题: HI-827

### 变更内容
- 公网验收: 将 Frist-API 部署到腾讯云小服务器，临时开放 `5566` 端口供陌生用户访问和业务链路实测。
- 安全配置: 服务器端生成强随机管理员令牌和会话密钥，生产模式关闭演示充值和验证码回显；临时公网 HTTP 仅用于无域名阶段验收。
- 健康检查: Docker 健康检查从 `localhost` 改为 `127.0.0.1`，避免 Alpine 先解析 IPv6 `::1` 导致服务可访问但容器误报 `unhealthy`。
- 验证结果: 本机外网访问用户端和管理端均返回 `200 OK`，服务器 Docker 状态为 `healthy`，Frist-API 回归测试维持 52/52 通过。

### 文件变更
- `docker-compose.frist-api.yml` — 修正容器健康检查地址为 IPv4 loopback
- `docs/025-frist-api-quickstart.md` — 同步临时公网验收和健康检查说明
- `docs/026-frist-api-tencent-deploy.md` — 同步腾讯云临时验收端口和健康检查注意事项
- `docs/060-health.md` — 更新 Frist-API 公网验收状态
- `docs/002-changelog.md` — 记录本次公网部署

## [2026-05-01] Frist-API 公开网关生产化加固
> 领域: `backend` | `deploy` | `docs`
> 影响模块: `Frist-API`, `Docker`, `docs`
> 关联问题: HI-827

### 变更内容
- 会话粘滞: 网关支持 `x-frist-session-id`、`x-conversation-id` 和请求体 `metadata.frist_session_id`，同一对话优先固定到同一枚健康上游 Key，补入更快 Key 不会打断当前上下文。
- 故障切换: 上游余额不足、5xx 或网络失败时会清掉当前会话粘滞记录，切换到备用 Key，并完整保留原始 `messages`、`tools`、`metadata` 等请求体。
- 流式透传: `stream: true` 改为边读边转发上游 SSE 数据，不再把流式响应缓冲到结束后一次性返回。
- 计费策略: 流式请求按预估消耗先扣费，非流式请求继续优先按上游 `usage` 精确扣费。
- 生产硬门槛: `NODE_ENV=production` 或 `FRIST_API_PUBLIC_MODE=1` 时，默认管理员令牌、默认会话密钥、验证码回显、演示充值或本地 HTTP 网关地址会直接拒绝启动。
- 临时公网验收: 增加 `FRIST_API_ALLOW_INSECURE_PUBLIC_HTTP=1` 显式开关，允许无域名阶段用公网 IP 做短期验收；正式付费用户仍要求 HTTPS 域名。
- 回归测试: Frist-API 测试扩展到 52 条，覆盖会话粘滞、上下文保留、流式首包透传和公开模式安全配置。

### 文件变更
- `apps/frist-api/server/server.js` — 增加网关会话粘滞、流式透传、故障切换粘滞清理和公开模式配置校验
- `apps/frist-api/tests/server.test.mjs` — 增加公开网关生产化回归测试
- `apps/frist-api/deploy/production.env.example` — 增加生产模式和公开模式环境变量
- `docker-compose.frist-api.yml` — 暴露 `NODE_ENV` 和 `FRIST_API_PUBLIC_MODE` 配置
- `docs/025-frist-api-quickstart.md` — 同步会话粘滞、流式透传、公开模式硬门槛和测试覆盖
- `docs/026-frist-api-tencent-deploy.md` — 同步服务器上线检查项
- `docs/060-health.md` — 更新 Frist-API 当前状态和 HI-827
- `docs/002-changelog.md` — 记录本次公开网关生产化加固

## [2026-05-01] Frist-API 用户端商业化 UI 重构
> 领域: `frontend` | `docs`
> 影响模块: `Frist-API`, `CC Switch`, `docs`
> 关联问题: Frist-API-MVP

### 变更内容
- 用户首页: 从高密度数据控制台改成商业化客户首页，首屏只固定展示今日费用、今日剩余额度和线路状态 3 个核心指标。
- 视觉风格: 去掉左侧 Logo 黑色块，改成抽象轻量标识；页面加入深绿、珊瑚、薄荷、暖白的层次色、玻璃面板和拟物阴影。
- 导航体验: 左侧导航补充分组隔断，所有用户侧入口统一为 hash 路由和 `data-route` 钩子，避免“有的能点有的不能点”的错觉。
- 渐进披露: 首页新增状态轮播、三步快捷入口、Claude/OpenAI 快速连通性和可展开模型消耗明细，减少一屏堆满信息。
- 动效: 增加首屏进入动画、轮播切换、轻微浮动和按钮按压反馈，并保留 `prefers-reduced-motion` 降级。
- 解耦边界: 用户端继续不出现补号、号商、价格解析和管理端入口；管理端 `/admin.html` 不改动。
- 回归测试: Frist-API 测试扩展到 48 条，新增客户首页降噪结构、导航可点击契约和动效钩子测试。

### 文件变更
- `apps/frist-api/index.html` — 重构用户端首页、Logo、导航隔断、轮播、核心指标和渐进展开区
- `apps/frist-api/src/app.js` — 增加首页轮播、自动切换和明细展开交互
- `apps/frist-api/src/styles.css` — 重做用户端视觉层次、玻璃/拟物面板、动画和响应式样式
- `apps/frist-api/tests/core.test.mjs` — 增加用户端商业化 UI 边界测试
- `docs/025-frist-api-quickstart.md` — 同步新用户端结构、截图和测试覆盖
- `docs/031-command-registry.md` — 登记新增轮播和展开交互入口
- `docs/060-health.md` — 更新 Frist-API 测试数
- `docs/002-changelog.md` — 记录本次用户端 UI 重构

## [2026-05-01] Frist-API 公开能用链路打通
> 领域: `frontend` | `backend` | `ai-pool` | `deploy` | `docs`
> 影响模块: `Frist-API`, `CC Switch`, `Docker`, `docs`
> 关联问题: Frist-API-MVP

### 变更内容
- 补号助手: 新增代理请求地址，补号时会对直连和代理做低成本聊天探测，自动选择成功率更高且延迟更低的路径。
- 网关路由: 上游调用优先使用补号探测得到的 `routeBaseUrl`，适配弱服务器只中转、不推理的公开试用策略。
- 模型探测: 上游不支持 `/models` 时，系统会按内置模型清单逐个低成本探测，只写入实际可用模型。
- 价格扣费: 管理端粘贴价格文本后，上游返回 `usage` 时会按输入/输出 token 和销售价扣用户套餐、加油包和上游库存。
- 日卡切换: Key 额度不足、上游余额不足、上游 5xx 或网络失败时继续自动摘除并切同池健康 Key；日卡套餐过期会清空套餐额度并切回默认套餐。
- 管理端解耦: 代理路径和库存标签只在 `/admin.html` 展示，用户端继续只保留模型消耗、Claude/OpenAI 连通性、API、充值和 CC Switch 导入。
- 回归测试: Frist-API 测试扩展到 45 条，覆盖代理/直连择优、fallback 模型探测和按真实 usage 扣费。

### 文件变更
- `apps/frist-api/server/server.js` — 增加代理路径择优、fallback 模型探测、`routeBaseUrl` 转发和按上游 usage 计费
- `apps/frist-api/admin.html` — 增加代理请求地址输入
- `apps/frist-api/src/admin.js` — 管理端提交代理地址并展示直连/代理库存标签
- `apps/frist-api/tests/server.test.mjs` — 增加代理转发、fallback 探测和 usage 扣费回归测试
- `apps/frist-api/tests/business-flow.test.mjs` — 锁定代理字段只存在于管理端
- `docs/025-frist-api-quickstart.md` — 同步公开能用链路
- `docs/026-frist-api-tencent-deploy.md` — 同步弱服务器上线检查
- `docs/054-2026-05-01-frist-api-mvp-design.md` — 同步当前实现边界和交接提示
- `docs/031-command-registry.md` — 登记管理端代理地址入口
- `docs/060-health.md` — 更新 Frist-API 测试数和已修复技术债
- `docs/061-handoff.md` — 写入本轮交接状态
- `docs/002-changelog.md` — 记录本次公开能用链路打通

## [2026-05-01] Frist-API 公开试用业务安全加固
> 领域: `frontend` | `backend` | `ai-pool` | `deploy` | `docs`
> 影响模块: `Frist-API`, `CC Switch`, `Docker`, `docs`
> 关联问题: Frist-API-MVP

### 变更内容
- 充值链路: 公开环境默认不再允许用户自助点击按钮直接增加余额；用户侧改为生成待处理充值单，管理端按邮箱人工确认入账。
- 管理端: 新增人工充值入口和 `/api/admin/customers/recharge` 接口，适配先人工收款、再后台加余额的早期运营方式。
- 兑换码: 日卡/月卡/加油包兑换码改为一次性使用，避免同一张卡被多个用户重复兑换。
- 日卡过期: 网关路由前会检查日卡/月卡到期时间，过期后清空套餐额度并切回默认套餐，防止旧卡继续走日卡池。
- 补号探测: 同一请求地址先做一次模型列表探测，再逐个 Key 做最低成本聊天健康检查，减少重复探测。
- 用户连通性: 用户侧模型连通性按模型聚合显示可用线路数量，不再把每枚上游 Key 当成一张客户状态卡。
- 部署: Docker 和生产环境模板默认关闭演示充值，避免公开部署时误开放免费额度。
- 回归测试: Frist-API 测试扩展到 42 条，覆盖待处理充值单、管理员入账、一次性兑换码、日卡过期、模型聚合连通性和补号低成本探测。

### 文件变更
- `apps/frist-api/server/server.js` — 增加待处理充值单、管理员人工入账、兑换码防复用、套餐过期、低成本探测和模型聚合健康摘要
- `apps/frist-api/index.html` — 将用户充值文案改为充值申请
- `apps/frist-api/admin.html` — 增加人工入账表单
- `apps/frist-api/src/app.js` — 用户侧充值按钮改为提交待处理充值单
- `apps/frist-api/src/admin.js` — 接入管理员人工入账接口
- `apps/frist-api/tests/server.test.mjs` — 扩展公开业务链路回归测试
- `apps/frist-api/tests/business-flow.test.mjs` — 锁定管理端人工入账入口和用户端解耦
- `apps/frist-api/deploy/production.env.example` — 增加演示充值关闭开关
- `Makefile` — 本地 Frist-API 开发启动默认回显验证码、关闭演示充值
- `docker-compose.frist-api.yml` — 生产默认关闭演示充值
- `docs/025-frist-api-quickstart.md` — 同步公开试用充值和补号规则
- `docs/026-frist-api-tencent-deploy.md` — 同步上线前检查
- `docs/031-command-registry.md` — 登记 Frist-API 管理端人工入账入口
- `docs/060-health.md` — 更新 Frist-API 当前状态
- `docs/061-handoff.md` — 更新 Frist-API 交接状态
- `docs/002-changelog.md` — 记录本次公开试用业务安全加固

## [2026-05-01] Frist-API 公开能用链路加固
> 领域: `frontend` | `backend` | `ai-pool` | `deploy` | `docs`
> 影响模块: `Frist-API`, `CC Switch`, `Docker`, `docs`
> 关联问题: Frist-API-MVP

### 变更内容
- 用户链路: 新增邮箱密码登录，重复注册会被拦截，用户端不再预填演示密码。
- 计费链路: 网关成功调用后真实扣减套餐额度和加油包额度；余额不足会在访问上游前拦截。
- 日卡切换: 除额度不足外，上游 5xx 或网络失败也会自动切到同池下一枚健康 Key，并记录管理审计。
- 补号补充: 同一请求地址下重复补同一枚上游 Key 会恢复原库存记录，不再重复堆积。
- 补号探测: 管理端支持自动探测、严格探测和信任写入；未填写模型时可通过 `/models` 自动探测并过滤坏 Key。
- 管理端: 增加探测模式选择和最近操作审计列表，库存和审计继续只在管理端展示。
- 部署: 增加生产环境变量模板、冒烟脚本和腾讯云小服务器部署说明。
- 回归测试: 扩展服务端和页面链路测试，覆盖登录、真实扣费、余额拦截、坏 Key 过滤、故障切换和补货恢复。

### 文件变更
- `apps/frist-api/server/server.js` — 增加登录、真实扣费、补号探测、库存恢复、故障切换和审计事件
- `apps/frist-api/src/serverClient.js` — 增加用户端登录接口
- `apps/frist-api/index.html` — 增加登录按钮并移除演示密码预填
- `apps/frist-api/src/app.js` — 接入登录流程
- `apps/frist-api/admin.html` — 增加探测模式和审计区域
- `apps/frist-api/src/admin.js` — 发送探测模式并渲染补号审计
- `apps/frist-api/src/styles.css` — 增加管理端审计列表样式
- `apps/frist-api/tests/server.test.mjs` — 扩展公开可用后端链路测试
- `apps/frist-api/tests/business-flow.test.mjs` — 扩展用户端/管理端页面接线测试
- `apps/frist-api/deploy/production.env.example` — 新增生产环境变量模板
- `apps/frist-api/deploy/smoke-test.sh` — 新增部署冒烟检查脚本
- `docker-compose.frist-api.yml` — 补充公开网关地址和探测超时环境变量
- `docs/025-frist-api-quickstart.md` — 同步公开试用链路和部署边界
- `docs/026-frist-api-tencent-deploy.md` — 新增腾讯云小服务器部署准备说明
- `docs/113-frist-api-public-usable-user-2026-05-01.png` — 保存用户端浏览器验证截图
- `docs/112-frist-api-public-usable-admin-2026-05-01.png` — 保存管理端浏览器验证截图
- `docs/054-2026-05-01-frist-api-mvp-design.md` — 更新当前公开试用后端边界
- `docs/060-health.md` — 更新 Frist-API 当前状态
- `docs/061-handoff.md` — 更新 Frist-API 交接状态
- `docs/002-changelog.md` — 记录本次公开可用链路加固

## [2026-05-01] Frist-API 公开试用链路后端
> 领域: `frontend` | `backend` | `ai-pool` | `deploy` | `docs`
> 影响模块: `Frist-API`, `CC Switch`, `Makefile`, `Docker`, `docs`
> 关联问题: Frist-API-MVP

### 变更内容
- 轻量后端: 新增 Node HTTP 服务，跑通用户注册、邮箱验证、充值、兑换码、创建 Key、Key 开关、Dashboard 和 CC Switch 导入接口。
- 中转网关: 新增 `/v1/chat/completions`，用户使用 `fk-live-*` 鉴权后按套餐池路由到上游 Key。
- 日卡切换: 日卡池 Key 额度不足会自动跳过；上游返回余额不足时自动标记当前 Key 耗尽并重试同池下一枚健康 Key。
- 管理端: 新增独立 `/admin.html` 补号工作台，支持管理员令牌、请求地址、池子、模型、Key 列表、价格文本和脱敏库存查看。
- 用户端接线: 用户页面优先调用轻量后端，失败时保留演示数据兜底；用户端继续不展示补号、号源和价格解析入口。
- 部署: `make frist-api-dev` 改为启动完整链路；Docker 原型改为 256MB Node 服务，适配弱服务器小范围试用。
- 回归测试: 新增服务端链路和管理端解耦测试，覆盖注册到导入、补号写入、上游脱敏和日卡自动切换。

### 文件变更
- `apps/frist-api/server/server.js` — 新增轻量 Frist-API HTTP 后端和 `/v1` 中转网关
- `apps/frist-api/src/serverClient.js` — 新增用户端浏览器 API 客户端和 Dashboard 归一化
- `apps/frist-api/src/app.js` — 用户端业务按钮优先调用真实后端，失败时回退演示状态
- `apps/frist-api/admin.html` — 新增独立管理端补号工作台
- `apps/frist-api/src/admin.js` — 新增管理端补号和库存查看逻辑
- `apps/frist-api/src/styles.css` — 新增管理端布局和响应式样式
- `apps/frist-api/tests/server.test.mjs` — 新增服务端完整链路测试
- `apps/frist-api/tests/business-flow.test.mjs` — 新增管理端独立页面边界测试
- `apps/frist-api/package.json` — 默认启动轻量后端，保留静态预览命令
- `.gitignore` — 忽略 Frist-API 本地运行数据，避免误提交用户 Key 或上游 Key
- `Makefile` — `frist-api-dev` 改为完整链路启动，新增 `frist-api-static`
- `docker-compose.frist-api.yml` — 改为轻量 Node 服务和 JSON 运行数据卷
- `docs/025-frist-api-quickstart.md` — 更新本地启动、管理端和公开试用边界
- `docs/054-2026-05-01-frist-api-mvp-design.md` — 补充公开试用后端实现边界
- `docs/114-frist-api-public-user-2026-05-01.png` — 保存用户端浏览器验证截图
- `docs/111-frist-api-public-admin-2026-05-01.png` — 保存管理端浏览器验证截图
- `docs/001-project-map.md` — 更新 Frist-API 项目登记
- `docs/031-command-registry.md` — 登记 Frist-API Web 操作入口
- `docs/060-health.md` — 登记并关闭 Frist-API 首页 403 回归
- `docs/061-handoff.md` — 更新 Frist-API 交接状态
- `docs/002-changelog.md` — 记录本次公开试用链路落地

## [2026-05-01] Frist-API 完整业务链路 MVP
> 领域: `frontend` | `ai-pool` | `docs`
> 影响模块: `Frist-API`, `CC Switch`, `docs`
> 关联问题: Frist-API-MVP

### 变更内容
- 业务链路: 新增 Frist-API 用户业务状态机，跑通注册、邮箱验证、充值、兑换码、创建 Key、开启/关闭 Key 和 CC Switch 导入。
- 用户页面: 在 API 管理页加入最小账户注册与邮箱验证入口，让网页端也能串起“注册 -> 充值 -> 创建 Key -> 导入”的闭环。
- Key 管理: API Key 列表改为按每个 Key 自己的启停状态渲染，避免多个 Key 时被全局状态误导。
- 管理链路: 新增补号报告、价格草稿、号源档案写入和日卡额度不足自动切换的可测试核心逻辑，仍保持管理端内容不进入用户页。
- 回归测试: 新增业务链路测试，覆盖用户主流程、补号应用、日卡自动切换、页面业务按钮和用户/管理端解耦边界。
- 文档: 更新快速启动、MVP 设计和会话交接，明确当前为本地模拟业务状态，真实写接口下一步接入 New-API fork。

### 文件变更
- `apps/frist-api/src/businessFlow.js` — 新增 Frist-API 用户与补号业务状态机
- `apps/frist-api/src/app.js` — 接入注册、验证、充值、兑换码、创建 Key、Key 开关、连通性刷新和 CC Switch 导入
- `apps/frist-api/index.html` — 新增用户侧注册与邮箱验证入口
- `apps/frist-api/src/styles.css` — 新增账户链路表单样式
- `apps/frist-api/tests/business-flow.test.mjs` — 新增完整业务链路回归测试
- `docs/025-frist-api-quickstart.md` — 同步当前业务闭环和验证方式
- `docs/054-2026-05-01-frist-api-mvp-design.md` — 记录当前业务链路实现边界
- `docs/061-handoff.md` — 更新 Frist-API 交接状态
- `docs/002-changelog.md` — 记录本次业务链路落地

## [2026-05-01] Frist-API 接入 New-API 前端适配层
> 领域: `frontend` | `ai-pool` | `docs`
> 影响模块: `Frist-API`, `New-API`, `docs`
> 关联问题: Frist-API-MVP

### 变更内容
- 数据接线: 新增 New-API 会话客户端和 Frist-API 数据仓库，用户控制台优先读取 New-API，接口不可用时回退演示数据。
- 归一化: 支持 New-API 用户余额、Token、用量日志和脱敏连通性快照转换为客户侧展示字段。
- 安全边界: 前端不发送管理员密钥，不暴露上游 Key、渠道 ID、号商地址等管理端字段。
- 页面接线: `app.js` 从硬编码演示数组改为通过数据仓库渲染，保留本地静态预览能力。
- Docker: 为 Frist-API 站点增加 Nginx 代理配置，同域 `/api/` 和 `/v1/` 转发到 New-API 容器。
- 测试: 新增 New-API 适配器测试，覆盖响应包装、缺失接口回退、Token 脱敏、用量分组和页面接线。
- 文档: 更新快速启动和 MVP 方案，明确下一步要在 New-API fork 中补齐用户安全接口。

### 文件变更
- `apps/frist-api/src/newApiClient.js` — 新增 New-API 会话客户端、数据仓库和归一化函数
- `apps/frist-api/src/app.js` — 页面改为优先读取数据仓库并保留演示数据兜底
- `apps/frist-api/deploy/nginx.conf` — 新增 Docker 站点代理配置
- `apps/frist-api/tests/new-api-adapter.test.mjs` — 新增 New-API 适配层回归测试
- `docker-compose.frist-api.yml` — 挂载 Frist-API Nginx 代理配置
- `docs/025-frist-api-quickstart.md` — 说明当前数据接入方式和下一步
- `docs/054-2026-05-01-frist-api-mvp-design.md` — 同步当前前端适配边界
- `docs/061-handoff.md` — 更新 Frist-API 交接状态
- `docs/002-changelog.md` — 记录本次适配层接入

## [2026-05-01] Frist-API 参考 Tabcode 的用户控制台迭代
> 领域: `frontend` | `docs`
> 影响模块: `Frist-API`, `CC Switch`, `docs`
> 关联问题: Frist-API-MVP

### 变更内容
- UI: 登录参考 `tabcode.cc/dashboard` 后，将 Frist-API 从单页堆叠改为分区式客户控制台，默认只展示仪表板。
- 信息架构: 借鉴客户侧分组导航，拆成控制台、API 与用量、模型与渠道、充值与订购、支持，继续保持管理端完全不暴露。
- 连通性: 将 Claude / OpenAI 状态卡升级为对话延迟、端点 Ping、官方状态、7 天可用性和历史状态条。
- 降噪: 合并重复的“使用统计”导航入口，并将慢速状态文案从“拥堵”调整为“可用较慢”。
- API/充值/导入: 增加 API Key 列表、充值金额按钮、兑换码入口、客户端下载和五目标 CC Switch 导入视图。
- 测试: 扩展用户端边界测试，锁定客户侧必要入口和连通性可观测字段。
- 文档: 更新快速启动指南，说明新的分区式用户端结构。

### 文件变更
- `apps/frist-api/index.html` — 改为分区式用户控制台
- `apps/frist-api/src/core.js` — 调整客户侧连通性状态文案
- `apps/frist-api/src/app.js` — 增加 hash 视图路由、API/充值/状态卡渲染
- `apps/frist-api/src/data.js` — 补充 API Key、充值、帮助、渠道可用性模拟数据
- `apps/frist-api/src/styles.css` — 重做分区控制台、状态卡和移动端样式
- `apps/frist-api/favicon.svg` — 更新抽象品牌图标
- `apps/frist-api/tests/core.test.mjs` — 增加分区导航和连通性字段测试
- `docs/025-frist-api-quickstart.md` — 同步当前可见能力
- `docs/002-changelog.md` — 记录本次参考站迭代

## [2026-05-01] Frist-API 用户端 UI 解耦重构
> 领域: `frontend` | `docs`
> 影响模块: `Frist-API`, `CC Switch`, `docs`
> 关联问题: Frist-API-MVP

### 变更内容
- UI: 按用户反馈重构 Frist-API 为纯用户控制台，移除首屏中的管理端、补号助手、价格解析和号源归类信息。
- 信息架构: 用户端只保留模型消耗、Claude/OpenAI 渠道连通性、API 管理、充值入口和 CC Switch 导入。
- 品牌: 重做 Frist-API 抽象 Logo 和 favicon，使用黑白基础与红色识别点，降低视觉噪音。
- 测试: 新增用户端边界测试，确保管理端内容不会再次出现在用户页面。
- 文档: 更新快速启动指南，说明用户端与管理端分离。

### 文件变更
- `apps/frist-api/index.html` — 重构用户端页面结构
- `apps/frist-api/src/app.js` — 重写用户端渲染逻辑
- `apps/frist-api/src/data.js` — 调整用户端模拟数据
- `apps/frist-api/src/styles.css` — 重做用户端视觉和响应式样式
- `apps/frist-api/favicon.svg` — 更新抽象品牌图标
- `apps/frist-api/tests/core.test.mjs` — 增加用户端/管理端解耦测试
- `docs/025-frist-api-quickstart.md` — 同步用户端范围说明
- `docs/002-changelog.md` — 记录本次 UI 解耦重构

## [2026-05-01] Frist-API 网站雏形落地
> 领域: `frontend` | `ai-pool` | `deploy` | `docs`
> 影响模块: `Frist-API`, `CC Switch`, `New-API`, `Makefile`, `docs`
> 关联问题: Frist-API-MVP

### 变更内容
- 网站: 新增 `apps/frist-api/` 独立静态网站雏形，首屏覆盖账单卡、API Key、五目标 CC Switch 导入、模型连通性、补号助手和价格解析。
- 逻辑: 新增可测试核心逻辑，覆盖请求地址归一化、CC Switch 导入链接、价格解析、直连/代理推荐、日卡 Key 自动切换和用户侧模型健康摘要。
- 部署: 新增 `docker-compose.frist-api.yml`，本地同时启动 Frist-API 网站和 New-API 核心原型。
- 命令: Makefile 增加 `frist-api-test`、`frist-api-dev`、`frist-api-up`、`frist-api-down`。
- 文档: 新增快速启动指南，并在项目地图登记 Frist-API 原型位置。

### 文件变更
- `apps/frist-api/index.html` — Frist-API 网站雏形页面
- `apps/frist-api/favicon.svg` — Frist-API 网站图标
- `apps/frist-api/src/core.js` — 核心业务逻辑
- `apps/frist-api/src/app.js` — 页面交互和模拟数据绑定
- `apps/frist-api/src/data.js` — 首屏模拟数据
- `apps/frist-api/src/styles.css` — 黑白账单控制台样式
- `apps/frist-api/tests/core.test.mjs` — 核心逻辑回归测试
- `apps/frist-api/package.json` — 本地测试和预览脚本
- `docker-compose.frist-api.yml` — Frist-API 原型 Docker 入口
- `Makefile` — 增加 Frist-API 本地命令
- `docs/025-frist-api-quickstart.md` — 新增快速启动指南
- `docs/001-project-map.md` — 登记 Frist-API 应用位置
- `docs/002-changelog.md` — 记录本次网站雏形落地

## [2026-05-01] Frist-API 盈利中转站 MVP 设计落地
> 领域: `docs` | `ai-pool`
> 影响模块: `Frist-API`, `New-API`, `docs/specs`, `handoff`
> 关联问题: Frist-API-MVP

### 变更内容
- 方案: 将公开收费 API 中转站命名为 `Frist-API`，定位为独立网站和盈利渠道，不改 OpenClaw APP 现有 New API 内部管理页面。
- 架构: 明确 Frist-API 只做中转、鉴权、计费、日志和号源管理，不使用本机硬件做模型推理，适配弱服务器部署。
- 用户端: 固化注册、充值、创建 Key、开启/关闭 Key、选择导入位置、CC Switch 导入的完整流程，导入目标覆盖 Claude、Codex、OpenCode、OpenClaw、Hermes。
- 管理端: 设计按请求地址归类的补号助手，支持模型列表缓存、Key 低成本检测、上游不支持模型列表时的降级探测。
- 价格: 设计粘贴式价格解析流程，支持币种/计费单位识别、美元/人民币换算、利润倍率、安全垫和人工确认。
- 号源: 补充上游号商模板、直连/代理测速、模型连通性缓存和用户侧可用性展示。
- 套餐: 补充日卡、月卡、默认池隔离，以及日卡 Key 额度耗尽后的自动摘除和同组切换策略。
- 交接: 写入可直接交给下一位执行者的提示词，包含实现边界、优先级和验证要求。

### 文件变更
- `docs/054-2026-05-01-frist-api-mvp-design.md` — 新增 Frist-API MVP 设计文档和交接提示词
- `docs/061-handoff.md` — 写入本轮 Frist-API 交接摘要
- `docs/002-changelog.md` — 记录本次方案文档落地

## [2026-05-01] 质量优化: API 边界异常链路清理
> 领域: `backend` | `docs`
> 影响模块: `api/routers/cli`, `api/routers/pool`, `api/routers/shopping`, `docs`
> 关联问题: TD-005

### 变更内容
- 维护性: 为 CLI、API 池和购物比价路由的异常转换补充 `raise ... from e`，保留原始异常链，方便排查问题。
- 行为保持: 接口状态码、错误文案和日志级别不变，仅提升故障定位信息。
- 技术债: 全仓 Ruff 历史问题从 552 降到 547，B904 剩余项从 93 降到 88。

### 文件变更
- `packages/clawbot/src/api/routers/cli.py` — 3 个端点补充异常链
- `packages/clawbot/src/api/routers/pool.py` — API 池统计错误转换补充异常链
- `packages/clawbot/src/api/routers/shopping.py` — 购物比价错误转换补充异常链
- `docs/060-health.md` — 同步 TD-005 剩余技术债计数
- `docs/002-changelog.md` — 记录本次质量优化

## [2026-05-01] 质量优化: monitor 路由 lint 清理
> 领域: `backend` | `docs`
> 影响模块: `api/routers/monitor`, `docs`
> 关联问题: TD-004, TD-005

### 变更内容
- 维护性: 清理 monitor 路由中的歧义变量名和未使用循环变量，消除当前文件 Ruff 告警。
- 可靠性: 后台翻译任务保留任务引用并在结束时移除，避免异步任务被静默丢弃。
- 清理: 将后台翻译调度失败的空占位改为 debug 日志，保持接口返回行为不变。
- 技术债: 全仓 Ruff 历史问题从 555 降到 552，源码 `pass` 语句从 64 降到 63。

### 文件变更
- `packages/clawbot/src/api/routers/monitor.py` — 清理 3 项机械 lint 问题和 1 个空异常占位
- `docs/060-health.md` — 同步 TD-004/TD-005 剩余技术债计数
- `docs/002-changelog.md` — 记录本次质量优化

## [2026-05-01] 质量优化: 测试入口、RPC 去重与文档入口修正
> 领域: `backend` | `infra` | `docs`
> 影响模块: `Makefile`, `api/rpc`, `bot mixins`, `social adapters`, `requirements-dev`, `docs`
> 关联问题: HI-821, HI-822, HI-823

### 变更内容
- 架构: 梳理后端主数据流，确认 API/Telegram 共享 `ClawBotRPC` 聚合层，优先优化共用热点。
- 维护性: `Makefile` 的 Python 探测改为优先使用项目 `.venv312`，避免系统 Python 无 pytest 时测试入口失效。
- 重复代码: 提取 yfinance 批量价格补齐 helper，统一 IBKR 价格兜底和本地持仓价格兜底。
- 重复代码: 提取社媒 Cookie 状态 helper，统一 X/Twitter 与小红书登录状态检测。
- 清理: 去掉 `CircuitOpenError` 的空 `pass`，将抽象风控校验器中的 `...` 改为明确异常。
- 清理: 去掉命令聚合类、安全异常和 SDK 降级路径中的空占位语句，抽象策略/社媒适配器改为明确 `NotImplementedError`。
- 文档: 同步 AGENTS/SOP/索引中的文档路径到当前真实文件名，修复旧归档链接和不存在的索引项。
- 文档: 用 AST 扫描真实语法占位，剩余 64 个历史 `pass` 登记为 TD-004，后续按模块分批审查。
- 工具链: `requirements-dev.txt` 补齐 `ruff`，让 `make lint` 不再依赖未声明工具。
- 工具链: 安装 Ruff 后 `make lint` 已进入真实检查阶段，暴露 555 个历史 lint 问题，登记为 TD-005 分批处理。
- 测试: 新增 API 回归测试覆盖价格 helper 去重、previous_close 兜底和 Cookie 文件格式识别。

### 文件变更
- `Makefile` — Python 探测优先项目虚拟环境
- `packages/clawbot/src/api/rpc.py` — 提取价格补齐与社媒 Cookie 检测 helper
- `packages/clawbot/src/http_client.py` — 清理异常类空占位
- `packages/clawbot/src/risk_validators.py` — 抽象方法改为明确 `NotImplementedError`
- `packages/clawbot/src/bot/cmd_basic/__init__.py` — 去掉命令聚合类空占位
- `packages/clawbot/src/bot/cmd_execution_mixin.py` — 去掉执行命令聚合类空占位
- `packages/clawbot/src/core/security.py` — 清理安全异常空占位
- `packages/clawbot/src/execution/social/platform_adapter.py` — 抽象社媒适配器改为明确未实现异常
- `packages/clawbot/src/strategy_engine.py` — 抽象策略分析改为明确未实现异常
- `packages/clawbot/src/tools/deepgram_stt.py` — SDK 缺失降级路径增加调试日志
- `packages/clawbot/src/tools/fal_client.py` — SDK 缺失降级路径增加调试日志
- `packages/clawbot/tests/test_api_routes_regression.py` — 增加行为锁定回归测试
- `packages/clawbot/requirements-dev.txt` — 补齐 Ruff 开发依赖
- `AGENTS.md` — 同步项目导航与文档命名规范到当前文件布局
- `docs/003-docs-index.md`, `docs/001-project-map.md`, `docs/043-update-protocol.md`, `docs/040-docs-first-protocol.md`, `docs/023-disaster-recovery.md`, `docs/032-dependency-map.md` — 修正文档入口路径和依赖登记
- `docs/060-health.md` — 登记 HI-821/HI-822/HI-823 和最新测试状态
- `docs/002-changelog.md` — 记录本次质量优化

## 最近更新（2026-04）

## [2026-04-28] Git 全历史密钥扫描 + 本地风险清理
> 领域: `infra` | `docs`
> 影响模块: Git history, .gitignore, security scan, local runtime cache
> 关联问题: HI-817, HI-818, HI-819

### 变更内容
- 安全: 使用 gitleaks、trufflehog、detect-secrets 对当前工作区、本机 ignored 文件和 1217 个 Git 历史提交做密钥扫描。
- 安全: 确认公开历史曾包含 `.openclaw/openclaw.json*`、`.openclaw/devices/paired.json`、sqlite 数据库等敏感痕迹；记录为待轮换密钥 + 待历史重写。
- 安全: 从 Git 索引移除 `.openclaw/iflow_key_timestamp.json`, 并补充根 `.gitignore` 规则。
- 安全: 执行 `git-filter-repo` 全历史重写, 清除敏感配置、设备配对文件、数据库、`.env`、旧依赖、构建产物和样例凭据噪音。
- 安全: 清理后 `gitleaks` Git 全历史扫描 0 命中, `trufflehog` Git 全历史扫描 0 verified / 0 unverified。
- 清理: 删除可重建本地产物约 4.4GB，包括前端 `node_modules`、Tauri `target`、Python venv、子项目 venv、日志文件。
- 清理: 删除本机浏览器 profile 中确认含 Gemini API key 痕迹的临时 LevelDB 日志。
- Git: 运行 `git gc --prune=now`, 本地松散对象清零。
- 文档: 新增密钥扫描报告, 更新 HEALTH 安全状态。

### 文件变更
- `.gitignore` — 增加 `.openclaw/iflow_key_timestamp.json` 与本地扫描报告忽略规则
- `.openclaw/iflow_key_timestamp.json` — 从 Git 索引移除, 保留本机文件
- `.pre-commit-config.yaml` — 移除已删除 `.secrets.baseline` 的依赖
- `docs/083-secret-scan-2026-04-28.md` — 新增全量密钥扫描报告
- `docs/060-health.md` — 登记 HI-817/HI-818/HI-819
- `docs/changelog.md` — 记录本次安全扫描与清理

## [2026-04-27] Tauri 桌面端重新构建 + Makefile + iLink Session 修复
> 领域: `frontend` | `infra` | `wechat` | `docs`
> 影响模块: Makefile, wechat_receiver(云端), BUILD_GUIDE
> 关联问题: HI-812, HI-816

### 变更内容
- 构建: 创建项目 Makefile，`make tauri-build` 一键清理+编译+安装+验证
- 构建: 桌面端重新构建，OpenClaw.app 7.8MB 已安装到 /Applications
- 构建: 清理旧版 OpenClaw.app 残留，确认无 OpenEverything.app 双版本
- 云端: iLink Session 过期自动恢复 — 清空轮询游标强制重建 session
- 云端: 诊断 errcode=-14 根因 — iLink bot token 在平台侧失效，需重新扫码
- 文档: 新增 BUILD_GUIDE.md (构建铁律+快速构建+环境要求+常见问题)

### 文件变更
- `Makefile` — 新建，包含 tauri-build/dev/clean + backend-restart/test + cloud-sync
- `docs/guides/BUILD_GUIDE.md` — 新建，桌面端构建必操作指南
- `/opt/openclaw-wechat/wechat_receiver.py`(云端) — session 过期时清空 buf 游标

## [2026-04-26] 全量桌面客户端审计 — 7项Bug修复 + 性能优化 + 三端对齐
> 领域: `backend` | `frontend` | `wechat` | `infra`
> 影响模块: world_monitor, broker_bridge, monitor, log_config, wechat, multi_main
> 关联问题: HI-805~811

### 变更内容
- 后端: 金融指数全零修复(yfinance单个Ticker替代批量请求) + volume数据补全
- 后端: IBKR accountSummary event loop冲突修复(accountSummary→accountSummaryAsync)
- 后端: /monitor/extended超时修复(3个外部API改并发+缓存优先+20s超时保护)
- 后端: loguru配置修复(rotation 10s→50MB) + 清理1800+旧日志文件(168MB)
- 微信: 欢迎消息重写(完整功能速查+分区索引) + cmd_dashboard不可达修复(添加编号107)
- 微信: cmd_iorders差异化格式化 + 完整帮助消息动态生成
- 微信: cmd_status路径修复(/system/status→/status) + 12个命令新增API映射
- 微信: 热点话题(300)专用格式化 + 全球情报(407)嵌套dict展开 + 执行简报(500)映射
- 微信: 全市场扫描(205)改为需要参数 + 全球情报timeout提升至30s
- 性能: Ollama模型常驻9.1GB修复(unload + KEEP_ALIVE=5m自动卸载)
- 审计: Telegram 101命令全对齐 / 微信64命令映射完整 / 桌面端30页面覆盖
- 审计: 全量命令验证 27/27 可用(25✅ 2⚠️数据空 0❌)
- 测试: 1486 passed, 0 failed (零回归)
- 云端: 腾讯云wechat_receiver.py同步(欢迎消息+帮助+服务重启)

### 文件变更
- `src/monitoring/world_monitor.py` — yfinance单个Ticker + volume + 超时25s + warning级别
- `src/broker_bridge.py` — accountSummary→accountSummaryAsync
- `src/api/routers/monitor.py` — extended端点并发+缓存+超时保护
- `src/log_config.py` — loguru rotation改为50MB固定文件名
- `src/api/routers/wechat.py` — 新增_format_intel/_format_topics + 12个API映射 + timeout差异化

## [2026-04-25] 全量审计与优化 Sprint
> 领域: `backend` | `frontend` | `wechat`
> 影响模块: `wechat.py`, `rpc.py`, `world_monitor.py`, `social_browser_worker.py`, `multi_main.py`, 前端 8 个组件
> 关联问题: 全量审计

### 变更内容
- 后端: 修复 /trading/pnl 全零问题(IBKR 离线兜底计算), /trading/dashboard 空数据, /monitor/finance 行情全零(yfinance getattr), /social/analytics 导入错误, /trading/system unknown 状态
- 前端: 修复 Social 页 t 变量遮蔽, ControlCenter 响应检查, usePortfolioAPI 错误处理, 8 个页面轮询优化(useActivePagePolling), Settings 通知硬编码
- 微信: 实现编号命令系统(60+ 命令映射), 欢迎消息, 完整功能列表
- 性能: Chrome V8 堆 512→128MB, 渲染进程限制 3, 自动清理多余标签页, 模块懒加载(browser-use/CrewAI/进化引擎)
- Telegram: 命令全量审计(100/100 通过), 发现 2 个注册表缺失(/claude, /deals)

## [2026-04-25] 内存优化: Chrome 浏览器 + 模块懒加载
> 领域: `backend`, `infra`
> 影响模块: `social_browser_worker`, `multi_main`, `browser_use_bridge`
> 关联问题: PERF-MEM-001
### 变更内容
- Chrome 社交浏览器 V8 堆限制从 512MB 降至 128MB，新增 `--renderer-process-limit=3` 限制渲染进程数，禁用 background networking/extensions/component-update 等冗余功能。预计节省 ~800-1200MB
- 新增 `cleanup_excess_tabs()` 自动清理重复/无用标签页（blob: URL、chrome:// 内部页、重复登录页），每次状态检查时自动触发，标签页上限 4 个
- browser-use、CrewAI、进化引擎改为懒加载模式——启动时不实例化，首次使用时才初始化。预计减少启动内存 ~30-50MB
### 文件变更
- `scripts/social_browser_worker.py` — Chrome 启动参数内存优化 + 标签页清理函数
- `multi_main.py` — browser-use/CrewAI/进化引擎从启动初始化改为延迟加载
- `src/browser_use_bridge.py` — `get_browser_use()` 改为自动懒初始化

## [2026-04-17] 后端 API 新增 + 前端真实数据对接 — 从演示数据到可用系统
> 领域: `backend`, `frontend`
> 影响模块: `api/routers/system`, `api/routers/trading`, `api/server`, `api/routers/conversation`, `tauri.ts`, `Home`, `conversationService`
> 关联问题: 桌面 APP 5 个页面需要从模拟数据切换到后端真实数据
### 变更内容
- **后端新增 4 组 API 端点** — `GET /api/v1/system/daily-brief`（今日简报聚合 metrics + 模块状态）、`GET/POST /api/v1/system/notifications`（通知列表+标记已读+全部已读）、`GET /api/v1/trading/portfolio-summary`（持仓聚合摘要）、`GET /api/v1/system/services`（服务运行状态检测）
- **挂载 Conversation 路由** — `router_conversation` 之前已实现（SSE 流式对话 333 行），但未在 server.py 注册，导致 /api/v1/conversation/* 端点全部 404
- **前端 tauri.ts 新增全部 API 封装** — dailyBrief/notifications/markNotificationRead/markAllNotificationsRead/portfolioSummary/services/serviceStatus + conversation 完整封装（sessions/create/get/delete/send）
- **Home 首页对接真实数据** — 模拟通知替换为 `api.notifications()` + 首页摘要并行请求加入 `api.dailyBrief()`
- **conversationService SSE 修复** — 流式请求从裸 fetch 改为 clawbotFetch（携带 API Token），修复未授权错误
- **回归测试**: 1339 passed, 2 skipped, 0 failures ✓
### 文件变更
- `packages/clawbot/src/api/server.py` — 新增 router_conversation 导入和挂载（2处）
- `packages/clawbot/src/api/routers/system.py` — 31行→~280行，新增 daily-brief/notifications/services 三组端点
- `packages/clawbot/src/api/routers/trading.py` — 151行→~240行，新增 portfolio-summary 端点
- `apps/openclaw-manager-src/src/lib/tauri.ts` — 719行→~820行，新增所有 API 封装函数
- `apps/openclaw-manager-src/src/components/Home/index.tsx` — 模拟通知→真实 API + dailyBrief 数据对接
- `apps/openclaw-manager-src/src/services/conversationService.ts` — SSE fetch→clawbotFetch + 移除废弃 API_BASE

---

## [2026-07-07] CC中转方案 B 本机卖家桥接器常驻
> 领域: `xianyu` | `infra` | `frontend`
> 影响模块: `CC中转`, `XianyuAdmin`, `Seller Bridge`, `Chrome Social Pilot`
> 关联问题: HI-cc-xianyu-auto-ops
### 变更内容
- 老板已确认方案 B：六档套餐、库存自动补、每日上游余额同步、低余额预警和自动化发货路线继续推进。
- 修复 18800 操作台 CORS，允许本项目 Chrome 扩展来源访问本机操作台，同时继续拒绝任意外部网页来源。
- 发现 Chromium 扩展 Service Worker 访问 localhost 在新版 Local Network Access 下不稳定，新增 `cc_zhongzhuan_seller_bridge.mjs` 本机卖家桥接器：本机进程读取 18800 队列，通过 DevTools 注入既有闲鱼页面执行器，接管自动发卡、点击发送、确认发货和恢复可售巡检。
- 已安装 `ai.openclaw.cc-seller-bridge` LaunchAgent 常驻；老板日常只需打开卖家专用 Chromium 并登录闲鱼，桥接器每 15 秒巡检一次。
- 卖家专用浏览器启动器默认使用 `cc-zhongzhuan-seller-chromium-v2` Profile，并增加 Local Network Access 兼容参数；若本机 Playwright Chromium 缓存缺失，会降级到普通 Google Chrome 并提示安装 Chromium。
### 文件变更
- `scripts/cc_zhongzhuan_seller_bridge.mjs` — 新增本机 DevTools 桥接器。
- `scripts/cc_zhongzhuan_launch_seller_chrome.mjs` / `scripts/cc_zhongzhuan_launch_seller_chrome.test.mjs` — 默认新 Profile、Local Network Access 参数和降级测试。
- `packages/clawbot/src/xianyu/xianyu_admin.py` / `packages/clawbot/tests/test_xianyu_cc_auto_ship.py` — 18800 CORS 与桥接器状态提示。
- `Makefile` — 新增 `cc-seller-bridge`、`cc-seller-auto` 入口。
- `~/Library/LaunchAgents/ai.openclaw.cc-seller-bridge.plist` — 本机运行资产，已安装并运行。
### 验证
- `node --check scripts/cc_zhongzhuan_seller_bridge.mjs`：exit 0。
- `node scripts/cc_zhongzhuan_seller_bridge.mjs --dry-run --json`：`ok=true`，找到卖家浏览器和闲鱼标签页。
- `node scripts/cc_zhongzhuan_seller_bridge.mjs --once --json`：`ok=true`，当前闲鱼首页无已付款信号，因此安全跳过，不发送消息。
- `cd packages/clawbot && .venv312/bin/python -m pytest tests/test_xianyu_cc_auto_ship.py::test_xianyu_admin_cors_allows_chrome_extension_origin tests/test_xianyu_cc_auto_ship.py::test_xianyu_admin_cors_rejects_unlisted_web_origin tests/test_xianyu_cc_auto_ship.py::test_xianyu_status_reports_local_bridge_next_action -q`：`3 passed`。
- 运行态：`ai.openclaw.cc-seller-bridge` 为 `running`，本机 `/api/status.cc_chrome_extension` 显示 `manifest_version=bridge`、`supports_paid_page_dispatch=true`、`supports_relist_queue=true`、`needs_refresh_for_global_watch=false`。
### 当前边界
- 当前仍是生产环境内测；正式售卖严格门不放宽，必须等待新的 `xy_oid_*` 真实闲鱼付款订单，并完成买家兑换、创建 API Key、CC Switch 导入和调模型。
- 如果卖家专用 Chromium 窗口关闭，桥接器会继续运行但只能等待浏览器重新打开；若打开后未登录闲鱼，不会自动读取订单或发货。


...

2026-04 以前的详细审计附件和截图已在 2026-05-03 文档清理中移除，核心变更记录保留在本文。

## [2026-07-06] Intel Brief Phase C/D 支架 — Source Adapter 与 plan-only 派发
> 领域: `intel-brief` | `execution` | `docs`
> 影响模块: `src/intel/sources/base.py`, `src/intel/sources/congress_trading.py`, `src/execution/intel_brief.py`

### 变更内容
- 新增 Intel Brief Source Adapter 统一契约：`IntelSourceResult` / `IntelSourceAdapter`。
- 将 Senate raw GitHub fallback 封装为 `SenateTransactionsAdapter`，保留 Phase B 真实调用 evidence_path。
- 新增独立执行场景 `src/execution/intel_brief.py`，当前只输出多服务器派发计划，不进行远程执行、部署、调度注册或 Telegram 推送。
- 新增 Phase C/D evidence JSON，记录 controller 本地支架验证结果和明确边界。
- 回归：Intel Brief 相关测试 20 passed。

## [2026-07-06] Intel Brief Worker Contract 与 Source Health helper
> 领域: `intel-brief` | `execution` | `observability`
> 影响模块: `src/intel/worker_contract.py`, `src/execution/intel_brief.py`, `src/intel/db/store.py`

### 变更内容
- 新增 `IntelWorkerRequest` / `IntelWorkerResponse`，作为 controller↔worker JSON-safe 契约。
- `dispatch_source_job` 保持 `plan_only`，但新增 `worker_request` 字段，后续可直接作为远程 worker 输入。
- 新增 `record_source_health` / `get_source_health`，为每个数据源接入真实 `source_health` 更新链路。
- 生成 Phase D/E evidence JSON：worker contract 派发计划、临时 SQLite source_health 写入证明。
- 只读排查 SGW 管理路径：发现现有 SOP 支持“management-path mismatch”分类，但未找到当前 Mac 可用 SGW SSH alias；未修改任何安全组或凭证。

## [2026-07-06] Intel Brief Worker Runner 与 SGW read-only preflight
> 领域: `intel-brief` | `worker` | `infra-evidence`
> 影响模块: `src/intel/worker_runner.py`, `src/intel/sources/registry.py`, VPS-Config SGW evidence

### 变更内容
- 新增 worker 本地执行器：request JSON → adapter → response JSON → source_health。
- 新增默认 adapter registry：当前只注册已有 Phase B 证据的 `senate_trading`。
- 生成 worker-runner 本地契约 evidence：`packages/clawbot/data/intel_evidence/phasee/20260706T232159Z-worker-runner-local-contract.json`。
- 运行 VPS-Config SGW read-only preflight：OCI 只读 run 完成但处于 launch prerequisites blocker；无生产动作。

## [2026-07-06] Intel Brief Worker CLI 入口
> 领域: `intel-brief` | `worker` | `ops-evidence`
> 影响模块: `scripts/intel_worker_cli.py`, `src/intel/worker_runner.py`, `src/intel/sources/registry.py`

### 变更内容
- 新增 worker CLI：stdin/文件读取 request JSON，输出 response JSON，可选写 source_health DB。
- CLI 错误码边界：success=0，业务失败=2，JSON parse error=1。
- 本地 CLI 真实调用 `senate_trading` 成功，生成 evidence。
- 只读检查 `oracle-arm1` fallback：SSH/Python 可用，但未发现现成 OpenEverything 项目路径，暂不能直接运行新 CLI。

## [2026-07-06] Intel Brief Worker Bundle 与 oracle-arm1 fallback 远程执行
> 领域: `intel-brief` | `worker` | `infra-evidence`
> 影响模块: `scripts/intel_worker_bundle.py`, `scripts/intel_worker_cli.py`, `src/intel/*`

### 变更内容
- 新增 worker bundle builder，输出最小可回滚 bundle 与 manifest。
- 本地 bundle smoke 通过，bundle 不含密钥/服务文件/生产配置。
- 将 bundle 临时 staging 到 `oracle-arm1:/tmp`，真实执行 `senate_trading` worker CLI 成功，返回 BYND / Ron L Wyden 样本，并写入远程临时 SQLite source_health。
- 已清理远程 staging 并验证目录不存在；不涉及 systemd、cron、生产配置、Token/Cookie。

## [2026-07-06] Intel Brief 炎火云 AKShare worker CLI 真实执行
> 领域: `intel-brief` | `worker` | `domestic-source`
> 影响模块: `src/intel/sources/astock_flow.py`, `src/intel/sources/registry.py`, `scripts/intel_worker_bundle.py`, `src/intel/worker_runner.py`

### 变更内容
- 新增 AKShare 龙虎榜 adapter，并加入默认 registry 与 worker bundle。
- 修复 worker bundle Python 3.10 兼容：`datetime.UTC` → `timezone.utc`。
- 修复 adapter stdout 噪声污染问题，确保 worker CLI stdout 为单个 response JSON。
- 炎火云 `/tmp` 临时 staging + 临时 venv 安装 `akshare==1.18.64` 后真实执行成功，返回 `000021` / `深科技`，执行后清理并验证目录不存在。

## [2026-07-07] Intel Brief Remote Runner 固化
> 领域: `intel-brief` | `worker` | `remote-execution`
> 影响模块: `scripts/intel_worker_remote_run.py`, `scripts/intel_worker_bundle.py`, `scripts/intel_worker_cli.py`

### 变更内容
- 新增 remote runner：构建 bundle → SSH 临时 staging → 执行 worker CLI → 查询 source_health → cleanup → evidence。
- 用 remote runner 复核 oracle-arm1 fallback `senate_trading` 成功。
- 用 remote runner 复核炎火云 domestic `akshare` 成功，支持临时 pip 依赖安装。
- 两条远程复核均完成 cleanup 并验证 staging 目录不存在。

## [2026-07-07] Intel Brief Collect-once 多源远程采集
> 领域: `intel-brief` | `collector` | `remote-execution`
> 影响模块: `scripts/intel_collect_once.py`, `scripts/intel_worker_remote_run.py`

### 变更内容
- 新增 collect-once controller 编排脚本，按 source 调用 remote runner 并聚合 child evidence。
- 真实执行 `senate_trading` + `akshare` 两源采集成功，覆盖海外 fallback 与国内 worker。
- 聚合 evidence 记录 child response、source_health、cleanup 状态。
- 仍未注册 scheduler、未部署服务、未推送 Telegram。

## [2026-07-07] Intel Brief Dry-run 简报生成

> 影响模块: `Intel Brief`, `Brief Builder`, `Content Moderation`, `Evidence`

- 新增 `packages/clawbot/src/intel/brief_builder.py`，把真实 collect-once evidence 转为规范化、去重、内容过滤后的 Markdown/JSON dry-run 简报。
- 新增 `packages/clawbot/scripts/intel_brief_dry_run.py`，提供本地 CLI 生成 dry-run evidence；明确不调用 LLM、不推送 Telegram、不注册 scheduler。
- 新增 `packages/clawbot/tests/test_intel_brief_dry_run.py`，覆盖规范化、stable-key 去重、过滤占位与 CLI 输出。
- 真实 dry-run evidence：`packages/clawbot/data/intel_evidence/phasef/20260707T003755Z-brief-dry-run.md` 与 `.json`，summary 为 `source_count=2 / rendered_count=2 / deduped_count=0 / moderated_count=0`。
- 边界：该阶段只把已有真实采集证据生成草稿，不代表 LLM 摘要、Telegram 推送、生产调度或自然日演练已闭合。

## [2026-07-07] Intel Brief Dry-run 验证基线

> 影响模块: `Intel Brief`, `Verification`, `Docs Baseline`

- Dry-run 简报生成最终验证 evidence：`packages/clawbot/data/intel_evidence/phasef/20260707T004119Z-brief-dry-run-verification.json`。
- 验证结果：`ruff` 通过，Intel Brief 相关 pytest `54 passed`，OpenEverything/VPS-Config `git diff --check` 均通过。
- 边界：仍未调用 LLM、未推送 Telegram、未注册 scheduler、未创建常驻服务或写入密钥。

## [2026-07-07] Intel Brief LLM 摘要 dry-run

> 影响模块: `Intel Brief`, `LLM Routing`, `Ollama Local`, `Evidence`

- 新增 `routing_profiles.intel_brief`，为 Intel Brief 摘要层建立专属 LLM routing profile。
- 新增本地 dry-run family `intel_local`，通过现有 LiteLLM routing 指向 Ollama `qwen2.5:1.5b`，且无外部 fallback。
- 新增 `src/intel/llm_summary.py` 与 `scripts/intel_llm_summary_dry_run.py`，把 Phase F dry-run evidence 转为 LLM summary dry-run evidence。
- 首次 `gemma` 调用超时并降级，失败证据：`packages/clawbot/data/intel_evidence/phaseg/20260707T005033Z-llm-summary-dry-run.json`。
- 成功证据：`packages/clawbot/data/intel_evidence/phaseg/20260707T005640Z-llm-summary-dry-run-intel-local.json`，`intel_local` 调用成功，token usage 为 `353/159/512`。
- 边界：未推送 Telegram、未注册 scheduler、未调用外部付费 LLM、未写入生产 DB 或密钥。

## [2026-07-07] CC中转闲鱼付款系统卡片漏单修复
> 领域: `xianyu` | `commerce` | `qa`
> 影响模块: `XianyuLive`, `Chrome Social Pilot`, `CC中转`
> 关联问题: HI-cc-xianyu-plain-paid-card

### 变更内容
- 修复闲鱼 WebSocket 明文 JSON 系统卡片被直接跳过的问题：现在“我已付款，等待你发货”这类系统卡片会进入订单状态识别。
- 新增买家 ID 提取兜底：订单消息 `1` 字段为对象时，从系统卡片 meta 中读取 `senderUserId/senderId/userId/buyerId`，缺失买家 ID 时阻止自动发货。
- 增加安全门：只信“付款系统卡片标题”，普通聊天内容里照抄“我已付款，等待你发货”不会触发发货，避免买家假话术导致误发卡。
- 复核开源轮子后继续选择“搬能力不整套替换”：`zhinianboke/xianyu-auto-reply`、`GuDong2003/xianyu-auto-reply-fix` 为 AGPL-3.0，`23Star/xianyu-super-butler` 许可证不明确；短期不替换 New-API/CC中转主链路。

### 验证结果
- `cd packages/clawbot && .venv312/bin/python -m py_compile src/xianyu/xianyu_live.py` 通过。
- `cd packages/clawbot && .venv312/bin/python -m pytest tests/test_xianyu_cc_auto_ship.py::test_detects_paid_status_from_xianyu_system_chat_title tests/test_xianyu_cc_auto_ship.py::test_paid_text_in_normal_chat_content_does_not_trigger tests/test_xianyu_cc_auto_ship.py::test_decode_sync_payload_accepts_plain_json_system_card tests/test_xianyu_cc_auto_ship.py::test_plain_json_paid_system_card_starts_auto_ship tests/test_xianyu_cc_auto_ship.py::test_paid_order_uses_message_item_id_before_recent_item -q`：`5 passed`。
- 根目录 `make test`：后端全量 pytest 到 `[100%]`，exit code `0`。
- `cd packages/openclaw-npm/assets/chrome-extension && node --check background.js && node --check popup.js && node --check social-page-runner.js && node --test test/social-page-runner.test.mjs test/popup-static.test.mjs`：`43 passed / 0 failed`。
- `cd apps/frist-api && node --test tests/*.test.mjs`：`182 passed / 0 failed`。
- `node scripts/cc_zhongzhuan_readiness_audit.mjs --mode=read_only --json` 仍正确返回 `ok=false`，原因是当前真实内测单 `pendingRescue=1` 尚未发到买家聊天，不允许误报闭环。

### 文件变更
- `packages/clawbot/src/xianyu/xianyu_live.py` — 兼容明文付款系统卡片、提取买家 ID、保护普通聊天不误触发。
- `packages/clawbot/tests/test_xianyu_cc_auto_ship.py` — 增加明文系统卡片、普通聊天防误发、买家 ID 提取和自动发货任务启动回归测试。

## [2026-07-07] Intel Brief LLM 摘要验证基线

> 影响模块: `Intel Brief`, `LLM Routing`, `Verification`, `Docs Baseline`

- 最终验证 evidence：`packages/clawbot/data/intel_evidence/phaseg/20260707T010034Z-llm-summary-postdocs-verification.json`。
- 验证结果：`llm_routing.json` JSON 校验通过，变更范围 `ruff` 通过，Intel Brief + LLM routing 相关 pytest `148 passed`，OpenEverything/VPS-Config diff check 均通过。
- 边界：仍未推送 Telegram、未注册 scheduler/cron/systemd、未创建常驻服务或写入密钥。

## [2026-07-07] Intel Brief 订阅者与 fake Telegram 投递沙盒

> 影响模块: `Intel Brief`, `Subscribers`, `Delivery Log`, `Telegram Sandbox`, `Evidence`

- 新增 `src/intel/delivery.py`，验证 sandbox subscriber、active subscription、source preference、delivery_log 和 fake Telegram outbox。
- 新增 `scripts/intel_delivery_sandbox.py`，从 LLM summary evidence 生成投递沙盒 evidence。
- 新增 `tests/test_intel_delivery_sandbox.py`，覆盖订阅者写入、消息渲染、fake sender、delivery_log、CLI。
- 真实 sandbox evidence：`packages/clawbot/data/intel_evidence/phaseh/20260707T010624Z-delivery-sandbox.json`，结果 `eligible=1 / sent=1 / failed=0 / network_calls=0`。
- 边界：未调用真实 Telegram Bot API，未写生产 DB，未注册 scheduler/cron/systemd，未写入 Token/Cookie/API Key。

## [2026-07-07] Intel Brief 投递沙盒验证基线

> 影响模块: `Intel Brief`, `Delivery Sandbox`, `Verification`, `Docs Baseline`

- 最终验证 evidence：`packages/clawbot/data/intel_evidence/phaseh/20260707T010821Z-delivery-sandbox-verification.json`。
- 验证结果：`llm_routing.json` JSON 校验通过，变更范围 `ruff` 通过，Intel Brief + LLM routing 相关 pytest `154 passed`，OpenEverything/VPS-Config diff check 均通过。
- 边界：仍未调用真实 Telegram Bot API、未注册 scheduler/cron/systemd、未创建常驻服务或写入密钥。

## [2026-07-07] Intel Brief Scheduled Sandbox 排练

> 影响模块: `Intel Brief`, `Scheduler Rehearsal`, `Evidence`, `Telegram Sandbox`

- 新增 `src/intel/scheduled_pipeline.py`，提供 scheduled decision 与本地 scheduled sandbox pipeline。
- 新增 `scripts/intel_scheduled_sandbox.py`，从既有 collect evidence 串联 dry-run brief、LLM summary dry-run、delivery sandbox，并写统一 Phase I evidence。
- 新增 `tests/test_intel_scheduled_pipeline.py`，覆盖未到点 skip、到点执行、同日去重、fallback-only LLM、fake Telegram delivery 和 CLI。
- 真实 scheduled sandbox evidence：`packages/clawbot/data/intel_evidence/phasei/20260707T011556Z-scheduled-sandbox.json`，结果 `brief rendered=2 / llm_attempted=false / eligible=1 / sent=1 / failed=0 / network_calls=0`。
- 最终验证 evidence：`packages/clawbot/data/intel_evidence/phasei/20260707T011701Z-scheduled-sandbox-verification.json`。
- 边界：未注册 scheduler/cron/systemd，未调用真实 Telegram Bot API，未写生产 DB，未远程抓取新数据，未写入 Token/Cookie/API Key。

## [2026-07-07] Intel Brief ExecutionScheduler 安全闸门接入

> 影响模块: `Intel Brief`, `ExecutionScheduler`, `Scheduler Gate`, `Evidence`

- 新增 `build_intel_brief_scheduler_gate()`，为 `INTEL_BRIEF_ENABLED` / `INTEL_BRIEF_TIME` / `INTEL_BRIEF_MODE` 建立独立调度闸门。
- `ExecutionScheduler` 新增 `_run_intel_brief()`，默认只允许 sandbox runner；生产模式缺少完整硬闸门时不执行。
- 修复 async scheduler context 调用 scheduled sandbox pipeline 的嵌套 event loop 问题：默认 runner 改由 `asyncio.to_thread()` 执行。
- 新增 `scripts/intel_scheduler_gate_probe.py`，输出脱敏 gate evidence。
- `.env.example` 新增 Intel Brief 独立调度变量；控制面板静态任务表登记 `intel_brief`，默认 disabled。
- 真实 evidence：`packages/clawbot/data/intel_evidence/phasej/20260707T012933Z-production-hard-gate-blocked.json` 与 `packages/clawbot/data/intel_evidence/phasej/20260707T013200Z-execution-scheduler-sandbox-invocation.json`。
- 边界：未启用生产 scheduler/cron/systemd，未调用真实 Telegram Bot API，未写生产 DB，未远程抓取新数据，未输出任何密钥明文。

## [2026-07-07] Intel Brief Scheduler Gate 验证基线

> 影响模块: `Intel Brief`, `Verification`, `Docs Baseline`

- 最终验证 evidence：`packages/clawbot/data/intel_evidence/phasej/20260707T013304Z-scheduler-gate-verification.json`。
- 验证结果：Phase J evidence JSON 校验通过，`llm_routing.json` JSON 校验通过，变更范围 `ruff` 通过，Intel Brief + LLM routing + Execution facade 相关 pytest 通过，fake secret 泄漏检查通过，OpenEverything/VPS-Config diff check 均通过。
- 边界：仍未启用生产 scheduler/cron/systemd、未调用真实 Telegram Bot API、未创建常驻 worker 或写入密钥。

## [2026-07-07] Intel Brief Telegram sandbox sender 合同层

> 影响模块: `Intel Brief`, `Telegram`, `Delivery`, `Evidence`

- 新增 `src/intel/telegram_delivery.py`，包含 Telegram sandbox gate、`TelegramBotApiSender` 和 evidence probe。
- 新增 `scripts/intel_telegram_sandbox_probe.py`，默认只读 gate-only；真实网络必须显式 `--allow-real-network` 且 gate ready。
- 新增 `tests/test_intel_telegram_delivery.py`，覆盖脱敏 gate、注入 transport 合同、probe evidence 与 CLI blocked evidence。
- `.env.example` 新增 `INTEL_BRIEF_TELEGRAM_SANDBOX_SEND_ACK`，默认空。
- 证据：`packages/clawbot/data/intel_evidence/phasek/20260707T014112Z-telegram-sandbox-gate-blocked.json` 与 `packages/clawbot/data/intel_evidence/phasek/20260707T014112Z-telegram-sandbox-contract-injected.json`。
- 边界：未调用真实 Telegram Bot API，未写 token/chat id 明文，未注册 scheduler/cron/systemd，未写生产 DB。

## [2026-07-07] Intel Brief Telegram sender 合同验证基线

> 影响模块: `Intel Brief`, `Telegram`, `Verification`, `Docs Baseline`

- 最终验证 evidence：`packages/clawbot/data/intel_evidence/phasek/20260707T014408Z-telegram-contract-verification.json`。
- 验证结果：Phase K evidence JSON 校验通过，Telegram 合同层 ruff 通过，`.env.example` ack 变量存在，Phase K/Intel Brief/LLM routing 相关 pytest 通过，token/chat/fake secret 泄漏检查通过，OpenEverything/VPS-Config diff check 均通过。
- 边界：仍未调用真实 Telegram Bot API、未验证真实 bot token/chat id、未启用生产 scheduler/cron/systemd、未创建常驻 worker。

## [2026-07-07] Intel Brief Telegram summary delivery 集成预演

> 影响模块: `Intel Brief`, `Telegram`, `Delivery`, `Evidence`

- 新增 `build_telegram_summary_delivery_probe()`，把真实 LLM summary evidence 渲染为 Telegram 消息并进入 Telegram sender 合同层。
- 新增 `scripts/intel_telegram_summary_probe.py`，默认不真实联网。
- 扩展 `tests/test_intel_telegram_delivery.py`，覆盖 summary evidence 输入、gate blocked、注入 transport 合同成功和 CLI。
- 证据：`packages/clawbot/data/intel_evidence/phasel/20260707T015241Z-telegram-summary-gate-blocked.json` 与 `packages/clawbot/data/intel_evidence/phasel/20260707T015241Z-telegram-summary-contract-injected.json`。
- 边界：未调用真实 Telegram Bot API，未写 token/chat id 明文，未注册 scheduler/cron/systemd，未写生产 DB，未抓取新数据。

## [2026-07-07] Intel Brief Telegram summary delivery 验证基线

> 影响模块: `Intel Brief`, `Telegram`, `Delivery`, `Verification`

- 最终验证 evidence：`packages/clawbot/data/intel_evidence/phasel/20260707T015419Z-telegram-summary-delivery-verification.json`。
- 验证结果：Phase L-pre evidence JSON 校验通过，Telegram summary delivery ruff 通过，Phase L-pre/Intel Brief/LLM routing 相关 pytest 通过，token/chat/fake secret 泄漏检查通过，OpenEverything/VPS-Config diff check 均通过。
- 边界：仍未调用真实 Telegram Bot API、未验证真实 bot token/chat id、未启用生产 scheduler/cron/systemd、未创建常驻 worker。

## [2026-07-07] Intel Brief production-once 真实 Telegram 投递

> 影响模块: `Intel Brief`, `Telegram`, `Production Gate`, `Private Env`, `Evidence`

- 私有 env `.openclaw/intel-brief.production.env` 已写入并保持 `0600` / gitignored；证据仅记录 key presence，不含 token/chat id。
- 修复 production-once runner 未把 private env 合并后传给 Telegram delivery runner 的问题，并补回归测试。
- 不带 production ack 时 production-once 仍 blocked，`network_calls=0`。
- 临时命令环境变量注入 production ack 后，一次性 production runner 真实调用 Telegram Bot API `sendMessage` 成功，证据：`packages/clawbot/data/intel_evidence/phaser/20260707T032645Z-production-once-real-delivery.json`。
- 边界：未安装/加载 launchd，未注册 cron/systemd，未创建常驻 worker，未完成自然日调度观察，production ack 未持久化。

## [2026-07-07] Intel Brief fresh production cycle 真实投递

> 影响模块: `Intel Brief`, `Production Cycle`, `Launch Package`, `Telegram`, `Evidence`

- 新增 `intel_production_cycle.py`：每次运行先做 production preflight，再重新远程采集 SGW Senate 与炎火云 AKShare，生成新简报/摘要，最后走 gated production-once 真实 Telegram 投递。
- 无 production ack 时在采集前阻断，避免 Token 已配置后误跑远程采集或误发 Telegram。
- launchd dry-run package 已改为指向 fresh production cycle，不再固定旧 summary evidence。
- 真实 run evidence：`packages/clawbot/data/intel_evidence/phases/20260707T034621Z-production-cycle-real-delivery.json`，结果 fresh collect `success=2/failed=0`、Telegram `network_calls=1`、发送成功。
- 边界：未安装/加载 launchd，未注册 cron/systemd，未完成自然日定时观察，production ack 未持久化。

## [2026-07-07] Intel Brief LaunchAgent 已安装加载

> 影响模块: `Intel Brief`, `launchd`, `Production Cycle`, `Evidence`

- Launch package 支持显式 production ack、stdout/stderr log path，并把相对路径解析为 project_root 下绝对路径。
- 已安装并加载 `~/Library/LaunchAgents/ai.openclaw.intel-brief.scheduler.plist`，目标为 fresh `intel_production_cycle.py`。
- 安装/加载证据：`packages/clawbot/data/intel_evidence/phaset/20260707T040135Z-launchd-production-cycle-reinstall-load-absolute.json`。
- 边界：未 kickstart，安装步骤 `network_calls=0`；自然日自动运行仍待下一次 08:30 触发观察。

## [2026-07-07] Intel Brief LaunchAgent post-run 审计工具

> 影响模块: `Intel Brief`, `launchd`, `Evidence`, `Verification`

- 新增 `intel_launchagent_audit.py`，用于下一次 08:30 后自动判断 LaunchAgent 是否真实完成 fresh production cycle。
- 当前真实审计 evidence：`packages/clawbot/data/intel_evidence/phaseu/20260707T041950Z-launchagent-post-run-audit-pending.json`，状态为 `pending_calendar_trigger`，原因是 `runs=0` 且 run evidence 尚未生成。
- 边界：审计工具只读，不 kickstart、不发送 Telegram、不远程采集。

## [2026-07-07] Intel Brief Telegram Bot API 复核通过

> 影响模块: `Intel Brief`, `Telegram`, `Private Env`, `Evidence`

- 复核 `.openclaw/intel-brief.production.env`：存在、`0600`、必需 key 均为存在态；证据不包含明文 token/chat id。
- 真实调用 Telegram Bot API `sendMessage` 成功，证据：`packages/clawbot/data/intel_evidence/phasetelegram/20260707T123350Z-telegram-bot-api-real-send-probe.json`。
- 真实调用 Telegram Bot API `getMe` 成功，返回 username `carven_Jianbao_bot`，证据：`packages/clawbot/data/intel_evidence/phasetelegram/20260707T123424Z-telegram-bot-api-getme-probe.json`。
- 边界：无需再接管本机 Telegram 点击 Copy；仍需继续处理自然日 LaunchAgent 生产调度观察与 SGW 间歇 SSH timeout 容错。

## [2026-07-07] Intel Brief SGW fallback 容错与 LaunchAgent canary 验证

> 影响模块: `Intel Brief`, `Remote Worker`, `LaunchAgent`, `Evidence`

- `senate_trading` collect 现在保留 SGW preferred worker，同时新增 `oracle-arm1-overseas-fallback`；collect evidence 会记录 `attempts[]` 与 `fallback` 字段。
- SGW SSH profile 增加 `BatchMode=yes` 与 `ConnectTimeout=12`，降低间歇 SSH timeout 对生产周期的影响。
- remote worker runner 在初始 staging/mkdir SSH 失败时 fail-fast，避免后续 health/cleanup/verify 重复超时。
- 回归测试：`test_intel_collect_once.py` 覆盖 SGW failed → oracle-arm1 fallback success；`test_intel_worker_remote_runner.py` 覆盖 staging 失败 fail-fast。
- 真实 fallback 证据：`packages/clawbot/data/intel_evidence/phasew/20260707T124408Z-forced-senate-fallback/collect-once.json`。
- 真实 production cycle 证据：`packages/clawbot/data/intel_evidence/phasew/20260707T124152Z-production-cycle-with-sgw-fallback/latest-production-cycle.json`。
- 真实 LaunchAgent calendar canary 证据：`packages/clawbot/data/intel_evidence/phasew/20260707T125003Z-launchd-calendar-canary-verified/post-run-audit.json`，结果 `verified_success`；临时 canary rollback 证据：`packages/clawbot/data/intel_evidence/phasew/20260707T125003Z-launchd-calendar-canary-verified/rollback-evidence.json`。
- 边界：正式 daily LaunchAgent 未 kickstart，仍待下一次 08:30 自然触发；没有创建 VPS 常驻 worker/systemd/cron；无 token/chat id 明文写入。

## [2026-07-07] Intel Brief Phase W 最终验证基线

> 影响模块: `Intel Brief`, `Verification`, `Docs Baseline`

- 最终验证 evidence：`packages/clawbot/data/intel_evidence/phasew/20260707T125656Z-phase-w-final-verification.json`。
- 验证结果：Phase V/W evidence JSON 校验通过，ruff 通过，相关 pytest 15 项通过，OpenEverything/VPS-Config diff check 通过，Token 片段扫描 0 命中。
- 状态：临时 canary 已移除；正式 daily LaunchAgent 仍 loaded，等待自然日 08:30 运行。

## [2026-07-07] Intel Brief 正式 daily LaunchAgent 预触发审计

> 影响模块: `Intel Brief`, `LaunchAgent`, `Evidence`, `Automation Follow-up`

- 在本地 06:58 MDT 做正式 label `ai.openclaw.intel-brief.scheduler` 只读审计，结果仍为 `pending_calendar_trigger`，符合尚未到 08:30 的状态。
- 证据：`packages/clawbot/data/intel_evidence/phasex/20260707T125904Z-daily-launchagent-pre-trigger-pending-audit.json`。
- 已创建一次性 heartbeat，在本地 08:40 左右回到当前线程继续正式 daily post-run audit。
- 边界：未 kickstart，未发送 Telegram，未远程采集，未修改 LaunchAgent 或 VPS。

## [2026-07-07] Intel Brief Phase X 预触发等待阶段验证

> 影响模块: `Intel Brief`, `LaunchAgent`, `Evidence`, `Verification`

- Heartbeat creation evidence：`packages/clawbot/data/intel_evidence/phasex/20260707T130014Z-daily-audit-heartbeat-created.json`。
- 最终验证 evidence：`packages/clawbot/data/intel_evidence/phasex/20260707T130040Z-phase-x-pretrigger-final-verification.json`。
- 验证结果：phasex JSON、diff check、Token 片段扫描均通过；正式 daily LaunchAgent loaded 且仍未到点运行。

## [2026-07-07] Intel Brief 正式 daily LaunchAgent 自然触发成功

> 影响模块: `Intel Brief`, `LaunchAgent`, `Production Cycle`, `Telegram`, `Evidence`

- 正式 macOS LaunchAgent `ai.openclaw.intel-brief.scheduler` 于本地 08:30 自然触发，`launchctl.runs=1`、`last_exit_code=0`。
- 正式 run evidence：`packages/clawbot/data/intel_evidence/phaset/20260707T040135Z-launchd-production-cycle-install-package-absolute/runs/latest-production-cycle.json`，结果 `status=success`、collect `success=2/failed=0`、Telegram `sendMessage` 成功。
- 正式 post-run audit：`packages/clawbot/data/intel_evidence/phasex/20260707T144102Z-daily-launchagent-post-run-audit.json`，结果 `verified_success`。
- 一次性 heartbeat 已清理，证据：`packages/clawbot/data/intel_evidence/phasex/20260707T145534Z-heartbeat-cleanup-after-daily-success.json`。
- 边界：正式 daily LaunchAgent 继续保留；没有创建 VPS 常驻服务；证据不包含 token/chat id 明文。

## [2026-07-07] Intel Brief Phase X 最终验证与闭环基线

> 影响模块: `Intel Brief`, `Verification`, `Docs Baseline`

- 最终验证 evidence：`packages/clawbot/data/intel_evidence/phasex/20260707T145702Z-daily-launchagent-closure-final-verification.json`。
- 验证结果：JSON、ruff、pytest 28 项、OpenEverything/VPS-Config diff check、Token 片段扫描均通过。
- 生产闭环状态：正式 daily LaunchAgent 自然触发成功，collect `success=2/failed=0`，Telegram delivery success，post-run audit `verified_success`。

## [2026-07-07] Intel Brief 商业订阅 MVP 数据层

> 影响模块: `Intel Brief`, `Subscription`, `Telegram Menu`, `SQLite`, `Evidence`

- 新增 `delivery_preferences` 与 `subscription_audit_log` schema，支撑推送频率/时间与订阅授权审计。
- 新增 `src/intel/subscriptions.py`：套餐、Telegram 订阅者、订阅授权、分类偏好、推送偏好、eligible recipient 筛选、Telegram 菜单合同。
- 新增 `tests/test_intel_commercial_mvp.py`，覆盖 active/expired、偏好筛选、菜单命令合同。
- sandbox 证据：`packages/clawbot/data/intel_evidence/phasey/20260707T152655Z-commercial-mvp-subscription-contract/evidence.json`。
- 边界：未调用 Telegram/支付/闲鱼；未写生产 DB；未输出 chat id/token 明文。

## [2026-07-07] Intel Brief Phase Y 最终验证基线

> 影响模块: `Intel Brief`, `Subscription`, `Verification`

- 最终验证 evidence：`packages/clawbot/data/intel_evidence/phasey/20260707T153329Z-commercial-mvp-subscription-final-verification.json`。
- 验证结果：JSON、ruff、pytest 14 项、OpenEverything/VPS-Config diff check、Token 片段扫描均通过。
- 边界：已完成商业 MVP 数据层/菜单合同；尚未接入真实 Telegram handler 或生产 delivery recipient filtering。

## [2026-07-07] Intel Brief Telegram 用户菜单 handler contract

> 影响模块: `Intel Brief`, `Telegram Menu`, `Subscription`, `Evidence`

- 新增 `src/intel/telegram_menu.py`，提供不联网的 Telegram 命令 handler contract：`/start`、`/status`、`/sources`、`/schedule`、`/custom`、`/help`。
- `/custom` 走开放输入人物追踪数据层，只写 tracking target/subscription/audit log，不触发社媒抓取。
- 新增 sandbox evidence 脚本 `scripts/intel_telegram_menu_sandbox.py`，演练 `/start → grant → /sources → /schedule → /custom → /status`。
- sandbox 证据：`packages/clawbot/data/intel_evidence/phasez/20260707T155448Z-telegram-menu-handler-contract/evidence.json`，结果 `status=success`、`network_calls=0`、final profile active。
- 边界：未调用 Telegram Bot API，未注册真实 bot handler/setMyCommands，未触发社媒抓取，未调用支付/闲鱼，未修改 production LaunchAgent 或正式 DB。

## [2026-07-07] Intel Brief Phase Z 最终验证基线

> 影响模块: `Intel Brief`, `Telegram Menu`, `Verification`

- 最终验证 evidence：`packages/clawbot/data/intel_evidence/phasez/20260707T155805Z-telegram-menu-handler-final-verification.json`。
- 验证结果：Phase Z JSON、ruff、pytest 12 项、OpenEverything/VPS-Config diff check、Telegram token 形态扫描均通过。
- 边界：handler contract 仍未接入真实 Telegram runtime；production delivery 仍未按订阅/偏好筛选真实用户。

## [2026-07-07] Intel Brief Telegram runtime adapter sandbox

> 影响模块: `Intel Brief`, `Telegram Runtime`, `Subscription`, `Evidence`

- 新增 `src/intel/telegram_runtime.py`，把 Telegram update 形状接入 Phase Z menu handler，并调用注入式 reply sender。
- 新增 `scripts/intel_telegram_runtime_sandbox.py`，用 fake sender 演练 `/start → grant → /sources → /schedule → /custom → /status`。
- sandbox 证据：`packages/clawbot/data/intel_evidence/phaseaa/20260707T160334Z-telegram-runtime-adapter-sandbox/evidence.json`，结果 `status=success`、updates `handled=5`、reply success `5`、`network_calls=0`。
- 边界：未调用 Telegram Bot API，未启动 long-polling/webhook，未设置真实 bot commands，未写 production DB，未触发社媒抓取/支付/闲鱼。

## [2026-07-07] Intel Brief Phase AA 最终验证基线

> 影响模块: `Intel Brief`, `Telegram Runtime`, `Verification`

- 最终验证 evidence：`packages/clawbot/data/intel_evidence/phaseaa/20260707T160655Z-telegram-runtime-adapter-final-verification.json`。
- 验证结果：Phase AA JSON、ruff、pytest 15 项、OpenEverything/VPS-Config diff check、Telegram token 形态扫描均通过。
- 边界：runtime adapter 仍未接入真实 Bot API getUpdates/webhook；production delivery 仍未按订阅/偏好筛选真实用户。

## [2026-07-07] Intel Brief Telegram Bot API runtime probe

> 影响模块: `Intel Brief`, `Telegram Bot API`, `Runtime Gate`, `Evidence`

- 新增 `src/intel/telegram_bot_runtime.py`，提供 Bot API runtime gate、`setMyCommands`、`getUpdates` 与 redacted probe evidence。
- 新增 `scripts/intel_telegram_bot_runtime_probe.py`，从私有 env 读取 token/ack 并执行受控 probe。
- 注入式证据：`packages/clawbot/data/intel_evidence/phaseab/20260707T161200Z-telegram-bot-runtime-injected-contract/evidence.json`。
- 真实 Bot API 证据：`packages/clawbot/data/intel_evidence/phaseab/20260707T161129Z-telegram-bot-runtime-real-probe.json`，结果 gate ready、`setMyCommands` success、`getUpdates` success、`network_calls=2`。
- 边界：未 `sendMessage`，未启动 long-polling/webhook，未写 production DB，未持久化 raw updates/chat id/user id/message text。

## [2026-07-07] Intel Brief Phase AB 最终验证基线

> 影响模块: `Intel Brief`, `Telegram Bot API`, `Verification`

- 最终验证 evidence：`packages/clawbot/data/intel_evidence/phaseab/20260707T161357Z-telegram-bot-runtime-final-verification.json`。
- 验证结果：注入式/真实 Bot API JSON、ruff、pytest 19 项、OpenEverything/VPS-Config diff check、token/raw-update 扫描均通过。
- 边界：真实 Bot API 只调用 `setMyCommands` 与 `getUpdates`；未 `sendMessage`，未写 production DB，未启动 long-polling/webhook。

## [2026-07-07] Intel Brief Telegram update offset sandbox

> 影响模块: `Intel Brief`, `Telegram Runtime`, `SQLite`, `Evidence`

- 新增 `telegram_runtime_state` schema，按 bot profile 持久化 Telegram `last_update_id`。
- 新增 `src/intel/telegram_update_processor.py`，读取 offset、过滤重复 updates、调用 runtime adapter，并在成功后推进 offset。
- 新增 `scripts/intel_telegram_update_processor_sandbox.py`，用 fake Bot API client/sender 演练 offset 防重复。
- sandbox 证据：`packages/clawbot/data/intel_evidence/phaseac/20260707T161820Z-telegram-update-processor-offset-sandbox/evidence.json`，结果 offset `0→100→103`，重复 replay `handled_count=0`，`network_calls=0`。
- 边界：未调用 Telegram Bot API，未 `sendMessage`，未写 production DB，未启动 long-polling/webhook。

## [2026-07-07] Intel Brief Phase AC 最终验证基线

> 影响模块: `Intel Brief`, `Telegram Runtime`, `SQLite`, `Verification`

- 最终验证 evidence：`packages/clawbot/data/intel_evidence/phaseac/20260707T162038Z-telegram-update-processor-final-verification.json`。
- 验证结果：Phase AC JSON、ruff、pytest 23 项、OpenEverything/VPS-Config diff check、token/raw-chat scan 均通过。
- 边界：本阶段仍未真实 `sendMessage` 或写 production DB；下一步需要 baseline offset/ack 后处理真实新 updates。

## [2026-07-07] Intel Brief Telegram baseline offset real gate

> 影响模块: `Intel Brief`, `Telegram Bot API`, `SQLite`, `Evidence`

- 新增 `src/intel/telegram_baseline_offset.py` 与 `scripts/intel_telegram_baseline_offset.py`，用于自动回复前设置历史 update baseline。
- sandbox 证据：`packages/clawbot/data/intel_evidence/phasead/20260707T162500Z-telegram-baseline-offset-sandbox/evidence.json`。
- 真实 Bot API 证据：`packages/clawbot/data/intel_evidence/phasead/20260707T162505Z-telegram-baseline-offset-real.json`，结果真实 `getUpdates` 成功，正式 DB offset 写为 `684746897`，`reply_sent=false`。
- 边界：未 `sendMessage`，未写用户订阅/偏好，未启动 long-polling/webhook，未持久化 raw updates/chat id/user id/message text。

## [2026-07-07] Intel Brief Phase AD 最终验证基线

> 影响模块: `Intel Brief`, `Telegram Bot API`, `SQLite`, `Verification`

- 最终验证 evidence：`packages/clawbot/data/intel_evidence/phasead/20260707T162726Z-telegram-baseline-offset-final-verification.json`。
- 验证结果：sandbox/real baseline JSON、production DB offset、ruff、pytest 27 项、OpenEverything/VPS-Config diff check、token/raw-update scan 均通过。
- 边界：真实 Bot API 只调用 `getUpdates`；未 `sendMessage`，未写用户订阅/偏好。

## [2026-07-07] Intel Brief Telegram real update runner one-shot

> 影响模块: `Intel Brief`, `Telegram Bot API`, `Runtime Gate`, `Evidence`

- 新增 `src/intel/telegram_real_update_runner.py` 与 `scripts/intel_telegram_real_update_runner.py`，把真实 Bot API client/sender 接入 offset-safe processor。
- runner 必须显式满足 token、runtime ack、`--allow-real-network`、`--allow-send-message` 四项 gate。
- 真实 one-shot 证据：`packages/clawbot/data/intel_evidence/phaseae/20260707T163143Z-telegram-real-update-runner-one-shot.json`，结果 `no_new_updates`，request offset `684746898`，`send_message_attempted=false`。
- 边界：没有新 update，因此未 `sendMessage`，未写用户订阅/偏好；下一步需用户发送新命令后重跑。

## [2026-07-07] Intel Brief Phase AE 最终验证基线

> 影响模块: `Intel Brief`, `Telegram Runtime`, `Verification`

- 最终验证 evidence：`packages/clawbot/data/intel_evidence/phaseae/20260707T163352Z-telegram-real-update-runner-final-verification.json`。
- 验证结果：real runner evidence、production DB offset、ruff、pytest 32 项、OpenEverything/VPS-Config diff check、token/raw-update scan 均通过。
- 边界：本次无新 update，未 `sendMessage`，未写用户订阅/偏好；真实用户交互验收仍待新命令。


## [2026-07-07] Intel Brief subscription-filtered delivery sandbox

> 影响模块: `Intel Brief`, `Subscription`, `Delivery`, `SQLite`, `Evidence`

- 新增 `packages/clawbot/src/intel/subscription_delivery.py`，把 summary evidence 的来源分类映射到 active/non-expired Telegram 订阅者与 source preferences，只对命中的订阅者投递。
- 新增 `packages/clawbot/scripts/intel_subscription_delivery_sandbox.py` 与 `packages/clawbot/tests/test_intel_subscription_filtered_delivery.py`，验证 eligible=2、sent=2、failed=0，排除未命中分类和过期订阅。
- sandbox 证据：`packages/clawbot/data/intel_evidence/phaseaf/20260707T164449Z-subscription-filtered-delivery-sandbox/evidence.json`。
- 最终验证 evidence：`packages/clawbot/data/intel_evidence/phaseaf/20260707T165346Z-subscription-filtered-delivery-final-verification.json`。
- 边界：sandbox-only，fake sender，`network_calls=0`，未调用 Telegram API，未修改正式 `intel_brief.db` 或 daily LaunchAgent；生产周期仍未接入订阅过滤投递。


## [2026-07-07] Intel Brief production-once subscription delivery switch

> 影响模块: `Intel Brief`, `ProductionOnce`, `Subscription Delivery`, `Runtime Gate`

- `packages/clawbot/src/intel/production_once.py` 新增 `INTEL_BRIEF_SUBSCRIPTION_DELIVERY_ENABLED` feature flag。
- 默认不开关时继续使用已验证 fixed-chat Telegram delivery；开关开启时要求 `INTEL_BRIEF_DB_PATH` 并进入 subscription-filtered delivery。
- 新增/更新 `packages/clawbot/tests/test_intel_production_once.py` 覆盖默认兼容、订阅投递接线、缺 DB 阻断。
- sandbox evidence：`packages/clawbot/data/intel_evidence/phaseag/20260707T165951Z-production-once-subscription-delivery-switch-sandbox/evidence.json`；最终验证：`packages/clawbot/data/intel_evidence/phaseag/20260707T170034Z-production-once-subscription-switch-final-verification.json`。
- 边界：未修改正式 private env、daily LaunchAgent 或生产 DB；未调用真实 Telegram API。


## [2026-07-07] Intel Brief Telegram inline keyboard menu correction

> 影响模块: `Intel Brief`, `Telegram Menu`, `Callback Query`, `Bot UX`

- 按用户截图要求，将 `/start` 菜单从底部 reply keyboard/纯文本说明改为消息内 `inline_keyboard` 按钮矩阵。
- inline 菜单结构：5 行 22 个按钮，覆盖 Github/OpenAI/Claude/Deepseek、微博/小红书/抖音/知乎/B站、天气类、投行/科技/股市/加密、设置/自定义/定时。
- `getUpdates` 现在接收 `callback_query`；runtime 可把按钮点击回调映射回已有 handler；sender 支持 `answerCallbackQuery`。
- 真实发送 evidence：`packages/clawbot/data/intel_evidence/phaseai/20260707T172324Z-real-telegram-inline-keyboard-menu-send/evidence.json`。
- 最终验证 evidence：`packages/clawbot/data/intel_evidence/phaseai/20260707T172410Z-inline-keyboard-menu-final-verification.json`。
- 边界：只修正 Telegram UI/交互层；未授予订阅、未改生产调度、未触发支付/闲鱼/爬虫/远程 worker。

## [2026-07-07] Intel Brief Telegram reference-style menu grid correction

> 影响模块: `Intel Brief`, `Telegram Menu`, `Bot UX`

- 按用户截图要求，继续收敛 `/start` 菜单视觉形态：正文改成短标题/短说明，移除旧的 `命令：/sources...` 文本提示。
- inline keyboard 调整为 4 列优先矩阵：6 行、22 个按钮，最后一行 2 个宽按钮，更接近 Telegram 消息内灰色按钮网格。
- 真实发送 evidence：`packages/clawbot/data/intel_evidence/phaseak/20260707T174008Z-reference-style-telegram-menu-send/evidence.json`。
- 边界：只修正 Telegram UI；未修改订阅授权、daily LaunchAgent、private env、VPS、支付/闲鱼、爬虫或远程 worker。

## [2026-07-07] Intel Brief real subscription-filtered Telegram delivery

> 影响模块: `Intel Brief`, `Subscription Delivery`, `Telegram`, `SQLite`, `Evidence`

- 正式 `intel_brief.db` 中的真实 Telegram subscriber 已获得内部测试订阅授权并配置 `akshare/senate_trading` 偏好。
- 使用真实 daily summary evidence 执行 subscription-filtered delivery：只发送给 active、未过期、偏好命中的 Telegram subscriber。
- 真实发送 evidence：`packages/clawbot/data/intel_evidence/phaseaj/20260707T174622Z-real-subscription-filtered-delivery/evidence.json`，结果 `eligible=1/sent=1/failed=0`，`delivery_log_delta=1`。
- `subscription_delivery` evidence 脱敏加强：不再持久化 `tg:<Telegram user id>`，只记录 `user_id_present`。
- 边界：未修改 LaunchAgent/private env/VPS；daily natural run 尚未切换为订阅投递；闲鱼/支付授权自动化未接入。

## [2026-07-07] Intel Brief daily production delivery switched to subscription-filtered mode

> 影响模块: `Intel Brief`, `ProductionOnce`, `LaunchAgent Runtime Env`, `Subscription Delivery`, `Telegram`

- 私有 env `.openclaw/intel-brief.production.env` 已启用 `INTEL_BRIEF_SUBSCRIPTION_DELIVERY_ENABLED=true` 并配置正式 `INTEL_BRIEF_DB_PATH`；不打印、不提交密钥或 chat id。
- 未重装 LaunchAgent；现有 `ai.openclaw.intel-brief.scheduler` 已通过 `INTEL_BRIEF_PRIVATE_ENV` 读取该私有 env，下一次自然 08:30 daily cycle 将使用订阅/偏好/到期过滤投递。
- `production_once` 订阅投递 gate 加固：DB path 缺失、DB 文件不存在、token 缺失均 blocked，避免误配创建空 DB。
- 受控真实验证 evidence：`packages/clawbot/data/intel_evidence/phaseal/20260707T175654Z-daily-subscription-mode-production-once/evidence.json`，结果 `delivery_mode=subscription_filtered`、`eligible=1/sent=1/failed=0`、`delivery_log_delta=1`。
- 边界：自然 08:30 订阅投递仍需下一次 LaunchAgent 定时触发后审计；支付/闲鱼授权自动化未接入。

## [2026-07-07] Intel Brief controlled production_cycle subscription-mode full path

> 影响模块: `Intel Brief`, `ProductionCycle`, `Subscription Delivery`, `LaunchAgent Script Path`, `Evidence`

- 使用 LaunchAgent 实际调用的同一脚本 `packages/clawbot/scripts/intel_production_cycle.py` 做受控全链路验证。
- 结果：collect `success=2/failed=0`，summary 2 items，production_once `delivery_mode=subscription_filtered`，Telegram delivery `eligible=1/sent=1/failed=0`，`delivery_log` 增至 3 条 success。
- Evidence：`packages/clawbot/data/intel_evidence/phaseam/20260707T180242Z-controlled-production-cycle-subscription-mode/latest-production-cycle.json`。
- 边界：未重装/重启 LaunchAgent；这不是自然 08:30 触发。下一步需等待 natural schedule 后审计。

## [2026-07-07] Intel Brief subscription lifecycle audit/reminder contract

> 影响模块: `Intel Brief`, `Subscription`, `SQLite`, `Evidence`, `Commercial MVP`

- 新增 `packages/clawbot/src/intel/subscription_lifecycle.py`，提供订阅到期审计、过期标记与到期提醒去重能力。
- 默认只读；只有显式 `apply_expiry=True` 才把 active 过期订阅标记为 `expired`；只有显式 `send_reminders=True` 且提供 sender 才发送提醒。
- 新增 `packages/clawbot/scripts/intel_subscription_lifecycle_sandbox.py` 与 `packages/clawbot/tests/test_intel_subscription_lifecycle.py`。
- sandbox evidence：`packages/clawbot/data/intel_evidence/phasean/20260707T181146Z-subscription-lifecycle-sandbox/evidence.json`。
- 正式 DB 只读审计 evidence：`packages/clawbot/data/intel_evidence/phasean/20260707T181219Z-production-db-subscription-lifecycle-readonly-audit/evidence.json`。
- 边界：未真实发送提醒，未修改正式订阅状态，未改 LaunchAgent/private env/VPS。

## [2026-07-07] Intel Brief production_cycle now records subscription lifecycle read-only audit

> 影响模块: `Intel Brief`, `ProductionCycle`, `Subscription Lifecycle`, `Evidence`

- `packages/clawbot/src/intel/production_cycle.py` 已接入订阅生命周期只读审计。
- daily production evidence 现在会包含顶层 `subscription_lifecycle` 字段。
- 审计默认 `apply_expiry=false`、`send_reminders=false`，不会改订阅状态、不会发送到期提醒。
- 若 `INTEL_BRIEF_DB_PATH` 缺失或文件不存在，只记录 `skipped`，不阻断主采集/投递链路。
- 受控集成 evidence：`packages/clawbot/data/intel_evidence/phaseao/20260707T182041Z-production-cycle-lifecycle-readonly-integration/wrapper.json`。
- 边界：使用 injected delivery 避免重复 Telegram 发送；真实投递链路已在 Phase AM 验证。

## [2026-07-07] Intel Brief manual order-to-entitlement bridge

> 影响模块: `Intel Brief`, `Subscription`, `Commercial MVP`, `SQLite`, `Evidence`

- 新增 `packages/clawbot/src/intel/manual_entitlement.py`，作为支付/闲鱼自动化前的人工核单授权入口。
- 新增 `packages/clawbot/scripts/intel_manual_entitlement.py`：默认 dry-run，必须 `--apply` 才写 DB。
- 新增 `packages/clawbot/scripts/intel_manual_entitlement_sandbox.py` 与 `packages/clawbot/tests/test_intel_manual_entitlement.py`。
- 支持续费从现有 active `expires_at` 顺延；订单号只以短哈希进入 audit source，evidence 不含 raw order/chat/user id。
- Sandbox evidence：`packages/clawbot/data/intel_evidence/phaseap/20260707T182938Z-manual-entitlement-sandbox/evidence.json`。
- 正式 DB dry-run evidence：`packages/clawbot/data/intel_evidence/phaseap/20260707T183007Z-production-db-manual-entitlement-dry-run/evidence.json`。
- 边界：未接入支付回调/闲鱼自动化，未修改正式 DB，未发送 Telegram。

## [2026-07-07] Intel Brief Telegram menu adjusted to provided reference screenshot

> 影响模块: `Intel Brief`, `Telegram Menu`, `Bot UX`

- 按用户最新参考图，把 `/start` 菜单进一步改成“热搜入口 + 灰色按钮矩阵”的视觉：正文只保留 `🔥 热搜排行`、高价值情报入口说明、关键词搜索提示，不再在首屏输出 `inactive_or_expired`、已启用分类或 `/sources` 命令说明。
- inline keyboard 当前基线：6 行、23 个按钮、最大 4 列，前 5 行保持 4 列，最后一行为 `⚙️ 设置 / 🔎 自定义 / ⏰ 定时` 快捷入口；按钮 `callback_data` 改为稳定内部值，避免展示文本变化影响回调路由。
- 真实发送 evidence：`packages/clawbot/data/intel_evidence/phasear/20260707T185237Z-reference-screenshot-style-menu-real-send/evidence.json`；sandbox contract evidence：`packages/clawbot/data/intel_evidence/phasear/20260707T185209Z-reference-screenshot-style-menu-contract-v2/evidence.json`；最终验证：`packages/clawbot/data/intel_evidence/phasear/20260707T185522Z-reference-screenshot-menu-final-verification/evidence.json`。
- 边界：只修改 OpenEverything Telegram 菜单合同/测试/证据记录；未修改订阅授权、daily LaunchAgent、private env、VPS、支付/闲鱼、爬虫或远程 worker。

## [2026-07-07] Intel Brief GitHub Trending source production verification

> 影响模块: `Intel Brief`, `Source Adapters`, `Remote Workers`, `Production Cycle`, `Telegram Delivery`

- 新增并验证 `github_trending` 高价值数据源：从 GitHub Trending daily HTML 抽取 repo、url、description、language、stars_today，无需 API token。
- 发现并修复真实页面解析问题：GitHub Trending article 中可能先出现 `/sponsors/...` 链接，旧解析会误识别为仓库；已新增回归测试，限定只从 repo heading 的 `<h2><a>` 提取仓库。
- 修正 `intel_collect_once.py` 的 GitHub fallback profile：`github_trending` 的 oracle-arm1 fallback 不再误标为 `senate_trading`。
- 真实 Oracle SG West worker 证据：`packages/clawbot/data/intel_evidence/phaseaq/20260707T190500Z-github-trending-oracle-sg-worker-parser-fixed.json`，结果 `raw_count=3`，返回 top repos 包含 `Zackriya-Solutions/meetily`、`addyosmani/agent-skills`、`ruvnet/RuView`。
- 受控三源 production cycle 证据：`packages/clawbot/data/intel_evidence/phaseaq/20260707T190718Z-controlled-production-cycle-three-sources/latest-production-cycle.json`，结果 collect `success=3/failed=0`，sources=`senate_trading/akshare/github_trending`，subscription-filtered Telegram delivery 成功。
- 最终验证 evidence：`packages/clawbot/data/intel_evidence/phaseaq/20260707T191656Z-github-trending-final-verification/evidence.json`。
- 边界：未安装服务、未重装 LaunchAgent、未创建长期 worker、未写密钥；远端 worker 仍是 `/tmp` 临时 staging 并 cleanup。

## [2026-07-07] Intel Brief AI model updates source and per-recipient filtered delivery

> 影响模块: `Intel Brief`, `Source Adapters`, `Remote Workers`, `Subscription Delivery`, `Telegram Delivery`

- 新增 `ai_model_updates` 高价值数据源：官方 OpenAI RSS + Anthropic News HTML + DeepSeek 官方首页公告 HTML，输出 `provider/title/url/published_at/summary`，无 API token。
- 目标环境验证：Oracle SG West 真实 worker 调用成功，返回 OpenAI、Anthropic、DeepSeek 三家真实条目。证据：`packages/clawbot/data/intel_evidence/phaseau/20260707T193548Z-ai-model-updates-oracle-sg-worker-final.json`。
- 修复 DeepSeek 目标环境差异：Oracle SG West 访问 `https://www.deepseek.com/news` 返回 404，因此 DeepSeek 源改用目标环境可访问且含官方公告的 `https://www.deepseek.com/`。
- 修复 AI 源截断策略：按 provider/feed 轮询合并，避免 OpenAI RSS 条目过多挤掉 Anthropic/DeepSeek。
- `intel_collect_once.py` 新增 per-source limit：`github_trending=3`，`ai_model_updates=6`，满足 GitHub Top 3 与 AI 三家动态的 MVP 口径。
- 修复 subscription delivery 定制化缺陷：不再只按偏好筛收件人，而是每个 recipient 发送前按 `matched_categories` 裁剪 summary items 和 message 正文；delivery_log 也写入过滤后的内容。
- 四源受控 production cycle：`packages/clawbot/data/intel_evidence/phaseau/20260707T194551Z-controlled-production-cycle-four-sources-source-limits/latest-production-cycle.json`，collect `success=4/failed=0`，GitHub raw_count=3，AI raw_count=6，真实 Telegram subscription-filtered delivery 成功，当前真实订阅者 filtered_item_count=2。
- per-recipient filter sandbox：`packages/clawbot/data/intel_evidence/phaseav/20260707T194902Z-subscription-delivery-per-recipient-filter-sandbox/evidence.json`。
- 最终验证 evidence：`packages/clawbot/data/intel_evidence/phaseau/20260707T195140Z-ai-model-and-recipient-filter-final-verification/evidence.json`。
- 边界：未安装/重装 LaunchAgent，未创建常驻 worker，未修改 VPS 服务或密钥；远端执行仍为临时 `/tmp` staging 并 cleanup。

## [2026-07-07] Intel Brief Telegram menu closer to reference screenshot wide-button layout

> 影响模块: `Intel Brief`, `Telegram Menu`, `Bot UX`, `Evidence`

- 在 Phase AR 截图风格菜单基础上，新增最后一行 2 个宽按钮：`🔍 备用搜索` 与 `👥 设置导航`，更贴近用户参考图中底部两个宽入口的视觉结构。
- `search` callback 现在返回关键词搜索提示；`👥 设置导航` 复用 settings/status 入口，不在首屏展示订阅状态噪音。
- 当前 `/start` inline keyboard 基线：7 行、25 个按钮，前 6 行保留情报分类/设置入口，最后一行为两列宽入口。
- Sandbox evidence：`packages/clawbot/data/intel_evidence/phasear/20260707T200639Z-reference-screenshot-style-menu-with-wide-row-sandbox/evidence.json`；真实 Telegram send evidence：`packages/clawbot/data/intel_evidence/phasear/20260707T200700Z-reference-screenshot-style-menu-with-wide-row-real-send/evidence.json`。
- 边界：只改 Telegram 菜单合同和测试；未修改订阅授权、production DB、LaunchAgent、private env、VPS、支付/闲鱼、爬虫或远程 worker。

## [2026-07-07] Intel Brief institutional 13F source aggregation and five-source production cycle

> 影响模块: `Intel Brief`, `Source Adapters`, `SEC EDGAR`, `Remote Workers`, `Production Cycle`, `Subscription Delivery`

- 完成 `institutional_13f` 数据源质量修复：SEC 13F information table 里同一 `(issuer, class, cusip)` 多行现在会聚合，`value_thousands_usd` 与 `shares` 可解析为整数时求和，并按持仓价值降序输出，避免 Berkshire 最新 13F 前 10 条被同一发行人拆分行占满。
- `registry.py` 的 `institutional_13f` evidence path 已从 pending 更新为 Oracle SG West 真实聚合验证证据。
- Oracle SG West 真实 worker 调用成功：`raw_count=10`，返回 Apple、American Express、Coca Cola、Bank of America、Chevron 等聚合后持仓，远端 `/tmp` staging cleanup 成功。
- 五源受控 production cycle 成功：`senate_trading / akshare / github_trending / ai_model_updates / institutional_13f` 全部成功，collect `success=5/failed=0`，summary 21 items，subscription-filtered Telegram delivery `eligible=1/sent=1/failed=0`。
- Evidence：13F real worker `packages/clawbot/data/intel_evidence/phaseaw/20260707T201214Z-institutional-13f-oracle-sg-worker-aggregated.json`；五源 cycle `packages/clawbot/data/intel_evidence/phaseaw/20260707T201455Z-controlled-production-cycle-five-sources-13f-aggregated/latest-production-cycle.json`。
- 边界：未安装/重装 LaunchAgent，未创建常驻 worker，未新增密钥；远端执行仍为临时 `/tmp` staging 并 cleanup。当前真实 subscriber 偏好仍只命中 `akshare/senate_trading`，因此本次真实推送正文按偏好过滤为 2 条。

## [2026-07-07] Intel Brief Telegram category buttons no longer overwrite preferences

> 影响模块: `Intel Brief`, `Telegram Menu`, `Source Preferences`, `Subscription UX`

- 修正商业化订阅菜单交互：点击分类按钮不再把已有 source preferences 全量覆盖为单一分类。
- 新行为：菜单分类按钮为“未全选则追加 / 已全选再点则取消该按钮对应分类”；显式 `/sources ...` 命令仍保留替换语义，方便运营或高级用户一次性重置偏好。
- 例子：先点 `股市` 得到 `akshare / institutional_13f / senate_trading`；再点 `Github` 会追加 `github_trending`；再点一次 `Github` 只取消 `github_trending`，不影响股市组合。
- Sandbox evidence：`packages/clawbot/data/intel_evidence/phaseax/20260707T202835Z-telegram-menu-button-preference-toggle-sandbox/evidence.json`。
- 真实 Telegram update runner evidence：`packages/clawbot/data/intel_evidence/phaseax/20260707T202846Z-telegram-real-update-runner-button-preference-cycle.json`，本次处理 1 条真实 `/start` update 并成功回发新版 inline keyboard，未持久化 raw update/chat id。
- 边界：未修改订阅授权、套餐、支付/闲鱼、LaunchAgent、VPS 或采集 worker；正式 DB 仅因真实 `/start` 处理而 upsert 同一 Telegram subscriber/chat 映射，当前偏好仍为 `akshare/senate_trading`。

## [2026-07-07] Intel Brief Telegram preferences use user-facing category labels

> 影响模块: `Intel Brief`, `Telegram Menu`, `Subscription UX`, `Evidence`

- Telegram `/sources`、分类按钮回包与 `/status` 不再向用户展示 `akshare`、`senate_trading`、`github_trending` 等内部 category id。
- 新增用户可读展示名：如 `A股资金流向`、`国会持仓`、`GitHub趋势`、`机构13F持仓`、`AI模型动态` 等；内部 `enabled_categories` 字段仍保留原始 id，便于投递过滤和审计。
- Sandbox evidence：`packages/clawbot/data/intel_evidence/phaseay/20260707T203616Z-telegram-menu-user-facing-category-labels-sandbox/evidence.json`，同时记录内部 flow 与 `button_preference_flow_display` 中文展示 flow。
- 边界：只改 Telegram 文案/证据，不改 DB schema、订阅授权、LaunchAgent、VPS、支付/闲鱼或采集 worker。

## [2026-07-07] Intel Brief weather/air/alert source verified and added to default cycle

> 影响模块: `Intel Brief`, `Source Adapters`, `Weather`, `Remote Workers`, `Production Cycle`, `Subscription Delivery`

- 新增 `weather` 数据源，覆盖菜单里的 `天气 / 空气 / 降雨 / 温度 / 湿度 / 灾害` 子类。
- 数据源实现：美国 NWS `api.weather.gov` 负责 hourly weather、temperature、rainfall probability、humidity、active alerts；Open-Meteo Air Quality 无 Key endpoint 负责 `air_quality` MVP 数据。
- `weather` item 同时保留 `source=weather` 和具体 `category` / `category_aliases`；subscription delivery 已支持按 alias 匹配，因此订阅 `weather` 可收到全部天气子类，订阅 `temperature` 只收到温度类 item。
- `DEFAULT_MVP_CATEGORIES` 已加入天气子类，人工授权默认覆盖天气菜单能力。
- Oracle SG West real worker evidence：`packages/clawbot/data/intel_evidence/phaseaz/20260707T204803Z-weather-oracle-sg-worker.json`，`raw_count=6`，样本包含 Denver weather/temperature/rainfall/humidity/active alert/air quality。
- 六源受控 production cycle evidence：`packages/clawbot/data/intel_evidence/phaseaz/20260707T205021Z-controlled-production-cycle-six-sources-weather/latest-production-cycle.json`，collect `success=6/failed=0`，summary 27 items，subscription-filtered Telegram delivery success。
- 商业边界：NWS API 要求自定义 User-Agent；Open-Meteo 文档显示无 Key 免费/非商业使用与商业使用边界，付费订阅正式商业化前需复核/替换为空气质量合规来源或购买商业访问，不把该免费 endpoint 当成最终商业合规结论。
- 边界：未重装 LaunchAgent，未创建常驻 worker，未新增密钥；远端执行仍为 `/tmp` 临时 staging 并 cleanup。

## [2026-07-07] Intel Brief Telegram menu aligned to user screenshot wording

> 影响模块: `Intel Brief`, `Telegram Menu`, `Bot UX`, `Evidence`

- 按用户最新截图将 `/start` 菜单继续收敛为“热搜排行卡片 + 多列灰色按钮矩阵”的 Telegram inline keyboard 风格。
- 首屏正文改为：`🔥 热搜排行`、`🔥 近期高价值情报排行榜`、`发送关键词🔍搜索你感兴趣的内容`；不展示订阅状态、内部 category id 或 `/sources` 帮助噪音。
- 第 6 行按钮改为无额外图标的 `设置 / 自定义 / 定时`，更接近截图中的纯文本分类按钮；最后一行改为 `🔍 情报搜索 / 👥 功能导航` 两个宽入口。
- 新增/保留回调兼容：`🔍 情报搜索` 进入关键词搜索提示，`👥 功能导航` 进入 status/settings；旧 `备用搜索/设置导航` callback 仍作为兼容别名。
- Sandbox evidence：`packages/clawbot/data/intel_evidence/phaseba/20260707T210354Z-screenshot-style-telegram-menu-v3/evidence.json`；真实 Telegram send evidence：`packages/clawbot/data/intel_evidence/phaseba/20260707T210719Z-screenshot-style-menu-v3-real-send/evidence.json`。
- 边界：只改 Telegram 菜单合同、handler 文案映射、测试和文档；未改 production DB、LaunchAgent、private env、VPS、支付/闲鱼、爬虫或远程 worker。

## [2026-07-07] Intel Brief LaunchAgent natural 08:30 audit verified via artifact evidence

> 影响模块: `Intel Brief`, `LaunchAgent`, `Production Audit`, `Evidence`

- 修正 `intel_launchagent_audit.py` 的判定逻辑：当 `launchctl print` 的 `runs/last exit code` 计数没有更新，但正式 LaunchAgent 仍加载、日历触发配置存在、stdout 与 `latest-production-cycle.json` 均显示成功时，审计可标记为 `verified_success`，并显式记录 `launchctl.counter_mismatch=true`。
- 复核正式 daily LaunchAgent `ai.openclaw.intel-brief.scheduler` 的自然 08:30 运行：`latest-production-cycle.json` 时间戳为 `2026-07-07T14:30:05Z`，collect `success=2/failed=0`，production_once success，真实 Telegram send success 且 message_id present。
- Read-only audit evidence：`packages/clawbot/data/intel_evidence/phaset/20260707T211424Z-launchagent-natural-0830-verified-with-artifact/evidence.json`。
- 边界：本次只是只读审计和审计脚本修复；没有执行 `launchctl kickstart/bootstrap/bootout`，没有重装 plist，没有改 private env/VPS/远程 worker/生产 DB/支付/闲鱼。该自然运行发生在后续 GitHub/AI/13F/weather 接入前，因此它证明“正式 LaunchAgent 自然 08:30 可触发并真实投递”，但不证明“六源默认链路已经自然触发”；六源链路已有受控 production cycle 证据，下一次自然 08:30 仍需复审。

## [2026-07-07] Intel Brief subscription lifecycle production-safe maintenance CLI

> 影响模块: `Intel Brief`, `Subscriptions`, `Lifecycle`, `Telegram Reminder`, `Evidence`

- 新增 `packages/clawbot/scripts/intel_subscription_lifecycle.py`，为订阅到期管理提供生产安全入口。
- 默认模式只读：审计正式 `intel_brief.db` 中 active 订阅是否已过期、是否 7 天内到期，不改库、不发 Telegram。
- `--apply-expiry` 只有在提供 `INTEL_BRIEF_SUBSCRIPTION_LIFECYCLE_APPLY_ACK=I_UNDERSTAND_INTEL_BRIEF_LIFECYCLE_APPLY` 或 `--apply-ack` 时才会把已过期 active 订阅标记为 expired 并写 audit。
- `--send-reminders` 只有在 Telegram token 存在、既有 Telegram runtime ack 存在、且显式 `--allow-real-network` 时才会发送到期提醒；提醒 audit 仍按 subscriber/plan/day 去重。
- Sandbox evidence：`packages/clawbot/data/intel_evidence/phasebc/20260707T212320Z-subscription-lifecycle-maintenance-sandbox/evidence.json`，覆盖 readonly、缺 ack 阻断、apply、注入 transport reminder。
- Production read-only evidence：`packages/clawbot/data/intel_evidence/phasebc/20260707T212337Z-subscription-lifecycle-production-readonly/evidence.json`，当前正式 DB 无已过期 active 订阅、无 7 天内到期候选，`network_calls=0`。
- 边界：本阶段没有对正式 DB 执行 apply，没有真实发送提醒；没有改 LaunchAgent/private env/VPS/远程 worker/支付/闲鱼/爬虫。证据不含 Telegram token/chat id/user id。

## [2026-07-07] Intel Brief LaunchAgent next-run six-source readiness audit

> 影响模块: `Intel Brief`, `LaunchAgent`, `Production Cycle`, `Evidence`

- 新增只读 readiness 审计：`packages/clawbot/src/intel/launchagent_readiness.py` 与 `packages/clawbot/scripts/intel_launchagent_next_run_readiness.py`。
- 审计 installed LaunchAgent plist 的 `ProgramArguments`，确认它调用 `intel_production_cycle.py` 且没有固定旧 `--source` 参数，因此下一次自然触发会读取当前 `DEFAULT_PRODUCTION_CYCLE_SOURCES`。
- 当前默认源为六源：`senate_trading / akshare / github_trending / ai_model_updates / institutional_13f / weather`。
- 同时读取六源 controlled cycle evidence，确认 controlled collect `success=6/failed=0`，并关联上一条自然 08:30 verified audit。
- Evidence：`packages/clawbot/data/intel_evidence/phasebd/20260707T213012Z-launchagent-next-run-six-source-readiness/evidence.json`，结果 `status=ready`、`missing=[]`、`network_calls=0`。
- 边界：只读审计；未执行 `launchctl kickstart/bootstrap/bootout`，未重装 plist，未改 private env/VPS/远程 worker/生产 DB/支付/闲鱼/爬虫，也未调用 Telegram。该 evidence 证明“下一次自然运行将使用六源默认链路”的 readiness，不替代下一次自然 08:30 后的真实审计。

## [2026-07-07] Intel Brief user-facing delivery copy and E2E status audit

> 影响模块: `Intel Brief`, `Telegram Delivery`, `Subscription Delivery`, `Commercial MVP Evidence`

- 修复真实 Telegram 投递正文误用 sandbox 文案的问题：`build_delivery_message()` 默认改为生产可见文案，末尾显示“内容来自公开来源自动汇总，不构成投资建议”；sandbox fake sender 调用显式传 `delivery_context="sandbox"`，仍保留测试边界。
- 通过 gated `production_once` 对真实订阅者发送一次修正文案后的 subscription-filtered 消息：`eligible=1/sent=1/failed=0`，matched categories=`akshare/senate_trading`，filtered item count=2，真实 Telegram send success。
- 新增 E2E 状态审计：`packages/clawbot/src/intel/e2e_status_audit.py` 与 `packages/clawbot/scripts/intel_e2e_status_audit.py`，只读汇总正式 DB 的真实 subscriber、订阅/偏好、最新 delivery_log、六源 next-run readiness 和最近 production delivery evidence。
- E2E evidence：`packages/clawbot/data/intel_evidence/phasebe/20260707T213933Z-commercial-mvp-e2e-status-audit/evidence.json`，结果 `status=verified`，active eligible subscriber=1，latest delivery success，latest delivery 不含 sandbox/fake 文案，按偏好过滤且无未订阅源标记。
- Real delivery evidence：`packages/clawbot/data/intel_evidence/phasebe/20260707T213634Z-production-once-user-facing-delivery-copy/evidence.json`。
- 边界：本次真实发送 1 条 Telegram 用于文案修复验收；未修改 LaunchAgent/private env/VPS/远程 worker/支付/闲鱼/爬虫。E2E audit 本身只读，证据不写 token/chat id/user id/raw message content。

## [2026-07-07] Intel Brief Telegram menu v4 matches reference with persistent shortcuts

> 影响模块: `Intel Brief`, `Telegram Menu`, `Bot UX`, `Telegram Bot API`, `Evidence`

- 修正用户指出的菜单问题：`/start` 不再输出“订阅状态 / 已启用分类 / 命令提示”这类状态页噪音，而是发送截图式“热搜排行”菜单卡片。
- 菜单正文改为 `CARVEN 情报简报`、`🔥 热搜排行`、`🔥 近期高价值情报排行榜`、`发送关键词🔍搜索你感兴趣的内容`。
- inline keyboard 调整为 4 列优先的矩阵：`Github/OpenAI/Claude/Deepseek`、社媒、天气、财经、设置区；底部宽入口为 `🔍 备用搜索 / 👥 功能导航`。
- 新增 persistent bottom shortcut keyboard：`👥 功能导航 / 🔥 热搜排行`，因此真实 Telegram 中会先发一条快捷入口安装消息，再发一条 inline 菜单卡片；这是为了接近用户截图中“消息内按钮 + 输入框上方快捷按钮”的组合效果。
- 修正 `👥 功能导航` 行为：不再跳到 status/settings 状态文本，而是回到菜单卡片；普通关键词文本会进入搜索提示，不再直接报未知命令。
- 注册 Telegram native commands 已通过 `setMyCommands` 真实调用验证。
- Sandbox evidence：`packages/clawbot/data/intel_evidence/phasebf/20260707T215214Z-screenshot-like-telegram-menu-v4/evidence.json`。
- Telegram command registration evidence：`packages/clawbot/data/intel_evidence/phasebf/20260707T215248Z-telegram-command-menu-registration-v4.json`。
- Real Telegram send evidence：`packages/clawbot/data/intel_evidence/phasebf/20260707T215317Z-screenshot-like-menu-v4-real-send/evidence.json`，真实发送 2 条消息，均成功，证据只记录 token/chat id 存在性与脱敏发送结果。
- 边界：只改 Telegram 菜单合同、runtime 多消息发送支持、测试和文档；未修改 LaunchAgent/private env/VPS/远程 worker/生产订阅授权/支付/闲鱼/爬虫。证据不写 Telegram token、chat id、user id 或 raw update payload。

## [2026-07-07] Intel Brief LaunchAgent audit now requires expected six-source proof

> 影响模块: `Intel Brief`, `LaunchAgent`, `Production Audit`, `Evidence`

- 强化 `intel_launchagent_audit.py`：新增重复参数 `--expected-source`，用于要求 `latest-production-cycle.json` 中指定数据源全部出现且 collect 成功。
- `build_launchagent_post_run_audit()` 现在会记录 `sources`、`expected_sources`、`sources_match_expected`、`collect_success_matches_expected`、`missing_expected_sources`、`unexpected_sources` 与 `failed_sources`。
- 当提供 expected sources 时，`verified_success` 不再只依赖 run artifact 成功和 Telegram send 成功；还必须满足源列表与 expected sources 一致、collect success 数等于 expected 数、failed=0、每个 expected source 都有 success run。
- 回归证据：使用旧自然 08:30 两源 artifact 运行六源 expected audit，正确返回 `failed_or_incomplete`，缺失 `github_trending / ai_model_updates / institutional_13f / weather`。
- Evidence：`packages/clawbot/data/intel_evidence/phasebg/20260707T220027Z-launchagent-six-source-expected-regression/evidence.json`。
- 边界：只读审计和测试增强；未执行 `launchctl kickstart/bootstrap/bootout`，未重装 plist，未修改 private env/VPS/远程 worker/生产 DB/订阅授权/支付/闲鱼/爬虫，也未调用 Telegram 或数据源网络。

## [2026-07-07] Intel Brief E2E status audit now gates on natural six-source LaunchAgent proof

> 影响模块: `Intel Brief`, `Commercial MVP Audit`, `LaunchAgent`, `Evidence`

- 强化 `intel_e2e_status_audit.py`：新增 `--launchagent-audit-evidence`，商业 MVP E2E `verified` 现在必须引用一份自然 08:30 LaunchAgent post-run audit，并且该 audit 必须为 `verified_success`、`expected_sources_checked=true`、六源匹配且 collect 全部成功。
- E2E checks 新增 `natural_six_source_launchagent_verified`；缺失或失败时即使 subscriber、偏好、最新投递和 next-run readiness 都正常，整体 status 也只能是 `needs_attention`。
- 当前生产状态 evidence：`packages/clawbot/data/intel_evidence/phasebh/20260707T220524Z-commercial-mvp-e2e-requires-natural-six-source/evidence.json`。
- 当前结果：active eligible subscriber=1，latest delivery success，next-run readiness=ready，但引用的自然 LaunchAgent audit 为 `failed_or_incomplete`，缺失 `github_trending / ai_model_updates / institutional_13f / weather`，所以 E2E status 正确保持 `needs_attention`。
- 边界：只读审计和测试增强；未执行 `launchctl kickstart/bootstrap/bootout`，未修改 LaunchAgent/private env/VPS/远程 worker/生产 DB/订阅授权/支付/闲鱼/爬虫，也未调用 Telegram 或数据源网络。

## [2026-07-10] Intel Brief 每日推送改为用户可读的稳定降级简报
> 领域: `backend`
> 影响模块: `Intel Brief`, `Subscription Delivery`, `Telegram UX`
> 关联问题: `Daily Brief fallback UX`
### 变更内容
- 生产简报不再暴露 `partial_fallback`、模型家族和 Token 数；降级时改为普通用户看得懂的稳定整理提示。
- 订阅筛选后按每位用户实际命中的条目生成专属“今日重点”，展示来源分布和前三条重点，不再覆盖成“查看输入条目”的空文案。
- 精选情报从固定前 5 条提升为最多 8 条；超过 8 条时明确提示剩余数量，修复计数与明细不一致。
- 清理摘要中的 Markdown 标题符号，并对 Telegram HTML 敏感字符做转义，降低消息格式错误风险。
- 点击“今日简报”时复用最新成品简报，不再叠加重复标题；零符合订阅者场景返回空成功结果。
### 文件变更
- `packages/clawbot/src/intel/delivery.py` — 重做生产简报排版、稳定降级提示、8 条展示和 HTML 安全处理。
- `packages/clawbot/src/intel/subscription_delivery.py` — 增加订阅者专属总览和零订阅者安全返回。
- `packages/clawbot/src/intel/channel_menu.py` — 避免“今日简报”重复标题。
- `packages/clawbot/tests/test_intel_delivery_sandbox.py` — 增加降级隐藏、8 条展示和 HTML 转义回归。
- `packages/clawbot/tests/test_intel_subscription_filtered_delivery.py` — 增加专属总览与零订阅者回归。
- `packages/clawbot/tests/test_intel_telegram_menu_handlers.py` — 增加今日简报单标题回归。
- `docs/009-health.md` — 登记问题根因、修复范围和验证证据。

## [2026-07-10] 每日简报 / CC中转最终审计补齐文档治理硬门
> 领域: `docs` | `infra`
> 影响模块: `Intel Brief`, `CC中转`, `文档治理`, `CI`
> 关联问题: HI-docs-governance-final-audit
### 变更内容
- 修复项目文档治理漂移：把根目录 Intel Brief 历史验收报告移动到 `docs/084-intel-brief-implementation-report.md`，并明确它是历史阶段证据，不代表当前生产状态。
- 删除违反 `docs/` 禁止子目录规则、且任务已经完成的 `docs/superpowers/` 补充执行计划；现有有效内容继续由 `docs/052-intel-brief-master-plan.md` 和 `docs/084-intel-brief-implementation-report.md` 承接。
- 新增 `scripts/check_docs_layout.sh` 和 `make docs-check`，自动拦截根目录散落文档、`docs/` 子目录、非编号命名、索引漏登记和陈旧索引引用。
- 将文档治理检查接入 `make ci-local`，避免后续 AI 或人工再次制造同类漂移。
- 完整 CI 首轮发现 `src/intel/wechat_bridge_runtime.py` 使用 `datetime.UTC`，会破坏 Intel worker 的 Python 3.10 兼容门；已改回 `timezone.utc` 并用行级 Ruff 说明保留兼容性。
### 文件变更
- `docs/084-intel-brief-implementation-report.md` — 归档 Intel Brief 历史阶段验收报告并标注时效边界。
- `docs/003-docs-index.md` — 删除违规子目录入口并登记 084 报告。
- `scripts/check_docs_layout.sh` / `Makefile` — 新增文档治理硬门并接入本地 CI。
- `packages/clawbot/src/intel/wechat_bridge_runtime.py` — 修复 Python 3.10 worker 不支持 `datetime.UTC` 的兼容问题。
- `docs/006-registries.md` / `docs/009-health.md` — 登记新命令和最终审计结论。
### 验证
- `bash -n scripts/check_docs_layout.sh`：通过。
- `make docs-check`：`22 个文档，目录扁平、命名合规、索引完整`。
- `cd apps/frist-api && npm test`：`187 passed / 0 failed`。
- `cd packages/clawbot && .venv312/bin/python -m pytest tests/test_intel_brief_dry_run.py tests/test_intel_delivery_sandbox.py tests/test_intel_subscription_filtered_delivery.py tests/test_intel_telegram_menu_handlers.py tests/test_intel_wechat_bridge_runtime_acceptance.py tests/test_wechat_numbered_commands.py tests/test_social_extension_status.py -q --maxfail=5`：`96 passed`。
- `make ci-local`：Ruff、Python 全量测试、Python 语法、前端 TypeScript、docs-check 全部通过。

## [2026-07-10] 全量工作区提交与维护基线确立
> 领域: `infra` | `docs` | `backend` | `frontend`
> 影响模块: `Intel Brief`, `CC中转`, `New-API`, `Xianyu`, `Social Pilot`, `维护基线`
> 关联问题: HI-maintenance-baseline-20260710
### 变更内容
- 将当前每日简报、CC中转、闲鱼自动发货、微信桥、浏览器扩展、运营脚本、测试与治理文档作为一个完整维护基线提交，不再保留散落的未提交源码。
- 把 New-API submodule 的 CC中转品牌修改保存为 `scripts/patches/new-api-cc-brand.patch`，submodule 恢复到可从官方上游获取的干净 `v1.0.0-rc.4`，避免提交无法推送到 `QuantumNous/new-api` 的本地 detached commit。
- 新增 `scripts/apply_new_api_brand_patch.sh` / `make new-api-brand-patch`；`new-api-check` 和 `new-api-sync` 会检查品牌补丁与上游版本的兼容性，升级后再显式应用补丁。
- 将 `output/` 和 `packages/clawbot/relative-launch/` 标记为本地可再生成验收产物，不提交 PID、浏览器快照或临时 LaunchAgent 包。
- 基线使用本地 annotated tag `baseline-2026-07-10` 标记，便于以后比较、回滚和继续维护。
### 文件变更
- `scripts/patches/new-api-cc-brand.patch` — 保存 New-API CC中转品牌差异。
- `scripts/apply_new_api_brand_patch.sh` / `scripts/sync_new_api_upstream.sh` / `Makefile` — 增加品牌补丁应用与升级兼容门。
- `.gitignore` — 排除本地验收输出和可再生成 LaunchAgent 包。
- `docs/002-changelog.md` / `docs/006-registries.md` / `docs/009-health.md` — 登记维护基线和后续升级方式。
### 验证
- `make ci-local`：Ruff、Python 全量测试、Python 语法、前端 TypeScript、docs-check 全部通过。
- `cd apps/frist-api && npm test`：`187 passed / 0 failed`。
- `node --test scripts/*.test.mjs`：`8 passed / 0 failed`。
- `node --test packages/openclaw-npm/assets/chrome-extension/test/*.test.mjs`：`85 passed / 0 failed`。
- `bash -n scripts/apply_new_api_brand_patch.sh scripts/sync_new_api_upstream.sh scripts/check_docs_layout.sh`：通过。
- New-API submodule：`git status --short` 为空；品牌补丁 `git apply --check` 通过。
- `git diff --check`：通过。
- staged snapshot `gitleaks dir`：扫描约 `24.26 MB`，`no leaks found`.
