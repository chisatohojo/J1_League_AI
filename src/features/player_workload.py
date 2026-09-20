"""Pre-match J1-only normalized workload from exact, team-season-local player names.

This is not total football workload or actual elapsed playing time. No target
lineup, target minutes, other team/season history, or same-date result is used.
"""

from collections import defaultdict
from datetime import date
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
MINUTES_PATH = ROOT / "data/processed/sfms02_player_minutes/2015_2024_j1_player_minutes.csv"
MATCH_DIR = ROOT / "data/processed/jleague"
STATS_DIR = ROOT / "data/processed/jleague_match_stats"
OUTPUT_PATH = ROOT / "data/processed/features/2015_2024_j1_player_workload_features.csv"
EXPECTED = {**{year: 306 for year in range(2015, 2021)}, 2021: 380,
            2022: 306, 2023: 306, 2024: 380}
WINDOWS = (7, 14, 30)
APPEARANCE_TYPES = frozenset({"starter_full", "starter_subbed_out", "starter_dismissed",
                              "sub_entered", "sub_entered_and_left", "sub_entered_dismissed",
                              "unused_substitute"})
MATCH_COLUMNS = ("match_id", "match_date", "season", "home_team_id", "away_team_id")
MINUTE_COLUMNS = ("match_id", "match_date", "season", "team_id", "player_name_raw",
                  "starter", "listed_substitute", "minutes_played_normalized", "appearance_type")


class WorkloadError(ValueError):
    """Input identity, chronology, or participation invariant failed."""


def _text(value, label):
    if not isinstance(value, str) or not value or value != value.strip() or "\ufffd" in value:
        raise WorkloadError(f"Invalid {label}: {value!r}")
    return value


def _flag(value, label):
    if value is True or value == "True":
        return True
    if value is False or value == "False":
        return False
    raise WorkloadError(f"Invalid {label}: {value!r}")


def _date(value):
    try:
        return date.fromisoformat(_text(value, "match_date"))
    except ValueError as exc:
        raise WorkloadError(f"Invalid match date: {value!r}") from exc


def build_player_workload_features(matches: pd.DataFrame, minutes: pd.DataFrame) -> pd.DataFrame:
    """Build one home/away feature row per ordinary J1 match, without mutating inputs.

    Each calendar date is a batch: features see only strictly earlier dates;
    player rows and previous squads become visible after all that date's
    features have been recorded. Missing previous J1 squad => null aggregates,
    zero counts/flags. An observed local key with no prior J1 appearance in a
    window contributes zero *local J1* normalized minutes, not zero true load.
    """
    if not isinstance(matches, pd.DataFrame) or not isinstance(minutes, pd.DataFrame):
        raise TypeError("matches and minutes must be DataFrames")
    if (matches.columns.has_duplicates or minutes.columns.has_duplicates
            or set(MATCH_COLUMNS) - set(matches.columns)
            or set(MINUTE_COLUMNS) - set(minutes.columns)):
        raise WorkloadError("Missing or duplicate input columns")

    match_rows = {}
    dates = defaultdict(list)
    team_dates = set()
    for row in matches.loc[:, MATCH_COLUMNS].to_dict("records"):
        mid = _text(row["match_id"], "match_id")
        day = _date(row["match_date"])
        season = int(row["season"])
        if season != day.year or not 2015 <= season <= 2024 or mid in match_rows:
            raise WorkloadError(f"Invalid season or duplicate match: {mid}")
        home = _text(row["home_team_id"], "home_team_id")
        away = _text(row["away_team_id"], "away_team_id")
        if home == away or (day, home) in team_dates or (day, away) in team_dates:
            raise WorkloadError(f"Repeated same-date team or self-match: {mid}")
        team_dates.update(((day, home), (day, away)))
        match_rows[mid] = (day, season, home, away)
        dates[day].append(mid)

    squads = defaultdict(list)
    seen = set()
    for row in minutes.loc[:, MINUTE_COLUMNS].to_dict("records"):
        mid = _text(row["match_id"], "match_id")
        if mid not in match_rows:
            raise WorkloadError(f"Orphan player row: {mid}")
        day, season, home, away = match_rows[mid]
        team = _text(row["team_id"], "team_id")
        name = _text(row["player_name_raw"], "player_name_raw")
        key = (mid, team, name)
        if (team not in (home, away) or _date(row["match_date"]) != day
                or int(row["season"]) != season or key in seen):
            raise WorkloadError(f"Misaligned or duplicate player row: {key}")
        seen.add(key)
        starter = _flag(row["starter"], "starter")
        listed_substitute = _flag(row["listed_substitute"], "listed_substitute")
        if starter == listed_substitute:
            raise WorkloadError(f"Invalid squad role: {key}")
        appearance = _text(row["appearance_type"], "appearance_type")
        if appearance not in APPEARANCE_TYPES or starter != appearance.startswith("starter_") or (
                appearance == "unused_substitute" and not listed_substitute):
            raise WorkloadError(f"Inconsistent participation type: {key}")
        try:
            raw_minute = row["minutes_played_normalized"]
            minute = int(raw_minute)
            if isinstance(raw_minute, float) and raw_minute != minute:
                raise ValueError
        except (TypeError, ValueError) as exc:
            raise WorkloadError(f"Invalid minutes: {key}") from exc
        if not 0 <= minute <= 90 or (appearance == "unused_substitute" and minute != 0):
            raise WorkloadError(f"Out-of-range minutes: {key}")
        squads[(mid, team)].append((name, starter, minute, appearance != "unused_substitute"))

    if len(squads) != 2 * len(match_rows):
        raise WorkloadError("Every match needs both team squads")
    for key, squad in squads.items():
        if len(squad) < 11 or sum(starter for _, starter, _, _ in squad) != 11:
            raise WorkloadError(f"Previous XI cannot be established: {key}")

    # Each key is (season, team_id, exact raw name); no carry-over is possible.
    history = defaultdict(list)
    previous = {}
    output = []

    def side_features(side, team, day, season):
        prefix = side + "_"
        ref = previous.get(team)
        found = ref is not None
        result = {prefix + "has_previous_j1_match": int(found),
                  prefix + "prev_starters_count": 11 if found else 0,
                  prefix + "prev_squad_size": len(ref[2]) if found else 0,
                  prefix + "prev_reference_from_prior_season": int(found and ref[1] != season)}
        for n in WINDOWS:
            for population in ("starters", "squad"):
                selected = ([(name, start) for name, start in ref[2] if start] if population == "starters"
                            else [(name, start) for name, start in ref[2]]) if found else []
                amounts = []
                with_history = 0
                for name, _ in selected:
                    events = history[(season, team, name)]
                    relevant = [(minute, played) for prior, minute, played in events
                                if 0 < (day - prior).days <= n]
                    amounts.append(sum(minute for minute, _ in relevant))
                    with_history += int(any(played for _, played in relevant))
                stem = prefix + f"prev_{population}_"
                result[stem + f"with_{n}d_history"] = with_history
                result[stem + f"sum_minutes_{n}d"] = sum(amounts) if found else None
                result[stem + f"mean_minutes_{n}d"] = sum(amounts) / len(amounts) if found else None
        return result

    for day in sorted(dates):
        for mid in sorted(dates[day]):
            _, season, home, away = match_rows[mid]
            features = {"match_id": mid, "match_date": day.isoformat(), "season": season}
            features.update(side_features("home", home, day, season))
            features.update(side_features("away", away, day, season))
            output.append(features)
        # The entire date is now complete. No same-day minutes or squad leak.
        for mid in sorted(dates[day]):
            _, season, home, away = match_rows[mid]
            for team in (home, away):
                squad = squads[(mid, team)]
                previous[team] = (day, season, tuple((name, starter) for name, starter, _, _ in squad))
                for name, _, minute, played in squad:
                    history[(season, team, name)].append((day, minute, played))
    return pd.DataFrame.from_records(output)


