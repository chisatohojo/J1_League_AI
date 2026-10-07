"""Synthetic-only checks for the immutable prediction fixture sidecar."""

import hashlib
import json
import builtins
import io
import os
from pathlib import Path
import socket

import pandas as pd
import pytest

import src.modeling.prediction_identity as identity


@pytest.fixture(autouse=True)
def production_io_and_network_firewall(monkeypatch):
    root = Path(identity.__file__).resolve().parents[2]
    forbidden = [root / p for p in ("data/processed/jleague", "data/master", "models", "data/processed/predictions")]
    def guard(original):
        def wrapped(file, *args, **kwargs):
            if isinstance(file, (str, bytes, Path)):
                path = Path(file).resolve()
                assert not any(path.is_relative_to(p) for p in forbidden), f"Production IO forbidden: {path}"
            return original(file, *args, **kwargs)
        return wrapped
    monkeypatch.setattr(builtins, "open", guard(builtins.open))
    monkeypatch.setattr(io, "open", guard(io.open))
    monkeypatch.setattr(os, "open", guard(os.open))
    def denied(*args, **kwargs):
        raise AssertionError("Network forbidden")
    monkeypatch.setattr(socket, "create_connection", denied)
    monkeypatch.setattr(socket.socket, "connect", denied)


def _bindings(match_id="page1", fixture="fixture:a:b", model="model-v1"):
    return pd.DataFrame([{
        "prediction_artifact": "predictions.csv",
        "prediction_match_id": match_id,
        "model_version": model,
        "fixture_key": fixture,
        "prediction_id_namespace": identity.MATCH_PAGE_NAMESPACE,
        "identity_witness_revision_id": "witness",
        "identity_witness_manifest_sha256": "a" * 64,
        "match_date": "2026-10-09",
        "home_team_id": "team_home",
        "away_team_id": "team_away",
        "prediction_generated_at": "2026-10-01T00:00:00+00:00",
    }], columns=identity.BINDING_COLUMNS)


def _predictions(match_id="page1", model="model-v1"):
    return pd.DataFrame([{
        "match_id": match_id, "model_version": model,
        "match_date": "2026-10-09", "home_team_id": "team_home",
        "away_team_id": "team_away",
        "prediction_generated_at": "2026-10-01T00:00:00+00:00",
        "p_home": "0.5",
    }])


def _validator(frame):
    assert tuple(frame.columns) == tuple(_predictions().columns)
    if frame.duplicated(["match_id", "model_version"]).any():
        raise ValueError("duplicate prediction key")


def test_binding_schema_and_both_uniqueness_keys_are_strict():
    valid = _bindings()
    identity.validate_prediction_bindings(valid)
    with pytest.raises(identity.PredictionIdentityError, match="schema"):
        identity.validate_prediction_bindings(valid.iloc[:, :-1])
    with pytest.raises(identity.PredictionIdentityError, match="primary"):
        identity.validate_prediction_bindings(pd.concat([valid, valid], ignore_index=True))
    duplicate_fixture = pd.concat([
        valid, _bindings(match_id="page2", fixture="fixture:a:b")
    ], ignore_index=True)
    with pytest.raises(identity.PredictionIdentityError, match="fixture"):
        identity.validate_prediction_bindings(duplicate_fixture)


def _six_row_baseline(tmp_path):
    all_bindings = []
    artifacts = ("baseline-a.csv", "baseline-b.csv")
    for artifact, count in zip(artifacts, (2, 4)):
        frames = []
        for i in range(count):
            frames.append(_predictions(f"{artifact}-{i}"))
            all_bindings.append(_bindings(f"{artifact}-{i}", fixture=f"fixture:{i}:away").assign(prediction_artifact=artifact))
        pd.concat(frames, ignore_index=True).to_csv(tmp_path / artifact, index=False)
    sidecar = tmp_path / "bindings.csv"
    bindings = pd.concat(all_bindings, ignore_index=True)
    bindings.to_csv(sidecar, index=False)
    return artifacts, sidecar, bindings


