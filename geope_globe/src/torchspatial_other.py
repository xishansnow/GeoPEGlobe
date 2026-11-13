"""TorchSpatial fixed coordinate formulas, area Grams and separate SH analysis.

Independent mathematical adapters for upstream ac7dbcf5694dc99cce136b17fa0c26964d7ee0de
(SpatialRelationEncoder.py and data_utils.coord_normalize). No upstream code is imported
or vendored. Coordinates are longitude/latitude in degrees; the inner product is
dOmega/(4*pi). SH uses encoders.real_sh's real4pi convention without CS phase.
The analysis cutoff never changes the original coordinate function or its Gram.
"""
import numpy as np
from scipy.special import roots_legendre, spherical_jn

from .encoders import RawEncoder, finite, integer, lonlat_xyz, real_sh


__all__ = ['build_other']

def fibonacci_cap(count, center, radius, scale):
    """Deterministic synthetic RBF center layout inside a spherical cap."""
    helper = np.array([0., 0., 1.]) if abs(center[2]) < .9 else np.array([1., 0., 0.])
    east = np.cross(helper, center); east /= np.linalg.norm(east)
    north = np.cross(center, east)
    z = 1-(np.arange(count)+.5)/count*(1-np.cos(np.deg2rad(radius)))
    phase = (np.arange(count)+scale*.37)*np.pi*(3-np.sqrt(5))
    return z[:, None]*center + np.sqrt(1-z*z)[:, None]*(np.cos(phase)[:, None]*east+np.sin(phase)[:, None]*north)


_COMMIT = 'ac7dbcf5694dc99cce136b17fa0c26964d7ee0de'
_SOURCE_URL = f'https://raw.githubusercontent.com/seai-lab/TorchSpatial/{_COMMIT}/main/SpatialRelationEncoder.py'
_SOURCE_SHA256 = '7a25ee624d9c3d4cb8ee2dbae9e3be70feb644147ad36a9e0e73980bfb7c11dd'
_SOURCE_CLASSES = dict(wrap='AodhaFFTSpatialRelationPositionEncoder', grid='GridCellSpatialRelationPositionEncoder',
    theory='TheoryGridCellSpatialRelationPositionEncoder', nerf='NERFSpatialRelationPositionEncoder',
    rff='RFFSpatialRelationPositionEncoder', rbf='RBFSpatialRelationPositionEncoder')
_METHODS = {'wrap', 'grid', 'theory', 'nerf', 'rff', 'rbf'}


def _coordinates(coords):
    values = np.asarray(coords, dtype=float)
    if values.ndim != 2 or values.shape[1] != 2 or not np.isfinite(values).all():
        raise ValueError('输入必须为有限的 [经度, 纬度] 数组')
    if np.any(np.abs(values[:, 0]) > 180) or np.any(np.abs(values[:, 1]) > 90):
        raise ValueError('经纬度超出范围')
    return values


def _relative_difference(fine, coarse):
    return float(np.linalg.norm(fine-coarse)/max(np.linalg.norm(fine), 1e-14))


def _spectral_difference(fine, coarse, gram):
    # Orthogonal projection may vanish; its norm is an unstable denominator.
    # Normalize instead by the original raw feature L2 norm.
    return float(np.linalg.norm(fine-coarse)/np.sqrt(np.trace(gram)))


def _latitude_rule(nodes, degree):
    t, w = roots_legendre(nodes)
    phi = t*np.pi/2
    # Integrating in latitude rather than z avoids endpoint square-root behavior
    # in associated Legendre functions for longitude-dependent chart formulas.
    weights = w*np.pi/4*np.cos(phi)
    xyz = np.column_stack((np.cos(phi), np.zeros(nodes), np.sin(phi)))
    return phi, weights, real_sh(xyz, degree)


def _plane_mean(vectors):
    """E exp(i*(a*lambda+b*phi)); np.sinc(t)=sin(pi*t)/(pi*t)."""
    a, b = np.moveaxis(vectors, -1, 0)
    return np.sinc(a)*np.pi/4*(np.sinc((b+1)/2)+np.sinc((b-1)/2))


