import json, math
from pathlib import Path
import numpy as np
import pandas as pd

STATE_DIR=Path('/mnt/data/state'); FORWARD_DIR=Path('/mnt/data/forward')
STATE_DIR.mkdir(parents=True,exist_ok=True); FORWARD_DIR.mkdir(parents=True,exist_ok=True)
STATE_FILE=STATE_DIR/'account_state.json'; TRADES_FILE=STATE_DIR/'trade_log.csv'; EQUITY_FILE=STATE_DIR/'equity_curve.csv'
INITIAL=1_000_000.0; START='2026-09-08'; BASE_RISK=.005; MAX_POS_PCT=.25; MAX_POS=5; MAX_MAINLINE=2
STOP_ATR=1.5; TARGET_R=1.5; MAX_HOLD=5; SLIP=.0005; COMM=.00025; MIN_COMM=5.0
TRADE_COLS=['trade_id','symbol','cluster','signal_date','entry_date','exit_date','shares','entry_raw','entry_exec','exit_raw','exit_exec','atr','stop','target','buy_commission','sell_commission','stamp_duty','pnl','return_pct','r_multiple','exit_reason','holding_days','v7_rank_score','v6_score','industry_score','market_score']
EQ_COLS=['date','cash','market_value','equity','peak_equity','drawdown','open_positions','pending_orders','realized_pnl','loss_streak','risk_multiplier','new_signals']

def empty_state():
    return {'version':'A100_FORWARD_ACCOUNT_V1','initial_capital':INITIAL,'cash':INITIAL,'equity':INITIAL,'peak_equity':INITIAL,'max_drawdown':0.0,'realized_pnl':0.0,'positions':[],'pending_orders':[],'last_processed_date_code':None,'last_processed_date':None,'closed_trades':0,'wins':0,'losses':0,'loss_streak':0,'pause_until_date_code':None,'started_on':START,'updated_on':None,'next_trade_id':1}

def load_state():
    if not STATE_FILE.exists(): return empty_state()
    s=empty_state(); s.update(json.loads(STATE_FILE.read_text(encoding='utf-8'))); return s

def load_csv(path,cols):
    if path.exists() and path.stat().st_size:
        d=pd.read_csv(path)
        for c in cols:
            if c not in d.columns: d[c]=np.nan
        return d[cols]
    return pd.DataFrame(columns=cols)

def dstr(ud,t): return pd.to_datetime(int(ud[int(t)]),unit='us').strftime('%Y-%m-%d')

def row_for(starts,ends,dc,sid,t):
    a,b=int(starts[sid]),int(ends[sid]); arr=dc[a:b]; j=int(np.searchsorted(arr,t))
    return a+j if j<len(arr) and int(arr[j])==int(t) else None

def limit_pct(sym,dt):
    if sym.endswith('.BJ'): return .30
    if sym.startswith('688'): return .20
    if sym.startswith(('300','301')): return .20 if dt>=pd.Timestamp('2020-08-24') else .10
    return .10

def locked_up(sym,dt,pre,o,h,l):
    if not(np.isfinite(pre) and pre>0): return False
    p=round(pre*(1+limit_pct(sym,dt))+1e-10,2)
    return o>=p-.005 and h<=p+.005 and l>=p-.005

def locked_down(sym,dt,pre,o,h,l):
    if not(np.isfinite(pre) and pre>0): return False
    p=round(pre*(1-limit_pct(sym,dt))+1e-10,2)
    return o<=p+.005 and h<=p+.005 and l<=p+.005

def risk_mult(s,t):
    dd=float(s['equity'])/max(float(s['peak_equity']),1e-9)-1
    pu=s.get('pause_until_date_code')
    if pu is not None and t<=int(pu): return 0.0
    if dd<=-.12 or int(s['loss_streak'])>=8: return 0.0
    if dd<=-.08 or int(s['loss_streak'])>=5: return .5
    return 1.0

def mark_equity(s,positions,marks):
    mv=sum(int(p['shares'])*float(marks.get(p['symbol'],p.get('last_mark',p['entry_raw']))) for p in positions)
    return float(s['cash'])+mv,mv

