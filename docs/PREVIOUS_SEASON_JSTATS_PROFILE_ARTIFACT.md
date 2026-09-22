# Previous-season J Stats profile artifact

## Status

`COMPLETE`

The historical profile materializer completed after correcting the identity namespace used for the denominator input. J1 match probes resolve through `source=jleague_data_site`; official J Stats ranking names resolve through `source=jleague_official`; the two namespaces are joined only by stable `team_id`.

## Intended artifact

The published artifact is:

```text
data/raw/jstats_previous_season_profiles/<retrieval_id>/
data/processed/jstats_previous_season_profiles/2018_2025_j1_team_profiles.csv
```

Current retrieval: `20260923T010000000000Z`  
Rows: 864  
Requests: 46  
Cache reuse: 0  
Status: `COMPLETE`

The processed schema keeps `official_club_code` and `official_club_href` separately. `official_club_id` is null because no numeric/internal official ID was observed. Slug/code/href is never used as the stable join key; `team_id` is the only join key. All 864 rows used exact `source=jleague_official` name resolution. The retrieval manifest records: code present 612, code missing 252, href present 612, href missing 252, and name fallback due to missing code/href 252.

The intended stats are `expected_goals`, `shoot_on_target`, `expected_goals_against`, `suffer_shoot_on_target`, `ball_rate`, and `pass_rate`; xG/xGA begin in 2019 and the other four begin in 2018. Expected rows are derived from the local season club counts, not hard-coded output rows.

## Strict publication policy

Publication required every fetched season/stat page to have expected club coverage, non-empty lossless official club names, exact unique TeamMaster resolution, no duplicate team/stat keys, finite non-negative values, and validated J1 appearance denominators. All conditions passed. A partial CSV is never published. If a future fetch begins and fails, the raw pages and `INCOMPLETE` manifest will be retained.

## Provenance and limitations

The source is the documented official J.LEAGUE.jp season-final team ranking route. Retrieved values are historical final profiles and may reflect later restatement; they are not historical point-in-time snapshots. This artifact must only be used according to the explicit ordinary-J1 season mapping in `PREVIOUS_SEASON_JSTATS_FEATURE_SPEC.md`. The current artifact was rebuilt from the same raw HTML and hashes with zero network requests; only parser/schema identity semantics changed.

No feature dataset, model fitting, evaluation, or prediction has been run.
