# J Stats team snapshot collector: 実装前の追加監査と設計案

調査日: 2026-09-20。これは [初回 feasibility 監査](J_STATS_TEAM_SNAPSHOT_FEASIBILITY.md) の追跡調査である。対象は公式 J.LEAGUE.jp の 2026/27 J1 と比較用の 2025 J1 の少数 stat。全時系列の取得、production collector、match-level 差分、feature、prediction、model 評価は行っていない。2025 は spent test、2026/27 の70完了試合は already-opened interim lockbox であり、既存 Champion / Challenger の選択・変更には使用しない。

## 判定と確認範囲

**Implementation readiness: B — point-in-time 値を保存する collector は実装可能だが、`games_played` と公式更新時刻の特定には制約がある。** 確認した主要8 stat は2025と2026/27の両季で同じ公式 stat slug・表示ラベル・値種別のページを持つ。2026/27のシュート総数と平均支配率は、各ページ**1 HTML request**に含まれる20クラブ分の RSC data から20/20取得でき、現行 J1 日程の20クラブおよび TeamMaster の official name / slug と20/20一致した。単独 snapshot を保存できることと、連続 snapshot の差分を1試合分として安全に使えることは別である。後者に `SAFE` と判定した項目はない。

J Stats ページ自身には、標本で club 別 `games_played`、最後に反映した match ID、厳密な `source_updated_at` を確認できなかった。表示は更新**日**まで。公式の別ページ・既存日程から試合数を照合できるが、統計側の更新遅延や後日訂正を除外できない。したがって `games_played` を単純に「取得時の completed matches 数」で確定してはならない。

## 実際に観測した公式 data path と20クラブ