def _plane_gram(angular_vectors, complex_amplitudes):
    # Every real channel is Re(q*exp(i*k.chart)); sine has q=-i exactly.
    low = _plane_mean(angular_vectors[:, None]-angular_vectors[None, :])
    high = _plane_mean(angular_vectors[:, None]+angular_vectors[None, :])
    q = complex_amplitudes
    return .5*((q[:, None]*q.conj()[None, :]).real*low+(q[:, None]*q[None, :]).real*high)


def _plane_project(degree, angular_vectors, complex_amplitudes, nodes):
    phi, weights, harmonics = _latitude_rule(nodes, degree)
    a, b = angular_vectors.T
    latitude = weights[:, None]*np.exp(1j*phi[:, None]*b)
    result = np.empty(((degree+1)**2, len(a)))
    for m in range(degree+1):
        ell = np.arange(m, degree+1)
        positive = ell*ell+ell+m
        lat_integral = harmonics[:, positive].T@latitude
        plus, minus = np.sinc(a+m), np.sinc(a-m)
        result[positive] = (lat_integral*(.5*(plus+minus)*complex_amplitudes)).real
        if m:
            result[ell*ell+ell-m] = (lat_integral*(.5j*(minus-plus)*complex_amplitudes)).real
    return result


def _build_plane(config):
    method, degree = config['encoder'], config['degree']
    vectors, sine, phases, channels = [], [], [], []
    metadata = {}
    amplitude = 1.

    def add(vector, is_sine, name, phase=0., **detail):
        vectors.append(vector)
        sine.append(is_sine)
        phases.append(phase)
        channels.append(dict(name=name, kind=method, **detail))

    if method == 'wrap':
        for is_sine, label in [(True, 'sin'), (False, 'cos')]:
            add([np.pi/180, 0.], is_sine, f'wrap · {label}(π lon/180)')
            add([0., np.pi/90], is_sine, f'wrap · {label}(π lat/90)')
        metadata['coordinate_extent'] = [-180, 180, -90, 90]
    elif method in {'grid', 'theory'}:
        frequencies = 1/np.geomspace(config['min_radius'], config['max_radius'], config['frequencies'])
        metadata.update(frequencies=frequencies.tolist(), frequency_units='inverse_degrees')
        if method == 'grid':
            # Upstream flattens coordinate, frequency, sin/cos in this order.
            for axis in range(2):
                for scale, f in enumerate(frequencies):
                    vector = [f, 0.] if axis == 0 else [0., f]
                    for is_sine, label in [(True, 'sin'), (False, 'cos')]:
                        add(vector, is_sine, f'grid · {label} {"lon" if axis == 0 else "lat"} s={scale}', scale=scale)
        else:
            directions = np.array([[1., 0.], [-.5, np.sqrt(3)/2], [-.5, -np.sqrt(3)/2]])
            for scale, f in enumerate(frequencies):
                for direction, vector in enumerate(directions*f):
                    for is_sine, label in [(True, 'sin'), (False, 'cos')]:
                        add(vector, is_sine, f'theory · s={scale} d={direction} {label}', scale=scale, direction=direction)
        metadata['source_adaptations'] = ('Single scale uses min_radius; the upstream geometric formula divides by S-1. '
                                          'Coordinates remain degrees, without spherical distance substitution.')
    else:
        count = config['feature_count']
        rng = np.random.RandomState(config['seed'])
        directions = rng.multivariate_normal(np.zeros(2), np.eye(2)*config['kernel_size'], count).T
        shifts = rng.uniform(0, 2*np.pi, count)
        amplitude = np.sqrt(2/count)
        for j in range(count):
            add(directions[:, j]/[180, 90], False, f'RFF · {j+1}', phase=shifts[j])
        metadata.update(coordinate_extent=[-180, 180, -90, 90],
            random_parameters=dict(directions=directions.tolist(), phases=shifts.tolist(),
                amplitude=float(amplitude), seed=config['seed'], kernel_size_is='covariance',
                generator='numpy.random.RandomState', direction_shape='2 x K'),
            source_adaptations='Local RandomState replaces the upstream global RNG; float64 mathematical formulas replace upstream float32 tensors.')

    vectors, sine, phases = np.asarray(vectors), np.asarray(sine), np.asarray(phases)
    # Keep evaluator arithmetic in the upstream input units. Radians enter only
    # the independent area integral and SH analysis, through the converted k.
    angular_vectors = vectors*(180/np.pi)
    complex_amplitudes = amplitude*np.exp(1j*phases)*np.where(sine, -1j, 1.)

    def coordinate_evaluator(coords):
        angles = _coordinates(coords)@vectors.T+phases
        return amplitude*np.where(sine, np.sin(angles), np.cos(angles))

    gram = _plane_gram(angular_vectors, complex_amplitudes)
    nodes = max(96, int(np.ceil(2*np.max(np.abs(angular_vectors[:, 1]))))+degree+24)
    coarse = _plane_project(degree, angular_vectors, complex_amplitudes, nodes)
    coefficients = _plane_project(degree, angular_vectors, complex_amplitudes, nodes+32)
    metadata.update(gram_source='analytic_coordinate_plane_wave_integrals',
        spectral_projection_method='analytic_longitude_and_gauss_legendre_latitude',
        spectral_quadrature_error=_spectral_difference(coefficients, coarse, gram),
        spectral_latitude_nodes=nodes+32, spectral_coarse_latitude_nodes=nodes,
        max_angular_frequency=float(np.max(np.linalg.norm(angular_vectors, axis=1))))
    return coefficients, gram, channels, [], coordinate_evaluator, metadata


