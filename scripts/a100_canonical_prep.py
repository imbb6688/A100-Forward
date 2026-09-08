import numpy as np,pandas as pd,os,time,gc
from scipy.stats import rankdata
from a100_io import read_column
PATH='/mnt/data/A100_2020_2026_raw.parquet'; OUT='/mnt/data/A100_complete_results';os.makedirs(OUT,exist_ok=True)
def roll(a,w,kind='mean',minp=None):
 s=pd.Series(a);r=s.rolling(w,min_periods=w if minp is None else minp);z=r.mean() if kind=='mean' else r.max() if kind=='max' else r.sum();return z.to_numpy(dtype=np.float32)
def pct(a,n):
 o=np.full(len(a),np.nan,np.float32)
 if len(a)>n:
  p=a[:-n];c=a[n:];ok=np.isfinite(p)&(p!=0)&np.isfinite(c);q=np.full(len(c),np.nan,np.float32);q[ok]=(c[ok]/p[ok]-1).astype(np.float32);o[n:]=q
 return o
def rank_date(v,dc,order,counts):
 out=np.full(len(v),np.nan,np.float32);pos=0
 for cnt in counts:
  idx=order[pos:pos+cnt];x=v[idx];ok=np.isfinite(x)
  if ok.any():
   rr=rankdata(x[ok],method='average')/ok.sum();temp=np.full(cnt,np.nan,np.float32);temp[ok]=rr.astype(np.float32);out[idx]=temp
  pos+=cnt
 return out

