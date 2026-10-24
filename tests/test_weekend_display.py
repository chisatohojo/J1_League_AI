"""Synthetic-only display tests. No collector, models, real stores or task execution."""
from copy import deepcopy
import json
import shutil
import subprocess

import pytest

from test_dashboard_feed import (repository, prepare_period_repository, publish,
                                 production_and_network_firewall, save_predictions, csv_bytes)
from scripts import build_dashboard_feed as feed
from scripts import weekend_display as view
from scripts.serve_dashboard import create_server, main as server_main


def arrange(repo, days=None, *, unsaved=(), finished=(), observed="2026-10-23T00:00:00Z"):
    days = days or ["2026-10-24"] * 5 + ["2026-10-25"] * 5
    prepare_period_repository(repo, days, unsaved=unsaved, finished=finished)
    sha = publish(repo["current_dir"], repo["current_rows"], observed=observed, version="ongoing-v2")
    (repo["root"] / feed.ONGOING_PATH / "latest.json").write_text(json.dumps({
        "revision_id": repo["current_id"], "manifest_sha256": sha}), encoding="utf8")
    return feed.read_dashboard_projection(repo["root"])


@pytest.mark.parametrize("missing", [(), tuple(range(5)), tuple(range(5, 10)), tuple(range(10))])
def test_all_ten_official_fixtures_without_inventing_probabilities(repository, missing):
    projection = arrange(repository, unsaved=missing)
    before = {p: p.read_bytes() for p in repository["root"].rglob("*") if p.is_file()}
    result = view.project_weekend(projection)
    assert result["period"] == ["2026-10-24", "2026-10-25"]
    assert len(result["matches"]) == 10
    assert sum(r["predictionStatus"] == "saved" for r in result["matches"]) == 10-len(missing)
    assert all(r["prediction"] is None for r in result["matches"] if r["predictionStatus"] != "saved")
    for row in result["matches"]:
        if row["prediction"]:
            assert row["prediction"] == projection.matches[row["id"]]["prediction"]
    assert before == {p: p.read_bytes() for p in repository["root"].rglob("*") if p.is_file()}
    assert projection.payload == feed.build_dashboard_feed(repository["root"])


def test_remaining_sunday_keeps_completed_saturday_and_previous_contract(repository):
    projection = arrange(repository, finished=tuple(range(5)), observed="2026-10-25T00:00:00Z")
    previous = deepcopy(projection.payload["previousRound"])
    result = view.project_weekend(projection)
    assert len(result["matches"]) == 10
    assert sum(r["fixtureStatus"] == "completed" for r in result["matches"]) == 5
    assert projection.payload["previousRound"] == previous


@pytest.mark.parametrize("days,period", [
    (["2026-10-31", "2026-11-01"], ["2026-10-31", "2026-11-01"]),
    (["2026-12-26", "2026-12-27"], ["2026-12-26", "2026-12-27"]),
    (["2027-01-02", "2027-01-03"], ["2027-01-02", "2027-01-03"]),
])
def test_calendar_boundaries(repository, days, period):
    result = view.project_weekend(arrange(repository, days))
    assert result["period"] == period
    assert len(result["matches"]) == 2


@pytest.mark.parametrize("day,expected", [("2027-12-31", None), ("2027-01-02", ("2027-01-02", "2027-01-03")), ("2023-12-31", ("2023-12-30", "2023-12-31"))])
def test_weekend_bounds_without_widening_official_season(day, expected):
    if expected is None:
        with pytest.raises(ValueError): view.weekend_bounds(day)
    else: assert view.weekend_bounds(day) == expected


def test_exclude_friday_monday_prior_and_next_weekends(repository):
    days = ["2026-10-17", "2026-10-18", "2026-10-23", "2026-10-24", "2026-10-25", "2026-10-26", "2026-10-31"]
    result = view.project_weekend(arrange(repository, days))
    assert [r["kickoffAt"][:10] for r in result["matches"]] == ["2026-10-24", "2026-10-25"]


def test_jst_and_snapshot_date_drive_selection_not_host_clock(repository):
    p = arrange(repository, observed="2026-10-24T15:00:00Z")  # Sunday 00:00 JST
    assert view.project_weekend(p)["period"] == ["2026-10-24", "2026-10-25"]


