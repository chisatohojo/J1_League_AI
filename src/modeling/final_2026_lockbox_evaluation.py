"""One-shot sequential evaluation of the frozen 2026 Model A and B.

Domestic rest deliberately excludes AFC.  Hyakunen matches are Elo-state and
domestic-chronology events only; they are never Logistic training targets.
"""
from pathlib import Path
import hashlib
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, log_loss, confusion_matrix
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from src.collect.teams import load_team_master
from src.features.elo import EloRatings

CLASS_ORDER=(0,1,2)
FEATURE_A=("elo_diff",)
FEATURE_B=("elo_diff","home_domestic_days_since_last_competitive_match","away_domestic_days_since_last_competitive_match","home_domestic_has_previous_competitive_match","away_domestic_has_previous_competitive_match")

FROZEN_TARGET_COUNT = 70
FROZEN_PREDICTIONS_PATH = Path(
    "data/processed/modeling/2026_27_interim_lockbox_predictions.csv"
)
FROZEN_PREDICTIONS_SHA256 = (
    "2f3e85eaf412afdcd9095891ce366aa75155773504205274015157119702ab14"
)
LIVE_SCHEDULE_COUNT = 380


def _read_strings(path):
    return pd.read_csv(path, dtype="string", keep_default_na=False)


def validate_live_2026_inputs(schedule_path, completed_path):
    """Validate one mutable 2026/27 publication without fixing its progress count."""
    schedule = _read_strings(schedule_path)
    completed_file = _read_strings(completed_path)
    required = {
        "match_id", "season", "round", "match_date", "home_team", "away_team",
        "home_score", "away_score", "result", "fixture_key", "status",
        "competition_key", "competition", "stage",
    }
    if schedule.columns.has_duplicates or required - set(schedule.columns):
        raise ValueError("invalid live 2026/27 schedule schema")
    if len(schedule) != LIVE_SCHEDULE_COUNT:
        raise ValueError("2026/27 schedule must contain all 380 fixtures")
    if schedule.fixture_key.eq("").any() or schedule.fixture_key.duplicated().any():
        raise ValueError("live schedule fixture_key must be complete and unique")
    known_match_ids = schedule.loc[schedule.match_id.ne(""), "match_id"]
    if known_match_ids.duplicated().any():
        raise ValueError("nonblank live match_id must be unique")
    if not schedule.status.isin(("scheduled", "candidate", "completed")).all():
        raise ValueError("invalid live schedule status")
    if schedule.home_team.eq(schedule.away_team).any():
        raise ValueError("a club cannot play itself")
    if not schedule.season.eq("2026").all():
        raise ValueError("invalid live season identity")
    if not schedule.competition_key.eq("j1_2026_2027").all():
        raise ValueError("invalid live competition identity")
    if not schedule.competition.eq("Ｊ１").all() or not schedule.stage.eq("full_season").all():
        raise ValueError("invalid live competition/stage")
    schedule_dates = pd.to_datetime(schedule.match_date, format="%Y-%m-%d", errors="coerce")
    if (schedule_dates.isna().any()
            or not schedule_dates.between(
                pd.Timestamp("2026-08-01"), pd.Timestamp("2027-06-30")
            ).all()):
        raise ValueError("invalid live schedule date")
    rounds = pd.to_numeric(schedule["round"], errors="coerce")
    if (rounds.isna().any() or not rounds.between(1, 38).all()
            or not rounds.value_counts().sort_index().eq(10).all()):
        raise ValueError("invalid 38-round schedule")

    clubs = set(schedule.home_team) | set(schedule.away_team)
    appearances = pd.concat([schedule.home_team, schedule.away_team], ignore_index=True)
    directed = schedule[["home_team", "away_team"]]
    if (len(clubs) != 20 or not appearances.value_counts().eq(38).all()
            or not schedule.home_team.value_counts().eq(19).all()
            or not schedule.away_team.value_counts().eq(19).all()
            or directed.duplicated().any()):
        raise ValueError("invalid 20-club double round-robin schedule")

    expected_completed = schedule.loc[schedule.status.eq("completed")].reset_index(drop=True)
    if not expected_completed.equals(completed_file):
        raise ValueError("completed_matches.csv must equal the live completed schedule subset")
    if (expected_completed.match_id.eq("").any()
            or expected_completed.match_id.duplicated().any()):
        raise ValueError("completed match_id must be complete and unique")
    if expected_completed[["match_date", "home_team", "away_team"]].eq("").any().any():
        raise ValueError("completed match identity is incomplete")
    if not expected_completed.home_score.str.fullmatch(r"[0-9]+").all():
        raise ValueError("invalid completed home score")
    if not expected_completed.away_score.str.fullmatch(r"[0-9]+").all():
        raise ValueError("invalid completed away score")
    if not expected_completed.result.isin(("0", "1", "2")).all():
        raise ValueError("invalid completed result")
    home_score = expected_completed.home_score.astype(int)
    away_score = expected_completed.away_score.astype(int)
    expected_result = pd.Series(
        np.where(home_score > away_score, "2", np.where(home_score < away_score, "0", "1")),
        dtype="string",
    )
    if not expected_completed.result.reset_index(drop=True).equals(expected_result):
        raise ValueError("completed score/result mismatch")
    return schedule, completed_file


