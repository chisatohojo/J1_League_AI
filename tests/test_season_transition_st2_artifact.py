"""Synthetic ONLY: guarded production IO/network and zero prediction/metrics."""

import ast
import builtins
from dataclasses import replace
import io
import json
import os
from pathlib import Path
import runpy
import socket
import warnings

import joblib
import numpy as np
import pandas as pd
import pytest
from sklearn.exceptions import ConvergenceWarning
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

from src.collect.teams import TeamAlias, TeamMaster, UnknownTeamError
from src.modeling import season_transition_st2_artifact as st


REPO = Path(__file__).parents[1].resolve()
MODULE_FILE = REPO / st.MODULE_PATH
ROSTER = tuple(f"team_{i:04d}" for i in range(1, 7))


@pytest.fixture(autouse=True)
def firewall(monkeypatch):
    """Block all real data/model IO, including stat and mutations, for every case."""
    def check(path):
        if isinstance(path, int):
            return
        try:
            value = os.path.normcase(os.path.abspath(os.fsdecode(path)))
        except TypeError:
            return
        for folder in (REPO / "data", REPO / "models"):
            base = os.path.normcase(str(folder))
            if value == base or value.startswith(base + os.sep):
                raise AssertionError(f"PRODUCTION IO FORBIDDEN: {value}")

    for owner, name in ((builtins, "open"), (io, "open"), (os, "open"), (os, "stat"),
                        (os, "lstat"), (os, "unlink"), (os, "remove"), (os, "mkdir"),
                        (os, "rename"), (os, "replace"), (os, "listdir"), (os, "scandir")):
        original = getattr(owner, name)

        def guarded(path, *args, _original=original, _name=name, **kwargs):
            check(path)
            if _name in ("rename", "replace") and args:
                check(args[0])
            return _original(path, *args, **kwargs)

        monkeypatch.setattr(owner, name, guarded)

    def forbidden(*args, **kwargs):
        raise AssertionError("NETWORK/PREDICTION/METRICS FORBIDDEN")

    for owner, name in ((socket, "create_connection"), (socket, "getaddrinfo"),
                        (socket.socket, "connect"), (socket.socket, "connect_ex"),
                        (socket.socket, "sendto"), (LogisticRegression, "predict"),
                        (LogisticRegression, "predict_proba"), (LogisticRegression, "score")):
        monkeypatch.setattr(owner, name, forbidden)
    original_import = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        if name.startswith(("sklearn.metrics", "src.modeling.champion_a_season_transition_evaluation",
                            "src.modeling.champion_a_oof", "src.modeling.xg_", "src.modeling.architecture",
                            "src.modeling.model_a_artifact", "src.modeling.prediction_identity",
                            "src.collect.jleague_ongoing", "src.collect.jleague_hyakunen")):
            raise AssertionError(f"FORBIDDEN LANE IMPORT: {name}")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    return check


def master():
    return TeamMaster([TeamAlias(team, f"Club{i}", f"Club{i}", "jleague_data_site", None, None, str(i))
                       for i, team in enumerate(ROSTER, 1)])


def match(year, day, number, home=1, away=2, result=2, stage=None):
    stage = stage or ("1st" if year in (2015, 2016) else "full_season")
    return {"season": year, "match_id": f"toy-{year}-{number:04d}",
            "match_date": f"{year}-01-{day:02d}", "round": number + 1,
            "home_team": f"Club{home}", "away_team": f"Club{away}", "stadium": "Toy ground",
            "home_score": int(result == 2), "away_score": int(result == 0), "result": result,
            "stage": stage, "competition": ("Ｊ１ １ｓｔ" if stage == "1st" else "Ｊ１ ２ｎｄ" if stage == "2nd" else "Ｊ１")}


def pin_population(monkeypatch, source):
    monkeypatch.setattr(st, "EXPECTED_ROWS", len(source))
    monkeypatch.setattr(st, "SEASON_COUNTS", source.season.value_counts().to_dict())


