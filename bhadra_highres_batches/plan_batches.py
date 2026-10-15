"""Create the complete high-resolution AOI queue without overwriting prior work."""
import math
import json
import shutil
import xml.etree.ElementTree as ET
import geopandas as gpd
import rasterio
from shapely.geometry import box
from shapely import make_valid
from common import *

def main():
    if MANIFEST.exists():
        assert GPKG.exists()
        print(json.dumps(progress(),indent=2)); return
    assert not GPKG.exists(), 'Unfinished initialization exists; inspect before retrying'
    OUT.mkdir(parents=True,exist_ok=True)
    boundary_path=ROOT.parent/'bhadra_full_region/data/bhadra_boundary.geojson'
    boundary=gpd.read_file(boundary_path).to_crs(32643)
    aoi=boundary.geometry.union_all()
    with rasterio.open(TEST/'data/esri_test_aligned.tif') as src:
        assert src.crs.to_epsg()==32643
        rx,ry=src.transform.a,-src.transform.e
        anchor_x=src.transform.c+2*rx; anchor_y=src.transform.f-2*ry
    seed_path=TEST/'output/full_classification/classified_regions.gpkg'
    seed=gpd.read_file(seed_path,layer='classified_regions')
    seed_extent=gpd.read_file(TEST/'output/full_rectangle/unlabelled_regions.gpkg',layer='test_extent').geometry.union_all()
    assert aoi.covers(seed_extent), 'Saved rectangle is not fully inside this AOI'
    verify_regions(seed,seed_extent)
    rows=[]; jobs=[]
    left,bottom,right,top=aoi.bounds
    for row in range(math.floor((anchor_y-top)/(CORE_H*ry)),math.ceil((anchor_y-bottom)/(CORE_H*ry))):
        for col in range(math.floor((left-anchor_x)/(CORE_W*rx)),math.ceil((right-anchor_x)/(CORE_W*rx))):
            x=anchor_x+col*CORE_W*rx; y=anchor_y-row*CORE_H*ry
            core=box(x,y-CORE_H*ry,x+CORE_W*rx,y)
            owned=polygon_only(make_valid(core.intersection(aoi).difference(seed_extent)))
            if owned.is_empty or owned.area<1e-7: continue
            key=f'b_r{row+1000:04d}_c{col+1000:04d}'
            priority=core.distance(seed_extent)+core.centroid.distance(seed_extent.centroid)*.001
            rows.append({'batch_id':key,'row':row,'col':col,'area_m2':owned.area,'geometry':owned})
            jobs.append((key,row,col,priority,owned.area,x-HALO*rx,y+HALO*ry,'pending','',utc()))
    grid=gpd.GeoDataFrame(rows,crs=32643)
    union=grid.geometry.union_all().union(seed_extent)
    assert aoi.symmetric_difference(union).area<.02
    assert abs(grid.area.sum()+seed_extent.area-aoi.area)<.02
    normalized=normalize(seed,'seed',rx)
    normalized.to_file(GPKG,layer='classified_regions',driver='GPKG')
    boundary.to_file(GPKG,layer='bhadra_boundary',driver='GPKG')
    grid.to_file(GPKG,layer='batch_grid',driver='GPKG')
    with connect() as conn:
        conn.execute('CREATE UNIQUE INDEX feature_key_unique ON classified_regions(feature_key)')
        conn.execute('CREATE INDEX batch_id_lookup ON classified_regions(batch_id)')
        conn.execute('CREATE TABLE run_jobs(batch_id TEXT PRIMARY KEY,row INTEGER,col INTEGER,priority REAL,area_m2 REAL,image_left REAL,image_top REAL,status TEXT,detail TEXT,updated_utc TEXT)')
        conn.executemany('INSERT INTO run_jobs VALUES(?,?,?,?,?,?,?,?,?,?)',jobs)
        conn.execute("INSERT INTO gpkg_contents(table_name,data_type,identifier,description,last_change) VALUES('run_jobs','attributes','Batch progress','Whole AOI queue; complete means geometrically verified, not ground-truth accuracy',strftime('%Y-%m-%dT%H:%M:%fZ','now'))")
    references=[boundary_path,seed_path,TEST/'data/esri_test_aligned.tif',
        TEST/'output/full_classification/scene_random_forest.joblib',TEST/'output/reviewed_with_industrial.gpkg',
        TEST/'output/full_classification/context.gpkg',TEST/'segment_full_rectangle.py',
        TEST/'compose_full_rectangle.py',TEST/'classify_full_rectangle.py']
    checkpoint=ROOT.parent/'weights/sam_vit_h_4b8939.pth'
    manifest={'version':2,'path_base':'repository_root','created_utc':utc(),'crs':'EPSG:32643','pixel_size':[rx,ry],
        'batch_image_size':[WIDTH,HEIGHT],'halo_pixels':HALO,'core_pixels':[CORE_W,CORE_H],
        'batch_count':len(jobs),'aoi_area_km2':aoi.area/1e6,'seed_area_km2':seed_extent.area/1e6,
        'zoom':19,'source':'Esri World Imagery XYZ','sam_params':PARAMS,'sam_tiles':TILES,
        'checkpoint':checkpoint.relative_to(ROOT.parent).as_posix(),'checkpoint_sha256':digest(checkpoint),
        'references':{p.relative_to(ROOT.parent).as_posix():digest(p) for p in references},
        'min_free_gb':8,'first_batch_review_required':True,
        'classification':'Original 16-feature scene random forest and region rules; no copied scene-specific IDs',
        'all_batches_planned':True,'grid_gap_m2':aoi.difference(union).area,
        'cpu_estimate_days_at_5_minutes_per_sam_pass':len(jobs)*7*5/(60*24)}
    atomic_json(MANIFEST,manifest)
    shutil.copy2(TEST/'output/full_classification/classified_regions.qml',OUT/'classified_regions.qml')
    style=ET.parse(TEST/'output/combined_classes_with_uncertain/combined_classes.qml')
    style.getroot().find('renderer-v2').set('attr','combined_id')
    style.write(OUT/'combined_display.qml',encoding='utf-8',xml_declaration=True)
    print(json.dumps(manifest,indent=2)); print(json.dumps(progress(),indent=2))

if __name__=='__main__': main()
