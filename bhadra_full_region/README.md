# Whole-Bhadra SAM ViT-H classification

**REJECTED COARSE EXPERIMENT — AUDIT ONLY.** This is not the current run.
For original-resolution continuation, use
`../bhadra_highres_batches/CONTINUE_ON_ANOTHER_LAPTOP.md` and its partial GeoPackage.
The coverage checks below do not make this coarse result an accepted substitute.

This folder uses the original saved Bhadra project boundary (about 1,107 km²)
and Esri World Imagery. It does not redefine or independently validate an official
reserve boundary. The input files were recovered from the local cleanup archive;
no Sentinel imagery is used.

## Verified run result — 2026-10-15

The GeoPackage contains 8,132 regions across the saved 1,107.33 km² AOI.
All 12 SAM ViT-H tile passes and the whole-image context pass completed.
After rejecting unsuitable masks, 77.69% of AOI pixels required image-edge gap
completion. This is therefore a **hybrid result, not a pure SAM map**. The `origin`
field identifies 510 SAM-derived regions, 7,621 gap-completion regions, and one
region without valid imagery. About 39.47% of the area is uncertain after the
conservative cloud-proximity review. No independent accuracy claim is made.

Saved geometry validity, full AOI coverage, absence of overlaps, interior-point
coordinates and raster/vector consistency passed. The separate QGIS project was
saved and reopened with two valid layers. Class colors are embedded in the
GeoPackage. These checks do not establish semantic accuracy.

## Resolution and meaning

The existing Esri source is 2,304 × 3,328 pixels, with 19.109 m spacing in
EPSG:3857 (roughly 18.6 m on the ground at this latitude). This is a broad-cover
map, not the detailed roof/road delineation in the sub-metre test image.

SAM ViT-H runs on 12 overlapping, AOI-intersecting 1,024-pixel image tiles,
plus a whole-image context pass resized to a 1,024-pixel long edge to capture
large forest/water regions spanning tile boundaries. Context masks are returned
to the native grid by nearest-neighbour resampling; tile masks supply finer detail.
The context pass has roughly 62 m Mercator sampling, so broad context-only edges
are coarser than the native 19 m tile edges. Regridding does not add spatial detail.
The checkpoint is `../weights/sam_vit_h_4b8939.pth`. Proposals are composed into
non-overlapping regions; uncovered pixels are filled using conventional
image-edge segmentation and are explicitly identified by the `origin` field.
No output should be described as exclusively raw SAM masks.

SAM does not supply land-cover names. A separate scene-trained random forest
labels broad water, woody vegetation, low vegetation and bare-ground regions.
Training labels from the previous test rectangle are averaged onto the actual
whole-region pixel grid; only pixels with at least 75% class purity are used.
Colour-only features avoid transferring sub-metre texture and road-distance
rules to this coarse scene. Weak or conflicting evidence becomes uncertain.

All labels need review. Training comes from one small scene; the recorded
spatial-block agreement is not independent field accuracy. Trees versus low
vegetation, shadows versus water, and soil versus sparse dry vegetation may
still be confused. Roofs, industrial structures and narrow roads are not claimed
as reliably detected classes at this resolution.

Visible clouds occur in the southern imagery. Bright neutral patches and nearby
dark shadows trigger conservative uncertainty flags. This RGB-only check can
also flag pale soil/concrete and is not a validated cloud/shadow mask.
The final water review additionally flags water-like regions with more than 10%
of their pixels within 150 source pixels (about 2.9 km Mercator) of a bright
neutral patch. This addresses displaced cloud shadows conservatively; genuine
water near bright surfaces may also become uncertain. Original class suggestions
and the pre-review class are retained for inspection. `classify_bhadra.py` runs
this final check automatically through `finalize_cloud_review.py`.

## Run

```powershell
python segment_bhadra.py
python classify_bhadra.py
```

The first stage resumes completed tiles from `cache/`. `progress.json` describes
the last completed stage, not a background schedule. `cache/manifest.json`
records input hashes, tile windows and SAM settings.

## GeoPackage

After successful completion, `output/bhadra_sam_vit_h_classification.gpkg` contains:

- `classified_regions`: individual regions with broad class, SAM provenance,
  model/vote evidence, review flags, square-metre area and interior latitude/longitude.
- `combined_regions`: the same regions with water/woody vegetation/uncertain
  merged into the combined class, retaining original labels in source fields.
- `open_ground`: a subset of class-4 regions, including their coordinates.
- `bhadra_boundary`: the exact saved AOI.

These layers are alternative views/subsets, not additional independent areas.
Do not sum areas across them. Geometries are stored in EPSG:3857; `area_m2` is
computed in UTM EPSG:32643. Latitude/longitude fields are WGS84 EPSG:4326 and
identify an interior point, not polygon corners. Full boundaries are the geometry.

Verification checks saved geometry validity, AOI coverage, no overlaps/outside
geometry, and vector/raster agreement. Those checks establish geometric
consistency, not classification accuracy. See `output/verification.json`.

The saved test project and all its data remain unchanged. No Excel is needed.

After verification, `create_qgis_project.py` can be run with the installed QGIS
Python runtime. It embeds class styles into the GeoPackage and writes the separate
`Bhadra_Whole_Region_SAM_ViT_H.qgz` project with relative paths. It does not alter
the currently open QGIS project. Keep the data and output folders beside it.
