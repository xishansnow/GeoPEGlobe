"""Registry for the explicitly requested fixed TorchSpatial PE subset."""

SPHERE_IDS = {'spherec', 'spherem', 'spheremplus', 'spheredfs'}
OTHER_IDS = {'wrap', 'grid', 'theory', 'nerf', 'rff', 'rbf'}
IDS = SPHERE_IDS | OTHER_IDS

DEFAULTS = {
    'wrap': dict(encoder='wrap', degree=31, global_degree=-1),
    'grid': dict(encoder='grid', degree=31, frequencies=4, min_radius=5, max_radius=180, global_degree=-1),
    'theory': dict(encoder='theory', degree=31, frequencies=4, min_radius=5, max_radius=180, global_degree=-1),
    'nerf': dict(encoder='nerf', degree=31, frequencies=4, global_degree=-1),
    'rff': dict(encoder='rff', degree=31, feature_count=32, kernel_size=10, seed=0, global_degree=-1),
    'rbf': dict(encoder='rbf', degree=31, feature_count=32, kernel_size=20,
                center_layout='global', center=[110, 35], radius=30, seed=0, global_degree=-1),
    **{key: dict(encoder=key, degree=31, frequencies=4, min_radius=.05,
                max_radius=1, global_degree=-1) for key in ['spherec', 'spherem']},
    'spheremplus': dict(encoder='spheremplus', degree=31, frequencies=4, max_radius=32, global_degree=-1),
    'spheredfs': dict(encoder='spheredfs', degree=31, frequencies=4, max_radius=32, global_degree=-1),
}


def build(supplied):
    method = supplied['encoder']
    if method in SPHERE_IDS:
        from .torchspatial_sphere import build_spherical
        return build_spherical(supplied)
    if method in OTHER_IDS:
        from .torchspatial_other import build_other
        return build_other(supplied)
    raise ValueError('未知 TorchSpatial PE')
