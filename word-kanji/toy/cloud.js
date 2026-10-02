import { passedLevels, progressRecord } from "./progress.js";

export const boards = { "campaign-one-standard": 1, "campaign-two-standard": 2 };
export const scopeKey = "wk_scope_v1";
const keys = record => Object.keys(record).sort().join(",");
const problem = (message, permanent = true) => Object.assign(new Error(message), { permanent });

// Every persistent value is rebuilt from a progress whitelist, never from game inputs.
export function cleanRecord(value, spec) {
  if (!value || keys(value) !== "completed,pending,revision,v" || value.v !== 1 || value.revision !== spec.revision || !Array.isArray(value.pending)) {
    throw problem("云存档版本不匹配或内容损坏，未覆盖原存档");
  }
  try { return { v: 1, ...progressRecord(passedLevels(value, spec.total), spec.total, spec.revision) }; }
  catch { throw problem("云存档进度无效，未覆盖原存档"); }
}

export function mergeRecord(a, b, spec) {
  return { v: 1, ...progressRecord(new Set([...passedLevels(a, spec.total), ...passedLevels(b, spec.total)]), spec.total, spec.revision) };
}

export class CloudProgress {
  constructor({ sdk, storage, catalog, update, status,
    timer = (fn, delay) => setTimeout(fn, delay), cancel = id => clearTimeout(id) }) {
    Object.assign(this, { sdk, storage, catalog, update, status, timer, cancel });
    this.records = {}; this.ack = {}; this.epoch = 0; this.retries = 0; this.nextRetry = 0;
  }
  empty() {
    return Object.fromEntries(Object.entries(this.catalog).map(([mode, spec]) =>
      [mode, { v: 1, ...progressRecord(new Set(), spec.total, spec.revision) }]));
  }
  cloudKey(mode) { return `wk1_${boards[mode]}_${this.catalog[mode].revision}`; }
  read(mode) { return this.records[mode] ? passedLevels(this.records[mode], this.catalog[mode].total) : new Set(); }
  stop(message = "正在读取云存档…") {
    this.epoch++; this.cancel(this.retryTimer); this.retryTimer = undefined;
    this.identity = undefined; this.cacheKey = undefined; this.records = {}; this.ack = {};
    this.retries = 0; this.nextRetry = 0; this.again = false;
    this.update({}, true); this.status(message, false);
  }
  assert(epoch) { if (epoch !== this.epoch) throw problem("账号状态已变化，请刷新页面"); }
  async verify(epoch) {
    this.assert(epoch);
    const data = await this.sdk().getCloudStorage([scopeKey]);
    this.assert(epoch);
    if (data[scopeKey] !== this.identity) {
      this.stop("账号已变化，正在重新读取云存档…");
      throw problem("账号已变化");
    }
  }
  persist() {
    if (!this.cacheKey) return;
    try { this.storage().setItem(this.cacheKey, JSON.stringify({ v: 1, modes: this.records })); this.localFailed = false; }
    catch { this.localFailed = true; }
  }
  localRecords() {
    try {
      const raw = this.storage().getItem(this.cacheKey);
      if (!raw) return {};
      const data = JSON.parse(raw);
      if (data.v !== 1 || keys(data) !== "modes,v") return {};
      const result = {};
      for (const [mode, value] of Object.entries(data.modes)) {
        if (this.catalog[mode] && value.revision === this.catalog[mode].revision) result[mode] = cleanRecord(value, this.catalog[mode]);
      }
      return result;
    } catch { return {}; }
  }
  async remote(epoch) {
    const data = await this.sdk().getCloudStorage([scopeKey, ...Object.keys(this.catalog).map(mode => this.cloudKey(mode))]);
    this.assert(epoch);
    if (data[scopeKey] !== this.identity) {
      this.stop("账号已变化，正在重新读取云存档…");
      throw problem("账号已变化");
    }
    const result = this.empty();
    for (const mode of Object.keys(this.catalog)) {
      const raw = data[this.cloudKey(mode)];
      if (raw === undefined) continue;
      let value;
      try { value = JSON.parse(raw); } catch { throw problem("云存档内容损坏，未覆盖原存档"); }
      result[mode] = cleanRecord(value, this.catalog[mode]);
    }
    return result;
  }
  async connect() {
    const oldWork = this.inFlight;
    this.stop("正在读取云存档…");
    if (oldWork) await oldWork;
    const epoch = this.epoch;
    try {
      // Cloud storage is already isolated by the platform account. A random,
      // non-credential marker namespaces our retry cache without profile consent.
      let scope = (await this.sdk().getCloudStorage([scopeKey]))[scopeKey];
      this.assert(epoch);
      if (scope === undefined) {
        scope = Array.from(crypto.getRandomValues(new Uint8Array(16)), b => b.toString(16).padStart(2, "0")).join("");
        await this.sdk().setCloudStorage({ [scopeKey]: scope });
        this.assert(epoch);
        scope = (await this.sdk().getCloudStorage([scopeKey]))[scopeKey];
      }
      this.assert(epoch);
      if (typeof scope !== "string" || !/^[a-f0-9]{32}$/.test(scope)) throw problem("云存档标识无效，未覆盖原存档");
      this.identity = scope;
      this.cacheKey = `word-kanji:toy:auto-v1:${scope}`;
      const remote = await this.remote(epoch);
      const local = this.localRecords();
      this.assert(epoch);
      this.records = Object.fromEntries(Object.entries(remote).map(([mode, value]) =>
        [mode, local[mode] ? mergeRecord(value, local[mode], this.catalog[mode]) : value]));
      this.ack = {}; this.rankBlocked = false;
      this.persist(); this.update(this.records, true);
      this.status("已自动读取云存档", true);
      await this.flush();
    } catch (error) {
      if (epoch === this.epoch) this.stop(error.message || "云存档暂不可用，请确认 B站登录状态");
      throw error;
    }
  }
  save(mode, value) {
    if (!this.identity || !this.records[mode]) return;
    const clean = cleanRecord({ v: 1, ...value }, this.catalog[mode]);
    if (JSON.stringify(clean) === JSON.stringify(this.records[mode])) return;
    this.records[mode] = mergeRecord(this.records[mode], clean, this.catalog[mode]);
    this.persist(); this.status("进度待同步", true);
    // A new completion is the event boundary; don't delay its first rank submission.
    void this.flush();
  }
  flush() {
    if (!this.identity || !Object.keys(this.records).length) return Promise.resolve();
    if (this.inFlight) { this.again = true; return this.inFlight; }
    if (Date.now() < this.nextRetry) return Promise.resolve();
    this.cancel(this.retryTimer); this.retryTimer = undefined;
    const epoch = this.epoch;
    this.inFlight = this.sync(epoch).then(() => {
      this.assert(epoch); this.retries = 0; this.nextRetry = 0;
      this.status(this.localFailed ? "云端已自动保存，本机缓存不可用" : "已自动保存", true);
    }).catch(error => {
      if (epoch !== this.epoch) return;
      const auth = ["unauthorized", "denied", "unsupported"].includes(error.type);
      if (auth) { this.stop("请先登录 B站，登录后将自动读取云存档"); return; }
      const limited = error.code === 307044;
      this.status(error.permanent ? error.message : limited ? "请求较多，稍后自动同步" : "同步失败，进度待同步", true);
      this.again = false;
      if (!error.permanent && this.retries < 5) {
        const delay = Math.min(60000, 2000 * 2 ** this.retries++) + Math.random() * 1000;
        this.nextRetry = Date.now() + delay;
        this.retryTimer = this.timer(() => { this.nextRetry = 0; void this.flush(); }, delay);
      }
    }).finally(() => {
      this.inFlight = undefined;
      if (epoch === this.epoch && this.again) { this.again = false; void this.flush(); }
    });
    return this.inFlight;
  }
  async sync(epoch) {
    const remote = await this.remote(epoch);
    const local = this.localRecords();
    for (const mode of Object.keys(this.catalog)) {
      this.records[mode] = mergeRecord(this.records[mode], remote[mode], this.catalog[mode]);
      if (local[mode]) this.records[mode] = mergeRecord(this.records[mode], local[mode], this.catalog[mode]);
    }
    this.persist(); this.update(this.records);
    // Snapshot after merging; newer completions schedule another pass.
    const snapshot = structuredClone(this.records);
    const changed = Object.fromEntries(Object.entries(snapshot)
      .filter(([mode, value]) => JSON.stringify(value) !== JSON.stringify(remote[mode]))
      .map(([mode, value]) => [this.cloudKey(mode), JSON.stringify(value)]));
    if (Object.keys(changed).length) {
      await this.verify(epoch);
      await this.sdk().setCloudStorage(changed);
      this.assert(epoch);
    }
    if (!this.rankBlocked) {
      try {
        for (const [mode, record] of Object.entries(snapshot)) {
          if (record.completed === 0) continue;
          if (this.ack[mode] === undefined) {
            const mine = await this.sdk().getMyRank({ board: boards[mode], period: "all" });
            this.assert(epoch); this.ack[mode] = mine.ranked ? mine.score : 0;
          }
          if (record.completed <= this.ack[mode]) continue;
          await this.verify(epoch);
          const result = await this.sdk().submitScore({ board: boards[mode], score: record.completed });
          this.assert(epoch); this.ack[mode] = result.score;
        }
      } catch (error) {
        this.assert(epoch);
        if (["unauthorized", "denied", "unsupported"].includes(error.type)) {
          // Leaderboard consent must never disable automatic cloud storage.
          this.rankBlocked = true;
        } else { throw error; }
      }
    }
  }
}
