from osgeo import gdal, ogr
import os

print("=== Checking bhadra_test.tif ===")
tif_path = r"C:\Users\Nehar\Desktop\HELPS\samgeo\data\bhadra_test.tif"
if os.path.exists(tif_path):
    ds = gdal.Open(tif_path)
    print(f"Dimensions: {ds.RasterXSize} x {ds.RasterYSize}, Bands: {ds.RasterCount}")
    print(f"GeoTransform: {ds.GetGeoTransform()}")
    for b in range(1, min(ds.RasterCount + 1, 5)):
        band = ds.GetRasterBand(b)
        stats = band.GetStatistics(True, True)
        print(f"  Band {b}: min={stats[0]}, max={stats[1]}, mean={stats[2]:.2f}")
else:
    print("bhadra_test.tif does not exist!")

print("\n=== Checking bhadra_masks.tif ===")
mask_tif_path = r"C:\Users\Nehar\Desktop\HELPS\samgeo\output\bhadra_masks.tif"
if os.path.exists(mask_tif_path):
    ds_m = gdal.Open(mask_tif_path)
    print(f"Dimensions: {ds_m.RasterXSize} x {ds_m.RasterYSize}, Bands: {ds_m.RasterCount}")
    band = ds_m.GetRasterBand(1)
    stats = band.GetStatistics(True, True)
    print(f"  Mask Band 1: min={stats[0]}, max={stats[1]}, mean={stats[2]:.2f}")
else:
    print("bhadra_masks.tif does not exist!")

print("\n=== Checking bhadra_masks.gpkg ===")
gpkg_path = r"C:\Users\Nehar\Desktop\HELPS\samgeo\output\bhadra_masks.gpkg"
if os.path.exists(gpkg_path):
    ds_v = ogr.Open(gpkg_path)
    layer = ds_v.GetLayer(0)
    print(f"Layer name: {layer.GetName()}, Feature count: {layer.GetFeatureCount()}")
    extent = layer.GetExtent()
    print(f"Layer extent (minX, maxX, minY, maxY): {extent}")
    spatial_ref = layer.GetSpatialRef()
    print(f"Spatial reference: {spatial_ref.GetName() if spatial_ref else 'None'}")
else:
    print("bhadra_masks.gpkg does not exist!")