def load_frozen_lockbox_target(
    completed_path, prediction_path=FROZEN_PREDICTIONS_PATH, *,
    expected_prediction_sha256=FROZEN_PREDICTIONS_SHA256,
):
    """Select the immutable target by saved prediction IDs, never by live ordering."""
    prediction_path = Path(prediction_path)
    digest = hashlib.sha256(prediction_path.read_bytes()).hexdigest()
    if digest != expected_prediction_sha256:
        raise ValueError("frozen prediction artifact SHA-256 mismatch")
    predictions = _read_strings(prediction_path)
    identity = ["match_id", "match_date", "home_team", "away_team", "actual_class"]
    if predictions.columns.has_duplicates or set(identity) - set(predictions.columns):
        raise ValueError("invalid frozen prediction artifact schema")
    if (len(predictions) != FROZEN_TARGET_COUNT or predictions.match_id.eq("").any()
            or predictions.match_id.duplicated().any()):
        raise ValueError("frozen prediction artifact must identify exactly 70 matches")

    completed = _read_strings(completed_path)
    if completed.columns.has_duplicates or "match_id" not in completed:
        raise ValueError("invalid live completed schema")
    if completed.match_id.eq("").any() or completed.match_id.duplicated().any():
        raise ValueError("live completed match_id must be complete and unique")
    indexed = completed.set_index("match_id", drop=False)
    missing = set(predictions.match_id) - set(indexed.index)
    if missing:
        raise ValueError("frozen target match IDs are absent from the live completed data")
    target = indexed.loc[predictions.match_id.tolist()].reset_index(drop=True)
    observed = target[["match_id", "match_date", "home_team", "away_team", "result"]].rename(
        columns={"result": "actual_class"}
    )
    if not observed.reset_index(drop=True).equals(predictions[identity].reset_index(drop=True)):
        raise ValueError("frozen target identity/result disagrees with saved predictions")
    return target

def _default_input_paths():
    return {
        "2025_j1": "data/processed/jleague/2025_matches_probe.csv",
        "2025_cup": "data/processed/jleague_cup/2025_jleague_cup_matches.csv",
        "2025_emperor": "data/processed/emperors_cup/2025_emperors_cup_matches.csv",
        "2026_cup": "data/processed/jleague_cup/2026_jleague_cup_matches.csv",
        "2026_emperor": "data/processed/emperors_cup/2026_emperors_cup_matches.csv",
        "hyakunen": "data/processed/jleague/2026_hyakunen/matches.csv",
        "live_completed": "data/processed/jleague/2026_27/completed_matches.csv",
        "schedule": "data/processed/jleague/2026_27/schedule.csv",
        "frozen_predictions": FROZEN_PREDICTIONS_PATH,
    }


def preflight_inputs(paths=None, *, expected_prediction_sha256=FROZEN_PREDICTIONS_SHA256):
    """Validate immutable evaluation inputs and the separate mutable live source."""
    paths = _default_input_paths() if paths is None else paths
    expected = {"2025_j1": 380, "2025_cup": 56, "2025_emperor": 41,
                "2026_cup": 4, "2026_emperor": 19, "hyakunen": 200,
                "schedule": LIVE_SCHEDULE_COUNT, "frozen_predictions": FROZEN_TARGET_COUNT}
    result={}
    for name,path in paths.items():
        p=Path(path)
        if not p.exists(): raise FileNotFoundError(f"missing frozen input: {name}: {path}")
        result[name] = {"path": str(p), "rows": int(len(pd.read_csv(p)))}
        if name == "frozen_predictions":
            result[name]["sha256"] = hashlib.sha256(p.read_bytes()).hexdigest()
        if name in expected and result[name]["rows"] != expected[name]:
            raise ValueError(f"unexpected row count for {name}: {result[name]['rows']} != {expected[name]}")
    if "schedule" in result and "live_completed" in result:
        schedule, live = validate_live_2026_inputs(
            result["schedule"]["path"], result["live_completed"]["path"]
        )
        result["live_completed"].update(
            scheduled_rows=int(schedule.status.eq("scheduled").sum()),
            candidate_rows=int(schedule.status.eq("candidate").sum()),
        )
    if "live_completed" in result and "frozen_predictions" in result:
        target = load_frozen_lockbox_target(
            result["live_completed"]["path"], result["frozen_predictions"]["path"],
            expected_prediction_sha256=expected_prediction_sha256,
        )
        result["frozen_target"] = {
            "rows": len(target),
            "match_ids": tuple(target.match_id.astype(str)),
            "identity_source": "frozen_predictions",
        }
    return result

