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
2. Map endpoint to LaunchAgent label.
3. Restart only affected service first.
4. Recheck endpoint health.
5. If still failing, escalate to dependency service restart order.
6. Capture concise incident note with root cause hypothesis.

## Stability rule

- Prefer targeted restarts over full stack restarts.
