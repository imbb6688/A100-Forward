from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


def load(path: str):
    p = Path(path)
    if not p.exists() or p.stat().st_size == 0:
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def main() -> int:
    p = argparse.ArgumentParser(description="Build sanitized A100 research status")
    p.add_argument("--manifest", required=True)
    p.add_argument("--yinyang-v2")
    p.add_argument("--output", required=True)
    args = p.parse_args()

    manifest = load(args.manifest) or {}
    yy = load(args.yinyang_v2) if args.yinyang_v2 else None
    market_date = str(manifest.get("latest_trade_date") or "")
    yy_date = str(yy.get("trade_date") or "") if yy else ""
    yy_aligned = bool(yy and market_date and yy_date == market_date)

    payload = {
        "schema_version": "A100-RESEARCH-STATUS-v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "market_date": market_date or None,
        "full_market": bool(manifest.get("full_market")),
        "yinyang_v2": {
            "available": yy_aligned,
            "date_aligned": yy_aligned,
            "stale_snapshot_present": bool(yy is not None and not yy_aligned),
            "trade_date": yy.get("trade_date") if yy else None,
            "yang_pct": yy.get("yang_pct") if yy else None,
            "yin_pct": yy.get("yin_pct") if yy else None,
            "position_tenths": yy.get("position_tenths") if yy else None,
            "signal": yy.get("signal") if yy else None,
            "state": yy.get("state") if yy else None,
            "status": yy.get("status") if yy else None,
        },
        "governance": {
            "research_only": True,
            "modifies_frozen_v7": False,
            "broker_orders": False,
        },
    }
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