@pytest.fixture
def toy(monkeypatch):
    source = pd.DataFrame([r for y in st.TRAINING_SEASONS for r in (
        match(y, 1, 0, 1, 2, 0), match(y, 1, 1, 3, 4, 1), match(y, 2, 2, 1, 2, 2))])
    pin_population(monkeypatch, source)
    return source, master()


def write(root, relative, body):
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)
    return st.sha256(body)


@pytest.fixture
def synthetic_root(tmp_path, monkeypatch, toy):
    source, _ = toy
    pins = {}
    for y, path in zip(st.TRAINING_SEASONS, st.SOURCE_HASHES):
        part = source[source.season.eq(y)].iloc[::-1]
        pins[path] = write(tmp_path, path, part.to_csv(index=False, lineterminator="\n").encode("utf-8"))
    monkeypatch.setattr(st, "SOURCE_HASHES", pins)
    master_body = "team_id,canonical_name,source_name,source,valid_from,valid_to,source_club_id\n" + "".join(
        f"{team},Club{i},Club{i},jleague_data_site,,,{i}\n" for i, team in enumerate(ROSTER, 1))
    monkeypatch.setattr(st, "TEAM_MASTER_SHA", write(tmp_path, st.TEAM_MASTER_PATH, master_body.encode()))
    monkeypatch.setattr(st, "CODE_HASHES", {p: write(tmp_path, p, b"synthetic reviewed code\n") for p in st.CODE_HASHES})
    monkeypatch.setattr(st, "REQUIREMENTS_HASHES", {p: write(tmp_path, p, b"synthetic locked dependency\n") for p in st.REQUIREMENTS_HASHES})
    monkeypatch.setattr(st, "SPEC_SHA", write(tmp_path, st.SPEC_PATH, b"synthetic spec\n"))
    write(tmp_path, st.MODULE_PATH, b"synthetic reviewed builder\n")
    monkeypatch.setattr(st, "repository_state", lambda root: {"commit": "a" * 40, "dirty": False})
    return tmp_path, {"approved_execution_head": "a" * 40, "task_reference": "synthetic-authorized-fit"}


def create(synthetic_root):
    root, auth = synthetic_root
    return st.create_artifact(root=root, authorization=auth)


def rewrite_checksums(path):
    (path / "checksums.sha256").write_text("".join(
        f"{st.sha256((path / n).read_bytes())}  {n}\n" for n in st.CHECKSUM_FILES), encoding="ascii", newline="\n")


def test_constants_spec_and_exact_seven_columns():
    assert st.SPEC_COMMIT == "fb4cef5fea338b99d62f5b2a6c7be5079b4d6f33"
    assert st.SPEC_SHA == "daa26ac92394edcaaa32c07e9b382cb744e380a454e10b548afeff3cf5a28fe3"
    assert st.sha256((REPO / st.SPEC_PATH).read_bytes()) == st.SPEC_SHA
    assert st.MODEL_VERSION == "season_transition_st2_20261006_v1"
    assert st.OUTPUT_DIR == REPO / "models/model_season_transition/season_transition_st2_20261006_v1"
    assert st.ROLE == "prospective_challenger"
    assert st.TRAINING_SEASONS == tuple(range(2015, 2026))
    assert st.EXPECTED_ROWS == 3588 and sum(st.SEASON_COUNTS.values()) == 3588
    assert st.FEATURES == ("elo_diff",) and st.CLASS_ORDER == (0, 1, 2)
    assert st.TARGET_MAPPING == {"0": "Away", "1": "Draw", "2": "Home"}
    assert st.MANIFEST_COLUMNS == ("season", "match_id", "match_date", "home_team_id", "away_team_id", "target_class", "elo_diff")
    assert st.ELO_PARAMETERS == {"initial_rating": 1500., "home_advantage": 175., "expectation_scale": 400.,
                                 "base_k": 30., "early_k": 45., "first_n_appearances": 5, "season_regression": None}
    text = (REPO / st.SPEC_PATH).read_text(encoding="utf-8")
    for path, digest in st.pinned_inputs().items():
        assert path in text and digest in text if path != st.SPEC_PATH else digest == st.SPEC_SHA
    assert tuple(st.SOURCE_HASHES) == tuple(f"data/processed/jleague/{y}_matches_probe.csv" for y in range(2015, 2026))


