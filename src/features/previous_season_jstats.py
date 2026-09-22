"""Build ordinary-J1 previous-season J Stats profile rows.

This is a feature materialization layer only. It does not fit or evaluate a
model. The explicit target-to-profile mapping below is the only season
linkage rule; arithmetic season subtraction is intentionally not used.
"""

from __future__ import annotations

import csv
from pathlib import Path

from src.collect.teams import TeamMaster, TeamMasterError, load_team_master

ROOT = Path(__file__).resolve().parents[2]
PROFILE_PATH = ROOT / "data/processed/jstats_previous_season_profiles/2018_2025_j1_team_profiles.csv"
MATCH_ROOT = ROOT / "data/processed/jleague"
SCHEDULE_2026 = MATCH_ROOT / "2026_27/schedule.csv"
OUTPUT_PATH = ROOT / "data/processed/features/previous_season_jstats_features.csv"

TARGET_PROFILE_MAPPING = {
    2020: 2019,
    2021: 2020,
    2022: 2021,
    2023: 2022,
    2024: 2023,
    2025: 2024,
    "2026/27": 2025,
}
STAT_NAMES = (
    "expected_goals", "shoot_on_target", "expected_goals_against",
    "suffer_shoot_on_target", "ball_rate", "pass_rate",
)
DERIVED = {
    "expected_goals": "expected_goals_per_match",
    "shoot_on_target": "shoot_on_target_per_match",
    "expected_goals_against": "expected_goals_against_per_match",
    "suffer_shoot_on_target": "suffer_shoot_on_target_per_match",
}
FEATURE_COLUMNS = (
    "match_id", "season", "match_date", "home_team_id", "away_team_id",
    "home_profile_season", "away_profile_season",
    "home_has_previous_j1_profile", "away_has_previous_j1_profile",
    "home_previous_expected_goals_per_match", "away_previous_expected_goals_per_match",
    "home_previous_shoot_on_target_per_match", "away_previous_shoot_on_target_per_match",
    "home_previous_expected_goals_against_per_match", "away_previous_expected_goals_against_per_match",
    "home_previous_suffer_shoot_on_target_per_match", "away_previous_suffer_shoot_on_target_per_match",
    "home_previous_ball_rate", "away_previous_ball_rate",
    "home_previous_pass_rate", "away_previous_pass_rate",
    "home_profile_retrieval_id", "away_profile_retrieval_id",
)


def _resolve_slug(master: TeamMaster, slug: str) -> str:
    matches = [a.team_id for a in master.aliases
               if a.source == "jleague_data_site" and a.source_club_id == slug]
    if len(set(matches)) != 1:
        raise ValueError(f"Unresolved or ambiguous schedule club slug: {slug!r}")
    return matches[0]


def _load_profiles(path: Path) -> dict[tuple[int, str], dict]:
    with Path(path).open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    required = {"profile_season", "team_id", "stat_name", "raw_value", "derived_value",
                "retrieval_id", "games_played_basis"}
    if not rows or not required <= set(rows[0]):
        raise ValueError("Profile artifact schema is incomplete.")
    profiles = {}
    for row in rows:
        season = int(row["profile_season"])
        if row["stat_name"] not in STAT_NAMES:
            raise ValueError(f"Unexpected profile stat: {row['stat_name']}")
        key = (season, row["team_id"])
        if key in profiles and profiles[key]["stat_name"] == row["stat_name"]:
            raise ValueError(f"Duplicate profile row: {key}/{row['stat_name']}")
        try:
            value = float(row["raw_value"])
            if value < 0 or value != value:
                raise ValueError
            if row["stat_name"] in DERIVED:
                derived = float(row["derived_value"])
                if derived < 0 or derived != derived:
                    raise ValueError
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Non-finite profile value: {key}/{row['stat_name']}") from exc
        profiles[(season, row["team_id"], row["stat_name"])] = row
    return profiles


