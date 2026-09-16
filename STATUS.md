# J1 Match Predictor Status

## 現在のフェーズ

Phase 1: 試合データ読み込み・入力検証 — 完了（実装コミット `21994d1`）。
J.League Data Siteの2015年J1取得調査 — 完了（commit・push済み `79ade3b`）。
2016年J1の調査・2015年との差分検証 — 完了（commit・push済み `43efdcf`）。
2015年・2016年の解析共通化 — 完了（commit・push済み `9c165d0`）。
2017年J1の取得・full_season対応・回帰検証 — 完了（commit・push済み `3116b12`）。
2021年J1の20クラブ制・大会構造検証 — 完了（commit・push済み `ec065e7`）。
2018～2020年J1の取得・共通検証 — 完了（commit・push済み `b1c027d`）。
2022・2023年J1の取得・共通検証 — 完了（commit・push済み `3194dd5`）。
2024・2025年J1の取得・共通検証 — 完了（commit・push済み `a1f9f50`）。2015～2025年を検証済み。
2026年J1百年構想リーグの調査・専用解析・正規化・大会検証 — 完了（commit・push済み `f60d28f`）。
通常2026/27 J1の更新アダプター・初回bootstrap・再処理と回帰検証 — 完了（commit・push済み `b50dd86`）。
通常2026/27 J1の候補69試合の公式終了確認・completedへの昇格 — 完了（commit・push済み `616d345`）。
Phase 2前準備: チーム名称マスター — 完了（commit・push済み `b62fc5a`）。
Phase 2: 最小Elo API — 完了（commit・push済み `f525ee9`）。
Phase 2: 2015～2025通常J1への時系列適用 — 完了（commit・push済み `5be560b`）。
Phase 2: 百年構想リーグ200試合へのElo接続 — 完了（commit・push済み `95b8e7e`）。
Phase 2: 通常2026/27 J1のcompleted70試合へのElo接続 — 完了（commit・push済み `c6a4ede`）。
Phase 2: 試合前Elo履歴・現在ratingのCSV出力 — 実装済み（未コミット）。

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
- 2021年の公式大会方式とHTMLを確認し、20クラブ・38節・380試合をfull_seasonとして正規化
- クラブ数とstage内の総当たり回数から期待件数を導出し、各節の全クラブ1回出場も検証
- 既存Validationを変更せず2021年全件通過。各クラブ38/home19/away19、欠損・重複・得点矛盾0件
- 2021年のCSV・集計JSON・人間レビュー・調査報告を作成し、訂正スコアとhome/away入替注記を記録
- 新規33件を含む全286テスト成功。2017年の旧コード由来固定ハッシュと、既存3年度の8実出力の完全一致を確認
- 2018～2020年の原本を各GET1回で取得し、年度設定追加のみで各306試合を共通解析・既存Validationへ通した
- 各年18クラブ・34節各9・全クラブ34/home17/away17、欠損・重複・得点矛盾0件を自動確認
- 各年度のCSV・集計JSON・人間レビューを生成。2020年の非連続ID・無観客・日程変更等を調査報告へ記録
- 既存正常系3テストをparameterizeして9ケース追加、全295件成功。既存4年度の11出力と原本・metadata8ファイルの完全一致を確認
- 2022・2023年を各GET1回で取得し、年度形式・比較先の設定追加だけで両年306試合を既存Validationへ通した
- 各18クラブ・34節各9・全クラブ34/home17/away17、欠損・重複・得点矛盾0件、両年CSV・集計・レビューを生成
- 共通parameterized testへ6ケース追加、全301件成功。2022年の比較元2021年は20クラブ・380試合として検証
- 2015～2021年の既存20出力と原本・metadata14ファイルのバイト不変、全9年度2,828件のID一意性を確認
- 2024・2025年を各GET1回で取得し、公式の20クラブ・2回戦総当たりと各380試合の原本を照合
- 両年38節各10、全クラブ38/home19/away19、全190対戦各2回・方向付き380対戦各1回を既存共通処理で検証
- 既存Validationを変更せず両年全件通過。欠損・重複・得点矛盾0件、CSV・集計JSON・人間レビューを生成
- 共通parameterized testへ6ケース追加し全307件成功。既存26出力・原本とmetadata18ファイルのバイト不変を確認
- 2025年の非連続ID、両年の分散日程・会場表記、2024年の後半再開試合を調査報告へ記録
- 保存済み百年構想リーグ14原本・metadataを保持し、地域180＋PO20の全200試合を独立監査
- 専用解析・正規化・大会検証・CLIを追加。90分結果、延長増分、PK、単一試合と2戦全体の勝者を区別
- 地域EAST/WEST各90試合・18節、20クラブ各20試合（home10／away10）、地域PK51・延長1を確認
- 試合CSV・PO対戦結果CSV・集計JSON・人間レビューを生成し、CSV型往復を確認
- 2015～2025年を隔離フォルダーで再生成し全32出力がバイト一致。元の原本・metadata・出力54ファイルも不変
- 通常2026/27 J1の年2026・大会枠1、20クラブ・38節・380試合を公式方式と一覧で確認
- 一覧380行（スコア掲載70、vs表示310）と公式記録詳細1件を取得し、調査原本・metadataを保存
- 不変snapshot、終了判定、IDなし予定と公式IDの対応、訂正差分、idempotency・最新参照の更新設計を記録
- 公式matchの実「試合終了」欄と大会・日付・節・クラブ・得点を照合する専用解析を実装
- 不変snapshot/revision、日程非依存のfixture_key、公式ID対応表、訂正履歴、検証成功後のlatest切替を実装
- 保存済み一覧＋公式証拠2ページからbootstrapを生成。scheduled310・candidate69・completed1、既存Validation通過
- 同一snapshot再importと2回replayでraw7・加工17ファイルの全バイト一致。日程・訂正・欠落・公開失敗を検証
- 既存2015～2025の32成果物＋百年構想リーグ4成果物を隔離再生成し全36件一致。既存92データファイルのSHA不変
- 公式期間一覧の実リンクから対象ページを特定し、未取得69試合の終了欄・カード・得点を既存規則で照合
- 新snapshotで69候補を昇格しscheduled310・candidate0・completed70。全70件が既存Validation通過
- fixture_key/公式ID対応と既存試合値を維持。旧902イベントを保持し、2比較計138のcompletedイベントを追加
- 同一snapshot再import・2回replay、旧bootstrap再処理で履歴と最新参照の不変性を確認。既存113保護ファイルのSHA不変
- `616d345`までの更新基盤・候補69件の終了確認がcommit・push済みで、origin/mainと一致することを確認
- `data/master/teams.csv`に33クラブ・86 alias、名称・年度・slugから独立した固定team_idを登録
- source・原表記・任意の期間による一意解決、未知名エラー、コピーへのID列追加を実装
- 既存4,168試合・予定の8,336参照とcompleted70件を確認。全raw/processed 418ファイルのSHA不変
- 名称マスター専用47件を追加し、既存508件を含む全555件のpytest成功
- `src/features/elo.py`にteam_id単位の最小Elo APIを実装。初期rating=1500、K=20、尺度400
- 90分resultのみ使用し、試合前ratingから期待値を計算して両チームを更新。変更不能な更新前後の値を取得可能
- 専用39件で期待値・勝敗/引分・合計保存・未知ID・入力順の再現性・未来結果のリーク防止を検証。全pytest 594件成功
- 既存11 CSVの3,588試合を31 team_idへ解決し、全登録33 IDを1500から年度リセットなしで更新
- match_date・文字列match_id順、ID単位の同日重複拒否、result更新前のhome_elo / away_elo / elo_diffを実装
- 2024再開試合30700は既存11月22日を使用する制限を文書・テスト化。時系列適用専用33テスト成功
- 同じEloインスタンスで百年構想リーグ200試合を接続。計3,788試合・33 ID、途中リセットなし、90分resultのみ使用
- 百年構想Elo専用26件を含む全pytest 653件成功。既存2015～2025のElo出力・期末ratingの完全一致を確認
- 保存済み2026/27のcompleted70試合を接続。計3,858試合・33 ID、scheduled310／candidate0はElo対象外
- 専用39件で状態除外・継承・非リーク・再現性・原本不変・revision整合性を検証。全pytest 692件成功

