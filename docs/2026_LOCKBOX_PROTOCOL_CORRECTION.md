# 2026 Lockbox Protocol Correction

確認日: 2026-09-20

## Protocol correction

旧preflightの`270 matches`は、次の異なるcompetitionを混在させた誤ったinvariantだった。

- 2026 J1百年構想リーグ: 200 matches
- 2026/27通常J1のcompleted matches: 70 matches

両competitionは方式が異なるため、final evaluation targetへ混在させない。

## Interim evaluation target

今回のinterim targetは **2026/27 明治安田J1リーグのcompleted matchesのみ** とする。

| check | result |
|---|---:|
| target rows | 70 |
| unique match_id | 70 |
| missing date | 0 |
| missing teams | 0 |
| missing scores | 0 |
| missing result | 0 |
| deterministic chronology | passed |
| future schedule rows excluded | 310 |

schedule全380試合のうち、未完了310試合はtargetへ含めない。百年構想リーグ200試合もtargetへ含めない。

## Elo policy

freeze済みModel A/Bの`elo_diff`は、2015–2025 ordinary J1と、targetより前に完了した2026/27 ordinary J1だけを`match_date, match_id`順でreplayする。百年構想リーグはElo updateへ追加しない。target自身およびfuture 2026 resultも使用しない。

## Domestic Rest policy

Model Bのfreeze済み国内competitive history familyは次のとおり。

- J1
- J.League Cup
- Emperor's Cup

2025については、J1 380件、J.League Cup 56件、Emperor's Cup 41件を確認済みである。

百年構想リーグ200件は、通常J1のElo/model targetには使わない。ただし、target以前の国内公式戦として、日付とTeamMaster identityだけをDomestic Rest chronologyへ利用する。百年構想リーグのscore/resultはEloやmodel targetへ使用しない。

今回のpreflightでは百年構想リーグ400 team appearancesがTeamMasterで解決でき、全matchが2026/27 target期間より前に位置することを確認した。一方、2026 J.League Cup / Emperor's Cupのprocessed historyは存在せず、既存collectorも2026 league probeがないため、この2 competitionの2026履歴は未準備である。

従って、**Model Aはinterim targetに対して準備可能、Model Bは2026 Cup/Emperor履歴の要否確認・準備が完了するまで評価readyではない**。不足分をJ1-only restへ置換しない。

## Lockbox discipline

このprotocolをmetrics確認前にfreezeする。interim 70件の結果を見ても、以下を変更しない。

- featureの追加・削除
- EloのK / home advantage
- Logistic parameter
- Domestic Rest定義・clipping・欠損処理
- Champion / Challengerの仕様

prediction、Accuracy、Log Loss、Brier、class distribution、confusion matrix、individual result表示は今回実行していない。

season終了後、同一仕様で2026/27 ordinary J1のfull 380 completed matchesを再評価する。百年構想リーグは引き続きevaluation target外とする。

