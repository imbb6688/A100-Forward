import unittest

from scripts.a100_autonomous_policy import RiskPolicy, build_shadow_allocations, classify_market_regime


class AutonomousPolicyTests(unittest.TestCase):
    def setUp(self):
        self.policy = RiskPolicy()
        self.signal = {
            'validated_full_market': True,
            'data_valid': True,
            'completeness_ratio': 1.0,
            'candidate_count': 10,
            'market_gate': True,
        }
        self.account = {
            'equity': 1_000_000,
            'peak_equity': 1_000_000,
            'loss_streak': 0,
            'open_positions': [],
            'pending_orders': [],
        }

    def test_risk_on_for_clean_state(self):
        r = classify_market_regime(self.signal, self.account, self.policy)
        self.assertEqual(r['regime'], 'RISK_ON')
        self.assertAlmostEqual(r['target_exposure_pct'], 0.65)

    def test_fail_closed_on_incomplete_data(self):
        signal = dict(self.signal)
        signal['completeness_ratio'] = 0.90
        r = classify_market_regime(signal, self.account, self.policy)
        self.assertEqual(r['regime'], 'RISK_OFF')
        self.assertEqual(r['target_exposure_pct'], 0.0)
        self.assertIn('DATA_INCOMPLETE', r['reasons'])

    def test_fail_closed_on_hard_drawdown(self):
        account = dict(self.account)
        account['equity'] = 870_000
        r = classify_market_regime(self.signal, account, self.policy)
        self.assertEqual(r['regime'], 'RISK_OFF')
        self.assertIn('HARD_DRAWDOWN', r['reasons'])

    def test_cautious_on_soft_drawdown(self):
        account = dict(self.account)
        account['equity'] = 915_000
        r = classify_market_regime(self.signal, account, self.policy)
        self.assertEqual(r['regime'], 'CAUTIOUS')
        self.assertAlmostEqual(r['target_exposure_pct'], 0.35)

    def test_market_gate_off_is_defensive_zero_exposure(self):
        signal = dict(self.signal)
        signal['market_gate'] = False
        signal['candidate_count'] = 0
        r = classify_market_regime(signal, self.account, self.policy)
        self.assertEqual(r['regime'], 'DEFENSIVE')
        self.assertEqual(r['target_exposure_pct'], 0.0)
        p = build_shadow_allocations([], r, self.account, self.policy)
        self.assertEqual(p['allocations'], [])
        self.assertEqual(p['target_exposure_pct'], 0.0)

    def test_portfolio_excludes_open_positions_and_caps_exposure(self):
        account = dict(self.account)
        account['open_positions'] = [{'symbol': '000001.SZ'}]
        regime = classify_market_regime(self.signal, account, self.policy)
        candidates = [
            {'rank': 1, 'symbol': '000001.SZ', 'v7_rank_score': 9, 'v6_score': 8, 'industry_score': 7, 'market_score': 6},
            {'rank': 2, 'symbol': '000002.SZ', 'v7_rank_score': 8, 'v6_score': 8, 'industry_score': 7, 'market_score': 6},
            {'rank': 3, 'symbol': '000003.SZ', 'v7_rank_score': 7, 'v6_score': 8, 'industry_score': 7, 'market_score': 6},
        ]
        p = build_shadow_allocations(candidates, regime, account, self.policy)
        symbols = {x['symbol'] for x in p['allocations']}
        self.assertNotIn('000001.SZ', symbols)
        self.assertLessEqual(sum(x['target_weight_pct'] for x in p['allocations']), 0.65 + 1e-9)

    def test_legacy_positions_schema_remains_supported(self):
        account = dict(self.account)
        account.pop('open_positions')
        account['positions'] = [{'symbol': '000001.SZ'}]
        regime = classify_market_regime(self.signal, account, self.policy)
        candidates = [
            {'rank': 1, 'symbol': '000001.SZ', 'v7_rank_score': 9, 'v6_score': 8, 'industry_score': 7, 'market_score': 6},
            {'rank': 2, 'symbol': '000002.SZ', 'v7_rank_score': 8, 'v6_score': 8, 'industry_score': 7, 'market_score': 6},
        ]
        p = build_shadow_allocations(candidates, regime, account, self.policy)
        self.assertNotIn('000001.SZ', {x['symbol'] for x in p['allocations']})

    def test_risk_off_creates_no_allocation(self):
        regime = {'regime': 'RISK_OFF', 'target_exposure_pct': 0.0, 'reasons': ['DATA_INVALID']}
        p = build_shadow_allocations([], regime, self.account, self.policy)
        self.assertEqual(p['allocations'], [])
        self.assertEqual(p['target_exposure_pct'], 0.0)


if __name__ == '__main__':
    unittest.main()
