# J Stats クラブ統計の point-in-time snapshot 実現性監査

調査日: 2026-09-20。対象は J.LEAGUE.jp 公式の J1 クラブ統計、主に 2026/27 と比較用の 2025。少数の公式ページと既存 TeamMaster だけを確認した。全クラブ・全統計・時系列の coverage 監査ではない。collector、feature、prediction、model 評価は実行していない。

## 結論

**B: 一部 stat の point-in-time snapshot collector は設計可能。ただし、この監査だけで match-level 差分を安全に復元できる stat は確定していない。** 少なくともシュート総数、被枠内シュート総数、パス総数（2025）、平均パス数・支配率・走行距離・スプリント数（2026/27）は公式 HTML に値がある。一方、優先度の高い 2026/27 J1 の xG/xGA、攻撃側の枠内シュート数、タックルは今回の公式ページ標本では確認できなかった。「未確認」は「存在しない」を意味しない。ランキング初期表示が10クラブであること、更新日と試合消化数の紐付け、前後2 snapshot の実測比較も未解決である。

2025 は既に spent test、2026/27 の既完了70試合は already-opened interim lockbox であり、本調査の値を既存 Champion / Challenger の選択や改変に用いない。新しい情報層は別 research cycle とする。既存の状況と優先順位は [PROJECT_STATUS_2026_09_20.md](PROJECT_STATUS_2026_09_20.md)、[DATA_PIPELINE_STATUS.md](DATA_PIPELINE_STATUS.md)、[NEXT_DATA_RESEARCH_ROADMAP.md](NEXT_DATA_RESEARCH_ROADMAP.md) に従う。

## 観測した公式 source と data path

