# Bhadra Esri / SamGeo boundary review

This is a **partial, visually interpreted test**, not a completed whole-Bhadra land-cover product. Unclassified areas are intentionally transparent. The original building layer is preserved. No Sentinel imagery is used.

## Open in QGIS

Open `Bhadra_Esri_Reviewed_Test.qgz` in this folder. The live Esri World Imagery XYZ basemap is underneath the reviewed classes. Blue is water, green is woody vegetation, light green is cultivated fields/plantations, and brown is open ground/sparse cover. Existing buildings remain red. Older results are retained in a hidden group; do not interpret them as the corrected result.

Primary vectors: `output/reviewed_test_classes.gpkg`, layer `reviewed_classes`. The `buildings_reference` layer is a clipped reference copy for offline checking, not a replacement for the accepted original buildings. Style: `output/reviewed_test_classes.qml`.

## What was corrected

The previous layout PNG crop was assigned the live canvas extent instead of the layout map extent. This produced an approximately 1.8x scale mismatch plus an offset. The reconstruction uses the saved layout frame, extent, 300 DPI and original crop offsets. RGB pixels are unchanged. CRS is EPSG:32643; sampling is approximately 0.485 m per pixel, not a claim of native imagery accuracy.

The test covers the saved layout footprint, approximately 1.29 km by 0.70 km around the dam, river reaches, treatment plant and adjacent fields. It does not cover every location in the user's earlier screenshots. The final water-growth search corridor is recorded in the review JSON; it prevents propagation from reservoir pixels onto blue-gray dam faces. It is a search constraint, not a manually drawn shoreline.

SAM automatic output contained 73 segment IDs, split into 557 polygon fragments. These were segmentation proposals, not semantic classes. Scene-specific visual interpretation assigns selected IDs to classes; small or ambiguous masks are excluded. Point-prompted SamGeo supplements water proposals. SAM-derived water seeds expand only through connected RGB water-like pixels with reviewed land masks as barriers. This is explicit post-processing, not another segmentation model. Islands are not filled as holes. Minor fragments below about 20–24 square metres are removed, and accepted building footprints are subtracted from final vectors exactly.

## Reproduction and review

Use the existing Python environment with SamGeo, torch, rasterio, geopandas, scipy, scikit-image and matplotlib. The local SAM ViT-H checkpoint is in `../samgeo/weights/`.

1. `python refine_test_area.py` reconstructs the original saved render and SAM-mask coordinates. Keep `Visible_Esri_SamGeo_Test.qgz` and original inputs as the audit baseline.
2. `python prompt_water.py` runs SAM with the recorded visual prompts on the corrected image (CPU; several minutes).
   `python prompt_land.py` and `python preview_land_prompts.py` generate additional soil/canopy candidates and their visual audit. The central soil and lower-left canopy candidates were accepted after visual review. The settlement candidate selected roofs, and the riverbank candidate selected mixed surfaces; both were rejected. Inclusion is explicit in `REVIEWED_LAND_PROMPTS`, not automatic from SAM score.
3. `python classify_reviewed_segments.py` writes the reviewed vectors, class raster, QGIS style, report and preview.
4. `python verify_reviewed_test.py` checks geometry, source pixels and handpicked shoreline regression points.

`segment_visible_esri.py` can produce a fresh automatic run in separate `sam_rerun_unreviewed` outputs. New mask IDs MUST be reviewed again; the current ID-to-class table must not be applied to another image or run without checking.

## Limits

This is not field-validated classification and the SAM scores are not class probabilities. Mixed dry vegetation/soil, shadows and unrecognized structures remain uncertain; much of the test footprint is still unclassified. Cultivated plantations can contain trees, so the legend describes land-use patches rather than botanical identity. No new road classification is claimed. Geometric validity and selected sample checks do not establish thematic accuracy. Review this small test before approving any expansion to the full AOI.

See `output/classification_review.json`, `output/verification.json`, `output/alignment_audit.json`, `output/water_prompts.json` and `output/reviewed_test_preview.png` for the audit trail. All old datasets remain on disk.
