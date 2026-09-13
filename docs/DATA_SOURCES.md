# Data Sources

## J1試合結果: J.League Data Site（一次データ源として採用）

- データ名: 過去J1リーグ戦試合結果
- 取得元: J.League Data Site（Ｊリーグ公式）。2026-09-11、ユーザー指示により採用
- URL: [2015年J1の日程・結果](https://data.j-league.or.jp/SFMS01/search?competition_frame_ids=1&competition_years=2015&tv_relay_station_name=)、
  [2016年J1の日程・結果](https://data.j-league.or.jp/SFMS01/search?competition_frame_ids=1&competition_years=2016&tv_relay_station_name=)、
  [2017年J1の日程・結果](https://data.j-league.or.jp/SFMS01/search?competition_frame_ids=1&competition_years=2017&tv_relay_station_name=)
- 対象期間: 2015～2017年の取得・検証を完了。2015/2016年は1st / 2nd各153試合、2017年は通年34節306試合。2018年以降は未取得
- 取得方法: `/SFMS01/search` へ対象の `competition_years`（2015・2016・2017）、`competition_frame_ids=1` を指定してGET。
  各年1ページに年間306試合が含まれる。原本は `data/raw/jleague/{年}_j1_search.html` に保存
- 更新方法: 取得済み原本とmetadataを再利用する。今回の再解析は通信なし。
  今後の取得器はキャッシュ優先とし、原本の更新・訂正反映方式は本番化時に決定する
- 利用する列: `match_id`, `season`, `round`, `match_date`, `home_team`,
  `away_team`, `stadium`, `home_score`, `away_score`, `result`
- 取得列との対応: 試合詳細リンクの `match_card_id` を `match_id`、シーズンを `season`、
  `第n節第m日` のnを `round`、表示日付を `YYYY-MM-DD` に変換。得点比較から `result` を生成
- 追加保存列: `stage`、`competition`、`round_label`、`kickoff_time`、`source_url`（試合詳細リンク）
- 原本metadata: 要求URL・最終URL・HTTP status・UTC取得日時・Content-Type・バイト数・SHA-256を同名JSONへ保存
- 注意事項: 2ndの節番号は1～17のまま保持し、`stage` で区別する。
  2017年の大会原表記は `Ｊ１`、解析上のstageは `full_season`、roundは通年1～34を保持する。
  チーム名とスタジアム略称は原表記を保持し、名称統一マスターは未作成。
  試合日は曜日・祝日表記を除去する。節順と実施日順を混同しない。
  今回は通常リーグ戦のみで、チャンピオンシップ等は含まれない。
  `robots.txt` は404で、公開・再配布条件は今回確認していない。
  原本を直接編集せず、既存Git除外設定を維持する

取得結果、HTML構造、正規化案とアクセス回数は [2015年調査報告](JLEAGUE_2015_RESEARCH.md)、
[2016年差分検証](JLEAGUE_2016_RESEARCH.md)、[2017年適用検証](JLEAGUE_2017_RESEARCH.md) を参照。
`python -m scripts.inspect_jleague --year 2015` / `--year 2016` / `--year 2017` で、共通処理を年度指定で実行する。
解析・キャッシュ照合・集計は `src/collect/jleague.py` に置く。
旧 `scripts/inspect_jleague_2015.py` / `inspect_jleague_2016.py` は同じ処理を呼ぶ互換入口。
2016年実行時は2015年、2017年実行時は2016年のキャッシュも比較に使用する。
検証CSVは `data/processed/jleague/{年}_matches_probe.csv`。
全対象年で既存Validationを変更せず各306件の受理とCSV再読込を確認した。

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

## チーム名称マスター（未作成）

- データ名: チーム名称統一マスター
- 取得元 / URL: Data Siteのチーム表示を候補として調査。正式名称・別名対応の確定は未実施
- 対象期間: 試合結果データに合わせる
- 取得方法 / 更新方法: 取得元と名称表記の調査後に決定する
- 利用する列: `team_id`, `team_name` を予定
- 注意事項: `data/master/teams.csv` に統一名称を管理し、原本のチーム情報と区別する。

負傷者・出場停止・スタジアムの追加情報は後続フェーズで取得元を調査する。
