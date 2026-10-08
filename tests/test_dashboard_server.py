"""Synthetic checks for the read-only, Champion-only local dashboard server."""

from copy import deepcopy
import json
from pathlib import Path
from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from scripts.serve_dashboard import (
    CHAMPION_MODEL,
    DashboardDataError,
    STATIC_ROUTES,
    create_server,
    empty_dashboard,
    load_dashboard_data,
    main,
    validate_dashboard_data,
)


@pytest.fixture
def payload():
    data = empty_dashboard()
    data["updatedAt"] = "2026-10-01T09:00:00+09:00"
    match = {
        "id": "synthetic-previous-1",
        "homeTeam": {"id": "team_0001", "name": "Synthetic Home"},
        "awayTeam": {"id": "team_0002", "name": "Synthetic Away"},
        "kickoffAt": "2026-09-30T19:00:00+09:00",
        "prediction": {
            "source": "saved_pre_match",
            "generatedAt": "2026-09-29T12:00:00Z",
            "probabilities": {"home": 31, "draw": 25, "away": 44},
        },
        "result": {"homeScore": 1, "awayScore": 2},
    }
    data["previousRound"]["matches"] = [match]
    future = deepcopy(match)
    del future["result"]
    future["id"] = "synthetic-next-1"
    future["kickoffAt"] = "2026-10-02T19:00:00+09:00"
    data["nextRound"]["matches"] = [future]
    return data


@pytest.fixture
def running_server(tmp_path, payload):
    for relative, _ in STATIC_ROUTES.values():
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f"synthetic asset: {relative}", encoding="utf-8")
    # A file outside the static allowlist must never be exposed.
    (tmp_path / "secret.json").write_text("not public", encoding="utf-8")
    server = create_server(payload, port=0, static_root=tmp_path)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}", server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_absent_data_returns_empty_without_opening_files(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Default dashboard must not read prediction/history/research files")

    monkeypatch.setattr(Path, "read_text", forbidden)
    data = load_dashboard_data()
    assert data == empty_dashboard()
    assert data["model"] == CHAMPION_MODEL
    assert data["previousRound"]["matches"] == []
    assert data["nextRound"]["matches"] == []


def test_empty_defaults_are_independent():
    one = empty_dashboard()
    one["model"]["name"] = "mutated"
    one["previousRound"]["matches"].append({})
    assert empty_dashboard()["model"] == CHAMPION_MODEL
    assert empty_dashboard()["previousRound"]["matches"] == []


def test_valid_saved_champion_payload_unchanged(payload):
    before = deepcopy(payload)
    assert validate_dashboard_data(payload) is payload
    assert payload == before


@pytest.mark.parametrize("probabilities", [
    {"home": 0, "draw": 0, "away": 100},
    {"home": 0.01, "draw": 49.99, "away": 50},
    {"home": 33.33, "draw": 33.33, "away": 33.33},
    {"home": 31, "draw": 25, "away": 44},
])
def test_valid_probability_edge_cases_not_normalized(payload, probabilities):
    payload["nextRound"]["matches"][0]["prediction"]["probabilities"] = probabilities
    validate_dashboard_data(payload)
    assert payload["nextRound"]["matches"][0]["prediction"]["probabilities"] is probabilities


@pytest.mark.parametrize("probabilities", [
    {"home": -1, "draw": 25, "away": 76},
    {"home": 101, "draw": 0, "away": -1},
    {"home": float("nan"), "draw": 25, "away": 44},
    {"home": float("inf"), "draw": 25, "away": 44},
    {"home": 10**400, "draw": 25, "away": 44},
    {"home": True, "draw": 25, "away": 74},
    {"home": "31", "draw": 25, "away": 44},
    {"home": 31, "draw": 25, "away": 43},
    {"home": 31, "draw": 25},
    {"home": 31, "draw": 25, "away": 44, "st2Draw": 27},
])
def test_invalid_probabilities_rejected(payload, probabilities):
    payload["nextRound"]["matches"][0]["prediction"]["probabilities"] = probabilities
    with pytest.raises(DashboardDataError):
        validate_dashboard_data(payload)