def _build_nerf(config):
    degree, count = config['degree'], config['frequencies']
    frequencies = np.pi*np.exp2(np.arange(count))
    # xyz axis first, scale second, with all sine channels before all cosines.
    vectors = (np.eye(3)[:, None, :]*frequencies[None, :, None]).reshape(-1, 3)
    lengths = np.linalg.norm(vectors, axis=1)
    low = np.sinc(np.linalg.norm(vectors[:, None]-vectors[None, :], axis=2)/np.pi)
    high = np.sinc(np.linalg.norm(vectors[:, None]+vectors[None, :], axis=2)/np.pi)
    zero = np.zeros_like(low)
    gram = np.block([[.5*(low-high), zero], [zero, .5*(low+high)]])
    ell = np.repeat(np.arange(degree+1), 2*np.arange(degree+1)+1)
    harmonics = real_sh(vectors/lengths[:, None], degree).T
    # E[e^(ik.x) Y_lm(x)] = i^l j_l(|k|) Y_lm(khat), in the real4pi basis.
    # Exact cycle avoids spurious even/odd leakage from complex exponentials.
    phase = np.array([1., 1j, -1., -1j])[ell % 4]
    complex_coefficients = phase[:, None]*spherical_jn(ell[:, None], lengths)*harmonics
    coefficients = np.column_stack((complex_coefficients.imag, complex_coefficients.real))

    def coordinate_evaluator(coords):
        xyz = lonlat_xyz(_coordinates(coords))
        angles = xyz@vectors.T
        return np.column_stack((np.sin(angles), np.cos(angles)))

    channels = [dict(name=f'NeRF · {label} {axis} s={s}', kind='nerf', scale=s, axis=axis,
                     angular_frequency=float(f))
                for label in ['sin', 'cos'] for axis in ['x', 'y', 'z'] for s, f in enumerate(frequencies)]
    metadata = dict(gram_source='analytic_spherical_sinc',
        spectral_projection_method='analytic_spherical_bessel_real4pi',
        spectral_quadrature_applicable=False,
        spectral_quadrature_error=0., max_angular_frequency=float(frequencies.max()),
        frequencies=frequencies.tolist())
    return coefficients, gram, channels, [], coordinate_evaluator, metadata


def _synthetic_centers(config):
    count = config['feature_count']
    phase = np.random.RandomState(config['seed']).uniform(0, 2*np.pi)
    golden = np.pi*(3-np.sqrt(5))
    if config['center_layout'] == 'global':
        z = 1-2*(np.arange(count)+.5)/count
        azimuth = np.arange(count)*golden+phase
        xyz = np.column_stack((np.sqrt(1-z*z)*np.cos(azimuth), np.sqrt(1-z*z)*np.sin(azimuth), z))
    else:
        axis = lonlat_xyz(np.array([config['center']]))[0]
        xyz = fibonacci_cap(count, axis, config['radius'], phase/(.37*golden))
    return np.rad2deg(np.column_stack((np.arctan2(xyz[:, 1], xyz[:, 0]), np.arcsin(np.clip(xyz[:, 2], -1, 1)))))