def test_manifest_canonicalization_deterministic_no_row_trace(toy):
    source, registry = toy
    first = st.build_training_manifest(source, registry)
    other = st.build_training_manifest(source.iloc[::-1], registry)
    assert first == other
    frame = first.to_frame()
    assert tuple(frame.columns) == st.MANIFEST_COLUMNS
    assert frame.elo_diff.dtype == np.dtype("float64")
    assert not first.csv_bytes.startswith(b"\xef\xbb\xbf") and b"\r" not in first.csv_bytes
    assert first.csv_bytes.splitlines()[0].decode() == ",".join(st.MANIFEST_COLUMNS)
    assert first.csv_bytes.endswith(b"\n")
    assert st.serialize_manifest(frame) == first.csv_bytes


def test_exact_count_abstraction(toy, monkeypatch):
    source, registry = toy
    monkeypatch.setattr(st, "EXPECTED_ROWS", len(source) + 1)
    with pytest.raises(st.ST2ArtifactError, match="population"):
        st.build_training_manifest(source, registry)


@pytest.mark.parametrize("change", ["cup", "j2", "hyakunen", "2026", "date", "date_whitespace", "score", "self", "id", "missing", "whitespace", "fraction", "generated"])
def test_semantic_corruption_rejected(toy, change):
    source, registry = toy
    source = source.copy()
    if change in ("cup", "j2", "hyakunen"):
        source.loc[0, "competition"] = {"cup": "League Cup", "j2": "Ｊ２", "hyakunen": "Hyakunen"}[change]
    elif change == "2026":
        source.loc[0, "season"] = 2026
    elif change == "date":
        source.loc[0, "match_date"] = "2025-01-01"
    elif change == "date_whitespace":
        source.loc[0, "match_date"] = " 2015-01-01 "
    elif change == "score":
        source.loc[0, "result"] = 2
    elif change == "self":
        source.loc[0, "away_team"] = source.loc[0, "home_team"]
    elif change == "id":
        source.loc[1, "match_id"] = source.loc[0, "match_id"]
    elif change == "missing":
        source.loc[0, "home_team"] = ""
    elif change == "whitespace":
        source.loc[0, "match_id"] += " "
    elif change == "fraction":
        source["home_score"] = source.home_score.astype(float)
        source.loc[0, "home_score"] = .5
    else:
        source["elo_diff"] = 0.
    with pytest.raises(ValueError):
        st.build_training_manifest(source, registry)


def test_unknown_team_fail_no_id_inference(toy):
    source, registry = toy
    source = source.copy()
    source.loc[0, "home_team"] = "Unknown Club"
    with pytest.raises(UnknownTeamError):
        st.build_training_manifest(source, registry)


def test_same_date_duplicate_team_rejected(toy):
    source, registry = toy
    source = source.copy()
    source.loc[1, "home_team"] = "Club1"
    with pytest.raises(st.ST2ArtifactError, match="Same-date"):
        st.build_training_manifest(source, registry)


def test_all_day_captures_before_updates(toy, monkeypatch):
    source, registry = toy
    events = []
    capture, apply = st._capture, st._apply

    def read(row, ratings, counts):
        events.append((row.match_date, "read"))
        return capture(row, ratings, counts)

    def update(row, values, ratings, counts):
        events.append((row.match_date, "update"))
        return apply(row, values, ratings, counts)

    monkeypatch.setattr(st, "_capture", read)
    monkeypatch.setattr(st, "_apply", update)
    st.build_training_manifest(source, registry)
    for day in source.match_date.unique():
        kinds = [kind for stamp, kind in events if stamp.strftime("%Y-%m-%d") == day]
        n = sum(source.match_date.eq(day))
        assert kinds == ["read"] * n + ["update"] * n


