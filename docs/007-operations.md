# 运维操作手册

> 合并自原 024-frist-api-operator-runbook.md + 025-frist-api-quickstart.md + 026-xianyu-cookie-guide.md + 029-deployment-checklist.md

---

## 一、Frist-API 运营操作清单

# Frist-API 运营操作清单

> 日期: 2026-05-03
> 范围: 管理员首登、人工入账、支付接口、固定域名、邮箱和验证码

## 当前可运营边界

Frist-API 现在不是只会展示页面的 MVP，已经能跑小范围真实验收: 用户注册登录、闲鱼/平台购买兑换码、用户兑换自动到账、管理员批量生成卡密、创建用户 Key、导出 Codex/OpenCode/Claude/OpenClaw/Hermes 配置，并通过 `/v1` 网关转发请求。

但正式商业化投放前还有外部依赖必须由你开通。没有这些依赖时，主路径按“第三方平台售卖兑换码 + Frist-API 核销”运营，不能对外宣称官方商户自动支付、正式域名或完整生产化。

| 模块 | 当前状态 | 生产要求 |
|------|------|------|
| 访问入口 | 唯一公网入口收口到 `frist-api.101-43-41-96.nip.io`；裸域名只做 301 跳转，HTTPS 仍需自有域名或 Tunnel | 固定品牌域名 + HTTPS |
| 充值 | 主路径改为管理端生成兑换码、闲鱼等平台售卖、用户端核销自动到账；商户支付代码保留为未来备用 | 平台售卖链接、自动发货规则、兑换码对账和库存告警 |
| 价格 | 管理端可直接编辑套餐和模型价格 JSON | 接支付回调后增加价格版本审计和生效审批 |
| 邮箱 | 已支持余额预警、注册验证码和找回密码 SMTP 邮件 | 企业邮箱或稳定邮件服务商 + 发信监控 |
| 防刷 | 轻量验证码 + 登录限流 | Cloudflare Turnstile + Redis 限流 |
| 数据 | JSON 运行数据文件，用户 Key 和上游 rawKey 已做字段加密 | SQLite WAL 或 PostgreSQL + 备份 |
| 管理员 | 一次性身份码 + 管理登录态 | 管理员 2FA + 审计 |
| 模型列表 | 上游探测 + 内置兜底 | 上游 `/v1/models` + 官方目录校验 + 后台排序 |
| 上游来源 | 授权供应商余额站/自有额度为主；CPA JSON、chong 只作为人工审核备用渠道登记 | 禁止把批量 OAuth Session、来路不明 JSON 号源或规避风控的账号池默认当作生产库存 |

## 腾讯云部署摘要

Frist-API 在共享腾讯云服务器上按“小服务独立端口 + 反向代理”的方式运行，避免抢占其他项目的 80/443 默认站点。

| 项目 | 当前约定 |
|------|------|
| 运行目录 | `/opt/frist-api` |
| 容器 | `frist-api-server` |
| 本地服务 | `http://127.0.0.1:3180` |
| 公网入口 | `frist-api.101-43-41-96.nip.io` 反代到 `127.0.0.1:3180`；`101-43-41-96.nip.io` 不直接服务页面 |
| HTTPS 测试入口 | Cloudflare Quick Tunnel |
| 运行数据 | `data/frist-api/runtime/runtime.json`，含用户 Key 和上游 Key，禁止提交 Git |
| 环境变量 | 只放服务器本机环境文件，禁止写入仓库 |

上线或重启后按下面顺序验收:

1. `docker ps` 确认 `frist-api-server` 为 `healthy`。
2. `curl -sS http://127.0.0.1:3180/` 确认容器本地入口可用。
3. 检查 Nginx 或 Tunnel 是否只把 Frist-API 页面公开到品牌域名，裸域名必须 301 到品牌域名。
4. 普通 `/admin.html` 应返回 404；只有登录账号完成一次性管理员身份码激活后才显示运营入口。
5. 跑 `apps/frist-api/deploy/smoke-test.sh http://127.0.0.1:3180 "$FRIST_API_ADMIN_PAGE_CODE"`，再用公网入口跑一次冒烟。

