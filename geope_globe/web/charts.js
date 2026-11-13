import { distanceSeries } from './distance-profile.mjs';

const COLORS={a:'#71dec4',b:'#8aaff5'};
export const escapeHTML=value=>String(value).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
export function format(value,digits=3) {
  if(value===null || value===undefined || !Number.isFinite(value))return '未定义';
  if(value===0)return '0';
  return Math.abs(value)>=1e4 || Math.abs(value)<.001?value.toExponential(2):Number(value.toPrecision(digits)).toLocaleString('en-US',{maximumFractionDigits:8});
}
export function bandlimitLabel(info) {
  return info.bandlimited===false?`非带限 · 频谱分析截断 L = ${info.spectral_max_degree}`:`L实际 ${info.actual_max_degree??info.spectral_max_degree}`;
}
export function budgetSummary(a,b) {
  const match=a.bandlimited!==false&&b.bandlimited!==false&&a.feature_count===b.feature_count&&a.rank===b.rank&&a.actual_max_degree===b.actual_max_degree;
  const text=match?`共同预算：${a.feature_count} 特征 · 数值秩 ${a.rank} · ${bandlimitLabel(a)}。相同预算不意味着相同几何或预测性能。`:
    `预算分别披露：A ${a.feature_count} 特征 / r ${a.rank} / ${bandlimitLabel(a)}；B ${b.feature_count} 特征 / r ${b.rank} / ${bandlimitLabel(b)}。${a.bandlimited===false||b.bandlimited===false?'分析截断不代表原式带限；':''}探索结果不构成性能优劣判断。`;
  return {match,text};
}
export function spectrumSummary(result) {
  const {info,spectrum}=result,sum=spectrum.energy.reduce((s,v)=>s+v,0);
  const base=`ΣEℓ = ${format(sum,6)}，r = ${info.rank}`;
  return info.bandlimited===false?`${base}（原式保留秩分母）；分析至 L = ${info.spectral_max_degree}，覆盖 ${format(100*info.spectral_energy_coverage,5)}%，未覆盖尾部 ${format(100*info.spectral_tail_fraction,5)}%${info.band_complete===false?'；所选频带超出分析截断，未计算（遮罩）':''}` : base;
}
export function diagnosticRows(info) {
  const nonBandlimited=info.bandlimited===false;
  const rows=[
    [nonBandlimited?'Gram 推导的特征条件数':'保留系数子空间条件数',format(info.condition_number,5)],['相对奇异值秩阈值',format(info.rank_tolerance)],
    ['绝对秩阈值',format(info.absolute_rank_threshold)],['最大丢弃奇异值',format(info.discarded_singular_max)],
    [nonBandlimited?'原式特征重构残差':'相对重构残差',format(info.relative_reconstruction_error,5)],
    [nonBandlimited?'保留基正交性误差 TᵀGT − I':'保留基正交性误差',format(info.basis_orthogonality_error??info.gram_error,5)]
  ];
  if(nonBandlimited) {
    rows.push(['Gram 来源',info.gram_source],['Gram 舍入保护阈值',format(info.gram_roundoff_floor)],['有效秩阈值',format(info.effective_rank_tolerance)]);
    if(info.spectral_quadrature_applicable===false || info.gram_source?.startsWith('analytic_spherical'))rows.push(['频谱系数计算','解析公式；节点复核不适用']);
    else rows.push(['投影积分复核差异（非严格误差界）',format(info.spectral_quadrature_error)],['投影复核归一化','‖ΔA‖F / √tr(G)（原式特征范数）']);
  }
  if(nonBandlimited && info.gram_quadrature_error!==undefined)rows.push(['Gram 积分复核差异（非严格误差界）',format(info.gram_quadrature_error)]);
  return rows;
}
const svg=(width,height,label,body,fontSize=9)=>`<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}" role="img" aria-label="${escapeHTML(label)}" font-family="system-ui,sans-serif" font-size="${fontSize}" fill="#8ba2b4">${body}</svg>`;
const text=(x,y,value,anchor='start')=>`<text x="${x}" y="${y}" text-anchor="${anchor}">${escapeHTML(value)}</text>`;
const line=(x1,y1,x2,y2,stroke='#293b4d',extra='')=>`<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" stroke="${stroke}" ${extra}/>`;

