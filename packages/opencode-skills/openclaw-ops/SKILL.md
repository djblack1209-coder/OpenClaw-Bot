# OpenClaw Ops

Purpose
- Keep ClawBot and OpenClaw services healthy.

Checklist
- From the current repository root, run `bash scripts/auto_health_check.sh --json --strict`.
- Ensure the required `ai.openclaw.*` LaunchAgents are running. Optional G4F and Kiro services are healthy when explicitly disabled and must not be started just to satisfy an audit.
- Run `openclaw gateway status --json` and confirm the RPC read-only probe is `ok`.
- Check logs in `~/Library/Logs/ClawBot/` on failures.

Recovery
- Preview recovery from the current repository root with `bash scripts/auto_recovery.sh --dry-run --scope services`.
- Apply the existing recovery path only after checking prestate, backup, rollback, and the exact affected service; then rerun the strict health check.
