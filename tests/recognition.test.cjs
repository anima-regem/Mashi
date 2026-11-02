const {test}=require("node:test");
const assert=require("node:assert/strict");
const fs=require("node:fs"), vm=require("node:vm");
const {sameCrop}=require("../mashi/static/review-state.js");

function scene(initial) {
  const elements=new Map(), calls=[], errors=[], messages=[];
  const $=id=>{if(!elements.has(id))elements.set(id,{hidden:false,value:"",checked:false,focus(){this.focused=true;}});return elements.get(id);};
  const region={id:"crop",active:true,label:"",confirmed:false,box:[0,0,30,40]};
  const context={window:{MashiReviewState:{sameCrop}},$,recognitionStatus:initial,busy:false,
    project:{id:"p",revision:1,regions:[region]},selected:region.id,
    generatedSelection:r=>r?.coordinate_space==="generated-canvas",url:()=>"/api/projects/p",
    showCodepoints(){context.codepointsShown=true;},saveCropDraft(){context.draft={label:$("label").value,confirmed:$("confirmed").checked};},
    message:text=>messages.push(text),render(){context.window.MashiRecognition.selection(context.current());},
    current:()=>context.project.regions.find(r=>r.id===context.selected),
    cropInputs:()=>({label:$("label").value,confirmed:$("confirmed").checked,box:region.box}),
    setProject:async doc=>{context.project=doc;return true;},
    api:async(path,options)=>{calls.push([path,options]);return {json:async()=>context.reply};},
    work:async callback=>{context.busy=true;try{await callback();}catch(error){errors.push(error.message);}finally{context.busy=false;context.window.MashiRecognition.refreshControls();}}};
  vm.createContext(context);
  vm.runInContext(fs.readFileSync(require.resolve("../mashi/static/recognition.js"),"utf8"),context);
  return {$,context,calls,errors,messages};
}

test("recognition availability exposes setup only when useful and recheck can enable suggestions",async()=>{
  const ui=scene({available:false,can_setup:false,reason:"Recognition is not installed."});
  assert.equal(ui.$("ocr").hidden,true);assert.equal(ui.$("ocr-setup").hidden,true);
  ui.context.reply={available:false,can_setup:true,reason:"Malayalam data is missing."};
  await ui.$("ocr-check").onclick();
  assert.equal(ui.$("ocr-setup").hidden,false);assert.equal(ui.$("ocr-setup-note").hidden,false);
  ui.context.reply={available:true,can_setup:false,reason:"Review each crop."};
  await ui.$("ocr-setup").onclick();
  assert.equal(ui.$("ocr").hidden,false);assert.equal(ui.$("ocr").disabled,false);
  assert.equal(ui.$("ocr-setup").hidden,true);
  assert.equal(ui.calls[1][0],"/api/ocr/setup");
});

test("a failed setup remains unavailable and permits retry without changing the page",async()=>{
  const ui=scene({available:false,can_setup:true,reason:"Data missing."}), before=ui.context.project;
  ui.context.api=async path=>{if(path.endsWith("setup"))throw Error("Connection failed.");return {json:async()=>({available:false,can_setup:true,reason:"Data missing."})};};
  await ui.$("ocr-setup").onclick();
  assert.deepEqual(ui.errors,["Connection failed."]);
  assert.equal(ui.context.project,before);assert.equal(ui.$("ocr").hidden,true);
  assert.equal(ui.$("ocr-setup").disabled,false);
});

test("new word proposals select the first correction crop and never confirm or label it",async()=>{
  const ui=scene({available:true}), proposal={id:"word",active:true,source:"ocr-word",label:"",confirmed:false,box:[0,0,30,40],suggestion:{raw_text:"ന്‍"}};
  ui.context.reply={...ui.context.project,revision:2,regions:[...ui.context.project.regions,proposal]};
  await ui.$("ocr").onclick();
  assert.equal(ui.context.selected,"word");assert.equal(proposal.label,"");assert.equal(proposal.confirmed,false);
  assert.match(ui.messages.at(-1),/1 word suggestion/);
  ui.$("confirmed").checked=true;
  ui.$("use-suggestion").onclick();
  assert.equal(ui.$("label").value,"ന്‍");assert.equal(ui.$("confirmed").checked,false);
  assert.deepEqual(ui.context.draft,{label:"ന്‍",confirmed:false});
  assert.equal(ui.$("label").focused,true);assert.equal(ui.calls.length,1,"Copying never saves or confirms");
});

test("no-word and dirty-form paths preserve input and give useful manual recovery",async()=>{
  const ui=scene({available:true});
  ui.$("label").value="ക";
  await ui.$("ocr").onclick();
  assert.equal(ui.calls.length,0);assert.match(ui.errors[0],/Save or discard/);
  ui.$("label").value="";ui.context.reply=ui.context.project;
  await ui.$("ocr").onclick();
  assert.match(ui.messages.at(-1),/No words found.*manually/);
  assert.equal(ui.context.selected,"crop");
  for(const raw_text of ["word", "ക ക", "ക".repeat(33)]) {
    ui.context.window.MashiRecognition.selection({active:true,suggestion:{raw_text}});
    assert.equal(ui.$("use-suggestion").hidden,true);
  }
});
