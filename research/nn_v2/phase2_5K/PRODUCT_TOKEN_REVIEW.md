# NN v2 Phase 2.5K — product-token / User-Agent group review

判定：`NN_V2_PRODUCT_TOKEN_REVIEW_PARTIAL`

基準は Phase J commit `33835802f8cddc006edc7db01d67649e79b6a756`。
独立branch `feature/nn-v2-product-token-review` で、保存済み原本の読み取りと純粋関数の検証だけを実施した。
実送信User-Agentの直接記録と、採用済みproduct-tokenが不足するため、実際の取得器について確定判定したとは扱わない。

## 棚卸しと証拠の強さ

`USER_AGENT_INVENTORY.json` は18箇所の設定と、インストール済み4 HTTP clientのデフォルトを記録する。
値・相対コード位置・SHAを対応付けた。取得器をimport・起動して通信する調査は行っていない。

| 経路 | コード設定 | 実送信値の証明 |
|---|---|---|
| 公式試合一覧／通常updater | `J1-Match-Predictor-Research/0.1` | request metadataにheaderなし。UNKNOWN |
| Gアクセス条件、I仕様取得、研究B14〜18のworker | `J1AI-Research-Timing-Pilot/1.0` | G/Iの固定コードSHAとrequest・receiptを照合。送信headerの直接記録はなくUNKNOWN |
| ニュース／プレス候補 | E設計の同じ固定UA | 設計上の入力検査のみ。B実行経路・送信証拠なし |
| その他のcollector | xG、出場停止、チームprofile、Cup等の個別設定 | 本工程ではコード値。過去の実送信と同一とは断定しない |

G/Iのrequest.jsonにはURL・UTC・permit/task SHA・PID等があるが、送信header欄がない。
封印workerの `headers={'User-Agent': AGENT, ...}` とpermitのcode pinは、構築予定引数を強く裏付ける。
これは送信headerの直接記録、server echo、packet captureとは別の証拠である。
A1/S1/S2のrequest・metadata・sealを再照合し、原本と旧通信台帳の不変を確認した。

調査したmodule内にUA用CLI／環境変数overrideは見つからなかった。G/Iは固定コード・task・permitで値を制限する。
ただし任意のmonkeypatchや独自openerによる変更の不可能性までは証明していない。
通常updaterの運用コピーは、対象2コードのSHAが今回の基準と一致した。

インストール済みsourceで、urllib.requestは `Python-urllib/3.12`、requestsは `python-requests/2.34.2`、
httpxは `python-httpx/0.28.1` を確認した。http.clientには自動User-Agent追加がない。
明示header・opener/client設定によるoverrideはライブラリ単位で区別する。
requests/httpxを通常公式取得経路で使用しているとは扱わない。ブラウザの実UAは調査していない。

## 保存済み仕様との照合

根拠はIで封印されたS1 RFC9309とS2 Google日本語仕様だけである。
`INPUT_EVIDENCE.json` と `GROUP_SELECTION_VALIDATION.json` に原本SHA、request/metadata SHA、節anchorのbyte範囲とSHAを記録した。
URLは出典identityであり、今回アクセスしていない。

| 区分 | 判断 |
|---|---|
| RFC9309 2.2のidentifier | ASCII英字・`_`・`-`。digit、version slash、dotを含む全文はtokenにしない |
| RFC9309 2.2.1 | crawlerがtokenを選ぶ。HTTP UAへの包含はSHOULD。HTTP UA全文と同一とは限らない |
| RFC group選択 | 明示tokenとの大文字小文字を無視した完全一致。同じtokenの複数groupを統合 |
| fallback | named groupがあれば`*`は混ぜない。一致がなければ`*`、それもなければ適用規則なし |
| Google固有挙動 | Google crawlerのmost-specific選択、`googlebot/1.2`／`googlebot*`の説明を記録。J1AIの一般則へ転用しない |
| J1AI独自制約 | 明示宣言は1候補だけ。headerへの包含を必須化。空・不正・複数候補・未確認構造はUNKNOWN |

header中のtoken包含検査と、robots group名の照合は別処理である。
group選択には部分一致・digit除去・version除去・Google suffix規則を使わない。
完全なHTTP UA構文解析器は実装していない。可視ASCII・長さ上限を設け、RFC Figure1のような付加情報付きheaderも、明示tokenがあれば候補照合できる。

## 別版parserと層の対応

新別版：`nn_v2_robots_offline_groups_v4`（`product_token_groups.py`）。
H/I/J旧実装、HTTP取得器、実UA設定、旧permitは変更していない。
Iのbounded parser／octet matcherとJの非実行permit checkerを再利用した。
64 KiB上限・reserved octet／ranking等の未解決制約を維持し、RFC／Google完全準拠は宣言しない。

`declared_identity` → `select_groups` → `path_decision` を独立出力する。
groupがSELECTEDでも、未対応のパス構文・query等でpathがUNKNOWNならrobotsもUNKNOWN。
構造を壊す未知agent／不正directiveはgroup自体をUNKNOWNとする。
未知のその他fieldは定義済みgroupを変更しないが、独立した証拠層で通信を許可しない。
厳密な `/robots.txt` の暗黙ALLOWは従来Jと同じくtoken宣言とは独立で、原本／origin／spec検査を迂回しない。

| Jの実JSON項目 | Kの項目 | 意味 |
|---|---|---|
| `layer1` | `layer1` | group／path／robots仕様判定 |
| `j1ai_evidence_policy` | `layer2` | 原本・origin・spec・実UA証拠・採用状態・未解決仕様 |
| `layer2`（permit） | `layer3.permit` | 今回はUNAPPROVED |
| `layer3`（communication） | `layer3.communication` | 実行権限なし |

