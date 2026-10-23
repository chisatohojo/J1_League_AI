"""Disabled production candidates, tested using Phase4 capabilities and mocks.

No CLI, real transport, deserializer, activation switch or production writer.
Production evidence requires a new explicit contract; synthetic attestations
are never relabelled as real acquisition/publication/model execution receipts.
"""
from copy import deepcopy
from dataclasses import dataclass
from datetime import timedelta
import hashlib
import json
import re
from urllib.parse import urlparse

import numpy as np

from src.modeling import champion_prediction as champion
from src.modeling import weekend_batch as w
from src.modeling import weekend_source as source
from src.modeling.weekend_integration import ReceiptBoundBackend
from src.modeling.weekend_staging_windows import StagingHold, need

SCOPE = "STAGING_MOCK_ONLY"
PRODUCTION_ENABLED = False
PRODUCTION_CONTRACT = {
    "format_version": "champion-weekend-production-source-v1-PROPOSED",
    "status": "NOT_ACCEPTED_BY_ANY_RUNTIME_READER",
    "required": ["official_revision", "official_manifest_sha256", "publication_receipt_sha256",
                 "reference_sha256", "acquisition_UTC", "publication_completed_UTC", "freeze_UTC",
                 "reservation_sha256", "fixture_identity_sha256", "elo_snapshot_sha256",
                 "model_payload_sha256", "input_sha256", "output_sha256", "generated_UTC",
                 "before_save_checkpoint", "post_publication_receipt", "commit_state"],
    "production_enabled": False,
}


def production_entrypoint(*args, **kwargs):
    raise StagingHold("separate_real_source_model_and_deployment_approval_required")


def inspect_champion_bundle(root):
    """Hash/JSON checks only. Never deserialize the fixed model or scaler."""
    directory = w.safe(root) / champion.ARTIFACT_PATH
    need(set(p.name for p in directory.iterdir()) == set(champion.FILE_PINS), "champion_bundle_files")
    for filename, expected in champion.FILE_PINS.items():
        need(w.sha(w.safe(directory / filename)) == expected, "champion_payload_changed")
    md = w.read_json(directory / "metadata.json")
    need(md["feature_list"] == ["elo_diff"] and md["model_version"] == champion.CHAMPION_VERSION
         and md["training_row_count"] == 3588
         and md["role"] == "operational_champion" and md["target_mapping"] == {"0":"Away","1":"Draw","2":"Home"}
         and md["elo_parameters"]["K"] == 30.0 and md["elo_parameters"]["home_advantage"] == 175.0,
         "champion_metadata_contract")
    need(all(md[key] == champion.FILE_PINS[filename] for key,filename in (
        ("model_hash","model.joblib"),("scaler_hash","scaler.joblib"),("training_manifest_hash","training_manifest.csv"))),
        "champion_metadata_payload_link")
    return dict(model_identity=md["model_version"], payload_sha256=dict(champion.FILE_PINS),
                feature_columns=["elo_diff"], class_order=[0,1,2], model_loaded=False, scaler_loaded=False)


@dataclass(frozen=True)
class CommunicationLimits:
    max_requests: int = 12
    timeout_seconds: int = 10
    retry_limit: int = 0
    interval_seconds: int = 5
    max_body_bytes: int = 2*1024*1024
    max_total_bytes: int = 24*1024*1024
    deadline_seconds: int = 180

    def check(self):
        fields = vars(self)
        need(all(type(v) is int for v in fields.values()), "integer_communication_limits")
        need(1 <= self.max_requests <= 12 and 1 <= self.timeout_seconds <= 10
             and self.retry_limit == 0 and self.interval_seconds >= 5
             and 1 <= self.max_body_bytes <= 2*1024*1024
             and self.max_body_bytes <= self.max_total_bytes <= 24*1024*1024
             and 1 <= self.deadline_seconds <= 600, "bounded_communication_limits")


