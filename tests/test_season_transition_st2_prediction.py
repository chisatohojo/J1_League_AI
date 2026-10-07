"""Synthetic-only ST2/A comparison tests; production IO/network/fit blocked."""

import ast
import builtins
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import socket
from types import SimpleNamespace

import joblib
import numpy as np
import pandas as pd
import pytest
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

from src.modeling import prediction_identity as identity
from src.modeling import season_transition_st2_artifact as authority
from src.modeling import season_transition_st2_prediction as p


NOW = datetime(2026, 10, 8, 0, tzinfo=timezone.utc)
HISTORY_COLUMNS = ("match_id", "season", "match_date", "home_team_id", "away_team_id", "result")


@pytest.fixture(autouse=True)
def firewall(monkeypatch):
    forbidden = [p.ROOT / relative for relative in (
        "data/processed/jleague", "data/master", "models", "data/processed/predictions")]
    def guard(original):
        def wrapped(file, *args, **kwargs):
            if isinstance(file, (str, bytes, Path)):
                path = Path(file).resolve()
                assert not any(path.is_relative_to(root) for root in forbidden), f"Production IO forbidden: {path}"
            return original(file, *args, **kwargs)
        return wrapped
    monkeypatch.setattr(builtins, "open", guard(builtins.open))
    monkeypatch.setattr(io, "open", guard(io.open))
    monkeypatch.setattr(p.os, "open", guard(p.os.open))
    def denied(*args, **kwargs):
        raise AssertionError("Network/fit/score forbidden")
    monkeypatch.setattr(socket, "create_connection", denied)
    monkeypatch.setattr(socket.socket, "connect", denied)
    for cls in (StandardScaler, LogisticRegression):
        for name in ("fit", "fit_transform", "partial_fit", "score"):
            if hasattr(cls, name):
                monkeypatch.setattr(cls, name, denied)


def empty_history():
    return pd.DataFrame(columns=HISTORY_COLUMNS)


def history(rows):
    return pd.DataFrame(rows, columns=HISTORY_COLUMNS)


def synthetic_model():
    # Persist manually assigned synthetic fitted state. NEVER fit in these tests.
    scaler = StandardScaler()
    scaler.n_features_in_, scaler.n_samples_seen_ = 1, np.int64(3588)
    scaler.mean_, scaler.var_, scaler.scale_ = np.array([3.]), np.array([4.]), np.array([2.])
    model = LogisticRegression(C=1.0, solver="lbfgs", max_iter=1000, random_state=0)
    model.classes_, model.n_features_in_ = np.array([0, 1, 2]), 1
    model.coef_, model.intercept_, model.n_iter_ = np.array([[-.1], [0.], [.1]]), np.zeros(3), np.array([4])
    return scaler, model


def branches():
    scaler, model = synthetic_model()
    return (p.FrozenModel(scaler, model, p.CHAMPION_A_ARTIFACT_HASH, {}),
            p.FrozenModel(scaler, model, p.ST2_ARTIFACT_HASH, {}))


def schedules():
    rows = []
    for i in range(4):
        home, away = ("a", "b") if i % 2 == 0 else ("c", "d")
        if i < 2:
            home, away = away, home
        rows.append({"fixture_key": f"j1_2026_2027:{home}:{away}", "match_id": str(100901 + i),
                     "match_date": "2026-09-20" if i < 2 else "2026-10-09", "kickoff_time": "19:00",
                     "home_team": home.upper(), "away_team": away.upper(), "home_club": home,
                     "away_club": away, "status": "completed" if i < 2 else "scheduled",
                     "competition_key": "j1_2026_2027", "season": "2026", "match_id_namespace": "",
                     "match_page_id": "", "data_site_match_id": "",
                     "evidence_type": "official_game_over_section" if i < 2 else "official_completion_unconfirmed",
                     "evidence_url": f"https://www.jleague.jp/match/j1/2026/{100901 + i}/",
                     "evidence_sha256": "a" * 64, "evidence_fetched_at_utc": "2026-10-03T00:00:00+00:00"})
    return pd.DataFrame(rows)


@pytest.fixture
def small_scope(monkeypatch):
    monkeypatch.setattr(p, "EXPECTED_SCHEDULE_ROWS", 4)
    monkeypatch.setattr(p, "EXPECTED_COHORT_ROWS", 2)


def targets():
    frame = schedules().iloc[2:].reset_index(drop=True)
    frame["home_team_id"] = ["team_0001", "team_0003"]
    frame["away_team_id"] = ["team_0002", "team_0004"]
    frame["match_id_namespace"] = identity.MATCH_PAGE_NAMESPACE
    return frame


def master():
    from src.collect.teams import TeamAlias, TeamMaster
    return TeamMaster([TeamAlias(f"team_{i:04}", name, name, "jleague_data_site", None, None, "")
                       for i, name in enumerate("ABCD", 1)])


def source_binding(target, *, artifact="baseline.csv", version="baseline-v1", witness="1" * 64, witness_sha="2" * 64):
    target = target.copy()
    target["match_id_namespace"] = identity.MATCH_PAGE_NAMESPACE
    row = {"match_id": target.match_id, "model_version": version,
           "match_date": target.match_date, "home_team_id": target.home_team_id,
           "away_team_id": target.away_team_id, "prediction_generated_at": NOW.isoformat()}
    return identity.make_binding_rows(pd.DataFrame([row]), pd.DataFrame([target]), prediction_artifact=artifact,
                                     identity_witness_revision_id=witness, identity_witness_manifest_sha256=witness_sha)


def records():
    state = p.LiveStates({f"team_{i:04}": 1500. for i in range(1, 5)},
                         {f"team_{i:04}": 1500. for i in range(1, 5)}, {}, [])
    return p.generate_prediction_records(targets(), state, *branches(), now=NOW,
                                         source_revision="1" * 64, source_observed_at="2026-10-03T00:00:00+00:00")


def revision_stub(version="ongoing-v1"):
    return p.Revision("1" * 64, "2" * 64, {"format_version": version,
                     "summary": {"observed_at_utc": "2026-10-03T00:00:00+00:00"}}, {})


