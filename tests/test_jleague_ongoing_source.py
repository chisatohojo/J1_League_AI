"""Offline source boundaries: a visible score is not proof of completion."""

from collections import Counter
from copy import deepcopy
from html import escape
from pathlib import Path

import pytest

from src.collect.jleague import HEADERS
from src.collect.jleague_ongoing_source import (
    COMPETITION_KEY,
    apply_completion_evidence,
    parse_completion_evidence,
    parse_listing,
    validate_fixture_coverage,
)


URL = "https://www.jleague.jp/match/j1/2026/091302/"


def listing_html(*, score="1-1", match_id="34583", date_label="26/09/13(日)", kickoff="18:04"):
    score_cell = escape(score)
    if match_id is not None:
        score_cell = f'<a href="/SFMS02/?match_card_id={match_id}">{score_cell}</a>'
    values = [
        "2026/27", "Ｊ１", "第７節第３日", date_label, kickoff,
        '<a href="http://www.jleague.jp/club/tokyov/profile/">東京Ｖ</a>',
        score_cell,
        '<a href="http://www.jleague.jp/club/chiba/profile/">千葉</a>',
        "味スタ", "15254", "DAZN",
    ]
    return '<table class="search-table"><tr>' + "".join(f"<th>{header}</th>" for header in HEADERS) + "</tr><tr>" + "".join(f"<td>{value}</td>" for value in values) + "</tr></table>"


def official_html(*, completed=True, header_score=(1, 1), over_score=(1, 1)):
    header = f'''<link rel="canonical" href="{URL}">
    <div class="o-page-header--game-details o-page-header--game-details--post-game">
      <div class="a-tournament-logo--j1"><img alt="明治安田Ｊ１リーグ"></div>
      <p class="o-page-header__date">2026/9/13 (日) 18:00 KO</p>
      <p class="o-page-header__section">第7節</p>
      <a class="o-page-header__club--home" href="/club/tokyov/"></a>
      <a class="o-page-header__club--away" href="/club/chiba/"></a>
      <p class="o-page-header__match-score">{header_score[0]}</p>
      <p class="o-page-header__match-score">{header_score[1]}</p>
    </div>'''
    over = f'''<section id="game-over" class="p-game-details-summary-tab__game-over">
      <h3>試合終了</h3><p class="o-team-comparison__score">{over_score[0]}</p>
      <p class="o-team-comparison__score">{over_score[1]}</p></section>'''
    return header + (over if completed else "")


def test_numeric_score_is_only_a_candidate():
    row = parse_listing(listing_html())[0]
    assert row["status"] == "candidate"
    assert row["match_id"] == "34583"
    assert row["result"] == 1
    assert row["evidence_url"] == ""
    assert row["round_label"] == "第７節第３日"
    assert row["match_date_label"] == "26/09/13(日)"
    assert row["home_team"] == "東京Ｖ"


@pytest.mark.parametrize("match_id", [None, "34583"])
def test_scheduled_fixture_keeps_unknown_results_with_or_without_match_id(match_id):
    row = parse_listing(listing_html(score="vs", match_id=match_id, kickoff=""))[0]
    assert row["status"] == "scheduled"
    assert row["match_id"] == match_id
    assert row["home_score"] is None and row["away_score"] is None and row["result"] is None


def test_fixture_key_does_not_change_with_date_kickoff_round_or_stadium():
    before = parse_listing(listing_html(score="vs", match_id=None))[0]
    html = listing_html(score="vs", match_id=None, date_label="27/02/13(土)", kickoff="")
    html = html.replace("第７節第３日", "第２１節第１日").replace("味スタ", "●未定●")
    after = parse_listing(html)[0]
    assert before["fixture_key"] == after["fixture_key"] == f"{COMPETITION_KEY}:tokyov:chiba"
    assert after["match_date"] == "2027-02-13"
    assert after["stadium"] == "●未定●"


@pytest.mark.parametrize("score", ["中止", "延期", "1-1(PK5-4)", "1.0-0", "-1-0", "1 - 1", ""])
def test_unknown_or_special_score_syntax_stops(score):
    with pytest.raises(ValueError):
        parse_listing(listing_html(score=score))


def test_numeric_score_requires_official_match_id():
    with pytest.raises(ValueError, match="no official match_id"):
        parse_listing(listing_html(match_id=None))


@pytest.mark.parametrize("old,new", [
    ("2026/27", "2026特別"),
    ("Ｊ１", "Ｊ１ 1st"),
    ("26/09/13(日)", "26/06/13(土)"),
    ("26/09/13(日)", "27/02/30(火)"),
    ("第７節第３日", "第３９節第１日"),
    ("18:04", "25:00"),
    ("http://www.jleague.jp/club/tokyov/profile/", "https://example.com/club/tokyov/profile/"),
    ("/club/chiba/profile/", "/club/tokyov/profile/"),
    ("?match_card_id=34583", "?match_card_id=0"),
    ("<th>大会</th>", "<th>別の列</th>"),
    ("</table>", ""),
])
def test_invalid_listing_structure_and_identity_stop(old, new):
    with pytest.raises(ValueError):
        parse_listing(listing_html().replace(old, new))


def test_duplicate_fixture_and_match_ids_stop():
    original = listing_html()
    data_row = original.split("</tr>")[1] + "</tr>"
    with pytest.raises(ValueError, match="Duplicate fixture_key"):
        parse_listing(original.replace("</table>", data_row + "</table>"))
    other = data_row.replace("tokyov", "urawa").replace("東京Ｖ", "浦和")
    with pytest.raises(ValueError, match="Duplicate match_id"):
        parse_listing(original.replace("</table>", other + "</table>"))


