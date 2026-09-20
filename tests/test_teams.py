"""Stable club identity resolution, without modifying source match data."""

import csv
from dataclasses import FrozenInstanceError
from datetime import date, datetime, timezone
from pathlib import Path
import re

import pandas as pd
import pytest

from src.collect.jleague_ongoing import read_latest
from src.collect.teams import (
    AmbiguousTeamError,
    TeamMasterError,
    UnknownTeamError,
    load_team_master,
)


ROOT = Path(__file__).resolve().parents[1]
COLUMNS = (
    "team_id", "canonical_name", "source_name", "source", "valid_from",
    "valid_to", "source_club_id",
)


def alias(name="Club A", *, team_id="team_0001", canonical="Club Alpha",
          source="jleague_data_site", valid_from="", valid_to="",
          club_id="alpha"):
    return {
        "team_id": team_id,
        "canonical_name": canonical,
        "source_name": name,
        "source": source,
        "valid_from": valid_from,
        "valid_to": valid_to,
        "source_club_id": club_id,
    }


def write_master(tmp_path, rows, *, columns=COLUMNS):
    path = tmp_path / "teams.csv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(columns)
        writer.writerows([row.get(column, "") for column in columns] for row in rows)
    return path


@pytest.fixture
def master(tmp_path):
    return load_team_master(write_master(tmp_path, [
        alias(),
        alias("Former Club A"),
        alias("Club B", team_id="team_0002", canonical="Club Beta", club_id="beta"),
    ]))


def test_multiple_aliases_and_source_namespaces_keep_stable_identity(tmp_path):
    master = load_team_master(write_master(tmp_path, [
        alias(), alias("Former Club A"),
        alias("Club A", team_id="team_0002", canonical="Club Beta",
              source="another_source", club_id="alpha"),
    ]))

    assert master.team_count == 2
    assert master.resolve_team_id("Club A") == "team_0001"
    assert master.resolve_team_id("Former Club A") == "team_0001"
    assert master.resolve_team_id("Club A", source="another_source") == "team_0002"
    assert isinstance(master.aliases, tuple)
    assert master.aliases[0].source_club_id == "alpha"
    with pytest.raises(FrozenInstanceError):
        master.aliases[0].team_id = "team_9999"


def test_omiya_historical_official_alias_is_date_bounded():
    master = load_team_master(ROOT / "data/master/teams.csv")
    assert master.resolve_team_id("大宮アルディージャ", source="jleague_official", on="2016-03-05") == "team_0022"
    with pytest.raises(UnknownTeamError):
        master.resolve_team_id("大宮アルディージャ", source="jleague_official", on="2025-01-01")
    assert master.resolve_team_id("ＲＢ大宮アルディージャ", source="jleague_official", on="2025-01-01") == "team_0022"


@pytest.mark.parametrize("name,source", [
    ("Unknown Club", "jleague_data_site"),
    ("Club A", "unknown_source"),
    (" Club A", "jleague_data_site"),
    ("Club A ", "jleague_data_site"),
    ("Ｃlub A", "jleague_data_site"),
])
def test_unknown_names_are_not_normalized_or_assigned_an_id(master, name, source):
    with pytest.raises(UnknownTeamError):
        master.resolve_team_id(name, source=source)
    assert master.team_count == 2


def test_rename_preserves_id_and_period_boundaries_are_inclusive(tmp_path):
    master = load_team_master(write_master(tmp_path, [
        alias("Old Club", valid_to="2020-12-31"),
        alias("New Club", valid_from="2021-01-01", club_id="new-alpha"),
    ]))

    assert master.team_count == 1
    assert master.resolve_team_id("Old Club", on="2020-12-31") == "team_0001"
    assert master.resolve_team_id("New Club", on="2021-01-01") == "team_0001"
    assert {entry.canonical_name for entry in master.aliases} == {"Club Alpha"}
    assert master.aliases[0].valid_to == date(2020, 12, 31)
    assert master.aliases[1].valid_from == date(2021, 1, 1)
    for name, on in [("Old Club", "2021-01-01"), ("New Club", "2020-12-31")]:
        with pytest.raises(UnknownTeamError):
            master.resolve_team_id(name, on=on)
    with pytest.raises(AmbiguousTeamError):
        master.resolve_team_id("Old Club")


def test_reused_name_requires_date_and_resolves_to_distinct_clubs(tmp_path):
    master = load_team_master(write_master(tmp_path, [
        alias(valid_to="2020-12-31"),
        alias(team_id="team_0002", canonical="Club Beta", club_id="beta",
              valid_from="2021-01-01"),
    ]))

    with pytest.raises(AmbiguousTeamError):
        master.resolve_team_id("Club A")
    assert master.resolve_team_id("Club A", on="2020-12-31") == "team_0001"
    assert master.resolve_team_id("Club A", on="2021-01-01") == "team_0002"


