"""Synthetic competition checks: no dependency on acquired HTML or network."""

from copy import deepcopy
from datetime import date, timedelta

import pandas as pd
import pytest

from src.collect.jleague_hyakunen import (
    COMPETITION_KEY, HyakunenValidationError, build_playoff_ties,
    normalize_matches, validate_competition,
)


def synthetic_sources() -> tuple[list[dict], dict[str, dict]]:
    """A complete artificial 200-match competition, including ET and tie PK."""
    records, details = [], {}

    def append(home, away, day, *, stage="regional", group=None, round_number=None,
               leg=None, placement=None, score=(1, 0), extra=None, pk=None):
        match_id = f"0{len(records) + 1:04d}"
        displayed = tuple(score[i] + (extra[i] if extra else 0) for i in range(2))
        row = {
            "match_id": match_id, "season": 2026, "competition_key": COMPETITION_KEY,
            "source_year_id": 20261, "source_frame_id": 35,
            "source_season_label": "2026特別",
            "competition": "明治安田Ｊ１百年構想 " + (group + "グループ" if group else "プレーオフラウンド"),
            "stage": stage, "group": group, "round": round_number, "leg": leg,
            "round_label": f"第{round_number}節第1日" if stage == "regional" else f"第{leg}戦第1日",
            "match_date": day.isoformat(), "kickoff_time": "14:03", "home_team": home,
            "away_team": away, "stadium": f"人工会場{home}",
            "source_url": f"https://data.j-league.or.jp/SFMS02/?match_card_id={match_id}",
            "home_team_source_url": f"http://www.jleague.jp/club/{home.lower()}/profile/",
            "away_team_source_url": f"http://www.jleague.jp/club/{away.lower()}/profile/",
            "raw_score_text": f"{displayed[0]}-{displayed[1]}" + (f"(PK{pk[0]}-{pk[1]})" if pk else ""),
            "displayed_home_score": displayed[0], "displayed_away_score": displayed[1],
            "home_pk_score": pk[0] if pk else None, "away_pk_score": pk[1] if pk else None,
            "placement_range": placement, "broadcast_raw": f"{placement or ''}人工放送",
            "match_date_label": day.strftime("%y/%m/%d") + "(土)",
        }
        records.append(row)
        if leg == 2:
            details[match_id] = {
                "home_score_90": score[0], "away_score_90": score[1],
                "extra_time_played": extra is not None,
                "home_extra_time_score": extra[0] if extra else None,
                "away_extra_time_score": extra[1] if extra else None,
                "displayed_home_score": displayed[0], "displayed_away_score": displayed[1],
                "home_pk_score": pk[0] if pk else None, "away_pk_score": pk[1] if pk else None,
                "home_team_detail": home + "正式名称", "away_team_detail": away + "正式名称",
            }

    for group in ("EAST", "WEST"):
        clubs = [f"{group}{number:02d}" for number in range(10)]
        rotation = clubs.copy()
        first_half = []
        for _ in range(9):
            first_half.append(list(zip(rotation[:5], reversed(rotation[5:]))))
            rotation = [rotation[0], rotation[-1], *rotation[1:-1]]
        rounds = first_half + [[(away, home) for home, away in pairs] for pairs in first_half]
        for number, pairs in enumerate(rounds, 1):
            for i, (home, away) in enumerate(pairs):
                is_pk = number == 1 and i == 0
                append(home, away, date(2026, 2, 6) + timedelta(days=(number - 1) * 6),
                       group=group, round_number=number,
                       score=(2, 2) if is_pk else (1, 0), pk=(14, 13) if is_pk else None)
    for club in range(10):
        first_score = (0, 0) if club in (1, 3) else (1, 0)
        append(f"WEST{club:02d}", f"EAST{club:02d}", date(2026, 5, 30),
               stage="playoff", leg=1, placement=f"{club*2+1}-{club*2+2}", score=first_score)
        second_score = (2, 0) if club == 0 else (0, 0) if club in (1, 3) else (1, 0) if club == 2 else (0, 1)
        append(f"EAST{club:02d}", f"WEST{club:02d}", date(2026, 6, 6),
               stage="playoff", leg=2, placement=f"{club*2+1}-{club*2+2}", score=second_score,
               extra=(2, 1) if club == 1 else (0, 0) if club in (2, 3) else None,
               pk=(4, 5) if club in (2, 3) else None)
    return records, details


@pytest.fixture
def sources():
    return synthetic_sources()


