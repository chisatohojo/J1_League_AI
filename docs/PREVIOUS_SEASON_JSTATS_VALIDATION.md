# Previous-season J Stats feature read-only validation

## Scope

2026-09-23時点のlocal repositoryだけを使ったread-only validation。外部web、collector、feature dataset、model fitting/evaluation、predictionは実行していない。

## Explicit season mapping

| Target | Profile |
|---|---:|
| 2020 ordinary J1 | 2019 J1 final |
| 2021 ordinary J1 | 2020 J1 final |
| 2022 ordinary J1 | 2021 J1 final |
| 2023 ordinary J1 | 2022 J1 final |
| 2024 ordinary J1 | 2023 J1 final |
| 2025 ordinary J1 | 2024 J1 final |
| 2026/27 ordinary J1 | 2025 J1 final |

2026 J1百年構想リーグは通常J1と別competitionであり、このfeature familyのtarget外。既存project方針に従い、2025 J1 profileを流用しない。

## Local J1 denominator validation

既存 `data/processed/jleague/{season}_matches_probe.csv` を読み、home/awayのexact source namesを既存TeamMasterの `source=jleague_data_site` aliasesへexact照合した。全対象seasonでunresolvedは0だった。

| Profile season | Matches | Clubs | Appearances per club | Match IDs missing | Duplicate match IDs | TeamMaster unresolved |
|---:|---:|---:|---:|---:|---:|---:|
| 2018 | 306 | 18 | 34 | 0 | 0 | 0 |
| 2019 | 306 | 18 | 34 | 0 | 0 | 0 |
| 2020 | 306 | 18 | 34 | 0 | 0 | 0 |
| 2021 | 380 | 20 | 38 | 0 | 0 | 0 |
| 2022 | 306 | 18 | 34 | 0 | 0 | 0 |
| 2023 | 306 | 18 | 34 | 0 | 0 | 0 |
| 2024 | 380 | 20 | 38 | 0 | 0 | 0 |
| 2025 | 380 | 20 | 38 | 0 | 0 | 0 |

34/38は決め打ちせず、各seasonの実データから得た。全seasonのscore/resultやfeature生成は行っていない。

## Candidate stat coverage

既存 `J_STATS_HISTORICAL_DATA_INVENTORY.md` のlocal documentationをcoverage source of truthとして確認した。

| Candidate | Documented source seasons | Local processed profile artifact | Numeric/finite/non-negative check |
|---|---:|---|---|
| `expected_goals` | 2019–2025 | historical files absent | 2026 snapshot 20/20 |
| `shoot_on_target` | 2018–2025 | historical files absent | 2026 snapshot 20/20 |
| `expected_goals_against` | 2019–2025 | historical files absent | 2026 snapshot 20/20 |
| `suffer_shoot_on_target` | 2018–2025 | historical files absent | 2026 snapshot 20/20 |
| `ball_rate` | 2018–2025 | historical files absent | 2026 snapshot 20/20 |
| `pass_rate` | 2018–2025 | historical files absent | 2026 snapshot 20/20 |

Current local snapshot `20260922T120000000000Z` has 20 clubs and numeric finite non-negative values for all six candidate stat names. This is a schema/value sanity check only; it does not validate historical season coverage. No historical 2018–2025 processed J Stats profile CSV exists under `data/processed/jstats_team_snapshots/`, so historical source rows cannot be independently rechecked from local artifacts in this turn.

## Profile normalization readiness

The J1 denominator is ready for a future per-match conversion: every audited profile season has complete match coverage, exact team identity, and a constant appearance count within that season. The actual historical stat values and official semantics still need to be materialized/validated before implementation.

For the six candidates:

- xG/xGA require a validated cumulative-total interpretation and division by the reconstructed J1 appearance denominator.
- SOT and suffered SOT require the same denominator gate before per-match conversion.
- `ball_rate` and `pass_rate` remain official rate values; they must not be converted back to totals.
- non-finite, negative, missing, duplicate, or unresolved rows must hard-fail the future profile build.

## Promoted-team cases

For each ordinary-J1 target, a club absent from the immediately preceding mapped J1 profile is a promoted/no-profile case. It must be represented as:

```text
profile_value = null
has_previous_j1_profile = false
```

No league-average or zero fallback was applied during this validation. The local ordinary-J1 history contains the exact team memberships needed to derive this comparison, but no feature rows were generated.

## Validation result

- Season mapping: validated as explicit ordinary-J1 mapping; arithmetic fallback removed from the spec.
- Candidate source coverage: documented coverage is 2018–2025 for non-xG candidates and 2019–2025 for xG/xGA.
- TeamMaster unresolved: 0 across 2018–2025 J1 denominator datasets.
- Denominator: validated from local match datasets; 34 or 38 per club depending on actual season.
- Candidate local historical profile rows: not available; historical artifact materialization remains required.
- Promoted-team handling: null plus `has_previous_j1_profile=false`; no imputation.
- Implementation readiness: **no**. The join/denominator contract is ready, but historical 2018–2025 profile artifacts and their per-stat validation are not present locally.

## Materialization preflight outcome

The targeted 2019 `expected_goals` identity audit is recorded in [J_STATS_2019_XG_IDENTITY_AUDIT.md](J_STATS_2019_XG_IDENTITY_AUDIT.md). The response contained 18 lossless official club names and all 18 mapped exactly and uniquely to existing `jleague_official` TeamMaster aliases. Fifteen rows also had `href`/`club.code`; three had those fields empty, but no guessed slug or ID is needed because the exact official name-to-TeamMaster mapping is safe.

The earlier apparent replacement characters were terminal-output mojibake, not raw response bytes or parser output. This removes the identity blocker for this page. Full historical materialization was still not run in this audit; every page must pass the same strict validation before publication.

The subsequent materializer preflight initially used the wrong namespace for the denominator input and attempted `jleague_official` resolution against J1 match-probe names. That was corrected to `source=jleague_data_site`; the profile pages continue to use `source=jleague_official`. The namespaces are joined only by stable `team_id`. No re-decoding, name repair, normalization, alias guess, or denominator substitution was applied.

After the namespace correction, historical materialization completed successfully. The COMPLETE artifact and its raw retrieval manifest are documented in `PREVIOUS_SEASON_JSTATS_PROFILE_ARTIFACT.md`.

The artifact was subsequently rebuilt from the same 46 raw HTML files after an identity-schema cleanup, with zero network requests. `official_club_id` is null unless an actual numeric/internal ID exists; source `club.code` and `href` are retained in separate fields. The stable join key remains `team_id`.

## Out of scope

No external web access, collector implementation, feature generation, model fitting/evaluation, prediction, parameter tuning, or commit/push was performed.
