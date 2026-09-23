# Previous-season J Stats feature read-only validation

## Scope

2026-09-23時点のlocal repositoryだけを使ったvalidation。historical profile artifactとordinary-J1 feature datasetは後続のlocal materializationで生成済み。外部web、model fitting/evaluation、predictionは実行していない。

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
| `expected_goals` | 2019–2025 | COMPLETE artifact | 2019–2025 expected club coverage |
| `shoot_on_target` | 2018–2025 | COMPLETE artifact | 2018–2025 expected club coverage |
| `expected_goals_against` | 2019–2025 | COMPLETE artifact | 2019–2025 expected club coverage |
| `suffer_shoot_on_target` | 2018–2025 | COMPLETE artifact | 2018–2025 expected club coverage |
| `ball_rate` | 2018–2025 | COMPLETE artifact | 2018–2025 expected club coverage |
| `pass_rate` | 2018–2025 | COMPLETE artifact | 2018–2025 expected club coverage |

The historical profile artifact is `2018_2025_j1_team_profiles.csv`, retrieval `20260923T010000000000Z`, with 864 rows and finite non-negative values. The separate 2026 snapshot remains only a schema/value sanity reference.

## Profile normalization readiness

The J1 denominator and the six candidate profile values are materialized in
the COMPLETE local artifact. Every audited profile season has complete match
coverage, exact team identity, and a constant appearance count within that
season. The feature dataset uses the validated derived values and official
rate values; model-stage implementation remains separate.

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

No league-average or zero fallback was applied. The local ordinary-J1 history
contains the exact team memberships needed to derive this comparison, and the
feature rows are materialized in the scoped output artifact.

## Validation result

- Season mapping: validated as explicit ordinary-J1 mapping; arithmetic fallback removed from the spec.
- Candidate source coverage: documented coverage is 2018–2025 for non-xG candidates and 2019–2025 for xG/xGA.
- TeamMaster unresolved: 0 across 2018–2025 J1 denominator datasets.
- Denominator: validated from local match datasets; 34 or 38 per club depending on actual season.
- Candidate local historical profile rows: materialized and COMPLETE, 864 rows.
- Promoted-team handling: null plus `has_previous_j1_profile=false`; no imputation.
- Profile artifact readiness: **complete**. Feature dataset generation is also complete for the scoped ordinary-J1 targets; model stage remains unstarted.

## Materialization preflight outcome

The targeted 2019 `expected_goals` identity audit is recorded in [J_STATS_2019_XG_IDENTITY_AUDIT.md](J_STATS_2019_XG_IDENTITY_AUDIT.md). The response contained 18 lossless official club names and all 18 mapped exactly and uniquely to existing `jleague_official` TeamMaster aliases. Fifteen rows also had `href`/`club.code`; three had those fields empty, but no guessed slug or ID is needed because the exact official name-to-TeamMaster mapping is safe.

The earlier apparent replacement characters were terminal-output mojibake, not raw response bytes or parser output. This removed the identity blocker for this page. At that historical checkpoint, full materialization had not yet run; the later COMPLETE artifact supersedes that checkpoint.

The subsequent materializer preflight initially used the wrong namespace for the denominator input and attempted `jleague_official` resolution against J1 match-probe names. That was corrected to `source=jleague_data_site`; the profile pages continue to use `source=jleague_official`. The namespaces are joined only by stable `team_id`. No re-decoding, name repair, normalization, alias guess, or denominator substitution was applied.

After the namespace correction, historical materialization completed successfully. The COMPLETE artifact and its raw retrieval manifest are documented in `PREVIOUS_SEASON_JSTATS_PROFILE_ARTIFACT.md`.

The artifact was subsequently rebuilt from the same 46 raw HTML files after an identity-schema cleanup, with zero network requests. `official_club_id` is null unless an actual numeric/internal ID exists; source `club.code` and `href` are retained in separate fields. The stable join key remains `team_id`.

The downstream feature dataset is also complete for the seven scoped ordinary-J1
target seasons: 2,438 rows, with explicit `match_id`/`fixture_key` identity
semantics documented in `PREVIOUS_SEASON_JSTATS_FEATURE_DATASET.md`. Model-stage
work remains unstarted.

## Out of scope

No external web access, collector implementation, model fitting/evaluation,
prediction, parameter tuning, or commit/push was performed. Feature dataset
materialization is complete; model-stage work remains out of scope.
