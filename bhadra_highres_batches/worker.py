"""Single-worker, resumable whole-AOI execution with atomic GeoPackage publication."""
import argparse
import json
import msvcrt
import os
import shutil
import time
import traceback
import geopandas as gpd
from common import *

def worker_lock():
    stream=(ROOT/'worker.lock').open('a+b')
    if stream.tell()==0: stream.write(b'0'); stream.flush()
    stream.seek(0)
    try: msvcrt.locking(stream.fileno(),msvcrt.LK_NBLCK,1)
    except OSError:
        stream.close(); raise RuntimeError('Another batch worker owns the lock')
    return stream

def validate_inputs():
    manifest=json.loads(MANIFEST.read_text())
    for path,sha in manifest['references'].items():
        assert digest(reference_path(path))==sha,f'Reference changed: {path}; do not silently mix workflows'
    checkpoint=Path(os.environ['SAM_CHECKPOINT']) if os.environ.get('SAM_CHECKPOINT') else reference_path(manifest['checkpoint'])
    assert digest(checkpoint)==manifest['checkpoint_sha256'], 'Wrong SAM ViT-H checkpoint'
    manifest['checkpoint']=str(checkpoint)
    return manifest

def select_device(requested):
    import torch
    if requested=='auto': return 'cuda' if torch.cuda.is_available() else 'cpu'
    if requested=='cuda' and not torch.cuda.is_available():
        raise RuntimeError('CUDA requested but unavailable; install a compatible PyTorch build or use --device cpu')
    return requested

def publish(batch_id):
    folder=batch_dir(batch_id); source=folder/'classified.gpkg'
    report=json.loads((folder/'verification.json').read_text())
    assert report['passed'] and digest(source)==report['gpkg_sha256']
    frame=gpd.read_file(source,layer='classified_regions')
    assert set(frame.batch_id)=={batch_id} and frame.feature_key.is_unique
    verify_regions(frame,owned_geometry(batch_id))
    conn=connect()
    try:
        conn.execute('ATTACH DATABASE ? AS stage',(str(source),))
        columns=[r['name'] for r in conn.execute('PRAGMA main.table_info(classified_regions)') if r['name']!='fid']
        assert set(columns)=={r['name'] for r in conn.execute('PRAGMA stage.table_info(classified_regions)') if r['name']!='fid'}
        names=','.join('"'+name+'"' for name in columns)
        conn.execute('BEGIN IMMEDIATE')
        # Idempotent replacement of this generated batch only, never the seed.
        conn.execute('DELETE FROM main.classified_regions WHERE batch_id=?',(batch_id,))
        conn.execute(f'INSERT INTO main.classified_regions({names}) SELECT {names} FROM stage.classified_regions')
        count=conn.execute('SELECT COUNT(*) FROM main.classified_regions WHERE batch_id=?',(batch_id,)).fetchone()[0]
        assert count==len(frame)
        bounds=frame.total_bounds
        conn.execute("UPDATE gpkg_contents SET min_x=MIN(min_x,?),min_y=MIN(min_y,?),max_x=MAX(max_x,?),max_y=MAX(max_y,?),last_change=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE table_name='classified_regions'",tuple(map(float,bounds)))
        conn.execute("UPDATE run_jobs SET status='complete',detail=?,updated_utc=? WHERE batch_id=?",
            (json.dumps({'regions':count,'gpkg_sha256':report['gpkg_sha256']}),utc(),batch_id))
        assert conn.execute('SELECT COUNT(*) FROM rtree_classified_regions_geom').fetchone()[0]==conn.execute('SELECT COUNT(*) FROM classified_regions').fetchone()[0]
        conn.commit()
    except BaseException:
        conn.rollback(); raise
    finally: conn.close()
    atomic_json(folder/'published.json',{'utc':utc(),'batch_id':batch_id,'regions':len(frame),'source_sha256':report['gpkg_sha256']})
    progress()

def cleanup_generated_cache(batch_id):
    """Only remove this verified batch's regenerable masks and raw XYZ cache."""
    folder=batch_dir(batch_id).resolve()
    assert folder.is_relative_to((ROOT/'batches').resolve()) and (folder/'published.json').exists()
    for child in ('sam','xyz'):
        target=(folder/child).resolve()
        assert target.parent==folder
        if target.exists():
            for file in target.iterdir():
                assert file.is_file() and file.suffix in ('.npz','.json','.jpg','.tmp')
                file.unlink()
            target.rmdir()
    # Keep the imagery, batch GeoPackage, audit and verification for now. The
    # worker stops at the disk threshold instead of deleting review evidence.

def final_check():
    with connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM run_jobs WHERE status!='complete'").fetchone()[0]==0
        assert conn.execute('PRAGMA quick_check').fetchone()[0]=='ok'
        total=conn.execute('SELECT SUM(area_m2) FROM classified_regions').fetchone()[0]
        count=conn.execute('SELECT COUNT(*) FROM classified_regions').fetchone()[0]
        unique=conn.execute('SELECT COUNT(DISTINCT feature_key) FROM classified_regions').fetchone()[0]
        assert count==unique
    manifest=json.loads(MANIFEST.read_text())
    error=abs(total-manifest['aoi_area_km2']*1e6)
    assert error<.1,error
    atomic_json(OUT/'final_verification.json',{'passed':True,'utc':utc(),'region_count':count,
        'area_error_m2':error,'completed_batches':manifest['batch_count'],
        'coverage_method':'Every staged partition verified against its disjoint AOI core before atomic publication; core union verified against complete AOI during planning',
        'semantic_accuracy':'Not independently validated; uncertainty and review attributes retained'})
    progress()

