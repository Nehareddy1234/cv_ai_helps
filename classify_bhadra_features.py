#!/usr/bin/env python3
"""
Generate detailed classifications for:
1. Buildings
2. Industrial Area
3. Water Areas
across the entire Bhadra Wildlife Sanctuary & Tiger Reserve AOI,
and add them with rich cartography into QGIS.
"""

import os
import json
import rasterio
import numpy as np
import geopandas as gpd
from rasterio.mask import mask
from shapely.geometry import shape, Polygon, MultiPolygon
from clean_rpc import send_rpc

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
AOI_PATH = os.path.join(BASE_DIR, "data", "bhadra_boundary.geojson")
ESRI_TIF = os.path.join(BASE_DIR, "data", "bhadra_esri_sanctuary.tif")
SAM_GPKG = os.path.join(BASE_DIR, "output", "bhadra_esri_masks.gpkg")

# Codes folder reference paths
CODES_DIR = r"C:\Users\Nehar\Desktop\HELPS\Codes"
BUILDINGS_GEOJSON = os.path.join(CODES_DIR, "data", "processed", "Bhadra", "buildings", "bhadra_overture_buildings.geojson")
OSM_CONTEXT_GPKG = os.path.join(CODES_DIR, "data", "processed", "Bhadra", "osm", "bhadra_osm_context.gpkg")
OSM_INPUT_GPKG = os.path.join(CODES_DIR, "data", "inputs", "45295356fafbdae35c06ddec", "2026-06-01", "osm.gpkg")

# Output classification paths
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
WATER_GPKG = os.path.join(OUTPUT_DIR, "bhadra_classified_water.gpkg")
INDUSTRIAL_GPKG = os.path.join(OUTPUT_DIR, "bhadra_classified_industrial.gpkg")
BUILDINGS_GPKG = os.path.join(OUTPUT_DIR, "bhadra_classified_buildings.gpkg")
MASTER_GPKG = os.path.join(OUTPUT_DIR, "bhadra_thematic_master.gpkg")

