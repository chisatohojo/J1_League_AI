# J1 Match Predictor Status

## 現在のフェーズ

Phase 1: 試合データ読み込み・入力検証 — 完了（実装コミット `21994d1`）。
J.League Data Siteの2015年J1取得調査 — 完了（commit・push済み `79ade3b`）。
2016年J1の調査・2015年との差分検証 — 完了（commit・push済み `43efdcf`）。
2015年・2016年の解析共通化 — 完了（commit・push済み `9c165d0`）。
2017年J1の取得・full_season対応・回帰検証 — 完了、未コミット。2018年以降と一括取得は未着手。

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
- `src/collect/jleague.py` へHTML解析・キャッシュ照合・集計を集約し、年度引数で共用
- `scripts/inspect_jleague.py --year` を追加し、旧年度別CLIを互換入口に整理
- 両年CSV・集計JSONと2016年レビューの計5ファイルが変更前とバイト単位で完全一致
- 共通化前のコードから人工データの期待出力を固定した25件の回帰テストを追加し、全207件成功
- 2017年の公式大会方式と結果HTMLを確認し、1ステージ・34節・306試合を検証
- 年度形式を明示し、2017年をfull_seasonとして既存15列へ正規化。共通CSV Validationを変更せず全件通過
- 2017年のCSV・集計JSON・人間レビューを出力し、日程注記を調査報告へ記録
- 2017年向け人工データテスト46件を追加して全253件成功。2015/2016年の既存5出力もバイト単位で一致

## 作業中

今回は2017年の取得・正規化・回帰テスト・調査報告まで完了。2017年対応のコード・テスト・文書は未コミット。
2015/2016年調査と共通化はユーザーがcommit・push済み。
2017年作業の開始時はクリーン。利用制限による中断からの再開時は変更4ファイル・新規テスト1ファイルがあり、保持して作業を再開した。
今回Git add / commit / pushは行っていない。報告時点で停止する。
2018年以降の結果や一括取得器は実装・取得していない。既存CSV Validationは変更していない。
Elo Rating・特徴量生成・モデル学習・予測処理は未実装。

## Git状態（2026-09-13確認）

- 正式リモートorigin: `https://github.com/chisatohojo/J1_League_AI.git`（fetch / push共通）
- 現在のブランチ: `main`、追跡先: `origin/main`
- `git fetch origin`: 成功。GitHubからの取得接続を確認
- `HEAD` / `origin/main`: `9c165d0`（解析共通化）。2016年調査は `43efdcf`、2015年調査は `79ade3b`
- `HEAD...origin/main`: ローカルのみ0件 / リモートのみ0件。同期は不要
- 今回は共通モジュール・共通CLI・未対応年度テスト・README・STATUS・CHANGELOG・DATA_SOURCES・DECISIONSの更新、2017年調査報告と専用テストの追加あり
- HTML原本・metadata・正規化検証CSV・集計JSON・人間レビュー用Markdownは既存設定によりGit対象外で、ローカルに保存
- リモートURLの変更、履歴変更、GitHubへの書き込みは行っていない

## 次にやること

1. Git状態・現在のブランチ・リモートとの差分と、README.md、DEVELOPMENT_GUIDE.md、本ファイルを確認する。
2. `docs/JLEAGUE_2017_RESEARCH.md` と人間レビュー、今回の未コミット変更・回帰テストを確認する。
3. 2018年以降へ進む場合は別作業で対象年の大会方式・stage・期待試合数を少量調査する。
   今回確認した3年度の形式を未調査年度に仮定しない。
4. 一括取得の前に、キャッシュ優先の取得とHTML解析を分離し、失敗時の停止・訂正時の原本保存を決める。
   今回の調査用スクリプトにはネットワーク機能を追加していない。
5. チーム・スタジアム略称の名称マスターは別途検討する。今回の原表記を直接変更しない。
6. Elo Rating（Phase 2）はデータ取得と分けて実装する。

今回の完全一致検証には2017年対応前に退避した2015年・2016年の実出力を使用した。
pytestは人工データと共通化前コードによる固定ハッシュで検証し、実データと通信を必要としない。

## 共通解析の構成と互換性

