# Continue the Bhadra SAM ViT-H run on another laptop

This is the **current high-resolution workflow**, paused for transfer on 15 October 2026.
It is NOT the rejected 19 m whole-region experiment in `bhadra_full_region`.
The whole AOI is not finished. See `handoff_snapshot.json` for the exact saved
batch count and coverage. The queue has 1,860 batches plus the preserved seed.

## 1. Get the saved work

Install Git and Python **3.11, 64-bit** on the destination Windows laptop.
In PowerShell, in a folder with enough space:

```powershell
git clone --branch master https://github.com/Nehareddy1234/cv_ai_helps.git
cd cv_ai_helps
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
```

If activation is blocked, use `.\.venv\Scripts\python.exe` instead of `python`
for commands from the repository root, or `..\.venv\Scripts\python.exe`
from inside `bhadra_highres_batches`. No system-wide policy change is required.
The repository may be cloned under any username/path; manifest references are
relative to the repository root. Keep all folders together.

The old laptop's worker and automated follow-up must remain stopped. Never run
two copies against a shared/live GeoPackage, and do not sync the database while
a worker is writing. Git transfers a stopped checkpoint, not a live shared queue.

## 2. Install the computation environment

For **CPU / AMD Radeon 610M**, the source laptop used this PyTorch pair:

```powershell
python -m pip install torch==2.13.0 torchvision==0.28.0 --index-url https://download.pytorch.org/whl/cpu
python -m pip install -r bhadra_highres_batches/requirements-resume.txt
python -m pip check
python -c "import torch; from samgeo import SamGeo; print(torch.__version__, 'CUDA:', torch.cuda.is_available())"
```

