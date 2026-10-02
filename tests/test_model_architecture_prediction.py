import hashlib
import json
import shutil
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

import src.modeling.model_architecture_prediction as prediction
from src.collect.teams import AmbiguousTeamError, load_team_master
from src.modeling.architecture_poisson import fit_poisson_model
from src.modeling.architecture_poisson_artifact import LoadedPoissonArtifact


def _schedule() -> pd.DataFrame:
    rows = []
    rows.append(("old", "2026-09-20", "19:00", "鹿島", "浦和", "old", "completed"))
    rows.extend(
        [
            ("next_b", "2026-10-09", "19:00", "浦和", "鹿島", "next_b", "scheduled"),
            ("next_a", "2026-10-09", "14:00", "鹿島", "浦和", "next_a", "scheduled"),
        ]
    )
    for index in range(298):
        rows.append(
            (
                f"later_{index:03d}",
                f"2026-10-{10 + index // 100:02d}",
                "14:00",
                "鹿島",
                "浦和",
                f"later_{index:03d}",
                "scheduled",
            )
        )
    return pd.DataFrame(rows, columns=prediction.SAFE_SCHEDULE_COLUMNS)


def _training_matches() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "match_id": ["m1", "m2", "m3", "m4", "m5", "m6"],
            "match_date": pd.date_range("2020-01-01", periods=6),
            "home_team_id": ["team_0008", "team_0030"] * 3,
            "away_team_id": ["team_0030", "team_0008"] * 3,
            "home_score": [2, 0, 1, 3, 1, 0],
            "away_score": [1, 1, 1, 0, 2, 0],
            "elo_diff": [10.0, -10.0, 20.0, -20.0, 5.0, -5.0],
        }
    )


def _artifact() -> LoadedPoissonArtifact:
    return LoadedPoissonArtifact(
        model=fit_poisson_model(_training_matches()),
        manifest=pd.DataFrame(),
        metadata={
            "model_version": prediction.MODEL_VERSION,
            "training_cutoff": prediction.TRAINING_CUTOFF,
            "training_row_count": 3588,
        },
        artifact_hash=prediction.EXPECTED_ARTIFACT_HASH,
    )


def _targets(two: bool = True) -> pd.DataFrame:
    rows = [
        {
            "match_id": "next_a",
            "match_date": "2026-10-09",
            "kickoff": "14:00",
            "home_team_id": "team_0008",
            "away_team_id": "team_0030",
            "elo_diff": 15.0,
        }
    ]
    if two:
        rows.append(
            {
                "match_id": "next_b",
                "match_date": "2026-10-09",
                "kickoff": "19:00",
                "home_team_id": "team_0030",
                "away_team_id": "team_0008",
                "elo_diff": -15.0,
            }
        )
    return pd.DataFrame(rows, columns=prediction.TARGET_COLUMNS)


def _records(two: bool = True) -> pd.DataFrame:
    return prediction.generate_prediction_records(
        _targets(two),
        _artifact(),
        generated_at="2026-10-09T08:00:00+09:00",
    )


def test_frozen_cohort_nearest_unfinished_whole_date_and_later_exclusion():
    schedule = _schedule()
    cohort, batch = prediction.select_next_date_batch(schedule)
    assert len(cohort) == prediction.EXPECTED_PROSPECTIVE_ROWS == 300
    assert batch["match_id"].tolist() == ["next_a", "next_b"]
    assert batch["match_date"].unique().tolist() == ["2026-10-09"]
    assert not batch["match_id"].str.startswith("later_").any()


def test_completed_row_stays_in_cohort_but_is_not_a_target():
    schedule = _schedule()
    schedule.loc[schedule["match_id"].eq("next_a"), "status"] = "completed"
    cohort, batch = prediction.select_next_date_batch(schedule)
    assert "next_a" in cohort["match_id"].tolist()
    assert batch["match_id"].tolist() == ["next_b"]


def test_wrong_cohort_size_is_rejected():
    with pytest.raises(prediction.ArchitecturePredictionError, match="must contain 300"):
        prediction.select_next_date_batch(_schedule().iloc[:-1])


