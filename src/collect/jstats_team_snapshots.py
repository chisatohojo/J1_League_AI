"""Capture official J1 team statistics as observed point-in-time snapshots.

These are season-to-date page values, NOT reconstructed match statistics or
pre-match features. The site's update lag and games-played basis are unknown.
"""

import csv
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import time
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from src.collect.teams import TeamMaster, load_team_master


ROOT = Path(__file__).resolve().parents[2]
SCHEDULE = ROOT / "data/processed/jleague/2026_27/schedule.csv"
RAW_ROOT = ROOT / "data/raw/jstats_team_snapshots"
PROCESSED_ROOT = ROOT / "data/processed/jstats_team_snapshots"
SEASON = "2026-27"
BASE_URL = "https://www.jleague.jp/j1/stats/club/2026-27/{slug}/search-list/"


@dataclass(frozen=True)
class Stat:
    slug: str
    label: str
    value_type: str
    unit: str


# Only routes and labels observed in J_STATS_TEAM_SNAPSHOT_COLLECTOR_DESIGN.md.
STATS = (
    Stat("shoot", "シュート総数", "total", "回"),
    Stat("shoot_on_target", "枠内シュート総数", "total", "回"),
    Stat("suffer_shoot_on_target", "被枠内シュート総数", "total", "回"),
    Stat("ball_rate", "平均ボール支配率", "percentage", "%"),
    Stat("pass_count", "パス総数", "total", "回"),
    Stat("pass_count_per_game", "1試合平均パス数", "average", "回/試合"),
    Stat("expected_goals", "ゴール期待値", "unknown", ""),
    Stat("expected_goals_against", "被ゴール期待値", "unknown", ""),
    Stat("distance_per_game", "1試合平均走行距離", "average", "km/試合"),
    Stat("sprint_per_game", "1試合平均スプリント回数", "average", "回/試合"),
)
SUPPLEMENTAL_STATS = (
    Stat("cross_count", "クロス総数", "total", "回"),
    Stat("chance_create", "チャンスクリエイト総数", "total", "回"),
    Stat("suffer_shoot", "被シュート総数", "total", "回"),
    Stat("clear_count", "クリア総数", "total", "回"),
    Stat("tackle_count", "タックル総数", "total", "回"),
    Stat("tackle_rate", "タックル成功率", "percentage", "%"),
    Stat("block_count", "ブロック総数", "total", "回"),
    Stat("intercept_count", "インターセプト総数", "total", "回"),
    Stat("recovery_count", "こぼれ球奪取数", "total", "回"),
    Stat("expected_goals_against_excl_pk", "被ゴール期待値 ※PKを除く", "unknown", ""),
    Stat("dribble_count", "ドリブル総数", "total", "回"),
    Stat("dribble_rate", "ドリブル成功率", "percentage", "%"),
    Stat("air_battle_win_count", "空中戦勝利数", "total", "回"),
    Stat("air_battle_win_rate", "空中戦勝率", "percentage", "%"),
    Stat("one_on_one", "1vs1勝利総数", "total", "回"),
    Stat("at_sprint_per_game", "1試合平均Atスプリント回数", "average", "回/試合"),
    Stat("mt_sprint_per_game", "1試合平均Mtスプリント回数", "average", "回/試合"),
    Stat("dt_sprint_per_game", "1試合平均Dtスプリント回数", "average", "回/試合"),
    Stat("possession_distance_per_game", "1試合平均ポゼッション時の走行距離", "average", "km/試合"),
    Stat("possession_sprint_per_game", "1試合平均ポゼッション時のスプリント回数", "average", "回/試合"),
    Stat("un_possession_distance_per_game", "1試合平均被ポゼッション時の走行距離", "average", "km/試合"),
    Stat("un_possession_sprint_per_game", "1試合平均被ポゼッション時のスプリント回数", "average", "回/試合"),
    Stat("pass_rate", "パス成功率", "percentage", "%"),
    Stat("through_pass_count", "スルーパス総数", "total", "回"),
    Stat("through_pass_rate", "スルーパス成功率", "percentage", "%"),
    Stat("foul_count", "ファウル総数", "total", "回"),
    Stat("yellow_count", "警告数", "total", "枚"),
)
RELATED_BASE_SNAPSHOT_ID = "20260920T212008928504Z"
SUPPLEMENTAL_SOURCE_STATE_DATE = "2026-09-14"
STAT_BY_SLUG = {stat.slug: stat for stat in (*STATS, *SUPPLEMENTAL_STATS)}
CSV_FIELDS = (
    "snapshot_id", "retrieved_at", "source_updated_at", "source_updated_date_jst",
    "competition", "season", "team_id", "official_club_id", "official_club_name",
    "official_club_slug", "games_played", "stat_name", "stat_value", "raw_value",
    "value_type", "unit", "source_url", "raw_sha256",
)


