# Windows J1 AI Predict launcher

## Scope

Windows専用、Python標準ライブラリのみのランチャーです。既存の `web/` と
read-only serverを変更せず、Edge（優先）またはChromeの `--app` モードで
アドレスバー・タブバーのない独立ウィンドウを開きます。通常のタブへのfallback、
ブラウザーのインストール、外部依存、Electron/Tauriはありません。

real Champion-only feedはまだ生成していません。既定の通常画面は空のoperational
viewです。保存済みJSONの自動探索・feed生成・予想生成・モデル読込・評価・取得は
行いません。ST2は既存UIのSEALED表示のままです。

## 初回セットアップ・ショートカット

既存のWindows仮想環境に `.venv\Scripts\python.exe` と `pythonw.exe` が必要です。
venvがない場合のセットアップは [README](../README.md) を参照してください。
EdgeまたはChromeを通常のWindowsインストール先に別途用意してください。

ユーザー自身が、repository rootで一度だけ次を実行します。

```powershell
.\scripts\install_dashboard_shortcut.ps1
```

端末のexecution policyで拒否された場合は、スクリプトをレビューして組織の方針に
従って実行してください。installerはpolicy変更や管理者昇格を行いません。

installerはWindowsの `SpecialFolder.DesktopDirectory` を使い、OneDrive等への
リダイレクトに対応します。作成名は `J1 AI Predict.lnk`。targetはvenvのpythonw、
引数は絶対パスのlauncher script、working directoryはrepository rootです。
ショートカットからの起動にコンソールは表示されません。

同じrepository用の所有marker・target・working directory・launcher引数が一致する
ショートカットだけを更新します。同名の無関係なものはSTOPし、上書きしません。
repositoryを移動した場合も古いショートカットは自動上書きしません。
installerを実行するまでDesktopには何も作成しません。import・help・testsでは
installerを実行しません。installer自体もserver/browserを起動しません。

今回は表示可能なWindows標準アイコン `System32\shell32.dll,0` を使用します。
オリジナルのJ1/AI `.ico` 作成は残課題です。素材のダウンロードはありません。

## ダブルクリックと起動確認

Desktopの「J1 AI Predict」をダブルクリックしてください。Edge/Chromeの
独立ウィンドウが開き、タスクバーから切り替えられます。

1. `__file__` からrepository rootを解決し、named mutexを取得。
2. venvとbrowserを確認。専用profileはLOCALAPPDATAのみに作成。
3. 自身のhidden子プロセスとして `python.exe -u -m scripts.serve_dashboard --port 0`
   を起動（引数配列、`shell=False`、repository rootをcwdに指定）。
4. stdoutの `J1AI dashboard: http://127.0.0.1:<port>/` からOS割当ポートを取得。
5. `/api/dashboard` をloopback GETで確認。HTTP 200、JSON、schemaVersion 1の基本構造、
   operational、Champion A / `operational_champion_20260922_v1` を要求。
6. `--app=<actual URL>` と専用 `--user-data-dir` を引数配列でbrowserへ渡す。

リダイレクトとHTTP proxyは無効。127.0.0.1以外・demo URL・追加path/query/fragmentは
拒否します。応答サイズは1 MiB上限。readiness全体のtimeoutは既定20秒で、遅い
応答でもsupervisorは無限待ちしません。失敗時は自身のserverだけを片付けて通知します。
既存serverがJSONを完全にschema validationしてから起動する設計を再利用します。
readiness検査は基本構造だけで、probability・結果の解釈や指標計算はしません。

## 二重起動と終了（重要）

Windowsのsession-local named mutexと停止eventを使います。repositoryの正規化パスの
hashで区別し、processが生存する間handleを保持します。重複クリックでは既存instanceを
維持し、新しいserver/windowを作りません。前面化や他のwindow操作は行いません。
PIDファイルは使わず、process終了でkernel objectsが解放されるのでstale PIDによる
永久起動不能はありません。

アプリの×ボタンはbrowser windowだけを閉じます。Chromiumの起動PIDが終了しても
windowは存続し得るため、**browser終了を推測してserverを止めません**。
ランチャーとserverは明示停止まで残ります。閉じた後に再び開く場合も、先に停止して
からDesktopアイコンを押してください。この安全側の制約は第一段階の既知仕様です。

serverを終了するには、repository rootで以下を実行してください。

