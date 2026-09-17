from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from a100_iros.enrichment import (
    EnrichmentTarget,
    IROSEnrichmentOrchestrator,
    targets_from_frozen_signal,
    targets_from_watchlist,
)
from a100_iros.hithink_context import HiThinkContextClient
from a100_iros.hithink_fundamentals import HiThinkFundamentalsClient
from a100_iros.repository import ResearchRepository


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _watchlist_rows(payload: Any) -> List[Dict[str, Any]]:
    if isinstance(payload, list):
        return [dict(row) for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        for key in ("watchlist", "securities", "items"):
            value = payload.get(key)
            if isinstance(value, list):
                return [dict(row) for row in value if isinstance(row, dict)]
    raise ValueError("watchlist JSON must be a list or contain watchlist/securities/items")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build persistent IROS Security Research Files")
    parser.add_argument("--daily", default="/mnt/data/A100_2020_2026_raw.parquet")
    parser.add_argument("--signal", default="/mnt/data/forward/latest_signal.json")
    parser.add_argument("--watchlist")
    parser.add_argument("--root", default="/mnt/data/iros_research")
    parser.add_argument("--as-of")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    key = os.environ.get("HITHINK_FINANCE_API_KEY")
    if not key:
        raise SystemExit("HITHINK_FINANCE_API_KEY secret is missing")

    targets: List[EnrichmentTarget] = []
    signal_path = Path(args.signal)
    if signal_path.exists():
        targets.extend(targets_from_frozen_signal(_read_json(signal_path)))
    if args.watchlist:
        targets.extend(targets_from_watchlist(_watchlist_rows(_read_json(Path(args.watchlist)))))
    if not targets:
        generated_at = datetime.now(timezone.utc).isoformat()
        summary = {
            "schema_version": "A100-IROS-ENRICHMENT-RUN-v1",
            "generated_at": generated_at,
            "as_of": args.as_of,
            "results": [],
            "complete": 0,
            "failed": 0,
            "status": "SKIPPED_NO_TARGETS",
            "governance": {
                "research_only": True,
                "modifies_frozen_v7": False,
                "generates_orders": False,
                "auto_promotes_state": False,
            },
        }
        root = Path(args.root)
        root.mkdir(parents=True, exist_ok=True)
        target = root / "latest_enrichment_run.json"
        temp = target.with_suffix(".json.tmp")
        temp.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(target)
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return

    orchestrator = IROSEnrichmentOrchestrator(
        repository=ResearchRepository(args.root),
        normalized_daily_path=args.daily,
        fundamentals_client=HiThinkFundamentalsClient(key),
        context_client=HiThinkContextClient(key),
    )
    summary = orchestrator.run(targets, as_of=args.as_of)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if summary["failed"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