## 作業中

2026/27までのElo接続はc6a4edeまでcommit済みで保存済みorigin/mainと一致。開始時の作業ツリーはクリーン。
進行中データはconfirmed-candidates-20260915、予定310・候補0・終了確認済み70の状態を保持する。
既存load_elo_history_with_ongoingの結果を2つのCSVへ保存する出力層・CLIを追加。取得・更新処理は実行していない。
百年構想のPK・延長勝者・playoff tie winnerは従来どおりElo更新に使用しない。
入力raw/processed、既存Elo API・Validation・team masterは未変更。ホーム補正・得点差補正・年度リセットは行わない。
Git add / commit / pushは行わず、未コミットの実装と検証結果を報告して停止する。
その他の特徴量生成・パラメータ調整・モデル学習・予測処理は未実装。

## Git状態（2026-09-17確認）

- 正式リモートorigin: `https://github.com/chisatohojo/J1_League_AI.git`（fetch / push共通）
- 現在のブランチ: `main`、追跡先: `origin/main`
- 今回はネットワーク取得なし。保存済みorigin/mainと比較
- `HEAD` / `origin/main`: `c6a4ede`（2026/27のcompletedへのElo接続まで完了）
- `HEAD...origin/main`: ローカルのみ0件 / リモートのみ0件。同期は不要
- 変更4件: README.md、STATUS.md、CHANGELOG.md、docs/DECISIONS.md
- 新規3件: src/features/elo_export.py、scripts/export_elo.py、tests/test_elo_export.py。ステージ済み変更なし
- HTML原本・metadata・正規化検証CSV・集計JSON・人間レビュー用Markdownは既存設定によりGit対象外で、ローカルに保存
- リモートURLの変更、履歴変更、GitHubへの書き込みは行っていない

## 次にやること

1. Git状態・現在のブランチ・リモートとの差分と、README.md、DEVELOPMENT_GUIDE.md、本ファイルを確認する。
2. `docs/JLEAGUE_2026_27_UPDATE_DESIGN.md` の採用済み終了根拠、再現CLI、latest/revision読取方法を確認する。
3. 候補69件の追加確認は完了。次の新しい結果についても必要な公式終了証拠を選び、新snapshotへ追加する。
   日付経過や数値スコアだけで終了を決めず、未確認行は結果Validationへ渡さない。
4. 次の明示的な取得で日程・得点差分を確認する。未知の中断・延期・取消表記は発見時に調査する。
   自動URL発見・定期実行・詳細だけの訂正監査・百年構想リーグの旧CSV投影は別作業とする。
5. `docs/TEAM_MASTER.md`に従って名称マスターをレビューする。新たな昇格クラブ・aliasは根拠確認後に追加し、既存IDは変更しない。
6. `python -m scripts.export_elo`で試合前Elo履歴・現在ratingを再生成できる。入力の更新・訂正後も保存済み入力から全系列を再計算する。
   スタジアム名称マスターは未実装で、今回の対象外。

百年構想リーグ対応時の完全一致検証には、作業開始前から保存した2015～2025年の32実出力を使用した。
再生成は原本コピーを置いた隔離rootで実施し、退避結果・既存成果物とのバイト一致を確認した。
pytestは人工データと変更前コードによる固定ハッシュで検証し、実データと通信を必要としない。
更新基盤実装時は既存92データファイルのSHAを照合した。候補69件確認時も過去36成果物を隔離再生成して不変を再確認した。
候補69件確認時は開始時120ファイルのうち最新参照・閲覧用コピー7件を除く113件がSHA不変。対応表コピーもバイト一致した。
今回の名称マスター追加では取得・更新処理を実行せず、全raw/processed 418ファイルを開始時のSHAと照合して不変を確認した。