```powershell
.\.venv\Scripts\pythonw.exe -m scripts.launch_dashboard --stop
```

停止要求の通知後、数秒待ってください。eventを受けた元のlauncherが自身のPopen
process handleで自身のserverだけを終了し、最大5秒待ってmutexを解放します。
ブラウザーは閉じません。先にwindowを手動で閉じることを推奨します。
launcher起動PIDやbrowser全体をtaskkillする方法ではありません。

停止が解決しない場合は、同じrepositoryの `--stop` を再確認してください。
Task Managerで元のlauncherがまだ生きている場合だけ、その子serverの実行ファイル
パス（このvenv）、command line（上記起動引数）、parent・起動時刻を確認できます。
手動終了はその所有関係が確実なserverだけに限定し、不明なら終了せず調査してください。
launcherのhard crash後はserver/browserが残る可能性があります。既存serverを探して
自動killする復旧は行いません。`taskkill /IM ... /F`、未検証PIDのkillは禁止です。

browser profileは以下にbrowser別で分離します。

```text
%LOCALAPPDATA%\J1AI\Dashboard\<repository-path-hash>\edge-profile
%LOCALAPPDATA%\J1AI\Dashboard\<repository-path-hash>\chrome-profile
```

個人profileは使わず、既存browserの設定を変更・削除しません。専用profileもlauncherは
削除しません。browser起動processは所有記録として生成しますが、window寿命の証拠には
使わず、終了命令も送りません。

## Champion-only JSONとの関係

将来別taskで生成・承認されたJSONを明示指定することは可能です。

```powershell
.\.venv\Scripts\python.exe -m scripts.launch_dashboard --data C:\approved\champion_home.json
.\scripts\install_dashboard_shortcut.ps1 -Data C:\approved\champion_home.json
```

launcherは絶対パスをserverの `--data` に渡すだけで、JSONを読みません。既存serverの
完全なChampion-only schema validationで拒否されたら起動失敗です。
省略時は空画面で、demoへの自動fallbackもありません。JSON更新の反映には停止・再起動が
必要です。`scripts.build_dashboard_feed` はこのlauncherから呼び出しません。

## ログ・トラブルシューティング

ログは `%LOCALAPPDATA%\J1AI\Dashboard\<repository-path-hash>\launcher.log`。
UTC時刻と固定event codeだけを記録し、server stdout/stderr・HTTP body・exception文字列・
traceback・研究probability・Elo・class・ST2データは含めません。エラーはWindows message
boxでも通知します。log書込不能でも通知を試みます。

- `venv_missing`: READMEのvenv構築手順とpython/pythonwの存在を確認。
- `browser_missing`: 通常のProgram Files(x86)/Program Files/LOCALAPPDATAにEdge/Chromeが必要。
- `startup_timeout` / `server_exited`: venv、server import、明示JSON、local権限を確認。
- `invalid_response` / `invalid_url`: 想定外の応答を拒否。タブやdemoで迂回しません。
- `already_running`: 既存instanceを維持。閉じたwindowを再起動するには先に `--stop`。
- `ipc_failed`: Windows/sessionのkernel object権限を確認。
- `cleanup_failed`: 上記の所有関係を確認した安全な終了方法に従う。

CLI診断はconsole版Pythonで実行できます。`--startup-timeout` は有限の(0,120]秒のみ。
デフォルトの起動方式を確認するだけなら `--help` を使用してください。

## 検証・今後

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_dashboard_launcher.py -q
.\.venv\Scripts\python.exe -m pytest tests/test_dashboard_server.py -q
.\.venv\Scripts\python.exe -m scripts.launch_dashboard --help
```

unit/integration testsはsynthetic/mocked IOのみ。実Windowsのkernel object testは
一時repositoryの名前のみを使い、Desktop/profile/server/browserを作成しません。
別のWindows smoke testではserverの実装コードだけを一時repositoryにコピーし、
空serverのhidden起動・動的port・loopback応答・所有process停止を確認します。
GUI app-modeはmockし、実ウィンドウの確認はユーザーレビュー時の
手動項目です。本番feed・モデル・予想artifact・ongoing sourceは読みません。

将来のEXE化ではこの独立moduleと同じ起動関数を利用し、repository/venv/serverの配置を
明示設計します。現在はPyInstallerを導入しておらず、EXEを生成していません。
より自動的なwindow/server連動終了やcustom iconは別の起動体験改善taskで扱います。
