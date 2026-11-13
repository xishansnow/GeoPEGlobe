// Exact coordinate-equivalence checks live at only three tested sphere points.
const definitions=[
  ['北极',0,90,'north_pole_0_vs_90'],
  ['南极',0,-90,'south_pole_0_vs_90'],
  ['赤道日界线',180,0,'dateline_plus_vs_minus_180']
];

export function boundaryMarkers(checks) {
  if(!checks)return [];
  return definitions.map(([label,lon,lat,key])=>{
    const value=checks[`${key}_relative_difference`],norm=checks[`${key}_max_norm`];
    const status=!Number.isFinite(value)?'unknown':Number.isFinite(norm)&&norm<1e-14?'tiny':value>1e-8?'different':'consistent';
    return {label,lon,lat,value,norm,status};
  });
}

export function boundaryReadout(markers) {
  if(!markers.length)return '<p class="hint">等待同点坐标检查。</p>';
  const names={consistent:'一致',different:'有差异',tiny:'极小幅值，谨慎解读',unknown:'未计算'};
  const rows=markers.map(m=>{
    const value=Number.isFinite(m.value)?m.value<.001?m.value.toExponential(2):m.value.toFixed(3):'—';
    return `<div class="boundary-row"><span class="boundary-swatch ${m.status}"></span><span>${m.label}</span><strong>${names[m.status]} · ${value}</strong></div>`;
  }).join('');
  return `<div class="boundary-readout">${rows}<p class="hint">仅这三个同点检查位置有数值；球面其他区域未检测。差值是原始 PE 向量的相对差，不是预测误差。极小幅值处不能仅按相对差判定好坏。</p></div>`;
}
