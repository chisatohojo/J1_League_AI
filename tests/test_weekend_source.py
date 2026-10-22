"""Only fake HTML/UTC, temporary publications and source checkpoints; no model."""
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from test_dashboard_feed import csv_bytes, production_and_network_firewall
from test_weekend_batch import no_real_estimator_or_network
from test_jleague_ongoing_update import synthetic_fixtures, listing_html, write_source, write_completion
from src.collect import jleague_ongoing as ongoing
from src.collect.teams import MASTER_COLUMNS
from src.modeling import weekend_source as s
from src.modeling import weekend_batch as w

FRIDAY = '2026-08-14'


def at(text):
    return datetime.fromisoformat(text).astimezone(timezone.utc)


FETCH = at('2026-08-14T06:45:00+09:00')
PUBLISH = at('2026-08-14T06:59:00+09:00')
FREEZE = at('2026-08-14T07:00:30+09:00')
CUTOFF = at('2026-08-14T07:00:00+09:00')


def tree(root):
    return {p.relative_to(root).as_posix(): w.sha(p) for p in root.rglob('*') if p.is_file()}


@pytest.fixture
def factory(tmp_path, monkeypatch):
    count = 0
    def build(*, fetched=FETCH, incomplete=False, score=(2, 1), created_offset=1, early_kickoff=False):
        nonlocal count
        count += 1
        root = tmp_path / f'candidate-{count}'
        root.mkdir()
        fixtures = synthetic_fixtures()
        for i, fixture in enumerate(fixtures):
            fixture['match_id'] = str(30000 + i)
        for fixture in fixtures[1:10]:
            fixture['date'] = date(2027, 5, 21)
        offsets = [0] + [1]*4 + [2]*4 + [3]
        for fixture, offset in zip(fixtures[10:20], offsets):
            fixture['date'] = date.fromisoformat(FRIDAY)+timedelta(days=offset)
        if early_kickoff:
            fixtures[10]['kickoff'] = '07:01'
        if not incomplete:
            fixtures[0]['score'] = score
        listing = write_source(root / 'input/listing.html', listing_html(fixtures), timestamp=(fetched-timedelta(seconds=2)).isoformat())
        evidence = []
        if not incomplete:
            page = write_completion(root / 'input', fixtures[0], 1)
            md = json.loads(page.with_suffix('.metadata.json').read_bytes())
            write_source(page, page.read_text(encoding='utf8'), timestamp=fetched.isoformat(), url=md['requested_url'])
            evidence.append(page)
        for path in [listing, *evidence]:
            md = json.loads(path.with_suffix('.metadata.json').read_bytes())
            md['request_started_at_utc'] = (at(md['fetched_at_utc'])-timedelta(milliseconds=500)).isoformat()
            path.with_suffix('.metadata.json').write_bytes(w.body(md))
        created = fetched + timedelta(seconds=created_offset)
        class FrozenDatetime(datetime):
            @classmethod
            def now(cls, tz=None):
                return created.astimezone(tz)
        monkeypatch.setattr(ongoing, 'datetime', FrozenDatetime)
        snap = ongoing.create_snapshot(root / 'snapshots', listing_html=listing, evidence_html=evidence, snapshot_id=f'synthetic-{count}')
        summary = ongoing.process_snapshot(snap, root / 'official')
        assert summary['publication_status'] == 'published'
        pointer = w.read_json(root / 'official/latest.json')
        aliases = [dict(team_id=f'team_{n+1:04d}', canonical_name=f'club{n:02d}', source_name=f'club{n:02d}',
                        source='jleague_data_site', valid_from='', valid_to='', source_club_id=f'club{n:02d}') for n in range(20)]
        (root / 'teams.csv').write_bytes(csv_bytes(aliases, MASTER_COLUMNS))
        return SimpleNamespace(root=root, revision=pointer['revision_id'], manifest_sha=pointer['manifest_sha256'], snapshot=snap, fixtures=fixtures)
    return build


@pytest.fixture
def case(factory, tmp_path):
    c = factory()
    c.workspace = s.Workspace.create(tmp_path / 'provider-output')
    return c


def publish(c, **kwargs):
    return s.publish(c.workspace, c.root, c.revision, c.manifest_sha, FRIDAY, clock=kwargs.pop('clock', lambda: PUBLISH), **kwargs)