旧JSONの名称を遡及変更せず、この対応を新schemaで明記した。
仕様上ALLOWでも、証拠不足をLayer1へ押し戻して隠さず、Layer2のUNKNOWNとして記録する。
全結果でexecution／B許可／history admissionはfalse。実行可能permitを作るAPIはない。

## A1の条件付き再評価

候補header：`J1AI-Research-Timing-Pilot/1.0`（既存コード設定と同じ）。
提案token：`Research-Timing-Pilot`。ASCII文法とheader内包含を満たす明示候補であり、自動抽出や採用済み設定ではない。
`Timing-Pilot`等も考えられるが、複数候補を渡すとUNKNOWNとし、都合のよいgroupを選ばない。

| 対象 | 旧J／token未宣言 | 明示候補の仕様判定 | 適用group／一致規則 | 証拠／permit／通信 |
|---|---|---|---|---|
| `https://www.jleague.jp/robots.txt` | ALLOW | ALLOW | `*`（group1）、一致規則なし。暗黙URI例外あり | UNKNOWN／UNAPPROVED／false |
| `https://www.jleague.jp/general/kiyaku/` | UNKNOWN | ALLOW | `*`（group1）、一致規則なし | UNKNOWN／UNAPPROVED／false |
| `https://www.jleague.jp/general/copyright/` | UNKNOWN | ALLOW | `*`（group1）、一致規則なし | UNKNOWN／UNAPPROVED／false |
| `https://www.jleague.jp/j1/news/` | UNKNOWN | ALLOW | `*`（group1）、一致規則なし | UNKNOWN／UNAPPROVED／false |

これは固定した候補への純粋計算である。現在／過去の実送信headerに対する確定ALLOWではない。
同じ明示tokenをJへ渡しても、このA1の4パスはALLOWとなる。旧正式結果との差は宣言条件の違いであり、パス規則を緩めた効果ではない。
A1の別のnamed group `spider` はこの候補には適用しない。明示tokenが `spider` の合成例では、named groupによるDENYを確認した。
原本全文・個別通信証拠はローカルに保持し、公開JSONはgroup ID・agent名・rule件数と判定を記録する。
aboutjはhost固有robots原本がないためUNKNOWN。利用規約・copyright・B入口の取得やアクセス条件確定も行っていない。

## 残る9項目への影響

正式IDはJ台帳から取り込んだ。
`agent_grammar` は明示候補の文法・group照合を実証したが、実送信証拠と採用判断が不足する。
`sealed_A1_replay` は候補に限り4 ALLOWとなるが、実senderについては未解決。
両軸の正式UNKNOWNを根拠なくPASSへ移していない。

`rule_grammar`、`longest_rule`、`reserved_octets`、`query`、`encoding_errors`、
`parse_limits`、`standard_examples` はJの未解決事項を維持する。
9項目は0 PASS／0 FAIL／9 UNKNOWN、全24項目は15 PASS／0 FAIL／9 UNKNOWNのまま。

## 検証と保護

今回の最終実行：**693 PASS／0 FAIL／0 skip**、warnings-as-errors。
新規K121件、Jまでの回帰再実行572件。新規の明示negative-controlは71件。
group統合・case・境界・wildcard・不正token・override・誤部分一致・層分離・SHA／origin／scope拒否を検証した。
実原本監査はJUnitと別の独立証跡として保存した。

初回は71 PASS後、巨大bytesをpytest case IDに使ったためWindows環境変数長制限で2 ERROR。
短いcase IDへ修正後の中間実行は686 PASS。named `spider` 関連5件の追加後は691 PASS。
最終レビューで暗黙URI例外のpath結果を明示し、未知rankingを迂回しない2件を追加した最終実行が693 PASS。
失敗ログ・中間JUnitを保持し、最終結果へ合算しない。J既存572 PASS／static54も過去証跡と今回の回帰を区別する。

テストprocess内のapplication audit hookでnetwork／DNS／子process／model deserialization／実ML呼出しと許可領域外writeを拒否した。
最終実行の禁止操作試行は0。OSレベルnetwork隔離を実証したとは扱わない。
実通信worker・collectorを実行するテストはない。

新baseline **58,011ファイル**に対しSHA・identity・metadata差分0。
封印モデル53 payload、旧原本・receipt・隔離・witness・ID30700方針、予測、main／他worktree、タスク定義・状態を維持した。
前工程後に既に存在した6差分は、本工程開始前の07:00運用mutable出力である。
独立したtask失敗・diagnostic・revision manifest・snapshot／raw／metadata SHAと対応を照合した。
履歴完全性ゲート失敗を正常な予測保存成功とは認定せず、研究の実行にも帰属させない。
修復・再実行は行っていない。詳細は `PREEXISTING_OPERATIONAL_EVENT.json` とprivate証跡に分離した。

## 次のゲート

1. 正式に採用するproduct-tokenと、送信headerとのbindingを別判断で固定する。今回の候補を自動採用しない。
2. 将来の取得を承認する場合、送信直前の実headerとcode／request／permit／receiptを結合して封印する設計を審査する。後から過去の送信証拠は作れない。
3. 残るpath／encoding／limit／standard-example等のUNKNOWNを別工程で審査する。
4. aboutj／規約等の実取得が必要なら、新しい限定URL集合と通信予算を明示承認する。旧permitを再利用しない。

新規GET／HEAD／DNS probe／資料取得／permit発行／UA設定変更／collector実行／実モデルload・fit・推論・評価／T0／履歴・予測登録は0。
通常Git pushは依頼された成果物保存であり、証拠URL取得や通信permitとは別である。
B/C/D各288 HOLD、HISTORY／PREDICTION HOLD、Phase A BLOCKED、Phase B NOT_AUTHORIZEDを維持する。
