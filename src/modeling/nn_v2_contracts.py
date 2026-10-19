"""Pure research contract validation. No enrollment, prediction writer or clock override."""
from collections import Counter
from datetime import datetime, timedelta, timezone
import re

import numpy as np

from src.features.nn_research_timing import POLICY
from src.modeling.nn_residual_v2 import FORM_FEATURES, finite

SHA = re.compile(r"[0-9a-f]{64}\Z")
STAMP = re.compile(r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:\.(\d{1,7}))?(Z|[+-](?:[01]\d|2[0-3]):[0-5]\d)\Z")


def exact(value, keys):
    if not isinstance(value, dict) or set(value) != set(keys):
        raise ValueError("Contract field set mismatch")


def text(value):
    if (not isinstance(value, str) or not value.strip() or value != value.strip()
            or any(ord(ch) < 32 or ord(ch) == 127 for ch in value)):
        raise ValueError("Nonblank exact text required")
    return value


def digest(value):
    if not isinstance(value, str) or not SHA.fullmatch(value):
        raise ValueError("Lowercase SHA-256 required")


def stamp(value):
    """Integer UTC 100ns ticks; preserve seventh decimal when comparing deadlines."""
    if not isinstance(value, str) or not (m := STAMP.fullmatch(value)) or value.endswith("-00:00"):
        raise ValueError("Aware ISO timestamp with at most 7 fractional digits required")
    base = datetime.fromisoformat(m[1] + ("+00:00" if m[3] == "Z" else m[3]))
    delta = base.astimezone(timezone.utc) - datetime(1970, 1, 1, tzinfo=timezone.utc)
    return (delta.days*86400 + delta.seconds)*10_000_000 + int((m[2] or "").ljust(7, "0"))


def jst_day(value):
    stamp(value)
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(
        timezone(timedelta(hours=9))).date()


def positive_int(value):
    if type(value) is not int or value <= 0:
        raise ValueError("Positive integer required")


def origin(value):
    if value not in ("synthetic", "real"):
        raise ValueError("Explicit data origin required")


def validate_artifact_manifest(m):
    exact(m, ("schema", "role", "data_origin", "study_id", "residual_sha256", "baseline_sha256",
              "implementation_sha256", "spec_sha256", "training_manifest_sha256", "input_sha256",
              "feature_order", "class_order", "timing_policy", "source_rows", "residual_rows", "sealed_at"))
    if m["schema"] != "nn_v2_study_artifact_manifest_v1" or m["role"] != "research_only_not_champion":
        raise ValueError("Research artifact role mismatch")
    origin(m["data_origin"]); text(m["study_id"])
    for k in ("residual_sha256", "baseline_sha256", "implementation_sha256", "spec_sha256", "training_manifest_sha256"):
        digest(m[k])
    if not isinstance(m["input_sha256"], dict) or not m["input_sha256"]:
        raise ValueError("Input pins required")
    for k, v in m["input_sha256"].items():
        text(k); digest(v)
    if (m["feature_order"] != list(FORM_FEATURES) or m["class_order"] != [0, 1, 2]
            or any(type(c) is not int for c in m["class_order"]) or m["timing_policy"] != POLICY):
        raise ValueError("Artifact feature/class/timing contract mismatch")
    positive_int(m["source_rows"]); positive_int(m["residual_rows"])
    if m["residual_rows"] >= m["source_rows"]:
        raise ValueError("Seed population must be excluded from residual rows")
    if m["data_origin"] == "real" and (m["source_rows"], m["residual_rows"]) != (3588, 2976):
        raise ValueError("Fixed real training population mismatch")
    stamp(m["sealed_at"])


