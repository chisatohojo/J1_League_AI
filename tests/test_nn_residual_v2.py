"""Entirely synthetic numeric checks; no real CSVs, network or worker process."""
import hashlib
import json
import socket
import subprocess

import numpy as np
import pandas as pd
import pytest

from src.modeling import nn_residual_v2 as r


@pytest.fixture(autouse=True)
def forbid_external_data(monkeypatch):
    def denied(*a, **k):
        raise AssertionError("Real data/network/process access forbidden in synthetic tests")
    monkeypatch.setattr(pd, "read_csv", denied)
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(subprocess, "Popen", denied)


def synthetic(n=18):
    rng = np.random.default_rng(101)
    x = np.zeros((n, 8))
    for side in (0, 1):
        count = rng.integers(0, 6, n)
        x[:, side] = count
        x[:, 2+side] = [rng.integers(0, int(3*c)+1) for c in count]
        for column in (4+side, 6+side):
            x[:, column] = np.where(count > 0, rng.integers(0, 16, n), 0)
    return pd.DataFrame(x, columns=r.FORM_FEATURES), rng.normal(size=(n, 3)), np.arange(n) % 3


@pytest.fixture(scope="module")
def fitted():
    x, base, y = synthetic()
    return r.ResidualNN().fit(x, base, y)


def test_initialization_and_exact_parameter_count(record_property):
    theta = r.initial_parameters()
    assert theta.shape == (90,) and theta.dtype == np.float64
    assert [p.shape for p in r.unpack(theta)] == [(8, 8), (8,), (8, 2), (2,)]
    limit = np.sqrt(6/16)
    expected = np.random.Generator(np.random.PCG64(42)).uniform(-limit, limit, 64)
    np.testing.assert_array_equal(theta[:64], expected)
    assert np.count_nonzero(theta[64:]) == 0
    record_property("parameter_count", 90)


def test_zero_residual_equals_base_even_with_common_logit_shift():
    rng = np.random.default_rng(55)
    u, base = rng.normal(size=(11, 8)), rng.normal(size=(11, 3))
    p, _, delta, _, _ = r.forward(r.initial_parameters(), u, base)
    np.testing.assert_array_equal(delta, np.zeros((11, 2)))
    np.testing.assert_allclose(p, np.exp(r.log_softmax(base)), atol=1e-14, rtol=0)
    shifted = r.forward(r.initial_parameters(), u, base + 1000)[0]
    np.testing.assert_allclose(p, shifted, atol=1e-13, rtol=0)


def test_residual_bound_and_away_home_difference():
    p = r.initial_parameters(); p[88:] = [1e9, -1e9]
    _, _, delta, _, _ = r.forward(p, np.zeros((2, 8)), np.zeros((2, 3)))
    np.testing.assert_array_equal(delta, [[0.25, -0.25], [0.25, -0.25]])
    assert np.max(delta[:, 0]-delta[:, 1]) == 0.5


def test_extreme_finite_logits_use_unclipped_stable_cross_entropy():
    u, base = np.zeros((3, 8)), np.array([[1000., 0., -1000.]]*3)
    p, lp, *_ = r.forward(np.zeros(90), u, base)
    assert np.isfinite(lp).all() and np.isfinite(p).all()
    loss, grad = r.loss_gradient(np.zeros(90), u, base, np.array([0, 1, 2]))
    assert loss == pytest.approx(1000.)
    assert np.isfinite(grad).all()
    np.testing.assert_allclose(p.sum(axis=1), 1, atol=1e-15, rtol=0)


def test_l2_applies_to_weights_only_and_is_not_divided_by_population():
    p = r.initial_parameters(); p[64:72] = 2; p[88:] = [1, -1]
    u, base, y = np.zeros((3, 8)), np.zeros((3, 3)), np.arange(3)
    loss, _ = r.loss_gradient(p, u, base, y)
    _, lp, *_ = r.forward(p, u, base)
    w1, _, w2, _ = r.unpack(p)
    expected = -lp[np.arange(3), y].mean() + 0.005*(np.square(w1).sum()+np.square(w2).sum())
    assert loss == pytest.approx(expected, abs=1e-14)
    repeated, _ = r.loss_gradient(p, np.tile(u, (2, 1)), np.tile(base, (2, 1)), np.tile(y, 2))
    assert repeated == pytest.approx(loss, abs=1e-14)


