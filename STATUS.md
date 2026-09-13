# J1 Match Predictor Status

## 現在のフェーズ

Phase 1: 試合データ読み込み・入力検証 — 完了（実装コミット `21994d1`）。
J.League Data Siteの2015年J1取得調査 — 完了（commit・push済み `79ade3b`）。
2016年J1の調査・2015年との差分検証 — 完了。2017年以降と一括取得は未着手。

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
- 保存済み2016年HTMLの来歴・SHAを照合し、同じ11列・2stage・306試合の構造を確認
- 2016年の全15列を正規化し、既存Validation・CSV往復比較・対戦網羅性・クラブ別home/awayを検証
- 2015年との差分報告と、全クラブ・全節・標本を含む人間レビュー用サマリーを出力
- 人工HTML・人工シーズン・一時キャッシュの62件を追加し、全182件のpytestが成功

## 作業中

今回は2016年の差分検証と報告まで完了。調査スクリプト・テスト・文書の変更は未コミット。
2015年調査はユーザーがcommit・push済み。再開時は作業ツリーがクリーンだった。
今回Git add / commit / pushは行っていない。報告時点で停止する。
2017年以降の結果や一括取得器は実装・取得していない。既存CSV Validationは変更していない。
Elo Rating・特徴量生成・モデル学習・予測処理は未実装。

## Git状態（2026-09-12確認）

- 正式リモートorigin: `https://github.com/chisatohojo/J1_League_AI.git`（fetch / push共通）
- 現在のブランチ: `main`、追跡先: `origin/main`
- `git fetch origin`: 成功。GitHubからの取得接続を確認
- `HEAD` / `origin/main`: `79ade3b`（2015年取得調査のコミット）。Phase 1実装は履歴の `21994d1`
- `HEAD...origin/main`: ローカルのみ0件 / リモートのみ0件。同期は不要
- 再開時はクリーン。今回はREADME、STATUS、CHANGELOG、DATA_SOURCES、DECISIONS、2015年解析補助関数の更新と、2016年調査報告・調査スクリプト・pytestの追加あり
- HTML原本・metadata・正規化検証CSV・集計JSON・人間レビュー用Markdownは既存設定によりGit対象外で、ローカルに保存
- リモートURLの変更、履歴変更、GitHubへの書き込みは行っていない

## 次にやること

1. Git状態・現在のブランチ・リモートとの差分と、README.md、DEVELOPMENT_GUIDE.md、本ファイルを確認する。
2. `docs/JLEAGUE_2016_RESEARCH.md` と人間レビュー用サマリーを確認し、今回の未コミット変更を保持する。
3. 2017年以降へ進む場合は別作業で対象年の大会方式・stage・期待試合数を少量調査する。
   調査用の「306件・2stage・各17節」の条件を全年度に仮定しない。
4. 一括取得の前に、キャッシュ優先の取得とHTML解析を分離し、失敗時の停止・訂正時の原本保存を決める。
   今回の調査用スクリプトにはネットワーク機能を追加していない。
5. チーム・スタジアム略称の名称マスターは別途検討する。今回の原表記を直接変更しない。
6. Elo Rating（Phase 2）はデータ取得と分けて実装する。

今回の差分検証には保存済み2015年・2016年の実データを使用した。pytestは人工データで検証し、実データを必要としない。

## 2016年調査成果物

- 原本: `data/raw/jleague/2016_j1_search.html`（385,420 bytes）、同名metadata JSON
- 取得日時: `2026-09-11T09:06:09.249866+00:00`（中断前の取得日時を保持）
- SHA-256: `e39d283c47667eb5f337b7d950c1da3c1a55f8ea7e76fc7a8827d3bd9d21472c`
- 正規化候補: `data/processed/jleague/2016_matches_probe.csv`（306行・15列）
- 集計・差分: `data/processed/jleague/2016_matches_probe.summary.json`
- 人間レビュー: `data/processed/jleague/2016_matches_probe.review.md`
- 再現処理: `scripts/inspect_jleague_2016.py`（オフライン・2016年と2015年の比較）
- 報告: `docs/JLEAGUE_2016_RESEARCH.md`

