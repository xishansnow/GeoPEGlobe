export const SPECTRAL_COVERAGE_TOLERANCE=1e-6;
const scales=(max=32)=>({name:'frequencies',label:'尺度数 frequencies',min:1,max});
const sphereRadii=[{name:'min_radius',label:'最小尺度半径',min:.001,max:10,step:'any'},
  {name:'max_radius',label:'最大尺度半径',min:'min_radius',max:10,step:'any'}];
const planarParameters=[scales(),{name:'min_radius',label:'最小尺度半径（输入坐标度）',min:.1,max:360,step:'any'},
  {name:'max_radius',label:'最大尺度半径（输入坐标度）',min:'min_radius',max:360,step:'any'}];
const sphereNote='半径为无量纲角缩放参数，按几何序列取值；单尺度采用最小半径。';
const independentFrequencyNote='上游独立频率规则为 max_radius^(-s/(S-1))，忽略 min_radius；单尺度频率取 1，不沿用 SphereC/C+/M 的几何半径规则。';
const independentRadius={name:'max_radius',label:'最大尺度半径 max_radius',min:1,max:10000,step:'any'};
const planarNote='尺度使用经纬度平面的输入坐标度，不是球面测地距离；单尺度采用最小半径。';
const seed={name:'seed',label:'随机种子 seed',min:0,max:4294967295};
export const FIXED_ENCODERS={
  spherecplus:{label:'Sphere2Vec-sphereC+',defaults:{frequencies:8,min_radius:.05,max_radius:1},parameters:[scales(),...sphereRadii],
    description:'Sphere2Vec-sphereC+ 原式，每尺度 6 维。球面经纬度三角因子具有坐标图边界效应，边界处局部敏感度可未定义。来源：Mai et al.，Sphere2Vec。',note:sphereNote},
  wrap:{label:'wrap',defaults:{},parameters:[],
    description:'经纬度平面上的固定三角映射，4 维。固定全球范围（经度 −180°…180°，纬度 −90°…90°）归一化，保留坐标图边界语义。',note:'全球归一化范围固定，无其他方法参数。'},
  grid:{label:'Space2Vec-grid',defaults:{frequencies:4,min_radius:5,max_radius:180},parameters:planarParameters,
    description:'经纬度平面的 Space2Vec-grid 多尺度正弦与余弦，每尺度 4 维；映射到球面后仍保留平面坐标图边界效应。',note:planarNote},
  theory:{label:'Space2Vec-theory',defaults:{frequencies:4,min_radius:5,max_radius:180},parameters:planarParameters,
    description:'经纬度平面的 Space2Vec-theory，沿 0°、120°、240° 三方向投影，每尺度 6 维；不是球面测地编码。',note:planarNote},
  nerf:{label:'NeRF',defaults:{frequencies:4},parameters:[scales(10)],
    description:'输入单位球 xyz 的 NeRF 三维平面波，频率 π·2^s，每尺度 6 维。在球面上处处光滑；极点和日界线的局部指标仍定义。',note:'频率作用于三维单位球坐标，不作用于经纬度平面。'},
  rff:{label:'RFF',defaults:{feature_count:32,kernel_size:10,seed:0},parameters:[{name:'feature_count',label:'特征数 K',min:1,max:128},
    {name:'kernel_size',label:'方向向量协方差 kernel_size',min:.01,max:1000,step:'any'},seed],
    description:'经纬度平面的随机 Fourier 特征。固定全球范围（经度 −180°…180°，纬度 −90°…90°）归一化。',
    note:'kernel_size 是随机方向向量的协方差参数，不是标准差，也不是 RBF 的度单位核宽度。方向与相位随 JSON 的 lastCompleted 导出。'},
  rbf:{label:'RBF',defaults:{feature_count:32,kernel_size:20,center_layout:'global',seed:0},parameters:[{name:'feature_count',label:'特征数 K',min:1,max:64},
    {name:'kernel_size',label:'Gaussian 核宽度（°）',min:2,max:90,step:'any'},seed],
    description:'经纬度平面欧氏 Gaussian RBF；核距离不是球面测地距离，日界线两侧在平面中不相邻。',
    note:'中心为带种子的可重放合成布局，非训练数据中心；上游从训练坐标采样中心，本工具的适配不代表作者中心选择或完整论文复现。中心随 JSON 的 lastCompleted 导出，可用“显示中心”查看。'},
  spherec:{label:'Sphere2Vec-sphereC',defaults:{frequencies:4,min_radius:.05,max_radius:1},parameters:[scales(),...sphereRadii],
    description:'Sphere2Vec-sphereC 原式，每尺度 3 维。一般频率下可能有坐标图边界效应；所有频率为 1 时等价于光滑球面坐标。',note:sphereNote},
  spherem:{label:'Sphere2Vec-sphereM',defaults:{frequencies:4,min_radius:.05,max_radius:1},parameters:[scales(),...sphereRadii],
    description:'Sphere2Vec-sphereM 原式，每尺度 5 维。一般频率下可能有坐标图边界效应；所有频率为 1 时张成光滑球面坐标空间。',note:sphereNote},
  spheremplus:{label:'Sphere2Vec-sphereM+',defaults:{frequencies:4,max_radius:32},parameters:[scales(),independentRadius],
    description:'Sphere2Vec-sphereM+ 原式，每尺度 8 维。球面经纬度三角因子保留坐标图边界效应；频率规则与 DFS 相同。',note:independentFrequencyNote},
  spheredfs:{label:'Sphere2Vec-DFS',defaults:{frequencies:4,max_radius:32},parameters:[scales(7),independentRadius],
    description:'Sphere2Vec-DFS 球面经纬度三角因子组合，维数 4S²+4S，保留坐标图边界效应。',
    note:independentFrequencyNote}
};
export const ENCODERS={xyz:'三维球坐标',sh:'全球实球谐',slepian:'区域 Slepian + 低阶全球球谐',
  ...Object.fromEntries(Object.entries(FIXED_ENCODERS).map(([id,definition])=>[id,definition.label]))};