def validate_enrollment(plan, *, now):
    exact(plan, ("schema", "state", "data_origin", "study_id", "competition", "t0", "spec_frozen_at",
                 "artifact_sealed_at", "schedule_observed_at", "official_revision", "r_start", "fixtures"))
    if (plan["schema"] != "nn_v2_enrollment_proposal_v1" or plan["state"] != "proposal"
            or plan["competition"] != "2026_27_ordinary_J1"):
        raise ValueError("Enrollment proposal scope mismatch")
    origin(plan["data_origin"]); text(plan["study_id"]); digest(plan["official_revision"])
    t0, spec, sealed, observed, clock = (stamp(s) for s in
        (plan["t0"], plan["spec_frozen_at"], plan["artifact_sealed_at"], plan["schedule_observed_at"], now))
    if not spec <= sealed <= t0 <= clock or observed > t0:
        raise ValueError("T0/seal/observation order mismatch")
    positive_int(plan["r_start"])
    if plan["r_start"] + 19 > 38 or not isinstance(plan["fixtures"], list) or len(plan["fixtures"]) != 200:
        raise ValueError("20 complete official rounds / 200 fixtures required")
    keys, official, rounds, clubs = set(), set(), Counter(), {}
    for f in plan["fixtures"]:
        exact(f, ("fixture_key", "round", "home_team_id", "away_team_id", "kickoff", "status",
                  "namespace", "official_id", "mapping_status"))
        key = text(f["fixture_key"])
        home, away = text(f["home_team_id"]), text(f["away_team_id"])
        positive_int(f["round"])
        if key in keys or home == away or f["status"] != "scheduled" or stamp(f["kickoff"]) <= clock:
            raise ValueError("Duplicate, started or non-scheduled fixture")
        if f["namespace"] != "jleague_match_page":
            raise ValueError("Official namespace mismatch")
        if f["official_id"] is None:
            if f["mapping_status"] != "pending":
                raise ValueError("Unresolved official identity must remain pending")
        else:
            mid = f["official_id"]
            if not isinstance(mid, str) or not re.fullmatch(r"[0-9]+", mid) or f["mapping_status"] != "verified" or mid in official:
                raise ValueError("Duplicate/invalid official identity")
            official.add(mid)
        keys.add(key); rounds[f["round"]] += 1
        team_set = clubs.setdefault(f["round"], set())
        if home in team_set or away in team_set:
            raise ValueError("Club appears twice in one official round")
        team_set.update((home, away))
    expected = set(range(plan["r_start"], plan["r_start"] + 20))
    if set(rounds) != expected or any(n != 10 for n in rounds.values()):
        raise ValueError("Incomplete/nonconsecutive official round set")
    if len({frozenset(s) for s in clubs.values()}) != 1:
        raise ValueError("Competition club population mismatch")


def validate_prediction(record, plan):
    if not isinstance(plan, dict) or "t0" not in plan:
        raise ValueError("Enrollment proposal required")
    validate_enrollment(plan, now=plan["t0"])
    exact(record, ("schema", "prediction_type", "data_origin", "study_id", "model_version", "fixture",
                   "generated_at", "readback_at", "official_revision", "source_witness_sha256",
                   "baseline_sha256", "residual_sha256", "feature_schema_sha256", "history_cutoff",
                   "source_observed_at", "run_id", "class_order", "base_probabilities", "residual_probabilities"))
    if record["schema"] != "nn_v2_paired_prediction_v1" or record["prediction_type"] != "research_v2_saved_pre_match":
        raise ValueError("Prediction type mismatch")
    if record["data_origin"] != plan["data_origin"] or record["study_id"] != plan["study_id"]:
        raise ValueError("Prediction study/origin mismatch")
    text(record["model_version"])
    text(record["run_id"])
    for k in ("official_revision", "source_witness_sha256", "baseline_sha256", "residual_sha256", "feature_schema_sha256"):
        digest(record[k])
    if record["class_order"] != [0, 1, 2] or any(type(c) is not int for c in record["class_order"]):
        raise ValueError("Prediction class order mismatch")
    f = record["fixture"]
    if not isinstance(f, dict):
        raise ValueError("Prediction fixture object required")
    members = [item for item in plan["fixtures"] if item["fixture_key"] == f.get("fixture_key")]
    if len(members) != 1 or f != members[0] or f["mapping_status"] != "verified":
        raise ValueError("Prediction fixture not verified/enrolled")
    if not stamp(plan["t0"]) <= stamp(record["generated_at"]) <= stamp(record["readback_at"]) < stamp(f["kickoff"]):
        raise ValueError("Prediction not durably saved before kickoff")
    cutoff = jst_day(f["kickoff"]).isoformat() + "T00:00:00+09:00"
    if (stamp(record["history_cutoff"]) != stamp(cutoff)
            or stamp(record["source_observed_at"]) > stamp(record["generated_at"])):
        raise ValueError("Prediction history/source cutoff mismatch")
    for k in ("base_probabilities", "residual_probabilities"):
        p = finite(record[k], (3,))
        if (p < 0).any() or (p > 1).any() or abs(p.sum() - 1) > 1e-12:
            raise ValueError("Invalid saved probabilities")