def test_complete_six_row_sidecar_allows_additional_st2_artifact(tmp_path):
    artifacts, sidecar, bindings = _six_row_baseline(tmp_path)
    assert len(identity.validate_complete_sidecar(repository_root=tmp_path, binding_path=sidecar, prediction_artifacts=artifacts)) == 6
    extra = _bindings("official-st2", "fixture:new:away", "season_transition_st2_vs_a_20261006_v1").assign(
        prediction_artifact="data/processed/predictions/season_transition_st2_prospective.csv")
    pd.concat([bindings, extra], ignore_index=True).to_csv(sidecar, index=False)
    assert len(identity.validate_complete_sidecar(repository_root=tmp_path, binding_path=sidecar, prediction_artifacts=artifacts)) == 7


def test_complete_sidecar_checks_fixture_when_prediction_contains_it(tmp_path):
    prediction = _predictions().assign(fixture_key="fixture:a:b")
    prediction.to_csv(tmp_path / "predictions.csv", index=False)
    sidecar = tmp_path / "bindings.csv"
    _bindings().to_csv(sidecar, index=False)
    identity.validate_complete_sidecar(repository_root=tmp_path, binding_path=sidecar, prediction_artifacts=("predictions.csv",))
    prediction.assign(fixture_key="fixture:wrong:away").to_csv(tmp_path / "predictions.csv", index=False)
    with pytest.raises(identity.PredictionIdentityError, match="fixture identity"):
        identity.validate_complete_sidecar(repository_root=tmp_path, binding_path=sidecar, prediction_artifacts=("predictions.csv",))


def test_frozen_default_six_row_schemas_and_future_append(tmp_path):
    """Actual frozen schema/path/count contracts, entirely synthetic temp bytes."""
    binding_frames = []
    for artifact, (_, count) in identity.FROZEN_PREDICTIONS.items():
        rows = []
        fixtures = list(identity.FROZEN_FIXTURES.items())
        for i in range(count):
            match_id, (fixture, day, home, away) = fixtures[i % 2]
            model = f"synthetic-baseline-{i // 2}"
            record = dict.fromkeys(identity.FROZEN_PREDICTION_COLUMNS[artifact], "synthetic")
            record.update(match_id=match_id, model_version=model, match_date=day,
                          home_team_id=home, away_team_id=away,
                          prediction_generated_at="2026-10-01T00:00:00+00:00")
            rows.append(record)
            binding_frames.append(_bindings(match_id, fixture, model).assign(
                prediction_artifact=artifact, match_date=day, home_team_id=home, away_team_id=away))
        path = tmp_path / artifact
        path.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(rows, columns=identity.FROZEN_PREDICTION_COLUMNS[artifact]).to_csv(path, index=False)
    sidecar = tmp_path / identity.DEFAULT_BINDING_PATH
    bindings = pd.concat(binding_frames, ignore_index=True)
    bindings.to_csv(sidecar, index=False)
    assert len(identity.validate_complete_sidecar(repository_root=tmp_path, binding_path=sidecar)) == 6
    extra = _bindings("42", "fixture:future:away", "season_transition_st2_vs_a_20261006_v1").assign(
        prediction_artifact="data/processed/predictions/season_transition_st2_prospective.csv")
    pd.concat([bindings, extra], ignore_index=True).to_csv(sidecar, index=False)
    assert len(identity.validate_complete_sidecar(repository_root=tmp_path, binding_path=sidecar)) == 7


