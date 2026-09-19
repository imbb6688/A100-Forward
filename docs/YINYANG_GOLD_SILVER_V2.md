# Yin-Yang / Gold-Silver Finger v2 design

## Why v1 is rejected for signal semantics

The user-provided Tonghuashun sample (2026-08-25 through 2026-09-18) demonstrates that:

1. Yang Spectrum, suggested position, and Finger signal are separate outputs.
2. A high Yang value is not sufficient for a Gold Finger.
3. Gold/Silver/Bounce behave like transition events, not static score buckets.
4. The v1 composite score can remain directionally correlated with Yang Spectrum while still misclassifying every labeled Finger event in the sample.

Therefore v1 remains useful only as a generic market-state research score. Its Gold/Silver labels are deprecated for semantic comparison with Tonghuashun.

## v2 architecture

Three independent heads share PIT market features but have separate targets:

### Head A — Yang Spectrum
Continuous 0..100 breadth/sentiment measure. Candidate feature families:
- advancer/decliner breadth and breadth acceleration
- percent above MA5/10/20/60
- new-high/new-low balance
- limit-up/down and strong/weak tail breadth
- median return and cross-sectional dispersion
- turnover expansion and declining-volume breadth
- sector participation / leadership diffusion

Do not define Yang as the composite regime score.

### Head B — Position
Ordinal 0..10 risk-budget state. It must be separately calibrated from Yang and include persistence/hysteresis.

### Head C — Signal state machine
Discrete events: GOLD, SILVER, BOUNCE, NONE. Candidate logic should use state transitions and derivatives, not score levels alone:
- prior-state context
- 1d/3d change in Yang and breadth
- reversal from local extremes
- trend confirmation / failure
- liquidity confirmation
- leadership diffusion
- hysteresis and cooldown

## Governance

The vendor formula is proprietary and unknown. The labeled screenshots are calibration evidence, not proof of the original formula.

Do not promote v2 to Frozen V7 or production gating until:
Backtest -> Walk Forward -> Shadow/Paper -> explicit acceptance.

The first calibration sample contains only 19 sessions and must not be used as a standalone training set. It is a falsification/constraint set. Additional labeled historical screenshots should be added before supervised calibration.
