"""Research-only feature/result events; original CSV dates are never edited."""
from collections import defaultdict, deque
import hashlib
import html
import json
from pathlib import Path
import re
import unicodedata

import numpy as np
import pandas as pd

from src.features.elo import EloRatings

POLICY = "nn_original_kickoff_events_v1_1"
JST = "Asia/Tokyo"
SPECIAL_ID = "30700"
TIMING_COLUMNS = (
    "fixture_identity", "feature_timestamp", "history_cutoff_timestamp",
    "result_effective_timestamp", "recorded_source_date", "final_label", "timing_policy",
)
SIGNALS = re.compile(r"中断|中止|再開|延期|継続試合|再試合|suspend|abandon|resum|postpon", re.I)
ROOT = Path(__file__).resolve().parents[2]
REVIEW_PATH = ROOT / "research/nn_v1/timing-v1_1/reviewed-interruptions.json"


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def timing_notes(raw):
    """Only the documented remarks block; unknown structures fail closed."""
    blocks = re.findall(rb"<!-- A11[^>]*Start -->(.*?)<!-- A11[^>]*End -->", raw, re.S)
    if not blocks and b"A11" not in raw:
        # Verified empty-remarks template: coaches end, legend only, then the
        # match-information section. Missing or arbitrary HTML is NOT ordinary.
        info = list(re.finditer(rb"<!-- A12[^>]*Start -->", raw))
        coaches = list(re.finditer(rb"<!-- A10[^>]*End -->", raw))
        if len(info) != 1 or not coaches or coaches[-1].end() >= info[0].start() or not all(s in raw for s in (b'team-name-l', b'team-name-r', b'score-board-main')):
            raise ValueError("Unknown official remarks structure")
        gap = raw[coaches[-1].end():info[0].start()]
        visible = re.sub(r"<!--.*?-->", "", gap.decode("utf-8-sig"), flags=re.S)
        visible = html.unescape(re.sub(r"<[^>]*>", "", visible))
        if re.sub(r"\s+", "", visible) != "▲：IN▽：OUT":
            raise ValueError("Unknown official empty-remarks structure")
        block_bytes = b""
    elif len(blocks) == 1:
        block_bytes = blocks[0]
    else:
        raise ValueError("Unknown official remarks structure")
    block = block_bytes.decode("utf-8-sig", errors="strict")
    paragraphs = re.findall(r"<p\b[^>]*>(.*?)</p>", block, re.S | re.I)
    notes = [html.unescape(re.sub(r"<[^>]*>", "", p)).strip() for p in paragraphs]
    signals = [n for n in notes if SIGNALS.search(n)]
    # A timing signal elsewhere must not disappear just because a page changed.
    remainder = (raw.replace(block_bytes, b"") if block_bytes else raw).decode("utf-8-sig", errors="replace")
    # Telemetry JavaScript uses sessionReplay.RESUME; it is not match evidence.
    remainder = re.sub(r"<(script|style)\b[^>]*>.*?</\1\s*>", "", remainder, flags=re.S | re.I)
    remainder = re.sub(r"<!--.*?-->", "", remainder, flags=re.S)
    if SIGNALS.search(re.sub(r"<[^>]*>", "", remainder)):
        raise ValueError("Unreviewed timing signal outside remarks")
    return signals


def classify_notes(match_id, source_date, notes, registry):
    entry = registry.get(str(match_id))
    if not notes:
        if entry:
            raise ValueError("Previously reviewed timing note disappeared")
        return "ordinary"
    if entry is None:
        raise ValueError(f"Unreviewed interruption/resumption: {match_id}")
    if (entry["source_date"] != str(source_date)[:10]
            or entry["note_sha256"] != digest("\n".join(notes).encode("utf-8"))):
        raise ValueError(f"Reviewed timing evidence changed: {match_id}")
    return entry["classification"]


