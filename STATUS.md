# J1 Match Predictor Status

## 現在のフェーズ

Phase 1: 試合データ読み込み・入力検証 — 完了（実装コミット `21994d1`）。
J.League Data Siteの2015年J1取得調査 — 完了。複数年取得は未着手。

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
- 正式リモートへのfetch接続とorigin/mainの参照、ローカルとの一致を確認
- Gitの開始・同期・完了手順と禁止操作を開発手順書へ記録
- J.League Data Siteを一次データ源に採用し、2015年の結果HTMLと取得metadataを保存
- 1st / 2nd各153試合、計306試合を抽出して既存ValidationとCSV再読込で検証
- 原本を再利用する2015年専用オフライン調査スクリプト、調査報告、取得元・正規化方針の文書を追加

## 作業中

今回は2015年の取得調査と報告まで完了。調査スクリプト・文書の変更は未コミット。
今回Git add / commit / pushは行っていない。
2016年以降の結果や複数年取得器は実装・取得していない。既存CSV Validationは変更していない。
Elo Rating・特徴量生成・モデル学習・予測処理は未実装。

## Git状態（2026-09-11確認）

- 正式リモートorigin: `https://github.com/chisatohojo/J1_League_AI.git`（fetch / push共通）
- 現在のブランチ: `main`、追跡先: `origin/main`
- `git fetch origin`: 成功。GitHubからの取得接続を確認
- `HEAD` / `origin/main`: `0ef1972`（Git運用方針の文書コミット）。Phase 1実装は履歴の `21994d1`
- `HEAD...origin/main`: ローカルのみ0件 / リモートのみ0件。同期は不要
- 作業開始時はクリーン。今回はREADME、STATUS、CHANGELOG、DATA_SOURCES、DECISIONSの更新と、調査報告・調査スクリプトの追加あり
- HTML原本・metadata・正規化検証CSV・集計JSONは既存設定によりGit対象外で、ローカルに保存
- リモートURLの変更、履歴変更、GitHubへの書き込みは行っていない

## 次にやること

1. Git状態・現在のブランチ・リモートとの差分と、README.md、DEVELOPMENT_GUIDE.md、本ファイルを確認する。
2. `docs/JLEAGUE_2015_RESEARCH.md` の取得結果と実装方針をレビューし、今回の未コミット変更を保持する。
3. 次回の取得機能は、キャッシュ優先の取得とHTML解析を分けたData Site用アダプターから始める。
   今回の調査用スクリプトにはネットワーク機能を追加していない。
4. チーム・スタジアム略称の名称マスターと、年度ごとの大会方式・期待試合数を確認する。
5. 複数年取得は今回の報告後、別の作業単位で進める。2015年の2ステージ制を全年度に仮定しない。
6. Elo Rating（Phase 2）はデータ取得と分けて実装する。

今回の正規化検証には保存済み2015年の実データを使用した。pytestの120件は従来どおり人工データによる検証。

## 2015年調査成果物

- 原本: `data/raw/jleague/2015_j1_search.html`（386,173 bytes）、同名metadata JSON
- 補助記録: `data/raw/jleague/robots.txt`（404応答）、`robots.metadata.json`
- 正規化候補: `data/processed/jleague/2015_matches_probe.csv`（306行・15列）
- 集計: `data/processed/jleague/2015_matches_probe.summary.json`
- 再現処理: `scripts/inspect_jleague_2015.py`（オフライン・2015年固定）
- 報告: `docs/JLEAGUE_2015_RESEARCH.md`

Data Siteへの直接HTTPアクセスは結果HTML 1回、robots確認1回の計2回。
それ以降は原本を再利用し、試合詳細・ステージ別ページ・他年を追加取得していない。

## 現在の問題

- 端末の3.12登録先には実体がないため、`.tools/python/` 内のPython 3.12.14で対処済み。
- Data Siteの2015年以外は未取得。複数年取得と訂正データの更新方針は未実装。
- 取得元のチーム名・スタジアム略称を保持しており、名称マスターによる統一はまだ行っていない。
- 既定入力 `data/raw/matches.csv` は未作成。調査結果はprocessed側の検証CSVに分離した。
- `.venv` が参照するため `.tools/python/` を保持する。再構築方法はREADME冒頭に記載。
- モデル未学習のため精度評価はまだない。
- 現在失敗しているテストや既知の実装不具合はない。

## 最終検証結果

2015年調査後の検証（Windows / Python 3.12.14）:

| 確認 | 結果 |
| --- | --- |
| `python -m scripts.inspect_jleague_2015` | 保存HTMLのSHA照合、306件の正規化、既存Validation、CSV往復比較が成功。通信0回 |
| 2015年の完全性 | 両ステージ153件、各17節・各節9試合、同じ18クラブ・各クラブ各ステージ17試合 |
| 必須欠損・ID重複・同一試合重複 | すべて0件 |
| 独立ローカル解析 | 全306件受理、クラブ別ホーム/アウェイ各17試合、総得点820を確認 |
| 調査スクリプトの一時的な異常入力確認 | 構造変更・年違い・不正得点・不完全件数等13条件、SHA不一致・他年引数を拒否 |
| `python -m pytest` | 既存全120件成功。既存テスト・Validationの変更なし |
| `git diff --check` / 既存コードのdiff | 問題なし / 差分なし |

調査スクリプトの異常入力確認はインメモリで実行した。本番取得器用のfixtureテストは次の実装時に追加する。

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
モデル精度の評価は未実施。

## 次回の開始コマンド

```powershell
git status
git branch --show-current
git rev-list --left-right --count HEAD...origin/main
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m scripts.inspect_jleague_2015
```

## TODO

- [x] Phase 0: 初期構成・環境・管理文書・起動確認
- [x] Phase 1: 試合データ読み込みと基本Validation
- [x] 過去J1データの取得元決定（J.League Data Site）
- [x] 2015年J1両ステージの取得・HTML調査・既存CSV契約への適合確認
- [ ] キャッシュ優先のData Site取得アダプターと人工HTMLテスト
- [ ] チーム・スタジアム名称マスター
- [ ] 2016年以降の取得（調査報告後の別作業）
- [ ] Phase 2: 試合開始前Eloとリーク防止テスト
- [ ] Phase 3: 直近5試合成績
- [ ] Phase 4: Baselineと時系列評価

## 最終確認日

2026-09-11
