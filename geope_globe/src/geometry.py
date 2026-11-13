"""Basis-invariant global-area geometry, with explicit truncation and masks."""
from dataclasses import dataclass
import time
import numpy as np
from .encoders import RawEncoder, integer, finite, lonlat_xyz, real_sh

SPECTRAL_COVERAGE_TOLERANCE = 1e-6


@dataclass
class Model:
    raw: RawEncoder
    basis: np.ndarray
    rank: int
    condition: float
    gram_error: float
    singular_values: np.ndarray
    retained_mask: np.ndarray
    absolute_threshold: float
    discarded_max: float
    reconstruction_error: float
    build_seconds: float = 0.0
    coordinate_transform: object = None


def analyze(raw):
    start = time.perf_counter()
    if raw.coordinate_evaluator is not None:
        gram = (raw.gram+raw.gram.T)/2
        values, vectors = np.linalg.eigh(gram)
        values, vectors = values[::-1], vectors[:, ::-1]
        # A Gram eigensystem squares the condition number. Declare the separate
        # roundoff guard instead of presenting unstable directions as capacity.
        floor = float(64*np.finfo(float).eps*len(values)*values[0])
        if values[-1] < -floor:
            raise ValueError('解析 Gram 出现超出舍入容差的负本征值')
        singular = np.sqrt(np.maximum(values, 0))
        threshold = max(singular[0]*raw.config['rank_tolerance'], np.sqrt(floor))
        keep = singular > threshold
        rank = int(keep.sum())
        if not rank:
            raise ValueError('配置未保留非零子空间')
        transform = vectors[:, keep]/singular[keep]
        raw.analysis_metadata.update(gram_roundoff_floor=floor,
            effective_rank_tolerance=float(threshold/singular[0]))
        discarded = singular[~keep]
        return Model(raw, raw.coefficients@transform, rank, float(singular[0]/singular[keep][-1]),
            float(np.max(np.abs(transform.T@gram@transform-np.eye(rank)))), singular, keep,
            threshold, float(discarded.max()) if len(discarded) else 0.,
            float(np.linalg.norm(discarded)/np.linalg.norm(singular)), time.perf_counter()-start, transform)
    u, singular, _ = np.linalg.svd(raw.coefficients, full_matrices=False)
    keep = singular > singular[0]*raw.config.get('rank_tolerance', 1e-9)
    rank = int(keep.sum())
    if rank == 0:
        raise ValueError('配置未保留非零子空间')
    basis = u[:, keep].copy()
    discarded = singular[~keep]
    return Model(raw, basis, rank, float(singular[0]/singular[keep][-1]),
                 float(np.max(np.abs(basis.T@basis-np.eye(rank)))),
                 singular.copy(), keep.copy(), float(singular[0]*raw.config.get("rank_tolerance", 1e-9)),
                 float(discarded.max()) if len(discarded) else 0.0,
                 float(np.linalg.norm(discarded)/np.linalg.norm(singular)), time.perf_counter()-start)


def numbers(values):
    values = np.asarray(values)
    return [float(x) if np.isfinite(x) else None for x in values.ravel()]


def stable_norm(vector):
    scale = float(np.max(np.abs(vector)))
    return scale*float(np.linalg.norm(vector/scale)) if scale else 0.


def raw_cosine(values, anchor):
    """Cosine of nonzero original vectors, stable across tiny amplitudes."""
    scales = np.max(np.abs(values), axis=1)
    anchor_scale = float(np.max(np.abs(anchor)))
    result = np.full(len(values), np.nan)
    if not anchor_scale:
        return result
    valid = scales > 0
    a = anchor/anchor_scale
    v = values[valid]/scales[valid, None]
    result[valid] = np.clip((v@a)/(np.linalg.norm(v, axis=1)*np.linalg.norm(a)), -1, 1)
    return result


def tangent_frame(point):
    helper = np.array([0., 0., 1.]) if abs(point[2]) < .9 else np.array([1., 0., 0.])
    first = np.cross(helper, point); first /= np.linalg.norm(first)
    return first, np.cross(point, first)


