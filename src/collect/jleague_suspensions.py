"""Capture prospective J.LEAGUE suspension notices as immutable snapshots.

This collector is intentionally prospective-only.  It accepts explicitly
observed official notice URLs; it does not discover or backfill archives, infer
unlisted target matches, normalize identities, or create modeling features.
"""

import argparse
import csv
from datetime import date, datetime, timezone
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import time
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from src.collect.teams import TeamMaster, TeamMasterError, load_team_master


ROOT = Path(__file__).resolve().parents[2]
SCHEDULE = ROOT / "data/processed/jleague/2026_27/schedule.csv"
RAW_ROOT = ROOT / "data/raw/jleague_suspensions"
PROCESSED_ROOT = ROOT / "data/processed/jleague_suspensions"
TEAM_SOURCE = "jleague_data_site"
SEASON = "2026/27"
NOTICE_HEADER = ("選手", "チーム", "前回の停止", "今回の停止", "出場停止試合")
NOTICE_URL_RE = re.compile(r"https://www\.jleague\.jp/news/article/([0-9]+)/")
J1_TARGET_RE = re.compile(
    r"^２０２６／２７明治安田Ｊ１リーグ"
    r"(?P<round>第[０-９0-9]+節第[０-９0-9]+日)"
    r"\((?P<month>[0-9]{2})/(?P<day>[0-9]{2})\)$"
)
CSV_FIELDS = (
    "snapshot_id", "retrieved_at", "published_at", "updated_at", "notice_id",
    "competition", "season", "team_id", "team_link_status",
    "official_club_name", "player_name_raw", "official_player_id",
    "target_match_id", "target_match_date", "target_round", "opponent_name",
    "suspension_code", "suspension_reason", "suspension_match_index",
    "suspension_match_count", "match_link_status", "player_link_status",
    "source_url",
)


class SuspensionSnapshotError(ValueError):
    """The source or snapshot violates a prospective collection invariant."""


class _NoticePage(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tables = []
        self.json_ld = []
        self._table = None
        self._row = None
        self._cell = None
        self._script = None
        self._script_type = None

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == "table" and self._table is None:
            self._table = []
        elif tag == "tr" and self._table is not None:
            self._row = []
        elif tag in ("th", "td") and self._row is not None:
            self._cell = []
        elif tag == "script":
            self._script = []
            self._script_type = attributes.get("type")

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)
        if self._script is not None:
            self._script.append(data)

    def handle_endtag(self, tag):
        if tag in ("th", "td") and self._cell is not None:
            # Strip HTML indentation only.  Internal spaces remain source-exact.
            self._row.append("".join(self._cell).strip())
            self._cell = None
        elif tag == "tr" and self._row is not None:
            if self._row:
                self._table.append(self._row)
            self._row = None
        elif tag == "table" and self._table is not None:
            self.tables.append(self._table)
            self._table = None
        elif tag == "script" and self._script is not None:
            if self._script_type == "application/ld+json":
                self.json_ld.append("".join(self._script))
            self._script = None
            self._script_type = None


def _utc_timestamp(value, *, field):
    if not isinstance(value, str) or not value:
        return ""
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise SuspensionSnapshotError(f"Invalid {field}: {value!r}.") from exc
    if parsed.tzinfo is None:
        raise SuspensionSnapshotError(f"Timezone missing from {field}.")
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _notice_id(url):
    if not isinstance(url, str) or urlsplit(url).query or urlsplit(url).fragment:
        raise SuspensionSnapshotError(f"Not an observed canonical notice URL: {url!r}.")
    match = NOTICE_URL_RE.fullmatch(url)
    if not match:
        raise SuspensionSnapshotError(f"Not an observed J.LEAGUE notice route: {url!r}.")
    return match.group(1)


