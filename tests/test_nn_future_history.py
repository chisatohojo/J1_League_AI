"""Synthetic future-history contracts; no fitted estimator or real predictions."""
from dataclasses import asdict, replace
from datetime import datetime, timedelta
from pathlib import Path
import builtins

import numpy as np
import pandas as pd
import pytest

from src.features import nn_future_history as h
from src.features.nn_research_timing import build_event_features

A, B, C, D = "team_0030", "team_0010", "team_0031", "team_0032"
ROSTER = (A, B, C, D)


def event(mid="32900", day="2026-02-01", home=A, away=B, hg=1, ag=1, **changes):
    e = h.ResultEvent("jleague_data_site_sfms02:" + mid, mid, "j1_hyakunen_2026",
                      home, away, day + "T15:00:00+09:00", day,
                      (datetime.fromisoformat(day) + timedelta(days=1)).date().isoformat() + "T00:00:00+09:00",
                      hg, ag, day + "T13:00:00+00:00", "a" * 64, "b" * 64,
                      "https://saved.example/" + mid, "synthetic-revision", "ordinary_reviewed")
    return replace(e, **changes)


def fixture(e):
    return h.Fixture(e.identity, e.home_team_id, e.away_team_id, e.original_kickoff, "completed")


def query(day="2026-02-02", home=A, away=B, **changes):
    return replace(h.Query("probe", home, away, day + "T15:00:00+09:00",
                           day + "T00:00:00+09:00", day + "T09:00:00+09:00"), **changes)


def run(events=(), queries=None, **changes):
    queries = [query()] if queries is None else queries
    kwargs = dict(team_ids=ROSTER, universe=[fixture(e) for e in events],
                  covered_through=max(q.history_cutoff for q in queries),
                  timing_admissions=changes.get("timing_admissions"))
    if kwargs["timing_admissions"] is None:
        kwargs["timing_admissions"] = {e.identity: h.event_sha(e) for e in events}
    kwargs.update(changes)
    return h.replay(events, queries, **kwargs)


def test_draw_uses_regulation_points_and_fixed_elo_parameters():
    rows, trace = run([event()])
    row = rows[0]
    expected_delta = 30 * (.5 - 1 / (1 + 10 ** (-175 / 400)))
    assert row["elo_diff"] == pytest.approx(2 * expected_delta)
    assert list(row) == ["identity", *h.FEATURES]
    assert row["home_last5_points"] == row["away_last5_points"] == 1
    assert row["home_last5_goals_for"] == row["away_last5_goals_against"] == 1
    assert trace[0]["source_fetched_at_utc"] == "2026-02-01T13:00:00+00:00"


def test_ongoing_result_and_cross_competition_cross_year_continuity():
    e1 = event(hg=2, ag=0, day="2026-06-01")
    e2 = event("010101", "2027-01-01", B, A, 0, 3, competition="j1_2026_2027",
               identity="j1_2026_2027:synthetic:b:a")
    row = run([e1, e2], [query("2027-01-02")])[0][0]
    assert row["home_last5_matches_available"] == 2
    assert row["home_last5_points"] == 6
    assert row["home_last5_goals_for"] == 5
    assert row["elo_diff"] > 0


def test_last_five_shared_home_and_away_history():
    games = [event(str(32900+i), f"2026-02-{i+1:02d}", A if i % 2 == 0 else B,
                   B if i % 2 == 0 else A, i+1, 0) for i in range(7)]
    rows, trace = run(games, [query("2026-02-08")])
    row = rows[0]
    assert row["home_last5_matches_available"] == row["away_last5_matches_available"] == 5
    assert row["home_last5_points"] == 9
    assert row["home_last5_goals_for"] == 3+5+7
    assert row["home_last5_goals_against"] == 4+6
    assert trace[-1]["home_form_ids"] == [e.identity for e in games[-5:]]


def test_same_day_and_future_result_changes_do_not_affect_features():
    prior, today, future = event("1"), event("2", "2026-02-02", C, D), event("3", "2026-02-03")
    original = run([prior, today, future])[0]
    assert run([prior, replace(today, home_score_90=99), replace(future, away_score_90=88)])[0] == original


def test_morning_acquisition_is_retained_separately_from_midnight_cutoff():
    e = event(source_fetched_at_utc="2026-02-01T23:00:00+00:00")  # Feb 2 08:00 JST
    rows, trace = run([e])
    assert rows[0]["home_last5_matches_available"] == 1
    assert trace[0]["source_fetched_at_utc"] == e.source_fetched_at_utc
    assert trace[-1]["history_cutoff"] == "2026-02-02T00:00:00+09:00"
    with pytest.raises(ValueError, match="not_yet_acquired"):
        run([e], [query(knowledge_at="2026-02-02T07:00:00+09:00")])


def test_later_query_cannot_reuse_results_unknown_at_its_knowledge_clock():
    e = event(source_fetched_at_utc="2026-02-01T23:00:00+00:00")
    with pytest.raises(ValueError, match="not_yet_acquired"):
        run([e], [query(identity="a"), query(identity="z", knowledge_at="2026-02-02T07:00:00+09:00")])


