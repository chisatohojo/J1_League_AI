"""Pre-activation compatibility checks: synthetic storage and mock estimator only."""
from copy import deepcopy
import json

import numpy as np
import pandas as pd
import pytest

from test_weekend_batch import (
    case, repository, production_and_network_firewall, no_real_estimator_or_network,
    friday, prepare, outputs, snapshot, FRIDAY,
)
from scripts import update_champion_dashboard as update
from scripts import build_dashboard_feed as feed
from src.modeling import weekend_batch as w
from src.modeling import champion_prediction as champion
from _legacy_batch_reader_5ac9052 import saved_batches as old_reader


def committed(case):
    friday(case)
    p = prepare(case)
    records, bindings = outputs(case, p)
    path = case.backend.commit(p, records, bindings, lambda: FRIDAY)
    return path, records, bindings


def legacy_directory(case):
    return next(p for p in (case.runtime / 'batches').iterdir() if not p.name.startswith(w.PREFIX))


def refresh_legacy_manifest(directory):
    (directory / 'manifest.json').write_bytes(w.body({n: w.sha(directory / n) for n in ('predictions.csv', 'bindings.csv')}))


def test_mixed_reader_returns_native_values_without_changing_any_batch(case):
    path, new, _ = committed(case)
    before = snapshot(case.runtime / 'batches')
    records, bindings = update.saved_batches(case.runtime)
    assert len(records) == len(bindings) == 14
    assert {r['fixture_key']: r for r in records if r['fixture_key'] in {n['fixture_key'] for n in new}} == {r['fixture_key']: r for r in new}
    assert w.read_batch(path)[0] == new
    assert snapshot(case.runtime / 'batches') == before


def test_v2_renamed_and_manifest_stripped_cannot_fall_back_to_legacy(case):
    path, _, _ = committed(case)
    disguised = path.with_name('a' * 64)
    path.rename(disguised)  # synthetic corruption only; keep the snapshot as evidence
    refresh_legacy_manifest(disguised)
    before = snapshot(case.runtime / 'batches')
    with pytest.raises(ValueError, match='batch_files'):
        update.saved_batches(case.runtime)
    assert snapshot(case.runtime / 'batches') == before


@pytest.mark.parametrize('field,value', [('fixture_key', 'wrong-fixture'), ('prediction_generated_at', '2026-08-01T00:00:00+00:00')])
def test_legacy_binding_identity_checked_by_reader_itself(case, field, value):
    directory = legacy_directory(case)
    sidecar = feed.csv_frame((directory / 'bindings.csv').read_bytes())
    sidecar.loc[0, field] = value
    (directory / 'bindings.csv').write_bytes(sidecar.to_csv(index=False, lineterminator='\n').encode())
    refresh_legacy_manifest(directory)
    before = snapshot(case.runtime / 'batches')
    with pytest.raises(ValueError):
        update.saved_batches(case.runtime)
    assert snapshot(case.runtime / 'batches') == before


def test_legacy_manifest_duplicate_keys_are_not_silently_collapsed(case):
    directory = legacy_directory(case)
    m = json.loads((directory / 'manifest.json').read_bytes())
    text = json.dumps(m)[:-1] + ',"predictions.csv":' + json.dumps(m['predictions.csv']) + '}'
    (directory / 'manifest.json').write_text(text, encoding='utf8')
    with pytest.raises(ValueError, match='duplicate_json_key'):
        update.saved_batches(case.runtime)


def test_legacy_orphan_binding_cannot_be_hidden_as_another_artifact(case):
    directory = legacy_directory(case)
    sidecar = feed.csv_frame((directory / 'bindings.csv').read_bytes())
    sidecar.loc[0, 'prediction_artifact'] = 'other.csv'
    (directory / 'bindings.csv').write_bytes(sidecar.to_csv(index=False, lineterminator='\n').encode())
    refresh_legacy_manifest(directory)
    with pytest.raises(ValueError):
        update.saved_batches(case.runtime)


def test_extra_unrelated_binding_cannot_be_ignored(case):
    directory = legacy_directory(case)
    sidecar = feed.csv_frame((directory / 'bindings.csv').read_bytes())
    extra = sidecar.iloc[[0]].copy()
    extra['prediction_artifact'] = 'other.csv'
    sidecar = pd.concat([sidecar, extra], ignore_index=True)
    (directory / 'bindings.csv').write_bytes(sidecar.to_csv(index=False, lineterminator='\n').encode())
    refresh_legacy_manifest(directory)
    with pytest.raises(ValueError):
        update.saved_batches(case.runtime)


def test_unmodified_legacy_reader_rejects_v2_without_corrupting_it(case):
    assert len(old_reader(case.runtime)[0]) == 4
    committed(case)
    before = snapshot(case.runtime / 'batches')
    with pytest.raises(ValueError, match='invalid_batch_directory'):
        old_reader(case.runtime)
    assert snapshot(case.runtime / 'batches') == before


def test_v2_manifest_disguised_as_legacy_is_rejected_by_both_readers(case):
    path, _, _ = committed(case)
    path.rename(path.with_name('a' * 64))
    before = snapshot(case.runtime / 'batches')
    with pytest.raises(ValueError, match='batch_manifest'):
        old_reader(case.runtime)
    with pytest.raises(ValueError, match='batch_manifest'):
        update.saved_batches(case.runtime)
    assert snapshot(case.runtime / 'batches') == before


