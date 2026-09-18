from __future__ import annotations
import argparse, json
from pathlib import Path
from a100_iros.agentic_ai_regime import RegimeSignal, build_agentic_ai_regime

def main() -> int:
    p=argparse.ArgumentParser()
    p.add_argument("--input", default="state/iros-regime/inputs/latest.json")
    p.add_argument("--output", default="state/iros-regime/latest.json")
    args=p.parse_args()
    src=Path(args.input)
    payload=json.loads(src.read_text(encoding="utf-8")) if src.exists() else {"signals":[]}
    signals=[RegimeSignal(**row) for row in payload.get("signals",[])]
    snap=build_agentic_ai_regime(signals, weights=payload.get("weights"), as_of=payload.get("as_of"))
    out=Path(args.output); out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(snap.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    hist=out.parent/"history.jsonl"
    with hist.open("a", encoding="utf-8") as f: f.write(json.dumps(snap.to_dict(), ensure_ascii=False)+"\n")
    print(json.dumps(snap.to_dict(), ensure_ascii=False, indent=2))
    return 0

if __name__=="__main__": raise SystemExit(main())
