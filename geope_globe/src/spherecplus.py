"""SphereC+ coordinate formula, analytic area Gram and separate SH analysis.

Independent formula implementation. Source identity: ../../docs/torchspatial_sources.json.
The coordinate function is not replaced by its finite harmonic projection.
"""
import numpy as np
from scipy.special import roots_legendre
from .encoders import RawEncoder, finite, integer, real_sh


def _factors(frequencies):
    # cos(0*t) is 1; each channel is one latitude factor times one longitude factor.
    lat_kind = np.tile([1, 0, 0, 0, 0, 0], len(frequencies))
    lon_kind = np.tile([0, 0, 1, 0, 0, 1], len(frequencies))
    lat_freq = (frequencies[:, None]*[1, 1, 0, 0, 1, 1]).ravel()
    lon_freq = (frequencies[:, None]*[0, 0, 1, 1, 1, 1]).ravel()
    return lat_kind, lat_freq, lon_kind, lon_freq


def _trig(angles, kinds, frequencies):
    phase = np.asarray(angles)[:, None]*frequencies
    return np.where(kinds, np.sin(phase), np.cos(phase))


def _mean_exponential(frequency, latitude=False):
    if latitude:
        return np.pi/4*(np.sinc((frequency+1)/2)+np.sinc((frequency-1)/2))
    return np.sinc(frequency)


def _inner(kinds_a, freqs_a, kinds_b, freqs_b, latitude=False):
    a, b = np.asarray(freqs_a)[:, None], np.asarray(freqs_b)[None, :]
    low = _mean_exponential(a-b, latitude)
    high = _mean_exponential(a+b, latitude)
    same = np.asarray(kinds_a)[:, None] == np.asarray(kinds_b)[None, :]
    return np.where(same, .5*(low+np.where(np.asarray(kinds_a)[:, None], -high, high)), 0.)


def _project(degree, factors, nodes):
    lat_kind, lat_freq, lon_kind, lon_freq = factors
    t, weights = roots_legendre(nodes)
    phi = t*np.pi/2
    weights = weights*np.pi/4*np.cos(phi)
    points = np.column_stack([np.cos(phi), np.zeros(nodes), np.sin(phi)])
    harmonics = real_sh(points, degree)
    weighted_lat = weights[:, None]*_trig(phi, lat_kind, lat_freq)
    result = np.empty(((degree+1)**2, len(lat_kind)))
    for m in range(degree+1):
        ell = np.arange(m, degree+1)
        positive = ell*ell+ell+m
        lat_integral = harmonics[:, positive].T@weighted_lat
        result[positive] = lat_integral*_inner(lon_kind, lon_freq, [0], [m]).T
        if m:
            result[ell*ell+ell-m] = lat_integral*_inner(lon_kind, lon_freq, [1], [m]).T
    return result


def build_spherecplus(supplied):
    count = integer(supplied.get('frequencies', 8), 'frequencies', 1, 32)
    minimum = finite(supplied.get('min_radius', .05), 'min_radius', .001, 10)
    maximum = finite(supplied.get('max_radius', 1.), 'max_radius', minimum, 10)
    degree = integer(supplied.get('degree', 31), '频谱分析截断阶数', 0, 48)
    tolerance = finite(supplied.get('rank_tolerance', 1e-9), 'rank_tolerance', 1e-14, 1e-3)
    if supplied.get('global_degree', -1) != -1:
        raise ValueError('SphereC+ 原式不拼接全球球谐；global_degree 必须为 -1')
    # Same endpoint/order as the repository's existing SphereCPlusFeatures adapter.
    frequencies = 1/np.geomspace(minimum, maximum, count)
    factors = _factors(frequencies)
    lat_kind, lat_freq, lon_kind, lon_freq = factors

    def coordinate_evaluator(coords):
        coords = np.asarray(coords, dtype=float)
        if coords.ndim != 2 or coords.shape[1] != 2 or not np.isfinite(coords).all():
            raise ValueError('SphereC+ 输入必须为有限经纬度数组')
        lon, lat = np.deg2rad(coords).T
        return _trig(lat, lat_kind, lat_freq)*_trig(lon, lon_kind, lon_freq)

    gram = _inner(lat_kind, lat_freq, lat_kind, lat_freq, True)*_inner(lon_kind, lon_freq, lon_kind, lon_freq)
    nodes = max(96, int(np.ceil(2*frequencies.max()))+degree+24)
    coarse = _project(degree, factors, nodes)
    coefficients = _project(degree, factors, nodes+32)
    error = float(np.linalg.norm(coefficients-coarse)/max(np.sqrt(np.trace(gram)), 1e-14))
    labels = ['sin φs', 'cos φs', 'sin λs', 'cos λs', 'cos φs cos λs', 'cos φs sin λs']
    channels = [dict(name=f'SphereC+ s={s} · {label}', kind='spherecplus', scale=s, angular_frequency=float(f))
                for s, f in enumerate(frequencies) for label in labels]
    config = dict(encoder='spherecplus', degree=degree, frequencies=count, min_radius=minimum,
                  max_radius=maximum, global_degree=-1, rank_tolerance=tolerance,
                  center=[110, 35], radius=30)
    warnings = ['SphereC+ 保留原式；非有限带限，频谱只显示分析截断内部分，未覆盖尾部另列',
                '经纬度坐标图原式在极点存在经度依赖；非整数角频率还可能产生日界线跳变，不能当作处处光滑的球面函数']
    if error > 1e-8:
        warnings.append('球谐投影积分未充分收敛，请谨慎解释频带图')
    metadata = dict(bandlimited=False, gram_source='analytic_coordinate_integrals', chart_boundary_effects=True,
                    spectral_max_degree=degree, spectral_quadrature_error=error,
                    spectral_quadrature_error_normalization='sqrt(trace(gram))',
                    spectral_latitude_nodes=nodes+32, max_angular_frequency=float(frequencies.max()),
                    frequencies=frequencies.tolist())
    return RawEncoder(coefficients, channels, config, warnings=warnings,
                      coordinate_evaluator=coordinate_evaluator, gram=gram, analysis_metadata=metadata)