v5=np.load('/mnt/data/A100_v5_results/A100_V5_context.npz',allow_pickle=False)
f=np.load('/mnt/data/A100_v6_results/A100_V6_features.npz',allow_pickle=False)
v6=np.load('/mnt/data/A100_v6_results/A100_V6_score_context.npz',allow_pickle=False)['score'].astype(float)
rk=np.load('/mnt/data/A100_v7_results/A100_V7_rank_context.npz',allow_pickle=False)
starts=v5['starts'].astype(int); ends=v5['ends'].astype(int); op=v5['op'].astype(float); hi=v5['hi'].astype(float); lo=v5['lo'].astype(float); cl=v5['cl'].astype(float); atr=v5['atr20'].astype(float); dc=v5['date_code'].astype(int); ud=v5['unique_dates'].astype(np.int64); symbols=v5['symbols']; clusters=v5['cluster'].astype(int)
sig=f['sig'].astype(int); sid_sig=f['sid'].astype(int); dc_sig=f['date_code_sig'].astype(int); ranks=rk['rank_score'].astype(float); broad=rk['broad'].astype(bool)
latest=len(ud)-1; latest_date=dstr(ud,latest)
manifest=json.loads(Path('/mnt/data/hithink_manifest.json').read_text(encoding='utf-8'))
if manifest.get('latest_trade_date')!=latest_date:
    raise SystemExit('FAIL CLOSED: account date differs from HiThink manifest')
if not all(bool(manifest.get(k)) for k in ('full_market','complete','data_valid')):
    raise SystemExit('FAIL CLOSED: incomplete full-market session')

s=load_state(); trades=load_csv(TRADES_FILE,TRADE_COLS); eqcurve=load_csv(EQUITY_FILE,EQ_COLS); actions=[]
start_us=pd.Timestamp(START).value//1000; start_code=int(np.searchsorted(ud,start_us))
if start_code>=len(ud): raise SystemExit('Forward start is after available data')
last=s.get('last_processed_date_code'); first=start_code if last is None else int(last)+1

