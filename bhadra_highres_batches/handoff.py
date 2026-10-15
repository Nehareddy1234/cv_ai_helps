"""Create/verify a stopped-run handoff; never starts inference or resets the queue."""
import argparse
import json
import sqlite3
from pathlib import Path
from common import ROOT, GPKG, MANIFEST, atomic_json, digest, progress, utc
from worker import worker_lock

SNAPSHOT=ROOT/'handoff_snapshot.json'

def check_database():
    with sqlite3.connect(GPKG.as_uri()+'?mode=ro',uri=True) as conn:
        assert conn.execute('PRAGMA quick_check').fetchone()[0]=='ok'
        count,unique=conn.execute('SELECT COUNT(*),COUNT(DISTINCT feature_key) FROM classified_regions').fetchone()
        assert count==unique
        assert conn.execute('SELECT COUNT(*) FROM rtree_classified_regions_geom').fetchone()[0]==count
        assert conn.execute('SELECT COUNT(*) FROM run_jobs').fetchone()[0]==1860
        assert conn.execute("SELECT COUNT(*) FROM run_jobs WHERE status='processing'").fetchone()[0]==0, 'Worker must finish its active batch first'
        return count

def create():
    lock=worker_lock()
    try:
        assert json.loads((ROOT/'control.json').read_text())['stop_requested'], 'Pause before packaging'
        count=check_database()
        import geopandas as gpd
        output=ROOT/'output/classified_regions_PARTIAL.geojson'
        gpd.read_file(GPKG,layer='classified_regions').to_crs(4326).to_file(output,driver='GeoJSON')
        files=[GPKG,output,MANIFEST,ROOT/'Bhadra_Resume_PARTIAL.qgs',ROOT/'output/combined_display.qml',ROOT/'output/classified_regions.qml']
        for folder in sorted((ROOT/'batches').iterdir()):
            if not folder.is_dir(): continue
            # Only top-level source/result/audit files, not rejected placeholders or caches.
            files.extend(p for p in sorted(folder.iterdir()) if p.is_file() and p.suffix in ('.tif','.gpkg','.json','.png'))
        snapshot={'created_utc':utc(),'state':'paused_for_transfer','whole_aoi_complete':False,
                  'region_count':count,'progress':progress(),
                  'files':{p.relative_to(ROOT).as_posix():{'sha256':digest(p),'bytes':p.stat().st_size} for p in files},
                  'note':'GeoPackage is authoritative for the remaining queue; GeoJSON is a WGS84 interchange export only. Uncertainty retained.'}
        atomic_json(SNAPSHOT,snapshot)
        print(json.dumps({'region_count':count,'files':len(files),'progress':snapshot['progress']},indent=2))
    finally: lock.close()

def verify():
    snapshot=json.loads(SNAPSHOT.read_text())
    for relative,info in snapshot['files'].items():
        path=(ROOT/relative).resolve()
        assert path.is_relative_to(ROOT.resolve()), 'Invalid handoff path'
        assert path.stat().st_size==info['bytes'] and digest(path)==info['sha256'], f'Transfer mismatch: {relative}'
    assert check_database()==snapshot['region_count']
    print(f"Transfer verified: {len(snapshot['files'])} files; {snapshot['region_count']} regions. Run worker.py validate for model/reference validation.")

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['create','verify'])
    args=parser.parse_args()
    create() if args.action=='create' else verify()
