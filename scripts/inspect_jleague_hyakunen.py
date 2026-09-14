"""Normalize the cached 2026 J1 special competition, without network access.

Run: python -m scripts.inspect_jleague_hyakunen
"""

import argparse
import json
from pathlib import Path
import tempfile

import pandas as pd

from scripts.inspect_jleague import _table
from src.collect.jleague_hyakunen import (
    build_playoff_ties, normalize_matches, validate_competition,
)
from src.collect.jleague_hyakunen_source import read_cached_sources


ROOT = Path(__file__).resolve().parents[1]


def _records(frame: pd.DataFrame) -> list[dict]:
    """Use JSON scalars and explicit nulls, including nullable integer columns."""
    display = frame.copy()
    for column in display:
        if pd.api.types.is_datetime64_any_dtype(display[column]):
            display[column] = display[column].dt.strftime("%Y-%m-%d")
    return json.loads(display.to_json(orient="records", force_ascii=False))


def _counts(series: pd.Series) -> dict:
    return {str(key): int(value) for key, value in series.value_counts().sort_index().items()}


def build_summary(matches: pd.DataFrame, ties: pd.DataFrame, metadata: dict) -> dict:
    """Validate structure and expose both match and two-leg outcomes for review."""
    coverage = validate_competition(matches)
    pd.testing.assert_frame_equal(ties, build_playoff_ties(matches))
    clubs = sorted(set(matches.home_team) | set(matches.away_team))
    club_counts = {}
    for club in clubs:
        home = matches.home_team.eq(club)
        away = matches.away_team.eq(club)
        regional = matches.stage.eq("regional")
        club_counts[club] = {
            "group": matches.loc[home, "home_group"].iloc[0],
            "total": int((home | away).sum()), "home": int(home.sum()), "away": int(away.sum()),
            "regional": int(((home | away) & regional).sum()),
            "playoff": int(((home | away) & ~regional).sum()),
        }
    stages = {}
    for label, subset in (
        ("EAST", matches[matches.group.eq("EAST")]),
        ("WEST", matches[matches.group.eq("WEST")]),
        ("playoff", matches[matches.stage.eq("playoff")]),
    ):
        stages[label] = {
            "matches": len(subset),
            "round_counts": _counts(subset["leg" if label == "playoff" else "round"]),
            "date_min": subset.match_date.min().date().isoformat(),
            "date_max": subset.match_date.max().date().isoformat(),
            "result_90_counts": _counts(subset.result),
            "extra_time_matches": int(subset.extra_time_played.sum()),
            "pk_matches": int(subset.pk_played.sum()),
        }
    # Nullable fields have stage-dependent meanings; count them without calling them defects.
    required = [
        "match_id", "season", "competition_key", "source_year_id", "source_frame_id",
        "source_season_label", "match_date", "home_team", "away_team", "stadium",
        "home_score", "away_score", "result", "stage", "competition", "round_label",
        "kickoff_time", "source_url", "raw_score_text", "home_group", "away_group",
        "extra_time_played", "pk_played", "match_decision",
    ]
    expected = 2 * matches.home_score.gt(matches.away_score).astype(int)
    expected += matches.home_score.eq(matches.away_score).astype(int)
    quality = {
        "required_missing": {c: int(matches[c].isna().sum()) for c in required},
        "all_column_null_counts": {c: int(matches[c].isna().sum()) for c in matches},
        "duplicate_match_ids": int(matches.match_id.duplicated().sum()),
        "duplicate_matches": int(matches.duplicated(["match_date", "home_team", "away_team"]).sum()),
        "duplicate_rows": int(matches.duplicated().sum()),
        "same_team_rows": int(matches.home_team.eq(matches.away_team).sum()),
        "score_result_mismatches": int(matches.result.ne(expected).sum()),
        "negative_score_rows": int((matches.home_score.lt(0) | matches.away_score.lt(0)).sum()),
        "competition_validation_passed": True,
    }
    summary = {
        "competition_key": "j1_hyakunen_2026", "season": 2026,
        "matches": len(matches), "columns": matches.columns.tolist(),
        "club_count": len(clubs), "clubs": clubs, "club_match_counts": club_counts,
        "stages": stages, "date_min": matches.match_date.min().date().isoformat(),
        "date_max": matches.match_date.max().date().isoformat(),
        "match_id_count": int(matches.match_id.nunique()),
        "stadiums": sorted(matches.stadium.unique().tolist()),
        "result_90_counts": _counts(matches.result),
        "match_outcome_counts": {
            "away": int(matches.match_winner_team.eq(matches.away_team).fillna(False).sum()),
            "draw": int(matches.match_winner_team.isna().sum()),
            "home": int(matches.match_winner_team.eq(matches.home_team).fillna(False).sum()),
        },
        "match_decision_counts": _counts(matches.match_decision),
        "extra_time_matches": int(matches.extra_time_played.sum()),
        "pk_matches": int(matches.pk_played.sum()),
        "goals_90": int(matches.home_score.sum() + matches.away_score.sum()),
        "extra_time_goals": int(matches.home_extra_time_score.sum() + matches.away_extra_time_score.sum()),
        "playoff_tie_count": len(ties), "tie_decision_counts": _counts(ties.tie_decision),
        "playoff_ties": _records(ties), "quality": quality, "coverage": coverage,
        "random_state": 42, "source_row_order_preserved": True,
        "first_five": _records(matches.head(5)), "last_five": _records(matches.tail(5)),
        "random_ten": _records(matches.sample(n=10, random_state=42)),
        "extra_time_games": _records(matches[matches.extra_time_played]),
        "pk_games": _records(matches[matches.pk_played]),
        "acquisition": metadata, "metadata_sha256_verified": True, "network_requests": 0,
        "validation_contract": "hyakunen competition; legacy matches.csv validator unchanged",
    }
    return summary


