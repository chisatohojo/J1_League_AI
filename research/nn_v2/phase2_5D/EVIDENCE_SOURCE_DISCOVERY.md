# NN v2 Phase 2.5D：B/C/D取得候補の調査・固定準備

判定：**NN_V2_BCD_SOURCE_DISCOVERY_PARTIAL**。ローカル調査・合成検証・保護監査は完了したが、試合別の当初日程・変更告知URLとアクセス条件が未確定で、実行可能な取得permitの条件はそろっていない。新規GET・permit・モデル実行・登録は0。**HISTORY/PREDICTION：HOLD、Phase A：BLOCKED、Phase B：NOT_AUTHORIZED**を維持する。

基準は `feature/nn-v2-bcd-evidence-audit` の `2d2c051a76bf2b17cfac3f5f331667e9b2c14c78`。独立した `feature/nn-v2-bcd-source-discovery` で作業した。基準の成果物・実装・テストを読み、SHAを検証した。元worktree・main・旧研究branch・週末worktreeを変更していない。全ゲート合格時のみcommitする指示に従い、PARTIALの成果は未commitで保持し、pushしない。

## 1. 既存の正式な証拠要件

意味を一般化して再定義せず、[Phase 2.5C契約](../phase2_5C/CONTRACT.md)の成立要件を次のとおり参照する。

| 軸 | 同契約の成立に必要な内容 |
| --- | --- |
| A | 「固定identity・規定時間結果・備考と封印原本の一致」 |
| B | 「実開始、中断・再開の来歴、終了・結果利用可能性の証拠、実取得時刻」 |
| C | 「当初の公式日程、変更の対応関係、公式告知とその取得証拠」 |
| D | 「実際の予測cutoff、固定source、完全な過去結果依存traceと取得証拠」 |

[PIT監査計画](../PIT_AUDIT_PLAN.md)、[将来評価計画](../FUTURE_EVALUATION_PLAN.md)、[固定時刻方針](../../nn_v1/TIMING_POLICY.md)、[completion binding契約](../phase2_5A/BINDING_CONTRACT.md)を維持する。A288 PASS、B/C/Dは各0 PASS・288 HOLDのままである。本工程の関数は証拠の形と欠落を検査するだけで、肯定的な合成入力でも軸のPASSや履歴admissionを返さない。

試合の存在、記録されたkickoff、実際の開始、当初予定、変更の発表、情報公開、情報取得、実予測cutoff、過去結果の確定・利用可能性は別の事実である。現在の結果や変更後の予定だけで、過去の発表や取得状態を立証しない。

## 2. 保存資料の棚卸し

原本は読取り専用で、ローカルの資料識別子ごとにsource URL、保存場所、raw/metadata/request SHA、実取得UTC、revision、対応fixture、軸、欠落を保持した。公開台帳には個人パス、原文、氏名、個別履歴を含めず、非公開台帳のSHAを保存する。

| 原本資料の記録単位 | 件数 | 内容と限界 |
| --- | ---: | --- |
| B19封印詳細packet | 288 | 原本・metadata・request・expected・sealを照合。Aと取得上界。実イベントの全来歴ではない |
| 保存済み公式snapshot内のHTML | 198 | 日程検索・完了witness・match discovery等。24 manifestの保存関係を照合。うち既存99完了witnessの対応を引き継ぐ |
| 以前のローカル公式HTML | 13 | 百年構想一覧1と先行詳細等12。詳細12は今回288件の外にある参考資料で、サンプルへ混入しない |
| ID30700の既存原本 | 3 | 既存の中断・再開方針の隔離参考。2026の調査対象や新規取得対象にしない |
| **原本資料の記録単位の合計** | **502** | 複数時点の同じURLを含む。502種類の試合・URLという意味ではない |
| 派生CSV／受理revision manifest | 14 | 結果CSV2と固定revision12。原本の代替にせず、公開完了UTCをmtime・manifest作成時刻から補わない |

棚卸しで固定したファイルは2,300件。原本資料502記録、派生14記録、uniqueファイル数は異なる数え方である。私的台帳に各資料の取得証拠とpublication時刻未成立を記録した。古いmetadataに独立request原本がなければnullを維持し、新詳細のrequestで過去の欠落を補完しない。保存UTCはtimezone・記録精度を保持するが、時計の絶対的真正性を保証しない。

旧9隔離、ID30700、Phase 2.5Aの4件binding、旧parser/v2〜v7規則、過去の取得結果は変更していない。履歴300件に対する今回の288件という部分集合も変更しない。

## 3. URL候補と確度

今回は外部仕様の新規参照も行わず、保存HTMLのhref（相対リンクを含む）と検証済みmetadata、既存コード・文書だけを用いた。相対URLは保存sourceをbaseにRFC解決し、元href・start-tag・source SHA・行位置を非公開に保持した。IDの連番生成、リンクのない試合URL生成、検索エンジンによる対応付けは行っていない。

