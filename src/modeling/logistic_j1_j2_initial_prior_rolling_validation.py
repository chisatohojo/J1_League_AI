"""One-shot comparison of an initial J2 rating prior.

Only J1 rows are Logistic targets. J1 and J2 league rows update one Elo
stream. The prior is fixed at 1400 for a club whose first official league
appearance is J2, and 1500 for a first J1 appearance. J3, Cups, AFC, 2025 and
2026 are intentionally excluded.
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

VALIDATION_SEASONS = (2020, 2021, 2022, 2023, 2024)
EXPECTED_VALIDATION_COUNTS = {2020: 306, 2021: 380, 2022: 306, 2023: 306, 2024: 380}
K_FACTOR = 30.0
HOME_ADVANTAGE = 175.0
J2_INITIAL_RATING = 1400.0
VARIANTS = ("current", "equal_j1_j2", "j2_initial_1400")


@dataclass(frozen=True)
class InitialPriorResult:
    fold_metrics: dict
    pooled_metrics: dict
    fold_counts: dict
    promotion_metrics: dict
    appearance_metrics: dict
    transitions: pd.DataFrame


def _metrics(y, p):
    y = np.asarray(y, dtype=int); p = np.asarray(p, dtype=float)
    if p.shape != (len(y), 3) or not np.allclose(p.sum(axis=1), 1.0):
        raise ValueError("invalid class probabilities")
    one_hot = (y[:, None] == np.asarray(CLASS_ORDER)).astype(float)
    return FormLogisticMetrics(float(accuracy_score(y, np.asarray(CLASS_ORDER)[p.argmax(axis=1)])),
                               float(log_loss(y, p, labels=list(CLASS_ORDER))),
                               float(np.mean(np.sum((p - one_hot) ** 2, axis=1))))


def _load_j1(processed_dir, master):
    frames = []
    for year in range(2015, 2025):
        f = pd.read_csv(Path(processed_dir) / f"{year}_matches_probe.csv")
        f["match_date"] = pd.to_datetime(f.match_date, errors="raise").dt.normalize()
        for side in ("home", "away"):
            f[f"{side}_team_id"] = [master.resolve_team_id(n, source="jleague_data_site", on=d.date()) for n, d in zip(f[f"{side}_team"], f.match_date)]
        f["event_key"] = "j1:" + f.match_id.astype(str)
        frames.append(f[["match_id", "event_key", "season", "match_date", "home_team_id", "away_team_id", "result"]])
    return pd.concat(frames, ignore_index=True)


def _load_j2(path):
    f = pd.read_csv(path, dtype={"match_id": str, "home_team_id": str, "away_team_id": str})
    f["match_date"] = pd.to_datetime(f.match_date, errors="raise").dt.normalize()
    if not f.season.isin(range(2015, 2025)).all(): raise ValueError("forbidden J2 season")
    f["event_key"] = "j2:" + f.match_id.astype(str)
    return f[["match_id", "event_key", "season", "match_date", "home_team_id", "away_team_id", "result"]]


def _stream(j1, j2):
    s = pd.concat([j1, j2], ignore_index=True).sort_values(["match_date", "event_key"], kind="stable").reset_index(drop=True)
    if s.event_key.duplicated().any(): raise ValueError("duplicate league event key")
    a = pd.concat([s[["match_date", "home_team_id"]].rename(columns={"home_team_id":"team_id"}), s[["match_date", "away_team_id"]].rename(columns={"away_team_id":"team_id"})])
    if a.duplicated(["match_date", "team_id"], keep=False).any(): raise ValueError("same team appears twice on one date")
    return s


def _replay(stream, end_season, *, j2_prior=False):
    s = stream[stream.season <= end_season]
    elo = EloRatings(sorted(set(s.home_team_id) | set(s.away_team_id)), k_factor=K_FACTOR, home_advantage=HOME_ADVANTAGE)
    seen = set(); rows = []; initial = {}
    for r in s.itertuples(index=False):
        if r.home_team_id not in seen:
            initial[r.home_team_id] = J2_INITIAL_RATING if j2_prior and r.event_key.startswith("j2:") else 1500.0
            elo._ratings[r.home_team_id] = initial[r.home_team_id]
        if r.away_team_id not in seen:
            initial[r.away_team_id] = J2_INITIAL_RATING if j2_prior and r.event_key.startswith("j2:") else 1500.0
            elo._ratings[r.away_team_id] = initial[r.away_team_id]
        before = elo.pre_match(r.home_team_id, r.away_team_id)
        rows.append((r.event_key, before.home_rating, before.away_rating))
        elo.update(r.home_team_id, r.away_team_id, r.result)
        seen.update((r.home_team_id, r.away_team_id))
    return pd.DataFrame(rows, columns=["event_key", "home_elo", "away_elo"]), initial


def _features(j1, stream, end_season, *, j2_prior=False, j1_only=False):
    source = j1 if j1_only else stream
    replay, initial = _replay(source, end_season, j2_prior=j2_prior)
    lookup = replay.set_index("event_key")
    out = j1[j1.season <= end_season].copy(deep=True)
    out["elo_diff"] = [lookup.loc[k, "home_elo"] - lookup.loc[k, "away_elo"] for k in out.event_key]
    return out, initial


def _fit(train, valid):
    model = Pipeline([("scaler", StandardScaler()), ("logistic", LogisticRegression(C=1, solver="lbfgs", max_iter=1000, random_state=0))])
    model.fit(train[["elo_diff"]], train.result)
    if not np.array_equal(model.classes_, CLASS_ORDER): raise ValueError("class order must be [0, 1, 2]")
    return model.predict_proba(valid[["elo_diff"]])


def _diagnostics(pred, j1):
    memberships = {y: set(j1.loc[j1.season.eq(y), "home_team_id"]) | set(j1.loc[j1.season.eq(y), "away_team_id"]) for y in range(2015, 2025)}
    first_seen = {}
    for r in j1.sort_values(["match_date", "event_key"]).itertuples(index=False):
        first_seen.setdefault(r.home_team_id, r.season); first_seen.setdefault(r.away_team_id, r.season)
    p = pred.copy(); p["category"] = "none"; p["appearance_no"] = 0
    for y in VALIDATION_SEASONS:
        promoted = memberships[y] - memberships[y-1]; counters = {t: 0 for t in promoted}
        for i, r in p[p.season.eq(y)].iterrows():
            involved = [t for t in (r.home_team_id, r.away_team_id) if t in promoted]
            if involved:
                for t in involved: counters[t] += 1
                p.at[i, "category"] = "first-time" if all(first_seen.get(t, y) == y for t in involved) else "returning"
                p.at[i, "appearance_no"] = min(counters[t] for t in involved)
    promoted_metrics = {}
    for cat in ("returning", "first-time", "none"):
        q = p[p.category.eq(cat)]
        promoted_metrics[cat] = {v: _metrics(q.result, np.vstack(q[f"{v}_prob"])) for v in VARIANTS} if len(q) else {}
    appearance_metrics = {}
    for label, mask in (("1-3", p.appearance_no.between(1,3)), ("4-10", p.appearance_no.between(4,10)), ("11+", p.appearance_no.ge(11))):
        q = p[mask]; appearance_metrics[label] = {v: _metrics(q.result, np.vstack(q[f"{v}_prob"])) for v in VARIANTS} if len(q) else {}
    return promoted_metrics, appearance_metrics


def run_logistic_j1_j2_initial_prior_rolling_validation(*, processed_dir="data/processed/jleague", j2_path="data/processed/jleague_j2/2015_2024_j2_matches.csv"):
    master = load_team_master(); j1 = _load_j1(processed_dir, master); j2 = _load_j2(j2_path); stream = _stream(j1, j2)
    folds = {}; counts = {}; pooled = {v: [] for v in VARIANTS}; targets=[]; pred_rows=[]; transitions=[]
    for y in VALIDATION_SEASONS:
        current, _ = _features(j1, stream, y, j1_only=True)
        equal, equal_initial = _features(j1, stream, y)
        prior, prior_initial = _features(j1, stream, y, j2_prior=True)
        sets = {"current": current, "equal_j1_j2": equal, "j2_initial_1400": prior}; val=current[current.season.eq(y)]; target=val.result.to_numpy(copy=True)
        if len(val) != EXPECTED_VALIDATION_COUNTS[y]: raise ValueError(f"unexpected validation count {y}")
        counts[y]=(int((current.season<y).sum()), len(val)); ps={}
        for v, frame in sets.items(): ps[v]=_fit(frame[frame.season<y], frame[frame.season.eq(y)]); pooled[v].append(ps[v])
        folds[y]={v:_metrics(target, ps[v]) for v in VARIANTS}; targets.append(target)
        for i,r in enumerate(val.itertuples(index=False)): pred_rows.append((str(r.match_id),y,int(r.result),r.home_team_id,r.away_team_id,*[ps[v][i] for v in VARIANTS]))
        transitions.append((y, equal_initial, prior_initial))
    y=np.concatenate(targets); pooled_metrics={v:_metrics(y,np.vstack(pooled[v])) for v in VARIANTS}
    cols=["match_id","season","result","home_team_id","away_team_id"]+[f"{v}_prob" for v in VARIANTS]
    pred=pd.DataFrame(pred_rows,columns=cols); promo,appearance=_diagnostics(pred,j1)
    transition_rows=[]
    for y0, eq, prior in transitions:
        for team, rating in sorted(prior.items()):
            transition_rows.append({"season":y0,"team_id":team,"j2_prior_initial":rating,"equal_initial":eq.get(team,1500.0)})
    return InitialPriorResult(folds, pooled_metrics, counts, promo, appearance, pd.DataFrame(transition_rows))
