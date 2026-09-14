import ast
import json
from datetime import datetime, timezone
from pathlib import Path
import subprocess
import sys
import uuid
import types
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from a100_runtime_checks import expected_session, require_session, require_account_continuity


class RuntimeChecks(unittest.TestCase):
    def test_china_date_after_close(self):
        self.assertEqual(expected_session(datetime(2026, 9, 14, 8, tzinfo=timezone.utc)), '2026-09-14')

    def test_before_close_rejected(self):
        with self.assertRaises(RuntimeError):
            expected_session(datetime(2026, 9, 14, 6, tzinfo=timezone.utc))

    def test_weekend_rejected(self):
        with self.assertRaises(RuntimeError):
            expected_session(datetime(2026, 9, 13, 8, tzinfo=timezone.utc))

    def test_stale_session_rejected(self):
        with self.assertRaises(RuntimeError):
            require_session('2026-09-09', '2026-09-14')

    def test_current_session_accepted(self):
        require_session('2026-09-14', '2026-09-14')

    def test_account_gap_rejected(self):
        with self.assertRaises(RuntimeError):
            require_account_continuity({'last_processed_date': '2026-09-09', 'last_processed_date_code': 0},
                                       ['2026-09-09', '2026-09-10', '2026-09-11'])

    def test_account_index_shift_rejected(self):
        with self.assertRaises(RuntimeError):
            require_account_continuity({'last_processed_date': '2026-09-09', 'last_processed_date_code': 0},
                                       ['2026-09-08', '2026-09-09'])

    def test_normal_next_day_and_repeat_accepted(self):
        state = {'last_processed_date': '2026-09-09', 'last_processed_date_code': 0}
        require_account_continuity(state, ['2026-09-09', '2026-09-10'])
        require_account_continuity(state, ['2026-09-09'])


class DownloadChecks(unittest.TestCase):
    def setUp(self):
        # Execute the actual transport functions with isolated network/Parquet doubles.
        tree = ast.parse((ROOT / 'scripts/download_hithink.py').read_text(encoding='utf-8'))
        functions = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'fetch']
        self.ns = {'presigned': Mock(return_value='https://example.invalid/signed'),
                   'requests': types.SimpleNamespace(get=Mock()),
                   'validate_parquet': Mock(), 'time': types.SimpleNamespace(sleep=Mock()),
                   'print': Mock()}
        exec(compile(ast.Module(body=functions, type_ignores=[]), '<downloader>', 'exec'), self.ns)
        self.temp = ROOT.parent / ('download-test-' + uuid.uuid4().hex)
        self.temp.mkdir()
        self.dest = self.temp / 'data.parquet'
        self.addCleanup(self.cleanup)

    def cleanup(self):
        self.dest.unlink(missing_ok=True)
        self.dest.with_suffix('.parquet.part').unlink(missing_ok=True)
        self.temp.rmdir()

    def response(self, chunks, length=None, status=200):
        response = Mock(status_code=status, headers={} if length is None else {'Content-Length': str(length)})
        response.iter_content.return_value = chunks
        context = Mock()
        context.__enter__ = Mock(return_value=response)
        context.__exit__ = Mock(return_value=False)
        return context

    def test_validated_download_replaces_destination(self):
        self.ns['requests'].get.return_value = self.response([b'complete'], 8)
        self.assertEqual(self.ns['fetch']('daily', self.dest, 'test', attempts=1), 8)
        self.assertEqual(self.dest.read_bytes(), b'complete')
        self.ns['validate_parquet'].assert_called_once()

    def test_interrupted_download_restarts_without_splicing(self):
        def broken():
            yield b'old'
            raise ConnectionError('secret signed URL')
        self.ns['requests'].get.side_effect = [self.response(broken()), self.response([b'new'], 3)]
        self.ns['fetch']('daily', self.dest, 'test', attempts=2)
        self.assertEqual(self.dest.read_bytes(), b'new')
        self.assertEqual(self.ns['presigned'].call_count, 2)
        self.assertNotIn('secret signed URL', str(self.ns['print'].call_args_list))

    def test_length_mismatch_preserves_previous_destination(self):
        self.dest.write_bytes(b'previous')
        self.ns['requests'].get.return_value = self.response([b'short'], 100)
        with self.assertRaises(RuntimeError):
            self.ns['fetch']('daily', self.dest, 'test', attempts=1)
        self.assertEqual(self.dest.read_bytes(), b'previous')
        self.assertFalse(self.dest.with_suffix('.parquet.part').exists())

    def test_invalid_parquet_never_promoted(self):
        self.ns['requests'].get.return_value = self.response([b'invalid'])
        self.ns['validate_parquet'].side_effect = ValueError('invalid parquet')
        with self.assertRaises(RuntimeError):
            self.ns['fetch']('daily', self.dest, 'test', attempts=1)
        self.assertFalse(self.dest.exists())

    def test_http_failure_does_not_expose_credentials(self):
        self.ns['requests'].get.side_effect = RuntimeError('secret signed URL')
        with self.assertRaises(RuntimeError) as caught:
            self.ns['fetch']('daily', self.dest, 'test', attempts=1)
        self.assertNotIn('secret signed URL', str(caught.exception))
        self.assertNotIn('secret signed URL', str(self.ns['print'].call_args_list))


