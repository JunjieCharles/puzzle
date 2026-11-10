import { cellInk } from './floorplan.mjs';

export const CENTERLINE_UNITS=1024;
export const SMOOTH_RADIUS=3;

// Guo-Hall topology-preserving thinning, with a zero-padded frame.
// Neighbors are compared by source label: thinning never merges components.
// Algorithm reference: OpenCV ximgproc thinning (Guo-Hall conditions).
export function skeletonize(labels,size) {
  const stride=size+2,work=new Int32Array(stride*stride);
  for(let y=0;y<size;y++) work.set(labels.subarray(y*size,(y+1)*size),(y+1)*stride+1);
  let changed=true;
  while(changed) {
    changed=false;
    for(let pass=0;pass<2;pass++) {
      const remove=[];
      for(let y=1;y<=size;y++) for(let x=1;x<=size;x++) {
        const p=y*stride+x,k=work[p];if(!k) continue;
        const n=Number(work[p-stride]===k),ne=Number(work[p-stride+1]===k);
        const e=Number(work[p+1]===k),se=Number(work[p+stride+1]===k);
        const s=Number(work[p+stride]===k),sw=Number(work[p+stride-1]===k);
        const w=Number(work[p-1]===k),nw=Number(work[p-stride-1]===k);
        const transitions=(!n&&(ne||e))+(!e&&(se||s))+(!s&&(sw||w))+(!w&&(nw||n));
        const degree=Math.min((nw|n)+(ne|e)+(se|s)+(sw|w),(n|ne)+(e|se)+(s|sw)+(w|nw));
        const protectedSide=pass===0 ? ((s|sw|Number(!nw))&w) : ((n|ne|Number(!se))&e);
        if(transitions===1 && degree>=2 && degree<=3 && !protectedSide) remove.push(p);
      }
      for(const p of remove) work[p]=0;
      changed ||= remove.length>0;
    }
  }
  const result=new Int32Array(labels.length);
  for(let y=0;y<size;y++) result.set(work.subarray((y+1)*stride+1,(y+1)*stride+size+1),y*size);
  return result;
}

// Uniform positional uncertainty, not stroke thickness. Clamping at the outer
// canvas edge preserves all mass; the frame itself is not a competing room.
function axisWeights(position,size,gridSize,radius) {
  const low=position-radius,high=position+radius,result=[];
  for(let c=0;c<gridSize;c++) {
    const left=c===0 ? low : c*size/gridSize;
    const right=c===gridSize-1 ? high : (c+1)*size/gridSize;
    const weight=Math.max(0,Math.min(high,right)-Math.max(low,left))/(2*radius);
    if(weight>0) result.push([c,weight]);
  }
  return result;
}

export function centerlineInk(points,size,count,gridSize,{dx=0,dy=0,factor=1}={},radius=SMOOTH_RADIUS) {
  if(![5,6,7,8].includes(gridSize) || !(radius>0)) throw new Error('Invalid scoring geometry');
  const rows=Array.from({length:count},()=>new Float64Array(gridSize*gridSize));
  for(const {x,y,label} of points) {
    const xx=(x-size/2)*factor+size/2+dx,yy=(y-size/2)*factor+size/2+dy;
    const shares=[];
    for(const [r,wy] of axisWeights(yy,size,gridSize,radius))
      for(const [c,wx] of axisWeights(xx,size,gridSize,radius)) {
        const value=wx*wy*CENTERLINE_UNITS;
        shares.push({cell:r*gridSize+c,units:Math.floor(value),fraction:value-Math.floor(value)});
      }
    // Largest-remainder quantization conserves exactly one point's weight.
    shares.sort((a,b)=>b.fraction-a.fraction || a.cell-b.cell);
    const remaining=CENTERLINE_UNITS-shares.reduce((sum,s)=>sum+s.units,0);
    for(let i=0;i<remaining;i++) shares[i%shares.length].units++;
    for(const share of shares) rows[label-1][share.cell]+=share.units;
  }
  return rows;
}

export function createScoring(base,{gridSize=6,metric='ink'}={}) {
  if(metric==='ink') return sample=>cellInk(sample.labels,sample.size,sample.count,gridSize);
  if(metric!=='centerline') throw new Error('Unknown objective');
  const skeleton=skeletonize(base.labels,base.size),points=[];
  for(let p=0;p<skeleton.length;p++) if(skeleton[p])
    points.push({x:p%base.size+.5,y:Math.floor(p/base.size)+.5,label:skeleton[p]});
  return (_sample,placement)=>centerlineInk(points,base.size,base.count,gridSize,placement);
}

export function pixelLoss(labels,size,count,gridSize,rooms) {
  const rows=cellInk(labels,size,count,gridSize);
  let total=0,lost=0;
  rows.forEach((row,k)=>row.forEach((value,c)=>{total+=value;if(rooms[c]!==k+1) lost+=value;}));
  return {lost,total,outside:total ? lost/total : 0};
}
