import test from 'node:test';
import assert from 'node:assert/strict';
import { skeletonize,centerlineInk,createScoring,CENTERLINE_UNITS } from '../public/scoring.mjs';
import { searchPlacement } from '../public/placement.mjs';

function regions(labels,size,label) {
  const remaining=new Set(Array.from(labels.entries()).filter(([,k])=>k===label).map(([p])=>p));
  let count=0;
  while(remaining.size) {
    count++;const queue=[remaining.values().next().value];remaining.delete(queue[0]);
    for(const p of queue) for(let dy=-1;dy<=1;dy++) for(let dx=-1;dx<=1;dx++) {
      const x=p%size+dx,y=Math.floor(p/size)+dy,q=y*size+x;
      if(x>=0&&x<size&&y>=0&&y<size&&remaining.has(q)) {remaining.delete(q);queue.push(q);}
    }
  }
  return count;
}

test('thinning preserves tiny components, edge strokes, diagonals and junctions',()=>{
  const size=40,labels=new Int32Array(size*size);
  labels[0]=1;
  for(let y=4;y<6;y++) for(let x=4;x<6;x++) labels[y*size+x]=2;
  for(let y=10;y<30;y++) for(let x=0;x<3;x++) labels[y*size+x]=3;
  for(let y=10;y<30;y++) for(let x=14;x<17;x++) labels[y*size+x]=4;
  for(let y=18;y<21;y++) for(let x=7;x<26;x++) labels[y*size+x]=4;
  for(let i=0;i<9;i++) labels[(30+i)*size+30+i]=5;
  const skeleton=skeletonize(labels,size);
  for(let k=1;k<=5;k++) assert.equal(regions(skeleton,size,k),1);
  assert.ok(skeleton.filter(Boolean).length<labels.filter(Boolean).length);
  for(let p=0;p<labels.length;p++) if(skeleton[p]) assert.equal(skeleton[p],labels[p]);
  assert.deepEqual(skeletonize(skeleton,size),skeleton);
});

test('thick loops retain their hole and thin horizontal strokes have a single center row',()=>{
  const size=32,labels=new Int32Array(size*size);
  for(let y=3;y<20;y++) for(let x=3;x<20;x++)
    if(y<6||y>=17||x<6||x>=17) labels[y*size+x]=1;
  for(let y=25;y<28;y++) for(let x=3;x<27;x++) labels[y*size+x]=2;
  const thin=skeletonize(labels,size);
  assert.equal(regions(thin,size,1),1);assert.equal(regions(thin,size,2),1);
  const seen=new Set([10*size+10]),queue=[10*size+10];
  for(const p of queue) for(const [dx,dy] of [[1,0],[-1,0],[0,1],[0,-1]]) {
    const x=p%size+dx,y=Math.floor(p/size)+dy,q=y*size+x;
    if(x>=0&&x<size&&y>=0&&y<size&&!thin[q]&&!seen.has(q)) {seen.add(q);queue.push(q);}
  }
  assert.ok(!seen.has(0));
  for(let x=8;x<22;x++) assert.equal([25,26,27].filter(y=>thin[y*size+x]===2).length,1);
});

test('a centerline crossing a wall changes gradually instead of all at once',()=>{
  for(const vertical of [false,true]) {
    const weights=[];
    for(const offset of [-3,-.5,0,.5,3]) {
      const p=vertical?{x:64+offset,y:32,label:1}:{x:32,y:64+offset,label:1};
      const [row]=centerlineInk([p],384,1,6);
      weights.push(row[0]/CENTERLINE_UNITS);
    }
    assert.equal(weights[0],1);assert.equal(weights[2],.5);assert.equal(weights[4],0);
    assert.ok(weights[1]-weights[3]<.17);
    for(let i=1;i<weights.length;i++) assert.ok(weights[i]<weights[i-1]);
  }
});

test('smoothing conserves integer mass at corners, outer frame and fractional grids',()=>{
  for(const gridSize of [5,6,7,8]) {
    const points=[{x:.5,y:.5,label:1},{x:383.5,y:383.5,label:2},
      {x:384/gridSize,y:384/gridSize,label:1}];
    const rows=centerlineInk(points,384,2,gridSize);
    assert.equal(rows[0].reduce((a,b)=>a+b,0),2*CENTERLINE_UNITS);
    assert.equal(rows[1].reduce((a,b)=>a+b,0),CENTERLINE_UNITS);
    for(const row of rows) assert.ok(row.every(v=>Number.isInteger(v)&&v>=0));
  }
});

test('centerline placement scoring preserves source identities and never worsens baseline',async()=>{
  const size=48,labels=new Int32Array(size*size),rgba=new Uint8ClampedArray(size*size*4).fill(255);
  for(let y=8;y<40;y++) for(const [x,k] of [[15,1],[17,2]]) {
    labels[y*size+x]=k;for(let c=0;c<3;c++) rgba[(y*size+x)*4+c]=0;
  }
  const base={labels,rgba,size,count:2},score=createScoring(base,{metric:'centerline'});
  const original=score(base,{dx:0,dy:0,factor:1});
  const moved=score(base,{dx:2,dy:-2,factor:1});
  for(let k=0;k<2;k++) assert.equal(original[k].reduce((a,b)=>a+b),moved[k].reduce((a,b)=>a+b));
  const best=await searchPlacement(base,{metric:'centerline',shift:2,stepSize:2});
  assert.ok(best.plan.lostInk<=best.tuning.baselineLost);
  assert.equal(best.count,2);
});
