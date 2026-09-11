# J1 Match Predictor

J1リーグ戦のホーム勝利・引き分け・アウェイ勝利の確率を予測するPythonプロジェクトです。

## 現在の実装範囲

現在は **Phase 1: 試合データ読み込み・入力検証まで実装済み** です。
Elo、特徴量生成、モデル学習、予測、UIは未実装です。
このREADMEを現在の正式仕様として管理し、以下にv0.1の目標仕様を掲載します。
開発時は `DEVELOPMENT_GUIDE.md` と `STATUS.md` も確認してください。
元の日本語仕様書・手順書は変更せず保存しています。

## 正式リモートリポジトリ

共有・バックアップ先は [chisatohojo/J1_League_AI](https://github.com/chisatohojo/J1_League_AI) です。
`origin` は `https://github.com/chisatohojo/J1_League_AI.git`、基準ブランチは `main` とします。
作業開始時のGit状態・リモート差分確認、同期、完了時の確認手順は `DEVELOPMENT_GUIDE.md` の第7・23節に従います。

## 開発環境のセットアップ（Windows / PowerShell）

Python 3.12とGitを使用します。この作業フォルダではPython 3.12.14の `.venv` を作成済みです。
起動と検証はプロジェクトルートで以下を実行します。

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt -c requirements-lock.txt
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m src.main
.\.venv\Scripts\python.exe -m pytest
```

仮想環境の有効化は必須ではありません。現在の `src.main` はプロジェクト名と開発段階を表示する起動確認用です。
`requirements.txt` は直接依存、`requirements-lock.txt` は検証済みの推移的依存を含む固定バージョンです。
ロックファイルはWindows / Python 3.12環境用です。依存更新時は再検証して両ファイルを更新します。

新規環境では、使用可能なPython 3.12があれば、最初に仮想環境を作成します。

```powershell
py -3.12 -m venv .venv
```

今回の端末はPython 3.12のランチャー登録だけが残り、実行ファイルがなかったため、
既存Python 3.10から導入用の環境を作り、uvでプロジェクト内にPythonを配置しました。
同じ環境を再構築する場合は、上の仮想環境作成コマンドの代わりに以下を実行します。
`.tools/` は `.venv` が参照するPython本体を含むため、使用中は保持してください。

```powershell
python -m venv .tools/bootstrap
.\.tools\bootstrap\Scripts\python.exe -m pip install uv==0.12.13
.\.tools\bootstrap\Scripts\uv.exe python install 3.12.14 --install-dir .tools/python --no-bin --no-registry --cache-dir .tools/cache
.\.tools\python\cpython-3.12.14-windows-x86_64-none\python.exe -m venv .venv
```

uvは環境構築用で、アプリケーションの依存には含めません。
`--no-bin` と `--no-registry` によってコマンド配置とWindowsへの登録を行わずに導入します。
導入方法は [uvのPython管理ドキュメント](https://docs.astral.sh/uv/guides/install-python/) と
[CLIオプション](https://docs.astral.sh/uv/reference/cli/#uv-python-install) を参照してください。

実装済みの構成:

```text
data/{raw,processed,master}/   # 生データ、加工データ、チーム名称マスター用
src/collect/matches.py        # CSV読み込み・入力検証
src/{features,model}/         # 後続フェーズの実装先（現在はパッケージのみ）
src/main.py                   # 起動確認用エントリーポイント
tests/                        # pytest
docs/{DECISIONS,DATA_SOURCES,MODEL_HISTORY}.md
models/                       # 将来の学習済みモデル用
notebooks/                    # 将来の探索分析用
```

データ・学習済みモデルはまだありません。生成物、仮想環境、取得データはGit管理から除外します。
`data/raw/` の取得データは編集せず、加工結果は `data/processed/` へ出力します。
名称統一用マスターは `data/master/teams.csv` に追加します（未作成）。

## 実装順序

Phase 1まで完了しています。次はPhase 2のElo、直近成績、Baselineの順に進み、
時系列評価を用意してからLightGBMを導入します。実データの取得元は未決定です。
以下のフェーズ番号は元の仕様書を維持しますが、評価処理（Phase 6）は手順書に従ってBaseline段階から整備します。

---

# J1 Match Predictor 開発仕様書

## 1. プロジェクト概要

### 1.1 プロジェクト名

J1 Match Predictor

### 1.2 目的

J1リーグの過去の試合データから各クラブの現在戦力を推定し、対戦相性、ホーム・アウェイ、直近成績などの試合コンディションを加味して、今後のJ1リーグ戦について以下の3結果の発生確率を予測する。

- ホームチーム勝利
- 引き分け
- アウェイチーム勝利

最終的には単純な勝敗予測だけではなく、「なぜその確率になったか」を確認できる説明可能な予測システムを目指す。

---

# 2. 基本コンセプト

予測を大きく以下の2要素に分けて考える。

## 2.1 チーム基礎戦力

各クラブが現在どの程度の強さを持っているかを数値化する。

初期バージョンではElo Ratingを使用する。

例：

```text
G大阪      1638
FC東京     1579
町田       1662
鹿島       1651
```

Eloは試合結果が発生するたびに更新し、その試合時点におけるチーム戦力として使用する。

重要事項として、学習対象試合より未来の結果をElo算出に使用してはならない。

---

## 2.2 試合コンディション

基礎戦力だけでは表現できない、その試合固有の要素を特徴量としてAIへ入力する。

主な対象は以下。

- ホーム / アウェイ
- 開催スタジアム
- 対戦相性
- 直近成績
- 直近の対戦相手の強さ
- 得点力
- 失点傾向
- 休養日数
- 負傷者
- 出場停止
- 将来的にはスタメン

概念的には以下のような構造とする。

```text
試合予測
=
チーム基礎戦力差
+
ホーム / アウェイ補正
+
直近コンディション
+
対戦相性
+
選手離脱影響
+
その他試合条件
```

---

# 3. 開発環境

## 3.1 使用環境

- Windows
- Visual Studio Code
- Codex
- Python 3.12系推奨
- Git

## 3.2 Python仮想環境

通常は、使用可能なPython 3.12がある環境のプロジェクトルートで以下を実行する。
今回の端末向けの代替手順と作成済み環境の起動方法は、README冒頭のセットアップを参照する。

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

## 3.3 初期ライブラリ

```text
pandas
numpy
scikit-learn
lightgbm
matplotlib
joblib
jupyter
pytest
```

将来的に追加予定。

```text
shap
requests
beautifulsoup4
streamlit
```

---

# 4. ディレクトリ構成

```text
j1-predictor/
│
├─ data/
│   ├─ raw/
│   │   ├─ matches.csv
│   │   ├─ injuries.csv
│   │   ├─ stadiums.csv
│   │   └─ teams.csv
│   │
│   └─ processed/
│       └─ training_data.csv
│
├─ src/
│   ├─ collect/
│   │   ├─ matches.py
│   │   ├─ injuries.py
│   │   └─ stadiums.py
│   │
│   ├─ features/
│   │   ├─ elo.py
│   │   ├─ form.py
│   │   ├─ matchup.py
│   │   ├─ availability.py
│   │   └─ build_features.py
│   │
│   ├─ model/
│   │   ├─ train.py
│   │   ├─ evaluate.py
│   │   └─ predict.py
│   │
│   └─ main.py
│
├─ models/
│   └─ model.pkl
│
├─ notebooks/
│   └─ analysis.ipynb
│
├─ tests/
│
├─ .gitignore
├─ requirements.txt
└─ README.md
```

---

# 5. 試合データ仕様

基本単位は「1試合1行」とする。

`matches.csv`

## 5.1 基本情報

```text
match_id
season
round
match_date
home_team
away_team
stadium
```

## 5.2 試合結果

```text
home_score
away_score
result
```

`result`は以下の3値。

```text
0 = Away Win
1 = Draw
2 = Home Win
```

例：

```text
2026_001,2026,1,2026-02-14,FC東京,鹿島,味の素スタジアム,2,1,2
```

## 5.3 読み込みAPIと入力検証（Phase 1）

```python
from src.collect.matches import load_matches, validate_matches

matches = load_matches()  # プロジェクト内の data/raw/matches.csv
# matches = load_matches("path/to/matches.csv")  # 取得元に合わせた別のファイル
# matches = validate_matches(existing_dataframe)  # CSV以外から取得したデータ
```

`load_matches(path, *, encoding="utf-8-sig")` はローカルCSVを読み込んで検証し、
型を統一したDataFrameを返します。既定パスは実行ディレクトリに依存しません。
UTF-8はBOMあり・なしの両方に対応し、別の文字コードは `encoding` で明示します。
`validate_matches(dataframe)` は同じ検証と型変換を行い、新しいDataFrameを返します。
どちらも入力CSV・DataFrameを書き換えません。

| 列 | 読み込み後の型・条件 |
| --- | --- |
| `match_id`, `home_team`, `away_team`, `stadium` | pandas `string`。前後の空白を除去し、空文字を拒否 |
| `season`, `round` | `int64`。正の整数 |
| `home_score`, `away_score` | `int64`。0以上の整数 |
| `result` | `int64`。0=アウェイ勝利、1=引分、2=ホーム勝利。得点と一致すること |
| `match_date` | `datetime64[ns]`。日付をタイムゾーンなしの午前0時として保持 |

- 必須10列の欠落、必須値の欠損（空文字・空白のみを含む）、空データを拒否します。
- 数値文字列や `2.0` など整数値は変換します。小数値、真偽値、非数、無限大、int64範囲外は拒否します。
  CSVの `match_id` は先頭ゼロを保持します。`NA` などの文字列を自動的に欠損へ置換しません。
- CSVの日付は `YYYY-MM-DD` とします。DataFrameでは `date` とタイムゾーンなし・午前0時の
  `datetime` / `Timestamp` も許容します。不正日付、曖昧な月日順、時刻・タイムゾーン付きの値、
  `datetime64[ns]` の範囲外は拒否します。
- 空白除去後のID重複と同一ホーム・アウェイチームを拒否します。
  IDが異なっても `(season, match_date, home_team, away_team)` が同一なら重複試合として拒否します。
- 重複列名、CSVパーサーが検出した引用符の不整合、ヘッダーと列数が一致しないCSV行（空行を含む）を拒否します。
- 追加列、行列の順序、DataFrameのindexは保持します。日付順への並べ替え、欠損補完、
  resultの修正、チーム名称マスターによる変換は行いません。seasonと日付年の一致は要求しません。

入力不正は `MatchValidationError`（`ValueError` の派生）で通知します。
最初に検出した問題と、値に関するエラーでは対象列・1始まりのデータ行位置を示します。
ファイル未存在・権限・文字コードのエラーはPython標準の例外を返します。
試合結果が必要な入力仕様のため、未開催試合は今回の読み込み対象外です。

---

# 6. 特徴量

学習時に使用する主な特徴量を以下とする。

## 6.1 Elo関連

```text
home_elo
away_elo
elo_diff
```

```text
elo_diff = home_elo - away_elo
```

各値は必ず試合開始前時点のものを使用する。

---

# 7. Elo Rating

## 7.1 初期値

全チームの初期Eloを仮に1500とする。

将来的には前年順位、J2昇格チーム補正などを検討する。

## 7.2 基本式

期待勝率：

```text
Expected_A =
1 / (1 + 10 ** ((Rating_B - Rating_A) / 400))
```

更新：

```text
New_Rating =
Old_Rating
+
K * (Actual - Expected)
```

## 7.3 Result

```text
勝利 = 1.0
引き分け = 0.5
敗北 = 0.0
```

## 7.4 K値

初期実装では、

```text
K = 20
```

とする。

後ほどバックテストによって最適化する。

## 7.5 ホーム補正

Elo計算時にホームアドバンテージを追加する方法も検討する。

ただし初期実装では、AI側にもホーム情報を特徴量として入力するため、二重に補正しないよう注意する。

---

# 8. 直近成績

試合開始前の直近5試合を使用する。

```text
home_last5_points
away_last5_points
```

勝点：

```text
勝利 = 3
引分 = 1
敗北 = 0
```

最大値：

```text
15
```

さらに以下を算出する。

```text
home_last5_goals
away_last5_goals

home_last5_conceded
away_last5_conceded

home_last5_goal_diff
away_last5_goal_diff
```

---

# 9. 対戦相手強度

単純な直近5試合勝敗だけではなく、その相手がどの程度強かったかを特徴量化する。

例：

```text
home_last5_opponent_elo_avg
away_last5_opponent_elo_avg
```

これにより、

「下位チーム相手に5連勝」

と

「上位チーム相手に5連勝」

を区別できるようにする。

---

# 10. ホーム / アウェイ成績

過去一定試合数におけるホーム・アウェイ別成績を算出する。

例：

```text
home_team_home_points_avg
away_team_away_points_avg

home_team_home_goal_diff_avg
away_team_away_goal_diff_avg
```

直近10～20試合程度を候補とする。

最適期間についてはバックテストで検討する。

---

# 11. 対戦相性

両チームの直接対決結果を使用する。

ただし古い試合ほど現在の戦力との関連性が低いため、直近数年間を中心にする。

初期実装では過去3年間を使用する。

特徴量候補：

```text
home_h2h_points_avg
away_h2h_points_avg

home_h2h_goal_diff_avg
away_h2h_goal_diff_avg

h2h_match_count
```

将来的には時間減衰を導入する。

例：

```text
直近1年   weight = 1.0
2年前     weight = 0.7
3年前     weight = 0.4
```

---

# 12. スタジアム

基本データ：

```text
stadium
```

将来的に以下も特徴量として検討する。

```text
home_team_stadium_points_avg
away_team_stadium_points_avg
```

ただしサンプル数が極端に少ないスタジアムについては過学習に注意する。

国立競技場など通常ホームとは異なる開催地についても識別可能な構造にする。

---

# 13. 日程

前回試合からの経過日数を算出する。

```text
home_rest_days
away_rest_days
rest_days_diff
```

例：

```text
rest_days_diff =
home_rest_days - away_rest_days
```

カップ戦やACL等についても、将来的には含める。

---

# 14. 負傷者・出場停止

初期モデル完成後に追加する。

単純な人数だけではなく、選手の重要度も考慮する。

特徴量候補：

```text
home_injured_count
away_injured_count

home_suspended_count
away_suspended_count
```

さらに、

```text
home_missing_minutes
away_missing_minutes
```

を追加する。

`missing_minutes`は欠場選手の当該シーズン出場時間合計。

これにより、

「主力1人離脱」

と

「出場機会の少ない選手1人離脱」

を区別する。

---

# 15. 将来追加する選手戦力

将来的にはチーム単位だけでなく選手単位の戦力評価を行う。

候補：

```text
starter_strength
bench_strength
missing_strength
```

試合前の予想スタメン、発表済みスタメンなどを使用して戦力を再計算する。

これはv1では実装しない。

---

# 16. 学習用データ

最終的な`training_data.csv`は以下のような構造を想定する。

```text
match_date
home_team
away_team

home_elo
away_elo
elo_diff

home_last5_points
away_last5_points

home_last5_goals
away_last5_goals

home_last5_conceded
away_last5_conceded

home_last5_opponent_elo_avg
away_last5_opponent_elo_avg

home_team_home_points_avg
away_team_away_points_avg

home_h2h_points_avg
away_h2h_points_avg

home_rest_days
away_rest_days

result
```

---

# 17. AIモデル

## 17.1 Baseline

最初に単純モデルを作成する。

候補：

```text
Logistic Regression
```

このモデルを基準精度とする。

## 17.2 Main Model

メインモデルとして、

```text
LightGBM
```

を使用する。

3クラス分類：

```text
Away Win
Draw
Home Win
```

を行う。

---

# 18. 予測出力

予測結果は必ず確率として出力する。

例：

```text
G大阪 vs FC東京

G大阪勝利
41.8%

引き分け
28.7%

FC東京勝利
29.5%
```

単純な最大確率の勝敗だけではなく、3結果すべて表示する。

---

# 19. 予測理由

将来的にSHAPを使用して予測への影響要因を表示する。

例：

```text
FC東京勝率への影響

基礎戦力差        -4.2%
アウェイ          -5.2%
直近5試合         +4.1%
対G大阪相性       -2.3%
G大阪主力離脱     +1.8%
休養日数          +0.9%
```

ユーザーが予測結果の理由を確認できることを重要な要件とする。

---

# 20. 評価方法

単純な的中率だけで評価しない。

以下を使用する。

## Accuracy

最も確率が高かった結果が実際の結果と一致した割合。

## Log Loss

予測確率そのものの品質評価。

本システムでは特に重要。

## Brier Score

確率予測の校正精度確認に使用する。

## Confusion Matrix

```text
Home Win
Draw
Away Win
```

それぞれの予測傾向を確認する。

---

# 21. Calibration

「勝率70%」と予測された試合が、本当に約70%勝っているかを確認する。

例：

```text
予測勝率 60～70%
↓
実際の勝率 64%
```

のようになっていることが望ましい。

単なる的中率よりも、確率の信頼性を重要視する。

---

# 22. Train / Test分割

ランダム分割は禁止する。

サッカーの試合は時系列データであるため、未来のデータを過去の予測に使用してはならない。

例：

```text
2015～2023
Training

2024
Validation

2025
Test
```

またはWalk Forward Validationを使用する。

---

# 23. データリーク禁止

本プロジェクトにおける最重要ルール。

ある試合を予測するとき、その試合開始時点より後に判明する情報を絶対に使用しない。

禁止例：

```text
シーズン最終順位
シーズン終了時Elo
試合後に更新された負傷情報
対象試合結果を含んだ直近成績
対象試合結果を含んだ直接対決成績
```

特徴量生成処理では必ず時系列順に処理する。

---

# 24. 初期開発対象期間

まずデータ取得可能な範囲で、

```text
2015年～現在
```

のJ1リーグ戦を対象とする。

必要に応じて対象期間を拡張する。

昇格・降格クラブについても正常に扱える構造とする。

---

# 25. 開発フェーズ

## Phase 1

試合データ読み込み。

目標：

```text
matches.csv
```

をPythonから正常に読み込める。

---

## Phase 2

Elo Rating実装。

各試合開始直前の、

```text
home_elo
away_elo
```

を算出する。

---

## Phase 3

直近成績特徴量生成。

```text
last5_points
last5_goals
last5_conceded
```

を追加。

---

## Phase 4

Baselineモデル。

Logistic Regressionで勝敗予測。

---

## Phase 5

LightGBM導入。

3クラス確率予測を実装。

---

## Phase 6

評価環境。

```text
Accuracy
Log Loss
Brier Score
Confusion Matrix
```

を出力する。

---

## Phase 7

追加特徴量。

```text
ホーム / アウェイ成績
対戦相性
対戦相手Elo
休養日数
```

を順番に追加する。

各追加前後で性能比較を行う。

---

## Phase 8

負傷者・出場停止情報。

データ取得方法を調査し、特徴量へ追加する。

---

## Phase 9

予測理由表示。

SHAP導入。

---

## Phase 10

UI。

Streamlit等で試合を選択し、予測結果を表示できるようにする。

---

# 26. UI最終イメージ

```text
J1 Match Predictor

2026 J1 League

G大阪
vs
FC東京

────────────────

WIN PROBABILITY

G大阪
41.8%

DRAW
28.7%

FC東京
29.5%

────────────────

TEAM STRENGTH

G大阪
1638

FC東京
1579

────────────────

FC東京への主な影響

Away             -5.2%
Recent Form      +4.1%
Matchup          -2.3%
Opponent Injury  +1.8%
Rest Days        +0.9%
```

---

# 27. Codex開発ルール

CodexはこのREADME.mdをプロジェクト仕様書として参照する。

実装を依頼するときは一度にプロジェクト全体を作らせず、小さな単位で実装する。

例：

```text
README.mdの仕様に従って
src/features/elo.pyを実装してください。

条件：
・pandas DataFrameを入力する
・試合日時順に処理する
・各試合開始前のEloを記録する
・試合後にEloを更新する
・未来情報を使用しない
・pytest用テストも追加する
```

実装後は必ず、

```text
テスト
↓
結果確認
↓
Git Commit
```

の順で進める。

---

# 28. 開発方針

最初から多数の特徴量を追加しない。

まず、

```text
Elo
+
直近成績
+
ホーム / アウェイ
```

のみでBaselineを作る。

その後、

```text
対戦相性
↓
対戦相手強度
↓
休養日数
↓
スタジアム
↓
負傷者
↓
出場停止
↓
スタメン
```

の順番で追加する。

特徴量を追加するたびにモデル性能を比較し、本当に予測性能向上へ寄与しているか確認する。

性能が改善しない特徴量は無理に使用しない。

---

# 29. 最初の完成条件

v0.1では以下を満たした時点で完成とする。

- 過去J1リーグ戦データを読み込める
- 試合開始前Eloを計算できる
- 直近5試合成績を計算できる
- ホーム / アウェイを考慮できる
- LightGBMを学習できる
- 任意の対戦カードについて3結果の確率を出せる
- 過去シーズンを利用して予測精度を評価できる
- データリークが発生していない

---

# 30. 将来的な拡張

将来的には以下も検討する。

```text
J2データ
カップ戦
ACLE
天候
気温
芝状態
移動距離
連戦
監督交代
フォーメーション
スタメン
選手個人Elo
xG
シュート数
ボール保持率
PPDA
セットプレー性能
レッドカード傾向
オッズ
```

ただし、オッズを入力すると市場予測をそのまま学習してしまう可能性があるため、「純粋なサッカー情報のみを使用するモデル」と「オッズを含むモデル」は分離する。

---

# 31. 最終目標

試合前に対戦カードを選択すると、

```text
勝敗確率
現在戦力
最近の調子
対戦相性
ホーム / アウェイ影響
欠場者影響
予測理由
```

を一画面で確認できるJ1専用勝敗予測システムを完成させる。

単純な「どちらが勝つか」ではなく、

「現在どちらが強く、今回の条件によって勝率がどう変化したのか」

を説明できるAIを目指す。
