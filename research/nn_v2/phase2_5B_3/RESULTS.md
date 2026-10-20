# Phase 2.5B-3 公式時刻証拠パイロット完了

判定は **READY_FOR_BOUNDED_EVIDENCE_ACQUISITION**（2026-10-20 JST）。元の選定12件が重複なく取得済みとなり、修正済みの固定解析で **12 PASS / 0 HOLD**。これは取得方式の準備判定であり、残り276件の取得許可ではない。**HISTORY / PREDICTIONはHOLD**を維持する。

開始branchは `feature/nn-research-v1`、HEADは `88f8cc0724d815a4cd520c68f5ae125b095965e6`、作業ツリーはclean。Study `nn_v2_residual_20261020_01`、モデル `TRAINED_AND_SEALED_RESEARCH_ONLY`。入力、修正済み解析実装、model/study/artifact sealと53 payload、既存snapshots、保護対象を照合し、不一致0で通信へ進んだ。

## 取得・再解析結果

| 範囲 | GET | HTTP | 修正後の解析 |
|---|---:|---|---|
| 既存7件のオフライン再検証 | 0 | 既存200を照合 | 7 PASS |
| 別途明示承認されたrobots確認 | 1 | 404 | 新しいアクセス証拠を保存 |
| 元の差集合5件 | 5 | 全件200 | 5 PASS |
| 既存7 URLへの再アクセス | 0 | — | — |
| 残り276件・追加告知 | 0 | — | 未承認 |

当初の6 PASS / 1 HOLDは元のartifactのまま保持し、新しい7件再解析結果を別artifactへ封印した。元の12 URLから取得済み7 URLを除いた差集合が正確に5件であることを確認し、公式ID、TeamMaster対戦、日付、年度付き全文見出し、90分スコアを取得前に固定した。選定・URL・identityの追加は0。

アクセス条件は、保存済みの9月11日404だけでは現行状態を確認できなかったため、通信前にHOLDした。ユーザーから別枠1 GETの明示承認を得て、10月20日のrobots.txtを1回取得した。新しい404を「公開されたrobots規則なし」として保存し、24時間のローカル鮮度guardを通過させた。この鮮度は研究側の方針であり、公式サイトの指定値ではない。最初のHOLD preflightと提案も保存し、その後の承認済みpermitを新規作成した。

5件は各URL1 GET、HTTPS証明書検証、timeout10秒と親processの10秒deadline、本文2 MiB/件、redirect追従0、retry0、並列0で取得した。robotsは本文64 KiB上限の独立permit。robots完了から最初の試合取得までを含め、実測間隔が全て5秒以上であることをreceiptで照合した。詳細な時刻・HTTP・SHAの公開集計は [communication-receipt.json](communication-receipt.json)、取得前の固定条件は [preflight-summary.json](preflight-summary.json)。

## 証拠の意味と限界

- 全12件で公式URLとidentityの一意対応、日付、年度付き大会見出し、規定時間結果、保存済みsourceとの整合を確認した。異なる種類の公式ページはrawの同一性を要求せず、identity・日付・90分結果を照合した。
- kickoff表記差の2件は、保存revisionの表記推移と新しい詳細ページの最終kickoffが一致した。表記差の理由や、当初発表日時・延期の有無を立証したとは扱わない。
- 封印済みcompletion bindingの比較対象1件でidentity・日付・90分Drawが一致した。Phase 2.5Aの全4 bindingも元packetから再検証した。10月17日の実取得時刻、元publicationとの不整合記録は維持し、新しいbindingは作らない。
- 備考は10件が既知の空欄構造、2件が非空欄。非空欄は監督警告、脳振盪交代と追加交代枠の注記で、既存strict parserが解析した。未知・曖昧な時刻注記0、新たな中断・再開注記0。一般記事の「リーグ中断／再開」を個別試合の例外へ変換しない。
- PKがある3ページではPK得点を90分結果と分離した。延長ページ0。パイロットで注記が見つからなかったことから、残り276件の例外不在は推定しない。

後日取得した最終詳細ページは、当初日程や当時の公開状態の証明にはならない。パイロット12件も当初発表の来歴は未立証。必要な当初日程、変更・延期・再開告知、試合identityとの対応と公開時刻は [original-schedule-evidence-plan.json](original-schedule-evidence-plan.json) に整理した。保存済み公式リンクから抽出した日程・お知らせindex候補2件をローカルに保持するが、直接の告知資料と必要取得件数は未確定。追加ページへのアクセスは行っていない。

## 残り276件の計画

[remaining-acquisition-plan.json](remaining-acquisition-plan.json) は計画のみ。別承認があれば最大276 URL / 276 GET、各1回、間隔5秒、timeout10秒、本文上限552 MiB。待機だけで最低22分55秒、全requestが10秒を使う予算では68分55秒にprocess・保存時間を加える。12ページの平均本文123,620 bytesから本文約32.54 MiBを見積もるが、上限は縮小しない。

同じ詳細ページ構造を対象とする限定取得方式は準備できた。全件のexact saved-link台帳、現行アクセス証拠、別の全体permitを必要とし、未知構造・注記・矛盾・通信エラーでは停止する。当初日程資料の調査は別枠であり、この276 GETの見積りに含まない。

## 検証・保護・保存

合成・既存関連テストは **190 PASS**、warnings-as-errors、skip0、テスト中のネットワーク0。通信前は187 PASSで完全な年度付き期待値、上限、TLS、host、1 GET、retry/redirect禁止、SHA、未知構造の拒否を確認した。取得後に親processの直列5秒間隔、429とhard timeout時の停止テストを加えた。追加テストのfixtureで期待見出しが欠けた1失敗を修正し、最終190 PASS。取得実装・固定parserは変更していない。[synthetic-test-results.json](synthetic-test-results.json) に段階別JUnit SHAを記録した。

保護ファイル10,061件のSHA不一致0、model sealと53 payloadの照合済み、Windowsタスク2件・main・他worktree2件・運用runtime等のファイル集合は不変。[protection-verification.json](protection-verification.json) を参照。実fit、性能評価、実確率計算、T0登録、対象登録、将来予測保存は全て **0**。

Raw HTML、request/metadata、12件個別検証、比較結果、取得permit、ローカル実装、SHA台帳は研究専用の新規領域に保存した。元snapshotへの追記や修正はない。既存7件のsnapshotも新しいbackup bundleへコピーし、元sealと照合した。別ドライブのZIPと独立展開後の全payload SHAを [backup-verification.json](backup-verification.json) に記録する。公開するのは集計、仕様、SHA、テストだけで、個別履歴や個人環境パス入りの証拠はローカルとbackupに置く。

公開SHAは [SHA256-MANIFEST.json](SHA256-MANIFEST.json)、ローカルartifactの索引は [local-evidence-index.json](local-evidence-index.json)、通信・解析契約は [PROTOCOL.md](PROTOCOL.md)。公開テストはSHA固定のローカル実装をloadし、別実装へfallbackしない。

未解決の実装不具合0、パイロット内の未知注記0。証拠不足は残り詳細276件と当初日程・告知・当時の情報状態である。取得方式READYをHISTORY全体や予測実行のREADYへ昇格しない。

**HISTORY / PREDICTION: HOLD。Phase A: BLOCKED。Phase B: NOT_AUTHORIZED。**
