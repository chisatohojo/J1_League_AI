# J1 context feature research

調査日：2026-09-20

## 1. Executive summary

2015・2019・2024のJ1公式記録を少数サンプルで確認した。J.League Data SiteのSFMS02は、試合単位で両チームの監督、先発、控え、交代、背番号、選手名を同一HTMLに掲載している。したがって監督とstarting XIは、少なくとも公式記録の事後データとしては再現性のある候補である。

一方、試合前のproduction入力としては、先発は通常キックオフ直前に確定する。監督・先発を同一のpre-matchモデルへ無条件に混ぜず、予測時点を分ける必要がある。全競技の休養日は、J.League、JFA、AFCを横断してmatch identityを統合する追加作業が必要であり、欠場・負傷は公式に一貫した過去データ源を確認できなかった。

今回の分類は、性能ではなく取得可能性である。

| 情報 | 判定 | 根拠 |
|---|---|---|
| 監督（SFMS02） | A | 3年代の公式記録でhome/away監督を確認でき、試合単位で取得できる |
| 実休養（全競技） | B | 公式競技別ソースは存在するが、統合ID・大会横断の欠損確認が必要 |
| starting XI | B | 3年代で11人、背番号、氏名を確認できるが、選手IDと予測時点制約がある |
| 欠場・負傷 | C | injury/illness/tactical omissionを2015–2024で公式に一貫して再現する一次ソースを確認できない |

## 2. Manager history

### SFMS02

確認した公式試合ページ：

- 2015 J1：`https://data.j-league.or.jp/SFMS02/?match_card_id=16803`
- 2019 J1：`https://data.j-league.or.jp/SFMS02/?match_card_id=21623`
- 2024 J1：`https://data.j-league.or.jp/SFMS02/?match_card_id=30619`

3ページとも、公式記録内に両チームの「監督」があり、home/awayのチーム見出しの後に対応して配置されている。2015ページでは渡邉晋／石﨑信弘、2019ページではペトロヴィッチ／金明輝、2024ページではペトロヴィッチ／ハリー キューウェルを確認した。

SFMS02のURLは`match_card_id`を持つため、既存のData Site match IDとの対応は明確である。監督名自体には、SFMS02本文上で安定したstaff IDリンクを確認できないため、identityは名前だけではなく、`team_id + match_date + source name`の履歴キーで管理するのが安全である。名前表記変更や同名監督には、TeamMasterと同様の別alias管理が必要になる。

### SFIX06 / SFIX07

- `https://data.j-league.or.jp/SFIX06/`
- `https://data.j-league.or.jp/SFIX07/`
- 例：`https://data.j-league.or.jp/SFIX07/?staff_id=7861`

SFIX06は監督の検索・一覧であり、検索対象チーム名が「最新の名称」である旨が表示される。SFIX07はstaff ID付きの監督詳細と年度別成績を提供するが、確認ページは通算・年度別集計であり、各J1試合の在任開始日・終了日を直接返す履歴表ではない。したがってprimaryは試合単位のSFMS02、SFIX06/07は人物候補・補助的なidentity確認にするのが妥当である。

作成可能な候補：

- `manager_changed_since_previous_match`
- `manager_matches_in_charge`
- `manager_days_in_charge`
- `manager_first_match_flag`

ただし、試合ページの監督は試合終了後の公式記録である。過去試合から直近監督を再構成することはできるが、当日発表や交代直後のproduction予測では別の告知時刻データが必要である。結果・scoreは監督履歴作成に使用しない。

## 3. All-competition schedule / true rest

対象競技とprimary候補は次の通り。

| Competition | Primary source | 取得内容 | 注意 |
|---|---|---|---|
| J1 | J.League Data Site SFMS01/SFMS02 | 日付、match card、公式記録 | 既存match_id体系を再利用しやすい |
| J.League Cup / Nabisco / Levain | J.League Data Site | 2015の競技検索・試合記録を確認 | competition frame/nameの年代差、延長・PKを区別する必要 |
| Emperor's Cup | JFA schedule/result、match PDF | 日時、対戦、公式記録 | JFA match/PDF IDとData Site IDは別namespace |
| AFC Champions League系 | AFC official fixtures/results、stats site | 日付、対戦、match history | 大会・年度・試合IDのmappingが必要 |
| FIFA Club World Cup等 | 大会公式 | 該当年のみ追加 | J1クラブ参加年を別途列挙する必要 |

確認URL：

