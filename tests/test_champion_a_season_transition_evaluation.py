"""The 47 frozen requirements: synthetic evidence ONLY, guarded real paths/network.

Formal functions below run only against isolated tmp roots and toy authority;
neither the production default CLI nor the production formal CLI is invoked.
"""

import ast
import builtins
from copy import deepcopy
import io
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import warnings

import numpy as np
import pandas as pd
import pytest
from sklearn.exceptions import ConvergenceWarning
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

from src.modeling import champion_a_season_transition_evaluation as st


REPO = Path(__file__).parents[1].resolve()
ROSTER = tuple(f"team_{i:04d}" for i in range(1, 7))
FORBIDDEN_MODULES = (
    "src.modeling.champion_a_calibration", "src.modeling.champion_a_oof",
    "src.modeling.architecture", "src.modeling.model_architecture",
    "src.modeling.player_workload", "src.modeling.predict", "src.predict",
    "src.features.player", "src.features.suspension", "src.collect.suspension",
)


@pytest.fixture(autouse=True)
def production_firewall(monkeypatch):
    """Deny even stat/mutation, not merely CSV parsing, on real evidence paths."""
    def check(path):
        if isinstance(path, int):
            return
        try:
            value = os.path.normcase(os.path.abspath(os.fsdecode(path)))
        except TypeError:
            return
        root = os.path.normcase(str(REPO)) + os.sep
        if value.startswith(root):
            rel = value[len(root):].replace("\\", "/")
            if (rel.startswith(("data/", "models/")) or
                    rel == st.RESULT_PATH.casefold() or
                    rel.startswith("docs/champion_a_calibration_evaluation_result") or
                    (not rel.startswith((".venv/", ".tools/")) and
                     any(year in rel for year in ("2025", "2026", "2027")))):
                raise AssertionError(f"PRODUCTION IO FORBIDDEN: {rel}")

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

    def no_network(*args, **kwargs):
        raise AssertionError("NETWORK FORBIDDEN")

    for owner, name in ((socket, "create_connection"), (socket, "getaddrinfo"),
                        (socket.socket, "connect"), (socket.socket, "connect_ex"),
                        (socket.socket, "sendto")):
        monkeypatch.setattr(owner, name, no_network)
    original_import = builtins.__import__

    def scoped_import(name, *args, **kwargs):
        if name.startswith(FORBIDDEN_MODULES):
            raise AssertionError(f"FORBIDDEN LANE IMPORT: {name}")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", scoped_import)
    return check


def match(year, day, number, home=1, away=2, result=2, round_=7):
    return {"match_id": f"toy-{year}-{number:04d}", "season": year, "round": round_,
            "match_date": pd.Timestamp(f"{year}-01-01") + pd.Timedelta(days=day),
            "home_team": f"Club{home}", "away_team": f"Club{away}", "stadium": "Toy ground",
            "home_score": int(result == 2), "away_score": int(result == 0), "result": result,
            "home_team_id": f"team_{home:04d}", "away_team_id": f"team_{away:04d}"}


def frame(*rows):
    return pd.DataFrame(rows).sort_values(["match_date", "match_id"], kind="stable").reset_index(drop=True)


