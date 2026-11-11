import { analyzeGlyph } from './glyph.mjs';
export { analyzeGlyph } from './glyph.mjs';
import { ranges } from './font-coverage.mjs';
const specs = [
  { name: 'Noto Sans SC', weight: 200, source: 'url("./fonts/NotoSansSC-Thin.ttf")' },
];
const $ = (id) => document.getElementById(id);
const palette = ['#efb641', '#49b9ae', '#f18d83', '#8d9ee0', '#b8ce68', '#be8cbf'];
const rgb = (hex) => [1, 3, 5].map(i => parseInt(hex.slice(i, i + 2), 16));
let version = 0;
function characters() { return Array.from($('text').value).filter(c => !/\s/u.test(c)); }

function draw(char, spec) {
  const {canvas, ctx, alpha, labels, count, size} = analyzeGlyph(char, spec.family, spec.weight);
  canvas.setAttribute('role', 'img');
  canvas.setAttribute('aria-label', `${spec.name}：${char}的闭合区域涂色`);
  const colors = ($('multi').checked ? palette : [$('color').value]).map(rgb);
  const result = ctx.createImageData(size, size), ink = [37, 51, 68];
  for (let p = 0; p < alpha.length; p++) {
    const color = labels[p] > 0 ? colors[(labels[p] - 1) % colors.length] : [255, 255, 255];
    const a = $('ink').checked ? alpha[p] / 255 : 0;
    for (let c = 0; c < 3; c++) result.data[p * 4 + c] = color[c] * (1 - a) + ink[c] * a;
    result.data[p * 4 + 3] = 255;
  }
  ctx.putImageData(result, 0, 0);
  canvas.title = count ? `${count} 个闭合区域` : '没有闭合区域';
  return canvas;
}
async function render() {
  const current = ++version, chars = characters();
  $('count').textContent = chars.length > 16 ? `已输入 ${chars.length} 字，展示前 16 字` : `${chars.length} / 16 字`;
  for (const spec of specs) {
    spec.grid.replaceChildren();
    if (!spec.ready || !chars.length) {
      const empty = document.createElement('p'); empty.className = 'empty';
      empty.textContent = spec.ready ? '输入文字，看看颜色会停在哪里。' : '等待 Noto Sans SC Thin 字体加载。';
      spec.grid.append(empty); continue;
    }
    for (const char of chars.slice(0, 16)) {
      await new Promise(resolve => requestAnimationFrame(resolve));
      if (current !== version) return;
      if (!ranges.some(([lo, hi]) => char.codePointAt(0) >= lo && char.codePointAt(0) <= hi)) {
        const missing = document.createElement('p');
        missing.textContent = `${char}：当前字体不支持`; missing.className = 'empty';
        spec.grid.append(missing); continue;
      }
      spec.grid.append(draw(char, spec));
    }
  }
}
async function load(spec, source) {
  const ticket = spec.ticket = (spec.ticket || 0) + 1;
  spec.ready = false; spec.status.textContent = '正在加载…'; spec.status.classList.remove('error');
  render();
  try {
    const face = new FontFace(spec.family, source, { weight: String(spec.weight) });
    await face.load();
    if (spec.ticket !== ticket) return;
    if (spec.face) document.fonts.delete(spec.face);
    document.fonts.add(face); spec.face = face; spec.ready = true;
    spec.status.textContent = source instanceof ArrayBuffer ? '已加载所选文件（请确认是 Thin）' : 'Thin 已加载';
  } catch {
    if (spec.ticket !== ticket) return;
    spec.status.textContent = '字体加载失败，请刷新重试'; spec.status.classList.add('error');
  }
  render();
}
specs.forEach((spec, i) => {
  spec.family = `PaintFont${i}`;
  const panel = document.createElement('section'); panel.className = 'font-panel';
  panel.innerHTML = `<div class="panel-head"><h2>${spec.name}</h2><span class="badge">THIN</span><span class="status" role="status"></span></div><div class="glyphs"></div>`;
  spec.status = panel.querySelector('.status'); spec.grid = panel.querySelector('.glyphs');
  $('results').append(panel);
});
specs.forEach(spec => load(spec, spec.source));
let timer;
$('text').addEventListener('input', () => { ++version; clearTimeout(timer); timer = setTimeout(render, 150); });
for (const id of ['ink', 'multi', 'color']) $(id).addEventListener('input', render);
$('clear').addEventListener('click', () => { $('text').value = ''; render(); $('text').focus(); });
// Browsers may restore form fields on navigation; never restore puzzle input.
window.addEventListener('pageshow', () => { $('text').value = ''; render(); });