def review_cache(source_root, source, registry_path=REVIEW_PATH):
    """Read/validate every ordinary-J1 cached detail; never fetch or write it."""
    registry = json.loads(Path(registry_path).read_bytes())
    directory = Path(source_root) / "data/raw/jleague_match_stats"
    entries, found = [], set()
    for row in source.itertuples(index=False):
        mid = str(row.match_id)
        if not re.fullmatch(r"[0-9]+", mid):
            raise ValueError("Invalid SFMS02 identity")
        raw = (directory / f"{mid}.html").read_bytes()
        meta_body = (directory / f"{mid}.metadata.json").read_bytes()
        meta = json.loads(meta_body)
        url = f"https://data.j-league.or.jp/SFMS02/?match_card_id={mid}"
        if (meta["requested_url"] != url or meta["final_url"] != url or meta["status"] != 200
                or str(meta["match_id"]) != mid or meta["bytes"] != len(raw)
                or meta["sha256"] != digest(raw)):
            raise ValueError(f"Cached official evidence mismatch: {mid}")
        try:
            notes = timing_notes(raw)
        except (ValueError, UnicodeError) as exc:
            raise ValueError(f"Timing evidence unreadable for {mid}: {exc}") from exc
        classification = classify_notes(mid, row.match_date, notes, registry)
        if classification != "ordinary":
            if (registry[mid]["cached_raw_sha256"] != digest(raw)
                    or registry[mid]["source_kickoff"] != str(row.kickoff_time)):
                raise ValueError(f"Reviewed cache/kickoff changed: {mid}")
            found.add(mid)
        entries.append({"match_id": mid, "raw_sha256": digest(raw),
                        "metadata_sha256": digest(meta_body), "classification": classification})
    if found != set(registry).intersection(set(source.match_id)):
        raise ValueError("Reviewed interruption coverage mismatch")
    return {"status": "PASS", "rows": len(entries), "reviewed_timing_ids": sorted(found),
            "unknown_timing_cases": [], "files": entries}


def events(matches):
    required = {"match_id", "match_date", "home_team_id", "away_team_id", "home_score", "away_score", "result"}
    if matches.columns.has_duplicates or required - set(matches.columns):
        raise ValueError("Missing/duplicate event columns")
    if matches.empty or matches.match_id.isna().any() or not matches.match_id.map(lambda x: isinstance(x, str) and bool(x.strip())).all() or not matches.match_id.is_unique:
        raise ValueError("Event IDs must be unique and nonblank strings")
    source = matches.copy(deep=True).reset_index(drop=True)
    dates = pd.to_datetime(source.match_date, errors="raise")
    if dates.isna().any() or dates.dt.tz is not None or not dates.eq(dates.dt.normalize()).all():
        raise ValueError("Source dates must be valid naive calendar dates")
    source["recorded_source_date"] = dates.dt.strftime("%Y-%m-%d")
    if source.home_team_id.eq(source.away_team_id).any():
        raise ValueError("Two distinct clubs are required")
    for c in ("home_team_id", "away_team_id"):
        if source[c].isna().any() or not source[c].map(lambda x: isinstance(x, str) and bool(x.strip())).all():
            raise ValueError("Nonblank club IDs required")
    values = source[["home_score", "away_score", "result"]].to_numpy(dtype=float)
    if not np.isfinite(values).all() or (values < 0).any() or not np.equal(values, np.floor(values)).all():
        raise ValueError("Scores/labels must be nonnegative integers")
    labels = np.where(values[:, 0] > values[:, 1], 2, np.where(values[:, 0] < values[:, 1], 0, 1))
    if not np.array_equal(labels, values[:, 2]):
        raise ValueError("Final label must agree with final scores")
    # Annotations supplied by another caller must not silently introduce a new
    # multi-day fixture. Frozen source CSVs themselves have no such columns.
    for c in ("timing_note", "source_notes", "resumed_at", "original_kickoff"):
        if c in source:
            unknown = source[c].fillna("").astype(str).str.strip().ne("") & source.match_id.ne(SPECIAL_ID)
            if unknown.any():
                raise ValueError("Unreviewed temporal annotation")
    kickoff = source.get("kickoff_time", pd.Series("00:00", index=source.index))
    if not kickoff.astype(str).str.fullmatch(r"(?:[01][0-9]|2[0-3]):[0-5][0-9]").all():
        raise ValueError("Unknown kickoff format")
    feature = pd.to_datetime(source.recorded_source_date + " " + kickoff.astype(str)).dt.tz_localize(JST)
    history = dates.dt.tz_localize(JST)
    effective = history + pd.Timedelta(days=1)
    special = source.match_id.eq(SPECIAL_ID)
    if special.any():
        row = source.loc[special].iloc[0]
        identity = (row.recorded_source_date, row.home_team_id, row.away_team_id, int(row.home_score), int(row.away_score), int(row.result))
        if identity != ("2024-11-22", "team_0030", "team_0010", 1, 1, 1):
            raise ValueError("Registered resumption identity/final label mismatch")
        if "season" in source and int(row.season) != 2024 or "round" in source and int(row["round"]) != 28:
            raise ValueError("Registered resumption competition/round mismatch")
        if str(kickoff.loc[row.name]) != "19:00":
            raise ValueError("Registered resumption source kickoff mismatch")
        feature.loc[special] = pd.Timestamp("2024-08-24T19:03:00+09:00")
        history.loc[special] = pd.Timestamp("2024-08-24T00:00:00+09:00")
        # Deliberately not an invented final-whistle time. Next-day midnight is
        # a conservative availability boundary after the recorded final day.
        effective.loc[special] = pd.Timestamp("2024-11-23T00:00:00+09:00")
    appearances = pd.concat([pd.DataFrame({"day": history, "club": source[f"{s}_team_id"]}) for s in ("home", "away")])
    if appearances.duplicated(["day", "club"]).any():
        raise ValueError("A club appears more than once on the same feature date")
    source["fixture_identity"] = "jleague_data_site_sfms02:" + source.match_id
    source["feature_timestamp"] = feature.map(lambda d: d.isoformat())
    source["history_cutoff_timestamp"] = history.map(lambda d: d.isoformat())
    source["result_effective_timestamp"] = effective.map(lambda d: d.isoformat())
    source["final_label"] = labels.astype(int)
    source["timing_policy"] = POLICY
    return source


