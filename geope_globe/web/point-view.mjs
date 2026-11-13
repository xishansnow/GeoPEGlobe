// All bars and dots below are the original feature coordinates phi_i(x0).
// No whitening or band projection enters this view.
const escape = value => String(value).replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
const number = value => Number.isFinite(value) ? (value<0?'−':'')+Math.abs(value).toPrecision(3) : '未定义';

export function channelGroups(channels=[]) {
  const groups=new Map();
  channels.forEach((channel,index)=>{
    const kind=channel.kind;
    const label=kind==='rbf'?'RBF 中心':kind==='sh'?`球谐阶 ℓ=${channel.degree}`:
      kind==='slepian'?'Slepian 模式':kind==='cartesian'?'三维球坐标':
      kind==='spheredfs'&&channel.longitude_scale!==undefined?`经度尺度 ${channel.longitude_scale} × 纬度尺度 ${channel.latitude_scale}`:
      channel.scale!==undefined?`频率尺度 s=${channel.scale}`:
      kind==='rff'?'随机频率方向':kind==='wrap'?'经纬周期项':kind||'其他通道';
    if(!groups.has(label))groups.set(label,{label,kind,items:[]});
    groups.get(label).items.push({...channel,index});
  });
  return [...groups.values()];
}

function centerMap(items,point,values) {
  const x=lon=>12+(lon+180)/360*336, y=lat=>8+(90-lat)/180*164;
  const max=Math.max(...items.map(item=>Math.abs(values[item.index]??0)),1e-12);
  const dots=items.map(item=>{
    const value=values[item.index],fill=value==null?'#596b7d':value>=0?'#71dec4':'#8aaff5';
    const radius=3+Math.min(7,7*Math.abs(value??0)/max);
    return `<circle cx="${x(item.lon)}" cy="${y(item.lat)}" r="${radius}" fill="${fill}" stroke="#07131f" stroke-width="1"><title>${escape(item.name)} · ${item.lon.toFixed(1)}°，${item.lat.toFixed(1)}° · ${escape(number(value))}</title></circle>`;
  }).join('');
  return `<svg class="center-map" viewBox="0 0 360 180" role="img" aria-label="中心经纬位置与所选点的原始特征值"><rect x="12" y="8" width="336" height="164" rx="5" fill="#102235" stroke="#385064"/><path d="M180 8V172M12 90H348" stroke="#30485b" stroke-dasharray="3 5"/>${dots}<circle cx="${x(point.lon)}" cy="${y(point.lat)}" r="5" fill="none" stroke="white" stroke-width="2"/></svg><p class="hint">白圈是选点；绿点为正、蓝点为负，大小表示本组内绝对值。经纬投影在日界线分割、极点挤压，图上距离不是球面距离。</p>`;
}

export function renderPointEncoding(result,slot='a') {
  if(!result?.point?.features || !result.info?.channels)return '<p class="hint">等待原始 PE 结果。</p>';
  const {point,info}=result,values=point.features,groups=channelGroups(info.channels);
  const cards=groups.map(group=>{
    const max=Math.max(...group.items.map(item=>Math.abs(values[item.index]??0)),1e-12);
    const centered=group.items.every(item=>Number.isFinite(item.lon)&&Number.isFinite(item.lat))&&group.kind==='rbf';
    const rows=group.items.map(item=>{
      const value=values[item.index],width=value==null?0:Math.min(100,100*Math.abs(value)/max),positive=value==null||value>=0;
      return `<button type="button" class="point-feature" data-slot="${escape(slot)}" data-feature-index="${item.index}" title="查看原始特征 ${escape(item.name)} 的全球分布"><span class="feature-name">${item.index} · ${escape(item.name)}</span><span class="feature-track"><i class="${positive?'positive':'negative'}" style="width:${width}%"></i></span><strong>${escape(number(value))}</strong></button>`;
    }).join('');
    return `<section class="point-group"><h3>${escape(group.label)} <small>${group.items.length} 项</small></h3>${centered?centerMap(group.items,point,values):''}<div class="point-feature-list">${rows}</div></section>`;
  }).join('');
  return `<div class="point-pe-heading"><strong>原始 PE φ(x₀)</strong><span>${values.length} 个特征 · 向量长度 ${escape(number(point.raw_norm))}</span></div><p class="hint">每条显示一个原始特征在白点处的取值；蓝色表示负值，条长只在本组内比较。点击条目可看该特征的全球形状。数值不是重要性或预测贡献。</p><div class="point-groups">${cards}</div>`;
}

