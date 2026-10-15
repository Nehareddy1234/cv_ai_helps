# Current Esri / SAM ViT-H result

Updated 2026-10-15 for `Nehareddy1234/cv_ai_helps`, branch `master`.
Open **Bhadra_Esri_SAM_ViT_H_Current.qgz**. It contains exactly two layers:
the current combined result and live Esri World Imagery. The GeoPackage path
is relative to this folder; Esri tiles require an internet connection.

## Current result

`output/combined_classes_with_uncertain` contains the GeoPackage, raster,
QML style and verification report. Water, trees/dense woody vegetation,
buildings/roofs, industrial/engineered structures, roads and uncertain regions
share one cyan category (2,176 original regions). Crops/grass and bare ground
remain separate categories in the same layer. The result has three dissolved
multipart category features; `reclassified_regions` retains all 2,634 original
segments and their source labels. Including uncertain regions does not validate
their interpretation. No gaps were filled and no outer hull was added by merging.

```powershell
python combine_selected_classes.py --include-uncertain
python verify_current_snapshot.py
```

The original classified data remain in `output/full_classification` to reproduce
the merge. The aligned image, original partition, reviewed footprint GeoPackage,
SAM tile caches, model/training evidence and relevant verification reports remain
as inputs and provenance. The full rectangle is the saved small test area, not
the whole Bhadra AOI. Segmentation uses SAM ViT-H plus image-edge gap completion
and geometric post-processing; classification uses RGB/texture evidence and
reviewed objects. This is not field-validated mapping or entirely raw SAM output.

## Cleanup scope and recovery

55 superseded project snapshots, early experiment scripts/data, and generated
previews were removed from the tracked snapshot. They remain on the local disk
and in commit `903b93f`; `.gitignore` lists their exact paths. No repository-wide
plugin files or unrelated Bhadra work were removed. No history was rewritten.
Earlier method stages can be inspected at `903b93f`, including industrial and
reviewed-test methods; current documentation describes the retained stages.

The cached composition and classification stages can run from this folder.
Fresh SAM inference still requires the checkpoint at the path configured in
`segment_full_rectangle.py`. `verify_full_rectangle.py` additionally checks the
original accepted-building dataset in the original sibling-folder layout; this
external provenance check is not required to open or verify the current snapshot.
Use `verify_full_classification.py` to check the included classified source and
`verify_current_snapshot.py` to check the portable current result/project.

The separate working folder `HELPS/latest try` and its older outputs were not
deleted. The mistaken historical commit in `ManimeghanathA/HELPS`, `Neha_branch`,
was already reverted; this commit belongs only to `cv_ai_helps`.
