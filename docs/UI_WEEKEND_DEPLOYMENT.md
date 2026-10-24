# 週末予想GUI：配備・実表示検証

判定：`J1AI_WEEKEND_GUI_DEPLOYED_VERIFIED`。2026-10-24の承認済みDesktop配備の記録。
今回の中断後の再開では、稼働中serverのStop・再起動・再配備を行っていない。
証跡SHAと集計は [検証台帳](UI_WEEKEND_DEPLOYMENT_VALIDATION.json)、切戻し条件は
[rollback手順](UI_WEEKEND_ROLLBACK.md) に記録する。

## Revisionと配備方法

| 用途 | Revision |
|---|---|
| 旧UI（変更せず保持） | `b57454857e779bd4b4a16d620decc9a125423cce` |
| オフライン検証済み週末UI | `c0b1652257977a7db67af73a2f4ceb5eb949e17a` |
| 配備した実行コード | `1b660f1843323c0f0325a3fde43836c9e2445c94` |

配備branchは `feature/ui-weekend-deployment`。候補版からの実行コード差分は
`scripts/launch_dashboard.py` の明示的な `--weekend-data` 転送だけで、対応する
`tests/test_weekend_deployment_launcher.py` を追加した。sidecarは `--data` と組で必須、
`--stop` との併用はIPCに触れる前に拒否する。未指定時の起動・停止契約は維持する。
既定ブラウザ方式を使用し、専用WebView2 GUIへ入口を戻していない。

旧worktreeへコピーせず、新しい配備専用worktreeをDesktopの `J1AI.lnk` が参照する。
絶対パス、shortcutの実引数、Owner SID、creation timeは非公開台帳に保持する。
本書追加後のcommitは記録用revisionであり、上記の配信中コードSHAは変わらない。
main、UI候補branch、旧UI、研究・週末batchのworktreeへmergeしていない。

## 表示専用snapshotとバックアップ

既存の検証済み公式revisionと保存済み日別Champion A batchを読み、独立した表示領域へ
schema v1の `champion_home.json` と `champion-weekend-display-v1` の `weekend.json` を配置した。
既存運用feedは上書きしていない。新規予測・公式取得・モデル呼出しはない。

組の相互binding・schema・source revision・保存値を確認し、stagingから新規release directoryへ
一括renameして公開した。manifest、fsync/readback、別領域のコピーを照合し、shortcutには
不変releaseの2ファイルを明示指定した。APIは起動時snapshotである。

- Pair manifest SHA：`d6cf2060f458c90f25ed0c84c6c58a3acb87da43b3802856511ab1e212abc8dc`
- Source revision：`5678e72ddb61a08cc88eea58fa8b3e8833aa3f4bc8c714a59e2bc9f54c9f033f`
- Source manifest SHA：`5e6d370c0eaeee8d0bca676c7d8dc3b75fabb12cf7c03c7372a34ddff9f37f3e`
- Source observation：`2026-10-23T22:00:22.614190+00:00`（10/24 07:00 JST）

旧コード、設定、shortcut、旧ディスクfeed、旧APIの実配信snapshotを323ファイルとして保全し、
別領域への独立コピーと全SHAの一致を配備前・再開後に確認した。旧ディスクfeedと旧APIは
異なっていたため、別々に保持する。旧画面を再現する切戻し案には旧API snapshotを指定する。
バックアップ読戻し成功は、切戻しを実行した意味ではない。

## 正式Stop・Desktop起動の既存証拠

中断前に所有権を確認して旧root専用の正式Stopを1回だけ実施した。
旧launcher/serverとwrapperの4 process終了、旧port解放、mutex/Stop event解放、
対象外serverの維持を確認した。Stop CLIの終了コードは0。

補助PowerShellスクリプトの読込みは既存execution policyに拒否されたが、正式Stopそのものは
既に成功していた。policyは変更していない。所有確認済みのStop完了ダイアログだけを閉じ、
helper失敗とStop成功を別receiptで保全した。強制kill・lock削除・Stop再送はしていない。