@pytest.mark.parametrize("field,value", [
    ("schemaVersion", True),
    ("schemaVersion", 2),
    ("mode", "demo"),
    ("mode", "research"),
    ("model", {"name": "ST2", "version": CHAMPION_MODEL["version"]}),
    ("model", {"name": "Champion A", "version": "alternative"}),
    ("model", {**CHAMPION_MODEL, "challenger": "ST2"}),
    ("updatedAt", "2026-10-01"),
    ("updatedAt", "2026-10-01T10:00:00"),
    ("updatedAt", "2026-99-01T10:00:00Z"),
])
def test_reject_nonoperational_contract(payload, field, value):
    payload[field] = value
    with pytest.raises(DashboardDataError):
        validate_dashboard_data(payload)


@pytest.mark.parametrize("location", ["top", "round", "match", "team", "prediction", "result"])
def test_research_extras_rejected_recursively(payload, location):
    match = payload["previousRound"]["matches"][0]
    target = {
        "top": payload,
        "round": payload["previousRound"],
        "match": match,
        "team": match["homeTeam"],
        "prediction": match["prediction"],
        "result": match["result"],
    }[location]
    target["researchPerformance"] = {"ST2": {"accuracy": 1}}
    with pytest.raises(DashboardDataError):
        validate_dashboard_data(payload)


@pytest.mark.parametrize("source", ["regenerated", "ST2", "live_prediction", None])
def test_only_saved_prediction_source_permitted(payload, source):
    payload["nextRound"]["matches"][0]["prediction"]["source"] = source
    with pytest.raises(DashboardDataError, match="saved_pre_match"):
        validate_dashboard_data(payload)


@pytest.mark.parametrize("timestamp", [
    "2026-10-02T19:00:00+09:00",  # Exactly kickoff.
    "2026-10-02T10:00:01Z",  # After kickoff, accounting for offset.
    "2026-10-02T10:00:00",  # No timezone.
    "2026-02-30T10:00:00Z",  # Invalid date.
    "2026-10-01T10:00Z",  # Seconds are required by the client contract.
])
def test_reject_non_prematch_prediction_time(payload, timestamp):
    payload["nextRound"]["matches"][0]["prediction"]["generatedAt"] = timestamp
    with pytest.raises(DashboardDataError):
        validate_dashboard_data(payload)


def test_next_round_cannot_have_outcomes(payload):
    payload["nextRound"]["matches"][0]["result"] = {"homeScore": 0, "awayScore": 0}
    with pytest.raises(DashboardDataError):
        validate_dashboard_data(payload)


@pytest.mark.parametrize("score", [-1, 1.5, True, "1", 2**53])
def test_previous_scores_must_be_nonnegative_integers(payload, score):
    payload["previousRound"]["matches"][0]["result"]["homeScore"] = score
    with pytest.raises(DashboardDataError):
        validate_dashboard_data(payload)


@pytest.mark.parametrize("location", ["label", "id", "teamName"])
def test_text_fields_longer_than_client_bound_rejected(payload, location):
    match = payload["nextRound"]["matches"][0]
    if location == "label":
        payload["nextRound"]["label"] = "x" * 201
    elif location == "id":
        match["id"] = "x" * 201
    else:
        match["homeTeam"]["name"] = "x" * 201
    with pytest.raises(DashboardDataError, match="200"):
        validate_dashboard_data(payload)


def test_more_than_100_matches_rejected(payload):
    template = payload["nextRound"]["matches"][0]
    payload["nextRound"]["matches"] = [
        {**deepcopy(template), "id": f"synthetic-next-{index}"}
        for index in range(101)
    ]
    with pytest.raises(DashboardDataError, match="100"):
        validate_dashboard_data(payload)


def test_exact_client_bounds_are_accepted(payload):
    payload["nextRound"]["label"] = "x" * 200
    template = payload["nextRound"]["matches"][0]
    template["homeTeam"]["name"] = "x" * 200
    template["prediction"]["generatedAt"] = "2026-10-01T10:00:00.123456Z"
    payload["nextRound"]["matches"] = [
        {**deepcopy(template), "id": f"{index:03d}" + "x" * 197}
        for index in range(100)
    ]
    payload["previousRound"]["matches"][0]["result"]["homeScore"] = 2**53 - 1
    assert validate_dashboard_data(payload) is payload