def _article_metadata(page):
    articles = []
    for raw in page.json_ld:
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise SuspensionSnapshotError("Malformed JSON-LD metadata.") from exc
        values = value if isinstance(value, list) else [value]
        articles.extend(item for item in values if isinstance(item, dict)
                        and item.get("@type") == "NewsArticle")
    if len(articles) != 1:
        raise SuspensionSnapshotError(f"Expected one NewsArticle metadata record; got {len(articles)}.")
    article = articles[0]
    if not str(article.get("headline", "")).startswith("出場停止選手のお知らせ"):
        raise SuspensionSnapshotError("Page is not an official suspension notice.")
    published = _utc_timestamp(article.get("datePublished"), field="datePublished")
    if not published:
        raise SuspensionSnapshotError("Official notice lacks publication timestamp.")
    updated = _utc_timestamp(article.get("dateModified"), field="dateModified")
    return published, updated


def _target(target_raw):
    # Whitespace in the match description is presentation, not an identity.
    compact = re.sub(r"\s+", "", target_raw)
    match = J1_TARGET_RE.fullmatch(compact)
    if not match:
        return None
    month, day = int(match.group("month")), int(match.group("day"))
    year = 2026 if month >= 7 else 2027
    try:
        target_date = date(year, month, day).isoformat()
    except ValueError as exc:
        raise SuspensionSnapshotError(f"Invalid explicit target date: {target_raw!r}.") from exc
    return target_date, match.group("round")


def parse_notice(raw: bytes, *, source_url: str):
    """Parse explicit 2026/27 J1 target rows from one observed notice page."""
    notice_id = _notice_id(source_url)
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise SuspensionSnapshotError("Official notice is not lossless UTF-8.") from exc
    page = _NoticePage()
    page.feed(text)
    published_at, updated_at = _article_metadata(page)
    matching = [table for table in page.tables if table and tuple(table[0]) == NOTICE_HEADER]
    if len(matching) != 1:
        raise SuspensionSnapshotError(f"Expected one player suspension table; got {len(matching)}.")

    groups = []
    current = None
    all_target_count = 0
    for cells in matching[0][1:]:
        if len(cells) != len(NOTICE_HEADER):
            raise SuspensionSnapshotError(f"Unexpected suspension row width: {len(cells)}.")
        player, club, previous_code, code, target_raw = cells
        if player:
            if not club or not code:
                raise SuspensionSnapshotError("A player row lacks club or suspension code.")
            current = {"player_name_raw": player, "official_club_name": club,
                       "previous_suspension_code": previous_code,
                       "suspension_code": code, "targets": []}
            groups.append(current)
        elif current is None or any((club, previous_code, code)):
            raise SuspensionSnapshotError("Ambiguous multi-match continuation row.")
        if not target_raw or current is None:
            raise SuspensionSnapshotError("Suspension row lacks an explicit target match.")
        current["targets"].append(target_raw)
        all_target_count += 1

    rows = []
    for group in groups:
        explicit_targets = group["targets"]
        for target_index, target_raw in enumerate(explicit_targets, 1):
            parsed_target = _target(target_raw)
            if parsed_target is None:
                continue
            target_date, target_round = parsed_target
            rows.append({
                "notice_id": notice_id,
                "published_at": published_at,
                "updated_at": updated_at,
                "competition": "j1",
                "season": SEASON,
                "official_club_name": group["official_club_name"],
                "player_name_raw": group["player_name_raw"],
                "official_player_id": "",
                "target_match_date": target_date,
                "target_round": target_round,
                "suspension_code": group["suspension_code"],
                "suspension_reason": "",
                "suspension_match_index": target_index,
                "suspension_match_count": len(explicit_targets),
                "source_url": source_url,
                "target_text_raw": target_raw,
            })
    return rows, {
        "notice_id": notice_id,
        "published_at": published_at,
        "updated_at": updated_at,
        "explicit_target_rows": all_target_count,
        "j1_target_rows": len(rows),
        "ignored_non_j1_target_rows": all_target_count - len(rows),
    }


