# J1 2024 Official Match Statistics Audit

確認日: 2026-09-20 (JST)

## Scope

対象は `data/processed/jleague/2024_matches_probe.csv` を基準とする、2024年通常J1の380試合のみ。2025年・2026年、モデル、feature生成、他社sourceは対象外とした。

公式match pageは `https://www.jleague.jp/en/match/j1/2024/{MMDDNN}/stats/` の実在ページを使用した。`{MMDDNN}` は公式ページ側のmatch identifierであり、日付と当日試合順を表す形式である。IDを生成して採用するのではなく、公式schedule/result pageとmatch本文の試合日・対戦カード・competitionを照合した。

## Match identity and page coverage

| 項目 | 結果 |
| --- | ---: |
| 基準match数 | 380 |
| 公式J1 match pageへlinkできた試合 | 380 |
| match date / home / away一致 | 380 |
| `/stats/` page取得可能 | 380 |
| 2025/2026の使用 | なし |

公式ページは試合名、試合日、Matchweek、home/away、最終スコアを本文に持つ。代表確認ページは [Urawa Reds–Kyoto Sanga (15 May 2024)](https://www.jleague.jp/en/match/j1/2024/051510/stats/) である。ページには `Overall` と `This Match` が併記されるため、match-level監査では `Match Stats / Team Stats` の `This Match` 側だけを対象にした。

## Match-level team field inventory

2024の公式stats pageで確認できるteam-level match fieldsは次の8項目だった。各項目はhome/awayの2値を持つ。

| field | unit | page type | available / 380 | missing | coverage | 判定 |
| --- | --- | --- | ---: | ---: | ---: | --- |
| Shots | count | This Match / Team Stats | 380 | 0 | 100.0% | A |
| Shots on Target | count | This Match / Team Stats | 380 | 0 | 100.0% | A |
| Possession | percent | This Match / Team Stats | 380 | 0 | 100.0% | A |
| Corner kicks | count | This Match / Team Stats | 380 | 0 | 100.0% | A |
| Free kicks | count | This Match / Team Stats | 380 | 0 | 100.0% | A |
| Offsides | count | This Match / Team Stats | 380 | 0 | 100.0% | A |
| Fouls | count | This Match / Team Stats | 380 | 0 | 100.0% | A |
| YC / RC | combined card count/display | This Match / Team Stats | 380 | 0 | 100.0% | B |

公式の表示順は `Shots`, `Shots on Target`, `Possession (%)`, `Corner kicks`, `Free kicks`, `Offsides`, `Fouls`, `YC / RC`。代表ページでもこの8ラベルとhome/away値が同一のTeam Stats blockに表示される。[公式ページ](https://www.jleague.jp/en/match/j1/2024/051510/stats/) の表示上、YC/RCはcombined表示であり、yellowとredを独立fieldとして安全に分離できることは今回確認できなかった。そのためカード全体はB、独立yellow/redはCとした。

## Requested fields not present as match-level team fields

| field | 結果 | 判定 |
| --- | --- | --- |
| Passes | match-level team fieldとして確認できず。ページの `Overall Stats` のseason/per-match contextと混同しない | C |
| Pass success / accuracy | 確認できず | C |
| Tackles | 確認できず | C |
| Interceptions | 確認できず | C |
| Blocks | 確認できず | C |
| Crosses | 確認できず | C |
| Chances created | player-stat側の表示であり、home/away team totalではない | C |
| Duels / 1v1 | player-stat側の表示であり、home/away team totalではない | C |
| Total distance | `Overall`側のteam contextまたはplayer displayであり、当該matchのhome/away final team valueとして扱わない | C |
| Sprint count | `Overall`側のteam contextまたはplayer displayであり、当該matchのhome/away final team valueとして扱わない | C |
| High-intensity running | 確認できず | C |
| xG / xGA | match-level home/away値は確認できず。season aggregateだけではfeature要件を満たさない | C |

つまり、pass、tackle、interception、distance、sprintを「ページに文字列がある」ことだけでmatch-level coverageと数えない。`Overall`、player stats、tracking系の表示は、今回必要なmatch-level home/away final fieldとは別物である。

## Structured data path and access

stats pageはHTML/RSC payloadにmatch identityとTeam Stats表示を含む。今回の範囲では、全試合に対して安定して利用できる公開・文書化済みの独立JSON/API endpointは確認できなかった。したがってcollectorへ進む場合の第一候補は公式HTML/RSCの該当Team Stats blockであり、非公開XHRや推測endpointを前提にしない。

ページはログインなしで閲覧できる。自動取得時は公式サイトの利用条件、robots、アクセス間隔を確認し、少なくとも0.25秒以上の逐次待機を置く必要がある。ページ本文には転載・再利用に関する注意書きがあるため、保存・再配布範囲は別途確認する。

## xG and future-use limitation

2024公式J.LEAGUE.jp match pageから、home/awayのmatch-level xGまたはxGAを380試合について取得できる経路は確認できなかった。従ってxGはC。season aggregateをmatch featureへ代用しない。

今回確認したstatsはすべてpost-match observed valuesである。将来featureにする場合も、target match自身の値は使用せず、各teamの過去matchだけを時系列でlagして作る必要がある。

## Practical classification

- **A**: Shots, Shots on Target, Possession, Corner kicks, Free kicks, Offsides, Fouls。
- **B**: YC / RCのcombined card display。yellow/redを別々に使うには追加のDOM確認が必要。
- **C**: xG/xGA、passes/pass accuracy、tackles、interceptions、blocks、crosses、team-level chances/duels、distance、sprints、high-intensity running。

2024については、Aの7項目は将来の公式match-level source候補としてcollector prototypeへ進む価値がある。一方、今回のA判定は2024限定であり、2015–2023のhistorical coverageを意味しない。

## Sources

- [J.LEAGUE official 2024 J1 match stats sample](https://www.jleague.jp/en/match/j1/2024/051510/stats/)
- [J.LEAGUE official 2024 J1 match page](https://www.jleague.jp/en/match/j1/2024/051510/)

