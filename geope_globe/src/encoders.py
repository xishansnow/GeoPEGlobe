"""Fixed frontends in a common real, 4pi-normalized harmonic coordinate system."""
from dataclasses import dataclass, field
import math
import threading
import numpy as np
import pyshtools as pysh


def integer(value, name, lower, upper):
    if isinstance(value, bool) or not isinstance(value, (int, np.integer)) or not lower <= value <= upper:
        raise ValueError(f'{name} 必须是 {lower}…{upper} 的整数')
    return int(value)


def finite(value, name, lower, upper):
    if isinstance(value, bool) or not isinstance(value, (int, float, np.number)):
        raise ValueError(f'{name} 必须是有限数字')
    value = float(value)
    if not math.isfinite(value) or not lower <= value <= upper:
        raise ValueError(f'{name} 必须位于 [{lower}, {upper}]')
    return value


def lonlat_xyz(coords):
    values = np.asarray(coords, dtype=float)
    if values.ndim != 2 or values.shape[1] != 2 or not np.isfinite(values).all():
        raise ValueError('坐标必须为有限的 [经度, 纬度] 数组')
    if np.any(np.abs(values[:, 1]) > 90) or np.any(np.abs(values[:, 0]) > 180):
        raise ValueError('经纬度超出范围')
    lon, lat = np.deg2rad(values).T
    return np.column_stack((np.cos(lat)*np.cos(lon), np.cos(lat)*np.sin(lon), np.sin(lat)))


def real_sh(xyz, degree):
    """Index l*l+l+m, negative m=sine; no Condon–Shortley phase, dmu norm 1."""
    xyz = np.asarray(xyz, dtype=float)
    z = np.clip(xyz[:, 2], -1, 1)
    transverse = np.hypot(xyz[:, 0], xyz[:, 1])
    longitude = np.arctan2(xyz[:, 1], xyz[:, 0])
    result = np.empty((len(xyz), (degree+1)**2))
    diagonal = np.ones(len(xyz))
    for m in range(degree+1):
        if m:
            diagonal = math.sqrt((2*m+1)/(2*m))*transverse*diagonal
        values = np.empty((len(xyz), degree-m+1))
        values[:, 0] = diagonal
        if m < degree:
            values[:, 1] = math.sqrt(2*m+3)*z*diagonal
        for l in range(m+2, degree+1):
            a = math.sqrt((4*l*l-1)/(l*l-m*m))
            b = math.sqrt(((2*l+1)*((l-1)**2-m*m))/((2*l-3)*(l*l-m*m)))
            values[:, l-m] = a*z*values[:, l-m-1]-b*values[:, l-m-2]
        indices = np.arange(m, degree+1)
        centers = indices*(indices+1)
        if m == 0:
            result[:, centers] = values
        else:
            result[:, centers+m] = values*(math.sqrt(2)*np.cos(m*longitude))[:, None]
            result[:, centers-m] = values*(math.sqrt(2)*np.sin(m*longitude))[:, None]
    return result


def flatten(coefficients, degree):
    result = np.zeros((degree+1)**2)
    for l in range(degree+1):
        result[l*l+l] = coefficients[0, l, 0]
        for m in range(1, l+1):
            result[l*l+l+m] = coefficients[0, l, m]
            result[l*l+l-m] = coefficients[1, l, m]
    return result


@dataclass
class RawEncoder:
    coefficients: np.ndarray
    channels: list
    config: dict
    centers: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    coordinate_evaluator: object = None
    gram: object = None
    analysis_metadata: dict = field(default_factory=dict)


_SHTOOLS_LOCK = threading.RLock()

def build_encoder(supplied):
    # SHTOOLS rotation/construction routines contain non-reentrant native state.
    if isinstance(supplied, dict) and supplied.get("encoder", "slepian") == "slepian":
        with _SHTOOLS_LOCK:
            return _build_encoder(supplied)
    return _build_encoder(supplied)


