import { Globe } from './globe.js';
import { LatestRequest, colorDomain, colorAt } from './core.mjs';
import { ENCODERS, FIXED_ENCODERS, encoderDefaults, createState, parseWorkspace, evaluateRequest, prepareConfigEdit, configurationName, configureSelectionFields } from './state.mjs';
import { escapeHTML as esc, format, renderSpectrum, renderProfile, sensitivityEllipse, bandlimitLabel, budgetSummary, spectrumSummary, diagnosticRows } from './charts.js';
import { renderPointEncoding, renderStructure, canOpenFeature } from './point-view.mjs';
import { boundaryMarkers, boundaryReadout } from './boundary-view.mjs';
import { renderLocalDetails } from './local-change-view.mjs';
import { regionInfo, centerLegend } from './region-view.mjs';

const $=selector=>document.querySelector(selector),$$=selector=>[...document.querySelectorAll(selector)];
const ids=['a','b'];
let state=createState(),catalog={},configTab='a',boundaryTab='a',toastTimer,manualAnchor={...state.slots.a.anchor},anchorDraftPending=false;
const slots=Object.fromEntries(ids.map(id=>[id,{gate:new LatestRequest(),result:null,shownRequest:null,phase:'waiting',timer:null,globe:null}]));
const fieldKey=()=>state.view.layer==='kernel'?state.view.response:state.view.layer;
const coordinate=p=>`${Math.abs(p.lon).toFixed(2)}° ${p.lon<0?'W':'E'} · ${Math.abs(p.lat).toFixed(2)}° ${p.lat<0?'S':'N'}`;
const resultMap=()=>Object.fromEntries(ids.map(id=>[id,slots[id].result]));
const metricRow=(label,value)=>`<div class="metric-row"><span>${esc(label)}</span><strong>${esc(value)}</strong></div>`;
function globalError(message) { const el=$('#global-error');el.textContent=message;el.hidden=!message; }
function toast(message) {clearTimeout(toastTimer);$('#toast').textContent=message;$('#toast').hidden=false;toastTimer=setTimeout(()=>$('#toast').hidden=true,4000);}
function status(id,phase,message) {
  slots[id].phase=phase;
  const el=$(`#status-${id}`);el.textContent=message;el.className=`status ${phase==='pending'?'busy':phase==='fresh'?'success':phase==='error'?'error':'config-stale'}`;
  $(`#card-${id}`).setAttribute('aria-busy',String(phase==='pending'));
  renderProfileContext();
}
function slotError(id,error) {
  const el=$(`#error-${id}`);el.textContent=error?.message??'';el.hidden=!error;
  if(error){status(id,'error',slots[id].result?'计算失败 · 旧图':'计算失败');renderNativeViews();renderLocalViews();renderFixedDiagnostics();}
}
function markDirty(id) {
  const slot=slots[id];slot.gate.invalidate();clearTimeout(slot.timer);
  slotError(id,null);status(id,'dirty',slot.result?'待更新 · 旧图':'待计算');
  renderBudget();renderInspector();renderNativeViews();renderLocalViews();renderFixedDiagnostics();
}
function queue(id,delay=650) {
  clearTimeout(slots[id].timer);renderFixedDiagnostics();slots[id].timer=setTimeout(()=>submit(id),delay);
}
const numeric=(name,value,{min,max,step='1'}={})=>`<input data-value="${name}" name="${name}" type="number" value="${esc(value)}" ${min!==undefined?`min="${min}"`:''} ${max!==undefined?`max="${max}"`:''} step="${step}" required>`;
const option=(value,label,current)=>`<option value="${esc(value)}" ${value===current?'selected':''}>${esc(label)}</option>`;

