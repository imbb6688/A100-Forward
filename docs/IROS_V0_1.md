# A100-IROS v0.1 — Foundation Contract

## Purpose
A100 Investment Research Operating System (IROS) is a research-only layer for structuring market, industry, company, event, technical, positioning, thesis, and risk evidence.

## Non-negotiable boundary
IROS v0.1 MUST NOT modify, retune, or implicitly influence the Frozen V7 forward ranker. Any IROS-derived signal remains research-only until it passes the normal A100 validation path (research -> backtest -> walk-forward -> shadow/paper -> acceptance).

## Core domain objects
- `ResearchObject`: versionable research container with state history.
- `SecurityResearchCard`: structured security-level evidence container.
- `Thesis`: bull/base/bear cases, assumptions, invalidation, priced-in assessment, and variant perception.
- `DecisionState`: explicit research-to-review lifecycle state machine.
- `EvidenceItem`: typed statement carrying provenance and confidence.

## Evidence taxonomy
- FACT
- EVIDENCE
- INFERENCE
- HYPOTHESIS
- CANDIDATE_RULE
- VALIDATED_RULE

`CANDIDATE_RULE` must never be treated as `VALIDATED_RULE` without evidence from the A100 validation layer.

## Decision states
`DISCOVERED -> RESEARCHING -> WATCHLIST/CANDIDATE -> VALIDATION -> TRADE_READY -> ACTIVE_POSITION -> EXIT -> POST_REVIEW -> ARCHIVED`

Alternative branches include `REJECTED`, `INVALIDATED`, and `REDUCE`. Direct state jumps are rejected by code.

## Persistence
Research objects use schema-versioned JSON. v0.1 storage is atomic at the file level and preserves state history and typed evidence.

## Next planned increments
1. Research repository/index for multiple securities.
2. Thesis delta/history tracking.
3. Market Regime object.
4. Industry Research object.
5. Event Intelligence object.
6. Research score as a research-priority signal only.
7. Interfaces into Daily Intelligence and Backtest/Validation.

## Explicitly out of scope for v0.1
- Live trading
- Automatic order generation
- Changes to V7 ranking weights
- New production signals
- Position sizing changes
- Workflow schedule changes
