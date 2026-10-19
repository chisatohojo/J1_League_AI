# NN v2 アーキテクチャ比較・推奨仕様案

状態: **DESIGN_ONLY_NOT_FROZEN_FOR_TRAINING**。2026-10-19 JST。

今回は設計調査のみ。モデルの実装・fit・性能評価・新規予測・依存ライブラリ導入・運用接続は行わない。v1は [CLOSE_NN_V1_RETAIN_ARTIFACTS](../nn_v1/CLOSURE.md) とし、再学習しない。以下の数値パラメータはv2の審議用の一案であり、実行の承認ではない。

## 事実と設計判断

v1のMLPは9特徴量・899学習パラメータで、pooled Log Loss 1.189486276。新時系列のElo-only Logisticは1.056063738、9特徴量Logisticは1.059921363だった。これは既存結果の参照で、新たな評価ではない。

過去のMLP実装にはElo＋開催側別Form＋休養/履歴フラグの11列入力・隠れ層(16)の直接分類もある。入力列はその実装が参照する [FEATURE_COLUMNS](../../src/modeling/logistic_elo_home_advantage_tuning.py) で確認した。正式アーキテクチャ比較のLightGBM Gはv1と同じ9特徴量を直接分類し、旧時系列でLog Loss 1.065176823、Aは1.056065401でGはclose済み。旧Gとv1はID30700の時刻処理が異なり、数値の小差を同一条件の優劣とは解釈しない。これらの正式判定を変更・再評価しない。

根拠: [v1結果](../nn_v1/phase1_2/RESULTS.md)、[旧MLP実装](../../src/modeling/mlp_baseline_rolling_validation.py)、[正式比較結果](../../docs/MODEL_ARCHITECTURE_BENCHMARK_RESULT.md)、[正式比較仕様](../../docs/MODEL_ARCHITECTURE_BENCHMARK_SPEC.md)。

