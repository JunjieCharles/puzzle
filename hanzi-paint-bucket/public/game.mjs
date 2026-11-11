import {decryptPuzzle} from './decrypt.mjs?v=20261111-noto-212';
import {loadResource, loadJsonResource} from './load-resource.mjs?v=20261111-noto-212';
import {validateProgress, encodeSave, decodeSave, nextLevel} from './state.mjs?v=20261111-noto-212';
const $ = id => document.getElementById(id);
const RELEASE = '20261111-noto-212';
const KEY = 'hanzi-paint-bucket.progress.v1';
let bank, passed = new Set(), current = 0, page = 0, pageSize = 30, routeTicket = 0;
let timer, composing = false, checking = false, revealed = false, loading;
let prepared = false, preparing;
let uiFontsReady = false;
const resourceProgress = {data:0, tutorial:0};
function updateLoading(kind, value) {
  resourceProgress[kind] = value;
  if (!preparing) return;
  const label = `加载中 ${Math.min(99, Math.floor(resourceProgress.data * 95 + resourceProgress.tutorial * 5))}%`;
  $('start-label').textContent = label;
  if (!$('levels').hidden) $('levels-status').textContent = label;
}
async function prepareGame() {
  if (prepared) return;
  if (!preparing) {
    $('start-game').disabled = true; $('start-label').textContent = '加载中…';
    preparing = Promise.all([loadBank(), loadTutorial(), loadUiFonts()]).then(()=>{
      prepared = true; $('start-label').textContent = '开始游戏';
    }).catch(error=>{
      $('start-label').textContent = '加载失败，点击重试'; throw error;
    }).finally(()=>{preparing = null; $('start-game').disabled = false;});
  }
  return preparing;
}
async function loadUiFonts() {
  if (uiFontsReady) return;
  const faces = await Promise.all([
    ['Regular', '400'], ['Medium', '500 900']
  ].map(async ([name, weight]) => {
    const bytes = await loadResource(`./fonts/NotoSansSC-UI-${name}.woff2?v=${RELEASE}`);
    return new FontFace('Noto Sans SC', bytes, {weight}).load();
  }));
  faces.forEach(face => document.fonts.add(face));
  uiFontsReady = true;
}
const unlocked = () => Math.min(bank.puzzles.length, passed.size + 3);
const record = () => ({revision: bank.revision, passed: [...passed].sort((a,b)=>a-b)});
function mergeStored() {
  try {
    const raw = localStorage.getItem(KEY);
    if (raw) for (const n of validateProgress(JSON.parse(raw), bank).passed) passed.add(n);
  } catch { /* Incompatible old revisions do not apply to this bank. */ }
}
async function persist() {
  const write = () => {
    mergeStored();
    try {localStorage.setItem(KEY, JSON.stringify(record())); $('save-warning').hidden = true;}
    catch {$('save-warning').hidden = false;}
  };
  try { if (navigator.locks) await navigator.locks.request(KEY, write); else write(); }
  catch {write();}
}
async function loadBank() {
  if (bank) return bank;
  if (!loading) loading = (async () => {
    const data = await loadJsonResource(`./levels.json.gz?v=${RELEASE}`, `./levels.json?v=${RELEASE}`, value=>updateLoading('data', value));
    if (data.version !== 'paint-v4' || !data.puzzles?.length) throw new Error('题目格式无效');
    bank = data; mergeStored(); return bank;
  })().finally(()=>{loading = null;});
  return loading;
}
function show(view) {
  for (const section of document.querySelectorAll('.view')) section.hidden = section.id !== view;
}
function navigate(hash, replace = false) {
  if (replace) {history.replaceState(history.state, '', '#' + hash); render();}
  else location.hash = hash;
}
function clearPlay() {
  clearTimeout(timer);
  checking = false; revealed = false; composing = false;
  $('board').replaceChildren(); $('board').className = 'paint-board';
  $('feedback').textContent = ''; $('submit').hidden = false; $('submit').disabled = false; $('submit').style.visibility = '';
  $('next').hidden = true; $('reveal').textContent = '查看答案'; $('reveal').disabled = false;
  $('word-entry').value = ''; $('word-entry').readOnly = false;
  $('word-entry').className = '';
}
function measurePage() {
  const width = $('level-grid').clientWidth || innerWidth - 48;
  const columns = Math.max(3, Math.floor((width + 12) / 92));
  $('level-grid').style.setProperty('--columns', columns);
  const rows = Math.max(2, Math.floor((innerHeight - 300) / 84));
  return columns * rows;
}
function drawLevels() {
  pageSize = measurePage();
  page = Math.max(0, Math.min(page, Math.ceil(bank.puzzles.length/pageSize)-1));
  $('levels-count').textContent = `${passed.size} / ${bank.puzzles.length}`;
  $('level-grid').replaceChildren();
  for (let n=page*pageSize+1; n<=Math.min((page+1)*pageSize,bank.puzzles.length); n++) {
    const button = document.createElement('button'); button.className = 'level-tile';
    button.textContent = n; button.disabled = n > unlocked();
    if (passed.has(n)) button.classList.add('passed');
    button.setAttribute('aria-label', `第 ${n} 关${passed.has(n)?'，已通过':n>unlocked()?'，未解锁':''}`);
    if (n === nextLevel(passed,0,bank.puzzles.length)) {button.classList.add('current'); button.setAttribute('aria-current','step');}
    button.onclick = () => navigate('play/'+n); $('level-grid').append(button);
  }
  $('page-select').replaceChildren();
  for(let i=0;i<Math.ceil(bank.puzzles.length/pageSize);i++) {
    const option = new Option(`${i*pageSize+1}–${Math.min((i+1)*pageSize,bank.puzzles.length)}`,i); $('page-select').add(option);
  }
  $('page-select').value = page;
  $('page-previous').disabled = page===0;
  $('page-next').disabled = (page+1)*pageSize >= bank.puzzles.length;
}
function showWord(result) {
  Array.from(result.word).forEach((char,i)=>{
    const cell=$('board').children[i];
    const glyph=cell.querySelector('.correct-glyph');
    glyph.src=result.strokes[i];glyph.alt=char;cell.classList.add('solved');
  });
}
function hideWord() {
  for(const cell of $('board').children){cell.classList.remove('solved');const glyph=cell.querySelector('.correct-glyph');glyph.removeAttribute('src');glyph.alt='';}
}
function drawPlay(n) {
  current=n; const puzzle=bank.puzzles[n-1];
  $('level-title').textContent=`第 ${n} 关`; $('level-count').textContent=`${passed.size} / ${bank.puzzles.length}`;
  $('progress').max=bank.puzzles.length; $('progress').value=passed.size;
  for(let i=0;i<puzzle.images.length;i++) {
    const cell=document.createElement('div'); cell.className='paint-cell';
    const img=document.createElement('img'); img.src=puzzle.images[i]; img.alt=`第 ${i+1} 个字的涂色`; img.draggable=false;
    const glyph=document.createElement('img');glyph.className='correct-glyph';glyph.alt='';
    cell.append(img,glyph); $('board').append(cell);
  }
  $('previous').disabled=n===1; $('review-next').disabled=n>=unlocked();
  $('reveal').hidden=!passed.has(n);
  if (!$('help-dialog').open && !$('save-dialog').open) $('word-entry').focus({preventScroll:true});
}
async function render() {
  const ticket=++routeTicket; clearPlay();
  const hash=location.hash.slice(1)||'home';
  if(hash==='home') {show('home');prepareGame().catch(()=>{});return;}
  show('levels'); $('levels-status').textContent='加载中…'; $('retry').hidden=true;
  try {await prepareGame();} catch(error) {if(ticket===routeTicket){$('levels-status').textContent=error.message;$('retry').hidden=false;} return;}
  if(ticket!==routeTicket)return;
  mergeStored(); $('levels-status').textContent='';
  if(hash==='levels') {pageSize=measurePage();page=Math.floor((unlocked()-1)/pageSize);drawLevels();return;}
  if(hash==='complete'&&passed.size===bank.puzzles.length) {show('complete');$('complete-count').textContent=`${passed.size} / ${bank.puzzles.length}`;return;}
  const match=/^play\/(\d+)$/.exec(hash), n=match?Number(match[1]):0;
  if(n<1||n>unlocked()) {navigate('levels',true);return;}
  show('play');drawPlay(n);
}
$('puzzle-form').addEventListener('submit', async event => {
  event.preventDefault(); if(composing||checking||revealed||$('word-entry').readOnly)return;
  const word=$('word-entry').value.trim(), puzzle=bank.puzzles[current-1], ticket=routeTicket;
  if(Array.from(word).length!==puzzle.images.length||!/^\p{Script=Han}+$/u.test(word)) {$('feedback').textContent=`请输入 ${puzzle.images.length} 字词语`;$('word-entry').className='wrong';return;}
  checking=true; $('submit').disabled=true;
  try {
    const result=await decryptPuzzle(puzzle,bank.encryption), correct=word===result.word;
    if(ticket!==routeTicket)return;
    // If the player edits while decrypting, ignore the stale check.
    if($('word-entry').value.trim()!==word)return;
    if(!correct){$('feedback').textContent='再想一想';$('word-entry').className='wrong';return;}
    passed.add(current); await persist(); if(ticket!==routeTicket)return;
    $('word-entry').readOnly=true; $('word-entry').className='correct';showWord(result);
    $('board').className='paint-board correct'; $('feedback').textContent='回答正确！';
    $('submit').hidden=true; $('next').hidden=false;
    timer=setTimeout(()=>{const next=nextLevel(passed,current,bank.puzzles.length);navigate(next?'play/'+next:'complete',true);},900);
  } catch {if(ticket===routeTicket)$('feedback').textContent='暂时无法校验，请重试';}
  finally {if(ticket===routeTicket){checking=false;$('submit').disabled=false;}}
});
$('word-entry').addEventListener('compositionstart',()=>{composing=true;});
$('word-entry').addEventListener('compositionend',()=>{composing=false;});
$('word-entry').addEventListener('input',()=>{$('word-entry').className='';$('feedback').textContent='';});
$('previous').onclick=()=>navigate('play/'+(current-1),true);
$('review-next').onclick=()=>navigate('play/'+(current+1),true);
$('page-previous').onclick=()=>{page--;drawLevels();};
$('page-next').onclick=()=>{page++;drawLevels();};
$('page-select').onchange=event=>{page=Number(event.target.value);drawLevels();};
$('retry').onclick=render;
$('start-game').onclick=()=>{if(prepared)navigate('levels');else prepareGame().catch(()=>{});};
window.addEventListener('resize',()=>{if(bank&&!$('levels').hidden){const first=page*pageSize;pageSize=measurePage();page=Math.floor(first/pageSize);drawLevels();}});
window.addEventListener('hashchange',render);
window.addEventListener('pagehide',()=>{routeTicket++;clearPlay();});
window.addEventListener('pageshow',event=>{if(event.persisted)render();});
$('reveal').onclick=async()=>{
  if(!passed.has(current)||checking||$('word-entry').readOnly&&!revealed)return;
  if(revealed){revealed=false;hideWord();$('word-entry').value='';$('word-entry').readOnly=false;$('reveal').textContent='查看答案';$('submit').style.visibility='';$('feedback').textContent='';return;}
  const ticket=routeTicket;
  $('reveal').disabled=true;checking=true;$('submit').disabled=true;
  try {
    const result=await decryptPuzzle(bank.puzzles[current-1],bank.encryption);
    if(ticket!==routeTicket)return;
    showWord(result);$('word-entry').value='';$('word-entry').readOnly=true;
    revealed=true;$('reveal').disabled=false;$('reveal').textContent='隐藏答案';$('submit').style.visibility='hidden';
  } catch {if(ticket===routeTicket)$('feedback').textContent='暂时无法查看，请重试';}
  finally {if(ticket===routeTicket){checking=false;$('reveal').disabled=false;$('submit').disabled=false;}}
};
for(const kind of ['help','save']) $(kind+'-open').onclick=()=>$(kind+'-dialog').showModal();
$('warning-export').onclick=()=>$('save-dialog').showModal();
$('save-export').onclick=async()=>{
  try {await loadBank();mergeStored();$('save-code').value=await encodeSave(record(),bank);
    try {await navigator.clipboard.writeText($('save-code').value);$('save-status').textContent='存档已复制';}
    catch {$('save-code').select();$('save-status').textContent='存档已生成，请手动复制';}
  } catch(error){$('save-status').textContent=error.message;}
};
$('save-import').onclick=async()=>{
  try {await loadBank();const value=await decodeSave($('save-code').value,bank);value.passed.forEach(n=>passed.add(n));await persist();$('save-status').textContent='存档已合并';render();}
  catch(error){$('save-status').textContent=error.message;}
};
let tutorialReady;
function loadTutorial() {
  tutorialReady ||= loadResource(`./tutorial.json?v=${RELEASE}`, value=>updateLoading('tutorial', value))
    .then(bytes=>JSON.parse(new TextDecoder().decode(bytes)))
    .catch(error=>{tutorialReady=null;throw error;});
  return tutorialReady;
}
async function helpDemo() {
  $('help-status').textContent='加载中…';
  try {
    const tutorial=await loadTutorial();
    if (!$('help-dialog').open) return;
    $('help-demo').replaceChildren();
    $('help-dialog').classList.remove('demo-ready');
    for(let i=0;i<2;i++) {
      const cell=document.createElement('div');cell.className='paint-cell';
      const paint=document.createElement('img');paint.src=tutorial.paint[i];paint.alt='';
      const strokes=document.createElement('img');strokes.src=tutorial.strokes[i];strokes.alt='';strokes.className='demo-strokes';
      cell.append(paint,strokes);$('help-demo').append(cell);
    }
    $('help-dialog').classList.add('demo-ready');
    $('help-status').textContent='';
  }catch{$('help-status').textContent='示例加载失败，请重新打开帮助';}
}
$('help-open').onclick=()=>{$('help-dialog').showModal();helpDemo();};
$('help-dialog').addEventListener('close',()=>{$('help-dialog').classList.remove('demo-ready');$('help-demo').replaceChildren();});
render();
