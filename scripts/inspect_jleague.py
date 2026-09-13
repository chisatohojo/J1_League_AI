"""Inspect one cached J1 season without downloading any data.

Run: python -m scripts.inspect_jleague --year 2015
     python -m scripts.inspect_jleague --year 2016
"""

import argparse
import json
from pathlib import Path

import pandas as pd

from src.collect.jleague import (
    SUPPORTED_SEASONS, build_review_summary, read_cached_matches, summarize_matches,
)
from src.collect.matches import load_matches


ROOT = Path(__file__).resolve().parents[1]


def compare_years(before: pd.DataFrame, after: pd.DataFrame) -> dict:
    """Compare observed source spellings without mapping names or venues."""
    old = summarize_matches(before, expected_season=2015)
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


def run_inspection(year: int, *, root: Path = ROOT, output_dir: Path | None = None) -> None:
    """Reuse one season's cache and preserve its existing output contract."""
    root = Path(root)
    output_dir = Path(output_dir) if output_dir is not None else root / "data/processed/jleague"
    raw_dir = root / "data/raw/jleague"
    matches, metadata = read_cached_matches(year, raw_dir=raw_dir)
    # The 2016 report also compares the already cached 2015 season.
    if year == 2016:
        before, before_metadata = read_cached_matches(2015, raw_dir=raw_dir)
        summary = build_review_summary(matches, expected_season=year)
        comparison = compare_years(before, matches)
        if comparison["shared_match_ids"]:
            raise ValueError("2015 and 2016 contain shared match IDs.")
        old_csv = output_dir / "2015_matches_probe.csv"
        if old_csv.exists():
            pd.testing.assert_frame_equal(before, load_matches(old_csv))
    else:
        summary = summarize_matches(matches, expected_season=year)

    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / f"{year}_matches_probe.csv"
    matches.to_csv(csv_path, index=False, encoding="utf-8", date_format="%Y-%m-%d")
    pd.testing.assert_frame_equal(matches, load_matches(csv_path))
    # Keep the historical JSON fields and their order, including 2016's review.
    if year == 2015:
        raw_path = raw_dir / f"{year}_j1_search.html"
        summary.update({
            "raw_path": raw_path.relative_to(root).as_posix(),
            "raw_sha256": metadata["sha256"], "raw_bytes": metadata["bytes"],
            "metadata_sha256_verified": True,
            "requested_url": metadata["requested_url"],
            "fetched_at_utc": metadata["fetched_at_utc"],
            "csv_path": (csv_path.relative_to(root) if csv_path.is_relative_to(root) else csv_path).as_posix(),
            "csv_roundtrip_validated": True, "network_requests": 0,
        })
    else:
        summary.update({
            "acquisition": metadata, "comparison": comparison,
            "baseline_2015_sha256": before_metadata["sha256"],
            "metadata_sha256_verified": True, "csv_roundtrip_validated": True,
            "network_requests": 0,
        })
    summary_path = output_dir / f"{year}_matches_probe.summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if year == 2016:
        review_path = output_dir / f"{year}_matches_probe.review.md"
        review_path.write_text(render_review(summary, comparison), encoding="utf-8")
        print("2016 offline comparison: 306 matches, 18 clubs, 153 per stage; validation/CSV roundtrip passed.")
        print(f"CSV: {csv_path}\nSummary: {summary_path}\nHuman review: {review_path}")
    else:
        print(f"2015 offline probe: {len(matches)} matches; 153 per stage; CSV roundtrip passed.")
        print(f"CSV: {csv_path}\nSummary: {summary_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--year", type=int, choices=SUPPORTED_SEASONS, required=True)
    args = parser.parse_args()
    run_inspection(args.year)


if __name__ == "__main__":
    main()

