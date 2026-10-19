# NN v2 Phase 2.2 実入力PIT監査・学習前フリーズ

判定: **READY_FOR_SEPARATE_TRAINING_APPROVAL**。学習の開始承認ではない。2026-10-20 JST。

開始branchは `feature/nn-research-v1`、HEADは `a424c1591d4642daca33d5cb9f64ab80c84d063c`、worktreeはclean。既存DESIGN／PIT計画／将来評価計画、NUMERICS／SCHEMAS、implementation spec／SHA台帳は一致した。アルゴリズムや仕様は変更していない。

## 実入力と時刻

- 2015〜2025 ordinary J1の全3,588試合を維持。2015〜2016のseed 612、2017〜2025の残差対象2,976。2024は380、2015〜2024は3,208。除外・補完なし。
- 年別CSV11件とTeamMasterのSHAを既存input pinsへ照合。公式HTML 3,588件とmetadata 3,588件は、Phase 1.1で封印した全件SHA・取得先URL・ID・bytes・statusに一致した。監査後にも再照合した。
- 詳細HTMLを既存parserで解析し、正確な正式名を既存 `jleague_official` 名前空間で解決して、各source行のhome／away IDと全件一致を確認。source一覧の略称は従来の `jleague_data_site` で解決する。別名追加・曖昧一致・fallbackなし。取得したstatsは予測入力へ追加しない。
- 既知の時刻注記14件、未知0件。研究用公式根拠3ページ、evidence manifest、例外registryのSHAは不変。公式ネットワーク取得0回。
- `nn_original_kickoff_events_v1_1` による全7,176イベントを監査。各feature readの使用結果集合が、そのcutoffまでに有効化された全結果と完全一致した。自試合・同日・未来結果なし。全結果はfeature生成後に一度だけ履歴へ反映された。
- 独立したElo式とForm dequeで全3,588行・9列を再計算し、絶対誤差1e-10以内で一致。全列有限、欠損0、列順は固定。8列Formの整数・availability・勝点・空履歴制約を検証。cold start 107件も除外しない。

ID30700は元CSVの日付2024-11-22を保持する。feature timestampは2024-08-24 19:03 JST、履歴cutoffは同日00:00 JST。その時点の3,097履歴試合だけを使い、最終履歴日付は8月17日。最終labelはDraw。最終結果の履歴反映境界は11月23日00:00 JSTであり、それより前の他試合には使わない。結果反映は一度だけ。元CSV・部分スコア・registryは変更していない。

これは結果有効時刻に基づく因果順序監査であり、後日取得した公式ページから当時の公開状態まで証明したものではない。`historical_publication_asof_proven=false` を維持する。

## Cross-fit（fitなし）

| 対象年 | 基準の訓練年度 | 訓練件数 | 対象件数 |
|---|---|---:|---:|
| 2017 | 2015〜2016 | 612 | 306 |
| 2018 | 2015〜2017 | 918 | 306 |
| 2019 | 2015〜2018 | 1,224 | 306 |
| 2020 | 2015〜2019 | 1,530 | 306 |
| 2021 | 2015〜2020 | 1,836 | 380 |
| 2022 | 2015〜2021 | 2,216 | 306 |
| 2023 | 2015〜2022 | 2,522 | 306 |
| 2024 | 2015〜2023 | 2,828 | 380 |
| 2025 | 2015〜2024 | 3,208 | 380 |

9foldすべてで訓練ID／対象IDの重複0。対象年より前だけを訓練集合にする。全対象IDの和集合は重複のない2,976件で、残差Scaler予定集合と完全一致。Form 8列をmatch IDで一対一結合して元の値・順序と照合した。基準fitへの対象年ラベル投入、実offset生成、実Scaler統計生成は行っていない。実際のfit後に検証すべきoffset値・Scaler統計・クラス順・確率は次工程に残す。

## Study Manifestと停止契約

study ID: `nn_v2_residual_20261020_01`。

正本: `%LOCALAPPDATA%/J1AI/NNResearch-phase2_2-20261020-063259/verified/study-manifest.json`

SHA-256: `75d51da6e8c984666fe5630330a3b962e37ff32d0fb3d294aaf3989f0ebf44cb`