def test_duplicate_ids_rejected_across_sections(payload):
    payload["nextRound"]["matches"][0]["id"] = payload["previousRound"]["matches"][0]["id"]
    with pytest.raises(DashboardDataError, match="duplicate"):
        validate_dashboard_data(payload)


@pytest.mark.parametrize("identity", ["ST2", "team_1", "team_0001"])
def test_invalid_or_same_team_rejected(payload, identity):
    payload["nextRound"]["matches"][0]["awayTeam"]["id"] = identity
    with pytest.raises(DashboardDataError):
        validate_dashboard_data(payload)


def test_explicit_json_read_only_and_no_normalization(tmp_path, payload):
    path = tmp_path / "prepared.json"
    encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    path.write_bytes(encoded)
    assert load_dashboard_data(path) == payload
    assert path.read_bytes() == encoded


def test_reject_raw_csv_input(tmp_path):
    path = tmp_path / "prospective.csv"
    path.write_text("never read this csv", encoding="utf-8")
    with pytest.raises(DashboardDataError, match=".json"):
        load_dashboard_data(path)


def test_reject_duplicate_json_keys(tmp_path):
    path = tmp_path / "duplicate.json"
    path.write_text('{"mode":"operational","mode":"research"}', encoding="utf-8")
    with pytest.raises(DashboardDataError, match="duplicate JSON key"):
        load_dashboard_data(path)


def test_bad_input_fails_before_binding_server(tmp_path, monkeypatch, capsys):
    path = tmp_path / "research.json"
    path.write_text('{"model":"ST2"}', encoding="utf-8")

    def forbidden(*args, **kwargs):
        pytest.fail("Invalid JSON must stop before binding a server")

    monkeypatch.setattr("scripts.serve_dashboard.create_server", forbidden)
    assert main(["--data", str(path)]) == 2
    assert "startup rejected" in capsys.readouterr().err


def test_api_returns_validated_saved_payload(running_server, payload):
    base, server = running_server
    assert server.server_address[0] == "127.0.0.1"
    with urlopen(f"{base}/api/dashboard", timeout=2) as response:
        assert response.headers["Content-Type"] == "application/json; charset=utf-8"
        assert response.headers["Cache-Control"] == "no-store"
        assert json.load(response) == payload


def test_server_api_is_startup_snapshot(running_server, payload):
    base, _ = running_server
    payload["model"]["name"] = "mutated"
    with urlopen(f"{base}/api/dashboard", timeout=2) as response:
        assert json.load(response)["model"] == CHAMPION_MODEL


@pytest.mark.parametrize("route", list(STATIC_ROUTES))
def test_only_allowlisted_static_routes(running_server, route):
    base, _ = running_server
    with urlopen(f"{base}{route}?cache=1", timeout=2) as response:
        assert response.status == 200
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert response.read().startswith(b"synthetic asset:")


@pytest.mark.parametrize("route", [
    "/secret.json",
    "/data/processed/predictions/season_transition_st2_prospective.csv",
    "/models/",
    "/../secret.json",
    "/%2e%2e/secret.json",
    "/components/../secret.json",
    "/%252e%252e/secret.json",
    "/tests/test_dashboard_server.py",
])
def test_traversal_repository_and_unlisted_files_not_exposed(running_server, route):
    base, _ = running_server
    with pytest.raises(HTTPError) as exc:
        urlopen(f"{base}{route}", timeout=2)
    assert exc.value.code == 404


@pytest.mark.parametrize("method", ["HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
def test_mutations_and_non_get_requests_rejected(running_server, method):
    base, _ = running_server
    with pytest.raises(HTTPError) as exc:
        urlopen(Request(f"{base}/api/dashboard", method=method), timeout=2)
    assert exc.value.code == 405
    assert exc.value.headers["Allow"] == "GET"
