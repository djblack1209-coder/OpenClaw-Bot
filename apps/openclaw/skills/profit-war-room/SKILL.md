---
name: profit-war-room
description: Profit-first operating mode for investment decisions with explicit risk controls and no-edge no-trade discipline.
metadata: {"openclaw":{"emoji":"💰"}}
---

# Profit War Room

Use when Boss asks for investment decisions, trading plans, capital allocation, or performance acceleration.

## Core doctrine

- Priority: maximize expected value and compounding.
- Constraint: risk controls are mandatory.
- If edge is unclear, output `NO TRADE`.

## Decision framework

1. Define target and boundary
   - Time horizon
   - Target return
   - Max acceptable drawdown
2. Build opportunity set
   - Catalysts, momentum, liquidity, positioning
3. Score each idea
   - Thesis quality
   - Probabilistic payoff
   - Invalidation clarity
4. Execute only ideas that pass risk gate
   - Favor asymmetric setups
   - Reject emotional or revenge trades
5. End with action board
   - `Execute now`
   - `Monitor`
   - `Reject`

## Failure behavior

- If recent performance misses target, immediately invoke `recovery-retrain-loop`.
