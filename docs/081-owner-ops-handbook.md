# 日常运营手册

> 面向站点所有者。这里不要求记服务器路径、端口或脚本内部结构。

## 日常只用三个入口

1. **OpenClaw App**：看本机状态、Bot、社媒、资讯、投资和服务开关。
2. **JIYU WebUI**：处理用户、API 密钥、余额、渠道、模型、邮件和系统设置。
3. **当前基线**：`docs/current/current-baseline.md`，确认什么已验证、什么仍被阻塞。

闲鱼、Frist-API 和中央生图 MCP 已退役，不再有第四个运营台。

## 每日检查

- App 首页没有红色核心故障。
- “智能体”页中 Gateway 与 ClawBot Agent 正常；未配置的可选服务显示 disabled。
- JIYU 首页、登录页和模型目录正常打开。
- 最近备份没有过期告警。
- 有真实用户问题时，只核对该用户对应的账号、余额、密钥或请求记录，不跑压力测试。

## 本机异常

先在 OpenClaw App 的“智能体”页查看服务状态和日志。只操作发生故障的服务，不批量重启全部能力。

```bash
bash scripts/auto_health_check.sh --json --strict
openclaw health --json --timeout 5000
openclaw status --json --timeout 5000
```

如果 App 自身无法打开，使用已签名上一版回滚；不要从 Git 历史恢复已删除页面。

## JIYU 异常

1. 判断是网页打不开、登录失败、API Key 失败、余额异常还是单个渠道异常。
2. 只读运行 Sub2API `status` 和 `check`。
3. 先确认 PostgreSQL、Redis、Sub2API、Apache 与公网健康，再决定是否写生产。
4. 任何写入先做一致性备份，失败立即恢复。

不要直接编辑生产数据库、环境文件、Apache 或 Cloudflare DNS。

## 用户支持

- **无法登录**：检查邮箱验证、Passkey/密码、限流和账号状态，不代替用户处理 MFA。
- **Key 不工作**：确认 Key 启用、分组、模型可见、余额和地域限制；不要让用户发送完整 Key。
- **余额或订单争议**：Oracle PostgreSQL 是唯一事实源，以站内账本为准。
- **图片任务失败**：先区分上游权限/模型失败与对象存储失败；当前已知阻塞在上游，不重复付费探针。
- **支付**：站内支付尚未启用，不接受截图作为自动入账证据。

## 备份

```bash
make backup-run
make backup-restore-drill
ssh oracle-arm1 '/usr/local/sbin/openclaw-sub2api-manager backup'
```

备份成功必须同时具备 checksum、受保护权限和恢复演练。不要删除最后一份已验证归档。

## 必须由用户处理

- MFA、账户恢复、所有权转移和不可逆凭据删除。
- 支付商户申请、续费和任何新费用。
- Apple Developer ID、公证和新增硬件。
- 实体手机验收、离机公钥和独立备份介质。

其余日常维护优先使用现有 App、Sub2API 管理器和备份入口，不新增控制台。
