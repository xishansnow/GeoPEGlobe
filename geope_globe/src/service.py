"""Validated, bounded request orchestration. The model cache contains no labels."""
from functools import lru_cache
import json
import time
from .encoders import build_encoder
from .geometry import analyze, evaluate, SPECTRAL_COVERAGE_TOLERANCE
from .torchspatial import DEFAULTS as TORCHSPATIAL_DEFAULTS


DEFAULTS = {
    **TORCHSPATIAL_DEFAULTS,
    'xyz': {'encoder': 'xyz'},
    'spherecplus': {'encoder': 'spherecplus', 'degree': 31, 'frequencies': 8,
                    'min_radius': .05, 'max_radius': 1., 'global_degree': -1},
    'sh': {'encoder': 'sh', 'degree': 8, 'global_degree': -1},
    'slepian': {'encoder': 'slepian', 'degree': 31, 'center': [110, 35], 'radius': 30,
                'selection': 'k', 'k': 64, 'threshold': .05, 'global_degree': 3},

}


def catalog():
    return {'defaults': DEFAULTS, 'limits': {'degree': [0, 48], 'sh_degree': [0, 24],
            'regional_features': [1, 256], 'nlat': [16, 96], 'global_degree': [-1, 8],
            'spherecplus_frequencies': [1, 32], 'spherecplus_radius': [.001, 10],
            'torchspatial': {'geometric_frequencies': [1, 32], 'dfs_frequencies': [1, 7],
                'nerf_frequencies': [1, 10], 'rff_features': [1, 128], 'rbf_features': [1, 64],
                'planar_radius': [.1, 360], 'sphere_radius': [.001, 10],
                'rff_covariance': [.01, 1000], 'rbf_width_degrees': [2, 90], 'seed': [0, 2**32-1]}},
            'tolerances': {'spectral_coverage': SPECTRAL_COVERAGE_TOLERANCE},
            'normalization': 'dμ=dΩ/(4π)', 'purpose': '固定前端表示几何，不读取目标标签或训练模型'}


@lru_cache(maxsize=4)
def cached_model(config_json):
    start = time.perf_counter()
    raw = build_encoder(json.loads(config_json))
    model = analyze(raw)
    model.build_seconds = time.perf_counter()-start
    return model


def compute(body):
    if not isinstance(body, dict):
        raise ValueError('请求必须为 JSON 对象')
    config = body.get('config', DEFAULTS['slepian'])
    if not isinstance(config, dict):
        raise ValueError('config 必须为对象')
    try:
        identity = json.dumps(config, sort_keys=True, allow_nan=False, separators=(',', ':'))
    except (ValueError, TypeError) as exc:
        raise ValueError('配置必须由有限 JSON 数值构成') from exc
    model = cached_model(identity)
    return evaluate(model, body.get('grid', {'nlat': 32, 'nlon': 64}),
                    body.get('anchor', {'lon': 110, 'lat': 35}),
                    body.get('band', {'min': 8, 'max': 16}), body.get('channel', 0))