export function renderSpectrum(container,results,band,onSelect) {
  const series=Object.entries(results).filter(([,r])=>r);
  if(!series.length){container.textContent='等待 API 频谱。';return;}
  const width=300,height=186,pad={l:33,r:9,t:12,b:32},w=width-pad.l-pad.r,h=height-pad.t-pad.b;
  const maxDegree=Math.max(...series.flatMap(([,r])=>r.spectrum.degrees)),count=maxDegree+1;
  const maxValue=Math.max(.01,...series.flatMap(([,r])=>r.spectrum.fraction))*1.08;
  const x=l=>pad.l+l/count*w,y=v=>pad.t+h-v/maxValue*h;
  let body=`<rect width="${width}" height="${height}" fill="transparent"/>`;
  const start=Math.max(0,band.min),end=Math.min(count,band.max+1);
  if(end>start)body+=`<rect x="${x(start)}" y="${pad.t}" width="${(end-start)/count*w}" height="${h}" fill="#71dec4" opacity=".055"/>`;
  for(let i=0;i<=3;i++){const v=maxValue*i/3;body+=line(pad.l,y(v),width-pad.r,y(v));body+=text(pad.l-5,y(v)+3,`${Math.round(v*100)}%`,'end');}
  for(const [id,result] of series) {
    result.spectrum.degrees.forEach((degree,i)=>{
      const value=result.spectrum.fraction[i],barw=Math.max(.6,w/count*.36),offset=id==='a'?.1:.5;
      body+=`<rect x="${x(degree)+w/count*offset}" y="${y(value)}" width="${barw}" height="${Math.max(0,pad.t+h-y(value))}" rx=".5" fill="${COLORS[id]}" opacity=".88"><title>${id.toUpperCase()} · ℓ=${degree} · Eℓ/r=${format(value,5)}</title></rect>`;
    });
  }
  const step=Math.max(1,Math.ceil(maxDegree/5));
  for(let l=0;l<=maxDegree;l+=step)body+=text(x(l)+w/count/2,height-15,l,'middle');
  body+=text(width-pad.r,height-2,'球谐阶 ℓ','end');
  for(let l=0;l<=maxDegree;l++)body+=`<rect data-degree="${l}" x="${x(l)}" y="${pad.t}" width="${w/count}" height="${h}" fill="transparent" tabindex="0" role="button" aria-label="选择球谐阶 ${l}" style="cursor:pointer"><title>选择 ℓ = ${l}</title></rect>`;
  container.innerHTML=svg(width,height,'A 与 B 的逐阶球谐频谱占比，横轴为球谐阶',body);
  container.querySelectorAll('[data-degree]').forEach(node=>{
    node.addEventListener('click',()=>onSelect(Number(node.dataset.degree)));
    node.addEventListener('keydown',event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();onSelect(Number(node.dataset.degree));}});
  });
}

export function renderProfile(container,results,field='similarity') {
  const series=Object.entries(results).filter(([,r])=>r).map(([id,r])=>[id,distanceSeries(r.profile,field)]);
  if(!series.length){container.textContent='等待真实 API 距离曲线。';return;}
  const samples=series.flatMap(([,points])=>points);
  if(!samples.length){container.textContent='当前结果没有公共正向路线采样。';return;}
  const width=720,height=260,pad={l:66,r:40,t:34,b:58},w=width-pad.l-pad.r,h=height-pad.t-pad.b;
  const values=samples.map(p=>p.value).filter(v=>v!==null);
  let min=Math.min(0,...values),max=Math.max(0,...values);if(field==='similarity'||field==='raw_similarity'){min=-1;max=1;}if(min===max)max=min+1;
  const hi=Math.max(...samples.map(p=>p.distanceKm)),x=distance=>pad.l+distance/(hi||1)*w,y=v=>pad.t+(max-v)/(max-min)*h;
  let body='';
  for(let i=0;i<=4;i++){const value=min+(max-min)*i/4;body+=line(pad.l,y(value),width-pad.r,y(value));body+=text(pad.l-9,y(value)+5,format(value),'end');}
  for(let i=0;i<=(hi>0?4:0);i++){const distance=hi*i/4;body+=text(x(distance),height-36,i===0?'0（起点）':distance.toLocaleString('en-US',{maximumSignificantDigits:5}),'middle');}
  body+=line(x(0),pad.t,x(0),pad.t+h,'#7794a1','stroke-dasharray="3 4"');
  for(const [id,points] of series) {
    let d='',open=false;
    points.forEach(({distanceKm,value})=>{
      if(value===null){open=false;return;}
      d+=`${open?'L':'M'}${x(distanceKm).toFixed(2)},${y(value).toFixed(2)} `;open=true;
    });
    body+=`<path d="${d}" fill="none" stroke="${COLORS[id]}" stroke-width="2" stroke-linejoin="round"/>`;
  }
  const label=field==='raw_similarity'?'原始 PE 相似度':field==='similarity'?'共同空间相似度':'共同空间核幅度';
  body+=text(pad.l,18,label)+text((pad.l+width-pad.r)/2,height-7,'距起点的球面距离（公里）','middle');
  body+=`<text x="${width-140}" y="18" fill="${COLORS.a}">━ A</text><text x="${width-75}" y="18" fill="${COLORS.b}">━ B</text>`;
  container.innerHTML=svg(width,height,`沿公共正向球面路线的距离—${label}曲线；横轴为距起点的公里数，断线表示未定义`,body,14);
}

export function sensitivityEllipse(point) {
  const matrix=point.metric,values=point.eigenvalues;
  if(matrix===null || values.some(v=>v===null))return svg(80,80,'局部敏感度未定义：经纬度坐标图边界，无法解释局部差分',text(40,43,'未定义','middle'));
  const hi=Math.max(0,...values),lo=Math.max(0,Math.min(...values));
  const angle=.5*Math.atan2(2*matrix[0][1],matrix[0][0]-matrix[1][1])*180/Math.PI;
  const ry=hi>0?27*Math.sqrt(lo/hi):0;
  let body=line(5,40,75,40)+line(40,5,40,75)+text(71,51,'t₁')+text(44,11,'t₂');
  if(hi>0)body+=ry>0?`<ellipse cx="40" cy="40" rx="27" ry="${ry}" transform="rotate(${-angle} 40 40)" fill="#71dec4" fill-opacity=".12" stroke="#71dec4" stroke-width="1.4"/>`:`<line x1="13" y1="40" x2="67" y2="40" transform="rotate(${-angle} 40 40)" stroke="#71dec4" stroke-width="1.4"/>`;
  body+='<circle cx="40" cy="40" r="2" fill="#a8e3d0"/>';
  return svg(80,80,'局部敏感度方向椭圆，半轴与 M 特征值的平方根成比例，最大半轴固定显示长度',body);
}
