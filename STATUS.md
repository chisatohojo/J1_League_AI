# J1 Match Predictor Status

## 現在のフェーズ

Phase 1: 試合データ読み込み・入力検証 — 完了（変更は未コミット）。

## 完了

- 元のプロジェクト仕様書・開発手順書を確認
- README.md、DEVELOPMENT_GUIDE.mdを整備
- パッケージ・データ・モデル・分析・テスト用のディレクトリを作成
- Gitリポジトリをmainブランチで初期化
- プロジェクト内のPython 3.12.14から仮想環境を作成
- 初期依存7ライブラリとpytestを導入し、直接依存・推移的依存115件をバージョン固定
- 起動確認用の `src/main.py` とpytestスモークテストを作成
- 設計判断・データ取得元・モデル実験・変更履歴の管理文書を作成
- 起動、テスト、ライブラリ読み込み、依存整合性、パッケージビルドの検証を完了
- Phase 1: `src/collect/matches.py` にCSV読み込みとDataFrame検証を分離して実装
- 必須列・欠損・日付・整数・重複ID/試合・同一チーム・負の得点・result整合性を検証
- CSVのBOM・文字コード指定・列数・重複ヘッダーを扱い、原本と追加列・行列順・indexを保持
- `tests/test_matches.py` の119件と既存1件、全120件のテストが成功
- READMEの入力契約、CHANGELOG、設計判断、起動メッセージを更新

## 作業中

なし。ユーザーの指示に従い、実装・テスト結果を報告する段階で停止。Git add / commitは行っていない。
Elo Rating・特徴量生成・モデル学習・予測処理は未実装。

## 次にやること

1. README.md、DEVELOPMENT_GUIDE.md、本ファイルを確認する。
2. Phase 1の変更をレビューする。コミットの実施はユーザーの指示を待つ。
3. 過去J1試合データの取得方法を調査し、`docs/DATA_SOURCES.md` に記録する。
4. 実データを入力仕様に合わせて読み込み、行数・日付範囲・チーム表記などを確認する。
5. 次の機能開発はPhase 2: 試合開始前Eloとリーク防止テスト。別の作業単位で実装する。

今回の検証は人工データのみ。実データの取得や名称マスターの実装は行っていない。

## 現在の問題

- 端末の3.12登録先には実体がないため、`.tools/python/` 内のPython 3.12.14で対処済み。
- 実データ未取得。データ取得元は未決定。
- `.venv` が参照するため `.tools/python/` を保持する。再構築方法はREADME冒頭に記載。
- モデル未学習のため精度評価はまだない。
- 現在失敗しているテストや既知の実装不具合はない。

## 最終検証結果

Phase 1の検証（Windows / Python 3.12.14）:

| 確認 | 結果 |
| --- | --- |
| `python -m pytest tests/test_matches.py -q` | 新規119件成功 |
| `python -m pytest` | 全120件成功（既存1件を含む）。失敗・警告なし |
| `python -m src.main` | 正常終了。Phase 1の実装状況を表示 |
| 独立レビュー | 数値・日付境界、BOM、ID保持、原本非変更など20件の実行確認が成功 |
| `git diff --check` | 問題なし |

テストは小さな人工DataFrameとpytestの一時CSVを使用する。`data/raw/` の実データには依存しない。
新しい依存パッケージは追加していない。

Phase 0で確認済みの環境検証:

| 確認 | 結果 |
| --- | --- |
| `python -m pip check` | 依存関係の不整合なし |
| 初期依存7ライブラリとpytestのimport | 8件成功（Jupyterはjupyter_coreのimportを確認） |
| 固定済みrequirementsとconstraintsでpip installのdry-run | 成功 |
| `python -m pip wheel --no-deps --wheel-dir .tools/wheels .` | パッケージビルド成功 |

上記の `python` はすべて `.\.venv\Scripts\python.exe` を使用した。
実データの妥当性やモデル精度を検証した結果ではない。

## 次回の開始コマンド

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m src.main
```

## TODO

- [x] Phase 0: 初期構成・環境・管理文書・起動確認
- [x] Phase 1: 試合データ読み込みと基本Validation
- [ ] 過去J1データの取得元決定
- [ ] Phase 2: 試合開始前Eloとリーク防止テスト
- [ ] Phase 3: 直近5試合成績
- [ ] Phase 4: Baselineと時系列評価

## 最終確認日

2026-09-11
