# J1 historical match event data feasibility

調査日: 2026-09-24 (JST)

## Scope and conclusion

既存のJ.League Data Site / SFMS02 raw cacheをread-onlyで監査した。対象はordinary J1 2015–2024の3,208試合であり、既存のcache、parser、player-minutes dataset、Starting XI audit、TeamMasterを使用した。production event dataset、feature、model fitting、prediction、metric calculationは行っていない。

総合判定は **PROCEED_TO_EVENT_DATASET_SPEC**。match-local event extractionは十分に実現可能で、既存のSFMS02 minutes parserがイベントsectionの境界・名前・時刻・状態を既に検証している。ただし stable player identity は未解決であり、match-local event datasetの実装可否とlongitudinal player featureの可否は分離する。

## Source and local coverage

主な入力:

- `data/raw/jleague_match_stats/` — SFMS02 HTML 3,588件（2015–2025 cache、今回の対象は2015–2024の3,208件）
- `data/processed/jleague/{season}_matches_probe.csv` — match identity/date/team reference
- `src/collect/sfms02_player_minutes.py` — A5/A6/A7/A9の既存構造・時刻・状態 parser
- `src/collect/jleague_match_stats.py` — official match-level basic stats parser
- `src/features/player_workload.py` — match-local player rowsを使う既存feature builder
- `data/processed/sfms02_player_minutes/2015_2024_j1_player_minutes.csv`

全3,208試合について、match cacheとprobeのjoin、source hash、A5/A6/A7の構造、player-nameのblank/replacement character、team-minute conservationは既存dataset auditで検証済み。今回のイベント監査でも既存cache以外のHTTP取得は行っていない。

## Representative samples

2015・2019・2024から、通常試合、複数交代、警告、退場、複数得点を含むcacheを確認した。代表的な構造は次の通り。

| section | content | observed structure |
|---|---|---|
| A1 | result | home/away team and final score |
| A2 | goals | goal event rows, player name, minute and goal-related display fields |
| A5 | starting XI | two side sections, 11 rows per side |
| A6 | bench | two side sections, player rows |
| A7 | substitutions | side-specific OUT/IN pairs; time is on the OUT row |
| A8 | yellow cards | side-specific card event rows |
| A9 | dismissals | side-specific red/dismissal event rows |

既存parserはA7の`▽`/`▲`をOUT/INとして扱い、A9の退場を別イベントとして扱う。A9は存在しない試合もあり、その場合は「退場なし」と「source欠損」を区別する必要がある。

## Proposed event schema

将来のevent datasetは、少なくとも次の列を持つ。

| field | policy |
|---|---|
| `event_id` | source rowの安定digest等。推測IDは作らない |
| `match_id` | official SFMS02 match ID |
| `match_date` | match probeと一致させる |
| `season` | ordinary J1 season |
| `team_id` | TeamMaster exact resolution |
| `side` | `home` / `away` |
| `event_type` | `GOAL`, `SUBSTITUTION`, `YELLOW_CARD`, `RED_CARD`等 |
| `player_name_raw` | source表示をlosslessに保持 |
| `related_player_name_raw` | substitutionのIN/OUT相手等、該当時のみ |
| `minute_raw` | 必ず原文を保存 |
| `minute_normalized` | deterministicに解釈できる場合のみ。rawを上書きしない |
| `source_section` | A2/A7/A8/A9 |
| `source_url` / `raw_sha256` | provenance |
| `null_reason` | section absent、player absent、minute absent等を明示 |

player ID列は、sourceに実際のstable official IDがある場合のみ保存する。SFMS02の観測範囲ではplayer profile link、`player_id`、`member_id`等は確認されていないため、現在値はnull/未提供となる。名前のみでcross-match identityを作成しない。

## Event semantics

### Goals

A2をgoal event sourceとする。通常の得点、own goal、penalty goal、stoppage-time goalはevent typeまたは属性で分離できるか確認し、分離不能な場合は「通常goal」と推測しない。A1 final scoreとの照合はdiagnosticに使えるが、欠落・曖昧なeventからscoreを再構成しない。

### Substitutions

A7の隣接OUT/IN行を1 substitution eventに束ねる。IN行の時刻が空欄で、OUT行の時刻をペアへ継承する既存方針を使える。unpaired row、同一時刻のdismissalとの順序競合、未知player名はhard failureまたはunresolvedとして露出させる。

### Cards and dismissals

