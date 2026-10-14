#!/usr/bin/env python3
"""
Download cloud-free Esri World Imagery across the entire Bhadra Wildlife Sanctuary & Tiger Reserve AOI,
clipped to the official boundary defined in the HELPS Codes folder.
"""

import os
import math
import concurrent.futures
import requests
from io import BytesIO
from PIL import Image
import numpy as np
import rasterio
from rasterio.transform import from_bounds
from rasterio.mask import mask
import geopandas as gpd

# Paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BOUNDARY_PATH = os.path.join(BASE_DIR, "data", "bhadra_boundary.geojson")
OUTPUT_RAW_TIF = os.path.join(BASE_DIR, "data", "bhadra_esri_full_raw.tif")
OUTPUT_CLIPPED_TIF = os.path.join(BASE_DIR, "data", "bhadra_esri_sanctuary.tif")

# Read AOI boundary
gdf = gpd.read_file(BOUNDARY_PATH)
min_lon, min_lat, max_lon, max_lat = gdf.total_bounds
bbox = [min_lon, min_lat, max_lon, max_lat]

# Zoom 13 gives ~2304x3328 pixels (~16m resolution), ideal for full-sanctuary SAM segmentation
ZOOM = 13

def deg2num(lat_deg, lon_deg, zoom):
    lat_rad = math.radians(lat_deg)
    n = 2.0 ** zoom
    xtile = int((lon_deg + 180.0) / 360.0 * n)
    ytile = int((1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n)
    return (xtile, ytile)

def tile_bounds_merc(xtile, ytile, zoom):
    n = 2.0 ** zoom
    origin_shift = 20037508.342789244
    tile_size = 2.0 * origin_shift / n
    minx = -origin_shift + xtile * tile_size
    maxx = -origin_shift + (xtile + 1) * tile_size
    maxy = origin_shift - ytile * tile_size
    miny = origin_shift - (ytile + 1) * tile_size
    return minx, miny, maxx, maxy

def download_and_stitch():
    x1, y2 = deg2num(bbox[1], bbox[0], ZOOM)
    x2, y1 = deg2num(bbox[3], bbox[2], ZOOM)
    min_x, max_x = min(x1, x2), max(x1, x2)
    min_y, max_y = min(y1, y2), max(y1, y2)

    cols = max_x - min_x + 1
    rows = max_y - min_y + 1
    total_tiles = cols * rows
    print(f"Downloading Esri World Imagery ({cols}x{rows} = {total_tiles} tiles, Zoom {ZOOM})...")

    b_minx, b_miny, _, _ = tile_bounds_merc(min_x, max_y, ZOOM)
    _, _, b_maxx, b_maxy = tile_bounds_merc(max_x, min_y, ZOOM)

    canvas = Image.new("RGB", (cols * 256, rows * 256))
    headers = {"User-Agent": "Mozilla/5.0"}
    session = requests.Session()

    def fetch_tile(coords):
        cx, cy = coords
        url = f"https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{ZOOM}/{cy}/{cx}"
        try:
            r = session.get(url, headers=headers, timeout=10)
            if r.status_code == 200:
                img = Image.open(BytesIO(r.content)).convert("RGB")
                return (cx - min_x, cy - min_y, img)
        except Exception as e:
            print(f"Error fetching tile {cx},{cy}: {e}")
        return None

    coords_list = [(x, y) for y in range(min_y, max_y + 1) for x in range(min_x, max_x + 1)]
    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as executor:
        for res in executor.map(fetch_tile, coords_list):
            if res:
                px, py, img = res
                canvas.paste(img, (px * 256, py * 256))

    arr = np.array(canvas).transpose(2, 0, 1)
    transform = from_bounds(b_minx, b_miny, b_maxx, b_maxy, canvas.width, canvas.height)

    # Save stitched raw GeoTIFF
    with rasterio.open(
        OUTPUT_RAW_TIF,
        "w",
        driver="GTiff",
        height=canvas.height,
        width=canvas.width,
        count=3,
        dtype="uint8",
        crs="EPSG:3857",
        transform=transform,
        compress="deflate",
    ) as dst:
        dst.write(arr)

    print(f"Stitched raw Esri imagery: {canvas.width}x{canvas.height} px")

    # Clip to official Bhadra Sanctuary boundary
    print("Clipping Esri imagery to official Bhadra sanctuary boundary...")
    gdf_3857 = gdf.to_crs("EPSG:3857")
    shapes = [geom for geom in gdf_3857.geometry]

    with rasterio.open(OUTPUT_RAW_TIF) as src:
        out_image, out_transform = mask(src, shapes, crop=True, nodata=0)
        out_meta = src.meta.copy()
        out_meta.update({
            "driver": "GTiff",
            "height": out_image.shape[1],
            "width": out_image.shape[2],
            "transform": out_transform,
            "nodata": 0,
            "compress": "deflate",
        })

    with rasterio.open(OUTPUT_CLIPPED_TIF, "w", **out_meta) as dst:
        dst.write(out_image)

    size_mb = os.path.getsize(OUTPUT_CLIPPED_TIF) / (1024 * 1024)
    print(f"Successfully generated clean Esri sanctuary raster: {OUTPUT_CLIPPED_TIF} ({size_mb:.2f} MB)")

if __name__ == "__main__":
    download_and_stitch()
