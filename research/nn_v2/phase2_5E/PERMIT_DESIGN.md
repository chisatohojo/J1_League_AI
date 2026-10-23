# Phase 2.5E：ニュース／プレスリリース限定探索のPermit設計

判定：**NN_V2_BCD_PERMIT_DESIGN_PARTIAL**。アクセス条件、追加hostの運営主体・規約適用範囲、正確なrobots確認URLが未確定である。通信予算と保存・STOP契約を設計したが、**permitの発行・有効化・外部取得は0**。B/C/D、HISTORY/PREDICTIONはHOLD、Phase AはBLOCKED、Phase BはNOT_AUTHORIZEDを維持する。

## Phase 2.5Dの保全

前工程の未commit11ファイルを[元SHA台帳](../phase2_5D/SHA256-MANIFEST.json)・保存済みテスト/監査証跡と照合し、独立ローカル領域へcreate-newでコピー、全SHAと読戻しを確認した。内容は変更せず、今回の明示許可により `feature/nn-v2-bcd-source-discovery` へ **fb1ddb05eb4af9fe28c22252e8a2e7b64900f62a** としてcommit・通常pushした。local/origin/実remote一致・cleanを確認した。これはPARTIAL調査成果の保全であり、旧[VALIDATION](../phase2_5D/VALIDATION.json)の当時の未commit記録も改変していない。

保全前は前工程303 PASS・静的102項目の実装SHA/JUnitを検証して再利用し、新たに実行したとは計上しなかった。新しい保護再照合も49,570ファイル差分0だった。初回補助処理はshell経由の日本語ファイル名読取りで停止したが、11コピーは完成・不変だった。元出力を保持し、filesystemから正確な添付名を取得する別版で照合を完了した。原本や未commit成果物の不整合はなかった。[保全由来](INPUT_PROVENANCE.json)

このcommitから独立した `feature/nn-v2-bc-permit-design` を作成した。Phase D・旧研究・運用・週末worktree、mainは変更していない。前工程のPARTIALを今回の作業でREADYへ読み替えない。

## 1. 固定した探索入口

正確な値は[前工程P1](../phase2_5D/PERMIT_PLAN.json)から抽出した。どちらもschemeはHTTPS、有効portは443、明示portなし、queryなし。path末尾のslashまで固定する。

| 枠 | 完全URL | hostname / path | 資料提供主体・期待内容 |
| --- | --- | --- | --- |
| B1 | `https://www.jleague.jp/j1/news/` | `www.jleague.jp` / `/j1/news/` | 既存J.LEAGUE公式sourceとの保存リンク関係。ニュースindexからB/C関連告知の実リンクを探す |
| B2 | `https://aboutj.jleague.jp/corporate/pressrelease/` | `aboutj.jleague.jp` / `/corporate/pressrelease/` | 保存公式ページの「プレスリリース」リンク。運営主体の直接確認はUNKNOWN。発表indexを期待するが未取得 |

両入口の取得原本は保存corpusにない。hrefがあることは現在の応答・過去版の存在・公開時刻を証明しない。個別記事、pagination、API、CSS/JS/画像は許可対象0。リンク先を自動追加せず、取得後もオフラインで記事URLとfixtureの対応を審査する。

HTTP版、www有無の別host、CDNへのredirect、認証/Cookieの要否は未確認である。HTTP→HTTPSを試したり、hostやpathを推測変換したりしない。**すべてのredirect追従を0**とし、同hostへのLocationでもSTOPする。hostnameの構文上の比較と、現行DNS/運営主体確認を区別する。今回DNS照会・HEAD・接続試験はしていない。

## 2. Hostとアクセス条件

保存原本502記録のhrefとmetadata、既存の取得契約をローカルで調査した。旧B18の単回permit hostは `data.j-league.or.jp` であり、新scopeや新hostの許可には使わない。過去にwwwの公式match原本が取得できたことも、今回の入口・規約への実行許可ではない。aboutjは旧許可host集合の拡張審査が必要で、共通domain suffixだけで承認しない。

保存実リンクとして次の2条件ページを確認した。原本のsource SHA・tag SHA・行位置・取得UTCは非公開の新台帳へ保存し、本文はまだ取得していない。