class MockHTTP:
    """Literal in-memory responses only. No socket/URL opener is implemented."""
    def __init__(self, responses):
        self.responses, self.called = deepcopy(responses), []

    def get(self, url):
        self.called.append(url)
        return self.responses[url]


class SourceWorkerCandidate:
    """Prefer one selected night publication; never discover/fallback to latest."""
    def __init__(self, workspace, reference, friday):
        need(type(workspace) is source.Workspace and type(reference) is source.Reference,
             "existing_synthetic_capability_required")
        self.workspace, self.reference, self.friday = workspace, reference, friday

    def select_previous_night(self):
        current, receipt = source.verify(self.workspace, self.reference, self.friday)
        acquired = source.utc(receipt["facts"]["source_acquired_at_utc"])
        start = w.stamp(w.period(self.friday)["information_cutoff"]) - timedelta(hours=9)
        need(start <= acquired < start+timedelta(hours=2), "selected_night_2200_source_required")
        # SHA/UTC/raw/metadata/history/fixtures are verified by the unchanged verifier.
        return current, receipt

    def independent_0645_real_acquisition(self, *args, **kwargs):
        raise StagingHold("0645_acquisition_requires_separate_explicit_approval")

    def collect_mock(self, arena, urls, transport, *, clock, limits=CommunicationLimits()):
        need(type(transport) is MockHTTP, "mock_HTTP_only")
        limits.check()
        need(type(urls) is tuple and 0 < len(urls) <= limits.max_requests
             and len(set(urls)) == len(urls), "fixed_unique_URL_set")
        need(all(urlparse(u).scheme == "https" and urlparse(u).hostname == "data.j-league.or.jp"
                 and not urlparse(u).username and not urlparse(u).fragment for u in urls), "official_URL_identity_required")
        need(set(transport.responses) == set(urls), "mock_response_set")
        session = w.digest(dict(urls=urls, scope=SCOPE))
        # Consumed before the first mock request, including failed/uncertain responses.
        arena.write_new("mock-HTTP-attempt-"+session+".json", w.body(dict(scope=SCOPE, urls=urls)))
        begun = source.utc(clock())
        cutoff = w.stamp(w.period(self.friday)["information_cutoff"])
        need(begun <= cutoff, "mock_acquisition_after_0700")
        previous = None
        total, receipts = 0, []
        for index,url in enumerate(urls):
            started = source.utc(clock())
            need(started >= begun and (started-begun).total_seconds() <= limits.deadline_seconds, "mock_global_deadline")
            need(previous is None or (started-previous).total_seconds() >= limits.interval_seconds, "mock_rate_limit")
            name = f"mock-source-{session[:12]}-{index:02}"
            arena.write_new(name+".request.json",w.body(dict(scope=SCOPE,url=url,request_started_at_utc=started.isoformat())))
            response, finished = None, None
            try:
                response = transport.get(url)
                finished = source.utc(clock())
                need(started <= finished and (finished-started).total_seconds() <= limits.timeout_seconds
                     and (finished-begun).total_seconds() <= limits.deadline_seconds, "mock_timeout")
                need(finished <= cutoff, "mock_acquisition_after_0700")
                need(type(response) is dict and set(response)=={"status","final_url","body","tls_verified"}, "mock_response_schema")
                need(response["status"] == 200 and response["final_url"] == url and response["tls_verified"] is True,
                     "mock_access_TLS_redirect_or_status_failure")
                raw = response["body"]
                need(type(raw) is bytes and 0 < len(raw) <= limits.max_body_bytes, "mock_body_cap")
                total += len(raw)
                need(total <= limits.max_total_bytes, "mock_total_body_cap")
            except Exception as error:
                raw = response.get("body") if type(response) is dict else None
                saved_raw = type(raw) is bytes and 0 < len(raw) <= limits.max_body_bytes
                if saved_raw:
                    arena.write_new(name+".unverified.html",raw)
                arena.write_new(name+".HOLD.json",w.body(dict(scope=SCOPE,url=url,state="HOLD",
                    request_started_at_utc=started.isoformat(),response_completed_at_utc=finished.isoformat() if finished else None,
                    failure_type=type(error).__name__,reason=str(error),raw_saved=saved_raw,
                    production_admission=False,actual_HTTP_requests=0)))
                raise
            saved = arena.write_new(name+".html",raw)
            md = dict(scope=SCOPE, evidence_kind="MOCK_HTTP_NOT_REAL_ACQUISITION", requested_url=url,
                      request_started_at_utc=started.isoformat(), fetched_at_utc=finished.isoformat(),
                      raw_sha256=saved["sha256"], bytes=len(raw), HTTP_status=200, simulated_TLS_verified=True)
            arena.write_new(name+".json",w.body(md))
            receipts.append(md); previous = finished
        return receipts


