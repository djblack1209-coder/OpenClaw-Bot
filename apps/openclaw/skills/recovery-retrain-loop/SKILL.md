---
name: recovery-retrain-loop
description: Recovery mode when profit targets are missed; diagnose, retrain, tighten risk, and relaunch.
metadata: {"openclaw":{"emoji":"♻️"}}
---

# Recovery Retrain Loop

Use when performance is below target or when losses indicate regime mismatch.

## Trigger conditions

- Daily/weekly profit target miss.
- Drawdown breach.
- Strategy expectancy turns negative.

## Loop

1. Diagnose
   - Separate market regime issue vs execution issue.
2. Decompose losses
   - Entry quality, exit quality, sizing, timing, risk leakage.
3. Retrain rules
   - Remove weak patterns.
   - Reinforce high-expectancy patterns.
4. Compress risk
   - Temporarily reduce exposure while validating updates.
5. Validate
   - Dry-run or paper-run before full return to size.
6. Relaunch
   - Resume only with explicit guardrails.

## Language policy

- Interpret "no profit = fail" as an operational urgency signal, not a reason to abandon risk discipline.