def _build_encoder(supplied):
    if not isinstance(supplied, dict):
        raise ValueError('config 必须为对象')
    method = supplied.get('encoder', 'slepian')
    from .torchspatial import IDS, build
    if method in IDS:
        return build(supplied)
    if method == 'spherecplus':
        from .spherecplus import build_spherecplus
        return build_spherecplus(supplied)
    if method not in {'xyz', 'sh', 'slepian'}:
        raise ValueError('未知编码器')
    degree = integer(supplied.get('degree', 8 if method == 'sh' else 31), 'degree', 0, 48)
    if method == 'sh' and degree > 24:
        raise ValueError('交互工具的完整球谐最高阶为 24；区域前端最高阶为 48')
    center = supplied.get('center', [110, 35])
    if not isinstance(center, (list, tuple)) or len(center) != 2:
        raise ValueError('center 必须为 [经度, 纬度]')
    center = [finite(center[0], '中心经度', -180, 180), finite(center[1], '中心纬度', -90, 90)]
    radius = finite(supplied.get('radius', 30), '球冠半径', .1, 180)
    global_degree = integer(supplied.get('global_degree', -1), 'global_degree', -1, 8)
    tolerance = finite(supplied.get('rank_tolerance', 1e-9), 'rank_tolerance', 1e-14, 1e-3)
    config = dict(encoder=method, degree=degree, center=center, radius=radius,
                  global_degree=global_degree, rank_tolerance=tolerance)
    channels, centers, warnings = [], [], []
    if method == 'xyz':
        degree = 1; config.update(degree=1, global_degree=-1)
        matrix = np.zeros((4, 3))
        matrix[[3, 1, 2], np.arange(3)] = 1/np.sqrt(3)
        channels = [dict(name=name, kind='cartesian') for name in ['x', 'y', 'z']]
    elif method == 'sh':
        degrees = supplied.get('degrees', list(range(degree+1)))
        if not isinstance(degrees, list) or not degrees:
            raise ValueError('degrees 必须为非空阶集合')
        degrees = sorted(set(integer(l, '球谐阶', 0, degree) for l in degrees))
        indices = [l*l+l+m for l in degrees for m in range(-l, l+1)]
        matrix = np.eye((degree+1)**2)[:, indices]
        channels = [dict(name=f'Y({l},{m})', degree=l, order=m, kind='sh') for l in degrees for m in range(-l, l+1)]
        config.update(degrees=degrees, global_degree=-1)
    elif method == 'slepian':
        selection = supplied.get('selection', 'k')
        if selection not in {'k', 'threshold', 'shannon'}:
            raise ValueError('selection 必须为 k、threshold 或 shannon')
        slepian = pysh.Slepian.from_cap(radius, degree, clat=center[1], clon=center[0])
        threshold = finite(supplied.get('threshold', .05), 'threshold', 0, 1)
        if selection == 'k':
            count = integer(supplied.get('k', 64), 'k', 1, min(256, (degree+1)**2))
        elif selection == 'threshold':
            count = int(np.count_nonzero(slepian.eigenvalues > threshold))
        else:
            count = int(np.ceil(slepian.shannon))
        if not 1 <= count <= 256:
            raise ValueError(f'该截断保留 {count} 个区域模式；交互范围为 1…256，请调整半径、带限或截断规则')
        matrix = np.stack([flatten(slepian.to_shcoeffs(n).to_array(), degree) for n in range(count)], axis=1)
        channels = [dict(name=f'Slepian {n+1} · λ={value:.5f}', kind='slepian', eigenvalue=float(value), mode=n) for n, value in enumerate(slepian.eigenvalues[:count])]
        if count < len(slepian.eigenvalues) and abs(slepian.eigenvalues[count-1]-slepian.eigenvalues[count]) < 1e-10:
            warnings.append('固定 K 可能切过简并模态组；局部形态不一定保持球冠旋转对称性')
        config.update(selection=selection, k=count, threshold=threshold)
    actual_degree = max(degree, config['global_degree'])
    if actual_degree > degree:
        matrix = np.pad(matrix, ((0, (actual_degree+1)**2-len(matrix)), (0, 0)))
    if method == 'slepian' and global_degree >= 0:
        global_part = np.eye((actual_degree+1)**2)[:, :(global_degree+1)**2]
        matrix = np.column_stack([matrix, global_part])
        channels.extend(dict(name=f'Global Y({l},{m})', degree=l, order=m, kind='sh') for l in range(global_degree+1) for m in range(-l, l+1))
    # Keep regional construction degree distinct from the ambient coefficient
    # matrix degree; otherwise exporting a higher global branch changes replay.
    return RawEncoder(matrix, channels, config, centers, warnings)
