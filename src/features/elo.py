"""Minimal, in-memory Elo updates using only the supplied 90-minute result.

Callers resolve team names first and submit completed matches in chronological
order, once each. This module processes one match at a time, without looking
ahead, sorting matches, reading data, or using penalties/aggregate tie winners.
"""

from collections.abc import Iterable
from dataclasses import dataclass
import math
from numbers import Integral, Real


INITIAL_RATING = 1500.0
K_FACTOR = 20.0


def expected_score(rating: float, opponent_rating: float) -> float:
    """Return the Elo expected score (win=1, draw=0.5, loss=0), scale 400."""
    if any(isinstance(value, bool) or not isinstance(value, Real)
           or not math.isfinite(value) for value in (rating, opponent_rating)):
        raise ValueError("Ratings must be finite real numbers.")
    rating, opponent_rating = float(rating), float(opponent_rating)
    # Equivalent to 1 / (1 + 10 ** ((opponent - rating) / 400)).
    # A nonpositive exponent avoids overflow for very large rating differences.
    if rating >= opponent_rating:
        return 1.0 / (1.0 + 10.0 ** ((opponent_rating - rating) / 400.0))
    ratio = 10.0 ** ((rating - opponent_rating) / 400.0)
    return ratio / (1.0 + ratio)


@dataclass(frozen=True)
class EloSnapshot:
    """Detached ratings and expected scores at one point in the update stream."""

    home_team_id: str
    away_team_id: str
    home_rating: float
    away_rating: float
    home_expected: float
    away_expected: float


@dataclass(frozen=True)
class EloUpdate:
    """Immutable before/after records for one 90-minute result."""

    before: EloSnapshot
    after: EloSnapshot
    result: int


class EloRatings:
    """Fixed-1500/K=20 ratings keyed by an explicitly supplied team-ID roster.

    Supply unique IDs resolved/registered by the team master. Unknown IDs raise
    KeyError; no team is implicitly added. A new instance starts a fresh replay.
    """

    def __init__(self, team_ids: Iterable[str], k_factor: float = K_FACTOR):
        if isinstance(k_factor, bool) or not isinstance(k_factor, Real) or not math.isfinite(k_factor) or k_factor <= 0:
            raise ValueError("k_factor must be a finite positive real number.")
        if isinstance(team_ids, (str, bytes)):
            raise ValueError("Provide an iterable of team IDs, not a single string.")
        ratings = {}
        for team_id in team_ids:
            if (not isinstance(team_id, str) or not team_id
                    or team_id != team_id.strip()
                    or any(ord(char) < 32 for char in team_id)):
                raise ValueError("Team IDs must be nonempty strings without surrounding whitespace.")
            if team_id in ratings:
                raise ValueError(f"Duplicate team_id: {team_id!r}.")
            ratings[team_id] = INITIAL_RATING
        if not ratings:
            raise ValueError("At least one registered team ID is required.")
        self._ratings = ratings
        self._k_factor = float(k_factor)

    @property
    def ratings(self) -> dict[str, float]:
        """Return a detached copy; external edits cannot change Elo state."""
        return self._ratings.copy()

    def get_rating(self, team_id: str) -> float:
        if not isinstance(team_id, str) or team_id not in self._ratings:
            raise KeyError(f"Unknown team_id: {team_id!r}.")
        return self._ratings[team_id]

    @staticmethod
    def _snapshot(home_team_id, away_team_id, home_rating, away_rating):
        home_expected = expected_score(home_rating, away_rating)
        return EloSnapshot(
            home_team_id, away_team_id, home_rating, away_rating,
            home_expected, 1.0 - home_expected,
        )

    def pre_match(self, home_team_id: str, away_team_id: str) -> EloSnapshot:
        """Read current ratings without a result or any state mutation."""
        home_rating = self.get_rating(home_team_id)
        away_rating = self.get_rating(away_team_id)
        if home_team_id == away_team_id:
            raise ValueError("A team cannot play itself.")
        return self._snapshot(home_team_id, away_team_id, home_rating, away_rating)

    def update(self, home_team_id: str, away_team_id: str, result: int) -> EloUpdate:
        """Apply one completed 90-minute result: 0=away win, 1=draw, 2=home win.

        Both ratings use the same pre-match expectation. PK outcomes, extra-time
        winners and playoff tie winners must never be substituted for result.
        Invalid inputs leave the ratings unchanged.
        """
        if isinstance(result, bool) or not isinstance(result, Integral) or result not in (0, 1, 2):
            raise ValueError("result must be an integer: 0=away win, 1=draw, 2=home win.")
        before = self.pre_match(home_team_id, away_team_id)
        delta = self._k_factor * (int(result) / 2.0 - before.home_expected)
        after = self._snapshot(
            home_team_id, away_team_id,
            before.home_rating + delta, before.away_rating - delta,
        )
        update = EloUpdate(before, after, int(result))
        self._ratings[home_team_id] = after.home_rating
        self._ratings[away_team_id] = after.away_rating
        return update
