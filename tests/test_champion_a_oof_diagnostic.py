"""Synthetic-only coverage of freeze §19, items 01--32 (named below).

No historical CSVs, real five-fold fit, production artifacts, or formal marker IO.
Every test installs production-data/network guards. Orchestration tests replace
load/fit/reference functions with synthetic stubs; actual fits use tiny toy data.
"""

import ast
import builtins
from contextlib import nullcontext
import copy
import importlib
import io
import json
from pathlib import Path
import socket
import subprocess
import sys
import warnings

import numpy as np
import pandas as pd
from pandas.testing import assert_frame_equal
import pytest
from sklearn.exceptions import ConvergenceWarning
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

from src.modeling import champion_a_oof_diagnostic as d


@pytest.fixture(autouse=True)
def forbidden_io_guard(monkeypatch):
    """Items 02/03/24/28/29: reject any production data/model IO and marker access."""
    root = str(d.ROOT).replace("\\", "/").casefold()
    def guarded(function):
        def call(file, *args, **kwargs):
            name = str(file).replace("\\", "/").casefold()
            if "formal_benchmark_attempt.json" in name:
                pytest.fail("Formal marker IO attempted")
            if name.startswith(root + "/data/") or name.startswith(root + "/models/"):
                pytest.fail(f"Production data IO attempted: {file}")
            return function(file, *args, **kwargs)
        return call
    monkeypatch.setattr(builtins, "open", guarded(builtins.open))
    monkeypatch.setattr(io, "open", guarded(io.open))
    for operation in ("stat", "unlink", "mkdir", "rename", "replace"):
        monkeypatch.setattr(Path, operation, guarded(getattr(Path, operation)))
    def network(*args, **kwargs):
        pytest.fail("Network attempted")
    monkeypatch.setattr(socket, "create_connection", network)
    monkeypatch.setattr(socket.socket, "connect", network)


def source_frame(year=2020, n=9):
    results = [i % 3 for i in range(n)]
    return pd.DataFrame({
        "match_id": [f"{year}-{i:04}" for i in range(n)], "season": [year]*n,
        "round": [i+1 for i in range(n)], "match_date": pd.date_range(f"{year}-02-01", periods=n),
        "home_team": ["Home"]*n, "away_team": ["Away"]*n, "stadium": ["Toy"]*n,
        "home_team_id": ["team_0001"]*n, "away_team_id": ["team_0002"]*n,
        "home_score": [1 if r == 2 else 0 for r in results],
        "away_score": [1 if r == 0 else 0 for r in results], "result": results,
        "elo_diff": np.linspace(-100, 100, n),
    })


def row_frame(year=2020, n=9):
    source = pd.concat([source_frame(2019, 1), source_frame(year, n)], ignore_index=True)
    metadata = d.add_metadata(source).loc[lambda f: f.season.eq(year)].copy()
    return d.make_rows(metadata, np.tile([0.3, 0.3, 0.4], (n, 1)))


def toy_runtime():
    return {"python": "3.12.14", "platform": "Windows-synthetic", "numpy": "2.5.3", "pandas": "3.0.5",
            "scikit-learn": "1.9.1", "scipy": "1.18.1", "requirements_sha256": d.CODE_HASHES["requirements.txt"],
            "lock_sha256": d.CODE_HASHES["requirements-lock.txt"]}


def synthetic_pair(monkeypatch):
    """Local 15 rows, no fit: substitute reference literals/counts for IO tests only."""
    rows = pd.concat([row_frame(y, 3) for y in d.FOLDS], ignore_index=True)
    counts = {y: (3*(y-2015), 3) for y in d.FOLDS}
    references = {y: d.calculate_metrics(f.result, f[["p_away", "p_draw", "p_home"]].to_numpy())
                  for y, f in rows.groupby("validation_year")}
    references["pooled"] = d.calculate_metrics(rows.result, rows[["p_away", "p_draw", "p_home"]].to_numpy())
    monkeypatch.setattr(d, "FOLD_COUNTS", counts)
    monkeypatch.setattr(d, "OOF_ROWS", len(rows))
    monkeypatch.setattr(d, "REFERENCES", references)
    metrics = d.gate_rows(rows)
    folds = [{"validation_year": y, "training_seasons": list(range(2015, y)),
              "training_rows": counts[y][0], "validation_rows": 3, "train_ids_sha256": "a"*64,
              "validation_ids_sha256": d.id_hash(rows.loc[rows.validation_year.eq(y), "match_id"])} for y in d.FOLDS]
    data = d.serialize_rows(rows)
    manifest = d.build_manifest(rows, data, metrics, folds,
                                authorization={"reviewed_implementation_commit": "c"*40, "task_reference": "synthetic-task"},
                                commit="c"*40, runtime=toy_runtime(), generator_sha="b"*64,
                                generated_at="2026-10-05T00:00:00Z")
    return rows, data, manifest


