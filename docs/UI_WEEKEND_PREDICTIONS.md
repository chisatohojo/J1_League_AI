# 週末の予想：オフライン表示実装

判定：`J1AI_WEEKEND_GUI_OFFLINE_VERIFIED`。運用GUIへの反映は未実施。

既存UIの `b57454857e779bd4b4a16d620decc9a125423cce` から独立した
`feature/ui-weekend-prediction-list` で実装した。起動中launcher/server、Desktop、
運用feed、タスク、保存予測、研究系は変更しない。

## 5件表示の原因と保存状況

| JST開催日 | 保存済み公式日程の対象数 | Champion A保存済み | 未保存 |
|---|---:|---:|---:|
| 2026-10-24（土） | 5 | 5 | 0 |
| 2026-10-25（日） | 5 | 0 | 5 |

保存済み日別manifestとCSV、fixture binding、TeamMaster、公式revisionを読取り照合した。
全保存予測は19件。revisionは
`5678e72ddb61a08cc88eea58fa8b3e8833aa3f4bc8c714a59e2bc9f54c9f033f`、manifest SHAは
`5e6d370c0eaeee8d0bca676c7d8dc3b75fabb12cf7c03c7372a34ddff9f37f3e`。
公式観測UTCは `2026-10-23T22:00:22.614190+00:00`。新規取得はしていない。

- UI branchのfeed選択は既に金曜〜月曜を扱う。土曜だけの日付filterではない。
- schema v1の試合行には保存済み予測が必須で、未保存の日曜5件を表現できない。
- 現serverは起動時のJSON snapshotを保持する。コードやディスク上のJSONの変更は、
  起動中APIへ自動反映されない。

## 表示期間と状態

新しい任意sidecarは土曜・日曜だけを対象にする。検証済み公式revisionの観測UTCをJSTへ変換し、
観測日の属する週末以降で未終了fixtureが残る最初の土日を選ぶ。ホストの当日日付だけでは切り替えない。
日曜に未終了試合が残れば、その土曜も同じ一覧へ含め、終了状態を保持する。
金曜・月曜・祝日・週末外の延期試合を自動追加しない。節番号も推測しない。
既存schema v1の金曜〜月曜選定、火〜木単独開催、previousRoundの判定は不変で、土日一覧とは別契約。

| 状態 | 表示と確率 |
|---|---|
| `saved` | 保存済みChampion Aの確率・AI PICK・既存バー。generatedAtを保持 |
| `not_saved` | 「予測未作成」。prediction=null、確率なし |
| `schedule_unconfirmed` | 「日程未確認」。candidateを確定日程と扱わず、確率なし |
| `prediction_conflict` | 保存時と現在の日付/時刻が違うため警告・表示保留、確率なし |

identity、source witness、正式日時を検証できない場合は、推測せず読取り全体をHOLDする。
週末外へ改日程された保存予測は古い日へ載せず、対象外identityの警告集合を残す。
土日見出し、開催日・kickoff順、HOME/AWAY、テーブルを維持する。
表示更新はsource観測時刻、保存時刻は元のgeneratedAtであり、新たな予測時刻を作らない。

## 読取りadapterと互換性

`read_dashboard_projection` は既存feedの証拠検証を維持した表示contextを返す。
`build_dashboard_feed` のschema v1出力・選定・previousRoundは変更しない。
明示的なChampion-only入力では運用readerと同じ列・モデル版を要求する。

`weekend_display.read_saved_daily_projection` は既存2 CSV日別manifestだけを読む。
全SHA、binding、source/witness取得時刻、予測がkickoff前であること、TeamMaster、
日付別batch完全性、重複、読取り前後のbytes・batch集合を検証する。
CSV集約はメモリ内だけで行い、実ファイルへ書き出さない。

