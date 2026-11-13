import numpy as np
import pytest
from scipy.special import roots_legendre
from geope_globe.src.encoders import build_encoder, lonlat_xyz, real_sh
from geope_globe.src.geometry import analyze, evaluate


def config(**kwargs):
    return dict(encoder='spherecplus',frequencies=3,min_radius=.25,max_radius=1.,degree=16,**kwargs)


def direct(coords, frequencies):
    lon,lat=(np.deg2rad(np.asarray(coords))[:,:,None]*np.asarray(frequencies)).transpose(1,0,2)
    return np.stack([np.sin(lat),np.cos(lat),np.sin(lon),np.cos(lon),np.cos(lat)*np.cos(lon),np.cos(lat)*np.sin(lon)],axis=-1).reshape(len(coords),-1)


def quadrature(nlat=96,nlon=256):
    phi,w=roots_legendre(nlat);phi*=np.pi/2;w*=np.pi/2
    lam,wl=roots_legendre(nlon);lam*=np.pi
    x,y=np.meshgrid(lam,phi)
    return np.rad2deg(np.column_stack([x.ravel(),y.ravel()])),(w[:,None]*np.cos(phi[:,None])/2*wl[None,:]/2).ravel()


def test_raw_formula_and_exact_gram_match_independent_area_quadrature():
    raw=build_encoder(config());coords,weights=quadrature()
    expected=direct(coords,[4.,2.,1.])
    np.testing.assert_allclose(raw.coordinate_evaluator(coords),expected,atol=1e-13)
    np.testing.assert_allclose(raw.gram,expected.T@(weights[:,None]*expected),atol=3e-13)
    harmonics=real_sh(lonlat_xyz(coords),16)
    np.testing.assert_allclose(raw.coefficients,harmonics.T@(weights[:,None]*expected),atol=3e-12)


def test_noninteger_frequencies_and_repeated_scales_are_supported():
    c=config();c.update(frequencies=3,min_radius=.3,max_radius=.7)
    raw=build_encoder(c);coords,weights=quadrature()
    expected=direct(coords,1/np.geomspace(.3,.7,3))
    np.testing.assert_allclose(raw.gram,expected.T@(weights[:,None]*expected),atol=3e-13)
    c.update(min_radius=1.,max_radius=1.)
    model=analyze(build_encoder(c));assert model.rank==6


def test_original_geometry_is_independent_of_spectral_analysis_cutoff():
    a=config();b={**a,'degree':4}
    args=({'nlat':16,'nlon':32},{'lon':110,'lat':35},{'min':0,'max':3},4)
    ra=evaluate(analyze(build_encoder(a)),*args);rb=evaluate(analyze(build_encoder(b)),*args)
    for key in ['energy','kernel','similarity','channel']:
        np.testing.assert_allclose(ra['fields'][key],rb['fields'][key],atol=1e-10)
    assert ra['info']['actual_max_degree'] is None and not ra['info']['bandlimited']
    assert ra['info']['spectral_energy_coverage']>rb['info']['spectral_energy_coverage']
    assert 0<ra['info']['spectral_tail_fraction']<1
    assert abs(sum(ra['spectrum']['energy'])/ra['info']['rank']+ra['info']['spectral_tail_fraction']-1)<1e-10
    # The displayed raw channel is the actual coordinate formula, not its SH projection.
    lon,lat=np.meshgrid(ra['grid']['longitudes'],ra['grid']['latitudes'])
    expected=direct(np.column_stack([lon.ravel(),lat.ravel()]),[4.,2.,1.])
    np.testing.assert_allclose(ra['fields']['channel'],expected[:,4],atol=1e-13)


