"""Independent formulas and area integrals for the fixed Sphere frontends."""
import importlib

import numpy as np
import pytest
from scipy.special import roots_legendre, sph_harm_y

from geope_globe.src.encoders import RawEncoder
from geope_globe.src.geometry import analyze, evaluate


METHODS = ('spherec', 'spherem', 'spheremplus', 'spheredfs')


def build(**overrides):
    # Lazy import makes the initial missing-feature failure visible per test.
    module = importlib.import_module('geope_globe.src.torchspatial_sphere')
    return module.build_spherical(dict(encoder='spherec', degree=6) | overrides)


def config(method, **overrides):
    return dict(encoder=method, degree=6, frequencies=3,
                min_radius=.3, max_radius=3.2) | overrides


def builder(supplied):
    module = importlib.import_module('geope_globe.src.torchspatial_sphere')
    return module.build_spherical(supplied)


def formula(coords, method, frequencies):
    """Scalar-channel formulas, independent of production factor assembly."""
    longitude, latitude = np.deg2rad(np.asarray(coords)).T
    channels = []
    if method == 'spheredfs':
        longitude_basis = [func(f * longitude) for func in (np.sin, np.cos)
                           for f in frequencies]
        latitude_basis = [func(f * latitude) for func in (np.sin, np.cos)
                          for f in frequencies]
        channels.extend(x * y for x in longitude_basis for y in latitude_basis)
    for f in frequencies:
        slat, clat = np.sin(f * latitude), np.cos(f * latitude)
        slon, clon = np.sin(f * longitude), np.cos(f * longitude)
        if method == 'spherec':
            channels.extend((slat, clat * clon, clat * slon))
        elif method == 'spherem':
            channels.extend((slat, clat * np.cos(longitude), np.cos(latitude) * clon,
                             clat * np.sin(longitude), np.cos(latitude) * slon))
        elif method == 'spheremplus':
            channels.extend((slat, clat, slon, clon,
                             clat * np.cos(longitude), np.cos(latitude) * clon,
                             clat * np.sin(longitude), np.cos(latitude) * slon))
        else:
            channels.extend((slat, clat, slon, clon))
    return np.column_stack(channels)


def area_quadrature(nlat=72, nlon=144):
    latitude, wlat = roots_legendre(nlat)
    latitude *= np.pi / 2
    longitude, wlon = roots_legendre(nlon)
    longitude *= np.pi
    x, y = np.meshgrid(longitude, latitude)
    weights = (wlat[:, None] * np.pi / 4 * np.cos(latitude[:, None])
               * wlon[None, :] / 2).ravel()
    return np.rad2deg(np.column_stack((x.ravel(), y.ravel()))), weights


def independent_sh(coords, degree):
    """SciPy complex SH converted to the application's real dμ norm 1 basis."""
    lon, lat = np.deg2rad(coords).T
    columns = []
    for ell in range(degree + 1):
        for order in range(-ell, ell + 1):
            harmonic = sph_harm_y(ell, abs(order), np.pi / 2 - lat, lon)
            if order == 0:
                columns.append(np.sqrt(4 * np.pi) * harmonic.real)
            else:
                part = harmonic.imag if order < 0 else harmonic.real
                columns.append((-1)**abs(order) * np.sqrt(8 * np.pi) * part)
    return np.column_stack(columns)


@pytest.mark.parametrize('method', METHODS)
def test_formula_channel_order_gram_and_projection_match_independent_integrals(method):
    supplied = config(method)
    frequencies = ([1., 1 / np.sqrt(3.2), 1 / 3.2] if method in ('spheredfs', 'spheremplus')
                   else 1 / np.geomspace(.3, 3.2, 3))
    raw = builder(supplied)
    coords, weights = area_quadrature()
    expected = formula(coords, method, frequencies)
    dimension = dict(spherec=9, spherem=15, spheremplus=24, spheredfs=48)[method]
    assert isinstance(raw, RawEncoder)
    assert len(raw.channels) == dimension
    assert raw.coefficients.shape == (49, dimension)
    np.testing.assert_allclose(raw.coordinate_evaluator(coords), expected, atol=2e-14)
    np.testing.assert_allclose(raw.gram, expected.T @ (weights[:, None] * expected),
                               atol=4e-13)
    harmonics = independent_sh(coords, 6)
    np.testing.assert_allclose(raw.coefficients,
                               harmonics.T @ (weights[:, None] * expected), atol=3e-12)
    assert np.linalg.eigvalsh(raw.gram).min() > -2e-13


def test_single_scale_spherec_is_xyz_permutation_with_known_area_gram():
    raw = build(frequencies=1, min_radius=1., max_radius=10.)
    expected = np.array([[0, 1, 0], [0, 0, 1], [1, 0, 0.]])
    np.testing.assert_allclose(raw.coordinate_evaluator([[0, 0], [90, 0], [0, 90]]),
                               expected, atol=2e-16)
    np.testing.assert_allclose(raw.gram, np.eye(3) / 3, atol=2e-16)
    assert raw.analysis_metadata['frequencies'] == [1.]


