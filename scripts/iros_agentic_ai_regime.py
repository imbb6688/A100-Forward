from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from datetime import date, datetime
from pathlib import Path
from typing import Any, Mapping
from zoneinfo import ZoneInfo

from a100_iros.agentic_ai_inputs import build_market_proxy_payload, index_codes_from_config, load_regime_config
from a100_iros.agentic_ai_regime import AgenticAIRegimeState, RegimeSignal, build_agentic_ai_regime
from a100_iros.hithink_context import HiThinkContextClient


def _json_bytes(payload: Any, *, pretty: bool = False) -> bytes:
    return json.dumps(payload, ensure_ascii=False, indent=2 if pretty else None,
                      sort_keys=True, separators=None if pretty else (",", ":")).encode("utf-8")


def _atomic_write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as handle:
        temporary = Path(handle.name)
        handle.write(_json_bytes(payload, pretty=True) + b"\n")
    temporary.replace(path)


def _fingerprint(config: Mapping[str, Any], payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(_json_bytes({"config": config, "input": payload})).hexdigest()


def _append_history_once(path: Path, snapshot: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            previous = json.loads(line)
            if (previous.get("as_of"), previous.get("input_fingerprint")) == (
                snapshot.get("as_of"), snapshot.get("input_fingerprint")
            ):
                return
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(snapshot, ensure_ascii=False, sort_keys=True) + "\n")


def _constituents(config: Mapping[str, Any], api_key: str) -> dict[str, list[str]]:
    client = HiThinkContextClient(api_key)
    output: dict[str, list[str]] = {}
    for code in sorted(set(index_codes_from_config(config))):
        try:
            rows = client.index_constituents(code)
        except Exception as exc:
            print(
                f"warning: constituent fallback unavailable for {code}: {type(exc).__name__}",
                file=sys.stderr,
            )
            rows = []
        output[code] = sorted({
            str(row.get("thscode") or row.get("ts_code") or "").strip().upper()
            for row in rows if row.get("thscode") or row.get("ts_code")
        })
    return output


def _validate_input(payload: Mapping[str, Any], config: Mapping[str, Any]) -> list[RegimeSignal]:
    if payload.get("schema_version") != "A100-Agentic-AI-Regime-Input-v2":
        raise ValueError("input schema_version is missing or unsupported")
    if payload.get("weights") != config.get("weights"):
        raise ValueError("input weights must exactly match the governed configuration")
    as_of = str(payload.get("as_of") or "")
    if not as_of:
        raise ValueError("input as_of is required")
    try:
        observed_date = date.fromisoformat(as_of)
    except ValueError as exc:
        raise ValueError("input as_of must be an ISO date") from exc
    age_days = (datetime.now(ZoneInfo("Asia/Shanghai")).date() - observed_date).days
    max_age_days = int(config["quality_gates"]["max_calendar_age_days"])
    if age_days < 0 or age_days > max_age_days:
        raise ValueError(f"input is stale or future-dated: as_of={as_of}, age_days={age_days}")
    if not isinstance(payload.get("quality"), Mapping):
        raise ValueError("input quality metadata is required")
    provenance = payload.get("provenance")
    if not isinstance(provenance, Mapping) or not provenance.get("source"):
        raise ValueError("input provenance.source is required")
    rows = payload.get("signals")
    if not isinstance(rows, list):
        raise ValueError("input signals must be a list")
    signals = [RegimeSignal(**row) for row in rows]
    if any(signal.observed_at != as_of for signal in signals):
        raise ValueError("every signal must be observed on the input as_of date")
    if any(not signal.source for signal in signals):
        raise ValueError("every signal must include source provenance")
    return signals


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build the research-only Agentic AI regime snapshot")
    parser.add_argument("--config", default="config/agentic_ai_regime.json")
    parser.add_argument("--input", help="Use a prebuilt, governed input JSON")
    parser.add_argument("--daily", help="HiThink normalized full-market parquet")
    parser.add_argument("--manifest", help="HiThink validation manifest JSON")
    parser.add_argument("--input-output", default="state/iros-regime/inputs/latest.json")
    parser.add_argument("--output", default="state/iros-regime/latest.json")
    parser.add_argument("--history", default="state/iros-regime/history.jsonl")
    return parser


def main() -> int:
    args = _parser().parse_args()
    config = load_regime_config(args.config)
    if args.input:
        if args.daily or args.manifest:
            raise ValueError("choose either --input or --daily/--manifest")
        payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    else:
        if not args.daily or not args.manifest:
            raise ValueError("real market mode requires both --daily and --manifest")
        api_key = os.environ.get("HITHINK_FINANCE_API_KEY", "").strip()
        if not api_key:
            raise ValueError("HITHINK_FINANCE_API_KEY is required for index constituent fallback")
        manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
        payload = build_market_proxy_payload(
            normalized_daily_path=args.daily,
            manifest=manifest,
            config=config,
            index_constituents=_constituents(config, api_key),
        )

    signals = _validate_input(payload, config)
    gates = config["quality_gates"]
    snapshot = build_agentic_ai_regime(
        signals, weights=config["weights"], as_of=str(payload["as_of"]),
        min_coverage=float(gates["min_coverage"]),
        min_effective_coverage=float(gates["min_effective_coverage"]),
        input_fingerprint=_fingerprint(config, payload),
        data_quality=payload.get("quality", {}), provenance=payload.get("provenance", {}),
    ).to_dict()
    if snapshot["state"] == AgenticAIRegimeState.INSUFFICIENT_DATA.value:
        raise RuntimeError("regime quality gates failed: "
                           f"coverage={snapshot['coverage']}, effective_coverage={snapshot['effective_coverage']}")

    _atomic_write(Path(args.input_output), payload)
    _atomic_write(Path(args.output), snapshot)
    _append_history_once(Path(args.history), snapshot)
    print(json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
