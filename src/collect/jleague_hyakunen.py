"""Normalize the special 2026 competition without changing the ordinary J1 contract.

Match scores/results describe 90 minutes. Extra-time goals are increments, and
playoff shootouts decide a two-leg tie rather than the second match in isolation.
"""

from collections import Counter
from datetime import time
from itertools import permutations
from numbers import Integral
import re
import unicodedata

import pandas as pd

from src.collect.jleague_hyakunen_source import COMPETITION_KEY, _COMPETITIONS

INTEGER_COLUMNS = (
    "season", "source_year_id", "source_frame_id", "round", "leg",
    "displayed_home_score", "displayed_away_score", "home_pk_score",
    "away_pk_score", "home_score", "away_score", "result",
    "home_extra_time_score", "away_extra_time_score", "home_points", "away_points",
)
BOOLEAN_COLUMNS = ("extra_time_played", "pk_played")
TEXT_COLUMNS = (
    "match_id", "competition_key", "source_season_label", "competition", "stage",
    "group", "round_label", "kickoff_time", "home_team", "away_team", "stadium",
    "source_url", "raw_score_text", "placement_range", "broadcast_raw",
    "match_date_label", "home_group", "away_group", "pk_scope", "pk_winner_team",
    "match_winner_team", "match_decision", "playoff_tie_id", "detail_source_url",
    "score_90_source", "home_team_detail", "away_team_detail",
    "home_team_source_url", "away_team_source_url",
)
MATCH_DTYPES = {
    **dict.fromkeys(TEXT_COLUMNS, "string"),
    **dict.fromkeys(INTEGER_COLUMNS, "Int64"),
    **dict.fromkeys(BOOLEAN_COLUMNS, "bool"),
    "match_date": "datetime64[ns]",
}


