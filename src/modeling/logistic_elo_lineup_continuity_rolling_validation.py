"""One-shot Elo plus lagged Starting XI continuity evaluation.

Only J1 match history is used.  The lineup feature is pre-match: for match M
it compares the exact raw-name XI from M-1 with M-2.  It does not include AFC,
J2, Cup matches, 2025, or 2026; lineup values are post-match records and are
used only as lagged history.
"""
from dataclasses import dataclass
from pathlib import Path
import re

import numpy as np
import pandas as pd
from bs4 import BeautifulSoup, Comment
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, log_loss
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from src.collect.teams import load_team_master
from src.features.elo import EloRatings

VALIDATION_SEASONS = (2020, 2021, 2022, 2023, 2024)
EXPECTED_VALIDATION_COUNTS = {2020: 306, 2021: 380, 2022: 306, 2023: 306, 2024: 380}
CLASS_ORDER = (0, 1, 2)
CURRENT_FEATURES = ("elo_diff",)
LINEUP_FEATURES = ("elo_diff", "home_prev2_lineup_overlap", "away_prev2_lineup_overlap",
                   "home_lineup_overlap_missing", "away_lineup_overlap_missing")


@dataclass(frozen=True)
class Metrics:
    accuracy: float
    log_loss: float
    brier_score: float


@dataclass(frozen=True)
class LineupRollingResult:
    fold_metrics: dict
    pooled_metrics: dict
    pooled_predictions: pd.DataFrame
    fold_distributions: dict
    season_start_diagnostics: dict


def parse_starting_xi_html(html: str) -> tuple[frozenset[str], frozenset[str]]:
    """Extract the two A5 Starting XI tables without name normalization."""
    if not isinstance(html, str) or not html.strip():
        raise ValueError("HTML must be nonempty")
    soup = BeautifulSoup(html, "html.parser")
    result = {}
    for side, cls in (("home", "two-column-table-box-l"), ("away", "two-column-table-box-r")):
        candidates = []
        for box in soup.find_all("div", class_=lambda v: v and cls in v.split()):
            comments = " ".join(str(c) for c in box.find_all(string=lambda x: isinstance(x, Comment)))
            if "A5" not in comments or "Start" not in comments:
                continue
            rows = []
            for tr in box.find_all("tr"):
                name = tr.find("td", class_="name")
                position = tr.find("td", class_="position")
                number = tr.find("td", class_="number")
                if name and position and number:
                    value = name.get_text("", strip=False)
                    if value:
                        rows.append(value)
            if len(rows) == 11:
                candidates.append(frozenset(rows))
        if not candidates:
            raise ValueError(f"missing exactly-11 Starting XI for {side}")
        result[side] = candidates[0]
    if result["home"] == result["away"]:
        raise ValueError("home and away XI are identical")
    return result["home"], result["away"]


def previous_two_lineup_overlap(history: pd.DataFrame) -> pd.DataFrame:
    """Return pre-match overlap columns, preserving input rows and order."""
    required = {"match_id", "match_date", "home_team_id", "away_team_id", "home_xi", "away_xi"}
    if not isinstance(history, pd.DataFrame) or not required.issubset(history.columns):
        raise ValueError(f"missing columns: {sorted(required - set(getattr(history, 'columns', [])))}")
    out = history.copy(deep=True)
    out["match_date"] = pd.to_datetime(out["match_date"], errors="raise").dt.normalize()
    if out["match_id"].duplicated().any():
        raise ValueError("match_id must be unique")
    ordered = out.sort_values(["match_date", "match_id"], kind="mergesort")
    states = {}
    values = {}
    for row in ordered.itertuples(index=False):
        for side, team, xi in (("home", row.home_team_id, row.home_xi), ("away", row.away_team_id, row.away_xi)):
            prior = states.get(team, [])
            key = (row.match_id, side)
            if len(prior) < 2:
                values[key] = np.nan
            else:
                values[key] = len(prior[-1] & prior[-2])
            states.setdefault(team, []).append(frozenset(xi))
    out["home_prev2_lineup_overlap"] = [values[(r.match_id, "home")] for r in out.itertuples()]
    out["away_prev2_lineup_overlap"] = [values[(r.match_id, "away")] for r in out.itertuples()]
    return out


def _load_j1(processed_dir: str | Path, raw_dir: str | Path) -> pd.DataFrame:
    master = load_team_master()
    frames = []
    for season in range(2015, 2025):
        frame = pd.read_csv(Path(processed_dir) / f"{season}_matches_probe.csv", dtype={"match_id": str})
        frame["season"] = season
        frame["match_date"] = pd.to_datetime(frame["match_date"], errors="raise").dt.normalize()
        frame["home_team_id"] = [master.resolve_team_id(n, source="jleague_data_site", on=d.date()) for n, d in zip(frame.home_team, frame.match_date)]
        frame["away_team_id"] = [master.resolve_team_id(n, source="jleague_data_site", on=d.date()) for n, d in zip(frame.away_team, frame.match_date)]
        home_xi, away_xi = [], []
        for match_id in frame.match_id:
            path = Path(raw_dir) / f"{match_id}.html"
            if not path.exists():
                raise FileNotFoundError(f"missing lineup cache: {match_id}")
            h, a = parse_starting_xi_html(path.read_text(encoding="utf-8", errors="replace"))
            home_xi.append(h); away_xi.append(a)
        frame["home_xi"], frame["away_xi"] = home_xi, away_xi
        frames.append(frame[["match_id", "season", "match_date", "home_team_id", "away_team_id", "result", "home_xi", "away_xi"]])
    result = pd.concat(frames, ignore_index=True).sort_values(["match_date", "match_id"], kind="mergesort").reset_index(drop=True)
    return previous_two_lineup_overlap(result)


