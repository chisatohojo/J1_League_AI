"""Local identity, date-batched pre-match workload tests (no model fit)."""

import pandas as pd
import pytest

from src.features.player_workload import WorkloadError, build_player_workload_features


def _fixture():
    matches = pd.DataFrame([
        ("1", "2020-01-01", "2020", "A", "B"),
        ("2", "2020-01-08", "2020", "A", "C"),
        ("3", "2020-01-08", "2020", "D", "E"),
        ("4", "2020-01-15", "2020", "C", "A"),
        ("5", "2021-01-01", "2021", "A", "B"),
    ], columns=["match_id", "match_date", "season", "home_team_id", "away_team_id"])
    rows = []
    for match in matches.itertuples(index=False):
        for team in (match.home_team_id, match.away_team_id):
            for i in range(11):
                # The same raw name on other teams must never import their minutes.
                name = "Shared" if i == 0 else f"{team}-{i}"
                minute = 10 if team == "A" and match.match_id == "1" and i == 0 else 90
                rows.append((match.match_id, match.match_date, match.season, team,
                             name, "True", "False", str(minute), "starter_full"))
            rows.append((match.match_id, match.match_date, match.season, team,
                         f"{team}-bench", "False", "True", "0", "unused_substitute"))
    minutes = pd.DataFrame(rows, columns=["match_id", "match_date", "season", "team_id",
                                          "player_name_raw", "starter", "listed_substitute",
                                          "minutes_played_normalized", "appearance_type"])
    return matches, minutes


def test_previous_xi_squad_windows_reset_and_no_input_mutation():
    matches, minutes = _fixture()
    old_matches, old_minutes = matches.copy(deep=True), minutes.copy(deep=True)
    result = build_player_workload_features(matches, minutes).set_index("match_id")
    pd.testing.assert_frame_equal(matches, old_matches)
    pd.testing.assert_frame_equal(minutes, old_minutes)
    assert len(result) == 5
    assert result.loc["1", "home_has_previous_j1_match"] == 0
    assert pd.isna(result.loc["1", "home_prev_starters_sum_minutes_7d"])
    assert result.loc["2", "home_prev_starters_count"] == 11
    assert result.loc["2", "home_prev_squad_size"] == 12
    assert result.loc["2", "home_prev_starters_sum_minutes_7d"] == 910
    assert result.loc["2", "home_prev_starters_mean_minutes_7d"] == 910 / 11
    assert result.loc["2", "home_prev_starters_with_7d_history"] == 11
    assert result.loc["2", "home_prev_squad_with_7d_history"] == 11
    assert result.loc["2", "home_prev_squad_sum_minutes_7d"] == 910
    # The bench was listed but did not play, so it has no played history.
    assert result.loc["2", "home_prev_squad_size"] - result.loc["2", "home_prev_squad_with_7d_history"] == 1
    # C played on the same date as match 2; match 4 sees that played history.
    assert result.loc["4", "home_prev_starters_with_7d_history"] == 11
    assert result.loc["5", "home_prev_reference_from_prior_season"] == 1
    assert result.loc["5", "home_prev_starters_sum_minutes_30d"] == 0
    assert result.loc["5", "home_prev_starters_with_30d_history"] == 0


def test_same_date_batch_future_and_target_lineup_do_not_leak():
    matches, minutes = _fixture()
    baseline = build_player_workload_features(matches, minutes).set_index("match_id")
    changed = minutes.copy(deep=True)
    changed.loc[changed.match_id.isin(["2", "3", "4", "5"]), "minutes_played_normalized"] = "0"
    alternate = build_player_workload_features(matches, changed).set_index("match_id")
    assert baseline.loc["2", "home_prev_starters_sum_minutes_7d"] == alternate.loc["2", "home_prev_starters_sum_minutes_7d"]
    # C has no previous J1 squad; same-date match 2 cannot become its own reference.
    assert pd.isna(baseline.loc["2", "away_prev_starters_sum_minutes_7d"])
    assert baseline.loc["2", "away_prev_starters_with_7d_history"] == 0
    assert baseline.loc["3", "home_has_previous_j1_match"] == 0
    assert baseline.loc["1", "home_has_previous_j1_match"] == alternate.loc["1", "home_has_previous_j1_match"]
    changed.loc[(changed.match_id == "2") & (changed.team_id == "A")
                & (changed.player_name_raw == "A-1"), "player_name_raw"] = "Changed XI"
    alternate = build_player_workload_features(matches, changed).set_index("match_id")
    assert baseline.loc["2", "home_prev_starters_sum_minutes_7d"] == alternate.loc["2", "home_prev_starters_sum_minutes_7d"]