正式开放陌生付费用户前，必须补齐固定品牌域名、HTTPS、SMTP 注册验证/找回密码、Turnstile、真实支付回调、管理员 2FA、数据库备份和监控告警。Quick Tunnel 只适合外部实测，不是长期入口。

## 你需要人工开通的服务

| 优先级 | 服务 | 你要准备的字段 | 我接入后的接口 |
|------|------|------|------|
| P0 | 域名和 Cloudflare / 免费 DNS | 自有域名优先；无域名时先用 `sslip.io`/`nip.io` 指向服务器 IP | `https://你的域名/` 和 `https://你的域名/v1` |
| P0 | 支付平台 | API Key、商户号、AppID、签名密钥、公钥、回调域名 | `/api/frist/payments/wechat/notify`、`/api/frist/payments/alipay/notify` |
| P0 | 备份目标 | 对象存储 Bucket、访问密钥或独立备份机路径 | 每日备份和恢复演练脚本 |
| P1 | SMTP 邮箱 | 主机、端口、用户名、应用密码、发件邮箱 | 余额预警、注册验证、找回密码已接入 |
| P1 | Turnstile | Site Key、Secret Key、允许域名 | 注册登录真实人机校验 |
| P1 | 告警 Webhook | Telegram、企业微信、飞书或 OpenClaw 通知地址 | 低库存、5xx、支付失败、异常扣费告警 |
| P2 | 合规文档 | 服务条款、退款规则、隐私政策、AGPL 源码入口 | 页面页脚和订单确认页展示 |

不要把 API Key、Webhook Secret、商户密钥、SMTP 密码或服务器密码发到聊天里。拿到后写进服务器本机环境文件，或让我通过 SSH 在服务器上创建只读权限的生产环境文件。

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

1. 打开 Frist-API 用户端，按普通用户流程注册和登录。
2. 先完成一次用户链路测试: 创建 Key、选择模型分组、生成 CC Switch 导入链接。
3. 回到右上角账户菜单，在身份码输入框粘贴一次性管理员身份码。
4. 点击激活。成功后当前账号变成管理员，身份码立即作废。
5. 账户菜单会显示运营入口。点击后进入独立管理页，同一浏览器登录态可直接加载库存和充值单。
6. 管理页里的管理员令牌输入框是后备方式，正常可以留空。

如果身份码输错，页面会提示身份码无效；如果已经使用过，会提示身份码已失效。需要新码时，只在服务器环境变量 `FRIST_API_ADMIN_CLAIM_CODES` 追加新的一次性码，然后重启 Frist-API 容器。

## 今晚可用的收款方式

当前最稳的公开测试方式是第三方平台售卖兑换码 + 用户端自动核销。

1. 管理员进入运营入口，在“卡密生成与闲鱼发货”里选择套餐和数量，生成一次性兑换码。
2. 复制本批卡密清单，导入闲鱼自动发货或客服系统。
3. 用户在闲鱼等平台下单，平台完成收款、售后和自动发货。
4. 用户回到 Frist-API 的兑换码页面输入卡密。
5. 系统校验卡密未使用后立即到账，并把卡密标记为已兑换。

这种方式不需要商户支付资质，也不需要用户上传付款截图，适合个人阶段把交易放到有保障的平台上完成。

人工入账只作为异常兜底。正常订单以兑换码核销记录为准，至少保留: 卡密批次、闲鱼订单号、卡密、套餐、售出平台、核销用户和核销时间。

### 闲鱼兑换码售卖

推荐把每个套餐作为一个闲鱼商品或 SKU，自动发货内容只放一条兑换码。

1. 在管理端生成本批卡密，复制 `卡密 + 套餐 + 额度 + 时限` 文本。
2. 将卡密导入闲鱼自动发货库或 OpenClaw 闲鱼客服系统。
3. 用户下单后收到卡密，回 Frist-API `#redeem` 页面兑换。
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

## 自动支付需要你人工准备的东西

国内自动支付建议按这个顺序推进:

1. 短期: 个人收款二维码 + 充值单 + 人工确认入账，先完成真实用户验收。
2. 中期: 开通支付宝当面付 或 微信支付 Native，打通扫码支付、异步通知、验签和自动入账。
3. 备选: 国内聚合支付或 Stripe。聚合支付上线快但签名规则差异大；Stripe 适合海外卡和订阅。

