import { lonLatToVector, colorAt } from './core.mjs';

// Keep the API's actual geodesic samples. The selected point is drawn by the
// globe's white anchor ring, so it is omitted from the colored point cloud.
export function neighborhoodVertices(local) {
  if(!local?.points)return [];
  return local.points.flatMap((sample,index)=>{
    if(index===local.center_index||sample.similarity===null)return [];
    return [{position:lonLatToVector(sample.lon,sample.lat,1.03),
      color:colorAt(sample.similarity,[-1,1],true),value:sample.similarity}];
  });
}
