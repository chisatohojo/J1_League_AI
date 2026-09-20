# Elo promotion transition audit

確認日: 2026-09-20

## Summary

2015～2024のJ1-only Elo stream（initial 1500, K=30, HA=175）を再生し、2016～2024のmembership transitionを監査した。2015は前年membershipがlocalにないためpromotion status unknownとして除外した。

- promotion events: 22
- first-time entry: 12
- returning entry: 10
- first-time entry pre-match Elo = 1500.0: 全12件
- returning entry pre-match Elo = previous J1 tenure終了後post-match Elo: 全10件一致
- returning clubのJ1不在期間中のrating変化: 全10件なし

## Transition examples

| season | team_id | entry | first match | first pre Elo | previous match | previous post Elo | absent days | absent seasons |
|---:|---|---|---:|---:|---:|---:|---:|---:|
| 2016 | team_0004 | first-time | 17896 | 1500.000 | - | - | - | - |
| 2016 | team_0007 | first-time | 17894 | 1500.000 | - | - | - | - |
| 2016 | team_0022 | first-time | 17901 | 1500.000 | - | - | - | - |
| 2017 | team_0025 | returning | 19078 | 1372.134 | 17104 | 1372.134 | 461 | 1 |
| 2018 | team_0018 | returning | 20748 | 1400.772 | 18198 | 1400.772 | 478 | 1 |
| 2018 | team_0026 | returning | 20749 | 1402.852 | 18198 | 1402.852 | 478 | 1 |
| 2019 | team_0015 | returning | 21494 | 1375.490 | 17103 | 1375.490 | 1189 | 3 |
| 2020 | team_0009 | returning | 22785 | 1506.481 | 21045 | 1506.481 | 448 | 1 |
| 2020 | team_0032 | first-time | 22791 | 1500.000 | - | - | - | - |
| 2021 | team_0004 | returning | 24983 | 1322.275 | 18199 | 1322.275 | 1578 | 4 |
| 2023 | team_0032 | returning | 28165 | 1378.558 | 25348 | 1378.558 | 441 | 1 |
| 2024 | team_0007 | returning | 30432 | 1426.312 | 27630 | 1426.312 | 476 | 1 |

Team nameは既存probe/masterのraw表示値を参照した。cache上の一部日本語表記は既存encoding状態のため、identity判定にはstable `team_id`だけを使用した。

## Promotion-season adaptation: 2020-2024 OOF only

promotion clubのseason内J1 appearance numberで分類した。試合に両方のpromotion clubが関与する場合は最小appearance numberを使用した。

| appearance bucket | count | Accuracy | Log Loss | Brier |
|---|---:|---:|---:|---:|
| 1-3 | 31 | 0.354839 | 1.103367 | 0.666911 |
| 4-10 | 75 | 0.480000 | 1.056948 | 0.637787 |
| 11+ | 274 | 0.430657 | 1.093674 | 0.661451 |

序盤1～3試合のサンプルは少なく、11試合目以降も悪化しているため、単純な「序盤ほど悪い」とは断定しない。

## First-time vs returning: 2020-2024 OOF

| group | count | Accuracy | Log Loss | Brier |
|---|---:|---:|---:|---:|
| first-time promoted involved | 180 | 0.450000 | 1.066659 | 0.643071 |
| returning promoted involved | 200 | 0.420000 | 1.105718 | 0.669965 |
| no promoted club involved | 1298 | 0.476117 | 1.046946 | 0.629440 |

Returning club関与試合の方がfirst-timeより悪く、no promotedよりも明確に悪い。

## Rating age: returning clubs, 2020-2024

| rating age | count | Accuracy | Log Loss | Brier |
|---|---:|---:|---:|---:|
| < 1 year | 0 | - | - | - |
| 1-2 years | 138 | 0.449275 | 1.074147 | 0.648683 |
| 2+ years | 138 | 0.384058 | 1.131493 | 0.687858 |

2年以上J1を離れていたreturning clubは、1～2年群よりLog Lossが高い。ただし観測数は各138であり、これは診断上の関連であって因果確定ではない。

## Conclusion

1. first-time promoted clubは、J1-only replay上で全件1500から開始している。
2. returning clubは、lower division期間中にratingがfreezeし、前回J1 post-match ratingをそのまま復帰戦pre-match ratingへ持ち越している。
3. promotion season序盤は悪いが、11試合目以降も悪く、序盤だけが原因とは言えない。
4. first-timeよりreturningの方が悪い。
5. 特に2年以上のrating ageで悪化しており、現行J1-only Eloのpromotion handlingはpromoted-club errorの有力な構造要因の一つと評価できる。ただし、今回の結果だけでrating reset等の修正を実装・選択してはいない。

今回、promotion flag、rating reset、regression、J2 Elo、special K、manual adjustmentは実装していない。2025・2026および2014データ・J2/J3データは使用していない。
