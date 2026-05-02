# 密钥轮换操作指南

> 最后更新: 2026-03-28

## 1. 概述

项目使用 `config/.env` 文件管理约 55 个 API 密钥。本指南规定了密钥分类、轮换频率和操作步骤。

**核心原则：**
- 所有密钥通过 `os.getenv()` 加载，源码中零硬编码
- `.env` 文件已被 `.gitignore` 排除，不会提交到 Git
- 密钥缺失时功能静默降级（不崩溃）

---

## 2. 密钥分类与轮换周期

| 优先级 | 分类 | 轮换周期 | 密钥清单 |
|--------|------|----------|----------|
| **高** | 付费 LLM API | 90天 | `CLAUDE_API_KEY`, `VOLCENGINE_API_KEY`, `FAL_KEY`, `KLING_*`, `DEEPGRAM_API_KEY` |
| **高** | 内部认证 | 90天 | `OPENCLAW_API_TOKEN`, `DEPLOY_ADMIN_TOKEN`, `KIRO_API_KEY` |
| **中** | 邮箱密码 | 180天 | `OPS_EMAIL_PASSWORD`, `SMTP_PASS` (同一密码，需同时更新) |
| **中** | 免费 LLM API | 180天或额度耗尽 | `OPENROUTER_API_KEY`, `GROQ_API_KEY`, `CEREBRAS_API_KEY`, `GEMINI_API_KEY` 等 |
| **低** | Telegram Bot | 仅泄露时 | `QWEN235B_TOKEN` 等 7 个 Bot Token |
| **低** | Session Cookie | 自动过期 | `XIANYU_COOKIES` |

---

## 3. 轮换操作步骤

### 3.1 通用流程

```bash
# 1. 在提供商官网生成新密钥

# 2. 测试新密钥可用
curl -H "Authorization: Bearer <新密钥>" https://api.xxx.com/v1/models

# 3. 更新 config/.env
nano packages/clawbot/config/.env
# 修改对应行: SOME_API_KEY=<新密钥>

# 4. 重启服务
cd packages/clawbot && python multi_main.py

# 5. 检查日志确认初始化成功
grep "已启用\|initialized\|API Token 认证已启用" /tmp/clawbot.log

# 6. 在提供商官网撤销旧密钥
```

### 3.2 OPENCLAW_API_TOKEN 轮换

这是内部 API 认证 Token，需同时更新后端和前端：

```bash
# 1. 生成新 Token
python3 -c "import secrets; print(secrets.token_urlsafe(32))"

# 2. 更新后端
# 编辑 packages/clawbot/config/.env:
# OPENCLAW_API_TOKEN=<新Token>

# 3. 更新前端 (Tauri 桌面端)
# 编辑 apps/openclaw-manager-src/.env.local:
# VITE_CLAWBOT_API_TOKEN=<新Token>

# 4. 重启后端 + 重新构建前端
```

### 3.3 Telegram Bot Token 轮换

```bash
# 1. 通过 @BotFather 使用 /revoke 命令获取新 Token
# 2. 更新 config/.env 中对应的 *_TOKEN 变量
# 3. 重启服务
```

### 3.4 邮箱应用密码轮换

```bash
# 1. 在 Google 账户 → 安全性 → 应用专用密码 → 生成新密码
# 2. 同时更新两处 (使用相同密码):
#    OPS_EMAIL_PASSWORD=<新密码>
#    SMTP_PASS=<新密码>
# 3. 重启服务
```

---

## 4. SiliconFlow 密钥池管理

SiliconFlow 支持多密钥轮转，系统自动管理：

```bash
# config/.env 中逗号分隔多个密钥
SILICONFLOW_KEYS=key1,key2,key3,key4
SILICONFLOW_PAID_KEYS=pkey1,pkey2,...,pkey10
```

- 系统自动 Round-Robin 轮转
- 额度耗尽的密钥自动标记为 exhausted
- 新增密钥只需追加到逗号列表末尾并重启

---

## 5. 紧急泄露处理

如果发现密钥泄露：

```bash
# 1. 立即在提供商官网撤销泄露的密钥
# 2. 生成新密钥并更新 config/.env
# 3. 重启服务
# 4. 检查是否有异常 API 调用 (查看提供商的用量仪表盘)
# 5. 如果是 Git 泄露，使用 git filter-repo 清除历史
```

---

## 6. 未配置密钥的功能列表

以下功能因对应密钥未配置而处于禁用状态：

| 功能 | 需要的密钥 | 状态 |
|------|-----------|------|
| X/Twitter 发帖 | `X_BEARER_TOKEN` + OAuth 4个 | 未配置 |
| Alpaca 交易 | `ALPACA_API_KEY/SECRET` | 未配置 |
| Langfuse 监控 | `LANGFUSE_SECRET_KEY/PUBLIC_KEY` | 未配置 |
| Tavily 搜索 | `TAVILY_API_KEY` | 未配置 |
| Retell 语音 | `RETELL_API_KEY` | 未配置 |
| Composio 集成 | `COMPOSIO_API_KEY` | 未配置 |
| Skyvern RPA | `SKYVERN_API_KEY` | 未配置 |