def _replay_elo(matches: pd.DataFrame) -> pd.Series:
    elo = EloRatings(sorted(set(matches.home_team_id) | set(matches.away_team_id)), k_factor=30.0, home_advantage=175.0)
    result = {}
    for row in matches.sort_values(["match_date", "match_id"], kind="mergesort").itertuples(index=False):
        snap = elo.pre_match(row.home_team_id, row.away_team_id)
        result[str(row.match_id)] = snap.home_rating - snap.away_rating
        elo.update(row.home_team_id, row.away_team_id, int(row.result))
    return pd.Series(result)


def _metrics(y, p) -> Metrics:
    y, p = np.asarray(y), np.asarray(p)
    if p.shape != (len(y), 3) or not np.allclose(p.sum(axis=1), 1):
        raise ValueError("invalid probability matrix")
    one_hot = (y[:, None] == np.asarray(CLASS_ORDER)).astype(float)
    return Metrics(float(accuracy_score(y, np.asarray(CLASS_ORDER)[p.argmax(axis=1)])),
                   float(log_loss(y, p, labels=list(CLASS_ORDER))),
                   float(np.mean(np.sum((p - one_hot) ** 2, axis=1))))


def _fit(train, validation, features):
    columns = list(features)
    train = train.copy(deep=True); validation = validation.copy(deep=True)
    if features == LINEUP_FEATURES:
        medians = train[["home_prev2_lineup_overlap", "away_prev2_lineup_overlap"]].median()
        for side in ("home", "away"):
            col = f"{side}_prev2_lineup_overlap"; missing = f"{side}_lineup_overlap_missing"
            train[missing] = train[col].isna().astype(int); validation[missing] = validation[col].isna().astype(int)
            train[col] = train[col].fillna(medians[col]); validation[col] = validation[col].fillna(medians[col])
    model = Pipeline([("scaler", StandardScaler()), ("logistic", LogisticRegression(C=1, solver="lbfgs", max_iter=1000, random_state=0))])
    model.fit(train[columns], train.result)
    if not np.array_equal(model.named_steps["logistic"].classes_, np.asarray(CLASS_ORDER)):
        raise ValueError("class order must be [0, 1, 2]")
    return model.predict_proba(validation[columns])


def run_logistic_elo_lineup_continuity_rolling_validation(*, processed_dir="data/processed/jleague", raw_dir="data/raw/jleague_match_stats") -> LineupRollingResult:
    base = _load_j1(processed_dir, raw_dir)
    base["elo_diff"] = base["match_id"].map(_replay_elo(base)).astype(float)
    fold_metrics, pooled, records, distributions, starts = {}, {"current": [], "lineup": []}, [], {}, {}
    targets = []
    for year in VALIDATION_SEASONS:
        train = base[base.season < year].copy(); val = base[base.season == year].copy()
        if len(val) != EXPECTED_VALIDATION_COUNTS[year]: raise ValueError(f"unexpected validation count {year}")
        y = val.result.to_numpy(); targets.append(y)
        p0, p1 = _fit(train, val, CURRENT_FEATURES), _fit(train, val, LINEUP_FEATURES)
        fold_metrics[year] = {"current": _metrics(y, p0), "lineup": _metrics(y, p1)}
        pooled["current"].append(p0); pooled["lineup"].append(p1)
        distributions[year] = {"home": val.home_prev2_lineup_overlap.describe(percentiles=[.1,.9]).to_dict(), "away": val.away_prev2_lineup_overlap.describe(percentiles=[.1,.9]).to_dict()}
        starts[year] = {"first3": val.groupby("home_team_id").head(3)[["home_prev2_lineup_overlap","away_prev2_lineup_overlap"]].notna().mean().to_dict(), "appearance4plus": val.groupby("home_team_id").head(10).groupby(level=0).tail(7).notna().mean().to_dict()}
        for i, row in enumerate(val.itertuples(index=False)):
            records.append((row.match_id, year, int(row.result), p0[i], p1[i], row.home_prev2_lineup_overlap, row.away_prev2_lineup_overlap))
    y = np.concatenate(targets); pooled_metrics = {k: _metrics(y, np.concatenate(v)) for k, v in pooled.items()}
    pred = pd.DataFrame(records, columns=["match_id","season","result","current_prob","lineup_prob","home_overlap","away_overlap"])
    if len(pred) != 1678: raise ValueError("pooled OOF must contain 1,678 matches")
    return LineupRollingResult(fold_metrics, pooled_metrics, pred, distributions, starts)
