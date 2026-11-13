import test from 'node:test';
import assert from 'node:assert/strict';
import { summarizeNeighborhood, renderLocalDetails } from '../web/local-change-view.mjs';

const local={definition:'tangent_exponential_map',radius_degrees:20,step_degrees:2,center_index:0,points:[
  {lon:180,lat:0,distance_degrees:0,similarity:1},
  {lon:178,lat:0,distance_degrees:2,similarity:.8},
  {lon:-178,lat:0,distance_degrees:4,similarity:.6},
  {lon:174,lat:0,distance_degrees:5,similarity:null},
  {lon:170,lat:0,distance_degrees:10,similarity:.2},
  {lon:160,lat:0,distance_degrees:20,similarity:-.4}
]};

test('局部距离带只汇总中心以外的有效原始 PE 余弦值，边界点归入正确距离带', () => {
  const result=summarizeNeighborhood(local);
  assert.equal(result.total,5);assert.equal(result.defined,4);
  assert.deepEqual(result.bands.map(b=>[b.start,b.end,b.count,b.missing]),[
    [0,5,2,1],[5,10,1,0],[10,15,0,0],[15,20,1,0]
  ]);
  assert.equal(result.bands[0].mean,.7);assert.equal(result.bands[0].min,.6);assert.equal(result.bands[0].max,.8);
  assert.equal(result.bands[3].mean,-.4);
  const html=renderLocalDetails(local);
  assert.match(html,/0–5°/);assert.match(html,/平均/);assert.match(html,/范围/);
  assert.match(html,/4\/5/);assert.match(html,/未定义/);
  assert.doesNotMatch(html,/NaN|Infinity/);
});

test('锚点零向量导致邻域余弦全部无定义时，不把缺失画成零', () => {
  const zero={...local,points:local.points.map(p=>({...p,similarity:null}))};
  const summary=summarizeNeighborhood(zero);
  assert.equal(summary.defined,0);
  assert.ok(summary.bands.every(b=>b.mean===null));
  const html=renderLocalDetails(zero);
  assert.match(html,/没有可定义的邻域相似度/);
  assert.doesNotMatch(html,/平均 0\.00/);
});
