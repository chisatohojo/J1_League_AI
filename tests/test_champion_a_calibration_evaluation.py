"""Freeze section 18, contracts 01--45, visibly mapped by test names.

Only generated toy arrays and tmp_path equivalents are used. An autouse guard
rejects production pair/source/model/prediction/marker IO and network access.
No production preflight/formal CLI, real candidate fit, or full suite is run.
"""

import ast
import builtins
from contextlib import nullcontext
import copy
import inspect
import io
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
from types import SimpleNamespace
import warnings

import numpy as np
import pandas as pd
import pytest
from scipy import optimize

from src.modeling import champion_a_calibration_evaluation as c


REPOSITORY_ROOT = Path(__file__).parents[1]


@pytest.fixture(autouse=True)
def production_and_network_guard(monkeypatch):
    """All 45 contracts: refuse real data/model/result/marker and network IO."""
    root = str(REPOSITORY_ROOT).replace("\\", "/").casefold()
    def guarded(function):
        def call(file, *args, **kwargs):
            if not isinstance(file, int):
                name = os.path.abspath(str(file)).replace("\\", "/").casefold()
                if (name.startswith(root + "/data/") or name.startswith(root + "/models/")
                        or name == root + "/" + c.RESULT_PATH.casefold()):
                    pytest.fail(f"Production path access forbidden: {file}")
            return function(file, *args, **kwargs)
        return call
    for owner, name in ((builtins, "open"), (io, "open"), (os, "open")):
        monkeypatch.setattr(owner, name, guarded(getattr(owner, name)))
    for name in ("stat", "unlink", "mkdir", "rename", "replace"):
        monkeypatch.setattr(Path, name, guarded(getattr(Path, name)))
    def forbidden_network(*args, **kwargs):
        pytest.fail("Network access forbidden")
    monkeypatch.setattr(socket, "create_connection", forbidden_network)
    monkeypatch.setattr(socket.socket, "connect", forbidden_network)
    monkeypatch.setattr(socket.socket, "connect_ex", forbidden_network)
    # No fitting/prediction in another repository lane can slip into a helper.
    old_profile = sys.getprofile()
    def execution_guard(frame, event, arg):
        if event == "call":
            module = frame.f_globals.get("__name__", "")
            name = frame.f_code.co_name
            if module.startswith("src.") and name in {"reconstruct", "run_generation", "diagnose", "replay_elo", "predict_proba"}:
                pytest.fail(f"Forbidden repository execution: {module}.{name}")
            if module.startswith("sklearn.") and name == "fit" and module != "sklearn.preprocessing._label":
                pytest.fail(f"Predictive-model fit forbidden: {module}")
    sys.setprofile(execution_guard)
    yield
    sys.setprofile(old_profile)


def toy_arrays():
    p = np.array([[.6, .2, .2], [.2, .6, .2], [.2, .2, .6],
                  [.45, .35, .2], [.25, .45, .3], [.2, .35, .45]], dtype=np.float64)
    return p, np.array([0, 1, 2, 1, 2, 0], dtype=np.int64)


