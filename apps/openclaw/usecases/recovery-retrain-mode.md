# Recovery Retrain Mode

## Objective

When profit targets are missed, switch into a strict recovery cycle until performance quality returns.

## Inputs

- PnL history and trade log
- Strategy parameter history
- Current drawdown and volatility context

## Workflow

1. Trigger recovery mode on target miss or drawdown breach.
2. Run postmortem by failure bucket: thesis, timing, sizing, execution.
3. Adjust strategy rules and tighten risk budgets.
4. Validate via dry run/paper run.
5. Resume normal mode only after recovery criteria are met.

## Success metrics

- Drawdown stabilization
- Recovery of positive expectancy
- Reduced rule-violation count

## Abort conditions

- Continued degradation after retraining
- Inability to explain source of losses with evidence

## Source inspiration

- `awesome-openclaw-usecases-src/usecases/polymarket-autopilot.md`
- `awesome-openclaw-usecases-src/usecases/project-state-management.md`