@pytest.mark.parametrize("on", [
    "2026-09-16", date(2026, 9, 16), datetime(2026, 9, 16),
    pd.Timestamp("2026-09-16"),
])
def test_supported_match_date_types(master, on):
    assert master.resolve_team_id("Club A", on=on) == "team_0001"


@pytest.mark.parametrize("on", [
    "2026/09/16", "2026-02-30", "2026-09-16T00:00:00", 20260916,
    datetime(2026, 9, 16, 12), datetime(2026, 9, 16, tzinfo=timezone.utc),
    pd.Timestamp("2026-09-16T00:00:00+09:00"), pd.NaT,
])
def test_invalid_dates_never_silently_choose_alias(master, on):
    with pytest.raises(TeamMasterError):
        master.resolve_team_id("Club A", on=on)


@pytest.mark.parametrize("field,value", [
    ("team_id", ""), ("team_id", "alpha"), ("team_id", "team_1"),
    ("canonical_name", ""), ("source_name", ""), ("source", ""),
    ("valid_from", "2021/01/01"), ("valid_to", "2021-02-30"),
])
def test_invalid_master_values_are_rejected(tmp_path, field, value):
    row = alias()
    row[field] = value
    with pytest.raises(TeamMasterError):
        load_team_master(write_master(tmp_path, [row]))


def test_inverted_validity_period_is_rejected(tmp_path):
    with pytest.raises(TeamMasterError):
        load_team_master(write_master(tmp_path, [
            alias(valid_from="2021-01-01", valid_to="2020-12-31"),
        ]))


@pytest.mark.parametrize("rows", [
    [alias(), alias()],
    [alias(valid_to="2020-12-31"), alias(valid_from="2020-12-31")],
    [alias(), alias(team_id="team_0002", canonical="Club Beta", club_id="beta")],
])
def test_duplicate_or_overlapping_name_periods_are_rejected(tmp_path, rows):
    with pytest.raises(TeamMasterError):
        load_team_master(write_master(tmp_path, rows))


def test_single_team_cannot_have_conflicting_canonical_names(tmp_path):
    with pytest.raises(TeamMasterError):
        load_team_master(write_master(tmp_path, [
            alias(), alias("Former Club A", canonical="Another Canonical Name"),
        ]))


def test_external_identity_cannot_point_to_two_teams(tmp_path):
    with pytest.raises(TeamMasterError):
        load_team_master(write_master(tmp_path, [
            alias(), alias("Club B", team_id="team_0002", canonical="Club Beta"),
        ]))


@pytest.mark.parametrize("columns", [COLUMNS[:-1], (*COLUMNS, "source_name")])
def test_missing_or_duplicate_headers_are_rejected(tmp_path, columns):
    with pytest.raises(TeamMasterError):
        load_team_master(write_master(tmp_path, [alias()], columns=columns))


def test_empty_master_is_rejected(tmp_path):
    with pytest.raises(TeamMasterError):
        load_team_master(write_master(tmp_path, []))


def test_malformed_csv_row_is_rejected(tmp_path):
    path = tmp_path / "teams.csv"
    path.write_text(
        ",".join(COLUMNS) + "\nteam_0001,Club Alpha,Club A\n", encoding="utf-8",
    )
    with pytest.raises(TeamMasterError):
        load_team_master(path)


def test_add_team_ids_preserves_names_columns_index_order_and_input(master):
    matches = pd.DataFrame({
        "match_id": ["m2", "m1"],
        "match_date": ["2026-09-16", "2015-03-07"],
        "home_team": ["Former Club A", "Club B"],
        "away_team": ["Club B", "Club A"],
        "extra": [None, "keep this"],
    }, index=pd.Index([7, 7], name="original_index"))
    before = matches.copy(deep=True)

    resolved = master.add_team_ids(matches)

    assert resolved is not matches
    pd.testing.assert_frame_equal(matches, before)
    pd.testing.assert_frame_equal(resolved[list(matches.columns)], before)
    assert resolved["home_team_id"].tolist() == ["team_0001", "team_0002"]
    assert resolved["away_team_id"].tolist() == ["team_0002", "team_0001"]


def test_add_team_ids_uses_each_match_date_for_renamed_club(tmp_path):
    master = load_team_master(write_master(tmp_path, [
        alias("Old Club", valid_to="2020-12-31"),
        alias("New Club", valid_from="2021-01-01"),
        alias("Club B", team_id="team_0002", canonical="Club Beta", club_id="beta"),
    ]))
    matches = pd.DataFrame({
        "match_date": pd.to_datetime(["2020-12-31", "2021-01-01"]),
        "home_team": ["Old Club", "New Club"],
        "away_team": ["Club B", "Club B"],
    })
    assert master.add_team_ids(matches)["home_team_id"].tolist() == [
        "team_0001", "team_0001",
    ]


