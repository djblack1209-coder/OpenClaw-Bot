# HANDOFF — 会话交接摘要

> 最后更新: 2026-05-02

---

## [2026-05-02 20:42] Frist-API 备用渠道与公网实测交接

### 本次完成了什么
- 已提交工作区原有改动: `dc7d373 feat: stabilize frist api connectivity`。
- 已新增 CPA JSON、chong 和其他人工备用渠道入口；这些来源默认隔离，必须人工核验并勾选风险确认后才会进入路由。
- 用户端 Dashboard、模型列表、广场和导入配置不暴露 CPA/chong、风险备注、上游来源和原始 Key。
- 已修复公网实测发现的库存问题: 当所有候选上游都返回认证失败、网络失败或 5xx 时，网关返回 503 但会把 failed/exhausted 状态写入运行数据，避免模型继续假显示可用。
- 已同步到腾讯云 `/opt/frist-api`，`frist-api-server` 容器为 healthy；服务器本机 smoke 通过，公网主页 200、管理页 404、未授权 `/v1/models` 401、验证码挑战可用。

### 未完成的工作
- 公网真实上游当前返回 `API key is disabled`，两枚库存已自动落盘为 failed，`gpt-5.5` 和 `gpt-image-2` 已从带 Key 的 `/v1/models` 下线。
- 需要补入一枚真实可用、授权明确的上游 Key 后，再复测广场 `gpt-5.5` 对话和 `gpt-image-2` 图片生成。
- 正式开放陌生付费用户前仍缺固定域名 HTTPS、SMTP/找回密码、Turnstile、真实支付回调、数据库迁移、备份、监控和管理员 2FA。

### 需要注意的坑
- 不要实现 OAuth Session 提取、Refresh Token 刷新、账号池规避风控或自动化批量获取逻辑；CPA JSON/chong 只能作为人工风险判断后的备用登记入口。
- 不要把服务器密码、管理员入口码、管理员令牌、用户真实 Key、上游 Key 或运行时 JSON 写入仓库、文档或最终汇报。
- 远端 `/opt/frist-api/.env` 已设置隐藏管理页入口码和 `FRIST_API_REQUIRE_CAPTCHA=1`，不要覆盖。

### 当前系统状态
- 本地 Frist-API `npm test`: 103 passed, 0 failed。
- 本地 focused 服务端回归: 51 passed, 0 failed。
- 公网 `http://101.43.41.96:5566/` 可访问；`http://101.43.41.96:5566/admin.html` 返回 404。
- 带现有用户 Key 调用公网 `/v1/models` 在失效库存下线后返回 0 个模型；这是当前正确状态，等待新可用上游补入。

## [2026-05-02 00:40] Frist-API 用户端降噪与公网同步交接

### 本次完成了什么
- 用户端移除左侧导航、不可点击分组文字、sticky 顶栏和旧版高密度说明，首页只保留余额、模型消耗、Claude/OpenAI 连通性和 API Key/充值/CC Switch 三个入口。
- 注册和登录收进右上角账户菜单，API 页面只保留创建 Key、Key 开关和请求地址。
- CC Switch 导入扩展为 Claude、Codex、OpenCode、OpenClaw、Hermes 五个客户端，导入链接包含请求地址、模型、`auth.json` 和 `config.toml`。
- 公开 HTML 初始值改为未登录、0 元和 `FA`，避免后端数据加载前闪现演示套餐或演示消耗。
- 游客 Dashboard 归一化为 0 余额、0 消耗和 0 调用，未登录滚动时不再看到演示账单。
- 充值页面三档选项改为三列，只保留类型和金额，去掉多余说明文字。
- 注册/登录接入轻量验证码挑战和认证限流，公开模式保持验证码不回显、演示充值关闭。
- 管理端普通 `/admin.html` 已隐藏为 404，必须用服务器环境变量里的隐藏入口码加载，再输入管理员令牌。
- 补号订单文本清洗覆盖请求地址、卡密、额度、到期、模型、认证字段、认证前缀和额外请求头；用户侧 CC Switch 导入只暴露 Frist-API 供应商、用户 Key 和公开网关。
- 网关保留小时卡、日卡、月卡、不限时、默认池优先级，会话粘滞、故障切换上下文保留、流式透传和低库存通知钩子。
- 已同步到腾讯云临时公网 `http://101.43.41.96:5566/`，普通管理页公网访问返回 404。
- 更新快速启动、腾讯云部署指南、命令注册表、设计文档、HEALTH 和 CHANGELOG。