## チーム名称マスター

- データ: `data/master/teams.csv`、33クラブ・86 alias（Data Site略称33＋詳細正式表記20＋公式サイト表記33）
- 実装: `src/collect/teams.py`。team_0001～team_0033を固定し、source・source_name・必要時の試合日で解決
- canonical_nameは表示用。名称・URLのslug・行順からIDを生成せず、未知名は明示的エラー
- 改称・別表記は同じIDへalias追加。期間は公式根拠がある場合だけ設定し、期間重複は拒否
- 対象: 2015～2025の3,588、百年構想200、2026/27の380、計4,168試合・予定。8,336参照すべて一意
- 正式revisionのcompleted70件も検証し、ID追加以外のDataFrame列・値・順序・indexは保持
- 仕様・追加手順・根拠: `docs/TEAM_MASTER.md`。追加通信0、raw/processed・既存Validation・依存は変更なし

## 通常2026/27 J1の更新成果物

- 設計報告: `docs/JLEAGUE_2026_27_UPDATE_DESIGN.md`
- 調査原本: `data/raw/jleague/2026_2027/research/20260914T224804164752Z/` の一覧・詳細34583と各metadata
- 大会: 年2026・大会枠1、原表2026/27・Ｊ１、20クラブ・38節・380試合、2026-08-07～2027-06-06
- 観測: 380行のうち数値スコア70行は公式IDあり、vs表示310行はIDなし。未開催時刻空欄180、会場未定10
- 終了証拠: `data/raw/jleague/2026_27/research/20260915T035921896334Z/` の公式091302・091904とmetadata
- snapshot: `data/raw/jleague/2026_27/snapshots/bootstrap-20260915/`（HTML3・metadata3・manifest1）
- 加工成果物: `data/processed/jleague/2026_27/` のschedule.csv、completed_matches.csv、fixture_identity.csv、change_log.csv、update_summary.json、review.md
- 初回revision: a5f7e4c2e9b53b7860f0f3e727ff212456128f203adae92fc5abd9f42ba80e9b（不変保持）
- 新snapshot: `data/raw/jleague/2026_27/snapshots/confirmed-candidates-20260915/`（HTML72・metadata72・manifest1）
- 採用参照: 同ディレクトリのlatest.json → revisions/9622f4bd6332db056e214b5cb94aed12d2c2d1ec187118b03f3d2d350f3850ec/
- 状態: scheduled310 / candidate0 / completed70。fixture_key380一意・公式ID70一意、予定310はID空
- 初回差分: 前回取得／前回採用の各基準でnew_fixture380・result_candidate70・completed1。全902イベント一意
- 実装: `scripts/update_jleague_ongoing.py`、`src/collect/jleague_ongoing_source.py`、`src/collect/jleague_ongoing.py`
- 再処理: `python -m scripts.update_jleague_ongoing replay data/raw/jleague/2026_27/snapshots/confirmed-candidates-20260915`
- 追加確認: 2比較各completed69イベント、累積1,040イベント一意。ID対応・日程・得点/result等は不変
- 結果Validationはcompleted70件すべて通過（Away22・Draw15・Home33）、第1～7節各10件。定期自動更新は未実施
- 全対象公式URL・取得来歴・検証: `docs/JLEAGUE_2026_27_CANDIDATE_REVIEW.md`

## 共通解析の構成と互換性

- 共通処理: `src/collect/jleague.py`。HTML解析・キャッシュ読取・集計は明示的な年度引数を受け取る。
- 共通CLI: `scripts/inspect_jleague.py --year <年>`。2015～2025年を指定できる。
- 旧 `scripts/inspect_jleague_2015.py` / `inspect_jleague_2016.py` は共通処理を呼ぶ互換入口。
- 2015年はCSV・集計JSON、2016年はCSV・集計JSON・人間レビューを従来と同じ名前・内容で出力。
  2017～2025年もCSV・集計JSON・人間レビューを出力する。
- 2016～2020年・2022～2025年は前年キャッシュと比較する。2021年の比較先は既存出力保護のため2017年を維持。
  自動巡回・ネットワーク取得機能は持たない。
- `SEASON_FORMATS` に公式確認済みのクラブ数とstage内対戦回数を設定し、`SEASON_STAGES` の節数も導出する。
  2015/2016年は18クラブ・1st/2nd各1回、2017～2020年・2022/2023年は18クラブ・full_season2回。
  2021年・2024/2025年は20クラブ・full_season2回。
  年間件数・クラブ別home/away・対戦網羅性・節内の全クラブ1回出場を大会構造に基づいて検証する。
  年度と大会表記が矛盾する入力は拒否し、元の大会名と節番号を保持する。
- 既存のstage、round、match_id等の15列、型、名称、行列順、集計・レビュー形式を維持。
- 全対象年度でHTMLとmetadataを必須とし、要求/最終URL、status、バイト数、SHA、取得日時の存在を照合。
  2015年旧CLIのみmetadata任意だった扱いを統一した。欠落・不一致時は停止し、自動再取得しない。
- 回帰テスト: `tests/test_jleague_common.py`、期待値と出所: `tests/fixtures/jleague_refactor/`。
  期待値は共通化前の `43efdcf` のコードから人工データで作成し、新コードから再生成していない。
- `tests/test_jleague_2021.py` の正常系3テストは2018～2025年の共通parameterized testとし、2024・2025年対応時に6ケース追加。
  CLI比較元のクラブ数・試合数もパラメータ化し、2024→2023（18クラブ）、2025→2024（20クラブ）を検証する。
  2021年の異常系と2017年の `3116b12` 由来固定ハッシュ検証は維持する。
  独立レビューでも旧コードを実行し、3出力のLF/CRLF双方のハッシュ一致を確認した。
- 2024・2025年取得時のData SiteへのGETは各1回、計2回。その再開後・解析・再生成では追加アクセス0回。
  2015～2023年のHTML・metadata18ファイルと26出力はバイト列も不変。

## 2026年J1百年構想リーグ成果物

