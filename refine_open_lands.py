#!/usr/bin/env python3
"""Remove water and built-up false positives from Bhadra open-land polygons."""

from pathlib import Path

import geopandas as gpd


BASE_DIR = Path(__file__).resolve().parent
LAND_COVER = BASE_DIR / "output" / "bhadra_cv_landcover.gpkg"
WATER = BASE_DIR / "output" / "bhadra_classified_water.gpkg"
BUILDINGS = BASE_DIR / "output" / "bhadra_classified_buildings.gpkg"
AOI = BASE_DIR / "data" / "bhadra_boundary.geojson"
OUTPUT = BASE_DIR / "output" / "bhadra_open_lands_refined.gpkg"

# Buffers compensate for date/resolution differences between the satellite
# classification and vector obstacles. A settlement-scale buffer also removes
# the spaces between adjacent roofs that are not operationally open land.
WATER_BUFFER_M = 20.0
BUILDING_BUFFER_M = 12.0
MIN_OPEN_AREA_M2 = 300.0


def refine_open_lands() -> None:
    print("Loading CV open-land classes...", flush=True)
    land = gpd.read_file(LAND_COVER, layer="land_cover").to_crs("EPSG:3857")
    land = land[land.class_id.isin([4, 5])].copy()

    print("Building water exclusion mask...", flush=True)
    water = gpd.read_file(WATER).to_crs(land.crs)
    water_mask = water.geometry.buffer(WATER_BUFFER_M).union_all()

    print("Building settlement exclusion mask...", flush=True)
    buildings = gpd.read_file(BUILDINGS).to_crs(land.crs)
    building_mask = buildings.geometry.buffer(BUILDING_BUFFER_M).union_all()

    exclusions = gpd.GeoSeries([water_mask, building_mask], crs=land.crs).union_all()
    land.geometry = land.geometry.difference(exclusions)
    land = land.explode(index_parts=False).reset_index(drop=True)
    land = land[land.geometry.notna() & ~land.geometry.is_empty].copy()

    # Close tiny pixel notches, then remove fragments too small to represent a
    # useful open region. Do not expand beyond the source classification.
    land.geometry = land.geometry.buffer(2.0).buffer(-2.0).simplify(3.0, preserve_topology=True)
    land["area_m2"] = land.geometry.area.round(1)
    land = land[land.area_m2 >= MIN_OPEN_AREA_M2].copy()
    land["area_ha"] = (land.area_m2 / 10000).round(3)
    land["open_type"] = land.class_id.map({
        4: "Open grass / low vegetation",
        5: "Bare or sparsely vegetated open land",
    })
    land["zone_id"] = [f"OPEN_{index + 1:05d}" for index in range(len(land))]

    aoi = gpd.read_file(AOI).to_crs(land.crs)
    land = gpd.clip(land, aoi)
    OUTPUT.unlink(missing_ok=True)
    land.to_file(OUTPUT, layer="open_lands", driver="GPKG")

    print(f"Created {len(land)} refined open-land regions", flush=True)
    print(f"Total refined open area: {land.area.sum() / 1_000_000:.2f} km2", flush=True)
    print(f"Output: {OUTPUT}", flush=True)


if __name__ == "__main__":
    refine_open_lands()