export function configurationName(config) {
  if(config.encoder==='slepian')return config.global_degree>=0?'区域 Slepian + 低阶全球球谐':'区域 Slepian（全球分支关闭）';
  return ENCODERS[config.encoder];
}
export function encoderDefaults(encoder,catalog={}) {
  const common={encoder,degree:encoder==='sh'?8:31,center:[110,35],radius:30,global_degree:['xyz','sh'].includes(encoder)||FIXED_ENCODERS[encoder]?-1:3,rank_tolerance:1e-9};
  const specific=encoder==='slepian'?{selection:'k',k:64,threshold:.05}:FIXED_ENCODERS[encoder]?.defaults??{};
  return structuredClone({...common,...specific,...catalog.defaults?.[encoder]});
}
export function createState(catalog={}) {
  return {schemaVersion:1,grid:{nlat:32,nlon:64},band:{min:8,max:16},
    slots:{a:{config:encoderDefaults('slepian',catalog),anchor:{lon:110,lat:35},channel:0},b:{config:encoderDefaults('sh',catalog),anchor:{lon:110,lat:35},channel:0}},
    view:{mode:'point',layer:'kernel',response:'raw_similarity',profile:'raw_similarity',cameraLinked:true,anchorLinked:true,colorsLocked:true,showRegion:false,showCenters:false,showNeighborhood:true},inspect:'a'};
}
export function prepareConfigEdit(previous,next,channel) {
  const config=structuredClone(next);
  if(config.encoder==='sh' && config.degree!==previous.degree)delete config.degrees;
  const dimensionKeys=['encoder','degree','global_degree','selection','k','threshold','center','radius','frequencies','min_radius','max_radius','feature_count','kernel_size','seed','center_layout'];
  if(dimensionKeys.some(key=>JSON.stringify(previous[key])!==JSON.stringify(config[key])))channel=0;
  return {config,channel};
}
const object=(v,name)=>{if(!v || typeof v!=='object' || Array.isArray(v))throw new Error(`${name} 必须为对象。`);return v;};
const number=(v,name,min=-Infinity,max=Infinity,integer=false)=>{
  if(typeof v!=='number' || !Number.isFinite(v) || v<min || v>max || (integer&&!Number.isInteger(v)))throw new Error(`${name} 必须是 ${min} 至 ${max} 的${integer?'整数':'有限数值'}。`);return v;
};
const choice=(v,allowed,name)=>{if(!allowed.includes(v))throw new Error(`${name} 无效：${String(v)}`);return v;};
function numericArray(v,name,length,nullable=false) {
  if(!Array.isArray(v) || (length!==undefined && v.length!==length))throw new Error(`${name} 的数组长度不符合合同。`);
  v.forEach(x=>{if(!(nullable&&x===null))number(x,name);});return v;
}
export function parseWorkspace(text) {
  const s=object(JSON.parse(text),'工作台 JSON');
  if(s.schemaVersion!==1)throw new Error('不支持的 JSON schemaVersion，需要版本 1。');
  object(s.slots,'slots');object(s.grid,'grid');object(s.band,'band');object(s.view,'view');
  number(s.grid.nlat,'nlat',16,96,true);if(s.grid.nlon!==2*s.grid.nlat)throw new Error('nlon 必须等于 2 × nlat。');
  number(s.band.min,'频带起点',0,Infinity,true);number(s.band.max,'频带终点',s.band.min,Infinity,true);
  for(const id of ['a','b']) {
    const slot=object(s.slots[id],id),c=object(slot.config,`${id}.config`),p=object(slot.anchor,`${id}.anchor`);
    choice(c.encoder,Object.keys(ENCODERS),'编码器');const fixed=FIXED_ENCODERS[c.encoder];
    number(c.degree,'degree',0,fixed?48:Infinity,true);
    if(fixed) {
      for(const {name,min,max,step} of fixed.parameters)number(c[name],name,typeof min==='string'?c[min]:min,max,step!=='any');
      if(c.global_degree!==undefined && c.global_degree!==-1)throw new Error(`${fixed.label} 不支持全球球谐拼接。`);
      if(c.encoder==='rbf')choice(c.center_layout,['global','cap'],'RBF 中心布局');
    }
    if(!fixed || c.center!==undefined) {
      numericArray(c.center,'center',2);number(c.center[0],'中心经度',-180,180);number(c.center[1],'中心纬度',-90,90);
    }
    if(!fixed || c.radius!==undefined)number(c.radius,'球冠半径',.1,180);
    if(!fixed)number(c.global_degree,'global_degree',-1,8,true);
    number(c.rank_tolerance,'rank_tolerance',1e-14,1e-3);
    if(c.encoder==='slepian') { choice(c.selection,['k','threshold','shannon'],'选择规则');if(c.selection==='k')number(c.k,'K',1,Infinity,true);if(c.selection==='threshold')number(c.threshold,'集中度阈值',0,1); }
    number(p.lon,'锚点经度',-180,180);number(p.lat,'锚点纬度',-90,90);number(slot.channel,'通道',0,Infinity,true);
    if(slot.camera) {
      object(slot.camera,'camera');for(const key of ['position','up','target'])numericArray(slot.camera[key],`camera.${key}`,3);
      if(Math.hypot(...slot.camera.position)<1.01 || Math.hypot(...slot.camera.up)<.1)throw new Error('相机位置或朝上方向无效。');
      if(Math.hypot(...slot.camera.target)>1e-8)throw new Error('本工作台相机目标固定为球心。');
    }
  }
  if(s.view.mode===undefined)s.view.mode='point';
  if(s.view.showNeighborhood===undefined)s.view.showNeighborhood=true;
  if(s.view.showRegion===undefined)s.view.showRegion=false;
  if(s.view.layer==='region'){s.view.layer='kernel';s.view.showRegion=true;}
  if(s.view.layer==='centers'){s.view.layer='kernel';s.view.showCenters=true;}
  if(['energy','band_energy','coordinate'].includes(s.view.layer))s.view.layer='kernel';
  s.view.response='raw_similarity';
  choice(s.view.mode,['structure','point','local','relation'],'功能');
  choice(s.view.layer,['energy','region','centers','band_energy','kernel','channel','coordinate'],'图层');choice(s.view.response,['kernel','similarity','raw_similarity'],'锚点响应');choice(s.view.profile,['kernel','similarity','raw_similarity'],'剖面响应');
  for(const key of ['cameraLinked','anchorLinked','colorsLocked','showRegion','showCenters','showNeighborhood'])if(typeof s.view[key]!=='boolean')throw new Error(`view.${key} 必须为布尔值。`);
  s.view.anchorLinked=true;s.slots.b.anchor={...s.slots.a.anchor};
  choice(s.inspect,['a','b'],'详情面板');
  return structuredClone(s);
}

