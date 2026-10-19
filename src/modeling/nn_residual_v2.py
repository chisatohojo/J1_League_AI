"""Fixed 90-parameter research residual; no data loader, runner or live hooks."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import platform
import re

import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler
from sklearn import __version__ as sklearn_version
from threadpoolctl import threadpool_limits

FORM_FEATURES = (
    "home_last5_matches_available", "away_last5_matches_available",
    "home_last5_points", "away_last5_points", "home_last5_goals_for",
    "away_last5_goals_for", "home_last5_goals_against", "away_last5_goals_against",
)
CLASSES = (0, 1, 2)
PARAMETERS = 90
EPOCHS = 200


def specification():
    return {"schema": "nn_v2_residual_numeric_v1", "features": list(FORM_FEATURES),
            "classes": list(CLASSES), "parameters": 90, "hidden": 8,
            "activation": "tanh", "residual_bound": 0.25, "l2_weights": 0.01,
            "dtype": "float64", "rng": "PCG64", "seed": 42,
            "initialization": "W1 Glorot uniform; b1/W2/b2 zero",
            "optimizer": "Adam", "lr": 0.001, "beta1": 0.9, "beta2": 0.999,
            "epsilon_outside_sqrt": 1e-8, "bias_correction": True,
            "epochs": 200, "batch": "full", "loss_record": "post_update",
            "early_stopping": False, "warm_start": False, "cpu_threads": 1,
            "objective": "mean CE + 0.01/2*(sum(W1**2)+sum(W2**2)); no bias penalty",
            "parameter_order": ["W1 row-major (8,8)", "b1 (8)", "W2 row-major (8,2)", "b2 (2)"],
            "W1_uniform_bounds": [-float(np.sqrt(6/16)), float(np.sqrt(6/16))],
            "input_scaler": {"with_mean": True, "with_std": True, "variance_ddof": 0}}


def versions():
    return {"python": platform.python_version(), "numpy": np.__version__,
            "pandas": pd.__version__, "sklearn": sklearn_version}


def finite(value, shape=None):
    a = np.asarray(value)
    if a.dtype.kind not in "iuf" or (shape is not None and a.shape != shape):
        raise ValueError("Numeric shape/type mismatch")
    a = a.astype(np.float64, copy=True)
    if not np.isfinite(a).all():
        raise ValueError("Nonfinite numeric input")
    return a


def feature_array(frame):
    if not isinstance(frame, pd.DataFrame) or tuple(frame.columns) != FORM_FEATURES:
        raise ValueError("Exact ordered Form feature columns required")
    if frame.empty:
        raise ValueError("Empty feature batch")
    x = finite(frame.to_numpy(), (len(frame), 8))
    if (x < 0).any() or not np.equal(x, np.floor(x)).all() or (x[:, :2] > 5).any():
        raise ValueError("Raw Form must contain nonnegative integer counts")
    for side in (0, 1):
        if (x[:, 2+side] > 3*x[:, side]).any():
            raise ValueError("Form points exceed available matches")
        if (x[x[:, side] == 0][:, [2+side, 4+side, 6+side]] != 0).any():
            raise ValueError("Cold start must have empty totals")
    return x


def labels(y, n):
    if isinstance(y, (list, tuple)) and any(isinstance(v, (bool, np.bool_)) for v in y):
        raise ValueError("Boolean labels are not class IDs")
    y = np.asarray(y)
    if y.shape != (n,) or y.dtype.kind not in "iu" or not np.isin(y, CLASSES).all():
        raise ValueError("Integer classes 0=Away, 1=Draw, 2=Home required")
    return y.astype(np.int64, copy=True)


def initial_parameters():
    p = np.zeros(90, dtype=np.float64)
    p[:64] = np.random.default_rng(42).uniform(-np.sqrt(6 / 16), np.sqrt(6 / 16), 64)
    return p


def unpack(theta):
    p = finite(theta, (90,))
    return p[:64].reshape(8, 8), p[64:72], p[72:88].reshape(8, 2), p[88:]


def log_softmax(logits):
    z = finite(logits)
    if z.ndim != 2 or z.shape[1] != 3 or len(z) == 0:
        raise ValueError("Nonempty Nx3 class logits required")
    try:
        with np.errstate(over="raise", invalid="raise", divide="raise"):
            shifted = z - z.max(axis=1, keepdims=True)
            out = shifted - np.log(np.exp(shifted).sum(axis=1, keepdims=True))
    except FloatingPointError as exc:
        raise ValueError("Unrepresentable class logits") from exc
    return finite(out, z.shape)


def forward(theta, u, base_logits):
    u = finite(u)
    if u.ndim != 2 or u.shape[1] != 8 or len(u) == 0:
        raise ValueError("Nonempty Nx8 standardized features required")
    base = finite(base_logits, (len(u), 3))
    w1, b1, w2, b2 = unpack(theta)
    try:
        with np.errstate(over="raise", invalid="raise"):
            h = np.tanh(u @ w1 + b1)
            r = np.tanh(h @ w2 + b2)
            delta = 0.25 * r
            eta = base[:, [0, 2]] - base[:, [1]]
            z = np.column_stack((eta[:, 0] + delta[:, 0], np.zeros(len(u)),
                                 eta[:, 1] + delta[:, 1]))
    except FloatingPointError as exc:
        raise ValueError("Nonfinite residual arithmetic") from exc
    lp = log_softmax(z)
    return np.exp(lp), lp, delta, h, r


def loss_gradient(theta, u, base_logits, y):
    u = finite(u)
    probabilities, lp, _delta, h, r = forward(theta, u, base_logits)
    y = labels(y, len(u))
    w1, _b1, w2, _b2 = unpack(theta)
    try:
        with np.errstate(over="raise", invalid="raise"):
            loss = -lp[np.arange(len(y)), y].mean() + 0.005 * ((w1*w1).sum() + (w2*w2).sum())
            dz = (probabilities - np.eye(3)[y]) / len(y)
            d2 = 0.25 * dz[:, [0, 2]] * (1 - r*r)
            d1 = (d2 @ w2.T) * (1 - h*h)
            gradient = np.concatenate(((u.T @ d1 + 0.01*w1).ravel(), d1.sum(axis=0),
                                       (h.T @ d2 + 0.01*w2).ravel(), d2.sum(axis=0)))
    except FloatingPointError as exc:
        raise ValueError("Nonfinite loss/gradient arithmetic") from exc
    if not np.isfinite(loss):
        raise ValueError("Nonfinite objective")
    return float(loss), finite(gradient, (90,))


def adam_step(theta, gradient, first, second, step):
    p, g, m, v = (finite(a, (90,)) for a in (theta, gradient, first, second))
    if type(step) is not int or step < 1 or (v < 0).any():
        raise ValueError("Invalid Adam state")
    try:
        with np.errstate(over="raise", invalid="raise", divide="raise"):
            m = 0.9*m + 0.1*g
            v = 0.999*v + 0.001*g*g
            p = p - 0.001*(m/(1-0.9**step))/(np.sqrt(v/(1-0.999**step)) + 1e-8)
    except FloatingPointError as exc:
        raise ValueError("Nonfinite Adam update") from exc
    return finite(p, (90,)), finite(m, (90,)), finite(v, (90,))


class ResidualNN:
    """One fixed fit per instance; callers supply features and independent logits."""

    def __init__(self):
        self._attempted = False
        self._fitted = False

    def fit(self, frame, base_logits, y):
        if self._attempted:
            raise ValueError("Warm start/retry on an attempted instance forbidden")
        self._attempted = True
        x = feature_array(frame)
        base = finite(base_logits, (len(x), 3))
        y = labels(y, len(x))
        if set(y) != set(CLASSES):
            raise ValueError("All three training classes required")
        with threadpool_limits(limits=1):
            scaler = StandardScaler().fit(x)
            u = finite(scaler.transform(x), x.shape)
            theta = initial_parameters()
            first, second = np.zeros(90), np.zeros(90)
            curve = []
            for epoch in range(1, 201):
                _, g = loss_gradient(theta, u, base, y)
                theta, first, second = adam_step(theta, g, first, second, epoch)
                loss, _ = loss_gradient(theta, u, base, y)
                curve.append(loss)
        self.theta_ = theta.copy()
        self.scaler_ = scaler
        self.loss_curve_ = curve
        self.classes_ = np.array(CLASSES)
        self.n_iter_ = 200
        self._fitted = True
        return self

    def _inputs(self, frame, base_logits):
        if not self._fitted:
            raise ValueError("Model not fitted")
        x = feature_array(frame)
        return finite(self.scaler_.transform(x), x.shape), finite(base_logits, (len(x), 3))

    def predict_proba(self, frame, base_logits):
        u, base = self._inputs(frame, base_logits)
        return forward(self.theta_, u, base)[0]

    def residual_logits(self, frame, base_logits):
        u, base = self._inputs(frame, base_logits)
        return forward(self.theta_, u, base)[2]

    def save(self, directory):
        if not self._fitted:
            raise ValueError("Cannot serialize unfitted model")
        payload = {"schema": "nn_v2_residual_artifact_v1", "role": "research_only_not_champion",
                   "specification": specification(), "versions": versions(), "theta": self.theta_.tolist(),
                   "classes": self.classes_.tolist(), "feature_order": list(FORM_FEATURES),
                   "scaler": {k: getattr(self.scaler_, k + "_").tolist()
                              for k in ("mean", "var", "scale")},
                   "training_rows": int(self.scaler_.n_samples_seen_),
                   "epochs": self.n_iter_, "loss_curve": self.loss_curve_}
        raw = (json.dumps(payload, sort_keys=True, allow_nan=False) + "\n").encode()
        folder = Path(directory)
        folder.mkdir(exist_ok=False)
        digest = hashlib.sha256(raw).hexdigest()
        for name, data in (("artifact.json", raw), ("artifact.sha256", (digest + "\n").encode())):
            with (folder/name).open("xb") as f:
                f.write(data)
                f.flush()
                os.fsync(f.fileno())
            if (folder/name).read_bytes() != data:
                raise ValueError("Artifact readback mismatch")
        return digest

    @classmethod
    def load(cls, directory, *, expected_sha256):
        if not isinstance(expected_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", expected_sha256):
            raise ValueError("Externally pinned artifact SHA required")
        folder = Path(directory)
        if {p.name for p in folder.iterdir()} != {"artifact.json", "artifact.sha256"}:
            raise ValueError("Unexpected artifact file set")
        raw = (folder/"artifact.json").read_bytes()
        if (hashlib.sha256(raw).hexdigest() != expected_sha256
                or expected_sha256 != (folder/"artifact.sha256").read_text().strip()):
            raise ValueError("Artifact SHA mismatch")
        def unique(pairs):
            d = {}
            for k, v in pairs:
                if k in d:
                    raise ValueError("Duplicate artifact JSON key")
                d[k] = v
            return d
        data = json.loads(raw, object_pairs_hook=unique)
        if not isinstance(data, dict) or not isinstance(data.get("scaler"), dict):
            raise ValueError("Artifact object/scaler required")
        expected = {"schema", "role", "specification", "versions", "theta", "classes", "feature_order",
                    "scaler", "training_rows", "epochs", "loss_curve"}
        if (set(data) != expected or data["schema"] != "nn_v2_residual_artifact_v1"
                or data["role"] != "research_only_not_champion"
                or data["versions"] != versions()
                or json.dumps(data["specification"], sort_keys=True, allow_nan=False) != json.dumps(specification(), sort_keys=True)
                or data["classes"] != list(CLASSES) or any(type(c) is not int for c in data["classes"])
                or data["feature_order"] != list(FORM_FEATURES) or type(data["epochs"]) is not int
                or data["epochs"] != 200 or type(data["training_rows"]) is not int
                or data["training_rows"] < 3 or set(data["scaler"]) != {"mean", "var", "scale"}):
            raise ValueError("Artifact contract mismatch")
        obj = cls()
        obj.theta_ = finite(data["theta"], (90,))
        obj.loss_curve_ = finite(data["loss_curve"], (200,)).tolist()
        if min(obj.loss_curve_) < 0:
            raise ValueError("Negative training objective")
        obj.scaler_ = StandardScaler()
        for k in ("mean", "var", "scale"):
            setattr(obj.scaler_, k + "_", finite(data["scaler"][k], (8,)))
        if (obj.scaler_.var_ < 0).any() or (obj.scaler_.scale_ <= 0).any():
            raise ValueError("Invalid scaler state")
        expected_scale = np.sqrt(obj.scaler_.var_)
        # sklearn may mark near-constant features scale=1; never accept arbitrary scales.
        tolerance = np.finfo(float).eps
        upper = data["training_rows"]*tolerance*obj.scaler_.var_ + (data["training_rows"]*obj.scaler_.mean_*tolerance)**2
        expected_scale[obj.scaler_.var_ <= upper] = 1
        if not np.array_equal(obj.scaler_.scale_, expected_scale):
            raise ValueError("Scaler scale/variance inconsistency")
        obj.scaler_.n_features_in_ = 8
        obj.scaler_.n_samples_seen_ = data["training_rows"]
        obj.classes_ = np.array(CLASSES)
        obj.n_iter_ = 200
        obj._attempted = obj._fitted = True
        return obj
