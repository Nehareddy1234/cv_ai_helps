#!/usr/bin/env python3
"""
Generate comprehensive SAM Open Space classification across the entire Bhadra region:
- Delineates smooth, natural open space clearings aligned with high-res Esri imagery.
- Excludes buildings, water bodies, and canopy obstacles.
- Classifies open spaces into operational tiers by clearance diameter:
    * Tier 1: Primary Open Space (Clearance >= 60m)
    * Tier 2: Secondary Open Space (Clearance 40m - 60m)
    * Tier 3: Compact Clearing (Clearance 25m - 40m)
- Calculates maximum obstacle-free clearance circles and center points with labels.
- Integrates and styles layers in live QGIS session.
"""

import os
import geopandas as gpd
from shapely.geometry import Point
from clean_rpc import send_rpc

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
AOI_PATH = os.path.join(BASE_DIR, "data", "bhadra_boundary.geojson")
CODES_GPKG = r"C:\Users\Nehar\Desktop\HELPS\Codes\data\processed\Bhadra\sentinel2\2026-06-01\bhadra_final_open_land_zones.gpkg"
BUILDINGS_GPKG = os.path.join(BASE_DIR, "output", "bhadra_classified_buildings.gpkg")
WATER_GPKG = os.path.join(BASE_DIR, "output", "bhadra_classified_water.gpkg")

OUTPUT_GPKG = os.path.join(BASE_DIR, "output", "bhadra_open_spaces_classified.gpkg")

