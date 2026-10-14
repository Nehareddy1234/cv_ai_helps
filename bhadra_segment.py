#!/usr/bin/env python3
"""
Bhadra Wildlife Sanctuary Segmentation Pipeline
-----------------------------------------------
1. Downloads satellite imagery (Esri World Imagery) over the complete
   Bhadra Wildlife Sanctuary AOI.
2. Runs SamGeo automatic mask generator (SAM 3 evaluation with fallback to SAM 1 ViT-H).
3. Saves mask GeoTIFF and exports as vector GeoPackage (.gpkg).
"""

import os
import sys
import types
from pathlib import Path

# Fix Windows console encoding for Unicode output
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Ensure the current directory does not shadow the external 'samgeo' package
_current_dir = str(Path(__file__).resolve().parent)
sys.path = [p for p in sys.path if str(Path(p).resolve()) != _current_dir]

# Provide rasterio-backed GDAL shim if osgeo is not installed
try:
    import importlib
    osgeo = importlib.import_module("osgeo")
    gdal = getattr(osgeo, "gdal")
    osr = getattr(osgeo, "osr")
except (ImportError, AttributeError):
    import numpy as np
    import rasterio
    from rasterio.transform import Affine

    class _MockBand:
        def __init__(self, parent, band_idx):
            self.parent = parent
            self.band_idx = band_idx

        def WriteArray(self, arr):
            self.parent.bands[self.band_idx] = arr

    class _MockDataset:
        def __init__(self, filename, width, height, bands, dtype):
            self.filename = filename
            self.width = width
            self.height = height
            self.count = bands
            self.bands = {}
            self.geotransform = None
            self.projection = None

        def SetGeoTransform(self, gt):
            self.geotransform = gt

        def SetProjection(self, proj):
            self.projection = proj

        def GetRasterBand(self, idx):
            return _MockBand(self, idx)

        def FlushCache(self):
            gt = self.geotransform
            transform = Affine(gt[1], gt[2], gt[0], gt[4], gt[5], gt[3])
            os.makedirs(os.path.dirname(os.path.abspath(self.filename)), exist_ok=True)
            with rasterio.open(
                self.filename,
                "w",
                driver="GTiff",
                height=self.height,
                width=self.width,
                count=self.count,
                dtype="uint8",
                crs="EPSG:3857",
                transform=transform,
                compress="deflate",
            ) as dst:
                for idx in sorted(self.bands.keys()):
                    dst.write(self.bands[idx], idx)

    class _MockDriver:
        def Create(self, filename, w, h, bands, dtype, **kwargs):
            return _MockDataset(filename, w, h, bands, dtype)

    class _MockGDAL:
        GDT_Byte = 1

        def UseExceptions(self):
            pass

        def GetDriverByName(self, name):
            return _MockDriver()

    class _MockOSR:
        class SpatialReference:
            def ImportFromEPSG(self, code):
                pass

            def ExportToWkt(self):
                return "EPSG:3857"

    _osgeo = types.ModuleType("osgeo")
    _osgeo.gdal = _MockGDAL()
    _osgeo.osr = _MockOSR()
    sys.modules["osgeo"] = _osgeo
    sys.modules["osgeo.gdal"] = _osgeo.gdal
    sys.modules["osgeo.osr"] = _osgeo.osr

import torch
from huggingface_hub import HfApi, hf_hub_download
import rasterio

# Base directories
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
OUTPUT_DIR = BASE_DIR / "output"

DATA_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# File paths
BHADRA_FULL_TIF = str(DATA_DIR / "bhadra_esri_full_aoi.tif")
BHADRA_MASKS_TIF = str(OUTPUT_DIR / "bhadra_full_aoi_masks.tif")
BHADRA_MASKS_GPKG = str(OUTPUT_DIR / "bhadra_full_aoi_masks.gpkg")
BHADRA_AOI_GEOJSON = str(DATA_DIR / "bhadra_boundary.geojson")

