"""Create a portable, separate QGIS project without changing the open session.

Run with the installed OSGeo4W python-qgis.bat after classification succeeds.
"""
from pathlib import Path
import json
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from qgis.core import (Qgis,QgsApplication,QgsProject,QgsVectorLayer,QgsRasterLayer,
                       QgsCoordinateReferenceSystem,QgsCoordinateTransform,
                       QgsReferencedRectangle,QgsLayerMetadata)

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'output'
report=json.loads((OUT/'verification.json').read_text())
assert report['passed'], 'Classification must pass verification first'
app=QgsApplication([],False)
app.initQgis()
project=QgsProject()
project.setCrs(QgsCoordinateReferenceSystem('EPSG:32643'))
project.setFilePathStorage(Qgis.FilePathType.Relative)
project.setTitle('Whole Bhadra — SAM ViT-H broad land-cover interpretation')
# Store default styles inside the GeoPackage, so opening it without this project
# still displays the intended classes. These are newly generated layers only.
for layer_name,style_name in [('classified_regions','classified_regions'),
                              ('open_ground','classified_regions'),
                              ('combined_regions','combined_regions')]:
    styled=QgsVectorLayer(str(OUT/'bhadra_sam_vit_h_classification.gpkg')+'|layername='+layer_name,layer_name,'ogr')
    assert styled.isValid(), layer_name
    message,ok=styled.loadNamedStyle(str(OUT/(style_name+'.qml')))
    assert ok, message
    metadata=QgsLayerMetadata()
    metadata.setTitle('Whole Bhadra — provisional SAM ViT-H broad land cover')
    metadata.setAbstract('Saved project AOI, not an independently verified official reserve boundary. '
        'Esri RGB imagery at approximately 19 m pixel spacing. SAM ViT-H boundaries with explicitly '
        'tagged image-edge gap completion; semantic labels from a separate scene-trained RGB random '
        'forest. All labels require review. Individual roofs and narrow roads are not resolved. '
        'Latitude/longitude are interior points; full boundaries are stored as polygon geometry.')
    styled.setMetadata(metadata)
    error=styled.saveStyleToDatabase('whole_bhadra_'+layer_name,'Provisional broad-cover classification; review required',True,'')
    assert not error, error
    del styled
base=QgsRasterLayer(str(ROOT/'data/esri_world_imagery.tif'),'Esri World Imagery — source used for classification','gdal')
layer=QgsVectorLayer(str(OUT/'bhadra_sam_vit_h_classification.gpkg')+'|layername=classified_regions',
                     'Whole Bhadra — SAM ViT-H classes (review required)','ogr')
assert base.isValid() and layer.isValid()
message,ok=layer.loadNamedStyle(str(OUT/'classified_regions.qml'))
assert ok, message
project.addMapLayer(base)
project.addMapLayer(layer)
extent=QgsCoordinateTransform(layer.crs(),project.crs(),project).transformBoundingBox(layer.extent())
extent.scale(1.03)
project.viewSettings().setDefaultViewExtent(QgsReferencedRectangle(extent,project.crs()))
target=ROOT/'Bhadra_Whole_Region_SAM_ViT_H.qgz'
assert project.write(str(target))
check=QgsProject()
assert check.read(str(target))
assert len(check.mapLayers())==2 and all(x.isValid() for x in check.mapLayers().values())
print(json.dumps({'saved':str(target),'layers':len(check.mapLayers()),'valid':True,
                 'geopackage_default_styles':3,'project_reopened':True}),flush=True)
