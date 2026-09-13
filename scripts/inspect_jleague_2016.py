"""Compare cached 2015/2016 J1 results and produce an offline 2016 review.

Run: python -m scripts.inspect_jleague_2016
No downloading, other seasons, or changes to the 2015 output files.
"""

import argparse
from collections import Counter
import hashlib
import json

import pandas as pd

from scripts.inspect_jleague_2015 import (
    ROOT, SOURCE_BASE, parse_matches_html, summarize_matches,
)
from src.collect.matches import load_matches, validate_matches


OUTPUT_DIR = ROOT / "data/processed/jleague"


def read_cached_matches(year: int) -> tuple[pd.DataFrame, dict]:
    """Require a complete, verifiable local cache; never fetch on failure."""
    if year not in (2015, 2016):
        raise ValueError("Only 2015 and 2016 caches are supported.")
    raw_path = ROOT / f"data/raw/jleague/{year}_j1_search.html"
    raw = raw_path.read_bytes()
    metadata = json.loads(raw_path.with_suffix(".metadata.json").read_text(encoding="utf-8"))
    expected_url = (
        f"{SOURCE_BASE}/SFMS01/search?competition_frame_ids=1"
        f"&competition_years={year}&tv_relay_station_name="
    )
    if (
        metadata.get("requested_url") != expected_url
        or metadata.get("final_url") != expected_url
        or metadata.get("status") != 200
        or metadata.get("bytes") != len(raw)
        or metadata.get("sha256") != hashlib.sha256(raw).hexdigest()
        or not metadata.get("fetched_at_utc")
    ):
        raise ValueError(f"{year} cache metadata or SHA-256 mismatch; no refetch performed.")
    return parse_matches_html(raw.decode("utf-8-sig"), expected_season=year), metadata


def build_review_summary(matches: pd.DataFrame) -> dict:
    """Verify 2016 coverage and include all requested human-review fields."""
    matches = validate_matches(matches)
    extra_columns = {"stage", "competition", "round_label", "kickoff_time", "source_url"}
    missing_columns = extra_columns - set(matches.columns)
    if missing_columns:
        raise ValueError(f"Missing research columns: {', '.join(sorted(missing_columns))}")
    summary = summarize_matches(matches, expected_season=2016)
    clubs = summary["clubs"]
    counts = {
        club: {
            "total": int(((matches.home_team == club) | (matches.away_team == club)).sum()),
            "home": int((matches.home_team == club).sum()),
            "away": int((matches.away_team == club).sum()),
        }
        for club in clubs
    }
    if any(count != {"total": 34, "home": 17, "away": 17} for count in counts.values()):
        raise ValueError("Expected each club to play 34 matches: 17 home and 17 away.")
    for stage, group in matches.groupby("stage"):
        pairs = Counter(tuple(sorted(pair)) for pair in zip(group.home_team, group.away_team))
        if len(pairs) != 153 or set(pairs.values()) != {1}:
            raise ValueError(f"Stage {stage} must contain all 153 club pairs exactly once.")
    if matches.duplicated(["home_team", "away_team"]).any():
        raise ValueError("Annual home/away matchups must each occur exactly once.")

    blank_counts = {
        column: int(matches[column].astype("string").str.strip().eq("").sum())
        for column in matches
    }
    missing_counts = matches.isna().sum().to_dict()
    if any(blank_counts.values()) or any(missing_counts.values()):
        raise ValueError("Review columns contain missing or blank values.")
    expected_result = (
        (matches.home_score > matches.away_score).astype("int64") * 2
        + (matches.home_score == matches.away_score).astype("int64")
    )
    display = matches.copy()
    display["match_date"] = display["match_date"].dt.strftime("%Y-%m-%d")
    summary.update({
        "columns": matches.columns.tolist(), "club_count": len(clubs),
        "club_match_counts": counts,
        "round_counts": matches["round"].value_counts().sort_index().to_dict(),
        "missing_counts": missing_counts, "blank_counts": blank_counts,
        "duplicate_rows": int(matches.duplicated().sum()),
        "same_team_rows": int((matches.home_team == matches.away_team).sum()),
        "score_result_mismatches": int((matches.result != expected_result).sum()),
        "negative_score_rows": int(((matches.home_score < 0) | (matches.away_score < 0)).sum()),
        "total_goals": int(matches.home_score.sum() + matches.away_score.sum()),
        "random_state": 42,
        "first_five": display.head(5).to_dict("records"),
        "last_five": display.tail(5).to_dict("records"),
        "random_ten": display.sample(n=10, random_state=42).to_dict("records"),
    })
    return summary


def compare_years(before: pd.DataFrame, after: pd.DataFrame) -> dict:
    """Compare observed source spellings without mapping names or venues."""
    old = summarize_matches(before)
    new = summarize_matches(after, expected_season=2016)
    old_clubs, new_clubs = set(old["clubs"]), set(new["clubs"])
    old_venues, new_venues = set(old["stadiums"]), set(new["stadiums"])
    venue_changes = {}
    for club in sorted(old_clubs & new_clubs):
        old_home = sorted(before.loc[before.home_team == club, "stadium"].unique().tolist())
        new_home = sorted(after.loc[after.home_team == club, "stadium"].unique().tolist())
        if old_home != new_home:
            venue_changes[club] = {"2015": old_home, "2016": new_home}
    return {
        "2015": {key: old[key] for key in ("matches", "date_min", "date_max", "result_counts")},
        "2016": {key: new[key] for key in ("matches", "date_min", "date_max", "result_counts")},
        "columns_equal": before.columns.equals(after.columns),
        "stage_labels_equal": set(before.competition) == set(after.competition),
        "clubs_added": sorted(new_clubs - old_clubs),
        "clubs_removed": sorted(old_clubs - new_clubs),
        "common_clubs": sorted(old_clubs & new_clubs),
        "stadiums_added": sorted(new_venues - old_venues),
        "stadiums_removed": sorted(old_venues - new_venues),
        "common_club_home_venue_changes": venue_changes,
        "shared_match_ids": sorted(set(before.match_id) & set(after.match_id)),
        "names_preserved": True,
    }


