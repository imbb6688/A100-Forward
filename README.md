# A100 Forward Bridge — HiThink → GitHub Actions → GitHub Pages

This repository runs the **frozen A100 V7 forward-test pipeline** after the China A-share close. It never exposes the HiThink API key to output files or Pages.

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
Repository → **Settings → Pages → Build and deployment → Source: GitHub Actions**.

### 5. Run once manually
Repository → **Actions → A100 Forward Daily → Run workflow**.

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
