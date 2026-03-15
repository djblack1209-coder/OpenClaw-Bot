---
name: alpha-research-pipeline
description: Build ranked watchlists from catalysts, market narratives, and event-driven signals.
metadata: {"openclaw":{"emoji":"📡"}}
---

# Alpha Research Pipeline

Use when Boss asks for market scanning, opportunity discovery, earnings tracking, or signal prioritization.

## Pipeline

1. Ingest signals
   - Earnings calendar
   - Macro calendar
   - Sector and narrative headlines
   - Social/news anomalies
2. Normalize to a candidate list
3. Score each candidate
   - Catalyst strength
   - Time sensitivity
   - Liquidity and spread quality
   - Risk of narrative reversal
4. Produce ranked watchlist
   - Setup
   - Trigger condition
   - Invalidation condition
   - Suggested position sizing band

## Output contract

- Always return top candidates with clear trigger and invalidation.
- If none meet quality threshold, say so explicitly and avoid forced picks.
