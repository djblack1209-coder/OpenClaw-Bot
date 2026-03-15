# Telegram Announce

Purpose
- Send operational updates to Telegram after major changes.

Checklist
- Read bot token and target chat id from `config/.env`.
- Send a short plain-text status update.
- Include: service health, model route, and gateway URL.
- Do not include secrets in the message body.

Suggested format
- "System updated. Core services are running. Gateway is online."