def evaluate(model, grid, anchor, band, channel):
    start = time.perf_counter()
    if not all(isinstance(x, dict) for x in [grid, anchor, band]):
        raise ValueError('grid、anchor 与 band 必须为对象')
    nlat = integer(grid.get('nlat', 32), 'nlat', 16, 96)
    nlon = integer(grid.get('nlon', 2*nlat), 'nlon', 32, 192)
    if nlon != 2*nlat:
        raise ValueError('nlon 必须等于 2*nlat')
    lon = finite(anchor.get('lon', 110), '锚点经度', -180, 180)
    lat = finite(anchor.get('lat', 35), '锚点纬度', -90, 90)
    bmin = integer(band.get('min', 8), '频带下界', 0, 48)
    bmax = integer(band.get('max', 16), '频带上界', bmin, 48)
    channel = integer(channel, '原始通道', 0, model.raw.coefficients.shape[1]-1)
    degree = int(np.sqrt(model.basis.shape[0]))-1
    harmonic_degrees = np.repeat(np.arange(degree+1), 2*np.arange(degree+1)+1)
    spectrum = np.bincount(harmonic_degrees, weights=np.sum(model.basis**2, axis=1), minlength=degree+1)
    band_mask = (harmonic_degrees >= bmin)&(harmonic_degrees <= bmax)
    band_basis = model.basis[band_mask]
    coordinate = model.raw.coordinate_evaluator
    exact_degree = model.raw.analysis_metadata.get('exact_max_degree')
    bandlimited = not bool(coordinate) or bool(model.raw.analysis_metadata.get('bandlimited', False))
    band_complete = not coordinate or bmax <= degree or (exact_degree is not None and degree >= exact_degree)
    band_energy = float(np.sum(band_basis**2)) if band_complete else None
    anchor_xyz = lonlat_xyz(np.array([[lon, lat]]))[0]
    anchor_sh = real_sh(anchor_xyz[None, :], degree)[0]
    anchor_raw = coordinate([[lon, lat]])[0] if coordinate else anchor_sh@model.raw.coefficients
    anchor_raw_norm = stable_norm(anchor_raw)
    # These coordinate pairs denote identical points on the sphere. Any raw
    # discrepancy is a coordinate-representation effect of this configuration.
    equivalent_coords = np.array([[0., 90.], [90., 90.], [0., -90.], [90., -90.],
                                  [180., 0.], [-180., 0.]])
    if coordinate:
        equivalent_raw = coordinate(equivalent_coords)
    else:
        equivalent_xyz = lonlat_xyz(equivalent_coords)
        # Coordinates of each pair are mathematically the same sphere point;
        # canonicalize them before finite-harmonic evaluation so cos(pi/2)
        # roundoff is not classified as an encoder discontinuity.
        equivalent_xyz[[1, 3, 5]] = equivalent_xyz[[0, 2, 4]]
        equivalent_raw = real_sh(equivalent_xyz, degree)@model.raw.coefficients
    def relative_gap(i, j):
        a, b = equivalent_raw[i], equivalent_raw[j]
        scale = max(float(np.max(np.abs(a))), float(np.max(np.abs(b))))
        if not scale:
            return 0., 0.
        an, bn = a/scale, b/scale
        return float(np.linalg.norm(an-bn)/max(np.linalg.norm(an), np.linalg.norm(bn))), max(stable_norm(a), stable_norm(b))
    north_gap, north_norm = relative_gap(0, 1)
    south_gap, south_norm = relative_gap(2, 3)
    seam_gap, seam_norm = relative_gap(4, 5)
    boundary_diagnostics = dict(
        north_pole_0_vs_90_relative_difference=north_gap,
        north_pole_0_vs_90_max_norm=north_norm,
        south_pole_0_vs_90_relative_difference=south_gap,
        south_pole_0_vs_90_max_norm=south_norm,
        dateline_plus_vs_minus_180_relative_difference=seam_gap,
        dateline_plus_vs_minus_180_max_norm=seam_norm)
    anchor_features = anchor_raw@model.coordinate_transform if coordinate else anchor_sh@model.basis
    anchor_energy = float(anchor_features@anchor_features)
    longitudes = -180+(np.arange(nlon)+.5)*360/nlon
    latitudes = 90-(np.arange(nlat)+.5)*180/nlat
    mesh_lon, mesh_lat = np.meshgrid(longitudes, latitudes)
    coordinates = np.column_stack([mesh_lon.ravel(), mesh_lat.ravel()])
    points = lonlat_xyz(coordinates)
    fields = {key: np.empty(len(points)) for key in ['energy', 'kernel', 'similarity', 'raw_similarity', 'channel', 'band_energy']}
    for offset in range(0, len(points), 384):
        indices = slice(offset, offset+384)
        harmonics = real_sh(points[indices], degree)
        raw_values = coordinate(coordinates[indices]) if coordinate else harmonics@model.raw.coefficients
        features = raw_values@model.coordinate_transform if coordinate else harmonics@model.basis
        energy = np.sum(features**2, axis=1)
        kernel = features@anchor_features
        valid = (energy > 1e-12*model.rank)&(anchor_energy > 1e-12*model.rank)
        similarity = np.full(len(energy), np.nan)
        similarity[valid] = np.clip(kernel[valid]/np.sqrt(energy[valid]*anchor_energy), -1, 1)
        fields['energy'][indices] = energy/model.rank
        fields['kernel'][indices] = kernel
        fields['similarity'][indices] = similarity
        fields['raw_similarity'][indices] = raw_cosine(raw_values, anchor_raw)
        fields['channel'][indices] = raw_values[:, channel]
        fields['band_energy'][indices] = np.sum((harmonics[:, band_mask]@band_basis)**2, axis=1)/band_energy if band_energy is not None and band_energy > 1e-12 else np.nan
    first, second = tangent_frame(anchor_xyz)
    # A geodesic neighborhood centered on the query point. Tangent-plane
    # coordinates are mapped with the sphere exponential map, so the patch
    # remains meaningful across the date line and at the poles.
    offsets = np.arange(-20, 21, 2, dtype=float)
    local_xy = np.array([(x, y) for y in offsets for x in offsets if np.hypot(x, y) <= 20], dtype=float)
    local_radius = np.deg2rad(np.linalg.norm(local_xy, axis=1))
    local_tangent = np.deg2rad(local_xy[:, 0, None])*first + np.deg2rad(local_xy[:, 1, None])*second
    local_xyz = (np.cos(local_radius)[:, None]*anchor_xyz +
        np.sin(local_radius)[:, None]*local_tangent/np.where(local_radius>0, local_radius, 1)[:, None])
    local_coords = np.rad2deg(np.column_stack((np.arctan2(local_xyz[:, 1], local_xyz[:, 0]),
        np.arctan2(local_xyz[:, 2], np.hypot(local_xyz[:, 0], local_xyz[:, 1])))))
    local_center = int(np.flatnonzero(np.all(local_xy == 0, axis=1))[0])
    local_coords[local_center] = [lon, lat]
    local_raw = coordinate(local_coords) if coordinate else real_sh(local_xyz, degree)@model.raw.coefficients
    local_raw[local_center] = anchor_raw
    local_similarity = numbers(raw_cosine(local_raw, anchor_raw))
    neighborhood = dict(definition='tangent_exponential_map', radius_degrees=20, step_degrees=2,
        center_index=local_center, points=[dict(lon=float(place[0]), lat=float(place[1]),
            distance_degrees=float(np.linalg.norm(delta)), similarity=value)
            for place, delta, value in zip(local_coords, local_xy, local_similarity)])
    max_frequency = model.raw.analysis_metadata.get('max_angular_frequency', 1)
    chart_boundary_effects = bool(coordinate and model.raw.analysis_metadata.get('chart_boundary_effects', True))
    chart_scale = max(abs(np.cos(np.deg2rad(lat))), 1e-8) if chart_boundary_effects else 1.
    step = min(1e-4, 1e-3*chart_scale/max(max_frequency, 1e-12)) if coordinate else 1e-4

    def features_at_xyz(x):
        if not coordinate:
            return real_sh(x, degree)@model.basis
        coords = np.rad2deg(np.column_stack([np.arctan2(x[:, 1], x[:, 0]), np.arctan2(x[:, 2], np.hypot(x[:, 0], x[:, 1]))]))
        return coordinate(coords)@model.coordinate_transform

    def jacobian(epsilon):
        result = []
        for direction in [first, second]:
            x = np.stack([np.cos(epsilon)*anchor_xyz+np.sin(epsilon)*direction,
                          np.cos(epsilon)*anchor_xyz-np.sin(epsilon)*direction])
            features = features_at_xyz(x)
            result.append((features[0]-features[1])/(2*epsilon))
        return np.stack(result, axis=1)

    boundary = bool(chart_boundary_effects and (abs(lat) >= 90-np.rad2deg(step) or
                    180-abs(lon) <= np.rad2deg(step/max(abs(np.cos(np.deg2rad(lat))), 1e-12)) or step < 1e-10))
    if boundary:
        metric, convergence, eigenvalues, sensitivity = None, None, [None, None], None
    else:
        j = jacobian(step/2)
        metric = j.T@j
        convergence = float(np.linalg.norm(j-jacobian(step))/max(np.linalg.norm(j), 1e-14))
        eigenvalues, sensitivity = np.linalg.eigvalsh(metric).tolist(), float(np.trace(metric)/model.rank)
    angles = np.linspace(-60, 60, 161)
    radians = np.deg2rad(angles)
    profile_xyz = np.cos(radians)[:, None]*anchor_xyz+np.sin(radians)[:, None]*first
    profile_features = features_at_xyz(profile_xyz)
    profile_coords = np.rad2deg(np.column_stack([np.arctan2(profile_xyz[:, 1], profile_xyz[:, 0]),
        np.arctan2(profile_xyz[:, 2], np.hypot(profile_xyz[:, 0], profile_xyz[:, 1]))]))
    profile_raw = coordinate(profile_coords) if coordinate else real_sh(profile_xyz, degree)@model.raw.coefficients
    if coordinate:
        profile_features[angles == 0] = anchor_features
        profile_raw[angles == 0] = anchor_raw
    profile_energy = np.sum(profile_features**2, axis=1)
    profile_kernel = profile_features@anchor_features
    valid = (profile_energy > 1e-12*model.rank)&(anchor_energy > 1e-12*model.rank)
    similarity = np.full(len(angles), np.nan)
    similarity[valid] = np.clip(profile_kernel[valid]/np.sqrt(profile_energy[valid]*anchor_energy), -1, 1)
    profile_raw_similarity = raw_cosine(profile_raw, anchor_raw)
    warnings = list(model.raw.warnings)
    if not band_complete:
        warnings.append('所选频带超出分析截断范围，完整频带未计算并已遮罩；不表示原式该频带能量为零')
    elif band_energy <= 1e-12:
        warnings.append('所选频带没有非零能量，频带图层已遮罩')
    if convergence is not None and convergence > 1e-4:
        warnings.append('局部敏感度差分尚未充分收敛，请谨慎解释')
    if boundary:
        warnings.append('锚点处于坐标图极点／日界线或差分精度边界，局部球面敏感度未定义')
    if coordinate:
        warnings.append(f'全球面积 Gram 白化采用舍入保护，有效相对奇异值阈值 {model.raw.analysis_metadata["effective_rank_tolerance"]:.3g}；不将舍入噪声计为方向')
    # Squared fields can double the highest spatial frequency. At Nyquist
    # equality a pixel-centered harmonic may vanish at every display node.
    spectral_support = np.flatnonzero(spectrum > 1e-12)
    actual_degree = int(spectral_support[-1]) if spectral_support.size else 0
    if coordinate and not spectral_support.size:
        warnings.append('当前球谐分析截断内没有非零投影；频谱图的零值不表示原始 PE 为零，请提高分析截断阶数')
    display_frequency = max_frequency if coordinate else actual_degree
    nyquist = min(nlon / 2, nlat)
    if 2*display_frequency >= nyquist:
        warnings.append('原始 PE 相似度／平方能量场的角频率达到或超过当前网格 Nyquist 边界，图像可能混叠；请提高显示网格')
    channel_peak = float(np.max(np.abs(fields['channel'])))
    if abs(float(anchor_raw[channel])) > 1e-8 and channel_peak < 1e-8*abs(float(anchor_raw[channel])):
        warnings.append('当前单特征在选点处非零，但显示网格全部采为近零；请提高显示网格，勿将暗色误解为特征缺失')
    if coordinate:
        if model.gram_error > 1e-5:
            warnings.append(f'该配置 Gram 白化精度降低：保留基正交性误差 {model.gram_error:.3g} 超过软件提示阈值 1e-5；请结合实际误差解释几何量')
    if model.rank < model.raw.coefficients.shape[1]:
        if coordinate:
            warnings.append(f'原式方向按请求容差／Gram 舍入阈值截断；全球面积范数相对重构残差 {model.reconstruction_error:.3g}，重复或近相关方向不重复计容量')
        elif model.discarded_max > np.finfo(float).eps*max(model.raw.coefficients.shape)*model.singular_values[0]*10:
            warnings.append(f'秩容差丢弃了非零方向；相对系数重构残差 {model.reconstruction_error:.3g}，所显示的是截断子空间')
        else:
            warnings.append('特征数超过线性秩或全球分支精确重叠；共同几何已去除重复方向')
    coverage = float(spectrum.sum()/model.rank)
    if coordinate and coverage > 1+SPECTRAL_COVERAGE_TOLERANCE:
        raise ValueError('球谐投影能量超过原式保留秩，积分／白化误差过大')
    spectral_metadata = dict(bandlimited=bandlimited, spectral_max_degree=degree,
        spectral_energy_coverage=coverage, spectral_tail_fraction=max(0., 1-coverage), gram_source='exact_harmonic_coefficients')
    spectral_metadata.update(model.raw.analysis_metadata)
    return {
        'config': model.raw.config,
        'grid': dict(nlat=nlat, nlon=nlon, longitudes=longitudes.tolist(), latitudes=latitudes.tolist()),
        'fields': {key: numbers(value) for key, value in fields.items()},
        'spectrum': dict(degrees=list(range(degree+1)), energy=spectrum.tolist(), fraction=(spectrum/model.rank).tolist()),
        'info': dict(encoder=model.raw.config['encoder'], feature_count=model.raw.coefficients.shape[1], rank=model.rank,
                     actual_max_degree=(exact_degree if exact_degree is not None else actual_degree) if bandlimited else None, normalization='共同全球面积 dμ=dΩ/(4π)；C/r，线性子空间几何，非预测精度',
                     condition_number=model.condition, rank_tolerance=model.raw.config['rank_tolerance'], gram_error=model.gram_error,
                     basis_orthogonality_error=model.gram_error, singular_values=model.singular_values.tolist(),
                     retained_singular_mask=model.retained_mask.tolist(), absolute_rank_threshold=model.absolute_threshold,
                     discarded_singular_max=model.discarded_max, relative_reconstruction_error=model.reconstruction_error,
                     band_energy=band_energy, band_complete=band_complete, build_seconds=model.build_seconds, evaluation_seconds=time.perf_counter()-start,
                     warnings=warnings, channels=model.raw.channels, centers=model.raw.centers,
                     boundary_diagnostics=boundary_diagnostics, **spectral_metadata),
        'point': dict(lon=lon, lat=lat, features=numbers(anchor_raw), raw_norm=anchor_raw_norm, energy=anchor_energy/model.rank,
                      metric=metric.tolist() if metric is not None else None, eigenvalues=eigenvalues, sensitivity=sensitivity,
                      finite_difference_step=None if boundary else step/2, finite_difference_relative_error=convergence),
        'profile': dict(angles=angles.tolist(), kernel=numbers(profile_kernel), similarity=numbers(similarity),
                        raw_similarity=numbers(profile_raw_similarity)),
        'neighborhood': neighborhood,
    }
