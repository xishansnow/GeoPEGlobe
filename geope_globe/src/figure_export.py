"""Publication-style, full-globe PNG from evaluated encoder fields."""
from functools import lru_cache
from io import BytesIO
import json
from pathlib import Path

import numpy as np

LAYERS = {'raw_similarity', 'similarity', 'kernel', 'energy', 'channel', 'region', 'centers'}
SIGNED = {'raw_similarity', 'similarity', 'kernel', 'channel'}
PLAIN = {'region', 'centers'}
TITLES = {
    'raw_similarity': 'Raw PE cosine similarity to selected location',
    'similarity': 'Global-area normalized subspace similarity',
    'kernel': 'Global-area subspace kernel amplitude',
    'energy': 'Fixed representation intensity C(x) / r',
    'channel': 'One raw PE feature',
    'region': 'Configured regional construction cap',
    'centers': 'Construction centers by native scale',
}
METHODS = {
    'slepian': 'Regional Slepian + low-degree global SH',
    'sh': 'Global real spherical harmonics',
    'xyz': 'Unit-sphere Cartesian coordinates',
    'spherecplus': 'Sphere2Vec sphereC+',
}


@lru_cache(maxsize=1)
def _land_arcs():
    path = Path(__file__).resolve().parents[1] / 'web/vendor/world-atlas/land-110m.json'
    topology = json.loads(path.read_text())
    scale = topology['transform']['scale']
    translate = topology['transform']['translate']
    arcs = []
    for encoded in topology['arcs']:
        x = y = 0
        points = []
        for dx, dy in encoded:
            x += dx
            y += dy
            points.append((x * scale[0] + translate[0], y * scale[1] + translate[1]))
        arcs.append(np.asarray(points, dtype=float))
    return arcs


def _segments(points):
    """Split a polyline where an equirectangular map crosses the date line."""
    if len(points) < 2:
        return []
    breaks = np.flatnonzero(np.abs(np.diff(points[:, 0])) > 180) + 1
    return [part for part in np.split(points, breaks) if len(part) > 1]


def _cap_points(center, radius):
    lon, lat = np.deg2rad(center)
    p = np.array([np.cos(lat) * np.cos(lon), np.cos(lat) * np.sin(lon), np.sin(lat)])
    east = np.array([-np.sin(lon), np.cos(lon), 0.])
    north = np.cross(p, east)
    azimuth = np.linspace(0, 2 * np.pi, 721)
    angle = np.deg2rad(radius)
    xyz = (np.cos(angle) * p + np.sin(angle) *
           (np.cos(azimuth)[:, None] * north + np.sin(azimuth)[:, None] * east))
    return np.rad2deg(np.column_stack([np.arctan2(xyz[:, 1], xyz[:, 0]),
                                      np.arctan2(xyz[:, 2], np.hypot(xyz[:, 0], xyz[:, 1]))]))


def _has_cap(config):
    return config['encoder'] == 'slepian' or (config['encoder'] == 'rbf' and config.get('center_layout') == 'cap')


def _method_label(config):
    name = METHODS.get(config['encoder'], config['encoder'])
    if config['encoder'] == 'slepian' and config.get('global_degree', -1) < 0:
        return name.replace(' + low-degree global SH', '')
    return name


def _config_summary(config):
    method = config['encoder']
    if method == 'slepian':
        center = config['center']
        text = f'L{config["degree"]} | target cap {config["radius"]}° at ({center[0]}°, {center[1]}°)'
        selection = config.get('selection', 'k')
        if selection == 'k':
            text += f' | K={config.get("k", "?")}'
        elif selection == 'threshold':
            text += f' | threshold={config.get("threshold", "?")}'
        else:
            text += ' | Shannon selection'
        if config.get('global_degree', -1) >= 0:
            text += f' | global SH L{config["global_degree"]}'
        return text
    if method == 'sh':
        return f'Full real SH through L{config["degree"]}'
    if method == 'xyz':
        return 'Unit-sphere xyz; 3 raw features'
    parameters = [f'{key}={value}' for key, value in config.items()
                  if key not in {'encoder', 'center', 'radius', 'rank_tolerance', 'global_degree'}]
    return ' | '.join(parameters)


def _domain(results, layer, locked):
    if layer in {'raw_similarity', 'similarity'}:
        return [(-1., 1.)] * 2
    values = [np.asarray(result['fields'][layer], dtype=float) for result in results]
    groups = [np.concatenate(values)] * 2 if locked else values
    domains = []
    for group in groups:
        finite = group[np.isfinite(group)]
        if layer in SIGNED:
            extent = max(float(np.max(np.abs(finite))) if finite.size else 0., 1e-12)
            domains.append((-extent, extent))
        else:
            maximum = max(float(np.max(finite)) if finite.size else 0., 1e-12)
            domains.append((0., maximum))
    return domains


