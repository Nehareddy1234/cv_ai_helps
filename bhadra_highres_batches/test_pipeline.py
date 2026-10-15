"""Read-only production checks and isolated publication transaction tests."""
import tempfile
import unittest
from unittest.mock import patch
import shutil
import pandas as pd
import rasterio
from shapely.geometry import box
import common as c
import worker
import pipeline


class PipelineTests(unittest.TestCase):
    def test_manifest_paths_are_portable(self):
        from pathlib import Path
        manifest=c.json.loads(c.MANIFEST.read_text())
        self.assertEqual(manifest['path_base'],'repository_root')
        for relative in [manifest['checkpoint'],*manifest['references']]:
            self.assertFalse(Path(relative).is_absolute())
            if relative in manifest['references']:
                self.assertTrue(c.reference_path(relative).is_file())
        with patch.object(c,'ROOT',Path('D:/DifferentUser/cv_ai_helps/bhadra_highres_batches')):
            self.assertEqual(c.reference_path('weights/sam_vit_h_4b8939.pth'),Path('D:/DifferentUser/cv_ai_helps/weights/sam_vit_h_4b8939.pth'))

    def test_device_selection_fails_explicitly(self):
        import torch
        with patch.object(torch.cuda,'is_available',return_value=False):
            self.assertEqual(worker.select_device('auto'),'cpu')
            with self.assertRaises(RuntimeError): worker.select_device('cuda')
        with patch.object(torch.cuda,'is_available',return_value=True):
            self.assertEqual(worker.select_device('auto'),'cuda')

    def test_plan_covers_entire_aoi(self):
        grid=c.gpd.read_file(c.GPKG,layer='batch_grid')
        aoi=c.gpd.read_file(c.GPKG,layer='bhadra_boundary').geometry.union_all()
        seed=c.gpd.read_file(c.GPKG,layer='classified_regions',where="batch_id='seed'")
        pieces=list(grid.geometry)+[seed.geometry.union_all()]
        union=c.gpd.GeoSeries(pieces,crs=32643).union_all()
        self.assertEqual(len(grid),1860)
        self.assertLess(aoi.symmetric_difference(union).area,.001)
        self.assertLess(abs(sum(g.area for g in pieces)-union.area),.001)

    def test_seed_is_unchanged(self):
        seed=c.gpd.read_file(c.GPKG,layer='classified_regions',where="batch_id='seed'").set_index('segment_id').sort_index()
        old=c.gpd.read_file(c.TEST/'output/full_classification/classified_regions.gpkg',layer='classified_regions').set_index('segment_id').sort_index()
        self.assertEqual(len(seed),len(old))
        self.assertTrue((seed.class_id==old.class_id).all())
        self.assertLess(seed.geometry.symmetric_difference(old.geometry).area.sum(),1e-8)

    def test_empty_context_and_features(self):
        transform=rasterio.transform.from_origin(580000,1480000,.484992610681435,.48499272632797674)
        ctx=pipeline.context(transform,(32,48))
        self.assertEqual(ctx['accepted_footprints'],0)
        self.assertTrue((ctx['road_distance']==1).all())
        rgb=c.np.full((32,48,3),100,dtype='uint8')
        features=pipeline.features(rgb,ctx['road_distance'])
        self.assertEqual(features.shape,(32,48,16))
        self.assertTrue(c.np.isfinite(features).all())
        self.assertTrue(c.np.allclose(features[:,:,:3],100/255))
        self.assertTrue((features[:,:,-1]==1).all())

    def test_atomic_publication_and_idempotency(self):
        # Only synthetic files in a disposable workspace; no production writes.
        with tempfile.TemporaryDirectory(prefix='pipeline-test-',dir=c.ROOT) as temp:
            root=c.Path(temp); target=root/'target.gpkg'; stage=root/'b_r1001_c1000'; stage.mkdir()
            shutil.copy2(c.GPKG,target)
            frame=c.gpd.read_file(target,layer='classified_regions',rows=1)
            owned=box(600000,1500000,600010,1500010)
            frame.geometry=[owned]; frame['segment_id']=1
            frame=c.normalize(frame,'b_r1001_c1000',.484992610681435)
            frame.to_file(stage/'classified.gpkg',layer='classified_regions',driver='GPKG')
            c.atomic_json(stage/'verification.json',{'passed':True,'gpkg_sha256':c.digest(stage/'classified.gpkg')})
            def connection(): return c.connect(target)
            with patch.object(worker,'connect',connection),patch.object(worker,'batch_dir',lambda _:stage),patch.object(worker,'owned_geometry',lambda _:owned),patch.object(worker,'progress',lambda:None):
                worker.publish('b_r1001_c1000'); worker.publish('b_r1001_c1000')
                with connection() as conn:
                    self.assertEqual(conn.execute("SELECT COUNT(*) FROM classified_regions WHERE batch_id='b_r1001_c1000'").fetchone()[0],1)
                    before=conn.execute('SELECT COUNT(*) FROM classified_regions').fetchone()[0]
                    self.assertEqual(conn.execute('SELECT COUNT(*) FROM rtree_classified_regions_geom').fetchone()[0],before)
                    conn.execute("CREATE TRIGGER injected_failure BEFORE INSERT ON classified_regions BEGIN SELECT RAISE(ABORT,'injected'); END")
                with self.assertRaises(Exception): worker.publish('b_r1001_c1000')
                with connection() as conn:
                    self.assertEqual(conn.execute('SELECT COUNT(*) FROM classified_regions').fetchone()[0],before)
                    self.assertEqual(conn.execute('PRAGMA quick_check').fetchone()[0],'ok')


if __name__=='__main__': unittest.main(verbosity=2)