### 未完成的工作
- 正式开放陌生付费用户前仍缺域名 HTTPS、SMTP/找回密码、Turnstile、管理员正式登录、2FA、真实支付回调、数据库迁移、备份和探测预算队列。
- 当前轻量后端仍用 JSON 运行数据，适合小范围验收，不适合长期大规模运营。

### 需要注意的坑
- 不要把服务器密码、管理员令牌、用户真实卡密、上游 Key 或运行时 JSON 写入仓库、文档或最终汇报。
- 生产必须保持 `FRIST_API_ALLOW_DEMO_RECHARGE=0` 和 `FRIST_API_EXPOSE_VERIFICATION_CODE=0`。
- 生产必须保持 `FRIST_API_ADMIN_PAGE_CODE`、`FRIST_API_REQUIRE_CAPTCHA=1` 和认证限流。
- 用户端不能再加入补号、号源、价格草稿、渠道写入、倍率、模型映射等管理端内容。

### 当前系统状态
- `npm test` 当前为 74 passed, 0 failed。
- 语法检查已覆盖 `app.js`、`serverClient.js`、`server.js`。
- 公网 `http://101.43.41.96:5566/api/frist/challenge` 可返回验证码挑战；`http://101.43.41.96:5566/admin.html` 返回 404；游客 Dashboard 为 0 消耗。
- 本地入口: `http://127.0.0.1:3180/`；公网验收入口: `http://101.43.41.96:5566/`。
- OpenClaw 后端、桌面端、内部 New API 管理页面未改动。

## [2026-05-01 17:45] Frist-API 公开试用业务安全交接

### 本次完成了什么
- 用户链路从“注册后使用”补到“注册 / 登录 / 验证 / 充值 / 兑换 / 创建 Key / 开关 Key / CC Switch 导入 / 网关调用 / 用量扣费”。
- 网关现在会先检查用户余额，余额不足时不访问上游，避免亏损；成功请求后按套餐额度优先、加油包兜底的顺序扣费。
- 日卡池切换加固: 上游 Key 额度不足、上游返回余额不足、上游 5xx 或网络失败时会摘除当前 Key，并切到同池下一枚健康 Key。
- 日卡套餐到期会在网关路由前清空套餐额度并切回默认套餐，旧日卡不能继续走日卡池。
- 兑换码改为一次性使用，同一张日卡/月卡/加油包不能被多个用户重复兑换。
- 管理端补号支持自动探测、严格探测和信任写入；未填写模型时会先按请求地址做一次 `/models` 探测，再逐 Key 做最低成本聊天健康检查。
- 用户侧模型连通性按模型聚合显示可用线路数量，不再把每枚上游 Key 展示成客户状态卡。
- 公开环境默认关闭演示充值；用户侧充值按钮只生成待处理充值单，管理端新增按邮箱人工确认入账。

### 未完成的工作
- 仍然使用 JSON 文件保存运行数据，小范围试用可以，扩大公开前要迁移 SQLite/PostgreSQL 或 New-API fork 数据库。
- 还缺 SMTP、找回密码、Turnstile、管理员正式登录、2FA、真实支付回调、订单审计和限流。
- 价格草稿仍未做管理员确认后上线的完整配置流。

### 需要注意的坑
- `data/frist-api/runtime/runtime.json` 会包含用户 Key 和上游 Key，必须保持未跟踪。
- 默认开发管理员令牌不能用于公开生产；生产必须设置强随机 `FRIST_API_ADMIN_TOKEN` 和 `FRIST_API_SESSION_SECRET`。
- 用户端不要加入补号、号源、价格草稿、渠道写入等管理端内容。

