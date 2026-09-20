"""Pre-match gaps since J1, J.League Cup or Emperor's Cup matches.

AFC is excluded. For AFC participants domestic rest may be longer than the
gap since their actual last competitive match.
"""
import pandas as pd

from src.features.schedule_gap import add_schedule_gap_features

FEATURE_COLUMNS = (
    "home_domestic_days_since_last_competitive_match",
    "away_domestic_days_since_last_competitive_match",
    "home_domestic_has_previous_competitive_match",
    "away_domestic_has_previous_competitive_match",
)
AUDIT_COLUMNS = (
    "current_match_id", "current_match_date", "team_id", "side",
    "league_previous_match_id", "league_previous_date",
    "domestic_previous_key", "domestic_previous_date",
    "domestic_previous_competition", "league_only_days",
    "domestic_days", "difference", "category",
)


def _dates(frame, label):
    dates = pd.to_datetime(frame["match_date"], errors="raise")
    if dates.isna().any() or dates.dt.tz is not None:
        raise ValueError(f"{label}: invalid match_date")
    return dates.dt.normalize()


def _events(matches, league_cup_matches, emperors_cup_matches):
    if not isinstance(matches, pd.DataFrame) or matches.columns.has_duplicates:
        raise ValueError("J1 matches need unique DataFrame columns")
    required = {"match_id", "match_date", "home_team_id", "away_team_id"}
    if required - set(matches.columns):
        raise ValueError(f"Missing J1 columns: {sorted(required - set(matches.columns))}")
    ids = matches["match_id"].astype(str)
    if matches["match_id"].isna().any() or ids.duplicated().any() or ids.str.strip().eq("").any():
        raise ValueError("J1 match_id must be unique and nonmissing")
    dates = _dates(matches, "J1")
    if not dates.dt.year.between(2015, 2024).all():
        raise ValueError("Only J1 matches from 2015-2024 are supported")
    events = []
    j1_appearances = set()
    for match_id, date, home, away in zip(ids, dates, matches.home_team_id, matches.away_team_id):
        if any(not isinstance(team, str) or not team.strip() for team in (home, away)) or home == away:
            raise ValueError(f"Invalid J1 teams: match_id={match_id}")
        for side, team in (("home", home), ("away", away)):
            if (team, date) in j1_appearances:
                raise ValueError(f"Duplicate J1 team/date event: {team}, {date.date()}")
            j1_appearances.add((team, date))
            events.append((date, f"j1:{match_id}", team, "J1", match_id, side))

    for frame, competition, namespace in (
        (league_cup_matches, "J.League Cup", "jleague_cup"),
        (emperors_cup_matches, "Emperor's Cup", "emperors_cup"),
    ):
        required = {"match_date", "source_match_id", "home_team_id", "away_team_id",
                    "home_is_j1", "away_is_j1"}
        if not isinstance(frame, pd.DataFrame) or frame.columns.has_duplicates or required - set(frame.columns):
            raise ValueError(f"{competition}: missing or duplicate input columns")
        dates = _dates(frame, competition)
        if not dates.dt.year.between(2015, 2024).all():
            raise ValueError(f"{competition}: only 2015-2024 matches are supported")
        source_ids = frame.source_match_id.astype(str)
        if frame.source_match_id.isna().any() or source_ids.duplicated().any() or source_ids.str.strip().eq("").any():
            raise ValueError(f"{competition}: invalid source_match_id")
        for row, date in zip(frame.itertuples(index=False), dates):
            key = f"{namespace}:{row.source_match_id}"
            for side in ("home", "away"):
                flag = getattr(row, f"{side}_is_j1")
                if pd.isna(flag) or type(flag) is not bool:
                    raise ValueError(f"{competition}: invalid J1 flag: {key}, {side}")
                if flag:
                    team = getattr(row, f"{side}_team_id")
                    if not isinstance(team, str) or not team.strip():
                        raise ValueError(f"{competition}: missing J1 team ID: {key}, {side}")
                    events.append((date, key, team, competition, str(row.source_match_id), side))
    return sorted(events, key=lambda event: (event[0], event[1]))


