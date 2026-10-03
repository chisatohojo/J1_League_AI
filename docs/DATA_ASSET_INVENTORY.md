# J1 League AI data asset inventory

最終更新: **2026-10-02 (JST)**。

このinventoryは、localに何が存在し、何に使用でき、何に使用してはいけないかを示す。`data/raw/`、`data/processed/`、`models/`配下のgenerated materialはplaceholderを除きGit-ignoredである。Clean checkoutでは、これらを別途materializeまたは受領し、documented hashを検証する必要がある。`data/master/teams.csv`はGit-tracked。

## A. Raw / cached source data

| Family | Local path | Scope / observed quantity | Provenance status | 使用可能範囲 / 禁止事項 |
|---|---|---|---|---|
| J1 listings / ongoing snapshots | `data/raw/jleague/` | historical annual inputs、Hyakunen、2026/27 immutable snapshots/research evidence | cached official pages/metadata。ongoing revisionを保存 | Basic match identity/resultとrevision replay。過去snapshot evidenceを上書きしない |
| SFMS02 match pages | `data/raw/jleague_match_stats/` | 2015–2025 J1の3,588 pages。各metadataあり | URL/status/bytes/SHA validation | Documented parser下のteam stats、XI、manager、events/minutes。stable player identityを意味しない |
| J2 listings | `data/raw/jleague_j2/` | 2015–2024の10 cached listings + metadata | official SFMS01 | J2 match history。J3 prehistoryはない |
| J.League Cup | `data/raw/jleague_cup/` | historical/2025/2026 listing caches | official SFMS01 | Domestic Rest date。generic resultは自動的にregulation Elo resultにならない |
| Emperor's Cup | `data/raw/emperors_cup/` | historical JSON/cache + metadata | mixed JFA delivery。2026 fallback limitationあり | 各source contract内のRest / validated bridge evidence |
| Cup regulation evidence | `data/raw/cup_regulation_results/` | 87 detail HTML/metadata pairs。historical JFA scheduleも別途再利用 | immutable URL/SHA/retrieval metadata | Frozen 145-row regulation datasetの裏付け。Cup model laneはclosed |
| Match-level xG | `data/raw/jleague_match_xg/{2025,2026_hyakunen,2026_27}/` | raw evidenceに裏付けられた660 processed official observations | competition-aware manifests/metadata | Rolling-xG history。2015–2024へretrofitしない |
| J Stats team snapshots | `data/raw/jstats_team_snapshots/<snapshot_id>/` | documented physical retrieval 6件: COMPLETE 4、INCOMPLETE 2 | append-only manifests、page SHA、retrieval/source dates | Cumulative prospective stateのみ。match-level reconstruction禁止 |
| J Stats source probes | `data/raw/jstats_snapshot_probes/<probe_id>/` | one-page update-state observations | probe URL/time/hash/status保持 | Capture triggerのみ。FULL_37 logical stateではない |
| Suspension notices | `data/raw/jleague_suspensions/<snapshot_id>/` | first confirmed KICKOFF_V2 observationあり: 7 `PRE_KICKOFF_CONFIRMED` rows / 4 exact target matches | operator-supplied canonical URL、publication/retrieval timestamps、capture-time schedule/kickoff provenance、read-only registry | Prospective PIT evidenceのみ。absenceはunknown。Historical productionはC / unsafeで、completeness claim禁止 |
| Previous-season J Stats profiles | `data/raw/jstats_previous_season_profiles/<retrieval_id>/` | raw-backed season-final profile artifact source | retrieval-specific immutable cache | Prior-season descriptive profileのみ。historical in-season PITではない |
| Player snapshot research evidence | `data/raw/research/jstats_player_*` | bounded ranking/profile samples | research-only raw evidence | Identity auditのみ。production registry/player snapshotではない |

## B. Processed match / source datasets

