---
name: risk
description: Telegram shortcut command for execution-risk-gate pre-trade checks.
metadata: {"openclaw":{"emoji":"🛡️"}}
---

# Risk Alias

Use this alias when Boss types `/risk`.

## Behavior

1. Read `{baseDir}/../execution-risk-gate/SKILL.md`.
2. Apply mandatory pre-trade and portfolio risk checks.
3. Output pass/fail with exact reasons and required fixes.
