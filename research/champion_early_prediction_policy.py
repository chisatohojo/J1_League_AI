"""Pure dependency-policy experiment. Never authorizes inference or admission.

No I/O, model/collector imports, execution entrypoint, production capability or
operational gate replacement. Evidence flags describe prerequisites, not proofs.
"""
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
from zoneinfo import ZoneInfo

SCOPE = "STATIC_DEPENDENCY_ANALYSIS_ONLY_NO_ADMISSION"
MODEL_COMPETITIONS = frozenset({"training_j1", "hyakunen", "j1_2026_27"})
JST = ZoneInfo("Asia/Tokyo")


@dataclass(frozen=True)
class Fixture:
    identity: str
    home: str
    away: str
    day: str
    kickoff: datetime | None
    status: str = "scheduled"
    competition: str = "j1_2026_27"
    result_acquired_at: datetime | None = None
    identity_verified: bool = True
    cancellation_verified: bool = False
    result: int | None = None
    witness_sha: str | None = None


@dataclass(frozen=True)
class Assessment:
    scope: str
    candidate: bool
    reasons: tuple[str, ...]
    required_ids: tuple[str, ...]
    required_teams: tuple[str, ...]
    unrelated_unfinished_ids: tuple[str, ...]
    excluded_non_model_ids: tuple[str, ...]
    last_required_result_date: str | None
    result_availability_lower_bound: str | None
    next_intervening_match_date: str | None
    input_digest: str
    history_admission: bool = False
    execution_authorized: bool = False


def _aware(value):
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timezone-aware timestamp required")
    return value.astimezone(timezone.utc)