def test_global_mean_and_kernel_anchor_identity_for_original_features():
    model=analyze(build_encoder(config()));coords,w=quadrature()
    q=model.raw.coordinate_evaluator(coords)@model.coordinate_transform
    np.testing.assert_allclose(q.T@(w[:,None]*q),np.eye(model.rank),atol=1e-8)
    assert abs(w@np.sum(q*q,axis=1)/model.rank-1)<1e-9
    r=evaluate(model,{'nlat':16,'nlon':32},{'lon':110,'lat':35},{'min':0,'max':16},0)
    zero=r['profile']['angles'].index(0)
    assert r['profile']['kernel'][zero]==pytest.approx(r['point']['energy']*model.rank)
    assert r['profile']['similarity'][zero]==pytest.approx(1)


@pytest.mark.parametrize('anchor',[{'lon':0,'lat':90},{'lon':180,'lat':0}])
def test_chart_boundary_metrics_are_explicitly_undefined(anchor):
    r=evaluate(analyze(build_encoder(config())),{'nlat':16,'nlon':32},anchor,{'min':0,'max':16},0)
    assert r['point']['metric'] is None and r['point']['sensitivity'] is None
    assert r['point']['eigenvalues']==[None,None]
    assert any('坐标图' in s for s in r['info']['warnings'])


def test_uncomputed_frequency_band_is_masked_not_reported_as_zero_energy():
    c={**config(),'degree':3}
    r=evaluate(analyze(build_encoder(c)),{'nlat':16,'nlon':32},{'lon':110,'lat':35},{'min':2,'max':7},0)
    assert r['info']['band_energy'] is None and not r['info']['band_complete']
    assert all(v is None for v in r['fields']['band_energy'])
    assert any('超出分析截断' in s for s in r['info']['warnings'])


def test_high_frequency_original_features_keep_unresolved_tail_and_sampling_warning():
    c={**config(),'frequencies':4,'min_radius':.001,'max_radius':1.,'degree':8}
    r=evaluate(analyze(build_encoder(c)),{'nlat':16,'nlon':32},{'lon':110,'lat':35},{'min':0,'max':8},0)
    assert r['info']['spectral_tail_fraction']>.2
    assert r['info']['spectral_quadrature_error']<1e-8
    assert any('混叠' in s for s in r['info']['warnings'])
    assert r['point']['finite_difference_step']<1e-5


@pytest.mark.parametrize('frequency',[8,16])
def test_nyquist_equality_warns_for_raw_and_squared_field(frequency):
    c={**config(),'frequencies':1,'min_radius':1/frequency,'max_radius':1/frequency,'degree':8}
    r=evaluate(analyze(build_encoder(c)),{'nlat':16,'nlon':32},{'lon':0,'lat':0},{'min':0,'max':0},3)
    assert any('混叠' in s for s in r['info']['warnings'])
    if frequency==16:
        assert max(abs(v) for v in r['fields']['channel'])<1e-12
        assert r['point']['features'][3]==pytest.approx(1)


def test_poorly_conditioned_supported_configuration_discloses_precision_loss():
    c={**config(),'frequencies':8,'min_radius':9,'max_radius':10,'degree':8}
    r=evaluate(analyze(build_encoder(c)),{'nlat':16,'nlon':32},{'lon':0,'lat':0},{'min':0,'max':0},0)
    assert r['info']['gram_error']>1e-5
    assert any('白化精度' in s for s in r['info']['warnings'])


def test_zero_low_order_projection_does_not_turn_roundoff_into_large_error():
    c={**config(),'frequencies':1,'min_radius':1/3,'max_radius':1/3,'degree':0}
    raw=build_encoder(c)
    assert np.linalg.norm(raw.coefficients)<1e-12
    assert raw.analysis_metadata['spectral_quadrature_error']<1e-10


@pytest.mark.parametrize('overrides',[{'frequencies':0},{'frequencies':33},{'min_radius':0},{'min_radius':.0001},{'min_radius':2,'max_radius':1},{'global_degree':2}])
def test_invalid_spherecplus_config_is_rejected(overrides):
    with pytest.raises(ValueError):build_encoder({**config(),**overrides})
