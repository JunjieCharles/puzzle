// Run against a built Toy directory. Fixtures are artificial progress, never real solutions.
import assert from 'node:assert/strict';
import { pathToFileURL } from 'node:url';
import { resolve } from 'node:path';
import { webcrypto } from 'node:crypto';
globalThis.crypto ??= webcrypto;
const { CloudProgress, cleanRecord, scopeKey } = await import(pathToFileURL(resolve(process.argv[2], 'cloud.js')));
const one = 'campaign-one-standard', two = 'campaign-two-standard';
const catalog = { [one]: { revision: 'a'.repeat(16), total: 8 }, [two]: { revision: 'b'.repeat(16), total: 8 } };
const { REVISION } = await import(pathToFileURL(resolve(process.argv[2], 'endless.js')));
const endlessOne = 'endless-one-standard', endlessTwo = 'endless-two-standard';
for (const mode of [endlessOne, endlessTwo]) catalog[mode] = { revision: REVISION, endless: true };
const endlessRecord = next => ({ v: 1, revision: REVISION, next });
const record = (mode, count, pending) => ({ v: 1, revision: catalog[mode].revision, completed: count,
  pending: pending || Array.from({ length: Math.min(8, count + 3) - count }, (_, i) => count + i + 1) });
function harness() {
  let account = 'alpha', failure;
  const data = { alpha: { [scopeKey]: '1'.repeat(32) }, beta: { [scopeKey]: '2'.repeat(32) } }, scores = { alpha: {}, beta: {} }, calls = [], local = new Map(), timers = [];
  const api = {
    getUserProfile: async () => { throw Error('Cloud must not request profile'); },
    getCloudStorage: async () => { if (failure === 'read') throw { code: 307044 }; return structuredClone(data[account]); },
    setCloudStorage: async items => { calls.push(['cloud', account, items]); Object.assign(data[account], items); },
    getMyRank: async ({ board }) => ({ ranked: board in scores[account], score: scores[account][board] || 0, rank: 1 }),
    submitScore: async ({ board, score }) => {
      if (failure === 'rank') throw { code: 307044 };
      calls.push(['rank', account, board, score]); scores[account][board] = Math.max(score, scores[account][board] || 0);
      return { score: scores[account][board] };
    },
  };
  const states = [];
  const cloud = new CloudProgress({ sdk: () => api, storage: () => ({ getItem: key => local.get(key), setItem: (key, value) => local.set(key, value) }),
    catalog, update: () => {}, status: (...state) => states.push(state), timer: fn => { timers.push(fn); return timers.length; }, cancel: () => {} });
  return { cloud, api, data, calls, local, timers, states, account: value => account = value, fail: value => failure = value };
}
{
  const h = harness();
  delete h.data.alpha[scopeKey];
  await h.cloud.connect();
  assert.match(h.data.alpha[scopeKey], /^[a-f0-9]{32}$/);
  assert.equal(h.cloud.records[one].completed, 0, 'first visit initializes automatically without profile permission');
  h.api.submitScore = async () => { throw { type: 'denied' }; };
  h.cloud.save(one, record(one, 1)); await h.cloud.inFlight;
  assert.equal(JSON.parse(h.data.alpha[h.cloud.cloudKey(one)]).completed, 1);
  assert.ok(h.cloud.identity, 'declining leaderboard permission must not disconnect cloud');
  h.cloud.save(one, record(one, 2)); await h.cloud.inFlight;
  assert.equal(JSON.parse(h.data.alpha[h.cloud.cloudKey(one)]).completed, 2);
}
{
  const h = harness(); await h.cloud.connect();
  h.cloud.save(one, record(one, 2, [1, 4, 5])); await h.cloud.inFlight;
  h.cloud.save(two, record(two, 1)); await h.cloud.inFlight;
  assert.deepEqual(h.calls.filter(c => c[0] === 'rank').map(c => c.slice(2)), [[1, 2], [2, 1]]);
  const before = h.calls.length;
  h.cloud.save(one, record(one, 2, [1, 4, 5])); await h.cloud.flush();
  assert.equal(h.calls.length, before, 'same score must not be submitted again');
  const remote = record(one, 2, [2, 4, 5]);
  h.data.alpha[h.cloud.cloudKey(one)] = JSON.stringify(remote);
  await h.cloud.flush();
  assert.equal(h.cloud.records[one].completed, 3, 'union must preserve different passed levels');
  assert.equal(h.cloud.records[two].completed, 1);
  for (const [key, value] of Object.entries(h.data.alpha)) {
    if (key === scopeKey) continue;
    assert.ok(new TextEncoder().encode(value).length <= 1024);
    assert.deepEqual(Object.keys(JSON.parse(value)).sort(), ['completed', 'pending', 'revision', 'v']);
  }
  h.account('beta'); await h.cloud.flush();
  assert.equal(h.cloud.identity, undefined);
  assert.deepEqual(h.data.beta, { [scopeKey]: '2'.repeat(32) }, 'account switch must not write alpha progress into beta');
  await h.cloud.connect();
  assert.equal(h.cloud.records[one].completed, 0);
  h.account('alpha'); await h.cloud.connect();
  assert.equal(h.cloud.records[one].completed, 3);
}
{
  const h = harness(); await h.cloud.connect();
  h.fail('read'); h.cloud.save(one, record(one, 1)); await h.cloud.inFlight;
  assert.equal(h.timers.length, 1, 'limit must schedule backoff');
  assert.ok(h.local.size, 'offline progress must survive locally');
  await h.cloud.flush(); assert.equal(h.timers.length, 1, 'manual retry must honor cooldown');
  h.fail(undefined); h.cloud.nextRetry = 0; await h.cloud.flush();
  assert.equal(JSON.parse(h.data.alpha[h.cloud.cloudKey(one)]).completed, 1);
  h.fail('rank'); h.cloud.save(two, record(two, 2)); await h.cloud.inFlight;
  assert.equal(JSON.parse(h.data.alpha[h.cloud.cloudKey(two)]).completed, 2, 'rank failure must not block cloud save');
}
{
  const h = harness(); h.data.alpha[h.cloud.cloudKey(one)] = '{broken';
  await assert.rejects(h.cloud.connect());
  assert.equal(h.calls.length, 0, 'corrupt cloud must not be overwritten');
  assert.equal(h.cloud.identity, undefined);
  assert.throws(() => cleanRecord({ ...record(one, 1), extra: 'unexpected' }, catalog[one]));
  assert.throws(() => cleanRecord({ ...record(one, 1), revision: 'c'.repeat(16) }, catalog[one]));
}
{
  const h = harness(); await h.cloud.connect();
  const realWrite = h.api.setCloudStorage;
  let release, entered;
  const writing = new Promise(resolve => entered = resolve);
  h.api.setCloudStorage = async items => { entered(); await new Promise(resolve => release = resolve); await realWrite(items); };
  h.cloud.save(one, record(one, 1)); await writing;
  h.cloud.save(one, record(one, 2));
  h.api.setCloudStorage = realWrite; release();
  while (h.cloud.inFlight) await h.cloud.inFlight;
  assert.equal(JSON.parse(h.data.alpha[h.cloud.cloudKey(one)]).completed, 2, 'completion during a write needs a second flush');
}
console.log('Toy cloud tests passed: isolation, merge, whitelist, retry, corrupt data, score idempotence, concurrent completion.');
{
  const h = harness();
  h.data.alpha[h.cloud.cloudKey(one)] = JSON.stringify(record(one, 2));
  await h.cloud.connect();
  assert.equal(h.cloud.records[one].completed, 2);
  assert.equal(h.cloud.readEndless(endlessOne).next, 1, 'old cloud saves initialize the new modes independently');
  h.cloud.save(endlessOne, endlessRecord(4)); await h.cloud.inFlight;
  h.cloud.save(endlessTwo, endlessRecord(2)); await h.cloud.inFlight;
  assert.deepEqual(h.calls.filter(c => c[0] === 'rank').map(c => c.slice(2)), [[1, 2], [3, 3], [4, 1]]);
  h.data.alpha[h.cloud.cloudKey(endlessOne)] = JSON.stringify(endlessRecord(6));
  await h.cloud.flush();
  h.cloud.save(endlessOne, endlessRecord(3)); await h.cloud.inFlight;
  assert.equal(h.cloud.readEndless(endlessOne).next, 6);
  assert.equal(h.cloud.readEndless(endlessTwo).next, 2);
  for (const mode of [endlessOne, endlessTwo]) {
    assert.deepEqual(Object.keys(JSON.parse(h.data.alpha[h.cloud.cloudKey(mode)])).sort(), ['next', 'revision', 'v']);
    for (const bad of [0, -1, 1.5, Number.MAX_SAFE_INTEGER]) assert.throws(() => cleanRecord(endlessRecord(bad), catalog[mode]));
    assert.throws(() => cleanRecord({...endlessRecord(2), extra: []}, catalog[mode]));
  }
  h.fail('read'); h.cloud.save(endlessTwo, endlessRecord(3)); await h.cloud.inFlight;
  assert.equal(JSON.parse(h.local.get(h.cloud.cacheKey)).modes[endlessTwo].next, 3);
  h.fail(undefined); h.cloud.nextRetry = 0; await h.cloud.flush();
  assert.equal(JSON.parse(h.data.alpha[h.cloud.cloudKey(endlessTwo)]).next, 3);
  h.account('beta'); await h.cloud.flush(); await h.cloud.connect();
  assert.equal(h.cloud.readEndless(endlessOne).next, 1);
  assert.deepEqual(h.data.beta, { [scopeKey]: '2'.repeat(32) });
  h.account('alpha'); await h.cloud.connect();
  assert.equal(h.cloud.readEndless(endlessOne).next, 6);
  assert.equal(h.cloud.readEndless(endlessTwo).next, 3);
  assert.equal(h.calls.filter(c => c[0] === 'rank' && c[2] === 3).length, 2, 'restoring must not resubmit the same score');
}
console.log('Toy endless cloud passed: four boards, old saves, max merge, whitelist, offline retry, account isolation.');
