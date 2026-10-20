# NN v2 Phase 2.5B-2 公式時刻証拠パイロット

判定：**HOLD_EVIDENCE_ACQUISITION**。2026-10-20 JST。HISTORY/PREDICTIONもHOLD。

`feature/nn-research-v1`、HEAD `9942458087829f9f6a917200e706bc1e29760d31`、開始時cleanを確認した。Study `nn_v2_residual_20261020_01`、NN v2 `TRAINED_AND_SEALED_RESEARCH_ONLY`。Phase 2.5B文書・不足候補・個別matrix、Phase 2.5Aの全packetからのbinding再生成、model/study/artifact sealと全53payloadのSHAを接続前に照合した。入力不一致は0件。

## 取得結果

保存公式一覧から抽出済みの正規リンクだけで、百年構想6件・2026/27 J1 6件を事前選定した。選定規則・通信・解析契約は [PROTOCOL.md](PROTOCOL.md)。個別ID/URL/理由とrecord SHAはローカルに固定した。

| 結果 | 件数 |
|---|---:|
| 事前選定 | 12 |
| 取得した一意URL | 7（百年構想6・2026/27は1） |
| HTTP 200・完全body保存 | 7 |
| transport失敗・403/429・timeout・redirect追従・再試行 | 各0 |
| 固定契約で解析成功 | 6 |
| 固定契約で解析HOLD | 1 |
| 事前選定内の未取得 | 5 |
| パイロット対象外の未取得 | 276 |
| オフライン修正確認で全項目一致 | 7 |

実通信は全URL各1回だけ。前のresponse完了から次request開始までの最短間隔は **5.17033秒**、最大body **128,013 bytes**、合計 **871,392 bytes**。TLS検証・socket timeout10秒・親worker deadline10秒・本文上限2 MiBを適用した。HTTP 200という通信成功と、解析契約の合否を分けている。

初回は私が追加した制限検出が、計測script内の定型文「429: Too Many Requests」を実際のアクセス制限と誤検知した。元snapshotと停止記録を保持し、表示本文に制限がないこととstrict parserの一致をオフライン確認した。検出を表示本文に限定してテスト後、最初のURLを再取得せず、別preflightで選定済み未取得11件だけを継続した。実403/429・timeoutの停止を解除したものではない。

継続中、最初の2026/27ページで、固定した大会見出し期待値が年度prefixを欠いていたため再びHOLDとなった。実ページの「2026/27」は既存の保存済み2026/27詳細templateにも存在し、試合結果の矛盾ではなく私のpreflight生成の不備だった。年度付き全文をsourceから準備する処理を追加し、保存rawで検証した。**この2回目の停止後は追加通信せず、残り5件にはアクセスしていない。** 停止時の固定判定は上書きしていない。

## 証拠として確認できたこと

7件ともSFMS02自身のID、TeamMasterの対戦クラブ、source日付・kickoff、90分得点が既存sourceと一致した。百年構想のPK3件は90分結果と分離し、PK勝者・大会勝点を代用していない。取得sampleに延長試合はなく、延長period分離は既存の合成テストで検証した。

7件の備考はすべて検証済みの空備考形式で、既存strict parserが解釈できた。新規の中断・再開を示す注記は確認0件。残り281件に例外がないとは主張しない。記事の「リーグ中断・再開」と個別中断を混同していない。

実取得日時はすべて2026年10月20日。request開始・response完了UTC、status・最終URL・Content-Type、raw bytes/SHA、metadataとrequest SHAの関係を個別保存した。当初発表日程・延期告知・試合当時のpublication as-ofを立証したことにはならず、追加資料は別途必要。

取得済みHTMLに実在する公式「日程・結果」「お知らせ」のindexリンク2件を追加資料の探索候補として記録した。特定試合の当初発表・延期告知への直接リンクはまだ特定できていない。その候補URLへのアクセスは0件で、必要な追加告知の件数も未確定。

## 次の取得への判断と見積り

安全なtransportとURL/identity対応は7件で確認でき、修正後のstrict解析も保存raw7件で一致した。ただし、年度を含む修正済みpreflightでの2026/27取得pilotと、選定したkickoff差・binding比較の層は未検証である。**部分的な成功から全件取得READYへ進めず、HOLD_EVIDENCE_ACQUISITIONを維持する。** 修正後に残った実装不具合はテスト上0件だが、修正後の通信pilot完了を意味しない。

未取得は **281件＝選定内5＋選定外276**。固定解析HOLDの保存済み1件を含む形式上の未解決候補は282件。保存済み1件の再解析には新規requestは不要。残りの公式詳細取得は、別承認があれば最大281 GET・各URL1回を上限とする案である。追加告知取得は別枠であり、現在は未承認。

5秒間隔だけで最低23分20秒、今回平均の通信時間で約24分36秒＋process/保存overhead、10秒timeoutを全件使う場合は約70分10秒＋overhead。元288件全体なら最大約71分55秒。実際には異常時にその場で停止する。

今回平均bodyで未取得281件のrawは約35.0 MBを見込む。設定上限ではbody合計562 MiB。metadata等を含めprimary・別ドライブbackup・独立展開先に各600 MiB、合計約1.8 GiBの枠を確保する案とした。成功率・全件の構造互換性・当初日程の十分性を保証する見積りではない。未取得リストの自動実行は行わない。

## 検証・保護・保存

新規合成テストと既存strict parser等の関連検証は **156 PASS**（warnings-as-errors）。URL/ID完全一致、件数・host上限、rate制限、timeout/403/429停止、再試行拒否、SHA、曖昧な注記、既存sourceへの書込み拒否、reparse point拒否、未知例外HOLD、定型script誤検知、年度付き見出し、継続時の合計上限・URL再取得禁止を確認した。

保護対象9,945ファイルを接続前後で比較した。事後結果は [protection-verification.json](protection-verification.json)。Champion A、NN v1/v2、保存予測14件・再現98件、元raw/metadata、運用runtime/publication/config、Windowsタスク2件、他worktreeとmainに変更はない。新規出力とbackup用子フォルダだけにACLを設定した。

raw・metadata・request/response・seal・各停止receipt・旧/新実装・個別解析・未取得候補・追加資料候補・protection・JUnitは `%LOCALAPPDATA%/J1AI/NNResearch-phase2_5B_2-20261020-180825` に保存した。rawを含むpayloadは別ドライブへ新規backupし、ZIP CRC、全SHA、独立展開先の全SHAを照合した。詳細は [backup-verification.json](backup-verification.json)、公開するSHA索引は [local-evidence-index.json](local-evidence-index.json)。GitHubへの追加は指定どおり集計・仕様・SHA・テストだけとし、取得実装本体、個人パス・raw・cookieを含むmetadataはローカル/backupに保持する。公開テストは環境変数で指定した封印済み実装をSHA照合して使い、今回もその形で全40件を実行した。

実データfit **0**、性能評価 **0**、実試合確率計算 **0**、実T0登録 **0**、対象登録 **0**、将来予測保存 **0**。7件の取得は履歴へのadmissionやcompletion bindingの拡張ではない。学習済みNN・Champion A・運用publicationへ新規結果を接続していない。

HISTORY/PREDICTION: **HOLD**。Phase A: **BLOCKED** / Phase B: **NOT_AUTHORIZED**。