def test_cold_start_is_explicit_but_missing_history_is_rejected():
    row = run()[0][0]
    assert all(row[k] == 0 for k in h.FEATURES)
    with pytest.raises(ValueError, match="missing_or_extra_completed_history"):
        run(universe=[fixture(event())])
    with pytest.raises(ValueError, match="incomplete_history_coverage"):
        run(covered_through="2026-02-01T00:00:00+09:00")


@pytest.mark.parametrize("status", ["scheduled", "candidate", "suspended"])
def test_prior_unfinished_fixture_stops_and_future_schedule_has_no_result(status):
    f = replace(fixture(event()), status=status)
    with pytest.raises(ValueError, match="unresolved_prior_fixture"):
        run(universe=[f])
    f = replace(f, original_kickoff="2026-02-03T15:00:00+09:00")
    rows, trace = run(universe=[f])
    assert rows[0]["home_last5_matches_available"] == 0
    assert all(t["event"] != "result_applied" for t in trace)
    with pytest.raises(ValueError, match="missing_or_extra_completed_history"):
        run([event()], universe=[f])


@pytest.mark.parametrize("changes,error", [
    ({"timing_class": "unknown"}, "unknown_timing_exception"),
    ({"source_fetched_at_utc": None}, "missing_source_witness"),
    ({"source_fetched_at_utc": "2026-02-01T00:00:00+00:00"}, "witness_clock"),
    ({"raw_sha256": None}, "missing_witness_sha"),
    ({"metadata_sha256": "bad"}, "missing_witness_sha"),
    ({"home_score_90": float("nan")}, "regulation_scores_required"),
    ({"home_score_90": True}, "regulation_scores_required"),
    ({"competition": "AFC"}, "competition_out_of_scope"),
    ({"competition": "Cup"}, "competition_out_of_scope"),
    ({"competition": "ST2"}, "competition_out_of_scope"),
    ({"home_team_id": "team_0030 "}, "TeamMaster_ID_mismatch"),
    ({"away_team_id": A}, "TeamMaster_ID_mismatch"),
    ({"result_effective_at": "2026-02-01T00:00:00+09:00"}, "result_boundary"),
    ({"result_effective_at": "2026-02-02T03:00:00+09:00"}, "not_jst_midnight"),
    ({"original_kickoff": "2026-01-31T15:00:00+09:00"}, "unreviewed_cross_date"),
    ({"binding_sha256": h.BINDING_SHA}, "binding_expansion_forbidden"),
])
def test_invalid_evidence_fails_closed(changes, error):
    with pytest.raises(ValueError, match=error):
        # Invalid nonfinite bytes cannot even be hashed into an admission.
        e = event(**changes)
        if error == "regulation_scores_required":
            run([e], timing_admissions={e.identity: "invalid"})
        else:
            run([e])


def test_timing_admission_is_not_implied_by_a_valid_final_result():
    e = event()
    with pytest.raises(ValueError, match="timing_admission"):
        run([e], timing_admissions={})
    with pytest.raises(ValueError, match="timing_admission"):
        run([replace(e, home_score_90=4)], timing_admissions={e.identity: h.event_sha(e)})


def test_duplicate_hyakunen_identity_and_same_day_club_anomaly():
    with pytest.raises(ValueError, match="duplicate_universe_identity"):
        run([event(), event()])
    with pytest.raises(ValueError, match="same_day_club_collision"):
        run([event("1"), event("2", home=A, away=C)])


def test_exact_200_hyakunen_identities_are_kept_and_duplicate_rejected():
    games = [event(str(33000+i), (datetime(2026, 1, 1)+timedelta(days=i)).date().isoformat()) for i in range(200)]
    row = run(games, [query("2026-07-20")])[0][0]
    assert row["home_last5_matches_available"] == 5
    with pytest.raises(ValueError, match="duplicate_universe_identity"):
        run(games[:-1]+[games[0]], [query("2026-07-20")])


@pytest.mark.parametrize("key", ["pk_winner", "home_pk_score", "home_extra_time_score", "result"])
def test_non_regulation_fields_cannot_enter_result_event(key):
    with pytest.raises(TypeError):
        h.ResultEvent(**asdict(event()), **{key: 99})


def test_query_cannot_receive_a_future_score():
    with pytest.raises(TypeError):
        h.Query(**asdict(query()), home_score_90=2)


def test_reviewed_resumption_has_original_feature_and_delayed_result_event():
    e = event(original_kickoff="2026-01-01T15:00:00+09:00", timing_class="resumption_reviewed")
    before, trace = run([e], [query("2026-01-01"), query("2026-02-01", identity="mid"),
                             query("2026-02-02", identity="after")])
    assert [row["home_last5_matches_available"] for row in before] == [0, 0, 1]
    assert len([t for t in trace if t["event"] == "result_applied"]) == 1


