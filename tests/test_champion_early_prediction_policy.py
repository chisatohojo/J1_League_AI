"""Synthetic calendars and Elo states only; never a real estimator or store."""
from dataclasses import replace
from datetime import datetime, timedelta
from itertools import product
from pathlib import Path

import pytest

from research.champion_early_prediction_policy import Fixture, assess, fixed_inputs_unchanged, SCOPE
from src.features.elo import EloRatings

def dt(value):
    return datetime.fromisoformat(value)


TARGET = Fixture("synthetic:target", "A", "B", "2026-10-25", dt("2026-10-25T05:00:00+00:00"))
FREEZE = dt("2026-10-24T01:00:00+00:00")
SOURCE = dt("2026-10-24T00:00:00+00:00")
CONTEXT = dict(freeze=FREEZE, source_observed_at=SOURCE, coverage_verified=True,
               source_evidence_verified=True, fixed_history_verified=True,
               source_revision="a"*64, source_manifest_sha="b"*64, model_bundle_sha="c"*64)


def completed(identity, home, away, day="2026-10-21", result=2):
    return Fixture(identity, home, away, day, dt(day+"T05:00:00+00:00"),
                   "completed", result_acquired_at=dt(day+"T08:00:00+00:00"),
                   result=result, witness_sha="d"*64)


def pending(identity="synthetic:pending", home="C", away="D", **kwargs):
    return Fixture(identity, home, away, "2026-10-24", dt("2026-10-24T05:00:00+00:00"), **kwargs)


BASE = (completed("synthetic:A-C", "A", "C"), completed("synthetic:B-D", "B", "D"))


def run(history=BASE, target=TARGET, **changes):
    return assess(target, history, **(CONTEXT | changes))


def test_both_target_teams_free_of_intervening_games():
    value = run()
    assert value.candidate and value.scope == SCOPE
    assert set(value.required_ids) == {f.identity for f in BASE}
    assert not value.history_admission and not value.execution_authorized


@pytest.mark.parametrize("home,away", [("A","E"),("E","B")])
def test_target_team_intervening_match_holds(home, away):
    value = run(BASE+(pending(home=home,away=away),))
    assert not value.candidate and "REQUIRED_RESULT_NOT_CONFIRMED" in value.reasons
    assert value.next_intervening_match_date == "2026-10-24"


def test_other_teams_future_game_is_not_needed_for_target_input():
    value=run(BASE+(pending(),))
    assert value.candidate and value.unrelated_unfinished_ids == ("synthetic:pending",)
    assert value.next_intervening_match_date is None


def test_transitive_prior_opponent_dependency_rejects_naive_team_only_gate():
    unknown=Fixture("synthetic:C-E", "C", "E", "2026-10-20", dt("2026-10-20T05:00:00+00:00"))
    value=run((unknown,*BASE))
    assert not value.candidate and unknown.identity in value.required_ids
    # A played C after C-E: different C-E outcomes change A despite no direct A game missing.
    states=[]
    for result in (0,2):
        elo=EloRatings(["A","B","C","D","E"],k_factor=30,home_advantage=175)
        elo.update("C","E",result);elo.update("A","C",2);elo.update("B","D",2)
        states.append(elo.ratings["A"]-elo.ratings["B"])
    assert states[0] != states[1]


def test_all_243_other_team_result_combinations_leave_target_input_identical():
    pairs=[("C","D"),("E","F"),("G","H"),("I","J"),("K","L")]
    differences=set()
    for outcomes in product((0,1,2),repeat=5):
        elo=EloRatings(list("ABCDEFGHIJKL"),k_factor=30,home_advantage=175)
        for f in BASE:elo.update(f.home,f.away,f.result)
        original=elo.ratings["A"]-elo.ratings["B"]
        for (home,away),result in zip(pairs,outcomes):elo.update(home,away,result)
        assert elo.ratings["A"]-elo.ratings["B"] == original
        differences.add(original)
    assert len(differences)==1


@pytest.mark.parametrize("features", [("elo_diff","rank"),("elo_diff","form"),("rank",),()])
def test_unknown_or_league_global_feature_never_allowed(features):
    value=run(BASE+(pending(),), feature_contract=features)
    assert not value.candidate and "UNKNOWN_FEATURE_DEPENDENCY" in value.reasons


@pytest.mark.parametrize("status", ["postponed","cancelled","unknown"])
def test_unverified_postponement_or_cancellation_has_unknown_order(status):
    value=run(BASE+(replace(pending(),status=status,kickoff=None),))
    assert not value.candidate and "CALENDAR_ORDER_UNKNOWN" in value.reasons


def test_explicit_confirmed_non_play_is_excluded_without_guessing_result():
    value=run(BASE+(replace(pending(home="A",away="E"),status="cancelled",cancellation_verified=True),))
    assert value.candidate


def test_cup_is_outside_frozen_elo_scope_not_proof_of_physical_rest():
    f=pending(home="A",away="E",competition="cup")
    value=run(BASE+(f,))
    assert value.candidate and value.excluded_non_model_ids == (f.identity,)
    assert not run(BASE+(f,),feature_contract=("elo_diff","rest_days")).candidate


