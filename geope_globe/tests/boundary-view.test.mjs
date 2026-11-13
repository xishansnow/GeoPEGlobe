import test from 'node:test';
import assert from 'node:assert/strict';
import { boundaryMarkers, boundaryReadout } from '../web/boundary-view.mjs';

test('同点坐标检查只生成三个实际检测位置，不把日界线整条经线充当测量', () => {
  const checks={north_pole_0_vs_90_relative_difference:0,north_pole_0_vs_90_max_norm:1,
    south_pole_0_vs_90_relative_difference:.4,south_pole_0_vs_90_max_norm:1,
    dateline_plus_vs_minus_180_relative_difference:1,dateline_plus_vs_minus_180_max_norm:1e-49};
  const markers=boundaryMarkers(checks);
  assert.deepEqual(markers.map(m=>[m.lon,m.lat,m.status]),[[0,90,'consistent'],[0,-90,'different'],[180,0,'tiny']]);
  assert.equal(markers.length,3);
  const html=boundaryReadout(markers);
  assert.match(html,/北极/);assert.match(html,/南极/);assert.match(html,/赤道日界线/);
  assert.match(html,/极小幅值/);assert.match(html,/仅这三个同点检查/);
});

test('缺失诊断不伪装为一致', () => {
  assert.deepEqual(boundaryMarkers(null),[]);
  assert.match(boundaryReadout([]),/等待/);
});