def fingerprint(target, history, **context):
    """Only integrity of supplied fixed inputs; not a rating-map or model hash."""
    def convert(value):
        if isinstance(value, datetime):
            return value.isoformat()
        raise TypeError("unsupported fingerprint input")
    rows = sorted((asdict(f) for f in history), key=lambda r: r["identity"])
    raw = json.dumps(dict(target=asdict(target), history=rows, context=context),
                     default=convert, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(raw.encode()).hexdigest()


def assess(target, history, *, freeze, source_observed_at, prediction_horizon_days=2,
           coverage_verified=False, source_evidence_verified=False,
           fixed_history_verified=False, feature_contract=("elo_diff",),
           source_revision="", source_manifest_sha="", model_bundle_sha=""):
    """Backward, time-respecting Elo closure, assuming participant-local fixed-K updates.

    History is the complete relevant calendar prefix, not the completed subset.
    A separately verified sealed 2015-2025/Hyakunen prefix remains mandatory.
    Missing evidence, calendar ambiguity and unknown feature dependencies HOLD.
    """
    history = tuple(history)
    reasons = []
    required, unavailable, excluded = [], [], []
    needed = {target.home, target.away}
    latest, availability, intervening = None, None, None
    digest = fingerprint(target, history, freeze=freeze, source_observed_at=source_observed_at,
                         prediction_horizon_days=prediction_horizon_days,
                         feature_contract=feature_contract, coverage_verified=coverage_verified,
                         source_evidence_verified=source_evidence_verified,
                         fixed_history_verified=fixed_history_verified,
                         source_revision=source_revision, source_manifest_sha=source_manifest_sha,
                         model_bundle_sha=model_bundle_sha)

    def result():
        return Assessment(SCOPE, not reasons, tuple(sorted(set(reasons))),
                          tuple(sorted(required)), tuple(sorted(needed)), tuple(sorted(unavailable)),
                          tuple(sorted(excluded)), latest, availability, intervening, digest)

    if feature_contract != ("elo_diff",):
        reasons.append("UNKNOWN_FEATURE_DEPENDENCY")
    if not coverage_verified:
        reasons.append("CALENDAR_COVERAGE_NOT_VERIFIED")
    if not source_evidence_verified:
        reasons.append("SOURCE_EVIDENCE_NOT_VERIFIED")
    if not fixed_history_verified:
        reasons.append("SEALED_HISTORY_PREFIX_NOT_VERIFIED")
    def valid_sha(value):
        return isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)
    if not all(valid_sha(v) for v in (source_revision, source_manifest_sha, model_bundle_sha)):
        reasons.append("SOURCE_MODEL_BINDING_UNPROVEN")
    try:
        freeze, observed, kickoff = _aware(freeze), _aware(source_observed_at), _aware(target.kickoff)
    except ValueError:
        reasons.append("UNKNOWN_TIME")
        return result()
    if type(prediction_horizon_days) is not int or not 0 <= prediction_horizon_days <= 14:
        reasons.append("INVALID_HORIZON")
        return result()
    if observed > freeze or freeze - observed > timedelta(hours=24):
        reasons.append("SOURCE_FUTURE_OR_STALE")
    if not freeze < kickoff:
        reasons.append("TARGET_KICKOFF_ELAPSED")
    days = (kickoff.astimezone(JST).date() - freeze.astimezone(JST).date()).days
    if not 0 <= days <= prediction_horizon_days:
        reasons.append("OUTSIDE_JST_DAY_HORIZON")
    if target.status != "scheduled" or not target.identity_verified or target.competition not in MODEL_COMPETITIONS:
        reasons.append("TARGET_NOT_CONFIRMED")

    ids, appearances, eligible = set(), set(), []
    for event in (target, *history):
        if not event.identity or event.identity in ids:
            reasons.append("DUPLICATE_OR_MISSING_ID")
        ids.add(event.identity)
        if not event.home or not event.away or event.home == event.away or not event.identity_verified:
            reasons.append("IDENTITY_UNVERIFIED")
        if event.competition not in MODEL_COMPETITIONS:
            if event.competition != "cup":
                reasons.append("UNKNOWN_COMPETITION_SCOPE")
            excluded.append(event.identity)
            continue  # Known cup results are not inputs to the frozen Champion A.
        try:
            day = date.fromisoformat(event.day)
            if day.isoformat() != event.day:
                raise ValueError()
            if event.kickoff is not None and _aware(event.kickoff).astimezone(JST).date() != day:
                raise ValueError()
        except ValueError:
            reasons.append("CALENDAR_ORDER_UNKNOWN")
            continue
        if event.status == "cancelled" and event.cancellation_verified:
            continue  # Explicitly confirmed non-play; never infer this from missing scores.
        if event.status not in {"completed", "scheduled", "candidate"} or event.kickoff is None:
            reasons.append("CALENDAR_ORDER_UNKNOWN")
            continue
        if event.status == "completed":
            try:
                if not _aware(event.kickoff) <= _aware(event.result_acquired_at) <= observed:
                    raise ValueError()
                if type(event.result) is not int or event.result not in (0, 1, 2) or not valid_sha(event.witness_sha):
                    raise ValueError()
            except ValueError:
                reasons.append("SOURCE_RESULT_PROVENANCE_CONTRADICTION")
        for team in (event.home, event.away):
            key = (event.day, team)
            if key in appearances:
                reasons.append("TEAM_MULTIPLE_MATCHES_SAME_JST_DATE")
            appearances.add(key)
        if event is target:
            continue
        if {event.home, event.away} & {target.home, target.away} and freeze < _aware(event.kickoff) < kickoff:
            intervening = min(intervening or event.day, event.day)
        if event.day < target.day:
            eligible.append(event)

    # Matches on the same date have disjoint teams by the retained native gate.
    # Thus the ID order inside a day cannot change the target rating dependency.
    for event in sorted(eligible, key=lambda f: (f.day, f.identity), reverse=True):
        if not {event.home, event.away} & needed:
            if event.status != "completed":
                unavailable.append(event.identity)
            continue
        required.append(event.identity)
        needed.update((event.home, event.away))
        if event.status != "completed":
            reasons.append("REQUIRED_RESULT_NOT_CONFIRMED")
            continue
        try:
            acquired = _aware(event.result_acquired_at)
            if not _aware(event.kickoff) <= acquired <= observed:
                raise ValueError()
        except ValueError:
            reasons.append("REQUIRED_RESULT_TIME_UNPROVEN")
            continue
        latest = max(latest or event.day, event.day)
        availability = max(availability or acquired.isoformat(), acquired.isoformat())
    return result()


def fixed_inputs_unchanged(previous, current):
    """Compare the same frozen input set. A later latest revision is a separate review.

    False means HOLD/review, never delete/recompute an existing prediction.
    """
    return previous.scope == current.scope == SCOPE and previous.input_digest == current.input_digest
