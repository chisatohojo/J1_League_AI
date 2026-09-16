"""Chronological, read-only Elo replay of ordinary J1 seasons 2015--2025."""

from hashlib import sha256
from pathlib import Path

import pandas as pd
import pytest

from src.collect.matches import MatchValidationError
from src.collect.teams import TeamAlias, TeamMaster, UnknownTeamError, load_team_master
from src.features.elo import EloRatings
from src.features.elo_history import EloHistoryError, build_elo_history, load_elo_history


ROOT = Path(__file__).resolve().parents[1]
YEARS = range(2015, 2026)
FEATURES = ["home_team_id", "away_team_id", "home_elo", "away_elo", "elo_diff"]
A, B, C, D = (f"team_{number:04d}" for number in range(1, 5))


@pytest.fixture
def master():
    aliases = [
        TeamAlias(team_id, f"Club {name}", name, "jleague_data_site", None, None, name)
        for team_id, name in zip((A, B, C, D), "ABCD")
    ]
    aliases.append(TeamAlias(A, "Club A", "Former A", "jleague_data_site", None, None, "A"))
    return TeamMaster(aliases)


def match(match_id="first", day="2015-03-07", home="A", away="B", result=2, **extra):
    season = int(day[:4])
    home_score, away_score = {0: (0, 1), 1: (1, 1), 2: (1, 0)}[result]
    return {
        "match_id": match_id, "season": season, "round": 1, "match_date": day,
        "home_team": home, "away_team": away, "stadium": "Test Stadium",
        "home_score": home_score, "away_score": away_score, "result": result,
        "competition": "Ｊ１ １ｓｔ" if season < 2017 else "Ｊ１",
        "stage": "1st" if season < 2017 else "full_season", **extra,
    }


def result_changed(frame, position, result):
    changed = frame.copy(deep=True)
    home_score, away_score = {0: (0, 1), 1: (1, 1), 2: (1, 0)}[result]
    changed.iloc[position, changed.columns.get_loc("result")] = result
    changed.iloc[position, changed.columns.get_loc("home_score")] = home_score
    changed.iloc[position, changed.columns.get_loc("away_score")] = away_score
    return changed


def test_first_match_uses_1500_and_final_ratings_are_separate(master):
    history = build_elo_history(pd.DataFrame([match()]), team_master=master)
    before = history.matches.iloc[0]

    assert (before.home_elo, before.away_elo, before.elo_diff) == (1500, 1500, 0)
    assert (before.home_team_id, before.away_team_id) == (A, B)
    assert history.final_ratings == {A: 1510.0, B: 1490.0, C: 1500.0, D: 1500.0}


def test_next_match_uses_only_prior_results_and_keeps_unplayed_clubs_at_1500(master):
    history = build_elo_history(pd.DataFrame([
        match(), match("second", "2015-03-14", "B", "C", 1),
    ]), team_master=master)

    second = history.matches.iloc[1]
    assert (second.home_elo, second.away_elo, second.elo_diff) == (1490, 1500, -10)
    assert history.matches.iloc[0].home_elo == 1500
    assert history.final_ratings[B] > second.home_elo
    assert history.final_ratings[C] < second.away_elo
    assert history.final_ratings[D] == 1500
    assert sum(history.final_ratings.values()) == pytest.approx(6000)


def test_current_and_future_results_cannot_change_earlier_pre_match_ratings(master):
    matches = pd.DataFrame([
        match(), match("second", "2015-03-14", "B", "C", 1),
        match("third", "2015-03-21", "A", "C", 2),
        match("fourth", "2015-03-28", "A", "B", 0),
    ])
    original = build_elo_history(matches, team_master=master)
    changed = build_elo_history(result_changed(matches, 2, 0), team_master=master)
    prefix = build_elo_history(matches.iloc[:2], team_master=master)

    pd.testing.assert_frame_equal(original.matches.loc[:2, FEATURES], changed.matches.loc[:2, FEATURES])
    pd.testing.assert_frame_equal(original.matches.loc[:1, FEATURES], prefix.matches[FEATURES])
    assert original.matches.iloc[3].home_elo != changed.matches.iloc[3].home_elo
    assert original.final_ratings != changed.final_ratings


def test_ratings_continue_across_seasons_and_aliases_use_the_same_id(master):
    history = build_elo_history(pd.DataFrame([
        match(day="2015-11-22", competition="Ｊ１ ２ｎｄ", stage="2nd"),
        match("next-year", "2016-02-27", "Former A", "C", 1),
    ]), team_master=master)

    next_year = history.matches.iloc[1]
    assert next_year.home_team == "Former A"
    assert next_year.home_team_id == A
    assert (next_year.home_elo, next_year.away_elo) == (1510, 1500)
    assert history.final_ratings[B] == 1490