def run_classification():
    print("=" * 65, flush=True)
    print("Classifying Buildings, Industrial Area, and Water Areas in Bhadra AOI", flush=True)
    print("=" * 65, flush=True)

    # 1. Load AOI Boundary (EPSG:3857)
    gdf_aoi = gpd.read_file(AOI_PATH).to_crs("EPSG:3857")

    # -------------------------------------------------------------------------
    # 2. Extract & Classify WATER AREAS
    # -------------------------------------------------------------------------
    print("Processing Water Areas (Bhadra Reservoir, Rivers, Waterbodies)...", flush=True)
    water_geoms = []

    # From bhadra_osm_context.gpkg
    if os.path.exists(OSM_CONTEXT_GPKG):
        try:
            g_w = gpd.read_file(OSM_CONTEXT_GPKG, layer="water_polygons").to_crs("EPSG:3857")
            g_w = g_w[g_w.geometry.geom_type.isin(["Polygon", "MultiPolygon"])]
            water_geoms.extend(list(g_w.geometry))
        except Exception as e:
            print(f"Notice (water_polygons): {e}", flush=True)

    # From osm.gpkg
    if os.path.exists(OSM_INPUT_GPKG):
        try:
            g_w2 = gpd.read_file(OSM_INPUT_GPKG, layer="water").to_crs("EPSG:3857")
            g_w2 = g_w2[g_w2.geometry.geom_type.isin(["Polygon", "MultiPolygon"])]
            water_geoms.extend(list(g_w2.geometry))
        except Exception as e:
            print(f"Notice (water): {e}", flush=True)

    # From SamGeo spectral detection (dark water pixels in reservoir)
    if os.path.exists(SAM_GPKG) and os.path.exists(ESRI_TIF):
        gdf_sam = gpd.read_file(SAM_GPKG).to_crs("EPSG:3857")
        with rasterio.open(ESRI_TIF) as src:
            for idx, row in gdf_sam.iterrows():
                geom = row.geometry
                if geom.area > 200000: # large candidate reservoir/water bodies (>20 ha)
                    try:
                        out_img, _ = mask(src, [geom], crop=True, nodata=0)
                        valid = out_img[0] > 0
                        if np.any(valid):
                            mean_r = np.mean(out_img[0][valid])
                            mean_g = np.mean(out_img[1][valid])
                            mean_b = np.mean(out_img[2][valid])
                            # Deep water signature: dark reflectance across R, G, B
                            if mean_r < 45 and mean_g < 55 and mean_b < 70:
                                water_geoms.append(geom)
                    except Exception:
                        pass

    gdf_water = gpd.GeoDataFrame({"geometry": water_geoms}, crs="EPSG:3857")
    if not gdf_water.empty:
        gdf_water = gpd.clip(gdf_water, gdf_aoi)
        gdf_water = gdf_water.dissolve()
        gdf_water = gdf_water.explode(index_parts=False).reset_index(drop=True)
        gdf_water = gdf_water[gdf_water.geometry.area > 500]
        gdf_water["class_name"] = "Water Area"
        gdf_water["feature_type"] = gdf_water.geometry.area.apply(
            lambda a: "Bhadra Reservoir" if a > 5000000 else ("Major Waterbody" if a > 50000 else "Pond / Stream")
        )
        gdf_water["area_ha"] = (gdf_water.geometry.area / 10000.0).round(2)
        gdf_water["area_km2"] = (gdf_water.geometry.area / 1000000.0).round(3)
        gdf_water.to_file(WATER_GPKG, driver="GPKG", layer="water_areas")
        print(f"[OK] Water Areas saved: {len(gdf_water)} features, total water area: {gdf_water['area_km2'].sum():.2f} km²", flush=True)

    # -------------------------------------------------------------------------
    # 3. Extract & Classify INDUSTRIAL AREA
    # -------------------------------------------------------------------------
    print("Processing Industrial Areas (Quarries, Power Infrastructure, Plants)...", flush=True)
    ind_records = []

    if os.path.exists(OSM_INPUT_GPKG):
        try:
            g_ind = gpd.read_file(OSM_INPUT_GPKG, layer="industrial").to_crs("EPSG:3857")
            for _, r in g_ind.iterrows():
                attr = json.loads(r["attributes"]) if isinstance(r["attributes"], str) else {}
                landuse = attr.get("landuse", "industrial")
                ind_records.append({
                    "geometry": r.geometry,
                    "class_name": "Industrial Area",
                    "feature_type": f"Industrial ({landuse.capitalize()})",
                    "name": attr.get("name", "Industrial Zone")
                })
        except Exception as e:
            print(f"Notice (industrial): {e}", flush=True)

        try:
            g_pwr = gpd.read_file(OSM_INPUT_GPKG, layer="power").to_crs("EPSG:3857")
            g_pwr_poly = g_pwr[g_pwr.geometry.geom_type.isin(["Polygon", "MultiPolygon"])]
            for _, r in g_pwr_poly.iterrows():
                attr = json.loads(r["attributes"]) if isinstance(r["attributes"], str) else {}
                ind_records.append({
                    "geometry": r.geometry,
                    "class_name": "Industrial Area",
                    "feature_type": "Power Substation / Generating Station",
                    "name": attr.get("name", "Power Facility")
                })
        except Exception as e:
            print(f"Notice (power): {e}", flush=True)

    # Add Bhadra Dam infrastructure zone (large hydro-electric facility)
    # Dam coordinate approx (75.641, 13.700) in EPSG:3857
    dam_zone = Polygon([
        (8419600, 1539600), (8420600, 1539600), (8420600, 1540800), (8419600, 1540800)
    ])
    ind_records.append({
        "geometry": dam_zone,
        "class_name": "Industrial Area",
        "feature_type": "Bhadra Hydro-Electric Dam & Power Infrastructure",
        "name": "Bhadra Dam Works"
    })

    gdf_ind = gpd.GeoDataFrame(ind_records, crs="EPSG:3857")
    if not gdf_ind.empty:
        gdf_ind = gpd.clip(gdf_ind, gdf_aoi)
        gdf_ind = gdf_ind.explode(index_parts=False).reset_index(drop=True)
        gdf_ind["area_ha"] = (gdf_ind.geometry.area / 10000.0).round(2)
        gdf_ind.to_file(INDUSTRIAL_GPKG, driver="GPKG", layer="industrial_areas")
        print(f"[OK] Industrial Areas saved: {len(gdf_ind)} features ({gdf_ind['area_ha'].sum():.2f} ha)", flush=True)

    # -------------------------------------------------------------------------
    # 4. Extract & Classify BUILDINGS
    # -------------------------------------------------------------------------
    print("Processing Buildings & Built-up Structures...", flush=True)
    if os.path.exists(BUILDINGS_GEOJSON):
        gdf_bld = gpd.read_file(BUILDINGS_GEOJSON).to_crs("EPSG:3857")
        gdf_bld = gpd.clip(gdf_bld, gdf_aoi)
        gdf_bld = gdf_bld.explode(index_parts=False).reset_index(drop=True)
        gdf_bld["class_name"] = "Buildings"
        gdf_bld["feature_type"] = gdf_bld["class"].fillna("Building Structure")
        gdf_bld["area_m2"] = gdf_bld.geometry.area.round(1)
        # Select clean columns
        keep_cols = ["class_name", "feature_type", "area_m2", "geometry"]
        gdf_bld = gdf_bld[keep_cols]
        gdf_bld.to_file(BUILDINGS_GPKG, driver="GPKG", layer="buildings")
        print(f"[OK] Buildings saved: {len(gdf_bld)} individual building footprints", flush=True)
    else:
        gdf_bld = gpd.GeoDataFrame(columns=["geometry", "class_name", "feature_type", "area_m2"], crs="EPSG:3857")

    # -------------------------------------------------------------------------
    # 5. Build Master Thematic Classification GeoPackage
    # -------------------------------------------------------------------------
    print("Building Master Thematic Classification Layer...", flush=True)
    master_records = []
    for _, r in gdf_water.iterrows():
        master_records.append({
            "geometry": r.geometry,
            "category": "Water Areas",
            "class_id": 1,
            "description": r["feature_type"],
            "area_ha": r["area_ha"]
        })
    for _, r in gdf_ind.iterrows():
        master_records.append({
            "geometry": r.geometry,
            "category": "Industrial Area",
            "class_id": 2,
            "description": r["feature_type"],
            "area_ha": r["area_ha"]
        })

    # Cluster or buffer buildings for thematic regional representation
    if not gdf_bld.empty:
        # Building clusters (buffer & dissolve) for regional polygon coverage
        bld_union = gdf_bld.geometry.buffer(15).union_all()
        gdf_bld_clusters = gpd.GeoDataFrame({"geometry": [bld_union]}, crs="EPSG:3857").explode(index_parts=False)
        gdf_bld_clusters = gdf_bld_clusters[gdf_bld_clusters.geometry.area > 200]
        for _, r in gdf_bld_clusters.iterrows():
            master_records.append({
                "geometry": r.geometry,
                "category": "Buildings & Settlements",
                "class_id": 3,
                "description": "Building Clusters & Settlements",
                "area_ha": round(r.geometry.area / 10000.0, 2)
            })

    gdf_master = gpd.GeoDataFrame(master_records, crs="EPSG:3857")
    gdf_master.to_file(MASTER_GPKG, driver="GPKG", layer="thematic_classifications")
    print(f"[OK] Master Thematic Layer saved: {MASTER_GPKG} ({len(gdf_master)} features)", flush=True)

    # -------------------------------------------------------------------------
    # 6. Apply to Live QGIS Session
    # -------------------------------------------------------------------------
    print("\nApplying classified layers to live QGIS session...", flush=True)
    snap = send_rpc("session.snapshot", {"detail": "summary"})
    existing_layers = {l.get("name"): l.get("id") for l in snap.get("result", {}).get("layers", [])}

    # Add Water Areas
    r_w = send_rpc("project.action", {
        "action": "add_vector",
        "source": WATER_GPKG,
        "name": "Water Areas (Reservoir & Rivers)"
    })
    water_id = r_w.get("result", {}).get("id")
    if water_id:
        send_rpc("cartography.style", {
            "layer": water_id,
            "mode": "simple",
            "color": "#0288D1",
            "opacity": 0.65,
            "width": 1.4
        })

    # Add Industrial Areas
    r_i = send_rpc("project.action", {
        "action": "add_vector",
        "source": INDUSTRIAL_GPKG,
        "name": "Industrial Areas (Quarries & Facilities)"
    })
    ind_id = r_i.get("result", {}).get("id")
    if ind_id:
        send_rpc("cartography.style", {
            "layer": ind_id,
            "mode": "simple",
            "color": "#FF6F00",
            "opacity": 0.70,
            "width": 1.6
        })

    # Add Buildings
    r_b = send_rpc("project.action", {
        "action": "add_vector",
        "source": BUILDINGS_GPKG,
        "name": "Classified Buildings (Footprints)"
    })
    bld_id = r_b.get("result", {}).get("id")
    if bld_id:
        send_rpc("cartography.style", {
            "layer": bld_id,
            "mode": "simple",
            "color": "#E53935",
            "opacity": 0.85,
            "width": 0.8
        })

    # Order layers (Top to bottom):
    # 0. Boundary
    # 1. Buildings (Points / small footprints on top)
    # 2. Industrial Areas
    # 3. Water Areas
    # 4. SamGeo General Segmentations
    # 5. Esri Basemap
    boundary_id = existing_layers.get("Bhadra Sanctuary Boundary (HELPS AOI)")
    if boundary_id:
        send_rpc("layer.manage", {"action": "move_layer", "layer": boundary_id, "index": 0})
    if bld_id:
        send_rpc("layer.manage", {"action": "move_layer", "layer": bld_id, "index": 1})
    if ind_id:
        send_rpc("layer.manage", {"action": "move_layer", "layer": ind_id, "index": 2})
    if water_id:
        send_rpc("layer.manage", {"action": "move_layer", "layer": water_id, "index": 3})

    send_rpc("project.action", {"action": "refresh"})
    send_rpc("project.action", {"action": "save"})
    print("[SUCCESS] All classified layers loaded, styled, and saved in QGIS!", flush=True)

if __name__ == "__main__":
    run_classification()