function renderConfig(id) {
  const stored=state.slots[id].config,fixed=FIXED_ENCODERS[stored.encoder];
  const c=fixed?{...encoderDefaults(stored.encoder,catalog),...stored}:stored;
  const regional=c.encoder==='slepian',rbfCap=c.encoder==='rbf'&&c.center_layout==='cap';
  const degreeMax=fixed?48:(c.encoder==='sh'?catalog.limits?.sh_degree:catalog.limits?.degree)?.[1];
  const descriptions={
    xyz:'三维球坐标参照。原始坐标通道与地球显示坐标轴采用各自明确约定；共同核由数值 API 计算。',
    sh:'完整实球谐前端。改变最高阶会同时改变带限与特征维数，C/r 的常数分布不代表尺度相同。',
    slepian:'球冠区域集中模式与低阶全球分支。固定 K、集中度阈值与 Shannon 规则分别选择。来源：Rao et al. (2026)。',
  };
  $(`#config-${id}`).innerHTML=`<form data-config-form="${id}" novalidate>
    <label>前端类型<select name="encoder" data-value="encoder">${Object.entries(ENCODERS).map(([key,label])=>option(key,label,c.encoder)).join('')}</select></label>
    <p class="encoder-description">${esc(fixed?.description??descriptions[c.encoder])}</p>
    ${c.encoder!=='xyz'?`<label>${fixed?'频谱分析截断 L':regional?'区域最高阶 L':'最高球谐阶 L'}${numeric('degree',c.degree,{min:0,max:degreeMax})}</label>`:''}
    ${fixed?`<div class="config-group">${fixed.parameters.map(({name,label,min,max,step})=>`<label>${esc(label)}${numeric(name,c[name],{min:typeof min==='string'?c[min]:min,max,step})}</label>`).join('')}
      <p class="config-subnote">${esc(fixed.note)} 通常非有限带限，无全球球谐拼接。分析截断仅用于球谐频谱及分带投影，不改变原式空间图、核与原始通道。未覆盖尾部单独披露。来源：TorchSpatial 固定实现。</p></div>`:''}
    ${c.encoder==='rbf'?`<label>合成中心布局<select name="center_layout" data-value="center_layout">${option('global','全球合成布局',c.center_layout)}${option('cap','球冠合成布局',c.center_layout)}</select></label>`:''}
    ${regional||rbfCap?`<div class="input-pair"><label>球冠中心经度${numeric('center-lon',c.center[0],{min:-180,max:180,step:'any'})}</label><label>球冠中心纬度${numeric('center-lat',c.center[1],{min:-90,max:90,step:'any'})}</label></div>
    <div class="input-pair"><label>半径（°）${numeric('radius',c.radius,{min:.1,max:180,step:'any'})}</label>${regional?`<label>全球分支阶数${numeric('global_degree',c.global_degree,{min:-1,max:8})}</label>`:''}</div><p class="config-subnote">${regional?'全球分支 −1 表示关闭。':'球冠只限定合成中心布局；Gaussian 核仍按经纬度平面距离计算。'}可在右栏将锚点设为中心。</p>`:''}
    ${c.encoder==='slepian'?`<div class="config-group"><label>区域模式选择<select name="selection" data-value="selection">${option('k','固定 K',c.selection)}${option('threshold','集中度阈值 λ > τ',c.selection)}${option('shannon','Shannon 数向上取整',c.selection)}</select></label>
      <label data-selection="k" ${c.selection!=='k'?'hidden':''}>区域模式数 K${numeric('k',c.k??64,{min:1,max:256})}</label>
      <label data-selection="threshold" ${c.selection!=='threshold'?'hidden':''}>集中度阈值 τ${numeric('threshold',c.threshold??.05,{min:0,max:1,step:'any'})}</label>
      <p class="config-subnote">模式序号不是球谐频率。实际保留数以返回值为准。</p></div>`:''}
    <label>相对奇异值秩阈值${numeric('rank_tolerance',c.rank_tolerance,{min:1e-14,max:1e-3,step:'any'})}</label>
    <label>原始通道索引（从 0 起）${numeric('channel',state.slots[id].channel,{min:0})}</label><p id="channel-description-${id}" class="channel-description"></p>
    <div class="button-pair"><button type="submit" class="accent-outline">计算 ${id.toUpperCase()}</button><button type="button" data-reset="${id}" class="quiet">恢复预设</button></div>
    <p class="hint">有效参数编辑后自动更新。计算期间保留旧图。</p>
  </form>`;
  const form=$(`[data-config-form="${id}"]`);
  configureSelectionFields(form,c.selection);
  form.addEventListener('input',event=>handleConfigInput(id,event));
  form.addEventListener('change',event=>{if(event.target.name==='encoder')changeEncoder(id,event.target.value);else if(event.target.name==='selection'){
    configureSelectionFields(form,event.target.value);handleConfigInput(id,event);
  }else if(event.target.name==='center_layout')handleConfigInput(id,event);});
  form.addEventListener('submit',event=>{event.preventDefault();markDirty(id);if(readConfig(id,true))submit(id);});
  form.querySelector('[data-reset]').addEventListener('click',()=>{
    markDirty(id);state.slots[id].config=encoderDefaults(id==='a'?'slepian':'sh',catalog);state.slots[id].channel=0;renderConfig(id);submit(id);
  });
  renderChannelDescription(id);
}
function readConfig(id,report=false) {
  const form=$(`[data-config-form="${id}"]`),get=name=>form.elements.namedItem(name),number=name=>Number(get(name).value);
  for(const input of form.querySelectorAll('input'))input.setCustomValidity('');
  if(get('min_radius')&&get('max_radius')) {
    get('max_radius').min=get('min_radius').value;
    if(number('max_radius')<number('min_radius'))get('max_radius').setCustomValidity('最大尺度半径不得小于最小尺度半径。');
  }
  if(!form.checkValidity()){if(report)form.reportValidity();return false;}
  const c=structuredClone(state.slots[id].config);
  for(const key of ['degree','radius','global_degree','rank_tolerance','k','threshold',...(FIXED_ENCODERS[c.encoder]?.parameters.map(p=>p.name)??[])])if(get(key)&&!get(key).disabled)c[key]=number(key);
  for(const key of ['selection','center_layout'])if(get(key))c[key]=get(key).value;
  if(get('center-lon'))c.center=[number('center-lon'),number('center-lat')];
  const edit=prepareConfigEdit(state.slots[id].config,c,number('channel'));
  state.slots[id].config=edit.config;state.slots[id].channel=edit.channel;get('channel').value=edit.channel;return true;
}
function handleConfigInput(id,event) {
  if(event.target.name==='encoder')return;markDirty(id);
  if(readConfig(id)) {
    if(event.target.name==='center_layout')renderConfig(id);
    queue(id);
  }
}
function changeEncoder(id,encoder) {
  markDirty(id);const previous=state.slots[id].config;
  const next=encoderDefaults(encoder,catalog);
  state.slots[id].config={...next,center:[...(previous.center??next.center)],radius:previous.radius??next.radius};state.slots[id].channel=0;
  renderConfig(id);queue(id,150);
}
function readShared(report=false) {
  const controls=[$('#grid-size'),$('#band-min'),$('#band-max')];
  $('#band-max').setCustomValidity('');
  if(Number($('#band-max').value)<Number($('#band-min').value))$('#band-max').setCustomValidity('频带终点不得小于起点。');
  if(controls.some(el=>!el.checkValidity())){if(report)controls.find(el=>!el.checkValidity()).reportValidity();return false;}
  const nlat=Number($('#grid-size').value);state.grid={nlat,nlon:2*nlat};state.band={min:Number($('#band-min').value),max:Number($('#band-max').value)};return true;
}
function currentRequest(id) {
  const s=state.slots[id];return structuredClone({config:s.config,grid:state.grid,anchor:s.anchor,band:state.band,channel:s.channel});
}
async function submit(id) {
  const slot=slots[id];clearTimeout(slot.timer);
  if(applyPendingAnchor())return;
  if(!readShared() || !readConfig(id))return;
  renderFixedDiagnostics();
  const request=currentRequest(id);slotError(id,null);status(id,'pending',slot.result?'计算中 · 旧图':'计算中');renderBudget();renderInspector();
  await slot.gate.run(signal=>evaluateRequest(request,signal),result=>{
    slot.result=result;slot.shownRequest={...request,config:structuredClone(result.config)};
    state.slots[id].config=structuredClone(result.config);status(id,'fresh','已更新');slotError(id,null);
    slot.globe?.setModel(result.config,result.info);slot.globe?.setAnchor(request.anchor,result.profile.angles);
    slot.globe?.setNeighborhood(result.neighborhood);
    renderConfig(id);renderAll();
  },error=>{slotError(id,error);renderBudget();renderInspector();});
}
function setAnchor(id,point,locate=false) {
  anchorDraftPending=false;manualAnchor={lon:point.lon,lat:point.lat};
  for(const target of ids){markDirty(target);state.slots[target].anchor={lon:point.lon,lat:point.lat};if(locate)slots[target].globe?.locate(point);queue(target,120);}
  state.inspect=id;renderInspectTabs();updateAnchorInputs();
}
function handleAnchorInput() {anchorDraftPending=true;ids.forEach(markDirty);}
function submitManualAnchor() {
  const lon=Number($('#anchor-lon').value),lat=Number($('#anchor-lat').value);
  if(!$('#anchor-form').reportValidity()||!Number.isFinite(lon)||!Number.isFinite(lat)||Math.abs(lon)>180||Math.abs(lat)>90){
    globalError('请先输入有效锚点：经度 −180°～180°，纬度 −90°～90°。');return false;
  }
  globalError('');setAnchor(state.inspect,{lon,lat},true);return true;
}
function applyPendingAnchor() {if(!anchorDraftPending)return false;submitManualAnchor();return true;}
function updateAnchorInputs() {
  $('#anchor-lon').value=Number(manualAnchor.lon.toFixed(6));$('#anchor-lat').value=Number(manualAnchor.lat.toFixed(6));
}
function renderInspectTabs() {$$('[data-inspect]').forEach(el=>el.setAttribute('aria-pressed',String(el.dataset.inspect===state.inspect)));renderInspector();}
function selectConfigTab(id) {
  configTab=id;$$('[data-config-tab]').forEach(el=>el.setAttribute('aria-selected',String(el.dataset.configTab===id)));
  ids.forEach(key=>$(`#config-${key}`).hidden=key!==id);
}
function selectBoundaryTab(id) {
  boundaryTab=id;
  for(const side of ids){$(`#boundary-tab-${side}`).setAttribute('aria-selected',String(side===id));$(`#boundary-panel-${side}`).hidden=side!==id;}
}
function renderChannelDescription(id) {
  const el=$(`#channel-description-${id}`);if(!el)return;
  const channel=slots[id].result?.info.channels?.[state.slots[id].channel];el.textContent=channel?channel.name:'';
}
function renderProfileContext() {
  for(const id of ids) {
    const label=$(`#profile-encoder-${id}`),config=slots[id].result?.config??state.slots[id].config;
    if(label)label.textContent=`${id.toUpperCase()}（${id==='a'?'绿线':'蓝线'}）：${configurationName(config)}`;
  }
  const origin=$('#profile-origin'),progress=$('#profile-status');
  if(origin) {
    const points=ids.map(id=>slots[id].result?.point);
    origin.textContent=points.every(Boolean)&&points[0].lon===points[1].lon&&points[0].lat===points[1].lat?
      `两条曲线的实际起点：${coordinate(points[0])}`:
      ids.map((id,i)=>`${id.toUpperCase()} 实际起点：${points[i]?coordinate(points[i]):'等待计算'}`).join('；');
  }
  if(progress)progress.textContent=ids.map(id=>{
    const slot=slots[id],names={waiting:'等待计算',dirty:'待更新',pending:'计算中',fresh:'已更新',error:'计算失败'};
    return `${id.toUpperCase()}：${names[slot.phase]??slot.phase}${slot.result&&slot.phase!=='fresh'?'，仍显示旧曲线':''}`;
  }).join('；');
}
function openMapExplorer() {
  $('#map-explorer')?.scrollIntoView({block:'start'});
}
function renderMode() {
  const mode=state.view.mode??'point';
  $$('[data-mode]').forEach(el=>el.setAttribute('aria-pressed',String(el.dataset.mode===mode)));
  for(const key of ['structure','point','local','relation'])$(`#${key}-panel`).hidden=key!==mode;
}
function activateMode(mode) {
  state.view.mode=mode;
  const relationship=mode==='local'||mode==='relation';
  if(relationship) {
    state.view.layer='kernel';state.view.response='raw_similarity';
    if(mode==='local'){state.view.showNeighborhood=true;$('#show-neighborhood').checked=true;}
  }
  renderMode();
  if(relationship)renderLayers();
}
function renderLocalViews() {
  for(const id of ids) {
    const slot=slots[id],result=slot.result;
    $(`#local-title-${id}`).textContent=configurationName(result?.config??state.slots[id].config);
    $(`#local-visual-${id}`).innerHTML=result?
      `<p class="local-origin">${esc(coordinate(result.point))} · ${slot.phase==='fresh'?'当前选点':'上次完成结果，待更新'}</p>${renderLocalDetails(result.neighborhood)}`:
      '<p class="hint">等待当前选点的球面邻域采样。</p>';
  }
}
function renderBoundarySidebar() {
  for(const id of ids) {
    const slot=slots[id],result=slot.result;
    $(`#boundary-title-${id}`).textContent=configurationName(result?.config??state.slots[id].config);
    const oldConfig=result&&JSON.stringify(result.config)!==JSON.stringify(state.slots[id].config);
    $(`#boundary-sidebar-${id}`).innerHTML=result?
      `${oldConfig?'<p class="hint">显示上次完成的旧配置；当前编码器参数待更新。</p>':''}${boundaryReadout(boundaryMarkers(result.info.boundary_diagnostics))}`:
      '<p class="hint">等待编码器的同点坐标检查。</p>';
  }
}
function renderFixedDiagnostics() {
  renderBoundarySidebar();
  const stale=ids.filter(id=>slots[id].result&&JSON.stringify(slots[id].result.config)!==JSON.stringify(state.slots[id].config));
  const el=$('#spectrum-status');el.hidden=!stale.length;
  el.textContent=stale.length?`${stale.map(id=>id.toUpperCase()).join('、')}：旧配置频谱，当前编码器参数待更新。`:'';
}
function renderNativeViews() {
  const messages=[];
  for(const id of ids) {
    const slot=slots[id],result=slot.result;
    $(`#structure-visual-${id}`).innerHTML=renderStructure(result,id,slot.phase);
    $(`#point-visual-${id}`).innerHTML=renderPointEncoding(result,id);
    $(`#point-title-${id}`).textContent=configurationName(result?.config??state.slots[id].config);
    messages.push(`${id.toUpperCase()}：${slot.phase==='fresh'?'当前选点':'上次完成选点／待更新'}${result?` ${coordinate(result.point)}`:''}`);
  }
  $('#point-view-status').textContent=messages.join('；');
}
function renderLayers() {
  const key=fieldKey(),coordinateMode=key==='coordinate',signed=['kernel','similarity','raw_similarity','channel'].includes(key);
  const common=coordinateMode?[0,1]:['similarity','raw_similarity'].includes(key)?[-1,1]:colorDomain(ids.map(id=>slots[id].result?.fields[key]),signed);
  const labels={region:'区域构造范围',centers:'中心节点',energy:'固定表示强度 C/r · 非性能',band_energy:'所选频带的分布 Cᵦ/Eᵦ',kernel:'共同空间核幅度 k',similarity:'共同空间相似度 ρ',raw_similarity:'原始 PE 余弦相似度',channel:'单个原始特征 φᵢ',coordinate:'同点坐标检查'};
  $('#show-channel').checked=key==='channel';
  $('#region-layer-info').hidden=!state.view.showRegion;
  if(state.view.showRegion)$('#region-layer-info').textContent=ids.map(id=>`${id.toUpperCase()}：${regionInfo(slots[id].result?.config??state.slots[id].config).label}`).join('；');
  $('#center-layer-legend').hidden=!state.view.showCenters;
  for(const id of ids) {
    const result=slots[id].result;if(!result)continue;
    const domain=coordinateMode?[0,1]:state.view.colorsLocked?common:['similarity','raw_similarity'].includes(key)?[-1,1]:colorDomain([result.fields[key]],signed);
    slots[id].domain=domain;
    if(coordinateMode)slots[id].globe?.clearField();else slots[id].globe?.setField(result.fields[key],result.grid,domain,signed);
    slots[id].globe?.showBoundaryChecks(coordinateMode);
    slots[id].globe?.showRegion?.(!coordinateMode&&state.view.showRegion);
    slots[id].globe?.showCenters(!coordinateMode&&state.view.showCenters);
    slots[id].globe?.showNeighborhood(!coordinateMode&&key==='raw_similarity'&&state.view.showNeighborhood);
    const caption=$(`#globe-${id} .globe-caption`);if(caption)caption.textContent=coordinateMode?'当前：三个同点检查 · 点击仍可换选点':key==='raw_similarity'?'当前：原始 PE 相似度 · 小点为选点周边 2° 网格':(['similarity'].includes(key)?'当前：与白点有多像 · 点击可换选点':key==='energy'?'当前：固定表示强度 · 亮区不随白点移动':`当前：${labels[key]} · 拖动旋转`);
    const legend=$(`#legend-${id}`),canvas=legend.querySelector('canvas'),ctx=canvas.getContext('2d');
    const numeric=!coordinateMode;
    canvas.hidden=!numeric;legend.querySelector('.legend-min').hidden=!numeric;legend.querySelector('.legend-max').hidden=!numeric;
    if(numeric){for(let i=0;i<canvas.width;i++){const value=domain[0]+(domain[1]-domain[0])*i/(canvas.width-1);ctx.fillStyle=`rgb(${colorAt(value,domain,signed).join(',')})`;ctx.fillRect(i,0,1,canvas.height);}}
    legend.querySelector('.legend-min').textContent=numeric?format(domain[0]):'';legend.querySelector('.legend-max').textContent=numeric?format(domain[1]):'';
    const shown=slots[id].shownRequest,detail=key==='band_energy'?` · ℓ ${shown.band.min}–${shown.band.max}`:key==='channel'?` · i=${shown.channel}`:'';
    const incomplete=key==='band_energy'&&result.info.band_complete===false?' · 超出分析截断，未计算':'';
    legend.querySelector('.legend-label').textContent=coordinateMode?'点色：绿一致 · 橙有差异 · 灰极小幅值':`${state.view.colorsLocked?'共同':'独立'}色标 · ${labels[key]}${detail}${incomplete}`;
    $(`#scale-legend-${id}`).innerHTML=`<b>${id.toUpperCase()}</b> ${centerLegend(result.config,result.info.centers??[])}`;
    const readout=$(`#boundary-readout-${id}`);readout.hidden=!coordinateMode;
    if(coordinateMode)readout.innerHTML=boundaryReadout(boundaryMarkers(result.info.boundary_diagnostics));
    $(`#card-${id} .globe-footer`).hidden=false;
    $(`#title-${id}`).textContent=configurationName(result.config);
    const samplingWarning=result.info.warnings?.some(v=>v.includes('Nyquist')||v.includes('全部采为近零'));
    $(`#subtitle-${id}`).textContent=`${bandlimitLabel(result.info)} · ${result.info.feature_count} 特征 · r = ${result.info.rank}${samplingWarning?' · ⚠ 网格可能混叠':''}`;
    $(`#coordinate-${id}`).textContent=coordinate({lon:result.point.lon,lat:result.point.lat});
  }
}
function renderBudget() {
  const note=$('#budget-note'),a=slots.a.result?.info,b=slots.b.result?.info;
  const stale=ids.filter(id=>slots[id].phase!=='fresh'&&slots[id].result);
  if(!a || !b){note.textContent='待 API 返回两侧的实际带限、特征数与数值秩。';return;}
  const {match,text}=budgetSummary(a,b);
  note.classList.toggle('mismatch',!match||stale.length>0);
  note.textContent=text;
  if(stale.length)note.textContent+=` ${stale.map(id=>id.toUpperCase()).join('、')} 正显示上次完成结果，尚非当前参数。`;
}
function renderCharts() {
  renderProfileContext();
  $('#profile-title').textContent=state.view.profile==='kernel'?'距离—共同空间核幅度（进阶）':state.view.profile==='raw_similarity'?'距离—原始 PE 相似度':'距离—共同空间相似度（进阶）';
  renderSpectrum($('#spectrum-chart'),resultMap(),state.band,degree=>{
    ids.forEach(markDirty);state.band={min:degree,max:degree};$('#band-min').value=degree;$('#band-max').value=degree;
    renderLayers();ids.forEach(id=>queue(id,120));
  });
  $('#band-label').textContent=`ℓ = ${state.band.min}–${state.band.max}`;
  $('#spectrum-summary').textContent=ids.filter(id=>slots[id].result).map(id=>{
    return `${id.toUpperCase()}：${spectrumSummary(slots[id].result)}`;
  }).join('；');
  renderProfile($('#profile-chart'),resultMap(),state.view.profile);
  const actual=ids.map(id=>slots[id].result?.point),unequal=actual.every(Boolean)&&(actual[0].lon!==actual[1].lon||actual[0].lat!==actual[1].lat);
  $('#profile-note').textContent=`0 公里是实际起点，向右沿当前球面路线的一侧走远。${state.view.profile==='kernel'?'纵轴为处理后的共同空间核幅度，最高处不保证在起点。':state.view.profile==='raw_similarity'?'纵轴是原始 PE 向量的余弦相似度；绿线是 A，蓝线是 B。':'纵轴是处理后的共同空间相似度；绿线是 A，蓝线是 B。'}${unequal?'两侧实际起点不同，请结合坐标解释。':''}这条路线的变化快慢不直接代表预测好坏；有限采样可能漏掉细微变化。`;
}
function renderInspector() {
  for(const id of ids) {
  const slot=slots[id],r=slot.result;
  if(!r){$(`#point-metrics-${id}`).innerHTML='<p class="hint">等待真实锚点特征与敏感度。</p>';$(`#point-features-${id}`).textContent='等待 API。';$(`#diagnostics-${id}`).textContent='等待 API。';continue;}
  const p=r.point,info=r.info,values=p.eigenvalues,defined=p.metric!==null&&values.every(v=>v!==null),hi=defined?Math.max(...values):null,lo=defined?Math.min(...values):null;
  $(`#point-metrics-${id}`).innerHTML=`<p class="hint">${id.toUpperCase()} 图像锚点：${esc(coordinate(p))}${slot.phase!=='fresh'?' · 上次完成结果，待更新':''}</p>
    <div class="sensitivity">${sensitivityEllipse(p)}<div><div class="big-value">${format(p.sensitivity,5)}</div><div class="metric-caption">局部敏感度 tr(M)/r<br>切向角度以弧度计 · 非预测精度</div></div></div>
    ${metricRow('锚点归一化响应 C(x₀)/r',format(p.energy,5))}${metricRow('M 特征值（未按秩归一化）',values.map(v=>format(v,4)).join(' / '))}${metricRow('方向特征值之比',!defined?'未定义':lo>1e-14?format(hi/lo):'奇异 / 不定义')}
    <p class="hint">${defined?'椭圆半轴 ∝ √λ，最大半轴固定显示长度，仅示方向与相对各向异性。t₁、t₂ 是后端正交单位切向基，极区 t₁ 不一定朝东。':'经纬度坐标图边界处局部差分未定义；原式空间图、核与特征仍可查看。'}</p>
    ${info.warnings?.length?`<ul class="warning-list">${info.warnings.map(v=>`<li>${esc(v)}</li>`).join('')}</ul>`:''}`;
  $(`#point-features-${id}`).innerHTML=p.features.map((value,index)=>`<div class="feature-row" title="${esc(info.channels?.[index]?.name??`通道 ${index}`)}"><span>${index} · ${esc(info.channels?.[index]?.name??'原始通道')}</span><span>${format(value,6)}</span></div>`).join('');
  const requested=slot.shownRequest;
  $(`#diagnostics-${id}`).innerHTML=[
    ...diagnosticRows(info).map(([label,value])=>metricRow(label,value)),
    metricRow('有限差分步长（rad）',format(p.finite_difference_step)),metricRow('差分相对误差',format(p.finite_difference_relative_error)),
    metricRow('所选频带 Eᵦ',info.band_complete===false?'未计算（超出分析截断）':format(info.band_energy,5)),metricRow('构造 / 评价（s）',`${format(info.build_seconds)} / ${format(info.evaluation_seconds)}`),
    metricRow('实际显示网格',`${r.grid.nlat} × ${r.grid.nlon}`),metricRow('经 / 纬采样间隔',`${format(360/r.grid.nlon)}° / ${format(180/r.grid.nlat)}°`),
    `<p class="hint">${esc(info.normalization??'dμ=dΩ/(4π)')}。${info.bandlimited===false?'特征条件数为保留 Gram 本征值最大最小比的平方根；原式特征重构残差衡量丢弃方向在全球面积特征范数下的相对损失。TᵀGT − I 衡量白化正交性，投影积分复核差异与未覆盖尾部独立披露；NeRF 使用解析系数，节点复核不适用。':'正交性误差不衡量秩截断损失；请结合重构残差与丢弃奇异值解释。'}</p>`,
    `<p class="hint">${requested.config.encoder==='slepian'?'区域 Slepian + 低阶全球球谐；Rao et al. (2026)。模式符号与简并基不唯一。':requested.config.encoder==='spherecplus'?'Sphere2Vec-sphereC+；Mai et al.，Sphere2Vec。原式构造与有限球谐投影分别评价，尺度半径不是公里或球冠角度。':'原始特征与共同子空间量分别显示。'}</p>`
  ].join('');
  }
}
function renderAll() {renderMode();renderNativeViews();renderLocalViews();renderLayers();renderFixedDiagnostics();renderBudget();renderCharts();renderInspector();ids.forEach(renderChannelDescription);}