- 共通処理: `src/collect/jleague.py`。HTML解析・キャッシュ読取・集計は明示的な年度引数を受け取る。
- 共通CLI: `scripts/inspect_jleague.py --year 2015` / `--year 2016` / `--year 2017`。
- 旧 `scripts/inspect_jleague_2015.py` / `inspect_jleague_2016.py` は共通処理を呼ぶ互換入口。
- 2015年はCSV・集計JSON、2016年はCSV・集計JSON・人間レビューを従来と同じ名前・内容で出力。
  2017年もCSV・集計JSON・人間レビューを出力する。
- 2016年は2015年、2017年は2016年キャッシュと比較する。新しい年への自動巡回・取得機能は持たない。
- `SEASON_STAGES` に2015/2016年の1st・2nd各17節、2017年のfull_season・34節を明示。
  年度と大会表記が矛盾する入力は拒否し、元の大会名と節番号を保持する。
- 既存のstage、round、match_id等の15列、型、名称、行列順、集計・レビュー形式を維持。
- 全対象年度でHTMLとmetadataを必須とし、要求/最終URL、status、バイト数、SHA、取得日時の存在を照合。
  2015年旧CLIのみmetadata任意だった扱いを統一した。欠落・不一致時は停止し、自動再取得しない。
- 回帰テスト: `tests/test_jleague_common.py`、期待値と出所: `tests/fixtures/jleague_refactor/`。
  期待値は共通化前の `43efdcf` のコードから人工データで作成し、新コードから再生成していない。
- 2017年の初回取得でData SiteへのGETは1回。再開後は追加アクセス0回。
  2015/2016年のHTML・metadata4ファイルはバイト列も不変。

## 2017年調査成果物

- 原本: `data/raw/jleague/2017_j1_search.html`（368,692 bytes）、同名metadata JSON
- UTC取得日時: `2026-09-13T03:27:33.163161+00:00`（中断前の記録を保持）
- SHA-256: `1a70a85456082b68c9802af7070d560bf5172e88ac4f361c6d72749f02c751ec`
- 正規化候補: `data/processed/jleague/2017_matches_probe.csv`（306行・15列）
- 集計・差分: `data/processed/jleague/2017_matches_probe.summary.json`
- 人間レビュー: `data/processed/jleague/2017_matches_probe.review.md`
- 再現処理: `scripts/inspect_jleague.py --year 2017`（2016年のキャッシュも比較に使用）
- 報告: `docs/JLEAGUE_2017_RESEARCH.md`

2017年は1ステージ制。全306試合をfull_season、round1～34として扱い、各節9試合・全18クラブの各1回出場を確認。
各クラブ年間34試合（home17・away17）、開催期間2017-02-25～12-02。
必須10列＋追加5列を維持し、既存ValidationとCSV再読込を通過。欠損・空白・重複・得点矛盾は0件。
resultはAway Win107・Draw73・Home Win126、総得点793、会場24表記。
第13節のACLに伴う開催日と第22節の浦和の日程に関する注記は原本に保持し、調査報告へ記録した。
全クラブ・全節・先頭5・末尾5・seed42の10試合を含む人間レビューを出力済み。

## 2016年調査成果物

- 原本: `data/raw/jleague/2016_j1_search.html`（385,420 bytes）、同名metadata JSON
- 取得日時: `2026-09-11T09:06:09.249866+00:00`（中断前の取得日時を保持）
- SHA-256: `e39d283c47667eb5f337b7d950c1da3c1a55f8ea7e76fc7a8827d3bd9d21472c`
- 正規化候補: `data/processed/jleague/2016_matches_probe.csv`（306行・15列）
- 集計・差分: `data/processed/jleague/2016_matches_probe.summary.json`
- 人間レビュー: `data/processed/jleague/2016_matches_probe.review.md`
- 再現処理: `scripts/inspect_jleague.py --year 2016`（オフライン・2016年と2015年の比較、旧CLIも利用可能）
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
- 再現処理: `scripts/inspect_jleague.py --year 2015`（オフライン・年度指定、旧2015年固定CLIも利用可能）
- 報告: `docs/JLEAGUE_2015_RESEARCH.md`

2015年調査時のData Siteへの直接HTTPアクセスは結果HTML 1回、robots確認1回の計2回。
今回の共通化では原本・metadataを読み取り、CSV・集計JSONを再生成して変更前とのバイト一致を確認した。
試合詳細・ステージ別ページは取得していない。

## 現在の問題

