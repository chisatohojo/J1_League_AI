"""Synthetic history and fictional fixture contracts; never register or save forecasts."""
from copy import deepcopy
from datetime import datetime, timedelta
import socket
import subprocess

import numpy as np
import pandas as pd
import pytest

from src.features.nn_research_timing import POLICY
from src.modeling import nn_v2_contracts as c
from src.modeling import nn_v2_offsets as o
from src.modeling.nn_residual_v2 import FORM_FEATURES


@pytest.fixture(autouse=True)
def forbid_external_data(monkeypatch):
    def denied(*a, **k):
        raise AssertionError("Only synthetic in-memory data allowed")
    monkeypatch.setattr(pd, "read_csv", denied)
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(subprocess, "Popen", denied)


def history():
    rows = []
    for year in range(2015, 2026):
        for j in range(6):
            hg, ag = [(0, 1), (1, 1), (2, 0)][j % 3]
            rows.append(dict(match_id=f'synthetic-{year}-{j}', season=year,
                match_date=pd.Timestamp(year, 2, j+1), kickoff_time='19:00',
                home_team_id='synthetic-home', away_team_id='synthetic-away',
                home_score=hg, away_score=ag, result=j % 3))
    return pd.DataFrame(rows)


def test_chronological_offsets_have_only_prior_year_fit_and_new_scalers(record_property):
    prepared = o.prepare_history(history()); before = prepared.copy(deep=True)
    result = o.generate_crossfit_offsets(prepared)
    assert result.role == 'crossfit_training_offsets_only'
    assert len(result.rows) == 54 and len(result.audit) == 9
    for a, year in zip(result.audit, range(2017, 2026), strict=True):
        train = prepared[prepared.season.lt(year)]
        assert a['target_year'] == year
        assert a['training_years'] == list(range(2015, year))
        assert set(a['training_ids']).isdisjoint(a['target_ids'])
        assert a['training_rows'] == a['scaler_rows'] == len(train)
        np.testing.assert_allclose(a['scaler_mean'], [train.elo_diff.mean()], atol=1e-12)
        np.testing.assert_allclose(a['scaler_var'], [train.elo_diff.var(ddof=0)], atol=1e-10)
        assert a['class_order'] == [0, 1, 2]
    assert not result.rows.match_id.duplicated().any()
    assert set(result.rows.season) == set(range(2017, 2026))
    assert np.isfinite(result.rows.iloc[:, 2:].to_numpy()).all()
    pd.testing.assert_frame_equal(prepared, before)
    record_property('synthetic_crossfit_folds', 9)
    record_property('synthetic_crossfit_rows', 54)


def test_own_year_labels_do_not_fit_its_baseline_and_later_results_do_not_change_earlier_offsets():
    original = history(); changed = original.copy(deep=True)
    # Change the last synthetic 2020 outcome, not a real result.
    mask = changed.match_id.eq('synthetic-2020-5')
    changed.loc[mask, ['home_score', 'away_score', 'result']] = [0, 2, 0]
    one = o.generate_crossfit_offsets(o.prepare_history(original))
    two = o.generate_crossfit_offsets(o.prepare_history(changed))
    a = next(a for a in one.audit if a['target_year'] == 2020)
    b = next(a for a in two.audit if a['target_year'] == 2020)
    assert a == b
    pd.testing.assert_frame_equal(one.rows[one.rows.season.le(2020)], two.rows[two.rows.season.le(2020)])
    # 2021 may legitimately use completed 2020 labels; no invariance is claimed there.


def test_scaler_and_estimator_instances_are_new_for_each_fold(monkeypatch):
    seen = []
    create = o._new_pipeline
    def fresh():
        model = create(); seen.append(model); return model
    monkeypatch.setattr(o, '_new_pipeline', fresh)
    o.generate_crossfit_offsets(o.prepare_history(history()))
    assert len({id(m) for m in seen}) == len({id(m[0]) for m in seen}) == 9


def test_final_baseline_role_and_population_separated_from_crossfit():
    prepared = o.prepare_history(history())
    crossfit = o.generate_crossfit_offsets(prepared)
    final = o.fit_final_baseline(prepared)
    assert final.role == 'final_2015_2025_future_inference_only'
    assert final.audit['training_rows'] == final.audit['scaler_rows'] == 66
    assert crossfit.audit[-1]['training_rows'] == 60
    assert final.decision_function(pd.DataFrame({'elo_diff': [0., 10.]})).shape == (2, 3)
    with pytest.raises(ValueError): final.decision_function(prepared[['elo_diff', 'result']])
    final.pipeline[-1].classes_ = np.array([2, 1, 0])
    with pytest.raises(ValueError): final.decision_function(prepared[['elo_diff']])


