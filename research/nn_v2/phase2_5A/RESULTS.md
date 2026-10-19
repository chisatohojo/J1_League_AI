# NN v2 Phase 2.5A — completion witness 4件の研究用整合

判定：**COMPLETION_WITNESS_RECONCILED_RESEARCH_ONLY**。2026-10-20 JST。

開始branchは `feature/nn-research-v1`、HEADは `32ab4803850338122317f00d2022e903882fa62a`、clean。Studyは `nn_v2_residual_20261020_01`。NN v2は `TRAINED_AND_SEALED_RESEARCH_ONLY` のまま。Phase 2.4の原本、HISTORY／PREDICTIONのHOLDは変更していない。

## 原本から確認した4件

すべて2026-10-11・通常J1・第9節。既存strict parserでcanonicalが指定URLと完全一致し、日付・節・ホーム／アウェイslug・fixture_key・明示的な「試合終了」・ヘッダーと終了セクションのスコア一致を確認した。公式publicationのcandidate段階のスコア、初回completed、最新completedとも一致する。TeamMasterを使用した既存公式revision validatorも通過した。通常J1の規定時間結果として扱い、PK勝者や途中スコアを代用していない。別工程の2026中断・時刻例外監査を完了したという意味ではない。

| 対戦 | match-page ID | data-site ID | 確定スコア | 実raw取得UTC（2026-10-17） | binding |
|---|---|---|---|---|---|
| 千葉–長崎 | 101101 | 34601 | 1–1 | 13:36:08.005891 | 採用・研究参照限定 |
| 水戸–清水 | 101102 | 34602 | 1–2 | 13:36:09.613865 | 採用・研究参照限定 |
| 東京V–広島 | 101103 | 34603 | 0–2 | 13:36:11.177523 | 採用・研究参照限定 |
| 川崎F–名古屋 | 101104 | 34604 | 1–2 | 13:36:12.619673 | 採用・研究参照限定 |

URLは `https://www.jleague.jp/match/j1/2026/<match-page ID>/` の4件。namespace `jleague_match_page` と `jleague_data_site` を分離し、数値IDを同一視していない。SHA・URL・取得時刻・snapshot内ファイル名・元宣言を各件に保存した：[binding-manifest.json](binding-manifest.json)。

## 原因とrevision遷移

実rawのsnapshotは `20261017T133613718777Z-21f0d67d`（以後A）。宣言snapshotは `20261017T231757938417Z-edbc58a3`（以後B）。**Bにも同じ4URLの原本は存在するが、掲載行のevidence SHA・取得時刻に合う原本は存在しない。** BのrawはAとSHAが異なる一方、strict parserのidentity・終了状態・結果は4件すべて一致した。

| sequence | revision | 保存状態 |
|---|---|---|
| 11 | `35e58a01a567e7b786bbd16f435eae7ab66a7fa9e72be0610d2a97415dadb56f` | 4件candidate |
| 12 | `78b159382243a26101392700abafe6896fa440095b1a1875e5bba8d48253b021` | Aでcompleted。raw SHA・取得時刻・completion originはA。typed identity bridgeもAを保存 |
| 13 | `95a5760e986b28ebf149e2687eaea0dd69eb3d01c306c2100dfc681b8601808b` | Bを再取得。completion originはBだがraw SHA・取得時刻・match-page originはA |
| 14–18 | [bindingのpinsに全revisionを保存](binding-manifest.json) | completed保持処理が混在した参照を引き継ぐ。最新は `f2a2fdeb171367d422b520cea7d492d99edb4a25c9b713ce0fb72a8f38f285c7` |

`src/collect/jleague_ongoing.py` の `_parse_snapshot()` は現在のBから終了証拠を解析して `completion_origin_snapshot=B` を設定する。その後 `_hydrate_accepted_bridges()` が受理済みbridgeの `evidence_sha256`、`evidence_fetched_at_utc`、match-page originをAへ戻すが、completion originは変更しない。後続更新で再取得対象でなくなると、completed保持処理が `_IGNORE_FIELDS` をコピーしてこの不整合を残す。

