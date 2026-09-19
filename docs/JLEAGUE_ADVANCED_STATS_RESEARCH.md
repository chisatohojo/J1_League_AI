# J.League Advanced Match Stats 調査

調査日: 2026-09-20（JST）  
対象: J1リーグ、主に公式の J.League Data Site と J.LEAGUE.jp

## 結論

公式で、試合終了後のホーム/アウェイ値を安定して確認できたのは、少なくとも `Shots (SH)`、`CK`、`FK` です。J.League Data Site の公式記録ページはHTML本文に値を持ち、`match_card_id`で試合を識別できます。2015、2019、2024の個別試合で同じ表示形式を確認しました。

一方、公式J.LEAGUE.jpの `xG`、`Possession`、`Shots` 等のクラブスタッツページは、今回確認できた範囲ではシーズン集計（クラブ順位・合計・1試合平均）です。試合ページのHTML本文で、全試合について再利用可能な最終値を確認できる構造ではありませんでした。したがって、xG、xGA、Shots on Target、Possessionをそのままpre-match rolling feature用に収集できるとは現時点で断定できません。

## 指標別整理

| 指標 | 公式ソース | 確認できた最古年 | 2024取得可否 | 2025取得可否 | 2026取得可否 | 試合単位可否 | 最終値取得可否 | 構造化データ/API有無 | 定義上の注意 | モデル利用可否 | 備考 |
|---|---|---:|---|---|---|---|---|---|---|---|---|
| xG | jleague.jp J1 Club Stats / Expected Goals | 2024（今回確認） | シーズン集計は可 | シーズン集計は可 | 2026/27のクラブ集計ページは存在 | 未確認 | 試合単位は未確認 | ページはクラブ集計。公開APIは未確認 | xGモデル、PK込み/除外、Own Goal等の定義が公式ページだけでは確認不十分 | B | Matchページの個別xGを全履歴で検証する追加調査が必要 |
| xGA | 公式クラブスタッツで今回未確認 | 未確認 | 未確認 | 未確認 | 未確認 | 未確認 | 未確認 | 未確認 | xGAの公式名称・定義を確認できず | C | xGと同じ提供元でも別指標とは限らない |
| Shots | J.League Data Site公式記録、jleague.jpクラブスタッツ | 2015（個別試合） | 可 | 可 | 2026/27公式記録のシーズン枠を確認 | 可 | 可（試合終了後の公式記録） | HTML本文。Data Siteのmatch_card_id | `SH`の定義・ブロック等の扱いは公式記録定義を確認する必要 | A | 2024公式記録例はホーム/アウェイ値を掲載 |
| Shots on Target | 公式試合記録で今回未確認 | 未確認 | 未確認 | 未確認 | 未確認 | 未確認 | 未確認 | 未確認 | SHと枠内シュートは別項目。検索結果上の記述だけで採用しない | B | jleague.jp live表示の履歴・HTML/API検証が必要 |
| Possession | jleague.jp J1 Club Stats | 2024（今回確認） | シーズン平均は可 | シーズン平均は可 | 2026/27シーズン平均は可 | 試合単位は未確認 | 未確認 | クラブ集計HTMLとして確認。API/XHRは未確認 | 平均支配率はmatch-level最終値ではない | B | 試合ページに表示される可能性はあるが全シーズン互換性未確認 |
| CK | J.League Data Site公式記録、チーム集計 | 2015（個別試合） | 可 | 可 | 可（対象大会の公式記録が公開される前提） | 可 | 可 | HTML本文、match_card_id | 延長・PK戦を含む大会を混ぜない。リーグ90分記録との対応を固定 | A | 公式記録にホーム/アウェイ値 |
| 被シュート | J.League Data Siteチーム別集計 | 2021（今回確認） | シーズン集計可 | シーズン集計可 | ページで項目あり | 個別試合は今回の公式記録確認ではSHのみ | シーズン集計は可 | HTML本文 | `被シュート`は相手SH集計であり、Shots on Targetではない | B | 試合詳細への対応付けを追加確認 |
| 被枠内シュート | 公式で今回未確認 | 未確認 | 未確認 | 未確認 | 未確認 | 未確認 | 未確認 | 未確認 | 定義・名称未確認 | C | 代替として相手の枠内シュートが必要 |
| FK | J.League Data Site公式記録、チーム集計 | 2015（個別試合） | 可 | 可 | 可 | 可 | 可 | HTML本文、match_card_id | FK獲得数の定義確認が必要。反則数とは別 | A | 公式記録にホーム/アウェイ値 |
| ボール奪取関連 | jleague.jpの分析・クラブスタッツ候補 | 2022の分析資料で関連項目を確認 | 一部集計のみ | 未確認 | 未確認 | 未確認 | 未確認 | PDF/集計ページ中心 | recovery、duel等で定義が異なる | C | match-level rolling用途には不足 |
| 敵陣奪取 | 公式分析資料・候補項目 | 2022資料で概念を確認 | 未確認 | 未確認 | 未確認 | 未確認 | 未確認 | 構造化提供未確認 | zone、possession regain等の定義が必要 | C | 公式試合記録の標準項目として未確認 |
| PPDA | 公式で今回未確認 | 未確認 | 未確認 | 未確認 | 未確認 | 未確認 | 未確認 | 未確認 | 定義と分母（相手パス、守備行動）の差が大きい | C | 第三者データ依存になる可能性が高い |
| Final Third Entries | 公式で今回未確認 | 未確認 | 未確認 | 未確認 | 未確認 | 未確認 | 未確認 | 未確認 | 定義・座標系・イベント単位が必要 | C | 公式で自動取得可能な入口未確認 |
| Penalty Area Entries | 公式で今回未確認 | 未確認 | 未確認 | 未確認 | 未確認 | 未確認 | 未確認 | 未確認 | パス、ドリブル、走り込みの含有範囲が必要 | C | 公式で自動取得可能な入口未確認 |

