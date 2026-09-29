"""Materialize the frozen J1-J2 domestic-Cup regulation result dataset.

Candidate membership is reconstructed and frozen before any source retrieval.
This module never updates Elo, fits a model, predicts, or computes metrics.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time
from urllib.parse import urlparse
from urllib.request import Request, urlopen

import pandas as pd

from src.collect.cup_regulation_result_prototype import (
    CONFIRMED,
    UNRESOLVED,
    CupRegulationError,
    parse_jfa_match_page,
    parse_jfa_schedule_result,
    parse_jleague_sfms02,
)
from src.collect.teams import load_team_master
from src.modeling.logistic_j1_j2_cup_bridge_rolling_validation import (
    _bridge_candidates,
    _safe_cup_ids,
    _safe_emperor_ids,
)
from src.modeling.logistic_j1_j2_initial_prior_rolling_validation import (
    _load_j1,
    _load_j2,
)


DEFAULT_MANIFEST_PATH = Path(
    "data/processed/cup_regulation_results/2015_2024_j1_j2_bridge_candidates.csv"
)
DEFAULT_OUTPUT_PATH = Path(
    "data/processed/cup_regulation_results/2015_2024_j1_j2_bridge_regulation.csv"
)
DEFAULT_RAW_DIR = Path("data/raw/cup_regulation_results")
LEGACY_EMPEROR_RAW_DIR = Path("data/raw/emperors_cup")
FROZEN_CANDIDATE_SHA256 = "f44aa8785c80b48dc03acc4c206cbd59c4acc048d22d59579c865fbe990b5dc3"

MANIFEST_COLUMNS = (
    "candidate_key",
    "competition",
    "season",
    "source_match_id",
    "match_date",
    "home_team",
    "away_team",
    "home_team_id",
    "away_team_id",
    "source_url",
)

OUTPUT_COLUMNS = (
    "candidate_key",
    "competition",
    "season",
    "source_match_id",
    "match_date",
    "home_team_id",
    "away_team_id",
    "regulation_home_score",
    "regulation_away_score",
    "regulation_result",
    "extra_time_played",
    "penalty_shootout_played",
    "final_home_score",
    "final_away_score",
    "source_url",
    "source_type",
    "raw_sha256",
    "resolution_status",
    "resolution_reason",
)

EXPECTED_COUNTS = {
    ("emperors_cup", 2015): 6,
    ("emperors_cup", 2016): 5,
    ("emperors_cup", 2017): 8,
    ("emperors_cup", 2018): 12,
    ("emperors_cup", 2019): 7,
    ("emperors_cup", 2020): 1,
    ("emperors_cup", 2021): 6,
    ("emperors_cup", 2022): 14,
    ("emperors_cup", 2023): 13,
    ("emperors_cup", 2024): 5,
    ("jleague_cup", 2018): 16,
    ("jleague_cup", 2019): 14,
    ("jleague_cup", 2020): 1,
    ("jleague_cup", 2022): 12,
    ("jleague_cup", 2023): 12,
    ("jleague_cup", 2024): 13,
}


class CupDatasetError(ValueError):
    """The frozen membership, raw provenance, or output contract failed."""


def _load_candidate_inputs(
    *,
    processed_dir="data/processed/jleague",
    j2_path="data/processed/jleague_j2/2015_2024_j2_matches.csv",
    cup_path="data/processed/jleague_cup/2015_2024_jleague_cup_matches.csv",
    emperor_path="data/processed/emperors_cup/2015_2024_emperors_cup_matches.csv",
):
    master = load_team_master()
    j1 = _load_j1(processed_dir, master)
    j2 = _load_j2(j2_path)
    cup = pd.read_csv(cup_path, dtype=str)
    emperor = pd.read_csv(emperor_path, dtype=str)
    for frame in (cup, emperor):
        frame["season"] = frame["season"].astype(int)
        frame["match_date"] = pd.to_datetime(frame["match_date"])
    return master, j1, j2, cup, emperor


def build_frozen_candidates(**paths):
    """Reproduce the existing 145-candidate identity set without source results."""
    master, j1, j2, cup, emperor = _load_candidate_inputs(**paths)
    j1_membership = {
        year: set(j1.loc[j1.season.eq(year), "home_team_id"])
        | set(j1.loc[j1.season.eq(year), "away_team_id"])
        for year in range(2015, 2025)
    }
    j2_membership = {
        year: set(j2.loc[j2.season.eq(year), "home_team_id"])
        | set(j2.loc[j2.season.eq(year), "away_team_id"])
        for year in range(2015, 2025)
    }
    resolved = {
        "jleague_cup": _safe_cup_ids(cup, master),
        "emperors_cup": _safe_emperor_ids(emperor, master),
    }
    legacy = _bridge_candidates(
        resolved["jleague_cup"],
        resolved["emperors_cup"],
        j1_membership,
        j2_membership,
    )
    rows = []
    for competition, frame in resolved.items():
        for row in frame.itertuples(index=False):
            home_id = row.home_resolved_id
            away_id = row.away_resolved_id
            if pd.isna(home_id) or pd.isna(away_id):
                continue
            year = int(row.season)
            is_bridge = (
                (home_id in j1_membership[year] and away_id in j2_membership[year])
                or (home_id in j2_membership[year] and away_id in j1_membership[year])
            )
            if not is_bridge:
                continue
            source_match_id = str(row.source_match_id)
            rows.append(
                {
                    "candidate_key": f"{competition}:{source_match_id}",
                    "competition": competition,
                    "season": year,
                    "source_match_id": source_match_id,
                    "match_date": pd.Timestamp(row.match_date).strftime("%Y-%m-%d"),
                    "home_team": str(row.home_team),
                    "away_team": str(row.away_team),
                    "home_team_id": str(home_id),
                    "away_team_id": str(away_id),
                    "source_url": str(row.source_url),
                }
            )
    candidates = pd.DataFrame(rows, columns=MANIFEST_COLUMNS).sort_values(
        ["competition", "season", "match_date", "source_match_id"],
        kind="stable",
    ).reset_index(drop=True)
    validate_frozen_candidates(candidates)
    legacy_keys = set(legacy["competition"] + ":" + legacy["match_id"].astype(str))
    if legacy_keys != set(candidates["candidate_key"]):
        raise CupDatasetError("candidate set differs from existing bridge logic")
    return candidates


def validate_frozen_candidates(candidates):
    if tuple(candidates.columns) != MANIFEST_COLUMNS:
        raise CupDatasetError("candidate manifest schema mismatch")
    if len(candidates) != 145:
        raise CupDatasetError(f"candidate count mismatch: {len(candidates)}")
    if candidates["candidate_key"].duplicated().any():
        raise CupDatasetError("duplicate candidate_key")
    actual = candidates.groupby(["competition", "season"]).size().to_dict()
    if actual != EXPECTED_COUNTS:
        raise CupDatasetError(f"candidate season distribution mismatch: {actual}")
    counts = candidates.groupby("competition").size().to_dict()
    if counts != {"emperors_cup": 77, "jleague_cup": 68}:
        raise CupDatasetError(f"candidate competition counts mismatch: {counts}")
    identity = candidates[["home_team_id", "away_team_id"]]
    if identity.isna().any().any() or identity.eq("").any().any():
        raise CupDatasetError("candidate has unresolved stable team identity")
    if candidates["home_team_id"].eq(candidates["away_team_id"]).any():
        raise CupDatasetError("candidate has identical home/away identity")
    appearances = pd.concat(
        [
            candidates[["match_date", "home_team_id"]].rename(
                columns={"home_team_id": "team_id"}
            ),
            candidates[["match_date", "away_team_id"]].rename(
                columns={"away_team_id": "team_id"}
            ),
        ],
        ignore_index=True,
    )
    if appearances.duplicated(["match_date", "team_id"]).any():
        raise CupDatasetError("same team has multiple frozen candidates on one date")


def canonical_csv_bytes(frame, columns):
    return frame.loc[:, list(columns)].to_csv(index=False, lineterminator="\n").encode("utf-8")


def sha256_bytes(raw):
    return hashlib.sha256(raw).hexdigest()


def freeze_candidates(path=DEFAULT_MANIFEST_PATH, **paths):
    candidates = build_frozen_candidates(**paths)
    raw = canonical_csv_bytes(candidates, MANIFEST_COLUMNS)
    digest = sha256_bytes(raw)
    if digest != FROZEN_CANDIDATE_SHA256:
        raise CupDatasetError(f"candidate SHA mismatch: {digest}")
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists() and output.read_bytes() != raw:
        raise CupDatasetError("saved candidate manifest differs from reconstruction")
    if not output.exists():
        output.write_bytes(raw)
    if output.read_bytes() != raw:
        raise CupDatasetError("candidate manifest write was not deterministic")
    return candidates, digest


def _cache_paths(raw_dir, url):
    key = hashlib.sha256(url.encode("utf-8")).hexdigest()
    return Path(raw_dir) / f"{key}.html", Path(raw_dir) / f"{key}.metadata.json"


def read_valid_cache(raw_path, metadata_path, *, expected):
    raw_path = Path(raw_path)
    metadata_path = Path(metadata_path)
    if raw_path.exists() != metadata_path.exists():
        raise CupDatasetError(f"incomplete raw cache pair: {expected['candidate_key']}")
    if not raw_path.exists():
        return None
    raw = raw_path.read_bytes()
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    required = {
        "requested_url": expected["source_url"],
        "final_url": expected["source_url"],
        "status": 200,
        "bytes": len(raw),
        "sha256": sha256_bytes(raw),
        "competition": expected["competition"],
        "season": int(expected["season"]),
        "source_match_id": expected["source_match_id"],
    }
    if any(metadata.get(key) != value for key, value in required.items()):
        raise CupDatasetError(f"raw cache metadata mismatch: {expected['candidate_key']}")
    retrieved_at = metadata.get("retrieved_at_utc")
    if not isinstance(retrieved_at, str) or not retrieved_at.endswith("+00:00"):
        raise CupDatasetError(f"invalid retrieved_at_utc: {expected['candidate_key']}")
    return raw, metadata


def fetch_official_html(candidate, *, raw_dir=DEFAULT_RAW_DIR, interval=0.25):
    expected = {key: candidate[key] for key in MANIFEST_COLUMNS}
    parsed = urlparse(expected["source_url"])
    allowed = (
        expected["competition"] == "jleague_cup"
        and parsed.hostname == "data.j-league.or.jp"
        and parsed.path == "/SFMS02/"
    ) or (
        expected["competition"] == "emperors_cup"
        and parsed.hostname == "www.jfa.jp"
        and parsed.path.startswith(f"/match/emperorscup_{int(expected['season'])}/match_page/")
    )
    if parsed.scheme != "https" or not allowed:
        raise CupDatasetError(f"disallowed official source URL: {expected['source_url']}")
    raw_path, metadata_path = _cache_paths(raw_dir, expected["source_url"])
    cached = read_valid_cache(raw_path, metadata_path, expected=expected)
    if cached is not None:
        return cached[0], True
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    request = Request(
        expected["source_url"],
        headers={"User-Agent": "J1-League-AI bounded Cup result materialization"},
    )
    with urlopen(request, timeout=30) as response:
        raw = response.read()
        final_url = response.geturl()
        status = response.status
    if final_url != expected["source_url"] or status != 200 or not raw:
        raise CupDatasetError(f"official source request mismatch: {expected['candidate_key']}")
    metadata = {
        "requested_url": expected["source_url"],
        "final_url": final_url,
        "status": status,
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
        "bytes": len(raw),
        "sha256": sha256_bytes(raw),
        "competition": expected["competition"],
        "season": int(expected["season"]),
        "source_match_id": expected["source_match_id"],
    }
    raw_path.write_bytes(raw)
    metadata_path.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    read_valid_cache(raw_path, metadata_path, expected=expected)
    time.sleep(interval)
    return raw, False


def _schedule_url(season):
    return f"https://www.jfa.jp/match/emperorscup_{int(season)}/match/schedule.json"


def read_legacy_jfa_schedule(season, raw_dir=LEGACY_EMPEROR_RAW_DIR):
    url = _schedule_url(season)
    key = hashlib.sha256(url.encode("utf-8")).hexdigest()
    raw_path = Path(raw_dir) / f"{key}.json"
    metadata_path = Path(raw_dir) / f"{key}.metadata.json"
    if not raw_path.exists() or not metadata_path.exists():
        raise CupDatasetError(f"missing JFA schedule cache: {season}")
    raw = raw_path.read_bytes()
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    required = {
        "requested_url": url,
        "final_url": url,
        "status": 200,
        "bytes": len(raw),
        "sha256": sha256_bytes(raw),
    }
    if any(metadata.get(key) != value for key, value in required.items()):
        raise CupDatasetError(f"JFA schedule cache metadata mismatch: {season}")
    retrieved_at = metadata.get("fetched_at_utc") or metadata.get("retrieved_at_utc")
    if not isinstance(retrieved_at, str) or not retrieved_at.endswith("+00:00"):
        raise CupDatasetError(f"invalid JFA schedule retrieval timestamp: {season}")
    return raw, metadata


def _parse_schedule_candidate(candidate, raw):
    return parse_jfa_schedule_result(
        raw,
        season=int(candidate["season"]),
        source_match_id=candidate["source_match_id"],
        match_date=candidate["match_date"],
        home_team_id=candidate["home_team_id"],
        away_team_id=candidate["away_team_id"],
        expected_home_team=candidate["home_team"],
        expected_away_team=candidate["away_team"],
        source_url=_schedule_url(candidate["season"]),
    )


def required_official_lookups(candidates):
    league = candidates[candidates["competition"].eq("jleague_cup")]
    emperor_detail = []
    schedules = {}
    for candidate in candidates[candidates["competition"].eq("emperors_cup")].to_dict("records"):
        season = int(candidate["season"])
        if season not in schedules:
            schedules[season] = read_legacy_jfa_schedule(season)[0]
        parsed = _parse_schedule_candidate(candidate, schedules[season])
        if parsed["resolution_status"] == UNRESOLVED:
            emperor_detail.append(candidate)
    required = pd.concat(
        [league, pd.DataFrame(emperor_detail, columns=MANIFEST_COLUMNS)],
        ignore_index=True,
    )
    required = required.loc[:, list(MANIFEST_COLUMNS)].sort_values(
        ["competition", "season", "match_date", "source_match_id"], kind="stable"
    ).reset_index(drop=True)
    if len(required) != 87:
        raise CupDatasetError(f"official lookup set mismatch: {len(required)}")
    if required.groupby("competition").size().to_dict() != {
        "emperors_cup": 19,
        "jleague_cup": 68,
    }:
        raise CupDatasetError("official lookup competition distribution mismatch")
    return required


def acquire_required_sources(candidates, *, raw_dir=DEFAULT_RAW_DIR, interval=0.25):
    required = required_official_lookups(candidates)
    hits = downloads = 0
    for candidate in required.to_dict("records"):
        _, hit = fetch_official_html(candidate, raw_dir=raw_dir, interval=interval)
        hits += int(hit)
        downloads += int(not hit)
    return {"required": len(required), "cache_hits": hits, "downloads": downloads}


def _team_identity_evidence(master, team_id):
    aliases = tuple(alias.source_name for alias in master.aliases if alias.team_id == team_id)
    club_ids = tuple(
        sorted({alias.source_club_id for alias in master.aliases
                if alias.team_id == team_id and alias.source_club_id
                and "=" not in alias.source_club_id})
    )
    if not aliases:
        raise CupDatasetError(f"missing TeamMaster identity evidence: {team_id}")
    return aliases, club_ids


def _read_detail_cache(candidate, raw_dir=DEFAULT_RAW_DIR):
    raw_path, metadata_path = _cache_paths(raw_dir, candidate["source_url"])
    cached = read_valid_cache(raw_path, metadata_path, expected=candidate)
    if cached is None:
        raise CupDatasetError(f"missing required detail cache: {candidate['candidate_key']}")
    return cached[0]


def _normalize_positive_evidence(result):
    normalized = dict(result)
    for field in ("extra_time_played", "penalty_shootout_played"):
        if normalized.get(field) is not True:
            normalized[field] = None
    return normalized


def _result_row(candidate, result):
    row = {"candidate_key": candidate["candidate_key"]}
    for field in OUTPUT_COLUMNS[1:]:
        row[field] = result.get(field)
    return row


def build_dataset_from_cache(candidates, *, raw_dir=DEFAULT_RAW_DIR):
    """Build all 145 rows offline from validated raw caches."""
    validate_frozen_candidates(candidates)
    manifest_raw = canonical_csv_bytes(candidates, MANIFEST_COLUMNS)
    if sha256_bytes(manifest_raw) != FROZEN_CANDIDATE_SHA256:
        raise CupDatasetError("candidate SHA changed before dataset build")
    master = load_team_master()
    schedules = {}
    rows = []
    for candidate in candidates.to_dict("records"):
        if candidate["competition"] == "jleague_cup":
            raw = _read_detail_cache(candidate, raw_dir)
            home_aliases, home_club_ids = _team_identity_evidence(
                master, candidate["home_team_id"]
            )
            away_aliases, away_club_ids = _team_identity_evidence(
                master, candidate["away_team_id"]
            )
            result = parse_jleague_sfms02(
                raw,
                season=int(candidate["season"]),
                source_match_id=candidate["source_match_id"],
                match_date=candidate["match_date"],
                home_team_id=candidate["home_team_id"],
                away_team_id=candidate["away_team_id"],
                expected_home_team=candidate["home_team"],
                expected_away_team=candidate["away_team"],
                source_url=candidate["source_url"],
                expected_home_aliases=home_aliases,
                expected_away_aliases=away_aliases,
                expected_home_club_ids=home_club_ids,
                expected_away_club_ids=away_club_ids,
            )
        else:
            season = int(candidate["season"])
            if season not in schedules:
                schedules[season] = read_legacy_jfa_schedule(season)[0]
            result = _parse_schedule_candidate(candidate, schedules[season])
            if result["resolution_status"] == UNRESOLVED:
                raw = _read_detail_cache(candidate, raw_dir)
                result = parse_jfa_match_page(
                    raw,
                    season=season,
                    source_match_id=candidate["source_match_id"],
                    match_date=candidate["match_date"],
                    home_team_id=candidate["home_team_id"],
                    away_team_id=candidate["away_team_id"],
                    expected_home_team=candidate["home_team"],
                    expected_away_team=candidate["away_team"],
                    source_url=candidate["source_url"],
                )
        rows.append(_result_row(candidate, _normalize_positive_evidence(result)))
    dataset = pd.DataFrame(rows, columns=OUTPUT_COLUMNS)
    validate_dataset(dataset, candidates)
    return dataset


def _null(value):
    return value is None or pd.isna(value)


def validate_dataset(dataset, candidates):
    if tuple(dataset.columns) != OUTPUT_COLUMNS:
        raise CupDatasetError("result dataset schema mismatch")
    if len(dataset) != 145:
        raise CupDatasetError(f"result dataset row count mismatch: {len(dataset)}")
    if dataset["candidate_key"].duplicated().any():
        raise CupDatasetError("duplicate result candidate_key")
    identity_columns = (
        "candidate_key", "competition", "season", "source_match_id",
        "match_date", "home_team_id", "away_team_id",
    )
    expected = candidates.loc[:, list(identity_columns)].reset_index(drop=True).astype(str)
    actual = dataset.loc[:, list(identity_columns)].reset_index(drop=True).astype(str)
    if not actual.equals(expected):
        raise CupDatasetError("result identity differs from frozen candidates")
    for row in dataset.to_dict("records"):
        status = row["resolution_status"]
        score_fields = (
            "regulation_home_score", "regulation_away_score", "regulation_result"
        )
        if status == CONFIRMED:
            if any(_null(row[field]) for field in score_fields):
                raise CupDatasetError(f"confirmed score is null: {row['candidate_key']}")
            home = int(row["regulation_home_score"])
            away = int(row["regulation_away_score"])
            result = int(row["regulation_result"])
            if home < 0 or away < 0 or result != (2 if home > away else 0 if home < away else 1):
                raise CupDatasetError(f"invalid confirmed score/result: {row['candidate_key']}")
            if (row["extra_time_played"] is True or row["penalty_shootout_played"] is True) \
                    and home == away and result != 1:
                raise CupDatasetError(f"knockout draw result mismatch: {row['candidate_key']}")
        elif status == UNRESOLVED:
            if any(not _null(row[field]) for field in score_fields):
                raise CupDatasetError(f"unresolved score was populated: {row['candidate_key']}")
        else:
            raise CupDatasetError(f"unknown resolution status: {status}")
        if not isinstance(row["raw_sha256"], str) or len(row["raw_sha256"]) != 64:
            raise CupDatasetError(f"missing raw provenance: {row['candidate_key']}")


def canonical_dataset_bytes(dataset):
    return dataset.loc[:, list(OUTPUT_COLUMNS)].to_csv(
        index=False, lineterminator="\n", na_rep=""
    ).encode("utf-8")


def materialize_dataset(
    *, manifest_path=DEFAULT_MANIFEST_PATH, output_path=DEFAULT_OUTPUT_PATH,
    raw_dir=DEFAULT_RAW_DIR,
):
    manifest_path = Path(manifest_path)
    candidates = build_frozen_candidates()
    canonical_manifest = canonical_csv_bytes(candidates, MANIFEST_COLUMNS)
    if not manifest_path.exists() or manifest_path.read_bytes() != canonical_manifest:
        raise CupDatasetError("saved candidate manifest differs from reconstruction")
    if sha256_bytes(canonical_manifest) != FROZEN_CANDIDATE_SHA256:
        raise CupDatasetError("saved candidate manifest SHA mismatch")
    dataset = build_dataset_from_cache(candidates, raw_dir=raw_dir)
    raw = canonical_dataset_bytes(dataset)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(raw)
    if output_path.read_bytes() != raw:
        raise CupDatasetError("dataset write was not deterministic")
    return dataset, sha256_bytes(raw)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--freeze-only", action="store_true")
    parser.add_argument("--fetch", action="store_true")
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--manifest-path", default=str(DEFAULT_MANIFEST_PATH))
    parser.add_argument("--output-path", default=str(DEFAULT_OUTPUT_PATH))
    parser.add_argument("--raw-dir", default=str(DEFAULT_RAW_DIR))
    parser.add_argument("--interval", type=float, default=0.25)
    args = parser.parse_args(argv)
    candidates, digest = freeze_candidates(args.manifest_path)
    print(f"candidates={len(candidates)} candidate_sha256={digest}")
    if args.freeze_only:
        return
    if args.fetch == args.offline:
        raise CupDatasetError("choose exactly one of --fetch or --offline")
    if args.fetch:
        acquisition = acquire_required_sources(
            candidates, raw_dir=args.raw_dir, interval=args.interval
        )
        print(" ".join(f"{key}={value}" for key, value in acquisition.items()))
    dataset, dataset_digest = materialize_dataset(
        manifest_path=args.manifest_path,
        output_path=args.output_path,
        raw_dir=args.raw_dir,
    )
    counts = dataset["resolution_status"].value_counts().to_dict()
    print(
        f"rows={len(dataset)} confirmed={counts.get(CONFIRMED, 0)} "
        f"unresolved={counts.get(UNRESOLVED, 0)} dataset_sha256={dataset_digest}"
    )


if __name__ == "__main__":
    main()