| 目的 | 実際に確認した URL | 観測内容 |
| --- | --- | --- |
| 2026/27 J1 クラブ統計入口 | [club ranking](https://www.jleague.jp/j1/stats/club/) | パス、支配率、走行距離、スプリント等の上位表示。表示更新日 2026/9/14。 |
| 2026/27 統計カテゴリ | [平均パス数](https://www.jleague.jp/j1/stats/club/2026-27/pass_count_per_game/search-list/)、[平均支配率](https://www.jleague.jp/j1/stats/club/2026-27/ball_rate/search-list/)、[平均走行距離](https://www.jleague.jp/j1/stats/club/2026-27/distance_per_game/search-list/)、[平均スプリント](https://www.jleague.jp/j1/stats/club/2026-27/sprint_per_game/search-list/) | URL の `/2026-27/{stat}/search-list/` が season / stat の指定として実在。 |
| 2026/27 整数 total | [シュート総数](https://www.jleague.jp/j1/stats/club/2026-27/shoot/search-list/)、[被枠内シュート総数](https://www.jleague.jp/j1/stats/club/2026-27/suffer_shoot_on_target/search-list/)、[クリーンシート総数](https://www.jleague.jp/j1/stats/club/2026-27/clean_sheet/search-list/) | 「被枠内」は相手から受けた枠内シュートであり、自チームの攻撃側 SOT ではない。 |
| club 指定 | [広島の2026/27シュート総数](https://www.jleague.jp/j1/stats/club/2026-27/shoot/search-list/?club=hiroshima)、[横浜FMの2025シュート総数](https://www.jleague.jp/j1/stats/club/2025/shoot/search-list/?club=yokohamafm) | 実在する `?club={official_slug}` のフィルタ。全クラブの全 stat で使えるかは未確認。 |
| 2025 同系統ページ | [xG](https://www.jleague.jp/j1/stats/club/2025/expected_goals/search-list/)、[パス総数](https://www.jleague.jp/j1/stats/club/2025/pass_count/search-list/) | `/2025/{stat}/search-list/` の実在とランキング表示を確認。2025 値はシーズン終盤・終了後の表示であり、当時の中途 snapshot ではない。 |
| club identity | [広島公式クラブページ](https://www.jleague.jp/club/hiroshima/) | ランキングのクラブ URL と同じ公式 slug。 |

上記各ページは HTTP GET の公開 `text/html; charset=utf-8` として閲覧可能だった。直接取得した標本では Next.js の `self.__next_f.push` スクリプトがあったが、値は JavaScript 実行後に初めて現れるのではなく、サーバー応答 HTML 内のランキング要素にも存在した。実際に観測した要素は `a.m-ranking-club-list-item__link[href^="/club/"]` の子 `div.m-ranking-club-list-item` で、後者の `name`, `ranking`, `score` 属性および表示テキストにクラブ名・順位・値があった。これは少なくとも標本ページで HTML から機械的に読めるという意味であり、**公式の安定した structured API を特定したわけではない**。未観測 API URL を推測していない。

詳細 ranking の初期 HTML には標本で10クラブ分だけが現れた。「もっと見る」の後続データ経路と全20クラブの取得・欠損判定は未監査。club フィルタの存在は確認したが、全 stat・全クラブでの網羅性を保証しない。ランキングの `score` 属性だけを永続 schema と見なさず、将来実装する際は見出し・season・club slug・表示値の整合を検証する必要がある。

公式ページの案内は J1 統計を**試合翌日～2日後**に更新するとしている。表示される `2026/9/14 更新` は日付であり、厳密な更新時刻、どの試合まで反映したか、クラブごとの `games_played` は標本ページで確認できなかった。取得時刻は collector 側で UTC に記録可能だが、公式更新時刻の代用にはならない。

## 標本クラブと表示値

性能・順位による事後選択はせず、既存 TeamMaster に official name と slug がある3クラブを使った。数値は上記の公式ページに表示された**調査時点の標本**であり、評価対象試合の pre-match 値ではない。

| 公式表示名 | TeamMaster `team_id` | 公式 slug | 観測した標本値 |
| --- | --- | --- | --- |
| サンフレッチェ広島 | `team_0006` | `hiroshima` | 2025 xG `59.8`、2026/27 シュート総数 `130`、平均パス数 `544.7`、平均支配率 `53.5%` |
| 柏レイソル | `team_0009` | `kashiwa` | 2025 xG `51.3`、2025 パス総数 `23149`、2026/27 平均パス数 `628.4`、平均支配率 `58.2%`、平均走行距離 `118km` |
| 名古屋グランパス | `team_0018` | `nagoya` | 2026/27 平均パス数 `545.4`、平均支配率 `56.7%`、被枠内シュート総数 `34` |

クラブリンクの `/club/{slug}/` と [data/master/teams.csv](../data/master/teams.csv) の `jleague_official` exact source name / `source_club_id` が上の3件では一致する。これはクラブ identity の接続であり、選手 ID はこのクラブランキングに現れない。選手統計を使うなら別の公式選手 ID 監査が必要。名称だけの fuzzy matching や TeamMaster 変更はしない。

## Stat 別 inventory

`○` はその J1 season・当該項目を公式ページ上で実見、`?` はこの少数監査で未確認。`○` でも全クラブ・全時点 coverage を示さない。機械可は**観測した HTML 標本について**。評価記号: A = snapshot と match-level 差分が安全に検証済み、B = snapshot は可能そうだが差分には未解決条件、C = 安定 snapshot 経路未確認、D = 表示・順位だけで値の機械読取不可。今回 A と D は確定していない。

| Stat | 2025 available | 2026/27 available | Value type | Machine-readable | Delta reconstruction | Verdict |
| --- | --- | --- | --- | --- | --- | --- |
| xG (for) | ○ `59.8` 広島、`51.3` 柏 | ? | 2025 `ゴール期待値`; 累積らしいがページに total 明記なし、表示小数1桁 | 2025 HTML ○ | 丸め誤差、2026/27 同項目・2時点未確認 | 2025 B / 2026/27 C |
| xGA / xG against | ? | ? | 不明 | 未確認 | 不可 | C |
| Shots | ○ 横浜FM `406` | ○ 広島 `130` | `シュート総数`、整数 total | HTML ○ | 正確な連続 snapshot と1試合だけの増分なら候補。未実証 | B |
| Shots on Target (for) | ? | ? | 不明 | 未確認 | 不可。下行と混同しない | C |
| Shots on Target **against** | ? | ○ 名古屋 `34` | `被枠内シュート総数`、整数 total | HTML ○ | 連続 snapshot・対象試合対応の実証が必要 | B |
| Possession | ? | ○ 柏 `58.2%`、広島 `53.5%` | `平均ボール支配率`、率・表示小数1桁 | HTML ○ | 単純差分不可。集計分子/分母と定義未確認 | B |
| Passes | ○ 柏 `23149` | ○ 柏 `628.4` | 2025 は `パス総数`、2026/27 標本は `1試合平均パス数` | HTML ○ | 2026/27 total と同期 `games_played` 未確認。平均×試合数も丸め誤差あり | B |
| Pass Success / Pass Accuracy | ? | ? | 成功数・試行数・率とも未確認 | 未確認 | 分子/分母なしの率差分禁止 | C |
| Tackles | ? | ? | 2026**特別**シーズンの total ページは存在するが 2026/27 の証拠ではない | 対象 season 未確認 | 不可 | C |
| Interceptions / Blocks / Clearances / Chance Creation / Crosses / Dribbles / Through Passes | ? | ? | 今回は項目ごとの対象季ページ未検証 | 未確認 | 不可 | C |
| Fouls | ? | ○ [2026/27 総数](https://www.jleague.jp/j1/stats/club/2026-27/foul_count/search-list/) | 整数 total | HTML ○ | 連続 snapshot・対象試合対応の実証が必要 | B |
| Yellow / Red Cards | ? | ? | 未確認 | 未確認 | 不可 | C |
| Running Distance | ? | ○ 柏 `118km` | `1試合平均走行距離`、表示は整数 km | HTML ○ | 丸め幅が大きく、exact match-level 距離は復元不可 | B |
| Sprint Count | ? | ○ FC東京 `138` | `1試合平均スプリント回数`、表示は整数 | HTML ○ | total・hidden precision 未確認。平均から exact 件数は復元不可 | B |
| High-intensity running | ? | ? | 未確認 | 未確認 | 不可 | C |
| Clean sheets (追加例) | ? | ○ 広島 `3` | `クリーンシート総数`、整数 total | HTML ○ | 条件付きで差分候補。ただし対象 match 対応未実証 | B |

2025 と 2026/27 は `/{season}/{stat}/search-list/` の URL 形と HTML ランキング形式が標本では共通。ただし **同じ stat が両季に存在することは未確認**。特に 2025 のパス**総数**と 2026/27 のパス**平均**を同一 field として扱わない。また `/2026/` は百年構想の**特別シーズン**であり、`/2026-27/` と混同しない。2026 特別シーズンの [タックル総数](https://www.jleague.jp/j1/stats/club/2026/tackle_count/search-list/) は 2026/27 の証拠に含めていない。

## Snapshot と match-level 差分の安全条件

1. **同一 season・club・stat の前後2 snapshot** が必要。現在の2025終了値から2025途中時点を再構成することはできない。各取得で `fetched_at_utc`、公式表示更新日、source URL、raw HTML/response hash、表示文字列・数値・単位・値種別、official club slug、TeamMaster ID を保存する設計が妥当。`games_played`、最終反映 match ID / datetime は公式値か検証可能な公式日程と結び、未確認なら null とする。
2. 整数の season total でも `current_total - previous_total` が単一 match の値となるのは、前後 snapshot の間にそのクラブの対象大会 match が**ちょうど1試合**反映され、遅延更新・訂正・定義変更がなく、両 snapshot が同じ集計基準の場合だけ。試合が2つ進めば差分は合算であり、複数試合を推測配分しない。同日複数試合や延期・後日訂正も検証対象。
3. 1試合平均 `a` は、公式が同じ `games_played=n` を提供し、平均の集計分母が実際に `n` であると検証できて初めて `a×n` を検討できる。表示小数1桁なら平均の丸めだけで累積推定誤差は最大およそ `0.05n`、前後差分では両側の誤差が加わる。整数 km・整数 sprint 平均ではさらに粗い。今回、同期した `games_played` と hidden precision は見つけていない。
4. 支配率・パス成功率は率を単純差分してはならない。公式の分子/分母、試合時間・集計定義、丸め精度が揃わない限り、試合別率の復元を認めない。単純な試合数重み付き平均であるという仮定も未検証。
5. 公開は試合翌日～2日後の案内であり、取得時刻に終了した試合がすべて反映済みとは限らない。未来の試合の値を pre-match feature に入れないため、snapshot の公表・取得時刻と対象試合 kickoff の先後を検証する。公式ページの日付のみでは時刻順序を保証できない。

過去の [2024 official match stats audit](J1_2024_OFFICIAL_MATCH_STATS_AUDIT.md) では match-level HTML/RSC に `0` や `0%` の placeholder が観測された。今回の**別系統であるクラブ season ranking** の値を根拠に、その旧 match-level placeholder を確定値へ読み替えない。逆も同様。

## 次段階へ進む前のゲート

実装するならまず少数クラブ・少数 stat の複数日時 snapshot を保存し、(a) フィルタで全クラブを一意に取れるか、(b) 公式更新時点と `games_played` が分かるか、(c) 1試合だけ増えた total が公式 match-level 値と整合するか、(d) 同日・延期・訂正で誤差が出ないか、(e) 2026/27 の xG/xGA・攻撃 SOT・タックル等の実在 URL が公式 UI から辿れるか、を別 research cycle で確認する。独自の未観測 endpoint や過去値の推測は使わない。公式サイトの利用条件・自動取得可否も本監査では確定していないため、定期収集前に確認が必要。

本件はデータ経路の feasibility のみ。既存モデル・2020～2024 選択過程・2026 interim 結果は変更しない。
