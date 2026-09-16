"""Sequential Elo updates from synthetic 90-minute results only."""

from dataclasses import FrozenInstanceError
from enum import IntEnum

import pytest

from src.features.elo import (
    INITIAL_RATING,
    K_FACTOR,
    EloRatings,
    expected_score,
)


TEAMS = ("team_0001", "team_0002", "team_0003")
A, B, C = TEAMS


@pytest.mark.parametrize("rating,opponent,expected", [
    (1500, 1500, 0.5),
    (1900, 1500, 10 / 11),
    (1500, 1900, 1 / 11),
])
def test_expected_score_uses_rating_difference(rating, opponent, expected):
    assert expected_score(rating, opponent) == pytest.approx(expected)
    assert expected_score(rating, opponent) + expected_score(opponent, rating) == pytest.approx(1)


@pytest.mark.parametrize("invalid", [True, "1500", None, float("nan"), float("inf")])
def test_expected_score_rejects_non_finite_or_non_numeric_ratings(invalid):
    for rating, opponent in ((invalid, 1500), (1500, invalid)):
        with pytest.raises(ValueError):
            expected_score(rating, opponent)


def test_explicit_roster_initializes_every_team_and_getting_ratings_does_not_update():
    ratings = EloRatings(iter(TEAMS))

    assert INITIAL_RATING == 1500.0
    assert K_FACTOR == 20.0
    assert ratings.ratings == dict.fromkeys(TEAMS, 1500.0)
    assert ratings.get_rating(A) == 1500.0
    assert ratings.pre_match(A, B).home_rating == 1500.0
    assert ratings.ratings == dict.fromkeys(TEAMS, 1500.0)


@pytest.mark.parametrize("team_ids", [
    [], A, [A, A], [""], [" "], [" team_0001"], [None],
])
def test_roster_rejects_invalid_or_duplicate_team_ids(team_ids):
    with pytest.raises(ValueError):
        EloRatings(team_ids)


@pytest.mark.parametrize("result,home_after,away_after", [
    (0, 1490.0, 1510.0),
    (1, 1500.0, 1500.0),
    (2, 1510.0, 1490.0),
])
def test_win_draw_and_loss_update_both_teams(result, home_after, away_after):
    ratings = EloRatings(TEAMS)
    update = ratings.update(A, B, result)

    assert update.result == result
    assert update.before.home_expected == 0.5
    assert update.before.away_expected == 0.5
    assert update.after.home_rating == home_after
    assert update.after.away_rating == away_after
    assert ratings.ratings == {A: home_after, B: away_after, C: 1500.0}


def test_draw_moves_unequal_ratings_toward_each_other():
    ratings = EloRatings(TEAMS)
    ratings.update(A, B, 2)

    update = ratings.update(A, B, 1)

    assert 1500 < update.after.home_rating < update.before.home_rating
    assert update.before.away_rating < update.after.away_rating < 1500
    assert update.after.home_rating == pytest.approx(1509.4249887221546)


def test_rating_sum_is_preserved_after_each_match_in_a_longer_sequence():
    ratings = EloRatings(TEAMS)
    matches = [(A, B, 2), (B, C, 0), (C, A, 1), (A, C, 0)] * 25

    for home, away, result in matches:
        update = ratings.update(home, away, result)
        assert update.after.home_rating + update.after.away_rating == pytest.approx(
            update.before.home_rating + update.before.away_rating
        )
        assert sum(ratings.ratings.values()) == pytest.approx(4500.0)


def test_underdog_win_awards_more_than_equal_strength_win():
    ratings = EloRatings(TEAMS)
    ratings.update(A, B, 2)

    update = ratings.update(B, A, 2)

    assert update.before.home_expected < 0.5
    assert update.after.home_rating - update.before.home_rating > 10
    assert update.after.home_rating == pytest.approx(1500.5750112778454)


def test_swapping_home_and_away_does_not_introduce_home_advantage():
    home_win = EloRatings(TEAMS)
    away_win = EloRatings(TEAMS)

    home_win.update(A, B, 2)
    away_win.update(B, A, 0)

    assert home_win.ratings == away_win.ratings


