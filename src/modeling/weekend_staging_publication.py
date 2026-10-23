"""NTFS staging envelope around an unchanged Phase4 saved batch.

The envelope is deliberately not an operational daily/v2 publication. Readers
require post-rename receipt AND seal. Uncertain/failed runs are never resumed.
"""
from pathlib import Path
import uuid

from scripts import update_champion_dashboard as updater
from src.modeling import champion_prediction as champion
from src.modeling import weekend_batch as w
from src.modeling import weekend_integration as integration
from src.modeling.weekend_production_staging import SCOPE, SourceWorkerCandidate, StagingReceiptBackend
from src.modeling.weekend_staging_windows import need, read_staging, publish_staging

FORMAT = "weekend-production-staging-envelope-v1"


def forbidden(*args, **kwargs):
    raise ValueError("staging_must_not_call_real_collector_or_predictor")


class Publisher:
    def __init__(self, arena):
        self.arena = arena
        arena.check()

    def read(self, request_id):
        return read_staging(self.arena,request_id,champion.FILE_PINS,integration.read_bound_batch)

    def copy_saved(self, backend, request_id, *, fault=lambda event: None):
        need(type(backend) is StagingReceiptBackend, "staging_backend_required")
        backend.workspace.check(backend.source,backend.runtime)
        backend.adapter.verify()
        paths=[p for p in (backend.runtime/"batches").glob(integration.PREFIX+"*")
               if w.read_json(p/"manifest.json")["period"]==backend.window]
        need(len(paths)==1, "one_complete_saved_batch_required")
        original=paths[0]
        return self.stage_saved(original, request_id, backend.adapter.witness["sha256"],
                                recheck=backend.adapter.verify, fault=fault)

    def stage_saved(self, original, request_id, mock_witness_sha256, *, recheck, fault=lambda event: None):
        """Copy a verified synthetic batch under the caller's owned transaction.

        This storage boundary is also exercised by the test-only Windows child.
        It does not generate predictions, attach to runtime or accept real scope.
        """
        records, _, _, _ = integration.read_bound_batch(original)
        return publish_staging(self.arena,original,request_id,mock_witness_sha256,champion.FILE_PINS,
            {row["fixture_key"] for row in records},validate_saved=integration.read_bound_batch,
            recheck=recheck,fault=fault)

    def run_mock(self, backend, source_root, runtime_root, config, *, clock, slot="morning", fault=lambda event: None):
        need(type(backend) is StagingReceiptBackend and slot in {"morning","evening"}, "mock_backend_and_slot_required")
        backend.bind(source_root,runtime_root,config)
        need(backend.window["start"]!="2026-10-23", "existing_partial_saved_weekend_excluded")
        selected=SourceWorkerCandidate(backend.source_workspace,backend.reference,backend.window["start"])
        selected.select_previous_night()
        reservation=backend.runtime/"weekend-reservations"/(backend.window["start"]+".json")
        request_id=w.digest(dict(scope=SCOPE,reference=backend.reference.__dict__,reservation_sha256=w.sha(w.safe(reservation))))
        if self.arena.path("batch-"+request_id).exists():
            # Never revive uncertain terminal state even if a sealed batch exists.
            need(not self.arena.path("publication.lock").exists(), "retained_lock_manual_review_required")
            return request_id,self.read(request_id)
        need(slot=="morning", "evening_prediction_generation_forbidden")
        with self.arena.transaction(request_id):
            updater.run_update(source_root,runtime_root,slot,config,collector=forbidden,predictor=forbidden,
                               clock=clock,weekend_backend=backend)
            self.copy_saved(backend,request_id,fault=fault)
        return request_id,self.read(request_id)

    def recovery_report(self):
        """Read-only triage, never remove lock/attempt/staging or invoke a backend."""
        self.arena.check()
        return dict(state="HOLD_MANUAL_REVIEW" if self.arena.path("publication.lock").exists() else "READ_ONLY",
                    entries={p.name:w.sha(p) for p in self.arena.root.iterdir() if p.is_file()},
                    directory_names=sorted(p.name for p in self.arena.root.iterdir() if p.is_dir()),
                    auto_resume=False,auto_delete=False,production_admission=False)
