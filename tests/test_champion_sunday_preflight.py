"""Pinned operational pure-function contracts, synthetic fixtures only.

Only selected function ASTs are executed. The updater module, collector, worker,
Champion artifact loader and estimator are never imported or invoked.
"""
import ast
from copy import deepcopy
from datetime import datetime, timedelta
import hashlib
from pathlib import Path
import subprocess
from types import SimpleNamespace
import uuid
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import pytest

from test_dashboard_feed import production_and_network_firewall
from scripts import build_dashboard_feed as feed

OPS_COMMIT = "5ac9052a221c6d8d563ec982bc48fbddb9e80bfa"
TARGET_COLUMNS = ("fixture_key", "match_id", "match_date", "kickoff_time",
                  "home_team_id", "away_team_id", "match_id_namespace")


@pytest.fixture(scope="module")
def source():
    # git object read only; no worker, shell, HTTP or model deserialization.
    body = subprocess.check_output(
        ["git", "--no-optional-locks", "show", f"{OPS_COMMIT}:scripts/update_champion_dashboard.py"],
        cwd=Path(__file__).resolve().parents[1], timeout=10)
    return body.decode("utf-8")


@pytest.fixture
def contract(source):
    selected = {"select_targets", "require_complete_history", "new_records", "timestamp_aware"}
    nodes = [n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name in selected]
    assert {n.name for n in nodes} == selected
    diagnostics = []
    ns = dict(feed=feed, pd=pd, np=np, ZoneInfo=ZoneInfo, timedelta=timedelta,
              datetime=datetime, TARGET_COLUMNS=TARGET_COLUMNS, uuid=uuid,
              NATIVE=feed.CHAMPION_PREDICTION_ARTIFACT,
              atomic_json=lambda path, value: diagnostics.append(value))
    exec(compile(ast.Module(body=nodes, type_ignores=[]), "<pinned-pure-updater-functions>", "exec"), ns)
    return SimpleNamespace(**{name: ns[name] for name in selected}, diagnostics=diagnostics)


@pytest.fixture
def season():
    rows = [dict(fixture_key=f"synthetic:{i}", match_id=f"{700000+i}",
                 match_date="2026-10-24" if i < 5 else "2026-10-25",
                 kickoff_time="14:00", home_team_id=f"h{i}", away_team_id=f"a{i}",
                 match_id_namespace=feed.MATCH_PAGE_NAMESPACE, status="scheduled") for i in range(10)]
    return SimpleNamespace(schedule=pd.DataFrame(rows), manifest={"format_version": "ongoing-v2"},
                           revision_id="a"*64, manifest_sha="b"*64)


NOW = datetime.fromisoformat("2026-10-24T06:00:00+00:00")
SAVED = [{"fixture_key": f"synthetic:{i}"} for i in range(5)]


def test_selection_does_not_make_history_complete(contract, season):
    selected = contract.select_targets(season, SAVED, NOW, 2)
    assert len(selected) == 5 and tuple(selected.columns) == TARGET_COLUMNS
    with pytest.raises(ValueError, match="prediction_history_incomplete"):
        contract.require_complete_history(season, "2026-10-25", Path("synthetic-never-written"), NOW)
    assert len(contract.diagnostics[0]["unresolved"]) == 5
    assert contract.diagnostics[0]["officialRevision"] == season.revision_id


@pytest.mark.parametrize("status", ["scheduled", "candidate"])
def test_each_uncompleted_prior_fixture_holds(contract, season, status):
    season.schedule.loc[:4, "status"] = "completed"
    season.schedule.loc[0, "status"] = status
    with pytest.raises(ValueError, match="prediction_history_incomplete"):
        contract.require_complete_history(season, "2026-10-25", Path("no-file-write"), NOW)
    assert len(contract.diagnostics[0]["unresolved"]) == 1


def test_verified_completed_prior_day_is_allowed_by_daily_contract(contract, season):
    season.schedule.loc[:4, "status"] = "completed"
    contract.require_complete_history(season, "2026-10-25", Path("no-file-write"), NOW)
    assert contract.diagnostics == []  # Sunday's own unfinished matches are not history.


@pytest.mark.parametrize("offset", [0, 1, 4])
def test_partial_saved_sunday_refused(contract, season, offset):
    with pytest.raises(ValueError, match="saved_date_batch_changed"):
        contract.select_targets(season, SAVED + [{"fixture_key": f"synthetic:{5+offset}"}], NOW, 2)


def test_all_saved_has_no_prediction_target(contract, season):
    saved = season.schedule[["fixture_key"]].to_dict("records")
    assert contract.select_targets(season, saved, NOW, 2).empty


@pytest.mark.parametrize("now,count", [("2026-10-22T22:00:00+00:00",5),
                                       ("2026-10-22T00:00:00+00:00",0),
                                       ("2026-10-24T23:00:00+00:00",5)])
