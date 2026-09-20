# Model Freeze Before 2026

Freeze date: **2026-09-20**

この文書作成後、2026の結果を見てmodel、feature、parameter、Elo設定、欠損処理を変更しない。2026はfinal lockboxとして、次段階で固定仕様のModel A/Bを各1回だけ評価する。

## Frozen production candidates

### Model A — Champion / reference

- model: `StandardScaler` + `LogisticRegression`
- feature: `elo_diff`
- initial Elo: `1500`
- K: `30`
- home advantage: `175`
- `elo_diff = home_rating - away_rating`
- home advantageはElo expected-score計算内部だけに適用
- Logistic: `C=1`, `solver="lbfgs"`, `max_iter=1000`, `random_state=0`

2020–2024 pooled OOF（1,678試合）：

| Accuracy | Log Loss | Brier |
|---:|---:|---:|
| 0.466627 | 1.056065 | 0.635732 |

### Model B — Challenger

Model Aに次の4列を追加する。

- `home_domestic_days_since_last_competitive_match`
- `away_domestic_days_since_last_competitive_match`
- `home_domestic_has_previous_competitive_match`
- `away_domestic_has_previous_competitive_match`

Domestic competitive historyはJ1、J.League Cup、Emperor's Cupのみ。AFCは含めない。

| Model | Accuracy | Log Loss | Brier |
|---|---:|---:|---:|
| Elo + Domestic Rest | 0.464839 | 1.055538 | 0.635051 |
| B − A | -0.001788 | -0.000527 | -0.000681 |

Log Loss改善fold数は3/5。proper scoringでは小幅改善だが、effect sizeは非常に小さい。従ってAをChampion/reference、BをChallengerとして併存freezeする。

Primary metricはLog Loss、secondaryはBrier、Accuracyはdescriptive metricとする。

## Explored and closed experiments

以下はproduction candidateに含めない。数値は既存のexperiment document/moduleで得た結論を要約したもので、今回再評価は行っていない。

| experiment | conclusion |
|---|---|
| old 11-context feature model | 現行freeze候補には含めない |
| Shots extension | production candidateには含めない |
| CatBoost | Logistic baselineを置換しない |
| MLP | Logistic baselineを置換しない |
| Independent Poisson | Elo-onlyを置換しない |
| Dixon-Coles | production candidateには含めない |
| Poisson time decay | production candidateには含めない |
| Elo-assisted Poisson | production candidateには含めない |
| dynamic attack/defense Poisson | production candidateには含めない |
| Manager features | production candidateには含めない |
| Recent Form | production candidateには含めない |
| Elo Parity / `abs_elo_diff` | pooled改善なしのため含めない |
| Promotion Reset | robust replacementにならずclose |
| Equal J1+J2 Elo | pooledでCurrentより悪化 |
| J2 initial=1400 | Currentに届かずclose |
| Promotion-Calibrated J1+J2 | pooledでCurrentを上回らずclose |
| Returning-History Hybrid | pooledでCurrentを上回らずclose |
| Davidson | production candidateには含めない |
| Lineup Continuity | pooled Log Lossを改善せず含めない |

Promotion/J2 Elo handlingは **CLOSED FOR NOW** とする。追加のinitial値、offset multiplier、shrinkage、club別補正、promotion flag tuningは行わない。

## Deferred data, not rejected

次の項目は性能で不採用としたのではなく、data availability、identity、structured delivery、または安全な規定時間結果の不足によりdeferredとする。

- FootyStats xG
- SofaScore player ratings
- J.LEAGUE.jp detailed match stats
- Cup cross-division bridge with regulation-time score
- AFC integration

将来データが安全に整備された場合は、別のresearch cycleとして扱い、このfreezeを変更する根拠には自動的にならない。

## 2025 and 2026 discipline

2025は過去のexperimentで参照済みであり、fresh holdoutではない。今回のmodel selectionには使用せず、2025結果を根拠にA/Bの仕様を変更しない。

2026はfinal lockboxである。このfreeze完了前に2026 performanceを計算しない。次段階では、A/Bを同一の固定条件で一度だけ評価し、generalization確認として報告する。

2026結果を見て、feature追加・削除、parameter変更、K/HA変更、rest clipping変更、その他の後追い調整を行わない。

## Final freeze conclusion

- **Champion/reference:** Model A, Elo-only Logistic
- **Challenger:** Model B, Elo + Domestic Competitive Rest
- **Selection metric:** Log Loss（primary）、Brier（secondary）
- **2020–2024 exploration:** closed
- **2026 status:** unopened final lockbox
- **Post-freeze changes based on 2026:** prohibited

