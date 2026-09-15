"""Resolve source-specific club aliases to manually assigned, permanent IDs.

This module never changes match names or writes acquired/processed data. A club
rename changes display names/aliases, not its ID. Unknown names fail explicitly.
"""

from collections import defaultdict
import csv
from dataclasses import dataclass
from datetime import date, datetime, time
from pathlib import Path
import re

import pandas as pd


DEFAULT_TEAM_MASTER_PATH = Path(__file__).resolve().parents[2] / "data/master/teams.csv"
DEFAULT_SOURCE = "jleague_data_site"
MASTER_COLUMNS = (
    "team_id", "canonical_name", "source_name", "source",
    "valid_from", "valid_to", "source_club_id",
)


class TeamMasterError(ValueError):
    """Invalid registry, lookup input, or match-to-team mapping."""


class UnknownTeamError(TeamMasterError):
    """The source/name/date has no registered alias; never create an ID here."""


class AmbiguousTeamError(TeamMasterError):
    """A name needs a date or does not identify exactly one registered club."""


def _date(value, *, field: str, allow_blank: bool = False) -> date | None:
    if allow_blank and (value is None or value == ""):
        return None
    if isinstance(value, str):
        if re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
            try:
                return date.fromisoformat(value)
            except ValueError:
                pass
    elif isinstance(value, datetime):
        if not pd.isna(value) and value.tzinfo is None and value.time() == time.min and not getattr(value, "nanosecond", 0):
            return value.date()
    elif isinstance(value, date):
        return value
    raise TeamMasterError(f"{field}: expected YYYY-MM-DD or a timezone-naive date at midnight.")


def _text(value, *, field: str, optional: bool = False) -> str:
    if not isinstance(value, str) or (not value and not optional):
        raise TeamMasterError(f"{field}: expected a nonempty string.")
    if value != value.strip() or any(ord(char) < 32 for char in value):
        raise TeamMasterError(f"{field}: surrounding whitespace/control characters are not allowed.")
    return value


@dataclass(frozen=True)
class TeamAlias:
    team_id: str
    canonical_name: str
    source_name: str
    source: str
    valid_from: date | None
    valid_to: date | None
    source_club_id: str


