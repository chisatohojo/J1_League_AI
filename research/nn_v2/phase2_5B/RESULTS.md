# NN v2 Phase 2.5B 2026時刻監査・将来Elo/Form adapter

判定：**HOLD_HISTORY_EVIDENCE_OR_ADAPTER**。2026-10-20 JST。HOLD理由は実履歴の証拠不足。adapterの合成検証と既存実履歴との数値照合は合格、検証で残った実装不具合は0件。

開始branchは `feature/nn-research-v1`、HEADは `1e9a2e0c54c541853b7b0a047954bfb88090db21`、開始時clean。指定branchの既存worktreeで作業した。Study `nn_v2_residual_20261020_01`、モデルは `TRAINED_AND_SEALED_RESEARCH_ONLY` のまま。Phase 2.5Aの封印済み4件と、Phase 2.4のHISTORY/PREDICTION HOLDを照合した。

## 採用sourceとcoverage

公式revisionは `f2a2fdeb171367d422b520cea7d492d99edb4a25c9b713ce0fb72a8f38f285c7`、manifest SHAは `b8eee29d3b5ff286e50c2a171a56cff7da9afaab5ee3bc0ca64447f1b50a8e87`。観測は2026-10-20 07:00:03.153102 JST。現在のネット上の状態とは主張せず、この保存済み承認revisionだけを採用した。

| 系列 | 完了結果 | 結果・identityの確認 | 認識済み時刻備考を確認できる詳細 |
|---|---:|---|---:|
| 2015〜2025 ordinary J1 | 3,588 | 固定入力12件・全raw/metadata・既存timing review照合 | 3,588 |
| 2026百年構想 | 200 | 保存公式一覧を再parse、全正規化列・TeamMaster・大会構造と一致 | 11 |
| 2026/27 ordinary J1 | 100 | 採用revisionから件数導出、completion witness全100件検証 | 1 |

2026/27の100件はコード上の固定期待件数ではない。未完了280件を結果eventに使っていない。追加の保存済みsource探索で2026/27のSFMS02詳細1件を確認した。対象IDの重複、両2026系列間のdata-site ID衝突、同日クラブ重複は検出0。Cup/AFC/ST2/後日再現予測を履歴へ追加していない。

百年構想はPK51件・延長1件。公式一覧とdetail periodから正規化を再生成し、既存全列と一致した。Elo/Form入力は90分得点・勝敗だけであり、PK勝者・PK得点・延長得点・大会独自勝点を含めない。

## 時刻監査と不足

百年構想の残り189件について、結果が一覧に存在することは確認したが、中断・再開・延期等の時刻例外がないという立証には使わない。2026/27の99件もcompletion確認と、認識済み備考または同等の公式時刻注記による監査を分けた。**不足する詳細・同等証拠の取得候補は最低288件（189＋99）**。該当ID、欠落証拠、公式候補URL、取得状態はローカル `missing-evidence.json` に保存した。URLは既存公式一覧から抽出済みの実リンクのみで、連番・推測生成・新規取得は0件。

保存revision間のkickoff表記差は20件、日付変更の検出は0件。予定時刻と記録上の実開始時刻の差を、延期の原因と断定しない。開始前の保存日程観測があるのは20件で、当初発表日程からの完全な変更履歴を300件すべてで立証できたわけではない。各試合で元日程、source記録の開始、実終了時刻、研究上の翌日境界候補、source実取得時刻を区別し、不明fieldはnullで保持した。

completionページ11件の「中断・再開」は、文脈確認では代表ウィーク等のリーグ休止・再開を述べた記事文であり、個別試合の中断を示すものではなかった。検出語だけで例外に認定しない。この文脈判断も、残る試合に例外がないという証明には使わない。raw SHA・文脈SHA付きの補足reviewと、20件のkickoff差をローカルregistryへ保存した。

2026全300件に結果有効eventのadmissionをまだ発行していない。詳細欠落288件と、当初日程・変更履歴等の立証不足は重複するため加算しない。延期・再開の注記が今後見つかった場合に必要な追加公式告知の件数は未確定。保存sourceだけでは十分な立証に届かず、**HISTORYはHOLD**。

## Bindingとadapter検証

Phase 2.5Aのbinding SHA、全原revision packet、snapshot A/B、raw/metadata、公式identity・90分結果・実取得時刻を再検証した。101101〜101104だけを研究参照可能とし、4件の10月17日取得を10月11日取得へ書き換えていない。元publicationの不整合記録はそのまま残した。追加binding・元publicationの修正は0件。

独立adapterと入力・時刻・9列の契約は [ADAPTER_CONTRACT.md](ADAPTER_CONTRACT.md)。固定Elo1500/K30/HA175、season resetなし、共通直近5試合を実装した。対象日00:00 cutoffと実取得/knowledgeの時刻を分け、不足・未知・未完了を黙って落とさず停止する。

合成・関連回帰テストは **297 PASS / 1 SKIP**（warnings-as-errors）。skipは既存の任意ローカルfixtureで、今回の実sourceは別途照合済み。追加テストはlegacy時刻一致、200件identity重複、PK/延長混入拒否、2026/27結果更新、同日結果隔離、未知時刻・未完了拒否、中断の二event分離、直近5件、cold startと欠損、TeamMaster完全一致、binding改変、Scaler fit拒否、予定への結果付与拒否、書込み拒否等を検証した。

保存済み2015〜2025実3,588試合の9列は既存generatorと最大絶対差 **0**。ID30700の8月24日開始前と11月23日からの最終Draw反映を維持し、最後の2025結果を含む全3,588結果eventの適用順も一致した。値域・有限性・列順・個別依存traceはローカルに保存した。2026実履歴の不完全なadmissionでadapterが停止することを確認し、実2026特徴量の部分出力は0件。全実履歴のadapter合格や全体READYとは主張しない。

## 保護と保存

事前にモデルseal SHA `d620f8a9cb44a3940996f89ded80c5396b0925e862501261870b6598458d392f` と全53payload、既存入力SHA、前工程の保護805件を照合し、保護対象を9,281ファイルまで広げた。事後照合結果は [protection-verification.json](protection-verification.json)。Champion A、NN v1/v2封印物、既存予測14件・再現98件、元publication/raw/metadata、runtime/config、Windowsタスク2件、他worktreeとmainは変更しない。

実データfit **0**、性能評価 **0**、実試合確率計算 **0**、T0登録 **0**、対象登録 **0**、将来予測保存 **0**、新規sourceネットワーク取得 **0**。監査processはsocket/DNS/HTTP取得を拒否し、既存no-learning tripwireの呼出検出も0。

個別履歴・取得候補一覧・個人パス入り保護台帳・process receipt・JUnitは `%LOCALAPPDATA%/J1AI/NNResearch-phase2_5B-20261020-154857` へローカル保存。GitHubへ追加するのは新規研究実装、合成テスト、集計・仕様・SHAのみ。公開索引は [local-evidence-index.json](local-evidence-index.json)、実装SHAは [implementation-sha256.json](implementation-sha256.json)。

実装不具合と証拠不足を分離し、証拠不足を理由に `HOLD_HISTORY_EVIDENCE_OR_ADAPTER` とする。HISTORYが将来READYになっても、実T0登録・将来予測実行の承認にはならない。

Phase A: **BLOCKED** / Phase B: **NOT_AUTHORIZED**。