表形式NNの比較論文でも万能な優位モデルは示されていないため、NNであること自体を性能改善の根拠にしない。[Gorishniy et al., 2021](https://arxiv.org/abs/2106.11959)。次の推奨は、この小規模データと既存結果に対する設計上の判断である。

## 学習可能な件数

入力SHA照合済みのordinary J1は2015〜2024が3,208試合、2015〜2025が3,588試合。9特徴量は全件で有限。これは時系列計算可能性の確認であり、当時の公式公開状態の完全なPIT証明ではない。

今回、既存時刻ポリシーで特徴量だけを読み取り専用に再構築して件数を監査した。モデルや確率は計算していない。

| 母集団 | 試合単位の上限 | 両クラブとも過去5試合あり | 片方以上が5試合未満 |
|---|---:|---:|---:|
| 2015〜2024 | 3,208 | 3,106 | 102 |
| 2015〜2025 | 3,588 | 3,481 | 107 |

home/awayの2系列を作っても独立した試合数は倍にならない。直近履歴の共有により、隣接する試合も独立ではない。追加情報のcomplete-case件数はPIT監査前なので未確定。

## 3候補の比較

| 項目 | A: Elo＋小型残差NN | B: 履歴特徴量の増強 | C: 小型時系列NN |
|---|---|---|---|
| 入力 | 固定Elo基準logit＋既存Form 8列 | 既存9列＋監査後の休養・過去stats等 | home/away各過去5試合の順序付きtoken＋mask＋Elo差 |
| 構成例 | Form 8→tanh 8→2残差logit。Draw基準、補正に上限 | p列→小型MLP(8)→3。線形対照も別計画で必要 | 重み共有GRU(hidden 8)×2系列→結合→3。チームID埋込みなし |
| 出力 | Away/Draw/Homeの3確率。基準確率も別保存 | 3確率 | 3確率 |
| 使える試合数 | 原資料3,588。時系列offset生成の初期2年をseedにすると残差fitは2017〜2025の**2,976** | 最大3,588。追加情報により縮小し得る。採用可件数は未確認 | padding＋maskなら最大3,588、全5試合を必須にすると3,481。token拡張後の件数は要監査 |
| 試合前利用 | 既存のElo/Form計算を再利用しやすい。将来は取得時刻witness必須 | 休養日・prior結果は再構築可能。shots/xG等は先行公開の証明が別途必要 | 結果・得失点・開催側は履歴から構成可能。順序・mask・結果反映時刻の追加実装が必要 |
| 過学習 | 残差90パラメータと補正上限で容量を制限できるが、改善保証なし | 次元増加・欠損処理・多数の特徴量選択で研究過適合しやすい | 系列の重複と少数クラブへの過適合。数千tokenを数千独立試合と誤認しない |
| リーク | offsetを同じ対象ラベルで学習した基準から作らない。Scalerもfold内に限定 | 現在試合stats、season-final集計、訂正後データ、source公開遅延が主リスク | target行の混入、結果での並べ替え、同日・中断試合・padding後処理が主リスク |
| CPUコスト | 小行列・full-batch。基準offset生成に9回＋最終1回の小型Logistic fitが必要 | 小型MLP自体よりsource整備・監査のコストが大きい | 短系列でも逐次計算が必要。CPUで実装可能だがAより実装・検証負担が大きい |
| 過去研究との差 | 直接softmax分類をやめ、Elo基準を固定した限定補正だけを学ぶ | モデル変更より情報追加の仮説。旧closed特徴量研究を自動再開しない | 集計Formにない順序を扱う。行を増やしたMLPやLightGBMの再試行ではない |
| 将来独立評価 | 補正なしの同一v2 Elo基準とのpaired比較を主とする | Aと同時投入せず、新情報のPIT・仕様を別途固定してから同じ将来登録方式 | 別研究登録と将来期間が必要。Aの将来結果を見てCを同じholdoutへ追加しない |

CPU時間のv2実測はない。v1の秒数をv2の所要時間として転記しない。Bは入力列pが未確定、CのGRUはbias定義にも依存するため、今回そのパラメータ数を確定値として扱わない。

GRUの構成参考は [Cho et al., 2014](https://aclanthology.org/D14-1179/)。原論文は言語処理であり、J1での有効性を立証しない。

## 推奨: Aを1候補だけ次段階へ

既存情報を増やさず、Eloの判断を小さく補正する仮説に限定できるため、Aを推奨する。BはPIT立証とsource整備を先に進める候補、Cは順序情報の安全な構築後に別サイクルで検討する候補とする。Aの成績を見て同じ将来評価にB/Cや別seedを追加しない。

残差という着想の参考は [He et al., 2015](https://arxiv.org/abs/1512.03385) だが、下の固定logit補正は本研究の設計案であり、画像用ResNetや同論文の実験結果をそのまま移植したものではない。

### 入出力と90パラメータの案

基準モデルは**v2研究専用Elo-only Logistic**。C=1、lbfgs、max_iter=1000、seed=0、Elo=1500/K30/HA175、Scaler付き、クラス順序[0 Away,1 Draw,2 Home]を提案する。運用Champion Aのartifactを再学習・置換せず、v2名義の別artifactにする。

残差入力uは、既存9特徴量からelo_diffを除いた8列を既存の順序で使う。availability列を残し、cold startを架空の5試合に補完しない。StandardScalerは残差学習用行だけでfitする。

```text
h = tanh(W1 u + b1)                          # 8 -> 8
delta = 0.25 * tanh(W2 h + b2)               # 8 -> 2
eta_away = log(p_base_away) - log(p_base_draw)
eta_home = log(p_base_home) - log(p_base_draw)
p_v2 = softmax([eta_away + delta[0], 0, eta_home + delta[1]])
```

学習パラメータ数は8×8＋8＋8×2＋2＝90。固定基準はこの数に含めない。ゼロ残差なら基準確率と一致する。0.25は各対Draw log-odds補正の上限案であり、Away対Home差の上限は0.5。上限があっても損失悪化は防げない。

実装時のetaは基準Logisticの有限なdecision_function値からDrawとの差として求め、確率のlogを経由するunderflowを避ける案とする。softmaxとcross-entropyも安定なlog-sum-expで計算する。非有限値や誤ったクラス並びをclip等で成功に変換しない。

目的関数案は平均3クラスcross-entropy＋`0.01/2 * (||W1||² + ||W2||²)`、biasへの罰則なし。Adam lr=0.001、beta=(0.9,0.999)、epsilon=1e-8、seed=42、float64、CPU 1 thread、full-batch 200 epochs、early stoppingなし、warm startなし、最後のepochを保存する。W1はseed固定のGlorot uniform、b1=0、W2=b2=0から始める。epoch・seed・上限・正則化値を過去評価や将来の途中結果で選び直さない。非有限値、クラス・SHA・勾配検査の不整合は停止条件。

### 学習用offsetと最終基準を分離

2015〜2025全件でfitした基準のin-sample確率を、全年度の「試合前基準予測」と称して残差の訓練入力に流用しない。

提案は2015〜2016の612件をseedとし、各年y=2017〜2025について、2015〜y−1だけでScaler＋Elo Logisticをfitし、その年の試合前Eloからoffsetを作る。前処理・基準係数に対象年ラベルを入れない。残差学習行は3,588−612＝2,976。これらは**訓練補助の時系列cross-fit**で、未使用testや新規性能評価ではない。2025もその訓練行としてだけ使い、モデル選択・性能報告の対象にしない。

将来推論用には、同じ新時刻ポリシーの2015〜2025でv2基準を1回fitして凍結する案。残差は上記2,976行で1回fitする案。v2基準9 cross-fit＋最終1 fit、残差1 fitは**将来の別承認後**に限る。v1の再学習ではない。cross-fitと最終基準の学習量差による分布ずれは残るため、監査に記録して将来paired比較で検証する。

### 実装上の制約

既存 [MLPClassifierの公開API](https://scikit-learn.org/stable/modules/generated/sklearn.neural_network.MLPClassifier.html) には、上の固定外部logitを損失へ加えるoffset引数はない。単なる確率平均やMLPRegressorへの置換を同一仕様とみなさない。実装段階では、既存NumPyによる小型専用推定器と合成データでの有限差分勾配検査を提案する。新ライブラリの無断導入やsklearn内部関数の書き換えはしない。今回は推定器もテストも未実装。

## 次工程で固定するもの

[PIT監査計画](PIT_AUDIT_PLAN.md) と [独立した将来評価計画](FUTURE_EVALUATION_PLAN.md) を満たした後、仕様、入力・source・実装・artifact SHA、依存版、例外registry、学習回数、将来対象の登録規則を機械可読manifestに固定する。未確定のsource時刻・ID・実装仕様をダミーSHAや推測値で埋めない。承認前は実装・学習・予測を開始しない。

資料は2026-10-19に公式API・原論文を参照した。文献の性能を本データの実測として扱わない。Phase A: **BLOCKED** / Phase B: **NOT_AUTHORIZED**。
