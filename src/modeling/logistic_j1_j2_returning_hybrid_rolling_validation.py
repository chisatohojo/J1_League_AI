"""One-shot hybrid policy: carry J2 history for returners, reset first-timers.

J1 and J2 league matches update one Elo stream. A promoted club with any prior
J1 appearance carries its J2-season rating; a promoted club with no prior J1
appearance is reset to 1500 immediately before its first J1 season. J2 rows
are never Logistic targets. Cups, J3, AFC, 2025 and 2026 are excluded.
"""

from dataclasses import dataclass
import numpy as np
import pandas as pd

from src.collect.teams import load_team_master
from src.features.elo import EloRatings
from src.modeling.logistic_j1_j2_initial_prior_rolling_validation import (
    EXPECTED_VALIDATION_COUNTS, VALIDATION_SEASONS, _fit, _load_j1, _load_j2,
    _metrics, _replay, _stream,
)


@dataclass(frozen=True)
class ReturningHybridResult:
    fold_metrics: dict
    pooled_metrics: dict
    fold_counts: dict
    promotion_metrics: dict
    appearance_metrics: dict
    transitions: pd.DataFrame


def _membership(j1, j2):
    j1m = {y: set(j1.loc[j1.season.eq(y), "home_team_id"]) | set(j1.loc[j1.season.eq(y), "away_team_id"]) for y in range(2015, 2025)}
    j2m = {y: set(j2.loc[j2.season.eq(y), "home_team_id"]) | set(j2.loc[j2.season.eq(y), "away_team_id"]) for y in range(2015, 2025)}
    return j1m, j2m


def _replay_hybrid(stream, end_season, j1, j2):
    selected = stream[stream.season.le(end_season)]
    elo = EloRatings(sorted(set(selected.home_team_id) | set(selected.away_team_id)), k_factor=30.0, home_advantage=175.0)
    j1m, j2m = _membership(j1, j2)
    prior_j1 = set(); rows=[]; transitions=[]; current_season=None
    for r in selected.itertuples(index=False):
        if r.season != current_season:
            current_season = r.season
            if current_season >= 2016:
                promoted = j2m[current_season-1] & j1m[current_season]
                first_time = {t for t in promoted if t not in prior_j1}
                returning = promoted - first_time
                before = {t: elo._ratings[t] for t in promoted if t in elo._ratings}
                for team in first_time:
                    if team in elo._ratings: elo._ratings[team] = 1500.0
                transitions.append({"season":current_season,"promoted_ids":tuple(sorted(promoted)),"returning_ids":tuple(sorted(returning)),"first_time_ids":tuple(sorted(first_time)),"pre_boundary":before,"post_boundary":{t:elo._ratings[t] for t in promoted if t in elo._ratings}})
        before = elo.pre_match(r.home_team_id, r.away_team_id)
        rows.append((r.event_key,before.home_rating,before.away_rating))
        elo.update(r.home_team_id,r.away_team_id,r.result)
        if r.event_key.startswith("j1:"): prior_j1.update((r.home_team_id,r.away_team_id))
    return pd.DataFrame(rows,columns=["event_key","home_elo","away_elo"]), transitions


def _features(j1, stream, year, *, hybrid=False, j2=None):
    replay, transitions = (_replay_hybrid(stream, year, j1, j2) if hybrid else _replay(stream, year))
    lookup=replay.set_index("event_key"); out=j1[j1.season.le(year)].copy(deep=True)
    out["elo_diff"]=[lookup.loc[k,"home_elo"]-lookup.loc[k,"away_elo"] for k in out.event_key]
    return out, transitions