def test_target_and_peer_and_future_results_cannot_change_prior_features(toy):
    source, registry = toy
    baseline = st.build_training_manifest(source, registry).to_frame()
    changed = source.copy()
    changed.loc[0, ["result", "home_score", "away_score"]] = [2, 1, 0]
    after = st.build_training_manifest(changed, registry).to_frame()
    assert after.elo_diff.iloc[0] == baseline.elo_diff.iloc[0] == 0.
    assert after.elo_diff.iloc[1] == baseline.elo_diff.iloc[1] == 0.
    changed = source.copy()
    changed.loc[len(changed)-1, ["result", "home_score", "away_score"]] = [0, 0, 1]
    pd.testing.assert_frame_equal(st.build_training_manifest(changed, registry).to_frame().iloc[:-1], baseline.iloc[:-1])


@pytest.mark.parametrize("home,away,expected", [(1, 1, 45.), (5, 5, 45.), (5, 6, 45.), (6, 5, 45.), (6, 6, 30.), (9, 2, 45.), (9, 9, 30.)])
def test_frozen_match_k_ordinals(home, away, expected):
    assert st.match_k(home, away) == expected


@pytest.mark.parametrize("value", [0, -1, True, 1.0, "1"])
def test_invalid_ordinals_rejected(value):
    with pytest.raises(st.ST2ArtifactError):
        st.match_k(value, 1)


def test_actual_replay_five_six_asymmetric_reset_no_regression_2025(monkeypatch):
    source = pd.DataFrame([match(2015, i+1, i, 1, 2, i % 3) for i in range(6)] + [
        match(2015, 7, 6, 1, 3, 2, stage="2nd"), match(2025, 1, 0, 1, 2, 0)])
    pin_population(monkeypatch, source)
    reads, updates = [], []
    capture, apply = st._capture, st._apply

    def read(row, ratings, counts):
        values = capture(row, ratings, counts)
        reads.append((row, values))
        return values

    def update(row, values, ratings, counts):
        apply(row, values, ratings, counts)
        updates.append(ratings.copy())

    monkeypatch.setattr(st, "_capture", read)
    monkeypatch.setattr(st, "_apply", update)
    manifest = st.build_training_manifest(source, master()).to_frame()
    assert reads[4][1][2:5] == (5, 5, 45.)
    assert reads[5][1][2:5] == (6, 6, 30.)
    assert reads[6][1][2:5] == (7, 1, 45.)  # Asynchronous appearances, not round.
    assert reads[7][1][2:5] == (1, 1, 45.)  # Including 2025, despite ten-year gap.
    assert reads[7][1][0] == updates[6][ROSTER[0]]  # No regression during absence.
    assert reads[7][1][1] == updates[6][ROSTER[1]]
    for state in updates:
        assert sum(state.values()) == pytest.approx(1500. * len(ROSTER), abs=1e-10)
    assert manifest.elo_diff.iloc[7] == reads[7][1][0] - reads[7][1][1]


def test_home_advantage_expectation_only_zero_sum(monkeypatch):
    source = pd.DataFrame([match(2025, 1, 0), match(2025, 2, 1, result=1)])
    pin_population(monkeypatch, source)
    result = st.build_training_manifest(source, master()).to_frame()
    expected = 1 / (1 + 10 ** (-175. / 400.))
    delta = 45. * (1. - expected)
    assert result.elo_diff.iloc[0] == 0.
    assert result.elo_diff.iloc[1] == (1500. + delta) - (1500. - delta)


