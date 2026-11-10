import test from 'node:test';
import assert from 'node:assert/strict';
import { allocate, cellInk } from '../public/floorplan.mjs';
function check(plan,count) {
  assert.equal(plan.rooms.length,36);
  for(let k=1;k<=count;k++) {
    const cells=Array.from(plan.rooms.entries()).filter(([,v])=>v===k).map(([c])=>c);
    assert.ok(cells.length);const seen=new Set([cells[0]]),queue=[cells[0]];
    for(const c of queue) for(const d of cells) if(!seen.has(d) && Math.abs(c%6-d%6)+Math.abs(Math.floor(c/6)-Math.floor(d/6))===1) {seen.add(d);queue.push(d);}
    assert.equal(seen.size,cells.length);
  }
  assert.ok(plan.outside>=0 && plan.outside<=1);
}
test('joins separated targets through empty bridge',()=>{
  const row=new Float64Array(36);row[0]=row[35]=10;
  const plan=allocate([row]);check(plan,1);assert.equal(plan.outside,0);assert.equal(plan.empty,25);
});
test('competing components and crowded allocations remain connected',()=>{
  for(const count of [2,5,12,36]) {
    const ink=Array.from({length:count},(_,k)=>Float64Array.from({length:36},(_,c)=>(k*13+c*7)%17+1));
    const plan=allocate(ink);check(plan,count);assert.deepEqual(plan.rooms,allocate(ink).rooms);
  }
});
test('pixel cells align to six by six grid',()=>{
  const labels=new Int32Array(144);labels[0]=1;labels[143]=2;
  const ink=cellInk(labels,12,2);assert.equal(ink[0][0],1);assert.equal(ink[1][35],1);
});
test('rejects impossible number of rooms and empty ink',()=>{
  assert.ok(allocate([]).error);assert.ok(allocate(Array.from({length:37},()=>new Float64Array(36).fill(1))).error);
  assert.throws(()=>allocate([new Float64Array(36)]));
});

test('optimizes total pixels rather than equal component percentages',()=>{
  const a=new Float64Array(36),b=new Float64Array(36);
  a[0]=100;a[1]=90;b[0]=2;b[2]=1;
  const plan=allocate([a,b]);check(plan,2);
  assert.equal(plan.rooms[0],1);assert.equal(plan.lostInk,2);
  assert.equal(plan.totalInk,193);assert.equal(plan.optimal,true);
  assert.equal(plan.outside,plan.lowerBound);
});

test('a small ink gain is never rejected for room area or symmetry',()=>{
  const a=new Float64Array(36);a[0]=10000;a[5]=1;
  const plan=allocate([a]);check(plan,1);
  assert.equal(plan.lostInk,0);assert.equal(plan.optimal,true);
});

test('zero-cost blank representatives do not damage a feasible direct optimum',()=>{
  const a=new Float64Array(36),b=new Float64Array(36),c=new Float64Array(36);
  a[6]=30;a[7]=10;a[13]=20;b[10]=8;b[16]=9;c[33]=3;
  const plan=allocate([a,b,c]);check(plan,3);
  assert.equal(plan.outside,0);assert.equal(plan.optimal,true);
  assert.equal(plan.rooms[0],0);assert.equal(plan.rooms[1],0);
  assert.equal(plan.empty,30);
  for(let cell=0;cell<36;cell++) {
    if(a[cell]) assert.equal(plan.rooms[cell],1);
    if(b[cell]) assert.equal(plan.rooms[cell],2);
    if(c[cell]) assert.equal(plan.rooms[cell],3);
  }
});

test('crossing connection demands report an unclosed lower bound honestly',()=>{
  const a=new Float64Array(36),b=new Float64Array(36);
  a[0]=a[35]=10;b[5]=b[30]=10;
  const plan=allocate([a,b],{maxSearchNodes:0});check(plan,2);
  assert.equal(plan.lowerBound,0);assert.ok(plan.outside>0);
  assert.equal(plan.optimal,false);assert.equal(plan.boundGap,plan.outside);
});

