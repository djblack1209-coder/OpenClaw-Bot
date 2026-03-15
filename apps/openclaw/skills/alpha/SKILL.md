---
name: alpha
description: Telegram shortcut command for alpha-research-pipeline watchlist generation.
metadata: {"openclaw":{"emoji":"📡"}}
---

# Alpha Alias

Use this alias when Boss types `/alpha`.

## Behavior

1. Read `{baseDir}/../alpha-research-pipeline/SKILL.md`.
2. Run the same signal ingestion and ranking pipeline.
3. Return a ranked watchlist with trigger and invalidation for each candidate.
