# 2026/27 J1: 候補69試合の公式終了確認

確認日: 2026-09-15（日本時間）。更新基盤 `b50dd86` の終了判定・Validation・ID規則を変更せず実施。

## 結果

| 状態 | 処理前 | 処理後 |
| --- | ---: | ---: |
| scheduled | 310 | 310 |
| candidate | 69 | 0 |
| completed | 1 | 70 |

69候補すべてで、公式matchページの実「試合終了」欄とData Siteの大会・日付・節・左右クラブ・得点が一致した。
既存の `official-game-over-v1` をそのまま使用し、数値スコアだけで昇格した試合はない。
終了確認済み70行は既存ValidationとCSV再読込を通過。結果はAway22・Draw15・Home33、第1～7節各10試合。
日程・得点・result・クラブ・会場・公式IDなどの既存値は変更せず、状態と終了証拠だけを追加した。

## 取得とキャッシュ

- 保存済み公式ページを先に棚卸し。34583の終了根拠と未開催091904のページは再取得していない。
- 公式日程検索の指定期間一覧を1回取得し、実hrefから対象J1の70リンクを抽出した。URL連番は推測していない。
- 一覧のDOMと公式クラブ選択肢による独立監査でも、日付・節・左右クラブ・得点は既存70カードと一致した。
  一覧には他大会25試合のリンクもあったため、対象J1だけに限定した。
- 69の未取得試合ページだけ各1回取得。既取得1終了ページはキャッシュ再利用。Data Site一覧・詳細は追加取得0回。
- 新規GETは計70回（URL確認一覧1＋対象詳細69）。逐次取得・1秒間隔・自動再試行なし、取得失敗0件。
- 一覧の終了表示だけでは昇格せず、全対象に既存の公式match詳細解析を適用した。

