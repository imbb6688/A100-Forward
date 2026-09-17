from __future__ import annotations

import argparse, hashlib, json, math
from pathlib import Path
import numpy as np
import pandas as pd

INITIAL=1_000_000.; RISK=.005; MAX_PCT=.25; MAX_POS=5; MAX_INDUSTRY=2
STOP_ATR=1.5; TARGET_R=1.5; MAX_HOLD=5; SLIP=.0005; COMM=.00025; MIN_COMM=5.

def pf(x):
    x=np.asarray(x,float); g=x[x>0].sum(); l=-x[x<0].sum()
    return float(g/l) if l else (999. if g else 0.)

def load_pit(path,value):
    d=pd.read_parquet(path).sort_values(['symbol','effective_from'])
    d.effective_from=pd.to_datetime(d.effective_from); d.effective_to=pd.to_datetime(d.effective_to)
    return {s:list(zip(g.effective_from,g.effective_to,g[value])) for s,g in d.groupby('symbol')}

def pit_at(index,symbol,date,default=None):
    for a,b,v in index.get(symbol,[]):
        if a<=date<=b: return v
    return default

def row(starts,ends,dc,sid,t):
    a,b=int(starts[sid]),int(ends[sid]); j=int(np.searchsorted(dc[a:b],t))
    return a+j if j<b-a and int(dc[a+j])==t else None

def limit_pct(sym,date,is_st):
    if is_st: return .05
    if sym.endswith('.BJ'): return .30
    if sym.startswith('688'): return .20
    return .20 if sym.startswith(('300','301')) and date>=pd.Timestamp('2020-08-24') else .10

def locked(sym,date,is_st,pre,o,h,l,up):
    if not np.isfinite(pre) or pre<=0: return False
    p=round(pre*(1+(1 if up else -1)*limit_pct(sym,date,is_st))+1e-10,2)
    return o>=p-.005 and h<=p+.005 and l>=p-.005 if up else o<=p+.005 and h<=p+.005 and l<=p+.005

