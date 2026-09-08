import numpy as np, pandas as pd, os, time, gc
from scipy.stats import rankdata
from sklearn.cluster import MiniBatchKMeans
from sklearn.decomposition import PCA
from parquet_minread import read_column

BASE='/mnt/data/A100_complete_results'; OUT='/mnt/data/A100_v5_results'; os.makedirs(OUT,exist_ok=True)
z=np.load(BASE+'/A100_canonical_context.npz',allow_pickle=False)
starts=z['starts']; ends=z['ends']; op=z['op']; hi=z['hi']; lo=z['lo']; cl=z['cl']; atr=z['atr20']; base=z['base']; core_norm=z['core']; dc=z['date_code']; ud=z['unique_dates']; symbols=z['symbols']; mscore=z['mscore']; regime_daily=z['regime']; setup=z['setup_type']
N=len(symbols); D=len(ud); n=len(cl)
print('A100 V5 PIT-proxy prep',N,D,n,flush=True)
# row -> symbol id
sid=np.empty(n,np.int16)
for i,(a,b) in enumerate(zip(starts,ends)): sid[a:b]=i
# dense close/high matrices; only ~72MB each pair
C=np.full((D,N),np.nan,np.float32); H=np.full((D,N),np.nan,np.float32)
C[dc,sid]=cl; H[dc,sid]=hi
# daily returns matrix and trailing returns
R1=np.full_like(C,np.nan)
R1[1:]=C[1:]/C[:-1]-1
R5=C/np.vstack([np.full((5,N),np.nan,np.float32),C[:-5]])-1
R20=C/np.vstack([np.full((20,N),np.nan,np.float32),C[:-20]])-1
# MA20 by rolling cumulative sum/count
valid=np.isfinite(C); x=np.nan_to_num(C,nan=0.0).astype(np.float64)
cs=np.vstack([np.zeros((1,N),np.float64),np.cumsum(x,axis=0)])
cc=np.vstack([np.zeros((1,N),np.int32),np.cumsum(valid.astype(np.int32),axis=0)])
MA20=np.full_like(C,np.nan)
sums=cs[20:]-cs[:-20]; cnts=cc[20:]-cc[:-20]; ok=cnts==20; tmp=np.full_like(sums,np.nan,dtype=np.float32); tmp[ok]=(sums[ok]/20).astype(np.float32); MA20[19:]=tmp
del x,cs,cc,sums,cnts,tmp; gc.collect()
ABOVE=(C>MA20)
# amount20: read raw amount, dense, rolling using per-symbol to keep memory controlled
amt=read_column('/mnt/data/A100_2020_2026_raw.parquet','amount',np.float32)
A=np.full((D,N),np.nan,np.float32); A[dc,sid]=amt; del amt
# rolling amount mean via cumsum
va=np.isfinite(A); xa=np.nan_to_num(A,nan=0.0).astype(np.float64)
cs=np.vstack([np.zeros((1,N),np.float64),np.cumsum(xa,axis=0)]); cc=np.vstack([np.zeros((1,N),np.int32),np.cumsum(va.astype(np.int32),axis=0)])
AM20=np.full_like(A,np.nan); sums=cs[20:]-cs[:-20]; cnts=cc[20:]-cc[:-20]; ok=cnts==20; tmp=np.full_like(sums,np.nan,dtype=np.float32); tmp[ok]=(sums[ok]/20).astype(np.float32); AM20[19:]=tmp
del A,va,xa,cs,cc,sums,cnts,tmp; gc.collect()
# global daily amount rank for leader liquidity
a_rank=np.full((D,N),np.nan,np.float32)
for t in range(D):
    a=AM20[t]; ok=np.isfinite(a)
    if ok.any(): a_rank[t,ok]=(rankdata(a[ok],method='average')/ok.sum()).astype(np.float32)
# PIT dynamic co-movement clusters, rebalance every 60 trading days, trailing 60 daily returns
cluster=np.full((D,N),-1,np.int16)
rebal=list(range(120,D,60))
cluster_meta=[]
last_labels=None
for ri,t0 in enumerate(rebal):
    t1=rebal[ri+1] if ri+1<len(rebal) else D
    X=R1[t0-60:t0].T.astype(np.float32)
    cnt=np.isfinite(X).sum(1); good=cnt>=45
    Xg=X[good]
    # cross-time demean/std stock series, fill missing with 0 after standardization
    mu=np.nanmean(Xg,axis=1,keepdims=True); sd=np.nanstd(Xg,axis=1,keepdims=True); sd=np.where(sd<1e-4,1e-4,sd)
    Xg=(Xg-mu)/sd; Xg=np.nan_to_num(Xg,nan=0.0,posinf=0.0,neginf=0.0)
    # PCA preserves co-movement shape; fixed seed ensures reproducibility
    pca=PCA(n_components=12,random_state=42)
    Z=pca.fit_transform(Xg)
    k=30
    km=MiniBatchKMeans(n_clusters=k,random_state=42,batch_size=1024,n_init=3,max_iter=150)
    lab=km.fit_predict(Z)
    labels=np.full(N,-1,np.int16); labels[np.flatnonzero(good)]=lab.astype(np.int16)
    cluster[t0:t1]=labels
    sizes=np.bincount(lab,minlength=k)
    cluster_meta.append((t0,t1,int(good.sum()),int(sizes.min()),int(np.median(sizes)),int(sizes.max()),float(pca.explained_variance_ratio_.sum())))
    print('cluster',ri+1,'/',len(rebal),'date',pd.to_datetime(ud[t0],unit='us').date(),'stocks',good.sum(),'sizes',sizes.min(),int(np.median(sizes)),sizes.max(),flush=True)
