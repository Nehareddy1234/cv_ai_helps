# Current Esri/SamGeo test snapshot

Updated on 2026-10-15 from `HELPS/latest try`. This folder includes the reviewed
classification, industrial additions, and full saved test rectangle partitioned
into **2,634 unlabeled regions**. Scripts, input imagery, cached SAM tile masks,
vectors, rasters, styles, previews, verification reports and QGIS projects are
included. Model weights, Python caches and provisional previews are excluded.
The destination is `Nehareddy1234/cv_ai_helps`, branch `master`. GeoTIFFs contain
actual raster data, not Git LFS pointer files.

The pre-industrial baseline remains available in commit `fff3e34`. The mistaken
copy in `ManimeghanathA/HELPS` (`Neha_branch`, `d97db48`) was reverted by `f28d926`
at the user's request; no history was rewritten.

The working folder remains `HELPS/latest try`; this is its Git snapshot. Scripts
retain their working-layout paths to sibling `samgeo` and `Codes` datasets and
the local SAM checkpoint. Original QGIS project snapshots also retain external
layer references. They are audit snapshots, not standalone installations.
For reproduction with unchanged scripts, use the original sibling-folder layout
described in the method READMEs. Cached full-rectangle masks are included so the
composition step does not require running the model again.

## Inspect the current result independently of external project paths

In QGIS, load `data/esri_test_aligned.tif`, then
`output/full_rectangle/unlabelled_regions.gpkg`, layer `regions`, and apply
`output/full_rectangle/unlabelled_regions.qml`. These files are self-contained.
The saved `Bhadra_Esri_Unlabelled_Segments.qgz` records the working live-Esri view.

The partition covers the entire inner test rectangle with no overlaps and no
semantic classes. SAM ViT-H proposals and accepted footprints are combined;
approximately 26% of pixels initially require image-edge gap completion, followed
by small-fragment cleanup. The `origin` field identifies provenance. This is
SAM-based post-processed segmentation, not entirely raw SAM output or proof of
perfect physical-object boundaries.

For industrial additions, use `output/reviewed_with_industrial.gpkg` and
`README_INDUSTRIAL.md`. The original reviewed result remains at
`output/reviewed_test_classes.gpkg` with its corresponding QML style.

See `README_FULL_RECTANGLE.md`, `README_INDUSTRIAL.md`, and
`README_REVIEWED_TEST.md` for methods and limitations. Verification results are
in `output/full_rectangle/verification.json` and `coverage_report.json`. This is
the saved small test rectangle, not the full Bhadra AOI or field-validated mapping.
