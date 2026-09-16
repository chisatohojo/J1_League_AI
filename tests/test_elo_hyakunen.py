"""Continue the ordinary J1 history using only each special match's 90 minutes."""

from copy import deepcopy
from hashlib import sha256
from pathlib import Path

import pandas as pd
import pytest

from src.collect.jleague_hyakunen import (
    HyakunenValidationError, build_playoff_ties, normalize_matches,
)
from src.collect.teams import TeamAlias, TeamMaster, UnknownTeamError, load_team_master
from src.features.elo import EloRatings, expected_score
from src.features.elo_history import (
    EloHistoryError, build_elo_history, build_elo_history_with_hyakunen,
    load_elo_history, load_elo_history_with_hyakunen,
)
from tests.test_jleague_hyakunen import synthetic_sources


ROOT = Path(__file__).resolve().parents[1]
FEATURES = ["home_team_id", "away_team_id", "home_elo", "away_elo", "elo_diff"]
CLUBS = [f"{group}{number:02d}" for group in ("EAST", "WEST") for number in range(10)]
UNPLAYED = "team_0021"


def ordinary_match(season, match_id=None):
    return {
        "match_id": match_id or f"ordinary-{season}", "season": season, "round": 1,
        "match_date": f"{season}-03-07", "home_team": "EAST00", "away_team": "WEST00",
        "stadium": "Test stadium", "home_score": 1, "away_score": 0, "result": 2,
        "competition": "Ｊ１ １ｓｔ" if season < 2017 else "Ｊ１",
        "stage": "1st" if season < 2017 else "full_season",
    }


@pytest.fixture
def master():
    return TeamMaster([
        TeamAlias(f"team_{number:04d}", club, club, "jleague_data_site", None, None, "")
        for number, club in enumerate([*CLUBS, "UNPLAYED"], 1)
    ])


@pytest.fixture
def ordinary():
    return pd.DataFrame([ordinary_match(2015), ordinary_match(2025)])


@pytest.fixture
def special():
    return normalize_matches(*synthetic_sources())


def replay(ordinary, special, master):
    return build_elo_history_with_hyakunen(ordinary, special, team_master=master)


def assert_same_elo(left, right):
    pd.testing.assert_frame_equal(left.historical.matches, right.historical.matches)
    assert left.historical.final_ratings == right.historical.final_ratings
    pd.testing.assert_frame_equal(left.hyakunen.matches[FEATURES], right.hyakunen.matches[FEATURES])
    assert left.hyakunen.final_ratings == right.hyakunen.final_ratings


def test_2025_final_ratings_are_carried_into_every_first_day_match(ordinary, special, master):
    history = replay(ordinary, special, master)
    previous = build_elo_history(ordinary, team_master=master)
    pd.testing.assert_frame_equal(history.historical.matches, previous.matches)
    assert history.historical.final_ratings == previous.final_ratings
    first_day = history.hyakunen.matches.loc[
        history.hyakunen.matches.match_date.eq(history.hyakunen.matches.match_date.min())
    ]
    assert len(first_day) == 10
    for row in first_day.itertuples(index=False):
        assert row.home_elo == previous.final_ratings[row.home_team_id]
        assert row.away_elo == previous.final_ratings[row.away_team_id]
    assert previous.final_ratings[master.resolve_team_id("EAST00")] > 1500


def test_registered_new_entrants_start_at_1500_and_unused_ids_stay_at_1500(ordinary, special, master):
    history = replay(ordinary, special, master)
    old_ids = set(history.historical.matches.home_team_id) | set(history.historical.matches.away_team_id)
    appearances = pd.concat([
        history.hyakunen.matches[["match_date", f"{side}_team_id", f"{side}_elo"]].rename(
            columns={f"{side}_team_id": "team_id", f"{side}_elo": "rating"},
        ) for side in ("home", "away")
    ]).sort_values("match_date").drop_duplicates("team_id")
    new = appearances.loc[~appearances.team_id.isin(old_ids)]
    assert len(new) == 18
    assert new.rating.eq(1500).all()
    assert history.historical.final_ratings[UNPLAYED] == 1500
    assert history.hyakunen.final_ratings[UNPLAYED] == 1500


def test_all_200_pre_match_values_and_final_updates_follow_the_existing_api(ordinary, special, master):
    history = replay(ordinary, special, master)
    ratings = EloRatings(sorted(history.historical.final_ratings))
    for frame in (history.historical.matches, history.hyakunen.matches):
        for row in frame.itertuples(index=False):
            before = ratings.pre_match(row.home_team_id, row.away_team_id)
            assert (row.home_elo, row.away_elo) == (before.home_rating, before.away_rating)
            assert row.elo_diff == before.home_rating - before.away_rating
            ratings.update(row.home_team_id, row.away_team_id, row.result)
    assert len(history.hyakunen.matches) == history.hyakunen.matches.match_id.nunique() == 200
    assert set(history.hyakunen.matches.match_id) == set(special.match_id)
    assert history.hyakunen.final_ratings == ratings.ratings
    assert sum(history.hyakunen.final_ratings.values()) == pytest.approx(master.team_count * 1500)


