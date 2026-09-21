# J.LEAGUE 出場停止データ feasibility audit

## 1. Summary

本監査は、J.LEAGUE 公式 source だけを使い、出場停止情報を kickoff 前に既知の pre-match data として安全に利用できるかを確認したものである。collector、feature、model evaluation、prediction は実施していない。

最終判定は **C: 2015～2024 historical production feature には現状不十分** とする。

理由は、代表年の公式告知自体は現在も閲覧でき、対象大会・対象日・対象節・選手・クラブを取得できる一方、次が未解決だからである。

- historical archive の全件性を確認できる season-keyed listing/API がない。
- 過去ページには target kickoff 後の `dateModified` がある例があり、現在の本文だけでは kickoff 時点の内容を厳密に復元できない。
- 2019 corporate archive は公開日を確認できるが、時刻を確認できない。
- official player ID は sampled notice に含まれず、source ごとの空白表記差により local player data への exact linkage が失敗する例がある。
- multi-match suspension は明示された target row なら展開可能だが、規程から対象試合を推測して補完してはならない。

一方、**2026/27 以降を定期 snapshot として収集する運用は B 相当**である。公開時点で raw HTML、`published_at`、`source_updated_at`、`retrieved_at` を保存し、kickoff 前に取得済みの record だけを使う方式なら、将来の collector 候補になる。

## 2. Official source overview

### 2.1 J.LEAGUE.jp news / corporate archive

代表ページを開いて本文を確認した。

