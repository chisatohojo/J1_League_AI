# AFC 2024 Fixture Prototype Audit

- Scope: AFC official club competitions, calendar year 2024 only.
- Sources: AFC-hosted schedule PDFs and AFC archive/article evidence only.
- Final decision: `BLOCKED_AFC_DATE_PROVENANCE`

## Coverage

- Fixture rows: 34
- Resolved J1 clubs: 4 (team_0006, team_0010, team_0011, team_0033)
- Unique derived keys: 34
- Same-club/same-day collisions: 0 (validated)
- Unresolved/ambiguous fixtures: 34
- TeamMaster resolution: exact explicit crosswalk; no fuzzy matching.
- Provenance: raw SHA-256 recorded per AFC PDF; source IDs remain null for derived keys.
- Date policy: schedule dates are not asserted as played dates until AFC result/archive evidence is linked.

## Identity audit

All rows use `identity_type=derived_fixture_key`; no AFC stable match ID was invented.
The prototype is offline-replayable from the embedded manifest and cached AFC raw PDFs.
