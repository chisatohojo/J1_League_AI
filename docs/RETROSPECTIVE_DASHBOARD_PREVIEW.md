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

このプレビューは固定入力の確認用スナップショットです。60秒再読込は表示ファイルだけを
再検証します。公式取得・ライブ予測・既存runtimeの変更は行いません。
後日の公式revisionや予測batchを反映するには、新しい隔離出力を明示的に生成します。

## 検証

```powershell
& $python -B -m pytest tests/test_retrospective_overlay.py tests/test_dashboard_server.py tests/test_dashboard_feed.py -q -p no:cacheprovider
cd web
npm test
npm run test:browser
```

合成入力で優先順位、誤った公式ID・日付・方向・節・訂正結果、重複、改変、未確定、
再読込時の種別保持、通常画面・v1・デモとの互換性を検証します。

## 運用導入の境界

このbranchは確認専用で、既存の運用worktree・タスク・アイコンへ反映しません。
正式切り替えでは、ユーザー承認後に運用へ反映するcommit、overlay再生成と更新失敗時の
保持契約、専用起動引数・プロファイルを確定し、既存ショートカットをバックアップしてから
変更します。`--view rounds` だけを変更してもoverlayは接続されません。
Phase A: BLOCKED / Phase B: NOT_AUTHORIZEDを維持します。
