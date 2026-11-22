// Optional development-time generator: node scripts/build_manifest.js
// Reads years/*/index.html and writes exam_manifest.json.
const fs=require('fs'),vm=require('vm'),path=require('path');
const root=path.resolve(__dirname,'..');
const yearsDir=path.join(root,'years');
let all=[];
for(const year of fs.existsSync(yearsDir)?fs.readdirSync(yearsDir).sort():[]){
 const file=path.join(yearsDir,year,'index.html'); if(!/^\d{4}$/.test(year)||!fs.existsSync(file))continue;
 const html=fs.readFileSync(file,'utf8'),script=html.match(/<script>([\s\S]*?)<\/script>/)?.[1];
 if(!script){console.warn('Skipping no script',file);continue}
 const start=script.indexOf('const QUESTIONS=['),end=script.indexOf('\nlet current=',start);
 if(start<0||end<0){console.warn('Skipping unknown questions layout',file);continue}
 let helpers=script.slice(end,script.indexOf('function capture',end));
 helpers=helpers.replace(/let current=0;[\s\S]*?let responses=QUESTIONS\.map\([\s\S]*?\);/,'');
 const ctx={};vm.runInNewContext(script.slice(start,end)+'\n'+helpers+'\n globalThis.extracted=QUESTIONS;',ctx,{timeout:2500});
 for(const q of ctx.extracted){
  const fields=Array.from(q.fields||[],f=>({id:String(f.id),label:String(f.label),type:String(f.type||'text'),placeholder:String(f.placeholder||'')}));
  const model=String(q.model||'');
  const rec={label:q.label,year,original:q.original||'',points:q.points||'',intro:q.intro||'',fields,images:Array.from(q.images|| (q.image?[q.image]:[])),extraInstruction:q.extraInstruction||'',incomplete:!!q.incomplete,grade_cases:[]};
  // Collect independent candidate exact inputs from the original checker.
  const tokens=[...new Set([
    ...model.match(/\b[a-zA-Z][a-zA-Z+-]*\b/g)||[],
    ...model.match(/\[[+-][a-zA-Z]+\]/g)||[],
    ...model.match(/\/[æɪəʊɔʌɛɑɒuːiː]+\//g)||[],
    ...model.match(/[①②③④⑤]/g)||[],
    ...'12345'.split(''),...'abcd'.split(''),
    ...['a,b','a,c','a,d','b,c','b,d','c,d'],
    ...['+anterior','-anterior','+sonorant','-sonorant','+consonantal','-consonantal','rhyme','rhythm','onset','coda','allophone','geminates','stressed','unstressed','penultimate','trochaic','æ','n','ŋ','ɪ','velars','suffixes']
  ])];
  // Reasonable search, prioritizing model terms; objective fields generally have 1-2 values.
  const candidates=tokens.filter(x=>x.length<45).slice(0,120);
  const empty=Object.fromEntries(fields.map(f=>[f.id,'']));
  let sample;try{sample=q.check(empty)}catch(e){sample=[]}
  const objective=Array.from(sample,(x,i)=>x.status!=='review'?i:-1).filter(i=>i>=0);
  if(objective.length){
   // Record smallest set of field values that satisfies each objective item.
   const cases=[];
   function tryValues(vals){let out;try{out=q.check(vals)}catch(e){return}if(!out)return;
    for(const idx of objective){if(out[idx]?.status==='ok')cases.push({index:idx,values:{...vals}})}
   }
   for(const f of fields){for(const c of candidates){let v={...empty,[f.id]:c};tryValues(v)}}
   const objFields=fields.filter(f=>f.type!=='textarea');
   if(objFields.length>=2 && objFields.length<=3){
     for(const a of 'abcd')for(const b of 'abcd')if(a!==b){let v={...empty,[objFields[0].id]:a,[objFields[1].id]:b};tryValues(v)}
   }
   // Keep only cases with minimal populated value count; capture alternatives for the same keys.
   const scored=cases.map(c=>({...c,n:Object.values(c.values).filter(Boolean).length}));
   for(const idx of objective){
     const possible=scored.filter(c=>c.index===idx);if(!possible.length)continue;
     const n=Math.min(...possible.map(c=>c.n));
     const unique=new Map();
     for(const c of possible.filter(c=>c.n===n)){
       const v=Object.fromEntries(Object.entries(c.values).filter(([k,x])=>x));
       const key=JSON.stringify(v);unique.set(key,v);
     }
     rec.grade_cases.push({index:idx,label:String(sample[idx].label||''),accepted:[...unique.values()].slice(0,80)});
   }
  }
  rec.grade_labels=Array.from(sample,x=>({label:x.label||'',review:x.status==='review'}));
  // Written-answer fields can return 'no' for blank input and 'review' for filled input.
  if(fields.some(f=>f.type==='textarea')){
    const full=Object.fromEntries(fields.map(f=>[f.id, f.type==='textarea'?'A written explanation':'']));
    try{const filled=q.check(full);filled.forEach((x,i)=>{if(x.status==='review' && rec.grade_labels[i])rec.grade_labels[i].review=true});}catch(e){}
  }
  if(q.label==='2011-2'){rec.grade_cases=[{index:0,label:'Selected statements',accepted:[{a:'a,c,d'}]}]}
  if(q.label==='2024-3'){rec.grade_cases=[{index:0,label:'TWO words',accepted:[{a:'a,c'}]}];if(rec.grade_labels[1])rec.grade_labels[1].review=true}

  all.push(rec);
 }
}
fs.writeFileSync(path.join(root,'exam_manifest.json'),JSON.stringify(all,null,2));
console.log('Exported',all.length,'questions in',new Set(all.map(q=>q.year)).size,'years');
console.log('Objective checks:',all.reduce((a,q)=>a+q.grade_cases.length,0));
