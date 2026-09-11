# J1 Match Predictor 開発手順・運用指示書

## 1. この文書の目的

この文書は、J1 Match Predictorの開発を継続的かつ安全に進めるための作業ルールを定める。

機能仕様については `README.md` を参照し、本書では主に以下を定義する。

- 開発の進め方
- Codexへの指示方法
- 作業開始時の確認事項
- 実装単位
- テスト方針
- 作業履歴の残し方
- README等の更新ルール
- Git運用
- データ変更時のルール
- AIモデル評価時のルール
- 次回作業へ引き継ぐ情報の残し方

最重要方針は以下。

> 一度に大量実装しない。  
> 小さい単位で実装、確認、テスト、記録を繰り返す。

---

# 2. 管理ファイル

プロジェクトでは以下のファイルを継続的に管理する。

```text
README.md
DEVELOPMENT_GUIDE.md
STATUS.md
CHANGELOG.md

docs/
├─ DECISIONS.md
├─ DATA_SOURCES.md
└─ MODEL_HISTORY.md
```

---

# 3. 各ファイルの役割

## README.md

プロジェクト全体の正式仕様。

主に以下を記載する。

- プロジェクト目的
- システム構成
- ディレクトリ構成
- 使用する特徴量
- AIモデル
- データ仕様
- 開発フェーズ
- 起動方法
- 使用方法

READMEは「現在の正しい仕様」を記載する。

古い仕様や作業メモを大量に残さない。

仕様変更が発生した場合はREADMEを更新する。

---

## DEVELOPMENT_GUIDE.md

本ファイル。

開発の進め方とCodexの作業ルールを記載する。

原則として頻繁には変更しない。

---

## STATUS.md

現在の開発状況を記載する。

次回開発開始時、最初に確認するファイル。

常に最新状態を維持する。

例：

```markdown
# Current Status

## 現在のフェーズ

Phase 2: Elo Rating実装

## 完了

- Python環境構築
- ディレクトリ作成
- matches.csv読み込み
- 基本データチェック

## 作業中

- Elo Rating実装

## 次にやること

1. Elo計算テスト
2. 各試合開始前Elo保存
3. training_data.csvへ追加

## 現在の問題

- 2015年昇格チームの初期Eloをどう扱うか未決定

## 最終確認日

2026-09-11
```

---

## CHANGELOG.md

変更履歴を記載する。

「何を変更したか」を残す。

例：

```markdown
# Changelog

## 2026-09-11

### Added

- プロジェクト初期構成を作成
- Elo Rating計算モジュールを追加
- Elo単体テストを追加

### Changed

- matches.csvのresult表現を文字列から0/1/2へ変更

### Fixed

- 引き分け時のElo更新処理を修正
```

細かすぎる変更は書かなくてよい。

機能追加、仕様変更、重要な修正を記録する。

---

# 4. DECISIONS.md

設計上の判断を記録する。

後から、

「なんでこうしたんだっけ？」

となることを防ぐ。

例：

```markdown
# Design Decisions

## Eloを基礎戦力として採用

Date:
2026-09-11

Decision:
チーム戦力の初期推定にはElo Ratingを使用する。

Reason:
- 少量データでも使用可能
- 時系列で戦力を更新できる
- 実装が単純
- AIへの入力特徴量として利用できる

Alternative:
- FIFA型Rating
- 独自Power Ranking
- Neural Networkによる戦力推定

Status:
採用
```

特に以下の変更時は記録する。

- AIモデル変更
- 特徴量追加・削除
- Elo計算方法変更
- データソース変更
- データ形式変更
- Train/Test分割変更
- 評価指標変更

---

# 5. DATA_SOURCES.md

使用するデータの取得元を記録する。

以下を必ず残す。

```text
データ名
取得元
URL
対象期間
取得方法
更新方法
利用する列
注意事項
```

例：

```markdown
## J1試合結果

Source:
XXXX

URL:
https://example.com/

Period:
2015-

Usage:
- match_date
- home_team
- away_team
- home_score
- away_score
- stadium

Update:
シーズン中は節終了後に更新
```

データ取得元を変更した場合は必ず更新する。

---

# 6. MODEL_HISTORY.md

AIモデルの実験結果を記録する。

モデルを変更するたびに結果を残す。

例：

```markdown
# Model History

## Model 001

Date:
2026-09-11

Model:
Logistic Regression

Features:
- Elo Difference
- Home/Away
- Last 5 Points

Training:
2015-2023

Validation:
2024

Test:
2025

Accuracy:
0.XX

Log Loss:
0.XX

Brier Score:
0.XX

Notes:
初期Baseline。
```

