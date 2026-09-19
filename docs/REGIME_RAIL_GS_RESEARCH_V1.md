# A100 Regime / Adaptive Rail / GS Research v1

Status: **research only**. Frozen V7 remains unchanged.

This experiment separates three questions: (1) Market Regime: how permissive is the cross-sectional environment? (2) Adaptive Rail: what trend-life-cycle state is each stock in? (3) GS Trigger proxy: is there a causal reversal/entry/re-entry/exhaustion/exit setup inside that trend?

The GS proxy is **not** represented as the proprietary Tonghuashun/Financial Master formula. It is an independently specified, testable A100 hypothesis inspired by observable state/trigger separation.

## Validation contract

All rolling and EMA features are point-in-time causal. Primary outputs report sample count, 5/20-day forward return and 20-day hit rate by Market × Rail × GS state. The first diagnostic window is 2026-05-19 through 2026-09-18, chosen to investigate the long Frozen V7 signal drought without changing the frozen baseline.

No production promotion is permitted from an attractive in-sample table. Required next evidence: multi-year PIT replay, transaction-cost-aware event returns, walk-forward parameter stability, regime/state coverage, turnover and drawdown, then Shadow/Paper comparison against Frozen V7. Thresholds must be frozen before the final holdout.

Run:

    python scripts/a100_regime_research.py --input <canonical OHLCV parquet>

Outputs are written under research_results/regime_v1 by default.
