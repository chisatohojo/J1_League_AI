"""Original-start features and delayed final results, without real model fits."""
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.features import nn_research_timing as t
from src.features.elo import EloRatings
from src.modeling import nn_research_v1 as n

U, K, C, D = "team_0030", "team_0010", "team_0031", "team_0032"


def game(mid, day, home=U, away=C, hg=2, ag=0, **extra):
    return dict(match_id=mid, match_date=pd.Timestamp(day), season=2024,
        round=28, home_team_id=home, away_team_id=away, home_score=hg, away_score=ag,
        result=2 if hg > ag else 0 if hg < ag else 1, kickoff_time="19:00", **extra)


def chronology():
    # Probe fixtures deliberately stress shared-club timing around the final
    # result day. They are synthetic, not claims about real scheduling.
    return pd.DataFrame([
        game("prior", "2024-08-23"),
        game("30700", "2024-11-22", U, K, 1, 1),
        game("between", "2024-09-01", U, D, 0, 1),
        game("probe22", "2024-11-22", U, C, 1, 0),
        game("probe23", "2024-11-23", U, K, 0, 1),
        game("probe24", "2024-11-24", U, D, 1, 1),
    ])


def test_features_are_frozen_before_original_day_not_resumption():
    source = chronology()
    before = source.copy(deep=True)
    state = n.build_features(source).set_index("match_id")
    row = state.loc["30700"]
    elo = EloRatings([U, K, C, D], k_factor=30, home_advantage=175)
    elo.update(U, C, 2)
    prior = elo.pre_match(U, K)
    assert row.elo_diff == prior.home_rating - prior.away_rating
    assert row.home_last5_matches_available == 1
    assert row.home_last5_points == 3
    assert row.home_last5_goals_for == 2
    assert row.away_last5_matches_available == 0
    assert row.feature_timestamp == "2024-08-24T19:03:00+09:00"
    assert row.history_cutoff_timestamp == "2024-08-24T00:00:00+09:00"
    assert row.recorded_source_date == "2024-11-22"
    assert row.match_date == pd.Timestamp("2024-11-22")
    assert row.final_label == row.result == 1
    pd.testing.assert_frame_equal(source, before)


def test_final_result_not_effective_until_next_day_and_applied_once():
    source = chronology()
    trace = []
    state = t.build_event_features(source, trace=trace).set_index("match_id")
    without = n.build_features(source.loc[source.match_id.ne("30700")]).set_index("match_id")
    for mid in ("between", "probe22"):
        np.testing.assert_array_equal(state.loc[mid, list(n.FEATURES)], without.loc[mid, list(n.FEATURES)])
    assert state.loc["probe23", "home_last5_matches_available"] == 4
    assert without.loc["probe23", "home_last5_matches_available"] == 3
    assert state.loc["probe23", "home_last5_points"] == without.loc["probe23", "home_last5_points"] + 1
    assert state.loc["probe23", "elo_diff"] != without.loc["probe23", "elo_diff"]
    assert [e for e in trace if e["event"] == "result_applied" and e["match_id"] == "30700"] == [
        {"event": "result_applied", "match_id": "30700", "at": "2024-11-23T00:00:00+09:00"}]
    assert len([e for e in trace if e["event"] == "features_frozen"]) == len(source)
    assert len([e for e in trace if e["event"] == "result_applied"]) == len(source)
    assert np.isfinite(state[list(n.FEATURES)].to_numpy(dtype=float)).all()


def test_intervening_and_same_original_day_results_do_not_change_special_features():
    source = chronology()
    source = pd.concat([source, pd.DataFrame([game("same_original_day", "2024-08-24", C, D)])], ignore_index=True)
    base = n.build_features(source).set_index("match_id")
    changed = source.copy(deep=True)
    for mid in ("same_original_day", "between", "probe22"):
        changed.loc[changed.match_id.eq(mid), ["home_score", "away_score", "result"]] = [0, 9, 0]
    after = n.build_features(changed).set_index("match_id")
    np.testing.assert_array_equal(base.loc["30700", list(n.FEATURES)], after.loc["30700", list(n.FEATURES)])


def test_halftime_fields_never_become_completed_history():
    source = chronology().assign(halftime_home=1, halftime_away=0)
    first = n.build_features(source)
    source[["halftime_home", "halftime_away"]] = [99, 88]
    second = n.build_features(source)
    pd.testing.assert_frame_equal(first[list(n.FEATURES)], second[list(n.FEATURES)])


@pytest.mark.parametrize("column,value", [("home_score", 2), ("match_date", pd.Timestamp("2024-08-24")),
    ("home_team_id", D), ("kickoff_time", "19:03"), ("round", 29), ("season", 2025)])
def test_registered_identity_cannot_be_changed(column, value):
    source = chronology()
    source.loc[source.match_id.eq("30700"), column] = value
    with pytest.raises(ValueError):
        n.build_features(source)


def test_duplicate_id_and_unknown_temporal_annotation_stop():
    source = chronology()
    with pytest.raises(ValueError, match="unique"):
        n.build_features(pd.concat([source, source.iloc[:1]], ignore_index=True))
    source["timing_note"] = ""
    source.loc[source.match_id.eq("between"), "timing_note"] = "翌日に再開"
    with pytest.raises(ValueError, match="Unreviewed temporal"):
        n.build_features(source)


