from pathlib import Path

import pytest

from src.collect.player_identity_prototype import (
    OfficialPlayerRecord,
    PlayerIdentityPrototypeError,
    SOURCE_NAMESPACE,
    link_exact_player_identities,
    parse_sfpr01_enumeration,
)


FIXTURE = Path(__file__).parent / "fixtures/player_identity_prototype/sfpr01_display_names_only.html"
SOURCE_URL = (
    "https://data.j-league.or.jp/SFPR01/search?competition_frame_id=1"
    "&competition_frame_id_ex=1&competition_id=589&competition_id_ex=589"
    "&competition_year=2024&competition_year_ex=2024&dataSize=1&pageStartNo=0"
    "&selectedCompetitionName=%EF%BC%AA%EF%BC%91%E3%83%AA%E3%83%BC%E3%82%B0"
    "&selectedCompetitionYear=2024%E5%B9%B4"
    "&selectedTeamName=%EF%BC%A3%E5%A4%A7%E9%98%AA&team_id=20&team_id_ex=20"
)


def official(season, team_id, player_id, name):
    return OfficialPlayerRecord(
        season=season,
        team_id=team_id,
        official_player_id=player_id,
        official_player_name=name,
        source_namespace=SOURCE_NAMESPACE,
        source_profile_url=f"https://data.j-league.or.jp/SFIX04/?player_id={player_id}",
    )


def test_sfpr01_fixture_enumerates_exact_names_but_no_player_ids():
    audit = parse_sfpr01_enumeration(
        FIXTURE.read_bytes(), season=2024, team_id="team_0002",
        source_team_name="セレッソ大阪", source_url=SOURCE_URL,
    )
    assert [row.official_player_name for row in audit.players] == [
        "ヤン　ハンビン", "レオ　セアラ",
    ]
    assert audit.display_player_count == 2
    assert audit.id_bearing_player_count == 0
    assert audit.id_enumeration_complete is False


def test_sfpr01_parser_requires_the_official_route_season_and_exact_team_text():
    raw = FIXTURE.read_bytes()
    with pytest.raises(PlayerIdentityPrototypeError, match="official SFPR01 season"):
        parse_sfpr01_enumeration(
            raw, season=2023, team_id="team_0002", source_team_name="セレッソ大阪",
            source_url=SOURCE_URL,
        )
    with pytest.raises(PlayerIdentityPrototypeError, match="team identity"):
        parse_sfpr01_enumeration(
            raw, season=2024, team_id="team_0002", source_team_name="Ｃ大阪",
            source_url=SOURCE_URL,
        )


def test_exact_linkage_is_deterministic_and_counts_unique_players_separately_from_rows():
    rows = [
        {"season": "2024", "team_id": "team_0002", "player_name_raw": "レオ　セアラ"},
        {"season": "2024", "team_id": "team_0002", "player_name_raw": "レオ　セアラ"},
        {"season": "2024", "team_id": "team_0002", "player_name_raw": "香川　真司"},
    ]
    players = [official(2024, "team_0002", "19209", "レオ　セアラ")]
    first = link_exact_player_identities(rows, players)
    second = link_exact_player_identities(reversed(rows), reversed(players))
    assert first.links == second.links
    assert first.sfms02_unique_players == 2
    assert first.sfms02_player_match_rows == 3
    assert first.unique_status_counts == {
        "AMBIGUOUS": 0, "COLLISION": 0, "EXACT": 1, "UNRESOLVED": 1,
    }
    assert first.player_match_status_counts == {
        "AMBIGUOUS": 0, "COLLISION": 0, "EXACT": 2, "UNRESOLVED": 1,
    }
    assert first.exact_linkage_rate == 0.5


def test_no_unicode_or_whitespace_normalization_is_used_for_identity():
    rows = [{"season": "2024", "team_id": "team_0005", "player_name_raw": "松田 陸"}]
    result = link_exact_player_identities(
        rows, [official(2024, "team_0005", "11446", "松田　陸")],
    )
    assert result.links[0].link_status == "UNRESOLVED"
    assert result.links[0].official_player_id == ""


@pytest.mark.parametrize(
    ("name", "left_id", "left_team", "right_id", "right_team", "season"),
    [
        ("セルジーニョ", "29580", "team_kashima", "23156", "team_matsumoto", 2019),
        ("松田　陸", "11446", "team_cosaka", "29236", "team_gosaka", 2018),
    ],
)
def test_known_same_name_people_keep_distinct_official_ids_by_exact_scope(
        name, left_id, left_team, right_id, right_team, season):
    rows = [
        {"season": str(season), "team_id": left_team, "player_name_raw": name},
        {"season": str(season), "team_id": right_team, "player_name_raw": name},
    ]
    result = link_exact_player_identities(rows, [
        official(season, left_team, left_id, name),
        official(season, right_team, right_id, name),
    ], known_collision_names={name})
    assert [link.link_status for link in result.links] == ["EXACT", "EXACT"]
    assert {link.official_player_id for link in result.links} == {left_id, right_id}


def test_known_collision_without_scoped_id_is_not_downgraded_to_unresolved():
    result = link_exact_player_identities(
        [{"season": "2024", "team_id": "team_0005", "player_name_raw": "松田　陸"}],
        [], known_collision_names={"松田　陸"},
    )
    assert result.links[0].link_status == "COLLISION"


def test_multiple_scoped_ids_are_ambiguous_or_known_collision():
    rows = [{"season": "2024", "team_id": "team_x", "player_name_raw": "同名"}]
    players = [official(2024, "team_x", "1", "同名"), official(2024, "team_x", "2", "同名")]
    assert link_exact_player_identities(rows, players).links[0].link_status == "AMBIGUOUS"
    assert link_exact_player_identities(
        rows, players, known_collision_names={"同名"},
    ).links[0].link_status == "COLLISION"


def test_profile_namespace_and_id_must_be_exactly_self_consistent():
    bad = OfficialPlayerRecord(2024, "team_0002", "19209", "レオ　セアラ",
                               "jleague_official",
                               "https://data.j-league.or.jp/SFIX04/?player_id=19209")
    with pytest.raises(PlayerIdentityPrototypeError, match="namespace/profile"):
        link_exact_player_identities(
            [{"season": "2024", "team_id": "team_0002", "player_name_raw": "レオ　セアラ"}],
            [bad],
        )
