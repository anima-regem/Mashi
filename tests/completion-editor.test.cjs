const {test}=require("node:test");
const assert=require("node:assert/strict");
const fs=require("node:fs");
const vm=require("node:vm");
const {LatestRequest}=require("../mashi/static/review-state.js");

test("generated editor stays disabled until its current raster loads; stale loads and failures cannot enable saving",async()=>{
  const elements=new Map(), images=[], loaded=[], errors=[], saveControl={disabled:false};
  const element=id=>{
    if(!elements.has(id))elements.set(id,{disabled:false,checked:false,querySelectorAll:()=>id==="vector-form"?[saveControl]:[],replaceChildren(){}});
    return elements.get(id);
  };
  class DeferredImage {
    constructor(){this.promise=new Promise((resolve,reject)=>{this.resolve=resolve;this.reject=reject;});images.push(this);}
    decode(){return this.promise;}
  }
  const context={
    window:{MashiReviewState:{LatestRequest},MashiOutline:{load:(...args)=>loaded.push(args)}},
    $:element,project:null,busy:false,selected:null,outlineReady:false,
    current:()=>({coordinate_space:"generated-canvas"}),generatedSelection:()=>true,
    Image:DeferredImage,url:()=>"/api/projects/p",message:text=>errors.push(text),
  };
  vm.createContext(context);
  vm.runInContext(fs.readFileSync(require.resolve("../mashi/static/completion.js"),"utf8"),context);
  context.project={id:"p",image:{canonical_sha256:"page"}};
  const item={id:"candidate",revision:1,raster_sha256:"raster",review_state:"pending",
    vector:{paths:["closed"],baseline:19,scale:31.25,advance:800},
    generation:{model:{terms:{checkpoint_source_known:true}}}};
  context.selected=item.id;
  const first=context.window.MashiCompletion.loadEditor(item);
  const repeated=context.window.MashiCompletion.loadEditor(item);
  assert.equal(context.outlineReady,false);
  assert.equal(saveControl.disabled,true);
  images[0].resolve(); await first;
  assert.equal(loaded.length,0);
  assert.equal(context.outlineReady,false);
  images[1].resolve(); await repeated;
  assert.equal(loaded.length,1);
  assert.equal(context.outlineReady,true);
  assert.equal(saveControl.disabled,false);
  assert.equal(element("baseline").value,19);
  assert.equal(loaded[0][1].image.canonical_sha256,"raster");
  await context.window.MashiCompletion.loadEditor(item);
  assert.equal(images.length,2);
  const newer={...item,id:"newer"};context.selected=newer.id;
  const late=context.window.MashiCompletion.loadEditor(newer);
  context.window.MashiCompletion.clearEditorIdentity();context.selected="captured";
  images[2].resolve();await late;
  assert.equal(loaded.length,1);
  assert.equal(context.outlineReady,false);
  context.selected=newer.id;
  const failed=context.window.MashiCompletion.loadEditor(newer);
  images[3].reject(Error("decode failed"));await failed;
  assert.equal(context.outlineReady,false);
  assert.match(errors[0],/Select the candidate again to retry/);
  const retry=context.window.MashiCompletion.loadEditor(newer);
  images[4].resolve();await retry;
  assert.equal(context.outlineReady,true);
  assert.equal(loaded.length,2);
});