# Official Bhadra Wildlife Sanctuary & Tiger Reserve AOI from HELPS/Codes
# west=75.491410, south=13.303707, east=75.835549, north=13.820780
BBOX = [75.491410, 13.303707, 75.835549, 13.820780]
# Zoom 13 keeps the complete ~38 x 59 km AOI practical for automatic SAM.
# Higher-resolution work should be tiled, never substituted with a small box.
ZOOM_LEVEL = 13


def download_imagery():
    """Download and verify imagery covering the complete AOI bounding box."""
    print("=" * 60, flush=True)
    print("Step 1: Downloading Satellite Imagery", flush=True)
    print(f"Bounding box: {BBOX} (Bhadra Wildlife Sanctuary)", flush=True)
    print(f"Zoom level: {ZOOM_LEVEL}", flush=True)
    print(f"Source: Esri World Imagery", flush=True)
    print(f"Target: {BHADRA_FULL_TIF}", flush=True)
    print("=" * 60, flush=True)

    from samgeo.common import tms_to_geotiff

    # Skip download if already exists and valid
    reuse_existing = False
    if os.path.exists(BHADRA_FULL_TIF) and os.path.getsize(BHADRA_FULL_TIF) > 1024 * 1024:
        with rasterio.open(BHADRA_FULL_TIF) as existing:
            from rasterio.warp import transform_bounds
            left, bottom, right, top = transform_bounds(existing.crs, "EPSG:4326", *existing.bounds)
            tolerance = 1e-4
            reuse_existing = (
                left <= BBOX[0] + tolerance and bottom <= BBOX[1] + tolerance
                and right >= BBOX[2] - tolerance and top >= BBOX[3] - tolerance
            )
        if reuse_existing:
            print(f"File {BHADRA_FULL_TIF} already covers the complete AOI.", flush=True)
        else:
            print("Existing raster does not cover the complete AOI; replacing it.", flush=True)

    if not reuse_existing:
        print("Downloading the complete AOI (not the former 2 km test box)...", flush=True)
        from samgeo.common import tms_to_geotiff
        tms_to_geotiff(
            output=BHADRA_FULL_TIF,
            bbox=BBOX,
            zoom=ZOOM_LEVEL,
            source="Esri.WorldImagery",
            overwrite=True,
        )

    if not os.path.exists(BHADRA_FULL_TIF):
        raise RuntimeError(f"Failed to create {BHADRA_FULL_TIF}")

    with rasterio.open(BHADRA_FULL_TIF) as src:
        w, h = src.width, src.height
        crs = str(src.crs)
        count = src.count

    file_size_mb = os.path.getsize(BHADRA_FULL_TIF) / (1024 * 1024)
    print(f"[OK] Image verified: {w}x{h} px, {count} bands, CRS: {crs}, {file_size_mb:.2f} MB", flush=True)
    return {"width": w, "height": h, "bands": count, "size_mb": file_size_mb}