- J.League Cup 2015 search：`https://data.j-league.or.jp/SFPR01/search?competition_frame_id=11&competition_year=2015`
- J.League Cup SFMS02例：`https://data.j-league.or.jp/SFMS02/?match_card_id=17847`
- JFA Emperor's Cup 2015：`https://www.jfa.jp/match/emperorscup_2015/`
- JFA 2015 schedule PDF：`https://www.jfa.jp/match/emperorscup_2015/schedule_result.pdf`
- JFA 2019 match page例：`https://www.jfa.jp/match/emperorscup_2019/match_page/m80.html`
- AFC 2015 official guide：`https://assets.the-afc.com/migration/o/f/official-guide-acl2020`
- AFC match history例：`https://stats.the-afc.com/match_preview/8887`

2015のJ.League Cup公式検索では、競技名、日付、対戦、会場、試合単位の結果が確認できた。JFAの2015公式記録PDFは日時・大会・対戦・試合形式を持つ。AFCも2015の公式ガイドおよびmatch historyで日付・対戦・結果を確認できる。ただし、今回の少数確認だけでは2015–2024の全試合で欠損がないとは言えない。

実休養を作る場合は、各クラブについて全競技の公式試合を時系列で統合し、各J1 kickoffから直前の公式戦を引く。日付だけでなくkickoff時刻を使える場合は時刻を保持する。J1だけの既存schedule gapは、cup/ACLを挟む場合に実休養を過大評価する可能性がある。

現時点の分類はBであり、collector実装前に、J1クラブが参加した2015・2019・2024の代表例でJ1→cup/ACL→J1の対応表を作る必要がある。今回は大量crawlを行っていないため、具体的な全日数の主張はしない。

## 4. Starting lineup

SFMS02の3サンプルでは、両チームについて次を確認できた。

- 先発欄と11人
- 控え欄
- 交代（IN/OUT、分）
- 背番号
- 選手名
- チーム見出しによるhome/away対応
- 監督

選手名と背番号はHTMLにあるが、今回確認したSFMS02本文では、選手ごとの安定した公開player IDを取得できる構造は確認できなかった。選手identityは、Data Siteの選手一覧・詳細IDを補助的に照合する設計が必要で、氏名文字列だけでseasonを跨いで同一人物と断定してはいけない。

候補featureは作成可能性がある。

- `starting_xi_changes_from_previous_match`
- `starting_xi_returning_count`
- `previous_match_starters_available_count`
- `starter_minutes_last_n`

ただし、SFMS02は試合終了後の公式記録である。数日前に予測するAモデルには、前試合までの先発履歴だけを使用する。公式lineup発表後に予測するBモデルでは当該試合の先発を使用できるが、A/Bを同一評価に混ぜない。starting XIは今回のサンプルでは取得可能だが、player ID mappingと発表時刻が未確認のためBとした。

## 5. Injury / absence

区別すべき状態は、injury、suspension、illness、national-team absence、registration issue、tactical omission、unknown omissionである。

SFMS02で確認できるのは主に当該試合の先発・控え・交代・警告退場などの公式記録であり、非選出理由は記録されない。J.Leagueの公式出場停止告知はsuspensionの一部には使えるが、injuryやillnessを2015–2024で試合単位に完全収録する一次データ源とは確認できない。先発でないことから負傷を推測してはならない。

したがって、現時点では欠場理由featureを公式sourceだけでproduction再現するのはCである。公式クラブ発表や第三者サイトを補助利用する場合も、coverage、公開時刻、削除、利用規約、選手identityを別途検証する必要がある。

## 6. Source comparison

| Source | Official? | URL pattern | Fields | Format | ID mapping | Missing / access risk | Feasibility |
|---|---|---|---|---|---|---|---|
| Data Site SFMS02 | Yes | `/SFMS02/?match_card_id=...` | match, teams, manager, XI, bench, subs, date | HTML | `match_card_id` = existing Data Site match key | post-match record、player ID不明 | A for manager; B for lineup |
| Data Site SFIX06 | Yes | `/SFIX06/` | manager search/list | HTML | staff search/detailへ補助mapping | latest team name表示、履歴粒度不足 | B |
| Data Site SFIX07 | Yes | `/SFIX07/?staff_id=...` | manager profile、年度別成績 | HTML | staff_id | match-level tenure開始日が不足 | B |
| Data Site SFPR01/SFMS02 | Yes | competition search / match card | Cup schedule/result | HTML | Data Site match_card_id | competition IDs/名称の年代差 | B |
| JFA Emperor's Cup | Yes | `/match/emperorscup_<year>/...` | schedule、公式記録、日時 | HTML/PDF | JFA match/PDF ID | Data Site IDとは別 | B |
| AFC official/stats | Yes | AFC competition/match URLs | fixtures、results、match history | HTML/PDF/structured pages | AFC match/competition ID | historical URL/format差、外部クラブ名 | B |
| Third-party injury source | No | provider dependent | injuries/absence claims | varies | player/team mapping必要 | terms、coverage、公開時刻、推測混入 | C until audited |

## 7. Coverage matrix by season/source