def test_regional_pk_winner_changes_do_not_change_any_elo_value(ordinary, master):
    original_sources = synthetic_sources()
    altered_sources = deepcopy(original_sources)
    record = altered_sources[0][0]
    record["home_pk_score"], record["away_pk_score"] = 13, 14
    record["raw_score_text"] = "2-2(PK13-14)"
    original = replay(ordinary, normalize_matches(*original_sources), master)
    altered = replay(ordinary, normalize_matches(*altered_sources), master)
    before = original.hyakunen.matches.set_index("match_id").loc[record["match_id"]]
    after = altered.hyakunen.matches.set_index("match_id").loc[record["match_id"]]
    assert before.result == after.result == 1
    assert before.pk_winner_team != after.pk_winner_team
    assert before.home_points != after.home_points
    assert_same_elo(original, altered)


def test_extra_time_winner_changes_do_not_replace_the_90_minute_draw(ordinary, master):
    original_sources = synthetic_sources()
    altered_sources = deepcopy(original_sources)
    record = next(r for r in altered_sources[0] if r["placement_range"] == "3-4" and r["leg"] == 2)
    record["displayed_home_score"], record["displayed_away_score"] = 1, 2
    record["raw_score_text"] = "1-2"
    detail = altered_sources[1][record["match_id"]]
    detail.update(home_extra_time_score=1, away_extra_time_score=2,
                  displayed_home_score=1, displayed_away_score=2)
    original = replay(ordinary, normalize_matches(*original_sources), master)
    altered = replay(ordinary, normalize_matches(*altered_sources), master)
    before = original.hyakunen.matches.set_index("match_id").loc[record["match_id"]]
    after = altered.hyakunen.matches.set_index("match_id").loc[record["match_id"]]
    assert before.result == after.result == 1
    assert before.match_winner_team != after.match_winner_team
    assert_same_elo(original, altered)


@pytest.mark.parametrize("placement", ["5-6", "7-8"])
def test_playoff_tie_pk_winner_is_separate_from_the_single_match_result(ordinary, master, placement):
    original_sources = synthetic_sources()
    altered_sources = deepcopy(original_sources)
    record = next(r for r in altered_sources[0] if r["placement_range"] == placement and r["leg"] == 2)
    record["home_pk_score"], record["away_pk_score"] = 5, 4
    score = f"{record['displayed_home_score']}-{record['displayed_away_score']}"
    record["raw_score_text"] = score + "(PK5-4)"
    altered_sources[1][record["match_id"]].update(home_pk_score=5, away_pk_score=4)
    original_frame, altered_frame = normalize_matches(*original_sources), normalize_matches(*altered_sources)
    original_tie = build_playoff_ties(original_frame).set_index("placement_range").loc[placement]
    altered_tie = build_playoff_ties(altered_frame).set_index("placement_range").loc[placement]
    assert original_tie.tie_winner_team != altered_tie.tie_winner_team
    assert_same_elo(replay(ordinary, original_frame, master), replay(ordinary, altered_frame, master))


def test_optional_tie_winner_metadata_is_never_used_as_an_elo_outcome(ordinary, special, master):
    first = special.assign(tie_winner_team="EAST00", tie_decision="penalties")
    second = special.assign(tie_winner_team="WEST00", tie_decision="extra_time")
    assert_same_elo(replay(ordinary, first, master), replay(ordinary, second, master))


def test_current_and_future_result_changes_cannot_rewrite_earlier_ratings(ordinary, master):
    sources = synthetic_sources()
    altered = deepcopy(sources)
    changed = next(r for r in altered[0] if r["group"] == "EAST" and r["round"] == 17)
    changed.update(displayed_home_score=0, displayed_away_score=1, raw_score_text="0-1")
    original = replay(ordinary, normalize_matches(*sources), master)
    modified = replay(ordinary, normalize_matches(*altered), master)
    pd.testing.assert_frame_equal(original.historical.matches, modified.historical.matches)
    assert original.historical.final_ratings == modified.historical.final_ratings
    position = original.hyakunen.matches.index[original.hyakunen.matches.match_id.eq(changed["match_id"])][0]
    pd.testing.assert_frame_equal(original.hyakunen.matches.loc[:position, FEATURES],
                                  modified.hyakunen.matches.loc[:position, FEATURES])
    assert not original.hyakunen.matches.loc[position + 1:, FEATURES].equals(
        modified.hyakunen.matches.loc[position + 1:, FEATURES],
    )
    assert original.hyakunen.final_ratings != modified.hyakunen.final_ratings