t=time.time(); print('read',flush=True)
sym=read_column(PATH,'ts_code'); dates=read_column(PATH,'trade_date'); op=read_column(PATH,'open',np.float32);hi=read_column(PATH,'high',np.float32);lo=read_column(PATH,'low',np.float32);cl=read_column(PATH,'close',np.float32);pre=read_column(PATH,'pre_close',np.float32);vol=read_column(PATH,'volume',np.float32);amt=read_column(PATH,'amount',np.float64)
n=len(cl);starts=np.r_[0,np.flatnonzero(sym[1:]!=sym[:-1])+1];ends=np.r_[starts[1:],n];symbols=sym[starts].astype(str); del sym
ud=np.unique(dates); mp={v:i for i,v in enumerate(ud.tolist())}; dc=np.fromiter((mp[v] for v in dates),count=n,dtype=np.int16);del dates;D=len(ud); counts=np.bincount(dc,minlength=D).astype(np.int32);order=np.argsort(dc,kind='stable').astype(np.int32)
ret5=np.full(n,np.nan,np.float32);ret10=np.full(n,np.nan,np.float32);ret20=np.full(n,np.nan,np.float32);ma20=np.full(n,np.nan,np.float32);ma60=np.full(n,np.nan,np.float32);ma120=np.full(n,np.nan,np.float32);slope10=np.full(n,np.nan,np.float32);atr=np.full(n,np.nan,np.float32);vr=np.full(n,np.nan,np.float32);amount20=np.full(n,np.nan,np.float64);hh=np.full(n,np.nan,np.float32);lim20=np.full(n,np.nan,np.float32);obs=np.empty(n,np.int16)
print('features',flush=True)
# limit pct vector based on symbol/date
cut=np.int64(pd.Timestamp('2020-08-24').value//1000)
for k,(a,b) in enumerate(zip(starts,ends)):
 c=cl[a:b];h=hi[a:b];l=lo[a:b];v=vol[a:b];am=amt[a:b]
 obs[a:b]=np.arange(1,b-a+1,dtype=np.int16);ret5[a:b]=pct(c,5);ret10[a:b]=pct(c,10);ret20[a:b]=pct(c,20)
 m20=roll(c,20);ma20[a:b]=m20;ma60[a:b]=roll(c,60);ma120[a:b]=roll(c,120);slope10[a:b]=pct(m20,10)
 prev=np.r_[np.nan,c[:-1]].astype(np.float32);tr=np.nanmax(np.vstack([np.abs(h-l),np.abs(h-prev),np.abs(l-prev)]),axis=0).astype(np.float32);atr[a:b]=roll(tr,20)
 vm=roll(v,20);vr[a:b]=np.divide(v,vm,out=np.full_like(v,np.nan),where=np.isfinite(vm)&(vm!=0));amount20[a:b]=pd.Series(am).rolling(20,min_periods=20).mean().to_numpy();hh[a:b]=pd.Series(h).shift(1).rolling(20,min_periods=20).max().to_numpy(dtype=np.float32)
 code=symbols[k]; pctlim=.30 if code.endswith('.BJ') else .20 if code.startswith('688') else .10
 lpct=np.full(b-a,pctlim,np.float32)
 if code.startswith(('300','301')):
  lpct=np.where(ud[dc[a:b]]>=cut,.20,.10).astype(np.float32)
 lup=np.round(pre[a:b]*(1+lpct),2); hit=np.isfinite(pre[a:b])&(h>=lup-.005);lim20[a:b]=pd.Series(hit.astype(np.int8)).rolling(20,min_periods=1).sum().to_numpy(dtype=np.float32)
 if k and k%1000==0:print(k,flush=True)
dist=cl/ma20-1; breakout=cl>hh; atrpct=atr/cl
# market exact V3
up=(cl>pre)&np.isfinite(pre); above=cl>ma20; dailyret=np.divide(cl,pre,out=np.full(n,np.nan,np.float32),where=np.isfinite(pre)&(pre!=0))-1
Nday=np.bincount(dc,minlength=D);adv=np.bincount(dc,weights=up.astype(np.int8),minlength=D);breadth20=np.bincount(dc,weights=above.astype(np.int8),minlength=D)/Nday;ta=np.bincount(dc,weights=np.nan_to_num(amt),minlength=D);finite=np.isfinite(dailyret);cnt=np.bincount(dc[finite],minlength=D);ew=np.bincount(dc[finite],weights=dailyret[finite],minlength=D)/np.maximum(cnt,1);adv_ratio=adv/Nday;ama=pd.Series(ta).rolling(20,min_periods=20).mean().to_numpy();idx=np.cumprod(1+np.clip(np.nan_to_num(ew),-.2,.2))*1000;i20=pd.Series(idx).rolling(20,min_periods=20).mean().to_numpy();i60=pd.Series(idx).rolling(60,min_periods=60).mean().to_numpy();trendm=(idx>i20)*4+(i20>i60)*4; breadthsc=np.select([breadth20>=.65,breadth20>=.55,breadth20>=.45,breadth20>=.35],[6,5,3,1],0);ar=ta/ama;liqsc=np.select([ar>=1.15,ar>=1,ar>=.85],[4,3,1],0);app=np.select([adv_ratio>=.60,adv_ratio>=.50],[2,1],0);mdaily=np.clip(trendm+breadthsc+liqsc+app,0,20).astype(np.float32);ms=mdaily[dc]
print('ranks',flush=True)
r5=rank_date(ret5,dc,order,counts);r10=rank_date(ret10,dc,order,counts);r20=rank_date(ret20,dc,order,counts);mom=((r5*.45+r10*.35+r20*.20)*10).astype(np.float32);del r5,r10,r20
amrank=rank_date(amount20,dc,order,counts);del order
trends=((cl>ma20)*4+(ma20>ma60)*4+(ma60>ma120)*4+(slope10>0)*4).astype(np.float32)
bsc=np.select([breakout&(vr>=1.5),breakout&(vr>=1.2),breakout],[12,10,7],0).astype(np.float32);pb=np.select([(dist>=-.015)&(dist<=.025)&(ma20>ma60)&(ret5>-.08),(dist>=-.035)&(dist<=.05)&(ma20>ma60)],[12,8],0).astype(np.float32);setscore=np.maximum(bsc,pb);settype=np.where(bsc>=pb,0,1).astype(np.int8)
liq=(np.clip((vr-.6)/1.0,0,1)*4+amrank*4).clip(0,8).astype(np.float32);risk=np.select([(atrpct>=.018)&(atrpct<=.045),(atrpct>=.012)&(atrpct<=.060),(atrpct>=.008)&(atrpct<=.080)],[7,5,3],1).astype(np.float32);crowd=np.select([(dist<=.05)&(lim20<=1),(dist<=.10)&(lim20<=2),(dist<=.15)&(lim20<=3)],[5,3,1],0).astype(np.float32)
# V3 fillna(0) for components
raw=np.nan_to_num(ms)+np.nan_to_num(trends)+np.nan_to_num(mom)+np.nan_to_num(setscore)+np.nan_to_num(liq)+np.nan_to_num(risk)+np.nan_to_num(crowd);core=np.clip(raw/78*100,0,100).astype(np.float32)
hard=(obs<120)|(amount20<5e7)|(dist>.20)|(cl<=0)|(~np.isfinite(atr)); base=(~hard)&(ms>=14); valid72=base&(core>=72)
print('signals72',valid72.sum(),'days',len(np.unique(dc[valid72])),'signals85',(base&(core>=85)).sum(),'days85',len(np.unique(dc[base&(core>=85)])),flush=True)
reg=np.where(mdaily>=17,0,np.where(mdaily>=14,1,np.where(mdaily>=10,2,3))).astype(np.int8)
np.savez_compressed(OUT+'/A100_canonical_context.npz',starts=starts,ends=ends,op=op,hi=hi,lo=lo,cl=cl,atr20=atr,base=base,core=core,date_code=dc,unique_dates=ud,symbols=np.asarray(symbols,dtype='U16'),mscore=ms,regime=reg,setup_type=settype)
print('saved',time.time()-t)
