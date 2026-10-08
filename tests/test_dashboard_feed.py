"""Only temporary synthetic repositories; production IO, models and network blocked."""

import ast
import builtins
from copy import deepcopy
import csv
from datetime import date, timedelta
import importlib.abc
import io
import json
from pathlib import Path
import socket
import sys
import urllib.request

import pandas as pd
import pytest

from scripts import build_dashboard_feed as adapter
from scripts.serve_dashboard import DashboardDataError, validate_dashboard_data
from src.collect.teams import MASTER_COLUMNS


@pytest.fixture(autouse=True)
def production_and_network_firewall(monkeypatch):
    protected = [adapter.ROOT / path for path in ("data", "models")]

    def guard(original):
        def checked(file, *args, **kwargs):
            if isinstance(file, (str, bytes, Path)):
                path = Path(file).resolve()
                assert not any(path.is_relative_to(root) for root in protected), "Production IO forbidden"
            return original(file, *args, **kwargs)
        return checked

    monkeypatch.setattr(builtins, "open", guard(builtins.open))
    monkeypatch.setattr(io, "open", guard(io.open))

    def forbidden(*args, **kwargs):
        pytest.fail("Network/model/metrics forbidden")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(urllib.request, "urlopen", forbidden)

    class ForbiddenImport(importlib.abc.MetaPathFinder):
        def find_spec(self, fullname, *args):
            if fullname.split(".")[0] in {"sklearn", "joblib", "lightgbm", "catboost"}:
                forbidden()
            if fullname.startswith("src.modeling.") and fullname != "src.modeling.prediction_identity":
                forbidden()

    blocker = ForbiddenImport()
    sys.meta_path.insert(0, blocker)
    yield
    sys.meta_path.remove(blocker)


def csv_bytes(rows, columns):
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=columns)
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


