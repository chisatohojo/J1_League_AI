import csv
import hashlib
import json
from pathlib import Path

import pytest

from src.collect.sfms02_match_events import MatchEventError, _materialize


URL = "https://data.j-league.or.jp/SFMS02/?match_card_id=1"


class Master:
    def resolve_team_id(self, name, *, source, on):
        return {
            ("jleague_data_site", "H"): "team_0001",
            ("jleague_data_site", "A"): "team_0002",
            ("jleague_official", "Home"): "team_0001",
            ("jleague_official", "Away"): "team_0002",
        }[(source, name)]


def raw_fixture():
    return (
        '<!-- A2 Start --><td class="left-area"><table><tr><td>Scorer</td><td>10\'</td></tr></table></td>'
        '<td class="right-area"><table></table></td><!-- A2 End -->'
        '<!-- A5 Start --><table></table><!-- A5 End --><!-- A5 Start --><table></table><!-- A5 End -->'
        '<!-- A6 Start --><table></table><!-- A6 End --><!-- A6 Start --><table></table><!-- A6 End -->'
        '<!-- A7 Start --><table><tr><td class="change">▽</td><td class="name">Out</td><td class="time">60\'</td></tr>'
        '<tr><td class="change">▲</td><td class="name">In</td><td class="time"></td></tr></table><!-- A7 End -->'
        '<!-- A7 Start --><table></table><!-- A7 End -->'
        '<!-- A8 Start --><table><tr><td class="name">Carded</td><td class="time">***</td></tr></table><!-- A8 End -->'
        '<!-- A8 Start --><table></table><!-- A8 End --><!-- A12 Start -->'
    ).encode()


def write_csv(path, fieldnames, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader(); writer.writerows(rows)


def inputs(root, *, bad_sha=False, stats_id="1", duplicate=False):
    matches, stats, raw = root / "matches", root / "stats", root / "raw"
    raw.mkdir(parents=True)
    match_rows = [{"match_id":"1", "season":"2015", "match_date":"2015-01-01",
                   "home_team":"H", "away_team":"A",
                   "home_score":"1", "away_score":"0", "source_url":URL}]
    if duplicate:
        match_rows.append(dict(match_rows[0]))
    write_csv(matches / "2015_matches_probe.csv", match_rows[0].keys(), match_rows)
    stat_rows = [{"match_id":stats_id, "home_team":"Home", "away_team":"Away",
                  "home_team_id":"team_0001", "away_team_id":"team_0002", "source_url":URL}]
    if duplicate:
        stat_rows.append(dict(stat_rows[0]))
    write_csv(stats / "2015_match_stats.csv", stat_rows[0].keys(), stat_rows)
    body = raw_fixture(); (raw / "1.html").write_bytes(body)
    metadata = {"requested_url":URL, "final_url":URL, "status":200, "match_id":"1",
                "bytes":len(body), "sha256":hashlib.sha256(body).hexdigest()}
    if bad_sha: metadata["sha256"] = "0" * 64
    (raw / "1.metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
    return matches, stats, raw


def run(root, **kwargs):
    matches, stats, raw = inputs(root, **kwargs)
    return _materialize(expected_counts={2015: 1}, matches_dir=matches, stats_dir=stats,
        raw_dir=raw, output_path=root / "out.csv", summary_path=root / "summary.json",
        team_master=Master())


def test_materializes_validated_deterministic_artifact_and_a7_ratio(tmp_path):
    first = run(tmp_path / "a"); second = run(tmp_path / "b")
    assert first["source_matches"] == 1 and first["total_event_rows"] == 3
    assert first["raw_source_rows"]["A7"] == 2
    assert first["event_types"]["SUBSTITUTION"]["rows"] == 1
    assert first["unresolved_minute_rows"] == 1
    assert (tmp_path / "a/out.csv").read_bytes() == (tmp_path / "b/out.csv").read_bytes()
    assert first["output_sha256"] == second["output_sha256"]


@pytest.mark.parametrize("failure", ["duplicate", "id_mismatch", "missing_raw", "bad_sha"])
def test_input_preflight_hard_fail(tmp_path, failure):
    root = tmp_path / failure
    if failure == "duplicate":
        matches, stats, raw = inputs(root, duplicate=True)
        expected = {2015: 2}
    else:
        matches, stats, raw = inputs(root, stats_id="2" if failure == "id_mismatch" else "1",
                                     bad_sha=failure == "bad_sha")
        expected = {2015: 1}
        if failure == "missing_raw": (raw / "1.html").unlink()
    with pytest.raises(MatchEventError):
        _materialize(expected_counts=expected, matches_dir=matches, stats_dir=stats,
            raw_dir=raw, output_path=root / "out.csv", summary_path=root / "summary.json",
            team_master=Master())
    assert not (root / "out.csv").exists()


def test_refuses_output_overwrite(tmp_path):
    root = tmp_path / "overwrite"; matches, stats, raw = inputs(root)
    (root / "out.csv").write_text("existing", encoding="utf-8")
    with pytest.raises(MatchEventError, match="overwrite"):
        _materialize(expected_counts={2015:1}, matches_dir=matches, stats_dir=stats,
            raw_dir=raw, output_path=root / "out.csv", summary_path=root / "summary.json",
            team_master=Master())


def test_materializer_has_no_network_dependency(tmp_path, monkeypatch):
    import urllib.request
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: (_ for _ in ()).throw(AssertionError("network")))
    assert run(tmp_path / "offline")["external_http_requests"] == 0
