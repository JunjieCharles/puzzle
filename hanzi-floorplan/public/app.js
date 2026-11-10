import { analyze, characters } from './analysis.mjs';
import { allocate, drawPlan } from './floorplan.mjs';
import { searchPlacement } from './placement.mjs';
import { createScoring, skeletonize, pixelLoss, CENTERLINE_UNITS } from './scoring.mjs';
const $ = id => document.getElementById(id);
const percent = value => `${(value*100).toFixed(value>0 && value<.001 ? 2 : 1)}%`;
const specs = [
  { name: '思源黑体', style: 'ExtraLight', weight: 250, url: './fonts/SourceHanSansSC-ExtraLight.otf' },
  { name: 'MiSans', style: 'Thin', weight: 150, names: ['MiSans-Thin', 'MiSans Thin'] },
  { name: 'HarmonyOS Sans SC', style: 'Thin', weight: 250, url: './fonts/HarmonyOS_Sans_SC_Thin.ttf' },
  { name: 'Noto Sans SC', style: 'Thin', weight: 100, variationSettings: '"wght" 100', names: ['NotoSansSCThin', 'NotoSansSC-Thin', 'Noto Sans SC Thin', 'NotoSansCJKsc-Thin'] },
  { name: '微软雅黑', style: 'Light', weight: 300, names: ['MicrosoftYaHeiLight', 'Microsoft YaHei Light'] },
  { name: '等线', style: 'Light', weight: 300, names: ['DengXian-Light', 'DengXian Light'] },
  { name: '苹方 SC', style: 'Ultralight', weight: 100, names: ['PingFangSC-Ultralight', 'PingFang SC Ultralight'] },
  { name: '冬青黑体', style: 'W3', weight: 300, names: ['HiraginoSansGB-W3', 'Hiragino Sans GB W3'] },
];
const available = [];
const palette = [[36,105,84],[186,91,53],[69,106,170],[152,76,135],[161,128,35],[30,137,143],[110,100,176],[164,68,74]];
let sequence = 0, frame, renderEpoch=0;

function option(font, loaded, detail, selected=loaded) {
  const label = document.createElement('label'); label.className = 'font-choice';
  const input = document.createElement('input'); input.type = 'checkbox'; input.checked = selected;
  font.input = input;font.loaded=loaded;font.label=label;
  const text = document.createElement('span'); text.textContent = `${font.name} · ${font.style}`;
  const status = document.createElement('small'); status.textContent = loaded ? (font.url ? '内置' : '已加载') : '未加载';
  font.status=status;
  label.title = detail; label.append(input, text, status); $('fonts').append(label);
  input.addEventListener('change',()=>{
    if(input.checked && !font.loaded) ensureFont(font);
    else schedule();
  });
}

async function ensureFont(font) {
  if(font.loaded || font.pending) return font.pending;
  font.status.textContent='加载中…';
  font.pending=(async()=>{
    const loaded=await loadFont(font);
    if(loaded) {
      Object.assign(font,loaded);font.loaded=true;
      font.status.textContent=font.url?'内置':'已加载';font.label.title=font.source;
    } else {
      font.input.checked=false;font.input.disabled=true;font.label.classList.add('unavailable');
      font.status.textContent='未找到';font.label.title='未找到指定字重，或浏览器禁止本地字体访问';
    }
    schedule();
  })();
  return font.pending;
}

async function loadFont(spec) {
  const font = { ...spec, alias: `ThinStudy${sequence++}` };
  const sources = spec.url ? [`url("${spec.url}")`] : spec.names.map(name => `local("${name}")`);
  for (const source of sources) {
    try {
      const face = await new FontFace(font.alias, source, { weight: String(font.weight), variationSettings: font.variationSettings || 'normal' }).load();
      document.fonts.add(face); font.source = source;
      return font;
    } catch { /* Try only explicit face names, never a generic-family fallback. */ }
  }
  return null;
}

