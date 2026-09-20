# Data pipeline status (2026-09-20)

This is a repository inventory, not a collection run. Counts below come from the **currently present local CSVs**. `raw cache` indicates a local source copy was found, not that every associated match has a complete, independently verified raw archive. Source documents provide the lineage and caveats; current input counts take precedence over older expected counts. Data outside `data/processed` may be intentionally ignored by Git, so another checkout must check materialization independently.

## A. Production / reusable inputs

| Source | Seasons and observed rows | Raw cache / processed output | Identity and chronology | Usable information / current limitation |
|---|---:|---|---|---|
| Ordinary J1, J.League Data Site | 2015–2025 **3,588**: 2015–20 306/year, 2021 380, 2022–23 306/year, 2024–25 380/year | `data/raw/jleague/`; `data/processed/jleague/{year}_matches_probe.csv` | `match_id` unique; TeamMaster exact aliases; `match_date, match_id`; 2015–16 two-stage, later full-season, 2021 20 clubs | Results, basic schedule, Elo/form history. Post-match values must be lagged. |
| 2026 J1 Hyakunen | **200** | `data/raw/jleague/2026_hyakunen/`; `data/processed/jleague/2026_hyakunen/matches.csv` | Distinct competition key and match IDs; all 200 have regulation-time result; date/ID ordering | Elo state and Domestic Rest dates only. PK/extra-time winner and Logistic target excluded. |
| 2026/27 ordinary J1 | schedule **380**, completed **70**, future **310** | J.League raw snapshots/revisions; `data/processed/jleague/2026_27/{schedule,completed_matches}.csv` | 70 completed official IDs; future rows have no official match ID but retain fixture key; saved completion evidence and revision history | Interim target and chronology; the open lockbox is not a new selection dataset. Same-time replay requires audit (see project status). |
| J2, SFMS01 | 2015–2024 **4,538** | `data/raw/jleague_j2/` (10 cached HTML listings + metadata); `data/processed/jleague_j2/2015_2024_j2_matches.csv` | 40/40 Japanese source names exact-resolved; official match-card IDs; date/ID order; 90-minute league results | Reusable lower-division history; J3-before-J2 history remains absent. J2 Elo experiments closed for present model selection. |
| TeamMaster | **49** stable teams, **103** alias rows | `data/master/teams.csv` (master, not raw fetch) | `team_0001`–`team_0033` preserved; J2 clubs `team_0034`–`team_0049`; source/date-aware exact resolution, no fuzzy fallback | Shared ID layer. Club name/alias coverage is source specific; a name match is not an identity proof. |
| J.League Cup, SFMS01 | 2015–2024 **597** retained J1-involved; 2025 **56**; 2026 **4** | `data/raw/jleague_cup/` cached listings + metadata; `data/processed/jleague_cup/*.csv` | SFMS01 search-table rows and same-row `match_card_id`; J1 side exact ID; lower-division opponent may be nullable; date/source ID order | Domestic Rest dates. Processed data does not establish safe 90-minute result for Cup Elo. 2026 is completed-to-cutoff, not the final season. |
| Emperor's Cup, JFA | 2015–2024 **291** retained; 2025 **41**; 2026 **19** J1-involved retained from **56** completed | 2015–25 JSON/cache + metadata under `data/raw/emperors_cup/`; `data/processed/emperors_cup/*.csv`; 2026 official HTML fallback has processed output but no corresponding persistent per-match HTML cache in that directory | J1 side exact-resolved; non-J1 opponent may be nullable; JFA match-page key; date/key order | Domestic Rest dates for resolved J1 side. 2026 processed 19 have 19 resolved J1 sides, 19 nullable opponents. Completion/status comes from HTML; full raw reconstruction should be documented before future reuse. |
| SFMS02 historical team match stats | 2015–2025 **3,588** rows, one per ordinary J1 match | `data/raw/jleague_match_stats/` **3,588** HTML + metadata; `data/processed/jleague_match_stats/{year}_match_stats.csv` | official J1 match ID + exact team IDs | Home/away Shots, Corner Kicks, Free Kicks. No confirmed historical match xG, possession, or shots on target here. These past experiment features are not frozen candidates. |

## B. Research-ready, with bounded use