def toy_schedule(counts=None):
    counts = counts or {y: 12 if y in (2021, 2024) else 9 for y in st.YEARS}
    records = []
    for year, count in counts.items():
        for i in range(count):
            home, away = (1, 2) if i % 2 == 0 else (3, 4)
            records.append(match(year, i // 2, i, home, away, i % 3, i // 2 + 1))
    return frame(*records)


def pin_toy_population(monkeypatch, source):
    monkeypatch.setattr(st, "SOURCE_ROWS", len(source))
    monkeypatch.setattr(st, "SEASON_COUNTS", source.season.value_counts().sort_index().to_dict())
    counts, training_hashes, validation_hashes = {}, {}, {}
    for year in st.FOLDS:
        train, valid = source[source.season < year], source[source.season == year]
        counts[year] = (len(train), len(valid))
        training_hashes[year], validation_hashes[year] = st.id_hash(train.match_id), st.id_hash(valid.match_id)
    targets = source[source.season.isin(st.FOLDS)]
    monkeypatch.setattr(st, "FOLD_COUNTS", counts)
    monkeypatch.setattr(st, "TRAIN_ID_HASHES", training_hashes)
    monkeypatch.setattr(st, "VALID_ID_HASHES", validation_hashes)
    monkeypatch.setattr(st, "OOF_ROWS", len(targets))
    monkeypatch.setattr(st, "POOLED_ID_SHA", st.id_hash(targets.match_id))


def toy_oof(source):
    target = source[source.season.isin(st.FOLDS)].reset_index(drop=True)
    rows = target.rename(columns={"season": "validation_year"}).copy()
    rows["match_date"] = rows.match_date.dt.strftime("%Y-%m-%d")
    p = np.array([[.6, .1, .3] if y == 2021 else [.2, .3, .5] for y in rows.validation_year])
    for c, v in zip(st.P_COLUMNS, p.T):
        rows[c] = v
    rows["elo_diff"] = np.zeros(len(rows))  # NOT a baseline replay.
    rows["abs_elo_diff"] = abs(rows.elo_diff)
    rows["predicted_class"] = p.argmax(axis=1)
    rows["max_p"] = p.max(axis=1)
    rows["p_true"] = p[np.arange(len(rows)), rows.result.to_numpy()]
    rows["nll"] = -np.log(rows.p_true)
    rows["brier"] = np.sum((p - (rows.result.to_numpy()[:, None] == np.arange(3)))**2, axis=1)
    metadata = st.schedule_metadata(source).loc[source.season.isin(st.FOLDS)].reset_index(drop=True)
    for c in metadata:
        rows[c] = metadata[c]
    rows["home_favorite"] = (rows.p_home > rows.p_away).astype(int)
    rows["away_favorite"] = (rows.p_away > rows.p_home).astype(int)
    rows["near_even"] = (abs(rows.p_home-rows.p_away) < .05).astype(int)
    return rows[list(st.OOF_COLUMNS)].astype(st.DTYPES)


@pytest.fixture
def toy(monkeypatch):
    source = toy_schedule()
    pin_toy_population(monkeypatch, source)
    rows = toy_oof(source)
    refs = {str(y): st.calculate_metrics(f.result.to_numpy(), f[list(st.P_COLUMNS)])
            for y, f in rows.groupby("validation_year", sort=True)}
    refs["pooled"] = st.calculate_metrics(rows.result.to_numpy(), rows[list(st.P_COLUMNS)])
    monkeypatch.setattr(st, "REFERENCES", refs)
    return source, rows, ROSTER[:4]


def write_bytes(root, rel, data):
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def synthetic_manifest(csv_bytes, rows):
    return {
        "schema_version": "champion_a_oof_diagnostic_v1",
        "purpose": "diagnostic_only_not_formal_evaluation_not_model_input",
        "reviewed_source_commit": "376973e1f2238bbd29799386ec100dd400648ce4",
        "freeze_spec": {"path": "docs/CHAMPION_A_OOF_DIAGNOSTIC_FREEZE_SPEC.md",
                        "commit": "159ca0c7d71dfd10b9d3888971fb05c9f681855e",
                        "sha256": "3167daf9ddff78ef4c3dceec64ed36782c6c36424baed239d83ce1191c023663"},
        "generation_authorization": {"reviewed_implementation_commit": st.GENERATOR_COMMIT, "task_reference": st.GENERATION_TASK},
        "generator": {"path": "src/modeling/champion_a_oof_diagnostic.py", "commit": st.GENERATOR_COMMIT,
                      "sha256": st.GENERATOR_SHA, "git_dirty": False, "fits": 5, "prediction_batches": 5, "automatic_retries": 0},
        "runtime": {"python": "3.12.14", "platform": "Windows-toy", **st.VERSIONS,
                    "requirements_sha256": st.REQUIREMENTS_HASHES["requirements.txt"], "lock_sha256": st.REQUIREMENTS_HASHES["requirements-lock.txt"]},
        "inputs": [{"path": p, "season": y, "rows": st.SEASON_COUNTS[y], "sha256": h}
                   for y, (p, h) in zip(st.YEARS, st.SOURCE_HASHES.items())],
        "team_master": {"path": st.TEAM_MASTER_PATH, "sha256": st.TEAM_MASTER_SHA},
        "champion_a_contract": deepcopy(st.A_CONTRACT),
        "folds": [{"validation_year": y, "training_seasons": list(range(2015, y)),
                   "training_rows": st.FOLD_COUNTS[y][0], "validation_rows": st.FOLD_COUNTS[y][1],
                   "train_ids_sha256": st.TRAIN_ID_HASHES[y], "validation_ids_sha256": st.VALID_ID_HASHES[y]} for y in st.FOLDS],
        "class_order": list(st.CLASS_ORDER), "columns": list(st.OOF_COLUMNS), "column_dtypes": st.DTYPES,
        "row_count": st.OOF_ROWS,
        "csv": {"path": st.CSV_PATH, "sha256": st.sha256(csv_bytes), "encoding": "utf-8", "line_ending": "LF",
                "float_format": "%.17g", "ordered_ids_sha256": st.id_hash(rows.match_id)},
        "references": {"values": deepcopy(st.REFERENCES), "sources": ["docs/H2H_EVALUATION.md", "docs/MODEL_ARCHITECTURE_BENCHMARK_RESULT.md"], "rtol": 0., "atol": 1e-12},
        "observed_metrics": deepcopy(st.REFERENCES), "diagnostic_contract": {"synthetic": True},
        "gates": {k: "PASS" for k in ("input", "source", "chronology", "folds", "identity", "classes", "probabilities", "references", "serialization")},
        "generated_at": "2020-01-01T00:00:00Z",
    }


@pytest.fixture
def inputs(toy, tmp_path, monkeypatch):
    source, rows, roster = toy
    hashes = {}
    for y, rel in zip(st.YEARS, st.SOURCE_HASHES):
        # Freeze the INTENTIONALLY NONCANONICAL physical bytes themselves.
        # Canonical source/accepted toy OOF above remain independent of that order.
        data = source[source.season == y].iloc[::-1].drop(columns=["home_team_id", "away_team_id"]).to_csv(index=False, lineterminator="\n").encode()
        write_bytes(tmp_path, rel, data)
        hashes[rel] = st.sha256(data)
    monkeypatch.setattr(st, "SOURCE_HASHES", hashes)
    master = ("team_id,canonical_name,source_name,source,valid_from,valid_to,source_club_id\n" +
              "".join(f"{team},Club{i},Club{i},jleague_data_site,,,\n" for i, team in enumerate(roster, 1))).encode()
    write_bytes(tmp_path, st.TEAM_MASTER_PATH, master)
    monkeypatch.setattr(st, "TEAM_MASTER_SHA", st.sha256(master))
    data = rows.to_csv(index=False, lineterminator="\n", float_format="%.17g").encode()
    write_bytes(tmp_path, st.CSV_PATH, data)
    monkeypatch.setattr(st, "CSV_SHA", st.sha256(data))
    manifest = synthetic_manifest(data, rows)
    monkeypatch.setattr(st, "DIAGNOSTIC_CONTRACT_SHA", st.metadata_hash(manifest["diagnostic_contract"]))
    data = json.dumps(manifest).encode()
    write_bytes(tmp_path, st.MANIFEST_PATH, data)
    monkeypatch.setattr(st, "MANIFEST_SHA", st.sha256(data))
    (tmp_path / "docs").mkdir(exist_ok=True)
    return tmp_path, source, rows, manifest, roster


def forbid(*args, **kwargs):
    raise AssertionError("Forbidden execution")


def assert_reject(call, text=None, status=None):
    with pytest.raises((st.TransitionError, ValueError, TypeError, KeyError), match=text) as error:
        call()
    if status:
        assert isinstance(error.value, st.TransitionError) and error.value.status == status


def gate_inputs():
    baseline = {y: {"n": st.FOLD_COUNTS[y][1], "accuracy": .5, "log_loss": 1., "brier": .6} for y in st.FOLDS}
    pooled = {"n": st.OOF_ROWS, "accuracy": .5, "log_loss": 1., "brier": .6}
    candidate = deepcopy(baseline)
    for y in st.FOLDS[:3]:
        candidate[y]["log_loss"] = .9
    return candidate, {**pooled, "log_loss": .95}, baseline, pooled


def selection(ll=(.9, .9, .9), passing=(True, True, True)):
    return {"ST0": {}, **{n: {"pooled": {"log_loss": v}, "gate": {"passes": p}, "context": {}, "accuracy": 0.}
                           for n, v, p in zip(st.CHALLENGERS, ll, passing)}}


def stub_formal(monkeypatch, root):
    head = "a" * 40
    monkeypatch.setattr(st, "ROOT", root)
    monkeypatch.setattr(st, "execution_head", lambda r: head)
    monkeypatch.setenv(st.AUTHORIZATION_ENV, json.dumps({"approved_execution_head": head, "task_reference": "toy-st-formal"}))
    monkeypatch.setattr(st, "verify_code", lambda *a: "b" * 64)
    monkeypatch.setattr(st, "runtime_provenance", lambda *a: {"synthetic": True})
    return head


def test_contract_01_exact_registry_spec_pins(tmp_path, monkeypatch):
    st.validate_registry()
    assert tuple(st.CANDIDATES) == ("ST0", "ST1", "ST2", "ST3")
    assert [c.mechanisms for c in st.CANDIDATES.values()] == [0, 1, 1, 2]
    assert st.FEATURES == ("elo_diff",)
    assert st.SPEC_COMMIT == "88b6d28ac12ae2232f29d5084e8d9ebf395292a9"
    # Committed SPEC only; no production input hashes are recomputed.
    spec = subprocess.run(["git", "show", f"{st.SPEC_COMMIT}:{st.SPEC_PATH}"], cwd=REPO, check=True, capture_output=True).stdout
    assert st.sha256(spec) == st.SPEC_SHA == "efbf7995d2a8f5611d4002f5f9fe2299201d1d24c6e100dbf8662081e163cdd2"
    for value in (*st.SOURCE_HASHES.values(), st.TEAM_MASTER_SHA, st.CSV_SHA, st.MANIFEST_SHA,
                  *st.SEMANTIC_HASHES.values(), *st.REQUIREMENTS_HASHES.values(), *st.TRAIN_ID_HASHES.values(), *st.VALID_ID_HASHES.values(), st.POOLED_ID_SHA):
        assert value.encode() in spec
    assert_reject(lambda: st.challenger("ST4"))
    with pytest.raises(TypeError):
        st.CANDIDATES["ST4"] = st.CANDIDATES["ST1"]
    # Future code-integrity validator, isolated copies, no real evidence IO.
    write_bytes(tmp_path, st.SPEC_PATH, spec)
    module = (REPO/st.MODULE_PATH).read_bytes()
    write_bytes(tmp_path, st.MODULE_PATH, module)
    semantic_hashes = {}
    for rel in st.SEMANTIC_HASHES:
        data = b"synthetic reviewed code authority"
        write_bytes(tmp_path, rel, data)
        semantic_hashes[rel] = st.sha256(data)
    monkeypatch.setattr(st, "SEMANTIC_HASHES", semantic_hashes)
    def git(root, *args):
        if args[0] == "show":
            return spec if args[1].endswith(st.SPEC_PATH) else (root/st.MODULE_PATH).read_bytes()
        assert args == ("merge-base", "--is-ancestor", st.SPEC_COMMIT, "a"*40)
        return b""
    monkeypatch.setattr(st, "git", git)
    assert st.verify_code(tmp_path, "a"*40) == st.sha256(module)
    write_bytes(tmp_path, next(iter(semantic_hashes)), b"corrupt authority")
    assert_reject(lambda: st.verify_code(tmp_path, "a"*40), "semantic code SHA")
    write_bytes(tmp_path, next(iter(semantic_hashes)), b"synthetic reviewed code authority")
    write_bytes(tmp_path, st.MODULE_PATH, module + b"\nimport src.modeling.champion_a_calibration_evaluation\n")
    assert_reject(lambda: st.verify_code(tmp_path, "a"*40), "Forbidden import")


def test_contract_02_exact_anchor_regression():
    original = {"toy-high": 1900., "toy-low": 1100., "toy-center": 1500.}
    assert st.season_regression(original) == {"toy-high": 1800., "toy-low": 1200., "toy-center": 1500.}
    assert original["toy-high"] == 1900.
    for bad in (np.nan, np.inf, True):
        assert_reject(lambda: st.season_regression({"toy": bad}))


def test_contract_03_one_boundary_before_first_read(monkeypatch):
    source = frame(match(2015, 0, 0), match(2016, 0, 0), match(2016, 1, 1), match(2016, 2, 2))
    calls = []
    original = st.season_regression
    monkeypatch.setattr(st, "season_regression", lambda ratings: calls.append(dict(ratings)) or original(ratings))
    replay = st.replay_candidate(source, "ST1", ROSTER)
    assert len(calls) == 1 and replay["boundary_seasons"] == [2016]
    assert replay["features"].iloc[1].home_rating == original(calls[0])[ROSTER[0]]
    assert replay["features"].home_season_appearance.tolist() == [1, 1, 2, 3]


def test_contract_04_no_2015_transition(monkeypatch):
    monkeypatch.setattr(st, "season_regression", forbid)
    r = st.replay_candidate(frame(match(2015, 0, 0), match(2015, 1, 1)), "ST1", ROSTER)
    assert r["boundary_seasons"] == []
    assert r["features"].iloc[0].home_rating == r["features"].iloc[0].away_rating == 1500.


def test_contract_05_absent_ids_repeated_global_shrink(monkeypatch):
    source = frame(match(2015, 0, 0), match(2016, 0, 0, 3, 4), match(2017, 0, 0, 3, 4), match(2018, 0, 0))
    calls = []
    original = st.season_regression
    monkeypatch.setattr(st, "season_regression", lambda r: calls.append(dict(r)) or original(r))
    r = st.replay_candidate(source, "ST1", ROSTER)
    first_after = st.replay_candidate(source.iloc[:1], "ST1", ROSTER)["final_ratings"][ROSTER[0]]
    expected = first_after
    for _ in range(3):
        expected = 1500. + .75*(expected-1500.)
    assert r["features"].iloc[-1].home_rating == expected
    assert abs(expected - (1500. + .75**3*(first_after-1500.))) < 1e-12
    assert len(calls) == 3 and all(tuple(c) == ROSTER for c in calls)
    assert r["boundary_seasons"] == [2016, 2017, 2018]
    # Missing entire toy years still apply every intervening global boundary.
    skipped = st.replay_candidate(source.iloc[[0, 3]], "ST1", ROSTER)
    assert skipped["features"].iloc[-1].home_rating == expected


def test_contract_06_center_and_cold_start():
    source = frame(match(2015, 0, 0), match(2018, 0, 0, 5, 6))
    for name in st.CHALLENGERS:
        r = st.replay_candidate(source, name, ROSTER)["features"]
        assert r.iloc[-1].home_rating == r.iloc[-1].away_rating == 1500.
    assert st.season_regression({"new": 1500.}) == {"new": 1500.}


@pytest.mark.parametrize("ordinals", [(1, 1), (5, 6), (6, 5), (100, 100)])
def test_contract_07_st1_always_k30(ordinals):
    assert st.match_k("ST1", *ordinals) == 30.


def test_contract_08_st2_continuous_no_regression(monkeypatch):
    source = frame(match(2015, 0, 0), match(2018, 0, 0))
    monkeypatch.setattr(st, "season_regression", forbid)
    before = st.replay_candidate(source.iloc[:1], "ST2", ROSTER)["final_ratings"]
    r = st.replay_candidate(source, "ST2", ROSTER)
    assert r["boundary_seasons"] == []
    assert r["features"].iloc[1].home_rating == before[ROSTER[0]]
    assert r["features"].iloc[1].away_rating == before[ROSTER[1]]


def asynchronous():
    records = [match(2015, i, i, 1 if i % 2 == 0 else 2, 2 if i % 2 == 0 else 1, i % 3, 40) for i in range(6)]
    records += [match(2015, 6, 6, 1, 3, 2, 40), match(2016, 0, 0, 3, 1, 0, 40)]
    return frame(*records)


def test_contract_09_asynchronous_ordinals_reset_both_sides():
    source = asynchronous()
    a = st.replay_candidate(source, "ST2", ROSTER)["features"]
    assert a.home_season_appearance.tolist() == [1, 2, 3, 4, 5, 6, 7, 1]
    assert a.away_season_appearance.tolist() == [1, 2, 3, 4, 5, 6, 1, 1]
    assert a.match_k.tolist() == [45.]*5 + [30., 45., 45.]
    mutated = source.copy()
    mutated["result"] = 1
    b = st.replay_candidate(mutated, "ST2", ROSTER)["features"]
    pd.testing.assert_frame_equal(a[["home_season_appearance", "away_season_appearance", "match_k"]], b[["home_season_appearance", "away_season_appearance", "match_k"]])
    for pair in ((5, 6), (6, 5), (1, 50)):
        assert st.match_k("ST2", *pair) == 45.


def test_contract_10_both_over5_not_round():
    source = asynchronous()
    source["round"] = 1
    a = st.replay_candidate(source, "ST2", ROSTER)["features"]
    assert a.iloc[5].match_k == 30. and a.iloc[5]["round"] == 1
    assert st.match_k("ST2", 6, 6) == 30.
    for pair in ((0, 1), (1.5, 2), (True, 2)):
        assert_reject(lambda: st.match_k("ST2", *pair))


@pytest.mark.parametrize("result", [0, 1, 2])
@pytest.mark.parametrize("name", st.CHALLENGERS)
def test_contract_11_symmetric_delta_zero_sum(name, result):
    r = st.replay_candidate(frame(match(2015, 0, 0, result=result)), name, ROSTER)
    row = r["features"].iloc[0]
    delta = row.match_k*(result/2.-row.home_expected)
    assert r["final_ratings"][ROSTER[0]] == 1500.+delta
    assert r["final_ratings"][ROSTER[1]] == 1500.-delta
    assert sum(r["final_ratings"].values()) == 9000.


def test_contract_12_st3_exact_composition():
    source = asynchronous()
    prefix = st.replay_candidate(source.iloc[:-1], "ST3", ROSTER)
    all_ = st.replay_candidate(source, "ST3", ROSTER)
    row = all_["features"].iloc[-1]
    shrunk = st.season_regression(prefix["final_ratings"])
    assert row.home_rating == shrunk[ROSTER[2]] and row.away_rating == shrunk[ROSTER[0]]
    assert all_["features"].match_k.tolist() == [45.]*5 + [30., 45., 45.]
    assert all_["boundary_seasons"] == [2016]


def test_contract_13_state_isolation_determinism_prefix():
    source = asynchronous()
    for name in st.CHALLENGERS:
        a, b = st.replay_candidate(source, name, ROSTER), st.replay_candidate(source, name, ROSTER)
        pd.testing.assert_frame_equal(a["features"], b["features"])
        assert a["final_ratings"] == b["final_ratings"] and a["final_ratings"] is not b["final_ratings"]
        prefix = st.replay_candidate(source.iloc[:-1], name, ROSTER)
        pd.testing.assert_frame_equal(prefix["features"], a["features"].iloc[:-1])
        a["features"].loc[0, "elo_diff"] = 123.
        a["final_ratings"][ROSTER[0]] = -999.
        assert b["features"].loc[0, "elo_diff"] == 0.
    assert source.columns.tolist() == list(match(2015, 0, 0))


def test_contract_14_batch_order_and_malformed_rejection(monkeypatch, inputs):
    from src.collect.matches import validate_matches
    root, expected, rows, _, _ = inputs
    rel = next(iter(st.SOURCE_HASHES))
    frozen = (root/rel).read_bytes()
    physical = pd.read_csv(io.BytesIO(frozen), keep_default_na=False)
    assert physical.match_id.tolist() != expected.loc[expected.season.eq(2015), "match_id"].tolist()
    semantic = st.validate_source_file_semantics(physical, 2015)
    assert semantic.match_id.tolist() == physical.match_id.tolist()  # No per-file reorder.
    canonical, accepted, _, _ = st.load_inputs(root)
    pd.testing.assert_frame_equal(canonical, st.validate_schedule(validate_matches(expected)))
    assert canonical.index.tolist() == list(range(len(canonical)))
    st.validate_identity(canonical, accepted)
    assert (root/rel).read_bytes() == frozen  # Loader never rewrites the source.
    source = frame(match(2015, 0, 1, 3, 4), match(2015, 0, 0), match(2015, 1, 2))
    import src.features.elo as elo
    events = []
    actual = elo.expected_score
    monkeypatch.setattr(elo, "expected_score", lambda h, a: events.append((h, a)) or actual(h, a))
    r = st.replay_candidate(source, "ST1", ROSTER)
    assert r["features"].match_id.tolist() == sorted(source.match_id.tolist())
    assert events[:2] == [(1675., 1500.), (1675., 1500.)]
    assert events[2] != events[0]
    duplicate = frame(match(2015, 0, 0), match(2015, 0, 1, 1, 3))
    assert_reject(lambda: st.replay_candidate(duplicate, "ST1", ROSTER), "Same-date team")
    assert_reject(lambda: st.replay_candidate(source.iloc[::-1], "ST1", ROSTER), "Noncanonical")
    malformed = source.copy()
    malformed.loc[0, "season"] = 2016
    assert_reject(lambda: st.replay_candidate(malformed, "ST1", ROSTER), "coherence")
    malformed.loc[0, "match_date"] = pd.Timestamp("2015-01-01 12:00")
    assert_reject(lambda: st.validate_schedule(malformed), "coherence")


def test_contract_15_target_peer_and_prior_validation_leakage():
    source = frame(match(2015, 0, 0), match(2020, 0, 0), match(2020, 0, 1, 3, 4), match(2020, 1, 2))
    for name in st.CHALLENGERS:
        original = st.replay_candidate(source, name, ROSTER)["features"]
        mutated = source.copy()
        mutated.loc[1:2, "result"] = 0
        changed = st.replay_candidate(mutated, name, ROSTER)["features"]
        fields = ["home_rating", "away_rating", "elo_diff", "home_season_appearance", "away_season_appearance", "home_expected", "match_k"]
        pd.testing.assert_frame_equal(original.loc[:2, fields], changed.loc[:2, fields])
        assert original.loc[3, "elo_diff"] != changed.loc[3, "elo_diff"]
        mutated.loc[3, "result"] = 0
        final = st.replay_candidate(mutated, name, ROSTER)["features"]
        pd.testing.assert_frame_equal(changed[fields], final[fields])


def test_contract_16_initial_home_advantage_scale400():
    from src.features.elo import expected_score
    source = frame(match(2015, 0, 0))
    r = st.replay_candidate(source, "ST1", ROSTER)
    expected = 1./(1.+10.**(-175./400.))
    assert r["features"].iloc[0].home_expected == expected_score(1675., 1500.) == expected
    assert r["final_ratings"][ROSTER[0]] == 1500.+30.*(1.-expected)
    assert r["final_ratings"][ROSTER[0]] != 1500.+20.*(1.-expected)
    assert expected_score(1e9, -1e9) == 1. and expected_score(-1e9, 1e9) == 0.


def test_contract_17_one_raw_feature_without_ha():
    r = st.replay_candidate(asynchronous(), "ST3", ROSTER)["features"]
    np.testing.assert_array_equal(r.elo_diff, r.home_rating-r.away_rating)
    assert r.elo_diff.iloc[0] == 0. and st.FEATURES == ("elo_diff",)
    for bad in (np.zeros((3, 2)), np.array([[np.inf]]), np.ones(3)):
        assert_reject(lambda: st.feature_array(bad))
    assert_reject(lambda: st.replay_candidate(r, "ST3", ROSTER), "generated replay")


def test_contract_18_full_frozen_counts_ids_dates_synthetic(monkeypatch):
    assert st.FOLDS == (2020, 2021, 2022, 2023, 2024)
    assert st.FOLD_COUNTS == {2020: (1530, 306), 2021: (1836, 380), 2022: (2216, 306), 2023: (2522, 306), 2024: (2828, 380)}
    # 3208 fabricated rows; no classifier fit or production table involved.
    source = toy_schedule(st.SEASON_COUNTS)
    pin_toy_population(monkeypatch, source)
    assert len(source) == st.SOURCE_ROWS == 3208 and st.OOF_ROWS == 1678
    folds = st.extract_folds(st.validate_schedule(source))
    assert [(y, len(t), len(v)) for y, t, v in folds] == [(2020, 1530, 306), (2021, 1836, 380), (2022, 2216, 306), (2023, 2522, 306), (2024, 2828, 380)]
    for _, train, valid in folds:
        assert train.match_date.max() < valid.match_date.min() and set(train.match_id).isdisjoint(valid.match_id)
    for seed in (0, 7):
        physical_frames = [source.loc[source.season.eq(y)].sample(frac=1., random_state=seed) for y in st.YEARS]
        canonical = st.canonicalize_source(physical_frames)
        pd.testing.assert_frame_equal(canonical, source)
        canonical_folds = st.extract_folds(st.validate_schedule(canonical))
        for (y, train, valid), (_, reference_train, reference_valid) in zip(canonical_folds, folds):
            assert train.match_id.tolist() == reference_train.match_id.tolist()
            assert valid.match_id.tolist() == reference_valid.match_id.tolist()
            assert st.id_hash(train.match_id) == st.TRAIN_ID_HASHES[y]
            assert st.id_hash(valid.match_id) == st.VALID_ID_HASHES[y]
        assert st.id_hash([i for _, _, v in canonical_folds for i in v.match_id]) == st.POOLED_ID_SHA
        st.validate_identity(canonical, toy_oof(source))
    assert_reject(lambda: st.canonicalize_source(physical_frames[:-1]), "ten source")
    assert_reject(lambda: st.canonicalize_source(physical_frames[::-1]), "concat sequence")
    for bad in (source.iloc[:-1], source.iloc[::-1], source.drop(index=0)):
        assert_reject(lambda: st.extract_folds(bad))


@pytest.mark.parametrize("corruption", ["missing", "bytes", "partial", "source_order", "oof_order", "schema", "provenance", "reference", "source_identity",
                                        "source_schema", "source_count", "source_season", "source_date", "source_invalid_date", "source_result", "source_nonfinite_score", "source_score_result", "source_duplicate_id", "source_fixture", "source_self", "source_team", "source_same_date_team"])
def test_contract_19_integrity_gates_before_replay(inputs, monkeypatch, corruption):
    root, source, rows, manifest, roster = inputs
    before = {p: (root/p).read_bytes() for p in st.input_hashes()}
    rel = next(iter(st.SOURCE_HASHES))
    physical = pd.read_csv(io.BytesIO(before[rel]), keep_default_na=False)
    assert st.sha256(before[rel]) == st.SOURCE_HASHES[rel]
    assert physical.match_id.tolist() != source.loc[source.season.eq(2015), "match_id"].tolist()
    loaded, accepted, actual_manifest, used = st.load_inputs(root)
    repeated, _, _, _ = st.load_inputs(root)
    pd.testing.assert_frame_equal(loaded, repeated)
    assert loaded.match_id.tolist() == source.match_id.tolist() and used == list(roster)
    assert len(loaded) == len(source) and loaded.match_id.is_unique
    assert loaded.match_id.tolist() == loaded.sort_values(["match_date", "match_id"], kind="stable").match_id.tolist()
    assert {p: (root/p).read_bytes() for p in st.input_hashes()} == before
    st.baseline_gate(accepted, actual_manifest)
    monkeypatch.setattr(st, "replay_candidate", forbid)
    if corruption == "missing":
        (root / st.CSV_PATH).unlink()
        with pytest.raises(FileNotFoundError):
            st.load_inputs(root)
        return
    if corruption in ("bytes", "partial"):
        (root / st.CSV_PATH).write_bytes(b"" if corruption == "partial" else b"corrupt")
        assert_reject(lambda: st.load_inputs(root), "SHA mismatch")
    elif corruption == "source_order":
        values = (root / rel).read_bytes().splitlines(keepends=True)
        data = values[0] + b"".join(values[:0:-1])
        assert data != before[rel]
        (root / rel).write_bytes(data)
        # ORIGINAL frozen hash is retained. Even now-canonical physical bytes
        # must fail BEFORE TeamMaster/CSV parse and canonicalization.
        import src.collect.teams as teams
        monkeypatch.setattr(teams, "load_team_master", forbid)
        monkeypatch.setattr(st, "validate_source_file_semantics", forbid)
        monkeypatch.setattr(st, "canonicalize_source", forbid)
        assert_reject(lambda: st.load_inputs(root), "SHA mismatch")
    elif corruption.startswith("source_") and corruption != "source_identity":
        bad = physical.copy()
        if corruption == "source_schema":
            bad = bad.drop(columns="stadium")
        elif corruption == "source_count":
            bad = bad.iloc[:-1]
        elif corruption == "source_season":
            bad["season"] = 2016
        elif corruption == "source_date":
            bad.loc[0, "match_date"] = "2016-01-01"
        elif corruption == "source_invalid_date":
            bad.loc[0, "match_date"] = "not-a-date"
        elif corruption == "source_result":
            bad.loc[0, "result"] = 4
        elif corruption == "source_nonfinite_score":
            bad["home_score"] = bad.home_score.astype(float)
            bad.loc[0, "home_score"] = np.inf
        elif corruption == "source_score_result":
            bad.loc[0, "result"] = 0 if bad.loc[0, "result"] == 2 else 2
        elif corruption == "source_duplicate_id":
            bad.loc[0, "match_id"] = bad.loc[1, "match_id"]
        elif corruption == "source_fixture":
            for c in ("match_date", "home_team", "away_team"):
                bad.loc[0, c] = bad.loc[1, c]
        elif corruption == "source_self":
            bad.loc[0, "home_team"] = bad.loc[0, "away_team"]
        elif corruption == "source_team":
            bad.loc[0, "home_team"] = "Unregistered toy club"
        else:
            # Different fixture but one team appears twice on the same date.
            bad.loc[0, "match_date"] = bad.loc[1, "match_date"]
            bad.loc[0, "away_team"] = bad.loc[1, "away_team"]
        data = bad.to_csv(index=False, lineterminator="\n").encode()
        (root/rel).write_bytes(data)
        # Synthetic frozen equivalence only: a correct SHA cannot excuse
        # semantic corruption. Original production constants are never changed.
        monkeypatch.setitem(st.SOURCE_HASHES, rel, st.sha256(data))
        assert_reject(lambda: st.load_inputs(root))
    elif corruption == "oof_order":
        assert_reject(lambda: st.validate_oof(rows.iloc[::-1]), "ordered")
    elif corruption == "schema":
        assert_reject(lambda: st.validate_oof(rows.drop(columns="round")), "schema")
    elif corruption == "provenance":
        manifest["generator"]["fits"] = 4
        assert_reject(lambda: st.validate_manifest(manifest, (root/st.CSV_PATH).read_bytes(), rows), "Generator")
    elif corruption == "source_identity":
        altered = source.copy()
        altered.loc[altered.season.eq(2020), "home_team"] = "Other alias"
        assert_reject(lambda: st.validate_identity(altered, rows), "home_team")
    else:
        manifest["observed_metrics"]["2020"]["log_loss"] += 2e-12
        assert_reject(lambda: st.baseline_gate(rows, manifest), "mismatch", st.REFERENCE_FAILURE)
        assert_reject(lambda: st.validate_manifest(manifest, (root/st.CSV_PATH).read_bytes(), rows), "mismatch", st.REFERENCE_FAILURE)


def test_contract_20_master_registration_alias_unknown_self(inputs):
    from src.collect.teams import load_team_master, UnknownTeamError
    root, source, _, _, roster = inputs
    master = load_team_master(root/st.TEAM_MASTER_PATH)
    valid = st.validate_source(source, master)
    assert valid.home_team_id.tolist() == source.home_team_id.tolist()
    assert master.resolve_team_id("Club1", on=pd.Timestamp("2015-01-01")) == roster[0]
    bad = source.copy()
    bad.loc[0, "home_team_id"] = "team_9999"
    assert_reject(lambda: st.validate_source(bad, master), "registration")
    assert_reject(lambda: st.replay_candidate(bad, "ST1", roster), "Unknown")
    bad.loc[0, "home_team_id"] = roster[1]
    assert_reject(lambda: st.validate_source(bad, master), "self-match")
    with pytest.raises(UnknownTeamError):
        master.resolve_team_id("club1", on=pd.Timestamp("2015-01-01"))
    bad = source.copy()
    bad.loc[0, "home_team"] = "Club3"
    assert_reject(lambda: st.validate_source(bad, master), "alias/date/ID")


def test_contract_21_reject_2025_without_lookup(toy, monkeypatch, production_firewall):
    source, rows, _ = toy
    source = source.copy()
    source.loc[source.index[-1], ["season", "match_date"]] = [2025, pd.Timestamp("2025-01-01")]
    assert_reject(lambda: st.validate_schedule(source), "Forbidden season")
    rows = rows.copy()
    rows.loc[rows.index[-1], "validation_year"] = 2025
    assert_reject(lambda: st.validate_oof(rows), "OOF years")
    monkeypatch.setitem(st.SOURCE_HASHES, "data/processed/jleague/2025_matches_probe.csv", "0"*64)
    assert_reject(lambda: st.input_hashes(), "no discovery")
    with pytest.raises(AssertionError, match="PRODUCTION IO"):
        (REPO/"data/processed/jleague/2025_matches_probe.csv").read_bytes()


@pytest.mark.parametrize("year", [2026, 2027, 2028])
def test_contract_22_future_lockbox_reject_no_access(toy, year):
    source, rows, _ = toy
    bad = source.copy()
    bad.loc[bad.index[-1], ["season", "match_date"]] = [year, pd.Timestamp(f"{year}-01-01")]
    assert_reject(lambda: st.validate_schedule(bad), "Forbidden season")
    bad = rows.copy()
    bad.loc[bad.index[-1], "validation_year"] = year
    assert_reject(lambda: st.validate_oof(bad), "OOF years")
    for rel in (f"data/prospective/{year}/predictions.csv", f"models/{year}/bundle.pkl"):
        with pytest.raises(AssertionError, match="PRODUCTION IO"):
            (REPO/rel).open("wb")


def test_contract_23_training_only_scaler_statistics():
    x, y = np.arange(12, dtype=float).reshape(-1, 1), np.tile(np.arange(3), 4)
    _, a = st.fit_classifier("ST1", x, y, np.array([[1e6], [-1e6]]))
    _, b = st.fit_classifier("ST1", x, y, np.array([[0.]]))
    assert a["scaler_mean"] == [5.5] and a["scaler_var"] == [float(x.var())]
    assert a["scaler_n_samples_seen"] == 12
    for key in ("scaler_mean", "scaler_var", "scaler_scale", "coef", "intercept"):
        assert a[key] == b[key]


@pytest.mark.parametrize("failure", ["warning", "exception", "classes", "nonfinite", "probabilities"])
def test_contract_24_frozen_lr_defaults_finite_convergence(monkeypatch, failure):
    model = st.build_pipeline("ST1")
    assert model.named_steps["scaler"].get_params() == {"copy": True, "with_mean": True, "with_std": True}
    assert model.named_steps["logistic"].get_params() == LogisticRegression(C=1., solver="lbfgs", max_iter=1000, random_state=0).get_params()
    fit = model.fit
    def bad_fit(x, y):
        if failure == "warning":
            warnings.warn("synthetic nonconvergence", ConvergenceWarning)
        if failure == "exception":
            raise RuntimeError("synthetic failure")
        fit(x, y)
        if failure == "classes":
            model.named_steps["logistic"].classes_ = np.array([2, 1, 0])
        if failure == "nonfinite":
            model.named_steps["logistic"].coef_[0, 0] = np.nan
        return model
    monkeypatch.setattr(model, "fit", bad_fit)
    if failure == "probabilities":
        monkeypatch.setattr(model, "predict_proba", lambda x: np.full((len(x), 3), np.nan))
    monkeypatch.setattr(st, "build_pipeline", lambda n: model)
    assert_reject(lambda: st.fit_classifier("ST1", np.arange(9.).reshape(-1, 1), np.tile(np.arange(3), 3), [[0.]]), "no retry", st.MODEL_FAILURE)


def test_contract_25_no_weights_pseudodata_or_mapping(monkeypatch):
    seen = []
    actual = LogisticRegression.fit
    def fit(self, x, y, *args, **kwargs):
        assert not args and not kwargs
        assert len(x) == len(y) == 9 and x.shape[1] == 1
        assert self.C == 1. and self.class_weight is None and self.warm_start is False
        seen.append(y.copy())
        return actual(self, x, y)
    monkeypatch.setattr(LogisticRegression, "fit", fit)
    y = np.tile(np.arange(3), 3)
    st.fit_classifier("ST2", np.arange(9.).reshape(-1, 1), y, [[0.], [1.]])
    np.testing.assert_array_equal(seen[0], y)
    tree = ast.parse((REPO/st.MODULE_PATH).read_text(encoding="utf-8"))
    assert not any(isinstance(n, ast.keyword) and n.arg in ("sample_weight", "class_weight", "warm_start") for n in ast.walk(tree))


def test_contract_26_fresh_fit_predict_st0_firewall(toy, monkeypatch):
    source, rows, roster = toy
    for call in (lambda: st.replay_candidate(source, "ST0", roster), lambda: st.build_pipeline("ST0"),
                 lambda: st.fit_classifier("ST0", [[0.]], [0], [[0.]])):
        assert_reject(call, "ST0")
    before = rows.copy(deep=True)
    models = []
    build = st.build_pipeline
    monkeypatch.setattr(st, "build_pipeline", lambda name: models.append(build(name)) or models[-1])
    result = st.evaluate(source, rows, roster)
    assert len(models) == 15 and len({id(m) for m in models}) == 15
    assert len({id(m.named_steps["scaler"]) for m in models}) == 15
    assert len({id(m.named_steps["logistic"]) for m in models}) == 15
    pd.testing.assert_frame_equal(rows, before)
    assert result["results"]["ST0"]["models"] == {}
    assert result["results"]["ST0"]["pooled"] == st.calculate_metrics(rows.result.to_numpy(), rows[list(st.P_COLUMNS)])


def test_contract_27_exact_toy_accounting_fold_major(toy, monkeypatch):
    source, rows, roster = toy
    counts = {"replays": 0, "scalers": 0, "fits": 0, "predictions": 0}
    order, train_counts, own_features = [], [], {}
    replay, scaler_fit, lr_fit, predict, fit = st.replay_candidate, StandardScaler.fit, LogisticRegression.fit, LogisticRegression.predict_proba, st.fit_classifier
    def counted_replay(src, name, ids):
        assert name != "ST0" and src.match_id.tolist() == source.match_id.tolist()
        counts["replays"] += 1
        result = replay(src, name, ids)
        own_features[name] = result["features"].copy(deep=True)
        return result
    def counted_scaler(self, x, *a, **kw):
        counts["scalers"] += 1
        return scaler_fit(self, x, *a, **kw)
    def counted_lr(self, x, *a, **kw):
        counts["fits"] += 1
        train_counts.append(len(x))
        return lr_fit(self, x, *a, **kw)
    def counted_predict(self, x):
        counts["predictions"] += 1
        return predict(self, x)
    def recorded_fit(name, x, y, target, *, progress):
        order.append((progress["fold"], name))
        year = progress["fold"]
        own = own_features[name]
        assert len(x) == st.FOLD_COUNTS[year][0]
        np.testing.assert_array_equal(x, own.loc[own.season < year, ["elo_diff"]].to_numpy())
        np.testing.assert_array_equal(y, own.loc[own.season < year, "result"].to_numpy())
        np.testing.assert_array_equal(target, own.loc[own.season == year, ["elo_diff"]].to_numpy())
        return fit(name, x, y, target, progress=progress)
    monkeypatch.setattr(st, "replay_candidate", counted_replay)
    monkeypatch.setattr(StandardScaler, "fit", counted_scaler)
    monkeypatch.setattr(LogisticRegression, "fit", counted_lr)
    monkeypatch.setattr(LogisticRegression, "predict_proba", counted_predict)
    monkeypatch.setattr(st, "fit_classifier", recorded_fit)
    result = st.evaluate(source, rows, roster)
    assert counts == {"replays": 3, "scalers": 15, "fits": 15, "predictions": 15}
    assert order == [(year, name) for year in st.FOLDS for name in st.CHALLENGERS]
    assert train_counts == [st.FOLD_COUNTS[y][0] for y in st.FOLDS for _ in st.CHALLENGERS]
    assert result["counts"]["replays_completed"] == 3 and result["counts"]["fits_completed"] == 15


def test_contract_28_no_retry_reuse_or_adaptation(toy, monkeypatch):
    x, y = np.arange(12.).reshape(-1, 1), np.tile(np.arange(3), 4)
    a, record_a = st.fit_classifier("ST3", x, y, [[0.], [3.]])
    b, record_b = st.fit_classifier("ST3", x, y, [[0.], [3.]])
    np.testing.assert_array_equal(a, b)
    assert record_a == record_b
    calls = []
    def failed(*args, **kwargs):
        calls.append(1)
        raise RuntimeError("no retry synthetic fit")
    monkeypatch.setattr(LogisticRegression, "fit", failed)
    progress = st.new_progress()
    progress["fold"] = 2020
    assert_reject(lambda: st.fit_classifier("ST1", x, y, [[0.]], progress=progress), "no retry")
    assert len(calls) == 1 and progress["scaler_fits_completed"] == 1 and progress["fits_completed"] == 0


def test_contract_29_metrics_argmax_brier_loss_domain():
    y = np.array([0, 1, 2])
    p = np.array([[.5, .5, 0.], [0., 1., 0.], [1., 0., 0.]])
    original = p.copy()
    m = st.calculate_metrics(y, p)
    assert m["accuracy"] == 2./3. and m["brier"] == 2.5/3.
    assert m["log_loss"] == pytest.approx((-np.log(.5)-np.log(1.-np.finfo(float).eps)-np.log(np.finfo(float).eps))/3., abs=1e-12)
    np.testing.assert_array_equal(p, original)
    assert st.metric_delta(m, m) == {"accuracy": 0., "log_loss": 0., "brier": 0.}
    for bad in ([[.3, .3, .3]], [[np.nan, 0., 1.]], [[-1., 1., 1.]], [[0., 0., np.inf]], [[1., 0.]], [], [[2., 0., -1.]]):
        assert_reject(lambda: st.probabilities(bad))
    for bad_y in ([1.5], [3], [True]):
        assert_reject(lambda: st.calculate_metrics(bad_y, [[1., 0., 0.]]))
    assert_reject(lambda: st.metric_delta(m, {**m, "n": 4}))


def test_contract_30_pooled_rows_not_fold_average(toy):
    source, rows, roster = toy
    result = st.evaluate(source, rows, roster)
    direct = st.calculate_metrics(rows.result.to_numpy(), rows[list(st.P_COLUMNS)])
    baseline = result["results"]["ST0"]
    assert baseline["pooled"] == direct
    assert direct["log_loss"] != np.mean([v["log_loss"] for v in baseline["folds"].values()])
    assert [v["validation_ids_sha256"] for v in result["identities"]] == [st.VALID_ID_HASHES[y] for y in st.FOLDS]
    for name in st.CHALLENGERS:
        assert result["results"][name]["pooled"]["n"] == len(rows)
        assert result["results"][name]["deltas"]["pooled"] == st.metric_delta(result["results"][name]["pooled"], direct)


def test_contract_31_strict_ll_conjunction_fixed_five():
    candidate, pooled, baseline, bp = gate_inputs()
    assert st.candidate_pass(candidate, pooled, baseline, bp)["passes"]
    assert not st.candidate_pass(candidate, bp, baseline, bp)["passes"]
    candidate[2022]["log_loss"] = 1.
    gate = st.candidate_pass(candidate, pooled, baseline, bp)
    assert gate["improved_ll_folds"] == 2 and not gate["passes"]
    candidate.pop(2024)
    assert_reject(lambda: st.candidate_pass(candidate, pooled, baseline, bp), "denominator")


def test_contract_32_brier_exact_no_tolerance():
    args = list(gate_inputs())
    assert st.candidate_pass(*args)["passes"]  # Equality passes.
    args[1]["brier"] = np.nextafter(.6, np.inf)
    assert args[1]["brier"]-.6 < st.ATOL
    assert not st.candidate_pass(*args)["passes"]


def test_contract_33_accuracy_not_gate_or_selection():
    candidate, pooled, baseline, bp = gate_inputs()
    candidate = {y: {**m, "accuracy": 0.} for y, m in candidate.items()}
    pooled["accuracy"] = 0.
    assert st.candidate_pass(candidate, pooled, baseline, bp)["passes"]
    pooled["log_loss"] = bp["log_loss"]
    pooled["accuracy"] = 1.
    assert not st.candidate_pass(candidate, pooled, baseline, bp)["passes"]
    results = selection()
    results["ST3"]["accuracy"] = 1.
    assert st.select_candidate(results)["selected_candidate"] == "ST1"


def test_contract_34_exact_two_context_views_empty_and_firewall(toy):
    source, rows, roster = toy
    probe = pd.DataFrame({"round": [5, 6, 1, 9], "home_season_appearance": [6, 5, 6, 6], "away_season_appearance": [6, 6, 6, 1]})
    masks = st.context_masks(probe)
    assert tuple(masks) == ("opening", "any_team_first5")
    np.testing.assert_array_equal(masks["opening"], [True, False, True, False])
    np.testing.assert_array_equal(masks["any_team_first5"], [False, True, False, True])
    empty = {k: np.zeros(4, dtype=bool) for k in masks}
    assert st.context_metrics(np.array([0, 1, 2, 0]), np.full((4, 3), 1/3), empty) == {k: {"n": 0, "log_loss": None, "brier": None} for k in masks}
    result = st.evaluate(source, rows, roster)
    for name in st.CANDIDATES:
        assert set(result["results"][name]["context"]) == {*st.FOLDS, "pooled"}
        for views in result["results"][name]["context"].values():
            assert tuple(views) == tuple(masks)
            assert all(set(v) == {"n", "log_loss", "brier"} for v in views.values())
    old = st.select_candidate(result["results"])
    result["results"]["ST3"]["context"] = {"manufactured": "best"}
    assert st.select_candidate(result["results"]) == old


def test_contract_35_passing_only_minimum_anchored_ties():
    result = st.select_candidate(selection((.9+1.6e-12, .9+.8e-12, .9)))
    assert result["tied_candidates"] == ["ST2", "ST3"] and result["selected_candidate"] == "ST2"
    result = st.select_candidate(selection((.1, .9, 1.2), (False, True, True)))
    assert result["selected_candidate"] == "ST2" and result["tied_candidates"] == ["ST2"]
    result = st.select_candidate(selection((1e6+1e-7, 1e6, 1e6+1e-6)))
    assert result["tied_candidates"] == ["ST2"]  # No relative tolerance.


def test_contract_36_tie_mechanism_count_not_coefficients():
    results = selection((.9+5e-13, 1., .9))
    results["ST1"]["models"] = {"coef": [1000.]*100}
    results["ST3"]["models"] = {"coef": [0.]}
    assert st.select_candidate(results)["selected_candidate"] == "ST1"


def test_contract_37_fixed_order_two_decisions_technical_stop(monkeypatch, capsys):
    assert st.select_candidate(selection())["selected_candidate"] == "ST1"
    assert st.select_candidate(selection(passing=(False, True, True)))["selected_candidate"] == "ST2"
    assert st.select_candidate(selection(passing=(False, False, True)))["decision"] == st.PROCEED_GATE
    assert st.select_candidate(selection(passing=(False, False, False))) == {"decision": st.CLOSE_GATE, "selected_candidate": None, "tied_candidates": []}
    monkeypatch.setattr(st, "preflight", lambda: st.require(False, "toy integrity STOP"))
    assert st.main([]) == 1  # Dispatch stub ONLY, not production default CLI.
    output = capsys.readouterr()
    assert "no research decision" in output.err and not output.out


def test_contract_38_authority_durable_exclusive_marker_before_gates(inputs, monkeypatch):
    root, _, _, _, _ = inputs
    actual_execution_head = st.execution_head
    head = stub_formal(monkeypatch, root)
    for value in ({}, {"approved_execution_head": "x", "task_reference": "toy"},
                  {"approved_execution_head": head, "task_reference": " "},
                  {"approved_execution_head": head, "task_reference": st.GENERATION_TASK},
                  {"approved_execution_head": head, "task_reference": st.CALIBRATION_TASK},
                  {"approved_execution_head": head, "task_reference": "toy", "override": True}):
        monkeypatch.setenv(st.AUTHORIZATION_ENV, json.dumps(value))
        assert_reject(lambda: st.formal_authorization(root))
    monkeypatch.setenv(st.AUTHORIZATION_ENV, json.dumps({"approved_execution_head": head, "task_reference": "toy-st-formal"}))
    events = []
    fsync = os.fsync
    monkeypatch.setattr(os, "fsync", lambda fd: events.append("fsync") or fsync(fd))
    def gate(*args):
        assert events == ["fsync"]
        payload = json.loads((root/st.MARKER_PATH).read_bytes())
        assert payload["state"] == "ATTEMPT_CONSUMED" and payload["schema_version"] == "champion_a_season_transition_attempt_v1"
        events.append("gate")
        raise st.TransitionError("toy pre-fit STOP")
    monkeypatch.setattr(st, "verify_code", gate)
    monkeypatch.setattr(st, "replay_candidate", forbid)
    assert_reject(st.formal, "toy pre-fit STOP")
    assert events == ["fsync", "gate"]
    # Independently test actual clean-HEAD validation with stub git outputs.
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(st, "git", lambda root, *a: b"dirty" if a[0] == "status" else b"a"*40)
        assert_reject(lambda: actual_execution_head(root), "Clean")


@pytest.mark.parametrize("stage", ["pre-fit", "reference", "replay", "fit", "prediction", "metrics", "publication", "fsync"])
def test_contract_39_immutable_consumed_failure_evidence(inputs, monkeypatch, stage):
    root, _, _, _, _ = inputs
    stub_formal(monkeypatch, root)
    snapshots = []
    def stop(*args, **kwargs):
        snapshots.append((root/st.MARKER_PATH).read_bytes())
        raise st.TransitionError("synthetic failure at " + stage, st.MODEL_FAILURE if stage in ("fit", "prediction") else st.ARTIFACT_FAILURE)
    if stage == "pre-fit":
        monkeypatch.setattr(st, "load_inputs", stop)
    elif stage == "reference":
        monkeypatch.setattr(st, "baseline_gate", stop)
    elif stage == "replay":
        monkeypatch.setattr(st, "replay_candidate", stop)
    elif stage == "fit":
        monkeypatch.setattr(LogisticRegression, "fit", stop)
    elif stage == "prediction":
        monkeypatch.setattr(LogisticRegression, "predict_proba", stop)
    elif stage == "metrics":
        actual_metrics = st.calculate_metrics
        calls = []
        def fail_candidate_metrics(*args):
            calls.append(1)
            if len(calls) == 7:  # six saved-reference reductions, then formal scoring.
                return stop()
            return actual_metrics(*args)
        monkeypatch.setattr(st, "calculate_metrics", fail_candidate_metrics)
    elif stage == "publication":
        monkeypatch.setattr(st, "publish_result", stop)
    else:
        monkeypatch.setattr(os, "fsync", stop)
        monkeypatch.setattr(st, "load_inputs", forbid)
    assert_reject(st.formal, "progress=")
    marker = (root/st.MARKER_PATH).read_bytes()
    assert snapshots == [marker] and json.loads(marker)["state"] == "ATTEMPT_CONSUMED"
    assert not (root/st.RESULT_PATH).exists()
    assert_reject(st.formal, "Existing/partial consumed marker")
    assert (root/st.MARKER_PATH).read_bytes() == marker


@pytest.mark.parametrize("evidence", ["marker_empty", "marker_partial", "result_empty", "result_partial", "concurrent", "publication_race"])
def test_contract_40_existing_partial_concurrent_exclusive_publication(inputs, monkeypatch, evidence):
    root, _, _, _, _ = inputs
    stub_formal(monkeypatch, root)
    monkeypatch.setattr(st, "replay_candidate", forbid)
    if evidence == "concurrent":
        code = ("from pathlib import Path; from src.modeling.champion_a_season_transition_evaluation import process_lock,TransitionError; "
                f"r=Path({str(root)!r});\ntry:\n with process_lock(r): raise AssertionError('acquired')\nexcept TransitionError:\n print('REFUSED')")
        with st.process_lock(root):
            result = subprocess.run([sys.executable, "-B", "-c", code], cwd=REPO, capture_output=True, text=True, check=True)
            assert result.stdout.strip() == "REFUSED"
            assert_reject(st.formal, "Concurrent")
        assert not (root/st.MARKER_PATH).exists()
        return
    if evidence == "publication_race":
        marker_sha = st.consume_marker(root, {"state": "ATTEMPT_CONSUMED"})
        exclusive = st.exclusive_write
        def race(path, data):
            path.write_bytes(b"racing partial result")
            exclusive(path, data)
        monkeypatch.setattr(st, "exclusive_write", race)
        with pytest.raises(FileExistsError):
            st.publish_result(root, "complete synthetic result", marker_sha)
        assert (root/st.RESULT_PATH).read_bytes() == b"racing partial result"
        return
    rel = st.MARKER_PATH if evidence.startswith("marker") else st.RESULT_PATH
    data = b"" if evidence.endswith("empty") else b"{partial"
    write_bytes(root, rel, data)
    assert_reject(st.formal, "Existing/partial")
    assert (root/rel).read_bytes() == data


def test_contract_41_failure_stage_counts_no_drop_retry_replacement(inputs, monkeypatch):
    root, _, _, _, _ = inputs
    stub_formal(monkeypatch, root)
    calls = []
    fit = LogisticRegression.fit
    def fail_second(self, x, y):
        calls.append(len(x))
        if len(calls) == 2:
            raise RuntimeError("toy second fit failed")
        return fit(self, x, y)
    monkeypatch.setattr(LogisticRegression, "fit", fail_second)
    with pytest.raises(st.TransitionError) as exc:
        st.formal()
    message = str(exc.value)
    assert "2020:ST2:fit" in message and "'replays_completed': 3" in message
    assert "'fit_attempts': 2" in message and "'fits_completed': 1" in message
    assert "'scaler_fits_completed': 2" in message and "'predictions_completed': 1" in message
    assert len(calls) == 2 and exc.value.status == st.MODEL_FAILURE
    assert st.CLOSE_GATE not in message and st.PROCEED_GATE not in message
    assert not (root/st.RESULT_PATH).exists()
    assert_reject(st.formal, "Existing/partial")
    assert len(calls) == 2


@pytest.mark.parametrize("help_", [False, True])
def test_contract_42_import_help_stdlib_no_io(help_):
    # Independent process audits actual import/help; scientific and lane imports
    # forbidden before module load. -B prevents bytecode mutation.
    script = f"""
import sys, os
def audit(event,args):
 if event == 'open':
  p = str(args[0]).replace('\\\\','/').casefold()
  if '/data/' in p or '/models/' in p: raise AssertionError('task IO')
  if len(args)>1 and isinstance(args[1],str) and any(c in args[1] for c in 'wax+'): raise AssertionError('write')
 if event.startswith(('socket.', 'os.mkdir','os.remove','os.rename')): raise AssertionError(event)
 if event == 'import' and args[0].startswith(('numpy','pandas','sklearn','requests','httpx','src.collect','src.features','src.modeling.champion_a_calibration','src.modeling.architecture','src.modeling.player_workload')): raise AssertionError('forbidden import')
sys.addaudithook(audit)
import src.modeling.champion_a_season_transition_evaluation as module
assert not any(n in sys.modules for n in ('numpy','pandas','sklearn'))
if {help_!r}:
 try: module.main(['--help'])
 except SystemExit as exc: assert exc.code == 0
else: print('IMPORT_SAFE')
"""
    result = subprocess.run([sys.executable, "-B", "-c", script], cwd=REPO, capture_output=True, text=True, check=True)
    assert "--confirm-one-shot" in result.stdout if help_ else result.stdout.strip() == "IMPORT_SAFE"


def test_contract_43_readonly_preflight_structural_only(inputs, monkeypatch):
    root, _, _, _, _ = inputs
    stub_formal(monkeypatch, root)
    for function in ("replay_candidate", "build_pipeline", "fit_classifier", "calculate_metrics", "baseline_gate", "candidate_pass", "select_candidate", "consume_marker", "publish_result"):
        monkeypatch.setattr(st, function, forbid)
    before = {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()}
    # Function with tmp ROOT only, NOT default production CLI.
    result = st.preflight()
    assert result["status"] == "READY_FOR_ONE_CHAMPION_A_SEASON_TRANSITION_FORMAL_EVALUATION"
    assert result["candidate_replay"] == result["candidate_fit"] == result["candidate_prediction"] == result["candidate_metrics"] == "NOT RUN"
    after = {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()}
    assert before == after
    assert not result["marker_created"] and not result["result_created"]


def test_contract_44_network_guards_and_no_collection():
    with pytest.raises(AssertionError, match="NETWORK"):
        socket.create_connection(("127.0.0.1", 9))
    with socket.socket() as client:
        with pytest.raises(AssertionError, match="NETWORK"):
            client.connect(("127.0.0.1", 9))
        with pytest.raises(AssertionError, match="NETWORK"):
            client.connect_ex(("127.0.0.1", 9))
    tree = ast.parse((REPO/st.MODULE_PATH).read_text(encoding="utf-8"))
    imports = [n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)] + [a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names]
    assert not any(n.startswith(("socket", "urllib", "requests", "httpx", "aiohttp")) for n in imports)
    assert {n for n in imports if n.startswith("src.collect")} == {"src.collect.matches", "src.collect.teams"}


def test_contract_45_no_activation_prospective_dependency_success_tmp_only(inputs, monkeypatch):
    root, source, rows, manifest, roster = inputs
    stub_formal(monkeypatch, root)
    result = st.formal()  # Isolated synthetic formal FUNCTION, never real CLI.
    assert result["status"] == "COMPLETE" and result["automatic_retries"] == 0
    assert result["counts"]["fits_completed"] == 15 and result["counts"]["replays_completed"] == 3
    text = (root/st.RESULT_PATH).read_text(encoding="utf-8")
    assert "separate prospective freeze at a NEW unseen boundary" in text
    assert "ST0=saved accepted p, ZERO replay/fit/prediction" in text
    assert "winner_refits\": 0" in text
    assert "Feature-contract changes=NO" in text and "tuning=NOT RUN" in text
    assert "any_team_first5" in text and "opening" in text
    assert set(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()) == {*st.input_hashes(), st.MARKER_PATH, st.RESULT_PATH}
    assert_reject(st.formal, "Existing/partial result")


def test_contract_46_calibration_firewall_untouched(production_firewall):
    with pytest.raises(AssertionError, match="FORBIDDEN LANE"):
        builtins.__import__("src.modeling.champion_a_calibration_evaluation")
    for rel in ("docs/CHAMPION_A_CALIBRATION_EVALUATION_RESULT.md", "data/processed/model_calibration/formal_calibration_attempt.json"):
        with pytest.raises(AssertionError, match="PRODUCTION IO"):
            (REPO/rel).read_bytes()
    tree = ast.parse((REPO/st.MODULE_PATH).read_text(encoding="utf-8"))
    assert not any(isinstance(n, ast.ImportFrom) and "calibration" in n.module for n in ast.walk(tree))


def test_contract_47_scoped_dependencies_offline_exact_inputs(monkeypatch, inputs):
    root, _, _, _, _ = inputs
    tree = ast.parse((REPO/st.MODULE_PATH).read_text(encoding="utf-8"))
    repository_imports = {n.module: {a.name for a in n.names} for n in ast.walk(tree)
                          if isinstance(n, ast.ImportFrom) and n.module.startswith("src.")}
    assert repository_imports == {"src.features.elo": {"expected_score"}, "src.collect.matches": {"validate_matches"}, "src.collect.teams": {"load_team_master"}}
    assert not any(isinstance(n, ast.Attribute) and n.attr in ("glob", "rglob") for n in ast.walk(tree))
    for name in FORBIDDEN_MODULES:
        with pytest.raises(AssertionError, match="FORBIDDEN LANE"):
            builtins.__import__(name)
    accessed = []
    read = Path.read_bytes
    def record(path):
        accessed.append(path.relative_to(root).as_posix())
        return read(path)
    monkeypatch.setattr(Path, "read_bytes", record)
    st.load_inputs(root)
    assert set(accessed) == set(st.input_hashes())
    assert len(accessed) == 14  # thirteen snapshots + immutable-master recheck.
    for args in (["--formal"], ["--confirm-one-shot"], ["--source", "x"], ["--candidate", "ST4"]):
        with pytest.raises(SystemExit) as exc:
            st.main(args)
        assert exc.value.code == 2
