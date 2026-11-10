import test from 'node:test';
import assert from 'node:assert/strict';
import { analyze, characters } from '../public/analysis.mjs';

function raster(size, points) {
  const pixels=new Uint8ClampedArray(size*size*4).fill(255);
  for(const [x,y,value=0] of points) for(let c=0;c<3;c++) pixels[(y*size+x)*4+c]=value;
  return pixels;
}
test('diagonal pixels connect; row ends never wrap',()=>{
  assert.equal(analyze(raster(4,[[0,0],[1,1],[3,3]]),4).count,2);
  assert.equal(analyze(raster(4,[[3,0],[0,1]]),4).count,2);
});
test('threshold affects components but not grayscale coverage',()=>{
  const pixels=raster(3,[[0,0,150],[1,1,0]]);
  const low=analyze(pixels,3,96),high=analyze(pixels,3,128);
  assert.equal(low.labels[0],1); assert.equal(high.labels[0],0);
  assert.equal(low.coverage,high.coverage);
});
test('blank and transparent pixels are not ink',()=>{
  assert.equal(analyze(raster(3,[]),3).count,0);
  assert.equal(analyze(new Uint8ClampedArray(36),3).coverage,0);
});
test('input accepts only distinct Han characters',()=>{
  assert.deepEqual(characters('abc123!?'),[]);
  const glyph=String.fromCodePoint(0x4e00);
  assert.deepEqual(characters(glyph+glyph+'abc'),[glyph]);
});
