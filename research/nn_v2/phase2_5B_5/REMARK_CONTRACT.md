# Exact reviewed staff-warning adapter v2

Version: `reviewed_staff_warning_exact_witness_v2`. This offline adapter has no acquisition entrypoint. It composes the unchanged SHA-pinned strict parser and unchanged legacy remark classifier with one separately reviewed witness rule. Existing run records are immutable.

Before parsing, verify original raw, metadata and request SHA; URL equality; HTTP200/full body; request-to-response SHA binding; byte count; UTC request/completion ordering and the original completion timestamp. Any difference is HOLD.

Always invoke the original strict parser with the original row, TeamMaster and full expected header. A strict HOLD or any timing note remains HOLD. EMPTY and KNOWN_NON_TIMING_NOTE keep their legacy classifications. Other categories can use the reviewed rule only if every check below passes:

1. Canonical review-rule SHA and the approved version/decision/namespace match.
2. Every fixture-scope field matches: identity, official ID, URL, competition series, date/kickoff, both TeamMaster IDs, both90-minute scores, PK/extra-time flags.
3. Expected and parsed competition/season/round headers match the reviewed rule exactly; identity, date, kickoff and the complete strict parsed-result object match.
4. Raw/metadata/request hashes match the reviewed witness. The entire remarks list has exactly the reviewed one item; timing notes are empty.
5. Exactly one A11 block has the reviewed inclusive byte-range and SHA. Its remarks heading, whole paragraph HTML and verbatim unescaped text match exactly. No extra paragraph can be ignored.
6. Positive disciplinary syntax is reassembled from separately reviewed minute, warning expression/code, club, named staff and explicit interpreter role fields. The result must equal the entire verbatim paragraph.

This permits the one reviewed annotation. It does not grant a generic interpreter-role regex to other fixtures or warning texts. Coach and interpreter remain distinct paths; unregistered roles and unknown forms HOLD. Existing Unicode-normalized extraction is also checked, but never substitutes for exact original bytes. A same-normalized-text whitespace change, prefix/suffix, new paragraph, changed metadata or different fixture cannot fall back to acceptance.

The single paragraph explicitly identifies a staff warning in an official remarks block. This positive context supports its non-timing classification. Absence of timing keywords is an additional check, not the classification basis. No detailed regulatory meaning of the warning code is inferred without additional evidence. The classification does not prove no physical interruption ever occurred or establish an original schedule, completion boundary, or match-day source availability.

Return a new result containing the unchanged strict analysis, prior category, new category and applied-rule reference. Never modify raw/metadata, the strict parser, old classifier, publication, historical result admission, trained artifacts or the stopped run's26 PASS/1 HOLD/249 unacquired record.

The separate future-plan validator requires exactly249 unique unacquired URLs, no overlap with the39 acquired URLs, and21 batches of20x12+9. It only accepts `network_enabled=false`, `permit_created=false`, `execution_authorized=false`. New evidence retrieval requires an independent authorization and a newly bounded executor/permit. This phase creates neither.
