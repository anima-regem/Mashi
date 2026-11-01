const {test}=require("node:test");
const assert=require("node:assert/strict");
const fs=require("node:fs");
const vm=require("node:vm");
const {LatestRequest}=require("../mashi/static/review-state.js");
const tick=()=>new Promise(setImmediate);
const deferred=()=>{let resolve;const promise=new Promise(r=>resolve=r);return {promise,resolve};};

async function scene(initial,suggestions=[]){
  class Element {
    constructor(){this.value="";this.children=[];this.dataset={};this.classList={toggle(){}};}
    append(...nodes){this.children.push(...nodes);}
    replaceChildren(...nodes){this.children=nodes;}
    querySelectorAll(){return [];}
  }
  const elements=new Map(),loads=[];
  const $=id=>{if(!elements.has(id))elements.set(id,new Element());return elements.get(id);};
  let capability=initial;
  const response=value=>({json:async()=>value});
  const context={window:{MashiReviewState:{LatestRequest}},document:{createElement:()=>new Element()},
    $,project:null,busy:false,current:()=>null,generatedSelection:()=>false,url:()=>"/api/projects/p",
    crypto:{randomUUID:()=>"11111111-1111-1111-1111-111111111111"},
    api:async path=>{
      if(path==="/api/completion/capabilities")return response(capability);
      if(path.endsWith("/load")){const load=deferred();loads.push(load);return load.promise;}
      if(path.endsWith("/cancel"))return response({canceled:true});
      if(path.endsWith("/unload")){capability={...capability,loaded:false,model:null};return response(capability);}
      throw Error(path);
    }};
  vm.createContext(context);
  vm.runInContext(fs.readFileSync(require.resolve("../mashi/static/completion.js"),"utf8"),context);
  context.project={id:"p",revision:1,image:{canonical_sha256:"page"},regions:[],completion_suggestions:suggestions};
  context.window.MashiCompletion.sync();await tick();
  return {$,loads,loaded(){capability={...capability,loaded:true,model:{labels:[]}};return response(capability);}};
}

test("model controls show only available actions; cancellation suppresses a late load and permits retry",async()=>{
  const ui=await scene({available:true,configured:true,loaded:false,reason:"Suggestions are off."});
  assert.equal(ui.$("completion-actions").hidden,false);
  assert.equal(ui.$("completion-load").hidden,false);
  assert.equal(ui.$("completion-unload").hidden,true);
  assert.equal(ui.$("completion-cancel").hidden,true);
  assert.equal(ui.$("completion-quality").hidden,false);
  const pending=ui.$("completion-load").onclick();await tick();
  assert.equal(ui.$("completion-load").hidden,true);
  assert.equal(ui.$("completion-cancel").hidden,false);
  ui.$("completion-cancel").onclick();await tick();
  ui.loads[0].resolve({json:async()=>({available:true,loaded:true,model:{labels:[]}})});await pending;
  assert.equal(ui.$("completion-load").hidden,false);
  assert.equal(ui.$("completion-unload").hidden,true);
  const retry=ui.$("completion-load").onclick();await tick();
  ui.loads[1].resolve(ui.loaded());await retry;
  assert.equal(ui.$("completion-load").hidden,true);
  assert.equal(ui.$("completion-unload").hidden,false);
  assert.equal(ui.$("completion-cancel").hidden,true);
  await ui.$("completion-unload").onclick();
  assert.equal(ui.$("completion-load").hidden,false);
  assert.equal(ui.$("completion-unload").hidden,true);
});

test("unavailable suggestions show no inert model controls",async()=>{
  const ui=await scene({available:false,configured:false,loaded:false,reason:"Configure SHA-256 and install the completion extra."});
  assert.equal(ui.$("completion-actions").hidden,true);
  assert.equal(ui.$("completion-load").hidden,true);
  assert.equal(ui.$("completion-cancel").hidden,true);
  assert.equal(ui.$("completion-quality").hidden,true);
  assert.match(ui.$("completion-capability").textContent,/unavailable/);
  assert.doesNotMatch(ui.$("completion-capability").textContent,/install|SHA-256|configure/i);
});

test("unverified output rights stay visible beside the affected candidate",async()=>{
  const ui=await scene({available:false,loaded:false},[{
    id:"unknown",label:"മ",revision:1,review_state:"pending",vector:{},
    generation:{image_sha256:"page",observations:[],model:{terms:{checkpoint_source_known:false}}},
    vectorization:{method:"vtracer-0.6.12"},
  }]);
  const text=node=>[node.textContent||"",...node.children.map(text)].join(" ");
  assert.match(text(ui.$("completion-suggestions")),/Font export is blocked.*source rights are unverified/);
  assert.equal(ui.$("completion-quality").hidden,false);
});

test("review cards hide actions that do not apply to accepted or rejected forms",async()=>{
  const ui=await scene({available:false,loaded:false},["accepted","rejected"].map((state,index)=>({
    id:String(index),label:"മ",revision:1,review_state:state,vector:{},
    generation:{image_sha256:"page",observations:[],model:{terms:{checkpoint_source_known:true}}},
    vectorization:{method:"vtracer-0.6.12"},
  })));
  const [accepted,rejected]=ui.$("completion-suggestions").children;
  const actions=card=>card.children.find(node=>node.className==="actions").children;
  assert.equal(actions(accepted)[0].hidden,true);
  assert.equal(actions(accepted)[1].hidden,false);
  assert.equal(actions(rejected)[0].hidden,true);
  assert.equal(actions(rejected)[1].hidden,true);
  assert.equal(actions(rejected)[2].textContent,"Review again");
});
