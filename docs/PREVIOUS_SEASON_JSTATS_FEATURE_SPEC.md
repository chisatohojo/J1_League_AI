# Previous-season J Stats team profile feature specification

## 1. Objective

J.LEAGUE公式の season-final team statistics を、完了済みseason `N` のチーム profile として保存し、翌season `N+1` のJ1 target matchにだけ付与する。

例:

```text
2019 final profile -> 2020 target matches
2020 final profile -> 2021 target matches
...
2025 final profile -> 2026/27 target matches
```

season `N` の試合を予測するために season `N` final profileを使うことは禁止する。これはmatch-levelの過去値を再構成する仕様ではなく、翌season向けのpoint-in-timeではない season-final profile仕様である。

## 2. Source and availability boundary

参照した既存監査では、J Stats team ranking routeは次の範囲で確認されている。

| Profile family | Available final seasons | Earliest target season |
|---|---:|---:|
| Non-xG team stats | 2018–2025 | 2019 |
| Team `expected_goals`, `expected_goals_against`, `expected_goals_against_excl_pk` | 2019–2025 | 2020 |

2015–2017はrouteがHTTP 200でもranking rowsがなく、profile sourceとして扱わない。2024/2025のmatch-level xG coverageやJ Stats snapshot deltaは、この仕様の入力として使わない。

J Statsの過去season pageは後日restatementされ得る。従って、このprofileは「当時その日に公開されていた値」ではなく、監査・取得時点で確認した `previous completed season profile` として扱う。

## 3. Input identity and linkage

- source: J.LEAGUE公式J Stats team ranking
- competition: J1
- identity: existing TeamMaster `team_id`
- resolution: exact `jleague_official` name/slug linkageのみ
- fuzzy match、部分一致、推測alias、canonical-name fallbackは禁止
- target seasonのhome/away clubはtarget J1 match datasetからstable `team_id`で取得
- profileはhome/away splitせず、team overall profileを両sideへlookupする

target clubの `team_id` に対するprofileは、数値の単純減算ではなく、competitionとseason labelの明示mappingで選ぶ。

| Target competition / season | Allowed profile source |
|---|---:|
| 2020 ordinary J1 | 2019 J1 final profile |
| 2021 ordinary J1 | 2020 J1 final profile |
| 2022 ordinary J1 | 2021 J1 final profile |
| 2023 ordinary J1 | 2022 J1 final profile |
| 2024 ordinary J1 | 2023 J1 final profile |
| 2025 ordinary J1 | 2024 J1 final profile |
| 2026/27 ordinary J1 | 2025 J1 final profile |

この表にないtarget competitionは自動mappingしない。特に2026 J1百年構想リーグは、既存project方針上、通常J1のevaluation targetとは別competitionであり、この previous-season J Stats profile featureのtargetには含めない。百年構想向けに2025 J1 profileを自動適用してはならない。将来別のcompetition-specific profile sourceが確立した場合は、別仕様として扱う。

TeamMasterで解決できない、またはprofile側のofficial identityが一致しない場合はjoin errorとし、別clubへの自動割当を行わない。

## 4. Feature groups and final candidate list

38-stat archiveを一括投入せず、意味のある4 groupを定義する。初回実装で採用する候補は以下の6 fieldsに限定する。

| Group | Final candidate field | Role | Earliest target |
|---|---|---|---:|
| Attack | `expected_goals_per_match` | previous-season attacking chance quality | 2020 |
| Attack | `shoot_on_target_per_match` | attacking shot quality/volume | 2019 |
| Defense | `expected_goals_against_per_match` | previous-season chance prevention | 2020 |
| Defense | `suffer_shoot_on_target_per_match` | prevention of opponent SOT | 2019 |
| Possession / Build-up | `ball_rate` | official possession percentage | 2019 |
| Possession / Build-up | `pass_rate` | official pass success rate | 2019 |

Physical / Running is retained as a separate deferred group, not part of the first candidate interface:

- `distance_per_game`
- `sprint_per_game`

これらは意味のある候補だが、official definition/version consistencyを実装時に再確認してから追加する。`chance_create`, `intercept_count`, `recovery_count`, `through_pass_count` などのcountは、全てを同時投入するのではなく、次のnormalization gateを通過した場合のみ候補に昇格する。

## 5. Normalization policy

### 5.1 Counts and decimal totals

season lengthが異なるため、累積totalをそのままseason間比較しない。

- `expected_goals`, `expected_goals_against`: team J1 appearance countで割った `*_per_match` を候補とする。
- `shoot_on_target`, `suffer_shoot_on_target`, その他count: games-played basisとofficial unitが安全に確定できる場合だけper-match化する。
- games-played basis、値のprecision、stat definitionが安全に確認できない場合はnullではなく「未提供」とし、0埋め・league average補完・推測除算をしない。

J1 match datasetから得たappearance countを denominatorとして使用する場合、対象seasonの全J1 scheduleがcompleteで、team identityが100%解決されていることを事前にassertする。これはJ Statsに存在しない値を推測することではなく、対象seasonの公式J1 match participation countを固定するための条件である。

### 5.2 Rates and per-game values

公式の rate / percentage / per-game valueは、表示値とunitを保持したまま候補とする。rateをtotalへ戻したり、別rate同士を合成したりしない。

### 5.3 Snapshot delta prohibition