class SnapshotError(ValueError):
    """A source page or snapshot failed a strict acquisition invariant."""


class _Page(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.scripts = []
        self.visible = []
        self.text_parts = []
        self._in_script = False
        self._script_parts = []
        self._club_link = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        classes = set(attrs.get("class", "").split())
        if tag == "script":
            self._in_script = True
            self._script_parts = []
        elif tag == "a" and "m-ranking-club-list-item__link" in classes:
            self._club_link = attrs.get("href")
        elif tag == "div" and "m-ranking-club-list-item" in classes:
            self.visible.append((self._club_link, attrs.get("name"), attrs.get("score")))

    def handle_data(self, data):
        if self._in_script:
            self._script_parts.append(data)
        else:
            self.text_parts.append(data)

    def handle_endtag(self, tag):
        if tag == "script":
            self.scripts.append("".join(self._script_parts))
            self._in_script = False
        elif tag == "a":
            self._club_link = None


def _numeric(value):
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal, str)):
        raise SnapshotError(f"Non-numeric stat value: {value!r}")
    raw = str(value)
    if not re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", raw):
        raise SnapshotError(f"Non-numeric stat value: {raw!r}")
    try:
        if not Decimal(raw).is_finite():
            raise SnapshotError(f"Non-finite stat value: {raw!r}")
    except InvalidOperation as exc:
        raise SnapshotError(f"Non-numeric stat value: {raw!r}") from exc
    return raw


def expected_club_slugs(schedule_path: Path = SCHEDULE) -> set[str]:
    """Read only club codes from the ordinary 2026/27 J1 schedule, not results."""
    with Path(schedule_path).open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not {"home_club", "away_club"} <= set(reader.fieldnames or ()):
            raise SnapshotError("J1 schedule lacks club codes.")
        slugs = {row[side] for row in reader for side in ("home_club", "away_club")}
    if len(slugs) != 20 or any(not re.fullmatch(r"[a-z][a-z0-9]*", slug or "") for slug in slugs):
        raise SnapshotError(f"Expected exactly 20 J1 club slugs; got {len(slugs)}.")
    return slugs


