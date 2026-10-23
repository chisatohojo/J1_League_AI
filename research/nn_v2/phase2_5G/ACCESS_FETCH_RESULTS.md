# Phase 2.5G — A枠アクセス条件確認

判定：`NN_V2_ACCESS_CONDITIONS_PARTIAL`。
通信前基準はPhase 2.5F `e877c9f24ea779e934a062d32a145c0c0456cb42`。
明示承認されたA1〜A4のうちA1のみを取得した。A1の原本・通信整合性は合格したが、
固定した保守的robots parserでワイルドカード規則の適用を検証できず、内容審査で全体STOPした。
サイト全体の取得禁止を立証したという意味ではない。規則をその場で変更せず、再開もしない。

## 実行結果

| ID | 固定URL | GET | HTTP | 本文bytes | 状態 |
| --- | --- | ---: | --- | ---: | --- |
| A1 | `https://www.jleague.jp/robots.txt` | 1 | 200 | 646 | 原本封印成功、内容審査STOP |
| A2 | `https://aboutj.jleague.jp/robots.txt` | 0 | 未観測 | 0 | `NOT_STARTED_AFTER_GLOBAL_STOP` |
| A3 | `https://www.jleague.jp/general/kiyaku/` | 0 | 未観測 | 0 | 同上 |
| A4 | `https://www.jleague.jp/general/copyright/` | 0 | 未観測 | 0 | 同上 |

許可上限4 intentに対して使用1。未使用3回分はこの実行終了により失効し、後日再利用しない。
本文は合計646 / 2,228,224 bytes。redirect追従0、retry0、並列0、proxy使用0。
HEAD/OPTIONS/独立DNS probe/事前接続試験/B枠GETはいずれも0。
承認GET内部の名前解決1回・TCP接続1回・request1回を記録した。これをDNS通信0とは表現しない。
2件目の開始がないため5秒間隔の実測判定はN/A。実行器はhost間も含め完了後5秒以上を要求する。

request開始UTC：`2026-10-23T09:46:47.361661+00:00`。
応答取得完了UTC：`2026-10-23T09:46:47.645062+00:00`。
snapshot保存UTC：`2026-10-23T09:46:47.663444+00:00`。
ローカル実時計による記録であり、独立した絶対時刻真正性の証明ではない。過去の試合時点へ遡及しない。

raw SHA-256：`3f41d473ef69f00cd9eb1cd8f3e2c1f7a053bb21b75bef16a268cd3af242228c`。
TLS 1.3、証明書・hostname検証あり。全headers/status bytes、原本、metadata、request、
task、通信intent、worker/parent receipt、seal、内容審査、終了receiptを非公開領域へ保持した。
公開headerはContent-Type/Length、Date、Cache-Control、Serverのみのallowlistで、
Cookie等の機微headerは公開せず、受信したCookieを保存・再送するjarも使用しない。
全生headersを証拠として非公開保存することと、Cookie jarの使用は別である。

## robots・規約の評価

wwwのrobotsにはUser-Agent `*`と`spider`のgroup、Disallow規則、sitemap参照が存在した。
`spider` groupに`Disallow: /`があったことを、研究用UAへの包括的拒否と同一視しない。
研究用UAは`J1AI-Research-Timing-Pilot/1.0`で固定した。
観測したpath規則とgroupは[ACCESS_CONDITIONS_REVIEW.json](ACCESS_CONDITIONS_REVIEW.json)に構造化して記録する。
リンク先のsitemapは取得していない。

通信前に固定したparserはワイルドカード・終端指定の適用を未検証としてHOLDする契約だった。
実際の本文にワイルドカードが含まれたため、`UNKNOWN_OR_UNSUPPORTED_ROBOTS_DIRECTIVE`となった。
これは受信原本の改変・通信障害・identity矛盾ではなく、現在の解析実装の保守的な未対応である。
実行中に緩和したり、単純な文字列prefixで許可と推測したりしなかった。
原本と固定parserのSHAが一致したまま、別のオフライン審査票でSTOPを確定した。

A2未実施のためaboutj robots・運営主体・規約適用範囲はUNKNOWN。
A3/A4未実施のため、現在の規約主体、適用host、自動取得、保存・引用・再利用に関する条件もUNKNOWN。
以前の保存hrefや静的候補URLは、本文確認の代用ではない。
robotsのpath判定と、規約・著作権上の許可は別の審査である。

wwwのB入口は**追加条件確認が必要**、aboutjのB入口は**UNKNOWN**。
どちらもB枠permit発行・有効化・GETは0。次の取得承認へ直ちに進めるとの判定はしていない。
まず新しい不変versionでワイルドカード/UA適用のオフライン検証を行い、必要な条件確認を別の限定計画・明示承認へ切り出す。
今回のrun・permit・残予算では取得を継続できない。

## 通信・保存・所有権

独立した[access_worker.py](access_worker.py)と[access_parent.py](access_parent.py)を新規作成した。
旧executor/launcherは実行せず、旧Windows研究用storage/JobプリミティブのみをSHA固定して再利用した。
通信前の[Phase F設計](../phase2_5F/A_ACCESS_PLAN.json)に対応する専用rootをexclusive-createし、
owner SID/DACL/reparse/祖先identity/既存領域との非重複を確認した。
保存先の実パス、SID、kernel process情報は非公開証拠へ保存し、公開物は参照SHAのみとした。

