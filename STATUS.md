# J1 Match Predictor Status

## 現在のフェーズ

Phase 0: 開発環境構築 — 完了。次回はPhase 1: 試合データ読み込み。

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

## 作業中

なし。試合データの読み込み、特徴量生成、AIモデルは未実装。

## 次にやること

1. README.md、DEVELOPMENT_GUIDE.md、本ファイルを確認する。
2. Phase 1として `src/collect/matches.py` に `matches.csv` 読み込みを実装する。
   必須列、日付変換、欠損、重複、得点・resultの整合性などの検証仕様を先に確定する。
3. `tests/test_matches.py` に正常系・異常系のテストを追加し、全体テストを実行する。
4. 過去J1試合データの取得方法を調査し、`docs/DATA_SOURCES.md` に記録する。

Phase 1ではAIモデルやEloをまだ実装しない。人工データによる読込テストと実データの取得を区別する。

## 現在の問題

- 端末の3.12登録先には実体がないため、`.tools/python/` 内のPython 3.12.14で対処済み。
- 実データ未取得。データ取得元は未決定。
- `.venv` が参照するため `.tools/python/` を保持する。再構築方法はREADME冒頭に記載。
- モデル未学習のため精度評価はまだない。

## 最終検証結果

Windows / Python 3.12.14で以下を確認した。

| 確認 | 結果 |
| --- | --- |
| `python -m src.main` | 正常終了。Phase 0と予測機能未実装の案内を表示 |
| `python -m pytest` | 1件成功（起動コマンドのスモークテスト） |
| `python -m pip check` | 依存関係の不整合なし |
| 初期依存7ライブラリとpytestのimport | 8件成功（Jupyterはjupyter_coreのimportを確認） |
| 固定済みrequirementsとconstraintsでpip installのdry-run | 成功 |
| `python -m pip wheel --no-deps --wheel-dir .tools/wheels .` | パッケージビルド成功 |

上記の `python` はすべて `.\.venv\Scripts\python.exe` を使用した。
機能の単体テストは各実装フェーズで追加する。データやモデルの動作を検証した結果ではない。

## 次回の開始コマンド

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m src.main
```

## TODO

- [x] Phase 0: 初期構成・環境・管理文書・起動確認
- [ ] Phase 1: 試合データ読み込みと基本Validation
- [ ] 過去J1データの取得元決定
- [ ] Phase 2: 試合開始前Eloとリーク防止テスト
- [ ] Phase 3: 直近5試合成績
- [ ] Phase 4: Baselineと時系列評価

## 最終確認日

2026-09-11
