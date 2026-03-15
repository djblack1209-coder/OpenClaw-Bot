# OpenClaw Ops

Purpose
- Keep ClawBot and OpenClaw services healthy.

Checklist
- Run `./scripts/clawctl.sh status` in `~/Desktop/OpenClaw Bot/clawbot`.
- Ensure `com.clawbot.agent`, `com.clawbot.g4f`, `com.clawbot.kiro-gateway` are running.
- Run `openclaw gateway status` and confirm RPC probe is `ok`.
- Check logs in `~/Library/Logs/ClawBot/` on failures.

Recovery
- Run `./scripts/repair_launch_agents.sh` in `~/Desktop/OpenClaw Bot/clawbot`.
- If needed, re-bootstrap jobs with `launchctl bootstrap gui/$(id -u) <plist>`.
