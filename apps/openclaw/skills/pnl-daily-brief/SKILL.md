---
name: pnl-daily-brief
description: Generate a strict daily PnL and execution report with target tracking and next-session directives.
metadata: {"openclaw":{"emoji":"📊"}}
---

# PnL Daily Brief

Use at end of day or start of next session.

## Required sections

1. Performance
   - Realized PnL
   - Unrealized PnL
   - Net daily return
2. Quality metrics
   - Win rate
   - Avg win / avg loss
   - Profit factor
3. Risk metrics
   - Max intraday drawdown
   - Largest position risk
   - Rule violations (if any)
4. What worked / what failed
5. Tomorrow directives
   - Keep
   - Adjust
   - Stop

## Enforcement

- If target miss is detected, include `RECOVERY MODE: ON` and call out the exact corrective actions.