| Dataset | Path | Coverage / rows | 現在の役割 | 使用禁止の解釈 |
|---|---|---:|---|---|
| Ordinary J1 | `data/processed/jleague/{2015..2025}_matches_probe.csv` | 3,588。core retrospective 2015–2024 = 3,208 | Result、identity、Elo/form history。Model A operational trainingは2025まで | 2025をfresh model-selection setとして使うこと |
| 2026 Hyakunen | `data/processed/jleague/2026_hyakunen/matches.csv` | 200 | Frozen contractで許可されたElo/Rest/xG history | ordinary-J1 Logistic target |
| 2026/27 ongoing | `data/processed/jleague/2026_27/` | schedule 380。latest documented publicationは80 completed / 300 scheduled | Immutable revision、live chronology、prospective scheduling | Frozen 70-ID interim lockboxの拡張・再選択 |
| J2 | `data/processed/jleague_j2/2015_2024_j2_matches.csv` | 4,538 | Reusable lower-division match history | Closed J2 Elo laneを再開する根拠 |
| J.League Cup | `data/processed/jleague_cup/*.csv` | 2015–2024 597 retained J1-involved、2025 56、2026 cutoff時4 | Domestic Rest / source identity | 未検証regulation-time Elo results |
| Emperor's Cup | `data/processed/emperors_cup/*.csv` | 2015–2024 291 retained、2025 41、2026 cutoff時J1-involved 19 | Domestic Rest / source research | Opponent identityがnullableな範囲でのcomplete historical identity |
| Cup bridge candidates | `data/processed/cup_regulation_results/2015_2024_j1_j2_bridge_candidates.csv` | 145 | Frozen identity-safe manifest | 結果確認後のcandidate再選択 |
| Cup regulation results | `data/processed/cup_regulation_results/2015_2024_j1_j2_bridge_regulation.csv` | 145 | Provenance-complete reusable data | Closed Cup bridge model laneの再開 |
| SFMS02 team match stats | `data/processed/jleague_match_stats/{year}_match_stats.csv` | 2015–2025の3,588 | Shots/corners/free kicksとparser identity | Sourceが供給していないxG、possession、SOT |
| Match events | `data/processed/sfms02_match_events/2015_2024_j1_match_events.csv` | 39,987 events | Deterministic match-local GOAL/SUB/YELLOW/RED source | Stable longitudinal player identity |
| Player minutes | `data/processed/sfms02_player_minutes/2015_2024_j1_player_minutes.csv` | 115,468 squad rows | 0–90 normalized participation intervals | Official elapsed minutes / cross-team identity |
| Match xG | `data/processed/jleague_match_xg/*.csv` | 380 + 200 + 80 = 660 | Rolling-xG source | Historical 2015–2024 xG coverage |
| Previous-season J Stats profiles | `data/processed/jstats_previous_season_profiles/2018_2025_j1_team_profiles.csv` | 864 profile rows | Explicit previous-season mapping source | In-season PIT snapshot |
| J Stats team snapshots | `data/processed/jstats_team_snapshots/<snapshot_id>.csv` | documented COMPLETE physical CSV 4件 | Cumulative prospective archive | Inferred per-match values |
| Manager matches/master | `data/processed/jleague_match_managers/`、`data/processed/jleague_manager_master/` | 3,208 matches。6,058/6,416 appearances resolved。master 462 rows | Identity audit/research | 残る358 appearancesのfuzzy resolution |
| Interim predictions | `data/processed/modeling/2026_27_interim_lockbox_predictions.csv` | immutable 70 target rows | Official opened-lockbox membership / predictions | New selection/tuning data |

Sources: [DATA_PIPELINE_STATUS.md](DATA_PIPELINE_STATUS.md)、[J1_MATCH_EVENT_DATASET.md](J1_MATCH_EVENT_DATASET.md)、[SFMS02_PLAYER_MINUTES_DATASET.md](SFMS02_PLAYER_MINUTES_DATASET.md)、[JLEAGUE_MATCH_XG_DATASET.md](JLEAGUE_MATCH_XG_DATASET.md)。

## C. Feature artifacts

下表のCSVはすべてgenerated / Git-ignored。`NOT DOCUMENTED`は、current dataset/freeze/result documentsにfrozen SHAが見つからないことを意味し、local fileが空または自由に変更可能という意味ではない。

