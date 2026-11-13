import * as THREE from 'three';
import { OrbitControls } from './vendor/three/addons/controls/OrbitControls.js';
import { lonLatToVector, vectorToLonLat, colorAt, capCircle, profilePath, profileArrow } from './core.mjs';
import { decodeLand } from './geography.mjs';
import { boundaryMarkers } from './boundary-view.mjs';
import { neighborhoodVertices } from './neighborhood-view.mjs';
import { regionInfo, centerColor } from './region-view.mjs';

const WIDTH=2048,HEIGHT=1024;
const canvasOf=(width,height)=>Object.assign(document.createElement('canvas'),{width,height});
let atlasPromise;

function landGeometry() {
  atlasPromise ??= fetch('./vendor/world-atlas/land-110m.json').then(async response=>{
    if(!response.ok) throw new Error(`大陆纹理加载失败（HTTP ${response.status}）。`);
    if(!globalThis.topojson?.feature) throw new Error('本地 TopoJSON 依赖未加载。');
    const topology=await response.json();
    return decodeLand(topology,globalThis.topojson.feature);
  });
  return atlasPromise;
}

// Unwrap each ring before painting shifted copies. This avoids long false coastlines
// across the antimeridian; pole-enclosing rings close along the appropriate map edge.
function traceLand(ctx,geometry,fill) {
  const polygons=geometry.type==='Polygon'?[geometry.coordinates]:geometry.coordinates;
  for(const polygon of polygons) {
    const rings=polygon.map(ring=>{
      let previous; const points=[];
      for(const [lon,lat] of ring) {
        let x=(lon+180)/360*WIDTH;
        if(previous!==undefined) { while(x-previous>WIDTH/2)x-=WIDTH; while(x-previous<-WIDTH/2)x+=WIDTH; }
        points.push([x,(90-lat)/180*HEIGHT]); previous=x;
      }
      if(fill && points.length && Math.abs(points.at(-1)[0]-points[0][0])>WIDTH/2) {
        const edge=ring.reduce((s,p)=>s+p[1],0)<0?HEIGHT:0;
        points.push([points.at(-1)[0],edge],[points[0][0],edge]);
      }
      return points;
    });
    for(const offset of [-WIDTH,0,WIDTH]) {
      ctx.beginPath();
      for(const points of rings) {
        if(!points.length) continue;
        ctx.moveTo(points[0][0]+offset,points[0][1]);
        for(const [x,y] of points.slice(1)) ctx.lineTo(x+offset,y);
        if(fill) ctx.closePath();
      }
      if(fill)ctx.fill('evenodd');else ctx.stroke();
    }
  }
}

function geographicCanvas(geometry,coastOnly=false) {
  const canvas=canvasOf(WIDTH,HEIGHT),ctx=canvas.getContext('2d');
  if(!coastOnly) {
    ctx.fillStyle='#122237';ctx.fillRect(0,0,WIDTH,HEIGHT);
    ctx.fillStyle='#203950';traceLand(ctx,geometry,true);
  }
  ctx.strokeStyle=coastOnly?'rgba(199,226,223,.52)':'#587b8e';ctx.lineWidth=1.1;
  traceLand(ctx,geometry,false);
  ctx.strokeStyle='rgba(131,170,189,.20)';ctx.lineWidth=.7;ctx.beginPath();
  for(let lon=-180;lon<=180;lon+=30) { const x=(lon+180)/360*WIDTH;ctx.moveTo(x,0);ctx.lineTo(x,HEIGHT); }
  for(let lat=-60;lat<=60;lat+=30) { const y=(90-lat)/180*HEIGHT;ctx.moveTo(0,y);ctx.lineTo(WIDTH,y); }
  ctx.stroke(); return canvas;
}

