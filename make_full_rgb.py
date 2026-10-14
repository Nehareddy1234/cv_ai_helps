import os
import rasterio
from rasterio.mask import mask
import geopandas as gpd
import numpy as np

spectral_path = r"C:\Users\Nehar\Desktop\HELPS\Codes\data\processed\Bhadra\sentinel2\2026-06-01\bhadra_spectral.tif"
scl_path = r"C:\Users\Nehar\Desktop\HELPS\Codes\data\processed\Bhadra\sentinel2\2026-06-01\bhadra_scl.tif"
aoi_path = r"C:\Users\Nehar\Desktop\HELPS\samgeo\data\bhadra_boundary.geojson"
output_rgb = r"C:\Users\Nehar\Desktop\HELPS\samgeo\data\bhadra_entire_rgb.tif"

print("Reading Sentinel-2 bands...")
with rasterio.open(spectral_path) as src:
    blue = src.read(1).astype(np.float32)
    green = src.read(2).astype(np.float32)
    red = src.read(3).astype(np.float32)
    profile = src.profile.copy()
    meta = src.meta.copy()

with rasterio.open(scl_path) as src:
    scl = src.read(1)

valid_mask = (scl != 0) & np.isfinite(red) & np.isfinite(green) & np.isfinite(blue)

rgb = np.stack([red, green, blue], axis=0)
rgb_u8 = np.zeros_like(rgb, dtype=np.uint8)

for i in range(3):
    band = rgb[i]
    vals = band[valid_mask & (band > 0)]
    if len(vals) > 0:
        p2 = np.percentile(vals, 2)
        p98 = np.percentile(vals, 98)
        stretched = np.clip((band - p2) / (p98 - p2), 0, 1)
        # Gamma boost for natural vegetation visibility
        stretched = np.power(stretched, 0.85)
        rgb_u8[i] = (stretched * 255).astype(np.uint8)
    rgb_u8[i][~valid_mask] = 0

profile.update(
    dtype=rasterio.uint8,
    count=3,
    compress="deflate",
    nodata=0
)

print(f"Writing entire sanctuary RGB to {output_rgb}...")
with rasterio.open(output_rgb, "w", **profile) as dst:
    dst.write(rgb_u8)

print(f"Done! Created RGB raster: {profile['width']} x {profile['height']} ({os.path.getsize(output_rgb)/(1024*1024):.1f} MB)")
