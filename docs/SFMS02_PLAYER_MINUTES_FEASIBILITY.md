# SFMS02 player-match minutes reconstruction feasibility

調査日: 2026-09-21。対象は既存のJ.League Data Site SFMS02 raw cacheから、2015～2024の通常J1 **3,208試合**のみ。ネットワーク取得、production parser、player-minutes CSV、feature、prediction、model評価は行っていない。既存の[project status](PROJECT_STATUS_2026_09_20.md)、[data pipeline status](DATA_PIPELINE_STATUS.md)、[research roadmap](NEXT_DATA_RESEARCH_ROADMAP.md)、[Starting XI audit](JLEAGUE_STARTING_XI_AUDIT.md)と、`src/collect/jleague_match_stats.py` / `src/collect/jleague_match_managers.py` / 関連testsを確認した。下記件数はone-shotのread-only軽量走査による監査値であり、保存済みprocessed minutesではない。

## Verdict

**B — 通常ケースのmatch-local participation intervalは概ね復元可能。ただし「正確な実時間のminutes played」としては未確定。** A5/A6の登録選手、A7の交代ペア、A9の退場は対象全件で構造・名前・時刻をほぼ整合させられる。一方、公式の試合終了実時刻・added-timeを含む実durationは見つからず、`46'`がハーフタイムと後半開始直後のどちらかを全件で区別できない。交代済み選手の後刻退場、および出場しない控えの退場も実在する。したがって、90分に正規化した**規約上の参加分数**なら将来の限定的な実装候補だが、物理的なプレー時間・公式出場分数と同一視しない。長期player ID不在は別の未解決問題で、workload feature化の承認ではない。

## Local source structure and scope

- J1 probe CSVの`match_id`を2015～2024に限定してraw cacheへstrict対応させた。season件数は2015～2020が各306、2021が380、2022～2023が各306、2024が380。対象3,208 HTMLとmetadataが全件存在し、`match_id`、byte count、SHA-256のcache検証は **3,208/3,208**。raw directory全体の3,588ページには2025も含まれるが、今回の監査対象から除外した。
- A5: 左右`two-column-table-box-l/r`の先発11人。A6: 同じsideの控え。各player rowに`td.position`（GK等）、`td.number`、`td.name`、`td.time`がある。標本・走査ではA5/A6の`time`は空欄。A5の11人coverageは既存auditとも一致。
- A7: side別「交代」。1イベントは隣接する`▽` OUT行と`▲` IN行。**時刻はOUT行の`td.time`だけ**にあり、IN行は空欄。同じペアの時刻をINへ継承できる。ページの凡例も`▲：IN ▽：OUT`。A8は警告、A9は退場で、それぞれplayer nameと`td.time`を持つ。A8/A9はイベントがない場合、sectionごと存在しないことがある。A10は監督、A12は日付・kickoff・会場・天候等で、標本に公式の終了時刻/実durationはない。
- A5/A6/A7/A9の`td.name`は、matchとside内でHTML周辺空白を除いた**exact raw文字列**としてのみ結合した。内部の全角空白、表記、Unicodeは統合・fuzzy補正していない。背番号やポジションは照合補助であり、永続的player IDではない。

## Full-cache diagnostic

| Check | Result |
| --- | ---: |
| 対象・section構造を読めたmatch | 3,208 / 3,208 |
| parse/section structure failure | 0 |
| 交代ありmatch / 交代なしmatch | 3,208 / 0 |
| 交代なしteam side | 6 / 6,416 |
| A7 OUT–INペア | 23,638 |
| ペア順序・件数不整合 / 未知change記号 | 0 / 0 |
| OUT時刻欠損 / IN行の予期しない時刻 | 0 / 0 |
| OUT名・IN名の同side A5/A6 exact照合失敗 | 0 / 0 |
| 同一sideのA5+A6 raw name collision | 0 |
| A9退場行 / 退場ありmatch | 301 / 286 |
| A9時刻欠損 / A5+A6 exact照合失敗 | 0 / 0 |
| 控え登録row / IN未記録の控えrow | 44,892 / 21,254 |
| 途中出場後に交代でOUTとなるplayer-match | 134 |
| GKを含む交代ペア | 62 |

