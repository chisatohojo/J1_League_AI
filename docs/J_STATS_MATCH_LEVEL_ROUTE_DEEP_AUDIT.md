# J Stats historical match-level route deep audit

調査日: 2026-09-22  
対象: 2015～2024 J1、特に2018～2023  
調査種別: 公式route discovery / read-only audit

## Executive summary

現在利用できるJ.LEAGUE公式ページ、embedded React Server Component (RSC) payload、実ページが読み込むJavaScript chunk、historical match page、旧tracking導線を限定調査した。

結論は次のとおり。

- 現行J Statsのseason ranking値は、HTML内のRSCに集計済み`rankingList`として埋め込まれている。観測した入力軸はcompetition、season、stat slug、club/player filterであり、match ID、fixture ID、date、roundを入力にする処理は見つからなかった。
- route固有JSは`rankingList`をpropsとして受け取り、filter URLを組み立て、`slice()`で「もっと見る」を実装する。ranking値を取得するclient-side fetch、GraphQL、公開API、ranking用server actionは観測できなかった。
- 2018～2023は各年3試合、2024は移行前後を含む4試合を確認した。全22試合を既存J1 datasetへdate + home/away stable `team_id`で22/22一意にexact linkageできた。
- 2018～2023の18標本には、xG、possession、passing、creation、defense、duels、runningのmatch-level numeric payloadは見つからなかった。stat名は共通translation dictionaryに存在するが、値ではない。
- 2019～2023のhidden home/away xGは代表15試合で見つからなかった。season-final xGが存在することは、同じ値のmatch-level public routeが残っている証拠にはならない。
- 2024-09-01以前の標本にはhidden xG値がなく、2024-09-13と2024-12-08には既知のFull Time summaryがある。前後で読み込むmatch-page JS chunk集合は同じで、確認できた変化はRSC内の試合後summary dataの有無だった。
- 2015～2017のtracking dataが当時存在した公式証拠と旧deep linkは確認できたが、現在値を返すofficial routeは復元できなかった。旧special routeは404、旧deep linkは現在tracking payloadを返さない。
- 現在production化できるhistorical match-level advanced statsは、既存の2024後半96試合のxG/shots on targetだけである（classification C）。2018～2023のadvanced statsは、underlying dataの存在を示すseason aggregateはあるがcurrent match-level retrieval routeがないためD。SFMS02の`SH`は別系統で2015～2024のshotsを提供済みである。

したがって、今回新しいhistorical collectorへ進めるrouteは発見しなかった。advanced-stat match-level routeの最初の確認日は**2024-09-13**、full-season xG routeの最初の確認seasonは対象外の**2025**のままである。

## Scope and existing evidence

先に次の成果と実装を確認した。

- [J_STATS_HISTORICAL_DATA_INVENTORY.md](J_STATS_HISTORICAL_DATA_INVENTORY.md)
- [J_STATS_TEAM_SNAPSHOT_FEASIBILITY.md](J_STATS_TEAM_SNAPSHOT_FEASIBILITY.md)
- [J_STATS_TEAM_SNAPSHOT_COLLECTOR_DESIGN.md](J_STATS_TEAM_SNAPSHOT_COLLECTOR_DESIGN.md)
- [JLEAGUE_MATCH_XG_DATASET.md](JLEAGUE_MATCH_XG_DATASET.md)
- [2026_MATCH_XG_COVERAGE_AUDIT.md](2026_MATCH_XG_COVERAGE_AUDIT.md)
- `src/collect/jstats_team_snapshots.py`
- `src/collect/jleague_match_xg.py`
- [JLEAGUE_STARTING_XI_AUDIT.md](JLEAGUE_STARTING_XI_AUDIT.md)
- [SFMS02_PLAYER_MINUTES_FEASIBILITY.md](SFMS02_PLAYER_MINUTES_FEASIBILITY.md)
- [SFMS02_PLAYER_MINUTES_DATASET.md](SFMS02_PLAYER_MINUTES_DATASET.md)

既存SFMS02 cache / auditは、2015～2025についてscore、lineup、substitution、cards、SH、CK、FK、referee、stadium等を確認済みである。SFMS02にadvanced-stat routeがあるとは解釈しない。