def test_source_hash_before_any_parse(synthetic_root, monkeypatch):
    root, auth = synthetic_root
    last = root / list(st.SOURCE_HASHES)[-1]
    last.write_bytes(last.read_bytes() + b"\n")
    monkeypatch.setattr(st, "parse_csv", lambda *_: pytest.fail("parse before all SHA gates"))
    monkeypatch.setattr(st, "parse_master", lambda *_: pytest.fail("master parsed before SHA gates"))
    with pytest.raises(st.ST2ArtifactError, match="Frozen SHA"):
        st.create_artifact(root=root, authorization=auth)
    assert not (root / st.ATTEMPT_PATH).exists()


def test_snapshot_loading_no_toctou_master_or_source(synthetic_root):
    root, _ = synthetic_root
    snapshots = st.snapshot_inputs(root)
    (root / st.TEAM_MASTER_PATH).write_bytes(b"untrusted replacement")
    (root / list(st.SOURCE_HASHES)[0]).write_bytes(b"untrusted replacement")
    source, registry = st.load_sources(snapshots)
    assert len(st.build_training_manifest(source, registry).to_frame()) == st.EXPECTED_ROWS


def test_exact_fit_kwargs_training_statistics_single_feature(toy, monkeypatch):
    source, registry = toy
    training = st.build_training_manifest(source, registry)
    calls = {"scaler": 0, "classifier": 0}
    scaler_fit, lr_fit = StandardScaler.fit, LogisticRegression.fit

    def scaler(self, x, *args, **kwargs):
        calls["scaler"] += 1
        assert x.shape == (st.EXPECTED_ROWS, 1) and x.dtype == np.float64
        assert self.get_params() == {"copy": True, "with_mean": True, "with_std": True}
        return scaler_fit(self, x, *args, **kwargs)

    def classifier(self, x, y, *args, **kwargs):
        calls["classifier"] += 1
        assert not args and not kwargs
        assert self.get_params() == LogisticRegression(C=1., solver="lbfgs", max_iter=1000, random_state=0).get_params()
        return lr_fit(self, x, y)

    monkeypatch.setattr(StandardScaler, "fit", scaler)
    monkeypatch.setattr(LogisticRegression, "fit", classifier)
    fitted = st.fit_frozen_st2(training)
    assert calls == {"scaler": 1, "classifier": 1}
    assert tuple(fitted.model.classes_) == st.CLASS_ORDER
    assert fitted.scaler.n_samples_seen_ == st.EXPECTED_ROWS
    assert fitted.scaler.mean_[0] == np.mean(training.to_frame().elo_diff)
    assert fitted.scaler.var_[0] == np.var(training.to_frame().elo_diff)


def test_synthetic_repeated_fit_state_deterministic(toy):
    training = st.build_training_manifest(*toy)
    first, second = st.fit_frozen_st2(training), st.fit_frozen_st2(training)
    assert st.fitted_state(first, st.EXPECTED_ROWS) == st.fitted_state(second, st.EXPECTED_ROWS)


def test_fit_only_validated_manifest_and_seal(toy):
    training = st.build_training_manifest(*toy)
    with pytest.raises(st.ST2ArtifactError, match="Validated"):
        st.fit_frozen_st2(training.to_frame())
    with pytest.raises(st.ST2ArtifactError, match="seal"):
        st.fit_frozen_st2(replace(training, csv_bytes=training.csv_bytes + b"\n"))


@pytest.mark.parametrize("case", ["extra", "order", "float32", "infinite", "class", "season", "unknown", "duplicate", "date"])
def test_manifest_gate_rejects_unvalidated_inputs(toy, case):
    training = st.build_training_manifest(*toy)
    frame = training.to_frame()
    if case == "extra":
        frame["home_rating"] = 1500.
    elif case == "order":
        frame = frame[list(st.MANIFEST_COLUMNS)[::-1]]
    elif case == "float32":
        frame["elo_diff"] = frame.elo_diff.astype("float32")
    elif case == "infinite":
        frame.loc[0, "elo_diff"] = np.inf
    elif case == "class":
        frame.loc[0, "target_class"] = 3
    elif case == "season":
        frame.loc[0, "season"] = 2026
    elif case == "unknown":
        frame.loc[0, "home_team_id"] = "team_9999"
    elif case == "duplicate":
        frame.loc[1, "match_id"] = frame.loc[0, "match_id"]
    else:
        frame.loc[0, "match_date"] = "2015-1-1"
    with pytest.raises(st.ST2ArtifactError):
        st.validate_training_manifest(frame, training.registered_ids)