# dates before first cluster unavailable -> V5 base starts at rebalance 120
ind_score=np.full((D,N),np.nan,np.float32); leader_score=np.full((D,N),np.nan,np.float32)
for t in range(120,D):
    labs=cluster[t]; validlab=labs>=0
    if not validlab.any(): continue
    k=int(labs[validlab].max())+1
    # cluster stats for ret20, ret5, breadth above MA20
    def stats(v):
        ok=validlab & np.isfinite(v)
        cnt=np.bincount(labs[ok],minlength=k).astype(np.float32)
        sm=np.bincount(labs[ok],weights=v[ok],minlength=k).astype(np.float32)
        sm2=np.bincount(labs[ok],weights=(v[ok]**2),minlength=k).astype(np.float32)
        mean=np.divide(sm,cnt,out=np.full(k,np.nan,np.float32),where=cnt>0)
        var=np.divide(sm2,cnt,out=np.full(k,np.nan,np.float32),where=cnt>0)-mean**2
        std=np.sqrt(np.maximum(var,1e-8)).astype(np.float32)
        return mean,std,cnt
    m20,s20,c20=stats(R20[t]); m5,s5,c5=stats(R5[t])
    okb=validlab & np.isfinite(MA20[t]) & np.isfinite(C[t])
    cb=np.bincount(labs[okb],minlength=k).astype(np.float32); sb=np.bincount(labs[okb],weights=ABOVE[t,okb].astype(np.float32),minlength=k).astype(np.float32)
    br=np.divide(sb,cb,out=np.full(k,np.nan,np.float32),where=cb>0)
    # cluster cross-sectional percentile ranks
    def cr(x):
        out=np.zeros(k,np.float32); ok=np.isfinite(x)
        if ok.any(): out[ok]=(rankdata(x[ok],method='average')/ok.sum()).astype(np.float32)
        return out
    q20=cr(m20); q5=cr(m5)
    iscore=np.clip(q20*5 + q5*3 + np.clip((br-.35)/.35,0,1)*4,0,12).astype(np.float32)
    ii=np.flatnonzero(validlab); l=labs[ii]
    ind_score[t,ii]=iscore[l]
    # leader: relative 20d (4), relative 5d (2), liquidity rank (2), positive multi-horizon consistency (2)
    r20=R20[t,ii]; r5=R5[t,ii]; ar=a_rank[t,ii]
    z20=(r20-m20[l])/np.maximum(s20[l],1e-4); z5=(r5-m5[l])/np.maximum(s5[l],1e-4)
    p20=np.select([z20>=.75,z20>=.25,z20>=-.25],[4.,3.,1.],default=0.)
    p5=np.select([z5>=.75,z5>=.25],[2.,1.],default=0.)
    pliq=np.select([ar>=.80,ar>=.50],[2.,1.],default=0.)
    pcons=((r20>0)&(r5>0)).astype(np.float32)*2
    leader_score[t,ii]=np.clip(p20+p5+pliq+pcons,0,10).astype(np.float32)
    if t%250==0: print('scores date',t,flush=True)
# map dense scores back to row order
is_row=ind_score[dc,sid]; ls_row=leader_score[dc,sid]
raw78=(core_norm/100*78).astype(np.float32)
v5=(raw78+np.nan_to_num(is_row,nan=0.0)+np.nan_to_num(ls_row,nan=0.0)).astype(np.float32)
# valid V5 requires cluster available and original base hard filters; PIT proxy ST filter unavailable separately
v5base=base & np.isfinite(is_row) & np.isfinite(ls_row)
print('V5 score dist',np.nanpercentile(v5[v5base],[1,5,25,50,75,90,95,99]),flush=True)
for th in [60,65,70,75,80,85,88,90]: print('thr',th,'signals',int((v5base&(v5>=th)).sum()),flush=True)
np.savez_compressed(OUT+'/A100_V5_context.npz',starts=starts,ends=ends,op=op,hi=hi,lo=lo,cl=cl,atr20=atr,v5base=v5base,v5=v5,core=core_norm,industry=is_row,leader=ls_row,date_code=dc,unique_dates=ud,symbols=symbols,mscore=mscore,regime=regime_daily,setup_type=setup,cluster=cluster)
pd.DataFrame(cluster_meta,columns=['start_ix','end_ix','stocks','min_cluster','median_cluster','max_cluster','pca_var12']).to_csv(OUT+'/A100_V5_cluster_audit.csv',index=False)
print('saved context',flush=True)