`http.client`で明示hostへの直接単一接続を行い、`auto_open=0`とした。
環境proxy/TLS上書き変数は通信前検査で0件。OSネットワーク設定を変更していない。
最初の名前解決結果の1 addressだけを使用し、複数addressへのfallback、retry、redirect追従をしない。
Socket 10秒、親worker 12秒、cleanup 2秒、run 120秒、外側150秒の有限deadlineを設定した。
本文・status/headerに受信上限を設けた。取得上限到達時に未完了なら完全取得と記録しない。

一回限りpermitとコード・入力SHAを事前に固定した。
run消費markerとURLごとのintentをDNS/接続前に永続化し、同じpermit・slotの再実行を拒否する。
permitはこのA枠のみで、既存常設permitや本番設定を変更していない。
UTC、raw/metadata/request、permit/task、worker PID/kernel親identityを結合し、readback/SHA照合した。

今回のworkerはsuspended作成後、親所有のkill-on-close Windows Jobへ所属を確認してから起動した。
worker終了コード0、最終Job active process数0。
OSのJob accountingには終了直後の遅延があり、wait直後active1を観測したが、有限settle確認後は0だった。
これを残存processの放置と混同しない。outer wrapper・実親・workerのPIDを後から読取り専用で照合し、全て不存在だった。
審査STOPによる親の正式終了コードは2、外側timeoutはfalse。run全体は52.125秒で終了した。

内容審査票は原本SHA・親receipt SHAへ完全結合した。親はそれを読んで`REVIEW_STOP`として終了した。
A2〜A4のslotやconnection markerは存在せず、response台帳はintent台帳のA1 prefixと一致した。
このSTOPを通信成功4件や条件確認完了へ書き換えない。

## 検証・保護

通信前に実施したテスト：新規69＋関連回帰488＝**557 PASS**、FAIL/error/skip 0、warnings-as-errors。
新規テストは合成応答、純粋なschema/SHA照合、専用一時領域のWindows実I/Oのみを使用した。
URL完全一致、B/旧permit/重複/期限の拒否、redirect/HTTPエラー、上限、partial body、TLS必須、
未知robots/HTML、raw/metadata/requestの改変、保存のexclusive-create/flush/readbackを検証した。
合成通信は実HTTP通信の実証件数に加えない。

通信後の独立オフライン証拠監査は42項目PASS。実行後の解析・監査scriptは取得時固定コードと別に記録した。
監査script初版はrobots HOLD結果にもB_authorizedフィールドがあると仮定して停止した。
別v2でpermitのB_GET=0と審査票のB_authorized=falseを照合した。取得コード・原本・receiptを変更していない。
今回の557件は通信前実行の実績であり、通信後に再実行したとの記録はしない。

開始baselineは**53,042ファイル**。通信直前・直後ともhash/identity/metadata差分0。
モデル53 payload、既存予測、288原本、旧witness/ID30700方針/隔離9件、
運用タスク定義と状態、main、他worktreeに差分なし。運用タスクを実行・修復していない。
新原本は既存公式source/publicationとは独立の領域へ保存し、証拠SHA台帳で後続改変も検査する。

独立監査・テスト・静的検証・保護のSHAは[VALIDATION.json](VALIDATION.json)、
[IMPLEMENTATION_SHA256.json](IMPLEMENTATION_SHA256.json)、[PROTECTION.json](PROTECTION.json)、
通信集計は[ACCESS_FETCH_LEDGER.json](ACCESS_FETCH_LEDGER.json)に記録する。
ファイル集合のSHAは[SHA256-MANIFEST.json](SHA256-MANIFEST.json)。
公開するのは仕様・コード・合成テスト・集計・SHAのみで、原本bytes、個別metadata/request、
全生header、個人パス、認証情報、モデルはGitへ追加しない。

## 維持するゲート・未実証事項

このrunが実証したのはA1の単一実GET・TLS・封印・所有終了と、保守的審査でのSTOPである。
A2〜A4、複数実GET間隔、サイト規約の内容、ワイルドカードの正しい適用判定、
ネットワーク障害・timeout時の全実故障、普遍的なACL/TOCTOU/電源断耐性は未実証。
外側venv起動wrapperと実親の異常終了時の子孫cleanupは今回の正常終了照合だけで一般化しない。
以降の取得は今回のrunを再利用せず、新しい承認と接続前ゲートを要する。

詳細Aの288 PASS、B/C/D各288 HOLDは不変。
HISTORY/PREDICTION：HOLD、Phase A：BLOCKED、Phase B：NOT_AUTHORIZED。
モデルload/fit/推論、性能評価、確率計算、T0/対象登録、履歴admission、将来予測保存、
本番collector/task/feed/GUI/設定変更、取得runの再実行はいずれも0。
通常Git commit/pushのみ別途許可されたGit通信として扱い、証拠GET予算へ紛れ込ませない。