`J_STATS_SNAPSHOT_DELTA_FEASIBILITY.md`で確認した通り、snapshot差分はmatch-level reconstructionに使わない。特にshots/SOT/xG系でdirect match-level値との不一致が確認されているため、season profileの値をdeltaから生成してはならない。

## 6. Missing and promoted-team policy

前年J1に所属していなかったpromoted teamには previous-season J1 profileがない。

保存形式は次の通りとする。

```text
profile_value = null
has_previous_j1_profile = false
profile_season = explicit competition/season mapping
```

禁止事項:

- league averageによる補完
- 0埋め
- 他division、Cup、別teamのprofile流用
- TeamMasterのfuzzy resolution

前年profileが存在する場合は `has_previous_j1_profile = true` とし、stat単位で欠損がある場合はstat-level missing maskを保持する。profile全体が欠けている場合と個別statが欠けている場合を区別する。

将来model interfaceでは、missing indicatorとbaseline fallbackを別途事前定義する余地があるが、今回の仕様書ではmodel側の補完方式を決めない。

## 7. Proposed target-row schema

将来生成するdatasetはtarget J1 matchごとに1 rowとし、match自身のresultやseason-final target-season statsをfeature sourceに含めない。

```text
match_id
season
match_date
home_team_id
away_team_id

home_profile_season
away_profile_season
home_has_previous_j1_profile
away_has_previous_j1_profile

home_previous_expected_goals_per_match
away_previous_expected_goals_per_match
home_previous_shoot_on_target_per_match
away_previous_shoot_on_target_per_match
home_previous_expected_goals_against_per_match
away_previous_expected_goals_against_per_match
home_previous_suffer_shoot_on_target_per_match
away_previous_suffer_shoot_on_target_per_match
home_previous_ball_rate
away_previous_ball_rate
home_previous_pass_rate
away_previous_pass_rate

home_profile_source_snapshot
away_profile_source_snapshot
```

最初はhome/awayのraw profile valuesを基本とする。差分、ratio、合成strength、interactionはこの仕様のfeature interfaceに含めない。これにより、個別statを順番に試すfeature lotteryを避ける。

## 8. Chronology and leakage safeguards

必須ルール:

1. ordinary J1 targetは、上記の明示mappingで指定されたprofile seasonのみ参照する。`target_season - 1` の数値減算を実装規則にしない。
2. target season `N` のseason-final statsは同seasonのどのmatchにも参照しない。
3. future season、target match result、target match stats、target season final aggregateをprofile作成に使わない。
4. profileのsource retrieval dateと公式表示update dateを別フィールドで保持する。
5. 後日restatementされた過去profileは、取得時点の値として再現可能なsnapshot/artifactから読む。
6. home/awayのprofile lookupはstable `team_id`で行う。
7. 2026 J1百年構想リーグはこのmappingのtarget外であり、2025 J1 profileを流用しない。
8. target datasetのseason範囲外（2025/2026を含むopened data）のperformanceを、この仕様の候補feature選択に使わない。

このprofileは「previous completed season」を使うため、season開始前に常に利用可能だったことを保証するものではない。将来のprospective運用では、各profileのretrieved/source stateを記録し、事前にfreezeする。

## 9. Source metadata and artifact requirements

各season/profile statについて、少なくとも次を保持する。

```text
profile_season
snapshot_id or retrieval_id
source_url
source_update_date
retrieved_at
raw_sha256
stat_name
unit
value_type
team_id
official_club_id
official_club_name
games_played_basis
```

`source_update_date` が日付のみの場合、exact timestampを推測しない。`games_played_basis` は公式表示値なのか、complete J1 match datasetから検証済みのappearance countなのかを明示する。

## 10. Opened-data discipline

2025はspent test、2026/27 first 80 matchesもopened dataである。これらのperformanceやcoverageを見て、候補stat、normalization、missing policy、model仕様を変更しない。

この仕様は新しいmodel評価を行う文書ではない。将来新しい情報層を検討する場合は、別のresearch cycleとして事前に候補groupと評価protocolをfreezeする。

## 11. Future model interface

将来のmodel側には、次の入力契約だけを渡す。

- target match identity
- home/away stable team ID
- previous profile season
- fixed candidate values
- profile availability/missing indicators
- source snapshot provenance

model側でのimputation、scaling、feature selection、group比較はこの仕様の範囲外であり、別途事前登録する。

## 12. Implementation next step

実装前に以下をread-only validationとして確認する。

1. 2018–2025の各stat routeについて、20/20または当該seasonのJ1 club数を取得できるか。
2. 2019–2025のxG/xGA rowsとofficial TeamMaster identityをexact照合する。
3. profile seasonごとのJ1 appearance denominatorを完全なmatch datasetから検証する。
4. count/per-match候補のunitとroundingをmanifestへ保存する。
5. promoted clubでnull profileとavailability flagが期待通りになるfixture testを作る。
6. target competition / seasonが、上記explicit mappingで許可されたprofile season以外を参照しないleakage testを作る。

このread-only validationが完了するまでcollector、feature generation、model fitting、evaluation、predictionは開始しない。

## 13. Explicitly out of scope

- 外部web調査
- collector実装
- feature dataset生成
- match-level J Stats delta reconstruction
- same-season prediction
- model fitting / Accuracy / Log Loss / Brier
- prediction
- parameter tuning
- feature importance
- 2025/2026 opened-dataを用いた仕様変更
- commit / push