def test_shuffled_input_replays_in_date_then_lexical_match_id_order(ordinary, special, master):
    first = replay(ordinary, special, master)
    second = replay(ordinary.sample(frac=1, random_state=42), special.sample(frac=1, random_state=42), master)
    pd.testing.assert_frame_equal(first.hyakunen.matches, second.hyakunen.matches)
    assert_same_elo(first, second)
    expected = special.sort_values(["match_date", "match_id"], kind="stable").match_id.tolist()
    assert first.hyakunen.matches.match_id.tolist() == expected
    assert first.hyakunen.matches.index.tolist() == list(range(200))


def test_both_inputs_and_all_source_columns_are_preserved(ordinary, special, master):
    before_ordinary, before_special = ordinary.copy(deep=True), special.copy(deep=True)
    history = replay(ordinary, special, master)
    pd.testing.assert_frame_equal(ordinary, before_ordinary)
    pd.testing.assert_frame_equal(special, before_special)
    expected = special.sort_values(["match_date", "match_id"], kind="stable").reset_index(drop=True)
    pd.testing.assert_frame_equal(history.hyakunen.matches[special.columns], expected)
    assert history.hyakunen.matches.columns.tolist() == special.columns.tolist() + FEATURES
    history.hyakunen.matches.loc[0, "home_team"] = "Mutated output"
    pd.testing.assert_frame_equal(special, before_special)


def test_2025_and_special_final_snapshots_are_detached(ordinary, special, master):
    history = replay(ordinary, special, master)
    previous = history.historical.final_ratings.copy()
    team_id = master.resolve_team_id("EAST00")
    history.hyakunen.final_ratings[team_id] = -999
    assert history.historical.final_ratings == previous
    fresh = replay(ordinary, special, master)
    assert fresh.hyakunen.final_ratings[team_id] != -999


def test_match_id_cannot_be_reused_across_competitions(ordinary, special, master):
    ordinary.loc[0, "match_id"] = special.iloc[0].match_id
    with pytest.raises(EloHistoryError):
        replay(ordinary, special, master)


def test_unknown_special_club_is_not_implicitly_registered(ordinary, special, master):
    incomplete_master = TeamMaster([alias for alias in master.aliases if alias.source_name != "EAST09"])
    with pytest.raises(UnknownTeamError):
        replay(ordinary, special, incomplete_master)
    assert incomplete_master.team_count == 20


def test_same_team_id_cannot_appear_twice_on_a_special_match_date(ordinary, special, master):
    # The source has 20 different strings, but two resolve to one club identity.
    same_club = TeamMaster([
        TeamAlias("team_0001", "EAST00", alias.source_name, alias.source, None, None, "")
        if alias.source_name == "EAST01" else alias for alias in master.aliases
    ])
    with pytest.raises(EloHistoryError):
        replay(ordinary, special, same_club)


@pytest.mark.parametrize("column", FEATURES)
def test_existing_special_feature_columns_are_rejected_without_overwriting(ordinary, special, master, column):
    special[column] = "existing"
    original = special.copy(deep=True)
    with pytest.raises(EloHistoryError):
        replay(ordinary, special, master)
    pd.testing.assert_frame_equal(special, original)


def test_partial_special_competition_cannot_silently_replace_the_200_matches(ordinary, special, master):
    with pytest.raises(HyakunenValidationError):
        replay(ordinary, special.iloc[:-1], master)


def test_result_inconsistent_with_90_minute_score_is_rejected(ordinary, special, master):
    special.loc[0, "result"] = 2
    with pytest.raises(HyakunenValidationError):
        replay(ordinary, special, master)


def write_inputs(directory, special):
    for year in range(2015, 2026):
        pd.DataFrame([ordinary_match(year)]).to_csv(directory / f"{year}_matches_probe.csv", index=False)
    special_dir = directory / "2026_hyakunen"
    special_dir.mkdir()
    special.to_csv(special_dir / "matches.csv", index=False)
    # Unrelated files deliberately cannot be parsed as match data.
    (special_dir / "playoff_ties.csv").write_bytes(b"must never be loaded")
    ongoing = directory / "2026_27"
    ongoing.mkdir()
    (ongoing / "completed_matches.csv").write_bytes(b"out of scope")


def file_hashes(directory):
    return {p.relative_to(directory): sha256(p.read_bytes()).hexdigest()
            for p in directory.rglob("*") if p.is_file()}