「交代なし」の全試合例はこの期間に**存在しない**ため作らない。代わりに`16818`のhome sideはA7 rowがなく、対戦側には交代がある。A7 rowがないsideについて、A6登録選手を0分、A5選手を原則full-match候補として扱えるが、A9退場は別途確認が必須。21,254は控え**登録row**数で、重複しない永続選手数ではない。

## Minute notation, halftime and match duration

A7 OUT行では通常の`70'`、`45'`、`46'`、`90'`に加え、**`45'+X` / `90'+X`**が実在する。A7 OUTは`46'`が1,717件、`45'`が12件、`45'+X`が35件、`90'+X`が1,137件。A9退場には`45'+X`が10件、`90'+X`が41件ある。走査したA7 OUT/A9時刻はすべて`N'`か`N'+X`形式で、その他の文字列形式・時刻欠損は0。`HT` / `ハーフタイム`表記は見つからなかった。A9には`90'+18`（`21036`）もあるため、`90'+X`を93等の数値に直して全員のmatch durationへ加えることはできない。

将来の**90分基準の規約上の参加分数**なら、full matchを90とし、後半added-time `90'+X`の境界を90でcap、前半added-time `45'+X`を前半境界45でcapする方針が一貫している。これは実際にピッチにいたadded-time分を捨てる定義であり、公式に公表された「出場時間」の換算式と確認したわけではない。例えば90+3に入った選手は、この規約では0分だが、実際にはadded timeに出場している。0分と未出場は`appearance_type`/IN eventで区別する必要がある。

`46'`は交代行で非常に多く、後半開始時の交代と整合する。ただし、SFMS02には別のHT flagがなく、46分表示だけではハーフタイム中か後半開始直後かを全件で証明できない。45/46境界の1分差を厳密な実durationとして扱わない。production化するなら、`46'`を45分境界へ写すか表示minuteとして残すかを**事前に明文化し、公式別根拠または標本で検証**する。今回どちらかの値をCSVへ確定保存していない。

## Dismissal, double substitution and goalkeeper cases

A9の`退場`には名前と時刻がある。`16803`では野沢 拓也がA8で35'と63'に警告、A9で63'に退場し、交代A7には退場として現れない。したがって、ピッチ上のplayerならdismissalを終了境界にでき、90分full扱いは誤り。ただしA9が常に「出場中」を意味するわけではない。`27377`ではディエゴ ピトゥカがA7で63'にOUT、その後A9で64'に退場しているため、参加終了は**63'**であり64'ではない。`28320`では控え登録の三田 啓貴がA7 INなしで`45'+2`に退場しており、出場分数は0候補。301 A9行の内訳は、A5 starterで交代OUTなし263、A6からIN後36、交代OUT後1、INのない控え1。前二者だけをon-field dismissalとしてminutes終了に使える。A9のdirect red / second yellowの区別はminutes計算に必要ないが、A8警告だけから退場を推定しない。

`16810`では控えの岡田 翔平が56'にIN、80'にOUTする。1人に開始・終了両境界を持たせられ、単純な「starterかsubか」だけでは不十分。`16902`ではGK秋元 陽太が46'にOUT、控えGKイ ホスンがIN。GKもA7の同じペア構造なので、位置別の特別な交代parserは不要。ただし上記46'境界の解釈はGKにも残る。

## Representative raw-cache evidence

| match ID / date | Observed local HTML | Why it matters |
| --- | --- | --- |
| `16818`, 2015-03-14 | home A7空、away A7に交代 | side単位の交代なし。期間内に両side交代なしmatchはない |
| `21623`, 2019-06-22 | ジェイ`▽ 70'` → アンデルソン ロペス`▲`（時刻空欄） | 通常ペア。IN時刻を同じペアから得る |
| `16810`, 2015-03-07 | 岡田 翔平`▲ 56'相当`、後に`▽ 80'` | 途中出場後に途中交代 |
| `16902`, 2015-05-14 | GK秋元 陽太`▽ 46'` → GKイ ホスン`▲` | GK交代・HT境界候補 |
| `16977`, 2015 | A7 OUT `45'+3` | 前半added-timeの表記 |
| `16803`, 2015-03-07 | A9野沢 拓也`63'`、A8にも同時刻警告 | 交代なしの退場 |
| `21036`, 2018-11-24 | A9ウェリントン`90'+18` | 90分を超える実イベント表記とdurationの違い |
| `27377`, 2022-04-02 | A7ディエゴ ピトゥカ`▽ 63'`、A9同名`64'` | 交代後退場のためA9を優先してはいけない |
| `28320`, 2023-06-24 | 控え三田 啓貴、A7 INなし、A9`45'+2` | bench dismissalでもminutesは増やさない |

