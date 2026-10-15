"""Dense, tiled SAM proposals for the entire saved Esri test rectangle.

No semantic labels are used. Each tile is cached separately so CPU runs can
resume. Tile-boundary-truncated masks are excluded during composition, not
presented as rectangular object boundaries.
"""
from pathlib import Path
import hashlib
import json
import time
import os
import numpy as np
import rasterio

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'output/full_rectangle'
OUT.mkdir(exist_ok=True)
PARAMS=dict(points_per_side=24,points_per_batch=16,pred_iou_thresh=.82,
            stability_score_thresh=.90,crop_n_layers=0,min_mask_region_area=40)
TILES=[(x,y,1024,768) for y in (0,678) for x in (0,818,1636)]

def main():
    image_path=ROOT/'data/esri_test_aligned.tif'
    digest=hashlib.sha256(image_path.read_bytes()).hexdigest()
    with rasterio.open(image_path) as src: rgb=src.read().transpose(1,2,0)
    assert rgb.shape[:2]==(1446,2660)
    identity={'image_sha256':digest,'parameters':PARAMS,'tiles':TILES}
    manifest=OUT/'manifest.json'
    if manifest.exists():
        previous=json.loads(manifest.read_text())
        assert previous['image_sha256']==digest and previous['parameters']==PARAMS
    else: manifest.write_text(json.dumps(identity,indent=2))
    todo=[i for i in range(len(TILES)) if not (OUT/f'tile_{i}.json').exists()]
    if not todo:
        print('All six tile caches already available',flush=True); return
    print('Loading SamGeo ViT-H on CPU for dense, overlapping tiles',flush=True)
    import torch
    from samgeo import SamGeo
    torch.set_num_threads(4)
    checkpoint=Path(os.environ.get('SAM_CHECKPOINT', str(ROOT.parent/'weights/sam_vit_h_4b8939.pth')))
    if not checkpoint.is_file():
        raise FileNotFoundError(f'Set SAM_CHECKPOINT or supply the ViT-H checkpoint at {checkpoint}')
    sam=SamGeo(model_type='vit_h',checkpoint=str(checkpoint),
        automatic=True,device='cpu',sam_kwargs=PARAMS)
    for i in todo:
        x,y,w,h=TILES[i]; t=time.time()
        print(f'Tile {i+1}/6: generating masks ({x},{y},{w},{h})',flush=True)
        with torch.inference_mode(): masks=sam.mask_generator.generate(rgb[y:y+h,x:x+w])
        arrays={}; records=[]
        for j,m in enumerate(masks):
            mask=m['segmentation']; yy,xx=np.where(mask)
            if not len(xx): continue
            x0=int(xx.min()); x1=int(xx.max())+1; y0=int(yy.min()); y1=int(yy.max())+1
            clipped_internal_edge=bool((x>0 and x0<=2) or (y>0 and y0<=2) or
                (x+w<rgb.shape[1] and x1>=w-2) or (y+h<rgb.shape[0] and y1>=h-2))
            key=f'm{j}'
            arrays[key]=mask[y0:y1,x0:x1]
            records.append({'key':key,'bbox':[x+x0,y+y0,x1-x0,y1-y0],
                'area_px':int(mask.sum()),'sam_score':float(m['predicted_iou']),
                'stability':float(m['stability_score']),'internal_edge':clipped_internal_edge})
        np.savez_compressed(OUT/f'tile_{i}.npz',**arrays)
        report={'tile':i,'window':[x,y,w,h],'elapsed_seconds':time.time()-t,'masks':records}
        (OUT/f'tile_{i}.json').write_text(json.dumps(report,indent=2))
        print(f'Tile {i+1}/6 saved: {len(records)} proposals, {time.time()-t:.1f} seconds',flush=True)
        (OUT/'progress.json').write_text(json.dumps({'completed_tiles':i+1,'total_tiles':6,'last_elapsed_seconds':time.time()-t}))
    print('All six tiles complete. Run compose_full_rectangle.py next.',flush=True)

if __name__=='__main__': main()
