"""Receipt-bound synthetic weekend execution; no HTTP/model-loader entry point."""
from copy import deepcopy
from pathlib import Path
import time

import pandas as pd

from scripts import build_dashboard_feed as feed
from src.modeling import weekend_batch as w
from src.modeling import weekend_source as source

FORMAT = "champion-weekend-v2-source-v1"
PREFIX = "weekend-v2-source-"
PROOF = "weekend-source-binding-v1"
CHECKPOINT_KEYS = {"snapshot_id", "receipt_sha256", "frozen_at_utc", "checkpoint_at_utc", "source_acquired_at_utc"}
MANIFEST_KEYS = {"format_version", "scope", "policy", "period", "official_revision", "official_manifest_sha256", "fixture_set_sha256", "snapshot_id", "model_identity", "input_sha256", "generated_at", "committed_at", "count", "completeness", "commit_state", "files", "source_binding_sha256"}


def applicability(current, targets, window, *, completed):
    rows = current.schedule.loc[current.schedule.match_date.between(window["start"], window["end"])]
    w.need(set(rows.fixture_key) == {t["fixture_key"] for t in targets}
           and rows.fixture_key.is_unique and rows.status.isin(["scheduled", "completed"] if completed else ["scheduled"]).all(), "HOLD_REVIEW_ON_SCHEDULE_CHANGE")
    bykey = rows.set_index("fixture_key")
    for t in targets:
        row = bykey.loc[t["fixture_key"]]
        field = "match_page_id" if t["match_id_namespace"] == feed.MATCH_PAGE_NAMESPACE else "data_site_match_id"
        w.need(all(row[k] == t[k] for k in ("match_date", "kickoff_time", "home_team_id", "away_team_id"))
               and row[field] == t["match_id"], "HOLD_REVIEW_ON_SCHEDULE_CHANGE")


