# OpenEverything 项目地图

> 本文只描述当前调用关系。生产事实、已验证状态和交接提示词以 `docs/current/current-baseline.md` 为准。

## 生产面

```text
Mac
  OpenClaw.app
    -> OpenClaw Gateway (127.0.0.1:18789)
    -> ClawBot Agent (127.0.0.1:18790)
    -> 可选 G4F / Kiro / IBKR 服务
  Chrome 扩展
    -> X / 小红书当前页只读采集、草稿和安全填入

Oracle
  Cloudflare -> Apache -> Sub2API (127.0.0.1:18080)
                         -> PostgreSQL
                         -> 专用 Redis
                         -> JIYU 私有 R2
```

Oracle 是 JIYU 账户、余额、订单、API 密钥和账本的唯一事实源。Mac 保存个人运行状态和受保护备份，不复制 Oracle 账本。中国生产面暂停，不存在数据库双写。

## 源码归属

| 路径 | 当前职责 |
|------|----------|
| `apps/openclaw-manager-src/` | Tauri 桌面 App、唯一服务写控制面 |
| `packages/clawbot/` | Bot、社媒、投资、资讯和本机 API |
| `packages/openclaw-npm/` | 固定的 OpenClaw 运行包与 X/小红书扩展 |
| `scripts/sub2api_oracle_manage.sh` | Oracle Sub2API 安装、备份、更新、品牌与回滚唯一入口 |
| `scripts/local_backup.sh` | Mac 一致性备份 |
| `scripts/disaster_recovery.sh` | Mac 恢复预览与恢复演练 |
| `tools/launchagents/` | 可复现的 macOS LaunchAgent 定义 |
| `docs/current/current-baseline.md` | 唯一当前生产基线 |

## 写入边界

- App 的“智能体”页通过 Tauri 原生管理器控制受管 LaunchAgent；ClawBot HTTP API 不提供第二套启停实现。
- Chrome 扩展只服务 X 和小红书。填入页面与发布是分离动作，默认不点击发布、评论或关注。
- Sub2API 生产变更只使用现有管理器，必须先备份并通过本地健康、未授权 401 和公网健康回读。
- 支付、数据库迁移、备份恢复、安全和关键浏览器流程保留独立测试，不汇总成第二个控制面。

## 已退役

- 闲鱼客服、卖家浏览器桥、自动发货、恢复上架和 18800 控制台。
- Frist-API 服务、3180 监听、每日 Frist 备份定时器和可登录履约数据库角色。
- 中央生图 MCP 及其客户端注入；原生支持异步图片 API 的客户端直接调用 Sub2API。
- 静态模块注册表、旧路线图和开源轮子调研报告。源码、当前基线和真实故障记录分别承担事实、现状和历史职责。

历史订单兼容字段和数据库迁移保留，以便恢复与审计；它们不是可重新启用的产品入口。

## 维护入口

```bash
bash scripts/auto_health_check.sh --json --strict
openclaw health --json --timeout 5000
openclaw status --json --timeout 5000
make backup-run
make backup-restore-drill
make docs-check
make sub2api-check
make tauri-build
```

不要用本地测试数量代替生产结论，也不要从 Git 历史恢复已退役控制面。
