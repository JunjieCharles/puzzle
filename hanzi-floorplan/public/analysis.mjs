export function characters(value) {
  return [...new Set([...value].filter(char => /\p{Script=Han}/u.test(char)))].slice(0, 12);
}

export function analyze(rgba, size, threshold = 96) {
  const labels = new Int32Array(size * size);
  const queue = new Int32Array(size * size);
  let count = 0, total = 0;
  for (let i = 0; i < labels.length; i++) {
    const ink = (255 - rgba[4 * i]) * rgba[4 * i + 3] / 255;
    total += ink / 255;
    if (ink >= threshold) labels[i] = -1;
  }
  for (let i = 0; i < labels.length; i++) {
    if (labels[i] !== -1) continue;
    count++; let start = 0, end = 1; queue[0] = i; labels[i] = count;
    while (start < end) {
      const pos = queue[start++], x = pos % size, y = Math.floor(pos / size);
      for (let dy = -1; dy <= 1; dy++) for (let dx = -1; dx <= 1; dx++) {
        const nx = x + dx, ny = y + dy;
        if (nx < 0 || ny < 0 || nx >= size || ny >= size) continue;
        const next = ny * size + nx;
        if (labels[next] === -1) { labels[next] = count; queue[end++] = next; }
      }
    }
  }
  return { labels, count, coverage: total / (size * size) };
}
