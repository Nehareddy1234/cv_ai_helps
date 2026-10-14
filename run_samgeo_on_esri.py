#!/usr/bin/env python3
"""
Run SamGeo classification and segmentation directly on cloud-free Esri World Imagery
covering the entire Bhadra Wildlife Sanctuary & Tiger Reserve AOI.
"""

import os
import sys
import time
from pathlib import Path

from _samgeo_lib import get_samgeo
samgeo_mod = get_samgeo()
SamGeo = samgeo_mod.SamGeo

import numpy as np
import rasterio
import rasterio.features
from shapely.geometry import shape
import geopandas as gpd

BASE_DIR = Path(__file__).resolve().parent
INPUT_TIF = str(BASE_DIR / "data" / "bhadra_esri_sanctuary.tif")
BOUNDARY_GEOJSON = str(BASE_DIR / "data" / "bhadra_boundary.geojson")
OUTPUT_MASK_TIF = str(BASE_DIR / "output" / "bhadra_esri_masks.tif")
OUTPUT_MASK_GPKG = str(BASE_DIR / "output" / "bhadra_esri_masks.gpkg")
CHECKPOINT = str(BASE_DIR / "weights" / "sam_vit_h_4b8939.pth")

def vector_polygonize(mask_tif, out_gpkg, boundary_file=None):
    print(f"Vectorizing mask raster {mask_tif} to GeoPackage {out_gpkg}...", flush=True)
    with rasterio.open(mask_tif) as src:
        image = src.read(1)
        valid_mask = image > 0
        records = []
        for geom_dict, val in rasterio.features.shapes(image, mask=valid_mask, transform=src.transform):
            val_int = int(val)
            if val_int > 0:
                geom = shape(geom_dict)
                if geom.is_valid and geom.area > 50:
                    records.append({"geometry": geom, "value": val_int})

    if not records:
        print("[Warning] No valid polygon records extracted from mask raster.", flush=True)
        return

    gdf = gpd.GeoDataFrame(records, crs=src.crs)
    print(f"Extracted {len(gdf)} polygon features. CRS: {gdf.crs}", flush=True)

    if boundary_file and os.path.exists(boundary_file):
        print(f"Clipping polygons to exact sanctuary boundary ({boundary_file})...", flush=True)
        b_gdf = gpd.read_file(boundary_file)
        if b_gdf.crs != gdf.crs:
            b_gdf = b_gdf.to_crs(gdf.crs)
        gdf = gpd.clip(gdf, b_gdf)
        # Filter out empty or micro-geometries
        gdf = gdf[~gdf.is_empty & (gdf.geometry.area > 50)]

    # Add descriptive attributes
    gdf["area_m2"] = gdf.geometry.area.round(1)
    gdf["class_label"] = gdf["value"].apply(lambda v: f"SamGeo Segment #{v}")

    # Save to GPKG
    os.makedirs(os.path.dirname(out_gpkg), exist_ok=True)
    gdf.to_file(out_gpkg, driver="GPKG", layer="samgeo_classifications")
    size_mb = os.path.getsize(out_gpkg) / (1024 * 1024)
    print(f"[OK] Saved GeoPackage: {out_gpkg} ({len(gdf)} features, {size_mb:.2f} MB)", flush=True)

def main():
    print("=" * 65, flush=True)
    print("SamGeo Classification on Esri World Imagery (Entire Bhadra Sanctuary)", flush=True)
    print(f"Input Imagery: {INPUT_TIF}", flush=True)
    print(f"Checkpoint: {CHECKPOINT}", flush=True)
    print(f"Output Mask: {OUTPUT_MASK_TIF}", flush=True)
    print(f"Output GPKG: {OUTPUT_MASK_GPKG}", flush=True)
    print("=" * 65, flush=True)

    start_time = time.time()


    print("Initializing SamGeo with SAM ViT-H on CPU...", flush=True)
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
            "min_mask_region_area": 80,
        },
    )

    print("Running automatic mask generation across full sanctuary...", flush=True)
    sam.generate(
        source=INPUT_TIF,
        output=OUTPUT_MASK_TIF,
        foreground=True,
        unique=True,
    )
    print(f"Mask generation completed in {time.time() - start_time:.1f}s.", flush=True)

    # Convert to vector GeoPackage
    vector_polygonize(OUTPUT_MASK_TIF, OUTPUT_MASK_GPKG, boundary_file=BOUNDARY_GEOJSON)

    total_time = time.time() - start_time
    print(f"All processing complete in {total_time:.1f}s!", flush=True)

if __name__ == "__main__":
    main()
