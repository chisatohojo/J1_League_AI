import test from "node:test";
import assert from "node:assert/strict";
import { syntheticRetrospective } from "./retrospective-fixture.mjs";
import { validateRetrospective, selectDisplayPrediction } from "../retrospective-data.js";
import { validateDashboard } from "../dashboard-data.js";

test("independent overlay validates without modifying the saved v2 feed",()=>{
  const {data,overlay}=syntheticRetrospective(),before=JSON.stringify(data);
  assert.equal(validateRetrospective(overlay,data),overlay);
  assert.equal(JSON.stringify(data),before);
  const matches=[...data.previousRound.matches,...data.nextRound.matches];
  assert.equal(matches.filter(m=>selectDisplayPrediction(m,overlay)?.kind==="saved_pre_match").length,4);
  assert.equal(matches.filter(m=>selectDisplayPrediction(m,overlay)?.kind==="retrospective_reconstruction").length,16);
  for(const m of matches.filter(m=>m.prediction)) assert.equal(selectDisplayPrediction(m,overlay).value,m.prediction);
  assert.equal(selectDisplayPrediction({...matches[2],status:"candidate"},overlay),null);
  assert.equal(selectDisplayPrediction(matches[2],null),null);
});

for(const [name,mutate] of Object.entries({
  source:o=>o.entries[0].reconstruction.type="saved_pre_match",
  home:o=>o.entries[0].homeTeamId="team_9999",
  officialId:o=>o.entries[0].officialId="888888",
  namespace:o=>o.entries[0].officialNamespace="jleague_data_site",
  round:o=>o.entries[0].round=1,
  day:o=>o.entries[0].matchDate="2026-10-01",
  result:o=>o.entries[0].result.homeScore=9,
  duplicate:o=>o.entries.push(structuredClone(o.entries[0])),
  candidate:o=>{o.historyRounds[0].matches[2].status="candidate";o.historyRounds[0].matches[2].result=null;},
  saved:o=>o.historyRounds[0].matches[2].prediction=structuredClone(o.historyRounds[0].matches[0].prediction),
  hash:o=>o.entries[0].reconstruction.artifactHash="0".repeat(64),
  hit:o=>o.entries[0].reconstruction.hit=false,
  time:o=>o.entries[0].reconstruction.calculatedAt="2026-02-30T00:00:00Z",
  precision:o=>o.entries[0].reconstruction.probabilities.home=56,
  revisionTime:o=>o.officialObservedAt="2026-10-19T00:00:00Z",
  extra:o=>o.entries[0].reconstruction.source="saved_pre_match",
  model:o=>o.model.version="ST2",
})) test(`retrospective rejects ${name}`,()=>{
  const {data,overlay}=syntheticRetrospective();mutate(overlay);assert.throws(()=>validateRetrospective(overlay,data));
});

test("v2 cannot disguise retrospective as a saved prediction",()=>{
  const {data}=syntheticRetrospective();data.previousRound.matches[0].prediction.source="retrospective_reconstruction";
  assert.throws(()=>validateDashboard(data));
});