class ReceiptBoundBackend(w.OfflineWeekendBackend):
    batch_format = FORMAT
    batch_prefix = PREFIX

    def __init__(self, workspace, artifact, special, witnesses, source_workspace, reference, *, monotonic=time.monotonic):
        super().__init__(workspace, artifact, special, witnesses)
        w.need(isinstance(source_workspace, source.Workspace) and isinstance(reference, source.Reference), "source_capability_required")
        source_workspace.check()
        self.source_workspace, self.reference, self.monotonic = source_workspace, reference, monotonic
        self.provider = None

    def fixed_source(self, *, clock=None):
        if clock is not None:
            self.execution_clock = clock
        if getattr(self, "execution_clock", None) is not None:
            w.need(source.utc(self.reference.ready_at_utc) <= w.stamp(self.execution_clock()), "source_not_yet_ready")
        current, _ = source.verify(self.source_workspace, self.reference, self.window["start"])
        self.verify_source(current)
        return current

    def verify_source(self, current):
        fixed, receipt = source.verify(self.source_workspace, self.reference, self.window["start"])
        w.need(current.revision_id == fixed.revision_id and current.manifest_sha == fixed.manifest_sha
               and current.schedule.equals(fixed.schedule) and current.completed.equals(fixed.completed), "pinned_source_projection")
        bundle = self.source_workspace.root / "publications" / self.reference.revision_id
        w.need(w.sha(self.source / feed.TEAM_MASTER_PATH) == receipt["facts"]["files"]["teams.csv"], "pinned_team_master")
        pins = {str(bundle / p): h for p, h in receipt["facts"]["files"].items()}
        folder = self.source_workspace.root / "receipts" / self.reference.revision_id
        for name in ("receipt.json", "seal.json", "reference.json"):
            pins[str(folder / name)] = w.sha(folder / name)
        for code in (Path(__file__), Path(source.__file__)):
            pins[str(code)] = w.sha(code)
        return pins

    def latest_applicability(self):
        from scripts.update_champion_dashboard import official
        current = official(self.source, self.runtime / "official")
        if getattr(self, "execution_clock", None) is not None:
            w.need(w.stamp(current.observed_at) <= w.stamp(self.execution_clock()), "future_applicability")
        return current

    def review(self, current, saved):
        self.verify_source(current)
        published = [w.read_batch(p) for p in (self.runtime / "batches").glob(w.PREFIX + "*")]
        published = [item for item in published if item[2]["period"] == self.window]
        if published:
            w.need(len(published) == 1 and published[0][2]["format_version"] == FORMAT, "partial_or_legacy_saved")
            records, _, _, context = published[0]
            expected = context["snapshot"]["targets"]
            reservation = self.runtime / "weekend-reservations" / (self.window["start"] + ".json")
            w.need(w.sha(w.safe(reservation)) == context["reservation_sha256"], "reservation_changed")
            proof = w.read_json(next(p for p in (self.runtime / "batches").glob(PREFIX + "*")
                                    if w.read_json(p / "manifest.json")["period"] == self.window) / "source-proof.json")
            w.need(proof["reference"] == self.reference.__dict__, "selected_receipt_changed")
            keys = {t["fixture_key"] for t in expected}
            w.need([r for r in saved if r["fixture_key"] in keys] == records, "saved_values_changed")
            applicability(self.latest_applicability(), expected, self.window, completed=True)
            return True
        applicability(self.latest_applicability(), w.target_identity(current, self.window), self.window, completed=False)
        return super().review(current, saved)

    def prepare(self, current, saved, now, clock):
        self.execution_clock = clock
        if self.review(current, saved):
            return None
        attempt = self.runtime / "weekend-attempts" / (self.window["start"] + ".json")
        w.need(not attempt.exists(), "incomplete_attempt_no_resume")
        path = self.runtime / "weekend-reservations" / (self.window["start"] + ".json")
        self.provider = source.Provider(self.source_workspace, self.reference, self.window["start"], path,
                                        clock=clock, monotonic=self.monotonic)
        return super().prepare(current, saved, self.provider.frozen_at, clock)

    def before_inference(self, current, snapshot, pins, clock):
        pins.update(self.verify_source(current))
        self.prediction_check = self.provider.checkpoint("before_prediction", applicability=self.latest_applicability())
        w.need(snapshot["frozen_at"] == self.prediction_check["frozen_at_utc"], "freeze_conflict")

    def before_commit(self, prepared, records, bindings, clock):
        checkpoint = self.provider.checkpoint("before_save", generated_at_utc=prepared.context["generated_at"],
                                              applicability=self.latest_applicability())
        folder = self.source_workspace.root / "receipts" / self.reference.revision_id
        proof = dict(format_version=PROOF, scope=w.SCOPE, reference=self.reference.__dict__,
            reference_sha256=w.sha(folder / "reference.json"), receipt=w.read_json(folder / "receipt.json"),
            seal=w.read_json(folder / "seal.json"), source_snapshot_id=self.provider.identity,
            before_prediction={k:v for k,v in self.prediction_check.items() if k in CHECKPOINT_KEYS},
            before_save={k:v for k,v in checkpoint.items() if k in CHECKPOINT_KEYS},
            reservation_id=self.window["start"], reservation_sha256=prepared.context["reservation_sha256"],
            elo_snapshot_id=prepared.context["snapshot_id"],
            prediction_input_sha256=w.digest(prepared.context["snapshot"]["features"]),
            prediction_output_sha256=feed.sha(pd.DataFrame(records, columns=feed.CHAMPION_COLUMNS).to_csv(index=False,lineterminator="\n").encode()))
        binding = dict(format_version=PROOF, sha256=w.digest(proof))
        prepared.context["source_binding"] = binding
        self.proof = proof
        return {"source-proof.json": w.body(proof)}

    def manifest_extension(self, prepared):
        return dict(source_binding_sha256=prepared.context["source_binding"]["sha256"])

    def before_visibility(self, prepared, clock):
        current = self.fixed_source()
        applicability(self.latest_applicability(), prepared.context["snapshot"]["targets"], self.window, completed=False)
        now = self.provider.timer.sample("before_visibility_verified")
        self.provider._check(current, now)


