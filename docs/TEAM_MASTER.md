# チーム名称マスター

2026-09-16。Phase 2前準備として33クラブを登録した。Elo本体は未実装。
保存先は`data/master/teams.csv`、解決処理は`src/collect/teams.py`。
raw / processed、既存結果Validation、各大会の出力仕様には変更を加えない。

## 保存形式とID

UTF-8 CSV、1行が1つの取得元・表記・有効期間に対応するalias。7列すべてを持つ。

| 列 | 意味 |
| --- | --- |
| team_id | 永続的なプロジェクト内ID。現在team_0001～team_0033 |
| canonical_name | そのクラブの表示用名称。同じIDの全行で一致させる |
| source_name | 原本に掲載された文字列。全角・半角等を維持 |
| source | 表記の取得元。jleague_data_site / jleague_official |
| valid_from | alias有効期間の開始日。YYYY-MM-DD、空欄は開始制約なし |
| valid_to | alias有効期間の終了日。当日を含む。空欄は終了制約なし |
| source_club_id | 照合補助用の公式profile URLのslug。任意、空欄可 |

`team_id`は`team_`＋最低4桁の数字。名称、年度、CSV行位置、URLのslugをIDにしない。
初回割当の対応をCSVに固定し、追加・並べ替え・改称時に再採番しない。削除したクラブのIDも再利用しない。
例: 千葉=team_0001、FC東京=team_0003、大宮=team_0022、横浜FM=team_0033。
実装には自動採番・類似名の統合・ファイル書き込み処理を持たせない。

## 表記の根拠

86 aliasの内訳はData Site一覧の略称33、保存済みData Site詳細で確認した正式表記20、公式サイト表記33。
一覧の原表記33種とprofile slug33種は一対一で、同一略称が別クラブを指す例はなかった。

- 略称: 2015～2025年の保存済み一覧、百年構想リーグ一覧、2026/27の検証済みschedule。
- 正式表示名: `data/raw/jleague/2026_27/research/candidate_completion_20260915/official_fixture_index.html`。
  RSC `clubGroupOptions[*].options[*]` のvalue=slug、label=名称を対応付けた。
  原本は2026-09-15取得。全33クラブを照合し、source=`jleague_official`のaliasに登録した。
- Data Site正式表記20件: `data/raw/jleague/2026_hyakunen/match_*.html` の
  `div.score-board-main th#team-name-l / th#team-name-r`。同じslugの公式表示名と完全一致した。
  例: `FC東京`と`ＦＣ東京`を同じteam_0003のData Site aliasとして登録する。
- 残る13クラブの正式名はData Site側の保存済み根拠を確認できないため、そちらのsourceへは登録しない。

`canonical_name`は保存済み公式ページの表示名で、過去の試合当時の名称を表すものではない。
たとえば原表記「大宮」を残したまま、表示名を「ＲＢ大宮アルディージャ」とする。
今回の登録では改称適用日を推測せずvalid_from/toを空欄とした。空欄は史実上の改称日がないという意味ではない。
試合当時の名称が必要なら元のhome_team / away_teamを使う。公式表記の根拠は[DATA_SOURCES](DATA_SOURCES.md)参照。
追加のサイトアクセスは行っていない。

## 解決APIとエラー

`load_team_master(path=DEFAULT_TEAM_MASTER_PATH)`はCSVを読み、`TeamMaster`を返す。
不正ヘッダー、欠損・不正な値、逆転期間、同一source/nameの重複・期間重複、
同じIDの表示名不一致、同じsource/slugが複数IDを指す登録は`TeamMasterError`で拒否する。
source_club_idは補助照合用で、解決キーはsourceとsource_nameおよび必要に応じた日付である。

`resolve_team_id(source_name, source="jleague_data_site", on=None)`は完全一致のみ。
空白除去・Unicode正規化・英語翻訳・canonical_nameへの暗黙fallbackは行わない。
未知名・未知source・期間外は`UnknownTeamError`。期間付きaliasを日付なしで解決すると`AmbiguousTeamError`。
`on`はYYYY-MM-DD文字列、date、タイムゾーンなし午前0時のdatetime/Timestampを受け付ける。
現在日付を暗黙に使わないので、同じ入力は実行日に依存しない。

`add_team_ids(matches, source="jleague_data_site")`はhome_team、away_teamを解決し、
コピーへhome_team_id / away_team_idだけを追加する。match_date列があれば各行の日付を使う。
元の全列・値・行列順・indexを保持する。ID列が既に存在する場合は上書きせずエラー。
途中に未知名があっても入力DataFrameを変更しない。CSVへの保存は行わない。

## alias・改称・昇格クラブの追加

1. 原本と公式クラブ情報から、既存クラブの別表記か、新しいクラブかを確認する。
2. 別表記・改称なら同じteam_idでalias行を追加する。旧表記は削除しない。
   表示名変更時はそのIDの全canonical_nameを揃える。slug変更時もIDは維持する。
3. 期間を公式に確認できた場合のみvalid_from/toを設定する。旧名の終了日と新名の開始日を明示する。
   同一source/nameが時代により別クラブを指す場合は期間を重ねず、試合日付きで解決する。
4. 未登録の昇格クラブ等には未使用IDを明示的に割り当てる。次候補はteam_0034。
   リーグ区分や参加年はIDへ含めず、昇降格で変更しない。登録漏れを自動生成で補わない。
5. 根拠をDATA_SOURCESへ記録し、IDの固定期待値・網羅テストを更新してpytestを実行する。

## 検証

| 入力 | 行数 |
| --- | ---: |
| 2015～2025 J1（11 CSV） | 3,588 |
| 2026 J1百年構想リーグ | 200 |
| 2026/27 J1 schedule（予定含む） | 380 |
| 計 | 4,168 |

全8,336のhome/away参照が33 IDへ一意に解決し、同一試合のhome/away IDは異なる。
2026/27はread_latestで正式revisionを検証し、completed70件も別途確認した（上表では重複集計しない）。
追加ID列を除いたDataFrameは元と完全一致する。開始時に保存した全raw / processed 418ファイルのSHA-256も不変。

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_teams.py -q
.\.venv\Scripts\python.exe -m pytest
git diff --check
```

専用47件は、33クラブの固定ID、alias・改称・期間境界・名前再利用、未知名、CSV不正、入力非破壊を検証する。
実データの網羅テスト1件はローカルに保存済みの出力を読む。取得済みデータが全くない環境ではその1件をskipし、
人工データとGit管理されたマスターによる残り46件は通信なしで動作する。
