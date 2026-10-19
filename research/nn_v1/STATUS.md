# Phase 1 status: HOLD — original-kickoff chronology unresolved

2026-10-19。起点: `5ac9052a221c6d8d563ec982bc48fbddb9e80bfa`。
研究branch: `feature/nn-research-v1`。運用worktreeとは別のworktree。

## 完了した範囲

- Python 3.12.14 / scikit-learn 1.9.1 / CPUを確認。
- 指定9特徴量、StandardScaler、MLP (32,16) と指定パラメータを固定。
- 2種類のLogistic比較、年度順5fold、研究専用モデル保存、学習曲線・評価グラフの生成コードを実装。
- 2015--2025普通J1の11 CSVとTeamMasterを既存Champion A metadataのSHAと照合。
- 3,588試合（2015--2024: 3,208、2025: 380）を確認。
- 9特徴量の計算上の欠損は0。空履歴は利用可能試合数0と実在する0集計で表現。
- 追加の保存済み特徴量はcoverage/欠損/来歴を監査しただけで、学習入力へ混ぜていない。
- NN研究・Elo・Formの合成テスト: **89 PASS**。

## 実行していない範囲

**実データのfit 0回、歴史評価0回、最終研究モデル学習0回。**

年度別・pooled比較表、学習済みモデル、学習曲線・評価グラフは未生成。
実データのクラス順・確率・収束、Champion A歴史評価との一致も未検証。
合成テストのfit/predictは実データ実験と区別する。

## 保留の理由

2024年浦和―川崎F（ID30700）は2024-08-24に当初開始し、2024-11-22に後半再開。
原本のmatch_dateおよび既存の凍結基準は11月22日を使うため、そのままのElo/Formは
当初開始後の8--11月の結果を含む。当初キックオフ前の特徴量とは認められない。

利用者は「当初キックオフ前を厳守し、この1試合の扱い確定まで学習を保留する」を選択。
全件点検でこのIDがあれば、最初のfold開始前に停止する。fit/evaluate/predictの研究APIにも
ガードを置き、再開日を認めるだけのCLIオプションは提供しない。
件数合わせのために除外したり、原本の日付を8月へ移したりしていない。

さらに、最終保存済み結果表は過去の公式掲載・訂正タイムスタンプそのものを証明しない。
計算上のcoverageと当時の情報可用性は区別する。正式ベンチマーク判定は変更しない。

## 次の最小作業（未実施）

この1試合について、当初開始前の特徴量cutoffと、最終終了後の履歴反映時点を分離する
研究用ポリシーを、保存済み公式根拠で確定する。過去ソースと正式基準は変更しない。
その方法が確定するまでは、件数変更・基準変更・学習再開を自動判断しない。
安全な時刻整合と3,208/3,588件の両立、既存歴史評価との差異の説明を先に確認する。

## 再現コマンド

独立した研究worktreeから、既存データを持つRepositoryをread-onlyの入力に指定する。
出力には未作成の新規パスを使用する。

```powershell
python -B -m pytest tests/test_nn_research_v1.py tests/test_elo.py tests/test_form.py -q -p no:cacheprovider
python -B -m src.modeling.nn_research_v1 --source-root <existing-data-repository> --output <new-audit-directory> --audit-only
```

本来の学習入口は以下だが、**現在は時刻ガードでfit前にHOLDになる。保留中は実行しない**。

```powershell
python -B -m src.modeling.nn_research_v1 --source-root <existing-data-repository> --output <new-research-run-directory>
```

`audit/` は回答前の監査原本、`audit-strict/` が回答を反映した現行監査。
両者ともaudit-onlyで学習0回。初期specと現行specの差分は時刻ポリシーのみで、
9特徴量・モデルパラメータの変更や結果を見た調整はない。

Phase A: **BLOCKED** / Phase B: **NOT_AUTHORIZED**。
