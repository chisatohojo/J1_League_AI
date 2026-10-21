# 二段階オフライン証拠処理の契約

`two_stage_saved_byte_replay_v1` は、保存済みbytesの読取り・検証・新規領域への封印・解析を行う研究専用実装。実HTTP worker、通信permit、ネットワーク有効化スイッチ、CLI、Windowsタスク、運用collector、publication、将来予測器との接続を持たない。解析callbackは保存bytesを既存の固定strict parser・個別adapterへ渡すためのオフライン境界であり、実worker注入のAPIではない。共通備考分類候補は使用しない。

## Stage A

封印済みExpectedを信頼基点に、fixture行の完全一致、公式HTTPS URLとID、source revision、raw/metadata/request SHA、内部SHA・bytes、HTTP 200・完了状態、GET1回・retry/redirectなし・TLS/timeout記録、Content-Type、実UTCの対応を検証する。既存strict parserで大会・年度・節、公式identity、TeamMaster、日付・kickoff、規定時間結果、PK/延長分離、最終詳細状態を検証する。旧パイロット12件の完全見出しは別の封印済みfieldに保持されているため、元のfixture行を補正せずExpectedの見出しを照合する。

Source revisionは、元CSV全文SHA・行SHA・大会系列・承認済みcompleted revision・旧packet index SHAを結び付けた新しい再生用envelope。元metadataにrevision fieldを後付けしない。公式原本の取得UTCと、今回の再生・解析UTCを区別する。過去のTLS方針や一度限りのGET記録の整合を検証するものであり、現在のネットワーク接続を実証するものではない。

identity・結果・証拠の検証に失敗した場合はSTOP。strict parserが事実欄を検証し終えた後、既知の「未分類時刻注記」理由だけでHOLDになった場合は、その完全なstrict結果を保持してStage Bへ渡せる。未知HTML等によりidentity・結果を検証できないHOLDは、この例外へ入れない。

## Stage Bと隔離

Stage A原本bundleを全SHAで読み戻し、そのbytesだけを解析する。strict結果がStage Aと異なる場合、または証拠SHA・identity・結果等の不整合を示す場合はSTOP。既知形式は固定契約に合格したときだけPASS。UNKNOWN_FORMATや未分類時刻注記はHOLDで隔離し、通常試合へ再分類しない。時刻注記によるstrict HOLDをStage BがPASSへ変えることも禁止する。

隔離packetはidentity・namespace・公式URL/ID・source revision・元packet SHA・実取得UTC、Stage Aの結果参照、Stage B解析と理由、未確認分類、原本bundleとseal参照、receipt参照を持つ。`packet.json`のSHAは自己参照を避けるためsealとreceiptに分離する。全構成ファイルのexclusive-create、flush、file fsync、readback、SHA検証、seal、receiptの保存・再照合が完了してから次の入力へ進む。

未完了のsource/quarantine folder、receipt欠落、未集計の隔離packetは全件PASSとして集計できない。保存失敗はSTOP。通常例外時には可能な範囲で失敗原本とSTOP理由を別bundleへ保持し、保存確認ができなければその旨を明示する。異常終了でreceiptが残らない場合も、開始claimが残るため同じrunの再実行・無断再開は拒否する。元のraw・metadata・正式停止記録は更新しない。

## 状態と集計

`source_acquired`、`source_integrity_verified`はStage Aで封印・読戻しが完了した原本数、`detail_PASS/HOLD`はStage Bのreceiptまで確定した審査数。Stage Bの致命的不整合で停止したときも、完了済みStage A原本と審査済み件数を混同しない。部分保存で正確な全数照合ができなければ、`counts_complete_and_verified=false`としPASS/HOLD数を未確定にする。

| packet field | 既知詳細PASS | 未知備考HOLD |
|---|---|---|
| source_acquired | true | true |
| source_integrity_verified | true | true |
| detail_analysis_status | PASS | HOLD |
| quarantine_status | false | true |
| timing_evidence_status | HOLD_B_C_D | HOLD_B_C_D |
| history_admission_status | false | false |

隔離packetを除外して「完全な履歴」を作る機能はない。集計は全receipt・seal・packetを読み、source/review/quarantineの集合も照合する。history admissionを要求する関数は常に拒否する。Aの最終詳細PASSは、Bの実際の開始/中断/再開/完了/結果利用可能時刻、Cの当初日程・変更告知、Dの予測cutoffまでの情報取得証明を代替しない。

## 合成境界と実取得への未接続

SyntheticBudgetは架空の開始/終了時刻・本文量・結果ラベルを検査するだけで、時計を待つ、接続する、再試行する機能を持たない。仮想clockを保存済み公式packetへ付加することを拒否する。通信異常・HTTP 403/429・TLS/アクセス制限・timeout・不明完了・redirect・上限・重複・deadline/rate違反は合成でも全体STOP。実タスクやcollectorへ合成fixtureを渡す接続点はない。

ファイルfsyncとreadbackはオフライン実証の対象。Windowsのdirectory fsync、電源断、敵対的プロセスとのpath競合、実workerの所有権・ACL・終了/cleanup、実HTTP receiptの統合までは実証していない。次回実取得へ統合する場合、これらの監査と新しい固定対象permit・取得許可が別途必要。今回の実装に実通信の入口を追加していない。
