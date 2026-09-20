# Elo Promotion / J2 Experiment Summary

確認日: 2026-09-20

## Scope

2015〜2024のJ1/J2 historyを使ったpromotion / re-promotion時のElo state調査を整理する。対象は2020〜2024 expanding-window rolling OOF（1,678 J1 matches）。2025、2026、Cup性能評価、J3、AFCは使用していない。

全variantの共通条件は、initial Elo 1500、`K=30`、home advantage 175、`elo_diff = home_elo - away_elo`、J1 rowsのみをLogistic Regressionの学習・validation targetとする構成である。

## 1. Promotion Transition Audit

確認した構造は以下のとおり。

- first-time J1 entryはinitial Elo=1500
- returning clubはJ1-only EloではJ1離脱中にratingがfreeze
- returning promoted matchesは誤差が大きい
- 2年以上離脱したgroupでさらに悪化

したがって、returning clubのstale J1-only Eloは構造的な原因候補として実在する。ただしこれは原因候補の確認であり、別divisionの実力を直接観測した証明ではない。

## 2. Promotion Reset

returning entryをJ1復帰時に1500へresetした固定variant。

| Model | Accuracy | Log Loss | Brier |
|---|---:|---:|---:|
| Current | 0.466627 | 1.056065 | 0.635732 |
| Reset | 0.467223 | 1.055671 | 0.635486 |

Current比では小幅改善し、Log Loss改善foldは2/5だった。returning subgroupでは改善したが、昇格後1〜3試合では悪化した。robustなbaseline replacementとするには弱い結果だった。

## 3. Equal J1+J2 Elo

J1/J2 league matchを同一streamでreplayし、全clubをinitial=1500から開始した。

| Model | Accuracy | Log Loss | Brier |
|---|---:|---:|---:|
| Current J1-only | 0.466627 | 1.056065 | 0.635732 |
| Equal J1+J2 | 0.460072 | 1.057002 | 0.636552 |

pooledではCurrentより悪化した。一方でreturning promoted subgroupには改善があり、J2 rating history自体には情報があることを示唆した。同時に、J1/J2 absolute rating scale mismatchの可能性も確認した。

## 4. J2 initial=1400

J2初回league appearanceのclubを1400から開始するvariantを、事前固定値として1回だけ評価した。

| Model | Accuracy | Log Loss | Brier |
|---|---:|---:|---:|
| J2 initial=1400 | 0.463647 | 1.056353 | 0.636014 |

Equal J1+J2より改善したが、Currentには届かなかった。Log Loss改善foldは1/5だった。1400以外のinitial値探索は行っておらず、fixed initial offset tuningはcloseとする。

## 5. Cross-Division Cup Bridge

国内CupのJ1-vs-J2 bridge candidateは145件だった。

- J.League Cup: 68
- Emperor's Cup: 77
- identity-safe candidate: 145
- safe 90-minute score/resultを利用できた件数: 0
- used bridge: 0

したがって性能結果はEqual J1+J2と同一になった。Cup bridge仮説そのものをrejectしたのではなく、現在のprocessed dataでは90分score/resultが不足しており未評価である。将来、公式90-minute dataを安全に整備できた場合のみ再検討可能である。

## 6. Promotion-Calibrated J1+J2

season boundaryごとに、以下のsetを使用した。

```text
promoted = previous J2 ∩ current J1
relegated = previous J1 ∩ current J2
offset = mean(relegated Elo) - mean(promoted Elo)
```

offsetはpromoted ratingだけに一度適用したparameter-free calibrationである。

| Model | Accuracy | Log Loss | Brier |
|---|---:|---:|---:|
| Promotion-Calibrated | 0.464243 | 1.056243 | 0.636050 |

Currentとの差はLog Loss `+0.000178`。Log Loss改善foldは3/5だが、pooledではわずかに悪化した。

| Group | Current Log Loss | Calibrated Log Loss |
|---|---:|---:|
| Returning | 1.104431 | 1.095960 |
| First-time | 1.065951 | 1.083227 |
| Early 1〜3 | 1.103367 | 1.147594 |

returningには有効だったが、first-timeおよび昇格直後1〜3試合を悪化させた。

## 7. Returning-History Hybrid

- returning: J2 Eloをcarry-over
- first-time: J1初参入時に1500へreset

| Model | Accuracy | Log Loss | Brier |
|---|---:|---:|---:|
| Returning-History Hybrid | 0.463051 | 1.056399 | 0.636058 |

Currentとの差はLog Loss `+0.000333`。Log Loss改善foldは2/5だった。

| Group | Current Log Loss | Hybrid Log Loss |
|---|---:|---:|
| Returning | 1.104431 | 1.103611 |
| First-time | 1.065951 | 1.070096 |
| Early 1〜3 | 1.103367 | 1.137503 |

returningは小幅改善したが、first-timeとearly-seasonは悪化した。

## Overall decision

以下を総合判断とする。

- returning clubのstale J1-only Eloは実在する構造問題である
- J2 historyを利用するとreturning subgroupが改善するcaseはある
- しかしJ1 prediction全体では一貫した改善にならない
- first-time promotedおよび昇格直後1〜3試合が特に不安定
- J1/J2 scaleを固定値、mean calibration、hybrid policyで扱ってもCurrent J1-onlyをrobustに上回らなかった
- parameter追加探索はresearcher overfitting riskが高いため終了する
- 1450/1350等のinitial探索は禁止する
- offset multiplier、shrinkage、club別補正は禁止する
- promotion-specific flag tuningもこのbranchでは行わない
- J2 dataset / TeamMaster拡張は将来別用途に再利用可能
- Cup bridgeは90-minute dataを将来整備した場合のみ再検討可能

## Final status

**Promotion/J2 Elo handling: CLOSED FOR NOW**

Current J1-only Eloをreferenceとして維持する。
