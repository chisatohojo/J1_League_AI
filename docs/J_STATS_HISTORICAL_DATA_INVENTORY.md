# J Stats historical data inventory (J1 2015–2025)

調査日: 2026-09-21 (JST)

## 1. Executive summary

J.LEAGUE 公式だけを対象に、J1 の advanced statistics を year-by-year で監査した。結論は次のとおり。

- 現行 J Stats の season-final club/player ranking は **2018 から**取得できる。2015–2017 の同 route は HTTP 200 でもランキング行がない。
- team の `expected_goals` / `expected_goals_against` と player の `expected_goals` / `expected_goals_excl_pk` は **2019 から**取得できる。2018 の xG 系 ranking は空である。
- match-level の home/away xG 最終値は、2024 の **96/380** 試合（最初の確認日は 2024-09-13）と、2025 の **380/380** 試合で公式 live-commentary 内に確認できた。2024 の残り 284 試合には xG の翻訳ラベルは埋め込まれているが、試合値はない。
- 2020–2023 は各年3試合の opening/mid/late sample で match-level xG 値を確認できなかった。sample 外まで「存在しない」とは断定しない。
- J1 全試合の tracking system 導入は2015年から公式に確認できるが、2015–2017 の match-level tracking data を現在取得できる公式 route は発見できなかった。現行 match page の各年3試合にも tracking link/data はなかった。
- 現行 J Stats は season を指定できるが、過去の round/date 時点へ戻す parameter や backend route は確認できない。現在得られる過去 season 値は season-final/restated snapshot として扱い、同 season の pre-match feature に流用してはならない。

本監査では collector、dataset、feature、model、prediction を作成していない。

## 2. Classification

| Code | Meaning |
|---|---|
| A | 公式 structured route から historical production dataset 化できる |
| B | 公式 HTML / embedded RSC の解析で実用的に取得できる |
| C | 一部 season / 一部 match だけ確認できる |
| D | 公式に data の存在証拠はあるが、現在の取得 route を発見できない |
| E | 今回の公式 route/sample では確認できない |

`tracking` 列の B は raw coordinates ではなく、J Stats の season-final running/tracking summary（distance/sprint）を意味する。

## 3. Availability matrix

| Year | Season team stats | Season player stats | Season xG/xGA | Match xG | Tracking | Possession | Pass | Distance / sprint | Defensive events |
|---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| 2015 | E | E | E | E | D | E | E | D | E |
| 2016 | E | E | E | E | D | E | E | D | E |
| 2017 | E | E | E | E | D | E | E | D | E |
| 2018 | B | B | E | E | B | B | B | B | B |
| 2019 | B | B | B | E | B | B | B | B | B |
| 2020 | B | B | B | E (0/3 sample) | B | B | B | B | B |
| 2021 | B | B | B | E (0/3 sample) | B | B | B | B | B |
| 2022 | B | B | B | E (0/3 sample) | B | B | B | B | B |
| 2023 | B | B | B | E (0/3 sample) | B | B | B | B | B |
| 2024 | B | B | B | C (96/380) | B | B | B | B | B |
| 2025 | B | B | B | B (380/380) | B | B | B | B | B |

Notes:

- Possession/pass/distance/sprint/defensive events の B は **season-final ranking** であり、match-level coverage を意味しない。
- 2015–2017 の D は、公式発表上は tracking system/data が存在したことを示す。現在の production source としての取得可能性は確認できない。
- SFMS02 で既に得られる score、lineup、substitution、card、SH、CK、FK はこの advanced-stat matrix とは別系統である。

## 4. Official routes and sampling method

### 4.1 Season-final J Stats

- Club: `https://www.jleague.jp/j1/stats/club/{season}/{stat}/search-list/`
- Player: `https://www.jleague.jp/j1/stats/player/{season}/{stat}/search-list/`

ページ内 embedded RSC の ranking list、season、filter list、更新表示を機械的に確認した。club route は38 stat × 8 seasons (2018–2025) = 304 pages を監査した。player route は `shoot` と xG 関連を境界確認した。

### 4.2 Match identity and match-level xG