不论选哪种自动支付，都需要你人工准备这些字段: 主体实名、商户号、应用 AppID、API Key、签名密钥、回调域名、异步通知 URL、同步跳转 URL、订单号规则、金额单位和退款规则。不要把密钥发到聊天里，写入服务器环境文件后再让我接代码。

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

当前代码已接入: `alipay.trade.precreate` 下单、`RSA2` 异步通知验签、`TRADE_SUCCESS` / `TRADE_FINISHED` 幂等入账。商户未开户注册前，页面会提示接口未配置，不会伪造自动支付成功。

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
5. 设置 `APIv3 密钥`，下载商户证书和商户私钥。
6. 配置异步通知地址，建议预留为 `https://你的域名/api/frist/payments/wechat/notify`。
7. 确认微信回调是加密资源，需要用 APIv3 密钥解密；订单金额单位是分，不是元。
8. 把证书、私钥和 APIv3 密钥放到服务器安全路径，例如 `/opt/frist-api/secrets/wechat/`，权限设为只有 root 可读。
9. 在 `/opt/frist-api/.env.production` 写入商户号、AppID、证书序列号、证书路径、私钥路径、APIv3 密钥和回调地址。
10. 重启 Frist-API 后，用 0.01 元订单测试: 下单生成 Native 二维码、微信扫码付款、收到回调、用户自动入账、重复回调不会重复加钱。

当前代码已接入: 微信支付 Native 下单、APIv3 回调验签、AES-256-GCM 资源解密、`SUCCESS` 幂等入账。商户未开户注册前，页面会提示接口未配置，不会伪造自动支付成功。

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

第一版自动支付只接一个成功事件和一个失败事件就够了，先保证付款后能自动入账、重复回调不会重复加钱、订单金额和用户选择套餐一致。退款、优惠券和订阅续费放到第二阶段。

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

当前 Quick Tunnel 适合今晚测试，不适合长期品牌入口。长期方案建议用 Cloudflare 的命名 Tunnel 或 DNS 路由到服务器。

无自有域名时的免费方案: 先用 `nip.io` 这种 wildcard DNS。它会把主机名里的 IP 自动解析到服务器，例如 `frist-api.101-43-41-96.nip.io` 会解析到 `101.43.41.96`。2026-05-04 公网实测中，`sslip.io` 在腾讯 DNSPod 侧被拦截到封禁页，当前可用免费入口切到 `frist-api.101-43-41-96.nip.io`。`101-43-41-96.nip.io` 只作为兼容跳转入口，不直接服务页面。这不是正式品牌域名，只是带 Frist-API 前缀的免费固定 HTTP 过渡入口。

免费域名部署步骤:

1. 在服务器检查 80/443 是否已被其他项目占用，避免影响共享项目。
2. 新增 Nginx server block: `server_name frist-api.101-43-41-96.nip.io` 反代到 `http://127.0.0.1:3180`；`server_name 101-43-41-96.nip.io` 只返回 301 到品牌域名。
3. 使用 certbot 给 `frist-api.101-43-41-96.nip.io` 申请证书；本轮证书机构访问 80 端口 ACME challenge 返回 connection reset，免费域名 HTTPS 未签发成功。
4. 当前 HTTP 过渡入口将服务器环境变量设为 `FRIST_API_PUBLIC_GATEWAY_BASE_URL=http://frist-api.101-43-41-96.nip.io/v1`、`FRIST_API_CANONICAL_HOST=frist-api.101-43-41-96.nip.io`、`FRIST_API_REDIRECT_HOSTS=101-43-41-96.nip.io`，并保留 `FRIST_API_ALLOW_INSECURE_PUBLIC_HTTP=1`；拿到 HTTPS 后再改为 `https://你的域名/v1`。
5. 重启容器后跑首页、看板、`/v1/models` 未授权 401、管理员入口隐藏和支付回调 URL 冒烟。

免费域名只适合过渡。正式投放建议仍购买自有域名，便于品牌识别、支付审核、风控和客服。

你需要人工完成:

1. 购买或准备域名，例如 `api.yourdomain.com`。
2. 把域名接入 Cloudflare。
3. 在 Cloudflare 后台进入 Tunnel，给 Frist-API 增加公开主机名。
4. 主机名指向服务器本地服务 `http://127.0.0.1:3180`。
5. 生效后把服务器 `FRIST_API_PUBLIC_GATEWAY_BASE_URL` 改成 `https://你的域名/v1`。
6. 重启容器并跑冒烟检查。

Cloudflare 官方文档说明，Tunnel 会把 Cloudflare 网络流量转到运行 `cloudflared` 的源站服务；在 Dashboard 添加路由时，会自动创建指向 Tunnel 子域的 DNS 记录。

参考官方文档:

- Cloudflare Tunnel: https://developers.cloudflare.com/tunnel/
- Cloudflare Tunnel Routing: https://developers.cloudflare.com/tunnel/routing/

域名切换后需要同步修改服务器环境变量 `FRIST_API_PUBLIC_GATEWAY_BASE_URL=https://你的域名/v1`。否则用户导出的 Codex/OpenCode 配置仍可能指向旧测试入口。

## 邮箱和防刷

当前已有轻量验证码和登录频率限制，余额预警、注册验证和找回密码邮件都可以走 SMTP；正式开放陌生用户还需要继续接 Turnstile 和更稳定的外部限流存储。

你需要人工准备:

- SMTP 主机、端口、用户名、应用专用密码、发件邮箱。余额预警、注册验证码和找回密码共用 `FRIST_API_SMTP_HOST`、`FRIST_API_SMTP_PORT`、`FRIST_API_SMTP_SECURE`、`FRIST_API_SMTP_FAMILY`、`FRIST_API_SMTP_USER`、`FRIST_API_SMTP_PASSWORD`、`FRIST_API_SMTP_FROM` 和 `FRIST_API_BALANCE_ALERT_FROM_NAME`。
- Cloudflare Turnstile Site Key 和 Secret Key。
- 一个客服邮箱，用于账单、找回密码和异常申诉。

建议先用企业邮箱或域名邮箱，不建议用个人邮箱长期发验证码。Gmail 这类个人邮箱只能作为短期测试，应用专用密码只允许写入服务器环境变量，不能写入仓库、文档或运行数据。拿到字段后写入服务器环境文件，再继续接 Turnstile 校验。

余额预警测试方式:

1. 用户登录 Frist-API，进入 `账单`。
2. 在 `余额预警` 卡片里打开开关，填写阈值和收件邮箱。
3. 点击 `发送测试邮件`。成功说明 SMTP 可以发信；失败时页面会显示 SMTP 未配置或连接异常。
4. 真实扣费后，系统只在余额从阈值上方跌到阈值以下时发送一次，避免每次调用都刷邮件。

如果本机或云厂商出口限制 SMTP，可能出现 465/587 端口 TCP 可连但 TLS 或 SMTP greeting 阶段无响应。遇到这种情况，不要反复换代码，先在正式服务器网络上跑测试邮件，再决定是否改用企业邮箱、邮件服务商或放行 SMTP 出口。腾讯云实测中 Gmail IPv6 出口可用、IPv4 465 超时，因此默认 `FRIST_API_SMTP_FAMILY=auto` 会按 DNS 地址逐个尝试；如某台服务器 IPv4 长期超时，可临时设为 `6`。

Turnstile 接入后，前端只保存 Site Key，Secret Key 只能放在服务器。服务端必须校验 Cloudflare 返回结果，不能只检查前端传了一个 token。

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

- `playwright`: 通过 `@playwright/mcp@latest` 给 Codex 增加浏览器自动化能力。
- `superpowers`: 通过 `superpowers-mcp@latest` 增加 TDD、调试、协作类工作流提示。
- `open_computer_use`: 通过 `open-computer-use@latest` 启动 `open-codex-computer-use-mcp`，给支持的 Codex 环境准备电脑操作入口。

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

- HTTP 过渡用户端: `http://frist-api.101-43-41-96.nip.io/`
- HTTP 过渡 API 网关: `http://frist-api.101-43-41-96.nip.io/v1`
- 裸域名 `http://101-43-41-96.nip.io/` 只做 301 跳转，不直接服务页面。