---

# 7. Codexが作業を開始するときのルール

毎回、作業開始前にGitの作業ツリー、現在のブランチ、リモートとの差分を確認する。

```powershell
git status
git branch --show-current
git remote -v
git rev-list --left-right --count HEAD...origin/main
git diff --stat HEAD origin/main
```

接続確認やリモート情報の更新が必要な場合は `git fetch origin` を行い、差分を再確認する。
`rev-list` の左はローカルだけ、右はリモートだけに存在するコミット数を示す。
未コミット変更も含めて状態を把握し、新しいリモート変更との同期は第23節に従う。

Codexはコード変更前に以下のファイルを確認する。

```text
README.md
DEVELOPMENT_GUIDE.md
STATUS.md
```

必要に応じて以下も確認する。

```text
CHANGELOG.md
docs/DECISIONS.md
docs/DATA_SOURCES.md
docs/MODEL_HISTORY.md
```

---

# 8. Codexへの基本指示

Codexへ作業を依頼するときは以下を基本形とする。

```text
README.md
DEVELOPMENT_GUIDE.md
STATUS.md

を最初に読んでください。

現在の仕様と実装状況を確認してから作業してください。

今回の作業：

○○を実装してください。

条件：

・既存仕様を壊さない
・未来情報を使用しない
・変更範囲を必要最小限にする
・必要なテストを追加する
・既存テストを実行する
・作業完了後にSTATUS.mdを更新する
・重要な変更ならCHANGELOG.mdも更新する
・設計判断を変更した場合はdocs/DECISIONS.mdを更新する

実装前に既存コードを確認し、重複機能を作らないでください。
```

---

# 9. 1回の作業範囲

1回のCodexへの依頼は原則1機能とする。

良い例：

```text
Elo Ratingを実装する
```

```text
直近5試合の勝点を計算する
```

```text
LightGBMの学習処理を追加する
```

悪い例：

```text
J1予測AIを全部作って
```

```text
データ取得からUIまで完成させて
```

巨大な変更を一度に行うと、不具合発生時に原因追跡が困難になるため禁止する。

---

# 10. 基本開発サイクル

すべての機能開発は以下の順で行う。

```text
1. STATUS確認

↓

2. README確認

↓

3. 対象コード確認

↓

4. 実装方針決定

↓

5. 小規模実装

↓

6. 単体テスト

↓

7. 全体テスト

↓

8. 実行結果確認

↓

9. ドキュメント・STATUS更新、git diff / git statusで変更内容確認

↓

10. Git Commit（コミットする場合。今回のユーザー指示を優先）

↓

11. STATUSとGit状態の最終確認・報告
```

---

# 11. 実装前確認

コード変更前に確認する。

## 対象機能

今回何を作るのか。

## 入力

何を受け取るのか。

## 出力

何を返すのか。

## 使用データ

どの列を使用するのか。

## 時系列

対象試合より未来のデータが入らないか。

## 既存機能

似た処理が既に存在しないか。

---

# 12. データリーク確認

J1 Match Predictorではデータリーク防止を最優先とする。

特徴量作成時、必ず以下を確認する。

```text
この情報は試合開始前に知ることができたか？
```

Noの場合、その情報を使用してはいけない。

特に注意する。

```text
対象試合自身の結果
対象試合後のElo
シーズン最終順位
シーズン最終勝点
未来試合
未来の負傷情報
未来のスタメン情報
```

---

# 13. 特徴量追加ルール

新しい特徴量はいきなり本番モデルへ追加しない。

以下の順で検証する。

```text
Baselineモデル

↓

特徴量A追加

↓

同条件で再学習

↓

評価比較

↓

改善した場合
採用候補

↓

改善しない場合
削除または保留
```

MODEL_HISTORY.mdへ結果を記録する。

---

# 14. 評価条件固定

特徴量の性能比較時には以下を固定する。

```text
Training期間
Validation期間
Test期間
モデル
ハイパーパラメータ
乱数Seed
評価指標
```

複数条件を同時に変更しない。

悪い例：

```text
特徴量追加
+
LightGBMパラメータ変更
+
Train期間変更
```

これでは改善理由が判断できない。

---

# 15. Baselineを残す

Baselineモデルは削除しない。

最低でも以下を比較可能にする。

```text
Baseline 0
ホームチーム常時予測等の単純予測

Baseline 1
Eloのみ

Baseline 2
Elo + 直近成績

Main Model
LightGBM
```

新モデルがBaselineを本当に上回っていることを確認する。

---