def test_corrupted_event_metadata_stops_before_any_fit(monkeypatch):
    state = n.build_features(chronology())
    n.require_original_kickoff_timing(state)
    state.loc[state.match_id.eq("30700"), "result_effective_timestamp"] = "2024-08-25T00:00:00+09:00"
    monkeypatch.setattr(n, "estimator", lambda *a: pytest.fail("Must stop before fit"))
    with pytest.raises(ValueError, match="event field"):
        n.fit("mlp", state)


def test_normal_matches_preserve_legacy_values_and_all_models_share_features():
    source = chronology().loc[lambda x: x.match_id.ne("30700")]
    legacy = n.legacy_features(source)
    current = n.build_features(source)
    pd.testing.assert_frame_equal(legacy[list(n.FEATURES)], current[list(n.FEATURES)], check_dtype=False)
    assert n.specification()["all_three_models_share_event_features"] is True
    assert n.specification()["legacy_historical_reference_is_required_gate"] is False


def record_html(note="", outside=""):
    return (f'<html>{outside}<!-- A11 備考エリア Start --><div><p>{note}</p></div><!-- A11 備考エリア End --></html>').encode()


def test_unknown_timing_notes_do_not_get_normal_fallback():
    for note in ("8/24中止、翌日に再開", "30分のため5分間中断"):
        notes = t.timing_notes(record_html(note))
        with pytest.raises(ValueError, match="Unreviewed interruption"):
            t.classify_notes("99999", "2024-08-24", notes, {})
    with pytest.raises(ValueError, match="outside remarks"):
        t.timing_notes(record_html(outside="<p>Match resumed next day</p>"))
    assert t.timing_notes(record_html(outside='<script>sessionReplay.RESUME="resume"</script>')) == []


def test_unknown_remarks_structure_is_not_assumed_ordinary():
    with pytest.raises(ValueError, match="remarks structure"):
        t.timing_notes(b"<html><p>no remarks schema</p></html>")


def test_verified_empty_remarks_template_and_changed_template():
    template = '<html><div id="team-name-l"></div><div id="team-name-r"></div><div class="score-board-main"></div><!-- A10 監督 End --><!-- IN・OUTマーク凡例 --><p>▲：IN　▽：OUT</p><!-- A12 試合情報 Start --></html>'
    assert t.timing_notes(template.encode()) == []
    two_coaches = template.replace('<!-- A10 監督 End -->', '<!-- A10 監督 End --><div>監督 石﨑信弘</div><!-- A10 監督 End -->')
    assert t.timing_notes(two_coaches.encode()) == []
    with pytest.raises(ValueError, match="empty-remarks structure"):
        t.timing_notes(template.replace("▲：IN　▽：OUT", "延期して翌日再開").encode())


def test_cache_hash_and_unreviewed_interruption_stop(tmp_path):
    directory = tmp_path / "data/raw/jleague_match_stats"
    directory.mkdir(parents=True)
    raw = record_html("延期して再開")
    (directory / "99999.html").write_bytes(raw)
    url = "https://data.j-league.or.jp/SFMS02/?match_card_id=99999"
    meta = dict(requested_url=url, final_url=url, status=200, match_id="99999", bytes=len(raw), sha256=t.digest(raw))
    path = directory / "99999.metadata.json"
    path.write_text(json.dumps(meta))
    registry = tmp_path / "registry.json"
    registry.write_text("{}")
    source = pd.DataFrame([game("99999", "2024-08-24")])
    with pytest.raises(ValueError, match="Unreviewed interruption"):
        t.review_cache(tmp_path, source, registry)
    meta["sha256"] = "0" * 64
    path.write_text(json.dumps(meta))
    with pytest.raises(ValueError, match="evidence mismatch"):
        t.review_cache(tmp_path, source, registry)


def test_input_order_cannot_change_event_features():
    pd.testing.assert_frame_equal(n.build_features(chronology()), n.build_features(chronology().iloc[::-1]))


def test_three_models_receive_identical_event_state_before_feature_subset(monkeypatch):
    from types import SimpleNamespace
    state = n.build_features(chronology())
    captured = {}
    class NoFitPipeline:
        def __init__(self, name):
            self.name = name
        def fit(self, x, y):
            captured[self.name] = (x.copy(deep=True), y.copy(deep=True))
            self.named_steps = {
                "scaler": SimpleNamespace(mean_=np.zeros(x.shape[1]), scale_=np.ones(x.shape[1]), n_samples_seen_=len(x)),
                "classifier": SimpleNamespace(classes_=np.array([0, 1, 2]), n_iter_=1,
                    coef_=np.zeros((3, x.shape[1])), intercept_=np.zeros(3),
                    coefs_=[np.zeros((x.shape[1], 3))], intercepts_=[np.zeros(3)]),
            }
    monkeypatch.setattr(n, "estimator", NoFitPipeline)
    for name in n.NAMES:
        n.fit(name, state)  # Mock only; not an sklearn fit.
    pd.testing.assert_frame_equal(captured["form_logistic"][0], captured["mlp"][0])
    pd.testing.assert_frame_equal(captured["elo_logistic"][0], captured["mlp"][0][["elo_diff"]])
    for name in n.NAMES:
        pd.testing.assert_series_equal(captured[name][1], state.result)
