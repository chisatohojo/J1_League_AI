import { validateDashboard, actualOutcome } from "./dashboard-data.js";

export const RETROSPECTIVE_TYPE = "retrospective_reconstruction";
const HASH = /^[0-9a-f]{64}$/;
const ARTIFACT = "2d2e50dbfc4d71ec2cdaf5fe1a6e48953c160c388f1740cfe538f29f593646d1";
const ORDER = ["away", "draw", "home"];
function require(value, code) { if (!value) throw new Error(`後日再現データ: ${code}`); }
function keys(value, names) {
  require(value && typeof value === "object" && !Array.isArray(value)
    && Object.keys(value).sort().join() === names.slice().sort().join(), "schema");
}
function canonical(value) {
  if (Array.isArray(value)) return `[${value.map(canonical).join(",")}]`;
  if (value && typeof value === "object") return `{${Object.keys(value).sort().map(k => `${JSON.stringify(k)}:${canonical(value[k])}`).join(",")}}`;
  return JSON.stringify(value);
}
function timestamp(value) {
  require(typeof value === "string" && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})$/.test(value)
    && Number.isFinite(Date.parse(value)), "timestamp");
  const [y,m,d] = value.slice(0,10).split("-").map(Number);
  require(y >= 1 && m >= 1 && m <= 12 && d >= 1 && d <= new Date(Date.UTC(y,m,0)).getUTCDate(), "calendar");
}

/** Independent overlay: no modification to the strict saved_pre_match v2 contract. */
export function validateRetrospective(overlay, dashboard) {
  validateDashboard(dashboard);
  keys(overlay, ["schemaVersion","type","model","runId","reconstructionRevision","officialRevision",
    "officialObservedAt","note","dashboardSha256","entries","historyRounds","diagnostics","officialIdentities"]);
  require(dashboard.schemaVersion === 2 && overlay.schemaVersion === 1 && overlay.type === "retrospective_overlay"
    && canonical(overlay.model) === canonical(dashboard.model)
    && overlay.note === "当時の試合前保存予測ではありません", "contract");
  for (const key of ["runId","reconstructionRevision","officialRevision","dashboardSha256"]) require(typeof overlay[key] === "string" && HASH.test(overlay[key]), "hash");
  timestamp(overlay.officialObservedAt);
  require(overlay.officialObservedAt === dashboard.updatedAt, "official observation changed");
  require(Array.isArray(overlay.historyRounds) && overlay.historyRounds.length > 0 && overlay.historyRounds.length <= 38
    && Array.isArray(overlay.entries) && overlay.entries.length <= 380
    && Array.isArray(overlay.diagnostics) && overlay.diagnostics.length <= 380, "bounds");
  const fixtures = new Map(), numbers = new Set();
  let preceding = 0;
  for (const section of overlay.historyRounds) {
    validateDashboard({ ...dashboard, previousRound: section,
      nextRound: { label:"次節", number:null, kind:"next", matches:[] } });
    require(section.number > preceding && !numbers.has(section.number), "round order");
    preceding = section.number; numbers.add(section.number);
    for (const match of section.matches) {
      require(!fixtures.has(match.id), "duplicate history fixture"); fixtures.set(match.id,match);
    }
  }
  for (const section of [dashboard.previousRound,dashboard.nextRound]) for (const match of section.matches) {
    if (numbers.has(match.round)) require(canonical(fixtures.get(match.id)) === canonical(match), "current fixture changed");
  }
  keys(overlay.officialIdentities,[...fixtures.keys()]);
  const officialIds = new Set();
  for (const [key,identity] of Object.entries(overlay.officialIdentities)) {
    keys(identity,["id","namespace"]);
    if (identity.id === null && identity.namespace === null) require(fixtures.get(key).status !== "completed","completed official ID missing");
    else {
      const pair = `${identity.namespace}:${identity.id}`;
      require(typeof identity.id === "string" && /^\d+$/.test(identity.id)
        && ["jleague_match_page","jleague_data_site"].includes(identity.namespace) && !officialIds.has(pair),"official ID collision");
      officialIds.add(pair);
    }
  }
  const seen = new Set(), models = new Set();
  for (const entry of overlay.entries) {
    keys(entry,["fixtureKey","round","matchDate","homeTeamId","awayTeamId","officialId","officialNamespace","result","reconstruction"]);
    require(!seen.has(entry.fixtureKey) && fixtures.has(entry.fixtureKey), "duplicate/missing fixture"); seen.add(entry.fixtureKey);
    const match = fixtures.get(entry.fixtureKey), reconstruction = entry.reconstruction;
    require(overlay.officialIdentities[entry.fixtureKey].id === entry.officialId
      && overlay.officialIdentities[entry.fixtureKey].namespace === entry.officialNamespace,"official ID mismatch");
    keys(entry.result,["homeScore","awayScore"]);
    require(Object.values(entry.result).every(v => Number.isSafeInteger(v) && v >= 0),"score");
    const day = new Intl.DateTimeFormat("sv-SE",{timeZone:"Asia/Tokyo",year:"numeric",month:"2-digit",day:"2-digit"}).format(new Date(match.kickoffAt));
    require(match.status === "completed" && match.prediction === null && Number.isInteger(entry.round) && entry.round === match.round
      && entry.matchDate === day && entry.homeTeamId === match.homeTeam.id && entry.awayTeamId === match.awayTeam.id
      && canonical(entry.result) === canonical(match.result) && typeof entry.officialId === "string" && /^\d+$/.test(entry.officialId)
      && ["jleague_match_page","jleague_data_site"].includes(entry.officialNamespace), "official identity/result");
    keys(reconstruction,["type","calculatedAt","probabilities","predictedOutcome","hit","modelHash","artifactHash"]);
    require(reconstruction.type === RETROSPECTIVE_TYPE && reconstruction.artifactHash === ARTIFACT
      && typeof reconstruction.modelHash === "string" && HASH.test(reconstruction.modelHash), "model/type");
    models.add(reconstruction.modelHash); timestamp(reconstruction.calculatedAt);
    require(Date.parse(reconstruction.calculatedAt) >= Date.parse(match.kickoffAt), "calculation time");
    keys(reconstruction.probabilities,["home","draw","away"]);
    const probabilities = reconstruction.probabilities, values = Object.values(probabilities);
    require(values.every(v => typeof v === "number" && Number.isFinite(v) && v >= 0 && v <= 100)
      && Math.abs(values.reduce((a,b) => a+b,0)-100) < 1e-9, "probabilities");
    const pick = ORDER.reduce((best,side) => probabilities[side] > probabilities[best] ? side : best,"away");
    require(reconstruction.predictedOutcome === pick && typeof reconstruction.hit === "boolean"
      && reconstruction.hit === (pick === actualOutcome(match.result)), "pick/hit");
  }
  require(models.size <= 1,"mixed models");
  const codes = ["fixture_missing","official_not_completed","round_mismatch","kickoff_mismatch","official_result_corrected",
    ...["match_date","home_team_id","away_team_id","match_id","match_id_namespace"].map(k=>k+"_mismatch")];
  const diagnostics = new Set();
  for (const entry of overlay.diagnostics) {
    keys(entry,["fixtureKey","code"]);
    require(typeof entry.fixtureKey === "string" && entry.fixtureKey.length > 0 && entry.fixtureKey.length <= 200
      && !diagnostics.has(entry.fixtureKey) && !seen.has(entry.fixtureKey) && codes.includes(entry.code),"diagnostic");
    diagnostics.add(entry.fixtureKey);
  }
  return overlay;
}