| Artifact | Rows × columns | Seasons / family | Documented SHA-256 | Final evaluation status | Safe reuse boundary |
|---|---:|---|---|---|---|
| `data/processed/features/2015_2024_j1_h2h_features.csv` | 3,208 × 11 | 2015–2024 exact-pair H2H | `ab51fd674ee1665591e4b4b152a92f12ffd020211db3e541047c3066815784ff` | **CLOSED** | Audit/reproductionのみ。H2H variant search禁止 |
| `data/processed/features/2015_2024_j1_player_workload_features.csv` | 3,208 × 47 | previous XI/squad workload | `NOT DOCUMENTED` | **CLOSED** | Local-name / normalized-minute limitationを維持 |
| `data/processed/features/previous_season_jstats_features.csv` | 2,438 × 24 | targets 2020–2026/27。previous-season profiles | `NOT DOCUMENTED` | **CLOSED** retrospectively | Explicit mappingのみ。future rowsにoutcomeはなく、historical PIT proofではない |
| `data/processed/features/2015_2024_j1_team_discipline_features.csv` | 3,208 × 13 | prior team card rates | `UNRESOLVED`: source documentは65文字の`40a7581dd9fa9f85c3d2e2af3942a73390098f78c34664770cc1d28d06cf9f1f3`をSHA-256として記録 | **CLOSED** | 再利用前にdigestを検証。event-derived rateのみでplayer identityではない |
| `data/processed/features/2015_2024_j1_first_score_features.csv` | 3,208 × 21 | prior first-score profile | `aa5beb436695e0382ab39039f9b98de85aec73cfafc29765b060a451f1435f9a` | **CLOSED** | Frozen classification/tie semanticsのみ |
| `data/processed/features/2015_2024_j1_goal_timing_features.csv` | 3,208 × 25 | prior goal-timing profile | `260e79cec4836243586556c0e253818ed063d27870d74649c939502287919e42` | **CLOSED** | Normalized-minute semantics / exclusionを維持 |
| `data/processed/features/2015_2024_j1_substitution_timing_features.csv` | 3,208 × 13 | prior substitution timing | `898c7d53ed429d36920fd67b218333d837f5d2604c99c3556e47584721b9161f` | **CLOSED** | Count/regime-derived variant禁止 |
| `data/processed/features/2015_2024_j1_starter_df_features.csv` | 3,208 × 13 | previous-match starter DF count | `056963dd4707f122754d596ac6865721052cc3a31589a3a02941faca683aa674` | **CLOSED** | Source-listed position countでありformationではない |
| `data/processed/features/2015_2024_j1_draw_propensity_features.csv` | 3,208 × 21 | last-five/current-season draw rates | `97b33269a11b62f94dbd4b83924b97cc1cb1cb250ae0eb636ca5d8ccc6ba36a5` | **CLOSED** | Smoothing/window/subset/imputation follow-up禁止 |
| `data/processed/features/2025_2026_27_j1_rolling_xg_features.csv` | 660 × 18 | 2025、Hyakunen、opened first 80 rolling xG | `NOT DOCUMENTED` | **PROSPECTIVE_ONLY** | Frozen last-five v1。first 80はhistory、future 300はprospective targets |

Goal/substitution datasetが使用するevent-source SHAは`6eaaedbc7ffc5ad02a1207392924ff817e6356a08fbf64f3fbbfca9c62ec1131`であり、feature-output SHAではない。

未解決artifact referenceは4件。Player workload、previous-season J Stats、rolling xGのfeature-output SHAは未記録で、Team Disciplineのdocumented digestには上記length inconsistencyがある。このinventoryではreplacement valueを推定しない。

## D. Registries / masters / model bundles

| Asset | Path | Git state | Scope / limitation |
|---|---|---|---|
| TeamMaster | `data/master/teams.csv` | tracked | 49 stable team IDs / 103 aliases。exact source/date resolution、fuzzy fallbackなし |
| Manager master | `data/processed/jleague_manager_master/managers.csv` | generated/ignored | 462 rows。358/6,416 appearancesは未解決 |
| J Stats snapshot registry | `src/collect/jstats_snapshot_registry.py` + raw/processed snapshot directories | code tracked、observations ignored | Physical / logical BASE_10/SUPPLEMENTAL_27/FULL_37 stateをvalidate。raw filesはmergeしない |
| 2026/27 revision ledger | `data/processed/jleague/2026_27/{revisions,runs,change_log.csv,latest.json}` | generated/ignored | Append-only live schedule/result history。mutable publicationとfrozen target membershipを分離 |
| Player identity prototypes | `docs/J1_PLAYER_IDENTITY_LINKAGE_PROTOTYPE.md` + ignored research evidence | docs tracked、evidence ignored | Production player masterなし。automatic cross-season identityなし |
| Model A bundle | `models/model_a/operational_champion_20260922_v1/` | generated/ignored | Frozen 3,588-row Elo-only operational Champion。checksum validation必須 |
| X0/X1 bundle | `models/xg_challenger/xg_challenger_20260922_v1/` | generated/ignored | 594 eligible rowsで1回fit済み。prospective performance未開封。prediction時refit禁止 |

