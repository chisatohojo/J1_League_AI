# J Stats snapshot delta feasibility audit

## 結論

2026-09-14 と 2026-09-21 の J Stats team snapshot は、同じ20クラブ・同じ37統計を持ち、snapshot間に各クラブちょうど1試合が追加された比較可能なpoint-in-time pairである。

しかし、既存の公式match-level datasetで直接検証できる `shots`、`shots on target`、`xG` とそのagainst側は、snapshot差分と20/20では一致しなかった。したがって、この1組のsnapshot差分を第8節のproduction match-level値として採用することはできない。snapshotの訂正、集計定義差、表示精度の影響をこの監査だけでは分離できない。

今後もsnapshot保存を続ける価値はあるが、差分復元は「各クラブ1試合」「同一source state」「直接match-level値との検証」を満たす区間に限定し、現時点ではproduction datasetを生成しない。

## 対象snapshot

| Source state | Snapshot | 構成 | Rows | 検証結果 |
|---|---|---:|---:|---|
| 2026-09-14 | `20260920T212008928504Z` | base 10 stats | 200 | complete |
| 2026-09-14 | `20260921T044103287576Z` | supplemental 27 stats | 540 | complete |
| 2026-09-14 reconstructed | 上記2件のread-only結合 | 37 stats × 20 clubs | 740 | valid |
| 2026-09-21 | `20260922T120000000000Z` | 37 stats × 20 clubs | 740 | valid |

両stateについて次を確認した。

- `(team_id, stat_name)` duplicate: 0
- missing stat: 0
- 各statのclub数: 20
- TeamMaster identity: 同一20クラブで整合
- stat set: 37/37で一致
- null value: 0
- 既存snapshotは変更していない

## Match transition

2026/27通常J1 completed datasetは70試合から80試合へ増加していた。新規10試合のmatch IDは次のとおり。

`34596`, `34587`, `34588`, `34589`, `34590`, `34592`, `34591`, `34593`, `34594`, `34595`

この10試合にはstable team IDで20クラブが登場し、各クラブのappearance増分は全てexactly 1だった。延期、重複、同一クラブの複数試合を含む区間ではない。従って、区間構造だけを見ればteam cumulative deltaを1試合分と比較できる条件を満たす。

## 37 statのsemantics分類

| 分類 | 件数 | Stats |
|---|---:|---|
| A: cumulative count | 18 | `shoot`, `shoot_on_target`, `suffer_shoot`, `suffer_shoot_on_target`, `pass_count`, `cross_count`, `chance_create`, `clear_count`, `tackle_count`, `block_count`, `intercept_count`, `recovery_count`, `dribble_count`, `air_battle_win_count`, `one_on_one`, `through_pass_count`, `foul_count`, `yellow_count` |
| B: cumulative decimal total | 3 | `expected_goals`, `expected_goals_against`, `expected_goals_against_excl_pk` |
| C: per-game average | 10 | `pass_count_per_game`, `distance_per_game`, `sprint_per_game`, `at_sprint_per_game`, `mt_sprint_per_game`, `dt_sprint_per_game`, `possession_distance_per_game`, `possession_sprint_per_game`, `un_possession_distance_per_game`, `un_possession_sprint_per_game` |
| D: percentage/rate | 6 | `ball_rate`, `tackle_rate`, `dribble_rate`, `air_battle_win_rate`, `pass_rate`, `through_pass_rate` |
| E: uncertain | 0 | なし |

この分類は既存collector metadataと公式表示labelに基づく。ここでのA～Eは値のsemantics分類であり、後述するproduction suitabilityのA～Dとは別である。

## Cumulative delta diagnostics

21 cumulative statsについて `state_20260921 - state_20260914` を20クラブごとに計算した。

- null delta: 0
- negative delta: 0
- 18 count statsのnon-integer delta: 0
- 明らかなimpossible value: 0
- 全740行で見たnegative delta: 127（全てper-game averageまたはrate）

Count deltaの観測rangeは、例えば `shoot` 2～33、`shoot_on_target` 0～11、`pass_count` 128～776、`foul_count` 5～20、`yellow_count` 0～5だった。Decimal cumulative deltaは `expected_goals` 0.1～4.0、`expected_goals_against` 0.2～4.1、`expected_goals_against_excl_pk` 0.2～4.1だった。

負の差分がaverage/rateに現れること自体は異常ではない。これらのraw differenceは1試合値を表さない。

## Official match-level direct validation

既存 `data/processed/jleague_match_xg/2026_27_j1_match_xg.csv` に新規10試合が全件存在することを確認し、home/awayをteam perspectiveへ展開した20 team sidesで比較した。Countはexact integer equality、xGはDecimalで比較し、任意のtoleranceは導入していない。

