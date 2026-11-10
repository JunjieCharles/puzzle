// Generic runtime geometry only. Never persist glyph-to-room mappings.
function validateGridSize(gridSize) {
  if(![5,6,7,8].includes(gridSize)) throw new Error('Expected grid size 5, 6, 7 or 8');
}

export function cellInk(labels, size, count, gridSize=6) {
  validateGridSize(gridSize);
  const ink=Array.from({length:count},()=>new Float64Array(gridSize*gridSize));
  for(let p=0;p<labels.length;p++) if(labels[p]>0) {
    const cell=Math.floor(Math.floor(p/size)*gridSize/size)*gridSize+Math.floor((p%size)*gridSize/size);
    ink[labels[p]-1][cell]++;
  }
  return ink;
}

// Each cached solver closes over its own immutable grid geometry.
const solvers=new Map();
export function allocate(ink,{gridSize=6,connectivity=4,maxSearchNodes=128}={}) {
  validateGridSize(gridSize);
  if(![4,8].includes(connectivity)) throw new Error('Expected room connectivity 4 or 8');
  const key=`${gridSize}:${connectivity}`;
  if(!solvers.has(key)) solvers.set(key,createSolver(gridSize,connectivity));
  return solvers.get(key)(ink,{maxSearchNodes});
}