def test_complete_competition_and_source_order_are_preserved(sources):
    records, details = sources
    original = deepcopy(sources)
    matches = normalize_matches(records, details)
    summary = validate_competition(matches)
    assert summary["expected_matches"] == 200
    assert summary["regional_matches"] == 180
    assert summary["playoff_matches"] == 20
    assert summary["matches_per_club"] == 20
    assert summary["home_matches_per_club"] == summary["away_matches_per_club"] == 10
    assert summary["all_regional_pairings_covered"] is True
    assert matches.match_id.tolist() == [r["match_id"] for r in records]
    assert sources == original
    assert str(matches.match_date.dtype) == "datetime64[ns]"
    assert str(matches.match_id.dtype) == "string"
    assert matches.loc[matches.stage == "playoff", "round"].isna().all()
    assert matches.loc[matches.stage == "regional", "leg"].isna().all()
    assert "tie_winner_team" not in matches


def test_regional_pk_keeps_90_minute_draw_and_records_points(sources):
    match = normalize_matches(*sources).iloc[0]
    assert (match.home_score, match.away_score, match.result) == (2, 2, 1)
    assert (match.home_pk_score, match.away_pk_score) == (14, 13)
    assert match.pk_scope == "match"
    assert match.match_winner_team == match.home_team
    assert match.match_decision == "penalties"
    assert (match.home_points, match.away_points) == (2, 1)
    assert not match.extra_time_played
    assert pd.isna(match.home_extra_time_score)


def test_extra_time_is_incremental_and_separate_from_90_result(sources):
    matches = normalize_matches(*sources)
    match = matches.loc[(matches.placement_range == "3-4") & (matches.leg == 2)].iloc[0]
    assert (match.home_score, match.away_score, match.result) == (0, 0, 1)
    assert (match.home_extra_time_score, match.away_extra_time_score) == (2, 1)
    assert match.match_winner_team == match.home_team
    assert match.match_decision == "extra_time"
    tie = build_playoff_ties(matches).set_index("placement_range").loc["3-4"]
    assert (tie.east_score_90, tie.west_score_90) == (0, 0)
    assert (tie.east_total_score, tie.west_total_score) == (2, 1)
    assert tie.tie_decision == "extra_time"
    assert tie.confirmed_date == pd.Timestamp("2026-06-06")


@pytest.mark.parametrize("placement,decision,winner", [
    ("1-2", "regulation_goal_difference", "EAST00"),
    ("3-4", "extra_time", "EAST01"),
    ("5-6", "penalties", "WEST02"),
    ("7-8", "penalties", "WEST03"),
    ("9-10", "regulation_wins", "WEST04"),
])
def test_playoff_tie_deciding_methods(sources, placement, decision, winner):
    tie = build_playoff_ties(normalize_matches(*sources)).set_index("placement_range").loc[placement]
    assert tie.tie_decision == decision
    assert tie.tie_winner_team == winner


@pytest.mark.parametrize("placement,match_winner,decision", [
    ("5-6", "EAST02", "extra_time"), ("7-8", None, "draw"),
])
def test_playoff_pk_does_not_overwrite_single_match_outcome(sources, placement, match_winner, decision):
    matches = normalize_matches(*sources)
    match = matches.loc[(matches.placement_range == placement) & (matches.leg == 2)].iloc[0]
    assert match.pk_scope == "tie"
    assert match.pk_winner_team.startswith("WEST")
    if match_winner is None:
        assert pd.isna(match.match_winner_team)
    else:
        assert match.match_winner_team == match_winner
    assert match.match_decision == decision
    assert pd.isna(match.home_points)


@pytest.mark.parametrize("field,value", [
    ("season", 20261), ("source_year_id", 2026), ("source_frame_id", 1),
    ("competition_key", "j1_2026"), ("stage", "full_season"), ("group", "OTHER"),
    ("round", 0), ("round", 19), ("leg", 1), ("home_team", "EAST09"),
    ("stadium", ""), ("match_id", None), ("match_date", "2026-02-30"),
    ("match_date", "2025-02-06"), ("displayed_home_score", -1),
    ("displayed_home_score", 1.5), ("displayed_home_score", True),
    ("away_pk_score", None), ("away_pk_score", 14),
    ("source_url", "https://data.j-league.or.jp/SFMS02/?match_card_id=99999"),
    ("competition", "WRONG"), ("round_label", "第２節第１日"),
    ("match_date_label", "26/02/07(土)"), ("kickoff_time", "25:00"),
    ("raw_score_text", "2-2(PK4-3)"), ("home_team_source_url", "invalid"),
])
def test_invalid_source_values_are_rejected(sources, field, value):
    records, details = sources
    records[0][field] = value
    with pytest.raises(HyakunenValidationError):
        normalize_matches(records, details)


def test_missing_second_leg_detail_does_not_guess_90_score(sources):
    records, details = sources
    details.pop(next(iter(details)))
    with pytest.raises(HyakunenValidationError, match="Missing second-leg detail"):
        normalize_matches(records, details)


