"""Synthetic-only safety/chronology tests; no production model fits."""
import json
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from src.modeling import nn_research_v1 as n


def matches():
    # Four independent clubs per day; shuffled IDs exercise deterministic order.
    rows = []
    for day in range(1, 19):
        for index, (home, away) in enumerate((("A", "B"), ("C", "D"))):
            home, away = (home, away) if day % 2 else (away, home)
            result = (day + index) % 3
            hg, ag = {0: (0, 2), 1: (1, 1), 2: (2, 0)}[result]
            rows.append(dict(match_id=f"{day:03}{index}", match_date=pd.Timestamp(2015, 3, day),
                             home_team_id=home, away_team_id=away, home_score=hg,
                             away_score=ag, result=result, season=2015))
    return pd.DataFrame(rows)


def test_fixed_spec_and_runtime_contract():
    n.verify_spec(n.ROOT / "research/nn_v1/frozen-spec.json")
    model = n.estimator("mlp")
    params = model.named_steps["classifier"].get_params()
    assert all(params[k] == v for k, v in n.MLP_PARAMS.items())
    assert params["hidden_layer_sizes"] == (32, 16)
    assert params["random_state"] == 42 and params["max_iter"] == 500
    assert params["early_stopping"] is False
    assert n.YEARS == (2020, 2021, 2022, 2023, 2024)
    assert sum(n.COUNTS.values()) == 3588
    assert sum(n.COUNTS[y] for y in n.YEARS) == 1678


def test_future_and_current_results_cannot_change_earlier_features():
    source = matches()
    before = source.copy(deep=True)
    original = n.build_features(source)
    source.loc[source.match_date.ge("2015-03-10"), ["result", "home_score", "away_score"]] = [2, 8, 0]
    changed = n.build_features(source)
    pd.testing.assert_frame_equal(original.loc[original.match_date.le("2015-03-10"), list(n.FEATURES)],
                                  changed.loc[changed.match_date.le("2015-03-10"), list(n.FEATURES)])
    assert (original.loc[original.match_date.gt("2015-03-10"), "elo_diff"] !=
            changed.loc[changed.match_date.gt("2015-03-10"), "elo_diff"]).any()
    pd.testing.assert_frame_equal(n.build_features(before), original)


def test_same_day_permutation_has_no_effect_and_duplicate_club_rejected():
    source = matches()
    pd.testing.assert_frame_equal(n.build_features(source), n.build_features(source.iloc[::-1]))
    source.loc[1, "home_team_id"] = "A"
    with pytest.raises(ValueError, match="more than once"):
        n.build_features(source)


def test_form_totals_counts_and_cross_season_state():
    source = matches()
    source.loc[source.match_date.ge("2015-03-10"), "season"] = 2016
    state = n.build_features(source)
    assert state.loc[0, "home_last5_matches_available"] == 0
    assert state.loc[0, "home_last5_points"] == 0
    assert state.loc[10, "home_last5_matches_available"] == 5
    assert state.loc[18, "home_last5_matches_available"] == 5
    assert state.loc[10, "home_last5_goals_for"] == 6


@pytest.mark.parametrize("column,value", [("elo_diff", np.nan), ("elo_diff", np.inf),
    ("home_last5_matches_available", 6), ("home_last5_matches_available", 0.5),
    ("home_last5_points", -1), ("home_last5_points", 100),
    ("home_last5_goals_for", 0.5), ("home_last5_goals_for", 1)])
def test_bad_features_rejected(column, value):
    state = n.build_features(matches()).astype({column: float})
    state.loc[0, column] = value
    with pytest.raises(ValueError):
        n.validate_features(state)


@pytest.mark.parametrize("p", [np.zeros((2, 3)), np.ones((2, 2)),
    [[np.nan, 0.5, 0.5]] * 2, [[-0.1, 0.6, 0.5]] * 2])
def test_invalid_probabilities(p):
    with pytest.raises(ValueError):
        n.probabilities(p, 2)


def test_metric_class_order_and_brier_convention():
    assert n.metrics([0, 1, 2], np.eye(3))["accuracy"] == 1
    assert n.metrics([0, 1, 2], np.eye(3))["brier"] == 0
    m = n.metrics([0, 1, 2], np.full((3, 3), 1 / 3))
    assert m["brier"] == pytest.approx(2 / 3)
    assert m["log_loss"] == pytest.approx(np.log(3))


def test_fit_scaler_training_only_and_class_mapping():
    frame = n.build_features(matches())
    training, validation = frame.iloc[:24], frame.iloc[24:]
    for name in n.NAMES:
        model, report = n.fit(name, training)
        columns = ["elo_diff"] if name == "elo_logistic" else list(n.FEATURES)
        np.testing.assert_allclose(model.named_steps["scaler"].mean_, training[columns].mean())
        assert report["scaler_training_rows"] == len(training)
        assert tuple(model.classes_) == (0, 1, 2)
        p = n.score_model(name, model, validation)
        assert p.shape == (12, 3)
        assert report["iterations"] <= (500 if name == "mlp" else 1000)


def test_original_kickoff_guard_precedes_fits_and_output_creation(tmp_path, monkeypatch):
    source = matches()
    source.loc[0, "match_id"] = "30700"
    monkeypatch.setattr(n, "load_source", lambda *args: (source, {}))
    monkeypatch.setattr(n, "fit", lambda *args: pytest.fail("Must not fit"))
    output = tmp_path / "output"
    with pytest.raises(ValueError, match="original-kickoff"):
        n.run(tmp_path / "source", output)
    assert not output.exists()