今回の新規network調査はJ.LEAGUE公式domainに限定した。search indexは旧route名の発見だけに使い、archive値やthird-party値は採用していない。URL総当たり、match ID生成、parameter guessingはしていない。

## Inspected architectures

1. 現行Next.js J Stats team ranking page
   - HTML
   - `self.__next_f.push(...)` embedded RSC
   - filter/component props
   - 実ページが参照する24個のJ.LEAGUE JS chunk
2. 現行Next.js historical match / live-commentary page
   - HTML、embedded RSC、translation/hydration payload
   - `#stats` navigation
   - match-page固有5 chunkを含む26 chunk構成
3. 2024 xG delivery transition前後
4. 旧2015～2017 tracking導線
   - official announcements
   - announcement内のactual match link / deep link
   - official publicationに記録されたold special route
5. 既存SFMS02 structure / cache audit

## Current J Stats internal data path

### Observed route and RSC object

確認した代表route:

```text
https://www.jleague.jp/j1/stats/club/2025/expected_goals/search-list/
https://www.jleague.jp/j1/stats/club/2019/expected_goals/search-list/
https://www.jleague.jp/j1/stats/club/2018/shoot/search-list/
```

HTML内のRSCは、たとえば2019 xGを次の形でcomponentへ渡す。

```text
rankingList[0].id       = "ranking-expected_goals"
rankingList[0].category = "j1"
rankingList[0].year     = "2019"
rankingList[0].stats    = {value: "expected_goals", label: "ゴール期待値"}
rankingList[0].data[]   = {
  href,
  club: {code, name, icon},
  rank,
  ranking,
  points,
  score
}
```

2018 `shoot`、2019 `expected_goals`、2025 `expected_goals`の3ページすべてで、ranking objectはseason/stat別の集計済みrowsだった。RSC中のclub identityは公式slug (`club.code`) と公式表示名である。

### Inputs found and not found

| Input / identifier | Result |
| --- | --- |
| competition/category | `j1`を確認 |
| season/year | URLと`rankingList.year`に存在 |
| stat ID | stat slug (`expected_goals`, `shoot`等)として存在 |
| club ID | official club slugとしてfilter / resultに存在 |
| match ID / fixture ID / game ID | ranking payloadとroute-specific JSで未確認 |
| date / round / historical update state | ranking filterに未確認 |
| `updatedAt` | global navigation CMS metadataにはあるがranking data時点ではない |
| `matchday` | global competition translationにあるだけでranking filterではない |

`matchId`, `gameId`, `fixtureId`, `roundId`, `detailHref`は3つのranking payloadで0件だった。`matchday`や`updatedAt`という文字列だけをmatch-level / snapshot parameterとは扱っていない。

### Loaded JS and request behavior

実ページが参照するJ.LEAGUE JS chunk 24個を確認した。route固有chunk `3yk7vweb2yfki.js` の`StatsTabs` / search-list componentは、serverから受け取った`rankingList`をpropsとして使い、次を行う。

- year / stat / club filterから`/{competition}/stats/{type}/{year}/{stat}/search-list`を組み立てる
- `rankingList[].data.slice(0, end)`で表示件数を制御する
- 「もっと見る」で`end`を増やす

このcomponent内にranking fetchはない。別chunkで観測した`fetch()`は画像到達性のHEAD確認等で、ranking値取得ではなかった。generic Next runtimeに`createServerReference` / `serverAction`文字列はあるが、rankingに紐づくaction identifierやmatch-level actionは観測できなかった。API/GraphQL endpoint literalも見つからなかった。

**観測に基づく最も強い説明**は「server側で用意された集計済みranking objectをRSCへ埋め込み、clientは描画だけを行う」である。static file、precomputed database aggregate、event DBからrequest時にdynamic aggregationのどれかは、公開payloadだけでは判別できない。

## Historical match embedded data

### Sample and exact linkage

2018～2023はopening / middle / lateを各3試合、2024はopening、移行直前、移行開始、lateを確認した。2018・2019・2024のpathはofficial schedule listingのactual `detailHref`から選び、推測生成していない。

