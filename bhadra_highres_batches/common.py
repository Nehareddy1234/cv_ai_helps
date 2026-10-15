"""Shared, bounded-state helpers for the original-resolution Bhadra batch run."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import sqlite3
import numpy as np
import geopandas as gpd
from shapely import from_wkb
from shapely.geometry import MultiPolygon

ROOT=Path(__file__).resolve().parent
TEST=ROOT.parent/'samgeo_esri_test'
OUT=ROOT/'output'
GPKG=OUT/'bhadra_highres_classification.gpkg'
MANIFEST=ROOT/'manifest.json'

def reference_path(value):
    """Manifest v2 paths are relative to the cloned repository, not a username."""
    path=Path(value)
    return path if path.is_absolute() else ROOT.parent/path

WIDTH,HEIGHT=2660,1446
HALO=128
CORE_W,CORE_H=WIDTH-2*HALO,HEIGHT-2*HALO
TILES=[(x,y,1024,768) for y in (0,678) for x in (0,818,1636)]
PARAMS=dict(points_per_side=24,points_per_batch=16,pred_iou_thresh=.82,
            stability_score_thresh=.90,crop_n_layers=0,min_mask_region_area=40)
FIELDS=['feature_key','batch_id','segment_id','class_id','class_name','combined_id',
        'origin','proposal_id','sam_score','model_score','vote_fraction','vote_margin',
        'suggested_class','method','review_status','review_reason','area_m2',
        'longitude','latitude','source_resolution_m','geometry']

def load_original(name):
    spec=importlib.util.spec_from_file_location('reference_'+name,TEST/(name+'.py'))
    module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module

def utc(): return datetime.now(timezone.utc).isoformat()

def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda:stream.read(8*1024*1024),b''): h.update(chunk)
    return h.hexdigest()

def atomic_json(path,value):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(path.suffix+'.tmp')
    tmp.write_text(json.dumps(value,indent=2),encoding='utf-8'); tmp.replace(path)

def polygon_only(g):
    from shapely.ops import unary_union
    if g.geom_type in ('Polygon','MultiPolygon'): return g
    return unary_union([polygon_only(p) for p in getattr(g,'geoms',[]) if 'Polygon' in p.geom_type or p.geom_type=='GeometryCollection'])

def normalize(frame,batch_id,resolution):
    frame=frame.copy()
    frame['batch_id']=batch_id
    frame['feature_key']=[f'{batch_id}:{int(i)}' for i in frame.segment_id]
    frame['combined_id']=frame.class_id.where(frame.class_id.isin([3,4]),1)
    frame['area_m2']=frame.area
    points=frame.geometry.representative_point().to_crs(4326)
    frame['longitude']=points.x; frame['latitude']=points.y
    frame['source_resolution_m']=resolution
    for col in FIELDS:
        if col not in frame: frame[col]=None
    for col in ('sam_score','model_score','vote_fraction','vote_margin'):
        frame[col]=frame[col].astype('float64')
    for col in ('origin','proposal_id','suggested_class','method','review_status','review_reason'):
        frame[col]=frame[col].fillna('').astype(str)
    frame.geometry=frame.geometry.map(lambda g: MultiPolygon([g]) if g.geom_type=='Polygon' else g)
    return frame[FIELDS]

def decode_gpkg(blob):
    if blob is None: return None
    raw=bytes(blob)
    assert raw[:2]==b'GP', 'Expected GeoPackage geometry'
    envelope_code=(raw[3]>>1)&7
    offset=8+8*{0:0,1:4,2:6,3:6,4:8}[envelope_code]
    return from_wkb(raw[offset:])

class ClosingConnection(sqlite3.Connection):
    def __exit__(self, *args):
        try: return super().__exit__(*args)
        finally: self.close()


def connect(path=GPKG):
    conn=sqlite3.connect(path,timeout=60,factory=ClosingConnection)
    conn.row_factory=sqlite3.Row
    # These implement the standard GeoPackage RTree triggers during atomic SQL
    # publication. Existing GDAL-created spatial index definitions are retained.
    conn.create_function('ST_IsEmpty',1,lambda b: 1 if b is None else int(decode_gpkg(b).is_empty))
    for name,index in [('ST_MinX',0),('ST_MinY',1),('ST_MaxX',2),('ST_MaxY',3)]:
        conn.create_function(name,1,lambda b,i=index: None if b is None else decode_gpkg(b).bounds[i])
    conn.create_function('ST_SRID',1,lambda b: 32643)
    return conn

def state(batch_id,status,detail=''):
    with connect() as conn:
        conn.execute('UPDATE run_jobs SET status=?, detail=?, updated_utc=? WHERE batch_id=?',
                     (status,detail,utc(),batch_id))
    return progress()

def progress():
    with connect() as conn:
        rows=[dict(r) for r in conn.execute('SELECT status,COUNT(*) count,SUM(area_m2) area_m2 FROM run_jobs GROUP BY status')]
        complete=conn.execute("SELECT COALESCE(SUM(area_m2),0) FROM run_jobs WHERE status='complete'").fetchone()[0]
        seed=conn.execute("SELECT SUM(area_m2) FROM classified_regions WHERE batch_id='seed'").fetchone()[0] or 0
        total=conn.execute('SELECT SUM(area_m2) FROM run_jobs').fetchone()[0]+seed
        active=[dict(r) for r in conn.execute("SELECT batch_id,status,detail FROM run_jobs WHERE status NOT IN ('pending','complete')")]
    exhausted=all(r['status']=='complete' for r in rows)
    final_path=OUT/'final_verification.json'
    final_ok=final_path.exists() and json.loads(final_path.read_text()).get('passed',False)
    result={'updated_utc':utc(),'whole_aoi_complete':exhausted and final_ok,'queue_exhausted':exhausted,
        'aoi_area_km2':total/1e6,'verified_area_km2':(complete+seed)/1e6,
        'verified_area_percent':100*(complete+seed)/total,'batches':rows,'attention_or_active':active}
    atomic_json(ROOT/'progress.json',result)
    return result

def batch_dir(batch_id):
    assert batch_id.startswith('b_') and all(c.isalnum() or c=='_' for c in batch_id)
    folder=ROOT/'batches'/batch_id; folder.mkdir(parents=True,exist_ok=True)
    return folder

def owned_geometry(batch_id):
    return gpd.read_file(GPKG,layer='batch_grid',where=f"batch_id='{batch_id}'").geometry.iloc[0]

def verify_regions(frame,expected,tolerance=.02):
    assert len(frame) and frame.is_valid.all() and frame.segment_id.is_unique
    assert frame.class_id.between(1,8).all() and (frame.area>0).all()
    union=frame.geometry.union_all()
    overlap=float(frame.area.sum()-union.area)
    gap=float(expected.difference(union).area); outside=float(union.difference(expected).area)
    assert abs(overlap)<tolerance and gap<tolerance and outside<tolerance,(overlap,gap,outside)
    return {'valid':True,'regions':len(frame),'overlap_m2':overlap,'gap_m2':gap,'outside_m2':outside,
        'uncertain_area_percent':float(frame.loc[frame.class_id==8].area.sum()/frame.area.sum()*100)}