def test_unknown_competition_scope_holds():
    assert not run(BASE+(pending(competition="unreviewed"),)).candidate


@pytest.mark.parametrize("source", ["2026-10-22T23:59:59+00:00","2026-10-24T01:00:00.000001+00:00"])
def test_stale_or_future_source_holds(source):
    assert "SOURCE_FUTURE_OR_STALE" in run(source_observed_at=dt(source)).reasons


@pytest.mark.parametrize("freeze", ["2026-10-25T05:00:00+00:00","2026-10-25T05:00:00.000001+00:00"])
def test_equal_or_after_kickoff_holds(freeze):
    assert "TARGET_KICKOFF_ELAPSED" in run(freeze=dt(freeze)).reasons


def test_duplicate_fixture_and_same_day_target_appearance_refused():
    assert "DUPLICATE_OR_MISSING_ID" in run(BASE+(BASE[0],)).reasons
    other=replace(pending(home="A",away="E"),day=TARGET.day,kickoff=TARGET.kickoff-timedelta(hours=2))
    assert "TEAM_MULTIPLE_MATCHES_SAME_JST_DATE" in run(BASE+(other,)).reasons


def test_JST_day_horizon_not_UTC_calendar_days():
    # Friday 23:30 UTC is Saturday morning JST; Monday afternoon is two JST days away.
    monday=replace(TARGET,day="2026-10-26",kickoff=dt("2026-10-26T05:00:00+00:00"))
    assert run(target=monday,freeze=dt("2026-10-23T23:30:00+00:00"),source_observed_at=dt("2026-10-23T23:00:00+00:00"),prediction_horizon_days=2).candidate
    assert "OUTSIDE_JST_DAY_HORIZON" in run(target=monday,prediction_horizon_days=1).reasons


@pytest.mark.parametrize("days", [-1,15,True,1.5])
def test_invalid_horizon_never_waives_dependency(days):
    assert not run(prediction_horizon_days=days).candidate


def test_longer_horizon_does_not_waive_required_result():
    assert not run(BASE+(pending(home="A",away="E"),),prediction_horizon_days=14).candidate


@pytest.mark.parametrize("flag", ["coverage_verified","source_evidence_verified","fixed_history_verified"])
def test_missing_prerequisite_is_not_inferred_from_available_rows(flag):
    assert not run(**{flag:False}).candidate


@pytest.mark.parametrize("field,value", [("source_revision",""),("model_bundle_sha","not-a-pin"),("source_manifest_sha","F"*64)])
def test_source_and_model_pins_required(field,value):
    assert not run(**{field:value}).candidate


@pytest.mark.parametrize("change", [dict(result_acquired_at=None),dict(result_acquired_at=dt("2026-10-25T00:00:00+00:00")),dict(witness_sha=None),dict(result=None),dict(result=True)])
def test_missing_or_late_required_result_evidence(change):
    assert not run((replace(BASE[0],**change),BASE[1])).candidate


def test_unrelated_unfinished_history_safe_only_when_not_in_reverse_closure():
    older=replace(pending(home="X",away="Y"),day="2026-10-20",kickoff=dt("2026-10-20T05:00:00+00:00"))
    value=run((older,*BASE))
    assert value.candidate and older.identity in value.unrelated_unfinished_ids
    connecting=completed("synthetic:A-X","A","X",day="2026-10-22")
    assert not run((older,*BASE,connecting)).candidate


def test_unrelated_completed_source_time_contradiction_is_not_hidden():
    bad=completed("synthetic:X-Y","X","Y",day="2026-10-24")
    assert not run(BASE+(bad,)).candidate


def test_fixed_schedule_result_and_revision_change_detected_no_reprediction():
    original=run()
    versions=[run(target=replace(TARGET,kickoff=TARGET.kickoff+timedelta(minutes=1))),
              run((replace(BASE[0],result=0),BASE[1])),run(source_revision="e"*64)]
    for changed in versions:
        assert not fixed_inputs_unchanged(original,changed)
        assert not changed.execution_authorized and not changed.history_admission
    assert fixed_inputs_unchanged(original,run(tuple(reversed(BASE))))


def test_unknown_timezone_date_and_target_identity_hold():
    assert not run(freeze=FREEZE.replace(tzinfo=None)).candidate
    assert not run(target=replace(TARGET,day="2026-10-24")).candidate
    assert not run(target=replace(TARGET,identity_verified=False)).candidate


def test_no_production_import_or_IO_entrypoint():
    import ast
    import research.champion_early_prediction_policy as policy
    tree=ast.parse(Path(policy.__file__).read_text(encoding="utf-8"))
    imports=[ast.unparse(n) for n in ast.walk(tree) if isinstance(n,(ast.Import,ast.ImportFrom))]
    assert not any(any(token in s for token in ["modeling","collect","socket","urllib","subprocess","joblib","sklearn"]) for s in imports)
    assert not any(isinstance(n,ast.Name) and n.id in {"open","exec","eval","predict","fit"} for n in ast.walk(tree))