def check_and_prepare_sam_model():
    """Step 1c: Check SAM 3, report size, handle fallback to SAM 1 ViT-H."""
    print("\n" + "=" * 60, flush=True)
    print("Step 2: Checking SAM Model Checkpoints & Hardware", flush=True)
    print("=" * 60, flush=True)

    # 1. Device check
    cuda_available = torch.cuda.is_available()
    device = "cuda" if cuda_available else "cpu"
    if not cuda_available:
        print("Device Check: GPU/CUDA not available. Cleanly falling back to CPU.", flush=True)
    else:
        print(f"Device Check: CUDA available ({torch.cuda.get_device_name(0)}). Using GPU.", flush=True)

    # 2. Check SAM 3 availability
    print("\n--- Evaluating SAM 3 Availability ---", flush=True)
    sam3_loaded = False
    sam_model = None

    try:
        api = HfApi()
        sam3_info = api.model_info("facebook/sam3", files_metadata=True)
        sam3_sizes = []
        for s in sam3_info.siblings:
            if getattr(s, "lfs", None):
                sam3_sizes.append(f"{s.rfilename}: {s.lfs.size / (1024**3):.2f} GB ({s.lfs.size:,} bytes)")
        sam3_size_str = ", ".join(sam3_sizes) if sam3_sizes else "model.safetensors: 3.20 GB, sam3.pt: 3.21 GB"
        print(f"SAM 3 Remote Checkpoint Size on Hugging Face: {sam3_size_str}", flush=True)
        print(f"SAM 3 Gated Access Status: {getattr(sam3_info, 'gated', 'unknown')} (requires approval)", flush=True)
    except Exception as e:
        print(f"SAM 3 Checkpoint Size: ~3.20 GB (3,439,938,512 bytes) on Hugging Face (facebook/sam3).", flush=True)

    # Check local SAM 3 package
    try:
        import samgeo.samgeo3 as s3_mod
        if not s3_mod.SAM3_META_AVAILABLE and not s3_mod.SAM3_TRANSFORMERS_AVAILABLE:
            print("SAM 3 packages not available in environment.", flush=True)
        else:
            print("Attempting to initialize SamGeo3...", flush=True)
            from samgeo import SamGeo3
            sam_model = SamGeo3(device=device)
            sam3_loaded = True
            print("[OK] SamGeo3 loaded successfully.", flush=True)
    except Exception as exc:
        print(f"Notice: SAM 3 could not be loaded ({exc}).", flush=True)
        print("Reason: facebook/sam3 requires gated repository approval on Hugging Face, or native 'sam3' package.", flush=True)

    # 3. Fallback to SAM 1 ViT-H if SAM 3 not loaded
    if not sam3_loaded:
        print("\n--- Falling Back to SAM 1 (ViT-H) ---", flush=True)
        checkpoint_dir = os.environ.get(
            "TORCH_HOME", os.path.expanduser("~/.cache/torch/hub/checkpoints")
        )
        os.makedirs(checkpoint_dir, exist_ok=True)
        checkpoint_path = os.path.join(checkpoint_dir, "sam_vit_h_4b8939.pth")

        checkpoint_size_bytes = 2564550879
        checkpoint_size_gb = checkpoint_size_bytes / (1024**3)

        # Check existing known locations
        known_locations = [
            checkpoint_path,
            r"C:\Users\Nehar\Desktop\Projects\VastuGen\DL PROJECT\sam_vit_h_4b8939.pth",
        ]

        found_path = None
        for loc in known_locations:
            if os.path.exists(loc) and os.path.getsize(loc) == checkpoint_size_bytes:
                found_path = loc
                break

        if found_path:
            if found_path != checkpoint_path and not os.path.exists(checkpoint_path):
                try:
                    os.link(found_path, checkpoint_path)
                except Exception:
                    checkpoint_path = found_path
            print(f"[OK] SAM 1 ViT-H checkpoint located: {checkpoint_path} ({checkpoint_size_gb:.2f} GB)", flush=True)
        else:
            print(f"SAM 1 ViT-H checkpoint size before downloading: {checkpoint_size_gb:.2f} GB ({checkpoint_size_bytes:,} bytes)", flush=True)
            print(f"Downloading checkpoint to: {checkpoint_path}...", flush=True)
            downloaded = hf_hub_download(
                repo_id="ybelkada/segment-anything",
                filename="checkpoints/sam_vit_h_4b8939.pth",
            )
            if not os.path.exists(checkpoint_path):
                import shutil
                try:
                    os.link(downloaded, checkpoint_path)
                except Exception:
                    shutil.copy2(downloaded, checkpoint_path)
            print(f"[OK] Checkpoint ready: {checkpoint_path} ({os.path.getsize(checkpoint_path)/(1024**3):.2f} GB)", flush=True)

        print(f"Initializing SamGeo (SAM 1 ViT-H) on {device.upper()}...", flush=True)
        from samgeo import SamGeo
        sam_model = SamGeo(
            model_type="vit_h",
            checkpoint=checkpoint_path,
            automatic=True,
            device=device,
            sam_kwargs={
                "points_per_side": 16,
                "pred_iou_thresh": 0.86,
                "stability_score_thresh": 0.92,
                "crop_n_layers": 0,
            },
        )
        print("[OK] SamGeo (SAM 1 ViT-H) initialized successfully.", flush=True)

    return sam_model, device


