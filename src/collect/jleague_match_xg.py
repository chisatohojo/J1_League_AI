"""Collect post-match J1 xG from official J.LEAGUE live commentary.

The values in this dataset are observed after a match.  They are not pre-match
features.  A future rolling feature must use only matches completed before its
target match.  UI labels and translation dictionaries never count as xG data;
only the numeric Full Time summary is parsed.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import html as html_module
import json
from pathlib import Path
import re
import time
import unicodedata
from urllib.request import Request, urlopen

from src.collect.teams import TeamMaster, TeamMasterError, load_team_master


ROOT = Path(__file__).resolve().parents[2]
BASE_URL = "https://www.jleague.jp"
USER_AGENT = "J1-League-AI official match xG collector/1.0"
DEFAULT_SEASON = 2025
DEFAULT_INTERVAL = 0.25

OUTPUT_COLUMNS = (
    "season", "match_id", "match_date",
    "home_team_id", "away_team_id", "home_team_name", "away_team_name",
    "home_score", "away_score", "home_xg", "away_xg",
    "home_shots", "away_shots", "home_shots_on_target",
    "away_shots_on_target", "source_match_path_id", "source_url",
    "retrieved_at", "raw_full_time_summary",
)


@dataclass(frozen=True)
class SummaryStats:
    status: str
    home_name: str | None = None
    away_name: str | None = None
    home_xg: Decimal | None = None
    away_xg: Decimal | None = None
    home_shots: int | None = None
    away_shots: int | None = None
    home_shots_on_target: int | None = None
    away_shots_on_target: int | None = None
    raw_summary: str | None = None


@dataclass(frozen=True)
class CommentaryMatch:
    season: int
    source_match_path_id: str
    source_url: str
    match_date: str
    home_full_name: str
    away_full_name: str
    home_short_name: str
    away_short_name: str
    home_score: int
    away_score: int
    summary: SummaryStats
    retrieved_at: str


def schedule_urls(season: int) -> tuple[str, str]:
    """Use bounded official listings so the site's result cap is not hit."""
    return tuple(
        f"{BASE_URL}/j1/match/search-list/?category=j1"
        f"&startdate={season}-{start}&enddate={season}-{end}&period=custom"
        for start, end in (("01-01", "06-30"), ("07-01", "12-31"))
    )


def commentary_url(season: int, path_id: str) -> str:
    if re.fullmatch(r"[0-9]{6}", path_id) is None:
        raise ValueError("Official match path ID must contain exactly six digits.")
    return f"{BASE_URL}/match/j1/{season}/{path_id}/live-commentary/"


def parse_schedule_detail_hrefs(source: str, *, season: int) -> tuple[str, ...]:
    """Read only actual official detailHref values; never generate path IDs."""
    pattern = re.compile(rf"/match/j1/{season}/([0-9]{{6}})")
    ids = sorted(set(pattern.findall(source)))
    if not ids:
        raise ValueError(f"No official J1 detailHref found for {season}.")
    return tuple(ids)


def _normalized_number(raw: str, *, field: str) -> str:
    value = unicodedata.normalize("NFKC", raw).strip()
    if value.startswith(("-", "+")):
        raise ValueError(f"{field} must be nonnegative and unsigned.")
    return value


def _integer(raw: str, *, field: str) -> int:
    value = _normalized_number(raw, field=field)
    if re.fullmatch(r"[0-9]+", value) is None:
        raise ValueError(f"Invalid {field}: {raw!r}.")
    return int(value)


def _decimal(raw: str, *, field: str) -> Decimal:
    value = _normalized_number(raw, field=field)
    if re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", value) is None:
        raise ValueError(f"Invalid {field}: {raw!r}.")
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError(f"Invalid {field}: {raw!r}.") from exc
    if not parsed.is_finite() or parsed < 0:
        raise ValueError(f"{field} must be a finite nonnegative number.")
    return parsed


def _pairs(segment: str, *, label: str, integer: bool, suffix: str = "") -> list[tuple[str, int | Decimal]]:
    if not segment.startswith(label):
        raise ValueError(f"Expected Full Time segment {label!r}.")
    body = segment[len(label):]
    if not body:
        return []
    result = []
    for item in body.split("、"):
        if "：" not in item:
            raise ValueError(f"Malformed Full Time item: {item!r}.")
        name, raw = item.rsplit("：", 1)
        if not name or name != name.strip():
            raise ValueError("Full Time team name must be nonempty and exact.")
        if suffix:
            if not raw.endswith(suffix):
                raise ValueError(f"Missing {suffix!r} suffix in {item!r}.")
            raw = raw[: -len(suffix)]
        value = _integer(raw, field=label) if integer else _decimal(raw, field=label)
        result.append((name, value))
    if len({name for name, _ in result}) != len(result):
        raise ValueError(f"Duplicate team in Full Time segment {label!r}.")
    return result


