export function regionInfo(config={}) {
  const hasCap=config.encoder==='slepian'||(config.encoder==='rbf'&&config.center_layout==='cap');
  return hasCap?{hasCap:true,label:`名义目标球冠 ${config.radius}°`}:
    {hasCap:false,label:'无区域球冠 · 此配置在全球构造'};
}

export function centerColor() {return 0xf4d49a;}

export function centerLegend(config,centers=[]) {
  return centers.length?'<span><i style="background:#f4d49a"></i>构造中心（无尺度编号）</span>':
    '<span>无逐原子构造中心</span>';
}