各IDの証拠は`data/raw/jleague_match_stats/{match_id}.html`と同名metadataにあり、未加工bytesとSHA-256を保持している。表記を読みやすくする空白表示はしているが、identity判定は内部空白を正規化していない。

## Proposed future player-match schema and algorithm — not implemented

| Field | Meaning |
| --- | --- |
| `match_id`, `match_date`, `team_id`, `team_name`, `player_name_raw` | match-local key and exact official display name |
| `starter`, `entered_minute`, `left_minute`, `dismissed_minute` | lineup status and original event/boundary; original `45'+X`等のraw tokenも別列で保持 |
| `minutes_played`, `minutes_convention` | 事前に固定した90分正規化の値とversioned定義。未解決caseはnullとreason |
| `appearance_type` | `starter_full`, `starter_subbed_out`, `sub_entered`, `sub_entered_and_left`, `dismissed`, `unused_substitute`等。交代後退場・控え退場は別flagも必要 |
| `source`, `source_url`, `raw_sha256`, `identity_status`, `minute_quality_flag` | provenanceと例外の監査可能性 |

将来の処理順序は、sideごとにA5/A6 exact名の重複を拒否し、A7の隣接`▽/▲`を同時刻ペアとして取り込み、A9を**現在on-fieldかどうか**と照合し、その後各選手のintervalを閉じるもの。starterは開始0、A6のINなしは未出場、INありはペア時刻から開始。終了は自分のA7 OUT、on-field A9退場、または規約上の90分末尾のうち実際に先に起きたもの。交代後A9退場や控えA9退場で参加時間を延ばしたり縮めたりしない。先発→交代、途中出場→交代/退場、GK、0分のlate INを別々に検査する。`46'`の境界方針を確定し、team-level time accountingと例外監査を通すまで正式な`minutes_played`出力を作らない。

## Future workload ideas and leakage boundary

将来候補は`minutes_last_7d/14d/30d`、`starts_last_5/10`、`consecutive_starts`、`days_since_last_appearance`、`team_minutes_last_7d/14d`、`starter_minutes_share`、`rotation_minutes_delta`。今回は計算・性能判断していない。SFMS02のminutesは**試合後情報**であり、target match自身のminutesをその試合のpre-match featureに入れない。target kickoffより前に終了した試合だけを使い、既存のsame-date batching policyで同日・同時刻の結果を相互利用しない。複数試合間で同一選手にworkloadを結ぶにはstable player IDまたは公式根拠のあるidentity masterが別途必要で、match-local raw nameだけでは足りない。未確認のCup/AFC appearancesも合算しない。

## Limitations / next gate

この監査はDOMと整合性の軽量走査で、1人ごとのproduction minutesを全件計算・外部の公式分数と照合したものではない。SFMS02には見つけられた範囲で公式の実match durationや「played minutes」欄はなく、added time・46'は規約選択の影響を受ける。将来進めるなら、(1) 公式のminute conventionとHT表示の追加根拠、(2) 90分正規化の固定仕様、(3) on-field A9判定と例外テスト、(4) player identity、(5) 時点利用可能性を、production化・feature化前のgateとする。