[SOURCE_CANDIDATES.json](SOURCE_CANDIDATES.json)に候補と確度を記録した。抽出したdistinct URLは**1,489**で、分類は試合詳細リンク1,474、日程・結果indexリンク10、ニュース／プレスリリース入口2、ID30700の隔離参考3。この数には既取得・対象外・別年度のリンクを含み、許可対象数ではない。425 URLには棚卸し範囲で実取得記録がある。現在の存在、初回公開時刻、過去版取得の可能性は別途UNKNOWNである。

新たに検討する入口は次の2つだけである。

| 保存実リンクから得た入口 | 想定目的 | 未確認事項 |
| --- | --- | --- |
| `https://www.jleague.jp/j1/news/` | 2026初期日程・変更・中断/再開告知の具体リンクを発見できるか調査 | 現在の応答、過去記事への到達性、アクセス条件、288件との対応 |
| `https://aboutj.jleague.jp/corporate/pressrelease/` | 発表資料の具体リンクを発見できるか調査 | 保存公式ページ上の「プレスリリース」リンクのみ確認。host/operatorの追加審査・許可、現在の応答、アクセス条件、対象資料 |

後者は旧data-site/www許可hostに含まれない。保存リンクがあるだけで、新hostへ接続可能とはしない。どちらも特定試合の告知そのものではない。**288件と対応が立証された当初日程・変更告知URLは0件**である。入口探索が成功してもCのPASSにはしない。

日程・結果の既取得検索URLは現在状態の参考に限る。`back`は状態依存の可能性があるため対象外とし、対象大会を確認できないframe（1/35以外）、対象外年度・大会・詳細リンク、旧288詳細とID30700参考を取得対象へ加えない。コードのURL正規表現・日付window builderは形式の仕様だけで、具体URLの存在や歴史的公開を証明しない。今回それらを用いてURLを生成していない。

## 4. 最大10試合の調査候補

固定288台帳のordinalを用いて、分類ごとの先頭から重複なく選んだ。未知備考や結果を探しに行く選定ではない。実identity・公式ID・正確なURL・revision・選定理由は非公開台帳へ封印し、[SAMPLE_CASES.json](SAMPLE_CASES.json)には対応SHAと匿名aliasを保存した。

| 選定理由 | 件数 |
| --- | ---: |
| kickoff表記差あり、変更原因は未証明 | 4 |
| 保存観測で表記差を検出していない、match-page ID既知 | 2 |
| PK分離を要する百年構想、match-page ID bridge未立証 | 2 |
| 保存観測で表記差を検出していない、match-page ID bridge未立証 | 2 |

match-page ID既知6、未立証4。全10件で実NN予測cutoff・完全な結果traceは未登録。旧9隔離とのoverlap0、ID30700の混入0。特定の変更を検出しなかったことを「日程変更なし」の証明へ昇格させず、表記差を延期や実際の日付変更と断定しない。実際の延期を立証したサンプル、変更不存在を立証したサンプルは選べていない。この不足もPARTIALの根拠である。評価対象登録、HISTORY登録、既存隔離の解除ではない。

## 5. 時刻証明とDのtrace

7種類の時刻は、timezone、記録精度、原本SHA、根拠種別、実取得との関係、証明可能性を別フィールドにする。日付のみ、時刻未公表、出典不明、mtimeしかない情報はHOLD。予定時刻を実kickoffへ、取得UTCを公開UTCへ、当日00:00の研究用境界を実取得UTCへ置き換えない。cutoffをわずかに過ぎる取得・公開や、後日更新された版は過去PITの証明にならない。開始前であることだけでも不十分である。

Dの完全traceに必要なのは、実際の予測cutoff・feature cutoff、source revisionとpublication/取得証拠、対象自身を除く完全な過去試合集合、各試合の原本SHA・90分結果とPK/延長の分離、実開始・終了/確定・公開/利用可能・実取得時刻と出典、研究用result-effective境界、集計実装SHAと例外registry、未完了/延期/中止/再試合・訂正の処理、完全性照合である。各witnessのorigin snapshotと、選択したsource revisionへのbindingを区別する。

完全な過去集合が不明な状態を空履歴やcold startとして処理しない。重複witness、対象自身の結果、source revision矛盾は拒否する。異なる版をlatestへ自動差し替えず、後日確認できた結果を過去に参照したtraceへ追加しない。今回、実特徴量・Elo/Form・結果event・過去結果traceは生成していない。既存Champion Aの保存予想時刻があっても、NNの同一cutoff・同一source・完全traceの代替ではない。