当前固定品牌域名和 HTTPS 证书仍未闭环；进生产时建议绑定自有域名到 Cloudflare Tunnel 或 DNS，再把 `FRIST_API_PUBLIC_GATEWAY_BASE_URL` 切到固定 HTTPS 域名。

管理端不公开展示。普通 `/admin.html` 在公网会返回 404。日常用法是先注册/登录自己的用户账号，在右上角账户区域输入一次性管理员身份码，当前账号会升级为管理员，身份码随即作废；升级后账户区域会出现运营入口，管理 API 也会直接识别当前登录态。隐藏入口码和管理员令牌仍保留为服务器后备方案，不给普通用户展示。

人工收款、固定域名、SMTP、Turnstile 和正式支付接口的操作清单见本文件上方的 Frist-API 运营操作清单。

无域名阶段这是临时 HTTP 验收地址。正式开放陌生付费用户前，必须绑定域名、HTTPS、SMTP 注册验证/找回密码、Turnstile、真实支付回调、管理员 2FA 和数据库备份。

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
- 用户端不展示补号助手、上游号商、价格解析、渠道、倍率、模型映射和库存。运营入口只会在当前账号完成一次性管理员身份码激活后出现。

## 管理端能做什么

管理端独立在隐藏入口后。推荐方式是用一次性管理员身份码把你的账号升级为管理员，然后通过账户区域的运营入口进入；管理员令牌只作为后备方式保留在服务器环境变量里，不写入仓库和公开文档。

- 人工入账: 按用户邮箱确认日卡、月卡或余额充值。
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

管理端不会把原始上游 Key、管理员令牌或号商细节带到用户端。

## 业务链路

用户链路:

1. 用户打开 Frist-API，右上角注册或登录，并完成轻量验证码挑战。
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

