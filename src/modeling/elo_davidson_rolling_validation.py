"""One-shot Davidson draw model using the fixed J1-only Elo replay."""

from dataclasses import dataclass
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.optimize import minimize_scalar
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, log_loss
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from src.collect.teams import load_team_master
from src.features.elo import EloRatings
from src.modeling.logistic_form import CLASS_ORDER, FormLogisticMetrics

VALIDATION_SEASONS=(2020,2021,2022,2023,2024)
EXPECTED_VALIDATION_COUNTS={2020:306,2021:380,2022:306,2023:306,2024:380}
K_FACTOR=30.0; HOME_ADVANTAGE=175.0; ELO_SCALE=400.0


@dataclass(frozen=True)
class DavidsonResult:
    fold_metrics: dict
    pooled_metrics: dict
    fold_counts: dict
    fitted_nu: dict
    draw_diagnostics: dict
    near_even: dict
    draw_calibration: dict


def davidson_probabilities(home_elo, away_elo, nu, *, home_advantage=HOME_ADVANTAGE):
    if not np.isfinite(nu) or nu <= 0: raise ValueError("nu must be finite and positive")
    h=10.0**((np.asarray(home_elo,dtype=float)+home_advantage)/ELO_SCALE); a=10.0**(np.asarray(away_elo,dtype=float)/ELO_SCALE)
    tie=nu*np.sqrt(h*a); denominator=h+a+tie
    # Existing class order: Away, Draw, Home.
    return np.column_stack((a/denominator,tie/denominator,h/denominator))


def _load_j1(processed_dir="data/processed/jleague"):
    master=load_team_master(); frames=[]
    for year in range(2015,2025):
        f=pd.read_csv(Path(processed_dir)/f"{year}_matches_probe.csv"); f["match_date"]=pd.to_datetime(f.match_date,errors="raise").dt.normalize()
        for side in ("home","away"):
            f[f"{side}_team_id"]=[master.resolve_team_id(n,source="jleague_data_site",on=d.date()) for n,d in zip(f[f"{side}_team"],f.match_date)]
        frames.append(f[["match_id","season","match_date","home_team_id","away_team_id","result"]])
    out=pd.concat(frames,ignore_index=True); out["match_id"]=out.match_id.astype(str); return out.sort_values(["match_date","match_id"],kind="stable").reset_index(drop=True)


def _replay(frame, end_season):
    f=frame[frame.season.le(end_season)]; ids=sorted(set(f.home_team_id)|set(f.away_team_id)); elo=EloRatings(ids,k_factor=K_FACTOR,home_advantage=HOME_ADVANTAGE); rows=[]
    for r in f.itertuples(index=False):
        b=elo.pre_match(r.home_team_id,r.away_team_id); rows.append((r.match_id,b.home_rating,b.away_rating)); elo.update(r.home_team_id,r.away_team_id,r.result)
    return pd.DataFrame(rows,columns=["match_id","home_elo","away_elo"])


def _fit_nu(home, away, target):
    target=np.asarray(target,dtype=int)
    def objective(theta):
        p=davidson_probabilities(home,away,float(np.exp(theta)))
        return float(-np.log(np.clip(p[np.arange(len(target)),target],1e-15,1.0)).sum())
    result=minimize_scalar(objective,method="bounded",bounds=(-20.0,20.0),options={"xatol":1e-12,"maxiter":1000})
    if not result.success: raise ValueError("nu optimization failed")
    return float(np.exp(result.x))


def _metrics(y,p):
    y=np.asarray(y,dtype=int); p=np.asarray(p,dtype=float); one=(y[:,None]==np.asarray(CLASS_ORDER)).astype(float)
    if not np.allclose(p.sum(axis=1),1): raise ValueError("probabilities do not sum to one")
    return FormLogisticMetrics(float(accuracy_score(y,np.asarray(CLASS_ORDER)[p.argmax(axis=1)])),float(log_loss(y,p,labels=list(CLASS_ORDER))),float(np.mean(np.sum((p-one)**2,axis=1))))


