from __future__ import annotations

import argparse
import html
import json
from pathlib import Path

import pandas as pd


def main() -> int:
    p = argparse.ArgumentParser(description="Render A100 Yin-Yang v2 research dashboard")
    p.add_argument("--latest", required=True)
    p.add_argument("--history", required=True)
    p.add_argument("--output", required=True)
    args = p.parse_args()

    latest = json.loads(Path(args.latest).read_text(encoding="utf-8"))
    hist = pd.read_csv(args.history).tail(20).copy()
    hist["date"] = pd.to_datetime(hist["date"]).dt.strftime("%Y-%m-%d")
    hist["v2_yang_pct"] = hist["v2_yang_pct"].map(lambda x: f"{float(x):.1f}%")
    hist["v2_yin_pct"] = hist["v2_yin_pct"].map(lambda x: f"{float(x):.1f}%")
    hist["v2_position_tenths"] = hist["v2_position_tenths"].map(lambda x: f"{int(x)}/10")

    rows = []
    for r in hist.itertuples():
        sig = "" if str(r.v2_signal) == "NONE" else html.escape(str(r.v2_signal))
        rows.append(
            "<tr>"
            f"<td>{html.escape(str(r.date))}</td>"
            f"<td>{html.escape(str(r.v2_yang_pct))}</td>"
            f"<td>{html.escape(str(r.v2_yin_pct))}</td>"
            f"<td>{html.escape(str(r.v2_position_tenths))}</td>"
            f"<td>{html.escape(str(r.v2_state))}</td>"
            f"<td><b>{sig}</b></td>"
            "</tr>"
        )

    doc = f"""<!doctype html>
<meta charset="utf-8">
<title>A100 Yin-Yang v2</title>
<style>
body{{font-family:system-ui,-apple-system,sans-serif;max-width:1000px;margin:36px auto;padding:0 20px;line-height:1.45}}
.cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin:20px 0}}
.card{{border:1px solid #ddd;border-radius:12px;padding:16px}}
.value{{font-size:28px;font-weight:700}}
table{{border-collapse:collapse;width:100%;margin-top:18px}}
th,td{{border-bottom:1px solid #ddd;padding:9px;text-align:left}}
small{{opacity:.72}}
</style>
<h1>A100 Yin-Yang Spectrum v2</h1>
<p><small>Research-only state-transition model. Not a production trading gate.</small></p>
<div class="cards">
<div class="card"><div>Trade date</div><div class="value">{html.escape(str(latest["trade_date"]))}</div></div>
<div class="card"><div>Yang</div><div class="value">{float(latest["yang_pct"]):.1f}%</div></div>
<div class="card"><div>Yin</div><div class="value">{float(latest["yin_pct"]):.1f}%</div></div>
<div class="card"><div>Position</div><div class="value">{int(latest["position_tenths"])}/10</div></div>
<div class="card"><div>State</div><div class="value">{html.escape(str(latest["state"]))}</div></div>
<div class="card"><div>Signal</div><div class="value">{html.escape(str(latest["signal"]))}</div></div>
</div>
<h2>Latest 20 sessions</h2>
<table>
<thead><tr><th>Date</th><th>Yang</th><th>Yin</th><th>Position</th><th>State</th><th>Signal</th></tr></thead>
<tbody>{''.join(rows)}</tbody>
</table>
"""
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(doc, encoding="utf-8")
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
