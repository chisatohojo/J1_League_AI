# Phase 2.1 数値仕様の確定

2026-10-19、実装前の質問に対してユーザーが「この数値仕様で確定する」と回答した。既存DESIGN.mdは原記録として変更しない。

- float64、NumPy default_rng(42) / PCG64。W1は独立なuniform[-sqrt(6/16), sqrt(6/16)]、形状(8,8)。b1(8)、W2(8,2)、b2(2)は0。順序W1 row-major、b1、W2 row-major、b2の90要素。
- h=tanh(u W1+b1)、delta=0.25 tanh(h W2+b2)。Draw基準の2logitを補正し、順序Away/Draw/Homeでsoftmaxする。
- 損失はmean cross-entropy + 0.01/2*(sum(W1²)+sum(W2²))。biasは正則化しない。logitを最大値でshiftしたlog-sum-expを用い、確率clipで損失を変えない。
- Adam: m0=v0=0、t=1から。m=.9m+.1g、v=.999v+.001g²、mhat=m/(1-.9^t)、vhat=v/(1-.999^t)、theta -= .001*mhat/(sqrt(vhat)+1e-8)。epsilonは平方根の外。全パラメータに同じ更新則、decoupled weight decayなし。
- full-batchで正確に200更新。各更新後の正則化込み損失を200点記録。最終状態を保存し、early stopping、最良epoch選択、warm start、再試行をしない。
- FormのStandardScalerは残差fitに渡した訓練行だけにfitする。既存sklearnのwith_mean=True / with_std=True（母分散、定数列scale=1）を使用する。
- 基準LogisticはC=1 / lbfgs / max_iter=1000 / random_state=0 / tol=1e-4。各cross-fitで新規Scalerと新規モデル。基準fitの警告・クラス不整合・非有限値は停止する。
- 入力順序、時刻イベント、クラス順序を検証する。数値overflowや未知の時刻例外をclip・fallbackで成功に変えない。
- 生Formは非負整数の集計値、availabilityは0〜5、pointsは3×availability以下、availability=0の各集計は0を要求する。これは既存特徴量の意味の検証であり、値をclipする処理ではない。標準化後の内部行列にはこの生値の制約を適用しない。
- artifactはJSON＋SHAでcreate-new保存し、読み戻しには外部で固定した期待SHAを必須にする。ローカルsidecarだけの置換を信頼しない。NumPy・pandas・sklearn・Pythonの版も保存し、異なる版の読込は停止する。

この文書の実装承認は合成検証まで。実データfit・評価・将来予測保存は0回を維持する。
