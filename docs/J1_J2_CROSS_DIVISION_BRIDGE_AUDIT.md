# J1/J2 cross-division bridge audit

確認日: 2026-09-20

対象は2015〜2024のJ1、J2、J.League Cup、Emperor's Cupの保存済みprocessed CSVのみ。AFC、J3、2025、2026は使用していない。TeamMaster、collector、CSVは変更していない。

## 判定方法

各seasonのJ1/J2 membershipをleague matchのstable `team_id` unionから作成した。Cup側は、J.League Cupでは`jleague_data_site` exact aliasを再照合し、Emperor's Cupでは既存TeamMasterのcanonical/source aliasへのexact一致だけをsafe candidateとした。trim、NFKC、fuzzy matching、canonical fallbackによるproduction resolutionは行っていない。

分類は、両sideのsafe identityを使い、`J1 vs J1`、`J1 vs J2`、`J2 vs J1`、`J2 vs J2`、`J1 vs other`、`J2 vs other`、`other vs other`とした。`J1 vs J2`と`J2 vs J1`の合計をbridgeとする。

## Season diagnostics

| season | J.League Cup total | Cup safely resolved | Cup bridge | Emperor's Cup total | Emperor safe resolved | Emperor bridge | combined bridge |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 2015 | 55 | 55 | 0 | 23 | 17 | 6 | 6 |
| 2016 | 55 | 55 | 0 | 26 | 17 | 5 | 5 |
| 2017 | 59 | 59 | 0 | 31 | 17 | 8 | 8 |
| 2018 | 69 | 69 | 16 | 34 | 20 | 12 | 28 |
| 2019 | 69 | 69 | 14 | 31 | 17 | 7 | 21 |
| 2020 | 28 | 28 | 1 | 3 | 3 | 1 | 2 |
| 2021 | 69 | 69 | 0 | 35 | 19 | 6 | 6 |
| 2022 | 69 | 69 | 12 | 40 | 22 | 14 | 26 |
| 2023 | 73 | 73 | 12 | 37 | 22 | 13 | 25 |
| 2024 | 51 | 36 | 13 | 31 | 12 | 5 | 18 |
| **total** | **597** | **579** | **68** | **291** | **166** | **77** | **145** |

J.League Cupの2024年は下位category側の未解決名が残るため、全51試合のうち36試合がfully resolvedだった。Emperor's CupはJFA由来のraw nameを既存aliasへexact照合した結果、291試合中166試合が両side safe resolvedだった。未解決sideを推測で補完していないため、bridge数は保守的な下限である。

## Bridge club coverage

bridgeに登場したstable IDの延べseason別集合は以下。IDは既存TeamMasterのstable IDである。

| season | bridge club IDs |
|---:|---|
| 2015 | team_0001, team_0003, team_0008, team_0010, team_0011, team_0013, team_0016 |
| 2016 | team_0001, team_0005, team_0008, team_0010, team_0021, team_0025, team_0028, team_0033 |
| 2017 | team_0001, team_0002, team_0005, team_0018 |
| 2018 | 16 clubs |
| 2019 | 16 clubs |
| 2020 | team_0002, team_0015 |
| 2021 | 7 clubs |
| 2022 | 11 clubs |
| 2023 | 12 clubs |
| 2024 | 10 clubs |

全期間で、bridgeに登場したJ1-side stable IDは17、J2-side stable IDは少なくとも12確認できた。2017のreturning club `team_0025`と2024のreturning club `team_0007`はbridgeへ登場した。一方、2018 `team_0018/team_0026`、2019 `team_0015`、2020 `team_0009`、2021 `team_0004`、2022 `team_0007`、2023 `team_0019/team_0032`は、この保守的なidentity判定ではbridge重複を確認できなかった。

## Chronology

全competitionを`match_date`、competition discriminator、source match IDから作る内部keyで並べられる。J1/J2は`j1:<match_id>` / `j2:<match_id>`、Cupは各sourceのmatch ID namespaceを使えば衝突しない。

同一teamが同一calendar dateにJ1/J2/Cup/Emperor's Cupへ複数出場するケースは、今回の全件監査で**0件**だった。従ってpre-match replayのstrict chronological orderingは実装可能である。

## Result suitability

J1/J2 processed dataには`result`があり、0=away win、1=draw、2=home winとして利用可能。J.League Cup/Emperor's Cupにもprocessed resultは存在するが、CupではPK・extra-time・tie winnerを90分resultへ再解釈していないことを個別に再検証する必要がある。今回の監査では新しいresult推測や補正は行わず、既存processed値をそのまま確認対象とした。

## Assessment

**判定: B — bridge matchは存在するがcoverageは限定的。**

2015〜2024で145 bridge matchは確認でき、J1/J2のrating populationをつなぐ情報は実在する。ただし2015〜2017はJ.League Cup bridgeが0で、Emperor's Cup中心であり、2024はCup identityの未解決も残る。したがって「十分にscale alignmentが保証される」とは言えないが、safe identityを増やさず保守的なsubsetでCup-bridged J1+J2 Eloを実験する価値はある。

次段階では、identity未解決のEmperor's Cup側を勝手に補完せず、safe-resolved bridgeだけを使うvariantと、Cup resultの90分定義を明示的に検証したvariantを分けて評価する必要がある。
