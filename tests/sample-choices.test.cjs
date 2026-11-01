const {test}=require("node:test");
const assert=require("node:assert/strict");
const fs=require("node:fs");
const vm=require("node:vm");

function scene(group){
  class Element {
    constructor(tag="div"){this.tag=tag;this.children=[];this.attributes={};this.value="";}
    append(...nodes){this.children.push(...nodes);}
    replaceChildren(...nodes){this.children=nodes;}
    setAttribute(key,value){this.attributes[key]=value;}
    querySelectorAll(){return [];}
  }
  const elements=new Map(),updates=[];
  const $=id=>{if(!elements.has(id))elements.set(id,new Element());return elements.get(id);};
  const context={window:{},document:{createElement:tag=>new Element(tag)},$,features:{multi_page:true},busy:false,project:null,
    url:()=>"/api/projects/font",work:fn=>fn(),
    update:async(path,options)=>{
      updates.push({path,input:options.json});
      const g=context.project.sample_groups[0],s=g.samples[0];
      g.choice={page_id:s.page_id,region_id:s.region_id,revision:s.revision,vector_sha256:s.vector_sha256};
      g.needs_choice=false;g.stale_choice=false;g.reason=null;
      context.project.revision++;context.window.MashiProjects.sync();
    },
  };
  vm.createContext(context);vm.runInContext(fs.readFileSync(require.resolve("../mashi/static/studio-projects.js"),"utf8"),context);
  context.project={id:"font",revision:10,page_id:"page",page_name:"Sheet",pages:[{id:"page",name:"Sheet"}],sample_groups:[group]};
  return {$,updates,sync:()=>context.window.MashiProjects.sync(),context};
}
const sample={page_id:"page",region_id:"current",revision:3,vector_sha256:"a".repeat(64),page_name:"Sheet",kind:"captured",number:1,provenance:"observed"};
const signature={page_id:sample.page_id,region_id:sample.region_id,revision:sample.revision,vector_sha256:sample.vector_sha256};
const children=(row,tag)=>row.children.filter(e=>e.tag===tag);
const text=node=>[node.textContent||"",...node.children.map(text)].join(" ");

for(const [name,change] of [["missing selected sample",{region_id:"removed"}],["old selected revision",{revision:2}],["changed vector hash",{vector_sha256:"b".repeat(64)}]]){
  test(`${name} stays unselected and recoverable even if the supplied needs-choice flag is false`,async()=>{
    const ui=scene({label:"ക",samples:[sample],choice:{...signature,...change},needs_choice:false});
    assert.doesNotThrow(ui.sync);
    let row=ui.$("font-sample-list").children[0];
    const select=children(row,"select")[0];
    assert.ok(select,"An explicit choice must remain available");assert.equal(select.value,"");
    assert.ok(children(row,"button").every(button=>button.hidden));
    assert.equal(ui.updates.length,0,"Rendering cannot substitute or save a sample");
    assert.match(ui.$("font-samples-summary").textContent,/1 needs review/);
    select.value="0";await select.onchange();
    assert.equal(ui.updates[0].input.region_id,"current");
    assert.equal(ui.updates[0].input.sample_revision,3);
    row=ui.$("font-sample-list").children[0];
    assert.ok(children(row,"button").some(button=>!button.hidden));
  });
}

test("a choice with no eligible sample renders capture guidance and does not invent a replacement",()=>{
  const ui=scene({label:"ക",samples:[],choice:signature,needs_choice:true,stale_choice:true});
  assert.doesNotThrow(ui.sync);
  const row=ui.$("font-sample-list").children[0];
  assert.equal(children(row,"select").length,0);
  assert.ok(children(row,"button").every(button=>button.hidden));
  assert.match(text(row),/Capture and trace a sample/);
  assert.equal(ui.updates.length,0);
});
