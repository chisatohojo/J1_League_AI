"""Synthetic, offline checks for the separate Hyakunen source format."""

import hashlib
from html import escape
import json

import pytest

from src.collect.jleague import HEADERS
from src.collect.jleague_hyakunen_source import (
    SOURCE_URL, parse_detail, parse_listing, read_cached_sources,
)


def listing(*, playoff=False, score="1-1(PK14-13)", match_id="1", changes=None):
    values = [
        "2026特別", "明治安田Ｊ１百年構想 EASTグループ", "第１節第１日",
        "26/02/06(金)", "19:03", "Home ＦＣ", score, "Away ＦＣ", "原表記スタジアム",
        "12,345", "ＤＡＺＮ",
    ]
    if playoff:
        values[1], values[2], values[10] = "明治安田Ｊ１百年構想 プレーオフラウンド", "第２戦第１日", "１‐２位決定戦／ＤＡＺＮ"
    for index, value in (changes or {}).items():
        values[index] = value
    cells = [f"<td>{escape(value)}</td>" for value in values]
    cells[5] = f'<td><a href="http://www.jleague.jp/club/home/profile/">{escape(values[5])}</a></td>'
    cells[7] = f'<td><a href="http://www.jleague.jp/club/away/profile/">{escape(values[7])}</a></td>'
    cells[6] = f'<td><a href="/SFMS02/?match_card_id={match_id}">{escape(values[6])}</a></td>'
    return '<table class="table-base00 search-table"><tr>' + "".join(
        f"<th>{escape(name)}</th>" for name in HEADERS
    ) + "</tr><tr>" + "".join(cells) + "</tr></table>"


def period(label, home, away):
    return f'<dl><dd class="left-area">{home}</dd><dt>{label}</dt><dd class="right-area">{away}</dd></dl>'


def pk_block(home, away):
    return f'<div class="score-board-pk"><table><tr><td class="left-area">{home}</td><th>PK戦</th><td class="right-area">{away}</td></tr></table></div>'


def detail(*, match_id="1", periods=None, displayed=(1, 1), pk=None):
    if periods is None:
        periods = [("前半", 0, 1), ("後半", 1, 0)]
    board = (
        '<div class="score-board-main"><div><table><tr>'
        '<th id="team-name-l"><a href="http://www.jleague.jp/club/home/profile/">Home ＦＣ</a></th>'
        f'<td class="score">{displayed[0]}</td><td class="time">'
        + "".join(period(*values) for values in periods)
        + f'</td><td class="score">{displayed[1]}</td>'
        '<th id="team-name-r"><a href="http://www.jleague.jp/club/away/profile/">Away ＦＣ</a></th></tr></table></div></div>'
    )
    identity = f'''<script>form.append('<input type="hidden" name="match_card_id" value="{match_id}" />');</script>'''
    return identity + board + (pk_block(*pk) if pk is not None else "")


