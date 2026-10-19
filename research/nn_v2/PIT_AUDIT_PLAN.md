# NN v2 利用可能な特徴量とPIT監査計画

状態: **PLAN_ONLY**。2026-10-19 JST。今回の作業は存在・SHA・件数の監査と設計だけで、学習・性能評価・新しい公式情報取得は行わない。

## データと利用境界

既存 [DATA_ASSET_INVENTORY](../../docs/DATA_ASSET_INVENTORY.md) は2026-10-02時点の目録であり、現在の運用件数を示す資料ではない。ここでは [Phase 1.1のSHA付き監査](../nn_v1/audit-timing-v1_1/dataset-audit.json) と今回の読み取り専用照合を優先する。

| 情報 | 現在確認できる規模・coverage | 由来・時刻上の制約 | v2案での扱い |
|---|---|---|---|
| 普通J1のidentity・規定時間最終結果 | 2015〜2025の3,588試合、2015〜2024は3,208 | 年別CSV11件とTeamMasterをpin。公式キャッシュ・metadata各3,588。後日記録から当時の公開時刻は立証できない | 歴史的学習の母集団。厳密な当時as-ofの実績とは呼ばない |
| elo_diff | 全3,588行で有限、機械的coverage 100% | Elo1500/K30/HA175。対象日より前に結果有効となった試合だけ | Aの基準入力、B/Cの候補入力 |
| home/away_last5_matches_available | 各3,588行、値0〜5 | 時刻イベントに従う過去5完了試合。0件も明示 | Aの残差8列の一部。未知と実在する0を区別 |
| home/away_last5_points | 各3,588行で有限 | 過去の確定結果だけから合計 | A残差入力。対象試合の勝点は使わない |
| home/away_last5_goals_for | 各3,588行で有限 | 過去の確定得点だけから合計 | A残差入力。対象試合の得点はラベル側のみ |
| home/away_last5_goals_against | 各3,588行で有限 | 過去の確定失点だけから合計 | A残差入力。同日結果を追加しない |
| 過去試合の順序・開催側・経過日数 | 元3,588試合から構築可能。双方5試合あり3,481、cold start107 | C用tensorは未実装・未監査。中断試合は結果が有効になった順に履歴へ入れる | Cの実装前監査対象。現時点でtensor coverage 100%とは主張しない |
| 国内休養日・試合間隔 | ordinary J1以外にCup/JFA等の既存sourceあり。結合後のPIT安全件数は未確定 | 大会・クラブID・日時・延期・時刻公開の整合が必要 | Bの候補。既存closed/challenger研究を自動再開しない |
| 過去shots/corners等 | 目録上のSFMS02 processed stats 3,588試合 | 現在試合のstatsは禁止。過去statsも公開・訂正時刻が未立証 | Bの候補、Aには追加しない |
| xG・J Stats・出場停止等 | 旧目録のxG660行、previous-season J Stats 2,438 feature行など。異なる期間・大会の混在 | 2015〜2024のxGを捏造できない。season-final集計を同season途中へ逆流させない。absenceはunknownの場合あり | 歴史的全件NNへ無条件投入しない。将来witnessの取得計画を別途固定 |
| 旧実験の派生特徴量 | 既存監査で10 artifactの行数とSHAを記録済み | nonmissingであることはPIT適格性を意味しない。closed・未解決SHA・player identity制約あり | 再利用は診断・監査まで。Aの訓練入力にjoinしない |
| v1 OOF・後日再現予測・実保存予測 | 保存済みの別研究・運用成果物 | ラベルや別モデルの性能を代理入力にすると研究条件が変わる | 特徴量・ターゲットの追加sourceとして使用しない |

数値のcoverageは「その列を計算できる」ことを表す。取得時刻まで含めたPIT合格率とは別である。旧inventoryの未知・誤記SHAを推測修正せず、対象を拡張するなら現物を別監査する。

## Aの入力順序案

基準はelo_diffのみ。残差NNは次の8列を固定順序で使う。