def test_cross_team_exact_name_never_links():
    matches, minutes = _fixture()
    result = build_player_workload_features(matches, minutes).set_index("match_id")
    # C's Shared is in the reference XI at match 4, but only C's 8 January row counts.
    # A's earlier Shared row must not be imported into C's seven-day history.
    assert result.loc["2", "away_prev_starters_with_7d_history"] == 0
    assert result.loc["4", "home_prev_starters_sum_minutes_7d"] == 990


def test_duplicate_identity_and_alignment_are_rejected():
    matches, minutes = _fixture()
    with pytest.raises(WorkloadError):
        build_player_workload_features(matches, pd.concat([minutes, minutes.iloc[[0]]], ignore_index=True))
    bad = minutes.copy()
    bad.loc[0, "team_id"] = "unknown"
    with pytest.raises(WorkloadError):
        build_player_workload_features(matches, bad)
    bad_match = pd.concat([matches, matches.iloc[[0]]], ignore_index=True)
    with pytest.raises(WorkloadError):
        build_player_workload_features(bad_match, minutes)


def test_deterministic_and_nonnegative_aggregates():
    matches, minutes = _fixture()
    first = build_player_workload_features(matches, minutes)
    second = build_player_workload_features(matches.sample(frac=1, random_state=7),
                                            minutes.sample(frac=1, random_state=9))
    pd.testing.assert_frame_equal(first, second)
    sums = [c for c in first if "sum_minutes" in c]
    assert all((first[c].dropna() >= 0).all() for c in sums)
    assert not any("high_load" in c for c in first)


def _two_match_case(first_date, second_date, *, same_season=True):
    y1 = first_date[:4]
    y2 = y1 if same_season else second_date[:4]
    matches = pd.DataFrame([
        ("10", first_date, y1, "C", "F"),
        ("11", second_date, y2, "C", "G"),
    ], columns=["match_id", "match_date", "season", "home_team_id", "away_team_id"])
    rows = []
    for m in matches.itertuples(index=False):
        for team in (m.home_team_id, m.away_team_id):
            for i in range(11):
                name = "Shared" if team == "F" and i == 0 else f"{team}-{i}"
                rows.append((m.match_id, m.match_date, m.season, team, name,
                             "True", "False", "90", "starter_full"))
            # C's Shared appears only as an unused bench player: F's played
            # Shared must not give C's reference squad positive history.
            bench = "Shared" if team == "C" else team + "-bench"
            rows.append((m.match_id, m.match_date, m.season, team, bench,
                         "False", "True", "0", "unused_substitute"))
    minutes = pd.DataFrame(rows, columns=["match_id", "match_date", "season", "team_id",
                                          "player_name_raw", "starter", "listed_substitute",
                                          "minutes_played_normalized", "appearance_type"])
    return matches, minutes


def test_cross_team_play_does_not_populate_local_bench_history():
    matches, minutes = _two_match_case("2020-01-01", "2020-01-08")
    row = build_player_workload_features(matches, minutes).set_index("match_id").loc["11"]
    assert row.home_prev_squad_size == 12
    assert row.home_prev_squad_with_7d_history == 11
    assert row.home_prev_squad_sum_minutes_7d == 990


def test_nearby_prior_season_is_still_a_hard_identity_reset():
    matches, minutes = _two_match_case("2020-12-30", "2021-01-02", same_season=False)
    row = build_player_workload_features(matches, minutes).set_index("match_id").loc["11"]
    assert row.home_has_previous_j1_match == 1
    assert row.home_prev_reference_from_prior_season == 1
    assert row.home_prev_starters_with_30d_history == 0
    assert row.home_prev_starters_sum_minutes_30d == 0


def test_windows_exclude_older_play_even_with_previous_squad():
    matches, minutes = _two_match_case("2020-01-01", "2020-01-22")
    row = build_player_workload_features(matches, minutes).set_index("match_id").loc["11"]
    assert row.home_prev_starters_sum_minutes_7d == 0
    assert row.home_prev_starters_sum_minutes_14d == 0
    assert row.home_prev_starters_sum_minutes_30d == 990
