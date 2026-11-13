"""Independent original-formula and global-area checks; no upstream runtime needed."""
import json
import math

import numpy as np
import pytest
from scipy.integrate import quad
from scipy.special import gammaln, lpmv, roots_legendre


def build(**config):
    from geope_globe.src.torchspatial_other import build_other
    return build_other(config)


def area_rule(nlat=90, nlon=180):
    t, wt = roots_legendre(nlat)
    u, wu = roots_legendre(nlon)
    phi, lam = t*np.pi/2, u*np.pi
    x, y = np.meshgrid(lam, phi)
    coords = np.rad2deg(np.column_stack((x.ravel(), y.ravel())))
    weights = (wt[:, None]*np.pi/4*np.cos(phi[:, None])*wu[None, :]/2).ravel()
    return coords, weights


def independent_sh(coords, degree):
    """SciPy associated Legendre functions, removing their Condon–Shortley phase."""
    lon, lat = np.deg2rad(coords).T
    result = np.empty((len(coords), (degree+1)**2))
    for ell in range(degree+1):
        for m in range(ell+1):
            norm = np.sqrt((2*ell+1)*np.exp(gammaln(ell-m+1)-gammaln(ell+m+1)))
            p = (-1)**m*norm*lpmv(m, ell, np.sin(lat))
            result[:, ell*ell+ell+m] = p if m == 0 else np.sqrt(2)*p*np.cos(m*lon)
            if m:
                result[:, ell*ell+ell-m] = np.sqrt(2)*p*np.sin(m*lon)
    return result


def reference(coords, method, scales=3, minimum=5, maximum=180, count=7, kernel=10, seed=19):
    """Deliberately construct channels individually, independent of adapter internals."""
    coords = np.asarray(coords)
    if method == 'wrap':
        a = np.pi*coords/[180, 90]
        return np.column_stack((np.sin(a[:, 0]), np.sin(a[:, 1]), np.cos(a[:, 0]), np.cos(a[:, 1])))
    if method in {'grid', 'theory'}:
        f = 1/np.geomspace(minimum, maximum, scales)
        channels = []
        if method == 'grid':
            angles = [coords[:, axis]*frequency for axis in range(2) for frequency in f]
        else:
            angles = [frequency*(coords[:, 0]*dx+coords[:, 1]*dy) for frequency in f
                      for dx, dy in [(1, 0), (-.5, np.sqrt(3)/2), (-.5, -np.sqrt(3)/2)]]
        for angle in angles:
            channels.extend((np.sin(angle), np.cos(angle)))
        return np.column_stack(channels)
    if method == 'nerf':
        lon, lat = np.deg2rad(coords).T
        xyz = [np.cos(lat)*np.cos(lon), np.cos(lat)*np.sin(lon), np.sin(lat)]
        return np.column_stack([op(axis*np.pi*2**s) for op in (np.sin, np.cos)
                                for axis in xyz for s in range(scales)])
    rng = np.random.RandomState(seed)
    directions = rng.multivariate_normal(np.zeros(2), np.eye(2)*kernel, count).T
    phases = rng.uniform(0, 2*np.pi, count)
    return np.sqrt(2/count)*np.cos((coords/[180, 90])@directions+phases)


@pytest.mark.parametrize('method,dimension', [('wrap', 4), ('grid', 12), ('theory', 18), ('nerf', 18), ('rff', 7)])
def test_upstream_channel_order_amplitude_and_units(method, dimension):
    raw = build(encoder=method, degree=4, frequencies=3, feature_count=7, seed=19)
    coords = np.array([[0., 0.], [13.7, -28.3], [-179., 61.], [180., 90.]])
    saved = coords.copy()
    expected = reference(coords, method)
    np.testing.assert_allclose(raw.coordinate_evaluator(coords), expected, atol=2e-14)
    np.testing.assert_array_equal(coords, saved)
    assert raw.coefficients.shape == (25, dimension)
    assert len(raw.channels) == dimension


@pytest.mark.parametrize('method', ['wrap', 'grid', 'theory', 'nerf', 'rff', 'rbf'])
def test_gram_and_real4pi_projection_match_independent_tensor_area_rule(method):
    raw = build(encoder=method, degree=6, frequencies=3, feature_count=7, seed=19)
    coords, weights = area_rule()
    if method == 'rbf':
        centers = np.array(raw.analysis_metadata['random_parameters']['centers'])
        expected = np.exp(-np.sum((coords[:, None, :]-centers)**2, axis=2)/(2*20**2))
    else:
        expected = reference(coords, method)
    np.testing.assert_allclose(raw.coordinate_evaluator(coords), expected, atol=3e-14)
    np.testing.assert_allclose(raw.gram, expected.T@(weights[:, None]*expected), atol=3e-13)
    np.testing.assert_allclose(raw.coefficients, independent_sh(coords, 6).T@(weights[:, None]*expected), atol=3e-12)
    assert raw.analysis_metadata['spectral_quadrature_error'] < 1e-9