def reservation(c, ref, *, created='2026-08-11T06:59:00+09:00'):
    _, receipt = s.verify(c.workspace, ref, FRIDAY)
    path = c.workspace.root / 'reservation.json'
    w.write_new(path, w.body(dict(scope=s.SCOPE, policy=w.POLICY, period=receipt['facts']['period'],
        targets=receipt['facts']['targets'], created_at=w.utc(at(created)), source_revision=c.revision,
        source_manifest_sha256=c.manifest_sha)))
    return path


def provider(c, ref, **kwargs):
    path = reservation(c, ref)
    return s.Provider(c.workspace, ref, FRIDAY, path, clock=kwargs.pop('clock', lambda: FREEZE), **kwargs)


def test_0645_acquisition_0659_publication_receipt_and_fixed_backend_checkpoints(case):
    original = tree(case.root)
    ref = publish(case)
    current, receipt = s.verify(case.workspace, ref, FRIDAY)
    assert receipt['publication_completed_at_utc'] == PUBLISH.isoformat()
    assert receipt['facts']['source_acquired_at_utc'] == FETCH.isoformat()
    assert receipt['facts']['fixture_count'] == 380 and receipt['facts']['history_completed_count'] == 1
    assert len(receipt['facts']['targets']) == 10
    assert {t['match_date'] for t in receipt['facts']['targets']} == {'2026-08-14','2026-08-15','2026-08-16','2026-08-17'}
    session = provider(case, ref)
    a = session.checkpoint('before_prediction')
    b = session.checkpoint('before_save', generated_at_utc=FREEZE)
    assert a['snapshot_id'] == b['snapshot_id'] and a['receipt_sha256'] == b['receipt_sha256']
    assert a['source'].revision_id == b['source'].revision_id == current.revision_id == case.revision
    assert tree(case.root) == original
    assert not (case.workspace.root / 'batches').exists()


def test_previous_evening_publication_can_be_reused_when_all_gates_pass(factory, tmp_path):
    fetched = at('2026-08-13T22:00:00+09:00')
    c = factory(fetched=fetched)
    c.workspace = s.Workspace.create(tmp_path / 'night-output')
    ref = publish(c, clock=lambda: fetched+timedelta(seconds=30))
    session = provider(c, ref)
    assert session.checkpoint('before_prediction')['source_acquired_at_utc'] == fetched.isoformat()
    session.checkpoint('before_save', generated_at_utc=FREEZE)


def test_evening_unfinished_history_holds_without_receipt(factory, tmp_path):
    c = factory(fetched=at('2026-08-13T22:00:00+09:00'), incomplete=True)
    c.workspace = s.Workspace.create(tmp_path / 'night-output')
    with pytest.raises(ValueError, match='history_incomplete'):
        publish(c)
    assert not list(c.workspace.root.glob('receipts/*/seal.json'))


@pytest.mark.parametrize('kind', ['acquired_after', 'published_after', 'exact_boundary'])
def test_070000_boundary_down_to_microsecond(factory, tmp_path, kind):
    acquired = CUTOFF + timedelta(microseconds=1) if kind == 'acquired_after' else CUTOFF-timedelta(seconds=2)
    c = factory(fetched=acquired)
    c.workspace = s.Workspace.create(tmp_path / 'boundary-output')
    now = CUTOFF + timedelta(microseconds=1) if kind == 'published_after' else CUTOFF
    if kind == 'exact_boundary':
        ref = publish(c, clock=lambda: now)
        assert s.verify(c.workspace, ref, FRIDAY)[0].revision_id == c.revision
    else:
        with pytest.raises(ValueError): publish(c, clock=lambda: now)


@pytest.mark.parametrize('fault_point', ['before_payload', 'before_publish', 'after_publish', 'before_receipt', 'after_receipt', 'before_seal'])
def test_publication_crash_keeps_orphans_and_refuses_restart(case, fault_point):
    def fault(event):
        if event == fault_point: raise OSError('synthetic crash')
    with pytest.raises(OSError): publish(case, fault=fault)
    before = tree(case.workspace.root)
    with pytest.raises(FileExistsError): publish(case)
    assert tree(case.workspace.root) == before
    fake = s.Reference(case.revision, 'a'*64, 'b'*64, PUBLISH.isoformat())
    with pytest.raises(ValueError): s.verify(case.workspace, fake, FRIDAY)


