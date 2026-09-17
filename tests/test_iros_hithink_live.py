import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from a100_iros.hithink_live import build_live_bundle


class HiThinkLiveAdapterTests(unittest.TestCase):
    def test_build_live_bundle_from_provider_shaped_inputs(self) -> None:
        dates = pd.date_range('2026-06-01', periods=70, freq='B')
        rows = []
        for sid in range(1200):
            ticker = f'{sid:06d}.SZ'
            base = 10.0 + sid / 5000.0
            for i, dt in enumerate(dates):
                close = base * (1.0 + 0.001 * i + 0.0001 * (sid % 7))
                rows.append({
                    'ts_code': ticker,
                    'trade_date': int(dt.value // 1000),
                    'open': close * 0.995,
                    'high': close * 1.01,
                    'low': close * 0.99,
                    'close': close,
                    'volume': 100000 + sid,
                    'amount': (100000 + sid) * close,
                })
        daily = pd.DataFrame(rows)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            daily_path = root / 'daily.parquet'
            adj_path = root / 'adj.parquet'
            signal_path = root / 'latest_signal.json'
            manifest_path = root / 'manifest.json'
            output_dir = root / 'out'

            pq.write_table(pa.Table.from_pandas(daily, preserve_index=False), daily_path)
            pq.write_table(
                pa.Table.from_pydict({
                    'thscode': ['000001.SZ'],
                    'ticker': ['000001'],
                    'ex_date_ms': [int(dates[-5].value // 1_000_000)],
                    'dividend_per_share': [0.1],
                    'per_share_bonus': [0.0],
                    'allotment_ratio': [0.0],
                    'allotment_price': [0.0],
                    'currency': ['CNY'],
                }),
                adj_path,
            )
            trade_date = dates[-1].strftime('%Y-%m-%d')
            signal_path.write_text(json.dumps({
                'latest_trade_date': trade_date,
                'market_gate': True,
                'candidate_count': 3,
                'top2': [
                    {'rank': 1, 'symbol': '000001.SZ', 'v7_rank_score': 0.8},
                    {'rank': 2, 'symbol': '000002.SZ', 'v7_rank_score': 0.7},
                ],
            }), encoding='utf-8')
            manifest_path.write_text(json.dumps({
                'latest_trade_date': trade_date,
                'full_market': True,
                'complete': True,
                'data_valid': True,
                'latest_rows': 1200,
                'symbols': 1200,
                'completeness_ratio': 1.0,
                'source': 'HiThink synthetic contract fixture',
            }), encoding='utf-8')

            bundle = build_live_bundle(
                normalized_daily_path=daily_path,
                signal_path=signal_path,
                manifest_path=manifest_path,
                adjustment_path=adj_path,
                output_dir=output_dir,
            )

            self.assertEqual(bundle['trade_date'], trade_date)
            self.assertEqual(bundle['frozen_v7']['top2_count'], 2)
            self.assertEqual(bundle['manifest']['symbols'], 1200)
            self.assertTrue(bundle['governance']['research_only'])
            self.assertFalse(bundle['governance']['modifies_frozen_v7'])
            self.assertEqual(len(bundle['research_objects']), 2)
            self.assertTrue((output_dir / 'live_bundle.json').exists())
            self.assertEqual(len(list((output_dir / 'objects').glob('*.json'))), 2)
            self.assertGreater(bundle['market_metrics']['above_ma20_ratio'], 0.9)
            self.assertEqual(bundle['market_regime']['validation_status'], 'UNVALIDATED_RESEARCH_HEURISTIC')


if __name__ == '__main__':
    unittest.main()
