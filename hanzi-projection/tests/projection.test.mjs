import test from 'node:test';
import assert from 'node:assert/strict';
import { project } from '../public/projection.mjs';
const rgba = values => new Uint8ClampedArray(values.flatMap(v => [v, v, v, 255]));
const close = (a, b) => assert.ok(Math.abs(a - b) < 1e-12);
test('fractional weights preserve orientation and totals', () => {
  const p = project(rgba([0,102,255,255,255,255,51,255,255]),3);
  [1.6,0,0.8].forEach((v,i)=>close(p.rows[i],v));
  [1.8,0.6,0].forEach((v,i)=>close(p.cols[i],v));
  close(p.total,2.4); close(p.cols.reduce((a,b)=>a+b),p.total);
});
test('black, white and near-white endpoints', () => {
  for(const v of [0,128,254,255]) close(project(rgba([v]),1).total,(255-v)/255);
});
test('one gray level changes only the affected row and column', () => {
  const a=project(rgba([255,128,255,255]),2),b=project(rgba([255,127,255,255]),2);
  close(b.rows[0]-a.rows[0],1/255); close(b.cols[1]-a.cols[1],1/255);
  close(b.rows[1],a.rows[1]); close(b.cols[0],a.cols[0]);
});