後から得た資料がB/Cの来歴を補う可能性はあるが、当時の取得ログが存在しなければDの歴史的証明は遡及作成できない。将来の新たな実cutoffに対する証拠保存・T0は別承認である。既存の20公式節200試合案や未確定ID・kickoffを自動登録しない。

## 6. Permit条件と次工程

既存B18の109件permit SHA、消費receipt、元scopeを確認した。消費済みの固定詳細取得permitであり、今回のindex・告知・新hostは対象外。旧permitの拡張・再利用・新permit作成は0。各候補は `execution_authorized=false`、現在のGET許可上限は0である。[PERMIT_PLAN.json](PERMIT_PLAN.json)は承認準備資料でありpermitではない。

次工程の案を分離する。

1. **P0：追加のオフライン候補確認。** 保存済み資料の別の保管場所が判明すれば、原本SHA・発行主体・fixture対応・告知日付を読取り専用で確認する。見つからなければ不明を維持する。
2. **P1：入口2ページの限定探索案。** 上の正確な2 URLだけ、各1 GET・最大2 GETの新しい別承認を検討する。第三hostの正当性・許可、アクセス条件の確認方式、必要なrobots等の正確なURL・別枠件数が未確定なので、現時点では実行不可である。data-siteのrobots証拠を他hostへ流用しない。アクセス条件確認の通信を2 GETへ紛れ込ませない。
3. **P2：取得後のオフライン固定。** P1を別承認で実行できた場合にだけ、保存したindexから正規実リンク・対象identity・資料種別を確認する。本文にないAPI・pagination・追加ページへ自動アクセスしない。個別告知URL集合と件数が決まるまで、その取得上限は0。
4. **P3：具体的告知の別承認。** URL集合・fixture対応・目的・期待値・全上限・保存先・コードSHAを新工程で固定する。後日取得が過去Dを証明しないことを再確認してから、別permitと明示承認を受ける。

P1の提案値はHTTPS/TLS・hostname検証、各URL1 GET、retry/redirect/parallel 0、socket10秒・親worker12秒、通信完了から次開始まで5秒以上、本文2 MiB/件・合計4 MiB、全体90秒・cleanup2秒である。これらはコードに実装した実行設定ではなく、未承認の設計値である。条件が厳しい場合は厳しい方を優先する。アクセス条件不明、403/429、redirect、通信終了不明、上限超過、未知host/構造、SHA/identity/結果矛盾、保存失敗ではSTOP。自動retry、許可拡張、他URLへの代替、規則緩和を行わない。

保存は独立したcreate-new研究領域へ、request開始/response完了/snapshot保存/検証完了の実UTC、URL・status・Content-Type・bytes、raw/metadata/request SHA、revision、fsync/readback、seal/receiptを残す。旧原本やpublicationに追記しない。失敗証跡も保持し、自動cleanup・無断再開を行わない。

## 7. 検証・保護・未完了事項

今回のテストは **303 PASS、FAIL/error/skip 0、warnings-as-errors**。新規の静的・純粋契約79件、関連回帰224件を今回再実行した。既存証跡を新規実行として足していない。証拠軸の厳密な指定、欠落HOLD、日付のみ/精度/時刻種別、cutoff後・後日版、revision、witness重複、隔離対象除外、URL・host未承認、完全trace欠損を検証した。合成の肯定的traceでもD PASS/admissionを返さない。

私的監査は書込み先を新研究領域へ限定し、通信・子process・モデルdeserialize等を拒否するPython audit guard下で実行し、禁止操作の試行0だった。テストの関連回帰がimportするモデルクラス定義は実モデルloadではなく、実fit/predict/deserializationは禁止した。Python guardをOS隔離実証と呼ばない。

保護baselineは現時点の**49,570ファイル**。前後のSHA・file identity/metadata差分0、モデルseal/53 payload・既存予測・原本・旧witness・9隔離・例外方針・source/publication・task定義/状態・main/他worktree不変。前工程の48,429を固定期待件数にせず、前工程worktreeと新しい証跡も保護範囲へ追加した。既知のタスク失敗等を修復・再実行・正常認定していない。[PROTECTION.json](PROTECTION.json)、[VALIDATION.json](VALIDATION.json)

PARTIALとして残すのは、試合別の具体的な初期日程/変更告知URL、実イベント資料と正確な公開/結果時刻、当時の取得trace、第三hostとアクセス条件、条件確認を含めた全リクエスト上限である。これらを推測してREADYにしない。原本と派生結果、1,489リンクと取得許可、10調査候補と正式評価対象を混同しない。

**次に必要な承認**は、P0に用いる追加保存資料の提供、またはP1の限定探索についてhost・アクセス条件確認URLと別枠通信上限を固定した後の明示承認である。今回は試合データGET、robots取得、permit発行、実モデルload/fit/推論、実確率計算、性能評価、T0、対象登録、履歴admission、予測保存、本番処理、mergeはすべて0。
