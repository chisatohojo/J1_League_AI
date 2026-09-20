# FootyStats J1 Match-Level xG Feasibility

調査日: 2026-09-20

## 結論

判定: **B — 追加調査が必要**。

FootyStatsにはJ1の2015～2024 season selectorと、season単位のMatch CSV導線が存在する。しかし、今回の限定調査では、2015・2019・2024の全試合について、公開HTMLから `home_xg` / `away_xg` を実際に取得できることまでは確認できなかった。Match CSVの導線は確認できるが、2015・2019ではPremiumページへリダイレクトされたため、無料公開範囲だけでcoverageを確定できない。

従って、現時点でcollector実装や全件取得へ進めない。次段階では、契約・利用許諾を確認したうえで、J1の過去season Match CSVまたはAPIレスポンスの実サンプルを各対象年から1件ずつ取得し、xG列とmatch identityを検証する必要がある。

## 調査範囲とアクセス

- 対象: 2015、2019、2024 J1のみ。
- 対象外: 2025、2026、他サイト、全件crawl、collector実装、CSV生成。
- ネットワーク確認: FootyStats公式ページを限定的に確認。season/dataset/xG/API/match-detail関連ページを合計10ページ程度閲覧した。大量取得やID総当たりは行っていない。
- FootyStatsのdatasetsページは、プログラム利用にはAPIを使うよう案内している。またAPIはJSON形式で、利用可能league数・request上限がpackageにより異なり、有料packageが示されている。[J1 datasets](https://footystats.org/japan/j1-league/datasets)、[FootyStats API](https://footystats.org/api)
- Match CSVリンクは存在するが、2015・2019のリンク確認ではPremiumページへ遷移した。したがって「CSV導線がある」ことは確認できるが、今回の環境で無料・無認証のCSV内容は確認できなかった。[Premium redirect example](https://footystats.org/c-dl.php?comp=251&type=matches)

## Season inventory / coverage

| season | 既存J1期待試合数 | FootyStats season / Match CSV行数表示 | match-level xG実値を今回確認 | coverage | 判定 |
|---|---:|---:|---:|---:|---|
| 2015 | 306 | 309 rows表示 | 0件を確定できず | 未確定 | B |
| 2019 | 306 | 306 rows表示 | 0件を確定できず | 未確定 | B |
| 2024 | 380 | 380 rows表示 | 0件を確定できず | 未確定 | B |

FootyStatsのdatasets pageは、2015を309 rows、2019を306 rows、2024を380 rowsとして表示している。[J1 datasets](https://footystats.org/japan/j1-league/datasets)

この行数は今回の「match-level xG available matches」ではない。2015は既存J1の306試合と行数が一致しないため、延期・重複・別match type・データセット定義の差を追加確認せず、coverage 100%とは扱わない。今回の調査で確認できたcoverageは、3 seasonとも **未確定**、安全に採用できる確定coverageは **0/expectedではなく、実値未検証** である。

## 公開xG表示の確認

現行のJ1 xG pageには、team aggregateの `xG` / `xGA` / `xGD` と、Recent Resultsの `Home XG`、`Away XG`、`Final Goals` が表示される。Recent Resultsの行では、例えばmatch date、home/away、score、両側のxG値が同一行に見える。[J1 xG page](https://footystats.org/japan/j1-league/xg)

ただし、確認できたRecent Resultsは現行seasonの表示であり、2015・2019・2024を選択した過去match一覧の全行を今回の公開HTMLから再現できなかった。従って、これはmatch-level xGというフィールドの存在確認であって、過去3 seasonのcoverage証明ではない。

## 必須フィールドの評価

| field | 今回の確認結果 | 評価 |
|---|---|---|
| `home_xg` | 現行Recent Resultsで表示 | 過去sample全件は未検証 |
| `away_xg` | 現行Recent Resultsで表示 | 過去sample全件は未検証 |
| `home_xga` / `away_xga` | match rowの独立fieldとしては未確認。team xGAはaggregateとして表示 | match-level xGAは、相手側xGを反転して導出する設計になる可能性があるが、今回は採用しない |
| match date | Recent Resultsに表示 | 過去CSVで全件確認は未実施 |
| home / away | Recent Resultsに表示 | 過去CSVで全件確認は未実施 |
| score | `Final Goals` として表示 | 過去CSVで全件確認は未実施 |
| stable match ID | match-detail URLはslug形式を確認したが、公式の安定numeric match IDは確認できず | date + home + away + scoreのdiagnostic mapping候補 |

FootyStatsのmatch-detail URLは、確認したページではチーム名を含むslug形式だった。ページ本文から独立した `match_id` / `fixture_id` の明示的な安定識別子は今回確認できなかった。[match-detail example](https://footystats.org/japan/mito-hollyhock-vs-yokohama-f-marinos-h2h-stats)

## Match identity linkage

既存J1 datasetとの候補keyは、次の順で検証するのが安全である。

1. FootyStats側に明示されたstable match identifierがCSV/APIに存在するか確認。
2. 存在しない場合、`match_date + home team + away team` を候補keyとする。
3. 同日同カード、延期、表記変更、ホーム/アウェイ逆転がないことを照合し、必要ならscoreを診断に使う。

ただし、team名のfuzzy matchingや自動normalizationで確定してはいけない。既存TeamMasterへの追加も今回行っていない。FootyStats名から既存team_idへの対応は、exactまたは公式に裏付けられた対応だけを採用する必要がある。

## Historical consistency と定義

FootyStatsはJ1 xGについて、独自formulaを使用し、shot positionだけではなく、shot accuracy、shot frequency、attack dangerousness、possession amount/depthなどを組み合わせると説明している。[J1 xG methodology](https://footystats.org/japan/j1-league/xg)

今回確認できた範囲では、次は不明である。

- xG providerの固有名
- penaltyをxGへ含めるか
- own goalの扱い
- 2015～2024のmodel/version変更
- historical dataのbackfill方法
- 2015～2024での小数精度・丸め規則

したがって、2015・2019・2024が同じ意味・単位であるとはまだ断定しない。FootyStatsの公開説明だけでは、上記定義差を解消できない。

## Access / automation feasibility

- 公開HTML: 現行xG aggregateとRecent Resultsのmatch-level xG表示は確認できる。
- Season selector: xG page上で2012～2026/27のseason選択肢を確認できる。[J1 xG page](https://footystats.org/japan/j1-league/xg)
- CSV: J1 datasets pageに各seasonのMatch CSVリンクがあるが、2015・2019の確認リンクはPremiumへリダイレクトされた。[J1 datasets](https://footystats.org/japan/j1-league/datasets)
- API: FootyStatsは自動取得にはAPIを使うよう案内し、JSON APIのpackage、rate limit、料金を公開している。[FootyStats API](https://footystats.org/api)
- Login / paid: 公開ページ閲覧とseason選択は可能。ただし過去Match CSVの実取得およびAPIのJ1 historical accessは、今回の確認では無料・無認証で確認できず、Premium/API packageが必要な可能性が高い。契約条件は別途確認が必要。
- robots / terms: 今回確認した公開ページから、研究用途の大量自動取得を許諾する明確な記述は確認できなかった。robots・利用規約・API契約を確認せずに大量scrapingへ進んではいけない。
- request-heavy risk: HTMLをmatch単位で全件取得する方式は、2015～2024全期間ではrequest-heavyになる。まずAPIまたはseason Match CSVの契約済みbulk取得を優先すべきである。

## Downstream use and leakage

もしhistorical match-level xGが安全に揃う場合、将来はteamごとの過去matchから次を作れる。

- rolling xG for
- rolling xG against
- xG difference
- xG overperformance / underperformance

いずれもcurrent matchのxGをそのmatch predictionへ入れてはならない。xGはpost-match observed valueなので、match date順に履歴へ追加し、次のmatchのpre-match featureだけに使用する必要がある。延期・同日試合・重複行を含む場合は、stable match identityと厳密な時系列規則が必要である。

## Final judgement

**B: 全期間coverageと利用条件が未確定で、追加調査が必要。**

FootyStatsは、少なくとも現行ページ上でmatch-level `Home XG` / `Away XG` を表示し、2012以降のseason selectorと2015・2019・2024のMatch CSV行数表示を持つため、将来の候補sourceとしては有望である。一方、今回の範囲では、3 sample seasonの実xG全件、stable match ID、historical methodology consistency、無料/API/契約条件を同時に確認できていない。よって「2015～2024へ安全に導入可能」とはまだ判断しない。

次に進む条件は、FootyStatsの許諾済みCSV/APIから2015・2019・2024の小さな実サンプルを取得し、`date/home/away/score/home_xg/away_xg` の列、欠損、ID、team mapping、定義資料を確認すること。そこで3年とも同じ構造と十分なcoverageが確認できた場合に限り、collector prototypeを検討する。