def render_review(summary: dict) -> str:
    """Generate a compact score-focused review, with complete column/null inventories."""
    parts = [
        "# 2026年J1百年構想リーグ: 人間レビュー用サマリー\n",
        "保存済み原本からオフライン生成。home_score / away_score / resultは90分結果。"
        "延長得点は増分、PK得点は別列。名称は原表記のまま。\n",
        "## 大会全体\n",
        _table([{"項目": key, "値": summary[key]} for key in (
            "matches", "club_count", "match_id_count", "date_min", "date_max",
            "extra_time_matches", "pk_matches", "playoff_tie_count", "goals_90", "extra_time_goals",
        )]),
        "## ステージ別\n",
        _table([{"stage": stage, **{k: v for k, v in values.items() if k != "round_counts"}}
                for stage, values in summary["stages"].items()]),
        "## 各クラブの試合数\n",
        _table([{"club": club, **counts} for club, counts in summary["club_match_counts"].items()]),
        "## 節・戦の件数\n",
        "地域のroundとプレーオフのlegを分けて集計する。\n",
        _table([{"stage": stage, "round_or_leg": number, "matches": count}
                for stage, values in summary["stages"].items()
                for number, count in values["round_counts"].items()]),
        "## 90分結果と決着方法\n",
        _table([{"kind": kind, "value": value, "count": count}
                for kind in ("result_90_counts", "match_outcome_counts", "match_decision_counts", "tie_decision_counts")
                for value, count in summary[kind].items()]),
        "resultは0=Away、1=Draw、2=Home。POのPKは2試合全体の決着なので、"
        "単一試合のスコアから決まる勝者をPK勝者へ上書きしない。\n",
        "## プレーオフ2試合全体の結果\n", _table(summary["playoff_ties"]),
        "tieの勝者は第2戦後の情報。第1戦の試合前情報には使用しない。\n",
        "## 列一覧とnull\n",
        "roundはPOで、leg・順位決定枠は地域でnull。延長／PK未実施の得点と引分の勝者もnull。"
        "これら適用外の値と必要情報の欠落は区別して検証済み。\n",
        _table([{"column": c, "null_count": summary["quality"]["all_column_null_counts"][c],
                 "required_nulls": summary["quality"]["required_missing"].get(c, "段階別に検証")}
                for c in summary["columns"]]),
        "## 重複・整合性\n",
        _table([{"check": key, "value": value} for key, value in summary["quality"].items()
                if key not in ("required_missing", "all_column_null_counts")]),
        "## スタジアム\n", f"{len(summary['stadiums'])}表記: " + "、".join(summary["stadiums"]) + "\n",
    ]
    selected = [
        "match_id", "match_date", "stage", "group", "round", "leg", "home_team", "away_team",
        "home_score", "away_score", "result", "extra_time_played", "home_extra_time_score",
        "away_extra_time_score", "home_pk_score", "away_pk_score", "match_winner_team",
        "match_decision", "stadium",
    ]
    for title, key in (
        ("延長実施試合", "extra_time_games"), ("PK実施試合", "pk_games"),
        ("先頭5試合（原本順）", "first_five"), ("最後5試合（原本順）", "last_five"),
        ("ランダム10試合（random_state=42）", "random_ten"),
    ):
        parts.extend([f"## {title}\n", _table([{c: row[c] for c in selected} for row in summary[key]])])
    parts.extend([
        "## 原本の来歴\n",
        "要求URL・取得日時・SHA-256等はsummary.jsonのacquisitionに収録。"
        f"照合済み原本{len(summary['acquisition'])}件、今回の追加通信0回。\n",
    ])
    return "\n".join(parts)