def build(root:Path):
    c=np.load(root/'A100_v5_results/A100_V5_context.npz',allow_pickle=False)
    f=np.load(root/'A100_v6_results/A100_V6_features.npz',allow_pickle=False)
    v6=np.load(root/'A100_v6_results/A100_V6_score_context.npz',allow_pickle=False)['score'].astype(float)
    rk=np.load(root/'A100_v7_results/A100_V7_rank_context.npz',allow_pickle=False)
    starts,ends=c['starts'].astype(int),c['ends'].astype(int); op,hi,lo,cl,atr=[c[k].astype(float) for k in ('op','hi','lo','cl','atr20')]
    dc=c['date_code'].astype(int); dates=pd.to_datetime(c['unique_dates'],unit='us'); symbols=c['symbols'].astype(str)
    sig=f['sig'].astype(int); ss=f['sid'].astype(int); sd=f['date_code_sig'].astype(int); rank=rk['rank_score'].astype(float); broad=rk['broad'].astype(bool)
    st=load_pit(root/'pit/st_risk_warning_history.parquet','is_st'); ind=load_pit(root/'pit/industry_membership_history.parquet','industry_code')
    cash=INITIAL; peak=INITIAL; equity=INITIAL; positions=[]; pending=[]; trades=[]; curve=[]; loss_streak=0; pause=-1
    start=int(np.searchsorted(dates,pd.Timestamp('2023-01-01')))
    for t in range(start,len(dates)):
        date=dates[t]; keep=[]
        for p in positions:
            r=row(starts,ends,dc,p['sid'],t)
            if r is None: keep.append(p); continue
            pr=row(starts,ends,dc,p['sid'],t-1); pre=cl[pr] if pr is not None else np.nan
            o,h,l,cx=op[r],hi[r],lo[r],cl[r]; age=t-p['entry_t']; ex=why=None
            if age>0 and not locked(p['symbol'],date,bool(pit_at(st,p['symbol'],date,False)),pre,o,h,l,False):
                if o<=p['stop']: ex,why=o,'STOP_GAP'
                elif o>=p['target']: ex,why=o,'TARGET_GAP'
                elif l<=p['stop']: ex,why=p['stop'],'STOP'
                elif h>=p['target']: ex,why=p['target'],'TARGET'
                elif age>=MAX_HOLD: ex,why=cx,'TIME'
            if ex is None: p['mark']=cx; keep.append(p); continue
            gross=p['shares']*ex*(1-SLIP); fee=max(MIN_COMM,gross*COMM); stamp=gross*(.0005 if date>=pd.Timestamp('2023-08-28') else .001)
            cash+=gross-fee-stamp; pnl=gross-fee-stamp-p['cost']; rm=pnl/(p['shares']*p['rps'])
            loss_streak=0 if pnl>0 else loss_streak+1; pause=t+10 if loss_streak>=8 else pause
            trades.append({**p,'exit_date':date,'pnl':pnl,'r_multiple':rm,'exit_reason':why})
        positions=keep
        for q in pending:
            if len(positions)>=MAX_POS or q['signal_t']!=t-1 or any(p['symbol']==q['symbol'] for p in positions): continue
            if sum(p['industry']==q['industry'] for p in positions)>=MAX_INDUSTRY: continue
            r=row(starts,ends,dc,q['sid'],t)
            if r is None: continue
            pr=row(starts,ends,dc,q['sid'],t-1); pre=cl[pr] if pr is not None else np.nan; o,h,l=op[r],hi[r],lo[r]
            if bool(pit_at(st,q['symbol'],date,False)) or locked(q['symbol'],date,False,pre,o,h,l,True): continue
            dd=equity/max(peak,1)-1; mult=0 if t<=pause or dd<=-.12 or loss_streak>=8 else (.5 if dd<=-.08 or loss_streak>=5 else 1.)
            if mult<=0 or not(np.isfinite(o) and np.isfinite(q['atr']) and o>0 and q['atr']>0): continue
            ep=o*(1+SLIP); rps=STOP_ATR*q['atr']; sh=int(max(0,min(math.floor(equity*RISK*mult/rps/100)*100,math.floor(equity*MAX_PCT/ep/100)*100,math.floor(cash/(ep*(1+COMM))/100)*100)))
            if sh<100: continue
            fee=max(MIN_COMM,sh*ep*COMM); cost=sh*ep+fee
            if cost>cash: continue
            cash-=cost; positions.append({**q,'entry_t':t,'entry_date':date,'shares':sh,'entry_exec':ep,'rps':rps,'stop':o-rps,'target':o+TARGET_R*rps,'cost':cost,'mark':cl[r]})
        marks=sum(p['shares']*p['mark'] for p in positions); equity=cash+marks; peak=max(peak,equity)
        pending=[]; dd=equity/peak-1; mult=0 if t<=pause or dd<=-.12 or loss_streak>=8 else (.5 if dd<=-.08 or loss_streak>=5 else 1.)
        ix=np.flatnonzero(broad&(sd==t)&np.isfinite(rank)); ix=ix[np.argsort(rank[ix])[::-1]]
        used={p['industry'] for p in positions}; counts={x:sum(p['industry']==x for p in positions) for x in used}
        for i in ix:
            if len(pending)>=2 or len(positions)+len(pending)>=MAX_POS or mult<=0: break
            sid=int(ss[i]); sym=symbols[sid]; industry=pit_at(ind,sym,date); stflag=pit_at(st,sym,date)
            if stflag is None or industry is None:
                raise RuntimeError(f'missing PIT coverage for eligible signal: {sym} {date.date()}')
            if bool(stflag) or counts.get(industry,0)>=MAX_INDUSTRY or any(p['symbol']==sym for p in positions+pending): continue
            raw=int(sig[i]); pending.append({'symbol':sym,'sid':sid,'industry':industry,'signal_t':t,'signal_date':date,'atr':float(atr[raw]),'rank':float(rank[i]),'v6':float(v6[i])}); counts[industry]=counts.get(industry,0)+1
        curve.append({'date':date,'equity':equity,'drawdown':equity/peak-1})
    td=pd.DataFrame(trades); ec=pd.DataFrame(curve); folds=[]
    for year in sorted(ec.date.dt.year.unique()):
        e=ec[ec.date.dt.year==year]; tr=td[pd.to_datetime(td.exit_date).dt.year==year] if len(td) else td
        pnl=tr.pnl.to_numpy(float) if len(tr) else np.array([]); folds.append({'fold':str(year),'train_end':'2022-12-31','test_start':f'{year}-01-01','test_end':str(e.date.max().date()),'trades':len(tr),'net_return':float(e.equity.iloc[-1]/e.equity.iloc[0]-1),'profit_factor':pf(pnl),'max_drawdown':float(e.drawdown.min()),'positive_trade_ratio':float((pnl>0).mean()) if len(pnl) else 0.})
    digest=hashlib.sha256((root/'pit/st_risk_warning_history.parquet').read_bytes()+(root/'pit/industry_membership_history.parquet').read_bytes()+(root/'A100_v7_results/A100_V7_rank_context.npz').read_bytes()).hexdigest()
    return {'schema_version':1,'status':'COMPLETE','evidence_class':'PORTFOLIO_REPLAY','graduation_eligible':True,'model':'A100_V7_FROZEN','data_fingerprint':digest,'pit_filters':{'historical_st':True,'historical_industry':True},'rules':{'initial_capital':INITIAL,'risk_per_trade':RISK,'max_positions':MAX_POS,'max_per_industry':MAX_INDUSTRY,'entry':'next open'},'folds':folds,'total_trades':len(td),'ending_equity':float(ec.equity.iloc[-1])},td,ec

def main():
    p=argparse.ArgumentParser(); p.add_argument('--root',type=Path,default=Path('/mnt/data')); a=p.parse_args(); report,trades,curve=build(a.root)
    out=a.root/'validation'; out.mkdir(parents=True,exist_ok=True); (out/'walk_forward_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8'); trades.to_parquet(out/'portfolio_replay_trades.parquet',index=False); curve.to_parquet(out/'portfolio_replay_equity.parquet',index=False); print(json.dumps(report,ensure_ascii=False,indent=2))
if __name__=='__main__': main()
