import os
import sys
import time
from pathlib import Path

# Fix module shadowing so we import the external samgeo package
_current_dir = str(Path(__file__).resolve().parent)
sys.path = [p for p in sys.path if str(Path(p).resolve()) != _current_dir]

import torch
import geopandas as gpd
import rasterio
from rasterio.warp import transform_bounds
torch.set_num_threads(os.cpu_count() or 8)

# Paths
BASE_DIR = Path(__file__).resolve().parent
RGB_TIF = str(BASE_DIR / "data" / "bhadra_entire_rgb.tif")
AOI_PATH = str(BASE_DIR / "data" / "bhadra_boundary.geojson")
MASK_TIF = str(BASE_DIR / "output" / "bhadra_entire_masks.tif")
MASK_GPKG = str(BASE_DIR / "output" / "bhadra_entire_masks.gpkg")
CHECKPOINT = str(BASE_DIR / "weights" / "sam_vit_h_4b8939.pth")


def validate_full_aoi_coverage():
    """Reject the former small test raster before expensive SAM inference."""
    aoi = gpd.read_file(AOI_PATH).to_crs("EPSG:4326")
    west, south, east, north = aoi.total_bounds
    with rasterio.open(RGB_TIF) as src:
        left, bottom, right, top = transform_bounds(src.crs, "EPSG:4326", *src.bounds)

    tolerance = 1e-4
    covered = (
        left <= west + tolerance and bottom <= south + tolerance
        and right >= east - tolerance and top >= north - tolerance
    )
    if not covered:
        raise RuntimeError(
            "Input raster does not cover the complete Bhadra AOI. "
            f"AOI={(west, south, east, north)}, raster={(left, bottom, right, top)}"
        )
    print("Coverage check passed: source raster contains the complete Bhadra AOI.")

print(f"Starting SamGeo Annotation on Full Bhadra Region...")
print(f"Input Raster: {RGB_TIF}")
print(f"Model Checkpoint: {CHECKPOINT}")
print(f"Target Mask: {MASK_TIF}")
print(f"Target GeoPackage: {MASK_GPKG}")
print(f"Using {torch.get_num_threads()} CPU threads for inference.")

start_time = time.time()

validate_full_aoi_coverage()

from samgeo import SamGeo

print("Initializing SamGeo on CPU...")
sam = SamGeo(
    model_type="vit_h",
    checkpoint=CHECKPOINT,
    automatic=True,
    device="cpu",
    sam_kwargs={
        "points_per_side": 12,
        "pred_iou_thresh": 0.86,
        "stability_score_thresh": 0.92,
        "crop_n_layers": 0,
        "min_mask_region_area": 100,
    },
)

print(f"Running automatic mask generator across full Bhadra sanctuary...")
sam.generate(
    source=RGB_TIF,
    output=MASK_TIF,
    foreground=True,
    unique=True,
)

print(f"Mask generation finished in {time.time() - start_time:.1f}s.")
print(f"Converting masks to vector GeoPackage: {MASK_GPKG}...")
sam.tiff_to_gpkg(MASK_TIF, MASK_GPKG)

print(f"Success! GeoPackage saved ({os.path.getsize(MASK_GPKG)/(1024*1024):.2f} MB)")
