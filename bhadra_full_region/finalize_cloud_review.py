"""Conservatively flag water-like regions near bright/cloudy RGB imagery.

This is an uncertainty check, not a validated cloud/shadow detector. It can also
flag true water near bright land. It never turns uncertain areas into water.
"""
from pathlib import Path
import json
import numpy as np
import geopandas as gpd
import rasterio
from rasterio.features import rasterize
from scipy import ndimage as ndi

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'output'
TARGET=OUT/'bhadra_sam_vit_h_classification.gpkg'

def main():
    report=json.loads((OUT/'verification.json').read_text())
    assert report['passed']
    frame=gpd.read_file(TARGET,layer='classified_regions')
    with rasterio.open(ROOT/'data/esri_world_imagery.tif') as src:
        rgb=src.read().transpose(1,2,0); transform=src.transform
    bright=(rgb.min(2)>170)&(rgb.mean(2)>195)&((rgb.max(2).astype('int16')-rgb.min(2))<40)
    distance=ndi.distance_transform_edt(~bright)
    ids=rasterize(zip(frame.geometry,frame.segment_id),out_shape=bright.shape,
                  transform=transform,dtype='int32')
    n=int(ids.max())+1
    counts=np.bincount(ids.ravel(),minlength=n)
    # Clouds can cast displaced shadows. This deliberately broad warning is
    # conservative, and may flag genuine ponds; it is not a land/water assertion.
    near=np.bincount(ids.ravel(),weights=(distance<150).ravel(),minlength=n)/np.maximum(counts,1)
    frame['near_bright_context_fraction']=near[frame.segment_id]
    if 'class_before_cloud_review' not in frame:
        frame['class_before_cloud_review']=frame.class_id
    flagged=(frame.class_id==1)&(frame.near_bright_context_fraction>.10)
    frame.loc[flagged,'class_id']=8
    frame.loc[flagged,'class_name']='Uncertain / mixed'
    frame.loc[flagged,'review_reason']='Water-like RGB near bright/cloudy imagery; displaced cloud shadow cannot be excluded'
    frame.to_file(TARGET,layer='classified_regions',driver='GPKG')
    frame[frame.class_id==4].to_file(TARGET,layer='open_ground',driver='GPKG')
    combined=frame.rename(columns={'class_id':'source_class_id','class_name':'source_class_name'}).copy()
    combined['class_id']=combined.source_class_id.where(combined.source_class_id.isin([3,4]),1)
    combined['class_name']=combined.class_id.map({1:'Combined features + uncertain',
        3:'Crops / grass / low vegetation',4:'Bare soil / rock / sparse ground'})
    combined.to_file(TARGET,layer='combined_regions',driver='GPKG')
    with rasterio.open(OUT/'classified_regions.tif') as src:
        profile=src.profile.copy(); tags=src.tags()
    raster=rasterize(zip(frame.geometry,frame.class_id),out_shape=ids.shape,transform=transform,dtype='uint8')
    with rasterio.open(OUT/'classified_regions.tif','w',**profile) as dst:
        dst.write(raster,1); dst.update_tags(**tags)
    saved=gpd.read_file(TARGET,layer='classified_regions')
    boundary=gpd.read_file(TARGET,layer='bhadra_boundary').geometry.union_all()
    union=saved.geometry.union_all()
    assert saved.is_valid.all() and saved.segment_id.is_unique
    assert abs(saved.area.sum()-union.area)<.1
    assert boundary.difference(union).area<.1 and union.difference(boundary).area<.1
    with rasterio.open(OUT/'classified_regions.tif') as src:
        assert np.array_equal(src.read(1),rasterize(zip(saved.geometry,saved.class_id),
            out_shape=ids.shape,transform=transform,dtype='uint8'))
    report['counts_by_class']=saved.class_name.value_counts().to_dict()
    report['area_km2_by_class']=(saved.groupby('class_name').area_m2.sum()/1e6).to_dict()
    report['uncertain_area_percent']=float(saved.loc[saved.class_id==8,'area_m2'].sum()/saved.area_m2.sum()*100)
    reviewed=(saved.class_before_cloud_review==1)&(saved.class_id==8)
    report['water_cloud_review']={'regions_flagged_uncertain':int(reviewed.sum()),
        'area_km2':float(saved.loc[reviewed,'area_m2'].sum()/1e6),
        'bright_proximity_pixels':150,'region_fraction_threshold':.10,
        'interpretation':'Conservative RGB uncertainty flag; may include genuine water near bright surfaces'}
    (OUT/'verification.json').write_text(json.dumps(report,indent=2))
    (ROOT/'progress.json').write_text(json.dumps({'phase':'Verified GeoPackage complete',
        'passed':True,'region_count':len(saved),'cloud_review_complete':True},indent=2))
    print(json.dumps(report['water_cloud_review'],indent=2),flush=True)

if __name__=='__main__': main()