def test_input_row_permutation_cannot_change_chronological_baseline_order():
    prepared = o.prepare_history(history())
    a = o.generate_crossfit_offsets(prepared)
    b = o.generate_crossfit_offsets(prepared.iloc[::-1])
    pd.testing.assert_frame_equal(a.rows, b.rows)
    assert a.audit == b.audit


@pytest.mark.parametrize('edit', ['unknown_note', 'unknown_effective', 'unknown_policy', 'exception_field', 'missing_seed', 'year_disguise', 'duplicate_id', 'nonfinite'])
def test_bad_chronology_rejected_before_any_fit(edit, monkeypatch):
    raw = history()
    if edit == 'unknown_note':
        raw['resumed_at'] = ''; raw.loc[0, 'resumed_at'] = '2015-03-01'
        with pytest.raises(ValueError): o.prepare_history(raw)
        return
    prepared = o.prepare_history(raw)
    if edit == 'unknown_effective': prepared.loc[0, 'result_effective_timestamp'] = '2015-03-01T00:00:00+09:00'
    if edit == 'unknown_policy': prepared.loc[0, 'timing_policy'] = 'unreviewed'
    if edit == 'exception_field': prepared['timing_exception_id'] = 'new-interruption'
    if edit == 'missing_seed': prepared = prepared[prepared.season.ne(2016)]
    if edit == 'year_disguise': prepared.loc[0, 'season'] = 2025
    if edit == 'duplicate_id': prepared.loc[0, 'match_id'] = prepared.loc[1, 'match_id']
    if edit == 'nonfinite': prepared.loc[0, 'elo_diff'] = np.inf
    def forbidden(*a, **k): raise AssertionError('Must reject before fit')
    monkeypatch.setattr(o, '_fit', forbidden)
    with pytest.raises(ValueError): o.generate_crossfit_offsets(prepared)


def plan():
    fixtures = []
    for r in range(11, 31):
        day = (datetime(2026, 11, 1) + timedelta(days=7*(r-11))).date().isoformat()
        for j in range(10):
            fixtures.append({'fixture_key': f'synthetic-fixture-{r}-{j}', 'round': r,
                'home_team_id': f'synthetic-club-{2*j}', 'away_team_id': f'synthetic-club-{2*j+1}',
                'kickoff': day+'T14:00:00+09:00', 'status': 'scheduled',
                'namespace': 'jleague_match_page', 'official_id': f'999{r:02}{j:02}', 'mapping_status': 'verified'})
    return {'schema': 'nn_v2_enrollment_proposal_v1', 'state': 'proposal', 'data_origin': 'synthetic',
        'study_id': 'synthetic-study', 'competition': '2026_27_ordinary_J1',
        't0': '2026-10-20T07:00:00+09:00', 'spec_frozen_at': '2026-10-19T07:00:00+09:00',
        'artifact_sealed_at': '2026-10-20T06:00:00+09:00', 'schedule_observed_at': '2026-10-20T06:30:00+09:00',
        'official_revision': 'a'*64, 'r_start': 11, 'fixtures': fixtures}


def prediction(p, fixture):
    day = c.jst_day(fixture['kickoff']).isoformat()
    return {'schema': 'nn_v2_paired_prediction_v1', 'prediction_type': 'research_v2_saved_pre_match',
        'data_origin': 'synthetic', 'study_id': p['study_id'], 'model_version': 'synthetic-v2',
        'fixture': deepcopy(fixture), 'generated_at': day+'T07:00:00.0000001+09:00',
        'readback_at': day+'T07:00:01+09:00', 'history_cutoff': day+'T00:00:00+09:00',
        'source_observed_at': day+'T06:59:00+09:00', 'run_id': 'synthetic-run',
        'official_revision': 'a'*64, 'source_witness_sha256': 'b'*64,
        'baseline_sha256': 'c'*64, 'residual_sha256': 'd'*64, 'feature_schema_sha256': 'e'*64,
        'class_order': [0, 1, 2], 'base_probabilities': [0.2, 0.3, 0.5], 'residual_probabilities': [0.21, 0.3, 0.49]}


def test_synthetic_20_round_200_fixture_proposal_and_full_date_batch(record_property):
    p = plan(); before = deepcopy(p)
    c.validate_enrollment(p, now=p['t0'])
    records = [prediction(p, f) for f in p['fixtures'][:10]]
    c.validate_prediction_batch(records, p)
    assert p == before and p['state'] == 'proposal'
    record_property('synthetic_enrolled_fixture_validation_only', 200)
    record_property('actual_enrollments', 0)
    record_property('actual_saved_forecasts', 0)