export class Globe {
  constructor(container,{onPick,onCamera,onError}) {
    this.container=container;this.onPick=onPick;this.onCamera=onCamera;this.onError=onError;
    this.scene=new THREE.Scene();
    this.camera=new THREE.PerspectiveCamera(35,1,.01,100);this.camera.up.set(0,1,0);
    this.camera.position.fromArray(lonLatToVector(110,35,3.65));
    this.renderer=new THREE.WebGLRenderer({alpha:true,antialias:true,preserveDrawingBuffer:true});
    this.renderer.setPixelRatio(Math.min(devicePixelRatio||1,2));
    this.renderer.setClearColor(0,0);this.renderer.outputColorSpace=THREE.SRGBColorSpace;
    this.renderer.domElement.tabIndex=0;
    this.renderer.domElement.setAttribute('aria-label','交互地球：拖动旋转，滚轮或双指缩放，点击选点。可通过侧栏经纬度定位。');
    this.renderer.domElement.setAttribute('role','img');
    container.prepend(this.renderer.domElement);
    this.controls=new OrbitControls(this.camera,this.renderer.domElement);
    this.controls.enableDamping=true;this.controls.dampingFactor=.09;this.controls.enablePan=false;
    this.controls.minDistance=1.45;this.controls.maxDistance=7;this.controls.rotateSpeed=.55;this.controls.zoomSpeed=.7;
    this.textureCanvas=canvasOf(WIDTH,HEIGHT);this.texture=new THREE.CanvasTexture(this.textureCanvas);
    this.texture.colorSpace=THREE.SRGBColorSpace;this.texture.anisotropy=Math.min(8,this.renderer.capabilities.getMaxAnisotropy());
    this.texture.wrapS=THREE.RepeatWrapping;
    this.mesh=new THREE.Mesh(new THREE.SphereGeometry(1,144,96),new THREE.MeshBasicMaterial({map:this.texture}));
    this.scene.add(this.mesh);
    const halo=new THREE.Mesh(new THREE.SphereGeometry(1.035,64,48),new THREE.ShaderMaterial({
      vertexShader:'varying vec3 vNormal; varying vec3 vPosition; void main(){ vec4 p=modelViewMatrix*vec4(position,1.0); vNormal=normalize(normalMatrix*normal); vPosition=p.xyz; gl_Position=projectionMatrix*p; }',
      fragmentShader:'varying vec3 vNormal; varying vec3 vPosition; void main(){float rim=pow(1.0-abs(dot(normalize(vNormal),normalize(-vPosition))),3.0);gl_FragColor=vec4(0.22,0.58,0.64,rim*0.22);}',
      transparent:true,depthWrite:false,side:THREE.BackSide,blending:THREE.AdditiveBlending
    }));
    this.scene.add(halo);this.markers=new THREE.Group();this.scene.add(this.markers);
    this.anchorGroup=new THREE.Group();this.scene.add(this.anchorGroup);
    this.centerGroup=new THREE.Group();this.scene.add(this.centerGroup);this.centerGroup.visible=false;
    this.boundaryGroup=new THREE.Group();this.scene.add(this.boundaryGroup);this.boundaryGroup.visible=false;
    this.neighborhoodGroup=new THREE.Group();this.scene.add(this.neighborhoodGroup);this.neighborhoodGroup.visible=false;
    this.pointer=new THREE.Vector2();this.raycaster=new THREE.Raycaster();
    let down;
    this.renderer.domElement.addEventListener('pointerdown',event=>{down={x:event.clientX,y:event.clientY,time:performance.now(),id:event.pointerId};});
    this.renderer.domElement.addEventListener('pointerup',event=>{
      if(down && down.id===event.pointerId && Math.hypot(event.clientX-down.x,event.clientY-down.y)<5 && performance.now()-down.time<700) {
        const hit=this.pick(event);if(hit)this.onPick(hit);
      } down=null;
    });
    this.renderer.domElement.addEventListener('pointercancel',()=>{down=null;});
    this.renderer.domElement.addEventListener('webglcontextlost',event=>{event.preventDefault();onError(new Error('WebGL 上下文丢失，请重新加载页面。'));});
    this.controls.addEventListener('change',()=>{if(!this.applyingCamera)this.onCamera(this.cameraState());});
    this.observer=new ResizeObserver(()=>this.resize());this.observer.observe(container);
    this.resize();this.drawBase();
    this.renderer.setAnimationLoop(()=>{this.controls.update();this.renderer.render(this.scene,this.camera);});
    landGeometry().then(geometry=>{
      this.base=geographicCanvas(geometry);this.coast=geographicCanvas(geometry,true);
      if(this.lastField)this.setField(...this.lastField);else this.drawBase();
    }).catch(onError);
  }
  resize() {
    const width=Math.max(1,this.container.clientWidth),height=Math.max(1,this.container.clientHeight);
    this.camera.aspect=width/height;this.camera.updateProjectionMatrix();this.renderer.setSize(width,height,false);
  }
  drawBase() {
    const ctx=this.textureCanvas.getContext('2d');ctx.fillStyle='#14283b';ctx.fillRect(0,0,WIDTH,HEIGHT);
    if(this.base)ctx.drawImage(this.base,0,0);this.texture.needsUpdate=true;
  }
  setField(values,grid,domain,signed) {
    this.lastField=[values,grid,domain,signed];this.drawBase();
    const layer=canvasOf(grid.nlon,grid.nlat),ctx=layer.getContext('2d'),image=ctx.createImageData(grid.nlon,grid.nlat);
    for(let i=0;i<values.length;i++) {
      const color=colorAt(values[i],domain,signed);
      image.data.set(color?[...color,233]:[73,83,96,165],i*4);
    }
    ctx.putImageData(image,0,0);
    const target=this.textureCanvas.getContext('2d');target.imageSmoothingEnabled=false;target.drawImage(layer,0,0,WIDTH,HEIGHT);
    if(this.coast)target.drawImage(this.coast,0,0);this.texture.needsUpdate=true;
  }
  clearField() { this.lastField=null;this.drawBase(); }
  clearGroup(group) {
    while(group.children.length) {
      const object=group.children[0];group.remove(object);object.geometry?.dispose();
      if(Array.isArray(object.material))object.material.forEach(m=>m.dispose());else object.material?.dispose();
    }
  }
  line(points,color,group,dashed=false) {
    const geometry=new THREE.BufferGeometry().setFromPoints(points.map(p=>new THREE.Vector3(...p)));
    const material=dashed?new THREE.LineDashedMaterial({color,dashSize:.025,gapSize:.016,transparent:true,opacity:.65}):new THREE.LineBasicMaterial({color,transparent:true,opacity:.85});
    const line=new THREE.Line(geometry,material);if(dashed)line.computeLineDistances();group.add(line);
  }
  dot(lon,lat,color,radius,group) {
    const dot=new THREE.Mesh(new THREE.SphereGeometry(radius,12,8),new THREE.MeshBasicMaterial({color}));
    dot.position.fromArray(lonLatToVector(lon,lat,1.02));group.add(dot);
  }
  setModel(config,info) {
    this.clearGroup(this.markers);this.clearGroup(this.centerGroup);
    if(regionInfo(config).hasCap) {
      this.line(capCircle(config.center,config.radius),0xc0e6bd,this.markers);
      this.dot(...config.center,0xd4efb7,.012,this.markers);
    }
    for(const center of info.centers ?? [])this.dot(center.lon,center.lat,centerColor(center),.011,this.centerGroup);
    this.setBoundaryChecks(info.boundary_diagnostics);
  }
  setBoundaryChecks(checks) {
    this.clearGroup(this.boundaryGroup);
    const colors={consistent:0x71dec4,different:0xefce92,tiny:0x9b9faa,unknown:0x687b8c};
    for(const marker of boundaryMarkers(checks))this.dot(marker.lon,marker.lat,colors[marker.status],.028,this.boundaryGroup);
  }
  showBoundaryChecks(visible) {
    this.boundaryGroup.visible=visible;
    if(visible)this.markers.visible=false;
  }
  showRegion(visible) {this.markers.visible=visible;}
  setNeighborhood(local) {
    this.clearGroup(this.neighborhoodGroup);
    const vertices=neighborhoodVertices(local);
    if(!vertices.length)return;
    const positions=[],colors=[];
    for(const vertex of vertices) {
      positions.push(...vertex.position);
      const [r,g,b]=vertex.color;
      const color=new THREE.Color().setRGB(r/255,g/255,b/255,THREE.SRGBColorSpace);
      colors.push(color.r,color.g,color.b);
    }
    const geometry=new THREE.BufferGeometry();
    geometry.setAttribute('position',new THREE.Float32BufferAttribute(positions,3));
    geometry.setAttribute('color',new THREE.Float32BufferAttribute(colors,3));
    const material=new THREE.PointsMaterial({size:6,sizeAttenuation:false,vertexColors:true,depthTest:true,depthWrite:false});
    this.neighborhoodGroup.add(new THREE.Points(geometry,material));
  }
  showNeighborhood(visible) {this.neighborhoodGroup.visible=visible;}
  setAnchor(anchor,angles) {
    this.clearGroup(this.anchorGroup);this.dot(anchor.lon,anchor.lat,0xffffff,.018,this.anchorGroup);
    const ring=new THREE.Mesh(new THREE.RingGeometry(.026,.032,32),new THREE.MeshBasicMaterial({color:0x9dffe2,side:THREE.DoubleSide,depthTest:true}));
    ring.position.fromArray(lonLatToVector(anchor.lon,anchor.lat,1.024));ring.quaternion.setFromUnitVectors(new THREE.Vector3(0,0,1),ring.position.clone().normalize());this.anchorGroup.add(ring);
    if(angles?.length) {
      this.line(profilePath(anchor,angles),0xb3e4dc,this.anchorGroup,true);
      const arrow=profileArrow(anchor,angles);if(arrow.length)this.line(arrow,0xe7fff5,this.anchorGroup);
    }
  }
  showCenters(visible) { this.centerGroup.visible=visible; }
  pick(event) {
    const rect=this.renderer.domElement.getBoundingClientRect();
    this.pointer.set((event.clientX-rect.left)/rect.width*2-1,-(event.clientY-rect.top)/rect.height*2+1);
    this.raycaster.setFromCamera(this.pointer,this.camera);
    const hit=this.raycaster.intersectObject(this.mesh)[0];return hit?vectorToLonLat(hit.point.toArray()):null;
  }
  cameraState() { return {position:this.camera.position.toArray(),up:this.camera.up.toArray(),target:this.controls.target.toArray()}; }
  setCamera(state) {
    this.applyingCamera=true;
    // Reset OrbitControls' accumulated damping before applying an external view.
    this.controls.enableDamping=false;this.controls.update();
    this.camera.position.fromArray(state.position);this.camera.up.fromArray(state.up);this.controls.target.fromArray(state.target);
    this.controls.update();this.controls.enableDamping=true;this.applyingCamera=false;
  }
  locate(anchor) {
    this.setCamera({position:lonLatToVector(anchor.lon,anchor.lat,this.camera.position.length()),up:[0,1,0],target:[0,0,0]});
    this.onCamera(this.cameraState());
  }
  snapshot() { this.renderer.render(this.scene,this.camera);return this.renderer.domElement; }
}
