const EARTH_RADIUS_KM = 6371.0088;

// Keep only the API's sampled positive route, including undefined endpoints.
// No mirroring, interpolation, added origin or extension of sample support.
export function distanceSeries(profile, field = 'similarity') {
  return profile.angles.flatMap((angle, index) => {
    if (!Number.isFinite(angle) || angle < 0) return [];
    const value = profile[field][index];
    return [{distanceKm:angle * Math.PI / 180 * EARTH_RADIUS_KM,
      value:typeof value === 'number' && Number.isFinite(value) ? value : null}];
  });
}