def _schedule_rows(schedule_path, master):
    required = {
        "match_id", "match_date", "round_label", "home_team", "away_team",
        "competition_key",
    }
    rows = []
    with Path(schedule_path).open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not required <= set(reader.fieldnames or ()):
            raise SuspensionSnapshotError(f"Schedule lacks columns: {sorted(required - set(reader.fieldnames or ()))}.")
        for source in reader:
            if source["competition_key"] != "j1_2026_2027":
                continue
            try:
                home_id = master.resolve_team_id(source["home_team"], source=TEAM_SOURCE,
                                                 on=source["match_date"])
                away_id = master.resolve_team_id(source["away_team"], source=TEAM_SOURCE,
                                                 on=source["match_date"])
            except TeamMasterError as exc:
                raise SuspensionSnapshotError(f"Schedule identity is unresolved: {exc}") from exc
            rows.append({**source, "home_team_id": home_id, "away_team_id": away_id})
    if not rows:
        raise SuspensionSnapshotError("No 2026/27 ordinary J1 schedule rows.")
    nonblank_ids = [row["match_id"] for row in rows if row["match_id"]]
    if len(nonblank_ids) != len(set(nonblank_ids)):
        raise SuspensionSnapshotError("Schedule has duplicate nonblank match IDs.")
    return rows


def link_rows(rows, *, schedule_path=SCHEDULE, master=None, player_identity_keys=None):
    """Apply exact club and match linkage; unresolved records remain explicit."""
    master = master or load_team_master()
    schedule = _schedule_rows(schedule_path, master)
    player_identity_keys = set(player_identity_keys or ())
    linked = []
    for source in rows:
        row = dict(source)
        team_id = ""
        try:
            team_id = master.resolve_team_id(
                row["official_club_name"], source=TEAM_SOURCE,
                on=row["target_match_date"],
            )
            team_status = "EXACT"
        except TeamMasterError:
            team_status = "UNRESOLVED"
        candidates = []
        if team_id:
            candidates = [match for match in schedule
                          if match["match_date"] == row["target_match_date"]
                          and team_id in (match["home_team_id"], match["away_team_id"])]
        target_match_id = ""
        opponent = ""
        if len(candidates) == 1:
            candidate = candidates[0]
            if team_id == candidate["home_team_id"]:
                opponent = candidate["away_team"]
            else:
                opponent = candidate["home_team"]
            if candidate["round_label"] != row["target_round"]:
                match_status = "UNRESOLVED_ROUND_MISMATCH"
            elif not candidate["match_id"]:
                match_status = "UNRESOLVED_NO_MATCH_ID"
            else:
                target_match_id = candidate["match_id"]
                match_status = "EXACT"
        elif not candidates:
            match_status = "UNRESOLVED"
        else:
            match_status = "AMBIGUOUS"
        player_key = (row["season"], team_id, row["player_name_raw"])
        player_status = "EXACT" if team_id and player_key in player_identity_keys else "UNRESOLVED"
        row.update({
            "team_id": team_id,
            "team_link_status": team_status,
            "target_match_id": target_match_id,
            "opponent_name": opponent,
            "match_link_status": match_status,
            "player_link_status": player_status,
        })
        linked.append(row)
    return linked


def _fetch(url):
    request = Request(
        url,
        headers={"User-Agent": "J1LeagueAI/1.0 (+prospective point-in-time research; no archive crawl)",
                 "Accept": "text/html"},
    )
    with urlopen(request, timeout=30) as response:
        return response.read(), response.status, response.geturl(), response.headers.get("Content-Type", "")