### 当前系统状态
- 当时 `make frist-api-test` 为 42 passed, 0 failed。
- 本地完整链路入口: `make frist-api-dev`，用户端 `http://127.0.0.1:3180`，管理端 `http://127.0.0.1:3180/admin.html`。
- OpenClaw 后端、桌面端、内部 New API 管理页面未改动。

## [2026-05-01 16:26] Frist-API 公开能用链路交接

### 本次完成了什么
- 补号助手增加代理请求地址，补号时会对直连和代理做低成本聊天探测，并把更优路径写入 `routeBaseUrl`。
- 网关转发上游时优先使用补号探测得到的 `routeBaseUrl`，弱服务器只做鉴权、计费和转发，不承担本地推理。
- 上游不支持 `/models` 时，系统会按内置模型清单逐个做低成本探测，只把通过的模型写入号源档案和凭证。
- 管理端粘贴的价格文本已参与真实扣费；上游返回 `usage` 时按输入/输出 token 和销售价扣用户套餐额度、加油包额度以及上游库存额度。
- 日卡链路继续加固: Key 额度不足、上游余额不足、上游 5xx、网络失败会摘除当前 Key 并切到同池下一枚健康 Key；日卡套餐过期会清空套餐额度并切回默认套餐。

### 未完成的工作
- 仍然使用 JSON 文件保存运行数据，小范围实测可以，扩大公开前要迁移 SQLite/PostgreSQL 或 New-API fork 数据库。
- 还缺 SMTP、找回密码、Turnstile、管理员正式登录、2FA、真实支付回调、订单审计、限流和探测预算队列。
- 当前模型能力探测只做低成本可用性判断，尚未做真实上下文上限、工具调用、流式能力和质量评分。

### 需要注意的坑
- 生产必须设置强随机 `FRIST_API_ADMIN_TOKEN` 和 `FRIST_API_SESSION_SECRET`。
- 生产必须保持 `FRIST_API_ALLOW_DEMO_RECHARGE=0`、`FRIST_API_EXPOSE_VERIFICATION_CODE=0`。
- 代理路径只是可选加速/稳定通道，不要把代理地址、上游 Key 或管理员令牌放到用户端。

### 当前系统状态
- 当时 `make frist-api-test` 为 45 passed, 0 failed。
- OpenClaw 后端、桌面端、内部 New API 管理页面未改动。

## [2026-05-01 16:10] Frist-API 公开试用链路交接

### 本次完成了什么
- 新增 `apps/frist-api/server/server.js` 轻量 Node 后端，用户端不再只是本地状态演示。
- 用户 HTTP 链路已跑通: 注册、邮箱验证、充值、兑换码、创建 Key、开启/关闭 Key、Dashboard、CC Switch 导入。
- 新增 `/v1/chat/completions` 中转网关，用户用 `fk-live-*` 鉴权，后端按套餐映射到日卡、月卡或默认池。
- 日卡池自动切换已落到网关层: 额度不足先跳过，上游返回余额不足时标记当前上游 Key 耗尽并重试下一枚健康 Key。
- 新增独立管理端 `apps/frist-api/admin.html` 和 `apps/frist-api/src/admin.js`，补号、价格文本和库存状态只在管理端出现。

### 未完成的工作
- 轻量后端仍用 JSON 文件保存用户、会话、用户 Key、上游 Key 和事件，正式运营前要迁移到 SQLite/PostgreSQL 或 New-API fork 数据库。
- 还没有正式登录、找回密码、SMTP、Turnstile、管理员 2FA、支付回调、订单审计和限流。
- 当前 Node 后端适合小规模公开试用，不是最终 New-API AGPL 合规 fork。

### 需要注意的坑
- `data/frist-api/runtime/runtime.json` 会包含用户 Key 和上游 Key，必须保持未跟踪，不能提交。
- 管理端开发默认令牌不能用于公开生产，公开部署前必须换成强随机值并接正式登录。

### 当前系统状态
- 当时 `make frist-api-test` 为 31 passed, 0 failed。
- OpenClaw 后端、桌面端、内部 New API 管理页面未改动。
