"""Offline contracts for the bounded player snapshot feasibility parser."""

from dataclasses import replace
from datetime import date
import json
from pathlib import Path

import pytest

from src.collect.jstats_player_snapshot_prototype import (
    OfficialProfileIdentity,
    PlayerSnapshotPrototypeError,
    STATS,
    classify_player_identity_states,
    discover_player_stat_options,
    parse_official_profile_identity,
    parse_player_page,
    verify_embedded_player_identity,
)
from src.collect.teams import TeamAlias, TeamMaster


MASTER = TeamMaster([
    TeamAlias("team_0001", "Alpha", "Alpha", "jleague_official", None, None, "alpha"),
    TeamAlias("team_0002", "Beta", "Beta", "jleague_official", None, None, "beta"),
])


def fixture(*, slug="time", bad_id=False, bad_club=False, missing_href=False,
            visible_score=None):
    stat = STATS[slug]
    rows = []
    for index in range(12):
        club = "alpha" if index % 2 == 0 else "beta"
        club_name = club.title()
        player_id = str(1000 + index)
        rows.append({
            "href": None if missing_href and index == 11 else f"/player/{player_id}/",
            "club": {"code": "outside" if bad_club and index == 0 else club,
                     "name": club_name, "fullName": club_name},
            "position": ("GK" if index == 0 else "MF") + f" {index + 1}",
            "playerName": f"Player {index}",
            "name": f"Player {index}",
            "score": 720 - index,
            "legacyPlayerPhotoLookup": {
                "playerId": "9999" if bad_id and index == 0 else player_id,
            },
        })
    ranking = {
        "id": f"ranking-{slug}", "category": "j1", "year": "2026",
        "stats": {"value": slug, "label": stat.label},
        "data": rows, "loadMore": {"max": len(rows), "end": 10, "step": 10},
    }
    filters = [{"id": "stats", "label": "スタッツ", "groups": [
        {"id": "stats-physical", "options": [
            {"value": "time", "label": "出場時間"},
            {"value": "distance", "label": "総走行距離"},
        ]},
    ]}]
    payload = "8:" + json.dumps(
        {"filterList": filters, "rankingList": [ranking]}, ensure_ascii=False,
    )
    script = json.dumps([1, payload], ensure_ascii=False)
    visible = "".join(
        f'<a class="m-ranking-player-list-item__link" href="{row["href"]}">'
        f'<div class="m-ranking-player-list-item" name="{row["name"]}" '
        f'score="{visible_score if visible_score is not None and index == 0 else row["score"]}"></div></a>'
        for index, row in enumerate(rows[:10])
    )
    return (
        f"<html><head><title>2026/27 Ｊ１</title></head><body>2026/9/21 更新{visible}"
        f"<script>self.__next_f.push({script})</script></body></html>"
    ).encode()


def parse(raw):
    return parse_player_page(
        raw, stat=STATS["time"], expected_slugs={"alpha", "beta"}, master=MASTER,
        observed_date=date(2026, 9, 30),
    )


def profile_fixture(*, player_id="1011", name="Player 11", club="beta",
                    club_name="Beta", include_name=True, include_club=True):
    heading = f"<h1>{name}</h1>" if include_name else ""
    club_link = f'<a href="/club/{club}/">{club_name}</a>' if include_club else ""
    return (
        f'<html><head><link rel="canonical" '
        f'href="https://www.jleague.jp/player/{player_id}/"></head>'
        f'<body><main class="p-player-profile">{heading}{club_link}</main></body></html>'
    ).encode()


def test_extracts_complete_embedded_rows_stable_ids_clubs_and_visible_contract():
    result = parse(fixture())
    assert result.row_count == result.embedded_rows == result.load_more_max == 12
    assert result.visible_rows == 10
    assert result.unique_player_ids == result.player_id_coverage == 12
    assert result.numeric_candidate_coverage == 12
    assert result.unresolved_identity_rows == 0
    assert result.unique_clubs == 2
    assert result.position_distribution == {"GK": 1, "MF": 11}
    assert result.source_updated_date_jst == "2026-09-21"
    assert {row.identity_status for row in result.rows} == {
        "EXACT_OFFICIAL_PROFILE_ID_AND_CLUB"
    }


def test_discovers_minutes_and_distance_from_official_filter_options():
    options = discover_player_stat_options(fixture())
    assert options["time"] == "出場時間"
    assert options["distance"] == "総走行距離"


