# OpenClaw Bot Skills Pack

This pack curates local workspace skills for OpenClaw Bot and maps them to community references.

## Local skills enabled

- `usecase-playbook-router`
- `profit-war-room`
- `alpha-research-pipeline`
- `execution-risk-gate`
- `drawdown-kill-switch`
- `recovery-retrain-loop`
- `pnl-daily-brief`
- `clawbot-self-heal`
- `channel-command-center`
- `telegram-lane-router`
- `cost-quota-dashboard`
- `dev-todo-mode`

## Telegram shortcut aliases

- `profit` -> `profit-war-room`
- `alpha` -> `alpha-research-pipeline`
- `risk` -> `execution-risk-gate`
- `recover` -> `recovery-retrain-loop`
- `brief` -> `pnl-daily-brief`
- `heal` -> `clawbot-self-heal`
- `channel` -> `channel-command-center`
- `playbook` -> `usecase-playbook-router`
- `lane` -> `telegram-lane-router`
- `cost` -> `cost-quota-dashboard`
- `dev` -> `dev-todo-mode`

## Reference mapping

| Local skill | Usecase inspirations | Skill-list inspirations |
|---|---|---|
| `profit-war-room` | `usecases/polymarket-autopilot.md` | `categories/search-and-research.md` (`reef-polymarket-research`) |
| `alpha-research-pipeline` | `usecases/earnings-tracker.md` | `categories/git-and-github.md` (`kiro-creator-monitor-daily-brief`) |
| `execution-risk-gate` | `usecases/polymarket-autopilot.md` | `categories/productivity-and-tasks.md` (`portfolio-risk-analyzer`) |
| `drawdown-kill-switch` | `usecases/polymarket-autopilot.md` | `categories/search-and-research.md` (`blacksnow`) |
| `recovery-retrain-loop` | `usecases/project-state-management.md` | `categories/productivity-and-tasks.md` (`ops-hygiene`) |
| `pnl-daily-brief` | `usecases/custom-morning-brief.md` | `categories/productivity-and-tasks.md` (`rho-telegram-alerts`) |
| `clawbot-self-heal` | `usecases/self-healing-home-server.md` | `categories/devops-and-cloud.md` (`agentic-devops`) |
| `channel-command-center` | `usecases/multi-channel-assistant.md` | `categories/web-and-frontend-development.md` (`create-agent-with-telegram-group`) |
| `telegram-lane-router` | `usecases/multi-channel-assistant.md` | `categories/communication.md` (`telegram-contact-sync`) |
| `cost-quota-dashboard` | `usecases/project-state-management.md` | `categories/data-and-analytics.md` (`lineary-api`) |
| `dev-todo-mode` | `usecases/autonomous-game-dev-pipeline.md` | `categories/coding-agents-and-ides.md` (`coding-agent`) |
| `usecase-playbook-router` | `usecases/README.md` | `categories/git-and-github.md` (`agent-team-orchestration`) |

## Activation path

1. Skills live under `OpenClaw/skills/` (workspace scope).
2. Skill entries are enabled in `.openclaw/openclaw.json` under `skills.entries`.
3. OpenClaw loads workspace skills on the next session turn.

## Security note

- These local skills are instruction-only playbooks.
- Before adopting any third-party executable skill from public registries, review source code and permissions.
