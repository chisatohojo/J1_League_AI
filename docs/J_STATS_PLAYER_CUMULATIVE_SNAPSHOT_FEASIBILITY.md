# J Stats player cumulative snapshot feasibility

調査日: 2026-09-24 (JST)

## Conclusion

総合判定は **DEFER**。J.LEAGUE.jp の選手 season-ranking route には、選手ごとの累積値、クラブ表示、選手 profile URL、表示更新日が存在する。しかし、過去の任意時点へ戻る point-in-time snapshot route、履歴化された更新版、または公式の更新時刻を再現する仕組みは確認できなかった。したがって、現状の資料だけで retrospective な選手累積履歴を安全に作ることはできない。

一方、将来の公開時点で append-only に保存する prospective collector は、取得時刻と公式表示更新日を別々に保存し、同一ページ状態の全statを一括取得する設計なら **条件付きで進められる候補**である。production collectorの実装承認ではない。

今回、model fitting、prediction、metric calculation、feature selection、broad historical crawlは行っていない。

## Scope and sources

確認した既存資料・local source:

- `src/collect/jstats_team_snapshots.py`
- `src/collect/jstats_previous_season_profiles.py`
- `data/raw/jstats_team_snapshots/`
- `data/raw/jstats_previous_season_profiles/`
- `docs/J_STATS_HISTORICAL_DATA_INVENTORY.md`
- `docs/J_STATS_TEAM_SNAPSHOT_FEASIBILITY.md`
- `docs/J_STATS_SNAPSHOT_DELTA_FEASIBILITY.md`
- `docs/JLEAGUE_PLAYER_IDENTITY_FEASIBILITY.md`
- `docs/SFMS02_PLAYER_MINUTES_FEASIBILITY.md`
- `docs/PLAYER_WORKLOAD_FEATURE_DATASET.md`
- `docs/JLEAGUE_SUSPENSION_DATA_FEASIBILITY.md`

Local cacheにはteam rankingとprevious-season team profileのraw HTMLは存在するが、player cumulative rankingのraw cacheは確認できなかった。

少数の公式サンプルとして、以下のJ.LEAGUE.jp routeを確認した。

