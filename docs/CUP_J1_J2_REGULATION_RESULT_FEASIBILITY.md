# J1–J2 Cup regulation-time result source feasibility

確認日: 2026-09-29

## Verdict

**`PROCEED_TO_CUP_REGULATION_RESULT_DATASET`**

既存のidentity-safe 145試合（J.League Cup 68、Emperor's Cup 77）を変更せず、公式sourceの明示的な前半・後半scoreから90分resultを作るsource contractは成立する。今回実施したのはlocal cache監査、既知の公式linkによる6ページの代表sample確認、strict offline parser prototypeまでである。145試合のfull dataset、Elo update、model fit/evaluation、prediction、metric計算は実施していない。

`PROCEED`は全145行が取得済みという意味ではない。現時点では58行だけがlocal JSONから確定可能で、残る87行は次工程で公式detailを保存・検証する必要がある。

## Frozen candidate scope

候補集合は [J1_J2_CROSS_DIVISION_BRIDGE_AUDIT.md](J1_J2_CROSS_DIVISION_BRIDGE_AUDIT.md) と既存実装のexact identity判定をread-onlyで再現した。TeamMaster、collector、processed CSV、候補集合は変更していない。

| season | League Cup | Emperor's Cup | total |
|---:|---:|---:|---:|
| 2015 | 0 | 6 | 6 |
| 2016 | 0 | 5 | 5 |
| 2017 | 0 | 8 | 8 |
| 2018 | 16 | 12 | 28 |
| 2019 | 14 | 7 | 21 |
| 2020 | 1 | 1 | 2 |
| 2021 | 0 | 6 | 6 |
| 2022 | 12 | 14 | 26 |
| 2023 | 12 | 13 | 25 |
| 2024 | 13 | 5 | 18 |
| **total** | **68** | **77** | **145** |

J1/J2 season membershipと両sideのstable `team_id`は既存TeamMasterのexact resolutionだけを使用する。raw name、正規化名、fuzzy match、未解決opponentから候補を追加しない。

## Required score semantics

Elo用のresultは前半と後半の合計だけから決める。

```text
regulation_home_score = first_half_home + second_half_home
regulation_away_score = first_half_away + second_half_away
regulation_result = 0 (Away), 1 (Draw), 2 (Home)
```

延長各half、延長後final、PK score、match winnerは別fieldで保持し、`regulation_result`には入れない。たとえば90分0–0、延長1–1、PK 5–4はDrawである。final winner、total scoreだけ、`exMatch=false`だけから90分resultを推測しない。

## Local cache audit

### J.League Cup

- Retained CSVは2015–2024で597行、bridge候補は68行。`source_match_id`とSFMS02への公式linkはあるが、score fieldはprocessed schemaへ保持されていない。
- 保存済みSFMS01 listing HTML 12件とmetadata 12件はbytes/SHA-256整合を確認した。listingのscore cellは存在するが、延長・PKを含む最終表示になり得るため90分scoreとして使わない。
- 68候補のlisting scoreはすべて単純な`N-N`表示だったが、それだけでは延長未実施を証明しない。local evidenceだけで確定できる候補は **0/68**、SFMS02 lookupが必要なのは **68/68**。

### Emperor's Cup

- Retained CSVは2015–2024で291行、bridge候補は77行。processed schemaにはscoreがない。
- 保存済みJFA schedule JSON 12件とmetadata 12件はbytes/SHA-256整合を確認した。
- 77候補中 **58** はJSONに`home/awayTeamScore1st`と`home/awayTeamScore2nd`の4fieldが揃い、local evidenceだけで90分scoreを確定できる。
- 残る **19** はtotal scoreだけで、`UNRESOLVED_REGULATION_SCORE`とする。対象は2015年6件、2016年5件、2017年8件であり、公式match detailまたは公式reportのlookupが必要。
- 既存JSONのpositive flagから延長15件、PK 10件は確認できるが、これは安全な下限である。2015 m63はJSONの`exMatch=false`に反して公式detailが延長・PKを明示するため、negative flagを「延長なし」の証明に使わない。

## Official source audit

既存のlisting/candidateが保持する公式link、またはそこから既知の公式archive routeだけを使った。URL推測、numeric ID列挙、第三者source、broad crawlは行っていない。新しいraw fileも保存していない。