- 原本・metadata: `data/raw/jleague/2026_hyakunen/`。保存済み14組を独立照合、CLI使用は一覧＋詳細の12組
- 実行: `python -m scripts.inspect_jleague_hyakunen`（オフライン）
- 出力: `data/processed/jleague/2026_hyakunen/` の `matches.csv`（200行48列）、`playoff_ties.csv`（10行18列）、`summary.json`、`review.md`
- 処理: `src/collect/jleague_hyakunen_source.py`、`src/collect/jleague_hyakunen.py`。従来の共通表読取を再利用
- 試験: `tests/test_jleague_hyakunen_source.py`、`tests/test_jleague_hyakunen.py`、`tests/test_inspect_jleague_hyakunen.py`
- 大会方式・列定義・特殊ケース: `docs/JLEAGUE_2026_HYAKUNEN_RESEARCH.md`、`docs/DECISIONS.md`

| 項目 | 結果 |
| --- | --- |
| 件数 | 地域EAST90＋WEST90、PO20、合計200 |
| 大会構造 | 地域各10クラブ・18節各5試合、PO同順位10カード各2戦 |
| 各クラブ | 地域18＋PO2、合計20試合・home10／away10 |
| 期間・会場 | 2026-02-06～06-06、23会場表記 |
| 90分result（Away／Draw／Home） | 65／58／77 |
| 単一試合の結果（Away／Draw／Home） | 85／6／109（地域PK・PO延長を反映） |
| PK／延長 | 地域PK51、PO延長1、PO PK0 |
| PO決着方法 | 勝利数7、得失点差2、延長1 |
| データ品質 | 必須情報欠損・ID/試合重複・同一クラブ対戦・負得点・result矛盾0 |
| ID | 全200件一意、既存2015～2025年3,588 IDと共通0 |

33017町田－名古屋は90分0-0、延長2-1。一覧2-1を90分値へ流用していない。
33015鹿島－神戸は単一試合では鹿島、2戦全体では神戸が勝利する。
POのround、地域のleg、未実施のPK/延長得点などは仕様上nullで、欠損異常とは区別して検証する。

## 2024・2025年調査成果物

- 原本・metadata: `data/raw/jleague/{年}_j1_search.html` と同名 `.metadata.json`
- CSV・集計JSON・人間レビュー: `data/processed/jleague/{年}_matches_probe.csv`、同名 `.summary.json` / `.review.md`
- 再現: `scripts/inspect_jleague.py --year 2024` / `--year 2025`。それぞれ前年キャッシュも必要
- 調査報告・来歴: `docs/JLEAGUE_2024_2025_RESEARCH.md`、`docs/DATA_SOURCES.md`

| 年度 | 大会構造 | 各クラブ年間/home/away | 開催期間 | result 0/1/2 |
| --- | --- | --- | --- | --- |
| 2024 | 20クラブ・full_season・38節・380試合 | 38 / 19 / 19 | 02-23～12-08 | 130 / 104 / 146 |
| 2025 | 同上 | 38 / 19 / 19 | 02-14～12-06 | 115 / 97 / 168 |

各節10試合・全20クラブ各1回、無向190対戦各2回・有向380対戦各1回を自動確認。
全15列欠損・空白、ID/試合/行重複、同一クラブ・負得点・score/result矛盾は0件。既存Validation・CSV往復比較に成功。
独立HTML解析でも両年380行×15列がCSVと完全一致。全11年度のmatch_idは3,588件すべて一意。
2024年は1,013得点・25会場、2025年は911得点・21会場。日付順の節番号逆行は両年9箇所。
2025年のIDは第1～7節70件と第8～38節310件で番号が離れるが、全対戦を網羅し取得漏れはない。
2024年浦和対川崎Ｆ（30700）は後半再開試合。原本どおり11-22・19:00・最終1-1の1試合として保持する。
再開日と当初の試合開始日が異なる点は、将来の時系列処理で別途扱う。今回は日付・列・Validationを変更しない。
全クラブ・全節・会場一覧・先頭5・最後5・seed42の10試合を含む人間レビューを両年生成済み。

## 2022・2023年調査成果物

- 原本・metadata: `data/raw/jleague/{年}_j1_search.html` と同名 `.metadata.json`
- 正規化CSV・集計JSON・人間レビュー: `data/processed/jleague/{年}_matches_probe.csv`、同名 `.summary.json` / `.review.md`
- 再現: `scripts/inspect_jleague.py --year 2022` / `--year 2023`。それぞれ前年キャッシュも必要
- 報告・来歴: `docs/JLEAGUE_2022_2023_RESEARCH.md`、`docs/DATA_SOURCES.md`

| 年度 | 大会構造 | 各クラブ年間/home/away | 開催期間 | result 0/1/2 |
| --- | --- | --- | --- | --- |
| 2022 | 18クラブ・full_season・34節・306試合 | 34 / 17 / 17 | 02-18～11-05 | 87 / 97 / 122 |
| 2023 | 同上 | 34 / 17 / 17 | 02-17～12-03 | 99 / 78 / 129 |

各節9試合・全18クラブ各1回、無向153組各2回・有向306組各1回を自動確認。
全15列の欠損・空白、ID/試合/行重複、同一クラブ・負得点・score/result矛盾は0件。既存Validation・CSV往復比較に成功。
原本からの独立解析でも両年306行×15列がCSVと完全一致。全9年度のmatch_idは2,828件すべて一意。
両年のIDは年内で連続、各22会場。総得点は2022年771、2023年777。
節番号が原本の開催日順で戻る箇所は2022年9・2023年4。実施日・節番号を原本どおり保持する。
放送欄に開催変更等の注記はなく、日程差分の原因は推測しない。年度専用解析の追加は不要だった。
全クラブ・全節・先頭5・最後5・seed42の10試合を含む人間レビューを両年生成済み。

## 2018～2020年調査成果物

