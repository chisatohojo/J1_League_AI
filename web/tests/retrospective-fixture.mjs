import { DEMO_DATA } from "../demo-data.js";

export function syntheticRetrospective() {
  const data = structuredClone(DEMO_DATA);
  data.mode = "operational"; data.schemaVersion = 2; data.updatedAt = "2026-10-18T00:00:00Z";
  for (const [key,number] of [["previousRound",9],["nextRound",10]]) {
    const sample = structuredClone(DEMO_DATA.previousRound.matches[0]);
    const matches = Array.from({length:10},(_,i) => {
      const match=structuredClone(sample), completed=number===9 || i<8;
      const day=number===9 ? i<2?"09":i<6?"10":"11" : i<8?"17":"18";
      Object.assign(match,{id:`j1_2026_2027:club${number}-${i}:away${number}-${i}`,round:number,
        status:completed?"completed":"scheduled",kickoffAt:`2026-10-${day}T19:00:00+09:00`,
        result:completed?{homeScore:2,awayScore:1}:null});
      match.homeTeam.id=`team_${String(2*i+1).padStart(4,"0")}`;
      match.awayTeam.id=`team_${String(2*i+2).padStart(4,"0")}`;
      match.prediction=number===9?i<2?{source:"saved_pre_match",generatedAt:"2026-10-08T08:00:00Z",probabilities:{home:31,draw:25,away:44}}:null
        :i>=8?{source:"saved_pre_match",generatedAt:"2026-10-18T00:00:00Z",probabilities:{home:51,draw:25,away:24}}:null;
      return match;
    });
    data[key]={label:`${number===9?"前節":"今節"} · 第${number}節`,number,kind:number===9?"previous":"current",matches};
  }
  const entries=[...data.previousRound.matches,...data.nextRound.matches].filter(m=>m.prediction===null).map((m,i)=>({
    fixtureKey:m.id,round:m.round,matchDate:m.kickoffAt.slice(0,10),homeTeamId:m.homeTeam.id,awayTeamId:m.awayTeam.id,
    officialId:String(100000+i),officialNamespace:"jleague_match_page",result:structuredClone(m.result),
    reconstruction:{type:"retrospective_reconstruction",calculatedAt:"2026-10-18T05:00:00Z",
      probabilities:{home:55,draw:25,away:20},predictedOutcome:"home",hit:true,modelHash:"6".repeat(64),
      artifactHash:"2d2e50dbfc4d71ec2cdaf5fe1a6e48953c160c388f1740cfe538f29f593646d1"}}));
  const overlay={schemaVersion:1,type:"retrospective_overlay",model:structuredClone(data.model),runId:"1".repeat(64),
    reconstructionRevision:"2".repeat(64),officialRevision:"3".repeat(64),officialObservedAt:data.updatedAt,
    note:"当時の試合前保存予測ではありません",dashboardSha256:"4".repeat(64),entries,
    historyRounds:[structuredClone(data.previousRound),{...structuredClone(data.nextRound),kind:"previous"}],diagnostics:[],
    officialIdentities:Object.fromEntries([...data.previousRound.matches,...data.nextRound.matches].map((m,i)=>[m.id,
      {id:entries.find(e=>e.fixtureKey===m.id)?.officialId ?? String(200000+i),namespace:"jleague_match_page"}]))};
  return {data,overlay};
}

export function syntheticGeneration(stage=0) {
  const sample=syntheticRetrospective(),rounds=[],entries=[],identities={};
  for(let number=1;number<=(stage>=2?11:10);number++) {
    const matches=[];
    for(let i=0;i<10;i++) {
      const match=structuredClone(sample.data.previousRound.matches[i]);
      const completed=number<=9 || number===10 && (i<8 || stage>=1);
      const saved=number===9 && i<2 || number===10 && i>=8 || number===11;
      let day=new Date(Date.UTC(2026,7,7+(number-1)*7)).toISOString().slice(0,10);
      if(number===9) day='2026-10-09';
      if(number===10) day=i<8?'2026-10-17':'2026-10-18';
      if(number===11) day='2026-10-21';
      Object.assign(match,{id:`j1_2026_2027:club${number}_${i}:away${number}_${i}`,round:number,
        status:completed?'completed':'scheduled',kickoffAt:day+'T19:00:00+09:00',
        result:completed?{homeScore:2,awayScore:1}:null,prediction:saved?{
          source:'saved_pre_match',generatedAt:'2026-08-01T00:00:00Z',probabilities:{home:55,draw:25,away:20}}:null});
      identities[match.id]={id:String(100000+number*10+i),namespace:'jleague_match_page'};
      if((number<=9 || number===10 && i<8) && !saved) {
        entries.push({...structuredClone(sample.overlay.entries[0]),fixtureKey:match.id,round:number,matchDate:day,
          homeTeamId:match.homeTeam.id,awayTeamId:match.awayTeam.id,officialId:identities[match.id].id,result:structuredClone(match.result)});
      }
      matches.push(match);
    }
    rounds.push({number,label:`第${number}節`,kind:'previous',matches});
  }
  const observed=['2026-10-18T00:00:00Z','2026-10-18T13:00:00Z','2026-10-18T22:00:00Z'][stage];
  const data={...sample.data,updatedAt:observed,previousRound:structuredClone(rounds[stage>=2?9:8]),
    nextRound:{...structuredClone(rounds[stage>=2?10:9]),kind:stage>=2?'next':'current'}};
  const overlay={...sample.overlay,officialObservedAt:observed,officialRevision:String(stage+3).repeat(64),
    entries,historyRounds:rounds,officialIdentities:identities};
  return {schemaVersion:1,generationId:String(stage+5).repeat(64),sequence:stage+1,dashboard:data,overlay,
    status:{state:'ready',startedAt:null,finishedAt:null,lastSuccessAt:observed,errorCode:null,
      pollEnabled:true,pollSeconds:60,feedUpdatedAt:observed}};
}
