"""Deterministic offline CSVs preserve the existing pre-match Elo series."""

from copy import deepcopy
from dataclasses import asdict

import pandas as pd
import pytest

from src.collect.teams import load_team_master
from src.features.elo_export import export_elo_history
from src.features.elo_history import load_elo_history_with_ongoing
from tests.test_elo_hyakunen import (
    FEATURES, ROOT, UNPLAYED, assert_same_elo, file_hashes, master, special,
    write_inputs,
)
from tests.test_elo_ongoing import publish_fixture, schedule
from tests.test_jleague_ongoing_update import forbid_network


MATCH_COLUMNS = [
    "match_id", "match_date", "competition", "season", "home_team", "away_team",
    "home_team_id", "away_team_id", "home_elo", "away_elo", "elo_diff", "result",
]
RATING_COLUMNS = ["team_id", "canonical_name", "rating", "last_match_date"]


def prepare_inputs(directory, special, schedule):
    directory.mkdir()
    write_inputs(directory, special)
    publish_fixture(directory, schedule)
    return directory


def read_exports(paths):
    match_path, rating_path = paths
    matches = pd.read_csv(
        match_path, dtype={column: "string" for column in MATCH_COLUMNS[:3] + MATCH_COLUMNS[4:8]},
        float_precision="round_trip", keep_default_na=False,
    )
    ratings = pd.read_csv(
        rating_path, dtype={column: "string" for column in ("team_id", "canonical_name", "last_match_date")},
        float_precision="round_trip", keep_default_na=False,
    )
    return matches, ratings


def all_matches(history):
    return pd.concat([
        history.historical.matches, history.hyakunen.matches, history.ongoing.matches,
    ], ignore_index=True)


def assert_matches_preserved(exported, history):
    expected = all_matches(history)
    assert exported.columns.tolist() == MATCH_COLUMNS
    assert exported.match_id.is_unique
    assert exported.match_date.str.fullmatch(r"\d{4}-\d{2}-\d{2}").all()
    for column in MATCH_COLUMNS:
        values = expected[column]
        if column == "match_date":
            values = values.dt.strftime("%Y-%m-%d")
        assert exported[column].tolist() == values.tolist(), column


def assert_current_ratings_preserved(exported, history, master):
    canonical = {alias.team_id: alias.canonical_name for alias in master.aliases}
    assert exported.columns.tolist() == RATING_COLUMNS
    assert exported.team_id.tolist() == sorted(canonical)
    assert exported.team_id.is_unique
    expected_dates = {}
    for row in all_matches(history).itertuples(index=False):
        for team_id in (row.home_team_id, row.away_team_id):
            expected_dates[team_id] = row.match_date.strftime("%Y-%m-%d")
    for row in exported.itertuples(index=False):
        assert row.canonical_name == canonical[row.team_id]
        assert row.rating == history.ongoing.final_ratings[row.team_id]
        assert row.last_match_date == expected_dates.get(row.team_id, "")


def test_exports_preserve_every_value_and_regenerate_identical_bytes_without_input_writes(
    tmp_path, special, schedule, master,
):
    inputs = prepare_inputs(tmp_path / "inputs", special, schedule)
    before_inputs = file_hashes(inputs)
    before_master = deepcopy(master.aliases)
    expected = load_elo_history_with_ongoing(inputs, team_master=master)
    before_history = deepcopy(expected)
    output = tmp_path / "nested" / "elo"
    paths = export_elo_history(inputs, output_dir=output, team_master=master)
    assert paths == (output / "match_elo_history.csv", output / "current_ratings.csv")
    matches, ratings = read_exports(paths)
    assert len(matches) == 214
    assert len(ratings) == 21
    assert_matches_preserved(matches, expected)
    assert_current_ratings_preserved(ratings, expected, master)
    assert matches.match_id.str.startswith("0").any()
    assert "candidate-40" not in set(matches.match_id)
    assert matches.iloc[-3:].match_id.tolist() == ["ongoing-10", "ongoing-20", "ongoing-30"]

    saved = tuple(path.read_bytes() for path in paths)
    for data in saved:
        assert not data.startswith(b"\xef\xbb\xbf")
        assert b"\r" not in data
        assert data.endswith(b"\n")
        data.decode("utf-8")
    assert {path.name for path in output.iterdir()} == {path.name for path in paths}
    again = export_elo_history(inputs, output_dir=output, team_master=master)
    assert tuple(path.read_bytes() for path in again) == saved
    assert file_hashes(inputs) == before_inputs
    assert master.aliases == before_master
    assert_same_elo(expected, before_history)
    pd.testing.assert_frame_equal(expected.ongoing.matches, before_history.ongoing.matches)
    assert expected.ongoing.final_ratings == before_history.ongoing.final_ratings
    after = load_elo_history_with_ongoing(inputs, team_master=master)
    assert_same_elo(after, expected)
    pd.testing.assert_frame_equal(after.ongoing.matches, expected.ongoing.matches)
    assert after.ongoing.final_ratings == expected.ongoing.final_ratings