@pytest.mark.parametrize('method', ['wrap', 'grid', 'theory', 'nerf', 'rff', 'rbf'])
def test_spectral_cutoff_cannot_change_coordinate_function_or_gram(method):
    low = build(encoder=method, degree=0, frequencies=2, feature_count=6, kernel_size=2)
    high = build(encoder=method, degree=12, frequencies=2, feature_count=6, kernel_size=2)
    coords = np.array([[17., 40.], [-180., -90.], [180., 90.]])
    np.testing.assert_array_equal(low.coordinate_evaluator(coords), high.coordinate_evaluator(coords))
    np.testing.assert_array_equal(low.gram, high.gram)
    np.testing.assert_allclose(low.coefficients, high.coefficients[:1], atol=3e-13)
    # This protects the actual whitening geometry, not just the raw formula.
    from geope_globe.src.geometry import analyze
    a, b = analyze(low), analyze(high)
    qa = low.coordinate_evaluator(coords)@a.coordinate_transform
    qb = high.coordinate_evaluator(coords)@b.coordinate_transform
    np.testing.assert_array_equal(qa@qa.T, qb@qb.T)


def test_wrap_global_area_moments_are_hand_checked():
    raw = build(encoder='wrap', degree=1)
    # E cos(2 phi)=1/3; E sin^2(2 phi)=8/15; E cos^2(2 phi)=7/15.
    np.testing.assert_allclose(np.diag(raw.gram), [.5, 8/15, .5, 7/15], atol=2e-15)
    np.testing.assert_allclose(raw.coefficients[0], [0, 0, 0, 1/3], atol=2e-14)


def test_zero_projection_does_not_amplify_roundoff_in_quadrature_diagnostic():
    # At angular frequency 3, all four degree-zero moments vanish exactly.
    radius = 180/(3*np.pi)
    raw = build(encoder='grid', degree=0, frequencies=1, min_radius=radius, max_radius=radius)
    np.testing.assert_allclose(raw.coefficients, 0, atol=3e-14)
    assert raw.analysis_metadata['spectral_quadrature_error'] < 1e-12
    assert raw.analysis_metadata['spectral_quadrature_error_normalization'] == 'sqrt(trace(gram))'


@pytest.mark.parametrize('method', ['grid', 'theory'])
def test_one_scale_uses_minimum_and_repeated_scales_do_not_invent_rank(method):
    a = build(encoder=method, degree=0, frequencies=1, min_radius=7, max_radius=360)
    b = build(encoder=method, degree=0, frequencies=1, min_radius=7, max_radius=7)
    coords = np.array([[4., -9.], [90., 20.]])
    np.testing.assert_array_equal(a.coordinate_evaluator(coords), b.coordinate_evaluator(coords))
    expected = reference(coords, method, scales=1, minimum=7, maximum=7)
    np.testing.assert_allclose(a.coordinate_evaluator(coords), expected, atol=2e-14)
    repeated = build(encoder=method, degree=3, frequencies=4, min_radius=7, max_radius=7)
    from geope_globe.src.geometry import analyze
    assert analyze(repeated).rank == (4 if method == 'grid' else 6)


@pytest.mark.parametrize('method', ['grid', 'theory'])
def test_highest_planar_frequency_projection_is_checked_against_adaptive_integrals(method):
    raw = build(encoder=method, degree=0, frequencies=1, min_radius=.1)
    # Independent adaptive integration of the degree-zero channel moments.
    expected = []
    directions = [(1, 0), (0, 1)] if method == 'grid' else [(1, 0), (-.5, np.sqrt(3)/2), (-.5, -np.sqrt(3)/2)]
    for dx, dy in directions:
        a, b = 10*dx*180/np.pi, 10*dy*180/np.pi
        lon = quad(lambda t: np.cos(a*t), -np.pi, np.pi, epsabs=1e-12, limit=2048)[0]/(2*np.pi)
        lat = quad(lambda t: np.cos(b*t)*np.cos(t)/2, -np.pi/2, np.pi/2, epsabs=1e-12, limit=2048)[0]
        expected.extend((0., lon*lat))
    np.testing.assert_allclose(raw.coefficients[0], expected, atol=3e-12)
    assert raw.analysis_metadata['spectral_quadrature_error'] < 1e-8