| A枠slot | 完全URL・host | 方法 / 上限 | 目的・状態 |
| --- | --- | --- | --- |
| A1 | **UNKNOWN** / `www.jleague.jp` | GET / 最大1 | host固有のrobots確認。保存された正確なURLがなく、許可対象へ推測追加しない |
| A2 | **UNKNOWN** / `aboutj.jleague.jp` | GET / 最大1 | 同上。運営主体確認も必要 |
| A3 | `https://www.jleague.jp/general/kiyaku/` / `www.jleague.jp` | GET / 最大1 | 利用規約。リンクのみ確認、内容・現行性・path適用範囲はUNKNOWN |
| A4 | `https://www.jleague.jp/general/copyright/` / `www.jleague.jp` | GET / 最大1 | 著作権・利用案内。内容と自動取得条件はUNKNOWN |

全slotでredirect許可範囲は空、承認前取得不可、保存先は将来固定する `NEW_RESEARCH_ROOT/A` のみ。UNKNOWN slotは予約枠であり、URLが確定するまで消費できず、別URLへ流用できない。`/robots.txt` という既存data-site側のpathを別hostの取得証拠・確定URLとして移植しない。今回、未取得URLの実在を推測して補完していない。

プライバシーポリシーの保存リンク `https://auth.jleague.jp/contents/privacypolicy.html` もあったが、アクセス許可の代わりにはならず、auth hostを追加しない。このURLの予定GETは0。

旧data-site robotsは2026-10-21の404取得記録だけで、今回の両hostに適用できない。404はその正確なURLに規則を確認できなかったという意味に限定し、サイト全体の許可ではない。robotsのAllowがあっても規約・利用条件・頻度制限・自動取得禁止・認証要件の審査は別である。現在これらはUNKNOWN。aboutjにwww規約が適用されるとも仮定しない。[ACCESS_CONDITIONS.json](ACCESS_CONDITIONS.json)

## 3. 二つのPermit候補と予算

[PERMIT_CANDIDATES.json](PERMIT_CANDIDATES.json)は**DESIGN_ONLY**で、candidate IDだけを付けた。`permit_id=null`、`issued=false`、`activated=false`、現在のURL/host/root allowlistは空、許可GETは0。実行permitファイル、消費marker、worker、launcher、有効化スイッチを作っていない。候補JSONを実行用permitへ単純に書き換える経路もない。

| 予算 | 最大リクエスト | 本文上限 | header上限 | 有限process deadline |
| --- | ---: | --- | --- | --- |
| A：アクセス条件確認 | 4 | robots各64 KiB、規約/案内各1 MiB、合計2,228,224 bytes | 32 KiB/件 | 120秒 |
| B：入口探索 | 2 | 各2 MiB、合計4,194,304 bytes | 32 KiB/件 | 90秒 |
| 合算 | **6** | **6,422,528 bytes** | 全最大196,608 bytes | A/Bは別承認・別process。審査待ちを実workerの待機時間にしない |

本文＋headerの合算上限は6,619,136 bytes。TLSフレーム等を含むwire総量の実測・保証とは別である。HTTP圧縮の暗黙展開を避け、`Accept-Encoding: identity`を提案する。別encodingや未知構造はHOLD/STOPとして審査し、自動的にsize上限を増やさない。

共通条件はGETのみ、TLS証明書/hostname検証、parallel0、retry0、redirect追従0、通信完了から次開始まで全体で5秒以上、socket10秒、親worker12秒、cleanup2秒。User-Agent候補は既存研究workerの固定値 `J1AI-Research-Timing-Pilot/1.0` を引き継ぎ、サイト条件に適合するかは未確認のまま残す。Cookie jar・認証情報・個人browser profile・実GUIを使用せず、ログイン/CAPTCHA等が必要ならSTOPする。

接続intentを先に消費する。失敗応答・timeout・完了不明も1件として消費し、URLを再取得しない。redirect応答を受けた元リクエストも1件、禁止された追従やretryが記録に存在した場合も実数へ計上して独立STOPとする。A/B間の振替、失敗分の返却、空slotへの任意URL追加は禁止する。

4件のAで全条件を満たせる保証はない。aboutj側の規約や運営主体の別資料が必要なら、Aを自動増枠せずHOLDし、改訂設計と別承認を要する。A終了だけではBを開始しない。B前に各hostの真正な条件証拠・適用範囲を独立レビューし、実取得UTCとSHAで固定する。鮮度は提案24時間以内かサイト側のより厳しい条件。期限超過時の自動再取得は禁止する。

## 4. 保存・証拠・STOP

実保存先は未作成で、将来の明示承認後に独立create-new研究rootを固定する。原本・モデル・既存publication・予測・運用runtimeと重なるpathは拒否する。owner、DACL、reparse、ancestor/root identity、exclusive-createと公開直前の再照合は実worker接続前の必須ゲートであり、今回の純粋descriptorテストを実OSのACL実証とはしない。

