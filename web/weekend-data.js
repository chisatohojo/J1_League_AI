import { validateDashboard, CHAMPION_VERSION } from "./dashboard-data.js";

const require = (ok) => { if (!ok) throw new Error("週末の表示データを検証できません。表示を保留します。"); };
const keys = (v, names) => require(v && typeof v === "object" && !Array.isArray(v) && Object.keys(v).sort().join() === names.sort().join());
const jstDay = value => new Intl.DateTimeFormat("en-CA", {timeZone:"Asia/Tokyo", year:"numeric", month:"2-digit", day:"2-digit"}).format(new Date(value));

export function validateWeekend(data, base) {
  validateDashboard(base);
  keys(data, ["formatVersion", "model", "updatedAt", "sourceRevision", "baseFeedSha256", "period", "matches", "excludedSavedFixtureIds"]);
  require(data.formatVersion === "champion-weekend-display-v1" && base.mode === "operational");
  keys(data.model, ["name", "version"]);
  require(data.model.name === "Champion A" && data.model.version === CHAMPION_VERSION && data.updatedAt === base.updatedAt);
  require([data.sourceRevision, data.baseFeedSha256].every(v => typeof v === "string" && /^[a-f0-9]{64}$/.test(v)));
  require(Array.isArray(data.matches) && data.matches.length <= 100);
  require(Array.isArray(data.excludedSavedFixtureIds) && data.excludedSavedFixtureIds.length <= 100 &&
    data.excludedSavedFixtureIds.every(v => typeof v === "string" && v.length > 0 && v.length <= 200) &&
    JSON.stringify(data.excludedSavedFixtureIds) === JSON.stringify([...new Set(data.excludedSavedFixtureIds)].sort()));
  if (data.period === null) { require(data.matches.length === 0); return data; }
  require(Array.isArray(data.period) && data.period.length === 2 && data.period.every(v => typeof v === "string" && /^\d{4}-\d{2}-\d{2}$/.test(v)));
  const saturday = Date.parse(`${data.period[0]}T00:00:00+09:00`);
  require(Number.isFinite(saturday) && new Date(saturday + 9*3600000).getUTCDay() === 6 &&
    jstDay(new Date(saturday).toISOString()) === data.period[0] && jstDay(new Date(saturday+86400000).toISOString()) === data.period[1]);
  const ids = new Set(); let last = null;
  for (const row of data.matches) {
    keys(row, ["id", "homeTeam", "awayTeam", "kickoffAt", "fixtureStatus", "predictionStatus", "prediction", "warning"]);
    require(typeof row.id === "string" && row.id.length > 0 && row.id.length <= 200 && !ids.has(row.id)); ids.add(row.id);
    require(!data.excludedSavedFixtureIds.includes(row.id));
    for (const team of [row.homeTeam, row.awayTeam]) {
      keys(team, ["id", "name"]); require(typeof team.id === "string" && /^team_\d{4}$/.test(team.id) && typeof team.name === "string" && team.name.trim().length > 0 && team.name.length <= 200);
    }
    require(row.homeTeam.id !== row.awayTeam.id && typeof row.kickoffAt === "string" && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})$/.test(row.kickoffAt) && Number.isFinite(Date.parse(row.kickoffAt)));
    const [year,month,date] = row.kickoffAt.slice(0,10).split("-").map(Number);
    require(year >= 1 && month >= 1 && month <= 12 && date >= 1 && date <= new Date(Date.UTC(year,month,0)).getUTCDate());
    const day = jstDay(row.kickoffAt); require(day >= data.period[0] && day <= data.period[1]);
    const warnings = {saved:null, not_saved:null, schedule_unconfirmed:"日程未確認", prediction_conflict:"保存時の日程と不一致・表示保留"};
    require(Object.hasOwn(warnings, row.predictionStatus) && row.warning === warnings[row.predictionStatus]);
    require(["scheduled", "candidate", "completed"].includes(row.fixtureStatus) && (row.fixtureStatus === "candidate") === (row.predictionStatus === "schedule_unconfirmed"));
    if (row.predictionStatus === "saved") {
      const match = Object.fromEntries(["id", "homeTeam", "awayTeam", "kickoffAt", "prediction"].map(k => [k,row[k]]));
      validateDashboard({...base, previousRound:{label:"前節", matches:[]}, nextRound:{label:"週末", matches:[match]}});
      const original = [...base.previousRound.matches,...base.nextRound.matches].find(m => m.id === row.id);
      if (original) require(["homeTeam","awayTeam","kickoffAt","prediction"].every(k =>
        JSON.stringify(canonical(row[k])) === JSON.stringify(canonical(original[k]))));
    } else require(row.prediction === null);
    const order = [Date.parse(row.kickoffAt), row.id];
    require(!last || last[0] < order[0] || (last[0] === order[0] && last[1] < order[1])); last = order;
  }
  return data;
}

function canonical(value) {
  if (typeof value === "number") {
    const bytes = new Uint8Array(8); new DataView(bytes.buffer).setFloat64(0, value, false);
    return {$f64:[...bytes].map(v => v.toString(16).padStart(2,"0")).join("")};
  }
  if (Array.isArray(value)) return value.map(canonical);
  if (value && typeof value === "object") return Object.fromEntries(Object.keys(value).sort().map(k => [k,canonical(value[k])]));
  return value;
}

export async function verifyWeekendBinding(data, base) {
  validateWeekend(data, base);
  const bytes = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(JSON.stringify(canonical(base))));
  require([...new Uint8Array(bytes)].map(b => b.toString(16).padStart(2,"0")).join("") === data.baseFeedSha256);
  return data;
}
