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

LEGACY_FULL_TIME_SUMMARY = "legacy_full_time_summary"
TWO_WIDGET_SUMMARY = "two_widget_summary"
AUTO_SUMMARY = "auto"


@dataclass(frozen=True)
class CompetitionConfig:
    key: str
    output_season: str
    page_year: int
    official_name: str
    schedule_urls: tuple[str, ...]
    reference_path: Path
    raw_dir: Path
    output_path: Path
    expected_matches: int
    scheduled_matches: int
    source_format: str
    allow_extra_time_source_score: bool = False


def _schedule_url(start: str, end: str) -> str:
    return (
        f"{BASE_URL}/j1/match/search-list/?category=j1"
        f"&startdate={start}&enddate={end}&period=custom"
    )


COMPETITIONS = {
    "2025_j1": CompetitionConfig(
        key="j1_2025", output_season="2025", page_year=2025,
        official_name="明治安田Ｊ１リーグ",
        schedule_urls=tuple(
            _schedule_url(f"2025-{start}", f"2025-{end}")
            for start, end in (("01-01", "06-30"), ("07-01", "12-31"))
        ),
        reference_path=ROOT / "data/processed/jleague/2025_matches_probe.csv",
        raw_dir=ROOT / "data/raw/jleague_match_xg/2025",
        output_path=ROOT / "data/processed/jleague_match_xg/2025_j1_match_xg.csv",
        expected_matches=380, scheduled_matches=380,
        source_format=LEGACY_FULL_TIME_SUMMARY,
    ),
    "2026_hyakunen": CompetitionConfig(
        key="j1_hyakunen_2026", output_season="2026", page_year=2026,
        official_name="明治安田Ｊ１百年構想リーグ",
        schedule_urls=(_schedule_url("2026-01-01", "2026-06-30"),),
        reference_path=ROOT / "data/processed/jleague/2026_hyakunen/matches.csv",
        raw_dir=ROOT / "data/raw/jleague_match_xg/2026_hyakunen",
        output_path=ROOT / "data/processed/jleague_match_xg/2026_hyakunen_j1_match_xg.csv",
        expected_matches=200, scheduled_matches=200,
        source_format=LEGACY_FULL_TIME_SUMMARY,
        allow_extra_time_source_score=True,
    ),
    "2026_27_j1": CompetitionConfig(
        key="j1_2026_2027", output_season="2026/27", page_year=2026,
        official_name="明治安田Ｊ１リーグ",
        schedule_urls=(_schedule_url("2026-07-01", "2026-09-21"),),
        reference_path=ROOT / "data/processed/jleague/2026_27/completed_matches.csv",
        raw_dir=ROOT / "data/raw/jleague_match_xg/2026_27",
        output_path=ROOT / "data/processed/jleague_match_xg/2026_27_j1_match_xg.csv",
        expected_matches=80, scheduled_matches=380,
        source_format=TWO_WIDGET_SUMMARY,
    ),
}