def test_blank_duplicate_ids_reject_and_fixture_key_is_never_substituted():
    batch = _schedule().loc[lambda frame: frame["match_date"].eq("2026-10-09")].copy()
    batch.loc[batch.index[0], "match_id"] = ""
    batch.loc[batch.index[0], "fixture_key"] = "looks-like-an-id"
    with pytest.raises(prediction.ArchitecturePredictionError, match="never a substitute"):
        prediction.require_official_target_ids(batch)
    batch["match_id"] = "same"
    with pytest.raises(prediction.ArchitecturePredictionError, match="Duplicate official"):
        prediction.require_official_target_ids(batch)


def test_exact_team_master_resolution_and_deterministic_target_order():
    _cohort, batch = prediction.select_next_date_batch(_schedule())
    targets = prediction.resolve_targets(batch)
    assert targets["match_id"].tolist() == ["next_a", "next_b"]
    assert targets[["home_team_id", "away_team_id"]].to_dict("records") == [
        {"home_team_id": "team_0008", "away_team_id": "team_0030"},
        {"home_team_id": "team_0030", "away_team_id": "team_0008"},
    ]


def test_unknown_ambiguous_and_same_identity_are_rejected():
    _cohort, batch = prediction.select_next_date_batch(_schedule())
    unknown = batch.copy(deep=True)
    unknown.loc[0, "home_team"] = "Not A Registered Club"
    with pytest.raises(ValueError, match="Unknown team alias"):
        prediction.resolve_targets(unknown)

    class AmbiguousMaster:
        def resolve_team_id(self, name, **_kwargs):
            if name == "鹿島":
                raise AmbiguousTeamError("ambiguous")
            return "team_0030"

    with pytest.raises(AmbiguousTeamError, match="ambiguous"):
        prediction.resolve_targets(batch, team_master=AmbiguousMaster())

    class SameMaster:
        def resolve_team_id(self, _name, **_kwargs):
            return "team_0001"

    with pytest.raises(prediction.ArchitecturePredictionError, match="must differ"):
        prediction.resolve_targets(batch, team_master=SameMaster())


def _history_segment(rows):
    frame = pd.DataFrame(rows)
    frame["home_team_id"] = "team_0008"
    frame["away_team_id"] = "team_0030"
    frame["home_elo"] = 1500.0
    frame["away_elo"] = 1500.0
    frame["elo_diff"] = 0.0
    return frame


def test_elo_uses_only_strictly_prior_dates_and_preserves_continuous_history(monkeypatch):
    historical = _history_segment(
        [
            {"match_id": "2015", "season": 2015, "match_date": pd.Timestamp("2015-03-01")},
            {"match_id": "2025", "season": 2025, "match_date": pd.Timestamp("2025-12-06")},
        ]
    )
    hyakunen = _history_segment(
        [{"match_id": "h", "season": 2026, "match_date": pd.Timestamp("2026-05-01")}]
    )
    ongoing = _history_segment(
        [
            {"match_id": "prior", "season": 2026, "match_date": pd.Timestamp("2026-10-08")},
            {"match_id": "same", "season": 2026, "match_date": pd.Timestamp("2026-10-09")},
            {"match_id": "later", "season": 2026, "match_date": pd.Timestamp("2026-10-10")},
        ]
    )
    verified = SimpleNamespace(
        historical=SimpleNamespace(matches=historical),
        hyakunen=SimpleNamespace(matches=hyakunen),
        ongoing=SimpleNamespace(matches=ongoing),
    )
    captured = {}

    def rebuild(ordinary, special, current, **kwargs):
        captured["ordinary"] = ordinary.copy(deep=True)
        captured["special"] = special.copy(deep=True)
        captured["ongoing"] = current.copy(deep=True)
        captured["observed_at"] = kwargs["observed_at"]
        return SimpleNamespace(
            ongoing=SimpleNamespace(
                final_ratings={"team_0008": 1525.0, "team_0030": 1475.0}
            )
        )

    monkeypatch.setattr(prediction, "load_elo_history_with_ongoing", lambda *_a, **_k: verified)
    monkeypatch.setattr(prediction, "build_elo_history_with_ongoing", rebuild)
    identities = _targets(False).drop(columns="elo_diff")
    before = identities.copy(deep=True)

    result = prediction.add_strictly_prior_elo(
        identities, processed_dir="unused", team_master=load_team_master()
    )

    assert captured["ordinary"]["match_id"].tolist() == ["2015", "2025"]
    assert captured["special"]["match_id"].tolist() == ["h"]
    assert captured["ongoing"]["match_id"].tolist() == ["prior"]
    assert captured["observed_at"] == "2026-10-09T00:00:00+09:00"
    assert result["elo_diff"].tolist() == [50.0]
    assert np.isfinite(result["elo_diff"]).all()
    assert_frame_equal(identities, before)


