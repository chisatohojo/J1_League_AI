import copy
import hashlib
import json
from pathlib import Path

import pytest

from src.collect.cup_regulation_result_prototype import (
    CONFIRMED, UNRESOLVED, CupRegulationError, parse_jleague_sfms02,
    parse_jfa_match_page, parse_jfa_schedule_result,
)


FIXTURES = Path(__file__).parent / "fixtures/cup_regulation_result"


def _jleague(name, match_id, home, away):
    raw = (FIXTURES / name).read_bytes()
    match_date = "2024-11-02" if match_id == "31274" else "2018-03-07"
    return parse_jleague_sfms02(
        raw, season=2024 if match_id == "31274" else 2018,
        source_match_id=match_id, match_date=match_date,
        home_team_id="home-id", away_team_id="away-id",
        expected_home_team=home, expected_away_team=away,
        source_url=f"https://data.j-league.or.jp/SFMS02/?match_card_id={match_id}",
    )


def _jfa(score):
    item = {
        "matchNumber": "59", "homeTeamName": "名古屋", "awayTeamName": "仙台",
        "matchDate": "2023/07/12",
        "score": score,
    }
    raw = json.dumps({"matchScheduleList": {"matchSchedule": [item]}}).encode()
    return parse_jfa_schedule_result(
        raw, season=2023, source_match_id="2023-m59", match_date="2023-07-12",
        home_team_id="home-id", away_team_id="away-id",
        expected_home_team="名古屋", expected_away_team="仙台",
        source_url="https://www.jfa.jp/match/emperorscup_2023/match/schedule.json",
    )


def test_jleague_regulation_draw_uses_two_halves():
    row = _jleague("jleague_regulation.html", "21051", "仙台", "新潟")
    assert (row["regulation_home_score"], row["regulation_away_score"]) == (1, 1)
    assert row["regulation_result"] == 1
    assert row["extra_time_played"] is False
    assert row["penalty_shootout_played"] is False
    assert row["resolution_status"] == CONFIRMED


def test_jleague_final_score_never_replaces_regulation_draw():
    row = _jleague("jleague_extra_pk.html", "31274", "名古屋", "新潟")
    assert (row["regulation_home_score"], row["regulation_away_score"]) == (2, 2)
    assert (row["final_home_score"], row["final_away_score"]) == (3, 3)
    assert row["regulation_result"] == 1
    assert row["extra_time_played"] is True
    assert row["penalty_shootout_played"] is True


def test_jleague_identity_and_period_arithmetic_fail_closed():
    with pytest.raises(CupRegulationError, match="home/away identity"):
        _jleague("jleague_regulation.html", "21051", "wrong", "新潟")
    raw = (FIXTURES / "jleague_regulation.html").read_bytes().replace(b">1</td><th", b">2</td><th")
    with pytest.raises(CupRegulationError, match="period/final"):
        parse_jleague_sfms02(
            raw, season=2018, source_match_id="21051", match_date="2018-03-07",
            home_team_id="h", away_team_id="a", expected_home_team="仙台",
            expected_away_team="新潟",
            source_url="https://data.j-league.or.jp/SFMS02/?match_card_id=21051",
        )


def test_jleague_source_match_id_cannot_be_substituted():
    raw = (FIXTURES / "jleague_regulation.html").read_bytes()
    with pytest.raises(CupRegulationError, match="URL/match identity"):
        parse_jleague_sfms02(
            raw, season=2018, source_match_id="21051", match_date="2018-03-07",
            home_team_id="h", away_team_id="a", expected_home_team="仙台",
            expected_away_team="新潟",
            source_url="https://data.j-league.or.jp/SFMS02/?match_card_id=31274",
        )


def test_jleague_raw_sha_is_exact_source_bytes():
    row = _jleague("jleague_regulation.html", "21051", "仙台", "新潟")
    raw = (FIXTURES / "jleague_regulation.html").read_bytes()
    assert row["raw_sha256"] == hashlib.sha256(raw).hexdigest()


def test_jleague_exact_official_club_slug_validates_full_name_identity():
    raw = (FIXTURES / "jleague_regulation.html").read_bytes()
    raw = raw.replace(
        "仙台</th>".encode(),
        '<a href="https://www.jleague.jp/club/sendai/profile/">ベガルタ仙台</a></th>'.encode(),
    ).replace(
        "新潟</th>".encode(),
        '<a href="http://www.jleague.jp/club/niigata/profile/">アルビレックス新潟</a></th>'.encode(),
    )
    kwargs = dict(
        season=2018, source_match_id="21051", match_date="2018-03-07",
        home_team_id="home-id", away_team_id="away-id",
        expected_home_team="仙台", expected_away_team="新潟",
        source_url="https://data.j-league.or.jp/SFMS02/?match_card_id=21051",
        expected_home_club_ids=("sendai",), expected_away_club_ids=("niigata",),
    )
    assert parse_jleague_sfms02(raw, **kwargs)["regulation_result"] == 1
    with pytest.raises(CupRegulationError, match="club identity"):
        parse_jleague_sfms02(
            raw, **{**kwargs, "expected_home_club_ids": ("wrong",)}
        )


