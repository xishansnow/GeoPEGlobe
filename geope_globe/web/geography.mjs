export function decodeLand(topology, feature) {
  if(!topology?.objects?.land)throw new Error('地图数据缺少 land 对象。');
  const decoded=feature(topology,topology.objects.land),coordinates=[];
  function collect(value) {
    if(!value)throw new Error('地图转换未返回有效几何。');
    if(value.type==='FeatureCollection')value.features.forEach(collect);
    else if(value.type==='Feature')collect(value.geometry);
    else if(value.type==='GeometryCollection')value.geometries.forEach(collect);
    else if(value.type==='MultiPolygon')coordinates.push(...value.coordinates);
    else if(value.type==='Polygon')coordinates.push(value.coordinates);
    else throw new Error(`地图几何类型不支持：${value.type}`);
  }
  collect(decoded);
  if(!coordinates.length)throw new Error('地图未包含可绘制的大陆多边形。');
  return {type:'MultiPolygon',coordinates};
}