def _current_probabilities(train, valid):
    model=Pipeline([("scaler",StandardScaler()),("logistic",LogisticRegression(C=1,solver="lbfgs",max_iter=1000,random_state=0))]); model.fit(train[["elo_diff"]],train.result)
    if not np.array_equal(model.classes_,CLASS_ORDER): raise ValueError("class order must be [0,1,2]")
    return model.predict_proba(valid[["elo_diff"]])


def _draw_table(y,p):
    result={}
    for label,mask in (("draw",y==1),("non_draw",y!=1)):
        result[label]={"count":int(mask.sum()),"mean_predicted_draw":float(p[mask,1].mean()) if mask.any() else np.nan,"nll":float(-np.log(np.clip(p[mask,1],1e-15,1)).mean()) if label=="draw" and mask.any() else None}
    return result


def _calibration(y,p):
    edges=(0.0,0.1,0.2,0.3,0.4,1.0000001); out=[]
    for lo,hi in zip(edges[:-1],edges[1:]):
        mask=(p[:,1]>=lo)&(p[:,1]<hi); out.append({"bucket":f"{lo:.1f}-{min(hi,1.0):.1f}","count":int(mask.sum()),"mean_predicted_draw":float(p[mask,1].mean()) if mask.any() else np.nan,"empirical_draw_rate":float((y[mask]==1).mean()) if mask.any() else np.nan})
    return out


def run_elo_davidson_rolling_validation(*, processed_dir="data/processed/jleague"):
    data=_load_j1(processed_dir); folds={}; counts={}; nus={}; pooled_y=[]; pooled_current=[]; pooled_davidson=[]; near_masks=[]
    for year in VALIDATION_SEASONS:
        replay=_replay(data,year).set_index("match_id"); frame=data[data.season.le(year)].copy(); frame["home_elo"]=[replay.loc[str(k),"home_elo"] for k in frame.match_id]; frame["away_elo"]=[replay.loc[str(k),"away_elo"] for k in frame.match_id]; frame["elo_diff"]=frame.home_elo-frame.away_elo
        train=frame[frame.season<year]; valid=frame[frame.season.eq(year)].copy();
        if len(valid)!=EXPECTED_VALIDATION_COUNTS[year]: raise ValueError(f"unexpected validation count {year}")
        counts[year]=(len(train),len(valid)); y_train=train.result.to_numpy(copy=True); y_valid=valid.result.to_numpy(copy=True); nu=_fit_nu(train.home_elo.to_numpy(),train.away_elo.to_numpy(),y_train); nus[year]=nu
        p_current=_current_probabilities(train,valid); p_davidson=davidson_probabilities(valid.home_elo.to_numpy(),valid.away_elo.to_numpy(),nu); folds[year]={"current":_metrics(y_valid,p_current),"davidson":_metrics(y_valid,p_davidson)}; pooled_y.append(y_valid); pooled_current.append(p_current); pooled_davidson.append(p_davidson)
        near_masks.append(np.abs(p_current[:,2]-p_current[:,0])<0.05)
    y=np.concatenate(pooled_y); pc=np.vstack(pooled_current); pdv=np.vstack(pooled_davidson); pooled={"current":_metrics(y,pc),"davidson":_metrics(y,pdv)}
    near=np.concatenate(near_masks); near_result={"count":int(near.sum()),"current_log_loss":float(log_loss(y[near],pc[near],labels=list(CLASS_ORDER))),"davidson_log_loss":float(log_loss(y[near],pdv[near],labels=list(CLASS_ORDER)))}
    return DavidsonResult(folds,pooled,counts,nus,{"current":_draw_table(y,pc),"davidson":_draw_table(y,pdv)},near_result,{"current":_calibration(y,pc),"davidson":_calibration(y,pdv)})