function bindControls() {
  $$('[data-mode]').forEach(el=>el.addEventListener('click',()=>activateMode(el.dataset.mode)));
  $('#point-panel').addEventListener('click',event=>{
    const item=event.target.closest('[data-feature-index]');if(!item)return;
    const id=item.dataset.slot,index=Number(item.dataset.featureIndex);
    if(!ids.includes(id)||!Number.isInteger(index))return;
    if(!canOpenFeature(slots[id],state.slots[id],index)){toast('这是上次结果的特征；请等待当前编码器和选点更新。');return;}
    state.inspect=id;state.slots[id].channel=index;renderInspectTabs();renderConfig(id);selectConfigTab(id);
    state.view.layer='channel';renderLayers();markDirty(id);submit(id);openMapExplorer();
  });
  $$('[data-config-tab]').forEach(el=>el.addEventListener('click',()=>selectConfigTab(el.dataset.configTab)));
  $$('[data-boundary-tab]').forEach(el=>el.addEventListener('click',()=>selectBoundaryTab(el.dataset.boundaryTab)));
  $$('[data-locate]').forEach(el=>el.addEventListener('click',()=>slots[el.dataset.locate].globe?.locate(state.slots[el.dataset.locate].anchor)));
  $('#show-channel').addEventListener('change',event=>{state.view.layer=event.target.checked?'channel':'kernel';state.view.response='raw_similarity';renderLayers();});
  for(const [selector,key] of [['#sync-camera','cameraLinked'],['#lock-colors','colorsLocked'],['#show-region','showRegion'],['#show-centers','showCenters'],['#show-neighborhood','showNeighborhood']]) {
    $(selector).addEventListener('change',event=>{
      state.view[key]=event.target.checked;
      if(key==='cameraLinked'&&event.target.checked){const source=slots[state.inspect].globe?.cameraState();if(source)ids.forEach(id=>slots[id].globe?.setCamera(source));}
      renderLayers();
    });
  }
  $('#profile-kind').addEventListener('change',event=>{state.view.profile=event.target.value;renderCharts();});
  for(const selector of ['#grid-size','#band-min','#band-max'])$(selector).addEventListener('input',()=>{ids.forEach(markDirty);if(readShared()){renderCharts();ids.forEach(id=>queue(id));}});
  $('#evaluate-all').addEventListener('click',()=>{
    ids.forEach(markDirty);if(!readShared(true))return;for(const id of ids)if(readConfig(id,true))submit(id);
  });
  $('#anchor-form').addEventListener('submit',event=>{event.preventDefault();submitManualAnchor();});
  // Even before submitting an anchor edit, an in-flight response belongs to an old input.
  $('#anchor-form').addEventListener('input',handleAnchorInput);
  $('#anchor-to-center').addEventListener('click',()=>{
    const id=configTab,c=state.slots[id].config;
    if(c.encoder!=='slepian' && !(c.encoder==='rbf'&&c.center_layout==='cap')){toast('当前编码器没有球冠中心参数。');return;}
    if(!$('#anchor-form').reportValidity())return;
    markDirty(id);c.center=[Number($('#anchor-lon').value),Number($('#anchor-lat').value)];state.slots[id].channel=0;renderConfig(id);selectConfigTab(id);submit(id);
  });
  $('#export-json').addEventListener('click',exportJSON);
  $('#import-json').addEventListener('click',()=>$('#json-file').click());
  $('#json-file').addEventListener('change',async event=>{
    const file=event.target.files[0];if(!file)return;
    try {
      if(file.size>1024*1024)throw new Error('配置 JSON 超过 1 MiB，请选择工作台导出的配置文件。');
      const imported=parseWorkspace(await file.text());
      ids.forEach(markDirty);state=imported;manualAnchor={...state.slots.a.anchor};anchorDraftPending=false;globalError('');hydrateControls();
      for(const id of ids){if(state.slots[id].camera)slots[id].globe?.setCamera(state.slots[id].camera);submit(id);}
      toast('配置已导入，正在重新计算真实图层。');
    }catch(error){globalError(`JSON 导入失败：${error.message}`);}finally{event.target.value='';}
  });
  $('#export-png').addEventListener('click',()=>exportPNG().catch(error=>globalError(`PNG 导出失败：${error.message}`)));
}
function hydrateControls() {
  ids.forEach(renderConfig);selectConfigTab(configTab);selectBoundaryTab(boundaryTab);renderInspectTabs();updateAnchorInputs();
  const nlat=state.grid.nlat;if(![...$('#grid-size').options].some(o=>Number(o.value)===nlat))$('#grid-size').add(new Option(`${nlat} × ${2*nlat}`,nlat));
  $('#grid-size').value=nlat;$('#band-min').value=state.band.min;$('#band-max').value=state.band.max;
  for(const [selector,key] of [['#sync-camera','cameraLinked'],['#lock-colors','colorsLocked'],['#show-region','showRegion'],['#show-centers','showCenters'],['#show-neighborhood','showNeighborhood']])$(selector).checked=state.view[key];
  $('#profile-kind').value=state.view.profile;
  if(['local','relation'].includes(state.view.mode))activateMode(state.view.mode);renderAll();
}
function download(blob,name) {
  const url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=name;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),30000);
}
function filename(extension) {return `encoder-globe-${new Date().toISOString().replace(/[:.]/g,'-')}.${extension}`;}
function exportJSON() {
  if(anchorDraftPending){globalError('手动输入尚未应用；请先提交位置，再导出包含共同选点的 JSON。');return;}
  if(!readShared(true))return;
  for(const id of ids)if(!readConfig(id,true)){selectConfigTab(id);return;}
  const workspace=structuredClone(state);
  for(const id of ids) {const camera=slots[id].globe?.cameraState();if(camera)workspace.slots[id].camera=camera;}
  workspace.exportedAt=new Date().toISOString();workspace.measure='原始 PE 余弦相似度直接使用 φ；共同空间量使用 dμ=dΩ/(4π)';workspace.purpose='固定前端表示几何；不代表预测精度';
  workspace.lastCompleted=Object.fromEntries(ids.map(id=>[id,{phase:slots[id].phase,request:slots[id].shownRequest,info:slots[id].result?.info??null}]));
  download(new Blob([JSON.stringify(workspace,null,2)],{type:'application/json'}),filename('json'));toast('JSON 已导出：含当前配置与上次完成结果身份。');
}
function svgImage(markup) {
  return new Promise((resolve,reject)=>{
    const blob=new Blob([markup],{type:'image/svg+xml;charset=utf-8'}),url=URL.createObjectURL(blob),image=new Image();
    image.onload=()=>{URL.revokeObjectURL(url);resolve(image);};image.onerror=()=>{URL.revokeObjectURL(url);reject(new Error('SVG 图表转换失败。'));};image.src=url;
  });
}
function withMapVisible(callback) {
  return callback();
}
function wrapText(ctx,text,x,y,maxWidth,lineHeight) {
  let line='';for(const ch of text){if(ch==='\n'){ctx.fillText(line,x,y);y+=lineHeight;line='';continue;}if(ctx.measureText(line+ch).width>maxWidth){ctx.fillText(line,x,y);y+=lineHeight;line='';}line+=ch;}if(line)ctx.fillText(line,x,y);return y+lineHeight;
}
async function exportPNG() {
  if($('#png-theme').value==='paper')return exportPaperPNG();
  if(ids.some(id=>!slots[id].result||!slots[id].globe)){globalError('需要两个地球均有成功返回的真实数值结果，才能导出比较 PNG。');return;}
  const button=$('#export-png');button.disabled=true;
  try {
    // Snapshot canvases and SVG strings synchronously, before images load or new requests finish.
    const snapshots=withMapVisible(()=>ids.map(id=>{
      slots[id].globe.resize();
      const source=slots[id].globe.snapshot(),canvas=document.createElement('canvas');canvas.width=source.width;canvas.height=source.height;canvas.getContext('2d').drawImage(source,0,0);
      return {id,canvas,info:structuredClone(slots[id].result.info),spectrumSummary:spectrumSummary(slots[id].result),request:structuredClone(slots[id].shownRequest),domain:[...slots[id].domain],phase:slots[id].phase,legend:$(`#legend-${id} .legend-label`).textContent};
    }));
    const key=fieldKey(),signed=['kernel','similarity','raw_similarity','channel'].includes(key),measure=$('#legend-a .legend-label').textContent,profileField=state.view.profile;
    const spectrum=$('#spectrum-chart svg')?.outerHTML,profile=$('#profile-chart svg')?.outerHTML;
    const meta=snapshots.map(s=>`${s.id.toUpperCase()} ${configurationName(s.request.config)} · ${s.phase==='fresh'?'当前配置':'上次完成结果'}\n${s.spectrumSummary}\n${JSON.stringify(s.request)}`);
    const width=1600,height=1360+meta.reduce((sum,t)=>sum+Math.ceil(t.length/160)*20,0),canvas=document.createElement('canvas');canvas.width=width;canvas.height=height;
    const ctx=canvas.getContext('2d');ctx.fillStyle='#0a1421';ctx.fillRect(0,0,width,height);
    ctx.font='28px system-ui,sans-serif';ctx.fillStyle='#e2eeed';ctx.fillText('表示的地理 · 地理位置编码器工作台',40,52);
    ctx.fillStyle='#9ec7bc';ctx.font='15px system-ui,sans-serif';wrapText(ctx,measure,40,85,1520,23);
    for(const [index,snapshot] of snapshots.entries()) {
      const x=40+index*780;ctx.fillStyle=index===0?'#71dec4':'#8aaff5';ctx.font='19px system-ui,sans-serif';ctx.fillText(`${snapshot.id.toUpperCase()} · ${configurationName(snapshot.request.config)}`,x,139);
      ctx.fillStyle='#94aabc';ctx.font='14px system-ui,sans-serif';ctx.fillText(`${bandlimitLabel(snapshot.info)} · ${snapshot.info.feature_count} 特征 · r ${snapshot.info.rank} · ${snapshot.phase==='fresh'?'当前配置':'旧图 / 待更新'}`,x,166);
      const scale=Math.min(740/snapshot.canvas.width,470/snapshot.canvas.height),w=snapshot.canvas.width*scale,h=snapshot.canvas.height*scale;
      ctx.drawImage(snapshot.canvas,x+(740-w)/2,177+(470-h)/2,w,h);
      ctx.font='14px system-ui,sans-serif';ctx.fillStyle='#a8bfcd';ctx.fillText(`锚点 ${coordinate(snapshot.request.anchor)}`,x,675);
      if(key==='coordinate') {
        ctx.fillStyle='#b6d0c6';ctx.font='12px system-ui,sans-serif';
        for(const [row,marker] of boundaryMarkers(snapshot.info.boundary_diagnostics).entries()) {
          const status={consistent:'一致',different:'有差异',tiny:'极小幅值，谨慎',unknown:'未计算'}[marker.status];
          ctx.fillText(`${marker.label}：${status} · 相对差 ${format(marker.value,4)}`,x,696+row*18);
        }
      } else {
        for(let i=0;i<740;i++){ctx.fillStyle=`rgb(${colorAt(snapshot.domain[0]+i/739*(snapshot.domain[1]-snapshot.domain[0]),snapshot.domain,signed).join(',')})`;ctx.fillRect(x+i,692,1,8);}
        ctx.fillStyle='#b6d0c6';ctx.fillText(snapshot.legend,x+125,723);
        ctx.fillStyle='#a5b8c5';ctx.fillText(format(snapshot.domain[0]),x,723);ctx.fillText(format(snapshot.domain[1]),x+680,723);
      }
      const config=snapshot.request.config,hasCap=state.view.showRegion&&regionInfo(config).hasCap;
      if(hasCap){ctx.fillStyle='#c9e5c9';ctx.font='11px system-ui,sans-serif';ctx.fillText(`浅色实线：名义目标球冠 ${config.radius}°`,x,738);}
      if(state.view.showCenters&&(snapshot.info.centers?.length)){ctx.fillStyle='#b6d0c6';ctx.font='11px system-ui,sans-serif';ctx.fillText('构造中心',x,hasCap?755:738);}
    }
    const [spectrumImage,profileImage]=await Promise.all([spectrum?svgImage(spectrum):null,profile?svgImage(profile):null]);
    ctx.fillStyle='#c6d8d5';ctx.font='18px system-ui,sans-serif';ctx.fillText('逐阶球谐频谱 Eℓ/r',40,770);ctx.fillText(profileField==='kernel'?'距离—共同空间核幅度（公里）':profileField==='raw_similarity'?'距离—原始 PE 相似度（公里）':'距离—共同空间相似度（公里）',590,770);
    if(spectrumImage)ctx.drawImage(spectrumImage,40,790,490,304);
    if(profileImage){const scale=Math.min(980/profileImage.width,290/profileImage.height);ctx.drawImage(profileImage,575,800,profileImage.width*scale,profileImage.height*scale);}
    let y=1138;ctx.fillStyle='#b6d0c6';ctx.font='13px system-ui,sans-serif';
    y=wrapText(ctx,'原始 PE 余弦直接比较 φ；共同空间相似度、能量与频谱使用全球面积内积 dμ=dΩ/(4π)。图示为固定前端表示几何，不是预测精度。分带平方和不含频带间交叉项，不能逐点相加还原 C。相似度可能掩盖小范数处的幅度衰减，灰暗遮罩 / 剖面断线为未定义。',40,y,1520,21);
    ctx.fillStyle='#829bac';ctx.font='12px ui-monospace,monospace';
    for(const text of meta)y=wrapText(ctx,text,40,y+14,1520,19);
    ctx.fillStyle='#658594';ctx.fillText(`导出 ${new Date().toISOString()} · 配置和图像来自上次完成请求；完整重放请同时导出 JSON。`,40,Math.max(y+20,height-25));
    const blob=await new Promise(resolve=>canvas.toBlob(resolve,'image/png'));if(!blob)throw new Error('浏览器无法编码 PNG。');
    download(blob,filename('png'));toast('PNG 已导出，附数学量定义及实际显示配置。');
  }finally{button.disabled=false;}
}