def test_fit_requires_all_classes(toy):
    training = st.build_training_manifest(*toy)
    frame = training.to_frame()
    frame["target_class"] = 1
    training = st.validate_training_manifest(frame, training.registered_ids)
    with pytest.raises(st.ST2ArtifactError, match="All three"):
        st.fit_frozen_st2(training)


def test_warning_is_technical_stop_no_retry(synthetic_root, monkeypatch):
    root, _ = synthetic_root
    calls = []

    def warning(*args, **kwargs):
        calls.append(1)
        warnings.warn("synthetic nonconvergence", ConvergenceWarning)

    monkeypatch.setattr(LogisticRegression, "fit", warning)
    with pytest.raises(st.ST2ArtifactError, match="ConvergenceWarning"):
        create(synthetic_root)
    assert len(calls) == 1
    marker = (root / st.ATTEMPT_PATH).read_bytes()
    assert json.loads(marker)["state"] == "ATTEMPT_CONSUMED"
    with pytest.raises(st.ST2ArtifactError, match="consumed"):
        create(synthetic_root)
    assert (root / st.ATTEMPT_PATH).read_bytes() == marker and len(calls) == 1


def test_orchestration_exact_one_fit_five_files_and_metadata(synthetic_root, monkeypatch):
    root, _ = synthetic_root
    calls = []
    original = st.fit_frozen_st2

    def once(*args, **kwargs):
        calls.append(1)
        return original(*args, **kwargs)

    monkeypatch.setattr(st, "fit_frozen_st2", once)
    artifact = create(synthetic_root)
    path, metadata = root / st.OUTPUT_PATH, artifact.metadata
    assert calls == [1]
    assert tuple(sorted(p.name for p in path.iterdir())) == st.ARTIFACT_FILES
    assert artifact.artifact_hash == st.sha256((path / "checksums.sha256").read_bytes())
    assert [line.split()[1] for line in (path / "checksums.sha256").read_text().splitlines()] == list(st.CHECKSUM_FILES)
    assert metadata["spec"] == {"path": st.SPEC_PATH, "commit": st.SPEC_COMMIT, "sha256": st.SPEC_SHA}
    assert metadata["future_rows_used"] == 0 and metadata["metrics_calculated"] is False and metadata["predictions_generated"] is False
    assert metadata["fit_count"] == metadata["scaler_fit_count"] == 1 and metadata["retry_count"] == 0
    assert metadata["fit_progress"] == {**st.new_progress(), "scaler_fit_attempts": 1, "scaler_fits_completed": 1, "classifier_fit_attempts": 1, "classifier_fits_completed": 1}
    assert metadata["source_byte_pins"] == st.SOURCE_HASHES
    assert metadata["training_match_ids_hash"] == st.ordered_id_hash(st.parse_manifest((path / "training_manifest.csv").read_bytes()).match_id)
    assert metadata["training_manifest_hash"] == st.sha256((path / "training_manifest.csv").read_bytes())
    for forbidden in ("home_rating", "away_rating", "home_season_appearance", "away_season_appearance", "match_k", "probabilities", "accuracy", "log_loss", "brier"):
        assert forbidden not in metadata
    assert json.loads((root / st.ATTEMPT_PATH).read_bytes())["state"] == "ATTEMPT_CONSUMED"


@pytest.mark.parametrize("existing", ["output", "marker"])
def test_existing_output_or_attempt_refused_before_source_read(synthetic_root, monkeypatch, existing):
    root, _ = synthetic_root
    path = root / (st.OUTPUT_PATH if existing == "output" else st.ATTEMPT_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"existing evidence")
    monkeypatch.setattr(st, "snapshot_inputs", lambda *_: pytest.fail("read after consumed/existing output"))
    with pytest.raises(st.ST2ArtifactError, match="Existing"):
        create(synthetic_root)
    assert path.read_bytes() == b"existing evidence"


