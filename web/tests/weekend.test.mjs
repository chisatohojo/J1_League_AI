import test from 'node:test';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {DEMO_DATA} from '../demo-data.js';
import {validateWeekend,verifyWeekendBinding} from '../weekend-data.js';

function fixture() {
  const base=structuredClone(DEMO_DATA);base.mode='operational';
  const saved=structuredClone(base.nextRound.matches[0]);saved.id='saturday';saved.kickoffAt='2030-11-02T19:00:00+09:00';
  const rows=[{...saved,fixtureStatus:'scheduled',predictionStatus:'saved',warning:null},
    {...structuredClone(saved),id:'sunday',kickoffAt:'2030-11-03T10:00:00Z',fixtureStatus:'scheduled',predictionStatus:'not_saved',prediction:null,warning:null}];
  const canonical=value=>{
    if(typeof value==='number'){const b=Buffer.alloc(8);b.writeDoubleBE(value);return {$f64:b.toString('hex')};}
    if(Array.isArray(value))return value.map(canonical);
    if(value&&typeof value==='object')return Object.fromEntries(Object.keys(value).sort().map(k=>[k,canonical(value[k])]));
    return value;
  };
  return {base,view:{formatVersion:'champion-weekend-display-v1',model:structuredClone(base.model),updatedAt:base.updatedAt,sourceRevision:'a'.repeat(64),baseFeedSha256:createHash('sha256').update(JSON.stringify(canonical(base))).digest('hex'),period:['2030-11-02','2030-11-03'],matches:rows,excludedSavedFixtureIds:[]}};
}

test('saved and unsaved coexist; JST date is used; no input mutation',async()=>{
  const {base,view}=fixture();const before=JSON.stringify({base,view});
  assert.equal(await verifyWeekendBinding(view,base),view);assert.equal(JSON.stringify({base,view}),before);
  assert.equal(view.matches[1].prediction,null);
});

const mutations={
  'duplicate':v=>v.matches.push(structuredClone(v.matches[0])),
  'other weekend':v=>v.matches[1].kickoffAt='2030-11-10T19:00:00+09:00',
  'invented prediction':v=>v.matches[1].prediction=structuredClone(v.matches[0].prediction),
  'missing saved value':v=>v.matches[0].prediction=null,
  'NN model':v=>v.model.name='NN v2',
  'research field':v=>v.research={},
  'wrong period':v=>v.period=['2030-11-01','2030-11-03'],
  'wrong timezone':v=>v.matches[1].kickoffAt='2030-11-03T19:00:00',
  'reordered':v=>v.matches.reverse(),
  'warning omitted':v=>v.matches[1].predictionStatus='prediction_conflict',
  'unconfirmed with probabilities':v=>v.matches[0].fixtureStatus='candidate',
  'unknown state':v=>v.matches[1].predictionStatus='generated',
  'source revision':v=>v.sourceRevision='latest',
  'team identity':v=>v.matches[1].homeTeam.id='unknown',
  'same teams':v=>v.matches[1].awayTeam=structuredClone(v.matches[1].homeTeam),
  'extra paragraph':v=>v.matches[1].notes='unexpected',
};
for(const [name,change]of Object.entries(mutations))test(`reject ${name}`,()=>{const {base,view}=fixture();change(view);assert.throws(()=>validateWeekend(view,base));});
test('changed base binding is rejected',async()=>{const{base,view}=fixture();view.baseFeedSha256='0'.repeat(64);await assert.rejects(verifyWeekendBinding(view,base));});
test('no confirmed schedule is explicitly empty',()=>{const{base,view}=fixture();view.period=null;view.matches=[];assert.equal(validateWeekend(view,base),view);});
