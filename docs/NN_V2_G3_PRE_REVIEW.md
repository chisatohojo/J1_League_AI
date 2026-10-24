# NN v2 Phase 2.5P — G3事前審査

判定：`NN_V2_G3_PRE_REVIEW_READY`。
基準：G2 `665f0144cffa3b1b569cabf79e41394de9f3914d`。
branch：`feature/nn-v2-g3-pre-review`。
これは6 URL審査表・契約・UNKNOWN分類・隔離実証計画の準備完了で、permit発行可能という判定ではない。
**6 URLすべての実permitはHOLD、通信authorityは0。** G3発行・更新・有効化、G4通信は行っていない。

## 参照と変更範囲

G1採用manifest/schema、G2の6 request/E1、Mの固定scope/9 UNKNOWN、旧G/Iの原本・台帳をSHA照合した。
正式UAは `J1AI-Research-Timing-Pilot/1.0`、robots tokenは `Research-Timing-Pilot`。
G1の採用、G2のoffline E0/E1が成立したことを、旧Mの当時未承認という記録へ遡及反映しない。
新実装は [pre_review.py](../research/nn_v2/phase2_5P/pre_review.py) のpureな審査・状態モデルだけ。
本番permitの生成・受理・保存API、実transport、Windows Job/ACLの操作入口は持たない。

## URLごとの審査

詳細・原本SHA・取得UTC・G2 E1 SHA・scope・上限案・不足事項は
[G3_PRE_REVIEW_MATRIX.json](../research/nn_v2/phase2_5P/G3_PRE_REVIEW_MATRIX.json) を正本とする。

| ID・完全URL | 取得目的 | 保存済み原本 | robots／terms | 現判断 |
|---|---|---|---|---|
| A1 `https://www.jleague.jp/robots.txt` | 旧原本の鮮度検討。refreshは自動実行しない | 646 bytes、2026-10-23T09:46:47.645062+00:00 | 固定contextで条件付きALLOW／UNKNOWN | HOLD |
| A2 `https://aboutj.jleague.jp/robots.txt` | host固有の初回条件確認 | 検証済み台帳に未取得 | UNKNOWN／UNKNOWN | HOLD |
| A3 `https://www.jleague.jp/general/kiyaku/` | 適用規約・自動取得条件 | 同上 | 固定A1 contextで条件付きALLOW／UNKNOWN | HOLD |
| A4 `https://www.jleague.jp/general/copyright/` | 著作権・保存・引用・再利用条件 | 同上 | 同上 | HOLD |
| B1 `https://www.jleague.jp/j1/news/` | 条件確定後のニュース入口探索 | 同上 | 同上 | HOLD |
| B2 `https://aboutj.jleague.jp/corporate/pressrelease/` | 条件確定後のプレス入口探索 | 同上 | UNKNOWN／UNKNOWN | HOLD |

「未取得」は検証済みG/I条件確認registryでの状態で、個人disk全域に資料が存在しないとの主張ではない。
各URLはHTTPS・443・厳密なpath/queryなし・予定method GET、redirect/retry/parallel=0。
同じhostでも別path、query、index/article追加は承認範囲へ自動追加しない。

審査用の上限案は各URL1 request。A1/A2は64 KiB、A3/A4は1 MiB、B1/B2は2 MiB。
headers 32 KiB、完了後間隔5秒、socket10秒、parent12秒、cleanup2秒、global120秒を単一URL合成審査の既存条件として固定した。
これは新予算ではない。将来の対象subset・合計枠・順序・時刻・保存先は別審査で確定する。
Aの条件確認とBの探索を混ぜず、A1再取得も別途明示承認を要求する。

A1は後日保存された現実の原本だが、現在の公開状態や自動取得許可を保証しない。
approved TTLは未定。経過時間を計算しただけでfresh／staleを自動認定せず、Cache-Controlも許諾や任意期間の使用権と扱わない。
保存先は新規exclusive research rootの設計aliasだけで、実取得先・Owner SID/DACL・保存上限・ledgerは未承認。
取得しない代替は、封印原本のoffline解析、利用者／運営者が提供する正本のprovenance確認である。
新しく資料を得ても、過去の送信UAや過去PITを遡及立証できない。

## robotsと条件確認の循環を避ける

robots条件付きALLOWとterms上の許諾を同一視しない。wwwの資料をaboutjへ流用しない。
通常のpermitではrobots DENY/判断不能、terms違反/判断不能を拒否する。
未取得robots・規約の確認が必要なら、既知の厳しい条件、運営主体、資料の適用範囲、限定bootstrapの根拠を独立に審査する。
現在そのpolicyは未承認で、コードにもUNKNOWNを通す例外を実装していない。
初回条件確認を認める場合は別の具体的な条件確認承認として記録し、B探索へ拡張しない。根拠がなければHOLD。

## 9 UNKNOWNの分類

[G3_UNKNOWN_CLASSIFICATION.json](../research/nn_v2/phase2_5P/G3_UNKNOWN_CLASSIFICATION.json) は正式ID・元定義・元recordを保持し、複数カテゴリを付す。

