const edges=[0,5,10,15,20];

export function summarizeNeighborhood(local) {
  const bands=edges.slice(1).map((end,i)=>({start:edges[i],end,count:0,missing:0,mean:null,min:null,max:null}));
  if(!local?.points)return {total:0,defined:0,bands};
  let total=0,defined=0;
  const sums=bands.map(()=>0);
  local.points.forEach((sample,index)=>{
    if(index===local.center_index)return;
    const bandIndex=bands.findIndex(({start,end})=>sample.distance_degrees>start&&sample.distance_degrees<=end);
    if(bandIndex<0)return;
    const band=bands[bandIndex];total++;
    if(sample.similarity===null){band.missing++;return;}
    defined++;band.count++;sums[bandIndex]+=sample.similarity;
    band.min=band.min===null?sample.similarity:Math.min(band.min,sample.similarity);
    band.max=band.max===null?sample.similarity:Math.max(band.max,sample.similarity);
  });
  bands.forEach((band,i)=>{if(band.count)band.mean=sums[i]/band.count;});
  return {total,defined,bands};
}

export function renderLocalDetails(local) {
  if(!local?.points)return '<p class="hint">等待当前选点的球面邻域采样。</p>';
  const {total,defined,bands}=summarizeNeighborhood(local);
  const fmt=value=>value.toFixed(2);
  const rows=bands.map(band=>{
    const values=band.count?`样本网格平均 ${fmt(band.mean)} · 范围 ${fmt(band.min)} 至 ${fmt(band.max)}`:'没有可定义值';
    const range=band.count?`<div class="local-range" aria-hidden="true"><i style="left:${(band.min+1)*50}%;width:${Math.max((band.max-band.min)*50,.6)}%"></i><b style="left:${(band.mean+1)*50}%"></b></div>`:'';
    return `<div class="local-band"><div><strong>${band.start}–${band.end}°</strong><span>${band.count} 有效${band.missing?` · ${band.missing} 未定义`:''}</span></div>${range}<p>${values}</p></div>`;
  }).join('');
  return `<div class="local-summary"><strong>20° 邻域</strong><span>有效 ${defined}/${total} 个非中心采样点</span></div>
    ${defined?'':'<p class="local-empty">没有可定义的邻域相似度；可能是选点原始 PE 为零向量。</p>'}
    <div class="local-bands">${rows}</div><div class="local-axis" aria-hidden="true"><span>−1 不同向</span><span>0</span><span>+1 同向</span></div>
    <p class="hint">各点都与白点的原始 PE 比较，余弦相似度为 −1 至 1。距离为球面角度；每带平均只代表当前采样点，不是面积平均。带内范围也受距离和方向共同影响。</p>`;
}