def load_inputs(*, match_dir=MATCH_DIR, stats_dir=STATS_DIR, minutes_path=MINUTES_PATH):
    """Read and strictly align the existing 2015–2024 J1 source files."""
    all_matches = []
    for season, expected in EXPECTED.items():
        probe = pd.read_csv(Path(match_dir) / f"{season}_matches_probe.csv", dtype=str)
        stats = pd.read_csv(Path(stats_dir) / f"{season}_match_stats.csv", dtype=str)
        if (len(probe) != expected or len(stats) != expected
                or probe.match_id.duplicated().any() or stats.match_id.duplicated().any()
                or set(probe.match_id) != set(stats.match_id)):
            raise WorkloadError(f"J1 probe/stats mismatch in {season}")
        joined = probe[["match_id", "match_date", "season"]].merge(
            stats[["match_id", "home_team_id", "away_team_id"]], on="match_id",
            validate="one_to_one", sort=False)
        all_matches.append(joined)
    matches = pd.concat(all_matches, ignore_index=True)
    minutes = pd.read_csv(minutes_path, dtype=str, keep_default_na=False)
    if len(matches) != 3208 or len(minutes) != 115468:
        raise WorkloadError("Full-history input counts differ from audited data")
    return matches, minutes


def collect_history(*, match_dir=MATCH_DIR, stats_dir=STATS_DIR,
                    minutes_path=MINUTES_PATH, output_path=OUTPUT_PATH):
    """Publish the validated complete CSV once; refuse to overwrite an output."""
    matches, minutes = load_inputs(match_dir=match_dir, stats_dir=stats_dir,
                                   minutes_path=minutes_path)
    result = build_player_workload_features(matches, minutes)
    if len(result) != 3208 or result.match_id.duplicated().any():
        raise WorkloadError("Output match count/identity mismatch")
    output = Path(output_path)
    if output.exists():
        raise WorkloadError(f"Output already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8", newline="") as handle:
        result.to_csv(handle, index=False)
    return result


if __name__ == "__main__":
    result = collect_history()
    print(f"Saved {len(result)} match rows to {OUTPUT_PATH}")
