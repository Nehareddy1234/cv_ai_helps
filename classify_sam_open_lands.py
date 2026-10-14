#!/usr/bin/env python3
"""Classify open-land candidates from full-Bhadra SamGeo segments.

This workflow deliberately starts from SamGeo polygons, not the landing-zone
output in the sibling Codes project.  RGB evidence is used to reject water,
deep shadow, and dense dark canopy; known water and building polygons are then
subtracted.  The result is an open-land inventory, not a landing-safety claim.
"""

from __future__ import annotations

import math
from pathlib import Path

import geopandas as gpd
import numpy as np
import rasterio
from rasterio.mask import mask


BASE_DIR = Path(__file__).resolve().parent
AOI_PATH = BASE_DIR / "data" / "bhadra_boundary.geojson"
RGB_PATH = BASE_DIR / "data" / "bhadra_esri_sanctuary.tif"
SAM_SEGMENTS = BASE_DIR / "output" / "bhadra_esri_masks.gpkg"
SPECTRAL_PATH = BASE_DIR.parent / "Codes" / "data" / "processed" / "Bhadra" / "sentinel2" / "2026-06-01" / "bhadra_spectral.tif"
BUILDINGS = BASE_DIR / "output" / "bhadra_classified_buildings.gpkg"
WATER = BASE_DIR / "output" / "bhadra_classified_water.gpkg"
OUTPUT = BASE_DIR / "output" / "bhadra_sam_open_lands.gpkg"

MIN_AREA_M2 = 300.0
MIN_BRIGHTNESS = 62.0
MAX_GREEN_EXCESS = 48.0
MAX_TEXTURE_STD = 58.0
MAX_MEAN_NDVI = 0.55
MAX_NDVI_P75 = 0.68


def _rgb_stats(src: rasterio.io.DatasetReader, geom) -> dict[str, float] | None:
    try:
        data, _ = mask(src, [geom], crop=True, filled=False, indexes=[1, 2, 3])
    except ValueError:
        return None

    pixels = np.moveaxis(data.filled(0), 0, -1).reshape(-1, 3)
    valid = (~np.any(np.ma.getmaskarray(np.moveaxis(data, 0, -1)), axis=-1)).reshape(-1)
    valid &= np.any(pixels > 0, axis=1)
    pixels = pixels[valid].astype(np.float32)
    if pixels.shape[0] < 4:
        return None
    if pixels.shape[0] > 50000:
        pixels = pixels[:: math.ceil(pixels.shape[0] / 50000)]

    mean_r, mean_g, mean_b = np.mean(pixels, axis=0)
    brightness = float(np.mean(pixels))
    green_excess = float(2 * mean_g - mean_r - mean_b)
    texture = float(np.mean(np.std(pixels, axis=0)))
    blue_excess = float(mean_b - mean_r)
    return {
        "mean_r": float(mean_r),
        "mean_g": float(mean_g),
        "mean_b": float(mean_b),
        "brightness": brightness,
        "green_excess": green_excess,
        "texture_std": texture,
        "blue_excess": blue_excess,
    }


def _land_cover(stats: dict[str, float]) -> str | None:
    # Water/shadow are dark or blue-dominant. Dense forest usually has a high
    # green excess and/or strong crown-shadow texture in this imagery.
    if stats["brightness"] < MIN_BRIGHTNESS or stats["blue_excess"] > 18:
        return None
    if stats["green_excess"] > MAX_GREEN_EXCESS:
        return None
    if stats["texture_std"] > MAX_TEXTURE_STD and stats["brightness"] < 92:
        return None
    if stats["mean_ndvi"] > MAX_MEAN_NDVI or stats["ndvi_p75"] > MAX_NDVI_P75:
        return None
    if stats["mean_mndwi"] >= 0:
        return None

    if stats["green_excess"] >= 20:
        return "Open grass / meadow"
    if stats["brightness"] >= 115 and stats["green_excess"] < 15:
        return "Bare or exposed open land"
    return "Open clearing / sparse vegetation"


def _spectral_stats(src: rasterio.io.DatasetReader, geom) -> dict[str, float] | None:
    """Return Sentinel-2 NDVI/MNDWI evidence for a SamGeo polygon."""
    try:
        data, _ = mask(src, [geom], crop=True, filled=False, indexes=[2, 3, 4, 5])
    except ValueError:
        return None
    green, red, nir, swir = [band.compressed().astype(np.float32) for band in data]
    length = min(map(len, (green, red, nir, swir)))
    if length < 4:
        return None
    green, red, nir, swir = green[:length], red[:length], nir[:length], swir[:length]
    ndvi = (nir - red) / np.maximum(nir + red, 1e-6)
    mndwi = (green - swir) / np.maximum(green + swir, 1e-6)
    valid = np.isfinite(ndvi) & np.isfinite(mndwi)
    ndvi, mndwi = ndvi[valid], mndwi[valid]
    if len(ndvi) < 4:
        return None
    return {
        "mean_ndvi": float(np.mean(ndvi)),
        "ndvi_p75": float(np.percentile(ndvi, 75)),
        "mean_mndwi": float(np.mean(mndwi)),
    }