async function raster(char, font, cancelled) {
  const size = 384, canvas = document.createElement('canvas'); canvas.width = canvas.height = size;
  const ctx = canvas.getContext('2d', { willReadFrequently: true });
  const scale = Number($('scale').value),gridSize=Number($('grid-size').value),connectivity=Number($('connectivity').value);
  let pixels = size * scale;
  ctx.font = `${font.weight} ${pixels}px "${font.alias}"`;
  let m = ctx.measureText(char);
  if ($('layout').value === 'ink') {
    pixels *= size * scale / Math.max(m.actualBoundingBoxLeft + m.actualBoundingBoxRight, m.actualBoundingBoxAscent + m.actualBoundingBoxDescent);
    ctx.font = `${font.weight} ${pixels}px "${font.alias}"`; m = ctx.measureText(char);
  }
  ctx.fillStyle = '#fff'; ctx.fillRect(0, 0, size, size); ctx.fillStyle = '#222';
  // Metrics use black ink; the display is not artificially thinned or stroked.
  ctx.fillStyle = '#000';
  ctx.fillText(char, (size + m.actualBoundingBoxLeft - m.actualBoundingBoxRight) / 2,
    (size + m.actualBoundingBoxAscent - m.actualBoundingBoxDescent) / 2);
  let data = ctx.getImageData(0, 0, size, size);
  const result = analyze(data.data, size, Number($('threshold').value));
  const metric=$('objective').value,base={rgba:data.data,labels:result.labels,size,count:result.count};
  if ($('mode').value === 'plan') {
    let tuned=null;
    if($('tune').checked) {
      tuned=await searchPlacement(base,
        {gridSize,connectivity,metric,cancelled,
          yieldControl:()=>new Promise(resolve=>setTimeout(resolve,0))});
      if(cancelled()) return null;
      if(tuned) data={data:tuned.rgba};
    }
    const plan=tuned?.plan || allocate(createScoring(base,{gridSize,metric})(base,{factor:1,dx:0,dy:0}),{gridSize,connectivity});
    if(!plan.error) plan.pixels=pixelLoss(tuned?.labels || result.labels,size,result.count,gridSize,plan.rooms);
    const pair=document.createElement('div');pair.className='plan-pair';
    if(plan.error) {pair.className='empty';pair.textContent=plan.error;}
    else for(const overlay of [false,true]) {
      const figure=document.createElement('figure'),view=document.createElement('canvas');view.width=view.height=size;
      drawPlan(view,data.data,plan,overlay);
      view.setAttribute('role','img');view.setAttribute('aria-label',`${font.name}：${overlay?'汉字叠加':'房间轮廓'}`);
      const caption=document.createElement('figcaption');caption.textContent=overlay?'汉字叠加':'房间轮廓';
      figure.append(view,caption);pair.append(figure);
    }
    return {canvas:pair,...result,plan,tuned,metric};
  }
  if ($('mode').value === 'skeleton') {
    const skeleton=skeletonize(result.labels,size);
    for(let p=0;p<skeleton.length;p++) {
      const rgb=skeleton[p] ? palette[(skeleton[p]-1)%palette.length] : [255,255,255];
      for(let c=0;c<3;c++) data.data[p*4+c]=rgb[c];
    }
    ctx.putImageData(data,0,0);
  }
  if ($('mode').value === 'components') {
    for (let i = 0; i < result.labels.length; i++) {
      const label = result.labels[i];
      if (!label) { data.data[4*i] = data.data[4*i+1] = data.data[4*i+2] = 255; continue; }
      const rgb = palette[(label-1)%palette.length];
      for (let j=0;j<3;j++) data.data[4*i+j] = rgb[j];
    }
    ctx.putImageData(data, 0, 0);
  }
  if ($('grid').checked) {
    ctx.lineWidth = 1; ctx.strokeStyle = '#9eac9d66'; ctx.beginPath();
    for (let i=1;i<gridSize;i++) { ctx.moveTo(i*size/gridSize,0); ctx.lineTo(i*size/gridSize,size); ctx.moveTo(0,i*size/gridSize); ctx.lineTo(size,i*size/gridSize); }
    ctx.stroke();
  }
  canvas.setAttribute('role','img'); canvas.setAttribute('aria-label', `${char}，${font.name} ${font.style}，${result.count} 个连通块`);
  return { canvas, ...result };
}

