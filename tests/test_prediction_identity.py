"""Synthetic-only checks for the immutable prediction fixture sidecar."""

import hashlib
import json

import pandas as pd
import pytest

import src.modeling.prediction_identity as identity


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
