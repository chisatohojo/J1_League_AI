# Design Decisions

## 2026-09-11: Phase 0から小さい単位で実装する

Decision: 既存の仕様書・手順書を保存し、README.mdを現在の正式仕様、
DEVELOPMENT_GUIDE.mdを手順書のコピーとして作成する。今回は開発環境の初期構成までとする。

Reason: 作業開始時点には2つの原本文書しか存在せず、手順書の第9節・第45節が
小さい実装単位と初回の環境構築を指定しているため。
README掲載の将来構成を実装済みと扱わず、機能ファイルは該当フェーズで追加する。

Status: 採用

## 2026-09-11: Python 3.12と仮想環境を明示する

Decision: Python 3.12.14で `.venv` を作成し、実行時は仮想環境のPythonを直接指定する。
今回の端末は `.tools/bootstrap` にuv 0.12.13を導入し、uvの
`--install-dir .tools/python --no-bin --no-registry` でPythonをプロジェクト内に配置した。
初期依存は仕様の7ライブラリとpytestとし、直接依存と推移的依存をバージョン固定する。

Reason: 端末の既定Pythonは3.10.6。`py -0p` には3.12の登録があるものの実行ファイルがなく、
`py -3.12 -m venv .venv` が失敗したため、仕様で推奨される3.12をローカルに導入した。
既定環境やPowerShellのスクリプト実行ポリシーを変更せず、環境を再現できるようにするため。
uvとPython本体はGit対象外の `.tools/` に置き、アプリケーション依存と分けて管理する。
将来予定のSHAP・requests・Beautiful Soup・Streamlitは直接依存として追加しない
（Jupyter等が必要とする推移的依存はロックファイルに記録する）。

Status: 採用

## 2026-09-11: 取得データと名称マスターを区別する

Decision: `data/raw/` は取得原本、`data/processed/` は加工結果、
`data/master/teams.csv` は将来の名称統一マスターとして扱う。
生データ・加工データ・モデルは初期状態でGit対象外とし、空の実データファイルは作らない。

Reason: 仕様の `data/raw/teams.csv` と手順書の `data/master/teams.csv` は用途が異なる。
取得原本を不変に保ち、名称変換を再現可能にするため。データ取得元や容量が未定のため、
取得データを管理対象に追加する場合は改めて対象と理由を記録する。

Status: 採用

## 2026-09-11: Baseline段階から時系列評価を整備する

Decision: 元の仕様のフェーズ番号を維持しつつ、評価環境（Phase 6）の基本処理は
Baseline（Phase 4）とともに整備し、LightGBM（Phase 5）はその後に比較する。

Reason: 仕様のフェーズ一覧と手順書第34節の実施順序が異なる。
Baselineを残して同一条件で性能を比較する運用を満たすには、評価の準備が先に必要なため。
学習期間・ハイパーパラメータ・特徴量の採用判断は、今回確定も変更もしない。

Status: 採用