function createSolver(gridSize,connectivity) {
  const cells=gridSize*gridSize,priority=cells+1;
  const neighbors = Array.from({length:cells}, (_,cell) =>
    Array.from({length:cells}, (_,other) => other).filter(other => {
      const dx=Math.abs(cell%gridSize-other%gridSize),dy=Math.abs(Math.floor(cell/gridSize)-Math.floor(other/gridSize));
      return connectivity===8 ? Math.max(dx,dy)===1 : dx+dy===1;
    }));

  // Rectangular Hungarian assignment: distinct roots, maximum supplied cell value.
  function seeds(weights) {
    const n=weights.length,m=cells,u=new Float64Array(n+1),v=new Float64Array(m+1);
    const p=new Int32Array(m+1),way=new Int32Array(m+1);
    for(let i=1;i<=n;i++) {
      p[0]=i;let j0=0;const min=new Float64Array(m+1).fill(Infinity),used=new Uint8Array(m+1);
      do {
        used[j0]=1;const i0=p[j0];let delta=Infinity,j1=0;
        for(let j=1;j<=m;j++) if(!used[j]) {
          const cur=-weights[i0-1][j-1]-u[i0]-v[j];
          if(cur<min[j]) {min[j]=cur;way[j]=j0;}
          if(min[j]<delta) {delta=min[j];j1=j;}
        }
        for(let j=0;j<=m;j++) {if(used[j]) {u[p[j]]+=delta;v[j]-=delta;}else min[j]-=delta;}
        j0=j1;
      } while(p[j0]!==0);
      do {const j1=way[j0];p[j0]=p[j1];j0=j1;} while(j0);
    }
    const roots=new Int32Array(n);
    for(let j=1;j<=m;j++) if(p[j]) roots[p[j]-1]=j-1;
    return roots;
  }

  function connectedAfterRemoval(rooms, label, removed) {
    const start=rooms.findIndex((r,c)=>r===label && c!==removed);
    if(start<0) return false;
    const seen=new Set([start]),queue=[start];
    for(const cell of queue) for(const other of neighbors[cell])
      if(other!==removed && rooms[other]===label && !seen.has(other)) {seen.add(other);queue.push(other);}
    return rooms.every((r,c)=>r!==label || c===removed || seen.has(c));
  }

  function validRooms(rooms,count) {
    for(let label=1;label<=count;label++) {
      const start=rooms.indexOf(label);
      if(start<0) return false;
      const seen=new Set([start]),queue=[start];
      for(const c of queue) for(const other of neighbors[c])
        if(rooms[other]===label && !seen.has(other)) {seen.add(other);queue.push(other);}
      if(rooms.some((r,c)=>r===label && !seen.has(c))) return false;
    }
    return true;
  }

  // Count pixels only: no component normalization or shape penalties.
  function retained(rooms,ink) {
    return rooms.reduce((sum,label,c)=>sum+(label?ink[label-1][c]:0),0);
  }

  // At most gridSize squared occupied cells: one retained pixel always outweighs area.
  function objective(rooms,ink) {
    return priority*retained(rooms,ink)-rooms.filter(Boolean).length;
  }

  function grow(ink,roots,cellMax) {
    const count=ink.length,rooms=new Int32Array(cells);
    roots.forEach((c,k)=>{rooms[c]=k+1;});
    for(let iteration=0;iteration<cells;iteration++) {
      let best=null;
      for(let k=0;k<count;k++) {
        const distance=new Float64Array(cells).fill(Infinity),steps=new Float64Array(cells).fill(Infinity);
        const prev=new Int32Array(cells).fill(-1),visited=new Uint8Array(cells);
        for(let c=0;c<cells;c++) if(rooms[c]===k+1) {distance[c]=0;steps[c]=0;}
        for(let step=0;step<cells;step++) {
          let cell=-1;
          for(let c=0;c<cells;c++) if(!visited[c] && (cell<0 || distance[c]<distance[cell]
            || (distance[c]===distance[cell] && steps[c]<steps[cell]))) cell=c;
          if(cell<0 || !Number.isFinite(distance[cell])) break;
          visited[cell]=1;
          for(const other of neighbors[cell]) if(!rooms[other] && !visited[other]) {
            const cost=distance[cell]+cellMax[other]-ink[k][other],length=steps[cell]+1;
            if(cost<distance[other] || (cost===distance[other] && length<steps[other])) {
              distance[other]=cost;steps[other]=length;prev[other]=cell;
            }
          }
        }
        for(let c=0;c<cells;c++) if(!rooms[c] && prev[c]>=0) {
          const path=[];let at=c,gain=0;
          while(at>=0 && !rooms[at]) {path.push(at);gain+=ink[k][at];at=prev[at];}
          if(gain>0 && (!best || gain>best.gain)) best={k,path,gain};
        }
      }
      if(!best) break;
      for(const c of best.path) rooms[c]=best.k+1;
    }
    // Improve only total covered ink. Roots are initialization, never locked.
    for(let iteration=0;iteration<100;iteration++) {
      let best=null;
      for(let c=0;c<cells;c++) {
        const old=rooms[c];
        if(old && !connectedAfterRemoval(rooms,old,c)) continue;
        for(const next of new Set(neighbors[c].map(d=>rooms[d]))) if(next && next!==old) {
          const gain=ink[next-1][c]-(old?ink[old-1][c]:0);
          if(gain>0 && (!best || gain>best.gain)) best={moves:[[c,next]],gain};
        }
      }
      // Swaps can move the initial seed or escape a one-cell local optimum.
      for(let c=0;c<cells;c++) for(let d=c+1;d<cells;d++) if(rooms[c]!==rooms[d]) {
        const a=rooms[c],b=rooms[d];
        const gain=(b?ink[b-1][c]-ink[b-1][d]:0)+(a?ink[a-1][d]-ink[a-1][c]:0);
        if(gain<=0 || (best && gain<=best.gain)) continue;
        rooms[c]=b;rooms[d]=a;
        if(validRooms(rooms,count)) best={moves:[[c,b],[d,a]],gain};
        rooms[c]=a;rooms[d]=b;
      }
      if(!best) break;
      for(const [c,label] of best.moves) rooms[c]=label;
    }
    return rooms;
  }

  // Exact assignment relaxation under cell-label domains. Labels include 0 for
  // unassigned space. Forbidden representatives are checked after assignment.
  function relax(ink,domains) {
    const count=ink.length,max=new Float64Array(cells),direct=new Int32Array(cells);
    for(let c=0;c<cells;c++) {
      if(!domains[c].length) return null;
      max[c]=-Infinity;
      for(const label of domains[c]) {
        const value=label?priority*ink[label-1][c]-1:0;
        if(value>max[c]) {max[c]=value;direct[c]=label;}
      }
    }
    if(ink.every((_,k)=>direct.includes(k+1))) return {rooms:direct,score:objective(direct,ink)};
    const forbidden=-(ink.flatMap(row=>Array.from(row)).reduce((a,b)=>a+b,0)+1)*(priority+1);
    const roots=seeds(ink.map((row,k)=>Float64Array.from(row,(v,c)=>domains[c].includes(k+1)?priority*v-1-max[c]:forbidden)));
    for(let k=0;k<count;k++) {
      if(!domains[roots[k]].includes(k+1)) return null;
      direct[roots[k]]=k+1;
    }
    return {rooms:direct,score:objective(direct,ink)};
  }

  // Any connected solution with r,t in one room must cross the boundary of S.
  // Branch on that necessary condition instead of imposing a chosen room root.
  function disconnectedCut(rooms,count,domains) {
    let best=null;
    for(let label=1;label<=count;label++) {
      const unseen=new Set(Array.from(rooms.entries()).filter(([,v])=>v===label).map(([c])=>c));
      const parts=[];
      while(unseen.size) {
        const part=[unseen.values().next().value];unseen.delete(part[0]);
        for(const c of part) for(const d of neighbors[c]) if(unseen.has(d)) {unseen.delete(d);part.push(d);}
        parts.push(part);
      }
      if(parts.length<2) continue;
      for(const part of parts) {
        const boundary=[...new Set(part.flatMap(c=>neighbors[c]))]
          .filter(c=>!part.includes(c) && domains[c].includes(label));
        const cut={label,r:part[0],t:parts.find(other=>other!==part)[0],boundary};
        if(!best || boundary.length<best.boundary.length) best=cut;
      }
    }
    return best;
  }

  function certify(ink,incumbent,upper,maxNodes) {
    const domains=Array.from({length:cells},()=>Array.from({length:ink.length+1},(_,k)=>k));
    const pending=[{domains,upper}];let rooms=incumbent,score=objective(rooms,ink),nodes=0;
    while(pending.length && nodes<maxNodes) {
      let index=0;
      for(let i=1;i<pending.length;i++) if(pending[i].upper>pending[index].upper) index=i;
      const node=pending.splice(index,1)[0];
      if(node.upper<=score) continue;
      nodes++;
      const relaxed=relax(ink,node.domains);
      if(!relaxed || relaxed.score<=score) continue;
      const cut=disconnectedCut(relaxed.rooms,ink.length,node.domains);
      if(!cut) {rooms=relaxed.rooms;score=relaxed.score;continue;}
      // Disjoint exhaustive cases: remove r; keep r and remove t; otherwise
      // keep both and select the first boundary cell that belongs to this room.
      let base=node.domains.map(d=>d.slice());
      for(const c of [cut.r,cut.t]) {
        const child=base.map(d=>d.slice());child[c]=child[c].filter(k=>k!==cut.label);
        if(child[c].length) pending.push({domains:child,upper:relaxed.score});
        base[c]=[cut.label];
      }
      for(const c of cut.boundary) {
        const child=base.map(d=>d.slice());child[c]=[cut.label];
        pending.push({domains:child,upper:relaxed.score});
        base[c]=base[c].filter(k=>k!==cut.label);
        if(!base[c].length) break;
      }
    }
    return {rooms,nodes,upper:Math.max(score,...pending.map(node=>node.upper))};
  }

  function allocate(ink,{maxSearchNodes=128}={}) {
    const count=ink.length;
    if(!count || count>cells) return {error:count?`连通块超过 ${cells} 个，无法各分一个房间`:'没有可分配的墨迹'};
    if(ink.some(row=>row.length!==cells || row.some(x=>!Number.isFinite(x)||x<0) || row.reduce((a,b)=>a+b,0)<=0))
      throw new Error(`Expected nonempty component ink on ${cells} cells`);
    const totals=ink.map(row=>row.reduce((a,b)=>a+b,0)),total=totals.reduce((a,b)=>a+b,0);
    const cellMax=Float64Array.from({length:cells},(_,c)=>Math.max(...ink.map(row=>row[c])));
    // Exact relaxation: maximize total coverage with every component nonempty,
    // temporarily dropping connectivity. Choosing a distinct representative cell
    // for each component costs cellMax[c]-ink[k][c]; assignment minimizes this loss.
    const roots=seeds(ink.map(row=>Float64Array.from(row,(v,c)=>v-cellMax[c])));
    const direct=Int32Array.from(cellMax,(v,c)=>v?ink.findIndex(row=>row[c]===v)+1:0);
    let rooms=direct.slice();
    roots.forEach((c,k)=>{rooms[c]=k+1;});
    let upper=retained(rooms,ink);
    const relaxedUpper=upper;
    // Representatives certify nonemptiness in the relaxation; they are not
    // mandatory room anchors. An arbitrary zero-ink representative must never
    // turn an already connected maximum-coverage layout into a disconnected one.
    if(validRooms(direct,count)) rooms=direct;
    else {
      for(let c=0;c<cells;c++) if(rooms[c] && !cellMax[c]) {
        const label=rooms[c];
        if(rooms.some((other,d)=>d!==c && other===label)) rooms[c]=0;
      }
    }
    if(!validRooms(rooms,count)) {
      // Use actual owned ink as the growth seed, rather than arbitrary blank
      // representatives chosen by a tied assignment. The regions are disjoint,
      // so these seeds are distinct without adding any new objective term.
      const usefulRoots=Int32Array.from({length:count},(_,k)=>{
        let best=-1;
        for(let c=0;c<cells;c++) if(rooms[c]===k+1 && (best<0 || ink[k][c]>ink[k][best])) best=c;
        return best;
      });
      rooms=grow(ink,usefulRoots,cellMax);
      const alternative=grow(ink,seeds(ink),cellMax);
      if(retained(alternative,ink)>retained(rooms,ink)) rooms=alternative;
    }
    // Trim removable blank cells before the joint coverage/area proof search.
    for(let changed=true;changed;) {
      changed=false;
      for(let c=0;c<cells;c++) if(rooms[c] && ink[rooms[c]-1][c]===0
        && connectedAfterRemoval(rooms,rooms[c],c)) {rooms[c]=0;changed=true;}
    }
    upper=relax(ink,Array.from({length:cells},()=>Array.from({length:count+1},(_,k)=>k))).score;
    let searchNodes=0;
    if(objective(rooms,ink)<upper && maxSearchNodes>0) {
      const proof=certify(ink,rooms,upper,maxSearchNodes);
      rooms=proof.rooms;upper=proof.upper;searchNodes=proof.nodes;
    }
    const areaOptimal=objective(rooms,ink)===upper;
    upper=Math.ceil(upper/priority);
    const covered=retained(rooms,ink),lost=total-covered,boundGap=Math.max(0,upper-covered);
    const kept=ink.map((row,k)=>row.reduce((sum,x,c)=>sum+(rooms[c]===k+1?x:0),0));
    return {rooms,count,gridSize,connectivity,areaOptimal,occupied:rooms.filter(Boolean).length,empty:rooms.filter(x=>!x).length,outside:lost/total,
      lostInk:lost,totalInk:total,lowerBound:(total-upper)/total,boundGap:boundGap/total,
      optimal:boundGap===0,searchNodes,relaxedLowerBound:(total-relaxedUpper)/total,
      worstLoss:Math.max(...kept.map((x,k)=>1-x/totals[k]))};
  }

  return allocate;
}