- Official schedule listing: `https://www.jleague.jp/j1/match/search-list/?category=j1&startdate=...&enddate=...&period=custom`
- Match commentary: `https://www.jleague.jp/match/j1/{year}/{official_match_path_id}/live-commentary/`

schedule listing の actual `detailHref` だけを採用した。広い期間の検索は250件付近で制限されるため、年を複数期間へ分割して official match links を union した。推測 ID は使っていない。

match-level xG の `present` は、Full Time の本文に次の3項目が同時にあり、home/away の数値が示される場合に限定した。

- この試合のシュート
- 枠内シュート
- ゴール期待値

ページ共通の翻訳辞書にある `expected_goals` / 「ゴール期待値」ラベルだけは値の証拠に数えていない。

## 5. 2018–2025 club route inventory

### 5.1 Season coverage

| Season | Expected clubs | Filter options | Full 38-route rankings | Empty routes | Sparse routes | Displayed source update date |
|---:|---:|---:|---:|---|---|---|
| 2018 | 18 | 62 | 34 | xG, xGA, xGA excl. PK | red card 12/18 | 2024-05-28 |
| 2019 | 18 | 62 | 37 | none | red card 11/18 | 2024-05-28 |
| 2020 | 18 | 62 | 37 | none | red card 12/18 | 2024-05-28 |
| 2021 | 20 | 62 | 37 | none | red card 15/20 | 2025-10-27 |
| 2022 | 18 | 62 | 37 | none | red card 16/18 | 2024-05-28 |
| 2023 | 18 | 62 | 37 | none | red card 15/18 | 2024-05-28 |
| 2024 | 20 | 62 | 38 | none | none in audited routes | 2024-12-10 |
| 2025 | 20 | 62 | 37 | none | red card 15/20 | 2025-12-08 |

`red_count` の少ない club count は route failure ではなく、0件の club が ranking から省略される表示と整合する。ただし明示的な zero row を公式 response から作れないため、ranking をそのまま production table にする場合は sparse として保持すべきである。

古い season の更新日は当時の publication timestamp ではない。後日の page maintenance/restatement を含み得るため、historical in-season 時点の根拠には使えない。

### 5.2 Audited stat families

| Family | Slugs | Value type / unit | Earliest usable season |
|---|---|---|---:|
| Shots | `shoot`, `shoot_on_target`, `suffer_shoot`, `suffer_shoot_on_target` | total / count | 2018 |
| xG | `expected_goals`, `expected_goals_against`, `expected_goals_against_excl_pk` | decimal; official page does not state a stored unit | 2019 |
| Creation | `cross_count`, `chance_create` | total / count | 2018 |
| Defense | `clear_count`, `tackle_count`, `block_count`, `intercept_count`, `recovery_count` | total / count | 2018 |
| Defense rates | `tackle_rate` | percentage | 2018 |
| Duels/carry | `dribble_count`, `air_battle_win_count`, `one_on_one` | total / count | 2018 |
| Duels/carry rates | `dribble_rate`, `air_battle_win_rate` | percentage | 2018 |
| Passing | `pass_count`, `through_pass_count` | total / count | 2018 |
| Passing averages/rates | `pass_count_per_game`, `pass_rate`, `through_pass_rate` | count per game / percentage | 2018 |
| Possession | `ball_rate` | percentage | 2018 |
| Running | `distance_per_game`, `sprint_per_game` | km per game / sprint count per game | 2018 |
| Running by phase | `at_sprint_per_game`, `mt_sprint_per_game`, `dt_sprint_per_game` | count per game | 2018 |
| With/without ball | `possession_distance_per_game`, `un_possession_distance_per_game` | km per game | 2018 |
| With/without ball sprint | `possession_sprint_per_game`, `un_possession_sprint_per_game` | count per game | 2018 |
| Discipline/results | `foul_count`, `yellow_count`, `red_count`, `clean_sheet` | total / count | 2018 (`red_count` sparse) |

The same URL structure returns HTTP 200 for 2015–2017, but `shoot` has no ranking rows. Therefore page existence alone is not availability.

## 6. Player stats and xG archaeology

The official club page exposes the player route; it was not inferred. `shoot` ranking results were:

| Season | Player rows | xG rows | xG excl. PK rows | Assessment |
|---:|---:|---:|---:|---|
| 2015 | 0 | — | — | no ranking |
| 2016 | 0 | — | — | no ranking |
| 2017 | 0 | — | — | no ranking |
| 2018 | 420 | 0 | 0 | player stats exist; xG absent |
| 2019 | 417 | 417 | 417 | xG usable |
| 2020 | 420 | 420 | 420 | xG usable |
| 2021 | 492 | 492 | 491 | npxG one row sparse |
| 2022 | 441 | 441 | 441 | xG usable |
| 2023 | 440 | 440 | 440 | xG usable |
| 2024 | 508 (`shoot`) | 509 | 509 | xG route has one extra ranked player |
| 2025 | 512 | 512 | 512 | xG usable |

The player filter exposes 82 options including `expected_goals` and `expected_goals_excl_pk`. Player-level xGA is not an advertised route. Team xGA is available from 2019.

## 7. Match-level xG boundary

### 7.1 Full coverage audit: 2024–2025

| Season | Official J1 match links | Final home/away xG present | Partial value | Final xG missing | Coverage |
|---:|---:|---:|---:|---:|---:|
| 2024 | 380 | 96 | 0 | 284 | 25.26% |
| 2025 | 380 | 380 | 0 | 0 | 100.00% |

2024 の最初の confirmed final summary は match path ID `091301` (2024-09-13)。それ以前のページにも xG の共通 UI/翻訳ラベルが8回程度現れるが、home/away value はないため `partial` ではなく `missing` とした。2024 の delivery transition 後と2025は、同じ Full Time sentence に shots、shots on target、home/away xG が入る。

### 7.2 2020–2023 sample

| Season | Sample IDs (opening / middle / late) | Match xG values |
|---:|---|---|
| 2020 | `022101`, `090906`, `112119` | 0/3 |
| 2021 | `022601`, `062706`, `120410` | 0/3 |
| 2022 | `021801`, `062502`, `110509` | 0/3 |
| 2023 | `021701`, `062403`, `120309` | 0/3 |

各ページは official identity と一致した。xG label は共通辞書に存在するが、`ゴール期待値：home：value、away：value` に相当する本文はない。これは sample-based boundary であり、全試合不存在の証明ではない。

2015–2019 も各年の代表1試合 (`030701`, `022701`, `022501`, `022301`, `022201`) で final shots/SOT/xG summary を確認できなかった。

**Boundary conclusion:** partial-season match xG の最初の確認 season は2024、full-season coverage の最初の確認 season は2025。

## 8. Tracking archaeology: 2015–2017

Official evidence:

- [2015 J1全試合へのtracking system導入発表](https://www.jleague.jp/news/article/550/) は、underlying tracking data を全試合で取得するとしている。
- [LIVE tracking開始発表](https://www.jleague.jp/news/article/714/) は、public live service が2015 J1の毎節1試合を対象としていたと説明する。
- [2016 service update](https://www.jleague.jp/news/article/6303/) は、走行距離、sprint、top speed に加えて shots/SOT 等を live tracking に追加したと説明する。
- 旧公式 schedule search の検索indexには「トラッキング」欄が残る。

Current retrieval audit:

| Year | Sample match IDs | Current match page tracking link | Embedded tracking data | Stable official data route |
|---:|---|---:|---:|---:|
| 2015 | `030701`, `071101`, `112209` | 0/3 | 0/3 | not found |
| 2016 | `022701`, `070201`, `110309` | 0/3 | 0/3 | not found |
| 2017 | `022501`, `070801`, `120209` | 0/3 | 0/3 | not found |

Hence classification D. The data's historical existence does not establish a currently retrievable production source. Search-index text and archived presentation are not sufficient to invent an endpoint. No URL brute force was performed.

## 9. Historical match page field evolution

| Period | Confirmed official match-level fields | Not confirmed as usable match-level fields |
|---|---|---|
| 2015–2023 | SFMS02: date/kickoff, teams, score, stadium, referee, lineups, substitutions, cards, SH, CK, FK. Current J.LEAGUE.jp pages retain identity/commentary. | xG, possession, pass rate, distance, sprint. Historical tracking existed but current retrieval route was not found. |
| 2024 through 2024-09-12 | Same SFMS02 fields; season-final J Stats families available. | Final match xG/SOT summary; detailed match stats page has previously audited static placeholders. |
| 2024-09-13 through 2024 end | Full Time commentary adds final shots, shots on target, and home/away xG for 96 matches. | Reliable match-level possession/pass/distance/sprint route not confirmed. |
| 2025 | Full Time commentary has final shots, shots on target, and home/away xG for 380/380 official links. | Reliable match-level possession/pass/distance/sprint route not confirmed. |

The already-audited J.LEAGUE.jp detailed stats page returned static/RSC placeholders rather than final possession/SOT/foul values. It is not upgraded to an available source by this inventory.

## 10. Season-final, point-in-time, match-level, and tracking are different

1. **Season-final cumulative/average ranking**: currently retrievable for historical seasons, but reflects the completed season and possible later restatement.
2. **Historical in-season point-in-time snapshot**: not recoverable from the routes found here.
3. **Match-level observations**: can be chronologically aggregated without leakage if only matches before the target are used. Official xG meets this for 2025 and the final 96 matches of 2024.
4. **Tracking raw/summary**: current J Stats gives season-final summary rankings from 2018. This is not raw match tracking and cannot reconstruct past match values.

Season-final values must not be used as features for earlier matches in that same season. Doing so would expose future matches. Without stored historical snapshots or match-level values, cumulative differencing is also unsafe.

## 11. Historical in-season snapshot recoverability

The observed club/player J Stats filters contain competition/category, season/year, stat, and club/player selection. No observed filter or embedded request key provided historical `round`, `section`, `date`, `updated_at`, `snapshot`, `week`, or `matchday` state. A light inspection found no official backend link for prior update states.

**Result: historical in-season snapshot route not found.** No speculative parameter or brute-force request was used.

## 12. Recommended production datasets

Priority is based on official provenance, coverage, granularity, leakage safety, and implementation cost—not on model performance.

1. **2025 J1 match-level xG collector — recommended next.** Official match identity and final home/away xG are present in 380/380 live-commentary pages. Store the official match URL and original text/value, validate identity, and build only lagged features later.
2. **2024 partial match-level xG — optional companion.** Retain the explicit 96/380 availability mask. Do not impute the 284 absent matches or treat the UI label as data.
3. **2018–2025 season-final J Stats archive — useful for descriptive research and schema discovery.** It is not approved as same-season pre-match data. Preserve retrieval time and displayed update date because old pages can be restated.
4. **2019–2025 season-final team/player xG — useful for aggregate validation only.** It cannot replace match-level historical xG for rolling features.
5. **2015–2017 tracking collector — defer.** Reconsider only if a stable, currently accessible official data route is found. Official announcements alone are insufficient.

## 13. Request accounting

- Evidence-bearing successful direct HTTP responses from `jleague.jp` used across the audit: **1,208**.
- This includes the 304-page club route matrix and the 760 match pages used for the definitive 2024/2025 xG coverage pass.
- One earlier duplicate full-coverage attempt was interrupted after 2024 progress 350. Its exact final request count was not recoverable; at least 344 additional requests were sent and its observations were discarded. Therefore total network traffic was greater than 1,208, while the reported matrices use the complete controlled pass only.
- Search-engine calls used to locate official historical announcements are not included in the direct HTTP count.

No production cache or dataset was written by this audit.

## 14. Limitations

- 2020–2023 match-level xG is based on three representative matches per season, not a full crawl.
- 2015–2019 match page comparison is representative, not exhaustive.
- Ranking row counts can be sparse when zero-valued entities are omitted; absence is not automatically zero.
- Official methodology/version history for xG was not found in the inspected route. Values across seasons should not be assumed perfectly method-stable without further official documentation.
- Current availability can change if J.LEAGUE.jp redesigns or removes embedded RSC/history pages.
- This document records availability, not permission for prediction use. Any future feature must be generated from observations available strictly before the target match.
