# A100-IROS Enrichment Orchestrator v1

## Purpose

The Enrichment Orchestrator turns each Frozen V7 candidate or Watchlist security into one persistent, continuously refreshable Security Research File.

It coordinates already validated HiThink adapters in this order:

1. full-market Market Dump technical and market context;
2. industry catalog and constituent resolution;
3. financial statements and indicators;
4. valuation snapshot;
5. anomaly, dragon-tiger and limit-pool event context;
6. evidence records, current research object and immutable snapshot.

Capital flow remains `UNAVAILABLE_UPSTREAM` until HiThink publishes a supported endpoint.

## Inputs

- normalized HiThink full-market daily Parquet;
- Frozen V7 `latest_signal.json` Top-2 candidates;
- an optional JSON Watchlist;
- `HITHINK_FINANCE_API_KEY` supplied only through the runtime secret.

Duplicate tickers are collapsed into one enrichment target. Research IDs are stable:

`SEC-<stock-code>-<exchange>`

For example, `600519.SH` becomes `SEC-600519-SH`.

## Persistent layout

```text
<root>/
  objects/<research-id>.json
  snapshots/<research-id>/<snapshot-id>.json
  security_files/<ticker>.json
  security_files/history/<ticker>/<snapshot-id>.json
  enrichment_runs/<timestamp>.json
  latest_enrichment_run.json
```

The current Security Research File contains:

- source and source fingerprint;
- adapter completion status;
- market and technical structure;
- industry mapping;
- fundamentals and valuation;
- raw event context;
- evidence and thesis state;
- immutable snapshot reference;
- explicit research-only governance.

## Failure semantics

Each ticker is enriched in memory before persistence. If any required adapter raises an error:

- the result is `FAILED_NO_WRITE`;
- the previous valid object and current Security Research File remain unchanged;
- no snapshot is created;
- other tickers in the batch may continue.

Immutable snapshot identifiers cannot be overwritten.

## Governance boundary

The orchestrator:

- does not edit or retune Frozen V7;
- does not feed research heuristics back into Frozen V7;
- does not generate broker orders;
- does not automatically promote decision state to Candidate, Validation or Trade Ready;
- preserves the required validation path: Backtest → Walk Forward → Shadow/Paper → Acceptance.

## Daily integration

The production A100 Forward workflow runs enrichment immediately after the Frozen V7 research chain:

- Frozen V7 Top-2 and `config/iros_watchlist.json` are combined and deduplicated;
- no-target sessions are recorded as `SKIPPED_NO_TARGETS`;
- enrichment errors are isolated from Forward Account, Shadow and Pages;
- only a fully successful enrichment run receives a publish marker and is copied to `state/iros_research`;
- the next daily run restores that state before refreshing the same stable research files.

This integration persists research memory but never changes Frozen V7 signals or execution state.

## Command

```bash
python scripts/iros_enrich.py \
  --daily /mnt/data/A100_2020_2026_raw.parquet \
  --signal /mnt/data/forward/latest_signal.json \
  --watchlist watchlist.json \
  --root /mnt/data/iros_research
```

The command exits non-zero if any target fails, while retaining the run summary and every earlier valid Security Research File.

## Validation

- `tests/test_iros_enrichment.py` verifies persistence, immutable snapshots, governance, source normalization and failed-refresh protection.
- `.github/workflows/iros-ci.yml` executes the full dependency-installed unit suite.
- `.github/workflows/iros-enrichment-live-validation.yml` is the manual real-data validation workflow and uploads sanitized artifacts only.