def _rbf_integrals(centers, sigma, degree, nlon, nlat):
    u, wl = roots_legendre(nlon)
    longitude = u*np.pi
    phi, wt, harmonics = _latitude_rule(nlat, degree)
    lon_factor = np.exp(-.5*((u[:, None]*180-centers[:, 0])/sigma)**2)
    lat_factor = np.exp(-.5*((np.rad2deg(phi)[:, None]-centers[:, 1])/sigma)**2)
    gram_lon = lon_factor.T@((wl/2)[:, None]*lon_factor)
    gram_lat = lat_factor.T@(wt[:, None]*lat_factor)
    gram = gram_lon*gram_lat
    coefficients = np.empty(((degree+1)**2, len(centers)))
    weighted_lat = wt[:, None]*lat_factor
    weighted_lon = (wl/2)[:, None]*lon_factor
    for m in range(degree+1):
        ell = np.arange(m, degree+1)
        positive = ell*ell+ell+m
        lat_integral = harmonics[:, positive].T@weighted_lat
        coefficients[positive] = lat_integral*(np.cos(m*longitude)@weighted_lon)
        if m:
            coefficients[ell*ell+ell-m] = lat_integral*(np.sin(m*longitude)@weighted_lon)
    return coefficients, gram


def _build_rbf(config):
    degree, sigma = config['degree'], config['kernel_size']
    centers = _synthetic_centers(config)
    # These rules depend ONLY on Gaussian width, never on SH analysis cutoff.
    # In particular, changing degree must leave Gram and its whitening bitwise
    # identical. Both factors use full chart domains without seam wrapping.
    nlon = max(128, int(np.ceil(720/sigma))+48)
    nlat = max(96, int(np.ceil(360/sigma))+48)
    coarse, coarse_gram = _rbf_integrals(centers, sigma, degree, nlon, nlat)
    coefficients, gram = _rbf_integrals(centers, sigma, degree, nlon+64, nlat+64)

    def coordinate_evaluator(coords):
        delta = _coordinates(coords)[:, None, :]-centers
        return np.exp(-np.sum(delta*delta, axis=2)/(2*sigma*sigma))

    channels = [dict(name=f'RBF · {j+1}', kind='rbf', lon=float(lon), lat=float(lat))
                for j, (lon, lat) in enumerate(centers)]
    center_records = [dict(lon=float(lon), lat=float(lat)) for lon, lat in centers]
    metadata = dict(gram_source='separable_gaussian_gauss_legendre',
        gram_quadrature_error=_relative_difference(gram, coarse_gram),
        gram_refinement_absolute_difference=float(np.linalg.norm(gram-coarse_gram)),
        gram_longitude_nodes=nlon+64, gram_latitude_nodes=nlat+64,
        gram_coarse_longitude_nodes=nlon, gram_coarse_latitude_nodes=nlat,
        spectral_projection_method='separable_gaussian_gauss_legendre_real4pi',
        spectral_quadrature_error=_spectral_difference(coefficients, coarse, gram),
        spectral_longitude_nodes=nlon+64, spectral_latitude_nodes=nlat+64,
        max_angular_frequency=float(180/(np.pi*sigma)),
        angular_frequency_interpretation='Gaussian inverse width, a characteristic scale, not a strict bandlimit',
        random_parameters=dict(centers=centers.tolist(), seed=config['seed'], layout=config['center_layout'],
                               layout_method='seeded_azimuth_fibonacci_equal_area'),
        source_adaptations=('Synthetic Fibonacci centers replace upstream global train_locs sampling; '
            'cap is a synthetic cap layout, not the upstream relative mode. This is not author center reproduction. '
            'The original longitude/latitude Euclidean Gaussian is retained without longitude wrapping or geodesic distance.'))
    return coefficients, gram, channels, center_records, coordinate_evaluator, metadata


