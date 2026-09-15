# 通常2026/27 J1: 進行中シーズンの更新設計

確認日: 2026-09-15（日本時間）。**更新基盤は `b50dd86` でcommit・push済み。終了規則を変更せず候補69件の追加確認を完了。**
2015～2025年および百年構想リーグの既存コード・Validation・出力は変更しない。

## 1. 大会識別と公式方式

| 項目 | 確認結果 |
| --- | --- |
| 正式大会 | ２０２６／２７明治安田Ｊ１リーグ |
| Data Site検索条件 | `competition_years=2026`、`competition_frame_ids=1` |
| 原表シーズン／大会 | `2026/27`／`Ｊ１` |
| 内部識別 | `competition_key=j1_2026_2027`、`season=2026`、`source_season_label=2026/27` |
| 方式 | 20クラブ、ホーム＆アウェイ2回戦総当たり、全38節・380試合 |
| 完了時のクラブ別件数 | 各38試合、home19・away19 |
| stage | `full_season`。地域区分やプレーオフなし |
| 開催期間 | 2026-08-07～2027-06-06 |
| 冬季中断予定 | 2026-12-19の第20節後、2027-02-13再開 |
| 結果 | 90分、引分あり、延長・PKなし。勝点3／1／0 |

方式と期間は[公式J1大会概要](https://www.jleague.jp/outline/j1/)、
[2026/27シーズン概要](https://www.jleague.jp/corporate//about_competitions/season/)、
冬季日程は[2026-06-16発表](https://www.jleague.jp/news/article/34183/)で確認した。
[2026-07-01発表](https://www.jleague.jp/news/article/34294/)では2027年開催分の詳細発表は12月上旬予定。
公式年間カード表には候補日・未定・空欄があり、Data Siteに単一の日付が表示されていても確定予定日と断定しない。

対象URL: [通常2026/27 J1の日程・結果](https://data.j-league.or.jp/SFMS01/search?competition_frame_ids=1&competition_years=2026&tv_relay_station_name=)。
百年構想リーグの`20261`・大会枠`35`とは別。以前保存した大会カタログの`selectValue=725`も参照できるが、
今回確認した検索条件は上記の年・大会枠の組であり、別の大会IDパラメータを推測で追加しない。

`season`は開始年2026とし、`match_date`は実際の2026年または2027年の日付を保持する。
既存`validate_matches`はseasonと日付年の一致を要求しないため、この対応は既存契約内で可能。
一方、通常年度のHTML解析は年の一致・対応年度を、年間集計は全件数を要求するため、そのまま流用しない。

## 2. 初回調査で取得した情報

2026-09-14 **22:48:04 UTC（09-15 07:48:04 JST）**の一覧を1回取得。
同じ`table.table-base00.search-table`、従来と同じ11列に、終了結果候補と未開催予定が共存していた。

| 観測項目 | 結果 |
| --- | --- |
| 全行 | 380行、20クラブ、38節各10行、各クラブ38カード |
| 数値スコア掲載 | 70行、第1～7節各10行、2026-08-07～09-13 |
| 未開催表示 | 310行、スコア欄は`vs`、表示日は2026-09-19～2027-06-06 |
| スコア行の公式match_id | 70件すべてに`/SFMS02/?match_card_id=...`、70件一意 |
| 未開催行の公式match_id | **310件すべてリンク・IDなし** |
| 未開催行のK/O時刻空欄 | 180件 |
| 未開催行の入場者数空欄 | 310件 |
| 未開催行の会場未定 | `●未定●`が10件 |
| 取得できる原情報 | 年度、大会、節、表示日、K/O、home/away、得点またはvs、会場、入場者数、放送 |
| クラブの識別根拠 | home/awayそれぞれの公式クラブprofile URL |

一覧には時刻・会場の空欄が調整中である旨の注記もある。
空欄の予定時刻や会場を0・仮の会場で補完しない。未開催の得点/resultもnullのままとする。

終了根拠を調べるため、[34583 東京Ｖ－千葉の詳細](https://data.j-league.or.jp/SFMS02/?match_card_id=34583)だけを追加取得。
「公式記録」、2026-09-13、前半0-0・後半1-1・合計1-1と両クラブを確認した。
ただし初回調査の一覧・詳細には明示的な「試合終了」ステータスがなく、試合中や中断中の掲載仕様も未確認。
**数値スコア70行を、自動的に終了確定70行とする規則は採用しない。**
この段階ではCSVへ取り込まず、次節の公式終了根拠を確認してから実装した。

調査用原本は次に保存した。以前の原本は再利用し、新規のData Site GETは一覧1＋詳細1の計2回。

```text
data/raw/jleague/2026_2027/research/20260914T224804164752Z/
    j1_search.html
    j1_search.metadata.json
    match_34583.html
    match_34583.metadata.json
```

| 原本 | UTC取得日時 | bytes | SHA-256 |
| --- | --- | --- | --- |
| j1_search.html | 2026-09-14T22:48:04.164752+00:00 | 435727 | `5fab2eec20adc2e2b0015ddcd65b5672da6e836acfb881f71c62c8651adea9b6` |
| match_34583.html | 2026-09-14T22:49:49.355140+00:00 | 117827 | `b9a0e871c237e4d3c5e0bfe03e56150db641844e47585def18141c3ad8a3af09` |

両応答はHTTP 200・UTF-8、要求URLと最終URLが一致。metadataに各URL、status、日時、Content-Type、bytes、SHAを保存。
一覧応答にはETag・Last-Modifiedがなかった。条件付きGETが使えるとは仮定しない。

## 3. 採用した終了確認の根拠

Data Siteの一覧得点、SFMS02の「公式記録」という題名、前後半の内訳だけでは終了扱いにしない。
Data Siteトップのシーズン集計や、別サービスDigital Data Bookの公開時期説明も、SFMS02各試合の終了根拠には転用しない。

補助証拠に[Ｊリーグ公式の東京Ｖ対千葉](https://www.jleague.jp/match/j1/2026/091302/)を使用した。
実際の試合サマリーの `section#game-over.p-game-details-summary-tab__game-over` に
`h3` の「試合終了」と1-1の得点があり、対象の実ヘッダーも試合後状態で1-1だった。
[未開催の浦和対東京Ｖ](https://www.jleague.jp/match/j1/2026/091904/)にはこの終了欄がない。
両方に `post-game` クラス付きの読み込み待ちskeletonがあるため、クラス名だけの判定は誤る。
scriptの翻訳辞書にも「試合終了」があり、ページ全文の文字列検索も判定には使用しない。

`parse_completion_evidence` は次のすべてを確認する。

1. 取得URLとcanonicalが一致する公式 `/match/j1/{2026|2027}/{6桁}/` ページ。
2. skeletonを除いた実ヘッダーが1件。通常J1ロゴ、対象期間の日付、節、左右のクラブURLを確認。
3. 実DOMの終了欄が1件で、その見出しが「試合終了」。実ヘッダーのpost-game状態と両得点も一致。
4. Data Site側のfixture_key・開催日・節・左右クラブ・得点と一致し、公式match_idを持つ数値スコア行。

script・template・noscript・skeleton・対象自身や内部の非表示要素は根拠から除外する。
Reactのストリーミング配送用コンテナー自体を機械的に全排除せず、配送された実DOMの対象領域を解析する。
構造変更、別大会、複数候補、別日付、得点矛盾なら停止する。終了欄がなければ `verified=false`。
基盤実装時は34583（2026-09-13、東京Ｖ－千葉、1-1、result=1）の1件だけを確認し、残り69件には推測で付与しなかった。
その後、同じ規則で69件の公式ページを個別確認した結果は第8.1節を参照。

追加の原本確認は公式matchページ2件のGETだけ。Data Site一覧・詳細は再取得せず、最終再開後は全てオフライン。
調査時の公式サイト案内2ページのweb閲覧は終了証拠として使用していない。

```text
data/raw/jleague/2026_27/research/20260915T035921896334Z/
    official_match_091302.html
    official_match_091302.metadata.json
    official_match_091904.html
    official_match_091904.metadata.json
```

| 原本 | UTC取得日時 | bytes | SHA-256 |
| --- | --- | --- | --- |
| official_match_091302.html | 2026-09-15T03:59:22.429453+00:00 | 1889599 | `731f16cc9c5eecd481d9b304befc45a12448f0d213addc3df13ed19b93970b47` |
| official_match_091904.html | 2026-09-15T04:00:08.302656+00:00 | 985644 | `37a61f29d98f9221c82691d2509c993da47cc3f6af6b93f5b70c0779d602bc71` |

## 4. Snapshotと成果物

今回指定された保存先 `2026_27` を採用した。初回調査の `2026_2027/research/` は移動・削除せず保持する。

```text
data/raw/jleague/2026_27/
    research/                       # 終了根拠の調査キャッシュ
    acquisitions/<取得ID>/          # 明示--fetchの応答とmetadata。失敗時にも成功分を保持
    snapshots/<snapshot_id>/
        listing.html
        listing.metadata.json
        evidence_001.html           # 必要な公式match証拠。0件以上
        evidence_001.metadata.json
        manifest.json

data/processed/jleague/2026_27/
    runs/<snapshot_id>-ongoing-v1.json
    revisions/<revision_id>/
        schedule.csv                # 全予定・候補・終了確認済み。statusで区別
        completed_matches.csv       # 終了確認済みだけ
        fixture_identity.csv        # fixture_keyと公式match_idの対応
        change_log.csv              # 処理済み履歴＋今回の差分
        update_summary.json
        review.md
        observations.json           # null・整数等を保存した再現用レコード
        changes.json                # 今回の差分だけ
        manifest.json               # 各出力SHAと処理入力・比較基準
    latest.json                     # 正式な採用revisionへの参照
    schedule.csv                    # 以下6件はlatestの閲覧用コピー
    completed_matches.csv
    fixture_identity.csv
    change_log.csv
    update_summary.json
    review.md
    failures/<試行ID>.json           # 解析・Validation等の例外診断
```

rawは既存7項目のmetadata（URL、最終URL、HTTP status、UTC取得日時、Content-Type、bytes、SHA-256）と照合する。
HTTP200・UTF-8 HTML・対象公式URLを確認。snapshot manifestにsourceごとのHTML/metadata SHA、
取得順序sequence、前回snapshot ID、一覧取得日時、証拠を含む最終観測日時を固定する。
入力を排他的な一時フォルダーへ保存してからsnapshotディレクトリを確定し、その後は追加・上書きしない。
自動IDはUTC日時＋衝突防止IDで、取得順序はmanifestに別保存する。指定IDも利用可能。
同じID・同じ入力は既存snapshotを再利用し、異なる入力なら拒否する。
別の取得で同じHTMLが返っても、新しいmetadataと新しいsnapshotを保存する。
後から公式証拠を追加するときも、同じ一覧キャッシュを含む新snapshotを作り、古い原本へ追記しない。

`runs` は最初に処理した際の前回採用revisionと入力manifestのSHAを固定する。
revision IDはその固定入力と解析版 `ongoing-v1`、終了規則 `official-game-over-v1` から決まる。
終了証拠を前回採用結果から継承する場合は、そのrevisionへの参照も入力依存関係になる。

## 5. 状態・fixture_key・Validation

| status | 条件 | 結果Validation |
| --- | --- | --- |
| scheduled | 一覧のvs表示。公式IDなしを許容し、得点/resultはnull | 渡さない |
| candidate | 数値得点と公式IDはあるが、照合済み終了根拠がない | 渡さない |
| completed | 第3節の公式終了根拠と一覧が一致 | 既存validate_matchesへ渡す |

`scheduled` は原本の予定表示を意味し、日時経過だけで試合の開始・終了を決めない。
未知の得点表記、延期・中止・中断等の未対応表記は推測せず解析エラーとし、rawと旧latestを維持する。
対戦は次の方向付きキーで追跡する。

```text
fixture_key = j1_2026_2027:<home_club_slug>:<away_club_slug>
例: j1_2026_2027:tokyov:chiba
```

クラブslugはData Siteの公式profile URLから取得する。開催日、KO時刻、会場、節はキーに含めない。
同一方向のカードは年間1回という確認済み大会方式に基づき、日程変更でも同一キーを保つ。
公式ID出現後もキーを維持し、`fixture_identity.csv` に対応を保存。IDなしを仮のmatch_idで補完しない。
既存IDの再割当、別カードへの移動、IDの消失は自動統合せず採用を保留する。
過去の対応は各revisionおよび差分のbefore/afterに残る。

原本のクラブ名・会場名・日付表記・節・時刻・得点表記・入場者数・放送・source URLを保持する。
`season=2026`、`stage=full_season`。2027年開催日を2026年に書き換えない。
予定の表示日は確定日程と断定せず、未定会場・時刻もそのまま保存する。
v1は今回観測した単一日付表記を解析し、候補日・未知の書式へ変わった場合は停止する。

終了確認済みだけを既存10必須列を含むDataFrameとしてValidationへ渡す。
終了0件なら `result_validation=no_completed_matches` とし、空を拒否する既存Validationは呼ばない。
完成結果の必須欠損・負得点・得点/result矛盾があれば、Validation失敗で新しい公開を止める。
予定集合には20クラブ・38節・380方向付き対戦、各クラブ38/home19/away19、各節全クラブ1回を別途検証する。
380を終了件数の条件にせず、少数のcompletedを許容する。

以前の終了根拠は、同じfixture・match_id・日付・節・得点/resultが続き、新しい証拠と矛盾しない場合だけ継承する。
得点や日付が変われば再確認が必要。古い証拠を変更後の得点の証明には使わない。
列 `evidence_url`、`evidence_type`、`evidence_sha256`、`evidence_fetched_at_utc`、
`completion_origin_snapshot`／必要時の `completion_origin_revision` に来歴を残す。

## 6. 差分・訂正履歴

前回取得snapshotと、前回採用revisionの両方に対して比較する。
前回が保留でも取得間の変化は保持し、採用済み結果への影響も別に把握できる。
比較対象のraw・出力SHAを確認し、前回解析ができなければ比較不能と新規採用保留を明示する。

| event_type | 意味 |
| --- | --- |
| new_fixture | 初めて現れた予定キー |
| schedule_changed | 開催日・時刻・会場・節の変更 |
| identity_linked | IDなし予定に公式match_idが出現 |
| result_candidate | 初の数値スコア、または未確定候補の得点変更 |
| completed | 終了未確認から公式終了確認へ |
| result_corrected | 前に終了確認した得点/resultの変更。再確認できなければ保留 |
| missing_from_snapshot | 前回にあったカードが今回にない。自動削除しない |
| identity_conflict | 既存ID消失・変更等の対応矛盾 |
| completion_unconfirmed | 終了根拠の撤回・得点変更等で再確認が必要 |
| metadata_changed | 上記以外の原表記等の変更 |

各イベントには一意event_id、比較種別、前後snapshot、fixture_key、match_id、検出UTC日時、
変更列、before/afterを保存する。日程と得点など複数の変更分類が同時に生じることも保持する。
原本SHAとレコードの意味内容を分け、広告・行順だけの変更や同じ結果に対する追加証拠を得点訂正と扱わない。
公式掲載値A→B→Aも2回の訂正として残す。イベントIDを得点だけから作らず、対象snapshot等を含める。
検出時刻は固定した最終観測時刻であり、公式訂正が実際に発生した時刻ではない。
初回の2比較は同じ空集合が基準なので、各分類件数は `change_counts_by_comparison` で比較別に表示する。

得点が変わって終了根拠が不足した場合でも、保留revisionに訂正のbefore/afterを残す。
後の採用revisionのchange logにも過去の処理済み差分を含める。
解析失敗時はrawとfailure診断を保持するが、解析不能な行の意味差分を捏造しない。
parser/policy変更時は既存revisionからの自動移行を拒否し、公式訂正とは別に移行を設計する。

## 7. 公開・idempotency・運用

1. raw保存、解析、状態照合、全予定検証、終了結果Validation、差分生成、CSV再読込を完了する。
2. 出力とSHA manifestを一時ディレクトリへ保存し、immutable revisionとして確定する。
3. 一覧が現在採用中より古くないこと、固定した採用基準が変わっていないことを確認する。
4. 全検証成功後のみ閲覧用コピーを更新し、最後に `latest.json` をatomic replaceする。

rawの `.snapshot.lock` と加工側の `.update.lock` で同時writerを拒否する。
残ったlockは時間だけで自動奪取せず、作業者がプロセス状態を調べて復旧する。
失敗した候補や欠落・終了撤回は旧latestを維持し、保留理由をrevisionへ残す。
通常の公開例外では閲覧用コピーを元に戻す。プロセス強制終了ではコピーが一時的に混在し得るため、
**複数ファイルを整合した状態で読むプログラムは `read_latest()` が検証した不変revisionを使う。**
トップ階層CSVを独立して読むことを、複数ファイルのatomicな読取とは扱わない。
同snapshot再処理で閲覧用コピーを復旧できる。採用基準が変わっていたら古い処理で巻き戻さない。

同じ入力は初回の比較基準とrevisionを再利用する。再実行時の現在時刻を履歴へ追加せず、重複行・イベントを増やさない。
古いsnapshotのreplayや、新IDで古い一覧を取り込んだ場合も最新採用状態の後退を防ぐ。
replayが返すsummaryは当時の採用結果であり、現在のlatestは `read_latest()` で確認する。

保存済み原本からのbootstrap（通信なし）:

```powershell
.\.venv\Scripts\python.exe -m scripts.update_jleague_ongoing capture `
  --listing-html data/raw/jleague/2026_2027/research/20260914T224804164752Z/j1_search.html `
  --evidence-html data/raw/jleague/2026_27/research/20260915T035921896334Z/official_match_091302.html `
  --evidence-html data/raw/jleague/2026_27/research/20260915T035921896334Z/official_match_091904.html `
  --snapshot-id bootstrap-20260915

.\.venv\Scripts\python.exe -m scripts.update_jleague_ongoing replay `
  data/raw/jleague/2026_27/snapshots/bootstrap-20260915
```

将来の明示的更新は `capture --fetch`。対象シーズンの全一覧を1回だけ取得する。
新しい終了確認が必要な場合だけ `--evidence-url` で公式match URLを明示する。
保存済み証拠は `--evidence-html` で再利用可能。公式match URLや別年度を自動列挙しない。
30秒タイムアウト、複数の新規証拠間に1秒待機、自動再試行なし。
CLIは採用0・保留2を終了コードとし、解析例外時も成功とは扱わない。
定期実行・自動URL発見・詳細だけの訂正の定期監査は未実装。
HTTP通信自体の失敗はCLIでエラーとなり、保存済み成功応答はacquisitionsに残る。
全HTTP失敗の応答本文を一律保存する機構や包括的な取得試行台帳はv1の対象外。

## 8. 初回成果物・最終検証

snapshot: `bootstrap-20260915`。
revision: `a5f7e4c2e9b53b7860f0f3e727ff212456128f203adae92fc5abd9f42ba80e9b`。
一覧の観測時刻は2026-09-14T22:48:04.164752+00:00、証拠を含む最終観測は2026-09-15T04:00:08.302656+00:00。
同時に取得した1ページの状態と偽らず、sourceごとの観測時刻とSHAを保存している。

| 確認項目 | 結果 |
| --- | --- |
| schedule | 380行、20クラブ、38節、各節10、各クラブ38/home19/away19 |
| 状態 | scheduled310、candidate69、completed1 |
| fixture_key | 380件一意。日付・KO非依存 |
| 公式match_id | 70件一意、310予定は空。対応表は全380キーと一致 |
| completed | 34583 東京Ｖ－千葉、1-1・result1。既存Validation・CSV再読込成功 |
| 初回差分 | 各比較基準でnew_fixture380・result_candidate70・completed1。2基準計902イベント、一意 |
| idempotency | 同一ID再import＋2回replay後、raw7ファイルとprocessed17ファイルの全バイト一致 |
| 状態遷移等 | 人工fixtureで予定変更→ID出現→candidate→completed、訂正A→B→A、欠落・保留復旧、ID競合を検証 |
| 障害・順序 | raw改竄、Validation不合格、公開直前障害、writer lock、古snapshotによるlatest後退を防止 |
| 過去成果物 | 2015～2025の32件＋百年構想リーグ4件を隔離rootで再生成し、全36件バイト一致 |
| 既存データ | 作業開始時の92ファイルのSHA不変 |
| 全pytest | 508件成功 |
| git diff --check | 問題なし |

再生成比較・idempotency・来歴監査の機械可読記録はローカルの `.tools/ongoing-adapter-final-verification.json`。
基本テストは人工HTML・人工シーズンで実行でき、ネット接続を必要としない。
追加のローカル原本検証1件は、配布対象外のキャッシュがない環境ではskipする。

### 8.1 候補69件の追加終了確認（2026-09-15）

基盤の終了判定・Validation・更新処理を変更せず、対象69試合すべての公式終了根拠を照合した。
新状態は **scheduled310・candidate0・completed70**。初回snapshotと第8節の検証記録は履歴として保持する。

- 新snapshot: `confirmed-candidates-20260915`。
- 新revision: `9622f4bd6332db056e214b5cb94aed12d2c2d1ec187118b03f3d2d350f3850ec`。
- 取得: 公式URL発見用一覧1 GET＋未取得の試合ページ69 GET。既存ページを再取得せず、Data Site一覧も再利用。
- 一覧観測時刻は初回と同じ。証拠を含む最終観測UTCは `2026-09-15T10:23:54.019228+00:00`。
- 既存fixture_key/ID対応と試合値は不変、終了確認後の70件は既存Validationを通過。
- 差分は前回取得／採用の各基準でcompleted69だけ。既存902イベントを保持し、全1,040件一意。
- 同一snapshot再import・2回replayで全raw/加工ファイル不変。旧bootstrap再処理でも最新参照を巻き戻さない。
- 過去2015～2025と百年構想リーグの36成果物を再生成して完全一致。全508pytest成功、git diff --check問題なし。

全試合の公式リンク・取得時刻・監査の詳細は[候補終了確認報告](JLEAGUE_2026_27_CANDIDATE_REVIEW.md)。
今回の処理にコード・テスト・終了規則の変更はない。

## 9. 残課題と互換性

対象69候補の終了確認は完了し、現在candidateは0件。今後新しい結果が掲載された際も、公式終了根拠を必要分だけ確認する。
中断・延期・取消・候補日の未確認書式は検知時に個別調査し、勝手な完了・削除・日程確定はしない。
一覧に見えない詳細だけの事後訂正、日程の確定段階、自動URL発見、定期更新、parser移行は別課題。

新規コードは専用source・保存更新モジュールとCLI、テストは専用2ファイル。
2015～2025の共通処理・百年構想リーグ・既存Validation・依存ファイルは変更していない。
raw・生成データは既存.gitignoreどおりローカル保持。Elo・特徴量・AIモデル、commit・pushは行わない。
