"""Inspect one cached J1 season without downloading any data.

Run: python -m scripts.inspect_jleague --year 2015
     python -m scripts.inspect_jleague --year 2016
     python -m scripts.inspect_jleague --year 2017
     python -m scripts.inspect_jleague --year 2021
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
COMPARISON_SEASONS = {
    2016: 2015, 2017: 2016, 2018: 2017, 2019: 2018, 2020: 2019, 2021: 2017,
}


def compare_years(
    before: pd.DataFrame, after: pd.DataFrame, *, before_season: int = 2015, after_season: int = 2016,
) -> dict:
    """Compare observed source spellings without mapping names or venues."""
    old = summarize_matches(before, expected_season=before_season)
    new = summarize_matches(after, expected_season=after_season)
    old_clubs, new_clubs = set(old["clubs"]), set(new["clubs"])
    old_venues, new_venues = set(old["stadiums"]), set(new["stadiums"])
    venue_changes = {}
    for club in sorted(old_clubs & new_clubs):
        old_home = sorted(before.loc[before.home_team == club, "stadium"].unique().tolist())
        new_home = sorted(after.loc[after.home_team == club, "stadium"].unique().tolist())
        if old_home != new_home:
            venue_changes[club] = {str(before_season): old_home, str(after_season): new_home}
    return {
        str(before_season): {key: old[key] for key in ("matches", "date_min", "date_max", "result_counts")},
        str(after_season): {key: new[key] for key in ("matches", "date_min", "date_max", "result_counts")},
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


def render_review(summary: dict, comparison: dict, *, before_season: int = 2015) -> str:
    """Render complete review data, including deterministic sample records."""
    year = summary["season"]
    stage_names = list(summary["stages"])
    matches_per_round = summary["club_count"] // 2
    round_note = (
        f"roundはステージ内の節番号。年間合計{matches_per_round * len(stage_names)}試合は"
        + "と".join(f"{stage}の{matches_per_round}試合" for stage in stage_names) + "の合計。\n"
        if len(stage_names) == 2 else
        f"roundは通年の1～{max(summary['round_counts'])}節。"
        "full_seasonはステージ分割のない年間リーグ戦を表す。\n"
    )
    parts = [
        f"# {year}年J1: 人間レビュー用サマリー\n",
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
        round_note,
        _table([{"round": number,
                 **{stage: summary["stages"][stage]["round_counts"][number] for stage in stage_names},
                 "total": count}
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
        f"## {before_season}年との差分\n",
        f"{year}年に追加: " + "、".join(comparison["clubs_added"]) + "。\n",
        f"{year}年に存在しないクラブ: " + "、".join(comparison["clubs_removed"]) + "。\n",
        "追加の会場表記: " + "、".join(comparison["stadiums_added"]) + "。\n",
        f"{year}年に存在しない会場表記: " + "、".join(comparison["stadiums_removed"]) + "。\n",
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
    # Compare explicitly verified caches, including nonconsecutive seasons.
    if year in COMPARISON_SEASONS:
        before_year = COMPARISON_SEASONS[year]
        before, before_metadata = read_cached_matches(before_year, raw_dir=raw_dir)
        summary = build_review_summary(matches, expected_season=year)
        comparison = compare_years(before, matches, before_season=before_year, after_season=year)
        if comparison["shared_match_ids"]:
            raise ValueError(f"{before_year} and {year} contain shared match IDs.")
        old_csv = output_dir / f"{before_year}_matches_probe.csv"
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
            f"baseline_{before_year}_sha256": before_metadata["sha256"],
            "metadata_sha256_verified": True, "csv_roundtrip_validated": True,
            "network_requests": 0,
        })
    summary_path = output_dir / f"{year}_matches_probe.summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if year in COMPARISON_SEASONS:
        review_path = output_dir / f"{year}_matches_probe.review.md"
        review_path.write_text(render_review(summary, comparison, before_season=before_year), encoding="utf-8")
        stages = summary["stages"]
        stage_info = (
            f"{next(iter(stages.values()))['matches']} per stage" if len(stages) == 2 else
            f"{len(summary['round_counts'])} rounds in one full season"
        )
        print(f"{year} offline comparison: {summary['matches']} matches, {summary['club_count']} clubs, "
              f"{stage_info}; validation/CSV roundtrip passed.")
        print(f"CSV: {csv_path}\nSummary: {summary_path}\nHuman review: {review_path}")
    else:
        stage_matches = next(iter(summary["stages"].values()))["matches"]
        print(f"2015 offline probe: {len(matches)} matches; {stage_matches} per stage; CSV roundtrip passed.")
        print(f"CSV: {csv_path}\nSummary: {summary_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--year", type=int, choices=SUPPORTED_SEASONS, required=True)
    args = parser.parse_args()
    run_inspection(args.year)


if __name__ == "__main__":
    main()