@pytest.mark.parametrize('file', ['receipt.json', 'seal.json', 'reference.json'])
def test_receipt_or_seal_missing_or_modified_rejected(case, file):
    ref = publish(case)
    path = case.workspace.root / 'receipts' / case.revision / file
    saved = path.read_bytes()
    path.unlink()
    with pytest.raises(ValueError, match='receipt_missing'): s.verify(case.workspace, ref, FRIDAY)
    path.write_bytes(saved+b' ')
    with pytest.raises(ValueError, match='receipt_or_seal_sha'): s.verify(case.workspace, ref, FRIDAY)


@pytest.mark.parametrize('field', ['publication_completed_at_utc', 'publication_started_at_utc', 'receipt_created_at_utc'])
def test_completion_unknown_is_not_filled_from_mtime(case, field):
    ref = publish(case)
    path = case.workspace.root / 'receipts' / case.revision / 'receipt.json'
    r = w.read_json(path); r[field] = None
    path.write_bytes(w.body(r))
    with pytest.raises(ValueError): s.verify(case.workspace, ref, FRIDAY)


@pytest.mark.parametrize('relative', ['teams.csv', 'official/revisions/{revision}/schedule.csv', 'snapshots/{snapshot}/listing.html', 'snapshots/{snapshot}/listing.metadata.json'])
def test_all_selected_input_mutations_detected_before_save(case, relative):
    ref = publish(case); session = provider(case, ref)
    session.checkpoint('before_prediction')
    relative = relative.format(revision=case.revision, snapshot=case.snapshot.name)
    path = case.workspace.root / 'publications' / case.revision / relative
    path.write_bytes(path.read_bytes()+b' ')
    with pytest.raises(ValueError): session.checkpoint('before_save', generated_at_utc=FREEZE)


def test_later_latest_update_cannot_replace_selected_revision(case):
    ref = publish(case); session = provider(case, ref)
    (case.root / 'official/latest.json').write_bytes(w.body(dict(revision_id='f'*64,manifest_sha256='e'*64)))
    a = session.checkpoint('before_prediction'); b = session.checkpoint('before_save', generated_at_utc=FREEZE)
    assert a['source'].revision_id == b['source'].revision_id == case.revision


def test_changed_schedule_in_later_applicability_holds_without_changing_source(case):
    ref = publish(case); session = provider(case, ref)
    current, _ = s.verify(case.workspace, ref, FRIDAY)
    index = current.schedule.index[current.schedule.match_date.eq(FRIDAY)][0]
    current.schedule.loc[index, 'kickoff_time'] = '20:00'
    before = tree(case.workspace.root)
    with pytest.raises(ValueError, match='schedule_changed'):
        session.checkpoint('before_prediction', applicability=current)
    assert tree(case.workspace.root) == before


@pytest.mark.parametrize('created', ['2026-08-12T07:00:00+09:00', '2026-08-13T22:00:00+09:00'])
def test_late_reservation_holds(case, created):
    ref = publish(case)
    path = reservation(case, ref, created=created)
    with pytest.raises(ValueError, match='late_reservation'):
        s.Provider(case.workspace, ref, FRIDAY, path, clock=lambda: FREEZE)


def test_clock_rollback_during_publication_holds(case):
    times = iter([PUBLISH, PUBLISH-timedelta(microseconds=1)])
    with pytest.raises(ValueError, match='clock_changed'):
        publish(case, clock=lambda: next(times))


@pytest.mark.parametrize('monotonic', [lambda: float('nan'), iter([10.0, 9.0]).__next__])
def test_invalid_or_backward_monotonic_clock_holds(case, monotonic):
    with pytest.raises(ValueError): publish(case, monotonic=monotonic)


def test_wall_clock_jump_vs_monotonic_is_rejected(case):
    times = iter([PUBLISH, PUBLISH+timedelta(seconds=20)])
    with pytest.raises(ValueError, match='clock_changed'):
        publish(case, clock=lambda: next(times), monotonic=lambda: 10.0)


def test_competing_owner_refused_without_terminating_or_reclaiming(case):
    lock = case.workspace.root / 'source-publication.lock'
    lock.write_bytes(b'other owner')
    with pytest.raises(FileExistsError): publish(case)
    assert lock.read_bytes() == b'other owner'