for t in range(first,latest+1):
    dt=pd.to_datetime(int(ud[t]),unit='us'); ds=dt.strftime('%Y-%m-%d')
    keep=[]
    for p in list(s['positions']):
        sid=int(p['sid']); r=row_for(starts,ends,dc,sid,t)
        if r is None: keep.append(p); continue
        sym=p['symbol']; pr=row_for(starts,ends,dc,sid,t-1) if t>0 else None; pre=cl[pr] if pr is not None else np.nan
        o,h,l,c=map(float,(op[r],hi[r],lo[r],cl[r])); p['last_mark']=c
        if t<=int(p['entry_date_code']): keep.append(p); continue
        age=t-int(p['entry_date_code']); ex=None; why=None; blocked=locked_down(sym,dt,pre,o,h,l)
        if not blocked:
            stop=float(p['stop']); target=float(p['target'])
            if o<=stop: ex,why=o,'STOP_GAP'
            elif o>=target: ex,why=o,'TARGET_GAP'
            elif l<=stop: ex,why=stop,'STOP'
            elif h>=target: ex,why=target,'TARGET'
            elif age>=MAX_HOLD: ex,why=c,'TIME'
        if ex is None:
            if blocked: actions.append({'date':ds,'action':'EXIT_BLOCKED_LIMIT_DOWN','symbol':sym})
            keep.append(p); continue
        sh=int(p['shares']); ex_exec=float(ex)*(1-SLIP); gross=sh*ex_exec; sell_comm=max(MIN_COMM,gross*COMM); stamp=gross*(.0005 if dt>=pd.Timestamp('2023-08-28') else .001); net=gross-sell_comm-stamp
        s['cash']=float(s['cash'])+net; pnl=net-float(p['cost_basis']); s['realized_pnl']=float(s['realized_pnl'])+pnl; s['closed_trades']=int(s['closed_trades'])+1
        if pnl>0: s['wins']=int(s['wins'])+1; s['loss_streak']=0
        else:
            s['losses']=int(s['losses'])+1; s['loss_streak']=int(s['loss_streak'])+1
            if int(s['loss_streak'])>=8: s['pause_until_date_code']=t+10
        riskamt=sh*float(p['risk_per_share']); rmul=pnl/riskamt if riskamt>0 else np.nan
        tr={'trade_id':p['trade_id'],'symbol':sym,'cluster':p['cluster'],'signal_date':p['signal_date'],'entry_date':p['entry_date'],'exit_date':ds,'shares':sh,'entry_raw':p['entry_raw'],'entry_exec':p['entry_exec'],'exit_raw':ex,'exit_exec':ex_exec,'atr':p['atr'],'stop':p['stop'],'target':p['target'],'buy_commission':p['buy_commission'],'sell_commission':sell_comm,'stamp_duty':stamp,'pnl':pnl,'return_pct':pnl/float(p['cost_basis']),'r_multiple':rmul,'exit_reason':why,'holding_days':age,'v7_rank_score':p.get('v7_rank_score'),'v6_score':p.get('v6_score'),'industry_score':p.get('industry_score'),'market_score':p.get('market_score')}
        trades=pd.concat([trades,pd.DataFrame([tr])],ignore_index=True); actions.append({'date':ds,'action':'EXIT','symbol':sym,'reason':why,'pnl':round(pnl,2)})
    s['positions']=keep

    for order in list(s['pending_orders']):
        sym=order['symbol']
        if int(order['signal_date_code'])!=t-1: actions.append({'date':ds,'action':'ENTRY_CANCEL_STALE','symbol':sym}); continue
        if len(s['positions'])>=MAX_POS: actions.append({'date':ds,'action':'ENTRY_SKIP_MAX_POSITIONS','symbol':sym}); continue
        if any(p['symbol']==sym for p in s['positions']): actions.append({'date':ds,'action':'ENTRY_SKIP_ALREADY_HELD','symbol':sym}); continue
        if sum(int(p['cluster'])==int(order['cluster']) for p in s['positions'])>=MAX_MAINLINE: actions.append({'date':ds,'action':'ENTRY_SKIP_MAINLINE_CAP','symbol':sym}); continue
        sid=int(order['sid']); r=row_for(starts,ends,dc,sid,t)
        if r is None: actions.append({'date':ds,'action':'ENTRY_CANCEL_NO_OPEN','symbol':sym}); continue
        pr=row_for(starts,ends,dc,sid,t-1); pre=cl[pr] if pr is not None else np.nan; o,h,l=map(float,(op[r],hi[r],lo[r]))
        if locked_up(sym,dt,pre,o,h,l): actions.append({'date':ds,'action':'ENTRY_BLOCKED_LIMIT_UP','symbol':sym}); continue
        rm=min(float(order.get('risk_multiplier',1)),risk_mult(s,t)); aa=float(order['atr'])
        if rm<=0 or not(np.isfinite(aa) and aa>0 and np.isfinite(o) and o>0): actions.append({'date':ds,'action':'ENTRY_SKIP_RISK_OFF_OR_BAD_DATA','symbol':sym}); continue
        rps=STOP_ATR*aa; eqref=max(float(s['equity']),1); ep=o*(1+SLIP); n1=math.floor((eqref*BASE_RISK*rm/rps)/100)*100; n2=math.floor((eqref*MAX_POS_PCT/ep)/100)*100; n3=math.floor((float(s['cash'])/(ep*(1+COMM)))/100)*100; sh=int(max(0,min(n1,n2,n3)))
        if sh<100: actions.append({'date':ds,'action':'ENTRY_SKIP_SIZE_LT_100','symbol':sym}); continue
        gross=sh*ep; bc=max(MIN_COMM,gross*COMM)
        while sh>=100 and gross+bc>float(s['cash']): sh-=100; gross=sh*ep; bc=max(MIN_COMM,gross*COMM) if sh else 0
        if sh<100: actions.append({'date':ds,'action':'ENTRY_SKIP_NO_CASH','symbol':sym}); continue
        s['cash']=float(s['cash'])-gross-bc; tid=int(s['next_trade_id']); s['next_trade_id']=tid+1
        pos={'trade_id':tid,'symbol':sym,'sid':sid,'cluster':int(order['cluster']),'signal_date_code':int(order['signal_date_code']),'signal_date':order['signal_date'],'entry_date_code':t,'entry_date':ds,'entry_raw':o,'entry_exec':ep,'shares':sh,'atr':aa,'risk_per_share':rps,'stop':o-STOP_ATR*aa,'target':o+TARGET_R*rps,'buy_commission':bc,'cost_basis':gross+bc,'last_mark':float(cl[r]),'v7_rank_score':order.get('v7_rank_score'),'v6_score':order.get('v6_score'),'industry_score':order.get('industry_score'),'market_score':order.get('market_score')}
        s['positions'].append(pos); actions.append({'date':ds,'action':'ENTRY','symbol':sym,'shares':sh,'entry':round(o,4)})
    s['pending_orders']=[]

    marks={}
    for p in s['positions']:
        r=row_for(starts,ends,dc,int(p['sid']),t)
        if r is not None: marks[p['symbol']]=float(cl[r]); p['last_mark']=float(cl[r])
    equity,mv=mark_equity(s,s['positions'],marks); s['equity']=equity; s['peak_equity']=max(float(s['peak_equity']),equity); dd=equity/max(float(s['peak_equity']),1e-9)-1; s['max_drawdown']=min(float(s['max_drawdown']),dd)

    selected=[]; rmclose=risk_mult(s,t)
    if rmclose>0 and len(s['positions'])<MAX_POS:
        ix=np.flatnonzero(broad&(dc_sig==t)&np.isfinite(ranks)); ix=ix[np.argsort(ranks[ix])[::-1]] if len(ix) else ix
        held={p['symbol'] for p in s['positions']}; cc={}
        for p in s['positions']: cc[int(p['cluster'])]=cc.get(int(p['cluster']),0)+1
        for i in ix:
            if len(selected)>=2 or len(s['positions'])+len(selected)>=MAX_POS: break
            raw=int(sig[i]); sid=int(sid_sig[i]); sym=str(symbols[sid]); clu=int(clusters[raw]); aa=float(atr[raw])
            if sym in held or clu<0 or cc.get(clu,0)>=MAX_MAINLINE or not(np.isfinite(aa) and aa>0): continue
            order={'symbol':sym,'sid':sid,'cluster':clu,'signal_date_code':t,'signal_date':ds,'atr':aa,'risk_multiplier':rmclose,'v7_rank_score':float(ranks[i]),'v6_score':float(v6[i]),'industry_score':float(f['industry'][i]),'market_score':float(f['market'][i])}
            selected.append(order); held.add(sym); cc[clu]=cc.get(clu,0)+1
    s['pending_orders']=selected
    for o in selected: actions.append({'date':ds,'action':'NEW_SIGNAL','symbol':o['symbol'],'rank_score':round(o['v7_rank_score'],6)})

    equity,mv=mark_equity(s,s['positions'],marks); s['equity']=equity; s['peak_equity']=max(float(s['peak_equity']),equity); dd=equity/max(float(s['peak_equity']),1e-9)-1; s['max_drawdown']=min(float(s['max_drawdown']),dd); s['last_processed_date_code']=t; s['last_processed_date']=ds; s['updated_on']=pd.Timestamp.utcnow().isoformat()
    er={'date':ds,'cash':s['cash'],'market_value':mv,'equity':equity,'peak_equity':s['peak_equity'],'drawdown':dd,'open_positions':len(s['positions']),'pending_orders':len(selected),'realized_pnl':s['realized_pnl'],'loss_streak':s['loss_streak'],'risk_multiplier':rmclose,'new_signals':len(selected)}
    eqcurve=eqcurve[eqcurve['date'].astype(str)!=ds]; eqcurve=pd.concat([eqcurve,pd.DataFrame([er])],ignore_index=True)