`project_weekend` は検証済みcontextの純粋な表示投影。
形式は `champion-weekend-display-v1` で、保存batchや予測manifestではない。
exact schema、モデルallowlist、source revision、期間、状態とpredictionの対応、旧feedへのSHA結合を検証する。
Python/JavaScriptの共通数値表現はIEEE754のbytesを使い、保存確率を丸めたり再正規化したりしない。
SHAはローカル整合性であり、外部署名や原本の真正性の代用ではない。

候補serverは任意の `weekend` 引数を検証・snapshot化したときだけ `/api/weekend` を提供する。
`/api/dashboard` はschema v1のまま。任意CLI `--weekend-data` は明示的な `--data` との一致が必須。
既存launcher・Desktopの起動引数は変更しておらず、この経路は運用へ配備していない。

`/?view=next` の名称は「週末の予想」。sidecarが404なら既存v1を表示し、日程未確認・全件一覧ではない旨を示す。
sidecar不正、異なるfeedとの組合せ、取得失敗では表示停止し、DEMOや古い確率へfallbackしない。
DEMOは明示モードで分離。前節routing・採点規則も不変。
ホームは保存済みプレビューを維持し、土日全件と未保存状況は一覧へのリンクで確認する。

## Weekend Batch Phase 4との境界

Phase 4の固定source、receipt、共通Elo、二重推論防止、保存後reader、feed再投影の契約を確認した。
Phase 4コードやreaderは変更・実行せず、今回のadapterからbackend/providerを呼ばない。
旧v2、`champion-weekend-v2-source-v1`、staging形式は日別形式として誤読せず拒否する。
将来はcanonical readerで完全性・source receiptを検証した値を表示contextへ渡す独立adapter審査が必要。
新形式を旧形式へ偽装しない。過去の613 PASSを今回のテスト数へ加算しない。

## 検証・保護

最終Pythonは395 PASS（新規44、関連回帰351、warnings-as-errors）。
Node/ブラウザJUnitの独立testcaseは70 PASS（新規20、回帰50）。合計465 PASS / 0 FAIL / 0 skip。
Nodeの集約親testを重ねて加算していない。過去の証跡と今回の実行は別管理。
土曜のみ・日曜のみ・両日保存・全未保存、JST、月/年境界、前後週混入、改日程、重複、
部分batch、モデル版/binding/SHA不一致、未知形式拒否、schema v1不変を検証した。
実ブラウザは合成データ・専用一時profile/loopbackだけを使用。
土日10行・未保存5行・バー5本、320/375px、既存1280×900、前節、DEMO・空・不正データを確認した。
初回回帰で説明文の増加による900px密度不足を検出し、説明を短くして修正後PASSとした。

開始時60,515ファイルをSHA・identity・size・mtime・creationで再照合する。
モデル53 payload、既存19予測、公式原本、タスク定義/状態、25既存worktree、main、Desktop、
対象launcher/serverを確認する。access timeは通常読取りで変化し得るため比較から除外する。
最終結果と証跡SHAは `UI_WEEKEND_PREDICTIONS_VALIDATION.json` に記載。

実モデルload/fit/推論、公式GET、予測保存・変更、実feed書込み、タスク実行/変更、
Weekend Batch実行、稼働GUI/server停止・再起動、Desktop変更は0。
実保存データはメモリ上の読取り照合までで、運用JSONは生成・上書きしていない。

## 本番適用前の別承認

1. 候補UI/reader/serverの配備先・版・backup/rollbackを承認する。
2. 同一の検証済みcontextからv1と土日sidecarを作り、表示用に一括確定する操作を承認する。
3. 現GUI/server所有権を再確認し、正式Stop・候補起動・必要なDesktop引数変更を別承認する。
4. 適用時に10行・確率5件・未保存5件と、404/不正sidecar時の挙動を再確認する。

rollbackは元UI/起動設定へ戻す。予測・batch・sourceは変更/削除しない。
未知の途中状態や配備競合ではHOLDし、自動修復・再予測・強制停止は行わない。
表示PASSは日曜予測生成、週末batch実行、NN研究接続、タスク有効化を承認しない。