@pytest.mark.parametrize('method', METHODS)
def test_single_scale_uses_minimum_for_c_m_and_one_for_mplus_dfs(method):
    raw = builder({**config(method), 'frequencies': 1, 'min_radius': .4,
                   'max_radius': 10.})
    frequency = 1. if method in ('spheredfs', 'spheremplus') else 2.5
    coords = [[-180., -90.], [180., 90.], [37., -21.]]
    np.testing.assert_allclose(raw.coordinate_evaluator(coords),
                               formula(coords, method, [frequency]), atol=2e-15)
    assert raw.analysis_metadata['frequencies'] == [frequency]


@pytest.mark.parametrize('method', ['spheremplus', 'spheredfs'])
def test_mplus_and_dfs_preserve_special_source_frequency_and_ignore_minimum(method):
    a = builder(dict(encoder=method, degree=6, frequencies=4,
                     max_radius=64, min_radius=.001))
    b = builder({**a.config, 'min_radius': 9000})
    np.testing.assert_allclose(a.analysis_metadata['frequencies'], [1., .25, .0625, .015625])
    np.testing.assert_array_equal(a.gram, b.gram)
    np.testing.assert_array_equal(a.coefficients, b.coefficients)
    np.testing.assert_allclose(a.coordinate_evaluator([[63, -27]]),
                               formula([[63, -27]], method, [1., .25, .0625, .015625]),
                               atol=2e-15)
    assert 'min_radius' not in a.config and 'min_radius' not in b.config
    assert any('min_radius' in warning and 'max_radius' in warning for warning in a.warnings)


@pytest.mark.parametrize('method,dimension', [('spherec', 12), ('spherem', 20),
                                              ('spheremplus', 32), ('spheredfs', 80)])
def test_defaults_metadata_and_config_replay(method, dimension):
    raw = builder(dict(encoder=method))
    assert raw.coefficients.shape == (1024, dimension)
    assert raw.config['frequencies'] == 4
    assert raw.config['degree'] == 31 and raw.config['global_degree'] == -1
    assert raw.config['max_radius'] == (32 if method in ('spheredfs', 'spheremplus') else 1)
    if method in ('spheredfs', 'spheremplus'):
        assert 'min_radius' not in raw.config
    metadata = raw.analysis_metadata
    assert metadata['bandlimited'] is False and metadata['chart_boundary_effects'] is True
    assert metadata['spectral_max_degree'] == 31
    assert metadata['gram_source'] == 'analytic_coordinate_integrals'
    assert 0 <= metadata['spectral_quadrature_error'] < 1e-8
    assert metadata['spectral_latitude_nodes'] >= 128
    assert metadata['max_angular_frequency'] >= 1
    assert any('非有限带限' in warning for warning in raw.warnings)
    assert any('极点' in warning and '日界线' in warning for warning in raw.warnings)
    replay = builder(raw.config)
    np.testing.assert_array_equal(raw.gram, replay.gram)
    np.testing.assert_array_equal(raw.coefficients, replay.coefficients)


def test_spheremplus_and_dfs_report_same_source_frequency_rule():
    mplus = builder(config('spheremplus'))
    dfs = builder(config('spheredfs'))
    assert mplus.analysis_metadata['frequency_rule'] == dfs.analysis_metadata['frequency_rule']
    np.testing.assert_array_equal(mplus.analysis_metadata['frequencies'],
                                  dfs.analysis_metadata['frequencies'])
    assert any('上游' in warning and 'min_radius' in warning for warning in mplus.warnings)


@pytest.mark.parametrize('method,maximum', [('spherec', 1 / 3), ('spherem', 1.),
                                           ('spheremplus', 1.), ('spheredfs', 1.)])
def test_sampling_frequency_includes_fixed_base_angles_for_mixed_scales(method, maximum):
    raw = builder(config(method, min_radius=3., max_radius=10.))
    assert raw.analysis_metadata['max_angular_frequency'] == pytest.approx(maximum)
    assert raw.analysis_metadata['chart_boundary_effects'] is True


@pytest.mark.parametrize('method,dimension', [('spherec', 96), ('spherem', 160),
                                              ('spheremplus', 256), ('spheredfs', 224)])
@pytest.mark.parametrize('tolerance', [1e-14, 1e-3])
def test_maximum_scale_count_and_rank_tolerance_endpoints_are_accepted(method, dimension, tolerance):
    raw = builder(dict(encoder=method, degree=0,
                       frequencies=7 if method == 'spheredfs' else 32,
                       min_radius=10.,
                       max_radius=10000. if method in ('spheredfs', 'spheremplus') else 10.,
                       rank_tolerance=tolerance))
    assert raw.gram.shape == (dimension, dimension)
    assert raw.coefficients.shape == (1, dimension)
    assert raw.config['rank_tolerance'] == tolerance
    assert np.isfinite(raw.gram).all() and np.isfinite(raw.coefficients).all()


