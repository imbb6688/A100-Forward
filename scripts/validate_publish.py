import json
from pathlib import Path

MANIFEST=Path('/mnt/data/hithink_manifest.json')
SIGNAL=Path('/mnt/data/forward/latest_signal.json')
ACCOUNT=Path('/mnt/data/forward/account.json')

def fail(message):
    raise SystemExit(f'FAIL CLOSED: {message}')

for path in (MANIFEST,SIGNAL,ACCOUNT):
    if not path.exists() or path.stat().st_size==0:
        fail(f'missing publication artifact: {path}')

manifest=json.loads(MANIFEST.read_text(encoding='utf-8'))
signal=json.loads(SIGNAL.read_text(encoding='utf-8'))
account=json.loads(ACCOUNT.read_text(encoding='utf-8'))

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

if len({manifest_date,signal_date,account_date})!=1:
    fail(
        'date mismatch: '
        f'manifest={manifest_date}, '
        f'signal={signal_date}, '
        f'account={account_date}'
    )

top2=signal.get('top2')
if not isinstance(top2,list):
    fail('top2 is not a list')
if len(top2)>2:
    fail(f'top2 contains {len(top2)} rows')

for row in top2:
    if str(row.get('signal_date'))!=signal_date:
        fail('top2 signal_date differs from publication date')

print(
    'A100 PUBLISH CONTRACT OK | '
    f'date={manifest_date} | '
    f'latest_rows={manifest.get("latest_rows")} | '
    f'completeness_ratio={manifest.get("completeness_ratio")}'
)
