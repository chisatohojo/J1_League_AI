# NN v2 研究成果物の復元（再学習禁止）

別ドライブZIPのSHAは `backup-verification.json` を参照する。既存フォルダへ展開せず、新しい専用ディレクトリへ復元する。ZIP内は `run/` が封印済みモデル出力、`control/` が実行管理・source snapshot、`BACKUP-MANIFEST.json` が全保存ファイルのSHAとサイズである。

1. ZIP SHAとCRCを確認し、絶対パス・`..`・展開先外へのentryがないことを検証する。
2. 新規フォルダへ展開し、BACKUP-MANIFESTの全サイズ・SHAを照合する。
3. `run/artifact-seal.json` のSHA `d620f8a9cb44a3940996f89ded80c5396b0925e862501261870b6598458d392f` と、その全payload SHAを照合する。学習前Manifest SHAとexecution seal SHAも確認する。
4. 対応する研究commitのdriverと、固定されたPython 3.12.14、NumPy 2.5.3、pandas 3.0.5、scikit-learn 1.9.1、joblib環境を用意する。入力・数値コードのSHAはcontrol側のexecution seal／source snapshotを参照する。信頼する自作joblib以外はロードしない。
5. 読戻し専用モードを使う。これはfitや予測保存を行わない。合成5入力と保存offsetだけで数値再現を確認する。

```powershell
& $Python -X utf8 -B -W error -m src.modeling.nn_v2_training verify --artifact-root $RestoredRun --seal-sha d620f8a9cb44a3940996f89ded80c5396b0925e862501261870b6598458d392f
```

`SUCCEEDED.json` と外側実exit0が整合することを確認する。`STARTED` だけのmarkerは成功と見なさない。元の永続attempt markerは削除しない。復元後も同じStudy IDでtrainを再実行しない。

このバックアップにはモデル・Scaler・全実offset・監査・時刻付き訓練入力と元データSHAを含む。公式raw HTML各3,588件や元CSV12件の本体は同梱しないため、元入力からの完全な再監査には、別途同じSHAの元保存データが必要。再学習を復元確認の代用にしない。

旧PCの絶対パスはcontrolの原本receiptに保持されている。別PCではverifyの復元パスとPythonだけを明示指定し、古い運用runtime／configを開かない。Windowsタスク登録、公式取得、Champion A接続、実T0、将来対象登録や予測保存は復元操作に含まれない。