@pytest.mark.parametrize("home,away,expected", [(2, 0, 2), (1, 1, 1), (0, 3, 0)])
def test_jfa_class_order_is_away_draw_home(home, away, expected):
    row = _jfa({
        "homeScore": str(home), "awayScore": str(away),
        "homeTeamScore1st": str(home), "awayTeamScore1st": str(away),
        "homeTeamScore2nd": "0", "awayTeamScore2nd": "0", "exMatch": False,
    })
    assert row["regulation_result"] == expected
    assert row["resolution_status"] == CONFIRMED


def test_jfa_raw_sha_and_match_identity_share_one_payload():
    item = {
        "matchNumber": "59", "homeTeamName": "名古屋", "awayTeamName": "仙台",
        "matchDate": "2023/07/12",
        "score": {
            "homeScore": "1", "awayScore": "0",
            "homeTeamScore1st": "0", "awayTeamScore1st": "0",
            "homeTeamScore2nd": "1", "awayTeamScore2nd": "0", "exMatch": False,
        },
    }
    raw = json.dumps({"matchScheduleList": {"matchSchedule": [item]}}).encode()
    row = parse_jfa_schedule_result(
        raw, season=2023, source_match_id="2023-m59", match_date="2023-07-12",
        home_team_id="home-id", away_team_id="away-id",
        expected_home_team="名古屋", expected_away_team="仙台",
        source_url="https://www.jfa.jp/match/emperorscup_2023/match/schedule.json",
    )
    assert row["raw_sha256"] == hashlib.sha256(raw).hexdigest()
    with pytest.raises(CupRegulationError, match="missing or duplicated"):
        parse_jfa_schedule_result(
            raw, season=2023, source_match_id="2023-m60", match_date="2023-07-12",
            home_team_id="home-id", away_team_id="away-id",
            expected_home_team="名古屋", expected_away_team="仙台",
            source_url="https://www.jfa.jp/match/emperorscup_2023/match/schedule.json",
        )


def test_jfa_extra_time_and_pk_do_not_replace_regulation_draw():
    row = _jfa({
        "homeScore": "1", "awayScore": "1",
        "homeTeamScore1st": "0", "awayTeamScore1st": "0",
        "homeTeamScore2nd": "0", "awayTeamScore2nd": "0",
        "homeTeamScore1ex": "1", "awayTeamScore1ex": "1",
        "homeTeamScore2ex": "0", "awayTeamScore2ex": "0",
        "homePKScore": "5", "awayPKScore": "4", "exMatch": True,
    })
    assert (row["regulation_home_score"], row["regulation_away_score"]) == (0, 0)
    assert row["regulation_result"] == 1
    assert row["extra_time_played"] is True
    assert row["penalty_shootout_played"] is True


def test_jfa_explicit_halves_are_usable_when_extra_breakdown_is_absent():
    row = _jfa({
        "homeScore": "2", "awayScore": "1",
        "homeTeamScore1st": "0", "awayTeamScore1st": "0",
        "homeTeamScore2nd": "0", "awayTeamScore2nd": "0",
        "exMatch": True,
    })
    assert (row["regulation_home_score"], row["regulation_away_score"]) == (0, 0)
    assert row["regulation_result"] == 1
    assert row["extra_time_played"] is True


def test_jfa_legacy_total_only_is_unresolved_not_inferred():
    row = _jfa({
        "homeScore": "4", "awayScore": "1", "exMatch": True,
    })
    assert row["regulation_home_score"] is None
    assert row["regulation_result"] is None
    assert row["resolution_status"] == UNRESOLVED
    assert row["resolution_reason"] == "official_detail_or_report_required"


def test_jfa_partial_periods_and_wrong_identity_fail_closed():
    score = {
        "homeScore": "1", "awayScore": "0",
        "homeTeamScore1st": "1", "awayTeamScore1st": "0",
    }
    with pytest.raises(CupRegulationError, match="partial JFA regulation"):
        _jfa(score)
    item = {"matchNumber": "59", "matchDate": "2023/07/12",
            "homeTeamName": "wrong", "awayTeamName": "仙台", "score": score}
    with pytest.raises(CupRegulationError, match="home/away identity"):
        parse_jfa_schedule_result(
            json.dumps({"matchScheduleList": {"matchSchedule": [item]}}).encode(),
            season=2023, source_match_id="2023-m59", match_date="2023-07-12",
            home_team_id="h", away_team_id="a", expected_home_team="名古屋",
            expected_away_team="仙台",
            source_url="https://www.jfa.jp/match/emperorscup_2023/match/schedule.json",
        )