def test_rescheduled_saved_prediction_is_held_not_reassigned(repository):
    arrange(repository)
    repository["current_rows"][0]["kickoff_time"] = "02:00"
    sha = publish(repository["current_dir"], repository["current_rows"], observed="2026-10-23T00:00:00Z", version="ongoing-v2")
    (repository["root"] / feed.ONGOING_PATH / "latest.json").write_text(json.dumps({"revision_id": repository["current_id"], "manifest_sha256": sha}))
    result = view.project_weekend(feed.read_dashboard_projection(repository["root"]))
    held = next(r for r in result["matches"] if r["id"] == repository["rows"][0]["fixture_key"])
    assert held["predictionStatus"] == "prediction_conflict" and held["prediction"] is None


def test_candidate_is_schedule_unconfirmed(repository):
    p = arrange(repository, unsaved=tuple(range(10)))
    p.official.schedule.loc[p.official.schedule.match_date.eq("2026-10-24"), "status"] = "candidate"
    result = view.project_weekend(p)
    assert all(r["predictionStatus"] == "schedule_unconfirmed" for r in result["matches"][:5])


def test_postponed_outside_weekend_is_warned_without_using_old_date(repository):
    arrange(repository)
    repository["current_rows"][0]["match_date"] = "2026-10-27"
    sha=publish(repository["current_dir"], repository["current_rows"], observed="2026-10-23T00:00:00Z",version="ongoing-v2")
    (repository["root"]/feed.ONGOING_PATH/"latest.json").write_text(json.dumps({"revision_id":repository["current_id"],"manifest_sha256":sha}))
    result=view.project_weekend(feed.read_dashboard_projection(repository["root"]))
    key=repository["rows"][0]["fixture_key"]
    assert len(result["matches"])==9 and result["excludedSavedFixtureIds"]==[key]
    assert key not in {r["id"] for r in result["matches"]}


def test_all_weekends_completed_is_empty_not_fabricated(repository):
    p=arrange(repository)
    p.official.schedule.drop(p.official.schedule.index, inplace=True)
    result=view.project_weekend(p)
    assert result["period"] is None and result["matches"]==[]


@pytest.mark.parametrize("change", [
    lambda p: p["matches"].append(deepcopy(p["matches"][0])),
    lambda p: p["matches"][0].update(kickoffAt="2026-10-31T19:00:00+09:00"),
    lambda p: p["matches"][0].update(predictionStatus="not_saved"),
    lambda p: p["matches"][0]["prediction"].update(source="regenerated"),
    lambda p: p["matches"][0]["prediction"]["probabilities"].update(home=101),
    lambda p: p["matches"][0]["prediction"].update(probabilities={"home":40,"draw":20,"away":40}),
    lambda p: p["matches"][0].update(warning="arbitrary"),
    lambda p: p["matches"].reverse(),
    lambda p: p["model"].update(version="NN_v2"),
    lambda p: p.update(baseFeedSha256="0"*64),
    lambda p: p.update(sourceRevision="not-a-revision"),
    lambda p: p.update(research={}),
    lambda p: p.update(period=["2026-10-23", "2026-10-25"]),
])
def test_reject_malformed_or_contradictory_display(repository, change):
    p = arrange(repository); result = view.project_weekend(p); change(result)
    with pytest.raises((ValueError, TypeError)): view.validate_weekend(result, base=p.payload)


def test_partial_date_batch_still_rejected(repository):
    with pytest.raises(ValueError, match="Partial saved"):
        arrange(repository, unsaved=(0,))


def test_wrong_model_revision_still_rejected(repository):
    arrange(repository)
    repository["predictions"][0]["champion_a_model_version"] = "wrong"
    save_predictions(repository)
    with pytest.raises(ValueError, match="Champion version"):
        feed.read_dashboard_projection(repository["root"])


def test_missing_official_identity_is_not_silently_dropped(repository):
    p = arrange(repository)
    p.official.schedule.loc[0, "home_team_id"] = "unknown"
    with pytest.raises(KeyError): view.project_weekend(p)


def test_server_sidecar_must_bind_to_exact_base_before_binding_socket(repository):
    p = arrange(repository); result = view.project_weekend(p)
    result["baseFeedSha256"] = "0" * 64
    with pytest.raises(ValueError, match="base feed"):
        create_server(p.payload, port=0, weekend=result)


def test_live_batch_formats_not_enabled_by_display_reader(tmp_path):
    runtime = tmp_path / "runtime"; (runtime / "batches" / "weekend-v2-unapproved").mkdir(parents=True)
    with pytest.raises(ValueError, match="Unsupported"):
        view.read_saved_daily_projection(tmp_path, runtime)


