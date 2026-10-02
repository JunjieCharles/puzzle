import { REVISION } from "./endless-engine.js";
export { REVISION };
export const endlessModes = ["endless-one-standard", "endless-two-standard"];
export function validateEndless(record) {
  if (!record || typeof record !== "object" || Array.isArray(record) ||
      record.revision !== REVISION || !Number.isSafeInteger(record.next) || record.next < 1 || record.next >= Number.MAX_SAFE_INTEGER) {
    throw new Error("无尽存档版本或关号无效");
  }
  return { revision: REVISION, next: record.next };
}
export class EndlessProgress {
  constructor(storage) { this.storage = storage; this.values = new Map(); this.unsaved = false; }
  key(mode) { return `word-kanji:${mode}:v1`; }
  read(mode) {
    if (!endlessModes.includes(mode)) throw new Error("无尽题型无效");
    let stored;
    try { stored = this.storage.getItem(this.key(mode)); }
    catch { /* Storage may be unavailable; retain session progress. */ }
    // Invalid/unknown versions must not silently become a new sequence.
    const record = stored === null || stored === undefined ? { revision: REVISION, next: 1 } : validateEndless(JSON.parse(stored));
    const next = Math.max(record.next, this.values.get(mode)?.next || 1);
    const result = { revision: REVISION, next };
    this.values.set(mode, result); return result;
  }
  async merge(mode, record) {
    const incoming = validateEndless(record);
    const write = () => {
      const next = Math.max(this.read(mode).next, incoming.next);
      this.values.set(mode, { revision: REVISION, next });
      try { this.storage.setItem(this.key(mode), JSON.stringify({ revision: REVISION, next })); this.unsaved = false; }
      catch { this.unsaved = true; }
    };
    if (globalThis.navigator?.locks) await navigator.locks.request(this.key(mode), write);
    else write();
    return !this.unsaved;
  }
}
export class EndlessClient {
  constructor() { this.serial = 0; }
  cancel() {
    this.pending?.reject(new Error("生成已取消")); this.pending = null;
    this.worker?.postMessage({ cancel: true });
  }
  get(size, level, progress) {
    this.cancel();
    if (!this.worker) {
      this.worker = new Worker(new URL("./endless-worker.js", import.meta.url), { type: "module" });
      this.worker.onmessage = ({ data }) => {
        if (this.pending?.id !== data.id) return;
        if (data.progress !== undefined) { this.pending.progress?.(data.progress, data.target); return; }
        const pending = this.pending; this.pending = null;
        if (data.error) pending.reject(new Error(data.error)); else pending.resolve(data.puzzle);
      };
      this.worker.onerror = event => {
        event.preventDefault(); this.pending?.reject(new Error("生成器加载失败，请重试")); this.pending = null;
        this.worker.terminate(); this.worker = null;
      };
    }
    return new Promise((resolve, reject) => {
      const id = ++this.serial;
      this.pending = { id, resolve, reject, progress };
      this.worker.postMessage({ id, size, level });
    });
  }
}
