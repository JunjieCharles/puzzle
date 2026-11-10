import { allocate } from './floorplan.mjs';
import { createScoring } from './scoring.mjs';

export function placements(scaleRange=0,shift=10,stepSize=2) {
  const result=[],offsets=[0];
  for(let step=stepSize;step<=shift;step+=stepSize) offsets.push(-step,step);
  for(const factor of [1,1-scaleRange,1+scaleRange])
    for(const dx of offsets) for(const dy of offsets)
      if(!result.some(p=>p.factor===factor&&p.dx===dx&&p.dy===dy)) result.push({factor,dx,dy});
  return result.sort((a,b)=>(Math.abs(a.factor-1)+Math.abs(a.dx)/384+Math.abs(a.dy)/384)
    -(Math.abs(b.factor-1)+Math.abs(b.dx)/384+Math.abs(b.dy)/384));
}

export function inkBounds(rgba,size) {
  let x0=size,y0=size,x1=0,y1=0;
  for(let p=0;p<size*size;p++) if(rgba[p*4]<255) {
    x0=Math.min(x0,p%size);y0=Math.min(y0,Math.floor(p/size));
    x1=Math.max(x1,p%size+1);y1=Math.max(y1,Math.floor(p/size)+1);
  }
  return {x0,y0,x1,y1};
}

export function transform(base,placement,bounds=inkBounds(base.rgba,base.size)) {
  const {factor,dx,dy}=placement,{size,count}=base,center=size/2;
  if(factor<=0 || (bounds.x0-center)*factor+center+dx<0
    || (bounds.x1-center)*factor+center+dx>size
    || (bounds.y0-center)*factor+center+dy<0
    || (bounds.y1-center)*factor+center+dy>size) return null;
  if(factor===1 && dx===0 && dy===0) return base;
  const rgba=new Uint8ClampedArray(size*size*4).fill(255),labels=new Int32Array(size*size);
  const present=new Uint8Array(count+1);
  // The source component identity travels with each sampled pixel. Resampling
  // never reinterprets two touching marks as one component to improve the score.
  for(let y=0;y<size;y++) for(let x=0;x<size;x++) {
    const sx=Math.floor((x+.5-center-dx)/factor+center),sy=Math.floor((y+.5-center-dy)/factor+center);
    if(sx<0||sy<0||sx>=size||sy>=size) continue;
    const src=sy*size+sx,dst=y*size+x;labels[dst]=base.labels[src];
    present[labels[dst]]=1;
    for(let c=0;c<4;c++) rgba[dst*4+c]=base.rgba[src*4+c];
  }
  if(present.slice(1).some(v=>!v)) return null;
  return {rgba,labels,size,count};
}

export async function searchPlacement(base,{gridSize=6,connectivity=4,metric='ink',scaleRange=0,shift=10,stepSize=2,cancelled=()=>false,
  yieldControl=()=>Promise.resolve()}={}) {
  const candidates=placements(scaleRange,shift,stepSize),bounds=inkBounds(base.rgba,base.size);
  const score=createScoring(base,{gridSize,metric});
  let best=null,baselineLost=null,lower=Infinity,evaluated=0,rejected=0;
  const solved=[];
  for(const placement of candidates) {
    if(cancelled()) return null;
    const sample=transform(base,placement,bounds);
    if(!sample) {rejected++;continue;}
    const ink=score(sample,placement);
    // Even without connectivity, each cell can retain only one component.
    // If this cheap loss bound cannot beat the incumbent, no solve is needed.
    let cheapLower=0;
    for(let c=0;c<gridSize*gridSize;c++) {
      let sum=0,max=0;
      for(const row of ink) {sum+=row[c];max=Math.max(max,row[c]);}
      cheapLower+=sum-max;
    }
    if(best && cheapLower>best.plan.lostInk) {
      lower=Math.min(lower,cheapLower);evaluated++;
      if(evaluated%3===0) await yieldControl();
      continue;
    }
    const plan=allocate(ink,{gridSize,connectivity});
    if(plan.error) {rejected++;continue;}
    evaluated++;
    if(baselineLost===null) baselineLost=plan.lostInk;
    lower=Math.min(lower,Math.round(plan.lowerBound*plan.totalInk));
    solved.push(plan);
    if(!best || plan.lostInk<best.plan.lostInk
      || (plan.lostInk===best.plan.lostInk && plan.occupied<best.plan.occupied)) best={...sample,plan,placement};
    // Zero loss and one cell per component are joint absolute lower bounds.
    if(best.plan.lostInk===0 && best.plan.occupied===base.count) {lower=0;break;}
    if(evaluated%3===0) await yieldControl();
  }
  if(!best) return null;
  return {...best,tuning:{baselineLost,evaluated,rejected,candidates:candidates.length,
    optimal:best.plan.lostInk===lower,
    areaOptimal:best.plan.lostInk===lower && solved.every(p=>
      Math.round(p.lowerBound*p.totalInk)>best.plan.lostInk || p.areaOptimal),lower}};
}