def test_loader_reads_only_eleven_seasons_and_special_matches_without_writes(tmp_path, special, master):
    write_inputs(tmp_path, special)
    before = file_hashes(tmp_path)
    first = load_elo_history_with_hyakunen(tmp_path, team_master=master)
    second = load_elo_history_with_hyakunen(tmp_path, team_master=master)
    assert first.historical.matches.season.tolist() == list(range(2015, 2026))
    assert len(first.hyakunen.matches) == 200
    assert first.hyakunen.matches.match_id.str.startswith("0").all()
    assert first.hyakunen.matches["round"].isna().sum() == 20
    assert first.hyakunen.matches.extra_time_played.dtype == bool
    assert first.hyakunen.matches.match_date.dtype == "datetime64[ns]"
    pd.testing.assert_frame_equal(first.hyakunen.matches, second.hyakunen.matches)
    assert_same_elo(first, second)
    assert file_hashes(tmp_path) == before


@pytest.mark.parametrize("missing", ["2020_matches_probe.csv", "2026_hyakunen/matches.csv"])
def test_loader_requires_all_inputs_instead_of_silently_omitting_a_season(tmp_path, special, master, missing):
    write_inputs(tmp_path, special)
    (tmp_path / missing).unlink()
    with pytest.raises(FileNotFoundError):
        load_elo_history_with_hyakunen(tmp_path, team_master=master)


def test_cached_3788_matches_keep_the_old_history_and_use_real_90_minute_results():
    directory = ROOT / "data/processed/jleague"
    paths = [directory / f"{year}_matches_probe.csv" for year in range(2015, 2026)]
    paths.append(directory / "2026_hyakunen/matches.csv")
    if not all(path.is_file() for path in paths):
        pytest.skip("Locally acquired CSVs are not distributed with the repository")
    before = {path: sha256(path.read_bytes()).hexdigest() for path in paths}
    master = load_team_master()
    old = load_elo_history(directory, team_master=master)
    first = load_elo_history_with_hyakunen(directory, team_master=master)
    second = load_elo_history_with_hyakunen(directory, team_master=master)
    pd.testing.assert_frame_equal(first.historical.matches, old.matches)
    assert first.historical.final_ratings == old.final_ratings
    pd.testing.assert_frame_equal(first.hyakunen.matches, second.hyakunen.matches)
    assert_same_elo(first, second)
    frames = [first.historical.matches, first.hyakunen.matches]
    all_matches = pd.concat(frames, ignore_index=True)
    assert len(all_matches) == all_matches.match_id.nunique() == 3788
    assert len(first.hyakunen.matches) == 200
    assert set(first.hyakunen.matches.stage) == {"regional", "playoff"}
    assert first.hyakunen.matches.stage.value_counts().to_dict() == {"regional": 180, "playoff": 20}
    used_ids = set(all_matches.home_team_id) | set(all_matches.away_team_id)
    assert len(used_ids) == master.team_count == 33
    ratings = EloRatings(sorted(first.historical.final_ratings))
    for row in all_matches.itertuples(index=False):
        snapshot = ratings.pre_match(row.home_team_id, row.away_team_id)
        assert (row.home_elo, row.away_elo) == (snapshot.home_rating, snapshot.away_rating)
        assert row.elo_diff == snapshot.home_rating - snapshot.away_rating
        assert row.home_team_id == master.resolve_team_id(row.home_team, on=row.match_date)
        assert row.away_team_id == master.resolve_team_id(row.away_team, on=row.match_date)
        update = ratings.update(row.home_team_id, row.away_team_id, row.result)
        if row.match_id in ("32933", "33017"):
            assert row.result == 1
            draw_delta = 20 * (0.5 - expected_score(row.home_elo, row.away_elo))
            assert update.after.home_rating == pytest.approx(row.home_elo + draw_delta)
    assert first.hyakunen.final_ratings == ratings.ratings
    pk = first.hyakunen.matches.set_index("match_id").loc["32933"]
    assert pk.pk_played and pk.result == 1 and pk.pk_winner_team == pk.away_team
    extra = first.hyakunen.matches.set_index("match_id").loc["33017"]
    assert (extra.home_team, extra.away_team) == ("町田", "名古屋")
    assert (extra.home_score, extra.away_score, extra.result) == (0, 0, 1)
    assert extra.extra_time_played and extra.match_winner_team == extra.home_team
    playoff = first.hyakunen.matches.set_index("match_id").loc["33015"]
    tie = build_playoff_ties(first.hyakunen.matches).set_index("playoff_tie_id").loc[playoff.playoff_tie_id]
    assert (playoff.home_score, playoff.away_score, playoff.result) == (2, 0, 2)
    assert playoff.match_winner_team != tie.tie_winner_team
    assert sum(first.hyakunen.final_ratings.values()) == pytest.approx(33 * 1500)
    assert {path: sha256(path.read_bytes()).hexdigest() for path in paths} == before
