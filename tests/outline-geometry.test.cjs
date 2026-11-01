const {test}=require("node:test");
const assert=require("node:assert/strict");
const G=require("../mashi/static/outline-geometry.js");
test("closed outer and counter contours retain their path grouping and winding",()=>{
  const paths=["M0 0L100 0L100 100L0 100ZM25 25L25 75L75 75L75 25Z"];
  const c=G.parse(paths);assert.equal(c.length,2);assert.equal(G.serialize(c).length,1);
  const area=c=>{const points=[c.start,...c.segments.map(s=>s.to)];return points.reduce((v,p,i)=>{const q=points[(i+1)%points.length];return v+p[0]*q[1]-q[0]*p[1];},0)/2;};
  assert.ok(area(c[0])>0);assert.ok(area(c[1])<0);
  G.moveAnchor(c[0],1,2,3);const restored=G.parse(G.serialize(c));
  assert.ok(area(restored[0])>0);assert.equal(area(restored[1]),area(c[1]));
});
test("relative and smooth commands become editable absolute Bézier controls",()=>{
  const [c]=G.parse(["m10 10 c0 10 10 10 10 0 s10 -10 10 0 q5 10 10 0 t10 0 h10 v20 z"]);
  assert.deepEqual(c.segments[1].c1,[20,0]);assert.deepEqual(c.segments[3].c1,[45,0]);
  assert.deepEqual(c.segments.at(-1).to,[60,30]);
  assert.deepEqual(G.parse(G.serialize([c])),[c]);
});
test("moving a closing anchor also moves its adjoining controls without opening the contour",()=>{
  const [c]=G.parse(["M10 10C20 0 40 0 50 10C50 40 10 40 10 10Z"]);
  assert.equal(c.segments.at(-1).to,c.start);assert.equal(G.anchors(c).length,2);
  G.moveAnchor(c,0,3,4);
  assert.deepEqual(c.start,[13,14]);assert.deepEqual(c.segments[0].c1,[23,4]);assert.deepEqual(c.segments[1].c2,[13,44]);
  assert.equal(G.parse(G.serialize([c]))[0].segments.at(-1).to[0],13);
});
test("unsafe, nonfinite and open geometry is rejected",()=>{
  for(const p of ["<svg></svg>","M0 0L1e300 0Z","M0 0L10 10","M0 0A10 10 0 0 0 10 10Z"])
    assert.throws(()=>G.parse([p]));
});
