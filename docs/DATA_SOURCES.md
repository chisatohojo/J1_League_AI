# Data Sources

## J1試合結果: J.League Data Site（一次データ源として採用）

- データ名: 過去J1リーグ戦試合結果
- 取得元: J.League Data Site（Ｊリーグ公式）。2026-09-11、ユーザー指示により採用
- URL: [2015年J1の日程・結果](https://data.j-league.or.jp/SFMS01/search?competition_frame_ids=1&competition_years=2015&tv_relay_station_name=)、
  [2016年J1の日程・結果](https://data.j-league.or.jp/SFMS01/search?competition_frame_ids=1&competition_years=2016&tv_relay_station_name=)
- 対象期間: 2015年・2016年の取得・検証を完了。両年とも1st / 2nd各153試合、年間306試合。2017年以降は未取得
- 取得方法: `/SFMS01/search` へ `competition_years=2015` または `2016`、`competition_frame_ids=1` を指定してGET。
  各年1ページに両ステージが含まれる。原本は `data/raw/jleague/{年}_j1_search.html` に保存
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

取得結果、HTML構造、正規化案とアクセス回数は [2015年調査報告](JLEAGUE_2015_RESEARCH.md)、
[2016年差分検証](JLEAGUE_2016_RESEARCH.md) を参照。
`scripts/inspect_jleague_2015.py` は2015年、`scripts/inspect_jleague_2016.py` は2016年と2015年の比較をオフラインで実行する。
検証CSVは `data/processed/jleague/{年}_matches_probe.csv`。
両年とも既存Validationを変更せず全306件の受理とCSV再読込を確認した。

2016年の取得日時は `2026-09-11T09:06:09.249866+00:00`、385,420 bytes。
SHA-256は `e39d283c47667eb5f337b7d950c1da3c1a55f8ea7e76fc7a8827d3bd9d21472c`。
取得時はData SiteへGET 1回、2026-09-12の再開後は両年のキャッシュだけを使用して通信0回。
2016年は2016-02-27～11-03、18クラブ、各クラブ34試合（ホーム17・アウェイ17）。
共通15クラブの表記とstage/round構造は2015年と同じで、参加3クラブと会場表記の差分を記録した。
名称の独自変換は行っていない。各年のキャッシュの要求URL・最終URL・status・バイト数・SHAを照合し、
取得日時の存在を確認する。キャッシュ不備時に自動再取得しない。複数年取得器は未実装。

## チーム名称マスター（未作成）

- データ名: チーム名称統一マスター
- 取得元 / URL: Data Siteのチーム表示を候補として調査。正式名称・別名対応の確定は未実施
- 対象期間: 試合結果データに合わせる
- 取得方法 / 更新方法: 取得元と名称表記の調査後に決定する
- 利用する列: `team_id`, `team_name` を予定
- 注意事項: `data/master/teams.csv` に統一名称を管理し、原本のチーム情報と区別する。

負傷者・出場停止・スタジアムの追加情報は後続フェーズで取得元を調査する。
