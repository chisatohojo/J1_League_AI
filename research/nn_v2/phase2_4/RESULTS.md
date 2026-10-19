# NN v2 Phase 2.4 将来収集の事前監査

総合判定: **HOLD**。実T0・対象登録・実試合の確率計算／保存・性能評価は行っていない。2026-10-20 JST。

開始branchは `feature/nn-research-v1`、HEADは `ae208e0336e5554e52bfef87c3f0fe81c7d404a3`、clean。Studyは `nn_v2_residual_20261020_01`。学習前Manifest SHA `75d51da6e8c984666fe5630330a3b962e37ff32d0fb3d294aaf3989f0ebf44cb`、最終seal SHA `d620f8a9cb44a3940996f89ded80c5396b0925e862501261870b6598458d392f` と全payloadが一致した。Phase 2.3のZIP CRC・119 payload SHA・展開コピーSHA・保存済み独立readback証跡を再確認した。今回joblibモデルはロードせず、NN JSONの90重み・200更新・Scaler有限性を読み取り専用で確認した。

| 項目 | 判定 | 理由 |
|---|---|---|
| MODEL | READY | 封印済みモデル・Scaler・バックアップ・復元証跡が整合 |
| SOURCE | HOLD | 全380件と残り28節は整合。仮200件にID190件・kickoff100件のpendingあり |
| HISTORY | HOLD | 終了証拠参照4件の不整合、NN将来Elo/Form adapterと2026時刻例外監査が未完了 |
| STORAGE | READY（設計・合成契約のみ） | 独立経路の親・不存在を確認。合成専用取引24件PASS。実データwriter未導入 |
| ENROLLMENT | HOLD | T0未設定。既存v1登録契約が未公表kickoffを保持できない |
| PREDICTION | HOLD | 上記の未解決事項がある。今回実行・保存とも0 |

## 最新保存日程

最新pointerを読み取り、承認済み不変revision内のmanifest・全ファイルSHA・380 fixture・20クラブ・38節・typed ID・TeamMaster・確定結果を既存readerで検証した。監査前後でpointerは同一。運用更新タスクは呼び出していない。

- revision: `f2a2fdeb171367d422b520cea7d492d99edb4a25c9b713ce0fb72a8f38f285c7`
- manifest SHA: `b8eee29d3b5ff286e50c2a171a56cff7da9afaab5ee3bc0ca64447f1b50a8e87`
- 公式観測／listing取得: **2026-10-20 07:00:03.153102 JST**。
- completed **100**、candidate **0**、scheduled **280**。これは保存観測時点の状態であり、その後の実サイトを照会した結果ではない。取得0回。

| 保存集合 | 件数 | 公式ページID確定 | ID pending | kickoff確定 | 時刻未公表 |
|---|---:|---:|---:|---:|---:|
| 全日程 | 380 | 110 | 270 | 200 | 180 |
| 未開始予定 | 280 | 10 | 270 | 100 | 180 |
| 仮の連続20節（未登録） | 200 | 10 | 190 | 100 | 100 |

データサイトID確定は100件、公式試合ページIDは110件で、名前空間を混同していない。未開始は第11〜38節の28節。今の監査時計で最初の20節を調べると第11〜30節・200 fixtureで、全380件から選んだ集合に欠損／重複なし。これは容量確認であり、対象登録ではない。実T0には最初の未開始節から再選定する。

各節10試合の所属は維持。第16節は2026-11-25／12-16／2027-04-14に分散し、他にも複数開催日の節がある。開催日差だけで延期・中断の理由を断定しない。未公表時刻は空／nullのまま保存し、将来の開催日で未開始容量を確認しただけで、00:00のkickoffは作っていない。

全不足fixtureの一覧はローカル監査領域の `final-sources/missing-official-ids.csv`（270件）、`missing-kickoffs.csv`（180件）。仮200集合のフラグにより190／100件へ絞り込める。raw日程や原データはGitへ追加しない。[source-audit.json](source-audit.json) と [rounds.json](rounds.json) は公開可能な集計。

## 履歴・情報時刻

読み取り専用で、固定ordinary J1 2015〜2025の3,588件、百年構想200件、現在の承認済みJ1確定100件という利用範囲を確認した。2026を学習へ加えていない。Cup／AFC、ST2、後日再現予測は入力外。百年構想のPK51件・延長1件も、既存validatorが分離した90分スコア／Drawだけを履歴候補にする。PKの勝者・得点や延長得点をElo／Formへ渡さない。

