# 夜间自动审计系统 — 部署指南

> 最后更新: 2026-04-12

---

## 概述

夜间自动审计系统利用 Claude Code CLI 的无人值守模式（`-p` 参数），在中国时间 00:00-08:00（API 费用低谷期）自动执行全面代码审计。

系统将审计分为 **6 个阶段**，按价值位阶排序执行：

| 阶段 | 角色 | 审计范围 | 预估耗时 |
|------|------|---------|---------|
| 1 | 首席安全工程师 | 密钥/鉴权/输入验证/依赖漏洞 | ~30 分钟 |
| 2 | 首席后端工程师 | 测试/错误处理/并发/资源泄漏 | ~90 分钟 |
| 3 | 首席集成工程师 | HTTP客户端/Mock数据/外部服务 | ~60 分钟 |
| 4 | 首席前端工程师 | TypeScript/Rust/组件/深色模式 | ~90 分钟 |
| 5 | 首席架构师 | 依赖管理/CI-CD/Docker/性能 | ~60 分钟 |
| 6 | 首席产品官 | 注册表/文档/清理/审计总结 | ~60 分钟 |

---

## 文件结构

```
scripts/nightly-audit/
├── config.env.example      # 配置模板（复制为 config.env 使用）
├── config.env              # 实际配置（已 gitignore，不提交）
├── run-audit.sh            # 主执行脚本
├── setup-mac.sh            # macOS launchd 定时配置
├── install-server.sh       # Ubuntu 服务器安装脚本
├── phases/                 # 审计阶段提示词
│   ├── 01-security.txt
│   ├── 02-backend.txt
│   ├── 03-api-integration.txt
│   ├── 04-frontend-ui.txt
│   ├── 05-architecture-ops.txt
│   └── 06-governance-docs.txt
└── logs/                   # 运行日志（自动创建）
    ├── YYYY-MM-DD.log       # 当日汇总日志
    ├── YYYY-MM-DD.progress  # 进度记录
    ├── YYYY-MM-DD.summary   # 审计摘要
    └── YYYY-MM-DD_phaseN_runM.log  # 各阶段详细输出
```

---

## 部署方式

### 方式一：macOS 本机部署（推荐）

项目已在本机，环境齐全，适合日常使用。

#### 步骤

```bash
# 1. 创建配置文件
cd scripts/nightly-audit
cp config.env.example config.env

# 2. 编辑配置，填入 API 密钥
vim config.env
# 必填: ANTHROPIC_API_KEY, MODEL
# 如使用第三方提供商: ANTHROPIC_BASE_URL

# 3. 试运行（不实际调用 Claude，验证脚本逻辑）
./run-audit.sh --dry-run

# 4. 手动运行一次完整审计（验证 API 连通性）
./run-audit.sh 1 1   # 只运行第1阶段测试

# 5. 配置定时任务
./setup-mac.sh
```

#### Mac 休眠处理

Mac 合盖后默认会休眠。解决方案：

1. **setup-mac.sh 自动配置**: 脚本会提示是否配置 `pmset` 唤醒
2. **手动配置**: `sudo pmset repeat wakeorpoweron MTWRFSU HH:55:00`
3. **保持唤醒**: 在"系统设置 → 电池 → 选项"中启用"防止自动休眠"

### 方式二：腾讯云服务器部署

适合 Mac 经常关机/移动的场景。注意服务器仅 2GB 内存。

```bash
# 从本机上传安装脚本
scp scripts/nightly-audit/install-server.sh root@101.43.41.96:~

# SSH 到服务器执行安装
ssh root@101.43.41.96
./install-server.sh

# 编辑配置
vim /opt/openclaw-bot/scripts/nightly-audit/config.env

# 试运行
/opt/openclaw-bot/scripts/nightly-audit/run-audit.sh --dry-run
```

---

## 用法

```bash
# 运行全部 6 个阶段
./run-audit.sh

# 从第 3 阶段开始
./run-audit.sh 3

# 只运行第 2 到第 4 阶段
./run-audit.sh 2 4

# 试运行（不调用 Claude，只验证脚本逻辑）
./run-audit.sh --dry-run
```

---

## 配置说明

### 必填项

| 配置项 | 说明 | 示例 |
|--------|------|------|
| `ANTHROPIC_API_KEY` | API 密钥 | `sk-xxx` |
| `PROJECT_DIR` | 项目绝对路径 | `/Users/blackdj/Desktop/OpenClaw Bot` |

