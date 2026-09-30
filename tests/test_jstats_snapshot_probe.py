"""Offline contracts for the one-request J Stats source-state probe."""

from datetime import datetime, timezone
import json
from pathlib import Path

import pytest

from src.collect import jstats_snapshot_registry as registry
from src.collect.jstats_snapshot_probe import (
    ADVANCED,
    PROBE_URL,
    REGRESSED,
    UNCHANGED,
    UNKNOWN,
    classify_source_state,
    probe_source_state,
    run_capture_gate,
)
from src.collect.jstats_team_snapshots import FULL_STATS, STATS, expected_club_slugs
from src.collect.teams import load_team_master


MASTER = load_team_master()
SLUGS = expected_club_slugs()
IDENTITIES = sorted(
    (alias.source_club_id, alias.source_name, alias.team_id)
    for alias in MASTER.aliases
    if alias.source == "jleague_official"
    and alias.source_club_id in SLUGS
    and alias.valid_from is None
    and alias.valid_to is None
)


def fixture_html(*, source_date="2026/9/28", count=20):
    stat = STATS[0]
    records = [
        {
            "href": f"/club/{slug}",
            "club": {"code": slug, "name": name},
            "name": name,
            "score": "1.20",
        }
        for slug, name, _ in IDENTITIES[:count]
    ]
    ranking = {
        "id": f"ranking-{stat.slug}",
        "category": "j1",
        "year": "2026",
        "stats": {"value": stat.slug, "label": stat.label},
        "data": records,
    }
    payload = "8:" + json.dumps({"rankingList": [ranking]}, ensure_ascii=False)
    script = json.dumps([1, payload], ensure_ascii=False)
    visible = "".join(
        f'<a class="m-ranking-club-list-item__link" href="/club/{row["club"]["code"]}/">'
        f'<div class="m-ranking-club-list-item" name="{row["name"]}" '
        f'score="{row["score"]}"></div></a>'
        for row in records[:10]
    )
    update = f"{source_date} 更新" if source_date else ""
    return (
        f"<html><head><title>2026/27 J1</title></head><body>{update}{visible}"
        f"<script>self.__next_f.push({script})</script></body></html>"
    ).encode()


def report(day="2026-09-21"):
    state = registry.LogicalFullState(
        season="2026-27",
        source_state_date=day,
        profile="FULL_37",
        kind="PHYSICAL",
        snapshot_ids=("saved",),
        stat_names=tuple(stat.slug for stat in FULL_STATS),
        team_ids=tuple(sorted(identity[2] for identity in IDENTITIES)),
    )
    return registry.RegistryReport((), (state,), ())


def run_probe(tmp_path, *, source_date="2026/9/28", saved_date="2026-09-21", **fetch_changes):
    calls = []

    def fetch(url):
        calls.append(url)
        return (
            fixture_html(source_date=source_date, count=fetch_changes.get("count", 20)),
            fetch_changes.get("http_status", 200),
            fetch_changes.get("final_url", url),
            fetch_changes.get("content_type", "text/html; charset=utf-8"),
        )

    result = probe_source_state(
        raw_root=tmp_path / "probes",
        now=datetime(2026, 9, 30, 1, 2, 3, tzinfo=timezone.utc),
        fetch=fetch,
        registry_report=report(saved_date),
        master=MASTER,
    )
    return result, calls


