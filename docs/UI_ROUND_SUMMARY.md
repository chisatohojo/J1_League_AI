# 試合一覧とWindows入口の改善

main `05c1598`から独立した`feature/ui-round-summary-shortcut`で実装した。
元の作業worktree、NN研究branch、モデル・保存確率、公式source/publication、
学習/評価/推論、07:00/22:00タスクは変更していない。初回UI改善ではfeed生成器も変更せず、
以下の開催期間拡張で選定処理だけを独立して変更した。

## 画面とデータの範囲

トップに「次節の予想一覧」「前節の答え合わせ」の2つのリンクカードを置いた。
PCは横2列、スマホは縦2列。カード全体を通常のリンクとし、Enter、focus表示、
直接URL、ブラウザの戻る/進むを使える。トップのカード表示も維持した。

`/?view=next`は日時(JST)、HOME/AWAY、保存確率の完全精度によるAI PICK、
HOME/DRAW/AWAY数値と小型バーを1行へまとめる。`/?view=previous`は保存済み
PICK、スコア、実HOME/DRAW/AWAY、文字と記号によるHIT/MISS/判定対象外を示す。
同率最高にtie-breakを加えず、表示丸めで判定しない。的中率やランキングは追加しない。

既存`/api/dashboard`のschema v1だけを使う。新しい予想/結果APIは作っていない。
不正データは表示停止、空データは明示的な空状態。研究データ・デモへのfallbackや
予想補完はない。`/?demo=1&view=next`、`/?demo=1&view=previous`はDEMO表示と
同モードのトップへ戻るリンクを保持する。Champion状態、データ状態、SEALED表示は
一覧でも残す。追加static allowlistはSVG/ICOの2資産だけ。

前節の選定は**公式カレンダーの対象日**、次の予想は**対象日または金曜〜月曜の開催期間**
であり、節番号ではない。元の`round.label`と保存済み件数、範囲を示す注記を表示する。
真の1節全件への拡張には公式節情報・延期/変更試合を扱う別データ契約が必要。
fixture bindingsや保存確率・保存時刻を変更しない。

## 金曜〜月曜の開催期間（2026-10-22追加）

検証済みの現行公式カレンダー上で、未終了かつ保存済みChampion A予想がある最も早い
開催日（JST）を起点にする。金・土・日・月なら、その日を含む金曜〜月曜の最大4日間を
選ぶ。月曜は直前の金曜に属する。期間内の未終了・保存済み予想を日時、fixture IDの順で
すべて表示する。終了済みは次の予想へ含めず、土曜や日曜から起点が始まっても同じ期間に
なる。火〜木が起点なら従来どおりその1日だけを選び、週末へ飛ばさない。月・年またぎは
暦日演算で扱う。前節の「保存済み結果がある最新の完了日」という選定方法は不変。

schema v1の`nextRound.matches`と`label`のみを使い、新APIは追加しない。
表示名は「次の開催週末 · 2026-10-23〜2026-10-26」などで、トップと一覧に対象期間と
保存済み件数を表示する。未保存日を補完せず、日付別保存バッチの完全性検査、公式identity、
改日程、source revision、予測時点の検証は維持する。空状態・DEMOの明示・不正データでの
表示停止も維持する。未終了は現行公式statusに従い、独自の終了時刻を推定しない。

検証は合成入力のみ。Python（feed/server）231 PASS、UI・実ブラウザの合成検証51 PASS。
金1＋土4＋日5、月曜、残る各曜日からの同一期間、終了済み除外、火〜木、月/年またぎ、
期間外除外、未保存日、部分バッチ拒否、JST深夜と公式改日程、前節回帰、schema、トップと
一覧、DEMO・空・不正入力を確認した。今回は実feedの生成・上書き、予想生成、モデルload、
学習、性能評価、公式収集、運用タスク操作、Desktop移行は0。既存テスト記録とは別に
[今回の検証集計](UI_WEEKEND_VALIDATION.json)へ記録する。

## 定時保存範囲の読み取り監査（2026-10-22 JST）

既存07:00/22:00タスク定義が参照する別worktreeのコード・設定と、保存済みbatch manifest、
公式revision、CSVのSHAを読み取り照合した。タスクや運用feedは実行・変更していない。

| 開催日 | 公式未終了 | 保存済みChampion A | 未保存 |
| --- | ---: | ---: | ---: |
| 2026-10-23（金） | 0 | 0 | 0 |
| 2026-10-24（土） | 5 | 5 | 0 |
| 2026-10-25（日） | 5 | 0 | 5 |
| 2026-10-26（月） | 0 | 0 | 0 |