def legacy_source():
    def row(mid, day, hg=1, ag=0, away=B):
        return dict(match_id=mid, match_date=pd.Timestamp(day), season=int(day[:4]), round=28,
                    home_team_id=A, away_team_id=away, home_score=hg, away_score=ag,
                    result=2 if hg > ag else 0 if hg < ag else 1, kickoff_time="19:00")
    return pd.DataFrame([row("1", "2015-12-01"), row("2", "2016-01-01", 0, 1),
                         row("3", "2024-08-23", away=C), row("30700", "2024-11-22", 1, 1),
                         row("4", "2024-09-01", 0, 1, D), row("5", "2024-11-22", away=C),
                         row("6", "2024-11-23"), row("7", "2025-01-01")])


def test_legacy_feature_vectors_and_30700_chronology_match_frozen_generator():
    source = legacy_source()
    sealed = build_event_features(source)
    events = h.legacy_events(source)
    queries = [h.Query(r.fixture_identity, r.home_team_id, r.away_team_id, r.feature_timestamp,
                       r.history_cutoff_timestamp, r.history_cutoff_timestamp) for r in sealed.itertuples()]
    rows, _ = run(events, queries)
    by_id = {r["identity"]: r for r in rows}
    for r in sealed.itertuples():
        np.testing.assert_allclose([by_id[r.fixture_identity][c] for c in h.FEATURES],
                                   [getattr(r, c) for c in h.FEATURES], rtol=0, atol=1e-10)
    e = next(e for e in events if e.match_id == "30700")
    assert e.original_kickoff == "2024-08-24T19:03:00+09:00"
    assert e.result_effective_at == "2024-11-23T00:00:00+09:00"
    with pytest.raises(ValueError, match="30700_identity"):
        run([replace(e, home_score_90=2)], [query("2025-01-01")])


def test_four_bindings_cannot_be_admitted_by_a_sha_string_only():
    e = event("101101", competition="j1_2026_2027", identity="j1_2026_2027:chiba:nagasaki",
              binding_sha256=h.BINDING_SHA)
    with pytest.raises(ValueError, match="sealed_binding_required"):
        run([e])


def test_phase2_5a_sealed_binding_tamper_detected_before_any_replay():
    payload = (Path(__file__).parents[1] / "research/nn_v2/phase2_5A/binding-manifest.json").read_bytes()
    import hashlib
    assert hashlib.sha256(payload).hexdigest() == h.BINDING_SHA
    bad = h.BindingInputs(payload + b" ", (), {}, {})
    with pytest.raises(ValueError, match="binding_sha_mismatch"):
        run(binding_inputs=bad)


def test_adapter_never_fits_scaler_or_writes_operational_elo(monkeypatch):
    from sklearn.preprocessing import StandardScaler
    def forbidden(*args, **kwargs):
        raise AssertionError("Forbidden IO or scaler fit")
    for method in ("fit", "fit_transform", "partial_fit"):
        monkeypatch.setattr(StandardScaler, method, forbidden)
    monkeypatch.setattr(builtins, "open", forbidden)
    monkeypatch.setattr(Path, "write_text", forbidden)
    monkeypatch.setattr(Path, "write_bytes", forbidden)
    assert run([event()])[0][0]["home_last5_points"] == 1


@pytest.mark.parametrize("changes,error", [
    ({"history_cutoff": "2026-02-02T01:00:00+09:00"}, "not_jst_midnight"),
    ({"knowledge_at": "2026-02-02T15:00:00+09:00"}, "query_clock"),
    ({"knowledge_at": "2026-02-01T23:59:00+09:00"}, "query_clock"),
    ({"kickoff": "2026-02-02T15:00:00"}, "naive_clock"),
    ({"home_team_id": "missing"}, "TeamMaster_ID_mismatch"),
])
def test_query_clock_and_identity_are_validated_before_features(changes, error):
    with pytest.raises(ValueError, match=error):
        run([event()], [query(**changes)])


def test_duplicate_queries_and_forged_universe_cannot_emit_features():
    with pytest.raises(ValueError, match="duplicate_query_identity"):
        run([event()], [query(), query()])
    e = event()
    with pytest.raises(ValueError, match="fixture_event_identity_mismatch"):
        run([e], universe=[replace(fixture(e), home_team_id=C)])


def test_input_events_and_supplied_universe_are_not_mutated():
    e = event(); u = [fixture(e)]; before = list(u)
    run([e], universe=u)
    assert u == before and e == event()


def test_read_only_audit_detects_source_replacement(tmp_path):
    from scripts.audit_nn_future_history import Reader, sha
    path = tmp_path / "witness.html"
    path.write_bytes(b"first")
    reader = Reader({str(path): sha(b"first")})
    assert reader.read(path) == b"first"
    path.write_bytes(b"replacement")
    with pytest.raises(ValueError, match="changed_since_preflight"):
        reader.read(path)


def test_audit_network_tripwire_and_create_new_reports(tmp_path):
    from scripts.audit_nn_future_history import deny_network, write
    for name in ("socket.connect", "socket.getaddrinfo", "urllib.Request"):
        with pytest.raises(RuntimeError, match="forbids network"):
            deny_network(name, ())
    deny_network("socket.gethostname", ())
    write(tmp_path, "report.json", {"network_fetches": 0})
    with pytest.raises(FileExistsError):
        write(tmp_path, "report.json", {"network_fetches": 1})
