from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from a100_autonomous_policy import RiskPolicy, build_shadow_allocations, classify_market_regime

ROOT = Path('/mnt/data')
FORWARD = ROOT / 'forward'
STATE = ROOT / 'state'
OUT = FORWARD / 'autonomous'
OUT.mkdir(parents=True, exist_ok=True)

SIGNAL_FILE = FORWARD / 'latest_signal.json'
CANDIDATE_FILE = FORWARD / 'latest_candidates.csv'
ACCOUNT_FILE = STATE / 'account_state.json'

for path in (SIGNAL_FILE, CANDIDATE_FILE, ACCOUNT_FILE):
    if not path.exists():
        raise SystemExit(f'FAIL CLOSED: missing autonomous input: {path}')

signal = json.loads(SIGNAL_FILE.read_text(encoding='utf-8'))
account = json.loads(ACCOUNT_FILE.read_text(encoding='utf-8'))
candidates_df = pd.read_csv(CANDIDATE_FILE)
candidates = candidates_df.to_dict(orient='records')

if not signal.get('latest_trade_date'):
    raise SystemExit('FAIL CLOSED: latest_trade_date missing')
if account.get('last_processed_date') != signal.get('latest_trade_date'):
    raise SystemExit('FAIL CLOSED: account and signal dates are not aligned')

policy = RiskPolicy()
regime = classify_market_regime(signal, account, policy)
portfolio = build_shadow_allocations(candidates, regime, account, policy)

hard_fail_reasons = {'DATA_INVALID', 'DATA_INCOMPLETE', 'HARD_DRAWDOWN', 'HARD_LOSS_STREAK'}
risk_pass = not bool(hard_fail_reasons.intersection(regime['reasons']))

report = {
    'system': 'A100 Autonomous Trading System',
    'mode': 'SHADOW',
    'version': 'AUTONOMOUS_1.0',
    'trade_date': signal['latest_trade_date'],
    'generated_at_utc': pd.Timestamp.utcnow().isoformat(),
    'market_regime': regime,
    'validation': {
        'data_valid': bool(signal.get('data_valid')),
        'validated_full_market': bool(signal.get('validated_full_market')),
        'account_date_aligned': True,
        'risk_gate': 'PASS' if risk_pass else 'FAIL',
    },
    'portfolio': portfolio,
    'account': {
        'equity': float(account.get('equity', 0.0)),
        'cash': float(account.get('cash', 0.0)),
        'peak_equity': float(account.get('peak_equity', 0.0)),
        'max_drawdown': float(account.get('max_drawdown', 0.0)),
        'open_positions': len(account.get('positions', [])),
        'pending_orders': len(account.get('pending_orders', [])),
        'loss_streak': int(account.get('loss_streak', 0)),
    },
    'execution': 'SHADOW_ONLY_NO_BROKER_ORDERS',
}

(OUT / 'shadow_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
pd.DataFrame(portfolio['allocations']).to_csv(OUT / 'shadow_allocations.csv', index=False)
pd.DataFrame(portfolio['rejected']).to_csv(OUT / 'shadow_rejections.csv', index=False)

journal_path = STATE / 'autonomous_journal.csv'
row = {
    'date': report['trade_date'],
    'mode': report['mode'],
    'regime': regime['regime'],
    'risk_gate': report['validation']['risk_gate'],
    'target_exposure_pct': portfolio['target_exposure_pct'],
    'allocations': len(portfolio['allocations']),
    'rejections': len(portfolio['rejected']),
    'equity': report['account']['equity'],
    'drawdown': regime['drawdown'],
    'loss_streak': regime['loss_streak'],
}
if journal_path.exists() and journal_path.stat().st_size:
    journal = pd.read_csv(journal_path)
    journal = journal[journal['date'].astype(str) != str(row['date'])]
    journal = pd.concat([journal, pd.DataFrame([row])], ignore_index=True)
else:
    journal = pd.DataFrame([row])
journal.to_csv(journal_path, index=False)

alloc = pd.DataFrame(portfolio['allocations'])
rej = pd.DataFrame(portfolio['rejected'])
html = '''<!doctype html><meta charset="utf-8"><title>A100 Autonomous Shadow</title>
<style>body{font-family:system-ui;max-width:1050px;margin:40px auto;padding:0 20px}table{border-collapse:collapse;width:100%}td,th{border:1px solid #ddd;padding:8px;text-align:left}.ok{font-weight:700}.muted{color:#666}</style>
<h1>A100 Autonomous Trading System — Shadow</h1>'''
html += f"<p>Trade date: <b>{report['trade_date']}</b> · Regime: <b>{regime['regime']}</b> · Risk gate: <b>{report['validation']['risk_gate']}</b> · Target exposure: <b>{portfolio['target_exposure_pct']:.1%}</b></p>"
html += '<h2>Shadow allocations</h2>'
html += alloc.to_html(index=False, escape=True) if not alloc.empty else '<p>No shadow allocation.</p>'
html += '<h2>Rejected candidates</h2>'
html += rej.to_html(index=False, escape=True) if not rej.empty else '<p>No rejected candidate.</p>'
html += '<h2>Risk state</h2>'
html += f"<p>Equity: {report['account']['equity']:.2f} · Drawdown: {regime['drawdown']:.2%} · Loss streak: {regime['loss_streak']} · Data completeness: {regime['completeness_ratio']:.2%}</p>"
html += '<p class="muted">Shadow mode only. No broker orders are created or transmitted.</p>'
(OUT / 'shadow.html').write_text(html, encoding='utf-8')

print(json.dumps(report, ensure_ascii=False, indent=2))