- 原本: `data/raw/jleague/{年}_j1_search.html` と同名metadata JSON
- 取得日時・bytes・SHA-256: `docs/DATA_SOURCES.md` と `docs/JLEAGUE_2018_2020_RESEARCH.md` に記録
- 正規化候補: `data/processed/jleague/{年}_matches_probe.csv`（各306行・15列）
- 集計・前年との差分: 同名 `.summary.json`、人間レビュー: 同名 `.review.md`
- 再現処理: `scripts/inspect_jleague.py --year 2018` / `--year 2019` / `--year 2020`
- 報告: `docs/JLEAGUE_2018_2020_RESEARCH.md`

| 年度 | 大会構造 | 各クラブ年間/home/away | 開催期間 | result 0/1/2 |
| --- | --- | --- | --- | --- |
| 2018 | 18クラブ・full_season・34節・306試合 | 34 / 17 / 17 | 02-23～12-01 | 109 / 69 / 128 |
| 2019 | 同上 | 34 / 17 / 17 | 02-22～12-07 | 106 / 72 / 128 |
| 2020 | 同上 | 34 / 17 / 17 | 02-21～12-19 | 120 / 68 / 118 |

各節9試合・全18クラブ各1回、無向153組各2回・有向306組各1回を自動確認。
全年度の欠損・空白・重複・同一チーム・負得点・score/result矛盾は0件、既存Validation通過。
全7年度を合わせても2,216件のmatch_idが一意。原本→CSVの各306行×15列は独立監査でも完全一致した。
2020年のIDは第1節と第2～34節で大きく離れるが、全306試合の網羅性を確認済みで取得漏れではない。
2020年の132日間の開催日間隔・第2/3節18試合の入場者0・ACL日程注記16件等を報告へ記録した。
2018/2019年にも節順と開催日順のずれがあり、原本の実施日・節・表記を維持する共通処理で扱える。
各年の全クラブ・全節・先頭5・最後5・seed42の10試合を含む人間レビューを出力済み。

## 2021年調査成果物

- 原本: `data/raw/jleague/2021_j1_search.html`（432,288 bytes）、同名metadata JSON
- UTC取得日時: `2026-09-13T10:33:29.781495+00:00`（中断前の記録を保持）
- SHA-256: `911725c42e8e7efaa39af9faa0ee1e47517c1115ac620701c822519f22d792ba`
- 正規化候補: `data/processed/jleague/2021_matches_probe.csv`（380行・15列）
- 集計・2017年との差分: `data/processed/jleague/2021_matches_probe.summary.json`
- 人間レビュー: `data/processed/jleague/2021_matches_probe.review.md`
- 再現処理: `scripts/inspect_jleague.py --year 2021`（比較用2017年キャッシュも必要）
- 報告: `docs/JLEAGUE_2021_RESEARCH.md`

2021年は20クラブ・full_season・38節各10試合。各クラブ38試合（home19・away19）、
無向190組各2回・有向380組各1回、全節で全20クラブが各1回出場。
開催期間2021-02-26～12-04。既存Validation・CSV再読込成功。欠損・空白・重複・得点矛盾は0件。
resultはAway Win126・Draw94・Home Win160、総得点920、会場24表記。
スコア訂正（浦和対湘南、ID25153）とhome/away入替（横浜FM対名古屋、ID25147）の注記を原本に保持し、調査報告へ記録した。
原本の確定スコア・対戦方向・実施日・節番号を採用し、節順を日付順の代用にしない。
全20クラブ・全38節・先頭5・末尾5・seed42の10試合を含む人間レビューを出力済み。

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
- 通常2026/27の対象69候補は全件終了確認済みで未解決0。今後新規に現れる結果も公式終了根拠の確認が必要。
- 未知の中断・延期・取消・候補日表記は安全停止する。自動URL発見・定期実行・詳細だけの訂正監査は未対応。
- 未開催310件には公式IDがない。対応表で追跡し、ID再割当や別カードへの移動は自動採用を保留する。
- 複数成果物の整合した読取にはread_latestを使う。閲覧用CSV群はプロセス強制終了時に混在し得るためreplayで復旧する。
- 百年構想リーグのPO PKは実例0で人工fixtureによる検証。抽選・みなし開催の処理、旧CSVへのPO投影は未対応。
- 2021年には公式結果の事後訂正がある。将来の時点別データ再現では訂正前情報と取得時点の確定結果を区別する必要がある。
- 2024年の後半再開試合ではmatch_dateが再開日を示す。当初の開始前予測や休養日数にそのまま使わず、時点の扱いを決める必要がある。
- チーム名は名称マスター経由でID解決可能。新クラブ・未登録aliasの追加は公式根拠を確認して行う。
  canonical_nameは現在の登録表示名で、過去の正式名称履歴や未確認の改称日は再構成しない。スタジアムマスターは未実装。
- 既定入力 `data/raw/matches.csv` は未作成。調査結果はprocessed側の検証CSVに分離した。
- `.venv` が参照するため `.tools/python/` を保持する。再構築方法はREADME冒頭に記載。
- モデル未学習のため精度評価はまだない。
- 現在失敗しているテストや既知の実装不具合はない。

## 最終検証結果

通常2026/27 J1のcompletedへのElo接続（Windows / Python 3.12.14、2026-09-16）:

- 通常3,588＋百年構想200＋completed70＝3,858試合、使用33 ID。新規対象20クラブ、2026-08-07～09-13。
- read_latestが検証したrevision `9622f4bd6332db056e214b5cb94aed12d2c2d1ec187118b03f3d2d350f3850ec` を固定して読み、
  completed_matches.csvとscheduleのcompleted部分集合の一致を確認。閲覧用コピー・rawはElo入力にしない。
- statusで除外してからValidation・ID解決。scheduled310／candidate0は未適用。数値スコアだけで昇格せず、終了根拠列を保持。
- 全20クラブの初登場pre-Eloは百年構想終了時と厳密一致。同じEloRatingsで継続し、match_date→文字列match_id順で各試合を1回処理。
  同一IDの同日completed重複、全期間match_id重複、保存済み観測時点より未来のcompleted日付を拒否する。
