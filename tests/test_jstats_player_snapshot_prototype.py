"""Offline contracts for the bounded player snapshot feasibility parser."""

from datetime import date
import json
from pathlib import Path

import pytest

from src.collect.jstats_player_snapshot_prototype import (
    PlayerSnapshotPrototypeError,
    STATS,
    discover_player_stat_options,
    parse_player_page,
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
