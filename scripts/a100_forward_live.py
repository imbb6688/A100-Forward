import numpy as np,pandas as pd, json, os, math
from pathlib import Path
OUT=Path('/mnt/data/forward');OUT.mkdir(parents=True,exist_ok=True)
f=np.load('/mnt/data/A100_v6_results/A100_V6_features.npz',allow_pickle=False); sc=np.load('/mnt/data/A100_v6_results/A100_V6_score_context.npz',allow_pickle=False)['score']; rk=np.load('/mnt/data/A100_v7_results/A100_V7_rank_context.npz',allow_pickle=False); rank=rk['rank_score']; broad=rk['broad']; z=np.load('/mnt/data/A100_v5_results/A100_V5_context.npz',allow_pickle=False)
ud=z['unique_dates']; dts=pd.to_datetime(ud,unit='us'); symbols=z['symbols']; sig=f['sig']; sid=f['sid'].astype(int); dc=f['date_code_sig'].astype(int)
latest=int(len(ud)-1); today=dts[latest]; gate_by_day=np.load('/mnt/data/A100_v6_results/A100_V6_features.npz',allow_pickle=False)['gate']
mask=broad&(dc==latest)&np.isfinite(rank)
ix=np.flatnonzero(mask); ix=ix[np.argsort(rank[ix])[::-1]][:2]
rows=[]
for pos,i in enumerate(ix,1):
 rows.append({'rank':pos,'symbol':str(symbols[sid[i]]),'v7_rank_score':float(rank[i]),'v6_score':float(sc[i]),'industry_score':float(f['industry'][i]),'market_score':float(f['market'][i]),'setup':'PULLBACK','signal_date':str(today.date())})
manifest=json.loads(Path('/mnt/data/hithink_manifest.json').read_text())
status={'generated_at_utc':pd.Timestamp.utcnow().isoformat(),'latest_trade_date':str(today.date()),'hithink_latest_trade_date':manifest['latest_trade_date'],'market_gate':bool(gate_by_day[np.flatnonzero(dc==latest)[0]]) if np.any(dc==latest) else False,'candidate_count':int(mask.sum()),'top2':rows,'model':'A100 V7 FROZEN / ExtraTrees d4 leaf40','execution':'Signals at close; simulated entry next trading day open; max 5 positions; 0.5% risk; 1.5ATR stop; 1.5R target; max hold 5d','data_source':'HiThink Financial-API full-market daily-k + adjustment events','validated_full_market':manifest['latest_rows']>=4500}
if manifest['latest_trade_date']!=str(today.date()): raise SystemExit('FAIL CLOSED: engine date differs from HiThink manifest')
(OUT/'latest_signal.json').write_text(json.dumps(status,ensure_ascii=False,indent=2),encoding='utf-8')
pd.DataFrame(rows).to_csv(OUT/'latest_candidates.csv',index=False)
# human-readable page
html='''<!doctype html><meta charset="utf-8"><title>A100 Forward</title><style>body{font-family:system-ui;max-width:900px;margin:40px auto;padding:0 20px}table{border-collapse:collapse;width:100%}td,th{border:1px solid #ddd;padding:8px}code{background:#eee;padding:2px 5px}</style><h1>A100 Forward — Frozen V7</h1>'''
html+=f'<p>Latest validated A-share session: <b>{status["latest_trade_date"]}</b> · Full-market rows: <b>{manifest["latest_rows"]}</b> · Market gate: <b>{status["market_gate"]}</b></p>'
if rows: html+=pd.DataFrame(rows).to_html(index=False,escape=True)
else: html+='<p><b>No new Top-2 signal.</b></p>'
html+='<p>Data: HiThink Financial-API. Research/simulation only; not investment advice.</p>'
(OUT/'index.html').write_text(html,encoding='utf-8')
print(json.dumps(status,ensure_ascii=False,indent=2))
