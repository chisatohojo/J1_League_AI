"""Build frozen pre-match rolling xG features without model dependencies.

The v1 contract uses each team's last five eligible matches across 2025
ordinary J1, the 2026 100 Year Vision League, and completed 2026/27 ordinary
J1.  Calendar dates are batches, so same-date matches never become mutual
history.  Official-final xG with unresolved time scope remains a target row but
does not contribute to later history.
"""

from collections import defaultdict, deque
from datetime import date
from math import isfinite
from pathlib import Path

import pandas as pd

from src.collect.teams import TeamMaster, load_team_master


ROOT = Path(__file__).resolve().parents[2]
XG_DIR = ROOT / "data/processed/jleague_match_xg"
J1_DIR = ROOT / "data/processed/jleague"
OUTPUT_PATH = ROOT / "data/processed/features/2025_2026_27_j1_rolling_xg_features.csv"
WINDOW = 5
REGULATION_SCOPE = "REGULATION"
COMPETITION_ORDER = {
    "j1_2025": 0,
    "j1_hyakunen_2026": 1,
    "j1_2026_2027": 2,
}
SOURCE_SPECS = (
    ("j1_2025", "2025", 380, "2025_j1_match_xg.csv", "2025_matches_probe.csv"),
    ("j1_hyakunen_2026", "2026", 200, "2026_hyakunen_j1_match_xg.csv",
     "2026_hyakunen/matches.csv"),
    ("j1_2026_2027", "2026/27", 80, "2026_27_j1_match_xg.csv",
     "2026_27/completed_matches.csv"),
)
REQUIRED_SOURCE_COLUMNS = (
    "competition", "season", "match_id", "match_date", "home_team_id",
    "away_team_id", "home_xg", "away_xg", "xg_time_scope",
)
FEATURE_COLUMNS = (
    "home_last5_xg_for", "home_last5_xg_against",
    "away_last5_xg_for", "away_last5_xg_against",
)
DIAGNOSTIC_COLUMNS = (
    "home_xg_history_count", "away_xg_history_count",
    "home_xg_available", "away_xg_available", "xg_pair_available",
    "home_prior_xg_scope_exclusion_count",
    "away_prior_xg_scope_exclusion_count",
    "xg_history_excluded_source_match",
)
OUTPUT_COLUMNS = (
    "competition", "season", "match_id", "match_date", "home_team_id",
    "away_team_id", *FEATURE_COLUMNS, *DIAGNOSTIC_COLUMNS,
)


class RollingXGError(ValueError):
    """Input identity, chronology, scope, or feature invariant failed."""


def _text(value, label):
    if not isinstance(value, str) or not value or value != value.strip() or "\ufffd" in value:
        raise RollingXGError(f"Invalid {label}: {value!r}")
    return value


def _date(value):
    try:
        return date.fromisoformat(_text(value, "match_date"))
    except ValueError as exc:
        raise RollingXGError(f"Invalid match_date: {value!r}") from exc


def _xg(value, label):
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise RollingXGError(f"Invalid {label}: {value!r}") from exc
    if not isfinite(number) or number < 0:
        raise RollingXGError(f"Invalid {label}: {value!r}")
    return number