def _j1(path, master, years=range(2015,2026)):
    out=[]
    for y in years:
        d=pd.read_csv(Path(path)/f"{y}_matches_probe.csv")
        d["match_date"]=pd.to_datetime(d.match_date).dt.normalize(); d["season"]=y
        d["home_team_id"]=[master.resolve_team_id(x,source="jleague_data_site",on=t) for x,t in zip(d.home_team,d.match_date)]
        d["away_team_id"]=[master.resolve_team_id(x,source="jleague_data_site",on=t) for x,t in zip(d.away_team,d.match_date)]
        out.append(d[["match_id","season","match_date","home_team_id","away_team_id","result"]])
    return pd.concat(out,ignore_index=True).sort_values(["match_date","match_id"],kind="stable").reset_index(drop=True)

def _elo_features(stream, team_ids):
    elo=EloRatings(sorted(team_ids),k_factor=30,home_advantage=175); rows=[]
    for r in stream.sort_values(["match_date","match_id"],kind="stable").itertuples():
        s=elo.pre_match(r.home_team_id,r.away_team_id)
        rows.append((str(r.match_id),s.home_rating-s.away_rating))
        elo.update(r.home_team_id,r.away_team_id,int(r.result))
    return pd.DataFrame(rows,columns=["match_id","elo_diff"])

def _target_elo_features(history, targets, team_ids):
    """Read every target day's pre-match state before applying that day's results.

    Target kickoff times exist, but final-whistle times do not. A calendar-day
    bucket conservatively prevents an earlier-listed, still-running match from
    leaking its result into another match's pre-match Elo.
    """
    if not targets.empty and (pd.to_datetime(history.match_date) >= pd.to_datetime(targets.match_date).min()).any():
        raise ValueError("Elo history must precede the first target date.")
    elo=EloRatings(sorted(team_ids),k_factor=30,home_advantage=175)
    for r in history.sort_values(["match_date","match_id"],kind="stable").itertuples():
        elo.update(r.home_team_id,r.away_team_id,int(r.result))
    rows=[]
    ordered=targets.assign(_match_id=targets.match_id.astype(str)).sort_values(
        ["match_date","_match_id"],kind="stable"
    )
    for _,bucket in ordered.groupby("match_date",sort=False):
        for r in bucket.itertuples():
            before=elo.pre_match(r.home_team_id,r.away_team_id)
            rows.append((str(r.match_id),before.home_rating-before.away_rating))
        for r in bucket.itertuples():
            elo.update(r.home_team_id,r.away_team_id,int(r.result))
    return pd.DataFrame(rows,columns=["match_id","elo_diff"])

def _rest_features(j1, domestic, targets, *, include_completed_targets=False):
    events=[]
    for d in (j1,domestic):
        for r in d.itertuples():
            for side in ("home","away"):
                tid=getattr(r,side+"_team_id",None)
                if isinstance(tid,str) and tid: events.append((pd.Timestamp(r.match_date),str(getattr(r,"match_id",getattr(r,"source_match_id",""))),tid))
    events.sort(key=lambda x:(x[0],x[1])); result=[]
    ordered=targets.assign(_match_id=targets.match_id.astype(str)).sort_values(
        ["match_date","_match_id"],kind="stable"
    )
    for date,bucket in ordered.groupby("match_date",sort=False):
        for r in bucket.itertuples():
            vals=[]
            for side in ("home","away"):
                tid=getattr(r,side+"_team_id"); prior=[d for d,_,t in events if t==tid and d < date]; prev=max(prior) if prior else None
                vals += [0 if prev is None else (date-prev).days, int(prev is not None)]
            result.append((str(r.match_id),*vals))
        if include_completed_targets:
            for r in bucket.itertuples():
                for side in ("home","away"):
                    events.append((date,f"j1:{r.match_id}",getattr(r,side+"_team_id")))
    frame=pd.DataFrame(result,columns=["match_id","home_domestic_days_since_last_competitive_match","home_domestic_has_previous_competitive_match","away_domestic_days_since_last_competitive_match","away_domestic_has_previous_competitive_match"])
    return frame[["match_id","home_domestic_days_since_last_competitive_match","away_domestic_days_since_last_competitive_match","home_domestic_has_previous_competitive_match","away_domestic_has_previous_competitive_match"]]

