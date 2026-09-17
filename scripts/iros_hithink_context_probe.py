from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from a100_iros.hithink_context import HiThinkContextClient


def main() -> None:
    key = os.environ.get("HITHINK_FINANCE_API_KEY")
    if not key:
        raise SystemExit("HITHINK_FINANCE_API_KEY secret is missing")

    client = HiThinkContextClient(key)
    catalog = client.index_catalog("industry")
    first_index = catalog[0] if catalog else {}
    index_code = str(first_index.get("thscode") or "")
    constituents = client.index_constituents(index_code) if index_code else []
    anomaly = client.anomaly_for_stocks(["600519.SH"])
    dragon = client.dragon_tiger(board_type="all")
    limit_up = client.limit_pool("up")

    payload = {
        "industry_catalog_count": len(catalog),
        "sample_industry_index": first_index,
        "sample_constituent_count": len(constituents),
        "sample_constituents": constituents[:5],
        "anomaly": anomaly,
        "dragon_tiger": dragon,
        "limit_up": limit_up,
    }
    out = Path(os.environ.get("IROS_CONTEXT_PROBE_OUTPUT", "iros_context_probe.json"))
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "industry_catalog_count": len(catalog),
        "sample_industry_index": first_index,
        "sample_constituent_count": len(constituents),
        "anomaly_keys": sorted(anomaly.keys()),
        "dragon_tiger_keys": sorted(dragon.keys()),
        "limit_up_keys": sorted(limit_up.keys()),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
