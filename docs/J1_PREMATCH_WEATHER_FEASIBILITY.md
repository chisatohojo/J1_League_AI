# J1 Pre-match Weather Forecast Feasibility Audit

## Verdict

`DEFER_WEATHER_VENUE_IDENTITY`

The first root blocker is the already-established absence of a stable,
point-in-time-safe venue/location contract.  A weather forecast cannot be
safely attached to a target match until its venue/location was itself known
before kickoff and can be resolved to the weather source's geographic unit
without inference.  The weather-forecast archive is an independent secondary
blocker: the bounded official-source check did not establish a public archive
that can replay the issued-before-kickoff forecast for 2015, 2019, or 2024.

This is a source audit only.  No collector, feature data, model fit,
prediction, metric, feature selection, or use of realized target weather was
performed.

## Scope and read-only repository audit

- Scope: ordinary J1, 2015–2024, exactly 3,208 local completed matches.
- Inspected: `docs/NEXT_DATA_RESEARCH_ROADMAP.md`,
  `docs/H2H_STADIUM_FEASIBILITY.md`, `src/collect/jleague.py`,
  `src/collect/matches.py`, `src/collect/jleague_ongoing*.py`, stadium-related
  feature modules, TeamMaster, and the ordinary-J1 processed dataset.
- No local raw or processed file was altered and no existing venue/stadium
  feature code was treated as proof of venue identity or publication timing.

| Local audit item | Finding |
|---|---|
| Match identity | 3,208 unique official `match_id` values |
| Date / kickoff field | `match_date` plus nonblank `kickoff_time` (`HH:MM`) for 3,208 / 3,208 |
| Time-zone offset in match schema | absent |
| Stadium field | nonblank exact raw string for 3,208 / 3,208; 51 tokens |
| Latitude/longitude in match schema | absent |
| Venue/stadium master or stable venue ID | absent |
| TeamMaster coverage | club-only exact aliases and permanent team IDs; no venue/location entries |
| Historical schedule revision/as-of history | absent for 2015–2024; cached SFMS01 final listings were retrieved after the matches |
| Ongoing schedule revision history | exists for current 2026/27 listings, but does not retrofit historical venue provenance |

`src/collect/jleague.py` parses the ninth SFMS01 table cell as `stadium` and
preserves the string.  It deliberately does not normalize stadium names.
`validate_matches()` only requires a nonblank string.  The historical stadium
audit already found no venue link/master, neutral-site flag, home/away venue
designation, or stable venue ID, and recorded:

```text
STADIUM_PREMATCH_PROVENANCE_UNPROVEN
```

It also records that the annual 2015–2024 listings are retrospective caches
retrieved in 2026, not pre-kickoff schedule snapshots.  Exact raw-token
persistence is not proof that two tokens are the same physical facility, and
current venue data must not be projected backwards.  Therefore none of the
following is permitted in this lane: stadium-name-to-address lookup, fuzzy
venue matching, club-home-location substitution, or treating a neutral or
alternate venue as the home club's location.

## Official weather-source feasibility

The external check was limited to the following official Japan Meteorological
Agency (JMA) materials, viewed on 2026-09-28 JST.  No third-party weather site,
undocumented endpoint, URL guessing, or broad historical crawl was used.

1. [JMA regional time-series forecast catalogue](https://www.data.jma.go.jp/suishin/cgi-bin/catalogue/make_product_page.cgi?id=Jikeiret)
   documents a current forecast product for first-level forecast areas.  Its
   documented fields are issuance time, issuing office, 3-hour valid times,
   weather, temperature, and wind direction/speed; it is issued three times a
   day.
2. [JMA prefectural forecast / regional time-series specification No.11301](https://www.data.jma.go.jp/suishin/shiyou/pdf/no11301)
   documents weather, wind, temperature, and precipitation probability, the
   publication schedule (05:00, 11:00, 17:00), and corrections when conditions
   change.  This is a format/product specification, not a historical issued
   forecast archive.
3. [JMA historical weather-data search](https://www.data.jma.go.jp/stats/etrn/index.php/select/data/kaisetu/upper/view/data/data/kaisetu/index.html)
   exposes 2015, 2019, 2024, and current years but identifies the material as
   historical observations.  It provides station data such as precipitation,
   temperature, wind, and weather; it does not establish an issued forecast,
   forecast valid time, or original forecast revision for a match.

| Representative period | Official source state established by the bounded check | PIT forecast replay result |
|---|---|---|
| 2015 | historical observations selectable; no issued forecast artifact located | not established |
| 2019 | historical observations selectable; no issued forecast artifact located | not established |
| 2024 | historical observations selectable; no issued forecast artifact located | not established |
| current 2026/27 | current regional forecast product has issuance/valid-time semantics | only prospective capture could preserve an as-of artifact; retrospective replay not established |

JMA explicitly notes that historical observation data can be corrected
retroactively.  Those data are realized observations, so they are excluded
from a pre-match forecast feature regardless of their detail or geographic
coverage.  The current forecast specification allows corrections, but the
bounded inspection found no public, historical, versioned issuance archive
from which an earlier forecast and its supersession history can be replayed.
This is a finding about the reviewed public routes, not a claim that no such
record exists anywhere.

## Forecast fields versus usable evidence

The current official forecast product is source-level capable of carrying
several requested fields, but no historical target match is approved merely
because the product has them.

| Item | Current JMA forecast specification | Historical issued-before-kickoff replay |
|---|---|---|
| `issued_at` | documented | not established for 2015–2024 |
| forecast valid period/time | documented | not established for 2015–2024 |
| geographic unit | first-level forecast area / representative point | cannot join safely without venue contract |
| weather condition | documented | not established |
| temperature | documented | not established |
| wind direction/speed | documented | not established |
| precipitation probability | documented in prefectural forecast | not established |
| revision behaviour | corrections documented | historical versions not established |

The JMA historical portal must not be repurposed as a forecast archive.  In
particular, observed rain, temperature, wind, or weather at a later-selected
station is not evidence of what was forecast before a match.

## Venue/location linkage gate

The JMA products use forecast areas and representative locations; the
historical-observation portal uses named stations and publishes station
location information.  The J1 source provides only an exact stadium display
token.  There is no approved mapping from that token to a JMA forecast area,
representative point, station, latitude/longitude, municipality, or address.

The linkage is therefore **not feasible under the current contract**.  A
location join would require exactly the prohibited operations above, and it
would conceal alternate, neutral, renamed, or relocated venues.  This venue
identity/provenance gate is the root blocker even if a suitable historical
forecast archive is later located.

## Candidate future contract (not implemented)

Only after both gates pass, a later feature specification could consider a
single frozen forecast artifact per target with fields such as forecast
precipitation probability, forecast temperature, forecast wind, and a
rain/no-rain state.  A future contract must require all of the following:

1. a stable venue/location key bound to the target fixture by an official
   pre-kickoff schedule artifact;
2. a documented deterministic venue-to-forecast-geography mapping, including
   neutral/alternate venue handling, without fuzzy/manual inference;
3. `issued_at < target kickoff` in explicit time zones, plus a forecast valid
   time/period covering the target kickoff;
4. raw source URL, retrieval timestamp, SHA-256, source geographic identifier,
   and revision/supersession policy retained with the artifact; and
5. fail-closed handling for no eligible issue, ambiguous location, changed
   schedule/venue, or missing target-period coverage.

Target realized weather, later revised observations, and any forecast issued
after kickoff remain prohibited.  For future matches, snapshots may be
captured prospectively, but they cannot repair 2015–2024 retrospective PIT
evidence.