- [2024 player stats overview](https://www.jleague.jp/j1/stats/player/2024/)
- [2024 expected goals](https://www.jleague.jp/j1/stats/player/2024/expected_goals/search-list/)
- [2024 expected goals excl. penalties](https://www.jleague.jp/j1/stats/player/2024/expected_goals_excl_pk/search-list/)
- [2024 minutes](https://www.jleague.jp/j1/stats/player/2024/time/search-list/)
- [2025 minutes](https://www.jleague.jp/j1/stats/player/2025/time/search-list/)
- 2024 sample player profile linked from the ranking (`/player/1604106/`)
- existing local 2026/27 team snapshot route and documentation

2026/27については、既存のteam snapshotとは別に、選手profileの現行表示例を確認した。2026/27の数値は現在時点値であり、過去の各match時点の値ではない。

## Representative samples

| season | sample | observation |
|---|---|---|
| 2024 | player ranking: expected goals, expected goals excl. PK, minutes; linked player profile | ranking row has player name, club, value, and profile URL; page displays `2024/12/10` update date. The profile page exposes a numeric `/player/{id}/` identifier and career/competition sections. |
| 2025 | minutes ranking | same official player-ranking route and a season-final display update date (`2025/12/8` in the observed page). |
| 2026/27 | current player profile reached from official player route | current-season profile and update timestamp are displayed, but this is not a historical snapshot and does not establish complete current-season ranking coverage. |

移籍経験者について、既存の公式 identity auditでは、公式Data Siteのnumeric `player_id`が複数season・クラブの年度別成績に継続する例を確認している。ただしこれはJ Stats rankingの全rowをSFMS02へ結ぶcrosswalkの証明ではない。SFMS02側には選手IDがなく、raw nameだけでの横断joinは禁止する。

## Identity audit

| item | finding | grade |
|---|---|---|
| player stable identifier | J.LEAGUE.jp ranking rowから `/player/{numeric_id}/` profile linkを取得できる sample がある | B |
| club identity | rowにクラブ表示があり、team-level sourceのofficial club identityとは別namespace。TeamMasterへ自動追加・自動joinは未実施 | B |
| season identity | URLと表示ページがseasonを持つ。season rankingの値としては識別可能 | A/B |
| cross-season ID stability | official Data Site profileの年度別実績で継続例は確認済み。J Stats row全体のlongitudinal coverageは未証明 | B |
| transfer ID stability | official profileのcareer/年度別実績で同一人物の移籍履歴を表示する例はあるが、J Stats rankingと全選手のjoinを検証していない | B / partial |
| name-only linkage | unsafe; same-name collisions and display-name changes are documented in existing identity audit | C |

stable player IDが見えることと、2015–2026/27の全選手rowをそのIDで安全に連結できることは別である。SFMS02のmatch-local raw nameをJ Stats profileへ推測で対応付けない。

## Observed field inventory

以下は公式ページで意味と値の表示を確認できたfieldである。source keyはURLで明示されるstat slugを採用し、ページにない内部keyは推測しない。

| official field | source key / route example | unit | semantics | null / coverage finding |
|---|---|---|---|---|
| 出場時間 | `time` | 分 | season cumulative | 2024/2025 sampleで値あり。未出場・対象外行のnull semanticsは全件監査していない |
| 得点数 | `score` | goals | season cumulative | overview routeで値あり。full historical snapshot coverageは未監査 |
| アシスト | `assist`相当の表示 | assists | season cumulative | overviewで表示を確認。stable source keyと全season coverageは未確定 |
| ゴール期待値 | `expected_goals` | official display decimal; unit not separately stated | season cumulative-looking player total | 2019–2025 route coverageは既存inventoryで確認。内部precision・restatementは不明 |
| ゴール期待値（PK除く） | `expected_goals_excl_pk` | official display decimal | season cumulative-looking | 2019–2025 route coverageは既存inventoryで確認。penalty handlingはlabelの範囲のみ確定 |
| デュエル勝利数 | overview displayed stat | count | season cumulative-looking | sample field exists; route/key and historical completeness未確認 |
| 総走行距離 | `distance`系表示 | km | season cumulative-looking | sample field exists; unit表示あり。全season coverage未確認 |
| 総スプリント回数 | `sprint`系表示 | count | season cumulative-looking | sample field exists。全season coverage未確認 |

Passing、defensive actions、starts、xGA、rate/per-match fieldsについては、今回の少数sampleから公式key・unit・null semantics・全season coverageを確定しなかった。推測mappingは行わない。特に「表示されるoverview stat」と「個別ranking routeのstable source key」は同一と仮定しない。

既存inventory上のplayer ranking coverageは、2018から通常stats、xG/npxGは2019からである。2015–2017の同型routeはHTTP 200でもranking rowsがないため、少なくともこのrouteの利用開始は2018/2019以降となる。

## Point-in-time and timestamp audit

- season pageはseason-finalまたは現在取得時点の累積値であり、同seasonの過去match前の値ではない。
- 公式ページは更新日を表示する。2024/2025 sampleでは日付を確認できたが、正確な更新時刻は確認できない。
- `retrieved_at`はcollector側で保存可能だが、source-side update timeとは別物である。
- URLにround、matchday、as-of date、snapshot revisionを指定する仕組みは既存監査で確認できなかった。
- 過去ページが後日restatementされる可能性があり、現在取得したseason-final値を当時の途中値と扱ってはならない。
- historical final totalをhistorical pre-match featureへ使用してはならない。

従って、historical point-in-time snapshots: **No evidence / not available**。Prospective append-only snapshot path: **Yes, conditional**。各取得について `snapshot_id`, `retrieved_at`, displayed `source_updated_date`, source URL, raw hash, season, competition, player ID, club identity, stat key/valueをimmutableに保存し、全statが同一source stateであることを検証する必要がある。

## Coverage and access

| dimension | result |
|---|---|
| 2024 | player ranking and profile sample confirmed; existing inventory: 508 `shoot` rows, 509 xG/npxG rows |
| 2025 | player ranking sample confirmed; existing inventory: 512 xG rows and 512 `shoot` rows |
| current 2026/27 | individual current profile sample confirmed; full ranking/sample coverage not established |
| public access | official public HTML/page data is viewable in samples; login was not required for observed pages |
| paid/API key | not observed; no official public API contract for player cumulative snapshots was established |
| rate/terms | sample-level access policy and update cadence are visible; bulk automated collection limits and commercial terms were not established |
| historical as-of retrieval | not found |

The update notice on the official pages states that J1 data is updated one to two days after a match. This describes publication cadence, not a reproducible historical snapshot mechanism.

## Safe downstream use

If a prospective collector is later approved:

1. Capture only after the source update state is visible and record that state separately from retrieval time.
2. Use only a prior snapshot for a target match; never use the target match's post-match cumulative value.
3. Require official stable player ID and explicit club/season identity. Do not use name-only joins.
4. Keep cumulative, rate, per-match, and null values as distinct semantics.
5. Store missingness explicitly; do not convert absent rows to zero.
6. Treat later retrievals as new immutable snapshots, never overwriting an earlier snapshot.

## Verdict by item

| item | verdict |
|---|---|
| stable player identity in source | **B**: profile IDs are observable, but complete historical row linkage is unproven |
| club/season identity | **B**: visible in ranking/profile samples, namespace crosswalk remains required |
| cumulative player statistics | **B**: several season cumulative fields are publicly displayed |
| source update timestamp | **B**: update date available, exact timestamp unavailable |
| historical point-in-time snapshots | **C**: no documented as-of route or revision history |
| prospective append-only snapshots | **B**: technically viable with strict immutable capture and coverage gates |

## Final decision

**DEFER** historical/production use for now. A separate, narrowly scoped prospective collector feasibility step may proceed later, beginning with one complete current-season stat family and an explicit player-ID/club-ID schema. No collector is authorized by this audit, and no player identity mapping or feature dataset was created.

## Request / evidence note

No local cache was modified and no production data was generated. Official sample pages were inspected through the web research tool; its internal wire-level request count is not exposed, so an exact HTTP request count cannot be asserted. The work was limited to the representative official pages listed above; no bulk crawl was performed.

