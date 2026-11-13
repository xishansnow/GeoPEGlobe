# GeoPEGlobe

An interactive globe for exploring **fixed geographic location encoders**. Pick any point on either globe and compare its raw positional encoding (PE), nearby and global cosine similarity, feature organization, common spherical harmonic spectrum, and coordinate chart behavior. A/B views share the selected location.

中文：这是一个本地运行的地理位置编码器可视化工作台。点击地球任意位置，可同时查看 A/B 两种编码在该点的原始特征、邻域和全球余弦相似度、共同球谐频谱，以及极点和日界线的坐标表现。工具只分析固定前端的表示几何，不训练预测模型。

## Start locally

Requires Python 3.12, a browser with WebGL 2, and Node.js only if you want to run the frontend tests. Run the following commands from the repository root.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m geope_globe.server
```

Open <http://127.0.0.1:8876>. To choose another port, pass `--port 8877`. The service binds to localhost by default and serves the numerical API and bundled browser assets without a map service or CDN.

## Encoders

- Regional Slepian with optional low-degree global real spherical harmonics; global real spherical harmonics; Cartesian unit-sphere xyz.
- TorchSpatial-style fixed PE formula adapters: wrap, Space2Vec grid and theory, NeRF, RFF, RBF, Sphere2Vec sphereC, sphereC+, sphereM, sphereM+, and DFS.

Controls include Slepian cap center, radius, bandlimit and mode selection; method-specific scales and frequencies; RBF center layout; random seed; and a shared globe grid. The app does **not** train models, use task labels, or rank predictive accuracy. Several formula adapters intentionally differ from upstream training systems; see [source and adaptation notes](docs/torchspatial_sources.json).

## Reading the views

1. **Encoder organization:** inspect native feature groups and centers. The optional cap outline is a *construction region*, not a hard support mask.
2. **PE at this point:** inspect signed raw feature values and numerical diagnostics.
3. **Local change:** compare raw PE cosine similarity on a fine geodesic neighborhood and distance bands around the selected point.
4. **Similar locations:** see global similarity on the two globes and a route-distance profile. Cosine similarity is `φ(x)·φ(x₀)/(|φ(x)||φ(x₀)|)`; it can be negative and is undefined when either vector has zero norm.

The right rail shows the common spherical harmonic spectrum and fixed pole/date-line coordinate checks. Those panels describe an encoder configuration and do not move with the selected point. The common spectrum of non-bandlimited encoders is truncated and reports its unaccounted tail. The raw PE and globally normalized subspace quantities answer different questions; their values are not directly interchangeable.

Export the current workspace to JSON or a PNG. The light PNG option renders a full-sphere equirectangular map; the dark option captures the current globe view. The JSON includes the configuration, camera, last request, and summary diagnostics; it does not embed full numerical fields.

## API and checks

- `GET /api/health`: readiness.
- `GET /api/catalog`: method defaults and bounds.
- `POST /api/evaluate`: numerical fields for one encoder, point, grid and band.
- `POST /api/export/figure`: two-panel light PNG from two evaluation requests.

Example:

```bash
curl -s http://127.0.0.1:8876/api/evaluate \
  -H 'Content-Type: application/json' \
  -d '{"config":{"encoder":"xyz"},"anchor":{"lon":110,"lat":35},"grid":{"nlat":16,"nlon":32}}'
```

Tests, after installing `pytest`:

```bash
python -m pytest -q geope_globe/tests
node --test geope_globe/tests/*.test.mjs
```

## License and sources

GeoPEGlobe's original code is MIT licensed. See [LICENSE](LICENSE) and [THIRD_PARTY.md](THIRD_PARTY.md) for bundled software, data, pinned versions, and separate licenses.
