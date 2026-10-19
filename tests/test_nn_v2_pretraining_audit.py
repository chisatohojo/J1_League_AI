"""Synthetic-only checks for the pretraining auditor; no fitting permitted."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pandas as pd
import pytest

from src.features import nn_research_timing as t
from src.modeling import nn_v2_pretraining_audit as a
from src.modeling import nn_v2_offsets as o
from src.modeling import nn_residual_v2 as n
from src.collect.teams import TeamAlias, TeamMaster, UnknownTeamError


def history():
    rows = []
    for year in range(2015, 2026):
        for j in range(6):
            hg, ag = [(0, 1), (1, 1), (2, 0)][j % 3]
            rows.append(dict(match_id=f"synthetic-{year}-{j}", season=year,
                match_date=pd.Timestamp(year, 2, j+1), kickoff_time="19:00",
                home_team_id="synthetic-home", away_team_id="synthetic-away",
                home_score=hg, away_score=ag, result=j % 3))
    return pd.DataFrame(rows)


def test_detail_names_use_existing_official_namespace_without_fallback():
    aliases = []
    for club, short, full in (("team_0001", "SYN-H", "Synthetic Home"),
                              ("team_0002", "SYN-A", "Synthetic Away")):
        for name, source in ((short, "jleague_data_site"), (full, "jleague_official")):
            aliases.append(TeamAlias(club, full, name, source, None, None, ""))
    master = TeamMaster(aliases)
    row = SimpleNamespace(match_id="synthetic", match_date=pd.Timestamp(2020, 1, 1),
                          home_team_id="team_0001", away_team_id="team_0002")
    a.verify_detail_team_ids(master, {"home_team": "Synthetic Home", "away_team": "Synthetic Away"}, row)
    with pytest.raises(ValueError):
        a.verify_detail_team_ids(master, {"home_team": "Synthetic Away", "away_team": "Synthetic Home"}, row)
    with pytest.raises(UnknownTeamError):
        a.verify_detail_team_ids(master, {"home_team": "SYN-H", "away_team": "SYN-A"}, row)


def test_trace_independent_replay_and_dependency_proof():
    raw = history(); before = raw.copy(deep=True); trace = []
    with a.no_learning() as calls:
        frame = t.build_event_features(raw, trace=trace)
        result = a.audit_trace(frame, trace)
    assert len(result) == 66 and calls == []
    assert result[0]["history_count"] == 0
    assert result[-1]["history_count"] == 65
    assert all(r["independent_9_feature_match"] for r in result)
    pd.testing.assert_frame_equal(raw, before)


@pytest.mark.parametrize("edit", ["missing", "duplicate", "early", "unknown", "feature"])
def test_corrupted_trace_or_features_stops(edit):
    trace = []; frame = t.build_event_features(history(), trace=trace)
    if edit == "missing": trace.pop()
    if edit == "duplicate": trace.insert(1, deepcopy(trace[0]))
    if edit == "early": trace[0] = deepcopy(trace[1])
    if edit == "unknown": trace[0]["match_id"] = "not-in-history"
    if edit == "feature": frame.loc[0, "elo_diff"] += 1
    with pytest.raises(ValueError): a.audit_trace(frame, trace)


def test_reduced_population_is_rejected():
    frame = o.prepare_history(history())
    with a.no_learning(), pytest.raises(ValueError, match="population"):
        a.split_plan(frame)


def test_complete_synthetic_id_splits_and_form_join_without_fit():
    rows = []
    for year, count in a.COUNTS.items():
        for j in range(count):
            hg, ag = [(0, 1), (1, 1), (2, 0)][j % 3]
            rows.append(dict(match_id=f"synthetic-{year}-{j:03d}", season=year,
                match_date=pd.Timestamp(year, 1, 1)+pd.Timedelta(days=j//2), kickoff_time="19:00",
                home_team_id=f"synthetic-home-{j%2}", away_team_id=f"synthetic-away-{j%2}",
                home_score=hg, away_score=ag, result=j % 3))
    with a.no_learning() as calls:
        frame = o.prepare_history(pd.DataFrame(rows))
        plan = a.split_plan(frame)
    assert not calls and len(plan["folds"]) == 9
    assert len(plan["seed_ids"]) == 612 and len(plan["residual_scaler_fit_ids"]) == 2976
    assert len(plan["final_baseline_fit_ids"]) == 3588
    for fold in plan["folds"]:
        assert set(fold["training_ids"]).isdisjoint(fold["target_ids"])
        assert all(f"-{fold['target_year']}-" in mid for mid in fold["target_ids"])
        assert fold["offset_state"] == "NOT_GENERATED"


@pytest.mark.parametrize("call", [lambda: o.generate_crossfit_offsets(None),
                                  lambda: o.fit_final_baseline(None),
                                  lambda: n.initial_parameters()])
def test_no_learning_tripwire_fails_closed(call):
    with pytest.raises(RuntimeError), a.no_learning():
        call()


def schedule():
    rows = []
    start = datetime(2030, 1, 1)
    for round_ in range(1, 39):
        for j in range(10):
            rows.append(dict(fixture_key=f"synthetic-{round_}-{j}", round=str(round_),
                match_date=(start+timedelta(days=round_*7)).date().isoformat(),
                kickoff_time="19:00", status="scheduled", home_club=f"team-{j}",
                away_club=f"team-{j+10}", match_page_id="", match_id="",
                competition_key="j1_2026_2027"))
    return pd.DataFrame(rows)


def test_capacity_pending_ids_not_fabricated_or_enrolled():
    frame = schedule(); before = frame.copy(deep=True)
    result = a.future_capacity(frame, datetime(2029, 12, 1, tzinfo=timezone.utc))
    assert result["provisional_fixtures"] == 200 and result["mapping_pending"] == 200
    assert result["official_identity_present"] == 0 and result["T0"] is None
    assert result["enrolled"] is False
    pd.testing.assert_frame_equal(frame, before)


def test_insufficient_unstarted_rounds_hold():
    frame = schedule()
    frame.loc[frame["round"].astype(int).le(19), "status"] = "completed"
    assert a.future_capacity(frame, datetime(2029, 12, 1, tzinfo=timezone.utc))["status"] == "HOLD"


def test_future_date_with_unannounced_time_is_capacity_only():
    frame = schedule(); frame["kickoff_time"] = ""
    result = a.future_capacity(frame, datetime(2029, 12, 1, tzinfo=timezone.utc))
    assert result["provisional_fixtures"] == result["unknown_kickoff_count"] == 200
    assert result["first_known_kickoff_jst"] is None
    assert result["enrolled"] is False and result["T0"] is None


@pytest.mark.parametrize("edit", ["duplicate", "unknown_time", "missing", "wrong_competition"])
def test_capacity_bad_identity_or_time_stops(edit):
    frame = schedule()
    if edit == "duplicate": frame.loc[1, "fixture_key"] = frame.loc[0, "fixture_key"]
    if edit == "unknown_time": frame.loc[0, "kickoff_time"] = "TBD"
    if edit == "missing": frame = frame.iloc[:-1]
    if edit == "wrong_competition": frame.loc[0, "competition_key"] = "j2"
    with pytest.raises(ValueError):
        a.future_capacity(frame, datetime(2029, 12, 1, tzinfo=timezone.utc))
