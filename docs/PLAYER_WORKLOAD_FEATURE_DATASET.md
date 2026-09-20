# J1 local player workload feature dataset (2015–2024)

Built offline from `data/processed/sfms02_player_minutes/2015_2024_j1_player_minutes.csv` (115,468 player-match squad rows), joined strictly by `match_id` to the 2015–2024 J1 probes and match-stats team IDs. Output: `data/processed/features/2015_2024_j1_player_workload_features.csv` (3,208 rows, one per ordinary J1 match, 47 columns). Builder: `python -m src.features.player_workload`. It validates all inputs and refuses to overwrite an existing output. **No web requests, model evaluation, or prediction were performed.** This is a production *feature dataset*, not a claim of validated predictive value.

## Definition, identity, and available information

The exact raw-name key is `(season, team_id, player_name_raw)`. There is no normalization, fuzzy matching, official-ID inference, cross-team link, or cross-season link. A player moving teams or entering a new season starts a new local history. Namesakes within one team-season cannot be ruled out without an official ID; a display-name change may split one real player. See `LOCAL_PLAYER_IDENTITY_WORKLOAD_FEASIBILITY.md` and `JLEAGUE_PLAYER_IDENTITY_FEASIBILITY.md` for the underlying identity audits.

`minutes_played_normalized` is the existing SFMS02 interval reconstructed on a **0–90 regulation clock**, not actual elapsed time or an official player-minute field. The 45'/90' capping and 46' uncertainty in `SFMS02_PLAYER_MINUTES_DATASET.md` carry through unchanged. The features measure **local J1 normalized workload only**. Zero in a window means no normalized minutes observed for that *local key in ordinary J1* during the window; it never asserts zero total football workload. Other domestic/continental matches, J2, training, and injury information are not present. An unused substitute has zero minutes and does not count toward `with_Nd_history`; a played substitute with zero normalized minutes under the cap does count as a played appearance.

For each target match and team, the **immediately previous J1 match for that team** supplies the reference Starting XI (11 exact names) and full listed matchday squad (starters plus substitutes). These are known historical populations, **not the target match's Starting XI** or a predicted next lineup. If there is no previous J1 match, sums and means are null, `has_previous_j1_match=0`, and counts/sizes are zero; the target row remains in the output. If a previous J1 match exists but a reference player's local key has no prior appearance in a window, their contribution is zero local-J1 normalized minutes. The reference may come from the previous season, but its names are looked up under the *target season* key, so minutes never cross the season boundary. `prev_reference_from_prior_season` exposes this special case.

Windows are inclusive calendar-day differences **1–7, 1–14, and 1–30** before `match_date`. A member's window workload is the sum of their earlier J1 `minutes_played_normalized`. The corresponding `with_Nd_history` count measures reference players with at least one prior *played* match in that window, including zero-normalized-minute played substitutes, not bench-only listings. Starter and squad sums/means aggregate all members of the respective reference population; missing individual window history contributes zero. Means divide by 11 starters or the actual previous squad size, not by the number with history.

Chronology is `(match_date, match_id)`, with `match_id` treated as a string. All matches on one date are evaluated against the state at the **start of that date**; only after every feature row for that date is recorded are its player minutes and squads added. Thus target minutes, future minutes, target XI, and same-date other-match minutes cannot enter a pre-match value. The input has zero instances of one team playing multiple J1 matches on one date; such a case would fail validation instead of relying on uncertain ordering.

## Schema

`match_id`, `match_date`, `season`, then the same side-prefixed columns for `home_` and `away_`:

- `has_previous_j1_match` (0/1), `prev_reference_from_prior_season` (0/1), `prev_starters_count` (0 or 11), `prev_squad_size` (0 or actual prior squad size).
- For each `N` in 7, 14, 30: `prev_starters_with_Nd_history`, `prev_starters_sum_minutes_Nd`, `prev_starters_mean_minutes_Nd`; analogous `prev_squad_with_Nd_history`, `prev_squad_sum_minutes_Nd`, `prev_squad_mean_minutes_Nd`.

This produces 3 identity/date columns plus 22 columns per side = **47 columns**. No `high_load_count` feature was generated: the existing documents do **not** pre-specify a high-load threshold, and selecting one here would be tuning. No model-ready missing-value imputation was chosen. Output CSV nulls are confined to aggregate sums/means where no previous J1 squad exists.

## Coverage audit

All 3,208 target rows are retained. Of 6,416 team-target sides, **6,386** have a previous J1 match and **30** do not (home 3,194/14; away 3,192/16). At match level, 3,187 have both previous squads, 12 have one, and 9 have neither: **3,199** have at least one previous squad. Previous XI size is 11 on every available side. Across available reference populations there are 70,246 starter-member slots and 114,928 squad-member slots. A slot is counted as having history when its exact local key has a prior *played* J1 appearance in the window.