def test_date_then_string_match_id_gives_deterministic_order(master):
    matches = pd.DataFrame([
        match("2", "2015-03-07", "A", "B", 2, kickoff_time="12:00"),
        match("10", "2015-03-07", "C", "D", 0, kickoff_time="20:00"),
        match("1", "2015-03-14", "A", "C", 1, kickoff_time="10:00"),
    ], index=[9, 3, 9])
    expected = build_elo_history(matches, team_master=master)
    shuffled = build_elo_history(matches.iloc[[2, 1, 0]], team_master=master)

    assert expected.matches.match_id.tolist() == ["10", "2", "1"]
    assert expected.matches.index.tolist() == [0, 1, 2]
    assert expected.matches.loc[:1, ["home_elo", "away_elo"]].eq(1500).all().all()
    pd.testing.assert_frame_equal(expected.matches, shuffled.matches)
    assert expected.final_ratings == shuffled.final_ratings


@pytest.mark.parametrize("home,away", [("A", "C"), ("C", "A"), ("Former A", "C")])
def test_same_day_second_appearance_is_rejected_by_resolved_identity(master, home, away):
    matches = pd.DataFrame([match(), match("second", home=home, away=away)])
    original = matches.copy(deep=True)
    with pytest.raises(EloHistoryError):
        build_elo_history(matches, team_master=master)
    pd.testing.assert_frame_equal(matches, original)


def test_two_aliases_of_one_club_cannot_play_each_other(master):
    with pytest.raises(EloHistoryError):
        build_elo_history(pd.DataFrame([match(home="Former A", away="A")]), team_master=master)


def test_unknown_team_is_an_explicit_error_without_implicit_registration(master):
    with pytest.raises(UnknownTeamError):
        build_elo_history(pd.DataFrame([match(away="Unregistered")]), team_master=master)
    assert master.team_count == 4


@pytest.mark.parametrize("column", FEATURES)
def test_existing_elo_output_columns_are_never_overwritten(master, column):
    matches = pd.DataFrame([match(**{column: "existing value"})])
    original = matches.copy(deep=True)
    with pytest.raises(EloHistoryError):
        build_elo_history(matches, team_master=master)
    pd.testing.assert_frame_equal(matches, original)


@pytest.mark.parametrize("changes", [
    {"season": 2014, "match_date": "2014-03-07"},
    {"season": 2026, "match_date": "2026-08-07", "competition": "Ｊ１", "stage": "full_season"},
    {"season": 20261, "match_date": "2026-03-07", "competition": "Ｊ１百年構想リーグ", "stage": "regional"},
    {"season": 2017, "match_date": "2017-03-07", "competition": "Ｊ１", "stage": "1st"},
    {"competition": "Ｊ１", "stage": "full_season"},
    {"competition": "Ｊ１ ２ｎｄ", "stage": "1st"},
    {"season": 2016},
])
def test_unsupported_season_competition_stage_or_calendar_mismatch_is_rejected(master, changes):
    with pytest.raises(EloHistoryError):
        build_elo_history(pd.DataFrame([match(**changes)]), team_master=master)


@pytest.mark.parametrize("column", ["competition", "stage"])
def test_competition_identity_is_required(master, column):
    with pytest.raises(EloHistoryError):
        build_elo_history(pd.DataFrame([match()]).drop(columns=column), team_master=master)


@pytest.mark.parametrize("invalid", [
    [match(), match(day="2015-03-14")],
    [match(home_score=-1)],
    [match(home_score=0, away_score=1)],
])
def test_existing_result_validation_is_applied_unchanged(master, invalid):
    with pytest.raises(MatchValidationError):
        build_elo_history(pd.DataFrame(invalid), team_master=master)


def test_input_dataframe_is_unchanged_and_original_metadata_is_preserved(master):
    matches = pd.DataFrame([
        match("later", "2015-03-14", "C", "A", source_url="https://example.invalid/later"),
        match(source_url="https://example.invalid/first"),
    ], index=[42, 42])
    original = matches.copy(deep=True)

    history = build_elo_history(matches, team_master=master)

    pd.testing.assert_frame_equal(matches, original)
    assert history.matches.columns.tolist() == matches.columns.tolist() + FEATURES
    assert history.matches.source_url.tolist() == ["https://example.invalid/first", "https://example.invalid/later"]
    history.matches.loc[0, "home_team"] = "Different display"
    pd.testing.assert_frame_equal(matches, original)


def test_2024_resumed_fixture_uses_recorded_november_date_without_august_backdating(master):
    # Real match 30700 resumed its second half on 2024-11-22 after an 8/24
    # suspension. Replay intentionally uses the existing processed date. Its
    # pre-match rating therefore includes intervening results; it does not
    # represent the rating at the original August kickoff.
    matches = pd.DataFrame([
        match("30700", "2024-11-22", "A", "B", 1, round=28),
        match("august", "2024-08-30", "A", "C", 2, round=29),
        match("october", "2024-10-01", "B", "D", 0, round=33),
    ])
    history = build_elo_history(matches, team_master=master)

    resumed = history.matches.iloc[-1]
    assert history.matches.match_id.tolist() == ["august", "october", "30700"]
    assert resumed.match_date == pd.Timestamp("2024-11-22")
    assert (resumed.home_elo, resumed.away_elo) == (1510, 1490)
    changed_intervening = build_elo_history(result_changed(matches, 1, 0), team_master=master)
    assert changed_intervening.matches.iloc[-1].home_elo == 1490


