# 後日再現予測の独立プレビュー

通常のschema v2の `prediction.source = saved_pre_match` 契約は変更しません。
試合前保存予測を優先し、未保存かつ公式completedの試合にだけ、別型の
`retrospective_reconstruction` overlayを表示します。ライブと再現の成績は合算しません。

## 入力と検証

`scripts/build_retrospective_preview.py` は明示した運用runtimeと再現Rootを読み取り専用で扱います。
外部から指定した既存SHA台帳のSHAを起点に、全ファイル、run_id、公式revision、対象集合、
全日付の予測seal、結果JSON・summary・モデルhashを検証します。推論やモデル読み込みは行いません。
最新公式publicationとのfixture_key、日付・開始時刻、方向付きTeamMaster ID、節、公式ID namespace、
得点・勝敗が不一致なら、その試合の再現表示を保留し、固定診断コードをoverlayへ残します。

通常の保存済み予測・bindings・source/witnessは既存adapterで検証します。
運用中の `view/champion_rounds.json` は読み書きせず、別Rootに表示専用JSONを生成します。
出力先は新規・非reparse・入力およびRepositoryとは分離した場所を指定します。

```powershell
& $python -B -m scripts.build_retrospective_preview --source-root $source --runtime $runtime --retrospective $reconstruction --retrospective-ledger-sha $trustedLedgerSHA --output $preview
```

## 表示

```powershell
& $python -B -m scripts.serve_dashboard --port 0 --data "$preview/champion_rounds.json" --reload --status "$preview/update-status.json" --poll-seconds 60 --retrospective "$preview/retrospective-overlay.json" --retrospective-sha $overlaySHA
```

表示されたloopback URLへ `?retrospective=1` を付けて開きます。
通常URL、v1、デモはoverlayへアクセスせず、既存契約で動作します。
明示したoverlayが不正・欠損の場合は成功扱いやデモへの切り替えをせずエラーを表示します。
サーバーはoverlayのSHAとbase JSONとの一致を毎回検証します。
再読込中の不整合は直前の正常表示を保持します。

初期表示は通常の前節・今節／次節です。「過去の節を見る」を開くと、
再現対象を含む全公式節を選択できます。公式1節10試合の所属・日時順を維持します。
保存済み予測の文言・確率・生成日時は維持し、再現カードには
「後日再現予測」、実際の再計算日時、「当時の試合前保存予測ではありません」を表示します。
当時の公式掲載状況は未立証で、厳密な当時as-of予測とは主張しません。

従来の `--retrospective` プレビューは固定入力の確認用スナップショットです。60秒再読込は表示ファイルだけを
再検証します。公式取得・ライブ予測・既存runtimeの変更は行いません。
後日の公式revisionや予測batchを反映するには、新しい隔離出力を明示的に生成します。

## 更新追従の世代ストア

新しい `--refresh-store` 方式では、公式latestと全保存batchを再検証し、通常v2とoverlayを
同じ不変の世代へ保存します。初回だけ新しい独立した出力先を指定します。
再現98試合の成果物は読み取り専用です。新しい保存予測は優先され、再現対象にない試合には
確率を生成しません。新しい保存予測を含む節も履歴へ追加します。

```powershell
& $python -B -m scripts.build_retrospective_preview --source-root $source --runtime $runtime --retrospective $reconstruction --retrospective-ledger-sha $trustedLedgerSHA --output $store --refresh-store
# 初回の出力に表示された store_sha256 を固定して次回以降に指定
& $python -B -m scripts.build_retrospective_preview --source-root $source --runtime $runtime --retrospective $reconstruction --retrospective-ledger-sha $trustedLedgerSHA --output $store --refresh-store --store-sha $storeSHA
```

`store.json` は再現run_id・固定モデル・元台帳のSHAを束縛する不変契約です。
世代内のJSON両方を検証・flush・readbackし、SHA manifestから求めた世代IDのディレクトリへ
公開した後、`current.json` を原子的に切り替えます。同じ組み合わせの再生成は既存世代を返します。
明示的な再実行は、失敗時に残った世代が全bytes一致する場合だけ再利用します。
未検証の世代や改変ファイルを自動修復しません。排他lockが残ったhard crashは要調査です。