根拠となる公式revisionは`d179144f38ec64a43ef6bd860ca8802a19c89399a69e29c4e20c8cde1d15dc23`、
manifest SHAは`14ebc385fd3e45597895700abf8b524c6faf71f339c99cb653ebdd8c9a474184`。
公式観測は2026-10-22 07:00:30 JST。日別の保存済みbatchに10/25のfixtureは存在しない。
個別fixture・実予想・個人パスはローカル監査証跡へ保持する。

設定は`lookahead_days=2`。朝処理の`select_targets`はJST当日〜2日先の未保存scheduledから
最も早い日付の完全な1日分を選び、1回で複数日を保存するloopはない。夜処理は予想生成を
行わない。10/22時点で10/25は探索範囲外である。さらに`require_complete_history`は対象日
より前の公式試合がすべて完了済みであることを要求するため、単にlookaheadを広げても、
未終了の土曜を飛ばして日曜を事前生成できる契約ではない。将来の実行成功は推定しない。
金曜〜月曜分の事前保存を保証する処理ではなく、今回のUI拡張だけでは未保存5件は増えない。
次の週末10/31の6件・11/1の4件も現時点では未保存（14日範囲の別集計）。

運用タスクは別worktreeの旧feed生成器を使い、今回のコード変更は自動反映されない。
運用への反映や保存方式変更、実feed再生成は別承認とする。

ローカルで読取り検証した既存`view/champion_home.json`はschema v1に合格し、
前対象日10件/次対象日5件だった。別の`champion_rounds.json`は異なるschemaのため
本UIへ接続しない。現行serverは起動時snapshotであり、運用タスクがJSONを更新した
後は、自身のlauncherを`--stop`して再起動すると新しい表示を読む。自動生成/自動探索はない。

## スクリーンショット（すべて合成テスト）

- [トップ](ui-round-summary/home.png)
- [予想一覧・PC](ui-round-summary/next.png)
- [答え合わせ・PC](ui-round-summary/previous.png)
- [予想一覧・320px](ui-round-summary/next-320.png)
- [答え合わせ・375px](ui-round-summary/previous-375.png)

10試合を1280×900で確認し、320/375pxでも横はみ出しなく表示する。
長いチーム名/ラベルは折返し、固定高さで切らない。画面は実運用実績の証跡ではない。

## 実Desktopの読取り調査

実際の3件はいずれもPythonランチャーへの`.lnk`であり、WebView2 native hostへの
直接リンクはなかった。Target/Arguments/WorkingDirectory/Icon/Descriptionと
リンクSHA、対応するworktree・launcher SHAは非公開のdry-run planへ保存した。

| 入口の区分 | 確認した方式 |
|---|---|
| 保存ビュー用の旧入口 | Python launcher、明示storeと固定SHA、Edge/Chrome app-mode |
| 保存ビュー用の通常ブラウザ入口 | Python launcher、明示storeと固定SHA、default-browser |
| 運用ビューの復旧用入口 | Python launcher、明示runtime、rounds/app-mode |

実リンク名、対象root、Target/Arguments、store/runtimeの実体は非公開の調査記録だけに保持する。

Active DesktopとユーザーDesktop、存在するOneDrive転送先、Common Desktopを確認した。
Start MenuとTaskBarのpinは別枠で読取り確認し、J1AI該当項目はなかった。
これらのpinを移行操作の対象にしない。

正式候補は**通常ブラウザ＋今回のworktreeのread-only server＋明示的なschema-v1
Champion JSON**とした。既存通常ブラウザ入口に起動/再表示ログがあり、新UIを実Chrome
headlessで表示確認した。専用WebView2の未実証・承認待ち事項を正式入口へ持ち込まない。
旧app-mode/native実装は削除していない。既存retrospective storeを変換せず、98件の
後日再現を前後対象日の一覧へ混入させない。今回の正式候補は対象日feedの表示であり、
旧retrospective表示と同じ画面へ接続するという意味ではない。

専用アイコンは[`web/assets/j1ai.svg`](../web/assets/j1ai.svg)と
[`j1ai.ico`](../web/assets/j1ai.ico)。自作のrect/polygonのみでフォントや外部素材を
使用せず、濃紺/白J1/水色AIに統一した。16/24/32/48/64/128/256pxを収録。
`scripts/build_dashboard_icon.py`は開発時だけPillowでSVGから再生成する。
Windows Shellの大/小アイコン抽出は確認済み。実Desktop上でのExplorer表示と
ダブルクリック確認は、未適用のためまだ実施していない。

## ユーザー確認後の移行手順（今回は未実行）

今回のworktree rootから実行する。`$pythonPath`は既存環境のpython.exeを明示する。
対応するpythonw.exeを同じディレクトリから使い、作業worktreeにvenvを複製しない。