def write_revision(root, schedule, *, version="ongoing-v1", name="1" * 64):
    from src.collect.jleague_ongoing import COMPLETION_POLICY
    directory = root / p.ONGOING_PATH / "revisions" / name
    directory.mkdir(parents=True)
    full = schedule.assign(home_score="", away_score="", result="TARGET_OUTCOME_FORBIDDEN")
    full = full.assign(round="1", stadium="Synthetic Stadium", competition="Ｊ１", stage="full_season", completion_origin_snapshot="synthetic-completion")
    done = full.loc[full.status.eq("completed")].copy()
    done["home_score"], done["away_score"], done["result"] = "1", "0", "2"
    bodies = {"schedule.csv": full.to_csv(index=False, lineterminator="\n").encode(),
              "completed_matches.csv": done.to_csv(index=False, lineterminator="\n").encode(),
              "fixture_identity.csv": schedule[["fixture_key", "match_id", "home_club", "away_club"]].to_csv(index=False, lineterminator="\n").encode()}
    manifest = {"format_version": version, "completion_policy": COMPLETION_POLICY, "snapshot_id": p.BOUNDARY_SNAPSHOT_ID,
                "files": {name: p.sha(body) for name, body in bodies.items()},
                "summary": {"publication_status": "published", "observed_at_utc": "2026-10-03T00:00:00+00:00"}}
    for filename, body in bodies.items():
        (directory / filename).write_bytes(body)
    (directory / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return directory, p.sha((directory / "manifest.json").read_bytes())


def test_exact_constants_and_schema():
    assert p.PROSPECTIVE_BOUNDARY == "2026-10-06T18:24:19+09:00"
    assert p.COMPARISON_VERSION == p.MODEL_VERSION == "season_transition_st2_vs_a_20261006_v1"
    assert p.ST2_MODEL_VERSION == "season_transition_st2_20261006_v1"
    assert p.ST2_ARTIFACT_HASH == "f20359a1c12a4508d1a593e266a92f25fb8cab597bbbe3ace7a19ae5b0160c82"
    assert p.CHAMPION_A_MODEL_VERSION == "operational_champion_20260922_v1"
    assert p.CHAMPION_A_ARTIFACT_HASH == "2d2e50dbfc4d71ec2cdaf5fe1a6e48953c160c388f1740cfe538f29f593646d1"
    assert p.COHORT_HASH == "b63bce0289b80d096599a2f6343c48073c3617d919b3bf7153683e2089dfdcbf"
    assert p.EXPECTED_COHORT_ROWS == 300 and p.EXPECTED_SCHEDULE_ROWS == 380
    assert p.OUTPUT_PATH == p.ROOT / p.PREDICTION_ARTIFACT
    expected = "fixture_key match_id match_date kickoff home_team_id away_team_id home_team_name away_team_name prediction_generated_at prospective_boundary comparison_version model_version source_revision source_observed_at champion_a_model_version champion_a_artifact_hash st2_model_version st2_artifact_hash a_elo_diff st2_elo_diff a_p_away a_p_draw a_p_home st2_p_away st2_p_draw st2_p_home a_predicted_class st2_predicted_class"
    assert p.PREDICTION_COLUMNS == tuple(expected.split()) and len(p.PREDICTION_COLUMNS) == 28


def test_frozen_cohort_hash_and_revision_validation(tmp_path, monkeypatch, small_scope):
    directory, digest = write_revision(tmp_path, schedules(), name=p.BOUNDARY_REVISION)
    monkeypatch.setattr(p, "BOUNDARY_MANIFEST_SHA", digest)
    rev = p.read_revision(directory, expected_sha=digest)
    monkeypatch.setattr(p, "BOUNDARY_FILE_PINS", rev.manifest["files"])
    raw = tmp_path / p.BOUNDARY_RAW_MANIFEST
    raw.parent.mkdir(parents=True)
    raw.write_bytes(b"synthetic raw snapshot")
    monkeypatch.setattr(p, "BOUNDARY_RAW_MANIFEST_SHA", p.sha(raw.read_bytes()))
    keys = schedules().iloc[2:].sort_values(["match_date", "fixture_key"]).fixture_key
    monkeypatch.setattr(p, "COHORT_HASH", p.sha(("\n".join(keys) + "\n").encode()))
    _, cohort = p.frozen_cohort(tmp_path)
    assert cohort.fixture_key.tolist() == keys.tolist()
    schedule, done = p.validate_revision_schedule(rev)
    assert "result" not in schedule and done.result.tolist() == ["2", "2"]
    monkeypatch.setattr(p, "COHORT_HASH", "0" * 64)
    with pytest.raises(p.ST2PredictionError, match="sequence hash"):
        p.frozen_cohort(tmp_path)
    (directory / "schedule.csv").write_bytes(b"corrupt")
    with pytest.raises(p.ST2PredictionError, match="file hash"):
        p.read_revision(directory, expected_sha=digest)


def test_postponement_retains_membership_nearest_full_batch(small_scope):
    frozen = schedules()
    cohort = frozen.iloc[2:]
    current = frozen.copy()
    current.loc[2, "match_date"] = "2026-10-18"
    batch = p.select_next_date_batch(current, frozen, cohort)
    assert batch.fixture_key.tolist() == [current.loc[3, "fixture_key"]]
    current.loc[3, "status"] = "completed"
    assert p.select_next_date_batch(current, frozen, cohort).match_date.tolist() == ["2026-10-18"]
    batch = p.select_next_date_batch(frozen, frozen, cohort)
    assert len(batch) == 2
    assert set(batch.fixture_key) == set(cohort.fixture_key)
    bad = frozen.copy()
    bad.loc[2, "home_team"] = "replacement"
    with pytest.raises(p.ST2PredictionError, match="identity"):
        p.select_next_date_batch(bad, frozen, cohort)


@pytest.mark.parametrize("change", ["missing", "extra", "cross_boundary", "baseline_revert"])
def test_schedule_reconciliation_fails(small_scope, change):
    frozen, current = schedules(), schedules()
    if change == "missing":
        current = current.iloc[:-1]
    elif change == "extra":
        current.loc[2, "fixture_key"] = "j1_2026_2027:a:unknown"
    elif change == "cross_boundary":
        current.loc[2, "match_date"] = "2026-10-06"
    else:
        current.loc[0, "status"] = "scheduled"
    with pytest.raises(p.ST2PredictionError):
        p.select_next_date_batch(current, frozen, frozen.iloc[2:])


def test_v1_unique_reviewed_binding_and_witness(tmp_path, small_scope):
    directory, digest = write_revision(tmp_path, schedules())
    batch = targets().assign(match_id_namespace="")
    evidence = pd.concat([source_binding(row, witness_sha=digest) for _, row in batch.iterrows()], ignore_index=True)
    rev = p.read_revision(directory)
    resolved, witnesses = p.resolve_target_identity(batch, evidence, rev, root=tmp_path, master=master())
    assert resolved.match_id_namespace.tolist() == [identity.MATCH_PAGE_NAMESPACE] * 2
    assert witnesses == [("1" * 64, digest)] * 2
    bindings = p.make_comparison_bindings(records(), resolved, witnesses)
    assert len(bindings) == 2 and bindings.prediction_artifact.eq(p.PREDICTION_ARTIFACT).all()
    # Evidence from multiple models is allowed only when all identity fields agree.
    duplicate_evidence = evidence.copy().assign(model_version="baseline-v2")
    p.resolve_target_identity(batch, pd.concat([evidence, duplicate_evidence]), rev, root=tmp_path, master=master())
    duplicate_evidence.loc[0, "identity_witness_manifest_sha256"] = "f" * 64
    with pytest.raises(p.ST2PredictionError, match="conflicting"):
        p.resolve_target_identity(batch, pd.concat([evidence, duplicate_evidence]), rev, root=tmp_path, master=master())


@pytest.mark.parametrize("problem", ["no_binding", "blank_id", "different_id", "wrong_team", "wrong_date"])
def test_v1_identity_hard_fail_no_numeric_inference(tmp_path, problem):
    batch = targets().iloc[[0]].assign(match_id_namespace="")
    binding = source_binding(batch.iloc[0])
    if problem == "no_binding":
        binding = binding.iloc[:0]
    elif problem == "blank_id":
        batch.loc[0, "match_id"] = ""
    elif problem == "different_id":
        binding.loc[0, "prediction_match_id"] = "42"
    elif problem == "wrong_team":
        binding.loc[0, "home_team_id"] = "team_0049"
    else:
        binding.loc[0, "match_date"] = "2026-10-10"
    with pytest.raises(p.ST2PredictionError):
        p.resolve_target_identity(batch, binding, revision_stub(), root=tmp_path, master=master())


def test_no_id_available_subset(tmp_path, monkeypatch):
    batch = targets().assign(match_id_namespace="")
    batch.loc[1, "match_id"] = ""
    evidence = source_binding(batch.iloc[0])
    monkeypatch.setattr(p, "validate_witness", lambda *args: revision_stub())
    with pytest.raises(p.ST2PredictionError, match="no ID-available subset"):
        p.resolve_target_identity(batch, evidence, revision_stub(), root=tmp_path, master=master())


@pytest.mark.parametrize("namespace,field,value", [(identity.MATCH_PAGE_NAMESPACE, "match_page_id", "100903"), (identity.DATA_SITE_NAMESPACE, "data_site_match_id", "42")])
def test_v2_explicit_namespace_and_witness(tmp_path, small_scope, namespace, field, value):
    schedule = schedules()
    schedule.loc[2:, "match_id_namespace"] = namespace
    schedule.loc[2, [field, "match_id"]] = value
    schedule.loc[3, [field, "match_id"]] = "100904" if namespace == identity.MATCH_PAGE_NAMESPACE else "43"
    directory, _ = write_revision(tmp_path, schedule, version="ongoing-v2")
    rev = p.read_revision(directory)
    batch = p.resolve_team_ids(schedule.iloc[2:], master())
    resolved, _ = p.resolve_target_identity(batch, pd.DataFrame(columns=identity.BINDING_COLUMNS), rev, root=tmp_path, master=master())
    assert resolved.match_id_namespace.eq(namespace).all()
    batch.loc[2, "match_id_namespace"] = ""
    with pytest.raises(p.ST2PredictionError, match="Explicit v2"):
        p.resolve_target_identity(batch, pd.DataFrame(columns=identity.BINDING_COLUMNS), rev, root=tmp_path, master=master())


def test_replay_ordinals_k_reset_hyakunen_and_carry():
    ordinary = history([(f"m{i}", 2025, f"2025-01-{i:02}", "a", "b", 2) for i in range(1, 7)]
                       + [("new-season", 2015, "2015-01-01", "a", "b", 1)])
    special = history([("special", 2026, "2026-05-01", "a", "b", 1)])
    ongoing = history([("first80", 2026, "2026-08-01", "a", "b", 2),
                       ("later", 2026, "2027-01-01", "a", "c", 0)])
    state = p.replay_live_states(ordinary, special, ongoing, ["a", "b", "c"], target_date="2027-02-01")
    captures = {r["match_id"]: r for r in state.captures}
    assert captures["m1"]["home_ordinal"] == 1
    assert captures["m5"]["st2_k"] == 45 and captures["m6"]["st2_k"] == 30
    assert captures["special"]["st2_k"] == 30
    assert captures["first80"]["home_ordinal"] == 1 and captures["first80"]["st2_k"] == 45
    assert captures["first80"]["st2_elo_diff"] != 0  # ratings carry, not reset
    assert captures["later"]["home_ordinal"] == 2  # no January reset
    assert state.ordinals == {"a": 2, "b": 1, "c": 1}
    assert state.a is not state.st2 and state.a != state.st2


def test_asymmetric_ordinal_and_a_always_k30():
    ordinary = history([(f"m{i}", 2025, f"2025-01-{i:02}", "a", "b", 2) for i in range(1, 7)]
                       + [("asym", 2025, "2025-01-07", "a", "c", 2)])
    state = p.replay_live_states(ordinary, empty_history(), empty_history(), ["a", "b", "c"], target_date="2026-10-09")
    last = state.captures[-1]
    assert last["home_ordinal"] == 7 and last["away_ordinal"] == 1 and last["st2_k"] == 45
    from src.features.elo import EloRatings
    oracle = EloRatings(["a", "b", "c"], k_factor=30, home_advantage=175)
    for row in ordinary.itertuples():
        oracle.update(row.home_team_id, row.away_team_id, row.result)
    assert state.a == oracle.ratings


def test_same_date_capture_then_update_and_raw_diff():
    ordinary = history([("m1", 2025, "2025-01-01", "a", "b", 2), ("m2", 2025, "2025-01-01", "c", "d", 0)])
    state = p.replay_live_states(ordinary, empty_history(), empty_history(), list("abcd"), target_date="2026-10-09")
    assert [r["a_elo_diff"] for r in state.captures] == [0, 0]
    assert [r["st2_elo_diff"] for r in state.captures] == [0, 0]
    assert sum(state.a.values()) == 6000 and sum(state.st2.values()) == 6000
    reverse = p.replay_live_states(ordinary.iloc[::-1], empty_history(), empty_history(), list("abcd"), target_date="2026-10-09")
    assert state == reverse
    ordinary.loc[1, "home_team_id"] = "a"
    with pytest.raises(p.ST2PredictionError, match="Duplicate"):
        p.replay_live_states(ordinary, empty_history(), empty_history(), list("abcd"), target_date="2026-10-09")


@pytest.mark.parametrize("day", ["2026-10-09", "2026-10-10"])
def test_history_target_or_peer_date_rejected(day):
    with pytest.raises(p.ST2PredictionError, match="strictly earlier"):
        p.replay_live_states(empty_history(), empty_history(), history([("x", 2026, day, "a", "b", 2)]), ["a", "b"], target_date="2026-10-09")


@pytest.mark.parametrize("value", [True, 1.5, -1, 3])
def test_invalid_history_result(value):
    with pytest.raises(p.ST2PredictionError, match="result class"):
        p.replay_live_states(history([("x", 2025, "2025-01-01", "a", "b", value)]), empty_history(), empty_history(), ["a", "b"], target_date="2026-10-09")


def test_end_to_end_records_deterministic_no_fit_and_argmax():
    first, second = records(), records()
    pd.testing.assert_frame_equal(first, second, check_exact=True)
    assert tuple(first.columns) == p.PREDICTION_COLUMNS
    assert first.model_version.eq(p.COMPARISON_VERSION).all()
    assert first.source_revision.eq("1" * 64).all()
    assert first.source_observed_at.eq("2026-10-03T00:00:00+00:00").all()
    a, _ = branches()
    assert a.scaler.n_samples_seen_ == 3588
    assert not {"result", "home_score", "away_score", "accuracy", "correct"} & set(first)
    class TieModel:
        classes_, n_features_in_ = np.array([0, 1, 2]), 1
        def predict_proba(self, matrix):
            return np.tile([.4, .4, .2], (len(matrix), 1))
    tied = p.FrozenModel(a.scaler, TieModel(), p.CHAMPION_A_ARTIFACT_HASH, {})
    state = p.LiveStates(dict.fromkeys(targets().home_team_id.tolist() + targets().away_team_id.tolist(), 1500), {}, {}, [])
    state.st2 = state.a.copy()
    result = p.generate_prediction_records(targets(), state, tied, branches()[1], now=NOW, source_revision="rev", source_observed_at=NOW.isoformat())
    assert result.a_predicted_class.tolist() == [0, 0]


@pytest.mark.parametrize("values", [[[.2, .3, .4]], [[-.1, .5, .6]], [[1.1, 0, -.1]], [[np.nan, .5, .5]], [[np.inf, 0, 0]], [[.5, .5]]])
def test_probability_validation_rejects(values):
    with pytest.raises(p.ST2PredictionError):
        p.validate_probabilities(values, 1)


def test_class_order_and_feature_width_reject():
    a, _ = branches()
    a.model.classes_ = np.array([2, 1, 0])
    with pytest.raises(p.ST2PredictionError, match="class order"):
        p.predict_branch(a, [0])


@pytest.mark.parametrize("clock", [datetime(2026, 10, 6, 9, 24, 19, tzinfo=timezone.utc), datetime(2026, 10, 9, 10, tzinfo=timezone.utc), datetime(2026, 10, 9, 11, tzinfo=timezone.utc), datetime(2026, 10, 8)])
def test_boundary_elapsed_or_naive_clock_rejected(clock):
    with pytest.raises(p.ST2PredictionError):
        p.validate_target_time(targets(), clock)


@pytest.mark.parametrize("kickoff", ["", "TBD", "9:00", "24:00", "19:00:00", "19:60"])
def test_ambiguous_kickoff_rejected(kickoff):
    with pytest.raises(p.ST2PredictionError, match="HH:MM"):
        p.validate_target_time(targets().assign(kickoff_time=kickoff), NOW)


@pytest.mark.parametrize("column,value", [("model_version", "wrong"), ("st2_artifact_hash", "0" * 64), ("source_observed_at", "2026-10-09T00:00:00+00:00"), ("a_predicted_class", "2")])
def test_output_contract_rejects(column, value):
    frame = records()
    frame[column] = value
    with pytest.raises(p.ST2PredictionError):
        p.validate_prediction_records(frame)


def test_extra_outcome_column_rejected():
    with pytest.raises(p.ST2PredictionError, match="28-column"):
        p.validate_prediction_records(records().assign(result=2))


def test_prediction_api_rejects_target_outcome_before_model_call(monkeypatch):
    monkeypatch.setattr(p, "predict_branch", lambda *args: pytest.fail("target outcome reached estimator"))
    with pytest.raises(p.ST2PredictionError, match="Outcome/metric"):
        p.generate_prediction_records(targets().assign(result=2), None, *branches(), now=NOW,
                                      source_revision="revision", source_observed_at=NOW.isoformat())


def test_probability_sum_tolerance_preserves_values():
    values = np.array([[.2, .3, .5 + 5e-13]], dtype=np.float64)
    np.testing.assert_array_equal(p.validate_probabilities(values, 1), values)
    with pytest.raises(p.ST2PredictionError, match="sum"):
        p.validate_probabilities([[.2, .3, .5 + 2e-12]], 1)


@pytest.fixture
def history_sources(tmp_path, monkeypatch, small_scope):
    pins = {}
    for year in authority.TRAINING_SEASONS:
        row = {"match_id": f"ordinary-{year}", "season": year, "round": 1, "match_date": f"{year}-03-01",
               "home_team": "A", "away_team": "B", "stadium": "Synthetic Stadium", "home_score": 1,
               "away_score": 0, "result": 2, "competition": "Ｊ１ １ｓｔ" if year in (2015, 2016) else "Ｊ１",
               "stage": "1st" if year in (2015, 2016) else "full_season"}
        relative = f"data/processed/jleague/{year}_matches_probe.csv"
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(pd.DataFrame([row]).to_csv(index=False, lineterminator="\n").encode("utf-8"))
        pins[relative] = p.sha(path.read_bytes())
    monkeypatch.setattr(authority, "SOURCE_HASHES", pins)
    monkeypatch.setattr(authority, "EXPECTED_ROWS", 11)
    monkeypatch.setattr(authority, "SEASON_COUNTS", {year: 1 for year in authority.TRAINING_SEASONS})
    master_path = tmp_path / authority.TEAM_MASTER_PATH
    master_path.parent.mkdir(parents=True)
    from src.collect.teams import MASTER_COLUMNS
    master_rows = [{"team_id": f"team_{i:04}", "canonical_name": name, "source_name": name, "source": "jleague_data_site",
                    "valid_from": "", "valid_to": "", "source_club_id": ""} for i, name in enumerate("ABCD", 1)]
    master_path.write_bytes(pd.DataFrame(master_rows, columns=MASTER_COLUMNS).to_csv(index=False).encode())
    monkeypatch.setattr(authority, "TEAM_MASTER_SHA", p.sha(master_path.read_bytes()))
    special_path = tmp_path / p.HYAKUNEN_PATH
    special_path.parent.mkdir(parents=True)
    special_path.write_bytes(b"synthetic special source")
    monkeypatch.setattr(p, "HYAKUNEN_SHA", p.sha(special_path.read_bytes()))
    special = pd.DataFrame([{"match_id": "special", "season": 2026, "match_date": pd.Timestamp("2026-05-01"),
                             "home_team": "A", "away_team": "B", "result": 1, "home_score": 0, "away_score": 0,
                             "pk_played": True, "pk_winner": "A"}])
    from src.features import elo_history
    from src.collect import jleague_hyakunen
    monkeypatch.setattr(elo_history, "_read_hyakunen_matches", lambda path: special.copy())
    monkeypatch.setattr(jleague_hyakunen, "validate_competition", lambda frame: None)
    directory, _ = write_revision(tmp_path, schedules())
    rev = p.read_revision(directory)
    _, completed = p.validate_revision_schedule(rev)
    return tmp_path, rev, completed, authority.parse_master(master_path.read_bytes())


def test_history_loader_exact_sources_strict_prior_and_regulation_semantics(history_sources):
    root, rev, completed, roster = history_sources
    frames = p.load_live_history(root, rev, completed, roster, target_date="2026-10-09")
    assert len(frames[0]) == 11 and len(frames[1]) == 1 and len(frames[2]) == 2
    assert frames[1].result.tolist() == [1]  # PK winner is NOT regulation winner.
    assert frames[2].match_date.lt(pd.Timestamp("2026-10-09")).all()
    before_same_date = p.load_live_history(root, rev, completed, roster, target_date="2026-09-20")
    assert before_same_date[2].empty
    states = p.replay_live_states(*frames, [a.team_id for a in roster.aliases], target_date="2026-10-09")
    special = next(c for c in states.captures if c["segment"] == "hyakunen")
    assert special["st2_k"] == 30
    assert all(c["home_ordinal"] == 1 for c in states.captures if c["segment"] == "ongoing")


@pytest.mark.parametrize("source", ["ordinary", "master", "hyakunen"])
def test_historical_hash_gate_before_any_source_parse(history_sources, monkeypatch, source):
    root, rev, completed, roster = history_sources
    relative = next(iter(authority.SOURCE_HASHES)) if source == "ordinary" else authority.TEAM_MASTER_PATH if source == "master" else p.HYAKUNEN_PATH
    (root / relative).write_bytes(b"tampered")
    monkeypatch.setattr(authority, "load_sources", lambda snapshots: pytest.fail("source parsed before all hashes"))
    with pytest.raises(p.ST2PredictionError, match="source hash"):
        p.load_live_history(root, rev, completed, roster, target_date="2026-10-09")


def test_ongoing_completed_official_provenance_required(history_sources):
    root, rev, completed, roster = history_sources
    with pytest.raises(ValueError, match="confirmed ordinary"):
        p.load_live_history(root, rev, completed.assign(evidence_type="unconfirmed"), roster, target_date="2026-10-09")
    with pytest.raises(p.ST2PredictionError, match="after publication"):
        p.load_live_history(root, rev, completed.assign(evidence_fetched_at_utc="2026-10-10T00:00:00+00:00"), roster, target_date="2026-10-09")


def make_a_bundle(tmp_path, monkeypatch):
    directory = tmp_path / "a-bundle"
    directory.mkdir()
    scaler, model = synthetic_model()
    joblib.dump(scaler, directory / "scaler.joblib")
    joblib.dump(model, directory / "model.joblib")
    (directory / "training_manifest.csv").write_bytes(b"synthetic training manifest\n")
    metadata = {"model_version": p.CHAMPION_A_MODEL_VERSION, "role": "operational_champion", "training_row_count": 3588,
                "feature_list": ["elo_diff"], "target_mapping": {"0": "Away", "1": "Draw", "2": "Home"},
                "future_rows_used": 0, "metrics_calculated": False, "predictions_generated": False,
                **{key: p.sha((directory / name).read_bytes()) for key, name in (("training_manifest_hash", "training_manifest.csv"), ("model_hash", "model.joblib"), ("scaler_hash", "scaler.joblib"))}}
    (directory / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
    checksum = "".join(f"{p.sha((directory / n).read_bytes())}  {n}\n" for n in sorted(set(p.A_FILE_PINS) - {"checksums.sha256"}))
    (directory / "checksums.sha256").write_bytes(checksum.encode())
    pins = {name: p.sha((directory / name).read_bytes()) for name in p.A_FILE_PINS}
    monkeypatch.setattr(p, "A_FILE_PINS", pins)
    monkeypatch.setattr(p, "CHAMPION_A_ARTIFACT_HASH", pins["checksums.sha256"])
    return directory


def test_persisted_a_bundle_validates_without_fit(tmp_path, monkeypatch):
    directory = make_a_bundle(tmp_path, monkeypatch)
    bundle = p.validate_model_a_artifact(directory)
    assert bundle.model.classes_.tolist() == [0, 1, 2]
    assert bundle.artifact_hash == p.CHAMPION_A_ARTIFACT_HASH
    (directory / "model.joblib").write_bytes(b"tampered")
    with pytest.raises(p.ST2PredictionError, match="hash/pin"):
        p.validate_model_a_artifact(directory)


def test_a_expected_hash_required(tmp_path, monkeypatch):
    directory = make_a_bundle(tmp_path, monkeypatch)
    monkeypatch.setattr(p, "CHAMPION_A_ARTIFACT_HASH", "0" * 64)
    with pytest.raises(p.ST2PredictionError, match="expected artifact hash"):
        p.validate_model_a_artifact(directory)


def test_a_original_platform_checksum_newlines_preserved(tmp_path, monkeypatch):
    directory = make_a_bundle(tmp_path, monkeypatch)
    path = directory / "checksums.sha256"
    original = path.read_bytes().replace(b"\n", b"\r\n")
    path.write_bytes(original)
    monkeypatch.setattr(p, "A_FILE_PINS", {**p.A_FILE_PINS, "checksums.sha256": p.sha(original)})
    monkeypatch.setattr(p, "CHAMPION_A_ARTIFACT_HASH", p.sha(original))
    p.validate_model_a_artifact(directory)
    assert path.read_bytes() == original


def test_st2_reviewed_loader_expected_hash_required(tmp_path, monkeypatch):
    calls = []
    a, st2 = branches()
    def loader(path, *, expected_artifact_hash):
        assert path == tmp_path / p.ST2_ARTIFACT_PATH
        calls.append(expected_artifact_hash)
        return SimpleNamespace(fitted=SimpleNamespace(scaler=st2.scaler, model=st2.model),
                               metadata={"model_version": p.ST2_MODEL_VERSION}, artifact_hash=expected_artifact_hash)
    monkeypatch.setattr(authority, "load_artifact", loader)
    monkeypatch.setattr(p, "validate_model_a_artifact", lambda path: a)
    p.load_model_pair(tmp_path)
    assert calls == [p.ST2_ARTIFACT_HASH]
    monkeypatch.setattr(authority, "load_artifact", lambda *args, **kwargs: SimpleNamespace(artifact_hash="wrong", metadata={"model_version": p.ST2_MODEL_VERSION}))
    with pytest.raises(p.ST2PredictionError, match="identity/hash"):
        p.load_model_pair(tmp_path)


@pytest.fixture
def operational(tmp_path, monkeypatch, small_scope):
    directory, digest = write_revision(tmp_path, schedules())
    revision = p.read_revision(directory)
    schedule, completed = p.validate_revision_schedule(revision)
    batch = p.resolve_team_ids(schedule.iloc[2:], master())
    bindings = pd.concat([source_binding(row, witness_sha=digest) for _, row in batch.iterrows()], ignore_index=True)
    baseline = pd.DataFrame([{"match_id": r.match_id, "model_version": "baseline-v1", "match_date": r.match_date,
                             "home_team_id": r.home_team_id, "away_team_id": r.away_team_id, "prediction_generated_at": NOW.isoformat()} for r in batch.itertuples()])
    baseline.to_csv(tmp_path / "baseline.csv", index=False)
    sidecar = tmp_path / identity.DEFAULT_BINDING_PATH
    sidecar.parent.mkdir(parents=True)
    bindings.to_csv(sidecar, index=False, lineterminator="\n")
    original_validation = identity.validate_complete_sidecar
    monkeypatch.setattr(identity, "validate_complete_sidecar", lambda **kw: original_validation(**{**kw, "prediction_artifacts": kw.get("prediction_artifacts", ("baseline.csv",))}))
    master_path = tmp_path / authority.TEAM_MASTER_PATH
    master_path.parent.mkdir(parents=True)
    master_path.write_bytes(b"synthetic master")
    monkeypatch.setattr(authority, "TEAM_MASTER_SHA", p.sha(master_path.read_bytes()))
    monkeypatch.setattr(authority, "parse_master", lambda body: master())
    monkeypatch.setattr(p, "frozen_cohort", lambda root: (schedule, schedule.iloc[2:]))
    monkeypatch.setattr(p, "read_current_revision", lambda root: revision)
    ordinary = history([("hist", 2025, "2025-01-01", "team_0001", "team_0002", 2)])
    monkeypatch.setattr(p, "load_live_history", lambda *args, **kw: (ordinary, empty_history(), empty_history()))
    monkeypatch.setattr(p, "load_model_pair", lambda root: branches())
    monkeypatch.setattr(p, "repository_state", lambda root: "a" * 40)
    return tmp_path, sidecar


def auth():
    return {"approved_execution_head": "a" * 40, "target_date": "2026-10-09", "task_reference": "synthetic authorization"}


def test_dry_run_generates_probabilities_writes_zero_bytes(operational, monkeypatch):
    root, _ = operational
    before = {f: f.read_bytes() for f in root.rglob("*") if f.is_file()}
    calls = []
    original = p.predict_branch
    monkeypatch.setattr(p, "predict_branch", lambda *args: (calls.append(1), original(*args))[1])
    result = p.run_prediction(root=root, dry_run=True, clock=lambda: NOW)
    assert result == {"status": "DRY_RUN", "target_date": "2026-10-09", "target_count": 2,
                      "already_predicted_count": 0, "would_append_count": 2, "source_revision": "1" * 64}
    assert calls == [1, 1]
    assert before == {f: f.read_bytes() for f in root.rglob("*") if f.is_file()}


def test_production_append_duplicate_skip_no_regeneration(operational, monkeypatch):
    root, sidecar = operational
    original_sidecar = sidecar.read_bytes()
    result = p.run_prediction(root=root, authorization=auth(), clock=lambda: NOW)
    assert result["would_append_count"] == 2
    assert sidecar.read_bytes().startswith(original_sidecar)
    output = root / p.PREDICTION_ARTIFACT
    before = output.read_bytes(), sidecar.read_bytes()
    monkeypatch.setattr(p, "load_live_history", lambda *args, **kwargs: pytest.fail("duplicate replay"))
    monkeypatch.setattr(p, "load_model_pair", lambda *args: pytest.fail("duplicate model load"))
    result = p.run_prediction(root=root, authorization=auth(), clock=lambda: NOW)
    assert result["already_predicted_count"] == 2 and result["would_append_count"] == 0
    assert before == (output.read_bytes(), sidecar.read_bytes())


@pytest.mark.parametrize("change", ["missing", "head", "date", "extra"])
def test_production_authorization_rejects(operational, change):
    root, _ = operational
    obj = auth()
    if change == "missing":
        obj = None
    elif change == "head":
        obj["approved_execution_head"] = "b" * 40
    elif change == "date":
        obj["target_date"] = "2026-10-10"
    else:
        obj["extra"] = True
    with pytest.raises(p.ST2PredictionError, match="authorization|Authorization"):
        p.run_prediction(root=root, authorization=obj, clock=lambda: NOW)


def test_conflicting_partial_append_stops_before_probability(operational, monkeypatch):
    root, sidecar = operational
    comparison = records()
    bindings = p.make_comparison_bindings(comparison, targets(), [("1" * 64, "2" * 64)] * 2)
    bindings.to_csv(sidecar, mode="a", header=False, index=False)
    monkeypatch.setattr(p, "predict_branch", lambda *args: pytest.fail("partial probability regeneration"))
    with pytest.raises(p.ST2PredictionError, match="Orphan"):
        p.run_prediction(root=root, authorization=auth(), clock=lambda: NOW)


@pytest.mark.parametrize("dry_run", [True, False], ids=["dry-run", "authorized-production"])
def test_consistent_partial_date_batch_requires_journal_before_any_work(operational, monkeypatch, dry_run):
    root, sidecar = operational
    current = p.read_current_revision(root)
    current_targets = targets()
    assert len(current_targets) == 2
    comparison = records().iloc[[0]].reset_index(drop=True)
    binding_rows = p.make_comparison_bindings(
        comparison, current_targets.iloc[[0]], [(current.revision_id, current.manifest_sha)])
    output = root / p.PREDICTION_ARTIFACT
    p.append_records(comparison).to_csv(output, index=False, lineterminator="\n")
    binding_rows.to_csv(sidecar, mode="a", header=False, index=False, lineterminator="\n")
    assert not sidecar.with_name(f".{sidecar.name}.journal.json").exists()
    assert not sidecar.with_name(f".{sidecar.name}.lock").exists()
    # Prove this is a valid matched row, not the orphan/conflict failure case.
    existing = p.existing_comparisons(root, identity.read_prediction_bindings(sidecar))
    assert len(existing) == 1 and existing.fixture_key.tolist() == [current_targets.fixture_key.iloc[0]]
    before = {path: path.read_bytes() for path in root.rglob("*") if path.is_file()}

    def forbidden(*args, **kwargs):
        pytest.fail("Partial non-journal date batch reached replay/model/prediction/append")

    for name in ("load_live_history", "replay_live_states", "load_model_pair",
                 "generate_prediction_records", "predict_branch", "append_records"):
        monkeypatch.setattr(p, name, forbidden)
    monkeypatch.setattr(identity, "append_prediction_and_bindings", forbidden)
    monkeypatch.setattr(identity, "recover_prediction_append", forbidden)
    with pytest.raises(p.ST2PredictionError, match="Partial existing comparison date batch; journal recovery required"):
        p.run_prediction(root=root, dry_run=dry_run,
                         authorization=None if dry_run else auth(), clock=lambda: NOW)
    assert before == {path: path.read_bytes() for path in root.rglob("*") if path.is_file()}


def test_writer_lock_blocks_even_recovery(operational):
    root, sidecar = operational
    lock = sidecar.with_name(f".{sidecar.name}.lock")
    lock.write_text("synthetic active writer")
    with pytest.raises(p.ST2PredictionError, match="writer lock"):
        p.run_prediction(root=root, authorization=auth(), clock=lambda: NOW)
    assert lock.read_text() == "synthetic active writer"


def test_missing_id_full_date_rejected_before_prediction(operational, monkeypatch):
    root, _ = operational
    current = p.read_current_revision(root)
    schedule, completed = p.validate_revision_schedule(current)
    schedule.loc[3, "match_id"] = ""
    monkeypatch.setattr(p, "validate_revision_schedule", lambda rev: (schedule, completed))
    monkeypatch.setattr(p, "generate_prediction_records", lambda *args, **kwargs: pytest.fail("ID subset prediction"))
    with pytest.raises(p.ST2PredictionError, match="nonblank"):
        p.run_prediction(root=root, dry_run=True, clock=lambda: NOW)


def test_backward_clock_or_elapsed_during_run_stops(operational):
    root, _ = operational
    ticks = iter([NOW, datetime(2026, 10, 7, tzinfo=timezone.utc)])
    with pytest.raises(p.ST2PredictionError, match="backwards"):
        p.run_prediction(root=root, dry_run=True, clock=lambda: next(ticks))
    ticks = iter([NOW, datetime(2026, 10, 9, 10, tzinfo=timezone.utc)])
    with pytest.raises(p.ST2PredictionError, match="elapsed"):
        p.run_prediction(root=root, dry_run=True, clock=lambda: next(ticks))


def test_source_observed_after_clock_rejected(operational):
    root, _ = operational
    with pytest.raises(p.ST2PredictionError, match="Future published"):
        p.run_prediction(root=root, dry_run=True, clock=lambda: datetime(2026, 10, 2, tzinfo=timezone.utc))


def test_firewall_blocks_real_sources_and_network():
    for relative in ("data/processed/jleague/2015_matches_probe.csv", "data/master/teams.csv", "models/example.joblib", "data/processed/predictions/example.csv"):
        with pytest.raises(AssertionError, match="Production IO"):
            (p.ROOT / relative).read_bytes()
    with pytest.raises(AssertionError, match="Network"):
        socket.create_connection(("example.invalid", 443))


def test_fixture_duplicate_skip_across_namespace_change(operational, monkeypatch):
    root, _ = operational
    p.run_prediction(root=root, authorization=auth(), clock=lambda: NOW)
    schedule = schedules()
    schedule.loc[2:, "match_id_namespace"] = identity.DATA_SITE_NAMESPACE
    schedule.loc[2:, "match_id"] = ["42", "43"]
    schedule.loc[2:, "data_site_match_id"] = ["42", "43"]
    directory, _ = write_revision(root, schedule, version="ongoing-v2", name="3" * 64)
    rev = p.read_revision(directory)
    monkeypatch.setattr(p, "read_current_revision", lambda root: rev)
    monkeypatch.setattr(p, "load_model_pair", lambda *args: pytest.fail("duplicate predictions"))
    result = p.run_prediction(root=root, authorization=auth(), clock=lambda: NOW)
    assert result["already_predicted_count"] == 2 and result["would_append_count"] == 0


def test_recovery_uses_exact_journal_no_probability(operational, monkeypatch):
    root, sidecar = operational
    comparison = records()
    output = root / p.PREDICTION_ARTIFACT
    current_revision = p.read_current_revision(root)
    binding_rows = p.make_comparison_bindings(comparison, targets(), [(current_revision.revision_id, current_revision.manifest_sha)] * 2)
    desired_predictions = identity._suffix_bytes(comparison, header=True)
    desired_sidecar = sidecar.read_bytes() + identity._suffix_bytes(binding_rows, header=False)
    output.write_bytes(desired_predictions)
    journal = sidecar.with_name(f".{sidecar.name}.journal.json")
    journal.write_text(json.dumps({"prediction_sha256": p.sha(desired_predictions), "binding_sha256": p.sha(desired_sidecar),
                                  "prediction_rows": comparison.to_dict("records"), "binding_rows": binding_rows.to_dict("records")}), encoding="utf-8")
    monkeypatch.setattr(p, "generate_prediction_records", lambda *args, **kwargs: pytest.fail("recovery prediction forbidden"))
    before = journal.read_bytes()
    with pytest.raises(p.ST2PredictionError, match="dry-run"):
        p.run_prediction(root=root, dry_run=True, clock=lambda: NOW)
    assert journal.read_bytes() == before
    result = p.run_prediction(root=root, authorization=auth(), clock=lambda: NOW)
    assert result["status"] == "RECOVERED" and result["bindings_recovered"] == 2
    assert output.read_bytes() == desired_predictions and sidecar.read_bytes() == desired_sidecar


def test_common_writer_journal_preserves_exact_probability_suffix(operational, monkeypatch):
    root, sidecar = operational
    original_append = identity._append_suffix
    journal_captures = []
    def inspect_append(path, frame):
        journal = sidecar.with_name(f".{sidecar.name}.journal.json")
        journal_captures.append(json.loads(journal.read_bytes()))
        original_append(path, frame)
    monkeypatch.setattr(identity, "_append_suffix", inspect_append)
    p.run_prediction(root=root, authorization=auth(), clock=lambda: NOW)
    output = root / p.PREDICTION_ARTIFACT
    for frozen in journal_captures:
        rows = pd.DataFrame(frozen["prediction_rows"], columns=p.PREDICTION_COLUMNS)
        assert all(isinstance(value, str) for value in rows.a_p_draw)
        assert identity._suffix_bytes(rows, header=True) == output.read_bytes()
        assert p.sha(output.read_bytes()) == frozen["prediction_sha256"]
    # Pure conversion preserves every float64 bit, not a probability adjustment.
    original = records()
    serialized = p.append_records(original)
    np.testing.assert_array_equal(serialized[list(p.PREDICTION_COLUMNS[18:26])].to_numpy(dtype=float),
                                  original[list(p.PREDICTION_COLUMNS[18:26])].to_numpy(dtype=float))


def test_import_help_no_io_and_cli_no_probabilities(monkeypatch, capsys):
    def denied(*args, **kwargs):
        raise AssertionError("evidence read on import/help")
    monkeypatch.setattr(Path, "read_bytes", denied)
    with pytest.raises(SystemExit) as exc:
        p.main(["--help"])
    assert exc.value.code == 0
    assert "--dry-run" in capsys.readouterr().out
    monkeypatch.setattr(p, "run_prediction", lambda **kw: {"status": "DRY_RUN", "target_count": 2})
    assert p.main(["--dry-run"]) == 0
    assert json.loads(capsys.readouterr().out) == {"status": "DRY_RUN", "target_count": 2}
    # Re-executing module source proves module-level declarations perform no IO.
    import importlib
    importlib.reload(p)


def test_static_no_fit_metrics_network_xg_dependency():
    tree = ast.parse(Path(p.__file__).read_text(encoding="utf-8"))
    forbidden_calls = {"fit", "fit_transform", "partial_fit", "score", "calibrate", "minimize", "GridSearchCV"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            assert node.func.attr not in forbidden_calls
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            modules = [node.module or ""] if isinstance(node, ast.ImportFrom) else [a.name for a in node.names]
            assert all(not any(bad in module for bad in ("metrics", "xg", "requests", "urllib", "optimizer", "calibration")) for module in modules)
