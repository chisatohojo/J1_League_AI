"""Fixed rolling comparison of Elo-only and Elo plus absolute Elo parity."""
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

VALIDATION_SEASONS = (2020, 2021, 2022, 2023, 2024)
EXPECTED_VALIDATION_COUNTS = {2020:306, 2021:380, 2022:306, 2023:306, 2024:380}
ELO_FEATURES = ("elo_diff",)
PARITY_FEATURES = ("elo_diff", "abs_elo_diff")
K_FACTOR, HOME_ADVANTAGE = 30.0, 175.0

@dataclass(frozen=True)
class ParityRollingResult:
    fold_metrics: dict[int, dict[str, FormLogisticMetrics]]
    pooled_metrics: dict[str, FormLogisticMetrics]
    fold_counts: dict[int, tuple[int, int]]
    pooled_predictions: pd.DataFrame

def _metrics(target, probabilities):
    target, probabilities = np.asarray(target), np.asarray(probabilities)
    if probabilities.shape[1] != 3 or not np.allclose(probabilities.sum(1), 1):
        raise ValueError("Expected three-class probabilities summing to one")
    one_hot = (target[:, None] == np.asarray(CLASS_ORDER)).astype(float)
    return FormLogisticMetrics(float(accuracy_score(target, np.asarray(CLASS_ORDER)[probabilities.argmax(1)])),
                               float(log_loss(target, probabilities, labels=list(CLASS_ORDER))),
                               float(np.mean(np.sum((probabilities-one_hot)**2, axis=1))))

def _load_j1(processed_dir, master):
    frames=[]
    for season in range(2015,2025):
        f=pd.read_csv(Path(processed_dir)/f"{season}_matches_probe.csv")
        f["match_date"]=pd.to_datetime(f.match_date,errors="raise").dt.normalize()
        f["home_team_id"]=[master.resolve_team_id(n,source="jleague_data_site",on=d.date()) for n,d in zip(f.home_team,f.match_date)]
        f["away_team_id"]=[master.resolve_team_id(n,source="jleague_data_site",on=d.date()) for n,d in zip(f.away_team,f.match_date)]
        frames.append(f[["match_id","season","match_date","home_team_id","away_team_id","result"]])
    result=pd.concat(frames,ignore_index=True).sort_values(["match_date","match_id"],kind="stable").reset_index(drop=True)
    if result.match_id.duplicated().any(): raise ValueError("J1 match_id must be unique")
    return result

def _replay_elo(matches):
    elo=EloRatings(sorted(set(matches.home_team_id)|set(matches.away_team_id)),k_factor=K_FACTOR,home_advantage=HOME_ADVANTAGE)
    rows=[]
    for r in matches.sort_values(["match_date","match_id"],kind="stable").itertuples(index=False):
        before=elo.pre_match(r.home_team_id,r.away_team_id)
        rows.append((str(r.match_id),before.home_rating-before.away_rating))
        elo.update(r.home_team_id,r.away_team_id,r.result)
    return pd.DataFrame(rows,columns=["match_id","elo_diff"])

def _fit_predict(train, validation, columns):
    model=Pipeline([("scaler",StandardScaler()),("logistic",LogisticRegression(C=1,solver="lbfgs",max_iter=1000,random_state=0))])
    model.fit(train.loc[:,columns],train.result)
    if not np.array_equal(model.classes_,CLASS_ORDER): raise ValueError("Expected class order [0, 1, 2]")
    return model.predict_proba(validation.loc[:,columns])

def run_logistic_elo_parity_rolling_validation(*,processed_dir="data/processed/jleague"):
    """Evaluate only 2015-2024 J1 data; 2025 and 2026 are never read."""
    base=_load_j1(processed_dir,load_team_master())
    replay=_replay_elo(base).set_index("match_id")
    base["elo_diff"]=base.match_id.astype(str).map(replay.elo_diff)
    base["abs_elo_diff"]=base.elo_diff.abs()
    folds,counts={},{}
    pooled={"elo_only":[],"elo_parity":[]}; targets=[]; records=[]
    for year in VALIDATION_SEASONS:
        train=base.loc[base.season<year].copy(); val=base.loc[base.season==year].copy()
        if len(val)!=EXPECTED_VALIDATION_COUNTS[year]: raise ValueError(f"Unexpected validation count {year}")
        counts[year]=(len(train),len(val)); target=val.result.to_numpy(copy=True); targets.append(target)
        probs={"elo_only":_fit_predict(train,val,ELO_FEATURES),"elo_parity":_fit_predict(train,val,PARITY_FEATURES)}
        folds[year]={k:_metrics(target,p) for k,p in probs.items()}
        for name,p in probs.items(): pooled[name].append(p)
        for i,r in enumerate(val.itertuples(index=False)):
            records.append((r.match_id,year,r.result,probs["elo_only"][i],probs["elo_parity"][i],r.elo_diff))
    target=np.concatenate(targets); pooled_metrics={k:_metrics(target,np.concatenate(v)) for k,v in pooled.items()}
    pred=pd.DataFrame(records,columns=["match_id","season","result","elo_only_prob","elo_parity_prob","elo_diff"])
    for name in ("elo_only","elo_parity"):
        p=np.vstack(pred[f"{name}_prob"]); pred[f"{name}_p_true"]=p[np.arange(len(pred)),pred.result.to_numpy()]; pred[f"{name}_nll"]=-np.log(np.clip(pred[f"{name}_p_true"],1e-15,1))
    if len(pred)!=1678: raise ValueError("Expected pooled OOF count 1,678")
    return ParityRollingResult(folds,pooled_metrics,counts,pred)
