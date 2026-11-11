const $=id=>document.getElementById(id);
let current=1,pages=1,pageSize=12,request=0,controller;
let anchorOrdinal=1,resizeTimer;
let fontWeight=300;
function fitLayout(){
  const cards=$('cards'),gap=12;
  const columns=Math.max(1,Math.min(6,Math.floor((cards.clientWidth+gap)/(260+gap))));
  const rows=Math.max(1,Math.min(4,Math.floor((cards.clientHeight+gap)/(210+gap))));
  cards.style.setProperty('--columns',columns);
  cards.style.setProperty('--rows',rows);
  const size=columns*rows;
  if(size!==pageSize||request===0){
    pageSize=size;
    load(Math.ceil(anchorOrdinal/pageSize),request===0?undefined:anchorOrdinal);
  }
}
async function setAnswer(card,visible){
  card.dataset.revealed=String(visible);
  const button=card.querySelector('.reveal');
  button.textContent=visible?'收起格内答案':'显示答案';button.setAttribute('aria-expanded',String(visible));
  card.querySelectorAll('canvas').forEach(canvas=>canvas.hidden=!visible);
  if(!visible)return;
  try{await document.fonts.load(`${fontWeight} 400px PreviewPuzzle`);}catch{button.textContent='字体加载失败，请重试';return;}
  if(card.dataset.revealed!=='true')return;
  card.querySelectorAll('canvas').forEach((canvas,i)=>{
    const char=Array.from(card.word)[i],ctx=canvas.getContext('2d');
    ctx.clearRect(0,0,480,480);ctx.font=`${fontWeight} 400px PreviewPuzzle`;ctx.fillStyle='#253344';
    const m=ctx.measureText(char);
    ctx.fillText(char,(480-m.actualBoundingBoxRight+m.actualBoundingBoxLeft)/2,(480+m.actualBoundingBoxAscent-m.actualBoundingBoxDescent)/2);
    canvas.setAttribute('aria-label',char);
  });
}
async function load(page,ordinal){
  anchorOrdinal=ordinal??((page-1)*pageSize+1);
  const token=++request;controller?.abort();controller=new AbortController();
  $('status').textContent='正在加载…';$('cards').replaceChildren();$('prev').disabled=$('next').disabled=true;
  try{
    const response=await fetch(`./api?page=${page}&page_size=${pageSize}`,{cache:'no-store',signal:controller.signal});
    if(!response.ok)throw new Error('读取失败');
    const data=await response.json();if(token!==request)return;
    fontWeight=data.font_weight||200;
    const areaDifficulty=data.difficulty_aggregation==='mean-paint-area-px-v1';
    $('difficulty-note').textContent=areaDifficulty ? '难度按各字涂色面积的算术平均排序，空白计 0；面积越大越简单、排序越靠前。悬停分数可查看各字面积。' : '各字覆盖率＝暗示笔画面积／完整笔画面积；整词取算术平均，各字等权，越高越简单、排序越靠前。悬停分数可查看各字覆盖率。';
    $('difficulty-note').title=$('difficulty-note').textContent;
    const idiom=data.bank_type==='idiom',multi=data.bank_type==='hsk-multi',combined=data.bank_type==='hsk-combined';
    $('bank-label').textContent=`${combined?'HSK 二字＋三字＋四字 · 至少两字非空且非单矩形 · 三字词无空白格 · 按平均涂色面积混合排序':multi?'HSK 三字及以上 · 至少两字有有效涂色':idiom?'四字成语 · 至少两字有有效涂色':'HSK 二字词'} · ${data.font} ${data.font_style} · 简单 → 困难`;
    $('bank-label').title=$('bank-label').textContent;
    $('uniqueness').textContent=`${multi||combined?'完整成语库及扩展词库，同长度匹配；空白匹配空白':idiom?'完整成语库及现有扩展四字词；空白匹配空白':'扩展词库'} · ${data.multifont_ambiguity?'六字体整词匹配 · 同有效块数 · 图形 IoU >95%、中心距离 ≤50px，或原像素规则':'逐字最大 IoU >95%、最小曼哈顿位移 <10px'}`;
    document.title=`汉字油漆桶 · ${combined?'HSK 二字＋三字＋四字':multi?'HSK 三字及以上':idiom?'成语':'HSK'}题库预览`;
    current=data.page;pages=data.pages;pageSize=data.page_size;$('total').textContent=`共 ${data.total} 题 · 每页 ${pageSize} 题`;
    $('ordinal').max=data.total;$('page').textContent=`${current} / ${pages}`;
    for(const item of data.items){
      const card=document.createElement('article');card.className='card';card.id=`puzzle-${item.ordinal}`;card.word=item.word;
      card.innerHTML='<div class="card-top"><span class="rank"></span><span class="level"></span></div><div class="glyphs"></div><div class="answer"></div><div class="card-bottom"><span class="area"></span><button class="reveal" type="button"></button></div>';
      card.querySelector('.rank').textContent=`第 ${item.ordinal} 题`;
      card.querySelector('.level').textContent=idiom?'成语':`HSK ${item.level}`;
      card.querySelector('.area').textContent=areaDifficulty ? `平均涂色面积 ${item.mean_paint_area_px.toFixed(1)} px²` : `算术平均覆盖率 ${(item.stroke_ratio*100).toFixed(1)}%`;
      card.querySelector('.area').title=areaDifficulty ? `各字涂色面积：${item.character_areas.join('、')} px²；相加后除以字数，空白计 0，越大越简单` : `各字覆盖率：${item.character_ratios.map(r=>(r*100).toFixed(1)+'%').join('、')}；相加后除以字数，各字等权，越高越简单`;
      card.querySelector('.answer').textContent=item.word;
      card.querySelector('.glyphs').dataset.length=String(Array.from(item.word).length);
      card.querySelector('.glyphs').style.setProperty('--letters',item.images.length);
      item.images.forEach((url,i)=>{const cell=document.createElement('div');cell.className='glyph-cell';const img=document.createElement('img');img.src=url;img.alt=`第 ${i+1} 个字的涂色区域`;const overlay=document.createElement('canvas');overlay.width=overlay.height=480;overlay.hidden=true;overlay.setAttribute('role','img');const hint=document.createElement('img');hint.className='implied';hint.src=item.hints[i];hint.alt='估计可由图案暗示的笔画部分';hint.hidden=!$('hints').checked;cell.append(img,overlay,hint);card.querySelector('.glyphs').append(cell);});
      card.querySelector('.reveal').onclick=()=>setAnswer(card,card.dataset.revealed!=='true');
      setAnswer(card,$('answers').checked);$('cards').append(card);
    }
    $('status').textContent='';$('prev').disabled=current===1;$('next').disabled=current===pages;
    if(ordinal)$(`puzzle-${ordinal}`)?.classList.add('highlight');
  }catch(error){if(error.name!=='AbortError'){$('status').textContent='题库加载失败，请确认本地预览服务正在运行后刷新。';}}
}
$('answers').onchange=()=>document.querySelectorAll('.card').forEach(card=>setAnswer(card,$('answers').checked));
$('hints').onchange=()=>document.querySelectorAll('.implied').forEach(image=>image.hidden=!$('hints').checked);
$('prev').onclick=()=>load(current-1);$('next').onclick=()=>load(current+1);
$('jump').onsubmit=e=>{e.preventDefault();const n=Number($('ordinal').value);if(Number.isInteger(n)&&n>=1&&n<=Number($('ordinal').max))load(Math.ceil(n/pageSize),n);};
new ResizeObserver(()=>{clearTimeout(resizeTimer);resizeTimer=setTimeout(fitLayout,120);}).observe($('cards'));
fitLayout();