def rows_frame(counts=None):
    """Construct every byte/value synthetically, including diagnostic metadata."""
    counts = counts or {year: 3 for year in c.YEARS}
    records = []
    for year, n in counts.items():
        for i in range(n):
            p = np.array([1/3, 1/3, 1/3])
            y, ordinal, round_number = i % 3, i+1, i % 34+1
            first = int(ordinal <= 5)
            record = {
                "validation_year": year, "match_id": f"toy-{year}-{i:04}",
                "match_date": (pd.Timestamp(f"{year}-02-01") + pd.Timedelta(days=i//5)).strftime("%Y-%m-%d"),
                "home_team_id": "toy_home", "away_team_id": "toy_away", "result": y, "elo_diff": 0.0,
                "p_away": p[0], "p_draw": p[1], "p_home": p[2], "predicted_class": 0, "max_p": p.max(),
                "p_true": p[y], "nll": -np.log(p[y]), "brier": np.sum((p-np.eye(3)[y])**2),
                "abs_elo_diff": 0.0, "round": round_number, "home_team": "Toy home", "away_team": "Toy away",
                "season_phase": "opening" if round_number <= 5 else "middle" if round_number <= 29 else "closing",
                "home_season_appearance": ordinal, "away_season_appearance": ordinal,
                "home_first5": first, "away_first5": first, "any_team_first5": first, "both_team_first5": first,
                "home_status": "ESTABLISHED", "away_status": "ESTABLISHED", "promoted_involved": 0,
                "returning_involved": 0, "established_only": 1, "home_favorite": 0, "away_favorite": 0, "near_even": 1,
            }
            records.append(record)
    return pd.DataFrame(records, columns=c.COLUMNS).astype(c.DTYPES)


def bind_synthetic_constants(monkeypatch, rows):
    counts = rows.validation_year.value_counts().sort_index().to_dict()
    monkeypatch.setattr(c, "YEAR_COUNTS", counts)
    monkeypatch.setattr(c, "TRAIN_COUNTS", {y: len(rows.loc[rows.validation_year.lt(y)]) for y in c.EVALUATION_YEARS})
    monkeypatch.setattr(c, "OOF_ROWS", len(rows))
    monkeypatch.setattr(c, "POOLED_ROWS", len(rows.loc[rows.validation_year.ge(2021)]))
    monkeypatch.setattr(c, "VALID_ID_HASHES", {y: c.id_hash(rows.loc[rows.validation_year.eq(y), "match_id"]) for y in c.YEARS})
    monkeypatch.setattr(c, "TRAIN_ID_HASHES", {y: c.id_hash(rows.loc[rows.validation_year.lt(y), "match_id"]) for y in c.EVALUATION_YEARS})
    monkeypatch.setattr(c, "POOLED_ID_SHA", c.id_hash(rows.loc[rows.validation_year.ge(2021), "match_id"]))
    references = {str(y): c.calculate_metrics(f.result, f[list(c.P_COLUMNS)]) for y, f in rows.groupby("validation_year")}
    references["pooled"] = c.calculate_metrics(rows.result, rows[list(c.P_COLUMNS)])
    monkeypatch.setattr(c, "REFERENCES", references)


@pytest.fixture
def toy_rows(monkeypatch):
    rows = rows_frame()
    bind_synthetic_constants(monkeypatch, rows)
    return rows


def toy_runtime():
    return {"python": "3.12.14", "platform": "Windows-synthetic", **c.VERSIONS,
            "requirements_sha256": c.REQUIREMENTS_HASHES["requirements.txt"],
            "lock_sha256": c.REQUIREMENTS_HASHES["requirements-lock.txt"]}


def toy_manifest(rows, data, monkeypatch):
    metadata = {key: {"synthetic_metadata": key} for key in c.METADATA_HASHES}
    monkeypatch.setattr(c, "METADATA_HASHES", {key: c.metadata_hash(value) for key, value in metadata.items()})
    return {
        "schema_version": "champion_a_oof_diagnostic_v1",
        "purpose": "diagnostic_only_not_formal_evaluation_not_model_input",
        "reviewed_source_commit": "376973e1f2238bbd29799386ec100dd400648ce4",
        "freeze_spec": {"path": "docs/CHAMPION_A_OOF_DIAGNOSTIC_FREEZE_SPEC.md",
                       "sha256": "3167daf9ddff78ef4c3dceec64ed36782c6c36424baed239d83ce1191c023663",
                       "commit": "159ca0c7d71dfd10b9d3888971fb05c9f681855e"},
        "generation_authorization": {"reviewed_implementation_commit": c.GENERATOR_COMMIT, "task_reference": c.GENERATION_TASK},
        "generator": {"path": "src/modeling/champion_a_oof_diagnostic.py", "commit": c.GENERATOR_COMMIT,
                      "sha256": c.GENERATOR_SHA, "git_dirty": False, "fits": 5, "prediction_batches": 5, "automatic_retries": 0},
        "runtime": toy_runtime(), **metadata,
        "folds": [{"validation_year": y, "training_seasons": list(range(2015, y)),
                   "training_rows": {2020:1530,2021:1836,2022:2216,2023:2522,2024:2828}[y],
                   "validation_rows": c.YEAR_COUNTS[y], "train_ids_sha256": "a"*64,
                   "validation_ids_sha256": c.VALID_ID_HASHES[y]} for y in c.YEARS],
        "class_order": [0,1,2], "columns": list(c.COLUMNS), "column_dtypes": dict(c.DTYPES), "row_count": len(rows),
        "csv": {"path": c.CSV_PATH, "sha256": c.sha256(data), "encoding": "utf-8", "line_ending": "LF",
                "float_format": "%.17g", "ordered_ids_sha256": c.id_hash(rows.match_id)},
        "references": {"values": copy.deepcopy(c.REFERENCES),
                       "sources": ["docs/H2H_EVALUATION.md", "docs/MODEL_ARCHITECTURE_BENCHMARK_RESULT.md"], "rtol":0.0,"atol":1e-12},
        "observed_metrics": copy.deepcopy(c.REFERENCES), "gates": {g:"PASS" for g in c.GATE_NAMES},
        "generated_at": "2020-01-01T00:00:00Z",
    }


@pytest.fixture
def toy_pair(tmp_path, monkeypatch, toy_rows):
    root = tmp_path / "isolated"
    data = toy_rows.to_csv(index=False, lineterminator="\n", float_format="%.17g").encode()
    manifest = toy_manifest(toy_rows, data, monkeypatch)
    manifest_data = (json.dumps(manifest, indent=2) + "\n").encode()
    for path, buffer in ((c.CSV_PATH, data), (c.MANIFEST_PATH, manifest_data)):
        target = root/path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(buffer)
    (root/"docs").mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(c, "CSV_SHA", c.sha256(data))
    monkeypatch.setattr(c, "MANIFEST_SHA", c.sha256(manifest_data))
    return root, toy_rows, data, manifest


def stub_execution(monkeypatch, root):
    monkeypatch.setattr(c, "ROOT", root)
    monkeypatch.setattr(c, "execution_head", lambda target: "a"*40)
    monkeypatch.setattr(c, "verify_code", lambda target, head: "b"*64)
    monkeypatch.setattr(c, "runtime_provenance", lambda target: toy_runtime())
    monkeypatch.setenv(c.AUTHORIZATION_ENV, json.dumps({"approved_execution_head":"a"*40,"task_reference":"synthetic-formal-only"}))


def fake_result(theta, **changes):
    result = SimpleNamespace(success=True,status=0,x=np.array(theta,dtype=float),fun=1.0,
                             jac=np.zeros(len(theta)),nit=1,nfev=2,njev=2,message="synthetic convergence")
    for key,value in changes.items():
        setattr(result,key,value)
    return result


def score(ll=1.0, brier=.6, accuracy=.4, n=1):
    return {"n":n,"accuracy":accuracy,"log_loss":ll,"brier":brier}


def decision_values():
    base={y:score(n=c.YEAR_COUNTS[y]) for y in c.EVALUATION_YEARS}
    improved={y:score(ll=.9,n=c.YEAR_COUNTS[y]) for y in c.EVALUATION_YEARS}
    pooled_base=score(n=c.POOLED_ROWS)
    pooled_improved=score(ll=.9,n=c.POOLED_ROWS)
    return base,improved,pooled_base,pooled_improved


def test_contract_01_committed_spec_pin_schema_and_pair_validation(toy_pair):
    root,rows,data,manifest=toy_pair
    spec=(REPOSITORY_ROOT/c.SPEC_PATH).read_bytes()  # Docs only, never data.
    assert c.sha256(spec)==c.SPEC_SHA=="821e2a35e99bb7c785cd5405aa241ba898ef452123428199ac671a6c50df2e07"
    assert c.SPEC_COMMIT=="b5354705f1a7a32e64e2a0d484e22cd55f59d483"
    actual,loaded=c.load_accepted(root)
    pd.testing.assert_frame_equal(actual,rows)
    assert loaded==manifest
    assert c.baseline_gate(actual,loaded)==c.REFERENCES


@pytest.mark.parametrize("failure", ["csv_sha","manifest_sha","missing_csv","missing_manifest"])
def test_contract_01_corrupt_missing_partial_pair_rejects_before_parse(toy_pair,monkeypatch,failure):
    root,_,_,_=toy_pair
    if failure.startswith("missing"):
        (root/(c.CSV_PATH if failure=="missing_csv" else c.MANIFEST_PATH)).unlink()
    else:
        path=root/(c.CSV_PATH if failure=="csv_sha" else c.MANIFEST_PATH)
        path.write_bytes(path.read_bytes()+b" ")
    monkeypatch.setattr(c,"parse_rows",lambda _:pytest.fail("Must refuse before parsing"))
    with pytest.raises((c.CalibrationError,FileNotFoundError)):
        c.load_accepted(root)


@pytest.mark.parametrize("field,value", [
    ("class_order",[2,1,0]),("purpose","wrong"),("schema_version","wrong"),("row_count",999),
    ("columns",list(reversed(c.COLUMNS))),("column_dtypes",{}),("generator",{}),
    ("generation_authorization",{}),("gates",{}),("inputs",{}),("team_master",{}),
    ("champion_a_contract",{}),("diagnostic_contract",{}),("runtime",{}),("references",{}),
])
def test_contract_01_manifest_schema_provenance_rejection(toy_pair,field,value):
    _,rows,data,manifest=toy_pair
    manifest=copy.deepcopy(manifest);manifest[field]=value
    with pytest.raises((c.CalibrationError,KeyError)):
        c.validate_manifest(manifest,data,rows)


@pytest.mark.parametrize("failure",["header","duplicate_id","dtype","noncanonical","stored_flag","stored_derived","bom","crlf","empty"])
def test_contract_01_row_schema_and_identity_reject(toy_rows,failure):
    rows=toy_rows.copy(deep=True)
    if failure in ("header","bom","crlf","empty"):
        data=rows.to_csv(index=False,lineterminator="\n",float_format="%.17g").encode()
        data={"header":data.replace(b"validation_year",b"season",1),"bom":b"\xef\xbb\xbf"+data,
              "crlf":data.replace(b"\n",b"\r\n"),"empty":b""}[failure]
        with pytest.raises(c.CalibrationError):
            c.parse_rows(data)
        return
    if failure=="duplicate_id":rows.loc[1,"match_id"]=rows.loc[0,"match_id"]
    elif failure=="dtype":rows["result"]=rows.result.astype(float)
    elif failure=="noncanonical":rows=rows.iloc[::-1].reset_index(drop=True)
    elif failure=="stored_flag":rows.loc[0,"near_even"]=0
    elif failure=="stored_derived":rows.loc[0,"p_true"]+=.01
    with pytest.raises(c.CalibrationError):
        c.validate_rows(rows)


@pytest.mark.parametrize("year",[2019,2025,2026,2027])
def test_contract_02_only_exact_artifact_years_accepted(toy_rows,year):
    rows=toy_rows.copy(deep=True);rows.loc[0,"validation_year"]=year
    with pytest.raises(c.CalibrationError):
        c.rolling_folds(rows)


def test_contract_03_2020_is_warmup_only(toy_rows):
    folds=c.rolling_folds(toy_rows)
    assert [f[0] for f in folds]==[2021,2022,2023,2024]
    assert set(folds[0][1].validation_year)=={2020}
    assert all(not f[2].validation_year.eq(2020).any() for f in folds)


def test_contract_04_full_synthetic_frozen_counts_and_order(monkeypatch):
    assert c.YEAR_COUNTS=={2020:306,2021:380,2022:306,2023:306,2024:380}
    assert list(c.TRAIN_COUNTS.values())==[306,686,992,1298]
    assert c.POOLED_ROWS==1372 and c.OOF_ROWS==1678
    rows=rows_frame(dict(c.YEAR_COUNTS))
    bind_synthetic_constants(monkeypatch,rows)
    folds=c.rolling_folds(rows)
    assert [(len(t),len(v)) for _,t,v in folds]==[(306,380),(686,306),(992,306),(1298,380)]
    assert sum(len(v) for _,_,v in folds)==1372
    with pytest.raises(c.CalibrationError):
        c.rolling_folds(rows.iloc[:-1])


def test_contract_05_no_target_rows_and_date_identity_gates(toy_rows,monkeypatch):
    for y,t,v in c.rolling_folds(toy_rows):
        assert t.validation_year.lt(y).all() and v.validation_year.eq(y).all()
        assert set(t.match_id).isdisjoint(v.match_id)
        assert t.match_date.max()<v.match_date.min()
    # Skip only the outer structural validator to directly exercise date separation.
    monkeypatch.setattr(c,"validate_rows",lambda _:None)
    bad=toy_rows.copy(deep=True)
    bad.loc[bad.validation_year.eq(2020),"match_date"]="2021-12-31"
    with pytest.raises(c.CalibrationError,match="Non-prior"):
        c.rolling_folds(bad)


def test_contract_06_class_order_labels_and_missing_training_class(monkeypatch):
    p,y=toy_arrays()
    with pytest.raises(c.CalibrationError):
        c.fit_calibrator(p,np.zeros(len(y),dtype=int),"C1")
    for bad in ([0,1,3,0,1,2],[0,.5,2,0,1,2],[-1,0,1,2,0,1],["0"]*6):
        with pytest.raises(c.CalibrationError):
            c.labels(bad,6)
    monkeypatch.setattr(c,"CLASS_ORDER",(2,1,0))
    with pytest.raises(c.CalibrationError):
        c.labels(y,len(y))


@pytest.mark.parametrize("value",[0.0,-.1,np.nan,np.inf])
def test_contract_07_positive_finite_input_gate(value):
    p,_=toy_arrays();p[0,0]=value
    with pytest.raises(c.CalibrationError):
        c.apply_calibration(p,{"candidate":"C1","parameters":(1.0,)})


@pytest.mark.parametrize("name,theta",[("C1",(10000.,)),("C2",(10000.,0.)),("C3",(1.,10000.,0.))])
def test_contract_07_underflow_hard_stop_no_clipping(name,theta):
    p,y=toy_arrays()
    with pytest.raises(c.CalibrationError):
        c.objective_and_gradient(theta,p,y,name)


@pytest.mark.parametrize("bad", [np.ones(3),np.ones((2,2)),np.zeros((0,3)),np.array([[.5,.5,.5]]),np.array([[1.1,.1,.1]])])
def test_contract_08_probability_shape_range_sum_gate(bad):
    with pytest.raises(c.CalibrationError):
        c.probabilities(bad)


def test_contract_08_near_unit_sum_not_repaired():
    p=np.array([[.2,.3,.5+5e-13]])
    original=p.copy()
    result=c.apply_calibration(p,{"candidate":"A0","parameters":()})
    assert np.array_equal(result,original) and np.array_equal(p,original)
    assert result.sum()!=1.0
    with pytest.raises(c.CalibrationError):
        c.probabilities(p+1e-11)


def test_contract_09_stable_transform_uniform_boundary_and_float64():
    p=np.array([[1e-300,.4,.6]],dtype=np.float64)
    _,log_q,q=c.transform_components(p,"C1",(1.0,))
    assert q.dtype==np.float64 and np.isfinite(log_q).all() and (q>0).all()
    np.testing.assert_allclose(q,p,rtol=0,atol=1e-12)
    uniform=c.apply_calibration(p,{"candidate":"C1","parameters":(0.0,)})
    np.testing.assert_allclose(uniform,np.full((1,3),1/3),rtol=0,atol=1e-12)
    q=c.apply_calibration(p,{"candidate":"C3","parameters":(0.,.2,-.1)})
    expected=np.exp([0,.2,-.1]);expected/=expected.sum()
    np.testing.assert_allclose(q[0],expected,rtol=0,atol=1e-12)


def test_contract_10_c1_identity():
    p,_=toy_arrays()
    np.testing.assert_allclose(c.apply_calibration(p,{"candidate":"C1","parameters":(1.,)}),p,rtol=0,atol=1e-12)


def test_contract_11_c2_identity():
    p,_=toy_arrays()
    np.testing.assert_allclose(c.apply_calibration(p,{"candidate":"C2","parameters":(0.,0.)}),p,rtol=0,atol=1e-12)


def test_contract_12_c3_identity():
    p,_=toy_arrays()
    np.testing.assert_allclose(c.apply_calibration(p,{"candidate":"C3","parameters":(1.,0.,0.)}),p,rtol=0,atol=1e-12)


def test_contract_13_b_away_fixed_no_extra_parameter():
    for name,theta in [("C1",(2.,)),("C2",(.2,-.1)),("C3",(2.,.2,-.1))]:
        _,b=c.parameters(name,theta)
        assert b[0]==0
        with pytest.raises(c.CalibrationError):
            c.parameters(name,(*theta,.3))


def analytic_check(name,theta):
    p,y=toy_arrays()
    loss,g=c.objective_and_gradient(theta,p,y,name)
    _,log_q,q=c.transform_components(p,name,theta)
    expected_tau=np.mean(np.sum(q*np.log(p),axis=1)-np.log(p[np.arange(len(y)),y]))
    residual=q-np.eye(3)[y]
    expected={"C1":np.array([expected_tau]),"C2":residual[:,1:].mean(axis=0),
              "C3":np.r_[expected_tau,residual[:,1:].mean(axis=0)]}[name]
    assert isinstance(loss,np.float64) and g.dtype==np.float64
    assert loss==np.mean(-log_q[np.arange(len(y)),y])
    np.testing.assert_allclose(g,expected,rtol=0,atol=1e-12)


def test_contract_14_c1_analytic_gradient():
    analytic_check("C1",(1.3,))


def test_contract_15_c2_analytic_gradient():
    analytic_check("C2",(.2,-.1))


def test_contract_16_c3_analytic_gradient():
    analytic_check("C3",(1.3,.2,-.1))


@pytest.mark.parametrize("name,theta",[("C1",(1.3,)),("C2",(.2,-.1)),("C3",(1.3,.2,-.1))])
def test_contract_17_central_difference_gradient(name,theta):
    p,y=toy_arrays();theta=np.array(theta)
    _,gradient=c.objective_and_gradient(theta,p,y,name)
    finite=[]
    for j in range(len(theta)):
        plus,minus=theta.copy(),theta.copy()
        plus[j]+=1e-6;minus[j]-=1e-6
        finite.append((c.objective_and_gradient(plus,p,y,name)[0]-c.objective_and_gradient(minus,p,y,name)[0])/(2e-6))
    np.testing.assert_allclose(gradient,finite,rtol=1e-5,atol=1e-7)


@pytest.mark.parametrize("name",["C1","C2","C3"])
def test_contract_18_repeated_synthetic_fit_and_probabilities_deterministic(name):
    p,y=toy_arrays();original=p.copy()
    first=c.fit_calibrator(p,y,name);second=c.fit_calibrator(p,y,name)
    assert first==second
    assert np.array_equal(c.apply_calibration(p,first),c.apply_calibration(p,second))
    assert np.array_equal(p,original)


@pytest.mark.parametrize("name",["C1","C2","C3"])
def test_contract_19_exact_optimizer_call_identity_bounds_options(monkeypatch,name):
    p,y=toy_arrays();calls=[]
    def optimizer(**kwargs):
        calls.append(kwargs)
        assert kwargs["args"]==() and kwargs["method"]=="L-BFGS-B" and kwargs["jac"] is True
        assert kwargs["tol"] is None and kwargs["callback"] is None
        assert kwargs["bounds"]==c.CANDIDATES[name].bounds
        assert kwargs["options"]=={"maxcor":10,"maxiter":15000,"maxfun":15000,
                                  "ftol":2.220446049250313e-09,"gtol":1e-05,"maxls":20}
        assert set(kwargs)=={"fun","x0","args","method","jac","bounds","tol","callback","options"}
        assert kwargs["x0"].dtype==np.float64
        assert tuple(kwargs["x0"])==c.CANDIDATES[name].initial
        assert kwargs["fun"](kwargs["x0"])[1].shape==kwargs["x0"].shape
        return fake_result(kwargs["x0"])
    monkeypatch.setattr(optimize,"minimize",optimizer)
    c.fit_calibrator(p,y,name)
    assert len(calls)==1
    with pytest.raises(c.CalibrationError):
        c.parameters("C1",(-1e-15,))


@pytest.mark.parametrize("changes", [
    {"success":False},{"status":1},{"x":np.array([np.nan])},{"x":np.array([-1e-15])},
    {"x":np.array([1.,2.])},{"fun":np.inf},{"fun":np.array([1.])},
    {"jac":np.array([np.nan])},{"jac":np.zeros(2)},
])
def test_contract_20_optimizer_result_failures_stop_once(monkeypatch,changes):
    p,y=toy_arrays();calls=[]
    def optimizer(**kwargs):
        calls.append(1);return fake_result([1.],**changes)
    monkeypatch.setattr(optimize,"minimize",optimizer)
    with pytest.raises(c.CalibrationError) as error:
        c.fit_calibrator(p,y,"C1")
    assert error.value.status==c.OPTIMIZER_FAILURE and len(calls)==1


@pytest.mark.parametrize("failure",["warning","exception"])
def test_contract_20_warnings_errors_no_reinterpretation(monkeypatch,failure):
    p,y=toy_arrays();calls=[]
    def optimizer(**kwargs):
        calls.append(1)
        if failure=="warning":warnings.warn("synthetic warning",UserWarning)
        raise RuntimeError("synthetic optimizer failure")
    monkeypatch.setattr(optimize,"minimize",optimizer)
    with pytest.raises(c.CalibrationError):
        c.fit_calibrator(p,y,"C1")
    assert len(calls)==1


def test_contract_20_ftol_success_and_projected_gradient_are_recorded(monkeypatch):
    p,y=toy_arrays()
    monkeypatch.setattr(optimize,"minimize",lambda **kwargs:fake_result([0.],jac=np.array([.5]),message="ftol success"))
    result=c.fit_calibrator(p,y,"C1")
    assert result["optimizer"]["jac"]==[.5]
    assert result["optimizer"]["projected_gradient_inf"]==0
    assert set(result["optimizer"])=={"success","status","message","nit","nfev","njev","fun","jac","projected_gradient_inf"}


def test_contract_21_no_restart_warm_start_exact_fold_major_calls(toy_rows,monkeypatch):
    calls=[]
    def optimizer(**kwargs):
        calls.append(tuple(kwargs["x0"]))
        return fake_result(kwargs["x0"])
    monkeypatch.setattr(optimize,"minimize",optimizer)
    result=c.evaluate(toy_rows)
    assert calls==[(1.,),(0.,0.),(1.,0.,0.)]*4
    assert result["fits"]==result["applications"]==12


def test_contract_22_unpenalized_objective_no_extra_term():
    p,y=toy_arrays()
    theta=(2.,.4,-.3)
    loss,_=c.objective_and_gradient(theta,p,y,"C3")
    z=2*np.log(p)+np.array([0,.4,-.3])
    shifted=z-z.max(axis=1,keepdims=True)
    q=np.exp(shifted)/np.exp(shifted).sum(axis=1,keepdims=True)
    assert loss==pytest.approx(np.mean(-np.log(q[np.arange(len(y)),y])),abs=1e-12)
    assert set(inspect.signature(c.objective_and_gradient).parameters)=={"theta","p","y","name"}


def test_contract_23_no_weights_equal_row_mean():
    p,y=toy_arrays()
    loss,g=c.objective_and_gradient((1.2,),p,y,"C1")
    loss2,g2=c.objective_and_gradient((1.2,),np.repeat(p,2,axis=0),np.repeat(y,2),"C1")
    assert loss==pytest.approx(loss2,abs=1e-12)
    np.testing.assert_allclose(g,g2,rtol=0,atol=1e-12)
    with pytest.raises(TypeError):
        c.fit_calibrator(p,y,"C1",sample_weight=np.ones(len(y)))


def test_contract_24_prior_only_closures_and_target_api_once(toy_rows,monkeypatch):
    fits=[];applications=[]
    def fit(p,y,name):
        index=len(fits)//3
        prior=toy_rows.loc[toy_rows.validation_year.lt(c.EVALUATION_YEARS[index])]
        assert np.array_equal(p,prior[list(c.P_COLUMNS)].to_numpy())
        assert np.array_equal(y,prior.result.to_numpy())
        fits.append((name,len(y)))
        return {"candidate":name,"parameters":c.CANDIDATES[name].initial,"optimizer":{}}
    original=c.apply_calibration
    def apply(p,fitted):
        assert p.shape==(3,3)
        applications.append(fitted["candidate"])
        return original(p,fitted)
    monkeypatch.setattr(c,"fit_calibrator",fit)
    monkeypatch.setattr(c,"apply_calibration",apply)
    c.evaluate(toy_rows)
    assert len(fits)==len(applications)==12
    assert tuple(inspect.signature(original).parameters)==("p","fitted")
    assert tuple(inspect.signature(c.fit_calibrator).parameters)==("p","y","name")


def static_source():
    return ast.parse((REPOSITORY_ROOT/c.MODULE_PATH).read_text(encoding="utf-8"))


def imported_names():
    result=[]
    for node in ast.walk(static_source()):
        if isinstance(node,ast.ImportFrom):result.append(node.module)
        elif isinstance(node,ast.Import):result.extend(a.name for a in node.names)
    return result


def test_contract_25_no_base_model_dependency():
    assert not any(n and n.startswith(("src.","sklearn.linear_model","sklearn.pipeline")) for n in imported_names())
    attrs=[n.attr for n in ast.walk(static_source()) if isinstance(n,ast.Attribute)]
    assert "predict_proba" not in attrs and "fit" not in attrs


def test_contract_26_no_elo_or_replay_dependency():
    assert not any(n and "elo" in n for n in imported_names())
    calls=[n.func.id for n in ast.walk(static_source()) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name)]
    assert "replay_elo" not in calls


def test_contract_27_exact_two_data_paths_and_guard(toy_pair,monkeypatch):
    root,_,_,_=toy_pair
    reads=[];original=Path.read_bytes
    def read(path):
        reads.append(path)
        return original(path)
    monkeypatch.setattr(Path,"read_bytes",read)
    c.load_accepted(root)
    assert reads==[root/c.CSV_PATH,root/c.MANIFEST_PATH]
    for path in ("data/processed/jleague/2020_matches_probe.csv","data/raw/source.csv","models/bundle.pkl",
                 "data/master/teams.csv"):
        with pytest.raises(pytest.fail.Exception):
            (REPOSITORY_ROOT/path).read_bytes()


def test_contract_28_2025_access_guard():
    with pytest.raises(pytest.fail.Exception):
        (REPOSITORY_ROOT/"data/processed/jleague/2025_matches_probe.csv").read_bytes()
    assert 2025 not in c.YEARS and 2025 not in c.EVALUATION_YEARS


def test_contract_29_opened_years_and_persisted_predictions_guard():
    for path in ("data/processed/jleague/2026_matches.csv","data/raw/2027/outcomes.csv","data/processed/predictions/saved.csv"):
        with pytest.raises(pytest.fail.Exception):
            (REPOSITORY_ROOT/path).read_bytes()
    assert not any(n and "predict" in n for n in imported_names())


def test_contract_30_metrics_deltas_argmax_brier_and_loss_semantics():
    p=np.full((3,3),1/3);y=np.array([0,1,2])
    metrics=c.calculate_metrics(y,p)
    assert metrics["accuracy"]==1/3
    assert metrics["log_loss"]==pytest.approx(np.log(3))
    assert metrics["brier"]==pytest.approx(2/3)
    assert c.metric_delta(metrics,metrics)=={"accuracy":0.,"log_loss":0.,"brier":0.}
    tiny=np.array([[1e-100,.4,.6]])
    reported=c.calculate_metrics([0],tiny)["log_loss"]
    fit_loss,_=c.objective_and_gradient((1.,),tiny,[0],"C1")
    assert reported==pytest.approx(-np.log(np.finfo(np.float64).eps))
    assert fit_loss>reported
    assert tiny[0,0]==1e-100


def test_contract_30_reference_failure_stops_before_candidate(toy_pair,monkeypatch):
    root,rows,_,manifest=toy_pair
    changed=copy.deepcopy(manifest);changed["observed_metrics"]["2020"]["log_loss"]+=.01
    with pytest.raises(c.CalibrationError) as error:
        c.baseline_gate(rows,changed)
    assert error.value.status==c.REFERENCE_FAILURE
    assert c.baseline_gate(rows,manifest)==c.REFERENCES
    baseline=c.REFERENCES["2020"]
    for difference,passes in [(5e-13,True),(2e-12,False)]:
        actual=dict(baseline,log_loss=baseline["log_loss"]+difference)
        if passes:c.assert_reference(actual,baseline)
        else:
            with pytest.raises(c.CalibrationError):c.assert_reference(actual,baseline)


def test_contract_31_pooled_metrics_from_rows_not_fold_average(monkeypatch):
    rows=rows_frame({2020:3,2021:3,2022:6,2023:3,2024:9})
    # Different synthetic outcome mixes and positive p distributions.
    for year in c.EVALUATION_YEARS:
        mask=rows.validation_year.eq(year)
        p=np.tile([.2,.3,.5] if year==2024 else [.6,.2,.2],(mask.sum(),1))
        y=rows.loc[mask,"result"].to_numpy()
        rows.loc[mask,list(c.P_COLUMNS)]=p
        rows.loc[mask,"max_p"]=p.max(axis=1)
        rows.loc[mask,"p_true"]=p[np.arange(len(y)),y]
        rows.loc[mask,"predicted_class"]=p.argmax(axis=1)
        rows.loc[mask,"nll"]=-np.log(p[np.arange(len(y)),y])
        rows.loc[mask,"brier"]=np.sum((p-np.eye(3)[y])**2,axis=1)
        rows.loc[mask,"home_favorite"]=int(year==2024)
        rows.loc[mask,"away_favorite"]=int(year!=2024)
        rows.loc[mask,"near_even"]=0
    bind_synthetic_constants(monkeypatch,rows)
    monkeypatch.setattr(optimize,"minimize",lambda **kw:fake_result(kw["x0"]))
    outcome=c.evaluate(rows)
    targets=rows.loc[rows.validation_year.ge(2021)]
    assert outcome["results"]["A0"]["pooled"]==c.calculate_metrics(targets.result,targets[list(c.P_COLUMNS)])
    folds=outcome["results"]["A0"]["folds"]
    assert outcome["results"]["A0"]["pooled"]["log_loss"]!=np.mean([v["log_loss"] for v in folds.values()])


def test_contract_32_strict_improvement_count_no_epsilon():
    base,improved,bp,ip=decision_values()
    improved[2024]=copy.deepcopy(base[2024])
    gate=c.candidate_pass(improved,ip,base,bp)
    assert gate["improved_ll_folds"]==3 and gate["passes"]
    improved[2023]["log_loss"]=base[2023]["log_loss"]-1e-15
    assert c.candidate_pass(improved,ip,base,bp)["improved_ll_folds"]==3
    ip["log_loss"]=bp["log_loss"]
    assert not c.candidate_pass(improved,ip,base,bp)["passes"]


def test_contract_33_pooled_brier_equality_passes_tiny_worsening_fails():
    base,improved,bp,ip=decision_values()
    assert c.candidate_pass(improved,ip,base,bp)["passes"]
    ip["brier"]=bp["brier"]+1e-15
    assert not c.candidate_pass(improved,ip,base,bp)["passes"]


def test_contract_34_accuracy_and_calibration_context_cannot_gate():
    base,improved,bp,ip=decision_values()
    ip["accuracy"]=0
    for row in improved.values():row["accuracy"]=0
    assert c.candidate_pass(improved,ip,base,bp)["passes"]
    p,y=toy_arrays()
    context=c.calibration_context(y,p)
    np.testing.assert_allclose(context["bias"],np.array(context["empirical_frequency"])-context["mean_probability"])
    assert set(inspect.signature(c.candidate_pass).parameters)=={"fold_values","pooled","baseline_folds","baseline_pooled"}


def test_contract_35_three_of_four_conjunction_and_fixed_denominator():
    base,improved,bp,ip=decision_values()
    improved[2024]=copy.deepcopy(base[2024]);improved[2023]=copy.deepcopy(base[2023])
    assert not c.candidate_pass(improved,ip,base,bp)["passes"]
    del improved[2024]
    with pytest.raises(c.CalibrationError):c.candidate_pass(improved,ip,base,bp)


def selection_fixture(losses,passing):
    return {"A0":{},**{name:{"pooled":{"log_loss":losses[name]},"gate":{"passes":name in passing}} for name in ("C1","C2","C3")}}


def test_contract_36_lowest_pooled_ll_passing_only():
    result=c.select_candidate(selection_fixture({"C1":.8,"C2":.9,"C3":.7},["C1","C2"]))
    assert result["selected_candidate"]=="C1" and result["decision"]==c.PROCEED_GATE
    result=c.select_candidate(selection_fixture({"C1":.8,"C2":.9,"C3":.7},[]))
    assert result=={"decision":c.CLOSE_GATE,"selected_candidate":None,"tied_candidates":[]}


def test_contract_37_minimum_anchored_tie_complexity_not_chained():
    result=c.select_candidate(selection_fixture({"C1":1.+1.5e-12,"C2":1.+.8e-12,"C3":1.},["C1","C2","C3"]))
    assert result["tied_candidates"]==["C2","C3"] and result["selected_candidate"]=="C2"
    result=c.select_candidate(selection_fixture({"C1":1.+.5e-12,"C2":1.,"C3":1.},["C1","C2","C3"]))
    assert result["selected_candidate"]=="C1"
    result=c.select_candidate(selection_fixture({"C1":1000.+5e-10,"C2":1000.,"C3":1001.},["C1","C2","C3"]))
    assert result["selected_candidate"]=="C2"  # rtol=0, not relative tolerance.


def test_contract_38_exact_registry_a0_unfitted_value_preserving():
    c.validate_registry()
    assert tuple(c.CANDIDATES)==("A0","C1","C2","C3")
    assert [len(v.coordinates) for v in c.CANDIDATES.values()]==[0,1,2,3]
    p,y=toy_arrays()
    assert np.array_equal(c.apply_calibration(p,{"candidate":"A0","parameters":()}),p)
    with pytest.raises(c.CalibrationError):c.fit_calibrator(p,y,"A0")
    with pytest.raises(TypeError):c.CANDIDATES["C4"]=c.CANDIDATES["C1"]


def test_contract_39_no_new_family_or_posthoc_criteria(monkeypatch):
    with pytest.raises(c.CalibrationError):c.candidate("isotonic")
    monkeypatch.setattr(c,"CANDIDATES",{**c.CANDIDATES,"C4":c.Candidate((),(),())})
    with pytest.raises(c.CalibrationError):c.validate_registry()
    assert not any(n and any(token in n for token in ("isotonic","calibration","linear_model")) for n in imported_names())


@pytest.mark.parametrize("auth", [
    {},{"approved_execution_head":"a"*40},{"approved_execution_head":"b"*40,"task_reference":"toy"},
    {"approved_execution_head":"a"*40,"task_reference":""},
    {"approved_execution_head":"a"*40,"task_reference":c.GENERATION_TASK},
    {"approved_execution_head":"a"*40,"task_reference":" "+c.GENERATION_TASK+" "},
    {"approved_execution_head":"a"*40,"task_reference":"toy","optimizer":"other"},
])
def test_contract_40_invalid_authority_refused_before_marker(toy_pair,monkeypatch,auth):
    root,_,_,_=toy_pair
    stub_execution(monkeypatch,root)
    monkeypatch.setenv(c.AUTHORIZATION_ENV,json.dumps(auth))
    with pytest.raises(c.CalibrationError):c.formal()
    assert not (root/c.MARKER_PATH).exists()


def test_contract_40_dirty_execution_head_refused(monkeypatch,tmp_path):
    monkeypatch.setattr(c,"git",lambda root,*args:b" M uncommitted\n")
    with pytest.raises(c.CalibrationError,match="Clean tree"):c.execution_head(tmp_path)


@pytest.mark.parametrize("existing",[c.MARKER_PATH,c.RESULT_PATH])
def test_contract_40_existing_partial_entries_refuse_before_fit(toy_pair,monkeypatch,existing):
    root,_,_,_=toy_pair
    stub_execution(monkeypatch,root)
    path=root/existing;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b"partial evidence")
    monkeypatch.setattr(c,"fit_calibrator",lambda *a,**kw:pytest.fail("Existing evidence must stop before fit"))
    with pytest.raises(c.CalibrationError):c.formal()
    assert path.read_bytes()==b"partial evidence"
    if existing==c.RESULT_PATH:
        assert not (root/c.MARKER_PATH).exists()