def test_reload_no_fit_or_prediction(synthetic_root, monkeypatch):
    root, _ = synthetic_root
    artifact = create(synthetic_root)

    def forbidden(*args, **kwargs):
        pytest.fail("reload tried to fit/transform")

    for owner, name in ((StandardScaler, "fit"), (StandardScaler, "fit_transform"), (StandardScaler, "transform"), (LogisticRegression, "fit")):
        monkeypatch.setattr(owner, name, forbidden)
    reloaded = st.load_artifact(root / st.OUTPUT_PATH, expected_artifact_hash=artifact.artifact_hash)
    assert reloaded.metadata == artifact.metadata


@pytest.mark.parametrize("name", st.ARTIFACT_FILES)
def test_corrupt_artifact_hash_or_coverage_hard_fail(synthetic_root, name):
    root, _ = synthetic_root
    create(synthetic_root)
    target = root / st.OUTPUT_PATH / name
    target.write_bytes(target.read_bytes() + b"corrupt")
    with pytest.raises(st.ST2ArtifactError):
        st.load_artifact(root / st.OUTPUT_PATH)


def test_extra_file_rejected(synthetic_root):
    root, _ = synthetic_root
    create(synthetic_root)
    (root / st.OUTPUT_PATH / "extra.txt").write_bytes(b"extra")
    with pytest.raises(st.ST2ArtifactError, match="five"):
        st.load_artifact(root / st.OUTPUT_PATH)


@pytest.mark.parametrize("key,value", [("role", "champion"), ("training_row_count", 1), ("fit_count", 2),
                                      ("scaler_fit_count", 2), ("future_rows_used", 1), ("metrics_calculated", True),
                                      ("predictions_generated", True), ("retry_count", 1), ("feature_list", ["elo_diff", "extra"]),
                                      ("training_match_ids_hash", "wrong"), ("training_manifest_hash", "wrong"),
                                      ("model_hash", "wrong"), ("scaler_hash", "wrong")])
def test_metadata_linkage_tamper_rejected_even_rehashed(synthetic_root, key, value):
    root, _ = synthetic_root
    artifact = create(synthetic_root)
    path = root / st.OUTPUT_PATH
    metadata = dict(artifact.metadata)
    metadata[key] = value
    (path / "metadata.json").write_bytes(st.json_bytes(metadata))
    rewrite_checksums(path)
    with pytest.raises(st.ST2ArtifactError):
        st.load_artifact(path)


@pytest.mark.parametrize("case", ["classes", "width", "samples", "nan", "parameters"])
def test_reloaded_state_tamper_rejected(synthetic_root, case):
    root, _ = synthetic_root
    create(synthetic_root)
    path = root / st.OUTPUT_PATH
    model, scaler = joblib.load(path / "model.joblib"), joblib.load(path / "scaler.joblib")
    if case == "classes":
        model.classes_ = np.array([2, 1, 0])
    elif case == "width":
        model.n_features_in_ = 2
    elif case == "samples":
        scaler.n_samples_seen_ += 1
    elif case == "nan":
        scaler.mean_[0] = np.nan
    else:
        model.C = 2.
    joblib.dump(model, path / "model.joblib")
    joblib.dump(scaler, path / "scaler.joblib")
    metadata = json.loads((path / "metadata.json").read_bytes())
    metadata["model_hash"], metadata["scaler_hash"] = (st.sha256((path / n).read_bytes()) for n in ("model.joblib", "scaler.joblib"))
    (path / "metadata.json").write_bytes(st.json_bytes(metadata))
    rewrite_checksums(path)
    with pytest.raises(st.ST2ArtifactError):
        st.load_artifact(path)


