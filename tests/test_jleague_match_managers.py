import hashlib
import json

import pandas as pd
import pytest

from src.collect.jleague_match_managers import (
    load_cached_match_managers,
    parse_match_managers_html,
)


URL = "https://data.j-league.or.jp/SFMS02/?match_card_id=123"
HTML = """
<div class="two-column-table-box-l">
 <h4 class="two-column-table-st-base">監督</h4>
 <table><tr><td class="name">  Home\n Manager </td></tr></table>
</div>
<div class="two-column-table-box-r">
 <h4 class="two-column-table-st-base">監督</h4>
 <table><tr><td class="name">Away Manager</td></tr></table>
</div>
"""


def test_parse_home_away_and_whitespace():
    result = parse_match_managers_html(HTML, expected_match_id="123", source_url=URL)
    assert result.loc[0, "home_manager_name"] == "Home Manager"
    assert result.loc[0, "away_manager_name"] == "Away Manager"
    assert pd.isna(result.loc[0, "home_manager_staff_id"])


def test_source_url_mismatch_rejected():
    with pytest.raises(ValueError, match="mismatch"):
        parse_match_managers_html(HTML, expected_match_id="123",
                                   source_url=URL.replace("123", "124"))


def test_missing_or_duplicate_manager_rejected():
    with pytest.raises(ValueError):
        parse_match_managers_html(HTML.replace('class="name">Away Manager', 'class="other">Away Manager'),
                                   expected_match_id="123")
    duplicate = HTML + '<div class="two-column-table-box-l"><h4 class="two-column-table-st-base">監督</h4><table><tr><td class="name">Second</td></tr></table></div>'
    with pytest.raises(ValueError):
        parse_match_managers_html(duplicate, expected_match_id="123")


def test_cache_metadata_and_sha256_are_verified(tmp_path):
    raw = HTML.encode("utf-8")
    raw_path = tmp_path / "123.html"
    metadata_path = tmp_path / "123.metadata.json"
    raw_path.write_bytes(raw)
    metadata_path.write_text(json.dumps({
        "requested_url": URL, "final_url": URL, "status": 200,
        "match_id": "123", "bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
    }), encoding="utf-8")
    result = load_cached_match_managers("123", raw_dir=tmp_path)
    assert result.loc[0, "away_manager_name"] == "Away Manager"
    metadata_path.write_text(metadata_path.read_text(encoding="utf-8").replace("200", "500"), encoding="utf-8")
    with pytest.raises(ValueError, match="invalid"):
        load_cached_match_managers("123", raw_dir=tmp_path)


def test_missing_cache_is_rejected_without_network(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_cached_match_managers("123", raw_dir=tmp_path)


def test_parser_is_deterministic_and_does_not_mutate_html():
    original = HTML
    first = parse_match_managers_html(HTML, expected_match_id="123")
    second = parse_match_managers_html(HTML, expected_match_id="123")
    assert HTML == original
    pd.testing.assert_frame_equal(first, second)
