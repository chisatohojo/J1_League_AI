export const CHAMPION_VERSION = "operational_champion_20260922_v1";

function require(condition, message) {
  if (!condition) throw new Error(`表示データを検証できません: ${message}`);
}

function exactKeys(value, keys, label) {
  require(value !== null && typeof value === "object" && !Array.isArray(value), label);
  require(Object.keys(value).sort().join(",") === [...keys].sort().join(","), `${label} schema`);
}

function string(value, label) {
  require(typeof value === "string" && value.trim().length > 0 && value.length <= 200, label);
}

function timestamp(value, label) {
  require(typeof value === "string" && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})$/.test(value)
    && Number.isFinite(Date.parse(value)), label);
  const [year, month, day] = value.slice(0, 10).split("-").map(Number);
  require(year >= 1 && month >= 1 && month <= 12 && day >= 1
    && day <= new Date(Date.UTC(year, month, 0)).getUTCDate(), label);
}

/** Champion-only display contract. No research lane, outcome join, CSV read or prediction. */
export function validateDashboard(data, { demo = false } = {}) {
  exactKeys(data, ["schemaVersion", "mode", "model", "updatedAt", "previousRound", "nextRound"], "dashboard");
  require(data.schemaVersion === 1 && data.mode === (demo ? "demo" : "operational"), "mode/version");
  exactKeys(data.model, ["name", "version"], "model");
  require(data.model.name === "Champion A" && data.model.version === CHAMPION_VERSION, "Champion allowlist");
  if (data.updatedAt !== null) timestamp(data.updatedAt, "updatedAt");
  const ids = new Set();
  for (const [key, previous] of [["previousRound", true], ["nextRound", false]]) {
    const round = data[key];
    exactKeys(round, ["label", "matches"], key);
    string(round.label, "round label");
    require(Array.isArray(round.matches) && round.matches.length <= 100, "round matches");
    for (const match of round.matches) {
      exactKeys(match, ["id", "homeTeam", "awayTeam", "kickoffAt", "prediction", ...(previous ? ["result"] : [])], "match");
      string(match.id, "match id");
      require(!ids.has(match.id), "duplicate match id");
      ids.add(match.id);
      for (const team of [match.homeTeam, match.awayTeam]) {
        exactKeys(team, ["id", "name"], "team");
        require(typeof team.id === "string" && /^team_\d{4}$/.test(team.id), "TeamMaster id");
        string(team.name, "team name");
      }
      require(match.homeTeam.id !== match.awayTeam.id, "distinct teams");
      timestamp(match.kickoffAt, "kickoff");
      exactKeys(match.prediction, ["source", "generatedAt", "probabilities"], "prediction");
      require(match.prediction.source === "saved_pre_match", "saved pre-match source");
      timestamp(match.prediction.generatedAt, "prediction time");
      require(Date.parse(match.prediction.generatedAt) < Date.parse(match.kickoffAt), "prediction before kickoff");
      const probabilities = match.prediction.probabilities;
      exactKeys(probabilities, ["home", "draw", "away"], "probabilities");
      const values = Object.values(probabilities);
      require(values.every(value => typeof value === "number" && Number.isFinite(value) && value >= 0 && value <= 100)
        && Math.abs(values.reduce((sum, value) => sum + value, 0) - 100) <= 0.02 + 1e-9, "probability percentages");
      if (previous) {
        exactKeys(match.result, ["homeScore", "awayScore"], "result");
        require(Object.values(match.result).every(value => Number.isSafeInteger(value) && value >= 0), "score");
      }
    }
  }
  return data;
}

/** Uses full stored precision; display rounding never determines the pick. */
export function highestProbabilityOutcomes(probabilities) {
  const maximum = Math.max(probabilities.home, probabilities.draw, probabilities.away);
  return ["home", "draw", "away"].filter(outcome => probabilities[outcome] === maximum);
}

export function actualOutcome(result) {
  return result.homeScore === result.awayScore ? "draw" : result.homeScore > result.awayScore ? "home" : "away";
}

export function formatKickoff(value) {
  return new Intl.DateTimeFormat("ja-JP", {
    timeZone: "Asia/Tokyo", month: "2-digit", day: "2-digit", weekday: "short", hour: "2-digit", minute: "2-digit", hour12: false,
  }).format(new Date(value));
}