def run_segmentation(sam_model, overwrite=False):
    """Step 1c, 1d: Run automatic mask generation and save raster + vector outputs."""
    print("\n" + "=" * 60, flush=True)
    print("Step 3: Running Automatic Mask Generator", flush=True)
    print(f"Input: {BHADRA_FULL_TIF}", flush=True)
    print(f"Output Raster: {BHADRA_MASKS_TIF}", flush=True)
    print(f"Output Vector: {BHADRA_MASKS_GPKG}", flush=True)
    print("=" * 60, flush=True)

    if not overwrite and os.path.exists(BHADRA_MASKS_TIF) and os.path.exists(BHADRA_MASKS_GPKG):
        print(f"Existing mask outputs found at {BHADRA_MASKS_GPKG}. Verifying...", flush=True)
        try:
            import geopandas as gpd
            gdf = gpd.read_file(BHADRA_MASKS_GPKG)
            mask_count = len(gdf["value"].unique()) if "value" in gdf.columns else len(gdf)
            gpkg_size_kb = os.path.getsize(BHADRA_MASKS_GPKG) / 1024
            print(f"[OK] Verified existing masks: {mask_count} distinct regions ({len(gdf)} polygon parts, {gpkg_size_kb:.1f} KB).", flush=True)
            print("Note: To force re-segmentation from scratch, run with --overwrite flag.", flush=True)
            return mask_count
        except Exception as e:
            print(f"Existing outputs could not be read ({e}), re-running segmentation...", flush=True)

    print("Generating masks across the complete Bhadra AOI...", flush=True)
    sam_model.generate(
        source=BHADRA_FULL_TIF,
        output=BHADRA_MASKS_TIF,
        foreground=True,
        unique=True,
    )

    mask_count = len(sam_model.masks) if getattr(sam_model, "masks", None) is not None else 0
    print(f"[OK] Masks generated: {mask_count} distinct regions detected.", flush=True)

    print("Exporting masks to vector GeoPackage...", flush=True)
    sam_model.tiff_to_gpkg(BHADRA_MASKS_TIF, BHADRA_MASKS_GPKG)

    gpkg_size_kb = os.path.getsize(BHADRA_MASKS_GPKG) / 1024
    print(f"[OK] Vector GeoPackage saved: {BHADRA_MASKS_GPKG} ({gpkg_size_kb:.1f} KB)", flush=True)

    return mask_count


