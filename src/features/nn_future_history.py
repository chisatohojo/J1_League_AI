"""Research-only, in-memory Elo/Form adapter. No model, scaler or storage APIs.

The caller supplies a complete audited fixture universe and separately pinned
timing admissions. Final-score evidence alone is not a timing admission.
"""
from collections import defaultdict, deque
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
import hashlib
import json
import math
import re

from src.features.elo import EloRatings
from src.features.nn_research_timing import events as legacy_timing


FEATURES = (
    "elo_diff", "home_last5_matches_available", "away_last5_matches_available",
    "home_last5_points", "away_last5_points", "home_last5_goals_for",
    "away_last5_goals_for", "home_last5_goals_against", "away_last5_goals_against",
)
BINDING_SHA = "6e1309539a5fc5ab58a82d36035e5d96a6da462701d5253e3b83dd332b8181f0"
COMPETITIONS = {"ordinary_j1_2015_2025", "j1_hyakunen_2026", "j1_2026_2027"}


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def clock(value):
    value = datetime.fromisoformat(value)
    require(value.utcoffset() is not None, "naive_clock")
    return value


def midnight(value):
    parsed = clock(value)
    require(parsed.utcoffset() == timedelta(hours=9)
            and parsed.hour == parsed.minute == parsed.second == parsed.microsecond == 0,
            "not_jst_midnight")
    return parsed


@dataclass(frozen=True)
class ResultEvent:
    identity: str
    match_id: str
    competition: str
    home_team_id: str
    away_team_id: str
    original_kickoff: str
    recorded_source_date: str
    result_effective_at: str
    home_score_90: int
    away_score_90: int
    # A policy boundary is never substituted for an acquisition timestamp.
    source_fetched_at_utc: str | None
    raw_sha256: str | None
    metadata_sha256: str | None
    source_url: str | None
    source_revision: str | None
    timing_class: str
    binding_sha256: str | None = None


@dataclass(frozen=True)
class Fixture:
    """Complete audited universe, including pending/scheduled rows."""
    identity: str
    home_team_id: str
    away_team_id: str
    original_kickoff: str
    status: str


@dataclass(frozen=True)
class Query:
    """Feature request only; deliberately cannot carry scores or a label."""
    identity: str
    home_team_id: str
    away_team_id: str
    kickoff: str
    history_cutoff: str
    knowledge_at: str


@dataclass(frozen=True)
class BindingInputs:
    payload: bytes
    revisions: tuple
    snapshots: dict
    pins: dict