| Year | Official path IDs | Local SFMS02 match IDs | Exact linkage |
| ---: | --- | --- | ---: |
| 2018 | `022301`, `072701`, `120109` | `20745`, `20898`, `21050` | 3/3 |
| 2019 | `022201`, `070604`, `120709` | `21488`, `21643`, `21793` | 3/3 |
| 2020 | `022101`, `090906`, `112119` | `22783`, `24020`, `24140` | 3/3 |
| 2021 | `022601`, `062706`, `120410` | `24974`, `25171`, `25353` | 3/3 |
| 2022 | `021801`, `062502`, `110509` | `27328`, `27482`, `27633` | 3/3 |
| 2023 | `021701`, `062403`, `120309` | `28163`, `28318`, `28468` | 3/3 |
| 2024 | `022301`, `090102`, `091301`, `120810` | `30430`, `30719`, `30727`, `30809` | 4/4 |

linkageはofficial pageのcompetition/year、date、home/away名をTeamMasterの`jleague_official` / `jleague_data_site` exact identityへ解決し、既存J1 rowのdate + home/away stable IDと照合した。fuzzy、NFKC、substring matchingは使っていない。

### Payload findings

全22ページは現在の同一26-script構成を参照し、各ページにembedded RSCと共通translation dictionaryがある。次の点を区別した。

- `expected_goals`, `ball_rate`, `pass_count`, `shoot_on_target`, defense/running stat名の存在
- home / awayに結び付くnumeric valueの存在

前者は全歴史ページの共通辞書にあるが、後者ではない。たとえば`match.stats_comparison` / `detail_stats_comparison`は、possession、pass、through pass、chance creation、cross、tackle、recovery、block、clear、distance、sprint等の**表示ラベル辞書**だった。numeric match objectではなかった。

`distance_per_game` / `sprint_per_game`に対する単純な`key:number`検索は一見hitするが、実体は`"distance_per_game":"1試合平均..."`の先頭文字`1`を値と誤認したものだった。context確認後はnumeric evidenceから除外した。

match-page固有5 JS chunkも確認したが、advanced stat field名、match/fixture IDを受け取るstat API、tracking endpoint literalはなかった。2件のgeneric `fetch()` tokenはあったが、route-specific stat targetは観測できなかった。

各ページには`/match/j1/{year}/{path_id}/#stats`へのlinkがある。これは同一match page内のfragment navigationであり、別のstructured endpointではない。historical pageのRSC内に実値がないため、link labelだけからhidden dataを推定しない。

## 2019～2023 hidden xG

season-final team xGは2019から取得できるが、2019～2023の各3試合、合計15試合では次のすべてが未確認だった。

- home / away xG numeric pair
- numeric `expected_goals` object
- xG API / fetch target
- match IDを入力に取るJ Stats ranking function
- old xG payloadへのlink

各ページに`expected_goals` tokenが約10回あるのはtranslation / stat description由来である。既存parserが要求するFull Timeのhome/away numeric sentenceは15/15でmissingだった。

**判定: hidden match xG not found in the representative 2019–2023 sample.** これはsample-based conclusionであり、全1,678試合の不存在証明ではない。ただしstopping ruleで指定されたRSC、JS、embedded payload、old route clueまで確認してもretrieval routeが得られなかったため、追加parameter探索は行わない。

## 2024 transition analysis

| Sample | Date | Full Time xG | Hidden pre-transition numeric xG | JS architecture |
| --- | --- | --- | --- | --- |
| `022301` | 2024-02-23 | missing | not found | same current 26 chunks |
| `090102` | 2024-09-01 | missing | not found | same current 26 chunks |
| `091301` | 2024-09-13 | complete | n/a | same current 26 chunks |
| `120810` | 2024-12-08 | complete | n/a | same current 26 chunks |

移行前後とも共通stat label、`#stats` tab、同じJS bundlesを持つ。差は2024-09-13以降のRSC / Full Time commentaryに、両teamのshots、shots on target、xG numeric summaryが追加されたことだった。移行前sampleにbackend値だけが埋め込まれUI非表示になっている形跡は見つからなかった。

既存full auditの96/380と合わせ、2024はpartial availability (C) を維持する。xGAは独立fieldとして配信されず、両team xGがある96試合に限り、team視点でopponent xGをxG againstとして扱える。

