# 日曜5試合：個別承認用の実行・保存・表示計画

**未実行。現在は `CHAMPION_A_SUNDAY_PREDICTION_BLOCKED`。**
[調査結果](CHAMPION_A_SUNDAY_PREDICTION_PREFLIGHT.md) とJSON台帳を正本とし、
ここに記載した処理を今回の承認と解釈しない。raw・source・予測を手直ししてゲートを通さない。

## 推奨する順序

1. **既存定時処理の結果を先に再確認する。** 10/24 22:00はsource/表示のみ、10/25 07:00は
   通常の日別選択である。予定どおり動くことや成功することを仮定せず、タスクを再実行しない。
   翌日の全5件が既保存なら推論を行わず、保存の検証と表示計画へ進む。部分保存ならHOLD。
2. **保存済みsourceで履歴を再監査する。** 日曜より前の全fixtureが明示的終了証拠付きcompleted、
   特に土曜5件が90分結果として確定し、そのraw/metadata/取得UTCが整合していること。
   source age≤24時間、観測UTC≤実行時刻、ID/日時/TeamMaster/変更履歴が許可対象と一致すること。
   今回のrevisionは土曜5件未完了のため不適格。試合時間から終了を推定しない。
3. **新しい公式取得が不可避なら、取得だけを別承認する。** 具体的URL集合、host、アクセス条件、
   redirect、retry、requests/bytes/deadline、保存先、STOP条件をその時点で固定する。
   通常collectorはdiscoveryとpublicationを伴い、日曜5 URL限定の取得器ではない。
   現行 `_fetch` のredirect可能性を隠した厳密GET上限を宣言しない。
   この段階のsource更新も、後の推論やGUI反映を自動承認しない。
4. **単日A経路の実行guardを別審査する。** 通常CLIには日付/skip-collectorがないため、
   盲目的にmorning CLIを実行して「日曜だけ」と扱わない。正式関数を維持する最小driverなら、
   collector後に選ばれた全targetのkey/namespace/ID/日付/kickoff/両クラブを5件allowlistと完全比較し、
   revision/SHAを封印してから既存predictorへ渡す。相違・追加・不足でモデルload前にSTOP。
   固定sourceを使う場合も非収集driverの新契約として検証・承認し、通常collectorをmockで
   無断に差し替えた実運用を作らない。このguard/driverは本工程では未実装。
5. **実モデルload/predictと新規日別保存を個別承認する。** 固定model/scaler 5 SHAと
   12 data pins、百年構想履歴、依存環境を再検証する。既存 `update.lock` と共有する排他を使い、
   task/source writerと競合せず、stale/所有不明lockはHOLDする。既存19件のSHAを再保存する。
   予約・共通金曜snapshot・Weekend Batch/NN分岐は使わない。全5件同日でElo mapは共通。
6. **保存後を読取り専用で検証する。** 全5確率のclass順・有限性・範囲・和、生成UTC、各kickoff前、
   fixture binding、source/witness SHA、全CSV/manifestを照合する。
   旧19件不変、新5件のみ、重複0、期待batch ID・ファイル集合・読戻し一致を確認する。
   これは予測の再計算ではない。batch公開は一度限りで、不明状態を自動再試行しない。
7. **表示用pairの準備を別承認する。** 配備済みreaderで保存batchだけを読み、既存v1 feedと
   weekend sidecarを新規stagingへ投影する。予測器を呼ばない。source更新で対象日程や前節が
   進む場合は実数で検証する。現在のpairは上書きせず、新release・manifest・独立読戻しで封印する。
8. **GUI反映を別承認する。** 現在の所有権、旧pair/shortcut backup、task非競合を再確認後だけ、
   正式Stop→終了/port/mutex/Event解放→新pair引数のshortcut→Desktop起動→実表示・保護監査。
   現serverをStopする手順を今回実行しない。

## 時刻とSTOPゲート

- 最早kickoffは2026-10-25 14:00 JST（05:00 UTC）。開始だけでなく生成・保存前検査も厳密に前。
- 実行が遅れた場合に全5件を過去時点の予測として作らない。期限超過・改日程では再承認する。
- source取得/結果確認UTC≤使用時刻。後日取得情報を土曜以前・金曜07:00以前へ付け替えない。
- 土曜結果を使えるのは実行前に確定・取得済みの場合だけ。未確定スコア、PK/延長混入は拒否。
- ID/namespace/クラブ/結果/日時/モデル版/入力SHAの相違、追加対象、部分既保存、過去cutoffの
  入力再現不能、clock逆行、task競合、所有/ACL不明、lock残存、reader形式不適合でSTOP。
- 失敗後に別revision、別モデル、旧確率、研究値へ自動fallbackしない。
- ソース更新前に再度未保存集合を読み、定時処理が先に成功していたら二重推論しない。

## 保存先・責務・復旧

| 境界 | 成功時 | 失敗時 |
|---|---|---|
| 公式取得/publication | 新しい承認revisionと実取得証拠を保持 | 元原本を消さずHOLD。latestを過去へ無断復元しない |
| モデル前 | 完全な5件target/source/model pinを確定 | load/predict 0件。診断と承認対象を保持 |
| batch rename前 | staging全件を検証 | 可視の新規batch 0件。既存19件不変、残存stateを手動調査 |
| batch rename後 | 5件・全manifestを不変保持 | GUI/表示が失敗してもbatchを消さず、再推論しない |
| GUI投影/反映 | 新pairから表示。再表示は読戻しだけ | 前pairと前shortcutで切戻す。保存予測/sourceを巻き戻さない |

`publish_batch` はfixture集合SHA directoryを新規renameし、CSVとbindingを組で見せる。
別processとの排他・重複確認はcallerの仕事であり、関数単独の直接実行を承認対象としない。
native予測IDはmatch ID＋namespace＋fixture binding＋model＋生成UTCで、新しいUUID登録はない。
planned batch IDはJSON台帳に計算値だけ記録し、directory/manifest/実行permitは作らない。

現在のNTFS保存先・所有者/DACL・祖先reparse不在・lock不在は読取り確認済み。
本工程ではcreate/rename/競合/電源断を実際の本番保存先で試していない。
既存workerのTempDirectory cleanup、batch後feed失敗、sourceだけ先行更新の可能性を残す。
手動復旧はPIDだけで判断せず、process作成時刻/exe/SID/親子/実行markerを確認する。
不明なstaging/lockを削除・強制回収しない。電源断耐性や3領域全体の原子的rollbackは保証しない。

## ユーザーが次に承認する対象

まずは、**既存定時処理後の保存source・batchを再確認する読取り専用preflight**。
土曜完了がまだ確認できなければ、その時点の正確な条件で限定source取得を別承認する。
条件成立後も、実行guardの変更差分、実モデルload/predict＋新5件保存、通常workerの
view/status/retrospective副作用、表示pair生成、正式Stop/GUI切替を個別に明示する。
単に「日曜5件を表示して」と承認されたことを、これらすべての承認と扱わない。

今はモデル実行・取得・保存・GUI更新のいずれの承認待ち操作も実行していない。
