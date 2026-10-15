# Full saved Esri rectangle: unlabeled segmentation

This workflow partitions the saved test rectangle only, not the full Bhadra AOI.
The user confirmed the rectangle containing the dam, industrial site and adjacent
fields. No land-cover classes are assigned.

## Reproduce

Run from this directory with the existing Python environment:

```powershell
python -u segment_full_rectangle.py
python -u compose_full_rectangle.py
```

The first script runs SamGeo's automatic ViT-H mask generator on six overlapping
tiles. It caches each completed tile in `output/full_rectangle`. The existing
aligned full-image SAM masks supply larger-scale proposals. Internal tile-edge
masks are excluded, near-duplicates are filtered, and smaller proposals take
precedence over larger ones to create a non-overlapping partition. Accepted
building and industrial footprints are preserved as regions without class labels.
Small connected non-footprint remnants below 40 pixels are merged into substantial
touching regions by longest shared boundary. Preserved footprints are excluded
from both sides of this cleanup, so they cannot grow or shrink. This cleanup is
geometric post-processing, not a model prediction.

SAM proposals are not exhaustive. Image-edge graph segmentation (Felzenszwalb)
completes uncovered pixels. This is conventional post-processing, not a SAM
prediction. The vector `origin` attribute distinguishes `SAM automatic`,
`Preserved footprint`, and `Edge-based gap completion`. The completion fraction
is reported in `coverage_report.json`.

## Outputs and checks

- `unlabelled_regions.gpkg`: unique region polygons and test extent, EPSG:32643.
- `unlabelled_regions.tif`: integer region IDs, not class IDs.
- `unlabelled_regions.qml`: transparent polygons with pale yellow boundaries.
- `coverage_report.json`: coverage, overlap, validity, and provenance statistics.
- `verification.json`: independent saved-vector/raster and footprint checks,
  produced by `python verify_full_rectangle.py`.
- `unlabelled_overview.png` and `unlabelled_detail.png`: image-aligned previews.

The two-pixel layout-frame border is excluded. The source samples are about
0.485 m apart; this is pixel spacing, not a claim of imagery accuracy. Checks
require unique IDs, valid geometries, complete coverage of the inner rectangle,
and no overlaps or features outside it (0.01 square metre numerical tolerance).
Complete coverage does not mean every physical object is correctly delineated:
shadows, textures, adjacent objects, and ambiguous edges still need visual review.
No automatic semantic interpretation should be inferred from a region ID.

Previous classified/industrial files are retained. The new QGIS project is saved
separately as `Bhadra_Esri_Unlabelled_Segments.qgz` once the outputs pass review.