def test_contract_40_dangling_entry_refused(monkeypatch,tmp_path):
    monkeypatch.setattr(Path,"exists",lambda path:False)
    monkeypatch.setattr(Path,"is_symlink",lambda path:True)
    with pytest.raises(c.CalibrationError):c.refuse_existing(tmp_path)


def test_contract_40_durable_marker_precedes_all_gates_and_success_second_refused(toy_pair,monkeypatch):
    root,_,_,_=toy_pair
    stub_execution(monkeypatch,root)
    original=c.verify_code;events=[]
    original_fsync=os.fsync
    def fsync(fd):
        events.append("fsync");return original_fsync(fd)
    monkeypatch.setattr(os,"fsync",fsync)
    def verify(root,head):
        marker=json.loads((root/c.MARKER_PATH).read_bytes())
        assert marker["state"]=="ATTEMPT_CONSUMED" and events==["fsync"]
        events.append("gate");return original(root,head)
    monkeypatch.setattr(c,"verify_code",verify)
    result=c.formal()  # Synthetic tmp-root orchestration ONLY, not production CLI.
    assert result["status"]=="COMPLETE" and result["fits"]==result["applications"]==12
    marker_before=(root/c.MARKER_PATH).read_bytes()
    result_before=(root/c.RESULT_PATH).read_bytes()
    with pytest.raises(c.CalibrationError):c.formal()
    assert marker_before==(root/c.MARKER_PATH).read_bytes()
    assert result_before==(root/c.RESULT_PATH).read_bytes()
    document=result_before.decode()
    for token in ("1372" if c.POOLED_ROWS==1372 else str(c.POOLED_ROWS),
                  "Parameters","Delta LL","Calibration context","Final research decision","NOT USED"):
        assert token in document