def _diagnostics(pred, j1, j2):
    j1m,j2m=_membership(j1,j2); first_seen={}
    for r in j1.sort_values(["match_date","event_key"]).itertuples(index=False):
        first_seen.setdefault(r.home_team_id,r.season); first_seen.setdefault(r.away_team_id,r.season)
    p=pred.copy(); p["category"]="none"; p["appearance_no"]=0
    for y in VALIDATION_SEASONS:
        promoted=j2m[y-1]&j1m[y]; counts={t:0 for t in promoted}
        for i,r in p[p.season.eq(y)].iterrows():
            involved=[t for t in (r.home_team_id,r.away_team_id) if t in promoted]
            if involved:
                for t in involved: counts[t]+=1
                p.at[i,"category"]="first-time" if all(first_seen.get(t,y)==y for t in involved) else "returning"
                p.at[i,"appearance_no"]=min(counts[t] for t in involved)
    promo={}; appearance={}
    for cat in ("returning","first-time","none"):
        q=p[p.category.eq(cat)]; promo[cat]={v:_metrics(q.result,np.vstack(q[f"{v}_prob"])) for v in ("current","equal_j1_j2","hybrid")} if len(q) else {}
    for label,mask in (("1-3",p.appearance_no.between(1,3)),("4-10",p.appearance_no.between(4,10)),("11+",p.appearance_no.ge(11))):
        q=p[mask]; appearance[label]={v:_metrics(q.result,np.vstack(q[f"{v}_prob"])) for v in ("current","equal_j1_j2","hybrid")} if len(q) else {}
    return promo,appearance


def run_logistic_j1_j2_returning_hybrid_rolling_validation(*, processed_dir="data/processed/jleague", j2_path="data/processed/jleague_j2/2015_2024_j2_matches.csv"):
    master=load_team_master(); j1=_load_j1(processed_dir,master); j2=_load_j2(j2_path); stream=_stream(j1,j2)
    folds={}; counts={}; pooled={v:[] for v in ("current","equal_j1_j2","hybrid")}; targets=[]; rows=[]; transitions=[]
    for y in VALIDATION_SEASONS:
        current,_=_features(j1,stream,y,hybrid=False); equal,_=_features(j1,stream,y,hybrid=False); hybrid,t=_features(j1,stream,y,hybrid=True,j2=j2); transitions.extend(t)
        val=current[current.season.eq(y)]
        if len(val)!=EXPECTED_VALIDATION_COUNTS[y]: raise ValueError(f"unexpected validation count {y}")
        counts[y]=(int((current.season<y).sum()),len(val)); target=val.result.to_numpy(copy=True); targets.append(target); ps={}
        # current must use J1-only replay, while equal uses the common J1+J2 stream.
        current,_=_features_j1_only(j1,y); equal,_=_features_equal(j1,stream,y)
        for name,frame in (("current",current),("equal_j1_j2",equal),("hybrid",hybrid)):
            ps[name]=_fit(frame[frame.season<y],frame[frame.season.eq(y)]); pooled[name].append(ps[name])
        folds[y]={v:_metrics(target,ps[v]) for v in ps}
        for i,r in enumerate(val.itertuples(index=False)): rows.append((str(r.match_id),y,int(r.result),r.home_team_id,r.away_team_id,*[ps[v][i] for v in ps]))
    y=np.concatenate(targets); pooled_metrics={v:_metrics(y,np.vstack(pooled[v])) for v in pooled}; pred=pd.DataFrame(rows,columns=["match_id","season","result","home_team_id","away_team_id"]+[f"{v}_prob" for v in pooled]); promo,appearance=_diagnostics(pred,j1,j2)
    return ReturningHybridResult(folds,pooled_metrics,counts,promo,appearance,pd.DataFrame(transitions))


def _features_j1_only(j1,year):
    replay,_=_replay(j1[j1.season.le(year)],year); l=replay.set_index("event_key"); o=j1[j1.season.le(year)].copy(deep=True); o["elo_diff"]=[l.loc[k,"home_elo"]-l.loc[k,"away_elo"] for k in o.event_key]; return o,[]


def _features_equal(j1,stream,year):
    replay,_=_replay(stream,year); l=replay.set_index("event_key"); o=j1[j1.season.le(year)].copy(deep=True); o["elo_diff"]=[l.loc[k,"home_elo"]-l.loc[k,"away_elo"] for k in o.event_key]; return o,[]
