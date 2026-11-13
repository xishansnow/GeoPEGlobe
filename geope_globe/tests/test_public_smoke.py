from geope_globe.src.service import catalog, compute
import numpy as np
import pytest


def test_public_catalog_lists_only_supported_encoders():
    assert set(catalog()['defaults']) == {
        'grid', 'nerf', 'rbf', 'rff', 'sh', 'slepian', 'spherec',
        'spherecplus', 'spheredfs', 'spherem', 'spheremplus',
        'theory', 'wrap', 'xyz',
    }


def test_regional_and_global_methods_compute_at_shared_point():
    common = {'grid': {'nlat': 16, 'nlon': 32},
              'anchor': {'lon': 110, 'lat': 35},
              'band': {'min': 0, 'max': 4}}
    regional = compute({**common, 'config': {
        'encoder': 'slepian', 'degree': 4, 'center': [110, 35],
        'radius': 30, 'selection': 'k', 'k': 5, 'global_degree': 1,
    }})
    global_sh = compute({**common, 'config': {
        'encoder': 'sh', 'degree': 2, 'global_degree': -1,
    }})
    assert regional['point']['lon'] == global_sh['point']['lon'] == 110
    assert regional['point']['lat'] == global_sh['point']['lat'] == 35
    assert regional['info']['feature_count'] == 9
    assert global_sh['info']['feature_count'] == 9
    assert len(regional['fields']['raw_similarity']) == 16 * 32
    assert len(global_sh['fields']['raw_similarity']) == 16 * 32


def test_pixel_center_aliasing_is_disclosed_for_harmonic_channel():
    result = compute({'config': {'encoder': 'sh', 'degree': 16},
                      'channel': 288, 'anchor': {'lon': 110, 'lat': 35},
                      'grid': {'nlat': 16, 'nlon': 32}})
    assert abs(result['point']['features'][288]) > 0.01
    assert max(map(abs, result['fields']['channel'])) < 1e-10
    assert any('全部采为近零' in warning for warning in result['info']['warnings'])


def test_unit_frequency_spherec_and_spherem_are_smooth_like_xyz():
    anchor = {'lon': 0, 'lat': 90}
    baseline = compute({'config': {'encoder': 'xyz'}, 'anchor': anchor,
                        'grid': {'nlat': 16, 'nlon': 32}})
    for method in ('spherec', 'spherem'):
        result = compute({'config': {'encoder': method, 'frequencies': 1,
                                     'min_radius': 1, 'max_radius': 1, 'degree': 4},
                          'anchor': anchor, 'grid': {'nlat': 16, 'nlon': 32}})
        assert result['info']['rank'] == baseline['info']['rank'] == 3
        assert result['info']['bandlimited'] is True
        assert result['info']['actual_max_degree'] == 1
        assert result['info']['chart_boundary_effects'] is False
        np.testing.assert_allclose(result['point']['metric'], baseline['point']['metric'], rtol=1e-5)
        np.testing.assert_allclose(result['fields']['similarity'], baseline['fields']['similarity'], rtol=1e-9, atol=1e-12)


@pytest.mark.parametrize('config', [
    {'encoder': 'spherec', 'frequencies': 1, 'min_radius': 1, 'max_radius': 1, 'degree': 0},
    {'encoder': 'spherem', 'frequencies': 1, 'min_radius': 1, 'max_radius': 1, 'degree': 0},
    {'encoder': 'spherecplus', 'frequencies': 1, 'min_radius': 1/3, 'max_radius': 1/3, 'degree': 0},
])
def test_empty_harmonic_projection_remains_valid_and_disclosed(config):
    result = compute({'config': config, 'grid': {'nlat': 16, 'nlon': 32}})
    assert result['point']['raw_norm'] > 0
    assert result['info']['spectral_energy_coverage'] < 1e-10
    assert result['info']['spectral_tail_fraction'] > 1 - 1e-10
    assert any('没有非零投影' in warning for warning in result['info']['warnings'])
