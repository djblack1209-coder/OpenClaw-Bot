# JIYU AI 生产运维

> 更新时间：2026-08-11。本文是可重复操作入口；生产结论只写入 `docs/current/current-baseline.md`。

## 运行合同

每次生产写入必须具备最新 prestate、可恢复备份、单一最小变更、失败回滚和真实业务回读。禁止输出或记录密码、Token、Cookie、私钥、对象存储凭据、订阅地址和账户标识。

MFA、账户恢复、所有权转移、新增费用、支付平台开户、不可逆凭据删除和硬件采购由资产所有者处理。不要新增 Gate、证据编译器、一次性测试包、第二监控面或常驻 AI 管理面。

## 当前拓扑

| 层 | 当前实现 |
|----|----------|
| 公网 | Cloudflare 代理现有 JIYU 域名 |
| 源站 | Apache 80/443，只把业务流量送入 loopback |
| 网关 | `sub2api.service`，`127.0.0.1:18080` |
| 数据 | PostgreSQL 是账户、余额、订单、密钥和账本唯一事实源 |
| 任务 | 专用 Redis 只监听 loopback |
| 备份/图片 | JIYU 私有 R2 的独立前缀 |
| 更新 | `sub2api-update.timer` 只检查兼容版本，不裸装官方二进制 |
| 备份 | `sub2api-backup.timer` 每日生成 PostgreSQL 一致性备份 |

中国生产面暂停；中国 origin 不承载账户或账本副本。支付设置保留但未启用。

## 日常只读检查

```bash
ssh oracle-arm1 '/usr/local/sbin/openclaw-sub2api-manager status'
ssh oracle-arm1 '/usr/local/sbin/openclaw-sub2api-manager check'
ssh oracle-arm1 'systemctl list-timers sub2api-update.timer sub2api-backup.timer --no-pager'
```

真实回读至少包括：

- 本地与公网 `/health` 返回 200。
- 未授权 `/v1/models` 返回 401。
- Sub2API、PostgreSQL、Redis 和 Apache 运行。
- PostgreSQL、Redis、Sub2API 不监听公网地址。
- 备份定时器 active，最近归档校验可恢复。
- 不用 `/v1/usage` 或模型请求充当健康探针。

## 生产写入模板

1. 读取服务状态、配置哈希、数据库计数和公网结果。
2. 使用现有管理器创建一致性备份，校验 checksum 与恢复语义。
3. 只改一个明确对象；暂存文件和最终文件必须在同一文件系统原子替换。
4. 任一检查失败立即恢复 prestate。
5. 回读本地健康、401 边界、公网健康和本次业务对象。
6. 只把脱敏结论写入当前基线和变更日志。

## Sub2API 管理器

保留的主要命令：

```text
status / check / check-upstream / backup
install-jiyu-build / stage-jiyu-build / verify-jiyu-stage
brand / brand-asset / recharge-center / docs-page / terms-page
region-headers / region-enforcement / cn-production
upstream-allowlist / harden-apache / postgres-preflight
cloudflare-origin-443 / confirm-cloudflare-origin-443 / rollback-cloudflare-origin-443
responses-websocket / openai-ws-http-bridge / openai-ws-legacy
```

WebUI 更新只进入受限 root 代理和不可变 JIYU 兼容构建。相同构建不得重复安装；暂存后未在窗口内完成健康确认会自动撤销。

## 数据备份与 R2

Sub2API 原生备份和异步图片对象使用 JIYU 专用私有 R2，不复用其他项目 bucket 或前缀。数据库备份已验证下载、checksum、解压 SQL 和临时 PostgreSQL 恢复；图片前缀当前没有成功上游产物。

对象存储保持私有，凭据只存在服务器受保护配置中。生命周期分别覆盖备份、图片和未完成分片；不要为了验证制造周期性生图或付费负载。

## 异步生图

支持原生异步图片 API 的客户端直接提交任务并按任务 ID 轮询。Sub2API、Redis 和 R2 负责任务状态与结果对象；普通文本客户端不会经 CC Switch 隐式转换成图片请求，中央 MCP 不再恢复。

只有上游权限和模型恢复后才做一次最低成本真实单图验收，检查成功状态、MIME、对象大小、访问期限与清理策略。

## 支付与邮件

- 支付开关保持关闭，现阶段不填写商户回调、私钥或二维码。
- 启用支付必须具备合法主体、当前官方产品权限、签名验签、订单幂等、退款流程和一次真实小额回读。
- 邮件只使用服务器受保护配置；注册验证、找回密码和余额通知共用原生模板与限流。
- Passkey、管理员 2FA、登录条款和地区限制优先使用 Sub2API 原生设置，不创建第二套认证后台。

## Mac 运维

```bash
bash scripts/auto_health_check.sh --json --strict
openclaw health --json --timeout 5000
openclaw status --json --timeout 5000
make backup-run
make backup-restore-drill
make tauri-build
```

Gateway 与 ClawBot Agent 是核心服务；G4F、Kiro 和 IBKR 按实际配置显示 enabled/disabled。App 的“智能体”页是唯一写控制面。

## 已退役运行面

2026-08-11 已在用户确认商品全部下架且无待处理订单后完成：

- 停用并删除本机闲鱼客服、卖家桥、18800 控制台与专属扩展能力。
- 删除 Oracle Frist-API 服务与每日备份定时器，关闭 3180。
- 旧 Frist 公网别名 301 到 JIYU 主站，不再反代旧服务。
- `frist_xianyu` 数据库角色禁止登录；空预留表和迁移保留用于恢复。
- Frist 运行目录、环境、unit、Apache prestate 和数据库表保存在校验通过的 root-only 回滚包中。
- Sub2API 管理器不再提供 Frist/闲鱼履约重新部署命令。

不得从 Git 历史、旧文档或回滚包主动恢复这些能力。只有明确的真实数据恢复事件才允许读取回滚包。

## 故障处理

- 公网异常：先比对本地 `/health`、Apache、Cloudflare 代理与源站 443，不改 DNS 猜测修复。
- 数据库异常：先运行 `postgres-preflight` 和只读检查，不直接修改账本。
- 更新异常：使用该次发布的备份和管理器自动回滚，不装裸上游二进制。
- Mac App 异常：使用签名上一版回滚，不恢复已退役页面或服务。
- 本地检查失败不阻塞生产只读诊断，但任何生产写入仍必须满足完整事务合同。