def _fit(train, target, features):
    model=Pipeline([("scaler",StandardScaler()),("logistic",LogisticRegression(C=1,solver="lbfgs",max_iter=1000,random_state=0))])
    model.fit(train[list(features)],train.result); p=model.predict_proba(target[list(features)])
    if list(model.classes_)!=[0,1,2] or not np.allclose(p.sum(axis=1),1): raise ValueError("invalid class/probability contract")
    return p

def evaluate_lockbox(processed_dir="data/processed/jleague", target_path="data/processed/jleague/2026_27/completed_matches.csv", hyakunen_path="data/processed/jleague/2026_hyakunen/matches.csv"):
    paths=_default_input_paths(); paths["live_completed"]=target_path; paths["schedule"]=str(Path(target_path).with_name("schedule.csv")); paths["hyakunen"]=hyakunen_path
    inputs=preflight_inputs(paths); master=load_team_master(); j1=_j1(processed_dir,master); target=load_frozen_lockbox_target(inputs["live_completed"]["path"], inputs["frozen_predictions"]["path"]); target["match_date"]=pd.to_datetime(target.match_date).dt.normalize()
    target["home_team_id"]=[master.resolve_team_id(x,source="jleague_data_site",on=t) for x,t in zip(target.home_team,target.match_date)]
    target["away_team_id"]=[master.resolve_team_id(x,source="jleague_data_site",on=t) for x,t in zip(target.away_team,target.match_date)]
    if len(target)!=FROZEN_TARGET_COUNT or target.match_id.duplicated().any(): raise ValueError("2026 target invariant failed")
    hy=pd.read_csv(hyakunen_path); hy["match_date"]=pd.to_datetime(hy.match_date).dt.normalize(); hy["home_team_id"]=[master.resolve_team_id(x,source="jleague_data_site",on=t) for x,t in zip(hy.home_team,hy.match_date)]; hy["away_team_id"]=[master.resolve_team_id(x,source="jleague_data_site",on=t) for x,t in zip(hy.away_team,hy.match_date)]
    domestic=[]
    for pat in ["data/processed/jleague_cup/2015_2024_jleague_cup_matches.csv","data/processed/jleague_cup/2025_jleague_cup_matches.csv","data/processed/jleague_cup/2026_jleague_cup_matches.csv","data/processed/emperors_cup/2015_2024_emperors_cup_matches.csv","data/processed/emperors_cup/2025_emperors_cup_matches.csv","data/processed/emperors_cup/2026_emperors_cup_matches.csv"]:
        d=pd.read_csv(pat); d["match_date"]=pd.to_datetime(d.match_date).dt.normalize(); domestic.append(d)
    dom=pd.concat(domestic,ignore_index=True)
    for c in ("home_team_id","away_team_id"): dom[c]=dom[c].where(dom[c].notna(),pd.NA)
    # Only resolved J1-side events are needed for rest chronology.
    dom=dom.loc[dom.home_team_id.notna() | dom.away_team_id.notna()].copy()
    train_rest=_rest_features(j1,dom,j1)
    target_rest=_rest_features(j1,pd.concat([dom,hy],ignore_index=True),target,include_completed_targets=True)
    train_elo=_elo_features(j1, set(j1.home_team_id)|set(j1.away_team_id))
    history=pd.concat([j1,hy[["match_id","match_date","home_team_id","away_team_id","result"]]],ignore_index=True)
    all_elo=_target_elo_features(history,target,set(history.home_team_id)|set(history.away_team_id)|set(target.home_team_id)|set(target.away_team_id))
    j1["match_id"]=j1.match_id.astype(str); target["match_id"]=target.match_id.astype(str)
    train=j1.merge(train_elo,on="match_id").merge(train_rest,on="match_id"); targetf=target.merge(all_elo,on="match_id").merge(target_rest,on="match_id")
    if len(train)!=3588 or len(targetf)!=FROZEN_TARGET_COUNT:
        raise ValueError("Unexpected Logistic training or target row count.")
    p_a=_fit(train,targetf,FEATURE_A); p_b=_fit(train,targetf,FEATURE_B); y=target.result.to_numpy(); return targetf,p_a,p_b,y

def metrics(y,p):
    pred=p.argmax(1); one=np.eye(3)[y]
    return {"correct":int((pred==y).sum()),"accuracy":float(accuracy_score(y,pred)),"log_loss":float(log_loss(y,p,labels=[0,1,2])),"brier":float(np.mean(np.sum((p-one)**2,axis=1))),"confusion":confusion_matrix(y,pred,labels=[0,1,2]).tolist()}