def _target_rows(target_season, *, match_root: Path, schedule_path: Path, master: TeamMaster):
    if target_season == "2026/27":
        path = Path(schedule_path)
        with path.open(encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
        for row in rows:
            row["match_id"] = row["match_id"] or row.get("fixture_key", "")
            row["season"] = "2026/27"
            row["home_team_id"] = _resolve_slug(master, row.get("home_club", ""))
            row["away_team_id"] = _resolve_slug(master, row.get("away_club", ""))
        return rows
    with (Path(match_root) / f"{target_season}_matches_probe.csv").open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    for row in rows:
        try:
            row["home_team_id"] = master.resolve_team_id(row["home_team"], source="jleague_data_site",
                                                          on=row["match_date"])
            row["away_team_id"] = master.resolve_team_id(row["away_team"], source="jleague_data_site",
                                                          on=row["match_date"])
        except TeamMasterError as exc:
            raise ValueError(f"Unresolved target team: {target_season}/{row.get('match_id')}") from exc
    return rows


def build_previous_season_jstats_features(*, profile_path: Path = PROFILE_PATH,
                                           match_root: Path = MATCH_ROOT,
                                           schedule_path: Path = SCHEDULE_2026,
                                           output_path: Path = OUTPUT_PATH,
                                           master: TeamMaster | None = None) -> dict:
    """Create one row per ordinary-J1 target fixture using only mapped profiles."""
    master = master or load_team_master()
    profiles = _load_profiles(profile_path)
    output = []
    for target, profile_season in TARGET_PROFILE_MAPPING.items():
        rows = _target_rows(target, match_root=match_root, schedule_path=schedule_path, master=master)
        seen = set()
        for row in rows:
            match_id = row.get("match_id", "")
            if not match_id or match_id in seen:
                raise ValueError(f"Missing or duplicate target match ID: {target}/{match_id}")
            seen.add(match_id)
            values = {"match_id": match_id, "season": target,
                      "match_date": row.get("match_date", ""),
                      "home_team_id": row["home_team_id"], "away_team_id": row["away_team_id"],
                      "home_profile_season": profile_season, "away_profile_season": profile_season,
                      "home_has_previous_j1_profile": False, "away_has_previous_j1_profile": False,
                      "home_profile_retrieval_id": "", "away_profile_retrieval_id": ""}
            for side, team_id in (("home", row["home_team_id"]), ("away", row["away_team_id"])):
                team_profiles = {stat: profiles.get((profile_season, team_id, stat)) for stat in STAT_NAMES}
                present = [value for value in team_profiles.values() if value is not None]
                if present and len(present) != len(STAT_NAMES):
                    raise ValueError(f"Partial previous profile: {target}/{team_id}/{profile_season}")
                available = len(present) == len(STAT_NAMES)
                values[f"{side}_has_previous_j1_profile"] = available
                if available:
                    retrievals = {value["retrieval_id"] for value in present}
                    if len(retrievals) != 1:
                        raise ValueError(f"Mixed profile retrieval IDs: {target}/{team_id}")
                    values[f"{side}_profile_retrieval_id"] = next(iter(retrievals))
                for stat, profile in team_profiles.items():
                    column = DERIVED.get(stat, stat)
                    values[f"{side}_previous_{column}"] = (profile["derived_value"] if stat in DERIVED else profile["raw_value"]) if profile else ""
            output.append(values)
    if len({row["match_id"] for row in output}) != len(output):
        raise ValueError("Target match IDs collide across seasons.")
    output.sort(key=lambda row: (str(row["season"]), row["match_date"], row["match_id"]))
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with Path(output_path).open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FEATURE_COLUMNS); writer.writeheader(); writer.writerows(output)
    return {"output_path": Path(output_path), "row_count": len(output),
            "rows_by_season": {str(season): sum(row["season"] == season for row in output)
                                for season in TARGET_PROFILE_MAPPING}}
