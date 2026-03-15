# Trading Guard

Purpose
- Verify trading safety before enabling automatic execution.

Checklist
- Confirm IB Gateway is reachable on `127.0.0.1:4002`.
- Run `/status` in Telegram and verify risk engine is initialized.
- Confirm daily limits, stop-loss rules, and position caps in `config/.env`.
- Validate broker connectivity before any buy/sell automation.

Fallback
- If IBKR is down, keep strategy output in simulation mode only.