当前回归覆盖 104 条，包括:

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
docker compose -f docker-compose.frist-api.yml up -d
```

当前 Docker 原型使用 `node:22-alpine` 跑轻量 Frist-API 后端，内存限制 256MB，适配 2 核 2GB 的小服务器。运行数据默认写入 `data/frist-api/runtime/runtime.json`，该文件可能包含用户 Key 和上游 Key，不能提交到 Git。

生产环境必须设置:

- `FRIST_API_ADMIN_TOKEN`: 强随机管理员令牌
- `FRIST_API_ADMIN_PAGE_CODE`: 隐藏管理入口码
- `FRIST_API_ADMIN_CLAIM_CODES`: 一次性管理员身份码，逗号分隔；每个码成功使用后自动失效
- `FRIST_API_SESSION_SECRET`: 强随机会话密钥
- `FRIST_API_PASSWORD_HASH_SECRET`: 强随机密码哈希密钥；不要和会话密钥共用。轮换 `FRIST_API_SESSION_SECRET` 时旧账号密码仍可用。
- `FRIST_API_LEGACY_PASSWORD_HASH_SECRETS`: 历史密码哈希密钥列表。上线修复旧环境时先填旧 `FRIST_API_SESSION_SECRET`，用户登录成功后会迁移到新 `FRIST_API_PASSWORD_HASH_SECRET`。
- `FRIST_API_PUBLIC_MODE=1`
- `NODE_ENV=production`
- `FRIST_API_ENFORCE_PRODUCTION_READINESS=1`: 正式开放陌生付费用户时打开；缺固定 HTTPS 品牌域名、New-API 数据库、管理员 2FA 或真实支付商户会直接启动失败
- `FRIST_API_ALLOW_DEMO_RECHARGE=0`
- `FRIST_API_EXPOSE_VERIFICATION_CODE=0`
- `FRIST_API_REQUIRE_CSRF=1`
- `FRIST_API_REQUIRE_ADMIN_2FA=1`
- `FRIST_API_ADMIN_TOTP_SECRETS`: 管理员 TOTP Base32 Secret，多个用逗号分隔，只放服务器环境变量
- `FRIST_API_REQUIRE_CAPTCHA=1`，仅用于注册挑战；登录不再要求验证码
- `FRIST_API_CAPTCHA_MAX_ATTEMPTS=3`
- `FRIST_API_AUTH_RATE_LIMIT_MAX=20`
- `FRIST_API_BACKUP_STATUS_MAX_AGE_HOURS=26`: 备份超过 26 小时未登记则生产检查不通过
- `FRIST_API_SLA_RETENTION_DAYS=30`: 渠道 SLA 探测事件保留 30 天
- `FRIST_API_LOW_INVENTORY_WEBHOOK`: 可选，低库存通知 Webhook
- `FRIST_API_SMTP_HOST` / `FRIST_API_SMTP_PORT` / `FRIST_API_SMTP_SECURE` / `FRIST_API_SMTP_FAMILY`: 可选，余额预警邮件 SMTP 连接配置
- `FRIST_API_SMTP_USER` / `FRIST_API_SMTP_PASSWORD` / `FRIST_API_SMTP_FROM`: 可选，余额预警邮件登录和发件配置
- `FRIST_API_BALANCE_ALERT_FROM_NAME`: 可选，余额预警邮件发件人名称
- `FRIST_API_NEWAPI_ENABLED`: 生产设为 `1`，Frist-API 服务端通过 New-API 接管用户看板、API Key、日志、订阅、兑换和邀请数据
- `FRIST_API_REQUIRE_NEWAPI_DATABASE=1`: 生产硬门槛，防止继续把 JSON runtime 当数据库使用
- `FRIST_API_NEWAPI_BASE_URL` / `FRIST_API_NEWAPI_ACCESS_TOKEN` / `FRIST_API_NEWAPI_USER_ID`: 可选，New-API 内网地址、用户 access token 和对应用户 ID，只能放服务器环境变量
- `FRIST_API_NEWAPI_GATEWAY_ENABLED` / `FRIST_API_NEWAPI_GATEWAY_BASE_URL`: 可选，设为 `1` 后 `/v1` 网关请求直接代理 New-API；默认关闭，继续保留 Frist-API 自研路由兜底

无域名公网 IP 验收时可临时设置 `FRIST_API_ALLOW_INSECURE_PUBLIC_HTTP=1`。当前 Cloudflare HTTPS 入口已关闭这个临时开关。

生产边界验收:

```bash
curl -fsS -H "x-admin-token: $FRIST_API_ADMIN_TOKEN" \
  https://你的域名/api/admin/production-readiness
```

备份任务完成后登记一次状态，恢复演练建议至少每月跑一次:

```bash
curl -fsS -X POST -H "x-admin-token: $FRIST_API_ADMIN_TOKEN" -H "content-type: application/json" \
  --data '{"provider":"rclone","target":"s3://frist-api-prod/runtime","lastBackupAt":"2026-05-07T11:30:00.000Z","lastRestoreTestAt":"2026-05-07T11:40:00.000Z","status":"ok","artifact":"runtime-20260507.tgz","checksum":"sha256:..."}' \
  https://你的域名/api/admin/backups/status
```

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
- 可选模型网关: `FRIST_API_NEWAPI_GATEWAY_ENABLED=1` 后代理 `/v1/chat/completions`、`/v1/responses`、`/v1/images/generations`、`/v1/messages`

仍然保留在 Frist-API 自研层的部分:

- Workbench 前端视觉、页面结构和客户动线。
- CC Switch、Codex、Claude、Gemini、OpenCode、OpenClaw、Hermes/Harmes 的导入配置生成。
- Codex + DeepSeek 官方端点 `https://api.deepseek.com/v1` 的配置生成；新导入默认 `deepseek-v4-flash`，同时保留 `deepseek-v4-pro`、`deepseek-chat`、`deepseek-reasoner` 兼容。
- 余额预警邮件、隐藏管理员身份码、补号助手、备用渠道人工风险隔离、供应商文本解析和本地 JSON 兜底。

启用前必须先在 New-API 里生成用户 access token，并确认 `FRIST_API_NEWAPI_USER_ID` 与该 token 所属用户一致。New-API v1 会同时校验 `Authorization` 和 `New-Api-User`，二者不一致会认证失败。

## 当前限制

