const {test}=require("node:test");
const assert=require("node:assert/strict");
const {LatestRequest,sameCrop,traceIssue}=require("../mashi/static/review-state.js");
const deferred=()=>{let resolve,reject;const promise=new Promise((a,b)=>{resolve=a;reject=b;});return {promise,resolve,reject};};
test("late proof or image response cannot replace a newer revision",async()=>{
  const state=new LatestRequest(), first=deferred(), second=deferred(), accepted=[];
  const a=state.run(()=>first.promise,x=>accepted.push(x),e=>{throw e;});
  const b=state.run(()=>second.promise,x=>accepted.push(x),e=>{throw e;});
  second.resolve("new image + metadata"); await b;
  first.resolve("stale image + metadata"); await a;
  assert.deepEqual(accepted,["new image + metadata"]);
});
test("cancel ignores late success and failure; retry can succeed",async()=>{
  const state=new LatestRequest(), late=deferred(), accepted=[], errors=[];
  const pending=state.run(()=>late.promise,x=>accepted.push(x),e=>errors.push(e));
  state.cancel(); late.reject(Error("late failure"));await pending;
  assert.deepEqual(errors,[]); assert.deepEqual(accepted,[]);
  await state.run(()=>Promise.reject(Error("compiler failure")),()=>{},e=>errors.push(e.message));
  await state.run(()=>Promise.resolve("retry"),x=>accepted.push(x),()=>{});
  assert.deepEqual(errors,["compiler failure"]);assert.deepEqual(accepted,["retry"]);
});

test("trace waits for confirmed saved input, including after recovering an unsaved crop draft",()=>{
  let region={active:true,label:"",confirmed:false,box:[0,10,90,100]};
  let form={label:"",confirmed:false,box:["0","10","90","100"]};
  assert.match(traceIssue(region,form),/Confirm and save/);
  form={...form,label:"ക",confirmed:true};
  assert.match(traceIssue(region,form),/Save the label and crop/);
  region={...region,label:form.label,confirmed:true};
  assert.equal(traceIssue(region,form),"");
  const recovered={...form,box:["5","10","90","100"]};
  assert.match(traceIssue(region,recovered),/Save/);
  assert.equal(traceIssue(region,{...form}),"","Discarding the draft restores readiness");
  region={...region,box:recovered.box.map(Number)};
  assert.equal(traceIssue(region,recovered),"","Saving the changed bounds permits tracing them");
});

test("empty/invalid bounds and exact Unicode changes cannot be mistaken for saved crop data",()=>{
  const region={active:true,label:"ന്‍",confirmed:true,box:[0,10,90,100]};
  const form={label:region.label,confirmed:true,box:["0","10","90","100"]};
  for(const value of ["", " ", "NaN", "0.5", "Infinity"])
    assert.equal(sameCrop(region,{...form,box:[value,...form.box.slice(1)]}),false);
  for(const label of ["ൻ", "ന്‌"])
    assert.match(traceIssue(region,{...form,label}),/Save/);
  assert.equal(sameCrop(region,{...form,box:["0.0","10","90","100"]}),true);
  assert.equal(sameCrop(region,{...form,box:[...region.box]}),true,"Older numeric draft bounds remain compatible");
  assert.match(traceIssue({...region,coordinate_space:"generated-canvas"},form),/Choose a crop/);
  assert.match(traceIssue(null,form),/Choose a crop/);
});