def test_audit_only_never_fits(tmp_path, monkeypatch):
    source = matches()
    monkeypatch.setattr(n, "load_source", lambda *args: (source, {}))
    monkeypatch.setattr(n, "fit", lambda *args: pytest.fail("Audit must not fit"))
    result = n.run(tmp_path / "source", tmp_path / "audit", audit_only=True)
    assert result["status"] == "AUDIT_COMPLETE_NO_FIT"
    assert not (tmp_path / "audit/artifact").exists()
    with pytest.raises(FileExistsError):
        n.run(tmp_path / "source", tmp_path / "audit", audit_only=True)


def test_pin_scope_rejects_nonordinary_inputs(tmp_path):
    pins = tmp_path / "pins.json"
    pins.write_text(json.dumps({"data/processed/jleague/2026_hyakunen/matches.csv": "0" * 64}))
    with pytest.raises(ValueError, match="Only the 11"):
        n.load_source(tmp_path, pins)


def test_frozen_spec_rejects_parameter_changes(tmp_path):
    spec = n.specification()
    spec["mlp"]["max_iter"] += 1
    p = tmp_path / "spec.json"
    p.write_text(json.dumps(spec))
    with pytest.raises(ValueError, match="specification mismatch"):
        n.verify_spec(p)


def test_reference_gate_detects_drift():
    n.reference_gate(dict(zip(("log_loss", "brier", "accuracy"), n.REFERENCE[2020])), 2020)
    with pytest.raises(ValueError, match="reference mismatch"):
        n.reference_gate({"log_loss": 1, "brier": 0.5, "accuracy": 0.5}, 2020)


def test_model_error_stops_without_retry_or_final_fit(tmp_path, monkeypatch):
    source = matches()
    calls = []
    monkeypatch.setattr(n, "load_source", lambda *a: (source, {}))
    def fail(*a):
        calls.append(1)
        raise RuntimeError("synthetic fit failure")
    monkeypatch.setattr(n, "evaluate", fail)
    monkeypatch.setattr(n, "fit", lambda *a: pytest.fail("No final fit after failure"))
    output = tmp_path / "failed"
    with pytest.raises(RuntimeError, match="synthetic fit failure"):
        n.run(tmp_path / "source", output)
    assert calls == [1]
    assert json.loads((output / "failure.json").read_bytes())["automatic_retry"] is False


@pytest.mark.parametrize("name", n.NAMES)
def test_fit_cannot_bypass_original_kickoff_guard(name, monkeypatch):
    source = n.build_features(matches())
    source.loc[0, "match_id"] = "30700"
    monkeypatch.setattr(n, "estimator", lambda *args: pytest.fail("Must stop before constructing a model"))
    with pytest.raises(ValueError, match="original-kickoff"):
        n.fit(name, source)


def test_evaluator_stops_before_earliest_fold_if_unresolved_match_is_later(tmp_path, monkeypatch):
    source = n.build_features(matches())
    source.loc[0, ["match_id", "season"]] = ["30700", 2024]
    monkeypatch.setattr(n, "fit", lambda *a: pytest.fail("Not even an earlier fold may fit"))
    with pytest.raises(ValueError, match="original-kickoff"):
        n.evaluate(source, tmp_path)


def test_expanding_windows_are_train_only_and_never_score_2025(tmp_path, monkeypatch):
    rows = []
    for year, count in n.COUNTS.items():
        for index in range(count):
            rows.append(dict(season=year, match_id=f"synthetic_{year}_{index}",
                match_date=pd.Timestamp(year, 1, 1) + pd.Timedelta(days=index // 10),
                home_team_id="A", away_team_id="B", result=index % 3))
    source = pd.DataFrame(rows)
    calls = []
    def fake_fit(name, train):
        assert train.season.max() < 2024
        assert train.season.min() == 2015
        calls.append((name, int(train.season.max()), len(train)))
        return SimpleNamespace(train_end=int(train.season.max())), dict(seconds=0, iterations=1,
            converged=True, warnings=[], loss_curve=[1.0], scaler_training_rows=len(train))
    def fake_score(name, model, validation):
        assert validation.season.nunique() == 1
        assert validation.season.iloc[0] == model.train_end + 1
        assert not validation.season.eq(2025).any()
        return np.full((len(validation), 3), 1 / 3)
    monkeypatch.setattr(n, "fit", fake_fit)
    monkeypatch.setattr(n, "score_model", fake_score)
    monkeypatch.setattr(n, "reference_gate", lambda *args: None)
    folds, pooled, curves = n.evaluate(source, tmp_path)
    assert len(calls) == len(folds) == 15
    assert [p["n"] for p in pooled] == [1678] * 3
    assert set(curves) == {str(y) for y in n.YEARS}
    assert [c[2] for c in calls[::3]] == [1530, 1836, 2216, 2522, 2828]


def test_source_hash_mismatch_is_rejected_before_parsing(tmp_path):
    pins = {f"data/processed/jleague/{y}_matches_probe.csv": "0" * 64 for y in n.COUNTS}
    pins["data/master/teams.csv"] = "0" * 64
    for name in pins:
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"tampered")
    path = tmp_path / "pins.json"
    path.write_text(json.dumps(pins))
    with pytest.raises(ValueError, match="SHA mismatch"):
        n.load_source(tmp_path, path)


def test_fit_rejects_2026_before_estimator_construction(monkeypatch):
    frame = n.build_features(matches()).assign(season=2026)
    monkeypatch.setattr(n, "estimator", lambda *a: pytest.fail("Must not construct a 2026 model"))
    with pytest.raises(ValueError, match="2015--2025"):
        n.fit("mlp", frame)


@pytest.mark.parametrize("year", [2025, 2026])
def test_score_rejects_spent_2025_and_2026(year):
    frame = n.build_features(matches()).assign(season=year)
    with pytest.raises(ValueError, match="spent-test or 2026"):
        n.score_model("mlp", None, frame)
