import numpy as np,pandas as pd, os
OUT='/mnt/data/A100_v6_results'; z=np.load(OUT+'/A100_V6_features.npz',allow_pickle=False)
R=z['netR'].astype(float); year=z['year']; de=z['deoverlap5']; gate=z['gate']
features=['core','industry','oldleader','market','dist','ret5','ret20','atrpct','volratio','limit20','setup']; X={k:z[k] for k in features}
bins={'core':np.array([0,55,60,65,70,75,80,85,88,90,95,101],float),'industry':np.array([-1,4,6,7,8,9,10,11,11.5,12.1],float),'oldleader':np.array([-1,.5,1.5,2.5,3.5,4.5,5.5,6.5,7.5,8.5,9.5,10.1],float),'market':np.array([13.5,14.5,15.5,16.5,17.5,18.5,19.5,20.5],float),'dist':np.array([-.50,-.05,-.015,.015,.04,.07,.10,.15,.20,.50],float),'ret5':np.array([-9,-.12,-.06,-.02,.01,.04,.07,.12,.20,9],float),'ret20':np.array([-9,-.20,-.10,-.03,.03,.08,.15,.25,.40,9],float),'atrpct':np.array([-1,.008,.012,.018,.025,.035,.045,.06,.08,.12,9],float),'volratio':np.array([-1,.6,.8,1.0,1.2,1.5,2.0,3.0,9],float),'limit20':np.array([-.1,.5,1.5,2.5,3.5,5.5,8.5,99],float),'setup':np.array([-.5,.5,1.5,2.5],float)}
train=(year<=2022)&de&gate&np.isfinite(R); train_years=[2020,2021,2022]
def ids(v,e):
 q=np.digitize(v,e[1:-1],right=False); q[~np.isfinite(v)]=-1; return q
def fit_map(feat,mask):
 v=X[feat].astype(float); e=bins[feat]; q=ids(v,e); nb=len(e)-1; vals=np.zeros(nb,float); glob=np.nanmean(R[mask])
 for b in range(nb):
  m=mask&(q==b); n=m.sum()
  if n: vals[b]=(np.nanmean(R[m])-glob)*(n/(n+750.0))
 return vals,q
rel=[]
for feat in features:
 cors=[]
 for yy in train_years:
  vals,q=fit_map(feat,train&(year!=yy)); me=train&(year==yy); qe=q[me]; pred=np.zeros(me.sum()); ok=qe>=0; pred[ok]=vals[qe[ok]]; rr=R[me]; good=np.isfinite(rr)&np.isfinite(pred)&(np.nanstd(pred)>1e-12); cors.append(np.corrcoef(pred[good],rr[good])[0,1] if good.sum()>20 else np.nan)
 med=np.nanmedian(cors); rel.append(max(0.,med))
w=np.array(rel,float); w=np.ones_like(w) if w.sum()<=0 else w; w=w/w.sum(); contrib=np.zeros(len(R),float); maps={}
for feat,ww in zip(features,w):
 vals,q=fit_map(feat,train); maps[feat]=vals; ok=q>=0; contrib[ok]+=ww*vals[q[ok]]
ref=np.sort(contrib[train]); score=np.searchsorted(ref,contrib,side='right')/len(ref)*100.; score=np.clip(score,0,100).astype(np.float32)
np.savez_compressed(OUT+'/A100_V6_score_context.npz',score=score,pred_effect=contrib.astype(np.float32),**{('map_'+k):maps[k].astype(np.float32) for k in features},**{('edges_'+k):bins[k].astype(np.float32) for k in features})