## E. Lockbox / held-out boundaries

| Boundary | State | 許可された使用 | 禁止された使用 |
|---|---|---|---|
| 2025 ordinary J1 | **SPENT TEST** | 既に指定されたfrozen operational training / historical replay | New feature/model/parameter selection |
| First 70 completed 2026/27 ordinary J1 | **OPENED INTERIM LOCKBOX** | Immutable official diagnostic / chronology audit | Tuning、thresholding、calibration、feature selection、target reselection |
| Frozen 70後のadditional live completed rows | **OPENED LIVE HISTORY** | Frozen contract下の後続target向けstrictly-prior operational history | Untouched retrospective holdoutとして扱うこと |
| 2026-09-22 rolling-xG freeze時点のfuture 300 | **PROSPECTIVE COHORT** | 1 dateずつのpre-match predictionと完了後の1 evaluation | Early metric inspection、cohort replacement、refit、window/feature変更 |
| Full 380-match 2026/27 check | **FUTURE FIXED-SPEC CHECK** | Existing freeze下の将来evaluation | Interim/live resultからのbackfit |

## F. Prospective snapshot / prediction families

| Family | Collector / operator | Raw path | Processed/output path | PIT semantics | Current status | Known limitation |
|---|---|---|---|---|---|---|
| J Stats team cumulative | `src.collect.jstats_team_snapshots`、source-state probe/registry | `data/raw/jstats_team_snapshots/<snapshot_id>/` | `data/processed/jstats_team_snapshots/<snapshot_id>.csv` | UTC retrieval timeとofficial displayed source dateを分離。append-only | **PROSPECTIVE_ONLY / OPERATIONAL COLLECTOR** | Verified update time/games playedなし。match-level reconstruction禁止 |
| J Stats player rankings | Authorized production collectorなし | ignored research evidence | なし | Future observationではranking absenceをunknownとして保持 | **DEFERRED** | 5 embedded IDsにperson-specific official identityなし |
| Suspension notices | `src.collect.jleague_suspensions`、manual official URLs、read-only `src.collect.jleague_suspension_registry` | `data/raw/jleague_suspensions/<snapshot_id>/` | `data/processed/jleague_suspensions/<snapshot_id>.csv` | `retrieved_at`とofficial `published_at`/`updated_at`を分離。V2はcapture-time kickoff/SHAをfreeze。First confirmed: 7 rows / 4 exact targets | **OPERATIONAL PROSPECTIVE CAPTURE / READ-ONLY PIT REGISTRY** | Archive completenessとplayer identityは未解決。absence = unknown。Historical production unsafe |
| 2026/27 schedule/results | ongoing update/revision pipeline | `data/raw/jleague/2026_27/` | `data/processed/jleague/2026_27/` | Immutable observations/revisions、validated latest pointer | **OPERATIONAL** | Live countは変化。row positionでfrozen target membershipを定義しない |
| Rolling xG predictions | `src.modeling.xg_challenger_prediction` | 上記official xG caches | IDs入手後の`data/processed/predictions/xg_challenger_prospective.csv` | Prior-date xG/Eloのみ、same-date batch、append-only `(match_id, model_version)` | **READY FOR DOCUMENTED PROSPECTIVE OPERATION** | 次batchにはofficial match IDsが必要。history不足はexact Model Aへfallback |

## G. Reuse checklist

Asset使用前に以下を確認する。

1. Documentationがtrackedでも、対象fileがlocalに存在する。
2. Documented SHA-256とschemaが一致する。
3. Target identityをexact IDでjoinし、row positionやfuzzy nameを使わない。
4. Assetのseason/competition/regulation-time scopeがtaskに一致する。
5. Current/final pageをhistorical PIT stateとして扱わない。
6. Opened/spent outcomeをselection/tuningに使わない。
7. Dataが再利用可能という理由だけでclosed model laneを再開しない。