class HyakunenValidationError(ValueError):
    """The special competition's source or normalized data is inconsistent."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise HyakunenValidationError(message)


def _null(value) -> bool:
    return value is None or bool(pd.isna(value))


def _integer(value, name: str, *, nullable: bool = False) -> int | None:
    if _null(value):
        _require(nullable, f"Missing {name}.")
        return None
    _require(isinstance(value, Integral) and not isinstance(value, bool),
             f"{name} must be an integer.")
    _require(value >= 0, f"{name} must be nonnegative.")
    return int(value)


def _text(value, name: str) -> str:
    _require(isinstance(value, str) and bool(value.strip()), f"Missing {name}.")
    return value


def _date(value) -> pd.Timestamp:
    if isinstance(value, str):
        _require(re.fullmatch(r"\d{4}-\d{2}-\d{2}", value) is not None,
                 "match_date must be YYYY-MM-DD.")
    try:
        stamp = pd.Timestamp(value)
        _require(not pd.isna(stamp) and stamp.tzinfo is None
                 and stamp == stamp.normalize() and stamp.year == 2026,
                 "match_date must be a midnight calendar date in 2026.")
        return stamp.as_unit("ns")
    except (TypeError, ValueError, OverflowError) as exc:
        raise HyakunenValidationError("Invalid match_date.") from exc


def _result(home: int, away: int) -> int:
    return 2 if home > away else 0 if home < away else 1


def _score_winner(home: int, away: int, home_team: str, away_team: str):
    return home_team if home > away else away_team if away > home else None


def _pk(row: dict) -> tuple[int | None, int | None]:
    home = _integer(row.get("home_pk_score"), "home_pk_score", nullable=True)
    away = _integer(row.get("away_pk_score"), "away_pk_score", nullable=True)
    _require((home is None) == (away is None), "Both PK scores must be present or null.")
    _require(home is None or home != away, "PK scores cannot be tied.")
    return home, away


def _group_membership(records: list[dict]) -> dict[str, str]:
    membership = {}
    for row in records:
        if row.get("stage") != "regional":
            continue
        group = row.get("group")
        _require(group in ("EAST", "WEST"), "Regional group must be EAST or WEST.")
        for key in ("home_team", "away_team"):
            club = _text(row.get(key), key)
            _require(club not in membership or membership[club] == group,
                     f"Club belongs to more than one group: {club}.")
            membership[club] = group
    return membership


def _validate_source_fields(row: dict) -> None:
    """Keep normalized identifiers and labels tied to the original source values."""
    _require(re.fullmatch(r"[0-9]+", row["match_id"]) is not None
             and int(row["match_id"]) > 0, "Invalid source match_id.")
    _require(row["source_url"] ==
             f"https://data.j-league.or.jp/SFMS02/?match_card_id={row['match_id']}",
             "source_url differs from match_id.")
    _require(_COMPETITIONS.get(row["competition"]) == (row["stage"], row.get("group")),
             "Competition label differs from stage/group.")
    syntax = unicodedata.normalize("NFKC", row["round_label"])
    unit = "節" if row["stage"] == "regional" else "戦"
    parts = re.fullmatch(rf"第([0-9]+){unit}第([0-9]+)日", syntax)
    number = row["round"] if row["stage"] == "regional" else row["leg"]
    _require(parts is not None and int(parts[1]) == number and int(parts[2]) > 0,
             "round_label differs from round/leg.")
    label = unicodedata.normalize("NFKC", row["match_date_label"])
    parts = re.fullmatch(r"(26/[0-9]{2}/[0-9]{2})\([月火水木金土日](?:・[祝休])?\)", label)
    _require(parts is not None and parts[1] == row["match_date"].strftime("%y/%m/%d"),
             "match_date_label differs from match_date.")
    _require(re.fullmatch(r"[0-9]{2}:[0-9]{2}", row["kickoff_time"]) is not None,
             "Invalid kickoff_time.")
    try:
        time.fromisoformat(row["kickoff_time"])
    except ValueError as exc:
        raise HyakunenValidationError("Invalid kickoff_time.") from exc
    score = re.fullmatch(r"([0-9]+)-([0-9]+)(?:\s*\(PK([0-9]+)-([0-9]+)\))?",
                         unicodedata.normalize("NFKC", row["raw_score_text"]))
    _require(score is not None, "Invalid raw_score_text.")
    parsed = tuple(int(value) if value is not None else None for value in score.groups())
    _require(parsed == (row["displayed_home_score"], row["displayed_away_score"],
                         row["home_pk_score"], row["away_pk_score"]),
             "Raw score differs from normalized displayed/PK scores.")
    for side in ("home", "away"):
        url = _text(row.get(f"{side}_team_source_url"), f"{side}_team_source_url")
        _require(re.fullmatch(r"https?://www\.jleague\.jp/club/[a-z0-9_-]+/profile/", url) is not None,
                 "Invalid team profile URL.")
    _require(row["home_team_source_url"] != row["away_team_source_url"],
             "Home and away profile URLs must differ.")


def normalize_matches(records: list[dict], details: dict[str, dict]) -> pd.DataFrame:
    """Return typed match rows, keeping source order and all source fields.

