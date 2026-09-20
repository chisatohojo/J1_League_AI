import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

from src.collect.jleague_j2_matches import (
    EXPECTED_COUNTS,
    OUTPUT_COLUMNS,
    _fetch_listing,
    parse_j2_sfms01_html,
)


HTML = '''<table class="unrelated"><tr><td>2020</td><td>bad</td></tr></table>
<table class="table-base00 search-table"><tr>
<td>2020 Ｊ２</td><td>第1節第1日</td><td>20/02/23</td><td>14:00</td>
<td>千葉</td><td><a href="/SFMS02/?match_card_id=12345">1-0</a></td>
<td>琉球</td><td>フクアリ</td><td>10</td><td>other</td>
</tr></table>'''


def test_parse_search_table_only_and_same_row_match_id():
    frame = parse_j2_sfms01_html(HTML, expected_season=2020)
    assert list(frame.match_id) == ["12345"]
    assert frame.loc[0, "home_team"] == "千葉"
    assert frame.loc[0, "away_team"] == "琉球"
    assert frame.loc[0, "home_score"] == 1
    assert frame.loc[0, "away_score"] == 0
    assert frame.loc[0, "result"] == 2
    assert frame.loc[0, "stage"] == "full_season"


def test_result_mapping_and_duplicate_rejection():
    for score, result in (("0-1", 0), ("0-0", 1), ("1-0", 2)):
        html = HTML.replace("1-0", score)
        assert parse_j2_sfms01_html(html, expected_season=2020).loc[0, "result"] == result
    duplicate = HTML + HTML
    with pytest.raises(ValueError, match="duplicate"):
        parse_j2_sfms01_html(duplicate, expected_season=2020)


def test_expected_season_counts_and_schema_are_fixed():
    assert EXPECTED_COUNTS == {**{year: 462 for year in range(2015, 2024)}, 2024: 380}
    assert "match_id" in OUTPUT_COLUMNS and "source_url" in OUTPUT_COLUMNS
    with pytest.raises(ValueError):
        parse_j2_sfms01_html(HTML, expected_season=2021)


def test_cache_metadata_sha256_is_validated(tmp_path):
    url = "https://data.j-league.or.jp/SFMS01/search?competition_frame_ids=2&competition_years=2020&lang=ja"
    body = b"cached"
    (tmp_path / "2020.html").write_bytes(body)
    (tmp_path / "2020.metadata.json").write_text(json.dumps({
        "requested_url": url, "final_url": url, "status": 200, "season": 2020,
        "bytes": len(body), "sha256": hashlib.sha256(body).hexdigest(),
    }), encoding="utf-8")
    result, hit = _fetch_listing(url, tmp_path)
    assert hit and result == body