次の保存日程10月21日より前の未完了candidate／過去scheduledは0、最後の確定日は10月18日。構造上の過去結果は揃っている。一方、将来用NN adapterはまだ実装・PIT検証されておらず、学習用offset loaderは2015〜2025専用、Champion Aの経路はForm8を生成しない。既存live predictorに偽の時刻を渡したり、凍結した学習用時刻コードの制限を解除したりして代用しない。

百年構想はraw12点（listing1・詳細11）のSHAとmetadataが一致した。ただし189試合分の個別詳細はこの保存sourceにはなく、2026全体の中断・再開registry照合も未完了。これは189件の結果が欠けているという意味ではない。未知の時刻例外を通常試合とみなすことはできない。

現在のJ1確定100件のうち、**96件**は宣言されたcompletion-origin snapshot内のraw／metadata／URL／取得時刻／SHAと一致した。残る**10月11日4件**は [provenance-gaps.json](provenance-gaps.json) のとおり参照不整合がある。

- 千葉―長崎（101101）、水戸―清水（101102）、東京V―広島（101103）、川崎F―名古屋（101104）。
- publicationは `20261017T231757938417Z-edbc58a3` を指すが、保存された証拠SHAと取得時刻はそのsnapshotに一致しない。
- 一致するraw／metadataは `20261017T133613718777Z-21f0d67d` に実在し、4件ともSHA・URL・取得時刻を検証できた。raw消失や得点誤りと断定していない。
- これを自動採用して参照を書き換えず、代替候補を `adopted=false` で記録した。研究用の証拠bindingを明示的に検証・固定するまでHOLD。運用publication／履歴／14予測は変更していない。

取得時刻のwitnessは存在するが、公式が実際に公開・訂正した絶対時刻までは立証していない。将来は、終了日が対象日より前であることと、実取得時刻が予測生成以前であることを両方要求する。朝7時取得の前夜結果を使っても、00:00時点で取得済みだったとは主張しない。同日の結果は全試合で排除し、未知時刻・不完全履歴・ID／witness不整合は停止する。

## 保存・登録の準備

[保存／復旧設計](STORAGE_AND_RECOVERY.md) に、enrollment、source witness、artifact reference、paired v1、追記ledger、SHA、receiptを独立配置する計画を記録した。候補 `%LOCALAPPDATA%/J1AI/NNResearch-v2-future-20261020-01` は**未作成**。既存親のOwner、DACL、reparse、File IDを確認し、運用runtimeと重ならない。親DACLは継承であり変更していない。

既存 `nn_v2_paired_prediction_v1` のschemaとvalidatorは変更していない。追加実装は**合成専用**で、real origin／実fixture keyを拒否し、実データ有効化オプションやCLIを持たない。

登録v1には構造的な不足がある。IDはpendingを保持できるが、全200件のkickoffには確定ISO時刻が必須であり、現在100件が未公表なので通らない。近い10試合の時刻が判明していてもこの全体検査を迂回しない。全将来IDが今すぐ確定することを本登録の必須条件へ追加するのではなく、次に「固定identity集合」と「pendingを含む日程binding」の分離を設計・承認する必要がある。paired予測v1の確定ID・開始前・同一情報・完全batch条件は維持する。

## 合成検証と境界

- 合成専用保存テスト **24 PASS**。正常原子的公開、公式ID／kickoff不足、2モデル同一context、重複key、最早締切、時計逆行、障害3段階、receipt／SHA改変、独立380件との日程変更照合を検証。
- 既存Phase 2.1契約テストから登録・予測・batch・artifact・時刻等 **51 PASS**、19件は今回の対象外。今回はモデルfitテストを選択していない。
- 最初の旧テストrunはJUnit xunit2と `record_property` の互換警告がerrorになった。警告を抑制せず、既存テストが使うpropertyを保存可能なlegacy JUnit形式へ設定して再実行した。元の出力は保持した。
- source監査の初回例外は上記witness参照不整合。診断をHOLDとして列挙できるようにし、auditorの入力projectionも既存loaderの契約へ合わせた。最終source監査実exit0は「監査完了」であり、HOLDが解消した意味ではない。失敗ログは保持した。

保護779ファイル、NN v1/v2成果と原本Manifest／seal、14予測、再現98件、運用config／runtime、タスク定義2件、運用worktree／mainは不変。model deserialize／実確率計算／fit／性能評価／実T0／対象登録／実試合保存／ネットワーク取得はすべて0。

次の最小作業は、研究用witness binding4件の固定、2026時刻監査とfuture Elo/Form adapter、pending kickoffを表現する登録identity／日程binding契約の実装・合成検証。これらを解決してから最新保存日程を再監査する。今回、本登録・予測開始の承認は求めずHOLDで停止する。

Phase A: **BLOCKED** / Phase B: **NOT_AUTHORIZED**。
