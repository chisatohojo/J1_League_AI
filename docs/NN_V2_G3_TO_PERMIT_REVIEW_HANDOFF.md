# NN v2 — G3本審査への引継ぎ

事前審査の判定：`NN_V2_G3_PRE_REVIEW_READY`。
以下が不足するため、実permitは発行できず、G4開始も未承認である。
このP0/P1/P2は準備証拠の時点区分で、Mの規範scope優先度を変更するラベルではない。

| 区分 | 本審査に必要な事項 | 現在 |
|---|---|---|
| P0：許可前必須 | exact URL/subset/host/443/GET、目的A/B分離、UA/token、原本/規範/terms/source revision、鮮度・時計方針 | URL/識別子/E0/E1のみ成立。アクセス条件・freshness等はUNKNOWN |
| P0 | 承認者と具体的指示、開始/失効UTC、回数/bytes/頻度/timeout、保存先identity、STOP/rollback、code/config SHA、新しい一回限りの承認単位 | 設計のみ。ID/承認/保存先/時刻窓の実値なし |
| P0 | E3要否と方法/独立性/TLS/privacy、E2/E4のcapture、旧permit再利用禁止、G4開始を別scopeで記録 | 方針のみ。現に動くlive adapterなし |
| P1：動的隔離実証 | TLS拒否系、Job/子孫停止/escape、Owner SID/DACL/reparse、OS communication deny、範囲外write拒否 | 新adapterで未実証 |
| P1 | 複数process reservation競合、durable intent先行、crash/UNKNOWN_OUTCOME、raw/md/request/receipt/seal読戻し、部分保存/手動復旧 | pureモデルのみ。実FS/OSの原子性・永続性未実証 |
| P2：G4後の実観測 | 実E2送信開始/最終header/outcome、承認scopeに従う実E3、E4応答原本・HTTP/TLS結果・保存UTC | 未観測。初回sendより前の成立を要求しない |

P2を事前PASSとしない一方、未送信requestの実E2/E3がないことだけで本審査を永久に停止する循環は作らない。
事前に必要なのはP0とP1、およびP2を正確に記録し不成立ならSTOPする機構のqualificationである。
E3対象外を明示承認する場合もNOT_OBSERVED/UNVERIFIEDを残し、E2/E4から独立観測へ昇格させない。

## 次の承認順序

1. **隔離実証の範囲承認**：環境準備、必要ならVM/guestライセンス、設定変更の有無、専用root/endpoint、許可process、code/fixture SHA、故障注入、結果保持を固定する。現hostでの無断Job/ACL/Firewall試験はしない。
2. **不足原本・アクセス条件の審査**：operator/termsの正本提供や、限定bootstrap inspectionの根拠と別枠承認を確定する。現UNKNOWNを例外なしでALLOWにせず、B探索へ流用しない。
3. **G3本審査・新permit発行の明示承認**：P0/P1を満たした時点でexact subsetと新規予算/時刻窓/保存先を固定する。現設計JSONや合成fixtureを実permitへ書換えない。
4. **G4開始の明示承認**：permit・実装・入力・原本鮮度・全evidence機構を再照合し、その範囲だけを一度実行。次URL前に実観測・保存を監査する。

A1 refreshを含めた再取得は別の正確な承認が必要。旧G/Iの未使用枠は失効したまま復活させない。
A2/A3/A4の条件確認が成立してもB1/B2の探索を自動承認しない。外部正本取得や資料追加も今回の作業では0。

## STOPと復旧

robots/termsのDENYまたは未解決適用条件、URL/UA/revision不一致、403/429、TLS/timeout、不明完了、
SHA/ledger/readback矛盾、保存先/ownership不明、本番領域との混線では停止する。
attempt消費・不完全証拠・旧正式結果を保持し、予算巻戻し、再送、自動再開、lock強制回収、既存データ修復はしない。
本番との干渉があれば所有者・タスク時刻・変更前後SHAを分離し、原因を推測しない。

規範15 PASS/9 UNKNOWN、B/C/D各288 HOLD、HISTORY/PREDICTION HOLD、Phase A BLOCKED、Phase B NOT_AUTHORIZEDを維持。
性能比較、モデル実行、履歴admission、T0登録、将来予測保存は別工程である。
