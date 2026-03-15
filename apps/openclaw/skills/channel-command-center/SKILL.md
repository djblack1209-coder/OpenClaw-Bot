---
name: channel-command-center
description: Operate multi-channel messaging as a single command center with priority routing and alert hygiene.
metadata: {"openclaw":{"emoji":"📣"}}
---

# Channel Command Center

Use when configuring, testing, or operating Telegram/Discord/other channels.

## Routing model

- Primary command channel: Telegram
- Secondary collaboration channels: Discord/Slack
- Alert channel: high-priority incident summaries only

## Telegram 分流模式

- 当前群若不是 forum，使用 lane 标签分流（见 `telegram-lane-router`）：
  - `[RISK]` `[ALPHA]` `[EXEC]` `[FAST]` `[CN]` `[BRAIN]` `[CREATIVE]`
- 若后续迁移到 forum supergroup，再切换为 topic/thread 路由。

## Message policy

1. Send short, structured alerts.
2. Include severity, impact, and next action.
3. Avoid duplicate notifications across channels.
4. Confirm delivery path after critical alerts.

## Reliability checks

- Validate channel config before test sends.
- Run one quick end-to-end test after configuration changes.
- Keep channel-specific failures isolated from core trading/system alerts.
