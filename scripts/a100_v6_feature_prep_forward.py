import numpy as np,pandas as pd, os, gc
from a100_io import read_column
OUT='/mnt/data/A100_v6_results'; os.makedirs(OUT,exist_ok=True)
V5='/mnt/data/A100_v5_results/A100_V5_context.npz'; PATH='/mnt/data/A100_2020_2026_raw.parquet'
z=np.load(V5,allow_pickle=False)
starts=z['starts']; ends=z['ends']; op=z['op']; hi=z['hi']; lo=z['lo']; cl=z['cl']; atr=z['atr20']; base=z['v5base']; core=z['core']; industry=z['industry']; oldleader=z['leader']; dc=z['date_code']; ud=z['unique_dates']; symbols=z['symbols']; mscore=z['mscore']; setup=z['setup_type']; cluster=z['cluster']
n=len(cl); D=len(ud); N=len(symbols); dts=pd.to_datetime(ud,unit='us')
vol=read_column(PATH,'volume',np.float32); pre=read_column(PATH,'pre_close',np.float32)
ret5=np.full(n,np.nan,np.float32); ret20=np.full(n,np.nan,np.float32); dist=np.full(n,np.nan,np.float32); vr=np.full(n,np.nan,np.float32); lim20=np.zeros(n,np.float32)
for k,(a,b) in enumerate(zip(starts,ends)):
    c=cl[a:b]; v=vol[a:b]; L=b-a
    if L>5: ret5[a+5:b]=(c[5:]/c[:-5]-1).astype(np.float32)
    if L>20: ret20[a+20:b]=(c[20:]/c[:-20]-1).astype(np.float32)
    s=pd.Series(c.astype(float)); ma=s.rolling(20,min_periods=20).mean().to_numpy(); dist[a:b]=(c/ma-1).astype(np.float32)
    vm=pd.Series(v.astype(float)).rolling(20,min_periods=20).mean().to_numpy(); vr[a:b]=np.divide(v,vm,out=np.full(L,np.nan,float),where=np.isfinite(vm)&(vm!=0)).astype(np.float32)
    code=symbols[k]; lim=.30 if code.endswith('.BJ') else (.20 if code.startswith('688') else .10)
    lp=np.full(L,lim,np.float32)
    if code.startswith(('300','301')):
        cut=np.int64(pd.Timestamp('2020-08-24').value//1000); lp=np.where(ud[dc[a:b]]>=cut,.20,.10).astype(np.float32)
    lup=np.round(pre[a:b]*(1+lp),2); hit=np.isfinite(pre[a:b])&(hi[a:b]>=lup-.005)
    lim20[a:b]=pd.Series(hit.astype(np.int8)).rolling(20,min_periods=1).sum().to_numpy(dtype=np.float32)
del vol,pre;gc.collect(); atrpct=(atr/cl).astype(np.float32)
# Frozen PIT market gate.
r1=np.full(n,np.nan,np.float32)
for a,b in zip(starts,ends):
    c=cl[a:b]
    if b-a>1:r1[a+1:b]=(c[1:]/c[:-1]-1).astype(np.float32)
ok=np.isfinite(r1)&(np.abs(r1)<.5); cnt=np.bincount(dc[ok],minlength=D); ew=np.bincount(dc[ok],weights=r1[ok],minlength=D)/np.maximum(cnt,1)
idx=np.cumprod(1+np.clip(ew,-.15,.15))*1000.; s=pd.Series(idx); ma20=s.rolling(20).mean().to_numpy(); ma60=s.rolling(60).mean().to_numpy(); ma120=s.rolling(120).mean().to_numpy(); mr20=s.pct_change(20).to_numpy(); gate=(idx>ma20)&(ma20>ma60)&(ma60>ma120)&(mr20>0)
# Keep EVERY base signal so the latest close can be scored; compute netR only when future bars exist.
sig=np.flatnonzero(base).astype(np.int32); sid=np.searchsorted(starts,sig,side='right')-1
netR=np.full(len(sig),np.nan,np.float32)
for p,(sg,ss) in enumerate(zip(sig,sid)):
    if sg+1>=ends[ss]: continue
    ei=sg+1; entry=float(op[ei]); aa=float(atr[sg])
    if not(np.isfinite(entry) and entry>0 and np.isfinite(aa) and aa>0): continue
    stop=entry-1.5*aa; rps=1.5*aa; target=entry+1.8*rps; ex=None
    last=min(ei+5,ends[ss]-1)
    for j in range(ei+1,last+1):
        o,h,l,c=map(float,(op[j],hi[j],lo[j],cl[j]))
        if o<=stop: ex=o; break
        if o>=target: ex=o; break
        sh=l<=stop; th=h>=target
        if sh: ex=stop; break
        if th: ex=target; break
    if ex is None: ex=float(cl[last])
    buy=entry*1.0005; sell=ex*.9995; shares=max(100,np.floor(100000/buy/100)*100); ba=shares*buy; sa=shares*sell
    bc=max(5,ba*.00025); sc=max(5,sa*.00025); dt=pd.to_datetime(ud[dc[last]],unit='us'); stamp=.0005 if dt>=pd.Timestamp('2023-08-28') else .001
    netret=(sa-ba-bc-sc-sa*stamp)/ba; netR[p]=netret/(rps/entry)
F={'sig':sig,'sid':sid.astype(np.int16),'year':dts[dc[sig]].year.to_numpy(dtype=np.int16),'date_code_sig':dc[sig],
'core':core[sig].astype(np.float32),'industry':industry[sig].astype(np.float32),'oldleader':oldleader[sig].astype(np.float32),'market':mscore[sig].astype(np.float32),'setup':setup[sig].astype(np.int8),
'dist':dist[sig].astype(np.float32),'ret5':ret5[sig].astype(np.float32),'ret20':ret20[sig].astype(np.float32),'atrpct':atrpct[sig].astype(np.float32),'volratio':vr[sig].astype(np.float32),'limit20':lim20[sig].astype(np.float32),'gate':gate[dc[sig]],'netR':netR}
keep_de=np.zeros(len(sig),bool); last_by_sid=np.full(N,-9999,np.int32)
for i in range(len(sig)):
    ss=int(F['sid'][i]); t=int(F['date_code_sig'][i])
    if t-last_by_sid[ss]>=5: keep_de[i]=True; last_by_sid[ss]=t
F['deoverlap5']=keep_de
np.savez_compressed(OUT+'/A100_V6_features.npz',**F)
pd.DataFrame({'date':dts,'market_index':idx,'ma20':ma20,'ma60':ma60,'ma120':ma120,'ret20':mr20,'fulltrend_gate':gate}).to_csv(OUT+'/A100_V6_market_gate.csv',index=False)
