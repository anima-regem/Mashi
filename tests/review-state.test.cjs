const {test}=require("node:test");
const assert=require("node:assert/strict");
const {LatestRequest}=require("../mashi/static/review-state.js");
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