def daily_store(repo, tmp_path):
    arrange(repo, unsaved=tuple(range(5, 10)))
    runtime = tmp_path / "synthetic-runtime"
    batch = runtime / "batches" / ("b" * 64)
    batch.mkdir(parents=True)
    records = [{**{k:r[k] for k in feed.PROJECTION_COLUMNS}, "model_version":feed.CHAMPION_VERSION}
               for r in repo["predictions"]]
    bindings = [{**r, "prediction_artifact":feed.CHAMPION_PREDICTION_ARTIFACT,
                 "model_version":feed.CHAMPION_VERSION} for r in repo["bindings"]]
    bodies = {"predictions.csv":csv_bytes(records, feed.CHAMPION_COLUMNS),
              "bindings.csv":csv_bytes(bindings, feed.BINDING_COLUMNS)}
    for name, body in bodies.items(): (batch/name).write_bytes(body)
    (batch/"manifest.json").write_text(json.dumps({n:feed.sha(b) for n,b in bodies.items()}))
    shutil.copytree(repo["root"]/feed.ONGOING_PATH, runtime/"official")
    return runtime, batch


def test_deployed_daily_reader_contract_and_probability_identity(repository, tmp_path):
    runtime, _ = daily_store(repository, tmp_path)
    p = view.read_saved_daily_projection(repository["root"], runtime)
    rows = view.project_weekend(p)["matches"]
    assert len(rows) == 10 and sum(r["prediction"] is not None for r in rows) == 5
    assert rows[0]["prediction"]["probabilities"]["home"] == float(repository["predictions"][0]["a_p_home"])*100


@pytest.mark.parametrize("fault", ["SHA", "duplicate", "binding", "new-format"])
def test_daily_store_refuses_tamper_duplicates_and_unapproved_formats(repository, tmp_path, fault):
    runtime, batch = daily_store(repository, tmp_path)
    if fault == "SHA":
        (batch/"predictions.csv").write_bytes((batch/"predictions.csv").read_bytes()+b"\n")
    elif fault == "duplicate":
        shutil.copytree(batch, batch.with_name("c"*64))
    elif fault == "new-format":
        (batch/"manifest.json").write_text('{"format_version":"champion-weekend-v2-source-v1"}')
    else:
        body=(batch/"bindings.csv").read_bytes().replace(b"team_0001",b"team_9999")
        (batch/"bindings.csv").write_bytes(body)
        manifest=json.loads((batch/"manifest.json").read_text());manifest["bindings.csv"]=feed.sha(body)
        (batch/"manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError): view.read_saved_daily_projection(repository["root"], runtime)


def test_sidecar_api_is_optional_and_frozen_without_changing_v1(repository):
    p=arrange(repository); sidecar=view.project_weekend(p)
    server=create_server(p.payload, port=0, weekend=sidecar)
    try:
        handler=object.__new__(server.RequestHandlerClass);handler.path="/api/weekend"
        sent=[];handler._send=lambda body,mime:sent.append((body,mime))
        sidecar["matches"].clear()  # Published server snapshot remains immutable.
        handler.do_GET()
        assert len(json.loads(sent[0][0])["matches"])==10
        handler.path="/api/dashboard";handler.do_GET()
        assert json.loads(sent[1][0])==p.payload
    finally: server.server_close()


def test_python_and_browser_share_exact_numeric_binding(repository):
    p=arrange(repository);sidecar=view.project_weekend(p)
    code="""import fs from 'node:fs';import {verifyWeekendBinding} from './web/weekend-data.js';
const [base,view]=JSON.parse(fs.readFileSync(0,'utf8'));await verifyWeekendBinding(view,base);console.log('verified');"""
    r=subprocess.run(["node","--input-type=module","-e",code],input=json.dumps([p.payload,sidecar]),
                     text=True,encoding="utf-8",capture_output=True,timeout=10,check=True)
    assert r.stdout.strip()=="verified"


def test_sidecar_cli_requires_explicit_paired_v1_file(tmp_path):
    with pytest.raises(SystemExit) as e:
        server_main(["--weekend-data",str(tmp_path/"not-read.json")])
    assert e.value.code==2


def test_sidecar_cli_rejects_invalid_pair_before_starting_server(repository,tmp_path):
    p=arrange(repository);v=view.project_weekend(p);v["baseFeedSha256"]="0"*64
    base,sidecar=tmp_path/"base.json",tmp_path/"weekend.json"
    base.write_text(json.dumps(p.payload));sidecar.write_text(json.dumps(v))
    assert server_main(["--port","0","--data",str(base),"--weekend-data",str(sidecar)])==2
