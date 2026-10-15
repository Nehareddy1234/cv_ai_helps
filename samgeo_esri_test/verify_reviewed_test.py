"""Regression checks; these are geometry/sample checks, not accuracy estimates."""
from pathlib import Path
import json
import numpy as np
import rasterio
import geopandas as gpd
from shapely.geometry import Point, box

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'output'
with rasterio.open(ROOT/'data/esri_test_aligned.tif') as src:
    image=src.read(); transform=src.transform; bounds=src.bounds
    assert src.crs.to_epsg()==32643
    assert src.shape==(1446,2660)
    assert abs(src.res[0]-.484992610681435)<1e-10
with rasterio.open(ROOT/'data/visible_esri_test.tif') as src:
    assert np.array_equal(image,src.read()), 'Alignment must not alter the source RGB pixels'
features=gpd.read_file(OUT/'reviewed_test_classes.gpkg',layer='reviewed_classes')
buildings=gpd.read_file(OUT/'reviewed_test_classes.gpkg',layer='buildings_reference')
assert features.is_valid.all()
assert not features.is_empty.any()
union=features.geometry.union_all()
assert abs(features.area.sum()-union.area)<.01
assert union.intersection(buildings.geometry.union_all()).area<.01
assert union.difference(box(*bounds)).area<.01
water=features[features.class_id==1].geometry.union_all()
samples={'reservoir':(90,1000,True),'lower_river':(560,600,True),
         'middle_river':(800,450,True),'upper_river':(1040,300,True),
         'upper_island':(1230,240,False),'middle_island':(1080,370,False),
         'exposed_bar':(600,560,False),'dry_field':(480,125,False)}
results={}
for name,(x,y,expected) in samples.items():
    px=(x-20)*2660/2005; py=(y-30)*1446/1090
    world=transform*(px,py)
    actual=water.covers(Point(*world))
    results[name]={'expected_water':expected,'actual_water':bool(actual),'passed':bool(actual==expected)}
report={'geometry_checks_passed':True,'sample_checks':results,
        'all_samples_passed':all(x['passed'] for x in results.values()),
        'note':'Handpicked visual regression points only; not a statistical accuracy assessment'}
for name,(x,y,cls) in {'central_soil':(650,860,4),'lower_left_canopy':(470,890,2)}.items():
    world=transform*((x-20)*2660/2005,(y-30)*1446/1090)
    actual=features[features.class_id==cls].geometry.union_all().covers(Point(*world))
    report.setdefault('land_sample_checks',{})[name]={'expected_class':cls,'passed':bool(actual)}
    assert actual, name
(OUT/'verification.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report,indent=2))
assert report['all_samples_passed']