async function render() {
  const epoch=++renderEpoch,cancelled=()=>epoch!==renderEpoch;
  const chars = characters($('characters').value), fonts = available.filter(f => f.loaded && f.input.checked);
  $('grid-stamp').textContent=`${$('grid-size').value} × ${$('grid-size').value}`;
  $('grid').disabled=$('mode').value==='plan';
  $('plan-guide').hidden=$('mode').value!=='plan';
  $('tune').disabled=$('mode').value!=='plan';
  $('objective').disabled=$('mode').value!=='plan';
  $('connectivity').disabled=$('mode').value!=='plan';
  $('threshold-value').value = $('threshold').value;
  $('status').textContent = `${chars.length} 个汉字 × ${fonts.length} 款字体 · 左右滑动对比`;
  const fragment = $('results');fragment.replaceChildren();
  for (const [i, char] of chars.entries()) {
    const section = document.createElement('section'); section.className='comparison';
    const title = document.createElement('h3'); title.className='row-title'; title.textContent=char;
    const number = document.createElement('span'); number.textContent=String(i+1).padStart(2,'0'); title.prepend(number);
    const cards=document.createElement('div'); cards.className='cards';
    section.append(title,cards);fragment.append(section);
    for (const font of fonts) {
      if($('tune').checked && $('mode').value==='plan')
        $('status').textContent=`微调计算中：汉字 ${i+1} / ${chars.length} · ${font.name}`;
      const result=await raster(char,font,cancelled);
      if(cancelled() || !result) return;
      const card=document.createElement('article'); card.className=`card${result.plan?' plan-card':''}`;
      const head=document.createElement('div'); head.className='card-head';
      const name=document.createElement('h3'); name.textContent=font.name;
      const style=document.createElement('p'); style.textContent=`${font.style} · ${font.url?'页面字体':font.custom?'临时字体文件':'本机指定字重'}`;
      head.append(name,style);
      const metrics=document.createElement('div'); metrics.className='metrics';
      const blocks=document.createElement('strong'); blocks.textContent=`${result.count} 个连通块`;
      const coverage=document.createElement('span'); coverage.textContent=result.plan
        ? result.plan.error || `${result.metric==='centerline'?'平滑损失':'墨迹越界'} ${percent(result.plan.outside)} · 占用 ${result.plan.occupied} 格 · 空白 ${result.plan.empty} 格`
        : `墨迹 ${(result.coverage*100).toFixed(1)}%`;
      if(result.plan) coverage.title='先最小化所选损失，同损失时最小化占用格数；每个房间非空、连通且不重叠';
      metrics.append(blocks,coverage); card.append(head,result.canvas,metrics); cards.append(card);
      if(result.plan && !result.plan.error) {
        if(result.metric==='centerline') {
          const actual=document.createElement('p');actual.className='optimality';
          actual.textContent=`实际墨迹越界 ${result.plan.pixels.lost} 像素（${percent(result.plan.pixels.outside)}），仅供对照，不是当前优化目标。`;card.append(actual);
        }
        const proof=document.createElement('p');proof.className='optimality';
        proof.textContent=result.plan.optimal?`当前格网下 · ${result.plan.connectivity} 连通 · 所选损失已达最小 · ${result.plan.areaOptimal?'同损失下占用已达最小':'占用格数尚未证明最小'}`
          :`尚未证明最优 · 理论下界 ${percent(result.plan.lowerBound)} · 与下界相差 ${(result.plan.boundGap*100).toFixed(2)} 个百分点`;
        card.append(proof);
        if(result.tuned) {
          const {placement:p,tuning:t}=result.tuned;
          const adjustment=document.createElement('p');adjustment.className='optimality';
          const unit=result.metric==='centerline'?'中心线点当量':'像素';
          const format=value=>result.metric==='centerline'?(value/CENTERLINE_UNITS).toFixed(3):value;
          adjustment.textContent=`微调：大小不变，右移 ${p.dx}px，下移 ${p.dy}px · 损失 ${format(t.baselineLost)} → ${format(result.plan.lostInk)} ${unit}。${t.areaOptimal?'已确认采样范围内所选损失及占用最优':t.optimal?'所选损失已确认最小，占用尚未全部证明':'采样范围内目前最佳，尚未全部证明'}（已计算 ${t.evaluated} 个组合）。`;
          card.append(adjustment);
        }
      }
    }
    if($('tune').checked) {
      $('status').textContent=`微调计算中：${i+1} / ${chars.length} 个汉字`;
      await new Promise(resolve=>setTimeout(resolve,0));
      if(cancelled()) return;
    }
  }
  if (!chars.length || !fonts.length) {
    const empty=document.createElement('p'); empty.className='empty'; empty.textContent='请输入汉字，并至少选择一款可用字体。'; fragment.replaceChildren(empty);
  }
  $('status').textContent=`${chars.length} 个汉字 × ${fonts.length} 款字体 · 左右滑动对比`;
}
function schedule() { renderEpoch++;cancelAnimationFrame(frame); frame=requestAnimationFrame(render); }
document.querySelector('.controls').addEventListener('input', event => { if (event.target.id !== 'font-file') schedule(); });
$('font-file').addEventListener('change', async event => {
  const messages=[];
  for (const file of event.target.files) {
    if(file.size>40*1024*1024) { messages.push(`${file.name}：超过 40 MB`); continue; }
    try {
      const font={name:file.name,style:'文件默认字重',weight:400,custom:true,alias:`ThinStudy${sequence++}`};
      const face=await new FontFace(font.alias,await file.arrayBuffer()).load(); document.fonts.add(face);
      available.push(font); option(font,true,'本页临时加载；不保证包含所有汉字，缺字可能由浏览器回退'); messages.push(`${file.name}：已加载`);
    } catch { messages.push(`${file.name}：字体无法读取`); }
  }
  $('file-status').textContent=messages.join('；'); event.target.value=''; schedule();
});
for(let i=0;i<specs.length;i++) {
  const font={...specs[i]};available.push(font);
  option(font,false,'勾选后加载指定字重',i<3);
}
await Promise.all(available.filter(font=>font.input.checked).map(ensureFont));
schedule();