def test_no_second_publication_or_provider_checkpoint_reuse(case):
    ref = publish(case)
    before = tree(case.workspace.root)
    with pytest.raises(FileExistsError): publish(case)
    assert tree(case.workspace.root) == before
    session = provider(case, ref)
    session.checkpoint('before_prediction'); session.checkpoint('before_save', generated_at_utc=FREEZE)
    with pytest.raises(ValueError): session.checkpoint('before_save')


def test_freeze_before_cutoff_or_save_before_prediction_rejected(case):
    ref = publish(case); path = reservation(case, ref)
    with pytest.raises(ValueError, match='freeze_before_cutoff'):
        s.Provider(case.workspace, ref, FRIDAY, path, clock=lambda: CUTOFF-timedelta(microseconds=1))
    session = s.Provider(case.workspace, ref, FRIDAY, path, clock=lambda: FREEZE)
    with pytest.raises(ValueError): session.checkpoint('before_save')


def test_production_or_unmarked_workspace_cannot_be_used(case):
    with pytest.raises(ValueError, match='temporary_only'): s.Workspace.create(Path(__file__).parents[1] / 'forbidden')
    fake = s.Workspace(case.root)
    with pytest.raises(FileNotFoundError): fake.check()


def test_acquisition_and_publication_exactly_at_070000_can_pass(factory, tmp_path):
    c = factory(fetched=CUTOFF, created_offset=0)
    c.workspace = s.Workspace.create(tmp_path / 'boundary-output')
    ref = publish(c, clock=lambda: CUTOFF)
    assert s.verify(c.workspace, ref, FRIDAY)[1]['facts']['source_acquired_at_utc'] == CUTOFF.isoformat()


def test_publication_completes_after_cutoff_even_if_started_before(case):
    state = dict(now=CUTOFF-timedelta(seconds=1), mono=10.0)
    def fault(event):
        if event == 'after_publish':
            state.update(now=CUTOFF+timedelta(microseconds=1), mono=11.000001)
    with pytest.raises(ValueError, match='publication_after_cutoff'):
        publish(case, clock=lambda: state['now'], monotonic=lambda: state['mono'], fault=fault)
    assert (case.workspace.root / 'publications' / case.revision).is_dir()
    assert not list(case.workspace.root.glob('receipts/*/receipt.json'))


@pytest.mark.parametrize('field', ['home_score', 'kickoff_time'])
def test_rehashed_publication_cannot_conflict_with_official_raw(case, field):
    import pandas as pd
    directory = case.root / 'official/revisions' / case.revision
    for filename in ['schedule.csv', 'completed_matches.csv']:
        frame = pd.read_csv(directory / filename, dtype=str, keep_default_na=False)
        if field == 'home_score':
            frame.loc[frame.status.eq('completed'), field] = '9'
        else:
            frame.loc[frame.match_date.eq(FRIDAY), field] = '20:00'
        (directory / filename).write_bytes(frame.to_csv(index=False, lineterminator='\n').encode())
    m = w.read_json(directory / 'manifest.json')
    for filename in m['files']: m['files'][filename] = w.sha(directory / filename)
    (directory / 'manifest.json').write_bytes(w.body(m)); case.manifest_sha = w.sha(directory / 'manifest.json')
    with pytest.raises(ValueError, match='raw_.*conflict'):
        publish(case)


def rewrite_receipt(c, ref, change):
    folder = c.workspace.root / 'receipts' / c.revision
    r = w.read_json(folder / 'receipt.json')
    change(r)
    r.pop('receipt_sha256')
    r['receipt_sha256'] = w.digest(r)
    (folder / 'receipt.json').write_bytes(w.body(r))
    seal = w.read_json(folder / 'seal.json')
    seal['receipt_file_sha256'] = w.sha(folder / 'receipt.json')
    (folder / 'seal.json').write_bytes(w.body(seal))
    new = replace(ref, receipt_sha256=w.sha(folder / 'receipt.json'), seal_sha256=w.sha(folder / 'seal.json'))
    (folder / 'reference.json').write_bytes(w.body(new.__dict__))
    return new


@pytest.mark.parametrize('field', ['publication_completed_at_utc', 'publication_started_at_utc', 'receipt_created_at_utc'])
def test_even_rehashed_receipt_cannot_invent_missing_completion_utc(case, field):
    ref = publish(case)
    ref = rewrite_receipt(case, ref, lambda r: r.update({field: None}))
    with pytest.raises(ValueError): s.verify(case.workspace, ref, FRIDAY)