def test_failed_fit_preserves_consumed_marker_and_partial_directory(synthetic_root, monkeypatch):
    root, _ = synthetic_root
    monkeypatch.setattr(LogisticRegression, "fit", lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("synthetic fit failure")))
    with pytest.raises(st.ST2ArtifactError, match="classifier_fit_attempts.*1"):
        create(synthetic_root)
    assert (root / st.OUTPUT_PATH).is_dir()
    marker = (root / st.ATTEMPT_PATH).read_bytes()
    with pytest.raises(st.ST2ArtifactError, match="Existing"):
        create(synthetic_root)
    assert marker == (root / st.ATTEMPT_PATH).read_bytes()


def test_postfit_source_mutation_fails_without_retry(synthetic_root, monkeypatch):
    root, _ = synthetic_root
    original = st.fit_frozen_st2
    calls = []

    def change(*args, **kwargs):
        calls.append(1)
        result = original(*args, **kwargs)
        (root / list(st.SOURCE_HASHES)[0]).write_bytes(b"changed during fit")
        return result

    monkeypatch.setattr(st, "fit_frozen_st2", change)
    with pytest.raises(st.ST2ArtifactError, match="Immutable input changed"):
        create(synthetic_root)
    assert calls == [1] and not (root / st.OUTPUT_PATH / "checksums.sha256").exists()


@pytest.mark.parametrize("auth", [None, {}, {"approved_execution_head": "b"*40, "task_reference": "toy"},
                                  {"approved_execution_head": "a"*40, "task_reference": ""}])
def test_separate_authorization_required_before_sources(synthetic_root, monkeypatch, auth):
    root, _ = synthetic_root
    monkeypatch.setattr(st, "snapshot_inputs", lambda *_: pytest.fail("read before authority gate"))
    with pytest.raises(st.ST2ArtifactError, match="authorization"):
        st.create_artifact(root=root, authorization=auth)


def test_import_and_help_no_io_or_heavy_import(monkeypatch, capsys):
    original_import = builtins.__import__

    def stdlib_only(name, *args, **kwargs):
        if name.startswith(("numpy", "pandas", "sklearn", "joblib", "src.collect", "src.features")):
            pytest.fail(f"import/help loaded heavy or evidence module: {name}")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", stdlib_only)
    namespace = runpy.run_path(str(MODULE_FILE), run_name="synthetic_import_check")
    with pytest.raises(SystemExit) as exited:
        namespace["main"](["--help"])
    assert exited.value.code == 0 and "--create-artifact" in capsys.readouterr().out


def test_default_cli_does_not_execute(monkeypatch):
    monkeypatch.setattr(st, "create_artifact", lambda **_: pytest.fail("default CLI created artifact"))
    with pytest.raises(SystemExit) as exited:
        st.main([])
    assert exited.value.code == 2


def test_no_prediction_metrics_discovery_or_other_lane_calls():
    tree = ast.parse(MODULE_FILE.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            assert node.func.attr not in {"predict", "predict_proba", "score", "glob", "rglob", "partial_fit"}
        if isinstance(node, ast.ImportFrom):
            assert node.module is None or not node.module.startswith("sklearn.metrics")
    assert not any("trace" in key for key in st.MANIFEST_COLUMNS)


@pytest.mark.parametrize("relative", ["data/processed/jleague/2015_matches_probe.csv", "data/master/teams.csv",
                                      "models/model_season_transition", "models/model_a", "data/processed/predictions",
                                      "data/processed/jleague/2026_27", "data/processed/jleague/2026_hyakunen"])
def test_production_io_guard_actually_blocks(relative):
    with pytest.raises(AssertionError, match="PRODUCTION IO"):
        (REPO / relative).read_bytes()
    with pytest.raises(AssertionError, match="PRODUCTION IO"):
        (REPO / relative).write_bytes(b"forbidden")


def test_network_guard_actually_blocks():
    with pytest.raises(AssertionError, match="NETWORK"):
        socket.create_connection(("example.invalid", 80))
