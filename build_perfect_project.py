import os
import zipfile
from xml.etree import ElementTree as ET

from qgis.core import (
    QgsApplication,
    QgsProject,
    QgsRasterLayer,
    QgsVectorLayer,
    QgsCoordinateReferenceSystem,
    QgsCategorizedSymbolRenderer,
    QgsRendererCategory,
    QgsFillSymbol,
    QgsRectangle,
    QgsMultiBandColorRenderer,
    QgsContrastEnhancement,
)
from PyQt6.QtGui import QColor

def create_project():
    QgsApplication.setPrefixPath(r"C:\Users\Nehar\AppData\Local\Programs\OSGeo4W\apps\qgis", True)
    qgs = QgsApplication([], False)
    qgs.initQgis()

    try:
        project = QgsProject.instance()
        project.clear()
        crs = QgsCoordinateReferenceSystem("EPSG:3857")
        project.setCrs(crs)
        project.setTitle("Bhadra Wildlife Sanctuary - SAM Geo Segmentation")

        # 1. Base OpenStreetMap XYZ Layer (for geographic context)
        osm_url = "type=xyz&url=https://tile.openstreetmap.org/{z}/{x}/{y}.png&zmax=19&zmin=0"
        osm_layer = QgsRasterLayer(osm_url, "OpenStreetMap (Global Context)", "wms")
        if osm_layer.isValid():
            project.addMapLayer(osm_layer, False)
            print("Added OpenStreetMap layer")

        # 2. High-res Satellite Imagery (Bhadra test patch)
        sat_path = r"C:\Users\Nehar\Desktop\HELPS\samgeo\data\bhadra_test.tif"
        sat_layer = QgsRasterLayer(sat_path, "Bhadra Satellite Imagery (Esri World Imagery)")
        if sat_layer.isValid():
            # Setup RGB MultiBandColorRenderer
            provider = sat_layer.dataProvider()
            renderer = QgsMultiBandColorRenderer(provider, 1, 2, 3)
            # Enhance contrast
            for b in [1, 2, 3]:
                ce = QgsContrastEnhancement(provider.dataType(b))
                ce.setContrastEnhancementAlgorithm(QgsContrastEnhancement.StretchToMinimumMaximum)
                stats = provider.bandStatistics(b)
                ce.setMinimumValue(stats.minimumValue)
                ce.setMaximumValue(stats.maximumValue)
                if b == 1:
                    renderer.setRedContrastEnhancement(ce)
                elif b == 2:
                    renderer.setGreenContrastEnhancement(ce)
                elif b == 3:
                    renderer.setBlueContrastEnhancement(ce)
            sat_layer.setRenderer(renderer)
            project.addMapLayer(sat_layer, False)
            print("Added satellite imagery layer")

        # 3. SAM Masks Raster (toggleable, default off)
        mask_path = r"C:\Users\Nehar\Desktop\HELPS\samgeo\output\bhadra_masks.tif"
        mask_layer = QgsRasterLayer(mask_path, "SAM Mask (Raster Overlay)")
        if mask_layer.isValid():
            mask_layer.setOpacity(0.4)
            project.addMapLayer(mask_layer, False)
            print("Added mask raster layer")

        # 4. SAM Vector Polygons (GeoPackage)
        gpkg_path = r"C:\Users\Nehar\Desktop\HELPS\samgeo\output\bhadra_masks.gpkg"
        vec_layer = QgsVectorLayer(gpkg_path, "Segmented Polygons (SAM Geo)", "ogr")
        if vec_layer.isValid():
            palette = [
                QColor(230, 25, 75, 160),
                QColor(60, 180, 75, 160),
                QColor(255, 225, 25, 160),
                QColor(0, 130, 200, 160),
                QColor(245, 130, 48, 160),
                QColor(145, 30, 180, 160),
                QColor(70, 240, 240, 160),
                QColor(240, 50, 230, 160),
                QColor(210, 245, 60, 160),
                QColor(250, 190, 212, 160),
                QColor(0, 128, 128, 160),
                QColor(220, 190, 255, 160),
                QColor(170, 110, 40, 160),
                QColor(255, 250, 200, 160),
                QColor(128, 0, 0, 160),
                QColor(170, 255, 195, 160),
                QColor(128, 128, 0, 160),
            ]
            fields = [f.name() for f in vec_layer.fields()]
            val_field = "value" if "value" in fields else (fields[0] if fields else "")
            categories = []
            if val_field:
                unique_vals = vec_layer.uniqueValues(vec_layer.fields().indexFromName(val_field))
                for idx, val in enumerate(sorted(unique_vals)):
                    c = palette[idx % len(palette)]
                    symbol = QgsFillSymbol.createSimple({
                        'color': f'{c.red()},{c.green()},{c.blue()},{c.alpha()}',
                        'outline_color': '255,255,255,230',
                        'outline_width': '0.7',
                        'outline_style': 'solid'
                    })
                    categories.append(QgsRendererCategory(val, symbol, f"Segment Class {val}"))
                vec_layer.setRenderer(QgsCategorizedSymbolRenderer(val_field, categories))

            project.addMapLayer(vec_layer, False)
            print("Added vector polygon layer")

        # Configure Layer Tree (Top to Bottom):
        # 1. Vector Polygons (Checked)
        # 2. SAM Mask Raster (Unchecked by default so user can toggle)
        # 3. Satellite Imagery (Checked)
        # 4. OpenStreetMap (Checked)
        root = project.layerTreeRoot()
        root.clear()

        node_vec = root.addLayer(vec_layer)
        node_vec.setItemVisibilityChecked(True)

        node_mask = root.addLayer(mask_layer)
        node_mask.setItemVisibilityChecked(False)  # Unchecked so satellite is visible directly

        node_sat = root.addLayer(sat_layer)
        node_sat.setItemVisibilityChecked(True)

        if osm_layer.isValid():
            node_osm = root.addLayer(osm_layer)
            node_osm.setItemVisibilityChecked(True)

        # Set default view extent to Bhadra satellite imagery extent
        from qgis.core import QgsReferencedRectangle
        extent = sat_layer.extent()
        extent.grow(extent.width() * 0.05)  # 5% padding around area
        ref_rect = QgsReferencedRectangle(extent, crs)
        project.viewSettings().setDefaultViewExtent(ref_rect)
        project.viewSettings().setPresetFullExtent(ref_rect)
        project.viewSettings().setRestoreProjectExtentOnProjectLoad(True)

        # Save project as uncompressed .qgs first so we can ensure <mapcanvas> tag is present
        qgs_path = r"C:\Users\Nehar\Desktop\HELPS\samgeo\bhadra_segmentation.qgs"
        project.write(qgs_path)

        # Now inject explicit <mapcanvas> into .qgs
        with open(qgs_path, "r", encoding="utf-8") as f:
            content = f.read()

        mapcanvas_xml = f"""
  <mapcanvas>
    <units>meters</units>
    <extent>
      <xmin>{extent.xMinimum():.6f}</xmin>
      <ymin>{extent.yMinimum():.6f}</ymin>
      <xmax>{extent.xMaximum():.6f}</xmax>
      <ymax>{extent.yMaximum():.6f}</ymax>
    </extent>
    <rotation>0</rotation>
    <destinationsrs>
      <spatialrefsys nativeFormat="Wkt">
        <wkt>PROJCRS["WGS 84 / Pseudo-Mercator",BASEGEOGCRS["WGS 84",ENSEMBLE["World Geodetic System 1984 ensemble",MEMBER["World Geodetic System 1984 (Transit)"],MEMBER["World Geodetic System 1984 (G730)"],MEMBER["World Geodetic System 1984 (G873)"],MEMBER["World Geodetic System 1984 (G1150)"],MEMBER["World Geodetic System 1984 (G1674)"],MEMBER["World Geodetic System 1984 (G1762)"],MEMBER["World Geodetic System 1984 (G2139)"],MEMBER["World Geodetic System 1984 (G2296)"],ELLIPSOID["WGS 84",6378137,298.257223563,LENGTHUNIT["metre",1]],ENSEMBLEACCURACY[2.0]],PRIMEM["Greenwich",0,ANGLEUNIT["degree",0.0174532925199433]],ID["EPSG",4326]],CONVERSION["Popular Visualisation Pseudo-Mercator",METHOD["Popular Visualisation Pseudo Mercator",ID["EPSG",1024]],PARAMETER["Latitude of natural origin",0,ANGLEUNIT["degree",0.0174532925199433],ID["EPSG",8801]],PARAMETER["Longitude of natural origin",0,ANGLEUNIT["degree",0.0174532925199433],ID["EPSG",8802]],PARAMETER["False easting",0,LENGTHUNIT["metre",1],ID["EPSG",8806]],PARAMETER["False northing",0,LENGTHUNIT["metre",1],ID["EPSG",8807]],ID["EPSG",3857]],CS[Cartesian,2],AXIS["easting (X)",east,ORDER[1],LENGTHUNIT["metre",1]],AXIS["northing (Y)",north,ORDER[2],LENGTHUNIT["metre",1]],USAGE[SCOPE["Web mapping and visualisation."],AREA["World between 85.06°S and 85.06°N."],BBOX[-85.06,-180,85.06,180]],ID["EPSG",3857]]</wkt>
        <proj4>+proj=merc +a=6378137 +b=6378137 +lat_ts=0 +lon_0=0 +x_0=0 +y_0=0 +k=1 +units=m +nadgrids=@null +wktext +no_defs</proj4>
        <srsid>3857</srsid>
        <srid>3857</srid>
        <authid>EPSG:3857</authid>
        <description>WGS 84 / Pseudo-Mercator</description>
        <projectionacronym>merc</projectionacronym>
        <ellipsoidacronym>EPSG:7030</ellipsoidacronym>
        <geographicflag>false</geographicflag>
      </spatialrefsys>
    </destinationsrs>
    <rendermaptile>0</rendermaptile>
  </mapcanvas>
"""
        # Insert before </qgis>
        if "</qgis>" in content and "<mapcanvas>" not in content:
            content = content.replace("</qgis>", f"{mapcanvas_xml}\n</qgis>")
            with open(qgs_path, "w", encoding="utf-8") as f:
                f.write(content)
            print("Injected mapcanvas XML successfully into .qgs")

        # Package into .qgz as well
        qgz_path = r"C:\Users\Nehar\Desktop\HELPS\samgeo\bhadra_segmentation.qgz"
        with zipfile.ZipFile(qgz_path, "w", zipfile.ZIP_DEFLATED) as z:
            z.write(qgs_path, "bhadra_segmentation.qgs")
        print("Updated bhadra_segmentation.qgz with mapcanvas & view settings")

    finally:
        qgs.exitQgis()

if __name__ == "__main__":
    create_project()