@pytest.mark.parametrize("seed", [7, 43])
def test_all_90_gradients_by_central_difference(seed, record_property):
    rng = np.random.default_rng(seed)
    theta = rng.normal(0, 0.3, 90)  # nonzero output weights exercise hidden gradients
    u, base, y = rng.normal(size=(7, 8)), rng.normal(size=(7, 3)), np.arange(7) % 3
    _, analytic = r.loss_gradient(theta, u, base, y)
    numeric = np.zeros(90)
    for j in range(90):
        upper, lower = theta.copy(), theta.copy()
        upper[j] += 1e-6; lower[j] -= 1e-6
        numeric[j] = (r.loss_gradient(upper, u, base, y)[0]-r.loss_gradient(lower, u, base, y)[0])/2e-6
    absolute = float(np.max(np.abs(analytic-numeric)))
    relative = float(np.linalg.norm(analytic-numeric)/(np.linalg.norm(analytic)+np.linalg.norm(numeric)))
    assert absolute < 5e-8 and relative < 1e-7
    record_property("gradient_max_absolute_error", absolute)
    record_property("gradient_relative_l2_error", relative)


def test_adam_two_steps_against_scalar_hand_calculation():
    p = np.ones(90); m, v = np.zeros(90), np.zeros(90)
    p1, m1, v1 = r.adam_step(p, np.full(90, 2.), m, v, 1)
    e1 = 1-0.001*2/(2+1e-8)
    np.testing.assert_allclose(p1, e1, atol=1e-15, rtol=0)
    p2, m2, v2 = r.adam_step(p1, np.full(90, -1.), m1, v1, 2)
    e2 = e1-0.001*(0.08/(1-0.9**2))/(np.sqrt(0.004996/(1-0.999**2))+1e-8)
    np.testing.assert_allclose(p2, e2, atol=1e-15, rtol=0)
    np.testing.assert_allclose(m2, 0.08, atol=1e-15, rtol=0)
    np.testing.assert_allclose(v2, 0.004996, atol=1e-15, rtol=0)
    np.testing.assert_array_equal(p, np.ones(90))


def test_adam_epsilon_is_outside_sqrt():
    updated, *_ = r.adam_step(np.zeros(90), np.full(90, 1e-12), np.zeros(90), np.zeros(90), 1)
    np.testing.assert_allclose(updated, -0.001*1e-12/(1e-12+1e-8), rtol=1e-14, atol=0)


def test_200_updates_post_update_curve_reproducibility_and_training_scaler(fitted):
    x, base, y = synthetic()
    again = r.ResidualNN().fit(x, base, y)
    assert fitted.n_iter_ == len(fitted.loss_curve_) == 200
    np.testing.assert_array_equal(fitted.theta_, again.theta_)
    np.testing.assert_array_equal(fitted.loss_curve_, again.loss_curve_)
    np.testing.assert_allclose(fitted.scaler_.mean_, x.mean().to_numpy(), atol=1e-14)
    assert fitted.scaler_.n_samples_seen_ == len(x)
    loss, _ = r.loss_gradient(fitted.theta_, fitted.scaler_.transform(x.to_numpy()), base, y)
    assert fitted.loss_curve_[-1] == loss
    with pytest.raises(ValueError, match="Warm start"):
        again.fit(x, base, y)


@pytest.mark.parametrize("bad", [np.nan, np.inf, -np.inf])
@pytest.mark.parametrize("location", ["features", "base", "theta", "adam"])
def test_nonfinite_rejected(bad, location):
    x, base, y = synthetic()
    if location == "features":
        x.iloc[0, 0] = bad
        with pytest.raises(ValueError): r.ResidualNN().fit(x, base, y)
    elif location == "base":
        base[0, 0] = bad
        with pytest.raises(ValueError): r.ResidualNN().fit(x, base, y)
    elif location == "theta":
        p = r.initial_parameters(); p[0] = bad
        with pytest.raises(ValueError): r.forward(p, np.zeros((1, 8)), np.zeros((1, 3)))
    else:
        g = np.zeros(90); g[0] = bad
        with pytest.raises(ValueError): r.adam_step(np.zeros(90), g, np.zeros(90), np.zeros(90), 1)


@pytest.mark.parametrize("bad", [[0, 1, 3], [-1, 1, 2], [False, True, False], [True, 1, 2], [0., 1., 2.], [0, 1, np.nan]])
def test_invalid_class_rejected(bad):
    with pytest.raises(ValueError): r.loss_gradient(np.zeros(90), np.zeros((3, 8)), np.zeros((3, 3)), bad)


def test_feature_order_is_required_for_training_and_inference(fitted):
    x, base, y = synthetic()
    for bad in (x.iloc[:, ::-1], x.iloc[:, :-1], x.assign(extra=1), x.to_numpy()):
        with pytest.raises(ValueError): r.ResidualNN().fit(bad, base, y)
        with pytest.raises(ValueError): fitted.predict_proba(bad, base)


