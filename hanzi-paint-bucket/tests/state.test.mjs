import test from 'node:test';
import assert from 'node:assert/strict';
import {validateProgress, encodeSave, decodeSave, nextLevel} from '../public/state.mjs';
const bank={revision:'test-revision',puzzles:Array(8).fill(null)};
test('unlock window and nonsequential completion',()=>{
  assert.equal(nextLevel(new Set([2,3]),3,8),4);
  assert.equal(nextLevel(new Set([2,3]),5,5),1);
  assert.equal(nextLevel(new Set([1,2,3]),3,3),null);
  assert.throws(()=>validateProgress({revision:bank.revision,passed:[4]},bank));
  assert.throws(()=>validateProgress({revision:bank.revision,passed:[1,1]},bank));
});
test('save round trip, corruption detection and field whitelist',async()=>{
  const input={revision:bank.revision,passed:[3,1],input:'discard me'};
  const code=await encodeSave(input,bank);
  assert.deepEqual(await decodeSave(code,bank),{revision:bank.revision,passed:[1,3]});
  await assert.rejects(decodeSave(code.slice(0,-1)+'x',bank));
  await assert.rejects(decodeSave(code,{...bank,revision:'other'}));
  assert.notEqual(code,await encodeSave(input,bank));
});