test('connectivity cuts prove a positive unavoidable loss without fixing roots',()=>{
  // Synthetic two crossing routes inside a heavily occupied enclosing region.
  const a=new Float64Array(36),b=new Float64Array(36),frame=new Float64Array(36).fill(10000);
  const inner=[13,14,15,19,20,21];for(const c of inner) frame[c]=0;
  a[13]=a[21]=10;b[15]=b[19]=10;
  const ink=[a,b,frame],plan=allocate(ink);check(plan,3);
  let best=Infinity;
  // Exhaust every inner assignment; sacrificing any outer cell costs more
  // than all inner ink, so an optimum preserves the fixed enclosing region.
  for(let code=0;code<3**inner.length;code++) {
    const rooms=new Int32Array(36).fill(3);let rest=code;
    for(const c of inner) {rooms[c]=rest%3;rest=Math.floor(rest/3);}
    let valid=true;
    for(let k=1;k<=3;k++) {
      const cells=Array.from(rooms.entries()).filter(([,v])=>v===k).map(([c])=>c);
      if(!cells.length) {valid=false;break;}
      const seen=new Set([cells[0]]),queue=[cells[0]];
      for(const c of queue) for(const d of cells)
        if(!seen.has(d)&&Math.abs(c%6-d%6)+Math.abs(Math.floor(c/6)-Math.floor(d/6))===1) {seen.add(d);queue.push(d);}
      if(seen.size!==cells.length) {valid=false;break;}
    }
    if(valid) {
      const kept=rooms.reduce((sum,k,c)=>sum+(k?ink[k-1][c]:0),0);
      best=Math.min(best,plan.totalInk-kept);
    }
  }
  assert.equal(best,10);assert.equal(plan.lostInk,best);
  assert.equal(plan.relaxedLowerBound,0);assert.ok(plan.lowerBound>0);
  assert.equal(plan.optimal,true);assert.ok(plan.searchNodes>0);
  const limited=allocate(ink,{maxSearchNodes:1});check(limited,3);
  assert.equal(limited.optimal,false);assert.ok(limited.lowerBound<=best/limited.totalInk);
});

test('assignment lower bound matches exhaustive distinct representative cells',()=>{
  for(let seed=1;seed<=12;seed++) {
    const ink=Array.from({length:2},(_,k)=>Float64Array.from({length:36},(_,c)=>(c*13+k*7+seed*11)%19));
    const best=Array.from({length:36},(_,c)=>Math.max(ink[0][c],ink[1][c]));
    let regret=Infinity;
    for(let a=0;a<36;a++) for(let b=0;b<36;b++) if(a!==b)
      regret=Math.min(regret,best[a]-ink[0][a]+best[b]-ink[1][b]);
    const total=ink.flatMap(row=>Array.from(row)).reduce((a,b)=>a+b,0);
    const expected=(total-best.reduce((a,b)=>a+b,0)+regret)/total;
    const plan=allocate(ink);check(plan,2);assert.equal(plan.relaxedLowerBound,expected);
    assert.ok(plan.lowerBound>=expected);assert.ok(plan.outside>=plan.lowerBound);
    assert.equal(plan.optimal,plan.outside===plan.lowerBound);
  }
});

test('equal coverage uses the shortest connected area and reports its proof',()=>{
  const row=new Float64Array(36);row[0]=row[2]=10;
  const plan=allocate([row]);check(plan,1);
  assert.equal(plan.lostInk,0);assert.equal(plan.occupied,3);
  assert.equal(plan.areaOptimal,true);
  const limited=allocate([row],{maxSearchNodes:0});
  assert.equal(limited.optimal,true);assert.equal(limited.areaOptimal,false);
});

