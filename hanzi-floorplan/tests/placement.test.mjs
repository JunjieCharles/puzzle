import test from 'node:test';
import assert from 'node:assert/strict';
import { placements,transform,searchPlacement } from '../public/placement.mjs';
import { allocate,cellInk } from '../public/floorplan.mjs';

function sample(size,points,count) {
  const rgba=new Uint8ClampedArray(size*size*4).fill(255),labels=new Int32Array(size*size);
  for(const [x,y,k] of points) {const p=y*size+x;labels[p]=k;rgba[p*4]=rgba[p*4+1]=rgba[p*4+2]=0;}
  return {rgba,labels,size,count};
}
test('enumerates a bounded grid including the unchanged baseline first',()=>{
  const grid=placements(.02,4,1);assert.equal(grid.length,243);
  assert.deepEqual(grid[0],{factor:1,dx:0,dy:0});
  assert.ok(grid.every(p=>p.factor>=.98 && p.factor<=1.02 && Math.abs(p.dx)<=4 && Math.abs(p.dy)<=4));
  for(let dx=-4;dx<=4;dx++) for(let dy=-4;dy<=4;dy++)
    assert.ok(grid.some(p=>p.factor===1 && p.dx===dx && p.dy===dy));
});

test('default tuning only translates, with zero size adjustment',()=>{
  const grid=placements();assert.equal(grid.length,121);
  assert.ok(grid.every(p=>p.factor===1 && p.dx%2===0 && p.dy%2===0));
  for(let dx=-10;dx<=10;dx+=2) for(let dy=-10;dy<=10;dy+=2)
    assert.ok(grid.some(p=>p.dx===dx&&p.dy===dy));
});
test('rejects clipping and preserves component identities while moving',()=>{
  const base=sample(12,[[0,0,1],[5,5,2]],2);
  assert.equal(transform(base,{factor:1,dx:-1,dy:0}),null);
  const moved=transform(base,{factor:1,dx:1,dy:2});
  assert.equal(moved.labels[2*12+1],1);assert.equal(moved.labels[7*12+6],2);
  assert.equal(moved.labels.filter(x=>x>0).length,2);
});

test('rejects resampling that makes a component disappear',()=>{
  const base=sample(12,[[3,3,1],[8,8,2]],2);
  assert.equal(transform(base,{factor:.1,dx:0,dy:0}),null);
});
test('search improves a synthetic cell collision without changing the objective',async()=>{
  const base=sample(12,[[4,4,1],[5,4,2]],2);
  const initial=allocate(cellInk(base.labels,base.size,base.count));assert.equal(initial.lostInk,1);
  const best=await searchPlacement(base,{scaleRange:0,shift:1,stepSize:1});
  assert.equal(best.plan.lostInk,0);assert.equal(best.tuning.baselineLost,1);
  assert.equal(best.tuning.optimal,true);assert.ok(best.placement.dx!==0);
});
test('search never replaces the baseline by a worse candidate and is cancellable',async()=>{
  const base=sample(12,[[2,2,1],[9,9,2]],2);
  const best=await searchPlacement(base);
  assert.equal(best.plan.lostInk,0);assert.equal(best.tuning.evaluated,1);
  assert.deepEqual(best.placement,{factor:1,dx:0,dy:0});
  assert.equal(await searchPlacement(base,{cancelled:()=>true}),null);
});

test('zero loss still searches for smaller occupied area',async()=>{
  const base=sample(12,[[3,3,1],[4,3,1]],1);
  const initial=allocate(cellInk(base.labels,base.size,base.count));
  assert.equal(initial.lostInk,0);assert.equal(initial.occupied,2);
  const best=await searchPlacement(base,{shift:1,stepSize:1});
  assert.equal(best.plan.lostInk,0);assert.equal(best.plan.occupied,1);
  assert.ok(best.tuning.evaluated>1);assert.equal(best.tuning.areaOptimal,true);
});

test('placement search carries the grid size through scoring and area ties',async()=>{
  for(const gridSize of [5,7,8]) {
    const base=sample(gridSize*2,[[3,3,1],[4,3,1]],1);
    const best=await searchPlacement(base,{gridSize,shift:1,stepSize:1});
    assert.equal(best.plan.gridSize,gridSize);assert.equal(best.plan.rooms.length,gridSize**2);
    assert.equal(best.plan.lostInk,0);assert.equal(best.plan.occupied,1);
    assert.equal(best.tuning.areaOptimal,true);
  }
});

test('placement search forwards room connectivity',async()=>{
  const base=sample(12,[[2,2,1],[4,4,1]],1);
  const eight=await searchPlacement(base,{shift:0,connectivity:8});
  const four=await searchPlacement(base,{shift:0,connectivity:4});
  assert.equal(eight.plan.occupied,2);assert.equal(four.plan.occupied,3);
  assert.equal(eight.plan.connectivity,8);assert.equal(four.plan.connectivity,4);
});
