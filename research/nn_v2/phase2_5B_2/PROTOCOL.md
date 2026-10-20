# Phase 2.5B-2 公式時刻証拠パイロット契約

研究専用取得器はローカルの `implementation-final.py`（取得時のmodule名は `scripts.nn_timing_evidence_pilot`）。GitHubへの追加は指定どおり集計・仕様・SHA・テストだけとし、実装本体はローカルと検証済み別ドライブbackupに保存する。モデル・Scaler・Elo/Form adapter・運用collectorの実行APIをimportしない。既存strict scoreboard parser、TeamMaster、時刻備考parserを読取り専用で参照する。

公開テストは `J1AI_TIMING_PILOT_IMPLEMENTATION` に指定したローカル実装を固定SHA照合後にloadする。実装が指定されなければmodule単位でskipし、別のコードへfallbackしない。今回の検証では実装を指定し、全40件を実行した。実取得時の旧実装2版も個別preflight SHAと一致するbyteで保存した。

## 選定とpreflight

Phase 2.5BのSHA付き不足候補288件と試合別監査matrixを入力とする。保存済み公式一覧にある正確なSFMS02リンクとIDの一致を確認し、URLの生成・推測・検索を行わない。

百年構想は時系列rankを3区分し、各区分から非PK・PKを1件ずつ、区分内25%・75%位置に最も近いものを選ぶ。2026/27はkickoff差なしの時系列0/3・1/3・2/3・3/3位置から4件、差ありの最初の封印済みbinding比較1件と最も遅い非binding比較1件を選ぶ。日付とIDで安定tie-breakする。最大12件、各系列6件を取得前に固定する。

ID・URL・理由・期待identity/日時/90分結果・元証拠record SHAと各選定record SHAをローカル保存する。選定全体SHA、許可ホスト、上限、source/model/study/seal・binding・保護台帳・テスト・実装SHA、保存先とACL検査をpreflightへ記録し、そのSHAを外側の実行引数へ固定する。入力不一致なら接続前に停止する。

## 通信・保存の上限

| 項目 | 固定値・動作 |
|---|---|
| URL | 保存済みの `https://data.j-league.or.jp/SFMS02/?match_card_id=...` の完全一致のみ |
| 許可ホスト | `data.j-league.or.jp`、HTTPS/443のみ |
| TLS | `ssl.create_default_context()`、証明書・hostname検証を必須 |
| 回数 | パイロット全体12 URL以下、各URL最大1 GET |
| timeout | socket 10秒、親processからworkerの待機も10秒で打切り |
| 間隔 | 同一ホストの前通信終了から次request開始まで最低5秒 |
| 並列・再試行 | 並列ダウンロード0、自動再試行0 |
| redirect | 追従0。Locationが明示許可ホスト外なら拒否し、許可ホスト内でも事前未承認redirectとして停止 |
| 本文 | 1応答最大2 MiB、12件で最大24 MiB。超過は不完全・失敗として保存 |
| 停止 | 403/429、他の異常status、timeout、アクセス制限、redirect、未知構造・注記・identity/結果不整合 |

標準HTTP clientで1 GETだけを実行し、HTML内のscript・画像・リンクを実行・追跡しない。proxy環境変数を使うclientやbrowser fallbackを用いない。robotsは既存のSHA付き応答を検査する。本pilotでは9月11日取得404であり、現行robots確認済みとは主張せず、対象外のrobots新規取得も行わない。保存済み200ルールがあればDisallowとcrawl-delayを尊重し、不明な制限は停止する。

保存先は `%LOCALAPPDATA%/J1AI/NNResearch-phase2_5B_2-<日時>` の新規研究領域に限定する。既存source/runtimeへの出力、reparse point・symlink、既存snapshot・ファイルの再利用を拒否する。ACL・実際のcreate-new/fsync/readback権限と別ドライブの保存先を接続前に検査する。新規出力とbackupの子フォルダだけを所有者・SYSTEM・Administratorsへ限定し、既存親ACLを変更しない。

request開始前にrequest JSONをexclusive作成する。応答headerを受けた時点の記録と、完了UTC・status・最終URL・raw SHA/bytes・Content-Type・request SHAを別metadataへ記録する。timeoutで完全な応答が保存できなければ、親processの失敗receiptを残し、完全な取得と偽らない。snapshot全payloadをSHA sealし、新規snapshotファイルをread-onlyにする。再開時の同一URL再取得は認めない。

## 解析とHOLD

既存 `parse_detail` でページ自身のrepost ID、対戦クラブ、90分/PK/延長periodを検証し、固定sourceと比較する。公式記録の大会・年度・節の全文見出しと、A12の日付・開始時刻も完全一致させる。後日取得した最終公式記録と、当初日程・試合当時の公開状態は別の証拠である。

備考は既存 `timing_notes` を使い、A11 blockまたは検証済みA10〜A12間の空備考形式を記録する。未知構造、時刻注記、備考外の未知の時刻語はHOLDとする。記事文の「リーグ中断・再開」を個別中断と認定しない。アクセス制限語もscript/style/commentを除いた表示本文で判定し、計測script内の定型エラー辞書をHTTP応答と混同しない。

年度付きの2026/27見出しは、保存済み公式templateとsourceの `source_season_label` から取得前に `header_expectation` で作る。parserで任意のprefixを許容したり、原sourceを修正するfallbackは置かない。

## 今回の停止記録と限定した継続

最初のHTTP 200を埋込み計測script内の定型429文で誤検知した。初回snapshotと実際の取得実装・テストbyteを元SHAに一致させて保持し、rawをオフライン検証した。その誤検知だけを理由として、別の明示preflightで未取得11件を継続した。元12件の部分集合、先行snapshot seal、rawを用いた修正確認、先行URLとの非重複、合計上限、跨processの5秒間隔を検証した。実際の403/429・timeout・未知注記はこの継続経路を使えない。

その後の2026/27見出し不一致では通常のHOLDで停止し、継続しなかった。修正後の年度付き見出し契約は保存済みrawだけで検証した。停止済みsnapshot・報告・取得日時は上書きしない。

## 次回の計画

未取得281件は元の実リンク集合から7取得URLを除いたもの。仮の全体上限は281 GET・各URL1回、各job最大12件とするなら24 job（23×12＋5）だが、実行には別承認と全体台帳が必要。現pilotのpermitで全件を実行できない。追加の当初日程・延期告知はこの281件と別枠で、候補を記録しても取得しない。

raw・個別監査・URL一覧・個人パス入りreceiptはローカルと別ドライブへSHA付き保存する。GitHubへ保存するのは実装・合成テスト・集計・仕様・SHAのみ。HISTORY/PREDICTION HOLD、Phase A BLOCKED、Phase B NOT_AUTHORIZEDを維持する。
