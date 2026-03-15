---
name: execution-risk-gate
description: Pre-trade and post-trade risk gate to prevent low-quality execution and uncontrolled losses.
metadata: {"openclaw":{"emoji":"🛡️"}}
---

# Execution Risk Gate

Use before sending any execution recommendation.

## Pre-trade checks (must pass)

1. Thesis is explicit and falsifiable.
2. Entry trigger is objective (not emotion-driven).
3. Stop condition exists and is quantifiable.
4. Reward-to-risk is acceptable for the setup.
5. Liquidity and spread are tradable at intended size.

## Portfolio constraints

- Cap single-position risk to a strict fraction of equity.
- Cap daily aggregate downside.
- Avoid correlated concentration unless explicitly intentional.

## Post-trade logging

- Record outcome as one of: thesis win, execution win, luck win, thesis fail, execution fail.
- Feed misses into `recovery-retrain-loop` when hit rate or expectancy degrades.
