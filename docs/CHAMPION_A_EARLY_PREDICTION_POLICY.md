# 日数ベース先行予測：policy設計案

設計判定：`CHAMPION_A_EARLY_PREDICTION_POLICY_READY`。
本番ゲート変更、実モデルload/推論、保存、公式取得、GUI更新は**未承認・未実行**。
現行の全件履歴ゲートと日曜の運用BLOCKEDは維持する。
[依存性根拠](CHAMPION_A_EARLY_PREDICTION_DEPENDENCY.md) を正本として、次段階の変更範囲を定める。

## 方式の比較

| 方式 | 成立条件と利点 | 限界 | 推奨 |
|---|---|---|---|
| A：現行の全件完了 | 全リーグの対象日前履歴が閉じる。既存コード/readerと一致 | 対象teamへ影響しない別チームの未完了でも止まる | 本番は当面維持 |
| B：対象teamの履歴だけ | 対象team自身の未完了を検出できる | 過去の相手→対象teamという間接依存を見逃す。直近結果だけでは不可 | 一般的なゲートとして不採用 |
| C：特徴量依存閉包 | 時間順のElo祖先を検証。不明な特徴量・順序はHOLD | 依存証拠、partial state、版付き保存/readerが必要 | **将来実装の推奨** |

Cの初期fast pathは、全必要歴史prefixが閉じており、その後target HOME/AWAYの更新がないことを要求する。
これはBへprefixの証明を加えた十分条件であり、単に全件ゲートを削除する変更ではない。
実際のElo再生は固定履歴と全approved completed結果を従来どおり使う。
閉包91件だけへ実データを切り詰めて再生する案ではない。

## 時点・日数パラメータ

| 項目 | 定義・境界 |
|---|---|
| `prediction_horizon_days` | 実freezeのJST日付からtargetのJST日付まで。候補既定2日、設計上0〜14日。運用configを今回変えない |
| `last_required_result_date` | 時間依存閉包に入る直近必要試合のJST日。固定3,788件のprefix検証は別途必須 |
| `next_intervening_match_date` | freezeより後・target kickoffより前にある、対象teamのモデル更新対象試合。なしとUNKNOWNを区別 |
| `feature_dependency_cutoff` | **実際のfreeze UTC**。必要結果取得UTC≤source観測≤freeze。event順序のcutoffと取得時刻を混同しない |
| `source_observed_at` | 封印sourceの実観測UTC。source公開完了は別証拠。未来source・24時間超はHOLD |
| `prediction_valid_until` | 新規生成可能期限は最早target kickoffとsource鮮度期限等の最小値。kickoff同時刻は拒否。保存済み予測の削除期限ではない |

「何日前」と「入力が確定したか」は独立条件。horizonを広げても必要結果の未確定を免除しない。
source鮮度期限を過ぎても、以前の有効なfreezeで保存した予測を再計算・削除しない。
新しい予測を作るときの再確認、保存済み入力の完全性確認、後続日程の適用性確認を分離する。

## Cで必須とする証明

1. model/scaler/feature contractを固定SHAで照合し、入力が `elo_diff` だけであること。
   全体順位・動的正規化・Form等が追加された場合は未知依存としてHOLD。
2. 公式fixture coverage・typed identity・TeamMaster・開催順序が確認できること。
   completed subsetだけから未開催試合の不存在を推測しない。
3. 必要な過去試合を、対象teamから逆時系列に展開すること。
   依存する相手の前状態も追跡し、未完了・不明な必要結果はHOLD。
4. 必要結果に明示的終了・90分結果・raw/metadata/取得UTC・source revisionの証拠があること。
   source自体のSHA/identity/結果矛盾は、無関係な備考や「依存しない試合」へ格下げしない。
5. 既存の同一team・同一日重複拒否を維持すること。不明な延期順序や重複IDはHOLD。
   中止を結果欠落から推定せず、明示的な非開催証拠がある場合のみ更新eventから除外する。
6. 未完了だが時間閉包へ到達しない試合は、別の未確定registryに保持すること。
   league全体のEloを完全と称さず、`global_history_complete=false` と対象別証明を分離する。
7. 同じsource/model/必要結果/fixtureを予測前・保存前に照合し、生成/commitはkickoff前であること。
   後続latestへ暗黙差替えしない。保存済みfixtureの再予測・上書きを拒否する。

