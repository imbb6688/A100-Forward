from __future__ import annotations

import json
import os
from pathlib import Path

from a100_iros.hithink_fundamentals import HiThinkFundamentalsClient


def main() -> None:
    key = os.environ.get("HITHINK_FINANCE_API_KEY")
    if not key:
        raise SystemExit("HITHINK_FINANCE_API_KEY secret is missing")

    ticker = os.environ.get("IROS_PROBE_TICKER", "600519.SH").strip().upper()
    period = os.environ.get("IROS_PROBE_PERIOD", "annual")
    limit = int(os.environ.get("IROS_PROBE_LIMIT", "5"))

    client = HiThinkFundamentalsClient(key)
    bundle = client.financials(ticker, period=period, limit=limit)
    payload = bundle.to_dict()

    out = Path("/mnt/data/iros_fundamentals_probe.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    summary = {
        "ticker": ticker,
        "period": period,
        "income_rows": len(bundle.income),
        "balance_sheet_rows": len(bundle.balance_sheet),
        "cash_flow_rows": len(bundle.cash_flow),
        "indicator_rows": len(bundle.indicators),
        "valuation_present": bool(bundle.valuation),
        "latest_income_report_date_ms": max(
            [int(x["report_date_ms"]) for x in bundle.income if x.get("report_date_ms") is not None],
            default=None,
        ),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