def build_other(supplied) -> RawEncoder:
    """Build wrap/grid/theory/NeRF/RFF/RBF RawEncoder with separate SH analysis."""
    if (not isinstance(supplied, dict) or not isinstance(supplied.get('encoder'), str)
            or supplied['encoder'] not in _METHODS):
        raise ValueError('config 必须为对象，encoder 必须为 wrap、grid、theory、nerf、rff 或 rbf')
    method = supplied['encoder']
    degree = integer(supplied.get('degree', 31), 'degree', 0, 48)
    integer(supplied.get('global_degree', -1), 'global_degree', -1, -1)
    tolerance = finite(supplied.get('rank_tolerance', 1e-9), 'rank_tolerance', 1e-14, 1e-3)
    config = dict(encoder=method, degree=degree, global_degree=-1, rank_tolerance=tolerance)
    if method in {'grid', 'theory', 'nerf'}:
        config['frequencies'] = integer(supplied.get('frequencies', 4), 'frequencies', 1, 10 if method == 'nerf' else 32)
    if method in {'grid', 'theory'}:
        config['min_radius'] = finite(supplied.get('min_radius', 5), 'min_radius', .1, 360)
        config['max_radius'] = finite(supplied.get('max_radius', 180), 'max_radius', config['min_radius'], 360)
    if method in {'rff', 'rbf'}:
        config['feature_count'] = integer(supplied.get('feature_count', 32), 'feature_count', 1, 128 if method == 'rff' else 64)
        config['kernel_size'] = finite(supplied.get('kernel_size', 10 if method == 'rff' else 20),
            'kernel_size', .01 if method == 'rff' else 2, 1000 if method == 'rff' else 90)
        config['seed'] = integer(supplied.get('seed', 0), 'seed', 0, 2**32-1)
    if method == 'rbf':
        layout = supplied.get('center_layout', 'global')
        if not isinstance(layout, str) or layout not in {'global', 'cap'}:
            raise ValueError('center_layout 必须为 global 或 cap')
        config['center_layout'] = layout
        center = supplied.get('center', [110, 35])
        if not isinstance(center, (list, tuple)) or len(center) != 2:
            raise ValueError('center 必须为 [经度, 纬度]')
        config['center'] = [finite(center[0], '中心经度', -180, 180), finite(center[1], '中心纬度', -90, 90)]
        config['radius'] = finite(supplied.get('radius', 30), 'radius', .1, 180)
    else:
        config.update(center=[110, 35], radius=30)
    builder = _build_rbf if method == 'rbf' else _build_nerf if method == 'nerf' else _build_plane
    coefficients, gram, channels, centers, evaluator, metadata = builder(config)
    metadata.update(bandlimited=False, spectral_max_degree=degree,
        chart_boundary_effects=method != 'nerf', torchspatial_source_commit=_COMMIT,
        upstream_url=_SOURCE_URL, upstream_commit=_COMMIT, upstream_sha256=_SOURCE_SHA256,
        upstream_symbol=_SOURCE_CLASSES[method],
        source_scope='Independent fixed frontend mathematics; no trained model reproduction',
        spectral_quadrature_error_normalization='sqrt(trace(gram))',
        quadrature_error_interpretation='Frobenius coarse/fine differences with declared normalization; not rigorous error bounds or spectral tail estimates')
    if method == 'rbf':
        metadata['gram_quadrature_error_normalization'] = 'frobenius_norm(gram)'
    warnings = ['保留原式地理位置编码；非有限带限，球谐仅分析截止内频谱，未覆盖尾部另列']
    if method != 'nerf':
        warnings.append('经纬度坐标图原式可能在极点存在经度依赖或在日界线不连续，不能视为处处光滑的球面函数')
    if method == 'rbf':
        warnings.append('RBF 使用可重放合成 Fibonacci 中心替代上游 train_locs 采样，不是作者中心选择复现；Gaussian 距离仍为经纬度平面欧氏距离')
    if metadata['spectral_quadrature_error'] > 1e-8:
        warnings.append('球谐投影节点复核差异较大，不能将积分误差解释为频谱尾部')
    if metadata.get('gram_quadrature_error', 0) > 1e-8:
        warnings.append('RBF 原式 Gram 节点复核差异较大，白化结果需谨慎解释')
    return RawEncoder(coefficients, channels, config, centers, warnings,
                      coordinate_evaluator=evaluator, gram=gram, analysis_metadata=metadata)
