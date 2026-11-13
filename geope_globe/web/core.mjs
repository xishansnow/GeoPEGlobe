// Shared by the browser and node:test. +Y is north; east-positive longitude points toward -Z.
const DEG = Math.PI / 180;
export function wrapLongitude(lon) { return ((lon + 180) % 360 + 360) % 360 - 180; }
export function lonLatToVector(lon, lat, radius = 1) {
  const c = Math.cos(lat * DEG) * radius;
  return [c * Math.cos(lon * DEG), Math.sin(lat * DEG) * radius, -c * Math.sin(lon * DEG)];
}
export function vectorToLonLat([x,y,z]) {
  const r = Math.hypot(x,y,z);
  if (!r) throw new Error('零向量没有经纬度。');
  return {lon:wrapLongitude(Math.atan2(-z,x) / DEG),lat:Math.atan2(y,Math.hypot(x,z)) / DEG};
}
export function lonLatToUV(lon,lat) { return {u:(wrapLongitude(lon)+180)/360,v:(90-Math.max(-90,Math.min(90,lat)))/180}; }
export function gridIndex(lon,lat,nlat,nlon) {
  const {u,v}=lonLatToUV(lon,lat);
  return Math.min(nlat-1,Math.floor(v*nlat))*nlon + Math.min(nlon-1,Math.floor(u*nlon));
}

// Aborting saves work when supported. The sequence check is the correctness guard,
// including transports which ignore AbortSignal and edits before a debounced request.
export class LatestRequest {
  #sequence=0; #controller;
  invalidate() { this.#sequence++; this.#controller?.abort(); }
  async run(operation,onValue,onError=()=>{}) {
    this.invalidate(); const sequence=this.#sequence;
    this.#controller=new AbortController();
    try {
      const value=await operation(this.#controller.signal);
      if(sequence===this.#sequence) { onValue(value); return true; }
    } catch(error) {
      if(sequence===this.#sequence && error.name!=='AbortError') onError(error);
    }
    return false;
  }
}

export function colorDomain(arrays,signed=false) {
  let min=Infinity,max=-Infinity;
  for(const array of arrays) for(const v of array ?? []) if(typeof v==='number' && Number.isFinite(v)) { min=Math.min(min,v); max=Math.max(max,v); }
  if(!Number.isFinite(min)) return signed?[-1,1]:[0,1];
  if(signed) { const extent=Math.max(Math.abs(min),Math.abs(max),1e-12); return [-extent,extent]; }
  return [0,Math.max(max,1e-12)];
}
const SEQUENTIAL=[[11,25,43],[19,72,89],[24,136,142],[77,209,176],[224,246,177]];
const DIVERGING=[[81,130,225],[141,183,223],[26,39,56],[49,171,151],[224,241,169]];
export function colorAt(value,domain,signed=false) {
  if(typeof value!=='number' || !Number.isFinite(value)) return null;
  const t=Math.max(0,Math.min(1,(value-domain[0])/(domain[1]-domain[0] || 1)));
  const palette=signed?DIVERGING:SEQUENTIAL;
  const p=t*(palette.length-1), i=Math.min(palette.length-2,Math.floor(p));
  return palette[i].map((v,k)=>Math.round(v+(palette[i+1][k]-v)*(p-i)));
}

// Analytic orthonormal tangent vectors remain defined at the exact poles. There,
// longitude chooses a tangent orientation, without dividing by cos(latitude).
function sphericalFrame(lon,lat) {
  const lo=lon*DEG,la=lat*DEG;
  return {
    p:lonLatToVector(lon,lat),
    t1:[-Math.sin(la)*Math.cos(lo),Math.cos(la),Math.sin(la)*Math.sin(lo)],
    t2:[-Math.sin(lo),0,-Math.cos(lo)]
  };
}
function tangentDestination({p,t1,t2},angle,bearing,radius) {
  const a=angle*DEG,b=bearing*DEG;
  return p.map((value,i)=>radius*(Math.cos(a)*value+Math.sin(a)*(Math.cos(b)*t1[i]+Math.sin(b)*t2[i])));
}
export function greatCircle(anchor,angles,bearing=90,radius=1.012) {
  const frame=sphericalFrame(anchor.lon,anchor.lat);
  return angles.map(angle=>tangentDestination(frame,angle,bearing,radius));
}

export function capCircle(center,radius) {
  const frame=sphericalFrame(center[0],center[1]);
  return Array.from({length:181},(_,i)=>tangentDestination(frame,radius,i*2,1.014));
}

// Match geometry.tangent_frame: geographic +Z helper, +X helper near the poles.
export function profilePath(anchor,angles,radius=1.013) {
  const [x,z,minusY]=lonLatToVector(anchor.lon,anchor.lat);
  const p=[x,-minusY,z], helper=Math.abs(p[2])<.9?[0,0,1]:[1,0,0];
  const cross=[helper[1]*p[2]-helper[2]*p[1],helper[2]*p[0]-helper[0]*p[2],helper[0]*p[1]-helper[1]*p[0]];
  const length=Math.hypot(...cross),t=cross.map(v=>v/length);
  return angles.map(angle=>{
    const a=angle*DEG,q=p.map((v,i)=>radius*(Math.cos(a)*v+Math.sin(a)*t[i]));
    return [q[0],q[2],-q[1]];
  });
}

export function profileArrow(anchor,angles) {
  const positives=angles.map((a,i)=>a>0?i:-1).filter(i=>i>=0);
  if(positives.length<3)return [];
  const index=positives[Math.floor((positives.length-1)/2)],path=profilePath(anchor,angles);
  if(index<1 || index>=path.length-1)return [];
  const point=path[index],delta=path[index+1].map((v,i)=>v-path[index-1][i]),length=Math.hypot(...delta);
  if(!length)return [];
  const tangent=delta.map(v=>v/length),normal=point.map(v=>v/Math.hypot(...point));
  const side=[normal[1]*tangent[2]-normal[2]*tangent[1],normal[2]*tangent[0]-normal[0]*tangent[2],normal[0]*tangent[1]-normal[1]*tangent[0]];
  return [-1,0,1].map(sign=>point.map((v,i)=>sign===0?v+.05*tangent[i]:v-.025*tangent[i]+sign*.025*side[i]));
}