def parse_full_time_summary(source: str) -> SummaryStats:
    """Parse one unique numeric Full Time sentence from HTML/RSC text."""
    candidates = {
        value.strip()
        for value in re.findall(r"この試合のシュート：[^\"\\<]+", source)
    }
    if not candidates:
        return SummaryStats(status="missing")
    if len(candidates) != 1:
        raise ValueError("Multiple conflicting Full Time summaries.")
    raw_summary = candidates.pop()
    segments = raw_summary.split("／")
    shots = _pairs(segments[0], label="この試合のシュート：", integer=True, suffix="本")
    on_target = (
        _pairs(segments[1], label="枠内シュート：", integer=True, suffix="本")
        if len(segments) >= 2 else []
    )
    xg = (
        _pairs(segments[2], label="ゴール期待値：", integer=False)
        if len(segments) >= 3 else []
    )
    if len(xg) == 0:
        return SummaryStats(status="missing", raw_summary=raw_summary)
    if len(xg) == 1:
        return SummaryStats(
            status="partial", home_name=xg[0][0], home_xg=xg[0][1],
            raw_summary=raw_summary,
        )
    if len(xg) != 2:
        raise ValueError("Full Time xG must have at most two sides.")
    if len(shots) != 2 or len(on_target) != 2:
        raise ValueError("Complete xG summary must also contain two-sided shots and SOT.")
    names = [name for name, _ in xg]
    if [name for name, _ in shots] != names or [name for name, _ in on_target] != names:
        raise ValueError("Full Time team order differs across shots/SOT/xG.")
    return SummaryStats(
        status="complete", home_name=names[0], away_name=names[1],
        home_xg=xg[0][1], away_xg=xg[1][1],
        home_shots=shots[0][1], away_shots=shots[1][1],
        home_shots_on_target=on_target[0][1], away_shots_on_target=on_target[1][1],
        raw_summary=raw_summary,
    )


_IDENTITY = re.compile(
    r'"awayTeam":\{.{0,700}?"name":"([^"\\]+)","nameS":"([^"\\]+)"'
    r'.{0,1100}?"score":([0-9]+).{0,1300}?\},'
    r'"date":"\$D([0-9]{4}-[0-9]{2}-[0-9]{2})T[^"\\]+",'
    r'"homeTeam":\{.{0,700}?"name":"([^"\\]+)","nameS":"([^"\\]+)"'
    r'.{0,1100}?"score":([0-9]+)',
    re.DOTALL,
)


def parse_commentary_page(
    source: str,
    *,
    season: int,
    source_match_path_id: str,
    source_url: str,
    retrieved_at: str,
) -> CommentaryMatch:
    expected_url = commentary_url(season, source_match_path_id)
    if source_url != expected_url:
        raise ValueError("Commentary URL does not match season/path identity.")
    canonical = re.findall(r'<link rel="canonical" href="([^"]+)"', source)
    if set(canonical) != {expected_url}:
        raise ValueError("Missing or conflicting official canonical URL.")
    # React/RSC serializes quoted data as \"...\" inside script text.
    normalized = html_module.unescape(source).replace('\\"', '"')
    identities = set(_IDENTITY.findall(normalized))
    if len(identities) != 1:
        raise ValueError("Expected one exact official match identity payload.")
    away_full, away_short, away_score, match_date, home_full, home_short, home_score = identities.pop()
    if not match_date.startswith(f"{season}-"):
        raise ValueError("Commentary match date is outside requested season.")
    summary = parse_full_time_summary(source)
    if summary.status == "complete" and (
        summary.home_name != home_short or summary.away_name != away_short
    ):
        raise ValueError("Full Time summary teams do not match page identity.")
    return CommentaryMatch(
        season=season, source_match_path_id=source_match_path_id,
        source_url=source_url, match_date=match_date,
        home_full_name=home_full, away_full_name=away_full,
        home_short_name=home_short, away_short_name=away_short,
        home_score=int(home_score), away_score=int(away_score),
        summary=summary, retrieved_at=retrieved_at,
    )


def _side_team_id(master: TeamMaster, match: CommentaryMatch, side: str) -> str:
    full = getattr(match, f"{side}_full_name")
    short = getattr(match, f"{side}_short_name")
    try:
        official_id = master.resolve_team_id(full, source="jleague_official", on=match.match_date)
        data_site_id = master.resolve_team_id(short, source="jleague_data_site", on=match.match_date)
    except TeamMasterError as exc:
        raise ValueError(f"Unresolved {side} team identity: full={full!r}, short={short!r}.") from exc
    if official_id != data_site_id:
        raise ValueError(f"Conflicting {side} team identities: {official_id} vs {data_site_id}.")
    return official_id