def test_nerf_analytic_parity_and_spherical_sinc_cross_axis_gram():
    raw = build(encoder='nerf', frequencies=1, degree=7)
    # sin(pi*x) is purely odd; cos(pi*x) is purely even in spherical harmonics.
    for ell in range(8):
        block = raw.coefficients[ell*ell:(ell+1)**2]
        np.testing.assert_array_equal(block[:, :3] if ell % 2 == 0 else block[:, 3:], 0)
    np.testing.assert_allclose(raw.gram[:3, :3], np.eye(3)/2, atol=1e-15)
    assert raw.gram[3, 4] == pytest.approx(np.sin(np.pi*np.sqrt(2))/(np.pi*np.sqrt(2)))
    assert raw.coefficients[3, 0] == pytest.approx(np.sqrt(3)/np.pi)
    assert raw.coefficients[2, 2] == pytest.approx(np.sqrt(3)/np.pi)
    assert raw.analysis_metadata['spectral_quadrature_error'] == 0
    assert 'analytic' in raw.analysis_metadata['spectral_projection_method']


def test_highest_nerf_frequency_needs_no_quadrature_and_stays_smooth_at_poles_and_seam():
    raw = build(encoder='nerf', frequencies=10, degree=48)
    assert raw.coefficients.shape == (2401, 60)
    assert np.isfinite(raw.coefficients).all() and np.isfinite(raw.gram).all()
    coords = [[-180, 90], [23, 90], [180, 90], [-180, 21], [180, 21]]
    values = raw.coordinate_evaluator(coords)
    np.testing.assert_allclose(values[:3], np.tile(values[1], (3, 1)), atol=3e-13)
    np.testing.assert_allclose(values[3], values[4], atol=5e-13)
    assert raw.analysis_metadata['chart_boundary_effects'] is False


def test_rff_covariance_draws_amplitude_and_recorded_parameters_are_exact_and_local():
    state = np.random.get_state()
    raw = build(encoder='rff', degree=8, feature_count=11, seed=2**32-1, kernel_size=37)
    current = np.random.get_state()
    for before, after in zip(state, current):
        np.testing.assert_array_equal(before, after)
    params = raw.analysis_metadata['random_parameters']
    rng = np.random.RandomState(2**32-1)
    directions = rng.multivariate_normal(np.zeros(2), np.eye(2)*37, 11).T
    phases = rng.uniform(0, 2*np.pi, 11)
    np.testing.assert_array_equal(params['directions'], directions)
    np.testing.assert_array_equal(params['phases'], phases)
    coords = np.array([[130., -30.], [-180., 90.]])
    replay = np.sqrt(2/11)*np.cos((coords/[180, 90])@np.array(params['directions'])+params['phases'])
    np.testing.assert_allclose(raw.coordinate_evaluator(coords), replay, atol=3e-15)
    # Metadata must be directly exportable, and seeds must change the actual realization.
    json.dumps(raw.analysis_metadata, allow_nan=False)
    other = build(encoder='rff', degree=0, feature_count=11, seed=0, kernel_size=37)
    assert not np.allclose(raw.coordinate_evaluator(coords), other.coordinate_evaluator(coords))


@pytest.mark.parametrize('layout', ['global', 'cap'])
def test_rbf_recorded_synthetic_centers_replay_plane_gaussian_without_wrapping(layout):
    kwargs = dict(encoder='rbf', degree=4, center_layout=layout, center=[179, 35], radius=12,
                  feature_count=9, kernel_size=13, seed=42)
    raw, again = build(**kwargs), build(**kwargs)
    params = raw.analysis_metadata['random_parameters']
    centers = np.array(params['centers'])
    np.testing.assert_array_equal(centers, again.analysis_metadata['random_parameters']['centers'])
    np.testing.assert_allclose(centers, [[p['lon'], p['lat']] for p in raw.centers], atol=0)
    coords = np.vstack((centers, [[-179, 35], [179, 35]]))
    expected = np.exp(-np.sum((coords[:, None]-centers[None, :])**2, axis=2)/(2*13**2))
    np.testing.assert_allclose(raw.coordinate_evaluator(coords), expected, atol=2e-15)
    np.testing.assert_array_equal(np.diag(raw.coordinate_evaluator(centers)), 1.)
    if layout == 'cap':
        # The cap straddles the seam: inspect anchors on the +179 side only.
        positive_side = centers[:, 0] > 150
        assert positive_side.any()
        assert np.max(raw.coordinate_evaluator([[-179, 35]])[:, positive_side]) < .01
    if layout == 'cap':
        lon, lat = np.deg2rad(centers).T
        axis_lon, axis_lat = np.deg2rad([179, 35])
        dot = np.cos(lat)*np.cos(axis_lat)*np.cos(lon-axis_lon)+np.sin(lat)*np.sin(axis_lat)
        assert np.min(dot) > np.cos(np.deg2rad(12))
    assert 'synthetic' in raw.analysis_metadata['source_adaptations'].lower()
    assert 'train_locs' in raw.analysis_metadata['source_adaptations']
    assert raw.analysis_metadata['gram_quadrature_error'] < 1e-9
    assert raw.analysis_metadata['gram_refinement_absolute_difference'] >= 0
    json.dumps(raw.analysis_metadata, allow_nan=False)


