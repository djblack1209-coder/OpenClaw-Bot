# HANDOFF — 会话交接摘要

> 最后更新: 2026-05-04

---

## [2026-05-04 12:00] Frist-API 清理提交前交接

### 本次完成了什么
- Frist-API 已完成 Workbench UI、New-API 桥接、DeepSeek v4 默认模型、登录免验证码、注册挑战增强、CC Switch/Codex 导入和美元计价等前序改动。
- 本轮补齐后端不可用时的用户恢复入口：工作台会显示离线恢复条，并提供一键重新连接。
- 文档治理已归集到 `docs/` 根目录编号文件，旧散落文档和历史 usecase 文档已进入本次清理范围。

### 未完成的工作
- 正式商业化仍需固定域名 HTTPS、真实支付回调、注册邮箱验证码/找回密码闭环、Turnstile/Redis 限流、管理员 2FA、数据库迁移、备份监控和真实 DeepSeek Key 在 Codex 桌面端端到端实测。
- New-API 已作为上游 submodule 和桥接层接入，但历史用户、余额、Key、订单和日志迁移仍需单独演练。

### 需要注意的坑
- 不要把服务器密码、管理员入口码、管理员令牌、用户真实 Key、上游 Key 或运行时 JSON 写入仓库、文档或最终汇报。
- `packages/new-api-upstream` 是上游 submodule，同步应走 `make new-api-check` / `make new-api-sync`，不要手工复制上游代码。

### 当前系统状态
- Frist-API 本地测试需要继续以 `cd apps/frist-api && npm test` 作为提交前验收。
- New-API 同步检查需要继续以 `make new-api-check` 验证 GitHub latest release、submodule 指针和 Compose 镜像一致。
