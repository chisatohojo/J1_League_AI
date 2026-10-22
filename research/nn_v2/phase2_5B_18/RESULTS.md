# Phase 2.5B-18 残り109件の二段階公式詳細取得

正式判定：**DETAIL_EVIDENCE_COLLECTION_COMPLETE_RESEARCH_ONLY**。[正式状態](readiness.json)、[独立監査](collection-summary.json)。

新規通信の上限は固定109 URL・各1 GETである。保存済み179件とのoverlap、URL/ID衝突、元288件の集合、実anchor、固定source・年度見出し・TeamMaster・90分/PK/延長を事前照合した。実行した詳細GET上限は109、HTTP200原本は109、Stage A封印は109。新規robots GETは0で、保存済みアクセス証拠を各バッチ前に再検証した。追加告知・日程・indexや既取得179件には接続していない。

| バッチ | GET | 新v5 PASS | 隔離HOLD | 累積確定 |
|---|---:|---:|---:|---:|
| 1 | 12 | 10 | 2 | 12 |
| 2 | 12 | 12 | 0 | 24 |
| 3 | 12 | 11 | 1 | 36 |
| 4 | 12 | 12 | 0 | 48 |
| 5 | 12 | 11 | 1 | 60 |
| 6 | 12 | 12 | 0 | 72 |
| 7 | 12 | 12 | 0 | 84 |
| 8 | 12 | 11 | 1 | 96 |
| 9 | 12 | 11 | 1 | 108 |
| 10 | 1 | 1 | 0 | 109 |

新109件の独立集計は **103 PASS／6隔離HOLD**。隔離packet・seal・receipt確定は6件、隔離確定後に別URLのGET完了を確認したものは6件。原本を隔離して解析HOLD・admission=falseを保持し、規則追加・自動PASS化は0。末尾隔離には後続URLがないため継続件数へ加算しない。未確認備考は別の独立オフラインレビューへ送る。[隔離](quarantine-summary.json)。

累計取得は**288件、未取得0件**。既存179件は、当時のv5正式取得解析176 PASS/3 HOLDと、後日のv6独立解析179 PASS/0 HOLDを区別して保持した。今回もv5だけで新規取得を解析し、v6をworker/実取得へ接続していない。既存179件の独立レビュー済み結果と新v5の集計ではPASS282／未解決HOLD6。v5取得時ビューだけの累積はPASS279／HOLD9であり、これらを混同しない。原本・旧隔離3件・正式記録は保持した。

10バッチの境界台帳・seal・receiptを独立再読込みし、最終通信台帳との前方一致を検証した。worker/kernel PID/親PID・image SHA・Job所属・終了、request/response UTC、TLS、raw/metadata/request・permit SHA、90分とPK/延長、隔離保存順序、次URLと次バッチの開始順序を照合した。通信間隔の最小は5.200099秒、本文合計は13,343,782 bytes。独立監査エラー件数は0。詳細はローカルに保持する。[バッチ](batch-summary.json)、[実装](implementation-sha256.json)、[permit/入力SHA](input-and-permit-sha256.json)。

今回新しく実行した通信前テストは**81 PASS、failure0/error0/skip0**。109件完了/110件目拒否、最終1件と末尾隔離、複数HOLD後の継続、各種STOP、境界・前方一致、Windows所有権/ACL/reparse/cleanup、二重実行/旧permit/既取得拒否を検証した。179件は新統合層のローカルworkerで再生し、v5全semantic field不変・176 PASS/3 HOLD、v6は別のオフライン処理で179 PASS/0 HOLDを確認した。過去4件の正式HOLDと隔離も再現した。旧935件・後処理9件・v6用54件の証跡はSHA/元JUnit時刻で再利用し、今回再実行したとは記録しない。[テスト](test-results.json)。

ローカル再生自体は完了した後、監査出力の旧ファイル名参照が失敗した。保存済み179 receiptから監査を続け、結果本体と集計の異なるschemaを対応するfieldごとに照合した。元の失敗script/成果物を保持し、179 workerを再実行せず、旧HOLDや備考規則を緩和していない。この修正は通信前に完了した。

保護baseline 36,143ファイル、model sealと53 payload、既存179原本、旧parser/v5/v6/個別rule、保存14予測・再現98件、固定source/publication・運用runtime/タスク定義・main/他worktreeを照合した。保護判定はPASS、今回の運用出力変化は0。前工程の22:00タスク失敗と07:00の独立照合済み更新、過去未帰属11件を区別して引き継ぎ、タスクを修復・再実行・変更・停止していない。[保護](protection-summary.json)。

全実HTTP原本・metadata/request・worker/Stage A/B/隔離receipt・10累積台帳・入力/permit/実装・最終監査・テスト証跡を別ドライブへbackupし、ZIP CRC・全entry SHA・独立展開後SHA・読戻しを検証した。再生成可能な合成テストscratchはローカルに保持したままarchive対象外とし、テストsource/JUnit、実OS179再生と過去4隔離の証跡は収録した。実HTTP証拠は除外していない。公開成果物も別途backup/復元照合した。raw/metadata・備考全文・氏名・個人パス・モデルartifactは公開しない。[backup](backup-verification.json)。

**HISTORY／PREDICTION：HOLD。Phase A：BLOCKED。Phase B：NOT_AUTHORIZED。** 詳細Aの収集/審査と、実開始・中断・再開・完了・結果利用可能時刻B、当初日程/変更告知C、予測cutoffでの取得証明Dは別判定とする。実fit・性能評価・実確率計算・T0・対象登録・将来予測保存はすべて0。履歴event admissionと予測器へ未接続。[次工程](next-stage.json)、[仕様と未実証範囲](SPEC.md)。