def test_contract_40_concurrent_windows_mutex_refusal(tmp_path):
    # Actual kernel mutex, but ONLY a tmp-root name; no marker or fitting.
    with c.process_lock(tmp_path):
        with pytest.raises(c.CalibrationError,match="Concurrent"):
            with c.process_lock(tmp_path):
                pytest.fail("Second lock entered")
        script=("from pathlib import Path; import sys; "
                "from src.modeling.champion_a_calibration_evaluation import process_lock, CalibrationError\n"
                "try:\n"
                "    with process_lock(Path(sys.argv[1])): raise RuntimeError('unexpected lock')\n"
                "except CalibrationError:\n"
                "    print('CONCURRENT_REFUSED')\n")
        result=subprocess.run([sys.executable,"-B","-c",script,str(tmp_path)],cwd=REPOSITORY_ROOT,capture_output=True,text=True,check=True)
        assert result.stdout.strip()=="CONCURRENT_REFUSED"
    with c.process_lock(tmp_path):
        pass


@pytest.mark.parametrize("stage",["artifact","reference","optimizer","application","publication"])
def test_contract_41_failed_attempt_persists_without_retry(toy_pair,monkeypatch,stage):
    root,_,_,_=toy_pair
    stub_execution(monkeypatch,root)
    def fail(*args,**kwargs):raise c.CalibrationError("synthetic stage failure")
    target={"artifact":"load_accepted","reference":"baseline_gate","optimizer":"fit_calibrator",
            "application":"apply_calibration","publication":"publish_result"}[stage]
    monkeypatch.setattr(c,target,fail)
    with pytest.raises(c.CalibrationError,match="consumed attempt retained") as error:c.formal()
    assert "progress=" in str(error.value)
    marker=(root/c.MARKER_PATH).read_bytes()
    assert json.loads(marker)["state"]=="ATTEMPT_CONSUMED"
    with pytest.raises(c.CalibrationError):c.formal()
    assert marker==(root/c.MARKER_PATH).read_bytes()
    assert not (root/c.RESULT_PATH).exists()


