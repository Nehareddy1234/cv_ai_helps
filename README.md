# Bhadra Esri — current SAM ViT-H work

This repository contains the saved Esri test rectangle and the whole-region
Bhadra SAM ViT-H workflow from October 14–15, 2026. It is no longer a QGIS plugin
source checkout. The workflows are kept in separate folders.

## Current whole-region workflow — high-resolution batches

Use **[the laptop resume instructions](bhadra_highres_batches/CONTINUE_ON_ANOTHER_LAPTOP.md)**.
The current result is `bhadra_highres_batches/output/bhadra_highres_classification.gpkg`.
It is **PARTIAL / provisional**, preserves the accepted seed, and continues a
1,860-batch queue at the original ~0.485 m output grid with SAM ViT-H.
The transfer-time GeoJSON is `bhadra_highres_batches/output/classified_regions_PARTIAL.geojson`.
Open `bhadra_highres_batches/Bhadra_Resume_PARTIAL.qgs` in QGIS on the new laptop.

## Rejected coarse whole-region experiment — audit only

See [bhadra_full_region/README.md](bhadra_full_region/README.md) for processing,
verification and limitations. Its GeoPackage target is
`bhadra_full_region/output/bhadra_sam_vit_h_classification.gpkg`; the separate QGIS
project is `bhadra_full_region/Bhadra_Whole_Region_SAM_ViT_H.qgz`.

This uses the original saved AOI and approximately 19 m Esri imagery. It was
rejected for insufficient detail; do not use it to resume the current run.
Only the required Esri image and AOI were recovered from the cleanup archive;
the old experiments remain archived. No Sentinel imagery is used.

## Saved high-resolution test project

**[Bhadra_Esri_SAM_ViT_H_Current.qgz](samgeo_esri_test/Bhadra_Esri_SAM_ViT_H_Current.qgz)**

Open it in QGIS. It has only the current combined result and Esri World Imagery.
The result uses relative paths; keep the project inside `samgeo_esri_test`.
Live Esri tiles require internet. For offline imagery, add the included
`samgeo_esri_test/data/esri_test_aligned.tif`.

The cyan class combines water, trees/dense woody vegetation, buildings/roofs,
industrial/engineered structures, roads, and uncertain regions: 2,176 source
regions. Crops/grass and bare ground remain separate. The GeoPackage also retains
all 2,634 original segment geometries and source labels for audit.

## What to keep

- `samgeo_esri_test/`: current project, scripts, source imagery, cached SAM masks,
  classification evidence, current results and verification reports.
- `bhadra_full_region/`: separate whole-AOI Esri source, SAM ViT-H workflow,
  rejected coarse outputs and verification, preserved for audit only.
- `bhadra_highres_batches/`: current detailed batch workflow, paused checkpoint,
  GeoPackage, GeoJSON, source evidence, review previews and migration instructions.
- `weights/`: local SAM ViT-H checkpoint, excluded from Git because of its size.
- `requirements.txt`: versions used in the local Python 3.11 environment.
- `LICENSE`: retained original repository license notice.

## Verify or reproduce

Using the existing Python environment, from `samgeo_esri_test`:

```powershell
python verify_current_snapshot.py
python verify_full_classification.py
python verify_full_rectangle.py
```

To regenerate the latest combined result:

```powershell
python combine_selected_classes.py --include-uncertain
```

For earlier stages, see `README_FULL_RECTANGLE.md` and
`README_FULL_CLASSIFICATION.md` in that folder. Cached masks are included;
a fresh SAM run uses `weights/sam_vit_h_4b8939.pth` at repository root, or the
path in `SAM_CHECKPOINT`. SAM installation can require platform-specific
geospatial dependencies; no environment was reinstalled during cleanup.

SAM ViT-H proposals are combined with accepted footprints, image-edge gap filling,
and geometric post-processing. Classification uses image evidence and reviewed
objects. These are provisional interpretations, not field-validated mapping.
Including uncertain regions in the cyan category does not make them confirmed.

## Cleanup and recovery

Old full-Bhadra experiments, plugin source, debug helpers, alternative-method
experiments, old projects and redundant previews have been removed from this
repository and its active local folder. Git history is unchanged. Required
source datasets were retained inside `samgeo_esri_test`.

Before local removal, all 263 archived files (including uncommitted work and
the previous README) were SHA-256 verified in this recovery archive:

`C:/Users/Nehar/Desktop/HELPS/cleanup-backups/cv_ai_helps-legacy-20261015.zip`

The archive is outside the repository and is not uploaded. The separate
`HELPS/latest try` working folder and `Codes` / `ViT` folders were not cleaned.