@pytest.mark.parametrize("problem", ["missing_artifact", "missing_binding", "conflict", "orphan", "duplicate_id", "duplicate_fixture"])
def test_complete_sidecar_extra_rows_never_weaken_baseline(tmp_path, problem):
    artifacts, sidecar, bindings = _six_row_baseline(tmp_path)
    extra = _bindings("extra", "fixture:new:away").assign(prediction_artifact="st2.csv")
    if problem == "missing_artifact":
        bindings = bindings.loc[bindings.prediction_artifact.ne(artifacts[0])]
    elif problem == "missing_binding":
        bindings = bindings.iloc[1:]
    elif problem == "conflict":
        bindings.loc[0, "home_team_id"] = "wrong"
    elif problem == "orphan":
        bindings = pd.concat([bindings, _bindings("orphan", "fixture:orphan:away").assign(prediction_artifact=artifacts[0])])
    elif problem == "duplicate_id":
        bindings = pd.concat([bindings, bindings.iloc[[0]]])
    else:
        bindings = pd.concat([bindings, bindings.iloc[[0]].assign(prediction_match_id="different")])
    pd.concat([bindings, extra], ignore_index=True).to_csv(sidecar, index=False)
    with pytest.raises(identity.PredictionIdentityError):
        identity.validate_complete_sidecar(repository_root=tmp_path, binding_path=sidecar, prediction_artifacts=artifacts)


def test_atomic_prediction_binding_append_and_fixture_aware_duplicate(tmp_path):
    prediction_path = tmp_path / "predictions.csv"
    binding_path = tmp_path / "bindings.csv"
    assert identity.append_prediction_and_bindings(
        _predictions(), _bindings(), prediction_path=prediction_path,
        binding_path=binding_path, prediction_columns=tuple(_predictions().columns),
        prediction_validator=_validator,
    ) == (1, 0)
    before_prediction, before_binding = prediction_path.read_bytes(), binding_path.read_bytes()
    assert identity.append_prediction_and_bindings(
        _predictions("data42"), _bindings("data42"), prediction_path=prediction_path,
        binding_path=binding_path, prediction_columns=tuple(_predictions().columns),
        prediction_validator=_validator,
    ) == (0, 1)
    assert prediction_path.read_bytes() == before_prediction
    assert binding_path.read_bytes() == before_binding


def test_atomic_failure_restores_both_files(tmp_path, monkeypatch):
    prediction_path = tmp_path / "predictions.csv"
    binding_path = tmp_path / "bindings.csv"
    original_append = identity._append_suffix
    calls = 0

    def fail_second(path, frame):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("synthetic binding replace failure")
        return original_append(path, frame)

    monkeypatch.setattr(identity, "_append_suffix", fail_second)
    with pytest.raises(OSError, match="synthetic"):
        identity.append_prediction_and_bindings(
            _predictions(), _bindings(), prediction_path=prediction_path,
            binding_path=binding_path, prediction_columns=tuple(_predictions().columns),
            prediction_validator=_validator,
        )
    assert not prediction_path.exists()
    assert not binding_path.exists()
    assert not list(tmp_path.glob("*.journal.json"))


def test_journal_recovery_appends_only_missing_suffix_once(tmp_path):
    prediction_path = tmp_path / "predictions.csv"
    binding_path = tmp_path / "bindings.csv"
    predictions, bindings = _predictions(), _bindings()
    predictions.to_csv(prediction_path, index=False, lineterminator="\n")
    binding_bytes = identity._suffix_bytes(bindings, header=True)
    journal = binding_path.with_name(f".{binding_path.name}.journal.json")
    journal.write_text(json.dumps({
        "prediction_sha256": hashlib.sha256(prediction_path.read_bytes()).hexdigest(),
        "binding_sha256": hashlib.sha256(binding_bytes).hexdigest(),
        "prediction_rows": json.loads(predictions.to_json(orient="records")),
        "binding_rows": json.loads(bindings.to_json(orient="records")),
    }), encoding="utf-8")

    assert identity.recover_prediction_append(
        prediction_path=prediction_path, binding_path=binding_path,
        prediction_columns=tuple(predictions.columns), prediction_validator=_validator,
    ) == (0, 1)
    assert not journal.exists()
    assert len(pd.read_csv(prediction_path)) == 1
    assert len(pd.read_csv(binding_path)) == 1
    with pytest.raises(identity.PredictionIdentityError, match="journal is missing"):
        identity.recover_prediction_append(
            prediction_path=prediction_path, binding_path=binding_path,
            prediction_columns=tuple(predictions.columns), prediction_validator=_validator,
        )


