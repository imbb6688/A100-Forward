# A100 Investment Research Operating System (IROS) v1

## Status

IROS v1 is a **research-only operating layer** for A100. It standardizes market, industry, security, event, thesis, validation, risk and execution-plan information without modifying the Frozen V7 ranker or its signal-generation logic.

The governing rule is unchanged:

> No research signal becomes a production rule merely because it exists in IROS.

A new rule or score remains research-only until it has evidence from Backtest, Walk Forward and Shadow/Paper validation and an explicit acceptance reference.

## Scope

IROS v1 provides:

1. `ResearchObject` — canonical research entity.
2. `SecurityResearchCard` — market, industry, fundamentals, valuation, events, technical structure, positioning, risks and thesis.
3. `DecisionState` — guarded lifecycle from discovery through research, validation, trade readiness, position lifecycle and post-review.
4. `EvidenceItem` and `EvidenceLedger` — explicit separation of facts, evidence, inferences, hypotheses and rules, including superseded/invalid/conflicting evidence.
5. `ResearchSnapshot` — immutable point-in-time record.
6. `ThesisDelta` — differences between two snapshots: stance, confidence, state, evidence, risks and invalidation conditions.
7. `ResearchRepository` — versioned JSON object storage plus immutable snapshots.
8. Market/industry/event assessment contracts.
9. `ResearchScore` — optional research-priority score. Default status is `UNVALIDATED_RESEARCH_HEURISTIC`.
10. `PremortemFailure` — pre-trade failure-map contract.
11. `ValidationRecord` — Backtest -> Walk Forward -> Shadow/Paper evidence chain.
12. `TradePlan` — structured entry, invalidation, sizing-cap, reduction and exit contract.
13. `evaluate_trade_readiness` — governance gate. It does not emit buy/sell signals.
14. Portfolio concentration and risk-budget helpers.
15. CLI commands for repository creation, inspection, snapshots and diffs.

## Non-goals

IROS v1 does **not**:

- modify `scripts/a100_v7_forward_ranker.py`;
- change V7 training parameters or training period;
- retune Frozen V7 with forward data;
- generate broker orders;
- place trades;
- promote a heuristic score into validated alpha;
- treat news sentiment, technical indicators or model commentary as verified signals without validation evidence.

## Research lifecycle

```text
DISCOVERED
  -> RESEARCHING
  -> WATCHLIST or CANDIDATE
  -> VALIDATION
  -> TRADE_READY
  -> ACTIVE_POSITION
  -> REDUCE / EXIT
  -> POST_REVIEW
  -> ARCHIVED
```

Side paths:

```text
REJECTED
INVALIDATED
```

Invalid state jumps are rejected by the model.

## Research card contract

Each security can retain:

```text
Market Context
Industry Context
Fundamentals
Valuation
Catalysts
Event Risks
Technical Structure
Positioning
Risks
Evidence
Thesis
Metadata
Audit Log
Validation Record
Trade Plan
```

The research card is deliberately source-agnostic. Daily Intelligence or another ingestion layer may populate these fields, but the IROS core itself does not fabricate or fetch market data.

## Evidence taxonomy

`EvidenceKind` values:

- `FACT`
- `EVIDENCE`
- `INFERENCE`
- `HYPOTHESIS`
- `CANDIDATE_RULE`
- `VALIDATED_RULE`

The ledger lifecycle is separate:

- `ACTIVE`
- `SUPERSEDED`
- `INVALIDATED`
- `CONFLICTING`

This prevents a later source correction from silently rewriting historical research.

## Thesis contract

A thesis can contain:

- stance;
- bull case;
- base case;
- bear case;
- conditions that must remain true;
- explicit invalidation conditions;
- priced-in assessment;
- variant perception;
- confidence;
- update timestamp.

Confidence is bounded to `[0, 1]`. Confidence is a research annotation, not a probability forecast unless a separately validated calibration process is introduced.

## Thesis Delta

Two immutable snapshots can be compared to produce:

- stance change;
- confidence change;
- decision-state change;
- new/removed evidence;
- new/removed risks;
- new/removed invalidation conditions.

The purpose is to answer: **what changed, and why did the research view change?**

## Research score

`weighted_research_score()` accepts components on a `0..100` scale. If weights are omitted, equal weights are used. If weights are provided, they are normalized.

The default status is:

`UNVALIDATED_RESEARCH_HEURISTIC`

This score is for research prioritization only. It is not an execution score and is not part of Frozen V7.

## Event assessment