[取得した公式日程一覧](https://www.jleague.jp/j1/match/search-list/?enddate=2026-09-13&period=custom&startdate=2026-08-07)

公式URL発見用一覧:
`data/raw/jleague/2026_27/research/candidate_completion_20260915/official_fixture_index.html` とmetadata。
SHA-256: `9869843f51032787c97088f161b73dbed55fccc4a9839eaf37ba9a02ef35579c`。

新規公式match原本・metadata:
`data/raw/jleague/2026_27/acquisitions/candidate_completion_20260915/official_match_*.html` と同名metadata。
対象69件のUTC取得範囲: `2026-09-15T10:21:53.505710+00:00` ～ `2026-09-15T10:23:54.019228+00:00`。
全要求URL・最終URL・HTTP200・UTC時刻・bytes・SHA-256と判定結果を同フォルダーの `verification_report.json` に保存。
取得後は再処理も含め通信していない。

## Snapshot・履歴・再処理

- 新snapshot: `data/raw/jleague/2026_27/snapshots/confirmed-candidates-20260915/`
- 新revision: `data/processed/jleague/2026_27/revisions/9622f4bd6332db056e214b5cb94aed12d2c2d1ec187118b03f3d2d350f3850ec/`
- 保存済み一覧と旧証拠2ページ、新規証拠69ページを入力として固定。HTML72・metadata72・manifest1の145ファイル。
- Data Site一覧観測日時は引き続き `2026-09-14T22:48:04.164752+00:00`。証拠を含む最終観測は `2026-09-15T10:23:54.019228+00:00`。
  今回は候補の終了根拠を追加した更新であり、日程一覧を新たに取得したとは扱わない。
- schedule.csv・completed_matches.csv・change_log.csv・fixture_identity.csv・update_summary.json・review.mdを出力。
- fixture_key380件・公式match_id70件の対応を維持。fixture_identity.csv自体もバイト一致。
- 前回取得／前回採用の各基準で `completed` 69件だけを追加。新規試合・日程変更・得点訂正・欠落は0件。
- 元の902イベントをbefore/after込みで保持し、今回138イベントを追加。計1,040件でevent_idは全件一意。
- 同じsnapshotを再importし2回replayしても、全rawと加工ファイルはバイト一致。
- 旧bootstrapをreplayしても旧snapshot/revisionは不変で、新しいlatestが維持された。
- 開始時120ファイルのうち更新を許す最新参照・閲覧用コピー7件を除く113件はSHA不変。対応表コピーも実際は不変。

通信なしで再処理:

```powershell
.\.venv\Scripts\python.exe -m scripts.update_jleague_ongoing replay `
  data/raw/jleague/2026_27/snapshots/confirmed-candidates-20260915
```

## 今回completedへ昇格した試合

各IDのリンクは保存・照合した公式ページ。既存completedの34583はこの69件に含めない。

| match_id / 公式根拠 | 開催日 | 節 | home | score | away |
| --- | --- | ---: | --- | --- | --- |
| [34517](https://www.jleague.jp/match/j1/2026/080701/) | 2026-08-07 | 1 | 横浜FM | 3-4 | 鹿島 |
| [34518](https://www.jleague.jp/match/j1/2026/080702/) | 2026-08-07 | 1 | Ｇ大阪 | 4-3 | 浦和 |
| [34519](https://www.jleague.jp/match/j1/2026/080801/) | 2026-08-08 | 1 | 柏 | 2-1 | 水戸 |
| [34520](https://www.jleague.jp/match/j1/2026/080802/) | 2026-08-08 | 1 | FC東京 | 1-5 | 町田 |
| [34521](https://www.jleague.jp/match/j1/2026/080803/) | 2026-08-08 | 1 | 名古屋 | 0-1 | 清水 |
| [34522](https://www.jleague.jp/match/j1/2026/080804/) | 2026-08-08 | 1 | Ｃ大阪 | 2-1 | 岡山 |
| [34523](https://www.jleague.jp/match/j1/2026/080805/) | 2026-08-08 | 1 | 福岡 | 0-1 | 神戸 |
| [34524](https://www.jleague.jp/match/j1/2026/080806/) | 2026-08-08 | 1 | 広島 | 3-0 | 千葉 |
| [34525](https://www.jleague.jp/match/j1/2026/080901/) | 2026-08-09 | 1 | 東京Ｖ | 1-1 | 川崎Ｆ |
| [34526](https://www.jleague.jp/match/j1/2026/080902/) | 2026-08-09 | 1 | 長崎 | 2-1 | 京都 |
| [34527](https://www.jleague.jp/match/j1/2026/081401/) | 2026-08-14 | 2 | 東京Ｖ | 1-3 | 柏 |
| [34528](https://www.jleague.jp/match/j1/2026/081501/) | 2026-08-15 | 2 | 鹿島 | 2-1 | 名古屋 |
| [34529](https://www.jleague.jp/match/j1/2026/081502/) | 2026-08-15 | 2 | 水戸 | 1-1 | Ｇ大阪 |
| [34530](https://www.jleague.jp/match/j1/2026/081503/) | 2026-08-15 | 2 | 清水 | 0-1 | 横浜FM |
| [34531](https://www.jleague.jp/match/j1/2026/081504/) | 2026-08-15 | 2 | 岡山 | 1-0 | 長崎 |
| [34532](https://www.jleague.jp/match/j1/2026/081505/) | 2026-08-15 | 2 | 浦和 | 1-4 | 広島 |
| [34533](https://www.jleague.jp/match/j1/2026/081506/) | 2026-08-15 | 2 | 千葉 | 0-4 | 町田 |
| [34534](https://www.jleague.jp/match/j1/2026/081507/) | 2026-08-15 | 2 | 川崎Ｆ | 2-2 | 京都 |
| [34535](https://www.jleague.jp/match/j1/2026/081508/) | 2026-08-15 | 2 | 神戸 | 2-2 | FC東京 |
| [34536](https://www.jleague.jp/match/j1/2026/081509/) | 2026-08-15 | 2 | 福岡 | 3-0 | Ｃ大阪 |
| [34537](https://www.jleague.jp/match/j1/2026/082102/) | 2026-08-21 | 3 | 柏 | 4-2 | 長崎 |
| [34538](https://www.jleague.jp/match/j1/2026/082101/) | 2026-08-21 | 3 | FC東京 | 2-0 | 千葉 |
| [34539](https://www.jleague.jp/match/j1/2026/082201/) | 2026-08-22 | 3 | 鹿島 | 3-2 | 福岡 |
| [34540](https://www.jleague.jp/match/j1/2026/082202/) | 2026-08-22 | 3 | 岡山 | 0-0 | 東京Ｖ |
| [34541](https://www.jleague.jp/match/j1/2026/082203/) | 2026-08-22 | 3 | 名古屋 | 3-1 | Ｇ大阪 |
| [34542](https://www.jleague.jp/match/j1/2026/082204/) | 2026-08-22 | 3 | 京都 | 1-3 | 水戸 |
| [34543](https://www.jleague.jp/match/j1/2026/082205/) | 2026-08-22 | 3 | Ｃ大阪 | 1-0 | 清水 |
| [34544](https://www.jleague.jp/match/j1/2026/082206/) | 2026-08-22 | 3 | 広島 | 1-1 | 川崎Ｆ |
| [34545](https://www.jleague.jp/match/j1/2026/082207/) | 2026-08-22 | 3 | 横浜FM | 1-0 | 神戸 |
| [34546](https://www.jleague.jp/match/j1/2026/082301/) | 2026-08-23 | 3 | 町田 | 3-1 | 浦和 |
| [34547](https://www.jleague.jp/match/j1/2026/082901/) | 2026-08-29 | 4 | 水戸 | 1-1 | 町田 |
| [34548](https://www.jleague.jp/match/j1/2026/082902/) | 2026-08-29 | 4 | Ｇ大阪 | 0-0 | 広島 |
| [34549](https://www.jleague.jp/match/j1/2026/082903/) | 2026-08-29 | 4 | 清水 | 0-1 | 柏 |
| [34550](https://www.jleague.jp/match/j1/2026/082904/) | 2026-08-29 | 4 | 長崎 | 0-3 | FC東京 |
| [34551](https://www.jleague.jp/match/j1/2026/082905/) | 2026-08-29 | 4 | 浦和 | 3-2 | 横浜FM |
| [34552](https://www.jleague.jp/match/j1/2026/082906/) | 2026-08-29 | 4 | 東京Ｖ | 0-2 | 鹿島 |
| [34553](https://www.jleague.jp/match/j1/2026/082907/) | 2026-08-29 | 4 | 川崎Ｆ | 4-2 | 千葉 |
| [34554](https://www.jleague.jp/match/j1/2026/082908/) | 2026-08-29 | 4 | 名古屋 | 2-1 | 岡山 |
| [34555](https://www.jleague.jp/match/j1/2026/082909/) | 2026-08-29 | 4 | 京都 | 2-1 | 福岡 |
| [34556](https://www.jleague.jp/match/j1/2026/082910/) | 2026-08-29 | 4 | 神戸 | 1-0 | Ｃ大阪 |
| [34557](https://www.jleague.jp/match/j1/2026/090216/) | 2026-09-02 | 5 | 水戸 | 4-2 | 鹿島 |
| [34558](https://www.jleague.jp/match/j1/2026/090217/) | 2026-09-02 | 5 | 千葉 | 1-2 | 岡山 |
| [34559](https://www.jleague.jp/match/j1/2026/090218/) | 2026-09-02 | 5 | 東京Ｖ | 0-2 | 神戸 |
| [34560](https://www.jleague.jp/match/j1/2026/090219/) | 2026-09-02 | 5 | 町田 | 2-1 | 川崎Ｆ |
| [34561](https://www.jleague.jp/match/j1/2026/090220/) | 2026-09-02 | 5 | 横浜FM | 1-1 | 京都 |
| [34562](https://www.jleague.jp/match/j1/2026/090221/) | 2026-09-02 | 5 | 清水 | 1-1 | FC東京 |
| [34563](https://www.jleague.jp/match/j1/2026/090222/) | 2026-09-02 | 5 | Ｃ大阪 | 2-0 | 柏 |
| [34564](https://www.jleague.jp/match/j1/2026/090223/) | 2026-09-02 | 5 | 広島 | 3-0 | 名古屋 |
| [34565](https://www.jleague.jp/match/j1/2026/090224/) | 2026-09-02 | 5 | 福岡 | 2-3 | 浦和 |
| [34566](https://www.jleague.jp/match/j1/2026/090225/) | 2026-09-02 | 5 | 長崎 | 2-2 | Ｇ大阪 |
| [34567](https://www.jleague.jp/match/j1/2026/090501/) | 2026-09-05 | 6 | 福岡 | 1-1 | 水戸 |
| [34568](https://www.jleague.jp/match/j1/2026/090603/) | 2026-09-06 | 6 | 鹿島 | 0-1 | 浦和 |
| [34569](https://www.jleague.jp/match/j1/2026/090604/) | 2026-09-06 | 6 | 千葉 | 2-0 | Ｇ大阪 |
| [34570](https://www.jleague.jp/match/j1/2026/090605/) | 2026-09-06 | 6 | 名古屋 | 1-3 | 町田 |
| [34571](https://www.jleague.jp/match/j1/2026/090606/) | 2026-09-06 | 6 | 岡山 | 3-2 | 広島 |
| [34572](https://www.jleague.jp/match/j1/2026/090607/) | 2026-09-06 | 6 | 柏 | 0-2 | 横浜FM |
| [34573](https://www.jleague.jp/match/j1/2026/090602/) | 2026-09-06 | 6 | 川崎Ｆ | 3-1 | 清水 |
| [34574](https://www.jleague.jp/match/j1/2026/090608/) | 2026-09-06 | 6 | Ｃ大阪 | 0-0 | 東京Ｖ |
| [34575](https://www.jleague.jp/match/j1/2026/090609/) | 2026-09-06 | 6 | 神戸 | 3-1 | 長崎 |
| [34576](https://www.jleague.jp/match/j1/2026/090610/) | 2026-09-06 | 6 | FC東京 | 2-0 | 京都 |
| [34585](https://www.jleague.jp/match/j1/2026/091101/) | 2026-09-11 | 7 | 京都 | 2-3 | 柏 |
| [34586](https://www.jleague.jp/match/j1/2026/091102/) | 2026-09-11 | 7 | 神戸 | 2-1 | 鹿島 |
| [34577](https://www.jleague.jp/match/j1/2026/091202/) | 2026-09-12 | 7 | 水戸 | 0-1 | 川崎Ｆ |
| [34578](https://www.jleague.jp/match/j1/2026/091203/) | 2026-09-12 | 7 | 清水 | 1-0 | 福岡 |
| [34579](https://www.jleague.jp/match/j1/2026/091201/) | 2026-09-12 | 7 | 町田 | 1-1 | 横浜FM |
| [34580](https://www.jleague.jp/match/j1/2026/091204/) | 2026-09-12 | 7 | Ｇ大阪 | 0-2 | FC東京 |
| [34581](https://www.jleague.jp/match/j1/2026/091205/) | 2026-09-12 | 7 | 広島 | 6-1 | Ｃ大阪 |
| [34582](https://www.jleague.jp/match/j1/2026/091206/) | 2026-09-12 | 7 | 長崎 | 2-0 | 名古屋 |
| [34584](https://www.jleague.jp/match/j1/2026/091303/) | 2026-09-13 | 7 | 浦和 | 1-2 | 岡山 |

## 検証と残課題

- 2015～2025の32成果物＋百年構想リーグ4成果物を隔離rootで再生成し、全36件バイト一致。
- 全pytest: 508件成功。git diff --check: 問題なし。既存コード・テスト・Validation・終了規則・依存に変更なし。
- 機械可読監査: `.tools/ongoing-candidates-final-verification.json`、`.tools/candidate-past-regression-verification.json`。
- 対象69候補の未解決件数は0。今後の新しい日程取得・新結果の終了確認・定期更新は別の作業。
- Elo、特徴量、モデル、commit・pushは実施していない。
