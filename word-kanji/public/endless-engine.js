// All solutions are derived at runtime from generic vocabulary. Never serialize engine state.
export const REVISION = "endless-v1";
export const COOLING = 100;
export const codepointOrder = (a, b) => {
  const x = Array.from(a, c => c.codePointAt(0)), y = Array.from(b, c => c.codePointAt(0));
  for (let i = 0; i < Math.min(x.length, y.length); i++) if (x[i] !== y[i]) return x[i] - y[i];
  return x.length - y.length;
};

// Fixed FNV-1a seed expansion and Mulberry32; all arithmetic explicitly uint32.
function randomFor(text) {
  let state = 2166136261;
  for (const char of text) state = Math.imul(state ^ char.codePointAt(0), 16777619) >>> 0;
  return () => {
    state = (state + 0x6d2b79f5) >>> 0;
    let value = Math.imul(state ^ (state >>> 15), 1 | state);
    value ^= value + Math.imul(value ^ (value >>> 7), 61 | value);
    return ((value ^ (value >>> 14)) >>> 0) / 4294967296;
  };
}
function shuffle(values, random) {
  const result = [...values];
  for (let i = result.length - 1; i > 0; i--) {
    const j = Math.floor(random() * (i + 1));
    [result[i], result[j]] = [result[j], result[i]];
  }
  return result;
}
const empty = new Set();
function indexes(words) {
  const after = new Map(), before = new Map();
  for (const word of words) {
    const chars = Array.from(word);
    if (chars.length !== 2) continue;
    const [a, b] = chars;
    if (!after.has(a)) after.set(a, new Set());
    if (!before.has(b)) before.set(b, new Set());
    after.get(a).add(b); before.get(b).add(a);
  }
  return { after, before };
}
function intersection(sets) {
  const sorted = [...sets].sort((a, b) => a.size - b.size);
  return [...sorted[0]].filter(char => sorted.every(set => set.has(char)));
}

export class Vocabulary {
  constructor(data) {
    if (data.version !== "endless-lexicon-v1" || !Array.isArray(data.common) || !Array.isArray(data.broad)) throw new Error("词库格式无效");
    const common = [...new Set(data.common)].sort(codepointOrder);
    const broad = [...new Set([...data.broad, ...common])].sort(codepointOrder);
    this.common = indexes(common);
    this.audit = indexes(broad);
    this.singles = new Set(broad.filter(w => Array.from(w).length === 1));
    this.candidates = {};
    for (const size of [1, 2]) {
      this.candidates[size] = common.filter(word => {
        const chars = Array.from(word);
        return chars.length === size && new Set(chars).size === size && this.domains(word).every(d => d.length);
      });
    }
  }
  domains(word) {
    const chars = Array.from(word);
    return [...chars.map(c => this.common.before.get(c) || empty),
      ...chars.map(c => this.common.after.get(c) || empty),
      this.common.before.get(chars[0]) || empty, this.common.after.get(chars.at(-1)) || empty]
      .map(set => [...set].filter(c => !chars.includes(c)));
  }
  // Count all broad solutions, including rivals with repeated letters; stop at two.
  solutions(clues, size) {
    const { after, before } = this.audit;
    const top = size === 1 ? [clues.top] : clues.top;
    const bottom = size === 1 ? [clues.bottom] : clues.bottom;
    const domains = top.map((t, i) => intersection([
      after.get(t) || empty, before.get(bottom[i]) || empty,
      ...(i === 0 ? [after.get(clues.left) || empty] : []),
      ...(i === size - 1 ? [before.get(clues.right) || empty] : []),
    ]));
    if (size === 1) return domains[0].filter(c => this.singles.has(c)).slice(0, 2);
    const result = [];
    for (const a of domains[0]) for (const b of domains[1]) {
      if (after.get(a)?.has(b)) result.push(a + b);
      if (result.length === 2) return result;
    }
    return result;
  }
  clueSearch(word, random, exhaustive = false) {
    const size = Array.from(word).length;
    const domains = this.domains(word);
    const order = domains.map((_, i) => i).sort((a, b) => domains[a].length - domains[b].length || a - b);
    const make = chosen => ({ top: size === 1 ? chosen[0] : chosen.slice(0, size),
      bottom: size === 1 ? chosen[size] : chosen.slice(size, size * 2), left: chosen[size * 2], right: chosen[size * 2 + 1] });
    const valid = chosen => {
      const clues = make(chosen), solutions = this.solutions(clues, size);
      return solutions.length === 1 && solutions[0] === word ? clues : null;
    };
    if (!exhaustive) {
      for (let attempt = 0; attempt < 64; attempt++) {
        const chosen = [], used = new Set(word);
        for (const index of order) {
          const options = domains[index].filter(c => !used.has(c));
          if (!options.length) break;
          chosen[index] = options[Math.floor(random() * options.length)];
          used.add(chosen[index]);
        }
        if (order.every(i => chosen[i])) {
          const clues = valid(chosen);
          if (clues) return clues;
        }
      }
      return null;
    }
    const chosen = [], used = new Set(word);
    function visit(depth) {
      if (depth === order.length) return valid(chosen);
      const index = order[depth];
      for (const char of domains[index]) {
        if (used.has(char)) continue;
        chosen[index] = char; used.add(char);
        const result = visit(depth + 1);
        used.delete(char);
        if (result) return result;
      }
      return null;
    }
    return visit(0);
  }
}

export class EndlessSequence {
  constructor(vocabulary, size) {
    if (![1, 2].includes(size)) throw new Error("题型无效");
    this.vocabulary = vocabulary; this.size = size;
    this.level = 0; this.recent = []; this.blocked = new Set();
  }
  next() {
    const level = this.level + 1;
    if (!Number.isSafeInteger(level) || level >= Number.MAX_SAFE_INTEGER) throw new Error("关号超出支持范围");
    const random = randomFor(`word-kanji:${REVISION}:seed-2026-10-02:${this.size}:${level}`);
    const candidates = shuffle(this.vocabulary.candidates[this.size].filter(word =>
      !Array.from(word).some(c => this.blocked.has(c))), random);
    for (const exhaustive of [false, true]) for (const word of candidates) {
      const clues = this.vocabulary.clueSearch(word, random, exhaustive);
      if (!clues) continue;
      this.recent.push(Array.from(word));
      for (const char of word) this.blocked.add(char);
      if (this.recent.length > COOLING) for (const char of this.recent.shift()) this.blocked.delete(char);
      this.level = level;
      // This transient result is consumed inside the Worker; never persist it or post it to the page.
      return { level, clues, solution: word };
    }
    throw new Error("当前版本无法继续生成合格题目");
  }
}

export async function publicPuzzle(generated, size) {
  const digest = async text => Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text))),
    b => b.toString(16).padStart(2, "0")).join("");
  const version = `${REVISION}-${size}`;
  const id = (await digest(`${version}:id:${generated.level}`)).slice(0, 32);
  const salt = (await digest(`${version}:salt:${generated.level}`)).slice(0, 32);
  return { id, clues: generated.clues, salt, check: await digest(`${version}:${id}:${salt}:${generated.solution}`) };
}
