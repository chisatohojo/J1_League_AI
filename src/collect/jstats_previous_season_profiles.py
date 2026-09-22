"""Materialize historical season-final J1 team J Stats profiles.

This module intentionally handles only the six frozen candidate stats.  It is
not a point-in-time collector and must not be used for same-season features.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import re
import time
from urllib.request import Request, urlopen

from src.collect.jstats_team_snapshots import _Page, SnapshotError
from src.collect.teams import TeamMaster, load_team_master

ROOT = Path(__file__).resolve().parents[2]
MATCH_ROOT = ROOT / "data/processed/jleague"
RAW_ROOT = ROOT / "data/raw/jstats_previous_season_profiles"
PROCESSED_ROOT = ROOT / "data/processed/jstats_previous_season_profiles"
BASE_URL = "https://www.jleague.jp/j1/stats/club/{season}/{stat}/search-list/"
SEASONS = tuple(range(2018, 2026))


@dataclass(frozen=True)
class ProfileStat:
    slug: str
    label: str
    value_type: str
    unit: str
    available_from: int
    derived_name: str | None = None


PROFILE_STATS = (
    ProfileStat("expected_goals", "ゴール期待値", "decimal_total", "", 2019,
                "expected_goals_per_match"),
    ProfileStat("shoot_on_target", "枠内シュート総数", "total", "回", 2018,
                "shoot_on_target_per_match"),
    ProfileStat("expected_goals_against", "被ゴール期待値", "decimal_total", "", 2019,
                "expected_goals_against_per_match"),
    ProfileStat("suffer_shoot_on_target", "被枠内シュート総数", "total", "回", 2018,
                "suffer_shoot_on_target_per_match"),
    ProfileStat("ball_rate", "平均ボール支配率", "percentage", "%", 2018),
    ProfileStat("pass_rate", "パス成功率", "percentage", "%", 2018),
)
STAT_BY_SLUG = {stat.slug: stat for stat in PROFILE_STATS}
CSV_FIELDS = (
    "profile_season", "team_id", "official_club_id", "official_club_code",
    "official_club_name", "official_club_href", "stat_name", "raw_value", "derived_value", "unit",
    "value_type", "source_url", "source_update_date", "retrieved_at",
    "retrieval_id", "raw_sha256", "games_played_basis",
)


def expected_teams(season: int, *, match_root: Path = MATCH_ROOT,
                   master: TeamMaster | None = None) -> dict[str, tuple[str, int]]:
    """Return exact official-name -> (team_id, appearance count) for one J1 season."""
    master = master or load_team_master()
    counts: dict[str, int] = {}
    ids: dict[str, str] = {}
    path = Path(match_root) / f"{season}_matches_probe.csv"
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise SnapshotError(f"Missing J1 matches for profile season {season}.")
    match_ids = [row.get("match_id") for row in rows]
    if any(not value for value in match_ids) or len(match_ids) != len(set(match_ids)):
        raise SnapshotError(f"Incomplete or duplicate J1 match IDs for {season}.")
    for row in rows:
        for field in ("home_team", "away_team"):
            name = row.get(field, "")
            if not name:
                raise SnapshotError(f"Missing team name in {season} J1 matches.")
            try:
                team_id = master.resolve_team_id(name, source="jleague_data_site",
                                                 on=date(season, 12, 31))
            except Exception as exc:
                raise SnapshotError(f"Unresolved TeamMaster name: {season} {name!r}") from exc
            if name in ids and ids[name] != team_id:
                raise SnapshotError(f"Name maps to multiple teams: {name!r}")
            ids[name] = team_id
            counts[team_id] = counts.get(team_id, 0) + 1
    if not counts or len(set(counts.values())) != 1 or len(rows) != len(counts) * (len(counts) - 1):
        raise SnapshotError(f"Unexpected J1 denominator for {season}: {counts}")
    return {name: (team_id, counts[team_id]) for name, team_id in ids.items()}


def _numeric(value: object) -> str:
    raw = str(value)
    try:
        number = Decimal(raw)
    except (InvalidOperation, ValueError) as exc:
        raise SnapshotError(f"Non-numeric historical stat value: {value!r}") from exc
    if not number.is_finite() or number < 0:
        raise SnapshotError(f"Invalid historical stat value: {value!r}")
    return raw


def _source_date(text: str) -> str | None:
    dates = set(re.findall(r"(20\d{2})/([0-9]{1,2})/([0-9]{1,2})\s*更新", text))
    if len(dates) > 1:
        raise SnapshotError("Ambiguous historical J Stats update dates.")
    if not dates:
        return None
    year, month, day = next(iter(dates))
    value = f"{int(year):04d}-{int(month):02d}-{int(day):02d}"
    date.fromisoformat(value)
    return value


def parse_profile_page(raw: bytes, *, season: int, stat: ProfileStat,
                       expected: dict[str, tuple[str, int]], master: TeamMaster) -> tuple[list[dict], str | None]:
    """Parse one official RSC page; names are exact fallback when code/href is absent."""
    text = raw.decode("utf-8", errors="strict")
    page = _Page()
    page.feed(text)
    decoder = json.JSONDecoder(parse_float=Decimal)
    rankings = []
    for script in page.scripts:
        if not (script.startswith("self.__next_f.push(") and script.endswith(")")):
            continue
        push = json.loads(script[len("self.__next_f.push("):-1])
        if not isinstance(push, list) or len(push) < 2 or not isinstance(push[1], str):
            continue
        payload = push[1]
        for match in re.finditer(r'"rankingList"\s*:', payload):
            ranking, _ = decoder.raw_decode(payload, match.end())
            rankings.extend(ranking)
    if len(rankings) != 1:
        raise SnapshotError(f"Expected one rankingList for {season}/{stat.slug}.")
    ranking = rankings[0]
    if (ranking.get("id") != f"ranking-{stat.slug}" or ranking.get("category") != "j1"
            or str(ranking.get("year")) != str(season)):
        raise SnapshotError(f"Wrong season/stat identity for {season}/{stat.slug}.")
    data = ranking.get("data")
    if not isinstance(data, list):
        raise SnapshotError(f"Missing ranking data for {season}/{stat.slug}.")
    rows, seen = [], set()
    expected_ids = {value[0] for value in expected.values()}
    for item in data:
        club = item.get("club") if isinstance(item, dict) else None
        name = club.get("name") if isinstance(club, dict) else None
        if not isinstance(name, str) or not name or "\ufffd" in name:
            raise SnapshotError(f"Invalid official club name for {season}/{stat.slug}.")
        try:
            team_id = master.resolve_team_id(name, source="jleague_official",
                                             on=date(season, 12, 31))
        except Exception as exc:
            raise SnapshotError(f"Unresolved official club name: {name!r}") from exc
        if team_id not in expected_ids or team_id in seen:
            raise SnapshotError(f"Unexpected or duplicate club in {season}/{stat.slug}: {name!r}")
        seen.add(team_id)
        code = club.get("code") if isinstance(club, dict) else None
        href = item.get("href")
        official_id = None
        raw_value = _numeric(item.get("score"))
        denominator = next((count for team, count in expected.values() if team == team_id), None)
        if denominator is None:
            raise SnapshotError(f"Missing denominator for resolved team: {team_id!r}")
        derived = None
        if stat.derived_name and stat.value_type in {"total", "decimal_total"}:
            derived = format(Decimal(raw_value) / Decimal(denominator), "f")
        rows.append({"team_id": team_id, "official_club_id": official_id,
                     "official_club_code": code or None,
                     "official_club_name": name,
                     "official_club_href": href if isinstance(href, str) else None,
                     "stat_name": stat.slug, "raw_value": raw_value,
                     "derived_value": derived, "unit": stat.unit,
                     "value_type": stat.value_type, "games_played_basis": denominator,
                     "source_url": BASE_URL.format(season=season, stat=stat.slug)})
    if len(data) != len(expected) or seen != expected_ids:
        raise SnapshotError(f"Unexpected club coverage for {season}/{stat.slug}: {len(seen)}/{len(expected_ids)}")
    return rows, _source_date(" ".join(page.text_parts))


def _fetch(url: str) -> tuple[bytes, int, str, str]:
    request = Request(url, headers={"User-Agent": "J1LeagueAI/1.0 (+historical profile materialization)",
                                    "Accept": "text/html"})
    with urlopen(request, timeout=30) as response:
        return response.read(), response.status, response.geturl(), response.headers.get("Content-Type", "")


def materialize(*, retrieval_id: str | None = None, now: datetime | None = None,
                raw_root: Path = RAW_ROOT, processed_root: Path = PROCESSED_ROOT,
                match_root: Path = MATCH_ROOT, master: TeamMaster | None = None,
                fetch=_fetch, pause=time.sleep) -> dict:
    """Fetch and publish a complete six-stat historical profile artifact."""
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise SnapshotError("retrieved_at must be timezone-aware")
    retrieval_id = retrieval_id or now.strftime("%Y%m%dT%H%M%S%fZ")
    raw_dir = Path(raw_root) / retrieval_id
    output = Path(processed_root) / "2018_2025_j1_team_profiles.csv"
    manifest_path = raw_dir / "manifest.json"
    if raw_dir.exists() or output.exists():
        raise SnapshotError("Refusing to overwrite an existing retrieval or artifact.")
    master = master or load_team_master()
    denominators = {season: expected_teams(season, match_root=match_root, master=master) for season in SEASONS}
    urls = [(season, stat) for season in SEASONS for stat in PROFILE_STATS if season >= stat.available_from]
    retrieved_at = now.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    raw_dir.mkdir(parents=True)
    manifest = {"retrieval_id": retrieval_id, "retrieved_at": retrieved_at,
                "profile_seasons": list(SEASONS), "stats": [s.slug for s in PROFILE_STATS],
                "status": "INCOMPLETE", "expected_rows": sum(len(denominators[y]) for y, _ in urls),
                "actual_rows": 0, "request_count": 0, "cache_reuse_count": 0,
                "pages": [], "denominator_provenance": "validated local J1 match datasets",
                "known_restatement_limitation": True,
                "identity_diagnostics": {"name_exact_resolution_count": 0,
                    "code_present_count": 0, "code_missing_count": 0,
                    "href_present_count": 0, "href_missing_count": 0,
                    "name_fallback_due_to_missing_code_or_href_count": 0}}
    all_rows = []
    try:
        for index, (season, stat) in enumerate(urls):
            if index:
                pause(0.25)
            url = BASE_URL.format(season=season, stat=stat.slug)
            body, status, final_url, content_type = fetch(url)
            digest = hashlib.sha256(body).hexdigest()
            filename = f"{season}_{stat.slug}.html"
            (raw_dir / filename).write_bytes(body)
            page = {"season": season, "stat_name": stat.slug, "requested_url": url,
                    "final_url": final_url, "status": status, "content_type": content_type,
                    "bytes": len(body), "sha256": digest, "html": filename,
                    "parsed_clubs": 0, "source_update_date": None}
            manifest["pages"].append(page); manifest["request_count"] += 1
            if status != 200 or final_url != url or not content_type.lower().startswith("text/html"):
                raise SnapshotError(f"Unexpected official response: {season}/{stat.slug}")
            rows, source_date = parse_profile_page(body, season=season, stat=stat,
                                                   expected=denominators[season], master=master)
            page["parsed_clubs"] = len(rows); page["source_update_date"] = source_date
            for row in rows:
                diagnostics = manifest["identity_diagnostics"]
                diagnostics["name_exact_resolution_count"] += 1
                if row["official_club_code"]:
                    diagnostics["code_present_count"] += 1
                else:
                    diagnostics["code_missing_count"] += 1
                if row["official_club_href"]:
                    diagnostics["href_present_count"] += 1
                else:
                    diagnostics["href_missing_count"] += 1
                if not row["official_club_code"] or not row["official_club_href"]:
                    diagnostics["name_fallback_due_to_missing_code_or_href_count"] += 1
                all_rows.append({"profile_season": season, **row, "source_update_date": source_date,
                                 "retrieved_at": retrieved_at, "retrieval_id": retrieval_id,
                                 "raw_sha256": digest})
        keys = [(r["profile_season"], r["team_id"], r["stat_name"]) for r in all_rows]
        if len(all_rows) != manifest["expected_rows"] or len(keys) != len(set(keys)):
            raise SnapshotError("Historical profile row coverage or duplicate validation failed.")
        Path(processed_root).mkdir(parents=True, exist_ok=True)
        with output.open("x", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS); writer.writeheader(); writer.writerows(all_rows)
        manifest["actual_rows"] = len(all_rows); manifest["status"] = "COMPLETE"
        return {"retrieval_id": retrieval_id, "raw_dir": raw_dir, "processed_path": output,
                "manifest_path": manifest_path, "request_count": len(urls), "row_count": len(all_rows)}
    except Exception as exc:
        manifest["error"] = str(exc); manifest["actual_rows"] = len(all_rows)
        if output.exists(): output.unlink()
        raise
    finally:
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def rebuild_from_raw(*, retrieval_id: str, raw_root: Path = RAW_ROOT,
                     processed_root: Path = PROCESSED_ROOT,
                     match_root: Path = MATCH_ROOT, master: TeamMaster | None = None) -> dict:
    """Explicitly rebuild the processed artifact from one validated raw retrieval.

    No network callback exists in this path. The existing manifest hashes are
    checked before parsing, and the old processed artifact is replaced only by
    this explicitly named rebuild operation.
    """
    master = master or load_team_master()
    raw_dir = Path(raw_root) / retrieval_id
    manifest_path = raw_dir / "manifest.json"
    output = Path(processed_root) / "2018_2025_j1_team_profiles.csv"
    if not manifest_path.exists():
        raise SnapshotError(f"Missing raw retrieval manifest: {retrieval_id}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("retrieval_id") != retrieval_id or manifest.get("status") != "COMPLETE":
        raise SnapshotError("Raw retrieval is not a COMPLETE artifact.")
    denominators = {season: expected_teams(season, match_root=match_root, master=master) for season in SEASONS}
    all_rows = []
    diagnostics = {"name_exact_resolution_count": 0, "code_present_count": 0,
                   "code_missing_count": 0, "href_present_count": 0,
                   "href_missing_count": 0,
                   "name_fallback_due_to_missing_code_or_href_count": 0}
    for page in manifest.get("pages", []):
        season, stat = int(page["season"]), STAT_BY_SLUG.get(page["stat_name"])
        if stat is None or season not in SEASONS or season < stat.available_from:
            raise SnapshotError("Raw manifest contains an unexpected profile page.")
        raw_path = raw_dir / page["html"]
        body = raw_path.read_bytes()
        if hashlib.sha256(body).hexdigest() != page.get("sha256"):
            raise SnapshotError(f"Raw hash mismatch: {raw_path}")
        rows, source_date = parse_profile_page(body, season=season, stat=stat,
                                               expected=denominators[season], master=master)
        if source_date != page.get("source_update_date"):
            raise SnapshotError(f"Source update date changed: {season}/{stat.slug}")
        for row in rows:
            diagnostics["name_exact_resolution_count"] += 1
            if row["official_club_code"]: diagnostics["code_present_count"] += 1
            else: diagnostics["code_missing_count"] += 1
            if row["official_club_href"]: diagnostics["href_present_count"] += 1
            else: diagnostics["href_missing_count"] += 1
            if not row["official_club_code"] or not row["official_club_href"]:
                diagnostics["name_fallback_due_to_missing_code_or_href_count"] += 1
            all_rows.append({"profile_season": season, **row,
                             "source_update_date": source_date,
                             "retrieved_at": manifest["retrieved_at"],
                             "retrieval_id": retrieval_id,
                             "raw_sha256": page["sha256"]})
    expected_rows = sum(len(denominators[season]) for season in SEASONS
                        for stat in PROFILE_STATS if season >= stat.available_from)
    keys = [(r["profile_season"], r["team_id"], r["stat_name"]) for r in all_rows]
    if len(all_rows) != expected_rows or len(keys) != len(set(keys)):
        raise SnapshotError("Raw-only rebuild coverage or duplicate validation failed.")
    Path(processed_root).mkdir(parents=True, exist_ok=True)
    temp = output.with_suffix(".csv.rebuild.tmp")
    with temp.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS); writer.writeheader(); writer.writerows(all_rows)
    temp.replace(output)
    manifest["actual_rows"] = len(all_rows)
    manifest["expected_rows"] = expected_rows
    manifest["identity_diagnostics"] = diagnostics
    manifest["rebuild"] = {"type": "raw_only_parser_schema_cleanup",
                            "processed_path": str(output), "network_request_count": 0,
                            "raw_source_unchanged": True}
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"retrieval_id": retrieval_id, "processed_path": output,
            "manifest_path": manifest_path, "row_count": len(all_rows),
            "request_count": 0, "identity_diagnostics": diagnostics}


if __name__ == "__main__":
    print(json.dumps(materialize(), ensure_ascii=False, default=str, indent=2))