def test_narrow_rbf_gram_and_projection_are_not_confused_with_missing_spectral_tail():
    raw = build(encoder='rbf', degree=4, feature_count=5, kernel_size=2, center_layout='cap', radius=40)
    coords, weights = area_rule(nlat=260, nlon=520)
    centers = np.array(raw.analysis_metadata['random_parameters']['centers'])
    values = np.exp(-np.sum((coords[:, None]-centers)**2, axis=2)/8)
    np.testing.assert_allclose(raw.gram, values.T@(weights[:, None]*values), atol=2e-12)
    np.testing.assert_allclose(raw.coefficients, independent_sh(coords, 4).T@(weights[:, None]*values), atol=2e-12)
    assert raw.analysis_metadata['gram_quadrature_error'] < 1e-9
    assert raw.analysis_metadata['spectral_quadrature_error'] < 1e-9
    coverage = np.sum(raw.coefficients**2)/np.trace(raw.gram)
    assert coverage < .1  # Accurate integral, large legitimate unresolved tail.


@pytest.mark.parametrize('method,dimension', [('wrap', 4), ('grid', 16), ('theory', 24), ('nerf', 24), ('rff', 32), ('rbf', 32)])
def test_defaults_and_nonbandlimited_metadata(method, dimension):
    raw = build(encoder=method)
    assert raw.coefficients.shape == (1024, dimension)
    assert raw.config['degree'] == 31 and raw.config['global_degree'] == -1
    assert raw.config['rank_tolerance'] == 1e-9
    meta = raw.analysis_metadata
    assert meta['bandlimited'] is False and meta['spectral_max_degree'] == 31
    assert meta['chart_boundary_effects'] is (method != 'nerf')
    assert meta['max_angular_frequency'] > 0 and meta['gram_source']
    assert math.isfinite(meta['spectral_quadrature_error'])


@pytest.mark.parametrize('method,overrides', [
    ('wrap', {'degree': -1}), ('wrap', {'degree': 49}), ('wrap', {'degree': True}),
    ('grid', {'frequencies': 0}), ('grid', {'frequencies': 33}), ('grid', {'min_radius': .01}),
    ('theory', {'min_radius': 361}), ('theory', {'min_radius': 10, 'max_radius': 5}),
    ('grid', {'max_radius': float('nan')}), ('nerf', {'frequencies': 11}),
    ('rff', {'feature_count': 129}), ('rff', {'feature_count': 0}),
    ('rff', {'kernel_size': 0}), ('rff', {'kernel_size': 1001}),
    ('rff', {'seed': -1}), ('rff', {'seed': 2**32}), ('rff', {'seed': True}),
    ('rbf', {'feature_count': 65}), ('rbf', {'kernel_size': 1.9}), ('rbf', {'kernel_size': 91}),
    ('rbf', {'center_layout': 'train'}), ('rbf', {'radius': 0}), ('rbf', {'radius': 181}),
    ('rbf', {'center': [181, 0]}), ('rbf', {'center': [0, 91]}), ('rbf', {'center': [0]}),
    ('wrap', {'global_degree': 0}), ('nerf', {'global_degree': False}),
    ('wrap', {'rank_tolerance': 0}), ('wrap', {'rank_tolerance': float('inf')}),
])
def test_invalid_config_is_rejected_before_analysis(method, overrides):
    with pytest.raises(ValueError):
        build(encoder=method, **overrides)


@pytest.mark.parametrize('coords', [[[0, 91]], [[181, 0]], [[float('nan'), 0]], [0, 0], [[1, 2, 3]]])
@pytest.mark.parametrize('method', ['wrap', 'grid', 'theory', 'nerf', 'rff', 'rbf'])
def test_coordinate_domain_is_validated_for_every_formula(method, coords):
    raw = build(encoder=method, degree=0, feature_count=2)
    with pytest.raises(ValueError):
        raw.coordinate_evaluator(coords)


def test_public_entry_rejects_missing_or_unknown_encoder_and_nonobjects():
    from geope_globe.src.torchspatial_other import build_other
    for supplied in (None, [], {}, {'encoder': 'other'}, {'encoder': []}, {'encoder': {}}):
        with pytest.raises(ValueError):
            build_other(supplied)
