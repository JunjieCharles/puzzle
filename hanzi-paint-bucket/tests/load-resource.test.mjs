import test from 'node:test';
import assert from 'node:assert/strict';
import {loadResource, loadJsonResource} from '../public/load-resource.mjs';
import {gzipSync} from 'node:zlib';

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
test('compressed JSON supports gzip bytes and server-decoded responses',async t=>{
  const data={version:'synthetic',puzzles:[]}, raw=JSON.stringify(data);
  let body=gzipSync(raw);
  t.mock.method(globalThis,'fetch',async()=>new Response(body));
  assert.deepEqual(await loadJsonResource('/test.gz','/test.json'),data);
  body=raw;
  assert.deepEqual(await loadJsonResource('/test.gz','/test.json'),data);
});
test('older browsers load the plain JSON fallback',async t=>{
  const previous=globalThis.DecompressionStream;
  globalThis.DecompressionStream=undefined;
  try {
    t.mock.method(globalThis,'fetch',async url=>{
      assert.equal(url,'/test.json');return new Response('{"ok":true}');
    });
    assert.deepEqual(await loadJsonResource('/test.gz','/test.json'),{ok:true});
  } finally {globalThis.DecompressionStream=previous;}
});