def run(max_batches=0,device='cpu',resume=False):
    lock=worker_lock()
    sam=None; model=None; processed=0
    try:
        manifest=validate_inputs()
        device=select_device(device)
        if resume:
            atomic_json(ROOT/'control.json',{'stop_requested':False,'reason':'Explicit resume on this machine'})
        atomic_json(ROOT/'worker_status.json',{'pid':os.getpid(),'started_utc':utc(),'state':'running','device':device})
        with connect() as conn:
            # A crash can leave an in-progress marker. The OS lock proves that
            # no prior worker remains, and per-stage caches make retry safe.
            conn.execute("UPDATE run_jobs SET status='pending',detail='Resuming interrupted batch' WHERE status='processing'")
        while True:
            control=ROOT/'control.json'
            if control.exists() and json.loads(control.read_text()).get('stop_requested'):
                return 'Stopped at user request'
            with connect() as conn:
                attention=conn.execute("SELECT batch_id,status FROM run_jobs WHERE status IN ('awaiting_review','error','blocked') ORDER BY priority LIMIT 1").fetchone()
                if attention: return f'Needs attention: {dict(attention)}'
                row=conn.execute("SELECT * FROM run_jobs WHERE status='pending' ORDER BY priority LIMIT 1").fetchone()
            if row is None:
                final_check(); return 'Whole AOI verified complete'
            job=dict(row); batch_id=job['batch_id']
            if shutil.disk_usage(ROOT).free<manifest['min_free_gb']*1024**3:
                state(batch_id,'blocked','Less than 8 GiB free; retain all source and result files')
                return 'Storage threshold reached'
            state(batch_id,'processing','Downloading original-resolution Esri imagery')
            try:
                from imagery import download
                from pipeline import run_batch
                download(job)
                if sam is None:
                    import torch
                    from samgeo import SamGeo
                    import joblib
                    torch.set_num_threads(4)
                    state(batch_id,'processing','Loading SAM ViT-H checkpoint')
                    sam=SamGeo(model_type='vit_h',checkpoint=manifest['checkpoint'],automatic=True,device=device,sam_kwargs=PARAMS)
                    model=joblib.load(TEST/'output/full_classification/scene_random_forest.joblib')
                    model.n_jobs=3
                report=run_batch(job,sam,model)
                from preview_batch import preview
                preview(batch_id)
                with connect() as conn:
                    prior=conn.execute("SELECT COUNT(*) FROM run_jobs WHERE status='complete'").fetchone()[0]
                approval=batch_dir(batch_id)/'review_approval.json'
                gate=(prior==0 or report['geometry']['uncertain_area_percent']>75 or report['segmentation']['gap_completion_pixel_percent']>65)
                approved=approval.exists() and json.loads(approval.read_text()).get('gpkg_sha256')==report['gpkg_sha256']
                if gate and not approved:
                    state(batch_id,'awaiting_review','Inspect source and classification preview before publishing this batch')
                    return f'Batch {batch_id} ready for visual review'
                publish(batch_id)
                cleanup_generated_cache(batch_id)
                processed+=1
                print(json.dumps(progress()),flush=True)
                if max_batches and processed>=max_batches: return 'Requested batch limit reached'
            except Exception as exc:
                atomic_json(batch_dir(batch_id)/'error.json',{'utc':utc(),'error':str(exc),'traceback':traceback.format_exc()})
                state(batch_id,'error',str(exc)); raise
    finally:
        atomic_json(ROOT/'worker_status.json',{'pid':os.getpid(),'stopped_utc':utc(),'state':'stopped'})
        lock.close()

def approve(batch_id,note):
    lock=worker_lock()
    try:
        with connect() as conn:
            row=conn.execute('SELECT status FROM run_jobs WHERE batch_id=?',(batch_id,)).fetchone()
        assert row and row['status']=='awaiting_review'
        assert len(note.strip())>=20,'Record what was actually inspected and any remaining uncertainty'
        folder=batch_dir(batch_id)
        atomic_json(folder/'review_approval.json',{'utc':utc(),'note':note,
            'gpkg_sha256':digest(folder/'classified.gpkg'),'review_scope':'Visual QA, not field accuracy'})
        publish(batch_id); cleanup_generated_cache(batch_id)
    finally: lock.close()

def retry(batch_id):
    lock=worker_lock()
    try:
        with connect() as conn:
            row=conn.execute('SELECT status FROM run_jobs WHERE batch_id=?',(batch_id,)).fetchone()
        assert row and row['status'] in ('error','blocked')
        state(batch_id,'pending','Retry requested after inspecting the failure')
    finally: lock.close()

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('action',choices=['run','status','approve','retry','validate','pause'])
    parser.add_argument('--max-batches',type=int,default=0)
    parser.add_argument('--device',choices=['cpu','cuda','auto'],default='cpu')
    parser.add_argument('--resume',action='store_true',help='Explicitly clear the pause flag after input validation and acquiring the exclusive lock')
    parser.add_argument('--batch-id'); parser.add_argument('--review-note')
    args=parser.parse_args()
    if args.action=='run': print(run(args.max_batches,args.device,args.resume),flush=True)
    elif args.action=='status': print(json.dumps(progress(),indent=2))
    elif args.action=='approve': approve(args.batch_id,args.review_note or '')
    elif args.action=='retry': retry(args.batch_id)
    elif args.action=='validate':
        validate_inputs(); print('All reference and checkpoint SHA-256 checks passed')
    elif args.action=='pause':
        atomic_json(ROOT/'control.json',{'stop_requested':True,'reason':'Explicit user pause'})
        print('Pause requested. The active batch finishes before the worker exits; wait for worker_status.json state=stopped before copying files.')