def parse_page(raw: bytes, *, stat: Stat, expected_slugs: set[str], master: TeamMaster,
               observed_date=None):
    """Parse the complete embedded RSC ranking; cross-check the visible top 10."""
    if STAT_BY_SLUG.get(stat.slug) != stat or len(expected_slugs) != 20:
        raise SnapshotError("Unknown stat or incomplete J1 membership.")
    try:
        html = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise SnapshotError("Official page is not lossless UTF-8.") from exc
    page = _Page()
    page.feed(html)
    if "2026/27" not in " ".join(page.text_parts):
        raise SnapshotError("Page title/season does not identify 2026/27.")
    rankings = []
    decoder = json.JSONDecoder(parse_float=Decimal)
    for script in page.scripts:
        if not script.startswith("self.__next_f.push(") or not script.endswith(")"):
            continue
        try:
            push = json.loads(script[len("self.__next_f.push("):-1])
        except (ValueError, TypeError) as exc:
            raise SnapshotError("Malformed Next.js flight payload.") from exc
        if not isinstance(push, list) or len(push) < 2 or not isinstance(push[1], str):
            continue
        payload = push[1]
        for match in re.finditer(r'"rankingList"\s*:', payload):
            try:
                start = match.end()
                while start < len(payload) and payload[start].isspace():
                    start += 1
                ranking, _ = decoder.raw_decode(payload, start)
            except ValueError as exc:
                raise SnapshotError("Malformed RSC rankingList.") from exc
            rankings.append(ranking)
    if len(rankings) != 1 or not isinstance(rankings[0], list) or len(rankings[0]) != 1:
        raise SnapshotError(f"Expected one RSC rankingList, found {len(rankings)}.")
    ranking = rankings[0][0]
    if (ranking.get("id") != f"ranking-{stat.slug}" or ranking.get("category") != "j1"
            or str(ranking.get("year")) != "2026" or ranking.get("stats") != {"value": stat.slug, "label": stat.label}):
        raise SnapshotError(f"Wrong season, competition, slug or label for {stat.slug}.")
    data = ranking.get("data")
    if not isinstance(data, list) or len(data) != 20:
        raise SnapshotError(f"{stat.slug}: expected 20 RSC clubs, got {len(data) if isinstance(data, list) else 'invalid'}.")
    rows, seen = [], set()
    aliases = master.aliases
    for item in data:
        club = item.get("club") if isinstance(item, dict) else None
        if not isinstance(club, dict):
            raise SnapshotError("Missing RSC club identity.")
        slug, name = club.get("code"), club.get("name")
        if (not isinstance(slug, str) or slug not in expected_slugs or slug in seen
                or item.get("href") != f"/club/{slug}" or not isinstance(name, str)
                or not name or item.get("name") != name):
            raise SnapshotError(f"Missing, duplicate or inconsistent club: {slug!r} / {name!r}.")
        seen.add(slug)
        matches = [alias for alias in aliases if alias.source == "jleague_official"
                   and alias.source_name == name and alias.source_club_id == slug]
        if len(matches) != 1:
            raise SnapshotError(f"Exact TeamMaster name/slug linkage failed: {slug!r} / {name!r}.")
        team_id = master.resolve_team_id(name, source="jleague_official", on=observed_date)
        if team_id != matches[0].team_id:
            raise SnapshotError(f"TeamMaster identity conflict: {slug!r}.")
        score = _numeric(item.get("score"))
        rows.append({"team_id": team_id, "official_club_id": slug,
                     "official_club_name": name, "official_club_slug": slug,
                     "stat_value": score, "raw_value": score})
    if seen != expected_slugs or len({row["team_id"] for row in rows}) != 20:
        raise SnapshotError("RSC clubs do not exactly match J1 membership / stable IDs.")
    if len(page.visible) != 10:
        raise SnapshotError(f"Expected 10 initially visible clubs, got {len(page.visible)}.")
    for visible, row in zip(page.visible, rows):
        href, name, score = visible
        if href != f"/club/{row['official_club_slug']}/" or name != row["official_club_name"] or _numeric(score) != row["stat_value"]:
            raise SnapshotError("Visible ranking and embedded RSC ranking disagree.")
    text = " ".join(page.text_parts)
    dates = set(re.findall(r"(20[0-9]{2})/([0-9]{1,2})/([0-9]{1,2})\s*更新", text))
    if len(dates) > 1:
        raise SnapshotError("Ambiguous official update dates.")
    source_date = None
    if dates:
        year, month, day = next(iter(dates))
        source_date = f"{int(year):04d}-{int(month):02d}-{int(day):02d}"
        datetime.fromisoformat(source_date)
    return rows, source_date


def _fetch(url: str):
    request = Request(url, headers={"User-Agent": "J1LeagueAI/1.0 (+point-in-time research; no bulk crawl)",
                                    "Accept": "text/html"})
    with urlopen(request, timeout=30) as response:
        return response.read(), response.status, response.geturl(), response.headers.get("Content-Type", "")