@pytest.mark.parametrize("column", ["home_team_id", "away_team_id"])
def test_existing_id_columns_are_not_overwritten(master, column):
    matches = pd.DataFrame({"home_team": ["Club A"], "away_team": ["Club B"],
                            column: ["existing-value"]})
    before = matches.copy(deep=True)
    with pytest.raises(TeamMasterError):
        master.add_team_ids(matches)
    pd.testing.assert_frame_equal(matches, before)


@pytest.mark.parametrize("missing", ["home_team", "away_team"])
def test_missing_team_column_is_rejected(master, missing):
    matches = pd.DataFrame({"home_team": ["Club A"], "away_team": ["Club B"]})
    with pytest.raises(TeamMasterError):
        master.add_team_ids(matches.drop(columns=missing))


def test_unknown_club_fails_without_partial_input_mutation(master):
    matches = pd.DataFrame({
        "home_team": ["Club A", "Unknown Club"], "away_team": ["Club B", "Club B"],
    })
    before = matches.copy(deep=True)
    with pytest.raises(UnknownTeamError):
        master.add_team_ids(matches)
    pd.testing.assert_frame_equal(matches, before)


def test_committed_master_registers_33_stable_clubs():
    master = load_team_master()
    # These identities are a permanent allocation, not a CSV-derived expectation.
    # Registering a new club must never renumber any existing club.
    expected_ids = {
        "千葉": "team_0001", "Ｃ大阪": "team_0002", "FC東京": "team_0003",
        "福岡": "team_0004", "Ｇ大阪": "team_0005", "広島": "team_0006",
        "磐田": "team_0007", "鹿島": "team_0008", "柏": "team_0009",
        "川崎Ｆ": "team_0010", "神戸": "team_0011", "甲府": "team_0012",
        "京都": "team_0013", "町田": "team_0014", "松本": "team_0015",
        "水戸": "team_0016", "長崎": "team_0017", "名古屋": "team_0018",
        "新潟": "team_0019", "大分": "team_0020", "岡山": "team_0021",
        "大宮": "team_0022", "札幌": "team_0023", "仙台": "team_0024",
        "清水": "team_0025", "湘南": "team_0026", "徳島": "team_0027",
        "東京Ｖ": "team_0028", "鳥栖": "team_0029", "浦和": "team_0030",
        "山形": "team_0031", "横浜FC": "team_0032", "横浜FM": "team_0033",
    }
    assert {name: master.resolve_team_id(name) for name in expected_ids} == expected_ids
    assert master.team_count == 33
    assert len({entry.team_id for entry in master.aliases}) == 33
    assert all(re.fullmatch(r"team_[0-9]{4}", entry.team_id) for entry in master.aliases)
    for entry in master.aliases:
        on = date(2016, 3, 5) if entry.valid_from is not None or entry.valid_to is not None else None
        assert master.resolve_team_id(entry.source_name, source=entry.source, on=on) == entry.team_id


def test_all_available_match_outputs_resolve_without_changes():
    base = ROOT / "data/processed/jleague"
    paths = [base / f"{year}_matches_probe.csv" for year in range(2015, 2026)]
    paths += [base / "2026_hyakunen/matches.csv", base / "2026_27/schedule.csv"]
    latest = read_latest(base / "2026_27")
    if latest is not None:
        revision, _ = latest
        paths[-1] = revision / "schedule.csv"
    available = [path for path in paths if path.exists()]
    if not available:
        pytest.skip("Downloaded match outputs are optional; synthetic coverage runs offline.")
    master = load_team_master()

    def verify_output(path):
        before = path.read_bytes()
        matches = pd.read_csv(path, dtype={"match_id": "string"})
        resolved = master.add_team_ids(matches)
        pd.testing.assert_frame_equal(resolved[list(matches.columns)], matches)
        assert resolved[["home_team_id", "away_team_id"]].notna().all().all(), path
        assert resolved["home_team_id"].ne(resolved["away_team_id"]).all(), path
        assert path.read_bytes() == before
        return len(matches)

    total_rows = sum(verify_output(path) for path in available)
    if len(available) == len(paths):
        assert total_rows == 4168
    if latest is not None:
        # Completed matches are already included in schedule: resolve them too,
        # without counting them a second time in the distinct-fixture total.
        verify_output(revision / "completed_matches.csv")
        for name in ("schedule.csv", "completed_matches.csv"):
            projection = base / "2026_27" / name
            if projection.exists():
                verify_output(projection)