STATE_FILE.write_text(json.dumps(s,ensure_ascii=False,indent=2),encoding='utf-8'); trades.to_csv(TRADES_FILE,index=False); eqcurve.to_csv(EQUITY_FILE,index=False)
closed=int(s['closed_trades']); wins=int(s['wins']); wr=wins/closed if closed else None
pnlcol=pd.to_numeric(trades['pnl'],errors='coerce') if len(trades) else pd.Series(dtype=float); gp=float(pnlcol[pnlcol>0].sum()) if len(pnlcol) else 0.; gl=-float(pnlcol[pnlcol<0].sum()) if len(pnlcol) else 0.; pf=gp/gl if gl>0 else (None if gp==0 else float('inf'))
public={'version':s['version'],'as_of':s['last_processed_date'],'initial_capital':INITIAL,'cash':round(float(s['cash']),2),'market_value':round(float(s['equity'])-float(s['cash']),2),'equity':round(float(s['equity']),2),'total_return':float(s['equity'])/INITIAL-1,'realized_pnl':round(float(s['realized_pnl']),2),'peak_equity':round(float(s['peak_equity']),2),'current_drawdown':float(s['equity'])/max(float(s['peak_equity']),1e-9)-1,'max_drawdown':float(s['max_drawdown']),'closed_trades':closed,'wins':wins,'losses':int(s['losses']),'win_rate':wr,'profit_factor':pf,'loss_streak':int(s['loss_streak']),'risk_multiplier':risk_mult(s,latest),'open_positions':s['positions'],'pending_orders':s['pending_orders'],'latest_actions':actions[-30:],'data_valid':bool(manifest.get('data_valid')),'model':'A100 V7 FROZEN / Forward Account V1','rules':{'risk_per_trade':BASE_RISK,'max_position_pct':MAX_POS_PCT,'max_positions':MAX_POS,'max_per_mainline':MAX_MAINLINE,'entry':'next trading day open','stop':'1.5 ATR','target':'1.5R','max_hold_days':MAX_HOLD,'slippage_each_side':SLIP,'commission_each_side':COMM,'stamp_duty_sell_side_current':.0005,'drawdown_controls':'-8% half risk; -12% no new entries','loss_streak_controls':'5 losses half risk; 8 losses pause 10 trading days'}}
(FORWARD_DIR/'account.json').write_text(json.dumps(public,ensure_ascii=False,indent=2),encoding='utf-8'); trades.to_csv(FORWARD_DIR/'account_trades.csv',index=False); eqcurve.to_csv(FORWARD_DIR/'account_equity.csv',index=False)
pos=pd.DataFrame(s['positions']); pend=pd.DataFrame(s['pending_orders']); metrics=[('Date',public['as_of']),('Equity',f"¥{public['equity']:,.2f}"),('Total return',f"{public['total_return']:.2%}"),('Cash',f"¥{public['cash']:,.2f}"),('Open positions',len(s['positions'])),('Pending orders',len(s['pending_orders'])),('Closed trades',closed),('Win rate','—' if wr is None else f'{wr:.2%}'),('Profit factor','—' if pf is None else ('∞' if pf==float('inf') else f'{pf:.3f}')),('Max drawdown',f"{public['max_drawdown']:.2%}"),('Loss streak',public['loss_streak']),('Risk multiplier',public['risk_multiplier'])]
html='''<!doctype html><meta charset="utf-8"><title>A100 Forward Account V1</title><style>body{font-family:system-ui;max-width:1100px;margin:36px auto;padding:0 20px}table{border-collapse:collapse;width:100%;margin:15px 0 30px}td,th{border:1px solid #ddd;padding:8px;text-align:left}h1,h2{margin-top:28px}.muted{color:#666}</style><h1>A100 Forward 模拟账户 V1</h1><p class="muted">Frozen V7 · Research/paper trading only · ¥1,000,000 initial capital</p>'''
html+=pd.DataFrame(metrics,columns=['Metric','Value']).to_html(index=False,escape=True); html+='<h2>Open positions</h2>'+(pos.to_html(index=False,escape=True) if len(pos) else '<p>None.</p>'); html+='<h2>Pending next-open orders</h2>'+(pend.to_html(index=False,escape=True) if len(pend) else '<p>None.</p>'); html+='<p><a href="index.html">Signal page</a> · <a href="account.json">account.json</a> · <a href="account_trades.csv">trade log</a> · <a href="account_equity.csv">equity curve</a></p>'
(FORWARD_DIR/'account.html').write_text(html,encoding='utf-8'); print(json.dumps(public,ensure_ascii=False,indent=2))
