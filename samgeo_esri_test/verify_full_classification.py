"""Integrity and handpicked visual regression checks, not field accuracy."""
from pathlib import Path
import hashlib
import json
import numpy as np
import rasterio
from rasterio.features import rasterize
import geopandas as gpd

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'output/full_classification'

def main():
    basepath=ROOT/'output/full_rectangle/unlabelled_regions.gpkg'
    report=json.loads((OUT/'classification_report.json').read_text())
    assert hashlib.sha256(basepath.read_bytes()).hexdigest()==report['original_segmentation_sha256']
    base=gpd.read_file(basepath,layer='regions').sort_values('segment_id').reset_index(drop=True)
    classified=gpd.read_file(OUT/'classified_regions.gpkg',layer='classified_regions').sort_values('segment_id').reset_index(drop=True)
    assert len(base)==len(classified)==2634 and classified.segment_id.is_unique
    assert np.array_equal(base.segment_id,classified.segment_id)
    assert all(a.equals_exact(b,0) for a,b in zip(base.geometry,classified.geometry))
    assert classified.is_valid.all() and classified.class_id.between(1,8).all()
    with rasterio.open(OUT/'classified_regions.tif') as src:
        pixels=src.read(1); t=src.transform
    with rasterio.open(ROOT/'output/full_rectangle/unlabelled_regions.tif') as src: ids=src.read(1)
    assert np.array_equal(pixels>0,ids>0)
    raster=rasterize(list(zip(classified.geometry,classified.class_id)),out_shape=pixels.shape,transform=t,dtype='uint8')
    assert np.array_equal(raster,pixels)
    # Fixed footprints must keep roof/industrial distinction exactly.
    buildings=gpd.read_file(ROOT/'output/reviewed_with_industrial.gpkg',layer='buildings_reference')
    structures=gpd.read_file(ROOT/'output/reviewed_with_industrial.gpkg',layer='industrial_structures')
    fixed=rasterize([(g,5) for g in buildings.geometry]+[(r.geometry,5 if r.subtype=='Roofed building' else 6)
        for r in structures.itertuples()],out_shape=pixels.shape,transform=t,dtype='uint8')
    mask=(fixed>0)&(ids>0)
    assert np.array_equal(pixels[mask],fixed[mask]), 'Accepted footprint classes changed'
    union=classified.geometry.union_all()
    assert abs(classified.area.sum()-union.area)<.01
    # Same previously reviewed shoreline locations. This is regression checking,
    # not a random sample and not independent of prior scene interpretation.
    shoreline={'reservoir':(90,1000,True),'lower_river':(560,600,True),
        'middle_river':(800,450,True),'upper_river':(1040,300,True),
        'upper_island':(1230,240,False),'middle_island':(1080,370,False),
        'exposed_bar':(600,560,False),'dry_field':(480,125,False)}
    samples={}
    for name,(x,y,water) in shoreline.items():
        px=int((x-20)*2660/2005); py=int((y-30)*1446/1090)
        actual=int(pixels[py,px]); segment=int(ids[py,px])
        samples[name]={'segment_id':segment,'class_id':actual,'expected_water':water,'passed':bool((actual==1)==water)}
    checks={'integrity_passed':True,'region_count':len(classified),'geometries_unchanged':True,
        'vector_raster_identical':True,'complete_rectangle_coverage':True,
        'accepted_footprint_classes_preserved':True,'shoreline_regression_points':samples,
        'all_shoreline_points_passed':all(v['passed'] for v in samples.values()),
        'note':'Geometry and handpicked point checks do not establish real-world classification accuracy'}
    targeted={427:7,1103:7,1338:4,1610:6,2066:1,2190:1}
    checks['reviewed_object_export_checks']={str(i):bool(classified.loc[classified.segment_id==i,'class_id'].iloc[0]==cls)
        for i,cls in targeted.items()}
    (OUT/'verification.json').write_text(json.dumps(checks,indent=2))
    print(json.dumps(checks,indent=2))
    assert checks['all_shoreline_points_passed'], 'Inspect shoreline mismatches; do not claim a verified shoreline'
    assert all(checks['reviewed_object_export_checks'].values())

if __name__=='__main__': main()