def test_contract_41_marker_flush_failure_preserves_evidence_and_zero_fit_progress(toy_pair,monkeypatch):
    root,_,_,_=toy_pair
    stub_execution(monkeypatch,root)
    def fail_fsync(fd):raise OSError("synthetic marker fsync failure")
    def forbidden(*args,**kwargs):pytest.fail("Pre-fit gate/fit entered before durable marker")
    monkeypatch.setattr(os,"fsync",fail_fsync)
    monkeypatch.setattr(c,"verify_code",forbidden)
    monkeypatch.setattr(c,"fit_calibrator",forbidden)
    with pytest.raises(c.CalibrationError,match="consumed attempt retained") as error:c.formal()
    message=str(error.value)
    assert "marker consumption" in message and "'fit_attempts': 0" in message
    assert "'application_attempts': 0" in message
    marker=(root/c.MARKER_PATH).read_bytes()
    assert json.loads(marker)["state"]=="ATTEMPT_CONSUMED"
    with pytest.raises(c.CalibrationError):c.formal()
    assert (root/c.MARKER_PATH).read_bytes()==marker and not (root/c.RESULT_PATH).exists()


def test_contract_42_exclusive_publication_no_overwrite_or_cleanup(toy_pair):
    root,_,_,_=toy_pair
    payload={"schema_version":"champion_a_calibration_attempt_v1","state":"ATTEMPT_CONSUMED"}
    marker_sha=c.consume_marker(root,payload)
    marker=(root/c.MARKER_PATH).read_bytes()
    with pytest.raises(c.CalibrationError):c.consume_marker(root,payload)
    c.publish_result(root,"synthetic result\n",marker_sha)
    with pytest.raises(c.CalibrationError):c.publish_result(root,"replacement",marker_sha)
    assert (root/c.RESULT_PATH).read_text()=="synthetic result\n"
    assert (root/c.MARKER_PATH).read_bytes()==marker
    methods=[n.attr for n in ast.walk(static_source()) if isinstance(n,ast.Attribute)]
    assert not any(method in methods for method in ("unlink","rename","rmdir","glob","rglob","to_csv","write_bytes"))
    # UTC string.replace is legitimate; filesystem Path.replace is not.
    replacements=[n.value for n in ast.walk(static_source()) if isinstance(n,ast.Attribute) and n.attr=="replace"]
    assert all(isinstance(value,ast.Subscript) or
               isinstance(value,ast.Call) and isinstance(value.func,ast.Attribute) and value.func.attr=="isoformat"
               for value in replacements)


