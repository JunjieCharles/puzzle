// Production-vocabulary checks print aggregates only. Never log generated records.
import fs from "node:fs";
import assert from "node:assert/strict";
import { Vocabulary, EndlessSequence } from "../public/endless-engine.js";
const data = JSON.parse(fs.readFileSync(new URL("../public/endless-lexicon.json", import.meta.url), "utf8"));
const v = new Vocabulary(data), common = new Set(data.common), broad = new Set([...data.broad, ...data.common]);
let seed = 20261002;
const random = () => ((seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0) / 4294967296);
for (const size of [1, 2]) {
  // k distinct blocked characters can exclude at most k pairwise-disjoint witnesses.
  // 101 singles / 201 disjoint words therefore guarantee an eligible valid candidate.
  const used = new Set(); let witnesses = 0;
  for (const word of v.candidates[size]) {
    if (Array.from(word).some(c => used.has(c))) continue;
    if (!v.clueSearch(word, random)) continue;
    witnesses++; for (const c of word) used.add(c);
    if (witnesses > 100 * size) break;
  }
  assert.ok(witnesses > 100 * size, "Could not establish inexhaustibility for the frozen vocabulary");
  const sequence = new EndlessSequence(v, size), seen = new Map();
  const started = performance.now();
  let terminal;
  for (let n = 1; n <= 10000; n++) {
    const puzzle = sequence.next();
    for (const char of puzzle.solution) {
      assert.ok(!seen.has(char) || n - seen.get(char) > 100, "Cooling violation"); seen.set(char, n);
    }
    const fixed = Object.values(puzzle.clues).flat();
    assert.ok(new Set([...fixed, ...puzzle.solution]).size === fixed.length + size, "Repeated character");
    if (n <= 20) {
      const edges = answer => {
        const chars = Array.from(answer), c = puzzle.clues;
        const top = size === 1 ? [c.top] : c.top, bottom = size === 1 ? [c.bottom] : c.bottom;
        return [c.left + chars[0], chars.at(-1) + c.right,
          ...chars.flatMap((char, i) => [top[i] + char, char + bottom[i]]), ...(size === 2 ? [answer] : [])];
      };
      assert.ok(common.has(puzzle.solution) && edges(puzzle.solution).every(w => common.has(w)), "Non-common word");
      const solutions = [...broad].filter(w => Array.from(w).length === size && edges(w).every(edge => broad.has(edge)));
      assert.ok(solutions.length === 1 && solutions[0] === puzzle.solution, "Independent uniqueness check failed");
    }
    terminal = puzzle;
  }
  const ms = Math.round(performance.now() - started);
  const replay = new EndlessSequence(v, size); let recovered;
  for (let n = 0; n < 10000; n++) recovered = replay.next();
  assert.ok(JSON.stringify(recovered) === JSON.stringify(terminal), "Replay mismatch");
  console.log(JSON.stringify({ size, disjointWitnessCount: witnesses, levels: sequence.level, generationMs: ms, replayMatches: true }));
}
