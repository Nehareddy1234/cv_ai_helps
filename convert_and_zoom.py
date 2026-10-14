from osgeo import gdal, ogr, osr
from clean_rpc import send_rpc
import os

src_geojson = r"C:\Users\Nehar\Desktop\HELPS\samgeo\data\bhadra_boundary.geojson"
dst_gpkg = r"C:\Users\Nehar\Desktop\HELPS\samgeo\data\bhadra_boundary_3857.gpkg"

# 1. Reproject GeoJSON (4326) to GPKG (3857)
ds_src = ogr.Open(src_geojson)
layer_src = ds_src.GetLayer(0)

srs_4326 = osr.SpatialReference()
srs_4326.ImportFromEPSG(4326)
srs_4326.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)

srs_3857 = osr.SpatialReference()
srs_3857.ImportFromEPSG(3857)
srs_3857.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)

coord_trans = osr.CoordinateTransformation(srs_4326, srs_3857)

driver = ogr.GetDriverByName("GPKG")
if os.path.exists(dst_gpkg):
    driver.DeleteDataSource(dst_gpkg)

ds_dst = driver.CreateDataSource(dst_gpkg)
layer_dst = ds_dst.CreateLayer("bhadra_boundary", srs_3857, ogr.wkbPolygon)

for feat in layer_src:
    geom = feat.GetGeometryRef().Clone()
    geom.Transform(coord_trans)
    feat_dst = ogr.Feature(layer_dst.GetLayerDefn())
    feat_dst.SetGeometry(geom)
    layer_dst.CreateFeature(feat_dst)

ds_dst.FlushCache()
del ds_src, ds_dst
print("Reprojected boundary to EPSG:3857 GPKG successfully!")

# 2. In QGIS, remove the old boundary layer and add the 3857 GPKG layer
send_rpc("project.action", {
    "action": "remove_layer",
    "layer": "Bhadra_Sanctuary_Boundary__HELPS_AOI__761b98d4_4597_4d5f_8822_0ccd089f02db"
})

r_add = send_rpc("project.action", {
    "action": "add_vector",
    "source": dst_gpkg,
    "name": "Bhadra Sanctuary Boundary (HELPS AOI)"
})
print("Added 3857 boundary layer:", r_add)
new_id = r_add.get("result", {}).get("id")

if new_id:
    # Load QML style
    qml_path = r"C:\Users\Nehar\Desktop\HELPS\samgeo\bhadra_boundary.qml"
    send_rpc("project.action", {
        "action": "load_style",
        "layer": new_id,
        "path": qml_path
    })
    # Move to top
    send_rpc("layer.manage", {
        "action": "move_layer",
        "layer": new_id,
        "index": 0
    })

# 3. Zoom canvas to the full 3857 extent with 5% margin
extent_3857 = [8401000.0, 1492000.0, 8444000.0, 1556000.0]
r_zoom = send_rpc("canvas.control", {
    "action": "set_extent",
    "extent": extent_3857,
    "crs": "EPSG:3857"
})
print("Canvas zoom set to full sanctuary:", r_zoom)

send_rpc("project.action", {"action": "refresh"})
send_rpc("project.action", {"action": "save"})
print("Project updated, saved, and ready!")
