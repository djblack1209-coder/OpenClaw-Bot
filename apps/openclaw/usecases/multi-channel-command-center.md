# Multi-Channel Command Center

## Objective

Operate Telegram, Discord, and other channels as one coordinated control surface.

## Inputs

- Channel configurations
- Alert policy (severity and routing)
- Message templates for status and incidents

## Workflow

1. Use Telegram as primary command lane.
2. Route collaboration updates to secondary channels.
3. Deduplicate notifications across channels.
4. Keep critical incident alerts short and actionable.

## Success metrics

- Reduced channel noise
- Faster incident response
- Consistent delivery confirmation

## Abort conditions

- Credential or channel API failures
- Unknown delivery state on critical alerts

## Source inspiration

- `awesome-openclaw-usecases-src/usecases/multi-channel-assistant.md`
- `awesome-openclaw-usecases-src/usecases/multi-agent-team.md`
- `awesome-openclaw-usecases-src/usecases/multi-channel-customer-service.md`