def test_contract_01_constants_folds_hashes_schema_match_freeze():
    # Only docs are read here; never historical sources. Static reference comparison.
    spec = (d.ROOT / d.SPEC_PATH).read_text(encoding="utf-8")
    assert d.FOLDS == (2020, 2021, 2022, 2023, 2024)
    assert list(d.FOLD_COUNTS.values()) == [(1530,306),(1836,380),(2216,306),(2522,306),(2828,380)]
    assert sum(c[1] for c in d.FOLD_COUNTS.values()) == 1678
    assert sum(d.SEASON_COUNTS.values()) == 3208
    assert d.INITIAL_ELO == 1500 and d.K == 30 and d.HOME_ADVANTAGE == 175
    assert d.CLASS_ORDER == (0,1,2) and d.FEATURES == ("elo_diff",)
    assert d.RTOL == 0 and d.ATOL == 1e-12
    assert len(d.COLUMNS) == len(set(d.COLUMNS)) == 34
    for name, sha in {**d.INPUT_HASHES, d.TEAM_MASTER_PATH:d.TEAM_MASTER_SHA, **d.CODE_HASHES}.items():
        assert name in spec and sha in spec
    for r in d.REFERENCES.values():
        for v in r.values():
            assert str(v) in spec
    schema = spec.split("```text\nvalidation_year\n", 1)[1].split("\n```", 1)[0].splitlines()
    assert d.COLUMNS == tuple(["validation_year", *schema])
    assert d.sha256((d.ROOT / d.SPEC_PATH).read_bytes()) == d.SPEC_SHA


