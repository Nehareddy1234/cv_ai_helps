# Whole saved Bhadra AOI — original-resolution SAM ViT-H batches

**Paused for laptop transfer.** Start with
[CONTINUE_ON_ANOTHER_LAPTOP.md](CONTINUE_ON_ANOTHER_LAPTOP.md).
The authoritative partial GeoPackage includes the remaining queue. The saved
handoff counts and checksums are in `handoff_snapshot.json`. Do not resume on
both laptops. `--resume` is required to clear the saved pause flag.

**Resume confirmation (2026-10-15):** After reviewing the original pixel grid and tile settings, the user confirmed continuing the same method across the rest of the saved AOI. Preserve the cyan/green/brown grouping AND individual object boundaries. The first new batch was inspected against source imagery and is accepted only as a provisional output: 39.15% uncertain remains explicitly flagged, not reinterpreted as confident identification. Compare `preview_combined.png` with the reference; `preview.png`, when present, is the eight-class diagnostic view. Run `check_reference_fidelity.py` to verify seed pixel labels, grid alignment and SAM tile settings. This audit does not establish semantic accuracy. Continue the queue with existing quality gates; never approve on geometry alone.

This is the replacement for the rejected coarse whole-region run. It covers the **entire saved project AOI** (1107.328657 km²), not an independently verified official reserve boundary. All 1,860 remaining batch cores are planned in advance. The accepted 0.900873 km² rectangle is retained unchanged as the seed.

## Method and limitations

- Live Esri World Imagery only; preferred zoom 19, explicit fallback to zoom 18 (~0.58 m ground sampling here) if Esri reports missing tiles. No fallback below 18 is allowed. Imagery is resampled to the original rectangle's ~0.484993 m UTM 43N pixel grid. Each batch records its actual native zoom; resampling does not create additional detail or guarantee accuracy or age. The first batch's zoom-19 placeholders were caught during visual inspection and excluded before inference.
- Original SAM ViT-H checkpoint and automatic-mask settings, six overlapping 1024×768 windows plus a global pass per 2660×1446 image. 128-pixel halos provide context; each batch publishes only its disjoint AOI core. Objects can be split at core boundaries.
- Original 16-feature RGB/texture/road-context random forest and region rules. Original scene-specific numbered review overrides are **not** copied to unrelated areas. Accepted footprints and reviewed polygons apply only at their actual geographic locations.
- Eight classes: water; trees/dense woody vegetation; crops/grass/low vegetation; bare soil/rock/sparse ground; roofs/buildings; industrial/engineered structures; roads/tracks/paved surfaces; uncertain.
- Industrial structures are not learned by this scene classifier. Outside reviewed references, industrial/road/roof identification needs additional spatial evidence or review; uncertain remains explicit. The seed classifier's generalization over the whole AOI is not independently validated.
- SAM boundaries and image-edge gap completion remain separately identified by `origin`. Complete geometric coverage is **not** a claim that all pixels were segmented by SAM, or that every class is semantically correct.

## Outputs

`output/bhadra_highres_classification.gpkg` contains `classified_regions`, the saved `bhadra_boundary`, the complete `batch_grid`, and the `run_jobs` status table. It starts with the accepted seed and grows only when a batch passes checks. `class_id` preserves eight categories; `combined_id` gives the previously requested combined display (1 = water/trees/buildings/industrial/roads/uncertain; 3 = low vegetation; 4 = open ground). Corresponding QML styles are beside the GeoPackage.

`progress.json` is the coverage report. **Do not call the AOI complete until `whole_aoi_complete` is true and `output/final_verification.json` passes.** Geometry validity, gaps, overlaps, raster coverage, unique IDs, and the spatial index are checked. These do not replace semantic review.

## Run / resume

From this directory with the existing Python environment:

```powershell
python -m unittest test_pipeline -v
.\start_worker.ps1
python worker.py status
```

The hidden single worker continues pending batches until finished, stopped, an error occurs, a review gate is reached, or free space falls below 8 GiB. Keep the computer awake. A reboot/sleep interrupts computation; relaunching resumes cached stages. No OS startup job or power-setting change is installed.

The **first new batch** always stops for visual review. Batches with >75% uncertain area or >65% gap completion also stop for review. Inspect `batches/<id>/preview.png`, actual source imagery, and `verification.json`; never auto-approve solely because geometric checks passed.

```powershell
python worker.py approve --batch-id BATCH_ID --review-note "Specific observations from actual source/result inspection"
.\start_worker.ps1
```

After diagnosing and fixing a failure, `python worker.py retry --batch-id BATCH_ID` requeues an error/blocked batch. To stop gracefully between batches, create `control.json` with `{"stop_requested": true}`; remove that request before resuming. The OS file lock prevents concurrent workers. Publication is transactional and idempotent per batch. Source/checkpoint hashes guard against mixing workflows.

After verified publication, only that batch's regenerable SAM-mask and raw XYZ caches are removed. Georeferenced imagery, staged results, previews and audit reports are retained. Storage may need expansion for the whole run; the worker pauses instead of deleting evidence or reducing detail.

At five minutes per SAM pass, inference alone is roughly 45 continuous CPU-days for this queue. This is a planning estimate, not a completion promise; the first real batch supplies measured timings. Automated follow-ups can inspect/restart this local worker only while the app and computer are running.
