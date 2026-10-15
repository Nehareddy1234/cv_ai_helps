# Industrial buildings and structures addition

The reviewed Esri/SamGeo baseline checkpoint is in the user-designated repository
`Nehareddy1234/cv_ai_helps`, branch `master`, commit `fff3e34`, in
`samgeo_esri_test`. This snapshot is the baseline **before** the industrial
addition. An earlier mistaken push to `ManimeghanathA/HELPS`, branch
`Neha_branch`, commit `d97db48`, was reverted at the user's request by commit
`f28d926` on 2026-10-15. The unrelated `lulc_methods` folders were not staged.

This addition targets the industrial area in the supplied screenshot, within the already georeferenced test image. The three circular objects are classified as **Buildings / industrial structures**, with a separate **Circular tank / treatment unit** subtype. They are not asserted to be roofed buildings. Roofed buildings and rectangular process structures have separate subtype values; all interpretations are based on imagery, not field verification.

`segment_industrial.py` crops the aligned Esri raster, runs SAM ViT-H using recorded point and box prompts, and writes candidate masks, vectors, prompts and a preview. A connected-component check retains the component selected by each positive point. Output geometry is produced from SAM pixels, not manually drawn circles or bounding-box rectangles.

`integrate_industrial.py` includes only explicitly reviewed candidates. Existing accepted building footprints are preserved; already represented candidates are skipped and remaining additions are clipped against existing buildings. The updated land-cover polygons have these industrial footprints subtracted so a structure cannot also be labelled open ground, trees or water. The original class GeoPackage and original full-Bhadra building dataset are not overwritten.

## Files

- `Bhadra_Esri_Industrial_Test.qgz`: updated QGIS review project, retaining live Esri XYZ imagery.
- `output/reviewed_with_industrial.gpkg`: `industrial_structures`, `reviewed_classes`, and `buildings_reference` layers.
- `output/industrial_structures.qml`: red structure styling.
- `output/reviewed_classes_with_industrial.tif`: combined class raster; code 5 is buildings / industrial structures, including reference buildings in this test footprint.
- `output/industrial_prompts.json`: crop location, prompt coordinates and SAM scores (not class probabilities).
- `output/industrial_review.json`: accepted/duplicate objects, geometry checks and checksum of the untouched original building dataset.
- `output/industrial_reviewed_preview.png`: source versus updated classification.

Run `python segment_industrial.py`, inspect `output/industrial_candidates_preview.png`, and only then update `ACCEPTED` in `integrate_industrial.py` and run it. Do not infer semantic certainty from the SAM score. This is still the small partial test, not a new classification of the complete Bhadra AOI.
