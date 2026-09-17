from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, Sequence

import pyarrow.parquet as pq


def _fingerprint(path: Path) -> str | None:
    if not path.exists() or path.stat().st_size == 0:
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _pit_contract(path: Path, required: set[str]) -> tuple[bool, list[str]]:
    if not path.exists() or path.stat().st_size == 0:
        return False, sorted(required)
    try:
        names = set(pq.read_schema(path).names)
    except Exception:
        return False, sorted(required)
    missing = sorted(required - names)
    return not missing, missing


def inventory(root: Path) -> Dict[str, Any]:
    specs = {
        "price_adjustment": root / "A100_adjustment_factors.parquet",
        "st_risk_warning_history": root / "pit" / "st_risk_warning_history.parquet",
        "industry_membership_history": root / "pit" / "industry_membership_history.parquet",
    }
    datasets: Dict[str, Any] = {}
    contracts = {
        "st_risk_warning_history": {"symbol", "effective_from", "effective_to", "is_st"},
        "industry_membership_history": {"symbol", "effective_from", "effective_to", "industry_code"},
    }
    for name, path in specs.items():
        digest = _fingerprint(path)
        contract_ok, missing_columns = (True, []) if name == "price_adjustment" and digest else _pit_contract(path, contracts.get(name, set()))
        complete = bool(digest) and contract_ok
        datasets[name] = {
            "status": "COMPLETE" if complete else "MISSING_OR_INVALID_PIT_CONTRACT",
            "point_in_time_safe": complete,
            "path": str(path),
            "sha256": digest,
            "size_bytes": path.stat().st_size if digest else 0,
            "missing_columns": missing_columns,
        }
    datasets["capital_flow"] = {
        "status": "UNAVAILABLE_UPSTREAM",
        "point_in_time_safe": False,
        "path": None,
        "sha256": None,
        "size_bytes": 0,
    }
    return {"schema_version": 1, "datasets": datasets}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("/mnt/data"))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    report = inventory(args.root)
    output = args.output or args.root / "validation" / "data_inventory.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
