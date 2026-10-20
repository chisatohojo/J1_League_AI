# Phase 2.5B 将来Elo/Form adapter契約

研究専用の独立実装は `src.features.nn_future_history`。既存の学習用offset generator、時刻generator、運用Elo履歴は変更しない。ファイルIO、モデル・Scalerのload/fit/transform、推論・予測保存APIを持たない。結果更新時のElo期待値計算は履歴構築の内部演算であり、学習済みモデルによる実試合の予測確率計算は行わない。

## 入力と停止条件

- `ResultEvent` はidentity、namespaceごとのID、大会、TeamMaster ID、当初kickoff、source記録日、研究上の結果有効時刻、90分得点、raw/metadata SHA、URL、revision、実取得UTCを別fieldで保持する。PK・延長得点・PK勝者・完成済みラベルを受け取るfieldは設けない。
- `Fixture` の完全な監査済みuniverseにはcompletedだけでなくscheduled/candidate/suspendedも残す。completed集合と結果event集合の完全一致、identity重複、同日クラブ重複、TeamMaster IDの形式と明示rosterへの完全一致を検査する。roster・universe・coverage境界は外側の証拠監査が固定する。自己申告の空集合を実データの完全履歴の代用にしない。
- 2026以降の各結果は、全event fieldのSHAと一致する外側の監査済みtiming admissionが必要。結果witnessがあるだけではadmissionを作らない。未知の中断、変更されたevent、欠損witness、曖昧な時刻は拒否する。このphaseでは実2026用admissionを発行していない。
- `Query` はidentity、両TeamMaster ID、kickoff、JST日付00:00のhistory cutoff、独立したknowledge clockだけを受け取る。結果列を付与できない。knowledgeはcutoff以降・kickoffより前とする。
- coverageが対象日まで届かない場合、対象日より前に未完了fixtureがある場合、適格な過去結果の実取得がknowledgeより後の場合は、結果を黙って除外せず停止する。正当な空履歴の0件と欠損履歴を区別する。

2015〜2025に限り既存 `nn_original_kickoff_events_v1_1` からeventを生成する。外側で既存入力pinと全公式cacheの封印済みtiming reviewを照合する。後日記録を用いた研究再構成であり、当時のsource取得済みを主張しない。ID30700は2024-08-24 19:03開始前の特徴量、8月24日00:00 cutoff、11月22日の最終1-1、11月23日00:00からのDraw反映を維持する。

## 時刻と更新

結果有効境界はsource記録日の翌日00:00 JSTであり、実終了時刻の推定値ではない。中断再開では元のfeature時刻と再開後の結果境界を分離する。結果eventは結果有効時刻、source日付、source IDの順に一度だけ適用する。再開結果のElo更新には反映時の現在stateを使う。

対象日に反映可能な結果だけを適用し、同日試合の結果は使わない。朝08:00に取得した前日結果を09:00のknowledgeで参照することは可能だが、00:00取得済みとは記録しない。実取得時刻は監査traceにもそのまま残す。これは過去日の厳密publication as-ofを証明するものではない。

初期Elo1500、K30、home advantage175、season resetなし。Formはホーム・アウェイ共通の直近5完了結果で、大会・年度をまたいで継続する。90分勝利3・Draw1・敗戦0を集計し、百年構想の大会勝点やPK勝敗を使わない。

## 出力列と値域

出力はidentityと次の固定9列。値は生値で、学習済みScalerへfitしない。

| 順 | 列 | 制約 |
|---:|---|---|
| 1 | elo_diff | home Elo − away Elo、有限float。任意のclip上限なし |
| 2 | home_last5_matches_available | 整数0〜5 |
| 3 | away_last5_matches_available | 整数0〜5 |
| 4 | home_last5_points | 整数0〜3×home availability |
| 5 | away_last5_points | 整数0〜3×away availability |
| 6 | home_last5_goals_for | 非負整数。空履歴は0 |
| 7 | away_last5_goals_for | 非負整数。空履歴は0 |
| 8 | home_last5_goals_against | 非負整数。空履歴は0 |
| 9 | away_last5_goals_against | 非負整数。空履歴は0 |

traceには結果有効時刻と実取得時刻、各featureのcutoff/knowledge、依存履歴件数・ID集合SHA、直近5件のIDを記録する。個別traceはローカル保存する。未知を0で補完せず、非有限値を成功へ変換しない。

## Phase 2.5A binding

固定SHA `6e1309539a5fc5ab58a82d36035e5d96a6da462701d5253e3b83dd332b8181f0` と元revision/snapshot packetを既存validatorへ渡し、byte照合と再生成一致を要求する。SHA文字列だけを渡しても採用しない。

対象は101101〜101104の4件だけ。eventのidentity・日付・90分得点・raw/metadata SHA・取得時刻・URLが封印済みbindingと一致する必要がある。それ以外へのbinding適用を拒否する。10月17日の取得時刻と元publicationの誤ったcompletion originを別記録で保持し、元publicationは修正しない。

## 実履歴監査の境界

`scripts.audit_nn_future_history` は保存済みsourceだけを読み、network audit hookと既存no-learning tripwireを有効にする。採用revisionを独立pinと照合し、completed件数をそのtableから導出する。全入力の再読SHA照合後、source/runtime/repo外の未作成ディレクトリへcreate-newで報告し、fsync/readbackする。個人パス入りの台帳・取得候補・個別履歴はGit対象外。

2015〜2025の実9特徴量を既存generatorと照合し、最後の2025結果まで全3,588件の適用順を検証する。最後のstate検査には明示的な架空audit probeを1件だけ使い、実試合への予測は作らない。2026の時刻証拠不足が残る場合は完全なuniverseの欠落拒否を確認し、部分履歴による実2026特徴量を出力しない。

この契約・合成検証・HISTORYのREADYは、実T0登録・対象登録・将来予測の開始承認を含まない。Phase A: BLOCKED / Phase B: NOT_AUTHORIZED。