def render_publication_png(results, layer, colors_locked=True, show_region=False, show_centers=False, requests=None):
    if layer not in LAYERS or len(results) != 2:
        raise ValueError('论文图需要 A/B 两份结果和受支持的图层')
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.colors import LinearSegmentedColormap
    from matplotlib.figure import Figure

    signed = layer in SIGNED
    palette = (['#2c659b', '#eaf1f3', '#f2b544'] if signed else
               ['#f2f5f7', '#cce3e1', '#63b8aa', '#237984', '#123c60'])
    cmap = LinearSegmentedColormap.from_list('paper_pe', palette).with_extremes(bad='#d3d7dc')
    domains = None if layer in PLAIN else _domain(results, layer, colors_locked)
    figure = Figure(figsize=(12, 5.8), dpi=220, facecolor='white')
    FigureCanvasAgg(figure)
    figure.text(.06, .94, TITLES[layer], fontsize=17, color='#1c2e3d', weight='semibold')
    figure.text(.06, .902, 'Full sphere in equirectangular projection | A/B comparison', fontsize=9, color='#526473')
    for index, result in enumerate(results):
        left = .065 + index * .49
        ax = figure.add_axes([left, .33, .42, .47], facecolor='#f8fafb')
        config = result['config']
        if layer not in PLAIN:
            grid = result['grid']
            field = np.asarray(result['fields'][layer], dtype=float).reshape(grid['nlat'], grid['nlon'])
            masked = np.ma.masked_invalid(field)
            image = ax.imshow(masked, extent=(-180, 180, -90, 90), origin='upper',
                              interpolation='nearest', aspect='auto', cmap=cmap,
                              vmin=domains[index][0], vmax=domains[index][1], rasterized=True)
        for arc in _land_arcs():
            for part in _segments(arc):
                ax.plot(part[:, 0], part[:, 1], color='#445968', linewidth=.28, alpha=.72, zorder=3)
        if (layer == 'region' or show_region) and _has_cap(config):
            for part in _segments(_cap_points(config['center'], config['radius'])):
                ax.plot(part[:, 0], part[:, 1], color='#b54e38', linewidth=1.5, zorder=5)
            ax.scatter(*config['center'], s=31, marker='+', color='#b54e38', linewidths=1.5, zorder=6)
        centers = result['info'].get('centers', []) if layer == 'centers' or show_centers else []
        for center in centers:
            ax.scatter(center['lon'], center['lat'], s=17, color='#b08435',
                       edgecolors='#283845', linewidths=.25, zorder=5)
        anchor = result['point']
        ax.scatter(anchor['lon'], anchor['lat'], s=55, facecolor='white', edgecolor='#172b38',
                   linewidths=1.2, zorder=7)
        ax.set_xlim(-180, 180)
        ax.set_ylim(-90, 90)
        ax.set_xticks([-180, -90, 0, 90, 180])
        ax.set_yticks([-90, -45, 0, 45, 90])
        ax.grid(color='#96a9b4', linewidth=.35, alpha=.65)
        ax.tick_params(labelsize=8, colors='#465967', length=2)
        for spine in ax.spines.values():
            spine.set_color('#9aaeb9')
        method = _method_label(config)
        figure.text(left, .872, f'{"A" if index == 0 else "B"}  {method}', fontsize=10,
                    weight='semibold', color='#243b4a')
        figure.text(left, .845, _config_summary(config), fontsize=6.7, color='#526473')
        if layer == 'channel':
            channel = requests[index].get('channel', 0) if requests else 0
            channels = result['info'].get('channels', [])
            name = channels[channel].get('name', 'raw feature') if channel < len(channels) else 'raw feature'
            figure.text(left, .823, f'Raw channel i={channel}: {name}', fontsize=7.2, color='#344b59')
        if layer not in PLAIN:
            cax = figure.add_axes([left, .235, .42, .025])
            bar = figure.colorbar(image, cax=cax, orientation='horizontal')
            bar.ax.tick_params(labelsize=8, length=2, colors='#445866')
            bar.outline.set_edgecolor('#8498a4')
            label = 'Raw feature value' if layer == 'channel' else 'Cosine similarity' if layer == 'raw_similarity' else \
                'C(x) / r' if layer == 'energy' else 'Normalized subspace similarity' if layer == 'similarity' else 'Kernel amplitude'
            bar.set_label(label + (' | shared scale' if colors_locked else ' | individual scale'),
                          fontsize=8, color='#445866')
        else:
            note = 'No regional cap' if layer == 'region' and not _has_cap(config) else \
                'Cap boundary and construction center' if layer == 'region' else \
                f'{len(result["info"].get("centers", []))} construction centers'
            figure.text(left, .245, note, fontsize=8.5, color='#526473')
        info = result['info']
        figure.text(left, .09, f'{info["feature_count"]} raw features | rank {info["rank"]} | '
                    f'point ({anchor["lon"]:.2f}°, {anchor["lat"]:.2f}°)', fontsize=8, color='#526473')
        if any('Nyquist' in warning or '全部采为近零' in warning for warning in info.get('warnings', [])):
            figure.text(left, .066, 'Caution: display grid may alias this field; increase grid resolution.',
                        fontsize=7.2, color='#a14431')
    overlay_note = (' Red outline = nominal target cap.' if show_region else '') + \
                   (' Colored points = construction centers.' if show_centers else '')
    figure.text(.06, .043, 'Gray = undefined / uncomputed. White point = selected location.' + overlay_note,
                fontsize=7.5, color='#536674')
    figure.text(.06, .018, 'Fixed PE geometry; no predictive accuracy is implied.',
                fontsize=7.5, color='#536674')
    buffer = BytesIO()
    metadata = {'Software': 'GeoPEGlobe',
                'Description': json.dumps({'layer': layer, 'colors_locked': colors_locked,
                    'show_region': show_region, 'show_centers': show_centers,
                    'requests': requests if requests is not None else [
                        {'config': r['config'], 'anchor': {'lon': r['point']['lon'], 'lat': r['point']['lat']}}
                        for r in results]}, ensure_ascii=False, sort_keys=True)}
    figure.savefig(buffer, format='png', dpi=220, facecolor='white', metadata=metadata)
    return buffer.getvalue()
