# J1–J2 Cup regulation-time bridge dataset

作成日: 2026-09-29

## Readiness verdict

**`READY_TO_FREEZE_CUP_BRIDGE_EVALUATION`**

固定済み145 candidatesを変更せず、全行の90分score/resultを公式sourceからmaterializeした。全145行が`CONFIRMED_REGULATION_SCORE`、unresolvedは0行である。今回実施したのはdataset作成とsource/identity/chronology validationまでであり、Elo update、model fit/evaluation、prediction、Accuracy / Log Loss / Brier計算は実施していない。

後続evaluationは本datasetと以下のSHAをfreeze specificationへ固定した後、一度だけ実行する。

## Frozen artifacts

| artifact | path | rows | SHA-256 |
|---|---|---:|---|
| Candidate manifest | `data/processed/cup_regulation_results/2015_2024_j1_j2_bridge_candidates.csv` | 145 | `f44aa8785c80b48dc03acc4c206cbd59c4acc048d22d59579c865fbe990b5dc3` |
| Regulation result dataset | `data/processed/cup_regulation_results/2015_2024_j1_j2_bridge_regulation.csv` | 145 | `f7dc0151299a01d8dcad5e0a1235759cad53d9784740bf81320cc0b5fb985b64` |

SHAはUTF-8、headerあり、LF、固定column/orderのcanonical CSV bytesに対する値である。candidate manifestはnetwork取得前に既存bridge logicだけから作成した。以後、source結果を理由にcandidateを追加・削除・再選択していない。

## Candidate membership gate

- Candidate rows: exactly 145
- J.League Cup: exactly 68
- Emperor's Cup: exactly 77
- Duplicate `candidate_key`: 0
- Missing stable TeamMaster ID: 0
- Same home/away stable ID: 0
- Same team / same calendar date duplicate appearance: 0
- Existing auditのcompetition/season分布との相違: 0

`candidate_key`は`competition:source_match_id`。J1/J2 membership、Cup side identity、TeamMaster mappingは既存 [J1_J2_CROSS_DIVISION_BRIDGE_AUDIT.md](J1_J2_CROSS_DIVISION_BRIDGE_AUDIT.md) と同じlogicを再利用した。TeamMaster、alias、retained Cup inputは変更していない。fuzzy matching、trim/NFKC、current clubからの逆算は行っていない。

## Coverage

| competition | season | candidates | confirmed | unresolved | confirmed rate | extra-time positive evidence | PK positive evidence |
|---|---:|---:|---:|---:|---:|---:|---:|
| Emperor's Cup | 2015 | 6 | 6 | 0 | 100% | 1 | 1 |
| Emperor's Cup | 2016 | 5 | 5 | 0 | 100% | 3 | 1 |
| Emperor's Cup | 2017 | 8 | 8 | 0 | 100% | 0 | 0 |
| Emperor's Cup | 2018 | 12 | 12 | 0 | 100% | 2 | 2 |
| Emperor's Cup | 2019 | 7 | 7 | 0 | 100% | 1 | 0 |
| Emperor's Cup | 2020 | 1 | 1 | 0 | 100% | 0 | 0 |
| Emperor's Cup | 2021 | 6 | 6 | 0 | 100% | 2 | 1 |
| Emperor's Cup | 2022 | 14 | 14 | 0 | 100% | 2 | 1 |
| Emperor's Cup | 2023 | 13 | 13 | 0 | 100% | 4 | 4 |
| Emperor's Cup | 2024 | 5 | 5 | 0 | 100% | 2 | 0 |
| **Emperor's Cup subtotal** | | **77** | **77** | **0** | **100%** | **17** | **10** |
| J.League Cup | 2018 | 16 | 16 | 0 | 100% | 0 | 0 |
| J.League Cup | 2019 | 14 | 14 | 0 | 100% | 0 | 0 |
| J.League Cup | 2020 | 1 | 1 | 0 | 100% | 0 | 0 |
| J.League Cup | 2022 | 12 | 12 | 0 | 100% | 0 | 0 |
| J.League Cup | 2023 | 12 | 12 | 0 | 100% | 0 | 0 |
| J.League Cup | 2024 | 13 | 13 | 0 | 100% | 2 | 0 |
| **J.League Cup subtotal** | | **68** | **68** | **0** | **100%** | **2** | **0** |
| **Total** | | **145** | **145** | **0** | **100%** | **19** | **10** |

`extra_time_played`と`penalty_shootout_played`は明示的positive official evidenceがある場合だけ`True`。明示がない行は空欄であり、`False`または「実施なし」と推測しない。したがって表の件数はpositive evidence countである。