@source.evidence_errors
def read_bound_batch(directory, *, staging=False):
    directory = w.safe(directory)
    m = w.read_json(directory / "manifest.json")
    w.need(set(m) == MANIFEST_KEYS and m["format_version"] == FORMAT and m["scope"] == w.SCOPE
           and m["policy"] == w.POLICY and m["commit_state"] == "COMMITTED" and m["completeness"] == "PASS", "bound_manifest")
    w.need(m["period"] == w.period(m["period"]["start"]), "manifest_period")
    w.need(staging or directory.name == PREFIX + w.sha(directory / "manifest.json"), "manifest_address")
    w.need(set(m["files"]) == {"predictions.csv", "bindings.csv", "snapshot.json", "source-proof.json"}
           and {p.name for p in directory.iterdir()} == set(m["files"]) | {"manifest.json"}, "bound_files")
    for name, digest in m["files"].items():
        w.need(w.sha(w.safe(directory / name)) == digest, "batch_sha")
    c = w.read_json(directory / "snapshot.json")
    w.need(set(c) == {"scope", "snapshot", "snapshot_id", "reservation_sha256", "generated_at", "source_binding"}, "bound_context")
    proof = w.read_json(directory / "source-proof.json")
    w.need(set(proof) == {"format_version", "scope", "reference", "reference_sha256", "receipt", "seal", "source_snapshot_id", "before_prediction", "before_save", "reservation_id", "reservation_sha256", "elo_snapshot_id", "prediction_input_sha256", "prediction_output_sha256"}, "proof_schema")
    w.need(proof["format_version"] == PROOF and proof["scope"] == w.SCOPE, "proof_scope")
    w.need(w.digest(proof) == m["source_binding_sha256"] == m["files"]["source-proof.json"]
           and c["source_binding"] == dict(format_version=PROOF,sha256=w.digest(proof)), "source_binding_sha")
    ref = source.Reference(**proof["reference"])
    w.need(w.digest(ref.__dict__) == proof["reference_sha256"], "reference_sha")
    facts = proof["receipt"]["facts"]
    source.validate_record(ref, proof["receipt"], proof["seal"], facts, m["period"]["start"])
    s = c["snapshot"]
    w.need(facts["revision_id"] == ref.revision_id == s["official_revision"]
           and facts["publication_manifest_sha256"] == s["official_manifest_sha256"]
           and facts["targets"] == s["targets"] and facts["period"] == s["period"]
           and facts["source_acquired_at_utc"] == w.utc(s["source_observed_at"]), "source_snapshot_conflict")
    identity = w.digest(dict(scope=w.SCOPE, policy=w.POLICY, reference=ref.__dict__, frozen_at_utc=s["frozen_at"],
        target_sha256=w.digest(s["targets"]), reservation_sha256=c["reservation_sha256"]))
    w.need(proof["source_snapshot_id"] == identity and proof["reservation_id"] == m["period"]["start"]
           and proof["reservation_sha256"] == c["reservation_sha256"] and proof["elo_snapshot_id"] == c["snapshot_id"]
           and proof["prediction_input_sha256"] == w.digest(s["features"])
           and proof["prediction_output_sha256"] == m["files"]["predictions.csv"], "proof_prediction_binding")
    for phase in ("before_prediction", "before_save"):
        cp = proof[phase]
        w.need(set(cp) == CHECKPOINT_KEYS and cp["snapshot_id"] == identity and cp["receipt_sha256"] == ref.receipt_sha256
               and cp["frozen_at_utc"] == s["frozen_at"] and cp["source_acquired_at_utc"] == facts["source_acquired_at_utc"], "checkpoint_binding")
    w.need(source.utc(ref.ready_at_utc) <= source.utc(s["frozen_at"]) <= source.utc(proof["before_prediction"]["checkpoint_at_utc"])
           <= source.utc(m["generated_at"]) <= source.utc(proof["before_save"]["checkpoint_at_utc"])
           <= source.utc(m["committed_at"]), "checkpoint_chronology")
    core_m, core_c = deepcopy(m), deepcopy(c)
    core_m.pop("source_binding_sha256"); core_m["format_version"] = w.FORMAT
    core_m["files"].pop("source-proof.json"); core_c.pop("source_binding")
    records, bindings, _, _ = w.validate_core(core_m, core_c, (directory / "predictions.csv").read_bytes(), (directory / "bindings.csv").read_bytes())
    return records, bindings, m, c