@pytest.mark.parametrize("field,value", [
    ("displayed_home_score", 99), ("home_score_90", 99),
    ("extra_time_played", "False"), ("home_extra_time_score", 0),
    ("home_pk_score", 3), ("home_score_90", -1),
    ("home_team_detail", None),
])
def test_detail_score_mismatch_is_rejected(sources, field, value):
    records, details = sources
    details[next(iter(details))][field] = value
    with pytest.raises(HyakunenValidationError):
        normalize_matches(records, details)


@pytest.mark.parametrize("operation", ["duplicate_id", "duplicate_fixture", "regional_pk_missing", "regional_pk_on_win"])
def test_source_cross_field_errors(sources, operation):
    records, details = sources
    if operation == "duplicate_id":
        records[1]["match_id"] = records[0]["match_id"]
        records[1]["source_url"] = records[0]["source_url"]
    elif operation == "duplicate_fixture":
        records.append({**records[0], "match_id": "90000",
                        "source_url": "https://data.j-league.or.jp/SFMS02/?match_card_id=90000"})
    elif operation == "regional_pk_missing":
        records[0]["home_pk_score"] = records[0]["away_pk_score"] = None
        records[0]["raw_score_text"] = "2-2"
    else:
        records[0]["displayed_home_score"] = 3
        records[0]["raw_score_text"] = "3-2(PK14-13)"
    with pytest.raises(HyakunenValidationError):
        normalize_matches(records, details)


@pytest.mark.parametrize("field,value", [
    ("result", 0), ("home_score", 9), ("home_points", 3),
    ("match_decision", "regulation"), ("match_winner_team", "unknown"),
    ("pk_scope", "tie"), ("pk_played", False), ("extra_time_played", True),
    ("home_group", "WEST"), ("score_90_source", "unknown"),
    ("playoff_tie_id", "unexpected"),
])
def test_validation_rejects_tampered_derived_values(sources, field, value):
    matches = normalize_matches(*sources)
    matches.loc[0, field] = value
    with pytest.raises(HyakunenValidationError):
        validate_competition(matches)


@pytest.mark.parametrize("operation", ["missing_match", "missing_column", "missing_group", "wrong_round", "repeat_card", "playoff_date", "repeated_playoff_club"])
def test_competition_coverage_errors(sources, operation):
    records, details = sources
    if operation == "missing_match":
        records.pop(4)
    elif operation == "missing_group":
        records = [r for r in records if r["group"] != "WEST"]
    elif operation == "wrong_round":
        records[4]["round"] = 2
        records[4]["round_label"] = "第2節第1日"
    elif operation == "repeat_card":
        # Keep row count and a unique date but repeat a pairing.
        records[4].update(home_team=records[3]["home_team"], away_team=records[3]["away_team"],
                          match_date="2026-02-07", match_date_label="26/02/07(土)")
    elif operation == "playoff_date":
        records[180]["match_date"] = "2026-06-07"
        records[180]["match_date_label"] = "26/06/07(日)"
    elif operation == "repeated_playoff_club":
        records[182]["away_team"] = "EAST00"
        records[183]["home_team"] = "EAST00"
    with pytest.raises(HyakunenValidationError):
        matches = normalize_matches(records, details)
        if operation == "missing_column":
            matches = matches.drop(columns="result")
        validate_competition(matches)


@pytest.mark.parametrize("operation", ["unnecessary_et", "missing_et", "unnecessary_pk", "missing_pk", "wrong_leg_orientation"])
def test_two_leg_inconsistency_is_rejected(sources, operation):
    records, details = sources
    if operation == "unnecessary_et":
        detail = details[records[181]["match_id"]]
        detail.update(extra_time_played=True, home_extra_time_score=0, away_extra_time_score=0)
    elif operation == "missing_et":
        detail = details[records[187]["match_id"]]
        detail.update(extra_time_played=False, home_extra_time_score=None, away_extra_time_score=None,
                      home_pk_score=None, away_pk_score=None)
        records[187].update(home_pk_score=None, away_pk_score=None)
    elif operation == "unnecessary_pk":
        detail = details[records[183]["match_id"]]
        detail.update(home_pk_score=4, away_pk_score=5)
        records[183].update(home_pk_score=4, away_pk_score=5)
    elif operation == "missing_pk":
        detail = details[records[185]["match_id"]]
        detail.update(home_pk_score=None, away_pk_score=None)
        records[185].update(home_pk_score=None, away_pk_score=None)
    else:
        for row in records[180:182]:
            row["home_team"], row["away_team"] = row["away_team"], row["home_team"]
    # Keep raw/listing PK fields consistent so these cases reach the two-leg rule checks.
    for row in records[180:]:
        row["raw_score_text"] = f"{row['displayed_home_score']}-{row['displayed_away_score']}"
        if row["home_pk_score"] is not None:
            row["raw_score_text"] += f"(PK{row['home_pk_score']}-{row['away_pk_score']})"
    with pytest.raises(HyakunenValidationError):
        validate_competition(normalize_matches(records, details))