| 正式ID | 主な不足 | 解消経路 |
|---|---|---|
| agent_grammar | 実UA・適用scope・独立観測 | G1/G2は採用/E1部分だけ解消。実adapter qualificationとG4実記録 |
| rule_grammar | ABNF・公式例・recoveryの解釈 | offline検討＋不足正本/clarification |
| longest_rule | RFC/Google順位解釈 | offline検討＋不足正本。固定4 pathの一致0とは区別 |
| reserved_octets | octet処理・参照仕様不足 | offline検討＋必要正本。unquote-allにしない |
| query | 規範subset・URL scope | offline検討＋正本。現6 URLにqueryを追加しない |
| encoding_errors | 不正原本の解釈・保存 | offline/parser検討＋正本＋保存境界実証 |
| parse_limits | parser容量・資源/保存 | offline設計＋正本＋上限変更時の隔離実証 |
| standard_examples | 公式例の不整合 | offline検討＋clarification。説明を創作しない |
| sealed_A1_replay | 実UA、terms、scope、保存、独立観測 | offline証拠＋追加正本/条件確認＋隔離実証＋承認後の実観測 |

6分類は規範/robots、実UA、terms、許可範囲、保存/監査、独立証拠。termsやOS隔離等の横断不足を新しい「第10の規範UNKNOWN」にしない。
各項目に①offlineで検討可能な部分、②追加正本/条件確認、③限定実環境試験の経路を分離した。
**15 PASS／9 UNKNOWNを維持、今回完全解消0。** Mのscope優先度P0/P1/P2と、本工程の証拠準備P0/P1/P2は別軸。

## permit契約とattempt

[G3_PERMIT_CONTRACT.json](../research/nn_v2/phase2_5P/G3_PERMIT_CONTRACT.json) は `DESIGN_NOT_PERMIT`。
実permit ID・承認者・承認日時は設定していない。将来の必須項目はexact URL、method、期限、承認者、UA/token、
robots/terms revision、code/config/input SHA、保存先identity、requests/bytes上限、ledger、STOP/rollback、E3要否など。
permit本体はimmutableとし、使用済み状態と結果は別append-only ledgerへの参照で管理する。承認bytesを書き換えて消費状態を表さない。

状態モデルはCREATED→RESERVED→STARTED→SENT→COMPLETED、失敗終端はREJECTED/ABORTED/UNKNOWN_OUTCOME。
旧run消費markerはrun reservation、旧consumed-intentはslot予約、旧connection-startedはSTARTED相当として対応を整理しただけで、旧状態名や記録は変更しない。
RESERVEDで一度消費し、以後ABORTEDでも返却しない。STARTED以後の不確定終了はUNKNOWN_OUTCOMEへ進み、無断再送しない。
予約したrequest hashは別permitでも再予約できない。これも当該メモリledger内の論理検査で、globalな永続registryの実証ではない。
SENTはclient側進捗でserver到達証明ではない。COMPLETEDの実用化には全証拠のfsync/readback完了が必要。

今回のモデルはbyte列・外部head SHA・event hash-chain・revision CAS・単一permit消費を純粋関数で確認するだけ。
同時reservationは同じrevisionを使う二つの論理操作で競合を模擬し、実process競合や原子的disk操作とは呼ばない。
hashは署名・承認者認証・時計真正性ではない。将来は所有されたledgerと信頼できるhead SHA・明示承認との照合が必要。
crash後はownershipと証拠を手動審査し、lock強制回収・staging削除・自動再推論/再送をしない。

## 検証と保護

今回の最終試験は新規95 PASS（明示negative-control85件）＋回帰1,268 PASS、合計1,363 PASS。
FAIL/ERROR/skip/deselectは0、warnings-as-errors。改良前94 PASSと過去G2の108+1,160 PASSは別証跡として保持する。
22種の要求異常を含むnegative-control、合成TLS/Job escape/ACL/OS不明、CAS/crash/改変、E2/E3/E4誤昇格を検証した。
G2 MemorySinkを補助検証に再利用し、通信やE4原本を生成していない。
専用Python processのapplication guardは通信・DNS・socket生成・外部process・実model・範囲外writeを拒否する。
**今回はsocket/DNS/processのprobe自体も実行していない。** 過去G2の3遮断確認を今回実行したと数えない。
OS隔離・TLS・Job・ACL・永続化の動的実証は0である。

開始baselineは75,265ファイル・31既存worktree。モデル53 payload、既存19予測、288詳細原本、旧permit/evidence、
Champion/Weekend/GUI、live server、定時2タスク、mainを照合する。
最終実績は [VALIDATION.json](../research/nn_v2/phase2_5P/VALIDATION.json) とSHA台帳を参照。
研究HTTP/DNS/socket、実transport、新permit、モデル実行、Job子起動、ACL/Firewall/VM設定変更は0。
通常Git pushだけは承認された成果物保存として分離する。

B/C/D各288 HOLD、HISTORY/PREDICTION HOLD、Phase A BLOCKED、Phase B NOT_AUTHORIZEDを維持。
次の承認は [動的実証計画](NN_V2_G3_DYNAMIC_PROOF_PLAN.md) と [本審査引継ぎ](NN_V2_G3_TO_PERMIT_REVIEW_HANDOFF.md) を参照する。