Every playoff second leg requires a detail record. The caller must verify cache
provenance before parsing; this function checks the independent score views.
Full season cardinality and two-leg rules are checked by validate_competition.
"""
    _require(bool(records), "At least one match is required.")
    membership = _group_membership(records)
    normalized = []
    for source in records:
        row = dict(source)
        for name in ("match_id", "home_team", "away_team", "stadium", "source_url",
                     "competition", "round_label", "raw_score_text", "kickoff_time",
                     "broadcast_raw", "match_date_label", "source_season_label"):
            row[name] = _text(row.get(name), name)
        for name, expected in (("season", 2026), ("source_year_id", 20261),
                               ("source_frame_id", 35)):
            _require(_integer(row.get(name), name) == expected, f"Invalid {name}.")
        _require(row.get("competition_key") == COMPETITION_KEY,
                 "Unexpected competition_key.")
        _require(row["source_season_label"] == "2026特別", "Unexpected source season.")
        _require(row["home_team"] != row["away_team"], "A club cannot play itself.")
        row["match_date"] = _date(row.get("match_date"))
        stage = row.get("stage")
        _require(stage in ("regional", "playoff"), "Invalid stage.")
        row["round"] = _integer(row.get("round"), "round", nullable=True)
        row["leg"] = _integer(row.get("leg"), "leg", nullable=True)
        if stage == "regional":
            _require(row["round"] in range(1, 19) and row["leg"] is None,
                     "Regional matches require round 1..18 and null leg.")
            _require(_null(row.get("placement_range")), "Regional placement must be null.")
        else:
            _require(row["leg"] in (1, 2) and row["round"] is None
                     and _null(row.get("group")),
                     "Playoffs require leg 1/2 and null round/group.")
            _require(row.get("placement_range") in {f"{n}-{n+1}" for n in range(1, 20, 2)},
                     "Invalid playoff placement_range.")
        for side in ("home", "away"):
            team = row[f"{side}_team"]
            _require(team in membership, f"No regional membership for {team}.")
            row[f"{side}_group"] = membership[team]
            if stage == "regional":
                _require(membership[team] == row["group"], "Cross-group regional match.")
            row[f"displayed_{side}_score"] = _integer(
                row.get(f"displayed_{side}_score"), f"displayed_{side}_score")
        home_pk, away_pk = _pk(row)
        row.update(home_pk_score=home_pk, away_pk_score=away_pk)
        _validate_source_fields(row)
        detail = details.get(row["match_id"])
        _require(not (stage == "playoff" and row["leg"] == 2 and detail is None),
                 f"Missing second-leg detail for {row['match_id']}.")
        if detail is not None:
            _require(type(detail.get("extra_time_played")) is bool,
                     "extra_time_played must be a boolean.")
            extra_time = detail["extra_time_played"]
            _require(_pk(detail) == (home_pk, away_pk), "Listing/detail PK disagreement.")
            for side in ("home", "away"):
                displayed = _integer(detail.get(f"displayed_{side}_score"),
                                     f"detail displayed_{side}_score")
                _require(displayed == row[f"displayed_{side}_score"],
                         "Listing/detail score disagreement.")
                row[f"{side}_score"] = _integer(detail.get(f"{side}_score_90"),
                                               f"{side}_score_90")
                increment = _integer(detail.get(f"{side}_extra_time_score"),
                                     f"{side}_extra_time_score", nullable=not extra_time)
                _require(extra_time or increment is None,
                         "Unplayed extra time must have null scores.")
                _require(row[f"{side}_score"] + (increment or 0) == displayed,
                         "90-minute plus extra-time scores disagree with displayed score.")
                row[f"{side}_extra_time_score"] = increment
                row[f"{side}_team_detail"] = _text(
                    detail.get(f"{side}_team_detail"), f"{side}_team_detail")
        else:
            extra_time = False
            for side in ("home", "away"):
                row[f"{side}_score"] = row[f"displayed_{side}_score"]
                row[f"{side}_extra_time_score"] = None
                row[f"{side}_team_detail"] = None
        _require(not extra_time or (stage == "playoff" and row["leg"] == 2),
                 "Extra time is only possible in playoff second legs.")
        row["extra_time_played"] = extra_time
        row["detail_source_url"] = row["source_url"] if detail is not None else None
        row["score_90_source"] = "detail_periods" if detail is not None else "listing_no_extra_time"
        row["result"] = _result(row["home_score"], row["away_score"])
        row["pk_played"] = home_pk is not None
        row["pk_scope"] = ("match" if stage == "regional" else "tie") if home_pk is not None else None
        row["pk_winner_team"] = (
            _score_winner(home_pk, away_pk, row["home_team"], row["away_team"])
            if home_pk is not None else None
        )
        winner = _score_winner(row["displayed_home_score"], row["displayed_away_score"],
                               row["home_team"], row["away_team"])
        decision = ("extra_time" if extra_time else "regulation") if winner else "draw"
        row["home_points"] = row["away_points"] = None
        if stage == "regional":
            _require((row["result"] == 1) == row["pk_played"],
                     "Regional 90-minute draws require PK; wins must not have PK.")
            if row["pk_played"]:
                winner, decision = row["pk_winner_team"], "penalties"
            points = (2, 1) if row["pk_played"] else (3, 0)
            row["home_points"], row["away_points"] = (
                points if winner == row["home_team"] else points[::-1]
            )
        elif row["leg"] == 1:
            _require(not row["pk_played"], "First playoff legs cannot have PK.")
        else:
            _require(not row["pk_played"] or extra_time,
                     "Playoff PK requires extra time.")
        row["match_winner_team"], row["match_decision"] = winner, decision
        row["playoff_tie_id"] = (
            f"{COMPETITION_KEY}_{row['placement_range']}" if stage == "playoff" else None
        )
        normalized.append(row)
    frame = pd.DataFrame(normalized)
    _require(not frame["match_id"].duplicated().any(), "Duplicate match_id.")
    _require(not frame.duplicated(["match_date", "home_team", "away_team"]).any(),
             "Duplicate match fixture.")
    return frame.astype({name: dtype for name, dtype in MATCH_DTYPES.items() if name in frame})


def build_playoff_ties(matches: pd.DataFrame) -> pd.DataFrame:
    """Resolve ties after both legs; do not attach future winners to match rows."""
    rows = []
    for tie_id, pair in matches.loc[matches["stage"] == "playoff"].groupby(
            "playoff_tie_id", sort=False, dropna=False):
        _require(not _null(tie_id) and len(pair) == 2 and set(pair["leg"]) == {1, 2},
                 "Every playoff tie requires exactly legs 1 and 2.")
        first, second = (pair.loc[pair["leg"] == leg].iloc[0] for leg in (1, 2))
        _require(first["match_date"] < second["match_date"], "Playoff leg dates out of order.")
        _require(first["home_team"] == second["away_team"]
                 and first["away_team"] == second["home_team"],
                 "Playoff legs must reverse home/away.")
        _require(first["home_group"] == second["away_group"] == "WEST"
                 and first["away_group"] == second["home_group"] == "EAST",
                 "Playoff first leg must be WEST home and second leg EAST home.")
        east, west = second["home_team"], second["away_team"]
        east_90 = int(first["away_score"] + second["home_score"])
        west_90 = int(first["home_score"] + second["away_score"])
        east_wins = int(first["result"] == 0) + int(second["result"] == 2)
        west_wins = int(first["result"] == 2) + int(second["result"] == 0)
        extra_time = bool(second["extra_time_played"])
        pk_played = bool(second["pk_played"])
        regulation_tied = east_wins == west_wins and east_90 == west_90
        _require(extra_time == regulation_tied,
                 "Extra time must occur exactly when wins and aggregate goals are tied.")
        east_total, west_total = east_90, west_90
        if east_wins != west_wins:
            winner = east if east_wins > west_wins else west
            decision = "regulation_wins"
        elif east_90 != west_90:
            winner = east if east_90 > west_90 else west
            decision = "regulation_goal_difference"
        else:
            east_total += int(second["home_extra_time_score"])
            west_total += int(second["away_extra_time_score"])
            _require(pk_played == (east_total == west_total),
                     "Playoff PK must occur exactly when aggregate remains tied after extra time.")
            if pk_played:
                winner = second["pk_winner_team"]
                _require(winner in (east, west), "Missing playoff PK winner.")
                decision = "penalties"
            else:
                winner = east if east_total > west_total else west
                decision = "extra_time"
        _require(not pk_played or extra_time, "Unexpected playoff PK.")
        rows.append({
            "competition_key": COMPETITION_KEY, "playoff_tie_id": tie_id,
            "placement_range": first["placement_range"], "east_team": east,
            "west_team": west, "first_match_id": first["match_id"],
            "second_match_id": second["match_id"], "first_match_date": first["match_date"],
            "second_match_date": second["match_date"], "confirmed_date": second["match_date"],
            "east_score_90": east_90, "west_score_90": west_90,
            "east_total_score": east_total, "west_total_score": west_total,
            "east_wins_90": east_wins, "west_wins_90": west_wins,
            "tie_winner_team": winner, "tie_decision": decision,
        })
    return pd.DataFrame(rows)


def _validate_match_rows(matches: pd.DataFrame) -> None:
    _require(isinstance(matches, pd.DataFrame), "matches must be a DataFrame.")
    _require(not matches.columns.has_duplicates, "Duplicate column names.")
    missing = set(MATCH_DTYPES) - set(matches.columns)
    _require(not missing, f"Missing normalized columns: {sorted(missing)}.")
    # Rebuild derived values from independent listing/detail score fields and
    # compare them, so tampering with winner/result/points flags is not accepted.
    records, details = [], {}
    for source in matches.to_dict("records"):
        record = {name: None if _null(value) else value for name, value in source.items()}
        records.append(record)
        if record["score_90_source"] == "detail_periods":
            details[record["match_id"]] = {
                "home_score_90": record["home_score"], "away_score_90": record["away_score"],
                **{name: record[name] for name in (
                    "extra_time_played", "home_extra_time_score", "away_extra_time_score",
                    "displayed_home_score", "displayed_away_score", "home_pk_score",
                    "away_pk_score", "home_team_detail", "away_team_detail",
                )},
            }
    rebuilt = normalize_matches(records, details)
    for name in MATCH_DTYPES:
        actual = matches[name].reset_index(drop=True)
        expected = rebuilt[name]
        _require(bool((actual.eq(expected).fillna(False) | (actual.isna() & expected.isna())).all()),
                 f"Inconsistent normalized column: {name}.")


def validate_competition(matches: pd.DataFrame) -> dict:
    """Check completed 2026 competition structure, scores and all directed cards.

