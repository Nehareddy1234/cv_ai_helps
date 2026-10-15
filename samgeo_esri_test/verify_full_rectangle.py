"""Independent checks of the saved vector/raster partition after composition."""
from pathlib import Path
import json
import hashlib
import numpy as np
import rasterio
from rasterio.features import rasterize
import geopandas as gpd

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'output/full_rectangle'

def main():
    regions=gpd.read_file(OUT/'unlabelled_regions.gpkg',layer='regions')
    extent=gpd.read_file(OUT/'unlabelled_regions.gpkg',layer='test_extent').geometry.iloc[0]
    manifest=json.loads((OUT/'manifest.json').read_text())
    digest=hashlib.sha256((ROOT/'data/esri_test_aligned.tif').read_bytes()).hexdigest()
    assert digest==manifest['image_sha256'], 'Source imagery changed'
    assert not ({'class','class_id','class_name','subtype'}&set(regions.columns))
    assert regions.segment_id.is_unique and regions.is_valid.all()
    assert not regions.is_empty.any()
    with rasterio.open(OUT/'unlabelled_regions.tif') as src:
        labels=src.read(1); transform=src.transform
        assert src.crs==regions.crs and src.nodata==0
    expected=np.zeros(labels.shape,bool); expected[2:-2,2:-2]=True
    assert np.array_equal(labels>0,expected)
    reconstructed=rasterize(list(zip(regions.geometry,regions.segment_id)),
        out_shape=labels.shape,transform=transform,dtype='int32')
    assert np.array_equal(reconstructed,labels), 'Vector/raster labels differ'
    footprint_shapes=[]
    for layer in ('buildings_reference','industrial_structures'):
        frame=gpd.read_file(ROOT/'output/reviewed_with_industrial.gpkg',layer=layer).to_crs(regions.crs)
        footprint_shapes.extend((geom,1) for geom in frame.geometry)
    original_footprints=rasterize(footprint_shapes,out_shape=labels.shape,
        transform=transform,dtype='uint8').astype(bool)&expected
    saved_footprints=np.isin(labels,regions.loc[regions.origin=='Preserved footprint','segment_id'])
    assert np.array_equal(original_footprints,saved_footprints), 'Footprint coverage altered'
    union=regions.geometry.union_all()
    overlap=regions.area.sum()-union.area
    mismatch=union.symmetric_difference(extent).area
    assert abs(overlap)<.01 and mismatch<.01
    counts=np.bincount(labels.ravel())
    pixel_area=abs(transform.a*transform.e-transform.b*transform.d)
    max_area_error=max(abs(row.geometry.area-counts[row.segment_id]*pixel_area)
        for row in regions.itertuples())
    assert max_area_error<.01
    old=json.loads((ROOT/'output/industrial_review.json').read_text())
    current=hashlib.sha256((ROOT.parent/'samgeo/output/bhadra_classified_buildings.gpkg').read_bytes()).hexdigest()
    assert current==old['original_buildings_sha256'], 'Accepted building source changed'
    report={'passed':True,'region_count':len(regions),'vector_raster_identical':True,
        'complete_inner_rectangle':True,'no_semantic_class_fields':True,
        'source_image_unchanged':True,'accepted_buildings_source_unchanged':True,
        'preserved_footprint_pixels_unchanged':True,
        'overlap_m2':float(overlap),'extent_mismatch_m2':float(mismatch),
        'maximum_region_area_error_m2':float(max_area_error)}
    (OUT/'verification.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))

if __name__=='__main__': main()
