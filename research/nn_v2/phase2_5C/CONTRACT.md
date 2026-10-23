# Phase 2.5C 独立監査の契約

対象はPhase 2.5B-19で封印した288件の集合である。確定済みAの解釈、時刻ポリシー、旧parser、v2〜v7 adapter、個別review-ruleを変更しない。監査対象の追加、結果eventの生成、履歴admission、予測、評価、取得機能を持たない。

## 判定と証拠の境界

各fixtureをA・B・C・Dで別々に判定する。各構成要件は `ESTABLISHED`（照合済み）、`NOT_ESTABLISHED`（必要証拠が未成立）、`UNKNOWN`（時刻・状態等が不明）とし、全構成要件が成立した軸だけをPASSにする。不足はHOLD、SHA・identity・結果・時計の矛盾は独立したSTOPとする。

| 軸 | 成立に必要な内容 | 代用できない情報 |
| --- | --- | --- |
| A | 固定identity・規定時間結果・備考と封印原本の一致 | 計算可能な特徴量だけでは代用しない |
| B | 実開始、中断・再開の来歴、終了・結果利用可能性の証拠、実取得時刻 | 記録されたkickoff、通常の試合時間、後日最終ページだけではイベント時刻を確定しない |
| C | 当初の公式日程、変更の対応関係、公式告知とその取得証拠 | 現在の日程、開始前の途中revision、kickoff表記差だけでは当初日程・変更告知を確定しない |
| D | 実際の予測cutoff、固定source、完全な過去結果依存traceと取得証拠 | 仮の00:00、後日原本、対象自身の完成スコアを使わない |

確認した最終結果ページの取得完了UTCは、その結果を**遅くともその時点で観測できた**という上界である。初回公開時刻、最終笛、試合当時の取得証明ではない。取得UTCを試合日へ変更せず、HTTP Date、mtime、manifest作成時刻を結果公開UTCとして代用しない。ローカル記録の絶対的時刻真正性まで保証しない。

私的台帳の `earliest_verified_result_acquisition_upper_bound_UTC` は、今回個別に検証した詳細と完了witnessの間での最早値である。全世界での初公開・全保存資料中の最初の取得を意味しない。一覧の取得記録は別フィールドに保持する。旧witnessに独立request原本がない場合、新詳細のrequestで補完した扱いにしない。

## 固定入力と独立した照合

封印packet indexの288 identity、公式詳細URL、公式ID、source CSV・行SHA、TeamMaster、source revision、raw/metadata/requestを照合する。旧解析全体のSHAを検証したうえで、SHA固定のstrict parserの純粋関数だけを抽出し、同じ原本のstrict解析全体を再計算してv7のstrict解析と完全一致させる。備考はv7の確定解釈を保持し、再分類しない。旧取得scriptのmodule、worker、CLI、実行入口はimportしない。

受理済み12 revisionの日程行を保存時の観測と照合する。補助source corpusの範囲は既存publicationに結びつくsnapshotと保存済み公式raw領域であり、その外の告知が存在しないとは主張しない。今回走査したmanifestは24件すべて既知formatだった。候補URLの生成・検索・新規アクセスは行わない。

Phase 2.5Aの4件のbindingは、元publicationと実snapshotの不整合記録を維持したままSHA・raw/metadata・公式identity・結果・実取得日時を照合する。取得は10月17日であり、10月11日に取得済みだったという証拠へ変換しない。bindingを他fixtureへ拡張しない。

## 時刻ポリシーと履歴採用の非接続

2015〜2025の固定ポリシーを変更しない。ID30700は今回の288件の外にある既存例外として、当初2024-08-24 19:03 JST前の特徴量、2024-11-22再開後の最終1-1 Draw、11月23日00:00 JSTからの研究用結果有効境界を保持する。中断時1-0を最終結果へ使わず、境界を最終笛と呼ばない。後日取得した3原本は当時as-ofの証明ではない。

Dの依存traceは対象自身を含まない完全な過去履歴を要求する。対象日以前という研究用境界と実取得を区別し、前日結果の有効境界が当日00:00に等しい場合の `result_effective_at <= history_cutoff` を維持する。朝取得した情報は実際の予測時刻までに取得済みかを別に照合し、00:00に取得済みだったと記録しない。未知と正当なcold startを混同しない。

この判定関数は純粋な監査用であり、渡された肯定的事実が合成上すべて成立してもadmissionは常にfalseである。履歴採用要求は拒否する。モデル、Scaler、offset、特徴量生成器、将来予測器、運用collectorとは接続しない。PK・延長と90分スコアを分離する。

## 保護・検証・公開

原本・旧9隔離packet・旧正式記録をread-onlyで照合し、新しい非公開fixture別台帳をcreate-newで保存する。各書込みはflush/fsync/readbackを行う。監査中の書込み範囲は独立worktreeと新規の私的監査領域、合成テスト用tempに限定する。Python audit guardは誤操作防止であり、OS隔離の実証ではない。

Gitへ公開するのは、この契約、集計、純粋判定コード、合成テスト、SHAだけである。非公開原本・metadata/request・個別の備考・氏名・個人パスを公開しない。合格した監査成果を保存してもHISTORY/PREDICTIONは解禁しない。