def _validate_sources(matches: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(matches, pd.DataFrame):
        raise TypeError("matches must be a pandas DataFrame")
    if matches.columns.has_duplicates or set(REQUIRED_SOURCE_COLUMNS) - set(matches.columns):
        raise RollingXGError("Missing or duplicate rolling xG source columns")
    if (set(FEATURE_COLUMNS) | set(DIAGNOSTIC_COLUMNS)) & set(matches.columns):
        raise RollingXGError("Rolling xG output columns already exist")

    rows = []
    seen = set()
    for source in matches.loc[:, list(REQUIRED_SOURCE_COLUMNS)].to_dict("records"):
        competition = _text(source["competition"], "competition")
        if competition not in COMPETITION_ORDER:
            raise RollingXGError(f"Unsupported competition: {competition!r}")
        match_id = _text(source["match_id"], "match_id")
        if match_id in seen:
            raise RollingXGError(f"Duplicate match_id: {match_id}")
        seen.add(match_id)
        day = _date(source["match_date"])
        home = _text(source["home_team_id"], "home_team_id")
        away = _text(source["away_team_id"], "away_team_id")
        if home == away:
            raise RollingXGError(f"Self-match: {match_id}")
        scope = _text(source["xg_time_scope"], "xg_time_scope")
        if scope not in {REGULATION_SCOPE, "OFFICIAL_FINAL_SCOPE_UNRESOLVED"}:
            raise RollingXGError(f"Unsupported xG time scope: {scope!r}")
        rows.append({
            "competition": competition,
            "season": _text(source["season"], "season"),
            "match_id": match_id,
            "match_date": day,
            "home_team_id": home,
            "away_team_id": away,
            "home_xg": _xg(source["home_xg"], "home_xg"),
            "away_xg": _xg(source["away_xg"], "away_xg"),
            "xg_time_scope": scope,
        })
    return pd.DataFrame(rows).sort_values(
        ["match_date", "competition", "match_id"],
        key=lambda values: values.map(COMPETITION_ORDER) if values.name == "competition" else values,
        kind="stable",
    ).reset_index(drop=True)


def build_rolling_xg_features(matches: pd.DataFrame) -> pd.DataFrame:
    """Return one frozen pre-match feature row per supplied source match.

    Inputs are copied and sorted deterministically.  Features for every match on
    a calendar date are generated before that date's eligible xG observations
    are appended.  The returned DataFrame stores per-side history match IDs in
    ``attrs['rolling_xg_history_audit']`` for diagnostics; those IDs are not
    production CSV columns.
    """
    ordered = _validate_sources(matches.copy(deep=True))
    history = defaultdict(lambda: deque(maxlen=WINDOW))
    excluded = defaultdict(int)
    output = []
    audit = []

    def side_values(side, team):
        prior = tuple(history[team])
        count = len(prior)
        available = count == WINDOW
        values = {
            f"{side}_last5_xg_for": (
                sum(item[1] for item in prior) / WINDOW if available else None
            ),
            f"{side}_last5_xg_against": (
                sum(item[2] for item in prior) / WINDOW if available else None
            ),
            f"{side}_xg_history_count": count,
            f"{side}_xg_available": available,
            f"{side}_prior_xg_scope_exclusion_count": excluded[team],
        }
        return values, tuple(item[0] for item in prior)

    for day, today in ordered.groupby("match_date", sort=True):
        # Snapshot all rows first; nothing from this date is visible yet.
        for row in today.itertuples(index=False):
            home_values, home_ids = side_values("home", row.home_team_id)
            away_values, away_ids = side_values("away", row.away_team_id)
            record = {
                "competition": row.competition,
                "season": row.season,
                "match_id": row.match_id,
                "match_date": day.isoformat(),
                "home_team_id": row.home_team_id,
                "away_team_id": row.away_team_id,
                **home_values,
                **away_values,
                "xg_pair_available": (
                    home_values["home_xg_available"] and away_values["away_xg_available"]
                ),
                "xg_history_excluded_source_match": row.xg_time_scope != REGULATION_SCOPE,
            }
            output.append(record)
            audit.append({
                "competition": row.competition,
                "match_id": row.match_id,
                "match_date": day.isoformat(),
                "home_history_match_ids": home_ids,
                "away_history_match_ids": away_ids,
            })

        # Update only after every feature row on this date has been recorded.
        for row in today.itertuples(index=False):
            if row.xg_time_scope != REGULATION_SCOPE:
                excluded[row.home_team_id] += 1
                excluded[row.away_team_id] += 1
                continue
            history[row.home_team_id].append((row.match_id, row.home_xg, row.away_xg))
            history[row.away_team_id].append((row.match_id, row.away_xg, row.home_xg))

    result = pd.DataFrame.from_records(output, columns=OUTPUT_COLUMNS)
    for column in FEATURE_COLUMNS:
        result[column] = pd.array(result[column], dtype="Float64")
    for column in (
        "home_xg_history_count", "away_xg_history_count",
        "home_prior_xg_scope_exclusion_count", "away_prior_xg_scope_exclusion_count",
    ):
        result[column] = pd.array(result[column], dtype="int64")
    for column in (
        "home_xg_available", "away_xg_available", "xg_pair_available",
        "xg_history_excluded_source_match",
    ):
        result[column] = pd.array(result[column], dtype="bool")
    result.attrs["rolling_xg_history_audit"] = pd.DataFrame.from_records(audit)
    return result


def rolling_xg_history_audit(featured: pd.DataFrame) -> pd.DataFrame:
    """Return a detached match-ID provenance table saved during construction."""
    if not isinstance(featured, pd.DataFrame):
        raise TypeError("featured must be a pandas DataFrame")
    audit = featured.attrs.get("rolling_xg_history_audit")
    if not isinstance(audit, pd.DataFrame):
        raise RollingXGError("No rolling xG history audit is attached")
    return audit.copy(deep=True)


def _read_csv(path: Path) -> pd.DataFrame:
    if not path.is_file():
        raise FileNotFoundError(path)
    return pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8-sig")


def _validate_exact_reference(
    source: pd.DataFrame, reference: pd.DataFrame, competition: str,
    master: TeamMaster,
) -> None:
    required = {"match_id", "match_date", "home_team", "away_team"}
    if reference.columns.has_duplicates or required - set(reference.columns):
        raise RollingXGError(f"Invalid reference schema for {competition}")
    if len(source) != len(reference) or reference.match_id.duplicated().any():
        raise RollingXGError(f"Reference count or identity mismatch for {competition}")
    refs = {}
    for row in reference.loc[:, list(required)].to_dict("records"):
        match_id = _text(row["match_id"], "reference match_id")
        day = _text(row["match_date"], "reference match_date")
        refs[match_id] = (
            day,
            master.resolve_team_id(row["home_team"], source="jleague_data_site", on=day),
            master.resolve_team_id(row["away_team"], source="jleague_data_site", on=day),
        )
    if set(source.match_id) != set(refs):
        raise RollingXGError(f"Reference match IDs differ for {competition}")
    for row in source.itertuples(index=False):
        if refs[row.match_id] != (row.match_date, row.home_team_id, row.away_team_id):
            raise RollingXGError(f"Exact target identity mismatch: {competition}/{row.match_id}")


def load_rolling_xg_inputs(
    *, xg_dir: str | Path = XG_DIR, j1_dir: str | Path = J1_DIR,
    team_master: TeamMaster | None = None,
) -> pd.DataFrame:
    """Load and exactly link the three audited production source partitions."""
    xg_root, j1_root = Path(xg_dir), Path(j1_dir)
    master = load_team_master() if team_master is None else team_master
    frames = []
    for competition, season, expected, xg_name, reference_name in SOURCE_SPECS:
        frame = _read_csv(xg_root / xg_name)
        if len(frame) != expected or frame.match_id.duplicated().any():
            raise RollingXGError(f"Unexpected source count or duplicate ID: {competition}")
        if "competition" not in frame:
            frame.insert(0, "competition", competition)
        if "xg_time_scope" not in frame:
            frame["xg_time_scope"] = REGULATION_SCOPE
        if not frame.competition.eq(competition).all() or not frame.season.eq(season).all():
            raise RollingXGError(f"Source competition/season mismatch: {competition}")
        reference = _read_csv(j1_root / reference_name)
        _validate_exact_reference(frame, reference, competition, master)
        frames.append(frame)
    combined = pd.concat(frames, ignore_index=True, sort=False)
    if len(combined) != 660 or combined.match_id.duplicated().any():
        raise RollingXGError("Combined production xG identity must contain 660 unique matches")
    unresolved = combined.loc[combined.xg_time_scope.ne(REGULATION_SCOPE), "match_id"].tolist()
    if unresolved != ["33017"]:
        raise RollingXGError(f"Unexpected unresolved xG time scope: {unresolved}")
    return combined


def collect_rolling_xg_features(
    *, xg_dir: str | Path = XG_DIR, j1_dir: str | Path = J1_DIR,
    output_path: str | Path = OUTPUT_PATH, team_master: TeamMaster | None = None,
) -> pd.DataFrame:
    """Validate current production inputs and publish the historical feature CSV once."""
    source = load_rolling_xg_inputs(xg_dir=xg_dir, j1_dir=j1_dir, team_master=team_master)
    result = build_rolling_xg_features(source)
    if len(result) != 660 or result.match_id.nunique() != 660:
        raise RollingXGError("Rolling xG output must contain 660 unique matches")
    counts = result[["home_xg_history_count", "away_xg_history_count"]]
    if not counts.ge(0).all().all() or not counts.le(WINDOW).all().all():
        raise RollingXGError("Rolling xG history count is outside 0-5")
    for side in ("home", "away"):
        available = result[f"{side}_xg_available"]
        values = result[[f"{side}_last5_xg_for", f"{side}_last5_xg_against"]]
        if (available != result[f"{side}_xg_history_count"].eq(WINDOW)).any():
            raise RollingXGError("Availability and history count disagree")
        if values.loc[available].isna().any().any() or values.loc[~available].notna().any().any():
            raise RollingXGError("Rolling xG missing semantics disagree with availability")
        if values.loc[available].lt(0).any().any():
            raise RollingXGError("Negative rolling xG mean")
    output = Path(output_path)
    if output.exists():
        raise RollingXGError(f"Output already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8", newline="") as handle:
        result.to_csv(handle, index=False)
    return result


if __name__ == "__main__":
    built = collect_rolling_xg_features()
    print(f"Saved {len(built)} match rows to {OUTPUT_PATH}")