既存の純粋helperをメモリ内で適用し、4件のSHA・取得時刻・両originが保存sequence 13と完全一致した：[cause-replay.json](cause-replay.json)。collectorのGit blobは初期実装commit `b93e232` と現在で同一（SHA `5e91025142d583d09f2417724f9cbaeed50339275390d46000d3a73179cbe956`）。これは保存遷移と実装による再現であり、当時のprocessがロードしたモジュールのhashや内部実行traceまで保存されていたとは主張しない。複製時のraw破損を示す事実はなく、snapshot Aのraw／metadata計8ファイルは元acquisitionコピーとbyte単位で一致した。

## 研究bindingの根拠と限界

Aに存在する同じSHAを見つけただけで採用したのではない。sequence 11→12→13→18の受理済みpublication、revision内の全ファイルSHA、runとsnapshot manifestのSHA、前revision参照、初回identity bridge、原本HTML・metadata、独立したBでの再取得結果を照合した。研究bindingはこの独立した証拠関係を追加するもので、元publicationのBという宣言を正しいものへ変更しない。

metadataのrequest開始≤取得≤snapshot観測≤snapshot生成、各publicationの観測時刻、研究監査時刻を検証した。根拠は**10月17日22:36 JSTに取得した証拠**であり、10月11日時点の入手・掲載状態は未立証。元の取得時刻を変えず `available_at_match_day_proven: false` を保持する。

binding SHA-256：`6e1309539a5fc5ab58a82d36035e5d96a6da462701d5253e3b83dd332b8181f0`。

## 検証と保護

- 新規合成テスト **40 PASS**。関連strict parserテストを含め **102 PASS / 1 SKIP**。skipは配布されない任意のローカル実ページfixtureであり、今回の4件の実原本は別途すべて解析・照合した。
- SHA改変、snapshot差し替え、時刻矛盾、canonical／identity／スコア不一致、namespace混同、競合bridge、不完全・重複・未登録bindingを拒否。封印SHAに加え、入力から再生成したbindingとの完全一致を検証。
- 監査初回は過剰なネットワークaudit hookがpandas import時のローカル `gethostname` を拒否してexit 1。原本やbindingを生成する前に停止した。実socket I/Oを拒否しローカルhostname参照を許す設定で監査を完了（exit 0）。2回のprocess receiptと初回失敗ログを保持。公式取得や予測の再試行はしていない。
- 保護**805ファイル**のSHA一致、WindowsタスクXML 2件一致、運用worktree clean、運用HEAD `5ac9052a221c6d8d563ec982bc48fbddb9e80bfa`、main `05c1598f1fa087c39dc1450be65ed075675c1c4c` 不変。NN v1/v2、Champion A、14予測、再現98件、運用config・publication・元raw／metadata・前工程監査は不変。既存サーバーへの操作なし。
- 実データfit・性能評価・実確率計算・T0登録・対象登録・将来予測保存・ネットワーク取得はすべて **0**。

ローカル証跡は `%LOCALAPPDATA%/J1AI/NNResearch-phase2_5A-20261020-074228`。[local-evidence-index.json](local-evidence-index.json) にSHAを記録。個人パスを含む保護対象リスト・外側receiptはGit対象外。公式HTML・metadataや学習モデルを新たにGitへ追加していない。

## 次工程の判定

4件のcompletion witness参照だけは研究限定で整合した。**Phase 2.4総合／HISTORY／PREDICTIONはHOLDを維持**する。2026時刻例外監査、将来推論用Elo/Form adapter、pending ID・kickoffを含む登録契約は未解決。bindingを実予測経路へ接続していない。これらを別工程で解決するまで予測開始へ進まない。

Phase A：**BLOCKED**。Phase B：**NOT_AUTHORIZED**。