@pytest.mark.parametrize('problem', ['late_commit', 'stale_source'])
def test_rehashed_snapshot_cannot_hide_deadline_or_staleness(case, problem):
    path, _, _ = committed(case)
    m = w.read_json(path / 'manifest.json')
    if problem == 'late_commit':
        m['committed_at'] = '2026-08-21T08:00:00+09:00'
    else:
        c = w.read_json(path / 'snapshot.json')
        c['snapshot']['source_observed_at'] = '2026-08-19T06:59:00+09:00'
        c['snapshot_id'] = m['snapshot_id'] = w.digest(c['snapshot'])
        (path / 'snapshot.json').write_bytes(w.body(c))
        m['files']['snapshot.json'] = w.sha(path / 'snapshot.json')
    (path / 'manifest.json').write_bytes(w.body(m))
    path.rename(path.with_name(w.PREFIX + w.sha(path / 'manifest.json')))
    with pytest.raises(ValueError):
        update.saved_batches(case.runtime)


def test_duplicate_prediction_id_across_distinct_fixtures_is_rejected(case):
    directory, records, bindings = committed(case)
    old_records, _ = old_reader_for_legacy_only(case)
    records[0]['match_id'] = old_records[0]['match_id']
    bindings[0]['prediction_match_id'] = old_records[0]['match_id']
    # A distinct fixture with a conflicting external ID must not enter aggregate readers.
    update._publish_daily_batch(case.runtime, records[:1], bindings[:1])
    # Remove only the synthetic v2 source here, so fixture duplication is not the reason.
    directory.rename(case.runtime / 'held-v2')
    with pytest.raises(ValueError, match='duplicate_saved_prediction_id'):
        update.saved_batches(case.runtime)


def old_reader_for_legacy_only(case):
    # Do not call an old reader against v2; inspect only unchanged synthetic seed files.
    rows, bindings = [], []
    for p in (case.runtime / 'batches').iterdir():
        if not p.name.startswith(w.PREFIX):
            rows.extend(feed.csv_frame((p / 'predictions.csv').read_bytes()).to_dict('records'))
            bindings.extend(feed.csv_frame((p / 'bindings.csv').read_bytes()).to_dict('records'))
    return rows, bindings


def test_roll_back_to_disabled_mode_keeps_v2_and_refuses_duplicate_daily_append(case):
    path, records, bindings = committed(case)
    before = snapshot(case.runtime / 'batches')
    assert w.policy({'weekend_policy': {'enabled': False}}) is None
    assert len(update.saved_batches(case.runtime)[0]) == 14
    with pytest.raises(ValueError, match='saved_prediction_overlap'):
        update.publish_batch(case.runtime, records, bindings)
    assert path.is_dir() and snapshot(case.runtime / 'batches') == before


@pytest.mark.parametrize('file', ['snapshot.json', 'bindings.csv', 'predictions.csv'])
def test_context_or_output_missing_never_recovers_or_deletes_published_batch(case, file):
    path, _, _ = committed(case)
    (path / file).unlink()
    before = snapshot(case.runtime / 'batches')
    with pytest.raises(ValueError):
        update.saved_batches(case.runtime)
    assert path.is_dir() and snapshot(case.runtime / 'batches') == before


def test_cross_format_fixture_overlap_stops_without_modifying_either(case):
    _, records, bindings = committed(case)
    # Deliberately bypass the publisher's lock/overlap guard in synthetic storage.
    update._publish_daily_batch(case.runtime, records[:1], bindings[:1])
    before = snapshot(case.runtime / 'batches')
    with pytest.raises(ValueError, match='duplicate_saved_fixture'):
        update.saved_batches(case.runtime)
    assert snapshot(case.runtime / 'batches') == before


def test_elo_input_is_single_float_column_and_ha_is_not_added_to_feature(case):
    friday(case)
    targets = pd.DataFrame(w.target_identity(case.current, case.backend.window), columns=champion.TARGET_COLUMNS)
    ratings = {team: 1500.0 for team in set(targets.home_team_id) | set(targets.away_team_id)}
    ratings[targets.iloc[0].home_team_id] = 1530.0
    expected = np.array([ratings[r.home_team_id] - ratings[r.away_team_id] for r in targets.itertuples()]).reshape(-1, 1)
    before = deepcopy(ratings)
    champion.probability_rows(case.backend.artifact, targets, ratings)
    assert np.array_equal(case.model.inputs[-1], expected)
    assert case.model.inputs[-1].dtype.kind == 'f' and ratings == before
    champion.probability_rows(case.backend.artifact, targets.iloc[::-1], ratings)
    assert np.array_equal(case.model.inputs[-1][::-1], expected) and ratings == before


def test_champion_target_api_cannot_accept_future_outcome_columns(case):
    friday(case)
    targets = pd.DataFrame(w.target_identity(case.current, case.backend.window), columns=champion.TARGET_COLUMNS)
    targets['result'] = '2'
    with pytest.raises(ValueError, match='prediction_target_allowlist'):
        champion.probability_rows(case.backend.artifact, targets, {})
    assert not case.model.inputs


def test_wrong_class_order_stops_before_scaler_or_model_prediction(case):
    friday(case)
    targets = pd.DataFrame(w.target_identity(case.current, case.backend.window), columns=champion.TARGET_COLUMNS)
    case.model.classes_ = np.array([2, 1, 0])
    ratings = {team: 1500.0 for team in set(targets.home_team_id) | set(targets.away_team_id)}
    with pytest.raises(ValueError, match='prediction_class_order'):
        champion.probability_rows(case.backend.artifact, targets, ratings)
    assert not case.model.inputs
