"""Offline 2024 AFC fixture-identity prototype.

The prototype deliberately consumes only a checked-in, hand-reviewed AFC
schedule manifest (the downloaded PDFs are kept under ``data/raw`` and are
ignored by git).  It does not fetch, infer, fuzzy-match, or alter TeamMaster.
Schedule dates are retained as *scheduled* dates and are never represented as
verified played dates without separate AFC evidence.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass, asdict
from datetime import date
import hashlib
import json
from pathlib import Path
import re

from src.collect.teams import TeamMaster, load_team_master


OUTPUT_COLUMNS = (
    "match_key", "identity_type", "source_match_id", "competition",
    "stage_or_matchday", "match_date", "home_team", "away_team",
    "j1_team_id", "j1_side", "source_url", "source_type", "raw_sha256",
    "date_verification_status", "date_evidence_url", "provenance_status",
)
IDENTITY_TYPE = "derived_fixture_key"
OFFICIAL_ARCHIVE = "https://www.the-afc.com/en/more/content/afc_champions_league_202324.html"
SCHEDULE_URLS = {
    "AFC Champions League 2023/24": (
        "https://assets.the-afc.com/2023-24_ACL/Downloads/AFC-Champions-League-2023-24-Round-of-16-Match-Schedule.pdf",
        "D84EF2F4D724FBFE7FCF28BEA2D7182D8CF3D88FA16F27B4B30F3432D347762B",
    ),
    "AFC Champions League Elite 2024/25": (
        "https://assets.the-afc.com/2024-25_ACL_Elite/Draw/Group_Stage/ACL-Elite-League-Stage---Draw-Results-%26-Match-Schedule.pdf",
        "14C57B0FFCE0B921CEBFE732E7825C4265DFE8C50D8F40AB1AC148D68387E413",
    ),
    "AFC Champions League Two 2024/25": (
        "https://assets.the-afc.com/2024-25_ACL_Two/Downloads/AFC-Champions-League-Two-Match-Schedule-(upd-10-Oct-2024).pdf",
        "DF601D4F62ED9C53CDB937568A2ED2BA5238B8EE5D8391F17F654BA7829E5679",
    ),
}

# AFC spelling -> exact, pre-existing TeamMaster alias.  This is an explicit
# source crosswalk, not fuzzy matching and does not modify TeamMaster.
TEAM_CROSSWALK = {
    "Yokohama F. Marinos": "横浜FM",
    "Kawasaki Frontale": "川崎Ｆ",
    "Vissel Kobe": "神戸",
    "Sanfrecce Hiroshima": "広島",
}
J1_TEAMS = frozenset(TEAM_CROSSWALK)


@dataclass(frozen=True)
class Fixture:
    competition: str
    stage_or_matchday: str
    match_date: str
    home_team: str
    away_team: str
    date_verification_status: str = "unresolved_schedule_only"
    date_evidence_url: str = OFFICIAL_ARCHIVE


def _fixture(competition, stage, day, home, away, status="unresolved_schedule_only"):
    return Fixture(competition, stage, day, home, away, status)


# These values are transcribed from the three AFC official schedule PDFs.
# Knockout dates are retained as schedule dates but remain unresolved until a
# corresponding AFC result/archive evidence is linked.
DEFAULT_FIXTURES = (
    _fixture("AFC Champions League 2023/24", "Round of 16 (1st leg)", "2024-02-13", "Shandong Taishan FC", "Kawasaki Frontale"),
    _fixture("AFC Champions League 2023/24", "Round of 16 (2nd leg)", "2024-02-20", "Kawasaki Frontale", "Shandong Taishan FC"),
    _fixture("AFC Champions League 2023/24", "Round of 16 (1st leg)", "2024-02-14", "Bangkok United", "Yokohama F. Marinos"),
    _fixture("AFC Champions League 2023/24", "Round of 16 (2nd leg)", "2024-02-21", "Yokohama F. Marinos", "Bangkok United"),
    _fixture("AFC Champions League 2023/24", "Quarter-final (1st leg)", "2024-03-06", "Shandong Taishan FC", "Yokohama F. Marinos"),
    _fixture("AFC Champions League 2023/24", "Quarter-final (2nd leg)", "2024-03-13", "Yokohama F. Marinos", "Shandong Taishan FC"),
    _fixture("AFC Champions League 2023/24", "Semi-final (1st leg)", "2024-04-17", "Yokohama F. Marinos", "Ulsan Hyundai FC"),
    _fixture("AFC Champions League 2023/24", "Semi-final (2nd leg)", "2024-04-24", "Ulsan Hyundai FC", "Yokohama F. Marinos"),
    _fixture("AFC Champions League 2023/24", "Final (1st leg)", "2024-05-11", "Yokohama F. Marinos", "Al Ain FC"),
    _fixture("AFC Champions League 2023/24", "Final (2nd leg)", "2024-05-25", "Al Ain FC", "Yokohama F. Marinos"),
    _fixture("AFC Champions League Elite 2024/25", "MD1", "2024-09-17", "Gwangju FC", "Yokohama F. Marinos"),
    _fixture("AFC Champions League Elite 2024/25", "MD1", "2024-09-17", "Buriram United", "Vissel Kobe"),
    _fixture("AFC Champions League Elite 2024/25", "MD1", "2024-09-18", "Ulsan HD FC", "Kawasaki Frontale"),
    _fixture("AFC Champions League Elite 2024/25", "MD2", "2024-10-01", "Yokohama F. Marinos", "Ulsan HD FC"),
    _fixture("AFC Champions League Elite 2024/25", "MD2", "2024-10-01", "Kawasaki Frontale", "Gwangju FC"),
    _fixture("AFC Champions League Elite 2024/25", "MD2", "2024-10-02", "Vissel Kobe", "Shandong Taishan FC"),
    _fixture("AFC Champions League Elite 2024/25", "MD3", "2024-10-21", "Johor Darul Ta'zim FC", "Ulsan HD FC"),
    _fixture("AFC Champions League Elite 2024/25", "MD3", "2024-10-22", "Shandong Taishan FC", "Yokohama F. Marinos"),
    _fixture("AFC Champions League Elite 2024/25", "MD3", "2024-10-22", "Shanghai Shenhua FC", "Kawasaki Frontale"),
    _fixture("AFC Champions League Elite 2024/25", "MD3", "2024-10-23", "Ulsan HD FC", "Vissel Kobe"),
    _fixture("AFC Champions League Elite 2024/25", "MD4", "2024-11-05", "Kawasaki Frontale", "Shanghai Port FC"),
    _fixture("AFC Champions League Elite 2024/25", "MD4", "2024-11-05", "Yokohama F. Marinos", "Buriram United"),
    _fixture("AFC Champions League Elite 2024/25", "MD4", "2024-11-05", "Vissel Kobe", "Gwangju FC"),
    _fixture("AFC Champions League Elite 2024/25", "MD5", "2024-11-26", "Central Coast Mariners", "Yokohama F. Marinos"),
    _fixture("AFC Champions League Elite 2024/25", "MD5", "2024-11-26", "FC Pohang Steelers", "Vissel Kobe"),
    _fixture("AFC Champions League Elite 2024/25", "MD5", "2024-11-26", "Kawasaki Frontale", "Shandong Taishan FC"),
    _fixture("AFC Champions League Elite 2024/25", "MD6", "2024-12-03", "Yokohama F. Marinos", "Shanghai Shenhua FC"),
    _fixture("AFC Champions League Elite 2024/25", "MD6", "2024-12-04", "Vissel Kobe", "Shanghai Port FC"),
    _fixture("AFC Champions League Elite 2024/25", "MD6", "2024-12-04", "FC Pohang Steelers", "Kawasaki Frontale"),
    _fixture("AFC Champions League Two 2024/25", "MD1", "2024-09-19", "Sanfrecce Hiroshima", "Kaya FC-Iloilo"),
    _fixture("AFC Champions League Two 2024/25", "MD2", "2024-10-03", "Eastern", "Sanfrecce Hiroshima"),
    _fixture("AFC Champions League Two 2024/25", "MD3", "2024-10-23", "Sanfrecce Hiroshima", "Sydney FC"),
    _fixture("AFC Champions League Two 2024/25", "MD4", "2024-11-07", "Sydney FC", "Sanfrecce Hiroshima"),
    _fixture("AFC Champions League Two 2024/25", "MD5", "2024-11-28", "Kaya FC-Iloilo", "Sanfrecce Hiroshima"),
    _fixture("AFC Champions League Two 2024/25", "MD6", "2024-12-05", "Sanfrecce Hiroshima", "Eastern"),
)


def make_derived_fixture_key(competition, match_date, home_team, away_team, stage_or_matchday):
    def slug(value):
        return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return ":".join(("afc", "derived", slug(competition), match_date, slug(home_team), slug(away_team), slug(stage_or_matchday)))


def _resolve(name: str, day: str, master: TeamMaster) -> str | None:
    if name not in J1_TEAMS:
        return None
    return master.resolve_team_id(TEAM_CROSSWALK[name], source="jleague_data_site", on=day)


def build_fixtures(fixtures=DEFAULT_FIXTURES, *, team_master=None):
    master = team_master or load_team_master()
    rows = []
    for fixture in fixtures:
        if not (fixture.match_date.startswith("2024-") and (fixture.home_team in J1_TEAMS or fixture.away_team in J1_TEAMS)):
            continue
        j1_names = [name for name in (fixture.home_team, fixture.away_team) if name in J1_TEAMS]
        if len(j1_names) != 1:
            raise ValueError(f"Expected exactly one J1 side: {fixture}")
        j1_name = j1_names[0]
        url, sha = SCHEDULE_URLS[fixture.competition]
        rows.append({
            "match_key": make_derived_fixture_key(fixture.competition, fixture.match_date, fixture.home_team, fixture.away_team, fixture.stage_or_matchday),
            "identity_type": IDENTITY_TYPE, "source_match_id": None,
            "competition": fixture.competition, "stage_or_matchday": fixture.stage_or_matchday,
            "match_date": fixture.match_date, "home_team": fixture.home_team, "away_team": fixture.away_team,
            "j1_team_id": _resolve(j1_name, fixture.match_date, master),
            "j1_side": "home" if j1_name == fixture.home_team else "away",
            "source_url": url, "source_type": "official_afc_schedule_pdf", "raw_sha256": sha,
            "date_verification_status": fixture.date_verification_status,
            "date_evidence_url": fixture.date_evidence_url,
            "provenance_status": "complete" if fixture.date_verification_status == "verified_official_result" else "date_unresolved",
        })
    validate_rows(rows)
    return rows


def validate_rows(rows):
    keys = [row["match_key"] for row in rows]
    if len(keys) != len(set(keys)):
        raise ValueError("derived_fixture_key collision")
    for row in rows:
        if row["identity_type"] != IDENTITY_TYPE or row["source_match_id"] is not None:
            raise ValueError("identity contract violated")
        if not row["j1_team_id"]:
            raise ValueError("unresolved TeamMaster identity")
    seen = set()
    for row in rows:
        marker = (row["j1_team_id"], row["match_date"])
        if marker in seen:
            raise ValueError(f"same J1 club/date appears more than once: {marker}")
        seen.add(marker)


def render_audit_markdown(rows, *, output_path: str | Path):
    unresolved = sum(row["date_verification_status"] != "verified_official_result" for row in rows)
    clubs = sorted({row["j1_team_id"] for row in rows})
    decision = "BLOCKED_AFC_DATE_PROVENANCE" if unresolved else "PROCEED_TO_AFC_REST_HISTORY"
    lines = [
        "# AFC 2024 Fixture Prototype Audit", "", "- Scope: AFC official club competitions, calendar year 2024 only.",
        "- Sources: AFC-hosted schedule PDFs and AFC archive/article evidence only.",
        f"- Final decision: `{decision}`", "", "## Coverage", "",
        f"- Fixture rows: {len(rows)}", f"- Resolved J1 clubs: {len(clubs)} ({', '.join(clubs)})",
        f"- Unique derived keys: {len({r['match_key'] for r in rows})}",
        f"- Same-club/same-day collisions: 0 (validated)",
        f"- Unresolved/ambiguous fixtures: {unresolved}",
        "- TeamMaster resolution: exact explicit crosswalk; no fuzzy matching.",
        "- Provenance: raw SHA-256 recorded per AFC PDF; source IDs remain null for derived keys.",
        "- Date policy: schedule dates are not asserted as played dates until AFC result/archive evidence is linked.",
        "", "## Identity audit", "", "All rows use `identity_type=derived_fixture_key`; no AFC stable match ID was invented.",
        "The prototype is offline-replayable from the embedded manifest and cached AFC raw PDFs.",
    ]
    Path(output_path).write_text("\n".join(lines) + "\n", encoding="utf-8")
    return decision


def write_csv(rows, path):
    with Path(path).open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader(); writer.writerows(rows)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("data/processed/afc_2024_fixture_prototype.csv"))
    parser.add_argument("--audit", type=Path, default=Path("docs/AFC_2024_FIXTURE_PROTOTYPE.md"))
    args = parser.parse_args(argv)
    rows = build_fixtures()
    args.output.parent.mkdir(parents=True, exist_ok=True); args.audit.parent.mkdir(parents=True, exist_ok=True)
    write_csv(rows, args.output)
    decision = render_audit_markdown(rows, output_path=args.audit)
    print(json.dumps({"decision": decision, "fixture_count": len(rows), "club_count": len({r['j1_team_id'] for r in rows}), "unresolved": sum(r['provenance_status'] != 'complete' for r in rows)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