def build_processed_rows(
    reference_rows: list[dict[str, str]],
    matches: list[CommentaryMatch],
    master: TeamMaster,
) -> list[dict[str, object]]:
    """Strictly join official page identities to the existing league dataset."""
    required = {
        "match_id", "season", "match_date", "home_team", "away_team",
        "home_score", "away_score", "result",
    }
    if any(required - set(row) for row in reference_rows):
        raise ValueError("Reference J1 rows are missing required columns.")
    by_key: dict[tuple[str, str, str], dict[str, str]] = {}
    seen_match_ids = set()
    for row in reference_rows:
        if str(row["season"]) != str(matches[0].season if matches else row["season"]):
            raise ValueError("Reference season mismatch.")
        key = (row["match_date"], row["home_team"], row["away_team"])
        if key in by_key or row["match_id"] in seen_match_ids:
            raise ValueError("Duplicate reference match identity.")
        seen_match_ids.add(row["match_id"])
        by_key[key] = row
    output, used_reference_ids, path_ids, urls = [], set(), set(), set()
    for match in matches:
        if match.source_match_path_id in path_ids or match.source_url in urls:
            raise ValueError("Duplicate official commentary identity.")
        path_ids.add(match.source_match_path_id)
        urls.add(match.source_url)
        home_id = _side_team_id(master, match, "home")
        away_id = _side_team_id(master, match, "away")
        key = (match.match_date, match.home_short_name, match.away_short_name)
        reference = by_key.get(key)
        if reference is None:
            raise ValueError(f"Official commentary identity mismatch: {key!r}.")
        expected_home = master.resolve_team_id(reference["home_team"], source="jleague_data_site", on=reference["match_date"])
        expected_away = master.resolve_team_id(reference["away_team"], source="jleague_data_site", on=reference["match_date"])
        if (home_id, away_id) != (expected_home, expected_away):
            raise ValueError("Official commentary TeamMaster identity mismatch.")
        if (match.home_score, match.away_score) != (int(reference["home_score"]), int(reference["away_score"])):
            raise ValueError("Official commentary score differs from reference J1 data.")
        expected_result = 1 if match.home_score == match.away_score else 2 if match.home_score > match.away_score else 0
        if expected_result != int(reference["result"]):
            raise ValueError("Reference result is inconsistent with score.")
        if match.summary.status != "complete":
            continue
        if reference["match_id"] in used_reference_ids:
            raise ValueError("Multiple commentary pages joined to one reference match.")
        used_reference_ids.add(reference["match_id"])
        output.append({
            "season": match.season, "match_id": reference["match_id"],
            "match_date": match.match_date, "home_team_id": home_id,
            "away_team_id": away_id, "home_team_name": match.home_full_name,
            "away_team_name": match.away_full_name,
            "home_score": match.home_score, "away_score": match.away_score,
            "home_xg": str(match.summary.home_xg), "away_xg": str(match.summary.away_xg),
            "home_shots": match.summary.home_shots, "away_shots": match.summary.away_shots,
            "home_shots_on_target": match.summary.home_shots_on_target,
            "away_shots_on_target": match.summary.away_shots_on_target,
            "source_match_path_id": match.source_match_path_id,
            "source_url": match.source_url, "retrieved_at": match.retrieved_at,
            "raw_full_time_summary": match.summary.raw_summary,
        })
    output.sort(key=lambda row: (row["match_date"], str(row["match_id"])))
    return output


def _default_fetch(url: str) -> tuple[bytes, str, int]:
    last_error = None
    for attempt in range(3):
        request = Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urlopen(request, timeout=30) as response:
                return response.read(), response.geturl(), response.status
        except (OSError, TimeoutError) as exc:
            last_error = exc
            if attempt < 2:
                time.sleep(attempt + 1)
    assert last_error is not None
    raise last_error


