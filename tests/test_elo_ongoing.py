"""Append only locally confirmed ongoing matches, without observing future results."""

from hashlib import sha256
import json

import pandas as pd
import pytest

from src.collect.jleague_ongoing import COMPLETION_POLICY, FORMAT_VERSION, read_latest
from src.collect.matches import MatchValidationError
from src.collect.teams import UnknownTeamError, load_team_master
from src.features.elo import EloRatings
from src.features.elo_history import (
    EloHistoryError, build_elo_history_with_hyakunen,
    build_elo_history_with_ongoing, load_elo_history_with_hyakunen,
    load_elo_history_with_ongoing,
)
from tests.test_elo_hyakunen import (
    FEATURES, ROOT, assert_same_elo, file_hashes, master, ordinary, special,
    write_inputs,
)
from tests.test_jleague_ongoing_update import forbid_network


OBSERVED = "2026-09-15T10:30:00+00:00"


def ongoing_match(match_id, day, home, away, score=(1, 0), status="completed"):
    return {
        "match_id": match_id, "season": 2026, "round": 1,
        "match_date": day, "home_team": home, "away_team": away,
        "stadium": "Test stadium", "home_score": score[0], "away_score": score[1],
        "result": 2 if score[0] > score[1] else 0 if score[0] < score[1] else 1,
        "fixture_key": f"j1_2026_2027:{home.lower()}:{away.lower()}",
        "status": status, "competition_key": "j1_2026_2027",
        "competition": "Ｊ１", "stage": "full_season", "kickoff_time": "19:00",
        "evidence_type": "official_game_over_section",
        "evidence_url": "https://www.jleague.jp/match/j1/2026/080701/",
        "evidence_sha256": "a" * 64, "evidence_fetched_at_utc": OBSERVED,
        "completion_origin_snapshot": "offline-confirmed",
    }


@pytest.fixture
def schedule():
    return pd.DataFrame([
        ongoing_match("ongoing-20", "2026-08-07", "EAST00", "WEST00"),
        ongoing_match("ongoing-10", "2026-08-07", "EAST01", "WEST01", (0, 0)),
        ongoing_match("ongoing-30", "2026-08-14", "WEST00", "EAST00", (0, 1)),
        ongoing_match("candidate-40", "2026-08-21", "EAST02", "WEST02", status="candidate"),
        ongoing_match("", "2027-05-01", "EAST03", "WEST03", status="scheduled"),
    ])


def replay(ordinary, special, schedule, master, observed_at=OBSERVED):
    return build_elo_history_with_ongoing(
        ordinary, special, schedule, team_master=master, observed_at=observed_at,
    )


def test_every_first_ongoing_appearance_inherits_special_final_rating(ordinary, special, schedule, master):
    previous = build_elo_history_with_hyakunen(ordinary, special, team_master=master)
    history = replay(ordinary, special, schedule, master)
    assert_same_elo(history, previous)
    seen = set()
    for row in history.ongoing.matches.itertuples(index=False):
        for side in ("home", "away"):
            team_id = getattr(row, f"{side}_team_id")
            if team_id not in seen:
                assert getattr(row, f"{side}_elo") == previous.hyakunen.final_ratings[team_id]
                seen.add(team_id)
    assert len(seen) == 4
    assert any(previous.hyakunen.final_ratings[team_id] != 1500 for team_id in seen)


def test_only_completed_are_processed_once_with_pre_result_features(ordinary, special, schedule, master):
    history = replay(ordinary, special, schedule, master)
    assert history.ongoing.matches.match_id.tolist() == ["ongoing-10", "ongoing-20", "ongoing-30"]
    assert history.ongoing.matches.status.eq("completed").all()
    assert history.ongoing.matches.match_id.is_unique
    elo = EloRatings(sorted(history.historical.final_ratings))
    for frame in (history.historical.matches, history.hyakunen.matches, history.ongoing.matches):
        for row in frame.itertuples(index=False):
            before = elo.pre_match(row.home_team_id, row.away_team_id)
            assert (row.home_elo, row.away_elo) == (before.home_rating, before.away_rating)
            assert row.elo_diff == before.home_rating - before.away_rating
            assert row.home_team_id == master.resolve_team_id(row.home_team, on=row.match_date)
            assert row.away_team_id == master.resolve_team_id(row.away_team, on=row.match_date)
            elo.update(row.home_team_id, row.away_team_id, row.result)
    assert history.ongoing.final_ratings == elo.ratings
    assert sum(history.ongoing.final_ratings.values()) == pytest.approx(master.team_count * 1500)
    assert history.ongoing.final_ratings["team_0021"] == 1500