- 端末の3.12登録先には実体がないため、`.tools/python/` 内のPython 3.12.14で対処済み。
- Data Siteの2018年以降は未取得。確認した3年度以外の大会形式・一括取得・訂正データの更新運用は未実装。
- 取得元のチーム名・スタジアム略称を保持しており、名称マスターによる統一はまだ行っていない。
- 既定入力 `data/raw/matches.csv` は未作成。調査結果はprocessed側の検証CSVに分離した。
- `.venv` が参照するため `.tools/python/` を保持する。再構築方法はREADME冒頭に記載。
- モデル未学習のため精度評価はまだない。
- 現在失敗しているテストや既知の実装不具合はない。

## 最終検証結果

2017年対応の完了時（Windows / Python 3.12.14、2026-09-13）:

| 確認 | 結果 |
| --- | --- |
| 2017年作業開始前 `python -m pytest` | 既存207件成功 |
| `python -m scripts.inspect_jleague --year 2017` | 306件の正規化・既存Validation・CSV往復比較に成功。再解析の通信0回 |
| 2017年の完全性 | full_season、1～34節各9試合、18クラブ各34/home17/away17、無向153組各2回・有向306組各1回 |
| 2015/2016年の回帰 | 固定期待値テスト成功。退避した実出力5ファイルと再生成結果がバイト単位で完全一致 |
| 原本保護 | 2015/2016年のHTML・metadata4ファイルは不変。2017年のSHA・来歴を照合して再利用 |
| `python -m pytest` | 全253件成功（既存207件＋新規46件） |
| 独立レビュー | 2017 CSVの原本再解析・summaryとの一致、旧9ファイルの不変、2018年以降の拒否を確認。重大な不足なし |
| `git diff --check` | 問題なし |
| Git確認 | main / origin/mainは `9c165d0`、差分0/0。未コミット変更を保持、add・commit・pushなし |

未対応年を検証する既存テストの2017は2018へ置き換えた。固定ハッシュ・既存CSV Validation・そのテストに変更はない。

共通解析へのリファクタリング後（Windows / Python 3.12.14、2026-09-13）:

| 確認 | 結果 |
| --- | --- |
| 作業前 `python -m pytest` | 既存182件成功 |
| `python -m scripts.inspect_jleague --year 2015` / `--year 2016` | 各306件の解析・Validation・CSV再読込成功。通信0回 |
| 実出力の完全一致 | 退避した両年CSV・集計JSON・2016年レビューの5ファイルすべてがバイト単位で一致 |
| DataFrameの完全一致 | 両年とも306行・15列、全値・型・列順・行順・indexが退避CSV読取結果と完全一致 |
| 原本保護 | 両年HTML・metadataの4ファイルのバイト列とSHAが作業前と一致 |
| 固定期待値による回帰テスト | 人工両年データを新API・新CLI・旧CLIで処理し、共通化前の全5出力ハッシュと一致 |
| `python -m pytest` | 全207件成功（既存182件＋新規25件）。既存テスト・共通CSV Validationの変更なし |
| 独立レビュー | パーサー・数値構文・Markdown生成のAST一致、依存方向、情報保持、原本非変更を確認。重大な問題なし |
| `git diff --check` | 問題なし |
| Git確認 | fetch成功、main / origin/mainは `43efdcf` で差分0/0。今回の変更は未ステージ・未コミット |

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
.\.venv\Scripts\python.exe -m scripts.inspect_jleague --year 2015
.\.venv\Scripts\python.exe -m scripts.inspect_jleague --year 2016
.\.venv\Scripts\python.exe -m scripts.inspect_jleague --year 2017
```

## TODO

- [x] Phase 0: 初期構成・環境・管理文書・起動確認
- [x] Phase 1: 試合データ読み込みと基本Validation
- [x] 過去J1データの取得元決定（J.League Data Site）
- [x] 2015年J1両ステージの取得・HTML調査・既存CSV契約への適合確認
- [x] 2016年J1の取得・2015年との差分検証・人間レビュー出力
- [x] 人工HTML・人工シーズン・キャッシュ来歴のpytest
- [x] 2015/2016共通解析・年度指定CLI・旧出力との完全一致テスト
- [x] 2017年J1の取得・full_season対応・Validation・回帰テスト
- [ ] キャッシュ優先のData Site取得アダプター（ネットワーク取得）
- [ ] チーム・スタジアム名称マスター
- [ ] 2018年以降の調査・取得（報告後の別作業）
- [ ] Phase 2: 試合開始前Eloとリーク防止テスト
- [ ] Phase 3: 直近5試合成績
- [ ] Phase 4: Baselineと時系列評価

## 最終確認日

2026-09-13