| competition | season / official match | candidate | explicit 90-minute score | separate extra time / PK | outcome |
|---|---|---:|---:|---:|---|
| League Cup | 2018 [SFMS02 21051](https://data.j-league.or.jp/SFMS02/?match_card_id=21051) | yes | 1–1 | no / no | Draw |
| League Cup | 2024 [SFMS02 29640](https://data.j-league.or.jp/SFMS02/?match_card_id=29640) | yes | 0–1 | no / no | Away |
| League Cup | 2024 final [SFMS02 31274](https://data.j-league.or.jp/SFMS02/?match_card_id=31274) | no; semantics control | 2–2 | 1–1 / 5–4 | Draw |
| Emperor's Cup | 2015 [m63](https://www.jfa.jp/match/emperorscup_2015/match_page/m63.html) | yes | 0–0 | 0–0 / 2–3 | Draw |
| Emperor's Cup | 2016 [m71](https://www.jfa.jp/match/emperorscup_2016/match_page/m71.html) | yes | 1–1 | 3–0 / none | Draw |
| Emperor's Cup | 2023 [m59](https://www.jfa.jp/match/emperorscup_2023/match_page/m59.html) | yes | 0–0 | 1–1 / 5–4 | Draw |

確認sampleは6件（候補5件、非候補のsemantic control 1件）、90分score確認6件、unresolved 0件だった。

J.League Data Site SFMS02はsampled 2018/2024 pageで前半・後半、存在する場合は延長前半・延長後半、PKを別表示する。31274ではmain totalが3–3、90分は2–2、延長は1–1、PKは5–4であり、listing/final totalを90分値に流用できないことも確認した。League Cupのbridge seasonは2018–2024で、保存済みSFMS01の各candidate official IDからSFMS02へexactに結べる。

JFA match pageはsampled 2015/2016/2023で各periodを分離する。schedule JSONはseasonによりfield coverageが異なり、古いtotal-only rowはmatch detailへfallbackする必要がある。代表sampleではlegacy detail routeが現在もhistorical breakdownを保持していたが、全19件のarchive coverageは次工程で個別にhard-fail検証する。

## Source hierarchy and resolution rules

1. 公式structured resultに前半・後半scoreが明示されている場合だけ、その和を採用する。
2. なければ、candidateの公式match IDとhome/awayがexact一致する公式detail pageのperiod breakdownを使う。
3. なければ、同じmatch identityを明示するJ.LEAGUE/JFA公式reportまたはPDFの90分・延長内訳を使う。
4. それ以外は`UNRESOLVED_REGULATION_SCORE`とし、Elo入力から除外する。

次はhard failである。

- official match ID、season、home/away、candidate stable team IDの不一致
- 前半/後半fieldの片側欠損、非整数、重複またはscore arithmeticの矛盾
- 延長fieldの部分欠損、`exMatch`との矛盾、PKの片側欠損または同点
- final/PK/winnerしかなく、90分scoreを明示できないsource
- raw bytesとmetadataのURL、retrieval time、SHA-256を結べないrecord

## Strict offline prototype

`src/collect/cup_regulation_result_prototype.py`はnetwork accessを持たず、既知の1試合だけを解決する。

- SFMS02: official URL内の`match_card_id`、exact home/away、前後半、延長、final arithmetic、PK構造を検証し、raw bytesからSHA-256を計算する。
- JFA JSON: detached rowやcaller supplied digestを信用せず、raw JSONからexact `matchNumber`を一意に選択し、exact home/awayとperiod fieldsを検証し、raw bytesからSHA-256を計算する。
- total-only JFA rowは、final scoreを転用せず`UNRESOLVED_REGULATION_SCORE`を返す。
- `regulation_result`のclass orderは既存modelと同じ0=Away、1=Draw、2=Homeである。

offline fixtureは公式pageの必要最小構造だけを縮約したもので、raw archiveではない。production materializationでは必ず公式raw全体とmetadataを保存する。

## Coverage estimate and next stage

| competition | candidates | locally confirmed | official detail lookup required | demonstrated semantic failure |
|---|---:|---:|---:|---:|
| League Cup | 68 | 0 | 68 | 0 in sample |
| Emperor's Cup | 77 | 58 | 19 | 0 in sample |
| **total** | **145** | **58** | **87** | **0 in sample** |

次段階は、候補集合を再選択せず、68個の既知SFMS02 linkと19個の既知JFA match identityだけをboundedに取得すること。各rawにsource URL、`retrieved_at`、SHA-256を保存し、145件すべてについてidentity、period arithmetic、status、一意性を監査する。1件でも明示的な90分scoreを得られなければ、その行だけunresolvedとして除外し、推測で埋めない。

このsource-feasibility判定は後続dataset materializationを許可するだけで、Cup-bridged Elo experimentの再実行やmodel採否を許可しない。

## Future chronology / Elo contract

- target J1 matchよりstrictly prior dateに完了したCup matchだけをElo stateへ反映する。
- 同日試合は既存Elo contractのconservative batchingに従い、全pre-match値取得後にresultを反映する。
- Elo resultは90分の0/1/2だけ。延長、PK、winnerは更新値に使わない。
- J1/J2 identityは既存TeamMasterのexact mappingだけを使い、unresolved sideを補完しない。
- current target自身またはsame-date peerのresultをpre-match historyへ先入れしない。
- Elo parameter、既存145候補、model training/validation targetをこのdataset作成工程で変更しない。
