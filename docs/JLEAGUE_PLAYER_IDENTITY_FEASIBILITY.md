# J.LEAGUE official player identity feasibility for SFMS02 minutes

調査日: 2026-09-21。対象は2015～2024通常J1の既存SFMS02 cache **3,208試合**と、生成済みの**115,468 player-match squad rows**。公式サイトの少数標本以外に外部データは使わず、player master、CSV変更、workload feature、model評価は行わない。`docs/SFMS02_PLAYER_MINUTES_FEASIBILITY.md`と`docs/SFMS02_PLAYER_MINUTES_DATASET.md`を前提とする。

## Verdict

**C — 現段階ではproductionのcross-match workload featureには不十分。** J.League Data Siteには人物ごとの`player_id`付き公式詳細ページがあり、同じIDの年度別成績には複数クラブ・複数seasonが載る。しかしSFMS02のlineup/eventにはそのIDへのリンクがなく、2015～2024の各試合のraw名をIDへ一意に結び付けるための、時点付きhistorical rosterの網羅性を確認できていない。IDの存在は確認できたが、115,468行の高coverage exact linkageは未証明である。名前だけで独自IDを発行しない。

## 1. Local SFMS02 identity structure

season probeで限定した3,208 cached HTMLの選手領域をread-only走査した。A5先発70,576行、A6控え44,892行、A7交代47,276行、A9退場301行、およびA8警告7,671行の`td.name`を確認した。これらの選手セル/行には選手別`href`、profile URL、`id`/`data-*`/`onclick`属性、hidden input、埋め込みの`player_id`/registration IDは**0件**。A5～A9のside section内にも選手リンクは0件で、全HTMLにも`player_id`、`member_id`、`player_profile`、`/SFPL...`の明示的な文字列は見つからなかった。これは観測した構造と文字列に関する陰性結果であり、任意の難読化された内部IDが絶対に存在しないという主張ではない。

例: local `data/raw/jleague_match_stats/16818.html`のA5/A6は`td.position`, `td.number`, `td.name`, `td.time`のplain cells、`21623.html`のA7は`td.change`, `td.name`, `td.time`で、名前にanchorはない。名前の内部全角空白はそのまま保持される。背番号やpositionはmatch-localな補助情報であり永続IDではない。A8/A9も同様。従って**SFMS02 stable player ID present: no**。

## 2. Observed official identity routes

