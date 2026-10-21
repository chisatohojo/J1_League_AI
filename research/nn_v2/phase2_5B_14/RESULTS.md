# Phase 2.5B-14 実HTTP少数件パイロット

判定：**TWO_STAGE_REAL_HTTP_SMALL_PILOT_VERIFIED_RESEARCH_ONLY**。未取得172件の固定順序先頭3件を、独立した実HTTP worker・permitで取得し、Stage A封印、Stage B審査、receipt確定、Windows Job終了まで確認した。**詳細3 GET / HTTP 200が3件 / 3 PASS / 0 HOLD**。累計119/288件取得、未取得169件。残りの取得許可には拡張しない。[取得集計](communication-summary.json)、[状態集計](stage-summary.json)。

開始branch `feature/nn-research-v1`、HEAD `f585a9fc7460d68f57e2332024d7c1f2ec8bd5b5`、study `nn_v2_residual_20261020_01`。モデルは`TRAINED_AND_SEALED_RESEARCH_ONLY`。model seal・全53 payload・原本・既存実装・正式停止記録・入力SHA・22,519保護ファイルを照合した。[入力SHA](input-sha256.json)。

通信前に保存済み116件を新統合層のローカルworker経由で再生し、116 PASS、v5の全semantic field不変を確認した。過去4件は当時の旧契約でHOLDを完全再現し、隔離packet/seal/receiptの読戻し後に後続正常原本へ進行した。旧正式HOLD記録を変更していない。新56ケース＋既存742ケースの合計 **798 PASS / failure0 / error0 / skip0、warnings-as-errors**。公式へのテスト通信0。実Windows process・ACL/reparse/競合・crash/cleanupの46ケースも再実行し、45領域703ファイルの故障証拠を保存した。[互換性](compatibility-summary.json)、[テスト](synthetic-test-results.json)。

初期のテストでは巨大bytes値から生成されたテスト名がWindows path長制限に触れ、2件のsetup errorとなった。明示的な短いparameter IDへ修正した。また初回の116件再生後の監査書出しで参照パス誤りが見つかった。初期出力を保持し、別runner・新領域で116件と4件を再検証した。これらは通信開始前の開発不備で、旧原本や正式停止記録を修正して合格にしたものではない。最終798件が合格してからpermitを封印した。

保存済みrobots証拠は24時間の鮮度条件を超えていたため、独立permitで **1 GET / HTTP 404 / 905 bytes** を取得した。保存済みの正確なrobots URLだけを使い、本文SHAは旧404と一致。404の意味はそのURLに公開robots規則が確認できなかったことに限定し、サイト全体の許可証明とは扱わない。保存済みprotocol上、別の既知の厳しい適用条件は見つからなかった。日程・告知・indexへアクセスしていない。

実取得は2026-10-21の12:11:16〜12:11:33 UTC。robots1件と詳細3件の各request/response UTC、raw/metadata/request/receipt SHA、PID/task/permit結合、TLS証明書・hostname検証、TLSv1.2、本文量を照合した。詳細本文合計373,401 bytes、最大126,982 bytes。通信完了→次開始は全3間隔で5秒以上。retry0、redirect0、parallel0、無断再開0。worker内socket/wall期限10秒、親worker12秒、全体外側240秒、cleanup2秒を固定した。全4 workerと外側親の所有Jobは終了時process0。[通信receipt集計](communication-summary.json)、[所有権・保存](process-storage-summary.json)。

新workerと統合層のコード、選定3件、期待値、元台帳・source revision、parser/v5/rule、入力、別々のdetail/robots permit、launcherを通信前にSHA封印した。permit共有消費claimと各URLのintentを接続前に保存し、既取得116 URLや同一permitの再使用を拒否する。Stage A/Bは既存の封印byte検証器を変更せず利用した。旧byte検証器内のnetwork counter 0はその検証器自身の副作用を示し、実通信件数は外側receiptで詳細3・robots1と別記する。[仕様](SPEC.md)、[実装SHA](implementation-sha256.json)。

3件とも最終詳細のidentity・大会/年度/節・TeamMaster・日時・90分結果・PK/延長分離・備考審査がPASSし、元CSVのPK/延長数値も一致した。Stage Bは封印済み原本だけを入力とし、receipt確定後だけ次URLへ進んだ。**実HTTPでの未知備考隔離はNOT_OBSERVED**。過去4件のオフライン隔離再現を実HTTP隔離実例として数えない。最終詳細AのPASSと、開始/中断/再開/結果利用可能時刻B、当初日程/変更告知C、予測cutoffでの取得証明Dを分離し、B〜Dは全てHOLD、history admissionはfalse。

元288件＝取得済み119件＋未取得169件、URL重複/overlap/ID衝突0。元172件台帳と旧完全計画は不変。169件の新しいローカル計画は未承認・通信無効で保存し、公開はSHAだけ。今回3件終了後に取得を終了し、他URLへ進んでいない。[集合照合](fixed-set-verification.json)。

保護対象22,519ファイルと53 model payloadは不変。新しい運用出力差分0、タスク時間帯との重複なし。07:00/22:00タスク定義2件、main、他worktree2件も不変。過去11件の未帰属差分と、前工程の07:00タスクで根拠確認済み10件は区別して保持し、今回の研究変更や通常更新と推測していない。[保護監査](protection-verification.json)、[旧正式記録](old-formal-records-verification.json)。

新規原本・metadata/request・通信receipt・Stage A/B・過去隔離再現・合成故障証拠・実装/入力/出力SHAを別ドライブbackupへ保存し、ZIP CRC・全payload SHA・独立展開・読戻しを検証した。Raw、metadata、氏名、個人パス、モデルは公開していない。[backup](backup-verification.json)。

Windows ACL変更自体の原子的禁止、全filesystem/特権的競合に対する普遍的保証、電源断時のdirectory永続性、他のページや長時間取得、実HTTP隔離例は未実証。今回の合格は固定3件に限る。[未実証事項](UNPROVEN.md)。残り169件は新しい対象集合・executor・permitと別承認が必要。[次工程](next-stage.json)。

**HISTORY / PREDICTION：HOLD**。実fit0、性能評価0、実試合確率計算0、T0登録0、対象登録0、将来予測保存0。共通備考分類候補・運用collector・予測器へ未接続。Phase A：BLOCKED、Phase B：NOT_AUTHORIZED。