def test_valid_frozen_artifact_loads_and_hash_is_exact():
    loaded = prediction.load_frozen_artifact()
    assert loaded.metadata["model_version"] == prediction.MODEL_VERSION
    assert loaded.metadata["training_cutoff"] == "2025-12-06"
    assert loaded.metadata["training_row_count"] == 3588
    assert loaded.artifact_hash == prediction.EXPECTED_ARTIFACT_HASH


def _replace_checksum(directory: Path, filename: str) -> None:
    checksum_path = directory / "checksums.sha256"
    lines = checksum_path.read_text(encoding="ascii").splitlines()
    digest = hashlib.sha256((directory / filename).read_bytes()).hexdigest()
    replaced = [f"{digest}  {filename}" if line.endswith(f"  {filename}") else line for line in lines]
    checksum_path.write_text("\n".join(replaced) + "\n", encoding="ascii")


def test_wrong_model_version_corrupt_checksum_and_missing_artifact_reject(tmp_path):
    source = prediction.ARTIFACT_DIR
    wrong = tmp_path / "wrong"
    shutil.copytree(source, wrong)
    metadata_path = wrong / "metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["model_version"] = "wrong"
    metadata_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    _replace_checksum(wrong, "metadata.json")
    with pytest.raises(prediction.ArchitecturePredictionError, match="validation failed"):
        prediction.load_frozen_artifact(wrong)

    corrupt = tmp_path / "corrupt"
    shutil.copytree(source, corrupt)
    (corrupt / "model.joblib").write_bytes(b"corrupt")
    with pytest.raises(prediction.ArchitecturePredictionError, match="checksum"):
        prediction.load_frozen_artifact(corrupt)
    with pytest.raises(prediction.ArchitecturePredictionError, match="validation failed"):
        prediction.load_frozen_artifact(tmp_path / "missing")


def test_probability_output_contract_is_exact_deterministic_and_unprocessed():
    first = _records()
    second = _records()
    assert tuple(first.columns) == prediction.PREDICTION_COLUMNS
    assert_frame_equal(first, second, check_exact=True)
    values = first[["p_away", "p_draw", "p_home"]].to_numpy(dtype=float)
    assert np.isfinite(values).all()
    assert ((values >= 0) & (values <= 1)).all()
    np.testing.assert_allclose(values.sum(axis=1), 1.0, rtol=0.0, atol=1e-12)
    np.testing.assert_array_equal(first["predicted_class"], values.argmax(axis=1))
    assert first["artifact_hash"].eq(prediction.EXPECTED_ARTIFACT_HASH).all()
    assert first["history_cutoff_exclusive"].eq("2026-10-09").all()
    assert not {"lambda_home", "lambda_away"} & set(first.columns)


@pytest.mark.parametrize(
    ("generated_at", "allowed"),
    [
        ("2026-10-09T13:59:59+09:00", True),
        ("2026-10-09T14:00:00+09:00", False),
        ("2026-10-09T14:00:01+09:00", False),
    ],
)
def test_kickoff_guard_before_equal_and_after(generated_at, allowed):
    targets = _targets(False)
    if allowed:
        assert prediction.validate_pre_kickoff(targets, generated_at).startswith("2026-10-09T13:59:59")
    else:
        with pytest.raises(prediction.ArchitecturePredictionError, match="strictly before"):
            prediction.validate_pre_kickoff(targets, generated_at)


@pytest.mark.parametrize("kickoff", ["", "TBD", "24:00", "14:00 JST", "9:00"])
def test_malformed_or_unsafe_kickoff_rejects(kickoff):
    targets = _targets(False).assign(kickoff=kickoff)
    with pytest.raises(prediction.ArchitecturePredictionError, match="cannot be proven"):
        prediction.validate_pre_kickoff(targets, "2026-10-09T08:00:00+09:00")


