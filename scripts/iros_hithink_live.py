from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from a100_iros.hithink_live import build_live_bundle


def main() -> None:
    bundle = build_live_bundle(
        normalized_daily_path=Path('/mnt/data/A100_2020_2026_raw.parquet'),
        signal_path=Path('/mnt/data/forward/latest_signal.json'),
        manifest_path=Path('/mnt/data/hithink_manifest.json'),
        adjustment_path=Path('/mnt/data/A100_adjustment_factors.parquet'),
        output_dir=Path('/mnt/data/iros_live'),
    )
    print(json.dumps(bundle, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