- 2015: [出場停止選手のお知らせ（15年5月25日）](https://www.jleague.jp/news/article/1560/)
- 2019: [出場停止選手のお知らせ（2019年5月14日）](https://aboutj.jleague.jp/corporate/pressrelease/article/11115)
- 2024: [出場停止選手のお知らせ（2024年7月16日）](https://www.jleague.jp/news/article/28371/)
- 2026/27: [出場停止選手のお知らせ（2026年9月14日）](https://www.jleague.jp/news/article/34896/)
- 2026/27 multi-match sample: [出場停止選手のお知らせ（2026年8月10日）](https://www.jleague.jp/news/article/34617/)

2015 は competition・節・開催日ごとの見出しと選手行からなる旧 layout である。2019 以降の sampled pages は概ね次の列を持つ表形式だった。

- 選手
- チーム
- 前回の停止
- 今回の停止
- 出場停止試合

modern J.LEAGUE.jp article では JSON-LD の `datePublished` と `dateModified` を取得できた。2019 corporate page は公開日だけで、時刻は確認できなかった。

### 2.2 J.League Data Site

公式 navigation から [SFIN03 出場停止のお知らせ](https://data.j-league.or.jp/SFIN03/?lang=ja) を確認した。current snapshot は選手・チーム・停止 code・対象試合を表示するが、過去日を stable URL parameter で指定できることは確認できなかった。date selector は session state を伴い、未認証の単発 request から historical snapshot を再現できなかった。

Data Site は current operation の補助 source としては有望だが、今回の範囲では historical archive source として採用できない。

### 2.3 Rules

[2026/27 J.LEAGUE 出場停止規程](https://www.jleague.jp/corporate/assets/pdf/regulation/jleague/detailed_rules_regarding_handling_of_suspensions.pdf) を semantics の確認に使用した。規程は record source ではなく、code と competition-specific rule の参考資料として扱う。

## 3. Source classification

| Official source | Historical | Current | Classification | Main limitation |
|---|---:|---:|---|---|
| J.LEAGUE.jp news / corporate archive | representative pages available | available | B | HTML layout variation、全件 listing 未確認、過去 revision の as-of 復元不可 |
| J.League Data Site SFIN03 | historical route 未確定 | available | B for current / C for historical | session-based date selection、publication time 不明 |
| J.LEAGUE rules PDF | versioned reference | available | B as reference only | individual suspension record ではない |
| official club pages | systematic route 未確認 | club-dependent | C | centralized coverage と統一 schema を確認できない |

## 4. Historical availability and publication timing

| Sample | Page exists now | Published information | Target sample | Point-in-time assessment |
|---|---:|---|---|---|
| 2015 | yes | 2015-05-25 16:22 JST; JSON-LD also exposes a later modification timestamp | J1 5/30 matches | published before target, but current page was modified later; original body cannot be proven from current HTML alone |
| 2019 | yes | 2019-05-14 date; time not confirmed | J1 5/18 matches | date is before target, but intraday safety cannot be proven if same-day cases occur |
| 2024 | yes | 2024-07-16 18:50 JST; modified 18:55 JST | J1 7/20 matches | publication and update are before sampled target |
| 2026/27 | yes | 2026-09-14 19:00 JST; modified on 9/15 | J1 9/19 and 9/20 matches | suitable for operational snapshot if fetched and frozen before kickoff |

The archive preserves representative pages from 2015, 2019, and 2024, but this audit did not establish complete season inventories. No historical count or coverage percentage is claimed.

## 5. Available fields

| Field | 2015 sample | 2019+ sample | Notes |
|---|---:|---:|---|
| `player_name_raw` | yes | yes | official display text; no automatic whitespace normalization |
| `club_name_raw` | yes | yes | TeamMaster exact resolution required |
| target competition | yes | yes | raw label and canonical value should both be stored |
| `target_match_date` | yes | yes | explicit in sampled notices |
| `target_round_raw` | yes | yes | check field, not the only identity key |
| opponent | no | no | can only be derived after unique match linkage |
| official match ID | no | no | derive only by exact linkage to the existing match dataset |
| official player ID | no | no | not present in sampled notices |
| previous/current suspension code | no | yes | modern table contains code such as `J1(f)` or `J1(b)` |
| total suspension matches | no | code-dependent | code semantics exist, but explicit target rows take precedence |
| remaining suspension matches | no | no | no independent remaining-count field found |
| reason / disciplinary basis | no | code-level only | detailed incident/reason was not a stable row field |
| `published_at` | yes | date only in sampled 2019 page; datetime in modern/2015 JSON-LD | timezone must be retained |
| `source_updated_at` | JSON-LD | modern JSON-LD; not confirmed on sampled 2019 page | later update invalidates naive historical as-of assumptions |
| `source_url` | yes | yes | immutable raw snapshot and hash also required |

## 6. Suspension semantics

The sampled modern notices include official codes. The table notes distinguish the target competition and suspension length/type. The rules also confirm that yellow-card accumulation is competition-specific. A J1 accumulation suspension must not automatically be moved to an intervening League Cup match.

Dismissal and disciplinary-committee sanctions are more complex. Depending on the case, a suspension can cover multiple matches or move between competitions of the same regulatory level. Therefore:

- competition carry-over must never be inferred from chronology alone;
- the collector should store official code and every explicit target row;
- a target match should be generated only when the notice explicitly identifies it or an official update supplies it;
- PK, result, lineup, or later match participation must not be used to reverse-engineer the original suspension.

## 7. Multi-match handling

The 2026-08-10 notice explicitly lists two J1 target rows for one player. A 2015 sampled notice also lists a player under two target rounds. Thus multi-match expansion is feasible when each target is present in the official page.

Safe parsing rule:

1. inherit player/team/code only across an explicit HTML continuation/rowspan structure;
2. emit one normalized record per explicit target match row;
3. preserve `target_sequence` and the raw target text;
4. reject a continuation row that cannot be tied unambiguously to its parent;
5. do not generate additional matches from the nominal suspension length.

This makes explicit multi-match notices B-level feasible. Notices that provide only a length without an explicit target cannot be expanded safely.

## 8. Match linkage strategy

The notice does not provide a J1 `match_id` or opponent. The safe candidate key is:

`target competition + target date + resolved team_id`

`target_round_raw` is a consistency check. It must not be the only key.

Read-only linkage samples against the existing J1 match datasets were unique:

| Notice sample | Exact team | Target date | Linked existing match |
|---|---|---|---|
| 2015 | 山形 (`team_0031`) | 2015-05-30 | `16921`, 名古屋 vs 山形 |
| 2015 | G大阪 (`team_0005`) | 2015-05-30 | `16925`, 横浜FM vs G大阪 |
| 2019 | 清水 (`team_0025`) | 2019-05-18 | `21594`, 大分 vs 清水 |
| 2019 | G大阪 (`team_0005`) | 2019-05-18 | `21595`, G大阪 vs C大阪 |
| 2024 | 柏 (`team_0009`) | 2024-07-20 | `30663`, 柏 vs 川崎F |
| 2024 | 東京V (`team_0028`) | 2024-07-20 | `30668`, 福岡 vs 東京V |

Production linkage would require exactly one match. Zero or multiple candidates must remain `UNRESOLVED`; fuzzy club matching and inferred opponent matching are prohibited.

## 9. TeamMaster linkage

Sampled club labels 山形、G大阪、清水、柏、東京V resolved exactly through the existing TeamMaster official aliases. No TeamMaster change is needed for the sampled records.

The future collector should resolve only through the notice's declared source namespace and exact source name. It must not trim, apply NFKC, use canonical fallback, or perform fuzzy matching silently.

## 10. Player linkage and collision safety

No stable official player ID was found in the sampled suspension notices. Therefore a future local linkage candidate is:

`season + team_id + player_name_raw`

with the uniquely linked target match retained as provenance. Raw name alone is forbidden.

Sample behavior was mixed:

- 2015 and 2019 sampled HTML used full-width spaces in Japanese full names that matched corresponding local raw names.
- 2024 J.LEAGUE.jp sampled HTML used ASCII spaces for names whose SFMS02 player records use full-width spaces. Exact string linkage therefore fails without an explicit alias.
- 東京V's 2024 local data contains multiple players sharing the same surname, demonstrating that surname-only linkage is unsafe.

No normalization-based identity resolution is allowed. A source-specific, officially evidenced alias could be added in a separate research cycle. Until then, spacing mismatches and absent local player records remain `UNRESOLVED`.

An unresolved player does not invalidate a team-level suspension count after the notice's club and target match have been resolved. It does invalidate player-minutes shares or previous-lineup linkage for that player. Missing linkage must be exposed as coverage, never interpreted as “not suspended.”

## 11. Historical coverage

Representative official notices were confirmed for 2015, 2019, and 2024. Recurring notice pages are discoverable through the official news/archive surfaces. However, the following were not established without a prohibited full crawl:

- complete number of notices per season;
- complete number of J1 suspension records;
- whether corrected/deleted notices remain discoverable;
- whether every target match is listed in an explicit row;
- historical as-of content before later edits.

Consequently, historical coverage is **unknown**, not zero and not assumed complete.

## 12. 2026/27 operational usability

Current J.LEAGUE.jp notices are published before their sampled target matches and carry publication/update metadata. An operational collector is feasible if it runs before every target kickoff and stores immutable snapshots.

Required controls:

- fetch on a fixed schedule and before each matchday;
- store raw bytes, SHA-256, request/final URL, status, `retrieved_at`, `published_at`, and `source_updated_at`;
- version a notice instead of overwriting it when `dateModified` or content hash changes;
- use only a version whose retrieval/publication time precedes target kickoff;
- require one exact TeamMaster resolution and one exact target-match resolution;
- expose unresolved player identity and record-level coverage;
- never backfill a historical pre-match feature from a later page version without an archived pre-kickoff snapshot.

This is practical for future collection but does not repair the 2015～2024 historical point-in-time gap.

## 13. Proposed future schema

No schema was implemented. A collector should at minimum preserve:

- `notice_id`
- `notice_version`
- `source_url`
- `source_page_type`
- `published_at`
- `source_updated_at`
- `retrieved_at`
- `raw_sha256`
- `player_name_raw`
- `official_player_id` (nullable)
- `club_name_raw`
- `team_id`
- `suspension_code_raw`
- `suspension_type` (nullable unless explicitly decoded)
- `target_competition_raw`
- `target_competition`
- `target_round_raw`
- `target_match_date`
- `target_match_id`
- `target_sequence`
- `resolution_status`
- `resolution_reason`
- `is_known_before_kickoff`

## 14. Workload integration proposal

If a future dataset passes the point-in-time and identity gates, it can be joined to the existing player workload dataset without using target-match lineup information.

Candidate feature group for a separate experiment:

- `suspended_player_count`
- `suspended_prev_starter_count`
- `suspended_prev_squad_count`
- `suspended_prev_starters_minutes_7d`
- `suspended_prev_starters_minutes_14d`
- `suspended_prev_starters_minutes_30d`
- `suspended_recent_minutes_share`

Only previous J1 starting XI, previous matchday squad, and lagged player minutes may be used. The target match starting XI or post-match participation is prohibited. Unresolved players require an explicit unresolved count/coverage flag and must not be included as zero-minute/non-suspended players.

No feature was calculated in this audit.

## 15. Leakage policy

A suspension record is eligible only if all of the following hold:

1. the exact notice version was published or retrieved before target kickoff;
2. the target match is explicitly identified by the notice and linked uniquely;
3. no later corrected page content is silently projected backward;
4. local player history used by a workload feature ends before target kickoff;
5. future notices, target lineup, target result, and post-match statistics are unused.

If publication time is unavailable, a conservative collector may accept the record only when the official publication date is strictly before the target date. Same-day records without a reliable timestamp must be rejected for pre-match use.

## 16. Limitations

- This was a representative audit, not a full historical crawl.
- Search discovery is not proof of complete archive coverage.
- Current HTML can differ from the page content visible at historical kickoff time.
- The 2015 and modern layouts require separate strict parsers.
- The sampled notices contain no stable player ID or match ID.
- Player name spacing differs by official surface.
- Detailed disciplinary reason and remaining-match count are not consistently available as structured fields.
- Club-specific announcements were not found to provide a more complete centralized history.

## 17. Verdict

**Overall: C — historical production feature is not safe yet.**

The official notices contain useful and often explicit suspension targets, and exact team/match linkage works in the samples. Nevertheless, historical completeness, as-of page content, publication-time consistency, and exact player linkage are insufficient for a leakage-safe 2015～2024 production feature.

**Current/future operation: B.** A snapshot collector for 2026/27 onward is worth a separate implementation task, provided it begins prospectively and preserves every pre-kickoff page version. Historical and prospective records must not be mixed under the same completeness claim.

## 18. Request discipline

- Official domains only: `jleague.jp`, `aboutj.jleague.jp`, and `data.j-league.or.jp`.
- Representative official content pages/URLs evidenced in the audit: 17.
- Search queries used to locate official routes and representative years: 16.
- Data Site route/date-selector inspection required additional technical HTTP requests; the browser/search tooling does not expose a reliable aggregate wire-request count.
- No season-wide or player-wide crawl was performed.