- 最終34584（2026-09-13浦和1–2岡山）の更新後は1543.472741／1541.781178。FC東京は1597.745943、全33 ID合計49,500。
  全事前値・最終ratingは独立式と一致（最大差4.55e-13）。数値確認用であり、実順位・予測精度の評価ではない。
- 開始前の2015～2025／百年構想Eloの全列・型・値・期末ratingは完全一致。raw／processed／master全420ファイルのSHA-256・集合不変。
- 専用39件を含む全pytest 692件成功（30.05秒、skipなし）。git diff --check問題なし。
- API: `load_elo_history_with_ongoing()`はhistorical / hyakunen / ongoing各結果のmatches・final_ratingsをメモリ上で返す。
  `build_elo_history_with_ongoing(ordinary, special, schedule, team_master=master, observed_at=保存済みUTC観測日時)`も使用可能。
  既存API・Validation・名称マスターは維持。正式CSV保存、ネットワーク取得、snapshot更新は行わない。

百年構想リーグElo接続（Windows / Python 3.12.14、2026-09-16）:

- 通常3,588＋百年構想200＝3,788試合、使用33 ID。百年構想は地域180／プレーオフ20、2026-02-06～06-06。
- 全20出場クラブの初回試合前値が2025終了時のratingと完全一致。千葉・水戸は未出場時の1500から開始。
- match_date→文字列match_id順。同一ID・同日複数試合と全期間match_id重複は0。更新前のElo列を記録してから90分resultで更新。
- 地域PK51試合は90分引分。延長33017（町田–名古屋、90分0-0）も引分として更新。
  33015（鹿島–神戸、90分2-0）は鹿島勝利で更新し、2戦全体の勝者・神戸は参照しない。
- 最終33022（川崎Ｆ–広島）の更新後は1542.488205／1626.414458。全33 IDの期末合計49,500。
  全3,788試合の事前値・全期末ratingは独立式と一致（丸めによる最大差4.55e-13）。
- 保存済み変更前の2015～2025 DataFrameと2025期末ratingに完全一致。既存データ・マスター・Elo等425保護ファイルのSHA-256不変。
- 専用26件を含む全pytest 653件成功（24.67秒、skipなし）、git diff --check問題なし。手動修正2点も保持。
- API: `load_elo_history_with_hyakunen()`のhistorical / hyakunen各結果にmatchesとfinal_ratingsを保持。
  通常専用load_elo_historyの契約は維持。2026/27・playoff_ties.csvを読み込まず、正式CSV出力なし。

2015～2025通常J1の時系列Elo（Windows / Python 3.12.14、2026-09-16）:

- 11 CSVの3,588試合・ID一意3,588、全7,176チーム名参照を解決。使用31 ID、初期化33 ID。
- 開催日→文字列match_idの昇順。同一IDの同日複数試合は0件。年度をまたいで継続し、未出場2 IDは1500を維持。
- 先頭16803（2015-03-07仙台–山形）は事前1500/1500、事後1510/1490。
- 最終32530（2025-12-06広島–湘南）は事前1626.236872/1426.218495、事後1631.041547/1421.413820。
  全試合の事前値と最終ratingを独立数式と照合（最大差2.27e-13）。最終合計49,500。
- 2024再開試合30700は11月22日順。8～11月の結果を反映するため当初8月24日開始前のEloは再現しない。
- 同じ入力の完全再現、未来・当該結果の非リーク、年度継続、元DataFrame・入力CSV不変を専用33件で検証。
- 全pytest 627件成功（既存594＋専用33、25.43秒、skipなし）。git diff --check問題なし。
- raw / processed / masterと既存Elo・Validation・名称解決コードの423ファイルは開始時のSHA-256と一致。正式CSV保存なし。

Phase 2 最小Elo API（Windows / Python 3.12.14、2026-09-16）:

- 初期rating=1500、K=20、尺度400。90分resultだけを使用し、PK・延長勝者・プレーオフtie winnerは使わない。
- 試合前・試合後の値を分離。未来結果・当該試合結果が過去の試合前ratingへ混入しないことをテスト済み。
- ホーム補正・得点差補正・実データ適用・CSV出力・特徴量生成は未実装。
- 全pytest 594件成功（既存555＋Elo専用39）。git diff --check問題なし。
- 今回の再開ではコードを変更せず、STATUS.md・CHANGELOG.mdだけ更新。commit・pushなし。

チーム名称マスター（Windows / Python 3.12.14、2026-09-16）:

| 確認 | 結果 |
| --- | --- |
| Git | 開始時クリーン、main / origin/mainは616d345、fetch成功、差分0/0 |
| マスター | 33クラブ・86 alias。33原略称の固定ID、source/slugと保存原本の対応を照合 |
| 全試合 | 13入力の4,168行・8,336参照が一意。正式revisionのcompleted70件も別途確認 |
| 改称・alias | 同じIDを維持、期間境界・名前再利用を検証。未知名・曖昧名は明示的エラー |
| 入力不変 | コピーの追加ID列以外は元と完全一致。全raw/processed 418ファイルのSHA不変 |
| 既存年度 | 2015～2025、百年構想、進行中snapshot/revision/対応表/履歴すべて未変更 |
| 全pytest | 555件成功（既存508＋専用47）、失敗・skipなし |
| git diff --check | 問題なし。新規ファイルも空白・競合マーカーを確認 |
| 変更範囲 | 既存文書5変更、新規4件。追加通信0、既存Validation・依存の変更なし。commit・pushなし |

通常2026/27 J1の候補69試合の終了確認（Windows / Python 3.12.14、2026-09-15）:

