# NN v1 凍結記録

判定: **CLOSE_NN_V1_RETAIN_ARTIFACTS**。2026-10-19 JST。

完了commitは `2af07472900b23936a7cfbad1431f2dbd354170d`。v1の実装・仕様・母集団・パラメータ・モデル・Scaler・OOF・グラフ・既存SHA台帳・既存ZIPを保持し、再学習・パラメータ変更・評価の選び直しを禁止する。Champion Aへの昇格・運用接続は行わない。

## 確定した結果

| モデル | Pooled Log Loss | Brier | Accuracy |
|---|---:|---:|---:|
| Elo-only Logistic | 1.056063737594059 | 0.635731117789051 | 0.466626936829559 |
| 9特徴量 Logistic | 1.059921362633946 | 0.638142043841970 | 0.461859356376639 |
| 9特徴量 MLP | 1.189486276207542 | 0.701244412625614 | 0.411203814064362 |

これはPhase 1.2の保存済み結果の転記であり、新たな性能評価ではない。各モデル1,678試合の研究使用済みOOF。MLPの有意な優位性は未実証で、点推定も両Logisticより悪い。2020〜2023 foldと最終fitの収束警告を削除しない。詳細は [Phase 1.2レポート](phase1_2/RESULTS.md)。

## 保存と今回の読み取り専用照合

- 原本: `%LOCALAPPDATA%/J1AI/NNResearch-phase1_2-20261019-142912/run`。
- 研究ZIP: `D:/J1AI-Backups/NNResearch-phase1_2-20261019-142912.zip`、1,599,048 bytes。
- モデルSHA: `30b159ed8cb6da84f210def283ab2c242073463c4895ac8d279adc5c03e8f55a`。
- Scaler SHA: `dada7aab10cb8cf706bd96fed311edd262a2ee167162464137bac563c4985c0b`。
- Run台帳SHA: `f2438b10c7f630bbc71e4a8150bb4a992b06cd88a9a92d327240c23cdf6b37ea`。
- ZIP SHA: `b29104508988a4fa2237f81e6a1da63b4afdf6edde45464a26aa167cdfb15b27`。
- Runの26 payloadファイル＋台帳の集合・サイズ・SHAを全件確認。ZIPの89 payloadファイル＋バックアップ台帳を読み出し、CRC・SHA・原本runとのバイト一致を確認した。
- 原本の再シリアライズ、日時・属性・アクセス権の変更、ZIPの作り直しは行っていない。今回のfit・性能評価はともに0回。
- 完了commit配下の既存研究ファイル、固定実装・文書18件、保護対象560ファイル、自動更新タスク2件も照合した。機械可読の確認結果は [closure-verification.json](closure-verification.json)。

ここでの凍結は、Git commitとSHAで特定した原本を保持して改変を検出する研究運用規約である。通常ディスクのファイルをWORM媒体へ変換した、または物理的に変更不能にしたという主張ではない。保存媒体の故障対策には既存ZIPとそのSHAを別媒体にもコピーして照合する。ZIPに公式キャッシュ3,588ページ本体は含まれない。

## 記録の優先関係

`STATUS.md`、Phase 1.1の仕様・SHA台帳・監査は各工程の原記録として書き換えない。そこにあるfit 0回は当時の状態であり、Phase 1.2の実行済み結果を取り消さない。本記録がv1の終了判断である。今後の調査は [v2設計](../nn_v2/DESIGN.md) に分離し、v1を再開する手順は設けない。

運用Champion A、14件の保存予測、公式履歴、後日再現98件、Windowsタスク、外部config、運用worktree、mainには変更しない。

Phase A: **BLOCKED** / Phase B: **NOT_AUTHORIZED**。