正本にはsource SHA、元データSHA、時刻registry、9／8列順、class順、90パラメータの数値仕様、Adam／seed／200更新／目的関数、全ID集合、9fold、最終基準3,588件、予定fit 9＋1＋1、将来登録規則、停止条件、未作成の専用出力先を固定した。行別監査CSV、dependency監査、event trace、全cache SHA、分割集合、正本とSHA台帳はローカル保存し、flush／readbackを確認した。

モデル・Scaler・実offset SHA、実Scaler統計、T0はすべて未生成/null。数値を仮置きしていない。学習後の実SHAは別sealへ格納し、この学習前manifestを書き換えない。

[学習実行契約](TRAINING_RUNBOOK.md)は、create-new専用出力、fit前の排他的study attempt予約、同一study再学習禁止、有限timeout、再試行0、失敗状態の保存、artifact読戻しを要求する。今回は学習driverもattempt markerも学習出力も作成・実行していない。入口実装が必要なら次承認工程で確認し、最初のfit前に別execution sealへSHAを記録する。

## 将来20節200試合

保存済み承認revision `67031cfbfa99dd78e889d606225840ca7a74211dae105233327d3beed9d3bdba` を固定して検証した。manifest SHAは `3d79c9369ed47fa6847c13ead79c2a5176b5b486674a83415a3dd22f8b87ce8e`。公式観測は2026-10-19 22:00:05.223872 JST。現在のネットワーク状況を取得した記録ではない。

保存時点でcompleted100／candidate0／scheduled280。2026-10-20 06:42 JSTの監査時刻に対し、全試合未開始と判断できる第11〜38節の28節・280試合が残る。仮の最初の20節は第11〜30節、各10試合・同じ20クラブ、合計200件で容量条件を満たす。開催日は2026-10-21〜2027-04-17。第16節内の11月25日／12月16日／4月14日の分散も元の所属節のまま保持する。

仮集合では公式IDあり10件、未登録190件、開始時刻未公表100件。未公表時刻はnull相当を保ち、将来の開催日という下限から未開始の容量だけを確認した。00:00などの架空kickoffを作っていない。未登録IDを推測しない。これは登録可能な容量の監査で、200件の予測実行準備完了や登録済みを意味しない。

実T0・対象登録・将来予測保存は0件。実T0時点の最新公式revisionと残り20節を再検査する。ID／kickoff未確定、履歴未完了、witness不足なら当該予測をHOLDし、延期試合を置換・除外しない。20節に満たなければ登録をHOLDする。2026の結果で性能を計算・選択していない。

## 実行・テスト・保護

今回の初回監査は、追加した監査コードが詳細正式名に一覧用名前空間を指定したためexit1で停止した。既存collectorとTeamMasterを読んで指定誤りを特定し、監査コードだけを既存の `jleague_official` 契約へ修正した。失敗ログ・`audit/failure.json`・外側exitは保持した。入力不一致を補正したものではなく、source／TeamMaster／時刻仕様に変更はない。

修正後は別の未使用 `verified/` へ監査を実行し、実process exit0、約33秒、外側timeout1,200秒、timeoutなし、自動再試行0。学習入口呼出し0回。監査中のfit／モデル推論／offset生成／NN初期パラメータ生成はtripwireで拒否し、到達なし。

- 新しい監査用合成テスト19 PASS、warnings-as-errors、実exit0。完全な合成ID分割、依存trace改変、独立再計算、名前空間、未公表時刻、20節不足、不正identityの停止を検証。
- Phase 2.1の115 PASSは、同じ実装SHAと元JUnit SHAを確認して再利用した証跡。今回115件を再実行したとは扱わない。
- 保護560ファイルが開始時から同一SHA。NN v1成果26件と保存ZIPのSHA／CRCも確認。Champion A、実保存14予測、再現98試合、公式publication、表示ストア、外部config、タスク定義2件は不変。
- 運用worktreeは指定HEADとcleanを維持。main不変。既存サーバー・ブラウザー・ショートカットへの操作なし。

実データfit: **0回**。実データ性能評価: **0回**。将来予測保存: **0件**。モデル生成: **0件**。実offset／Scaler統計: **未生成**。

2020〜2024は繰り返し研究使用済み、2025は使用済みtest、既知2026結果もfresh holdoutではない。READYは固定された歴史入力で次の学習承認へ進める判定に限る。Champion A採用や運用接続は含まない。

Phase A: **BLOCKED** / Phase B: **NOT_AUTHORIZED**。
