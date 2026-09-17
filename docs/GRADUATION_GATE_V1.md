# A100 Graduation Gate V1

The gate converts the remaining roadmap into machine-verifiable evidence. It
does not modify Frozen V7 and it cannot enable a broker connection.

## Required stages

1. **Data** — valid full-market dump plus point-in-time adjustment, ST/risk
   warning history, and historical industry membership.
2. **Walk Forward** — at least three non-overlapping out-of-sample folds, 100
   total trades, 67% profitable folds, median PF >= 1.10, worst-fold PF >=
   0.90, and worst-fold drawdown <= 15%.
3. **Paper** — at least 60 unique sessions and 30 closed trades, PF >= 1.10,
   max drawdown <= 12%, with continuous, unique state history.
4. **Risk** — fail-closed scenarios for invalid/stale data, drawdown, loss
   streak, unknown order state, broker outage, price conflict, T+1, and limit
   locks.
5. **Graduation** — every check must pass. A pass still returns
   `live_trading_enabled=false` and requires separate human approval and a
   broker-specific execution review.

Current repository evidence intentionally records missing PIT ST and industry
history and an incomplete Walk Forward run. The gate therefore remains
`BLOCKED`; no result is invented to force a pass.