@pytest.mark.parametrize('edit', ['199', '201', 'round', 'key', 'official', 'club', 'namespace', 'candidate', 'started', 'seal', 'observation', 'future_t0', 'naive', 'too_late_round'])
def test_enrollment_rejects_incomplete_identity_or_bad_T0(edit):
    p = plan()
    if edit == '199': p['fixtures'].pop()
    if edit == '201': p['fixtures'].append(deepcopy(p['fixtures'][0]))
    if edit == 'round': p['fixtures'][0]['round'] = 31
    if edit == 'key': p['fixtures'][1]['fixture_key'] = p['fixtures'][0]['fixture_key']
    if edit == 'official': p['fixtures'][1]['official_id'] = p['fixtures'][0]['official_id']
    if edit == 'club': p['fixtures'][1]['home_team_id'] = p['fixtures'][0]['home_team_id']
    if edit == 'namespace': p['fixtures'][0]['namespace'] = 'guessed_namespace'
    if edit == 'candidate': p['fixtures'][0]['status'] = 'candidate'
    if edit == 'started': p['fixtures'][0]['kickoff'] = p['t0']
    if edit == 'seal': p['artifact_sealed_at'] = '2026-10-21T07:00:00+09:00'
    if edit == 'observation': p['schedule_observed_at'] = '2026-10-21T07:00:00+09:00'
    if edit == 'future_t0': p['t0'] = '2026-10-21T07:00:00+09:00'
    if edit == 'naive': p['t0'] = '2026-10-20T07:00:00'
    if edit == 'too_late_round': p['r_start'] = 20
    with pytest.raises(ValueError): c.validate_enrollment(p, now='2026-10-20T07:00:00+09:00')


def test_pending_id_can_be_tracked_but_not_predicted_or_guessed():
    p = plan(); p['fixtures'][0].update(official_id=None, mapping_status='pending')
    c.validate_enrollment(p, now=p['t0'])
    with pytest.raises(ValueError): c.validate_prediction(prediction(p, p['fixtures'][0]), p)
    assert p['fixtures'][0]['official_id'] is None


@pytest.mark.parametrize('edit', ['late', 'readback_before_generation', 'before_T0', 'score', 'source_future', 'cutoff', 'identity', 'class_order', 'nan', 'sum', 'negative', 'sha', 'kind', 'missing_field'])
def test_prediction_rejects_invalid_schema_identity_or_deadline(edit):
    p = plan(); r = prediction(p, p['fixtures'][0])
    if edit == 'late': r['readback_at'] = r['fixture']['kickoff']
    if edit == 'readback_before_generation': r['readback_at'] = '2026-11-01T06:00:00+09:00'
    if edit == 'before_T0': r['generated_at'] = '2026-10-19T00:00:00+09:00'
    if edit == 'score': r['result'] = 2
    if edit == 'source_future': r['source_observed_at'] = r['fixture']['kickoff']
    if edit == 'cutoff': r['history_cutoff'] = '2026-10-31T00:00:00+09:00'
    if edit == 'identity': r['fixture']['home_team_id'], r['fixture']['away_team_id'] = r['fixture']['away_team_id'], r['fixture']['home_team_id']
    if edit == 'class_order': r['class_order'] = [2, 1, 0]
    if edit == 'nan': r['residual_probabilities'] = [np.nan, 0.2, 0.8]
    if edit == 'sum': r['base_probabilities'] = [0.2, 0.3, 0.4]
    if edit == 'negative': r['base_probabilities'] = [-0.2, 0.3, 0.9]
    if edit == 'sha': r['residual_sha256'] = 'bad'
    if edit == 'kind': r['prediction_type'] = 'retrospective_reconstruction'
    if edit == 'missing_field': r.pop('source_witness_sha256')
    with pytest.raises(ValueError): c.validate_prediction(r, p)


def test_partial_duplicate_and_mixed_date_batches_are_rejected():
    p = plan(); records = [prediction(p, f) for f in p['fixtures'][:10]]
    for bad in [records[:-1], records+[records[0]], records+[prediction(p, p['fixtures'][10])]]:
        with pytest.raises(ValueError): c.validate_prediction_batch(bad, p)


def test_all_readbacks_must_precede_the_earliest_batch_kickoff():
    p = plan(); p['fixtures'][9]['kickoff'] = '2026-11-01T16:00:00+09:00'
    records = [prediction(p, f) for f in p['fixtures'][:10]]
    records[-1]['readback_at'] = '2026-11-01T15:00:00+09:00'
    with pytest.raises(ValueError): c.validate_prediction_batch(records, p)


def test_timestamp_seventh_digit_and_timezone_are_preserved():
    assert c.stamp('2026-11-01T14:00:00.0000001+09:00')-c.stamp('2026-11-01T05:00:00Z') == 1
    p = plan(); p['fixtures'][0]['kickoff'] = '2026-11-01T14:00:00.0000001+09:00'
    r = prediction(p, p['fixtures'][0]); r['readback_at'] = '2026-11-01T14:00:00.0000000+09:00'
    c.validate_prediction(r, p)
    r['readback_at'] = '2026-11-01T14:00:00.0000002+09:00'
    with pytest.raises(ValueError): c.validate_prediction(r, p)