def collect_snapshot(*, urls, raw_root=RAW_ROOT, processed_root=PROCESSED_ROOT,
                     schedule_path=SCHEDULE, master=None, player_identity_keys=None,
                     now=None, fetch=_fetch, pause=time.sleep):
    """Fetch explicit current notice URLs and publish only a complete snapshot."""
    urls = tuple(urls)
    if not urls or len(urls) != len(set(urls)):
        raise SuspensionSnapshotError("At least one unique explicit notice URL is required.")
    notice_ids = [_notice_id(url) for url in urls]
    if len(notice_ids) != len(set(notice_ids)):
        raise SuspensionSnapshotError("Duplicate notice identity in one snapshot.")
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None or now.utcoffset() != timezone.utc.utcoffset(now):
        raise SuspensionSnapshotError("Retrieval time must be UTC-aware.")
    snapshot_id = now.strftime("%Y%m%dT%H%M%S%fZ")
    retrieved_at = now.isoformat().replace("+00:00", "Z")
    raw_dir = Path(raw_root) / snapshot_id
    output = Path(processed_root) / f"{snapshot_id}.csv"
    if raw_dir.exists() or output.exists():
        raise SuspensionSnapshotError(f"Snapshot already exists: {snapshot_id}.")
    raw_dir.mkdir(parents=True)
    manifest = {
        "snapshot_id": snapshot_id,
        "retrieved_at": retrieved_at,
        "season": SEASON,
        "status": "INCOMPLETE",
        "source_urls": list(urls),
        "pages": [],
        "notice_count": 0,
        "processed_target_rows": 0,
    }
    all_rows = []
    try:
        for index, (url, notice_id) in enumerate(zip(urls, notice_ids)):
            if index:
                pause(0.25)
            body, status, final_url, content_type = fetch(url)
            if not isinstance(body, bytes):
                raise SuspensionSnapshotError("Official response body is not bytes.")
            digest = hashlib.sha256(body).hexdigest()
            page_record = {
                "notice_id": notice_id,
                "requested_url": url,
                "final_url": final_url,
                "http_status": status,
                "content_type": content_type,
                "response_size": len(body),
                "sha256": digest,
                "html": f"notice_{notice_id}.html",
                "parse_result": "PENDING",
            }
            manifest["pages"].append(page_record)
            (raw_dir / page_record["html"]).write_bytes(body)
            if status != 200 or final_url != url or not content_type.lower().startswith("text/html"):
                raise SuspensionSnapshotError("Unexpected HTTP status, redirect, or content type.")
            parsed, diagnostics = parse_notice(body, source_url=url)
            page_record.update(diagnostics)
            page_record["parse_result"] = "OK"
            all_rows.extend(parsed)
        master = master or load_team_master()
        all_rows = link_rows(all_rows, schedule_path=schedule_path, master=master,
                             player_identity_keys=player_identity_keys)
        keys = [(row["source_url"], row["player_name_raw"], row["official_club_name"],
                 row["target_match_date"], row["target_round"]) for row in all_rows]
        if len(keys) != len(set(keys)):
            raise SuspensionSnapshotError("Duplicate source/target record in one snapshot.")
        Path(processed_root).mkdir(parents=True, exist_ok=True)
        with output.open("x", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS, extrasaction="ignore")
            writer.writeheader()
            for row in all_rows:
                writer.writerow({"snapshot_id": snapshot_id, "retrieved_at": retrieved_at, **row})
        manifest.update({
            "status": "COMPLETE",
            "notice_count": len(urls),
            "processed_target_rows": len(all_rows),
            "exact_team_linkage_count": sum(row["team_link_status"] == "EXACT" for row in all_rows),
            "exact_match_linkage_count": sum(row["match_link_status"] == "EXACT" for row in all_rows),
            "unresolved_match_count": sum(row["match_link_status"] != "EXACT" for row in all_rows),
            "exact_player_linkage_count": sum(row["player_link_status"] == "EXACT" for row in all_rows),
        })
    except Exception as exc:
        manifest["error"] = str(exc)
        if output.exists():
            output.unlink()
        raise
    finally:
        (raw_dir / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    return {
        "snapshot_id": snapshot_id,
        "raw_dir": raw_dir,
        "processed_path": output,
        "request_count": len(manifest["pages"]),
        "notice_count": manifest["notice_count"],
        "row_count": manifest["processed_target_rows"],
        "exact_team_linkage_count": manifest["exact_team_linkage_count"],
        "exact_match_linkage_count": manifest["exact_match_linkage_count"],
        "unresolved_match_count": manifest["unresolved_match_count"],
        "exact_player_linkage_count": manifest["exact_player_linkage_count"],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", action="append", required=True,
                        help="Observed canonical J.LEAGUE suspension notice URL; repeatable.")
    arguments = parser.parse_args(argv)
    print(json.dumps(collect_snapshot(urls=arguments.url), ensure_ascii=False,
                     default=str, indent=2))


if __name__ == "__main__":
    main()