def test_jfa_extra_time_flags_and_pk_scores_fail_closed():
    base = {
        "homeScore": "1", "awayScore": "1",
        "homeTeamScore1st": "0", "awayTeamScore1st": "0",
        "homeTeamScore2nd": "1", "awayTeamScore2nd": "1",
    }
    with pytest.raises(CupRegulationError, match="exMatch flag"):
        _jfa({**base, "exMatch": "false"})
    with pytest.raises(CupRegulationError, match="exMatch/extra-time fields conflict"):
        _jfa({
            **base, "exMatch": False,
            "homeTeamScore1ex": "0", "awayTeamScore1ex": "0",
            "homeTeamScore2ex": "0", "awayTeamScore2ex": "0",
        })
    with pytest.raises(CupRegulationError, match="tied JFA PK"):
        _jfa({**base, "exMatch": False, "homePKScore": "4", "awayPKScore": "4"})


def test_blank_or_identical_team_ids_fail_closed():
    with pytest.raises(CupRegulationError, match="home_team_id"):
        parse_jfa_schedule_result(
            json.dumps({"matchScheduleList": {"matchSchedule": [{
                "matchNumber": "59", "homeTeamName": "名古屋", "awayTeamName": "仙台",
                "matchDate": "2023/07/12",
                "score": {"homeScore": "1", "awayScore": "0"},
            }]}}).encode(),
            season=2023, source_match_id="2023-m59", match_date="2023-07-12",
            home_team_id="", away_team_id="away-id", expected_home_team="名古屋",
            expected_away_team="仙台",
            source_url="https://www.jfa.jp/match/emperorscup_2023/match/schedule.json",
        )
    with pytest.raises(CupRegulationError, match="identical home/away"):
        parse_jleague_sfms02(
            (FIXTURES / "jleague_regulation.html").read_bytes(),
            season=2018, source_match_id="21051", match_date="2018-03-07",
            home_team_id="same", away_team_id="same", expected_home_team="仙台",
            expected_away_team="新潟",
            source_url="https://data.j-league.or.jp/SFMS02/?match_card_id=21051",
        )


def test_inputs_are_not_mutated():
    score = {
        "homeScore": "2", "awayScore": "1",
        "homeTeamScore1st": "1", "awayTeamScore1st": "0",
        "homeTeamScore2nd": "1", "awayTeamScore2nd": "1", "exMatch": False,
    }
    before = copy.deepcopy(score)
    _jfa(score)
    assert score == before


def test_jfa_detail_extra_time_and_pk_preserve_regulation_draw():
    raw = (FIXTURES / "jfa_extra_pk.html").read_bytes()
    row = parse_jfa_match_page(
        raw, season=2015, source_match_id="2015-m63", match_date="2015-10-14",
        home_team_id="home-id", away_team_id="away-id",
        expected_home_team="鹿島アントラーズ",
        expected_away_team="水戸ホーリーホック",
        source_url="https://www.jfa.jp/match/emperorscup_2015/match_page/m63.html",
    )
    assert (row["regulation_home_score"], row["regulation_away_score"]) == (0, 0)
    assert row["regulation_result"] == 1
    assert row["extra_time_played"] is True
    assert row["penalty_shootout_played"] is True


def test_jfa_detail_identity_date_and_arithmetic_fail_closed():
    raw = (FIXTURES / "jfa_extra_pk.html").read_bytes()
    kwargs = dict(
        season=2015, source_match_id="2015-m63", match_date="2015-10-14",
        home_team_id="home-id", away_team_id="away-id",
        expected_home_team="鹿島アントラーズ",
        expected_away_team="水戸ホーリーホック",
        source_url="https://www.jfa.jp/match/emperorscup_2015/match_page/m63.html",
    )
    with pytest.raises(CupRegulationError, match="home/away identity"):
        parse_jfa_match_page(raw, **{**kwargs, "expected_home_team": "wrong"})
    with pytest.raises(CupRegulationError, match="match date mismatch"):
        parse_jfa_match_page(raw, **{**kwargs, "match_date": "2015-10-15"})
    broken = raw.replace(b'<div class="total-score">0</div><div class="flag">',
                         b'<div class="total-score">1</div><div class="flag">')
    with pytest.raises(CupRegulationError, match="period/final"):
        parse_jfa_match_page(broken, **kwargs)
