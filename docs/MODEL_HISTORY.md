# Model History

モデル学習・性能比較は未実施。Phase 0ではモデルを作成していない。

Baseline導入以降、比較可能な実験ごとに以下を記録する。

- 日時・モデル名・使用特徴量
- Training / Validation / Test期間（時系列で分割する）
- Accuracy・Log Loss・Brier Score・Confusion Matrix
- 主要パラメータ・乱数Seed・データバージョン
- Baselineとの比較・所感・採否

単純予測、Eloのみ、Eloと直近成績、LightGBMを比較できるように残す。
評価指標の定義や分割条件を確定・変更する場合は `DECISIONS.md` に理由を記録する。