サーバーは `store.json` の外部SHA、世代manifest、両JSONのSHAと相互参照を再検証します。
更新中・失敗・世代の巻き戻りは直前の正常な組み合わせを保持します。
ブラウザーは `/api/presentation` の1応答でv2・overlay・世代IDを取得するため、別々のGETによる
世代混在を防げます。従来のv1/v2・固定プレビューは互換のままです。

```powershell
& $python -B -m scripts.serve_dashboard --port 0 --generation-store $store --store-sha $storeSHA
```

表示されたURLに `?retrospective=1` を付けて開きます。60秒周期で新しい検証済み世代へ追従します。
初回起動には正常な世代が必要です。起動中のキャッシュは不正な新世代で置き換えません。
PC再起動後は、保存済みの不変世代を検証して表示します。元の再現計算は再実行しません。

## 自動更新処理との任意接続

外部configに次の任意設定がある場合だけ、本体の更新成功・排他解除の後に表示を再生成します。
設定がない場合は現行の動作を維持します。今回は実configへ追加しません。

```json
"retrospective_display": {
  "store_root": "<運用runtimeとは別の表示ストア絶対パス>",
  "store_sha256": "<初回store.jsonのSHA-256>",
  "reconstruction_root": "<固定された再現成果物Root>",
  "ledger_sha256": "<固定された元SHA台帳のSHA-256>"
}
```

表示生成に失敗しても本体の結果・予測・v1/v2保存を失敗へ変更しません。
CLI結果の `retrospectiveState` と表示ストアの `status.json` で表示側の失敗を確認します。
本体の処理中は前回の表示世代を保持します。通常の `view/update-status.json` は本体専用で維持します。

## 専用アプリの起動経路

```powershell
& $pythonw -B $launcher --runtime $store --view retrospective --store-sha $storeSHA --python $python
& $python -B $launcher --stop --runtime $store --view retrospective
```

`$launcher`、`$pythonw`、`$python`、`$store` はすべて絶対パスです。
既存v1/v2とは異なるmutex・イベント・専用プロファイルを使います。
×でウィンドウを閉じても所有サーバーは維持し、再起動は同じURL・プロファイルへ再表示します。
停止は所有するPopenハンドルだけを対象とし、ブラウザーや他サーバーを停止しません。
PC再起動後も同じ明示パスで起動可能です。自動ログオン起動やタスク登録は追加しません。
可視GUI操作が実行環境の承認レビューで拒否されている場合は、迂回せずその確認だけを保留します。

## 検証

```powershell
& $python -B -m pytest tests/test_retrospective_generations.py tests/test_retrospective_overlay.py tests/test_dashboard_launcher.py tests/test_dashboard_server.py tests/test_dashboard_feed.py tests/test_champion_dashboard_update.py -q -p no:cacheprovider
cd web
npm test
npm run test:browser
```

合成入力で優先順位、誤った公式ID・日付・方向・節・訂正結果、重複、改変、未確定、
再読込時の種別保持、通常画面・v1・デモとの互換性を検証します。

## 運用導入の境界

確認用branchから運用worktreeへの反映には、初回自動更新の保存データ監査と明示的な導入承認が必要です。
反映前に両HEAD・clean状態・更新lock・定期実行までの余裕を確認し、コード・config・表示世代・
ショートカット・タスク定義を別ディレクトリへバックアップします。コードはfast-forwardのみで反映します。
まず終了証拠・履歴完全性・朝の10試合バッチ・確率保存とv1/v2更新を確認します。
次に承認対象commitを運用worktreeへ反映し、最新保存入力から新しい表示ストアを初期生成します。
実configをバックアップして任意設定を追加し、本体更新と表示更新の分離を確認します。
通常ブラウザーの運用入口は `--view retrospective --browser-mode default` を明示し、
承認済みの運用worktree・独立ストア・store SHA・Pythonを絶対パスで指定します。
所有関係を確認した対象アイコンだけを変更し、既存のアプリモードや運用v2アイコンは維持します。
Windowsタスクの登録変更は不要です。可視操作が拒否された場合は迂回せず未確認と記録します。
実データのブラウザー検証は、固定の4/16件を前提にせず、検証済みペアの各fixture・予測種別・
確率・保存日時・結果と照合します。履歴も確定fixture集合の完全一致を確認します。
切り戻しは任意設定を外して元のショートカットを復元します。既存予測・再現成果物は削除しません。
Phase A: BLOCKED / Phase B: NOT_AUTHORIZEDを維持します。