以下は「少数sampleで存在を確認した範囲」であり、全シーズン完全性の保証ではない。

| Season | SFMS02 manager/XI | J.League Cup source | JFA Emperor's Cup | AFC source |
|---|---|---|---|---|
| 2015 | confirmed: match_card_id 16803 | confirmed: competition search、SFMS02 cup page | confirmed: schedule/PDF | confirmed: official guide/match history |
| 2019 | confirmed: match_card_id 21623 | not exhaustively sampled | confirmed: JFA match page m80 | not exhaustively sampled |
| 2024 | confirmed: match_card_id 30619 | not exhaustively sampled | not exhaustively sampled | not exhaustively sampled |
| 2016–2018, 2020–2023 | URL pattern exists, full coverage not established | not established | not established | not established |

「2015–2024で安定取得可能」というA判定を付けるには、各年の代表match、競技別の欠損、ID対応、名称変更、延期・中止・延長・PKを追加検証する必要がある。

## 8. Identity mapping considerations

### Manager

primary key候補は`team_id + match_date + manager source name`。SFIX07の`staff_id`が取得できる場合は補助キーにする。SFMS02の名前とSFIX07の名前を手書きnormalizeやfuzzy matchで接続しない。

### Player

`team_id + player_id`が取得できる場合を優先し、未取得時は名前・背番号だけでstable identityを作らない。移籍、登録名変更、外国人表記差があるため、TeamMaster相当のplayer alias tableが必要になる。

### Competition match

既存J1はData Site `match_card_id`を維持する。JFA/AFCは独自match IDを保持し、`date + normalized stable team IDs + competition`の候補で照合し、曖昧な場合は拒否する。試合結果やscoreをidentity mappingの根拠にしない。

## 9. Leakage / prediction-time availability

- SFMS02の監督、lineup、交代、match statsは原則として試合終了後に確定する。
- pre-match predictionでは、対象試合自身のSFMS02を使わず、過去試合までの記録だけを使う。
- starting XI発表後のモデルは、数日前モデルと別のprediction timestampを持つべきである。
- suspensionは公式発表日・適用試合を確認し、試合後の公式記録から逆算しない。
- injury/illnessは、情報公開時刻が不明な記事を自動的にpre-match featureへ入れない。
- cup/ACLの試合日付だけでなく、延期・延長・PK・kickoff timezoneを統一する。
- 2025 Testおよび2026 Reservedのモデル評価は今回行っていない。

## 10. Recommended implementation order

最初に実装を推奨するfeature groupは、**SFMS02の監督履歴**である。

理由は、公式試合単位で2015・2019・2024を確認でき、home/away対応と既存match_card_id mappingが明確で、starting XIよりprediction-time leakageを管理しやすく、全競技横断休養より実装範囲が小さいためである。まず`manager_changed_since_previous_match`と在任試合数のような過去記録ベースのfeatureに限定し、公開時刻を含むproduction入力仕様を先に決める。性能改善は今回判断していない。

次段階は、全競技休養日の小規模cross-competition mapping調査、その後にplayer IDが確認できた場合のみstarting XI continuityを別timestampモデルとして進める。欠場・負傷は公式coverageが確認できるまで採用しない。

## Sources and access date

上記URLは2026-09-20に確認した。公式ページの代表確認に使用したURLは以下。

- [Data Site SFMS02 2015 sample](https://data.j-league.or.jp/SFMS02/?match_card_id=16803)
- [Data Site SFMS02 2019 sample](https://data.j-league.or.jp/SFMS02/?match_card_id=21623)
- [Data Site SFMS02 2024 sample](https://data.j-league.or.jp/SFMS02/?match_card_id=30619)
- [Data Site SFIX06](https://data.j-league.or.jp/SFIX06/)
- [Data Site SFIX07](https://data.j-league.or.jp/SFIX07/)
- [Data Site SFIX07 manager example](https://data.j-league.or.jp/SFIX07/?staff_id=7861)
- [Data Site 2015 J.League Cup search](https://data.j-league.or.jp/SFPR01/search?competition_frame_id=11&competition_year=2015)
- [Data Site 2015 J.League Cup match example](https://data.j-league.or.jp/SFMS02/?match_card_id=17847)
- [JFA 2015 Emperor's Cup](https://www.jfa.jp/match/emperorscup_2015/)
- [JFA 2015 schedule/result PDF](https://www.jfa.jp/match/emperorscup_2015/schedule_result.pdf)
- [JFA 2019 match page example](https://www.jfa.jp/match/emperorscup_2019/match_page/m80.html)
- [AFC 2015 official guide](https://assets.the-afc.com/migration/o/f/official-guide-acl2020)
- [AFC match history example](https://stats.the-afc.com/match_preview/8887)