def write_season_files(directory):
    for year in YEARS:
        pd.DataFrame([match(str(year), f"{year}-03-07")]).to_csv(
            directory / f"{year}_matches_probe.csv", index=False, encoding="utf-8",
        )


def test_loader_reads_exactly_the_eleven_seasons_and_does_not_write_files(tmp_path, master):
    write_season_files(tmp_path)
    # Deliberately malformed, out-of-scope data must not be read or overwritten.
    (tmp_path / "2026_matches_probe.csv").write_bytes(b"not a match CSV")
    before = {path.name: path.read_bytes() for path in tmp_path.iterdir()}

    history = load_elo_history(tmp_path, team_master=master)

    assert history.matches.season.tolist() == list(YEARS)
    assert history.matches.match_id.tolist() == [str(year) for year in YEARS]
    assert history.matches.iloc[1].home_elo == 1510
    assert history.matches.iloc[-1].home_elo > 1510
    assert {path.name: path.read_bytes() for path in tmp_path.iterdir()} == before


def test_loader_rejects_missing_season_instead_of_silently_replaying_a_partial_history(tmp_path, master):
    write_season_files(tmp_path)
    (tmp_path / "2020_matches_probe.csv").unlink()
    with pytest.raises(FileNotFoundError):
        load_elo_history(tmp_path, team_master=master)


def test_loader_rejects_a_season_stored_under_the_wrong_year(tmp_path, master):
    write_season_files(tmp_path)
    pd.DataFrame([match("wrong-year", "2020-03-14")]).to_csv(
        tmp_path / "2019_matches_probe.csv", index=False, encoding="utf-8",
    )
    with pytest.raises(EloHistoryError):
        load_elo_history(tmp_path, team_master=master)


def test_cached_2015_through_2025_replay_is_complete_reproducible_and_read_only():
    directory = ROOT / "data/processed/jleague"
    paths = [directory / f"{year}_matches_probe.csv" for year in YEARS]
    missing = [path.name for path in paths if not path.exists()]
    if missing:
        pytest.skip(f"Optional historical CSV cache unavailable: {', '.join(missing)}")
    original_hashes = {path: sha256(path.read_bytes()).hexdigest() for path in paths}
    source = pd.concat([pd.read_csv(path, dtype={"match_id": str}) for path in paths], ignore_index=True)
    master = load_team_master()

    first = load_elo_history(directory, team_master=master)
    second = load_elo_history(directory, team_master=master)

    assert len(first.matches) == first.matches.match_id.nunique() == 3588
    assert set(first.matches.match_id) == set(source.match_id)
    assert first.matches.groupby("season").size().to_dict() == {
        year: 380 if year in (2021, 2024, 2025) else 306 for year in YEARS
    }
    played = set(first.matches.home_team_id) | set(first.matches.away_team_id)
    registered = {alias.team_id for alias in master.aliases}
    assert len(played) == 31
    assert len(registered) == len(first.final_ratings) == 33
    assert set(first.final_ratings) == registered
    assert all(first.final_ratings[team_id] == 1500 for team_id in registered - played)
    assert first.matches.home_team_id.notna().all() and first.matches.away_team_id.notna().all()
    pd.testing.assert_frame_equal(first.matches, second.matches)
    assert first.final_ratings == second.final_ratings
    assert first.matches.match_date.min() == pd.Timestamp("2015-03-07")
    assert first.matches.match_date.max() == pd.Timestamp("2025-12-06")
    first_day = first.matches.loc[first.matches.match_date == first.matches.match_date.min()]
    assert first_day[["home_elo", "away_elo"]].eq(1500).all().all()
    assert first.matches.loc[first.matches.match_id == "30700", "match_date"].item() == pd.Timestamp("2024-11-22")

    # Independently walk every input row through the existing public API. This
    # confirms that every stored feature is the pre-update value, and that the
    # final 2025 result is included in final_ratings exactly once.
    ratings = EloRatings(sorted(registered))
    for row in first.matches.itertuples(index=False):
        before = ratings.pre_match(row.home_team_id, row.away_team_id)
        assert (row.home_elo, row.away_elo) == (before.home_rating, before.away_rating)
        assert row.elo_diff == before.home_rating - before.away_rating
        assert master.resolve_team_id(row.home_team, on=row.match_date) == row.home_team_id
        assert master.resolve_team_id(row.away_team, on=row.match_date) == row.away_team_id
        ratings.update(row.home_team_id, row.away_team_id, row.result)
    assert first.final_ratings == ratings.ratings
    assert sum(first.final_ratings.values()) == pytest.approx(33 * 1500)
    assert {path: sha256(path.read_bytes()).hexdigest() for path in paths} == original_hashes
