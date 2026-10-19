# NN v2 学習実行契約（実行は別承認）

Phase 2.2は入力監査・学習前フリーズだけを行う。学習、実offset生成、Scaler統計生成、性能評価、実対象登録、将来予測保存は許可しない。`scripts.audit_nn_v2_pretraining` は監査専用であり、学習入口ではない。

監査の再現コマンドは次の形を取る。変数には実際にSHA照合した絶対パスを指定し、`$AuditOutput` と `$TrainingOutput` は未作成の専用パスにする。元の封印済み監査出力を上書きしない。

```powershell
& $Python -X utf8 -B -m scripts.audit_nn_v2_pretraining --source-root $SourceRoot --evidence-root $EvidenceRoot --publication $RevisionDir --publication-sha $RevisionManifestSha --output $AuditOutput --study-id $StudyId --training-output $TrainingOutput
```

これは入力監査の再実行だけであり、学習を開始しない。別studyへの再利用時には今回の固定仕様を勝手に変更せず、承認されたstudy IDと保存先を使う。

## 固定した研究

study IDは `nn_v2_residual_20261020_01`。正本は独立したローカル監査ディレクトリの `verified/study-manifest.json`。公開用の `study-manifest-index.json` に正本・入力・実装・分割集合のSHAを記録する。正本には全3,588 ID、seed 612 ID、残差2,976 ID、各foldの訓練／対象ID、絶対出力先を保存する。個人パス・原データ・行別特徴量はGitHubへ追加しない。

次の承認でも仕様・母集団・時刻ポリシー・seed・更新回数を変更しない。新しい学習driverが必要なら、既存の固定アルゴリズムを呼ぶ薄い入口として実装・確認し、そのSHAと実行コマンドを**最初のfit前**の別execution sealに保存する。現時点ではdriverとモデル等のSHAは未生成であり、仮値を記録しない。

## 実行前

1. 正本manifestのSHA、source台帳、入力12件、公式HTML／metadata各3,588件、研究用根拠3件、registry、依存バージョンを再照合する。監査時の9特徴量・ID順・9foldの集合と完全一致を要求する。
2. Champion A、v1、運用worktree／config／タスク／予測／publicationが保護されていることを確認する。07:00／22:00の更新を止めない。研究入力は2015〜2025 ordinary J1だけとする。
3. manifestに記載した研究出力先が不存在であることを確認する。入力や運用runtimeの内部、既存出力の再利用、symlink／reparseによる保護領域への転送は禁止する。
4. 学習前に別の永続attempt台帳へstudy IDを `O_CREAT|O_EXCL` 相当で排他的に予約し、flush／fsync／readbackする。続いて出力ディレクトリをcreate-newし、`STARTED` receiptへmanifest SHA、driver SHA、実時刻、予定fit数を記録する。並行起動・既存marker・既存出力はSTOP。markerは失敗時にも削除しない。

出力先は `%LOCALAPPDATA%/J1AI/NNResearch-v2-study-20261020-01` を予定し、Phase 2.2では作成していない。attempt台帳も今回は作成しない。出力作成前後の親・権限・reparse・identity検査を次工程で行う。

## 一度だけの学習

- 外側processに有限timeoutを設定し、再試行0回。成功・失敗・timeout・途中終了を区別して外側から保存する。実行試行は1回。同じstudy IDの再学習は禁止する。
- 9年度のcross-fit基準を、それぞれ対象年より前の行だけで学習する。9個のScalerと9個のLogisticは新規インスタンス。対象年のラベルをその基準fitへ渡さない。offsetは固定した2,976 IDへ一対一で結合する。
- 実offsetの行順、有限な3 logit、クラス順 `[0,1,2]`、学習／対象ID、Scalerの `n_samples_seen_` と訓練行限定の実統計を検証する。Phase 2.2ではこれらの値は作っていない。
- 将来推論専用の最終基準を3,588件で1回学習する。全期間fitのin-sample logitでcross-fit offsetを代替しない。
- 残差Scalerと90パラメータNNは固定した2,976行だけで1回学習する。8列の順序、PCG64 seed 42、Glorot、Adam、full-batch 200更新、更新後損失、最終状態保存を維持する。早期停止・best epoch選択・再初期化・seed変更は行わない。
- 予定fit数は基準9＋最終基準1＋残差NN1。実行回数をreceiptで数える。実offset、Scaler統計、モデルSHAは生成後の別artifact sealへ保存し、学習前manifestは書き換えない。
- 非有限値、未知の例外、警告、class／ID／SHA／時刻不一致で即時停止する。catchして成功へ変換しない。固定200更新のNNには別の収束条件を後付けしない。

## 封印・読み戻し

成功時は `SUCCEEDED`、失敗時は `FAILED`、外側timeout時は `TIMED_OUT` とする。完了receiptがないSTARTEDは未完了として扱い、成功と推測しない。失敗した部分成果物とattempt markerは保持する。再実行が必要なら別の承認と新しいstudy IDを必要とする。

モデル・Scaler・実offset・loss curve・fit manifest・環境・source／input pinsを新規成果物として保存し、全SHAとサイズを計算する。flush／fsync後に読み戻し、クラス順、8列順、90要素、200更新、標本集合、finite、確率範囲と合計、保存前後の推論一致を確認する。これは承認済み学習後の技術的readback検証であり、2025／2026性能による選び直しを行わない。信頼する自作成果物以外のpickle／joblibをロードしない。

最終artifact sealは学習前manifest SHAとexecution seal SHAを参照する。T0はモデル封印と独立収集の準備完了後の実時刻として別途記録する。学習を終えただけでT0や200対象を自動登録しない。

## 将来評価

実T0に最新の承認済み公式revisionと未開始条件を再確認し、最初の全試合未開始節から連続20節・200 fixtureを固定する。足りなければHOLD。日付だけで将来と分かる未公表kickoffは残り日程の容量確認にだけ使い、実予測では公式ID・開始日時・history／witnessの完全性を要求する。未登録IDを推測せず、延期試合を除外・置換しない。

基準と残差のpaired予測を、同じ入力・cutoff・全同日batch・キックオフ前flush/readbackで別系統へ保存する。既存Champion Aと保存予測を変更しない。最終200件の確定結果が揃うまで性能選択を行わない。2020〜2024は研究使用済み、2025は使用済みtest、既知2026結果はfresh holdoutではない。

Champion Aへの接続、運用config／タスク変更、main統合はこの契約に含まない。Phase A: **BLOCKED** / Phase B: **NOT_AUTHORIZED**。