def _subtract_obstacles(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    obstacles = []
    if WATER.exists():
        water = gpd.read_file(WATER).to_crs(gdf.crs)
        obstacles.extend(water.geometry[~water.geometry.is_empty])
    if BUILDINGS.exists():
        buildings = gpd.read_file(BUILDINGS).to_crs(gdf.crs)
        obstacles.extend(buildings.geometry[~buildings.geometry.is_empty].buffer(5.0))
    if not obstacles:
        return gdf

    obstacle_union = gpd.GeoSeries(obstacles, crs=gdf.crs).union_all()
    result = gdf.copy()
    result.geometry = result.geometry.difference(obstacle_union)
    return result.explode(index_parts=False).reset_index(drop=True)


def build_open_land_inventory() -> None:
    for required in (AOI_PATH, RGB_PATH, SAM_SEGMENTS, SPECTRAL_PATH):
        if not required.exists():
            raise FileNotFoundError(required)

    print("Loading the full Bhadra AOI and SamGeo segments...", flush=True)
    aoi = gpd.read_file(AOI_PATH).to_crs("EPSG:3857")
    segments = gpd.read_file(SAM_SEGMENTS).to_crs(aoi.crs)
    segments = gpd.clip(segments, aoi).explode(index_parts=False).reset_index(drop=True)
    segments = segments[segments.geometry.notna() & ~segments.geometry.is_empty].copy()
    segments["area_m2"] = segments.geometry.area
    segments = segments[segments["area_m2"] >= MIN_AREA_M2].copy()

    print(f"Evaluating {len(segments)} viable SamGeo regions against RGB imagery...", flush=True)
    records = []
    with rasterio.open(RGB_PATH) as src, rasterio.open(SPECTRAL_PATH) as spectral_src:
        if src.crs != segments.crs:
            segments = segments.to_crs(src.crs)
        spectral_geoms = segments.to_crs(spectral_src.crs).geometry
        for position, (source_id, row) in enumerate(segments.iterrows(), start=1):
            if position % 100 == 0:
                print(f"  evaluated {position}/{len(segments)} regions", flush=True)
            stats = _rgb_stats(src, row.geometry)
            if stats is None:
                continue
            spectral = _spectral_stats(spectral_src, spectral_geoms.loc[source_id])
            if spectral is None:
                continue
            stats.update(spectral)
            open_type = _land_cover(stats)
            if open_type is None:
                continue
            records.append({
                "geometry": row.geometry,
                "source_id": int(source_id),
                "sam_value": int(row.get("value", 0)),
                "open_type": open_type,
                **{key: round(value, 2) for key, value in stats.items()},
            })

    open_land = gpd.GeoDataFrame(records, crs=segments.crs)
    if open_land.empty:
        raise RuntimeError("No open-land segments passed the classification thresholds")
    print(f"Retained {len(open_land)} spectral open-land candidates; subtracting obstacles...", flush=True)
    open_land = _subtract_obstacles(open_land)
    open_land = gpd.clip(open_land, aoi.to_crs(open_land.crs))
    open_land = open_land[open_land.geometry.notna() & ~open_land.geometry.is_empty].copy()
    open_land["area_m2"] = open_land.geometry.area.round(1)
    open_land = open_land[open_land["area_m2"] >= MIN_AREA_M2].copy()
    open_land["area_ha"] = (open_land["area_m2"] / 10000).round(3)
    open_land = open_land.reset_index(drop=True)
    open_land["zone_id"] = ""
    open_land["clear_diam_m"] = 0.0

    centers = []
    for index, row in open_land.iterrows():
        geom = row.geometry
        # A guaranteed-inside point keeps the regional workflow fast. Its
        # boundary distance is a conservative local-clearance measurement.
        center = geom.representative_point()
        radius = center.distance(geom.boundary)
        zone_id = f"SAM_OPEN_{index + 1:04d}"
        open_land.at[index, "zone_id"] = zone_id
        open_land.at[index, "clear_diam_m"] = round(2 * radius, 1)
        centers.append({
            "zone_id": zone_id,
            "open_type": row.open_type,
            "area_ha": row.area_ha,
            "clear_diam_m": round(2 * radius, 1),
            "geometry": center,
        })

    open_land = open_land.to_crs("EPSG:3857")
    center_gdf = gpd.GeoDataFrame(centers, crs=segments.crs).to_crs("EPSG:3857")
    OUTPUT.unlink(missing_ok=True)
    open_land.to_file(OUTPUT, layer="open_lands", driver="GPKG")
    center_gdf.to_file(OUTPUT, layer="open_land_centers", driver="GPKG")

    print(f"Created {len(open_land)} SamGeo-derived open-land polygons")
    print(f"Total candidate open-land area: {open_land.area.sum() / 1_000_000:.2f} km2")
    print(f"Output: {OUTPUT}")


if __name__ == "__main__":
    build_open_land_inventory()
