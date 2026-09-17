import tempfile
import unittest
from pathlib import Path

import pandas as pd
import numpy as np

from scripts.a100_pit_import import normalize
from scripts.a100_v7_walk_forward_proxy import build


class PITImportTests(unittest.TestCase):
    def test_valid_st_intervals(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "st.csv"
            pd.DataFrame([
                {"symbol": "600000.sh", "effective_from": "2020-01-01", "effective_to": "2020-02-01", "is_st": 1},
                {"symbol": "600000.sh", "effective_from": "2020-02-02", "effective_to": "2020-03-01", "is_st": 0},
            ]).to_csv(path, index=False)
            result = normalize("st", path)
        self.assertEqual(result["symbol"].tolist(), ["600000.SH", "600000.SH"])
        self.assertEqual(result["is_st"].tolist(), [True, False])

    def test_overlap_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "industry.csv"
            pd.DataFrame([
                {"symbol": "000001.SZ", "effective_from": "2020-01-01", "effective_to": "2020-03-01", "industry_code": "A"},
                {"symbol": "000001.SZ", "effective_from": "2020-02-01", "effective_to": "2020-04-01", "industry_code": "B"},
            ]).to_csv(path, index=False)
            with self.assertRaisesRegex(ValueError, "overlapping"):
                normalize("industry", path)

    def test_proxy_is_explicitly_not_graduation_evidence(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            for name in ("A100_v5_results", "A100_v6_results", "A100_v7_results"):
                (root / name).mkdir()
            dates = pd.to_datetime(["2023-01-03", "2024-01-03", "2025-01-03"]).astype("int64") // 1000
            np.savez_compressed(root / "A100_v5_results" / "A100_V5_context.npz", unique_dates=dates.to_numpy())
            np.savez_compressed(
                root / "A100_v6_results" / "A100_V6_features.npz",
                netR=np.array([1.0, -0.5, 0.8]),
                date_code_sig=np.array([0, 1, 2]),
                year=np.array([2023, 2024, 2025]),
            )
            np.savez_compressed(
                root / "A100_v7_results" / "A100_V7_rank_context.npz",
                rank_score=np.array([0.9, 0.8, 0.7]),
                broad=np.array([True, True, True]),
            )
            report = build(root)
        self.assertEqual(report["evidence_class"], "RANKING_PROXY")
        self.assertFalse(report["graduation_eligible"])
        self.assertEqual(len(report["folds"]), 3)


if __name__ == "__main__":
    unittest.main()
