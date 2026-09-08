import numpy as np,pandas as pd, os, json
from sklearn.ensemble import ExtraTreesRegressor
OUT='/mnt/data/A100_v7_results';os.makedirs(OUT,exist_ok=True)
f=np.load('/mnt/data/A100_v6_results/A100_V6_features.npz',allow_pickle=False); sc=np.load('/mnt/data/A100_v6_results/A100_V6_score_context.npz',allow_pickle=False)['score'].astype(float)
R=f['netR'].astype(float); yr=f['year']; dc=f['date_code_sig'].astype(int)
broad=f['gate']&(f['setup']==1)&(f['market']>=14)&(f['industry']>=9)&(sc>=75)
raw=np.column_stack([sc,f['core'],f['industry'],f['oldleader'],f['market'],f['dist'],f['ret5'],f['ret20'],f['atrpct'],f['volratio'],f['limit20']]).astype(float)
Xrank=np.full_like(raw,np.nan,dtype=np.float32)
for t in np.unique(dc[broad]):
 ix=np.flatnonzero(broad&(dc==t))
 for j in range(raw.shape[1]): Xrank[ix,j]=pd.Series(raw[ix,j]).rank(pct=True,method='average').to_numpy(dtype=np.float32)
X=np.column_stack([Xrank,sc/100.,f['industry']/12.,f['market']/20.,np.clip(f['dist'],-.2,.3),np.clip(f['atrpct'],0,.15),np.log1p(np.clip(f['volratio'],0,10))]).astype(np.float32)
train=broad&(yr<=2022)&np.isfinite(R); med=np.nanmedian(X[train],axis=0)
for j in range(X.shape[1]):
 bad=~np.isfinite(X[:,j]); X[bad,j]=med[j] if np.isfinite(med[j]) else .5
cnt=np.bincount(dc[train],minlength=dc.max()+1); w=np.ones(len(R),float);w[train]=1/np.maximum(cnt[dc[train]],1);w[train]*=train.sum()/w[train].sum()
# FROZEN V7 model specification. Never changed by forward data.
m=ExtraTreesRegressor(n_estimators=220,max_depth=4,min_samples_leaf=40,max_features=.8,n_jobs=-1,random_state=17)
m.fit(X[train],R[train],sample_weight=w[train]); p=np.full(len(R),np.nan,np.float32);p[broad]=m.predict(X[broad]).astype(np.float32)
np.savez_compressed(OUT+'/A100_V7_rank_context.npz',rank_score=p,broad=broad)