def test_rehashed_receipt_cannot_claim_different_fsync_results(case):
    ref = publish(case)
    ref = rewrite_receipt(case, ref, lambda r: r['verification'].update(payload_fsync=False))
    with pytest.raises(ValueError, match='verification_missing'): s.verify(case.workspace, ref, FRIDAY)


@pytest.mark.parametrize('cap', ['MAX_PAGES', 'MAX_BODY', 'MAX_TOTAL'])
def test_bounded_archive_caps(case, monkeypatch, cap):
    monkeypatch.setattr(s, cap, 1)
    with pytest.raises(ValueError): publish(case)
    assert not list(case.workspace.root.glob('receipts/*/seal.json'))


def test_parent_budget_finite_even_before_0700(case):
    start = at('2026-08-14T06:46:00+09:00')
    wall = iter([start, start+timedelta(seconds=601)])
    mono = iter([0.0, 601.0])
    with pytest.raises(ValueError, match='deadline'):
        publish(case, clock=lambda: next(wall), monotonic=lambda: next(mono))


@pytest.mark.parametrize('issue', ['missing', 'timeout', 'parallel'])
def test_request_utc_timeout_and_parallel_rejected(case, issue):
    p = case.snapshot / 'evidence_001.metadata.json'
    md = w.read_json(p)
    if issue == 'missing': md.pop('request_started_at_utc')
    elif issue == 'timeout': md['request_started_at_utc'] = (FETCH-timedelta(seconds=31)).isoformat()
    else: md['request_started_at_utc'] = (FETCH-timedelta(seconds=3)).isoformat()
    p.write_bytes(w.body(md))
    with pytest.raises(ValueError, match={'missing':'request_UTC_missing','timeout':'request_timeout','parallel':'parallel_requests'}[issue]):
        publish(case)


def test_failed_checkpoint_cannot_resume_even_after_cause_removed(case):
    ref = publish(case); session = provider(case, ref)
    reservation_path = session.reservation
    original = reservation_path.read_bytes()
    reservation_path.write_bytes(original+b' ')
    with pytest.raises(ValueError): session.checkpoint('before_prediction')
    reservation_path.write_bytes(original)
    with pytest.raises(ValueError, match='failed_session_no_resume'): session.checkpoint('before_save')


def test_input_dataframe_mutation_does_not_mutate_provider_source(case):
    ref = publish(case); session = provider(case, ref)
    a = session.checkpoint('before_prediction')
    a['source'].schedule.loc[:, 'kickoff_time'] = '00:01'
    b = session.checkpoint('before_save', generated_at_utc=FREEZE)
    assert set(b['source'].schedule.kickoff_time) == {'19:00'}


@pytest.mark.parametrize('age_excess', [0, 1])
def test_source_freshness_24_hours_boundary(factory, tmp_path, age_excess):
    fetched = CUTOFF-timedelta(hours=24, microseconds=age_excess)
    c = factory(fetched=fetched)
    c.workspace = s.Workspace.create(tmp_path / 'freshness-output')
    if age_excess:
        with pytest.raises(ValueError, match='source_stale'): publish(c)
    else:
        assert s.verify(c.workspace, publish(c), FRIDAY)[0].revision_id == c.revision


def test_provider_clock_rollback_and_wrong_receipt_reference_rejected(case):
    ref = publish(case)
    with pytest.raises(ValueError): s.verify(case.workspace, replace(ref, revision_id='f'*64), FRIDAY)
    path = reservation(case, ref)
    clock = iter([FREEZE, FREEZE, FREEZE, FREEZE-timedelta(microseconds=1)])
    session = s.Provider(case.workspace, ref, FRIDAY, path, clock=lambda: next(clock))
    with pytest.raises(ValueError, match='clock_changed'): session.checkpoint('before_prediction')
    with pytest.raises(ValueError, match='failed_session_no_resume'): session.checkpoint('before_save')


def test_two_publishers_contend_for_one_owned_lane(case):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    entered, released = Event(), Event()
    def fault(event):
        if event == 'before_publish':
            entered.set()
            assert released.wait(5), 'bounded synthetic owner wait'
    with ThreadPoolExecutor(max_workers=1) as pool:
        first = pool.submit(publish, case, monotonic=lambda: 0.0, fault=fault)
        try:
            assert entered.wait(5)
            with pytest.raises(FileExistsError): publish(case)
        finally:
            released.set()
        ref = first.result(timeout=10)
    assert s.verify(case.workspace, ref, FRIDAY)[0].revision_id == case.revision
    assert len(list(case.workspace.root.glob('receipts/*/seal.json'))) == 1