test('all grid sizes map fractional pixel boundaries without loss',()=>{
  for(const gridSize of [5,6,7,8]) {
    const size=384,labels=new Int32Array(size*size).fill(1);
    const [ink]=cellInk(labels,size,1,gridSize);
    assert.equal(ink.length,gridSize**2);
    assert.equal(ink.reduce((a,b)=>a+b,0),size*size);
    for(let y=0;y<gridSize;y++) for(let x=0;x<gridSize;x++) {
      const width=Math.ceil((x+1)*size/gridSize)-Math.ceil(x*size/gridSize);
      const height=Math.ceil((y+1)*size/gridSize)-Math.ceil(y*size/gridSize);
      assert.equal(ink[y*gridSize+x],width*height);
    }
    const plan=allocate([ink],{gridSize});
    assert.equal(plan.occupied,gridSize**2);assert.equal(plan.lostInk,0);
    assert.equal(plan.areaOptimal,true);assert.equal(plan.gridSize,gridSize);
  }
});

test('grid topology never connects adjacent indices across a row boundary',()=>{
  for(const gridSize of [8,5,7,6,8]) {
    const row=new Float64Array(gridSize**2);row[gridSize-1]=row[gridSize]=1;
    const plan=allocate([row],{gridSize,maxSearchNodes:0});
    assert.equal(plan.lostInk,0);
    assert.equal(plan.occupied,gridSize+1);
    assert.equal(plan.empty+plan.occupied,gridSize**2);
  }
});

test('room capacity follows the selected grid rather than the old 36-cell limit',()=>{
  const ink=Array.from({length:64},(_,k)=>Float64Array.from({length:64},(_,c)=>Number(c===k)));
  const plan=allocate(ink,{gridSize:8});
  assert.equal(plan.occupied,64);assert.equal(plan.lostInk,0);assert.equal(plan.areaOptimal,true);
  assert.ok(allocate(Array.from({length:26},()=>new Float64Array(25).fill(1)),{gridSize:5}).error);
  assert.throws(()=>allocate([new Float64Array(36).fill(1)],{gridSize:7}));
});

test('eight-connected rooms join diagonal cells without an orthogonal bridge',()=>{
  for(const gridSize of [5,6,7,8]) {
    const row=new Float64Array(gridSize**2);row[0]=row[gridSize+1]=10;
    const eight=allocate([row],{gridSize,connectivity:8});
    const four=allocate([row],{gridSize,connectivity:4});
    assert.equal(eight.lostInk,0);assert.equal(eight.occupied,2);assert.equal(eight.areaOptimal,true);
    assert.equal(four.lostInk,0);assert.equal(four.occupied,3);assert.equal(four.areaOptimal,true);
    assert.deepEqual(allocate([row],{gridSize,connectivity:8}).rooms,eight.rooms);
  }
});

test('diagonally crossing labels may share a vertex, but never a cell',()=>{
  const gridSize=5,a=new Float64Array(25),b=new Float64Array(25),frame=new Float64Array(25).fill(100);
  for(const c of [6,7,11,12]) frame[c]=0;
  a[6]=a[12]=1;b[7]=b[11]=1;
  const eight=allocate([a,b,frame],{gridSize,connectivity:8});
  assert.equal(eight.lostInk,0);assert.equal(eight.areaOptimal,true);
  assert.equal(eight.rooms[6],eight.rooms[12]);assert.equal(eight.rooms[7],eight.rooms[11]);
  assert.notEqual(eight.rooms[6],eight.rooms[7]);
  const four=allocate([a,b,frame],{gridSize,connectivity:4});
  assert.equal(four.lostInk,1);assert.equal(four.optimal,true);
});

test('eight-neighbor topology still cannot wrap across rows',()=>{
  const row=new Float64Array(25);row[4]=row[5]=10;
  const plan=allocate([row],{gridSize:5,connectivity:8,maxSearchNodes:0});
  assert.equal(plan.lostInk,0);assert.equal(plan.occupied,5);
  assert.throws(()=>allocate([row],{gridSize:5,connectivity:6}));
});