For a supported **NVIDIA GPU**, install a matching CUDA-enabled PyTorch and
TorchVision pair using the [official PyTorch installer](https://pytorch.org/get-started/locally/),
then install `requirements-resume.txt`. Confirm `torch.cuda.is_available()` is
`True` before using `--device cuda`. Do not install the CPU-only pair afterward.
`--device auto` chooses CUDA when available, otherwise CPU; it does not enable
an unsupported AMD GPU. CUDA execution has not been benchmarked on this laptop.

These pins record the source environment, not a claim that a clean environment
has been tested on your destination hardware. If a wheel/version is unavailable
or dependency validation fails, stop and resolve it; do not silently change the
classifier's scikit-learn version, use SAM 2, or substitute ViT-B/L. Only load the
trusted project model/checkpoint. QGIS's Python is not needed for the worker.
The imagery downloader uses Rasterio, avoiding the earlier standalone GDAL export issue.

## 3. Supply the exact SAM ViT-H checkpoint

The approximately 2.4 GB checkpoint is excluded from Git. Either copy
`weights/sam_vit_h_4b8939.pth` from the old laptop into the same relative folder
in the clone, or download it from Meta's
[official SAM checkpoint list](https://github.com/facebookresearch/segment-anything#model-checkpoints).
Choose **ViT-H**, not ViT-L, ViT-B, or SAM 2.

Expected SHA-256:

```text
a7bf3b02f3ebf1267aba913ff637d9a2d5c33d3173bb679e46d9f338c26f262e
```

```powershell
Get-FileHash .\weights\sam_vit_h_4b8939.pth -Algorithm SHA256
```

Alternatively set `$env:SAM_CHECKPOINT` to the full path of that exact file.
The worker verifies its hash and all accepted references before inference.

## 4. Verify the transfer before resuming

```powershell
cd bhadra_highres_batches
python handoff.py verify
python worker.py validate
python -m unittest test_pipeline -v
python check_reference_fidelity.py
python worker.py status
```

`handoff.py verify` checks the saved GeoPackage, GeoJSON and batch evidence hashes;
run it **before** new processing modifies those files. `worker.py validate`
verifies the immutable references and checkpoint. The queue lives in the
GeoPackage's `run_jobs` table; `progress.json` is a regenerated summary.
Do not delete the GeoPackage, recreate the queue, or rerun the seed classification.
Completed batches are skipped automatically. The accepted seed is preserved.

## 5. Test one remaining batch, then continue

The repository intentionally contains `control.json` with `stop_requested: true`.
Only an explicit `--resume` clears it, after validation and acquiring the single-worker lock.

```powershell
python -u worker.py run --resume --device cpu --max-batches 1
```

Use `--device cuda` instead only on a verified CUDA-capable installation.
Review the new batch's `esri_rgb.tif`, `preview_combined.png`, `verification.json`
and class attributes. The combined preview includes the actual source image.
Small numerical differences across devices are possible; a new GPU does not
make the semantic labels automatically correct. Measure this batch for an ETA.

If satisfactory, start continuous processing (keep this terminal open):

```powershell
python -u worker.py run --resume --device cpu
```

Or, with the virtual environment activated, use the hidden Windows launcher:

```powershell
.\start_worker.ps1 -Resume -Device cpu
```

Use just one launch method. Logs are in `logs/`; inspect `worker_status.json`
and `python worker.py status`. Keep the laptop powered, awake and ventilated.
The worker runs continuously; no Codex automation is required to perform batches.
The old laptop's follow-up remains paused and is not transferred automatically.

## 6. Review holds, errors and safe pauses

The first batch and batches exceeding the uncertainty/gap thresholds stop for
review. Never approve because geometry alone passed. Inspect actual source and
combined/eight-class output, retain uncertainty, and diagnose visible mistakes.
Only after a real review:

```powershell
python worker.py approve --batch-id BATCH_ID --review-note "Describe the actual source/result inspection and remaining limitations"
python -u worker.py run --device cpu
```

For `error` or `blocked`, read `batches/BATCH_ID/error.json` and logs first.
After fixing the cause, `python worker.py retry --batch-id BATCH_ID` requeues it.
Missing imagery must not enter SAM; never bypass that check or lower zoom below 18.

To pause:

```powershell
python worker.py pause
```

The current batch finishes first. Wait until `worker_status.json` says `stopped`
and the process exits before copying/committing the database. The launcher does
not automatically restart. If an unexpected crash occurs, the exclusive lock and
per-stage caches allow the next worker to recover processing markers.

## 7. View the result in QGIS

Open **`Bhadra_Resume_PARTIAL.qgs`** in this folder. This separate portable copy
preserves the styles/visibility but repairs a hidden old layer's external path.
The original live `.qgz` is kept unchanged. If any saved project
source cannot resolve after relocation, create a new QGIS project and add:

1. `output/bhadra_highres_classification.gpkg`, layer `classified_regions`.
2. Load its style from `output/combined_display.qml`; name it
   **SAM ViT-H — detailed combined classification (PARTIAL / provisional)**.
3. Set the project CRS to **EPSG:32643**. The vector layer already has that CRS;
   do not assign EPSG:4326 to it.
4. Add an XYZ basemap named Esri World Imagery, below the classification:
   `https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}`.
5. Keep the rejected coarse classification and old duplicate results hidden.

`output/classified_regions_PARTIAL.geojson` is the transfer-time WGS84/EPSG:4326
export for interchange; it does not contain the queue and is not the resume database.
It will not update automatically as batches run. The GeoPackage is authoritative.
Reload the GeoPackage layer in QGIS after new batches publish.

## Detail, labels and storage

- Esri preferred zoom 19, explicit zoom 18 fallback; original ~0.485 m output
  grid, six overlapping 1024×768 SAM windows plus global proposals, ViT-H weights.
- Original 16-feature classifier, region voting and reviewed spatial context;
  no old scene-specific object IDs applied elsewhere.
- Cyan combines water, trees, structures, roads **and uncertain**; green is low
  vegetation, brown open ground. Individual object outlines and all eight source
  class attributes remain. Cyan does not mean confident identification.
- The geometrically complete partition includes explicitly tagged edge-based
  gap filling; it is not a claim of pixel-perfect semantic classification.
- Stop threshold is 8 GiB free. Allow substantially more storage for the full
  1,860-batch imagery/evidence archive. Do not delete evidence or reduce detail to
  evade the storage/quality gates.
- Do not announce completion until all 1,860 queue entries are complete,
  `progress.json` reports `whole_aoi_complete: true`, and
  `output/final_verification.json` passes. Field accuracy is a separate question.

For another later handoff, safely pause, update the portable QGIS project if needed,
run `python handoff.py create`, then
commit the current checkpoint and evidence. Do not force-push or overwrite a
newer checkpoint from another laptop. In a fresh clone, `origin` is **cv_ai_helps**;
on the old laptop, the correct remote was named **cv_ai_helps**, not `origin`.