def validate_prediction_batch(records, plan):
    """Validate only: no file is created and no target is registered."""
    if not isinstance(records, list) or not records:
        raise ValueError("Empty paired prediction batch")
    if not isinstance(plan, dict) or "t0" not in plan:
        raise ValueError("Enrollment proposal required")
    # The proposal itself must already be a valid pre-kickoff enrollment set.
    validate_enrollment(plan, now=plan["t0"])
    for record in records:
        validate_prediction(record, plan)
    days = {jst_day(r["fixture"]["kickoff"]) for r in records}
    ids = [r["fixture"]["fixture_key"] for r in records]
    if len(days) != 1 or len(set(ids)) != len(ids):
        raise ValueError("Mixed-day or duplicate prediction batch")
    expected = {f["fixture_key"] for f in plan["fixtures"] if jst_day(f["kickoff"]) in days}
    if set(ids) != expected:
        raise ValueError("Partial enrolled date batch")
    # Flush/readback for all rows must precede the earliest kickoff in the batch.
    if max(stamp(r["readback_at"]) for r in records) >= min(stamp(r["fixture"]["kickoff"]) for r in records):
        raise ValueError("Partial batch saved after first kickoff")


def validate_audit_manifest(m):
    exact(m, ("schema", "data_origin", "study_id", "started_at", "finished_at", "implementation_sha256",
              "artifact_manifest_sha256", "source_hashes", "checks", "real_fit_calls", "real_evaluation_calls", "future_saved_predictions"))
    if m["schema"] != "nn_v2_phase2_1_audit_v1" or m["data_origin"] != "synthetic":
        raise ValueError("Phase 2.1 accepts synthetic verification only")
    text(m["study_id"])
    if stamp(m["finished_at"]) < stamp(m["started_at"]):
        raise ValueError("Audit timestamp order mismatch")
    digest(m["implementation_sha256"]); digest(m["artifact_manifest_sha256"])
    if not isinstance(m["source_hashes"], dict) or not m["source_hashes"]:
        raise ValueError("Audit input pins required")
    for k, v in m["source_hashes"].items():
        text(k); digest(v)
    if not isinstance(m["checks"], dict) or not m["checks"] or any(v not in ("PASS", "FAIL", "NOT_RUN") for v in m["checks"].values()):
        raise ValueError("Explicit audit checks required")
    for k in ("real_fit_calls", "real_evaluation_calls", "future_saved_predictions"):
        if type(m[k]) is not int or m[k] != 0:
            raise ValueError("Real operations forbidden in Phase 2.1")


def validate_target_selection(plan, full_schedule, *, now):
    """Check first eligible round against an independent complete schedule input."""
    validate_enrollment(plan, now=now)
    if not isinstance(full_schedule, list) or len(full_schedule) != 380:
        raise ValueError("Independent full 38-round schedule required")
    keys, official, grouped = set(), set(), {}
    fixture_fields = set(plan["fixtures"][0])
    for f in full_schedule:
        exact(f, fixture_fields)
        key = text(f["fixture_key"])
        positive_int(f["round"])
        home, away = text(f["home_team_id"]), text(f["away_team_id"])
        if (key in keys or home == away or f["namespace"] != "jleague_match_page"
                or f["status"] not in ("scheduled", "candidate", "completed")):
            raise ValueError("Invalid full-schedule fixture")
        stamp(f["kickoff"])
        if f["official_id"] is None:
            if f["mapping_status"] != "pending":
                raise ValueError("Full-schedule unresolved identity mismatch")
        else:
            mid = f["official_id"]
            if (not isinstance(mid, str) or not re.fullmatch(r"[0-9]+", mid)
                    or mid in official or f["mapping_status"] != "verified"):
                raise ValueError("Full-schedule official identity collision")
            official.add(mid)
        keys.add(key); grouped.setdefault(f["round"], []).append(f)
    if set(grouped) != set(range(1, 39)) or any(len(v) != 10 for v in grouped.values()):
        raise ValueError("Full official round membership mismatch")
    club_sets = []
    for fixtures in grouped.values():
        clubs = [f[k] for f in fixtures for k in ("home_team_id", "away_team_id")]
        if len(set(clubs)) != 20:
            raise ValueError("Full-schedule club collision")
        club_sets.append(frozenset(clubs))
    if len(set(club_sets)) != 1:
        raise ValueError("Full-schedule competition membership mismatch")
    eligible = sorted(r for r, items in grouped.items() if all(
        f["status"] == "scheduled" and stamp(f["kickoff"]) > stamp(plan["t0"]) for f in items))
    if not eligible or plan["r_start"] != eligible[0]:
        raise ValueError("R_start must be first wholly unstarted official round")
    expected = {f["fixture_key"]: f for r in range(plan["r_start"], plan["r_start"]+20)
                for f in grouped[r]}
    if {f["fixture_key"]: f for f in plan["fixtures"]} != expected:
        raise ValueError("Enrolled fixtures differ from independent source schedule")