- JSON runtime 仍作为兜底和本地小范围验收可用；生产强制模式要求 `FRIST_API_NEWAPI_ENABLED=1` 和 `FRIST_API_REQUIRE_NEWAPI_DATABASE=1`，历史 JSON 数据迁移仍需单独演练。
- 已有轻量验证码、认证限流、一次性管理员身份码、管理员 TOTP 2FA、余额预警 SMTP 邮件和真实支付回调代码；商户开户注册、正式域名、正式备份任务和恢复演练需要在外部平台完成。
- 补号探测已做低成本可用性判断、Responses fallback、直连/代理择优和认证字段清洗，但未做完整上下文上限、工具调用、流式能力和模型质量评分。
- CPA JSON/chong 入口只做人工登记和放行，不包含 OAuth Session 提取、Refresh Token 刷新、账号池规避风控或自动化批量获取逻辑。
- `QuantumNous/new-api` 是 AGPL-3.0，公开二开运营时必须准备源码公开入口或公开 fork。

## New-API 上游同步 SOP

New-API 不再从旧本地目录复制代码。项目用 `packages/new-api-upstream` submodule 固定上游 release，用 `docker-compose.newapi.yml` 固定同版本 Docker 镜像，Frist-API 和 ClawBot 通过接口代理复用业务逻辑。

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

- 当前固定版本为 `v1.0.0-rc.2`，镜像为 `calciumion/new-api:v1.0.0-rc.2`。
- `make new-api-check` 发现版本落后会返回非 0；`.github/workflows/new-api-sync.yml` 已每天自动检查并在落后时创建同步 PR。
- Docker Desktop 或服务器 Docker daemon 必须运行，才能执行镜像 pull、容器启动和健康检查。
- 本地已有 `data/newapi/new-api.db` 和 `data/newapi/one-api.db`，不要在未备份时直接启动新版容器，避免自动迁移后无法回退。
- New-API v1 后台/用户接口需要 `Authorization` 和 `New-Api-User` 一致；ClawBot 代理环境变量为 `NEWAPI_ADMIN_TOKEN` / `NEWAPI_ADMIN_USER_ID`，Frist-API 桥接环境变量为 `FRIST_API_NEWAPI_ACCESS_TOKEN` / `FRIST_API_NEWAPI_USER_ID`。
- 公开商业化时，AGPL-3.0 合规要求必须准备源码公开入口或公开 fork。

当前腾讯云状态:

- 共享服务器上目前只部署了 Frist-API Workbench，未发现独立 New-API 容器或 `/opt/*/data/newapi` 运行数据。
- 因此本轮 New-API “升级”是本地工程源码指针、compose 镜像和代理层升级；正式迁移到服务器前还需要数据库备份、初始化 root token、内网端口和反代策略。

## 下一步

1. 绑定真实品牌域名和 HTTPS，关闭临时公网 HTTP 开关。
2. 在微信/支付宝或 Stripe 等商户平台开户并把正式回调域名填入商户后台。
3. 把 Frist-API JSON 运行数据迁移到 New-API 数据库，优先迁移用户、余额、API Key、渠道、日志和订单。
4. 给 Frist-API UI 接 New-API 用户会话或服务端代理，避免重复维护账号、Key、计费和日志逻辑。
5. 给补号探测加并发上限、预算上限和后台队列。
6. 做价格草稿确认、版本回滚和亏损预警。
7. 准备 AGPL-3.0 合规源码公开入口。

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


## ✅ 已完成的工作

### 1. 核心文件
- ✅ `web_installer.py` - 主安装器（8步自动部署）
- ✅ `license_manager.py` - 离线License验证
- ✅ `docs/agents.md` - 三省六部架构配置
- ✅ `docs/quick-start-guide.md` - API/Telegram/飞书/钉钉教程
- ✅ `docs/product-copy.txt` - 闲鱼商品描述
- ✅ `tools/xianyu_product_image.html` - 商品图模板

