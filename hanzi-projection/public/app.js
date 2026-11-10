import { project } from './projection.mjs';
const $ = id => document.getElementById(id);
const fontSpecs = [
  ['宋体', 'SimSun'], ['黑体', 'SimHei'], ['楷体', 'KaiTi'],
  ['仿宋', 'FangSong'], ['微软雅黑', 'Microsoft YaHei'], ['等线', 'DengXian'],
  ['苹方', 'PingFang SC'], ['冬青黑体', 'Hiragino Sans GB'],
  ['思源黑体', 'Source Han Sans CN'],
];
const defaultFonts = new Set(['黑体', '微软雅黑', '思源黑体']);
const available = [];
// local() fails explicitly if absent, unlike a CSS font stack's silent fallback.
await Promise.all(fontSpecs.map(async ([label, local], index) => {
  const alias = `ComparisonFont${index}`;
  try {
    const face = await new FontFace(alias, `local("${local}")`).load();
    document.fonts.add(face); available.push({ label, alias, index });
  } catch { /* Missing fonts are listed below, never silently substituted. */ }
}));
available.sort((a, b) => a.index - b.index);
for (const [label, , index] of fontSpecs.map((s, i) => [...s, i])) {
  const found = available.find(f => f.index === index);
  const wrapper = document.createElement('label');
  const input = document.createElement('input'); input.type = 'checkbox';
  input.value = String(index); input.disabled = !found; input.checked = !!found && defaultFonts.has(label);
  wrapper.append(input, document.createTextNode(label + (found ? '' : '（未安装）')));
  $('fonts').append(wrapper);
}
if (!$('fonts').querySelector(':checked')) {
  const first = $('fonts').querySelector('input:not(:disabled)'); if (first) first.checked = true;
}
function raster(char, font, size, scale) {
  const canvas = document.createElement('canvas'); canvas.width = canvas.height = size;
  const ctx = canvas.getContext('2d', { willReadFrequently: true });
  ctx.fillStyle = 'white'; ctx.fillRect(0, 0, size, size);
  ctx.font = `${size * scale}px "${font}"`; ctx.fillStyle = 'black';
  const m = ctx.measureText(char);
  const x = (size - m.actualBoundingBoxRight + m.actualBoundingBoxLeft) / 2;
  const y = (size + m.actualBoundingBoxAscent - m.actualBoundingBoxDescent) / 2;
  ctx.fillText(char, x, y);
  const pixels = ctx.getImageData(0, 0, size, size);
  const data = project(pixels.data, size);
  canvas.className = 'glyph';
  canvas.setAttribute('aria-label', '灰度字形');
  return { canvas, ...data };
}
function plot(values, size, color, title, direction) {
  const ns = 'http://www.w3.org/2000/svg';
  const svg = document.createElementNS(ns, 'svg');
  svg.classList.add('plot', `${direction}-plot`);
  svg.setAttribute('viewBox', '0 0 100 100');
  svg.setAttribute('preserveAspectRatio', 'none');
  svg.setAttribute('role', 'img'); svg.setAttribute('aria-label', title);
  const add = (tag, attrs) => {
    const el = document.createElementNS(ns, tag);
    for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, v);
    svg.append(el);
  };
  for (const fraction of [0, 0.25, 0.5, 0.75, 1]) {
    const position = fraction * 100;
    add('line', direction === 'row'
      ? { x1: position, x2: position, y1: 0, y2: 100, stroke: '#e5e9e2' }
      : { x1: 0, x2: 100, y1: position, y2: position, stroke: '#e5e9e2' });
  }
  // Sample at pixel centers to align with the raster rows and columns.
  const points = values.map((v, i) => {
    const position = (i + 0.5) / size * 100, count = v / size * 100;
    return direction === 'row' ? `${100 - count},${position}` : `${position},${count}`;
  }).join(' ');
  add('polyline', { points, fill: 'none', stroke: color,
    'stroke-width': 1.4, 'vector-effect': 'non-scaling-stroke' });
  return svg;
}
function render() {
  const chars = [...new Set([...$('characters').value].filter(c => /\p{Script=Han}/u.test(c)))].slice(0, 12);
  const fonts = available.filter(f => $('fonts').querySelector(`input[value="${f.index}"]`).checked);
  const size = Number($('size').value);
  $('results').replaceChildren();
  $('status').textContent = `${chars.length} 个汉字 × ${fonts.length} 种字体 · ${size} × ${size} 像素 · 灰度累计：黑 = 1，白 = 0`;
  if (!chars.length || !fonts.length) {
    const p = document.createElement('p'); p.className = 'empty';
    p.textContent = '请输入汉字，并至少选择一种已安装字体。'; $('results').append(p); return;
  }
  for (const [index, char] of chars.entries()) {
    const section = document.createElement('section'); section.className = 'comparison';
    const heading = document.createElement('h2');
    heading.append(document.createTextNode(`${String(index + 1).padStart(2, '0')} / `));
    const name = document.createElement('span'); name.className = 'char-label'; name.textContent = char; heading.append(name);
    const cards = document.createElement('div'); cards.className = 'cards';
    for (const font of fonts) {
      const result = raster(char, font.alias, size, Number($('scale').value));
      const card = document.createElement('article'); card.className = 'card';
      const h = document.createElement('h3'); h.textContent = font.label;
      const weight = document.createElement('span'); weight.textContent = '常规字重'; h.append(weight);
      const metric = document.createElement('p'); metric.className = 'metrics';
      metric.textContent = `平均黑度 ${(result.total / size ** 2 * 100).toFixed(1)}% · 行峰 ${Math.max(...result.rows).toFixed(2)} · 列峰 ${Math.max(...result.cols).toFixed(2)}`;
      const diagram = document.createElement('div'); diagram.className = 'diagram';
      diagram.append(plot(result.rows, size, '#287d68', '逐行：从上到下，黑度累计向左增加', 'row'),
        result.canvas, plot(result.cols, size, '#c06b37', '逐列：从左到右，黑度累计向下增加', 'col'));
      const axes = document.createElement('p'); axes.className = 'axes';
      axes.textContent = `行：上 → 下 / 黑度 ←　列：左 → 右 / 黑度 ↓（0～${size}）`;
      card.append(h, diagram, axes, metric); cards.append(card);
    }
    section.append(heading, cards); $('results').append(section);
  }
}
let frame;
document.querySelector('.controls').addEventListener('input', event => {
  if (event.target.id === 'hide') { $('results').classList.toggle('concealed', event.target.checked); return; }
  cancelAnimationFrame(frame); frame = requestAnimationFrame(render);
});
render();
