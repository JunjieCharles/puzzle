// Opaque grayscale input: black contributes 1, white contributes 0.
// No stored character-to-projection data.
export function project(rgba, size) {
  const rows = new Array(size).fill(0), cols = new Array(size).fill(0);
  for (let y = 0; y < size; y++) for (let x = 0; x < size; x++) {
    // Canvas draws black on opaque white, so R = G = B.
    const darkness = 1 - rgba[(y * size + x) * 4] / 255;
    rows[y] += darkness; cols[x] += darkness;
  }
  return { rows, cols, total: rows.reduce((a, b) => a + b, 0) };
}
