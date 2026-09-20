# J2 Elo data feasibility

確認日: 2026-09-20

## 結論

判定は **B**。J.League Data SiteにはJ2をseason + competitionで検索できる公式listingがあり、match-levelのdate、home、away、score、SFMS02へのmatch identityを取得できる構造が確認できる。したがって収集自体は現実的である。

ただし今回はfull crawlを行っていないため、2015～2024の全J2 club aliasを既存TeamMasterだけで解決できるか、未登録club数、official club IDの全件coverageは未確定である。J1+J2 Eloへ進む前に、J2全期間のclub identity監査とTeamMaster拡張方針が必要になる。

## Official source structure

Data Site SFMS01の検索項目にはseasonと大会があり、J2 Leagueを選択できる。2015 sampleは次の公式検索URLで確認した。

`https://data.j-league.or.jp/SFMS01/search?competition_frame_ids=2&competition_years=2015&lang=en`

ページには2015 J2の試合日、節、home、90分スコア、away、会場等のresult rowsが表示される。[2015 J2 official listing](https://data.j-league.or.jp/SFMS01/search?competition_frame_ids=2&competition_years=2015&lang=en)（確認日 2026-09-20）

J.League Data Siteの検索画面は2015～2024をseason selectorで保持し、J2を大会候補として表示する。[SFMS01 official search](https://data.j-league.or.jp/SFMS01/)（確認日 2026-09-20）

competition frameはJ2の `2` を使用するURL形が確認できた。実装時は、2015・2019・2024を先に取得し、SFMS01の実DOM rowから同一row内のSFMS02 linkとmatch_card_idを検証する必要がある。IDを連番推測してはいけない。

## Sample feasibility

| season | official listing URL pattern | sample fields observed/expected | full-year status |
|---:|---|---|---|
| 2015 | `competition_frame_ids=2&competition_years=2015` | date, round, home, 90-minute score, away, venue; SFMS02 identity path to verify per row | sample confirmed; full crawl not performed |
| 2019 | `competition_frame_ids=2&competition_years=2019` | same official SFMS01 search family; representative fetch required before parser | not fully verified |
| 2024 | `competition_frame_ids=2&competition_years=2024` | same official search family; current competition naming/row structure must be checked | not fully verified |

Expected ordinary J2 format is generally 22 clubs / 42 rounds / 462 matches for seasons with 22 clubs, while a 20-club season has 380 matches. These are format expectations, not collected counts; COVID-era scheduling and format changes must be validated from the actual listing before any dataset is written. The official J2 overview describes a home-and-away double round-robin format and 38 matchdays for the current format.[J2 competition overview](https://www.jleague.jp/en/outline/j2/)（確認日 2026-09-20）

## Fields needed for Elo

The official result listing is suitable for the required match-level fields:

- `match_date`
- raw `home_team` / `away_team`
- `home_score` / `away_score`
- round / competition label
- source URL and SFMS02 `match_card_id`, if the row link is present

The 90-minute result must be derived only from the ordinary score: away win = 0, draw = 1, home win = 2. Promotion playoff, relegation playoff, penalty shootout winner, extra-time winner, or aggregate-tie winner must not be substituted for the league result. J2 regulations describe a draw when scores remain level after 90 minutes.[J2 competition overview](https://www.jleague.jp/en/outline/j2/)（確認日 2026-09-20）

## Club identity scope

J2 Elo needs every J2 opponent, not only clubs later promoted to J1. Existing J1 TeamMaster may resolve many clubs that have appeared in J1, but J2-only clubs, renamed clubs, and historically bounded aliases may remain unresolved. This audit did not add aliases or change `teams.csv`, and no full-season club union was generated.

Therefore the following full-period quantities remain **not yet measured** without the prohibited full crawl:

- J2 2015～2024 unique club count
- existing TeamMaster-resolved count
- unresolved club count and names
- official source club ID coverage

The SFMS01 row's official club display name can be retained as raw provenance. If an official club identifier is present in the row/team link, it should be collected and compared with the TeamMaster mapping; no fuzzy matching or name-only automatic identity resolution should be used.

## J1 ↔ J2 continuity

At the conceptual level, continuity is feasible for clubs resolved to the same stable TeamMaster ID: J1 and J2 season memberships can be joined by `team_id`, and a single chronological stream can include both competitions. This would allow J1→J2→J1 rating updates without inventing a frozen J1 state.

The continuity is not yet operationally proven for all 2015～2024 clubs because the J2 club identity union has not been collected. J2 clubs promoted from J3 create a separate limitation: without J3 matches, their lower-division prehistory remains unavailable and their first J2 rating would still start from the chosen initial state.

## Access and collection risk

Only a few official listing samples were inspected; no full crawl, CSV, TeamMaster change, or network batch was performed. The source appears suitable for a sequential cached collector. Before implementation, validate:

1. exact SFMS01 result-table selector and row structure for 2015, 2019, and 2024;
2. same-row SFMS02 `match_card_id` availability;
3. season counts and postponed/rescheduled matches;
4. all J2 names against TeamMaster, without fuzzy matching;
5. raw HTML metadata/SHA256 cache reuse.

## Final decision

**B: official collection is feasible, but identity expansion is substantial and must be audited first.**

The next safe step is a limited parser prototype for 2015, 2019, and 2024, followed by a full J2 club identity diagnostic. This research did not implement a collector, alter Elo, modify TeamMaster, collect J3, or use 2025/2026.
