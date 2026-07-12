# OpenEverything 使用手册（给老板）

> 最后更新：2026-07-12
> 目标：日常只看状态和续费提醒；真实交易、发货、发布、付款和生产修改仍由本人确认。

## 日常只做这一件事

在项目目录运行：

```bash
cd /Users/blackdj/Desktop/OpenEverything
scripts/auto_health_check.sh --json
```

如果本机控制台已经启动，也可以打开 `http://127.0.0.1:18800/dashboard`。页面打不开不等于数据丢失，先按下面的恢复预演处理。

### 颜色怎么看

- 🟢 **绿灯**：不用处理。
- 🟡 **黄灯**：按输出里的“下一步”处理；常见原因是续费日期仍为 `unknown`、资源进入提醒窗口或某个可选服务降级。
- 🔴 **红灯**：先导出脱敏状态或保存健康检查输出，再做恢复预演；不要反复重启、重复发卡或重复点击发布。

## 红灯怎么处理

### 第一步：只看恢复计划

```bash
scripts/auto_recovery.sh --dry-run
```

这一步不会重启服务、启动浏览器或删除文件。

### 第二步：确认计划后再执行

```bash
scripts/auto_recovery.sh --confirm
```

只有显式 `--confirm` 才会执行。涉及生产部署、LaunchAgent、Docker、账号登录或真实外部业务时，先由本人授权对应动作。

## 续费清单

本机实际台账位置：

```text
packages/clawbot/config/renewals.json
```

首次使用：

```bash
cp packages/clawbot/config/renewals.example.json packages/clawbot/config/renewals.json
```

只填写：资源名称、用途、供应商、到期日、预计费用、自动续费状态和安全操作入口。**不要填写**密码、API Key、Cookie、验证码、MFA 恢复码、证书内容或银行卡信息。

提醒规则：提前 **30 / 14 / 7 / 3 / 1 天**提示；未知日期保持 `unknown`。系统不会替你登录、付款、续费或修改自动续费。

检查方式：

```bash
scripts/check_renewals.py --json
```

## 备份和恢复

### 创建源码快照

```bash
scripts/local_backup.sh
```

脚本带锁、空间预检、校验和保留策略，并排除 `.env`、数据库、日志、浏览器 Profile、依赖和构建产物等敏感/可再生成目录。

### 数据库备份与可丢弃恢复演练

```bash
make backup-databases
make backup-restore-drill
```

### 灾难恢复

先预演：

```bash
scripts/disaster_recovery.sh --dry-run
```

真实覆盖必须显式确认：

```bash
scripts/disaster_recovery.sh --confirm
```

## 永远需要本人确认的事

- 真实交易、下单、转账、付款、退款和充值。
- 闲鱼发送卡密、确认发货、恢复自动发货和处理真实订单。
- 社媒发布、评论、关注、私信和删除内容。
- 账号登录、扫码、MFA、实名、验证码和平台风控验证。
- 购买、续费、扩容、改变自动续费或创建付费资源。
- 生产部署、重启、删除数据、升级 New-API、安装桌面 App 和不可逆操作。

## 老板只需要记住一句话

平时跑健康检查，看黄/红灯和续费提醒；任何会动钱、动账号、发出去或删生产数据的动作，都先由本人确认。
