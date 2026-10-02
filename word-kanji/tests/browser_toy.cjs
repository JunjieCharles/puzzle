// Toy and ordinary-site integration, using a mocked SDK and synthetic puzzle data.
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const { createServer } = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const { createHash } = require('node:crypto');
const toyRoot = path.resolve(process.argv[2]);
const publicRoot = path.resolve(__dirname, '../public');
const imageRoot = process.argv[3];
if (imageRoot) {
  const repository = path.resolve(__dirname, '../..');
  const relative = path.relative(repository, path.resolve(imageRoot));
  if (!relative || (!relative.startsWith('..' + path.sep) && !path.isAbsolute(relative))) {
    throw Error('Screenshots must be outside the repository');
  }
}
const one = 'campaign-one-standard', two = 'campaign-two-standard';
const symbol = i => String.fromCodePoint(0x3400 + i);
function campaign(size) {
  const version = size === 1 ? 'kanji-one-v1' : 'kanji-two-v1';
  return { version, revision: (size === 1 ? 'a' : 'b').repeat(16), puzzles: Array.from({ length: 5 }, (_, i) => {
    const id = String(i).padStart(32, '0'), salt = 'c'.repeat(32);
    const input = size === 1 ? symbol(i) : symbol(i * 2) + symbol(i * 2 + 1);
    return { id, salt, check: createHash('sha256').update(`${version}:${id}:${salt}:${input}`).digest('hex'),
      clues: size === 1 ? { top: symbol(40), left: symbol(41), right: symbol(42), bottom: symbol(43) } :
        { top: [symbol(40), symbol(41)], bottom: [symbol(42), symbol(43)], left: symbol(44), right: symbol(45) },
      difficulty: 5, levels: {} };
  }) };
}
const server = createServer((req, res) => {
  const url = new URL(req.url, 'http://localhost');
  const prefix = url.pathname.startsWith('/toy/check/') ? '/toy/check/' : '/puzzle/word-kanji/';
  const root = prefix.startsWith('/toy') ? toyRoot : publicRoot;
  const relative = url.pathname.slice(prefix.length) || 'index.html';
  if (!url.pathname.startsWith(prefix) || relative.includes('..') || relative.includes('/')) { res.writeHead(404).end(); return; }
  const file = path.join(root, relative);
  if (!fs.existsSync(file)) { res.writeHead(404).end(); return; }
  const types = { '.js': 'text/javascript', '.html': 'text/html', '.css': 'text/css', '.json': 'application/json', '.svg': 'image/svg+xml' };
  res.writeHead(200, { 'Content-Type': types[path.extname(file)] || 'text/plain', 'Cache-Control': 'no-store' });
  res.end(fs.readFileSync(file));
});
(async () => {
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const origin = `http://127.0.0.1:${server.address().port}`;
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  try {
    const context = await browser.newContext({ viewport: { width: 390, height: 844 } });
    const errors = []; const badRequests = [];
    context.on('page', p => { p.on('pageerror', e => errors.push(e.message)); p.on('response', r => { if (r.status() >= 400) badRequests.push(r.url()); }); });
    await context.route('**/campaign.json', route => route.fulfill({ json: campaign(1) }));
    await context.route('**/campaign-two.json', route => route.fulfill({ json: campaign(2) }));
    let account = 'alpha', clock = 0;
    const cloud = { alpha: {wk_scope_v1:'1'.repeat(32)}, beta: {wk_scope_v1:'2'.repeat(32)} }, scores = { alpha: {}, beta: {} }, ranks = [];
    await context.exposeBinding('toyTestCall', async (_, method, arg) => {
      if (method === 'getUserProfile') throw Error('Unexpected profile request');
      if (method === 'getCloudStorage') return cloud[account];
      if (method === 'setCloudStorage') { Object.assign(cloud[account], arg); return null; }
      if (method === 'submitScore') {
        ranks.push({ account, ...arg });
        const old = scores[account][arg.board];
        if (!old || arg.score > old.score) scores[account][arg.board] = { score: arg.score, time: ++clock };
        return { score: scores[account][arg.board].score };
      }
      const rows = Object.entries(scores).filter(([, s]) => s[arg.board]).map(([nickname, s]) => ({ nickname, ...s[arg.board] }))
        .sort((a, b) => b.score - a.score || a.time - b.time).map((item, i) => ({ ...item, rank: i + 1, avatar: '' }));
      if (method === 'getRankList') return rows;
      if (method === 'getMyRank') { const me = rows.find(r => r.nickname === account); return { ranked: !!me, score: me?.score || 0, rank: me?.rank || 0 }; }
      throw Error('Unexpected SDK method');
    });
    await context.route('**/toy-sdk.js', route => route.fulfill({ contentType: 'text/javascript', body: `window.toy = Object.fromEntries(['getUserProfile','getCloudStorage','setCloudStorage','getMyRank','getRankList','submitScore'].map(method => [method, async arg => { const result = await window.toyTestCall(method,arg); if(result?.error) throw result.error; return result; }]));` }));
    const page = await context.newPage();
    // Deliberately seed an ordinary-site save; Toy must not import it.
    await page.goto(origin + '/puzzle/word-kanji/');
    await page.evaluate(() => localStorage.setItem('word-kanji:campaign:v2', JSON.stringify({ revision: 'a'.repeat(16), completed: 4, pending: [5] })));
    await page.goto(origin + '/toy/check/index.html');
    await page.locator('#cloud-status').waitFor();
    assert.equal(await page.locator('#save-dialog, #save-open').count(), 0);
    assert.equal(await page.locator('#cloud-connect, #cloud-sync').count(), 0);
    await page.waitForFunction(() => document.querySelector('#cloud-status').dataset.message === '已自动保存', null, { timeout: 10000 }).catch(async error => {
      console.error('Cloud status:', await page.locator('#cloud-status').textContent(), 'Page errors:', errors); throw error;
    });
    assert.equal(await page.locator('#cloud-retry').isVisible(), false);
    await page.keyboard.press('Escape');
    await page.goto(origin + '/toy/check/index.html#play/1');
    // Navigation via goto in same document preserves connection.
    await page.locator('#entry:not([disabled])').waitFor();
    assert.equal(await page.locator('#level-count').textContent(), '1 / 5');
    await page.locator('#entry').fill(symbol(0)); await page.locator('#submit').click();
    await page.waitForFunction(() => location.hash === '#play/2');
    assert.equal(scores.alpha[1].score, 1);
    await page.goto(origin + '/toy/check/index.html#play-two/1');
    await page.locator('#entry-two:not([disabled])').waitFor();
    await page.locator('#entry').fill(symbol(0)); await page.locator('#entry-two').fill(symbol(1));
    await page.locator('#submit').click();
    await page.waitForFunction(() => location.hash === '#play-two/2');
    assert.equal(scores.alpha[2].score, 1);
    const firstTime = scores.alpha[1].time;
    await page.goto(origin + '/toy/check/index.html#play/1');
    await page.locator('#entry:not([disabled])').waitFor();
    await page.locator('#entry').fill(symbol(0)); await page.locator('#submit').click();
    await page.waitForFunction(() => location.hash === '#play/2');
    assert.equal(scores.alpha[1].time, firstTime);
    assert.equal(ranks.filter(r => r.board === 1).length, 1);
    await page.reload();
    await page.waitForFunction(() => document.querySelector('#cloud-status').dataset.message === '已自动保存');
    assert.ok((await page.locator('#saved-progress').textContent()).includes('1'));
    await page.locator('#rank-open').click();
    await page.waitForFunction(() => document.querySelector('#rank-mine').textContent.includes('第 1 名'));
    await page.locator('#rank-two').click();
    await page.waitForFunction(() => document.querySelector('#rank-two').getAttribute('aria-pressed') === 'true' && document.querySelector('#rank-rows').children.length === 1);
    if (imageRoot) await page.screenshot({ path: path.join(imageRoot, 'toy-ranks.png') });
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    await page.keyboard.press('Escape');
    account = 'beta';
    await page.evaluate(() => document.dispatchEvent(new Event('visibilitychange')));
    await page.waitForFunction(() => document.querySelector('#saved-progress').textContent === '0 / 5');
    assert.deepEqual(cloud.beta, {wk_scope_v1:'2'.repeat(32)});
    await page.waitForFunction(() => document.querySelector('#cloud-status').dataset.message === '已自动保存');
    assert.equal(await page.locator('#saved-progress').textContent(), '0 / 5');
    await page.keyboard.press('Escape');
    await page.goto(origin + '/toy/check/index.html#play/1');
    await page.locator('#entry:not([disabled])').waitFor();
    await page.locator('#entry').fill(symbol(0)); await page.locator('#submit').click();
    await page.waitForFunction(() => location.hash === '#play/2');
    await page.locator('#rank-open').click();
    await page.locator('#rank-one').click();
    await page.waitForFunction(() => document.querySelector('#rank-mine').textContent.includes('第 2 名'));
    assert.equal(await page.locator('#rank-rows tr').first().locator('td').nth(1).textContent(), 'alpha');
    await page.keyboard.press('Escape');
    await page.goto(origin + '/toy/check/index.html#home');
    for (const viewport of [{ width: 320, height: 568 }, { width: 844, height: 390 }, { width: 1280, height: 900 }]) {
      await page.setViewportSize(viewport);
      assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    }
    if (imageRoot) await page.screenshot({ path: path.join(imageRoot, 'toy-home.png') });
    // Ordinary website still provides working save-code roundtrips.
    await page.goto(origin + '/puzzle/word-kanji/');
    await page.locator('#save-open').click(); await page.locator('#save-export').click();
    await page.waitForFunction(() => document.querySelector('#save-code').value.startsWith('HT101-2.'));
    await page.locator('#save-import').click();
    await page.waitForFunction(() => document.querySelector('#save-status').textContent.includes('已导入'));
    assert.equal(await page.locator('#levels-count').textContent(), '4 / 5');
    assert.equal(await page.evaluate(() => typeof window.toy), 'undefined');
    assert.deepEqual(errors, []); assert.deepEqual(badRequests, []);
    console.log('Browser Toy + web passed: synthetic solves, separate boards, same-score ordering, cloud restore, account isolation, no save codes in Toy, web save-code roundtrip, responsive layout.');
  } finally { await browser.close(); }
})().then(() => server.close(), error => { console.error(error); server.close(); process.exitCode = 1; });
