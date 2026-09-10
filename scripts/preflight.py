from pathlib import Path
import ast

ROOT=Path(__file__).resolve().parent
required=[
    "download_hithink.py",
    "a100_io.py",
    "a100_canonical_prep.py",
    "a100_v5_pit_proxy.py",
    "a100_v6_feature_prep_forward.py",
    "a100_v6_train_score_forward.py",
    "a100_v7_forward_ranker.py",
    "a100_forward_live.py",
    "a100_account_v1.py",
    "validate_publish.py",
]
missing=[x for x in required if not (ROOT/x).exists()]
if missing: raise SystemExit(f"missing scripts: {missing}")
for n in required:
    ast.parse((ROOT/n).read_text(encoding="utf-8"),filename=n)

for n in ["a100_canonical_prep.py","a100_v5_pit_proxy.py","a100_v6_feature_prep_forward.py"]:
    tree=ast.parse((ROOT/n).read_text(encoding="utf-8"))
    imports=[]
    for node in ast.walk(tree):
        if isinstance(node,ast.ImportFrom):
            imports.append(node.module)
    if "a100_io" not in imports:
        raise SystemExit(f"{n}: audited a100_io import missing")
    if "parquet_minread" in imports:
        raise SystemExit(f"{n}: stale parquet_minread import")
print("A100 PRE-FLIGHT OK")
