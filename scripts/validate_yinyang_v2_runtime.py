from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

ALLOWED_SIGNAL = {"NONE", "GOLD", "SILVER", "BOUNCE"}
ALLOWED_STATE = {"RISK_OFF", "DEFENSIVE", "TRANSITION", "RECOVERY", "RISK_ON"}


def main() -> int:
    p = argparse.ArgumentParser(description="Validate A100 Yin-Yang v2 runtime outputs")
    p.add_argument("--manifest", required=True)
    p.add_argument("--latest", required=True)
    p.add_argument("--history", required=True)
    args = p.parse_args()

    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    latest = json.loads(Path(args.latest).read_text(encoding="utf-8"))
    hist = pd.read_csv(args.history)

    required_latest = {
        "trade_date", "yang_pct", "yin_pct", "position_tenths",
        "signal", "state", "status"
    }
    missing = required_latest - set(latest)
    if missing:
        raise ValueError(f"v2 latest missing fields: {sorted(missing)}")

    if str(latest["trade_date"]) != str(manifest.get("latest_trade_date")):
        raise ValueError(
            f"v2 date mismatch: latest={latest['trade_date']} manifest={manifest.get('latest_trade_date')}"
        )

    yang = float(latest["yang_pct"])
    yin = float(latest["yin_pct"])
    if not (0.0 <= yang <= 100.0 and 0.0 <= yin <= 100.0):
        raise ValueError("yin/yang must be within 0..100")
    if abs((yang + yin) - 100.0) > 0.11:
        raise ValueError(f"yin/yang must sum to 100, got {yin + yang}")

    pos = int(latest["position_tenths"])
    if not (0 <= pos <= 10):
        raise ValueError(f"position_tenths out of range: {pos}")
    if str(latest["signal"]) not in ALLOWED_SIGNAL:
        raise ValueError(f"unknown v2 signal: {latest['signal']}")
    if str(latest["state"]) not in ALLOWED_STATE:
        raise ValueError(f"unknown v2 state: {latest['state']}")
    if "RESEARCH_ONLY" not in str(latest["status"]):
        raise ValueError("v2 status must remain research-only")

    required_history = {
        "date", "v2_yang_pct", "v2_yin_pct", "v2_position_tenths",
        "v2_signal", "v2_state"
    }
    missing_hist = required_history - set(hist.columns)
    if missing_hist:
        raise ValueError(f"v2 history missing fields: {sorted(missing_hist)}")
    if hist.empty:
        raise ValueError("v2 history is empty")

    last_date = str(pd.to_datetime(hist.iloc[-1]["date"]).date())
    if last_date != str(latest["trade_date"]):
        raise ValueError(f"v2 history/latest mismatch: history={last_date} latest={latest['trade_date']}")

    print(
        "YIN-YANG V2 RUNTIME OK | "
        f"date={latest['trade_date']} | "
        f"yang={yang:.2f} | "
        f"position={pos}/10 | "
        f"signal={latest['signal']} | "
        f"state={latest['state']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