def test_probe_makes_one_exact_request_and_validates_20_clubs_date_and_provenance(tmp_path):
    result, calls = run_probe(tmp_path)
    assert calls == [PROBE_URL]
    assert result.request_count == 1
    assert result.parsed_clubs == 20
    assert result.source_state_date == "2026-09-28"
    assert result.latest_saved_source_state_date == "2026-09-21"
    assert result.status == ADVANCED
    assert len(result.raw_sha256) == 64
    manifest = json.loads((Path(result.raw_dir) / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["requested_url"] == PROBE_URL
    assert manifest["retrieved_at"] == "2026-09-30T01:02:03Z"
    assert manifest["raw_sha256"] == result.raw_sha256
    assert (Path(result.raw_dir) / "shoot.html").is_file()


@pytest.mark.parametrize(
    ("observed", "latest", "expected"),
    [
        ("2026-09-28", "2026-09-21", ADVANCED),
        ("2026-09-21", "2026-09-21", UNCHANGED),
        ("2026-09-14", "2026-09-21", REGRESSED),
        (None, "2026-09-21", UNKNOWN),
        ("2026-09-28", None, UNKNOWN),
    ],
)
def test_source_state_classification(observed, latest, expected):
    assert classify_source_state(observed, latest) == expected


@pytest.mark.parametrize(
    "changes",
    [
        {"count": 19},
        {"http_status": 503},
        {"final_url": "https://example.invalid/redirect"},
        {"content_type": "application/json"},
    ],
)
def test_schema_http_redirect_or_content_type_failure_closes_gate_as_unknown(tmp_path, changes):
    result, calls = run_probe(tmp_path, **changes)
    assert calls == [PROBE_URL]
    assert result.status == UNKNOWN
    assert result.error


def test_missing_update_date_is_unknown(tmp_path):
    result, calls = run_probe(tmp_path, source_date=None)
    assert calls == [PROBE_URL]
    assert result.status == UNKNOWN
    assert result.source_state_date is None


def test_unchanged_does_not_call_full_collector(tmp_path):
    full_calls = []
    probe, capture = run_capture_gate(
        full_collector=lambda **kwargs: full_calls.append(kwargs),
        raw_root=tmp_path / "probes",
        now=datetime(2026, 9, 30, 1, 2, 3, tzinfo=timezone.utc),
        fetch=lambda url: (fixture_html(source_date="2026/9/21"), 200, url, "text/html"),
        registry_report=report(),
        master=MASTER,
    )
    assert probe.status == UNCHANGED
    assert capture is None
    assert full_calls == []


def test_advanced_calls_full_collector_once_and_does_not_treat_probe_as_full_proof(tmp_path):
    full_calls = []

    def full_collector(**kwargs):
        full_calls.append(kwargs)
        return {"request_count": 37, "uniform_validation": "collector-owned"}

    probe, capture = run_capture_gate(
        full_collector=full_collector,
        raw_root=tmp_path / "probes",
        now=datetime(2026, 9, 30, 1, 2, 3, tzinfo=timezone.utc),
        fetch=lambda url: (fixture_html(), 200, url, "text/html"),
        registry_report=report(),
        master=MASTER,
    )
    assert probe.status == ADVANCED
    assert full_calls == [{"required_source_date": "2026-09-28"}]
    assert capture["request_count"] == 37


def test_full_failure_is_not_retried(tmp_path):
    calls = []

    def fail_once(**kwargs):
        calls.append(kwargs)
        raise RuntimeError("FULL_37 failed")

    with pytest.raises(RuntimeError, match="FULL_37 failed"):
        run_capture_gate(
            full_collector=fail_once,
            raw_root=tmp_path / "probes",
            now=datetime(2026, 9, 30, 1, 2, 3, tzinfo=timezone.utc),
            fetch=lambda url: (fixture_html(), 200, url, "text/html"),
            registry_report=report(),
            master=MASTER,
        )
    assert len(calls) == 1


def test_newly_registered_source_state_prevents_duplicate_capture(tmp_path):
    first, _ = run_probe(tmp_path / "first")
    assert first.status == ADVANCED
    second, _ = run_probe(tmp_path / "second", saved_date="2026-09-28")
    assert second.status == UNCHANGED


def test_probe_has_no_model_or_evaluation_dependency():
    source = Path(__file__).parents[1].joinpath(
        "src/collect/jstats_snapshot_probe.py"
    ).read_text(encoding="utf-8")
    assert "src.modeling" not in source
    assert "sklearn" not in source
    assert "metric" not in source.lower()