def test_absent_and_never_played_clubs_keep_their_own_last_rating_and_date(
    tmp_path, special, schedule, master,
):
    inputs = prepare_inputs(tmp_path / "inputs", special, schedule)
    expected = load_elo_history_with_ongoing(inputs, team_master=master)
    _, ratings = read_exports(export_elo_history(inputs, output_dir=tmp_path / "elo", team_master=master))
    assert_current_ratings_preserved(ratings, expected, master)
    by_team = ratings.set_index("team_id")
    assert by_team.loc[UNPLAYED, "rating"] == 1500
    assert by_team.loc[UNPLAYED, "last_match_date"] == ""
    ongoing_ids = set(expected.ongoing.matches.home_team_id) | set(expected.ongoing.matches.away_team_id)
    inactive = set(by_team.index) - ongoing_ids - {UNPLAYED}
    assert inactive
    for team_id in inactive:
        assert by_team.loc[team_id, "rating"] == expected.hyakunen.final_ratings[team_id]
        assert by_team.loc[team_id, "last_match_date"] < "2026-08-07"


def test_no_completed_ongoing_matches_exports_previous_history_and_current_ratings(
    tmp_path, special, schedule, master,
):
    schedule.loc[:, "status"] = "scheduled"
    inputs = prepare_inputs(tmp_path / "inputs", special, schedule)
    expected = load_elo_history_with_ongoing(inputs, team_master=master)
    matches, ratings = read_exports(export_elo_history(inputs, output_dir=tmp_path / "elo", team_master=master))
    assert len(matches) == 211
    assert len(ratings) == master.team_count
    assert_matches_preserved(matches, expected)
    assert_current_ratings_preserved(ratings, expected, master)
    assert dict(zip(ratings.team_id, ratings.rating)) == expected.hyakunen.final_ratings


def test_unconfirmed_future_information_cannot_change_either_export(
    tmp_path, special, schedule, master,
):
    original_inputs = prepare_inputs(tmp_path / "original", special, schedule)
    original = export_elo_history(original_inputs, output_dir=tmp_path / "elo_original", team_master=master)
    changed = schedule.copy(deep=True)
    excluded = changed.status.ne("completed")
    for column in ("home_team", "away_team", "match_date", "home_score", "result"):
        changed[column] = changed[column].astype(object)
        changed.loc[excluded, column] = "unusable future information"
    changed.loc[excluded, "match_id"] = "ongoing-10"
    changed_inputs = prepare_inputs(tmp_path / "changed", special, changed)
    modified = export_elo_history(changed_inputs, output_dir=tmp_path / "elo_modified", team_master=master)
    assert tuple(path.read_bytes() for path in original) == tuple(path.read_bytes() for path in modified)


def test_latest_result_changes_current_rating_without_rewriting_any_pre_match_elo(
    tmp_path, special, schedule, master,
):
    original_inputs = prepare_inputs(tmp_path / "original", special, schedule)
    original_matches, original_ratings = read_exports(
        export_elo_history(original_inputs, output_dir=tmp_path / "elo_original", team_master=master),
    )
    changed = schedule.copy(deep=True)
    changed.loc[changed.match_id.eq("ongoing-30"), ["home_score", "away_score", "result"]] = [5, 0, 2]
    changed_inputs = prepare_inputs(tmp_path / "changed", special, changed)
    modified_matches, modified_ratings = read_exports(
        export_elo_history(changed_inputs, output_dir=tmp_path / "elo_modified", team_master=master),
    )
    pd.testing.assert_frame_equal(original_matches[FEATURES], modified_matches[FEATURES], check_exact=True)
    pd.testing.assert_frame_equal(original_matches.iloc[:-1], modified_matches.iloc[:-1], check_exact=True)
    assert original_matches.iloc[-1].result != modified_matches.iloc[-1].result
    assert not original_ratings.rating.equals(modified_ratings.rating)


