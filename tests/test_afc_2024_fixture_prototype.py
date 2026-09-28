from pathlib import Path

import pytest

from src.collect.afc_2024_fixture_prototype import (
    DEFAULT_FIXTURES,
    IDENTITY_TYPE,
    build_fixtures,
    make_derived_fixture_key,
    render_audit_markdown,
    validate_rows,
)


def test_default_scope_and_counts():
    rows = build_fixtures()
    assert len(rows) == 34
    assert {row["j1_team_id"] for row in rows} == {"team_0006", "team_0010", "team_0011", "team_0033"}
    assert all(row["match_date"].startswith("2024-") for row in rows)


def test_identity_is_explicitly_derived_and_unique():
    rows = build_fixtures()
    keys = [row["match_key"] for row in rows]
    assert len(keys) == len(set(keys))
    assert all(row["identity_type"] == IDENTITY_TYPE for row in rows)
    assert all(row["source_match_id"] is None for row in rows)


def test_same_club_same_day_invariant():
    rows = build_fixtures()
    assert len({(row["j1_team_id"], row["match_date"]) for row in rows}) == len(rows)


def test_exact_team_resolution_has_no_unknown_ids():
    assert all(row["j1_team_id"].startswith("team_") for row in build_fixtures())


def test_provenance_is_complete_except_explicit_date_gate():
    rows = build_fixtures()
    assert all(row["source_url"].startswith("https://assets.the-afc.com/") for row in rows)
    assert all(len(row["raw_sha256"]) == 64 for row in rows)
    assert all(row["provenance_status"] == "date_unresolved" for row in rows)


def test_validate_rejects_key_collision():
    rows = build_fixtures()[:2]
    rows[1] = dict(rows[1], match_key=rows[0]["match_key"])
    with pytest.raises(ValueError, match="collision"):
        validate_rows(rows)


def test_key_uses_only_declared_identity_fields():
    key = make_derived_fixture_key("AFC Test", "2024-01-02", "Home FC", "Away FC", "MD1")
    assert key == "afc:derived:afc-test:2024-01-02:home-fc:away-fc:md1"


def test_audit_is_deterministic_and_fail_closed(tmp_path: Path):
    rows = build_fixtures()
    first = tmp_path / "first.md"
    second = tmp_path / "second.md"
    assert render_audit_markdown(rows, output_path=first) == "BLOCKED_AFC_DATE_PROVENANCE"
    assert render_audit_markdown(rows, output_path=second) == "BLOCKED_AFC_DATE_PROVENANCE"
    assert first.read_text(encoding="utf-8") == second.read_text(encoding="utf-8")
    assert "34" in first.read_text(encoding="utf-8")


def test_no_third_party_source_types():
    assert {row["source_type"] for row in build_fixtures()} == {"official_afc_schedule_pdf"}


def test_fixture_manifest_is_immutable_tuple():
    assert isinstance(DEFAULT_FIXTURES, tuple)
