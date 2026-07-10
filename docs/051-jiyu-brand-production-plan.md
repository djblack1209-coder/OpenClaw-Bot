# CC中转品牌收口与生产内测执行方案

> 最后更新: 2026-07-04
> 领域: frontend / backend / deploy / security / xianyu
> 继承关系: 兑换码状态机、渠道倍率、闲鱼履约接口设计直接复用 `docs/050-frist-api-86game-clone-commerce-plan.md`，本文件只补品牌、域名、生产加固和分期上线。

## 一句话目标

把原 Frist-API 对外壳收口为 **CC中转**：用户看到统一品牌、原创紫色视觉、生产环境内测说明、兑换码核销闭环、清晰售后条款和生产安全门槛；内部接口和历史 `FRIST_API_*` 配置名保留，避免破坏现有运行链路。

## 本轮已落地边界

- 品牌名: `CC中转`。
- 当前正式域名: `jiyu.245334.xyz`（复用现有 `245334.xyz` Cloudflare Business 区域）；后续若老板单独购买 `jiyu.gg` / `jiyu.cc`，只需按同一套流程把主域名替换过去。
- 主色: `#7F77DD`，辅助紫色和浅色商业后台。
- 兑换码默认前缀: `CC`；历史 `JIYU-*` 卡密仅作为兼容别名保留，避免旧测试/已发卡密失效。
- 产品文案边界: 不写“官方合作”“官方授权”“平台直营”，也不在用户可见文案里使用“第三方”字样；统一表述为“非厂商官方渠道”“依赖外部上游资源”，模型价格统一显示为“参考标价”。
- 合规入口: 首页 / 页脚 / 兑换页可直达服务说明、服务条款、售后规则、隐私说明。

## Phase 0：品牌地基

### 仓库内完成

- 前端标题、登录页、工作台、管理页、CC Switch 导入名、邮件模板均切到 CC中转。
- `apps/frist-api/favicon.svg` 已替换为原创 CC中转图形标。
- `apps/frist-api/assets/` 已新增 Logo、闲鱼头像、闲鱼横幅 SVG。
- `apps/frist-api/deploy/production.env.example` 和 `deploy/nginx.conf` 已改为 `jiyu.245334.xyz` 模板。

### 生产账号动作

- 已在 Cloudflare `245334.xyz` 区域创建 `jiyu.245334.xyz` proxied A 记录，指向 Oracle ARM `150.136.73.15`。
- 已在 Oracle 源站安装 Cloudflare Origin CA 证书，覆盖 `jiyu.245334.xyz`、`frist-api.245334.xyz`、`frist-api-oracle.245334.xyz`。
- 旧 `frist-api.245334.xyz` 保留为跳转/回滚别名，对外投放统一使用 `https://jiyu.245334.xyz/`。

## Phase 1：生产环境内测闭环

### 已完成

- 管理端可生成 `unused → sold → redeemed → disabled` 状态卡密。
- 新生成卡密只在创建响应和导出文本里出现明文，落库改为 `codeHash + codeCipher + codePreview`，避免新卡密明文长期存储。
- 闲鱼履约按订单分配未售出卡密，发货话术按需解密生成，运行数据不再长期保存完整卡密话术。
- 兑换接口新增 IP + 登录账号双维度限流，防止暴力猜码。
- 用户端兑换成功后自动到账，后台履约记录会随兑换更新为 `redeemed`。

### 当前人工边界

- 闲鱼真实订单检测仍不自动接入；当前是人工确认订单后在后台一键分配卡密。
- 自动支付仍是未来备用能力，本阶段主路径是内测卡密人工发放 + CC中转站内兑换；暂未正式售卖。

## Phase 2：生产加固清单

### 已完成到生产强制模式

- Cloudflare Turnstile 已接入登录、注册、兑换三个高危入口；公网无 token 请求会被拒绝。
- 管理员 TOTP 2FA 已在 Oracle 生产启用，secret 仅保存在 root-only 环境文件/安全文件。
- `FRIST_API_PUBLIC_MODE=1`、`FRIST_API_ENFORCE_PRODUCTION_READINESS=1`、`FRIST_API_ALLOW_INSECURE_PUBLIC_HTTP=0` 已启用。
- R2 备份已手动触发并完成恢复演练：`frist-api-20260705T000508Z.tar.gz` 解包后 `runtime.json` 可读，`one-api.db` 完整性检查为 `ok`。
- `/api/admin/production-readiness` 已返回 `ready=true`，固定品牌域名、New-API 数据库、备份监控、管理员 2FA、Turnstile、兑换码内测核销闭环、渠道 SLA 七项通过。
- 历史 runtime 旧加密字段已做兼容隔离：旧 key 不可恢复时标记“需重新生成”，不让整站 500。

### 继续保持

- 监控告警持续覆盖服务存活、上游可用性、异常兑换频率和低库存。
- 上游不可用时，前端继续使用小白可读错误提示，不暴露内部技术细节。

## 验收命令

```bash
cd apps/frist-api
node --check server/server.js src/app.js src/admin.js src/core.js src/businessFlow.js server/shared.js server/catalog.js server/email.js
node --test tests/*.test.mjs   # 最新生产闭环回归: 172 passed / 0 failed
git diff --check
```

## 关联文件

- `apps/frist-api/index.html` — CC中转用户端品牌、合规页面、页脚入口。
- `apps/frist-api/admin.html` — CC中转管理端品牌、默认卡密前缀。
- `apps/frist-api/src/styles.css` — CC中转紫色视觉系统和合规页样式。
- `apps/frist-api/server/server.js` — `CC` 卡密、安全存储、兑换限流、`jiyu.245334.xyz` 生产默认域名。
- `apps/frist-api/server/email.js` — CC中转邮件品牌。
- `apps/frist-api/assets/` — Logo、闲鱼头像、闲鱼横幅。
- `docs/050-frist-api-86game-clone-commerce-plan.md` — 兑换码/渠道倍率/闲鱼履约原始设计，不重复设计。


## 2026-07-04 生产闭环验收结果

- 线上入口: `https://jiyu.245334.xyz/` HTTP 200。
- 旧入口: `https://frist-api.245334.xyz/` 最终跳转到 CC中转主站。
- 未授权模型接口: `/v1/models` HTTP 401。
- Turnstile: 不带 token 的注册、登录、兑换均 HTTP 400，提示“请先完成人机验证”。
- 生产 readiness: `ready=true`，备份登记时间 `2026-07-05T00:05:09.000Z`，SLA 探测事件 `21` 条。
- 服务状态: `frist-api.service`、`openclaw-newapi.service`、`apache2.service`、`frist-api-r2-backup.timer` 均 active，`systemctl --failed` 为 0。
- 截图证据: `output/playwright/jiyu-production-home-20260704.png`。