観測した公開 URL 例は [2026/27 J1 シュート総数](https://www.jleague.jp/j1/stats/club/2026-27/shoot/search-list/) と [平均ボール支配率](https://www.jleague.jp/j1/stats/club/2026-27/ball_rate/search-list/)。season は URL の `2026-27`、stat は `shoot` / `ball_rate` などの要素で指定される。`?club=hiroshima` は [公式の広島フィルタページ](https://www.jleague.jp/j1/stats/club/2026-27/shoot/search-list/?club=hiroshima) として既に実在を確認しているが、全クラブ取得には使わなくてよい。

HTTP GET は公開 `text/html; charset=utf-8`。サーバー応答の通常 HTML には `.m-ranking-club-list-item` が**上位10件**あり、「もっと見る」はリンクではなくボタン。ページが参照する公式 JavaScript chunk の実装を確認すると、`rankingList` 全件を client-side で `slice(0, end)` し、ボタンでは `end` を10ずつ増やす。実際の HTML 内 `self.__next_f.push`（Next.js RSC payload）の `rankingList[0].data` には最初から**20件**あり、`loadMore={max:20,end:10,step:10}`。pagination / page parameter / 追加 API request はこの2ページでは不要だった。これはページの実際の挙動の確認であり、未観測 endpoint の創作ではない。

各 RSC record には `href`, `club.code`, `club.name`, `score`, `rank` 等が含まれる。`club.code` は公式 `/club/{slug}` へのリンクと対応する URL identifier で、数値 ID や将来永続性を保証する契約ではない。HTML の10件と RSC の先頭10件のクラブ・値を照合する。RSC は**HTMLに埋め込まれた内部表現**であり、公開安定 API ではない。形式が変わったら推測で補修せず検出・停止する。

2026/27 のシュート総数20件（同日表示更新 `2026/9/14`）。これは20/20 identity と値の存在の監査用であり、予測 feature ではない。

| 公式 club code | 公式表示名 | TeamMaster `team_id` | シュート総数 |
| --- | --- | --- | ---: |
| `hiroshima` | サンフレッチェ広島 | `team_0006` | 130 |
| `kawasakif` | 川崎フロンターレ | `team_0010` | 119 |
| `kashima` | 鹿島アントラーズ | `team_0008` | 114 |
| `ftokyo` | ＦＣ東京 | `team_0003` | 110 |
| `okayama` | ファジアーノ岡山 | `team_0021` | 109 |
| `urawa` | 浦和レッズ | `team_0030` | 101 |
| `kashiwa` | 柏レイソル | `team_0009` | 99 |
| `fukuoka` | アビスパ福岡 | `team_0004` | 96 |
| `gosaka` | ガンバ大阪 | `team_0005` | 94 |
| `machida` | ＦＣ町田ゼルビア | `team_0014` | 92 |
| `nagoya` | 名古屋グランパス | `team_0018` | 87 |
| `mito` | 水戸ホーリーホック | `team_0016` | 84 |
| `kyoto` | 京都サンガF.C. | `team_0013` | 81 |
| `cosaka` | セレッソ大阪 | `team_0002` | 80 |
| `kobe` | ヴィッセル神戸 | `team_0011` | 77 |
| `yokohamafm` | 横浜Ｆ・マリノス | `team_0033` | 74 |
| `shimizu` | 清水エスパルス | `team_0025` | 73 |
| `nagasaki` | Ｖ・ファーレン長崎 | `team_0017` | 73 |
| `chiba` | ジェフユナイテッド千葉 | `team_0001` | 68 |
| `tokyov` | 東京ヴェルディ | `team_0028` | 66 |

2026/27 の平均支配率も同じ RSC 経路で**20 unique code / 20 numeric value**を取得し、[現行 J1 日程](../data/processed/jleague/2026_27/schedule.csv) の `home_club` / `away_club` union の20 code と完全一致した。20件すべてが [TeamMaster](../data/master/teams.csv) の `source=jleague_official` において**exact な公式名 + `source_club_id`**で一意に解決した。fuzzy / NFKC / canonical fallback や TeamMaster 変更はしていない。

## 2025 / 2026-27 stat と route の互換性

下表のリンクは実際に確認した公式詳細ページ。今回新たに取得したページは title、season、`rankingList[0].stats.value` / label、データ件数まで検証した。「初回監査で値確認」としたページは[初回文書](J_STATS_TEAM_SNAPSHOT_FEASIBILITY.md)の確認範囲であり、今回あらためて全20件を検証したという意味ではない。2025 は `2025/12/8 更新`、2026/27 は `2026/9/14 更新` の表示。`○` は値のあるページであり、過去の中途時点 snapshot の保存や同じデータ生成方法を保証しない。2026 の特別シーズン `/2026/` と 2026/27 `/2026-27/` を混同しない。

| stat slug | 2025 route | 2025 available | 2026-27 route | 2026-27 available | value type | same semantic meaning / notes |
| --- | --- | --- | --- | --- | --- | --- |
| `shoot` | [2025/shoot](https://www.jleague.jp/j1/stats/club/2025/shoot/search-list/) | ○ 20件 | [2026-27/shoot](https://www.jleague.jp/j1/stats/club/2026-27/shoot/search-list/) | ○ 20件 | `total`, 回 | 同じ「シュート総数」。計測定義の内部改定は未監査 |
| `suffer_shoot_on_target` | [2025/suffer_shoot_on_target](https://www.jleague.jp/j1/stats/club/2025/suffer_shoot_on_target/search-list/) | ○ 20件 | [2026-27/suffer_shoot_on_target](https://www.jleague.jp/j1/stats/club/2026-27/suffer_shoot_on_target/search-list/) | ○ 初回監査で値確認 | `total`, 回 | 同じ「被枠内シュート総数」。自軍の攻撃側 SOT と区別 |
| `ball_rate` | [2025/ball_rate](https://www.jleague.jp/j1/stats/club/2025/ball_rate/search-list/) | ○ 20件 | [2026-27/ball_rate](https://www.jleague.jp/j1/stats/club/2026-27/ball_rate/search-list/) | ○ 20件 | `percentage`, % | 同じ「平均ボール支配率」。表示小数1桁、算出分母は未検証 |
| `pass_count` | [2025/pass_count](https://www.jleague.jp/j1/stats/club/2025/pass_count/search-list/) | ○ 初回監査で値確認 | [2026-27/pass_count](https://www.jleague.jp/j1/stats/club/2026-27/pass_count/search-list/) | ○ 20件 | `total`, 回 | 同じ「パス総数」 |
| `pass_count_per_game` | [2025/pass_count_per_game](https://www.jleague.jp/j1/stats/club/2025/pass_count_per_game/search-list/) | ○ 20件 | [2026-27/pass_count_per_game](https://www.jleague.jp/j1/stats/club/2026-27/pass_count_per_game/search-list/) | ○ 初回監査で値確認 | `average`, 回/試合 | 同じ「1試合平均パス数」。小数1桁に丸め |
| `distance_per_game` | [2025/distance_per_game](https://www.jleague.jp/j1/stats/club/2025/distance_per_game/search-list/) | ○ 20件 | [2026-27/distance_per_game](https://www.jleague.jp/j1/stats/club/2026-27/distance_per_game/search-list/) | ○ 初回監査で値確認 | `average`, km/試合 | 同じ「1試合平均走行距離」。表示は整数 km |
| `sprint_per_game` | [2025/sprint_per_game](https://www.jleague.jp/j1/stats/club/2025/sprint_per_game/search-list/) | ○ 20件 | [2026-27/sprint_per_game](https://www.jleague.jp/j1/stats/club/2026-27/sprint_per_game/search-list/) | ○ 初回監査で値確認 | `average`, 回/試合 | 同じ「1試合平均スプリント回数」。表示は整数。閾値等の定義互換性は別途確認が必要 |
| `expected_goals` | [2025/expected_goals](https://www.jleague.jp/j1/stats/club/2025/expected_goals/search-list/) | ○ 初回監査で値確認 | [2026-27/expected_goals](https://www.jleague.jp/j1/stats/club/2026-27/expected_goals/search-list/) | ○ 20件、広島 `16.1` | `unknown`（season累積に見える小数1桁） | 同じ「ゴール期待値」だが、ページ上に `total` の明記・モデル改定情報なし |

2025 の `/2025/distance_per_game/` のような overview URL は検索結果によって「データなし」と表示される例がある。一方、上表の明示的な `/search-list/` 詳細 URL では20件を取得した。**HTTP 200 だけを available の判定に使わず、title・season・選択 stat・数値件数を検証**する。ランキングの `score` は単位を取り除いた numeric 値なので、表示 `%` / `km` と stat 定義を合わせて解釈する。

追加の最優先調査結果:

| stat | 2025 | 2026/27 | 意味・注意 |
| --- | --- | --- | --- |
| xGA `expected_goals_against` | [公式ページ](https://www.jleague.jp/j1/stats/club/2025/expected_goals_against/search-list/) 20件（先頭: 湘南 `57.3`） | [公式ページ](https://www.jleague.jp/j1/stats/club/2026-27/expected_goals_against/search-list/) 20件（先頭: C大阪 `13.6`） | 「被ゴール期待値」。累積らしいが total 明記なし、小数1桁 |
| 攻撃側 SOT `shoot_on_target` | **今回は実ページ未確認** | [公式ページ](https://www.jleague.jp/j1/stats/club/2026-27/shoot_on_target/search-list/) 20件（先頭: 広島 `48`） | 「枠内シュート総数」。`suffer_shoot_on_target` とは別の stat |

攻撃側 SOT は直接の公式 stat が2026/27に確認できたため、相手側の「被枠内シュート」を対戦カードから換算する必要はない。2025 に同 route があるとは、今回の検証なしに断定しない。xG/xGA の選択肢と攻撃側 SOT の選択肢は公式ページの filter data に実在し、上記の URL は実際の HTTP 応答・title・ranking を確認してから採用した。

## Games played と更新時点

- J Stats 標本のページ・RSC では `games_played` / 最終反映 match ID / round を**直接確定できなかった**。`rankingList` はスコアと順位を持つが、試合数は持たない。`number_of_games_played` などの翻訳用文字列が HTML にあっても、そのクラブの現値と見なさない。
- J Stats は `2026/9/14 更新`、2025ページは `2025/12/8 更新` と**日付**を表示する。2026/27 シュート総数ページの HTTP 応答に `Last-Modified` header はなく、標本の meta tag に正確な update timestamp はなかった。`source_updated_date_jst` は取れるが、`source_updated_at`（日時）は未確認で null。`retrieved_at` は collector の実際の UTC 取得日時として別に保存する。
- [2026/27 J1 の公式順位表](https://www.jleague.jp/j1/standings/) には試合数の欄があり、標本では `2026/9/13 更新`、柏・広島等は7試合。一方、[既存の completed history](../data/processed/jleague/2026_27/completed_matches.csv) は70試合、最終日9/13、20クラブすべて7 appearance。J Stats 側の柏の `pass_count=4399` と `pass_count_per_game=628.4` は `4399/7≈628.4` で整合する。これは**7試合時点らしいという照合結果**であって、J Stats から公式に付された `games_played=7` ではない。
- 順位表・日程・J Stats の更新 cadence は独立。更新日だけ一致しても、特定クラブの延期試合や後日修正まで同期したとは言えない。したがって games played availability は **B: schedule/standings 照合で推定可能だが update lag risk あり**。推定値を公式確定値として永続保存しない。
- 次の収集では `retrieved_at`、`source_updated_date_jst`、raw page hash と、必要なら別々に確認した `schedule_completed_count_at_retrieval` / 根拠 URL を分ける。統計の反映試合数が不明なら snapshot schema の `games_played` は **null** にし、既知の別ソース推定値と混ぜない。

## Snapshot schema / raw cache 設計案（未実装）

| field | 型・扱い |
| --- | --- |
| `snapshot_id` | 取得イベントを一意に識別する ID。再取得・訂正時にも別イベントを保持 |
| `retrieved_at` | collector 側で記録する UTC datetime、必須 |
| `source_updated_at` | 公式が時刻まで公表する場合のみ datetime。現行 J Stats では **null** |
| `competition`, `season` | `j1`, `2026-27` のように分離。`2026` 特別シーズンと混ぜない |
| `team_id` | TeamMaster exact 解決済み ID、必須 |
| `official_club_id`, `official_club_name` | 観測した `/club/{slug}` の slug と raw 公式表示名 |
| `games_played` | 公式 stat と同時点と証明できる場合のみ整数。現状 **null** |
| `stat_name`, `stat_value` | 公式 filter の stat slug と数値。raw 表示は別途保持すると再監査しやすい |
| `value_type`, `unit` | `total` / `average` / `rate` / `percentage` / `unknown`、および回・回/試合・%・km/試合など |
| `source_url` | 実際に取得した公式詳細ページ URL |

追加の provenance 列候補は `source_updated_date_jst`（表示日付を時刻なしで保持）、`raw_value`、`raw_sha256`、`games_played_basis`、`retrieval_status`。これらは上記の必須 draft を置き換えず、`source_updated_at` に架空の `00:00` を入れないための補助列である。

raw cache 案（今回ディレクトリは作らない）:

```text
data/raw/jstats_team_snapshots/YYYYMMDD_HHMMSS/{season}/{stat_name}.html
data/raw/jstats_team_snapshots/YYYYMMDD_HHMMSS/{season}/{stat_name}.metadata.json
data/processed/jstats_team_snapshots/team_stats_snapshots.csv
```

metadata は requested/final URL、HTTP status、content type、`retrieved_at_utc`、bytes、SHA256、表示更新日、必要なら response headers を保持する。1ページに20クラブ分を含むため、同一取得の20 rows は同じ `snapshot_id` / raw hash を共有する設計が自然。実装時は HTML 先頭10件と RSC 20件の一致、20 unique club、TeamMaster exact identity、season / stat title と `rankingList.stats.value` の一致、欠損・非数値を hard failure / diagnostic にする。RSC 構造は非契約のため schema drift を必ず検出する。

## 差分安全性と stat allowlist 候補

**Snapshot capture allowlist 候補**（2026/27 で公式の値を確認したもの）: `shoot`, `suffer_shoot_on_target`, `shoot_on_target`, `pass_count`, `pass_count_per_game`, `ball_rate`, `distance_per_game`, `sprint_per_game`, `expected_goals`, `expected_goals_against`。これは**生の point-in-time snapshot 保存だけ**を許す候補で、match-level delta や予測投入の承認ではない。2025 との互換が実際に確認できたのは前節の8 stat と xGA。攻撃側 SOT の2025は未確認。

| 分類 | stat | 理由 |
| --- | --- | --- |
| `SAFE` | **該当なし** | 連続する2時点の snapshot と、反映済み match を1対1で対応させる検証をしていない |
| `POSSIBLE_WITH_CAUTION` | `shoot`, `suffer_shoot_on_target`, `shoot_on_target`, `pass_count` | 整数 total。間に同クラブの対象 J1 match がちょうど1つ反映され、訂正なし・同一定義なら差分候補。2試合以上なら合算のみ |
| `POSSIBLE_WITH_CAUTION` | `expected_goals`, `expected_goals_against` | season累積に見えるが total 明記がなく、表示は小数1桁。確認後も差分は丸め誤差を持ち、exact match xG とは言えない |
| `NOT_SAFE_YET` | `pass_count_per_game`, `distance_per_game`, `sprint_per_game` | 同時点 `games_played` と未丸め total がない。平均の単純差分は無意味。`average×games` も丸め誤差を増幅 |
| `NOT_SAFE_YET` | `ball_rate` | percentage の単純差分は禁止。分子/分母・集計方式が未確認 |

2026/27 xG/xGA が利用可能という今回の発見は、**既存70試合の選択・評価のやり直しを正当化しない**。将来の collector が取得した時刻以前の値を「当時公開されていた」と遡って扱うことも禁止。

## Request strategy、残課題、次の gate

今回の直接 HTTP GET は**29件**（公式 HTML 17、同ページで実際に参照された公式 JS chunk 12）。検索・閲覧ツールでの公式ページ表示2件は別途行ったが、内部の cache / network 挙動は不明。全クラブ×全 stat の crawl はしていない。将来の collector は1 stat につき原則1ページで20クラブを検証し、低頻度で取得する。club 別20 requests は不要。`?club=` は不具合調査用の明示的な fallback 候補に留める。RSC が消えた場合や20クラブが揃わない場合、非公式 endpoint の推測や無検証の fallback は行わない。

次の実装/運用前 gate: (1) 20件が継続して揃うか、(2) `games_played` の source と J Stats 更新ラグの安全な扱い、(3) raw snapshot の再取得・訂正時の保存方針、(4) xG/xGA の累積 semantics と定義改定、(5) 利用条件・自動取得許容範囲。まず snapshot を蓄積し、後から match-level 差分を検証する。日程だけから同時点を断定しない。既存 [DATA_PIPELINE_STATUS.md](DATA_PIPELINE_STATUS.md) の match-level stats placeholder 問題は別系統であり、本件のクラブ統計で解消したとはみなさない。production code、データ CSV、cache directory、TeamMaster は今回変更していない。

## 2026-09-14 source state の補完 snapshot

2026-09-21 に、公式表示更新日が引き続き `2026/9/14 更新` である間に追加 stat を保存した。これは「第7節確定値」ではなく、**source display update date = 2026-09-14 の point-in-time snapshot**である。統計ページ自身から集計対象試合数を確定できないため、全行の `games_played` と `source_updated_at` は null のままとした。平均値から total を逆算せず、match-level delta reconstruction、feature、prediction、model 評価も行っていない。

- base snapshot: `20260920T212008928504Z`（既存10 stat、未変更）
- supplemental snapshot: `20260921T044103287576Z`（追加27 stat、540 rows）
- raw: `data/raw/jstats_team_snapshots/20260921T044103287576Z/`
- processed: `data/processed/jstats_team_snapshots/20260921T044103287576Z.csv`
- manifest: `related_snapshot_id=20260920T212008928504Z`, `source_state_date=2026-09-14`, `status=COMPLETE`
- identity: 各 stat 20 clubs、TeamMaster `jleague_official` name + slug exact 20/20

既存HTMLの公式 stat filterには62 optionsがあり、既存10を除く追加 route candidate は52だった。候補を無差別取得せず、意味・単位が明確で情報の重複が比較的小さいPriority A/Bを中心に検証した。下表の「20」は実ページのRSC rankingを取得・検証したもの、「未取得」は公式filterにroute候補があることだけを確認したものである。

### 保存した追加 stat

| slug | label | value type | unit | clubs | source update | saved | reason |
| --- | --- | --- | --- | ---: | --- | --- | --- |
| `cross_count` | クロス総数 | total | 回 | 20 | 2026-09-14 | yes | 明確な攻撃量 |
| `chance_create` | チャンスクリエイト総数 | total | 回 | 20 | 2026-09-14 | yes | 公式定義あり |
| `suffer_shoot` | 被シュート総数 | total | 回 | 20 | 2026-09-14 | yes | 明確な被攻撃量 |
| `clear_count` | クリア総数 | total | 回 | 20 | 2026-09-14 | yes | 公式定義あり |
| `tackle_count` | タックル総数 | total | 回 | 20 | 2026-09-14 | yes | 公式定義あり |
| `tackle_rate` | タックル成功率 | percentage | % | 20 | 2026-09-14 | yes | 公式定義あり。逆算禁止 |
| `block_count` | ブロック総数 | total | 回 | 20 | 2026-09-14 | yes | 公式定義あり |
| `intercept_count` | インターセプト総数 | total | 回 | 20 | 2026-09-14 | yes | 公式定義あり |
| `recovery_count` | こぼれ球奪取数 | total | 回 | 20 | 2026-09-14 | yes | 公式定義あり |
| `expected_goals_against_excl_pk` | 被ゴール期待値 ※PKを除く | unknown | — | 20 | 2026-09-14 | yes | xGA関連の観測値。集計単位は断定しない |
| `dribble_count` | ドリブル総数 | total | 回 | 20 | 2026-09-14 | yes | 公式定義あり |
| `dribble_rate` | ドリブル成功率 | percentage | % | 20 | 2026-09-14 | yes | 公式定義あり。逆算禁止 |
| `air_battle_win_count` | 空中戦勝利数 | total | 回 | 20 | 2026-09-14 | yes | 公式定義あり |
| `air_battle_win_rate` | 空中戦勝率 | percentage | % | 20 | 2026-09-14 | yes | 公式定義あり。逆算禁止 |
| `one_on_one` | 1vs1勝利総数 | total | 回 | 20 | 2026-09-14 | yes | 公式filter上の明確な指標 |
| `at_sprint_per_game` | 1試合平均Atスプリント回数 | average | 回/試合 | 20 | 2026-09-14 | yes | tracking detail。平均の逆算禁止 |
| `mt_sprint_per_game` | 1試合平均Mtスプリント回数 | average | 回/試合 | 20 | 2026-09-14 | yes | tracking detail。平均の逆算禁止 |
| `dt_sprint_per_game` | 1試合平均Dtスプリント回数 | average | 回/試合 | 20 | 2026-09-14 | yes | tracking detail。平均の逆算禁止 |
| `possession_distance_per_game` | 1試合平均ポゼッション時の走行距離 | average | km/試合 | 20 | 2026-09-14 | yes | tracking detail。平均の逆算禁止 |
| `possession_sprint_per_game` | 1試合平均ポゼッション時のスプリント回数 | average | 回/試合 | 20 | 2026-09-14 | yes | tracking detail。平均の逆算禁止 |
| `un_possession_distance_per_game` | 1試合平均被ポゼッション時の走行距離 | average | km/試合 | 20 | 2026-09-14 | yes | tracking detail。平均の逆算禁止 |
| `un_possession_sprint_per_game` | 1試合平均被ポゼッション時のスプリント回数 | average | 回/試合 | 20 | 2026-09-14 | yes | tracking detail。平均の逆算禁止 |
| `pass_rate` | パス成功率 | percentage | % | 20 | 2026-09-14 | yes | 明確なpass detail。逆算禁止 |
| `through_pass_count` | スルーパス総数 | total | 回 | 20 | 2026-09-14 | yes | 公式定義あり |
| `through_pass_rate` | スルーパス成功率 | percentage | % | 20 | 2026-09-14 | yes | 公式定義あり。逆算禁止 |
| `foul_count` | ファウル総数 | total | 回 | 20 | 2026-09-14 | yes | discipline stat |
| `yellow_count` | 警告数 | total | 枚 | 20 | 2026-09-14 | yes | discipline stat |

### 保存しなかった追加 route candidate

| slug | label | value type / unit | clubs | source update | saved | reason |
| --- | --- | --- | ---: | --- | --- | --- |
| `shoot_per_game` | 1試合平均シュート数 | average / 回/試合 | 未取得 | 未検証 | no | 既存totalとの重複が大きい |
| `shoot_on_target_per_game` | 1試合平均枠内シュート数 | average / 回/試合 | 未取得 | 未検証 | no | 既存totalとの重複が大きい |
| `shoot_rate` | シュート決定率 | percentage / % | 未取得 | 未検証 | no | 得点・shootから派生する率 |
| `score` | 得点総数 | total / 点 | 未取得 | 未検証 | no | 公式match resultから既取得 |
| `score_per_game` | 1試合平均得点数 | average / 点/試合 | 未取得 | 未検証 | no | resultと重複しgames basis不明 |
| `cross_count_per_game` | 1試合平均クロス数 | average / 回/試合 | 未取得 | 未検証 | no | 保存したtotalと重複 |
| `chance_create_per_game` | 1試合平均チャンスクリエイト数 | average / 回/試合 | 未取得 | 未検証 | no | 保存したtotalと重複 |
| `suffer_shoot_per_game` | 1試合平均被シュート数 | average / 回/試合 | 未取得 | 未検証 | no | 保存したtotalと重複 |
| `suffer_shoot_on_target_per_game` | 1試合平均被枠内シュート数 | average / 回/試合 | 未取得 | 未検証 | no | 既存totalと重複 |
| `lost` | 失点総数 | total / 点 | 未取得 | 未検証 | no | 公式match resultから既取得 |
| `lost_per_game` | 1試合平均失点数 | average / 点/試合 | 未取得 | 未検証 | no | resultと重複しgames basis不明 |
| `clear_count_per_game` | 1試合平均クリア数 | average / 回/試合 | 未取得 | 未検証 | no | 保存したtotalと重複 |
| `tackle_count_per_game` | 1試合平均タックル数 | average / 回/試合 | 未取得 | 未検証 | no | 保存したtotalと重複 |
| `block_count_per_game` | 1試合平均ブロック数 | average / 回/試合 | 未取得 | 未検証 | no | 保存したtotalと重複 |
| `intercept_count_per_game` | 1試合平均インターセプト数 | average / 回/試合 | 未取得 | 未検証 | no | 保存したtotalと重複 |
| `recovery_count_per_game` | 1試合平均こぼれ球奪取数 | average / 回/試合 | 未取得 | 未検証 | no | 保存したtotalと重複 |
| `expected_goals_against_per_game` | 1試合平均被ゴール期待値 | average / 不明 | 未取得 | 未検証 | no | 既存xGAと重複しgames basis不明 |
| `apt_pg_rank` | 1試合平均アクチュアルプレーイングタイム(APT) | average / 不明 | 未取得 | 未検証 | no | ranking slugと値の単位を安全に確定していない |
| `dribble_count_per_game` | 1試合平均ドリブル数 | average / 回/試合 | 未取得 | 未検証 | no | 保存したtotalと重複 |
| `air_battle_win_count_per_game` | 1試合平均空中戦勝利数 | average / 回/試合 | 未取得 | 未検証 | no | 保存したtotalと重複 |
| `one_on_one_per_game` | 1試合平均1vs1勝利数 | average / 回/試合 | 未取得 | 未検証 | no | 保存したtotalと重複 |
| `through_pass_count_per_game` | 1試合平均スルーパス数 | average / 回/試合 | 未取得 | 未検証 | no | 保存したtotalと重複 |
| `foul_count_per_game` | 1試合平均ファウル数 | average / 回/試合 | 未取得 | 未検証 | no | 保存したtotalと重複 |
| `clean_sheet` | クリーンシート総数 | total / 試合 | 17 | 2026-09-14 | no | 0値クラブを含む20件を返さずstrict completeness不成立 |
| `red_count` | 退場数 | total / 枚 | 6 | 2026-09-14 | no | 0値クラブを含む20件を返さずstrict completeness不成立 |

最初の取得は `clean_sheet=17` で、次の補完試行は `red_count=6` でそれぞれhard failureとなった。両runは raw HTML と `status=INCOMPLETE` manifestだけを保持し、processed CSVを作っていない。成功したページは再requestせずcacheから正式snapshotへコピーしたため、公式HTTP requestは追加候補29 unique routeに対する29回だった。正式snapshotは27/27 statが20 clubs、同一更新日、重複 `(team_id, stat_name)` なしの場合だけpublishされた。