## Old tracking / J Stats architecture

公式announcementとそこから実際に辿れるlinkを確認した。

- [2015 LIVE tracking開始](https://www.jleague.jp/news/article/714/) は、2015 J1全試合でtracking取得、公開LIVE serviceは毎節1試合と説明し、actual linkとして `/match/j1/2015/030702/preview/` を持つ。
- [2016 service update](https://www.jleague.jp/news/article/6303/) はdistance、sprint、top speedに加え、shots/SOT、opponent-half passing、方向別pass、attacking-third play等を追加したと説明する。
- [2015浦和–横浜FMの公開通知](https://www.jleague.jp/news/article/1203/) は、actual deep link `https://www.jleague.jp/l/?/match/j1/2015/041806/live#trackingdata` を持つ。
- J.LEAGUE公式刊行物に記録された `https://www.jleague.jp/special/trackingdata/` は現在404。

現在のdeep link responseには`tracking` payload、canonical match page、old XHR/API URLがなく、generic official pageを返した。2015 preview pageにもcurrent tracking data objectは確認できなかった。したがってold application route名は回収できたが、値を取得できるrouteは回収できていない。

**判定: 2015～2017 tracking = D.** 元dataと旧公開serviceの存在証拠はあるが、current official retrieval routeなし。

## Season-final aggregation provenance

観測できた証拠:

1. current pageのRSCには集計済みranking rowsが直接入る。
2. client JSはそのrowsを描画・sliceし、match eventを合算しない。
3. ranking routeはseason/stat/clubを持つがmatch/date/roundを持たない。
4. 旧公式J Stats表示とofficial search indexは「データ提供：データスタジアム」と明記し、J1は試合翌日～2日後更新と説明している。
5. 2018以降のhistorical rankingがcurrent routeから返る一方、RSCのclub icon asset等は現行frontend資産で再描画されている。

これらから、public interfaceは「Data Stadium由来の集計済みseason rankingをJ.LEAGUE server componentへ渡すもの」に近い。ただし、保存済みseason aggregate、database view、request-time dynamic aggregationのどれかは公開技術証拠だけでは確定できない。provider表記も、public match-level feedの存在や利用可能性を意味しない。

## Discovered official route patterns

| Pattern | Observed role | Match-level suitability |
| --- | --- | --- |
| `/j1/stats/club/{season}/{stat}/search-list/` | embedded RSC season ranking | no match/date input; season aggregate only |
| `/match/j1/{year}/{actual_path_id}/live-commentary/` | match identity/commentary; 2024-09-13以降xG/SOT summary | C for 2024 late xG/SOT |
| `/match/j1/{year}/{actual_path_id}/#stats` | same page fragment | not an endpoint |
| `/l/?/match/j1/2015/{id}/live#trackingdata` | old announcement deep link | current response has no tracking payload |
| `/special/trackingdata/` | old official route clue | current 404 |
| `/stats/j1/club/{season}/{stat}/` | observed legacy aggregate URL family | redirects to current season aggregate route; no match ID |

No stable official structured historical match-level API, GraphQL endpoint, static JSON, recoverable XHR, or ranking server action was discovered.

## Stat-family availability and classification

Classification:

- **A**: stable official structured match-level route; production-ready
- **B**: official HTML/RSC/embedded payload; productionizable
- **C**: only some seasons/matches
- **D**: underlying data evidence exists, but no current official retrieval route
- **E**: not confirmed in this audit

| Stat family | 2015–2017 | 2018 | 2019–2023 | 2024 | Notes |
| --- | --- | --- | --- | --- | --- |
| xG / xGA | E | E | D | C | season-final xG starts 2019; match values only final 96 in 2024 |
| possession | D/E | D | D | D | aggregate/old architecture evidence, no current match values |
| pass / pass rate / through pass | D (especially 2016) | D | D | D | no current match payload found |
| chance creation / cross / dribble | E/D | D | D | D | season rankings prove later aggregate data only |
| tackle / interception / recovery / block / clear | E | D | D | D | no match numeric route found |
| aerial duel / 1v1 | E | D | D | D | no match numeric route found |
| distance / sprint / possession-phase running | D | D | D | D | 2015+ tracking existence; 2018+ season rankings; no current match route |
| shots | B | B | B | B | existing SFMS02 `SH` HTML route; 2024 late summary is an additional source |
| shots on target | D | D | D | C | 2016 old LIVE service evidence; current value route only 2024 late 96 matches |

`B` for shots refers to the already-used SFMS02 HTML route, not a newly discovered J Stats API. CK/FK/cards等も同じSFMS02系であり、今回のadvanced-route discoveryの成果ではない。

## Year-by-year assessment

| Year | xG | Possession / pass | Creation / defense / duels | Distance / sprint | Shots | SOT | Overall advanced route |
| ---: | --- | --- | --- | --- | --- | --- | --- |
| 2015 | E | D/E | E | D | B | D | D |
| 2016 | E | D | D/E | D | B | D | D |
| 2017 | E | D | D/E | D | B | D | D |
| 2018 | E | D | D | D | B | D | D |
| 2019 | D | D | D | D | B | D | D |
| 2020 | D | D | D | D | B | D | D |
| 2021 | D | D | D | D | B | D | D |
| 2022 | D | D | D | D | B | D | D |
| 2023 | D | D | D | D | B | D | D |
| 2024 | C (96/380) | D | D | D | B | C (96/380) | C/D |

The earliest currently usable match-level field in the requested period is SFMS02 shots in 2015. The earliest usable **advanced** match summary is 2024-09-13; it remains partial-season. No 2018～2023 production match-level advanced-stat start year was established.

## Production suitability and final verdict

- **New historical advanced-stat collector: do not implement.** No new official match-level route was found.
- **2024 late xG/SOT: C.** Existing explicit missing mask and 96/380 boundary remain correct.
- **2018～2023 advanced stats: D.** Underlying aggregate data exists, but current official match-level retrieval route is absent.
- **2015～2017 tracking: D.** Historical service evidence survives; retrievable values do not.
- **SFMS02 shots/basic match fields: B.** Continue using the established collector/cache, without reclassifying them as J Stats advanced data.
- **Season-final J Stats: descriptive / schema evidence only.** It must not be substituted for chronological match values or used as an in-season feature.

Revisit only if J.LEAGUE publishes or exposes an observed, stable route carrying exact match identity plus numeric values. A translation key, empty stats tab, legacy link text, or season aggregate is not sufficient.

## Chronology policy

Any future match-level observation is post-match data. A rolling feature may use it only after that match completed and strictly before the target kickoff, with same-time batching where required. Season-final rankings cannot be retroactively assigned to earlier matches. No feature, model evaluation, or prediction was performed in this audit.

## Request accounting

- Controlled direct HTTP requests: **83** requests across **68 unique observed official URLs**.
  - 6 bounded schedule listings
  - 22 historical match pages
  - 3 J Stats ranking pages
  - 24 J Stats-referenced J.LEAGUE chunks
  - 5 match-page-only chunks
  - official tracking articles/routes and narrowly scoped follow-up diagnostics
- Search discovery: 2 search calls / 7 official-domain queries. Search results were used only to find official evidence/routes.
- One initial all-in-one diagnostic exceeded the execution window before its counter was emitted. Its observations were discarded. It generated an indeterminate number of additional requests, so physical network traffic was **greater than 83**; all reported findings come from the controlled 83-request runs.
- Some controlled requests were repeated after output/encoding failures. Evidence is deduplicated by URL; no duplicate response was counted as an additional sample.

No full historical crawl was run. No raw cache, processed dataset, production collector, TeamMaster row, feature, model metric, or prediction was created.

## Limitations

- 2018～2023 conclusions are based on three exact-linked representative matches per year, not every match.
- 2024 pre-transition hidden-data conclusion is based on opening and 2024-09-01 samples plus the existing 380-page coverage audit.
- Absence from current HTML/RSC/chunks does not prove that J.LEAGUE or its provider never stored the data internally.
- Next.js chunk names and embedded RSC are non-contractual and may change.
- Search-index renderings can preserve text from older frontend generations; only live official responses were accepted as retrieval evidence.
- Old tracking announcements prove acquisition/publication at the time, not current retrievability or historical completeness.