Events can be annotated with:

- direction;
- impact;
- surprise;
- persistence;
- credibility;
- estimated priced-in level;
- source;
- observed time.

The `incremental_information_score` is a simple research heuristic:

```text
impact * surprise * persistence * credibility * (1 - priced_in)
```

It is explicitly unvalidated unless separate evidence upgrades its status.

## Validation governance

A `ValidationRecord` must contain all three required stages:

1. `BACKTEST`
2. `WALK_FORWARD`
3. `SHADOW_PAPER`

All must be `PASS`. To reach `VALIDATED`, the record must also include:

- `accepted_at`;
- `acceptance_ref`.

A plain metadata flag is insufficient.

Each validation stage may also record:

- evidence/artifact reference;
- dataset version;
- code version;
- notes.

## Trade-readiness gate

`TRADE_READY` requires all of the following:

- current state is `VALIDATION`;
- at least one `FACT` or `EVIDENCE` item exists;
- base case exists;
- thesis invalidation conditions exist;
- thesis confidence is present;
- complete accepted `ValidationRecord` exists;
- valid `TradePlan` exists and matches the ticker.

Failure of any check blocks promotion.

This is a governance gate, not an investment recommendation.

## Trade plan contract

A `TradePlan` requires:

- plan id;
- ticker;
- entry conditions;
- invalidation conditions;
- exit conditions.

It may additionally contain:

- initial-position fraction;
- maximum-position fraction;
- add conditions;
- reduce conditions;
- time stop;
- event stop;
- portfolio-risk note.

It does not contain a broker action and cannot place an order.

## Portfolio risk helpers

IROS v1 can summarize:

- security weights;
- industry weights;
- theme weights;
- weighted beta when supplied;
- HHI concentration;
- largest position.

The current concentration warnings are deterministic research safeguards, not optimized portfolio limits. They must be calibrated separately before being treated as validated policy.

`size_position_by_risk_budget()` sizes a hypothetical position from:

- account equity;
- allowed loss fraction;
- entry price;
- invalidation price;
- board-lot size;
- maximum notional fraction.

Decimal arithmetic is used on the sizing path to avoid losing a board lot because of binary floating-point representation error.

## Persistence

Current write schema: `1.0`.

Read compatibility:

- `0.1`
- `1.0`

Object storage is atomic through temp-file replacement.

Snapshots are immutable by id and cannot be overwritten.

Suggested runtime location:

```text
state/iros/
  objects/
  snapshots/
```

Do not publish private research or portfolio state to GitHub Pages unless a separate sanitization contract is implemented.

## CLI

Create an object:

```bash
python -m a100_iros --root state/iros new SEC-600206-001 600206.SH --company "Example"
```

Inspect:

```bash
python -m a100_iros --root state/iros show SEC-600206-001
```

Snapshot:

```bash
python -m a100_iros --root state/iros snapshot SEC-600206-001 --snapshot-id 20260917-close
```

List snapshots:

```bash
python -m a100_iros --root state/iros snapshots SEC-600206-001
```

Compare snapshots:

```bash
python -m a100_iros --root state/iros diff SEC-600206-001 20260917-close 20260924-close
```

## Integration with A100 00-05

### 00 Master Architecture
Owns IROS architecture, schemas, governance and version boundaries.

### 01 A100 Development
Owns code, persistence, interfaces, tests and CI.

### 02 Daily Intelligence
Supplies timestamped market, industry, event and source-backed evidence inputs.

### 03 Strategy Research
Creates hypotheses, candidate rules and research scores. These remain unvalidated unless promoted through the formal validation record.

### 04 Backtest & Validation
Produces Backtest, Walk Forward and Shadow/Paper evidence and explicit acceptance or failure records.

### 05 Risk & Execution
Produces trade plans, portfolio-risk constraints and execution discipline after validation. No IROS helper bypasses this layer.

## CI

`.github/workflows/iros-ci.yml` runs:

1. Python compile check;
2. repository unit tests, including existing Autonomous Policy tests;
3. IROS CLI smoke test.

The workflow requires no market-data secret and does not run the daily Forward pipeline.

## Completion criterion for v1

IROS v1 is considered engineering-complete when:

- unit tests pass;
- CLI smoke test passes;
- Frozen V7 file is unchanged;
- existing Forward workflow is unchanged;
- IROS remains disconnected from production signal generation;
- documentation and end-to-end example are present.

Future live-data adapters, factor calibration and signal validation are separate versioned research work, not silent changes to v1.
