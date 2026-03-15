---
name: brief
description: Telegram shortcut command for pnl-daily-brief and next-session directives.
metadata: {"openclaw":{"emoji":"📊"}}
---

# Brief Alias

Use this alias when Boss types `/brief`.

## Behavior

1. Read `{baseDir}/../pnl-daily-brief/SKILL.md`.
2. Produce the full PnL brief format.
3. If target miss is detected, include `RECOVERY MODE: ON` and corrective actions.