OUTPUT_COLUMNS = (
    "competition", "season", "match_id", "match_date",
    "home_team_id", "away_team_id", "home_team_name", "away_team_name",
    "home_score", "away_score", "home_xg", "away_xg",
    "home_shots", "away_shots", "home_shots_on_target",
    "away_shots_on_target", "source_match_path_id", "source_url",
    "source_format", "source_home_score", "source_away_score",
    "score_scope_status", "xg_time_scope", "retrieved_at",
    "raw_full_time_summary",
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
    source_format: str | None = None


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


def parse_schedule_detail_hrefs(
    source: str,
    *,
    season: int,
    competition_name: str | None = None,
    completed_only: bool = False,
) -> tuple[str, ...]:
    """Read actual detailHref values, optionally under an exact competition.

    Filtered discovery reads the observed RSC grouping: one
    ``leagueDisplayName`` followed by match records containing adjacent
    ``state`` and ``detailHref`` fields.  It never generates path IDs.
    """
    if competition_name is None and not completed_only:
        pattern = re.compile(rf"/match/j1/{season}/([0-9]{{6}})")
        ids = sorted(set(pattern.findall(source)))
    else:
        normalized = source.replace('\\"', '"')
        groups = list(re.finditer(r'"leagueDisplayName":"([^"\\]+)"', normalized))
        observed: dict[str, tuple[str, str]] = {}
        for index, group in enumerate(groups):
            end = groups[index + 1].start() if index + 1 < len(groups) else len(normalized)
            name = group.group(1)
            for state, path_id in re.findall(
                rf'"state":"([^"\\]+)","detailHref":"/match/j1/{season}/([0-9]{{6}})"',
                normalized[group.end():end],
            ):
                identity = (name, state)
                if path_id in observed and observed[path_id] != identity:
                    raise ValueError(f"Conflicting official schedule identity for {path_id}.")
                observed[path_id] = identity
        ids = sorted(
            path_id for path_id, (name, state) in observed.items()
            if (competition_name is None or name == competition_name)
            and (not completed_only or state == "game-over")
        )
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
        return SummaryStats(status="missing", source_format=LEGACY_FULL_TIME_SUMMARY)
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
        return SummaryStats(
            status="missing", raw_summary=raw_summary,
            source_format=LEGACY_FULL_TIME_SUMMARY,
        )
    if len(xg) == 1:
        return SummaryStats(
            status="partial", home_name=xg[0][0], home_xg=xg[0][1],
            raw_summary=raw_summary, source_format=LEGACY_FULL_TIME_SUMMARY,
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
        raw_summary=raw_summary, source_format=LEGACY_FULL_TIME_SUMMARY,
    )


def _single_value(raw_summary: str, *, label: str, integer: bool, suffix: str = ""):
    segments = raw_summary.split("、")
    selected = [segment for segment in segments if segment.startswith(label)]
    if len(selected) != 1:
        return None
    raw = selected[0][len(label):]
    if not raw:
        return None
    if suffix:
        if not raw.endswith(suffix):
            raise ValueError(f"Missing {suffix!r} suffix in one-sided Full Time summary.")
        raw = raw[: -len(suffix)]
    return _integer(raw, field=label) if integer else _decimal(raw, field=label)


_TWO_WIDGET = re.compile(
    r'"visual":"[^"\\]*:(awayTeam|homeTeam):teamLogo"'
    r'.{0,1800}?"children":"(この試合のシュート：[^"\\<]+)"',
    re.DOTALL,
)


def parse_two_widget_summary(source: str) -> SummaryStats:
    """Parse the observed 2026/27 home/away Full Time widget pair.

    Values are bound through each widget's explicit ``homeTeam`` or
    ``awayTeam`` logo reference.  Page order alone is never used.
    """
    normalized = html_module.unescape(source).replace('\\"', '"')
    by_side: dict[str, str] = {}
    for side, raw_summary in _TWO_WIDGET.findall(normalized):
        raw_summary = raw_summary.strip()
        if side in by_side and by_side[side] != raw_summary:
            raise ValueError(f"Conflicting {side} Full Time widgets.")
        by_side[side] = raw_summary
    if not by_side:
        return SummaryStats(status="missing", source_format=TWO_WIDGET_SUMMARY)

    parsed = {}
    for side, raw_summary in by_side.items():
        parsed[side] = {
            "shots": _single_value(
                raw_summary, label="この試合のシュート：", integer=True, suffix="本"
            ),
            "sot": _single_value(raw_summary, label="枠内シュート：", integer=True, suffix="本"),
            "xg": _single_value(raw_summary, label="ゴール期待値：", integer=False),
        }
    present_xg = sum(values["xg"] is not None for values in parsed.values())
    raw = json.dumps(
        {side: by_side[side] for side in ("homeTeam", "awayTeam") if side in by_side},
        ensure_ascii=False, separators=(",", ":"),
    )
    if present_xg == 0:
        return SummaryStats(
            status="missing", raw_summary=raw, source_format=TWO_WIDGET_SUMMARY,
        )
    if present_xg == 1:
        side = next(side for side, values in parsed.items() if values["xg"] is not None)
        kwargs = {"home_xg" if side == "homeTeam" else "away_xg": parsed[side]["xg"]}
        return SummaryStats(
            status="partial", raw_summary=raw, source_format=TWO_WIDGET_SUMMARY,
            **kwargs,
        )
    if set(parsed) != {"homeTeam", "awayTeam"}:
        raise ValueError("Complete two-widget xG requires one explicit widget per side.")
    if any(values["shots"] is None or values["sot"] is None for values in parsed.values()):
        raise ValueError("Complete two-widget xG also requires shots and SOT for both sides.")
    return SummaryStats(
        status="complete",
        home_xg=parsed["homeTeam"]["xg"], away_xg=parsed["awayTeam"]["xg"],
        home_shots=parsed["homeTeam"]["shots"], away_shots=parsed["awayTeam"]["shots"],
        home_shots_on_target=parsed["homeTeam"]["sot"],
        away_shots_on_target=parsed["awayTeam"]["sot"],
        raw_summary=raw, source_format=TWO_WIDGET_SUMMARY,
    )


def parse_match_summary(source: str, *, source_format: str = AUTO_SUMMARY) -> SummaryStats:
    if source_format == LEGACY_FULL_TIME_SUMMARY:
        return parse_full_time_summary(source)
    if source_format == TWO_WIDGET_SUMMARY:
        return parse_two_widget_summary(source)
    if source_format != AUTO_SUMMARY:
        raise ValueError(f"Unknown Full Time source format: {source_format!r}.")
    two_widget = parse_two_widget_summary(source)
    if two_widget.status != "missing":
        return two_widget
    return parse_full_time_summary(source)


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
    source_format: str = LEGACY_FULL_TIME_SUMMARY,
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
    summary = parse_match_summary(source, source_format=source_format)
    if summary.status == "complete" and (
        summary.source_format == LEGACY_FULL_TIME_SUMMARY
        and (summary.home_name != home_short or summary.away_name != away_short)
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
    *,
    competition: str | None = None,
    output_season: str | None = None,
    allow_extra_time_source_score: bool = False,
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
        regulation_score = (int(reference["home_score"]), int(reference["away_score"]))
        source_score = (match.home_score, match.away_score)
        score_scope_status = "REGULATION_MATCH"
        xg_time_scope = "REGULATION"
        if source_score != regulation_score:
            extra_time_score = (
                reference.get("home_extra_time_score", ""),
                reference.get("away_extra_time_score", ""),
            )
            safely_explained = (
                allow_extra_time_source_score
                and reference.get("extra_time_played") == "True"
                and all(value != "" for value in extra_time_score)
                and source_score == tuple(int(value) for value in extra_time_score)
            )
            if not safely_explained:
                raise ValueError("Official commentary score differs from reference J1 data.")
            score_scope_status = "EXTRA_TIME_SOURCE_SCORE"
            xg_time_scope = "OFFICIAL_FINAL_SCOPE_UNRESOLVED"
        expected_result = (
            1 if regulation_score[0] == regulation_score[1]
            else 2 if regulation_score[0] > regulation_score[1] else 0
        )
        if expected_result != int(reference["result"]):
            raise ValueError("Reference result is inconsistent with score.")
        if match.summary.status != "complete":
            continue
        if reference["match_id"] in used_reference_ids:
            raise ValueError("Multiple commentary pages joined to one reference match.")
        used_reference_ids.add(reference["match_id"])
        output.append({
            "competition": competition or f"j1_{match.season}",
            "season": output_season or str(match.season),
            "match_id": reference["match_id"],
            "match_date": match.match_date, "home_team_id": home_id,
            "away_team_id": away_id, "home_team_name": match.home_full_name,
            "away_team_name": match.away_full_name,
            "home_score": regulation_score[0], "away_score": regulation_score[1],
            "home_xg": str(match.summary.home_xg), "away_xg": str(match.summary.away_xg),
            "home_shots": match.summary.home_shots, "away_shots": match.summary.away_shots,
            "home_shots_on_target": match.summary.home_shots_on_target,
            "away_shots_on_target": match.summary.away_shots_on_target,
            "source_match_path_id": match.source_match_path_id,
            "source_url": match.source_url,
            "source_format": match.summary.source_format,
            "source_home_score": source_score[0], "source_away_score": source_score[1],
            "score_scope_status": score_scope_status,
            "xg_time_scope": xg_time_scope,
            "retrieved_at": match.retrieved_at,
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
    competition_name: str | None = None,
    reference_path: str | Path | None = None,
    raw_dir: str | Path | None = None,
    output_path: str | Path | None = None,
    interval: float = DEFAULT_INTERVAL,
    fetcher=_default_fetch,
    sleep=time.sleep,
) -> tuple[list[dict[str, object]], dict]:
    config = COMPETITIONS.get(competition_name) if competition_name else None
    if competition_name and config is None:
        raise ValueError(f"Unknown competition configuration: {competition_name!r}.")
    if config:
        season = config.page_year
        schedule_source_urls = config.schedule_urls
        official_name = config.official_name
        source_format = config.source_format
        expected_config = config.expected_matches
        scheduled_matches = config.scheduled_matches
        output_season = config.output_season
        competition_key = config.key
        allow_extra_time_source_score = config.allow_extra_time_source_score
        reference_path = Path(reference_path or config.reference_path)
        raw_dir = Path(raw_dir or config.raw_dir)
        output_path = Path(output_path or config.output_path)
    else:
        schedule_source_urls = schedule_urls(season)
        official_name = None
        source_format = LEGACY_FULL_TIME_SUMMARY
        expected_config = None
        scheduled_matches = None
        output_season = str(season)
        competition_key = f"j1_{season}"
        allow_extra_time_source_score = False
        reference_path = Path(reference_path or ROOT / f"data/processed/jleague/{season}_matches_probe.csv")
        raw_dir = Path(raw_dir or ROOT / f"data/raw/jleague_match_xg/{season}")
        output_path = Path(output_path or ROOT / f"data/processed/jleague_match_xg/{season}_j1_match_xg.csv")
    reference = _read_csv(reference_path)
    expected = len(reference)
    if expected == 0:
        raise ValueError("Reference J1 dataset is empty.")
    if expected_config is not None and expected != expected_config:
        raise ValueError(f"Configured reference count mismatch: {expected} != {expected_config}.")
    cache_hits = requests = 0
    source_urls = []
    path_ids = set()
    for index, url in enumerate(schedule_source_urls, 1):
        body, _, hit = fetch_cached(
            url, raw_dir / f"schedule_{index}.html", fetcher=fetcher,
            interval=interval, sleep=sleep,
        )
        cache_hits += int(hit); requests += int(not hit); source_urls.append(url)
        path_ids.update(parse_schedule_detail_hrefs(
            body.decode("utf-8"), season=season,
            competition_name=official_name,
            completed_only=config is not None,
        ))
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
                source_format=source_format,
            )
        except ValueError:
            identity_mismatch += 1
            raise
        parsed.append(match)
        partial += int(match.summary.status == "partial")
        missing += int(match.summary.status == "missing")
    master = load_team_master()
    rows = build_processed_rows(
        reference, parsed, master, competition=competition_key,
        output_season=output_season,
        allow_extra_time_source_score=allow_extra_time_source_score,
    )
    complete = sum(match.summary.status == "complete" for match in parsed)
    source_format_counts = {}
    for match in parsed:
        key = match.summary.source_format or "unknown"
        source_format_counts[key] = source_format_counts.get(key, 0) + 1
    score_scope_mismatch = sum(
        row["score_scope_status"] == "EXTRA_TIME_SOURCE_SCORE" for row in rows
    )
    manifest = {
        "competition": competition_key,
        "season": output_season,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "expected_matches": expected,
        "completed_matches": expected,
        "scheduled_matches": scheduled_matches or expected,
        "future_excluded": (scheduled_matches or expected) - expected,
        "downloaded": requests,
        "cache_hits": cache_hits,
        "parse_success": complete,
        "partial": partial,
        "missing": missing,
        "identity_mismatch": identity_mismatch,
        "score_scope_mismatch": score_scope_mismatch,
        "source_format_counts": source_format_counts,
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
    parser.add_argument("--competition", choices=sorted(COMPETITIONS))
    parser.add_argument("--reference-path")
    parser.add_argument("--raw-dir")
    parser.add_argument("--output-path")
    parser.add_argument("--interval", type=float, default=DEFAULT_INTERVAL)
    args = parser.parse_args()
    rows, manifest = collect_jleague_match_xg(
        season=args.season, competition_name=args.competition,
        reference_path=args.reference_path,
        raw_dir=args.raw_dir, output_path=args.output_path,
        interval=args.interval,
    )
    print(json.dumps({**manifest, "rows": len(rows)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
