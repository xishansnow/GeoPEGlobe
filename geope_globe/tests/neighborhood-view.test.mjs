import test from 'node:test';
import assert from 'node:assert/strict';
import { neighborhoodVertices } from '../web/neighborhood-view.mjs';

test('局部网格仅绘制真实非中心有效采样，跨日界线保持球面相邻', () => {
  const local={center_index:1,points:[
    {lon:179,lat:80,distance_degrees:2,similarity:.8},
    {lon:180,lat:80,distance_degrees:0,similarity:1},
    {lon:-179,lat:80,distance_degrees:2,similarity:.6},
    {lon:-178,lat:80,distance_degrees:4,similarity:null}
  ]};
  const vertices=neighborhoodVertices(local);
  assert.equal(vertices.length,2);
  assert.deepEqual(vertices.map(v=>v.value),[.8,.6]);
  assert.ok(Math.hypot(...vertices[0].position.map((v,i)=>v-vertices[1].position[i]))<.04);
  assert.ok(vertices.every(v=>v.color.length===3&&v.color.every(Number.isFinite)));
});