def test_constant_feature_and_empty_batch():
    x, base, y = synthetic(); x.iloc[:, 4] = 0
    model = r.ResidualNN().fit(x, base, y)
    assert model.scaler_.scale_[4] == 1
    with pytest.raises(ValueError): model.predict_proba(x.iloc[:0], base[:0])


def test_invalid_domain_shape_and_overflow_fail_closed():
    x, base, y = synthetic(); x.iloc[0, 0] = 6
    with pytest.raises(ValueError): r.ResidualNN().fit(x, base, y)
    with pytest.raises(ValueError): r.forward(np.zeros(89), np.zeros((1, 8)), np.zeros((1, 3)))
    with pytest.raises(ValueError): r.forward(np.zeros(90), np.zeros((1, 8)), [[1e308, -1e308, 0]])
    with pytest.raises(ValueError): r.adam_step(np.zeros(90), np.zeros(90), np.zeros(90), -np.ones(90), 1)
    with pytest.raises(ValueError): r.adam_step(np.zeros(90), np.zeros(90), np.zeros(90), np.zeros(90), 0)


def test_model_save_load_bit_exact_and_no_overwrite(tmp_path, fitted):
    folder = tmp_path/'synthetic-model'; digest = fitted.save(folder)
    assert digest == hashlib.sha256((folder/'artifact.json').read_bytes()).hexdigest()
    restored = r.ResidualNN.load(folder, expected_sha256=digest)
    x, base, _ = synthetic()
    np.testing.assert_array_equal(restored.predict_proba(x, base), fitted.predict_proba(x, base))
    np.testing.assert_array_equal(restored.theta_, fitted.theta_)
    np.testing.assert_array_equal(restored.loss_curve_, fitted.loss_curve_)
    original = (folder/'artifact.json').read_bytes()
    with pytest.raises(FileExistsError): fitted.save(folder)
    assert (folder/'artifact.json').read_bytes() == original


@pytest.mark.parametrize("edit", ["sha", "order", "classes", "bool_class", "theta_shape", "nan", "scale", "extra", "spec_bool", "versions", "file_set"])
def test_artifact_tampering_and_invalid_schema_rejected(tmp_path, fitted, edit):
    folder = tmp_path/'synthetic-model'; fitted.save(folder)
    file = folder/'artifact.json'; data = json.loads(file.read_bytes())
    if edit == "sha":
        file.write_bytes(file.read_bytes()+b' ')
    elif edit == "file_set":
        (folder/'unexpected').write_text('synthetic')
    else:
        if edit == "order": data['feature_order'].reverse()
        if edit == "classes": data['classes'] = [2, 1, 0]
        if edit == "bool_class": data['classes'] = [False, 1, 2]
        if edit == "theta_shape": data['theta'].pop()
        if edit == "nan": data['theta'][0] = float('nan')
        if edit == "scale": data['scaler']['scale'][0] *= 2
        if edit == "extra": data['unreviewed'] = 1
        if edit == "spec_bool": data['specification']['cpu_threads'] = True
        if edit == "versions": data['versions']['numpy'] = 'unreviewed'
        file.write_text(json.dumps(data), encoding='utf-8')
        (folder/'artifact.sha256').write_text(hashlib.sha256(file.read_bytes()).hexdigest())
    expected = hashlib.sha256(file.read_bytes()).hexdigest()
    with pytest.raises(ValueError): r.ResidualNN.load(folder, expected_sha256=expected)


def test_changed_valid_state_and_local_sidecar_cannot_override_external_pin(tmp_path, fitted):
    folder = tmp_path/'synthetic-model'; original = fitted.save(folder)
    file = folder/'artifact.json'; data = json.loads(file.read_bytes())
    data['theta'][0] += 0.1
    file.write_text(json.dumps(data), encoding='utf-8')
    (folder/'artifact.sha256').write_text(hashlib.sha256(file.read_bytes()).hexdigest())
    with pytest.raises(ValueError): r.ResidualNN.load(folder, expected_sha256=original)


def test_constant_scaler_serialization_and_missing_external_pin(tmp_path):
    x, base, y = synthetic(); x.iloc[:, 4] = 0
    model = r.ResidualNN().fit(x, base, y)
    folder = tmp_path/'synthetic-model'; digest = model.save(folder)
    loaded = r.ResidualNN.load(folder, expected_sha256=digest)
    assert loaded.scaler_.scale_[4] == 1
    with pytest.raises(ValueError): r.ResidualNN.load(folder, expected_sha256='dummy')