| Official route | Observed information | Identity implication / limitation |
| --- | --- | --- |
| [Data Site 全選手一覧 SFIX03](https://data.j-league.or.jp/SFIX03/) and [actual list result](https://data.j-league.or.jp/SFIX03/search) | official display name, English name, latest club, birth date; player-name link | list nameリンクから [SFIX04 detail](https://data.j-league.or.jp/SFIX04/?player_id=11446) のnumeric `player_id`へ辿れる。ただし検索対象clubは「最終所属」で、過去の各所属クラブからは検索できない、と公式画面に明記 |
| [Data Site SFIX04 example: 松田 陸](https://data.j-league.or.jp/SFIX04/?player_id=11446) | numeric URL ID, official name, birth date, year/club/competition appearance table | 同じprofile IDの複数season・クラブを確認できる。年度別**出場成績**であり、全登録者・登録有効日・試合別名義の完全な表ではない |
| [Data Site 登録選手一覧 SFIX02 example](https://data.j-league.or.jp/SFIX02/search?lang=ja&selectValue=1&selectValueTeam=10) | 現在表示中の大会・club roster、選手名等と更新日 | current roster routeは確認できたが、2015/2019/2024の過去時点の完全snapshotをこの少数標本から取得できていない |
| [J.LEAGUE.jp current club roster example](https://www.jleague.jp/club/kashima/player/) → [individual profile example](https://www.jleague.jp/player/1632225/) | 別namespaceのnumeric profile URL ID、current club lineup | Data Siteの`player_id`と同一値・同一namespaceとは仮定しない。2019の[公式名鑑告知](https://www.jleague.jp/news/article/14013/)内のclub roster linkも現行club rosterへ遷移した |

J.LEAGUE.jpの[名鑑検索画面の観測例](https://www.jleague.jp/player/?birth_day_date_from=&birth_day_date_to=&birth_day_month_from=&birth_day_month_to=&birth_day_year_from=&birth_day_year_to=&birth_place=&height_from=&height_to=&player_name=&team_id%5B%5D=120&uniform_no=&weight_from=&weight_to=&year=2007)には2015～2024を含むseason selectorがある。ただし今回、2015/2019/2024の検索結果をそれぞれ実際のhistorical roster rowsとして取得・再現できなかった。selectorの存在や[2024公式公開告知](https://www.jleague.jp/news/article/27175/)だけをfull historical coverageの証明にしない。URL patternや内部endpointを推測して補完しない。

### Transfer stability: confirmed profile-level examples

次は**各行が同じ公式profile URL上にある**ことを根拠とし、名前一致だけでは結び付けていない。

| Data Site `player_id` | Official year/club evidence within one profile | Finding |
| --- | --- | --- |
| [`11446`](https://data.j-league.or.jp/SFIX04/?player_id=11446) | 2015 FC東京、2016～2022 C大阪、2024 G大阪 | 移籍・division変化後も同一profile ID |
| [`49249`](https://data.j-league.or.jp/SFIX04/?player_id=49249) | 2023 横浜FC、2024 鳥栖 | J1クラブ移籍後も同一profile ID |
| [`19209`](https://data.j-league.or.jp/SFIX04/?player_id=19209) | 2021～2022 横浜FM、2023～2024 C大阪 | 表示名の長短があっても同一profile IDの年度別成績 |

この標本はprofile内のID継続を示すが、SFMS02 raw表示名の自動対応を保証しない。2015～2024全員についてID安定性・profile欠損率を測ったものでもない。

## 3. Exact raw-name inventory and collision

処理済みplayer-minutes CSVの**1,783 unique exact raw strings**を、`player_name_raw`、`team_id`、`season`、`match_date`だけで集計した。表記差は人物統合に使っていない。

| Local diagnostic | Count | Interpretation |
| --- | ---: | --- |
| 同一raw名が複数team IDに現れる | 579 names | 真の移籍と別人同名が混在し、名前だけでは分類不能 |
| 同一raw名・同一seasonで複数team ID | 142 name-season keys | season中移籍もあり得る。これだけではcollision確定ではない |
| 同一raw名・同日・別teamの登録 | **22 name-date keys / 4 raw names** | 強い同名衝突候補。うち11 name-date keysで両側のnormalized minutesが正、5 keysで両側先発 |
| 同一matchの両sideで同一raw名 | 0 | 異なるmatch間の同日衝突は残る |
| match/team内のexact duplicate | 0 | match-local parser keyは成立 |

4 raw namesの同日衝突は、ドゥドゥ（11日）、セルジーニョ（8日）、松田　陸（2日）、レアンドロ（1日）。例: 2019-02-23のセルジーニョは鹿島`21493`と松本`21494`で双方先発。2018-04-11の松田　陸はC大阪`20801`とG大阪`20804`に登録。同日別clubの表記一致を単一人物としてmergeしてはいけない。

公式一覧でも、同名`セルジーニョ`には[松本側 `player_id=23156`](https://data.j-league.or.jp/SFIX04/?player_id=23156)と[鹿島側 `player_id=29580`](https://data.j-league.or.jp/SFIX04/?player_id=29580)が別profileであり、生年月日も異なる。同名`松田　陸`にも[C大阪側 `11446`](https://data.j-league.or.jp/SFIX04/?player_id=11446)と[G大阪側 `29236`](https://data.j-league.or.jp/SFIX04/?player_id=29236)が存在する。この2例は公式ID差による確定的なraw-name collision。ドゥドゥ・レアンドロの個々のIDは今回確定していないので候補のままとする。

文字形のexact inventoryでは、先頭/末尾空白を持つ名前0、replacement characterを含む名前0。1,631 unique名に内部全角空白、434名にカタカナがある。ASCII空白・中黒・ASCII/全角Latinを含むraw名は各0。空白除去またはNFKCで同じ文字列となる**異なるraw名の組**は、この1,783名内で0。ただしこれは同一人物の別表示（特に外国籍選手のカタカナ表記変更）が存在しない証明ではなく、表記変更率を推定する材料にもならない。音韻・類似度・手作業推測によるmergeは行っていない。

source間の表記差もある。例えばSFMS02に`レオ　セアラ`というraw名がある一方、[Data Siteの該当season/clubを持つprofile](https://data.j-league.or.jp/SFIX04/?player_id=19209)の見出しは`レオ　セアラ（レオナルド）`である。この**非exact**な組を自動aliasにせず、公式な別表記根拠または別の厳密な照合がない限り未解決とする。外国籍選手の表示名変化をraw文字列だけで網羅的に測ることはできない。

## 4. Historical coverage and estimated linkage feasibility

| Sample season / club | Verified official evidence | Historical roster with per-player ID, exact display name, club, season |
| --- | --- | --- |
| 2015 FC東京 | [SFIX04 `11446`](https://data.j-league.or.jp/SFIX04/?player_id=11446)の2015 FC東京成績 | **未確認**。profileのappearance rowは確認、full rosterではない |
| 2019 C大阪 | 同じ[`11446`](https://data.j-league.or.jp/SFIX04/?player_id=11446)の2019 C大阪成績、[2019名鑑告知](https://www.jleague.jp/news/article/14013/) | **未確認**。告知先club URLは現行一覧へ遷移 |
| 2024 鳥栖 | [SFIX04 `49249`](https://data.j-league.or.jp/SFIX04/?player_id=49249)の2024 鳥栖成績、[2024名鑑告知](https://www.jleague.jp/news/article/27175/) | **未確認**。全登録者の歴史的rosterを検証できず |

上記は3 season / 3 clubの**profile-level sample**であり、historical roster availabilityの肯定ではない。SFIX03は現在の最終所属clubで検索されるため、過去のclub-season全選手の列挙にはそのまま使えない。SFIX04は同一IDの年度別成績を持つものの、出場ゼロの登録選手や途中加入・抹消の有効日を必ずしも列挙しない。よって**115,468行の何%をexact IDへlinkできるかは現時点で数値推定不可**。「大部分可能」との判定もしない。

## 5. Future strict linkage design — not implemented

1. 実際に取得できた公式roster/profileから、出典・取得時点・`official_player_id`・official name・club・season・可能なら登録有効期間を保存する。Data Site IDとJ.LEAGUE.jp IDは別namespaceとして保管し、公式なcrosswalk無しに同一値扱いしない。
2. `SFMS02(team_id, season, player_name_raw, match_date)`と、同じclub/season・当該match時点に有効な公式roster recordを**exact raw文字列**で照合する。team IDと公式club表示の対応も別途根拠を確認。1件だけ残るときのみ`EXACT`候補とする。公式名とSFMS02名の表記が異なる場合、類似度・NFKC・空白削除による自動確定はしない。
3. 同じキーで複数公式IDが残る場合は`AMBIGUOUS`/`COLLISION`、候補なし・有効期間不明なら`UNRESOLVED`。同名衝突や途中移籍は、日付根拠がない限りseasonだけで解消しない。後から判明した最新所属を、当時既知の所属状態として扱わない。
4. 一度確定したIDについては、公式profileの所属履歴を別テーブルで保持し、transfer後も同じIDで結ぶ。該当するraw rowへの証拠URLと照合理由を監査可能に残す。

提案schema（未実装）: `player_id`（内部永続キー）、`official_player_id`、`official_player_name`、`source_profile_url`、`source_namespace`、`season`、`team_id`、`official_club_name`、`sfms02_player_name_raw`、`valid_from`、`valid_to`、`link_status`（`EXACT`/`AMBIGUOUS`/`UNRESOLVED`/`COLLISION`）、`link_reason`、`evidence_url`、`observed_at_utc`。内部`player_id`は公式identityが確定するまで発行しない。validityは資料に無ければnullとし、架空の日付を補わない。

## Workload readiness and limitations

`minutes_last_7d/14d/30d`、`starts_last_5/10`、`consecutive_starts`、`days_since_last_appearance`はいずれも**C / production未ready**。minutes自体は3,208試合で復元済みだが、player IDと時点付きclub affiliationの全件リンクがまだない。将来のfeatureはtarget match自身・未来matchのminutesを使わず、予測時点以前に確定したappearanceのみを集計する必要がある。J1-onlyデータではCup/J2/AFC等の負荷も欠ける。

同一team・同一seasonのexact raw名だけを使う限定fallbackは、異clubの同名衝突をある程度隔離できるが、同じclub内の同名選手、mid-season transfer、登録名変更、season境界での継続を保証しない。研究用の短期表示一致診断に留め、stable player identityやproduction workloadへ昇格させない。

## Request discipline

Local cache auditは追加web request **0**。公式ソース限定のweb調査は少数の一覧・profile・告知ページに留め、full roster/player crawlは実施しなかった。調査ツール上の操作は公式ページ`open/click` **32回**（重複閲覧・不達3件を含む）、検索query **18件**。検索ツールが内部で行った実HTTP request数は公開されないため、厳密なwire-level request countは**unknown**。非公式サイトはidentityの根拠に使っていない。
