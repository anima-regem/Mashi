const {test}=require("node:test");
const assert=require("node:assert/strict");
const fs=require("node:fs");
const vm=require("node:vm");
const {LatestRequest}=require("../mashi/static/review-state.js");
const tick=()=>new Promise(setImmediate);
const deferred=()=>{let resolve;const promise=new Promise(r=>resolve=r);return {promise,resolve};};

test("page preparation ignores late images and preview responses from another page",async()=>{
  const elements=new Map(), images=[], previews=[], draws=[];
  const $=id=>{
    if(!elements.has(id))elements.set(id,{open:true,checked:false,value:"",children:[],
      replaceChildren(){this.children=[];},append(n){this.children.push(n);},removeAttribute(){},querySelectorAll:()=>[$("prep-apply")],
      getContext:()=>({drawImage:image=>draws.push(image.src),scale(){}}),
    });return elements.get(id);
  };
  class PendingImage {
    constructor(){this.pending=deferred();this.complete=true;this.width=200;this.height=300;this.naturalWidth=200;images.push(this);}
    decode(){return this.pending.promise;}
  }
  const context={window:{addEventListener(){}},document:{createElement:()=>({append(){},setAttribute(){}})},
    $,project:null,busy:false,Image:PendingImage,setTimeout,clearTimeout,message(){},work:fn=>fn(),
    url:()=>`/api/projects/${context.project.id}`,
    pageURL:path=>path+"?page_id="+context.project.page_id,
    URL:{createObjectURL:blob=>blob.tag,revokeObjectURL(){}},
    api:path=>{const pending=deferred();previews.push({path,pending});return pending.promise;},
  };
  vm.createContext(context);vm.runInContext(fs.readFileSync(require.resolve("../mashi/static/capture.js"),"utf8"),context);
  const page=id=>({id:"font",page_id:id,image:{canonical_sha256:id},preparation_history:[]});
  context.project=page("a");const lateImage=context.window.MashiCapture.load();
  context.project=page("b");const first=context.window.MashiCapture.load();
  assert.equal($("prep-apply").disabled,true);
  images[1].pending.resolve();await tick();
  assert.equal($("prep-apply").disabled,false);
  context.project=page("c");const current=context.window.MashiCapture.load();
  images[2].pending.resolve();await tick();
  const response=tag=>({blob:async()=>({tag}),headers:{get:()=>"300"}});
  previews[1].pending.resolve(response("current-preview"));await current;
  previews[0].pending.resolve(response("stale-preview"));await first;
  images[0].pending.resolve();await lateImage;
  assert.equal($("prep-preview").src,"current-preview");
  assert.equal(images[0].src,"/api/projects/font/source-image?page_id=a");
  assert.ok(draws.every(path=>!path.endsWith("page_id=a")));
  assert.equal(previews.length,2);
});

test("saved typography is shared across pages; a newer saved revision supersedes an old browser draft",()=>{
  const elements=new Map(), saved=new Map();
  const $=id=>{
    if(!elements.has(id))elements.set(id,{value:"",checked:false,required:true,reportValidity:()=>true,
      replaceChildren(){},classList:{remove(){}},
    });return elements.get(id);
  };
  const context={window:{MashiReviewState:{LatestRequest}},document:{},$,project:null,busy:false,
    remember:(key,value)=>{saved.set(key,value);return true;},recall:key=>saved.get(key),forget:key=>saved.delete(key),
  };
  vm.createContext(context);vm.runInContext(fs.readFileSync(require.resolve("../mashi/static/proof.js"),"utf8"),context);
  context.project={id:"font",page_id:"a",revision:1,typography_revision:1,proof_text:"ന്‍ ന്‌",typography:{family_name:"Saved Font",space_advance:543}};
  context.window.MashiProof.sync();
  assert.equal($("proof-text").value,"ന്‍ ന്‌");
  assert.equal(context.window.MashiProof.projectSettings().options.space_advance,543);
  $("proof-text").value="Unapplied draft";$("proof-form").oninput();
  context.project={...context.project,page_id:"b"};context.window.MashiProof.sync();
  assert.equal($("proof-text").value,"Unapplied draft");
  context.project={...context.project,revision:2,typography_revision:2,proof_text:"ക"};context.window.MashiProof.sync();
  assert.equal($("proof-text").value,"ക");
  assert.equal(saved.size,1);
});