def test_explicit_match_bound_evidence_promotes_candidate_without_mutating_input():
    records = parse_listing(listing_html())
    before = deepcopy(records)
    evidence = parse_completion_evidence(official_html(), source_url=URL)
    completed = apply_completion_evidence(records, [evidence])
    assert evidence["verified"] is True
    assert completed[0]["status"] == "completed"
    assert completed[0]["evidence_url"] == URL
    assert completed[0]["evidence_type"] == "official_game_over_section"
    assert records == before


@pytest.mark.parametrize("fake_wrapper", ["script", "template", "noscript", "skeleton"])
def test_translation_scripts_templates_and_loading_skeletons_are_not_evidence(fake_wrapper):
    clean = official_html(completed=False)
    fake = official_html().split('<section id="game-over"')[1]
    fake = '<section id="game-over"' + fake
    if fake_wrapper == "skeleton":
        fake = '<div class="p-match-details-skeleton__header">' + fake + "</div>"
    else:
        fake = f"<{fake_wrapper}>" + fake + f"</{fake_wrapper}>"
    evidence = parse_completion_evidence(clean + fake, source_url=URL)
    assert evidence["verified"] is False
    assert apply_completion_evidence(parse_listing(listing_html()), [evidence])[0]["status"] == "candidate"


@pytest.mark.parametrize("old,new", [
    (URL, "https://www.jleague.jp/match/j1/2026/091303/"),
    ("明治安田Ｊ１リーグ", "明治安田Ｊ１百年構想リーグ"),
    ("2026/9/13", "2026/9/14"),
    ("第7節", "第39節"),
    ("試合終了", "試合中"),
    ("o-page-header--game-details--post-game", "o-page-header--game-details--pre-game"),
    ("/club/chiba/", "/club/tokyov/"),
    ("</section>", ""),
])
def test_mismatched_or_malformed_official_evidence_stops(old, new):
    with pytest.raises(ValueError):
        parse_completion_evidence(official_html().replace(old, new), source_url=URL)


def test_untrusted_source_host_and_other_competition_are_rejected():
    for source_url in (URL.replace("www.jleague.jp", "example.com"), URL.replace("/j1/", "/j2/")):
        with pytest.raises(ValueError):
            parse_completion_evidence(official_html(), source_url=source_url)


def test_ambiguous_game_over_or_canonical_is_rejected():
    original = official_html()
    section = '<section id="game-over"' + original.split('<section id="game-over"')[1]
    for addition in (section, f'<link rel="canonical" href="{URL}">'):
        with pytest.raises(ValueError):
            parse_completion_evidence(original + addition, source_url=URL)


def test_header_and_game_over_scores_must_agree():
    with pytest.raises(ValueError, match="scores conflict"):
        parse_completion_evidence(official_html(over_score=(1, 2)), source_url=URL)


@pytest.mark.parametrize("attribute", ['aria-hidden="true"', "hidden"])
def test_explicitly_hidden_game_over_sections_are_not_evidence(attribute):
    html = official_html().replace('<section id="game-over"', f'<section {attribute} id="game-over"')
    assert parse_completion_evidence(html, source_url=URL)["verified"] is False


@pytest.mark.parametrize("field,value", [
    ("home_score", 2), ("away_score", 2), ("match_date", "2026-09-14"),
    ("round", 8), ("home_club", "urawa"), ("competition_key", "j1_hyakunen_2026"),
    ("fixture_key", "j1_2026_2027:chiba:tokyov"),
])
def test_evidence_must_match_the_listing_exactly(field, value):
    evidence = parse_completion_evidence(official_html(), source_url=URL)
    evidence[field] = value
    with pytest.raises(ValueError):
        apply_completion_evidence(parse_listing(listing_html()), [evidence])


def test_duplicate_evidence_and_completed_evidence_for_vs_stop():
    evidence = parse_completion_evidence(official_html(), source_url=URL)
    with pytest.raises(ValueError, match="Duplicate evidence"):
        apply_completion_evidence(parse_listing(listing_html()), [evidence, evidence])
    with pytest.raises(ValueError, match="conflicts"):
        apply_completion_evidence(parse_listing(listing_html(score="vs", match_id=None)), [evidence])


def test_incomplete_fixture_set_cannot_redefine_the_competition_format():
    with pytest.raises(ValueError, match="coverage"):
        validate_fixture_coverage(parse_listing(listing_html()))


def test_saved_source_bootstrap_boundaries_when_local_cache_is_available():
    listing = Path("data/raw/jleague/2026_2027/research/20260914T224804164752Z/j1_search.html")
    evidence_dir = Path("data/raw/jleague/2026_27/research/20260915T035921896334Z")
    files = [listing, evidence_dir / "official_match_091302.html", evidence_dir / "official_match_091904.html"]
    if not all(path.exists() for path in files):
        pytest.skip("Locally archived official research pages are not distributed as test fixtures.")
    rows = parse_listing(listing.read_text(encoding="utf-8"))
    summary = validate_fixture_coverage(rows)
    assert (summary["club_count"], summary["round_count"], summary["fixture_count"]) == (20, 38, 380)
    assert Counter(row["status"] for row in rows) == {"scheduled": 310, "candidate": 70}
    evidence = [parse_completion_evidence(path.read_text(encoding="utf-8"), source_url=f"https://www.jleague.jp/match/j1/2026/{suffix}/") for path, suffix in zip(files[1:], ("091302", "091904"))]
    updated = apply_completion_evidence(rows, evidence)
    assert Counter(row["status"] for row in updated) == {"scheduled": 310, "candidate": 69, "completed": 1}
    assert [row["match_id"] for row in updated if row["status"] == "completed"] == ["34583"]