```powershell
$pythonPath = (Resolve-Path '..\J1_League_AI\.venv\Scripts\python.exe').Path
$dataPath = Read-Host '承認済みChampion schema-v1 JSONの絶対パス'
$planPath = Join-Path $env:LOCALAPPDATA 'J1AI\j1ai-shortcut-plan.json'
& $pythonPath -B -m scripts.unify_dashboard_shortcut plan --python $pythonPath --data $dataPath --output $planPath
Get-Content -LiteralPath $planPath -Encoding UTF8
```

planはcreate-new。既存planを上書きせず別名を選ぶ。実調査で3件の所有markerと
launcher/Target/Arguments/working directoryを確認し、3件→`J1AI.lnk`のdry-runに
成功した。今回のplan実体はローカル監査領域に保持し、Desktopは変更していない。
以下のapplyは、planの対象・データ範囲をユーザーが最終確認した後だけ実行する。

```powershell
& $pythonPath -B -m scripts.unify_dashboard_shortcut apply --plan $planPath --confirm-desktop-migration
```

Targetは既存pythonw、Argumentsは今回のlauncherに`-B --data <明示JSON>
--python <既存python> --browser-mode default`、WorkingDirectoryは今回のworktree、
IconLocationは専用ICO、Descriptionは専用所有markerへ固定する。実際の引数配列は
planの`new_fields.Arguments`を確認する。デモには接続しない。別repositoryや所有不明の
リンクはignoredとして触れず、同名J1AI・入力/コード変更・所有marker不一致・reparse・
衝突はSTOP。別Desktopに跨がる変更など再検証が成立しないplanもSTOPする。

applyは入力/全リンクを再検証後、LOCALAPPDATA配下の新規`J1AI/ShortcutBackups/<ID>`に
元lnk bytes・target情報・SHA・新lnk原本を保存/fsync/readbackする。その後だけ新リンクを
exclusive-createし、COM読戻しが一致した場合に限り所有確認済み旧リンクを整理する。
失敗時はbackupと途中状態を保持し、他のリンクやprocessを削除しない。

```powershell
# <backup>はapplyが表示した専用ディレクトリ。信頼できる元backupだけを指定する。
& $pythonPath -B -m scripts.unify_dashboard_shortcut rollback --backup '<backup>'
```

rollbackは元/新リンク・backup SHAと所有を確認し、上書き衝突時はSTOPする。
途中失敗でも元リンクを復元してから、完全一致した自分の新リンクだけを除く。
current-userが管理するDesktopでの通常移行を想定しており、特権攻撃者や全ての
TOCTOU競合に対する原子的transactionを保証する実装ではない。移行中にリンクや
親ディレクトリを編集/移動しない。未知の途中状態を無断で再適用しない。

新入口はこのworktreeを参照するので、適用後はworktreeを削除/移動しない。
将来別rootへ配置する場合は新planと再確認が必要。旧installerは今回使用しない。

## 終了・再起動

ブラウザのタブを閉じても所有serverは残る。2回クリックしても同じrootのmutexが
二重serverを拒否し、既存起動中の案内を表示する。再度開く必要がある場合は、
今回のworktreeで次を実行し、その後新しいJ1AIリンクを開く。

```powershell
& $pythonPath -B -m scripts.launch_dashboard --stop
```

このeventは今回のrootのlauncherだけに作用する。旧runtime/storeのlauncherとは
所有scopeが異なるため、それらを止める操作は含めない。ブラウザを一括終了せず、
個人profile・既存タブを操作/削除せず、運用タスクも変更しない。

## 検証と残る事項

合成UI/データ/ブラウザ50件PASS。Chromeで直接URL、戻る/進む、キーボード、
table/headerのアクセシビリティ、DEMO保持、空/不正データ、10件密度、320/375px、
HIT/MISS/同率/丸めを確認した。Python関連333件PASS（警告もエラー扱い）。
一時Desktop内の実COMによるapply/rollback、所有不一致STOP、途中失敗復元、
reparse/衝突、icon形式/Shell抽出、実Windows mutexと所有serverの停止/再起動を含む。
実Desktop apply、実Desktopでのダブルクリック/Explorer目視は未実施。

テスト途中に、900pxで10行が収まらない密度、ブラウザ待機条件、旧HTTPError応答の
テスト側未closeを検出し修正した。モデル/取得処理の修正ではない。
既存nativeの初回は非canonicalなCLIパスで16件拒否され、canonicalパスで191件PASS。
後の実行で既存handle数検査1件の変動も観測したため、ログを区別して保存する。
native実装・閾値は変更せず、単独再実行は191件PASSとなった。handle数変動の原因は未確定である。
結果詳細は[検証集計](UI_ROUND_SUMMARY_VALIDATION.json)へ記録する。
専用WebView2の実運用GUI再試験・白画面問題の解決を今回の成果として認定しない。

NN研究のHISTORY/PREDICTIONはHOLD、Phase AはBLOCKED、Phase BはNOT_AUTHORIZED。
