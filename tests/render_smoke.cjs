/* Node-only render smoke test; does not replace browser layout/E2E testing.
   Start server.py, then: node tests/render_smoke.cjs http://127.0.0.1:8000 */
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const assert=require('node:assert/strict');
const base=process.argv[2]||'http://127.0.0.1:8000';
const root=path.resolve(__dirname,'..');
(async()=>{
 const request=async route=>{const r=await fetch(base+route,{headers:{'X-Demo-Role':'business'}});assert.equal(r.status,200);return r.json();};
 const state=await request('/api/state'),demo=await request('/api/demo');
 const app={innerHTML:''},panel={innerHTML:''};
 const listeners={};
 const context=vm.createContext({console,setTimeout,clearTimeout,fetch:(url,opts)=>fetch(base+url,opts),
   localStorage:{getItem:()=>null,setItem:()=>{}},window:{scrollTo:()=>{}},
   document:{querySelector:s=>s==='#app'?app:s==='#rating-panel'?panel:null,addEventListener:(name,handler)=>{listeners[name]=handler;}},
   FormData:class{}, seedState:state,seedDemo:demo});
 const source=fs.readFileSync(path.join(root,'static/app.js'),'utf8').replace(/boot\(\);\s*$/,'');
 vm.runInContext(source,context);
 vm.runInContext('state=seedState;demo=seedDemo;',context);
 const run=code=>vm.runInContext(code,context);
 const cases=[
  ['catalog',"route='catalog';render()",'Идеялар іске айналады.'],
  ['builder-landing',"route='builder';builder=null;render()",'Алғашқы қадамнан бастаңыз'],
  ['builder-description',"startBuilder(true)",'Қандай мәселе бар?'],
 ];
 for(const [name,code,expected] of cases){run(code);assert.ok(app.innerHTML.includes(expected),name);}
 const ai=await fetch(base+'/api/analyze',{method:'POST',headers:{'Content-Type':'application/json','X-Demo-Role':'business'},body:JSON.stringify({description:demo.description,topic:demo.topic,answers:{}})}).then(r=>r.json());
 context.analysis=ai;
 run('builder.analysis=analysis;builder.step=2;render()');
 assert.ok((app.innerHTML.match(/id="answer-/g)||[]).length>=3,'three questions');
 run('builder.fields={...demo.answers};builder.step=3;render()');
 assert.equal((app.innerHTML.match(/data-confirm=/g)||[]).length,10,'ten editable confirmed fields');
 run("detailId=state.tasks[0].id;route='detail';render()");assert.ok(app.innerHTML.includes('Командалардың ұсыныстары'));
 run("route='proposals';render()");assert.ok(app.innerHTML.includes('Команданы таңдау'));
 run("route='teams';render()");assert.ok(app.innerHTML.includes('Qadam Lab'));
 run("route='demo';render()");assert.ok(app.innerHTML.includes('04:15–05:00'));
 run("role='student';route='catalog';render()");assert.ok(app.innerHTML.includes('id="team-select"'));
 run("route='detail';render()");assert.ok(app.innerHTML.includes('Ұсыныс беру'));
 run("filters.level='draft';filters.topic='';filters.search='';");
 assert.equal(run('filteredTasks().length'),1,'low score remains visible');
 run("filters.search='zzzzzzzzzz';");assert.ok(run('catalogCards()').includes('Міндет табылмады'));
 run("state.tasks[0].fields.title='<img src=x onerror=alert(1)>';filters.search='';filters.level='';");
 const escaped=run('catalogCards()');assert.ok(!escaped.includes('<img src=x'));assert.ok(escaped.includes('&lt;img'));
 assert.deepEqual(Object.keys(listeners).sort(),['change','click','input','submit']);
 await new Promise(resolve=>setTimeout(resolve,100));
 assert.ok(panel.innerHTML.includes('Дайындық рейтингі'));
 console.log('PASS: 10 page render states, 3+ questions, 10 editor fields, filters, XSS escaping and server rating.');
 console.log('Note: DOM events and visual layout require a real browser; this test uses minimal DOM substitutes.');
})().catch(error=>{console.error(error);process.exitCode=1;});