「未確認」は存在しないという意味ではなく、今回の公式ページ確認だけでは、全試合を同じ方式で取得できる根拠を得られなかったという意味である。

## シーズン横断サンプル

| シーズン | 確認した公式ページ | 確認結果 |
|---|---|---|
| 2015 | Data Site公式記録（match_card_id=16803） | SH、CK、FKをHTML本文で確認。ホーム/アウェイ値あり |
| 2019 | Data Site公式記録（match_card_id=21623） | SH、CK、FKを同じ形式で確認 |
| 2021 | Data Siteチーム別集計 | シュート、被シュート、FK、CK等の季節集計を確認 |
| 2022 | J.LEAGUE公式分析レポート | 攻撃・ポゼッション・ボール奪取関連の分析項目は確認したが、試合別取得口ではない |
| 2023 | jleague.jp試合ページ・検索結果 | 試合記事内のシュート/ポゼッションへの言及は確認。ただし再利用可能な数値表としては未確認 |
| 2024 | Data Site公式記録（例: match_card_id=30619）、jleague.jpクラブStats | SH、CK、FKは個別試合可。xG・Possessionはクラブ季節集計を確認 |
| 2025 | Data Siteチーム別集計、jleague.jp xGクラブStats | SH等の季節集計とxGクラブ集計は確認。個別xG/個別Possessionの全件取得方式は未確認 |
| 2026特別 | Data Siteのシーズン選択肢 | シーズンとして選択可能。ただし対象大会・個別advanced statsの完全性は未確認 |
| 2026/27 | Data Site日程ページ、jleague.jpクラブStats | 2026/27の大会・クラブ集計表示を確認。個別advanced statsの過去互換性は未確認 |

2015～2021については、今回のサンプルではSH/CK/FKの公式記録の継続性を確認できた。一方、xG、xGA、Shots on Target、Possessionについては、同じ試合単位方式が2015～2021まで遡れる証拠を確認できていない。

## 取得方式とmatch_id対応

### J.League Data Site

- 日程・結果検索はシーズン、競技会、節を選択でき、公式試合記録へ遷移できる。
- 個別公式記録URLは `https://data.j-league.or.jp/SFMS02/?match_card_id=...` の形式で、`match_card_id`は試合ページの安定したキー候補である。
- 試合記録のHTML本文に得点、SH、CK、FK、先発等が含まれるため、ブラウザ操作を再現するcollectorには比較的向く。
- ただし、Data Site内部の既存プロジェクト`match_id`との対応表は別途必要である。日付・ホーム・アウェイ・大会を照合キーにし、重複・訂正・クラブ表記揺れを検査する必要がある。

### jleague.jp

- クラブStatsはシーズンURLで、クラブ順位・合計・平均を返す。2024年の平均ポゼッション、2024/2025年のExpected Goals、2026/27のクラブStats表示を確認した。
- 公式ページにはデータ更新タイミングとしてJ1は試合後1～2日程度と記載されるが、これはシーズン集計ページの更新であり、個別matchの全項目を機械的に取得できることを意味しない。
- 試合ページのレビュー本文は記事テキストであり、記事内の言及だけでは数値の安定取得や最終値判定に不十分である。
- HTMLに埋め込まれたXHR/APIのエンドポイントは今回確認できなかった。collector着手前に、代表matchページをブラウザのNetworkで調査する必要がある。