def test_contract_42_partial_marker_result_and_write_failure_preserved(toy_pair,monkeypatch):
    root,_,_,_=toy_pair
    path=root/c.MARKER_PATH;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b"partial")
    with pytest.raises(c.CalibrationError):c.consume_marker(root,{})
    assert path.read_bytes()==b"partial"
    target=root/"docs/isolated_partial.md"
    monkeypatch.setattr(os,"fsync",lambda fd:(_ for _ in ()).throw(OSError("synthetic fsync failure")))
    with pytest.raises(OSError):c.exclusive_write(target,b"evidence")
    assert target.read_bytes()==b"evidence"
    with pytest.raises(FileExistsError):c.exclusive_write(target,b"new")


@pytest.mark.parametrize("changed",[c.CSV_PATH,c.MANIFEST_PATH,c.MARKER_PATH])
def test_contract_42_changed_evidence_refuses_publication(toy_pair,changed):
    root,_,_,_=toy_pair
    marker_sha=c.consume_marker(root,{"state":"ATTEMPT_CONSUMED"})
    path=root/changed;path.write_bytes(path.read_bytes()+b"changed")
    before=path.read_bytes()
    with pytest.raises(c.CalibrationError):c.publish_result(root,"unpublished",marker_sha)
    assert path.read_bytes()==before and not (root/c.RESULT_PATH).exists()