class TeamMaster:
    """A validated, read-only registry of exact aliases and inclusive date ranges."""

    def __init__(self, aliases):
        aliases = tuple(aliases)
        if not aliases:
            raise TeamMasterError("Team master must contain at least one alias.")
        by_name = defaultdict(list)
        canonical_names, external_ids = {}, {}
        for alias in aliases:
            if not isinstance(alias, TeamAlias):
                raise TeamMasterError("Expected TeamAlias records.")
            for field in ("team_id", "canonical_name", "source_name", "source"):
                _text(getattr(alias, field), field=field)
            _text(alias.source_club_id, field="source_club_id", optional=True)
            if re.fullmatch(r"team_[0-9]{4,}", alias.team_id) is None or int(alias.team_id[5:]) == 0:
                raise TeamMasterError(f"Invalid permanent team_id: {alias.team_id!r}.")
            if re.fullmatch(r"[a-z][a-z0-9_]*", alias.source) is None:
                raise TeamMasterError(f"Invalid source namespace: {alias.source!r}.")
            # Direct construction has the same date contract as CSV loading.
            if any(value is not None and type(value) is not date for value in (alias.valid_from, alias.valid_to)):
                raise TeamMasterError("Alias interval endpoints must be date or None.")
            start, end = alias.valid_from or date.min, alias.valid_to or date.max
            if start > end:
                raise TeamMasterError(f"Reversed alias interval: {alias.source_name!r}.")
            if canonical_names.setdefault(alias.team_id, alias.canonical_name) != alias.canonical_name:
                raise TeamMasterError(f"Conflicting canonical_name for {alias.team_id}.")
            if alias.source_club_id:
                external = (alias.source, alias.source_club_id)
                if external_ids.setdefault(external, alias.team_id) != alias.team_id:
                    raise TeamMasterError(f"Source club identity assigned to multiple team_ids: {external}.")
            key = (alias.source, alias.source_name)
            for previous in by_name[key]:
                if start <= (previous.valid_to or date.max) and (previous.valid_from or date.min) <= end:
                    raise TeamMasterError(f"Duplicate or overlapping alias intervals: {key}.")
            by_name[key].append(alias)
        self._aliases = aliases
        self._by_name = {key: tuple(values) for key, values in by_name.items()}
        self._team_count = len(canonical_names)

    @property
    def aliases(self) -> tuple[TeamAlias, ...]:
        return self._aliases

    @property
    def team_count(self) -> int:
        return self._team_count

    def resolve_team_id(self, source_name: str, *, source: str = DEFAULT_SOURCE, on=None) -> str:
        """Resolve an exact spelling; a bounded alias requires an explicit date.

        The default source is Data Site. No trimming, Unicode normalization,
        fuzzy matching, canonical-name fallback, or automatic IDs are applied.
        """
        if not isinstance(source_name, str) or not source_name or not isinstance(source, str) or not source:
            raise UnknownTeamError("Club name and source must be nonempty strings.")
        observed_date = _date(on, field="on") if on is not None else None
        aliases = self._by_name.get((source, source_name), ())
        if not aliases:
            raise UnknownTeamError(f"Unknown team alias: source={source!r}, source_name={source_name!r}.")
        if observed_date is None:
            if any(alias.valid_from is not None or alias.valid_to is not None for alias in aliases):
                raise AmbiguousTeamError(f"An explicit match date is required for {source_name!r}.")
        else:
            aliases = tuple(alias for alias in aliases if (alias.valid_from or date.min) <= observed_date <= (alias.valid_to or date.max))
        if not aliases:
            raise UnknownTeamError(f"No team alias valid on {observed_date}: {source!r}/{source_name!r}.")
        if len(aliases) != 1:
            raise AmbiguousTeamError(f"Ambiguous team alias: {source!r}/{source_name!r}.")
        return aliases[0].team_id

    def add_team_ids(self, matches: pd.DataFrame, *, source: str = DEFAULT_SOURCE) -> pd.DataFrame:
        """Return a copy with home/away IDs; leave all original values untouched."""
        if not isinstance(matches, pd.DataFrame) or not matches.columns.is_unique:
            raise TeamMasterError("Expected a DataFrame with unique columns.")
        missing = {"home_team", "away_team"} - set(matches.columns)
        if missing:
            raise TeamMasterError(f"Missing match name columns: {sorted(missing)}.")
        if {"home_team_id", "away_team_id"} & set(matches.columns):
            raise TeamMasterError("Team ID output columns already exist; refusing to overwrite them.")
        dates = matches["match_date"].tolist() if "match_date" in matches else [None] * len(matches)
        additions = {}
        for side in ("home", "away"):
            ids = []
            for position, (name, day) in enumerate(zip(matches[f"{side}_team"], dates), 1):
                try:
                    ids.append(self.resolve_team_id(name, source=source, on=day))
                except TeamMasterError as exc:
                    raise type(exc)(f"{side}_team at data row {position}: {exc}") from exc
            additions[f"{side}_team_id"] = ids
        result = matches.copy(deep=True)
        for column, ids in additions.items():
            result[column] = ids
        return result


def load_team_master(path: str | Path = DEFAULT_TEAM_MASTER_PATH) -> TeamMaster:
    """Read the UTF-8 alias registry and reject malformed or ambiguous mappings."""
    aliases = []
    try:
        with Path(path).open(encoding="utf-8-sig", newline="") as source:
            reader = csv.reader(source, strict=True)
            columns = next(reader, [])
            if len(columns) != len(set(columns)) or set(columns) != set(MASTER_COLUMNS):
                raise TeamMasterError(f"Expected exactly the master columns: {MASTER_COLUMNS}.")
            for position, values in enumerate(reader, 2):
                if len(values) != len(columns):
                    raise TeamMasterError(f"Master CSV line {position}: incorrect number of fields.")
                row = dict(zip(columns, values))
                row["valid_from"] = _date(row["valid_from"], field=f"line {position} valid_from", allow_blank=True)
                row["valid_to"] = _date(row["valid_to"], field=f"line {position} valid_to", allow_blank=True)
                aliases.append(TeamAlias(**row))
    except csv.Error as exc:
        raise TeamMasterError(f"Invalid team master CSV: {exc}") from exc
    return TeamMaster(aliases)
