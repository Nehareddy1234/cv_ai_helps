import os
from qgis.core import (
    QgsApplication,
    QgsProject,
    QgsRasterLayer,
    QgsVectorLayer,
    QgsCoordinateReferenceSystem,
    QgsCategorizedSymbolRenderer,
    QgsRendererCategory,
    QgsSymbol,
    QgsFillSymbol,
    QgsSimpleFillSymbolLayer,
)
from PyQt6.QtGui import QColor

def build_project():
    # Initialize headless QgsApplication
    QgsApplication.setPrefixPath(r"C:\Users\Nehar\AppData\Local\Programs\OSGeo4W\apps\qgis", True)
    qgs = QgsApplication([], False)
    qgs.initQgis()

    try:
        project = QgsProject.instance()
        project.clear()
        project.setCrs(QgsCoordinateReferenceSystem("EPSG:3857"))
        project.setTitle("Bhadra Wildlife Sanctuary - SAM Geo Segmentation")

        # 1. Base Satellite Imagery Layer
        sat_path = r"C:\Users\Nehar\Desktop\HELPS\samgeo\data\bhadra_test.tif"
        sat_layer = QgsRasterLayer(sat_path, "Bhadra Satellite Imagery (Esri World Imagery)")
        if not sat_layer.isValid():
            print("Failed to load satellite layer")
        else:
            project.addMapLayer(sat_layer)
            print("Added satellite layer")

        # 2. SAM Segmentation Mask Raster
        mask_tif_path = r"C:\Users\Nehar\Desktop\HELPS\samgeo\output\bhadra_masks.tif"
        mask_layer = QgsRasterLayer(mask_tif_path, "SAM Mask (Raster)")
        if not mask_layer.isValid():
            print("Failed to load mask raster layer")
        else:
            # Set 50% opacity
            mask_layer.setOpacity(0.5)
            project.addMapLayer(mask_layer)
            print("Added mask raster layer")

        # 3. Vector Polygons Layer (GeoPackage)
        gpkg_path = r"C:\Users\Nehar\Desktop\HELPS\samgeo\output\bhadra_masks.gpkg"
        vec_layer = QgsVectorLayer(gpkg_path, "Segmented Polygons (SAM Geo)", "ogr")
        if not vec_layer.isValid():
            print("Failed to load vector GeoPackage layer")
        else:
            # Style the polygons with distinct semi-transparent colors
            categories = []
            palette = [
                QColor(230, 25, 75, 140),
                QColor(60, 180, 75, 140),
                QColor(255, 225, 25, 140),
                QColor(0, 130, 200, 140),
                QColor(245, 130, 48, 140),
                QColor(145, 30, 180, 140),
                QColor(70, 240, 240, 140),
                QColor(240, 50, 230, 140),
                QColor(210, 245, 60, 140),
                QColor(250, 190, 212, 140),
                QColor(0, 128, 128, 140),
                QColor(220, 190, 255, 140),
                QColor(170, 110, 40, 140),
                QColor(255, 250, 200, 140),
                QColor(128, 0, 0, 140),
                QColor(170, 255, 195, 140),
                QColor(128, 128, 0, 140),
            ]

            # Get unique values of value/DN field if present
            fields = [f.name() for f in vec_layer.fields()]
            val_field = "value" if "value" in fields else (fields[0] if fields else "")

            if val_field:
                unique_vals = vec_layer.uniqueValues(vec_layer.fields().indexFromName(val_field))
                for idx, val in enumerate(sorted(unique_vals)):
                    color = palette[idx % len(palette)]
                    symbol = QgsFillSymbol.createSimple({
                        'color': f'{color.red()},{color.green()},{color.blue()},{color.alpha()}',
                        'outline_color': '255,255,255,220',
                        'outline_width': '0.6',
                        'outline_style': 'solid'
                    })
                    cat = QgsRendererCategory(val, symbol, f"Segment Class {val}")
                    categories.append(cat)

                renderer = QgsCategorizedSymbolRenderer(val_field, categories)
                vec_layer.setRenderer(renderer)

            project.addMapLayer(vec_layer)
            print("Added vector polygon layer")

        # Save project
        out_project = r"C:\Users\Nehar\Desktop\HELPS\samgeo\bhadra_segmentation.qgz"
        project.write(out_project)
        print(f"Project saved successfully to: {out_project}")

    finally:
        qgs.exitQgis()

if __name__ == "__main__":
    build_project()