| 確認 | 結果 |
| --- | --- |
| Git | 開始時クリーン、main / origin/mainはb50dd86、fetch成功、差分0/0 |
| 取得 | 公式一覧1＋対象詳細69 GET、既存ページ再利用、Data Site再取得0 |
| 公式終了根拠 | 既存規則で69/69件一致、未知状態・得点不一致・取得失敗0 |
| 新状態 | scheduled310・candidate0・completed70。全70件Validation通過 |
| 既存値・ID | fixture_key380/公式ID70の対応維持。日程・得点/result等は不変 |
| 履歴 | 902件保持＋138件追加、計1,040件一意。過去snapshot/revision不変 |
| Idempotency | 同一入力再import・2回replayで全raw/加工不変。旧bootstrap再処理でもlatest維持 |
| 回帰 | 過去36成果物を隔離再生成し全件一致。既存113保護ファイルのSHA不変 |
| 全pytest | 508件成功 |
| git diff --check | 問題なし。新規報告の空白・競合マーカーも確認 |
| 変更範囲 | 文書5変更・報告1新規。コード・終了規則・Validation・テスト変更なし。commit・pushなし |

通常2026/27 J1の更新アダプター実装時の検証（Windows / Python 3.12.14、2026-09-15）:

| 確認 | 結果 |
| --- | --- |
| Git | 未コミット変更を保持、main / origin/mainは `f60d28f`、差分0/0 |
| 終了根拠 | 公式matchの終了欄＋大会/日付/節/クラブ/得点照合。skeletonや辞書文字列は除外 |
| 初回状態 | 全380予定、scheduled310・candidate69・completed1、既存Validation成功 |
| ID・差分 | fixture_key380/公式ID70一意。予定変更・候補→完了・A→B→A訂正・欠落/保留復旧を確認 |
| 再実行 | 同じsnapshot再import＋2回replayでraw7・加工17ファイルの全バイト一致 |
| 既存データ | 92ファイルのSHA不変。過去36成果物を隔離再生成して全バイト一致 |
| 全pytest | 全508件成功。うちローカル原本検証1件は原本なし環境ではskip |
| git diff --check | 問題なし。未追跡6ファイルも空白・競合マーカー確認済み |
| 変更範囲 | 文書変更5・新規6。既存Validation/旧年度実装/依存は変更なし。add・commit・pushなし |

2026年J1百年構想リーグ対応（Windows / Python 3.12.14、2026-09-15）:

| 確認 | 結果 |
| --- | --- |
| Git・既存テスト | main / origin/mainは `a1f9f50`、fetch成功・差分0/0、開始時307件成功 |
| 原本 | 保存済み14原本とmetadata全件のSHA・bytes・取得URL・UTC日時を照合、追加通信0 |
| 専用CLI | 200試合・10カードの正規化、大会検証、CSV型往復、4成果物の生成に成功 |
| 独立監査 | 90分・PK・延長・単一試合勝者・2戦全体勝者の件数が実装結果と一致 |
| 旧年度の回帰 | 隔離再生成した32成果物が完全一致。元の22原本/metadata＋32出力もSHA不変 |
| 全pytest | 全439件成功（既存307＋専用132）。失敗・警告なし |
| git diff --check | 問題なし。未追跡ファイルの空白・競合マーカーも別途確認 |
| Git最終状態 | 変更5・未追跡7ファイル、すべて未ステージ。add・commit・pushなし |

最終確認で、正規化済み全200行・PO全10行を独立監査値と照合し、90分／延長／PK・勝者・決着方法が一致した。
専用4成果物は別フォルダーへ再生成してバイト一致を確認。再開前からの原本14組と旧54ファイルも改めて不変を確認した。

以下は各作業完了時点の履歴。

2024・2025年の取得・検証完了時（Windows / Python 3.12.14、2026-09-14）:

| 確認 | 結果 |
| --- | --- |
| 開始時Git・テスト | クリーン、main / origin/mainは `3194dd5`、fetch後差分0/0。既存301件成功 |
| 再開時 | 変更7ファイルと両年6成果物、307件成功済みの実装を保持して文書・最終確認を完了 |
| 両年の共通CLI | 各380試合を正規化し既存Validation・CSV往復比較成功、CSV/JSON/レビュー計6出力を生成 |
| 大会構造・全対戦 | 各20クラブ・38節各10・全クラブ38/home19/away19、190対戦各2回・方向付き380対戦各1回 |
| 品質 | 欠損・空白・重複・同一クラブ・負得点・result矛盾すべて0件 |
| 既存9年度の回帰 | 退避した26出力と一時領域の再生成がバイト単位で完全一致。原本・metadata18ファイルも不変 |
| 新2年度の再現性 | 計6出力も再生成とバイト単位で一致。全11年度のDataFrameも型・全値・行列順・index一致。通信禁止で検証 |
| 独立監査・レビュー | 両年の原本380行×15列とCSV完全一致、コード差分の要修正事項なし |
| `python -m pytest` | 全307件成功（301件＋共通parameterizationの追加6ケース）、失敗・警告なし |
| `git diff --check` | 問題なし |
| Git最終状態 | main / origin/main差分0/0。変更9・新規1ファイル、すべて未ステージ。add・commit・pushなし |

共通処理の本体変更は年度設定と比較先だけ。解析関数・CSV Validation・人工fixture生成処理・固定ハッシュ・依存は維持。

2022・2023年の取得・検証完了時（Windows / Python 3.12.14、2026-09-14）:

| 確認 | 結果 |
| --- | --- |
| 開始時Git・テスト | クリーン、main / origin/mainは `b1c027d`、fetch後も差分0/0。既存295件成功 |
| 両年の共通CLI | 各306試合を正規化し既存Validation・CSV往復比較成功、CSV/JSON/レビュー計6出力を生成 |
| 大会構造・品質 | 各18クラブ・34節各9・全クラブ34/home17/away17、欠損・重複・得点矛盾0 |
| 2015～2021年の回帰 | 退避した20出力と一時領域への再生成がバイト単位で完全一致。原本・metadata14ファイルも不変 |
| 新2年度の再現性 | 計6出力の再生成がバイト単位で一致。全9年度のDataFrameも型・行列順・全値・index一致。ネットワーク禁止で検証 |
| 独立監査・コードレビュー | 両年の原本306行×15列がCSVと完全一致。設定・テスト差分の要修正事項なし |
| `python -m pytest` | 全301件成功（295件＋共通parameterizationの追加6ケース）、失敗・警告なし |
| `git diff --check` | 問題なし |
| Git最終状態 | main / origin/main差分0/0。変更9・新規1ファイル、すべて未ステージ。add・commit・pushなし |