A8はyellow-card event、A9はdismissal eventとして保存する。second yellowとdirect redをsourceに明示された場合のみ分離する。A8だけからredを推測しない。交代OUT後の退場や、出場前の控えの退場などの例外があるため、player stateを用いたevent interpretationが必要である。

## Minute semantics

raw minuteは必ず保存する。既存cacheでは少なくとも次を扱う必要がある。

- integer minute: `1'`, `46'`, `90'`
- first-half added time: `45+N'`
- second-half added time: `90+N'`
- halftime substitution: source orderとminute stateで扱う
- missing minute: null + reason
- extra-time notation: ordinary J1では通常対象外だが、入力に現れた場合は別status

`45+N` / `90+N`を整数分へ単純変換してrawを失わない。`46'`は45分終了後か後半開始直後かを物理時間として確定できないため、既存policyどおり normalization flagを付ける。same-minute substitution/redの順序がsourceから確定できない場合は黙って並べ替えない。

## Identity findings

| identity | result |
|---|---|
| match identity | 3,208 probe/cache rowsのexact joinが可能 |
| team identity | TeamMaster exact resolutionが可能 |
| event-local player name | A2/A5/A6/A7/A8/A9のraw nameを保持可能 |
| official player ID in SFMS02 | observed cacheでは未確認 |
| longitudinal player identity | raw nameのみでは安全に確定不可 |

同一team・同一season内の短期exact-name比較は限定的な診断には使えるが、同姓同名、表記変更、移籍、season境界を解消しない。将来player-level featureを作る場合は、別途公式player-ID crosswalkが必要である。

## Coverage classification

既存の全件minutes auditで、3,208 match、6,416 team lineups、70,576 starters、A7交代47,276行、A8警告7,671行、A9退場301行が監査済みである。A5/A6/A7/A9の構造・状態検証は全cacheに対して通過しており、A8はsectionが無い試合を含む「イベントなし」と、イベント行がある試合を区別できる。

| item | feasibility | reason |
|---|---|---|
| goals | B | A2 source section exists; own goal/penalty/score consistencyの全件event schema検証は未materialize |
| substitutions | A/B | A7のOUT/IN pairとminute stateは既存parserで全件扱える。source exceptionはhard failで露出可能 |
| yellow cards | B | A8 section/rowsを取得可能。card subtypeの完全性はsource表示に依存 |
| red cards | B | A9 section/rowsを取得可能。second-yellow/direct-red区別と出場状態を別途保持 |
| player event identity | C | stable official player IDなし。match-local raw nameに限定 |
| team-side identity | A | existing TeamMaster / match identityで exact resolution可能 |

「sectionが存在する」ことと「イベントが1件以上ある」ことは同じではない。イベント0件は正常なno-event状態として扱い、source欠損と混同しない。

## Chronology and leakage policy

イベントはpost-match observationである。将来feature化する場合、target match自身のevent、同時刻の別match event、future match eventは使用しない。target開始前に完了したmatchだけをhistoryへ追加する。同日でkickoff datetimeがない場合は保守的にdate bucketを使い、同日match間の相互利用を禁止する。

event minuteはmatch内の順序復元に使えるが、match間のpre-match availabilityを意味しない。first-goal history、card burden、substitution timing等は、対象match以前の確定eventだけで構築する。

## Regulation and non-league scope

今回の対象はordinary J1のみ。extra-time / PK shootoutのあるCup等をこのevent schemaへ混ぜない。別competitionを追加する場合は、competition discriminator、regulation-time semantics、source identityを別途監査する。

## Recommended next step

次段階はproduction collectorではなく、fixtureを固定したread-only event schema specificationとfixture testsである。少なくとも以下を先にfixture化する。

1. A2 multiple goals / own goal / penalty / stoppage-time
2. A7 multiple substitutions and halftime substitution
3. A8 yellow and second-yellow evidence
4. A9 direct red, post-substitution dismissal, and unused-substitute dismissal
5. missing section versus zero-event semantics
6. raw minute preservation and deterministic normalization
7. exact TeamMaster and match-ID resolution

その後、全件のevent materializationを別taskとして実施する。player-level longitudinal featureはstable player IDが得られるまでclosed/deferredとする。

## Prohibited in this audit

- model fitting, prediction, metric calculation
- feature selection or feature generation
- fuzzy/normalized/manual player identity mapping
- score reconstruction from incomplete events
- Cup/J2/J3/AFC event mixing
- broad external crawl
- 2025/2026 performance use

## Completion note

Local cache read-only audit: completed. External HTTP requests: 0. Created file: this document only. No event CSV, production collector, feature, model, or prediction was created.

