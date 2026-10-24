# NN v2 Phase 2.5Q — P0からG3本審査への引継ぎ

証拠整理ゲートは `NN_V2_P0_ACCESS_EVIDENCE_REVIEW_READY`。6 URLの実permitは全件HOLD。G3本審査・permit発行・G4通信はこの工程で実施していない。

## G3へ進めない理由

| 区分 | 不足 | 最小限の次工程 | 解消後も残る制約 |
|---|---|---|---|
| P0-A | 正式9 UNKNOWNの解釈問題、B入口選定理由 | 保存済み仕様・公式例・試合資料を比較し、適用subsetと残る不足を記録 | 一般規範PASSやアクセス許可にはならない |
| P0-B | wwwの適用規約・著作権・研究自動取得・保存加工条件 | A3/A4の出典・版・UTC・適用対象付き正本提供を優先。不可なら限定条件確認の根拠を審査 | 条文があってもscopeと鮮度が必要。aboutjへ流用不可 |
| P0-B | A1の現在有効性・承認TTL・時計方針 | 旧原本の使用可能性を先に審査し、必要ならA1更新だけを別候補へ | 更新だけではtermsや実UAの証明にならない |
| P0-B | aboutjの必要性・運営者・robots・適用条件 | www先行なら延期。採用時だけA2と正本提供の必要性を具体化 | A2取得後もB2探索は未承認。規約URL追加も別審査 |
| P0 | 新しいexact subset、承認者、時刻窓、予算、保存先identity、E3方針、停止・復旧条件 | P0/P1成立後にG3本審査の明示承認を得る | 旧G/I permit・合成fixture・設計JSONは再利用不可 |
| P1 | TLS／OS通信遮断／Job／Owner SID・DACL／reparse／保存境界の実証 | 環境・endpoint・fixture/code SHA・設定変更・試験対象を固定した別承認の隔離試験 | 現ホストでの無断設定変更をしない。実サイトの観測は別 |
| P1 | 永続attempt・競合・crash・readback・UNKNOWN_OUTCOME | 別承認環境でfsync、複数process競合、部分保存、手動復旧を実証 | pureモデルのPASSは永続性・OS原子性を保証しない |
| P2 | 実E2・E3・E4 | qualified実装と新permitを照合し、G4開始の別承認後に限定観測 | 事前PASSにしない。過去UAや過去PITを遡及立証しない |

P2の実観測が初回send前にないことだけで循環停止させない。P0/P1では観測機構・E3要否・独立性・TLS/privacy方針をqualificationし、実送信時の証拠をP2として記録する。E3不要の明示承認がある場合もNOT_OBSERVED／UNVERIFIEDを残す。

## 次に提示する承認単位

最初の候補は**A3/A4の適用条件正本の確認**。まず、運営者／利用者提供の保存原本で代替できるかを確認する。通信が必要なら、通常permitにおけるrobots／terms UNKNOWN拒否を維持したまま、条件確認のbootstrap根拠・適用範囲を独立に審査する。

将来の限定取得案は以下を具体化してから提示する。これは未承認の候補であり、この文書により取得枠は生じない。

- exact URL：A3 `https://www.jleague.jp/general/kiyaku/` とA4 `https://www.jleague.jp/general/copyright/` の必要なsubset。
- 上限案：各1 GET、最大合計2 GET。既存Pのbody上限案は各1 MiB、headers 32 KiB。query追加・redirect・retry・parallel・定期取得なし。
- 順序・時刻：条件確認だけを目的とし、開始・失効UTC、総時間・完了後間隔・STOP条件を新たな承認で固定する。旧予算は流用しない。
- 識別子：G1採用UA/tokenをexact bytesで固定。最終header記録とE1/E2/E3の区別を維持する。
- 保存：独立rootの実path、所有者・DACL・reparse、bytes上限・保管期間、raw/metadata/request/receipt/seal、永続attemptの準備を確定する。取得本文の外部再配布は含めない。
- 根拠：適用運営者、確認対象規約、条件未確認時に限定確認できる根拠、DENY／不明時の停止を明記する。正当な根拠が得られなければHOLD。

A1更新は必要性・鮮度方針が成立した場合だけ別枠1 GETの候補。A2・aboutj規約・B1/B2はこの最小案から延期する。新しい規約URL、記事本文、pagination、C/D、HISTORY/PREDICTIONをscopeに追加しない。

条件原本の取得承認、G3本審査、permit発行、G4開始は異なる承認単位である。追加正本を得ただけで後続を自動開始しない。

## STOPと証拠保持

別host適用、URL・UA・revision・hash・時刻の不一致、robots/termsのDENYまたは未解決適用条件、403/429、TLS／timeout、不明完了、保存所有者・readback・ledger矛盾、保護対象差分で停止する。消費attemptは戻さず、自動再送・旧permit復活・lock強制回収・raw修復・既存worktree操作を行わない。

バックグラウンド更新が保護対象に差分を生じた場合は、タスク定義・実行時刻・変更前後hashを独立に確認する。原因不明ならSTOPし、推測で定時処理由来と認定しない。

規範15 PASS／9 UNKNOWN、terms全6 UNKNOWN、B/C/D・HISTORY/PREDICTION HOLD、Phase A BLOCKED、Phase B NOT_AUTHORIZEDを維持する。Phase 2.5Qの完了点は証拠整理と引継ぎまでである。
