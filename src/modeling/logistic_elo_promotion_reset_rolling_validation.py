"""One-shot evaluation of a 1500 Elo reset for returning J1 clubs.

Only J1 2015-2024 data is used. At a season boundary, a club absent from the
previous J1 season but seen in an earlier J1 season is reset to 1500 before
its first current-season match. No promotion flag is passed to the model.
"""
from dataclasses import dataclass
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, log_loss
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from src.collect.teams import load_team_master
from src.features.elo import EloRatings
from src.modeling.logistic_form import CLASS_ORDER, FormLogisticMetrics

VALIDATION_SEASONS=(2020,2021,2022,2023,2024)
EXPECTED_VALIDATION_COUNTS={2020:306,2021:380,2022:306,2023:306,2024:380}
FEATURES=("elo_diff",); K_FACTOR=30.0; HOME_ADVANTAGE=175.0

@dataclass(frozen=True)
class PromotionResetResult:
    fold_metrics: dict[int,dict[str,FormLogisticMetrics]]
    pooled_metrics: dict[str,FormLogisticMetrics]
    fold_counts: dict[int,tuple[int,int]]
    promoted_metrics: dict[str,dict[str,FormLogisticMetrics]]
    appearance_metrics: dict[str,dict[str,FormLogisticMetrics]]
    transitions: pd.DataFrame

def _load_j1(processed_dir,master):
    fs=[]
    for y in range(2015,2025):
        f=pd.read_csv(Path(processed_dir)/f"{y}_matches_probe.csv")
        f["match_date"]=pd.to_datetime(f.match_date,errors="raise").dt.normalize()
        f["home_team_id"]=[master.resolve_team_id(n,source="jleague_data_site",on=d.date()) for n,d in zip(f.home_team,f.match_date)]
        f["away_team_id"]=[master.resolve_team_id(n,source="jleague_data_site",on=d.date()) for n,d in zip(f.away_team,f.match_date)]
        fs.append(f[["match_id","season","match_date","home_team_id","away_team_id","result"]])
    out=pd.concat(fs,ignore_index=True).sort_values(["match_date","match_id"],kind="stable").reset_index(drop=True)
    if out.match_id.duplicated().any(): raise ValueError("J1 match_id must be unique")
    return out

def _metrics(y,p):
    y=np.asarray(y); p=np.asarray(p)
    if p.shape[1]!=3 or not np.allclose(p.sum(1),1): raise ValueError("Invalid probabilities")
    one=(y[:,None]==np.asarray(CLASS_ORDER)).astype(float)
    return FormLogisticMetrics(float(accuracy_score(y,np.asarray(CLASS_ORDER)[p.argmax(1)])),float(log_loss(y,p,labels=list(CLASS_ORDER))),float(np.mean(np.sum((p-one)**2,axis=1))))

def _replay(matches, memberships, reset):
    elo=EloRatings(sorted(set(matches.home_team_id)|set(matches.away_team_id)),k_factor=K_FACTOR,home_advantage=HOME_ADVANTAGE)
    seen=set(); last_season=None; rows=[]; transitions=[]
    for r in matches.sort_values(["match_date","match_id"],kind="stable").itertuples(index=False):
        if r.season!=last_season:
            if r.season>=2016:
                returning=(memberships[r.season]-memberships[r.season-1]) & seen
                for team in sorted(returning):
                    elo._ratings[team]=1500.0 if reset else elo._ratings[team]
                    transitions.append((r.season,team,elo._ratings[team],reset))
            last_season=r.season
        b=elo.pre_match(r.home_team_id,r.away_team_id)
        rows.append((str(r.match_id),b.home_rating-b.away_rating))
        seen.update((r.home_team_id,r.away_team_id)); elo.update(r.home_team_id,r.away_team_id,r.result)
    return pd.DataFrame(rows,columns=["match_id","elo_diff"]),transitions

def _fit(train,val):
    model=Pipeline([("scaler",StandardScaler()),("logistic",LogisticRegression(C=1,solver="lbfgs",max_iter=1000,random_state=0))])
    model.fit(train[["elo_diff"]],train.result)
    if not np.array_equal(model.classes_,CLASS_ORDER): raise ValueError("Expected class order [0,1,2]")
    return model.predict_proba(val[["elo_diff"]])