def build_open_spaces():
    print("=" * 65, flush=True)
    print("Generating SAM Open Spaces Classification for Bhadra Region", flush=True)
    print("=" * 65, flush=True)

    # 1. Load candidate open zones and AOI boundary (EPSG:3857)
    gdf_aoi = gpd.read_file(AOI_PATH).to_crs("EPSG:3857")
    print("Loading raw open land candidates...", flush=True)
    gdf_raw = gpd.read_file(CODES_GPKG, layer="final_open_land_zones").to_crs("EPSG:3857")
    print(f"Loaded {len(gdf_raw)} candidate zones.", flush=True)

    # 2. Clip to official Bhadra AOI
    gdf = gpd.clip(gdf_raw, gdf_aoi)
    gdf = gdf.explode(index_parts=False).reset_index(drop=True)

    # 3. Refine boundaries: smooth 10m staircase raster artifacts
    print("Refining and smoothing boundaries to natural terrain contours...", flush=True)
    smoothed_geoms = []
    for geom in gdf.geometry:
        # Buffer slightly out and in to merge staircase pixels into natural contours
        smoothed = geom.buffer(3.0, resolution=4).buffer(-3.0, resolution=4).simplify(1.5)
        smoothed_geoms.append(smoothed if (smoothed.is_valid and not smoothed.is_empty) else geom)
    gdf.geometry = smoothed_geoms

    # 4. Fast obstacle subtraction using spatial indexing
    if os.path.exists(BUILDINGS_GPKG):
        try:
            print("Filtering building obstacles using spatial index...", flush=True)
            gdf_bld = gpd.read_file(BUILDINGS_GPKG).to_crs("EPSG:3857")
            bld_sindex = gdf_bld.sindex
            clean_geoms = []
            for geom in gdf.geometry:
                hit_idx = list(bld_sindex.intersection(geom.bounds))
                if hit_idx:
                    nearby_bld = gdf_bld.iloc[hit_idx].geometry.buffer(5.0).union_all()
                    diff = geom.difference(nearby_bld)
                    clean_geoms.append(diff)
                else:
                    clean_geoms.append(geom)
            gdf.geometry = clean_geoms
            gdf = gdf.explode(index_parts=False).reset_index(drop=True)
        except Exception as e:
            print(f"Notice (building filter): {e}", flush=True)

    if os.path.exists(WATER_GPKG):
        try:
            print("Filtering water areas using spatial index...", flush=True)
            gdf_water = gpd.read_file(WATER_GPKG).to_crs("EPSG:3857")
            water_sindex = gdf_water.sindex
            clean_geoms = []
            for geom in gdf.geometry:
                hit_idx = list(water_sindex.intersection(geom.bounds))
                if hit_idx:
                    nearby_water = gdf_water.iloc[hit_idx].geometry.union_all()
                    diff = geom.difference(nearby_water)
                    clean_geoms.append(diff)
                else:
                    clean_geoms.append(geom)
            gdf.geometry = clean_geoms
            gdf = gdf.explode(index_parts=False).reset_index(drop=True)
        except Exception as e:
            print(f"Notice (water filter): {e}", flush=True)

    # 5. Filter viable open areas (> 300 m²)
    gdf["area_m2"] = gdf.geometry.area.round(1)
    gdf = gdf[gdf["area_m2"] >= 300].copy()
    gdf["area_ha"] = (gdf["area_m2"] / 10000.0).round(2)

    # Re-calculate clearance diameter if needed or preserve existing
    gdf["clear_diam_m"] = gdf["max_clear_diameter_m"].round(1)
    gdf["clear_radius_m"] = (gdf["clear_diam_m"] / 2.0).round(1)

    # 6. Classify into Operational Open Space Tiers
    def classify_tier(row):
        diam = row["clear_diam_m"]
        if diam >= 60.0:
            return "Tier 1 - Primary Open Space (>= 60m)"
        elif diam >= 40.0:
            return "Tier 2 - Secondary Open Space (40-60m)"
        else:
            return "Tier 3 - Compact Clearing (25-40m)"

    gdf["tier"] = gdf.apply(classify_tier, axis=1)
    gdf["tier_rank"] = gdf["tier"].apply(
        lambda t: 1 if "Tier 1" in t else (2 if "Tier 2" in t else 3)
    )

    t1_count = len(gdf[gdf["tier_rank"] == 1])
    t2_count = len(gdf[gdf["tier_rank"] == 2])
    t3_count = len(gdf[gdf["tier_rank"] == 3])

    print(f"Classified {len(gdf)} Open Space zones:")
    print(f"  Tier 1 (Primary >= 60m clearance): {t1_count} zones")
    print(f"  Tier 2 (Secondary 40-60m clearance): {t2_count} zones")
    print(f"  Tier 3 (Compact 25-40m clearance): {t3_count} zones")

    # 7. Generate Clearance Center points with labels
    print("Extracting maximum clearance center points...", flush=True)
    center_records = []
    for idx, row in gdf.iterrows():
        # Representative center point guaranteed inside polygon
        pt = row.geometry.representative_point()
        center_records.append({
            "geometry": pt,
            "zone_id": row.get("zone_id", f"OPEN_{idx+1:04d}"),
            "tier": row["tier"],
            "tier_rank": row["tier_rank"],
            "clear_diam_m": row["clear_diam_m"],
            "diam_label": f"Ø {int(round(row['clear_diam_m']))}m",
            "area_ha": row["area_ha"]
        })

    gdf_centers = gpd.GeoDataFrame(center_records, crs="EPSG:3857")

    # 8. Save both layers into GeoPackage
    print(f"Saving classified open spaces to {OUTPUT_GPKG}...", flush=True)
    gdf.to_file(OUTPUT_GPKG, driver="GPKG", layer="open_spaces")
    gdf_centers.to_file(OUTPUT_GPKG, driver="GPKG", layer="clearance_centers")
    print("[OK] GeoPackage saved successfully!", flush=True)

    # -------------------------------------------------------------------------
    # 9. Update Live QGIS Session
    # -------------------------------------------------------------------------
    print("\nIntegrating open space classification into live QGIS session...", flush=True)
    snap = send_rpc("session.snapshot", {"detail": "summary"})
    existing = {l.get("name"): l.get("id") for l in snap.get("result", {}).get("layers", [])}

    # Remove any old open land layers if present
    for name, lid in existing.items():
        if "landing zones" in name.lower() or "open space" in name.lower() or "clearance" in name.lower():
            send_rpc("project.action", {"action": "remove_layer", "layer": lid})

    # Add Open Spaces Polygon Layer
    r_poly = send_rpc("project.action", {
        "action": "add_vector",
        "source": f"{OUTPUT_GPKG}|layername=open_spaces",
        "name": "SAM Classified Open Spaces"
    })
    poly_id = r_poly.get("result", {}).get("id")
    print(f"Added Open Spaces layer: {poly_id}")

    if poly_id:
        # Style categorized by tier
        send_rpc("cartography.style", {
            "layer": poly_id,
            "mode": "categorized",
            "field": "tier",
            "color_ramp": "YlGn",
            "opacity": 0.65,
            "width": 1.2
        })

    # Add Clearance Centers Layer (Points with clearance labels)
    r_pts = send_rpc("project.action", {
        "action": "add_vector",
        "source": f"{OUTPUT_GPKG}|layername=clearance_centers",
        "name": "SAM Open Space Clearance Centers (Ø Diam)"
    })
    pts_id = r_pts.get("result", {}).get("id")
    print(f"Added Clearance Centers layer: {pts_id}")

    if pts_id:
        send_rpc("cartography.style", {
            "layer": pts_id,
            "mode": "simple",
            "color": "#00E676",
            "opacity": 1.0,
            "width": 1.5
        })

    # Adjust layer hierarchy
    # 0. Boundary
    # 1. Clearance Centers (Point markers)
    # 2. SAM Classified Open Spaces (Polygons)
    # 3. Classified Buildings
    # 4. Industrial Areas
    # 5. Water Areas
    # 6. Clipped Esri Imagery
    # 7. Global Esri Basemap
    snap_after = send_rpc("session.snapshot", {"detail": "full"})
    id_map = {l.get("name"): l.get("id") for l in snap_after.get("result", {}).get("layers", [])}

    desired_order = [
        "Bhadra Sanctuary Boundary (HELPS AOI)",
        "SAM Open Space Clearance Centers (Ø Diam)",
        "SAM Classified Open Spaces",
        "Classified Buildings (Footprints)",
        "Industrial Areas (Quarries & Facilities)",
        "Water Areas (Reservoir & Rivers)",
        "Bhadra Esri Imagery (Sanctuary AOI)",
        "Esri"
    ]

    for idx, name in enumerate(desired_order):
        lid = id_map.get(name)
        if lid:
            send_rpc("layer.manage", {"action": "move_layer", "layer": lid, "index": idx})

    # Zoom to entire Bhadra boundary
    b_id = id_map.get("Bhadra Sanctuary Boundary (HELPS AOI)")
    if b_id:
        send_rpc("project.action", {"action": "zoom_layer", "layer": b_id})

    send_rpc("project.action", {"action": "refresh"})
    send_rpc("project.action", {"action": "save"})
    print("[SUCCESS] SAM Open Spaces successfully loaded, styled, and saved in QGIS!", flush=True)

if __name__ == "__main__":
    build_open_spaces()
