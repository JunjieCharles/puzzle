import test from 'node:test';
import assert from 'node:assert/strict';
import {decryptWord} from '../public/decrypt.mjs';

test('decrypt artificial word; reject altered ciphertext, ID and word length',async()=>{
  const word='甲乙', encoder=new TextEncoder();
  const raw=crypto.getRandomValues(new Uint8Array(32));
  const key=await crypto.subtle.importKey('raw',raw,'AES-GCM',false,['encrypt']);
  const iv=crypto.getRandomValues(new Uint8Array(12));
  const puzzle={id:'0'.repeat(32),images:[null,null]};
  const cipher=await crypto.subtle.encrypt({name:'AES-GCM',iv,additionalData:encoder.encode(puzzle.id)},key,encoder.encode(word));
  puzzle.sealed={iv:Buffer.from(iv).toString('base64'),ciphertext:Buffer.from(cipher).toString('base64')};
  const config={algorithm:'AES-GCM',key:Buffer.from(raw).toString('base64')};
  assert.equal(await decryptWord(puzzle,config),word);
  await assert.rejects(decryptWord({...puzzle,id:'2'.repeat(32)},config));
  await assert.rejects(decryptWord({...puzzle,images:[null,null,null]},config));
  const damaged=new Uint8Array(cipher);damaged[0]^=1;
  await assert.rejects(decryptWord({...puzzle,sealed:{...puzzle.sealed,ciphertext:Buffer.from(damaged).toString('base64')}},config));
});