def fetch_cached(
    url: str,
    body_path: str | Path,
    *,
    fetcher=_default_fetch,
    interval: float = DEFAULT_INTERVAL,
    sleep=time.sleep,
) -> tuple[bytes, dict, bool]:
    """Return a SHA-256-validated cache entry or fetch and save one."""
    body_path = Path(body_path)
    metadata_path = body_path.with_suffix(".metadata.json")
    if body_path.exists() and metadata_path.exists():
        body = body_path.read_bytes()
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        valid = (
            metadata.get("requested_url") == url
            and metadata.get("final_url") == url
            and metadata.get("status") == 200
            and metadata.get("bytes") == len(body)
            and metadata.get("sha256") == sha256(body).hexdigest()
        )
        if valid:
            return body, metadata, True
    body, final_url, status = fetcher(url)
    if status != 200 or final_url != url:
        raise ValueError(f"Unexpected official response: status={status}, final_url={final_url!r}.")
    retrieved_at = datetime.now(timezone.utc).isoformat()
    metadata = {
        "requested_url": url, "final_url": final_url, "status": status,
        "retrieved_at": retrieved_at, "bytes": len(body),
        "sha256": sha256(body).hexdigest(),
    }
    body_path.parent.mkdir(parents=True, exist_ok=True)
    body_path.write_bytes(body)
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    sleep(interval)
    return body, metadata, False


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as source:
        return list(csv.DictReader(source))


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def collect_jleague_match_xg(
    *,
    season: int = DEFAULT_SEASON,
    reference_path: str | Path | None = None,
    raw_dir: str | Path | None = None,
    output_path: str | Path | None = None,
    interval: float = DEFAULT_INTERVAL,
    fetcher=_default_fetch,
    sleep=time.sleep,
) -> tuple[list[dict[str, object]], dict]:
    reference_path = Path(reference_path or ROOT / f"data/processed/jleague/{season}_matches_probe.csv")
    raw_dir = Path(raw_dir or ROOT / f"data/raw/jleague_match_xg/{season}")
    output_path = Path(output_path or ROOT / f"data/processed/jleague_match_xg/{season}_j1_match_xg.csv")
    reference = _read_csv(reference_path)
    expected = len(reference)
    if expected == 0:
        raise ValueError("Reference J1 dataset is empty.")
    cache_hits = requests = 0
    source_urls = []
    path_ids = set()
    for index, url in enumerate(schedule_urls(season), 1):
        body, _, hit = fetch_cached(
            url, raw_dir / f"schedule_{index}.html", fetcher=fetcher,
            interval=interval, sleep=sleep,
        )
        cache_hits += int(hit); requests += int(not hit); source_urls.append(url)
        path_ids.update(parse_schedule_detail_hrefs(body.decode("utf-8"), season=season))
    if len(path_ids) != expected:
        raise ValueError(f"Official schedule/reference count mismatch: {len(path_ids)} != {expected}.")
    parsed, partial, missing, identity_mismatch = [], 0, 0, 0
    for path_id in sorted(path_ids):
        url = commentary_url(season, path_id)
        body, metadata, hit = fetch_cached(
            url, raw_dir / f"{path_id}.html", fetcher=fetcher,
            interval=interval, sleep=sleep,
        )
        cache_hits += int(hit); requests += int(not hit); source_urls.append(url)
        try:
            match = parse_commentary_page(
                body.decode("utf-8"), season=season,
                source_match_path_id=path_id, source_url=url,
                retrieved_at=metadata["retrieved_at"],
            )
        except ValueError:
            identity_mismatch += 1
            raise
        parsed.append(match)
        partial += int(match.summary.status == "partial")
        missing += int(match.summary.status == "missing")
    master = load_team_master()
    rows = build_processed_rows(reference, parsed, master)
    complete = sum(match.summary.status == "complete" for match in parsed)
    manifest = {
        "season": season,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "expected_matches": expected,
        "downloaded": requests,
        "cache_hits": cache_hits,
        "parse_success": complete,
        "partial": partial,
        "missing": missing,
        "identity_mismatch": identity_mismatch,
        "source_urls": source_urls,
        "request_count": requests,
        "processed_rows": len(rows),
        "complete": False,
    }
    raw_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = raw_dir / "manifest.json"
    if complete != expected or partial or missing or identity_mismatch or len(rows) != expected:
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        raise ValueError("Incomplete match xG coverage; processed dataset was not written.")
    if len({str(row["match_id"]) for row in rows}) != expected:
        raise ValueError("Processed match IDs are not unique.")
    if len({str(row["source_url"]) for row in rows}) != expected:
        raise ValueError("Processed source URLs are not unique.")
    manifest["complete"] = True
    _write_csv(output_path, rows)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return rows, manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--season", type=int, default=DEFAULT_SEASON)
    parser.add_argument("--reference-path")
    parser.add_argument("--raw-dir")
    parser.add_argument("--output-path")
    parser.add_argument("--interval", type=float, default=DEFAULT_INTERVAL)
    args = parser.parse_args()
    rows, manifest = collect_jleague_match_xg(
        season=args.season, reference_path=args.reference_path,
        raw_dir=args.raw_dir, output_path=args.output_path,
        interval=args.interval,
    )
    print(json.dumps({**manifest, "rows": len(rows)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
