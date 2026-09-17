from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from .memory import ResearchSnapshot, compare_snapshots
from .models import ResearchObject, SecurityResearchCard
from .repository import ResearchRepository


def _snapshot_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _print(data: object) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="a100-iros", description="A100 Investment Research Operating System")
    parser.add_argument("--root", default="state/iros", help="research repository root")
    sub = parser.add_subparsers(dest="command", required=True)

    new_cmd = sub.add_parser("new", help="create a research object")
    new_cmd.add_argument("research_id")
    new_cmd.add_argument("ticker")
    new_cmd.add_argument("--company", default="")

    show_cmd = sub.add_parser("show", help="show a research object")
    show_cmd.add_argument("research_id")

    sub.add_parser("list", help="list research ids")

    snap_cmd = sub.add_parser("snapshot", help="capture immutable research snapshot")
    snap_cmd.add_argument("research_id")
    snap_cmd.add_argument("--snapshot-id", default="")
    snap_cmd.add_argument("--note", default="")

    snaps_cmd = sub.add_parser("snapshots", help="list snapshots")
    snaps_cmd.add_argument("research_id")

    diff_cmd = sub.add_parser("diff", help="compare two research snapshots")
    diff_cmd.add_argument("research_id")
    diff_cmd.add_argument("before_snapshot_id")
    diff_cmd.add_argument("after_snapshot_id")

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    repo = ResearchRepository(Path(args.root))

    if args.command == "new":
        if repo.exists(args.research_id):
            raise SystemExit(f"research object already exists: {args.research_id}")
        obj = ResearchObject(
            research_id=args.research_id,
            security=SecurityResearchCard(ticker=args.ticker, company_name=args.company),
        )
        repo.save(obj)
        _print(obj.to_dict())
        return 0

    if args.command == "show":
        _print(repo.load(args.research_id).to_dict())
        return 0

    if args.command == "list":
        _print({"research_ids": repo.list_research_ids()})
        return 0

    if args.command == "snapshot":
        obj = repo.load(args.research_id)
        snap = ResearchSnapshot.capture(
            obj,
            snapshot_id=args.snapshot_id or _snapshot_id(),
            note=args.note,
        )
        repo.save_snapshot(snap)
        _print(snap.to_dict())
        return 0

    if args.command == "snapshots":
        _print({"snapshots": [item.to_dict() for item in repo.list_snapshots(args.research_id)]})
        return 0

    if args.command == "diff":
        before = repo.load_snapshot(args.research_id, args.before_snapshot_id)
        after = repo.load_snapshot(args.research_id, args.after_snapshot_id)
        _print(compare_snapshots(before, after).to_dict())
        return 0

    raise SystemExit(f"unsupported command: {args.command}")
