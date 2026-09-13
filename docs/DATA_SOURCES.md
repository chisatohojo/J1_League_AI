# Data Sources

## J1試合結果: J.League Data Site（一次データ源として採用）

- データ名: 過去J1リーグ戦試合結果
- 取得元: J.League Data Site（Ｊリーグ公式）。2026-09-11、ユーザー指示により採用
- URL: [2015年J1の日程・結果](https://data.j-league.or.jp/SFMS01/search?competition_frame_ids=1&competition_years=2015&tv_relay_station_name=)、
  [2016年J1の日程・結果](https://data.j-league.or.jp/SFMS01/search?competition_frame_ids=1&competition_years=2016&tv_relay_station_name=)、
  [2017年J1の日程・結果](https://data.j-league.or.jp/SFMS01/search?competition_frame_ids=1&competition_years=2017&tv_relay_station_name=)、
  [2018年J1の日程・結果](https://data.j-league.or.jp/SFMS01/search?competition_frame_ids=1&competition_years=2018&tv_relay_station_name=)、
  [2019年J1の日程・結果](https://data.j-league.or.jp/SFMS01/search?competition_frame_ids=1&competition_years=2019&tv_relay_station_name=)、
  [2020年J1の日程・結果](https://data.j-league.or.jp/SFMS01/search?competition_frame_ids=1&competition_years=2020&tv_relay_station_name=)、
  [2021年J1の日程・結果](https://data.j-league.or.jp/SFMS01/search?competition_frame_ids=1&competition_years=2021&tv_relay_station_name=)
- 対象期間: 2015～2021年の取得・検証を完了。2015/2016年は1st / 2nd各153試合、2017～2020年は通年34節306試合、2021年は通年38節380試合。2022年以降は未取得
- 取得方法: `/SFMS01/search` へ対象の `competition_years`（確認済み2015～2021年）、`competition_frame_ids=1` を指定してGET。
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
  2017～2020年の大会原表記は `Ｊ１`、解析上のstageは `full_season`、roundは通年1～34を保持する。
  2021年も同じ大会表記・stageで、roundは通年1～38を保持する。
  チーム名とスタジアム略称は原表記を保持し、名称統一マスターは未作成。
  試合日は曜日・祝日表記を除去する。節順と実施日順を混同しない。
  今回は通常リーグ戦のみで、チャンピオンシップ等は含まれない。
  `robots.txt` は404で、公開・再配布条件は今回確認していない。
  原本を直接編集せず、既存Git除外設定を維持する

取得結果、HTML構造、正規化案とアクセス回数は [2015年調査報告](JLEAGUE_2015_RESEARCH.md)、
[2016年差分検証](JLEAGUE_2016_RESEARCH.md)、[2017年適用検証](JLEAGUE_2017_RESEARCH.md)、
[2021年大会構造検証](JLEAGUE_2021_RESEARCH.md)、[2018～2020年共通検証](JLEAGUE_2018_2020_RESEARCH.md) を参照。
`python -m scripts.inspect_jleague --year <年>` で、2015～2021年の共通処理を年度指定で実行する。
解析・キャッシュ照合・集計は `src/collect/jleague.py` に置く。
旧 `scripts/inspect_jleague_2015.py` / `inspect_jleague_2016.py` は同じ処理を呼ぶ互換入口。
2016～2020年実行時は、それぞれ前年のキャッシュも比較に使用する。
2021年実行時は確認済みの2017年キャッシュと比較し、`baseline_2017_sha256` を記録する。
2021年の既存出力を維持するため比較対象は変更せず、前年との差分とは表現しない。
検証CSVは `data/processed/jleague/{年}_matches_probe.csv`。
既存Validationを変更せず、2015～2020年は各306件、2021年は380件の受理とCSV再読込を確認した。

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

## チーム名称マスター（未作成）

- データ名: チーム名称統一マスター
- 取得元 / URL: Data Siteのチーム表示を候補として調査。正式名称・別名対応の確定は未実施
- 対象期間: 試合結果データに合わせる
- 取得方法 / 更新方法: 取得元と名称表記の調査後に決定する
- 利用する列: `team_id`, `team_name` を予定
- 注意事項: `data/master/teams.csv` に統一名称を管理し、原本のチーム情報と区別する。

負傷者・出場停止・スタジアムの追加情報は後続フェーズで取得元を調査する。