`A/access-NNNN`、`B/index-NNNN`ごとにraw bytes、request、response metadata、seal、receiptを分離し、flush/fsync/readback/SHAを確定する。開始・取得完了・保存・監査完了の実UTCとtimezone/精度、URL/最終URL/method/status/headers/Content-Type/bytes、source/save identity、保存先file identity/path、入力/コード/revision、全attempt、redirect履歴、関連fixture（当初未結合）、不完全状態を保存する。未来の本文SHAはまだ存在しないためnullのままにし、取得後に実bytesから計測する。

headersやbodyの個別情報はローカル原本へ保持し、公開版は集計・SHAとする。Set-Cookie等を取得後に送信し直さず、headerの個人情報をGitへ出さない。原本を加工せず、派生解析は別versionにする。途中保存・失敗・不明状態を消さず、無断cleanupや自動resumeをしない。

STOPは、未承認/UNKNOWN host・URL・運営主体、重大な条件不明、認証/CAPTCHA、HTTP3xx/401/403/429/取得異常、TLS/timeout/不明終了、数/size/時間/rate上限、所有権/ACL/reparse/root差替え、既存ファイル上書き、permit失効/時計異常、source revision・SHA矛盾、未知のAPI等による取得、本番taskとの干渉である。未知redirect先を採用して通信するfallbackを持たせない。

新たに取得できるのは取得時点のindex/条件文であり、当初日程・実イベント・過去の公開時刻の直接証拠ではない。個別告知の正規実リンクをオフラインで固定して初めて、別の個別資料取得案を審査する。Dの当時の取得traceは後日資料で作り直せない。旧隔離9件は未解除・不変で、関連IDが本文に出ても参照候補に留める。ID30700方針も変更しない。

## 5. 実装・検証・保護

[design_contract.py](design_contract.py)は純粋な設計検証で、実permit・HTTP・DNS・モデル・ファイルI/Oの入口を持たない。SYNTHETIC_ONLYの模擬descriptor以外は拒否し、肯定的な模擬結果でもexecution/admissionをfalse、B/C/DをHOLDのまま返す。URLの構文上のhostname正規化は行うが、実リクエスト候補は完全URLの文字列一致であり、port表記、path/query、大小文字・percent表記を変えて範囲を拡張しない。

今回の最終テストは **402 PASS、FAIL/error/skip 0、warnings-as-errors**。新規99件と前工程を含む関連回帰303件を今回実行した。URL/host/path/query、redirect・retryと予算、未承認/期限/source revision、body/header cap、保存先descriptor、時刻/metadata/SHA、robots404、旧9件を参照してもHOLD維持、非接続を検証した。初版400 PASSの証跡も保持し、header境界検査追加後の402件を最終結果とする。両runを足し合わせない。実TLS・OS ACL・実workerや実サイトの制限を実証した結果ではない。

新baselineは**50,716保護ファイル**。前工程worktree・私的証跡も加え、モデルsealと53 payload、既存予測、公式原本/witness/旧9隔離、ID30700、source/publication、タスク定義/状態、main・全既存worktreeをSHA・file identity/metadataで照合する。既知の運用失敗を修復・正常認定しない。最終結果は[VALIDATION.json](VALIDATION.json)と[PROTECTION.json](PROTECTION.json)へ保存する。

## 6. 次に必要な承認

現段階では外部取得へ進まない。まず正確な両hostのrobots確認URL、aboutjの運営主体、適用規約とアクセス条件の確認方法を固定する必要がある。今回確認済みの条件ページ2 URLの取得を検討する場合も、bootstrapの許可範囲・上限・出力root・有効期限を別承認で固定する。未知hostや未知URLへ試しにアクセスして確認しない。

その後に、A最大4件の実条件確認、結果のオフラインレビュー、B最大2件の入口探索をそれぞれ独立して承認する。Bには記事取得・API・paginationを含めず、条件が不足すれば実行しない。モデル評価、実予測、履歴admission、T0、対象登録、本番task有効化は、いずれも今回の承認準備に含まれない。

今回の証拠取得GET/HEAD/DNS接続試験、permit発行/有効化、実モデルload/fit/推論、確率計算、性能評価、T0/登録/予測保存は0。ユーザーが明示した通常Git push・remote照合の通信だけを、証拠取得と分離して行う。PARTIALでも独立検証可能な成果を保存してよいという今回の指示に従い、技術検証と保護監査合格後のみこの専用branchへ保存する。mainや他branchへのmergeはしない。