2016年の初回取得はData SiteへGET 1回。再開後は両年の保存原本だけを使用し、追加アクセス0回。
2016年も1st / 2nd各153試合、18クラブ・各34試合（home17・away17）、2016-02-27～11-03。
既存Validationは変更なし。全15列の欠損・空白、各種重複、同一チーム、負の得点、result矛盾は0件。
2015年との主な差分は参加3クラブ、会場表記、開催期間。1st第7・10・13節には月をまたぐ実施日がある。
先頭5・末尾5・`random_state=42` の10試合を含む全レビュー項目をMarkdownとJSONに出力済み。

## 2015年調査成果物

- 原本: `data/raw/jleague/2015_j1_search.html`（386,173 bytes）、同名metadata JSON
- 補助記録: `data/raw/jleague/robots.txt`（404応答）、`robots.metadata.json`
- 正規化候補: `data/processed/jleague/2015_matches_probe.csv`（306行・15列）
- 集計: `data/processed/jleague/2015_matches_probe.summary.json`
- 再現処理: `scripts/inspect_jleague_2015.py`（オフライン・2015年固定）
- 報告: `docs/JLEAGUE_2015_RESEARCH.md`

2015年調査時のData Siteへの直接HTTPアクセスは結果HTML 1回、robots確認1回の計2回。
2015年原本・metadata・CSV・集計JSONは今回変更せず、比較用に読み取った。
試合詳細・ステージ別ページは取得していない。

## 現在の問題

- 端末の3.12登録先には実体がないため、`.tools/python/` 内のPython 3.12.14で対処済み。
- Data Siteの2017年以降は未取得。年度別大会形式の一般化・一括取得・訂正データの更新方針は未実装。
- 取得元のチーム名・スタジアム略称を保持しており、名称マスターによる統一はまだ行っていない。
- 既定入力 `data/raw/matches.csv` は未作成。調査結果はprocessed側の検証CSVに分離した。
- `.venv` が参照するため `.tools/python/` を保持する。再構築方法はREADME冒頭に記載。
- モデル未学習のため精度評価はまだない。
- 現在失敗しているテストや既知の実装不具合はない。

## 最終検証結果

2016年差分検証後（Windows / Python 3.12.14、2026-09-12）:

| 確認 | 結果 |
| --- | --- |
| `python -m scripts.inspect_jleague_2016` | 両年のURL・SHA等の照合、2016年306件の正規化、既存Validation、CSV往復比較が成功。通信0回 |
| 2015年互換性 | 既定パーサーの再解析結果が既存2015年CSVと完全一致。原本・出力の書き換えなし |
| 2016年の完全性 | 両stage153件、各17節・各9試合、各クラブ34試合・home17/away17、対戦組合せの網羅を確認 |
| 欠損・重複・得点整合性 | 全15列欠損・空白0。重複ID/試合/行、同一チーム、負得点、result矛盾0。両年のID交差0 |
| 独立ローカルレビュー | 両年のHTML構造一致、2015/2016 CSVと原本再解析の一致、全レビュー出力を確認。重大な問題なし |
| `python -m pytest` | 全182件成功（既存120件＋新規62件）。既存テスト・Validationの変更なし |
| `git diff --check` | 問題なし |
| Git確認 | fetch成功、main / origin/mainは `79ade3b` で差分0/0。今回の変更は未ステージ・未コミット |

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

上記2015年調査時の異常入力確認はインメモリで実行した。今回、解析・完全性・キャッシュ来歴の人工fixtureをpytestへ追加した。

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
.\.venv\Scripts\python.exe -m scripts.inspect_jleague_2016
```

## TODO

- [x] Phase 0: 初期構成・環境・管理文書・起動確認
- [x] Phase 1: 試合データ読み込みと基本Validation
- [x] 過去J1データの取得元決定（J.League Data Site）
- [x] 2015年J1両ステージの取得・HTML調査・既存CSV契約への適合確認
- [x] 2016年J1の取得・2015年との差分検証・人間レビュー出力
- [x] 人工HTML・人工シーズン・キャッシュ来歴のpytest
- [ ] キャッシュ優先のData Site取得アダプター（ネットワーク取得）
- [ ] チーム・スタジアム名称マスター
- [ ] 2017年以降の調査・取得（報告後の別作業）
- [ ] Phase 2: 試合開始前Eloとリーク防止テスト
- [ ] Phase 3: 直近5試合成績
- [ ] Phase 4: Baselineと時系列評価

## 最終確認日

2026-09-12