## 定義・欠損リスク

- `Shots`、`SH`、`Shots on Target`は同じものではない。Data Site公式記録で確認したのはSHであり、枠内シュート列ではない。
- xGは提供元のモデル定義が必要で、PKを通常のシュートと同じ扱いにするか、PKを除外するか、オウンゴール・相手のOwn Goal・リバウンドをどう扱うかを明文化しない限り、季節間比較はできない。今回確認した公式ページはxG値を表示するが、これらの定義を十分に開示していない。
- シーズン形式が通常のJ1、2026特別、2026/27で異なるため、同一大会フィルタと対象試合集合を固定する必要がある。
- 公式記録の訂正がある。Data Siteには公式記録訂正のお知らせがあるため、取得日による値の変化を想定し、再取得・監査ログが必要である。
- 未開催、延期、試合中断、クラブ名変更、昇降格、シーズン途中の大会再編はmatch_id対応と欠損判定に影響する。

## モデル用の判断

モデルで使うのは「試合終了後に確定した値を、次の試合のpre-match rolling featureへ入れる」形式である。そのため、シーズン集計を試合値の代替として使ってはならない。試合単位の最終値、match_id対応、欠損ルール、公式訂正の扱いが確認できた指標だけを採用候補にする。

### A: すぐcollector実装へ進める

- Shots（SH）
- CK
- FK

いずれも公式Data Siteの個別公式記録で、2015・2019・2024のサンプルに同じHTML表示があり、ホーム/アウェイの試合終了値とmatch_card_idを確認できた。ただし実装前に、対象全シーズンの件数照合と既存match_id対応テーブルは作る必要がある。

### B: 取得できそうだが追加調査が必要

- xG
- Possession
- Shots on Target
- 被シュート

シーズン集計または公式サイト上の候補表示は確認できるが、全対象シーズンの個別試合・最終値・構造化取得方式が未確定である。特にxGはPK込み/除外等の定義確認が必須である。

### C: 現時点では採用困難

- xGA
- 被枠内シュート
- ボール奪取関連
- 敵陣奪取
- PPDA
- Final Third Entries
- Penalty Area Entries

今回の公式確認では、安定した試合単位の公開入口、定義、過去シーズン互換性のいずれかが不足している。第三者ソースを使う場合も、公式値との照合と利用規約確認が別途必要である。

## 参照URL（確認日: 2026-09-20 JST）

- [J.League Data Site 日程・結果（2024 J1）](https://data.j-league.or.jp/SFMS01/search?competition_frame_ids=1&competition_years=2024)
- [J.League Data Site 公式記録（2015サンプル）](https://data.j-league.or.jp/SFMS02/?match_card_id=16803)
- [J.League Data Site 公式記録（2019サンプル）](https://data.j-league.or.jp/SFMS02/?match_card_id=21623)
- [J.League Data Site 公式記録（2024サンプル）](https://data.j-league.or.jp/SFMS02/?match_card_id=30619)
- [J.League Data Site チーム別集計（2021）](https://data.j-league.or.jp/SFRT08/search?competitionId=1&competitionIdEx=1&competitionYear=2021&competitionYearEx=2021&selectedCompetitionName=%E6%98%8E%E6%B2%BB%E5%AE%89%E7%94%B0%E7%94%9F%E5%91%BD%EF%BC%AA%EF%BC%91%E3%83%AA%E3%83%BC%E3%82%B0&selectedCompetitionYear=2021%E5%B9%B4)
- [J.LEAGUE.jp 2024 J1クラブStats](https://www.jleague.jp/en/j1/stats/club/2024/)
- [J.LEAGUE.jp 2024 Expected Goals](https://www.jleague.jp/en/j1/stats/club/2024/expected_goals/search-list/)
- [J.LEAGUE.jp 2025 Expected Goals](https://www.jleague.jp/en/j1/stats/club/2025/expected_goals/search-list/)
- [J.LEAGUE.jp 2026/27クラブStats](https://www.jleague.jp/en/j1/stats/club/)
- [J.League Data Site 2026/27日程・結果](https://data.j-league.or.jp/SFTP01/)
- [J.LEAGUE 2022分析レポート](https://www.jleague.jp/img/pdf/REPORT_2022_1)