def test_dry_run_first_append_repeat_and_existing_bytes_are_immutable(tmp_path):
    records = _records()
    output = tmp_path / "predictions.csv"
    assert prediction.persist_predictions(records, dry_run=True, path=output) == (0, 0)
    assert not output.exists()
    assert prediction.persist_predictions(records, dry_run=False, path=output) == (2, 0)
    original = output.read_bytes()
    assert prediction.persist_predictions(records, dry_run=False, path=output) == (0, 2)
    assert output.read_bytes() == original


def test_full_synthetic_dry_run_crosses_pipeline_and_writes_nothing(tmp_path, monkeypatch):
    schedule = _schedule()
    frozen = _artifact()
    monkeypatch.setattr(
        prediction, "read_schedule_without_results", lambda _path: schedule.copy(deep=True)
    )
    monkeypatch.setattr(prediction, "load_frozen_artifact", lambda _path: frozen)

    def add_elo(identities, **_kwargs):
        result = identities.copy(deep=True)
        result["elo_diff"] = [15.0, -15.0]
        return result.loc[:, list(prediction.TARGET_COLUMNS)]

    monkeypatch.setattr(prediction, "add_strictly_prior_elo", add_elo)
    output = tmp_path / "predictions.csv"
    run = prediction.run_prediction(
        dry_run=True,
        schedule_path="unused",
        output_path=output,
        artifact_dir="unused",
        processed_dir="unused",
        generated_at="2026-10-09T08:00:00+09:00",
    )
    assert run.status == "DRY_RUN"
    assert run.target_date == "2026-10-09"
    assert run.target_count == 2
    assert run.appended_count == run.already_predicted_count == 0
    assert run.saved is False and run.dry_run is True
    assert not output.exists()


def test_duplicate_existing_key_and_malformed_schema_reject(tmp_path):
    records = _records(False)
    duplicate_path = tmp_path / "duplicate.csv"
    pd.concat([records, records], ignore_index=True).to_csv(duplicate_path, index=False)
    with pytest.raises(prediction.ArchitecturePredictionError, match="Duplicate prediction key"):
        prediction.persist_predictions(records, dry_run=True, path=duplicate_path)
    malformed = tmp_path / "malformed.csv"
    records.drop(columns="p_draw").to_csv(malformed, index=False)
    with pytest.raises(prediction.ArchitecturePredictionError, match="schema mismatch"):
        prediction.persist_predictions(records, dry_run=True, path=malformed)


def test_other_model_row_is_not_overwritten_and_same_match_id_can_be_appended(tmp_path):
    records = _records(False)
    other = records.copy(deep=True)
    other["model_version"] = "future_candidate_g_v1"
    other["artifact_hash"] = "g" * 64
    output = tmp_path / "predictions.csv"
    other.to_csv(output, index=False, lineterminator="\n")
    original = output.read_bytes()

    assert prediction.persist_predictions(records, dry_run=False, path=output) == (1, 0)

    saved = pd.read_csv(output, dtype=str, keep_default_na=False)
    assert len(saved) == 2
    assert saved["match_id"].nunique() == 1
    assert set(saved["model_version"]) == {"future_candidate_g_v1", prediction.MODEL_VERSION}
    assert output.read_bytes().startswith(original)


def test_generated_duplicate_key_is_rejected():
    records = _records(False)
    duplicate = pd.concat([records, records], ignore_index=True)
    with pytest.raises(prediction.ArchitecturePredictionError, match="Duplicate prediction key"):
        prediction.persist_predictions(duplicate, dry_run=True, path="unused.csv")


def test_predictor_has_no_refit_metric_candidate_g_or_xg_output_dependency():
    source = Path("src/modeling/model_architecture_prediction.py").read_text(encoding="utf-8")
    for forbidden in (
        "fit_poisson_model",
        "create_poisson_artifact",
        "sklearn.metrics",
        "accuracy_score",
        "log_loss",
        "brier",
        "lightgbm",
        "xg_challenger_prospective.csv",
        "requests",
        "http",
    ):
        assert forbidden not in source


def test_cli_summary_contract_does_not_include_probabilities():
    fields = set(prediction.PredictionRun.__dataclass_fields__)
    assert {
        "status",
        "target_date",
        "target_count",
        "model_version",
        "appended_count",
        "already_predicted_count",
        "saved",
        "dry_run",
    }.issubset(fields)
