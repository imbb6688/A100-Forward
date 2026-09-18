# Agentic AI / AI Infrastructure Regime v2

## Purpose and boundary

This is a research-only market-regime monitor. It does not generate orders, alter
positions, or modify the Frozen V7 feature, ranking, or account logic. A promotion
to any trading use requires separate backtest, walk-forward, shadow/paper, and
acceptance evidence.

## Data contract

The daily builder consumes the validated HiThink normalized full-market parquet
and its manifest. It refuses incomplete, partial, stale, or future-dated data.
Every signal records its source, observation date, and proxy type. The output also
contains an input/config SHA-256 fingerprint.

The four industry buckets are explicitly **listed-equity market proxies**:

- domestic compute
- optical interconnect
- semiconductor equipment and materials
- robotics

They express price/relative-strength behavior versus CSI 300 and are not evidence
of actual orders, revenue, adoption, or fundamentals. STAR100 relative strength is
computed against STAR50 and CSI300 over 5, 20, and 60 sessions. Direct index or ETF
series are preferred; current-constituent equal-weight reconstruction is only a
lower-confidence fallback and is labeled as such.

`token_demand` is intentionally missing until a supported upstream source exists.
The five observable buckets represent 85% configured coverage. The monitor must
still pass both raw coverage (67%) and confidence-adjusted coverage (50%).

## Failure behavior

The command requires either a governed input JSON or both real daily data and its
manifest. There is no empty-input default. Invalid weights, unknown buckets,
missing provenance, date mismatch, stale data, or insufficient coverage terminate
with a non-zero status. A failed daily run is not published over the prior valid
snapshot.

Run from the repository root as a module so imports are deterministic:

```bash
python -m scripts.iros_agentic_ai_regime \
  --daily /mnt/data/A100_2020_2026_raw.parquet \
  --manifest /mnt/data/hithink_manifest.json
```

The dedicated workflow validates unit/integration behavior on pull requests and
runs a real-data HiThink check on branch pushes or manual dispatch. After merge,
the main A100 Forward workflow owns the one daily run so downloaded data and
persistent history share the same runner and concurrency lock.