export function validateEvaluation(data) {
  object(data,'API 响应');object(data.config,'config');const grid=object(data.grid,'grid');
  number(grid.nlat,'响应 nlat',1,Infinity,true);number(grid.nlon,'响应 nlon',1,Infinity,true);
  numericArray(grid.longitudes,'longitudes',grid.nlon);numericArray(grid.latitudes,'latitudes',grid.nlat);
  const fields=object(data.fields,'fields');
  for(const key of ['energy','band_energy','kernel','similarity','channel'])numericArray(fields[key],`fields.${key}`,grid.nlat*grid.nlon,true);
  if(fields.raw_similarity!==undefined)numericArray(fields.raw_similarity,'fields.raw_similarity',grid.nlat*grid.nlon,true);
  const spectrum=object(data.spectrum,'spectrum');numericArray(spectrum.degrees,'spectrum.degrees');
  for(const key of ['energy','fraction'])numericArray(spectrum[key],`spectrum.${key}`,spectrum.degrees.length);
  const info=object(data.info,'info');number(info.rank,'rank',1,Infinity,true);number(info.feature_count,'feature_count',info.rank,Infinity,true);
  choice(data.config.encoder,Object.keys(ENCODERS),'响应编码器');
  const fixed=FIXED_ENCODERS[data.config.encoder];
  if(fixed) {
    if(info.bandlimited===false) {
      if(info.actual_max_degree!==null)throw new Error(`${fixed.label} 非带限时实际最高阶应为空。`);
    } else if(info.bandlimited===true) {
      if(!['spherec','spherem'].includes(data.config.encoder))throw new Error('此方法没有已知的有限带限特例。');
      number(info.actual_max_degree,'实际带限',1,1,true);
      if(info.chart_boundary_effects!==false)throw new Error('有限带限特例应为光滑球面表示。');
    } else throw new Error(`${fixed.label} 应披露带限状态。`);
    if(info.chart_boundary_effects!==undefined && typeof info.chart_boundary_effects!=='boolean')throw new Error('chart_boundary_effects 必须为布尔值。');
    if(data.config.encoder==='nerf' && info.chart_boundary_effects!==false)throw new Error('NeRF 在单位球上光滑，chart_boundary_effects 应为 false。');
    number(info.spectral_max_degree,'频谱分析截断',0,48,true);
    number(info.spectral_energy_coverage,'频谱覆盖',0,1+SPECTRAL_COVERAGE_TOLERANCE);number(info.spectral_tail_fraction,'频谱尾部',0,1);
    const sumEnergy=spectrum.energy.reduce((a,b)=>a+b,0),sumFraction=spectrum.fraction.reduce((a,b)=>a+b,0);
    spectrum.energy.forEach(v=>number(v,'谱能量',0));spectrum.fraction.forEach(v=>number(v,'谱占比',0,1+SPECTRAL_COVERAGE_TOLERANCE));
    spectrum.degrees.forEach(v=>number(v,'频谱阶',0,info.spectral_max_degree,true));
    const close=(a,b)=>Math.abs(a-b)<=SPECTRAL_COVERAGE_TOLERANCE;
    if(sumEnergy>info.rank*(1+SPECTRAL_COVERAGE_TOLERANCE) || sumFraction>1+SPECTRAL_COVERAGE_TOLERANCE || !close(sumEnergy/info.rank,sumFraction) ||
      !close(sumFraction,info.spectral_energy_coverage) || !close(info.spectral_energy_coverage+info.spectral_tail_fraction,1) ||
      spectrum.energy.some((v,i)=>!close(v/info.rank,spectrum.fraction[i])))throw new Error('频谱必须保留原式秩分母及未覆盖尾部。');
    if(typeof info.gram_source!=='string' || !info.gram_source.trim())throw new Error('Gram 来源不能为空。');
    for(const key of ['gram_roundoff_floor','effective_rank_tolerance','spectral_quadrature_error'])number(info[key],key,0);
    if(info.gram_quadrature_error!==undefined)number(info.gram_quadrature_error,'gram_quadrature_error',0);
    if(info.band_complete!==undefined && typeof info.band_complete!=='boolean')throw new Error('band_complete 必须为布尔值。');
    if(info.band_complete===false && (info.band_energy!==null || fields.band_energy.some(v=>v!==null)))throw new Error('未计算的频带应完整遮罩并保留空能量。');
  } else {
    if(info.bandlimited!==undefined && info.bandlimited!==true)throw new Error('旧编码器应为有限带限对象。');
    number(info.actual_max_degree,'实际带限',0,Infinity,true);
  }
  const point=object(data.point,'point');numericArray(point.features,'point.features',info.feature_count,true);
  number(point.lon,'point.lon',-180,180);number(point.lat,'point.lat',-90,90);
  if(point.raw_norm!==undefined)number(point.raw_norm,'point.raw_norm',0);
  if(fixed && data.config.encoder!=='nerf' && info.chart_boundary_effects!==false && point.metric===null) {
    if(!Array.isArray(point.eigenvalues)||point.eigenvalues.length!==2||point.eigenvalues.some(v=>v!==null)||point.sensitivity!==null)throw new Error('空 metric 须同时披露空特征值和敏感度。');
  } else {
    numericArray(point.eigenvalues,'point.eigenvalues',2);number(point.sensitivity,'point.sensitivity');
    if(!Array.isArray(point.metric)||point.metric.length!==2)throw new Error('局部敏感度矩阵 M 应为 2 × 2。');
    point.metric.forEach(row=>numericArray(row,'point.metric',2));
  }
  if(point.finite_difference_relative_error!==undefined && point.finite_difference_relative_error!==null)number(point.finite_difference_relative_error,'差分相对误差',0);
  const profile=object(data.profile,'profile');numericArray(profile.angles,'profile.angles');
  for(const key of ['kernel','similarity'])numericArray(profile[key],`profile.${key}`,profile.angles.length,true);
  if(profile.raw_similarity!==undefined)numericArray(profile.raw_similarity,'profile.raw_similarity',profile.angles.length,true);
  if(data.neighborhood!==undefined) {
    const local=object(data.neighborhood,'neighborhood');
    if(local.definition!=='tangent_exponential_map')throw new Error('未知周边网格定义。');
    number(local.radius_degrees,'neighborhood.radius_degrees',0,180);
    number(local.step_degrees,'neighborhood.step_degrees',0,180);
    if(!Array.isArray(local.points)||!local.points.length)throw new Error('周边网格必须有采样点。');
    number(local.center_index,'neighborhood.center_index',0,local.points.length-1,true);
    local.points.forEach(sample=>{
      object(sample,'neighborhood point');number(sample.lon,'local.lon',-180,180);number(sample.lat,'local.lat',-90,90);
      number(sample.distance_degrees,'local.distance',0,local.radius_degrees+1e-8);
      if(sample.similarity!==null)number(sample.similarity,'local.similarity',-1,1);
    });
    const center=local.points[local.center_index];
    if(Math.abs(center.lon-point.lon)>1e-8||Math.abs(center.lat-point.lat)>1e-8||center.distance_degrees>1e-8)
      throw new Error('周边网格中心必须对应实际选点。');
  }
  return data;
}

export async function evaluateRequest(request,signal) {
  const response=await fetch('/api/evaluate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(request),signal});
  let body;try{body=await response.json();}catch{throw new Error(`API 返回不可读 JSON（HTTP ${response.status}）。`);}
  if(!response.ok || body.error)throw new Error(typeof body.error==='string'?body.error:`计算失败（HTTP ${response.status}）。`);
  const result=validateEvaluation(body);
  if(!Array.isArray(result.fields.raw_similarity)||!Array.isArray(result.profile.raw_similarity)||typeof result.point.raw_norm!=='number'||!result.neighborhood)
    throw new Error('本地数值服务版本较旧，请重启 Python 服务后刷新页面。');
  return result;
}
export function configureSelectionFields(form, selection) {
  for(const group of form.querySelectorAll('[data-selection]')) {
    const active=group.dataset.selection===selection;
    group.hidden=!active;
    for(const input of group.querySelectorAll('input'))input.disabled=!active;
  }
}
