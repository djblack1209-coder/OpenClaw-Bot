---
name: clawbot-self-heal
description: Detect and recover OpenClaw/ClawBot service failures using the local launchagent control plane.
metadata: {"openclaw":{"emoji":"🩺"}}
---

# ClawBot Self Heal

Use when service health degrades, endpoints fail, or message routing stalls.

## Targets

- OpenClaw gateway: `127.0.0.1:18789`
- ClawBot g4f: `127.0.0.1:18891`
- ClawBot kiro gateway: `127.0.0.1:18793`

## Recovery sequence

1. Detect failing endpoint and impacted workflows.
2. **Auto-recovery first**: Immediately restart affected service (map endpoint to LaunchAgent label).
3. Recheck endpoint health after 10s.
4. If still failing, escalate to dependency service restart order.
5. Recheck again after 10s.
6. Track failure state in `apps/openclaw/memory/heartbeat-state.json` under `healFailures: {endpoint: consecutiveCount}`.

## Notification rules

- **All healthy** → Silent (no message to Boss)
- **Auto-recovery succeeded** → Silent
- **Auto-recovery failed (consecutiveCount >= 2)** → Notify Boss with concise incident note + root cause hypothesis

## Stability rule

- Prefer targeted restarts over full stack restarts.