def test_unconfirmed_scores_unknown_names_and_future_dates_do_not_enter_elo(ordinary, special, schedule, master):
    original = replay(ordinary, special, schedule, master)
    changed = schedule.copy(deep=True)
    excluded = changed.status.ne("completed")
    for column in ("home_team", "away_team", "match_date", "home_score", "result", "evidence_type"):
        changed[column] = changed[column].astype(object)
        changed.loc[excluded, column] = "unusable future information"
    # A scheduled/candidate ID, even one colliding with history, is not an Elo input.
    changed.loc[excluded, "match_id"] = ordinary.iloc[0].match_id
    modified = replay(ordinary, special, changed, master)
    assert_same_elo(original, modified)
    pd.testing.assert_frame_equal(original.ongoing.matches[FEATURES], modified.ongoing.matches[FEATURES])
    # Extra provenance columns retain their source dtype; changing excluded rows
    # can widen that dtype without changing a single completed value or rating.
    pd.testing.assert_frame_equal(original.ongoing.matches, modified.ongoing.matches, check_dtype=False)
    assert original.ongoing.final_ratings == modified.ongoing.final_ratings


def test_future_completed_result_cannot_rewrite_previous_or_own_pre_match_ratings(ordinary, special, schedule, master):
    original = replay(ordinary, special, schedule, master)
    changed = schedule.copy(deep=True)
    changed.loc[changed.match_id.eq("ongoing-30"), ["home_score", "away_score", "result"]] = [5, 0, 2]
    modified = replay(ordinary, special, changed, master)
    assert_same_elo(original, modified)
    pd.testing.assert_frame_equal(original.ongoing.matches[FEATURES], modified.ongoing.matches[FEATURES])
    pd.testing.assert_frame_equal(original.ongoing.matches.iloc[:-1], modified.ongoing.matches.iloc[:-1])
    assert original.ongoing.final_ratings != modified.ongoing.final_ratings


def test_repeated_and_shuffled_input_is_deterministic_without_mutating_inputs(ordinary, special, schedule, master):
    before = [frame.copy(deep=True) for frame in (ordinary, special, schedule)]
    first = replay(ordinary, special, schedule, master)
    second = replay(ordinary.sample(frac=1, random_state=1),
                    special.sample(frac=1, random_state=2),
                    schedule.sample(frac=1, random_state=3), master)
    assert_same_elo(first, second)
    pd.testing.assert_frame_equal(first.ongoing.matches, second.ongoing.matches)
    assert first.ongoing.final_ratings == second.ongoing.final_ratings
    for frame, saved in zip((ordinary, special, schedule), before):
        pd.testing.assert_frame_equal(frame, saved)
    first.ongoing.matches.loc[0, "home_team"] = "output-only mutation"
    first.ongoing.final_ratings["team_0001"] = -999
    for frame, saved in zip((ordinary, special, schedule), before):
        pd.testing.assert_frame_equal(frame, saved)
    assert first.hyakunen.final_ratings == second.hyakunen.final_ratings


def test_no_completed_matches_preserves_all_previous_ratings(ordinary, special, schedule, master):
    schedule.loc[:, "status"] = "scheduled"
    history = replay(ordinary, special, schedule, master)
    assert history.ongoing.matches.empty
    assert set(FEATURES).issubset(history.ongoing.matches.columns)
    assert history.ongoing.final_ratings == history.hyakunen.final_ratings
    assert history.ongoing.final_ratings is not history.hyakunen.final_ratings


@pytest.mark.parametrize("column,value", [
    ("competition_key", "j1_hyakunen_2026"), ("competition", "Ｊ２"),
    ("stage", "regional"), ("season", 2025), ("match_date", "2028-01-01"),
    ("fixture_key", ""), ("fixture_key", "other:home:away"),
    ("evidence_type", "numeric_score"), ("evidence_url", ""),
    ("evidence_sha256", ""), ("evidence_fetched_at_utc", ""),
    ("completion_origin_snapshot", ""),
])
def test_completed_requires_correct_competition_identity_and_completion_provenance(
    ordinary, special, schedule, master, column, value,
):
    schedule.loc[0, column] = value
    with pytest.raises(EloHistoryError):
        replay(ordinary, special, schedule, master)


@pytest.mark.parametrize("problem", ["missing_column", "unknown_status", "null_status"])
def test_numeric_score_cannot_replace_an_explicit_valid_status(ordinary, special, schedule, master, problem):
    if problem == "missing_column":
        schedule = schedule.drop(columns="status")
    else:
        schedule.loc[0, "status"] = "finished" if problem == "unknown_status" else pd.NA
    with pytest.raises(EloHistoryError):
        replay(ordinary, special, schedule, master)