def publish(directory, rows, *, observed, version="ongoing-v1"):
    directory.mkdir(parents=True, exist_ok=True)
    columns = tuple(rows[0])
    completed = [row for row in rows if row["status"] == "completed"]
    bodies = {
        "schedule.csv": csv_bytes(rows, columns),
        "completed_matches.csv": csv_bytes(completed, columns),
        "fixture_identity.csv": csv_bytes([
            {key: row[key] for key in adapter.IDENTITY_COLUMNS} for row in rows
        ], adapter.IDENTITY_COLUMNS),
    }
    summary = {
        "publication_status": "published", "observed_at_utc": observed,
        "publication_blocks": [], "total_fixtures": len(rows),
        "counts": {state: sum(row["status"] == state for row in rows)
                   for state in ("scheduled", "candidate", "completed")},
        "result_validation": "passed" if completed else "no_completed_matches",
    }
    bodies["update_summary.json"] = json.dumps(summary).encode()
    manifest = {
        "format_version": version, "completion_policy": adapter.COMPLETION_POLICY,
        "snapshot_id": "synthetic-snapshot", "summary": summary,
        "files": {name: adapter.sha(body) for name, body in bodies.items()},
    }
    for name, body in bodies.items():
        (directory / name).write_bytes(body)
    (directory / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return adapter.sha((directory / "manifest.json").read_bytes())


def set_completed(row, *, home=2, away=1):
    row.update(
        status="completed", home_score=str(home), away_score=str(away),
        result=str(2 if home > away else 1 if home == away else 0),
        evidence_type="official_game_over_section", completion_origin_snapshot="synthetic-finish",
        evidence_fetched_at_utc=f"{row['match_date']}T23:00:00+09:00",
        match_id=str(9000 + int(row["match_page_id"])),
        data_site_match_id=str(9000 + int(row["match_page_id"])), match_id_namespace=adapter.DATA_SITE_NAMESPACE,
    )


@pytest.fixture
def repository(tmp_path):
    root = tmp_path / "repo"
    master = root / adapter.TEAM_MASTER_PATH
    master.parent.mkdir(parents=True)
    aliases = []
    for number in range(1, 21):
        for name in (f"Club {number}", f"Canonical Club {number}"):
            aliases.append(dict(
                team_id=f"team_{number:04d}", canonical_name=f"Canonical Club {number}",
                source_name=name, source="jleague_data_site", valid_from="", valid_to="",
                source_club_id=f"club{number}",
            ))
    master.write_bytes(csv_bytes(aliases, MASTER_COLUMNS))
    circle = list(range(1, 21))
    first_half = []
    for round_index in range(19):
        for index in range(10):
            first_half.append((round_index + 1, circle[index], circle[-index - 1]))
        circle = [circle[0], circle[-1], *circle[1:-1]]
    pairs = first_half + [(round_number + 19, away, home) for round_number, home, away in first_half]
    rows = []
    for index, (round_number, home, away) in enumerate(pairs):
        page = str(100001 + index)
        # Different dates for unrelated unsaved fixtures prevent accidental synthetic date batches.
        day = (date(2026, 9, 1) + timedelta(days=round_number)).isoformat()
        rows.append(dict(
            match_id=page, season="2026", round=str(round_number), match_date=day,
            home_team=f"Club {home}", away_team=f"Club {away}", stadium="Synthetic Stadium",
            home_score="", away_score="", result="", fixture_key=f"j1_2026_2027:club{home}:club{away}",
            kickoff_time="19:00", status="scheduled", competition_key="j1_2026_2027",
            competition="Ｊ１", stage="full_season", home_club=f"club{home}", away_club=f"club{away}",
            evidence_type="official_scheduled_identity", evidence_url=f"https://www.jleague.jp/match/j1/2026/{page}/",
            evidence_sha256="a" * 64, evidence_fetched_at_utc="2026-08-02T12:00:00+00:00",
            completion_origin_snapshot="", match_page_id=page, data_site_match_id="", match_id_namespace="",
        ))
    dates = ["2026-08-08", "2026-08-15", "2026-08-22", "2026-08-29"]
    for index, row in enumerate(rows[:8]):
        row["match_date"] = dates[index // 2]
    ongoing = root / adapter.ONGOING_PATH
    source_id, current_id = "1" * 64, "2" * 64
    source_dir = ongoing / "revisions" / source_id
    source_sha = publish(source_dir, rows, observed="2026-08-02T15:00:00+00:00")
    current_rows = deepcopy(rows)
    for row in current_rows:
        row["match_id_namespace"] = adapter.MATCH_PAGE_NAMESPACE
    for row in current_rows[:4]:
        set_completed(row)
    current_dir = ongoing / "revisions" / current_id
    current_sha = publish(current_dir, current_rows, observed="2026-09-01T15:00:00+00:00", version="ongoing-v2")
    (ongoing / "latest.json").write_text(json.dumps({
        "revision_id": current_id, "manifest_sha256": current_sha,
    }), encoding="utf-8")
    predictions, bindings = [], []
    for row in rows[:8]:
        projection = dict(
            fixture_key=row["fixture_key"], match_id=row["match_id"], match_date=row["match_date"],
            kickoff=row["kickoff_time"], home_team_id=f"team_{int(row['home_club'][4:]):04d}",
            away_team_id=f"team_{int(row['away_club'][4:]):04d}",
            home_team_name=row["home_team"], away_team_name=row["away_team"],
            prediction_generated_at="2026-08-03T12:34:56.123456+00:00", source_revision=source_id,
            champion_a_model_version=adapter.CHAMPION_VERSION, champion_a_artifact_hash=adapter.CHAMPION_HASH,
            a_p_home="0.3123456789012345", a_p_draw="0.25", a_p_away="0.4376543210987655",
            comparison_version=adapter.COMPARISON_VERSION,
        )
        mixed = {column: "OPAQUE_RESEARCH_SENTINEL_NOT_A_NUMBER" for column in adapter.MIXED_COLUMNS}
        mixed.update(projection)
        predictions.append(mixed)
        bindings.append(dict(
            prediction_artifact=adapter.PREDICTION_ARTIFACT, prediction_match_id=row["match_id"],
            model_version=adapter.COMPARISON_VERSION, fixture_key=row["fixture_key"],
            prediction_id_namespace=adapter.MATCH_PAGE_NAMESPACE, identity_witness_revision_id=source_id,
            identity_witness_manifest_sha256=source_sha, match_date=row["match_date"],
            home_team_id=projection["home_team_id"], away_team_id=projection["away_team_id"],
            prediction_generated_at=projection["prediction_generated_at"],
        ))
    prediction_path, binding_path = root / adapter.PREDICTION_ARTIFACT, root / adapter.BINDING_PATH
    prediction_path.parent.mkdir(parents=True)
    prediction_path.write_bytes(csv_bytes(predictions, adapter.MIXED_COLUMNS))
    binding_path.write_bytes(csv_bytes(bindings, adapter.BINDING_COLUMNS))
    return dict(root=root, rows=rows, current_rows=current_rows, predictions=predictions, bindings=bindings,
                source_dir=source_dir, source_id=source_id, source_sha=source_sha, current_dir=current_dir,
                current_id=current_id, prediction_path=prediction_path, binding_path=binding_path)


def save_predictions(repo):
    repo["prediction_path"].write_bytes(csv_bytes(repo["predictions"], adapter.MIXED_COLUMNS))


def save_bindings(repo):
    repo["binding_path"].write_bytes(csv_bytes(repo["bindings"], adapter.BINDING_COLUMNS))


def republish_current(repo):
    digest = publish(repo["current_dir"], repo["current_rows"], observed="2026-09-01T15:00:00+00:00", version="ongoing-v2")
    (repo["root"] / adapter.ONGOING_PATH / "latest.json").write_text(json.dumps({
        "revision_id": repo["current_id"], "manifest_sha256": digest,
    }), encoding="utf-8")


def test_end_to_end_exact_schema_firewall_selection_identity_and_no_writes(repository):
    before = {path: path.read_bytes() for path in repository["root"].rglob("*") if path.is_file()}
    payload = adapter.build_dashboard_feed(repository["root"])
    assert validate_dashboard_data(payload) is payload
    assert payload["model"] == {"name": "Champion A", "version": adapter.CHAMPION_VERSION}
    assert payload["updatedAt"] == "2026-09-01T15:00:00+00:00"
    assert payload["previousRound"]["label"] == "前節 · 2026-08-15"
    assert payload["nextRound"]["label"] == "次節 · 2026-08-22"
    assert [match["id"] for match in payload["previousRound"]["matches"]] == sorted(
        row["fixture_key"] for row in repository["predictions"][2:4])
    assert [match["id"] for match in payload["nextRound"]["matches"]] == sorted(
        row["fixture_key"] for row in repository["predictions"][4:6])
    for match in payload["previousRound"]["matches"]:
        assert match["result"] == {"homeScore": 2, "awayScore": 1}
    for match in payload["nextRound"]["matches"]:
        assert "result" not in match
        assert match["prediction"]["probabilities"] == {
            "home": float("0.3123456789012345") * 100, "draw": 25.0,
            "away": float("0.4376543210987655") * 100,
        }
        assert match["homeTeam"]["name"].startswith("Canonical Club")
    serialized = json.dumps(payload)
    for forbidden in ("st2", "a_elo_diff", "predicted_class", "comparison_version", "OPAQUE_RESEARCH", "accuracy", "brier"):
        assert forbidden not in serialized.lower()
    assert all(path.read_bytes() == body for path, body in before.items())
    assert not (repository["root"] / adapter.OUTPUT_PATH).exists()


def test_projection_never_materializes_research_or_class_fields(repository):
    frame = adapter.read_champion_predictions(repository["prediction_path"])
    assert tuple(frame.columns) == adapter.PROJECTION_COLUMNS
    assert len(frame) == 8
    assert frame.iloc[0].a_p_home == "0.3123456789012345"
    before = adapter.build_dashboard_feed(repository["root"])
    for row in repository["predictions"]:
        for key in set(adapter.MIXED_COLUMNS) - set(adapter.PROJECTION_COLUMNS) - {"comparison_version"}:
            row[key] = "ST2_POISON_INFINITY_UNUSABLE"
    save_predictions(repository)
    assert adapter.build_dashboard_feed(repository["root"]) == before


@pytest.mark.parametrize("column,value", [
    ("champion_a_model_version", "wrong"), ("champion_a_artifact_hash", "f" * 64),
    ("comparison_version", "wrong"), ("a_p_home", "NaN"), ("a_p_home", "Infinity"),
    ("a_p_home", "-0.1"), ("a_p_home", "1.1"), ("a_p_home", "0.9"),
    ("a_p_home", ""), ("kickoff", "19時"), ("match_date", "2026-02-30"),
    ("prediction_generated_at", "2026-08-08T19:00:00+09:00"),
    ("prediction_generated_at", "2026-08-03T12:00:00"), ("source_revision", "../outside"),
])
def test_invalid_champion_projection_rejected(repository, column, value):
    repository["predictions"][0][column] = value
    save_predictions(repository)
    with pytest.raises(ValueError):
        adapter.build_dashboard_feed(repository["root"])


@pytest.mark.parametrize("problem", ["missing", "orphan", "duplicate", "fixture", "id", "model", "date", "home", "away", "time", "namespace", "witness", "witness_sha"])
def test_sidecar_one_to_one_and_identity_mandatory(repository, problem):
    if problem == "missing":
        repository["bindings"].pop()
    elif problem == "orphan":
        extra = deepcopy(repository["bindings"][0])
        extra.update(prediction_match_id="999999", fixture_key="j1_2026_2027:club20:club19")
        repository["bindings"].append(extra)
    elif problem == "duplicate":
        repository["bindings"].append(deepcopy(repository["bindings"][0]))
    else:
        field, value = {
            "fixture": ("fixture_key", "j1_2026_2027:club20:club19"), "id": ("prediction_match_id", "999999"),
            "model": ("model_version", "wrong"), "date": ("match_date", "2026-08-09"),
            "home": ("home_team_id", "team_0020"), "away": ("away_team_id", "team_0019"),
            "time": ("prediction_generated_at", "2026-08-03T13:00:00Z"),
            "namespace": ("prediction_id_namespace", adapter.DATA_SITE_NAMESPACE),
            "witness": ("identity_witness_revision_id", "f" * 64),
            "witness_sha": ("identity_witness_manifest_sha256", "f" * 64),
        }[problem]
        repository["bindings"][0][field] = value
    save_bindings(repository)
    with pytest.raises((ValueError, OSError)):
        adapter.build_dashboard_feed(repository["root"])


def test_partial_saved_date_batch_is_never_silently_displayed(repository):
    repository["predictions"].pop()
    repository["bindings"].pop()
    save_predictions(repository)
    save_bindings(repository)
    with pytest.raises(adapter.DashboardFeedError, match="Partial saved"):
        adapter.build_dashboard_feed(repository["root"])


@pytest.mark.parametrize("marker", ["journal.json", "lock"])
def test_no_append_recovery_or_read_during_writer(repository, marker):
    path = repository["binding_path"].with_name(f".{repository['binding_path'].name}.{marker}")
    path.write_text("RESEARCH_JOURNAL_MUST_NOT_BE_READ", encoding="utf-8")
    with pytest.raises(adapter.DashboardFeedError, match="append pending"):
        adapter.build_dashboard_feed(repository["root"])


@pytest.mark.parametrize("problem", ["pointer_sha", "pointer_escape", "file_sha", "unpublished", "policy", "identity", "completed_subset", "game_over", "result", "evidence_time", "evidence_sha", "team_swap", "typed_id", "population"])
def test_official_source_validation_required(repository, problem):
    current = repository["current_dir"]
    if problem == "pointer_sha":
        pointer = repository["root"] / adapter.ONGOING_PATH / "latest.json"
        pointer.write_text(json.dumps({"revision_id": repository["current_id"], "manifest_sha256": "f" * 64}))
    elif problem == "pointer_escape":
        pointer = repository["root"] / adapter.ONGOING_PATH / "latest.json"
        pointer.write_text(json.dumps({"revision_id": "../outside", "manifest_sha256": "f" * 64}))
    elif problem == "file_sha":
        (current / "schedule.csv").write_bytes(b"tampered")
    elif problem in {"unpublished", "policy"}:
        path = current / "manifest.json"
        manifest = json.loads(path.read_bytes())
        if problem == "unpublished":
            manifest["summary"]["publication_status"] = "held"
        else:
            manifest["completion_policy"] = "scores-only"
        path.write_text(json.dumps(manifest))
        (repository["root"] / adapter.ONGOING_PATH / "latest.json").write_text(json.dumps({
            "revision_id": repository["current_id"], "manifest_sha256": adapter.sha(path.read_bytes()),
        }))
    elif problem in {"identity", "completed_subset"}:
        filename = "fixture_identity.csv" if problem == "identity" else "completed_matches.csv"
        path = current / filename
        frame = pd.read_csv(path, dtype=str, keep_default_na=False)
        frame.loc[0, "match_id"] = "999999"
        body = frame.to_csv(index=False, lineterminator="\n").encode()
        path.write_bytes(body)
        manifest = json.loads((current / "manifest.json").read_bytes())
        manifest["files"][filename] = adapter.sha(body)
        (current / "manifest.json").write_text(json.dumps(manifest))
        (repository["root"] / adapter.ONGOING_PATH / "latest.json").write_text(json.dumps({
            "revision_id": repository["current_id"], "manifest_sha256": adapter.sha((current / "manifest.json").read_bytes()),
        }))
    else:
        row = repository["current_rows"][0]
        if problem == "game_over": row["evidence_type"] = "official_completion_unconfirmed"
        if problem == "result": row["result"] = "0"
        if problem == "evidence_time": row["evidence_fetched_at_utc"] = "2026-09-03T12:00:00Z"
        if problem == "evidence_sha": row["evidence_sha256"] = "bad"
        if problem == "team_swap": row["home_team"], row["away_team"] = row["away_team"], row["home_team"]
        if problem == "typed_id": row["match_id_namespace"] = adapter.MATCH_PAGE_NAMESPACE
        if problem == "population": repository["current_rows"].pop()
        republish_current(repository)
    with pytest.raises((ValueError, OSError)):
        adapter.build_dashboard_feed(repository["root"])


def test_team_master_and_prediction_names_require_exact_registered_identity(repository):
    repository["predictions"][0]["home_team_name"] = "Unknown guessed alias"
    save_predictions(repository)
    with pytest.raises(ValueError):
        adapter.build_dashboard_feed(repository["root"])


def test_empty_previous_and_candidate_scores_not_official_results(repository):
    for row in repository["current_rows"][:4]:
        row.update(status="candidate", evidence_type="official_completion_unconfirmed", completion_origin_snapshot="")
    republish_current(repository)
    payload = adapter.build_dashboard_feed(repository["root"])
    assert payload["previousRound"]["matches"] == []
    assert payload["nextRound"]["label"] == "次節 · 2026-08-08"
    assert all("result" not in match for match in payload["nextRound"]["matches"])


def test_empty_next_and_latest_completed_date(repository):
    for row in repository["current_rows"][:8]:
        set_completed(row)
    republish_current(repository)
    payload = adapter.build_dashboard_feed(repository["root"])
    assert payload["nextRound"]["matches"] == []
    assert payload["previousRound"]["label"] == "前節 · 2026-08-29"


def test_empty_saved_artifact_does_not_fabricate_or_predict(repository):
    repository["predictions"], repository["bindings"] = [], []
    save_predictions(repository)
    save_bindings(repository)
    payload = adapter.build_dashboard_feed(repository["root"])
    assert payload["previousRound"]["matches"] == payload["nextRound"]["matches"] == []


def test_witness_can_be_older_than_prediction_source(repository):
    newer_id = "3" * 64
    publish(repository["root"] / adapter.ONGOING_PATH / "revisions" / newer_id,
            repository["rows"], observed="2026-08-03T00:00:00+00:00")
    for row in repository["predictions"]:
        row["source_revision"] = newer_id
    save_predictions(repository)
    payload = adapter.build_dashboard_feed(repository["root"])
    assert len(payload["nextRound"]["matches"]) == 2


def test_probability_example_and_future_append_not_pinned_to_two_rows(repository):
    for row in repository["predictions"]:
        row.update(a_p_home="0.31", a_p_draw="0.25", a_p_away="0.44")
    save_predictions(repository)
    payload = adapter.build_dashboard_feed(repository["root"])
    assert payload["nextRound"]["matches"][0]["prediction"]["probabilities"] == {"home": 31.0, "draw": 25.0, "away": 44.0}
    assert len(adapter.read_champion_predictions(repository["prediction_path"])) == 8


def test_atomic_writer_fsync_before_replace(repository, tmp_path, monkeypatch):
    payload = adapter.build_dashboard_feed(repository["root"])
    output = tmp_path / "feed.json"
    previous = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    output.write_bytes(previous)
    calls = []
    original_fsync, original_replace = adapter.os.fsync, adapter.os.replace

    def fsync(fd):
        calls.append("fsync")
        assert output.read_bytes() == previous
        original_fsync(fd)

    def replace(source, target):
        calls.append("replace")
        assert Path(source).parent == output.parent
        assert validate_dashboard_data(json.loads(Path(source).read_bytes())) == payload
        original_replace(source, target)

    monkeypatch.setattr(adapter.os, "fsync", fsync)
    monkeypatch.setattr(adapter.os, "replace", replace)
    adapter.write_dashboard_feed(payload, output)
    assert calls == ["fsync", "replace"]
    assert json.loads(output.read_bytes()) == payload
    assert list(tmp_path.glob(".*.tmp")) == []


@pytest.mark.parametrize("failure", ["validation", "write", "fsync", "replace"])
def test_atomic_failure_preserves_previous_output(repository, tmp_path, monkeypatch, failure):
    payload = adapter.build_dashboard_feed(repository["root"])
    output = tmp_path / "feed.json"
    previous = json.dumps(payload).encode("utf-8")
    output.write_bytes(previous)
    if failure == "validation":
        payload["nextRound"]["matches"][0]["st2_p_home"] = "SHOULD_NOT_LEAK"
    elif failure == "write":
        original_fdopen = adapter.os.fdopen

        class InterruptedFile:
            def __init__(self, handle): self.handle = handle
            def __enter__(self): return self
            def __exit__(self, *args): self.handle.close()
            def write(self, body):
                self.handle.write(body[:2])
                raise OSError("Synthetic interrupted write")

        monkeypatch.setattr(adapter.os, "fdopen", lambda *args: InterruptedFile(original_fdopen(*args)))
    else:
        def fail(*args):
            raise OSError("Synthetic write failure")
        monkeypatch.setattr(adapter.os, failure, fail)
    with pytest.raises((ValueError, OSError)):
        adapter.write_dashboard_feed(payload, output)
    assert output.read_bytes() == previous
    assert list(tmp_path.glob(".*.tmp")) == []


def test_cli_help_reads_no_inputs(monkeypatch, capsys):
    def forbidden(*args, **kwargs):
        pytest.fail("Help must not load sources")
    monkeypatch.setattr(adapter, "build_dashboard_feed", forbidden)
    with pytest.raises(SystemExit) as exc:
        adapter.main(["--help"])
    assert exc.value.code == 0
    assert "--output" in capsys.readouterr().out


def test_cli_synthetic_write_and_failure_logs_never_echo_mixed_cells(repository, tmp_path, capsys):
    output = tmp_path / "feed.json"
    assert adapter.main(["--output", str(output)], repository_root=repository["root"]) == 0
    previous = output.read_bytes()
    repository["predictions"][0]["a_p_home"] = "RESEARCH_SENTINEL_MUST_NOT_BE_LOGGED"
    save_predictions(repository)
    assert adapter.main(["--output", str(output)], repository_root=repository["root"]) == 1
    logs = capsys.readouterr()
    assert "SENTINEL" not in logs.out + logs.err
    assert "TECHNICAL STOP" in logs.err
    assert output.read_bytes() == previous


def test_cli_cannot_overwrite_protected_inputs(repository):
    path = repository["root"] / "models" / "metadata.json"
    assert adapter.main(["--output", str(path)], repository_root=repository["root"]) == 1
    assert not path.exists()


def test_static_firewall_no_prediction_metrics_or_network_dependencies():
    tree = ast.parse(Path(adapter.__file__).read_text(encoding="utf-8"))
    imports = [node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
    assert not any(name and name.startswith("src.modeling.") and name != "src.modeling.prediction_identity" for name in imports)
    assert not any(name and name.startswith(("sklearn", "joblib", "requests", "urllib", "src.features")) for name in imports)
    calls = [node.func.attr for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)]
    assert not set(calls) & {"fit", "predict", "predict_proba", "load", "urlopen", "request"}
    direct_imports = [alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names]
    assert not any(name.startswith(("sklearn", "joblib", "requests", "urllib")) for name in direct_imports)
    assert "validate_complete_sidecar" not in Path(adapter.__file__).read_text(encoding="utf-8")


def test_fixture_key_survives_official_namespace_transition(repository):
    for index in range(4):
        assert repository["rows"][index]["match_id"] != repository["current_rows"][index]["match_id"]
    payload = adapter.build_dashboard_feed(repository["root"])
    for match in payload["previousRound"]["matches"]:
        assert match["id"].startswith("j1_2026_2027:")
        assert match["result"] == {"homeScore": 2, "awayScore": 1}


def test_common_sidecar_other_artifacts_are_not_opened_or_result_joined(repository):
    extra = deepcopy(repository["bindings"][0])
    extra.update(prediction_artifact="not-read-research.csv", model_version="other-model")
    repository["bindings"].append(extra)
    save_bindings(repository)
    assert len(adapter.build_dashboard_feed(repository["root"])["previousRound"]["matches"]) == 2


def test_input_changed_during_read_rejected(repository, monkeypatch):
    original = adapter.validate_dashboard_data

    def mutate_after_validation(payload):
        result = original(payload)
        repository["prediction_path"].write_bytes(repository["prediction_path"].read_bytes() + b"\n")
        return result

    monkeypatch.setattr(adapter, "validate_dashboard_data", mutate_after_validation)
    with pytest.raises(adapter.DashboardFeedError, match="changed during"):
        adapter.build_dashboard_feed(repository["root"])


@pytest.mark.parametrize("problem", ["unknown_master_id", "swapped_prediction_teams", "witness_date", "witness_after_prediction", "split_batch_time", "missing_official_id", "completion_before_kickoff"])
def test_additional_identity_and_chronology_gates(repository, problem):
    if problem in {"unknown_master_id", "swapped_prediction_teams"}:
        if problem == "unknown_master_id":
            repository["predictions"][0]["home_team_id"] = "team_9999"
            repository["bindings"][0]["home_team_id"] = "team_9999"
        else:
            for row in (repository["predictions"][0], repository["bindings"][0]):
                row["home_team_id"], row["away_team_id"] = row["away_team_id"], row["home_team_id"]
        save_predictions(repository)
        save_bindings(repository)
    elif problem == "split_batch_time":
        repository["predictions"][0]["prediction_generated_at"] = "2026-08-03T12:34:57+00:00"
        repository["bindings"][0]["prediction_generated_at"] = "2026-08-03T12:34:57+00:00"
        save_predictions(repository)
        save_bindings(repository)
    elif problem in {"witness_date", "witness_after_prediction"}:
        observed = "2026-08-04T15:00:00+00:00" if problem == "witness_after_prediction" else "2026-08-02T15:00:00+00:00"
        if problem == "witness_date": repository["rows"][0]["match_date"] = "2026-08-09"
        digest = publish(repository["source_dir"], repository["rows"], observed=observed)
        for row in repository["bindings"]: row["identity_witness_manifest_sha256"] = digest
        save_bindings(repository)
    else:
        row = repository["current_rows"][4 if problem == "missing_official_id" else 0]
        if problem == "missing_official_id":
            row.update(match_id="", match_page_id="", data_site_match_id="", match_id_namespace="")
        else:
            row["evidence_fetched_at_utc"] = "2026-08-02T12:00:00+00:00"
        republish_current(repository)
    with pytest.raises(ValueError):
        adapter.build_dashboard_feed(repository["root"])


def test_csv_shape_is_exact_even_when_research_cells_are_opaque(repository):
    body = repository["prediction_path"].read_bytes()
    with pytest.raises(adapter.DashboardFeedError):
        adapter.read_champion_predictions(body=body.replace(b"fixture_key,", b"unknown_extra,fixture_key,", 1))
    with pytest.raises(adapter.DashboardFeedError):
        adapter.read_champion_predictions(body=body + b"malformed,row\n")


def test_canonical_prediction_names_are_explicitly_valid(repository):
    for row in repository["predictions"]:
        for side in ("home", "away"):
            number = int(row[f"{side}_team_id"][5:])
            row[f"{side}_team_name"] = f"Canonical Club {number}"
    save_predictions(repository)
    assert len(adapter.build_dashboard_feed(repository["root"])["nextRound"]["matches"]) == 2


def test_v2_data_site_witness_uses_typed_identity_not_numeric_namespace_guess(repository):
    source_rows = deepcopy(repository["rows"])
    for index, row in enumerate(source_rows):
        row["match_id_namespace"] = adapter.MATCH_PAGE_NAMESPACE
        if index < 8:
            identifier = str(600001 + index)
            row.update(match_id=identifier, match_page_id="", data_site_match_id=identifier,
                       match_id_namespace=adapter.DATA_SITE_NAMESPACE, evidence_type="", evidence_url="",
                       evidence_sha256="", evidence_fetched_at_utc="")
    digest = publish(repository["source_dir"], source_rows, observed="2026-08-02T15:00:00+00:00", version="ongoing-v2")
    for index in range(8):
        repository["predictions"][index]["match_id"] = source_rows[index]["match_id"]
        repository["bindings"][index].update(
            prediction_match_id=source_rows[index]["match_id"],
            prediction_id_namespace=adapter.DATA_SITE_NAMESPACE, identity_witness_manifest_sha256=digest)
    save_predictions(repository)
    save_bindings(repository)
    assert len(adapter.build_dashboard_feed(repository["root"])["nextRound"]["matches"]) == 2


def test_accepted_reschedule_selects_official_date_without_changing_saved_probability(repository):
    for row in repository["current_rows"][4:6]:
        row["match_date"], row["kickoff_time"] = "2026-08-25", "20:00"
    republish_current(repository)
    payload = adapter.build_dashboard_feed(repository["root"])
    assert payload["nextRound"]["label"] == "次節 · 2026-08-25"
    assert len(payload["nextRound"]["matches"]) == 2
    assert all(match["kickoffAt"] == "2026-08-25T20:00:00+09:00" for match in payload["nextRound"]["matches"])
    assert payload["nextRound"]["matches"][0]["prediction"]["probabilities"]["home"] == float("0.3123456789012345") * 100


def test_extra_output_keys_are_rejected_before_any_output_write(repository, tmp_path):
    payload = adapter.build_dashboard_feed(repository["root"])
    payload["metrics"] = {"accuracy": "DO_NOT_COMPUTE"}
    output = tmp_path / "feed.json"
    with pytest.raises(DashboardDataError):
        adapter.write_dashboard_feed(payload, output)
    assert not output.exists()


@pytest.mark.parametrize("problem", ["unsafe_file", "missing_typed_column", "summary_counts", "summary_projection"])
def test_additional_published_revision_schema_gates(repository, problem):
    current = repository["current_dir"]
    manifest_path = current / "manifest.json"
    manifest = json.loads(manifest_path.read_bytes())
    if problem == "unsafe_file":
        manifest["files"]["../outside.csv"] = "a" * 64
    elif problem == "missing_typed_column":
        for filename in ("schedule.csv", "completed_matches.csv"):
            frame = pd.read_csv(current / filename, dtype=str, keep_default_na=False).drop(columns=["match_id_namespace"])
            body = frame.to_csv(index=False, lineterminator="\n").encode()
            (current / filename).write_bytes(body)
            manifest["files"][filename] = adapter.sha(body)
    else:
        manifest["summary"]["counts"]["completed"] = 0
        if problem == "summary_counts":
            body = json.dumps(manifest["summary"]).encode()
            (current / "update_summary.json").write_bytes(body)
            manifest["files"]["update_summary.json"] = adapter.sha(body)
    manifest_path.write_text(json.dumps(manifest))
    (repository["root"] / adapter.ONGOING_PATH / "latest.json").write_text(json.dumps({
        "revision_id": repository["current_id"], "manifest_sha256": adapter.sha(manifest_path.read_bytes()),
    }))
    with pytest.raises(ValueError):
        adapter.build_dashboard_feed(repository["root"])
