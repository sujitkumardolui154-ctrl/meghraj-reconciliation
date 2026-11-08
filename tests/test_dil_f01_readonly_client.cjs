"use strict";
const {test}=require("node:test");
const assert=require("node:assert/strict");
const fs=require("node:fs");
const vm=require("node:vm");
const source=fs.readFileSync("dashboard_source/dil_floating_assistant.js","utf8");
function harness(enabled, responder) {
  const elements={};
  function element(name) {
    return {name,hidden:false,disabled:false,value:"",textContent:"",children:[],
      attrs:{},events:{},style:{},
      setAttribute(k,v){this.attrs[k]=v},
      addEventListener(k,fn){this.events[k]=fn},
      appendChild(c){this.children.push(c)},
      focus(){},
      querySelector(k){return elements[k]},
      get scrollHeight(){return 100},
      set scrollTop(v){}
    };
  }
  const body=element("body"),head=element("head");
  const root=element("root");
  for(const k of [".dil-panel",".dil-launch",".dil-close",".dil-question",".dil-form",".dil-messages",".dil-send"]) elements[k]=element(k);
  root.querySelector=k=>elements[k];
  body.appendChild=c=>{if(c===root) elements["dil-assistant-root"]=root};
  const document={body,head,readyState:"complete",activeElement:element("focus"),
    createElement:tag=>tag==="aside"?root:element(tag),
    getElementById:id=>elements[id]||null};
  let calls=0;
  const fetch=async(...args)=>{calls++;return responder(...args)};
  const window={DIL_READONLY_QUERY_ENABLED:enabled};
  vm.runInNewContext(source,{document,window,fetch,AbortController,
    setTimeout,clearTimeout},{timeout:1000});
  const form=elements[".dil-form"],input=elements[".dil-question"],log=elements[".dil-messages"];
  return {submit:async q=>{input.value=q;await form.events.submit({preventDefault(){}})},
    messages:()=>log.children.map(x=>x.textContent),calls:()=>calls};
}
const valid={read_only:true,authorized:true,answer:"Verified synthetic invoice",evidence:[{source:"Invoice Details.",row_id:"synthetic-7"}]};
test("feature off never calls backend",async()=>{
  const h=harness(false,async()=>{throw Error("must not call")});
  await h.submit("invoice");assert.equal(h.calls(),0);
  assert.match(h.messages().at(-1),/not yet available/);
});
test("valid evidence renders answer and row citation",async()=>{
  const h=harness(true,async()=>({ok:true,headers:{get:()=>"application/json"},json:async()=>valid}));
  await h.submit("invoice");assert.equal(h.calls(),1);
  assert.match(h.messages().at(-2),/Verified synthetic/);
  assert.match(h.messages().at(-1),/synthetic-7/);
});
test("unauthorized result is rejected even with evidence",async()=>{
  const h=harness(true,async()=>({ok:true,headers:{get:()=>"application/json"},json:async()=>({...valid,authorized:false})}));
  await h.submit("invoice");assert.match(h.messages().at(-1),/Unable to verify/);
});
test("missing evidence is rejected",async()=>{
  const h=harness(true,async()=>({ok:true,headers:{get:()=>"application/json"},json:async()=>({...valid,evidence:[]})}));
  await h.submit("invoice");assert.match(h.messages().at(-1),/Unable to verify/);
});
test("HTTP denial is rejected",async()=>{
  const h=harness(true,async()=>({ok:false,status:403,headers:{get:()=> "application/json"}}));
  await h.submit("invoice");assert.match(h.messages().at(-1),/Unable to verify/);
});
test("request is same-origin POST with no-store and no redirects",async()=>{
  const h=harness(true,async(url,opts)=>{
    assert.equal(url,"/api/dil/query");assert.equal(opts.method,"POST");
    assert.equal(opts.credentials,"same-origin");assert.equal(opts.cache,"no-store");
    assert.equal(opts.redirect,"error");
    return {ok:true,headers:{get:()=>"application/json"},json:async()=>valid};
  });
  await h.submit("invoice");assert.equal(h.calls(),1);
});
test("script does not create extra dashboard tabs or write finance",()=>{
  assert.doesNotMatch(source,/fetch\s*\(\s*["']\/api\/(?:import\/apply|finance\/write)/);
  assert.match(source,/prefers-reduced-motion/);
  assert.match(source,/bubble\.textContent = message/);
});