def collect_snapshot(*, raw_root=RAW_ROOT, processed_root=PROCESSED_ROOT,
                     schedule_path=SCHEDULE, master=None, now=None, fetch=_fetch, pause=time.sleep,
                     stats=STATS, related_snapshot_id=None, required_source_date=None,
                     previous_source_state_date=None, previous_snapshot_ids=None):
    """Fetch each allowlisted page once; publish only a complete 20 x N snapshot.

    A failed run retains its raw pages and INCOMPLETE manifest, never a CSV.
    Existing snapshot IDs are never overwritten or appended twice.
    """
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None or now.utcoffset() != timezone.utc.utcoffset(now):
        raise SnapshotError("Retrieval time must be UTC-aware.")
    snapshot_id = now.strftime("%Y%m%dT%H%M%S%fZ")
    retrieved_at = now.isoformat().replace("+00:00", "Z")
    raw_dir = Path(raw_root) / snapshot_id
    output = Path(processed_root) / f"{snapshot_id}.csv"
    if raw_dir.exists() or output.exists():
        raise SnapshotError(f"Snapshot already exists: {snapshot_id}.")
    expected = expected_club_slugs(schedule_path)
    master = master or load_team_master()
    stats = tuple(stats)
    if not stats or any(STAT_BY_SLUG.get(stat.slug) != stat for stat in stats):
        raise SnapshotError("Empty or unknown stat allowlist.")
    urls = [BASE_URL.format(slug=stat.slug) for stat in stats]
    if len(urls) != len(set(urls)):
        raise SnapshotError("Duplicate stat URL in allowlist.")
    raw_dir.mkdir(parents=True)
    manifest = {"snapshot_id": snapshot_id, "retrieved_at": retrieved_at,
                "season": SEASON, "requested_stats": [s.slug for s in stats],
                "status": "INCOMPLETE", "pages": []}
    if related_snapshot_id is not None:
        manifest["related_snapshot_id"] = related_snapshot_id
    if required_source_date is not None:
        manifest["source_state_date"] = required_source_date
    if previous_source_state_date is not None:
        manifest["previous_source_state_date"] = previous_source_state_date
    if previous_snapshot_ids is not None:
        manifest["previous_snapshot_ids"] = list(previous_snapshot_ids)
    all_rows = []
    try:
        for index, (stat, url) in enumerate(zip(stats, urls)):
            if index:
                pause(0.25)
            body, status, final_url, content_type = fetch(url)
            if not isinstance(body, bytes):
                raise SnapshotError(f"{stat.slug}: non-byte HTTP response.")
            digest = hashlib.sha256(body).hexdigest()
            page_record = {"stat_name": stat.slug, "requested_url": url, "final_url": final_url,
                           "status": status, "content_type": content_type, "bytes": len(body),
                           "sha256": digest, "html": f"{stat.slug}.html", "parsed_clubs": 0}
            manifest["pages"].append(page_record)
            (raw_dir / page_record["html"]).write_bytes(body)
            if status != 200 or final_url != url or not content_type.lower().startswith("text/html"):
                raise SnapshotError(f"{stat.slug}: unexpected HTTP status, redirect or content type.")
            rows, source_date = parse_page(body, stat=stat, expected_slugs=expected,
                                           master=master,
                                           observed_date=now.astimezone(ZoneInfo("Asia/Tokyo")).date())
            if required_source_date is not None and source_date != required_source_date:
                raise SnapshotError(
                    f"{stat.slug}: source update date {source_date!r} does not match "
                    f"required state {required_source_date!r}."
                )
            page_record["parsed_clubs"] = len(rows)
            page_record["source_updated_date_jst"] = source_date
            for row in rows:
                all_rows.append({"snapshot_id": snapshot_id, "retrieved_at": retrieved_at,
                                 "source_updated_at": "", "source_updated_date_jst": source_date or "",
                                 "competition": "j1", "season": SEASON, **row,
                                 "games_played": "", "stat_name": stat.slug,
                                 "value_type": stat.value_type, "unit": stat.unit,
                                 "source_url": url, "raw_sha256": digest})
        if len(all_rows) != 20 * len(stats) or len({(r["team_id"], r["stat_name"]) for r in all_rows}) != len(all_rows):
            raise SnapshotError("Incomplete or duplicate processed snapshot rows.")
        Path(processed_root).mkdir(parents=True, exist_ok=True)
        with output.open("x", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
            writer.writeheader()
            writer.writerows(all_rows)
        manifest["status"] = "COMPLETE"
    except Exception as exc:
        manifest["error"] = str(exc)
        if output.exists():
            output.unlink()
        raise
    finally:
        (raw_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"snapshot_id": snapshot_id, "raw_dir": raw_dir, "processed_path": output,
            "request_count": len(manifest["pages"]), "row_count": len(all_rows),
            "parsed_clubs_per_stat": {p["stat_name"]: p["parsed_clubs"] for p in manifest["pages"]}}


def collect_supplemental_snapshot(**kwargs):
    """Capture the additional stats only when every page is still at the base source state."""
    return collect_snapshot(
        stats=SUPPLEMENTAL_STATS,
        related_snapshot_id=RELATED_BASE_SNAPSHOT_ID,
        required_source_date=SUPPLEMENTAL_SOURCE_STATE_DATE,
        **kwargs,
    )


if __name__ == "__main__":
    print(json.dumps(collect_snapshot(), ensure_ascii=False, default=str, indent=2))