@pytest.mark.parametrize("operation", ["get_rating", "pre_match", "update"])
def test_unknown_team_id_is_not_automatically_registered(operation):
    ratings = EloRatings(TEAMS)
    original = ratings.ratings
    unknown = "team_9999"
    calls = [(unknown,)] if operation == "get_rating" else [(unknown, A), (A, unknown)]

    for args in calls:
        if operation == "update":
            args += (2,)
        with pytest.raises(KeyError):
            getattr(ratings, operation)(*args)
        assert ratings.ratings == original


def test_self_match_is_rejected_without_changing_state():
    ratings = EloRatings(TEAMS)
    ratings.update(A, B, 0)
    original = ratings.ratings

    with pytest.raises(ValueError):
        ratings.pre_match(A, A)
    with pytest.raises(ValueError):
        ratings.update(A, A, 2)
    assert ratings.ratings == original


@pytest.mark.parametrize("result", [-1, 3, 2.0, "2", True, None])
def test_invalid_result_fails_atomically(result):
    ratings = EloRatings(TEAMS)
    ratings.update(A, B, 2)
    original = ratings.ratings

    with pytest.raises(ValueError):
        ratings.update(B, C, result)
    assert ratings.ratings == original


def test_integral_result_subclass_is_accepted():
    class Result(IntEnum):
        HOME_WIN = 2

    ratings = EloRatings(TEAMS)
    update = ratings.update(A, B, Result.HOME_WIN)

    assert update.result == 2
    assert ratings.get_rating(A) == 1510.0


def test_pre_match_snapshot_and_post_match_snapshot_are_separate_and_immutable():
    ratings = EloRatings(TEAMS)
    before = ratings.pre_match(A, B)

    update = ratings.update(A, B, 2)

    assert update.before == before
    assert (before.home_team_id, before.away_team_id) == (A, B)
    assert (before.home_rating, before.away_rating) == (1500.0, 1500.0)
    assert (update.after.home_rating, update.after.away_rating) == (1510.0, 1490.0)
    assert update.after == ratings.pre_match(A, B)
    assert update.after.home_expected == pytest.approx(0.5287505638922686)
    assert update.after.away_expected == pytest.approx(0.4712494361077314)
    with pytest.raises(FrozenInstanceError):
        before.home_rating = 9000
    with pytest.raises(FrozenInstanceError):
        update.result = 0


def test_ratings_property_returns_a_copy():
    ratings = EloRatings(TEAMS)
    exposed = ratings.ratings
    exposed[A] = 9000
    exposed["team_9999"] = 1500

    assert ratings.ratings == dict.fromkeys(TEAMS, 1500.0)


def test_processing_the_same_input_order_is_reproducible():
    matches = [(A, B, 2), (B, C, 1), (C, A, 0), (A, B, 0)]
    first = EloRatings(TEAMS)
    second = EloRatings(TEAMS)

    first_updates = [first.update(*match) for match in matches]
    second_updates = [second.update(*match) for match in matches]

    assert first_updates == second_updates
    assert first.ratings == second.ratings
    for previous, current in zip(first_updates, first_updates[1:]):
        previous_teams = {
            previous.after.home_team_id: previous.after.home_rating,
            previous.after.away_team_id: previous.after.away_rating,
        }
        if current.before.home_team_id in previous_teams:
            assert current.before.home_rating == previous_teams[current.before.home_team_id]


def test_appending_or_changing_future_results_cannot_change_past_snapshots():
    prefix = [(A, B, 2), (B, C, 1)]
    first = EloRatings(TEAMS)
    second = EloRatings(TEAMS)
    saved = [first.update(*match) for match in prefix]
    copied = [second.update(*match) for match in prefix]

    first.update(C, A, 2)
    first.update(A, B, 0)
    second.update(C, A, 0)

    assert saved == copied
    assert saved[0].before.home_rating == 1500.0
    assert saved[0].after.home_rating == 1510.0
    assert saved[1].before.home_rating == 1490.0
    assert first.ratings != second.ratings


def test_current_result_does_not_leak_into_its_own_pre_match_ratings():
    winning = EloRatings(TEAMS)
    losing = EloRatings(TEAMS)
    for ratings in (winning, losing):
        ratings.update(A, C, 2)

    win_update = winning.update(A, B, 2)
    loss_update = losing.update(A, B, 0)

    assert win_update.before == loss_update.before
    assert win_update.before.home_rating == 1510.0
    assert win_update.before.away_rating == 1500.0
    assert win_update.after != loss_update.after