class SourceChecks(unittest.TestCase):
    def test_all_python_syntax(self):
        for path in ROOT.rglob('*.py'):
            ast.parse(path.read_text(encoding='utf-8'), filename=str(path))

    def test_preflight(self):
        result = subprocess.run([sys.executable, str(ROOT / 'scripts/preflight.py')], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


class AccountChecks(unittest.TestCase):
    def test_latest_candidate_creates_order_with_daily_cluster(self):
        import numpy as np
        import pandas as pd
        root = ROOT.parent / ('account-test-' + uuid.uuid4().hex)
        for name in ('state', 'forward', 'A100_v5_results', 'A100_v6_results', 'A100_v7_results'):
            (root / name).mkdir(parents=True, exist_ok=True)
        self.addCleanup(self.cleanup, root)
        dates = (pd.to_datetime(['2026-09-10', '2026-09-11']).as_unit('ns').asi8 // 1000)
        arrays = dict(starts=np.array([0, 2, 4]), ends=np.array([2, 4, 6]),
                      op=np.ones(6)*10, hi=np.ones(6)*11, lo=np.ones(6)*9,
                      cl=np.ones(6)*10, atr20=np.ones(6), date_code=np.array([0,1,0,1,0,1]),
                      unique_dates=dates, symbols=np.array(['000001.SZ','000002.SZ','000003.SZ']),
                      cluster=np.array([[1,2,3],[4,5,6]]))
        np.savez(root / 'A100_v5_results/A100_V5_context.npz', **arrays)
        np.savez(root / 'A100_v6_results/A100_V6_features.npz', sig=[5], sid=[2],
                 date_code_sig=[1], industry=[10], market=[18])
        np.savez(root / 'A100_v6_results/A100_V6_score_context.npz', score=[80])
        np.savez(root / 'A100_v7_results/A100_V7_rank_context.npz', rank_score=[1], broad=[True])
        state = {'cash':1000000., 'equity':1000000., 'positions':[], 'pending_orders':[],
                 'last_processed_date':'2026-09-10', 'last_processed_date_code':0}
        (root / 'state/account_state.json').write_text(json.dumps(state), encoding='utf-8')
        (root / 'state/trade_log.csv').write_text('trade_id,pnl\n', encoding='utf-8')
        (root / 'state/equity_curve.csv').write_text('date,equity\n2026-09-10,1000000\n', encoding='utf-8')
        (root / 'hithink_manifest.json').write_text(json.dumps(dict(
            latest_trade_date='2026-09-11', full_market=True, complete=True, data_valid=True)), encoding='utf-8')
        tree = ast.parse((ROOT / 'scripts/a100_account_v1.py').read_text(encoding='utf-8'))

        class RuntimePaths(ast.NodeTransformer):
            def visit_Constant(self, node):
                if isinstance(node.value, str) and node.value.startswith('/mnt/data/'):
                    return ast.copy_location(ast.Constant(str(root / node.value[len('/mnt/data/'):])), node)
                return node

        code = compile(ast.fix_missing_locations(RuntimePaths().visit(tree)), '<account>', 'exec')
        namespace = {'__name__':'__main__'}
        try:
            with patch('a100_runtime_checks.expected_session', return_value='2026-09-11'), patch('builtins.print'):
                exec(code, namespace)
        finally:
            for value in namespace.values():
                if isinstance(value, np.lib.npyio.NpzFile):
                    value.close()
        result = json.loads((root / 'state/account_state.json').read_text(encoding='utf-8'))
        self.assertEqual(result['cash'], 1000000.)
        self.assertEqual(result['positions'], [])
        self.assertEqual(len(result['pending_orders']), 1)
        self.assertEqual(result['pending_orders'][0]['symbol'], '000003.SZ')
        self.assertEqual(result['pending_orders'][0]['cluster'], 6)

    def cleanup(self, root):
        for path in root.rglob('*'):
            if path.is_file():
                path.unlink()
        for path in sorted(root.rglob('*'), key=lambda p:len(p.parts), reverse=True):
            if path.is_dir():
                path.rmdir()
        root.rmdir()


if __name__ == '__main__':
    unittest.main()