未知競技や未知featureはfail closed。現Championは通常J1と固定百年構想以外のcup結果をEloへ入れない。
これは休養・負傷・物理的中断・全大会の日程不在を証明するものではない。
全大会の無試合を追加要件とするなら、公式cup等のcoverage証拠を別工程で取得・審査する。

## 日曜5件への適用範囲

保存sourceでは、直近必要結果は全件10/21 completed、以降に日曜対象teamのモデル対象試合なし。
土曜5件は対象teamと重ならず、Cで数学的に除外可能な未確定更新である。
各fixtureの閉包は91/90/93/91/91件で必要結果取得済み。全5件が**Elo依存条件の解析候補**となった。
全大会の無試合、当時の最早publication完了UTC、実モデル数値動作、実保存は未実証。

現行workerは依然全5件を `prediction_history_incomplete` で止める。
この試作の `candidate=true` を使う本番entrypointは存在しない。
金曜07:00共通snapshotのWeekend Batchへ今週末を後付けせず、土曜既保存5件は不変とする。

## 保存・reader・GUIの移行設計

現行は「同じ開催日の全targetを一つの旧日別batch」として保存し、部分既保存を拒否する。
新policyが3/5件だけ適格と判定しても、旧形式へ3件だけ保存すると日別完全性契約を壊す。
初期段階は全日targetがCに合格した場合だけ全日一括保存を設計し、1件HOLDなら日別保存0件とする。
試合単位の部分先行保存は、新しいformatとcanonical readerの独立実装・承認後に限る。

新format（名称・versionの確定は実装審査で行う）には少なくとも次を含める。

- model版と別の `prediction_policy_id`、情報cutoff、実生成/保存UTC、全source/model SHA。
- 対象日の全fixture集合、今回eligible集合、HOLD集合と理由、typed identityとkickoff。
- 固定履歴証拠、対象別の必要event集合/SHA、結果の取得UTC、入力snapshot/feature SHA。
- 未確定の非依存event集合、league全体未完了状態、dependency検証結果。
- 出力CSV/binding SHA、重複拒否、全件公開状態、公開後readback receipt。

旧CSVや旧manifestの意味を遡及変更せず、新formatを旧日別の2-key manifestへ偽装しない。
既存readerの旧日別・v2互換性を保ち、新形式は理解するreaderだけが検証して読む。
現UIの `read_saved_daily_projection` は旧日別3ファイルだけを許可するため、新形式を現在接続しない。
publicationを先に変えずreader互換を先行審査し、rollback後も新しい保存batchは削除しない。
GUI投影/固定pair切替/正式Stop・起動は予測保存とは別承認で、再表示の推論は0にする。

## 日程・必要特徴量の更新時

同じ固定revisionのSHAや必要結果が変われば整合性HOLD。自動修復・別sourceへのfallbackはしない。
targetのidentity、日時、クラブが変われば適用性HOLDとし、原保存値は不変で警告する。
後続revisionに無関係な結果が追加されても、古い予測へ混入させず、固定入力と後続日程の確認を分ける。
policyやfeature構成が変われば別versionを審査し、モデルを再学習・再fitして帳尻を合わせない。

## 実装順序と追加承認

1. このpolicyの限定scope（固定Elo／J1＋百年構想）と全日batchの初期方針をユーザーが承認する。
2. 必要event証拠validator、snapshot契約、exact target guard、版付きreader/保存receiptを合成環境で実装する。
   変更候補は運用updaterのgate選択、Champion入力の証拠受渡し、新format reader、保存/投影adapter。
   学習済みmodel/scaler、Elo式、既存batch、22:00の推論0は変えない。
3. 対象別証明と旧ゲートのshadow差分を検証する。無関係な欠損と間接依存欠損を区別し、未知はHOLD。
4. 実モデルload/推論・保存の隔離検証を別承認し、モデル環境・実時計・排他・crash/readbackを実証する。
5. 新しい未保存集合・source revision・実cutoff・全kickoff・task競合を改めて確定し、本番実行を個別承認する。
6. 必要ならGUIの新pair準備・反映をさらに別承認する。今回のGit保存はこの実行許可ではない。

原子renameの可視性と電源断永続性は別。stale lock、途中状態、意味不明な時刻やsource矛盾ではSTOP。
failure後の自動再推論、旧予測の削除、lock強制回収、現在GUIの再起動は行わない。