| Season | Target matches | Sides with previous J1 | Starter slots with 7d / 14d / 30d history | Squad slots with 7d / 14d / 30d history |
| --- | ---: | ---: | --- | --- |
| 2015 | 306 | 594 | 4,136 / 6,281 / 6,534 of 6,534 | 5,217 / 8,222 / 9,201 of 10,691 |
| 2016 | 306 | 609 | 4,675 / 6,292 / 6,534 of 6,699 | 5,895 / 8,391 / 9,287 of 10,961 |
| 2017 | 306 | 610 | 3,861 / 6,028 / 6,534 of 6,710 | 4,864 / 7,938 / 9,218 of 10,980 |
| 2018 | 306 | 611 | 4,499 / 6,171 / 6,336 of 6,721 | 5,776 / 8,313 / 9,022 of 10,996 |
| 2019 | 306 | 611 | 3,465 / 6,248 / 6,534 of 6,721 | 4,372 / 8,146 / 9,163 of 10,994 |
| 2020 | 306 | 611 | 5,841 / 6,270 / 6,314 of 6,721 | 8,276 / 9,284 / 9,604 of 10,994 |
| 2021 | 380 | 759 | 5,907 / 7,557 / 8,085 of 8,349 | 8,378 / 10,973 / 12,114 of 13,658 |
| 2022 | 306 | 611 | 4,631 / 5,896 / 6,534 of 6,721 | 6,570 / 8,566 / 9,777 of 10,994 |
| 2023 | 306 | 612 | 3,575 / 5,995 / 6,534 of 6,732 | 5,034 / 8,641 / 9,752 of 11,014 |
| 2024 | 380 | 758 | 5,368 / 7,392 / 8,140 of 8,338 | 7,583 / 10,770 / 12,244 of 13,646 |
| **Total** | **3,208** | **6,386** | **45,958 (65.4%) / 64,130 (91.3%) / 68,079 (96.9%) of 70,246** | **61,965 (53.9%) / 89,244 (77.7%) / 99,382 (86.5%) of 114,928** |

These are **member-slot history-presence rates**, not percentages of matches with usable features or evidence of player identity accuracy. All sides with a previous squad have numeric aggregate features, including legitimate local-J1 zero windows. The shorter-window rates vary with fixture spacing. At match-side level, at least one reference starter has played history for 4,178 / 5,830 / 6,189 of 6,416 target sides in the 7/14/30-day windows; reference-squad presence gives the same counts because every previous-match starter played.

### Aggregate distributions

Each distribution pools the available home and away team-target sides (6,386 values). Entries are `min / median / mean / max` normalized minutes; mean-per-player columns have the same unit per reference member.

| Feature family | 7d | 14d | 30d |
| --- | --- | --- | --- |
| Previous starters, sum | 0 / 897 / 642.124 / 1,919 | 0 / 1,539 / 1,380.119 / 3,595 | 0 / 2,632.5 / 2,680.622 / 6,115 |
| Previous starters, mean | 0 / 81.545 / 58.375 / 174.455 | 0 / 139.909 / 125.465 / 326.818 | 0 / 239.318 / 243.693 / 555.909 |
| Previous squad, sum | 0 / 990 / 702.689 / 1,980 | 0 / 1,808 / 1,551.091 / 3,960 | 0 / 2,935 / 3,111.732 / 7,182 |
| Previous squad, mean | 0 / 55 / 39.046 / 111.176 | 0 / 100.472 / 86.188 / 220 | 0 / 163.056 / 172.905 / 399 |

The cumulative window sum may exceed 90 minutes per player because it spans multiple prior matches. For 7d, max starter mean exceeds 90 for the same reason. The audit found no negative aggregate, no previous side with a non-11 starter count or fewer than 11 listed squad members, no aggregate populated for a side without previous J1, no duplicate match IDs, and no dropped match rows. **Anomaly count for the checked invariants: 0.**

## Reset limitations and future identity integration

The previous-match reference is from an earlier season on **154 team-target sides** (78 home, 76 away); `prev_reference_from_prior_season=1` marks these. Their current-season player history is empty until new-season J1 play occurs. The separate feasibility audit observed 142 same-name/multi-team season keys and 140 candidate new team-local keys with earlier other-team same-name records. They are **not certified transfers** and are never merged here; any genuine transfer loses its pre-transfer local history. This dataset has no official player ID and cannot resolve namesakes, renames, or individual non-J1 workload. Future official-ID integration would require a separately verified source-to-SFMS02 mapping and an independent leakage audit. It must not retroactively reinterpret the current exact-name keys as official player identities.

No feature selection, threshold search, training, predictions, 2025/2026 evaluation, or Champion/Challenger change was performed.
