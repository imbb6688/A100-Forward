import ast
import json
import tempfile
import unittest
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"

import sys
sys.path.insert(0, str(SCRIPTS))

from a100_runtime_checks import require_account_continuity, require_authoritative_state


class RecoveryGuardTests(unittest.TestCase):
    def test_authoritative_files_are_required(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = [Path(tmp) / name for name in ("account_state.json", "trade_log.csv", "equity_curve.csv")]
            for path in paths:
                path.write_text("x", encoding="utf-8")
            require_authoritative_state(paths)
            paths[1].unlink()
            with self.assertRaisesRegex(RuntimeError, "trade_log.csv"):
                require_authoritative_state(paths)

    def test_account_continuity_accepts_only_current_or_next_session(self):
        dates = ["2026-09-15", "2026-09-16", "2026-09-17"]
        require_account_continuity(
            {"last_processed_date": "2026-09-16", "last_processed_date_code": 1},
            dates,
        )
        with self.assertRaisesRegex(RuntimeError, "gap"):
            require_account_continuity(
                {"last_processed_date": "2026-09-15", "last_processed_date_code": 0},
                dates,
            )

    def test_account_continuity_rejects_reindexed_history(self):
        with self.assertRaisesRegex(RuntimeError, "date/index"):
            require_account_continuity(
                {"last_processed_date": "2026-09-16", "last_processed_date_code": 0},
                ["2026-09-15", "2026-09-16"],
            )


class SourceContractTests(unittest.TestCase):
    def test_forward_job_is_main_only_and_checks_outputs(self):
        workflow = (ROOT / ".github/workflows/a100-forward.yml").read_text(encoding="utf-8")
        self.assertIn("if: github.ref == 'refs/heads/main'", workflow)
        self.assertIn("test -s /mnt/data/hithink_manifest.json", workflow)

    def test_account_uses_date_symbol_cluster_index(self):
        account = (SCRIPTS / "a100_account_v1.py").read_text(encoding="utf-8")
        self.assertIn("clusters[t, sid]", account)
        self.assertNotIn("clusters[raw]", account)
        self.assertIn("require_account_continuity", account)
        self.assertIn("require_authoritative_state", account)

    def test_downloader_fully_decodes_and_resets_partial(self):
        source = (SCRIPTS / "download_hithink.py").read_text(encoding="utf-8")
        self.assertIn("batch.validate(full=True)", source)
        self.assertIn("tmp.unlink(missing_ok=True)", source)
        self.assertIn("stderr=subprocess.PIPE", source)

    def test_valid_parquet_decodes_complete_file(self):
        source_path = SCRIPTS / "download_hithink.py"
        tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
        function = next(
            node for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "valid_parquet"
        )
        module = ast.Module(body=[function], type_ignores=[])
        namespace = {"Path": Path, "pq": pq}
        exec(compile(ast.fix_missing_locations(module), str(source_path), "exec"), namespace)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sample.parquet"
            pq.write_table(pa.table({"x": list(range(1000))}), path, row_group_size=100)
            self.assertTrue(namespace["valid_parquet"](path))
            path.write_bytes(path.read_bytes()[:100])
            self.assertFalse(namespace["valid_parquet"](path))


if __name__ == "__main__":
    unittest.main()
