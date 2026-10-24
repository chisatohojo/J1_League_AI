# NN v2 Phase 2.5R — アクセス条件評価と停止後の引継ぎ

最終ゲート：`NN_V2_2_5R_FETCH_BLOCKED`。送信前のR-1/R-2条件を立証できなかったため、A3/A4ともGETを送らず終了した。取得を試みて失敗した状態や、原本を保存できた状態とは区別する。

| 項目 | A3 | A4 |
|---|---|---|
| URL | `https://www.jleague.jp/general/kiyaku/` | `https://www.jleague.jp/general/copyright/` |
| 送信・実transport呼出し | なし | なし |
| 消費attempt | 0 | 0 |
| HTTP status・Content-Type・Content-Length | 未観測 | 未観測 |
| 受信byte数 | 0 | 0 |
| raw・保存先・raw SHA・readback SHA | 原本なし・null | 原本なし・null |
| terms | UNKNOWN | UNKNOWN |

原本がないため空のrawを作成せず、空bytesのhashを取得原本のhashとして報告しない。rawはGitへ追加していない。台帳と根拠は [FETCH_EVIDENCE.json](../research/nn_v2/phase2_5R/FETCH_EVIDENCE.json)、[TERMS_REVIEW.json](../research/nn_v2/phase2_5R/TERMS_REVIEW.json)、[取得前審査](NN_V2_PHASE_2_5R_FETCH_PRECHECK.md) に保持した。

## terms 15項目

自動アクセス、robotsとの関係、個人的・非商用利用、研究利用、収集、保存、複製・加工、二次利用、再配布・公開、取得頻度、サーバー負荷、禁止事項、許諾申請、他ページへの適用、更新日・適用時点は、A3/A4いずれもUNKNOWN。根拠箇所・取得時刻はnullであり、過去HTMLのfooterリンクやURL名を条文の代用にしない。

禁止を確認したための停止ではなく、現在のrobots根拠と実行境界を送信前に立証できないための停止である。禁止の未発見を許諾と扱わず、条文のない状態で法的判断も行わない。原本を得た後、解釈が必要な条件だけ個別の専門確認事項として整理する。

## robotsとE0〜E4

固定A1原本と採用識別子に対するA3/A4のpath再評価は条件付きALLOW。ただし現在性はUNKNOWNで、R-1をPASSにしていない。保存済みRFC段落と現在性の不足を新しいR評価へ記録し、過去の規範15 PASS／9 UNKNOWNを変更していない。A2/B2はUNKNOWN、B1の取得も未承認のままである。

| 証拠レベル | 今回の状態 |
|---|---|
| E0 | G1 manifest・今回の承認scope・予定設定を照合 |
| E1 | G2の既存記録を保持。Rはオフライン予定request仕様のみで、送信直前の実記録なし |
| E2 | NOT_OBSERVED。クライアント実送信なし |
| E3 | UNKNOWN。独立観測なし |
| E4 | NOT_ACQUIRED。HTTP応答・新規rawなし |

合成responseのhash検証が成功しても実E2/E3/E4へ昇格しない。過去Gの1 GET等は過去の承認済み通信であり、今回のHTTP/DNS/socket観測0に混ぜない。

## G3本審査に残る条件

| 優先度 | 必要事項 | 今回の到達点 |
|---|---|---|
| P0 | robotsの現在性・限定条件確認の根拠、適用規約原本・保存加工等のscope、実保存先、proxy・時計方針 | 保存原本・不足の出典を確認。現在性・規約本文は未解消 |
| P1 | 今回の5秒／15秒条件とUA・scopeを守る実client、運用write拒否、隔離・所有者境界、実attemptの永続化・競合・crash qualification | 合成の拒否・ローカルfsync/readback・再open時重複拒否だけ確認 |
| P2 | 承認された実通信でのE2/E3/E4、実TLS・送信結果・保存時刻 | 未観測。初回send前の実観測を循環的に要求しないが、観測機構のqualificationは事前に必要 |

今回の限定取得承認は存在するが、付された必須条件が成立していない。G3 permit本発行・G4・研究データ収集・モデル実行へ進まない。6 URLのterms UNKNOWN、G3 permit HOLD、B/C/D・HISTORY/PREDICTION HOLD、Phase A BLOCKED、Phase B NOT_AUTHORIZEDを維持する。

## 次に必要な個別承認・証拠

1. **A1の現行性確認または使用根拠**：今回の2 URLにはA1が含まれない。A1を限定取得する場合はexact URL、1回限りのmethod・上限・timeout・保存・停止条件を別承認で固定する。取得しない場合は、既存A1を今回の限定条件確認に使用できる根拠を具体的に審査する。UNKNOWNを一律に通す例外にはしない。
2. **実行経路と保存境界のqualification**：既存構成のまま運用write拒否、5秒connect／15秒read、TLS/hostname検証、proxy方針、exact request captureと重複拒否を満たす証拠を示す。構成変更が必要なら、今回の指示で禁止されたFirewall／ACL／Job／VMの操作範囲を新たに承認する。自動的にVM構築を必須と決めない。
3. **A3/A4の新しい単一セッション**：上記条件を満たしてから、対象subset、試行上限、順序、保存先と時刻範囲を固定して改めて承認する。今回の未使用枠や旧G/I permitを再利用しない。原本を利用者／運営者から提供する方法も代替候補となる。

Git push／fetch／pull／ls-remoteは今回0件。ローカルcommitだけを行い、研究raw・秘密情報・環境のSIDやproxy URLをGitへ含めない。今回の完了点は、未送信でのBLOCKED判定、証拠の保存、オフライン検証と保護監査までである。
