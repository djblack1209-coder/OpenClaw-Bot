---
name: playbook
description: Telegram shortcut command for usecase-playbook-router workflow selection.
metadata: {"openclaw":{"emoji":"🧭"}}
---

# Playbook Alias

Use this alias when Boss types `/playbook`.

## Behavior

1. Read `{baseDir}/../usecase-playbook-router/SKILL.md`.
2. Select the best local playbook under `OpenClaw/usecases`.
3. Return a concrete execution plan with checkpoints.
