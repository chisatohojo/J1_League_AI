# NN v2 Phase 2.5C：証拠B・C・D独立監査

正式判定：**NN_V2_BCD_EVIDENCE_AUDIT_COMPLETE**。これは保存証拠の監査完了であり、B・C・D成立や予測開始の判定ではない。**HISTORY／PREDICTIONはHOLD、Phase AはBLOCKED、Phase BはNOT_AUTHORIZED**。

研究baseline `42bd4050df5fef09f5e3887785056d0e69cec7c6` から独立した `feature/nn-v2-bcd-evidence-audit` で実施した。元の研究branch・他worktreeは変更していない。Studyは `nn_v2_residual_20261020_01`、モデルは `TRAINED_AND_SEALED_RESEARCH_ONLY` のままである。

## 288件の独立照合

| 証拠 | PASS | HOLD | 確認結果 |
| --- | ---: | ---: | --- |
| A：最終詳細の事実・結果・備考 | 288 | 0 | 公式URL・ID・source行・TeamMaster・raw/metadata/request・seal・strict解析全体が既存結果と一致 |
| B：実イベント・結果利用可能時刻 | 0 | 288 | 全件の最終結果取得上界、99件の以前の完了witnessは成立。実開始・中断/再開・終了の全来歴は不明 |
| C：当初日程・変更告知の来歴 | 0 | 288 | 1,188保存観測行を元revisionで照合。20件に開始前の観測とkickoff表記差があるが、当初日程・変更告知の連鎖は未成立 |
| D：予測時点までの実取得証明 | 0 | 288 | 実NN予測cutoff・完全な過去結果依存traceは未登録。仮のcutoffを置いてPASSにしない |

取得済み288、未取得0、公式ID・URL・identity衝突0。内訳は百年構想189件、2026/27通常J1 99件。PKあり50件は90分結果から分離し、この288件中の延長ありは0件だった。母集合は旧不足詳細288件であり、凍結2026履歴300件全体ではない。既存の別12詳細を今回監査済みとは扱わない。

受理済み12 revision、旧固定source 421ファイル、既存source snapshot 24 manifest（既知formatのみ）、420関連ファイル（HTML198・metadata198・manifest24）を照合した。調査範囲内に288件の当初日程・変更告知の完全な対応証拠はなかった。調査外にも資料が存在しないとは認定しない。[軸別集計](evidence-A-D-summary.json)と[不足・追加調査計画](EVIDENCE_GAPS.md)を参照。

最終結果を後日取得できたことは、その取得時点の観測上界だけを証明する。通常の試合時間から終了UTCを計算せず、取得時刻を過去へ戻さない。Dは対象自身の最終結果を開始前に持っていることを要求するものでもない。必要なのは、実cutoffまでに取得済みの完全な**過去結果**traceである。

## 既存証拠・時刻例外の保持

Phase 2.5Aのbinding4件は正しい実snapshot・公式identity・raw/metadata・結果・10月17日の取得日時と一致した。元publicationの不整合を修正せず、10月11日に取得済みだったとも扱わない。4件以外への拡張は0。

旧9隔離packet・seal・receiptを元の保存領域と照合し、すべて元HOLDのまま保持した。B16の45 PASS／3 HOLD、B18の103 PASS／6 HOLD、旧v5累計279 PASS／9 HOLD、v6を含む282 PASS／6 HOLD、B19のv7独立288 PASS／0 HOLDはそれぞれ別の正式記録であり、変更していない。備考規則の追加・変更は0である。

ID30700は対象288件外の既存例外として3原本SHAと方針を確認した。2024-08-24の当初開始前特徴量、2024-11-22再開後の最終Draw、11月23日以降の研究用反映境界を維持する。中断時の暫定1-0は完成結果ではなく、境界時刻は最終笛でもない。後日取得証拠によって2024年当時のas-of取得は立証できない。