def build_event_features(matches, *, trace=None):
    state = events(matches)
    ids = sorted(set(state.home_team_id) | set(state.away_team_id))
    elo = EloRatings(ids, k_factor=30.0, home_advantage=175.0)
    histories = defaultdict(lambda: deque(maxlen=5))
    features = {}
    emitted, applied = set(), set()
    reads = defaultdict(list)
    updates = defaultdict(list)
    for row in state.itertuples(index=False):
        reads[row.history_cutoff_timestamp].append(row)
        updates[row.result_effective_timestamp].append(row)
    for day in sorted(set(reads) | set(updates)):
        # Results effective at today's midnight all finished before today.
        for row in sorted(updates[day], key=lambda r: (r.recorded_source_date, r.match_id)):
            if row.match_id not in emitted or row.match_id in applied:
                raise ValueError("Result applied before feature emission or more than once")
            elo.update(row.home_team_id, row.away_team_id, int(row.final_label))
            for club, gf, ga, win in ((row.home_team_id, row.home_score, row.away_score, 2), (row.away_team_id, row.away_score, row.home_score, 0)):
                histories[club].append((3 * int(row.final_label == win) + int(row.final_label == 1), int(gf), int(ga)))
            applied.add(row.match_id)
            if trace is not None:
                trace.append({"event": "result_applied", "match_id": row.match_id, "at": day})
        for row in sorted(reads[day], key=lambda r: r.match_id):
            before = elo.pre_match(row.home_team_id, row.away_team_id)
            result = {"elo_diff": before.home_rating - before.away_rating}
            for side, club in (("home", row.home_team_id), ("away", row.away_team_id)):
                games = histories[club]
                result[f"{side}_last5_matches_available"] = len(games)
                for pos, name in enumerate(("points", "goals_for", "goals_against")):
                    result[f"{side}_last5_{name}"] = sum(g[pos] for g in games)
            features[row.match_id] = result
            emitted.add(row.match_id)
            if trace is not None:
                trace.append({"event": "features_frozen", "match_id": row.match_id, "at": day})
    if len(emitted) != len(state) or emitted != applied:
        raise ValueError("Incomplete event processing")
    for c in next(iter(features.values())):
        state[c] = [features[mid][c] for mid in state.match_id]
    return state.sort_values(["match_date", "match_id"], kind="stable").reset_index(drop=True)


def validate_timed_state(frame):
    if frame.match_id.astype(str).eq(SPECIAL_ID).any():
        if set(TIMING_COLUMNS) - set(frame.columns):
            raise ValueError("Missing original-kickoff event metadata")
        expected = events(frame)
        for c in TIMING_COLUMNS:
            if frame[c].astype(str).tolist() != expected[c].astype(str).tolist():
                raise ValueError(f"Invalid original-kickoff event field: {c}")