export function selectDisplayPrediction(match, overlay) {
  if (match.prediction !== null) return { kind:"saved_pre_match", value:match.prediction };
  const entry = overlay?.entries.find(row => row.fixtureKey === match.id);
  if (match.status === "completed" && entry) return { kind:RETROSPECTIVE_TYPE, value:entry.reconstruction };
  return null;
}

/** One HTTP response binds v2 + overlay to a single immutable display generation. */
export function validatePresentation(value) {
  keys(value,["schemaVersion","generationId","sequence","dashboard","overlay","status"]);
  require(value.schemaVersion===1 && typeof value.generationId==="string" && HASH.test(value.generationId)
    && Number.isSafeInteger(value.sequence) && value.sequence>0,"presentation identity");
  validateRetrospective(value.overlay,value.dashboard);
  const status=value.status;
  keys(status,["state","startedAt","finishedAt","lastSuccessAt","errorCode","pollEnabled","pollSeconds","feedUpdatedAt"]);
  require(["idle","updating","ready","error"].includes(status.state) && status.pollEnabled===true
    && Number.isInteger(status.pollSeconds) && status.pollSeconds>=10 && status.pollSeconds<=3600
    && status.feedUpdatedAt===value.dashboard.updatedAt
    && [null,"update_failed","display_reload_failed","update_status_invalid"].includes(status.errorCode),"presentation status");
  for(const key of ["startedAt","finishedAt","lastSuccessAt"]) if(status[key]!==null) timestamp(status[key]);
  return value;
}