def test_contract_42_exclusive_create_race_preserves_winner(tmp_path,monkeypatch):
    path=tmp_path/"isolated_marker"
    original=Path.open
    def raced(target,mode="r",*args,**kwargs):
        if target==path and mode=="xb":
            with original(target,"xb") as winner:
                winner.write(b"other-process evidence")
        return original(target,mode,*args,**kwargs)
    monkeypatch.setattr(Path,"open",raced)
    with pytest.raises(FileExistsError):c.exclusive_write(path,b"loser")
    assert path.read_bytes()==b"other-process evidence"


def test_contract_43_preflight_no_fit_transform_metrics_or_mutation(toy_pair,monkeypatch):
    root,_,_,_=toy_pair
    stub_execution(monkeypatch,root)
    for name in ("fit_calibrator","apply_calibration","transform_components","objective_and_gradient",
                 "calculate_metrics","baseline_gate","evaluate","consume_marker","publish_result"):
        monkeypatch.setattr(c,name,lambda *a,**kw:pytest.fail("Preflight performance/write forbidden"))
    monkeypatch.setattr(optimize,"minimize",lambda *a,**kw:pytest.fail("Preflight fit forbidden"))
    before={p.relative_to(root):p.read_bytes() for p in (root/c.CSV_PATH,root/c.MANIFEST_PATH)}
    result=c.preflight()
    assert result["status"]=="PREFLIGHT_PASS" and result["candidate_metrics"]=="NOT RUN"
    assert result["marker_created"] is False and result["result_created"] is False
    assert before=={p.relative_to(root):p.read_bytes() for p in (root/c.CSV_PATH,root/c.MANIFEST_PATH)}


