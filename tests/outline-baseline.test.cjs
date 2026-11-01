const {test}=require("node:test");
const assert=require("node:assert/strict");
const fs=require("node:fs");
const vm=require("node:vm");
const G=require("../mashi/static/outline-geometry.js");

// Execute the actual editor's keyboard/pointer handlers with identity SVG
// coordinates. No browser layout or duplicated metric-update logic is mocked.
function editor(){
  class Node {
    constructor(tag){this.tag=tag;this.attrs={};this.children=[];this.isConnected=true;this.checked=true;this.value="0.3";}
    setAttribute(key,value){this.attrs[key]=String(value);}
    getAttribute(key){return this.attrs[key];}
    append(...nodes){this.children.push(...nodes);}
    replaceChildren(...nodes){this.children=nodes;}
    getBoundingClientRect(){return {width:800,height:400};}
    setPointerCapture(){}
    createSVGPoint(){return {x:0,y:0,matrixTransform(){return {x:this.x,y:this.y};}};}
    getScreenCTM(){return {inverse:()=>({})};}
    getContext(){return {drawImage(){}};}
    toDataURL(){return "data:image/png;base64,synthetic";}
    querySelector(){return null;}
  }
  const elements=new Map();
  const $=id=>{if(!elements.has(id))elements.set(id,new Node("control"));return elements.get(id);};
  const context={window:{MashiGeometry:G,addEventListener(){}},
    document:{createElement:tag=>new Node(tag),createElementNS:(_,tag)=>new Node(tag),activeElement:null},
    $,busy:false,project:null,remember:()=>true,recall:()=>null,forget(){},message(){}};
  vm.createContext(context);
  vm.runInContext(fs.readFileSync(require.resolve("../mashi/static/outline.js"),"utf8"),context);
  const svg=()=>$("vector-preview").children[0];
  const baseline=()=>svg().children.find(n=>n.attrs["data-testid"]==="outline-baseline");
  return {context,$,svg,baseline};
}

for(const fixture of [{name:"ink wholly above",height:16,baseline:21,top:24},
                      {name:"ink wholly below",height:8,baseline:-8,top:53}]){
  test(`${fixture.name} the baseline: visual keyboard and pointer edits retain outside-ink metrics`,()=>{
    const ui=editor();
    const vector={width:14,height:fixture.height,baseline:fixture.baseline,scale:31.25,advance:800,
      paths:[`M0 0L14 0L14 ${fixture.height}L0 ${fixture.height}Z`],edited:false};
    const region={id:"generated",revision:1,provenance:"model-generated",vector,
      box:[41,fixture.top,55,fixture.top+fixture.height]};
    ui.context.window.MashiOutline.load(region,{id:"p",image:{canonical_sha256:"synthetic"}},{});
    const view=ui.svg().attrs.viewBox.split(" ").map(Number);
    const event={key:"ArrowUp",preventDefault(){}};
    ui.baseline().onkeydown(event);
    assert.equal(Number(ui.$("baseline").value),fixture.baseline-1);
    assert.equal(Number(ui.baseline().attrs["aria-valuenow"]),fixture.baseline-1);
    ui.baseline().onpointerdown({pointerId:1,preventDefault(){}});
    ui.svg().onpointermove({clientX:0,clientY:fixture.baseline+2.5});
    ui.svg().onpointerup();
    assert.equal(Number(ui.$("baseline").value),fixture.baseline+2.5);
    assert.equal(Number(ui.baseline().attrs["aria-valuenow"]),fixture.baseline+2.5);
    ui.$("outline-undo").onclick();
    assert.equal(Number(ui.$("baseline").value),fixture.baseline-1);
    ui.$("outline-undo").onclick();
    assert.equal(Number(ui.$("baseline").value),fixture.baseline);
    ui.$("outline-redo").onclick();
    assert.equal(Number(ui.$("baseline").value),fixture.baseline-1);
    assert.ok(view[1]<Math.min(0,fixture.baseline));
    assert.ok(view[1]+view[3]>Math.max(fixture.height,fixture.baseline));
    assert.ok(Number(ui.baseline().attrs["aria-valuemin"])<fixture.baseline);
    assert.ok(Number(ui.baseline().attrs["aria-valuemax"])>fixture.baseline);
  });
}
