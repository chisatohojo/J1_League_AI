# NN v2 Phase 2.3 学習・モデル封印

判定: **TRAINED_AND_SEALED_RESEARCH_ONLY**。性能優位性は未評価。2026-10-20 JST。

Study IDは `nn_v2_residual_20261020_01`。開始HEADは `6918724605275aaa142f210d20bbf45f8bbf3a34`、研究branchのみ使用した。学習前Manifest SHA `75d51da6e8c984666fe5630330a3b962e37ff32d0fb3d294aaf3989f0ebf44cb` は不変。Phase 2.1/2.2の固定数値コード・文書・入力を変更していない。

## Preflightと一度だけの学習

実入力12件、公式cache／metadata各3,588件、公式根拠3ページ、例外registry、全9特徴量と時刻、9年度のID集合、依存バージョンを再検証した。3,588／612／2,976件とID30700のイベント処理が固定記録に一致した。Python 3.12.14、NumPy 2.5.3、pandas 3.0.5、scikit-learn 1.9.1。

新しい薄いdriverは既存アルゴリズムを呼び、fit／Scaler／Adam回数、訓練IDと年、実統計、保存再現を計測する。数式やパラメータを変更しない。driver合成テスト8 PASS、warnings-as-errors。実入力preflightは実exit0、fit0回。115件・19件の旧合成証跡は固定実装SHAとともに保持した。

最初のfit前にexecution sealを保存・readbackした。SHAは `bc3f2e74cfcea598c5c16aa88d083e8d8ea16c52e17e901781cd9a74558fb353`。driver／依存実装SHA、Manifest SHA、実行コマンド、環境、予定回数、専用出力、停止条件を含む。seal自身のSHAは循環参照せず、作成後に外部環境変数 `J1AI_NN_EXECUTION_SEAL_SHA256` で固定してprocessへ渡した。

永続markerを `O_EXCL` 相当で作成し、出力をcreate-newしてから学習した。markerは成功後も保持し、同じStudy IDの再実行は禁止する。

| 実測対象 | 回数 |
|---|---:|
| 2017〜2025 cross-fit基準 | 9 |
| 全3,588件の最終基準 | 1 |
| 残差NN | 1 |
| Logistic.fit合計 | 10 |
| Scaler.fit合計 | 11 |
| Adam更新 | 200 |

cross-fitの訓練件数は612、918、1,224、1,530、1,836、2,216、2,522、2,828、3,208。各fitの実ID・年・label配列を固定集合に照合し、新しいScalerとLogisticを確認した。対象年はその基準fitに含まれない。2,976件のoffsetとFormが同じID順に一致。最終全期間基準のlogitを残差学習offsetへ使っていない。

NNはForm8→tanh8→tanh2、90パラメータ、±0.25補正、float64、PCG64 seed42、固定Adam／L2、full-batch200更新を維持した。早期停止・best epoch・再初期化なし。

学習入口は1回、実process exit0、timeoutなし、自動再試行0。実行は2026-10-20 06:56:59.496920〜06:57:10.566111 JSTで、朝7時の運用処理より前に完了した。Fit warningなし。既存fitコードの警告停止契約に加え、実行processは `-W error` とした。

## 技術的な検証

実offset 2,976×3の有限性・ID・class順 `[0,1,2]`、Scaler標本数／平均／分散、残差Scalerの2,976行限定、200損失、90要素、補正上限、softmaxと残差確率の数値整合を確認した。

モデルを別processで読み戻し、fit／fit_transform／partial_fitを禁止した状態で検証した。全9 cross-fitモデルからoffsetを再現し、CSV／NPZと一致。最終基準・Scalerと残差JSON・Scalerの状態が一致した。保存前後の合成5入力に対する確率は最大絶対差0。実試合の残差確率は技術検査で一時的に計算しただけで、予測batchとして保存していない。