def run_logistic_elo_promotion_reset_rolling_validation(*,processed_dir="data/processed/jleague"):
    master=load_team_master(); base=_load_j1(processed_dir,master)
    memberships={y:set(base.loc[base.season==y,"home_team_id"])|set(base.loc[base.season==y,"away_team_id"]) for y in range(2015,2025)}
    current,recs=_replay(base,memberships,False); reset,_=_replay(base,memberships,True)
    base["current_elo_diff"]=base.match_id.astype(str).map(current.set_index("match_id").elo_diff)
    base["reset_elo_diff"]=base.match_id.astype(str).map(reset.set_index("match_id").elo_diff)
    fold_metrics={}; counts={}; pooled={"current":[],"reset":[]}; targets=[]; pred=[]
    for y in VALIDATION_SEASONS:
        tr=base.loc[base.season<y]; va=base.loc[base.season==y].copy();
        if len(va)!=EXPECTED_VALIDATION_COUNTS[y]: raise ValueError(f"Unexpected validation count {y}")
        counts[y]=(len(tr),len(va)); target=va.result.to_numpy(copy=True); targets.append(target)
        ps={}
        for name,col in (("current","current_elo_diff"),("reset","reset_elo_diff")):
            train=tr.rename(columns={col:"elo_diff"}); valid=va.rename(columns={col:"elo_diff"}); ps[name]=_fit(train,valid); pooled[name].append(ps[name])
        fold_metrics[y]={k:_metrics(target,p) for k,p in ps.items()}
        for i,r in enumerate(va.itertuples(index=False)): pred.append((str(r.match_id),y,r.result,ps["current"][i],ps["reset"][i],r.home_team_id,r.away_team_id))
    y=np.concatenate(targets); pooled_metrics={k:_metrics(y,np.concatenate(v)) for k,v in pooled.items()}
    p=pd.DataFrame(pred,columns=["match_id","season","result","current_prob","reset_prob","home_team_id","away_team_id"])
    promoted_metrics={}; appearance_metrics={}
    for variant in ("current","reset"):
        probs=np.vstack(p[variant+"_prob"]); p[variant+"_nll"]=-np.log(np.clip(probs[np.arange(len(p)),p.result],1e-15,1)); p[variant+"_correct"]=(probs.argmax(1)==p.result); p[variant+"_brier"]=[np.sum((a-(b==np.arange(3)))**2) for a,b in zip(probs,p.result)]
    p["type"]="none"; p["appearance_no"]=0
    for y0 in VALIDATION_SEASONS:
        promoted=memberships[y0]-memberships[y0-1]; counts2={t:0 for t in promoted}; ix=p.season.eq(y0)
        for idx,r in p.loc[ix].iterrows():
            involved=[t for t in (r.home_team_id,r.away_team_id) if t in promoted]
            for t in (r.home_team_id,r.away_team_id):
                if t in counts2: counts2[t]+=1
            if involved:
                prior_ids=set(base.loc[base.season<y0,"home_team_id"])|set(base.loc[base.season<y0,"away_team_id"])
                p.at[idx,"type"]="returning" if any(t in prior_ids for t in involved) else "first-time"
                p.at[idx,"appearance_no"]=min(counts2[t] for t in involved)
    for typ in ("none","first-time","returning"):
        promoted_metrics[typ]={v:_metrics(p.loc[p.type.eq(typ),"result"],np.vstack(p.loc[p.type.eq(typ),v+"_prob"])) for v in ("current","reset")}
    for bucket,mask in (("1-3",(p.appearance_no>=1)&(p.appearance_no<=3)),("4-10",(p.appearance_no>=4)&(p.appearance_no<=10)),("11+",p.appearance_no>=11)):
        appearance_metrics[bucket]={v:_metrics(p.loc[mask,"result"],np.vstack(p.loc[mask,v+"_prob"])) for v in ("current","reset")}
    return PromotionResetResult(fold_metrics,pooled_metrics,counts,promoted_metrics,appearance_metrics,pd.DataFrame(recs,columns=["season","team_id","reset_rating","is_reset"]))
