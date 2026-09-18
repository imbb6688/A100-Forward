# A100 V8 Challenger — Adaptive Market Gate Research

## Hypothesis

Frozen V7 uses two overlapping market filters: `market_score >= 14` and a hard
full-trend gate requiring the internal equal-weight index and moving averages to
satisfy `index > MA20 > MA60 > MA120` with positive 20-session return. The hard
MA120 condition can admit signals late in a trend and may explain long dormant
periods followed by poorly timed entries.

## Controlled change

The first V8 challenger removes only the hard full-trend gate. It retains:

- pullback setup only;
- market score at least 14/20;
- industry score at least 9/12;
- V6 score at least 75;
- the Frozen V7 ExtraTrees model specification;
- the 2020–2022 model-training window;
- daily Top-2 selection and the existing signal-outcome definition.

The model is refit on the challenger training population because Frozen V7 never
produced rank scores outside its own hard gate.

The second challenger keeps the same security thresholds but replaces the hard
120-session ordering with a state gate: index above a rising MA20, positive
20-session return, and either established MA20/MA60 trend or an early recovery
above MA60 with a non-falling MA60. An exhaustion veto removes observations above
the 90th percentile of index/MA20 stretch or 20-session return. Both caps are
estimated only from 2020–2022; forward years cannot move them.

Before comparison, the research job must reproduce Frozen V7's saved eligibility
mask and rank scores exactly. A mismatch stops the job, preventing a faulty
baseline from making the challenger look better.

## Governance

This is a research challenger, not a production upgrade. Frozen V7 files and live
selection remain unchanged. Ranking-proxy evidence cannot promote V8. Promotion
requires point-in-time data, portfolio replay with overlap/cash constraints,
walk-forward acceptance, and shadow/paper evidence.

## Acceptance screen

The report applies the existing proxy thresholds: at least three folds and 100
trades, profitable-fold ratio at least 67%, median profit factor at least 1.10,
worst-fold profit factor at least 0.90, and worst drawdown no worse than 15%.
Passing is necessary but not sufficient for promotion.

The report treats 2023–2024 as retrospective selection/robustness evidence and
2025 as a retrospective locked-test convention. Because this V8 hypothesis was
formed after inspecting the 19 May 2026 signal, 2026 is diagnostic only and is
excluded from the acceptance calculation. None of these labels claims that the
strategy-selection process has a pristine, untouched historical test set.