def _table(records: list[dict]) -> str:
    """Render Markdown without adding a formatting dependency."""
    if not records:
        return "該当なし。\n"
    columns = list(records[0])
    def cell(value):
        return str(value).replace("|", "\\|").replace("\n", " ").replace("\r", " ")
    lines = ["| " + " | ".join(map(cell, columns)) + " |", "| " + " | ".join("---" for _ in columns) + " |"]
    lines.extend("| " + " | ".join(cell(row[column]) for column in columns) + " |" for row in records)
    return "\n".join(lines) + "\n"


def render_review(summary: dict, comparison: dict) -> str:
    """Render complete review data, including deterministic sample records."""
    parts = [
        "# 2016年J1: 人間レビュー用サマリー\n",
        "保存済みHTMLから生成。ネットワークアクセスなし。名称は取得表記のまま。\n",
        "## 概要\n",
        _table([{"項目": key, "値": value} for key, value in {
            "総行数": summary["matches"], "列数": len(summary["columns"]),
            "クラブ数": summary["club_count"], "match_idユニーク数": summary["match_id_count"],
            "最古開催日": summary["date_min"], "最新開催日": summary["date_max"],
            "総得点": summary["total_goals"], "random_state": summary["random_state"],
        }.items()]),
        "## 列名\n", ", ".join(f"`{column}`" for column in summary["columns"]) + "\n",
        "## クラブ一覧・年間試合数\n",
        _table([{"club": club, **counts} for club, counts in summary["club_match_counts"].items()]),
        "## 各roundの試合数\n",
        "roundはステージ内の節番号。年間合計18試合は1stの9試合と2ndの9試合の合計。\n",
        _table([{"round": number, "1st": summary["stages"]["1st"]["round_counts"][number],
                 "2nd": summary["stages"]["2nd"]["round_counts"][number], "total": count}
                for number, count in summary["round_counts"].items()]),
        "## 欠損・空白\n",
        _table([{"column": column, "missing": summary["missing_counts"][column],
                 "blank": summary["blank_counts"][column]} for column in summary["columns"]]),
        "## 重複・整合性\n",
        _table([{"check": key, "rows": summary[key]} for key in (
            "duplicate_match_ids", "duplicate_matches", "duplicate_rows", "same_team_rows",
            "score_result_mismatches", "negative_score_rows", "adjacent_date_decreases",
        )]),
        "## result別件数\n",
        _table([{"result": result, "label": {0: "Away Win", 1: "Draw", 2: "Home Win"}[result],
                 "matches": count} for result, count in summary["result_counts"].items()]),
        "## スタジアム一覧\n", f"{len(summary['stadiums'])}表記。\n",
        "、".join(summary["stadiums"]) + "\n",
        "## 2015年との差分\n",
        "2016年に追加: " + "、".join(comparison["clubs_added"]) + "。\n",
        "2016年に存在しないクラブ: " + "、".join(comparison["clubs_removed"]) + "。\n",
        "追加の会場表記: " + "、".join(comparison["stadiums_added"]) + "。\n",
        "2016年に存在しない会場表記: " + "、".join(comparison["stadiums_removed"]) + "。\n",
    ]
    for title, key in (("先頭5試合（原本順）", "first_five"), ("最後5試合（原本順）", "last_five"),
                       ("ランダム10試合（random_state=42、原本順から抽出）", "random_ten")):
        parts.extend([f"## {title}\n", _table(summary[key])])
    if "acquisition" in summary:
        parts.extend(["## 原本の来歴\n", "```json\n" + json.dumps(summary["acquisition"], ensure_ascii=False, indent=2) + "\n```\n"])
    return "\n".join(parts)


def main() -> None:
    argparse.ArgumentParser(description=__doc__).parse_args()
    before, before_metadata = read_cached_matches(2015)
    matches, metadata = read_cached_matches(2016)
    summary = build_review_summary(matches)
    comparison = compare_years(before, matches)
    if comparison["shared_match_ids"]:
        raise ValueError("2015 and 2016 contain shared match IDs.")
    old_csv = OUTPUT_DIR / "2015_matches_probe.csv"
    if old_csv.exists():
        pd.testing.assert_frame_equal(before, load_matches(old_csv))
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = OUTPUT_DIR / "2016_matches_probe.csv"
    matches.to_csv(csv_path, index=False, encoding="utf-8", date_format="%Y-%m-%d")
    pd.testing.assert_frame_equal(matches, load_matches(csv_path))
    summary.update({
        "acquisition": metadata, "comparison": comparison,
        "baseline_2015_sha256": before_metadata["sha256"],
        "metadata_sha256_verified": True, "csv_roundtrip_validated": True,
        "network_requests": 0,
    })
    summary_path = OUTPUT_DIR / "2016_matches_probe.summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    review_path = OUTPUT_DIR / "2016_matches_probe.review.md"
    review_path.write_text(render_review(summary, comparison), encoding="utf-8")
    print("2016 offline comparison: 306 matches, 18 clubs, 153 per stage; validation/CSV roundtrip passed.")
    print(f"CSV: {csv_path}\nSummary: {summary_path}\nHuman review: {review_path}")


if __name__ == "__main__":
    main()