| Snapshot delta | Direct official value | Exact | Mismatch | Max absolute difference |
|---|---|---:|---:|---:|
| `shoot` | team shots | 11/20 | 9/20 | 2 |
| `shoot_on_target` | team shots on target | 16/20 | 4/20 | 1 |
| `suffer_shoot` | opponent shots | 11/20 | 9/20 | 2 |
| `suffer_shoot_on_target` | opponent shots on target | 16/20 | 4/20 | 1 |
| `expected_goals` | team xG | 1/20 | 19/20 | 0.43 |
| `expected_goals_against` | opponent xG | 1/20 | 19/20 | 0.43 |

6 anchors合計では56/120 cellsのみexactだった。

### Interpretation

- Count系にも差があり、表示丸めだけでは説明できない。
- J Stats cumulative xGは1桁表示、match-level xGは2桁であるため、xGにはcumulative roundingの影響が含まれ得る。
- ただしxGの最大差は0.43で、20件中exactは1件だけである。validation結果に合わせたtoleranceは設定しない。
- `expected_goals_against_excl_pk` は既存match-level datasetに直接anchorがないため検証不能だった。
- 不一致原因が過去試合値のrestatement/correctionか、J Statsとmatch pageの定義差か、表示精度かは、このsnapshot pairだけでは確定できない。

従って、単純なsnapshot差分は公式match-level valueの代替にならない。直接値との不一致はrestatement riskが現実に存在する証拠として扱う。

## Average/rateを逆算しない理由

Per-game averageやrateについて、例えば `new_avg * 8 - old_avg * 7` のような逆算は行わない。

- snapshotに公式`games_played`がない
- display rounding前の値が不明
- rateの分母とweighted aggregation semanticsが不明
- 過去値訂正の有無を分離できない

このため10 averagesと6 ratesは、point-in-time記録としては利用できるが、snapshot差分からmatch-level値を復元できない。

## Stat-by-stat production suitability

この表の判定は次の意味を持つ。

- A: 直接official match-level値で完全検証され、安全に採用可能
- B: cumulative totalのstrong candidateだが、追加snapshotとdirect validationが必要
- C: rounding、restatement、semanticsのためmatch-level reconstruction非推奨
- D: snapshot差分からmatch-level値を得ること自体が不可能

| Verdict | 件数 | Stats | 根拠 |
|---|---:|---|---|
| A | 0 | なし | 20/20で完全一致したdirect anchorなし |
| B | 14 | `pass_count`, `cross_count`, `chance_create`, `clear_count`, `tackle_count`, `block_count`, `intercept_count`, `recovery_count`, `dribble_count`, `air_battle_win_count`, `one_on_one`, `through_pass_count`, `foul_count`, `yellow_count` | count deltaは非負整数。ただしdirect anchor未検証で、1 transitionのみ |
| C | 7 | `shoot`, `shoot_on_target`, `suffer_shoot`, `suffer_shoot_on_target`, `expected_goals`, `expected_goals_against`, `expected_goals_against_excl_pk` | direct mismatch、decimal precision、またはdirect anchor欠如 |
| D | 16 | `pass_count_per_game`, `distance_per_game`, `sprint_per_game`, `at_sprint_per_game`, `mt_sprint_per_game`, `dt_sprint_per_game`, `possession_distance_per_game`, `possession_sprint_per_game`, `un_possession_distance_per_game`, `un_possession_sprint_per_game`, `ball_rate`, `tackle_rate`, `dribble_rate`, `air_battle_win_rate`, `pass_rate`, `through_pass_rate` | average/rate差分は1試合値ではない |

現時点でproduction suitability Aは0である。Bの14 statsもproduction採用ではなく、将来validation対象という位置付けに留める。

## Prospective collection policy

今後のJ Stats更新時もimmutable point-in-time snapshotを保存する。差分監査を行う場合は、最低限次を全て満たすこと。

1. 全stat pageが同じofficial source update dateを持つ。
2. 前後snapshotが同じstat set、20 clubs、exact TeamMaster identityを持つ。
3. official match historyから各クラブの区間内match数を確定する。
4. 各クラブexactly 1 matchでない区間はsingle-match reconstructionに使わない。
5. cumulative candidateのみ差分を計算し、average/rateは逆算しない。
6. direct official match-level値があるstatは全team sidesで照合する。
7. negative、non-integer count、null、identity mismatch、source-state混在をhard failureにする。
8. direct mismatchがあるstatはproduction match-level datasetへ昇格しない。

連続する複数のclean intervalとdirect anchorsで安定性を確認できた場合に限り、B判定statsの再評価が可能である。

## Limitations and scope

- 監査対象は2026-09-14から2026-09-21への1 transitionのみ。
- Snapshotはofficial point-in-time display stateであり、過去値が不変である保証はない。
- Sourceの内部precision、rate denominator、訂正履歴は公開snapshotから確認できない。
- Production match-level J Stats dataset、feature、model evaluation、predictionは生成・実行していない。
- 既存snapshotは変更していない。

## Final recommendation

Prospective snapshot collectionは継続する。一方、今回のdelta reconstructionは**feasibility evidenceとしては有用だが、production match-level reconstructionには不採用**とする。特にshots/SOT/xGの直接不一致が解消されない限り、他のcumulative totalsも無検証のまま安全とはみなさない。
