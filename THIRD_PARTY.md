# Third-party software and data

The browser assets are served locally. Their original license files are retained beside the assets.

| Asset | Version | License | Source |
| --- | --- | --- | --- |
| [three.js](https://github.com/mrdoob/three.js) | 0.180.0 | [MIT](geope_globe/web/vendor/three/LICENSE) | [Pinned commit](https://github.com/mrdoob/three.js/commit/0af9729d0c143a86a1d725d6e2c3ad83301f3f34) |
| [world-atlas](https://github.com/topojson/world-atlas) | 2.0.2 | [ISC](geope_globe/web/vendor/world-atlas/LICENSE) | [Pinned commit](https://github.com/topojson/world-atlas/commit/a912c0a22c3fbd1979cb6defdd6389d8c35e7c2a) |
| [topojson-client](https://github.com/topojson/topojson-client) | 3.1.0 | [ISC](geope_globe/web/vendor/topojson-client/LICENSE) | [Pinned commit](https://github.com/topojson/topojson-client/commit/71e5bd6428fd8b7a40fa980d2ef7862140851f03) |

The 110m land outlines in world-atlas derive from [Natural Earth](https://www.naturalearthdata.com/about/terms-of-use/), whose map data are public domain. They are generalized visual context, not precise boundaries.

Numerical dependencies (NumPy, SciPy, PySHTOOLS and Matplotlib) are installed through `requirements.txt`; their source code is not copied here. The fixed encoder formula adapters were independently implemented against a [pinned TorchSpatial revision](https://github.com/seai-lab/TorchSpatial/tree/ac7dbcf5694dc99cce136b17fa0c26964d7ee0de). Upstream source files are not bundled; see [source metadata](docs/torchspatial_sources.json) for the checked files and adaptations. These adapters do not include learned networks or training.

Package metadata and vendored asset hashes are recorded in [docs](docs/).