### 可选但建议配置

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `ANTHROPIC_BASE_URL` | 空（用官方） | 第三方 API 提供商地址 |
| `MODEL` | `sonnet` | 模型名称 |
| `BUDGET_PER_PHASE` | `3.00` | 每阶段最大花费（美元） |
| `MAX_TOTAL_BUDGET` | `15.00` | 整晚总预算上限 |
| `AUTO_PUSH` | `true` | 审计完成后自动 git push |
| `NOTIFY_TG_BOT_TOKEN` | 空 | Telegram 通知 Bot Token |
| `NOTIFY_TG_CHAT_ID` | 空 | 接收通知的 Chat ID |

---

## 工作原理

### 执行流程

```
cron/launchd (CST 00:00)
  → run-audit.sh
    → git pull（拉取最新代码）
    → caffeinate（Mac 防休眠）
    → Phase 1: claude -p "安全审计提示词" --dangerously-skip-permissions
      → 如果上下文满了: claude --resume SESSION_ID -p "继续"
      → 检查时间，够则继续
    → Phase 2: claude -p "后端审计提示词" ...
    → ... (6 个阶段)
    → git push（推送修复）
    → Telegram 通知（可选）
```

### 上下文管理

每个阶段是独立的 Claude Code 会话，避免单个会话的上下文窗口耗尽。阶段间通过 `docs/status/HANDOFF.md` 传递状态。

如果单个阶段工作量太大，脚本会自动使用 `--resume` 续接（最多 3 次），模拟用户说"继续审计"。

### 时间控制

- 每个阶段开始前检查剩余时间
- 不足 30 分钟则跳过后续阶段
- 确保在 CST 08:00 前结束

### 预算控制

- 每个阶段有独立预算上限（`--max-budget-usd`）
- 有整晚总预算上限
- 超预算自动停止

---

## 日常操作

### 早上查看审计结果

```bash
# 查看今日摘要
cat scripts/nightly-audit/logs/$(date +%Y-%m-%d).summary

# 查看进度明细
cat scripts/nightly-audit/logs/$(date +%Y-%m-%d).progress

# 查看完整日志
cat scripts/nightly-audit/logs/$(date +%Y-%m-%d).log

# 查看某个阶段的详细输出
cat scripts/nightly-audit/logs/$(date +%Y-%m-%d)_phase1_run1.log

# 查看审计产生的 Git 提交
git log --oneline --since="midnight"
```

### 查看系统状态

```bash
# 审计会更新这些文档
cat docs/status/HANDOFF.md    # 最新交接摘要
cat docs/status/HEALTH.md     # 系统健康状态
cat docs/CHANGELOG.md         # 变更记录
```

### 管理定时任务

```bash
# macOS
launchctl list | grep openclaw           # 查看状态
launchctl start com.openclaw.nightly-audit  # 手动触发
launchctl unload ~/Library/LaunchAgents/com.openclaw.nightly-audit.plist  # 停止

# Ubuntu
crontab -l                               # 查看 cron 列表
crontab -e                               # 编辑 cron
```

---

## 安全注意事项

1. **config.env 不提交**: 已加入 `.gitignore`，包含 API 密钥
2. **`--dangerously-skip-permissions`**: 跳过 Claude Code 的权限确认，仅在可信环境使用
3. **服务器部署建议创建专用用户**: 不要用 root 运行审计
4. **定期轮换 API 密钥**: 特别是在自动化场景
5. **日志中可能包含代码片段**: 日志目录已 gitignore

---

## 故障排除

| 问题 | 原因 | 解决 |
|------|------|------|
| Claude Code 报错 "API key invalid" | API 密钥错误或过期 | 检查 config.env |
| 脚本没有执行 | launchd/cron 未正确配置 | 检查 `launchctl list` 或 `crontab -l` |
| Mac 休眠没有唤醒 | pmset 未配置 | 运行 `setup-mac.sh` 重新配置 |
| 阶段中途停止 | 预算耗尽或上下文满 | 检查 `.progress` 文件，下次从该阶段继续 |
| git push 失败 | 远程有冲突 | 手动 `git pull --rebase && git push` |
| 服务器内存不足 | 2GB 太紧张 | 减少并发，或改用 Mac 部署 |

---

## 自定义审计范围

如需修改审计范围，编辑 `phases/` 目录下的提示词文件。每个 `.txt` 文件是一个完整的 Claude Code 提示词，可以自由调整审计重点和深度。

新增阶段：
1. 在 `phases/` 下创建新的提示词文件（如 `07-custom.txt`）
2. 修改 `run-audit.sh` 中的 `PHASE_NAMES` 和 `PHASE_FILES` 数组
3. 调整 `END_PHASE` 默认值
