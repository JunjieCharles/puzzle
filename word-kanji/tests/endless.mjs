import assert from "node:assert/strict";
import { Vocabulary, EndlessSequence, publicPuzzle, REVISION } from "../public/endless-engine.js";
import { EndlessProgress, endlessModes } from "../public/endless.js";
import { encodeSave, decodeSave } from "../public/save-code.js";

// Artificial disconnected word graphs, generated in memory; no production solutions.
export function fixture(size, count = 101) {
  const words = new Set();
  for (let n = 0; n < count; n++) {
    const c = Array.from({ length: 8 }, (_, i) => String.fromCodePoint(0x3400 + n * 8 + i));
    if (size === 1) for (const w of [c[0], c[2] + c[0], c[3] + c[0], c[0] + c[4], c[0] + c[5]]) words.add(w);
    else for (const w of [c[0] + c[1], c[2] + c[0], c[3] + c[1], c[0] + c[4], c[1] + c[5], c[6] + c[0], c[1] + c[7]]) words.add(w);
  }
  return { version: "endless-lexicon-v1", common: [...words], broad: [...words] };
}
for (const size of [1, 2]) {
  const data = fixture(size), v = new Vocabulary(data), s = new EndlessSequence(v, size);
  const last = new Map(), sequence = [];
  for (let n = 1; n <= 310; n++) {
    const puzzle = s.next();
    for (const c of puzzle.solution) {
      assert.ok(!last.has(c) || n - last.get(c) > 100);
      last.set(c, n);
    }
    const clues = Object.values(puzzle.clues).flat();
    assert.equal(new Set([...clues, ...puzzle.solution]).size, clues.length + size);
    assert.deepEqual(v.solutions(puzzle.clues, size), [puzzle.solution]);
    sequence.push(puzzle);
  }
  assert.equal(sequence[0].solution, sequence[101].solution); // First re-use exactly n+101.
  assert.equal(s.recent.length, 100);
  const replay = new EndlessSequence(new Vocabulary({ ...data, common: [...data.common].reverse(), broad: [...data.broad].reverse() }), size);
  for (let n = 0; n < sequence.length; n++) assert.deepEqual(replay.next(), sequence[n]);
  const exposed = await publicPuzzle(sequence[0], size);
  assert.deepEqual(Object.keys(exposed).sort(), ["check", "clues", "id", "salt"]);
  assert.deepEqual(exposed, await publicPuzzle(sequence[0], size));
  const exhausted = new EndlessSequence(new Vocabulary(fixture(size, 100)), size);
  for (let n = 0; n < 100; n++) exhausted.next();
  assert.throws(() => exhausted.next(), /无法继续/);
  assert.equal(exhausted.level, 100);
  // Exhaustive fallback still works when the fast random stage finds nothing.
  const original = v.clueSearch.bind(v);
  v.clueSearch = (word, random, exhaustive) => exhaustive ? original(word, random, true) : null;
  assert.ok(new EndlessSequence(v, size).next());
}
{
  const data = fixture(2, 1), base = new Vocabulary(data);
  const clue = new EndlessSequence(base, 2).next().clues;
  const rival = String.fromCodePoint(0x4500);
  const extra = [rival + rival, ...clue.top.map(c => c + rival), ...clue.bottom.map(c => rival + c), clue.left + rival, rival + clue.right];
  assert.equal(new Vocabulary({ ...data, broad: [...data.broad, ...extra] }).solutions(clue, 2).length, 2);
}
const stored = new Map(), storage = { getItem: k => stored.get(k) ?? null, setItem: (k, v) => stored.set(k, v) };
const progress = new EndlessProgress(storage), mode = endlessModes[0];
assert.equal(progress.read(mode).next, 1);
await progress.merge(mode, { revision: REVISION, next: 101 });
await progress.merge(mode, { revision: REVISION, next: 7 });
assert.equal(new EndlessProgress(storage).read(mode).next, 101);
assert.equal(progress.read(endlessModes[1]).next, 1);
assert.deepEqual(Object.keys(JSON.parse(stored.get(progress.key(mode)))).sort(), ["next", "revision"]);
const code = await encodeSave({ [mode]: progress.read(mode), "campaign-one-standard": { revision: "a".repeat(16), completed: 0, pending: [1, 2, 3] } });
assert.equal((await decodeSave(code))[mode].next, 101);
for (const next of [0, -1, 1.5, Number.MAX_SAFE_INTEGER, "2"]) {
  await assert.rejects(() => progress.merge(mode, { revision: REVISION, next }));
}
await assert.rejects(() => progress.merge(mode, { revision: "unknown", next: 1 }));
const denied = new EndlessProgress({ getItem() { throw new Error(); }, setItem() { throw new Error(); } });
assert.equal(await denied.merge(mode, { revision: REVISION, next: 5 }), false);
assert.equal(denied.read(mode).next, 5);
console.log("Endless synthetic tests passed: determinism, cooling, uniqueness, fallback, saves.");
