import test from "node:test";
import assert from "node:assert/strict";
import { validateDashboard, highestProbabilityOutcomes, actualOutcome, formatKickoff } from "../dashboard-data.js";
import { DEMO_DATA } from "../demo-data.js";

function operationalData() {
  const data = structuredClone(DEMO_DATA);
  data.mode = "operational";
  return data;
}

test("opt-in demo data validates but cannot pass as operational feed", () => {
  assert.equal(validateDashboard(DEMO_DATA, { demo: true }), DEMO_DATA);
  assert.throws(() => validateDashboard(DEMO_DATA));
});

test("operational feed is read-only and retains stored probabilities", () => {
  const data = operationalData();
  const before = JSON.stringify(data);
  assert.equal(validateDashboard(data), data);
  assert.equal(JSON.stringify(data), before);
});

test("empty Champion feed is a valid not-yet-connected state", () => {
  const data = operationalData();
  data.previousRound.matches = [];
  data.nextRound.matches = [];
  assert.equal(validateDashboard(data), data);
});

const mutations = {
  "research mode": data => { data.mode = "research"; },
  "ST2 model name": data => { data.model.name = "ST2"; },
  "unknown model version": data => { data.model.version = "challenger"; },
  "extra research metrics": data => { data.research = { accuracy: 1 }; },
  "extra per-match lane": data => { data.nextRound.matches[0].branch = "ST2"; },
  "extra probability": data => { data.nextRound.matches[0].prediction.probabilities.st2 = 40; },
  "regenerated prediction": data => { data.nextRound.matches[0].prediction.source = "regenerated"; },
  "post-kickoff prediction": data => { data.nextRound.matches[0].prediction.generatedAt = data.nextRound.matches[0].kickoffAt; },
  "timezone absent": data => { data.nextRound.matches[0].kickoffAt = "2030-08-10T19:00:00"; },
  "invalid calendar date": data => { data.nextRound.matches[0].kickoffAt = "2030-02-30T19:00:00+09:00"; },
  "negative probability": data => { data.nextRound.matches[0].prediction.probabilities.home = -1; },
  "wrong probability scale": data => { data.nextRound.matches[0].prediction.probabilities = { home: 0.31, draw: 0.25, away: 0.44 }; },
  "NaN probability": data => { data.nextRound.matches[0].prediction.probabilities.home = NaN; },
  "missing stored probability": data => { delete data.nextRound.matches[0].prediction.probabilities.home; },
  "missing result": data => { delete data.previousRound.matches[0].result; },
  "negative score": data => { data.previousRound.matches[0].result.homeScore = -1; },
  "boolean score": data => { data.previousRound.matches[0].result.homeScore = true; },
  "future outcome": data => { data.nextRound.matches[0].result = { homeScore: 1, awayScore: 1 }; },
  "duplicate match id": data => { data.nextRound.matches[0].id = data.previousRound.matches[0].id; },
  "same team": data => { data.nextRound.matches[0].awayTeam = data.nextRound.matches[0].homeTeam; },
  "array-shaped team id": data => { data.nextRound.matches[0].homeTeam.id = ["team_0003"]; },
};
for (const [name, mutate] of Object.entries(mutations)) {
  test(`reject ${name}`, () => {
    const data = operationalData();
    mutate(data);
    assert.throws(() => validateDashboard(data));
  });
}

test("AI pick uses original precision, not display rounding; exact ties stay explicit", () => {
  assert.deepEqual(highestProbabilityOutcomes({ home: 33.33333, draw: 33.33334, away: 33.33333 }), ["draw"]);
  assert.deepEqual(highestProbabilityOutcomes({ home: 40, draw: 20, away: 40 }), ["home", "away"]);
});

for (const [score, expected] of [
  [{ homeScore: 2, awayScore: 1 }, "home"],
  [{ homeScore: 0, awayScore: 0 }, "draw"],
  [{ homeScore: 0, awayScore: 1 }, "away"],
]) test(`RESULT keeps the official ${expected} outcome and score unchanged`, () => {
  const result = Object.freeze(score), before = JSON.stringify(result);
  assert.equal(actualOutcome(result), expected);
  assert.equal(JSON.stringify(result), before);
});

test("kickoff display is JST, independent of client timezone", () => {
  assert.match(formatKickoff("2030-08-10T10:00:00Z"), /19:00/);
});

function roundData() {
  const data = operationalData();
  data.schemaVersion = 2;
  const sample = data.previousRound.matches[0];
  for (const [section, number] of [["previousRound", 1], ["nextRound", 2]]) {
    const matches = Array.from({ length: 10 }, (_, i) => {
      const match = structuredClone(sample);
      Object.assign(match, { id: `round-${number}-${String(i).padStart(2, "0")}`, round: number,
        status: i < 8 ? "completed" : "scheduled", kickoffAt: `2030-08-${number + 10}T19:00:00+09:00` });
      match.homeTeam.id = `team_${String(2*i+1).padStart(4,"0")}`;
      match.awayTeam.id = `team_${String(2*i+2).padStart(4,"0")}`;
      if (i >= 2) match.prediction = null;
      else match.prediction.generatedAt = "2030-08-01T09:00:00+09:00";
      if (match.status !== "completed") match.result = null;
      return match;
    });
    data[section] = { label: `第${number}節`, number, kind: number === 1 ? "previous" : "current", matches };
  }
  return data;
}

test("v2 all official fixtures, missing predictions and unconfirmed results validate without mutation", () => {
  const data = roundData();
  data.nextRound.matches[0].status = "candidate";
  data.nextRound.matches[0].result = null;
  const before = JSON.stringify(data);
  assert.equal(validateDashboard(data), data);
  assert.equal(JSON.stringify(data), before);
});

for (const [problem, mutate] of Object.entries({
  partial: d => d.nextRound.matches.pop(),
  round: d => { d.nextRound.matches[0].round = 3; },
  kind: d => { d.nextRound.kind = "previous"; },
  team: d => { d.nextRound.matches[1].homeTeam.id = d.nextRound.matches[0].homeTeam.id; },
  order: d => d.nextRound.matches.reverse(),
  candidateScore: d => { d.nextRound.matches[0].status = "candidate"; },
  missingFinalScore: d => { d.nextRound.matches[0].result = null; },
  research: d => { d.nextRound.matches[9].st2 = 1; },
  fakePrediction: d => { d.nextRound.matches[0].prediction.source = "generated"; },
})) test(`v2 rejects ${problem}`, () => { const data = roundData(); mutate(data); assert.throws(() => validateDashboard(data)); });
