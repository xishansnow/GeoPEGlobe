"""Fixed Sphere coordinate formulas with analytic area Gram and separate SH analysis.

Independent implementation; no upstream code is distributed. Channel order was
checked against TorchSpatial's PositionEncoders in the source pinned below.
Source identity and adaptations: ../../docs/torchspatial_sources.json. SphereM+ and DFS
retain the source's max_radius-only frequency rule; SphereC and SphereM use
geometric radii including min_radius.
"""
import numpy as np

from .encoders import RawEncoder, finite, integer
from .spherecplus import _inner, _project, _trig

__all__ = ['build_spherical']

_COMMIT = 'ac7dbcf5694dc99cce136b17fa0c26964d7ee0de'
_SOURCE_URL = (f'https://raw.githubusercontent.com/seai-lab/TorchSpatial/{_COMMIT}'
               '/main/SpatialRelationEncoder.py')
_SOURCE_SHA256 = '7a25ee624d9c3d4cb8ee2dbae9e3be70feb644147ad36a9e0e73980bfb7c11dd'
_METHODS = {
    'spherec': ('SphereC', 'SphereSpatialRelationPositionEncoder'),
    'spherem': ('SphereM', 'SphereMixScaleSpatialRelationPositionEncoder'),
    'spheremplus': ('SphereM+', 'SphereGridMixScaleSpatialRelationPositionEncoder'),
    'spheredfs': ('DFS', 'DFTSpatialRelationPositionEncoder'),
}


def _channel_factors(method, frequencies):
    """Each channel is trig(latitude) * trig(longitude); kind 1=sin, 0=cos."""
    rows, channels = [], []
    name = _METHODS[method][0]

    def append(lat_kind, lat_frequency, lon_kind, lon_frequency, label, **details):
        rows.append((lat_kind, lat_frequency, lon_kind, lon_frequency))
        channels.append(dict(name=f'{name} · {label}', kind=method,
                             angular_frequency=float(max(lat_frequency, lon_frequency)),
                             **details))

    if method == 'spheredfs':
        # [sin of all S, cos of all S] on each axis, longitude-major outer product.
        basis = [(kind, float(f), s) for kind in (1, 0)
                 for s, f in enumerate(frequencies)]
        for lon_kind, lon_frequency, lon_scale in basis:
            for lat_kind, lat_frequency, lat_scale in basis:
                lon_label = 'sin' if lon_kind else 'cos'
                lat_label = 'sin' if lat_kind else 'cos'
                append(lat_kind, lat_frequency, lon_kind, lon_frequency,
                       f'{lon_label} λ{lon_scale} {lat_label} φ{lat_scale}',
                       longitude_scale=lon_scale, latitude_scale=lat_scale)

    for s, f in enumerate(frequencies):
        if method == 'spherec':
            terms = [(1, f, 0, 0, 'sin φs'),
                     (0, f, 0, f, 'cos φs cos λs'),
                     (0, f, 1, f, 'cos φs sin λs')]
        else:
            mixed = [(0, f, 0, 1, 'cos φs cos λ'),
                     (0, 1, 0, f, 'cos φ cos λs'),
                     (0, f, 1, 1, 'cos φs sin λ'),
                     (0, 1, 1, f, 'cos φ sin λs')]
            singles = [(1, f, 0, 0, 'sin φs'), (0, f, 0, 0, 'cos φs'),
                       (0, 0, 1, f, 'sin λs'), (0, 0, 0, f, 'cos λs')]
            if method == 'spherem':
                terms = singles[:1] + mixed
            elif method == 'spheremplus':
                terms = singles + mixed
            else:
                terms = singles
        for lat_kind, lat_frequency, lon_kind, lon_frequency, label in terms:
            append(lat_kind, lat_frequency, lon_kind, lon_frequency,
                   f's={s} · {label}', scale=s)

    lat_kind, lat_frequency, lon_kind, lon_frequency = np.asarray(rows).T
    return (lat_kind.astype(int), lat_frequency, lon_kind.astype(int), lon_frequency), channels