def test_fixture_aware_evaluation_join_is_one_to_one_and_checks_identity():
    predictions, bindings = _predictions(), _bindings()
    bridges = pd.DataFrame([{
        "fixture_key": "fixture:a:b", "competition_key": "j1_2026_2027",
        "data_site_match_id": "42",
    }])
    completed = pd.DataFrame([{
        "match_id": "42", "competition_key": "j1_2026_2027",
        "match_date": "2026-10-09", "home_team_id": "team_home",
        "away_team_id": "team_away", "result": 2,
    }])
    resolved = identity.resolve_predictions_to_completed(
        predictions, bindings, bridges, completed, prediction_artifact="predictions.csv",
    )
    assert resolved["result"].tolist() == [2]
    bad = completed.assign(home_team_id="wrong")
    with pytest.raises(identity.PredictionIdentityError, match="identity mismatch"):
        identity.resolve_predictions_to_completed(
            predictions, bindings, bridges, bad, prediction_artifact="predictions.csv",
        )


def test_offline_bootstrap_hash_witness_exactness_and_exclusive_creation(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    revision_id = "witness-revision"
    revision = root / "revisions" / revision_id
    revision.mkdir(parents=True)
    observations = [{
        "match_id": "page1", "fixture_key": "fixture:a:b", "match_date": "2026-10-09",
        "home_team": "Home", "away_team": "Away",
        "status": "scheduled",
        "evidence_url": "https://www.jleague.jp/match/j1/2026/100901/",
    }]
    observations[0]["match_id"] = "100901"
    observations_body = json.dumps(observations).encode("utf-8")
    (revision / "observations.json").write_bytes(observations_body)
    manifest = {
        "files": {"observations.json": hashlib.sha256(observations_body).hexdigest()},
        "summary": {"publication_status": "published"},
    }
    manifest_bytes = json.dumps(manifest).encode("utf-8")
    (revision / "manifest.json").write_bytes(manifest_bytes)
    artifact = "predictions.csv"
    prediction = _predictions("100901")
    prediction_path = root / artifact
    prediction.to_csv(prediction_path, index=False, lineterminator="\n")

    class Master:
        def resolve_team_id(self, name, **_kwargs):
            return {"Home": "team_home", "Away": "team_away"}[name]

    monkeypatch.setattr(identity, "load_team_master", lambda: Master())
    output = tmp_path / "bindings.csv"
    result = identity.build_frozen_prediction_bindings(
        repository_root=root, witness_revision_dir=revision, output_path=output,
        expected_predictions={artifact: (
            hashlib.sha256(prediction_path.read_bytes()).hexdigest(), 1,
        )},
        witness_revision_id=revision_id,
        witness_manifest_sha256=hashlib.sha256(manifest_bytes).hexdigest(),
        expected_fixtures={
            "100901": ("fixture:a:b", "2026-10-09", "team_home", "team_away"),
        },
    )
    assert len(result) == 1
    with pytest.raises(identity.PredictionIdentityError, match="already exists"):
        identity.build_frozen_prediction_bindings(
            repository_root=root, witness_revision_dir=revision, output_path=output,
            expected_predictions={artifact: (
                hashlib.sha256(prediction_path.read_bytes()).hexdigest(), 1,
            )}, witness_revision_id=revision_id,
            witness_manifest_sha256=hashlib.sha256(manifest_bytes).hexdigest(),
            expected_fixtures={
                "100901": ("fixture:a:b", "2026-10-09", "team_home", "team_away"),
            },
        )
