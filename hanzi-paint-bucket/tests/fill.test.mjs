import test from 'node:test';
import assert from 'node:assert/strict';
import { enclosedRegions } from '../public/fill.mjs';
test('closed artificial square fills only its interior', () => {
  const a = Uint8Array.from([0,0,0,0,0, 0,255,255,255,0, 0,255,0,255,0, 0,255,255,255,0, 0,0,0,0,0]);
  const result = enclosedRegions(a, 5, 5);
  assert.equal(result.count, 1); assert.equal(result.labels[12], 1); assert.equal(result.labels[0], -1);
  a[7] = 0;
  assert.equal(enclosedRegions(a, 5, 5).count, 0);
});
test('empty canvas has no enclosed regions', () => {
  assert.equal(enclosedRegions(new Uint8Array(100), 10, 10).count, 0);
});