@pytest.mark.parametrize('method', METHODS)
def test_direct_fields_and_gram_are_independent_of_analysis_degree(method):
    supplied = {**config(method), 'min_radius': .25, 'max_radius': 2.}
    low = builder({**supplied, 'degree': 0})
    high = builder({**supplied, 'degree': 10})
    np.testing.assert_array_equal(low.gram, high.gram)
    args = ({'nlat': 16, 'nlon': 32}, {'lon': 35, 'lat': -22}, {'min': 0, 'max': 0}, 2)
    first, second = [evaluate(analyze(raw), *args) for raw in (low, high)]
    for field in ('energy', 'kernel', 'similarity', 'channel'):
        np.testing.assert_allclose(first['fields'][field], second['fields'][field], atol=1e-12)
    assert first['info']['actual_max_degree'] is None
    assert second['info']['spectral_energy_coverage'] > first['info']['spectral_energy_coverage']


@pytest.mark.parametrize('method,rank', [('spherec', 3), ('spherem', 3),
                                         ('spheremplus', 6), ('spheredfs', 8)])
def test_repeated_scales_do_not_create_spurious_rank(method, rank):
    raw = builder({**config(method), 'min_radius': 1., 'max_radius': 1.})
    model = analyze(raw)
    assert model.rank == rank
    assert model.gram_error < 1e-10


@pytest.mark.parametrize('method', METHODS)
def test_extreme_frequency_retains_original_formula_and_finite_projection(method):
    raw = builder(dict(encoder=method, frequencies=1, min_radius=.001,
                       max_radius=10000 if method in ('spheredfs', 'spheremplus') else 10., degree=48))
    frequency = 1. if method in ('spheredfs', 'spheremplus') else 1000.
    coords = [[-123.7, 56.2], [179.9, -89.8]]
    np.testing.assert_allclose(raw.coordinate_evaluator(coords),
                               formula(coords, method, [frequency]), atol=2e-13)
    assert raw.coefficients.shape[0] == 2401
    assert np.isfinite(raw.coefficients).all()
    assert raw.analysis_metadata['spectral_quadrature_error'] < 1e-8
    if method in ('spherec', 'spherem'):
        # At even integer frequency 1000 these channels' low-degree SH
        # projections vanish by Fourier orthogonality, despite nonzero raw Gram.
        np.testing.assert_allclose(raw.coefficients, 0, atol=1e-11)


@pytest.mark.parametrize('method', METHODS)
@pytest.mark.parametrize('overrides', [dict(frequencies=0), dict(frequencies=1.5),
    dict(frequencies=True), dict(degree=-1), dict(degree=49), dict(degree=True),
    dict(global_degree=0), dict(rank_tolerance=0), dict(rank_tolerance=1.01e-3),
    dict(rank_tolerance=float('nan')), dict(max_radius=float('inf'))])
def test_invalid_common_config_is_rejected(method, overrides):
    with pytest.raises(ValueError):
        builder({**config(method), **overrides})


@pytest.mark.parametrize('overrides', [dict(frequencies=33), dict(min_radius=.0009),
    dict(min_radius=10.1), dict(min_radius=float('nan')), dict(max_radius=10.1),
    dict(min_radius=2, max_radius=1)])
@pytest.mark.parametrize('method', METHODS[:2])
def test_invalid_geometric_config_is_rejected(method, overrides):
    with pytest.raises(ValueError):
        builder({**config(method), **overrides})


def test_dfs_scale_count_above_seven_is_rejected():
    with pytest.raises(ValueError):
        builder(config('spheredfs', frequencies=8))


@pytest.mark.parametrize('method', ['spheremplus', 'spheredfs'])
@pytest.mark.parametrize('maximum', [.99, 10001])
def test_invalid_source_rule_maximum_radius_is_rejected(method, maximum):
    with pytest.raises(ValueError):
        builder(config(method, max_radius=maximum))


def test_mplus_scale_count_above_thirty_two_is_rejected():
    with pytest.raises(ValueError):
        builder(config('spheremplus', frequencies=33))


@pytest.mark.parametrize('supplied', [None, [], {}, {'encoder': 'spherecplus'}, {'encoder': []}])
def test_invalid_builder_input_is_rejected(supplied):
    with pytest.raises(ValueError):
        builder(supplied)


@pytest.mark.parametrize('coords', [[0, 0], [[0, 0, 0]], [[float('nan'), 0]],
                                    [[0, float('inf')]], [[0, 91]], [[181, 0]]])
def test_invalid_coordinates_are_rejected(coords):
    raw = build(frequencies=1)
    with pytest.raises(ValueError):
        raw.coordinate_evaluator(coords)
