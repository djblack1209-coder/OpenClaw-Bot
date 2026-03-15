# Telegram Forum Topic Cutover

适用场景：你要把当前 supergroup 从 lane 标签分流升级为 Telegram 原生 topic/thread 分流。

## 目标

- 保留现有 7-bot 架构和风控规则。
- 在同一个群里，用 forum topic 做职责隔离（RISK/ALPHA/EXEC/FAST/CN/BRAIN/CREATIVE）。
- 提供一键改写 `/.openclaw/openclaw.json` 的工具和回滚路径。

## 0) 预检（当前群是否已开启 forum）

在项目根目录执行：

```bash
token=$(jq -r '.channels.telegram.accounts.default.botToken // .channels.telegram.botToken' ".openclaw/openclaw.json")
curl -s "https://api.telegram.org/bot${token}/getChat?chat_id=-1003754981982"
```

判定：返回里出现 `"is_forum": true` 代表已开启 forum topic。

## 1) 免费升级步骤（Telegram 客户端）

1. 打开目标群 -> `Edit`/`管理群组`。
2. 打开 `Topics`/`话题` 开关（升级到 forum 形态）。
3. 确认 Bot 管理员权限包含：`can_manage_topics`、`can_send_messages`。

## 2) 创建 7 个 topic（建议命名）

- `RISK-风控`
- `ALPHA-研究`
- `EXEC-执行`
- `FAST-快问`
- `CN-中文`
- `BRAIN-终极推理`
- `CREATIVE-创意`

## 3) 发现 topic 的 message_thread_id

执行：

```bash
node OpenClaw/tools/telegram-topic-discovery.mjs --chat-id -1003754981982 --limit 200
```

你会拿到 `topics[]`，里面包含 `threadId` 与 `topicName`。

## 4) 一键改写 OpenClaw topic 路由

把上一步拿到的 threadId 填进去执行：

```bash
node OpenClaw/tools/apply-telegram-topic-routing.mjs \
  --chat-id -1003754981982 \
  --owner-id 7043182738 \
  --risk 101 \
  --alpha 102 \
  --exec 103 \
  --fast 104 \
  --cn 105 \
  --brain 106 \
  --creative 107
```

脚本会：

- 自动备份当前配置为 `/.openclaw/openclaw.json.bak-topic-*`
- 写入 `channels.telegram.groups.<chatId>.topics.<threadId>`
- 每个 topic 自动设置：`enabled=true`、`requireMention=false`、`groupPolicy=allowlist`

## 5) 验证与切换策略

```bash
openclaw config validate
openclaw cron run 5e401547-128d-4614-bd72-a8e620e8b731
openclaw cron runs --id 5e401547-128d-4614-bd72-a8e620e8b731 --limit 5
```

建议切换顺序：

1. 先保留 lane 标签分流（现网兜底）。
2. 新消息优先在 topic 内测试一段时间。
3. 稳定后再逐步降低 lane 标签依赖。

## 6) 回滚

```bash
latest=$(ls -t ".openclaw"/openclaw.json.bak-topic-* | head -n 1)
cp "$latest" ".openclaw/openclaw.json"
openclaw config validate
```

回滚后立即恢复 lane 标签模式即可。
