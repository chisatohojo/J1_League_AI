# Elo promotion reset evaluation

確認日: 2026-09-20

## Fold metrics

| season | Current Accuracy | Current Log Loss | Current Brier | Reset Accuracy | Reset Log Loss | Reset Brier |
|---:|---:|---:|---:|---:|---:|---:|
| 2020 | 0.506536 | 1.023120 | 0.611757 | 0.513072 | 1.022935 | 0.611414 |
| 2021 | 0.507895 | 1.025344 | 0.614983 | 0.510526 | 1.018910 | 0.610628 |
| 2022 | 0.401961 | 1.094019 | 0.661022 | 0.405229 | 1.095257 | 0.661917 |
| 2023 | 0.460784 | 1.060429 | 0.638531 | 0.457516 | 1.061484 | 0.639179 |
| 2024 | 0.450000 | 1.079241 | 0.653170 | 0.444737 | 1.082235 | 0.655470 |

## Pooled OOF

| model | Accuracy | Log Loss | Brier |
|---|---:|---:|---:|
| Current Elo | 0.466627 | 1.056065 | 0.635732 |
| Promotion Reset Elo | 0.467223 | 1.055671 | 0.635486 |

Reset - Current：Accuracy **+0.000596**、Log Loss **-0.000394**、Brier **-0.000247**。Log Loss改善fold数は2/5（2020、2021）。

## Promoted-club diagnostics

2020～2024 OOFのみ。promotion flagはmodel featureには渡していない。

| group | count | Current Log Loss | Reset Log Loss | Current Brier | Reset Brier |
|---|---:|---:|---:|---:|---:|
| first-time promoted involved | 170 | 1.065951 | 1.067735 | 0.642272 | 0.643467 |
| returning promoted involved | 210 | 1.104431 | 1.100179 | 0.669331 | 0.667024 |
| no promoted club involved | 1298 | 1.046946 | 1.046890 | 0.629440 | 0.629338 |

Returning群ではResetがLog Loss/Brierとも改善した。一方、first-time群は既存仕様でも1500開始のため、Resetで改善せず僅かに悪化した。

## Early-season diagnostics

| promotion-season appearance | count | Current Log Loss | Reset Log Loss | Current Brier | Reset Brier |
|---|---:|---:|---:|---:|---:|
| 1-3 | 31 | 1.103367 | 1.118940 | 0.666911 | 0.677277 |
| 4-10 | 75 | 1.056948 | 1.055476 | 0.637787 | 0.636408 |
| 11+ | 274 | 1.093674 | 1.090163 | 0.661451 | 0.659628 |

1～3試合目はResetで悪化し、4～10および11+では改善した。従って、単純に「昇格直後だけを改善する」結果ではない。

## Reset sanity

2016～2024のpromotion eventは22件（first-time 12、returning 10）。first-timeは全件pre-match Elo=1500。returningの代表例は以下の通りで、Currentのold frozen ratingをResetでは1500へ置換した。

| season | team_id | old frozen Elo | reset Elo | first match |
|---:|---|---:|---:|---:|
| 2020 | team_0009 | 1506.481 | 1500.000 | 22785 |
| 2021 | team_0004 | 1322.275 | 1500.000 | 24983 |
| 2022 | team_0007 | 1444.336 | 1500.000 | 27336 |
| 2023 | team_0019 | 1401.641 | 1500.000 | 28167 |
| 2023 | team_0032 | 1378.558 | 1500.000 | 28165 |
| 2024 | team_0007 | 1426.312 | 1500.000 | 30432 |

Continuous J1 clubsはresetしていない。2015は前年membershipがないためreset判定をしていない。判定はprevious-season membershipと過去J1 appearanceだけで行い、future membershipは使用していない。

## Conclusion

1500 resetはpooledで小幅改善したが、5fold中2foldのみ改善し、1～3試合目では悪化した。Returning群、特にfreezeしたratingを持つ群では改善方向だったため、promotion handlingは誤差の一因である可能性がある。ただし、今回の結果だけでreset ruleを採用・固定する判断は行わない。

実験module以外のElo coreは変更していない。2025・2026、J2/J3データ、追加initial rating、reset duration別条件、feature追加は使用していない。
