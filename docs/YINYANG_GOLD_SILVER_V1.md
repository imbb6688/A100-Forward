# A100 Yin-Yang Spectrum + Gold/Silver Finger v1

Status: **research-only / unvalidated heuristic**.

This module converts full-market A-share daily data into a market-state fingerprint inspired by the behavioral ideas behind "yin-yang spectrum / gold finger / silver finger" style market sentiment displays. It does **not** claim to reproduce any proprietary vendor formula.

## Components

The composite score is 0..100:

- Breadth 25%
- Trend 20%
- Momentum 15%
- Liquidity 15%
- Volatility 10%
- Leadership 10%
- Capital confirmation 5%

State mapping:

- 0-25 RISK_OFF
- 25-40 DEFENSIVE
- 40-55 TRANSITION
- 55-70 RECOVERY
- 70-100 RISK_ON

Yin = 100 - composite score. Yang = composite score.

## Silver Finger

An early recovery transition candidate. Current v1 condition:

- previous score < 40
- current score >= 45
- 3-session score delta > 5
- 3-session breadth average >= 50

## Gold Finger

A confirmed risk-on candidate. Current v1 condition:

- score >= 60
- 3-session average score >= 55
- trend >= 55
- breadth >= 55
- leadership >= 50
- liquidity >= 45

These are candidate rules, not production signals.

## Governance

The module is isolated under IROS. It must not modify Frozen V7 or become a live gate until it passes:

Backtest -> Walk Forward -> Shadow/Paper -> explicit acceptance.

## CLI

```bash
python -m scripts.iros_yinyang_fingerprint \
  --daily /mnt/data/A100_2020_2026_raw.parquet \
  --output /mnt/data/state/iros-regime/yinyang/latest.json \
  --history /mnt/data/state/iros-regime/yinyang/history.csv
```

The history CSV is intended for the next step: ablation, transition analysis, and comparison against Frozen V7 signal droughts such as 2026-05-19 through 2026-09-18.
