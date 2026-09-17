from __future__ import annotations

import json
import re
from pathlib import Path
from typing import List

from .memory import ResearchSnapshot
from .models import ResearchObject
from .storage import load_research_object, save_research_object

_SAFE = re.compile(r"[^A-Za-z0-9._-]+")


def _safe(value: str) -> str:
    cleaned = _SAFE.sub("_", value.strip())
    if not cleaned:
        raise ValueError("identifier is empty after normalization")
    return cleaned


class ResearchRepository:
    """Filesystem-backed IROS repository.

    Layout:
      root/objects/<research_id>.json
      root/snapshots/<research_id>/<snapshot_id>.json

    Snapshots are immutable: an existing snapshot_id cannot be overwritten.
    """

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.objects_dir = self.root / "objects"
        self.snapshots_dir = self.root / "snapshots"
        self.objects_dir.mkdir(parents=True, exist_ok=True)
        self.snapshots_dir.mkdir(parents=True, exist_ok=True)

    def object_path(self, research_id: str) -> Path:
        return self.objects_dir / f"{_safe(research_id)}.json"

    def save(self, obj: ResearchObject) -> Path:
        path = self.object_path(obj.research_id)
        save_research_object(obj, path)
        return path

    def load(self, research_id: str) -> ResearchObject:
        return load_research_object(self.object_path(research_id))

    def exists(self, research_id: str) -> bool:
        return self.object_path(research_id).exists()

    def list_research_ids(self) -> List[str]:
        ids: List[str] = []
        for path in sorted(self.objects_dir.glob("*.json")):
            try:
                obj = load_research_object(path)
            except (OSError, ValueError, KeyError, json.JSONDecodeError):
                continue
            ids.append(obj.research_id)
        return ids

    def snapshot_path(self, research_id: str, snapshot_id: str) -> Path:
        return self.snapshots_dir / _safe(research_id) / f"{_safe(snapshot_id)}.json"

    def save_snapshot(self, snapshot: ResearchSnapshot) -> Path:
        path = self.snapshot_path(snapshot.research_id, snapshot.snapshot_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            raise FileExistsError(f"snapshot already exists: {snapshot.snapshot_id}")
        temp = path.with_suffix(path.suffix + ".tmp")
        temp.write_text(
            json.dumps(snapshot.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temp.replace(path)
        return path

    def load_snapshot(self, research_id: str, snapshot_id: str) -> ResearchSnapshot:
        path = self.snapshot_path(research_id, snapshot_id)
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("snapshot payload must be a JSON object")
        return ResearchSnapshot.from_dict(data)

    def list_snapshots(self, research_id: str) -> List[ResearchSnapshot]:
        folder = self.snapshots_dir / _safe(research_id)
        if not folder.exists():
            return []
        snapshots: List[ResearchSnapshot] = []
        for path in folder.glob("*.json"):
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                snapshots.append(ResearchSnapshot.from_dict(raw))
            except (OSError, ValueError, KeyError, json.JSONDecodeError):
                continue
        snapshots.sort(key=lambda item: (item.captured_at, item.snapshot_id))
        return snapshots
