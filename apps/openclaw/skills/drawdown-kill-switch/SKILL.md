---
name: drawdown-kill-switch
description: Escalation protocol for drawdown events with automated risk compression and trading throttle controls.
metadata: {"openclaw":{"emoji":"🚨"}}
---

# Drawdown Kill Switch

Use when equity drawdown, consecutive losses, or abnormal volatility threatens capital.

## Escalation levels

- Level 1 (warning): reduce position size and tighten entries.
- Level 2 (critical): freeze discretionary trades and allow only highest-conviction setups.
- Level 3 (emergency): halt active strategy and switch to recovery workflow.

## Mandatory actions

1. Notify 严总 with concise incident details.
2. Snapshot current exposure and risk.
3. Cut or hedge positions according to predefined limits.
4. Start postmortem log: what failed, why, and what changes before restart.

## Resume criteria

- No resume until root-cause actions are defined and validated.