async function exportPaperPNG() {
  if(anchorDraftPending){globalError('手动输入尚未应用；请先提交位置并等待 A/B 更新后导出论文图。');return;}
  if(ids.some(id=>slots[id].phase!=='fresh'||!slots[id].shownRequest||
      JSON.stringify(slots[id].result?.config)!==JSON.stringify(state.slots[id].config))){
    globalError('论文图要求 A/B 都是当前配置和选点的已更新结果；请等待计算完成。');return;
  }
  const button=$('#export-png');button.disabled=true;
  try {
    const response=await fetch('/api/export/figure',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({
      theme:'paper',layer:fieldKey(),colors_locked:state.view.colorsLocked,
      show_region:state.view.showRegion,show_centers:state.view.showCenters,
      requests:ids.map(id=>slots[id].shownRequest)
    })});
    if(!response.ok){const failure=await response.json().catch(()=>({}));throw new Error(failure.error??`HTTP ${response.status}`);}
    const blob=await response.blob();
    download(blob,filename('png').replace(/\.png$/,'-paper.png'));
    toast('论文浅色 PNG 已导出：全球经纬图、A/B 数值图层及配置摘要。');
  }finally{button.disabled=false;}
}

async function boot() {
  bindControls();hydrateControls();
  for(const id of ids) {
    try {slots[id].globe=new Globe($(`#globe-${id}`),{
      onPick:point=>setAnchor(id,point),onCamera:camera=>{if(state.view.cameraLinked)slots[id==='a'?'b':'a'].globe?.setCamera(camera);},
      onError:error=>globalError(`地球渲染：${error.message}`)
    });}catch(error){globalError(`无法初始化 WebGL 地球：${error.message}。数值 API 和配置面板仍可使用。`);}
  }
  try {
    const response=await fetch('/api/catalog',{signal:AbortSignal.timeout(8000)});if(!response.ok)throw new Error(`HTTP ${response.status}`);
    catalog=await response.json();
    // Defaults are taken from the same service; explicit per-slot presets remain A/B.
    if(ids.every(id=>slots[id].phase==='waiting')){state=createState(catalog);hydrateControls();}
    const limits=catalog.limits;$('#catalog-limits').textContent=limits?`服务上限：区域 L ≤ ${limits.degree?.[1]??'见 API'}；完整球谐 L ≤ ${limits.sh_degree?.[1]??'见 API'}；区域特征 ≤ ${limits.regional_features?.[1]??'见 API'}。`:'计算上限由本地服务验证。';
    $('#health').textContent='本地服务已连接';$('#health').className='connection online';
  }catch(error){$('#health').textContent='服务目录不可用';$('#health').className='connection offline';$('#catalog-limits').textContent='采用计划默认参数；计算上限由 API 验证。';globalError(`读取 /api/catalog 失败：${error.message}。请确认从 Python 服务 URL 打开页面。`);}
  await Promise.all(ids.map(submit));
}
boot().catch(error=>globalError(`工作台初始化失败：${error.message}`));