def build_spherical(supplied) -> RawEncoder:
    """Build spherec, spherem, spheremplus or spheredfs; input is lon/lat degrees.

    The evaluator and Gram use the full coordinate functions under dΩ/(4π).
    ``degree`` only controls the real SH projection in ``coefficients``; the
    projection never replaces the direct function or defines its actual bandlimit.
    ``spectral_quadrature_error`` is the node-refinement difference divided by
    total raw feature L2 norm, sqrt(trace(Gram)); it is not an error bound.
    """
    if not isinstance(supplied, dict):
        raise ValueError('config 必须为对象')
    method = supplied.get('encoder')
    if not isinstance(method, str) or method not in _METHODS:
        raise ValueError('encoder 必须为 spherec、spherem、spheremplus 或 spheredfs')
    dfs = method == 'spheredfs'
    source_frequencies = method in {'spheremplus', 'spheredfs'}
    count = integer(supplied.get('frequencies', 4), 'frequencies', 1, 7 if dfs else 32)
    degree = integer(supplied.get('degree', 31), '频谱分析截断阶数', 0, 48)
    tolerance = finite(supplied.get('rank_tolerance', 1e-9), 'rank_tolerance', 1e-14, 1e-3)
    integer(supplied.get('global_degree', -1), 'global_degree', -1, -1)
    config = dict(encoder=method, degree=degree, frequencies=count, global_degree=-1,
                  rank_tolerance=tolerance, center=[110, 35], radius=30)
    if source_frequencies:
        maximum = finite(supplied.get('max_radius', 32), 'max_radius', 1, 10000)
        # Deliberately do not read or export min_radius: the pinned source ignores it.
        frequencies = (np.ones(1) if count == 1 else
                       maximum ** (-np.arange(count, dtype=float) / (count - 1)))
        frequency_rule = 'max_radius**(-s/(S-1)); S=1: frequency=1'
    else:
        minimum = finite(supplied.get('min_radius', .05), 'min_radius', .001, 10)
        maximum = finite(supplied.get('max_radius', 1.), 'max_radius', minimum, 10)
        frequencies = 1 / np.geomspace(minimum, maximum, count)
        config['min_radius'] = minimum
        frequency_rule = '1/geomspace(min_radius,max_radius,S); S=1: 1/min_radius'
    config['max_radius'] = maximum
    smooth_degree_one = bool(method in {'spherec', 'spherem'} and np.all(frequencies == 1))
    factors, channels = _channel_factors(method, frequencies)
    lat_kind, lat_frequency, lon_kind, lon_frequency = factors

    def coordinate_evaluator(coords):
        coords = np.asarray(coords, dtype=float)
        if coords.ndim != 2 or coords.shape[1] != 2 or not np.isfinite(coords).all():
            raise ValueError('输入必须为有限的 [经度, 纬度] 数组')
        if np.any(np.abs(coords[:, 0]) > 180) or np.any(np.abs(coords[:, 1]) > 90):
            raise ValueError('经纬度超出范围')
        lon, lat = np.deg2rad(coords).T
        return _trig(lat, lat_kind, lat_frequency) * _trig(lon, lon_kind, lon_frequency)

    gram = (_inner(lat_kind, lat_frequency, lat_kind, lat_frequency, True)
            * _inner(lon_kind, lon_frequency, lon_kind, lon_frequency))
    # Include unscaled base factors (frequency 1) for mixed-scale encoders.
    maximum_frequency = float(max(lat_frequency.max(), lon_frequency.max()))
    nodes = max(96, int(np.ceil(2 * maximum_frequency)) + degree + 24)
    coarse = _project(degree, factors, nodes)
    coefficients = _project(degree, factors, nodes + 32)
    # A projection may vanish by exact Fourier orthogonality. Normalize by
    # original feature energy so roundoff in a zero projection is not amplified.
    error = float(np.linalg.norm(coefficients - coarse) / np.sqrt(np.trace(gram)))
    name, source_class = _METHODS[method]
    warnings = ([] if smooth_degree_one else [
        f'{name} 保留坐标原式；非有限带限，频谱只显示分析截断内部分，未覆盖尾部另列',
        '经纬度坐标图原式可能在极点存在经度依赖；非整数角频率还可能产生日界线跳变，'
        '不能当作处处光滑的球面函数'])
    if smooth_degree_one:
        warnings.append('此配置的所有频率为 1，特征张成空间等价于单位球 xyz；重复通道可改变原始 PE 余弦，函数仍处处光滑且实际带限为 1')
    if source_frequencies:
        warnings.append(f'{name} 严格保留固定上游源码的 max_radius^(-s/(S-1)) 频率，忽略 min_radius；'
                        '不同于 SphereC／SphereM 的几何半径规则；S=1 明确延拓为频率 1')
    if count == 1 and not source_frequencies:
        warnings.append('S=1 明确延拓为频率 1/min_radius，不计算上游含 S-1 分母的多尺度公式')
    if error > 1e-8:
        warnings.append('球谐投影积分未充分收敛，请谨慎解释频带图')
    metadata = dict(bandlimited=smooth_degree_one, exact_max_degree=1 if smooth_degree_one else None,
                    spectral_max_degree=degree,
                    gram_source='analytic_coordinate_integrals',
                    spectral_quadrature_error=error, spectral_latitude_nodes=nodes + 32,
                    spectral_quadrature_error_normalization='sqrt(trace(gram))',
                    max_angular_frequency=maximum_frequency, chart_boundary_effects=not smooth_degree_one,
                    frequencies=frequencies.tolist(), frequency_rule=frequency_rule,
                    upstream_url=_SOURCE_URL, upstream_commit=_COMMIT,
                    upstream_sha256=_SOURCE_SHA256, upstream_symbol=source_class,
                    upstream_frequency_rule=('max_radius**(-s/(S-1))'
                                             if source_frequencies
                                             else '1/geomspace(min_radius,max_radius,S)'),
                    source_scope='Independent fixed frontend formulas; no trained model reproduction')
    return RawEncoder(coefficients, channels, config, warnings=warnings,
                      coordinate_evaluator=coordinate_evaluator, gram=gram,
                      analysis_metadata=metadata)