def _audit(matches, league_cup_matches, emperors_cup_matches):
    events = _events(matches, league_cup_matches, emperors_cup_matches)
    last_league, last_domestic = {}, {}
    records = {}
    position = 0
    while position < len(events):
        date = events[position][0]
        end = position
        while end < len(events) and events[end][0] == date:
            end += 1
        today = events[position:end]
        for event in today:
            _, key, team, competition, match_id, side = event
            if competition != "J1":
                continue
            previous_league = last_league.get(team)
            previous_domestic = last_domestic.get(team)
            league_days = (date - previous_league[0]).days if previous_league else 0
            domestic_days = (date - previous_domestic[0]).days if previous_domestic else 0
            if previous_domestic is None:
                category = "no_previous_domestic"
            elif previous_league is None:
                category = "no_previous_league"
            elif domestic_days == league_days:
                category = "equal"
            elif domestic_days < league_days:
                category = "shorter"
            else:
                category = "domestic_longer"
            records[(match_id, side)] = {
                "current_match_id": match_id, "current_match_date": date,
                "team_id": team, "side": side,
                "league_previous_match_id": previous_league[4] if previous_league else None,
                "league_previous_date": previous_league[0] if previous_league else pd.NaT,
                "domestic_previous_key": previous_domestic[1] if previous_domestic else None,
                "domestic_previous_date": previous_domestic[0] if previous_domestic else pd.NaT,
                "domestic_previous_competition": previous_domestic[3] if previous_domestic else None,
                "league_only_days": league_days, "domestic_days": domestic_days,
                "difference": league_days - domestic_days if previous_league and previous_domestic else None,
                "category": category,
            }
        # Only after every appearance on this date has been recorded.
        for event in today:
            last_domestic[event[2]] = event
            if event[3] == "J1":
                last_league[event[2]] = event
        position = end
    audit = pd.DataFrame(
        [records[(str(row.match_id), side)] for row in matches.itertuples(index=False)
         for side in ("home", "away")], columns=AUDIT_COLUMNS
    )
    if len(audit) != 2 * len(matches):
        raise ValueError("Incomplete J1 appearance audit")
    both = audit.league_previous_match_id.notna() & audit.domestic_previous_key.notna()
    if (audit.loc[both, "domestic_days"] > audit.loc[both, "league_only_days"]).any():
        raise ValueError("Domestic gap exceeds league gap")
    j1 = audit.domestic_previous_competition.eq("J1")
    if (audit.loc[j1 & both, "difference"] != 0).any():
        raise ValueError("Previous J1 has inconsistent gaps")
    if (audit.loc[audit.category.eq("shorter"), "domestic_previous_competition"] == "J1").any():
        raise ValueError("J1 cannot shorten domestic rest")
    return audit


def audit_domestic_competitive_rest(matches, league_cup_matches, emperors_cup_matches, *,
                                    existing_league_features=None):
    """Return per-appearance provenance and verify J1 gaps using schedule_gap.

    If supplied, existing gap columns are strictly aligned by match_id before
    comparison. No input is modified and no CSV is written.
    """
    audit = _audit(matches, league_cup_matches, emperors_cup_matches)
    ordered = matches.assign(_audit_date=pd.to_datetime(matches.match_date)).sort_values(
        ["_audit_date", "match_id"], kind="stable"
    )
    recomputed = add_schedule_gap_features(
        ordered[["match_date", "home_team_id", "away_team_id"]].reset_index(drop=True)
    )
    reference = ordered[["match_id"]].reset_index(drop=True).copy()
    for side in ("home", "away"):
        reference[f"{side}_days_since_last_match"] = recomputed[f"{side}_days_since_last_match"]
    reference["match_id"] = reference.match_id.astype(str)
    if existing_league_features is not None:
        required = {"match_id", "home_days_since_last_match", "away_days_since_last_match"}
        existing = existing_league_features
        if not isinstance(existing, pd.DataFrame) or existing.columns.has_duplicates or required - set(existing.columns):
            raise ValueError("Existing league features require unique match_id and both gap columns")
        ids = existing.match_id.astype(str)
        if existing.match_id.isna().any() or ids.duplicated().any() or set(ids) != set(reference.match_id):
            raise ValueError("Existing league features do not align strictly by match_id")
        aligned = reference.merge(existing[list(required)].assign(match_id=ids), on="match_id",
                                  validate="one_to_one", suffixes=("_recomputed", "_existing"))
        for side in ("home", "away"):
            if not (aligned[f"{side}_days_since_last_match_recomputed"].to_numpy()
                    == aligned[f"{side}_days_since_last_match_existing"].to_numpy()).all():
                raise ValueError(f"Existing {side} J1 gap differs from schedule_gap recomputation")
    lookup = {(str(r.match_id), side): getattr(r, f"{side}_days_since_last_match")
              for r in reference.itertuples(index=False) for side in ("home", "away")}
    if any(row.league_only_days != lookup[(str(row.current_match_id), row.side)]
           for row in audit.itertuples(index=False)):
        raise ValueError("Independent J1 history differs from schedule_gap by match_id")
    return audit


def add_domestic_competitive_rest_features(matches, league_cup_matches, emperors_cup_matches):
    """Add four pre-match domestic features, excluding AFC and current-day events."""
    if not isinstance(matches, pd.DataFrame):
        raise TypeError("matches must be a pandas DataFrame")
    if any(column in matches.columns for column in FEATURE_COLUMNS):
        raise ValueError("Domestic rest columns already exist")
    audit = audit_domestic_competitive_rest(matches, league_cup_matches, emperors_cup_matches)
    output = matches.copy(deep=True)
    for side in ("home", "away"):
        subset = audit.loc[audit.side.eq(side)]
        output[f"{side}_domestic_days_since_last_competitive_match"] = pd.array(
            subset.domestic_days.to_list(), dtype="int64"
        )
        output[f"{side}_domestic_has_previous_competitive_match"] = pd.array(
            subset.domestic_previous_key.notna().astype(int).to_list(), dtype="int64"
        )
    output.attrs["domestic_rest_diagnostics"] = {
        "appearances": audit,
        "category_counts": audit.category.value_counts().to_dict(),
        "league_only_equals_domestic": int(audit.category.eq("equal").sum()),
        "domestic_shorter": int(audit.category.eq("shorter").sum()),
    }
    return output


def diagnose_domestic_competitive_rest(featured):
    """Return the saved, exclusive appearance audit from feature generation."""
    if not isinstance(featured, pd.DataFrame) or "domestic_rest_diagnostics" not in featured.attrs:
        raise ValueError("Generate domestic rest features before requesting diagnostics")
    return featured.attrs["domestic_rest_diagnostics"]
