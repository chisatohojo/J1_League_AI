import { CHAMPION_VERSION } from "./dashboard-data.js";

// Entirely synthetic UI fixtures. Not copied from any saved production prediction/outcome.
const team = (id, name) => ({ id, name });
const teams = {
  tokyo: team("team_0003", "FC東京"), urawa: team("team_0030", "浦和レッズ"),
  kashima: team("team_0008", "鹿島アントラーズ"), gamba: team("team_0005", "ガンバ大阪"),
  kobe: team("team_0011", "ヴィッセル神戸"), hiroshima: team("team_0006", "サンフレッチェ広島"),
  kawasaki: team("team_0010", "川崎フロンターレ"), kashiwa: team("team_0009", "柏レイソル"),
};
function match(id, home, away, kickoffAt, probabilities, result) {
  return {
    id: `synthetic-${id}`, homeTeam: teams[home], awayTeam: teams[away], kickoffAt,
    prediction: { source: "saved_pre_match", generatedAt: "2030-08-01T10:00:00+09:00", probabilities },
    ...(result ? { result } : {}),
  };
}
export const DEMO_DATA = {
  schemaVersion: 1, mode: "demo", model: { name: "Champion A", version: CHAMPION_VERSION },
  updatedAt: null,
  previousRound: { label: "第20節 · デモ", matches: [
    match("previous-1", "kashima", "gamba", "2030-08-03T19:00:00+09:00", { home: 48, draw: 27, away: 25 }, { homeScore: 2, awayScore: 1 }),
    match("previous-2", "kobe", "hiroshima", "2030-08-03T19:00:00+09:00", { home: 39, draw: 28, away: 33 }, { homeScore: 1, awayScore: 1 }),
  ] },
  nextRound: { label: "第21節 · デモ", matches: [
    match("next-1", "tokyo", "urawa", "2030-08-10T19:00:00+09:00", { home: 31, draw: 25, away: 44 }),
    match("next-2", "kawasaki", "kashiwa", "2030-08-11T18:30:00+09:00", { home: 41, draw: 31, away: 28 }),
  ] },
};
