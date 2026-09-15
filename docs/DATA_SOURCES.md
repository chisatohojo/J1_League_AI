# Data Sources

## 通常2026/27 J1（更新基盤完成・候補69件の終了確認済み）

- 対象: [Data Siteの日程・結果](https://data.j-league.or.jp/SFMS01/search?competition_frame_ids=1&competition_years=2026&tv_relay_station_name=)。
  `competition_years=2026`、`competition_frame_ids=1`、原表は`2026/27`・`Ｊ１`。
- [公式大会方式](https://www.jleague.jp/outline/j1/): 20クラブ・2回戦総当たり・全38節380試合、
  2026-08-07～2027-06-06。90分引分あり、延長・PKなし。season開始年と実開催日の暦年を区別する。
- 2026-09-15 07:48 JSTの一覧は380行。数値スコアと公式IDがある70行（第1～7節）と、vs表示310行。
  **未開催310行には公式IDがない**。時刻空欄180件、会場`●未定●`10件。未確定情報として保持する。
- 一覧と公式記録詳細34583を各GET1回、計2回取得。以前保存した大会カタログ・検索フォームは再利用。
  原本とmetadataは `data/raw/jleague/2026_2027/research/20260914T224804164752Z/` に保存した。
  UTC日時・取得URL・bytes・SHA-256等の来歴は[更新設計報告](JLEAGUE_2026_27_UPDATE_DESIGN.md)に記録。
- 一覧やSFMS02題名だけでは終了確定としない。補助証拠として
  [公式東京Ｖ－千葉](https://www.jleague.jp/match/j1/2026/091302/)の実DOM内の「試合終了」欄と得点を使用する。
  canonical、大会、日付、節、左右クラブslug、得点をData Siteと照合してcompletedへ進める。
  [未開催の浦和－東京Ｖ](https://www.jleague.jp/match/j1/2026/091904/)には終了欄がないことも確認。
  読み込み待ちskeletonのpost-gameクラスやscript翻訳辞書は終了根拠にならない。
- 上記公式matchの追加GET2件を `data/raw/jleague/2026_27/research/20260915T035921896334Z/` に保存。
  UTC03:59:22と04:00:08取得。各metadataにURL・HTTP200・bytes・SHAを保存し、一覧は再取得していない。
- 更新処理: 不変snapshotを取得ごとに保存し、同じmatch_idの意味内容を比較する。
  IDなし予定は `j1_2026_2027:<home_slug>:<away_slug>` で追跡し、公式ID出現後も対応表を保持する。
  検証済みrevisionだけlatest参照を更新し、過去snapshot・過去訂正前の値は上書きしない。
- 訂正検出の初期対象は一覧に掲載された項目。詳細だけの変更の定期監査は別途設計する。
  応答にはETag・Last-Modifiedがなく、条件付きGETは未採用。
- 初回snapshotは `data/raw/jleague/2026_27/snapshots/bootstrap-20260915/`。
  `data/processed/jleague/2026_27/` にschedule・completed・対応表・change log・summary・reviewを生成した。
  全380予定（20クラブ・38節・各38/home19/away19）、scheduled310・candidate69・completed1。
  初回は34583だけ公式終了証拠と照合し、1-1・result1で既存Validationを通過。残り69件は当時終了未確認。
- `python -m scripts.update_jleague_ongoing replay SNAPSHOT_DIRECTORY` は通信なし。
  明示的な `capture --fetch` で一覧1回、必要な公式matchだけ `--evidence-url` で指定する。自動列挙・定期実行はしない。
- 更新基盤実装の最終再開後は追加アクセス0回。同一snapshotの再import・2回replayでraw7・加工17ファイルの全バイト一致。
  2015～2025の32件と百年構想リーグ4件を別rootで再生成し、全36成果物が一致。既存92データファイルもSHA不変。

### 2026-09-15: 69候補の終了根拠を追加

- [公式期間一覧](https://www.jleague.jp/j1/match/search-list/?enddate=2026-09-13&period=custom&startdate=2026-08-07)を1回取得し、実hrefで対象70ページを特定。
  既存の1終了ページはキャッシュ利用、未取得69ページだけ各1回GET。Data Site一覧・詳細の追加GETは0。
- 既存 `official-game-over-v1` により全69件の終了欄・カード・得点を照合し、scheduled310・candidate0・completed70へ更新。
  70件は既存Validationを通過。fixture_key/公式ID、日付、得点/result、チーム・会場名は変更していない。
- 新規原本・metadataは `data/raw/jleague/2026_27/acquisitions/candidate_completion_20260915/`。
  各URL・取得UTC時刻・SHAと判定を `verification_report.json` に保存。HTTP取得は全件成功、再取得なし。
- 新snapshot `confirmed-candidates-20260915` と新revisionを保存。過去snapshot/revisionと902履歴を保持し、2比較計138のcompletedイベントを追加。
- 同一入力再import・2回replayと旧snapshot再処理で不変性・最新参照維持を確認。過去36成果物の隔離再生成もバイト一致。
- 全対象の公式根拠URL・結果・取得範囲は[候補終了確認報告](JLEAGUE_2026_27_CANDIDATE_REVIEW.md)を参照。

## 2026年J1百年構想リーグ（通常J1とは別大会）

- 取得元: J.League Data Site。[対象一覧](https://data.j-league.or.jp/SFMS01/search?competition_frame_ids=35&competition_years=20261&tv_relay_station_name=)
- 識別: `competition_years=20261`（2026特別）、`competition_frame_ids=35`。
  通常2026/27の`2026`・通常J1の`1`とは区別する。内部大会キーは`j1_hyakunen_2026`。
- 方式: [公式大会実施要項](https://aboutj.jleague.jp/corporate/assets/pdf/regulation/jleague/myjleague_100year_vision_league_match_regulations_revision.pdf)
  に基づくEAST/WEST各10クラブの地域2回戦総当たり180試合と、同順位同士2戦制のプレーオフ20試合。
- 原本: `data/raw/jleague/2026_hyakunen/`。2026-09-14 UTCに一覧1、地域PK詳細1、PO第2戦詳細10、
  大会ID確認JSON1、検索フォーム1の計14応答を保存。各metadataに要求/最終URL、status、UTC日時、Content-Type、bytes、SHA-256を記録。
  大会ID確認JSONには通常2026/27の大会識別子だけが含まれ、通常J1の試合結果は取得していない。
- 2026-09-15の実装・再検証は保存済み原本を再利用し、追加取得0回。詳細の不足やmetadata不整合時は自動取得せず停止。
- 全200試合、20クラブ各20試合（home10／away10）。地域PK51、PO延長1、PO PK0。
  90分結果はAway65／Draw58／Home77。
- 一覧スコアには延長込みの値がある。33017町田－名古屋は表示2-1、90分0-0、延長増分2-1。
  PO第2戦は全詳細の前後半・延長内訳を使い、地域／第1戦は延長なしの公式規則と一覧を照合する。
- 保存モデル: 試合単位の90分得点/result、延長・PKの有無と得点、単一試合の勝者／決着方法に加え、
  2戦全体の勝者／決着方法を別テーブルに保存。POのPKは対戦全体を決める情報として扱う。
  地域のroundとPOのleg、EAST/WEST、放送列内の順位決定枠、原名称・原日付表記・ID・source URLを保持する。
- 再現: `python -m scripts.inspect_jleague_hyakunen`。
  `data/processed/jleague/2026_hyakunen/` に `matches.csv`、`playoff_ties.csv`、`summary.json`、`review.md`を出力する。
- 既存matches.csvとは別の大会検証を使用。既存Validation・2015～2025出力・原本は変更しない。
  PO PKの実データは0件のため、解析と勝者判定は人工fixtureでも検証する。

取得URL・日時・SHA-256の全一覧と列の意味は
[百年構想リーグ調査・実装報告](JLEAGUE_2026_HYAKUNEN_RESEARCH.md)を参照。
原本・加工成果物は既存設定のままGit対象外。

## J1試合結果: J.League Data Site（一次データ源として採用）

- データ名: 過去J1リーグ戦試合結果
- 取得元: J.League Data Site（Ｊリーグ公式）。2026-09-11、ユーザー指示により採用
- URL: [2015年J1の日程・結果](https://data.j-league.or.jp/SFMS01/search?competition_frame_ids=1&competition_years=2015&tv_relay_station_name=)、
  [2016年J1の日程・結果](https://data.j-league.or.jp/SFMS01/search?competition_frame_ids=1&competition_years=2016&tv_relay_station_name=)、
  [2017年J1の日程・結果](https://data.j-league.or.jp/SFMS01/search?competition_frame_ids=1&competition_years=2017&tv_relay_station_name=)、
  [2018年J1の日程・結果](https://data.j-league.or.jp/SFMS01/search?competition_frame_ids=1&competition_years=2018&tv_relay_station_name=)、
  [2019年J1の日程・結果](https://data.j-league.or.jp/SFMS01/search?competition_frame_ids=1&competition_years=2019&tv_relay_station_name=)、
  [2020年J1の日程・結果](https://data.j-league.or.jp/SFMS01/search?competition_frame_ids=1&competition_years=2020&tv_relay_station_name=)、
  [2021年J1の日程・結果](https://data.j-league.or.jp/SFMS01/search?competition_frame_ids=1&competition_years=2021&tv_relay_station_name=)、
  [2022年J1の日程・結果](https://data.j-league.or.jp/SFMS01/search?competition_frame_ids=1&competition_years=2022&tv_relay_station_name=)、
  [2023年J1の日程・結果](https://data.j-league.or.jp/SFMS01/search?competition_frame_ids=1&competition_years=2023&tv_relay_station_name=)、
  [2024年J1の日程・結果](https://data.j-league.or.jp/SFMS01/search?competition_frame_ids=1&competition_years=2024&tv_relay_station_name=)、
  [2025年J1の日程・結果](https://data.j-league.or.jp/SFMS01/search?competition_frame_ids=1&competition_years=2025&tv_relay_station_name=)
- 対象期間: 2015～2025年の取得・検証を完了。2015/2016年は1st / 2nd各153試合、2017～2020年・2022/2023年は通年34節306試合、2021年・2024/2025年は通年38節380試合。通常2026/27は冒頭の調査原本のみ取得、継続更新は未実装
- 取得方法: `/SFMS01/search` へ対象の `competition_years`（確認済み2015～2025年）、`competition_frame_ids=1` を指定してGET。
  各年1ページに年間の全試合が含まれる。原本は `data/raw/jleague/{年}_j1_search.html` に保存
- 更新方法: 取得済み原本とmetadataを再利用する。今回の再解析は通信なし。
  今後の取得器はキャッシュ優先とし、原本の更新・訂正反映方式は本番化時に決定する
- 利用する列: `match_id`, `season`, `round`, `match_date`, `home_team`,
  `away_team`, `stadium`, `home_score`, `away_score`, `result`
- 取得列との対応: 試合詳細リンクの `match_card_id` を `match_id`、シーズンを `season`、
  `第n節第m日` のnを `round`、表示日付を `YYYY-MM-DD` に変換。得点比較から `result` を生成
- 追加保存列: `stage`、`competition`、`round_label`、`kickoff_time`、`source_url`（試合詳細リンク）
- 原本metadata: 要求URL・最終URL・HTTP status・UTC取得日時・Content-Type・バイト数・SHA-256を同名JSONへ保存
- 注意事項: 2ndの節番号は1～17のまま保持し、`stage` で区別する。
  2017～2020年・2022/2023年の大会原表記は `Ｊ１`、解析上のstageは `full_season`、roundは通年1～34を保持する。
  2021年・2024/2025年も同じ大会表記・stageで、roundは通年1～38を保持する。
  チーム名とスタジアム略称は原表記を保持し、名称統一マスターは未作成。
  試合日は曜日・祝日表記を除去する。節順と実施日順を混同しない。
  今回は通常リーグ戦のみで、チャンピオンシップ等は含まれない。
  `robots.txt` は404で、公開・再配布条件は今回確認していない。
  原本を直接編集せず、既存Git除外設定を維持する

取得結果、HTML構造、正規化案とアクセス回数は [2015年調査報告](JLEAGUE_2015_RESEARCH.md)、
[2016年差分検証](JLEAGUE_2016_RESEARCH.md)、[2017年適用検証](JLEAGUE_2017_RESEARCH.md)、
[2021年大会構造検証](JLEAGUE_2021_RESEARCH.md)、[2018～2020年共通検証](JLEAGUE_2018_2020_RESEARCH.md)、
[2022・2023年共通検証](JLEAGUE_2022_2023_RESEARCH.md)、[2024・2025年共通検証](JLEAGUE_2024_2025_RESEARCH.md) を参照。
`python -m scripts.inspect_jleague --year <年>` で、2015～2025年の共通処理を年度指定で実行する。
解析・キャッシュ照合・集計は `src/collect/jleague.py` に置く。
旧 `scripts/inspect_jleague_2015.py` / `inspect_jleague_2016.py` は同じ処理を呼ぶ互換入口。
2016～2020年・2022～2025年実行時は、それぞれ前年のキャッシュも比較に使用する。
2021年実行時は確認済みの2017年キャッシュと比較し、`baseline_2017_sha256` を記録する。
2021年の既存出力を維持するため比較対象は変更せず、前年との差分とは表現しない。
検証CSVは `data/processed/jleague/{年}_matches_probe.csv`。
既存Validationを変更せず、2015～2020年・2022/2023年は各306件、2021年・2024/2025年は各380件の受理とCSV再読込を確認した。

2016年の取得日時は `2026-09-11T09:06:09.249866+00:00`、385,420 bytes。
SHA-256は `e39d283c47667eb5f337b7d950c1da3c1a55f8ea7e76fc7a8827d3bd9d21472c`。
取得時はData SiteへGET 1回、2026-09-12の再開後は両年のキャッシュだけを使用して通信0回。
2016年は2016-02-27～11-03、18クラブ、各クラブ34試合（ホーム17・アウェイ17）。
共通15クラブの表記とstage/round構造は2015年と同じで、参加3クラブと会場表記の差分を記録した。
名称の独自変換は行っていない。各年のキャッシュの要求URL・最終URL・status・バイト数・SHAを照合し、
取得日時の存在を確認する。キャッシュ不備時に自動再取得しない。複数年取得器は未実装。

2026-09-13の共通化で、両年ともHTMLとmetadataの組を必須に統一した。
2015年旧CLIのみmetadata任意だったが、来歴を照合できない場合は共通読取で停止する。
取得元・対象年・原本・出力形式・名称表記・共通CSV Validationに変更はない。
両年のCSV・集計JSONと2016年レビューの計5ファイルが、共通化前の保存結果とバイト単位で一致した。

2017年の取得日時は `2026-09-13T03:27:33.163161+00:00`、368,692 bytes。
SHA-256は `1a70a85456082b68c9802af7070d560bf5172e88ac4f361c6d72749f02c751ec`。
初回GETは1回、中断からの再開後は取得済みキャッシュのみ使用し追加アクセス0回。
1ステージ制への変更は [Ｊリーグ公式の大会方式発表](https://www.jleague.jp/news/article/7829/)で確認した。
結果表の11列・IDリンク構造は2015/2016年と同じ。開催日は2017-02-25～12-02。
原表には第13節のACLに伴う開催日と、第22節の浦和の日程について注記があり、本文は原本に保持する。
2017年対応後も2015/2016年の原本・metadata・既存5出力はバイト単位で不変。

2021年の取得日時は `2026-09-13T10:33:29.781495+00:00`、432,288 bytes。
SHA-256は `911725c42e8e7efaa39af9faa0ee1e47517c1115ac620701c822519f22d792ba`。
キャッシュ不存在を確認して検索結果をGET 1回取得し、その後の正規化・検証・再実行は通信0回。
大会方式は [2021年の公式発表](https://www.jleague.jp/news/article/18914/)で確認した。
20クラブの年間2回戦総当たりから38節・各10試合・380試合を導出し、実データと一致することを確認した。
開催期間は2021-02-26～12-04、各クラブ38試合（home19・away19）。表の11列・IDリンク構造は既存3年度と同じ。
原本の名前・実施日・節番号・行順を保持する。試合数等の固定条件は調査用の大会構造設定から計算し、
共通CSV Validationは変更していない。2015～2017年の原本・metadata6ファイルと既存8出力はバイト単位で不変。
2026-09-14の再開後も取得済みキャッシュだけを使い、追加アクセス0回で最終検証した。
スコアの事後訂正とhome/away入替の注記を原本・2021年調査報告に保持し、現在の公式結果セルを採用している。

2026-09-14（日本時間）、2018～2020年を各1回のGET、計3回で取得した。UTC取得日時は以下のとおり。
各原本はHTTP 200、`text/html;charset=UTF-8`。要求URL・最終URLは上記の対象年度URLと同一。

| 年度 | UTC取得日時 | bytes | SHA-256 |
| --- | --- | --- | --- |
| 2018 | `2026-09-13T22:14:31.176346+00:00` | 368,317 | `8dd507483091cec030d00489ac52cde22df41204e6b901532195b1f58f46d6d7` |
| 2019 | `2026-09-13T22:14:33.542133+00:00` | 367,781 | `00af9317a662e0dc674f9571561a48b5a52b796334ef670af1e84ecd59bd32cf` |
| 2020 | `2026-09-13T22:14:35.907091+00:00` | 369,393 | `5c2cd9e3c3b1144c4745f2d73b2eb8f6013f1973cbf92fa0351f8435a6716414` |

3年度とも同一の検索結果表・11列で、年間18クラブ・34節・306試合を既存共通処理で検証した。
年度設定と比較年度だけを追加し、HTML解析・キャッシュ照合・CSV Validationの処理は変更していない。
各年度のCSV・集計JSON・レビューを生成。取得後の解析・再生成は通信0回。
2015/2016/2017/2021年の既存11出力とHTML・metadata8ファイルはバイト単位で不変。
2020年の実施日・無観客の入場者数0・ACL日程注記などは原本を保持し、差分報告へ記録する。
今回も名称の独自正規化は行っていない。複数年度を巡回する自動取得アダプターは未実装。

2026-09-14（日本時間）、2022・2023年の未保存を確認し、各GET 1回、計2回で原本を取得した。
全件HTTP 200、`text/html;charset=UTF-8`。要求URL・最終URLは上記の対象年度URLと同一。
原本を応答バイト列のまま保存し、各 `.metadata.json` に以下の来歴を記録した。

| 年度 | UTC取得日時 | bytes | SHA-256 |
| --- | --- | --- | --- |
| 2022 | `2026-09-14T03:56:03.106195+00:00` | 367,492 | `0eaca2d845798ff0ebd1630aae17765464793a989e19f7c69c2f4331ce4fe4a6` |
| 2023 | `2026-09-14T03:56:05.470906+00:00` | 368,119 | `e0c585a2a132c6897a286924b4569e68627e5c24ec5f973c0c13aaf3f801b1ce` |

公式の [2022年大会方式](https://www.jleague.jp/news/article/21360/) と
[2023年大会方式](https://www.jleague.jp/news/article/24237/?mode=pc)により、両年18クラブ・年間2回戦総当たりを確認。
34節・各9試合・年間306試合・各クラブ34/home17/away17を既存共通処理で自動検証した。
2022年は02-18～11-05、2023年は02-17～12-03。欠損・重複・得点矛盾0件で既存Validation通過。
表の11列・IDリンク構造は既存年度と共通で、年度形式と比較先の設定だけを追加した。
比較先は2022年→2021年、2023年→2022年。2021年の比較先2017年は保持する。
両年のCSV・集計JSON・人間レビューを生成し、取得後の解析・回帰検証は通信0回。
2015～2021年の既存20出力とHTML・metadata14ファイルはバイト単位で不変。
日程・開始時刻・会場の差分は原表記を保持して調査報告へ記録し、独自補正や専用解析は追加していない。
2024年以降は取得していない。

2026-09-14（日本時間）、2024・2025年の未保存を確認し、年度一覧を各GET 1回、計2回で取得した。
HTTP 200、`text/html;charset=UTF-8`、要求URL・最終URLは上記の年度URLと同一。
応答バイト列をそのままHTMLに保存し、同名 `.metadata.json` に来歴を記録した。

| 年度 | UTC取得日時 | bytes | SHA-256 |
| --- | --- | --- | --- |
| 2024 | `2026-09-14T04:38:33.694939+00:00` | 432,597 | `b2d76c5f2a10828b37e7bf1f0334d6382007832fe2135ec4cf0955fbe56c4af6` |
| 2025 | `2026-09-14T04:38:36.028921+00:00` | 433,011 | `c04b32fef0547fa10e73a527bd6588c2c8687209ee399f22e8458f4006cee732` |

公式の [2024年大会方式変更](https://www.jleague.jp/news/article/26789/) と
[2025年大会方式](https://www.jleague.jp/news/article/29445/)で20クラブ・ホーム＆アウェイ2回戦総当たりを確認。
クラブ数と対戦回数から38節・各10試合・年間380試合・各クラブ38/home19/away19を導出し、原本と照合した。
無向190カード各2試合、有向380カード各1試合で全対戦を網羅。欠損・重複・得点矛盾0件、既存Validation通過。
2024年は02-23～12-08、2025年は02-14～12-06。各CSV・集計JSON・人間レビューを生成済み。
11列・IDリンク・Ｊ１表記は既存と同じ。年度設定と比較先2024→2023・2025→2024だけを追加した。
原本の実施日・節・ID・チーム/会場表記を保持し、日程やIDの非連続性は調査報告へ記録する。
2024年浦和対川崎Ｆ（ID30700）は、[公式発表](https://www.jleague.jp/news/article/28819/)で後半再開試合と確認した。
原本のmatch_dateは再開日の11-22、K/O19:00、最終1-1。8月の当初開始日へ書き換えず、1試合として保存する。
このCSVだけでは当初開始・中止・再開の各時点を表現できないため、将来の時系列特徴量では別途扱いを決める。
取得後はキャッシュだけを使い追加通信0回。2015～2023年の既存26出力と原本・metadata18ファイルはバイト単位で不変。
2026年の取得や、自動取得アダプターの追加は行っていない。

## チーム名称マスター（未作成）

- データ名: チーム名称統一マスター
- 取得元 / URL: Data Siteのチーム表示を候補として調査。正式名称・別名対応の確定は未実施
- 対象期間: 試合結果データに合わせる
- 取得方法 / 更新方法: 取得元と名称表記の調査後に決定する
- 利用する列: `team_id`, `team_name` を予定
- 注意事項: `data/master/teams.csv` に統一名称を管理し、原本のチーム情報と区別する。

負傷者・出場停止・スタジアムの追加情報は後続フェーズで取得元を調査する。