def test_incomplete_inputs_fail_without_overwriting_existing_exports(tmp_path, special, schedule, master):
    inputs = prepare_inputs(tmp_path / "inputs", special, schedule)
    output = tmp_path / "elo"
    paths = export_elo_history(inputs, output_dir=output, team_master=master)
    saved = tuple(path.read_bytes() for path in paths)
    (inputs / "2020_matches_probe.csv").unlink()
    before = file_hashes(inputs)
    with pytest.raises(FileNotFoundError):
        export_elo_history(inputs, output_dir=output, team_master=master)
    assert tuple(path.read_bytes() for path in paths) == saved
    assert file_hashes(inputs) == before


def test_cli_reads_explicit_input_and_master_paths(tmp_path, special, schedule, master, capsys):
    from scripts.export_elo import main

    inputs = prepare_inputs(tmp_path / "inputs", special, schedule)
    master_path = tmp_path / "teams.csv"
    pd.DataFrame([asdict(alias) for alias in master.aliases]).to_csv(master_path, index=False)
    before_inputs, before_master = file_hashes(inputs), master_path.read_bytes()
    output = tmp_path / "elo"
    assert main([
        "--processed-dir", str(inputs), "--output-dir", str(output),
        "--team-master", str(master_path),
    ]) == 0
    paths = (output / "match_elo_history.csv", output / "current_ratings.csv")
    assert capsys.readouterr().out.splitlines() == [str(path) for path in paths]
    matches, ratings = read_exports(paths)
    expected = load_elo_history_with_ongoing(inputs, team_master=master)
    assert_matches_preserved(matches, expected)
    assert_current_ratings_preserved(ratings, expected, master)
    assert file_hashes(inputs) == before_inputs
    assert master_path.read_bytes() == before_master


def test_cached_3858_matches_33_clubs_fc_tokyo_and_all_inputs_remain_unchanged(tmp_path):
    inputs = ROOT / "data/processed/jleague"
    required = [inputs / f"{year}_matches_probe.csv" for year in range(2015, 2026)]
    required.extend([inputs / "2026_hyakunen/matches.csv", inputs / "2026_27/latest.json"])
    if not all(path.is_file() for path in required):
        pytest.skip("Locally acquired CSVs are not distributed with the repository")
    before = {name: file_hashes(ROOT / "data" / name) for name in ("raw", "processed", "master")}
    master = load_team_master()
    expected = load_elo_history_with_ongoing(inputs, team_master=master)
    paths = export_elo_history(inputs, output_dir=tmp_path / "elo")
    matches, ratings = read_exports(paths)
    assert len(matches) == matches.match_id.nunique() == 3858
    assert len(ratings) == ratings.team_id.nunique() == master.team_count == 33
    assert_matches_preserved(matches, expected)
    assert_current_ratings_preserved(ratings, expected, master)
    tokyo = ratings.set_index("team_id").loc[master.resolve_team_id("FC東京")]
    assert tokyo.rating == pytest.approx(1597.745943, abs=0.000001, rel=0)
    assert tokyo.canonical_name == "ＦＣ東京"
    completed_ids = set(expected.ongoing.matches.home_team_id) | set(expected.ongoing.matches.away_team_id)
    inactive = ratings.loc[~ratings.team_id.isin(completed_ids)]
    assert len(inactive) == 13
    for row in inactive.itertuples(index=False):
        assert row.rating == expected.hyakunen.final_ratings[row.team_id]

    saved = tuple(path.read_bytes() for path in paths)
    repeated = export_elo_history(inputs, output_dir=tmp_path / "elo")
    assert tuple(path.read_bytes() for path in repeated) == saved
    after = load_elo_history_with_ongoing(inputs, team_master=master)
    assert_same_elo(after, expected)
    pd.testing.assert_frame_equal(after.ongoing.matches, expected.ongoing.matches, check_exact=True)
    assert after.ongoing.final_ratings == expected.ongoing.final_ratings
    assert {name: file_hashes(ROOT / "data" / name) for name in ("raw", "processed", "master")} == before