@pytest.mark.parametrize('bad', ['2026-02-30T00:00:00Z', '2026-11-01T14:00:00.12345678Z',
                                '2026-11-01T14:00:00+09:99', '2026-11-01T14:00:00+24:00',
                                '2026-11-01T14:00:00-00:00', '2026-11-01', None])
def test_invalid_timestamps_rejected(bad):
    with pytest.raises(ValueError): c.stamp(bad)


def artifact_manifest():
    return {'schema': 'nn_v2_study_artifact_manifest_v1', 'role': 'research_only_not_champion',
        'data_origin': 'synthetic', 'study_id': 'synthetic-study', 'residual_sha256': 'a'*64,
        'baseline_sha256': 'b'*64, 'implementation_sha256': 'c'*64, 'spec_sha256': 'd'*64,
        'training_manifest_sha256': 'e'*64, 'input_sha256': {'synthetic-input': 'f'*64},
        'feature_order': list(FORM_FEATURES), 'class_order': [0, 1, 2], 'timing_policy': POLICY,
        'source_rows': 66, 'residual_rows': 54, 'sealed_at': '2026-10-20T06:00:00+09:00'}


@pytest.mark.parametrize('edit', [None, 'champion', 'order', 'bool_class', 'real_count', 'no_seed', 'timing', 'extra'])
def test_research_artifact_manifest_schema(edit):
    m = artifact_manifest()
    if edit is None:
        c.validate_artifact_manifest(m); return
    if edit == 'champion': m['role'] = 'champion'
    if edit == 'order': m['feature_order'].reverse()
    if edit == 'bool_class': m['class_order'] = [False, 1, 2]
    if edit == 'real_count': m['data_origin'] = 'real'
    if edit == 'no_seed': m['residual_rows'] = m['source_rows']
    if edit == 'timing': m['timing_policy'] = 'unreviewed'
    if edit == 'extra': m['new_field'] = 1
    with pytest.raises(ValueError): c.validate_artifact_manifest(m)


@pytest.mark.parametrize('bad_field', [None, 'real_fit_calls', 'real_evaluation_calls', 'future_saved_predictions'])
def test_phase2_1_audit_manifest_has_zero_real_operations(bad_field):
    m = {'schema': 'nn_v2_phase2_1_audit_v1', 'data_origin': 'synthetic', 'study_id': 'synthetic-study',
        'started_at': '2026-10-20T07:00:00Z', 'finished_at': '2026-10-20T07:01:00Z',
        'implementation_sha256': 'a'*64, 'artifact_manifest_sha256': 'b'*64,
        'source_hashes': {'synthetic-fixtures': 'c'*64}, 'checks': {'gradients': 'PASS'},
        'real_fit_calls': 0, 'real_evaluation_calls': 0, 'future_saved_predictions': 0}
    if bad_field is None:
        c.validate_audit_manifest(m)
    else:
        m[bad_field] = 1
        with pytest.raises(ValueError): c.validate_audit_manifest(m)


def full_schedule():
    p = plan()
    fixtures = []
    for r in range(1, 39):
        day = (datetime(2026, 7, 1)+timedelta(days=7*(r-1)) if r < 11 else
               datetime(2026, 11, 1)+timedelta(days=7*(r-11))).date().isoformat()
        for j in range(10):
            f = deepcopy(p['fixtures'][j])
            f.update(fixture_key=f'synthetic-fixture-{r}-{j}', round=r,
                     official_id=f'999{r:02}{j:02}', kickoff=day+'T14:00:00+09:00',
                     status='completed' if r < 11 else 'scheduled')
            fixtures.append(f)
    return fixtures


def test_first_eligible_round_checked_against_independent_380_fixture_schedule():
    p = plan(); source = full_schedule()
    c.validate_target_selection(p, source, now=p['t0'])
    p['r_start'] = 12
    p['fixtures'] = [f for f in source if 12 <= f['round'] <= 31]
    c.validate_enrollment(p, now=p['t0'])  # structurally valid but skips the first eligible round
    with pytest.raises(ValueError, match='first wholly unstarted'):
        c.validate_target_selection(p, source, now=p['t0'])


@pytest.mark.parametrize('edit', ['missing', 'identity', 'club', 'official'])
def test_independent_schedule_mismatch_is_rejected(edit):
    p = plan(); source = full_schedule()
    if edit == 'missing': source.pop()
    if edit == 'identity': source[100]['official_id'] = '88888888'
    if edit == 'club': source[0]['home_team_id'] = source[1]['home_team_id']
    if edit == 'official': source[1]['official_id'] = source[0]['official_id']
    with pytest.raises(ValueError): c.validate_target_selection(p, source, now=p['t0'])