def _read_csv_like(path: Path, template: pd.DataFrame) -> pd.DataFrame:
    """Round-trip explicit dtypes; never infer IDs or interpret text such as NA as null."""
    frame = pd.read_csv(path, dtype="string", keep_default_na=False)
    if frame.columns.tolist() != template.columns.tolist():
        raise ValueError("CSV columns differ from the normalized schema.")
    frame = frame.replace("", pd.NA)
    for column, dtype in template.dtypes.items():
        if pd.api.types.is_bool_dtype(dtype):
            if not frame[column].dropna().isin(["True", "False"]).all():
                raise ValueError(f"Invalid CSV boolean in {column}.")
            frame[column] = frame[column].map({"True": True, "False": False}).astype(dtype)
        else:
            frame[column] = frame[column].astype(dtype)
    return frame


def run_inspection(*, root: Path = ROOT, output_dir: Path | None = None) -> dict:
    """Validate all cached inputs before staging the four deterministic artifacts."""
    root = Path(root)
    raw_dir = root / "data/raw/jleague/2026_hyakunen"
    output_dir = Path(output_dir) if output_dir is not None else root / "data/processed/jleague/2026_hyakunen"
    if output_dir.resolve().is_relative_to((root / "data/raw").resolve()):
        raise ValueError("Outputs must not be written into raw data.")
    records, details, metadata = read_cached_sources(raw_dir=raw_dir)
    matches = normalize_matches(records, details)
    validate_competition(matches)
    ties = build_playoff_ties(matches)
    summary = build_summary(matches, ties, metadata)
    output_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".hyakunen-", dir=output_dir) as temporary:
        stage = Path(temporary)
        for filename, frame in (("matches.csv", matches), ("playoff_ties.csv", ties)):
            path = stage / filename
            frame.to_csv(path, index=False, encoding="utf-8", date_format="%Y-%m-%d")
            reloaded = _read_csv_like(path, frame)
            pd.testing.assert_frame_equal(frame, reloaded)
            if filename == "matches.csv":
                validate_competition(reloaded)
        summary["csv_roundtrip_validated"] = True
        (stage / "summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8",
        )
        (stage / "review.md").write_text(render_review(summary), encoding="utf-8")
        for filename in ("matches.csv", "playoff_ties.csv", "summary.json", "review.md"):
            (stage / filename).replace(output_dir / filename)
    print(f"2026 J1 special competition: {len(matches)} matches, {len(ties)} playoff ties; "
          f"PK {summary['pk_matches']}, extra time {summary['extra_time_matches']}; "
          "competition validation and CSV roundtrip passed. Network requests: 0.")
    print(f"Artifacts: {output_dir}")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, help="Override the processed artifact directory.")
    args = parser.parse_args()
    run_inspection(output_dir=args.output_dir)


if __name__ == "__main__":
    main()
