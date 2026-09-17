# PIT and Walk Forward Evidence

## HiThink boundary verified 2026-09-17

The official public contract exposes full-market daily K and adjustment-event
dumps. Industry catalogs and constituents are current snapshots. Historical
industry membership and historical ST/risk-warning intervals are not exposed.
The planned stock-to-index membership endpoint is also not callable yet.

Current snapshots must not be backfilled into historical dates.

## Canonical PIT imports

`scripts/a100_pit_import.py` accepts versioned CSV/Parquet extracts and rejects
missing columns, invalid intervals, overlaps and duplicates. Required schemas:

- ST: `symbol,effective_from,effective_to,is_st`
- Industry: `symbol,effective_from,effective_to,industry_code`

The source name and source version are mandatory. The resulting files are
written under `/mnt/data/pit/` and checked by the graduation data inventory.

## Immediate empirical evidence

`scripts/a100_v7_walk_forward_proxy.py` evaluates the model trained only on
2020–2022 across annual 2023+ folds. It selects Frozen V7 daily Top 2 and
reports trade count, positive ratio, mean R, PF, net return and drawdown.

This is intentionally labelled `RANKING_PROXY` and
`graduation_eligible=false`: it uses signal-level future outcomes and does not
enforce overlapping positions or cash constraints. It is useful evidence about
ranking stability, but it cannot satisfy the final `PORTFOLIO_REPLAY` gate.
