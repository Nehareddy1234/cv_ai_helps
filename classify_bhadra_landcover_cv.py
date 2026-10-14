#!/usr/bin/env python3
"""Index-based computer-vision land-cover map for the complete Bhadra AOI.

The polygons are analysis overlays designed to sit transparently above the
live Esri XYZ basemap. Buildings and detailed SamGeo open-land candidates are
kept as separate, higher-priority vector layers in the QGIS project.
"""

from pathlib import Path

import geopandas as gpd
import numpy as np
import rasterio
from rasterio.features import geometry_mask, shapes, sieve
from shapely.geometry import shape


BASE_DIR = Path(__file__).resolve().parent
SPECTRAL = BASE_DIR.parent / "Codes" / "data" / "processed" / "Bhadra" / "sentinel2" / "2026-06-01" / "bhadra_spectral.tif"
SCL = BASE_DIR.parent / "Codes" / "data" / "processed" / "Bhadra" / "sentinel2" / "2026-06-01" / "bhadra_scl.tif"
AOI = BASE_DIR / "data" / "bhadra_boundary.geojson"
OUTPUT = BASE_DIR / "output" / "bhadra_cv_landcover.gpkg"

LABELS = {
    1: "Water",
    2: "Dense vegetation / forest",
    3: "Moderate vegetation",
    4: "Open grass / low vegetation",
    5: "Bare or sparsely vegetated open land",
}


def build_landcover() -> None:
    print("Reading full-AOI Sentinel spectral imagery...", flush=True)
    with rasterio.open(SPECTRAL) as src:
        green = src.read(2).astype("float32")
        red = src.read(3).astype("float32")
        nir = src.read(4).astype("float32")
        swir = src.read(5).astype("float32")
        transform, crs = src.transform, src.crs
        aoi = gpd.read_file(AOI).to_crs(crs)
        inside = geometry_mask(aoi.geometry, src.shape, transform, invert=True)
    with rasterio.open(SCL) as src:
        scl = src.read(1)

    ndvi = (nir - red) / np.maximum(nir + red, 1e-6)
    mndwi = (green - swir) / np.maximum(green + swir, 1e-6)
    valid = inside & np.isfinite(ndvi) & np.isfinite(mndwi) & ~np.isin(scl, [0, 1, 3, 8, 9, 10, 11])

    classes = np.zeros(ndvi.shape, dtype="uint8")
    classes[valid & ((scl == 6) | (mndwi >= 0.0))] = 1
    land = valid & (classes == 0)
    classes[land & (ndvi > 0.65)] = 2
    classes[land & (ndvi > 0.45) & (ndvi <= 0.65)] = 3
    classes[land & (ndvi > 0.20) & (ndvi <= 0.45)] = 4
    classes[land & (ndvi <= 0.20)] = 5

    # Remove isolated speckle smaller than 25 connected 10 m pixels (0.25 ha).
    classes = sieve(classes, size=25, connectivity=8)
    records = []
    for geom_mapping, value in shapes(classes, mask=classes > 0, transform=transform, connectivity=8):
        class_id = int(value)
        geom = shape(geom_mapping).simplify(7.0, preserve_topology=True)
        if geom.is_empty or geom.area < 2500:
            continue
        records.append({
            "class_id": class_id,
            "land_cover": LABELS[class_id],
            "area_ha": round(geom.area / 10000, 3),
            "geometry": geom,
        })

    result = gpd.GeoDataFrame(records, crs=crs)
    result = gpd.clip(result, aoi).explode(index_parts=False).reset_index(drop=True)
    result["area_ha"] = (result.geometry.area / 10000).round(3)
    result = result[result.area_ha >= 0.25].copy()
    result = result.to_crs("EPSG:3857")

    OUTPUT.unlink(missing_ok=True)
    result.to_file(OUTPUT, layer="land_cover", driver="GPKG")
    print(f"Created {len(result)} land-cover polygons in {OUTPUT}", flush=True)
    print(result.groupby("land_cover").area_ha.agg(["count", "sum"]).round(2), flush=True)


if __name__ == "__main__":
    build_landcover()