旧registryの31ケースも独立照合した。11件の可視語コンテキストSHAを保存原本から再計算し、全文脈を読み、リーグ中断期間・再開やpreviewの記述であることを再確認した。20件の日程表記差は固定revisionの全観測値と一致した。これらから個別中断の不存在や履歴採用を推定しない。[例外registry照合](timing-registry-audit.json)

## PIT・将来評価への判断

現状、実履歴admissionは0件で、将来adapterへの実結果投入は承認しない。B/Cは追加の真正なイベント・当初日程・変更告知資料で解消する可能性がある。Dの歴史的取得記録が存在しなければ、新たな取得で過去PITを遡及成立させることはできない。

最新の**保存済み**日程には未開始予定27節270件がある。例示した先頭20節200件にはkickoff未確定110件、match-page ID未確定190件があり、T0も未登録である。別namespaceのdata-site ID未確定は200件。これは現在の公式サイトの新規確認でも、対象登録でもない。凍結NN履歴100 completedのrevisionを、最新保存revisionの110 completedへ差し替えていない。[計画上の成立条件](future-evaluation-feasibility.json)を参照。

主比較は[既存将来評価計画](../FUTURE_EVALUATION_PLAN.md)どおりv2 residual対v2 Elo基準の同一試合・同一cutoffのpaired比較とする。Champion Aは正式保存予想のidentity・時点条件が一致する場合のみ外部比較。既存の研究・後日再現集合をfresh holdoutと呼ばず、今回の確率計算・Log Loss/Brier/的中率比較は0である。

次は[証拠計画](next-evidence-plan.json)に従う独立審査が必要である。正確な候補リンクをまだ固定できないため、今回の許可URL集合は空、GET上限0、permit0。履歴採用契約、全300件のcoverage、将来adapter実履歴監査、T0・公式節集合・ID確定、paired予測保存はいずれも別承認であり、この監査完了で開始しない。

## 検証と保護

今回の最終テストは **224 PASS／0 FAIL／0 error／0 skip**、warnings-as-errors。新規の純粋監査契約55件、既存回帰169件（future history48、binding40、v7備考62、研究時刻19）。回帰にはID30700、同日・未知時刻・改変拒否、PK/延長分離、Scaler fit・運用書込み禁止を含む。既存研究時刻テストのNoFitPipelineは合成stubであり、実モデルfitではない。[テスト証跡](test-results.json)

初回テストharnessはpytest既定log出力先を書込みguardが拒否し、収集前に中断した。私的logと旧scriptを保持し、専用tempにlogを明示した別版で224件を完走した。集計公開補助scriptにもregistry配置の参照誤りによる停止があり、出力作成前の旧script/logを保持して正しい保存先を読む別版で完了した。いずれも取得runや原本を書き換えたものではない。

コンテキスト補助監査は証拠のfsync/readback完了後、consoleのcp932表示で停止した。元のexit/logを保持し、保存済み証拠を別処理で独立読戻し・確認した。表示失敗を証拠不一致とは扱わず、元processが正常終了したとも記録していない。

新baselineの**48,429保護ファイルでSHA・identity/metadata差分0**。モデルsealと53 payload、既存予測、公式source/publication、旧原本・解析契約・receipt、main・研究branch・週末worktree・他worktree、Desktop/feed、07:00／22:00タスク定義・状態を再照合した。過去のタスク失敗や未帰属差分を正常更新と再認定せず、今回の研究起因とも推測しない。今回の監査区間では変化0。[保護監査](protection-summary.json)

公開対象は[監査契約](CONTRACT.md)、純粋判定コード、合成テスト、集計・SHAだけとし、個別原文・氏名・raw/metadata/request・個人パスは新しい私的台帳へ保持した。[入力・出力SHA](input-output-sha256.json)でその版を固定した。原本の読取り・新規監査成果のflush/fsync/readbackは行ったが、電源断耐性やOSネットワーク隔離を今回実証したとは主張しない。

新規公式GET、robots、新permit、取得run再実行、実モデルload/fit/推論、実確率計算、性能評価、T0、対象登録、履歴admission、将来予測保存はすべて0。[独立ゲート](readiness.json)・[次工程](next-stage.json)
