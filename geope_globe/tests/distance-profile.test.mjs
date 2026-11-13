import test from 'node:test';
import assert from 'node:assert/strict';
import { renderProfile } from '../web/charts.js';

const result = profile => ({profile});
const render = (results, field) => {
  const container = {innerHTML:'', textContent:''};
  renderProfile(container, results, field);
  return container;
};
const curvePaths = html => [...html.matchAll(/<path\b[^>]*\bd="([^"]*)"[^>]*>/g)].map(match => match[1]);

test('默认曲线只显示正向路线，以公里标记距离和起点，保留相似程度负值', () => {
  const {innerHTML} = render({a:result({angles:[-90,0,90],similarity:[.9,1,-1],kernel:[900,10,-10]})},'similarity');
  assert.match(innerHTML,/共同空间相似度/);
  assert.match(innerHTML,/公里/);
  assert.match(innerHTML,/起点/);
  assert.doesNotMatch(innerHTML,/°|ρ|NaN|Infinity/);
  const [path] = curvePaths(innerHTML);
  const points = [...path.matchAll(/[ML]([\d.]+),([\d.]+)/g)].map(m=>m.slice(1).map(Number));
  assert.equal(points.length,2,'负向路线不参与曲线');
  assert.ok(points[0][0]<points[1][0]);
  assert.ok(points[0][1]<points[1][1],'负相似程度仍位于纵轴下部');
  assert.match(innerHTML,/10,?00[078]/,'90 度约为 10007.6 公里');
});

test('省略字段时仍可直接读取相似程度', () => {
  assert.doesNotThrow(()=>render({a:result({angles:[0,90],similarity:[1,-1]})}));
  assert.match(render({a:result({angles:[0,90],similarity:[1,-1]})}).innerHTML,/共同空间相似度/);
});

test('相似程度固定为负一到一，不随当前样本幅度拉伸', () => {
  const full=render({a:result({angles:[0,90],similarity:[1,-1]})}).innerHTML;
  const partial=render({a:result({angles:[0,90],similarity:[.5,-.5]})}).innerHTML;
  const ys=html=>[...curvePaths(html)[0].matchAll(/[ML][\d.]+,([\d.]+)/g)].map(m=>Number(m[1]));
  const [top,bottom]=ys(full),[upper,lower]=ys(partial);
  assert.ok(Math.abs(upper-(top+(bottom-top)/4))<.01);
  assert.ok(Math.abs(lower-(bottom-(bottom-top)/4))<.01);
});

test('distanceSeries 按原样保留正向样本、端点空值和原始支持范围，不改输入', async () => {
  const {distanceSeries}=await import('../web/distance-profile.mjs');
  const profile={angles:[-90,-.01,0,45,90],similarity:[.8,.9,null,-.25,null],kernel:[20,20,12,-30,null]};
  const before=structuredClone(profile),series=distanceSeries(profile);
  assert.equal(series.length,3);
  assert.deepEqual(series.map(p=>p.value),[null,-.25,null]);
  assert.equal(series[0].distanceKm,0);
  assert.ok(Math.abs(series[1].distanceKm-5003.778610508981)<1e-8);
  assert.ok(Math.abs(series[2].distanceKm-10007.557221017962)<1e-8);
  assert.deepEqual(distanceSeries(profile,'kernel').map(p=>p.value),[12,-30,null]);
  assert.deepEqual(profile,before);
  const partial=distanceSeries({angles:[10,20],similarity:[null,.5]});
  assert.equal(partial.length,2);assert.ok(partial[0].distanceKm>0,'不插入不存在的起点样本');
  assert.deepEqual(distanceSeries({angles:[-20,-10],similarity:[1,1]}),[]);
});

test('未定义值断线，两侧采用各自已有采样范围，不外推到共同端点', () => {
  const {innerHTML} = render({
    a:result({angles:[-30,0,10,20,30,40],similarity:[1,1,null,.4,.2,null]}),
    b:result({angles:[0,10,20],similarity:[1,.5,0]})
  },'similarity');
  const [a,b] = curvePaths(innerHTML);
  assert.equal((a.match(/M/g)||[]).length,2);
  assert.equal((a.match(/L/g)||[]).length,1);
  assert.equal((b.match(/M/g)||[]).length,1);
  assert.equal((b.match(/L/g)||[]).length,2);
  const xs=path=>[...path.matchAll(/[ML]([\d.]+),/g)].map(m=>Number(m[1]));
  const ax=xs(a),bx=xs(b);
  assert.equal(ax[0],bx[0],'两侧零距离相同');
  assert.equal(ax[1],bx.at(-1),'同一已有采样距离落在共同横轴同一点');
  assert.ok(bx.at(-1)<ax.at(-1),'B 不外推到 A 的较远样本');
  assert.doesNotMatch(innerHTML,/NaN|Infinity/);
  assert.match(innerHTML,/#71dec4/);assert.match(innerHTML,/#8aaff5/);
});

test('原始核保持数值幅度和负号，不使用相似程度固定量程', () => {
  const {innerHTML} = render({a:result({angles:[0,45,90],kernel:[20,null,-10],similarity:[1,.5,-1]})},'kernel');
  assert.match(innerHTML,/共同空间核幅度/);
  assert.match(innerHTML,/>20<|>20\.0*</);
  assert.match(innerHTML,/>-10<|>-10\.0*</);
  assert.equal((curvePaths(innerHTML)[0].match(/M/g)||[]).length,2);
});

test('无结果保持等待；单个起点样本或全空值不会生成非法 SVG 坐标', () => {
  assert.match(render({a:null,b:null}).textContent,/等待/);
  for(const similarity of [[1],[null]]) {
    const {innerHTML}=render({a:result({angles:[0],similarity})},'similarity');
    assert.doesNotMatch(innerHTML,/NaN|Infinity/);
  }
});