def test_missing_direct_profile_link_is_explicitly_unresolved_not_inferred_exact():
    result = parse(fixture(missing_href=True))
    assert result.player_id_coverage == 11
    assert result.numeric_candidate_coverage == 12
    assert result.unresolved_identity_rows == 1
    assert result.rows[-1].player_id is None
    assert result.rows[-1].player_id_candidate == "1011"
    assert result.rows[-1].player_id_candidate_source == "LEGACY_PLAYER_PHOTO_LOOKUP"
    assert result.rows[-1].player_profile_url == ""
    assert result.rows[-1].identity_status == "UNRESOLVED_NO_DIRECT_PROFILE_LINK"


def test_verified_embedded_id_acceptance_preserves_source_kind_and_raw_names():
    profile = parse_official_profile_identity(profile_fixture(), expected_player_id="1011")
    decision = verify_embedded_player_identity(
        candidate_player_id="1011",
        ranking_player_name_raw="Player 11",
        ranking_club_slug="beta",
        profile=profile,
    )
    assert decision.player_id == "1011"
    assert decision.identity_source == "VERIFIED_EMBEDDED_PLAYER_ID"
    assert decision.name_exact_match is True


def test_profile_name_difference_is_retained_without_name_normalization():
    profile = parse_official_profile_identity(
        profile_fixture(name="Official Display"), expected_player_id="1011",
    )
    decision = verify_embedded_player_identity(
        candidate_player_id="1011",
        ranking_player_name_raw="Ranking Display",
        ranking_club_slug="beta",
        profile=profile,
    )
    assert decision.ranking_player_name_raw == "Ranking Display"
    assert decision.profile_player_name_raw == "Official Display"
    assert decision.name_exact_match is False


def test_wrong_profile_id_is_rejected():
    with pytest.raises(PlayerSnapshotPrototypeError, match="canonical ID"):
        parse_official_profile_identity(profile_fixture(player_id="9999"), expected_player_id="1011")


@pytest.mark.parametrize("changes", [{"include_name": False}, {"include_club": False}])
def test_missing_profile_identity_field_is_rejected(changes):
    with pytest.raises(PlayerSnapshotPrototypeError, match="lacks one player name and club"):
        parse_official_profile_identity(profile_fixture(**changes), expected_player_id="1011")


def test_conflicting_profile_club_is_rejected():
    profile = parse_official_profile_identity(
        profile_fixture(club="alpha", club_name="Alpha"), expected_player_id="1011",
    )
    with pytest.raises(PlayerSnapshotPrototypeError, match="club identities conflict"):
        verify_embedded_player_identity(
            candidate_player_id="1011",
            ranking_player_name_raw="Player 11",
            ranking_club_slug="beta",
            profile=profile,
        )


def test_conflicting_player_identity_and_multi_club_state_fail_closed():
    row = parse(fixture()).rows[0]
    name_conflict = replace(row, player_name_raw="Different Person")
    club_conflict = replace(row, official_club_slug="beta")
    assert classify_player_identity_states((row, name_conflict))[row.player_id_candidate] == (
        "CONFLICTING_PLAYER_IDENTITY"
    )
    assert classify_player_identity_states((row, club_conflict))[row.player_id_candidate] == (
        "AMBIGUOUS_MULTI_CLUB_PLAYER_STATE"
    )


def test_name_only_fallback_is_forbidden():
    profile = OfficialProfileIdentity(
        player_id="1011", player_name_raw="Player 11", official_club_slug="beta",
        official_club_name="Beta", profile_url="https://www.jleague.jp/player/1011/",
    )
    with pytest.raises(PlayerSnapshotPrototypeError, match="Name-only"):
        verify_embedded_player_identity(
            candidate_player_id=None,
            ranking_player_name_raw="Player 11",
            ranking_club_slug="beta",
            profile=profile,
        )


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"bad_id": True}, "conflicting player ID"),
        ({"bad_club": True}, "outside current J1"),
        ({"visible_score": 999}, "Visible and embedded"),
    ],
)
def test_identity_club_and_visible_mismatches_fail_closed(changes, message):
    with pytest.raises(PlayerSnapshotPrototypeError, match=message):
        parse(fixture(**changes))


def test_prototype_has_no_network_model_or_production_output_dependency():
    source = Path(__file__).parents[1].joinpath(
        "src/collect/jstats_player_snapshot_prototype.py"
    ).read_text(encoding="utf-8")
    assert "urlopen" not in source
    assert "requests" not in source
    assert "src.modeling" not in source
    assert "processed_root" not in source.lower()