def test_result_still_passes_existing_validation(ordinary, special, schedule, master):
    schedule.loc[0, "result"] = 0
    with pytest.raises(MatchValidationError):
        replay(ordinary, special, schedule, master)


def test_unknown_completed_club_is_not_implicitly_registered(ordinary, special, schedule, master):
    schedule.loc[0, "home_team"] = "UNKNOWN"
    with pytest.raises(UnknownTeamError):
        replay(ordinary, special, schedule, master)


@pytest.mark.parametrize("collision", ["fixture_key", "match_id", "historical_id", "hyakunen_id", "same_day"])
def test_completed_identity_and_chronology_collisions_are_rejected(ordinary, special, schedule, master, collision):
    if collision in ("fixture_key", "match_id"):
        schedule.loc[1, collision] = schedule.loc[0, collision]
    elif collision == "historical_id":
        schedule.loc[0, "match_id"] = ordinary.iloc[0].match_id
    elif collision == "hyakunen_id":
        schedule.loc[0, "match_id"] = special.iloc[0].match_id
    else:
        schedule.loc[2, "match_date"] = schedule.loc[0, "match_date"]
    with pytest.raises((EloHistoryError, MatchValidationError)):
        replay(ordinary, special, schedule, master)


def test_ongoing_must_follow_the_end_of_hyakunen(ordinary, special, schedule, master):
    schedule.loc[0, "match_date"] = "2026-06-06"
    with pytest.raises(EloHistoryError):
        replay(ordinary, special, schedule, master)


def test_future_completed_date_is_rejected_against_saved_observation(ordinary, special, schedule, master):
    schedule.loc[0, "match_date"] = "2026-09-16"
    with pytest.raises(EloHistoryError):
        replay(ordinary, special, schedule, master)


def test_observed_timestamp_must_be_timezone_aware(ordinary, special, schedule, master):
    with pytest.raises(EloHistoryError):
        replay(ordinary, special, schedule, master, observed_at="2026-09-15T10:30:00")


def test_observation_uses_japanese_calendar_date(ordinary, special, schedule, master):
    completed = schedule.loc[[0]].copy()
    completed.loc[0, "match_date"] = "2026-09-16"
    completed.loc[0, "evidence_fetched_at_utc"] = "2026-09-15T16:00:00+00:00"
    history = replay(ordinary, special, completed, master, observed_at="2026-09-15T16:00:00+00:00")
    assert history.ongoing.matches.match_date.tolist() == [pd.Timestamp("2026-09-16")]


def publish_fixture(directory, schedule, *, completed=None, publication_status="published"):
    """A small immutable publication; no updater or network access is needed."""
    output = directory / "2026_27"
    revision = output / "revisions" / "offline-revision"
    revision.mkdir(parents=True, exist_ok=True)
    completed = schedule.loc[schedule.status.eq("completed")] if completed is None else completed
    for name, frame in (("schedule.csv", schedule), ("completed_matches.csv", completed)):
        frame.to_csv(revision / name, index=False)
    summary = {
        "competition_key": "j1_2026_2027", "publication_status": publication_status,
        "observed_at_utc": OBSERVED, "counts": {status: int(schedule.status.eq(status).sum())
        for status in ("scheduled", "candidate", "completed")}, "total_fixtures": len(schedule),
    }
    manifest = {
        "format_version": FORMAT_VERSION, "completion_policy": COMPLETION_POLICY,
        "snapshot_id": "offline-confirmed", "summary": summary,
        "files": {name: sha256((revision / name).read_bytes()).hexdigest()
                  for name in ("schedule.csv", "completed_matches.csv")},
    }
    manifest_path = revision / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    (output / "latest.json").write_text(json.dumps({
        "revision_id": revision.name, "manifest_sha256": sha256(manifest_path.read_bytes()).hexdigest(),
    }), encoding="utf-8")
    return revision


def test_loader_uses_verified_revision_and_ignores_mutable_projection_copies(tmp_path, special, schedule, master):
    write_inputs(tmp_path, special)
    publish_fixture(tmp_path, schedule)
    (tmp_path / "2026_27/schedule.csv").write_bytes(b"must not read this projection")
    before = file_hashes(tmp_path)
    first = load_elo_history_with_ongoing(tmp_path, team_master=master)
    second = load_elo_history_with_ongoing(tmp_path, team_master=master)
    assert len(first.historical.matches) == 11
    assert len(first.hyakunen.matches) == 200
    assert len(first.ongoing.matches) == 3
    assert_same_elo(first, second)
    pd.testing.assert_frame_equal(first.ongoing.matches, second.ongoing.matches)
    assert first.ongoing.final_ratings == second.ongoing.final_ratings
    assert file_hashes(tmp_path) == before