| Source / processing | Seasons and observed coverage | Raw / processed | Identity and chronology | Status, usable features and limitation |
|---|---:|---|---|---|
| SFMS02 Starting XI | 2015–2024 **3,208** matches, **6,416** lineups, **70,576** starter appearances; 1,462 unique raw names in saved audit | Same SFMS02 raw cache; **no dedicated lineup CSV** | A5 starter section, 11 per lineup; `match_date, match_id` team stream; no official player ID/link | Short adjacent-lineup exact-name continuity is research-ready: 6,356/6,416 available (99.06%). Longitudinal player identity and current-match XI before publication are not established. No blank/duplicate/replacement anomaly in saved audit. |
| SFMS02 managers + official manager master | 2015–2024 **3,208** match rows = 6,416 manager side appearances; **6,058** resolved, **358** unresolved | Match HTML/master cache; `data/processed/jleague_match_managers/{2015_2024_match_managers,2015_2024_match_managers_resolved}.csv`; master `data/processed/jleague_manager_master/managers.csv` (**462** rows) | Stable staff ID when safe; date/team order; nine unresolved raw names | Manager history is reusable for identity audits and bounded feature research, but 94.42% ID resolution is not complete. Unresolved identities are not fuzzy-merged. |
| Domestic Competitive Rest | 2015–2024 J1 **3,208** targets in rolling experiment; 2025/2026 inputs now materialized | Derived by `src/features/domestic_competitive_rest.py`; **no standalone feature CSV** | Team IDs and strictly prior domestic event date; nullable non-J1 Cup opponents | Frozen Model B feature group. AFC excluded, so AFC-club total competitive rest can be shorter. Historical feature module is scoped to 2015–2024; interim evaluator has a separate path with outstanding target-history audit. |
| 2026 interim lockbox output | **70** saved prediction rows | `data/processed/modeling/2026_27_interim_lockbox_predictions.csv` | Target IDs unique; class order 0/1/2 | Existing report records A/B scores. Do not treat this as a fresh validation set or new feature-selection input; see chronology concerns in [PROJECT_STATUS_2026_09_20.md](PROJECT_STATUS_2026_09_20.md). |

## C. Deferred sources and processing

| Source | Verified coverage/data path | Raw / processed | Identity, chronology and status |
|---|---|---|---|
| J.LEAGUE.jp detailed 2024 match stats | Static/RSC audit: 357/380 pages linked by the follow-up path; Shots on Target, Possession and Fouls final values **0/380 confirmed**; Offsides final status unproven | Audit docs only; no trusted processed final-value CSV | Earlier sample-based “380/380 A” claim was superseded by full audit. Numeric `0/0%` is a placeholder candidate, not a valid observed final match value. Browser runtime endpoint not identified; current verdict C. |
| FootyStats match xG/xGA | Season pages and some current match-level display exist; 2015/2019/2024 historical full-match xG coverage **unverified** | Research docs; no approved historical processed CSV | Premium CSV/API access and historical definition/ID mapping unconfirmed; verdict B/deferred. Do not use season aggregate as match xG. |
| SofaScore player ratings/minutes | 2015/2019/2024 match pages and lineup routes exist, but starting-XI player ID/rating/minutes were not recovered from a supported structured path | Research docs only | Official public API path not established; historical coverage and license unresolved; verdict C/deferred. |
| AFC club matches | Limited official year-by-year delivery matrix, with legacy reports and modern PDF/article sources | No 2015–2024 full processed AFC dataset | Mixed identity conventions and uncertain full-year coverage. No AFC input in Domestic Rest. A light schedule-only Japanese-club path remains a research idea. |
| Cup J1–J2 Elo bridge | **145** identity-safe candidates in audit (68 League Cup + 77 Emperor's Cup) | Existing retained Cup CSVs | Existing processed inputs did not safely establish 90-minute result for use in Elo; **zero used** in the bridge experiment. This is unavailable data, not a performance rejection. |
| Stable player master | XI names/shirt numbers present, stable official player ID absent | No player-master artifact | Exact raw-name overlap is only short-term diagnostic; same name across teams/years cannot establish one person. |

## D. Failed / superseded routes

| Route | Outcome | Replacement / remaining constraint |
|---|---|---|
| 2026 Emperor's Cup legacy `schedule.json` assumption | Returned 2020 schedule data, unsuitable for 2026 | Official `schedule_result`/match-page HTML fallback yielded 56 completed and 19 retained J1 matches. |
| First 2026/27 lockbox run | 2026 Cup/Emperor inputs absent; Brier was averaged over matches **and classes** | Invalidated. Materialized 4+19 Cup rows and corrected Brier to `mean(sum(..., axis=1))`; later saved report records a rerun, subject to chronology audit. |
| 270-match lockbox assumption | Mixed Hyakunen 200 with ordinary 2026/27 J1 70 | Withdrawn; ordinary J1 completed 70 is the interim evaluation target. |

## Reusable processing methods and their boundaries

| Working processing | Reuse boundary / limitation |
|---|---|
| J1 format-aware parsing: 2015/2016 two stages, later full season, 2021 20-club year | Never infer all years have 306 matches; match date is the chronology key. |
| Exact TeamMaster resolution, stable source IDs, CSV validation | Source aliases and validity periods must match; unresolved opponents can be nullable only where a resolved J1 side is sufficient. |
| Cached HTML/JSON with URL/size/SHA-256 metadata | Existing J.League/JFA caches are source specific; 2026 Emperor HTML fallback lacks equivalent persistent raw archive. |
| SFMS01 J2/Cup parsers and JFA Cup parser | Search result table or documented schedule rows only; exclude form/dropdown content and future matches. |
| SFMS02 A5 XI / A10 manager extraction | XI has no official player ID; manager master leaves 358 appearances unresolved. |
| Prior-date Domestic Rest and 90-minute Hyakunen Elo update | Current target and simultaneous results may enter state only after they become available. The interim evaluator needs the separate chronology audit recorded above. |
| Lockbox input preflight and Brier correction | Current preflight hard-fails 2026 counts but does not enforce the observed 2025 counts; Brier uniform invariant is 2/3. |

The strongest next source candidates and point-in-time rules are in [NEXT_DATA_RESEARCH_ROADMAP.md](NEXT_DATA_RESEARCH_ROADMAP.md).
