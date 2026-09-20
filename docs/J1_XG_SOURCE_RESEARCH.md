# J1 match-level xG source research

確認日: 2026-09-20

## 結論

現時点では、2015～2024のJ1全試合について、同一定義・同一取得方式でhome/awayのmatch-level xGを安全に列挙できる公開sourceは確認できなかった。判定は **C（いったん見送り）** とする。

FootyStatsは最有力候補だが、公開ページで確認できたのはseason selector、team aggregate、直近試合のmatch-level表示およびmatch CSV/APIの案内までであり、2015～2024全試合のxG列の実在・完全性・定義の時系列一貫性を今回の少数確認だけでは確定できない。

## 必須フィールドと評価

必要フィールドは `match_date`, `home_team`, `away_team`, `home_xg`, `away_xg`。将来のrolling featureでは、current matchより前の試合だけを使用する必要がある。

| source | 2015 | 2019 | 2021 | 2022 | 2024 | match-level home/away xG | delivery | 判定 |
|---|---|---|---|---|---|---|---|---|
| J.LEAGUE公式 | season/team aggregateを確認 | 同一方式の継続を確認できず | 同左 | 同左 | club aggregateのxGを確認 | 今回の公開ページ確認では全試合のhome/away値を確認できず | HTMLページ | C |
| FootyStats | season selectorに存在。ただし試合xG列は未検証 | season selector/dataset導線あり。試合xG列は未検証 | 同左 | 同左 | team aggregateとRecent Resultsのmatch-level xG表示を確認 | 一部match-level表示は確認。全期間・全試合の完全性は未確定 | HTML、CSV/API案内 | B |
| FotMob | 今回未確認 | 今回未確認 | 今回未確認 | 今回未確認 | match pageでxG機能の存在を確認 | 2024 sampleではxG機能の説明はあるが、公開HTML本文から値を安定取得する方式は未確定 | HTML/動的データ | B |
| FBref | 今回のJ1全期間match xGを確認できず | 同左 | 同左 | 同左 | league summaryは確認したがmatch xGを確認できず | J1 2015～2024のhome/away match xG sourceとして確定できず | HTML | D |

## 公式J.LEAGUE

2024公式ページはExpected Goalsのクラブseason aggregateを掲載し、更新時期も「J1: 1–2 days post match」と案内している。しかし表示はクラブ集計であり、対象matchごとのhome/away xG列ではない。[J.LEAGUE 2024 club Expected Goals](https://www.jleague.jp/en/j1/stats/club/2024/expected_goals/search-list/)（確認日 2026-09-20）

従って、aggregateをmatch-levelへ逆算してはならない。2015～2023について、同じ公式API・embedded JSON・historical match-level deliveryが継続している証拠は今回確認できなかった。

## FootyStats

FootyStatsのJ1 xGページには2015～2025等のseason selectorが表示され、xG/xGAのteam aggregateが提供される。またRecent Resultsには、試合カード単位でホーム・アウェイ、結果、home xG、away xGが表示される例がある。[J1 xG](https://footystats.org/japan/j1-league/xg)（確認日 2026-09-20）

同サイトはJ1 dataset pageで、seasonごとのMatch CSVとAPIを案内している。[J1 datasets](https://footystats.org/japan/j1-league/datasets)（確認日 2026-09-20）ただし、今回の調査では2015・2019・2021・2022・2024のMatch CSVを大量取得せず、xG列の全件性、欠損、match identity、値のhistorical backfillを検証していない。

定義は一般的なshot-location-only xGではなく、shot accuracy、shot frequency、attack dangerousness、possession amount/depth等を組み合わせたFootyStats独自式と説明されている。[FootyStats xG methodology](https://footystats.org/japan/j1-league/xg)（確認日 2026-09-20）したがってOpta等の別providerのxGと同一視できず、2015～2024でmethodologyが不変かも未確認である。PK、own goal、penalty除外の扱い、精度、historical recalculationは公開説明だけでは確定できなかった。

自動取得については、公開CSV/API導線があるためprototype候補ではあるが、API利用条件・rate limit・再利用条件を確認してから実装すべきである。ログイン必須とは確認できなかったが、無制限利用可能とも判断しない。

## FotMob

2024-08-11 Sagan Tosu–Urawa Red Diamondsのmatch pageは、試合日、home/away、Full timeを掲載し、Stats機能とxGを含むReal-time extensive statsを説明している。[FotMob sample match](https://www.fotmob.com/matches/urawa-red-diamonds-vs-sagan-tosu/6ilqoij)（確認日 2026-09-20）

ただし今回取得した公開本文ではxG数値そのものを安定して確認できず、動的payload/APIの公開・historical 2015～2024 coverage・provider/定義も確定できなかった。Match IDはFotMob固有IDで、既存J.League `match_id`との直接同一性は確認できない。日付+home/awayのTeamMaster照合が必要になる。

## FBref

2024 J1 League StatsとScores & Fixturesのleagueページは確認できたが、今回の確認範囲では、J1 match reportからhome/away xGを全試合取得できる構造を確認できなかった。[FBref 2024 J1 Stats](https://fbref.com/en/comps/25/2024/2024-J1-League-Stats), [FBref 2024 fixtures](https://fbref.com/en/comps/25/2024/schedule/2024-J1-League-Scores-and-Fixtures)（確認日 2026-09-20）

なお、FBrefで見つかるPSxG（post-shot xG）は通常のmatch xGとは区別する必要がある。今回のJ1 2015～2024 sourceとしては採用しない。

## sample coverage summary

| season | official match-level xG | FootyStats match-level sample | FotMob match-level sample | 判断 |
|---|---|---|---|---|
| 2015 | 未確認 | season導線は確認、全match値未検証 | 未確認 | 未確定 |
| 2019 | 未確認 | season導線は確認、全match値未検証 | 未確認 | 未確定 |
| 2021 | 未確認 | season導線は確認、全match値未検証 | 未確認 | 未確定 |
| 2022 | 未確認 | season導線は確認、全match値未検証 | 未確認 | 未確定 |
| 2024 | aggregate確認 | Recent Resultsでmatch-level表示例確認 | xG機能確認、値の安定取得未確認 | 部分確認 |

## identity / chronology

J.LEAGUE公式の既存 `match_id` と第三者match IDが同一とは限らない。第三者sourceを採用する場合は、source match IDを保存し、日付・home/awayをTeamMasterで検証する必要がある。match-level xGが取得できても、同日開催・延期・表記差・duplicateを検証し、current match自身のxGをpre-match featureに含めないことが必須である。

## 最終判断

**C: coverage / consistency不足のため、xGは一旦見送る。**

次に進む場合の候補はFootyStatsである。ただしcollector実装前に、2015・2019・2021・2022・2024の各Match CSV/APIレスポンスを少量取得し、以下を確認する必要がある。

1. 全J1 matchにhome/away xGが存在すること
2. source match IDと日付・home/awayの一意対応
3. 欠損・再計算・定義変更・利用規約/API制限

これらが確認できるまでは、xGを2015～2024のrolling featureへ投入しない。