# 16. テスト方針

重要処理にはpytestテストを作成する。

特に必須。

```text
Elo更新
引き分け処理
直近5試合集計
ホーム/アウェイ集計
対戦相性集計
休養日数
特徴量生成
データリーク防止
```

---

# 17. Eloテスト例

以下を確認する。

```text
勝者Eloが上昇する
敗者Eloが低下する
引き分け時に正しく更新される
格下勝利時の変動が大きい
対象試合前Eloが保存される
対象試合結果が事前Eloへ混入しない
```

---

# 18. データ確認

新しいCSVを追加した場合は最低限以下を確認する。

```text
行数
列数
欠損
重複
日付範囲
チーム名
異常値
```

例：

```python
df.shape
df.isna().sum()
df.duplicated().sum()
df["match_date"].min()
df["match_date"].max()
df["home_team"].unique()
```

---

# 19. チーム名の統一

チーム名称は必ず統一する。

例：

```text
FC東京
ＦＣ東京
FC Tokyo
Tokyo
```

が混在しないようにする。

正式名称を管理するマスターを作成する。

```text
data/master/teams.csv
```

可能であれば内部処理には `team_id` を使用する。

例：

```text
team_id
team_name
```

---

# 20. 生データを変更しない

`data/raw/` に保存した取得データは原則編集しない。

加工データは、

```text
data/processed/
```

へ出力する。

構造：

```text
raw data

↓

cleaning

↓

processed data

↓

feature engineering

↓

training data
```

生データを残すことで処理を再現可能にする。

---

# 21. スクリプトによる再現

可能な限り手作業でCSVを書き換えない。

以下をコード化する。

```text
データクリーニング
チーム名変換
Elo生成
特徴量生成
Trainデータ生成
モデル学習
評価
```

最終的に、

```powershell
python -m src.main
```

などで主要処理を再現できる状態を目指す。

---

# 22. Notebookの扱い

Notebookは以下に使用する。

```text
データ確認
グラフ
特徴量分析
モデル実験
```

正式な処理はNotebookだけに置かない。

有用な処理が確定した場合、

```text
notebook
↓
src/
```

へ移植する。

---

# 23. Git運用

正式な共有・バックアップ先は `https://github.com/chisatohojo/J1_League_AI.git` とする。
ローカルの `origin` はこのURL、基準ブランチは `main` とし、リモート設定は明示的な指示なく変更しない。

作業中は依頼範囲に限定し、関係のないファイル変更、大規模な自動整形、不要なリファクタリングを行わない。
既存のGit履歴を理由なく書き換えず、ローカル実装・文書・STATUS・Git履歴の整合性を維持する。

リモートに新しい変更がある場合は、既存の変更を壊さずに同期できることを確認する。
`main` で作業ツリーがクリーン、かつfast-forward可能であることを確認できた場合は
`git merge --ff-only origin/main` で同期できる。未コミット変更や履歴の分岐がある場合は、
差分と影響を調べ、既存変更を保持する方法で進める。

作業完了時は以下を実施する。

1. 対象のテストと全体テストを実行し、結果を確認する。
2. `git diff`（ステージ済みの変更があれば `git diff --cached` も）で変更内容を確認する。
3. `git status` で最終的な変更とブランチ状態を確認する。
4. STATUS.mdを更新し、必要に応じてCHANGELOG.md等も更新する。
5. 変更内容・テスト結果・Git状態を報告する。文書更新後も差分と状態を最終確認する。

コミットする場合は機能単位で分かりやすいメッセージを使用し、ユーザーが指定した停止条件を優先する。

良い例：

```text
feat: add Elo rating calculation

feat: add rolling five-match form features

test: add Elo rating tests

fix: prevent future match leakage

docs: update feature specification
```

巨大なCommitは避ける。

以下は明示的な指示なしに実行しない。

- `git push --force`
- `git reset --hard`
- 公開済みコミットのrebase
- ブランチ削除
- Git履歴の大規模な書き換え
- リモートリポジトリの変更
- GitHub上の既存データ削除

通常の `git fetch`、`git status`、`git diff` 等の確認操作は実施してよい。

---

# 24. Commit前チェック

Commit前に確認する。

```text
コードが動く
テスト成功
不要なdebugコードがない
一時ファイルがない
データリークがない
STATUS更新済み
必要ならREADME更新済み
必要ならCHANGELOG更新済み
```

---

# 25. STATUS.md更新タイミング

以下のタイミングで必ず更新する。

```text
機能完成時
作業中断時
重大な問題発生時
次にやることが変わった時
```