def test_contract_43_import_help_and_flag_parser_safe(monkeypatch,capsys):
    for name in ("preflight","formal"):
        monkeypatch.setattr(c,name,lambda:pytest.fail("No execution during help"))
    with pytest.raises(SystemExit) as error:c.main(["--help"])
    assert error.value.code==0 and "--confirm-one-shot" in capsys.readouterr().out
    for args in (["--formal"],["--confirm-one-shot"],["--source","other"]):
        with pytest.raises(SystemExit):c.main(args)
    script=(
        "import sys\n"
        "def guard(event,args):\n"
        "    if event=='open' and ('/data/' in str(args[0]).replace('\\\\','/') or '/models/' in str(args[0]).replace('\\\\','/')):\n"
        "        raise RuntimeError('production read')\n"
        "sys.addaudithook(guard)\n"
        "import src.modeling.champion_a_calibration_evaluation\n"
        "assert not any(name in sys.modules for name in ('numpy','pandas','scipy','sklearn'))\n"
        "print('SAFE_IMPORT')\n"
    )
    result=subprocess.run([sys.executable,"-B","-c",script],cwd=REPOSITORY_ROOT,capture_output=True,text=True,check=True)
    assert result.stdout.strip()=="SAFE_IMPORT"
    help_result=subprocess.run([sys.executable,"-B","-m","src.modeling.champion_a_calibration_evaluation","--help"],
                               cwd=REPOSITORY_ROOT,capture_output=True,text=True,check=True)
    assert "--formal" in help_result.stdout and "COMPLETE" not in help_result.stdout


def test_contract_43_cli_dispatch_only_synthetic_stubs(monkeypatch,capsys):
    calls=[]
    monkeypatch.setattr(c,"preflight",lambda:calls.append("preflight") or {"status":"SYNTHETIC"})
    monkeypatch.setattr(c,"formal",lambda:calls.append("formal") or {"status":"SYNTHETIC"})
    assert c.main([])==0
    assert c.main(["--formal","--confirm-one-shot"])==0
    assert calls==["preflight","formal"]
    assert "SYNTHETIC" in capsys.readouterr().out


def test_contract_44_network_guard_and_no_network_import():
    with pytest.raises(pytest.fail.Exception):socket.create_connection(("example.invalid",443))
    assert not any(n and n.split(".")[0] in {"requests","urllib","httpx","socket"} for n in imported_names())


def test_contract_45_no_prediction_dependency_or_promotion(toy_rows,monkeypatch):
    assert not any(n and n.startswith("src.") for n in imported_names())
    monkeypatch.setattr(optimize,"minimize",lambda **kw:fake_result(kw["x0"]))
    outcome=c.evaluate(toy_rows)
    assert outcome["decision"] in (c.CLOSE_GATE,c.PROCEED_GATE)
    doc=c.build_result(outcome,{"synthetic":True})
    assert "separate prospective freeze" in doc and "No operational promotion" in doc
    assert "UNCHANGED" in doc and "NOT CREATED" in doc


def test_runtime_mismatch_lock_hash_and_static_code_gate(toy_pair,monkeypatch):
    root,_,_,_=toy_pair
    import importlib.metadata
    monkeypatch.setattr(importlib.metadata,"version",lambda key:"wrong")
    with pytest.raises(c.CalibrationError,match="runtime mismatch"):c.runtime_provenance(root)
    monkeypatch.setattr(importlib.metadata,"version",lambda key:c.VERSIONS[key])
    for path in c.REQUIREMENTS_HASHES:
        (root/path).write_bytes(b"synthetic wrong lock")
    with pytest.raises(c.CalibrationError,match="lock mismatch"):c.runtime_provenance(root)
    monkeypatch.setattr(c,"REQUIREMENTS_HASHES",{path:c.sha256((root/path).read_bytes()) for path in c.REQUIREMENTS_HASHES})
    assert c.runtime_provenance(root)["python"]=="3.12.14"
    # Exercise actual verify_code/AST whitelist on synthetic files and mocked git.
    source=(REPOSITORY_ROOT/c.MODULE_PATH).read_bytes()
    spec=(REPOSITORY_ROOT/c.SPEC_PATH).read_bytes()
    for path,buffer in ((c.MODULE_PATH,source),(c.SPEC_PATH,spec)):
        destination=root/path;destination.parent.mkdir(parents=True,exist_ok=True);destination.write_bytes(buffer)
    def git(target,*args):
        if args[0]=="show":return spec if args[1].startswith(c.SPEC_COMMIT+":") else source
        return b""
    monkeypatch.setattr(c,"git",git)
    assert c.verify_code(root,"a"*40)==c.sha256(source)


def test_all_45_contracts_have_visible_behavior_mapping():
    tree=ast.parse(Path(__file__).read_text(encoding="utf-8"))
    covered={int(n.name.split("_")[2]) for n in tree.body if isinstance(n,ast.FunctionDef) and n.name.startswith("test_contract_")}
    assert covered==set(range(1,46))
