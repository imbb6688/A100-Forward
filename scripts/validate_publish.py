import json
from pathlib import Path

MANIFEST=Path('/mnt/data/hithink_manifest.json')
SIGNAL=Path('/mnt/data/forward/latest_signal.json')
ACCOUNT=Path('/mnt/data/forward/account.json')
AUTONOMOUS=Path('/mnt/data/forward/autonomous/shadow_report.json')
AUTONOMOUS_HTML=Path('/mnt/data/forward/autonomous/shadow.html')
JOURNAL=Path('/mnt/data/state/autonomous_journal.csv')
GRADUATION=Path('/mnt/data/forward/graduation_gate.json')

def fail(message):
    raise SystemExit(f'FAIL CLOSED: {message}')

for path in (MANIFEST,SIGNAL,ACCOUNT,AUTONOMOUS,AUTONOMOUS_HTML,JOURNAL,GRADUATION):
    if not path.exists() or path.stat().st_size==0:
        fail(f'missing publication artifact: {path}')

manifest=json.loads(MANIFEST.read_text(encoding='utf-8'))
signal=json.loads(SIGNAL.read_text(encoding='utf-8'))
account=json.loads(ACCOUNT.read_text(encoding='utf-8'))
autonomous=json.loads(AUTONOMOUS.read_text(encoding='utf-8'))
graduation=json.loads(GRADUATION.read_text(encoding='utf-8'))

if not all(bool(manifest.get(k)) for k in ('full_market','complete','data_valid')):
    fail('manifest is not complete/full-market/data-valid')
if not bool(signal.get('validated_full_market')):
    fail('signal is not validated as full-market')
if not bool(signal.get('data_valid')):
    fail('signal data_valid is false')
if not bool(account.get('data_valid')):
    fail('account data_valid is false')

manifest_date=str(manifest.get('latest_trade_date'))
signal_date=str(signal.get('latest_trade_date'))
account_date=str(account.get('as_of'))
autonomous_date=str(autonomous.get('trade_date'))

if len({manifest_date,signal_date,account_date,autonomous_date})!=1:
    fail(
        'date mismatch: '
        f'manifest={manifest_date}, '
        f'signal={signal_date}, '
        f'account={account_date}, '
        f'autonomous={autonomous_date}'
    )

top2=signal.get('top2')
if not isinstance(top2,list):
    fail('top2 is not a list')
if len(top2)>2:
    fail(f'top2 contains {len(top2)} rows')

for row in top2:
    if str(row.get('signal_date'))!=signal_date:
        fail('top2 signal_date differs from publication date')

if autonomous.get('system')!='A100 Autonomous Trading System':
    fail('unexpected autonomous system identifier')
if autonomous.get('mode')!='SHADOW':
    fail('autonomous mode must remain SHADOW')
if autonomous.get('execution')!='SHADOW_ONLY_NO_BROKER_ORDERS':
    fail('autonomous execution contract is not shadow-only')
if graduation.get('status') not in {'BLOCKED','GRADUATED'}:
    fail('unknown graduation status')
if graduation.get('live_trading_enabled') is not False:
    fail('graduation report must never auto-enable live trading')
if graduation.get('broker_orders_enabled') is not False:
    fail('graduation report must never enable broker orders')

validation=autonomous.get('validation') or {}
if not bool(validation.get('data_valid')):
    fail('autonomous data_valid is false')
if not bool(validation.get('validated_full_market')):
    fail('autonomous full-market validation is false')
if not bool(validation.get('account_date_aligned')):
    fail('autonomous account date is not aligned')

regime=(autonomous.get('market_regime') or {}).get('regime')
if regime not in {'RISK_ON','CAUTIOUS','DEFENSIVE','RISK_OFF'}:
    fail(f'unknown autonomous regime: {regime}')

portfolio=autonomous.get('portfolio') or {}
exposure=float(portfolio.get('target_exposure_pct') or 0.0)
if exposure < 0 or exposure > 0.65 + 1e-12:
    fail(f'autonomous target exposure out of bounds: {exposure}')

allocations=portfolio.get('allocations')
if not isinstance(allocations,list):
    fail('autonomous allocations is not a list')
if len(allocations)>5:
    fail(f'autonomous allocations exceed max positions: {len(allocations)}')
if regime=='RISK_OFF' and (allocations or exposure!=0):
    fail('RISK_OFF must produce zero allocations and zero target exposure')

weight_sum=sum(float(x.get('target_weight_pct') or 0.0) for x in allocations)
if weight_sum > exposure + 1e-9:
    fail(f'allocation weights exceed target exposure: {weight_sum}>{exposure}')

print(
    'A100 PUBLISH CONTRACT OK | '
    f'date={manifest_date} | '
    f'regime={regime} | '
    f'target_exposure={exposure:.2%} | '
    f'allocations={len(allocations)} | '
    f'latest_rows={manifest.get("latest_rows")} | '
    f'completeness_ratio={manifest.get("completeness_ratio")}'
)
