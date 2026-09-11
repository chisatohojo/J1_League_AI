# Changelog

## 2026-09-11

### Added

- Phase 1として `load_matches` / `validate_matches` と `MatchValidationError` を追加。
  必須列・欠損・日付・整数・ID/試合重複・同一チーム・得点/result整合性・CSV構造を検証する。
- 実データに依存しないCSV/DataFrameの正常系・異常系テストを追加。
- 読み込みAPI、返却型、日付形式と検証境界をREADME・設計判断に記録。
- Phase 0のPythonプロジェクト構成と開発環境設定を追加。
- 起動確認用の `python -m src.main` とpytestスモークテストを追加。
- 正式仕様README、開発手順、開発状況、設計判断、データ取得元、モデル実験の管理文書を追加。
- 生データ・加工データ・名称マスター・モデル・分析用ディレクトリとGit除外設定を追加。
- 初期依存7ライブラリとpytestの依存定義、検証済みバージョンを保存するロックファイルを追加。
- 端末のPython 3.12実体がない問題に対し、プロジェクト内にPython 3.12.14と仮想環境を構築する手順を追加。

### Changed

- 正式リモートをGitHubの `chisatohojo/J1_League_AI` として文書化し、開発開始・同期・完了時のGit確認手順と禁止操作を追加。
- STATUSのPhase 1未コミット表記を、Git履歴とorigin/mainで確認したコミット済みの状態に修正。
- 起動確認メッセージをPhase 1の実装状況に合わせて更新。

元の日本語仕様書・手順書は変更していない。Elo・特徴量・AIモデル・予測処理は未実装。