全200更新後のtraining objective（平均CE＋L2）をCSVとPNGに保存した。update1は1.0933591278294177、update200は1.0677315769569444。これは学習目的関数であり、実データ性能評価や未知試合のLog Lossではない。Brier／Accuracyも未計算。結果による仕様変更・選択なし。

## 保存先とseal

- 学習成果物: `%LOCALAPPDATA%/J1AI/NNResearch-v2-study-20261020-01`
- 実行管理・preflight・execution seal・外側receipt: `%LOCALAPPDATA%/J1AI/NNResearch-phase2_3-20261020-065115`
- 永続attempt: `%LOCALAPPDATA%/J1AI/NNResearch-study-attempts/nn_v2_residual_20261020_01.json`

学習先には9基準モデル、最終EloモデルとScaler、残差モデルとScaler、offset CSV／NPZと監査、全ID／入力／時刻manifest、loss CSV／PNG、環境、技術検証、artifact manifest／sealを保存した。学習前Manifestはコピーして参照し、原本を書き換えていない。

最終artifact seal SHA: `d620f8a9cb44a3940996f89ded80c5396b0925e862501261870b6598458d392f`。

主要artifact SHAは [training-summary.json](training-summary.json)、全payloadはローカルの `artifact-seal.json` を参照する。モデル・実offset・行別特徴量・個人パス入りconfig／execution sealはGitHubへ追加しない。公開するのはdriver、テスト、文書、学習曲線、匿名化したreceiptとSHA情報のみ。

別ドライブの新規ZIPと独立展開先へ保存し、CRC・全ファイルSHA・展開先でのモデル読み戻しを検証した。[復元手順](RESTORE_GUIDE.md)に従い、復元検証でもfitしていない。

保存ZIPは `D:/J1AI-Backups/NNResearch-phase2_3-20261020-065115.zip`、1,177,411 bytes。119 payloadファイル、非圧縮4,810,003 bytesを保存した。CRC、ZIP内SHA、独立展開後SHA、展開コピーでの全9年度offset／モデル再現がすべてPASS、検証process実exit0、fit0回。ZIP SHAは `93185124ea29244ce8cf62934db99997fa87ddae7ec59da2ecaafdf32effd083`。詳細は [backup-verification.json](backup-verification.json)。

## 保護と次工程

学習・独立readback後の06:58 JSTに保護560ファイル、入力12件、タスク定義2件、保存14予測、再現98試合、Champion A、NN v1、運用config／runtime、運用worktree／mainの不変性を確認した。既存サーバー、表示ストア、ショートカットへの操作なし。運用タスクは無効化・変更していない。

その後、既存Morningタスクが07:00:02〜07:00:04 JSTに自律実行し、実終了コード0、ready／errorなしとなった。研究側から実行を要求していない。終了時点では保護560件中550件が同一SHAで、既知の運用投影8件と表示ストアのcurrent/status 2件が通常更新された。保存14予測・固定モデル・研究入力・タスク定義・外部configは不変。最新公式revisionは `f2a2fdeb171367d422b520cea7d492d99edb4a25c9b713ce0fb72a8f38f285c7`。変更前後SHAと実更新状態は [post-scheduled-update-protection.json](post-scheduled-update-protection.json) に区別して保存し、runtime全体が終了時まで同一だったとは扱わない。研究モデルは06:57に封印済みで、この新revisionを学習へ使用していない。

実データ性能評価0回、将来予測保存0件、実T0なし、実対象登録なし。性能優位性は**未評価**。Champion Aへ接続していない。

次は別承認で最新の公式日程、未開始20節200件、公式ID、kickoff、履歴／witness、研究専用保存経路を監査する。以前未確定だった公式ID190件・時刻100件を推測で埋めていない。実T0と対象集合はモデル封印後の実時点で決定する。2020〜2024は研究使用済み、2025は使用済みtest、既知2026はfresh holdoutではない。

Phase A: **BLOCKED** / Phase B: **NOT_AUTHORIZED**。