作業途中で終了するときは特に重要。

---

# 26. 作業中断時

途中で開発を終了する場合、STATUS.mdへ以下を書く。

```text
どこまで完成したか

何が未完成か

現在発生しているエラー

次に確認するファイル

次に実行するコマンド

次の作業
```

例：

```markdown
## 作業中断地点

elo.pyの実装完了。

pytest実行時に
test_draw_case
のみ失敗。

原因候補：
引き分け時Actual Scoreの扱い。

次回：
src/features/elo.py
tests/test_elo.py
を確認する。
```

---

# 27. Codexによる作業完了報告

Codexは作業後、以下をまとめる。

```text
変更したファイル
実装内容
テスト内容
テスト結果
残っている問題
次に推奨する作業
```

例：

```text
変更ファイル

src/features/elo.py
tests/test_elo.py
STATUS.md
CHANGELOG.md

実装

Elo Rating計算を追加。

テスト

8件実行
8件成功

残課題

昇格クラブ初期Ratingは暫定1500。

次の作業

Elo値をtraining_dataへ追加。
```

---

# 28. README更新ルール

以下の場合READMEを更新する。

```text
仕様変更
ディレクトリ変更
特徴量追加
AIモデル変更
データ形式変更
実行方法変更
UI変更
```

単なるバグ修正ではREADME更新不要。

---

# 29. CHANGELOG更新ルール

以下を記載する。

```text
Added
Changed
Fixed
Removed
```

例：

```markdown
## 2026-09-11

### Added

- Elo Rating機能

### Fixed

- 引き分け時のRating更新処理
```

---

# 30. DECISIONS更新ルール

仕様上の判断を行った場合更新する。

特に、

```text
なぜこの方式を採用したか
```

を書く。

結果だけを書かない。

---

# 31. MODEL_HISTORY更新ルール

モデル学習を実施し、比較可能な結果が出た場合に更新する。

必ず以下を残す。

```text
日時
モデル
特徴量
Train期間
Validation期間
Test期間
Accuracy
Log Loss
Brier Score
主要パラメータ
所感
```

---

# 32. データソース変更時

取得元変更時は、

```text
docs/DATA_SOURCES.md
```

を更新する。

また、同じ項目でも取得元によって定義が違う可能性があるため確認する。

例：

```text
試合開催日
延期試合
スタジアム名称
クラブ名称
中立地扱い
```

---

# 33. バックアップ

大量データ変更前はGit Commitを行う。

モデルや生成可能な大容量ファイルはGitへ保存しない場合がある。

`.gitignore`へ適切に追加する。

例：

```text
.venv/
__pycache__/
.ipynb_checkpoints/
*.pyc
```

学習モデルや取得データについてはサイズを確認して判断する。

---

# 34. AIモデル開発順

基本順序は以下。

```text
Step 1
データ取得

↓

Step 2
データクリーニング

↓

Step 3
Elo

↓

Step 4
直近成績

↓

Step 5
Baseline Logistic Regression

↓

Step 6
時系列評価

↓

Step 7
LightGBM

↓

Step 8
特徴量追加

↓

Step 9
Calibration

↓

Step 10
SHAP

↓

Step 11
UI
```

順番を飛ばして複雑化しない。

---

# 35. 現在地を常に確認する

作業開始時に、

```text
STATUS.md
```

を読み、

```text
今どこまで完成しているか
今回何を作るか
次は何か
```

を確認する。

Codexも同様。

---

# 36. TODOの扱い

細かい作業はSTATUS.mdのTODO欄へ記載する。

例：

```markdown
## TODO

- [x] ディレクトリ構成作成
- [x] matches.csv読込
- [ ] Elo実装
- [ ] Eloテスト
- [ ] Last5 Features
- [ ] Baseline学習
```

完了した項目も一定期間残してよい。

大量になった場合は完了済みをCHANGELOGへ移し整理する。

---

# 37. 不具合発生時

まず原因を特定する。

いきなり大規模リファクタリングしない。

手順：

```text
エラー再現

↓

対象テスト作成

↓

原因箇所特定

↓

最小修正

↓

テスト

↓

全体テスト

↓

CHANGELOG
```

---

# 38. リファクタリング

機能追加と大規模リファクタリングを同時に行わない。

```text
機能追加Commit

↓

動作確認

↓

別CommitでRefactor
```

とする。

---

# 39. Codex禁止事項

Codexは明示的な理由なく以下を行わない。

```text
大量ファイル削除
ディレクトリ構成全面変更
既存API変更
CSV列名変更
特徴量定義変更
モデル変更
Train/Test期間変更
依存ライブラリ大量追加
```

