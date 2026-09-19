# A100 Forward Bridge — HiThink → GitHub Actions → GitHub Pages

This repository runs the **frozen A100 V7 forward-test pipeline** after the China A-share close. It never exposes the HiThink API key to output files or Pages.

## A100 Investment Research Operating System (IROS)

The repository also contains **A100-IROS**, an isolated research-only operating layer for structured market, industry, security, event, thesis, validation and risk research.

IROS does **not** modify Frozen V7, does not retune V7 with forward data, and does not generate broker orders. Research heuristics remain unvalidated until the formal Backtest → Walk Forward → Shadow/Paper evidence chain is complete and explicitly accepted.

See:

- `docs/IROS_V1.md` — v1 architecture and governance contract.
- `docs/IROS_ENRICHMENT_V1.md` — persistent Security Research File orchestration.
- `examples/iros_end_to_end.py` — synthetic end-to-end example.
- `.github/workflows/iros-ci.yml` — isolated IROS validation workflow.
- `scripts/iros_enrich.py` — enrich Frozen V7/Watchlist securities with real HiThink market, industry, fundamentals, valuation and event context.
- `docs/GRADUATION_GATE_V1.md` — evidence thresholds for Data → Walk Forward → Paper → Risk → Graduation.
- `scripts/a100_graduation_gate.py` — fail-closed graduation evaluator; it never enables live or broker orders.
- `docs/PIT_AND_WALK_FORWARD_EVIDENCE.md` — verified upstream PIT boundary, canonical import contract and annual Frozen V7 proxy evidence.


## Yin-Yang Spectrum / Gold-Silver Finger v2

A100 now includes a **research-only** market-state transition model inspired by the behavioral structure of Yin-Yang Spectrum / Gold Finger / Silver Finger displays.

The v2 model keeps three outputs separate:

- **Yang Spectrum** — continuous 0..100 market breadth/sentiment estimate.
- **Position** — ordinal 0..10 research exposure state with hysteresis.
- **Signal state machine** — `GOLD`, `SILVER`, `BOUNCE`, or `NONE`.

The first user-provided Tonghuashun calibration sample covers 19 sessions from 2026-08-25 through 2026-09-18. The current v2 signal state machine matches all 19 labeled signal states in that calibration set, but this is **in-sample calibration evidence, not proof of the proprietary vendor formula and not production validation**.

Full-history research evidence (2020-01-03 through 2026-09-18) is stored under:

- `state/iros-regime/yinyang-v2/latest.json`
- `state/iros-regime/yinyang-v2/history.csv`
- `state/iros-regime/yinyang-v2/vendor_alignment.json`
- `state/iros-regime/yinyang-v2/event_validation.json`

When the daily research path succeeds, GitHub Pages also publishes:

- `research/yinyang-v2/` — human-readable v2 dashboard.
- `research/yinyang-v2/latest.json`
- `research/yinyang-v2/history.csv`
- `research/status.json` — sanitized research availability/status.

The v1 Gold/Silver semantics are deprecated; v1 remains only a generic market-regime research baseline. Yin-Yang v2 does not modify Frozen V7 or broker execution.

## What it does

1. Authenticates to HiThink Financial-API with the repository secret `HITHINK_FINANCE_API_KEY`.
2. Downloads the official full-market `daily-k` dump and `adjustment-factors` dump.
3. Fails closed if the latest market day has fewer than 4,500 A-share rows.
4. Rebuilds the historical A100 feature chain from raw data.
5. Uses the frozen V7 ranker specification (`ExtraTrees`, depth=4, min leaf=40, seed=17).
6. Generates the latest close signal, at most Top 2 candidates.
7. Publishes only sanitized outputs to GitHub Pages:
   - `latest_signal.json`
   - `latest_candidates.csv`
   - `data_manifest.json`
   - human-readable `index.html`

## One-time setup

### 1. Create a GitHub repository
Create a new repository, preferably named `a100-forward`. Public is easiest if you want ChatGPT to read the result URL without a GitHub connector. **Do not commit any API key.**

### 2. Upload this package
Upload all files/folders from this package to the repository root.

### 3. Add the HiThink secret
GitHub repository → **Settings → Secrets and variables → Actions → New repository secret**

Name exactly:

`HITHINK_FINANCE_API_KEY`

Paste your HiThink key there. It will not be written to the repository or Pages.

### 4. Enable GitHub Pages
GitHub repository → **Settings → Pages → Build and deployment → Source: GitHub Actions**.

### 5. Run once manually
GitHub repository → **Actions → A100 Forward Daily → Run workflow**.

The scheduled run is configured for **15:35 Asia/Shanghai, Monday–Friday**. This gives HiThink time to publish the daily dump and leaves ~10 minutes before the ChatGPT 15:45 A100 task.

## Expected public URLs
If the repository is `https://github.com/USERNAME/a100-forward`, Pages is normally:

`https://USERNAME.github.io/a100-forward/`

Machine-readable status:

`https://USERNAME.github.io/a100-forward/latest_signal.json`

Once that URL exists, provide only the Pages URL to ChatGPT. **Never provide the HiThink key.**

## Fail-closed behavior
No formal signal is produced if:
- the HiThink secret is missing;
- the signed dump cannot be downloaded;
- the latest day has implausibly few market rows;
- the pipeline dates disagree;
- the model fails to rebuild.

## Frozen model rule
Forward data must not be used to retune the V7 model. The model's training period and specification are fixed. Future model changes must be versioned as a new research project rather than silently changing A100 Forward.