export function drawPlan(canvas, rgba, plan, overlay) {
  const gridSize=plan.gridSize ?? 6,cells=gridSize*gridSize;
  const ctx=canvas.getContext('2d'),size=canvas.width,step=size/gridSize;
  ctx.fillStyle='#fff';ctx.fillRect(0,0,size,size);
  for(let c=0;c<cells;c++) if(!plan.rooms[c]) {
    ctx.fillStyle='#e2e5e9';ctx.fillRect(c%gridSize*step,Math.floor(c/gridSize)*step,step,step);
  }
  if(overlay) {
    const image=ctx.getImageData(0,0,size,size);
    for(let i=0;i<size*size;i++) {
      const alpha=(255-rgba[4*i])/255*.55;
      for(let j=0;j<3;j++) image.data[4*i+j]=Math.round(image.data[4*i+j]*(1-alpha));
    }
    ctx.putImageData(image,0,0);
  }
  ctx.strokeStyle='#26332e';ctx.lineWidth=2;ctx.beginPath();
  for(let r=0;r<gridSize;r++) for(let c=0;c<gridSize;c++) {
    const label=plan.rooms[r*gridSize+c];
    if(c<gridSize-1 && label!==plan.rooms[r*gridSize+c+1]) {ctx.moveTo((c+1)*step,r*step);ctx.lineTo((c+1)*step,(r+1)*step);}
    if(r<gridSize-1 && label!==plan.rooms[(r+1)*gridSize+c]) {ctx.moveTo(c*step,(r+1)*step);ctx.lineTo((c+1)*step,(r+1)*step);}
  }
  ctx.stroke();ctx.lineWidth=3;ctx.strokeRect(1.5,1.5,size-3,size-3);
}