本体は年度形式と比較先の設定追加だけ。既存Validation・解析関数・人工fixture生成処理・固定ハッシュ・依存は維持した。

2018～2020年の取得・検証完了時（Windows / Python 3.12.14、2026-09-14）:

| 確認 | 結果 |
| --- | --- |
| 開始時Git・テスト | クリーン、main / origin/mainは `ec065e7`、fetch後も差分0/0。既存286件成功 |
| 3年度の共通CLI | 各306試合を正規化し既存Validation・CSV往復比較成功、各CSV/JSON/レビュー計9出力を生成 |
| 大会構造・品質 | 各18クラブ・34節各9・全クラブ34/home17/away17、欠損・重複・得点矛盾0 |
| 既存4年度の回帰 | 作業前の11出力と一時領域への再生成がバイト単位で完全一致。元の8原本・metadataも不変 |
| 新3年度の再現性 | 計9出力の再生成がバイト単位で一致。ネットワーク呼出禁止で検証 |
| 独立監査 | 原本からの306行×15列が各年CSVと完全一致。日程・非連続ID・入場者0・ACL注記を確認 |
| `python -m pytest` | 全295件成功（286件＋共通parameterizationの追加9ケース）、失敗・警告なし |
| `git diff --check` | 問題なし |
| Git最終状態 | main / origin/main差分0/0。変更9・新規1ファイル、すべて未ステージ。add・commit・pushなし |

本体は年度形式と比較先の設定追加だけ。年度専用の解析処理を追加せず、Validation・固定ハッシュ・依存は維持した。

2021年対応の完了時（Windows / Python 3.12.14、2026-09-14）:

| 確認 | 結果 |
| --- | --- |
| 再開時Git | 変更5・未追跡3ファイルを保持。main / origin/mainは `3116b12`、fetch後も差分0/0 |
| 2021年原本・CSV | 保存済みHTMLの来歴・SHAを照合し、既存Validation・CSVとのDataFrame完全一致を確認。再開後の通信0回 |
| 2021年の完全性 | 20クラブ、full_season、38節各10試合、各38/home19/away19、全対戦と各節出場を確認 |
| 欠損・重複・得点整合性 | 全15列欠損・空白0、ID/試合/行重複0、同一チーム・負得点・result矛盾0 |
| 2015～2017年の回帰 | 変更前の実出力8ファイルと一時領域の再生成結果がバイト単位で完全一致。DataFrameの型・行列順・indexも一致 |
| 原本・生成物保護 | 旧3年度のHTML・metadata6ファイルは不変。2021年の3出力も再生成結果とバイト単位で一致 |
| `python -m pytest` | 全286件成功（既存253件＋新規33件）、失敗・警告なし |
| 独立レビュー | 原本から380行×15列を独立照合。新規テストと2017年旧コード由来の全6ハッシュも一致、要修正事項なし |
| `git diff --check` | 問題なし |
| Git最終状態 | main / origin/mainの差分0/0。変更7・未追跡3ファイル、すべて未ステージ。add・commit・pushなし |

再開時の共通モジュール・CLI・新規テスト・固定ハッシュは変更せず保持した。
既存CSV Validation・そのテスト・2015/2016年固定ハッシュ・依存パッケージに変更はない。

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
.\.venv\Scripts\python.exe -m scripts.inspect_jleague --year 2018
.\.venv\Scripts\python.exe -m scripts.inspect_jleague --year 2019
.\.venv\Scripts\python.exe -m scripts.inspect_jleague --year 2020
.\.venv\Scripts\python.exe -m scripts.inspect_jleague --year 2021
.\.venv\Scripts\python.exe -m scripts.inspect_jleague --year 2022
.\.venv\Scripts\python.exe -m scripts.inspect_jleague --year 2023
.\.venv\Scripts\python.exe -m scripts.inspect_jleague --year 2024
.\.venv\Scripts\python.exe -m scripts.inspect_jleague --year 2025
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
- [x] 2021年J1の20クラブ制・大会構造検証・Validation・既存3年度の回帰テスト
- [x] 2018～2020年J1のまとめ取得・共通検証・人間レビュー・既存4年度の回帰テスト
- [x] 2022・2023年J1のまとめ取得・共通検証・人間レビュー・2015～2021年の回帰テスト
- [x] 2024・2025年J1のまとめ取得・全対戦網羅性検証・人間レビュー・2015～2023年の回帰テスト
- [x] 2026年J1百年構想リーグの専用解析・90分/延長/PK/単一試合/2戦全体の結果分離・人間レビュー
- [x] 百年構想リーグ対応後の2015～2025年全32成果物のバイト一致検証
- [ ] 確定年度向けの汎用ネットワーク取得アダプター（通常2026/27の明示fetchは実装済み）
- [x] チーム名称マスター・安定team_id・alias/改称・既存全試合の解決検証
- [ ] スタジアム名称マスター（別作業）
- [x] 通常2026/27 J1の識別・大会構造・掲載情報の調査、進行中シーズン更新設計案
- [x] 通常2026/27 J1取得・更新アダプター、公式終了判定根拠、候補69件の確認・昇格
- [x] Phase 2: 最小Elo API・試合前後の分離・リーク防止テスト
- [x] Phase 2: 2015～2025通常J1への時系列Elo適用（メモリ上のみ）
- [x] Phase 2: 百年構想リーグ200試合への90分resultによるElo接続（メモリ上のみ）
- [x] Phase 2: 通常2026/27 J1のcompleted70試合へのElo接続（メモリ上のみ）
- [x] Phase 2: match_elo_history.csv・current_ratings.csvの決定的出力
- [ ] Phase 3: 直近5試合成績
- [ ] Phase 4: Baselineと時系列評価

## 最終確認日

2026-09-17
