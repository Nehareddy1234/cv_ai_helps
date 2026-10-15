"""Audit exact seed labels/grid and original tiled SAM settings without inference."""
import json
import numpy as np
import geopandas as gpd
import rasterio
from rasterio.features import rasterize
from common import ROOT,TEST,GPKG,PARAMS,TILES,WIDTH,HEIGHT,load_original,atomic_json,utc


def check():
    reference=load_original('segment_full_rectangle')
    assert reference.PARAMS==PARAMS and reference.TILES==TILES
    with rasterio.open(TEST/'data/esri_test_aligned.tif') as src:
        original_shape=src.shape; original_transform=src.transform; crs=src.crs
    assert original_shape==(HEIGHT,WIDTH)
    old=gpd.read_file(TEST/'output/full_classification/classified_regions.gpkg',layer='classified_regions').set_index('segment_id').sort_index()
    seed=gpd.read_file(GPKG,layer='classified_regions',where="batch_id='seed'").set_index('segment_id').sort_index()
    assert list(old.index)==list(seed.index) and (old.class_id==seed.class_id).all()
    assert seed.geometry.symmetric_difference(old.geometry).area.sum()<1e-8
    def grid(frame,column):
        return rasterize(zip(frame.geometry,frame[column]),out_shape=original_shape,transform=original_transform,dtype='uint8')
    old_pixels=grid(old,'class_id'); seed_pixels=grid(seed,'class_id')
    assert np.array_equal(old_pixels,seed_pixels)
    combined=old_pixels.copy(); combined[np.isin(combined,[1,2,5,6,7,8])]=1
    assert np.array_equal(combined,grid(seed,'combined_id'))
    batches=[]
    for folder in (ROOT/'batches').iterdir():
        path=folder/'esri_rgb.tif'
        if not path.exists(): continue
        with rasterio.open(path) as src:
            assert src.shape==original_shape and src.crs==crs
            assert abs(src.transform.a-original_transform.a)<1e-12
            assert abs(src.transform.e-original_transform.e)<1e-12
            offsets=((src.transform.c-original_transform.c)/original_transform.a,(src.transform.f-original_transform.f)/original_transform.e)
            assert all(abs(v-round(v))<1e-6 for v in offsets)
        report_path=folder/'verification.json'
        report=json.loads(report_path.read_text()) if report_path.exists() else None
        batches.append({'batch_id':folder.name,'same_pixel_spacing':True,'aligned_to_original_pixel_grid':True,
            'same_image_dimensions':True,'native_zoom':json.loads((folder/'imagery.json').read_text())['zoom'],
            'uncertain_area_percent':report['geometry']['uncertain_area_percent'] if report else None})
    result={'utc':utc(),'passed':True,'seed_pixels_identical':True,'seed_combined_pixels_identical':True,
        'sam_tile_windows_and_settings_identical':True,'pixel_size_m':[original_transform.a,-original_transform.e],
        'checked_batches':batches,'semantic_accuracy_verified':False,
        'limitations':['This checks original grid and workflow consistency, not correct labels or perfect boundaries.',
            'Original method scores pixels then labels segments; it is not independent per-pixel semantic classification.',
            'Original 40-pixel fragment cleanup (~9.4 square metres) remains; it does not preserve every one-pixel detail.',
            'SAM global context proposals are resized internally; small 1024x768 tile passes retain the original detailed sampling.',
            'Matching cyan display includes uncertain regions; cyan does not imply confident identification.']}
    atomic_json(ROOT/'reference_fidelity.json',result)
    print(json.dumps(result,indent=2))


if __name__=='__main__': check()
