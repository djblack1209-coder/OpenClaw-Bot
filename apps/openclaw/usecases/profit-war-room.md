# Profit War Room

## Objective

Run a high-intensity profit engine that prioritizes expected value while preserving survivability.

## Inputs

- Current capital and exposure
- Daily/weekly profit targets
- Max drawdown constraints
- Event and catalyst feed

## Workflow

1. Generate candidate trades from event-driven catalysts.
2. Filter for asymmetry and liquidity.
3. Pass every candidate through `execution-risk-gate`.
4. Execute only high-conviction setups.
5. Review outcomes and feed misses into `recovery-retrain-mode`.

## Success metrics

- Positive expectancy
- Profit target hit rate
- Controlled drawdown profile

## Abort conditions

- Risk limits breached
- Regime shift invalidates current strategy assumptions

## Source inspiration

- `awesome-openclaw-usecases-src/usecases/polymarket-autopilot.md`
- `awesome-openclaw-usecases-src/usecases/earnings-tracker.md`