### 2. 部署功能
- ✅ 安装 OpenClaw 核心（npm install -g openclaw@latest）
- ✅ 初始化 OpenClaw（openclaw onboard --install-daemon）
- ✅ 部署三省六部 AGENTS.md 到 ~/.openclaw/workspace/
- ✅ 安装5个热门 Skills（playwright/pdf/doc/vercel-deploy/cloudflare-deploy）
- ✅ 提供 Manager UI 下载链接（.dmg/.exe/.AppImage）
- ✅ 配置 MCP 服务（Context7 + GitHub Grep）
- ✅ 配置 AI 模型（DeepSeek/硅基流动/OpenRouter/Ollama/自定义）

### 3. 安全功能
- ✅ 离线 License 验证（HMAC签名 + 过期时间）
- ✅ 退款自动销毁（`python web_installer.py --destroy`）

### 4. 打包文件
- ✅ 打包脚本：`tools/package.sh`
- ✅ 压缩包：`dist/OpenClaw-Installer-v4.0.zip`
- ✅ 启动脚本：`启动安装器.command` / `启动安装器.bat`
- ✅ 销毁脚本：`退款销毁.command` / `退款销毁.bat`
- ✅ README.txt 使用说明

## 📦 打包内容

```
OpenClaw-Installer-v4.0.zip
├── web_installer.py          # 主安装器
├── license_manager.py         # License管理
├── 启动安装器.command          # Mac启动脚本
├── 启动安装器.bat             # Windows启动脚本
├── 退款销毁.command           # Mac销毁脚本
├── 退款销毁.bat              # Windows销毁脚本
├── README.txt                # 使用说明
└── docs/
    ├── agents.md             # 三省六部配置
    ├── quick-start-guide.md  # 免费模型教程
    └── product-copy.txt      # 闲鱼文案
```

## 🧪 测试激活码

```
OC-5E08E78A-6B9831D5-1447136E
```
有效期：365天

## 📤 下一步操作

### 1. 上传百度网盘
```bash
# 文件位置
/Users/blackdj/Desktop/OpenClaw Bot/packages/clawbot/dist/OpenClaw-Installer-v4.0.zip

# 上传后获取分享链接，格式如：
https://pan.baidu.com/s/xxxxx
提取码: xxxx
```

### 2. 更新配置文件
编辑 `config/.env`：
```env
BAIDU_PAN_LINK=https://pan.baidu.com/s/xxxxx
BAIDU_PAN_CODE=xxxx
```

### 3. 生成商品图
```bash
# 在浏览器打开
open tools/xianyu_product_image.html

# 截图保存为 750x1000 PNG
```

### 4. 发布到闲鱼
- 标题：🦞 OpenClaw龙虾AI助手一键部署 GitHub315k⭐ 三省六部架构 小白可用
- 价格：¥19.9
- 描述：复制 `docs/product-copy.txt` 内容
- 图片：上传商品图截图

## 🔑 License 生成

卖家端生成激活码：
```python
from src.deployer.license_manager import generate_offline_key

# 生成1年期激活码
key = generate_offline_key(days=365)
print(key)  # OC-XXXXXXXX-XXXXXXXX-XXXXXXXX
```

## 🛠️ 故障排查

### 问题1：Node.js版本过低
解决：引导买家安装 Node.js >= 22
https://nodejs.org/

### 问题2：npm安装失败
解决：检查网络，或使用国内镜像
```bash
npm config set registry https://registry.npmmirror.com
```

### 问题3：Skills安装失败
解决：可跳过，不影响核心功能

### 问题4：激活码无效
解决：检查是否复制完整，是否过期

## 📊 成本分析

- 开发成本：0元（开源项目）
- 服务器成本：0元（离线验证）
- 模型成本：0元（买家自己注册）
- 售后成本：极低（自动化部署）

定价建议：¥19.9 - ¥29.9

## 🎯 核心卖点

1. **GitHub 315k⭐ 官方项目** - 不是山寨
2. **三省六部架构（9.6k⭐）** - 智能决策系统
3. **一键部署** - 双击启动，浏览器操作
4. **免费模型教程** - 不骗人说"免费模型"
5. **完整生态** - Manager UI + Skills + MCP
6. **小白友好** - 详细教程 + 7天售后

## ⚠️ 注意事项

1. 不要宣传"免费模型"，只说"免费模型获取教程"
2. 明确说明需要自己注册API
3. 退款后激活码自动失效并删除已部署内容
4. 提供7天售后支持
