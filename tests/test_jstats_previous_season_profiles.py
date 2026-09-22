import json
from datetime import date
from pathlib import Path
import shutil

import pytest

from src.collect.jstats_previous_season_profiles import (
    PROFILE_STATS,
    ProfileStat,
    SnapshotError,
    expected_teams,
    parse_profile_page,
)
from src.collect.teams import TeamAlias, TeamMaster


def _master():
    return TeamMaster([
        TeamAlias("team_0001", "Alpha", "A-data", "jleague_data_site", None, None, "a"),
        TeamAlias("team_0001", "Alpha", "Alpha", "jleague_official", None, None, "a"),
        TeamAlias("team_0002", "Beta", "B-data", "jleague_data_site", None, None, "b"),
        TeamAlias("team_0002", "Beta", "Beta", "jleague_official", None, None, "b"),
    ])


def _page(rows, *, season=2019, stat="expected_goals"):
    ranking = {"id": f"ranking-{stat}", "category": "j1", "year": str(season),
               "stats": {"value": stat, "label": "x"}, "data": rows}
    payload = json.dumps({"rankingList": [ranking]}, ensure_ascii=False, separators=(",", ":"))
    push = json.dumps(["x", payload], ensure_ascii=False)
    return (f"<script>self.__next_f.push({push})</script>").encode()


def _rows(*, missing_code=False):
    return [
        {"club": {"code": "" if missing_code else "a", "name": "Alpha"},
         **({} if missing_code else {"href": "/club/a"}), "score": 1.2},
        {"club": {"code": "b", "name": "Beta"}, "href": "/club/b", "score": 2.3},
    ]


def test_denominator_uses_jleague_data_site_namespace():
    class Recording:
        def __init__(self, inner):
            self.inner = inner
            self.sources = []

        def resolve_team_id(self, name, *, source, on):
            self.sources.append(source)
            return self.inner.resolve_team_id(name, source=source, on=on)

    recorder = Recording(__import__("src.collect.teams", fromlist=["load_team_master"]).load_team_master())
    result = expected_teams(2018, master=recorder)
    assert len(result) == 18
    assert set(recorder.sources) == {"jleague_data_site"}


def test_profile_rows_use_jleague_official_namespace_and_name_fallback():
    class Recording:
        def __init__(self, inner):
            self.inner = inner
            self.sources = []

        def resolve_team_id(self, name, *, source, on):
            self.sources.append(source)
            return self.inner.resolve_team_id(name, source=source, on=on)

    recorder = Recording(_master())
    stat = next(s for s in PROFILE_STATS if s.slug == "expected_goals")
    expected = {"A-data": ("team_0001", 1), "B-data": ("team_0002", 1)}
    rows, _ = parse_profile_page(_page(_rows(missing_code=True)), season=2019, stat=stat,
                                 expected=expected, master=recorder)
    assert [row["team_id"] for row in rows] == ["team_0001", "team_0002"]
    assert rows[0]["official_club_id"] is None
    assert rows[0]["official_club_code"] is None
    assert rows[0]["official_club_href"] is None
    assert set(recorder.sources) == {"jleague_official"}


def test_unresolved_profile_is_hard_failure():
    stat = next(s for s in PROFILE_STATS if s.slug == "expected_goals")
    with pytest.raises(SnapshotError):
        parse_profile_page(_page(_rows()), season=2019, stat=stat,
                           expected={"A-data": ("team_0001", 1), "B-data": ("team_0002", 1)},
                           master=TeamMaster([TeamAlias("team_0001", "Alpha", "Alpha", "jleague_official", None, None, "a")]))


def test_duplicate_profile_team_is_rejected():
    stat = next(s for s in PROFILE_STATS if s.slug == "expected_goals")
    duplicate = _rows()
    duplicate[1] = {"club": {"code": "a", "name": "Alpha"}, "href": "/club/a", "score": 2.3}
    with pytest.raises(SnapshotError):
        parse_profile_page(_page(duplicate), season=2019, stat=stat,
                           expected={"A-data": ("team_0001", 1), "B-data": ("team_0002", 1)},
                           master=_master())


def test_2018_xg_absence_is_expected():
    assert next(s for s in PROFILE_STATS if s.slug == "expected_goals").available_from == 2019
    assert next(s for s in PROFILE_STATS if s.slug == "expected_goals_against").available_from == 2019


def test_profile_parse_is_deterministic():
    stat = next(s for s in PROFILE_STATS if s.slug == "expected_goals")
    expected = {"A-data": ("team_0001", 1), "B-data": ("team_0002", 1)}
    first = parse_profile_page(_page(_rows()), season=2019, stat=stat, expected=expected, master=_master())
    second = parse_profile_page(_page(_rows()), season=2019, stat=stat, expected=expected, master=_master())
    assert first == second


def test_rebuild_from_raw_does_not_fetch_http(tmp_path, monkeypatch):
    from src.collect import jstats_previous_season_profiles as module

    def fail_fetch(*args, **kwargs):
        raise AssertionError("raw-only rebuild must not fetch HTTP")

    monkeypatch.setattr(module, "urlopen", fail_fetch)
    raw_copy = Path(tmp_path) / "raw"
    shutil.copytree("data/raw/jstats_previous_season_profiles/20260923T010000000000Z",
                    raw_copy / "20260923T010000000000Z")
    result = module.rebuild_from_raw(
        retrieval_id="20260923T010000000000Z",
        raw_root=raw_copy,
        processed_root=Path(tmp_path),
    )
    assert result["request_count"] == 0
    assert result["row_count"] == 864
    assert result["identity_diagnostics"]["name_exact_resolution_count"] == 864


def test_explicit_mapping_is_not_arithmetic():
    # The materializer only stores profile seasons; target linkage is governed
    # by the explicit mapping in the feature specification document.
    assert [s.available_from for s in PROFILE_STATS if s.slug.startswith("expected_goals")] == [2019, 2019]
