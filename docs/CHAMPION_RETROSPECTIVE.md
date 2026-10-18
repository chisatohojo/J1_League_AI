# Champion A 後日再現バックテスト

`scripts/reconstruct_champion_season.py` は、選択した2026/27通常J1の公式revisionで
completedが確定した試合だけを、固定Champion Aで時系列再現します。保存済みの
試合前予測とは別の `prediction_type: retrospective_reconstruction` です。
ネットワーク取得・学習・live predictor・運用更新・タスク登録は呼び出しません。

## 時間と入力の境界

- 既存 `load_champion()` が固定artifact一式と2015〜2025年の入力SHAを検証してから
  scaler/modelを読み込みます。百年構想リーグの固定SHAも検証します。
- 既存 `replay_ratings()` と `probability_rows()` を再利用します。K=30、home advantage=175、
  特徴量は `elo_diff` だけです。fitやST2の封印済みデータは使用しません。
- 日付ごとに固定履歴からEloを再構築します。ongoing履歴は**対象日より前**の確定結果に
  限定してからreplayへ渡します。モデルの対象入力から得点・勝敗を除外します。
- 同日全試合を一括計算し、その日の予測ファイルをflush/readbackして確定します。
  試走／全件の予測sealが保存された後、別段階で正式結果と照合します。
- 対象日より前のcandidate／scheduledが残る場合、欠けた履歴を補完せず停止します。

これは当時の厳密なas-of予測ではありません。固定artifact自体や選択した公式publicationは
試合日より後に作成された可能性があります。後日の結果訂正や過去掲載時刻の未立証も
残ります。`calculated_at_utc` は実際の計算日時で、過去の生成日時へ偽装しません。

## 実行

入力は既存sourceと**明示した不変revisionディレクトリ**です。latestを追いかけません。
出力はRepository、運用runtime、公式入力と重ならない別ディレクトリにします。

```powershell
& $python -B -u -m scripts.reconstruct_champion_season --source-root $source --official-directory $revisionDirectory --manifest-sha $manifestSHA --output $output --stage trial
```

最初の3試合日を試走します。その結果を確認してから、同じ出力と固定revisionで続行します。

```powershell
& $python -B -u -m scripts.reconstruct_champion_season --source-root $source --official-directory $revisionDirectory --manifest-sha $manifestSHA --output $output --stage complete --resume --saved-runtime $runtime
```

`--saved-runtime` は任意で、native Champion予測batchを読み取り専用にして10月9日の
保存済み予測との独立した差分レポートを作ります。予測を一致するよう修正しません。
差がある場合は、保存時source revisionの過去履歴でも再計算し、履歴差と残る不一致を区別します。

## 保存・再開

- `run.json`: revision、artifact・入力・実装SHA、対象fixture集合、試走日、型、限界の固定契約。
- `inputs/<revision>/`: 公式manifestとその全対象ファイルのSHA検証済みコピー。
- `days/<date>/`: 結果なしの予測、履歴cutoff証跡、SHA manifest。
- `prediction-seals/`: 集計前に固定した日別manifestのSHA。
- `trial/`, `complete/`: 試合別CSV／JSON、日付・節・結果クラス・予測クラス別の集計とレポート。
- `live-comparison/`: 実際の保存済み予測と再現値の差分。成績は合算しません。

日別ディレクトリはcreate-new／原子的renameで公開します。途中停止後の `--resume` は
同じ入力・実装契約とSHAが一致する日だけを再利用し、確定済み予測や計算時刻を変えません。
全件完了後の再実行は検証して既存成果物を返し、予測・集計を重複生成しません。
異なるrevisionや実装で続ける場合は、新しい出力を使います。改変・欠損・別ownerのlockは
自動修復しません。hard crashで `.run.lock` が残った場合は所有と状態を確認してから対処します。

## 成績の定義

CSVの確率は0〜1で、丸めず保存します。予測クラスは固定モデルのAWAY=0／DRAW=1／HOME=2の
最大確率です。同率はこの順で最初のクラスを選び、同率フラグも保存します。
Log Lossは自然対数の `mean(-ln(max(p_actual, 1e-15)))`、Brierは3クラスの二乗誤差の和の平均
（3で割らない）です。空グループの成績はnullです。対象カバレッジと未処理件数も明記します。

現行v2画面・保存済み予測・bindings・公式latest・運用JSON・enabled設定・タスクは変更しません。
出力はGitへ追加せず、実装・合成テスト・本書だけを保存します。

```powershell
& $python -B -m pytest tests/test_champion_retrospective.py tests/test_champion_dashboard_update.py -q -p no:cacheprovider
```
