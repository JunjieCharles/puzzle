import { enclosedRegions } from './fill.mjs';
export function analyzeGlyph(char, family, weight) {
  const size = 480, canvas = document.createElement('canvas');
  canvas.width = canvas.height = size;
  const ctx = canvas.getContext('2d', { willReadFrequently: true });
  ctx.font = `${weight} 400px "${family}"`;
  const m = ctx.measureText(char);
  ctx.fillText(char, (size - m.actualBoundingBoxRight + m.actualBoundingBoxLeft) / 2, (size + m.actualBoundingBoxAscent - m.actualBoundingBoxDescent) / 2);
  const original = ctx.getImageData(0, 0, size, size);
  const alpha = new Uint8Array(size * size);
  for (let p = 0; p < alpha.length; p++) alpha[p] = original.data[p * 4 + 3];
  const { labels, count } = enclosedRegions(alpha, size, size);
  return {canvas, ctx, alpha, labels, count, size};
}
