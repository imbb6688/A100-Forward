import os, sys, json, time, requests
from pathlib import Path
import pyarrow.parquet as pq

BASE='https://fuyao.aicubes.cn'
ENDPOINTS={
    'daily':'/api/dump/market-dumps/daily-k/download-url',
    'adj':'/api/dump/market-dumps/adjustment-factors/download-url',
}
OUT=Path('/mnt/data'); OUT.mkdir(parents=True, exist_ok=True)
KEY=os.environ.get('HITHINK_FINANCE_API_KEY')
if not KEY:
    raise SystemExit('HITHINK_FINANCE_API_KEY secret is missing')

def signed_download(kind, dest):
    r=requests.get(BASE+ENDPOINTS[kind],headers={'X-api-key':KEY},timeout=45)
    if r.status_code!=200:
        raise RuntimeError(f'{kind} signing failed HTTP {r.status_code}: {r.text[:500]}')
    obj=r.json()
    url=(obj.get('data') or {}).get('download_url') or obj.get('download_url') or obj.get('url')
    if not url:
        # handle common nested response shapes without logging credentials
        def walk(x):
            if isinstance(x,dict):
                for k,v in x.items():
                    if k in ('download_url','url') and isinstance(v,str) and v.startswith('http'): return v
                    z=walk(v)
                    if z:return z
            elif isinstance(x,list):
                for v in x:
                    z=walk(v)
                    if z:return z
        url=walk(obj)
    if not url: raise RuntimeError(f'{kind} response contains no presigned URL; keys={list(obj)[:20]}')
    with requests.get(url,stream=True,timeout=(30,180)) as d:
        d.raise_for_status()
        tmp=dest.with_suffix(dest.suffix+'.part')
        with open(tmp,'wb') as f:
            for chunk in d.iter_content(1024*1024):
                if chunk:f.write(chunk)
        tmp.replace(dest)
    return dest.stat().st_size

daily=OUT/'A100_2020_2026_raw.parquet'
adj=OUT/'A100_adjustment_factors.parquet'
print('Downloading HiThink full-market daily dump...')
print('daily bytes',signed_download('daily',daily))
print('adjustment bytes',signed_download('adj',adj))
# normalize expected names from official dump schema to legacy A100 schema
import pyarrow as pa, pyarrow.compute as pc
T=pq.read_table(daily)
rename={'thscode':'ts_code','open_price':'open','high_price':'high','low_price':'low','close_price':'close','turnover':'amount'}
cols=[]; names=[]
for name in T.column_names:
    names.append(rename.get(name,name)); cols.append(T[name])
T=pa.table(cols,names=names)
if 'trade_date' not in T.column_names:
    # date_ms is Asia/Shanghai midnight; date string is sufficient for existing engine
    ms=T['date_ms'].to_numpy(zero_copy_only=False)
    import pandas as pd
    trade=pd.to_datetime(ms,unit='ms').strftime('%Y-%m-%d').to_numpy(dtype='U10')
    T=T.append_column('trade_date',pa.array(trade))
if 'pre_close' not in T.column_names:
    import pandas as pd, numpy as np
    df=T.select(['ts_code','trade_date','close']).to_pandas()
    pre=df.groupby('ts_code',sort=False)['close'].shift(1).to_numpy()
    T=T.append_column('pre_close',pa.array(pre))
# enforce sort; official dump normally is sorted, but engine requires contiguous symbols
import pandas as pd
df=T.to_pandas()
df=df.sort_values(['ts_code','trade_date'],kind='stable').reset_index(drop=True)
pq.write_table(pa.Table.from_pandas(df,preserve_index=False),daily,compression='snappy')
latest=str(df['trade_date'].max()); nlatest=int((df['trade_date']==latest).sum())
meta={'latest_trade_date':latest,'latest_rows':nlatest,'rows':len(df),'symbols':int(df.ts_code.nunique()),'daily_bytes':daily.stat().st_size,'adjustment_bytes':adj.stat().st_size}
(OUT/'hithink_manifest.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(meta,ensure_ascii=False))
# Fail closed if today's latest session is implausibly incomplete.
if nlatest < 4500:
    raise SystemExit(f'FAIL CLOSED: latest trading day has only {nlatest} rows (<4500)')