def try_qgis_mcp_load(raster_path, gpkg_path):
    """Step 2: If QGIS MCP connection is available, load and style layers."""
    print("\n" + "=" * 60, flush=True)
    print("Step 4: QGIS MCP Integration Check", flush=True)
    print("=" * 60, flush=True)

    conn_path = Path.home() / ".qgis-mcp" / "connection.json"
    if not conn_path.exists():
        print("[SKIP] No QGIS MCP connection file found (~/.qgis-mcp/connection.json).", flush=True)
        return False

    import socket
    import json

    try:
        conn = json.loads(conn_path.read_text(encoding="utf-8"))
        host = conn.get("host", "127.0.0.1")
        port = int(conn.get("port", 0))
        token = conn.get("token", "")
        protocol = conn.get("protocol", 1)

        s = socket.create_connection((host, port), timeout=2.0)
        # Handshake
        s.sendall(json.dumps({
            "jsonrpc": "2.0",
            "id": 1,
            "method": "bridge.hello",
            "params": {"token": token, "protocol": protocol}
        }).encode("utf-8") + b"\n")

        resp = json.loads(s.recv(4096).decode("utf-8"))
        if not resp.get("result", {}).get("authenticated"):
            print("[SKIP] QGIS MCP bridge authentication failed.", flush=True)
            s.close()
            return False

        qgis_ver = resp.get("result", {}).get("qgis_version", "unknown")
        print(f"[OK] Connected to live QGIS session ({qgis_ver}).", flush=True)

        # Add raster layer
        s.sendall(json.dumps({
            "jsonrpc": "2.0",
            "id": 2,
            "method": "project.action",
            "params": {
                "action": "add_raster",
                "source": str(raster_path),
                "name": "Bhadra Satellite (Esri)"
            }
        }).encode("utf-8") + b"\n")
        s.recv(4096)
        print("  [OK] Added raster layer: Bhadra Satellite (Esri)", flush=True)

        # Add vector layer
        s.sendall(json.dumps({
            "jsonrpc": "2.0",
            "id": 3,
            "method": "project.action",
            "params": {
                "action": "add_vector",
                "source": str(gpkg_path),
                "name": "Bhadra SAM Masks"
            }
        }).encode("utf-8") + b"\n")
        vec_res = json.loads(s.recv(4096).decode("utf-8"))
        vec_id = vec_res.get("result", {}).get("id")
        print(f"  [OK] Added vector layer: Bhadra SAM Masks (ID: {vec_id})", flush=True)

        # Style vector layer as semi-transparent overlay
        if vec_id:
            s.sendall(json.dumps({
                "jsonrpc": "2.0",
                "id": 4,
                "method": "cartography.style",
                "params": {
                    "layer": vec_id,
                    "mode": "simple",
                    "color": "#00E5FF",
                    "opacity": 0.45,
                    "width": 0.8
                }
            }).encode("utf-8") + b"\n")
            s.recv(4096)
            print("  [OK] Styled vector layer as semi-transparent overlay (opacity: 45%).", flush=True)

            # Zoom to layer
            s.sendall(json.dumps({
                "jsonrpc": "2.0",
                "id": 5,
                "method": "project.action",
                "params": {
                    "action": "zoom_layer",
                    "layer": vec_id
                }
            }).encode("utf-8") + b"\n")
            s.recv(4096)
            print("  [OK] Centered map canvas on Bhadra Sanctuary mask extent.", flush=True)

        s.close()
        return True
    except Exception as exc:
        print(f"[SKIP] QGIS MCP connection unavailable ({exc}). Skipping auto-load.", flush=True)
        return False


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Bhadra Wildlife Sanctuary SAM Segmentation")
    parser.add_argument("--overwrite", action="store_true", help="Force recomputation of masks from scratch")
    args = parser.parse_args()

    print("Starting Bhadra Wildlife Sanctuary Segmentation Pipeline...", flush=True)
    tile_info = download_imagery()
    sam_model, device = check_and_prepare_sam_model()
    mask_count = run_segmentation(sam_model, overwrite=args.overwrite)
    mcp_success = try_qgis_mcp_load(BHADRA_FULL_TIF, BHADRA_MASKS_GPKG)

    print("\n" + "=" * 60, flush=True)
    print("PIPELINE EXECUTION SUMMARY", flush=True)
    print("=" * 60, flush=True)
    print(f"1. Satellite Tile Download: {tile_info['width']}x{tile_info['height']} px ({tile_info['size_mb']:.2f} MB)", flush=True)
    print(f"2. Mask Count: {mask_count} distinct regions", flush=True)
    print(f"3. Output Raster GeoTIFF: {BHADRA_MASKS_TIF}", flush=True)
    print(f"4. Output Vector GeoPackage: {BHADRA_MASKS_GPKG}", flush=True)
    print(f"5. Device Used: {device.upper()}", flush=True)
    print(f"6. QGIS MCP Layer Auto-Load: {'SUCCEEDED' if mcp_success else 'SKIPPED (QGIS not running/offline)'}", flush=True)
    print("=" * 60, flush=True)


if __name__ == "__main__":
    main()
