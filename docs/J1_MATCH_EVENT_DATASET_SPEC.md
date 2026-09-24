# J1 historical match event dataset specification

Status: schema/parser contract frozen; fixture gate passed and production
result **MATERIALIZED_AND_VALIDATED**.

## Scope

- Competition: ordinary J1 only
- Seasons: 2015–2024
- Expected source matches: 3,208
- Source: existing cached SFMS02 HTML only
- Excluded: Cup, J2, J3, AFC, 2025, 2026/27, and 2026 Hyakunen

One normalized row represents one event. Raw source rows are not copied as
events: an A7 OUT/IN pair becomes one `SUBSTITUTION` row.

## Frozen columns

`event_id`, `match_id`, `match_date`, `season`, `team_id`, `team_name`,
`side`, `event_type`, `player_name_raw`, `related_player_name_raw`,
`minute_raw`, `minute_normalized`, `minute_order_half`,
`minute_order_base`, `minute_order_added`, `normalization_flags`,
`source_section`, `source`, `source_url`, `raw_sha256`.

Optional columns may be added only when directly evidenced by the source:
`event_subtype`, `source_row_index`, and `null_reason`.

`player_id` is deliberately not populated: SFMS02 has no verified stable
official player identifier. Name-derived IDs, fuzzy matching, normalized-name
joins, manual merges, and cross-season identity stitching are prohibited.

## Event types and source sections

| event type | SFMS02 section |
|---|---|
| `GOAL` | A2 |
| `SUBSTITUTION` | A7 |
| `YELLOW_CARD` | A8 |
| `RED_CARD` | A9 |

Team identity must resolve through the existing TeamMaster and official
match identity must resolve through the existing match dataset. The parser
does not reconstruct the final score from events. A1 score comparison is a
diagnostic only.

## Event rules

### Goals

Preserve scorer raw name, side, and raw minute. `event_subtype` is populated
only when the source explicitly identifies own goal, penalty goal, or another
subtype; otherwise it is `UNKNOWN`/null. Never infer `NORMAL_GOAL` merely
because no subtype is shown.

The observed A2 DOM mirrors its cells: home rows are `[player, minute]` and
away rows are `[minute, player]`. Both are parsed from their explicit side
containers; position or score-based team inference is prohibited.

### Substitutions

Reuse `sfms02_player_minutes.py` semantics:

- adjacent OUT and IN rows are required;
- OUT marker is `▽` and IN marker is `▲` (including the existing source
  encoding representation);
- IN minute is empty and OUT minute is present;
- the OUT player is `player_name_raw`, the IN player is
  `related_player_name_raw`;
- unpaired or malformed pairs are hard failures.

### Cards

A8 is `YELLOW_CARD`; A9 is `RED_CARD`. Second-yellow/direct-red subtype is
stored only when explicitly visible. A yellow row alone never becomes a red
event. A9 rows remain events even when the player-state analysis says the
player had already been substituted or was an unused substitute.

Section absence and zero-event are distinct: a present section with no rows is
normal no-event; an expected boundary that is malformed is a hard failure.

## Minute contract

Always preserve `minute_raw`. Accepted representations include integer
minutes, `45+N'`, `90+N'`, and the observed `46'` boundary. Added time keeps
its order component. `46'` receives `MINUTE_46_BOUNDARY_AMBIGUOUS` where the
existing minute policy requires it. Unsupported tokens are hard failures or
explicit unresolved values; silent coercion is prohibited.

The full cache contains 18 A8 rows whose official token is `***`. For this
observed variant only, `minute_raw` is retained, normalized minute/order fields
are null, and `null_reason=SOURCE_MINUTE_UNRESOLVED`. No numeric minute is
inferred. Any other unsupported token remains a hard failure.

Event ordering is `(minute_order_half, minute_order_base,
minute_order_added, source row order)`. This is deterministic source order,
not a claim of physical elapsed time.

## event_id and provenance

`event_id` is a deterministic SHA-256 digest of match ID, side, source
section, source row index, and event type. It is unique within a match and is
not a random UUID. Player name and minute alone are never the identity.

Every row retains `source`, `source_url`, and `raw_sha256`; raw input is
`data/raw/jleague_match_stats/{match_id}.html` with its existing metadata.

## Chronology and score diagnostics

Events are post-match observations. A future feature may use only events from
matches completed before the target kickoff. Same-date matches must be batched
conservatively when kickoff order is unavailable. Target-match events and
future events are prohibited.

For goals, A1 final score is a validation diagnostic only. Incomplete or
ambiguous goal semantics yield `NOT_CHECKABLE`; the parser never silently
repairs a score mismatch.

## Acceptance gate

The fixture gate now covers single and multiple goals, stoppage time,
substitution pairs and multiple substitutions, yellow/red cards, 46-minute
ambiguity, blank/replacement names, malformed/unpaired rows, same-minute
substitution/red ambiguity, deterministic IDs, section absence/zero-event
semantics, and no network dependency. The parser contract is therefore
**READY_FOR_FULL_EVENT_MATERIALIZATION**. This task still produces no
3,208-match CSV by itself; materialization is a separate explicitly authorized
task and is documented in `docs/J1_MATCH_EVENT_DATASET.md`.
