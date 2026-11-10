// Four-neighbour components: only enclosed transparent regions receive paint.
export function enclosedRegions(alpha, width, height) {
  const labels = new Int32Array(width * height);
  const queue = new Int32Array(labels.length);
  let count = 0;
  for (let start = 0; start < labels.length; start++) {
    if (alpha[start] >= 128 || labels[start]) continue;
    let head = 0, tail = 1, edge = false;
    queue[0] = start; labels[start] = -1;
    while (head < tail) {
      const p = queue[head++], x = p % width, y = Math.floor(p / width);
      if (!x || !y || x === width - 1 || y === height - 1) edge = true;
      for (const next of [x ? p - 1 : -1, x + 1 < width ? p + 1 : -1, y ? p - width : -1, y + 1 < height ? p + width : -1]) {
        if (next >= 0 && !labels[next] && alpha[next] < 128) {
          labels[next] = -1; queue[tail++] = next;
        }
      }
    }
    const id = edge ? -1 : ++count;
    for (let i = 0; i < tail; i++) labels[queue[i]] = id;
  }
  return { labels, count };
}
