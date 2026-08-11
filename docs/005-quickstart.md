# OpenEverything 快速开始

> 生产运行时是唯一事实。首次操作先读 `docs/current/current-baseline.md`，不要从旧截图、历史报告或本地测试推断生产状态。

## 本机只读检查

```bash
bash scripts/auto_health_check.sh --json --strict
openclaw health --json --timeout 5000
openclaw status --json --timeout 5000
```

正常基线至少包括 Gateway 与 ClawBot Agent 可达、每日备份新鲜、核心 LaunchAgent 运行。G4F、Kiro 和 IBKR 是显式可选能力，未配置时应显示 disabled，而不是伪装成故障。

## 开发环境

```bash
cd apps/openclaw-manager-src
npm ci
npm run build

cd ../../packages/clawbot
.venv312/bin/python -m compileall -q src
```

不要把 `.env`、浏览器 Profile、数据库、备份或构建产物提交 Git。API Key、Cookie、Token、私钥和账户标识只能留在受保护的运行环境。

## 桌面 App

```bash
make tauri-build
```

该入口会先保存已安装 App，构建并验证签名，再原子安装；失败自动恢复上一版。App 的“智能体”页是本机服务唯一写控制面。

## 浏览器扩展

扩展当前仅支持 X 和小红书的页面识别、只读上下文采集、待审草稿、安全填入和表现回读。默认不点击发布、评论、关注或私信。

聚焦回归：

```bash
node --test \
  packages/openclaw-npm/assets/chrome-extension/test/social-core.test.mjs \
  packages/openclaw-npm/assets/chrome-extension/test/social-page-runner.test.mjs \
  packages/openclaw-npm/assets/chrome-extension/test/popup-static.test.mjs
```

## 本机备份与恢复

```bash
make backup-run
make backup-schedule-status
make backup-restore-drill
```

恢复默认只预览或演练。真正覆盖现有状态前必须有最新 prestate、校验通过的归档、明确范围和失败回滚。

## Oracle JIYU

只读检查：

```bash
ssh oracle-arm1 '/usr/local/sbin/openclaw-sub2api-manager status'
ssh oracle-arm1 '/usr/local/sbin/openclaw-sub2api-manager check'
```

一致性备份：

```bash
ssh oracle-arm1 '/usr/local/sbin/openclaw-sub2api-manager backup'
```

任何更新、品牌、Apache、Cloudflare 源站或地域配置写入都必须使用管理器的现有命令。不得直接替换二进制、改数据库或编辑生产环境文件。

## 聚焦验证

```bash
make docs-check
make sub2api-check
npm run build --prefix apps/openclaw-manager-src
```

只有改动跨越多个共享边界时才运行 `make ci-local`。本地环境失败单独记录，不阻塞安全的生产只读诊断。

## 恢复原则

- Mac：先运行现有备份恢复演练，再使用已签名上一版 App 或受管 LaunchAgent 定义。
- Oracle：使用管理器生成的一致性备份和变更自己的回滚目录。
- 闲鱼、Frist-API 和中央生图 MCP 已退役，不属于恢复目标。
- 支付、订单、数据库迁移、备份恢复和安全数据不得因减负而删除。