その後Desktopの `J1AI.lnk` から新版を1回起動した。再開時と最終監査でPIDだけでなく
creation time、実行ファイル、引数、Owner SID、session、親子関係、実kernel mutex/Event所有者、
listenerを再照合した。effective launcher PID **10872**、server PID **556**、
endpoint **http://127.0.0.1:51502/** が同一実体で稼働している。
PID/portはこの観測記録であり、将来の操作には再照合が必要。

## 実表示・ナビゲーション

既定Chromeの正確なlocalhost documentだけを対象にUI Automationで、週末一覧→前節→トップ→
週末一覧を確認した。既存Chromeを停止・再起動せず、個人profileを操作していない。
さらに新規の検証専用profileを用いたheadless Chromeで、同じ稼働serverの実データを検証した。
page requestは同じloopback originのGETだけを許可し、更新・予測APIは呼んでいない。
外部page request、JavaScript例外、console errorは検出されなかった。
これは全OS通信を遮断・監視したという主張ではない。

| JST対象日 | 公式日程行 | 保存済み表示 | 未保存表示 |
|---|---:|---:|---:|
| 2026-10-24（土） | 5 | 5 | 0 |
| 2026-10-25（日） | 5 | 0 | 5 |
| 合計 | 10 | 5 | 5 |

「週末の予想」、土日見出し、HOME/AWAY、fixture順序、JST kickoff、更新時刻、Champion A、
Research Models/ST2 SEALEDを確認した。保存済み5件は原保存確率と各バーの元値・AI PICKが一致。
未保存5件は「予測未作成」かつ確率なし。前節10件は旧API snapshotの内容と完全一致する。
1280×900、375px、320pxで横溢れなし。実配信画面のスクリーンショットを目視確認し、非公開で保持した。
検証専用Chromeは正常終了し、残存processなし。既定ブラウザとserverは維持した。

配備前のJUnitはPython **401 PASS**（warnings-as-errors）、Node/ブラウザの独立testcase
**70 PASS**、合計 **471 PASS / 0 FAIL / 0 skip**。中断後は証跡SHAとコードSHAを照合して
再利用し、再実行したと計上していない。再開後の追加実表示検証は別集計の **22 PASS**。
候補版の過去465 PASSも重ねて加算していない。

追加検証helperの初回は、既存の月日・曜日・JST表示に「年」を要求する誤ったassertionで停止した。
配信コードを変えず検証側を訂正し、元の失敗記録を残した。
また監査helperの空process一覧のJSON化を修正し、正常な「残存0件」を確認した。
これらを製品の不具合や未実施テストのPASSへ置き換えていない。

## 最終保護監査・制約

開始時baselineは61,069ファイル。許可済みのDesktop shortcutと旧launcher終了ログを区分し、
残り **61,067ファイルでSHA・file identity・size・mtime・creation差分0**。
access timeは読取りで変化するため比較対象外。モデル53 payload、既存19予測、公式原本、
NN v2・Weekend Batch成果物、main、26既存worktreeのHEAD/status、運用タスク2件の
定義・状態・実行履歴は不変。対象外serverのprocess identityも維持した。
新規配備領域のOwner/DACL、祖先を含むreparse不在、実行コード・pairの全SHAも再確認した。

07:00タスクの既存 `prediction_history_incomplete` 失敗は独立した運用事象として残す。
日曜予測に必要な履歴完了条件の不成立が記録されており、タスクの成功・修復・GUIとの因果関係を
推定しない。22:00タスクも変更・再実行せず、監査期間中の新たな実行はない。

ロールバック未実施。公式GET、モデルload/fit/推論、新規予測・原予測変更、本番feed上書き、
運用タスク変更/実行、Weekend Batch本番有効化、NN評価は0。
表示は07:00時点の固定snapshotであり、試合進行・日曜の未保存予測を自動補完しない。
次の表示更新は新しい検証済みpairの準備・承認が必要。単一directory renameの可視性を、
電源断耐性やあらゆるTOCTOUへの普遍的保証とはしない。
