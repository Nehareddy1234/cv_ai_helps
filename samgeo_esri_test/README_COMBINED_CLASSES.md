# Combined selected features

The current tracked version includes uncertain regions. Open
`Bhadra_Esri_SAM_ViT_H_Current.qgz` and see the final section below.
The earlier variant described first is reproducible but its outputs/project
are not included in this cleaned Git snapshot.

Water (1), trees/dense woody vegetation (2), buildings/roofs (5), industrial and
engineered structures (6), and roads/tracks/paved surfaces (7) are merged into
one category: **Combined selected features** (new code 1, cyan).

Crops/grass/low vegetation (3), bare soil/rock/sparse ground (4), and uncertain
regions (8) remain separate. Dense forest is represented by the existing woody
vegetation class; no new forest or industrial-site extent has been inferred.

Run `python combine_selected_classes.py` to reproduce. Results:

- `output/combined_classes/combined_classes.gpkg`, layer `combined_classes`:
  dissolved multipart geometries, one feature per remaining category.
- Layer `combined_selected_only`: only the single combined category.
- Layer `reclassified_regions`: all original segment boundaries and attributes,
  with `source_class_id` and `source_class_name` retaining the old labels.
- `combined_classes.qml`: categorical QGIS styling.
- `combined_classes.tif`: remapped raster codes; zero remains outside the extent.
- `verification.json`: exact union/coverage, no-overlap, raster/vector agreement,
  and unchanged source checks.

Merging does not improve classification accuracy. No gaps are filled and no
outer hull or buffer is added. Original class probabilities/evidence attributes
refer to the source interpretation, not the combined category.

The original classified project is preserved. The new QGIS project is saved as
`Bhadra_Esri_Combined_Classes.qgz`, displaying the merged result over Esri imagery.

## Current version including uncertain regions

Run `python combine_selected_classes.py --include-uncertain` to include class 8
in the cyan combined class. This writes `output/combined_classes_with_uncertain`
without replacing the previous version. Only crops/grass (3) and bare ground (4)
remain separate. The merged class contains 2,176 source regions, including 1,405
uncertain regions; their inclusion is not a confirmation of their classification.

`Bhadra_Esri_SAM_ViT_H_Current.qgz` contains only this current result and Esri.
Older layers are removed from that project's layer list, not deleted from disk.
The result is SAM ViT-H-derived with image-edge gap filling and classification
post-processing, not a new pure SAM inference run.