1. home_last5_matches_available
2. away_last5_matches_available
3. home_last5_points
4. away_last5_points
5. home_last5_goals_for
6. away_last5_goals_for
7. home_last5_goals_against
8. away_last5_goals_against

availability=0なら空履歴の合計0を表現する。履歴を取得できない状態をこの0へ変換しない。非有限値・不明な欠損・ID不整合は停止。Scalerは訓練行だけにfitし、transform以外で評価・将来データへ触れない。一般的な前処理リークの根拠は [scikit-learn公式のdata leakage説明](https://scikit-learn.org/stable/common_pitfalls.html#data-leakage)。本データのPIT合格を同資料が保証するわけではない。

## 1行ごとに保存するPIT監査情報

- fixture_key、namespace付き公式ID、season/round、home/awayのTeamMaster ID。
- 元source日付、original kickoff、現在の公式kickoff、feature cutoff、result-effective時刻、取得UTC時刻。
- source URL・canonical・raw SHA・metadata SHA・publication/revision、利用した履歴試合IDと結果証拠。
- 9特徴量の有限性、mask/availability、Scaler学習範囲、基準offsetを作った学習期間。
- ラベルは特徴量inputと別の経路に置く。将来予測の入力に対象試合のscore/result列を持たせない。

学習用履歴と将来推論用履歴を区別する。学習対象は2015〜2025 ordinary J1のみ。2026 Hyakunen・2026/27は重みやScalerのfit・ハイパーパラメータ選択に使わない。将来推論では、既存の承認済みidentity・結果検証契約を満たす過去2026結果を、その時点で観測済みのElo/Form履歴としてだけ扱う案とする。競技・90分結果の扱いを正式freezeで固定し、Cup/AFC等を暗黙に追加しない。

## 時刻・履歴の合格条件

1. `nn_original_kickoff_events_v1_1`を維持する。ID30700はfeature=2024-08-24 19:03より前、履歴は8月24日より前の終了試合、label=最終Draw、結果反映=11月23日以降。source CSVは11月22日のまま。
2. 同一JST日付の特徴量を全部freezeしてから、その日の結果を後日の履歴へ反映する。中断時の1-0を完成済み結果にせず、11月22日の他試合にも最終結果を混ぜない。
3. 未知・変更された中断/再開・同日クラブ衝突・曖昧なidentityはSTOP。結果を通常扱いするfallbackを置かない。
4. 将来は、履歴試合の終了日が対象日より前であり、正式確定のsourceを実際の予測保存前に取得していることを確認する。朝に取得した前夜結果を使う場合、公開が対象日の00:00以前だったと偽って記録しない。
5. 予測対象日より前のcandidateや過去scheduledがあれば履歴不完全として保留する。欠けた試合を黙って落としてEloを再構築しない。
6. source掲載の後日訂正を過去のsnapshotへ上書きしない。訂正は新revisionで管理し、当初予測で何を知っていたかを残す。
7. cross-fit基準の訓練年が対象年より前であること、残差Scalerのfit行集合、クラス[0,1,2]を検証する。フル期間fit済み基準のin-sample値で代替しない。

## 次の実装段階で行う検証案

実データのfitや性能評価より先に、既存テストへ必要最小限の合成検証を追加する案とする。現在は実装・実行しない。

- 対象試合・同日・未来結果を改変しても対象特徴量が不変となる反事実テスト。
- ID30700の8月24日前状態、11月22日まで反映なし、11月23日から一度だけ反映。
- 履歴欠損と正当なcold start、home/away逆転、重複・ID衝突、未知中断の拒否。
- 前処理のfold分離、zero residualと基準確率の一致、有限差分勾配照合、有限確率・合計1。
- 将来入力に対象scoreがないこと、時刻witness不足時に予測batchを作らないこと。

監査が不合格なら行を後付けで除外して件数を合わせず、理由と該当集合を記録して仕様確定を保留する。Phase A: **BLOCKED** / Phase B: **NOT_AUTHORIZED**。
