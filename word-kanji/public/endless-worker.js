import { Vocabulary, EndlessSequence, publicPuzzle } from "./endless-engine.js";

const VOCABULARY_SHA256 = "430a352eca23b62195f7a536fd2e79651b4d8b2fb663eab6b88581a66b3be44f";
let loading, token = 0;
const sequences = new Map(), latest = new Map();
async function vocabulary() {
  if (!loading) loading = (async () => {
    const response = await fetch(new URL("./endless-lexicon.json", import.meta.url));
    if (!response.ok) throw new Error("词库加载失败，请重试");
    const bytes = await response.arrayBuffer();
    const hash = Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256", bytes)), b => b.toString(16).padStart(2, "0")).join("");
    if (hash !== VOCABULARY_SHA256) throw new Error("词库版本不匹配，请刷新页面");
    return new Vocabulary(JSON.parse(new TextDecoder().decode(bytes)));
  })().catch(error => { loading = null; throw error; });
  return loading;
}
self.onmessage = async ({ data }) => {
  const request = ++token;
  if (data.cancel) return;
  const { id, size, level } = data;
  try {
    if (![1, 2].includes(size) || !Number.isSafeInteger(level) || level < 1 || level >= Number.MAX_SAFE_INTEGER) throw new Error("关号无效");
    const lexicon = await vocabulary();
    if (request !== token) return;
    if (latest.get(size)?.level === level) {
      postMessage({ id, puzzle: latest.get(size).puzzle }); return;
    }
    let sequence = sequences.get(size);
    if (!sequence || sequence.level >= level) {
      sequence = new EndlessSequence(lexicon, size); sequences.set(size, sequence);
    }
    let generated;
    while (sequence.level < level) {
      generated = sequence.next();
      if (sequence.level % 32 === 0 && sequence.level < level) {
        generated = null;
        postMessage({ id, progress: sequence.level, target: level });
        await new Promise(resolve => setTimeout(resolve, 0));
        if (request !== token) return;
      }
    }
    const puzzle = await publicPuzzle(generated, size);
    generated = null;
    if (request !== token) return;
    latest.set(size, { level, puzzle });
    postMessage({ id, puzzle });
  } catch (error) {
    if (request === token) postMessage({ id, error: error.message || "生成失败，请重试" });
  }
};