The two ten-club groups are part of the official competition configuration.
Expected match and venue counts are derived from that format, not ordinary J1.
"""
    _validate_match_rows(matches)
    group_size = 10
    regional = matches.loc[matches["stage"] == "regional"]
    groups = {}
    for group in ("EAST", "WEST"):
        subset = regional.loc[regional["group"] == group]
        clubs = set(subset["home_team"]) | set(subset["away_team"])
        _require(len(clubs) == group_size, f"{group} must have {group_size} clubs.")
        rounds = subset.groupby("round").size().to_dict()
        expected_rounds = dict.fromkeys(range(1, 2 * (group_size - 1) + 1), group_size // 2)
        _require(rounds == expected_rounds, f"Invalid {group} round coverage.")
        for number, round_rows in subset.groupby("round"):
            playing = list(round_rows["home_team"]) + list(round_rows["away_team"])
            _require(Counter(playing) == dict.fromkeys(clubs, 1),
                     f"A club appears twice or is missing in {group} round {number}.")
        cards = Counter(zip(subset["home_team"], subset["away_team"]))
        _require(cards == Counter(permutations(clubs, 2)),
                 f"Incomplete or duplicate ordered pairings in {group}.")
        groups[group] = clubs
    _require(not groups["EAST"] & groups["WEST"], "Regional groups overlap.")
    ties = build_playoff_ties(matches)
    _require(len(ties) == group_size, "Expected one playoff tie per group position.")
    _require(set(ties["placement_range"]) == {f"{n}-{n+1}" for n in range(1, 20, 2)},
             "Playoff placement coverage is incomplete.")
    _require(Counter(ties["east_team"]) == dict.fromkeys(groups["EAST"], 1)
             and Counter(ties["west_team"]) == dict.fromkeys(groups["WEST"], 1),
             "Each club must appear in exactly one playoff tie.")
    playoff = matches.loc[matches["stage"] == "playoff"]
    _require(regional["match_date"].max() < playoff["match_date"].min(),
             "Playoffs must follow the regional round.")
    clubs = groups["EAST"] | groups["WEST"]
    expected_home = group_size - 1 + 1
    for side in ("home", "away"):
        _require(Counter(matches[f"{side}_team"]) == dict.fromkeys(clubs, expected_home),
                 f"Unexpected per-club {side} match counts.")
    regional_count = 2 * group_size * (group_size - 1)
    playoff_count = 2 * group_size
    _require(len(matches) == regional_count + playoff_count, "Unexpected total matches.")
    return {
        "club_count": len(clubs), "clubs_per_group": group_size,
        "rounds_per_group": 2 * (group_size - 1),
        "regional_matches": regional_count, "playoff_matches": playoff_count,
        "playoff_ties": len(ties), "expected_matches": regional_count + playoff_count,
        "matches_per_club": 2 * expected_home, "home_matches_per_club": expected_home,
        "away_matches_per_club": expected_home, "all_regional_pairings_covered": True,
        "all_playoff_pairings_covered": True,
    }