必要な場合は、

```text
docs/DECISIONS.md
README.md
```

へ理由を記録する。

---

# 40. 新ライブラリ追加

依存パッケージを追加した場合、

```text
requirements.txt
```

を更新する。

使用目的が分かりにくいライブラリの場合はREADMEにも記載する。

---

# 41. 再現性

AI実験では可能な限り乱数Seedを固定する。

例：

```python
RANDOM_STATE = 42
```

同じ入力から同じ評価結果を再現できる状態を目指す。

---

# 42. モデルファイル

モデル保存時にはモデルだけでなく必要情報も残す。

例：

```text
model.pkl
model_metadata.json
```

metadata例：

```json
{
  "model": "LightGBM",
  "training_end": "2025-12-31",
  "features": [
    "elo_diff",
    "home_last5_points",
    "away_last5_points"
  ]
}
```

---

# 43. 開発初期に作成するファイル

プロジェクト作成直後に以下を用意する。

```text
README.md
DEVELOPMENT_GUIDE.md
STATUS.md
CHANGELOG.md
requirements.txt
.gitignore

docs/
├─ DECISIONS.md
├─ DATA_SOURCES.md
└─ MODEL_HISTORY.md
```

空でもよいので最初に作成する。

---

# 44. 最初のSTATUS.md

初期状態は以下とする。

```markdown
# J1 Match Predictor Status

## Current Phase

Phase 0: 開発環境構築

## 完了

- プロジェクト仕様書作成
- 開発手順書作成

## 作業中

- Python / VS Code環境構築

## Next

1. Git Repository作成
2. Python venv作成
3. requirements.txt作成
4. ディレクトリ作成
5. 過去J1試合データ取得方法の決定

## Issues

なし
```

---

# 45. Codex最初の指示

リポジトリ作成後、最初に以下を依頼する。

```text
README.mdとDEVELOPMENT_GUIDE.mdを読んでください。

J1 Match Predictorの初期開発環境を作成してください。

今回はAIモデルを実装しないでください。

実施内容：

1. README記載のディレクトリ構成を作成
2. Pythonプロジェクト初期化
3. requirements.txt作成
4. .gitignore作成
5. testsディレクトリ作成
6. docsディレクトリ作成
7. STATUS.md作成
8. CHANGELOG.md作成
9. docs/DECISIONS.md作成
10. docs/DATA_SOURCES.md作成
11. docs/MODEL_HISTORY.md作成

既存ファイルの内容は勝手に変更しないでください。

作業後、

・作成ファイル
・変更内容
・次に行うべき作業

を報告してください。
```

---

# 46. 2回目のCodex指示

環境構築後。

```text
README.md
DEVELOPMENT_GUIDE.md
STATUS.md

を確認してください。

今回はJ1試合データの入力仕様と読み込み機能のみ実装してください。

AIモデルやEloはまだ実装しないでください。

実装内容：

・matches.csvの読み込み
・必須列チェック
・日付型変換
・重複チェック
・基本的なValidation
・pytestテスト

実装完了後、

STATUS.md
CHANGELOG.md

を更新してください。
```

---

# 47. 3回目のCodex指示

試合データ読込完成後。

```text
README.md
DEVELOPMENT_GUIDE.md
STATUS.md

を確認してください。

今回はElo Ratingのみ実装してください。

条件：

・試合を時系列順に処理
・全チーム初期値1500
・K=20
・対象試合開始前のEloを保存
・対象試合終了後にRating更新
・未来データ使用禁止
・引き分け対応
・pytest追加

実装後、

STATUS.md
CHANGELOG.md

を更新してください。
```

---

# 48. 毎回の作業終了条件

作業完了とは、

```text
コードを書いた
```

だけではない。

以下すべてを満たした状態を完成とする。

```text
実装完了

+

テスト成功

+

結果確認

+

ドキュメント更新

+

STATUS更新
```

この状態になって初めて次の機能へ進む。

---

# 49. 開発方針まとめ

J1 Match Predictorでは、

```text
小さく作る
↓
動かす
↓
測る
↓
記録する
↓
次へ進む
```

を繰り返す。

特にAI開発では、

```text
何を変更したか

なぜ変更したか

精度がどう変わったか
```

を常に追跡可能にする。

最終的に数か月後に開発を再開しても、

```text
README.md
STATUS.md
CHANGELOG.md
docs/DECISIONS.md
docs/MODEL_HISTORY.md
```

を読めば、現在の状態と過去の判断を把握できるプロジェクトを維持する。