export function renderStructure(result,slot='a',phase='fresh') {
  if(!result?.info?.channels)return '<p class="hint">等待编码器结构。</p>';
  const groups=channelGroups(result.info.channels);
  const centered=groups.filter(group=>group.kind==='rbf');
  const rows=groups.map(group=>{
    const values=group.items.map(item=>result.point?.features?.[item.index]);
    const magnitude=values.every(Number.isFinite)?number(Math.hypot(...values)):'待计算';
    return `<div class="structure-row"><span>${escape(group.label)}</span><strong>${group.items.length} 项 · 本点范数 ${escape(magnitude)}</strong></div>`;
  }).join('');
  const checks=result.info.boundary_diagnostics;
  const checkRows=checks?[
    ['北极：经度 0° 与 90°',checks.north_pole_0_vs_90_relative_difference,checks.north_pole_0_vs_90_max_norm],
    ['南极：经度 0° 与 90°',checks.south_pole_0_vs_90_relative_difference,checks.south_pole_0_vs_90_max_norm],
    ['日界线：+180° 与 −180°',checks.dateline_plus_vs_minus_180_relative_difference,checks.dateline_plus_vs_minus_180_max_norm]
  ].map(([name,value,norm])=>`<div class="structure-row"><span>${name}</span><strong>${norm!==undefined&&norm<1e-14?'极小幅值（谨慎）':value>1e-8?'有差异':'一致'} · ${number(value)}</strong></div>`).join(''):'';
  const centerText=centered.length?`模板中心：${centered.reduce((sum,g)=>sum+g.items.length,0)} 个；例如 ${centered[0].items.slice(0,3).map(item=>`${item.lon.toFixed(1)}°，${item.lat.toFixed(1)}°`).join('；')}。中心配置改变空间偏好。`:'此方法的通道没有逐个空间中心；不能把亮区当作中心。';
  const location=result.point?`${result.point.lon.toFixed(2)}°，${result.point.lat.toFixed(2)}°`:'等待计算';
  const identity=phase==='fresh'?'当前选点':phase==='error'?'上次完成选点（计算失败）':'上次完成选点（待更新）';
  return `<section class="structure-card" data-slot="${escape(slot)}"><h3>${escape(slot.toUpperCase())} · ${escape(result.config?.encoder??'编码器')}</h3><p>${identity}：${escape(location)}。原始 ${result.info.feature_count} 维；共同空间有效秩 ${result.info.rank}。分组固定，本点范数随选点变化；不同组的原始尺度未统一，不按范数大小判好坏。</p><div>${rows}</div><p class="hint">${escape(centerText)}</p><h3>同一地理点，两种坐标写法</h3><div>${checkRows||'等待数值检查。'}</div><p class="hint">数值是原始向量差距除以两者较大的长度；不超过 10⁻⁸ 且幅值充分时标为一致。幅值小于 10⁻¹⁴ 时保留归一化差距并提示谨慎。球面几何没有日界线奇点，极点的不同经度代表同一位置。此检查只测坐标写法是否影响 PE，不评价空间分辨率或预测表现。</p></section>`;
}

export function canOpenFeature(slot,current,index) {
  return slot?.phase==='fresh' && Number.isInteger(index) && index>=0 && index<slot.result?.info?.feature_count &&
    JSON.stringify(slot.result.config)===JSON.stringify(current.config) &&
    slot.result.point.lon===current.anchor.lon && slot.result.point.lat===current.anchor.lat;
}