## Official sources and bounded acquisition

| source type | result rows | acquisition |
|---|---:|---|
| J.League Data Site SFMS02 | 68 | 固定candidateが保持する68 official match IDsから取得 |
| JFA schedule JSON | 58 | 既存local cacheを再利用。network再取得なし |
| JFA official match page | 19 | JSONがtotal-onlyだった固定19 match identitiesだけ取得 |

新規lookup集合はnetwork前にexactly 87 URLへ固定した。domainは`data.j-league.or.jp`と`www.jfa.jp`のみ。最初の構造確認2件と残る85件を各1回取得し、合計87 distinct official requestsだった。broad crawl、search、numeric ID enumeration、guessed ID、third-party sourceは使用していない。

新規87 sourceは`data/raw/cup_regulation_results/`に、URL SHA-256をfilename keyとするHTML/metadata pairで保存した。metadataは次を保持する。

- requested/final source URL
- HTTP status
- `retrieved_at_utc`
- raw byte length
- raw SHA-256
- competition
- season
- source match ID

58 JFA rowsを支える2015–2024の10 schedule JSONは既存`data/raw/emperors_cup/`のraw/metadataを再利用した。全97 unique source files（87 detail + 10 schedule）についてURL、status、bytes、SHA-256、UTC retrieval timestampをoffline rebuild時に再検証する。raw/metadataの片側欠損または値不一致はhard failであり、再取得で黙って上書きしない。

## Identity contract

全145行でcompetition、season、source match ID、match date、home/away order、stable TeamMaster IDsをcandidate manifestと一致させた。

JFAはschedule/detail sourceのhome/away表示をcandidate raw nameと完全一致で検証する。J.League SFMS02はlistingの公式略称とdetailの公式正式名が異なる場合があるため、既存TeamMasterのexact aliasまたはdetailに埋め込まれた公式club profile slugを既存`source_club_id`へexact照合する。slug mismatchはhard failであり、名前の部分一致・正規化・fuzzy matchは行わない。

## Regulation-time semantics

```text
regulation_home_score = first_half_home + second_half_home
regulation_away_score = first_half_away + second_half_away
regulation_result = 0 (Away), 1 (Draw), 2 (Home)
```

採用順位は次のとおり。

1. JFA official structured JSONの明示的first/second-half fields
2. Exact match identityを持つJ.League/JFA official detail pageの明示的period breakdown
3. 今回は不要だったが、同一identityを明示するofficial report/PDF
4. それ以外は`UNRESOLVED_REGULATION_SCORE`

final score、winner、延長score、PK winnerから90分resultを逆算しない。`exMatch=false`だけを延長なしの根拠にしない。90分同点後に延長またはPKで勝者が決まった行も`regulation_result=1`である。final scoreと明示periodのarithmetic不一致、period欠損、home/awayまたはdate不一致はhard failする。

## Dataset schema and validation

Datasetは次を保持する。

```text
candidate_key, competition, season, source_match_id, match_date,
home_team_id, away_team_id,
regulation_home_score, regulation_away_score, regulation_result,
extra_time_played, penalty_shootout_played,
final_home_score, final_away_score,
source_url, source_type, raw_sha256,
resolution_status, resolution_reason
```

Confirmed scoreはnon-negative integerで、0/1/2 classをscoreから再検証した。unresolved行が将来発生する場合はcandidateを削除せず、score/resultをnullのままstatus/reason/source provenanceとともに残す。保存datasetは同じraw cacheから2回buildしてbyte-for-byte一致し、offline CLI再実行でも保存済みSHAと一致した。

## Chronology contract for the next task

- Eloへ入れられるのは`CONFIRMED_REGULATION_SCORE`だけ。
- target J1 matchよりstrictly prior dateのCup matchだけを反映する。
- same-dateは既存のconservative batchingを使い、全pre-match値取得後にresultを反映する。
- 延長・PK outcomeはElo updateへ使わない。
- J1/J2 identityは本manifestのstable TeamMaster IDsを使用し、unresolved sideを推測しない。
- target/current resultをfuture historyへ先入れしない。
- 次工程でcandidate SHA、dataset SHA、confirmed subset、Elo variant、fold、採用ruleをfreezeするまでevaluationを実行しない。

## Offline reproduction

```powershell
.\.venv\Scripts\python.exe -m src.collect.cup_regulation_results --offline
```

このcommandはcandidateを既存inputsから再構築し、保存manifestとSHAを照合してから、保存済みrawだけで145-row datasetを再構築する。network accessは行わない。