def event_sha(event):
    return hashlib.sha256(json.dumps(asdict(event), sort_keys=True,
                                    separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def legacy_events(matches):
    """Keep v1.1's frozen original-start / delayed-result policy verbatim.

    Historical reconstruction is not an acquisition-as-of claim. Callers must
    first check the existing source pins and the sealed cache timing review.
    """
    state = legacy_timing(matches)
    require(state.season.between(2015, 2025).all(), "legacy_year_scope")
    result = []
    for r in state.itertuples(index=False):
        result.append(ResultEvent(
            r.fixture_identity, r.match_id, "ordinary_j1_2015_2025",
            r.home_team_id, r.away_team_id, r.feature_timestamp,
            r.recorded_source_date, r.result_effective_timestamp,
            int(r.home_score), int(r.away_score), None, None, None, None, None,
            "legacy_v1_1"))
    return tuple(result)


def _validate_event(e, admissions, binding):
    require(e.competition in COMPETITIONS, "competition_out_of_scope")
    require(isinstance(e.identity, str) and e.identity.strip() == e.identity
            and bool(e.identity) and isinstance(e.match_id, str) and bool(e.match_id), "event_identity")
    require(all(type(x) is int and x >= 0 for x in (e.home_score_90, e.away_score_90)),
            "regulation_scores_required")
    original = clock(e.original_kickoff)
    require(original.utcoffset() == timedelta(hours=9), "kickoff_not_jst")
    effective = midnight(e.result_effective_at)
    day = datetime.strptime(e.recorded_source_date, "%Y-%m-%d").date()
    require(effective.date() == day + timedelta(days=1) and effective > original,
            "result_boundary_not_after_completion_day")
    if e.competition == "ordinary_j1_2015_2025":
        require(2015 <= day.year <= 2025 and e.timing_class == "legacy_v1_1"
                and e.identity == "jleague_data_site_sfms02:" + e.match_id, "legacy_scope")
        # Identity 30700 can only enter with its fixed, final Draw chronology.
        if e.match_id == "30700":
            require((e.original_kickoff, e.recorded_source_date, e.result_effective_at,
                     e.home_team_id, e.away_team_id, e.home_score_90, e.away_score_90) == (
                         "2024-08-24T19:03:00+09:00", "2024-11-22", "2024-11-23T00:00:00+09:00",
                         "team_0030", "team_0010", 1, 1), "30700_identity")
        else:
            require(original.date() == day, "unknown_legacy_resumption")
        return
    require(day.year in (2026, 2027) and original.year in (2026, 2027), "future_year_scope")
    require(e.timing_class in {"ordinary_reviewed", "resumption_reviewed"}, "unknown_timing_exception")
    if e.timing_class == "ordinary_reviewed":
        require(original.date() == day, "unreviewed_cross_date")
    require(admissions.get(e.identity) == event_sha(e), "missing_or_changed_timing_admission")
    require(all(isinstance(s, str) and re.fullmatch(r"[a-f0-9]{64}", s)
                for s in (e.raw_sha256, e.metadata_sha256)), "missing_witness_sha")
    require(bool(e.source_url) and bool(e.source_revision) and bool(e.source_fetched_at_utc),
            "missing_source_witness")
    fetched = clock(e.source_fetched_at_utc)
    require(fetched.utcoffset() == timedelta(0) and fetched > original
            and fetched.astimezone(original.tzinfo).date() >= day, "witness_clock")
    if e.competition == "j1_hyakunen_2026":
        require(day.year == 2026 and e.identity == "jleague_data_site_sfms02:" + e.match_id,
                "hyakunen_identity")
    if e.competition == "j1_2026_2027" and e.match_id in {"101101", "101102", "101103", "101104"}:
        require(e.binding_sha256 == BINDING_SHA and binding is not None, "sealed_binding_required")
        rows = [b for b in binding["bindings"] if b["match_page_id"] == e.match_id]
        require(len(rows) == 1, "binding_fixture_missing")
        b = rows[0]; r = b["identity_and_regulation_result"]
        require((e.identity, e.recorded_source_date, e.home_score_90, e.away_score_90,
                 e.raw_sha256, e.metadata_sha256, e.source_fetched_at_utc, e.source_url) == (
                     b["fixture_key"], r["match_date"], r["home_score"], r["away_score"],
                     b["actual_source"]["sha256"], b["actual_source"]["metadata_sha256"],
                     b["known_available_at_utc"], b["actual_source"]["source_url"]), "binding_event_mismatch")
    else:
        require(e.binding_sha256 is None, "binding_expansion_forbidden")


def replay(events, queries, *, team_ids, universe, covered_through, timing_admissions,
           binding_inputs=None):
    """Return raw nine-feature records and an audit trace; never predict or fit.

    All results eligible by a cutoff must be known at that query's independent
    knowledge clock. An unknown result stops the replay; it is not omitted.
    Even morning acquisitions may support a midnight policy cutoff, provided
    they precede knowledge_at and kickoff and retain their true timestamps.
    """
    events, queries, universe = tuple(events), tuple(queries), tuple(universe)
    roster = tuple(team_ids)
    require(all(isinstance(t, str) and re.fullmatch(r"team_[0-9]{4,}", t)
                and int(t[5:]) > 0 for t in roster), "TeamMaster_ID_format")
    elo = EloRatings(roster, k_factor=30.0, home_advantage=175.0)
    known = set(roster)
    binding = None
    if binding_inputs is not None:
        from src.modeling.nn_v2_completion_binding import validate_sealed_binding
        binding = validate_sealed_binding(binding_inputs.payload, BINDING_SHA,
                                         binding_inputs.revisions, binding_inputs.snapshots, binding_inputs.pins)
    require(len({r.identity for r in universe}) == len(universe), "duplicate_universe_identity")
    fixtures = {r.identity: r for r in universe}
    require(len({e.identity for e in events}) == len(events), "duplicate_result_identity")
    require({e.identity for e in events} == {r.identity for r in universe if r.status == "completed"},
            "missing_or_extra_completed_history")
    appearances = set()
    for r in universe:
        require(r.status in {"completed", "scheduled", "candidate", "suspended"}, "unknown_status")
        require(r.home_team_id in known and r.away_team_id in known
                and r.home_team_id != r.away_team_id, "TeamMaster_ID_mismatch")
        for club in (r.home_team_id, r.away_team_id):
            require(clock(r.original_kickoff).utcoffset() == timedelta(hours=9), "kickoff_not_jst")
            key = (clock(r.original_kickoff).date(), club)
            require(key not in appearances, "same_day_club_collision")
            appearances.add(key)
    for e in events:
        r = fixtures[e.identity]
        require((r.home_team_id, r.away_team_id, r.original_kickoff) == (
            e.home_team_id, e.away_team_id, e.original_kickoff), "fixture_event_identity_mismatch")
        _validate_event(e, timing_admissions, binding)
    coverage = midnight(covered_through)
    require(len({q.identity for q in queries}) == len(queries), "duplicate_query_identity")
    for q in queries:
        cutoff, kickoff, knowledge = midnight(q.history_cutoff), clock(q.kickoff), clock(q.knowledge_at)
        require(kickoff.utcoffset() == timedelta(hours=9), "kickoff_not_jst")
        require(cutoff.date() == kickoff.date() and cutoff <= knowledge < kickoff, "query_clock")
        require(coverage >= cutoff, "incomplete_history_coverage")
        require(q.home_team_id in known and q.away_team_id in known
                and q.home_team_id != q.away_team_id, "TeamMaster_ID_mismatch")
        if q.identity in fixtures:
            r = fixtures[q.identity]
            require((q.home_team_id, q.away_team_id, q.kickoff) == (
                r.home_team_id, r.away_team_id, r.original_kickoff), "query_fixture_mismatch")
        for r in universe:
            if clock(r.original_kickoff) < cutoff and r.status != "completed":
                raise ValueError("unresolved_prior_fixture:" + r.identity)
    ordered = sorted(events, key=lambda e: (clock(e.result_effective_at), e.recorded_source_date, e.match_id))
    forms = defaultdict(lambda: deque(maxlen=5))
    applied, trace, output = [], [], []
    for q in sorted(queries, key=lambda q: (clock(q.history_cutoff), q.identity)):
        cutoff, knowledge = clock(q.history_cutoff), clock(q.knowledge_at)
        while len(applied) < len(ordered) and clock(ordered[len(applied)].result_effective_at) <= cutoff:
            e = ordered[len(applied)]
            label = 2 if e.home_score_90 > e.away_score_90 else 0 if e.home_score_90 < e.away_score_90 else 1
            elo.update(e.home_team_id, e.away_team_id, label)
            for club, gf, ga, win in ((e.home_team_id, e.home_score_90, e.away_score_90, 2),
                                      (e.away_team_id, e.away_score_90, e.home_score_90, 0)):
                forms[club].append((e.identity, 3 * int(label == win) + int(label == 1), gf, ga))
            applied.append(e)
            trace.append({"event": "result_applied", "identity": e.identity,
                          "result_effective_at": e.result_effective_at,
                          "source_fetched_at_utc": e.source_fetched_at_utc})
        require(all(e.identity != q.identity for e in applied), "own_result_leakage")
        for e in applied:
            require(e.source_fetched_at_utc is None or clock(e.source_fetched_at_utc) <= knowledge,
                    "result_not_yet_acquired:" + e.identity)
        snapshot = elo.pre_match(q.home_team_id, q.away_team_id)
        values = {"elo_diff": snapshot.home_rating - snapshot.away_rating}
        for side, club in (("home", q.home_team_id), ("away", q.away_team_id)):
            games = forms[club]
            values[f"{side}_last5_matches_available"] = len(games)
            for pos, name in enumerate(("points", "goals_for", "goals_against"), 1):
                values[f"{side}_last5_{name}"] = sum(g[pos] for g in games)
        require(all(math.isfinite(v) for v in values.values()), "nonfinite_features")
        for side in ("home", "away"):
            available = values[f"{side}_last5_matches_available"]
            require(0 <= available <= 5 and 0 <= values[f"{side}_last5_points"] <= 3 * available,
                    "form_range")
        output.append({"identity": q.identity, **{k: values[k] for k in FEATURES}})
        trace.append({"event": "features_frozen", "identity": q.identity,
                      "history_cutoff": q.history_cutoff, "knowledge_at": q.knowledge_at,
                      "history_count": len(applied),
                      "history_ids_sha256": hashlib.sha256("\n".join(e.identity for e in applied).encode()).hexdigest(),
                      "home_form_ids": [g[0] for g in forms[q.home_team_id]],
                      "away_form_ids": [g[0] for g in forms[q.away_team_id]]})
    return output, trace
