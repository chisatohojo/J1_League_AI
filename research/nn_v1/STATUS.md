# Phase 1.1 status: READY — chronology preparation only

2026-10-19。起点: `5ac9052a221c6d8d563ec982bc48fbddb9e80bfa`。
研究branch: `feature/nn-research-v1`。運用worktreeとは別のworktree。
Phase 1.1開始HEAD: `9b6d48e8a2dac3d2fb1a61bb2a1bfddff29a77bf`。
READYは時系列の実装・監査・テストの判定であり、学習結果や運用モデル承認ではない。

## 完了した範囲

- Python 3.12.14 / scikit-learn 1.9.1 / CPUを確認。
- 指定9特徴量、StandardScaler、MLP (32,16) と指定パラメータを固定。
- 2種類のLogistic比較、年度順5fold、研究専用モデル保存、学習曲線・評価グラフの生成コードを実装。
- 2015--2025普通J1の11 CSVとTeamMasterを既存Champion A metadataのSHAと照合。
- 3,588試合（2015--2024: 3,208、2025: 380）を確認。
- 9特徴量の計算上の欠損は0。空履歴は利用可能試合数0と実在する0集計で表現。
- 追加の保存済み特徴量はcoverage/欠損/来歴を監査しただけで、学習入力へ混ぜていない。
- NN研究・イベント処理・Elo・Formの関連テスト: **108 PASS**。
- 全期間3,588件、2024年380件、ID重複0、9特徴量の非有限値0を維持。
- 公式キャッシュ3,588ページとmetadataを全件照合。未知の時刻例外0件。

## 実行していない範囲

**実データのfit 0回、歴史評価0回、最終研究モデル学習0回。**

年度別・pooled比較表、学習済みモデル、学習曲線・評価グラフは未生成。
実データの確率・収束・性能は未検証。旧Champion A歴史評価との一致は新時系列の必須条件にしない。
合成テストのfit/predictは実データ実験と区別する。

## ID30700の解決

2024年浦和―川崎F（ID30700）は2024-08-24に当初開始し、2024-11-22に後半再開。
従来の11月22日基準の特徴量を、新研究では当初開始前の特徴量へ切り替えた。

| 項目 | 研究用の扱い（JST） |
|---|---|
| feature timestamp | 2024-08-24 19:03、当初キックオフ |
| 履歴cutoff | 2024-08-24 00:00より前の終了試合のみ |
| 元CSVのmatch_date | 2024-11-22のまま |
| final label | 最終90分のDraw（1-1） |
| result-effective timestamp | 2024-11-23 00:00から、一度だけ |

前半1-0は完成済み履歴へ入れない。11月22日の同日結果も使わない。
結果の反映境界は日付単位の保守的ポリシーであり、推測した試合終了時刻ではない。
件数合わせのために除外したり、原本の日付を8月へ移したりしていない。

当初日より前の3,097試合だけを使った独立Elo/Form照合で、全9特徴量が一致。
特徴量イベント3,588件、結果イベント3,588件を照合し、当該結果の反映は11月23日の1回。
旧方式との差はこの1試合の7特徴量のみ。他3,587試合の9特徴量は完全一致。
例：elo_diffは -9.879785575924416 → -23.138035476119057。
詳細は `audit-timing-v1_1/legacy-feature-delta.csv`。

3モデルは同じ新時系列を使用する。旧評価値は参考差分として扱い、一致判定を学習の必須条件にしない。
公式3ページの取得日時とSHA、既知の時刻注記14件を記録。未知・変更された注記や構造ではSTOP。

さらに、最終保存済み結果表は過去の公式掲載・訂正タイムスタンプそのものを証明しない。
計算上のcoverageと当時の情報可用性は区別する。正式ベンチマーク判定は変更しない。

## 次の工程（未実施）

実データの歴史学習・評価・最終モデル学習は、別途の実行指示で行う。
この工程では監査とテストだけを実施し、性能比較や新規予測へ進まない。

## 再現コマンド

独立した研究worktreeから、既存データを持つRepositoryをread-onlyの入力に指定する。
出力には未作成の新規パスを使用する。

```powershell
python -B -m pytest tests/test_nn_research_v1.py tests/test_nn_research_timing.py tests/test_elo.py tests/test_form.py -q -p no:cacheprovider
python -B -m src.modeling.nn_research_v1 --source-root <existing-data-repository> --output <new-audit-directory> --audit-only
```

学習入口は以下だが、**このPhase 1.1では実行しない**。監査の再現には上のaudit-onlyを使う。

```powershell
python -B -m src.modeling.nn_research_v1 --source-root <existing-data-repository> --output <new-research-run-directory>
```

`audit/` と `audit-strict/` は過去の監査原本、`audit-timing-v1_1/` が現行監査。
すべてaudit-onlyで学習0回。時刻ポリシー・旧評価値との比較契約を更新したが、
9特徴量・モデルパラメータ・fold・母集団は初期固定のまま。結果を見た調整はない。
旧specも保存し、現行specとSHAを再固定した。詳細は `TIMING_POLICY.md` と
`timing-v1_1/evidence-manifest.json`、`real-data-verification.json`。

## 保護対象

560保護ファイルのSHA、公式キャッシュとmetadata各3,588件のSHA、タスク2件の定義、
運用worktreeとmainの不変を確認。Champion A、保存済み14予測、運用runtime、正式ベンチマーク、
後日再現成果物、ショートカット・サーバーは変更していない。

Phase A: **BLOCKED** / Phase B: **NOT_AUTHORIZED**。