def test_native_two_day_horizon_in_JST(contract, season, now, count):
    assert len(contract.select_targets(season, SAVED, datetime.fromisoformat(now), 2)) == count


@pytest.mark.parametrize("at", ["2026-10-25T05:00:00+00:00", "2026-10-25T05:00:00.000001+00:00"])
def test_kickoff_boundary_refused(contract, season, at):
    with pytest.raises(ValueError, match="kickoff_elapsed"):
        contract.select_targets(season, SAVED, datetime.fromisoformat(at), 2)


@pytest.mark.parametrize("field,value,error", [
    ("match_id", "", "official_id_missing"),
    ("match_id_namespace", "unreviewed_namespace", "official_id_missing"),
    ("status", "candidate", "target_not_officially_scheduled"),
    ("home_team_id", "h6", "target_team_date_duplicate"),
    ("match_id", "700006", "target_identity_duplicate"),
    ("fixture_key", "synthetic:6", "target_identity_duplicate"),
])
def test_identity_and_schedule_fail_closed(contract, season, field, value, error):
    season.schedule.loc[5, field] = value
    with pytest.raises(ValueError, match=error):
        contract.select_targets(season, SAVED, NOW, 2)


def test_typed_official_revision_required(contract, season):
    season.manifest["format_version"] = "ongoing-v1"
    with pytest.raises(ValueError, match="prediction_requires_typed_official_ids"):
        contract.select_targets(season, SAVED, NOW, 2)


def test_native_output_class_order_and_binding_without_any_model(contract, season):
    targets = contract.select_targets(season, SAVED, NOW, 2)
    master = SimpleNamespace(aliases=[SimpleNamespace(team_id=x, canonical_name=x)
        for x in season.schedule.home_team_id.tolist()+season.schedule.away_team_id.tolist()])
    generated = datetime.fromisoformat("2026-10-25T00:00:00+00:00")
    before = deepcopy(SAVED)
    rows, bindings = contract.new_records(targets, np.tile([.2,.3,.5], (5,1)), season, master, generated)
    assert len(rows) == len(bindings) == 5 and SAVED == before
    for row, binding in zip(rows, bindings):
        assert (row["a_p_away"],row["a_p_draw"],row["a_p_home"]) == ("0.2","0.3","0.5")
        assert row["prediction_generated_at"] == generated.isoformat()
        assert row["source_revision"] == season.revision_id
        assert binding["identity_witness_manifest_sha256"] == season.manifest_sha
        assert binding["prediction_id_namespace"] == feed.MATCH_PAGE_NAMESPACE
        assert set(row) == set(feed.CHAMPION_COLUMNS)


@pytest.mark.parametrize("values", [np.zeros((4,3)),np.tile([.1,.1,.1],(5,1)),
                                    np.tile([float("nan"),.3,.5],(5,1)),np.tile([-.2,.3,.9],(5,1))])
def test_output_validation_refuses_bad_probabilities(contract, season, values):
    targets=contract.select_targets(season,SAVED,NOW,2)
    with pytest.raises(ValueError,match="prediction_probabilities"):
        contract.new_records(targets,values,season,SimpleNamespace(aliases=[]),NOW)


def test_updater_has_no_date_or_no_collection_CLI(source):
    parsed=ast.parse(source)
    main=next(n for n in parsed.body if isinstance(n,ast.FunctionDef) and n.name=='main')
    flags=[n.args[0].value for n in ast.walk(main) if isinstance(n,ast.Call)
           and isinstance(n.func,ast.Attribute) and n.func.attr=='add_argument']
    assert flags == ["--config","--slot"]
    assert "collector(source, runtime, config, stage)" in source
    assert source.index("collector(source, runtime, config, stage)") < source.index('targets = select_targets')


def test_evening_predictor_is_not_selected_and_no_fixed_0700_cutoff(source):
    assert 'if slot == "morning" else None' in source
    assert 'now - observed <= timedelta(hours=config["max_source_age_hours"])' in source
    assert 'clock_moved_backwards' in source and 'kickoff_elapsed_before_commit' in source
    assert 'information_cutoff' not in source and 'friday' not in source.lower()


def test_daily_batch_directory_publish_and_no_automatic_stale_lock_recovery(source):
    parsed=ast.parse(source)
    publish=next(n for n in parsed.body if isinstance(n,ast.FunctionDef) and n.name=='publish_batch')
    code=ast.unparse(publish)
    assert 'stage.rename(destination)' in code and 'prediction_batch_already_exists' in code
    assert all(name in code for name in ['predictions.csv','bindings.csv','manifest.json'])
    assert 'A crashed owner\'s lock is deliberately not reclaimed automatically.' in source
    assert 'with update_lock(runtime)' in source
    assert source.index('publish_batch(runtime, added, added_bindings)') < source.index('with publish_display_feeds(runtime, legacy, rounds)')