def test_copy_readback_corruption_holds_before_publication(case, monkeypatch):
    original = w.write_new
    changed = []
    def corrupt(path, data):
        original(path, data)
        if '.pending-source-' in str(path) and not changed:
            Path(path).write_bytes(data+b' ')
            changed.append(str(path))
    monkeypatch.setattr(w, 'write_new', corrupt)
    with pytest.raises(ValueError): publish(case)
    assert changed and not list(case.workspace.root.glob('publications/*'))


def test_inherited_result_requires_original_snapshot_and_raw_witness(case, monkeypatch):
    # A later accepted snapshot has no completion page of its own. The original
    # page and acquisition UTC must remain reachable and must be checked too.
    newer = FETCH+timedelta(minutes=5)
    listing = write_source(case.root / 'new-input/listing.html', listing_html(case.fixtures), timestamp=newer.isoformat())
    md = w.read_json(listing.with_suffix('.metadata.json'))
    md['request_started_at_utc'] = (newer-timedelta(milliseconds=500)).isoformat()
    listing.with_suffix('.metadata.json').write_bytes(w.body(md))
    class NewDatetime(datetime):
        @classmethod
        def now(cls, tz=None): return (newer+timedelta(seconds=1)).astimezone(tz)
    monkeypatch.setattr(ongoing, 'datetime', NewDatetime)
    snap = ongoing.create_snapshot(case.root / 'snapshots', listing_html=listing, snapshot_id='synthetic-later')
    assert ongoing.process_snapshot(snap, case.root / 'official')['publication_status'] == 'published'
    p = w.read_json(case.root / 'official/latest.json')
    case.revision, case.manifest_sha = p['revision_id'], p['manifest_sha256']
    ref = publish(case)
    _, receipt = s.verify(case.workspace, ref, FRIDAY)
    assert len(receipt['facts']['snapshot_sha256']) == 2
    old = case.workspace.root / 'publications' / case.revision / 'snapshots' / case.snapshot.name / 'evidence_001.html'
    old.write_bytes(old.read_bytes()+b' ')
    with pytest.raises(ValueError): s.verify(case.workspace, ref, FRIDAY)


def test_accumulating_wall_clock_drift_is_not_hidden_by_small_steps(case):
    wall = iter([PUBLISH, PUBLISH+timedelta(seconds=1.5), PUBLISH+timedelta(seconds=3)])
    with pytest.raises(ValueError, match='clock_changed'):
        publish(case, clock=lambda: next(wall), monotonic=lambda: 0.0)


def test_malformed_manifest_is_an_evidence_hold(case):
    path = case.root / 'official/revisions' / case.revision / 'manifest.json'
    m = w.read_json(path); m['run'] = None
    path.write_bytes(w.body(m)); case.manifest_sha = w.sha(path)
    with pytest.raises(ValueError, match='evidence_missing_or_invalid'): publish(case)


@pytest.mark.parametrize('generated', [None, FREEZE-timedelta(microseconds=1), FREEZE+timedelta(microseconds=1)])
def test_generation_timestamp_must_be_between_prediction_and_save_checks(case, generated):
    ref = publish(case); session = provider(case, ref)
    session.checkpoint('before_prediction')
    with pytest.raises(ValueError, match='generation_'):
        session.checkpoint('before_save', generated_at_utc=generated)


def test_checkpoint_rechecks_actual_clock_after_evidence_validation(factory, tmp_path, monkeypatch):
    c = factory(early_kickoff=True)
    c.workspace = s.Workspace.create(tmp_path / 'early-output')
    ref = publish(c)
    path = reservation(c, ref)
    state = dict(now=FREEZE, mono=0.0)
    session = s.Provider(c.workspace, ref, FRIDAY, path, clock=lambda:state['now'], monotonic=lambda:state['mono'])
    original = s.verify
    def delayed(*args):
        result = original(*args)
        state.update(now=FREEZE+timedelta(seconds=30), mono=30.0)
        return result
    monkeypatch.setattr(s, 'verify', delayed)
    with pytest.raises(ValueError, match='kickoff_elapsed'): session.checkpoint('before_prediction')