@pytest.mark.parametrize("problem", ["missing_pointer", "modified_csv", "unpublished", "subset_mismatch"])
def test_loader_rejects_unverified_or_inconsistent_publication(tmp_path, special, schedule, master, problem):
    write_inputs(tmp_path, special)
    if problem == "subset_mismatch":
        completed = schedule.loc[schedule.status.eq("completed")].copy()
        completed.loc[0, ["home_score", "away_score", "result"]] = [0, 1, 0]
        revision = publish_fixture(tmp_path, schedule, completed=completed)
    else:
        revision = publish_fixture(tmp_path, schedule,
                                   publication_status="held" if problem == "unpublished" else "published")
    if problem == "missing_pointer":
        (tmp_path / "2026_27/latest.json").unlink()
    elif problem == "modified_csv":
        with (revision / "schedule.csv").open("ab") as handle:
            handle.write(b"unexpected mutation")
    with pytest.raises((ValueError, FileNotFoundError)):
        load_elo_history_with_ongoing(tmp_path, team_master=master)


def test_loader_requires_historical_inputs_even_when_latest_is_complete(tmp_path, special, schedule, master):
    write_inputs(tmp_path, special)
    publish_fixture(tmp_path, schedule)
    (tmp_path / "2020_matches_probe.csv").unlink()
    with pytest.raises(FileNotFoundError):
        load_elo_history_with_ongoing(tmp_path, team_master=master)


def test_cached_70_completed_extend_3788_matches_and_leave_all_data_unchanged():
    directory = ROOT / "data/processed/jleague"
    paths = [directory / f"{year}_matches_probe.csv" for year in range(2015, 2026)]
    paths.extend([directory / "2026_hyakunen/matches.csv", directory / "2026_27/latest.json"])
    if not all(path.is_file() for path in paths):
        pytest.skip("Locally acquired CSVs are not distributed with the repository")
    before = {name: file_hashes(ROOT / "data" / name) for name in ("raw", "processed", "master")}
    revision, _ = read_latest(directory / "2026_27")
    source = pd.read_csv(revision / "schedule.csv", dtype="string", keep_default_na=False)
    assert source.status.value_counts().to_dict() == {"scheduled": 310, "completed": 70}
    master = load_team_master()
    previous = load_elo_history_with_hyakunen(directory, team_master=master)
    history = load_elo_history_with_ongoing(directory, team_master=master)
    assert_same_elo(history, previous)
    completed = history.ongoing.matches
    assert len(completed) == completed.match_id.nunique() == 70
    assert set(completed.match_id) == set(source.loc[source.status.eq("completed"), "match_id"])
    assert set(completed.fixture_key).isdisjoint(source.loc[source.status.ne("completed"), "fixture_key"])
    all_matches = pd.concat([history.historical.matches, history.hyakunen.matches, completed], ignore_index=True)
    assert len(all_matches) == all_matches.match_id.nunique() == 3858
    assert len(set(all_matches.home_team_id) | set(all_matches.away_team_id)) == 33
    elo = EloRatings(sorted(history.historical.final_ratings))
    seen_ongoing = set()
    for frame in (history.historical.matches, history.hyakunen.matches, completed):
        for row in frame.itertuples(index=False):
            before_match = elo.pre_match(row.home_team_id, row.away_team_id)
            assert (row.home_elo, row.away_elo) == (before_match.home_rating, before_match.away_rating)
            assert row.elo_diff == before_match.home_rating - before_match.away_rating
            if frame is completed:
                for side in ("home", "away"):
                    team_id = getattr(row, f"{side}_team_id")
                    assert team_id == master.resolve_team_id(getattr(row, f"{side}_team"), on=row.match_date)
                    if team_id not in seen_ongoing:
                        assert getattr(row, f"{side}_elo") == previous.hyakunen.final_ratings[team_id]
                        seen_ongoing.add(team_id)
            elo.update(row.home_team_id, row.away_team_id, row.result)
    assert len(seen_ongoing) == 20
    assert history.ongoing.final_ratings == elo.ratings
    assert sum(history.ongoing.final_ratings.values()) == pytest.approx(33 * 1500)
    assert {name: file_hashes(ROOT / "data" / name) for name in ("raw", "processed", "master")} == before
