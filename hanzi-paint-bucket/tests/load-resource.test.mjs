import test from 'node:test';
import assert from 'node:assert/strict';
import {loadResource} from '../public/load-resource.mjs';

test('download reports progress and preserves bytes', async t=>{
  t.mock.method(globalThis,'fetch',async()=>new Response(new Uint8Array([1,2,3]),{headers:{'content-length':'3'}}));
  const progress=[];
  assert.deepEqual(await loadResource('/fixture',p=>progress.push(p)),new Uint8Array([1,2,3]));
  assert.equal(progress.at(-1),1);
});
test('stalled body aborts, then a fresh attempt succeeds', async t=>{
  t.mock.method(globalThis,'fetch',async(url,{signal})=>new Response(new ReadableStream({
    start(controller){signal.addEventListener('abort',()=>controller.error(new Error('aborted')));}
  })));
  await assert.rejects(loadResource('/stalled',()=>{},15),/下载超时/);
  t.mock.restoreAll();
  t.mock.method(globalThis,'fetch',async()=>new Response(new Uint8Array([4])));
  assert.deepEqual(await loadResource('/retry'),new Uint8Array([4]));
});
