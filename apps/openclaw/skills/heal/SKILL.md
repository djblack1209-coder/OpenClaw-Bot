---
name: heal
description: Telegram shortcut command for clawbot-self-heal service recovery.
metadata: {"openclaw":{"emoji":"🩺"}}
---

# Heal Alias

Use this alias when Boss types `/heal`.

## Behavior

1. Read `{baseDir}/../clawbot-self-heal/SKILL.md`.
2. Run endpoint diagnosis and targeted restart sequence.
3. Return health status plus concise incident summary.