class MockChampionAdapter:
    """Fixed object/code/byte witnesses, transform-only, no loader or fit API."""
    def __init__(self, artifact, witness):
        need(getattr(artifact.scaler,"synthetic_only",None) is True
             and getattr(artifact.model,"synthetic_only",None) is True, "marked_mock_estimator_required")
        need(tuple(artifact.model.classes_) == (0,1,2), "class_order")
        self.original, self.witness = artifact, dict(witness)
        self.expected = None
        self.verify()
        adapter = self

        class Scaler:
            synthetic_only = True
            def transform(self, values):
                adapter.verify()
                need(adapter.expected is not None and np.array_equal(values,adapter.expected)
                     and values.ndim==2 and values.shape[1]==1, "common_snapshot_elo_diff_contract")
                result = adapter.original.scaler.transform(values.copy())
                need(np.asarray(result).shape==values.shape and np.isfinite(result).all(), "transform_contract")
                return result

        class Model:
            synthetic_only = True
            @property
            def classes_(self):
                adapter.verify()
                return np.asarray((0,1,2))
            def predict_proba(self, matrix):
                adapter.verify()
                return adapter.original.model.predict_proba(matrix)

        self.artifact = champion.ChampionArtifact(Scaler(),Model(),artifact.training.copy(deep=True))

    def verify(self):
        need(set(self.witness)=={"path","sha256"} and w.sha(w.safe(self.witness["path"]))==self.witness["sha256"], "mock_artifact_witness_changed")
        need(getattr(self.original.model,"synthetic_only",None) is True
             and getattr(self.original.scaler,"synthetic_only",None) is True
             and tuple(self.original.model.classes_)==(0,1,2), "mock_artifact_contract_changed")

    def bind_snapshot(self, snapshot):
        self.verify()
        targets = snapshot["targets"]
        self.expected = np.asarray([snapshot["features"][t["fixture_key"]] for t in targets],dtype=float).reshape(-1,1)
        need(np.isfinite(self.expected).all(), "snapshot_feature_finite")
        self.snapshot_sha256 = w.digest(snapshot)


class StagingReceiptBackend(ReceiptBoundBackend):
    """Reuse Phase4 algorithm and manifest. This subclass is still synthetic."""
    def __init__(self, workspace, adapter, special, witnesses, source_workspace, reference, **kwargs):
        need(type(adapter) is MockChampionAdapter, "mock_Champion_adapter_required")
        self.adapter = adapter
        super().__init__(workspace, adapter.artifact, special, witnesses, source_workspace, reference, **kwargs)

    def before_inference(self, current, snapshot, pins, clock):
        super().before_inference(current,snapshot,pins,clock)
        self.adapter.bind_snapshot(snapshot)
        pins[self.adapter.witness["path"]] = self.adapter.witness["sha256"]

    def before_commit(self, prepared, records, bindings, clock):
        self.adapter.verify()
        need(w.digest(prepared.context["snapshot"])==self.adapter.snapshot_sha256, "snapshot_changed")
        return super().before_commit(prepared,records,bindings,clock)

    def before_visibility(self, prepared, clock):
        self.adapter.verify()
        super().before_visibility(prepared,clock)
