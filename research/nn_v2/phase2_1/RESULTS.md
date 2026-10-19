# NN Phase 2.1 実装・合成検証結果

判定: **SYNTHETIC_IMPLEMENTATION_READY**。実データ学習の実行判定は **HOLD / NOT_AUTHORIZED**。2026-10-19 JST。

実データfit 0回、実データ性能評価0回、将来予測保存0回、実対象登録0回。v1はCLOSE_NN_V1_RETAIN_ARTIFACTSを維持する。新規ライブラリ導入なし。

## 実装

- [残差NN](../../../src/modeling/nn_residual_v2.py): Form8→tanh8→tanh2、90パラメータ、固定基準logitへの±0.25補正。安定なsoftmax/CE、重みだけのL2、PCG64/seed42、Adam200更新、更新後損失を保存。訓練列・推論列の順序を厳密に要求する。
- [時系列offset](../../../src/modeling/nn_v2_offsets.py): 2015〜2016をseedとし2017〜2025を対象とする9 cross-fit。対象年ラベルは基準fitへ渡さず、毎回新しいScaler/Logisticを生成。最終全期間基準は別型/role。入力はrecorded match_date/match_idの安定順に正規化する。
- [研究契約](../../../src/modeling/nn_v2_contracts.py): artifact/監査manifest、T0、20節200対象、独立した全380試合との対象選択照合、paired予測の締切・完全batch検証。登録・予測保存・ネットワークの実行入口なし。
- [数値仕様の確定](NUMERICS.md)、[保存スキーマ](SCHEMAS.md)。既存DESIGN.md等のSHA付き設計原本は変更していない。

全コード・テスト・文書のSHAは [implementation-sha256.json](implementation-sha256.json)、数値仕様と環境は [implementation-spec.json](implementation-spec.json)。

## 合成検証

最終テストは **115 PASS、FAIL/ERROR/SKIP 0、実process exit 0**。警告をエラー扱いにして3.41秒で完了した。

```powershell
python -X utf8 -B -m pytest tests/test_nn_residual_v2.py tests/test_nn_v2_offsets_contracts.py -q -W error -p no:cacheprovider
```

テスト入力は固定乱数から作ったForm/logit/ラベル、架空クラブ・架空fixtureだけ。テスト中のread_csv、network connect、subprocess起動を拒否している。実データを読み込む訓練入口や運用moduleは呼んでいない。

| 確認 | 結果 |
|---|---|
| パラメータ数・ゼロ残差 | 90個、初期出力は基準softmaxと一致 |
| 補正上限 | 対Draw ±0.25、Away対Home差最大0.5 |
| softmax / CE | ±1000のlogitでも有限。確率clipで損失を変えない |
| 勾配照合 | 全90成分、2つの合成seed、中心差分epsilon=1e-6 |
| 勾配最大絶対誤差 | **3.2360407171e-10**（閾値5e-8） |
| 勾配最大relative L2誤差 | **4.2309485325e-9**（閾値1e-7） |
| 正則化・Adam | bias無罰則、母集団でL2を割らない。手計算2step、epsilon位置を確認 |
| 200更新・再現性 | 損失200点、最終状態を保存。固定seedでtheta/曲線のbit一致 |
| 入力拒否 | NaN/Inf、不正class、列順/shape不一致、無効Form、overflow、warm startを拒否 |
| artifact | 外部期待SHA・sidecar・schema・版・Scaler整合・読戻し一致。上書き・改変を拒否 |
| offset | 合成66試合→seed12＋対象54、9fold。実データ2,976件を実行した値ではない |
| リーク防止 | 各fold訓練年/ID・Scaler平均/分散/件数を確認。対象年の最後のラベル変更で当該年以前のoffsetが不変。後年が過去年の終了結果を使うこととは区別 |
| 不明時刻 | 未知中断注記・例外field、改変effective timestamp/policy、年の偽装をfit前に拒否 |
| 将来計画 | 架空20節200件と独立380日程、最初の適格節、重複・欠損・ID衝突・pending IDを確認 |
| 締切 | 7桁目の100nsを保持。生成/readback順、同日完全集合、最早kickoffを確認 |

結果の機械可読版は [synthetic-results.json](synthetic-results.json)。初回の数値テストは42 PASSで、テスト側のDataFrame/Scaler呼出しに警告1件があった。これを修正し、artifact外部SHA等を追加した最終115件を警告なしで確認した。仕様やパラメータを性能に合わせて変更していない。

## 保護対象と22時の定期更新

開始時はHEAD 10ec3bd679cb4fb66cf4d59c3b26001667c28e16、clean。v1 payload26件・既存ZIPのCRC/SHA・保護560ファイル・タスク2定義を照合した。

作業中に既存Eveningタスクが22:00に実行された。終了コード0、runtime ready、公式観測22:00:05 JST、completed100/candidate0/scheduled280。公式run記録は前revision f7f9ab1e...を参照し、新revisionは67031cfbfa99dd78e889d606225840ca7a74211dae105233327d3beed9d3bdba。表示JSON等の可変10ファイルが更新され、残りの保護550ファイルはSHA一致した。

研究作業からこれらを巻き戻したり、タスク・config・運用worktreeへ書き込んだりしていない。「全560ファイルが不変」とは報告しない。v1、Championモデル、14保存予測、既存の過去publication・後日再現98件、タスク定義、mainの保持は別に照合した。詳細は [protection-verification.json](protection-verification.json)。

## 残条件と実データ学習への判定

ユーザー確認済みの数値細部はすべて実装した。数値仕様の未確定項目や、今回の合成検証での未解決FAILはない。

**合成実装はREADYだが、実データ学習はまだ開始しない。** 次工程では別途承認を受け、実入力SHA/公式cache/metadata/時刻registryの再照合、実特徴量・2,976対象IDとoffsetのjoin、研究専用基準/NNのstudy manifest・artifact保存・外側実行receiptの固定が必要。今回は実公式parser・実時計・実登録/予測writerを接続していない。歴史的な公式掲載時刻が未立証である点も解消したとは主張しない。

2020〜2024を新しいholdoutとしてモデル選択しない。2025は将来承認された訓練だけ、既知2026結果もfresh holdoutとは呼ばない。将来評価登録や実データ学習の許可は、この合成PASSから自動的には発生しない。

ローカル検証証跡: `%LOCALAPPDATA%/J1AI/NNResearch-phase2_1-20261019-215910`。JUnitと合成モデルはここに保存し、個人パスを含む完全な証跡・合成モデルそのものはGitへ追加しない。

Phase A: **BLOCKED** / Phase B: **NOT_AUTHORIZED**。
