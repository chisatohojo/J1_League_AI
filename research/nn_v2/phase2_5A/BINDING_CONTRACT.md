# 研究専用completion binding契約

`src.modeling.nn_v2_completion_binding` はbyte入力だけを検証する独立モジュール。ファイル書込み、通信、モデルロード・fit・確率計算機能を持たない。Champion Aや研究の将来予測入口からは呼び出さない。

## 入力と採用

1. 外側で固定したmanifest SHA、revision packet、snapshot A/B packetを渡す。packetはディレクトリidentity・manifest原文・全参照ファイル原文を分離する。
2. revision 11以降の連続した受理済み履歴、run identity、全ファイルSHA、completed CSVとobservations、typed IDの単一所有を検証する。
3. A/B両snapshotのidentity、fingerprint、raw／metadata全SHA、URL・HTTP成功・byte数・取得時刻・時刻順序を検証する。manifestへの追記・差し替えは外側SHAで拒否する。
4. 固定allowlist 101101〜101104と指定4fixtureのみ採用可能。canonical、日付、節、ホーム／アウェイ、明示終了、結果は既存strict parserで検証する。A/Bの解析結果と各revisionのidentity・スコアは同一でなければならない。
5. 初回completedのAへの参照、typed bridgeのAへの参照、以後のSHA・取得時刻の維持、誤ったBのcompletion originをそれぞれ保持する。snapshotの別名を同一扱いするfallbackはない。
6. 4件の完全集合だけを一つの研究bindingとして採用する。部分成功、同一fixtureの競合binding、未登録fixtureへの拡張は禁止。
7. `validate_sealed_binding()` は独立に固定したbinding SHAと、原本からの再生成結果の完全一致を要求する。manifestに書かれた自己申告PASSだけでは受理しない。

## 保存・読み戻し

`scripts.audit_nn_v2_completion_binding` は読取り専用のruntimeと外側保護台帳を参照し、検証に合格してから未作成の監査ディレクトリをcreate-newする。元runtime/source配下への出力と既存出力の再利用を拒否する。binding・seal・原因再現・入力SHAを `xb` 保存し、flush/fsync/readbackとbinding再生成を実施する。

今回の新規成果物は `binding-manifest.json` と独立 `binding-seal.json`。元completion ledger、origin、raw、metadata、publication、予測batch、Phase 2.4監査を書き換えない。bindingが将来訂正を要する場合、今回の成果物を上書きせず別の研究監査で新規記録を作る。

## 再検証手順

1. このphaseの `SHA256-MANIFEST.json` と `implementation-sha256.json` を確認する。
2. `local-evidence-index.json` の監査Root・source pin台帳・receipt・JUnitのSHAを照合する。
3. `binding-manifest.json` のpinsで原publicationとsnapshotの同一性を確認し、各参照ファイルのbyteをpacketとして読む。
4. 封印済みbindingのSHAを別引数に渡して `validate_sealed_binding()` を呼ぶ。読取り専用であり、新規報告ディレクトリも必須ではない。
5. 入力が変化・欠落している場合はHOLD。原本の修復や別snapshotへの暗黙fallback、実予測実行は行わない。

10月11日時点のPIT掲載証明は付与しない。モデル封印状態、Phase 2.4のHOLD、Phase A BLOCKED／Phase B NOT_AUTHORIZEDは維持する。
