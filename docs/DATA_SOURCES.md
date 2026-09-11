# Data Sources

## J1試合結果: J.League Data Site（一次データ源として採用）

- データ名: 過去J1リーグ戦試合結果
- 取得元: J.League Data Site（Ｊリーグ公式）。2026-09-11、ユーザー指示により採用
- URL: [2015年J1の日程・結果](https://data.j-league.or.jp/SFMS01/search?competition_frame_ids=1&competition_years=2015&tv_relay_station_name=)
- 対象期間: 今回の取得・検証は2015年のみ。1st / 2nd各153試合、計306試合。2016年以降は未取得
- 取得方法: `/SFMS01/search` へ `competition_years=2015`、`competition_frame_ids=1` を指定してGET。
  検索結果HTML 1ページに両ステージが含まれる。原本は `data/raw/jleague/2015_j1_search.html` に保存
- 更新方法: 取得済み原本とmetadataを再利用する。今回の再解析は通信なし。
  今後の取得器はキャッシュ優先とし、原本の更新・訂正反映方式は本番化時に決定する
- 利用する列: `match_id`, `season`, `round`, `match_date`, `home_team`,
  `away_team`, `stadium`, `home_score`, `away_score`, `result`
- 取得列との対応: 試合詳細リンクの `match_card_id` を `match_id`、シーズンを `season`、
  `第n節第m日` のnを `round`、表示日付を `YYYY-MM-DD` に変換。得点比較から `result` を生成
- 追加保存列: `stage`、`competition`、`round_label`、`kickoff_time`、`source_url`（試合詳細リンク）
- 原本metadata: 要求URL・最終URL・HTTP status・UTC取得日時・Content-Type・バイト数・SHA-256を同名JSONへ保存
- 注意事項: 2ndの節番号は1～17のまま保持し、`stage` で区別する。
  チーム名とスタジアム略称は原表記を保持し、名称統一マスターは未作成。
  試合日は曜日・祝日表記を除去する。節順と実施日順を混同しない。
  今回は通常リーグ戦のみで、チャンピオンシップ等は含まれない。
  `robots.txt` は404で、公開・再配布条件は今回確認していない。
  原本を直接編集せず、既存Git除外設定を維持する

取得結果、HTML構造、正規化案とアクセス回数は [2015年調査報告](JLEAGUE_2015_RESEARCH.md) を参照。
`scripts/inspect_jleague_2015.py` で保存原本をオフライン解析できる。
検証CSVは `data/processed/jleague/2015_matches_probe.csv`。
既存Validationを変更せず全306件の受理とCSV再読込を確認した。

## チーム名称マスター（未作成）

- データ名: チーム名称統一マスター
- 取得元 / URL: Data Siteのチーム表示を候補として調査。正式名称・別名対応の確定は未実施
- 対象期間: 試合結果データに合わせる
- 取得方法 / 更新方法: 取得元と名称表記の調査後に決定する
- 利用する列: `team_id`, `team_name` を予定
- 注意事項: `data/master/teams.csv` に統一名称を管理し、原本のチーム情報と区別する。

負傷者・出場停止・スタジアムの追加情報は後続フェーズで取得元を調査する。