def save_cache(tmp_path, name, html, url):
    raw = html.encode("utf-8")
    path = tmp_path / name
    path.write_bytes(raw)
    metadata = {
        "requested_url": url, "final_url": url, "status": 200,
        "fetched_at_utc": "2026-09-14T09:50:00+00:00",
        "content_type": "text/html;charset=UTF-8", "bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
    }
    path.with_suffix(".metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
    return metadata


def test_listing_preserves_raw_names_group_and_large_pk_score():
    record, = parse_listing(listing())
    assert record["match_id"] == "1"
    assert (record["source_year_id"], record["source_frame_id"], record["source_season_label"]) == (20261, 35, "2026特別")
    assert (record["stage"], record["group"], record["round"], record["leg"]) == ("regional", "EAST", 1, None)
    assert record["home_team"] == "Home ＦＣ"
    assert record["stadium"] == "原表記スタジアム"
    assert (record["home_pk_score"], record["away_pk_score"]) == (14, 13)
    assert record["raw_score_text"] == "1-1(PK14-13)"
    assert "home_score_90" not in record


def test_playoff_uses_leg_and_preserves_placement_without_fabricating_round():
    record, = parse_listing(listing(playoff=True, score="2-1"))
    assert (record["stage"], record["group"], record["round"], record["leg"]) == ("playoff", None, None, 2)
    assert record["placement_range"] == "1-2"
    assert record["broadcast_raw"] == "１‐２位決定戦／ＤＡＺＮ"
    assert record["home_pk_score"] is None


@pytest.mark.parametrize("date_label", ["26/04/29(水・祝)", "26/05/06(水・休)"])
def test_listing_retains_holiday_date_label(date_label):
    record, = parse_listing(listing(changes={3: date_label}))
    assert record["match_date_label"] == date_label


@pytest.mark.parametrize("changes", [
    {0: "2026/27"}, {1: "Ｊ１"}, {2: "第１９節第１日"}, {2: "第１戦第１日"},
    {2: "第１節第０日"}, {3: "26/02/30(月)"}, {3: "25/02/06(金)"},
    {4: "25:00"}, {5: " "}, {6: "-1-0"}, {6: "1-1(PK4-4)"},
    {6: "1-1(PK4)"}, {10: "１‐２位決定戦／ＤＡＺＮ"},
])
def test_listing_rejects_invalid_source_values(changes):
    with pytest.raises(ValueError):
        parse_listing(listing(changes=changes))


@pytest.mark.parametrize("broadcast", ["ＤＡＺＮ", "２‐３位決定戦", "１‐３位決定戦", "１‐２位決定戦／３‐４位決定戦"])
def test_playoff_rejects_missing_or_invalid_placement(broadcast):
    with pytest.raises(ValueError):
        parse_listing(listing(playoff=True, changes={10: broadcast}))


@pytest.mark.parametrize("change", [
    lambda html: html.replace("シーズン", "年度"),
    lambda html: html + html,
    lambda html: html.replace("</table>", ""),
    lambda html: html.replace('match_card_id=1', 'match_card_id=0'),
    lambda html: html.replace('</a>', '</a><a href="/SFMS02/?match_card_id=2">other</a>'),
    lambda html: html.replace("</table>", html[html.index("<tr><td>"):html.index("</table>")] + "</table>"),
])
def test_listing_rejects_bad_table_or_ambiguous_id(change):
    with pytest.raises(ValueError):
        parse_listing(change(listing()))


def test_detail_separates_90_minutes_from_incremental_extra_time():
    result = parse_detail(detail(periods=[("前半", 0, 0), ("後半", 0, 0), ("延長前半", 1, 1), ("延長後半", 1, 0)], displayed=(2, 1)), expected_match_id="1")
    assert (result["home_score_90"], result["away_score_90"]) == (0, 0)
    assert result["extra_time_played"] is True
    assert (result["home_extra_time_score"], result["away_extra_time_score"]) == (2, 1)
    assert (result["displayed_home_score"], result["displayed_away_score"]) == (2, 1)
    assert result["home_pk_score"] is None


def test_detail_does_not_confuse_pk_summary_with_kick_grid_or_goal_table():
    kick_grid = '<div class="score-board-pk"><table><tr><td class="left-area"><table><tr><td>Player</td></tr></table></td><th>PK戦</th><td class="right-area"><table><tr><td>Player</td></tr></table></td></tr></table></div>'
    goals = '<div class="score-board-pk"><table><tr><td>Player</td><th>得点</th><td>Player</td></tr></table></div>'
    result = parse_detail(detail(pk=(14, 13)) + kick_grid + goals, expected_match_id="1")
    assert (result["home_pk_score"], result["away_pk_score"]) == (14, 13)
    assert result["extra_time_played"] is False
    assert result["home_extra_time_score"] is None
    without_pk = parse_detail(detail() + goals, expected_match_id="1")
    assert without_pk["home_pk_score"] is None
    with pytest.raises(ValueError, match="no numeric summary"):
        parse_detail(detail() + kick_grid, expected_match_id="1")


def test_detail_accepts_playoff_pk_after_extra_time_with_non_draw_single_match():
    # The tie can be level while this individual leg has unequal goals.
    result = parse_detail(detail(periods=[("前半", 1, 0), ("後半", 0, 0), ("延長前半", 0, 0), ("延長後半", 0, 0)], displayed=(1, 0), pk=(3, 4)), expected_match_id="1")
    assert (result["home_score_90"], result["away_score_90"]) == (1, 0)
    assert result["extra_time_played"] is True
    assert result["home_extra_time_score"] == 0
    assert (result["home_pk_score"], result["away_pk_score"]) == (3, 4)


@pytest.mark.parametrize("change", [
    lambda html: html.replace('value="1"', 'value="2"'),
    lambda html: html[html.index("</script>") + 9:],
    lambda html: html + '<input type="hidden" name="match_card_id" value="1">',
    lambda html: html.replace('id="team-name-l"', 'id="team-name-r"'),
    lambda html: html.replace('class="left-area"', 'class="right-area"', 1),
    lambda html: html.replace("前半", "延長前半"),
    lambda html: html.replace("後半", "前半"),
    lambda html: html.replace(period("後半", 1, 0), ""),
    lambda html: html.replace('<td class="score">1</td>', '<td class="score">2</td>', 1),
    lambda html: html + pk_block(1, "bad"),
    lambda html: html + pk_block(4, 4),
    lambda html: html + pk_block(3, 4) + pk_block(3, 4),
    lambda html: html.replace('class="score-board-main"', 'class="other"'),
])
def test_detail_rejects_bad_identity_sides_periods_totals_or_pk(change):
    with pytest.raises(ValueError):
        parse_detail(change(detail()), expected_match_id="1")


def test_detail_match_link_is_not_page_identity():
    html = detail().split("</script>", 1)[1] + '<a href="/SFMS02/?match_card_id=1">other match</a>'
    with pytest.raises(ValueError, match="match_id"):
        parse_detail(html, expected_match_id="1")


def test_cached_listing_requires_every_second_leg_detail(tmp_path):
    save_cache(tmp_path, "j1_search.html", listing(playoff=True, score="1-1"), SOURCE_URL)
    with pytest.raises(FileNotFoundError):
        read_cached_sources(raw_dir=tmp_path)
    detail_url = "https://data.j-league.or.jp/SFMS02/?match_card_id=1"
    save_cache(tmp_path, "match_1.html", detail(), detail_url)
    records, details, metadata = read_cached_sources(raw_dir=tmp_path)
    assert len(records) == 1
    assert details["1"]["home_score_90"] == 1
    assert set(metadata) == {"j1_search.html", "match_1.html"}


def test_cached_regional_detail_is_optional_but_checked_when_present(tmp_path):
    save_cache(tmp_path, "j1_search.html", listing(), SOURCE_URL)
    records, details, metadata = read_cached_sources(raw_dir=tmp_path)
    assert len(records) == 1 and not details
    assert set(metadata) == {"j1_search.html"}
    save_cache(tmp_path, "match_1.html", detail(match_id="2", pk=(14, 13)), "https://data.j-league.or.jp/SFMS02/?match_card_id=1")
    with pytest.raises(ValueError, match="match_id"):
        read_cached_sources(raw_dir=tmp_path)


def test_cache_rejects_swapped_detail_team_sides_even_if_scores_match(tmp_path):
    save_cache(tmp_path, "j1_search.html", listing(), SOURCE_URL)
    html = detail(pk=(14, 13)).replace("/home/", "/placeholder/").replace("/away/", "/home/").replace("/placeholder/", "/away/")
    save_cache(tmp_path, "match_1.html", html, "https://data.j-league.or.jp/SFMS02/?match_card_id=1")
    with pytest.raises(ValueError, match="team identity differs"):
        read_cached_sources(raw_dir=tmp_path)


@pytest.mark.parametrize("field,value", [
    ("requested_url", "https://data.j-league.or.jp/SFMS01/search?competition_years=2026"),
    ("final_url", "https://example.com/"), ("status", 302), ("bytes", 0),
    ("sha256", "0" * 64), ("fetched_at_utc", "yesterday"),
    ("fetched_at_utc", "2026-09-14T09:50:00"),
    ("fetched_at_utc", "2026-09-14T09:50:00+09:00"),
    ("content_type", "text/plain"),
])
def test_cache_rejects_bad_provenance_without_fetching(tmp_path, field, value):
    metadata = save_cache(tmp_path, "j1_search.html", listing(), SOURCE_URL)
    metadata[field] = value
    (tmp_path / "j1_search.metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
    with pytest.raises(ValueError, match="metadata or SHA-256 mismatch"):
        read_cached_sources(raw_dir=tmp_path)


def test_cache_rejects_changed_html(tmp_path):
    save_cache(tmp_path, "j1_search.html", listing(), SOURCE_URL)
    with (tmp_path / "j1_search.html").open("a", encoding="utf-8") as output:
        output.write("<!-- mutation -->")
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        read_cached_sources(raw_dir=tmp_path)