def test_contract_02_03_24_28_29_static_dependency_firewall():
    tree = ast.parse((d.ROOT / d.MODULE_PATH).read_text(encoding="utf-8"))
    modules = [n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
    assert not any(m and any(x in m for x in ("architecture_evaluation", "prediction", "artifact", "requests", "urllib")) for m in modules)
    assert list(d.INPUT_HASHES) == [f"data/processed/jleague/{y}_matches_probe.csv" for y in range(2015,2025)]


@pytest.mark.parametrize("year", [2025,2026,2027])
def test_contract_02_03_forbidden_seasons_rejected_in_memory(year):
    with pytest.raises(d.DiagnosticError, match="Forbidden source season"):
        d.validate_source(source_frame(year), exact_population=False)


def test_contract_02_03_24_28_29_explicit_loader_only_tmp_paths(monkeypatch, tmp_path):
    from src.collect import matches, teams
    opened = []
    class Master:
        aliases = [type("A", (), {"team_id": "team_0001"})(), type("A", (), {"team_id": "team_0002"})()]
        def add_team_ids(self, frame):
            return frame
    def load(path):
        opened.append(path.relative_to(tmp_path).as_posix())
        return source_frame(int(path.name[:4]), 3)
    monkeypatch.setattr(matches, "load_matches", load)
    monkeypatch.setattr(teams, "load_team_master", lambda path: Master())
    monkeypatch.setattr(d, "SOURCE_ROWS", 30)
    monkeypatch.setattr(d, "SEASON_COUNTS", {y:3 for y in range(2015,2025)})
    actual = d.load_source(tmp_path)
    assert len(actual) == 30 and opened == list(d.INPUT_HASHES)


def test_contract_04_05_06_07_30_training_only_deterministic_synthetic_fit(monkeypatch):
    train = source_frame(2019, 18)
    valid = source_frame(2020, 3).assign(elo_diff=[10000.,20000.,30000.])
    original = train.copy(deep=True)
    pipelines = []
    original_builder = d.build_pipeline
    def builder():
        model = original_builder()
        pipelines.append(model)
        return model
    monkeypatch.setattr(d, "build_pipeline", builder)
    seen = []
    fit = LogisticRegression.fit
    def spy(self, x, y, *args, **kwargs):
        seen.append((np.asarray(x).copy(), np.asarray(y).copy(), args, kwargs))
        return fit(self, x, y, *args, **kwargs)
    monkeypatch.setattr(LogisticRegression, "fit", spy)
    first = d.fit_fold(train, valid)
    second = d.fit_fold(train, valid)
    assert np.array_equal(first, second)
    assert pipelines[0] is not pipelines[1]
    assert pipelines[0].named_steps["scaler"] is not pipelines[1].named_steps["scaler"]
    np.testing.assert_array_equal(pipelines[0].named_steps["scaler"].mean_, [train.elo_diff.mean()])
    np.testing.assert_allclose(pipelines[0].named_steps["scaler"].var_, [train.elo_diff.var(ddof=0)])
    for x, y, args, kwargs in seen:
        assert x.shape == (18, 1) and np.max(np.abs(x)) < 2
        np.testing.assert_array_equal(y, train.result)
        assert not args and not kwargs
    assert_frame_equal(train, original)
    params = pipelines[0].named_steps["logistic"].get_params()
    assert {k:params[k] for k in ("C","solver","max_iter","random_state")} == {"C":1.,"solver":"lbfgs","max_iter":1000,"random_state":0}
    assert params["class_weight"] is None and not params["warm_start"]
    assert params["tol"] == 1e-4 and params["fit_intercept"]
    assert pipelines[0].named_steps["logistic"].classes_.tolist() == [0,1,2]
    assert list(pipelines[0].named_steps) == ["scaler", "logistic"]


def test_contract_04_mismatched_class_order_rejects_before_predict(monkeypatch):
    class Model:
        named_steps = {"logistic": type("L", (), {"classes_": np.array([2,1,0])})()}
        def fit(self, x, y): pass
        def predict_proba(self, x): pytest.fail("predict after class failure")
    monkeypatch.setattr(d, "build_pipeline", Model)
    with pytest.raises(d.DiagnosticError, match="Class order"):
        d.fit_fold(source_frame(), source_frame())


def test_contract_08_same_date_read_before_apply_no_target_or_peer_leak(monkeypatch):
    from src.modeling import player_workload_evaluation as existing
    events = []
    base = existing.EloRatings
    class Spy(base):
        def pre_match(self, h, a):
            events.append(("read",h,a))
            return super().pre_match(h,a)
        def update(self,h,a,r):
            events.append(("update",h,a))
            return super().update(h,a,r)
    monkeypatch.setattr(existing, "EloRatings", Spy)
    source = source_frame(2020, 3)
    source.loc[1, "match_date"] = source.loc[0, "match_date"]
    source.loc[1, ["home_team_id","away_team_id"]] = ["team_0003","team_0004"]
    output = d.replay_elo(source)
    assert events[:3] == [("read","team_0001","team_0002"),("read","team_0003","team_0004"),("update","team_0001","team_0002")]
    assert output.elo_diff.iloc[:2].tolist() == [0.,0.]
    changed = source.copy()
    changed.loc[:1, "result"] = [2,2]
    compare = d.replay_elo(changed)
    np.testing.assert_array_equal(compare.elo_diff.iloc[:2], output.elo_diff.iloc[:2])
    assert compare.elo_diff.iloc[2] != output.elo_diff.iloc[2]


def test_contract_08_duplicate_team_same_date_rejected():
    source = source_frame(2020, 2)
    source.loc[1,"match_date"] = source.loc[0,"match_date"]
    with pytest.raises(ValueError, match="same date"):
        d.replay_elo(source)


def test_contract_08_cross_season_absent_club_new_club_and_raw_elo():
    from src.features.elo import expected_score
    f = source_frame(2019, 3)
    f.loc[1,"season"] = 2020
    f.loc[1,"match_date"] = pd.Timestamp("2020-02-01")
    f.loc[1,["home_team_id","away_team_id"]] = ["team_0003","team_0004"]
    f.loc[2,"season"] = 2021
    f.loc[2,"match_date"] = pd.Timestamp("2021-02-01")
    actual = d.replay_elo(f)
    assert actual.elo_diff.iloc[0] == 0 and actual.elo_diff.iloc[1] == 0
    delta = 30*(f.result.iloc[0]/2-expected_score(1500+175,1500))
    assert actual.elo_diff.iloc[2] == (1500+delta)-(1500-delta)


def test_contract_09_schema_ids_metadata_nonmutation():
    source = source_frame()
    before = source.copy(deep=True)
    rows = d.make_rows(d.add_metadata(source), np.tile([.3,.3,.4],(len(source),1)))
    assert tuple(rows.columns) == d.COLUMNS
    assert rows.match_id.tolist() == source.match_id.tolist()
    assert rows.home_team.tolist() == source.home_team.tolist()
    assert rows.match_date.tolist() == source.match_date.dt.strftime("%Y-%m-%d").tolist()
    d.assert_target_identity(rows,source)
    assert_frame_equal(source,before)


@pytest.mark.parametrize("p", [[[.2,.3,.4]], [[-0.1,.4,.7]], [[0,0,1.1]], [[np.nan,.5,.5]], [[np.inf,0,0]], [[.5,.5]], [.2,.3,.5]])
def test_contract_10_invalid_probabilities(p):
    with pytest.raises(d.DiagnosticError): d.validate_probabilities(p)


def test_contract_10_sum_tolerance_no_renormalization():
    p = np.array([[.2,.3,.5+0.5e-12]])
    before = p.copy()
    d.validate_probabilities(p,1)
    np.testing.assert_array_equal(p,before)
    with pytest.raises(d.DiagnosticError): d.validate_probabilities([[.2,.3,.5+2e-12]])
    with pytest.raises(d.DiagnosticError): d.validate_probabilities(p,2)


def test_contract_11_12_13_14_derived_clipping_true_lookup_brier_ties():
    p = np.array([[0.,0.,1.],[1.,0.,0.],[.5,.5,0.],[.2,.3,.5]])
    original = p.copy()
    result = d.derived_values([0,0,1,2],p)
    np.testing.assert_array_equal(result["p_true"],[0,1,.5,.5])
    np.testing.assert_array_equal(result["predicted_class"],[2,0,0,2])
    np.testing.assert_array_equal(result["max_p"],[1,1,.5,.5])
    np.testing.assert_allclose(result["nll"],-np.log(np.clip([0,1,.5,.5],np.finfo(float).eps,1-np.finfo(float).eps)))
    np.testing.assert_allclose(result["brier"],[2,0,.5,.38])
    np.testing.assert_array_equal(p,original)
    metrics=d.calculate_metrics([0,0,1,2],p)
    assert metrics["log_loss"] == result["nll"].mean()
    with pytest.raises(d.DiagnosticError): d.derived_values([3],[[.2,.3,.5]])


@pytest.mark.parametrize("edges", [d.PROBABILITY_EDGES,d.MAX_P_EDGES,d.ABS_ELO_EDGES,d.SIGNED_ELO_EDGES])
def test_contract_15_every_fixed_bin_boundary(edges):
    for i, edge in enumerate(edges[:-1]):
        if np.isfinite(edge):
            assert d.bin_index(edge,edges)==i
            if i>0: assert d.bin_index(np.nextafter(edge,-np.inf),edges)==i-1
    if np.isfinite(edges[-1]): assert d.bin_index(edges[-1],edges)==len(edges)-2
    with pytest.raises(d.DiagnosticError): d.bin_index(np.nan,edges)


@pytest.mark.parametrize("round_number,phase", [(1,"opening"),(5,"opening"),(6,"middle"),(29,"middle"),(30,"closing"),(38,"closing")])
def test_contract_16_phase_boundaries(round_number,phase):
    assert d.season_phase(round_number)==phase


def test_contract_17_appearance_five_six_mixed_flags():
    f=source_frame(n=6)
    f.loc[5,"away_team_id"]="team_0003"
    metadata=d.add_metadata(f)
    assert metadata.home_season_appearance.tolist()==[1,2,3,4,5,6]
    assert metadata.home_first5.tolist()==[1,1,1,1,1,0]
    last=metadata.iloc[5]
    assert (last.home_first5,last.away_first5,last.any_team_first5,last.both_team_first5)==(0,1,1,0)


def test_contract_18_membership_returning_established_scoped_left_edge():
    f=pd.concat([source_frame(y,1) for y in (2015,2016,2017,2018)],ignore_index=True)
    f.loc[1,"home_team_id"]="team_0003"
    f.loc[3,"home_team_id"]="team_0004"
    m=d.add_metadata(f)
    assert m.home_status.tolist()==["FIRST_TIME_IN_SCOPE","FIRST_TIME_IN_SCOPE","RETURNING","FIRST_TIME_IN_SCOPE"]
    assert m.away_status.iloc[1]=="ESTABLISHED"
    assert m.returning_involved.iloc[2]==1 and m.promoted_involved.iloc[2]==1
    f.loc[3,"home_team_id"]="team_0001"
    m=d.add_metadata(f)
    assert m.established_only.iloc[3]==1


def test_contract_19_favorite_independence_tie_exact_005():
    flags=d.favorite_flags([[.4,.2,.4],[0,.95,.05],[.3,.38,.32],[.6,.2,.2]])
    assert flags["home_favorite"].tolist()==[0,1,1,0]
    assert flags["away_favorite"].tolist()==[0,0,0,1]
    assert flags["near_even"].tolist()==[1,0,1,0]
    views=d.favorite_diagnostics(row_frame(n=3))["2020"]
    assert len(views)==9
    assert sum(v["n"] for k,v in views.items() if k.startswith("home_favorite"))==3


def test_contract_20_club_double_attribution_composition_share_quantile():
    rows=row_frame(n=3)
    clubs=d.club_diagnostics(rows)
    assert clubs["attributed_n"]==6
    assert clubs["attributed_nll"]==pytest.approx(2*rows.nll.sum())
    assert sum(c["pooled_attributed_nll_share"] for c in clubs["cells"])==1
    assert [c["team_id"] for c in clubs["cells"]]==["team_0001","team_0002"]
    assert all(c["class_counts"]==[1,1,1] for c in clubs["cells"])
    assert clubs["concentration"]["pooled"]["top5_share"]==1
    assert clubs["concentration"]["pooled"]["iqr"]==0


@pytest.mark.parametrize("n,label", [(0,"EMPTY"),(1,"SPARSE"),(29,"SPARSE"),(30,"NONSPARSE")])
def test_contract_21_sparse_rules(n,label):
    assert d.sparse_status(n)==label
    rows=row_frame(n=max(3,n)).iloc[:n]
    cell=d.reliability_cell(rows,1)
    assert cell["n"]==n and cell["status"]==label
    if not n: assert cell["bias"] is None and cell["mean_nll"] is None and cell["total_nll"]==0


@pytest.mark.parametrize("key", ["accuracy","log_loss","brier"])
def test_contract_22_metric_just_inside_outside_tolerance(key):
    expected={"n":1,"accuracy":0.,"log_loss":0.,"brier":0.}
    actual=dict(expected); actual[key]=np.nextafter(d.ATOL,0)
    d.assert_reference(actual,expected)
    actual[key]=np.nextafter(d.ATOL,np.inf)
    with pytest.raises(d.DiagnosticError,match="Reference mismatch"): d.assert_reference(actual,expected)
    actual=dict(expected,n=2)
    with pytest.raises(d.DiagnosticError,match="count"): d.assert_reference(actual,expected)


def test_contract_22_reference_failure_stops_before_diagnostics(monkeypatch):
    monkeypatch.setattr(d,"gate_rows",lambda rows: (_ for _ in ()).throw(d.DiagnosticError("reference")))
    monkeypatch.setattr(d,"calibration_diagnostics",lambda rows: pytest.fail("diagnostics after failure"))
    with pytest.raises(d.DiagnosticError): d.diagnose(row_frame())


def test_contract_23_pooled_row_weighting_not_mean_of_fold_means():
    a=d.calculate_metrics([0],[[.9,.05,.05]])
    b=d.calculate_metrics([0,0,0],[[.2,.3,.5]]*3)
    pooled=d.calculate_metrics([0]*4,[[.9,.05,.05]]+[[.2,.3,.5]]*3)
    assert pooled["log_loss"]==pytest.approx((a["log_loss"]+3*b["log_loss"])/4)
    assert pooled["log_loss"]!=pytest.approx((a["log_loss"]+b["log_loss"])/2)


def test_contract_09_23_reordered_ids_metadata_or_derived_rejected():
    source=source_frame(n=3); rows=d.make_rows(d.add_metadata(source),np.tile([.3,.3,.4],(3,1)))
    with pytest.raises(d.DiagnosticError): d.validate_rows(rows.iloc[::-1])
    for c,value in [("round",9),("home_team","Other"),("match_date","2020-09-09"),("home_team_id","other")]:
        changed=rows.copy(); changed.loc[0,c]=value
        with pytest.raises(d.DiagnosticError): d.assert_target_identity(changed,source)
    changed=rows.copy(); changed.loc[0,"nll"]+=1e-8
    with pytest.raises(d.DiagnosticError): d.validate_rows(changed)


@pytest.mark.parametrize("existing", [(d.CSV_PATH,),(d.MANIFEST_PATH,),(d.CSV_PATH,d.MANIFEST_PATH)])
def test_contract_25_27_existing_partial_or_pair_refused(tmp_path,existing):
    for p in existing:
        target=tmp_path/p; target.parent.mkdir(parents=True,exist_ok=True); target.write_bytes(b"evidence")
    with pytest.raises(d.DiagnosticError,match="REFUSE"): d.refuse_existing(tmp_path)
    assert all((tmp_path/p).read_bytes()==b"evidence" for p in existing)


def test_contract_25_concurrent_named_mutex_no_persistent_files(tmp_path):
    with d.production_lock(tmp_path):
        with pytest.raises(d.DiagnosticError,match="Concurrent"):
            with d.production_lock(tmp_path): pytest.fail("second lock acquired")
        # A separate interpreter must also refuse, without reading any data or fitting.
        code = ("from pathlib import Path; import sys; "
                "from src.modeling.champion_a_oof_diagnostic import production_lock, DiagnosticError\n"
                "try:\n with production_lock(Path(sys.argv[1])): sys.exit(9)\n"
                "except DiagnosticError: sys.exit(7)\n")
        result = subprocess.run([sys.executable, "-c", code, str(tmp_path)], cwd=d.ROOT,
                                capture_output=True, text=True, check=False)
        assert result.returncode == 7, result.stderr
    with d.production_lock(tmp_path): pass
    assert list(tmp_path.iterdir())==[]


def test_contract_26_serialization_manifest_hash_roundtrip(monkeypatch):
    rows,data,manifest=synthetic_pair(monkeypatch)
    assert not data.startswith(b"\xef\xbb\xbf") and b"\r\n" not in data
    assert data.splitlines()[0].decode()==",".join(d.COLUMNS)
    assert set(manifest)==set(d.MANIFEST_KEYS)
    assert manifest["csv"]["sha256"]==d.sha256(data)
    assert manifest["purpose"]==d.PURPOSE
    assert manifest["freeze_spec"]["sha256"]==d.SPEC_SHA
    assert manifest["csv"]["ordered_ids_sha256"]==d.id_hash(rows.match_id)
    for mutate in (
        lambda m:m.update(opaque=True),
        lambda m:m["csv"].update(sha256="a"*64),
        lambda m:m["inputs"][0].update(sha256="a"*64),
        lambda m:m["runtime"].update(numpy="other"),
        lambda m:m["gates"].update(references="FAIL"),
        lambda m:m["observed_metrics"]["pooled"].update(log_loss=9),
    ):
        broken=copy.deepcopy(manifest); mutate(broken)
        with pytest.raises(d.DiagnosticError): d.validate_manifest(broken,data,rows)


def test_contract_26_float_roundtrip_preserves_identifiers(monkeypatch):
    rows,data,_=synthetic_pair(monkeypatch)
    rows["match_id"]=pd.Series([f"{i:05}" for i in range(len(rows))],dtype="string")
    rows["home_team"]="NA"  # This source name must not be parsed as a missing value.
    rows=rows.astype(d.DTYPES)
    data=d.serialize_rows(rows)
    parsed=pd.read_csv(io.BytesIO(data),dtype={c:d.DTYPES[c] for c in d.COLUMNS if c not in d.FLOAT_COLUMNS},float_precision="round_trip",keep_default_na=False).astype(d.DTYPES)
    d.validate_rows(parsed,rows)
    for c in d.FLOAT_COLUMNS: np.testing.assert_array_equal(parsed[c],rows[c])
    assert_frame_equal(d.parse_rows(data),rows)
    for broken in (b"\xef\xbb\xbf"+data,data.replace(b"\n",b"\r\n"),data.replace(b"validation_year",b"other_header",1)):
        with pytest.raises(d.DiagnosticError):d.parse_rows(broken)


def test_contract_25_27_exclusive_publication_tmp_only_and_replay_refused(monkeypatch,tmp_path):
    rows,data,manifest=synthetic_pair(monkeypatch)
    monkeypatch.setattr(d,"verify_hashes",lambda root: None)
    d.publish_pair(tmp_path,rows,data,manifest)
    assert (tmp_path/d.CSV_PATH).read_bytes()==data
    assert json.loads((tmp_path/d.MANIFEST_PATH).read_bytes())==manifest
    with pytest.raises(d.DiagnosticError): d.publish_pair(tmp_path,rows,data,manifest)


def test_contract_27_publication_failure_retains_partial_no_cleanup(monkeypatch,tmp_path):
    rows,data,manifest=synthetic_pair(monkeypatch)
    monkeypatch.setattr(d,"verify_hashes",lambda root:None)
    original=Path.open
    def failure(path,*args,**kwargs):
        if path==tmp_path/d.MANIFEST_PATH and args and args[0]=="xb": raise OSError("interruption")
        return original(path,*args,**kwargs)
    monkeypatch.setattr(Path,"open",failure)
    with pytest.raises(OSError): d.publish_pair(tmp_path,rows,data,manifest)
    assert (tmp_path/d.CSV_PATH).read_bytes()==data
    assert not (tmp_path/d.MANIFEST_PATH).exists()
    with pytest.raises(d.DiagnosticError): d.publish_pair(tmp_path,rows,data,manifest)


def stub_generation(monkeypatch,tmp_path):
    monkeypatch.setattr(d,"ROOT",tmp_path)
    monkeypatch.setattr(d,"production_lock",lambda root:nullcontext())
    monkeypatch.setattr(d,"execution_provenance",lambda root:("c"*40,{"reviewed_implementation_commit":"c"*40,"task_reference":"synthetic"}))
    monkeypatch.setattr(d,"runtime_provenance",toy_runtime)
    monkeypatch.setattr(d,"verify_hashes",lambda root:None)
    monkeypatch.setattr(d,"load_source",lambda root:source_frame())


def test_contract_22_24_27_failure_no_fit_retry_no_publication(monkeypatch,tmp_path):
    stub_generation(monkeypatch,tmp_path)
    calls=[]
    def fail(source):
        calls.append("attempt")
        raise d.DiagnosticError("synthetic fit failure")
    monkeypatch.setattr(d,"reconstruct",fail)
    monkeypatch.setattr(d,"publish_pair",lambda *a:pytest.fail("publication after failure"))
    with pytest.raises(d.DiagnosticError,match="failure"): d.run_generation()
    with pytest.raises(d.DiagnosticError,match="Attempt already"): d.run_generation()
    assert calls==["attempt"] and list(tmp_path.iterdir())==[]


def test_contract_25_concurrent_lock_refuses_before_input_or_fit(monkeypatch,tmp_path):
    monkeypatch.setattr(d,"ROOT",tmp_path)
    monkeypatch.setattr(d,"load_source",lambda *a:pytest.fail("source read under held lock"))
    monkeypatch.setattr(d,"reconstruct",lambda *a:pytest.fail("fit under held lock"))
    with d.production_lock(tmp_path):
        with pytest.raises(d.DiagnosticError,match="Concurrent"): d.run_generation()


def test_contract_27_preexisting_refuses_before_source_or_fit(monkeypatch,tmp_path):
    stub_generation(monkeypatch,tmp_path)
    p=tmp_path/d.CSV_PATH; p.parent.mkdir(parents=True); p.write_bytes(b"immutable")
    monkeypatch.setattr(d,"load_source",lambda *a:pytest.fail("source read after prior output"))
    with pytest.raises(d.DiagnosticError): d.run_generation()
    assert p.read_bytes()==b"immutable"


def test_contract_26_27_hash_failure_stops_before_load(monkeypatch,tmp_path):
    stub_generation(monkeypatch,tmp_path)
    monkeypatch.setattr(d,"verify_hashes",lambda *a: (_ for _ in ()).throw(d.DiagnosticError("hash")))
    monkeypatch.setattr(d,"load_source",lambda *a:pytest.fail("loaded after hash mismatch"))
    with pytest.raises(d.DiagnosticError,match="hash"): d.run_generation()


def test_contract_26_input_hash_exact_paths_tmp_only(monkeypatch,tmp_path):
    path="synthetic.csv"; payload=b"not historical data"
    (tmp_path/path).write_bytes(payload)
    monkeypatch.setattr(d,"INPUT_HASHES",{path:d.sha256(payload)})
    monkeypatch.setattr(d,"CODE_HASHES",{})
    monkeypatch.setattr(d,"TEAM_MASTER_PATH",path); monkeypatch.setattr(d,"TEAM_MASTER_SHA",d.sha256(payload))
    monkeypatch.setattr(d,"SPEC_PATH",path); monkeypatch.setattr(d,"SPEC_SHA",d.sha256(payload))
    d.verify_hashes(tmp_path)
    (tmp_path/path).write_bytes(b"changed")
    with pytest.raises(d.DiagnosticError): d.verify_hashes(tmp_path)


def test_contract_01_06_07_22_23_synthetic_five_fold_orchestration(monkeypatch):
    # 30 fabricated matches, stub predictions, zero actual five-fold historical fit.
    source=pd.concat([source_frame(y,3) for y in range(2015,2025)],ignore_index=True)
    counts={y:(3*(y-2015),3) for y in d.FOLDS}
    probabilities=np.tile([.3,.3,.4],(3,1))
    refs={y:d.calculate_metrics(source.loc[source.season.eq(y),"result"],probabilities) for y in d.FOLDS}
    refs["pooled"]=d.calculate_metrics(source.loc[source.season.isin(d.FOLDS),"result"],np.tile([.3,.3,.4],(15,1)))
    monkeypatch.setattr(d,"FOLD_COUNTS",counts)
    monkeypatch.setattr(d,"REFERENCES",refs)
    monkeypatch.setattr(d,"OOF_ROWS",15)
    seen=[]
    def predict(train,valid):
        year=int(valid.season.iloc[0]); seen.append(year)
        assert train.season.min()==2015 and train.season.max()==year-1
        assert len(train)==counts[year][0] and len(valid)==3
        assert set(train.match_id).isdisjoint(valid.match_id)
        return probabilities.copy()
    monkeypatch.setattr(d,"fit_fold",predict)
    before=source.copy(deep=True)
    rows,metrics,folds=d.reconstruct(source)
    assert seen==list(d.FOLDS) and len(rows)==15
    assert rows.match_id.tolist()==source.loc[source.season.isin(d.FOLDS),"match_id"].tolist()
    assert metrics["pooled"]==refs["pooled"]
    assert len(folds)==5 and all(f["train_ids_sha256"]==d.id_hash(source.loc[source.season.lt(f["validation_year"]),"match_id"]) for f in folds)
    assert_frame_equal(source,before)


def evidence(calibration=False,transition=False):
    cal={}; trans={}
    for y in d.FOLDS:
        cal[str(y)]={}
        for c in map(str,d.CLASS_ORDER):
            cell={"n":60,"bias":.01 if calibration and c=="1" else 0.}
            cal[str(y)][c]={"overall":dict(cell),"nonsparse":dict(cell),"core":dict(cell),
                            "bins":[dict(cell) for _ in range(10)],
                            "localization":{"1":{"share":.2},"-1":{"share":.2}}}
        trans[str(y)]={}
        for name in ("phase:opening","phase:middle","any_first5","neither_first5",
                     "established_only:phase:opening","established_only:phase:middle",
                     "established_only:first5:1","established_only:first5:0"):
            high=transition and name in ("phase:opening","any_first5","established_only:phase:opening","established_only:first5:1")
            trans[str(y)][name]={"n":60,"log_loss":1.1 if high else 1.,"brier":.7 if high else .6}
    return cal,trans


def test_contract_31_gate_a_priority_b_only_if_a_fails_and_fallback():
    assert d.decide(*evidence(True,True))==d.CALIBRATION_GATE
    assert d.decide(*evidence(False,True))==d.TRANSITION_GATE
    assert d.decide(*evidence(False,False))==d.INCONCLUSIVE_GATE


@pytest.mark.parametrize("passing_years,passes", [(3,False),(4,True),(5,True)])
def test_contract_31_class_four_of_five(passing_years,passes):
    cal,trans=evidence(True)
    for y in d.FOLDS[passing_years:]:cal[str(y)]["1"]["overall"]["bias"]=-.01
    assert (d.decide(cal,trans)==d.CALIBRATION_GATE)==passes


@pytest.mark.parametrize("passing_years,passes", [(2,False),(3,True)])
def test_contract_31_same_bin_three_of_five(passing_years,passes):
    cal,trans=evidence(True)
    for i,y in enumerate(d.FOLDS):
        for cell in cal[str(y)]["1"]["bins"]:cell["bias"]=0
        if i<passing_years:cal[str(y)]["1"]["bins"][2]["bias"]=.01
    assert (d.decide(cal,trans)==d.CALIBRATION_GATE)==passes


def test_contract_31_bins_cannot_rotate_across_years():
    cal,trans=evidence(True)
    for i,y in enumerate(d.FOLDS):
        for cell in cal[str(y)]["1"]["bins"]:cell["bias"]=0
        cal[str(y)]["1"]["bins"][i]["bias"]=.01
    assert d.decide(cal,trans)==d.INCONCLUSIVE_GATE


def test_contract_31_class_and_sign_cannot_rotate():
    cal,trans=evidence(True)
    for i,y in enumerate(d.FOLDS):
        cal[str(y)]["1"]["overall"]["bias"] = .01 if i<3 else -.01
        cal[str(y)]["0"]["overall"]["bias"] = .01 if i>=3 else 0
    assert d.decide(cal,trans)==d.INCONCLUSIVE_GATE


@pytest.mark.parametrize("field,n,passes", [("bins",29,False),("bins",30,True),("core",29,False),("core",30,True),("nonsparse",29,False)])
def test_contract_31_sparse_rejection_core_and_nonsparse(field,n,passes):
    cal,trans=evidence(True)
    for y in d.FOLDS:
        part=cal[str(y)]["1"][field]
        for cell in part if isinstance(part,list) else [part]:cell["n"]=n
    assert (d.decide(cal,trans)==d.CALIBRATION_GATE)==passes


@pytest.mark.parametrize("share,passes", [(np.nextafter(.8,0),True),(.8,False),(np.nextafter(.8,1),False),(None,False)])
def test_contract_31_localization_exact_080(share,passes):
    cal,trans=evidence(True)
    for y in d.FOLDS:cal[str(y)]["1"]["localization"]["1"]["share"]=share
    assert (d.decide(cal,trans)==d.CALIBRATION_GATE)==passes


def test_contract_31_localization_mass_formula_zero_denominator():
    rows=row_frame(n=3)
    rows["promoted_involved"]=0; rows["any_team_first5"]=[1,0,0]
    actual=d.localization_mass(rows,1,1)
    # Only the true Draw row has positive residual mass; it is outside narrow T.
    assert actual=={"share":0.,"status":"NOT_CONCENTRATED"}
    rows["p_draw"]=1; rows["result"]=1
    assert d.localization_mass(rows,1,1)["share"] is None


def test_contract_31_negative_sign_and_joint_core_localization_recurrence():
    cal,trans=evidence(True)
    for y in d.FOLDS:
        e=cal[str(y)]["1"]
        for cell in [e["overall"],e["nonsparse"],e["core"],*e["bins"]]:cell["bias"]=-.01
    assert d.decide(cal,trans)==d.CALIBRATION_GATE
    for i,y in enumerate(d.FOLDS):
        e=cal[str(y)]["1"]
        if i>=3:e["core"]["bias"]=0
        if i<2:e["localization"]["-1"]["share"]=.8
    # Three core years and three nonlocalized years, but only one joint year.
    assert d.decide(cal,trans)==d.INCONCLUSIVE_GATE


def test_contract_31_nonsparse_bias_needs_four_not_three_years():
    cal,trans=evidence(True)
    for y in d.FOLDS[3:]:cal[str(y)]["1"]["nonsparse"]["bias"]=0
    assert d.decide(cal,trans)==d.INCONCLUSIVE_GATE


def test_contract_26_diagnostic_contract_has_exact_fixed_views():
    frame=row_frame()
    assert d.diagnostic_contract()["report_views"]["transition"]==list(d.transition_masks(frame))


def test_contract_26_separate_authorization_provenance_required(monkeypatch,tmp_path):
    # No actual git/data access; simulate the subprocess responses for committed provenance.
    spec=(d.ROOT/d.SPEC_PATH).read_bytes()
    def git(args,**kwargs):
        if args[1:]==["status","--porcelain"]:return type("R",(),{"stdout":""})()
        if args[1:]==["rev-parse","HEAD"]:return type("R",(),{"stdout":"c"*40})()
        return type("R",(),{"stdout":spec})()
    monkeypatch.setattr(d.subprocess,"run",git)
    monkeypatch.delenv(d.AUTHORIZATION_ENV,raising=False)
    with pytest.raises(d.DiagnosticError,match="authorization"):d.execution_provenance(tmp_path)
    auth={"reviewed_implementation_commit":"c"*40,"task_reference":"separate-reviewed-task"}
    monkeypatch.setenv(d.AUTHORIZATION_ENV,json.dumps(auth))
    assert d.execution_provenance(tmp_path)==("c"*40,auth)
    auth["reviewed_implementation_commit"]="b"*40
    monkeypatch.setenv(d.AUTHORIZATION_ENV,json.dumps(auth))
    with pytest.raises(d.DiagnosticError):d.execution_provenance(tmp_path)


@pytest.mark.parametrize("bad", ["established","brier","sparse","only_two_years"])
def test_contract_31_gate_b_requirements(bad):
    cal,trans=evidence(False,True)
    for i,y in enumerate(d.FOLDS):
        e=trans[str(y)]
        if bad=="established": e["established_only:phase:opening"]["log_loss"]=1
        if bad=="brier": e["established_only:first5:1"]["brier"]=.5
        if bad=="sparse": e["phase:opening"]["n"]=29
        if bad=="only_two_years" and i>=2: e["phase:opening"]["log_loss"]=1
    assert d.decide(cal,trans)==d.INCONCLUSIVE_GATE


def test_contract_31_all_fixed_diagnostics_empty_years_actual_nll_semantics(monkeypatch):
    rows=row_frame(n=9)
    cal=d.calibration_diagnostics(rows)
    assert len(cal["2020"]["1"]["bins"])==10
    assert cal["2021"]["1"]["overall"]["bias"] is None
    cell=cal["2020"]["1"]["bins"][3]
    assert cell["n"]==9 and cell["total_nll"]==pytest.approx(rows.nll.sum())
    assert cell["mean_nll"]!=pytest.approx(-np.log(.3))  # All outcomes' true-class losses.
    assert d.confidence_diagnostics(rows)["2020"]["1:1"]["n"]==0
    assert len(d.elo_diagnostics(rows)["2020"]["elo_diff"])==5
    transition=d.transition_diagnostics(rows)
    assert "established_only:phase:opening" in transition["2020"]
    assert "home:ESTABLISHED:first5:1" in transition["2020"]
    assert d.decide(cal,transition)==d.INCONCLUSIVE_GATE


def test_contract_32_fit_warning_and_failure_no_retry(monkeypatch):
    calls=[]
    class Warn:
        def fit(self,*args):
            calls.append(1); warnings.warn("synthetic convergence",ConvergenceWarning)
    monkeypatch.setattr(d,"build_pipeline",Warn)
    with pytest.raises(d.DiagnosticError,match="no retry"): d.fit_fold(source_frame(),source_frame())
    assert calls==[1]


def test_contract_32_import_help_no_data_fit_writes_network(monkeypatch,capsys):
    def forbidden(*a,**k):pytest.fail("Import/help attempted IO or fit")
    monkeypatch.setattr(d,"run_generation",forbidden)
    monkeypatch.setattr(StandardScaler,"fit",forbidden)
    monkeypatch.setattr(LogisticRegression,"fit",forbidden)
    monkeypatch.setattr(Path,"open",forbidden)
    monkeypatch.setattr(Path,"read_bytes",forbidden)
    monkeypatch.setattr(builtins,"open",forbidden)
    monkeypatch.setattr(io,"open",forbidden)
    # Reload module directly under guards; reload resets run_generation, so guard it again.
    importlib.reload(d)
    monkeypatch.setattr(d,"run_generation",forbidden)
    with pytest.raises(SystemExit) as result:d.main(["--help"])
    assert result.value.code==0 and "no overrides" in capsys.readouterr().out


@pytest.mark.parametrize("argument", ["--input","--output","--season","--model","--parameter","--force","--overwrite","--dry-run"])
def test_contract_32_cli_overrides_rejected_without_generation(monkeypatch,argument):
    monkeypatch.setattr(d,"run_generation",lambda:pytest.fail("generation invoked"))
    with pytest.raises(SystemExit) as e:d.main([argument])
    assert e.value.code==2


def test_contract_32_import_help_subprocess_smoke_only():
    for arguments in (["-c","import src.modeling.champion_a_oof_diagnostic"],
                      ["-m","src.modeling.champion_a_oof_diagnostic","--help"]):
        result=subprocess.run([sys.executable,*arguments],cwd=d.ROOT,text=True,capture_output=True,check=False)
        assert result.returncode==0,result.stderr
